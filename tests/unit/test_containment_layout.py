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


@pytest.fixture
def tmp_unmasked(monkeypatch):
    """pytest's ``tmp_path`` is under /tmp on Linux, which a sandbox's own /tmp hides whole, so no mask under it is on
    the argv: a test that reads a mask's flags from the argv sees them as it would for a home anywhere else."""
    monkeypatch.setattr(L, "SANDBOX_TMP", "/sandbox-tmp")


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
               home: str | None = None, env: dict[str, str] | None = None) -> C.Layout:
    repo, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    return C.for_run(role=role, scope=scope, workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=policy, home=home if home is not None else str(tmp_path / "home"),
                     project=str(repo), env=env if env is not None else {})


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
                                                                                            tmp_unmasked, rel, kind):
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


def test_a_suffixed_copy_of_a_provider_config_file_is_masked_as_a_file_and_only_a_regular_file(tmp_path, fake_bwrap,
                                                                                            tmp_unmasked):
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
    assert [b for b in L.order(layout) if b[0] != "--tmpfs"] == binds  # the argv is the one order, not a second one
    assert [b for b in binds if b[1] in ("/a", "/a/b", "/a/b/c", "/x")] == order  # (the host's /run exceptions aside)


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
    L._refuse_store_binds(role, repo, L.bind_order(described["writable"], described["readonly"], layout.hide_runs))
    assert not any(L._within(w, store) or L._within(store, w) for w in layout.writable)
    # .aew/local is hidden whole (the runs directory is inside it, so it is not hidden twice), and stays hidden.
    local = os.path.join(repo, ".aew", "local")
    assert layout.hide_runs == (local,)
    assert mask_problems(C.bwrap_argv(layout, ["agent"]), layout.hide_runs) == []
    assert os.path.realpath(tmp_path / "repo/.aew/local/harness/runs/R-1/harness") in layout.writable  # bound back


def mask_problems(flags: list[str], hidden: tuple[str, ...]) -> list[str]:
    """The masked-path invariant (review of #231, m2 and m5), enumerated over the argv: after a mask's ``--tmpfs H``,
    no bind lands on ``H`` or above it (that would show the host's ``H`` again), only deeper bind-backs; and ``H`` is
    remounted read-only after the last of them (a writable mask lets a contained process make its own lock there)."""
    out = []
    kinds = ("--bind", "--ro-bind", "--tmpfs", "--remount-ro")
    steps = [(i, f, flags[i + 1]) for i, f in enumerate(flags) if f in kinds]
    for h in hidden:
        masked = [i for i, f, p in steps if f == "--tmpfs" and p == h]
        remounts = [i for i, f, p in steps if f == "--remount-ro" and p == h]
        if len(masked) != 1 or len(remounts) != 1:
            out.append(f"{h}: masked {len(masked)} times and remounted read-only {len(remounts)} times, not once each")
            continue
        for i, f, p in steps:
            dest = flags[i + 2] if f in ("--bind", "--ro-bind") else p
            if f in ("--bind", "--ro-bind") and i > masked[0] and L._within(h, dest):
                out.append(f"{f} {dest} after the mask of {h} shows the host's {h} again")
            if f in ("--bind", "--ro-bind") and L._within(dest, h) and dest != h and i > remounts[0]:
                out.append(f"{f} {dest} into {h} after its read-only remount")
    return out


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
    work = os.path.realpath(os.path.join(os.sep, "p"))
    aew, store = os.path.join(work, ".aew"), os.path.join(work, ".aew", "state")
    L._refuse_store_binds("lead", work, L.bind_order([work], [aew]))  # R-2: the Lead's writable working tree
    with pytest.raises(ContainmentUnavailable):  # the same re-bind applied before the writable bind covers nothing
        L._refuse_store_binds("lead", work, [("--ro-bind", aew), ("--bind", work)])
    with pytest.raises(ContainmentUnavailable):  # a deeper re-bind is not the next directory on the path
        L._refuse_store_binds("lead", work, L.bind_order([work], [store]))


