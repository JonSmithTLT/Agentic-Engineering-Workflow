The evidence-proof cancel control (`run-cancel-control`, both scenarios) failed twice with `controlled pytest lanes have
no overlapping time before collection` when one platform's runner queued (2026-11-25): run 45512919398, job 138864948990
(target run 45513035294, the Windows plant started 5 min 22 s after its Linux twin), and run 45547466156, job
138980412768 (target run 45547533341, Linux plant 04:34:53, Windows 04:40:16, 5 min 23 s later). Nothing in the evidence
under test was wrong. Each plant's 360 s window counts from its own deadline step, and the control triggers only once
both lanes are live and before either reaches its 60 s trigger reserve, so the Linux window had closed (04:39:55, the
control's failure) before the Windows lane opened (04:40:54): the two windows never overlapped. A controlled target's
plants now hold their deadline step until their twin has a runner, for at most
`prove_cancel_evidence.TWIN_BARRIER_SECONDS` (600 s), so both windows open together and the control's nine-minute
readiness clock starts once the later plant has a runner. A twin that is not live when the early plant reaches its
trigger reserve, or when the early plant's lane has already ended at its session deadline (a twin about 16 to 19 minutes
late, which reached the control only after the runner-allocation wait; #564 review), or that has no runner
`RUNNER_ALLOCATION_SECONDS` (20 minutes) after dispatch, is the control's own typed outcome, `PlantQueued`
(`plant-queued`, naming the late plant), which fails the control without claiming an evidence defect; the overlap
failure is kept for two live lanes whose windows still miss.
`test_a_plant_whose_runner_queues_late_still_overlaps_or_is_named_as_queued` proves this on modelled timelines (the
observed setup times, the lane ending at its session deadline): a twin up to 600 s late overlaps with the trigger inside
both plants' live windows, and twins 900 to 1300 s late are named `PlantQueued` on each of the three paths. No
flake-register entry: the register holds tests and lane sessions, and this was a deterministic defect of the control's
timing, not a lane's.
