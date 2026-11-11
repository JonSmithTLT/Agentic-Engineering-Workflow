"""A scenario of the `vertical` lane that ends before its verdict is **not measured**, never a fail (the designer's
addendum 1 to the oracle's hand-off, outcome 9): it counts in no counter and against no threshold, and the lane's
report leads with the not-measured count. And on Linux the scripted operator's session runs on a terminal it owns, as
CS-4's contained Lead requires. Then the scoreboard (register E115): the V-01 line, whether anything moved, and the
series of main's runs."""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys

from conftest import IS_WINDOWS
from lanes import VERTICAL_PATH
from vertical import ledger as L
from vertical import oracle as O
from vertical import report as R
from vertical import scoreboard as S
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
    assert "Alpha scripted gate: FAIL" in text
    assert text.count("```") == 6  # alpha and the two ledgers' own summaries


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
    assert sum(L.WINDOWS_UNQUALIFIED in line for line in lines[:conditions]) == 1  # stated once (review of #308, n1)
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


# ------------------------------------------------------------------------------- the scoreboard (register E115)


def _led(states: dict[str, str] | None = None, *, reached: bool | None = False, asked: bool = True,
         platform: str = "linux") -> L.Ledger:
    """A scenario's ledger that reached its verdict: every step not built but ``states``, and its result's observation
    (``reached`` None: an older ledger, with none)."""
    led = L.Ledger("V1", platform=platform)
    led.steps = [{"step": s.n, "key": s.key, "state": (states or {}).get(s.key, O.NOT_BUILT)} for s in O.STEPS]
    if reached is not None:
        led.observe(L.RESULT_REACHED, reached=reached, asked=asked)
    led.ended_by(None)
    return led


def _main_run(n: int, *, ref: str = S.MAIN_REF) -> S.Run:
    return S.Run(str(n), f"{n:040x}", f"2026-11-{n:02d}", ref)


def _row(n: int, *, passing: int | None = 0, measured: bool = True, total: int = 17, of: int | None = None) -> dict:
    """A line of the series: ``of`` is how many of the ``total`` in its JUnit report were measured (all, by default)."""
    identity = {"run": str(n), "sha": f"{n:040x}", "date": f"2026-11-{n:02d}", "measured": measured}
    if not measured:
        return {**identity, "why": "every scenario ended before its verdict"}
    return {**identity, "passing": passing, "total": total, "scenarios_measured": total if of is None else of,
            "v1_landed": 1, "v1_of": 8}


def _seed_series(directory, rows: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / S.SERIES).write_bytes("".join(json.dumps(r) + "\n" for r in rows).encode())


def _board_row(text: str, label: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"| {label}"))


def _series(directory) -> list[dict]:
    return [json.loads(line) for line in (directory / S.SERIES).read_bytes().decode().splitlines()]


def test_the_v01_line_is_the_second_line_on_every_path(tmp_path):
    """The designer: the V-01 line always leads, so alpha can't read as V-01. A run that measured, one that measured
    nothing, one with no JUnit report, one with no output at all, and Windows."""
    v01 = "**V-01 is not met:**"
    measured, nothing, no_junit, win = (tmp_path / d for d in ("measured", "nothing", "no-junit", "win"))
    for d in (measured, nothing, no_junit, win):
        d.mkdir()
    _lane(measured, {"test_v1": _led()})
    assert R.report(measured).splitlines()[1] == (f"{v01} 0 of 1 scenarios pass, and this job stays red until every "
                                                  "scenario passes.")
    _lane(nothing, {"test_v1": _scenario(AssertionError(LEAD_DID_NOT_START))})
    assert R.report(nothing).splitlines()[1].startswith(f"{v01} 0 of 1 scenarios pass")
    _lane(no_junit, {"test_v1": _led()})
    (no_junit / "junit.xml").unlink()
    assert R.report(no_junit).splitlines()[1].startswith(f"{v01} how many scenarios pass is unknown this run")
    assert R.report(tmp_path / "absent").splitlines()[1].startswith(v01)
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "junit.xml").write_text("<testsuites><testsuite/></testsuites>", encoding="utf-8")
    assert R.report(tmp_path / "empty").splitlines()[1].startswith(f"{v01} 0 of 0")  # no scenario is never "all pass"
    _lane(win, {"test_v1": _led(platform="win32")})
    lines = R.report(win).splitlines()
    assert lines[0].startswith(f"### {L.WINDOWS_UNQUALIFIED}. vertical (win32)") and lines[1].startswith(v01)
    assert "open conditions:" in lines[3] and lines.index("| Measure | Now | Flat since |") > 3


