# CI redesign: make the gate's cost proportional to the change (v0.2)

- **Status:** **Adopted** by the designer and the operator, 2026-10-06 (§5). Ingested 2026-10-06; until then it lived outside the repository with no register rows, which is how P4 went unbuilt (the [cost-detection investigation](../research/ci-cost-detection-investigation-2026-10-06.md)). The text is v0.2 as adopted, unchanged apart from this line, which read "proposal v0.2, 2026-10-06. v0.1 was approved in direction by the designer, who asked for four corrections and recorded the decisions in §5; this revision makes them, with the operator's ruling on the merge queue. Nothing is built." **Built:** P1 (PR #99) and P2 (PR #96), in `testing-and-ci-strategy.md` §3. **Tracked:** register E40 to E49 and E23. **Since adoption:** the repository's concurrency cap rose from 20 to 40 jobs (2026-10-07); §1's measurements were taken under the cap of 20, and a merge queue still needs an organization.
- **Basis:** the CI and testing posture review (2026-10-05, kept private); the lane reports of the last green merge-gate run (37390507069); a profile of four of the slowest test files on the Windows workstation; the PR history since 2026-10-03.
- **Problem in one line:** every pull request pays about 12 CPU-hours over 22 jobs whatever it changed, and the slow tests spend most of their time starting the CLI and rebuilding the same projects. So the gate gets slower with every feature, and it is now close to unable to go green.

## 1. What the measurements say

**Where the time goes (per OS, run 37390507069).**

| | Linux | Windows |
|---|---|---|
| Tests | 2,039 | 2,039 |
| Summed pytest time | 5.8 h | 6.3 h |
| Median test | 8 ms | 4 ms |
| Tests over 10 s: share of time | 495 tests, 97% | 487 tests, 96% |
| Tests over 60 s: share of time | 105 tests, 48% | 114 tests, 52% |
| Unit tests (`tests/unit`) | 0.05 h | 0.03 h |

The cost is entirely in about 500 scenario tests in `tests/integration`, `tests/regression` and `tests/acceptance`. The heaviest files are the queue, composition, history-surface, workspace and archival tests.

**What those tests spend it on.** Profiled locally: `test_queue.py`, `test_compositions.py`, `test_history_surface.py` and `test_workspaces.py`, 80 tests, 87 minutes.

- **82% of their time is CLI subprocess calls:** 2,961 calls, 30 to 50 per test, about 1.4 s each under load.
- **57% of their time is in the shared setup helpers** (`sample_project`, `create_planned_ticket`, `to_verified`, `to_commit_ready`, `prepare_and_validate`). That's rebuilding a project and walking a Ticket to COMMIT_READY before the test reaches what it tests. In `test_queue.py` this is 84% and up to 94% for single tests.
- **A CLI process costs about 560 ms before it does any work:**
  - 80 ms for Python itself;
  - about 450 ms importing AEW;
  - 364 ms of that is the dashboard server stack, which `aew.cli` imports eagerly for every command, `aew status` included.

**What runs it.** 73 PRs were opened since 2026-10-03:

- 22 were docs only (designs, the ledger, the register, the docs map);
- 2 were web only;
- 49 touched Python code, tests or CI.

Every one of them ran the full 22-job gate, and every sync with `main` ran it again.

**What it does to the gate.**
- A merge-gate run took 25 to 152 minutes of wall clock on 2026-10-05, against a 15-minute budget.
- 57 of the last 100 runs were cancelled.
- The integration lanes reach 21 to 26 minutes of their 30-minute timeout.
- Six of the last eight nightlies timed out (silently, until #92).

## 2. Diagnosis

1. **The gate's cost doesn't depend on the change.** A docs edit and an engine change pay the same 12 CPU-hours. With several agents merging around 25 changes a day through a 20-job concurrency cap, the queue, not the tests, sets the wall clock.
2. **Test cost grows with the product.** The strategy keeps the process boundary in the tests deliberately ("existing process-bound tests are not converted for speed"). That is right for a test whose property *is* the boundary. But the rule is applied to every step of every scenario, including the 30 to 50 setup calls before the step under test. Each new feature adds scenario tests that pay that setup again, so the total grows faster than the product.
3. **The CLI is expensive to start, for tests and users alike.** Half a second of imports per call is paid by every test step, and by every Lead tool call through `lead.cli`.
4. **Cost was never part of assurance.** The gate proves every test ran exactly once; nothing measures or bounds how much the run costs. So the drift was invisible until runs started timing out.

Re-sharding answers none of these. It moves the same 12 CPU-hours into more jobs, against the same concurrency cap.

## 3. Proposal

**v0.1 → v0.2 (the designer's four corrections):**

| # | Correction | Where |
|---|---|---|
| 1 | Pre-merge assurance for reduced tiers: a full `merge_group` gate is preferred; without a merge queue on a personal-account repository, an always-full `main` run is the stated compensating control | P1 |
| 2 | A definition of a snapshot-safe (quiescent) starting state; an immutable template per worker; one semantic-equivalence oracle; isolation of the in-process driver | P3 |
| 3 | Cost accounting now; no hard wall-clock merge failure until runner variance is measured; any performance gate is on controlled metrics | P4 |
| 4 | Duration history influences shard placement only, never which tests run, and falls back safely when absent or stale | P4 |

Five changes, in order of payoff against risk. None of them weakens an assertion, drops a test, or removes a process boundary from a test whose property is that boundary.

### P1. A gate tiered by what changed, decided fail-closed

- **The change sets the tier.** The `changes` job (the same pattern as `web.yml`'s, which already fails closed) classifies the PR's diff against its merge base:

  | Tier | Changed paths | Runs |
  |---|---|---|
  | `docs` | only `docs/**`, `*.md` outside `src/`, `web/docs/**` | `core` (the fast and serial lanes, which include every docs, ledger, register and link test) on both OSes, and `static` |
  | `web` | only `web/**` plus docs | `docs` tier plus the web checks |
  | `full` | anything else, or a diff that cannot be computed | everything, as today |

- **`assurance` enforces the tier.** It recomputes the tier from the same diff and requires exactly the lanes that tier names. A docs PR whose diff touches `src/` fails the gate rather than passing with too little.
- **Pre-merge assurance for reduced tiers (operator, 2026-10-06).** A pre-merge full `merge_group` gate would be preferred, but GitHub does not provide merge queues for personal-account repositories. AEW remains on the operator's personal account by prior decision. Therefore reduced PR tiers are backed by an always-full `main` run. This is an explicit reduction in pre-merge assurance for the docs and web tiers, accepted for throughput. If repository ownership moves to an organization later, full merge-group assurance should replace this compensating control.
- **What the compensating control means in practice:**
  - `main`'s push run is always `full`, whatever tier the PR took;
  - a red full run on `main` after a reduced-tier merge is triaged as a tier-classification defect: the classifier is corrected, and a test pins the case;
  - code PRs are unaffected, since they always run `full` before merge;
  - the `merge_group` trigger stays in `ci.yml`, and `assurance` refuses any tier but `full` on a `merge_group` event, so moving to an organization needs no CI change.
- **Expected effect:** 30% of PRs drop from about 12 CPU-hours to about 5 minutes. The concurrency cap frees up for the code PRs.

### P2. Lazy CLI imports

- Import each command group's module when its command runs, not when `aew` starts. The dashboard server stack, the OpenCode adapter and the history index are imported only by the commands that use them.
- **Measure:** `python -X importtime -m aew status` before and after. Target: under 200 ms of imports for the common Lead commands.
- **Measured effect (built 2026-10-06):** less than v0.1 estimated. The dashboard modules import the engine, which every ordinary command imports anyway, so lazy-loading the dashboard and the doctor saves about 0.1 s, not 0.35 s: `aew status` went from about 920 ms to about 825 ms, roughly 10% of every CLI call. What remains is mostly fixed cost: the JSON-schema library (about 100 ms), which every command needs to validate state, and the engine's own modules. P3, not P2, is where the large saving is.
- **No test changes.** The enforced property is architectural: a unit test pins that the common Lead commands (`aew status` among them) do not import `aew.dashboard` or other heavyweight modules unrelated to them. 200 ms is a measured objective, never a CI assertion.

### P3. Shared setup, with the boundary kept for the step under test

This needs the operator to amend one strategy rule. "Process-bound tests are not converted for speed" becomes:

> A test keeps a real process boundary for the steps whose property is that boundary: the step under test, crash and fault injection, credentials and terminals, harness custody, and acceptance scenarios. Setup that only brings a project to a starting state may use the in-process driver.

- **An in-process driver for setup, designed as a test driver.** It is not just "call `main()`". `aewflow`'s helpers run the CLI's `main()` in the test process, with the same argument parsing, output and exit codes, instead of spawning `python -m aew`. The default stays subprocess, and setup helpers opt in.
- **The driver's invariant:** an in-process setup invocation is observationally isolated from the next, except through the project state it intentionally modified. The driver saves and restores the following, and its own tests prove it does:
  - the working directory and the environment (the existing guards that fail a test leaking `AEW_*` or a changed cwd apply to every invocation);
  - stdin, stdout and stderr;
  - logging handlers;
  - parser and other module-global state;
  - thread locals and context variables;
  - every cache that is not intentionally project-scoped, which is cleared or keyed by project root.
- **Snapshotted starting states, only from explicitly classified quiescent states.** A starting point is built once per worker as an immutable template that no test ever works in; each test gets its own copy.
  - **Snapshot-safe means quiescent and relocatable.** A state is eligible only when it contains none of:
    - an active lease, run or invocation;
    - a live credential;
    - a supervisor or other process identity;
    - a transient lock;
    - wake-file state;
    - an absolute workspace identity that can't be rebound;
    - time-dependent state whose age has meaning (deadlines, heartbeats, grace periods).
  - **Each snapshot kind is declared and checked.** An initialized project is snapshot-safe. A COMMIT_READY project is eligible only once a check proves everything in it quiescent and relocatable. The checker refuses an ineligible state rather than snapshotting it.
  - **A copy is a real, independent repository.** Worktrees are re-registered (`git worktree repair`) and absolute paths rebound. A test proves a copy shares no git objects, worktrees or `.aew` state with its template.
  - Copies are used only where the project is input, never where repository construction is the property under test.
- **One semantic-equivalence oracle, defined once.** Before a helper switches to the in-process driver or a snapshot, a test builds the same starting state both ways and compares the two with one shared oracle.
  - It normalizes only a fixed, reviewed list of ephemeral fields: generated ids, timestamps, absolute paths and process ids.
  - It requires equality for everything authoritative: control and workflow state, evidence contents, git refs and objects, and the provenance relationships between them.
  - Adding a field to the normalized list is a reviewed change to the oracle, never a per-helper exception.
- **Expected effect:** setup is 57% of the profiled time (84% in the queue tests). Removing most of its process starts and rebuilds should cut the slow files' time by 40 to 50%. This is the change that stops the growth: a new scenario test then costs its own steps, not a fresh project.

### P4. Cost as part of assurance

- **`assurance` writes a per-run cost record**, as a job summary and an artifact. It covers:
  - queue delay and end-to-end wall clock;
  - runner-minutes, and wall time per lane and shard;
  - total pytest time, the slowest 20 tests, and CLI calls per test;
  - the share of collected tests present in `durations.json`.
- **Two separate concepts:**
  - **The hard safety bound stays the job timeout.** It is not a correctness assertion, and runner speed never fails a correct change.
  - **Wall-clock health is reported, not gated, for now:**
    - a shard over 20 minutes warns in the summary;
    - a shard over 25 minutes is an explicit CI-health violation in the summary;
    - repeated violations on `main` open or update a CI-health issue.

    Whether wall-clock becomes a hard gate is decided after P2 and P3, once runner variance is measured.
- **Any performance gate is on metrics AEW controls**, and only once baselines exist. The candidates are aggregate pytest duration, CLI subprocess starts, expensive fixture constructions, the slow-test aggregate and estimated cost per test family. A large increase a PR causes, judged against a baseline with its variance, can then fail as a performance regression.
- **Duration history influences placement, never eligibility.**
  - It is a non-authoritative balancing cache: a green `main` run may update it, and any run may use it.
  - Exactly-once assurance proves test membership independently of it, so the same commit runs the same set of tests whatever the cache holds.
  - A missing, stale or corrupt cache falls back to balancing by test count, never to a failure or an omitted test.
  - The committed `tests/durations.json` stays as the fallback, refreshed by an automated PR when drift passes a threshold.

### P5. Decisions on the matrix (the operator's)

These trade per-PR proof for throughput, so they're yours to decide; I'm not recommending them by default.

1. **Full lanes on one OS per PR, both OSes on `main` and nightly.** The second OS on PRs runs `core` plus the lanes that hold its platform-specific code: harness, containment, process, store. That halves the PR cost of the scenario lanes. A Windows-only or Linux-only regression is then caught on `main`'s run, after merge, not before.
2. **Windows coverage (#69) in the nightly reference run, not the merge gate.** The nightly runs serially and its shards have room. The merge gate keeps the Linux coverage ratchet. Running Windows coverage in the gate would roughly double the Windows lanes (measured on #69: regression shards went from 8–14 to 16–19 minutes), which would time out integration on today's suite.
3. **Larger runners** (8 vCPUs) for the scenario lanes, as an experiment once P2 and P3 have shown what stays CPU-bound (the review's item 14).

## 4. Order and expected outcome

| Step | Effort | Risk | Effect |
|---|---|---|---|
| P1 tiered gate | Small to medium | Low for code; an accepted, stated reduction in pre-merge assurance for docs and web tiers, compensated by an always-full `main` run | 30% of PR runs drop to minutes |
| P2 lazy imports | Small | Low; no test semantics change | About 10% off every CLI call (measured) |
| P4 cost record (no wall-clock gate yet) | Small | None | Drift becomes visible; gates later on controlled metrics |
| P3 shared setup | Large, per test family | Medium; guarded by equivalence tests | 40 to 50% off the scenario files; growth stops |
| P5 matrix | Configuration | Your trade-off | Up to half the PR cost of scenario lanes |

With P1, P2 and P3, a code PR's gate should fall from about 12 CPU-hours to roughly 5 to 6. Its longest shard should fall well under 15 minutes. Docs PRs stop competing for runners. This is an estimate from the profile, not a measurement; P4 measures it.

**Meanwhile:**
- #92 (the nightly report fires on timeouts) lands as a bug fix.
- #70 is merged.
- #69 waits for decision P5.2.
- The store crash slowdown (1–7 minutes before the outbox, over 60 after) is investigated as a performance regression, not given a bigger budget.

## 5. Decisions (designer and operator, 2026-10-06)

- **P1:** ADOPT. A full `merge_group` gate is preferred, but unavailable on a personal-account repository. The always-full `main` run is the compensating control for the docs and web tiers, an accepted reduction in pre-merge assurance (operator). It is replaced by full merge-group assurance if the repository moves to an organization.
- **P2:** ADOPT, and build it first: it changes no testing semantics and makes the real CLI faster.
- **P3 strategy amendment:** ADOPT, with the snapshot-eligibility, immutable-template, semantic-equivalence and driver-isolation constraints above.
- **P4:** ADOPT the measurement now. The hard wall-clock gate is deferred until runner variance is measured.
- **P5.1** (one full OS per PR): DEFER for this phase. Revisit only with post-redesign measurements, if CI is still too expensive.
- **P5.2** (Windows coverage in the nightly): ADOPT temporarily, as a placement decision for the current performance, not the architecture. Revisit after P2 and P3.
- **P5.3** (larger runners): DEFER until P2 and P3 have been measured.

**Sequence:**

1. #92, the nightly reporting fix.
2. P2, lazy imports.
3. P1, the tiered PR gate, with the always-full `main` run.
4. P4, the cost record, without a wall-time failure.
5. Refresh and rebalance the current shards from the new data.
6. P3, the setup driver and the snapshot framework; then migrate the expensive families one at a time.
7. P5.2, Windows coverage moved to the nightly.
8. Measure the resulting system.
9. Only then consider larger runners or any reduction in cross-platform PR coverage.
