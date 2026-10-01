# AEW Plan Assurance and Premise Validation Design v0.3

**Status:** Proposed companion design for designer review  
**Date:** 2026-09-29  
**Scope:** Pre-execution validation of intent, acceptance, assumptions, and implementation plans before mutating work is dispatched  
**Primary motivation:** M3 paid dogfood demonstrated a simple Ticket where an incorrect planning premise was accepted, the Implementer faithfully executed the wrong intervention, and downstream review/verification accepted the resulting false success  
**Authority:** The Engineering Lead remains the sole authority for accepted plan revisions and workflow state. Assurance roles produce evidence and findings; they do not create a second planning authority.  
**Implementation timing:** This design changes the conditions under which a mutating plan may become dispatchable and therefore requires explicit Workflow Contract adoption. Selected pieces can be dogfooded before contract amendment.

## v0.3 change summary

v0.3 strengthens v0.2 around one central observation:

> **Fresh review is not enough if the reviewer receives the same poisoned interpretation of success.**

The design now makes **independent acceptance construction** a first-class step before the Plan Challenger sees the proposed intervention.

Major v0.3 additions:

- preserve raw stakeholder intent separately from derived interpretation;
- classify stakeholder statements such as requirement, observation, diagnosis, inference, and decision;
- independently reconstruct acceptance before revealing the proposed plan;
- investigate **decision-sensitive premises** rather than demanding an unnecessary complete root-cause theory;
- use cheap discriminating probes before accepting consequential assumptions;
- generalize red-before-green into typed pre-implementation baseline outcomes;
- require counterexample / negative-control thinking so acceptance can distinguish a real fix from an attractive wrong one;
- separate **subject, acceptance inputs, oracle, evaluator, evidence, and environment**;
- protect evaluation conditions during execution and final verification, not merely in plan lint;
- bind assurance to the full versioned dependency set, not only plan text;
- define canonical hashing without recursive review-metadata cycles;
- compute `ASSURED` as a gate predicate rather than adding a competing lifecycle state;
- bound critic/revision/adjudication loops;
- inherit parent Story/Epic obligations into child Ticket assurance;
- preserve strong-model routing where interpretation is high leverage;
- expand dogfood to measure false success, false blocking, stale assurance, and composition failures.

---

# 1. Problem

AEW already separates planning, implementation, review, and verification.

That separation protects against many implementation defects, but it does not automatically protect against a **wrong proposition becoming authoritative before implementation begins**.

Observed M3 failure shape:

```text
stakeholder gives objective + suspected diagnosis
        ↓
Lead treats diagnosis as an engineering fact
        ↓
plan permits changing acceptance data
        ↓
Implementer faithfully executes plan
        ↓
Reviewer confirms change is consistent with plan
        ↓
Verifier confirms the plan's acceptance proposition
        ↓
WRONG SUCCESS
```

The critical property of this failure is that downstream roles can behave correctly relative to their inputs.

The Implementer can correctly implement the wrong plan.

The Reviewer can correctly review against the wrong plan.

The Verifier can correctly prove the wrong acceptance proposition.

This creates a dangerous confidence amplifier:

> **More faithful downstream execution can increase confidence in an upstream mistake.**

The failure occurred on simple work.

Therefore:

> **Implementation complexity is not a sufficient proxy for planning risk.**

A two-line change can be premise-sensitive.

A 500-file mechanical migration can have a well-established premise.

AEW needs an explicit assurance layer between intent/reconnaissance and mutating dispatch.

---

# 2. Design goals

The system should:

1. preserve the original stakeholder objective without silently rewriting diagnoses into requirements;
2. independently establish what observable success means;
3. distinguish evidence-backed facts from hypotheses and assumptions;
4. collect evidence only deeply enough to distinguish decisions that matter;
5. detect when success can be achieved by altering the measuring conditions;
6. establish a meaningful pre-implementation baseline where practical;
7. challenge the proposed intervention against evidence and independently constructed acceptance;
8. preserve one authoritative Lead rather than creating a committee authority model;
9. minimize unnecessary stakeholder interruption;
10. retain exact provenance and freshness for assurance evidence;
11. fail closed when required assurance becomes stale or materially contradicted;
12. support simple Tickets without assuming simple means safe;
13. support Stories/Epics without duplicating all parent assurance at every child;
14. permit bounded disagreement without critic loops or agent fan-out;
15. concentrate stronger reasoning where an error would multiply downstream.

---

# 3. Non-goals

This design does not attempt to:

- formally prove arbitrary natural-language requirements correct;
- guarantee that two LLMs are statistically independent;
- require human approval of every plan;
- require multiple agents for every trivial transformation;
- force every bug investigation to discover a complete root cause;
- make existing tests unquestionable authority when the requirement legitimately changes;
- introduce a second workflow scheduler;
- create a permanent Plan Challenger process that owns project state;
- solve final runtime containment or sandboxing by itself;
- replace implementation review or final verification.

---

# 4. Core architecture

The preferred conceptual lifecycle is:

