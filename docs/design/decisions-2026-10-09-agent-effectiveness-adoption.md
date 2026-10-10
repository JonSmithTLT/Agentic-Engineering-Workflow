# AEW Agent Effectiveness Research Adoption & Implementation Handoff v0.1

**Date:** 2026-10-09  
**Status:** Designer/operator direction for planning and implementation integration  
**Audience:** Opus / AEW implementation planner  
**Purpose:** Convert the 2026-10-09 agent-effectiveness research into executable AEW work without creating unnecessary new architecture.

## 1. BLUF

The research is **accepted with three designer revisions**.

The main conclusion is:

> AEW does not need a new "agent effectiveness" subsystem. It should finish and connect existing context-pack, project-map, Knowledge, worker-tool, impact, coordination, attention, and evaluation machinery.

The goal is two-sided:

1. **Weak-worker amplification:** give weaker models every safe deterministic advantage AEW can provide so they spend less capability on repository discovery, tool selection, task reconstruction, and remembering what they were doing.
2. **Frontier conservation:** give Astra-class models excellent helpers and high-signal state without forcing them through hand-holding abstractions that may be slower than expert raw tooling.

The intended asymmetry is deliberate:

```text
Astra-class profile:
    raw expert tools available
    typed helpers available
    maps/Knowledge available
    high-signal context and deltas
    use helpers when useful; do not constrain expert behavior

Weak/lower-bound profile:
    explicit orientation
    typed helpers prominently presented
    bounded source/test/constraint locators
    Knowledge/history lookup
    platform-owned recitation on long runs
    completion-impact assistance
    raw tools remain available as escape hatch
```

AEW should optimize each profile for effective engineering performance inside the **same authority architecture**. Do not encode model names into workflow semantics.

## 2. Source research disposition

The synthesis disposition is accepted:

- **R8 Task Context Compilation:** no new component; improve existing `ContextPacks` / `knowledge/context.py`.
- **R9 Intent-Level Capability Resolution:** no giant semantic facade; extend the existing typed role surface and provider-resolution layers.
- **R2-B Weak-Model Working State:** reject model-maintained structured state; use platform-owned recitation plus the already-recommended bounded handoff note.
- **E1 Pre-Completion Impact Nudge:** implement/probe as a T5/impact/validation extension; never a gate merely because something is related.
- **E2 Delta-First Lead Attention:** implement/probe as a projection over existing outbox/ActionProjection/F9/R3/F20/M5 state; no new store.

The research's simplest-system recommendation is accepted in spirit:

1. better context packs with locators;
2. useful typed reads for workers;
3. platform-owned recitation on long runs;
4. one bounded impact/completeness query;
5. one delta query for the Lead.

## 3. Designer revisions to the synthesis

### REVISION A — Preserve workspace-bounded lexical fallback

The synthesis rejects a broad free-text `repo.search` operation. That is acceptable as an API/design choice **only if ordinary bounded lexical search remains available beneath the intent layer**.

Required invariant:

> A worker must not need to construct its own repository root merely to perform ordinary textual search inside its authorized workspace.

If `map.find("foo")` cannot resolve the request from maps/indexes, AEW may internally fall back to workspace-rooted `rg` or an equivalent qualified provider.

The public operation name is implementation-local. Do not remove raw `rg`/shell access from strong profiles.

### REVISION B — Do not silently alter frozen M4-H treatment

Nothing in this research automatically changes the frozen M4-H experiment.

If any structural/context change is considered necessary for M4-H representativeness:

1. explicitly identify the treatment change;
2. amend the experiment manifest/preregistration;
3. re-freeze before running.

Otherwise, land/evaluate it after the existing M4-H gate.

There must be no invisible treatment drift under the label "implementation-local."

### REVISION C — Bound the F19 harness-session reader

Approve evaluator-side use of the retained harness session database, but with a narrow contract:

```text
experimental run completes
    -> hidden F19 evaluator opens session DB read-only
    -> extracts only preregistered measurement fields
    -> computes named/versioned metrics
    -> records evaluation result
    -> raw DB retained only for the configured evaluation-retention window
```

Constraints:

- AEW runtime does not consume the session database.
- This does not become a general Knowledge or supervision source.
- The evaluator does not opportunistically ingest arbitrary conversational content.
- Retention is bounded and operator-configured.
- Use is evaluation-only under F19 isolation rules.

## 4. Context-pack direction (R8)

Do **not** create a standalone "Context Compiler" service/component.

Treat context compilation as the behavior of the existing context-pack machinery.

Implementation direction:

- per-role serving policy: mandatory / opportunistic / on-demand / prohibited;
- derived-section rendering includes source, revision, freshness, coverage/limitations, expansion reference;
- execution-profile operational knobs may include `context.budget_chars`, `context.orientation_max_chars`, and `context.orientation = minimal | standard | explicit`;
- criteria/objective may be repeated in an explicit weak-profile orientation mode if evaluation supports it;
- inputs should prefer declared anchors and deterministic locators before broad context;
- Knowledge stays on-demand/tool-driven until M6b Arm B is measured;
- stale/partial derived information must be visibly qualified.

