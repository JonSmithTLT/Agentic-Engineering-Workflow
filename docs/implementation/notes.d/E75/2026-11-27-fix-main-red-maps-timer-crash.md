**A test moved the worker's clock, and the session deadline ended the worker (2026-11-27).** `main` at `136635cf`,
push run 45997128944, `integration 14/14 (windows-latest)` (job 140518111471): gw2 "crashed" 1.4 s into
`test_maps_v01_profile.py::test_no_map_freshness_turns_current_on_a_timer`. The bundle (the watchdog artifact,
`autopsy/session-4088-0cc85d80/worker-gw2-deadline.txt` and the test's autopsy `reason.txt`, "the session deadline
passed") shows the worker's own session-deadline exit, about 20 minutes before the real deadline. The test patched
`time.time` and `time.monotonic` on the shared `time` module to a year ahead, for every thread; the deadline thread
(`session_deadline.Worker._watch`) wakes at least once a minute, read the moved `time.monotonic()` and called
`os._exit(70)`. The test's stack in the autopsy is at line 221, inside the patch. The window is the test's second
freshness read (git subprocesses, about 1 s on Windows), so roughly one run of that test in forty or fifty is exposed.

**The fix** is a thread-scoped clock patch, `sleep_patch.patch_clock`, as `patch_sleep` already is for `sleep`, with
`test_sleep_patches.py::test_a_clock_a_test_moves_a_year_ahead_is_never_the_clock_another_thread_reads`. The flake
register's entry `shared-clock-session-deadline` records the sighting and its closure.

**Follow-on, not done here:** twelve other patches, in eight test files, still move a clock on the shared `time`
module for every thread (`time_ns`, `perf_counter`, `monotonic` and `time`, in `test_runlog_reads.py`,
`test_supervisor_state_read.py`, `test_usage_record.py`, `test_evidence_states.py`, `test_lead_contained.py`,
`test_lead_wake.py`, `test_profile.py`, `test_flake_register.py`). None moves `monotonic` forward past a deadline, but
`test_lead_contained.py`'s `lambda: next(clock)` would raise `StopIteration` in any other thread that reads the clock,
the session-deadline thread included, which would end that thread and leave the worker without its deadline.
Converting them to `patch_clock` and extending `test_sleep_patches.py`'s two detectors to the clocks is the follow-on,
owned by this row.