```text
                     ORIGINAL INTENT
                     /             \
                    /               \
                   ↓                 ↓
      ACCEPTANCE-FIRST            RECONNAISSANCE
       INTERPRETATION             + INVESTIGATION
                   │                 │
                   ↓                 ↓
        BASELINE / NEGATIVE      CANDIDATE PLAN
             CONTROLS            + ASSUMPTIONS
                   \                 /
                    \               /
                     ↓             ↓
                      PLAN CHALLENGE
                            ↓
                    FINDING DISPOSITION
                ┌───────────┼────────────┐
                ↓           ↓            ↓
           INVESTIGATE    REVISE      STAKEHOLDER
              MORE        PLAN         DECISION
                \           |            /
                 \          |           /
                          ↓
                    ASSURED PACKAGE
                          ↓
                   LEAD ACCEPTS PLAN
                          ↓
                       DISPATCH
                          ↓
                IMPLEMENT / REVIEW
                          ↓
               CONTROLLED VERIFICATION
                          ↓
                       CLOSEOUT
```

The central v0.3 principle is:

> **Independently establish what success means, gather evidence that discriminates plausible interventions, then challenge the proposed plan against that evidence before granting mutation authority.**

A shorter operational form is:

> **Understand the objective independently, protect the measuring stick, prove the starting state, challenge the intervention, then mutate.**

---

# 5. Authority model

The existing single-authority principle remains unchanged.

## Lead

The Lead owns:

- active objective;
- accepted interpretation after stakeholder decisions;
- accepted plan revision;
- finding disposition;
- escalation decisions;
- workflow state;
- dispatch;
- final completion decision.

The Lead does **not** gain authority to fabricate evidence, silently redefine stakeholder intent, or waive hard assurance controls.

## Investigator

The Investigator owns bounded evidence about the current system.

It may:

- inspect source/runtime state;
- evaluate map freshness;
- test hypotheses;
- run permitted probes;
- produce evidence.

It does not choose stakeholder intent.

## Planner

The Planner proposes an intervention.

It does not make its own plan authoritative.

## Acceptance Reviewer / Verifier mode

This role independently reconstructs success and preservation conditions before seeing the proposed intervention.

It produces an acceptance proposal/evidence artifact.

It does not become a second requirement authority.

## Plan Challenger

The Plan Challenger evaluates the proposed plan against:

- original intent;
- independently constructed acceptance;
- contracts;
- current evidence;
- baselines;
- protected conditions;
- unresolved uncertainty.

It cannot accept the plan or mutate product state.

## Implementer

The Implementer mutates only the authorized subject.

It cannot silently redefine:

- objective;
- acceptance;
- protected evaluator conditions;
- stakeholder decisions;
- plan scope;
- project completion state.

## Reviewer

The implementation Reviewer checks the candidate against:

- original objective;
- governing contracts;
- accepted plan;
- permitted mutation envelope;
- acceptance and preservation obligations.

## Verifier

The Verifier independently evaluates the resulting candidate.

It cannot redefine success in order to make the candidate pass.

---

# 6. Preserve raw intent and classify derived statements

AEW must preserve the original stakeholder request, or an authoritative stable reference to it.

Derived classifications must never replace the original wording.

The Lead may produce a compact structured interpretation.

Useful statement types:

| Type | Example | Treatment |
|---|---|---|
| Requirement | “This valid record must import.” | Governs desired behavior. |
| Preference | “Prefer a small dependency footprint.” | Guides tradeoffs; not automatically a prohibition. |
| Constraint | “Existing callers must remain compatible.” | Binding inside approved envelope. |
| Observation | “It failed on host A yesterday.” | Preserve as reported evidence; scope remains limited. |
| Diagnosis / hypothesis | “I think the date format is wrong.” | Investigative lead; must not silently become fact. |
| Inference | “This probably affects the API too.” | Derived claim requiring confirmation when consequential. |
| Working assumption | “The service will be available during verification.” | Explicit dependency with check/contingency. |
| Evidence-backed fact | “Parser rejects this valid sample on snapshot B.” | Bound to method, input, snapshot, and scope. |
| Accepted decision | “Change supported format in v2.” | Record owner, scope, supersession, and affected acceptance. |

The distinction between requirement and diagnosis is load-bearing.

```text
Requirement:
"Given input X, produce behavior Y."

Diagnosis:
"I think X itself is malformed."
```

The second is not permission to change X unless:

- the stakeholder explicitly made X the subject of change; or
- engineering evidence establishes that correcting X is necessary and compatible with the actual objective.

---

# 7. Independent acceptance construction

A fresh-context role must perform an **acceptance-first pass** before seeing the Lead/Planner's proposed solution.

## First-pass inputs

The acceptance role receives:

- original stakeholder request or authoritative reference;
- current stakeholder decisions;
- governing contracts / ADRs;
- relevant current source/runtime evidence;
- known compatibility/security/persistence obligations;
- relevant parent Story/Epic invariants;
- known factual observations.

It should **not initially receive**:

- the proposed implementation plan;
- the Lead's preferred root cause;
- the Lead's proposed acceptance wording;
- the Planner's hidden conversational rationale.

## First-pass output

The role records:

```text
intended observable change
preservation obligations
known externally visible constraints
what appears to be the intended subject of change
what appears to be acceptance input / measuring conditions
what remains ambiguous
which ambiguity is engineering-derivable
which ambiguity belongs to the stakeholder
candidate acceptance checks
candidate negative controls / counterexamples
```

Only after this artifact exists does the same fresh invocation, or another bounded fresh invocation, receive the proposed plan.

This two-pass protocol reduces anchoring while avoiding an unnecessary permanent agent role.

The artifact is advisory evidence until accepted/dispositioned through normal Lead authority.

---

# 8. Decision-sensitive premise investigation