### Review/verifier independence

Do **not** exclude all same-Ticket history.

Independent review means fresh/bounded context and exclusion of current implementer reasoning/private working state by default.

Canonical same-Ticket material may still be necessary, including objective/requirements, accepted plan, implementation diff, check results, unresolved review findings, verification failures/evidence, and governing decisions.

The context-pack/request-binding policy, not model query text, enforces independence.

## 5. Typed worker read surface (R9)

The worker-facing read tools should extend the existing **`aew-run` supervisor bridge**.

Reference shape:

```text
worker model
    -> typed role-side client inside worker boundary
    -> supervisor bridge
    -> authorized map / Knowledge / Evidence / check provider
```

Credentials remain supervisor-side.

Initial high-value operations may include:

```text
map.find
map.symbol
map.callers
map.callees
map.tests_for
map.constraints
map.changed

knowledge.search
knowledge.get

evidence.show
check.suggest

existing:
whoami
check.run
submit
```

Exact names remain implementation-local unless already frozen elsewhere.

### Tool-presentation policy

Do not force one presentation policy on all models.

Use profile-level operational knobs such as:

```text
tools.presentation = raw-first | neutral | typed-first
```

Expected evaluation posture:

- strong/frontier profile: likely `raw-first` or `neutral`;
- weak/lower-bound profile: likely `typed-first`;
- actual defaults must be earned by measurement.

Typed helpers supplement raw tools. They do not replace shell/Git/`rg` for expert models.

## 6. Weak-model working-state direction (R2-B)

Do not build a model-maintained structured working-state store, mandatory self-refresh, a new authority/record type for scratch state, or Lead access to raw private chain-of-thought or raw harness-session content.

Build/evaluate:

### Bounded handoff note

Finish the already-recommended run handoff/working-note path.

Properties:

- bounded;
- worker-authored;
- claim/reference, not authority;
- useful to a replacement invocation;
- may cite paths/evidence IDs;
- does not automatically become Knowledge.

### Platform-owned recitation

On sufficiently long/complex weak-profile runs, AEW may synthesize a zero-model-cost recitation from canonical/derived state, e.g. goal / active criterion, remaining criteria, plan tasks, changed files vs planned scope, checks performed, open findings/blockers, and the latest bounded handoff note.

The important boundary:

> AEW derives and restates what it already knows; the weak model is not required to maintain a second state system.

Thresholds/cadence are operational and must be evaluated.

## 7. Completion-impact nudge (E1)

Fold this into T5 impact + implementation validation.

Before `request_review`, AEW may surface a bounded high-confidence set of related-but-untouched surfaces.

The worker may disposition each item as `addressed`, `unaffected`, or `unsure`.

Rules:

- advisory by default;
- relation does not prove modification is required;
- no gate merely because an item is related;
- cap output aggressively;
- show uncertainty/coverage;
- use one computed impact surface for worker, reviewer, and later supervision consumers;
- evaluate false-positive and dismissal rates.

## 8. Delta-first Lead attention (E2)

Fold this into existing Lead/attention/supervision machinery.

Add one typed "changes since cursor" style query over existing committed events/projections.

Requirements:

- full `status` / `resume` remains available;
- no second event/state store;
- cursor binds to existing revision/event-watermark semantics;
- decisions required, blockers, and high-value supervision candidates remain prominent;
- measure whether delta-first saves Astra turns/tokens without hiding material developments.

## 9. Model profiles for research

### Laguna is not currently available

Laguna S2.1 remains the reference default-worker architecture target, but it is **not currently available in the operator's environment**.

Do not gate R8/R9/R2-B work on Laguna availability.

Use capability-class lanes instead:

```text
frontier profile:
    Astra-class / strongest available Lead model

mid profile:
    qualified model available through the operator's OpenAI API account

weak / lower-bound profile:
    qualified OpenCode free or inexpensive model
```

The lower-bound profile is not a "Laguna substitute." It is intentionally a stress specimen for testing whether AEW scaffolding helps weaker agents.

Record exact provider/model/harness/effective profile at preregistration.

If Laguna becomes available later, run the same profile-neutral suite.

### Lower-bound pre-M4-H fixture

The lower-bound qualification lane may run **before M4-H** on an independent non-held-out fixture.

Preferred order:

1. sanitized/public several-hundred-file repository;
2. purpose-built synthetic representative repository;
3. Q7 repository without sealed tasks only if a repo-specific integration probe genuinely requires it;
4. never expose Q7 sealed tasks before the gate.

Pre-gate lower-bound results are qualification/instrumentation evidence only, not M4-H/F19 efficacy claims.

