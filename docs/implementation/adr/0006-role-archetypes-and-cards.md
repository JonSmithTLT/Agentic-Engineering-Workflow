# ADR-0006 — Role archetypes (authority classes) and Role cards (catalog)

- **Status:** Accepted (M1, step 8b). Operator clarification, 2026-09-25.
- **Spec basis:**
  - WC §5: roles are reusable execution templates with authority and context contracts.
  - WC §5.8: specialists supply guidance *within another role* and create no parallel authority.
  - WC §6: authority model.
  - WC §7: review and verification are gates, not synthetic Tickets.
  - WC §15.3: skills are separate from roles.
  - WC §16.6: capability grants may be narrowed.
  - KC §20: project customization may not weaken invariants.
- **Nature:** An implementation clarification inside the frozen architecture. It adds no new authority semantics.

## Decision

**Archetypes** are the authority classes, built into AEW (`aew/role-archetype/v1`). There are eight: `lead`, `investigator`, `researcher`, `planner`, `implementer`, `reviewer`, `verifier` and `frontier_advisor`.

- Authority, meaning which engine operations and evidence kinds a credential may use, is enforced in code and keyed by archetype only.
- The archetype YAML documents that authority and declares its capability ceiling (whether it may mutate source).
- A test keeps the documentation and the code in agreement.
- **Specialist is not an archetype** (WC §5.8). Specialist expertise is what a card adds.

**Role cards** are concrete team roles (`aew/role/v1`), such as C Engineer, Security Reviewer or Vulnerability Triager. A card `extends` exactly one dispatchable archetype and may add or narrow the following:

- `purpose`, `use_when`, `responsibilities`;
- `skills` (how the work is done; resolved by the harness);
- `required_capabilities` / `optional_capabilities`;
- `required_knowledge` (logical knowledge names);
- `outputs` — named refinements of the archetype's evidence kind, never new authority-bearing artifacts;
- `specialty` (reviewer cards), which satisfies `review_<specialty>` gates;
- `restrict` — narrowing only: operations, checks, paths. Each restriction must be a subset of what the archetype allows.

**Enforced escalation rules** (validation happens at catalog load and again at dispatch):

- `extends` must name a dispatchable archetype. `lead` and `frontier_advisor` cannot be extended by cards in M1.
- Cards cannot declare `authority`, `allowed_operations`, `persistent`, transitions or completion. The schema rejects unknown keys.
- `restrict.operations` must be a subset of the archetype's engine operations.
- A card cannot request capabilities above the archetype's ceiling; for example, a non-mutating archetype may not ask for `source_mutation`.
- Invocations are authorized by **archetype only**. The card's id, source and sha256 are pinned on the invocation, so editing a project card never changes an in-flight invocation.