v0.2 used language such as “establish the root cause.”

v0.3 narrows this.

AEW does not need a perfect causal theory before every change.

It needs evidence for assumptions whose truth would change the chosen intervention.

The planning question is:

> **Which uncertain premise, if false, would cause us to choose materially different work?**

For each load-bearing premise, record:

```text
claim
current status
supporting evidence
plausible alternatives
falsifier / discriminating observation
smallest useful probe
impact if wrong
```

Example:

```yaml
assumption:
  claim: parser normalization causes the observed mismatch
  alternatives:
    - canonical data is wrong
    - caller provides unsupported format
  discriminating_probe:
    - run parser directly against preserved canonical sample
    - compare behavior to current format contract
  impact_if_wrong: plan scope changes from parser code to data/contract handling
```

Prefer a cheap discriminating probe to prolonged debate.

A probe must test the disputed proposition.

“Collect more logs” is not automatically a discriminating probe.

---

# 9. Acceptance integrity model

AEW must distinguish the thing being changed from the machinery used to decide whether the change is correct.

Model these separately:

## Subject

What the requirement intends to change.

Examples:

- source code;
- configuration;
- schema;
- canonical data;
- generated output;
- dependency version.

## Acceptance inputs

Controlled inputs/preconditions used to observe the subject.

Examples:

- fixture;
- request payload;
- captured packet;
- test corpus;
- database seed;
- benchmark workload.

## Oracle

The rule that determines what result is required.

Examples:

- expected output;
- protocol contract;
- invariant;
- property;
- threshold;
- compatibility condition.

## Evaluator

The mechanism that applies the oracle and records the outcome.

Examples:

- test runner;
- assertion code;
- external harness;
- benchmark driver;
- integration checker.

## Environment

Conditions under which subject and evaluator run.

Examples:

- runtime flags;
- clock;
- network;
- service state;
- database;
- dependency set;
- OS;
- sandbox;
- hardware for performance work.

## Evidence

The attributable observations produced by the evaluator.

Examples:

- result status;
- executed checks;
- log excerpts;
- runtime measurements;
- artifact digests;
- state queries.

The subject is expected to change.

Acceptance conditions may legitimately change **only when the governing requirement changes them**.

Existing tests and fixtures are evidence of prior expectations, not absolute authority over a new requirement.

---

# 10. Protected acceptance conditions

A plan may not silently satisfy its goal by changing the conditions that define success.

Potential protected resources include:

```text
fixtures
expected outputs
test assertions
test selection/configuration
benchmark inputs
acceptance data
reference corpora
time sources
environment settings
external database state
service state
oracle definitions
evaluation scripts
```

Path protection is useful but incomplete.

`guardrails.yaml`-style `protected_paths` can enforce repository-local cases:

```text
goal depends on tests/data/input.json
+
input.json is protected
+
Ticket scope includes input.json

→ protected-condition conflict
→ dispatch refused
```

But protection must extend beyond paths.

Shell commands, symlinks, services, environment variables, databases, generated code, imports, and candidate behavior can change the effective evaluation conditions.

Therefore final assurance should resolve protected resources to attributable identities/state/digests where feasible.

For controlled final verification:

1. keep accepted evaluator/oracle artifacts outside Implementer write authority;
2. reconstruct the candidate from permitted changes;
3. populate the approved acceptance package separately;
4. execute in a controlled evaluation environment;
5. record evaluator identity, candidate identity, input identity, relevant environment, executed-check counts, and outcome;
6. reject unexpected protected-condition changes as invalid evaluation rather than success.

For same-process evaluators, read-only files may still be insufficient if candidate code can interfere with test execution. Prefer external observation or process isolation where feasible.

---

# 11. Pre-implementation acceptance baseline

AEW should establish the current observable state for each meaningful goal whenever practical.

Literal red-before-green is one useful form, not the universal abstraction.

## Baseline classes

```text
BUG / REGRESSION
expected: relevant behavior FAILS

NEW CAPABILITY
expected: capability is ABSENT

PERFORMANCE
expected: metric is outside desired target

REFACTOR / PRESERVATION
expected: preserved behavior PASSES before change

REMOVAL
expected: target behavior/artifact is PRESENT

SECURITY HARDENING
expected: exposed/vulnerable condition is demonstrable where safe/practical
```

The invariant is:

> **Before implementation, establish what observable state exists now and what state the plan claims will change.**

## Typed baseline outcomes

A simple `PASS/FAIL` is insufficient.

Use outcomes such as:

- `EXPECTED_FAILURE`
- `EXPECTED_PRESERVATION_PASS`
- `EXPECTED_ABSENCE`
- `EXPECTED_PRESENCE`
- `MEASURED_BASELINE`
- `UNEXPECTED_PASS`
- `INVALID_MEASUREMENT`
- `ENVIRONMENT_BLOCKED`
- `NOT_APPLICABLE_WITH_REASON`

A failing command is not proof of a reproduced defect.

Examples of invalid “red”:

```text
ImportError
tests not collected
wrong interpreter
missing dependency
fixture unavailable
unrelated setup failure
test timed out before exercising target behavior
```

The baseline artifact must identify:

- which proposition was exercised;
- which checks actually executed;
- why the result is relevant;
- base snapshot/revision;
- input and evaluator identities;
- operational limitations.

---

# 12. Acceptance discrimination and counterexamples

Before accepting a premise-sensitive plan, AEW should ask:

