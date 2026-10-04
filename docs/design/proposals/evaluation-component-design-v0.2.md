# T2 — The evaluation component (F19): frozen shared-instrument design (v0.2)

- **Status:** **Design frozen — proposed for operator adoption**, 2026-10-04. This v0.2 keeps the review's bounded component shape, resolves the three designer questions, and adds the minimum controls required for preregistration integrity, hidden-oracle custody, crash-complete run accounting, blinding, and immutable analysis.
- **Basis:** the F19 decision (`plan-assurance-and-classification-decisions-2026-10-01.md` §3.6: one fixture format, runner, run-record schema, hidden-evaluator mechanism, model and profile configuration, metrics collector; experiments separately preregistered; one run is one run); the M3 dogfood instrument (`eval/m3/dogfood/`: `dogfood.py`, `headless.py`, `hidden.py`, `rubric.md`, `results.jsonl` with `aew/dogfood-run/v1`); plan assurance v0.4 §28–§30 (arms A–F, required task families, metrics); F17 §8 (corpus, arms, protocol, metrics; held-out rule); the skills evaluation guide §1–§3 (plan before running, A/B contract, selection vs procedure); the register (F19 "hidden material lives in `aew-private/eval/`; execution profiles and budget pinned at preregistration; Q7's scratch rule applies"); the designer's Q7 classification (containment research §8).
- **Constraint respected:** `aew-private` was not read (handoff §7). Its layout is cited from the register and the memory note's description ("q7, dogfood-cases, uat, eval (hidden corpora)"); where this plan assumes a path under it, it says so.

## 1. What exists, and what F19 adds

`eval/m3/dogfood/dogfood.py` (905 lines) already does most of what one experiment needs: builds a scratch repository from a fixture overlay, runs AEW mode (a headless Lead through the production adapter) or raw mode, scores with hidden tests that never enter the repository, collects cost, tokens, steps, invocations, runs, interventions, scope and safety, and appends one `aew/dogfood-run/v1` record per paid run whatever the outcome. The record's shape (from `results.jsonl`): `schema, task, mode, model, routing, title, started_at, ended_at, wall_s, workdir, agent_shell, cap_usd, limits{…}, revision, units{…}, invocations{…}, runs[…], reviews[…], verifications[…], lead{…}, lead_session{…}, hidden{task, checks[], passed, project_tests}, integrated_commit, changed_paths, out_of_scope, interventions, stopped_runs, safety{aew_credentials, checkout_untouched, provider_key_checked, provider_key_files}, totals{…}`.

What is written for one experiment and must become shared: the fixture format (`fixture/base` plus `overlays/<task>` plus `seeded/`), the hidden-test module (`hidden.py`, Python functions keyed by task), the rubric (prose, fixed by date), the arms (`--mode aew|raw`), the model configuration (`--model provider/model#effort`, `--routing`), the record, and the collector (`totals`). F19 makes each of these a component that four experiments (Q7, F14 phases, F17, Class 0 sampling) use without one run becoming four samples.

## 1.1 Frozen evaluation principles

F19 is a **measurement instrument**, not project/workflow authority.

1. Evaluation code and outputs never become AEW workflow truth merely because they are produced by AEW.
2. A paid/model run is counted once. The same immutable run may support several preregistered metrics or later secondary analysis, but it is never duplicated into multiple independent samples.
3. Every attempted paid/model run is durably registered **before** the first model/provider action so runner crashes cannot erase inconvenient failures.
4. Run observations are immutable after finalization. Re-scoring/re-analysis creates a new analysis artifact; it never edits the original run record.
5. Hidden oracles, reference answers and held-out cases are never mounted into a model-controlled process, agent environment, context pack, scratch repository or harness home.
6. Objective hidden checks dominate where available. Rubric/model adjudication is blinded to arm identity where feasible and remains explicitly attributable.
7. A causal AEW-vs-raw comparison changes one factor: AEW. Cross-harness comparisons are separate experiments/factors, not the raw control.
8. Preregistration freezes the question, cases, arm definitions, assignment/order, profiles, budget, scoring, exclusion/invalid-run rules, stopping rule and primary measure before outcomes are visible.

