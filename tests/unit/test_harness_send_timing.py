"""`aew harness send --when next-step|turn-end` (register E55; F9-A plan v4 amendment 2 §1.1, §1.4, §3.1, §3.3, §4):
the one mapping onto OpenCode's delivery modes, the help a Lead reads, and the route a send takes from the project's
messaging switch and the run's launch snapshot. The end-to-end cases, against fake V2, are
`tests/integration/test_harness_send_when.py`."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aew.coordination import layout as L
from aew.engine.harness_ops import run_messaging_snapshot, send_route
from aew.errors import HarnessSendNeedsStore, MessagingSnapshotMismatch, TurnEndNeedsMessaging
from aew.policy import execution as X

ROOT = Path(__file__).resolve().parents[2]
ON, OFF = X.MESSAGING_ENABLED, X.MESSAGING_DISABLED


def send_help(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> str:
    """`aew harness send --help` as printed, on one line: wide enough that argparse breaks no word at a hyphen."""
    from aew.cli.main import build_parser

    monkeypatch.setenv("COLUMNS", "10000")
    with pytest.raises(SystemExit):
        build_parser().parse_args(["harness", "send", "--help"])
    return " ".join(capsys.readouterr().out.split())


def test_when_maps_to_exactly_steer_and_queue():
    """One constant maps the timings onto OpenCode's modes (§1.1): `next-step` is `steer`, `turn-end` is `queue`, and
    the default is `next-step` (the designer's Q3). The supervisor posts a request-file send through it, never a
    literal mode."""
    assert L.WHEN_DELIVERY == {"next-step": "steer", "turn-end": "queue"}
    assert (L.NEXT_STEP, L.TURN_END, L.DEFAULT_WHEN) == ("next-step", "turn-end", "next-step")
    # defined in a leaf outside coordination, so `harness send` never imports coordination (F9 invariant 1), and
    # re-exported by the coordination layout for the F9 side: one object, never two copies
    from aew.harness import delivery as D

    assert L.WHEN_DELIVERY is D.WHEN_DELIVERY and L.DEFAULT_WHEN == D.DEFAULT_WHEN
    supervisor = (ROOT / "src/aew/harness/supervisor.py").read_text(encoding="utf-8")
    sends = [n for n in ast.walk(ast.parse(supervisor)) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "send"
             and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "adapter"]
    assert len(sends) == 1 and ast.unparse(sends[0].args[1]) == "WHEN_DELIVERY[NEXT_STEP]"
    assert all(not (isinstance(c, ast.Constant) and c.value in ("steer", "queue")) for c in ast.walk(sends[0]))


def test_harness_send_help_states_both_timings_and_their_order(capsys, monkeypatch):
    """The help a Lead reads (§4, §1.4) names both timings and the default, says why `turn-end` is unavailable while
    messaging is off, gives the order between and within the timings, the limit in both configurations, the evidence
    rule and what a send is with messaging on. It is static: the same with messaging on or off."""
    text = send_help(capsys, monkeypatch)
    for phrase in ("`next-step` (default) at its next step boundary, without interrupting it",
                   "`turn-end` after its current turn",
                   "`turn-end` is unavailable unless the project has enabled coordination messaging, because it needs "
                   "the F9 message store; while messaging is off it is refused",
                   "`next-step` messages arrive in the order they were sent, and so do `turn-end` messages, one at "
                   "each end of the agent's turn",
                   "a `next-step` message sent after a `turn-end` one arrives first",
                   "up to 1 MiB (4,000 characters when coordination messaging is on)",
                   "every send is recorded as a coordination message, and still wakes a held session",
                   "a report the worker submitted before receiving a message of either timing is not final until it "
                   "submits again",
                   "--when {next-step,turn-end}"):
        assert phrase in text, phrase
    assert "after its current step" not in text  # the old claim, true only of `steer`
    from aew.cli.main import build_parser

    harness = build_parser().parse_args(["harness", "send", "R-INV-0001-1", "--text", "x"])
    assert harness.when == "next-step"


@pytest.mark.parametrize("when", [L.NEXT_STEP, L.TURN_END])
def test_send_route_decides_every_cell_and_refuses_all_but_the_request_file(when):
    """§3.1's two values: both off is the request file for `next-step` and `TURN_END_NEEDS_MESSAGING` for `turn-end`;
    both on is `HARNESS_SEND_NEEDS_STORE` until MS5b; a disagreement is `MESSAGING_SNAPSHOT_MISMATCH` either way."""
    if when == L.NEXT_STEP:
        assert send_route(OFF, OFF, when) == "request"
    else:
        with pytest.raises(TurnEndNeedsMessaging) as refused:
            send_route(OFF, OFF, when)
        assert "--when next-step" in refused.value.message and "operator to enable messaging" in refused.value.message
    with pytest.raises(HarnessSendNeedsStore) as refused:
        send_route(ON, ON, when)
    assert "not yet available" in refused.value.message and "nothing was sent" in refused.value.message
    for project, snapshot in ((ON, OFF), (OFF, ON)):
        with pytest.raises(MessagingSnapshotMismatch) as refused:
            send_route(project, snapshot, when)
        assert refused.value.details == {"project": project, "snapshot": snapshot, "when": when}
        if project == ON:  # before MS4 a relaunch never clears it: every run reads as launched off
            assert "relaunch" not in refused.value.message.lower()
            assert "needs messaging switched off" in refused.value.message
        else:  # the project is off: a relaunched run reads as launched off, so it agrees with the project
            assert "Relaunch the run (`aew harness launch`)" in refused.value.message
            assert "needs messaging switched off" not in refused.value.message


def test_until_ms4_writes_the_snapshot_every_run_reads_as_launched_off():
    """The HS1 and MS4 coupling (§3.1, §7): the snapshot is MS4's, so no run carries one yet, and an absent snapshot
    reads as off. MS4 replaces the accessor with the real read, and this test with its own."""
    for entry in ({}, {"run": "R-INV-0001-1", "harness": "opencode"}):
        assert run_messaging_snapshot(entry) == OFF