## 10. Operator decisions already resolved

### 10.1 Pull the `aew-run` read half forward

**APPROVE.**

Do not wait for the complete M6a capability registry to expose safe worker read/query operations if the existing bridge can host them compatibly.

### 10.2 F19 evaluator-side session DB reader

**APPROVE WITH BOUNDS** described in §3 Revision C.

### 10.3 Weak/lower-bound profile

Use a currently available qualified free/inexpensive OpenCode model for the lower-bound lane, plus an available OpenAI API model where useful for a middle profile.

Laguna remains a future reference target.

## 11. Required roadmap/register integration

Opus should update the implementation plan/register rather than produce new architecture for these findings.

### Raise / pull forward

- T5-D / F22.3 test relationship index + constraint locators.
- F15.3 `aew-run` **read half** before full M6a where dependencies allow.
- R2 bounded handoff-note implementation.
- F19 evaluator metric reader/instrumentation.
- reviewer layout/orientation row and Lead structural-map/resume support where already owned by T5/context work.

### Refine existing entries

- T5/F30 impact work: first bounded completion-impact slice.
- F9/F20/M5: delta-first Lead projection and later supervision candidates.
- execution-profile schema: context budget/orientation, tool-presentation mode, recitation operational thresholds.
- context-pack serving policy and independence filter.
- F9-A1 should be formally ingested if still only tracked as an external/unmerged design artifact.

### After M6b Arm B

Expose `knowledge.search` and `knowledge.get` through the same `aew-run` read surface.

Do not automatically inject Knowledge into worker context before Arm B evaluation earns it.

## 12. Evaluation work, not default policy

Build enough substrate to run these F19 probes, but do not make their aggressive modes default until measured:

- R8 pack arms;
- R9 raw-first / neutral / typed-first tool-presentation arms;
- R2-B no support / handoff / recitation / recitation + Lead view;
- E1 completeness-nudge arms;
- E2 full / delta available / delta-first Lead view.

Primary measure remains independently verified correctly accepted outcomes.

Also measure tokens, frontier-model tokens separately, tool calls, time to relevant source, repeated exploration, repository-wide searches, missed related surfaces, worker drift/restarts, Lead interventions, context size, stale-context reliance, false-positive nudges, voluntary typed-helper usage, and full-view fallback rate.

## 13. Explicit non-goals / rejected expansions

Do not build from this research:

- a standalone Context Compiler service;
- a second capability registry;
- one giant free-text semantic facade;
- forced typed-tool-only operation for Astra-class models;
- model-name-specific workflow semantics;
- automatic Knowledge injection before Arm B;
- a model-maintained working-state store;
- mandatory scratch-state refresh;
- Lead access to raw worker scratch/chain-of-thought;
- a relation-derived completeness gate;
- a second attention/event store;
- peer-worker inspection outside existing coordination/supervision policy.

## 14. Related designer clarification — reviewer independence

Worker Knowledge lookup remains a default capability.

For independent reviewer/verifier roles:

- exclude current implementer reasoning/private scratch by default;
- do **not** blanket-exclude all same-Ticket canonical history;
- preserve required unresolved findings, verification failures, accepted plans, checks, and canonical Evidence;
- deeper historical prose may require the qualified investigation mode;
- enforce the filter in engine/context request binding.

## 15. Related designer clarification — Ticket parent changes vs promotion

For E19-B implementation:

- an ordinary revision may **not** change a committed Ticket from one parent to another;
- arbitrary re-parenting requires a replacement Ticket with explicit lineage;
- this applies even if work has not yet started, once the Ticket identity is committed;
- an uncommitted/draft Ticket may correct its parent before identity becomes governing.

KC §9.4 **promotion is a distinct hierarchy-expansion operation**. Promotion remains allowed after work starts and preserves original Ticket identity, evidence/history, effective risk/class floor, and inherited non-waivable gates/guardrails.

Until implementation text is updated, fail closed on ambiguous re-parenting.

## 16. Planning instruction to Opus

Please incorporate this handoff into the active AEW implementation plan/register.

Do **not** reopen frozen architecture unless integration reveals an actual contradiction.

For every item, classify it as one of:

```text
existing item — no change
existing item — priority/sequence change
implementation-local refinement
F19 probe
editorial contract clarification
true design gap
```

Escalate only true design gaps.

For implementation-local choices, choose the simplest conservative design consistent with governing contracts and proceed.

The desired outcome of this planning pass is an ordered implementation delta with:

- existing owner/register item;
- dependency;
- exact new work;
- sequencing change if any;
- completion criterion;
- probe/evaluation dependency;
- whether it can proceed before M4-H;
- whether it requires operator/designer action.

The design objective is not to add more AEW machinery.

It is:

> **Give weaker models every safe deterministic advantage they need, give frontier models every useful tool without getting in their way, and move model effort away from rediscovery and ceremony toward engineering reasoning.**
