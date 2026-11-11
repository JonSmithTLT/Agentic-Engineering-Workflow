"""The structural map is refreshed at use (register E62 with E184; ADR-0015, amended 2026-11-11).

A Lead's dispatch whose selected map is STALE, or absent, against the work's base uses the base's map, found stored or
made first, under the dispatching Lead's own credential, bounded by ``service.REFRESH_S``; at the authoritative head
it selects it. Its outcome is a line inside the slice the pack pins. Nothing else writes a map: every pack is built in
a Lead's transaction, a regenerated pack uses the map as it is, and a refresh that fails or runs out of time never
fails the pack."""

from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aewflow import create_investigation, dispatch, sample_project
from conftest import Project
from test_map_context import advance_main, invocations, pack_text, regenerate, select_map, switch_on

from aew.maps import gitobjects, service, slices, store
from aew.workspace import git as gitmod

LEAD = {"kind": "lead", "session_label": "lead-a", "generation": 1, "token_id": "LT-test"}
REFRESHED = "refresh at dispatch: this map was made for the work's base"
FOUND = "refresh at dispatch: this map was found stored for the work's base"


def aew_root(p: Project) -> Path:
    return p.root / ".aew"


def selected_sha(p: Project) -> str | None:
    registry = store.read_registry(aew_root(p)) or {}
    return ((registry.get("selected") or {}).get("structural") or {}).get("sha256")


def artifacts(p: Project) -> set[str]:
    return {f.name for f in (aew_root(p) / store.MAPS_REL).rglob("*.json") if f.name != "registry.json"}


def log_lines(p: Project) -> list[str]:
    path = aew_root(p) / store.LOG_REL
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def counted_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    made: list[str] = []
    real = service.build

    def build(repo: Path, commit: str, **kw: Any) -> dict[str, Any]:
        made.append(commit)
        return real(repo, commit, **kw)

    monkeypatch.setattr(service, "build", build)
    return made


# ------------------------------------------------------------------------------------------- through the CLI


def test_a_lead_dispatch_at_a_stale_head_refreshes_and_selects_the_heads_map_once(tmp_path):
    p = sample_project(tmp_path)
    switch_on(p)
    first = select_map(p)
    head = advance_main(p, "moved.txt")
    _, out = dispatch(p, create_investigation(p, tmp_path, title="After the move"))
    inv = out["invocation"]
    entry = slices.pinned(invocations(p)[inv]["pack"]["sources"])
    assert entry["sha256"] != first["root"] and entry["source_revision"] == head
    assert entry["freshness"]["status"] == "CURRENT" and selected_sha(p) == entry["sha256"]
    text = pack_text(p, inv)
    assert REFRESHED in text and "and is now the selected map" in text
    assert regenerate(p, inv)["matches_recorded"]  # the refresh line is pinned with the slice
    logged = log_lines(p)
    assert '"by":"dispatch_refresh"' in logged[-1] and '"kind":"lead"' in logged[-1]
    # A second dispatch at the same base finds the map CURRENT: nothing is generated or selected again.
    _, again = dispatch(p, create_investigation(p, tmp_path, title="Same base"))
    second = slices.pinned(invocations(p)[again["invocation"]]["pack"]["sources"])
    assert second["sha256"] == entry["sha256"] and "refresh" not in second
    assert "refresh at dispatch" not in pack_text(p, again["invocation"]) and log_lines(p) == logged


