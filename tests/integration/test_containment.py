"""OS filesystem containment and process ownership on Linux (F2, E13; M4-B).

Every test builds a real role layout and runs real processes in it through ``ProcessTree(layout=...)``, the same
choke point a harness run and its checks use. The host paths these tests attack live outside ``/tmp`` (the sandbox
has a private ``/tmp``), so each attack meets the host's file, made read-only, and each test checks both that the
attempt failed and that the host is byte-identical afterwards.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import layout as L
from aew.harness.containment import probe, sockets

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                reason="Linux bubblewrap containment (Windows: workdir separation only)")

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


@pytest.fixture
def visible(tmp_path):
    """A directory the sandbox sees as the host's (not under /tmp)."""
    base = Path(os.environ.get("AEW_CONTAINMENT_TEST_DIR") or Path.home() / ".aew-test-tmp")
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="contain-", dir=base))
    try:
        yield root
    finally:
        for p in root.rglob("*"):  # git makes objects read-only
            try:
                p.chmod(0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV, **(env or {})})


class Lab:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.repo.mkdir()
        assert git("init", "-q", cwd=self.repo).returncode == 0
        (self.repo / "f.txt").write_text("base\n")
        git("add", "f.txt", cwd=self.repo)
        assert git("commit", "-q", "-m", "base", cwd=self.repo).returncode == 0
        self.ws = root / "ws"
        self.other = root / "other-ws"
        for path, branch in ((self.ws, "w"), (self.other, "o")):
            assert git("worktree", "add", "-q", "-b", branch, str(path), cwd=self.repo).returncode == 0
        (Path(git("rev-parse", "--git-dir", cwd=self.ws).stdout.strip()) / "aew-workspace.yaml").write_text("m: 1\n")
        self.outside = root / "outside"
        self.outside.mkdir()
        (self.outside / "protected.txt").write_text("protected\n")
        self.home = root / "home"
        (self.home / ".ssh").mkdir(parents=True)
        (self.home / ".ssh" / "id_key").write_text("SECRET-KEY\n")
        (self.home / ".netrc").write_text("machine m login l password SECRET-NETRC\n")
        self.run = root / "runs" / "R-1"  # like a harness run: its parent, every run's directory, is hidden

    def layout(self, role: str = "implementer", **kw) -> C.Layout:
        self.run.mkdir(parents=True, exist_ok=True)
        return C.for_run(role=role, scope=kw.pop("scope", "ticket"), workspace=str(self.ws), run_dir=self.run,
                         scratch=str(self.run / "scratch"), bridge_dir=None, policy=kw.pop("policy", None),
                         home=str(self.home), project=str(self.repo), runs=str(self.run.parent))

    def sh(self, layout: C.Layout, script: str, *, cwd: Path | None = None,
           env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=str(cwd or self.ws), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8",
                                   **layout.env, **(env or {})})
            out, err = proc.communicate(timeout=60)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            tree.close()

    def fingerprint(self) -> dict[str, str]:
        """Every host file outside the writable roots, by content (the real git metadata included)."""
        out = {}
        skip = (self.run, self.ws)
        for p in sorted(self.root.rglob("*")):
            if any(p == s or s in p.parents for s in skip) and p != self.ws / ".git":
                continue
            if p.is_file() and not p.is_symlink():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
            elif p.is_dir():
                out[str(p)] = "dir"
        out["ws/.git"] = hashlib.sha256((self.ws / ".git").read_bytes()).hexdigest()
        return out


@pytest.fixture
def lab(visible):
    return Lab(visible)


# ------------------------------------------------------------------ isolation design §12: one test per item

ESCAPES = {
    "absolute_path": "cp f.txt {outside}/abs.txt",
    "dotdot": "printf x > ../outside/dotdot.txt",
    "symlink": "ln -s {outside} link && printf x > link/via-link.txt",
    "rename_out": "mv f.txt {outside}/moved.txt",
    "mkdir": "mkdir {outside}/newdir",
    "temp_outside_scratch": "printf x > /var/tmp/aew-contain-$$ && printf x > {home}/tmpfile",
    "python_open": "{python} -c \"open('{outside}/py.txt', 'w').write('x')\"",
    "shell_redirect": "printf x >> {outside}/protected.txt",
    "another_worktree": "printf x >> {other}/f.txt",
}


@pytest.mark.parametrize("attack", sorted(ESCAPES))
def test_an_escape_fails_at_the_os_and_leaves_the_host_unchanged(lab, attack):
    layout = lab.layout()
    before = lab.fingerprint()
    script = ESCAPES[attack].format(outside=lab.outside, other=lab.other, home=lab.home, python=sys.executable)
    done = lab.sh(layout, f"test -r {lab.outside}/protected.txt || exit 99; {script}")
    assert done.returncode not in (0, 99), (attack, done.stdout, done.stderr)  # visible to the sandbox, yet refused
    assert "Read-only file system" in done.stderr or "Permission denied" in done.stderr, done.stderr
    assert lab.fingerprint() == before
    assert not list(Path("/var/tmp").glob("aew-contain-*"))


def test_the_role_can_still_write_its_own_roots(lab):
    layout = lab.layout()
    done = lab.sh(layout, f"printf ok > new.txt && printf ok > {lab.run}/scratch/report.md && printf ok > /tmp/t")
    assert done.returncode == 0, done.stderr
    assert (lab.ws / "new.txt").read_text() == "ok" and (lab.run / "scratch" / "report.md").read_text() == "ok"


def test_the_agent_cannot_write_its_live_usage(lab):
    """The run's live usage file sits at the run root, outside what the sandbox binds back (scratch, harness, git):
    the agent can neither replace nor remove the host's copy (F25 for M4-H, slice L2)."""
    layout = lab.layout()
    lab.run.mkdir(parents=True, exist_ok=True)
    live = lab.run / "usage.live.json"
    live.write_text('{"schema": "aew/usage-live/v1", "seq": 3}')
    before = live.read_bytes()
    done = lab.sh(layout, f"printf x > {live}; rm -f {live}; printf x > {lab.run}/usage.live.state.json; true")
    assert done.returncode == 0, done.stderr
    assert live.read_bytes() == before
    assert not (lab.run / "usage.live.state.json").exists()