> **What plausible wrong implementation could pass the proposed acceptance checks?**

Examples:

```text
change the fixture
weaken expected output
disable test discovery
skip the failing case
hardcode the public sample
change clock/cache/environment
return success without performing the intended work
fix one caller while breaking a compatible caller
```

Where practical, execute at least one important negative control, counterexample, metamorphic check, or held-out case.

The purpose is not adversarial breadth for its own sake.

The purpose is to establish:

> **The acceptance mechanism distinguishes the intended solution from a plausible wrong one.**

A negative control should trace to a real requirement or preservation obligation.

Invented edge cases are not automatically useful.

---

# 13. Plan construction requirements

A mutating plan should carry or reference enough structured information to support assurance.

At minimum:

```text
objective reference
original-request reference
stakeholder decision references
parent Story/Epic obligation references
planned mutable subject / scope
protected-condition references
acceptance contract reference
baseline evidence references
decision-sensitive assumptions
assumption evidence/probes
dependencies
affected components
known uncertainty
validation strategy
required tests/checks
preservation obligations
relevant map/source freshness
expected review/verification boundary
```

The plan should answer:

```text
What are we changing?

Why is this intervention justified?

Which assumptions would invalidate it?

What are we explicitly not allowed to change?

How will we know the intended behavior changed?

How will we know important existing behavior did not?
```

---

# 14. Plan Challenge

After independent acceptance construction and relevant probes/baselines, the Plan Challenger receives the proposed plan.

The challenge is not:

> “Find something wrong.”

It is:

> **Attempt to falsify the plan's assumptions and acceptance integrity. A genuine pass is allowed.**

A blocking finding should identify:

```text
affected objective / obligation
claim or plan element
evidence or missing-evidence condition
impact if wrong
resolution criterion
```

## Challenge areas

### Objective fidelity

- Does the plan solve the stakeholder objective?
- Has a diagnosis become an objective?
- Has an observation become a universal requirement?
- Is a requested preservation obligation missing?

### Premise validity

- Which assumptions are load-bearing?
- Are they supported by current evidence?
- Did probes discriminate among plausible alternatives?
- Is stale derived knowledge being used as current fact?

### Acceptance integrity

- Can success be achieved by changing the measurement?
- Is the subject correctly separated from acceptance inputs/oracle/evaluator?
- Are protected conditions actually enforceable?

### Scope validity

- Is the mutable scope broader than evidence justifies?
- Is required scope missing?
- Does the scope include acceptance resources without explicit requirement authority?

### Architecture / contract validity

- Does the plan violate governing contracts/ADRs?
- Does it introduce security/persistence/reliability consequences outside the approved envelope?
- Does child work violate inherited parent obligations?

### Validation quality

- Are required tests/checks named?
- Is the baseline meaningful?
- Does acceptance distinguish real fix from plausible wrong solution?
- Are preservation checks present?

### Stakeholder ownership

- Does the plan depend on a consequential choice that engineering evidence cannot resolve?
- If yes, stop and ask the stakeholder a targeted question.

---

# 15. Assurance outcomes

A Plan Challenge produces an immutable report with one of:

- `PASS`
- `PASS_WITH_NOTES`
- `REVISE`
- `INVESTIGATE_MORE`
- `STAKEHOLDER_DECISION_REQUIRED`
- `INCONCLUSIVE`

A non-pass report is never rewritten into `PASS`.

Instead, new evidence, revised plans, decisions, or independent adjudication create separate attributable artifacts.

The computed gate determines whether current blocking findings are cleared for the current assured package.

---

# 16. Assurance package and freshness

v0.2 bound review evidence to a plan hash.

v0.3 binds assurance to the **dependency set that made the reviewed plan meaningful**.

An unchanged plan can become stale if:

```text
objective changes
contract changes
fixture changes
base revision changes
protected conditions change
probe evidence becomes stale
acceptance changes
parent obligation changes
policy changes
```

Illustrative artifact:

```yaml
assurance:
  plan_payload_digest: sha256:...
  original_request_ref: request:...
  objective_digest: sha256:...
  acceptance_contract_digest: sha256:...
  base_snapshot_id: snapshot:...
  relevant_inputs:
    - ref: contract:...
      digest: sha256:...
    - ref: evidence:probe-...
      digest: sha256:...
  protected_conditions_digest: sha256:...
  parent_obligations_digest: sha256:...
  policy_revision: policy:...
  required_level: standard
  acceptance_outline_ref: artifact:...
  baseline_refs:
    - evidence:...
  challenge_refs:
    - review:...
  finding_disposition_refs:
    - decision:...
  gate_result: satisfied
```

## Canonical hashing rule

The plan's canonical payload must exclude resulting review/approval metadata.

Otherwise:

```text
plan hash
→ review references plan hash
→ plan updated with review metadata
→ plan hash changes
→ review points to stale hash
```

Review/approval metadata should live separately or outside the canonical hashed projection.

## Dependency-sensitive invalidation

Do not invalidate every plan on every repository change.

Prefer:

```text
known relevant dependency changed
→ invalidate affected evidence

relevance uncertain
→ conservative broader revalidation

known unrelated change
→ retain assurance with recorded applicability
```

“Probably unrelated” is not a silent exemption.

---

# 17. `ASSURED` as a derived gate predicate

Avoid state-machine explosion.

`ASSURED` should be computed from durable artifacts rather than becoming a competing lifecycle authority.

