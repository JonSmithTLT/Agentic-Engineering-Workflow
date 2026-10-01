# AEW Hierarchy Intent Revision and Replanning Design v0.1

**Status:** Proposed design  
**Scope:** Goal/intent changes across Epic, Story, and Ticket hierarchy; Lead authority; stakeholder approval; evidence preservation; replanning; supersession  
**Motivation:** Live M3 verification exposed a case where the stored Ticket goal was malformed before becoming authoritative state. AEW correctly detected the contradiction during verification, classified it as a plan/design defect, and ultimately had to cancel and recreate the Ticket because the already-bound acceptance goal could not safely be edited.
**Review integration:** 2026-09-28 companion-design review incorporated. This revision adopts fail-closed change classification, approved-baseline comparison for cumulative drift, relationship-based supersession, explicit verification-classification authority, and immediate intent-ingress hardening.

## 1. Purpose

AEW needs a supported way for project intent to evolve without corrupting the meaning of existing evidence.

Real engineering work changes as:

- research produces new information;
- requirements are clarified;
- operator intent changes;
- implementation exposes previously unknown constraints;
- verification detects a defect in the plan or acceptance goal;
- upstream work invalidates downstream assumptions.

The system must avoid two opposite failures:

```text
everything is immutable forever
→ bureaucracy, needless cancellation/recreation, lost continuity

everything is editable in place
→ evidence meaning changes underneath completed work
```

This design introduces **hierarchy-sensitive intent mutability**.

The guiding rule is:

> **Parents preserve purpose. Tickets preserve proof.**

Higher-level work units are expected to absorb changing understanding.

Tickets are bounded execution contracts against which implementation, review, verification, and evidence are produced.

## 2. Semantic role of each hierarchy level

### Epic

An Epic represents a major stakeholder outcome or intent envelope.

Examples:

```text
Improve upload reliability.
Reduce crash-triage time.
Add resumable artifact transfer.
```

An Epic should survive substantial changes in implementation understanding.

The Epic's purpose should be comparatively stable, but its framing may evolve as research and execution reveal better approaches.

### Story

A Story represents a coherent problem slice, approach, or capability area within an Epic.

Examples:

```text
Implement restart-safe upload sessions.
Evaluate allocator-state signatures for crash deduplication.
Preserve backward compatibility for existing clients.
```

Stories are expected to evolve more frequently than Epics because research, architecture discovery, and implementation often refine the correct approach.

### Ticket

A Ticket represents a bounded execution contract.

It should define work tightly enough that:

- implementation evidence can be bound to it;
- review can evaluate it;
- verification can prove or disprove its acceptance goal;
- dependencies can rely on its meaning;
- retries/rework remain about the same proposition.

Once authoritative work begins against a Ticket, material changes to its acceptance meaning are dangerous.

## 3. Core principle

```text
higher hierarchy
= preserve purpose while allowing understanding to evolve

lower hierarchy
= preserve the proposition that evidence claims to prove
```

Or more compactly:

> **Parents preserve purpose. Tickets preserve proof.**

This is why a Story may legitimately change more than an active Ticket even though the Story has a larger organizational blast radius.

## 4. Change classes

Intent changes are classified semantically, but classification is fail-closed.

Cross-cutting rule:

> When an actor classifies a situation into categories with different ceremony, the heavier category is the default. Downgrading requires recorded justification reviewable by someone other than the classifier.

### 4.1 EDITORIAL

Permitted only when semantic non-change is mechanically verifiable.

Examples:

- whitespace/formatting;
- punctuation that cannot change parsing/meaning;
- spelling correction where the acceptance-bearing token/value set is otherwise identical.

If semantics could plausibly change, the change is not EDITORIAL.

### 4.2 CLARIFICATION

The wording becomes more explicit while the acceptance meaning remains unchanged.

After authoritative evidence is bound to an acceptance-bearing field, **CLARIFICATION is a downgrade from the MATERIAL default** and requires:

1. recorded justification explaining why acceptance meaning is unchanged; and
2. confirmation by a fresh-context Reviewer or Verifier independent of the Lead/classifier.

