**The Linux lane measures again (2026-10-30, branch `test/stg13-vertical-linux-pty`).** Every Linux scenario had
died at the Lead's start since CS-4 merged (#283): the contained Lead's TUI runs on a terminal AEW relays, and the
scripted operator started `aew opencode` with no terminal. These changes follow the designer's addendum 1 to the
oracle's hand-off:
- **The pty.** The scripted operator now starts the session on a pseudo-terminal it owns (`start_on_terminal`).
  CS-4's checks are unchanged.
- **Not measured.** A scenario that ends before its verdict is not measured. It counts in no counter and against no
  threshold.
- **The lane's report.** It leads the run's summary with the not-measured count, from the JUnit report's scenarios
  (`vertical/report.py`).
- **The #213 hang diagnosis fails on Linux, on its own assertions:** with the Lead contained, its autopsy finds no
  `events-*` from the TUI. It is tracked for a test-fixture fix in a later pull request (the designer's ruling).
- **The Lead's label on Linux** is read from the contained session's record. The operator's Lead minimums wait on the
  dispatched Linux run's reading.
