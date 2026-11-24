An unattributed lost job on PR #540 (2026-11-24), not a flake and not settled. Run 45358974748, head `b8827bd7`, job
138324120351 `regression 2/3 (windows-latest)`, attempt 1: it started at 08:51:02 and ended `failure` at 09:40:03,
49 minutes later, inside its 53-minute timeout. Its pytest step was still recorded `in_progress`; the recovery step,
which runs on `always()` after a failed or cancelled lane step, and the upload step never started. The job's log
returned 404 and `evidence` reported no published evidence, so no test, stack or cause is known. The session deadline
(1,800 s), the per-test timeout (600 s) and the step timeout (41 minutes) would each have ended a hang in the suite and
let the recovery step run, which suggests a lost runner, but nothing confirms it. Attempt 2 of the same job
(138366626649), on the same commit, passed in 12.5 minutes (10:09:53 to 10:22:27). That pass does not explain attempt 1
(testing strategy, the re-run rule). A second job lost this way, with its step left `in_progress` and no recovery, is
the evidence to look for: if it recurs, the recovery that depends on the job's own runner cannot be the only record.
