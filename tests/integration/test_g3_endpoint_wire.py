"""The raise at the operator endpoint on G3's real wire: the service on its real sockets with a stand-in PIN, the
confirmer's core on ``confirm.sock``, the real client, endpoint and standing. Only condition 3's register and the
confirmer's install path are stood in. The rules run on both platforms in ``test_g3_endpoint_adapter.py``."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from aew import errors, g3client, g3standing
from aew.engine import steering
from aew.engine.api import Engine
from aew.harness import operator_client, operator_endpoint
from aew.stg02 import adopted
from g3 import PIN, make

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="G3's sockets are Unix filesystem sockets")

MODE = "walk"
ENDED = 20.0
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def world(project, tmp_path, monkeypatch):
    from aew_g3 import server
    from aew_g3.service import utcnow

    path = project.root / ".aew/policy/execution.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    doc["steering"] = {"mode": "crawl"}
    doc["containment"] = {**(doc.get("containment") or {}), "mode": "required", "network": {"mode": "proxy_only"}}
    path.write_bytes(yaml.safe_dump(doc).encode())
    project.adopt_policy()
    g3 = server.G3Server(make(tmp_path / "g3", clock=utcnow).svc, server.bind_sockets(tmp_path / "run"))
    g3.start()
    monkeypatch.setattr(g3client, "REQUEST_SOCK", str(tmp_path / "run" / "request.sock"))
    confirmer = tmp_path / "aew-g3-confirm"
    confirmer.write_bytes(b"")
    monkeypatch.setattr(g3standing, "CONFIRMER", str(confirmer))
    monkeypatch.setattr(g3standing, "no_weaker_context", lambda now=None: None)
    lines: list[str] = []
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=lines.append, dev=True, timeout=30)
    ep.start()
    try:
        yield SimpleNamespace(project=project, confirm=str(tmp_path / "run" / "confirm.sock"), lines=lines, ep=ep,
                              root=project.root / ".aew")
    finally:
        ep.close()
        g3.stop()


def _confirmer(world: Any, decide: bool = True) -> threading.Thread:
    """The operator at the real confirmer's core, on the real confirm socket."""
    from aew_g3_confirm import core

    def run() -> None:
        deadline = time.monotonic() + ENDED
        while time.monotonic() < deadline:
            pending = core.list_pending(world.confirm)
            if pending:
                core.decide(pending[0]["approval_ref"], PIN if decide else None, world.confirm)
                return
            time.sleep(0.05)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def _no_typing(prompt: str) -> str:
    raise AssertionError("no code is typed on the G3 path")


def _raise(world: Any) -> dict[str, Any]:
    return operator_client.request_raise(world.root, MODE, ask=_no_typing, requester="test")


def _mode(world: Any) -> str | None:
    return steering.effective(Engine.discover(world.project.root).store.current())["mode"]


def _wait_for(done: Any) -> None:
    deadline = time.monotonic() + ENDED
    while not done():
        assert time.monotonic() < deadline, "it did not end"
        time.sleep(0.02)


def test_a_pin_approval_on_the_real_wire_raises_and_the_console_shows_it(world):
    t = _confirmer(world)
    out = _raise(world)
    t.join(ENDED)
    assert out["mode"] == MODE and _mode(world) == MODE
    assert any("steering mode raised" in line for line in world.lines)


def test_a_decline_on_the_real_wire_raises_nothing(world):
    t = _confirmer(world, decide=False)
    with pytest.raises(errors.OperatorAuthorizationRequired):
        _raise(world)
    t.join(ENDED)
    assert _mode(world) != MODE


def test_a_requester_that_has_gone_ends_the_wait_and_its_approval_raises_nothing(world):
    conn = operator_client._connect(world.root)
    operator_client._send(conn, "mode_raise", {"mode": MODE, "requester": "test"})
    approval = operator_client._reply(conn)["approval_ref"]
    conn.close()  # the operator pressed Ctrl-C
    _wait_for(lambda: any("has gone" in line for line in world.lines))
    assert any(approval in line for line in world.lines), world.lines

    _confirmer(world).join(ENDED)  # the abandoned approval, approved late, is what the operator finds on the confirmer
    time.sleep(0.2)
    assert _mode(world) != MODE, "nothing consumes an abandoned approval"

    t = _confirmer(world)
    assert _raise(world)["mode"] == MODE, "the endpoint is free again"
    t.join(ENDED)


def test_a_service_older_than_the_overlay_holds_and_names_the_reinstall(world, monkeypatch):
    from aew_g3 import wire as service_wire

    monkeypatch.setattr(service_wire, "o01_errors", lambda body: adopted.o01_errors("CommandSet", body))
    with pytest.raises(errors.Unavailable) as held:
        _raise(world)
    assert g3standing.INSTALL in held.value.message and "STRUCTURAL" in held.value.message
    assert not re.search("confirmation code", "".join(world.lines)), "held, never the code"


def test_the_runbooks_replay_script_consumes_once_and_is_refused_the_second_time(world, capsys):
    """The runbook's script, from the runbook: no command makes a replay, so a host's acceptance runs this."""
    text = (ROOT / "g3" / "README.md").read_text(encoding="utf-8")
    script = re.search(r"```python\n(.*?)```", text[text.index("### Acceptance on a real host"):], re.S).group(1)
    t = _confirmer(world)
    exec(compile(script, "g3/README.md", "exec"), {})  # noqa: S102 - the repository's own runbook
    t.join(ENDED)
    printed = capsys.readouterr().out.splitlines()
    assert printed[-2:] == ["CONSUMED", "CONSENT_ALREADY_USED"], json.dumps(printed)
    assert _mode(world) != MODE