Existing evidence remains admissible only if that confirmation supports unchanged meaning and normal freshness rules still hold.

### 4.3 MATERIAL

Any change to an acceptance-bearing field after evidence is bound is **MATERIAL by default**.

Examples:

```text
state may be ephemeral
→
state must survive restart

safe_div(7, 2) == 3
→
safe_div(7, 2) == 3.5
```

Expected behavior:

- impact analysis;
- plan/evidence invalidation as appropriate;
- stakeholder approval when the change represents consequential intent;
- active Ticket replacement/supersession when existing evidence would change meaning.

### 4.4 STRUCTURAL / SCOPE

The organization of work or the approach changes materially while higher-level purpose remains recognizable.

Examples:

- split one Story into two;
- merge overlapping Stories;
- replace an abandoned Story approach with a newly discovered one;
- add/remove planned Tickets based on research;
- broaden a Story because a discovered root cause spans two previously separate areas.

Expected behavior:

- Lead-owned impact analysis;
- descendant replan/restructure;
- preserve valid completed evidence;
- stakeholder approval only when the change leaves the approved execution envelope or changes stakeholder-owned intent.

## 5. Authority model

The Lead must be able to **discover**, **propose**, and, within bounded authority, **apply** hierarchy revisions.

The Lead does not receive unrestricted authority to rewrite project history.

The model is:

```text
Lead discovers need for change
        ↓
classifies change
        ↓
impact analysis
        ↓
if within delegated envelope:
    revise/restructure through AEW authority
else:
    request stakeholder approval
        ↓
AEW applies revision/supersession
        ↓
affected plans/evidence/contexts invalidated or refreshed
```

The Lead's authority grows with abstraction only in the sense that higher-level work is designed to evolve.

It does **not** mean the Lead may silently change stakeholder intent.

The Lead may propose and authoritatively apply classifications only through the governing AEW path. Where choosing a lighter class reduces ceremony, the cross-cutting fail-closed classification invariant applies: uncertain cases take the heavier path, and a downgrade requires independently reviewable justification.

## 6. Epic revision semantics

Epics are the closest hierarchy object to stakeholder intent.

### Lead may ordinarily

- reframe an Epic to incorporate discovered implementation structure;
- refine wording;
- add derived sub-objectives that remain inside the approved outcome;
- restructure Stories beneath the Epic;
- propose material changes.

### Stakeholder approval is required when

- the Epic's outcome materially changes;
- externally visible product intent changes;
- compatibility commitments change;
- major scope/cost changes;
- a prior stakeholder decision is overturned;
- the new Epic meaning would reasonably be considered a different objective.

### Example — Lead-owned refinement

Original:

```text
Improve parser reliability.
```

After investigation:

```text
Improve parser reliability by addressing retry, cleanup, and reconnect paths
that share the same lifecycle defect.
```

If this remains inside the approved objective, the Lead may apply the refinement and report it.

### Example — stakeholder-required change

Original:

```text
Improve upload reliability.
```

Proposed:

```text
Replace the upload system with a new transfer protocol.
```

This is not merely a refinement. It requires stakeholder approval.

## 7. Story revision semantics

Stories are intentionally adaptable.

Research and implementation can materially change the best framing of a Story without changing the Epic's purpose.

The Lead should have substantial authority to:

- revise Story framing;
- broaden or narrow a Story;
- split a Story;
- merge overlapping Stories;
- replace a Story approach;
- add/remove planned Stories;
- restructure descendant Tickets;
- replan descendants after research findings.

This authority is bounded by:

- the current Epic's approved intent;
- accepted stakeholder decisions;
- governing contracts;
- scope/cost policy;
- deterministic AEW authority.

### Example — research-driven Story revision

Original Story:

```text
Evaluate runtime provenance for crash deduplication.
```

Research finds:

```text
Runtime provenance is unstable.
Allocator-state signatures are significantly more discriminating.
```

The Lead may propose or apply, depending on execution-envelope impact:

```text
Evaluate crash-deduplication signatures, prioritizing allocator-state
signatures while retaining runtime provenance as a comparison.
```

