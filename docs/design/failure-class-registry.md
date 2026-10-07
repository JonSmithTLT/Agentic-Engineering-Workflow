# AEW Failure-Class Registry v0.2

**Status:** Cross-document index. v0.2 (2026-10-01, accepted by the designer in review): adds the plan assurance classes (§5) as reconciled by the designer on 2026-10-01 (`plan-assurance-and-classification-decisions-2026-10-01.md` §3.1). 2026-10-06: adds the Ticket-revision amendment's three classes to §4 (`workflow-contract-amendment-ticket-revisions-2026-10-06.md` §6.2, §6.3, §13).  
**Authority:** Non-authoritative index. Definitions point to owning design/contract text; this file must not become a second source of workflow authority.  
**Purpose:** Prevent naming/definition drift across AEW design, dogfood, and evaluation documents.

## 1. Registry rules

Each named class has one canonical name, one primary owning document/domain, a concise definition, and an expected detection/evaluation path.

Owning documents define semantics. Other documents reference the name.

A class names a failure, not an error code. Engine refusal codes are separate: a deterministic check emits its own code (for example `PROTECTED_CONDITION_OVERLAP`) and associates it with a canonical class (`PROTECTED_ACCEPTANCE_OVERLAP`). Some classes can only be established by evaluation against gold evidence (for example `PLAN_CHALLENGE_FALSE_CLEAR`).

## 2. Operator / orchestration / resource classes

| Class | Primary owner | Definition | Detection / standing evaluation |
|---|---|---|---|
| `UNNECESSARY_STAKEHOLDER_INTERRUPTION` | Lead/Operator | Lead asks for information AEW could reasonably discover or decide inside the approved envelope. | Elicitation dogfood/evals. |
| `MISSED_STAKEHOLDER_ELICITATION` | Lead/Operator | Lead silently makes a consequential stakeholder-owned choice. | Consequential-ambiguity eval. |
| `STALE_PROJECT_KNOWLEDGE` | Lead/Operator | Lead materially relies on stale derived project knowledge. | Map freshness tests. |
| `UNPROPAGATED_STAKEHOLDER_DECISION` | Lead/Operator | Durable stakeholder directive fails to reach affected work/context. | Active-run propagation tests. |
| `EXCESSIVE_REPLANNING` | Lead/Operator | Minor/local changes repeatedly trigger unnecessary approval/replanning. | Dogfood attention metrics. |
| `PROGRESS_NOISE` | Lead/Operator | Routine internal activity is surfaced without stakeholder value. | Checkpoint/status review. |
| `INSUFFICIENT_VISIBILITY` | Lead/Operator | Meaningful blocker/deviation/risk is not surfaced. | Checkpoint/status review. |
| `UNBOUNDED_DELEGATION` | Lead/Operator | Agent topology exceeds authorized depth/count or a worker gains unintended orchestration authority. | Skill-instructed-spawn capability regression. |
| `DUPLICATE_WORK_FANOUT` | Lead/Operator | Materially equivalent work is launched repeatedly without explicit ensemble purpose. | Deep-review standing regression. |
| `PERMISSION_PROMPT_AMPLIFICATION` | Lead/Operator | Equivalent capability decisions generate repeated stakeholder prompts through worker fanout. | Deep-review/aggregation regression. |
| `RESOURCE_COMPOSITION_FAILURE` | Lead/Operator, cross-cutting | Individually legal resource decisions compose into globally pathological behavior. | Fanout × workspace × permission stress cases. |

## 3. Workspace / containment classes

| Class | Primary owner | Definition | Detection / standing evaluation |
|---|---|---|---|
| `HOST_WRITE_ESCAPE` | Isolation | Worker mutates a protected path outside authorized writable roots. | Containment regression suite. |
| `ISOLATION_OVERHEAD_FAILURE` | Isolation | Isolation cost makes ordinary supported work operationally unusable. | Repository-scale benchmark gate. |
| `WORKSPACE_LEAK` | Isolation | Worker observes/mutates another worker's private state contrary to policy. | Cross-workspace tests. |
| `CLEANUP_DAMAGE` | Isolation | Cleanup modifies/destroys unrelated project state. | Crash/cleanup regression. |
| `FALSE_CONTAINMENT_CLAIM` | Isolation | Weak workdir separation is represented as stronger OS/runtime containment. | Metadata/status assertion + containment test. |

`RESOURCE_MULTIPLICATION` is retired as a local alias; use `RESOURCE_COMPOSITION_FAILURE`.

## 4. Hierarchy / intent / evidence classes

