# T2 — The evaluation component (F19): a plan for the shared instrument

- **Status:** bounded design from the independent architecture review (thread T2 of `HANDOFF.md`; `REVIEW.md` G1, F19), 2026-10-04. Not governing. A plan for code that does not exist: layout, the run-record schema, the preregistration record, the hidden-evaluator channel, the corpus list, and the comparator question. Deeper design waits for the first consumer (M4-H's preregistered dogfood).
- **Basis:** the F19 decision (`plan-assurance-and-classification-decisions-2026-10-01.md` §3.6: one fixture format, runner, run-record schema, hidden-evaluator mechanism, model and profile configuration, metrics collector; experiments separately preregistered; one run is one run); the M3 dogfood instrument (`eval/m3/dogfood/`: `dogfood.py`, `headless.py`, `hidden.py`, `rubric.md`, `results.jsonl` with `aew/dogfood-run/v1`); plan assurance v0.4 §28–§30 (arms A–F, required task families, metrics); F17 §8 (corpus, arms, protocol, metrics; held-out rule); the skills evaluation guide §1–§3 (plan before running, A/B contract, selection vs procedure); the register (F19 "hidden material lives in `aew-private/eval/`; execution profiles and budget pinned at preregistration; Q7's scratch rule applies"); the designer's Q7 classification (containment research §8).
- **Constraint respected:** `aew-private` was not read (handoff §7). Its layout is cited from the register and the memory note's description ("q7, dogfood-cases, uat, eval (hidden corpora)"); where this plan assumes a path under it, it says so.

## 1. What exists, and what F19 adds

`eval/m3/dogfood/dogfood.py` (905 lines) already does most of what one experiment needs: builds a scratch repository from a fixture overlay, runs AEW mode (a headless Lead through the production adapter) or raw mode, scores with hidden tests that never enter the repository, collects cost, tokens, steps, invocations, runs, interventions, scope and safety, and appends one `aew/dogfood-run/v1` record per paid run whatever the outcome. The record's shape (from `results.jsonl`): `schema, task, mode, model, routing, title, started_at, ended_at, wall_s, workdir, agent_shell, cap_usd, limits{…}, revision, units{…}, invocations{…}, runs[…], reviews[…], verifications[…], lead{…}, lead_session{…}, hidden{task, checks[], passed, project_tests}, integrated_commit, changed_paths, out_of_scope, interventions, stopped_runs, safety{aew_credentials, checkout_untouched, provider_key_checked, provider_key_files}, totals{…}`.

What is written for one experiment and must become shared: the fixture format (`fixture/base` plus `overlays/<task>` plus `seeded/`), the hidden-test module (`hidden.py`, Python functions keyed by task), the rubric (prose, fixed by date), the arms (`--mode aew|raw`), the model configuration (`--model provider/model#effort`, `--routing`), the record, and the collector (`totals`). F19 makes each of these a component that four experiments (Q7, F14 phases, F17, Class 0 sampling) use without one run becoming four samples.

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

Hidden material (oracles, held-out cases, reference solutions) lives in the private repository, which the register already decides (`aew-private/eval/`); the public tree holds the case manifests with the **hashes** of their hidden parts, so a run can prove which oracle scored it without the oracle being in the repository.

## 3. `aew/eval-run/v1`

One record per run, appended to `experiments/<id>/results.jsonl` whatever the outcome. Backward compatible with `aew/dogfood-run/v1`: every M3 field keeps its name under the new envelope, so `report.py` can read both.

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
harness: {name: opencode, version: 2.0.18, containment: {filesystem, process_ownership, network}}   # the run label
environment: {os, kernel, python, host_class: windows-reference|rocky8-vm|ci}
started_at, ended_at, wall_s
limits: {…as M3…}
outcome:
  hidden: {passed, checks: [{id, passed, detail}], project_tests}
  reached_done, integrated_commit, changed_paths, out_of_scope
  interventions: [{kind: nudge|manual|scripted, at, note}]
  safety: {aew_credentials: [], provider_key_files: [], checkout_untouched}
  classification: {…experiment-specific, e.g. F17 tag recall / reach, F14 bad-plan escape, Class 0 eligibility}
aew_facts:                          # from collect.py, the control state and the transition log
  revision_start, revision_end, units{…}, invocations{…}, runs[…], evidence[…], refusals[…], transitions: n
cost: {usd_reported, usd_from_tokens, tokens{…}, lead_share}
notes: free text, never scored
```

Rules: `experiment` is one id (the F19 decision: a run informs several metrics but is one run); `classification` is where an experiment's metric functions write, under the experiment's own key, so two experiments never fight over a field; `observed` versus `requested` is kept because the M3 dogfood needed it (`model_check`).

## 4. The preregistration record, `aew/eval-prereg/v1`

Frozen before the first paid run, hashed, and referenced by every record:

```yaml
schema: aew/eval-prereg/v1
experiment: m4h-dogfood
question: one sentence, falsifiable
arms: [{id, kind, description, config}]            # what differs between arms, and nothing else
cases: [{id, family, sha256, hidden_sha256, control_of: <case id> | null}]   # controls paired with cases (F17 §8.1)
profiles: {…per role, pinned; the budget cap}       # decisions §3.4: frozen with the evaluation
runs_per_cell: 5                                     # F17 §8.3: "directional at that size", stated
primary_measure: …                                   # one; secondary measures listed (evaluation guide §1)
thresholds: {…stated before results}
metrics: [function names in metrics.py, with their versions]
scoring: {hidden_channel: aew-private/eval/<experiment>/, who_scores: automated|adjudicated, blinding: …}
held_out: [case ids never used to tune]              # F17 §8.1's rule
amendment_policy: "changes after outcomes are visible create a new experiment id" (evaluation guide §1)
frozen_at, frozen_by, sha256_of_this_file_without_this_field
```

`prereg.py freeze` computes the hashes and refuses to run a case whose fixture or oracle hash differs from the frozen one; `report.py` groups by `experiment` and shows amendments as separate experiments.

## 5. The hidden-evaluator channel

The M3 rule stands: hidden tests never enter a repository a model works in. The channel generalizes `hidden.py`:

- an oracle is a directory in the private repository: `cases/<id>/oracle/` with `checks.py` (functions over an exported tree), optional `reference/` and a `manifest.yaml` with the case's expected family answers (F14's "expected" lines, F17's rubric findings);
- `hidden.py` loads it by path from an environment variable set only in the runner's process (`AEW_EVAL_HIDDEN_ROOT`), never in any agent environment (the custody machinery already guarantees agents get only the curated environment), exports the run's result (the integrated commit, or the working tree for a raw arm) to a temporary directory **outside** the scratch repository, and scores there;
- the record stores `hidden_sha256` (the oracle directory's content hash) so a result can be tied to the oracle version even though the oracle is not in the public tree;
- on an air-gapped host the private repository is part of the deployment bundle (T10), and the channel is the same path.

What stays prose: rubrics and adjudication procedures. A rubric is hashed into the preregistration like a case.

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

This plan therefore does **not** choose a comparator model. It specifies the verification: before any experiment that uses an evaluator model is frozen, `prereg.py` runs one sanitized request per feature the experiment relies on (structured output, reasoning effort, the context size) against the gateway with the pinned model and records the observed response shape in the preregistration (`profiles.evaluator.verified: {…}`). An experiment whose evaluator features are not verified cannot freeze. The M3 adapter's `effective` model check is the same discipline applied to the evaluator.

## 8. Sequencing

1. `schema/` and `prereg.py` first (a week): they are what M4-H's experiment is written against, and they can be validated against M3's `results.jsonl` immediately (backward compatibility is the acceptance test).
2. `runner.py` and `fixture.py` by generalizing `dogfood.py` (its `run()` is already the loop), keeping `experiments/m3-dogfood` runnable and its records unchanged.
3. `hidden.py` with the private-repository layout, and the first held-out case.
4. `metrics.py` per experiment as each is preregistered; `report.py` last.

The first consumer is M4-H's preregistered dogfood (M4 plan §5); F17 phase 1 (corpus and baseline, "nothing is implemented first") can use the same runner with `arm: aew` at the current commit and `arm: raw`.

## 9. Completion criteria for the component

- `aew/eval-run/v1` validates every record in `eval/m3/dogfood/results.jsonl` after an automatic envelope mapping (no field renamed).
- A preregistration freezes, hashes, and refuses a changed fixture or oracle; a changed plan after results produces a new experiment id.
- One run writes exactly one record, with one `experiment`, however many metrics read it.
- No hidden oracle path or content is ever present in a scratch repository, an agent environment or a pack; the custody scan already used by the dogfood (`scan_secrets`) is extended with the oracle root.
- The evaluator-model verification is recorded for any experiment that uses one.

## Questions for the designer

1. Does F19 live in this repository (`eval/aew_eval/`) with hidden material in `aew-private/eval/` (this plan), or entirely beside `aew-private`? (handoff question 4)
2. Is the raw arm always the same harness as the AEW arm (the M3 rule), or may an experiment compare AEW-on-OpenCode with Codex alone once a Codex adapter exists (T9)? The record carries `harness` per run either way.
3. Who adjudicates contested oracle facts for rubric-scored families (F17): the operator, a second model, or both with the disagreement recorded?