Impact analysis may conclude:

```text
T-1 completed research remains valid.
T-2 requires replanning.
T-3 remains useful but needs new inputs.
```

Replacing the entire Story and reconstructing all history would be wasteful.

The revised Story should preserve lineage.

## 8. Ticket revision semantics

Tickets are deliberately stricter.

Once implementation/review/evidence is bound to a Ticket, material changes to its acceptance meaning should not be edited in place.

### Before execution begins

If the Ticket has:

- no invocation;
- no authoritative evidence;
- no review;
- no verification;
- no downstream reliance;

then an authorized Ticket goal revision may be permitted.

The revision should still be recorded.

### After execution begins

Apply the following rule:

> **No Ticket goal change may silently preserve evidence whose meaning depended on the previous goal.**

For any acceptance-bearing field with bound evidence, the default classification is **MATERIAL**.

#### EDITORIAL

Allowed only when semantic non-change is mechanically verifiable.

#### CLARIFICATION

Allowed only after:

- the Lead records why acceptance meaning is unchanged; and
- a fresh-context Reviewer or Verifier independently confirms that bound evidence still proves the same proposition.

If either condition is missing or uncertain, treat the change as MATERIAL.

#### MATERIAL

Do not overwrite the goal in place.

Preferred behavior:

```text
old Ticket
→ existing terminal state (normally CANCELLED with a supersession reason)
→ supersession relationship to replacement Ticket
→ replacement Ticket with corrected goal
```

Existing evidence remains attached to the old Ticket and remains historically valid where appropriate.

The replacement Ticket receives fresh admissible evidence.

### Why Ticket replacement is acceptable

Tickets are intentionally scoped and bounded.

Their identity is closely tied to the work and acceptance proposition.

Replacing a Ticket is comparatively cheap and preserves evidentiary clarity.

Replacing a large Story or Epic solely because understanding evolved can be disproportionately wasteful.

## 9. Ticket supersession lineage

Supersession is a **relationship layered on existing lifecycle states**, not a new lifecycle state.

Example:

```text
T-17
state: CANCELLED
terminal_reason: GOAL_SUPERSEDED
superseded_by: T-18
```

T-18 may record:

```text
supersedes: T-17
reason:
  Correct literal currency acceptance goal.
```

The exact terminal-reason vocabulary is not frozen here.

The invariants are:

- replacement work preserves why it exists and what it supersedes;
- supersession does not erase the old Ticket/evidence;
- gates for the replacement do not silently accept evidence whose meaning was bound to the old proposition;
- parent closeout requires an explicit disposition for every superseded descendant so lineage cannot remain dangling.

## 10. The malformed-goal verification case

A live M3 scenario exposed the following sequence:

```text
operator intent
    ↓
shell interpolation altered literal goal text
    ↓
malformed goal stored authoritatively
    ↓
implementation matched direct observation
    ↓
review passed
    ↓
verification identified contradiction
    ↓
VERIFICATION_FAILED
    ↓
PLAN_OR_DESIGN_DEFECT
    ↓
REPLAN_REQUIRED
    ↓
existing Ticket could not safely be repaired
    ↓
CANCELLED / recreate
```

This demonstrates two separate requirements.

### 10.1 Intent ingress integrity

Free-form stakeholder/agent-authored semantics must enter AEW as **opaque data**, not shell-interpreted syntax.

This is an immediate hardening requirement, not deferred future design.

Canonical machine/Lead ingress should use one of:

- structured bridge/API payloads;
- stdin;
- file payloads;
- direct argv arrays where no shell evaluates authored text.

Authored semantics must **never** be constructed into an interpolated shell command string.

This applies to at least:

- goals;
- acceptance criteria;
- stakeholder decisions;
- review/verification text fields;
- agent-produced structured semantic fields.

Required regression corpus includes literal values containing:

```text
$5.00
$(echo nope)
`literal`
*
?
&
;
single and double quotes
backslashes / Windows paths
multiline text
Unicode
```

Tests must assert value/byte preservation into authoritative state across supported execution environments.

