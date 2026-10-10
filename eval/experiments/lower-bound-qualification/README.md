# Lower-bound qualification lane (`lbq-v1`)

**Status:** prepared and dry-run; **the run is the operator's**. It needs a provider credential and spends money (see
"Operator steps"). Experiment id `lbq-v1-deepseek-v4-flash`, `purpose: qualification`.

**Governed by:**
- the agent-effectiveness adoption record
  ([decisions-2026-10-09](../../../docs/design/decisions-2026-10-09-agent-effectiveness-adoption.md) §9 "Lower-bound
  pre-M4-H fixture", and §10.3);
- the synthesis ([§13.4](../../../docs/research/agent-effectiveness-and-model-leverage-synthesis-2026-10-09.md), the
  lane and its eight behaviours; §13.1, profiles as capability classes);
- the implementation delta's D3, and D2 (the session-database reader it relies on);
- the F19 instrument ([evaluation component design v0.2](../../../docs/design/evaluation-component-design-v0.2.md):
  preregistration, attempt ledger, hidden oracles, immutable runs).

## What it establishes

Whether a cheap OpenCode model can serve as the **lower bound** of the agent-effectiveness lanes. The lower bound is
the profile against which the question "does AEW's deterministic scaffolding amplify a weak worker?" is measured
later, raw against assisted, after the M4-H gate.

The lane produces a reusable **profile record** (`profiles.yaml`, `aew/eval-profile/v1`). Its `qualification_state`
is derived from three facts:

1. **Availability:** the pinned harness (OpenCode 2.0.18) offers the model.
2. **Floor:** the model completes AEW's bridge handshake and the typed submit path. This is rubric §2: in the live
   lane, the real-model implementer run ends with an accepted `implementation_report` after at least one bridge
   request.
3. **Ceiling:** the model still shows the weak-worker behaviours on seeded tasks (rubric §4: at least one of the
   eight). A model that shows none is `not_a_lower_bound`, and the next-cheaper profile is tried.

**What this run delivers.**
- **Scored now:** the floor, and the tree-observable half of the ceiling (behaviours 2, 4, 5 and 8 in part).
- **Scored later:** the session-observable half (behaviours 1, 3, 6 and 7, and the rest of 2 and 8). The F19
  session-database reader (D2) scores it from the kept databases, under the definitions frozen in the preregistration
  (`thresholds.behaviours`), within their 180-day retention window.
- **Interim state:** a profile that shows a tree-observable behaviour is `qualified` now. Otherwise its ceiling stays
  pending until D2.
- **Not evidence for M4-H.** These results are qualification and instrumentation evidence only, never M4-H or
  treatment-effect evidence. Q7's sealed tasks and the held-out corpus are not used.

## Profiles

Chosen by the lead developer on 2026-10-09:
- lower bound: `opencode/deepseek-v4-flash-free`, with its stable paid twin `opencode/deepseek-v4-flash`;
- backup: `opencode/minimax-m2.5-free`;
- middle profile: `openai/gpt-6-luna`;
- Laguna: recorded as a note only.

**On 2026-10-10 none of the chosen free models is offered by OpenCode 2.0.18.**
- The models.dev catalog that OpenCode serves marks `deepseek-v4-flash-free`, `minimax-m2.5-free` and
  `laguna-s-2.1-free` as `deprecated`.
- The served catalog does not list them; 2.0.22 behaves the same.
- The preregistration therefore pins the paid twin, **`opencode/deepseek-v4-flash` at high effort** ($0.14 / $0.28 per
  million input / output tokens, $0.028 cached). The operator approved paying for it within the lane's budget.
- **Why high effort:** the floor is a hard prerequisite, and flash-class models follow multi-step tool protocols
  poorly at low effort. At high effort it is still a flash-class model.
- **The fallback (the "next-cheaper" profile)** is `opencode/gpt-5-nano` ($0.05 / $0.40, released 2025-08): the
  cheapest paid model the pinned harness offers with a stable identity. `minimax-m2.5`'s paid twin costs more than the
  primary ($0.30 / $1.20), so it is not the fallback.

| Profile | Class | Offered by 2.0.18 | Effort pinned | Credential variable | State |
|---|---|---|---|---|---|
| `lb-deepseek-v4-flash-free` | lower-bound | no (deprecated) | – | none | `unavailable` |
| `lb-deepseek-v4-flash` (pinned) | lower-bound | yes (low, high, max) | high | `OPENCODE_API_KEY` | `unqualified` |
| `lb-minimax-m2.5-free` | lower-bound | no (deprecated) | – | none | `unavailable` |
| `lb-gpt-5-nano` (fallback) | lower-bound | yes (minimal, low, medium, high) | at its run | `OPENCODE_API_KEY` | `unqualified` |
| `mid-gpt-6-luna` | mid | yes (none to max) | medium | `OPENAI_API_KEY` | `unqualified` |
| `note-laguna-s-2.1-free` | lower-bound (note) | no (deprecated) | – | none | `unavailable` |

**The frozen arm pins all of this** (adoption record §9): the model and effort, the profile record's id, its
effective profile and its state at preregistration, and the harness.
- **Harness pin:** OpenCode 2.0.18, with each host platform's binary hash: `win32-x64` `78f454c0…`, `linux-x64`
  `67d82756…`.
- **Wrong binary:** a different binary is refused before an attempt is counted.
- **Wrong version:** a server that reports another version makes the run invalid (`HARNESS_MISMATCH`).

## The fixture

**Python-Markdown 3.11.0** (`upstream.yaml`: commit `0ffbf00c`, tree `a4ef60af`, BSD-3-Clause, 480 files, 2.5 MB). It
was chosen because it is:

- **independent and public:** nothing of AEW's or of any private project. A provider that retains prompts sees only
  this public code and the seeded files.
- **permissively licensed** (BSD-3-Clause), so the seeded copy can be built and shared freely.
- **the size and shape §13.4 asks for:** several hundred files, with more than one plausible search root for every
  question (`markdown/extensions/`, `docs/extensions/`, `tests/test_syntax/extensions/`, the legacy `tests/extensions/`
  data), and a test helper that lives in the package (`markdown/test_tools.py`).
- **runnable anywhere AEW runs:** standard library only (Python 3.11+), tested with `python -m unittest`.

**The base is fetched, never committed.** `qualify.py fetch` clones the tag, refuses any other commit or tree, and
exports the tracked files.

**The seeded files** (`fixture/overlay/`, 14 files) are added beside the base and never replace an upstream file:
- a link-policy extension three directories deep (`markdown/extensions/linkpolicy/`: the extension, its rules, its
  option table);
- its documentation;
- its tests, which reach the code only through a support module;
- a same-named decoy nearer the root (`tools/linkpolicy/`);
- an unrelated failing test (`test_wikilinks_spaces.py`);
- a stale TODO naming the wrong fix;
- an in-tree `Markdown.egg-info`, which is what a legacy editable install leaves. Without it the upstream suite cannot
  resolve its extensions' entry points and 365 of its tests error. With it, the only failure is the seeded one
  (`oracle-validation.json` and the dry run below).

## The cases

| Case | Family | The task (symptom, not file) | Seeds behaviours |
|---|---|---|---|
| `LBQ-1` | navigation | mixed-case and whitespace-prefixed `javascript:` links get through; fix and add a regression test | 1, 2, 3, 6, 7, 8 |
| `LBQ-2` | cross-file | add a `rel_external` option: option table, validation, processor, documentation, tests | 3, 4, 7 (+1, 2, 8) |
| `LBQ-3` | long horizon | four criteria for `report()` and strict mode; one needs `Markdown.reset()`/`registerExtension`, one is documentation | 5, 6, 8 (+1, 2, 7) |

**Oracles.** Each case's hidden oracle lives in the private evaluation root (`cases/<id>/oracle/checks.py`), with a
reference solution beside it. The case manifest commits to the oracle's content hash.

**Oracle validation.** Every oracle was validated against the real fixture before freezing (`oracle-validation.json`):
- on the seeded start, exactly the case's criteria fail;
- on the reference solution, every check passes.

## Where it runs: the arm host holds no oracle

The model runs happen on the **Rocky 8 VM**, contained, and the VM holds no oracle and no private material while any
model runs.

**Containment.** Each raw run's whole OpenCode process tree runs in bubblewrap:
- **Writable:** only its work tree and its harness state.
- **Hidden:** every other run, the ledger, everything beside the lane's run state, every home-directory entry the
  run does not need, and the checkout's `eval/` (this lane's manifests, rubric, behaviour paths and overlay) wherever
  it lives. Nothing from the import path is kept: the agent's shell needs only the standard library. A hidden
  directory appears as an empty tmpfs.
