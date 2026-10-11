"""F20: the second display layer behind the projections' allowlist applies the engine's credential redaction
(``aew.harness.contract.redact``) and its verifier masking to every response body the dashboard serves.

The credential-shaped string is minted by the engine in a temporary project (the Lead's own credential of a sample
project), so no credential appears in this file.
"""

from __future__ import annotations

import http.client
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import create_planned_ticket, create_unit, sample_project  # noqa: E402

from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard.server import DashboardServer  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.harness import contract as K  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
MARKER = K.redact("aew1.tk_" + "0" * 16 + "." + "x" * 20)  # the engine's own replacement text


class OpenAccess:
    """Test-only: every request may read."""

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        return None


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("display-redaction")
    p = sample_project(tmp)
    secret = p.token
    assert K.CREDENTIAL_RE.fullmatch(secret), "the sample project's credential has the engine's format"
    epic = create_unit(p, "epic", f"Calculator {secret}", cls=1)
    first = create_planned_ticket(p, tmp, title="Add apply()")
    second = create_planned_ticket(p, tmp, title="Add compose()")
    p.lead("work", "depend", second, "--add", f"{first}:mutating", "--reason", f"compose needs apply {secret}")
    server = DashboardServer(Engine.discover(p.root), authenticator=OpenAccess(), validate_with=CONTRACT)
    server.start()
    try:
        yield server, secret, {"epic": epic, "second": second}
    finally:
        server.stop()


def _get(server: DashboardServer, path: str) -> tuple[int, str]:
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=60)
    try:
        conn.request("GET", f"/api/v1{path}")
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8")
    finally:
        conn.close()


def test_the_second_display_layer_applies_the_engines_credential_redaction(served):
    server, secret, ids = served
    shown = {}
    for path in ("/work", f"/work/{ids['epic']}", f"/work/{ids['second']}", "/overview", "/activity"):
        status, text = _get(server, path)
        assert status == 200, (path, text)
        assert secret not in text, path
        shown[path] = MARKER in text
    # the routes that show the planted text show it redacted
    assert shown["/work"] and shown[f"/work/{ids['epic']}"] and shown["/activity"], shown


def test_an_error_body_passes_through_the_same_layer(served):
    server, secret, _ = served
    status, text = _get(server, f"/runs/{secret}")
    assert status == 404, text
    assert secret not in text and MARKER in text