def test_secrets_are_hidden_and_a_masked_file_is_still_a_file(lab):
    done = lab.sh(lab.layout(), f"ls -A {lab.home}/.ssh; cat {lab.home}/.netrc; test -f {lab.home}/.netrc && echo FILE")
    assert done.returncode == 0, done.stderr
    assert "SECRET" not in done.stdout and "id_key" not in done.stdout
    assert done.stdout.strip() == "FILE"


def test_provider_config_locations_read_empty_from_inside(lab):
    (lab.home / ".claude.json").write_text('{"secret": "SECRET-CFG"}\n')
    (lab.home / ".config" / "anthropic").mkdir(parents=True)
    (lab.home / ".config" / "anthropic" / "credentials").write_text("SECRET-DIR\n")
    (lab.home / ".claude.json.backup").write_text('{"secret": "SECRET-COPY"}\n')
    f, d = lab.home / ".claude.json", lab.home / ".config" / "anthropic"
    b = lab.home / ".claude.json.backup"
    done = lab.sh(lab.layout("reviewer"), f"cat {f} {b}; test -f {f} && test ! -s {f} && echo FILE; "
                                          f"test -f {b} && test ! -s {b} && echo COPY; ls -A {d}; echo END")
    assert done.returncode == 0, done.stderr
    assert "SECRET" not in done.stdout and "credentials" not in done.stdout
    assert done.stdout.split() == ["FILE", "COPY", "END"]
    assert f.read_text() == '{"secret": "SECRET-CFG"}\n'  # the host's own file is untouched


def test_another_runs_harness_state_is_invisible(lab):
    """Independent review (area 2, F2): a run must not read a sibling run's harness state, where OpenCode keeps that
    run's session environment (its bridge key). Every run's directory is hidden; only this run's own come back."""
    sibling = lab.run.parent / "R-0" / "harness"
    sibling.mkdir(parents=True)
    (sibling / "session.db").write_text("AEW_AGENT_KEY=sibling-key")
    layout = lab.layout("reviewer")
    runs = lab.sh(layout, f"ls -A {lab.run.parent}")
    assert runs.returncode == 0 and runs.stdout.split() == ["R-1"]  # only its own run's mount points
    read = lab.sh(layout, f"cat {sibling}/session.db")
    assert read.returncode != 0 and "sibling-key" not in read.stdout and "No such file" in read.stderr
    own = lab.sh(layout, f"ls -A {lab.run}")
    assert {"harness", "scratch"} <= set(own.stdout.split())  # its own directories are bound back
    assert lab.sh(layout, f"test -r {lab.repo}/f.txt").returncode == 0  # the project itself stays visible


def test_a_reviewer_cannot_write_its_workspace_but_can_write_scratch(lab):
    layout = lab.layout("reviewer")
    before = (lab.ws / "f.txt").read_text()
    denied = lab.sh(layout, "printf x >> f.txt")
    assert denied.returncode != 0 and "Read-only file system" in denied.stderr
    assert (lab.ws / "f.txt").read_text() == before
    ok = lab.sh(layout, f"printf ok > {lab.run}/scratch/review.md && {sys.executable} -c 'import json'")
    assert ok.returncode == 0, ok.stderr


# ------------------------------------------------------------------ git metadata: the confused-deputy tests

def test_the_real_git_metadata_is_immutable_from_inside(lab):
    layout = lab.layout()
    gitdir = Path(git("rev-parse", "--git-dir", cwd=lab.ws).stdout.strip())
    common = lab.repo / ".git"
    before = lab.fingerprint()
    head_before = git("rev-parse", "HEAD", cwd=lab.ws).stdout
    attacks = [
        "printf 'gitdir: /elsewhere\\n' > .git",
        f"printf 0000000000000000000000000000000000000000 > {gitdir}/HEAD",
        f"printf /elsewhere > {gitdir}/commondir",
        f"printf /elsewhere > {gitdir}/gitdir",
        f"printf x > {gitdir}/aew-workspace.yaml",
        f"printf x > {gitdir}/index",
        f"printf x > {common}/config",
        "printf x >> f.txt && git add f.txt && git commit -q -m sneaky",
        "git checkout -q --detach",
        "git branch sneaky",
        "git update-ref refs/heads/sneaky HEAD",
        "git stash",
        f"git --git-dir={common} update-ref refs/heads/w HEAD~0",
    ]
    for attack in attacks:
        done = lab.sh(layout, attack)
        assert done.returncode != 0, (attack, done.stdout, done.stderr)
    after = lab.fingerprint()
    assert after == before
    assert git("rev-parse", "HEAD", cwd=lab.ws).stdout == head_before
    assert git("branch", "--list", "sneaky", cwd=lab.repo).stdout == ""
    # The host side still acts on the identity the agent could not alter, and needs no alternates.
    assert git("status", "--porcelain", cwd=lab.ws).stdout.strip() == "M f.txt"  # the content change is the product
    assert git("fsck", "--no-progress", cwd=lab.repo).returncode == 0


def test_the_role_packs_git_commands_work_on_the_private_index_and_store(lab):
    layout = lab.layout()
    real_index = (Path(git("rev-parse", "--git-dir", cwd=lab.ws).stdout.strip()) / "index").read_bytes()
    done = lab.sh(layout, "printf more >> f.txt && printf new > g.txt && git status --porcelain && git diff --stat "
                          "&& git add f.txt g.txt && git diff --cached --name-only && git hash-object -w g.txt "
                          "&& git log --oneline -1")
    assert done.returncode == 0, done.stderr
    assert "f.txt" in done.stdout and "g.txt" in done.stdout
    assert (Path(git("rev-parse", "--git-dir", cwd=lab.ws).stdout.strip()) / "index").read_bytes() == real_index
    assert any((lab.run / "git" / "objects").rglob("*"))  # staged objects went to the private store
    assert git("fsck", "--no-progress", cwd=lab.repo).returncode == 0
    C.retire_private_git(lab.run)
    assert not (lab.run / "git").exists()
    assert git("status", "--porcelain", cwd=lab.ws).returncode == 0