def test_in_the_leads_r2_shape_the_mask_comes_after_the_aew_re_bind_so_the_lock_stays_hidden():
    """Review of #231, m2, scenario 1: the project writable and `.aew` re-bound read-only after it (what R-3 admits).
    Applied before every bind, the mask was covered again by the `.aew` re-bind, the host's lock with it."""
    work = os.path.realpath(os.path.join(os.sep, "p"))
    aew, local = os.path.join(work, ".aew"), os.path.join(work, ".aew", "local")
    run = os.path.join(local, "harness", "runs", "R-1", "harness")
    layout = C.Layout(role="lead", access="write", bwrap="/usr/bin/bwrap", writable=(work, run), readonly=(aew,),
                      hide_runs=(local,))
    flags = C.bwrap_argv(layout, ["agent"])
    assert mask_problems(flags, layout.hide_runs) == []
    kinds = ("--bind", "--ro-bind", "--tmpfs", "--remount-ro")
    steps = [(f, flags[i + 1]) for i, f in enumerate(flags) if f in kinds
             and not any(L._within(flags[i + 1], h) for h in layout.hide_host)]  # /run's mask: its own tests
    assert steps[-5:] == [("--bind", work), ("--ro-bind", aew), ("--tmpfs", local), ("--bind", run),
                          ("--remount-ro", local)]
    # The old order, the mask before every bind, is what the enumeration exists to catch.
    old = [layout.bwrap, "--tmpfs", local, "--bind", work, work, "--ro-bind", aew, aew, "--bind", run, run]
    assert mask_problems(old, layout.hide_runs) != []


def test_a_layout_of_a_project_whose_aew_is_a_symlink_is_refused_where_a_writable_bind_reaches_the_link(tmp_path,
                                                                                                          fake_bwrap):
    """Review of #231, m1: R-3 judged the resolved store, so a symlinked `.aew` under a writable bind passed, and a
    contained process could rename the link and make a `.aew` of its own for the next host `aew` to find."""
    if sys.platform == "win32":
        pytest.skip("a symlink needs a privilege on Windows; the check is pure and runs on Linux and macOS")
    work = tmp_path / "p"
    (tmp_path / "elsewhere" / "state").mkdir(parents=True)
    work.mkdir()
    (work / ".aew").symlink_to(tmp_path / "elsewhere")
    real = os.path.realpath(work)
    with pytest.raises(ContainmentUnavailable, match="symlink on the path to AEW's store") as refused:
        L._refuse_store_binds("lead", work, L.bind_order([real], [os.path.join(real, ".aew")]))
    assert refused.value.details["reason"] == "store_path_symlink"
    assert refused.value.details["symlink"] == os.path.join(real, ".aew")
    L._refuse_store_binds("lead", work, L.bind_order([os.path.realpath(tmp_path / "out")], []))  # no bind reaches it


def test_an_operator_root_inside_a_readers_workspace_is_not_bound_so_the_workspace_stays_read_only(tmp_path,
                                                                                                    fake_bwrap):
    """Review of #231, m3: with binds by depth, a writable root deeper than the reader's read-only workspace would win
    its subtree. A reader's workspace is read-only whole, so the root is left out of its layout (an implementer, who
    writes the workspace anyway, still gets it)."""
    repo, ws = repo_with_worktree(tmp_path)
    build = ws / "build"
    build.mkdir()
    for role, bound in (("reviewer", False), ("implementer", True)):
        run = tmp_path / f"run-{role}"
        layout = C.for_run(role=role, scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                           bridge_dir=None, policy={"writable": [str(build)]}, home=str(tmp_path / "home"),
                           project=str(repo))
        assert (os.path.realpath(build) in layout.writable) is bound, role
        assert (os.path.realpath(build) in layout.operator_writable) is bound, role


def test_a_missing_aew_local_is_made_and_hidden_and_a_project_with_no_aew_has_nothing_to_hide(tmp_path, fake_bwrap):
    """Review of #231, m4: skipped while absent, the mask failed open for a lock a host writer created later."""
    repo, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    kwargs = {"role": "reviewer", "scope": "ticket", "workspace": str(ws), "run_dir": run,
              "scratch": str(run / "scratch"), "bridge_dir": None, "policy": None, "home": str(tmp_path / "home"),
              "project": str(repo)}
    assert C.for_run(**kwargs).hide_runs == ()  # not an AEW root: nothing made there
    assert not (repo / ".aew").exists()
    (repo / ".aew" / "state").mkdir(parents=True)
    layout = C.for_run(**kwargs)
    assert (repo / ".aew" / "local").is_dir()
    assert layout.hide_runs == (os.path.realpath(repo / ".aew" / "local"),)


