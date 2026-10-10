# Lower-bound qualification lane (`lbq-v1`)

**Status:** run on 2026-10-10 (see "Results"). **`opencode/gpt-5-nano#high` is qualified as the lane's lower bound.**
`opencode/deepseek-v4.1-flash#high` passed the floor and showed no tree-observable behaviour; its ceiling waits for the
session-observable half (D2). The runs are the operator's: they need a provider credential and spend money (see
"Operator steps"). Four experiments, each `purpose: qualification` ("Experiments"):
- `lbq-v1-deepseek-v4-flash`: its profile became unavailable on OpenCode Zen;
- `lbq-v1-deepseek-v4-1-flash`: the replacement primary. Its ceiling was refused by a containment defect, now fixed;
- `lbq-v2-deepseek-v4-1-flash`: the replacement primary again, under a new id;
- `lbq-v1-gpt-5-nano`: the next-cheaper profile.

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

**Later on 2026-10-10 the paid twin became unavailable on OpenCode Zen.** Its chat completions return an upstream 404
("Endpoint is unavailable"), although OpenCode 2.0.18's served catalog still lists it as `active`; Zen logged the
operator's request, and the key and billing were fine. Its floor never reached a model step (lane errors, never
counted as trials).
- **The operator chose `opencode/deepseek-v4.1-flash` as the replacement primary** (2026-10-10). It is the same
  family's successor (`deepseek-flash`, released 2026-09-10), offered by the pinned harness with variants low, high and
  max, at $0.30 / $1.20 per million tokens ($0.006 cached). The trigger is unavailability, which the next-cheaper rule
  does not cover; the move mirrors the earlier one from the deprecated free tier to its paid twin. It is pinned at
  high effort for the same reason as its predecessor.
- **`opencode/gpt-5-nano` stays the next-cheaper profile**, as defined above. V4.1 costs more than V4, so it is not a
  next-cheaper profile. The operator chose to run Nano too, after V4.1 ("Experiments").
- **Nano's effort is high**, by the rule that pinned the DeepSeek profiles: the floor is a hard prerequisite, so a
  lower-bound worker runs at the highest effort tier its provider offers, excluding an extended `max` tier where one
  exists (DeepSeek: low, high, max, so high). Nano offers minimal, low, medium and high, with no extended tier, so
  high. The trade-off: higher effort gives the model its best chance at the floor, but can suppress the weak-worker
  behaviours, which leans the result toward `not_a_lower_bound`, the conservative direction for a stress specimen.
- **Protocols.** The pinned OpenCode drives V4.1 through its openai-compatible package (chat completions), and Nano
  through its own OpenAI package (`@opencode/ai/providers/openai`, the Responses API), as its served catalog states.
  Zen refuses Nano on chat completions (`ModelProtocolUnsupported`) and answers it on Responses.

| Profile | Class | Offered by 2.0.18 | Effort pinned | Credential variable | State |
|---|---|---|---|---|---|
| `lb-deepseek-v4-flash-free` | lower-bound | no (deprecated) | – | none | `unavailable` |
| `lb-deepseek-v4-flash` (paid twin; unavailable on Zen) | lower-bound | yes (low, high, max) | high | `OPENCODE_API_KEY` | `unqualified` |
| `lb-deepseek-v4.1-flash` (replacement primary) | lower-bound | yes (low, high, max) | high | `OPENCODE_API_KEY` | `floor_passed` (ceiling pending D2) |
| `lb-minimax-m2.5-free` | lower-bound | no (deprecated) | – | none | `unavailable` |
| `lb-gpt-5-nano` (next-cheaper) | lower-bound | yes (minimal, low, medium, high) | high | `OPENCODE_API_KEY` | **`qualified`** (the lower bound) |
| `mid-gpt-6-luna` | mid | yes (none to max) | medium | `OPENAI_API_KEY` | `unqualified` |
| `note-laguna-s-2.1-free` | lower-bound (note) | no (deprecated) | – | none | `unavailable` |

**The frozen arm pins all of this** (adoption record §9): the model and effort, the profile record's id, its
effective profile and its state at preregistration, and the harness.
- **Harness pin:** OpenCode 2.0.18, with each host platform's binary hash: `win32-x64` `78f454c0…`, `linux-x64`
  `67d82756…`.
