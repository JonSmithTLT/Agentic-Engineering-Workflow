# Testing and CI strategy

**Status:** implementation-level source of truth for how AEW's tests are organized and how CI provides assurance. Adopted 2026-09-27, after M1 (`main` at `6dd922e`).
- `pyproject.toml` (markers), `tests/helpers/lanes.py` (lanes, shards, reports, isolation guards), `.github/workflows/ci.yml`, `.github/workflows/nightly.yml` and `tools/ci/` **implement** this document. They are not the only place the design exists.
- A change to the rules here updates this document in the same pull request.

## 1. Non-negotiable rule

CI optimization never weakens established assurance.
- **No meaningful assertion is deleted, weakened, skipped or replaced to make CI faster.**
- **No deterministic regression runs only nightly.**
- **No real process, Git or crash boundary is replaced by an in-process shortcut** where that boundary is part of the property under test.
- Speed comes from scheduling (lanes, shards, parallel workers), from runner configuration, and from new tests choosing the cheapest boundary that still carries the property.

## 2. Test taxonomy

The **directory** says what a test is. **Markers** are used only for properties that cut across directories. Every test maps to exactly one **CI lane**, through a pure function of its path and markers (`lanes.lane_of`, first match wins). A test that maps to no lane stops the run with a usage error.