def test_only_every_scenario_passing_reads_as_all_passing_and_enforcing_stays_the_operators(tmp_path):
    (tmp_path / "all").mkdir()
    _lane(tmp_path / "all", {"test_v1": _led(), "test_v2": _led()}, passed=frozenset({"test_v1", "test_v2"}))
    line = R.report(tmp_path / "all", pytest=S.PYTEST_FINISHED).splitlines()[1]
    assert line == "**Every scenario passes (2 of 2).** Enforcing this job is the operator's decision."
    (tmp_path / "one").mkdir()
    _lane(tmp_path / "one", {"test_v1": _led(), "test_v2": _led()}, passed=frozenset({"test_v1"}))
    assert R.report(tmp_path / "one", pytest=S.PYTEST_FINISHED).splitlines()[1].startswith(
        "**V-01 is not met:** 1 of 2 scenarios pass")
    (tmp_path / "win").mkdir()
    _lane(tmp_path / "win", {"test_v1": _led(platform="win32")}, passed=frozenset({"test_v1"}))
    assert "outside the enforced gate" in R.report(tmp_path / "win", pytest=S.PYTEST_FINISHED).splitlines()[1]
    # A teardown error holds the job red, so it never reads as all passing
    (tmp_path / "torn").mkdir()
    _lane(tmp_path / "torn", {"test_v1": _led()}, passed=frozenset({"test_v1"}))
    junit = tmp_path / "torn" / "junit.xml"
    junit.write_text(junit.read_text(encoding="utf-8").replace(
        "</testcase>", '<error message="failed on teardown"/></testcase>'), encoding="utf-8")
    text = R.report(tmp_path / "torn", pytest=S.PYTEST_FINISHED)
    assert text.splitlines()[1].startswith("**V-01 is not met:** 0 of 1") and "| test_v1 | passed, errored in" in text
    assert "| Scenarios passing | 0 of 1 measured, 0 of 1 total |" in text


def test_the_scoreboard_shows_each_measure_and_no_counter_total(tmp_path):
    """V1's eight from the oracle's path, the others leaving out what is outside AEW and saying so. Counter totals are
    deliberately not on it: V2-forced fell from 56 to 32 because it stopped earlier, which is not progress."""
    states = {"init": O.BUILT, "exit": O.OUTSIDE, "preflight": O.SERVED}
    _lane(tmp_path, {"test_v1": _led(states), "test_v2": _led(states)})
    text = R.report(tmp_path, run=_main_run(3))
    board = text[:text.index("| Scenario |")]
    assert "| Scenarios passing | 0 of 2 measured, 0 of 2 total |" in board
    assert f"| V1's steps landed | 1 of {len(O.path('V1'))} |" in board
    others = len(O.STEPS) - len(O.path("V1")) - 1
    assert f"| The other steps landed | 1 of {others}, leaving out exit (outside AEW) |" in board
    assert "credentials" not in board and "counter" not in board.lower()
    assert _board_row(text, "V1's steps landed").endswith("| 2026-10-30 (#306, run 41120823321); 1 measured run in the "
                                                          "series, earlier runs not counted |")
    assert _board_row(text, "The other steps landed").endswith("| since the series began or restarted at run 3; any "
                                                               "earlier runs lost; 1 measured run |")
    _lane(tmp_path, {"test_v1": _led(states), "test_v2": _led(states)})
    _seed_series(tmp_path, [_row(1, total=2)])  # a series with no restart on its lines: the flat run's own date
    assert _board_row(R.report(tmp_path, run=_main_run(3)), "The other steps landed").endswith(
        "| 2026-11-03 (run 3); 1 measured run |")


def test_a_run_that_measured_nothing_is_marked_and_leaves_flat_since_alone(tmp_path):
    """The 40 hours from #283 to #307 cannot recur silently: the run is in the series, marked; flat since neither
    resets nor extends; and the scoreboard shows the last run that did measure, and says so."""
    _seed_series(tmp_path, [_row(1), _row(2)])
    _lane(tmp_path, {"test_v1": _scenario(AssertionError(LEAD_DID_NOT_START))})
    text = R.report(tmp_path, run=_main_run(3))
    assert _series(tmp_path)[-1]["measured"] is False and "passing" not in _series(tmp_path)[-1]
    assert "**This run measured nothing** (every scenario ended before its verdict)." in text
    assert f"the last run that measured the whole lane: run 2 (`{'0' * 8}`, 2026-11-02)." in text
    assert ("| Scenarios passing | 0 of 17 measured, 0 of 17 total | 2026-10-12 (run 38188158379); 2 measured runs"
            in text)
    assert "| 3 | `00000000` | 2026-11-03 | no: every scenario ended before its verdict |" in text
    (tmp_path / "junit.xml").unlink()  # a second, with no report: a passing count it cannot know is no data point
    text = R.report(tmp_path, run=_main_run(4))
    assert "**This run measured nothing** (pytest wrote no readable JUnit report)." in text
    assert "2 runs in a row have measured nothing, since 2026-11-03." in text
    assert "; 2 measured runs" in _board_row(text, "Scenarios passing")


