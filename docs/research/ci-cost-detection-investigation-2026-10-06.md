# Why a 648-second unit test went unnoticed: CI cost detection (2026-10-06)

- **Status:** investigation by the lead developer, 2026-10-06, asked for by the operator. It is input to the
  [CI redesign](../design/ci-redesign-design-v0.2.md), whose P4 it argues should be built first. Its recommendations
  are register rows (§5); the operator decided §5.2 on 2026-10-06.
- **Question:** the suite's depth and breadth are deliberate. Why did nothing detect one test taking half of a job's
  timeout?

## 1. What happened

- **The test.** `tests/unit/test_lead_reachability.py::test_no_message_in_aew_hands_an_operator_decision_to_whoever_reads_it`
  was added by PR #103 (merged 2026-10-06). It built the whole CLI parser once for every message string in `src/aew`
  (18,941 of them, 9 to 18 ms each). PR #111 builds it once; the test now takes 0.7 s.
- **What it cost:**

  | Where | Before #111 |
  |---|---|
  | The test, Windows workstation | 167 to 184 s |
  | The test, Linux CI under coverage (lane report, #109's run) | **648 s, 79% of the fast lane** |
  | Linux `core` fast lane | 13m42s (#109's run); over 19m43s on #110's run, cancelled by the 20-minute job timeout at 100% |
  | Strategy §8's budget for that job | **3 minutes** (measured 29 to 32 s on 2026-09-27) |

- **Separately, the same day:** `main`'s push run for `389e32d` failed because `integration 1/3 (ubuntu-latest)` hit
  its 30-minute timeout (30m45s). That is lane growth, not an outlier: the integration lanes ran 21 to 26 of their 30
  minutes when the CI redesign measured them.

## 2. Root cause

A per-item rebuild of a fixed value inside a loop over every message in the package. Its cost grows with the
codebase, so it was cheap when written and becomes expensive as `src/aew` grows. Correctness review passed it; nothing
looked at its cost.

## 3. Why it was not detected

1. **The data existed and nothing read it.** Every lane already writes `aew/lane-report/v1` with each test's
   duration, uploaded as an artifact on every run. #109's Linux fast-lane report ranks this test first at 648 s,
   nineteen times the next (33.5 s). No step reads durations, and the assurance check reads only membership and
   outcome.
2. **The budgets are written, not checked.** Strategy §8 gives Linux `core` 3 minutes. It ran 14 to 20 minutes, and
   no job compares a lane's wall time with its budget.
3. **The only cost signal is the timeout, and it fires at 100%.** A job timeout is a safety bound, not a measurement:
   there is no warning before it, and when it fires the result reads as "tests never ran", not "this test is slow".
4. **The adopted fix was never built, and never tracked.** The CI redesign's P4, "cost as part of assurance" (a
   per-run cost record with the slowest 20 tests, wall time per lane, and a warning over 20 minutes), was adopted by
   the designer and the operator on 2026-10-06. It existed only in a plan outside the repository, with no register row,
   so nothing scheduled it. Its own diagnosis 4 describes this failure: "the drift was invisible until runs started
   timing out".
5. **Nothing prints timings.** pytest shows durations only when asked, so neither CI logs nor local runs surfaced it.
6. **Neither authoring nor review looks at cost.** The author ran the file locally (about 3 minutes) during #103 and
   did not question it; four review rounds checked correctness.
7. **A failed `main` run is not triaged by cause.** `main`'s integration timeout was visible only as `failure` in the
   run list; nothing distinguishes "a job timed out" from "superseded" from "a test failed", or asks for a fix.

## 4. What is sound

The coverage itself: the guard is a good test, and the fix kept every assertion (its reviewer showed the same 18,941
messages are checked and a planted stale message still fails). The assurance gate did its job: it refused to pass a
run whose tests did not all run. The lane reports were the right design; they lacked a reader.

## 5. Recommendations (register rows)

1. **Build P4 first** (E43). `assurance` writes the per-run cost record from the lane reports it already downloads:
   wall time per lane and shard against strategy §8's budgets, the slowest 20 tests, and each test's share of its
   lane, as a job summary and an artifact. Each lane also prints `--durations=20`. Cheap, and it would have named this
   test on its first run.
2. **A per-test cost check** (E45). A test that takes more than a set share of its lane's time (for example 25%), or a
   fast-lane test over a set number of seconds, is a CI-health violation. **It warns and never fails the gate**
   (operator, 2026-10-06), in line with the redesign's deferral of hard wall-clock gates until runner variance is
   measured; a share-of-lane rule depends far less on runner speed than raw seconds do.
3. **Refresh and rebalance from the record** (E44), and sweep the current fast-lane outliers (E46): a 33.5 s
   randomized crash test in the fast lane, and several 5 to 7 s surface-runner tests.
4. **Triage every failed `main` run by cause** (E47). A job that timed out on `main` raises attention, as #92 made the
   nightly do; a superseded run does not.
5. **Shared setup (P3)** (E42) is what stops the integration lanes' growth, the second problem in §1.
6. **Cost in review.** With the record built, a PR's summary shows its new tests' cost, and the reviewer brief asks
   for it. The brief is ours to change; AGENTS.md is the operator's.
