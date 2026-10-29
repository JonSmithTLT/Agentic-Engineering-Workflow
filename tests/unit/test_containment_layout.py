"""The sandbox layout as data (M4-B): argv order, the exhaustive role map, secret masks by type, labels.

Pure: nothing here starts bubblewrap, so it runs on every platform. Linux behaviour is in
tests/integration/test_containment.py.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from host_env import GUARDED

from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import layout as L

pytestmark = GUARDED


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
    repo.mkdir(parents=True, exist_ok=True)  # a test may put files in it first
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


def lead_layout(tmp_path: Path, *, scope: str = "project", network: str = L.SHARED, net_dir: str | None = None,
                home: str | None = None, policy: dict | None = None, env: dict[str, str] | None = None) -> C.Layout:
    """The Lead's layout (STG-05 CS-4): its project's working tree is its workspace, its run directory and its own
    OpenCode state are under the project's `.aew/local`."""
    repo, _ = repo_with_worktree(tmp_path)
    for d in (".aew/state/log", ".aew/local/harness/runs"):
        (repo / d).mkdir(parents=True, exist_ok=True)
    run = repo / ".aew/local/harness/runs/lead-1"
    return C.for_run(role="lead", scope=scope, workspace=str(repo), run_dir=run, scratch=str(run / "scratch"),
                     bridge_dir=None, policy=policy, home=home if home is not None else str(tmp_path / "home"),
                     project=str(repo), runs=str(run.parent), env=env or {}, network=network, net_dir=net_dir,
                     state_dir=str(repo / ".aew/local/harness/lead"))


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


def test_every_archetype_has_a_layout_the_lead_included_and_an_unknown_role_has_none(tmp_path, fake_bwrap):
    from aew.roles import ARCHETYPES

    assert set(L.WORKSPACE_ACCESS) == set(ARCHETYPES)  # exhaustive: a new archetype must be classified (CS-4: the Lead)
    assert L.WORKSPACE_ACCESS["lead"] == "write"
    with pytest.raises(ContainmentUnavailable, match="no containment layout"):
        run_layout(tmp_path / "x", "mystery")


def test_a_lead_writes_only_its_project_and_an_implementer_only_its_ticket(tmp_path, fake_bwrap, monkeypatch):
    """A-33 §3.1: the write scopes are per role. Each writing role writes only its own scope; the other's is refused,
    and so is any scope for a writing role nobody gave scopes."""
    assert set(L.WRITE_SCOPES) == {r for r, a in L.WORKSPACE_ACCESS.items() if a == "write"}
    assert lead_layout(tmp_path / "ok-lead").role == "lead"
    assert run_layout(tmp_path / "ok-impl", "implementer", scope="ticket").access == "write"
    with pytest.raises(ContainmentUnavailable, match="the lead role may write only a project scope, not a 'ticket'"):
        lead_layout(tmp_path / "lead-ticket", scope="ticket")
    with pytest.raises(ContainmentUnavailable,
                       match="the implementer role may write only a ticket scope, not a 'project'"):
        run_layout(tmp_path / "impl-project", "implementer", scope="project")
    monkeypatch.setitem(L.WORKSPACE_ACCESS, "unscoped", "write")  # a writing role without scopes
    with pytest.raises(ContainmentUnavailable, match="the unscoped role may write only no scope") as refused:
        run_layout(tmp_path / "unscoped", "unscoped", scope="ticket")
    assert refused.value.details["allowed"] == []


def test_the_lead_layout_re_binds_aew_and_the_git_metadata_read_only_after_the_working_tree(tmp_path, fake_bwrap):
    """Ruling R-2 (CS-4 outcome 2): the Lead writes its working tree, which holds the store; `.aew` and the git
    metadata are re-bound read-only after it, so the role-bind check passes by its second clause (CB-07)."""
    layout = lead_layout(tmp_path)
    repo = os.path.realpath(tmp_path / "repo")
    aew, git_dir = os.path.join(repo, ".aew"), os.path.join(repo, ".git")
    assert layout.writable[0] == repo and layout.access == "write"
    assert aew in layout.readonly and git_dir in layout.readonly
    assert aew in layout.protected and os.path.join(git_dir, "HEAD") in layout.protected
    steps = L.order(layout)
    assert steps.index(("--bind", repo)) < steps.index(("--ro-bind", aew))
    assert steps.index(("--bind", repo)) < steps.index(("--ro-bind", git_dir))
    L._refuse_store_binds("lead", repo, steps)  # what for_run checked
    # Planted: the same layout without the `.aew` re-bind (the forgotten route) is refused, naming what to re-bind.
    without = [s for s in steps if s != ("--ro-bind", aew)]
    with pytest.raises(ContainmentUnavailable, match="is not re-bound read-only after it") as refused:
        L._refuse_store_binds("lead", repo, without)
    assert refused.value.details["reason"] == "store_path_writable" and refused.value.details["needs"] == aew


def test_the_lead_sandbox_hides_aew_local_but_its_own_run_and_state_directories(tmp_path, fake_bwrap):
    """CS-4 outcome 2: `.aew/local` is masked whole, so no control lock and no other run's state or server socket is in
    the Lead's sandbox; only the Lead's own run directories and its OpenCode state are bound back, writable."""
    layout = lead_layout(tmp_path)
    repo = os.path.realpath(tmp_path / "repo")
    local = os.path.join(repo, ".aew", "local")
    assert layout.hide_runs == (local,)
    run = os.path.join(local, "harness", "runs", "lead-1")
    under = sorted(p for p in (*layout.writable, *layout.readonly) if L._within(p, local))
    assert under == sorted([os.path.join(local, "harness", "lead"), os.path.join(run, "git"),
                            os.path.join(run, "harness"), os.path.join(run, "scratch")])
    assert all(p in layout.writable for p in under)
    assert os.path.isdir(os.path.join(local, "harness", "lead"))  # the state directory is made by for_run
    assert mask_problems(C.bwrap_argv(layout, ["agent"]), layout.hide_runs) == []


def test_a_private_network_layout_binds_no_resolv_conf_back_into_run_and_a_shared_one_keeps_it(tmp_path, fake_bwrap,
                                                                                               monkeypatch):
    """ST-27 fact 3: CS-2's bind-back of resolv.conf's target under /run was "until CS-3". A network of the run's own,
    the Lead's included, resolves no names inside (the relay and the egress proxy resolve on the host), so only the
    host's network keeps it."""
    monkeypatch.setattr(L, "_resolv_exception", lambda *a, **k: ((RESOLV, L.RESOLV_WHY),))
    shared = lead_layout(tmp_path / "shared")
    assert shared.run_exceptions == ((RESOLV, L.RESOLV_WHY),)
    for mode in (L.PROXY_ONLY, L.ISOLATED):
        net = tmp_path / f"net-{mode}"
        net.mkdir()
        private = lead_layout(tmp_path / mode, network=mode, net_dir=str(net))
        assert private.run_exceptions == L.RUN_EXCEPTIONS == ()
        assert RESOLV not in private.inside_host_masks()
        assert RESOLV not in C.bwrap_argv(private, ["agent"])
    worker = run_layout(tmp_path / "worker", "reviewer")  # the workers' layouts follow the same rule
    assert worker.run_exceptions == ((RESOLV, L.RESOLV_WHY),)


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