def test_a_not_measured_line_that_carries_values_is_still_no_data_point():
    rows = [_row(1), {**_row(2, measured=False), "passing": 5}, _row(3)]
    assert S.flat(rows, S.PASSING, None) == S.Flat(0, "2026-11-01", "run 1", runs=2)


def test_a_value_that_falls_resets_flat_since_and_reads_as_fell(tmp_path):
    _seed_series(tmp_path, [_row(1, passing=3, total=2), _row(2, passing=3, total=2)])
    _lane(tmp_path, {"test_v1": _led(), "test_v2": _led()}, passed=frozenset({"test_v1"}))
    text = R.report(tmp_path, run=_main_run(3))
    assert _board_row(text, "Scenarios passing").endswith(
        "| fell from 3 by 2026-11-03 (run 3); 1 measured run at this value |")
    assert S.flat([_row(1, passing=1), _row(2, passing=2)], S.PASSING, None).moved == "rose"
    settled = S.flat([_row(1, passing=3), _row(2, passing=1), _row(3, passing=1)], S.PASSING, None)
    assert settled.moved == "fell" and settled.runs == 2 and settled.date == "2026-11-02"


def test_a_series_that_cannot_be_read_falls_back_to_the_seed_and_never_fails_the_step(tmp_path):
    _lane(tmp_path, {"test_v1": _led()})
    identity = '"run": "1", "sha": "x", "date": "d"'
    counts = '"measured": true, "passing": 0, "total": 1, "scenarios_measured": 1'
    for bad in (b"{not json\n", b"\xff\xfe\x00", b'{"run": "1"}\n', b"[1]\n", b"",
                f'{{{identity}, "measured": true, "passing": "many"}}\n'.encode(),
                # Each reads as a line until the display reads the field (the review of #324, F7)
                f'{{{identity}, "measured": true}}\n'.encode(),
                f'{{{identity}, "measured": true, "passing": 0, "total": 1}}\n'.encode(),
                f'{{{identity}, {counts}, "owed": 3}}\n'.encode(),
                f'{{{identity}, {counts}, "left_out": [1]}}\n'.encode(),
                f'{{{identity}, {counts}, "v1_mixed": ["plan"]}}\n'.encode(),
                f'{{{identity}, {counts}, "other_mixed": {{"plan": 1}}}}\n'.encode(),
                f'{{{identity}, {counts}, "restarted": true}}\n'.encode()):
        (tmp_path / S.SERIES).write_bytes(bad)
        text = R.report(tmp_path)
        assert "The series began or restarted from its seed:" in text, bad
        assert "2026-10-12 (run 38188158379)" in _board_row(text, "Scenarios passing"), bad
    (tmp_path / S.SERIES).write_bytes(f'{{{identity}, {counts}}}\n'.encode())  # what the bad ones are planted against
    assert "began or restarted" not in R.report(tmp_path)
    (tmp_path / S.SERIES).unlink()
    (tmp_path / S.SERIES).mkdir()  # neither readable nor writable: the report still reports
    text = R.report(tmp_path, run=_main_run(1))
    assert "The series began or restarted from its seed:" in text and "The series could not be saved:" in text
    assert "| Scenarios passing | 0 of 1 measured" in text


def test_with_nothing_measured_ever_the_seed_is_shown_as_the_seed(tmp_path):
    _lane(tmp_path, {"test_v1": _scenario(AssertionError(LEAD_DID_NOT_START))})
    text = R.report(tmp_path, run=_main_run(1))
    assert "No run in the series has measured, so the values below are the seed's." in text
    assert "| Scenarios passing | 0 (the seed's) |" in text and "| V1's steps landed | 1 (the seed's) |" in text
    assert "| The other steps landed | unknown | no run has recorded it yet |" in text


def test_windows_keeps_its_own_series_with_no_seed(tmp_path):
    win = L.Ledger("V1", platform="win32")
    win.ended_by(RuntimeError("setup raised"))
    _lane(tmp_path, {"test_v1": win})
    text = R.report(tmp_path, run=_main_run(1))
    assert "38188158379" not in text and "41120823321" not in text
    assert "The series began or restarted with no seed, as this platform has none:" in text
    assert "No run in the series has measured, so the values below are unknown." in text
    assert "| Scenarios passing | unknown | no run has recorded it yet |" in text


