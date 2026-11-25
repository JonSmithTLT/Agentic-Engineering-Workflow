The cancellation evidence has lost live worker stacks on every superseded CI run since it was built (2026-11-23,
#526/#529/#531): 30-60% of in-flight lanes report `[live-stack] ... live worker lacks its interruption stack`, on both
platforms (cancelled runs 45272096898, 45295949163, 45320101069, 45365647270, 45512141007, and 45512296904, whose
evidence check 138869288721 listed 7 Linux and 9 Windows lanes). It has two causes with separate owners. On Linux
(`interrupted-*`) the pre-signal warning attach fails; #554 records each attempt's typed outcome so the next occurrence
names why. On Windows (`cancelled-*`) the cancellation collection (`lane_step.py --collect`) takes one nonblocking
py-spy dump per worker with none of the warning path's retries and leaves no unavailable marker when it fails; it
attaches only to workers already in the sampled ring, yet records every listed worker as alive, so a worker never
attached is still owed a stack; it discards a dump that straddles a test change; and a worker in setup, teardown or
between tests has no test-function frame to give. The fix for that side is the Windows cancel-collection PR. The
evidence-proof cancel control's failure at 4f1711b8 (`controlled pytest lanes have no overlapping time before
collection`, target run 45513035294) was runner queueing, not this defect: the Windows plant started 5 min 22 s behind
its Linux twin, past the trigger reserve. The cancellation collection now retries a failed or frameless attach inside
the warning path's shared budget (one constant, `evidence_files.INTERRUPTION_REASONS`, owns which reasons retry and
answer the live-stack check), decides liveness before its capture, and names every worker it keeps no test stack for,
bound to that observation's `collect_at`: #554's unavailable marker, or a typed outcome
(`snapshots/<pid>-<start>-cancel-outcome.txt`) for a worker with no sample in the owned tree, one that exited before or
during its attach or straddled a test change (an earlier dump of the same test is kept), or a dump without its test
frame classified by its pytest frames (setup, teardown, between tests, call, indeterminate). A worker with no sample is
`not sampled` only in a lane whose periodic sampling is off (`AEW_WORKER_SNAPSHOTS=0`), which the supervisor's sampler
records (`runner-resources-sampling.txt`); in a lane that samples it is a sampling gap and owes its stack, and the
sampler now keeps its first failed attach of each identity (`<pid>-<start>-sampling-failures.txt`, with #554's attempt
outcomes). The evidence check excuses a live worker only by a not-sampled outcome that the recorded policy bears out,
with no retained sample and no failed sampling attach of its identity, or by a setup, teardown or between-tests outcome
that the retained cancel-collection frames themselves classify so; a worker inside its test's call still owes its stack.
Hosted Windows CI now samples its serial lane's controller periodically, as hosted Linux already did (operator,
2026-11-25): every attach is `py-spy dump --nonblocking`, which never suspends its target, and #528 left the controller
out only because its overhead comparison covered xdist workers, not because of a found risk. So the Windows serial
controller owes its stack like any worker. The qualifying evidence is this PR's own Windows serial and xdist lanes in
CI, whose wall time the PR compares with the last three green `main` runs; a regression there reverts the switch. The
cancel plant's sighting (target run 45512199966, job 138862502221, of evidence-proof run 45512141240) has its cause
established from its bundle: `cancelled-7552.txt` observed `test_death[cancel-8]` alive with `collect_at` 23:43:50.297,
the watchdog shows `test_death[cancel-9]` starting 30 ms later, and the worker's ring holds only a periodic sample from
23:43:19 and no cancel-collection sample, so the collection's one dump straddled a test boundary on a plant of
few-second tests and was dropped without a marker. The collection now follows a worker whose dump straddles a test
change into its next test, retries inside the shared budget, and records the observation for the test its retained
sample labels (`straddled_from` names the test first observed), so a stack of one test never answers an observation of
another; a straddle with no dump kept after it stays a typed straddled outcome that owes its stack. The flake entry
`windows-cancel-live-stack` stays open, with that bundle as diagnostic evidence, with the Windows lanes of four more
superseded runs and this PR as its planned fix: closure awaits the first superseded runs after merge, since only the
cancel plant's sighting has an established cause. The Linux lanes of those runs open `linux-cancel-live-stack`, whose
cause is the pre-signal warning attach that #554 types, so its next sighting names why.