# ------------------------------------------------------------------ the launch self-test

def test_the_self_test_passes_the_real_layout_and_fails_a_writable_root_laid_over_the_host(lab):
    good = lab.layout()
    assert probe.self_test(good, sentinel_dir=lab.outside, sibling_dir=lab.root)["ok"] is True
    broken = dataclasses.replace(good, writable=(*good.writable, "/"))  # a broad writable bind over everything
    result = probe.self_test(broken, sentinel_dir=lab.outside, sibling_dir=lab.root)
    assert result["ok"] is False and "outside the writable roots" in result["reason"]
    unprotected = dataclasses.replace(good, readonly=())  # the .git pointer left writable inside the source
    result = probe.self_test(unprotected, sentinel_dir=lab.outside, sibling_dir=lab.root)
    assert result["ok"] is False and str(lab.ws / ".git") in result["reason"]
    assert lab.fingerprint() == lab.fingerprint()  # the probes left nothing behind
    assert not list(lab.root.glob(".aew-containment-probe-*"))


UNSAFE_ROOTS = ("project", "tmp", "aew_tmp", "runs", "home", "workspaces", "python")


@pytest.mark.parametrize("which", UNSAFE_ROOTS)
def test_an_operator_root_that_reaches_what_containment_protects_is_refused(lab, which):
    """M4-B review (Fable F1): a containment.writable root over the project, /tmp, the runs directory, a masked
    secret, other workspaces or the Python environment would leave the run labelled contained while it can write
    control state, evidence, other runs' bridge credentials or AEW itself. Refused, naming what it would expose."""
    (lab.repo / ".aew" / "state").mkdir(parents=True)
    other_bridge = Path(tempfile.mkdtemp(prefix="aew-bridge-"))  # another run's, in the shared temporary directory
    root = {"project": lab.repo, "tmp": Path(tempfile.gettempdir()), "aew_tmp": other_bridge, "runs": lab.run.parent,
            "home": lab.home, "workspaces": lab.root, "python": Path(sys.prefix)}[which]
    lab.run.mkdir(parents=True, exist_ok=True)
    with pytest.raises(C.ContainmentUnavailable, match="would let every contained run write") as refused:
        lab.layout(policy={"writable": [str(root)]})
    assert "List a narrower directory" in refused.value.message and refused.value.details["exposes"]
    other_bridge.rmdir()


def test_a_narrow_operator_root_is_accepted_and_the_layout_stays_contained(lab):
    (lab.repo / ".aew" / "state").mkdir(parents=True)
    build = lab.repo / "build"
    build.mkdir()
    layout = lab.layout(policy={"writable": [str(build)]})
    assert os.path.realpath(build) in layout.writable
    assert probe.self_test(layout, sentinel_dir=lab.outside, sibling_dir=lab.root)["ok"] is True


@pytest.mark.parametrize("reach", ["control_state", "host_tmp", "sibling_run"])
def test_the_self_test_fails_a_layout_that_reaches_control_state_tmp_or_another_run(lab, reach):
    """Whatever widened the layout (an operator root, a future bug), reaching these fails the launch self-test. A
    writable bind of the runs directory itself no longer shows the other runs: the mask on that path comes after it and
    is remounted read-only (review of #231, m2 and m5), so the widened root is unwritable from inside, which fails the
    self-test too."""
    (lab.repo / ".aew" / "state").mkdir(parents=True)
    good = lab.layout()
    extra, expected = {"control_state": (str(lab.repo), ".aew"), "host_tmp": ("/tmp", ".tmp-marker"),
                       "sibling_run": (str(lab.run.parent), "is not writable on the host from inside")}[reach]
    result = probe.self_test(dataclasses.replace(good, writable=(*good.writable, extra)), sentinel_dir=lab.outside,
                             sibling_dir=lab.root)
    assert result["ok"] is False and expected in result["reason"], result
    assert not list(lab.run.parent.glob("*.probe-run"))
    # this probe's own markers only: tests running alongside have probes of their own in the shared /tmp
    assert not list(Path(tempfile.gettempdir()).glob(f"{result['probe']}*"))


def test_launch_fails_closed_without_bubblewrap_unless_the_policy_allows_weaker(lab, monkeypatch):
    monkeypatch.setenv("PATH", str(lab.root / "empty"))
    args = dict(role="implementer", scope="ticket", workspace=str(lab.ws), run_dir=lab.run,
                scratch=str(lab.run / "scratch"), bridge_dir=None, project=str(lab.repo))
    with pytest.raises(C.ContainmentUnavailable, match="bubblewrap"):
        C.establish(**args, policy=None)
    layout, label = C.establish(**args, policy={"containment": {"mode": "allow_weaker"}})
    assert layout is None and label["filesystem"] == "workdir_separation_only"
    assert "bubblewrap" in label["weaker_because"] and not (lab.run / "git").exists()


def test_establish_labels_a_contained_run_truthfully(lab):
    layout, label = C.establish(role="reviewer", scope="ticket", workspace=str(lab.ws), run_dir=lab.run,
                                scratch=str(lab.run / "scratch"), bridge_dir=None, policy=None,
                                project=str(lab.repo))
    assert layout is not None
    assert label["filesystem"] == "os_readonly_roots" and label["process_ownership"] == "pid_namespace"
    assert label["network"] == "shared" and label["mechanism"].startswith("bubblewrap")
    assert label["self_test"]["ok"] is True and label["layout"]["workspace_access"] == "read"


# ------------------------------------------------------------------ process ownership (E13)

