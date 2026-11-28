`[live-stack] interrupted-<pid>.txt: live worker lacks its interruption stack` on superseded Linux integration lanes
(flake-register `linux-cancel-live-stack`): a Linux worker caught in fixture setup or teardown at the cancel signal
no longer owes a test-function frame.

- **The decision.** #573 stated that none of the Linux warning's outcomes excuses a stack. Asked whether a Linux
  worker caught in setup or teardown at the cancel signal should be accepted as Windows already accepts it, the
  operator answered "Yes" (2026-11-26). This change reverses that one statement and nothing wider.
- **The cause it answers.** Reproduced on 2026-11-26 with the real lane supervisor and py-spy over a two-worker
  session, one worker sleeping in a function fixture's setup: the pre-signal warning attach succeeds, its stack is
  kept with the fixture's frames and its typed outcome is `setup`, and the check still reported the defect, because
  it wanted a frame of the test function. The Windows collection has excused that state since #561.
- **The rule.** `evidence_files.STACK_NOT_OWED` names, per interruption, the typed outcomes for which a live worker
  owes no test frame: setup, teardown and between tests for the cancellation collection, as before, and setup and
  teardown for the Linux warning. `evidence_problems.outside_call` accepts one only for the same worker, test and
  collection instant, and only with a retained stack of that same interruption whose frames classify the same
  (`pytest_phase`). The warning stops retrying once a dump shows the worker in setup or teardown, as the collection
  does. `OUTCOME_FILES`, which file answers which interruption, moved to `evidence_files` as its one owner.
- **What is still a defect on Linux.** A dump inside the call without the test's frame, one with no pytest frame, one
  the frames place between tests, a worker that changed tests or exited during the attach, a failed attach, an
  outcome its retained frames contradict, one of another observation, and one whose stack is gone.
- **The message.** A live-stack defect names each typed outcome left for its observation
  (`evidence_problems.outcome_note`), for example `interrupted-2470.txt: live worker lacks its interruption stack
  (warning outcome: straddled a test change)`, so a sighting says why with no artifact download. The proof's own
  message uses the same owner; `verify_evidence.warning_why` is gone.
- **The proof.** The Linux cancel plant (`evidence_plants/deaths.py`) spends its odd cases' seconds in a fixture's
  setup instead of the test's call, with no case's length changed, so a cancellation can catch a worker outside its
  call. Every case used to sleep in its call, which is why the proof never saw this state.
  `verify_evidence.observe_cancel` accepts for the Linux plant exactly what the check accepts and prints how many
  workers were outside their call. It does not require one: which phase a worker is in at the signal is timing.
- **Tests.** `test_a_linux_worker_in_setup_or_teardown_at_the_signal_is_not_a_missing_stack`,
  `test_a_linux_worker_inside_its_call_without_its_test_frame_still_owes_its_stack`,
  `test_a_live_stack_defect_names_its_typed_outcome` and
  `test_the_linux_cancel_plant_holds_half_its_cases_in_a_fixtures_setup`. Read against the reproduced bundle, the
  check reports the defect at `main` and none with this change.

**What remains** (2026-11-26): E3 stays a standing watch. `linux-cancel-live-stack` stays open until a superseded
Linux integration run shows the typed outcome accepted. Following a worker that changes tests during the warning's
attach into its next test, as the collection does, is not built: it waits on the operator reading the typed outcomes
of the eight workers of 2026-11-26 in artifacts 15098507312, 15098582462, 15099432277, 15099067980 and 15100991546
(they expire 2026-12-10), which decide whether straddles are a real share of the sightings. Until then a straddle
stays a defect that now names itself.
