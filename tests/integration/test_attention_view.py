"""A-44 slice S1 end to end (register E101): a waiting G3 approval, recorded by its client, is first in the
dashboard's overview on contract 0.1.3 unchanged, and `aew status` lists the same items, from the same module, with
the dashboard stopped. Nothing reaches G3: only ``request.sock``'s path is checked.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from aew import g3client as C
from aew import g3records as R
from aew.cli.main import main
from aew.dashboard import contract as CT
from aew.dashboard.etag import stamp
from aew.dashboard.projections import OVERVIEW_ATTENTION, Projector
from aew.dashboard.reader import StateReader
from aew.dashboard.reasons import REASONS, codes_in
from aew.engine.api import Engine

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)


@pytest.fixture
def g3_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This host as one with G3: a ``request.sock`` path that exists (a plain file: nothing may connect to it)."""
    sock = tmp_path / "request.sock"
    sock.touch()
    monkeypatch.setattr(C, "REQUEST_SOCK", str(sock))
    return sock


def _start(ref: str, *, life_s: float = 300, project: str | None = "calc") -> R.Writer:
    pending = {"approval_ref": ref, "state": "PENDING",
               "expires_at": R._iso(datetime.now(UTC) + timedelta(seconds=life_s)),
               "rendering": [{"template_id": "g3:action:SET_STEERING_MODE", "values": {},
                              "source": {"kind": "TEMPLATE"}}]}
    return R.Writer(pending, project=project)


def _escalate(project: Any, n: int) -> list[str]:
    """``n`` units the Lead must act on: existing alert events."""
    out = []
    for i in range(n):
        wid = project.lead("work", "create", "ticket", "--title", f"t{i}", "--class", "1")["id"]
        project.lead("work", "transition", wid, "--to", "REPLAN_REQUIRED", "--reason", "needs a decision")
        out.append(wid)
    return out


def test_a_waiting_approval_is_first_in_the_overview_and_status_lists_the_same_items_with_the_dashboard_stopped(
        project: Any, g3_host: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """BOY-Q06, BOY-Q16, BOY-Q18, BOY-Q19, BOY-Q01's runtime spy."""
    _escalate(project, OVERVIEW_ATTENTION + 1)
    _start("g3:approval:waiting")
    finished = _start("g3:approval:done")
    finished.finish("declined")
    connects: list[Any] = []
    real = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", lambda self, addr: connects.append(addr) or real(self, addr))

    engine = Engine.discover(project.root)
    projector = Projector(StateReader(engine).snapshot(), route="/overview")
    overview = stamp(projector.overview(), "2026-11-27T12:00:00Z")  # as the server stamps the read's time in
    assert CONTRACT.violations("OverviewResponse", overview) == [], CONTRACT.violations("OverviewResponse", overview)
    assert codes_in(overview) <= set(REASONS)
    shown = overview["data"]["attention"]
    assert len(shown) == OVERVIEW_ATTENTION and shown[0]["id"] == "AT-g3-g3.approval.waiting"
    assert (shown[0]["kind"], shown[0]["severity"]) == ("decision_required", "high")
    assert "g3:approval:waiting" in shown[0]["summary"]["text"]
    counted = overview["data"]["counts"]["attention"]
    assert counted == OVERVIEW_ATTENTION + 2  # the escalations and the waiting approval; the declined one is FYI
    assert f"{counted} needing attention" in overview["data"]["summary"]["text"]

    # `aew status`, in this process, with no dashboard running: the same items, tiers, order and keys
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    assert main(["-C", str(project.root), "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)["attention"]
    site = projector.attention_view()
    assert [(i["key"], i["tier"], i["id"]) for i in status["items"]] == [
        (i["key"], i["tier"], i["id"]) for i in site["items"]]
    assert [i["id"] for i in status["items"]][:OVERVIEW_ATTENTION] == [a["id"] for a in shown]
    assert status["items"][-1]["key"] == "g3:approval:done" and status["items"][-1]["tier"] == "fyi"
    assert main(["-C", str(project.root), "status"]) == 0
    text = capsys.readouterr().out
    assert "[blocked-on-you] G3 approval: SET_STEERING_MODE" in text and "Decide in AEW approvals" in text
    assert str(g3_host) not in map(str, connects), connects  # request.sock is only checked, never connected to


def test_on_a_host_without_g3_the_overview_says_so_and_counts_nothing_for_it(
        project: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(C, "REQUEST_SOCK", str(tmp_path / "absent.sock"))
    _start("g3:approval:waiting")  # a record, but no G3 here: nothing is read
    overview = Projector(StateReader(Engine.discover(project.root)).snapshot(), route="/overview").overview()
    assert overview["data"]["attention"] == [] and overview["data"]["counts"]["attention"] == 0
    assert overview["data"]["summary"]["text"].endswith(". G3 is not on this host")


def test_the_outage_readers_engine_items_never_include_an_approval(project: Any, g3_host: Path) -> None:
    """BOY-05.e: committed records only, so a G3 approval is never an outage read's item."""
    _start("g3:approval:waiting")
    projector = Projector(StateReader(Engine.discover(project.root)).snapshot())
    assert any(i["id"].startswith("AT-g3-") for i in projector.attention_items())
    assert not any(i["id"].startswith("AT-g3-") for i in projector.attention_items(host=False, contradictions=[]))


def test_the_403_reason_names_the_dashboard_half_of_the_typed_surface_projection() -> None:
    message = REASONS["AWAITS_ACTION_PROJECTION"]
    assert "register E18" in message and "F15.1" not in message