def _wait_file(path: Path, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return path.read_text()
        time.sleep(0.05)
    raise AssertionError(f"{path} never written")


def _session(pid: int) -> int:
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[3])


@pytest.mark.parametrize("escape", ["setsid", "double_fork"])
def test_killing_the_tree_ends_every_process_even_one_that_left_the_group(lab, escape):
    """And under bubblewrap's --new-session (STG-05 CB-05), the contained command leads a session of its own, outside
    the tree's process group, and the kill still ends it: the PID namespace ends with bubblewrap."""
    layout = lab.layout()
    pidfile, topfile = lab.run / "scratch" / "pids", lab.run / "scratch" / "top"
    start = ("setsid sleep 300 & echo $! > {f}; wait" if escape == "setsid"
             else "(sleep 300 & echo $! > {f}) ; sleep 300").format(f=pidfile)
    tree = procs.ProcessTree(layout=layout)
    proc = tree.spawn(["sh", "-c", f"echo $$ > {topfile}; {start}"], cwd=str(lab.ws), stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"]})
    ns_pid = int(_wait_file(pidfile).split()[0])
    host = procs.host_pid(ns_pid, under=proc.pid)
    assert host != ns_pid  # it lives in the run's PID namespace
    top = procs.host_pid(int(_wait_file(topfile).split()[0]), under=proc.pid)
    assert _session(top) != os.getpgid(proc.pid)  # the command's own session, not the tree's group
    watches = [procs.Watch(host), procs.Watch(top)]
    assert all(w.alive() for w in watches)
    tree.kill()
    deadline = time.monotonic() + 15
    while any(w.alive() for w in watches) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not any(w.alive() for w in watches)
    tree.close()
    for w in watches:
        w.close()


def _descendants(root: int) -> list[tuple[int, list[int]]]:
    """(host pid, NSpid) of every process under ``root``."""
    out = []
    for entry in os.listdir("/proc"):
        if entry.isdigit() and procs._descends(int(entry), root) and int(entry) != root:
            try:
                out.append((int(entry), procs._nspid(entry)))
            except OSError:
                pass
    return out


def test_host_pid_reads_the_runs_namespace_level_and_never_guesses(lab):
    """M4-B review (Fable F2): a pid is read at the run's namespace level, so a process the agent started in a
    further nested sandbox translates to its own host pid; a pid nothing under the run has raises instead of coming
    back as if it were a host pid."""
    layout = lab.layout()
    nested = "bwrap --ro-bind / / --dev /dev --proc /proc --unshare-pid sleep 300"
    tree = procs.ProcessTree(layout=layout)
    proc = tree.spawn(["sh", "-c", f"{nested} & sleep 300"], cwd=str(lab.ws), stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"]})
    try:
        deadline = time.monotonic() + 30
        deep: list[tuple[int, list[int]]] = []
        while not deep and time.monotonic() < deadline:
            depth = len(procs._nspid(proc.pid))
            deep = [(h, ids) for h, ids in _descendants(proc.pid) if len(ids) == depth + 2]
            time.sleep(0.1)
        if not deep:
            pytest.skip("nested PID namespaces are not available inside the sandbox on this host")
        host, ids = deep[-1]
        assert procs.host_pid(ids[depth], under=proc.pid) == host  # what the agent sees, placed correctly
        shallow = [(h, ids) for h, ids in _descendants(proc.pid) if len(ids) == depth + 1]
        h1, ids1 = shallow[0]
        assert procs.host_pid(ids1[depth], under=proc.pid) == h1
        with pytest.raises(LookupError):
            procs.host_pid(4_000_000, under=proc.pid)
    finally:
        tree.kill()


def test_sigkill_of_bubblewrap_ends_the_namespace(lab):
    layout = lab.layout()
    pidfile = lab.run / "scratch" / "pid"
    tree = procs.ProcessTree(layout=layout)
    proc = tree.spawn(["sh", "-c", f"setsid sleep 300 & echo $! > {pidfile}; wait"], cwd=str(lab.ws),
                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                      env={"PATH": os.environ["PATH"]})
    watch = procs.Watch(procs.host_pid(int(_wait_file(pidfile)), under=proc.pid))
    os.kill(proc.pid, signal.SIGKILL)  # only bubblewrap's own host process
    deadline = time.monotonic() + 15
    while watch.alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not watch.alive()
    tree.close()
    watch.close()


_OWNER = """
import subprocess, sys, time
from aew.harness import containment, procs
from pathlib import Path
layout = containment.for_run(role="implementer", scope="ticket", workspace=sys.argv[1], run_dir=Path(sys.argv[2]),
                             scratch=sys.argv[2] + "/scratch", bridge_dir=None, policy=None, home=sys.argv[3],
                             project=sys.argv[4])
tree = procs.ProcessTree(layout=layout)
p = tree.spawn(["sh", "-c", "setsid sleep 300 & echo $! > " + sys.argv[2] + "/scratch/pid; wait"], cwd=sys.argv[1],
               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.pid, flush=True)
time.sleep(300)
"""


def test_sigkill_of_the_owner_ends_the_contained_tree(lab):
    owner = subprocess.Popen([sys.executable, "-c", _OWNER, str(lab.ws), str(lab.run), str(lab.home), str(lab.repo)],
                             stdout=subprocess.PIPE, text=True, start_new_session=True)
    try:
        bwrap_pid = int(owner.stdout.readline())
        watch = procs.Watch(procs.host_pid(int(_wait_file(lab.run / "scratch" / "pid")), under=bwrap_pid))
        assert watch.alive()
        owner.kill()  # the supervisor's death: the sentinel and --die-with-parent take the tree
        owner.wait(10)
        deadline = time.monotonic() + 15
        while watch.alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not watch.alive()
        watch.close()
    finally:
        if owner.poll() is None:
            owner.kill()


# ------------------------------------------------------------------ contained checks

def test_a_check_runs_inside_the_runs_layout(lab):
    from aew.policy import checks

    layout = lab.layout("reviewer")
    cfg = {"command": ["sh", "-c", f"printf x >> {lab.outside}/protected.txt; printf x >> f.txt; echo done"],
           "timeout_s": 60}
    before = lab.fingerprint()
    result = checks.run(cfg, lab.ws, env={"PATH": os.environ["PATH"], **layout.env}, layout=layout)
    assert "Read-only file system" in result["log"] and "done" in result["log"]
    assert lab.fingerprint() == before and (lab.ws / "f.txt").read_text() == "base\n"


# ------------------------------------------------------------------ STG-05: the store and the control lock (CBF-1)

def aew_project(lab: Lab) -> Path:
    """Make the lab's repository an AEW project (its store, its `.aew/local` and the control lock), as `aew init`."""
    from aew.engine.api import Engine

    Engine.initialize(lab.repo, project_id="lab")
    assert (lab.repo / ".aew" / "local" / "control.lock").exists()
    return lab.repo / ".aew"


def test_from_a_worker_sandbox_the_control_lock_is_not_there_and_none_can_be_made(lab):
    """Inside, `.aew/local` is an empty tmpfs, remounted read-only once the run's own directories are bound back into
    it (review of #231, m5): the host's lock is absent, a process cannot make a lock of its own there (EROFS), and the
    run's own harness directory, bound back into the mask, stays writable."""
    from aew.engine.lock import FileLock
    from aew.engine.store import LOCK_REL

    aew = aew_project(lab)
    lab.run = aew / "local" / "harness" / "runs" / "R-1"  # where a harness run's directory is: inside the mask
    layout = lab.layout("reviewer")
    harness = lab.run / "harness"
    probe = (f"test -e {aew / LOCK_REL} && echo present || echo absent; "
             f"{sys.executable} -c \"import errno\ntry:\n    open('{aew / LOCK_REL}', 'a+')\n    print('made')\n"
             f"except OSError as e:\n    print(errno.errorcode[e.errno])\"; "
             f"echo x > {harness / 'w'} && echo harness-writable")
    res = lab.sh(layout, probe)
    assert res.stdout.split() == ["absent", "EROFS", "harness-writable"], res.stdout + res.stderr
    with FileLock(aew / LOCK_REL, timeout=5):  # the engine's own lock, on the host, untouched
        pass


_NON_WRITER_READS = """
import json, os, sys
from aew import process_kind
from aew.engine import configuration, outbox
from aew.engine.base import Kernel
from aew.errors import PermissionDenied

process_kind.declare(process_kind.cli_entry_point(["status"], os.environ))
k = Kernel(*Kernel.locate(__import__("pathlib").Path(sys.argv[1])))
state = k.store.read_committed()
since = (state.get("outbox") or {}).get("since", 0)
out = {"kind": process_kind.kind(), "revision": state["revision"],
       "manifest": configuration.read_committed(k).manifest_raw is not None,
       "records": len(list(outbox.read_transitions(k.aew_root, since, state["revision"], outbox=state.get("outbox")))),
       "segment": outbox.LogView(k.aew_root, since).segment(0) is None}
try:
    k.store.read()
except PermissionDenied as exc:
    out["locked_read"] = exc.details["reason"]
print(json.dumps(out))
"""


def test_a_non_writer_in_a_worker_sandbox_reads_the_read_only_store_lock_free(lab):
    """The store on the sandbox's read-only bind of the project: every lock-free read works (no EROFS or EACCES), and
    a locked read is refused as a non-writer's, before the lock (which is not there) could be opened."""
    import json

    aew_project(lab)
    layout = lab.layout("reviewer")
    # The code under test, whichever checkout that is (an absolute PYTHONPATH outside the sandbox stays one inside).
    env = f"PYTHONPATH={os.environ.get('PYTHONPATH', '')} AEW_AGENT_ENDPOINT=/tmp/aew-no-bridge"
    res = lab.sh(layout, f"{env} {sys.executable} -c '{_NON_WRITER_READS}' {lab.repo}")
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == {"kind": "non_writer", "revision": 0, "manifest": True, "records": 0,
                                      "segment": True, "locked_read": "non_writer_process"}
    # The CLI itself, as an agent runs it there: its reads work lock-free on the read-only store (review of #231, B1),
    # and a command that needs the lock is refused as a non-writer's, not by the read-only filesystem.
    for args in ("status --json", "work list"):
        cli = lab.sh(layout, f"{env} {sys.executable} -m aew -C {lab.repo} {args}")
        assert cli.returncode == 0, (args, cli.stderr)
    locked = lab.sh(layout, f"{env} {sys.executable} -m aew -C {lab.repo} history audit")
    error = json.loads(locked.stderr)["error"]
    assert error["code"] == "PERMISSION_DENIED" and error["details"]["reason"] == "non_writer_process", locked.stderr


def test_every_command_a_worker_can_run_works_in_its_sandbox_or_is_refused_for_its_own_reason(visible):
    """Inside a real reviewer's sandbox (the store on the project's read-only bind, `.aew/local` an empty read-only
    mask with only the run's own directories bound back), on a project with finished work and a log past the
    compaction window: every command a worker's agent can run (``worker_surface.commands``) works or is refused for a
    reason of its own, with no crash and nothing met read-only, and only WRITER_ONLY is refused as a non-writer's
    (review of #231, m7: `context pack` crashed on the mask, and `history reindex` blamed "another AEW process").
    A fingerprint read's git writing objects met the read-only store until STG-05 CS-2 (D-CS2-1): the pin,
    ``worker_surface.READER_GIT_GAP``, is empty now, and the real object store is unchanged across the run."""
    import json
    from concurrent.futures import ThreadPoolExecutor

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
    import worker_surface

    w = worker_surface.worked_project(visible)
    ws = visible / "review-ws"
    assert git("worktree", "add", "-q", "--detach", str(ws), cwd=w.p.root).returncode == 0
    run = w.p.root / ".aew" / "local" / "harness" / "runs" / "R-REVIEW-1"
    run.mkdir(parents=True)
    home = visible / "home"
    home.mkdir()
    layout = C.for_run(role="reviewer", scope="ticket", workspace=str(ws), run_dir=run, scratch=str(run / "scratch"),
                       bridge_dir=None, policy=None, home=str(home), project=str(w.p.root), runs=str(run.parent))
    # The code under test, whichever checkout that is (an absolute PYTHONPATH outside the sandbox stays one inside).
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": os.environ.get("PYTHONPATH", ""), "HOME": str(home),
           "LANG": "C.UTF-8", **layout.env, "AEW_AGENT_ENDPOINT": "/tmp/aew-no-bridge/s", "AEW_AGENT_KEY": "00" * 32}

    def run_one(argv: list[str]) -> tuple[list[str], subprocess.CompletedProcess[str]]:
        cmd = C.bwrap_argv(layout, [sys.executable, "-m", "aew", "-C", str(w.p.root), *argv], cwd=str(ws))
        return argv, subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180,
                                    stdin=subprocess.DEVNULL)

    objects = worker_surface.objects(w.p.root)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run_one, worker_surface.commands(w)))
    assert worker_surface.objects(w.p.root) == objects  # D-CS2-1: a reader never writes the real object store
    gap = {worker_surface.words(a) for a, r in results if worker_surface.git_object_store_refused(r.stderr)}
    met = {" ".join(a): r.stderr[-300:] for a, r in results
           if any(sign in r.stderr for sign in worker_surface.WRITE_FAILURES)
           and not worker_surface.git_object_store_refused(r.stderr)}
    assert met == {}
    assert gap == worker_surface.READER_GIT_GAP, sorted(gap)  # the pinned gap, both ways: it only shrinks

    def reason(stderr: str) -> str | None:
        try:
            return (json.loads(stderr)["error"].get("details") or {}).get("reason")
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    refused = {worker_surface.words(a) for a, r in results if reason(r.stderr) == "non_writer_process"}
    assert refused == set(worker_surface.WRITER_ONLY), sorted(refused)


