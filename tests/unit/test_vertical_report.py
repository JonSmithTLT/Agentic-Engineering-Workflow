"""A scenario of the `vertical` lane that ends before its verdict is **not measured**, never a fail (the designer's
addendum 1 to the oracle's hand-off, outcome 9): it counts in no counter and against no threshold, and the lane's
report leads with the not-measured count. And on Linux the scripted operator's session runs on a terminal it owns, as
CS-4's contained Lead requires."""

from __future__ import annotations

import json
import os
import subprocess
import sys

from conftest import IS_WINDOWS
from vertical import ledger as L
from vertical import report as R
from vertical.scripted_operator import start_on_terminal

LEAD_DID_NOT_START = ("the Lead session did not start: USAGE: the contained Lead's TUI runs on a terminal AEW relays "
                      "(STG-05 CS-4)")


def _scenario(error: BaseException | None) -> L.Ledger:
    """A scenario's body that counted something, then ended (``error`` escaping it, or not), its ledger written in
    the ``finally`` around it as the acceptance module writes it."""
    led = L.Ledger("V1", platform="linux", pin_budget=3)
    led.count("credentials", {"input": "export AEW_LEAD_TOKEN=<credential>"}, actor="operator", step="open")
    try:
        try:
            if error is not None:
                raise error
        finally:
            led.ended_by(sys.exc_info()[1])
    except AssertionError:
        pass
    return led


def test_a_scenario_that_errors_before_its_verdict_is_not_measured_and_counts_in_no_counter():
    led = _scenario(AssertionError(LEAD_DID_NOT_START))
    found = led.to_json()
    assert found["measured"] is False and found["counts"] is None and led.over() == {}
    assert "did not start" in found["not_measured"]["error"] and found["entries"]  # the evidence stays
    lines = led.summary().splitlines()
    assert lines[0].startswith("NOT MEASURED (errored before its verdict): AssertionError: the Lead session")
    assert "operator: " not in led.summary() and "counters: none counted (not measured)" in lines


def test_a_scenario_that_reaches_its_verdict_and_fails_still_reports_failed():
    led = _scenario(None)
    assert led.to_json()["measured"] is True and led.not_measured is None
    assert led.over() == {"credentials": 1} and led.summary().startswith("vertical UAT V1 (linux")


def _lane(tmp_path, scenarios: dict[str, L.Ledger | None], passed: frozenset[str] = frozenset()):
    """A lane's output: the JUnit report of ``scenarios`` and the ledger each wrote (None: it wrote none)."""
    cases = "".join(f'<testcase classname="t" name="{name}">'
                    + ("" if name in passed else '<failure message="x"/>') + "</testcase>" for name in scenarios)
    (tmp_path / "junit.xml").write_text(f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>',
                                        encoding="utf-8")
    for name, led in scenarios.items():
        if led is not None:
            led.write(tmp_path / L.ledger_dir_name(name))


def test_the_lanes_report_leads_with_the_not_measured_count(tmp_path):
    failed = _scenario(None)
    failed.hard_limit("containment", L.HELD, lead="os_readonly_roots")
    _lane(tmp_path, {"test_v1[steering-off]": failed, "test_v2[exit]": _scenario(AssertionError(LEAD_DID_NOT_START)),
                     "test_v3[stale]": None})
    text = R.report(tmp_path)
    assert text.splitlines()[0] == "### vertical (linux): not measured: 2 of 3"
    assert "measured 1: 0 passed their verdict, 1 failed it" in text
    assert "| test_v1[steering-off] | failed | os_readonly_roots | - |" in text  # the Lead's label, as recorded
    assert "| test_v2[exit] | not measured | - | AssertionError: the Lead session did not start" in text
    assert "| test_v3[stale] | not measured | - | no ledger (it ended before its verdict" in text
    assert text.count("```") == 4  # the two ledgers' own summaries follow


def test_a_run_that_measured_nothing_says_so_in_its_first_words(tmp_path):
    _lane(tmp_path, {f"test_v{n}": _scenario(AssertionError(LEAD_DID_NOT_START)) for n in range(3)})
    assert R.report(tmp_path).startswith("### vertical (linux): not measured: 3 of 3 (nothing was measured)")
    assert R.report(tmp_path / "absent").startswith("### vertical (")  # no output at all reports, never raises


def test_the_report_without_a_junit_report_counts_the_ledgers_it_finds(tmp_path):
    _lane(tmp_path, {"test_v1": _scenario(None), "test_v2": _scenario(AssertionError("setup raised"))})
    (tmp_path / "junit.xml").unlink()
    text = R.report(tmp_path)
    assert text.startswith("### vertical (linux): not measured: 1 of 2") and "no JUnit report" in text
    assert json.loads((tmp_path / "test_v2" / "vertical-ledger.json").read_text(encoding="utf-8"))["counts"] is None


def test_the_operators_session_runs_on_a_terminal_it_owns_on_linux(tmp_path):
    """CS-4's own check (``os.isatty(0)``), in the process the scripted operator starts: on Linux its stdin is the
    pseudo-terminal the test owns, whose master is open until the test closes it; on Windows it has none (no relay)."""
    out, err = tmp_path / "out", tmp_path / "err"
    with out.open("wb") as o, err.open("wb") as e:
        proc, master = start_on_terminal([sys.executable, "-c", "import os, sys; sys.exit(0 if os.isatty(0) else 3)"],
                                         env=dict(os.environ), stdout=o, stderr=e)
    try:
        code = proc.wait(60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)
        raise
    finally:
        if master is not None:
            os.close(master)
    assert (master is None) == IS_WINDOWS
    if not IS_WINDOWS:  # on Windows NUL is a character device, which isatty reports as one: the check is Linux's
        assert code == 0, err.read_text(encoding="utf-8", errors="replace")