def test_a_secret_directory_is_masked_whole_and_any_other_secret_is_left_out_of_its_directory(tmp_path, fake_bwrap,
                                                                                               tmp_unmasked):
    """CS-4 addendum 6: a secret directory is an empty tmpfs; a secret file, and any secret path absent at the launch
    (its first component that does not exist yet), is left out of its directory: that directory is an empty tmpfs at
    its depth, every other entry it holds is put back read-only, links made again as links, and then it is read-only.
    So a replacement or a creation on the host is not seen inside. No file is bound over."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".netrc").write_text("machine x login y password z")
    (home / ".config" / "gh").mkdir(parents=True)
    (home / ".profile").write_text("# ordinary\n")
    (tmp_path / "extra-secret").write_text("s")
    layout = run_layout(tmp_path, "reviewer", home=str(home), policy={"hide": [str(tmp_path / "extra-secret")]})
    real = os.path.realpath
    assert set(layout.hide_dirs) == {real(home / ".ssh"), real(home / ".config" / "gh")}
    assert layout.hide_files == () and layout.tree_masks == () and layout.tree_absent == ()
    gone = {real(home / ".netrc"), real(tmp_path / "extra-secret"),  # present
            real(home / ".git-credentials"), real(home / ".Xauthority"),  # absent
            real(home / ".config" / "git"),  # ~/.config/git/credentials: its first component that does not exist
            real(home / ".local")}  # ~/.local/share/opencode: the same
    assert gone <= set(layout.left_out), sorted(set(gone) - set(layout.left_out))
    assert {real(home), real(home / ".config"), real(tmp_path)} <= set(layout.left_out_of)
    assert real(home / ".profile") in layout.put_back and not set(layout.put_back) & gone
    assert real(home / ".ssh") not in layout.put_back  # its own tmpfs, at its mount point
    flags = C.bwrap_argv(layout, ["true"])
    for d in (real(home), real(home / ".config")):
        assert d in pairs(flags, "--tmpfs") and d in pairs(flags, "--remount-ro"), d
    assert flags.index(real(home / ".profile")) > position(flags, "--tmpfs", real(home))
    assert flags[flags.index(real(home / ".profile")) - 1] == "--ro-bind-try"
    assert position(flags, "--remount-ro", real(home)) > position(flags, "--tmpfs", real(home / ".ssh"))
    assert not any(real(p) in flags for p in gone)


def pairs(flags: list[str], flag: str) -> list[str]:
    """The argument after each ``flag`` on a bubblewrap argv."""
    return [flags[i + 1] for i, f in enumerate(flags) if f == flag]


def position(flags: list[str], flag: str, path: str) -> int:
    """Where ``flag path`` is on a bubblewrap argv."""
    return next(i for i, f in enumerate(flags) if f == flag and flags[i + 1] == path)


@pytest.mark.parametrize(("rel", "kind"), [(".claude.json", "file"), (".config/anthropic", "dir")])
def test_a_provider_config_location_is_masked_by_its_type_and_left_out_while_absent(tmp_path, fake_bwrap,
                                                                                    tmp_unmasked, rel, kind):
    assert rel in (L.SECRET_FILES if kind == "file" else L.SECRET_DIRS)
    home = tmp_path / "home"
    home.mkdir()
    absent = run_layout(tmp_path / "a", "reviewer", home=str(home))
    first = home / Path(rel).parts[0]  # absent: its first component is left out of the home directory
    assert os.path.realpath(first) in absent.left_out and not any(p.endswith(os.path.normpath(rel)) for p in
                                                                    (*absent.hide_dirs, *absent.hide_files))
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
        assert real in layout.left_out and real not in (*layout.hide_dirs, *layout.hide_files, *layout.put_back)
        assert real not in flags and os.path.realpath(home) in pairs(flags, "--tmpfs")  # absent from its directory
    else:
        assert real in layout.hide_dirs and real not in layout.left_out
        assert flags[flags.index(real) - 1] == "--tmpfs"                # an empty directory


def test_a_suffixed_copy_of_a_provider_config_file_is_left_out_and_one_made_later_is_never_put_back(tmp_path,
                                                                                                fake_bwrap,
                                                                                                tmp_unmasked):
    """A copy beside a secret file, matched by its prefix, is left out of the home directory like the file; one made
    after the launch is not seen either, as only what the home directory held at the launch is put back."""
    assert ".claude.json." in L.SECRET_FILE_PREFIXES
    home = tmp_path / "home"
    home.mkdir()
    absent = run_layout(tmp_path / "a", "reviewer", home=str(home))
    assert not any(".claude.json." in os.path.basename(p) for p in (*absent.left_out, *absent.put_back))
    (home / ".claude.json.backup").write_text('{"k": "v"}')
    (home / ".claude.json.d").mkdir()                    # a directory with a matching name is not a file
    (home / ".claude.json.d" / ".claude.json.inner").write_text("v")  # and the listing is not recursive
    (home / "x.claude.json.backup").write_text("v")     # a prefix, not a substring
    layout = run_layout(tmp_path / "b", "reviewer", home=str(home))
    real = os.path.realpath
    backup = real(home / ".claude.json.backup")
    assert backup in layout.left_out and backup not in (*layout.put_back, *layout.hide_files)
    assert {real(home / ".claude.json.d"), real(home / "x.claude.json.backup")} <= set(layout.put_back)
    assert real(home) in layout.left_out_of and real(home / ".claude.json.later") not in layout.put_back
    assert backup not in C.bwrap_argv(layout, ["true"])


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
                         "network": {"mode": C.network(), "provider_relay": "none"}, "mechanism": "bubblewrap 0.4.0",
                         "self_test": {"ok": True}}
    assert C.network() == ("not_provided" if sys.platform == "win32" else "shared")
    weaker = C.label(contained=False, reason="bwrap missing")
    assert weaker["filesystem"] == "workdir_separation_only" and weaker["weaker_because"] == "bwrap missing"
    assert weaker["process_ownership"] in {"job_object", "process_group"}
    assert weaker["network"] == {"mode": C.network(), "provider_relay": "none"}
    for old in ("workdir_separation_only", None, {}):
        assert C.normalize(old)["filesystem"] == "workdir_separation_only"
        assert C.normalize(old)["network"] == {"mode": C.network(), "provider_relay": "none"}
    assert C.normalize(contained) is contained
    # a record from before CS-3b holds the network's mode as a string (F28 §3.1's labels came with CS-3b)
    assert C.normalize({**contained, "network": "shared"})["network"] == {"mode": "shared", "provider_relay": "none"}


def test_a_contained_runs_label_names_its_layouts_network_and_what_its_network_holds():
    """F28 §3.1: network.mode is the layout's, and network.provider_relay and network.egress_allow what the run's
    network started (``netns.RunNetwork.describe``)."""
    layout = L.Layout(role="reviewer", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=(),
                      hide_host=("/run",), run_exceptions=(), network="proxy_only", net_dir="/tmp/aew-net-x")
    got = C.label(contained=True, layout=layout,
                  net={"provider_relay": "configured", "egress_allow": ["a.example:443"]})
    assert got["network"] == {"mode": "proxy_only", "provider_relay": "configured", "egress_allow": ["a.example:443"]}
    assert got["layout"]["network"] == "proxy_only" and got["layout"]["net_dir"] == "/tmp/aew-net-x"
    # a contained run whose network started nothing (integration validation's) still says it has no relay
    assert C.label(contained=True, layout=layout)["network"] == {"mode": "proxy_only", "provider_relay": "none"}


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
    lead = role == "lead"  # the Lead's workspace is its project's working tree, in the project scope (CS-4)
    return C.for_run(role=role, scope="project" if lead else "ticket",
                     workspace=str(workspace or (repo if lead else ws)), run_dir=run,
                     scratch=str(scratch or run / "scratch"), bridge_dir=None, policy=None,
                     home=str(tmp_path / "home"), project=str(repo), runs=str(run.parent), env={})


@pytest.mark.parametrize("role", sorted(L.WORKSPACE_ACCESS))
def test_every_roles_layout_keeps_its_writable_binds_off_the_stores_path_and_the_control_lock_out(tmp_path, role,
                                                                                                    fake_bwrap):
    layout = project_layout(tmp_path, role)
    repo = os.path.realpath(tmp_path / "repo")
    store = os.path.join(repo, ".aew", "state")
    described = layout.describe()
    # The check itself, over what the run records of its layout: a role added later is checked the same way.
    L._refuse_store_binds(role, repo, L.bind_order(described["writable"], described["readonly"], layout.hide_runs))
    assert not any(L._within(w, store) for w in layout.writable)  # never the store, nor under it
    holders = [w for w in layout.writable if L._within(store, w)]  # CB-07's second clause: only the Lead's tree
    assert holders == ([repo] if role == "lead" else [])
    if holders:  # ...and the next directory down to the store is re-bound read-only after it
        assert os.path.join(repo, ".aew") in layout.readonly
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
                           project=str(repo), env={})
        assert (os.path.realpath(build) in layout.writable) is bound, role
        assert (os.path.realpath(build) in layout.operator_writable) is bound, role


def test_a_missing_aew_local_is_made_and_hidden_and_a_project_with_no_aew_has_nothing_to_hide(tmp_path, fake_bwrap):
    """Review of #231, m4: skipped while absent, the mask failed open for a lock a host writer created later."""
    repo, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    kwargs = {"role": "reviewer", "scope": "ticket", "workspace": str(ws), "run_dir": run,
              "scratch": str(run / "scratch"), "bridge_dir": None, "policy": None, "home": str(tmp_path / "home"),
              "project": str(repo), "env": {}}
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
    monkeypatch.setattr(L, "GSSPROXY", "/nonexistent/gssproxy")  # whatever this host has
    islink, isdir = os.path.islink, os.path.isdir
    monkeypatch.setattr(L.os.path, "islink", lambda p: p != L.VAR_RUN and islink(p))
    monkeypatch.setattr(L.os.path, "isdir", lambda p: p == L.VAR_RUN or isdir(p))
    assert L.host_masks() == (L.RUN, L.VAR_RUN)
    monkeypatch.setattr(L.os.path, "islink", lambda p: p == L.VAR_RUN or islink(p))
    assert L.host_masks() == (L.RUN,)  # the usual link to /run: masked with it


