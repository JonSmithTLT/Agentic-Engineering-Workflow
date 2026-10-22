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
    repo, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    return C.for_run(role=role, scope=scope, workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=policy, home=home if home is not None else str(tmp_path / "home"),
                     project=str(repo))


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


# ---------------------------------------------------------------------------------------------- STG-05 CB-07, CBF-1


def test_binds_are_applied_ancestors_first_and_a_path_in_both_is_read_only():
    order = L.bind_order(["/a", "/a/b/c"], ["/a/b", "/x", "/a"])
    assert order == [("--bind", "/a"), ("--ro-bind", "/x"), ("--ro-bind", "/a"),  # depth 1, the re-bind of /a last
                     ("--ro-bind", "/a/b"),                                         # read-only under the writable /a
                     ("--bind", "/a/b/c")]                                          # writable again under the re-bind
    layout = C.Layout(role="implementer", access="write", bwrap="/usr/bin/bwrap", writable=("/a", "/a/b/c"),
                      readonly=("/a/b", "/x", "/a"))
    flags = C.bwrap_argv(layout, ["agent"])
    binds = [(f, flags[i + 1]) for i, f in enumerate(flags) if f in ("--bind", "--ro-bind") and flags[i + 1] != "/"]
    assert binds == order  # the argv is the one order, not a second statement of it


def project_layout(tmp_path: Path, role: str, *, workspace: Path | None = None, run_dir: Path | None = None,
                   scratch: Path | None = None) -> C.Layout:
    """A role's layout in a project with a store and a `.aew/local`, its run directory where a harness run's is."""
    repo, ws = repo_with_worktree(tmp_path)
    for d in (".aew/state/log", ".aew/local/harness/runs"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    run = run_dir or repo / ".aew/local/harness/runs/R-1"
    return C.for_run(role=role, scope="ticket", workspace=str(workspace or ws), run_dir=run,
                     scratch=str(scratch or run / "scratch"), bridge_dir=None, policy=None,
                     home=str(tmp_path / "home"), project=str(repo), runs=str(run.parent))


@pytest.mark.parametrize("role", sorted(L.WORKSPACE_ACCESS))
def test_every_roles_layout_keeps_its_writable_binds_off_the_stores_path_and_the_control_lock_out(tmp_path, role,
                                                                                                    fake_bwrap):
    layout = project_layout(tmp_path, role)
    repo = os.path.realpath(tmp_path / "repo")
    store = os.path.join(repo, ".aew", "state")
    described = layout.describe()
    # The check itself, over what the run records of its layout: a role added later is checked the same way.
    L._refuse_store_binds(role, store, L.bind_order(described["writable"], described["readonly"]))
    assert not any(L._within(w, store) or L._within(store, w) for w in layout.writable)
    # .aew/local is hidden whole (the runs directory is inside it, so it is not hidden twice), before any bind.
    local = os.path.join(repo, ".aew", "local")
    assert layout.hide_runs == (local,)
    flags = C.bwrap_argv(layout, ["agent"])
    hidden = next(i for i in range(len(flags) - 1) if flags[i:i + 2] == ["--tmpfs", local])
    assert all(hidden < i for i, f in enumerate(flags) if f == "--bind")
    assert os.path.realpath(tmp_path / "repo/.aew/local/harness/runs/R-1/harness") in layout.writable  # bound back


def test_a_layout_whose_writable_bind_reaches_the_store_is_refused_naming_the_bind(tmp_path, fake_bwrap):
    repo = tmp_path / "repo"
    # The implementer's workspace is the project root itself, with no read-only re-bind of `.aew` after it.
    with pytest.raises(ContainmentUnavailable, match="contains AEW's store") as root:
        project_layout(tmp_path / "a", "implementer", workspace=tmp_path / "a" / "repo")
    assert root.value.details["reason"] == "store_path_writable"
    assert root.value.details["needs"] == os.path.join(os.path.realpath(tmp_path / "a" / "repo"), ".aew")
    # A reader whose scratch is `.aew`: `.aew/state` would have to be re-bound read-only after it.
    with pytest.raises(ContainmentUnavailable, match="contains AEW's store") as scratch:
        project_layout(tmp_path / "b", "reviewer", scratch=tmp_path / "b" / "repo" / ".aew")
    assert scratch.value.details["needs"] == os.path.join(os.path.realpath(tmp_path / "b" / "repo"), ".aew", "state")
    # A run whose harness directory is under the store.
    with pytest.raises(ContainmentUnavailable, match="lies under it") as inside:
        project_layout(tmp_path / "c", "investigator", run_dir=tmp_path / "c" / "repo" / ".aew" / "state" / "R-1")
    assert inside.value.details["reason"] == "writable_bind_in_store"
    assert not repo.exists()  # each case built its own project


def test_a_writable_bind_that_contains_the_store_passes_only_with_the_next_directory_re_bound_after_it():
    store = os.path.join(os.sep, "p", ".aew", "state")
    work, aew = os.path.join(os.sep, "p"), os.path.join(os.sep, "p", ".aew")
    L._refuse_store_binds("lead", store, L.bind_order([work], [aew]))  # R-2: the Lead's writable working tree
    with pytest.raises(ContainmentUnavailable):  # the same re-bind applied before the writable bind covers nothing
        L._refuse_store_binds("lead", store, [("--ro-bind", aew), ("--bind", work)])
    with pytest.raises(ContainmentUnavailable):  # a deeper re-bind is not the next directory on the path
        L._refuse_store_binds("lead", store, L.bind_order([work], [store]))


def test_a_run_without_its_project_is_refused_before_any_layout(tmp_path, monkeypatch, fake_bwrap):
    monkeypatch.setattr(C, "supported", lambda: True)
    with pytest.raises(ContainmentUnavailable, match="needs its project root"):
        C.establish(role="reviewer", scope="ticket", workspace=str(tmp_path), run_dir=tmp_path / "run",
                    scratch=str(tmp_path / "s"), bridge_dir=None, policy={"containment": {"mode": "required"}})
    assert not (tmp_path / "run").exists()