def test_a_run_without_its_project_is_refused_before_any_layout(tmp_path, monkeypatch, fake_bwrap):
    monkeypatch.setattr(C, "supported", lambda: True)
    with pytest.raises(ContainmentUnavailable, match="needs its project root"):
        C.establish(role="reviewer", scope="ticket", workspace=str(tmp_path), run_dir=tmp_path / "run",
                    scratch=str(tmp_path / "s"), bridge_dir=None, policy={"containment": {"mode": "required"}})
    assert not (tmp_path / "run").exists()


# ------------------------------------------------------------------------------------- STG-05 CS-2: the masks
RESOLV = "/run/systemd/resolve/stub-resolv.conf"


def masked_layout(**kw) -> C.Layout:
    """A layout with ``/run`` masked and one name-resolution exception, whatever this host's own facts are."""
    base = {"role": "reviewer", "access": "read", "bwrap": "/usr/bin/bwrap", "writable": ("/s",), "readonly": (),
            "hide_host": ("/run",), "run_exceptions": ((RESOLV, "name resolution until CS-3"),)}
    return C.Layout(**{**base, **kw})


def test_run_is_masked_after_the_root_bind_in_bind_order_and_remounted_read_only():
    """CB-03, ruling R-1: every layout masks /run whole (eval's, built without for_run, included): an empty tmpfs at
    its depth, after the root bind, remounted read-only after the last bind-back into it, and never covered again."""
    default = C.Layout(role="x", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=())
    assert L.RUN in default.hide_host
    layout = masked_layout(visible=("/run/media/u/d/proj",))
    flags = C.bwrap_argv(layout, ["agent"])
    root = next(i for i in range(len(flags) - 2) if flags[i:i + 3] == ["--ro-bind", "/", "/"])
    assert root < flags.index("/run") and flags[flags.index("/run") - 1] == "--tmpfs"
    assert mask_problems(flags, layout.hide_host) == []
    assert flags[flags.index("--remount-ro") + 1] == "/run"


def test_var_run_is_masked_too_where_it_is_a_directory_of_its_own(monkeypatch):
    islink, isdir = os.path.islink, os.path.isdir
    monkeypatch.setattr(L.os.path, "islink", lambda p: p != L.VAR_RUN and islink(p))
    monkeypatch.setattr(L.os.path, "isdir", lambda p: p == L.VAR_RUN or isdir(p))
    assert L.host_masks() == (L.RUN, L.VAR_RUN)
    monkeypatch.setattr(L.os.path, "islink", lambda p: p == L.VAR_RUN or islink(p))
    assert L.host_masks() == (L.RUN,)  # the usual link to /run: masked with it