def test_the_gss_api_proxys_directory_is_masked_whole_where_it_exists(monkeypatch):
    """The designer's D-CS2-6: /var/lib/gssproxy is one of the host's masks where it is a directory, so every layout
    (eval's included) hides it as it hides /run: an empty tmpfs at its depth, remounted read-only, and row 2 checks it
    (its host masks are layout.host_masks)."""
    islink, isdir = os.path.islink, os.path.isdir
    monkeypatch.setattr(L.os.path, "islink", lambda p: p != L.GSSPROXY and islink(p))
    monkeypatch.setattr(L.os.path, "isdir", lambda p: p == L.GSSPROXY or (p != L.VAR_RUN and isdir(p)))
    assert L.host_masks() == (L.RUN, L.GSSPROXY)
    layout = C.Layout(role="x", access="read", bwrap="/usr/bin/bwrap", writable=("/s",), readonly=())
    assert L.GSSPROXY in layout.hide_host and L.GSSPROXY in layout.describe()["hidden"]
    flags = C.bwrap_argv(layout, ["agent"])
    assert flags[flags.index(L.GSSPROXY) - 1] == "--tmpfs"
    assert mask_problems(flags, layout.hide_host) == []
    monkeypatch.setattr(L.os.path, "isdir", lambda p: p != L.GSSPROXY and p != L.VAR_RUN and isdir(p))
    assert L.host_masks() == (L.RUN,)  # a host without it masks nothing in its place


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
    assert exception(stub) == ((str(stub), L.RESOLV_WHY),)
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
    (tmp_path / "home").mkdir(exist_ok=True)  # an absent one would be left out of the test's own directory
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


def test_display_files_and_the_xauthority_file_are_masked_by_type(tmp_path, fake_bwrap):
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
    assert files <= set(layout.left_out) and layout.hide_files == ()
    assert {real(home / ".cache/git/credential"), real(home / ".git-credential-cache"),
            real(xdg / "cache" / "git" / "credential")} <= set(layout.hide_dirs)
    assert set(layout.display_files) == {real(home / ".Xauthority"), real(home / ".ICEauthority"), real(xauth)}
    assert run_layout(tmp_path / "bare", "reviewer", home=str(tmp_path / "empty")).display_files == ()


# Where OpenCode keeps its directories, named here and not taken from `opencode.login`, the owner these tests check
# (the review of #283 at b2dc3035, m2): each XDG base, with its default under the home directory.
XDG_BASES = {"XDG_DATA_HOME": ".local/share", "XDG_CONFIG_HOME": ".config", "XDG_STATE_HOME": ".local/state",
             "XDG_CACHE_HOME": ".cache"}

# The operator's environments for OpenCode: each moves where OpenCode keeps its files (STG-05 CS-4, outcome 2).
OPENCODE_ENVS: dict[str, Callable[[Path], dict[str, str]]] = {
    "defaults": lambda t: {},
    "xdg_moved": lambda t: {variable: str(t / "xdg" / variable) for variable in XDG_BASES},
    "absolute_db": lambda t: {"OPENCODE_DB": str(t / "elsewhere" / "logins.db")},
    "relative_db": lambda t: {"OPENCODE_DB": "other.db"},
    "relative_db_above": lambda t: {"OPENCODE_DB": os.path.join("..", "above.db")},
    "config_file": lambda t: {"OPENCODE_CONFIG": str(t / "cfg" / "custom.json")},
    "all_moved": lambda t: {**OPENCODE_ENVS["xdg_moved"](t), **OPENCODE_ENVS["absolute_db"](t),
                            **OPENCODE_ENVS["config_file"](t)},
}


def opencode_dir(env: dict[str, str], variable: str) -> Path:
    return Path(env.get(variable) or Path(env["HOME"], XDG_BASES[variable])) / "opencode"


def operator_files(env: dict[str, str]) -> list[Path]:
    """Every path AEW's host side reads the operator's OpenCode from, as OpenCode 2.0.18 places it, derived here from
    the operator's environment without the owner: the login database with SQLite's files beside it (``login.stored``),
    the configuration files (``lead.operator_preferences``, ``lead.operator_mcp_servers``) and the recent models
    (``ContainedLead._seed_models``); and, which the host never reads, the legacy login file OpenCode imports from its
    data directory and a file of its cache (addendum 4). The readers are named by hand; the environment keys they ask
    for are guarded by :func:`test_the_opencode_host_readers_ask_only_for_keys_these_environments_vary`."""
    data, config, state, cache = (opencode_dir(env, variable) for variable in XDG_BASES)
    named_db = env.get("OPENCODE_DB")
    db = Path(named_db) if named_db and os.path.isabs(named_db) else data / (named_db or "opencode.db")
    named = [Path(env["OPENCODE_CONFIG"])] if env.get("OPENCODE_CONFIG") else []
    return [db, *(db.with_name(db.name + suffix) for suffix in ("-wal", "-shm", "-journal")), config / "cli.json",
            *(config / name for name in ("config.json", "opencode.json", "opencode.jsonc")), state / "model.json",
            *named, data / "auth.json", cache / "models.json"]


