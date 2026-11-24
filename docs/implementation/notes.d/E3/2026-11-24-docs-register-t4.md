**The membership of one lost Windows regression shard (2026-11-24).** For `windows-regression-no-response`, the lane
report of run 45405842359's `regression 2/3 (windows-latest)` attempt 2 names the shard's 109 tests; the shard plan
comes from the run's tier job, so attempt 1, the lost job 138486559048, ran the same set. Its longest tests
take 30-66 s. It holds `tests/regression/test_m4b_review.py::test_the_hostile_repository_runs_its_programs_under_plain_git`, the lead
the flake register names, so that test was in this lost shard too. That is still a shard-membership lead, not a cause:
shards are cut from slowly changing durations, so membership is sticky. The test's fixture configures every kind of
program git starts, each through `sh`; the test's `add`, `diff` and `commit --no-verify` run the clean and process
filters, the diff programs, fsmonitor and the commit hooks `--no-verify` leaves. Whether any of them outlives git on
Windows is unmeasured. #546's host-resource stop names the running tests, so the next such loss, if it is resource
exhaustion, names them.