def test_each_run_exception_is_bound_back_read_only_after_the_mask_and_described_with_its_reason():
    layout = masked_layout()
    flags = C.bwrap_argv(layout, ["agent"])
    i = flags.index(RESOLV)
    assert flags[i - 1] == "--ro-bind" and flags[i + 1] == RESOLV  # read-only, by name
    assert flags.index("/run") < i < flags.index("--remount-ro")
    described = layout.describe()
    assert described["bound_back"] == [{"path": RESOLV, "why": "name resolution until CS-3"}]
    assert "/run" in described["hidden"]
    assert L.RUN_EXCEPTIONS == ()  # no exception is measured; the host-derived one is the operator's ruling


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need a privilege on Windows; the chain is POSIX's")
def test_the_resolv_conf_exception_is_the_first_path_under_run_on_its_chain_when_the_chain_ends_at_a_file(tmp_path):
    """The operator's ruling (2026-10-24): on a systemd-resolved host /etc/resolv.conf links into /run, and its target
    is the one host-derived exception, bound back read-only by name, with its reason."""
    etc, run, other = tmp_path / "etc", tmp_path / "run", tmp_path / "other"
    for d in (etc, run / "systemd" / "resolve", run / "resolvconf", other):
        d.mkdir(parents=True)
    resolv = etc / "resolv.conf"

    def exception(target: Path | None) -> tuple:
        if resolv.is_symlink() or resolv.exists():
            resolv.unlink()
        if target is None:
            resolv.write_text("nameserver 192.0.2.1\n")
        else:
            resolv.symlink_to(os.path.relpath(target, etc))
        return L._resolv_exception(str(resolv), str(run))

    assert exception(None) == ()  # NetworkManager's regular file (the Rocky VM): nothing under /run to keep
    stub = run / "systemd" / "resolve" / "stub-resolv.conf"
    stub.write_text("nameserver 127.0.0.53\n")
    assert exception(stub) == ((str(stub), "name resolution until CS-3 (the operator, 2026-10-24)"),)
    (run / "resolvconf" / "resolv.conf").symlink_to(stub)
    assert exception(run / "resolvconf" / "resolv.conf")[0][0] == str(run / "resolvconf" / "resolv.conf")  # the first
    assert exception(run / "systemd" / "resolve" / "missing.conf") == ()  # dangling: binding it would fail the launch
    (other / "resolv.conf").write_text("nameserver 192.0.2.1\n")
    assert exception(other / "resolv.conf") == ()  # a chain that never enters /run needs nothing back


def test_a_project_under_a_masked_prefix_stays_visible_and_a_writable_project_stays_writable():
    """The project's visible bind is in the one bind order (the Lead's approval, 2026-10-23): a project on removable
    media under /run lands inside the mask, after it, with its workspaces, each recorded with the operator's ruling
    (2026-10-23, on R-1) as its reason. Within a depth the visible bind comes first, so the Lead's R-2 shape (the
    project writable, CS-4) keeps its writable bind."""
    proj, ws = "/run/media/u/d/proj", "/run/media/u/d/.aew-workspaces/ws"
    layout = masked_layout(visible=(proj,), writable=(ws, "/s"))
    flags = C.bwrap_argv(layout, ["agent"])
    assert flags.index("/run") < flags.index(proj) and flags.index("/run") < flags.index(ws)
    assert mask_problems(flags, layout.hide_host) == []
    assert dict(layout.bind_backs()) == {RESOLV: "name resolution until CS-3", proj: L.RUN_BIND_BACK,
                                         ws: L.RUN_BIND_BACK}
    r2 = L.bind_order(["/p"], ["/p/.aew"], visible=["/p"])
    assert r2 == [("--ro-bind", "/p"), ("--bind", "/p"), ("--ro-bind", "/p/.aew")]


def test_a_mask_under_an_already_masked_tree_is_dropped():
    """An XAUTHORITY under /run (gdm's) or /tmp is hidden with its tree; binding a mask there would make its path in
    a mask that is read-only by then, and fail the launch."""
    home = "/home/u/.Xauthority"
    layout = masked_layout(hide_files=("/run/user/1000/gdm/Xauthority", home, "/tmp/xauth-1000"),
                           hide_dirs=("/run/user/1000/keyring", "/home/u/.ssh"))
    flags = C.bwrap_argv(layout, ["agent"])
    assert home in flags and "/home/u/.ssh" in flags
    assert not any(p in flags for p in ("/run/user/1000/gdm/Xauthority", "/tmp/xauth-1000", "/run/user/1000/keyring"))


