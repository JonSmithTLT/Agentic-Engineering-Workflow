# AEW Failure-Class Registry v0.1

**Status:** Cross-document index  
**Authority:** Non-authoritative index. Definitions point to owning design/contract text; this file must not become a second source of workflow authority.  
**Purpose:** Prevent naming/definition drift across AEW design, dogfood, and evaluation documents.

## 1. Registry rules

Each named class has one canonical name, one primary owning document/domain, a concise definition, and an expected detection/evaluation path.

Owning documents define semantics. Other documents reference the name.

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

## 5. Maintenance

Adding a class requires: owning document, concise definition, reason an existing class is insufficient, and detection/evaluation path.

Renaming/merging a class requires updating this registry and references in the same change.

Do not create document-local synonyms for an existing class.