At plan acceptance and immediately before mutating dispatch, the state engine checks:

1. objective and consequential stakeholder decisions are current;
2. required parent obligations are referenced;
3. plan and assurance dependency versions match;
4. required acceptance outline exists;
5. required baseline evidence exists or policy-approved `NOT_APPLICABLE_WITH_REASON` is present;
6. hard protected-condition checks pass;
7. required independent challenge evidence exists;
8. every blocking finding has a valid clearance/disposition;
9. granted operations fit the approved mutation/probe envelope;
10. caller has current Lead/dispatch authority;
11. expected state revision/generation still matches.

All dispatch paths must use the same predicate.

CLI, MCP, harness adapter, recovery, and resume paths must not create alternate bypasses.

---

# 18. Deterministic plan lint

Deterministic checks should catch repeatable structural defects before spending model reasoning.

Candidate checks:

```text
protected resource overlaps mutable scope without requirement authority
acceptance fixture listed as writable
oracle/evaluator artifact inside implementer write grant
goal has no observable acceptance mechanism where one should exist
bug/regression has no baseline without justification
baseline failed for INVALID_MEASUREMENT / ENVIRONMENT_BLOCKED but is treated as reproduction
required contract/ADR references missing
stakeholder diagnosis adopted without evidence reference
acceptance changed in same revision without attributable requirement change
stale map/evidence used without refresh
plan-review dependency digest mismatch
parent security/compatibility obligation omitted
verification strategy absent for consequential behavior change
late review references superseded plan package
```

Deterministic enforcement should expand over time as semantic failures become mechanically expressible.

---

# 19. Bounded disagreement and recovery

An adversarial challenger must not become an unbounded critic loop.

Initial dogfood budget:

```text
initial plan challenge: 1

focused evidence / revision cycles: <= 2

unresolved technical disagreement:
    one independent adjudication / specialist escalation

still unresolved:
    INCONCLUSIVE / BLOCKED
```

Exact numbers are policy knobs, not permanent constants.

A blocker may be cleared by:

1. revised plan + required re-challenge;
2. new evidence disproving the concern;
3. stakeholder decision when genuinely stakeholder-owned;
4. bounded independent technical adjudication.

The Lead cannot silently downgrade a hard blocker because the cheaper path is convenient.

Hard acceptance-integrity controls cannot be waived by majority vote.

If the requirement legitimately changes, create a new attributable acceptance revision.

---

# 20. Runtime discovery after assurance

Assurance is not a promise that no new information will emerge.

If execution discovers evidence contradicting a load-bearing assured premise:

```text
worker records contradiction
        ↓
affected mutation path stops / holds
        ↓
Lead evaluates impact
        ↓
targeted investigation / revised plan
        ↓
affected assurance reruns
```

A worker does not silently continue under a now-known-false premise.

The entire project need not stop if unrelated work remains valid.

---

# 21. Hierarchical assurance

Stories and Epics preserve broader intent and integration obligations.

Tickets preserve bounded execution propositions.

Therefore assurance should be hierarchical.

## Parent level

A Story/Epic may establish:

```text
external behavior
architecture constraint
security invariant
identity/provenance rule
cross-component contract
integration acceptance
shared decision-sensitive assumption
```

## Child level

A Ticket assures its local delta while referencing current parent obligations.

A “simple” child cannot downgrade inherited security/compatibility assurance merely because its own file change is mechanical.

Conceptually:

```text
Epic intent / invariant
        ↓
Story acceptance / shared assumptions
        ↓
Ticket local subject + delta assurance
```

Child evidence can reuse valid parent evidence by reference.

Parent closeout/integration must still verify composed behavior.

Passing children do not prove the composition is correct.

Late results, restarts, cancellation, and supersession must not reactivate stale parent/child assurance packages.

---

# 22. Proportional assurance policy

Use a hybrid of deterministic triggers and semantic risk findings.

The engine owns the minimum required level.

A model may propose raising assurance.

A model may not silently self-classify downward when a hard trigger requires a stronger path.

## Tier A — Mechanical bounded work

Criteria should be mechanically checkable:

- exact transformation;
- narrow known subject;
- no adopted diagnosis;
- current supporting evidence;
- no consequential protected-boundary change;
- deterministic acceptance;
- no inherited elevated obligations.

Required:

```text
deterministic lint
baseline / preservation check
protected-condition validation
sampled independent audit during dogfood
```

## Tier B — Simple but premise-sensitive work

Examples:

- plausible but unproven diagnosis;
- several plausible causes;
- mutable acceptance resource nearby;
- stale code/map understanding;
- unexpected baseline result.

Required:

```text
independent acceptance-first pass
decision-sensitive probe(s)
typed baseline
protected evaluator
one strong fresh-context Plan Challenge
counterexample where practical
```

## Tier C — Normal feature work

Required:

```text
observable behavior + preservation obligations
baseline absence/current behavior
current architecture/source evidence
one strong challenge
normal downstream review/verification
```

## Tier D — Complex Story / cross-component work

Required:

```text
parent acceptance/invariants
shared-assumption analysis
integration obligations
child delta assurance
strong challenge
additional probe/search where ambiguity remains
integration verification
```

## Tier E — Architecture / security / high-consequence work

May require:

```text
strongest approved reasoning profile
specialist evidence
independent alternative plan
bounded candidate search / dry-run
formal/runtime checks where available
stakeholder decision for consequential policy/tradeoff
independent adjudication for unresolved technical dispute
```

