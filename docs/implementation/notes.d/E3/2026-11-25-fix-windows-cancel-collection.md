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
`not sampled` only when the lane's sampling policy excludes it (`AEW_WORKER_SNAPSHOTS=0`, or the controller of an xdist
lane), which the supervisor's sampler records (`runner-resources-sampling.txt`); otherwise it is a sampling gap and owes
its stack, and the sampler now keeps its first failed attach of each identity (`<pid>-<start>-sampling-failures.txt`,
with #554's attempt outcomes). The evidence check excuses a live worker only by a not-sampled outcome that the recorded
policy bears out, with no retained sample and no failed sampling attach of its identity, or by a setup, teardown or
between-tests outcome that the retained cancel-collection frames themselves classify so; a worker inside its test's call
still owes its stack. That a policy-excluded worker, such as the Windows serial controller mid-test, owes no stack is
the current behaviour pending the operator's decision, not a settled policy. The flake entry `windows-cancel-live-stack`
stays open, with the Windows lanes of four more superseded runs and this PR as its planned fix: closure awaits a
sighting bundle, or the first superseded runs after merge, that establishes the cause. The Linux lanes of those runs
open `linux-cancel-live-stack`, whose cause is the pre-signal warning attach that #554 types, so its next sighting names
why.