class AskedFor(dict):
    """An environment that records each key read from it."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.asked: set[str] = set()

    def get(self, key: str, default: Any = None) -> Any:
        self.asked.add(key)
        return super().get(key, default)

    def __getitem__(self, key: str) -> Any:
        self.asked.add(key)
        return super().__getitem__(key)

    def __contains__(self, key: object) -> bool:
        self.asked.add(str(key))
        return super().__contains__(key)


def test_the_opencode_host_readers_ask_only_for_keys_these_environments_vary(tmp_path):
    """The review of #283 at b2dc3035, m2: each host reader of the operator's OpenCode asks the operator's environment
    only for keys :data:`OPENCODE_ENVS` moves (or the home directory), so a reader that starts following another
    variable fails here until the environments, and so the masks' test, cover it.

    Its limit (quick check of #283 at c307481a, n2): it sees only ``get``, ``[]`` and ``in`` on the mapping it hands to
    the four readers it calls. A key read through ``os.environ``, by iterating the mapping, or by a reader it does not
    call is not seen."""
    from types import SimpleNamespace

    from aew.harness.opencode import lead, login

    varied = {"HOME", *(k for shape in OPENCODE_ENVS.values() for k in shape(tmp_path))}
    asked: set[str] = set()
    for shape in OPENCODE_ENVS.values():
        env = AskedFor({"HOME": str(tmp_path / "home"), **shape(tmp_path)})
        login.stored(env)
        lead.operator_preferences(env)
        lead.operator_mcp_servers(env)
        lead.ContainedLead._seed_models(SimpleNamespace(base=env), tmp_path / "seed")  # type: ignore[arg-type]
        asked |= env.asked
    assert asked - varied == set(), sorted(asked - varied)
    # the guard sees the readers' own keys (none reads the cache, which is masked all the same)
    assert {"OPENCODE_DB", "OPENCODE_CONFIG", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME"} <= asked


def absent_inside(layout: C.Layout, path: str | os.PathLike[str]) -> bool:
    """Whether ``path`` is not there inside ``layout``'s sandbox, by the layout's data: it lies in a directory masked
    whole, or it, one of its ancestors, or where links lead it, is left out of its directory."""
    def left_out(p: str) -> bool:
        while True:
            if os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p)) in layout.left_out:
                return True
            if os.path.dirname(p) == p:
                return False
            p = os.path.dirname(p)

    named, real = os.path.abspath(path), os.path.realpath(path)
    return any(L._within(real, d) for d in layout.hide_dirs) or left_out(named) or left_out(real)


@pytest.mark.parametrize("shape", list(OPENCODE_ENVS))
def test_every_path_the_host_reads_the_operators_opencode_from_is_masked_from_a_contained_run(tmp_path, fake_bwrap,
                                                                                            shape):
    """STG-05 CS-4, outcome 2 (A-33 §3.1, CB-01): the Lead's view holds no operator credential. Every path the host
    side derives from the operator's environment for OpenCode's login and configuration is in a directory masked whole
    or left out of its directory, including one that appears only after the launch (CS-4 addendum 6)."""
    home = tmp_path / "home"
    env = OPENCODE_ENVS[shape](tmp_path)  # without HOME: the layout's home directory is the operator's
    host = {"HOME": str(home), **env}
    for variable in XDG_BASES:
        opencode_dir(host, variable).mkdir(parents=True, exist_ok=True)
    db = operator_files(host)[0]
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text("SYNTHETIC\n")  # the database alone: its sidecars and the other files are absent at the launch
    if env.get("OPENCODE_CONFIG"):
        Path(env["OPENCODE_CONFIG"]).parent.mkdir(parents=True)
        Path(env["OPENCODE_CONFIG"]).write_text("{}\n")
    layout = run_layout(tmp_path, "reviewer", home=str(home), env=env)
    unmasked = [str(p) for p in operator_files(host) if not absent_inside(layout, p)]
    assert unmasked == [], (layout.hide_dirs, layout.left_out)
    assert layout.hide_files == () and layout.tree_masks == () and layout.tree_absent == ()


def test_opencodes_database_or_configuration_among_other_files_is_left_out_and_hides_nothing_the_run_needs(
        tmp_path, fake_bwrap):
    """CS-4 addendum 6, ruling 5: the login database (with its -wal, -shm and -journal names) and the configuration
    file OPENCODE_CONFIG names are left out of their directories, so one in the home directory, or in a project the
    run only reads, launches, and the other files there stay readable."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("[user]\n")
    real = os.path.realpath
    for variable, name in (("OPENCODE_DB", "logins.db"), ("OPENCODE_CONFIG", "opencode.json")):
        for where in ("home", "project"):
            base = tmp_path / f"{variable}-{where}"
            repo = base / "repo"  # run_layout's project, which a reviewer only reads
            folder = home if where == "home" else repo
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text("SYNTHETIC\n")
            layout = run_layout(base, "reviewer", home=str(home), env={"HOME": str(home), variable: str(folder / name)})
            names = [name, *(name + s for s in ("-wal", "-shm", "-journal"))] if variable == "OPENCODE_DB" else [name]
            assert {real(folder / n) for n in names} <= set(layout.left_out), (variable, where)
            assert real(folder) in layout.left_out_of and real(folder) not in layout.hide_dirs
            assert real(home / ".gitconfig") in layout.put_back and layout.tree_masks == ()
            (folder / name).unlink()


def test_the_operators_opencode_database_in_the_runs_own_tree_is_refused_with_its_one_step(tmp_path, fake_bwrap):
    """The operator's decision of 2026-10-28: a login database in the run's own tree (the Lead's project, a worker's
    workspace) is refused, as OpenCode makes its -wal and -shm files there as it runs, which hold login rows and which
    no mask covers. The message gives the one step, the exact move and the variable's new value, and says it holds for
    every contained launch. Its data directory moved there takes the same refusal, unless it exists and is masked
    whole. In a policy's writable root the database is left out like any secret file, so the root is refused for
    holding a mask (CS-4 addendum 7, ruling 2)."""
    home = tmp_path / "home"
    home.mkdir()
    real = os.path.realpath
    dest = os.path.join(str(home), ".local", "share", "opencode")
    for case in ("OPENCODE_DB", "XDG_DATA_HOME"):
        t = tmp_path / case
        project = t / "repo"  # lead_layout's project, which is the Lead's workspace
        env = {"OPENCODE_DB": str(project / "logins.db")} if case == "OPENCODE_DB" else {
            "XDG_DATA_HOME": str(project / ".data")}
        with pytest.raises(ContainmentUnavailable) as exc:
            lead_layout(t, home=str(home), env={"HOME": str(home), **env})
        db = env.get("OPENCODE_DB") or str(project / ".data" / "opencode" / "opencode.db")
        assert exc.value.details["reason"] == "mask_holds_the_run" and exc.value.details["variables"] == [case]
        assert f"close OpenCode, move {db} with its -wal, -shm and -journal files to {dest}, and set " \
            f"OPENCODE_DB={os.path.join(dest, os.path.basename(db))}" in exc.value.message, exc.value.message
        assert exc.value.message.endswith("This applies to every contained launch, workers included")
    there = tmp_path / "there"
    (there / "repo" / ".data" / "opencode").mkdir(parents=True)  # there and masked whole: its database with it
    layout = lead_layout(there, home=str(home), env={"HOME": str(home), "XDG_DATA_HOME": str(there / "repo" / ".data")})
    assert real(there / "repo" / ".data" / "opencode") in layout.hide_dirs
    repo, ws = repo_with_worktree(tmp_path / "worker")
    root = tmp_path / "worker" / "out"
    root.mkdir()
    run = tmp_path / "worker" / "run"
    for where in (ws, root):
        with pytest.raises(ContainmentUnavailable) as exc:
            C.for_run(role="implementer", scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "s"),
                      bridge_dir=None, policy={"writable": [str(root)]}, home=str(home), project=str(repo),
                      env={"HOME": str(home), "OPENCODE_DB": str(where / "logins.db")})
        if where == ws:
            assert exc.value.details["refused"][0]["tree"] == real(ws), exc.value.details
        else:
            assert exc.value.details["resolved"] == real(root) and os.path.join(real(root), "logins.db") in [
                e["path"] for e in exc.value.details["exposes"]], exc.value.details


def test_inside_the_runs_own_tree_every_mask_is_made_in_place_read_only_and_named_with_what_put_it_there(
        tmp_path, fake_bwrap, tmp_unmasked):
    """CS-4 addendum 7, ruling 1, and the operator's decisions of 2026-10-28: in the run's own tree (the Lead's
    project, a worker's workspace) a tmpfs would make that level read-only, so a secret file there is masked by an
    empty file bound over it, as it is at the launch; a directory masked whole there is remounted read-only, so a
    write into it fails instead of vanishing; a path absent at the launch is not masked, as a mask would make it on the
    host. The launch line names each, with what put it there. Where the run only reads the project, the same file is
    left out of its directory."""
    home = tmp_path / "home"
    home.mkdir()
    real = os.path.realpath
    t = tmp_path / "lead"
    project = t / "repo"  # lead_layout's project, which is the Lead's workspace
    project.mkdir(parents=True)
    config, hidden, later, keys = (project / n for n in ("opencode.json", "deploy.env", "later.env", "keys"))
    config.write_text("{}\n")
    hidden.write_text("SYNTHETIC\n")
    keys.mkdir()
    layout = lead_layout(t, home=str(home), policy={"hide": [str(hidden), str(later), str(keys)]},
                         env={"HOME": str(home), "OPENCODE_CONFIG": str(config)})
    assert set(layout.hide_files) == {real(config), real(hidden)} and real(keys) in layout.hide_dirs
    assert set(layout.tree_masks) == {(real(config), "OPENCODE_CONFIG"), (real(hidden), "containment.hide"),
                                      (real(keys), "containment.hide")}, layout.tree_masks
    assert layout.tree_absent == ((real(later), "containment.hide"),)
    assert real(project) not in (*layout.left_out_of, *layout.hide_dirs) and not set(layout.left_out) & {
        real(config), real(hidden), real(later)}
    flags = C.bwrap_argv(layout, ["true"])
    assert flags[flags.index(real(config)) - 2:flags.index(real(config))] == ["--ro-bind", layout.mask_file]
    assert position(flags, "--remount-ro", real(keys)) > position(flags, "--tmpfs", real(keys))
    assert real(later) not in flags
    line = C.tree_masks_line(layout)
    assert line is not None and f"{real(config)} (OPENCODE_CONFIG)" in line and f"{real(keys)} (containment.hide)" \
        in line and "not there at launch, so not masked; if it appears during the session, the run sees it until the " \
        f"next launch: {real(later)} (containment.hide)" in line, line
    assert "A file the host replaces by rename, or first creates there, during the session is seen inside until the " \
        "next launch" in line and "edit it at your own terminal" in line and "an Include" in line
    assert layout.describe()["tree_masks"][0] == {"path": layout.tree_masks[0][0], "by": layout.tree_masks[0][1]}
    reader = run_layout(tmp_path / "r", "reviewer", home=str(home),
                        env={"HOME": str(home), "OPENCODE_CONFIG": str(tmp_path / "r" / "repo" / "opencode.json")})
    assert real(tmp_path / "r" / "repo" / "opencode.json") in reader.left_out and reader.tree_absent == ()
    repo, ws = repo_with_worktree(tmp_path / "worker")  # a worker's workspace is its own tree
    (ws / "deploy.env").write_text("SYNTHETIC\n")
    run = tmp_path / "worker" / "run"
    worker = C.for_run(role="implementer", scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "s"),
                       bridge_dir=None, policy={"hide": [str(ws / "deploy.env")]}, home=str(home), project=str(repo),
                       env={"HOME": str(home)})
    assert worker.tree_masks == ((real(ws / "deploy.env"), "containment.hide"),) and real(ws) not in worker.left_out_of


