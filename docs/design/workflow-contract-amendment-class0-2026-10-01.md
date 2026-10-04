# Workflow Contract amendment: one classification system, and Class 0 eligibility

**Status:** Adopted 2026-10-01, accepted by the designer in review. It is the Workflow Contract change that the decisions of 2026-10-01 require (`plan-assurance-and-classification-decisions-2026-10-01.md` §2, §3.2; Q10). The frozen Workflow Contract (`agent-engineering-workflow-design-v0.7.md`, pinned by `docs/spec-pin.yaml`) is not edited; like the Ticket-revision amendment, this text amends it. **Enforced since M4-A (2026-10-03)** for mutating Tickets dispatched at Class 0, as §9 records; `aew guide` and `lead-guide.md` state the rule.

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
>   AEW enforces the predicate when Class 0 is requested. Eligibility is deterministic structural checks, plus recorded semantic assertions by the Lead, plus no active hard assurance trigger:
>   - a clear intended transformation or behavior is a recorded Lead assertion, and AEW requires an explicit objective and acceptance reference;
>   - for current supporting inputs, AEW verifies that every declared supporting input is current under its freshness contract, and the Lead asserts that no known decision-sensitive input was omitted.
>
>   A Class 0 request that fails the predicate is refused with reasons and never silently reclassified: the Lead chooses a stronger class. During evaluation, a sample of Class 0 work receives an independent audit, which tests whether the semantic assertions are trustworthy.

Classes 1–4 are unchanged.

## 3. Amended §7.4: examples

Replace:

> - Ticket + Class 0: one obvious mechanical edit.

with:

> - Ticket + Class 0: a mechanical edit, or a behaviour fix whose acceptance is a deterministic check, when the Class 0 predicate holds.

## 4. New paragraph after §7.4's class list: assurance on classes

> **Assurance gates and triggers.** Classes are the only classification. The §7.5 paths remain the baseline obligations for Classes 1–4. Hard assurance triggers add premise-sensitive obligations regardless of class: for example, a stakeholder-supplied diagnosis or premise that is adopted by, or materially constrains, the intervention or acceptance; an acceptance input inside the mutation scope; or an unexpected baseline result. A triggered Class 0 request fails eligibility. Default assurance floors beyond §7.5 for Classes 1–4 are evaluation hypotheses, not part of this contract until controlled dogfood supports them. The triggers are defined in the plan assurance design (v0.4 §22) and computed by one shared dispatch predicate.

## 5. Amended §7.5: the Class 0 path

Replace:

> **Ticket / Class 0:** Implement → focused check → complete, plus any inherited mandatory gates.

with:

> **Ticket / Class 0:** Class 0 eligibility verified → Implement → focused check → complete, plus any inherited mandatory gates. "Complete" retains §8's controlled integration semantics and any policy-required post-integration validation; this amendment removes no integration gate. During evaluation, a sample of Class 0 work receives an independent audit.

## 6. Unchanged, and how they fit

- **"Classification may increase whenever evidence exposes additional risk. Demotion requires an explicit Lead decision with rationale."** This stands. Refusing an ineligible Class 0 request is the engine-side counterpart of `AEW-INV-CLASS-001`: when a classifier can choose categories with different ceremony, the heavier one is the default.
- **Parent and child risk, and inherited policy.** This stands. "No inherited elevated obligation" in the predicate is how an ancestor's non-waivable gates and minimum-class floor reach Class 0.

## 7. Consequences outside the contract

- **`aew guide` and `lead-guide.md`:** generated from policy, so they state the predicate and the refusal once the engine implements it (F16).
- **Engine:** the Class 0 checker is one of M4's first-step items (decisions §3.5), returning its reasons through `DispatchDecision`.
- **Evaluation:** the Class 0 sampling rubric uses the same predicate (F19).
- **The rubric's T1 label** ("Class 0 is appropriate", dogfood A4 and A5) is consistent with the amended definition.

## 8. Decided in review (designer, 2026-10-01)

1. **The semantic assertions stay** during evaluation, as stated in §2. Narrowing Class 0 until everything is machine-checkable would make it unusable again. The sampled audit shows whether the assertions need stronger machinery.
2. **The audit sample rate** is an experimental knob. It is set in the shared evaluation preregistration (F19), not in this contract, which only requires a sampled audit during evaluation.

## 9. Decided while implementing the predicate (operator and designer, 2026-10-03)

M4-A centralized Class 0 eligibility in the dispatch predicate (`m4-ambiguity-report.md` §2.3). That surfaced a contradiction between this amendment and the frozen Knowledge Contract's acceptance case "Parent risk policy propagation" (KC v0.4 §26): there, a locally Class 0 Ticket beneath a Class 3 Story with a mandatory security review keeps Class 0, inherits the gate, and runs. Under §2 it is not eligible. The amendment stands; "no inherited elevated obligation" is not weakened. Decided:

1. **The Class 0 path (§5), tightened.** Replace:

   > **Ticket / Class 0:** Class 0 eligibility verified → Implement → focused check → complete, plus any inherited mandatory gates.

   with:

   > **Ticket / Class 0:** Class 0 eligibility verified → Implement → focused check → complete, plus inherited mandatory gates compatible with Class 0 eligibility. An inherited elevated obligation makes Class 0 ineligible and requires a stronger class.

   An inherited elevated obligation is an ancestor's non-waivable gate or its minimum descendant class. A mechanical local change is not automatically Class 0; parent obligations never disappear; Class 0 means "mechanical and no elevated inherited obligation".

2. **KC §26 "Parent risk policy propagation", amended acceptance case.** The frozen text is not edited; this replaces the case it describes:

   > **Inherited elevated risk.** A mechanically bounded Ticket is proposed as Class 0 beneath a security-sensitive Story carrying an elevated security obligation. Expected: Class 0 eligibility is refused with an inherited-elevated-obligation reason. The parent obligation remains effective. The Lead must select a stronger class satisfying any inherited minimum-class floor. After reclassification, the inherited gate is still required.

   The rest of the case stands: an explicit parent minimum descendant class raises the effective minimum only when recorded with the Lead's rationale. A local Class 0 Ticket beneath such a floor is refused the same way.

3. **Reclassification is a recorded decision.** Raising a class (WC §7.4: "classification may increase whenever evidence exposes additional risk") records the previous and new class, the reason, the actor with its Lead generation, and the effective minimum at the time of the decision, so that "why did this seemingly tiny Ticket become Class 2?" stays answerable. The engine refuses a class below an inherited floor. Lowering a class (demotion) is a separate decision and is not part of this.

4. **Scope of enforcement.** The predicate is enforced when a mutating Ticket is dispatched at Class 0. The amended path is a mutation path (implement, focused check, controlled integration), and its conditions (deterministic acceptance, mutation scope, protected paths) are defined for code changes. Non-mutating Tickets and Stories keep their Class 0 paths until those conditions are given non-mutating definitions.

5. **A bounded subject is measured (operator, 2026-10-03, after the independent review of dispatch legality).** §2's "a bounded, known subject" is enforced structurally: a scope is unbounded when any glob's first segment is `**`, when it matches no tracked file, or when it matches more than 50 tracked files or more than a quarter of the tracked tree. Both bounds can be changed in the gates policy (`class0.max_scope_files`, `class0.max_scope_fraction`). The refusal, and an admitted decision's `dependency_digests.class0_subject`, report the measure.

6. **A declared acceptance check belongs to a mutating Ticket.** Under item 4, a non-mutating Ticket's Class 0 path has no deterministic acceptance condition, so `--acceptance-check` on a non-mutating Ticket is refused at creation rather than recorded and never run.