def test_a_ledger_with_no_result_observation_reads_unknown_never_no(tmp_path):
    (tmp_path / "old").mkdir()
    _lane(tmp_path / "old", {"test_v1": _led(reached=None)})
    text = R.report(tmp_path / "old")
    assert _board_row(text, "Reached a result").startswith(
        "| Reached a result, passing or not (no history before the first run that records it) | unknown (1 unknown) |")
    assert "| Reached, of those that ask |" in text  # what it counts: a report that fails the verdict still reached
    assert S.reached([L.Ledger("V1").to_json()])[S.REACHED] is None
    (tmp_path / "new").mkdir()
    _lane(tmp_path / "new", {"test_v1": _led(reached=True), "test_v2": _led(reached=False),
                             "test_v3": _led(asked=False), "test_v4": _led(reached=None)})
    assert "| 1 of the 2 measured that ask for one (1 not asked; 1 unknown) |" in R.report(tmp_path / "new")
    # A scenario that ended before its verdict counts for none of them
    (tmp_path / "part").mkdir()
    _lane(tmp_path / "part", {"test_v1": _led(reached=True), "test_v2": _scenario(AssertionError(LEAD_DID_NOT_START))})
    found, known, _ = R.rows(tmp_path / "part")
    line = R.run_row(found, known, None)
    assert (line[S.REACHED], line["reached_of"], line["reached_unknown"]) == (1, 1, 0)


def test_the_results_observation_touches_no_counter_and_no_threshold():
    led = L.Ledger("V1", platform="linux")
    led.observe(L.RESULT_REACHED, reached=False, asked=True)
    assert led.over() == {} and not any(led.counts().values()) and not led.entries


def test_the_observation_says_it_asks_for_a_result_exactly_where_the_verdict_does():
    """``write_out``'s ``asks_result`` restates what the scenario's verdict reads (the verdict runs after the ledger
    is written, so it cannot be read there): a scenario that stops before a result by design is not a "no"."""
    tree = ast.parse((O.ROOT / VERTICAL_PATH).read_text(encoding="utf-8"))
    tests = [f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name.startswith("test_v")]
    checked = 0
    for test in tests:
        calls = [n for n in ast.walk(test) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "write_out"]
        for call in calls:
            says = next((k.value.value for k in call.keywords if k.arg == "asks_result"), True)  # type: ignore[attr-defined]
            reads = any(isinstance(n, ast.Name) and n.id == "result_problems" for n in ast.walk(test))
            assert says == reads, test.name
            checked += 1
    assert checked >= 8


def test_write_out_records_whether_a_result_reached_the_operator_before_it_writes_the_ledger():
    """The review of #324, F6: nothing else reads the line, so nothing else would notice it gone or inverted. It is
    the writer of the "reached a result" row: what reached the operator is ``op.reports``, what asked is the argument,
    and an observation made after the ledger is written is lost."""
    tree = ast.parse((O.ROOT / VERTICAL_PATH).read_text(encoding="utf-8"))
    body = next(f for f in tree.body if isinstance(f, ast.FunctionDef) and f.name == "write_out")
    calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)]
    observed = [c for c in calls if getattr(c.func, "attr", "") == "observe" and c.args
                and getattr(c.args[0], "id", "") == "RESULT_REACHED"]
    assert len(observed) == 1
    assert {k.arg: ast.unparse(k.value) for k in observed[0].keywords} == {"reached": "bool(op.reports)",
                                                                           "asked": "asks_result",
                                                                           None: "result_evidence"}
    written = next(c for c in calls if ast.unparse(c.func) == "op.ledger.write")
    assert observed[0].lineno < written.lineno


def test_a_landed_step_whose_driver_is_owed_shows_as_its_own_row(tmp_path):
    """The designer: it has landed and still fails the verdict, so it is never folded into landed."""
    owed = _led({"init": O.BUILT, "open": O.SERVED})
    owed.observe("no_driver", step="open", oracle_step=O.STEP["open"].n, state=O.SERVED, instead="x")
    again = _led({"init": O.BUILT, "open": O.SERVED})
    again.observe("no_driver", step="open", oracle_step=O.STEP["open"].n, state=O.SERVED, instead="x")
    _lane(tmp_path, {"test_v1": owed, "test_v2": again})
    text = R.report(tmp_path, run=_main_run(1))
    assert _board_row(text, "Landed, driver owed").startswith(
        "| Landed, driver owed (these still fail the verdict) | 1: open |")  # one step, on two ledgers
    assert "| V1's steps landed | 2 of 8 |" in text
    assert _series(tmp_path)[0][S.DRIVER_OWED] == 1 and _series(tmp_path)[0]["owed"] == ["open"]
    assert "| 1 | `00000000` | 2026-11-01 | 2 of 2; the series began or restarted here | 0 of 2 | 2 of 8 |" in text


