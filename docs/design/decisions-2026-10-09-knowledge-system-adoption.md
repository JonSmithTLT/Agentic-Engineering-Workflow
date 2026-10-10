# AEW Knowledge System Adoption Decision v0.1

**Status:** ADOPTED  
**Date:** 2026-10-09  
**Authority:** Operator decision  
**Scope:** M6b knowledge-system semantic direction, storage placement, role access, and default discoverability

## 1. Decision

AEW adopts the current knowledge-system design set as the governing M6b direction:

- `aew-knowledge-capture-admission-design-v0.4.md`
- `aew-knowledge-capture-recall-shared-semantics-v0.4.md`
- `aew-knowledge-recall-context-routing-and-agent-use-design-v0.3.md`
- `ADR-0013-knowledge-storage-placement.md`

ADR-0013 is adopted together with the semantic set.

This adoption accepts the architecture and authority boundaries described by those artifacts. It does **not** bypass the existing evidence-driven implementation sequence or authorize production K1/K2 machinery ahead of the accepted stop/go gates.

## 2. Role-access decision

Knowledge/history lookup is a normal AEW capability, not a privilege reserved to the Lead.

All admitted engineering roles may receive safe project-scoped lookup capability by default, including Lead, implementer, reviewer, verifier, investigator, and future bounded worker roles unless an explicit policy reason excludes them.

The system should give weaker workers as much deterministic and retrieval assistance as safely possible.

The objective is not merely to reduce frontier-model cost. It is also to improve the effective capability of weaker models by removing avoidable discovery, context-reconstruction, and repository/history-navigation work.

### Default role shape

Ordinary workers receive:

- `EXPLICIT_LOOKUP`
- exact ID/source expansion
- compact qualified search results
- bounded progressive disclosure
- exact evidence/source links where available

Lead and investigator roles may additionally receive deeper historical investigation surfaces such as:

- `INVESTIGATION_HISTORY`
- challenged/held/historical material with explicit qualification
- broader expansion where policy permits

Operator/evaluation tooling may receive:

- `DEBUG_EVALUATION`
- ranking/index/provenance diagnostics
- evaluation-only metadata

Request modes remain query intent, never authority grants.

## 3. Discoverability decision

Knowledge/history lookup is a base AEW capability and SHOULD be ordinarily discoverable to workers by default.

Workers should not require a Lead to explicitly remember to grant ordinary knowledge lookup for each Ticket.

The intended experience is:

```text
worker invocation
    ↓
normal AEW capabilities include:
    project/repository navigation
    knowledge/history lookup
    exact evidence expansion
    role-appropriate task tools
```

This does **not** mean historical content is automatically injected into every context packet.

Default behavior is:

> **Broad tool availability, narrow default payload.**

The capability is present and easy to discover. Historical content is retrieved when useful.

## 4. Progressive-disclosure decision

Different roles need different answer depth, not different access to the existence of the capability.

An implementer normally needs concise, actionable results such as:

```text
Relevant prior incident: K/H-123
Why matched: same subsystem + failure signature
Status: historical / role-attested
Key point: retrying after stale revision caused duplicate integration work
Evidence: E-44, E-51
Expand? <ref>
```

An implementer should not receive a multi-page historical dossier merely because one exists.

A Lead or investigator may intentionally expand into full historical context, competing hypotheses, challenged records, related incidents, provenance chains, environment differences, and disposition history.

The role distinction is therefore primarily one of result budget, context budget, default expansion depth, and available investigation modes; not arbitrary denial of the knowledge capability itself.

## 5. Security / visibility posture

The knowledge system is not intended as a secret-management system.

M6 v1 remains project-scoped, and normal AEW authorization/visibility rules still apply.

The adoption does not authorize cross-project leakage, hidden provider metadata leakage, secrets in Knowledge records, historical prose gaining execution authority, request text widening visibility, or retrieval results granting workflow permissions.

Historical and model-authored text remains untrusted reference data.

## 6. Product objective

AEW should give every model the strongest safe informational advantage available.

For frontier Leads, this conserves scarce high-end reasoning capacity.

For weaker workers, this compensates for weaker repository navigation, historical recall, search strategy, and context acquisition.

> **A worker should spend as much of its limited intelligence as possible on the engineering assignment, not on rediscovering information AEW already possesses.**

This aligns with the adopted Deterministic Work Conservation requirement.

## 7. Implementation sequence remains evidence-driven

Adoption does not change the accepted M6b sequence:

```text
A — no recall
↓
B — guarded explicit raw canonical-history recall
↓
A/B evaluation under ordinary discoverability
↓
K1 historical replay / source-class gate
↓
C — smallest K0/K1 structured Case arm, only if B leaves a measurable gap
↓
B/C comparison
↓
K2 Lessons only if C earns the complexity
↓
automatic discovery only as a separately measured later arm
```

Arm B remains the first production implementation target.

Semantic/vector retrieval remains optional and must beat the lexical/structured baseline before becoming load-bearing.

## 8. Immediate implementation consequences

The M6b implementation-readiness work may now proceed without returning to the operator for these questions.

The implementation package should:

1. reconcile/freeze field names and glossary across the adopted semantic set;
2. qualify ADR-0013 assumptions against the current tree;
3. define the exact Arm B indexed corpus;
4. define the concrete request-mode/role matrix consistent with this decision;
5. define compact/default versus expanded result shapes;
6. assemble the F19-compatible A/B evaluation corpus and rubric;
7. replay K1 candidate templates only after Arm B is measurable;
8. leave ranking formula, vectors, rerankers, automatic discovery thresholds, and K2 production policy to later evidence.

Implementation-local naming and schema details should use the simplest conservative choice consistent with the adopted contracts rather than escalating routine decisions.

## 9. North-star interpretation

The knowledge system should be treated as part of AEW's base intelligence-amplification layer.

It is not primarily:

```text
a database agents may occasionally use
```

It is:

```text
a project-aware information capability
that makes prior engineering experience
cheaper to obtain than rediscover
```

Success means both frontier and weaker models rationally prefer AEW's knowledge/navigation surfaces when those surfaces can answer the question better, faster, or more completely than manual rediscovery.
