# Plan assurance and classification: decisions of 2026-10-01

- **What this is:** the operator's and designer's decisions on Q9 (plan assurance) and Q10 (risk-class calibration), recorded as given. They answer the implementer's questions raised after M3's acceptance.
- **Authority:** the decisions are the operator's and designer's. The texts they govern change separately, by their owners (§5). Until those changes land, this record and `future-work.md` point to it.
- **Sources:** `plan-assurance-and-premise-validation-design-v0.3.md` (§22, §26, §27, §33); `ticket-revision-amendment-2026-09-30.md` (F4); `failure-class-registry.md`; `invariant-index.md`; ADR-0010.

## 1. Q9: plan assurance (operator, 2026-10-01)

> Adopt Plan Assurance v0.3 as the post-M3 direction. ASSURED is a derived gate predicate, not a state. Initial implementation reuses Reviewer/Verifier infrastructure. Tier-A mechanical exemption exists from the start only when engine-checkable eligibility is satisfied and is sampled during dogfood. Hard protected-condition violations are non-waivable without a new attributable acceptance revision. Strong approved models are mandatory for Lead and acceptance/challenge during initial evaluation. Assurance tiers and routing/probe thresholds remain provisional until controlled dogfood demonstrates acceptable false-success and false-blocking behavior. Q9 does not block M4 implementation after ADR-0011, but assurance-compatible extension points and deterministic primitives should land early enough that M4 does not create conflicting workflow semantics.

## 2. One classification system (operator and designer, 2026-10-01)

> Delete Plan Assurance's Tier A–E naming. AEW gets one Class 0–4 classification system. Fold Tier A's positive criteria into the canonical Class 0 definition, and express assurance as gates/triggers layered onto those classes.
>
> That gives every Lead, guide, contract, engine check, evaluation rubric, and human operator exactly one answer to "what is Class 0?" instead of making them translate between two almost-but-not-quite-identical taxonomies.

Implementer's note, accepted with the decision: Tier B ("simple but premise-sensitive") does not map to a class. Its protections must survive as hard assurance triggers. Most are already in §22's trigger list; "mutable acceptance resource nearby" and "unexpected baseline result" are to be added.

## 3. Designer dispositions (2026-10-01)

### 3.1 Failure classes and invariants (the rest of Q9)

Reconcile §26 and §27 now, without copying all 15 names and 21 invariants into the indexes. The registry forbids document-local synonyms, and hierarchy concepts such as `SILENT_INTENT_REWRITE`, `EVIDENCE_MEANING_DRIFT`, `MISSED_REPLAN` and `STALE_PARENT_INTENT` already exist.

**Canonical plan-assurance failure classes (12):**
- `POISONED_PLAN_PREMISE`
- `ACCEPTANCE_UNDERSPECIFICATION`
- `ACCEPTANCE_CONDITION_MUTATION`
- `PROTECTED_ACCEPTANCE_OVERLAP`
- `ACCEPTANCE_BASELINE_INVALID`
- `PLAN_ASSURANCE_BYPASS`
- `ASSURANCE_DEPENDENCY_STALE`
- `PLAN_CHALLENGE_FALSE_CLEAR`
- `PLAN_CHALLENGE_FALSE_BLOCK`
- `EVALUATOR_INTEGRITY_FAILURE`
- `EXECUTION_PREMISE_CONTRADICTION`
- `HIERARCHICAL_ASSURANCE_LOSS`

**Merged, or represented as detail (3):**

| Candidate | Becomes |
|---|---|
| `INTENT_SUBSTITUTION` | the existing `SILENT_INTENT_REWRITE` |
| `PLAN_REVIEW_STALE` | `ASSURANCE_DEPENDENCY_STALE {dependency_kind: plan_review}` |
| `STAKEHOLDER_DIAGNOSIS_PROMOTION` | `POISONED_PLAN_PREMISE {premise_origin: stakeholder_diagnosis}` |

**Engine refusal codes are not failure-class names.** `PLAN_CHALLENGE_FALSE_CLEAR`, for example, can only be established by evaluation against gold evidence; the engine cannot know at dispatch time that its challenger falsely cleared something. A deterministic check emits its own code (for example `PROTECTED_CONDITION_OVERLAP`), which is associated with the canonical class (`PROTECTED_ACCEPTANCE_OVERLAP`). This keeps the registry from becoming a list of CLI error codes.

**Invariant index: add only the genuinely new cross-document assurance invariants:**
1. independent acceptance before plan exposure;
2. acceptance resources and protected conditions are distinct from the mutation subject;
3. a baseline counts only if it exercised the proposition;
4. assurance binds the versioned dependency set;
5. review metadata cannot change the payload it reviews;
6. clearing a blocker is attributable, not a rewrite of the blocker;
7. every dispatch path uses one computed predicate;
8. a contradicted load-bearing premise holds the affected mutation;
9. inherited obligations cannot disappear at a child;
10. passing children do not prove composition.

