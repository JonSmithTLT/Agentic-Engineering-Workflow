"""OS filesystem containment and process ownership on Linux (F2, E13; M4-B).

Every test builds a real role layout and runs real processes in it through ``ProcessTree(layout=...)``, the same
choke point a harness run and its checks use. The host paths these tests attack live outside ``/tmp`` (the sandbox
has a private ``/tmp``), so each attack meets the host's file, made read-only, and each test checks both that the
attempt failed and that the host is byte-identical afterwards.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import probe

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

    def sh(self, layout: C.Layout, script: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=str(cwd or self.ws), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8",
                                   **layout.env})
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


def test_secrets_are_hidden_and_a_masked_file_is_still_a_file(lab):
    done = lab.sh(lab.layout(), f"ls -A {lab.home}/.ssh; cat {lab.home}/.netrc; test -f {lab.home}/.netrc && echo FILE")
    assert done.returncode == 0, done.stderr
    assert "SECRET" not in done.stdout and "id_key" not in done.stdout
    assert done.stdout.strip() == "FILE"


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
    """Whatever widened the layout (an operator root, a future bug), reaching these fails the launch self-test."""
    (lab.repo / ".aew" / "state").mkdir(parents=True)
    good = lab.layout()
    extra, expected = {"control_state": (str(lab.repo), ".aew"), "host_tmp": ("/tmp", ".tmp-marker"),
                       "sibling_run": (str(lab.run.parent), ".probe-run")}[reach]
    result = probe.self_test(dataclasses.replace(good, writable=(*good.writable, extra)), sentinel_dir=lab.outside,
                             sibling_dir=lab.root)
    assert result["ok"] is False and expected in result["reason"], result
    assert not list(lab.run.parent.glob("*.probe-run"))
    # this probe's own markers only: tests running alongside have probes of their own in the shared /tmp
    assert not list(Path(tempfile.gettempdir()).glob(f"{result['probe']}*"))


def test_launch_fails_closed_without_bubblewrap_unless_the_policy_allows_weaker(lab, monkeypatch):
    monkeypatch.setenv("PATH", str(lab.root / "empty"))
    args = dict(role="implementer", scope="ticket", workspace=str(lab.ws), run_dir=lab.run,
                scratch=str(lab.run / "scratch"), bridge_dir=None)
    with pytest.raises(C.ContainmentUnavailable, match="bubblewrap"):
        C.establish(**args, policy=None)
    layout, label = C.establish(**args, policy={"containment": {"mode": "allow_weaker"}})
    assert layout is None and label["filesystem"] == "workdir_separation_only"
    assert "bubblewrap" in label["weaker_because"] and not (lab.run / "git").exists()


def test_establish_labels_a_contained_run_truthfully(lab):
    layout, label = C.establish(role="reviewer", scope="ticket", workspace=str(lab.ws), run_dir=lab.run,
                                scratch=str(lab.run / "scratch"), bridge_dir=None, policy=None)
    assert layout is not None
    assert label["filesystem"] == "os_readonly_roots" and label["process_ownership"] == "pid_namespace"
    assert label["network"] == "not_provided" and label["mechanism"].startswith("bubblewrap")
    assert label["self_test"]["ok"] is True and label["layout"]["workspace_access"] == "read"


# ------------------------------------------------------------------ process ownership (E13)

def _wait_file(path: Path, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text().strip():
            return path.read_text()
        time.sleep(0.05)
    raise AssertionError(f"{path} never written")


@pytest.mark.parametrize("escape", ["setsid", "double_fork"])
def test_killing_the_tree_ends_every_process_even_one_that_left_the_group(lab, escape):
    layout = lab.layout()
    pidfile = lab.run / "scratch" / "pids"
    start = ("setsid sleep 300 & echo $! > {f}; wait" if escape == "setsid"
             else "(sleep 300 & echo $! > {f}) ; sleep 300").format(f=pidfile)
    tree = procs.ProcessTree(layout=layout)
    proc = tree.spawn(["sh", "-c", start], cwd=str(lab.ws), stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"]})
    ns_pid = int(_wait_file(pidfile).split()[0])
    host = procs.host_pid(ns_pid, under=proc.pid)
    assert host != ns_pid  # it lives in the run's PID namespace
    watch = procs.Watch(host)
    assert watch.alive()
    tree.kill()
    deadline = time.monotonic() + 15
    while watch.alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not watch.alive()
    tree.close()
    watch.close()


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
                             scratch=sys.argv[2] + "/scratch", bridge_dir=None, policy=None, home=sys.argv[3])
tree = procs.ProcessTree(layout=layout)
p = tree.spawn(["sh", "-c", "setsid sleep 300 & echo $! > " + sys.argv[2] + "/scratch/pid; wait"], cwd=sys.argv[1],
               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print(p.pid, flush=True)
time.sleep(300)
"""


def test_sigkill_of_the_owner_ends_the_contained_tree(lab):
    owner = subprocess.Popen([sys.executable, "-c", _OWNER, str(lab.ws), str(lab.run), str(lab.home)],
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