def test_a_mask_inside_a_bind_into_a_masked_tree_is_emitted_and_holds():
    """Review of #244, m1: a secret inside a project under /run or under /tmp, or inside the run's own directory under
    its runs mask, is the host's file there, so its mask is emitted like any other: after every bind, and before the
    tree's read-only remount. A secret elsewhere in the same trees stays hidden with them."""
    proj, tmp_proj, runs = "/run/media/u/d/proj", "/tmp/proj", "/p/.aew/local"
    own = runs + "/harness/runs/R-1/scratch"
    files = (proj + "/secrets.env", tmp_proj + "/secrets.env", own + "/token")
    dirs = (proj + "/keys", tmp_proj + "/keys")
    hidden = ("/run/user/1000/gdm/Xauthority", "/tmp/xauth-1000", runs + "/harness/runs/R-2/token",
              "/run/user/1000/keyring")
    layout = masked_layout(visible=(proj, tmp_proj), writable=(own, "/s"), hide_runs=(runs,),
                           hide_files=(*files, *hidden[:3]), hide_dirs=(*dirs, hidden[3]))
    flags = C.bwrap_argv(layout, ["agent"])
    last_bind = max(i for i, f in enumerate(flags) if f in ("--bind", "--ro-bind") and flags[i + 1] in
                    (proj, tmp_proj, own, "/s", RESOLV))
    first_remount = flags.index("--remount-ro")
    for p in files:
        assert flags[flags.index(p) - 2:flags.index(p)] == ["--ro-bind", layout.mask_file], p
        assert last_bind < flags.index(p) < first_remount, p
    for p in dirs:
        assert flags[flags.index(p) - 1] == "--tmpfs" and last_bind < flags.index(p) < first_remount, p
    assert not any(p in flags for p in hidden)
    assert mask_problems(flags, (*layout.hide_host, *layout.hide_runs)) == []


def layout_of(tmp_path: Path, project: Path, ws: Path, run: Path, role: str) -> C.Layout:
    return C.for_run(role=role, scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=None, home=str(tmp_path / "home"), project=str(project),
                     runs=str(run.parent), env={})


def project_under(tmp_path: Path, monkeypatch, under: str, *,
                  role: str = "implementer") -> tuple[Path, Path, Path, Path, C.Layout]:
    """``(stand-in for /run, project, workspace, run directory, layout)``: a project and its workspace under ``under``
    below a directory of the test's own, which the layout masks as it masks /run. The run directory is where AEW keeps
    it, under the project's ``.aew/local``."""
    run_root = tmp_path / "run"
    (run_root / under).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(L, "host_masks", lambda: (L._real(run_root),))
    repo, ws = repo_with_worktree(run_root / under)
    (repo / ".aew").mkdir()
    run = repo / ".aew" / "local" / "harness" / "runs" / "R-1"
    return run_root, repo, ws, run, layout_of(tmp_path, repo, ws, run, role)


@pytest.mark.parametrize("role", ["implementer", "reviewer"])
def test_a_project_under_run_is_bound_back_only_by_its_own_binds_at_their_real_paths_and_modes(tmp_path, monkeypatch,
                                                                                                fake_bwrap, role):
    """The operator's ruling of 2026-10-23 on R-1, condition 1: what comes back into the mask is the layout's own binds
    of the project and this run's workspace, at their real paths, each with the mode the same layout gives it
    anywhere else; the bind order is the one without the mask plus the mask, so no ancestor (the media directory, the
    user's) comes back. Each bind-back is recorded with the ruling as its reason."""
    run_root, repo, ws, run, layout = project_under(tmp_path, monkeypatch, "media/u/d", role=role)
    mask = L._real(run_root)
    back = {p: why for p, why in layout.bind_backs() if p not in dict(layout.run_exceptions)}
    assert {L._real(repo), L._real(ws)} <= set(back)
    assert all(L._within(p, L._real(repo)) or L._within(p, L._real(ws)) for p in back), sorted(back)
    assert all(L._real(p) == p for p in back) and set(back.values()) == {L.RUN_BIND_BACK}
    monkeypatch.setattr(L, "host_masks", lambda: ())
    elsewhere = layout_of(tmp_path, repo, ws, run, role)  # the same layout, with nothing masked over the media
    assert [e for e in L.order(layout) if e != ("--tmpfs", mask)] == L.order(elsewhere)
    assert ("--tmpfs", mask) in L.order(layout)
    assert {b["path"]: b["why"] for b in layout.describe()["bound_back"]} == dict(layout.bind_backs())