- **Verified before OpenCode starts:** AEW's launch self-test, and a confidentiality probe (every hidden path is empty
  from inside, and every file that describes the cases fails to open). A run whose layout fails either check is
  `CONTAINMENT_FAILED`.

**The floor's role runs** are contained by AEW itself on Linux.

**Refusals.** `floor`, `ceiling` and `run` refuse while `AEW_EVAL_HIDDEN_ROOT` is set, or while the lane's documented
oracle copy (`<lane>/hidden`) exists.

**Scoring comes after every model run has ended.**
1. The oracles are copied into `<lane>/hidden`.
2. `qualify.py score` refuses while any harness process still runs. It then scores each run's exported, hashed tree in
   a scoring sandbox that masks the hidden root, and records one score per run in `scores.jsonl`. The run records
   themselves are never edited.
3. The copy is deleted.

**Why not Windows.** The Windows host holds the private evaluation root and other private material, and a raw run
there cannot be contained, so the lane does not run models there.

## Procedure and run state

| Step | What it does |
|---|---|
| `check` | the dry run (no provider call) |
| `fetch` | the fixture download (approved) |
| `freeze --by NAME` | fills the case, oracle and rubric hashes, materializes the schedule, writes `prereg.frozen.yaml`; it requires `oracle-validation.json` to cover exactly these hashes |
| `floor` | up to two live-lane trials, one at a time, cost-capped |
| `ceiling` | the six raw cells (3 cases × 2) in schedule order, scoring deferred; each attempt is registered in the ledger before it runs, and retried only under the frozen policy |
| `score` | after the oracles arrive: the retention purge, the deferred scores, the tree-observable behaviours, the summary |
| `purge` | the retention step on its own |

