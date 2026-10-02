# AEW Cross-Document Invariant Index v0.2 (draft)

**Status:** Cross-document index. v0.2 DRAFT for designer review (implementer, 2026-10-01): adds the plan assurance invariants (§6) selected by the designer on 2026-10-01 (`plan-assurance-and-classification-decisions-2026-10-01.md` §3.1).  
**Authority:** Non-authoritative index. Referenced contracts/designs remain governing.  
**Purpose:** Give implementation/review agents one place to enumerate AEW invariants without copying them into a second authority layer.

## 1. Cross-cutting

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-AUTH-001` | Coordination may move knowledge; only existing AEW authority paths may move project state. | Live Coordination §3 |
| `AEW-INV-CLASS-001` | If a classifier can choose categories with different ceremony, default to the heavier category; downgrading requires recorded justification reviewable by an independent actor. | Hierarchy Revision §4–5; applied elsewhere |
| `AEW-INV-RESOURCE-001` | Individually legal delegation, isolation, retry, capability, or parallelism choices must not compose into globally pathological behavior. | Lead/Operator §17; Incidents note |
| `AEW-INV-TRACE-001` | Registries/indexes improve discoverability but do not become alternate workflow authority. | Registry/index status |

## 2. Lead / stakeholder / delegation

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-LEAD-001` | Lead investigates engineering-derivable facts before asking the stakeholder. | Lead/Operator §3, §8 |
| `AEW-INV-LEAD-002` | Work proceeds autonomously inside the approved envelope; material departure returns to stakeholder authority. | Lead/Operator §10–11 |
| `AEW-INV-DELEG-001` | Worker roles receive no dispatch/delegate capability by default. | Lead/Operator §16.1 |
| `AEW-INV-DELEG-002` | Nested delegation requires explicit bounded AEW capability authority and is not inherited. | Lead/Operator §16.2 |
| `AEW-INV-DELEG-003` | Duplicate work requires explicit ensemble/evaluation purpose. | Lead/Operator §16.3 |
| `AEW-INV-PERM-001` | Capability aggregation is exact-match by capability, scope, and approved objective unless a future deterministic rule proves safe reuse. | Lead/Operator §16.5 |
| `AEW-INV-CANCEL-001` | Canceling an objective revokes descendant credentials/capability authority. | Lead/Operator §16.6 |
| `AEW-INV-ATTN-001` | Human-interruption budgets batch questions; they never authorize silent answers to consequential questions. | Lead/Operator §16.4 |

## 3. Intent / hierarchy / evidence

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-INTENT-001` | Free-form authored semantics cross ingress as opaque data, not shell-interpreted syntax. | Hierarchy Revision §10.1 |
| `AEW-INV-HIER-001` | Parents preserve purpose; Tickets preserve proof. | Hierarchy Revision §3 |
| `AEW-INV-HIER-002` | After acceptance-bearing evidence is bound, semantic field changes are MATERIAL by default. | Hierarchy Revision §4, §8 |
| `AEW-INV-HIER-003` | Downgrading to CLARIFICATION requires recorded justification plus fresh-context independent confirmation. | Hierarchy Revision §4, §8 |
| `AEW-INV-HIER-004` | Supersession is a relationship over existing lifecycle states, not a new execution state. | Hierarchy Revision §9 |
| `AEW-INV-HIER-005` | Parent closeout requires explicit disposition of every superseded descendant. | Hierarchy Revision §9 |
| `AEW-INV-HIER-006` | Story/Epic revisions are compared to the approved envelope baseline, not only the previous revision. | Hierarchy Revision §18.1 |
| `AEW-INV-EVID-001` | Historically valid evidence and currently admissible evidence are distinct; history is preserved while gates use current admissibility. | Hierarchy Revision §13 |
| `AEW-INV-VERIFY-001` | Verifier reports evidence and may propose classification; Lead decides; uncertainty/design signals default to heavier replan path. | Hierarchy Revision §11.1 |

## 4. Workspace / containment / integration

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-ISO-001` | Workdir separation is not OS-level containment and must be labeled honestly. | Isolation §3.1 |
| `AEW-INV-ISO-002` | Strong containment must pass the containment regression gate before real-repository dogfood/internal alpha. | Isolation §6.6, §12 |
| `AEW-INV-ISO-003` | Isolation benchmarks gate selection of a project-default strategy. | Isolation §13 |
| `AEW-INV-ISO-004` | Shared-mutable serialization locks are invocation-bound; stale owners are reconciled before release. | Isolation §6.3 |
| `AEW-INV-INTEGRATE-001` | Filesystem isolation does not prove semantic independence; integration-stage checks must catch cross-Ticket conflict/overlap. | Isolation §14.1 |
| `AEW-INV-SCRATCH-001` | Temporary output uses explicit scoped scratch; scratch does not become authoritative evidence by existence. | Isolation §11 |

## 5. Coordination

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-COORD-001` | Relevance hints are advisory only and cannot route, hold, mutate, widen scope, or grant authority. | Live Coordination §4.2, §22 |
| `AEW-INV-COORD-002` | Absence of declared dependency/overlap hint never proves work unaffected. | Live Coordination §4.2, §22 |
| `AEW-INV-COORD-003` | Material assignment changes supersede/re-dispatch; they are not smuggled through as context deltas. | Live Coordination §7.1, §22 |
| `AEW-INV-COORD-004` | Contradictory findings remain separately attributable until explicitly resolved. | Live Coordination §12, §22 |
| `AEW-INV-COORD-005` | Coordination history cannot satisfy evidence/review/verification gates merely because it was routed or summarized. | Live Coordination §3, §22 |

## 6. Plan assurance

Only the genuinely new cross-document invariants. Plan assurance §27 also restates authority, stakeholder, hierarchy and evidence invariants indexed above (for example `AEW-INV-LEAD-001`, `AEW-INV-HIER-001`, `AEW-INV-EVID-001`); those are referenced, not duplicated.

| ID | Invariant | Governing source |
|---|---|---|
| `AEW-INV-ASSURE-001` | Acceptance is independently reconstructed before the proposed plan is revealed to the assurance role. | Plan Assurance §7 |
| `AEW-INV-ASSURE-002` | Acceptance resources and protected conditions are distinct from the mutation subject. | Plan Assurance §9, §10 |
| `AEW-INV-ASSURE-003` | A baseline counts only if it exercised the intended proposition. | Plan Assurance §11 |
| `AEW-INV-ASSURE-004` | Assurance binds the versioned dependency set, not plan text alone. | Plan Assurance §16 |
| `AEW-INV-ASSURE-005` | Review metadata cannot change the payload it reviews. | Plan Assurance §16 |
| `AEW-INV-ASSURE-006` | Clearing a blocker is a separate attributable artifact; the blocking finding is never rewritten. | Plan Assurance §19 |
| `AEW-INV-ASSURE-007` | Every dispatch path uses one computed predicate. | Plan Assurance §17, §17.1 |
| `AEW-INV-ASSURE-008` | A contradicted load-bearing premise holds the affected mutation until reassessed. | Plan Assurance §20 |
| `AEW-INV-ASSURE-009` | Inherited parent obligations cannot disappear at a child. | Plan Assurance §21 |
| `AEW-INV-ASSURE-010` | Passing child work does not prove composed parent behavior. | Plan Assurance §21 |

## 7. Maintenance

When a governing invariant changes:

1. update the governing source first;
2. update this index in the same change;
3. update affected regression/evaluation references;
4. never reinterpret the governing source from this index alone.
