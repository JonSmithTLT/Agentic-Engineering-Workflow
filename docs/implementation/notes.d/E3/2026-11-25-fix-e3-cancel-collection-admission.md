The cancellation evidence after #561, from superseded ci run 45575360924 (PR 571, 2026-11-25), whose evidence job
139085524950 (run 45575360838) is in both cancel flake entries.

- **Windows, a new cause.** Integration 7/14 (job 139072636221) reported live-stack, snapshot-age, snapshot-label and
  snapshot defects for four pids. The hosted cancel killed the lane supervisor outright: its `finally` never ran (no
  host-resources peak line), so its periodic sampler never reached xdist workers born in the 3 s or so before the kill.
  The cancellation collection (`lane_step.py --collect`) attached only workers with a ring sample, so it refused those
  as never sampled (`SAMPLING_GAP`), and they owed their stacks. The collection now also admits a worker that its
  session's job holds when the collection runs. Membership is checked with the OS, on the worker's identity (pid and
  start time), in the job the lane step names: the lane action sets `AEW_SESSION_JOB_NAMESPACE` for the lane and for its
  collection step, and the session controller names its job by it, never joining one of that name it did not create.
  The admitted worker is attached with #561's retries, its `cancel collection` sample goes in the ring before its
  observation is recorded, and the observation says `admitted_by: session job`. A worker in neither the ring nor the
  job stays a sampling gap and owes its stack. `session_deadline.session_job` is the one owner of opening a session's
  job, for this admission and for `collect_leftovers`. Proof:
  `test_a_worker_too_new_for_its_first_sample_is_attached_when_its_session_job_holds_it` (the full
  `evidence_problems` output has no live-stack or snapshot problem for that pid),
  `test_a_never_sampled_worker_outside_its_session_job_is_never_attached` (not a member, a marker naming another job,
  no lane name) and, on Windows, `test_a_job_the_lane_named_holds_a_member_by_identity_and_its_name_is_never_joined_twice`
  on a real job object.
- **Linux, the warning path typed.** Integration 6/8 (job 139072636094) reported live-stack for `interrupted-2439` with
  no unavailable marker: #554 typed only the unavailable case, so a straddle, an exit during the attach or a dump without
  the test's frame left nothing. The pre-signal warning now writes a typed outcome for each
  (`snapshots/<pid>-<start>-warning-outcome.txt`, bound to the observation's `collect_at`; a worker outside the
  supervisor's tree is typed too), and the evidence proof's Linux failure names it, for example `... (straddled a test
  change)`. These outcomes only say why; none excuses a missing stack. The warning path does not follow a straddled
  worker into its next test as the cancellation collection does: its observation is recorded for the test it first saw.
  #561's quick check, m5, the follow's identity guard, now has its test:
  `test_a_straddle_is_never_followed_into_another_workers_test`.
- **#564's quick check, m1.** The cancel control named a target that failed before its lane ran as `PlantQueued`. Its
  ended-plant branch now names queueing only once the ended plant's lane reached its trigger reserve; an earlier end
  falls through to the existing error (`cancellation target finished before its replacement queued`). The
  `linux-fails-early` case of `test_a_plant_whose_runner_queues_late_still_overlaps_or_is_named_as_queued` proves it.
- **A Windows supervisor that receives Ctrl-C.** `child.send_signal(SIGINT)` raises `ValueError` on Windows, which the
  `suppress(OSError)` around it missed, so such a supervisor skipped its collection and the job's end. It is now
  suppressed with the rest; a hosted cancel never reached this path, since it kills the supervisor outright.
  `test_a_windows_supervisor_interrupted_by_sigint_still_collects_and_ends_its_lanes_job`.

Both cancel flake entries stay open: closure awaits the first superseded runs after this merges.