def test_a_policy_writable_root_that_holds_a_mask_is_refused_naming_it(tmp_path, fake_bwrap):
    """CS-4 addendum 7, ruling 2: a policy writable root is not the run's own tree. One that holds a mask is refused,
    naming it, whether the secret there is a file or a path left out as absent."""
    home = tmp_path / "home"
    home.mkdir()
    real = os.path.realpath
    root = tmp_path / "out"
    root.mkdir()
    (root / "token").write_text("SYNTHETIC\n")
    for secret in (root / "token", root / "not-yet"):
        with pytest.raises(ContainmentUnavailable, match="would let every contained run write") as exc:
            run_layout(tmp_path / secret.name, "implementer", home=str(home),
                       policy={"writable": [str(root)], "hide": [str(secret)]})
        assert {"what": "a containment.hide entry, a secret path left out of the sandbox whether or not it exists",
                "path": os.path.join(real(root), secret.name)} in exc.value.details["exposes"]


@pytest.mark.parametrize("cache", ["absent", "present"])
def test_a_writable_root_over_a_secret_names_what_the_secret_is_and_keeps_its_one_step(tmp_path, fake_bwrap, cache):
    """CS-4 addendum 8, ruling 1: the refusal of a policy writable root names each secret it would expose by what it
    is as well as by path, whether git's credential cache is absent (left out) or there (masked whole), and keeps the
    one step it gives. Quick check 4 of #283, m11: the step names the exact entry to list instead, a directory in the
    root that holds nothing protected, in the operator's own spelling, and the refusal applies to workers too."""
    home = tmp_path / "home"
    (home / ".cache" / "pip").mkdir(parents=True)
    secret = home / ".cache" / "git"
    if cache == "present":
        secret = secret / "credential"
        secret.mkdir(parents=True)
    raw = str(home / ".cache")
    with pytest.raises(ContainmentUnavailable, match="would let every contained run write") as exc:
        run_layout(tmp_path, "implementer", home=str(home), env={"HOME": str(home)}, policy={"writable": [raw]})
    kind = "a secret path left out of the sandbox whether or not it exists" if cache == "absent" else "a masked secret"
    assert {"what": f"git's credential cache, {kind}", "path": os.path.realpath(secret)} \
        in exc.value.details["exposes"], exc.value.details
    assert f"git's credential cache, {kind} ({os.path.realpath(secret)})" in exc.value.message
    assert "~/.cache/<tool>" in exc.value.message
    assert exc.value.details["instead"] == f"{raw}/pip"
    assert exc.value.message.endswith(f"in containment.writable in the execution policy: here, {raw + '/pip'!r} in "
                                      f"place of {raw!r}, or take {raw!r} out. This applies to every contained "
                                      "launch, workers included.")


def test_a_secret_that_cannot_be_left_out_of_its_directory_is_named_as_its_own_case(tmp_path, fake_bwrap,
                                                                                    monkeypatch):
    """Quick check 4 of #283, m9 (CS-4 addendum 8, ruling 2.1): a secret whose directory is ``/``, or one this account
    cannot list, cannot be left out of it: it takes a file mask where it exists, none where it is absent, and the
    launch line names it as its own case with its limit, never as the tree the run writes."""
    home = tmp_path / "home"
    home.mkdir()
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "token").write_text("SYNTHETIC\n")
    listing = os.scandir

    def scandir(path: Any = ".") -> Any:  # as for a directory with x but not r for this account
        if os.path.realpath(path) == os.path.realpath(locked):
            raise PermissionError(13, "Permission denied", str(path))
        return listing(path)

    monkeypatch.setattr(L.os, "scandir", scandir)
    top = os.path.abspath(os.sep + "aew-test-absent-under-the-root")
    layout = run_layout(tmp_path, "implementer", home=str(home),
                        policy={"hide": [str(locked / "token"), str(locked / "later"), top]})
    token, later = (os.path.join(os.path.realpath(locked), n) for n in ("token", "later"))
    assert layout.fixed_masks == ((token, "containment.hide"),) and token in layout.hide_files
    assert set(layout.fixed_absent) == {(later, "containment.hide"), (top, "containment.hide")}
    assert layout.tree_masks == layout.tree_absent == () and token not in layout.left_out
    absent = ("not there at launch, so not masked; if it appears during the session, the run sees it until the next "
              "launch")
    assert C.tree_masks_line(layout) == (
        "masked in place, read-only, as it cannot be left out of its directory (/, or one this account cannot list): "
        f"{token} (containment.hide); {absent}, as it cannot be left out of its directory (/, or one this account "
        f"cannot list): {', '.join(f'{p} (containment.hide)' for p, _ in layout.fixed_absent)}. A file replaced or "
        "first created there during the session is seen inside until the next launch; a write there by your own tools "
        "needs root, or a directory you cannot read")


def test_a_launch_over_bubblewraps_argument_limit_is_refused_before_it_starts(tmp_path, fake_bwrap, monkeypatch,
                                                                              tmp_unmasked):
    """CS-4 addendum 9 (quick check 4 of #283, m13): bubblewrap 0.4.0 takes at most 9,000 arguments, and each entry put
    back in a directory a secret is left out of takes three. Over the limit the launch is refused before bubblewrap
    starts, at the layout and at every start, naming each directory whose entries are put back, with how many, and the
    step: move entries out of the largest into a subdirectory."""
    assert L.BWRAP_MAX_ARGS == 9000
    home = tmp_path / "home"
    (home / ".config" / "app").mkdir(parents=True)
    for i in range(12):
        (home / f"entry-{i}").write_text("")
    layout = run_layout(tmp_path / "a", "implementer", home=str(home))
    count = len(C.bwrap_argv(layout, [], cwd="/w")) - 1
    monkeypatch.setattr(L, "BWRAP_MAX_ARGS", count - 1)
    with pytest.raises(ContainmentUnavailable, match="more than the") as exc:
        run_layout(tmp_path / "b", "implementer", home=str(home))
    real = os.path.realpath
    held = exc.value.details["put_back"]
    assert exc.value.details["reason"] == "bwrap_argument_limit" and exc.value.details["arguments"] == count
    assert list(held)[0] == real(home) and held[real(home)] >= 12 and held[real(home / ".config")] == 1
    assert f"{real(home)} ({held[real(home)]} entries), {real(home / '.config')} (1 entries)" in exc.value.message
    assert exc.value.message.endswith(f"To launch, move entries out of {real(home)} into a subdirectory, so it has "
                                      "fewer to put back. This applies to every contained launch, workers included")
    monkeypatch.setattr(L, "BWRAP_MAX_ARGS", count)  # at the limit the layout is made; one more argument is not run
    layout = run_layout(tmp_path / "c", "implementer", home=str(home))
    with pytest.raises(ContainmentUnavailable, match="bwrap|bubblewrap"):
        C.bwrap_argv(layout, ["true"], cwd="/w")


def test_every_secret_the_home_lists_says_what_it_is():
    """CS-4 addendum 8, ruling 1: a refusal names a secret by what it is, so each name the home's lists hold has its
    description, and none is described that the lists do not hold."""
    assert set(L.SECRET_WHAT) == {*L.SECRET_DIRS, *L.SECRET_FILES, *L.DISPLAY_FILES}
    assert all(L.SECRET_WHAT.values())


