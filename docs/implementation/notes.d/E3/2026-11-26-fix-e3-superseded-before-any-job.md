A `ci` run superseded before any of its jobs existed was recorded as an evidence gap: `[cancel-reason] no available
cancellation attribution`.

- **The sighting.** PR #601's run 45786034180 (2026-11-26, evidence check 139802251201): created 08:46:40Z, concluded
  `cancelled` at 08:57:13Z with no job and no `cancelled_by`. The pull request's next run, 45787535368, was created at
  08:57:12Z and is the only other run of its group in that window.
- **The cause.** No test ran, so no evidence was owed; the only fact to record is what replaced the run. The supersede
  attribution starts from a job's check-run annotation naming the concurrency group (`cancel_evidence.observe`), and a
  run with no job has none, so the completed-run record accepted only a manual cancellation that names an actor.
- **The fix.** With no job and no actor, `record_cancel_evidence.record` asks
  `cancel_evidence.superseded_before_any_job`: the group is derived from the run (`ci_group`), and `replacement`
  names the successor from run history under the rule a job's attribution already uses, exactly one other run of
  that group, workflow, branch, event and repository created within the cancelled run's life. One such run reads
  "Superseded before any job was recorded, by run N at SHA (event)" and counts no gap. None or several, a successor
  whose group cannot be established, or a cancelled run of another workflow or event (only a pull request's `ci` run
  is cancelled for a successor) keeps the defect: no attribution is invented. Read against the real run, it names
  45787535368. Tests: `test_a_run_superseded_before_any_job_names_its_unique_successor_and_is_no_gap`,
  `test_a_jobless_cancel_with_two_possible_successors_stays_an_attribution_gap`,
  `test_a_jobless_cancel_with_no_established_successor_stays_an_attribution_gap`,
  `test_a_jobless_run_outside_a_pull_requests_ci_group_is_never_attributed_from_history` and
  `test_a_jobless_manual_cancel_keeps_its_actor_and_asks_no_run_history`; the earlier
  `test_empty_canceled_attempt_records_the_unavailable_cause_without_inventing_a_job` is unchanged.
- **Limits.** The attribution is an inference from run history, not an observation of GitHub's reason: a jobless run
  that someone cancelled by hand while exactly one newer run of its group already existed, with no actor recorded,
  would read as superseded. ci.yml cancels a pull request's run for the next one of its group, so that newer run
  would have ended it in any case. The new head's "Superseded predecessor" line
  (`record_cancel_evidence.predecessor`) still needs a cancelled job, so it does not name a jobless predecessor.
- **After the review of #615.** Only a first attempt is attributed: a re-run keeps the first attempt's `created_at`,
  so its window took in runs older than the re-run (finding 1). A candidate of the cancelled run's own second counts
  only with a higher id, since a lower one is its predecessor (finding 2). The `ci.yml` path has one owner,
  `flake_register.CI_WORKFLOW`, which the recorder, the scorecard and `cancel_evidence` read (finding 4).
- **The flake register.** `linux-cancel-live-stack` gains the three sightings of 2026-11-26 (PR #606 run 45780063188,
  PR #607 run 45780328190, PR #597 run 45781663365: eight workers in five Linux integration lanes, the first since
  #573), a fourth of the same day (PR #608 run 45787278179, one worker, bundle not read) and a diagnostic observation, and its `cause` no longer says the warning attach failed: in the one reproduced
  case the attach succeeds and the check refuses a stack taken in fixture setup.

**What remains** (2026-11-26): E3 stays a standing watch. `linux-cancel-live-stack` is open with no `planned_fix`:
whether a Linux worker's setup or teardown outcome at the signal excuses its interruption stack, as the Windows
collection's does, reverses #573's stated rule and is the operator's decision; the typed outcomes of the eight
workers are in artifacts 15098507312, 15098582462, 15099432277, 15099067980 and 15100991546 (they expire 2026-12-10)
and have not been read. A serial lane cancelled before its first test is still typed `cancel`
(fix/e3-serial-cancel-before-tests).