**Catalogs:**
- AEW's built-in deck (`aew/roles/cards/`) is generic: `python_engineer`, `c_engineer`, `code_reviewer`, `security_reviewer`, `verifier`.
- Each project may add a catalog (`.aew/roles/*.yaml`, referenced from the manifest). IDs must be unique across both catalogs; a collision is a validation error and never silently shadows a built-in card. Domain cards (for example REVELATIONS' Vulnerability Triager or VR Analyst) live in the project catalog.

**Ticket role plan (Lead-owned control state; operator implementation notes 2026-09-25):**

```yaml
role_plan:
  execute: [{card: c_engineer, selected_by: lead}]
  review:  [{card: c_reviewer, selected_by: lead},
            {card: security_reviewer, selected_by: policy}]   # guardrail trigger
  verify:  [{card: verifier, selected_by: workflow}]         # default for a required gate
  forbidden: [{card: python_engineer, selected_by: operator, reason: "..."}]
```

- **Multiple cards per gate.** Every planned review/verify card is its own gate (`review_card:<id>`, `verify_card:<id>`), satisfied only by a passing result from an invocation that used that card, on the current snapshot. Ingest keeps the Ticket in REVIEW_PENDING/VERIFY_PENDING until every planned card has passed. Review and verification stay gates on the Ticket (WC §7); a standalone review Ticket is used only when the review is itself substantial work.
- **Selection precedence:**
  1. non-waivable policy and guardrail requirements (computed, cannot be removed; a forbidden card that policy requires is a conflict error);
  2. operator constraints (pins, forbids), which the Lead may replace only with a reason and a decision record;
  3. Lead selection;
  4. workflow defaults fill any required gate with no card (the archetype's `default_card`).

  The engine stores the plan and computes the *effective* plan; `aew work roles <T>` shows both.
- **`use_when` is advisory.** It is metadata for Lead/Planner reasoning, shown in catalog listings and the Lead's pack. It never dispatches anything; mandatory cards come only from policy.
- **Operator attribution limit.** `selected_by: operator` recorded through the Lead is attribution, the same as `authority accept --decided-by operator`: the engine cannot prove a human made it (ADR-0005 threat model). A follow-up can require the terminal operator channel for operator pins.

**Capability tiers (note 3).**
- *Authority-sensitive* capabilities must lie within the archetype's envelope: `source_mutation`, `control_state_mutation`, `integration_control`, `publication`, `verification_failure_classification`, `plan_acceptance`, `work_state_transition`. Only `implementer` has `source_mutation`; no dispatchable archetype has the others.
- *Ordinary* read/analysis capabilities (`binary_analysis`, `call_graph_query`, `relationship_discovery`, …) come from the card. Availability against the workbench profile is resolved in M6; until then they are recorded and listed in the pack as *requested, resolution pending*.

**Identity pinning (note 4).** Each invocation records `card: {id, version, source, sha256, content}`, and evidence records `producer.role_card`. Packs regenerate from the pinned content, so editing a card later never changes a historical invocation or its pack.

**Composition:** Invocation = Role card + Ticket assignment + Skills + resolved project knowledge + capability grants + context pack + invocation credential.

## M1 scope versus later

- **M1:**
  - the schema split;
  - built-in archetypes and cards;
  - the project catalog;
  - validation and escalation rejection;
  - `aew role list/show/validate`;
  - `aew invoke create --card`;
  - the Ticket role plan (`aew work roles`);
  - cards in packs;
  - specialty reviews via reviewer cards.
- **Later:**
  - M2: dispatching investigator/researcher/planner cards (the non-mutating Ticket path, with discovery and research evidence).
  - Per-card output-contract payload schemas. The evidence `contract` and `payload` fields are reserved now.
  - M3: skill loading by harness adapters.
  - M6: capability resolution against providers.

## Amendment 2026-09-26 — independent review (M4, M7, N1)

- **Gates count only ingested reports (M4).**
  - Review gates (`review_*`, `review_card:*`) and verification gates (`verification_*`, `verify_card:*`) are satisfied only by reports the Lead has **ingested**: their id and sha256 are pinned in the Ticket's accepted evidence refs. That set includes the report being ingested in the same transaction.
  - A sealed submission that was never ingested, or whose bytes changed, satisfies nothing. One ingest therefore cannot retire another required report that still awaits its own ingestion checks and bookkeeping. The Ticket stays in REVIEW_PENDING or VERIFY_PENDING until every planned card has been *ingested* and has passed.
  - `local_checks` and `self_review` keep counting the implementer's submissions. Their acceptance is the Lead's RUNNING → REVIEW/VERIFY transition, which pins the evidence it relied on.
- **Operator pins are recorded and enforced (M7).**
  - Staffing a card that is already in the plan now updates it. `--by operator` sets `selected_by: operator` and the requested pin, and records a decision. A Lead re-selecting an operator-pinned card leaves the operator's constraint intact.
  - Dispatch honours pins, whether the card is chosen explicitly (`invoke create --card`) or implicitly. In the `execute` slot, which holds one card, only an operator-pinned card may be dispatched. Any other card is refused, and an override goes through `aew work staff --reason` as a recorded decision, as the selection-precedence rule requires.
  - Pinned review/verify cards are enforced as required gates (`plan_gates`), so dispatching an additional card in those slots never bypasses them.
  - Operator attribution recorded through the Lead remains attribution, not proof (see above).
- **`restrict.paths` is deferred (N1).**
  - The M1 card schema accepts `restrict.operations` and `restrict.checks` only. A card declaring `restrict.paths` is rejected (fail closed), and the "paths" in the Role-cards bullet above is not yet available.
  - In M1, path limits come from the Ticket's declared scope paths and the guardrail policy (protected/generated paths, `outside_ticket_scope`).
  - Card-level path restriction is **Designed**. It needs enforcement at check/guardrail time and is recorded in `implementation-status.md`.