`qualify.py run --by NAME` runs everything up to the end of `ceiling` (every step that runs a model).

**A provider failure is a lane error, never a floor trial.** What is detected is narrow: the implementer's turn ended
on a named provider error (a `provider.*` type) before any model output. Every token count is known and zero, and
AEW's record shows no bridge request, no evidence, no tool called and an unchanged workspace. Such a trial measured
the provider, not the model. It is recorded with verdict `lane_error` and a reason: `PROVIDER_AUTH_FAILED` when the
provider rejected the key (`provider.auth`, or an HTTP 401/403 within the provider error), else `NO_MODEL_STEP`.
Anything else counts as a trial, including a provider failure that did not end the turn (a rate limit retried until
the deadline, for example). A lane error does not count toward the floor's two trials. The floor stops at once,
exiting non-zero with what the provider said and what to do (for a rejected key: check `OPENCODE_API_KEY`, rerun).
The ceiling stops the same way on its first `NO_MODEL_STEP` attempt. That attempt stays in the ledger as the
preregistration defines it (an `invalid_measurement`, retried under the frozen policy when the ceiling is rerun), and
the message says how many attempts the cell has left. The basis for both early stops is the frozen record itself: it
lists `NO_MODEL_STEP` under `validity_rules.infrastructure_invalid`, so such a run is not a measurement of the model,
and a stop that resumes on the same schedule leaves the preregistered trials, cells and retry policy as they are. The lane reads this from the
trial's run records, not from the live test's exit code: the live test passes when its implementer crashes, because
the model's outcome is recorded there and only AEW's side is asserted. A floor trial recorded `failed` by an earlier
version of the lane (it carries no `judged_by` stamp) whose stored results show such a failure is read as a lane
error on the next run, so the same
`--out` directory runs the floor again once the key is fixed.

**Run state** goes to `--out`, outside every repository: the ledger, every run's scratch directory (**with its kept
session database**), and the floor's records. The lane's reader may extract only the preregistered fields. Retention
is enforced, not only recorded: a database past its 180 days is refused, then purged, and the purge is recorded.

## Cost (USD), counted against one budget

| Part | Expected | Bound |
|---|---|---|
| Floor: 1–2 live-lane trials (implementer, reviewer, verifier; ≤ 40 steps each) | ≈ 0.1–0.35 per trial | `floor_cap_usd` 1.00, enforced within one 10 s poll |
| Ceiling: 6 raw runs of `deepseek-v4-flash#high`, ≤ 80 steps each, plus retries | ≈ 0.10–0.35 per run | `cap_usd` 0.75 per run, enforced within one 15 s poll |
| **The lane** | **≈ 1–2.5** | **`budget_usd` 5.00** |

**How the bound holds.**
- Every attempt is charged its reported cost, or its cap when the cost is unknown or the run was lost.
- An attempt starts only if `spent + its cap + 0.05 ≤ 5.00`. So the total stays within $5.00 provided each enforcement
  poll overshoots by under $0.05; at about $0.007 per step, a poll covers a few steps.
- The middle profile's floor (`gpt-6-luna#medium`, `OPENAI_API_KEY`) is a separate opt-in, ≈ $0.6 at most.

## Operator steps (the Rocky 8 VM)

See the pull request's description for the exact commands. In short:
1. clone this branch to a fresh lane directory on the VM, and run `vm/setup.sh`;
2. set `AEW_OPENCODE_BIN` to the pinned binary, and `OPENCODE_API_KEY` in that shell (the operator provisions it;
   the agent never sees it);
3. run `qualify.py --out <lane>/out run --by <name>`, then unset the key;
4. copy the oracles to `<lane>/hidden`, run `qualify.py --out <lane>/out score`, and delete the copy;
5. bring back `prereg.frozen.yaml` and the run summaries for this pull request.

## Files

| File | What it is |
|---|---|
| `prereg.yaml` | the preregistration (`aew/eval-prereg/v1`), unfrozen; it holds the structured behaviour definitions |
| `oracle-validation.json` | the oracles validated against the real fixture (seed fails as designed, reference passes) |
| `profiles.yaml` | the profile records (`aew/eval-profile/v1`) |
| `rubric.md` | the floor, the ceiling (the eight behaviours, their metrics and thresholds), correctness, the verdict |
| `behaviours.yaml` | the paths that the tree-observable behaviours and the scope use |
| `upstream.yaml` | the pinned upstream fixture |
| `fixture/LBQ-*.yaml`, `fixture/overlay/` | the case manifests (`aew/eval-case/v1`) and the seeded files |
| `qualify.py` | the driver: check, fetch, freeze, floor, ceiling, run, score, purge |
| `vm/setup.sh` | prepares the VM lane directory: an offline venv over this checkout, with nothing downloaded |
