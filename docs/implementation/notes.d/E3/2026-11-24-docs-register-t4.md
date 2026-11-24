**The membership of one lost Windows regression shard (2026-11-24).** For `windows-regression-no-response`, the lane
report of run 45405842359's `regression 2/3 (windows-latest)` attempt 2 names the shard's 109 tests; the shard plan
comes from the run's tier job, so attempt 1, the lost job 138486559048, ran the same set. Its longest tests are
compositions and scale tests of 30-66 s. It holds
`tests/regression/test_m4b_review.py::test_the_hostile_repository_runs_its_programs_under_plain_git`, the lead the flake
register names, so that test was in this lost shard too. That is still a shard-membership lead, not a cause: shards are
cut from slowly changing durations, so membership is sticky. The test runs every kind of configured program git starts
(filters, a long-running process filter that ends in `cat`, hooks, fsmonitor, diff and merge drivers), each through
`sh`; on Windows each child also gets a console host. Whether any of them outlives git there is unmeasured. #546's
host-resource stop names the running tests, so the next such loss, if it is resource exhaustion, names them.
