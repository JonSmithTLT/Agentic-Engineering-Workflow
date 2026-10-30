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
    assert "measured 1: 1 failed" in text
    assert "| test_v1[steering-off] | failed | os_readonly_roots | - |" in text  # the Lead's label, as recorded
    assert "| test_v2[exit] | not measured | - | AssertionError: the Lead session did not start" in text
    assert "| test_v3[stale] | not measured | - | no ledger (it ended before its verdict" in text
    assert text.count("```") == 4  # the two ledgers' own summaries follow


def test_a_run_that_measured_nothing_says_so_in_its_first_words(tmp_path):
    _lane(tmp_path, {f"test_v{n}": _scenario(AssertionError(LEAD_DID_NOT_START)) for n in range(3)})
    assert R.report(tmp_path).startswith("### vertical (linux): not measured: 3 of 3 (nothing was measured)")
    assert "not measured: unknown" in R.report(tmp_path / "absent").splitlines()[0]  # no output: reports, never raises


def test_the_report_without_a_junit_report_counts_the_ledgers_it_finds(tmp_path):
    _lane(tmp_path, {"test_v1": _scenario(None), "test_v2": _scenario(AssertionError("setup raised"))})
    (tmp_path / "junit.xml").unlink()
    text = R.report(tmp_path)
    first = text.splitlines()[0]
    assert first.startswith("### vertical (linux): not measured: unknown (pytest wrote no readable JUnit report")
    assert first.endswith("2 ledgers found, 1 of them not measured")  # the ledgers are listed, never the total
    assert "| test_v1 | verdict unknown |" in text and "measured 1: 1 verdict unknown" in text
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


def test_a_test_that_is_not_a_scenario_is_listed_apart_and_never_counted(tmp_path):
    """The #213 hang diagnosis writes no ledger by design: it records the not-a-scenario property, and the report lists
    it apart, so it is never "not measured" on a run that measured everything."""
    _lane(tmp_path, {"test_v1": _scenario(None)})
    junit = tmp_path / "junit.xml"
    extra = (f'<testcase classname="t" name="test_g3"><properties><property name="{R.NOT_A_SCENARIO}" '
             'value="the #213 hang diagnosis"/></properties><failure message="x"/></testcase>')
    junit.write_text(junit.read_text(encoding="utf-8").replace("</testsuite>", extra + "</testsuite>"),
                     encoding="utf-8")
    text = R.report(tmp_path)
    assert text.startswith("### vertical (linux): not measured: 0 of 1\n")
    assert "not scenarios (no ledger by design): test_g3 (failed; the #213 hang diagnosis)" in text


def test_with_no_report_and_no_ledger_the_count_is_unknown_never_zero(tmp_path):
    """Review of #307, F1: a run that left nothing says the count is unknown, never "0 of 0"; a JUnit report with no
    case says nothing was measured."""
    (tmp_path / "out").mkdir()
    first = R.report(tmp_path / "out").splitlines()[0]
    assert "not measured: unknown" in first and "0 ledgers found" in first
    (tmp_path / "out" / "junit.xml").write_text("<testsuites><testsuite/></testsuites>", encoding="utf-8")
    assert R.report(tmp_path / "out").splitlines()[0].endswith("not measured: 0 of 0 (nothing was measured)")


def test_on_windows_the_summary_leads_with_its_unqualified_state(tmp_path):
    """Review of #307, F2 (the operator's Q1(e)): outside the enforced gate the first words are the unqualified state,
    the count after it on the same line."""
    win = L.Ledger("V1", platform="win32")
    win.ended_by(RuntimeError("setup raised"))
    _lane(tmp_path, {"test_v1": win})
    assert R.report(tmp_path).splitlines()[0] == (f"### {L.WINDOWS_UNQUALIFIED}. vertical (win32): not measured: 1 of 1"
                                                  " (nothing was measured)")


def test_on_windows_the_conditions_still_open_come_before_the_first_scenario(tmp_path):
    """Q1(e) conformance (#307's quick check, noted): every Windows summary leads with its unqualified state and the
    conditions still open, so the conditions sit at the top, before the table and the first ledger's block."""
    failed = L.Ledger("V1", platform="win32")
    failed.ended_by(None)
    _lane(tmp_path, {"test_v1": failed})
    lines = R.report(tmp_path).splitlines()
    conditions = next(i for i, line in enumerate(lines) if "open conditions:" in line)
    assert all(c in lines[conditions] for c in L.WINDOWS_OPEN_CONDITIONS)
    assert conditions < lines.index("| Scenario | Result | Lead label | Why not measured |") < lines.index("```")
    _lane(tmp_path, {"test_v1": _scenario(None)})  # an enforced platform carries none
    assert "open conditions:" not in R.report(tmp_path)


def test_a_reason_or_a_ledger_that_would_break_the_table_never_does(tmp_path):
    """Review of #307, F3 and F4: a multi-line reason with a pipe stays one cell; an unreadable ledger is not measured;
    an unreadable JUnit report is an unknown count."""
    _lane(tmp_path, {"test_v1": _scenario(AssertionError("first line | a pipe\nsecond line")),
                     "test_v2": _scenario(None)})
    (tmp_path / "test_v2" / "vertical-ledger.json").write_text("{not json", encoding="utf-8")
    text = R.report(tmp_path)
    assert "| test_v1 | not measured | - | AssertionError: first line \\| a pipe second line |" in text
    assert "| test_v2 | not measured | - | unreadable ledger |" in text
    (tmp_path / "junit.xml").write_text("<testsuites", encoding="utf-8")
    assert "not measured: unknown" in R.report(tmp_path).splitlines()[0]


def test_a_teardown_error_is_never_read_as_a_failed_verdict(tmp_path):
    """Review of #307, F8: a scenario that passed its call and errored in its teardown reads so, never "failed"."""
    _lane(tmp_path, {"test_v1": _scenario(None)}, passed=frozenset({"test_v1"}))
    junit = tmp_path / "junit.xml"
    junit.write_text(junit.read_text(encoding="utf-8").replace(
        "</testcase>", '<error message="failed on teardown with &quot;OSError&quot;"/></testcase>'), encoding="utf-8")
    assert "| test_v1 | passed, errored in teardown |" in R.report(tmp_path)