Supersession is the recovery path after bad intent was stored. Ingress integrity is prevention and must be fixed independently.

### 10.2 Supported goal revision/supersession

When AEW detects that authoritative intent itself is wrong, the system needs a first-class recovery path rather than ad hoc manual reconstruction.

## 11. Verification's role

Review and verification intentionally answer different questions.

A reviewer primarily evaluates whether the implementation is sound relative to the plan, code, contracts, and review scope.

Verification asks whether the delivered state actually satisfies the required acceptance conditions.

Therefore verification may discover:

- implementation defects;
- environment defects;
- stale evidence;
- plan defects;
- malformed acceptance goals;
- contradictions between implementation reality and stored intent.

A review pass must not prevent verification from classifying the goal or plan itself as defective.

This is a primary reason AEW retains an independent verifier.

### 11.1 Verification failure classification authority

The Verifier **reports the failure, evidence, and may propose a classification**.

The Lead makes the authoritative workflow classification through the normal AEW control path.

This preserves the role boundary that the Verifier reports rather than mutating project state.

Fail-closed rule:

- if evidence supports a plan/design/contract defect, or the classification is uncertain, default to the heavier `REPLAN_REQUIRED` path;
- the Lead may not downgrade a verifier-raised design/contract concern to a local implementation defect solely to obtain cheaper rework;
- a downgrade requires recorded justification and independent fresh-context confirmation that the failure is local and that the governing goal/plan remains valid.

This authority model should be reconciled with the Workflow Contract and current `verify classify` implementation before the behavior is frozen.

## 12. Goal change impact analysis

Any non-editorial hierarchy revision should consider:

```text
Does this invalidate the current plan?
Does this invalidate context packs?
Does this invalidate implementation evidence?
Does this invalidate review evidence?
Does this invalidate verification evidence?
Does this affect dependencies?
Does this affect descendants?
Does this affect parent closeout?
Does this contradict stakeholder decisions?
Does this require active workers to be held/interrupted?
```

Impact should be derived and recorded rather than left implicit.

## 13. Evidence preservation

Revision must not discard provenance merely because some evidence is no longer current.

AEW should distinguish:

```text
historically valid evidence
vs
currently admissible evidence
```

This distinction is load-bearing enough to become a first-class Knowledge Contract concept. The exact schema is not frozen here, but gate evaluation must be able to determine current admissibility without deleting or falsifying historically valid evidence.

Example:

```text
Story S-4 v1
research evidence E-10
```

may remain historically valid after Story S-4 v2 supersedes its framing.

However, if the revised Story changes the proposition E-10 is supposed to support, E-10 must not silently satisfy current gates.

Likewise, Ticket evidence from a superseded Ticket remains part of history but does not satisfy the replacement Ticket's gates unless an explicit safe reuse rule says otherwise.

## 14. Active work during hierarchy revision

When an Epic or Story revision affects active work, the Lead should classify each descendant:

```text
UNCHANGED
current work remains valid

CONTEXT_UPDATE
work remains valid but new information must be propagated

REPLAN
objective remains but approach/plan is stale

HOLD
work must pause pending a decision

SUPERSEDE
current Ticket proposition is no longer the work that should be performed
```

The exact labels are not frozen.

The requirement is explicit impact classification.

## 15. Stakeholder interaction

The desired UX is concise.

Example:

```text
Lead> Standup 7 surfaced a material research result.

      Original Story:
      Evaluate runtime provenance for deduplication.

      Finding:
      Runtime provenance is unstable; allocator-state signatures are
      materially more useful and still satisfy the Epic's objective.

      Proposed change:
      Refocus S-4 on allocator-state signatures, retaining runtime
      provenance as a comparison.

      Impact:
      - T-21 remains valid.
      - T-22 requires replanning.
      - T-23 remains useful with changed inputs.
      - No external behavior or approved Epic intent changes.

      I can apply this within the current execution envelope.
      Proceed, or tell me what you want changed.
```

For a stakeholder-owned objective change:

```text
Lead> This would change the approved Epic outcome rather than merely
      refine the approach. I need your approval before proceeding.
```