def test_ledgers_that_disagree_on_a_step_show_mixed_and_count_for_neither(tmp_path):
    _lane(tmp_path, {"test_v1": _led({"init": O.BUILT, "plan": O.SERVED}), "test_v2": _led({"init": O.BUILT})})
    text = R.report(tmp_path)
    assert "| V1's steps landed | 1 of 8; mixed: plan (not built, served) |" in text
    _lane(tmp_path, {"test_v1": _led({"exit": O.OUTSIDE, "reopen": O.SERVED}), "test_v2": _led({"exit": O.OUTSIDE})})
    assert "mixed: reopen (not built, served)" in _board_row(R.report(tmp_path), "The other steps landed")


def test_a_step_on_no_ledger_is_unknown_never_a_fall(tmp_path):
    _seed_series(tmp_path, [_row(1)])
    bare = L.Ledger("V1", platform="linux")  # a ledger with no steps, as the lane's before #306
    bare.ended_by(None)
    _lane(tmp_path, {"test_v1": bare})
    text = R.report(tmp_path, run=_main_run(2))
    row = _board_row(text, "V1's steps landed")
    assert "unknown, of 8; on no ledger: init, configure" in row and "fell" not in row
    assert "; 1 measured run" in row  # neither a reset nor an extension


def test_only_main_saves_the_series_and_a_branch_shows_its_own_values(tmp_path, monkeypatch, capsys):
    """A dispatch on a branch reads main's series and shows its own values beside it, and writes nothing, so a branch
    cannot change main's line. Through ``main``, as the workflow runs it."""
    _seed_series(tmp_path, [_row(1, total=2)])
    before = (tmp_path / S.SERIES).read_bytes()
    _lane(tmp_path, {"test_v1": _led(), "test_v2": _led()}, passed=frozenset({"test_v1"}))
    monkeypatch.setenv("GITHUB_RUN_ID", "2")
    monkeypatch.setenv("GITHUB_SHA", "b" * 40)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feat/e115-scoreboard")
    assert R.main([str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert (tmp_path / S.SERIES).read_bytes() == before
    assert "| 2 (this run, not saved) | `bbbbbbbb` |" in text and "saved nowhere" in text
    assert "`main`'s series, when one was restored, is `vertical-series.jsonl` in this run's artifact, without" in text
    assert "| Scenarios passing | 1 of 2 measured, 1 of 2 total | rose from 0 by" in text
    monkeypatch.setenv("GITHUB_REF", S.MAIN_REF)
    assert R.main([str(tmp_path)]) == 0
    text = capsys.readouterr().out
    assert [r["run"] for r in _series(tmp_path)] == ["1", "2"] and "saved nowhere" not in text
    assert "the whole series is `vertical-series.jsonl` in this run's artifact" in text
    monkeypatch.delenv("GITHUB_RUN_ID")  # outside a workflow: it reports, and saves nothing
    saved = (tmp_path / S.SERIES).read_bytes()
    assert R.main([str(tmp_path)]) == 0
    assert (tmp_path / S.SERIES).read_bytes() == saved and b"\r" not in saved


def test_a_rerun_of_a_main_run_replaces_its_line_rather_than_adding_a_data_point(tmp_path):
    _seed_series(tmp_path, [_row(1, total=1), _row(2, total=1)])
    _lane(tmp_path, {"test_v1": _led()}, passed=frozenset({"test_v1"}))
    R.report(tmp_path, run=_main_run(2))
    assert [r["run"] for r in _series(tmp_path)] == ["1", "2"] and _series(tmp_path)[-1]["passing"] == 1


def test_a_rerun_of_an_older_run_keeps_its_place_and_never_loses_what_was_measured(tmp_path):
    """The review of #324, F4: a re-run restores the newest save, so moving its line last would read as a fall, and the
    next run as a rise. An attempt that measured less keeps the line it would replace, and a restart stays on its
    line."""
    rows = [_row(1, passing=5), _row(2, passing=5), _row(3, passing=5)]
    again = S.joined(rows, _row(2, passing=4))
    assert [r["run"] for r in again] == ["1", "2", "3"] and again[1]["passing"] == 4
    assert S.joined(rows, _row(4))[-1]["run"] == "4"
    assert S.joined(rows, _row(2, measured=False))[1]["passing"] == 5  # nothing measured: the measured line stays
    assert S.joined(rows, _row(2, passing=1, of=4))[1]["passing"] == 5  # less measured
    assert S.joined([_row(1, measured=False)], _row(1))[0]["measured"] is True
    restarted = [{**_row(1), "restarted": "no series was restored"}]
    assert S.joined(restarted, _row(1, passing=3)) == [{**_row(1, passing=3), "restarted": "no series was restored"}]
    # Through the report: the re-run of run 2 says the newest line, not itself, when that one is the short one
    _seed_series(tmp_path, [_row(1, total=1), _row(2, total=1), _row(3, measured=False)])
    _lane(tmp_path, {"test_v1": _led()})
    text = R.report(tmp_path, run=_main_run(2))
    assert [r["run"] for r in _series(tmp_path)] == ["1", "2", "3"]
    assert "**Run 3 measured nothing**" in text and "fell" not in _board_row(text, "Scenarios passing")


def test_the_report_shows_the_last_ten_runs_and_the_artifact_keeps_the_whole_series(tmp_path):
    _seed_series(tmp_path, [_row(n) for n in range(1, 13)])
    _lane(tmp_path, {"test_v1": _led()})
    text = R.report(tmp_path, run=_main_run(13))
    assert len(_series(tmp_path)) == 13
    assert "**The last 10 runs**" in text and text.index("| Measure |") < text.index("**The last 10 runs**")
    assert text.index("**The last 10 runs**") < text.index("| Scenario | Result |")
    shown = [line.split(" ")[1] for line in text.splitlines() if re.match(r"\| \d+ \| `", line)]
    assert shown == [str(n) for n in range(4, 14)]


def test_a_reason_with_a_pipe_never_breaks_the_scoreboards_tables(tmp_path):
    _seed_series(tmp_path, [{**_row(1, measured=False), "why": "a | b"}])
    text = R.report(tmp_path)
    assert "| no: a \\| b |" in text


def _incident_lane(directory) -> None:
    """A run of the blind stretch as it really ended (the Linux logs of runs 40821366033, 41003785057 and 41120823321):
    13 of the 17 scenarios where the Lead did not start, and V3's other four reaching their verdict."""
    directory.mkdir(parents=True, exist_ok=True)
    states = {"init": O.BUILT}
    lost = {f"test_v1[{n}]": _scenario(AssertionError(LEAD_DID_NOT_START)) for n in range(13)}
    _lane(directory, {**lost, **{f"test_v3[{n}]": _led(states, asked=False) for n in range(4)}})


def test_the_blind_stretch_as_it_really_ended_fires_the_banner_and_counts(tmp_path):
    """The review of #324, F1: 40 hours of runs that measured 4 of 17 were the incident. Each is in the series, marked,
    with the banner, its count and the count in the table; none extends "flat since" for what it cannot say."""
    text = ""
    for n in range(1, 4):
        _incident_lane(tmp_path)
        text = R.report(tmp_path, run=_main_run(n))
    assert "**This run measured only 4 of 17 scenarios** (the others ended before their verdict)." in text
    assert "3 runs in a row have measured nothing or only part of the lane, since 2026-11-01." in text
    assert ("No run in the series has measured the whole lane, so the rows that need it are the seed's or unknown."
            in text)
    assert "| 3 | `00000000` | 2026-11-03 | 4 of 17, partial |" in text
    assert _board_row(text, "Scenarios passing") == (
        "| Scenarios passing | 0 (the seed's) | 2026-10-12 (run 38188158379); 0 measured runs in the series, earlier "
        "runs not counted |")
    assert "| unknown | no run has recorded it yet |" in _board_row(text, "Landed, driver owed")
    reach = _board_row(text, "Reached a result")
    assert "| unknown (" not in reach and "of the" not in reach
    # A step's state is derived from the code at setup, so these stay data points, and say where they are from
    assert _board_row(text, "V1's steps landed").startswith("| V1's steps landed | 1 of 8 |")
    assert "3 measured runs in the series" in _board_row(text, "V1's steps landed")
    assert "The step rows are from run 3:" in text


def _full(tmp_path, *, passed: int, owed: bool) -> None:
    states = {"init": O.BUILT, "open": O.SERVED} if owed else {"init": O.BUILT}

    def one() -> L.Ledger:
        led = _led(states, reached=True)
        if owed:
            led.observe("no_driver", step="open", oracle_step=O.STEP["open"].n, state=O.SERVED, instead="x")
        return led

    names = [f"test_v{n}" for n in range(5)]
    _lane(tmp_path, {n: one() for n in names}, passed=frozenset(names[:passed]))


def test_an_early_stop_reads_as_neither_a_fall_nor_a_rise(tmp_path):
    """The review of #324, F1: full, full, partial, full, with no product change. Passing, driver owed and reached fall
    with what a run reached, and an early stop would read as drivers arriving."""
    _full(tmp_path, passed=3, owed=True)
    R.report(tmp_path, run=_main_run(1))
    _full(tmp_path, passed=3, owed=True)
    R.report(tmp_path, run=_main_run(2))
    # An early stop: three scenarios reach their verdict, and the operator never reaches the owed step
    shared = {"init": O.BUILT, "open": O.SERVED}
    lost = {"test_v3": _scenario(AssertionError(LEAD_DID_NOT_START)), "test_v4": _scenario(AssertionError("stopped"))}
    _lane(tmp_path, {**{f"test_v{n}": _led(shared, reached=False) for n in range(3)}, **lost},
          passed=frozenset({"test_v0"}))
    text = R.report(tmp_path, run=_main_run(3))
    assert "**This run measured only 3 of 5 scenarios**" in text
    assert "the last run that measured the whole lane: run 2" in text
    assert "| 3 | `00000000` | 2026-11-03 | 3 of 5, partial |" in text
    assert _series(tmp_path)[-1]["passing"] == 1  # in the series, marked: its own values are kept
    for label, now in (("Scenarios passing", "3 of 5 measured, 3 of 5 total"), ("Landed, driver owed", "1: open"),
                       ("Reached a result", "5 of the 5 measured")):
        row = _board_row(text, label)
        assert now in row and "fell" not in row and "rose" not in row and "; 2 measured runs" in row, row
    _full(tmp_path, passed=3, owed=True)
    text = R.report(tmp_path, run=_main_run(4))
    assert "measured only" not in text and "| 4 | `00000000` | 2026-11-04 | 5 of 5 |" in text
    for label in ("Scenarios passing", "Landed, driver owed", "Reached a result"):
        row = _board_row(text, label)
        assert "fell" not in row and "rose" not in row and "; 3 measured runs" in row, row


def test_a_whole_runs_fall_still_reads_as_fell_with_a_partial_run_before_it():
    rows = [_row(1, passing=5), _row(2, passing=9, of=4), _row(3, passing=3)]
    assert S.flat(rows, S.PASSING, None) == S.Flat(3, "2026-11-03", "run 3", runs=1, moved="fell", before=5)
    assert S.flat(rows, S.V1_LANDED, None).runs == 3  # a step row: a partial run is a data point


def test_a_report_that_holds_only_what_ran_is_partial_against_the_lanes_recent_size(tmp_path):
    """The review of #324, F1 and F2: a JUnit report holds only the scenarios that ran, so a run cut short has every
    scenario it holds measured, and only the runs before it show it. The lane growing marks nothing, and a lane that
    really shrinks reads partial for the window, then holds its new size."""
    rows = [_row(1), _row(2, total=3)]
    assert S.lane_sizes(rows) == [17, 17] and S.partials(rows) == [False, True]
    assert S.partials([_row(1, total=3), _row(2)]) == [False, False]  # it grew: the earlier run stays what it was
    assert S.partials([_row(1), _row(2, measured=False), _row(3)]) == [False, False, False]
    assert S.lane_sizes([_row(1), _row(2, measured=False)]) == [17, None]
    assert S.partials([_row(1, of=4)]) == [True]
    shrunk = [_row(1), *(_row(n, total=16) for n in range(2, S.LANE_WINDOW + 3))]
    assert S.partials(shrunk) == [False] + [True] * S.LANE_WINDOW + [False]
    _seed_series(tmp_path, [_row(1, passing=2)])
    _lane(tmp_path, {"test_v1": _led(), "test_v2": _led(), "test_v3": _led()}, passed=frozenset({"test_v1"}))
    text = R.report(tmp_path, run=_main_run(2))
    assert ("**This run measured only 3 of 17 scenarios** (its report holds only the 3 that ran; the others ended "
            "before their verdict or never ran).") in text
    assert "| 2 | `00000000` | 2026-11-02 | 3 of 17, partial |" in text
    row = _board_row(text, "Scenarios passing")
    assert "| 2 of 17 measured, 2 of 17 total |" in row and "fell" not in row


def test_every_scenario_passing_needs_pytest_to_have_finished_clean(tmp_path, monkeypatch, capsys):
    """The review of #324, F2: the V-01 line never reads as done before every scenario passes, and a JUnit report holds
    only what ran. A run cancelled after its first three passes is "3 of the 3 that ran", through ``main`` as the
    workflow runs it."""
    _lane(tmp_path, {f"test_v{n}": _led() for n in range(3)}, passed=frozenset(f"test_v{n}" for n in range(3)))
    monkeypatch.delenv(R.PYTEST_OUTCOME, raising=False)
    outcomes = {"cancelled": "pytest's step ended as cancelled", "failure": "pytest's step ended as failure",
                "": "nothing here says how pytest's step ended"}
    for outcome, why in outcomes.items():
        monkeypatch.setenv(R.PYTEST_OUTCOME, outcome)
        assert R.main([str(tmp_path)]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[0] == "### vertical (linux): not measured: 0 of 3"
        assert lines[1] == (f"**V-01 is not met:** 3 of the 3 that ran pass, and the run may have ended early ({why}); "
                            "this job stays red until every scenario passes.")
    monkeypatch.setenv(R.PYTEST_OUTCOME, S.PYTEST_FINISHED)
    assert R.main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines()[1] == ("**Every scenario passes (3 of 3).** Enforcing this job is the "
                                                       "operator's decision.")


def test_a_lost_series_says_so_for_as_long_as_a_flat_run_begins_there(tmp_path):
    """The review of #324, F3: the notice shows on the restart's run only, so the restart is on its line. With passing
    at 5 before the entry went, nothing compares with the seed across it, and from the next run it still says so."""
    def lane() -> None:
        names = [f"test_v{n}" for n in range(5)]
        _lane(tmp_path, {n: _led({"init": O.BUILT}) for n in names}, passed=frozenset(names))

    lane()
    text = R.report(tmp_path, run=_main_run(9))
    assert _series(tmp_path)[0]["restarted"] == "no series was restored"
    assert ("The series began or restarted from its seed: no series was restored. Any earlier lines are in the "
            "artifacts") in text
    since = "since the series began or restarted at run 9; any earlier runs lost; "
    row = _board_row(text, "Scenarios passing")
    assert row.endswith(f"| {since}1 measured run |") and "rose" not in row
    assert _board_row(text, "The other steps landed").endswith(f"| {since}1 measured run |")
    assert "| 9 | `00000000` | 2026-11-09 | 5 of 5; the series began or restarted here |" in text
    assert "2026-10-30 (#306, run 41120823321)" in _board_row(text, "V1's steps landed")  # back at its seed's value
    lane()
    text = R.report(tmp_path, run=_main_run(10))
    assert "The series began or restarted" not in text and "no series was restored" not in text  # the notice was once
    assert _board_row(text, "Scenarios passing").endswith(f"| {since}2 measured runs |")
    assert "| 10 | `00000000` | 2026-11-10 | 5 of 5 |" in text and "; the series began or restarted here" in text
    # A value that moves after it reads as moved: that flat run did not begin at the restart
    (tmp_path / "junit.xml").write_text((tmp_path / "junit.xml").read_text(encoding="utf-8").replace(
        '<testcase classname="t" name="test_v0">', '<testcase classname="t" name="test_v0"><failure message="x"/>'),
        encoding="utf-8")
    row = _board_row(R.report(tmp_path, run=_main_run(11)), "Scenarios passing")
    assert "fell from 5 by 2026-11-11 (run 11)" in row


def test_a_restart_on_a_run_that_measured_nothing_still_marks_the_flat_run_after_it():
    rows = [{**_row(9, measured=False), "restarted": "no series was restored"}, _row(10, passing=5)]
    assert S.flat(rows, S.PASSING, S.Seeded(0, "d", "w")) == S.Flat(5, "2026-11-10", "run 10", runs=1, restart="9")
    assert S.flat(rows, S.REACHED, None) == S.Flat(None)
    assert S.flat(rows, S.PASSING, None).restart == "9"


def test_the_small_words_the_review_named(tmp_path):
    """The review of #324, n1 to n5: no "the last 1 run", no "run this run" outside a workflow."""
    _lane(tmp_path, {"test_v1": _led()})
    text = R.report(tmp_path)
    assert "**The last run** (" in text and "The last 1 run" not in text
    assert "run this run" not in text
    assert "since the series began or restarted at this run;" in _board_row(text, "The other steps landed")


def test_the_seed_names_what_the_runs_show():
    """A named constant with its source; the values are the runs' (read 2026-11-03), and only the enforced platform has
    one. "Reached a result" and the other rows have no history, so they have no seed."""
    assert set(S.SEED) == set(L.ENFORCED_PLATFORMS)
    assert S.SEED["linux"] == {S.PASSING: S.Seeded(0, "2026-10-12", "run 38188158379"),
                               S.V1_LANDED: S.Seeded(1, "2026-10-30", "#306, run 41120823321")}
