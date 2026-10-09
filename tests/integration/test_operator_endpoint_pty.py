"""The operator endpoint against a real same-uid Lead session (M4-E plan v3 §2.1; A1 §6 test 1; N5).

The real Lead identity on today's hosts *is* the operator's uid, so this can only show the residual, not a boundary.
It runs ``aew operator serve --dev`` at a pseudo-terminal (its console), then a real ``aew lead session`` whose
"harness" is a probe: from inside the session, with the broker's environment and with it stripped and a pty present
(``script -qc``), it tries every way to the endpoint. What must hold: the client reaches only the endpoint, the
challenge code never appears on the requester's pty, the endpoint is not readable through ``ptrace`` or
``/proc/<pid>/mem``, and every record is ``guarantee: dev``. The residuals it cannot close are asserted to be
recorded, not claimed closed. POSIX pty path only: a Windows console would appear on the desktop."""

from __future__ import annotations

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from conftest import clean_env, run_aew

from aew.harness import operator_client

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("script") is None,
                                reason="the POSIX pty operator path (util-linux `script`); Linux only")
SRC = str(Path(__file__).resolve().parents[2] / "src")
PROBE = textwrap.dedent('''
    import json, os, subprocess, sys
    out, root = sys.argv[1], sys.argv[2]
    aew = [sys.executable, "-m", "aew", "-C", root]
    results = {}
    def run(argv, env, stdin=""):
        p = subprocess.run(argv, env=env, input=stdin, capture_output=True, text=True, timeout=120)
        return {"code": p.returncode, "out": p.stdout, "err": p.stderr}
    session_env = dict(os.environ)
    stripped = {k: v for k, v in os.environ.items() if not k.startswith("AEW_LEAD_BROKER")}
    results["raise_in_session"] = run(aew + ["lead", "mode", "raise", "walk"], session_env)
    results["serve_in_session"] = run(aew + ["operator", "serve", "--dev"], session_env)
    results["ping_in_session"] = run(aew + ["operator", "ping"], session_env)
    # The broker's coordinates stripped and a pty present: the client reaches the endpoint, whose code is on the
    # operator's console, not here. A guess is typed into this pty; it is refused.
    command = " ".join(aew + ["lead", "mode", "raise", "walk"])
    results["raise_stripped_pty"] = run(["script", "-qfec", command, "/dev/null"], stripped, stdin="000000\\n")
    results["serve_stripped"] = run(aew + ["operator", "serve", "--dev"], stripped)
    json.dump(results, open(out, "w"))
''')


def _env(**extra: str) -> dict[str, str]:
    return clean_env({"PYTHONPATH": SRC, **extra})


class Endpoint:
    """``aew operator serve --dev`` under ``script``: its console is a pty whose output is collected here."""

    def __init__(self, root: Path) -> None:
        command = f"{sys.executable} -m aew -C {root} operator serve --dev"
        self.proc = subprocess.Popen(["script", "-qfec", command, "/dev/null"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_env(),
                                     start_new_session=True)
        self.output = b""
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self.locator = operator_client.wait_for_locator(root / ".aew", timeout=60)
        assert self.locator, self.text()

    def _read(self) -> None:
        assert self.proc.stdout is not None
        for chunk in iter(lambda: self.proc.stdout.read1(4096), b""):  # type: ignore[union-attr]
            self.output += chunk

    def text(self) -> str:
        return self.output.decode("utf-8", "replace")

    def codes(self) -> list[str]:
        return re.findall(r"confirmation code ([0-9A-F]{6})", self.text())

    def stop(self) -> None:
        os.killpg(self.proc.pid, 2)
        try:
            self.proc.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(self.proc.pid, 9)
            self.proc.wait(30)


@pytest.fixture
def steered(project):
    path = project.root / ".aew" / "policy" / "execution.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "steering:\n  mode: crawl\n", encoding="utf-8")
    project.adopt_policy()
    return project


@pytest.fixture
def endpoint(steered):
    ep = Endpoint(steered.root)
    yield ep
    ep.stop()


def test_pty_and_stripped_env_reach_only_the_endpoint(steered, endpoint, tmp_path):
    probe, out = tmp_path / "probe.py", tmp_path / "probe.json"
    probe.write_text(PROBE, encoding="utf-8")
    res = run_aew("-C", str(steered.root), "lead", "session", "--", sys.executable, str(probe), str(out),
                  str(steered.root), env=_env(AEW_LEAD_TOKEN=steered.token), timeout=600)
    assert res.returncode == 0, res.stderr
    results = json.loads(out.read_text(encoding="utf-8"))
    for name in ("raise_in_session", "serve_in_session", "ping_in_session"):  # the broker refuses all three
        assert results[name]["code"] != 0 and "operator endpoint" in results[name]["err"], (name, results[name])
    pty = results["raise_stripped_pty"]
    assert pty["code"] != 0, pty
    deadline = time.monotonic() + 30
    while not endpoint.codes() and time.monotonic() < deadline:
        time.sleep(0.1)
    (code,) = endpoint.codes()  # the challenge reached the endpoint's console, once
    assert code not in pty["out"] + pty["err"], "the challenge code appeared on the requester's pty"
    assert "refused" in endpoint.text() or "wrong code" in endpoint.text()
    serve = results["serve_stripped"]
    assert serve["code"] != 0 and "Lead session" in serve["err"], serve
    status = json.loads(run_aew("-C", str(steered.root), "status", "--json", env=_env()).stdout)
    assert status["steering"]["effective"] == "crawl"  # nothing was raised
    records = [json.loads(line) for f in (steered.root / ".aew/records/steering").glob("*.jsonl")
               for line in f.read_text(encoding="utf-8").splitlines()]
    assert all(r["by"].get("guarantee", r["by"].get("principal", {}).get("guarantee")) == "dev"
               for r in records if r.get("kind") == "mode_change")


def test_endpoint_is_not_ptrace_readable(endpoint, steered):
    """N5: the endpoint process is non-dumpable, which is what keeps a same-uid process out of its memory."""
    info = operator_client.ping(steered.root / ".aew")
    assert info["dumpable"] is False and info["pid"] == endpoint.locator["pid"] and info["guarantee"] == "dev"
    assert len(info["residuals"]) == len(operator_client.RESIDUALS)


@pytest.mark.skipif(sys.platform.startswith("linux") and os.geteuid() == 0,
                    reason="root holds CAP_SYS_PTRACE, which reads any process; CI runs this as a plain user")
def test_a_same_uid_process_can_neither_read_nor_attach_to_the_endpoint(endpoint):
    pid = endpoint.locator["pid"]
    with pytest.raises(PermissionError):
        with open(f"/proc/{pid}/mem", "rb") as mem:
            mem.read(1)
    libc = ctypes.CDLL(None, use_errno=True)
    child = os.fork()
    if child == 0:  # attach from a separate process, as a same-uid Lead would
        os._exit(0 if libc.ptrace(16, pid, None, None) == -1 else 1)  # PTRACE_ATTACH
    _, status = os.waitpid(child, 0)
    assert os.WEXITSTATUS(status) == 0, "a same-uid process attached to the operator endpoint"
