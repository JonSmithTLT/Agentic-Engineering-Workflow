"""M4-B containment experiments (Rocky 8, a9fabaf). Run on the VM with the review venv:

    ~/aew-review/venv-a9fabaf/bin/python contain_probe.py

Builds a lab like tests/integration/test_containment.py (a repo with .aew control state, a worktree workspace, a
runs directory with a sibling run's harness state, a home with secrets), then:

  E1  an operator `containment.writable` root that is the project root: does the self-test pass, and what can the
      sandbox then write (control state) and read (the sibling run's bridge key)?
  E2  an operator writable root of /tmp: does the host's /tmp (other runs' bridge sockets) come back?
  E3  an operator writable root of $HOME: the sentinel catches it (contrast).
  E4  procs.host_pid: a pid of a process in a nested namespace, reported in the run's namespace, and an unknown pid.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from aew.harness import containment as C
from aew.harness import procs
from aew.harness.containment import probe

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})


class Lab:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "project"
        self.repo.mkdir()
        git("init", "-q", cwd=self.repo)
        (self.repo / "f.txt").write_text("base\n")
        aew = self.repo / ".aew"
        (aew / "state").mkdir(parents=True)
        (aew / "state" / "control.yaml").write_text("revision: 7\n# aew-checksum sha256:deadbeef\n")
        git("add", "-A", cwd=self.repo)
        git("commit", "-q", "-m", "base", cwd=self.repo)
        self.ws_root = root / ".aew-workspaces" / "project"
        self.ws_root.mkdir(parents=True)
        self.ws = self.ws_root / "T-0001-1"
        git("worktree", "add", "-q", "-b", "w", str(self.ws), cwd=self.repo)
        self.runs = aew / "local" / "harness" / "runs"
        self.run = self.runs / "R-INV-0002-1"
        sibling = self.runs / "R-INV-0001-1" / "harness"
        sibling.mkdir(parents=True)
        (sibling / "session.db").write_text("AEW_AGENT_KEY=sibling-bridge-key\n")
        self.home = root / "home"
        (self.home / ".ssh").mkdir(parents=True)
        (self.home / ".ssh" / "id_key").write_text("SECRET-KEY\n")

    def layout(self, role="implementer", policy=None) -> C.Layout:
        self.run.mkdir(parents=True, exist_ok=True)
        return C.for_run(role=role, scope="ticket", workspace=str(self.ws), run_dir=self.run,
                         scratch=str(self.run / "scratch"), bridge_dir=None, policy=policy, home=str(self.home),
                         project=str(self.repo), runs=str(self.runs))

    def sh(self, layout: C.Layout, script: str) -> subprocess.CompletedProcess:
        tree = procs.ProcessTree(layout=layout)
        try:
            proc = tree.spawn(["sh", "-c", script], cwd=str(self.ws), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              stdin=subprocess.DEVNULL, text=True,
                              env={"PATH": os.environ["PATH"], "HOME": str(self.home), **layout.env})
            out, err = proc.communicate(timeout=60)
            return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
        finally:
            tree.close()


def show(title: str, done: subprocess.CompletedProcess) -> None:
    print(f"  {title}: exit {done.returncode}; stdout={done.stdout.strip()[:200]!r} stderr={done.stderr.strip()[-160:]!r}")


def main() -> None:
    base = Path.home() / ".aew-test-tmp"
    base.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="review-", dir=base))
    lab = Lab(root)
    control = lab.repo / ".aew" / "state" / "control.yaml"
    sibling_db = lab.runs / "R-INV-0001-1" / "harness" / "session.db"

    print("== E0 default layout (no operator roots): the baseline the self-test and the tests prove")
    layout = lab.layout()
    print("  self_test:", json.dumps(probe.self_test(layout, sentinel_dir=lab.ws_root, sibling_dir=lab.ws_root)))
    show("write control.yaml", lab.sh(layout, f"printf x >> {control}"))
    show("read sibling run key", lab.sh(layout, f"cat {sibling_db}"))

    print("== E1 operator writable root = the project root (a misdeclared 'build cache')")
    layout = lab.layout(policy={"writable": [str(lab.repo)]})
    test = probe.self_test(layout, sentinel_dir=lab.ws_root, sibling_dir=lab.ws_root)
    print("  self_test:", json.dumps(test))
    label = C.label(contained=True, mechanism="bubblewrap 0.4.0", self_test={"ok": test["ok"]}, layout=layout)
    print("  label.filesystem:", label["filesystem"], "operator_writable:", label["layout"]["operator_writable"])
    before = control.read_text()
    show("write control.yaml", lab.sh(layout, f"printf '# forged\\n' >> {control}"))
    print("  control.yaml changed on host:", control.read_text() != before)
    show("read sibling run key", lab.sh(layout, f"cat {sibling_db}"))
    show("write sibling run dir", lab.sh(layout, f"printf x >> {sibling_db}"))
    show("git metadata still protected", lab.sh(layout, "git update-ref refs/heads/w HEAD~0"))
    show("evidence dir writable", lab.sh(layout, f"mkdir -p {lab.repo}/.aew/evidence/T-0001 && printf x > {lab.repo}/.aew/evidence/T-0001/forged.md"))

    print("== E2 operator writable root = /tmp")
    other_socket = Path("/tmp/aew-bridge-REVIEW-OTHER-RUN")
    other_socket.mkdir(exist_ok=True)
    (other_socket / "s").write_text("not a socket, a marker\n")
    try:
        layout = lab.layout(policy={"writable": ["/tmp"]})
        test = probe.self_test(layout, sentinel_dir=lab.ws_root, sibling_dir=lab.ws_root)
        print("  self_test:", json.dumps(test))
        show("host /tmp visible", lab.sh(layout, "ls -d /tmp/aew-bridge-* 2>/dev/null | head -3"))
        show("host /tmp writable", lab.sh(layout, f"printf x >> {other_socket}/s"))
    finally:
        (other_socket / "s").unlink(missing_ok=True)
        other_socket.rmdir()

    print("== E3 operator writable root = $HOME (the sentinel next to the workspace catches this one)")
    layout = lab.layout(policy={"writable": [str(root)]})
    print("  self_test:", json.dumps(probe.self_test(layout, sentinel_dir=lab.ws_root, sibling_dir=lab.ws_root)))

    print("== E4 procs.host_pid soundness")
    layout = lab.layout()
    pidfile = lab.run / "scratch" / "pids"
    tree = procs.ProcessTree(layout=layout)
    try:
        proc = tree.spawn(["sh", "-c",
                           "bwrap --unshare-pid --ro-bind / / --dev /dev --proc /proc -- sleep 300 & B=$!; sleep 1; "
                           "C=$(pgrep -P $B | head -1); S=$(pgrep -P $C | head -1); echo $B $C $S > " + str(pidfile)
                           + "; wait"],
                          cwd=str(lab.ws), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, env={"PATH": os.environ["PATH"]})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (pidfile.exists() and len(pidfile.read_text().split()) == 3):
            time.sleep(0.1)
        b, c, s = (int(x) for x in pidfile.read_text().split())
        print(f"  run-namespace pids: nested bwrap={b} its init={c} inner sleep={s} (as the agent would report them)")
        for name, ns_pid in (("nested bwrap", b), ("inner sleep (outer-ns pid)", s)):
            try:
                host = procs.host_pid(ns_pid, under=proc.pid)
                status = Path(f"/proc/{host}/status").read_text() if Path(f"/proc/{host}").exists() else ""
                name_line = next((l for l in status.splitlines() if l.startswith("Name:")), "Name:\t<gone>")
                nspid = next((l for l in status.splitlines() if l.startswith("NSpid:")), "NSpid:\t?")
                under = procs._descends(host, proc.pid)
                print(f"  host_pid({ns_pid}, under=bwrap) -> {host}: {name_line.split()[-1]} {nspid.strip()} "
                      f"descends from the run's bwrap: {under}")
            except LookupError as exc:
                print(f"  host_pid({ns_pid}) -> LookupError: {exc}")
        bogus = 4_000_000
        print(f"  host_pid({bogus}, under=bwrap) -> {procs.host_pid(bogus, under=proc.pid)} (no such process: "
              "returned as if it were a host pid)")
    finally:
        tree.kill()
        tree.close()
    print("done; lab at", root)


if __name__ == "__main__":
    main()
