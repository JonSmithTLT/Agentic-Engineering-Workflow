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
- **The fix.** The lane supervisor at the signal (on either platform), or the cancellation collection, writes
  `runner-resources-before-tests.txt` (`worker_evidence.before_tests`) from positive observations only: no in-flight
  header or running name, and each session either still starting, as an xdist session whose registered workers'
  lifecycle receipts, read from their live writers, stand before their first test, or finished after a graceful
  interrupt, with every registered worker's receipt short of execution and the lane report complete with no test's
  result (`evidence_files.finished_without_tests`; its `collected` list proves nothing, since under xdist the
  controller fills it only as each worker goes down); or no session registered at all. The check
  (`check_evidence_run`) types such a lane `before tests` (a controller's `abnormal-exit` does not prevent it: that is
  the cancellation's own death), and `evidence_problems` accepts the record as its death evidence only while the bundle
  bears it out: every session listed; every registered worker listed by pid and start, with its lifecycle receipt
  present, reaching its recorded phase and never `execution-started`; a finished session's own files showing no test
  began; no test's autopsy, test result in the lane report (a collection error is not one), in-flight header,
  interruption record or running name. Anything else is a `[before-tests]` defect. `WORKER_PHASES`, the lane report's
  schema and the `worker-count` marker are owned by `evidence_files`, so the check reads them without pytest.
- **The proof.** A real xdist session interrupted by SIGINT while its workers collect ends gracefully, and its published
  bundle is accepted whether the record was taken at the signal or at the collection
  (`test_a_start_up_interrupted_gracefully_is_typed_before_tests_from_its_real_bundle`, POSIX). The hosted matrix row is
  the evidence proof's start-up control: `run-cancel-control (start)` dispatches a target whose plants
  (`evidence_plants/startup.py`) hold their workers' collection, behind the twin barrier, cancels it once both lanes
  have run `START_READY_SECONDS`, and requires both jobs typed `before tests` with A2 yes and no defect. The `verify`
  job also ablates the rule on every hosted `normal` plant (`verify_evidence.before_tests_twin`).
- **Limits.** A serial session's controller runs its tests itself and keeps no lifecycle receipt, and an xdist session
  that has not yet written `worker-count` cannot be told from one; neither is recorded before it finishes, so its gap
  stays a defect. A registered worker whose receipt cannot be read from its live writer stays indeterminate, with the
  same result. "No session at all" reads an absence: it holds while every lane command passes `--session-deadline` with
  its hang directory the lane root or one level under it, which
  `test_every_lane_command_keeps_its_sessions_where_the_collection_looks` pins.
- **Carried follow-ons.** #564's quick-check m1 and #561's quick-check m5 were both fixed by #573 (42ecb439) and are
  proven there; this change confirmed each fails its test when undone.
