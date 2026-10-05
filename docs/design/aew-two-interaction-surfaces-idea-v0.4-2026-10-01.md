# AEW Idea Note v0.4: One Engine, Two Interaction Surfaces

**Status:** Direction adopted (designer, 2026-10-01; register F15). Since 2026-10-05 the governing text for what this note describes is the typed Lead surface v0.2 (`typed-lead-surface-design-v0.2.md`): where the two overlap, that design governs, and the requirements of this note that it carries are marked absorbed in the requirements ledger. This note still governs what the design defers to it: §16 (event-driven safety mechanics), §17 (conditional publication, with the designer's decisions of 2026-10-01) and the F17 and anomaly obligations (§6, §19). Written as a non-governing idea note for discussion and review  
**Date:** 2026-10-01  
**Purpose:** Refine the F15/operator-UX direction after designer, reviewer, and implementer feedback. This is intentionally not yet a formal design or contract.

## 1. Core observation

AEW currently asks both humans and model Leads to perform too much workflow choreography that AEW can already derive from durable state, recorded policy, and guarded engine operations.

The useful dividing line is not:

```text
human vs agent
CLI vs UI
manual vs automatic
```

It is:

```text
judgment / intent / evidence
vs
policy-resolved workflow mechanics
```

The operator and the Lead should spend attention on decisions that require judgment.

AEW should perform mechanics whose inputs are already durable and whose choices are fully determined by current policy and engine guards.

> **Keep the primitives. Stop making them the normal UX.**

---

## 2. The governing interaction rule

"Deterministic" is too broad.

Some operations that look mechanical still contain policy or judgment.

The stronger rule is:

> **A high-level action may chain only substeps whose inputs are already durable and whose choices are fully determined by recorded policy. It must stop before the next unresolved judgment boundary.**

A stage may resolve policy.

A stage may not invent judgment.

---

## 3. Three machine-readable operation classes

Every primitive used by the stage layer declares one of three operation classes.

### `MECHANICAL`

Fully determined by durable state and engine rules.

Examples:

```text
record a transition whose guard already passed
rotate/revoke execution credentials
create/update queue bookkeeping
advance bookkeeping after successful custody handoff
recompute freshness
select FIFO among already-runnable queue entries
```

### `POLICY_RESOLVED`

Not hard-coded mechanics, but fully determined by recorded policy.

Examples:

```text
select required review cards
resolve execution profile/model
resolve isolation strategy
resolve capability grants
resolve budget
resolve required integration validation mode
```

Policy inputs and resolved outputs are recorded.

A caller override is an explicit, attributable decision.

### `JUDGMENT_BEARING`

Requires interpretation, preference, consequence acceptance, or semantic disposition.

Examples:

```text
accept a plan
accept review/verification evidence
downgrade risk
waive a gate
classify a verification failure
resolve a merge conflict
publish a candidate
mark accepted_open
approve a material hierarchy change
make a stakeholder-owned choice
```

### Fail-closed default

> **An unclassified primitive defaults to `JUDGMENT_BEARING`.**

No stage expansion may include a judgment-bearing primitive unless the required judgment input is already present as an explicit durable input to that stage.

---

## 4. Primitive declarations make the boundary machine-checkable

The boundary cannot live only in prose.

Conceptually:

```text
PrimitiveSpec {
    primitive_id
    operation_class
    required_judgments[]
    required_policy_inputs[]
    required_evidence[]
    side_effect_class
    idempotency_scope
    guard_id
}
```

Before a stage starts, the engine expands it and refuses if:

```text
required judgment input is absent
OR primitive is unclassified
OR required policy input cannot be resolved
OR a required guard cannot be evaluated
```

This makes hidden judgment an engine-level conformance failure rather than something reviewers must rediscover manually for every new stage command.

---

## 5. Two interaction surfaces over one engine

### Surface A — intent / stage interface

The normal operator and Lead interface.

It expresses a decision the caller has already made and lets AEW perform the mechanical and policy-resolved choreography implied by it.

Examples:

```text
ticket draft
ticket start
ticket request-review
ticket request-verification --review-evidence E42
ticket submit-integration --verification-evidence E77
integrate next
```

### Surface B — primitive / recovery interface

The exact lower-level operations remain available for:

- recovery;
- debugging;
- conformance testing;
- forensic inspection;
- AEW development;
- unusual workflows;
- expert control.

The primitive interface remains the conformance surface.

The stage interface is a façade over it, not an alternate state machine.

---

## 6. Recorded judgment is necessary, not sufficient

A model can copy an evidence identifier from `decisions_required` without actually exercising judgment.

Therefore AEW should distinguish:

```text
judgment presence
judgment completeness
judgment quality
```

### Presence

A required judgment has a durable attributable record.

### Completeness

The engine must enforce the structural prerequisites for the judgment.

The existing review path already makes Blocker/Major findings required and prevents a passing review from carrying unresolved required findings. F15 should not duplicate that rule.

The extension needed for the simplified interface is:

> **Any finding or observation that policy marks `requires_disposition`, including F17 consequential observations regardless of ordinary severity label, must have a durable disposition before the evidence can satisfy the next gate.**

A low-severity label must not make a consequential observation disappear.

`noted` may be a valid disposition for genuinely advisory information, but it is not sufficient for an observation that carries an F17/open-consequence obligation.

### Quality

Whether the Lead genuinely understood the evidence cannot be proven mechanically.

Therefore:

> **Judgment-capture rate is necessary but weak evidence.**

`anomaly-catch rate` is the primary behavioral gate for whether the simplified interface is degrading Lead attention.

---

## 7. Stages are normally non-blocking

A stage command does not wait across a future judgment-bearing event.

Example:

```text
ticket request-review T
    ↓
resolve review policy
create + launch reviewers
record durable stage result
RETURN
```

Later:

```text
review finishes
    ↓
status / resume / ActionProjection
    ↓
decision_required:
    ACCEPT_REVIEW_EVIDENCE
    evidence = E42
    disposition_required = [...]
```

After the Lead supplies the judgment:

```text
ticket request-verification T --review-evidence E42
```

AEW can perform the policy-determined mechanics that follow.

---

## 8. Policy resolution and policy drift

A stage records the policy under which it expanded:

```text
policy_digest
effective_obligations_digest
resolved role/profile/isolation/capabilities/budget
overrides
```

If the effective policy digest changes while a stage bundle is active:

```text
STOP
→ STALE_POLICY
→ report completed substeps
→ do not continue under mixed policy
```

Accepted evidence records the policy/effective-obligation context under which it was produced and accepted.

A later policy change does not erase history, but current admissibility is recomputed:

```text
policy changed
    ↓
current obligations recomputed
    ↓
earlier evidence still satisfies them?
      YES → may remain admissible
      NO  → gate becomes unmet
```

No old `ALLOW` is inherited merely because evidence bytes are unchanged.

---

## 9. Durable stage-intent journal

Before its first primitive mutation, a stage writes a durable intent record:

```text
StageIntent {
    stage_id
    requested_action
    caller
    authority_generation
    input_revision
    explicit_judgment_inputs
    policy_digest
    obligations_digest
    primitive_expansion
    idempotency_keys
    completed_steps
    state
    started_at
}
```

Terminal states:

```text
COMPLETED
STOPPED_AT_BOUNDARY
REFUSED
ABANDONED
```

Nonterminal:

```text
ACTIVE
```

`STOPPED_AT_BOUNDARY` means all permitted mechanical/policy-resolved work completed and the next required action is judgment-bearing.

`ABANDONED` is explicit; inactivity never silently abandons a stage.

The journal is operation metadata, not a new Ticket lifecycle.

Every intermediate workflow state remains a legal primitive-reachable state.

---

## 10. ADR-0011 treatment from the start

Stage intents and anomaly records are history-growing records. They must not recreate the history-sized hot-state problem ADR-0011 was introduced to remove.

### Stage intents

```text
ACTIVE / unresolved stage intent
    → hot state

terminal StageIntent
    → immutable cold record

hot projection
    → bounded current pointer/count/recent summary only
```

Normal `resume` reads active/current stage state, not all historical stage intents.

Historical stage retrieval is explicit and does not make old intent authoritative.

### Anomalies

```text
high-severity unresolved anomaly / F17 obligation
    → bounded current obligation in hot state

resolved anomaly
    → immutable cold evidence/history

low-severity advisory anomaly
    → cold event + bounded recent/current projection as needed
```

Detector definitions and current baseline/configuration references remain bounded current metadata; historical detector/baseline versions are cold immutable records.

Archival follows ADR-0011's existing rule: retention does not imply normal-path residency or replay.

---

## 11. Crash, resume and Lead takeover

`resume` surfaces dangling stage intents:

```text
stage_id
original caller/generation
completed primitive steps
last durable revision
current policy status
current guard status
safe_to_continue
next unresolved boundary
```

A replacement Lead never silently inherits an old stage execution.

It explicitly chooses:

```text
CONTINUE_STAGE
ABANDON_STAGE
```

Continuation:

- binds to the new Lead generation;
- rechecks current guards;
- rechecks policy/admissibility;
- never reuses an old `ALLOW`;
- preserves already-completed durable primitive work rather than replaying it.

---

## 12. One source of truth for legality

These must derive from the same guard implementation:

```text
execution
--explain / dry-run
refusals
status
resume
ActionProjection
TUI / future web UI
M5 scheduler decisions
```

Conceptually:

```text
queryable guards
      ↓
ActionProjection
      ├─ stage execution
      ├─ --explain
      ├─ status/resume
      ├─ TUI/web
      └─ scheduler
```

`--explain` asks the real engine to expand and dry-run a stage.

It is not a second hand-written model of legality.

---

## 13. Step 0 is real work: queryable guards

The current engine has many Lead operations whose guards are checked inline with their mutations.

Making every guard globally side-effect-free in one refactor would be a major project and should not be hidden inside "add ActionProjection."

The decision is:

> **F15 does not require all existing Lead operations to be refactored before M4 can build its queue engine.**

Instead:

### Shared foundation

M4 already begins with `DispatchDecision`.

Treat that as the first queryable-guard substrate rather than building a separate F15 guard system.

The common guard API must support:

```text
query / dry-run
execution-time reuse
durable reason codes
revision/generation/policy binding
no side effects during query
```

### Incremental migration

Only primitives used by a stage/action need full queryable `PrimitiveSpec` support before that stage is enabled.

Unmigrated primitives:

- remain available through the advanced/recovery interface;
- default to judgment-bearing for stage-expansion purposes;
- are not silently approximated in `ActionProjection`.

The full public operation set can migrate incrementally.

For each migrated operation:

```text
dry-run guard result == execution-time guard result
for the same revision/generation/policy
```

The unchanged M1–M3 acceptance, regression and adversarial suites are the safety net.

---

## 14. Explicit M4/F15 ordering decision

F15 should not become an accidental all-or-nothing prerequisite for M4 concurrency.

Recommended sequencing:

```text
ADR-0011
    ↓
Shared M4/F15 foundation:
    queryable DispatchDecision / guard substrate
    durable reason codes
    initial PrimitiveSpec mechanism
    ↓
M4 core queue engine through primitive interface:
    queue records
    serial integration lease
    recovery/reconciliation
    current-head binding
    no-head-of-line-blocking semantics
    ↓
F15 stage foundation:
    ActionProjection
    stage-intent journal
    primitive declarations for staged operations
    ↓
F15 Lead-path proof:
    draft/start/request-review
    request-verification
    submit-integration
    paired/adversarial evaluation
    ↓
M4 normal queue UX:
    integrate next / queue stage surface
    ↓
M4 dogfood
    ↓
M5 scheduler later consumes the same action layer
```

This means:

- M4 engine semantics do not wait for all ~41 Lead operations to be refactored.
- The **normal M4 Lead UX** does wait for the F15 action/stage abstraction to be proven.
- M4 does not invent a separate queue-action abstraction that M5 would later replace.

---

## 15. Action projection and steering policy

A singular `next_action` is too strong.

Use:

```text
ActionProjection {
    revision
    mechanical_actions[]
    decisions_required[]
    blockers[]
    anomalies[]
}
```

Mechanical/policy-resolved actions may be marked:

```text
auto_runnable: true
```

only when current guards and policy fully determine them.

Judgment-bearing actions have:

```text
decision_required: true
default: NONE
```

No automatic default for:

```text
publish
accept evidence
classify failure
waive gate
risk downgrade
resolve conflict
accepted_open
material hierarchy change
stakeholder-owned choice
```

An action can nevertheless carry a previously recorded **conditional authorization**, described below.

---

## 16. Event-driven safety mechanics are not stage work

Safety-relevant authority mechanics cannot wait for a Lead command.

Examples:

```text
run ends
→ revoke invocation credential immediately

authority generation changes
→ revoke superseded authority immediately

integration custodian dies
→ revoke custodian authority immediately
→ mark reconciliation required
→ release/transfer the queue-entry lease only after invariants prove it safe
```

A timeout alone never releases a load-bearing lease.

These reactions belong in the engine/supervisor event path.

---

## 17. M4 publication without holding the queue behind Lead latency

M4's serial integration lease creates a special problem:

```text
prepare
→ integration validation
→ Lead judgment
→ publish
```

If the lease is held while waiting for a Lead/model response, every runnable Ticket behind it stalls.

Releasing the lease before publication allows the authoritative head to move and makes the validated candidate stale.

### Decision: support explicit conditional publication authorization

The publish primitive remains `JUDGMENT_BEARING`.

However, the Lead may provide its publish judgment **up front**, as a durable conditional authorization:

```text
PUBLISH_IF_CLEAN_VALIDATION
```

Conceptually:

```text
ticket submit-integration T \
    --verification-evidence E77 \
    --publish-if-clean
```

or an equivalent explicit later queue action.

This means:

> "I authorize publication of the candidate produced for this exact Ticket proposition if, and only if, the complete current integration policy is satisfied and no new judgment-bearing result appears."

The authorization is bound to at least:

```text
Ticket revision
commit_ready_seq
queue entry
accepted plan / assurance bindings
policy digest / effective obligations
Lead generation
authorization conditions
```

At lease acquisition the actual attempt additionally binds to current authoritative H and candidate M.

### Clean-validation predicate

The conditional authorization can be exercised only if:

```text
current DispatchDecision still allows the work
AND policy/effective obligations are unchanged
AND the authoritative head still matches H
AND every required integration check passes
AND no required finding remains
AND no finding/observation marked requires_disposition appears
AND no high-severity anomaly / F17 obligation appears
AND no override, waiver, conflict or unexpected policy branch is required
```

Then AEW may immediately execute the already-authorized publish CAS while the same queue entry still holds the lease.

### If clean conditions are not met

The authorization is **not** exercised.

AEW does not hold the serial lease across open-ended Lead think time.

Instead it:

```text
records the evidence / anomaly / finding
safely retires or parks the current integration attempt as policy requires
releases the lease after reconciliation proves release safe
moves the queue entry to AWAITING_DISPOSITION
allows independent runnable entries to continue
```

When the Lead later resolves the issue, the Ticket re-enters the integration path and is revalidated against the then-current head.

This preserves:

- explicit publication authority;
- no hidden judgment;
- no queue-wide stall on ordinary Lead response latency;
- exact-head validation before publication.

The conditional-authorization path itself must be evaluated in M4 dogfood. It is not permission to auto-publish after any generic "pass."

---

## 18. Cross-document obligations

### F17 / consequential observations

Anything policy marks `requires_disposition`, including F17 consequential observations, appears in:

```text
blocking_conditions
```

and can block review acceptance, verification progression, `submit-integration`, or conditional publish.

A low severity label never silently clears a consequential obligation.

### Free-text ingress

All operator/Lead authored text enters as data, never through shell interpolation.

### Decomposition

"Break this objective down as needed" grants authority to propose decomposition inside the approved envelope.

It does not silently create new stakeholder meaning or acceptance authority.

---

## 19. Anomalies are durable, not ephemeral UI

A stage result records which anomalies were shown:

```text
Anomaly {
    detector_id
    severity
    evidence_refs
    baseline_id
    baseline_version_or_digest
    observed_value
    expected_range_or_rule
    shown_to
    shown_at
}
```

High-severity anomalies route through the existing F17/open-observation obligation mechanism.

Lower-severity anomalies remain durable advisory signals.

A detector must define its baseline source and comparability rule.

For a timing anomaly, for example:

```text
project / role / profile cohort
sample count
time window
baseline version/digest
threshold method
```

With insufficient comparable history, the detector abstains rather than generating noise.

---

## 20. Equivalence and mixed-mode testing

The stage layer must prove it is only a safer façade.

### Equivalence

For the same starting state:

```text
stage action
```

must produce the same authoritative durable result as:

```text
the documented primitive sequence
```

### Mixed-mode walks

Seeded state-machine walks interleave:

```text
stage
primitive
stage
primitive
```

including a primitive issued after a crash and before stage continuation.

### Primitive classification

A stage cannot use a primitive lacking a complete `PrimitiveSpec`.

### Policy drift

Seed policy changes between stage expansion and each substep.

### Cold-history behavior

Large completed StageIntent/anomaly histories must not increase normal `status`, `resume`, dispatch, or stage latency beyond ADR-0011's bounded-hot-state expectations.

---

## 21. Success gates vs reported metrics

Cost optimization cannot mask correctness regression.

### Hard gates

1. **False advances:** no stage crosses a required judgment or guard boundary in the seeded/conformance corpus.
2. **Judgment capture:** every consequential judgment has an attributable durable decision before the consequential transition. Necessary, but not proof of quality.
3. **Anomaly catch:** Leads under stage UX catch seeded high-severity anomalies at least as well as the primitive-path baseline. This is the primary behavioral attention gate.
4. **Recovery correctness:** crash/retry/takeover/mixed-mode cases preserve authority, idempotency, evidence binding and legal state.

Additional conformance prerequisites:

```text
stage/primitive equivalence
query/execute guard equivalence for migrated operations
PrimitiveSpec coverage for every staged primitive
ADR-0011 bounded-hot-state behavior
```

### Reported-only optimization metrics

Report, but never trade the gates away for:

```text
Lead steps
operator actions
refusal/help/status churn
Lead token cost
total token cost
wall-clock
time to consequential decision
queue wait
```

---

## 22. Working principles

> **Humans and models provide intent, judgment, evidence, and explicit overrides. AEW performs mechanics and policy resolution already determined by durable state.**

> **A stage command never crosses an unresolved judgment boundary.**

> **A judgment record is necessary, but structural completeness and behavioral anomaly detection keep it from becoming ceremony.**

> **Safety-relevant authority reactions happen on the event, not when the Lead happens to issue the next command.**

> **M4 and F15 share one queryable guard/action substrate; neither gets a parallel definition of legality.**

> **Keep the primitives as the conformance and recovery surface. Stop making them the normal UX.**
