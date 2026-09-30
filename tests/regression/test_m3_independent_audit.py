"""Findings of the designer's independent M3 audit (`docs/implementation/m3-independent-audit-2026-09-29.md`).

Each regression was written, and seen failing, before its fix.
"""

from __future__ import annotations

import sys
import textwrap
import time
from pathlib import Path

import pytest

from aew.policy import checks

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# A check whose process starts a child, then either hangs (and times out) or exits at once. The child waits, then
# writes a marker: it must never get the chance, because the check's evidence is sealed when the check returns.
PARENT = textwrap.dedent("""\
    import subprocess, sys, time
    child = "import time, pathlib, sys; time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('child continued')"
    subprocess.Popen([sys.executable, "-c", child, sys.argv[1]], creationflags={flags},
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(float(sys.argv[2]))
""").format(flags=NO_WINDOW)


@pytest.mark.parametrize("parent_runs_s, timeout_s", [(30, 0.5), (0, 30)], ids=["parent-times-out", "parent-exits"])
def test_a_check_leaves_no_process_behind_when_it_returns(tmp_path, parent_runs_s, timeout_s):
    """I2. A check timing out (or its parent exiting) left its descendants running: `subprocess.run` ends only
    the direct child. The engine then took the after-snapshot and sealed the evidence while a descendant could
    still change the workspace. Every process a check starts must be gone when the check returns."""
    marker = tmp_path / "marker.txt"
    script = tmp_path / "parent.py"
    script.write_text(PARENT, encoding="utf-8")
    cfg = {"command": ["{python}", str(script), str(marker), str(parent_runs_s)], "timeout_s": timeout_s}
    result = checks.run(cfg, tmp_path)
    if parent_runs_s:
        assert result["exit_code"] is None and "TIMEOUT" in result["log"]
    else:
        assert result["exit_code"] == 0
    time.sleep(1.5)  # well past the child's 0.8 s
    assert not marker.exists(), "a process the check started outlived the check"


# --------------------------------------------------------------------------------------------- I3


class _TurnEndedServer:
    """Just enough of a V2 server for the adapter's poll: the last prompt was delivered and an idle follows it."""

    def __init__(self, session: str) -> None:
        self.session, self.posts = session, []

    def alive(self) -> bool:
        return True

    def get(self, path, params=None, **_):
        base = f"/api/session/{self.session}"
        if path == "/api/session/active":
            return {"data": {}}
        if path in (f"{base}/permission", f"{base}/form", f"{base}/inbox"):
            return {"data": []}
        if path.startswith(f"{base}/message/"):
            return {"data": {"id": path.rsplit("/", 1)[1], "type": "user", "time": {"created": 1}}}
        if path == f"{base}/message":
            return {"data": [{"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}}]}
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, body=None, params=None, **_):
        self.posts.append((path, body))
        return {"data": {"id": (body or {}).get("id")}}


def _adapter_at_turn_end(tmp_path):
    import threading

    from aew.harness.opencode.adapter import OpenCodeAdapter

    events: list[dict] = []
    adapter = OpenCodeAdapter(None, tmp_path, events.append)
    adapter.session = "ses_1"
    fake = _TurnEndedServer(adapter.session)
    adapter.server = adapter.client = fake
    adapter.sent, adapter.turn = ["msg_contract"], "running"
    return adapter, fake, threading


def test_a_lead_message_sent_while_a_turn_is_being_closed_keeps_the_run_going(tmp_path):
    """I3. The poll decided the turn was over, then released the lock; a Lead `harness send` accepted by OpenCode
    in between (here: while the adapter takes its final snapshot) was then overwritten: the run ended with the
    message unanswered. A newer prompt must keep the run going."""
    adapter, fake, threading = _adapter_at_turn_end(tmp_path)

    def snapshot_while_the_lead_sends():
        lead = threading.Thread(target=adapter.send, args=("Also note the changed files.",))
        lead.start()
        lead.join(10)

    adapter._take_snapshot = snapshot_while_the_lead_sends
    adapter._poll()  # idle seen once
    adapter._poll()  # confirmed: the turn is closed, and the Lead's message arrives meanwhile
    assert [p for p, _ in fake.posts] == ["/api/session/ses_1/prompt"]
    assert len(adapter.sent) == 2
    assert adapter.turn == "running" and adapter.exit_code is None and adapter.inspect()["alive"]


def test_a_lead_message_sent_after_the_turn_ended_is_refused_never_revives_it(tmp_path):
    """I3, the other order. Once the turn has ended, the adapter's watcher has stopped; a `send` that set the turn
    back to "running" left a run that looked alive and that nothing watched. It must be refused (the supervisor
    records `request_failed`), and nothing may reach OpenCode."""
    from aew.errors import HarnessError

    adapter, fake, _ = _adapter_at_turn_end(tmp_path)
    adapter._take_snapshot = lambda: None
    adapter._poll()
    adapter._poll()
    assert adapter.turn == "ended"
    with pytest.raises(HarnessError):
        adapter.send("Too late.")
    assert fake.posts == [] and adapter.turn == "ended" and not adapter.inspect()["alive"]