Existing authority, stakeholder, hierarchy and evidence invariants are referenced, not duplicated.

### 3.2 Class 0 eligibility (Q10; the former Tier A)

There is no Tier A any more, only Class 0 eligibility. The term is removed from normative plan-assurance material. One engine-side checker answers both questions:

```text
class0_eligible(work) =
    bounded known subject
    AND clear intended transformation/behavior
    AND no unresolved diagnosis/premise ambiguity
    AND current supporting inputs
    AND deterministic acceptance
    AND no protected-acceptance mutation
    AND no consequential security/trust/persistence/compatibility boundary
    AND no inherited elevated obligation
```

A Class 0 Ticket that fails the predicate is not silently reclassified. AEW refuses the Class 0 path, with reasons, and tells the Lead that a stronger class is required. The Lead keeps the decision, and nothing can exempt itself. This resolves Q10 and gives the Workflow Contract, the guide, F14, the engine, the evaluation rubric and the Lead one definition of "simple or mechanical".

### 3.3 "A new attributable acceptance revision" is an F4 Ticket revision

There is no third revision lineage. A legitimate acceptance change becomes a new Ticket revision (for example `T-17@r3`). When acceptance-related field digests change, the old assurance becomes invalid or is revalidated as appropriate, the plan may need revision or reconfirmation, and the new assurance binds `T-17@r3`'s digests. If the change no longer overlaps the Ticket's goal, or crosses the approved parent envelope, F4's replacement and parent-revision rules apply instead.

### 3.4 Strong models and budget are frozen with the evaluation

Model names are not part of the architectural decision. ADR-0010 execution profiles for the Lead, independent acceptance reconstruction and the Plan Challenger are pinned when the experiment is preregistered. The first comparison keeps the strong model and profile constant across assurance arms, so that it tests workflow architecture rather than model quality. The planned model-placement ablation is a separate run. The budget is frozen with the corpus and run counts, not before the experimental matrix is known.

### 3.5 M4's first step

M4 lands exactly these four things first:
1. one shared dispatch predicate;
2. protected-condition records and checks;
3. the Class 0 eligibility checker;
4. deterministic plan lint.

Additionally:
- The predicate returns a **typed decision with durable reason codes and effective obligations**.
- A **conformance test** proves that every dispatch route uses it. M4's queue, stage commands, the CLI, the harness adapter and the future scheduler must not each grow their own interpretation.
- It is **not called `ASSURED`** during the evaluation period:

  ```text
  DispatchDecision {
      allowed
      effective_obligations
      blocking_conditions
      reason_codes
      dependency_digests
  }
  ```

  At first it is permissive except for the existing gates, hard protected-condition failures, and Class 0 eligibility where Class 0 is requested. Later, F14 makes the full assurance package another input to the same predicate, without rewiring M4.
- M4 may cache "candidate runnable", but **actual dispatch recomputes the predicate against the current revision and generation. An old ALLOW is never cached.**

### 3.6 One evaluation program

Q7 (the next dogfood), F14 phases 1–4, the F17 corpus and Class 0 sampling share:
- one fixture format;
- one runner;
- one run-record schema;
- one hidden-evaluator mechanism;
- one model and profile configuration;
- one metrics collector.

The experiments stay **separately preregistered** inside that harness. Shared infrastructure does not make one run four independent samples:
- Q7 scores root-cause and final correctness, and rework;
- F14 scores bad-plan escape and false blocking;
- Class 0 scores eligibility correctness, ceremony and cost.

One immutable run can contribute evidence to several metrics, but it remains one run.

## 4. Questions these decisions close

| Register entry | Closed by |
|---|---|
| Q9, the remaining reconciliation part | §3.1 |
| Q10, risk-class calibration | §2, §3.2 |
| Q6, whether O3 becomes a registry class | §3.1: `ACCEPTANCE_CONDITION_MUTATION` is canonical |

O3 itself stays open until F14's fix is accepted.

## 5. What changes where

| Text | Change | Owner |
|---|---|---|
| Workflow Contract (class definitions) | Class 0 defined by the eligibility predicate (§3.2); assurance as gates and triggers on classes | Designer: a contract amendment |
| `plan-assurance-and-premise-validation-design-v0.3.md` | Remove the Tier A–E naming; Tier B's items become hard triggers (§2); refusal codes separate from failure classes (§3.1); acceptance revision = F4 Ticket revision (§3.3); `DispatchDecision` before `ASSURED` (§3.5) | Designer: a design revision |
| `failure-class-registry.md` | The 12 canonical classes and the 3 mappings (§3.1) | Designer (index owner) |
| `invariant-index.md` | The 10 new assurance invariants (§3.1) | Designer (index owner) |
| ADR-0010 | Evaluation execution profiles pinned at preregistration (§3.4) | With the evaluation |
| M4's ambiguity report | §3.5 as M4's first step | Implementer, at M4 planning |
| `future-work.md` | Q6, Q9 and Q10 closed; F14 updated; one evaluation program | This change |