def test_a_base_that_is_not_the_head_is_made_once_across_processes_and_found_stored_after(tmp_path):
    """E184 review MAJ-1: a Ticket's reviewer and verifier are dispatched at its workspace base H1 after main moved on
    to H2, so the selected map (H2's) is STALE there and H1's is never selected. Each `aew` command is its own process:
    the reviewer's dispatch makes H1's map, and the verifier's finds it stored instead of making it again."""
    from aewflow import assign, create_planned_ticket, implement, review, verify

    p = sample_project(tmp_path)
    switch_on(p)
    select_map(p)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    h1 = p.ok("work", "show", wid)["control"]["workspace"]["base_commit"]
    h2 = advance_main(p, "landed-meanwhile.txt")  # another Ticket's integration, or a commit made outside AEW
    dispatch(p, create_investigation(p, tmp_path, title="At the new head"))  # refreshes and selects H2's map
    for f in (aew_root(p) / store.STRUCTURAL_REL).iterdir():  # only H2's map is stored, so H1's must be made
        if f.name[:-5] != selected_sha(p):
            f.unlink()
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    entries = {inv["role"]: slices.pinned((inv.get("pack") or {}).get("sources")) for inv in invocations(p).values()
               if inv["work_unit"] == wid and inv["role"] in {"reviewer", "verifier"}}
    reviewer, verifier = entries["reviewer"], entries["verifier"]
    assert h1 != h2 and reviewer["source_revision"] == verifier["source_revision"] == h1
    assert reviewer["refresh"].startswith(REFRESHED) and "stored and not selected" in reviewer["refresh"]
    assert verifier["refresh"].startswith(FOUND) and verifier["sha256"] == reviewer["sha256"]
    assert reviewer["freshness"]["status"] == verifier["freshness"]["status"] == "CURRENT"
    assert store.read_registry(aew_root(p))["selected"]["structural"]["source_revision"] == h2


# ------------------------------------------------------------------------------------------- in process


def test_a_base_that_is_not_the_head_is_stored_and_pinned_never_selected_and_made_once(tmp_path, monkeypatch):
    """The project's selection never moves back to an older commit, and two bases never trade it. A base's map is
    made once: the next pack at it finds it stored (``store.find_structural``), in this process or another."""
    p = sample_project(tmp_path)
    old = select_map(p)
    head = advance_main(p, "moved.txt")
    at_head = select_map(p)
    (aew_root(p) / store.artifact_rel(old["root"])).unlink()  # the old base's map is not stored yet
    made = counted_builds(monkeypatch)
    before = log_lines(p)
    entry, lines = slices.pin(aew_root(p), p.root, old["source_revision"], [], lead=LEAD, head=head)
    assert entry["sha256"] == old["root"]  # deterministic: the old commit's map, made again
    assert entry["freshness"]["status"] == "CURRENT" and "stored and not selected" in entry["refresh"]
    assert entry["refresh"].startswith(REFRESHED)
    assert selected_sha(p) == at_head["root"] and log_lines(p) == before
    again, _ = slices.pin(aew_root(p), p.root, old["source_revision"], [], lead=LEAD, head=head)
    assert again["sha256"] == old["root"] and again["refresh"].startswith(FOUND)
    assert made == [old["source_revision"]]  # made once, then found stored
    assert slices.lines(aew_root(p), p.root, entry, []) == lines


def test_a_stored_map_is_used_only_for_its_own_commit_and_generator_and_only_if_it_verifies(tmp_path):
    """``find_structural`` matches a stored artifact on its source revision and generator identity, then reads it
    strictly: another commit's map, another generator's, or a damaged file is never returned."""
    p = sample_project(tmp_path)
    old = select_map(p)
    ident = service.identity()
    found = store.find_structural(aew_root(p), source_revision=old["source_revision"], generator=ident)
    assert found is not None and found[0] == old["root"]
    assert store.find_structural(aew_root(p), source_revision="0" * 40, generator=ident) is None
    other = {**ident, "version": int(ident["version"]) + 1}
    assert store.find_structural(aew_root(p), source_revision=old["source_revision"], generator=other) is None
    assert store.find_structural(aew_root(p), source_revision=old["source_revision"], generator=ident,
                                 deadline=time.monotonic() - 1) is None  # past the deadline: nothing read
    path = aew_root(p) / store.artifact_rel(old["root"])
    path.write_bytes(path.read_bytes().replace(b'"directories"', b'"directorieZ"'))  # still matches the two fields
    assert store.find_structural(aew_root(p), source_revision=old["source_revision"], generator=ident) is None