## 2. Package layout

```text
eval/
  aew_eval/                      the shared instrument (a package, importable from eval/ and installable with [eval])
    __init__.py
    schema/
      eval-run.schema.json       aew/eval-run/v1 (§3)
      preregistration.schema.json aew/eval-prereg/v1 (§4)
      case.schema.json           aew/eval-case/v1: a fixture's manifest
    fixture.py                   build a scratch repository from a case (base + overlay + seed), record its hashes
    arms.py                      Arm = how a case is run: aew (headless Lead), raw (harness alone), scripted (no model)
    runner.py                    one run: build, run the arm, collect, score, append the record; nothing else
    hidden.py                    the hidden-evaluator channel (§5): load oracles from outside the repository, score
    collect.py                   AEW-side facts for a run: the M3 `collect_aew` generalized (units, invocations, runs,
                                 evidence, refusals, transitions from the transition log, cost from OpenCode)
    metrics.py                   per-experiment metric functions over records; one record can feed several
    prereg.py                    freeze a preregistration: hash the plan, the cases, the oracles, the profiles
    report.py                    tables from records, by experiment id, never re-scoring silently
  experiments/
    m3-dogfood/                  the M3 instrument, kept as it was (its records stay aew/dogfood-run/v1)
    m4h-dogfood/                 M4-H: prereg.yaml, cases/, rubric.md (first consumer)
    f17-shallow-finding/         F17 §8: cases R1-*, SPT-*, Coverage; arms A–F
    f14-plan-assurance/          v0.4 §30 task families
    class0-sample/               the Class 0 audit sample
tools/perf/                      unchanged (ADR-0011's instrument is a different thing: no model, no oracle)
```

The shared instrument lives in this repository under `eval/aew_eval/`; hidden material (oracles, held-out cases, reference solutions) lives in the private repository under `aew-private/eval/`. The public tree holds case manifests and cryptographic commitments to hidden material so a result can bind to the exact oracle version without placing the oracle in the working repository.

The public instrument must run without access to hidden material for schema/unit tests. Access to `aew-private/eval/` is a runner/evaluator capability, not an import-time dependency.

## 3. `aew/eval-run/v1`

Each paid/model attempt is first appended to an experiment-local **attempt ledger** before any provider action, then finalized with exactly one immutable `aew/eval-run/v1` result. A process crash may leave an attempt without a result; that is visible as `RUNNER_LOST`/unfinished and cannot disappear from the sample accounting.

Backward compatibility with `aew/dogfood-run/v1` is required: every M3 field keeps its meaning under the new envelope, and a deterministic adapter can map the historical records without rewriting them.

```yaml
schema: aew/eval-run/v1
experiment: m4h-dogfood            # the preregistration this run belongs to (exactly one)
preregistration_sha256: …          # the frozen plan (§4) this run was made under
run_id: m4h-dogfood/T3-aew-20261012T1012Z
case: {id: T3, sha256: …, hidden_sha256: …}     # the fixture manifest and the hidden oracle it will be scored by
arm: {id: aew, kind: aew|raw|scripted, config_sha256: …}
profile:                            # pinned at preregistration; recorded as requested and as observed
  requested: {lead: openai/gpt-6-sol#medium, implementer: …, reviewer: …, verifier: …}
  observed:  [{role, provider, model, effort, runs}]     # from the adapter's `effective`
  mismatch: false
aew: {commit: dcd43f1…, spec_set: aew-frozen-2026-09-25, schema_control: aew/control/v2}
harness:
  name: opencode
  version: 2.0.18
  artifact_sha256: …
  capability_fixture_sha256: …
  containment: {filesystem, process_ownership, network}
environment: {os, kernel, python, host_class: windows-reference|rocky8-vm|ci}
assignment: {cell, order_index, randomization_seed}
validity: {status: valid|invalid_measurement|runner_lost|environment_blocked, reason_code: null}
started_at, ended_at, wall_s
limits: {…as M3…}
outcome:
  hidden: {passed, checks: [{id, passed, detail}], project_tests}
  reached_done, integrated_commit, changed_paths, out_of_scope
  interventions: [{kind: nudge|manual|scripted, at, note}]
  safety: {aew_credentials: [], provider_key_files: [], checkout_untouched}
  scoring: {scorer_version, oracle_sha256, rubric_sha256?, automated_checks: […], adjudication_ref?}
aew_facts:                          # from collect.py, the control state and the transition log
  revision_start, revision_end, units{…}, invocations{…}, runs[…], evidence[…], refusals[…], transitions: n
cost:
  provider_reported_usd: …
  tokens: {input, output, cached_input, reasoning, …}
  pricing_snapshot_sha256: …       # derived-dollar calculations bind to a frozen price table
  derived_usd: …
notes: free text, never scored
```