def test_a_bind_under_run_that_is_neither_the_project_nor_its_workspace_is_refused(tmp_path, monkeypatch, fake_bwrap):
    """Condition 1's other side: the interpreter's environment on the same media, outside the project, would be a
    bind-back of something else, so the launch is refused, naming it."""
    venv = tmp_path / "run" / "media" / "u" / "d" / "venv"
    venv.mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(venv))
    with pytest.raises(ContainmentUnavailable, match="only the project") as refused:
        project_under(tmp_path, monkeypatch, "media/u/d")
    assert refused.value.details["reason"] == "run_bind_back_outside_project"
    assert refused.value.details["path"] == L._real(venv)


@pytest.mark.parametrize("under", ["aew-g3/x", "aew-wis/x", "aew-later/x", "user/1000/gvfs/d", "dbus/x",
                                   "systemd/x"])
def test_a_project_under_a_protected_run_path_is_refused(tmp_path, monkeypatch, fake_bwrap, under):
    """Condition 2: nothing is bound back under G3's or the fact issuer's directory (or any later AEW service's), the
    operator's runtime directory, the buses or systemd's, whatever the ruling lets in (``L.RUN_PROTECTED``)."""
    with pytest.raises(ContainmentUnavailable, match="where nothing is bound back") as refused:
        project_under(tmp_path, monkeypatch, under)
    assert refused.value.details["reason"] == "run_bind_back_protected"


def test_a_bind_back_that_is_the_mask_itself_is_refused():
    """Condition 2's "is or contains": a project at /run itself would contain every protected path."""
    layout = masked_layout(visible=("/run",), run_exceptions=())
    with pytest.raises(ContainmentUnavailable, match="the mask itself") as refused:
        L._refuse_run_bind_backs(layout, project="/run", workspace="/elsewhere/ws")
    assert refused.value.details["reason"] == "run_bind_back_protected"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need a privilege on Windows; the check is POSIX's")
def test_a_project_reached_through_a_symlink_is_bound_back_at_its_real_path_and_a_link_path_is_refused(tmp_path,
                                                                                                       monkeypatch,
                                                                                                       fake_bwrap):
    """Condition 1's real paths: a project named through a symlink is bound back where it really is, and a layout
    that would bind back the link's path is refused."""
    run_root, repo, ws, run, _ = project_under(tmp_path, monkeypatch, "media/u/d")
    link = run_root / "media" / "u" / "link"
    link.symlink_to(repo)
    layout = layout_of(tmp_path, link, ws, run, "reviewer")
    assert os.path.realpath(repo) in layout.inside_host_masks() and str(link) not in layout.inside_host_masks()
    linked = masked_layout(hide_host=(os.path.realpath(run_root),), visible=(str(link),), run_exceptions=())
    with pytest.raises(ContainmentUnavailable, match="not its real one") as refused:
        L._refuse_run_bind_backs(linked, project=str(link), workspace=str(ws))
    assert refused.value.details["reason"] == "run_bind_back_not_real"


def test_an_operator_root_under_or_containing_run_is_refused(tmp_path, fake_bwrap):
    """R-1 binds nothing back into /run but measured exceptions (the Lead, Q6): an operator root there would be one.
    It stays refused for a project there (the operator's ruling of 2026-10-23, condition 3)."""
    _, ws = repo_with_worktree(tmp_path)
    guarded = L._guarded(ws, project=None, runs=None, bridge_dir=None, masks=(), host=(L.RUN,))
    under = L._real("/run/media/u/build")
    with pytest.raises(ContainmentUnavailable, match="runtime directory, masked whole"):
        L._refuse_unsafe_root(under, under, guarded, workspaces=str(tmp_path / "workspaces"))
    with pytest.raises(ContainmentUnavailable) as containing:  # its message names the first few of what it exposes
        L._refuse_unsafe_root("/", L._real("/"), guarded, workspaces=str(tmp_path / "workspaces"))
    assert any(e["path"] == L._real(L.RUN) for e in containing.value.details["exposes"])


def test_a_layout_survives_score_childs_json_round_trip_with_the_same_argv():
    """eval's scoring child rebuilds its layout from JSON (``dataclasses.asdict``, then lists back to tuples): the new
    fields, the exceptions' pairs among them, give the same sandbox."""
    import dataclasses
    import json

    layout = masked_layout(display_files=("/home/u/.Xauthority",))
    fields = {k: (tuple(v) if isinstance(v, list) else v)
              for k, v in json.loads(json.dumps(dataclasses.asdict(layout))).items()}
    assert C.bwrap_argv(C.Layout(**fields), ["x"]) == C.bwrap_argv(layout, ["x"])


