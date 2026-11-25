**The serial lane's fit pin is built (2026-11-25, branch `fix/nightly-serial-fit-pin`).** It is the pin this row's
note of 2026-10-29 called for (plan v6, G3a-r2 item 3). `tests/unit/test_repetition_fit.py`, in the fast lane, fails
when a nightly session that runs in one process without `--shard` no longer fits the recorded time of its tests:
the race-and-kill job's ten serial passes and its racing writers, and the crash job's iterations. It reads each budget
from `nightly.yml` (through `bounds.workflow_lanes`), the tests' time from `tests/durations.json`, which session runs
which tests from the collection, and what a knob such as `AEW_RACE_WRITES` multiplies from its test module's default.
Its rule and margins are in its docstring: a 70 s cold start, 1.25x the recorded time, and a deadline that leaves
each pass's `--test-timeout` free to name a hang.

**What ended the race-and-kill job on 11-24 and 11-25 (runs 45463965123 and 45698876718, Windows, repetition 1).** No
test stalled. Each session's autopsy recorder shows the first test starting 69.8 s and 46.3 s after the session (a
cold collection), the tests then running at 0.97x to 0.98x the record's time, and the running test at the deadline
(`test_hang_watchdog.py::test_a_watchdog_wait_fails_by_name_after_the_watchdogs_own_evidence`, then
`test_dashboard_static.py::test_the_request_log_never_blocks_a_request_on_a_stalled_terminal`) having started less
than 3 s before it. The lane had grown to 96 to 98 tests on 11-23, about 250 s of recorded Windows time, which with
the cold collection left no room in 270 s. The 10-29 night recorded above is the same class. It is a budget, not a
flake, so it has no flake-register entry.

**The budgets now:** each serial pass runs with `--test-timeout 150` and `--session-deadline 510` (it was 240 within
270, so a hang more than 30 s into a pass could only end the session, never fail by name), and the job's deadline is
4620 s, its timeout 99 minutes. `nightly.yml` gives the derivation.

**Two slow tests to watch, not hidden by the margin:** on 11-25,
`test_validation_coverage_disclosure.py::test_slow_selector_copy_setup_cannot_spend_the_checks_deadline` took 26.3 s on
Windows, and the record, which predates it, estimates 3.8 s; and
`test_log_sealing.py::test_a_lockless_reader_races_a_compaction_in_another_process_without_a_lock` took 29.2 s against
a recorded 18.5 s. The record's refresh, E111's N4, brings the first into the pin.