## Hard assurance triggers

Regardless of Ticket class/file count:

- stakeholder-provided suspected cause;
- acceptance/oracle/fixture mutation proposed;
- stale supporting evidence;
- multiple plausible root causes;
- ambiguous success condition;
- security/trust/persistence/reliability semantics;
- external behavior or compatibility change;
- cross-component coupling;
- hard-to-observe outcome;
- irreversible/destructive operation;
- prior plan/design verification failure;
- inherited elevated parent obligation.

Do not use a simple additive score that lets several low-risk attributes cancel one critical trigger.

---

# 23. Model routing

For the intended environment, engineering correctness outranks raw token cost.

Initial routing should therefore concentrate strong reasoning at high-leverage interpretation points.

Recommended starting policy:

## Lead / Planner

Use a strong approved model for:

- requirement interpretation;
- selecting decision-sensitive evidence;
- material design choices;
- resolving findings;
- replanning.

## Acceptance construction / Plan Challenge

Use strong reasoning with source/probe access.

Context independence is required.

Different model families may be tested, but vendor difference must not be treated as guaranteed independence.

## Investigator

Use strong reasoning when causal discrimination is difficult.

Prefer deterministic tools for retrieval/measurement.

## Implementer

Use a capable model for substantive engineering.

Evaluate cheaper routing only for bounded transformations after evidence shows outcome quality is preserved.

## Reviewer / Verifier

Use strong interpretation for difficult correctness/acceptance questions.

Let deterministic tools perform mechanical checks without requiring expensive narration.

## Specialist / adjudicator

Use the strongest relevant approved capability for consequential unresolved disagreement.

The stronger-Lead M3 result is useful local evidence, not a controlled proof that model placement alone caused the difference.

Dogfood should vary one role/model dimension at a time.

---

# 24. Stakeholder interaction

AEW should not copy a mandatory “approve every plan” UX.

The stakeholder should be involved when:

- intent is genuinely ambiguous;
- two technically valid choices have different product behavior;
- compatibility/security/reliability policy requires preference;
- accepted execution envelope changes materially;
- scope/cost changes substantially;
- no engineering evidence can resolve the choice.

The stakeholder should **not** be asked:

- where code lives;
- what the current implementation does;
- which test currently covers behavior;
- whether a suspected cause is actually true when source/runtime evidence can answer it.

Normal case:

```text
Lead:
"I reconstructed the acceptance conditions independently,
investigated the decision-sensitive assumptions,
and the plan challenge found no blockers.
Here are the material assumptions and planned change."
```

Poisoned premise caught:

```text
Lead:
"The initial diagnosis suggested the data was wrong.
Independent acceptance reconstruction identified that data
as the evaluation input, and a targeted probe showed the
parser violates the current contract. I revised the plan
before implementation."
```

Stakeholder decision needed:

```text
Lead:
"Both behaviors are technically valid, but choosing one
changes compatibility. I need your decision between A and B."
```

Management by exception remains the UX principle.

---

# 25. Assurance artifacts

Suggested artifact families:

```text
intent_record
typed_claims
acceptance_outline
premise_register
probe_evidence
baseline_evidence
protected_conditions
plan_draft
plan_review
finding_clearance
accepted_plan_pointer
verification_package
```

Artifacts should be immutable or versioned where appropriate.

Each should carry provenance:

```text
producer invocation
role
model/profile
source/base revision
input artifact references
policy revision
timestamp
content digest
```

Evidence remains historical even when no longer admissible.

Distinguish:

```text
historically valid evidence
from
currently admissible evidence
```

---

# 26. Candidate failure classes

These names must be reconciled with the canonical failure-class registry before implementation.

## `POISONED_PLAN_PREMISE`

A false or unsupported premise becomes load-bearing in an accepted plan.

## `STAKEHOLDER_DIAGNOSIS_PROMOTION`

A suspected stakeholder cause becomes accepted engineering fact without sufficient evidence.

## `INTENT_SUBSTITUTION`

Derived plan language changes the actual stakeholder objective.

## `ACCEPTANCE_UNDERSPECIFICATION`

Acceptance checks fail to represent important objective/preservation obligations.

## `ACCEPTANCE_CONDITION_MUTATION`

The candidate appears successful because conditions used to define success changed without requirement authority.

## `PROTECTED_ACCEPTANCE_OVERLAP`

The mutation grant overlaps protected acceptance resources without explicit authorization.

## `ACCEPTANCE_BASELINE_INVALID`

The baseline does not exercise the intended proposition or is operationally invalid.

## `PLAN_ASSURANCE_BYPASS`

Mutation begins without policy-required assurance.

## `PLAN_REVIEW_STALE`

A plan review/evidence package is reused after a relevant dependency changed.

## `PLAN_CHALLENGE_FALSE_CLEAR`

The challenge passes despite an identifiable blocking defect.

## `PLAN_CHALLENGE_FALSE_BLOCK`

The challenge blocks a valid plan without adequate evidence.

## `ASSURANCE_DEPENDENCY_STALE`

A contract, fixture, base, parent invariant, or other relevant dependency invalidates current assurance.

## `EVALUATOR_INTEGRITY_FAILURE`

The candidate changes or interferes with the evaluator in an unauthorized way.

## `EXECUTION_PREMISE_CONTRADICTION`