The operator should not need to manually recreate hierarchy objects when the Lead can safely preserve lineage and restructure work.

## 16. Research-specific behavior

Research exists partly to change what AEW believes it should do.

Therefore:

> **Research findings must be capable of changing the plan structure they were commissioned to inform.**

A system that commissions research but cannot revise Stories/Epics in response to the findings is structurally broken.

Research may lead to:

- revised Story framing;
- abandoned approaches;
- new Stories;
- merged Stories;
- changed Ticket decomposition;
- additional investigation;
- reduced scope;
- broader scope within approved intent.

The Lead is responsible for turning findings into explicit impact/replan decisions.

## 17. Authority boundaries

### Lead

May:

- identify required hierarchy changes;
- classify changes;
- perform impact analysis;
- revise/restructure within delegated authority;
- propose stakeholder-owned changes;
- apply approved changes through AEW.

May not:

- silently rewrite stakeholder intent;
- rewrite active Ticket acceptance goals so old evidence changes meaning;
- preserve stale evidence as current merely because revision is convenient;
- bypass governing contracts.

### Stakeholder

Owns consequential product/intent decisions.

May approve, reject, or redirect material Epic/Story changes.

Stakeholder approval does not itself mutate AEW state; normal AEW authority paths perform the change.

### AEW

Owns:

- allowed transitions;
- revision/supersession mechanics;
- evidence invalidation;
- lineage;
- dependency impact;
- plan freshness;
- authority enforcement.

## 18. Relationship to approved execution envelope

A hierarchy revision inside the approved execution envelope may proceed under Lead authority.

A change exits the envelope when it materially changes:

- stakeholder outcome;
- external behavior;
- compatibility;
- security/reliability commitment;
- major scope/cost;
- explicit stakeholder decision.

Those changes require stakeholder involvement.

The same mechanism therefore supports both autonomy and control.

### 18.1 Cumulative revision drift

An Epic/Story revision is not evaluated only against the immediately previous revision.

Every revision retains the **approved execution-envelope baseline** that authorized the work.

Impact analysis compares:

```text
proposed current revision
vs
originally/currently approved baseline
```

as well as the immediately preceding revision.

This prevents a sequence of individually small "in-envelope" changes from walking the work materially outside what the stakeholder approved.

Checkpoints should surface cumulative divergence when it becomes meaningful, even if no single revision crossed the approval threshold by itself.

## 19. Failure classes

Canonical definitions live in `failure-class-registry.md`.

This document owns or primarily motivates:

```text
INTENT_INGRESS_CORRUPTION
SILENT_INTENT_REWRITE
EVIDENCE_MEANING_DRIFT
EXCESSIVE_HIERARCHY_RECREATION
MISSED_REPLAN
UNAUTHORIZED_SCOPE_CHANGE
LOST_SUPERSESSION_LINEAGE
STALE_PARENT_INTENT
```

Use the registry rather than redefining these classes in downstream documents.

## 20. Acceptance/evaluation scenarios

### Scenario A — malformed active Ticket goal

Given:

- Ticket execution has started;
- goal is discovered to contain corrupted acceptance semantics;
- implementation/review evidence exists.

Expected:

- no in-place material goal rewrite;
- existing evidence preserved historically;
- Ticket superseded/cancelled;
- replacement Ticket linked;
- corrected goal receives fresh evidence.

### Scenario B — research changes Story approach

Given:

- research finds the planned approach is poor;
- Epic purpose remains unchanged;
- some descendant work remains valid.

Expected:

- Lead revises/restructures Story;
- valid completed evidence retained;
- only impacted descendants replan;
- no mandatory recreate-the-world ceremony.

### Scenario C — Story broadens within Epic

Given:

- discovered root cause spans retry and reconnect;
- Story originally covers retry;
- Epic already authorizes parser reliability work.

Expected:

- Lead may broaden/reframe Story inside the envelope;
- impact is surfaced;
- affected Tickets updated/replanned.

### Scenario D — Epic objective actually changes

Given:

- original Epic is "improve upload reliability";
- proposed change is "replace the transfer protocol".

