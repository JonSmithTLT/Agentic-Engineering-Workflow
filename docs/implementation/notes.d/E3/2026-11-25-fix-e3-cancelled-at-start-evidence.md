Lanes cancelled while their sessions were still starting, with `[death-record] cancel: no pre-cleanup worker
observation` and `[running] missing running test name` in the evidence check.

- **The sightings.** Superseded ci run 45590135545 (2026-11-25), ten lanes on both platforms, each cancelled 37 to 96 s
  into its pytest step: fast 1/2 and 2/2, integration 3/8 and 8/8, acceptance and regression 2/3 on Linux; integration
  4/14, 8/14, 12/14 and regression 3/3 on Windows (for example jobs 139124033204 and 139124033808). Also integration
  13/14 on Windows in run 45591135734 (job 139126281549, 44 s), integration 2/8 and 4/8 on Linux in run 45571060413
  (jobs 139058317158 and 139058317331, 37 and 110 s), and fast 1/2 on Linux in run 45570390239 (job 139056178075).
- **The cause.** No test had started. A green run's first progress line comes 76 to 141 s into the same step (run
  45602811086), the cancelled steps printed none, and the collection found no worker with an in-flight watchdog header
  (`evidence timing collect 0.010s`). A worker is observed only inside a test, so there was nothing to observe or name:
  the evidence was not lost, it never existed, and the check had no way to say so.
- **The fix.** The Linux supervisor at the signal, or the cancellation collection, writes
  `runner-resources-before-tests.txt` (`worker_evidence.before_tests`) from positive observations only: no in-flight
  header or running name, no finished session, and every session an xdist session whose registered workers' lifecycle
  receipts, read from their live writers, stand before their first test; or no session registered at all. The check
  (`check_evidence_run`) types such a lane `before tests`, and `evidence_problems` accepts the record as its death
  evidence only while the bundle bears it out: every session listed, every registered worker recorded before its first
  test, no `execution-started` receipt, no finished session, no test result in the lane report (a collection error is
  not one), and no in-flight header, interruption record or running name. Anything else is a `[before-tests]` defect.
  The evidence proof's `verify` job ablates the rule on every hosted `normal` plant: that lane's own bundle, claimed as
  cancelled before its tests, must raise it (`verify_evidence.before_tests_twin`). `WORKER_PHASES` moves to
  `evidence_files`, its one owner, so the check can read it without pytest.
- **Limits.** A serial session's controller runs its tests itself and keeps no lifecycle receipt, and an xdist session
  that has not yet written `worker-count` cannot be told from one; neither is recorded, so its gap stays a defect. A
  registered worker whose receipt cannot be read from its live writer stays indeterminate, with the same result. No
  hosted plant cancels a lane during start-up, so the record's acceptance is proven by the unit matrix in
  `tests/unit/test_cancel_evidence.py` (four start-up layouts accepted; serial, executing and finished refused; seven
  contradictions defects and a collection error not one; the Linux supervisor's record at the signal; no record while a
  test is in flight).
- **Carried follow-ons.** #564's quick-check m1 and #561's quick-check m5 were both fixed by #573 (42ecb439) and are
  proven there; this change confirmed each fails its test when undone.
