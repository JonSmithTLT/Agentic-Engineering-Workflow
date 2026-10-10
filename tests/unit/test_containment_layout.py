"""The sandbox layout as data (M4-B): argv order, the exhaustive role map, secret masks by type, labels.

Pure: nothing here starts bubblewrap, so it runs on every platform. Linux behaviour is in
tests/integration/test_containment.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import layout as L


@pytest.fixture
def fake_bwrap(monkeypatch):
    monkeypatch.setattr(L, "find_bwrap", lambda: "/usr/bin/bwrap")


def repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    for args in (["init", "-q"], ["commit", "-q", "--allow-empty", "-m", "base"],
                 ["worktree", "add", "-q", "-b", "w", str(tmp_path / "ws")]):
        subprocess.run(["git", *args], cwd=repo, check=True, env=env, capture_output=True)
    return repo, tmp_path / "ws"


def run_layout(tmp_path: Path, role: str, *, scope: str = "ticket", policy: dict | None = None,
               home: str | None = None) -> C.Layout:
    _, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    return C.for_run(role=role, scope=scope, workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=policy, home=home if home is not None else str(tmp_path / "home"))


def test_argv_binds_the_root_read_only_first_then_writable_roots_then_read_only_rebinds_then_masks():
    layout = C.Layout(role="implementer", access="write", bwrap="/usr/bin/bwrap", writable=("/w1", "/w2"),
                      readonly=("/r1",), hide_dirs=("/home/u/.ssh",), hide_files=("/home/u/.netrc",))
    argv = C.bwrap_argv(layout, ["agent", "--x"], cwd="/w1")
    assert argv[0] == "/usr/bin/bwrap"
    assert argv[argv.index("--"):] == ["--", "agent", "--x"]
    flags = argv[:argv.index("--")]
    for f in ("--die-with-parent", "--unshare-pid", "--unshare-ipc", "--unshare-uts"):
        assert f in flags
    assert "--unshare-net" not in flags and "--unshare-all" not in flags  # the network stays shared (by design)
    pos = {name: i for i, name in enumerate(flags)}

    def at(*seq: str) -> int:
        n = len(seq)
        return next(i for i in range(len(flags) - n + 1) if tuple(flags[i:i + n]) == seq)

    root = at("--ro-bind", "/", "/")
    tmp = at("--tmpfs", "/tmp")
    w1, w2 = at("--bind", "/w1", "/w1"), at("--bind", "/w2", "/w2")
    r1 = at("--ro-bind", "/r1", "/r1")
    ssh = at("--tmpfs", "/home/u/.ssh")
    netrc = at("--ro-bind", "/dev/null", "/home/u/.netrc")
    assert root < tmp < w1 < w2 < r1 < ssh < netrc  # a later bind wins: protection always comes last
    assert flags[pos["--chdir"] + 1] == "/w1"


def test_every_archetype_but_the_lead_has_a_layout_and_an_unknown_role_has_none(tmp_path, fake_bwrap):
    from aew.roles import ARCHETYPES

    assert set(L.WORKSPACE_ACCESS) == set(ARCHETYPES) - {"lead"}  # exhaustive: a new archetype must be classified
    with pytest.raises(ContainmentUnavailable, match="no containment layout"):
        run_layout(tmp_path, "lead")
    with pytest.raises(ContainmentUnavailable, match="no containment layout"):
        run_layout(tmp_path / "x", "mystery")


def test_write_access_exists_only_for_a_ticket_scope(tmp_path, fake_bwrap):
    with pytest.raises(ContainmentUnavailable, match="only a Ticket workspace"):
        run_layout(tmp_path, "implementer", scope="integration")


def test_missing_bubblewrap_is_containment_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "find_bwrap", lambda: None)
    with pytest.raises(ContainmentUnavailable, match="bubblewrap"):
        run_layout(tmp_path, "reviewer")


def test_an_implementer_writes_its_source_and_private_git_but_never_the_real_git_metadata(tmp_path, fake_bwrap):
    layout = run_layout(tmp_path, "implementer")
    ws = os.path.realpath(tmp_path / "ws")
    common = os.path.realpath(tmp_path / "repo" / ".git")
    assert layout.access == "write" and layout.writable[0] == ws
    assert os.path.realpath(tmp_path / "run" / "git") in layout.writable
    assert common in layout.readonly                                  # objects, refs, worktrees/<id>/ (HEAD, index)
    assert os.path.realpath(Path(ws) / ".git") in layout.readonly       # the pointer file, re-bound over the source
    assert not any(p == common or p.startswith(common + os.sep) for p in layout.writable)
    assert str(Path(ws) / ".git") in layout.protected
    assert any(p.endswith(os.path.join("worktrees", "ws", "HEAD")) for p in layout.protected)
    # The agent's git uses a private index (seeded from the real one) and object store, reading the real objects.
    assert Path(layout.env["GIT_INDEX_FILE"]).read_bytes() == (Path(common) / "worktrees" / "ws" / "index").read_bytes()
    assert Path(layout.env["GIT_OBJECT_DIRECTORY"]).is_dir()
    assert layout.env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] == str(Path(common) / "objects")
    C.retire_private_git(tmp_path / "run")
    assert not (tmp_path / "run" / "git").exists()


def test_a_reader_writes_only_scratch_and_harness_state(tmp_path, fake_bwrap):
    layout = run_layout(tmp_path, "reviewer")
    ws = os.path.realpath(tmp_path / "ws")
    assert layout.access == "read"
    assert ws not in layout.writable and layout.readonly[0] == ws and ws in layout.protected
    assert set(layout.writable) == {os.path.realpath(tmp_path / "run" / "scratch"),
                                    os.path.realpath(tmp_path / "run" / "harness")}
    assert layout.env["PYTHONDONTWRITEBYTECODE"] == "1" and "GIT_INDEX_FILE" not in layout.env
    assert not (tmp_path / "run" / "git").exists()


def test_secrets_are_masked_by_type_and_only_when_present(tmp_path, fake_bwrap):
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".netrc").write_text("machine x login y password z")
    (home / ".config" / "gh").mkdir(parents=True)
    (tmp_path / "extra-secret").write_text("s")
    layout = run_layout(tmp_path, "reviewer", home=str(home), policy={"hide": [str(tmp_path / "extra-secret")]})
    real = os.path.realpath
    assert set(layout.hide_dirs) == {real(home / ".ssh"), real(home / ".config" / "gh")}
    assert set(layout.hide_files) == {real(home / ".netrc"), real(tmp_path / "extra-secret")}  # /dev/null, not tmpfs


@pytest.mark.parametrize(("rel", "kind"), [(".claude.json", "file"), (".config/anthropic", "dir")])
def test_a_provider_config_location_is_masked_by_its_type_when_present_and_skipped_when_absent(tmp_path, fake_bwrap,
                                                                                            rel, kind):
    assert rel in (L.SECRET_FILES if kind == "file" else L.SECRET_DIRS)
    home = tmp_path / "home"
    home.mkdir()
    absent = run_layout(tmp_path / "a", "reviewer", home=str(home))
    assert not any(p.endswith(os.path.normpath(rel)) for p in (*absent.hide_dirs, *absent.hide_files))
    path = home / rel
    if kind == "file":
        path.write_text('{"k": "v"}')
    else:
        path.mkdir(parents=True)
        (path / "credentials").write_text("v")
    layout = run_layout(tmp_path / "b", "reviewer", home=str(home))
    real = os.path.realpath(path)
    flags = C.bwrap_argv(layout, ["true"])
    if kind == "file":
        assert real in layout.hide_files and real not in layout.hide_dirs
        i = flags.index(real)
        assert flags[i - 2:i] == ["--ro-bind", layout.mask_file]       # an empty read-only file, still a file
    else:
        assert real in layout.hide_dirs and real not in layout.hide_files
        assert flags[flags.index(real) - 1] == "--tmpfs"                # an empty directory


def test_a_suffixed_copy_of_a_provider_config_file_is_masked_as_a_file_and_only_a_regular_file(tmp_path, fake_bwrap):
    assert ".claude.json." in L.SECRET_FILE_PREFIXES
    home = tmp_path / "home"
    home.mkdir()
    absent = run_layout(tmp_path / "a", "reviewer", home=str(home))
    assert not any(".claude.json" in os.path.basename(p) for p in (*absent.hide_dirs, *absent.hide_files))
    (home / ".claude.json.backup").write_text('{"k": "v"}')
    (home / ".claude.json.d").mkdir()                    # a directory with a matching name is not a file
    (home / ".claude.json.d" / ".claude.json.inner").write_text("v")  # and the listing is not recursive
    (home / "x.claude.json.backup").write_text("v")     # a prefix, not a substring
    layout = run_layout(tmp_path / "b", "reviewer", home=str(home))
    real = os.path.realpath
    backup = real(home / ".claude.json.backup")
    assert backup in layout.hide_files and backup not in layout.hide_dirs
    assert real(home / ".claude.json.d") not in (*layout.hide_files, *layout.hide_dirs)
    assert not any(p.endswith(("inner", "x.claude.json.backup")) for p in layout.hide_files)
    flags = C.bwrap_argv(layout, ["true"])
    i = flags.index(backup)
    assert flags[i - 2:i] == ["--ro-bind", layout.mask_file]


def test_operator_writable_roots_must_exist_and_are_recorded(tmp_path, fake_bwrap):
    shared = tmp_path / "cache"
    shared.mkdir()
    layout = run_layout(tmp_path, "reviewer", policy={"writable": [str(shared)]})
    assert layout.operator_writable == (os.path.realpath(shared),)
    assert os.path.realpath(shared) in layout.writable
    assert layout.describe()["operator_writable"] == [os.path.realpath(shared)]
    with pytest.raises(ContainmentUnavailable, match="not an existing directory"):
        run_layout(tmp_path / "y", "reviewer", policy={"writable": [str(tmp_path / "missing")]})


def test_labels_say_what_a_run_had_and_old_records_read_as_workdir_only():
    contained = C.label(contained=True, mechanism="bubblewrap 0.4.0", self_test={"ok": True})
    assert contained == {"filesystem": "os_readonly_roots", "process_ownership": "pid_namespace",
                         "network": C.network(), "mechanism": "bubblewrap 0.4.0", "self_test": {"ok": True}}
    assert C.network() == ("not_provided" if sys.platform == "win32" else "shared")
    weaker = C.label(contained=False, reason="bwrap missing")
    assert weaker["filesystem"] == "workdir_separation_only" and weaker["weaker_because"] == "bwrap missing"
    assert weaker["process_ownership"] in {"job_object", "process_group"} and weaker["network"] == C.network()
    for old in ("workdir_separation_only", None, {}):
        assert C.normalize(old)["filesystem"] == "workdir_separation_only"
    assert C.normalize(contained) is contained


def test_policy_mode_defaults_to_required_where_containment_exists():
    if C.supported():
        assert C.mode(None) == C.mode({}) == "required"
        assert C.mode({"containment": {"mode": "allow_weaker"}}) == "allow_weaker"
    else:  # nothing can be required where nothing can contain: the label says what runs have
        assert C.mode({"containment": {"mode": "required"}}) == "allow_weaker"


def test_an_explicit_required_mode_refuses_on_a_platform_without_containment(monkeypatch, tmp_path):
    """M4-B review: on a POSIX platform other than Linux, `required` is honoured by refusing, never silently weakened;
    Windows stays labelled workdir_separation_only (ADR-0009)."""
    monkeypatch.setattr(C, "supported", lambda: False)
    required = {"containment": {"mode": "required"}}
    args = dict(role="implementer", scope="ticket", workspace=str(tmp_path), run_dir=tmp_path / "run",
                scratch=str(tmp_path / "s"), bridge_dir=None)
    monkeypatch.setattr(C.sys, "platform", "darwin")
    assert C.mode(required) == "required" and C.mode(None) == "allow_weaker"
    with pytest.raises(ContainmentUnavailable, match="containment.mode: allow_weaker"):
        C.establish(**args, policy=required)
    assert C.establish(**args, policy=None)[0] is None
    assert C.doctor(required, "note")[0] == "FAIL"
    monkeypatch.setattr(C.sys, "platform", "win32")
    assert C.mode(required) == "allow_weaker" and C.establish(**args, policy=required)[0] is None


def test_a_tree_that_requires_a_layout_refuses_to_spawn_without_one():
    tree = procs.ProcessTree(require_layout=True)
    with pytest.raises(ContainmentUnavailable, match="requires filesystem containment"):
        tree.spawn(["python", "-c", "pass"])
    assert tree.pids == []


def test_host_pid_of_a_process_in_no_namespace_is_itself():
    assert procs.host_pid(os.getpid()) == os.getpid()
