# AEW Workflow / Knowledge Contract Amendment — Ticket Revision Semantics

**Version:** v0.4  
**Status:** Adopted by the operator, 2026-10-06 (the freeze candidate v0.4, after the lead developer's review of v0.3; this line read "Proposed for operator adoption"). Design frozen and implementation-ready (§13).  
**Date:** 2026-10-06  
**Amends:** Workflow Contract v0.7 §7, §8, and invariant 7; Knowledge Contract v0.4 §12  
**Basis:** Adopted Ticket-revision design and designer review of 2026-09-30; T7 effective-spec overlay model v0.2; v0.1-v0.3 review corrections  
**Register:** E19-B  
**Supersedes:** `AEW_E19B_Ticket_Revision_Contract_Amendment_v0.3_FREEZE_CANDIDATE.md`

## 1. Purpose

This amendment makes Ticket revisions part of the governing AEW contract.

The governing principle is:

> **Ticket identity is stable; Ticket wording is not sacred. Revisions preserve useful work while the same bounded engineering objective is being pursued. A revision may not erase adverse history, weaken inherited authority, narrow acceptance to escape proof, or disguise a materially different objective as continuation.**

AEW MUST preserve engineering progress when a bounded correction can be made safely and attributable history can be retained. AEW MUST NOT require cancellation and replacement merely because the original Ticket wording, scope, dependency set, or acceptance expression needs a bounded correction.

At the same time, revision MUST NOT become an escape hatch from review, verification, inherited gates, parent purpose, prior adverse evidence, downstream commitments, or already-bound acceptance.

## 2. Ticket identity and revisions

### 2.1 Stable Ticket identity

A Ticket has one stable Ticket identifier and one or more immutable revisions:

```text
T-17@r1
T-17@r2
T-17@r3
```

The Ticket identifier names the continuing bounded engineering work. Each revision is an immutable acceptance-bearing statement of how AEW is currently pursuing that work.

Exactly one revision is current for a non-terminal Ticket.

Existing Tickets created before implementation of this amendment are treated as revision `r1`.

### 2.2 Revision records are immutable and engine-classified

A committed Ticket revision MUST NOT be edited in place.

A new revision MUST:

- identify the immediately preceding revision;
- record the reason for revision;
- preserve the prior revision unchanged;
- preserve attributable revision history;
- record the changed field groups computed by AEW;
- record the revision-impact determination computed from those groups and current bindings;
- record any required independent confirmation or Lead assertion under §§4–6.

The Lead MAY explain why it believes a field changed or a prior record remains relevant, but AEW MUST NOT trust a Lead-authored declaration of changed groups, digest equality, evidence status, or admissibility as the authoritative determination.

Revision history is part of the Ticket's durable history and MUST remain inspectable after later revisions or Ticket completion.

### 2.3 Every revision-governed input belongs to a governed, versioned field group

Every revision-governed input that can influence model behavior, acceptance, scope, authority, dependency, execution, or review MUST belong to exactly one primary field group in a schema/registry owned by AEW.

"Revision-governed input" includes both:

- fields stored in the immutable Ticket revision record; and
- revision-sensitive canonical control inputs stored elsewhere, including declared dependencies.

Storage location does not remove an input from revision binding.

The registry MUST have a stable schema/version identity or digest. Evidence and revision decisions that depend on field groups MUST bind to that registry identity.

The registry MUST cover at least:

- acceptance / objective;
- scope;
- gate set and effective classification;
- dependencies, regardless of whether they are stored in the Ticket file or control state;
- Ticket kind;
- card / presentation metadata;
- other engine-defined groups required by the Ticket/control schema.

A revision-governed input with no recognized registry assignment MUST fail closed into the broadest acceptance-bearing group. It MUST NOT remain unbound merely because the schema or registry has not yet classified it.

A Lead MUST NOT move a requirement, condition, constraint, or acceptance statement into a nominally descriptive or notes field in order to avoid the acceptance binding.

If a field's semantics permit acceptance-relevant content, the field is acceptance-bearing unless the schema explicitly and mechanically constrains it otherwise.

Card/presentation-only fields, including a Ticket title, are non-material for §4.3 when their schema guarantees that they carry no acceptance, scope, gate, dependency, kind, or check-definition semantics. A title spelling correction therefore does not consume the material-revision checkpoint budget. If acceptance-relevant content is placed in such a field, the fail-closed acceptance-bearing rule applies instead.

If a registry/schema revision moves a field between groups or changes whether a field is acceptance-bearing, AEW MUST conservatively treat the affected field as changed in both its old and new groups for admissibility and impact purposes until current bindings are regenerated.

### 2.4 Digest and change computation

AEW computes field-group digests from canonical content.

Raw authored Ticket text MUST be preserved byte-for-byte as provenance. Digest canonicalization is a separate deterministic projection and MUST be schema-defined.

For ordinary text fields, the v1 canonicalization set is deliberately small:

- normalize `CRLF` and `CR` line endings to `LF`;
- normalize Unicode to NFC;
- remove trailing spaces and tabs at line ends.

No other textual equivalence is implied. In particular, AEW MUST NOT fold case, punctuation, blank lines, interior whitespace, wording, synonyms, or semantic paraphrases.

Fields with a more specific schema rule use that rule. Where a field has no applicable canonicalization rule, its exact stored bytes are the semantic input for change detection.

Any normalization that can cause two distinct authored values to hash identically MUST be explicit, versioned, and covered by conformance tests. Cosmetic or editorial equivalence MUST NOT be inferred by the Lead.

Revision text is authored input. The P2/untrusted-authored-input rules apply: the authored bytes are preserved as data/provenance and MUST NOT gain instruction or authority semantics merely because they are later placed in a context pack or prompt.

### 2.5 Revision is continuation, not replacement

A revision is permitted when the Ticket continues to pursue the same bounded engineering objective.

Typical revision cases include:

- correcting or widening an incorrectly expressed scope while remaining within the parent envelope;
- clarifying acceptance language without changing the underlying objective;
- correcting dependencies;
- incorporating a planning or implementation discovery;
- changing implementation approach;
- correcting a Ticket field whose original value was mistaken or incomplete;
- making another bounded change for which the work remains recognizably the same engineering unit.

A revision MUST NOT be refused merely because work has already begun or useful workspace changes already exist.

## 3. When replacement is required

A new Ticket, rather than a revision, is required when any of the following is true:

1. the work changes kind in a way that changes the governing execution semantics;
2. the work moves to a different parent;
3. the new goal no longer substantially overlaps the previous Ticket objective;
4. the proposed change would require crossing a mechanically enforced parent or policy boundary that revision is not authorized to cross;
5. the prior Ticket is already `DONE` or `CANCELLED`.

A replacement MUST retain the normal supersession / lineage relationship to the prior Ticket where applicable.

A Lead MUST NOT use repeated revisions to avoid creating a replacement when the engineering objective has materially changed.

## 4. Parent envelope, cumulative drift, and authority boundaries

Parents define the approved purpose and inherited obligations. Ticket revisions preserve the history of how AEW pursued that purpose.

### 4.1 Mechanical refusal

AEW MUST mechanically refuse a proposed revision when it can determine that the revision would:

- lower the Ticket below the parent's minimum descendant class;
- remove a mandatory inherited gate;
- violate protected-path / guardrail policy;
- create a dependency cycle;
- revise a `DONE` or `CANCELLED` Ticket;
- revise while a publishing lease is held for the Ticket/integration candidate;
- lower classification without the attributable decision required by the governing classification rules;
- place Ticket scope outside an explicitly machine-checkable parent scope or other mechanically enforced envelope.

Parent scope and requirement coverage SHOULD be represented structurally where practical so that these checks can be mechanical rather than dependent on free-text self-attestation.

### 4.2 Non-mechanical parent alignment

AEW cannot mechanically prove all semantic alignment with the parent objective, stakeholder decisions, governing contracts, commitments, or cost expectations.

For those non-mechanical properties, the revision decision MUST contain an attributable Lead assertion that the revised Ticket remains within the approved parent purpose and governing obligations.

That assertion is inspectable and reviewable. It is not equivalent to mechanical proof and does not override later Plan Assurance, review, verification, or parent closeout judgment.

Independent confirmation of the revision decision is REQUIRED when any of the following is true:

- the Ticket's **effective class** is 2 or higher;
- the acceptance group changes after acceptance-bearing evidence has been bound to the Ticket;
- acceptance changes after a passing review or verification;
- the anti-laundering trigger in §6.2 fires;
- cumulative drift reaches the checkpoint rule in §4.3.

For lower-risk revisions before acceptance-bearing evidence exists, the Lead assertion is sufficient unless another governing rule requires review.

For this amendment, **acceptance-bearing evidence** includes at minimum:

- acceptance reviews;
- acceptance verifications;
- check receipts explicitly mapped to an acceptance criterion;
- other evidence classes that the governing gate/acceptance registry marks as satisfying or supporting an acceptance condition.

A Ticket is not considered "pre-evidence" merely because evidence exists in another store or is awaiting ingestion if AEW has already admitted or received an acceptance-bearing result attributable to that Ticket.

### 4.2.1 Independent confirmation

"Independent confirmation" in this amendment means a fresh-context reviewer/confirming invocation that:

- is not the Lead actor/session that authored or approved the proposed revision;
- is admitted under the applicable review/confirmation policy for the Ticket's effective class;
- receives the **engine-computed revision material first**: the predecessor→proposed diff, the cumulative checkpoint/r1→proposed diff, the parent envelope/coverage obligations, current field-group/registry identity, and the open-adverse set;
- makes and records its initial determination from those materials before receiving the Lead's free-text rationale or persuasive narrative;
- then MAY inspect the Lead rationale and other relevant evidence before finalizing the confirmation record.

The confirmation record MUST state at least whether:

1. the revised Ticket remains the same bounded engineering objective;
2. the parent envelope and required coverage remain satisfied or have explicit follow-up obligations;
3. adverse evidence has been preserved and correctly dispositioned;
4. the revision does not shed gates, narrow acceptance improperly, or hide a materially different objective.

For effective class 2 or higher, the confirmer MUST see the cumulative r1/checkpoint→proposed diff in addition to the latest incremental diff.

Independent confirmation is not an operator/stakeholder checkpoint unless the governing rule explicitly requires the operator/stakeholder.

### 4.3 Cumulative drift

Every material revision MUST be evaluated against:

1. its immediate predecessor;
2. revision `r1` or the most recent operator/stakeholder checkpoint;
3. the current parent envelope.

A sequence of individually small revisions MUST NOT be allowed to walk the Ticket outside the objective originally approved by the parent.

AEW has a built-in default checkpoint threshold:

> **After three material revisions since the last operator/stakeholder checkpoint, another material revision MUST receive an explicit operator/stakeholder checkpoint before it may become current.**

Operator-controlled project policy MAY set a different finite threshold. A Lead or model-controlled actor MUST NOT loosen this threshold.

AEW MUST track the material-revision count since the last checkpoint and surface it before a revision is committed.

For this amendment, a **material revision** is one that changes an acceptance-, scope-, gate/effective-class-, dependency-, kind-, or acceptance-bearing check-definition digest.

A change confined to schema-declared card/presentation metadata is non-material. This includes an ordinary Ticket-title spelling or formatting correction, provided the field remains non-acceptance-bearing under §2.3.

The checkpoint reviewer MUST receive the cumulative checkpoint/r1→proposed engine diff, not only the latest revision delta.

The checkpoint confirms continued identity and parent alignment; it does not waive evidence, findings, gates, or other obligations.

### 4.4 Parent coverage

Any acceptance-group change MUST trigger a parent-coverage recheck.

Where the parent has structured requirement-to-child mappings, AEW MUST recompute whether the parent's required coverage remains satisfied by the current child revisions.

Where coverage is not fully machine-representable, the revision MUST create a visible parent-coverage review obligation rather than silently assuming coverage remains intact.

Parent closeout MUST evaluate coverage against the children's final revisions, not merely their stable Ticket identifiers.

## 5. Revision impact and evidence admissibility

### 5.1 Evidence binds to what it proves

Evidence MUST bind to the Ticket inputs on which its claim depends.

The governing representation is engine-owned field-group digests plus the field-group registry/schema identity and any already-required source, snapshot, plan, check-definition, evaluator, environment, or policy bindings.

A revision number MAY also be recorded as provenance, but a revision number alone MUST NOT force unrelated evidence stale when the evidence's actual bound inputs remain unchanged.

No Ticket field may remain outside the field-group registry described in §2.3.

### 5.2 Admissibility is computed

Evidence records are immutable. Their current admissibility is computed by AEW from authoritative bindings and current governing state.

A revision may cause an existing artifact to become conceptually:

```text
UNCHANGED
REVALIDATE
INVALIDATED
HISTORICAL
SUPERSEDED
```

These are derived states, not mutable labels written back into the evidence record.

A gate MUST NOT be satisfied by evidence whose required bindings no longer match the current Ticket revision unless an allowed revalidation record establishes admissibility under the current revision.

The Lead cannot select or override these statuses.

### 5.3 Revalidation

`REVALIDATE` MUST resolve through a new attributable record, never by rewriting or relabelling the old evidence.

Gate-satisfying evidence may be revalidated only through:

1. **Mechanical revalidation** — AEW proves from authoritative bindings that every input relevant to the evidence claim is unchanged.
2. **Independent fresh-context confirmation** — an authorized independent actor confirms the old claim under the current revision and produces a new record referencing the old evidence.

A Lead MAY record an applicability note for advisory or non-gate-satisfying material, but that note does not make evidence CURRENT, satisfy a gate, dismiss a required finding, or substitute for independent confirmation.

A Lead decision MUST NOT revalidate an acceptance review or acceptance verification whose acceptance-relevant bindings changed.

### 5.4 Workspace carry-forward

Workspace state from a prior revision MAY carry forward as input to the current revision.

**Carry-forward carries work, not proof.**

Implementation work, patches, generated files, or other workspace state may be reused where still applicable, but evidence, review, verification, and gate satisfaction remain subject to the binding and revalidation rules above.

The purpose of this rule is to preserve useful engineering work without pretending that prior proof automatically proves the revised Ticket.

### 5.5 Migration of existing r1 evidence

When existing pre-revision Tickets are migrated to `r1`, existing evidence that lacks field-group bindings MUST be treated conservatively as bound to all Ticket field groups relevant to that evidence class.

A later revision therefore cannot preserve such legacy evidence merely by asserting that the changed field was unrelated. The evidence must be regenerated or revalidated through an allowed path.

Migration MAY enrich bindings only from deterministic facts already present in the canonical record; it MUST NOT infer narrower historical dependencies from model judgment.

## 6. Adverse evidence and anti-laundering rules

### 6.1 Revision does not erase adverse history

Open required findings, failed reviews, failed verifications, unresolved defects, and other adverse evidence from an earlier revision MUST remain visible to later revisions until they are:

- resolved;
- explicitly waived through an already-authorized waiver path; or
- shown by attributable evidence to be inapplicable to the revised work.

If the revision changes the criterion, acceptance group, scope, or gate that the adverse finding concerns, the same Lead that authored or accepted the revision MUST NOT unilaterally declare the prior finding inapplicable. Independent confirmation is required.

A revision MUST NOT both change the criterion and self-dismiss the adverse result produced under the prior criterion.

### 6.2 Revision laundering is forbidden

A Lead MUST NOT revise a Ticket for the purpose or effect of escaping an adverse review, verification result, failed gate, or unresolved finding while continuing substantially the same work.

AEW MUST route a revision for independent confirmation when:

- the current or immediately prior adverse workflow outcome is `REVIEW_FAILED`, `VERIFICATION_FAILED`, or `VERIFICATION_INCONCLUSIVE`, or unresolved adverse evidence exists;
- the revision changes acceptance, scope, gates, dependencies, or an acceptance-bearing check-definition input; and
- implementation/workspace lineage is carried forward.

`BLOCKED` is not an adverse-failure trigger for this rule. A Ticket that is merely waiting on a dependency may revise that dependency through the normal revision path unless another trigger applies.

For this trigger, carried-forward lineage is engine-computed and cannot be reset by creating a fresh worktree or changing a workspace identifier. Lineage is present when either:

- the proposed workspace/candidate descends from the prior revision's authoritative workspace/candidate lineage; or
- engine-observed patch/commit/content identity shows reuse of implementation content produced under the prior revision.

A conservative positive match routes to independent confirmation; it does not itself reject the revision.

This is a mechanical anti-laundering trigger. It does not require AEW to infer intent.

Where the failure-class registry includes `REVISION_LAUNDERING`, detected violations SHOULD be classified accordingly.

### 6.3 Acceptance narrowing and unbound-field escape

The failure-class registry MUST include or map equivalent classes for:

- `ACCEPTANCE_NARROWING_BY_REVISION` — acceptance is narrowed or rewritten after work/evidence exists in a way that attempts to make an unmet obligation disappear rather than record a legitimate objective change;
- `UNBOUND_FIELD_ESCAPE` — acceptance-, scope-, authority-, or gate-relevant content is moved into or hidden within an unclassified/non-binding field to avoid freshness or gate consequences.

These classes are diagnostic/accountability categories; they do not replace the mechanical refusals and confirmation requirements above.

### 6.4 Gate shedding is forbidden

A revision MUST NOT reduce classification, inherited gates, or other required assurance merely because the prior revision failed or was blocked by those requirements.

Any class reduction remains subject to the governing classification-change rules.

A class reduction after adverse evidence MUST require the independent confirmation already required by the governing downgrade rules; revision does not create a weaker path.

## 7. Invocation, StageIntent, downstream impact, and execution binding

### 7.1 Invocation binding

Every model-controlled invocation that performs Ticket work MUST be bound to the Ticket revision under which it was admitted.

There MUST NOT be an active invocation authorized for a non-current Ticket revision.

Results produced under a prior revision remain attributable historical results. Late results MAY be recorded under the revision that admitted them, but they do not regain mutation authority or become accepted/current merely because they arrived late.

### 7.2 Revision quiesce and commit

Revision is a two-phase authority transition:

1. **Quiesce/revoke phase.**
   - block new admission against the old revision;
   - revoke or stop Ticket mutation authority for active invocations admitted under that revision;
   - reconcile any custody/integration state required by the governing execution contracts;
   - preserve held leases until their owning/reconciliation path explicitly retires them.

2. **Revision commit phase.**
   - compare-and-swap against the expected current Ticket revision;
   - commit the new immutable revision and revision decision only after the old revision can no longer admit or exercise Ticket mutation authority.

A proposed revision exists before commit only as a bounded held draft plus an attributable revision-attempt record. It is not the current Ticket revision and has no mutation authority.

While quiesce/reconciliation is in progress, AEW exposes a `revision_pending` **overlay** on the current Ticket. This is not a new workflow state.

The pending overlay records at least:

- proposed revision/draft identity;
- expected current revision;
- quiesce/reconciliation obligations;
- started time;
- expiry/deadline;
- blocking leases/invocations;
- abortability/attention status.

A timeout, failed stop, or failed reconciliation MUST NOT silently release a workspace/integration lease and MUST NOT force the revision commit.

The operator/authorized Lead path MAY **abort** the pending revision. Abort:

1. discards the held proposed revision as a candidate for commit while retaining the attempt/audit record;
2. leaves the old revision current;
3. restores admission to the old revision only after any quiesce/reconciliation side effects are safely reconciled;
4. does not release a lease except through that lease's governing reconciliation path.

On pending-revision expiry, AEW initiates the abort/reconciliation path and raises attention rather than leaving the Ticket indefinitely stuck.

### 7.3 Dispatch/revision race

Every dispatch/admission MUST compare-and-swap on the Ticket revision it was authorized against.

If revision commits first, an admission carrying the old revision is stale and MUST fail closed.

If admission commits first, the revision path MUST observe that invocation and quiesce/revoke it before the new revision can commit.

No race may produce an invocation with mutation authority against a revision that was never current for that invocation.

### 7.4 StageIntent binding

Every open `StageIntent` that is decision-sensitive to a Ticket MUST bind to the Ticket revision and any already-required legality/obligation digest.

A StageIntent bound to a non-current Ticket revision is non-runnable.

A new revision MAY adopt/rebind an old StageIntent only after rechecking:

- current Ticket revision;
- current source/control revision;
- legality/obligation digest;
- authority/gate requirements;
- the stage contract and any revision-changed inputs.

Rebinding is explicit and attributable; a stale StageIntent does not silently continue under the new revision.

### 7.5 Downstream impact propagation

A revision that changes acceptance, scope, or dependencies MUST produce a durable revision-impact record.

This amendment defines the minimal downstream hold it requires. It does **not** adopt F9 or depend on F9 becoming governing.

AEW provides a `revision_impact_hold` overlay with these semantics:

- the overlay is applied only to a **direct explicit dependent** whose declared dependency binding could be affected by the changed upstream revision;
- if AEW can mechanically prove that the dependent's bound upstream inputs are unchanged, no hold is required;
- while held, the dependent's canonical workflow state is unchanged, but AEW MUST block new dispatch/progression that would rely on the unresolved affected dependency;
- active dependent invocations are not automatically cancelled solely because the hold exists, but their results remain bound to the dependency state under which they were admitted and cannot satisfy affected progression until the hold is resolved;
- the hold records the upstream Ticket/revision, changed groups, dependent binding, creation time, and the exact obligation required to clear it;
- the hold clears only when AEW mechanically proves no relevant impact, or an attributable dependent revalidation/update establishes the new dependency basis;
- clearing the overlay does not itself make stale evidence current; ordinary evidence/revision rules still apply.

Further propagation occurs only if resolving the direct dependent causes that dependent's own governed inputs to change. One upstream revision MUST NOT automatically fan out an unbounded recursive re-evaluation.

A dependent does not automatically become invalid merely because an upstream Ticket revised.

Sibling work is affected only where an explicit dependency, shared requirement mapping, or other governed relationship makes the revision relevant.

A parent coverage recheck under §4.4 is always required for acceptance-group changes.

## 8. Workflow-state rules

Ticket revision is a governed transition, not an edit.

A revision MAY occur in a non-terminal Ticket state except while a publishing lease is held for the Ticket/integration candidate.

A revision MUST NOT follow `DONE` or `CANCELLED`.

If the Ticket is at `COMMIT_READY` or another state with a prepared integration/publication candidate, a material revision MUST retire or invalidate that candidate as required by the integration contract before the revised Ticket can proceed.

The revision impact MUST drive the next legal workflow action. A revision may therefore require, depending on changed bindings:

- plan reconfirmation or replanning;
- parent-coverage recheck;
- dependent impact/revalidation;
- StageIntent revalidation/rebinding;
- guardrail recomputation;
- renewed review;
- renewed verification;
- renewed checks;
- no action for unaffected evidence.

AEW MUST NOT assume that every revision requires every prior check to be repeated, and MUST NOT assume that unaffected prior evidence remains admissible without evaluating its bindings.

## 9. Amendment to Workflow Contract invariant 7

Invariant 7 is extended as follows:

> **Current acceptance is revision-bound.** A gate may be satisfied only by evidence whose source/workspace, check-definition, accepted-plan, Ticket-input, and other required bindings are current for the Ticket revision being advanced, or by an attributable revalidation record permitted by the governing contract.

Additionally:

- every Ticket field is assigned to a governed field group; unclassified fields fail closed into an acceptance-bearing group;
- changed groups and evidence admissibility are engine-computed from canonical content, not Lead-declared;
- no active invocation may retain Ticket mutation authority for a non-current revision;
- dispatch and revision are CAS-bound to the Ticket revision;
- open StageIntents bound to a non-current revision are non-runnable until explicitly revalidated/rebound;
- every committed Ticket revision has an attributable revision decision;
- no Ticket revision follows `DONE` or `CANCELLED`;
- no material revision may silently discard unresolved adverse findings;
- no revision may weaken an inherited authority or assurance requirement except through the already-governed explicit decision path;
- cumulative revision drift is checked against the predecessor, the checkpoint/original revision, and the parent envelope;
- acceptance-group changes trigger parent coverage re-evaluation.

## 10. Amendment to Knowledge Contract §12

Ticket revisions join plan revisions as first-class durable revision history.

For each Ticket, AEW MUST preserve:

- stable Ticket identity;
- immutable revision records;
- the identity of the current revision while the Ticket is active;
- predecessor / supersession linkage between revisions;
- reason and engine-computed changed-field information;
- field-group registry/schema identity sufficient to interpret bindings;
- revision-impact / revalidation decisions;
- independent confirmations required by this amendment;
- evidence bindings sufficient to recompute current admissibility;
- downstream impact records;
- final revision identity in Ticket completion records.

Derived indexes or current-revision pointers MAY be rebuilt from durable canonical records where the governing storage design permits.

A completion record MUST identify the Ticket's final revision and the evidence basis accepted for that revision.

Parent closeout material MUST incorporate the final revision identity of completed children and verify required parent coverage against those final revisions so that a later reader can reconstruct exactly which child acceptance proposition was satisfied.

## 11. Non-goals

This amendment does not:

- make Ticket text freely mutable;
- authorize arbitrary objective changes;
- allow a Lead to bypass parent purpose or stakeholder authority;
- create a new waiver mechanism;
- weaken review, verification, classification, or inherited gates;
- require a human review or material-revision checkpoint debit for a schema-declared non-material typo/presentation correction;
- define the CLI syntax or storage path used to implement revisions;
- require every field correction to invalidate every artifact;
- authorize live mutation-authority transfer to an already-running invocation;
- allow a revision timeout to release a lease;
- change Story/Epic purpose ownership or allow Tickets to redefine their parent.

## 12. Acceptance / oracle requirements

Implementation/dogfood SHOULD also measure revision friction, including revision count, confirmation/checkpoint triggers, evidence invalidation/revalidation, revision aborts, and cancel/recreate work avoided. M4-H SHOULD include these as diagnostic/process metrics if Ticket revisions are exercised; they are not primary quality outcomes.

An implementation conforming to this amendment MUST demonstrate at least:

1. a scope correction can remain the same Ticket and preserve applicable workspace work;
2. prior implementation proof does not silently satisfy the revised Ticket when its bound inputs changed;
3. unrelated current evidence remains usable when its bound inputs did not change;
4. every Ticket field is classified; an unknown field defaults to the acceptance-bearing group;
5. changed groups and digests are computed from canonical content, not accepted from the Lead;
6. the default text normalization set behaves exactly as specified and does not collapse wording changes;
7. moving an acceptance condition into notes/description cannot preserve the old acceptance digest;
8. a field-group registry/schema version change that moves a field conservatively affects both old and new groups;
9. unresolved adverse findings survive a revision;
10. `HISTORICAL`, `INVALIDATED`, or `SUPERSEDED` admissibility does not clear an adverse finding;
11. a revision that changes the failed criterion cannot self-dismiss the old adverse finding;
12. the independent confirmer is distinct from the revision author and receives engine diff, parent envelope, and open-adverse material before the Lead rationale;
13. class-2-or-higher confirmation includes the cumulative r1/checkpoint→proposed diff;
14. a Lead cannot lower class / drop inherited gates through revision without the existing required authority;
15. the default three-material-revision checkpoint rule is enforced, schema-declared title/presentation-only corrections do not consume it, and operator-controlled policy can change the finite threshold;
16. acceptance changes trigger parent-coverage re-evaluation;
17. revision of `DONE`, `CANCELLED`, or work with a held publishing lease is refused;
18. a dispatch racing a revision either commits first and is quiesced, or loses the CAS and is refused stale;
19. no active invocation remains authorized for a non-current revision;
20. a timeout/failure during quiesce does not release a lease or force the revision commit;
21. `revision_pending` is an overlay rather than a workflow state, has an expiry, and exposes blocking obligations;
22. aborting a pending revision preserves the old revision and restores admission only after required reconciliation;
23. late old-revision results remain attributable historical results;
24. open StageIntents become non-runnable across a revision until explicitly revalidated/rebound;
25. direct dependents receive the amendment-local `revision_impact_hold` treatment without requiring F9 and without automatic recursive fan-out;
26. cumulative drift is checked against r1/checkpoint and the parent envelope;
27. legacy r1 evidence without field-group bindings is conservatively treated as bound to all relevant groups;
28. carried-forward lineage is detected from authoritative ancestry/content identity even across a fresh worktree;
29. `BLOCKED` alone does not trigger anti-laundering confirmation, while `REVIEW_FAILED`, `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE`, or unresolved adverse evidence can;
30. dependencies stored in canonical control state participate in the field-group registry and digest model;
31. independent-confirmation thresholds use the Ticket's effective class;
32. replacement is required when kind, parent, or substantially non-overlapping objective changes;
33. completion and parent closeout identify the final Ticket revision;
34. revision history is durable and attributable;
35. authored revision text remains data/provenance and cannot become executable instruction authority by interpolation.

## 12.1 Implementation compatibility consequences

The following are implementation consequences of the governing semantics above, not new authority domains:

- evidence requires a Ticket-input/field-registry binding in addition to its existing bindings;
- `revision_pending` and `revision_impact_hold` are projection-visible overlays, so any typed dashboard/API projection that exposes them MUST version its contract rather than smuggling them into an existing closed enum;
- required independent confirmation is a governed stage/result and therefore incurs a fresh-context model invocation when the policy requires it;
- migration of pre-revision projects/evidence occurs through the explicit `aew migrate` / spec-migration path, not silent reinterpretation.

These costs do not weaken or expand the amendment's authority rules.

## 13. Governing disposition

Upon adoption, this amendment supplies the effective Ticket-revision semantics missing from:

- Workflow Contract v0.7 §7;
- Workflow Contract v0.7 §8;
- Workflow Contract invariant 7;
- Knowledge Contract v0.4 §12.

The effective-spec overlay index should replace the corresponding Ticket-revision `pending` debt with adopted `replaces` / `extends` targets for this amendment.

The failure-class registry should add or map the equivalent classes for `REVISION_LAUNDERING`, `ACCEPTANCE_NARROWING_BY_REVISION`, and `UNBOUND_FIELD_ESCAPE`.

After operator adoption, E19-B v0.4 is **DESIGN FROZEN / IMPLEMENTATION-READY**. Reopening requires a concrete implementation contradiction or an explicit governing amendment.

The later WC v0.8 / KC v0.5 re-freeze may fold these semantics into the new frozen base without changing their meaning.