| Lane | Rule (in order) | What it holds | Class |
|---|---|---|---|
| `live` | `tests/live/**`, collected **only with `--live`** | Real harness binaries and real models: the harness conformance scenarios, the live twins of AT-14..AT-17 on OpenCode 2.0.18, and unscripted free-model trials (a Ticket through implementer, reviewer and verifier; and a seeded defect through rejection and rework), where AEW's invariants are asserted and the models' outcomes are recorded (M3). Opt-in and local; never part of CI or the assurance check, which never collect it. | Live evidence; not a merge gate |
| `serial` | marker `serial` | Properties that *are* timing or real-process concurrency: 2×50 racing writers, the real `os._exit` kill matrix and the cross-process stale writer (`tests/integration/test_store_processes.py`), and the pty operator takeover (AT-4b) | Deterministic regression; never parallel |
| `acceptance` | marker `acceptance(id)` | AT-1..AT-17 and KC §26 scenarios through the real CLI and real git; M3's AT-14..AT-17 through real supervisors and harness processes (the fake harness and the OpenCode adapter against a fake V2 server). `pytest -m acceptance` selects them all, including those in `serial`. | Deterministic merge gate |
| `adversarial` | marker `exploratory` | The seeded walks: the M1 composition walk (5 seeds × 60 steps) and the M2 hierarchy walk (5 seeds × 80 steps). Their default budgets are merge gates; larger budgets run nightly. | Seeded exploration, deterministic per seed |
| `fast` | `tests/unit/**`, `tests/test_spec_pin.py` | Pure logic, schemas, the store model and in-process fault injection, the frozen-spec pin, CI tooling | Deterministic |
| `integration` | `tests/integration/**` | Engine features over real git and the real CLI | Deterministic |
| `regression` | `tests/regression/**` | Independent-review probes (preserved **unchanged**), composition tests, the cross-operation invariant oracle, and the timing-free control-plane scale regression (M3: each command's counts of git processes, parses, commits and renders must not grow with the project; `m3-performance.md`) | **Permanent deterministic regression** |

### Deterministic regression versus exploration

- **Deterministic regressions** (review probes, compositions, crash matrices, acceptance scenarios) have fixed inputs and run on **every pull request**. A known failure, once fixed, is never demoted to nightly-only coverage.
- **Exploration** is seeded and randomized: the walk, randomized store crashes and repeated races.
  - Its default budget runs on every pull request.
  - Nightly runs larger budgets with rotating seeds, which are printed for reproduction.
  - When exploration finds a reproducible failure, the failing sequence becomes a deterministic test in `tests/regression/`, with or before its fix.

### Crash and race coverage (a property, not a lane)

Crash-injection tests live in several lanes:

| Where | Mechanism |
|---|---|
| `tests/unit/test_store.py` | In-process `AEW_FAULT_MODE=raise` at every transaction point, plus 200 randomized iterations |
| `tests/integration/test_store_processes.py` (`serial`) | Real process killed with `os._exit` |
| `tests/integration/test_integration.py::test_crash_during_publish_reconciles` | CLI child crashes at each publish point |
| `tests/acceptance/test_at4a_at7.py` | CLI transition and assignment crashes |
| `tests/regression/` | Crash then reconcile compositions |
| The walk | Random transaction and publish crashes |

Deterministic fault points are named code locations, not timings. That is why these tests may share a machine (§5).

## 3. What CI requires

| When | What runs | Blocking |
|---|---|---|
| Every pull request, every push to `main`, the merge queue | `core` per OS (the `fast` lane, then `serial`) + the `integration`, `acceptance`, `regression` and `adversarial` lanes per OS + `assurance` | **Yes** |
| Nightly (07:17 UTC) and on demand | serial reference run, extended walk, race repetition, extended randomized crashes, extra interpreter matrix | No; failures open an issue |

- **One gate for everything.** There is no separate "PR subset" versus "merge set": every merge gate runs on every pull request, in parallel. Fast feedback comes from ordering and parallelism, not from deferring assurance.
- **The merge gate is the `assurance` job.** It fails unless, per OS and from the lane reports:
  - every job collected the same test set;
  - every collected test ran exactly once across all lanes and shards;
  - no session failed, which includes the isolation guard (§5);
  - no test failed or errored;
  - the skipped tests are exactly those pinned in `tests/platform-skips.yaml`;
  - no xfail/xpass occurred unless pinned.

  It also fails if any test job did not succeed. Mark `assurance` as a **required status check** on `main`.
- **The dashboard joins the same gate** (F20.1, 2026-10-03). `ci.yml` calls `web.yml`, whose `changes` job decides whether `web/`, the shared contract (`docs/design/dashboard-api-v1-provisional.yaml`) or `web.yml` changed (merge base for pull requests and merge groups; it fails closed). If so, `checks` runs: locked install, the contract's acceptance digest, generated-artifact consistency, typecheck, lint, the frontend tests, the production build with its mock exclusion, the demo build and the compiled browser checks. Its `result` job passes only when the checks passed, or when nothing they cover changed, and `assurance` requires it. The Python lanes never need Node, and the web jobs never need Python.
- **The gate has already caught one gap.** On its first run it found that the frozen-spec tag `aew-spec-frozen-2026-09-25` had never been pushed to GitHub. So `test_spec_pin.py::test_tagged_revision_carries_pinned_blobs` had skipped silently in every earlier CI run. The tag was pushed on 2026-09-27, and the test now runs on both OSes.
- **The nightly lane has already found one gap.** On its first run (150 steps, fault rate 0.15), seeds 1014 and 1034 failed on both OSes, and the failure was in the walk harness, not in AEW.
  - A crash after an assignment's commit point left a live implementer invocation whose credential died with the process. The walk had no model for that state.
  - AEW's behaviour was correct: it refuses a second implementer while one is live, and the Lead recovers with `aew invoke cancel` followed by a fresh dispatch.
  - Per the policy, the failure became a deterministic CLI test, `test_compositions.py::test_an_assignment_committed_by_a_crashed_process_is_recovered_by_cancel_and_redispatch`. The walk now models the recovery. The default merge-gate seeds take step-for-step identical paths before and after that change.

### Coverage (register E2, M4-A)

- **What is measured.** Line and branch coverage of `src/aew`, measured with coverage.py (the `coverage` extra) on the Linux jobs: the `fast` lane in `core`, and every shard of the `integration`, `acceptance`, `regression` and `adversarial` lanes. Every Python subprocess the tests start is measured too: `aew` CLIs, harness supervisors, the Lead broker and xdist workers (`patch = ["subprocess"]`, `parallel = true`, `[tool.coverage.run]` in `pyproject.toml`). The `serial` lane runs without coverage, because its property is timing.
- **Where the data goes.** Each job writes its data files where `COVERAGE_FILE` points, under the runner's temp directory, never into the checkout (the isolation guard, §5, fails a run that writes into it), and uploads them as a `coverage-*` artifact.
- **The ratchet.** `assurance` combines every job's data and runs `tools/ci/coverage_gate.py`. It writes the total and per-package table to the job summary, and fails when total line or branch coverage falls more than 0.3 percentage points below `tests/coverage-baseline.json`. Coverage may rise freely. Raising the baseline is a deliberate commit (`--update`), never automatic.
- **The other platform's code.** A block that can only run on one OS is marked `# pragma: windows-only` or `# pragma: posix-only`, and the measurement excludes the other OS's marker (`AEW_COVERAGE_OTHER_OS`, default `windows`, so CI on Linux needs no setting). Both sides still run in their own OS's lanes; only the number ignores code that cannot run where it is measured.
- **What it is for.** Coverage points to thin tests; it is not a target to game. The ratchet keeps it from silently falling. A new test is written for a behaviour, not for a line.

### Failure and merge-blocking policy

- **Red `assurance` means no merge.** Re-running a failed job is allowed only to rule out runner infrastructure (network, image). A test that fails and then passes on re-run is a defect to investigate, not a flake to ignore.
- **Never mark a test xfail or skip to get green.** Changing `platform-skips.yaml` is a reviewed decision that names the platform that covers the test.
- **A nightly failure opens or updates a `nightly-failure` issue.** Triage it before the next merge to `main`. A reproducible failure becomes a deterministic regression test.

## 4. Platform responsibilities

| | Linux (Python 3.11: Rocky 8 / SPT wheelhouse target) | Windows (Python 3.13: developer workstation) |
|---|---|---|
| Runs | Everything | Everything except the 5 pinned POSIX-only tests |
| Only here | pty operator takeover (AT-4b), executable-bit and symlink sync (review M6) | `CREATE_NO_WINDOW` process launching; AT-1's in-process terminal substitute; Windows file-replace retry paths |
| Nightly extra | Python 3.13 | Python 3.11 |

Platform-specific tests use `skipif` with a reason naming the platform semantics they need, and are pinned in `tests/platform-skips.yaml`. No test may appear on a desktop: CLI test processes run with `CREATE_NO_WINDOW` on Windows and `start_new_session` on POSIX.

## 5. Concurrency: what may run in parallel

- **Serial: never parallel.**
  - The `serial` lane runs in its own step with `-p no:xdist`.
  - A `serial` test collected by an xdist worker **errors** with instructions; it is never silently deselected.
  - Add `serial` when timing, real-process concurrency, lock contention, terminal interaction or a wall-clock deadline is itself the property.
- **Everything else may run under pytest-xdist**, within one CI job or locally, because isolation is demonstrated:
  1. Each test owns its `tmp_path` repository, `.aew` control store, lock files and worktrees. Nothing in `src/` or `tests/` touches HOME, the global git config or shared paths.
  2. Environment changes go through `monkeypatch`, and xdist workers are separate processes.
  3. Deterministic `AEW_FAULT` injection points are code locations, not timings.
  4. **Enforced every run.** An autouse fixture fails any test that leaks an `AEW_*` variable or changes the working directory. The controller's **isolation guard** fails the session if the AEW checkout or the global git config changed.
  5. **Re-proven daily.** The nightly `reference` job runs the entire suite with no xdist and no shards on both OSes.
- **Coarse parallelism comes first.** Lanes are separate GitHub Actions jobs, on separate machines. Within a lane job, `-n auto --dist worksteal` uses the runner's vCPUs and never oversubscribes them. Timeouts (CLI 180 s, lock 60 s) are sized for the serial run and are not raised to hide contention.
- **Windows runner configuration.** Microsoft Defender exclusions for the test paths were A/B-measured and are **not used**. Summed Windows pytest time was 1037 s and 1202 s with exclusions and 1131 s without, which is within runner noise, and the exclusion step added ~9 s of setup per job.

## 6. Fixtures and process isolation

- **Use the real `aew` CLI in a separate process** whenever the process boundary is part of the property: acceptance scenarios, authority and credential checks, exit codes and error payloads, crash and recovery by a fresh process, and role drivers acting through launch contracts (`tests/helpers/aewflow.py`).
- **Use the in-process Engine API** (`aew.engine.api.Engine`) for new tests that need only deterministic engine semantics and gain nothing from another interpreter. The walk does this and stubs only the operator-terminal channel.
- **Do not convert existing process-bound tests for speed.** The harness's `Project.lead()` deliberately reads the revision through a `lead show` subprocess (~20 % of CLI time). Moving it in-process would move post-crash recovery out of a CLI process.
- **Every test builds its own repository and project** (`make_git_repo`, `sample_project`). Setup is ~7 % of runtime (measured), so fixture repositories are not shared, templated or cached.

## 7. Caching

- **Cached:** pip's downloaded wheels only (`actions/setup-python` `cache: pip`, keyed on `pyproject.toml`). Dependency resolution still runs every time.
- **Never cached:**
  - virtualenvs: the dependency ranges are unpinned, so a cached venv would freeze versions silently;
  - `.pytest_cache`: CI runs `-p no:cacheprovider`, so nothing like `--lf` can change selection;
  - any `.aew` control state, fixture or temporary repositories, worktrees, or lane reports.
- **Shard-balancing durations** (`tests/durations.json`) are **committed and reviewed**, not cached. Stale durations affect only balance, never which tests run. Refresh them from the nightly reference reports with `tools/ci/update_durations.py`.

## 8. Runtime budgets

| Feedback loop | Budget | Measured (2026-09-27) |
|---|---|---|
| Targeted local run (one lane, `-n auto`, 16-thread Windows workstation) | 1–3 min | 55 s (integration) to 111 s (regression) |
| Local full run (`-n auto -m "not serial"` + `--lane serial`) | ≤ 5 min | 268 s (260 s parallel + 8 s serial lane) |
| First CI signal (`core`, Linux: frozen-spec pin + unit + serial) | ≤ 3 min | 29–32 s (Windows `core`: 71–123 s) |
| Full PR / merge assurance (first job created to `assurance` done) | ≤ 15 min (target 10) | **279–325 s** over 3 runs (383–409 s while sharing the 20-job concurrency limit with a nightly run) |
| Nightly | ≤ 90 min | first validation run: Linux jobs 98–1190 s; Windows jobs 196–1106 s, plus the Windows serial `reference`, the long pole, at 2675 s (~45 min). **Over budget since 2026-10-01:** that job took 76 min on 2026-09-30, then hit its 90 min job timeout three nights running, while the Linux one grew from 41 to 62 min. Its timeout is now 150 min, so the nightly finishes. The budget still stands, and meeting it again needs the job split or sped up |

Before and after:

| | Before (`0daf11f`, one serial job per OS, push + PR both ran) | After (12 jobs, xdist within lanes) |
|---|---|---|
| Longest Windows job | 2656–2781 s (pytest 2623–2752 s) | 267–313 s |
| Longest Linux job | 976–1037 s (pytest 967–1028 s) | 197–224 s |
| PR wall clock | ~46 min, and the run was duplicated by the push trigger | ~5 min |
| Runner minutes per PR commit | ~124 (2 × ~62) | 31–35 |
| Local Windows, whole suite serially | 1499 s (per-test sum; 552 tests) | 1520 s (602 tests: 597 passed, 5 pinned skips, the same outcomes as the parallel run) |

The longest jobs are the Windows `adversarial` lane (the M1 walk's 5 seeds on 4 workers, 140–280 s per seed depending on the runner; the M2 hierarchy walk adds ~50 s), the Windows `acceptance` shards (M2's AT-13 alone is ~300 s there). Since M2 the lane jobs are: Linux integration 1, acceptance 1, regression 2, adversarial 1; Windows integration 2, acceptance 2, regression 3, adversarial 2 (14 lane jobs, 17 with `core` and `assurance`, sized from the first two M2 CI runs); the `integration` lane and the two `regression` shards. Runner-to-runner variation is up to 2× for CPU-bound jobs.

A lane that outgrows its budget gets another shard: add a matrix entry in `ci.yml`, since shards are deterministic. Do not move it to nightly.

## 9. Classifying a new test

1. Put it in the directory that says what it is:
   - `tests/unit` for in-process logic;
   - `tests/integration` for real git and/or the CLI;
   - `tests/regression` for a reproduced defect or composition, including review probes, which are preserved unchanged.
2. Add `acceptance("<id>")` if it is (part of) an acceptance scenario, and list it in `acceptance.md`.
3. Add `serial` if timing, real-process concurrency, lock contention, a pty or a wall-clock deadline is the property.
4. Add `exploratory` if it is seeded exploration whose budget can grow. Give it env knobs whose defaults are the merge-gate budget.
5. A new directory or lane needs a rule in `tests/helpers/lanes.py`, a unit test in `tests/unit/test_lanes.py`, a CI matrix entry, and an update to §2 of this document.
6. If it needs a platform, use `skipif` with the reason and pin it in `tests/platform-skips.yaml`.

## 10. Local commands

```bash
pip install -e ".[dev,parallel]"                       # parallel = pytest-xdist (optional)
python -m pytest -q                                     # everything, serially (always valid)
python -m pytest --lane fast -q                         # seconds: unit + frozen-spec pin
python -m pytest --lane regression -n auto -q           # one lane in parallel
python -m pytest -n auto -m "not serial" -q && python -m pytest --lane serial -q   # full, fast
python -m pytest -m acceptance -q                       # all acceptance scenarios
COVERAGE_FILE=/tmp/aew-cov/.coverage python -m coverage run -m pytest -n auto -m "not serial" -q   # coverage (".[coverage]")
python tools/ci/coverage_gate.py /tmp/aew-cov --baseline tests/coverage-baseline.json   # report and check the ratchet
# On Windows, also set AEW_COVERAGE_OTHER_OS=posix, and keep COVERAGE_FILE outside the checkout.
AEW_WALK_SEEDS=4242 AEW_WALK_STEPS=150 python -m pytest --lane adversarial -q     # reproduce a nightly seed
python -m pytest --live tests/live -n 4 -q              # live lane: real OpenCode (AEW_OPENCODE_BIN), a free model
python -m pytest --live tests/live/test_opencode_acceptance_live.py -p no:xdist -q   # AT-14..AT-17 on real OpenCode
AEW_LIVE_RESULTS=trials.jsonl python -m pytest --live tests/live/test_opencode_model_live.py -p no:xdist -q   # a free model, unscripted
AEW_LIVE_ROUTING=implementer=openai/gpt-5.6-luna AEW_LIVE_PROVIDER_KEY_ENV=OPENAI_API_KEY \n  python -m pytest --live tests/live/test_opencode_model_live.py -p no:xdist -q   # paid models, per role (costs money)
```

The paid dogfood (M3 step 9) is not a test lane. It is an evaluation with its own driver, fixtures, hidden tests and pre-registered rubric in `eval/m3/dogfood/` (see its README), reported in `m3-dogfood-report.md`.

Seeds and budgets are controlled by these environment knobs; the defaults are the merge-gate values:

| Knob | Default |
|---|---|
| `AEW_WALK_SEEDS` | 11,23,37,41,53 |
| `AEW_WALK_STEPS` | 60 |
| `AEW_WALK_FAULT_RATE` | 0.08 |
| `AEW_HWALK_SEEDS` | 7,19,31,43,59 |
| `AEW_HWALK_STEPS` | 80 |
| `AEW_HWALK_FAULT_RATE` | 0.06 |
| `AEW_RACE_WRITES` | 50 |
| `AEW_CRASH_SEED` | 20260925 |
| `AEW_CRASH_ITERATIONS` | 200 |

## 11. Nightly lane

| Job | What | Why |
|---|---|---|
| `reference` | Whole suite, serial, unsharded, both OSes | Re-proves the parallel runs are equivalent; refreshes durations |
| `walk-extended` | 3 blocks × 6 rotating seeds per OS for both walks, 150 steps, fault rate 0.15 (hierarchy walk: 250 steps, fault rate 0.12) | More adversarial sequences and crashes |
| `race-repeat` | Serial lane ×10, then 200 racing writes per writer | Heavier race and kill repetition |
| `crash-extended` | 2000 randomized store crash iterations, seed = run number | Larger randomized crash counts |
| `matrix-extra` | Full suite on ubuntu/py3.13 and windows/py3.11 | Broader environment |

**Code scanning** (`.github/workflows/codeql.yml`) runs CodeQL for Python, GitHub Actions and JavaScript/TypeScript (the dashboard, since F20.1) on pull requests, on pushes to `main` and weekly. It is not part of `assurance`. It replaces GitHub's default setup so that `eval/` can be excluded (`.github/codeql/codeql-config.yml`): those are research and evaluation scripts the operator runs by hand, whose path and command findings are their intended use (PR #5 triage).

## 12. Known cost drivers and follow-ups

- **CLI subprocesses dominate test time** (about 80 % when measured for M2). Then, a read-only `aew` call cost about 250 ms, including about 65 ms of pure-Python YAML parsing of `control.yaml`. M3 step 7 changed the persistence core: YAML now goes through libyaml where PyYAML has it (`aew doctor` reports which), and identical control-state bytes reuse their parse within a process. The bare CLI floor is now about 0.1 s (`m3-performance.md`). The remaining cost is linear in `control.yaml`'s size, which ADR-0011 addresses before M4.
- **The M1 walk re-parses `control.yaml` for every harness query** (~40 times per step). The M2 hierarchy walk caches the parsed state by the file's identity, which cut a seed from 150–320 s to ~20 s with step-for-step identical paths; applying the same harness change to `test_composition_walk.py` is a separately reviewed change to an M1 regression file.
- **Coverage is measured on Linux only.** Windows-only code (process jobs, the console, file-replace retries) runs in the Windows lanes but is not in the number. Measuring the Windows lanes too, and combining both platforms, is a later decision if Windows-only code grows.
- **A Rocky Linux 8 container job** (the SPT target) is a candidate for the nightly lane.
- **Action majors.** The workflows pin `actions/checkout@v4`, `setup-python@v5` and `upload/download-artifact@v4`. GitHub runs these Node 20 actions on Node 24 with a deprecation warning. Bumping to the current majors (checkout v7, setup-python v7, upload-artifact v7, download-artifact v8) is a separate change that needs a check of their changelogs.