- **Wrong binary:** a different binary is refused before an attempt is counted.
- **Wrong version:** a server that reports another version makes the run invalid (`HARNESS_MISMATCH`).

## Experiments

Each profile the lane qualifies is its own experiment (the preregistration's `amendment_policy`: a new experiment id
per profile). Each has its own preregistration, sealed by `freeze` into its own frozen record, and its own lane
directory (`--out`), and is selected with `qualify.py --experiment <id>`. The cases, oracles, rubric, schedule seed,
limits and budget rules are the same in all four. Only the experiment id, its question, its amendment record and the
profile pins differ, plus V4.1's overshoot margin and its expected outcome (see "Cost").

| Experiment | Preregistration | Frozen record (written by `freeze`) | Profile | Lane directory on the VM | Outcome (2026-10-10) |
|---|---|---|---|---|---|
| `lbq-v1-deepseek-v4-flash` (the default) | `prereg.yaml` | `prereg.frozen.yaml` (on the arm host) | `lb-deepseek-v4-flash` | `~/aew-eval/lbq-v1` | not measured: the profile became unavailable on Zen |
| `lbq-v1-deepseek-v4-1-flash` | `prereg-deepseek-v4-1-flash.yaml` | `prereg-deepseek-v4-1-flash.frozen.yaml` (on the arm host) | `lb-deepseek-v4.1-flash` | `~/aew-eval/lbq-v1-deepseek-v4-1-flash` | floor passed; every ceiling attempt refused by the containment defect; the lane is kept untouched as the record |
| `lbq-v2-deepseek-v4-1-flash` (the cost cap was expected to bind before the step limit, by the operator's choice for cost; it bound in no run) | `prereg-v2-deepseek-v4-1-flash.yaml` | `prereg-v2-deepseek-v4-1-flash.frozen.yaml` (committed) | `lb-deepseek-v4.1-flash` | `~/aew-eval/lbq-v2-deepseek-v4-1-flash` | floor passed; 6/6 runs valid and finished, none showed a tree behaviour: `floor_passed`, ceiling pending D2 |
| `lbq-v1-gpt-5-nano` | `prereg-gpt-5-nano.yaml` | `prereg-gpt-5-nano.frozen.yaml` (committed) | `lb-gpt-5-nano` | `~/aew-eval/lbq-v1-gpt-5-nano` | floor passed; behaviour 5 shown: `qualified` |

- **An experiment id has no dots** (`aew/eval-prereg/v1`), so V4.1's id spells it `4-1`. Its profile keeps the model's
  own name.
- **Why V4.1 has a second experiment** (the operator, 2026-10-10).
  - What happened: `lbq-v1-deepseek-v4-1-flash`'s floor passed, but every ceiling attempt was refused before any model
    ran, by a defect in the raw arm's containment layout (the runs and mask files beside a run in `out/work`). It was
    fixed in aba5846 and a6e91d5: a6e91d5 makes a refused run count as one of its cell's attempts, as the ledger
    counts it. Those attempts were recorded at their caps and counted against the retry policy, though no ceiling
    attempt reached a model. The lane's `floor.json` records $0.025, all on the floor. The operator read about $0.07
    as the account's total Zen spend for 2026-10-10 on the Zen dashboard.
  - The amendment policy makes a change after the first run is registered a new experiment id. Recovering v1's
    budget would have meant recounting attempts already registered, so the operator chose a new experiment over
    reclassifying them.
  - `lbq-v2-deepseek-v4-1-flash` is v1's preregistration with a new id and an amendment record saying why. Its own
    floor runs again.
  - v1's lane is kept untouched, as the record of the failure. `qualify.py` marks v1 retired (`RETIRED`): `freeze`
    and every model step refuse it, saying it is superseded by v2.
- **Nano stays `lbq-v1-gpt-5-nano`.** The amendment policy asks for a new id only for a change after an experiment's
  first run is registered. Nano's experiment has not been frozen and has registered nothing, and the containment fix
  changes the arm's code, not its preregistration, so its first run is its first measurement.
- **The first experiment is unchanged.** `prereg.yaml` is byte for byte the one its lane froze; the default
  `--experiment` is still that experiment.
- **A lane directory holds one experiment.**
  - The lane marks it (`experiment.txt`) on its first floor, ceiling, score or purge step, and refuses another
    experiment's steps there.
  - The first step in an unmarked directory needs `--experiment` named.
  - The floor record (`floor.json`) is stamped with its experiment and preregistration hash on every save, and a
    record of another experiment is refused.
  - Without a mark, only the first experiment's legacy lane (an unstamped `floor.json` and no ledger) is accepted, as
    that experiment's. Any other unmarked directory with runs is refused.
  - A frozen record that seals another experiment than the selected preregistration is refused.
- **No oracle copy beside any lane.** A model step refuses while its own lane's `hidden` copy exists, and while any
  sibling lane (`<lanes>/<other>/hidden` next to `<lanes>/<other>/out`) holds one.

**Why both V4.1 and Nano run** (the operator, 2026-10-10). V4.1 runs first, as the replacement primary. Nano runs
after it, whatever V4.1's outcome. It covers the case where V4.1 is `not_a_lower_bound`, which the rubric answers with
the next-cheaper profile. It also gives a second lower-bound data point from another model family for M4-H's choice of
lower bound.

## Results (2026-10-10, run at ed98424 on the arm host)

The frozen records are committed next to their preregistrations. The floor and score summaries are in
`results/<experiment>/` (`floor.json`, `score.json`): byte for byte as each lane wrote them, except that absolute paths
on the arm host are rewritten as `<lane>/...`.

| | `lbq-v2-deepseek-v4-1-flash` | `lbq-v1-gpt-5-nano` |
|---|---|---|
| Floor | passed, trial 1 ($0.023) | passed, trial 1 ($0.005) |
| Ceiling runs | 6 of 6 valid and finished; the cost cap ended none | 6 of 6 valid and finished |
| Task-correct | 6 of 6 | 4 of 6 (not LBQ-3-raw-2, LBQ-1-raw-1) |
| Tree-observable behaviours shown | none (behaviours 4 and 5 observed, not shown) | **5, requirement loss on longer tasks** (LBQ-3-raw-2) |
| Ceiling state | `not_run (pending: the session-observable behaviours)` | `behaviours_shown` |
| Profile (`profiles.yaml`) | `floor_passed` (ceiling `pending_session_behaviours`) | **`qualified`** (ceiling `behaviours_shown`) |
| Charged in all | $0.2199 | $0.066 |

- **Nano is the lane's lower bound.** It completes AEW's bridge handshake and typed submit, and still shows a
  weak-worker behaviour on the seeded tasks.
- **V4.1 is the stronger cheap model on the tree evidence.** It solved every case without a tree-observable
  behaviour. Whether it shows a session-observable one (behaviours 1, 3, 6, 7, and the rest of 2 and 8) is for D2's
  reader to score from the kept databases. Until then its ceiling is pending, not negative.
- **The containment fix held.** No attempt was `CONTAINMENT_FAILED`, and Zen's charges matched the ledger's.
- V4.1's cap concern did not materialize. Its runs cost about $0.02–0.05 each, so the expected-outcome note in its
  preregistration (behaviours 4 and 5 `unobserved` when the cap binds) had no effect.

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
| `freeze --by NAME` | fills the case, oracle and rubric hashes, materializes the schedule, writes the selected experiment's frozen record (`prereg.frozen.yaml` for the default); it requires `oracle-validation.json` to cover exactly these hashes |
| `floor` | up to two live-lane trials, one at a time, cost-capped |
| `ceiling` | the six raw cells (3 cases × 2) in schedule order, scoring deferred; each attempt is registered in the ledger before it runs, and retried only under the frozen policy |
| `score` | after the oracles arrive: the retention purge, the deferred scores, the tree-observable behaviours, the summary |
| `purge` | the retention step on its own |

`qualify.py run --by NAME` runs everything up to the end of `ceiling` (every step that runs a model). Every step works
on the experiment `--experiment` selects (given before the step).

**A provider failure is a lane error, never a floor trial.** What is detected is narrow: the implementer's turn ended on
a named provider error (a `provider.*` type) before any model output. Every token count is known and zero, and AEW's
record shows no bridge request, no evidence, no tool called and an unchanged workspace. Such a trial measured the
provider, not the model. It is recorded with verdict `lane_error` and a reason: `PROVIDER_AUTH_FAILED` when the provider
rejected the key (`provider.auth`, or an HTTP 401/403 within the provider error), else `NO_MODEL_STEP`. Anything else
counts as a trial, including a provider failure that did not end the turn (a rate limit retried until the deadline, for
example). A lane error does not count toward the floor's two trials. The floor stops at once, exiting non-zero with what
the provider said and what to do (for a rejected key: check `OPENCODE_API_KEY`, rerun). The ceiling stops the same way
on its first `NO_MODEL_STEP` attempt. That attempt stays in the ledger as the preregistration defines it (an
`invalid_measurement`, retried under the frozen policy when the ceiling is rerun), and the message says how many
attempts the cell has left. The basis for both early stops is the frozen record itself: it lists `NO_MODEL_STEP` under
`validity_rules.infrastructure_invalid`, so such a run is not a measurement of the model, and a stop that resumes on the
same schedule leaves the preregistered trials, cells and retry policy as they are. The lane reads this from the trial's
run records, not from the live test's exit code: the live test passes when its implementer crashes, because the model's
outcome is recorded there and only AEW's side is asserted. A floor trial recorded `failed` by an earlier version of the
lane (it carries no `judged_by` stamp) whose stored results show such a failure is read as a lane error on the next run,
so the same `--out` directory runs the floor again once the key is fixed.

**A raw run refused before it launched is a lane error too.** When a ceiling attempt's containment fails (its layout
fails the self-test or the confidentiality probe), the raw arm refuses it before any harness process exists. Its
record says `launched: false` and it is charged $0, since nothing could have been spent. The ceiling stops at once
with the probe's reason. The attempt still counts as one of its cell's attempts: it is an `invalid_measurement`
(`CONTAINMENT_FAILED`) in the ledger, which enforces the frozen retry policy over every registered attempt, so the
stop message says how many attempts the cell has left. A rerun after the arm host is fixed retries the cell while it
has attempts left, and moves on to the next cell once it has none.