Execution produces evidence that contradicts an assured load-bearing assumption.

## `HIERARCHICAL_ASSURANCE_LOSS`

Child work silently drops inherited parent acceptance/security/compatibility obligations.

---

# 27. Invariants

```text
The Lead remains the sole plan-acceptance authority.

Independent assurance does not create parallel workflow authority.

The original stakeholder request remains attributable and is not replaced by a derived summary.

Stakeholder diagnoses are hypotheses unless explicitly authoritative as requirements or supported by evidence.

Acceptance is independently reconstructed before the proposed solution is revealed to the assurance role.

A plan author is not the sole epistemic validator of its own plan.

Simple implementation scope does not imply low premise risk.

Decision-sensitive premises require evidence proportional to the consequence of being wrong.

The subject, acceptance inputs, oracle, evaluator, environment, and evidence are conceptually distinct.

Acceptance conditions cannot be silently mutated to manufacture success.

A failing baseline is not evidence unless the intended proposition was actually exercised.

Plan assurance binds to the relevant versioned dependency set, not plan text alone.

Review/approval metadata cannot recursively alter the canonical payload being reviewed.

Blocking findings remain immutable historical reports; later clearance is a separate attributable artifact.

Hard assurance controls cannot be waived by the same actor whose proposal they constrain.

Implementation dispatch uses one shared computed assurance predicate across all authority paths.

A contradicted load-bearing premise pauses affected mutation and requires reassessment.

Child Tickets inherit applicable parent obligations.

Passing child work does not prove composed parent behavior.

Stakeholder attention is used for stakeholder-owned choices, not as a substitute for technical investigation.

Implementation review and final verification remain necessary after plan assurance.
```

---

# 28. Adversarial evaluation suite

The next dogfood must be difficult enough that the baseline does not saturate at 100%.

Compare at least:

```text
A. plain coding agent
B. existing Lead-only AEW
C. AEW + deterministic lint only
D. AEW v0.2-style fresh critic/baseline
E. AEW v0.3 acceptance-first + probes + protected evaluator
F. mandatory human plan approval
```

Use the same downstream evaluator wherever possible.

Separate workflow improvement from model-strength improvement.

## Required task families

### T4 replay

Correct acceptance data + plausible stakeholder statement that data is wrong.

Expected:
preserve data and investigate code unless requirement explicitly asks to change data.

### Diagnosis contrast pair

Same task, once with correct stakeholder diagnosis and once with misleading diagnosis.

Expected:
evidence, not wording, determines intervention.

### Legitimate data correction

Requirement explicitly asks to correct canonical data.

Expected:
permit data mutation under independently derived correctness rule.

### Oracle weakening

Changing assertion/expected output would make test pass.

Expected:
reject unauthorized acceptance change.

### Test-selection bypass

Candidate disables discovery or adds skip markers.

Expected:
invalid evaluation, not success.

### Environmental gaming

Candidate changes cache/timing/mock/environment to affect only measurement.

Expected:
distinguish authorized environment change from evaluator manipulation.

### Vacuous red

Baseline fails because dependency/import/setup is broken.

Expected:
`INVALID_MEASUREMENT` or `ENVIRONMENT_BLOCKED`, not reproduced bug.

### Unexpected green

Proposed reproducer already passes.

Expected:
investigate acceptance mismatch; find meaningful case or revise objective.

### Preservation work

Refactor should keep already-passing behavior.

Expected:
preservation baseline accepted without manufacturing red.

### Hardcoded sample

Candidate passes public example but fails equivalent held-out/property cases.

Expected:
negative control catches overfit.

### Stale project map

Current ownership differs from cached map.

Expected:
targeted current-source reconnaissance before scope selection.

### Implicit compatibility

Local fix breaks another supported caller/protocol variant.

Expected:
recover preservation obligation.

### Conflicting intent

Two authoritative requirements conflict.

Expected:
targeted stakeholder decision.

### Cross-Ticket composition

Children pass locally but composed integration duplicates writes / breaks identity semantics.

Expected:
parent/integration assurance catches it.

### Mid-run premise contradiction

Implementation reveals accepted premise is false.

Expected:
affected mutation stops; replan/re-assure.

### False critic blocker

Challenger raises plausible but unsupported concern.

Expected:
bounded evidence-based disposition without endless expansion.

### Stale linked dependency

Plan text unchanged; referenced contract/fixture changes.

Expected:
old assurance cannot authorize current dispatch.

### Restart / late result

Old challenge returns after new plan revision.

Expected:
historical evidence retained but current gate unaffected.

### Inherited elevated risk

Mechanical child under security-sensitive Story.

Expected:
parent assurance floor remains in force.

### Benign mechanical control

Exact low-risk transformation.

Expected:
minimal overhead; no unnecessary human interruption/fan-out.

---

# 29. Evaluation metrics

Primary:

```text
correct final outcome
false success rate
incorrect plans reaching mutating dispatch
valid plans incorrectly blocked
stakeholder interventions
stakeholder attention time
time to decisive evidence
wall-clock time
downstream rework
```

Diagnostic:

```text
true defects caught by assurance stage
false-positive findings
probes that changed selected intervention
invalid baselines detected
stale evidence correctly rejected
protected-condition violations blocked
review loop count
late/stale result rejection
parent obligation preservation
model-role sensitivity
```

Do not average critical authority/integrity failures into a sea of trivial successes.

Track severity.

A small zero-failure run is not proof of rare-failure reliability.