def test_only_a_leads_transaction_refreshes_the_map(tmp_path, monkeypatch):
    """No new writer: a pin with no Lead (a regenerated pack) writes nothing under maps/, and ``build_pack`` passes a
    Lead to the pin only when its transaction's actor is one. Every ``build_pack`` caller runs in a ``lead_txn`` today
    and no custody transaction builds a pack (E184 review NIT-2), so the second half's custodian actor is set by hand:
    it pins the guard for any non-Lead transaction that ever builds one."""
    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    switch_on(p)
    _, out = dispatch(p, create_investigation(p, tmp_path))
    inv = out["invocation"]
    advance_main(p, "moved.txt")
    kept = artifacts(p)
    entry, _ = slices.pin(aew_root(p), p.root, gitmod.out("rev-parse", "HEAD", cwd=p.root), [])
    assert entry["freshness"]["status"] == "STALE" and "refresh" not in entry and artifacts(p) == kept

    engine = Engine.discover(p.root)
    seen: list[Any] = []
    real = slices.pin

    def pin(*a: Any, **kw: Any) -> Any:
        seen.append(kw.get("lead"))
        return real(*a, **kw)

    monkeypatch.setattr(slices, "pin", pin)
    state = engine.store.current()
    for actor in ({"kind": "custodian", "id": "IA-0001"}, LEAD):
        state["invocations"][inv].pop("pack", None)  # as a new invocation's first build (a rebuild keeps its map)
        engine._packs.build_pack(SimpleNamespace(actor=actor, state=state), inv)
    assert seen == [None, LEAD]


