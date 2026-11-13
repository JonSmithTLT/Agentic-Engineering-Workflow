"""E334 cache policy through checks, gates, guardrails and the Ticket commit."""

from pathlib import Path

import pytest
from aewflow import assign, create_planned_ticket, integrate, sample_project, to_commit_ready
from conftest import make_git_repo

from aew.errors import ValidationFailed
from aew.policy.checks import definition_digest, validate_caches
from aew.snapshot import fingerprint as F
from aew.util import dump_yaml, load_yaml
from aew.workspace import git, integration

CACHES = (".build-cache/",)
CACHE = ".build-cache/result.bin"
WRITE_CACHE = f"from pathlib import Path; p=Path({CACHE!r}); p.parent.mkdir(exist_ok=True); p.write_text('cached')"
PYC = "calc/__pycache__/core.cpython-311.pyc"
WRITE_PYC = (f"from pathlib import Path; p=Path({PYC!r}); p.parent.mkdir(exist_ok=True); "
             "p.write_bytes(b'cache')")


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
    # The Ticket has a cache at prepare. The integration verifier's workspace is read-only on Linux.
    p = project(tmp_path, unit=check(caches=CACHES))
    wid, impl = to_commit_ready(p, tmp_path, scope=("calc/**", "tests/**", ".build-cache/**"))
    path = impl.workspace / CACHE
    path.parent.mkdir()
    path.write_text("cache at prepare", encoding="utf-8", newline="\n")
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


def test_following_the_printed_cache_hint_makes_the_check_pass_and_stay_current(tmp_path):
    p = project(tmp_path, unit=check(WRITE_PYC), lint=check())
    (p.root / ".gitignore").write_text("", encoding="utf-8")
    git.git("commit", "-qam", "make cache output visible to Git", cwd=p.root, env=git.identity_env(p.root))
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    first = impl.check("unit")
    assert first["result"] == "inconclusive"
    line = first["message"].split("add `", 1)[1].split("`", 1)[0]
    assert line == 'caches: ["__pycache__/", "*.pyc"]'
    assert "make existing evidence STALE" in first["message"]
    assert impl.check("lint")["result"] == "pass"
    before = p.ok("gate", "show", wid)

    path = p.root / ".aew/policy/checks.yaml"
    policy = path.read_text(encoding="utf-8")
    anchor = "  unit:\n"
    assert anchor in policy
    path.write_text(policy.replace(anchor, f"{anchor}    {line}\n", 1), encoding="utf-8", newline="\n")
    p.adopt_policy()
    assert p.ok("gate", "show", wid)["snapshot"] != before["snapshot"]
    assert impl.check("unit")["result"] == "pass"
    assert impl.check("lint")["result"] == "pass"
    after = p.ok("gate", "show", wid)
    (impl.workspace / PYC).write_bytes(b"recompiled")
    assert p.ok("gate", "show", wid)["snapshot"] == after["snapshot"]
    assert "local_checks" not in after["unmet"]


@pytest.mark.parametrize(("pattern", "reason"), [
    ("*", "new project paths"), ("**", "new project paths"), ("*.py", "new project paths"),
    ("a/b.py", "new project paths"), ("calc/", "tracked path"), ("[c]alc/**", "tracked path"),
    ("/build/", "repository-relative"), ("C:/absolute", "repository-relative"),
    ("cache/../escape", "repository-relative"),
])
def test_a_cache_pattern_matching_a_probe_or_tracked_path_is_refused(tmp_path, pattern, reason):
    p = project(tmp_path, unit=check())
    path = p.root / ".aew/policy/checks.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    policy["checks"]["unit"]["caches"] = [pattern]
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    rev = p.rev()
    with pytest.raises(ValidationFailed, match=reason) as refused:
        p.adopt_policy()
    message = str(refused.value)
    assert repr(pattern) in message
    if reason == "repository-relative":
        assert "leading slash, drive, or '..' component" in message
    else:
        assert "Use a narrower pattern" in message
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


def test_include_ignored_keeps_a_cache_named_path_in_changed_paths_and_the_commit(tmp_path):
    repo = make_git_repo(tmp_path / "repo", {"tracked.txt": "base\n"})
    head = git.out("rev-parse", "HEAD", cwd=repo)
    path = repo / CACHE
    path.parent.mkdir()
    path.write_bytes(b"included input")
    path.with_name("other.bin").write_bytes(b"disposable cache")
    options = {"cache_patterns": (CACHES,), "include_ignored": [CACHE]}
    for stores in (False, True):
        assert F.changed_paths(repo, head, stores=stores, **options) == [CACHE]
    new = integration.commit_workspace(repo, "commit the included input", **options)
    assert git.out("diff", "--name-only", head, new, cwd=repo).splitlines() == [CACHE]


def test_reader_and_writer_fingerprints_agree_with_a_declared_cache_present(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo", {"tracked.txt": "base\n"})
    (repo / "source.py").write_bytes(b"value = 1\n")
    monkeypatch.setattr(F, "_stores_objects", lambda: True)
    expected = F.relevant_inputs_fingerprint(repo)
    path = repo / CACHE
    path.parent.mkdir()
    path.write_bytes(b"cache")
    assert F.relevant_inputs_fingerprint(repo, cache_patterns=(CACHES,)) == expected
    monkeypatch.setattr(F, "_stores_objects", lambda: False)
    assert F.relevant_inputs_fingerprint(repo, cache_patterns=(CACHES,)) == expected


def test_ticket_commit_with_many_declared_cache_paths(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo", {"tracked.txt": "base\n"})
    head = git.out("rev-parse", "HEAD", cwd=repo)
    cache_dir = (repo / CACHE).parent
    cache_dir.mkdir()
    # These literal excludes exceed the status command's 8,000-character budget.
    count = 300
    for index in range(count):
        (cache_dir / f"cached-result-{index:03d}.bin").write_bytes(b"cache")
    options = {"cache_patterns": (CACHES,)}
    status_calls = []
    original_out = git.out

    def record_status(*args, **kwargs):
        if args and args[0] == "status":
            status_calls.append(args)
        return original_out(*args, **kwargs)

    monkeypatch.setattr(git, "out", record_status)
    assert integration.commit_workspace(repo, "cache only", **options) == head
    (repo / "source.py").write_bytes(b"value = 1\n")
    new = integration.commit_workspace(repo, "commit source", **options)
    assert git.out("diff", "--name-only", head, new, cwd=repo).splitlines() == ["source.py"]
    assert f"Excluded {count} declared cache path(s)." in git.out("log", "--format=%B", new, cwd=repo)
    assert status_calls == [("status", "--porcelain", "--untracked-files=no", "--", ".", integration.AEW_EXCLUDE)] * 2


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


def test_cache_pattern_matching_uses_the_repositories_case_setting(tmp_path):
    repo = make_git_repo(tmp_path / "repo", {"src/input.txt": "base\n"})
    policy = {"checks": {"unit": check(caches=["SRC/"])}}
    for setting in ("true", "false"):
        git.git("config", "core.ignorecase", setting, cwd=repo)
        if setting == "true":
            with pytest.raises(ValidationFailed, match="tracked path"):
                validate_caches(policy, repo=repo, commit="HEAD", source="checks.yaml")
        else:
            validate_caches(policy, repo=repo, commit="HEAD", source="checks.yaml")
