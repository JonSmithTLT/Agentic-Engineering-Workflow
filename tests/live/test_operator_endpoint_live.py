"""Live lane: the operator endpoint refuses a different local principal (M4-E plan v3 §2.1, the stand-in test).

Run on a host where the operator created the stand-in user once (``sudo useradd -m aew-lead-probe``) and may run
commands as it without a password prompt (``sudo -n -u aew-lead-probe``)::

    AEW_LEAD_PROBE_USER=aew-lead-probe pytest --live tests/live/test_operator_endpoint_live.py -p no:xdist -q

The stand-in plays a separated Lead host. As that user, the client cannot reach the socket (its directory is 0700);
with the directory deliberately opened for the test, the endpoint refuses the connection on the peer check before
any challenge is shown. This proves the mechanism F18.6 will rely on. It does not prove the real Lead is excluded:
on today's hosts the real Lead runs as the operator's uid, and that production exit criterion stays open until F18.6
(the same-uid residuals are in ``test_operator_endpoint_pty.py``)."""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("sudo") is None,
                                reason="a second local user (sudo) on Linux")
PROBE_USER = os.environ.get("AEW_LEAD_PROBE_USER", "aew-lead-probe")
SRC = Path(__file__).resolve().parents[2] / "src"


def _as_probe(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sudo", "-n", "-u", PROBE_USER, "env", f"PYTHONPATH={SRC}", sys.executable, "-c",
                           *argv], capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)


CONNECT = """
import json, sys
from multiprocessing.connection import Client
try:
    conn = Client(sys.argv[1], family="AF_UNIX")
except OSError as exc:
    print(json.dumps({"reached": False, "error": type(exc).__name__})); raise SystemExit
try:  # the endpoint may refuse (and close) before it reads anything
    conn.send_bytes(json.dumps({"op": sys.argv[2], "args": {"mode": "walk", "requester": "probe"}}).encode())
except OSError:
    pass
print(json.dumps({"reached": True, "reply": json.loads(conn.recv_bytes())}))
"""


@pytest.fixture
def probe_user():
    try:
        pwd.getpwnam(PROBE_USER)
    except KeyError:
        pytest.fail(f"the stand-in user {PROBE_USER} does not exist: the operator creates it once with sudo "
                    "(M4-E plan v3 §10)")
    if _as_probe("print(1)").returncode != 0:
        pytest.fail(f"`sudo -n -u {PROBE_USER}` needs a password here; allow it for this test")
    return PROBE_USER


def test_lead_identity_cannot_reach_the_endpoint(project, probe_user):
    import json

    from aew.engine.api import Engine
    from aew.harness import operator_endpoint

    path = project.root / ".aew" / "policy" / "execution.yaml"
    path.write_text(path.read_text(encoding="utf-8") + "steering:\n  mode: crawl\n", encoding="utf-8")
    project.adopt_policy()
    shown: list[str] = []
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=shown.append, dev=True)
    ep.start()
    try:
        directory = Path(ep.address).parent
        out = _as_probe(CONNECT, ep.address, "mode_raise")
        assert out.returncode == 0, out.stderr
        assert json.loads(out.stdout) == {"reached": False, "error": "PermissionError"}, out
        directory.chmod(0o711)  # deliberately opened: now only the peer check stands
        os.chmod(ep.address, 0o777)  # noqa: S103 (the test opens the socket on purpose, so the peer check alone stands)
        for op in ("mode_raise", "ping"):
            out = _as_probe(CONNECT, ep.address, op)
            assert out.returncode == 0, out.stderr
            reply = json.loads(out.stdout)
            assert reply["reached"] and reply["reply"]["ok"] is False, out
            assert reply["reply"]["error"]["details"]["reason"] == "peer_check", reply
        assert shown == [], "a challenge was shown for another principal's request"
        assert Engine.discover(project.root).steering_view()["effective"] == "crawl"
    finally:
        ep.close()
