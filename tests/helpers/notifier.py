"""Helpers for the operator notifier's tests (M4-E E7a): a recording notifier, adopting a policy with a notifier, the
operator's raise as the endpoint commits it, seeding control state, and a bounded wait."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aew.engine.api import Engine
from aew.engine.steering import OperatorPrincipal
from aew.engine.store import Transition
from aew.harness import procs

IS_WINDOWS = sys.platform == "win32"

RECORDER = """\
import sys
data = sys.stdin.read()
with open(sys.argv[1], "a", encoding="utf-8") as fh:
    fh.write(data if data.endswith("\\n") else data + "\\n")
"""


def script(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return str(path)


def recorder(tmp_path: Path) -> tuple[list[str], Path]:
    """A notifier that appends each event it receives to ``notified.jsonl``: its argv, and that file."""
    out = tmp_path / "notified.jsonl"
    return [sys.executable, "-I", script(tmp_path, "recorder", RECORDER), str(out)], out


def received(out: Path) -> list[dict[str, Any]]:
    if not out.exists():
        return []
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]


def adopt(project: Any, *, mode: str | None = "crawl", command: list[str] | None = None, **notify_cfg: Any) -> Engine:
    """Adopt an execution policy with a steering mode and a notifier, as the operator would."""
    path = project.root / ".aew" / "policy" / "execution.yaml"
    text = path.read_text(encoding="utf-8").split("\n# --- e7a test ---\n")[0]
    extra = f"steering:\n  mode: {mode}\n" if mode else ""
    if command:
        extra += "notify:\n  command: " + json.dumps(command) + "\n"
        extra += "".join(f"  {k}: {v}\n" for k, v in notify_cfg.items())
    path.write_text(text + "\n# --- e7a test ---\n" + extra, encoding="utf-8")
    project.adopt_policy()
    return Engine.discover(project.root)


def raise_to(engine: Engine, mode: str) -> None:
    """The operator's raise, as the endpoint commits it after its challenge (E2's tests make it the same way)."""
    principal = OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                                  endpoint_pid=os.getpid(), endpoint_started_at="2026-10-10T00:00:00Z")
    bound = engine.steering_raise_preview(mode)
    engine.steering_raise(principal, mode=mode, generation=bound["generation"],
                          legality_digest=bound["legality_digest"])


def seed(project: Any, mutate: Any) -> None:
    """Put a condition into control state with one plain commit (the engine paths that make these conditions need a
    validation run or a custodian; the watcher only reads the state they leave)."""
    engine = Engine.discover(project.root)
    with engine.store.session() as s:
        mutate(s.state)
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="seeded for the notifier tests"))


def hidden() -> dict[str, Any]:
    """Popen arguments that never open a console window (Windows) and detach the child's session (POSIX)."""
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {"start_new_session": True}


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"], **hidden())
    proc.wait(30)
    assert not procs.pid_alive(proc.pid)
    return proc.pid


def until(predicate: Any, timeout: float = 30.0, what: str = "the condition") -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {what}")


def takeover(project: Any, monkeypatch: Any) -> None:
    """The operator's takeover, its terminal channel substituted in-process (as the takeover tests do)."""
    import aew.operator

    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **_: {"authorized_by": "operator-tty (test)"})
    project.token = Engine.discover(project.root).lead_takeover(expect_rev=project.rev(), reason="the test takes over",
                                                                session_label="operator")["token"]


def request(project: Any, kind: str) -> None:
    engine = Engine.discover(project.root)
    engine.steering_request(token=project.token, expect_rev=project.rev(), kind=kind, rationale="the test asks",
                            **({"mode": "walk"} if kind == "raise" else {"action_ref": "ticket_start:T-0001"}))


class Console:
    """The endpoint's console in-process: what it showed, and the last challenge code."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def __call__(self, text: str) -> None:
        self.lines.append(text)

    def code(self) -> str:
        found = re.findall(r"confirmation code ([0-9A-F]{6})", "".join(self.lines))
        assert found, self.lines
        return found[-1]