| Class | Primary owner | Definition | Detection / standing evaluation |
|---|---|---|---|
| `INTENT_INGRESS_CORRUPTION` | Hierarchy Revision / ingress | Authored semantic text is altered by transport/interpolation before authoritative storage. | Shell-significant value-preservation regression. |
| `SILENT_INTENT_REWRITE` | Hierarchy Revision | Goal semantics change without required provenance/approval. | Goal-revision tests. |
| `EVIDENCE_MEANING_DRIFT` | Hierarchy Revision / Knowledge | Evidence created under one proposition continues satisfying gates after proposition meaning changes. | Supersession/admissibility tests. |
| `EXCESSIVE_HIERARCHY_RECREATION` | Hierarchy Revision | Large Stories/Epics are replaced for ordinary discovery-driven evolution that could safely revise/restructure. | Research-driven Story eval. |
| `MISSED_REPLAN` | Hierarchy Revision | Material parent revision occurs while affected descendants continue on stale plan/context. | Descendant-impact tests. |
| `UNAUTHORIZED_SCOPE_CHANGE` | Hierarchy Revision | Lead changes stakeholder-owned intent outside delegated envelope. | Epic objective-change eval. |
| `LOST_SUPERSESSION_LINEAGE` | Hierarchy Revision | Replacement work lacks durable connection/disposition to superseded work. | Parent closeout + replacement tests. |
| `STALE_PARENT_INTENT` | Hierarchy Revision | Descendants continue against superseded Epic/Story framing. | Ancestor-plan/revision tests. |
| `REVISION_LAUNDERING` | Ticket-revision amendment (§6.2) | A Ticket is revised to escape an adverse review, verification result, failed gate or unresolved finding while substantially the same work continues. | The mechanical anti-laundering trigger routes to independent confirmation; conformance cases (§12 items 9 to 11, 28, 29). |
| `ACCEPTANCE_NARROWING_BY_REVISION` | Ticket-revision amendment (§6.3) | Acceptance is narrowed or rewritten after work or evidence exists so that an unmet obligation disappears, rather than a legitimate objective change being recorded. | Acceptance-group change after acceptance-bearing evidence requires independent confirmation (§4.2); conformance case (§12 item 2). |
| `UNBOUND_FIELD_ESCAPE` | Ticket-revision amendment (§6.3) | Acceptance-, scope-, authority- or gate-relevant content is moved into or hidden in an unclassified or non-binding field to avoid freshness or gate consequences. | Fail-closed field-group registry (§2.3); conformance cases (§12 items 4, 7). |

Plan assurance's candidate `INTENT_SUBSTITUTION` (derived plan language changes the actual stakeholder objective) is `SILENT_INTENT_REWRITE`.

The Ticket-revision classes, and why existing classes do not cover them: `ACCEPTANCE_NARROWING_BY_REVISION` is the Ticket-revision case of `ACCEPTANCE_CONDITION_MUTATION`, where the conditions changed through a recorded revision rather than without one; use the narrower name when a revision is the vehicle, the broader one otherwise. `REVISION_LAUNDERING` concerns escaping an adverse result while the work continues, which neither `UNAUTHORIZED_SCOPE_CHANGE` (intent changed outside the envelope) nor `SILENT_INTENT_REWRITE` (no provenance) names. `UNBOUND_FIELD_ESCAPE` concerns where content is placed to avoid binding, which `EVIDENCE_MEANING_DRIFT` (evidence outliving a changed proposition) does not.

## 5. Plan assurance classes

Owner: `plan-assurance-and-premise-validation-design-v0.4.md`, adopted with this registry revision (§26 for definitions, §28 for the adversarial evaluation suite, §31 for the conformance tests).

| Class | Primary owner | Definition | Detection / standing evaluation |
|---|---|---|---|
| `POISONED_PLAN_PREMISE` | Plan Assurance | A false or unsupported premise becomes load-bearing in an accepted plan. Detail `premise_origin` (for example `stakeholder_diagnosis`, the former candidate `STAKEHOLDER_DIAGNOSIS_PROMOTION`). | T4 replay fixture; diagnosis contrast pairs (§28). |
| `ACCEPTANCE_UNDERSPECIFICATION` | Plan Assurance | Acceptance checks fail to represent important objective or preservation obligations. | Acceptance discrimination and counterexample cases (§12, §28). |
| `ACCEPTANCE_CONDITION_MUTATION` | Plan Assurance | The candidate appears successful because conditions that define success changed without requirement authority. The M3 dogfood's T4 (O3). | Oracle-weakening cases (§28); protected-condition enforcement through final verification. |
| `PROTECTED_ACCEPTANCE_OVERLAP` | Plan Assurance | The mutation grant overlaps protected acceptance resources without explicit authorization. | Deterministic check at plan acceptance and dispatch (refusal code `PROTECTED_CONDITION_OVERLAP`); conformance test (§31). |
| `ACCEPTANCE_BASELINE_INVALID` | Plan Assurance | The baseline does not exercise the intended proposition, or is operationally invalid. | Typed-baseline cases, for example an ImportError not accepted as `EXPECTED_FAILURE` (§11, §31). |
| `PLAN_ASSURANCE_BYPASS` | Plan Assurance | Mutation begins without policy-required assurance. | The dispatch-route conformance test: every route calls the shared predicate (§17). |
| `ASSURANCE_DEPENDENCY_STALE` | Plan Assurance | A contract, fixture, base, parent invariant, plan review or other relevant dependency invalidates current assurance. Detail `dependency_kind` (for example `plan_review`, the former candidate `PLAN_REVIEW_STALE`). | Dependency-digest binding tests (§16, §31). |
| `PLAN_CHALLENGE_FALSE_CLEAR` | Plan Assurance | The challenge passes despite an identifiable blocking defect. | Evaluation only, against gold evidence (§28, §29). |
| `PLAN_CHALLENGE_FALSE_BLOCK` | Plan Assurance | The challenge blocks a valid plan without adequate evidence. | Evaluation only (§28, §29); bounded adjudication (§19). |
| `EVALUATOR_INTEGRITY_FAILURE` | Plan Assurance | The candidate changes or interferes with the evaluator in an unauthorized way. | Protected-evaluator enforcement (§9, §10); vacuous-red and oracle cases (§28). |
| `EXECUTION_PREMISE_CONTRADICTION` | Plan Assurance | Execution produces evidence that contradicts an assured load-bearing assumption. | Mid-run contradicted-premise test: affected mutation held (§20, §31). |
| `HIERARCHICAL_ASSURANCE_LOSS` | Plan Assurance | Child work silently drops inherited parent acceptance, security or compatibility obligations. | Child-drops-parent-obligation test (§21, §31). |

## 6. Maintenance

Adding a class requires: owning document, concise definition, reason an existing class is insufficient, and detection/evaluation path.

Renaming/merging a class requires updating this registry and references in the same change.

Do not create document-local synonyms for an existing class.