def test_a_layout_a_test_builds_from_the_hosts_own_home_fails_that_test(tmp_path, monkeypatch, fake_bwrap):
    """#283's CI at 59707278: a layout a test builds from the host's own HOME or XDG variables depends on that host's
    home. The suite's guard (tests/helpers/host_env.py) fails such a test, naming what came from the host; a synthetic
    launching environment passes."""
    import host_env

    monkeypatch.setattr(host_env, "HOST", {"HOME": "/host/home", "XDG_CONFIG_HOME": "/host/config", "PATH": "/bin"})
    monkeypatch.setenv("HOME", "/host/home")
    repo, ws = repo_with_worktree(tmp_path)
    run = tmp_path / "run"
    with pytest.raises(pytest.fail.Exception, match="built from the host's own HOME: pass env="):
        C.for_run(role="reviewer", scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "s"),
                  bridge_dir=None, policy=None, home=str(tmp_path / "home"), project=str(repo))
    with pytest.raises(pytest.fail.Exception, match="built from the host's own XDG_CONFIG_HOME"):
        L._launching(str(tmp_path / "home"), {"XDG_CONFIG_HOME": "/host/config"})
    assert L._launching(str(tmp_path / "home"), {"PATH": "/bin"}) == {"HOME": str(tmp_path / "home"), "PATH": "/bin"}


def test_every_test_module_that_builds_a_layout_takes_the_host_environment_guard():
    """#283's CI at 59707278 (the class of quick check 4's M3): a module whose tests build a containment layout
    themselves takes ``host_env.GUARDED`` in its ``pytestmark``, so none of its layouts reads the host's home."""
    builders = {"for_run", "_masks", "_mask_plan", "contained_layout", "scoring_layout"}
    tests = Path(__file__).resolve().parents[1]
    unguarded = []
    for path in sorted(tests.rglob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        builds = any(isinstance(n, ast.Call) and (getattr(n.func, "attr", None) or getattr(n.func, "id", None))
                     in builders for n in ast.walk(tree))
        marked = any(isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "pytestmark" for t in n.targets)
                     and "GUARDED" in (ast.get_source_segment(source, n.value) or "") for n in tree.body)
        if builds and not marked:
            unguarded.append(path.relative_to(tests).as_posix())
    assert unguarded == []


@pytest.mark.parametrize("inside", ["none", pytest.param("a_link", marks=pytest.mark.skipif(
    sys.platform == "win32", reason="making a symlink needs a privilege on Windows"))])
def test_every_directory_masked_over_the_run_is_named_in_one_refusal_with_each_variable_and_its_step(tmp_path,
                                                                                                   fake_bwrap, inside):
    """Quick check of #283 at c307481a, m4: where the operator's environment puts OpenCode's directories over more
    than one thing the run needs, or more than one variable puts them over one, the one refusal names each directory
    with every variable that puts it there, and each step; following it never meets a second refusal. A link inside a
    refused directory is not followed, so the refusal never names it (m6)."""
    real = os.path.realpath
    apart, together = tmp_path / "apart", tmp_path / "together"
    for base, env_of in ((apart, lambda h: {"XDG_DATA_HOME": str(apart), "XDG_CONFIG_HOME": str(h.parent)}),
                         (together, lambda h: {"XDG_DATA_HOME": str(together), "XDG_STATE_HOME": str(together)})):
        run_base = base / "opencode"  # the run's project is <run_base>/repo: in <XDG_DATA_HOME>/opencode
        home = tmp_path / f"h-{base.name}" / "opencode"  # apart: the home directory is <XDG_CONFIG_HOME>/opencode
        home.mkdir(parents=True)
        if inside == "a_link":
            run_base.mkdir(parents=True, exist_ok=True)
            elsewhere = tmp_path / f"elsewhere-{base.name}"
            elsewhere.mkdir()
            (run_base / "to-elsewhere").symlink_to(elsewhere, target_is_directory=True)
            (run_base / "to-root").symlink_to(Path(tmp_path.anchor), target_is_directory=True)
        with pytest.raises(ContainmentUnavailable) as exc:
            run_layout(run_base, "reviewer", home=str(home), env={"HOME": str(home), **env_of(home)})
        details, message = exc.value.details, exc.value.message
        assert details["reason"] == "mask_holds_the_run" and details["links"] == [], details
        assert "to-elsewhere" not in message and "to-root" not in message, message
        if base == apart:
            assert details["variables"] == ["XDG_DATA_HOME", "XDG_CONFIG_HOME"], details
            assert [(e["directory"], e["variables"]) for e in details["refused"]] == [
                (real(run_base), ["XDG_DATA_HOME"]), (real(home), ["XDG_CONFIG_HOME"])], details
            assert f"move the operator's OpenCode files from {real(run_base)} to " \
                f"{os.path.join(str(home), '.local', 'share', 'opencode')}, and unset XDG_DATA_HOME" in message
            assert f"XDG_CONFIG_HOME puts the operator's OpenCode files in {real(home)}" in message, message
            assert f"move the operator's OpenCode files from {real(home)} to " \
                f"{os.path.join(str(home), '.config', 'opencode')}, and unset XDG_CONFIG_HOME" in message, message
        else:
            assert [(e["directory"], e["variables"]) for e in details["refused"]] == [
                (real(run_base), ["XDG_DATA_HOME", "XDG_STATE_HOME"])], details
            assert "XDG_DATA_HOME and XDG_STATE_HOME put the operator's OpenCode files in" in message
            assert all(f"and unset {v}" in message for v in ("XDG_DATA_HOME", "XDG_STATE_HOME")), message
        assert message.endswith("This applies to every contained launch, workers included")


needs_symlinks = pytest.mark.skipif(sys.platform == "win32", reason="making a symlink needs a privilege on Windows, "
                                    "and containment is Linux's (bubblewrap); the checks are pure")

# Where the files the host reads sit when the operator's dotfile manager links them into OpenCode's directories: each
# directory's files in a directory of their own (as GNU stow's packages are), or all in one directory beside the
# operator's other dotfiles.
LINKED_FROM = ("own_directory", "beside_other_files")


@needs_symlinks
@pytest.mark.parametrize("placed", LINKED_FROM)
def test_every_file_the_host_reads_the_operators_opencode_from_is_masked_wherever_a_link_puts_it(tmp_path, fake_bwrap,
                                                                                               placed):
    """CB-01: the masks' class over the filesystem as well as the environment. In every environment of
    :data:`OPENCODE_ENVS`, each file the host reads (but the database, whose link the environment's own shapes cover)
    is a link to a file outside OpenCode's directories, and each is left out of its directory where it really is. So
    a flat dotfiles folder keeps its other files readable, and nothing is masked by an empty file."""
    real = os.path.realpath
    for shape, make in OPENCODE_ENVS.items():
        t = tmp_path / shape
        home = t / "home"
        env = make(t)
        host = {"HOME": str(home), **env}
        for variable in XDG_BASES:
            opencode_dir(host, variable).mkdir(parents=True, exist_ok=True)
        files = operator_files(host)
        files[0].parent.mkdir(parents=True, exist_ok=True)
        files[0].write_text("SYNTHETIC\n")
        dots = home / "dotfiles"
        dots.mkdir(parents=True)
        (dots / ".gitconfig").write_text("[user]\n")
        parents = list(dict.fromkeys(p.parent for p in files[4:]))
        for p in files[4:]:  # every file but the database and its sidecars
            target = dots / (str(parents.index(p.parent)) if placed == "own_directory" else "") / p.name
            target.parent.mkdir(exist_ok=True)
            target.write_text("SYNTHETIC\n")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.symlink_to(target)
        layout = run_layout(t, "reviewer", home=str(home), env=env)
        unmasked = [str(p) for p in files if not absent_inside(layout, p)]
        assert unmasked == [], (shape, layout.hide_dirs, layout.left_out)
        assert {real(p) for p in files[4:]} <= set(layout.left_out), shape
        assert not absent_inside(layout, dots / ".gitconfig") and layout.hide_files == (), shape
        assert (real(dots / ".gitconfig") in layout.put_back) == (placed == "beside_other_files"), shape


def role_layout(t: Path, role: str, home: Path) -> C.Layout:
    """``role``'s layout over ``home``: the Lead's in its project scope, any other role's in a Ticket's."""
    return lead_layout(t, home=str(home)) if role == "lead" else run_layout(t, role, home=str(home))


