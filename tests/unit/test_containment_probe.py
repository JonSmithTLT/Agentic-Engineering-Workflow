"""The launch self-test's judgement (STG-05 CB-12, rows 2 to 5), on synthetic probe output.

Pure: nothing starts bubblewrap, so it runs on every platform. The rows on a real sandbox, and each failing closed when
a protection is taken out, are in tests/integration/test_containment.py. Row 4 is judged here only: every test's
launcher has no controlling terminal, so a sandbox that forgot its new session cannot show one there.
"""

from __future__ import annotations

import pytest

from aew.harness.containment import layout as L
from aew.harness.containment import probe, sockets

LAYOUT = L.Layout(role="reviewer", access="read", bwrap="/usr/bin/bwrap", writable=("/runs/R-1/scratch",),
                  readonly=(), hide_runs=("/runs",), hide_host=("/run",), run_exceptions=())
GOOD = {
    "host_masks": {"/run": {"type": "tmpfs", "readonly": True, "extra": []}},
    "var_run": "/run",
    "inventory": {"sockets": ["/var/lib/sss/pipes/nss"], "walked": 1000, "unlistable": 2, "unwalked_mounts": [],
                  "seconds": 0.5, "complete": True},
    "display_files": {"/home/u/.Xauthority": "empty"},
    "env_set": [],
    "terminal": {"tty_nr": 0, "dev_tty": "ENXIO", "session_leader": True},
}


@pytest.fixture(autouse=True)
def no_host_facts(monkeypatch):
    monkeypatch.setattr(probe, "host_masks", lambda: ("/run",))  # whatever host runs this


def test_a_good_sandbox_passes_rows_2_to_4_with_their_facts():
    assert probe._row2(LAYOUT, GOOD, own=(), env={})["ok"] is True
    assert probe._row2(LAYOUT, GOOD, own=(), env={})["sockets"] == [{"path": "/var/lib/sss/pipes/nss",
                                                                      "class": sockets.REPORTED}]
    assert probe._row3(GOOD)["ok"] is True
    assert probe._row4(GOOD) == {"name": "terminal", "ok": True, "reason": None, **GOOD["terminal"]}


@pytest.mark.parametrize(("change", "says"), [
    ({"terminal": {"tty_nr": 34816, "dev_tty": "opened", "session_leader": True}}, "controlling terminal"),
    ({"terminal": {"tty_nr": 0, "dev_tty": "ENXIO", "session_leader": False}}, "own session"),
    ({"terminal": {}}, "controlling terminal"),  # nothing reported: fails closed
])
def test_row_4_fails_closed_on_a_controlling_terminal_or_a_shared_session(change, says):
    row = probe._row4({**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]


@pytest.mark.parametrize(("change", "says"), [
    ({"host_masks": {"/run": {"type": "ext4", "readonly": True, "extra": []}}}, "not a read-only tmpfs"),
    ({"host_masks": {"/run": {"type": "tmpfs", "readonly": False, "extra": []}}}, "not a read-only tmpfs"),
    ({"host_masks": {"/run": {"type": "tmpfs", "readonly": True, "extra": ["/run/dbus"]}}}, "did not put there"),
    ({"host_masks": {}}, "not a read-only tmpfs"),  # nothing reported: fails closed
    ({"var_run": "/srv/run"}, "outside the masked"),
    ({"inventory": {**GOOD["inventory"], "complete": False}}, "did not finish"),
    ({"inventory": {**GOOD["inventory"], "sockets": ["/run/dbus/system_bus_socket"]}}, "escape socket"),
])
def test_row_2_fails_closed(change, says):
    row = probe._row2(LAYOUT, {**GOOD, **change}, own=(), env={})
    assert row["ok"] is False and says in row["reason"]


def test_row_2_checks_the_hosts_run_even_when_the_layout_lost_its_mask():
    """The row asks the host which trees are masked whole, not only the layout: a layout without its /run mask fails."""
    lost = L.Layout(role="reviewer", access="read", bwrap="/usr/bin/bwrap", writable=(), readonly=(), hide_host=())
    row = probe._row2(lost, {**GOOD, "host_masks": {"/run": {"type": "tmpfs", "readonly": False, "extra": ["/x"]}}},
                      own=(), env={})
    assert row["ok"] is False and "/run" in row["reason"]


@pytest.mark.parametrize(("change", "says"), [
    ({"display_files": {"/home/u/.Xauthority": "readable"}}, "is readable"),
    ({"env_set": ["DISPLAY"]}, "DISPLAY reaches"),
])
def test_row_3_fails_closed(change, says):
    row = probe._row3({**GOOD, **change})
    assert row["ok"] is False and says in row["reason"]