# ------------------------------------------------------------------ STG-05 CS-2: a workspace fingerprint is a read

_READER_FINGERPRINT = """
import json, sys
from pathlib import Path
from aew import process_kind
from aew.snapshot import fingerprint
process_kind.declare("aew (worker run)")
ws = Path(sys.argv[1])
print(json.dumps({"fingerprint": fingerprint.relevant_inputs_fingerprint(ws), "tree": fingerprint.working_tree_id(ws)}))
"""


@pytest.mark.parametrize("state", ["uncommitted_edits", "fresh_worktree"])
def test_a_readers_fingerprint_in_its_sandbox_equals_the_writers(lab, state):
    """D-CS2-1: in a reader's sandbox, where the real object store is read-only, a fingerprint read works, for a
    workspace with uncommitted edits and for a worktree just made (its index racily clean, so every file is read
    again); its value is the one a writer computes for the same tree; and the real object store is unchanged."""
    import json

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
    import worker_surface

    from aew.snapshot import fingerprint

    ws = lab.ws
    if state == "uncommitted_edits":
        (ws / "f.txt").write_text("edited, not committed\n")
        (ws / "new.txt").write_text("untracked\n")
    else:
        ws = lab.root / "fresh"
        assert git("worktree", "add", "-q", "--detach", str(ws), cwd=lab.repo).returncode == 0
    lab.run.mkdir(parents=True, exist_ok=True)
    layout = C.for_run(role="reviewer", scope="ticket", workspace=str(ws), run_dir=lab.run,
                       scratch=str(lab.run / "scratch"), bridge_dir=None, policy=None, home=str(lab.home),
                       project=str(lab.repo), runs=str(lab.run.parent))
    objects = worker_surface.objects(lab.repo)
    # The code under test, whichever checkout that is (an absolute PYTHONPATH outside the sandbox stays one inside).
    res = lab.sh(layout, f"PYTHONPATH={os.environ.get('PYTHONPATH', '')} {sys.executable} -c '{_READER_FINGERPRINT}' "
                         f"{ws}", cwd=ws)
    assert res.returncode == 0, res.stderr
    assert worker_surface.objects(lab.repo) == objects
    seen = json.loads(res.stdout)
    assert seen == {"fingerprint": fingerprint.relevant_inputs_fingerprint(ws),  # the writer's, on the host
                    "tree": fingerprint.working_tree_id(ws)}