@needs_symlinks
def test_a_secret_a_masked_directory_links_to_is_left_out_of_its_directory_for_every_role(tmp_path, fake_bwrap):
    """CS-4 addendum 5's shapes under addendum 6, for every role. Two keys in ~/.ssh linked into a stow-style folder
    that holds only them (``~/dotfiles/ssh/.ssh``): each left out of that folder. The credentials in ~/.aws linked into
    a flat ``~/dotfiles`` that also holds ``.gitconfig``: the credentials left out, git's configuration put back. A
    directory in ~/.config/gh linked to a directory elsewhere: masked whole. A key in ~/.ssh linked into the project:
    left out of it where the run only reads the project, and where it writes it (the Lead's), masked by an empty file
    and named at launch (the operator's decision of 2026-10-28)."""
    real = os.path.realpath
    for role in sorted(L.WORKSPACE_ACCESS):
        t = tmp_path / role
        home = t / "home"
        stow, flat, hosts = home / "dotfiles" / "ssh" / ".ssh", home / "dotfiles", home / "vault" / "gh-hosts"
        for d in (home / ".ssh", home / ".aws", home / ".config" / "gh", stow, hosts, t / "repo"):
            d.mkdir(parents=True, exist_ok=True)
        for name in ("id_ed25519", "config"):
            (stow / name).write_text("SYNTHETIC\n")
            (home / ".ssh" / name).symlink_to(stow / name)
        (flat / "credentials").write_text("SYNTHETIC\n")
        (flat / ".gitconfig").write_text("[user]\n")
        (home / ".aws" / "credentials").symlink_to(flat / "credentials")
        (hosts / "github.com.yml").write_text("SYNTHETIC\n")
        (home / ".config" / "gh" / "hosts").symlink_to(hosts, target_is_directory=True)
        (t / "repo" / "deploy.key").write_text("SYNTHETIC\n")  # in the project the helpers make: <t>/repo
        (home / ".ssh" / "deploy").symlink_to(t / "repo" / "deploy.key")
        layout = role_layout(t, role, home)
        assert real(hosts) in layout.hide_dirs and real(stow) not in layout.hide_dirs, (role, layout.hide_dirs)
        assert {real(stow / "id_ed25519"), real(stow / "config"), real(flat / "credentials")} <= set(layout.left_out)
        assert real(flat / ".gitconfig") in layout.put_back, role
        key, link = real(t / "repo" / "deploy.key"), os.path.join(real(home / ".ssh"), "deploy")
        if role == "lead":
            assert layout.hide_files == (key,) and layout.tree_masks == ((key, f"the link {link}"),), layout.tree_masks
            assert key not in layout.left_out and f"{key} (the link {link})" in (C.tree_masks_line(layout) or "")
        else:
            assert key in layout.left_out and layout.tree_masks == () and C.tree_masks_line(layout) is None, role


@needs_symlinks
def test_a_linked_directory_is_masked_whole_at_its_target_and_the_links_in_it_are_followed(tmp_path, fake_bwrap):
    """A directory a masked directory links to is masked whole where it really is, and a link inside it is followed
    the same way."""
    home = tmp_path / "home"
    agents, keys = home / "dotfiles" / "agents", home / "keys"
    for d in (home / ".config" / "opencode", agents, keys):
        d.mkdir(parents=True)
    (keys / "auth.json").write_text("SYNTHETIC\n")
    (agents / "auth.json").symlink_to(keys / "auth.json")
    (home / ".config" / "opencode" / "agents").symlink_to(agents, target_is_directory=True)
    (home / ".config" / "opencode" / "keys").symlink_to(keys, target_is_directory=True)
    layout = run_layout(tmp_path, "reviewer", home=str(home))
    real = os.path.realpath
    assert {real(agents), real(keys)} <= set(layout.hide_dirs) and layout.tree_masks == (), layout.hide_dirs


@needs_symlinks
def test_a_link_target_absent_at_the_launch_is_left_out_so_one_made_later_is_not_seen(tmp_path, fake_bwrap):
    """A link's target is a named path: where it does not exist at the launch, its first component that does not
    exist yet is left out of its directory, so the operator's tool making it during the session (a first ``aws
    configure`` through a linked ~/.aws/credentials) is not seen inside."""
    home = tmp_path / "home"
    (home / ".aws").mkdir(parents=True)
    (home / "dotfiles").mkdir()
    (home / ".aws" / "credentials").symlink_to(home / "dotfiles" / "aws-credentials")  # dangling: made later
    (home / ".aws" / "config").symlink_to(home / "vault" / "aws" / "config")  # its directories too
    layout = run_layout(tmp_path, "reviewer", home=str(home))
    real = os.path.realpath
    assert {real(home / "dotfiles" / "aws-credentials"), real(home / "vault")} <= set(layout.left_out)
    assert real(home / "dotfiles") in layout.left_out_of and real(home) in layout.left_out_of


@needs_symlinks
def test_the_walk_of_links_ends_and_never_masks_or_walks_the_root_or_the_home_directory(tmp_path, fake_bwrap):
    """Quick check of #283 at 3ad586ed, m5: the walk of the links in a masked directory ends on a cycle of linked
    directories, a link to itself and a chain of links (each directory is walked once), and a link to ``/`` or to the
    home directory is refused, naming the link, so neither is masked whole or walked."""
    import threading

    real = os.path.realpath
    masked, d1, d2, files = (tmp_path / n for n in ("masked", "d1", "d2", "files"))
    for d in (masked, d1, d2, files):
        d.mkdir()
    (masked / "to-d1").symlink_to(d1, target_is_directory=True)
    (d1 / "to-d2").symlink_to(d2, target_is_directory=True)
    (d2 / "back").symlink_to(d1, target_is_directory=True)  # the cycle
    (d2 / "to-masked").symlink_to(masked, target_is_directory=True)
    (masked / "self").symlink_to(masked / "self")
    (files / "key").write_text("SYNTHETIC\n")
    (masked / "a").symlink_to(masked / "b")
    (masked / "b").symlink_to(d2 / "c")
    (d2 / "c").symlink_to(files / "key")  # a chain of three, from inside the cycle too
    out: list[Any] = []
    walk = threading.Thread(target=lambda: out.append(L._linked([real(masked)], [], skip=set())), daemon=True)
    walk.start()
    walk.join(timeout=10)
    assert not walk.is_alive(), "the walk of the links did not end"
    linked, targets, refused = out[0]
    assert {t for _, t in linked} == {real(d1), real(d2)} and refused == []
    assert {real(files / "key"), real(masked / "self")} <= {t for _, t in targets}
    for role in sorted(L.WORKSPACE_ACCESS):
        for name, to in (("root", Path(tmp_path.anchor)), ("home", None)):
            t = tmp_path / role / name
            home = t / "home"
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh" / "up").symlink_to(to or home, target_is_directory=True)
            with pytest.raises(ContainmentUnavailable) as exc:
                role_layout(t, role, home)
            assert exc.value.details["links"] == [os.path.join(real(home / ".ssh"), "up")], (role, name)
            assert exc.value.details["refused"][0]["directory"] == real(to or home), (role, name)


@needs_symlinks
def test_a_link_in_a_masked_directory_to_a_directory_the_run_needs_is_refused_naming_the_link(tmp_path, fake_bwrap):
    """For every role, a linked directory that is, or holds, something the run needs (here the project, which is the
    Lead's workspace, and the directory that holds it) is refused, naming the link and its step; with a variable's
    refusal, it is the one refusal naming both (m4)."""
    real = os.path.realpath
    for role in sorted(L.WORKSPACE_ACCESS):
        for to in ("repo", "."):  # is, and holds
            t = tmp_path / role / ("is" if to == "repo" else "holds")
            home = t / "home"
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh" / "proj").symlink_to(t / to, target_is_directory=True)  # the helper makes <t>/repo
            with pytest.raises(ContainmentUnavailable) as exc:
                role_layout(t, role, home)
            named = os.path.join(real(home / ".ssh"), "proj")
            what = "the workspace" if role == "lead" else "the project"
            assert exc.value.details["reason"] == "mask_holds_the_run" and exc.value.details["links"] == [named], role
            assert f"or holds {what} ({real(t / 'repo')})" in exc.value.message or to == ".", (role, exc.value.message)
            assert f"point {named} at a directory that holds nothing the run needs, or remove it" in exc.value.message
    base = tmp_path / "both" / "opencode"
    home = tmp_path / "both" / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "proj").symlink_to(base / "repo", target_is_directory=True)
    with pytest.raises(ContainmentUnavailable) as exc:
        run_layout(base, "reviewer", home=str(home),
                   env={"HOME": str(home), "XDG_DATA_HOME": str(tmp_path / "both")})
    assert exc.value.details["variables"] == ["XDG_DATA_HOME"], exc.value.details
    assert exc.value.details["links"] == [os.path.join(real(home / ".ssh"), "proj")]