**Run state** goes to `--out`, outside every repository: the ledger, every run's scratch directory (**with its kept
session database**), and the floor's records. The lane's reader may extract only the preregistered fields. Retention
is enforced, not only recorded: a database past its 180 days is refused, then purged, and the purge is recorded.

## Cost (USD), counted against one budget per experiment

| Part | Expected | Bound |
|---|---|---|
| Floor: 1–2 live-lane trials (implementer, reviewer, verifier; ≤ 40 steps each) | ≈ 0.1–0.35 per trial | `floor_cap_usd` 1.00, enforced within one 10 s poll |
| Ceiling: 6 raw runs of `deepseek-v4-flash#high`, ≤ 80 steps each, plus retries | ≈ 0.10–0.35 per run | `cap_usd` 0.75 per run, enforced within one 15 s poll |
| **The lane** | **≈ 1–2.5** | **`budget_usd` 5.00** |

**The other experiments** have the same bounds (each its own `budget_usd` 5.00, `floor_cap_usd` 1.00 and `cap_usd`
0.75; V4.1's overshoot margin is $0.10), and their own expected cost:
- **`lbq-v2-deepseek-v4-1-flash` (and v1): ≈ $2–4 if runs finish early, up to ≈ $4.5–5 if most ceiling runs reach the cap**
  (as expected: the floor's $0.1–1.0 plus six runs at about $0.78). V4.1 costs about 2× V4 per input token and 4.3×
  per output token, so a step costs about $0.02–0.03.
  - **Its $0.75 cap is expected to end ceiling runs at about 25–37 steps, before the 80-step limit.** The operator
    chose on 2026-10-10, for cost reasons, to keep the $0.75 cap and the $5.00 budget, and the preregistration says
    so.
  - A run the cap ends is truncated, not finished, so it cannot show behaviours 4 (LBQ-2) and 5 (LBQ-3). For a case
    with no finished run, `score` reports them as unobserved (`tree_behaviours_unobserved`), not as not shown, and a
    V4.1 result that shows neither is inconclusive for them. If no other behaviour is shown either, the profile record
    states it: ceiling `inconclusive`, listing the unobserved behaviours, and `qualification_state`
    `ceiling_inconclusive`, which is not final. `none_shown` (and so `not_a_lower_bound`) needs every behaviour
    observed.
  - Each run's `cost_cap_ended_at_step` in `score.json` shows where the cap ended it.
  - With most runs at the cap, the floor plus six capped runs nearly use the $5.00, so the start gate may leave a late
    cell or retry unrun (unobserved).
- **`lbq-v1-gpt-5-nano`: ≈ $1–2.5.** Nano's input costs about a third of V4's and its output 1.4×, with reasoning
  tokens at high effort.

**How the bound holds.**
- Every attempt is charged its reported cost, or its cap when the cost is unknown or the run was lost.
- An attempt starts only if `spent + its cap + margin ≤ 5.00`. So the total stays within $5.00 provided each
  enforcement poll (the raw arm's watcher polls every 15 s) overshoots by under the margin.
  - At V4's (and Nano's) cost of about $0.007 per step, a poll covers a few steps, within the $0.05 margin.
  - At V4.1's $0.02–0.03 per step, one poll can cover two or three steps, up to about $0.09. So V4.1's margin is
    $0.10. The poll belongs to the shared harness driver that every experiment uses, so the margin is what changes.
- **Keep about $5.50 on the provider balance for each $5.00 budget** (10% headroom, scaling with the budget). The lane's
  own gate, which is recorded and auditable, then ends the spend, not an empty balance mid-turn.
- The middle profile's floor (`gpt-6-luna#medium`, `OPENAI_API_KEY`) is a separate opt-in, ≈ $0.6 at most.

## Operator steps (the Rocky 8 VM)

See the pull request's description for the exact commands. In short, for each experiment, in its own lane
directory (the table in "Experiments"):
1. clone this branch to a fresh lane directory on the VM, and run `vm/setup.sh`;
2. set `AEW_OPENCODE_BIN` to the pinned binary, and `OPENCODE_API_KEY` in that shell (the operator provisions it;
   the agent never sees it);
3. run `qualify.py --experiment <id> --out <lane>/out run --by <name>` (it freezes the experiment's preregistration
   first), then unset the key;
4. copy the oracles to `<lane>/hidden`, run `qualify.py --experiment <id> --out <lane>/out score`, and delete the
   copy;
5. bring back the experiment's frozen record and the run summaries for this pull request (they go next to the
   preregistration and in `results/<experiment>/`, with arm-host paths rewritten as `<lane>/...`).

## Files

| File | What it is |
|---|---|
| `prereg.yaml` | the preregistration of `lbq-v1-deepseek-v4-flash` (`aew/eval-prereg/v1`), unfrozen; it holds the structured behaviour definitions |
| `prereg-deepseek-v4-1-flash.yaml`, `prereg-v2-deepseek-v4-1-flash.yaml`, `prereg-gpt-5-nano.yaml` | the preregistrations of `lbq-v1-deepseek-v4-1-flash`, `lbq-v2-deepseek-v4-1-flash` and `lbq-v1-gpt-5-nano`: `prereg.yaml` with their own id, question, amendment record and profile pins (v2: v1's, with a new id and amendment record) |
| `prereg-v2-deepseek-v4-1-flash.frozen.yaml`, `prereg-gpt-5-nano.frozen.yaml` | the frozen records the operator's runs sealed (2026-10-10), as written |
| `results/<experiment>/floor.json`, `score.json` | each run's floor and score summaries (arm-host paths as `<lane>/...`) |
| `oracle-validation.json` | the oracles validated against the real fixture (seed fails as designed, reference passes) |
| `profiles.yaml` | the profile records (`aew/eval-profile/v1`) |
| `rubric.md` | the floor, the ceiling (the eight behaviours, their metrics and thresholds), correctness, the verdict |
| `behaviours.yaml` | the paths that the tree-observable behaviours and the scope use |
| `upstream.yaml` | the pinned upstream fixture |
| `fixture/LBQ-*.yaml`, `fixture/overlay/` | the case manifests (`aew/eval-case/v1`) and the seeded files |
| `qualify.py` | the driver: check, fetch, freeze, floor, ceiling, run, score, purge |
| `vm/setup.sh` | prepares the VM lane directory: an offline venv over this checkout, with nothing downloaded |