Rules: `experiment` is one preregistration id. A run can inform many metrics but remains one sample. Raw observations and preregistered scorer outputs are immutable once finalized; later metric computation writes a separate `aew/eval-analysis/v1` artifact keyed by `{preregistration_sha256, run_ids[], metric_versions[]}`. It never edits `aew/eval-run/v1`. `observed` versus `requested` is retained because effective model/profile mismatch is itself a validity fact.

## 4. The preregistration record, `aew/eval-prereg/v1`

Frozen before the first paid run, hashed, and referenced by every record:

```yaml
schema: aew/eval-prereg/v1
experiment: m4h-dogfood
question: one sentence, falsifiable
arms: [{id, kind, description, config}]            # what differs between arms, and nothing else
cases: [{id, family, sha256, hidden_sha256, control_of: <case id> | null}]   # controls paired with cases (F17 §8.1)
profiles: {…per role, pinned; the budget cap}       # decisions §3.4: frozen with the evaluation
runs_per_cell: 5                                     # directional if that is all the experiment claims
assignment:
  method: randomized_blocked|counterbalanced|fixed
  seed: …
  order: […]                                           # materialized before the first run
primary_measure: …                                     # one; secondary measures listed
thresholds: {…stated before results}
metrics: [function names in metrics.py, with their versions]
validity_rules:
  infrastructure_invalid: […]
  counted_failures: […]
  retry_policy: …
  missing_result_policy: …
stopping_rule: …                                       # no peeking-driven extension/early stop
scoring:
  hidden_channel: aew-private/eval/<experiment>/
  who_scores: automated|model|operator|mixed
  blinding: arm_hidden|not_possible
  adjudication_policy: …
held_out: [case ids never used to tune]
exposure_policy: "a held-out case that informs tuning/debugging leaves the held-out set for future confirmatory runs"
amendment_policy: "changes after outcomes are visible create a new experiment id"
frozen_at, frozen_by, canonical_sha256
```

`prereg.py freeze` canonicalizes the record (schema-defined ordering/encoding), computes the hashes, materializes the assignment/order schedule, and refuses to run a case whose fixture/oracle/profile/config hash differs from the frozen record. Any material change after outcomes are visible gets a new experiment id/preregistration hash. `report.py` groups by preregistration and shows amendments/secondary analyses explicitly.

## 5. The hidden-evaluator channel

The M3 rule stands: hidden tests never enter a repository a model works in. The channel generalizes `hidden.py`:

- an oracle is a directory in the private repository: `cases/<id>/oracle/` with `checks.py` (functions over an exported tree), optional `reference/` and a `manifest.yaml` with the case's expected family answers (F14's "expected" lines, F17's rubric findings);
- `hidden.py` loads it by path from an evaluator-only environment variable (`AEW_EVAL_HIDDEN_ROOT`). The hidden root is never inherited by model-controlled processes, never mounted into their containment layout, and no hidden-oracle file descriptor is kept open across agent launch. Wherever practical, hidden scoring starts **after the model-controlled process tree has terminated**. It exports the run result to an evaluator-owned temporary directory outside the scratch repository and scores there;
- the record stores `hidden_sha256` (the oracle directory's content hash) so a result can be tied to the oracle version even though the oracle is not in the public tree;
- on an air-gapped host the private repository is part of the deployment bundle (T10), and the channel is the same path.

What stays prose: rubrics and adjudication procedures. A rubric is hashed into the preregistration like a case.

Held-out status is an **exposure property**, not just a folder name. If a hidden case, answer or oracle detail is revealed to a developer/model and then used to change AEW, that case is marked exposed and is not reused as confirmatory held-out evidence without being replaced. The private corpus keeps that exposure history.

If an evaluator model is used, its provider/model/effort, effective observed configuration, prompt/rubric hash and output are recorded as scorer provenance. The evaluator sees an arm-neutral exported artifact wherever feasible, not an `AEW`/`raw` label.

## 6. The incident corpus, with sources

Every case family already named in the repository, so F19 starts from recorded evidence rather than invented tasks:

| Family | Cases | Source | Oracle kind |
|---|---|---|---|
| M3 dogfood tasks | T1–T6, T1C0, the guide arms | `eval/m3/dogfood/` (fixture and `hidden.py`) | hidden tests on `ledger` |
| Acceptance-input mutation (the one harmful outcome) | T4 replay; diagnosis contrast pair; legitimate data correction | plan assurance v0.4 §30 "Required task families"; `m3-dogfood-report.md` T4 | expected-behaviour oracle (preserve data unless asked) |
| Oracle weakening and evaluator integrity | oracle weakening; test-selection bypass; environmental gaming; vacuous red; unexpected green; preservation work | v0.4 §30 | classification oracle (`INVALID_MEASUREMENT`, `ENVIRONMENT_BLOCKED`, …) |
| Shallow-finding termination | R1-given, R1-discover, R1-split, R1-control, R1-synthetic, SPT-headless, SPT-item9, Coverage | F17 §8.1 (sources: T-0001/T-0003 at the freeze tag, commit `812b492`, the SPT UAT commit) | rubric findings; controls measure false consequences |
| Class 0 eligibility | sampled Class 0 Tickets from dogfood runs | Class 0 amendment §2 ("a sample … receives an independent audit") | audit verdict on the semantic assertions |
| Resume after harness loss | T6 and its variants | `rubric.md`; AT-15 | hidden tests plus `resume` completeness |
| Seeded review defect | T5 and new seeds | `fixture/seeded/T5` | caught before integration, by whom |
| Containment (scratch rule) | every case runs under the Q7 classification | containment research §8 | the run label and the safety block |

New incidents (the drafts' "each new incident becomes a held-out case") are added to the private repository with a public manifest entry; the public tree never learns the answer.

## 7. The external comparator: a verification item, not a choice

Two different things are called "comparator" in the documents and should be named apart:

1. **The raw arm**: the same harness and model without AEW (`--mode raw` today). It is the control for "does AEW help", and it needs no external component.
2. **An external evaluator model**: a model that scores or adjudicates (F17's "evaluator", plan assurance's "protected evaluator", the drafts' "challenger"). The gateway decides what exists: which models, with which options (reasoning effort, structured output) actually reach the model through the gateway (airgap research §5: "a model name is not evidence that the gateway forwards every option").

This design therefore does **not** choose a comparator/evaluator model. Before an experiment that uses one is frozen, `prereg.py` verifies the required gateway features and records the observed effective configuration. An experiment whose evaluator features are not verified cannot freeze.

A model evaluator is never treated as independent proof merely because it agrees with another model. Objective hidden checks remain primary where available. For rubric-scored facts, the frozen adjudication policy determines how disagreements are handled; model scoring is attributable evidence for adjudication, not self-authenticating truth.

## 8. Sequencing

1. `schema/`, `prereg.py` and the append-only attempt ledger first: M4-H must be unable to lose or post-hoc redefine a paid run.
2. `runner.py` and `fixture.py` by generalizing `dogfood.py`, keeping the M3 experiment runnable and historical records unchanged.
3. `hidden.py` with the private-repository boundary, exposure tracking and the first held-out case.
4. `metrics.py` / immutable `analysis.py` per experiment; `report.py` last.

The first consumer is M4-H's preregistered dogfood (M4 plan §5); F17 phase 1 (corpus and baseline, "nothing is implemented first") can use the same runner with `arm: aew` at the current commit and `arm: raw`.

## 9. Completion criteria for the component

- `aew/eval-run/v1` can represent every historical M3 run through a deterministic compatibility mapping without renaming/changing the meaning of M3 fields.
- Before the first provider/model action, the attempt ledger durably records `{experiment, preregistration hash, run id, case, arm, assignment order, requested profile}`. Killing the runner after model launch but before finalization leaves a visible unfinished attempt, not a vanished sample.
- A preregistration freezes/canonical-hashes fixtures, hidden oracle commitments, profiles, arm configs, assignment schedule, validity/retry/stopping rules and scoring. A changed material input refuses to run under the old preregistration.
- One paid/model attempt is counted once. Retries occur only under the frozen invalid-infrastructure policy and remain linked to the original attempt.
- Run records are immutable after finalization. Re-analysis produces a separately hashed `aew/eval-analysis/v1` artifact naming exact input run ids and metric versions.
- No hidden oracle path/content/file descriptor is present in a scratch repo, agent environment, harness home, context pack or model-controlled mount/process. Hidden scoring is arm-blind where feasible and preferably starts after agent termination.
- Held-out case exposure is tracked; an exposed case cannot silently remain confirmatory held-out evidence.
- Objective hidden checks and model/operator adjudication are separately identified; every adjudicated score records scorer provenance and disagreement resolution.
- Effective harness/model/profile/capability-fixture identity is recorded; a material requested/observed mismatch triggers the frozen validity rule.
- Any evaluator-model feature used by an experiment is gateway-verified before preregistration freezes.

## Frozen designer decisions

1. **Component placement:** the shared F19 instrument lives in this repository under `eval/aew_eval/`; hidden corpora/oracles/reference material live under `aew-private/eval/`. Keeping evaluator mechanics public/testable while hidden answers stay private is the cleanest split.
2. **Raw control:** for an AEW-effect experiment, raw uses the **same harness, same model/profile, same case and same environmental envelope** as the AEW arm, changing only the AEW treatment. AEW-on-OpenCode versus raw-Codex is a cross-harness experiment and may be useful, but it is not the causal raw control.
3. **Contested rubric facts:** automated/objective checks win where they exist. For subjective/rubric-scored facts, use a preregistered **blinded evaluator-model assessment plus operator adjudication on disagreement/material ambiguity**. Record both outputs and the final adjudication. The operator may adjudicate directly when the experiment's preregistration says no adequate model evaluator exists.
4. **Run ordering:** paired/cell runs are randomized or counterbalanced from a preregistered seed/schedule to reduce time/provider drift; the actual order is part of the run record.
5. **Crash accounting:** every paid/model attempt is registered before launch; runner loss is visible and cannot be silently rerun away.
6. **Immutability:** raw observations and scorer outputs are immutable. Later metrics/reports are derived artifacts, never edits to run records.
7. **Held-out discipline:** once a hidden case materially informs implementation/tuning, it leaves the confirmatory held-out pool.
8. **F19 remains evaluation-only:** none of its records, scores or evaluator judgments mutate project control state or satisfy workflow gates by themselves.

No further designer-level question blocks M4-H preregistration. The first implementation should stop after the schemas/preregistration/attempt-ledger slice proves these invariants against the M3 corpus before generalizing the runner.
