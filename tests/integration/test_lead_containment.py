"""The Lead contained, on Linux (STG-05 CS-4; CB-01, CB-05, CB-12 rows 1 to 6).

Every test builds the real Lead layout (``for_run`` role ``lead``, scope ``project``) in a project with a store and a
``.aew/local``, and runs real processes in it through ``ProcessTree(layout=...)``, or the launch self-test. The project
lives outside ``/tmp`` (the sandbox has a private ``/tmp``), so each attempt meets the host's file.
"""

from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import egress, netns, probe
from aew.harness.containment import layout as L

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                                reason="Linux bubblewrap containment (Windows: the Lead runs labelled not contained)")

SRC = str(Path(procs.__file__).resolve().parents[2])
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV, **(env or {})})


class LeadLab:
    """A project with a store, a `.aew/local` holding another run's state and a control lock, and a synthetic home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "proj"
        self.repo.mkdir()
        assert git("init", "-q", cwd=self.repo).returncode == 0
        (self.repo / "f.txt").write_text("base\n")
        git("add", "f.txt", cwd=self.repo)
        assert git("commit", "-q", "-m", "base", cwd=self.repo).returncode == 0
        for d in (".aew/state/log", ".aew/local/harness/runs/R-other/harness"):
            (self.repo / d).mkdir(parents=True)
        (self.repo / ".aew" / "state" / "control.json").write_text('{"revision": 1}\n')
        (self.repo / ".aew" / "local" / "control.lock").write_text("")
        (self.repo / ".aew" / "local" / "harness" / "runs" / "R-other" / "harness" / "bridge.key").write_text("K\n")
        self.home = root / "home"
        (self.home / ".local" / "share" / "opencode").mkdir(parents=True)
        (self.home / ".local" / "share" / "opencode" / "opencode.db").write_text("SYNTHETIC-LOGIN-STORE\n")
        (self.home / ".config" / "opencode").mkdir(parents=True)
        (self.home / ".config" / "opencode" / "opencode.json").write_text('{"mcp": {}}\n')
        self.run = self.repo / ".aew" / "local" / "harness" / "runs" / "lead-1"
        self.state = self.repo / ".aew" / "local" / "harness" / "lead"

    def layout(self, **kw: Any) -> C.Layout:
        return C.for_run(role="lead", scope="project", workspace=str(self.repo), run_dir=self.run,
                         scratch=str(self.run / "scratch"), bridge_dir=None, policy=kw.pop("policy", None),
                         home=str(self.home), project=str(self.repo), runs=str(self.run.parent), env={},
                         state_dir=str(self.state), **kw)

    def sh(self, layout: C.Layout, script: str) -> subprocess.CompletedProcess[str]:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=str(self.repo), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": os.environ["PATH"], "HOME": str(self.home), "LANG": "C.UTF-8",
                                   **GIT_ENV, **layout.env})
            out, err = proc.communicate(timeout=60)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            tree.close()


@pytest.fixture
def lead_lab() -> Iterator[LeadLab]:
    base = Path(os.environ.get("AEW_CONTAINMENT_TEST_DIR") or Path.home() / ".aew-test-tmp")
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="lead-", dir=base))
    try:
        yield LeadLab(root)
    finally:
        for p in root.rglob("*"):  # git makes objects read-only
            try:
                p.chmod(0o700 if p.is_dir() else 0o600)
            except OSError:
                pass
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ outcome 2

def test_the_lead_writes_its_working_tree_and_never_aew_or_the_git_metadata(lead_lab):
    """CS-4 outcome 2 (ruling R-2): the working tree is writable; `.aew` (the store with it) and the real git metadata
    are read-only; git's status, diff and log work on the run's private index and object store."""
    lab = lead_lab
    before = {p: p.read_bytes() for p in (lab.repo / ".aew" / "state" / "control.json", lab.repo / ".git" / "HEAD")}
    done = lab.sh(lab.layout(), "printf edited > f.txt && printf new > g.txt && git add g.txt && "
                                "git status --porcelain && git diff --cached --stat && git log --oneline -1 && "
                                "{ printf x >> .aew/state/control.json; echo store=$?; } 2>/dev/null; "
                                "{ mv .aew .aew-moved; echo rename=$?; } 2>/dev/null; "
                                "{ printf x > .git/HEAD; echo head=$?; } 2>/dev/null")
    assert (lab.repo / "f.txt").read_text() == "edited" and (lab.repo / "g.txt").read_text() == "new"
    assert "g.txt" in done.stdout and "base" in done.stdout, done.stdout + done.stderr  # status, diff, log
    assert "store=1" in done.stdout and "rename=1" in done.stdout and "head=1" in done.stdout, done.stdout
    assert {p: p.read_bytes() for p in before} == before
    assert (lab.repo / ".aew").is_dir() and not (lab.repo / ".aew-moved").exists()
    assert "g.txt" not in git("diff", "--cached", "--name-only", cwd=lab.repo).stdout  # the real index: untouched


def test_from_the_leads_sandbox_aew_local_holds_only_its_own_directories(lead_lab):
    """CS-4 outcome 2: no control lock, no other run's state or socket; only the Lead's run directories and state."""
    lab = lead_lab
    done = lab.sh(lab.layout(), "ls -A .aew/local; echo ---; ls -A .aew/local/harness; echo ---; "
                                "ls -A .aew/local/harness/runs; echo ---; "
                                "touch .aew/local/mine.lock 2>/dev/null; echo lock=$?")
    parts = [p.split() for p in done.stdout.split("---\n")]
    assert parts[0] == ["harness"] and sorted(parts[1]) == ["lead", "runs"] and parts[2] == ["lead-1"], done.stdout
    assert "lock=1" in done.stdout


def test_the_operators_opencode_login_and_configuration_are_empty_from_the_leads_sandbox(lead_lab):
    lab = lead_lab
    done = lab.sh(lab.layout(), f"ls -A {lab.home}/.local/share/opencode {lab.home}/.config/opencode")
    assert "opencode.db" not in done.stdout and "opencode.json" not in done.stdout, done.stdout


# ------------------------------------------------------------------------------------------- outcome 6, rows

def lead_establish(lab: LeadLab, monkeypatch, *, terminal: bool = True, mode: str | None = None,
                   network: str | None = None) -> tuple[C.Layout | None, dict[str, Any]]:
    monkeypatch.setenv("HOME", str(lab.home))
    policy: dict[str, Any] = {"containment": {}}
    if mode:
        policy["containment"]["mode"] = mode
    if network:
        policy["containment"]["network"] = {"mode": network}
    return C.establish(role="lead", scope="project", workspace=str(lab.repo), run_dir=lab.run,
                       scratch=str(lab.run / "scratch"), bridge_dir=None, policy=policy, project=str(lab.repo), env={},
                       egress_policy=egress.AnyPublic(), state_dir=str(lab.state),
                       relayed_terminal={"forbid": None} if terminal else None)


def test_the_leads_self_test_passes_rows_1_to_6_with_its_relayed_terminal_and_any_public_egress(lead_lab, monkeypatch):
    """CS-4 outcome 6: the launch self-test runs on the Lead's own layout, every row passes and is on the label with
    the network mode: row 1 under any-public (R-6 refuses the host's own port), row 4's Lead form (its controlling
    terminal is the relayed one), row 6 (`.aew` a read-only mount point below the writable tree)."""
    layout, label = lead_establish(lead_lab, monkeypatch)
    try:
        assert layout is not None and label["filesystem"] == C.CONTAINED
        rows = label["self_test"]["rows"]
        assert sorted(rows) == ["1", "2", "3", "4", "5", "6"]
        assert {n: r["reason"] for n, r in rows.items() if not r["ok"]} == {}
        assert label["network"]["mode"] == L.PROXY_ONLY and rows["1"]["mode"] == L.PROXY_ONLY
        assert rows["1"]["egress_refused"]["why"] == "a host address (R-6)"
        assert rows["4"]["relayed"] is True and rows["4"]["dev_tty"] == "opened"
        aew = os.path.join(os.path.realpath(lead_lab.repo), ".aew")
        assert rows["6"]["stores"][0]["below"] == {aew: {"mount_point": True, "readonly": True}}
    finally:
        if layout is not None and layout.net_dir:
            shutil.rmtree(layout.net_dir, ignore_errors=True)


def test_row_6_fails_closed_when_the_aew_re_bind_is_missing_from_the_leads_sandbox(lead_lab, monkeypatch):
    """The forgotten route: the Lead's tree without the `.aew` re-bind. The host's own check (CB-07) refuses such a
    layout before anything runs; here the layout passes it and the sandbox loses the re-bind afterwards, and row 6,
    reading the mount table inside, fails, so `required` refuses the launch."""
    aew = os.path.join(os.path.realpath(lead_lab.repo), ".aew")
    real = probe.bwrap_argv

    def without_aew(layout, cmd, **kw):
        out = real(layout, cmd, **kw)
        at = next(i for i in range(out.index("--")) if out[i:i + 3] == ["--ro-bind", aew, aew])
        return out[:at] + out[at + 3:]

    monkeypatch.setattr(probe, "bwrap_argv", without_aew)
    with pytest.raises(ContainmentUnavailable, match="row 6 ") as refused:
        lead_establish(lead_lab, monkeypatch, network=L.SHARED)
    row = refused.value.details["self_test"]["rows"]["6"]
    assert row["ok"] is False and "is not a mount point inside" in row["reason"]


def test_row_4_for_the_lead_fails_closed_without_the_shims_controlling_terminal_step(lead_lab, monkeypatch):
    """Ruling R-7: without the shim's `ctty` step, the probe on the relayed terminal has no controlling terminal, so
    row 4's Lead form fails, and so does a launch on it."""
    real = netns.shim_argv
    monkeypatch.setattr(netns, "shim_argv", lambda spec, argv: real({k: v for k, v in spec.items() if k != "ctty"},
                                                                    argv))
    with pytest.raises(ContainmentUnavailable, match="row 4 ") as refused:
        lead_establish(lead_lab, monkeypatch, network=L.SHARED)
    assert "is not the relay's pseudo-terminal" in refused.value.details["self_test"]["rows"]["4"]["reason"]


# ------------------------------------------------------------------------------------------------ outcome 4

# The operator's side: a broker whose controlling terminal is the test's pseudo-terminal runs the session through the
# terminal relay (tests/integration/test_terminal_relay.py has the relay's endings and bytes).
BROKER = textwrap.dedent("""
    import fcntl, json, os, sys, termios
    os.setsid()
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    from aew.harness import procs
    out = procs.run_session_tree(json.loads(sys.argv[1]), env=dict(os.environ), cwd=sys.argv[2], relay=True)
    with open(sys.argv[3], "w") as f:
        json.dump(out, f)
""")

# The TUI's stand-in, in the sandbox under the shim's ctty step: every terminal open in the sandbox's processes (its
# own PID namespace: bubblewrap's, the shim's, its own), its controlling terminal, and a TIOCSTI on standard input and
# on /dev/tty, read back from its own input.
INSIDE = textwrap.dedent("""
    import errno, fcntl, json, os, select, stat, sys, termios, tty
    def dev(path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        major = os.major(st.st_rdev)
        terminal = stat.S_ISCHR(st.st_mode) and (major in (4, 5) or 136 <= major <= 143)   # terminals, /dev/tty, ptmx
        return [major, os.minor(st.st_rdev)] if terminal else None
    with open("/proc/self/stat", "rb") as f:
        nr = int(f.read().rsplit(b")", 1)[1].split()[4])
    terminals, unreadable = {}, []
    for pid in sorted(p for p in os.listdir("/proc") if p.isdigit()):
        try:
            fds = os.listdir(f"/proc/{pid}/fd")
        except OSError:
            unreadable.append(pid)
            continue
        for fd in fds:
            if (d := dev(f"/proc/{pid}/fd/{fd}")) is not None:
                terminals[f"{pid}/{fd}"] = d
    def sti(fd, char):  # None when the kernel took it, else its errno's name
        try:
            fcntl.ioctl(fd, termios.TIOCSTI, char)
        except OSError as exc:
            return errno.errorcode.get(exc.errno, str(exc.errno))
        return None
    tty.setraw(0)
    refused = [sti(0, b"Z")]
    t = os.open("/dev/tty", os.O_RDWR)
    refused.append(sti(t, b"Y"))
    os.close(t)
    want = refused.count(None)
    got = b""
    while len(got) < want and select.select([0], [], [], 5)[0]:
        got += os.read(0, want - len(got))
    with open(sys.argv[1], "w") as f:
        json.dump({"inner": dev("/proc/self/fd/0"), "tty_nr": nr, "terminals": terminals, "unreadable": unreadable,
                   "refused": refused, "got": got.decode()}, f)
""")
# Linux 6.2 and later refuse TIOCSTI to a process without CAP_SYS_ADMIN in the initial namespace when this is 0 (the
# CONFIG_LEGACY_TIOCSTI default of newer distributions, CI's runners among them); the Rocky VM's 4.18 has no setting.
LEGACY_TIOCSTI = Path("/proc/sys/dev/tty/legacy_tiocsti")


def test_the_tuis_controlling_terminal_is_the_relays_and_tiocsti_reaches_only_its_own_input(lead_lab):
    """CS-4 outcome 4 (CB-05): in the Lead's sandbox the TUI's controlling terminal is the relay's pseudo-terminal,
    no process in the sandbox has the operator's terminal (or any other) open, and a TIOCSTI, on standard input or on
    /dev/tty, lands in the TUI's own input: there is no route to type into the operator's shell. On a kernel that
    refuses TIOCSTI to unprivileged processes (legacy_tiocsti 0), it lands nowhere, refused with EIO."""
    import pty

    lab = lead_lab
    inside, result = lab.repo / "inside.json", lab.root / "result.json"
    harness = C.bwrap_argv(lab.layout(), netns.shim_argv({"in": [], "out": [], "ctty": True},
                                                         [sys.executable, "-I", "-c", INSIDE, str(inside)]),
                           cwd=str(lab.repo))
    master, slave = pty.openpty()
    operator = os.fstat(slave).st_rdev
    broker = subprocess.Popen([sys.executable, "-c", BROKER, json.dumps(harness), str(lab.repo), str(result)],
                              stdin=slave, stdout=slave, stderr=slave, env={**os.environ, "PYTHONPATH": SRC})
    try:
        shown = bytearray()
        deadline = time.monotonic() + 60
        while broker.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                shown += os.read(master, 65536)
        assert broker.poll() == 0, bytes(shown)[-500:]
    finally:
        if broker.poll() is None:
            broker.kill()
        os.close(master)
        os.close(slave)
    assert json.loads(result.read_text()) == [0, "clean"]
    seen = json.loads(inside.read_text())
    print(f"inside the Lead's sandbox: {seen}")  # its processes' terminals, on CI and on the Rocky VM (`-s`)
    inner = seen["inner"]
    assert inner is not None and inner != [os.major(operator), os.minor(operator)]
    assert seen["tty_nr"] == probe.tty_nr(*inner)
    assert seen["terminals"] and set(map(tuple, seen["terminals"].values())) == {tuple(inner)}, seen
    assert seen["unreadable"] == [], seen
    legacy = LEGACY_TIOCSTI.read_bytes().strip() if LEGACY_TIOCSTI.exists() else b"1"
    if legacy == b"0":
        assert (seen["refused"], seen["got"]) == (["EIO", "EIO"], ""), seen
    else:
        assert (seen["refused"], seen["got"]) == ([None, None], "ZY"), seen


def test_a_lead_that_falls_back_to_allow_weaker_is_labelled_so(lead_lab, monkeypatch):
    """CS-4 outcome 1: a Lead whose sandbox fails runs only under `allow_weaker`, labelled workdir_separation_only with
    the reason and the failing row, the label G3 reads as not established."""
    monkeypatch.setattr(netns, "shim_argv", lambda spec, argv: argv)  # no ctty step: row 4 fails
    layout, label = lead_establish(lead_lab, monkeypatch, mode=C.ALLOW_WEAKER, network=L.SHARED)
    assert layout is None and label["filesystem"] == C.WORKDIR_ONLY
    assert "row 4" in label["weaker_because"] and label["self_test"]["rows"]["4"]["ok"] is False