@needs_symlinks
@pytest.mark.parametrize("variable", ["OPENCODE_DB", "OPENCODE_CONFIG"])
def test_a_file_opencode_names_through_a_link_is_left_out_where_the_link_and_its_target_are(tmp_path, fake_bwrap,
                                                                                           variable):
    """Quick check of #283 at c307481a, n3, under CS-4 addendum 6: where the variable names a link (to a file in the
    home directory or in a project the run only reads) or a path through a link to the home directory, the file is
    left out at the link and where it really is, and the launch goes ahead."""
    home = tmp_path / "home"
    home.mkdir()
    real = os.path.realpath
    name = {"OPENCODE_DB": "logins.db", "OPENCODE_CONFIG": "opencode.json"}[variable]
    for shape in ("file_link_into_home", "dir_link_to_home", "file_link_into_project"):
        base, links = tmp_path / shape, tmp_path / shape / "links"
        links.mkdir(parents=True)
        repo = base / "repo"  # run_layout's project
        if shape == "file_link_into_home":
            (home / name).write_text("SYNTHETIC\n")
            (links / name).symlink_to(home / name)
            named, at = links / name, home / name
        elif shape == "dir_link_to_home":
            (links / "d").symlink_to(home, target_is_directory=True)
            named, at = links / "d" / name, home / name
        else:
            (links / name).symlink_to(repo / name)
            named, at = links / name, repo / name
        layout = run_layout(base, "reviewer", home=str(home), env={"HOME": str(home), variable: str(named)})
        assert real(at) in layout.left_out and absent_inside(layout, named), (shape, layout.left_out)
        assert real(home) not in layout.hide_dirs and real(repo) not in layout.hide_dirs, shape


def test_the_launch_line_names_each_mask_in_the_runs_own_tree_with_what_put_it_there_and_the_limits():
    """CS-4 addendum 7, ruling 1: one launch line when the run's own tree holds a mask or a secret path absent at the
    launch, naming each with what put it there, what to do instead and the limits; none otherwise."""
    bare = C.Layout(role="x", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=())
    assert C.tree_masks_line(bare) is None and bare.describe()["tree_masks"] == []
    two = C.Layout(role="x", access="write", bwrap="/usr/bin/bwrap", writable=("/p",), readonly=(),
                   hide_files=("/p/a",), tree_masks=(("/p/a", "the link /h/.ssh/a"),),
                   tree_absent=(("/p/b", "containment.hide"),))
    assert C.tree_masks_line(two) == (
        "masked in place, read-only, in the tree this run writes: /p/a (the link /h/.ssh/a); not there at launch, so "
        "not masked; if it appears during the session, the run sees it until the next launch: /p/b (containment.hide). "
        "A file the host replaces by rename, or first creates there, during the session is seen inside until the next "
        "launch. To change one, edit it at your own terminal, or keep the real file outside that tree (for ssh, an "
        "Include from your real ~/.ssh/config)")


def test_a_workers_containment_event_carries_the_launch_line_of_the_masks_in_its_workspace(tmp_path, monkeypatch):
    """Quick check of #283 at 3ad586ed, m5: a worker's supervisor records the launch line on its ``containment`` event
    when its workspace holds a mask, and nothing when it holds none."""
    from types import SimpleNamespace

    from aew.harness import supervisor

    masks = ((str(tmp_path / "ws" / "deploy.env"), "containment.hide"),)
    label = {"filesystem": "os_readonly_roots", "process_ownership": "tree", "network": {"mode": L.SHARED}}
    monkeypatch.setattr(procs, "ProcessTree", lambda **_: None)
    contract = SimpleNamespace(role="implementer", scope="ticket", workspace=str(tmp_path / "ws"),
                               scratch=str(tmp_path / "s"), extra={})
    for tree_masks in (masks, ()):
        layout = C.Layout(role="implementer", access="write", bwrap="/usr/bin/bwrap",
                          writable=(str(tmp_path / "ws"),), readonly=(), tree_masks=tree_masks)
        monkeypatch.setattr(C, "establish", lambda layout=layout, **_: (layout, dict(label)))
        events: list[tuple[str, dict[str, Any]]] = []
        engine = SimpleNamespace(execution_policy=lambda: ({}, None), repo_root=tmp_path / "repo")
        worker = SimpleNamespace(engine=engine, run_dir=tmp_path / "r",
                                 bridge=SimpleNamespace(private_dir=None, address="a"), record={}, layout=None,
                                 tree=None, _event=lambda kind, out=events, **fields: out.append((kind, fields)))
        supervisor.Supervisor._contain(worker, contract, SimpleNamespace(EGRESS=(), PROVIDER_RELAY=False))
        assert [kind for kind, _ in events] == ["containment"]
        if tree_masks:
            line = events[0][1]["tree_masks"]
            assert line == C.tree_masks_line(layout) and str(tmp_path / "ws" / "deploy.env") in line
        else:
            assert "tree_masks" not in events[0][1]


def test_a_directory_a_secret_is_left_out_of_is_masked_at_its_depth_with_its_other_entries_put_back_then_read_only():
    """CS-4 addendum 6, ruling 3's order: the directory's tmpfs comes before every mount under it, ancestors first (the
    project under the home directory comes after it); each other entry is put back a level below as --ro-bind-try,
    links as links; an entry the layout binds or masks itself is not put back (its own bind takes its place); a
    directory masked whole is masked after the put-backs, and every remount comes last. One hidden with a tree the
    sandbox masks whole (``/tmp``) is not masked, nor are its entries put back, which would bring the host's back."""
    layout = C.Layout(role="lead", access="write", bwrap="/usr/bin/bwrap", writable=("/h/proj",),
                      readonly=("/h/proj/.aew",), visible=("/h/proj",), hide_dirs=("/h/.ssh",),
                      left_out=("/h/.netrc", "/h/.config/git", "/tmp/x/xauth"),
                      left_out_of=("/h", "/h/.config", "/tmp/x"),
                      put_back=("/h/.profile", "/h/proj", "/h/.ssh", "/h/.config/app", "/tmp/x/other"),
                      put_back_links=(("/h/.gitconfig", "dotfiles/gitconfig"),), hide_host=(), run_exceptions=())
    flags = C.bwrap_argv(layout, ["true"])
    at = {name: position(flags, flag, path) for name, flag, path in (
        ("home", "--tmpfs", "/h"), ("config", "--tmpfs", "/h/.config"), ("profile", "--ro-bind-try", "/h/.profile"),
        ("app", "--ro-bind-try", "/h/.config/app"), ("project", "--ro-bind", "/h/proj"),
        ("bind", "--bind", "/h/proj"), ("ssh", "--tmpfs", "/h/.ssh"), ("ro_home", "--remount-ro", "/h"),
        ("ro_config", "--remount-ro", "/h/.config"))}
    at["link"] = flags.index("/h/.gitconfig") - 2  # --symlink TARGET PATH
    assert at["home"] < at["profile"] < at["config"] < at["app"] and at["home"] < at["link"] < at["project"]
    assert flags[at["link"]:at["link"] + 2] == ["--symlink", "dotfiles/gitconfig"] and at["project"] < at["bind"]
    assert at["bind"] < at["ssh"]
    assert at["ssh"] < at["ro_home"] and at["ssh"] < at["ro_config"] and at["bind"] < at["ro_home"]
    assert "/h/proj" not in pairs(flags, "--ro-bind-try") and "/h/.ssh" not in pairs(flags, "--ro-bind-try")
    assert "/tmp/x" not in (*pairs(flags, "--tmpfs"), *pairs(flags, "--remount-ro")) and "/tmp/x/other" not in flags
    assert ("--ro-bind-try", "/h/.profile") in L.order(layout) and ("--ro-bind", "/h/.profile") not in L.order(layout)
    assert layout.describe()["left_out_of"] == ["/h", "/h/.config", "/tmp/x"]
    assert set(layout.left_out) <= set(layout.describe()["hidden"])


def test_left_out_names_the_first_component_that_does_not_exist_below_a_directory(tmp_path):
    """CS-4 addendum 6: a named path is left out whether or not it exists. The first of its components that does not
    exist yet is left out of its deepest existing ancestor, at that ancestor's real path; nothing where that ancestor
    is a file, as nothing can be made below it."""
    real = os.path.realpath
    (tmp_path / "a").mkdir()
    (tmp_path / "f").write_text("x")
    (tmp_path / "a" / "there").write_text("x")
    assert L._left_out(str(tmp_path / "a" / "there")) == [os.path.join(real(tmp_path / "a"), "there")]
    assert L._left_out(str(tmp_path / "a" / "b" / "c" / "d")) == [os.path.join(real(tmp_path / "a"), "b")]
    assert L._left_out(str(tmp_path / "f" / "below")) == []


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
