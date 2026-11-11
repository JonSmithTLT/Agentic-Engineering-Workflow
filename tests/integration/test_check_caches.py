"""E334 cache policy through checks, gates, guardrails and the Ticket commit."""

from pathlib import Path

import pytest
from aewflow import assign, create_planned_ticket, integrate, sample_project, to_commit_ready
from conftest import make_git_repo

from aew.errors import ValidationFailed
from aew.policy.checks import definition_digest
from aew.snapshot import fingerprint as F
from aew.util import dump_yaml, load_yaml
from aew.workspace import git, integration

CACHES = (".build-cache/",)
CACHE = ".build-cache/result.bin"
WRITE_CACHE = f"from pathlib import Path; p=Path({CACHE!r}); p.parent.mkdir(exist_ok=True); p.write_text('cached')"


def check(code="pass", caches=None):
    cfg = {"configured": True, "command": ["{python}", "-c", code]}
    if caches is not None:
        cfg["caches"] = list(caches)
    return cfg


def project(tmp_path, **checks):
    return sample_project(tmp_path, checks={"schema": "aew/checks/v1", "checks": checks})


def test_a_check_writing_only_its_declared_caches_passes_and_stays_current(tmp_path):
    p = project(tmp_path, unit=check(WRITE_CACHE, CACHES))
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    assert impl.check("unit")["result"] == "pass"
    assert (impl.workspace / CACHE).read_text() == "cached"
    gate = p.ok("gate", "show", wid)
    (impl.workspace / CACHE).write_text("new cache content", encoding="utf-8", newline="\n")
    after = p.ok("gate", "show", wid)
    assert gate["snapshot"] == after["snapshot"]
    assert "local_checks" not in after["unmet"]


def test_a_check_writing_outside_its_caches_is_inconclusive(tmp_path):
    code = WRITE_CACHE + "; Path('new-source.py').write_text('value = 1')"
    p = project(tmp_path, unit=check(code, CACHES))
    impl = assign(p, create_planned_ticket(p, tmp_path))
    out = impl.check("unit")
    assert out["result"] == "inconclusive"
    assert out["changed_paths"] == ["new-source.py"]


def test_a_tracked_file_matching_a_cache_pattern_still_counts(tmp_path):
    p = project(tmp_path, unit=check(WRITE_CACHE, CACHES))
    impl = assign(p, create_planned_ticket(p, tmp_path))
    path = impl.workspace / CACHE
    path.parent.mkdir()
    path.write_text("staged", encoding="utf-8", newline="\n")
    git.git("add", "--", CACHE, cwd=impl.workspace)
    out = impl.check("unit")
    assert out["result"] == "inconclusive"
    assert out["changed_paths"] == [CACHE]
    assert "caches:" not in out["message"]


def test_one_checks_caches_do_not_stale_another_checks_evidence(tmp_path):
    p = project(tmp_path, unit=check(), cache_writer=check(WRITE_CACHE, CACHES))
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    assert impl.check("unit")["result"] == "pass"
    assert not (impl.workspace / CACHE).exists()
    before = p.ok("gate", "show", wid)
    assert impl.check("cache_writer")["result"] == "pass"
    assert (impl.workspace / CACHE).is_file()
    after = p.ok("gate", "show", wid)
    assert before["snapshot"] == after["snapshot"]
    assert "local_checks" not in after["unmet"]


def test_a_ticket_commit_leaves_declared_caches_out_and_integrates(tmp_path):
    p = project(tmp_path, unit=check(WRITE_CACHE, CACHES))
    wid, impl = to_commit_ready(p, tmp_path, scope=("calc/**", "tests/**", ".build-cache/**"))
    assert (impl.workspace / CACHE).is_file()
    out = integrate(p, wid)
    assert git.git("cat-file", "-e", f"{out['integrated_commit']}:{CACHE}", cwd=p.root, check=False).returncode != 0
    log = git.out("log", "--format=%B", out["integrated_commit"], cwd=p.root)
    assert "Excluded 1 declared cache path(s)." in log


def test_guardrails_scope_ignores_declared_caches(tmp_path):
    p = project(tmp_path, unit=check(WRITE_CACHE, CACHES))
    impl = assign(p, create_planned_ticket(p, tmp_path, scope=("calc/**",)))
    assert impl.check("unit")["result"] == "pass"
    assert (impl.workspace / CACHE).exists()
    assert impl.check("guardrails")["result"] == "pass"


@pytest.mark.parametrize(("pattern", "reason"), [
    ("*", "probe"), ("**", "probe"), ("*.py", "probe"), ("a/b.py", "probe"), ("calc/", "tracked path"),
    ("[c]alc/**", "tracked path"), ("/absolute", "invalid"), ("C:/absolute", "invalid"),
    ("cache/../escape", "invalid"),
])
def test_a_cache_pattern_matching_a_probe_or_tracked_path_is_refused(tmp_path, pattern, reason):
    p = project(tmp_path, unit=check())
    path = p.root / ".aew/policy/checks.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    policy["checks"]["unit"]["caches"] = [pattern]
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    rev = p.rev()
    with pytest.raises(ValidationFailed, match=reason):
        p.adopt_policy()
    assert p.rev() == rev


def test_caches_join_the_definition_digest_only_when_present():
    cfg = check()
    assert definition_digest(cfg) == definition_digest({**cfg, "description": "Operational prose"})
    assert definition_digest(cfg) != definition_digest({**cfg, "caches": []})
    assert definition_digest(cfg) != definition_digest({**cfg, "caches": list(CACHES)})


def test_include_ignored_wins_over_a_cache_match(tmp_path):
    repo = make_git_repo(tmp_path / "repo", {"tracked.txt": "base\n"})
    before = F.relevant_inputs_fingerprint(repo, cache_patterns=(CACHES,), include_ignored=[CACHE])
    path = Path(repo) / CACHE
    path.parent.mkdir()
    path.write_text("included", encoding="utf-8", newline="\n")
    assert before != F.relevant_inputs_fingerprint(repo, cache_patterns=(CACHES,), include_ignored=[CACHE])
    assert CACHE not in F.untracked_caches(repo, (CACHES,), [CACHE])



def test_cache_only_commit_and_existing_git_ignores(tmp_path):
    repo = make_git_repo(tmp_path / "repo", {"tracked.txt": "base\n", ".gitignore": ".build-cache/ignored\n"})
    head = git.out("rev-parse", "HEAD", cwd=repo)
    path = repo / CACHE
    path.parent.mkdir()
    path.write_text("cache", encoding="utf-8", newline="\n")
    ignored = ".build-cache/ignored"
    (repo / ignored).write_text("explicit snapshot input", encoding="utf-8", newline="\n")
    options = {"cache_patterns": (CACHES,), "include_ignored": [ignored]}
    assert F.untracked_caches(repo, (CACHES,), [ignored]) == [CACHE]
    assert F.changed_paths(repo, head, stores=False, **options) == []
    assert F.changed_paths(repo, head, stores=True, **options) == []
    assert integration.commit_workspace(repo, "cache only", **options) == head
    assert F.relevant_inputs_fingerprint(repo, **options) != f"git-tree:{F.head_tree_id(repo)}"
