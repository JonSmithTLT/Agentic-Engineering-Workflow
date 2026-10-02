# Workflow Contract amendment: one classification system, and Class 0 eligibility

**Status:** DRAFT for designer review (implementer, 2026-10-01). Not adopted. It drafts the Workflow Contract change that the decisions of 2026-10-01 require (`plan-assurance-and-classification-decisions-2026-10-01.md` §2, §3.2; Q10). The frozen Workflow Contract (`agent-engineering-workflow-design-v0.7.md`, pinned by `docs/spec-pin.yaml`) is not edited. Like the Ticket-revision amendment, this text amends it once adopted.

**Amends:** Workflow Contract v0.7 §7.4 (risk/complexity classes) and §7.5 (minimum paths).

## 1. Why

- The M3 dogfood showed that the prose definition of Class 0 ("trivial/mechanical … one obvious mechanical edit") made Class 0 unreachable for a behaviour fix backed by a test. With the contract's wording in the guide, every guided Lead chose Class 1, at about twice the cost (`future-work.md` Q10; `m3-dogfood-report.md` §6.5).
- Plan assurance proposed a second taxonomy (Tiers A–E) whose Tier A was almost, but not quite, Class 0. The operator and designer decided on one system (decisions §2).

## 2. Amended §7.4: the Class 0 bullet

Replace:

> - **Class 0 — trivial/mechanical:** obvious bounded change with little behavioral ambiguity.

with:

> - **Class 0 — eligible mechanical work:** work for which the Class 0 eligibility predicate holds:
>   - a bounded, known subject;
>   - a clear intended transformation or behavior;
>   - no unresolved diagnosis or premise ambiguity;
>   - current supporting inputs;
>   - deterministic acceptance;
>   - no mutation of protected acceptance resources;
>   - no consequential security, trust, persistence or compatibility boundary;
>   - no inherited elevated obligation.
>
>   AEW checks the predicate when Class 0 is requested, deterministically where it can and by recorded Lead attestation for the rest. A Class 0 request that fails it is refused with reasons and never silently reclassified: the Lead chooses a stronger class.

Classes 1–4 are unchanged.

## 3. Amended §7.4: examples

Replace:

> - Ticket + Class 0: one obvious mechanical edit.

with:

> - Ticket + Class 0: a mechanical edit, or a behaviour fix whose acceptance is a deterministic check, when the Class 0 predicate holds.

## 4. New paragraph after §7.4's class list: assurance on classes

> **Assurance gates and triggers.** Classes are the only classification. Plan assurance adds obligations to them: a baseline per class, and hard triggers that apply regardless of class (for example a stakeholder-provided suspected cause, a mutable acceptance resource near the mutation scope, or an unexpected baseline result). A triggered Class 0 request fails eligibility. The obligations and triggers are defined in the plan assurance design (§22) and computed by one shared dispatch predicate.

## 5. Amended §7.5: the Class 0 path

Replace:

> **Ticket / Class 0:** Implement → focused check → complete, plus any inherited mandatory gates.

with:

> **Ticket / Class 0:** Class 0 eligibility verified → Implement → focused check → complete, plus any inherited mandatory gates. During evaluation, a sample of Class 0 work receives an independent audit.

## 6. Unchanged, and how they fit

- **"Classification may increase whenever evidence exposes additional risk. Demotion requires an explicit Lead decision with rationale."** This stands. Refusing an ineligible Class 0 request is the engine-side counterpart of `AEW-INV-CLASS-001`: when a classifier can choose categories with different ceremony, the heavier one is the default.
- **Parent and child risk, and inherited policy.** This stands. "No inherited elevated obligation" in the predicate is how an ancestor's non-waivable gates and minimum-class floor reach Class 0.

## 7. Consequences outside the contract

- **`aew guide` and `lead-guide.md`:** generated from policy, so they state the predicate and the refusal once the engine implements it (F16).
- **Engine:** the Class 0 checker is one of M4's first-step items (decisions §3.5), returning its reasons through `DispatchDecision`.
- **Evaluation:** the Class 0 sampling rubric uses the same predicate (F19).
- **The rubric's T1 label** ("Class 0 is appropriate", dogfood A4 and A5) is consistent with the amended definition.

## 8. Open for the designer

1. Should "current supporting inputs" and "clear intended transformation" stay Lead-attested, as drafted, or be narrowed until the engine can check them?
2. Should the evaluation-period sample rate for Class 0 audits be set here, or by the evaluation preregistration (F19)?