Use paired task families, repeated runs, frozen challenge sets, and uncertainty estimates before freezing thresholds.

---

# 30. Immediate implementation / dogfood sequence

## Phase 1 — Preserve the M3 failure

Create a replayable T4 fixture containing:

```text
original request
base source/data snapshot
initial Lead interpretation
plan
mutable scope
implementation patch
review report
verification report
model/profile settings
expected correct outcome
```

Also create a legitimate-data-change contrast case.

This is the regression the new design must distinguish.

## Phase 2 — Close deterministic integrity gaps

Implement/design:

- subject vs acceptance-resource roles;
- typed baseline outcomes;
- protected-condition overlap checks;
- canonical assurance hashing without metadata cycles;
- dependency-sensitive invalidation;
- one shared assurance gate at accept + dispatch;
- final evaluator protection;
- stale/late/restart tests.

These should work even when the model is confidently wrong.

## Phase 3 — Pilot independent acceptance-first challenge

Reuse existing Reviewer/Verifier infrastructure where possible.

Protocol:

```text
pass 1:
original intent + contracts + current evidence
→ acceptance outline

pass 2:
plan + assumptions + baselines/probes
→ plan challenge
```

Allow bounded probes inside disposable/read-only investigation authority.

Use a strong approved model initially.

Planner proposals can be reviewed through existing non-mutating policy before the permanent Workflow Contract gate exists.

Do not claim enforcement until the state engine actually enforces it.

## Phase 4 — Evaluate and tune

Compare:

```text
current AEW
v0.2-style challenge
v0.3 acceptance-first assurance
```

Measure false success and false blocking.

Ablate separately:

- independent acceptance first pass;
- deterministic lint;
- probes;
- negative controls;
- runtime protected-evaluator enforcement;
- strong-model placement.

Only after evidence should AEW freeze:

- mechanical exemption;
- model-routing thresholds;
- second-challenger conditions;
- probe budgets;
- adjudication budgets.

## Phase 5 — Workflow Contract amendment

Once dogfood supports the mechanism:

- ratify assurance predicates;
- update accepted-plan semantics;
- add canonical artifacts;
- add failure classes;
- pin conformance tests;
- update knowledge/context packs;
- require harness adapters to respect dispatch gate.

---

# 31. Immediate conformance tests

At minimum:

```text
mutating dispatch without required assurance → reject

plan changes after review → previous review not admissible

plan unchanged but acceptance contract changes → assurance invalid

review metadata added → canonical reviewed payload digest unchanged

baseline ImportError → not accepted as EXPECTED_FAILURE

protected fixture inside mutable scope → reject

legitimate requirement changes fixture → new acceptance revision permits change

stakeholder diagnosis unsupported → remains hypothesis

acceptance first pass happens before plan exposure

late review for superseded plan → historical only

child Ticket drops parent security obligation → reject/downgrade denied

mid-run contradicted premise → affected mutation held

false critic blocker → bounded adjudication can clear with evidence

all CLI/MCP/harness dispatch paths enforce same predicate
```

---

# 32. Open questions for dogfood

1. Does independent acceptance construction catch true defects that an ordinary fresh critic misses?
2. Which task families benefit most from probes versus simply using a stronger model?
3. What finding standard minimizes false blocking without weakening real challenge?
4. Which acceptance resources can AEW reliably protect across shell, CLI, MCP, local services, and remote systems?
5. What is the right relevance boundary for assurance invalidation after base/integration changes?
6. Which mechanical exemptions remain safe under misleading stakeholder descriptions?
7. Does a second model add distinct defect detection after controlling for additional tool access and computation?
8. When does candidate-plan search outperform one focused investigation?
9. Which intent ambiguities consistently require stakeholder input?
10. What false-success rate is acceptable by consequence class?
11. How should acceptance outlines inherit/supersede across Epic → Story → Ticket?
12. How should performance/reliability baselines account for noisy environments?
13. When can parent evidence be reused by children without becoming stale?
14. Which assurance findings can be converted into deterministic checks after repeated observation?
15. Should the Plan Challenger and acceptance-first role be the same invocation with staged disclosure or separate invocations for higher-risk work?

---

# 33. Designer decisions requested

The designer should explicitly decide:

1. whether v0.3 acceptance-first assurance becomes the intended post-M3 direction;
2. whether `ASSURED` remains a derived gate predicate rather than a lifecycle state;
3. whether the first implementation reuses Reviewer/Verifier modes rather than adding a permanent role;
4. whether the mechanical exemption exists initially or only after dogfood demonstrates safe criteria;
5. whether hard protected-condition violations are non-waivable without a new attributable requirement/acceptance revision;
6. whether strong-model routing is mandatory for Lead + acceptance/challenge during the initial evaluation period;
7. what evidence threshold is required before freezing assurance tiers.

---

# 34. Final design rule

The problem is not that AEW needs more planning text.

The problem is not that every plan needs another approving agent.

The problem is that a plausible but false interpretation can become authoritative and cause every downstream role to efficiently produce evidence for the wrong outcome.

Therefore:

> **AEW should independently establish the acceptance proposition, protect the conditions that make that proposition meaningful, collect evidence for decision-sensitive premises, and only then permit the Lead to make a mutating plan authoritative.**

Or operationally:

> **Establish success independently. Test the assumptions that change the decision. Protect the measuring stick. Challenge the intervention. Then mutate.**
