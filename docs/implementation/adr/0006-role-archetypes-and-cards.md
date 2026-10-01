# ADR-0006 — Role archetypes (authority classes) and Role cards (catalog)

- **Status:** Accepted (M1, step 8b). Operator clarification, 2026-09-25. Amended for M2 (2026-09-27) and M3 (2026-09-29).
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

## Amendment 2026-09-27 — M2: dispatchable read-only archetypes (ADR-0008)

- **Investigator, Researcher and Planner are dispatchable.** `DISPATCHABLE_IN_M1` is replaced by per-slot rules:
  - The execute slot of a non-mutating Ticket accepts only cards extending `investigator`, `researcher` or `planner` (`NON_MUTATING_EXECUTORS`).
  - The execute slot of a mutating Ticket stays implementer-only.
  - Parents have no execute slot. Their review and verify slots take reviewer and verifier cards.
- **Three generic built-in cards.** `investigator`, `researcher` and `planner` become the archetypes' `default_card`s.
- **Default executor.** The workflow-default executor of an unstaffed non-mutating Ticket is the `investigator` card.
  - Dispatch records it as `selected_by: workflow-default` and pins `expected_kind: discovery_record`, so the choice is explicit and visible.
  - Research and planning Tickets must be staffed: `work create --card`, `work staff --execute`, or `work dispatch --card`.
- **Operations.** Engine operations and the archetype YAML are extended together, and the equality test still holds:
  - investigator: `check.run`, `submit.discovery_record`, `context.read`;
  - researcher: `submit.research_record`, `context.read`;
  - planner: `submit.plan_proposal`, `context.read`.

  None of them can submit another archetype's kind, drive control state, accept a plan or mutate source (`OBSERVATION_MUTATED`).
- **Unchanged.** Selection precedence, `use_when` (advisory), operator pins (enforced in the execute slot, including for non-mutating Tickets), forbids and escalation checks. No archetype is added.
- **Specialist remains a card modifier.** Substantial audit work, such as a security audit or a performance characterization, is a non-mutating Ticket executed by an investigator-based card. Routine review and verification remain gates (WC §7).

## Amendment 2026-09-29 — M3: skills and capabilities projected into a harness (ADR-0009)

The M1 note "M3: skill loading by harness adapters" is resolved as follows. No archetype, card field or authority rule changes.

- **A card's skills and capabilities reach the harness as projection, never as authority.** The adapter turns the pinned card into the harness's own configuration: a system text and a permission rule set. Authority is still enforced by the engine and keyed by archetype only. Harness permissions are defense in depth.
- **Skills (WC §15.3, §16.10).** A harness may expose only the skills it actually provides for the card; everything else is denied.
  - **M3 provides none.** The OpenCode projection denies `skill` except for skills the harness provides, and disables OpenCode's compatibility plugin, so the operator's own `~/.claude` or `~/.agents` skills never load.
  - A card's requested skills are therefore recorded per run as `requested`, `exposed` and `unavailable`, and the system text names the unavailable ones and tells the model to proceed without them and say so.
  - Making skills reachable is future work: the operator's skills in `docs/skills/`, resolved through the capability registry (M6), and disclosed progressively (`future-work.md` D3, F12, F13).
- **Capabilities.** Only one ordinary capability changes the projection in M3: `documentation_lookup` opens web fetch and search; otherwise both are denied. `source_mutation` remains the implementer's alone, and maps to OpenCode's `edit`. Other capabilities stay "requested, resolution pending" until M6.
- **Nested delegation stays closed.** OpenCode's `subagent` is denied for every role, and any session other than the run's own is recorded as `foreign_sessions`. Allowing bounded harness-native orchestration under a capability grant is designed (`docs/design/capability-discovery-and-progressive-disclosure-design-v0.1.md` §8; `future-work.md` F7, F13), not implemented.

## Amendment 2026-09-30 — plan assurance binds the role plan (operator UAT)

In the operator's acceptance session, an accepted plan promised independent review and verification, but a plan was free text and the non-mutating Ticket's policy path required neither. AEW would have accepted the record on its executor's own result; the Lead noticed and staffed the review by hand. Operator decision (P0 before the M3 freeze): **required and explicit**.

- **Every plan revision declares its assurance.** `aew plan propose` and `aew plan adopt` take `--review <card|default>` and `--verify <card|default>` (repeatable; `default` is the archetype's `default_card`), or `--assurance none`. Without one of them the command is refused, naming the options. The declaration is stored in the plan record (`assurance`, additive to `aew/plan/v1`) and in the unit's plan entry. Cards are validated at proposal against the slot (`_slot_ok`) and the unit's forbidden list.
- **Acceptance binds it.** `aew plan accept` puts each declared card into the role plan with `selected_by: plan`, `pinned`, `plan_revision: N` (or marks an existing entry for the same card with `plan_revision`). Each becomes a required gate through the existing `plan_gates` (`review_card:<card>`, `verify_card:<card>`), sourced "accepted plan vN".
- **Only a new plan revision changes it.** `aew work staff --remove` or `--forbid` of a plan-bound entry is refused. Accepting a later revision releases the earlier revision's entries (a Lead's or operator's own entry for the same card stays, without the plan binding) and binds the new declaration.
- **A revision replaces only the plan it was proposed against** (added 2026-10-01, AEW-Lead review of the M3 tag). `aew plan accept` refuses a revision whose recorded `supersedes` is not the plan accepted now, asking for a new revision. Before this, an older proposal accepted after a newer plan rebound its own (possibly empty) assurance, dropping the newer plan's gates, and a revision proposed before an acceptance escaped the reason a supersession needs.
- **No new semantics beyond that.** The gates, their evaluation and the precedence of operator pins are unchanged; plans accepted before this amendment carry no declaration and bind nothing. Archetype authority is unchanged.
- Regressions: `tests/regression/test_uat_2026_09_30.py`. The wider plan-assurance design (`future-work.md` F14) remains post-M3.