def test_a_refresh_past_its_limit_is_one_pinned_line_and_never_fails_the_pack(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    select_map(p)
    head = advance_main(p, "moved.txt")
    kept, before = artifacts(p), log_lines(p)
    monkeypatch.setattr(service, "REFRESH_S", 0.5)
    real = gitobjects.list_tree

    def slow(repo: Path, tree: str, **kw: Any) -> Any:  # a git that answers, slowly, inside the refresh only
        if kw.get("timeout", gitmod.OBJECT_TIMEOUT_S) <= 0.5:
            time.sleep(0.8)
        return real(repo, tree, **kw)

    monkeypatch.setattr(gitobjects, "list_tree", slow)
    entry, lines = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert entry["freshness"]["status"] == "STALE"
    took = re.search(r"not refreshed \(timeout, after ([\d.]+) s of the 0\.5 s allowed\)", entry["refresh"])
    assert took and float(took.group(1)) < 0.5 + 1.0, entry["refresh"]  # one bound on the whole refresh
    assert any(line == entry["refresh"] for line in lines)
    assert artifacts(p) == kept and log_lines(p) == before
    assert slices.lines(aew_root(p), p.root, entry, []) == lines  # a regenerated pack renders the same line


def test_a_failed_refresh_of_an_absent_map_is_pinned_in_its_unavailable_reason(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    for f in (aew_root(p) / store.MAPS_REL).rglob("*"):  # no selection and nothing stored: the map must be made
        if f.is_file():
            f.unlink()
    head = gitmod.out("rev-parse", "HEAD", cwd=p.root)

    def broken(*_a: Any, **_kw: Any) -> Any:
        raise OSError("the commit's objects cannot be read")

    monkeypatch.setattr(service, "build", broken)
    entry, lines = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert entry["unavailable"].startswith("none; refresh at dispatch: not refreshed (OSError")
    assert slices.lines(aew_root(p), p.root, entry, []) == lines


def test_a_selection_that_lands_during_a_refresh_wins_and_the_pack_pins_its_own_map(tmp_path, monkeypatch):
    """The race with `aew map generate --select`, which takes the registry's lock and not the control lock: the
    compare-and-set lets the other selection stand, and this pack pins the map it made, CURRENT for its base."""
    p = sample_project(tmp_path)
    old = select_map(p)
    head = advance_main(p, "moved.txt")
    real = service.build

    def build(repo: Path, commit: str, **kw: Any) -> dict[str, Any]:
        record = real(repo, commit, **kw)
        select_map(p)  # lands between the refresh's read of the registry and its selection
        return record

    monkeypatch.setattr(service, "build", build)
    other = selected_sha(p)
    entry, _ = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert other == old["root"] and selected_sha(p) != old["root"]  # the other selection stands
    assert entry["freshness"]["status"] == "CURRENT" and entry["source_revision"] == head
    assert "another selection landed or held the registry meanwhile" in entry["refresh"]


# ------------------------------------------------------------------------------------------- one bound (MIN-1)


def test_nothing_after_a_refresh_runs_git_so_nothing_there_can_fail_the_pack(tmp_path, monkeypatch):
    """E184 review MIN-1: the map a refresh returns is the base's own, CURRENT there by construction, so ``pin`` asks
    git nothing after it (a freshness call there was outside both the never-raise guard and ``REFRESH_S``)."""
    from aew.maps import freshness as F

    p = sample_project(tmp_path)
    select_map(p)
    head = advance_main(p, "moved.txt")
    done = {"refreshed": False}
    real_refresh, real_fresh = service.refresh_at_dispatch, F.freshness

    def refresh(*a: Any, **kw: Any) -> Any:
        out = real_refresh(*a, **kw)
        done["refreshed"] = True
        return out

    def fresh(*a: Any, **kw: Any) -> Any:
        if done["refreshed"]:
            raise OSError("git could not be started")
        return real_fresh(*a, **kw)

    monkeypatch.setattr(service, "refresh_at_dispatch", refresh)
    monkeypatch.setattr(F, "freshness", fresh)
    entry, _ = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert done["refreshed"] and entry["freshness"]["status"] == "CURRENT" and entry["source_revision"] == head
    assert entry["freshness"]["against_commit"] == head


def test_the_lazy_fetch_check_takes_only_the_time_left_for_both_its_git_calls(tmp_path, monkeypatch):
    """MIN-1: each of its two git processes had the whole time left, so the step alone could take twice it."""
    from aew.errors import GitError

    given: list[float] = []

    def partial(_repo: Path, *, timeout: float = 0.0) -> bool:
        given.append(timeout)
        time.sleep(0.3)
        return True

    def version(_repo: Path, *, timeout: float = 0.0) -> tuple[int, ...]:
        given.append(timeout)
        return (2, 50, 0)

    monkeypatch.setattr(gitobjects.git, "is_partial_clone", partial)
    monkeypatch.setattr(gitobjects.git, "version", version)
    gitobjects.refuse_lazy_fetch(tmp_path, deadline=time.monotonic() + 1.0)
    assert given[0] <= 1.0 and given[1] <= 1.0 - 0.3 + 0.05, given
    with pytest.raises(GitError) as raised:  # the first call used it all: the second never starts
        gitobjects.refuse_lazy_fetch(tmp_path, deadline=time.monotonic() + 0.2)
    assert raised.value.details["reason"] == "timeout"


def test_the_batch_readers_close_waits_only_for_the_time_left(tmp_path, monkeypatch):
    """MIN-1: closing the generation's ``cat-file --batch`` waited up to its own 30 s, past the refresh's bound."""
    p = sample_project(tmp_path)
    head = gitmod.out("rev-parse", "HEAD", cwd=p.root)
    waits: list[float] = []
    real_exit = gitmod.CatFileBatch.__exit__

    def exit_(self: Any, *exc: Any) -> None:
        waits.append(self.close_timeout)
        real_exit(self, *exc)

    monkeypatch.setattr(gitmod.CatFileBatch, "__exit__", exit_)
    with gitobjects.open_tree(p.root, head, deadline=time.monotonic() + 5.0):
        pass
    with gitobjects.open_tree(p.root, head):
        pass
    assert waits[0] <= 5.0 and waits[1] == gitmod.BATCH_CLOSE_TIMEOUT_S


def test_a_busy_registry_lock_is_waited_on_only_for_the_time_left_and_the_pack_keeps_its_map(tmp_path, monkeypatch):
    """MIN-1: the selection's wait for the registry lock (``FileLock``'s 60 s) was outside ``REFRESH_S``. Held past
    the time left, the map is stored and pinned, not selected, and the dispatch goes on."""
    from aew.engine.lock import FileLock

    p = sample_project(tmp_path)
    old = select_map(p)
    head = advance_main(p, "moved.txt")
    monkeypatch.setattr(service, "REFRESH_S", 2.0)
    start = time.monotonic()
    with FileLock(aew_root(p) / store.LOCK_REL):  # `aew map generate --select` holding it, in another process
        entry, _ = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert time.monotonic() - start < 2.0 + 1.0
    assert entry["source_revision"] == head and entry["freshness"]["status"] == "CURRENT"
    assert "stored and not selected" in entry["refresh"] and selected_sha(p) == old["root"]
