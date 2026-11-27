"""A review of a named local ref (register E168; SYS-45; the designer's decision of 2026-11-06, (d); ADR-0008 and
ADR-0006 as amended): the Ticket names the ref, each dispatch pins its commit and merge-base, the executor observes that
commit read-only, writes a ``ref_review`` whose freshness follows the ref and never gates, and nothing is fetched.
The end-to-end path through the real CLI is ``tests/integration/test_ref_review_flow.py``."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aewflow import Role, create_unit, plan_unit, sample_project
from conftest import git
from invariants import assert_control_invariants

from aew import roles
from aew.engine import freshness as F
from aew.engine import ref_review as R
from aew.engine.api import Engine
from aew.engine.role_ops import Roles
from aew.errors import AEWError, PermissionDenied, UsageError, ValidationFailed
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.workspace import git as G
from aew.workspace import worktrees

REVIEW = {"claim": "reviewed", "result": "pass", "producer": {"model": "scripted-reviewer"},
          "ref_review": {"summary": "adds subtract", "findings": [],
                         "requirement_trace": [{"requirement": "subtract exists", "status": "covered"}],
                         "checked": ["the diff"], "not_checked": []}}


def commit_on(p, name: str, path: str = "calc/sub.py", text: str = "def subtract(a, b):\n    return a - b\n",
              *, start: str = "main") -> str:
    """A branch ``name`` from ``start`` with one more commit, made in its own worktree (the operator's checkout stays
    on main); a second call adds a commit to the same branch."""
    where = p.root.parent / f"wt-{name.replace('/', '-')}"
    if not where.exists():
        git("worktree", "add", "-q", "-b", name, str(where), start, cwd=p.root)
    (where / path).parent.mkdir(parents=True, exist_ok=True)
    (where / path).write_text(text, encoding="utf-8")
    git("add", path, cwd=where)
    git("commit", "-q", "-m", f"{name}: {path}", cwd=where)
    return git("rev-parse", "HEAD", cwd=where)


def ref_ticket(p, tmp_path: Path, ref: str = "feature/x", *extra: str) -> str:
    wid = create_unit(p, "ticket", f"Review {ref}", cls=1,
                      extra=("--non-mutating", "--review-ref", ref, "--goal", "subtract exists", *extra))
    plan_unit(p, tmp_path, wid, "Review the branch against the requirement.\n")
    return wid


def refused(p, *args: str) -> dict[str, Any]:
    res = p.aew(*p.lead_args(*args), env={"AEW_LEAD_TOKEN": p.token})
    assert res.returncode != 0, res.stdout
    return res.error


def engine(p) -> Engine:
    return Engine(p.root, p.root / ".aew")


@pytest.fixture
def project(tmp_path):
    p = sample_project(tmp_path)
    commit_on(p, "feature/x")
    return p


# ---------------------------------------------------------------------------------------------- the name at creation


def test_a_review_ref_is_resolved_to_its_full_name_at_creation_and_never_to_a_commit(project, tmp_path):
    wid = ref_ticket(project, tmp_path)
    control = project.ok("work", "show", wid)["control"]
    assert control["review_ref"] == "refs/heads/feature/x"
    assert "execution" not in control and not any(len(v) == 40 for v in [control["review_ref"]])
    tag = git("rev-parse", "feature/x", cwd=project.root)
    git("tag", "v1", tag, cwd=project.root)
    assert project.ok("work", "show", ref_ticket(project, tmp_path, "v1"))["control"]["review_ref"] == "refs/tags/v1"
    # git's own short forms of an accepted ref name that ref (review of #661, m1)
    assert G.full_ref_name("heads/feature/x", cwd=project.root) == "refs/heads/feature/x"
    assert G.full_ref_name("tags/v1", cwd=project.root) == "refs/tags/v1"
    assert_control_invariants(project)


def test_head_is_recorded_as_the_branch_it_points_at(project):
    git("checkout", "-q", "-b", "topic", cwd=project.root)
    git("commit", "-q", "--allow-empty", "-m", "topic", cwd=project.root)
    assert G.full_ref_name("HEAD", cwd=project.root) == "refs/heads/topic"


@pytest.mark.parametrize("name, reason", [
    ("refs/stash", "ref_namespace"), ("refs/notes/commits", "ref_namespace"), ("notes/commits", "ref_namespace"),
    ("refs/replace/x", "ref_namespace"), ("HEAD~1", "not_a_ref"), ("main..feature/x", "not_a_ref"),
    ("feature/x^{tree}", "not_a_ref"), ("feature/x:calc", "not_a_ref"), ("main@{1}", "not_a_ref"),
    ("-x", "not_a_ref")])
def test_a_review_ref_outside_the_reviewable_namespaces_is_refused(project, name, reason):
    root = project.root
    git("notes", "add", "-m", "n", "HEAD", cwd=root)
    git("update-ref", "refs/replace/x", "HEAD", cwd=root)
    (root / "calc" / "core.py").write_text("# stash me\n", encoding="utf-8")
    git("stash", "-q", cwd=root)
    with pytest.raises(UsageError) as exc:
        G.full_ref_name(name, cwd=root)
    assert exc.value.details["reason"] == reason


def test_a_commit_id_is_refused_as_not_a_ref_with_the_way_to_review_one(project):
    sha = git("rev-parse", "feature/x", cwd=project.root)
    for name in (sha, sha[:12]):
        with pytest.raises(UsageError) as exc:
            G.full_ref_name(name, cwd=project.root)
        assert exc.value.details["reason"] == "not_a_ref" and "create a branch at it" in exc.value.message


def test_an_ambiguous_short_ref_is_refused_with_its_candidates(project):
    git("tag", "feature/x", "main", cwd=project.root)
    with pytest.raises(UsageError) as exc:
        G.full_ref_name("feature/x", cwd=project.root)
    assert exc.value.details["reason"] == "ambiguous_ref"
    assert exc.value.details["candidates"] == ["refs/heads/feature/x", "refs/tags/feature/x"]
    assert G.full_ref_name("refs/tags/feature/x", cwd=project.root) == "refs/tags/feature/x"


def test_an_aew_ticket_branch_is_never_reviewable(project):
    prefix = worktrees.branch_name("T-0009", 1)  # the prefix as AEW's own branches take it
    git("branch", prefix, "feature/x", cwd=project.root)
    with pytest.raises(PermissionDenied) as exc:
        R.resolve(project.root, prefix, authoritative_branch="main")
    assert exc.value.details["reason"] == "aew_managed_ref"
    with pytest.raises(UsageError) as exc:
        R.resolve(project.root, "main", authoritative_branch="main")
    assert exc.value.details["reason"] == "authoritative_ref"


def test_a_ref_review_is_refused_on_a_mutating_ticket(project):
    error = refused(project, "work", "create", "ticket", "--title", "Review", "--class", "1",
                    "--review-ref", "feature/x")
    assert error["code"] == "USAGE" and error["details"]["reason"] == "ref_review_mutating"


def test_an_unknown_or_detached_or_unborn_name_is_refused_at_creation(project):
    error = refused(project, "work", "create", "ticket", "--title", "Review", "--class", "1", "--non-mutating",
                    "--review-ref", "no-such-branch")
    assert error["code"] == "NOT_FOUND" and error["details"]["reason"] == "unknown_ref"
    root = project.root
    git("checkout", "-q", "--detach", "main", cwd=root)
    with pytest.raises(UsageError) as exc:
        G.full_ref_name("HEAD", cwd=root)
    assert exc.value.details["reason"] == "detached_head"
    git("checkout", "-q", "--orphan", "empty", cwd=root)
    with pytest.raises(AEWError) as exc:
        G.full_ref_name("HEAD", cwd=root)
    assert exc.value.code == "ILLEGAL_TRANSITION" and exc.value.details["reason"] == "unborn_ref"


def test_review_ref_is_classified_in_the_kind_group():
    from aew.engine import ticket_fields as TF

    reg = TF.load_registry()
    assert reg.classifies_control("review_ref")
    entry = next(f for f in reg.fields if f.name == "review_ref")
    assert entry.group == "kind"


# ---------------------------------------------------------------------------------------------- the pin at dispatch


def test_dispatch_pins_the_commit_it_resolved_even_when_the_ref_moves_during_dispatch(project, tmp_path, monkeypatch):
    wid = ref_ticket(project, tmp_path)
    resolved = git("rev-parse", "feature/x", cwd=project.root)
    real = worktrees.allocate_detached

    def moving(**kwargs: Any) -> dict[str, Any]:  # the ref moves between its resolution and the checkout
        commit_on(project, "feature/x", "calc/late.py", "late = 1\n")
        return real(**kwargs)

    monkeypatch.setattr(worktrees, "allocate_detached", moving)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    assert out["execution"]["ref_pin"]["commit"] == resolved == out["observation"]["commit"]
    assert git("rev-parse", "HEAD", cwd=Path(out["observation"]["path"])) == resolved
    assert git("rev-parse", "feature/x", cwd=project.root) != resolved
    assert_control_invariants(project)


def test_dispatch_pins_the_merge_base_against_the_authoritative_branch(project, tmp_path):
    root = project.root
    fork = git("rev-parse", "main", cwd=root)
    commit_on(project, "main-moves", "calc/m.py", "m = 1\n")  # main gains a commit after the branch point
    git("checkout", "-q", "main", cwd=root)
    git("merge", "-q", "--ff-only", "main-moves", cwd=root)
    wid = ref_ticket(project, tmp_path)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    pin = out["execution"]["ref_pin"]
    assert pin["merge_base"] == fork and pin["merge_bases"] == 1
    assert pin["authoritative_commit"] == git("rev-parse", "main", cwd=root) and pin["authoritative_branch"] == "main"
    assert_control_invariants(project)


def test_a_criss_cross_history_pins_the_first_merge_base_and_counts_them(project):
    root = project.root
    a = commit_on(project, "cc-a", "calc/a.py", "a = 1\n")
    b = commit_on(project, "cc-b", "calc/b.py", "b = 1\n")
    wa, wb = root.parent / "wt-cc-a", root.parent / "wt-cc-b"
    git("merge", "-q", "--no-edit", b, cwd=wa)
    git("merge", "-q", "--no-edit", a, cwd=wb)
    tip_a = git("rev-parse", "HEAD", cwd=wa)
    git("update-ref", "refs/heads/main", tip_a, cwd=root)
    git("reset", "-q", "--hard", cwd=root)
    commit_on(project, "cc-b", "calc/c.py", "c = 1\n")
    pin = R.pin(root, "refs/heads/cc-b", authoritative_branch="main", authoritative_commit=tip_a)
    bases = git("merge-base", "--all", tip_a, git("rev-parse", "cc-b", cwd=root), cwd=root).split()
    assert len(bases) == 2 and pin["merge_base"] == bases[0] and pin["merge_bases"] == 2


def test_a_ref_with_no_merge_base_is_refused(project):
    root = project.root
    git("checkout", "-q", "--orphan", "island", cwd=root)
    git("commit", "-q", "--allow-empty", "-m", "island", cwd=root)
    git("checkout", "-q", "-f", "main", cwd=root)
    with pytest.raises(AEWError) as exc:
        R.pin(root, "refs/heads/island", authoritative_branch="main",
              authoritative_commit=git("rev-parse", "main", cwd=root))
    assert exc.value.code == "ILLEGAL_TRANSITION" and exc.value.details["reason"] == "no_merge_base"


def test_a_ref_already_in_the_authoritative_branch_is_refused(project):
    root = project.root
    git("branch", "old", "main", cwd=root)
    with pytest.raises(AEWError) as exc:
        R.pin(root, "refs/heads/old", authoritative_branch="main", authoritative_commit=git("rev-parse", "main",
                                                                                            cwd=root))
    assert exc.value.code == "ILLEGAL_TRANSITION" and exc.value.details["reason"] == "ref_already_contained"


def test_a_deleted_ref_is_refused_at_dispatch(project, tmp_path):
    wid = ref_ticket(project, tmp_path)
    git("worktree", "remove", "--force", str(project.root.parent / "wt-feature-x"), cwd=project.root)
    git("branch", "-D", "feature/x", cwd=project.root)
    error = refused(project, "work", "dispatch", wid)
    assert error["code"] == "NOT_FOUND" and error["details"]["reason"] == "unknown_ref"
    assert "AEW fetches nothing" in error["message"]
    assert project.ok("work", "show", wid)["control"]["state"] == "READY"


def test_a_tag_that_is_not_a_commit_is_refused(project):
    root = project.root
    tree = git("rev-parse", "main^{tree}", cwd=root)
    git("tag", "-a", "-m", "a tree", "treetag", tree, cwd=root)
    with pytest.raises(UsageError) as exc:
        R.pin(root, "refs/tags/treetag", authoritative_branch="main",
              authoritative_commit=git("rev-parse", "main", cwd=root))
    assert exc.value.details["reason"] == "not_a_commit"


def test_a_redispatch_repins_to_the_refs_current_commit_and_the_earlier_record_stays_history(project, tmp_path):
    wid = ref_ticket(project, tmp_path)
    eng = engine(project)
    first = eng.work_dispatch(token=project.token, work_id=wid)
    project.lead("work", "transition", wid, "--to", "RUNNING")
    old = Role(project, first["invocation_token"], Path(first["observation"]["path"]))
    old_record = old.submit(E.REF_REVIEW, REVIEW, "First.\n")["evidence"]
    moved = commit_on(project, "feature/x", "calc/more.py", "more = 1\n")
    again = project.lead("work", "redispatch", wid, "--reason", "review the new commit")
    assert again["execution"]["ref_pin"]["commit"] == moved != first["execution"]["ref_pin"]["commit"]
    history = project.ok("work", "show", wid)["control"]["execution_history"]
    assert history[0]["ref_pin"]["commit"] == first["execution"]["ref_pin"]["commit"]
    error = refused(project, "evidence", "ingest", wid, "--evidence", old_record)
    assert error["code"] == "GATE_UNSATISFIED"
    assert_control_invariants(project)


def test_uncommitted_work_in_the_branchs_worktree_is_reported_and_its_index_is_untouched(project, tmp_path):
    where = project.root.parent / "wt-feature-x"
    (where / "calc" / "sub.py").write_text("edited, not committed\n", encoding="utf-8")
    index = (Path(git("rev-parse", "--absolute-git-dir", cwd=where)) / "index")
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    wid = ref_ticket(project, tmp_path)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    noticed = out["execution"]["ref_pin"]["uncommitted"]
    assert Path(noticed["worktree"]).resolve() == where.resolve() and noticed["paths"] == 1  # git prints C:/ on Windows
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before
    pack = (project.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "1 tracked path(s) had uncommitted changes" in pack
    assert_control_invariants(project)


def test_the_untrusted_filter_guard_reads_the_pinned_commit(project, tmp_path):
    """A filter only the branch assigns: the authoritative commit has no such attribute, so a guard that read it would
    let the observation be checked out without the filter."""
    git("config", "filter.evil.clean", "cat", cwd=project.root)
    commit_on(project, "feature/x", ".gitattributes", "*.py filter=evil\n")
    wid = ref_ticket(project, tmp_path)
    error = refused(project, "work", "dispatch", wid)
    assert error["code"] == "DISPATCH_REFUSED" and "GIT_DRIVER_UNTRUSTED" in error["details"]["reason_codes"]
    # the authoritative commit assigns no such filter: a guard reading it, not the pinned commit, would admit this
    assert G.untrusted_filters(project.root, git("rev-parse", "main", cwd=project.root)) == []


# ---------------------------------------------------------------------------------------------- no fetch


def test_a_ref_review_never_fetches(project, tmp_path, monkeypatch):
    wid = ref_ticket(project, tmp_path)
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []
    real_git, real_object = G.git, G.object_git

    def seen_git(*args: str, **kw: Any) -> Any:
        calls.append((args, kw.get("env")))
        return real_git(*args, **kw)

    def seen_object(*args: str, **kw: Any) -> Any:
        calls.append((args, G.OBJECT_ENV))
        return real_object(*args, **kw)

    monkeypatch.setattr(G, "git", seen_git)
    monkeypatch.setattr(G, "object_git", seen_object)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    words = {a for args, _ in calls for a in args}
    assert not words & {"fetch", "ls-remote", "pull", "remote"}
    add = [env for args, env in calls if args[:2] == ("worktree", "add")]
    # the observation's checkout reads objects only, and downloads no LFS content (review of #661, m2)
    assert add and all(env == R.CHECKOUT_ENV for env in add)
    assert R.CHECKOUT_ENV["GIT_LFS_SKIP_SMUDGE"] == "1" and G.OBJECT_ENV.items() <= R.CHECKOUT_ENV.items()
    ref_calls = [args for args, env in calls if env == G.OBJECT_ENV]
    assert any(a[:1] == ("merge-base",) for a in ref_calls) and any(a[:1] == ("for-each-ref",) for a in ref_calls)
    assert G.OBJECT_ENV["GIT_NO_LAZY_FETCH"] == "1"
    assert out["execution"]["ref_pin"]["commit"]


def test_a_ref_review_in_a_partial_clone_on_old_git_is_refused(project, tmp_path, monkeypatch):
    wid = ref_ticket(project, tmp_path)
    git("config", "extensions.partialClone", "origin", cwd=project.root)
    monkeypatch.setattr(G, "version", lambda cwd, **_: (2, 43, 0))
    with pytest.raises(AEWError) as exc:
        engine(project).work_dispatch(token=project.token, work_id=wid)
    assert exc.value.code == "UNAVAILABLE" and exc.value.details["reason"] == "lazy_fetch_possible"
    monkeypatch.setattr(G, "version", lambda cwd, **_: (2, 44, 0))  # a git that honours GIT_NO_LAZY_FETCH
    assert not G.lazy_fetch_possible(project.root)


# ---------------------------------------------------------------------------------------------- the record


def test_findings_set_the_verdict_and_never_fail_the_record():
    pin = {"name": "refs/heads/x", "commit": "a" * 40, "merge_base": "b" * 40, "merge_bases": 1,
           "authoritative_branch": "main", "authoritative_commit": "c" * 40,
           "uncommitted": {"worktree": "w", "paths": 1}}
    clear = E.ref_review_binding(pin, REVIEW)
    assert clear["verdict"] == E.VERDICT_CLEAR and "uncommitted" not in clear["reviewed_ref"]
    blocker = {**REVIEW, "ref_review": {**REVIEW["ref_review"], "findings": [
        {"id": "F1", "severity": "blocker", "summary": "breaks", "location": "a.py:1"}]}}
    found = E.ref_review_binding(pin, blocker)
    assert found["verdict"] == E.VERDICT_FINDINGS and found["ref_review"]["findings"][0]["required"] is True
    assert "result" not in found  # the record's result stays the submitter's: the review was done
    twice = {**REVIEW, "ref_review": {**REVIEW["ref_review"], "findings": [
        {"id": "F1", "severity": "minor", "summary": "a"}, {"id": "F1", "severity": "minor", "summary": "b"}]}}
    with pytest.raises(ValidationFailed) as exc:
        E.ref_review_binding(pin, twice)
    assert exc.value.details["reason"] == "duplicate_finding"


def test_a_ref_review_submission_cannot_supply_its_pin():
    for field in ("reviewed_ref", "verdict"):
        with pytest.raises(ValidationFailed) as exc:
            E.check_submission("investigator", E.REF_REVIEW, {**REVIEW, field: {}}, scope="observation",
                               expected=E.REF_REVIEW)
        assert field in exc.value.details["fields"]


def test_an_investigator_is_never_offered_submit_ref_review_and_a_branch_reviewer_never_a_discovery_record():
    ops = roles.archetype("investigator")["engine_operations"]
    assert "submit.ref_review" not in E.submit_operations(ops, "investigator", "observation", "discovery_record")
    assert "submit.ref_review" not in E.submit_operations(ops, "investigator", "observation")
    assert "submit.discovery_record" not in E.submit_operations(ops, "investigator", "observation", E.REF_REVIEW)
    assert "submit.ref_review" in E.submit_operations(ops, "investigator", "observation", E.REF_REVIEW)
    with pytest.raises(PermissionDenied) as exc:
        E.check_submission("investigator", E.REF_REVIEW, REVIEW, scope="observation", expected="discovery_record")
    assert exc.value.details["reason"] == "not_the_pinned_kind"
    with pytest.raises(PermissionDenied):
        E.check_submission("investigator", "discovery_record", {}, scope="observation", expected=E.REF_REVIEW)


def test_a_ref_ticket_refuses_a_card_without_ref_review_and_branch_reviewer_refuses_a_ticket_without_a_ref():
    cards = roles.builtin_cards()
    ref_unit = {"kind": "ticket", "mutating": False, "title": "Review", "review_ref": "refs/heads/x"}
    plain = {"kind": "ticket", "mutating": False, "title": "Investigate"}
    roles_ops = Roles.__new__(Roles)
    with pytest.raises(UsageError) as exc:
        roles_ops.slot_ok(ref_unit, "execute", cards["investigator"])
    assert exc.value.details["reason"] == "card_not_a_ref_reviewer"
    with pytest.raises(UsageError) as exc:
        roles_ops.slot_ok(plain, "execute", cards[E.REF_REVIEW_CARD])
    assert exc.value.details["reason"] == "no_ref_to_review"
    roles_ops.slot_ok(ref_unit, "execute", cards[E.REF_REVIEW_CARD])
    roles_ops.slot_ok(plain, "execute", cards["investigator"])


# ---------------------------------------------------------------------------------------------- freshness


def record(pin: dict[str, Any]) -> dict[str, Any]:
    return {"kind": E.REF_REVIEW, "reviewed_ref": pin, "evaluated_snapshot": {"base_revision": pin["commit"]}}


def test_a_ref_review_record_moves_from_current_to_moved_and_never_stale(project):
    root = project.root
    tip = git("rev-parse", "feature/x", cwd=root)
    pin = {"name": "refs/heads/feature/x", "commit": tip}
    fresh = F.record_freshness(root, record(pin), git("rev-parse", "main", cwd=root))
    assert fresh["status"] == F.CURRENT and fresh["source_bound"] is False and fresh["basis"] == "ref"
    commit_on(project, "feature/x", "calc/more.py", "more = 1\n")
    fresh = F.record_freshness(root, record(pin), None)
    assert (fresh["status"], fresh["moved"], fresh["detail"]) == (F.UNKNOWN, F.FORWARD, F.REF_MOVED)
    where = root.parent / "wt-feature-x"
    git("reset", "-q", "--hard", "main", cwd=where)
    git("commit", "-q", "--allow-empty", "-m", "rewritten", cwd=where)
    assert F.record_freshness(root, record(pin), None, timeout=30)["moved"] == F.REWRITTEN
    git("worktree", "remove", "--force", str(where), cwd=root)
    git("branch", "-D", "feature/x", cwd=root)
    fresh = F.record_freshness(root, record(pin), None)
    assert fresh["moved"] == F.DELETED and fresh["status"] == F.UNKNOWN
    assert F.is_acceptable_input(fresh)  # never gates a consumer


def test_discovery_record_freshness_is_unchanged(project):
    root = project.root
    head = git("rev-parse", "main", cwd=root)
    discovery = {"kind": "discovery_record", "evaluated_snapshot": {"base_revision": head},
                 "discovery": {"observed_paths": ["calc/**"]}}
    fresh = F.record_freshness(root, discovery, head)
    assert fresh == {"basis": "authoritative-source", "source_bound": True, "observed_commit": head,
                     "authoritative_commit": head, "status": F.CURRENT, "scope": "declared paths"}
    assert F.cached_by_head(discovery) and not F.cached_by_head(record({"name": "x", "commit": head}))


def test_a_moved_ref_never_blocks_ingest_acceptance_or_a_consumer(project, tmp_path):
    wid = ref_ticket(project, tmp_path)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    project.lead("work", "transition", wid, "--to", "RUNNING")
    role = Role(project, out["invocation_token"], Path(out["observation"]["path"]))
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")["evidence"]
    commit_on(project, "feature/x", "calc/more.py", "more = 1\n")  # the ref moves after the review
    project.lead("evidence", "ingest", wid, "--evidence", sealed)
    gate = project.ok("gate", "show", wid)["gates"]["execute_record"]
    assert gate["status"] == "CURRENT" and gate["freshness"]["moved"] == F.FORWARD
    project.lead("work", "accept", wid)
    consumer = create_unit(project, "ticket", "Act on the review", cls=1,
                           extra=("--non-mutating", "--goal", "g", "--depends-on", f"{wid}:evidence"))
    plan_unit(project, tmp_path, consumer, "Read the review.\n")
    later = engine(project).work_dispatch(token=project.token, work_id=consumer)  # no INPUT_STALE, no acknowledgement
    [consumed] = project.ok("work", "show", consumer)["control"]["execution"]["dependencies"]
    assert consumed == {"id": wid, "kind": "evidence"} and later["execution"]["expected_kind"] == "discovery_record"
    assert_control_invariants(project)


def test_the_dashboard_never_caches_a_ref_reviews_freshness(project, monkeypatch):
    from aew.dashboard.projections import Projector

    root = project.root
    calls = []

    class Cache(dict):
        def put(self, key: Any, value: Any) -> None:
            self[key] = value

    cache = Cache()
    fake = SimpleNamespace(_maps=lambda: SimpleNamespace(architecture=cache),
                           s=SimpleNamespace(engine=SimpleNamespace(repo_root=root)))
    monkeypatch.setattr("aew.dashboard.projections.record_freshness",
                        lambda *a, **k: calls.append(a[1]["kind"]) or {"status": "CURRENT"})
    head = git("rev-parse", "main", cwd=root)
    review = {"id": "EV-1", **record({"name": "refs/heads/feature/x", "commit": head})}
    discovery = {"id": "EV-2", "kind": "discovery_record", "evaluated_snapshot": {"base_revision": head}}
    for _ in range(2):
        Projector._architecture_freshness(fake, review, head)
        Projector._architecture_freshness(fake, discovery, head)
    assert calls == [E.REF_REVIEW, "discovery_record", E.REF_REVIEW]
    assert list(cache) == [("EV-2", head, head)]


# ---------------------------------------------------------------------------------------------- the pack and checks


def test_the_pack_carries_the_requirement_and_the_diff_from_the_merge_base(project, tmp_path, monkeypatch):
    wid = ref_ticket(project, tmp_path)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    pack = (project.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "subtract exists" in pack and "## The reviewed change" in pack and "+def subtract(a, b):" in pack
    assert f"`{out['execution']['ref_pin']['merge_base']}`" in pack
    pin = out["execution"]["ref_pin"]
    monkeypatch.setattr(R, "REF_DIFF_MAX_BYTES", 10)
    view = R.pack_view(project.root, pin)
    assert view["diff"] is None and view["paths"] == ["calc/sub.py"] and "sub.py" in view["stat"]
    assert view == R.pack_view(project.root, pin)  # a function of two pinned commits: a regenerated pack matches


def test_the_ref_review_report_format_is_what_the_engine_accepts():
    kind, template = ctxmod.output_template("investigator", "observation", E.REF_REVIEW)
    assert kind == E.REF_REVIEW
    E.check_submission("investigator", kind, template, scope="observation", expected=E.REF_REVIEW)
    pin = {"name": "refs/heads/x", "commit": "a" * 40, "merge_base": "b" * 40, "merge_bases": 1,
           "authoritative_branch": "main", "authoritative_commit": "c" * 40, "uncommitted": None}
    assert E.ref_review_binding(pin, template)["verdict"] == E.VERDICT_CLEAR
    allowed = ctxmod._allowed_values("investigator", "observation", E.REF_REVIEW)
    assert template["result"] in allowed["result"] and set(allowed) == {"result", "status", "severity"}


def test_a_check_on_a_ref_review_runs_only_contained(project, tmp_path, monkeypatch):
    """The operator's ruling of 2026-11-27 on E168's Q1 (a weaker context is not allowed by default to run tests or
    code): a check of a ref's code never runs outside a sandbox, by a run's supervisor or by the operator's own
    command; the built-in guardrails check runs no code."""
    wid = ref_ticket(project, tmp_path)
    eng = engine(project)
    out = eng.work_dispatch(token=project.token, work_id=wid)
    token = out["invocation_token"]
    weaker = {"filesystem": "workdir_separation_only"}
    with pytest.raises(PermissionDenied) as exc:
        eng.check_run(invocation_token=token, check_id="unit", label=weaker, layout=None)
    assert exc.value.details["reason"] == "ref_check_uncontained"
    # a layout, but a label that is not the contained filesystem: still refused (review of #661, m3)
    with pytest.raises(PermissionDenied) as exc:
        eng.check_run(invocation_token=token, check_id="unit", label=weaker, layout=SimpleNamespace(net_dir=None))
    assert exc.value.details["reason"] == "ref_check_uncontained"
    from aew.harness import containment

    monkeypatch.setattr(containment, "establish", lambda **_: (None, containment.label(contained=False)))
    with pytest.raises(PermissionDenied) as exc:
        eng.check_run(invocation_token=token, check_id="unit")
    assert exc.value.details["reason"] == "ref_check_uncontained"
    assert not list((project.root / ".aew" / "evidence").rglob(f"{out['invocation']}-check-*"))
    assert eng.check_run(invocation_token=token, check_id="guardrails")["ok"]


def test_git_level_ref_helpers_never_write(project):
    """The resolution, the pin and the freshness read; none of them takes a lock or writes a ref (spot check of the
    object_git seam's arguments)."""
    root = project.root
    before = git("for-each-ref", cwd=root)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    G.full_ref_name("feature/x", cwd=root)
    R.pin(root, "refs/heads/feature/x", authoritative_branch="main", authoritative_commit=git("rev-parse", "main",
                                                                                              cwd=root))
    assert git("for-each-ref", cwd=root) == before
    assert subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout == status


def test_a_branch_reviewer_run_has_no_writable_bind_on_its_observation_or_the_git_metadata():
    """Every card that writes a ref review runs as an archetype whose workspace is read-only in its sandbox, so its
    observation and the shared git metadata are bound read-only (the layout itself is per archetype:
    ``tests/unit/test_containment_layout.py``; a contained `git diff` and a refused `update-ref`:
    ``tests/integration/test_containment.py``)."""
    from aew.harness.containment import layout as L

    reviewers = [c for c in roles.builtin_cards().values() if E.REF_REVIEW in (c.meta.get("outputs") or [])]
    assert [c.id for c in reviewers] == [E.REF_REVIEW_CARD]
    assert all(L.WORKSPACE_ACCESS[c.archetype] == "read" for c in reviewers)


def test_a_ref_review_whose_reviewed_commit_was_pruned_is_unknown_and_never_gates(project, tmp_path):
    """Review of #661, M2: the ref is rewritten after the review is accepted, and gc drops the reviewed commit. Its
    freshness says so (``pruned``) and the gate, the Ticket's reads and a consumer's dispatch all go on."""
    root = project.root
    wid = ref_ticket(project, tmp_path)
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    project.lead("work", "transition", wid, "--to", "RUNNING")
    role = Role(project, out["invocation_token"], Path(out["observation"]["path"]))
    sealed = role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")["evidence"]
    project.lead("evidence", "ingest", wid, "--evidence", sealed)
    project.lead("work", "accept", wid)
    reviewed = out["execution"]["ref_pin"]["commit"]
    where = root.parent / "wt-feature-x"
    git("reset", "-q", "--hard", "main", cwd=where)
    commit_on(project, "feature/x", "calc/other.py", "other = 1\n")
    git("worktree", "prune", cwd=root)
    git("reflog", "expire", "--expire-unreachable=now", "--all", cwd=root)
    git("gc", "-q", "--prune=now", cwd=root)
    assert subprocess.run(["git", "cat-file", "-e", f"{reviewed}^{{commit}}"], cwd=root).returncode != 0
    fresh = F.record_freshness(root, record({"name": "refs/heads/feature/x", "commit": reviewed}), None)
    assert (fresh["status"], fresh["moved"], fresh["detail"]) == (F.UNKNOWN, F.PRUNED, F.REF_MOVED)
    gate = project.ok("gate", "show", wid)["gates"]["execute_record"]
    assert gate["status"] == "CURRENT" and gate["freshness"]["moved"] == F.PRUNED
    assert project.ok("work", "show", wid)["control"]["state"] == "DONE"
    consumer = create_unit(project, "ticket", "Act on the review", cls=1,
                           extra=("--non-mutating", "--goal", "g", "--depends-on", f"{wid}:evidence"))
    plan_unit(project, tmp_path, consumer, "Read the review.\n")
    engine(project).work_dispatch(token=project.token, work_id=consumer)
    assert_control_invariants(project)


def test_a_reviewer_of_a_ref_review_checks_out_with_the_ref_reviews_env(project, tmp_path, monkeypatch):
    """Review of #661, m2: a reviewer's observation of the pinned commit is checked out as its executor's was."""
    wid = ref_ticket(project, tmp_path)
    project.lead("work", "staff", wid, "--review", "code_reviewer")
    out = engine(project).work_dispatch(token=project.token, work_id=wid)
    project.lead("work", "transition", wid, "--to", "RUNNING")
    role = Role(project, out["invocation_token"], Path(out["observation"]["path"]))
    project.lead("evidence", "ingest", wid, "--evidence", role.submit(E.REF_REVIEW, REVIEW, "Reviewed.\n")["evidence"])
    project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    seen: list[dict[str, str] | None] = []
    real = worktrees.allocate_detached

    def recorded(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs.get("env"))
        return real(**kwargs)

    monkeypatch.setattr(worktrees, "allocate_detached", recorded)
    reviewer = engine(project).invoke_create(token=project.token, work_id=wid, role="reviewer", card=None,
                                             scope="ticket")
    assert seen == [R.CHECKOUT_ENV] and reviewer["observation"]["commit"] == out["execution"]["ref_pin"]["commit"]
    assert_control_invariants(project)