Expected:

- Lead identifies stakeholder-owned objective change;
- asks for approval;
- no silent Epic rewrite.

### Scenario E — editorial Ticket correction

Given:

- no semantic change;
- evidence exists.

Expected:

- safe revision permitted if provenance remains clear;
- evidence remains current only because acceptance meaning is unchanged.

### Scenario F — cumulative in-envelope drift

Given:

- several Story revisions are each small relative to the previous revision;
- their cumulative result differs materially from the stakeholder-approved baseline.

Expected:

- AEW compares the proposed revision to the approved baseline;
- cumulative divergence is surfaced;
- stakeholder approval is required when the baseline envelope is crossed.

### Scenario G — authored-text ingress preservation

Given authored semantic fields containing shell-significant characters and multiline text.

Expected:

- canonical ingress treats the text as opaque data;
- authoritative stored values match the submitted values;
- no shell interpolation/globbing/substitution occurs.

### Scenario H — verifier classification downgrade

Given:

- Verifier evidence indicates a plan/design defect;
- Lead proposes LOCAL_IMPLEMENTATION_DEFECT.

Expected:

- downgrade is refused without recorded justification and independent fresh-context confirmation;
- uncertainty defaults to REPLAN_REQUIRED.

## 21. Open questions

The following require implementation/design review before freezing:

1. Should Epic/Story revisions create explicit version numbers or immutable revision records?
2. Which exact existing terminal states/reasons may carry the supersession relationship? (`SUPERSEDED` itself is not a lifecycle state.)
3. Which Ticket changes are allowed before first invocation?
4. What deterministic checks, beyond independent fresh-context confirmation, are sufficient to prove a clarification leaves acceptance meaning unchanged?
5. Can some evidence be explicitly rebound after parent Story/Epic revision, or should relevance be recomputed through existing freshness rules?
6. How should ancestor-plan binding react to Story/Epic revisions?
7. How do dependency edges behave when Stories split/merge?
8. What representation records required explicit disposition of every superseded descendant at parent closeout?
9. What exact Lead authority exists for Story restructuring without stakeholder approval?
10. Should material Epic changes always require explicit approval, or can pre-approved envelopes authorize some classes?
11. How should hierarchy revisions appear in resume/status/operator summaries?
12. How are revisions represented in the Knowledge Contract and control-state schema?

## 22. Likely contract impact

This design probably requires review against:

- Workflow Contract;
- hierarchy state semantics;
- ancestor-plan binding;
- dependency semantics;
- evidence freshness and current admissibility;
- review/verification binding and verification-failure classification authority;
- authored-text/intent ingress;
- moves/promotions;
- parent closeout;
- resume/status/context reconstruction.

This should not be implemented as a UI-only feature.

The central semantics belong in AEW's deterministic control plane.

## 23. Non-goals

This design does not:

- allow arbitrary in-place mutation of goals;
- make all hierarchy objects freely editable;
- discard old evidence;
- let stakeholder chat directly mutate authoritative state;
- require a new Epic/Story for every discovery;
- require stakeholder approval for every Story refinement;
- weaken Ticket evidence binding;
- replace normal rework when the Ticket's goal itself is still correct.

## 24. Summary

AEW should not treat every hierarchy level as equally immutable.

The intended model is:

```text
Epic
= durable stakeholder purpose
= adaptable framing

Story
= evolving problem/approach slice
= deliberately responsive to research and discovery

Ticket
= bounded execution proposition
= comparatively rigid once evidence is produced
```

The Lead should have meaningful authority to revise and restructure Epics/Stories inside the approved stakeholder intent envelope.

Material Ticket goal changes should generally use supersession/replacement once execution has begun.

The system must preserve provenance, invalidate stale assumptions/evidence, and replan only affected work.

> **Parents preserve purpose. Tickets preserve proof.**


## 25. Cross-document registries

See:

- `failure-class-registry.md`;
- `invariant-index.md`.

The hierarchy-specific implementation must satisfy the cross-cutting fail-closed classification invariant rather than inventing a local lighter-path rule.