def test_display_files_and_the_xauthority_file_are_masked_by_type_when_present(tmp_path, fake_bwrap):
    """CB-04: the display's credentials are masked like the secret files, the file XAUTHORITY names included; so are
    git's credential cache and store file, at their defaults and where XDG_* moves them."""
    home = tmp_path / "home"
    (home / ".cache" / "git" / "credential").mkdir(parents=True)
    (home / ".config" / "git").mkdir(parents=True)
    for rel in (".Xauthority", ".ICEauthority", ".config/git/credentials"):
        (home / rel).write_text("synthetic\n")
    (home / ".git-credential-cache").mkdir()
    xauth, xdg = tmp_path / "elsewhere" / "xauth", tmp_path / "xdg"
    xauth.parent.mkdir()
    xauth.write_text("synthetic\n")
    (xdg / "cache" / "git" / "credential").mkdir(parents=True)
    (xdg / "config" / "git").mkdir(parents=True)
    (xdg / "config" / "git" / "credentials").write_text("synthetic\n")
    env = {"XAUTHORITY": str(xauth), "XDG_CACHE_HOME": str(xdg / "cache"), "XDG_CONFIG_HOME": str(xdg / "config")}
    layout = run_layout(tmp_path, "reviewer", home=str(home), env=env)
    real = os.path.realpath
    files = {real(home / ".Xauthority"), real(home / ".ICEauthority"), real(xauth),
             real(home / ".config/git/credentials"), real(xdg / "config" / "git" / "credentials")}
    assert files <= set(layout.hide_files)
    assert {real(home / ".cache/git/credential"), real(home / ".git-credential-cache"),
            real(xdg / "cache" / "git" / "credential")} <= set(layout.hide_dirs)
    assert set(layout.display_files) == {real(home / ".Xauthority"), real(home / ".ICEauthority"), real(xauth)}
    assert run_layout(tmp_path / "bare", "reviewer", home=str(tmp_path / "empty")).display_files == ()


def test_every_bwrap_argv_unsets_the_display_variables_and_starts_a_new_session():
    """CB-04 and CB-05 on every argv, whoever built the layout: no display or session variable, and no controlling
    terminal (bubblewrap's --new-session), so TIOCSTI has no terminal it would accept."""
    flags = C.bwrap_argv(C.Layout(role="x", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=()), ["a"])
    flags = flags[:flags.index("--")]
    unset = [flags[i + 1] for i, f in enumerate(flags) if f == "--unsetenv"]
    assert unset == list(L.DISPLAY_ENV)
    assert set(L.DISPLAY_ENV) == {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS",
                                  "SSH_AUTH_SOCK"}
    assert "--new-session" in flags


def test_posix_keep_and_the_display_variables_are_disjoint():
    from aew.harness import agentenv

    assert set(agentenv.POSIX_KEEP) & set(L.DISPLAY_ENV) == set()


def test_no_contained_environment_builder_passes_a_display_variable(tmp_path):
    """Every environment a contained process starts from (the harness's, its server's, a validation check's) is an
    allow-list without the display, the session bus or the ssh agent, so a change to the list fails here too."""
    from aew.engine.validation_ops import Validation
    from aew.harness import agentenv
    from aew.harness.opencode.adapter import server_env

    base = {"PATH": "/usr/bin", "HOME": "/home/u", **dict.fromkeys(L.DISPLAY_ENV, "synthetic")}
    built = [agentenv.build(base, endpoint="e", key_hex="00", invocation="I-1", run="R-1", work_unit="T-1"),
             server_env(base, tmp_path, provider_env=[], config={}, password="p")]
    with pytest.MonkeyPatch.context() as mp:
        for name in L.DISPLAY_ENV:
            mp.setenv(name, "synthetic")
        built.append(Validation._check_env(None))
    for env in built:
        assert not {k.upper() for k in env} & set(L.DISPLAY_ENV), sorted(env)
