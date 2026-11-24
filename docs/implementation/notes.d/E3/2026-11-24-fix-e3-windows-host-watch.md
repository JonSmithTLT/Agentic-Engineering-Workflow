The Windows regression lane's silent lost runner (flake register `windows-regression-no-response`), 2026-11-24. Two
more jobs were lost the same way: run 45358974748, job 138324120351 (PR #540, 08:51 to 09:40) and run 45405842359, job
138486559048 (PR #545, 13:40 to 14:28), each `regression 2/3 (windows-latest)` ending `failure` after about 48 minutes
against a normal 7 to 14, with its pytest step left in progress, no log, no recovery step and no evidence. Both are now
in the flake register entry. The leading suspect is the Windows host running out of something the lane's tests use
(commit charge, handles, processes or the service session's desktop heap: every `CREATE_NO_WINDOW` child also gets a
conhost, and the M4-B note above saw Git's shell fail to start with `0xc0000142`). The other is plain loss of the hosted
runner. Until this change nothing watched the host's resources on Windows: `lane_step.memory_used` and the cgroup
pressure capture are Linux-only.

What this adds. `tools/ci/lane_step.py`'s supervisor, which runs outside the session's job object, reads the Windows
host once a second (`GetPerformanceInfo`: commit charge and limit, handles, processes, threads, kernel pools; and the
free space on `RUNNER_TEMP`'s drive). It stops the lane at a stated limit: commit charge at 92% of the commit limit,
1,000,000 handles, 1,000 processes, or under 2 GiB free. The reason for each is beside it in the code. A stop writes
`runner-resources-host-high-water.txt` (the limits crossed, the reading, the lane's peaks and the running tests' names),
takes the stacks the cutoff path takes, ends the lane's job object and exits 72 (`HOST_RESOURCES_EXIT`), so the step
fails while the runner can still publish. The evidence check names that death `host-resources` instead of reporting it
unclassified. Every lane's exit record carries its host peaks as `host_resources_peak`, and the step log prints them.

What stays unknown. The limits are first estimates, set well past a loaded runner's normal readings: the peaks of green
Windows lanes, in their step logs, are what recalibrates them. Desktop heap cannot be read directly, so the process
count stands in for it. A resource the reading does not cover (nonpaged pool, say) or an exhaustion faster than one
second can still be missed, and nothing here explains a runner that is lost for another reason. If the next lost job
again leaves no stop file and no evidence, these limits did not catch it, and the next step is an off-VM heartbeat: a
check run the lane updates while it runs, so the last beat names where it stopped. It needs `checks: write` and a
workflow permission change, which is the operator's decision, so it is not built here.