# ------------------------------------------------------------------ STG-05 CS-2: the masks, through the self-test
# Each test asserts what the real launch self-test records (CB-12's rows 2 to 5), plus plain reads from inside. What a
# test plants is synthetic and its own: files and sockets in its `visible` directory (outside /tmp, which is private
# inside a sandbox; removed after the test), each socket with its own listener, closed in a finally. The launching
# environment is a dict built from scratch. Fail-closed is shown by taking one protection out of the self-test's
# sandbox: the row that covers it fails, `required` refuses the launch, and `allow_weaker` labels it.


@contextlib.contextmanager
def listening(path: Path) -> Iterator[socket.socket]:
    """A synthetic filesystem socket at ``path``, with its own listener; closed and removed afterwards."""
    path.parent.mkdir(parents=True, exist_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.settimeout(10)
    try:
        server.bind(str(path))
        server.listen(1)
        yield server
    finally:
        server.close()
        path.unlink(missing_ok=True)


def establish(lab: Lab, monkeypatch, *, env: dict[str, str] | None = None, mode: str | None = None):
    """``containment.establish`` for a reviewer of the lab's workspace: the lab's synthetic home as HOME, and a
    launching environment built from scratch."""
    monkeypatch.setenv("HOME", str(lab.home))
    lab.run.mkdir(parents=True, exist_ok=True)
    return C.establish(role="reviewer", scope="ticket", workspace=str(lab.ws), run_dir=lab.run,
                       scratch=str(lab.run / "scratch"), bridge_dir=None,
                       policy={"containment": {"mode": mode}} if mode else None, project=str(lab.repo),
                       env=env or {})


def without(monkeypatch, *steps: tuple[str, ...]) -> None:
    """The self-test's sandbox without one protection: each of ``steps`` (a run of argv words) taken out of it."""
    real = probe.bwrap_argv

    def argv(layout, cmd, **kw):
        out = real(layout, cmd, **kw)
        for step in steps:
            end = out.index("--")
            at = next((i for i in range(end - len(step) + 1) if tuple(out[i:i + len(step)]) == step), None)
            assert at is not None, f"{step} is not on the argv"
            out = out[:at] + out[at + len(step):]
        return out

    monkeypatch.setattr(probe, "bwrap_argv", argv)


def test_the_self_test_records_rows_2_to_5_on_the_label_of_a_passing_run(lab, monkeypatch):
    """CB-12's rows 2 to 5 pass on the real layout and are on the label with their facts: /run a read-only tmpfs
    holding nothing the layout did not put there, a complete socket inventory with no failing socket, no display
    credential or variable, no controlling terminal, and every bind and mask holding. The walk's size and time are
    printed: its cost, measured on CI and on the Rocky VM (`-s`)."""
    layout, label = establish(lab, monkeypatch)
    assert layout is not None and label["filesystem"] == "os_readonly_roots"
    rows = label["self_test"]["rows"]
    assert sorted(rows) == ["2", "3", "4", "5"]
    assert {n: r["reason"] for n, r in rows.items() if not r["ok"]} == {}
    assert rows["2"]["host_masks"][L.RUN] == {"type": "tmpfs", "readonly": True, "extra": []}
    assert rows["2"]["complete"] and rows["2"]["walked"] > 0
    assert [s for s in rows["2"]["sockets"] if s["class"] in sockets.FAILING] == []
    assert (rows["4"]["tty_nr"], rows["4"]["dev_tty"], rows["4"]["session_leader"]) == (0, "ENXIO", True)
    print(f"socket walk: {rows['2']['walked']} entries in {rows['2']['seconds']}s, {len(rows['2']['sockets'])} "
          f"sockets, {rows['2']['unlistable']} unlistable, not walked: {rows['2']['unwalked_mounts']}")


def test_an_ordinary_planted_socket_is_reported_on_the_label_and_the_run_starts(lab, monkeypatch):
    """A site's ordinary services never block a run: a socket no class names is reported, not refused."""
    path = lab.outside / "service" / "svc.sock"
    with listening(path):
        layout, label = establish(lab, monkeypatch)
    assert layout is not None
    assert {"path": str(path), "class": sockets.REPORTED} in label["self_test"]["rows"]["2"]["sockets"]


def test_a_planted_socket_the_launching_environment_names_as_its_agent_fails_the_launch(lab, monkeypatch):
    """A socket that reaches a credential fails the launch wherever it lives: here a synthetic socket that the launching
    environment's SSH_AUTH_SOCK names (so no other test's sandbox, walking the same host, counts it as one).
    `required` refuses the launch; `allow_weaker` starts it uncontained, labelled, with the rows."""
    path = lab.outside / "agent" / "synthetic.sock"
    env = {"SSH_AUTH_SOCK": str(path)}
    with listening(path):
        with pytest.raises(C.ContainmentUnavailable, match="credential socket is reachable") as refused:
            establish(lab, monkeypatch, env=env)
        layout, label = establish(lab, monkeypatch, env=env, mode="allow_weaker")
    row = refused.value.details["self_test"]["rows"]["2"]
    assert row["ok"] is False and {"path": str(path), "class": sockets.CREDENTIAL} in row["sockets"]
    assert layout is None and label["filesystem"] == "workdir_separation_only"
    assert label["self_test"]["rows"]["2"]["ok"] is False


def test_a_socket_on_a_read_only_bind_can_still_be_connected_to(lab):
    """The hand-off's question on outcome 2, answered as a property (fact a): a read-only mount refuses writes to
    files, directories and links, not a socket's connect, which is why the inventory matters. A synthetic listener on
    the host, seen through the sandbox's read-only root, answers a contained client."""
    path = lab.outside / "ro" / "echo.sock"
    with listening(path) as server:
        def answer() -> None:
            with contextlib.suppress(OSError):
                conn, _ = server.accept()
                with conn:
                    conn.sendall(b"answered")

        thread = threading.Thread(target=answer, daemon=True)
        thread.start()
        client = (f"{sys.executable} -c \"import socket; s = socket.socket(socket.AF_UNIX); s.settimeout(10); "
                  f"s.connect('{path}'); print(s.recv(16).decode())\"")
        done = lab.sh(lab.layout("reviewer"), client)
        thread.join(15)
    assert done.returncode == 0 and done.stdout.strip() == "answered", done.stderr


@pytest.mark.serial  # its socket has a credential class's name: a concurrent sandbox's walk of this host would count it
def test_a_credential_cache_socket_in_its_default_place_is_masked_and_the_run_starts(lab, monkeypatch):
    """git's credential-cache daemon keeps its socket under ~/.cache/git/credential, which is masked (the Lead,
    2026-10-23): a host that uses the cache still launches, and the inventory never sees the socket."""
    path = lab.home / ".cache" / "git" / "credential" / "socket"
    with listening(path):
        layout, label = establish(lab, monkeypatch)
    assert layout is not None
    assert [s for s in label["self_test"]["rows"]["2"]["sockets"] if s["path"] == str(path)] == []


def test_the_sandboxes_resolv_conf_resolves_to_a_readable_file_whenever_the_hosts_does(lab):
    """The operator's ruling (2026-10-24): with /run masked, the target of /etc/resolv.conf under /run (a
    systemd-resolved host, CI's runners among them) is bound back read-only, so name resolution keeps its
    configuration until CS-3."""
    try:
        host: str | None = Path(L.RESOLV_CONF).read_text()
    except OSError:
        host = None
    done = lab.sh(lab.layout("reviewer"), f"cat {L.RESOLV_CONF}")
    assert (done.returncode == 0) is (host is not None), done.stderr
    assert host is None or done.stdout == host


def test_what_a_harness_needs_runs_under_the_run_mask(lab):
    """What a harness needs from the host works with /run masked (outcome 1, fact c): the user database, git in the
    workspace, Python's TLS, and a name lookup wherever the host itself can resolve one (through the exception above,
    on a systemd-resolved host); OpenCode's version where it is installed (the Rocky VM)."""
    layout = lab.layout("reviewer")
    checks = ["getent passwd $(id -u) >/dev/null", "git status --porcelain >/dev/null",
              f"{sys.executable} -c 'import ssl, socket'"]
    with contextlib.suppress(OSError):
        socket.getaddrinfo("github.com", 443)
        checks.append(f"{sys.executable} -c \"import socket; socket.getaddrinfo('github.com', 443)\"")
    if shutil.which("opencode"):
        checks.append("opencode --version >/dev/null")
    for check in checks:
        done = lab.sh(layout, check)
        assert done.returncode == 0, (check, done.stderr)


def test_display_credentials_and_variables_never_reach_a_contained_process(lab, monkeypatch):
    """CB-04: the display's credential files (synthetic here) read empty from inside, the one XAUTHORITY names
    included; and no display, session-bus or ssh-agent variable reaches a contained process, even one its launcher
    hands them to. Row 3 records both."""
    for name in L.DISPLAY_FILES:
        (lab.home / name).write_text("SYNTHETIC-COOKIE\n")
    xauth = lab.outside / "xauth-synthetic"
    xauth.write_text("SYNTHETIC-COOKIE\n")
    layout, label = establish(lab, monkeypatch, env={"XAUTHORITY": str(xauth)})
    row = label["self_test"]["rows"]["3"]
    assert row["ok"] and row["env_set"] == []
    expected = {os.path.realpath(p) for p in (lab.home / ".Xauthority", lab.home / ".ICEauthority", xauth)}
    assert set(row["files"]) == expected and set(row["files"].values()) == {"empty"}
    done = lab.sh(layout, f"cat {xauth} {lab.home}/.Xauthority; env", env=dict.fromkeys(L.DISPLAY_ENV, "synthetic"))
    assert done.returncode == 0 and "SYNTHETIC" not in done.stdout, done.stderr
    assert {line.split("=", 1)[0] for line in done.stdout.splitlines()} & set(L.DISPLAY_ENV) == set()


def test_no_credential_reaches_git_inside_the_sandbox(lab):
    """The credential route, output-side, with synthetic files only: git's store helper finds the synthetic credential
    on the host (the control), and nothing from inside, where its two files are masked."""
    stored = "https://" + "synthetic-user:" + "SYNTHETIC-PASS" + "@example.invalid\n"
    (lab.home / ".git-credentials").write_text(stored)
    (lab.home / ".config" / "git").mkdir(parents=True)
    (lab.home / ".config" / "git" / "credentials").write_text(stored)
    ask = ("printf 'protocol=https\\nhost=example.invalid\\n\\n' | GIT_TERMINAL_PROMPT=0 GIT_CONFIG_NOSYSTEM=1 "
           "git -c credential.helper=store credential fill")
    host = subprocess.run(["sh", "-c", ask], capture_output=True, text=True, timeout=60,
                          env={"PATH": os.environ["PATH"], "HOME": str(lab.home), "LANG": "C.UTF-8"})
    assert "SYNTHETIC-PASS" in host.stdout, host.stderr  # the control: there is a credential to find
    inside = lab.sh(lab.layout("reviewer"), ask)
    assert "SYNTHETIC" not in inside.stdout + inside.stderr


FAIL_CLOSED = ("row2-run", "row3-file", "row3-env", "row5-mask")


@pytest.mark.parametrize("case", FAIL_CLOSED)
def test_each_row_fails_closed_when_its_protection_is_missing(lab, monkeypatch, case):
    """Each row checks the sandbox, not the layout's word for it: with one protection taken out of the self-test's
    sandbox, the row that covers it fails, `required` refuses the launch, and `allow_weaker` starts the run labelled
    workdir_separation_only, with the rows. Row 2's failing socket and incomplete walk have tests of their own; row 4
    is judged on synthetic probe output (tests/unit/test_containment_probe.py), since a launcher with no controlling
    terminal, as every test's, cannot show a missing session."""
    xauth = lab.home / ".Xauthority"
    xauth.write_text("SYNTHETIC-COOKIE\n")
    real = os.path.realpath
    row, steps = {
        "row2-run": ("2", [("--tmpfs", L.RUN), ("--remount-ro", L.RUN)]),
        "row3-file": ("3", [("--ro-bind", str(lab.run / L.MASK_FILE), real(xauth))]),
        "row3-env": ("3", [("--unsetenv", "DISPLAY")]),
        "row5-mask": ("5", [("--tmpfs", real(lab.home / ".ssh"))]),
    }[case]
    without(monkeypatch, *steps)
    with pytest.raises(C.ContainmentUnavailable, match=f"row {row} ") as refused:
        establish(lab, monkeypatch)
    assert refused.value.details["self_test"]["rows"][row]["ok"] is False
    layout, label = establish(lab, monkeypatch, mode="allow_weaker")
    assert layout is None and label["self_test"]["rows"][row]["ok"] is False


def test_an_incomplete_socket_walk_fails_row_2(lab):
    """An inventory that did not finish cannot show that no socket reaches the display, G3, an AEW service or a
    credential, so row 2 fails (the Lead's ruling on CS-2's plan, Q3)."""
    result = probe.self_test(lab.layout("reviewer"), sentinel_dir=lab.outside, sibling_dir=lab.root, walk_budget_s=0)
    row = result["rows"]["2"]
    assert result["ok"] is False and row["complete"] is False and "did not finish" in row["reason"]
