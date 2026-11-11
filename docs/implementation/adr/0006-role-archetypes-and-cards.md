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
- Each project may add a catalog (`.aew/roles/*.yaml`, referenced from the manifest). IDs must be unique across both catalogs; a collision is a validation error and never silently shadows a built-in card. Domain cards (for example a security-research project's Vulnerability Triager or VR Analyst) live in the project catalog.

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
- **Nested delegation stays closed.** OpenCode's `subagent` is denied for every role, and any session other than the run's own is recorded as `foreign_sessions`. Allowing bounded harness-native orchestration under a capability grant is designed (`docs/design/proposals/capability-discovery-and-progressive-disclosure-design-v0.1.md` §8; `future-work.md` F7, F13), not implemented.

## Amendment 2026-09-30 — plan assurance binds the role plan (operator UAT)

In the operator's acceptance session, an accepted plan promised independent review and verification, but a plan was free text and the non-mutating Ticket's policy path required neither. AEW would have accepted the record on its executor's own result; the Lead noticed and staffed the review by hand. Operator decision (P0 before the M3 freeze): **required and explicit**.

- **Every plan revision declares its assurance.** `aew plan propose` and `aew plan adopt` take `--review <card|default>` and `--verify <card|default>` (repeatable; `default` is the archetype's `default_card`), or `--assurance none`. Without one of them the command is refused, naming the options. The declaration is stored in the plan record (`assurance`, additive to `aew/plan/v1`) and in the unit's plan entry. Cards are validated at proposal against the slot (`Roles.slot_ok`) and the unit's forbidden list.
- **Acceptance binds it.** `aew plan accept` puts each declared card into the role plan with `selected_by: plan`, `pinned`, `plan_revision: N` (or marks an existing entry for the same card with `plan_revision`). Each becomes a required gate through the existing `plan_gates` (`review_card:<card>`, `verify_card:<card>`), sourced "accepted plan vN".
- **Only a new plan revision changes it.** `aew work staff --remove` or `--forbid` of a plan-bound entry is refused. Accepting a later revision releases the earlier revision's entries (a Lead's or operator's own entry for the same card stays, without the plan binding) and binds the new declaration.
- **A revision replaces only the plan it was proposed against** (added 2026-10-01, AEW-Lead review of the M3 tag). `aew plan accept` refuses a revision whose recorded `supersedes` is not the plan accepted now, asking for a new revision. Before this, an older proposal accepted after a newer plan rebound its own (possibly empty) assurance, dropping the newer plan's gates, and a revision proposed before an acceptance escaped the reason a supersession needs.
- **No new semantics beyond that.** The gates, their evaluation and the precedence of operator pins are unchanged; plans accepted before this amendment carry no declaration and bind nothing. Archetype authority is unchanged.
- Regressions: `tests/regression/test_uat_2026_09_30.py`. The wider plan-assurance design (`future-work.md` F14) remains post-M3.


## Amendment 2026-10-06 — a decision recorded as the operator's needs the operator (operator decision)

The operator's rule: **"if my name is attached to it, I should have actually approved."** This closes the operator attribution limit (Decision, above), for this ADR's `selected_by: operator` and for ADR-0005's `authority accept --decided-by operator`.

- **The terminal confirms it.** `aew work staff --by operator`, `aew authority accept --decided-by operator` and (since
  the policy pin, PR #118) `aew manifest adopt` ask the operator to type back a one-time code at their own controlling terminal (`operator.authorize`, the channel `lead takeover` and `integrate breaker reset` already use), before anything runs. With no terminal they are refused (`OPERATOR_AUTHORIZATION_REQUIRED`) and nothing is recorded. The engine also refuses an operator-attributed record that does not carry the prompt's `authorized_by: operator-tty` (`operator.require_operator_attribution`), and the decision record keeps it. That check only catches a caller that did not ask; the guarantee is the CLI's prompt and the broker's refusal, since an in-process Python caller could supply the record itself.
- **A Lead session cannot ask.** The Lead broker refuses `--by operator` on `work staff`, before anything runs (`lead_broker.OPERATOR_ATTRIBUTED`). The Lead's own staffing is unchanged. `authority accept` and `reject` are operator-only in a Lead session altogether (PR #103).
- **Prompts stay rare.** Only a record attributed to the operator prompts. The Lead's own decisions never do. A mechanism that needs no terminal, for an operator who is away, is F15.5's operator capability (register F15.5).
- Tests: `tests/integration/test_authority.py` (refused without the terminal, at the CLI and the engine; nothing recorded; `test_adopting_needs_the_operator_at_their_terminal_whatever_the_credential`, `test_a_missing_required_policy_file_is_never_adopted`) and `tests/unit/test_lead_reachability.py` (the broker's refusal); the pin itself: `test_a_policy_edit_after_a_transaction_began_is_never_used_by_it`, `test_an_unadopted_execution_policy_edit_trusts_no_git_driver`, `tests/integration/test_context_packs.py::test_a_pack_quotes_only_the_adopted_guardrails`.

## Amendment 2026-11-05 — skills reach workers, by the card's fit (register E127)

The designer's rulings of 2026-11-03 (§3) and 2026-11-04 ("skills by fit"), after the operator's "deliver the four" and "go with fit". This replaces the M3 amendment's "M3 provides none". Skills stay technique, never authority (this ADR's archetype rule): no gate, evidence or state reads them, and a card's lists grant nothing.

- **AEW's own install, not a project catalog.** Four skills ship as package data (`src/aew/skills/shipped/`), with a manifest of hashes over their allow-listed files (`aew.skills`). A project cannot add, replace or override one (`HEB-01.i`, `CAPR-05`). A card names a skill only by id, which resolves by manifest lookup, never by joining it to a path, so a project card can name shipped skills and add no text. The package copy changes only by a pull request that re-hashes the manifest. The manifest is an interim lookup: `CAPR-B6` stays open, and the register absorbs it when that settles.
- **Every shipped skill is labelled `unevaluated`.** The operator released them for the personal alpha only. This departs, for the alpha, from the install UX's "only when accepted/qualified", HNI-11 and F18's per-pin qualified surface. Qualification is owed before anything beyond the alpha.
- **The allow-list:** `SKILL.md`, `references/` and `examples/`. `evals/` never ships. Nothing else sits at the root the harness scans, since OpenCode would make a stray `*.md` there, or a nested `SKILL.md`, a skill of its own.
- **A second list on the card, `optional_skills`** (`role.schema.json`). `skills:` stays "load these"; `optional_skills` is what a run may load when its task matches. A name in both counts as `skills:`. It is fit, not a boundary: nothing is listed unless a card names it. Where a skill turns out to be a provider, that reverses `CAPR-06`'s default, which is the operator's "go with fit".
- **`launch.skills`, per run:** `requested` (the card's `skills:`, as before); `offered`, new (`optional_skills` beyond `skills:`); `exposed`, **widened**, which changes the M3 amendment's meaning: `(requested ∪ offered) ∩ provided`, where provided means shipped and matching the manifest; `unavailable`, unchanged in meaning (what `skills:` asked for and did not get); `reasons`, new (`{name: why}` for anything in either list that is not exposed: `not_shipped`, `hash_mismatch`, `outside_allow_list`, `copy_failed`); `delivered`, new (`name`, `version`, `sha256`, `label`, and the `SKILL.md` size in `bytes`, for what the run could reach); `copy` (`read_only_bind` or `rules_only`). The plan is decided once, in the launch contract, so the copy, the rules, the record and `aew harness config` agree. A missing or mismatched skill never fails a run.
- **The copy.** The supervisor copies only exposed skills, only the manifest's files, re-hashed, into the run's own `harness/skills` before its sandbox exists. On Linux the layout binds that folder read-only and adds it to the self-test's protected paths. Windows has no bind, and the record says `rules_only`.
- **The projection (OpenCode).** One `skills` entry, the copy's absolute path as a string (an object entry loads nothing, silently). `skill allow <id>` for each exposed skill, with everything else denied, OpenCode's built-ins included. On every platform the copy gets two rules together: `external_directory allow <copy>/*` so `read` reaches `references/`, and `edit deny <copy>/*`, since the read grant alone let a model write to an unbound copy.
- **What the agent is told.** The pack carries the card's pinned lists. Its "Skills to load" line is unchanged, and a card with `optional_skills` beyond `skills:` gets the conditional line "Optional skills (load one only if the `skill` tool lists it and your task matches)". The pack renders nothing from the manifest, so a re-hash between dispatch and relaunch never refuses a relaunch. The system text says what this run really has, in separately conditioned clauses: load the card's shipped `skills:` unless a description excludes the task, the other skills the tool lists, and the `skills:` it does not provide. The pack's `sources` pin each shipped `skills:` name by version and hash, never the optional ones.
- **`loaded`: a narrow exception to "never its inputs or outputs"** (ADR-0009's run result; M3-D3). Beside `tools_called`, a run's result has `loaded: {id: count}`, counting completed `skill` calls of an exposed id, and `skill_other: n` for every other `skill` call, whose id is never stored, since a model writes it. Their sum is `tools_called["skill"]`. It is telemetry: nothing reads it as a gate, evidence or state. It says loaded, not used. Any failure reading it leaves both absent and never reaches the run. No snapshot, or a truncated one, reads as unknown, never empty. `events.jsonl` keeps its own rule.
- **The Lead** is told to staff the implementer by the change's language, derived from the built-in cards and the install (`guide.staffing_text`). The Lead's own route takes no skills: it has no card.
- Tests: `tests/unit/test_skill_delivery.py`, `tests/unit/test_opencode_units.py`, `tests/unit/test_containment_layout.py`; the live regression test on Linux is `tests/live/test_skills_live.py`.

## Amendment 2026-11-11 — the specialist reviewers' skills ship (register E142)

The operator's 2026-11-04 decision to serve the two skills the role cards already requested, and the pointer rule inside a skill (operator, 2026-11-10: the pack says what the worker is doing, the skill says how).

- **Six skills ship, not four:** `security-review` and `c-review` join the 11-05 amendment's four, under the same manifest, allow-list and `unevaluated` label. `security_reviewer` and `c_reviewer` need no card change: their `skills:` named these all along, and their runs go from "does not provide" to delivered. Every built-in card's `skills:` now ships, and a test keeps it so.
- **The pointer rule inside a skill.** `SKILL.md` is the always-read core of how to do the task; detail read only when the task needs it moves, verbatim, to `references/` and `examples/`, each with a "when X, read Y" line where it was. Both skills ship their candidate text split this way: `security-review`'s cryptography, secret-lifetime and untrusted-input steps (which its own procedure applies "only where the changed path implicates those properties"), and `c-review`'s C++ lifetime step and its defined-behavior, concurrency and ABI step. Their examples move to `examples/good/` and `examples/bad/`. The split is unmeasured: no model has run either skill.
- Tests: `tests/unit/test_skill_delivery.py` (the six, every requested skill shipped, the two reviewers' delivery).
