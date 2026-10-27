<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-04
source: 10-adopted/RECONCILED-SOURCE-BASELINE/01-ADOPTED-SOURCE-BYTES/A-04__AEW-engineering-workflow-umbrella-contract-candidate-v0.4.md
source-sha256: 34ab99d49cc32f630870106b4ca2bfbc55a7d64947c63a4e40429761a940f764
edits-sha256: none
-->

# AEW Engineering Workflow Umbrella Contract — Candidate v0.4

**Status:** Principal-designer proposal — **NOT OPERATOR-ADOPTED**  
**Date:** 2026-10-13  
**Document role:** Proposed system-wide behavioral contract for the normal engineering journey  
**Derivation basis:** *AEW Foundational Requirements — Candidate Baseline v0.4* (`AEW-FR-NN.x`); operator's elicited routine-counter and substantial-integration-test workflows; foundational scenarios `AS-XX`  
**Historical implementation status:** Not assessed by this contract  
**Conformance status:** Not implementation-tested; Round 1 principal-designer tabletop exists, with review-driven amendments and additional proposed exercises; no completed independent conformance test  
**Authority notice:** Favorable discussion of foundational v0.4 is not treated here as an explicit adoption record. This contract cannot adopt the baseline, change effective AEW authority, or supersede live security, revocation, containment, or evidence controls.

**v0.4 change basis:** Narrow reconciliation of two focused v0.3 reviews. Strengthens comparison of proposed interpretations to original requests and existing behavior, assessment of overlooked premises, governing-check integrity, and bounded protection during credible urgent premise disputes. Separately performs design tabletop exercises `EW-X09`–`EW-X12`. All guarantees remain **proposed**, and tabletop analysis is **not** executable conformance evidence.

## 1. Executive intent

AEW must behave like a capable delegated engineering organization. The responsible authority specifies what is to be achieved. AEW establishes sufficient understanding, proposes consequential choices for confirmation, executes authorized engineering work, checks the actual outcome, preserves evidence, and reports results without demanding approval for routine details.

The **routine path** should feel like: *"Add a counter" → determine its impact using available project information → implement or delegate → perform applicable checks → report with evidence*. A separate investigator, planner, and independent review ceremony are **not universally required**.

The **substantial path** should feel like: *"Build the integration-test suite" → elicit and confirm intent → investigate relevant software and rationale → produce an assessable plan → independently challenge the plan against the original requirements → obtain implementation authorization → assign and coordinate work with an integration-proving responsibility → review changes → independently verify the integrated result → report an evidence-qualified outcome*. The Lead is accountable for the synthesis and coordination; AEW should perform routine bookkeeping and evidence plumbing without expensive Lead reconstruction.

**Umbrella rule:** The path's **assurance depth** depends on the governing constraints, observable engineering risks, dependencies, uncertainty, and delegated authority. It does **not** depend on whether AEW can spawn five agents, nor on line count, agent confidence, or a convenient label such as “trivial.”

**Qualitative intake signals (interpretive examples, not newly adopted class thresholds):** Changes to execution topology, protected effect boundaries, or an operator-stated requirement are consequential classification inputs; two contributions to one required behavior require an integration-evidence responsibility; alterations to governing verification checks require independently qualified assessment under the foundational rule; irreversible operations require the applicable authority and risk controls. A routine local counter that affects none of these may still use an economical path. These examples **do not** establish numerical classes or permit bypass of stricter effective controls. Where a required classifier input or rule is absent, the affected dispatch remains held unless an established more-protective authorized rule applies.

### 1.1 In scope

This umbrella defines the cross-role guarantees that connect objective interpretation, research, planning, implementation authorization, decomposition, integration, review, final verification, completion, exceptions, and durable history. It defines guarantees for the **hand-offs between these responsibilities**, independent of the particular models, tools, repositories, storage schema, or CLI commands used.

### 1.2 Out of scope

The contract does **not** define the full authority-token protocol, ticket state machine, tool-call mediation, branch/worktree technology, model-routing algorithm, knowledge-store schema, specific test tooling, or thresholds for risk, cost and time. Those belong to subordinate contracts or operator-adopted policy. This contract also does not replace the effective controls currently guarding those boundaries.

### 1.3 Normative reading

Each `EW-Uxx.y` below is **one independently assessable proposed obligation**. The section title is organizational, not another requirement. **Shall** indicates proposed mandatory behavior *if the contract is adopted and applicable*. **May** indicates permission, not an imposed execution step. A disconfirmation witness illustrates one violation; it is not a complete test plan.

The `AEW-FR` citations are **candidate derivation links**, not declarations that those foundational clauses have been formally adopted. `AS-XX` references identify the versioned v0.4 scenarios. This contract may refine behavioral guarantees but may **not silently add operator authority, loosen a foundational obligation, or resolve an unsettled operator choice by inventing a policy**.

**Priority when obligations conflict:** Applicable authority and safety controls take precedence over discretionary context preservation and optimization. Truthful, attributable evidence and work history take precedence over a convenient completion claim. Undefined parameters do not grant permission to take a less controlled path. Ambiguity requiring a consequential authority decision is held or escalated for that dependency, not converted into a global project stop.

## 2. Boundary vocabulary and normal-flow roles

| Term | Meaning for this umbrella | Not a mandate for |
|---|---|---|
| **Responsible authority** | Person or body permitted to confirm a particular objective, contract boundary, plan or change | A single universal operator for all projects |
| **Lead** | Accountable coordinator of delegated engineering interpretation, assignments, synthesis and escalation | A particular model or an uninterrupted conversation |
| **Investigation** | Establishing relevant facts, dependencies, rationale and uncertainty for an objective | Always spawning a research agent |
| **Planner** | Responsibility for producing an implementation proposal satisfying confirmed requirements | A dedicated process for every small edit |
| **Plan assessor** | Responsibility for challenging a consequential plan against protected original requirements, feasibility and dependencies | Trusting the planner's synopsis of the request |
| **Implementer** | Actor carrying out scoped engineering changes and producing related evidence | Independent power to change acceptance criteria |
| **Implementation reviewer** | Actor evaluating delivered changes against assigned obligations and required quality constraints | Automatically proving integrated behavior |
| **Final verifier** | Actor independently assessing the integrated outcome and evidence against applicable original requirements | Only rerunning existing green tests |
| **Integration responsibility** | Explicit ownership for establishing compatibility and the composed behavior required by an objective | Always adding a third agent or ticket |
| **Technical completion** | Applicable engineering, review and verification conditions met under declared qualifications | Operator's endorsement of the entire intended outcome |

Roles are **responsibilities**, not fixed seats. One authorized actor may serve several roles when the governing assurance policy permits it. A self-check must be labeled a self-check; an operator's actual inspection can serve an applicable human-review responsibility but does not replace mandatory execution evidence or protected independent assessment.

### 2.1 Required durable references (logical information, not storage schema)

An authorized engineering item must have an inspectable connection to its accepted objective and boundary, current revision, governing requirements/acceptance conditions, delegated authority, material dependencies and the evidence supporting any completion claim. When consequential, the chain must also identify the operator-confirmed interpretation, the accepted plan or execution direction, the responsible implementer/reviewer/verifier, integration responsibilities, findings and decisions. These may be realized through the existing work record and linked artifacts; **this is not a proposal for a new defect tracker or duplicate authority ledger**.

An agent-authored plan, summary, memory entry, project map, review conclusion or test log is **not itself an authorization**. Each can supply information or qualified evidence under an applicable rule.

**Source-preserved intent:** The original operator/request-authority input, subsequent clarifications, and explicit acceptance decisions remain separately attributable. A normalized acceptance interpretation is a useful derivative, not a replacement for the source request. Direct requests may already authorize bounded routine work under delegation rules; this umbrella does **not** demand a second ceremonial operator signoff for every Ticket.

**Discovered uncertainty:** Source records can reveal consequential existing behavior that the operator did not enumerate. Agents must not treat the absence of a detail from a short request or a paraphrase as evidence that the behavior can be discarded.

## 3. Normative cross-role guarantees

### EW-U01 — Admission and authority of the objective

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U01.a` | Before work is admitted for dependent execution, AEW shall associate the objective with the responsible authority for its affected requirement boundaries. | `AEW-FR-01.a`, `AEW-FR-02.b` | An agent dispatches work against a boundary using approval from an unrelated authority. |
| `EW-U01.b` | AEW shall distinguish permission to **investigate or propose** work from permission to implement the proposed consequential changes. | `AEW-FR-02.a`, `AEW-FR-02.c` | A researched proposal becomes a change authorization because a researcher recommended it. |
| `EW-U01.c` | AEW shall preserve the source request and authority-confirmed acceptance basis so that agent-authored interpretations cannot replace either without a traceable authorized change. | `AEW-FR-03.b`, `AEW-FR-12.f`, `AEW-FR-23.a` | The accepted remote-hop objective is replaced by a shortened local-install paraphrase without an attributable decision. |
| `EW-U01.d` | AEW shall not treat a proposed change to scope, governing requirements or acceptance conditions as effective without an appropriate authority decision. | `AEW-FR-02.b`, `AEW-FR-05.a` | A worker's discovered defect expands an approved feature into unrelated remediation. |
| `EW-U01.e` | AEW shall retain the attributable original request and subsequent material clarifications as retrievable source records for dependent planning and assessment. | `AEW-FR-03.b–c`, `AEW-FR-17.a`, `AEW-FR-23.a` | A plan verifier has only a Lead rewrite of the deployment request and cannot retrieve the original wording. |
| `EW-U01.f` | Where consequential acceptance interpretations require the responsible authority’s confirmation, AEW shall preserve the interpreted criteria and the authority’s attributable acceptance or correction before dependent implementation. | `AEW-FR-02.b`, `AEW-FR-03.b`, `AEW-FR-39.c` | The Lead records its own criterion list as “operator accepted” without the operator having confirmed its material interpretation. |
| `EW-U01.g` | A change presented as correction within already authorized scope shall be justified against the accepted objective and applicable governing constraints; unresolved consequential departures shall be referred to the responsible authority. | `AEW-FR-02.b–c`, `AEW-FR-03.b`, `AEW-FR-05.a` | The Lead describes removal of an unconfirmed VM hop as a mere plan correction to evade a consequential scope decision. |
| `EW-U01.h` | For a port, migration, replacement, or comparable task derived from an existing artifact, AEW shall identify material observable behaviors and effects of that artifact relevant to the requested outcome, and record whether each is retained, changed with appropriate authority, or established as inapplicable. | `AEW-FR-03.a–c`, `AEW-FR-23.a`, `AEW-FR-39.f` | The original installer performs intermediate remote hops, but the proposed port drops them without their being identified or dispositioned. |
| `EW-U01.i` | When requesting confirmation of a consequential interpretation, AEW shall present material differences between that interpretation, the source request, and the qualified existing-system evidence available for that decision. | `AEW-FR-03.b–c`, `AEW-FR-39.b–c`, `AEW-FR-28.d` | An operator says 'sounds good' to a local-install summary without being shown that the original workflow has three remote hops. |

### EW-U02 — Task understanding and proportional depth

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U02.a` | Before committing to a dependent implementation approach, AEW shall establish sufficient objective-specific understanding to identify affected boundaries and applicable obligations. | `AEW-FR-03.a–c`, `AEW-FR-19.b` | A port is planned without examining the original deployment topology available to AEW. |
| `EW-U02.b` | AEW shall permit qualified project records, maps, knowledge or targeted inspection to establish required task understanding without a mandatory separate investigator. | `AEW-FR-06.a`, `AEW-FR-09.d`, `AEW-FR-19.a–d` | The Lead must hire an investigator despite a current, sufficient map and verified procedure for a small counter. |
| `EW-U02.c` | AEW shall pursue further investigation or authority clarification when relied-upon information is stale, contradictory or insufficient for a consequential decision. | `AEW-FR-03.b`, `AEW-FR-23.d`, `AEW-FR-39.c` | A stale project map is treated as dispositive despite evidence that the boundary changed. |
| `EW-U02.d` | AEW shall establish the applicable minimum assurance/control level from authorized classification rules and observable work properties, not solely from an agent's confidence or chosen process label. | `AEW-FR-06.b–c`, `AEW-FR-39.f–g` | The Lead calls a deployment-topology change “trivial” to bypass required plan review. |
| `EW-U02.e` | AEW shall allow a lightweight path for bounded work when the governing classification and accepted objective do not require more elaborate planning or assessment. | `AEW-FR-03.d`, `AEW-FR-06.a`, `AEW-FR-05.b` | Every local counter change requires an Epic-sized plan and review board. |
| `EW-U02.f` | Use of a lightweight path shall not remove applicable authority, safety, integrity, or verification obligations. | `AEW-FR-06.c`, `AEW-FR-13.d` | A required Valgrind gate is skipped because the code change is small. |
| `EW-U02.g` | Before selecting an execution path, AEW shall obtain the classification inputs required by the authorized rule from qualified evidence; when the required input or protective rule is absent, AEW shall hold the affected dispatch unless a separately established applicable protective rule permits it. | `AEW-FR-03.a–c`, `AEW-FR-39.b`, `AEW-FR-39.f–g` | Unknown deployment topology is treated as safe simply because no one inspected the original installer. |
| `EW-U02.h` | A classification decision shall not rely solely on the Lead’s or another agent’s unsupported summary where observable source or qualified project evidence is needed to establish an applicable control floor. | `AEW-FR-03.a`, `AEW-FR-39.b`, `AEW-FR-39.f` | A Lead-authored “single host” plan outranks the original script’s observable multi-host deployment path. |

### EW-U03 — Elicitation, research and requirements fidelity

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U03.a` | When the available request and project evidence permit materially different engineering outcomes, AEW shall obtain consequential clarification or confirmation before authorizing dependent implementation. | `AEW-FR-03.b`, `AEW-FR-39.c` | AEW treats omission of intermediary hops from a short request as permission to remove them, without asking. |
| `EW-U03.b` | AEW shall keep consequential unconfirmed assumptions attributable and visible to the relevant decision-maker before work relies on them. | `AEW-FR-03.c`, `AEW-FR-39.b` | The Lead silently assumes a remote hop can be removed without recording the assumption. |
| `EW-U03.c` | For consequential or research-intensive work, AEW shall establish the operator-confirmed interpretation of the requested requirements as an assessable input to subsequent planning and final verification. | `AEW-FR-02.b`, `AEW-FR-12.f`, `AEW-FR-16.c` | The final assessor can see only a planner's revised objective, not what the operator approved. |
| `EW-U03.d` | AEW shall make research findings that materially affect scope, feasibility, dependencies or risk available to the Lead for judgment and necessary authority escalation. | `AEW-FR-04.a–b`, `AEW-FR-24.d` | A researcher finds a fatal concurrency assumption but the planner never learns of it. |
| `EW-U03.e` | Before beginning a consequential planning effort, the Lead shall establish that the available understanding supports a credible plan and identify material unresolved questions or limitations. | `AEW-FR-03.b–c`, `AEW-FR-04.a` | A plan proceeds as if the test environment is known while a crucial connection-lifecycle dependency remains unidentified. |

**Interpretation:** Research may occur before or during elicitation to uncover the right questions. “Ready to plan” does **not** mean “all questions answered.” It means consequential uncertainty is visible and handled in the plan rather than hidden under confident prose.

### EW-U04 — Planning, adversarial assessment and adoption

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U04.a` | Where a governing rule requires a consequential plan, AEW shall maintain a proposal that connects the authorized objectives to intended work and the obligations needed to demonstrate completion. | `AEW-FR-02.a–b`, `AEW-FR-07.e`, `AEW-FR-12.b` | An integration suite plan omits who will establish cleanup behavior or how it will be checked. |
| `EW-U04.b` | A required plan assessment shall compare the plan independently against the preserved, authority-confirmed requirements rather than rely solely on the planner's summary. | `AEW-FR-12.f`, `AEW-FR-03.b` | The plan assessor approves while a confirmed concurrency-cleanup requirement is missing from the plan. |
| `EW-U04.c` | A required plan assessment shall challenge the plan's material dependency, integration, feasibility and evidence obligations. | `AEW-FR-07.d–e`, `AEW-FR-12.g` | The plan verifier checks grammar but overlooks that two parallel components have no integration proof owner. |
| `EW-U04.d` | AEW shall not present a consequential plan as **successfully assessed and eligible for implementation authorization** while required material assessment findings remain unresolved. | `AEW-FR-12.f`, `AEW-FR-14.d` | An assessor rejects missing coverage and the same plan is represented as approved. |
| `EW-U04.e` | When operator approval is required, the Lead shall present the proposed approach with a concise decision summary and a retrievable full plan before dependent implementation begins. | `AEW-FR-02.b`, `AEW-FR-28.d` | A complex plan is dispatched to workers before the operator sees or approves it. |
| `EW-U04.f` | AEW shall bind implementation authorization to the accepted plan or scope revision so material changes cannot borrow an earlier approval by implication. | `AEW-FR-02.b–c`, `AEW-FR-07.b`, `AEW-FR-31.b` | A materially rewritten plan is executed using authorization for the prior plan. |
| `EW-U04.g` | Where consequential plan approval is sought, AEW shall make the original assessor findings independently retrievable by the approver rather than substituting only the Lead’s interpretation. | `AEW-FR-12.f`, `AEW-FR-14.d`, `AEW-FR-28.d` | A Lead summarizes a rejected plan as “approved with minor comments” while hiding the assessor’s original findings. |
| `EW-U04.h` | AEW shall disclose unresolved material plan-assessment findings in the authorization presentation before the approver decides. | `AEW-FR-12.b`, `AEW-FR-14.d`, `AEW-FR-28.d` | The operator approves a plan unaware the independent assessor still disputes coverage of cleanup failures. |
| `EW-U04.i` | A required plan assessment shall compare declared load-bearing premises with the preserved request and relevant qualified project evidence, and shall identify consequential reliance that the plan omitted. | `AEW-FR-03.a–c`, `AEW-FR-12.f`, `AEW-FR-39.f` | The plan identifies only its declared local-install premise; the assessor never checks the original script showing remote-hop dependencies. |

**Interpretation:** An unresolved or rejected plan may still be presented to the responsible authority **for disposition of the finding**; that does not make dependent implementation eligible. The Lead may gather research or prepare proposals before approval. Rejected plans return for revision and reassessment of affected obligations. This contract does not prescribe a planner model, a document format beyond retrievability, or a fixed count of review cycles.

### EW-U05 — Decomposition, assignment, and integration ownership

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U05.a` | Before dispatching dependent implementation work, AEW shall identify each assignment's governing objective, scope and acceptance responsibilities. | `AEW-FR-05.a`, `AEW-FR-07.a–b` | A worker receives “implement connections” with no trace to its assigned criteria. |
| `EW-U05.b` | AEW shall preserve applicable parent and cross-boundary obligations when decomposing a larger work item into child assignments. | `AEW-FR-07.e`, `AEW-FR-12.g` | A security or cleanup requirement disappears because no child Ticket claimed it. |
| `EW-U05.c` | Before authorizing parallel execution, AEW shall assess material dependencies and foreseeable interference among concurrent assignments under the applicable control rules. | `AEW-FR-09.b`, `AEW-FR-37.a–c` | Two workers unknowingly overwrite the same mutable implementation or test fixture. |
| `EW-U05.d` | Before dispatch of contributors to required composed behavior, AEW shall assign responsibility for obtaining integration evidence whenever their outputs jointly realize a parent obligation, including shared-interface dependencies unless a qualified exception is established. | `AEW-FR-07.d–e`, `AEW-FR-12.d`, `AEW-FR-12.g` | Two separate workers deliver helper and consumer with no owner for proving their combined behavior because the plan marked integration “not applicable.” |
| `EW-U05.e` | AEW shall not treat a planned integration check or a designated integration owner as evidence that actual integration has passed. | `AEW-FR-12.a`, `AEW-FR-14.a` | “Integration: owned by Worker C” is reported as a successful integration result before execution. |
| `EW-U05.f` | The Lead shall be able to reassign or serialize implementation work within the accepted objective when credible new evidence undermines the original decomposition. | `AEW-FR-11.a–c` | Two assignments are clearly duplicative but cannot be reconciled without an unrelated operator scope decision. |
| `EW-U05.g` | Reorganization of assignments shall preserve already established findings, artifacts, qualifications and applicable proof obligations. | `AEW-FR-11.b`, `AEW-FR-14.b` | Consolidating B and C discards the known failure and treats unrerun tests as current proof. |
| `EW-U05.h` | Each assignment shall expose material premises on which its execution or acceptance depends, linked to available evidence and relevant parent/dependency relationships. | `AEW-FR-04.a–d`, `AEW-FR-07.a–b`, `AEW-FR-08.b` | A worker continues on a known unsupported local-install assumption because no work record or source link identifies the reliance. |

**Interpretation:** “Integration owner” is a responsibility, not a mandated extra worker or Ticket. Proving compatibility may be performed by an implementer, an assigned integration activity, or another qualified participant. Independence rules still apply to the subsequent assessment.

### EW-U06 — Implementation, evidence production, and change review

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U06.a` | An implementer shall carry out changes only within its current authorized assignment and permitted effect boundaries. | `AEW-FR-05.a`, `AEW-FR-31.b` | A worker “fixes” an unrelated production defect discovered while writing tests. |
| `EW-U06.b` | An implementer's completed-work handoff shall identify the changed subject and evidence supporting claimed satisfaction of assigned obligations. | `AEW-FR-12.a–b`, `AEW-FR-14.a` | The worker reports “done, all green” with no identifiable change or test execution. |
| `EW-U06.c` | AEW shall route delivered changes through the implementation review required by the applicable assurance classification. | `AEW-FR-06.b–c`, `AEW-FR-12.c` | A protected change bypasses a mandatory reviewer because the Lead trusts the implementer. |
| `EW-U06.d` | A required implementation review shall assess the delivered subject against its assigned criteria and relevant engineering quality obligations, independently of an unverified implementer conclusion. | `AEW-FR-12.f`, `AEW-FR-12.c` | Reviewer approves solely because the builder said its patch was correct. |
| `EW-U06.e` | AEW shall represent a Lead reviewing its own implementation as a self-check, not as independent assessment. | `AEW-FR-12.f`, `AEW-FR-14.d` | A Lead marks its own spot check as satisfying a separate independent-review gate. |
| `EW-U06.f` | A deficient implementation or review shall return the affected work for correction without converting a failed check into a passing outcome. | `AEW-FR-13.a–c`, `AEW-FR-14.c` | A test failure disappears when a worker submits a revised patch without requalification. |

**Interpretation:** A small change may legitimately be checked by the Lead, by the operator through actual inspection, or by a lower-cost independent reviewer according to the governing assurance rules. This contract does not claim that operator inspection replaces execution evidence, nor that every self-check is an independent review.

### EW-U07 — Composition and final verification

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U07.a` | Before claiming integrated completion, AEW shall establish the current integrated subject to which the claim and supporting evidence apply. | `AEW-FR-14.a–b`, `AEW-FR-12.g` | Tests on individual feature branches are claimed as proof of a different combined state. |
| `EW-U07.b` | AEW shall obtain applicable integration evidence for required interactions among delivered components, not infer it from their separate local PASS results. | `AEW-FR-07.d`, `AEW-FR-12.d`, `AEW-FR-12.g` | All children pass but parent integration is declared verified despite an untested shared lifecycle. |
| `EW-U07.c` | A required final verifier shall evaluate the integrated result against the preserved, applicable original requirements and accepted changes to those requirements. | `AEW-FR-12.b`, `AEW-FR-12.f`, `AEW-FR-16.b` | Final approval cites only each worker's Ticket summary, omitting the operator's cleanup requirement. |
| `EW-U07.d` | A required final verifier shall assess whether the available evidence actually demonstrates the behavior claimed, rather than treat execution success as sufficient for an unproven capability. | `AEW-FR-12.a–b`, `AEW-FR-14.d` | A concurrency test suite passes despite accidental serialization, yet is certified as testing races. |
| `EW-U07.e` | When required evidence is missing or contradicted, the verifier shall decline the corresponding unqualified verification claim and identify the affected obligation. | `AEW-FR-14.c–d`, `AEW-FR-13.b` | The verifier records “PASS” despite no evidence for required failure-path cleanup. |
| `EW-U07.f` | AEW shall not accept a governing check, criterion, exclusion, threshold or relevant test input altered by **any participant** as proof for an unchanged obligation without the independent authorization, assessment and requalification required by the governing assurance rule. | `AEW-FR-12.f`, `AEW-FR-13.a`, `AEW-FR-14.a–b` | A builder or verifier changes a failing cleanup assertion and its resulting PASS is accepted without the required independent requalification. |
| `EW-U07.g` | AEW shall not use successful final verification of only the observed conditions to assert broader certainty or satisfaction of untested obligations. | `AEW-FR-14.d`, `AEW-FR-15.d` | A test run on one configuration is advertised as proof of all deployment modes. |
| `EW-U07.h` | Where independent review is required for changes to an assessed implementation, an assessor who makes those changes shall not satisfy the independent-review obligation for those changes through its own assessment. | `AEW-FR-12.c`, `AEW-FR-12.f`, `AEW-FR-14.a` | A reviewer rewrites a failing component and certifies the same patch as independently reviewed without another qualified assessment. |
| `EW-U07.i` | AEW shall determine whether a changed test, fixture or input is within the governing verification basis using authorized assurance criteria independent of the changing participant's unsupported classification. | `AEW-FR-13.a`, `AEW-FR-12.f`, `AEW-FR-39.b` | A test author calls a removed required assertion 'non-governing' and thereby exempts its own green run from requalification. |
| `EW-U07.j` | AEW shall permit routine authorized maintenance of test materials outside the governing verification basis without imposing changed-governing-check reassessment solely because a file was edited, while retaining otherwise applicable checks. | `AEW-FR-06.a–c`, `AEW-FR-13.a`, `AEW-FR-05.b` | Updating an unrelated fixture description automatically requires a protected assurance review despite no effect on governing tests, inputs or obligations. |

**Interpretation for a test-suite deliverable:** When the objective is to **build tests that can detect specified failures**, evidence should address that detection claim, not merely that tests pass on currently correct code. Depending on the defined risk and acceptance conditions, credible methods could include targeted fault injection, controlled failure fixtures, demonstrable assertions against failure paths, or another independently assessed method. No single technique is mandated universally.

### EW-U08 — Completion, reporting, and operator attention

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U08.a` | AEW shall distinguish implemented, reviewed, verified, technically complete, and operator-accepted claims in its work reports. | `AEW-FR-12.a–c`, `AEW-FR-16.a–b` | “Merged and tested” is presented as explicit operator acceptance. |
| `EW-U08.b` | AEW shall permit routine authorized work to advance after its applicable technical completion obligations are satisfied without unrequired operator signoff. | `AEW-FR-16.a`, `AEW-FR-28.a` | A simple verified counter cannot close without another ceremonial approval. |
| `EW-U08.c` | AEW shall obtain the responsible authority's decision before allowing dependent work to rely on materially unresolved foundational intent or contract assumptions. | `AEW-FR-04.d`, `AEW-FR-16.c` | A whole test architecture is built on disputed concurrency requirements. |
| `EW-U08.d` | The Lead's completion report shall identify the delivered subject, applicable satisfied obligations, qualified verification, unresolved findings and consequential limitations. | `AEW-FR-14.d`, `AEW-FR-28.d` | The final report says “mission accomplished” with no indication that required integration evidence is absent. |
| `EW-U08.e` | AEW shall consolidate nonurgent decisions requiring the same responsible authority into actionable decision briefs. | `AEW-FR-28.a–b` | Five workers independently ask the operator to approve choices the Lead could have brought as one decision. |
| `EW-U08.f` | AEW shall retain attributable links from a technical completion claim to relevant requirements, implementation subject, review results and verification evidence. | `AEW-FR-14.a`, `AEW-FR-17.a`, `AEW-FR-18.b` | A completed Story has no way to trace what was tested or which original criteria it met. |
| `EW-U08.g` | Before AEW reports technical completion, it shall establish qualified evidence addressing the item's applicable behavior and verification obligations even where no separate final-verifier role is required. | `AEW-FR-12.a–b`, `AEW-FR-14.a`, `AEW-FR-16.a` | A counter Ticket is marked technically complete solely because code was written and a superficial self-check passed, without evidence relevant to its required behavior. |
| `EW-U08.h` | AEW shall derive a technical-completion determination from applicable obligations and evidence accepted by the **assurance-authorized acceptance function or actor**, not solely from the Lead’s completion assertion; required independence shall not be supplied by the assessed actor acting alone. | `AEW-FR-12.a–b`, `AEW-FR-14.a–d`, `AEW-FR-16.a` | A Lead marks Story complete despite an unfulfilled mandatory integration obligation and absent evidence. |
| `EW-U08.i` | AEW shall promptly surface authority-level blockers that prevent materially dependent work from proceeding. | `AEW-FR-28.c`, `AEW-FR-04.b` | A plan’s contradiction blocks a major dependency for days without informing the responsible authority. |
| `EW-U08.j` | AEW shall permit unaffected authorized work to continue when another dependency is held or awaiting authority resolution. | `AEW-FR-16.d`, `AEW-FR-28.a` | A disputed installer topology needlessly halts independent documentation and tests. |

### EW-U09 — Findings, failure, and safe continuation

| ID | Atomic guarantee | Candidate foundational derivation | Disconfirmation witness |
|---|---|---|---|
| `EW-U09.a` | AEW shall enable authorized participants to record and trace consequential findings to potentially affected current or historical work. | `AEW-FR-18.a–e` | A worker reports a regression in an earlier Story but no durable link or retrievable finding is created. |
| `EW-U09.b` | AEW shall route credible contradictions to load-bearing premises for timely qualification and protective disposition by the appropriate coordination or enforcement authority. | `AEW-FR-04.a–d`, `AEW-FR-24.d`, `AEW-FR-31.a` | A qualified contradiction affecting an irreversible installer action remains only in a worker note without protective consideration. |
| `EW-U09.c` | AEW shall preserve valid work, qualified evidence, and governing obligations when a plan, assignment or implementation is rejected or revised. | `AEW-FR-07.b`, `AEW-FR-11.b–c`, `AEW-FR-14.b` | One failed child review causes valid sibling evidence to be silently erased, or old proof is silently carried to a changed revision. |
| `EW-U09.d` | AEW shall support continuing authorized work after Lead or session replacement only where the relevant authorization and dependencies remain valid. | `AEW-FR-23.a–e` | A fresh Lead must redo a valid plan or resumes an invalidated authority generation. |
| `EW-U09.e` | Mandatory refusal or revocation of unauthorized protected effects shall not be delayed solely to preserve an agent’s transient reasoning context. | `AEW-FR-25.d`, `AEW-FR-31.d–f` | AEW lets a revoked worker perform protected mutations to preserve its ongoing conversation. |
| `EW-U09.f` | AEW shall re-evaluate the applicable authorization and mandatory assurance controls when qualified new evidence changes the properties on which an active assignment was admitted, before allowing affected dependent effects to continue. | `AEW-FR-04.d`, `AEW-FR-06.b–c`, `AEW-FR-39.f–g` | A verified topology discovery raises the mandatory control floor, but the existing assignment retains a superseded lightweight authorization. |
| `EW-U09.g` | Where AEW mediates a relevant effect channel, it shall refuse further affected effects that rely on a qualified invalidated premise until an authorized resolution permits them, even when the worker cannot receive a notification. | `AEW-FR-04.d`, `AEW-FR-31.b–c`, `AEW-FR-31.e–h` | The worker is unreachable, so its controlled mutation continues under invalid authority merely because it did not acknowledge an alert. |
| `EW-U09.h` | AEW shall notify reachable affected workers of qualified premise invalidations and of applicable changes in execution permission or required assurance. | `AEW-FR-08.b–c`, `AEW-FR-09.a`, `AEW-FR-04.d` | A worker resumes after a hold is lifted but receives no corrected deployment premise and repeats the mistake. |
| `EW-U09.i` | AEW shall establish the impact scope of a premise invalidation using recorded dependencies and qualified newly discovered relationships, without permitting an unreviewed narrower scope than known affected work. | `AEW-FR-04.d`, `AEW-FR-07.e`, `AEW-FR-24.d` | The Lead excludes a known dependent Story from the protective scope because its Ticket did not declare the assumption. |
| `EW-U09.j` | A protective hold based on a disputed discovery shall have an attributable basis and a designated decision path for qualification, correction, or rejection under applicable safety and authority rules. | `AEW-FR-04.a–d`, `AEW-FR-39.a–g`, `AEW-FR-31.a` | Untrusted text resembling a defect report indefinitely blocks workers without anyone authorized to adjudicate the claim. |
| `EW-U09.k` | Release of a premise-dependent hold shall require a qualified resolution and a current authorized continuation decision; the reason shall remain linked to the original finding. | `AEW-FR-04.d`, `AEW-FR-14.b`, `AEW-FR-31.b`, `AEW-FR-39.e–g` | The same worker dismisses a verified cross-boundary contradiction, erases the finding and resumes under stale authority. |
| `EW-U09.l` | Where an authenticated participant submits credible evidence meeting an adopted imminent-hazard rule for a protected or irreversible effect, AEW shall apply the required narrowly scoped **provisional** protection to mediated affected effects while the report is qualified; authored source text alone shall not trigger that authority. | `AEW-FR-04.d`, `AEW-FR-31.a–c`, `AEW-FR-39.g` | An authenticated, corroborated warning of imminent destructive deployment receives no interim protection solely because final qualification has not finished, or a README claiming authority triggers the same protection. |
| `EW-U09.m` | A provisional premise-protection decision shall have an attributable adjudication deadline and escalation path; reaching that deadline shall not silently remove mandatory protection or permit an indefinite unreviewed hold. | `AEW-FR-04.b–d`, `AEW-FR-28.c`, `AEW-FR-39.g` | A disputed finding blocks effects forever with no escalation, or a deadline expires and a required safety hold vanishes without resolution. |
| `EW-U09.n` | Material qualification or dismissal of a challenged load-bearing premise shall be attributable to an actor or function authorized for that decision and not solely to the author of the challenged premise. | `AEW-FR-12.f`, `AEW-FR-39.e–g`, `AEW-FR-31.a` | The planner whose local-install assumption is challenged clears the contradiction alone and immediately dispatches the same plan. |

## 4. Decision boundaries during the ordinary journey

This table is explanatory shorthand for the proposed atomic guarantees, **not** a replacement normative state machine.

| Boundary reached | Proceed without operator interaction when… | Must hold or escalate when… | Durable consequence |
|---|---|---|---|
| Initial objective | Source request and delegation establish permissible investigation or bounded routine execution | Material interpretation or authority remains unresolved | Preserve original input, accepted clarifications, owner and assumptions |
| Before consequential plan | Research provides an adequate basis; unresolved questions are visible | A load-bearing premise is contradicted or unknown without a permissible resolution path | Record decision basis and material research |
| Before consequential implementation | Required plan assessment and responsible-authority approval are effective for the current scope | Original requirements are omitted, plan assessment rejected, or approval refers to another revision | Link accepted plan, findings, authorization or non-authorization disposition |
| Before parallel dispatch | Dependencies, relied-on premises, isolation and integration duties are identified to the required degree | A mandatory control cannot be satisfied or conflict is unsafe | Record work premises, assignments and integration ownership |
| Before accepting worker output | Applicable implementation review and required local evidence are qualified | Defects or mandatory check failures remain unresolved | Preserve review findings and negative evidence |
| Before integrated completion | Current composed behavior and final required assurance have accepted qualified evidence | Only child-local PASS exists for a required consumer guarantee | Evidence-derived technical completion; qualify or reject claim |
| Before dependent continuation | Necessary decisions and foundational assumptions are valid | A governing requirement/premise remains contradicted | Hold affected dependent work, not unrelated work |

### 4.1 Who can decide what — proposed authority envelope

| Decision | Normal responsible role | Important restriction |
|---|---|---|
| Choose source-reading method, inexpensive investigation, builder assignment or serial versus parallel strategy | Lead within accepted delegation | Cannot reduce mandatory controls or exceed resource limits |
| Choose an implementation detail consistent with approved scope | Authorized implementer or Lead | Cannot change accepted objective or contract obligation |
| Judge code against assigned criteria | Assigned reviewer under assurance rules | Self-check is not independent review when independence is required |
| Verify composed behavior against original criteria | Qualified verifier under assurance rules | Green local tests and builder assurances are not substitutes |
| Adopt a consequential objective/plan/scope revision | Responsible project-boundary authority | Research and plan assessment are recommendations, not adoption |
| Establish or raise a minimum assurance/control class | Authorized classification function/actor under governing rules | Observable properties and qualified evidence impose the minimum; a Lead label cannot lower it |
| Reduce an applicable class or mandatory control | Separately authorized assessor/decision authority | The classifier cannot self-approve removal of mandatory safeguards; protectively handle undefined rules |
| Alter governing verification checks or accept resulting proof | Designated governing-check authority and independent assessor under assurance policy | The altering party does not unilaterally approve its own new PASS |
| Waive, defer, or quarantine a mandatory verification obligation | Responsible authority for that obligation | Retain failure/deferral evidence and qualified completion status; not every obligation is waivable |
| Determine technical completion | Work/evidence acceptance boundary according to governing rules | Derive from current accepted evidence and obligations; a Lead's “done” is not the deciding record |
| Qualify or dismiss an active premise invalidation and permit continuation | Designated adjudication and execution authorities | The challenged premise author cannot decide alone; preserve finding/resolution, current authority, and hold scope |
| Revoke protected execution authority or issue emergency stop | Authorized control authority under effective safety rules | Context preservation does not block revocation |

## 5. Scenario-driven architectural exercises

These exercises **reuse** stable foundational scenarios (`AS-XX`) but have local exercise identifiers `EW-Xxx`. Neither their execution nor their expected outcome is claimed as verified. New exercise IDs do not rename or supersede the foundational scenarios.

### EW-X01 — Ordinary counter, tooling available (primary normal-path case)

**Related:** `AS-26`, `AS-31`; `EW-U01.e`, `EW-U02.b–g`, `EW-U06.b–e`, `EW-U08.b`, `EW-U08.g–h`.

**Given:** A valid bounded request to add a routine counter to a module; relevant map, implementation pattern and tests are available and current; no mandatory extra review class applies.

**When:** The Lead retrieves the relevant scope and impact, elects to implement directly or delegates, performs the applicable checks, and reports completion.

**Then:** The change is traceable to its objective and tests; no required control is skipped; no redundant investigator or complex planning ceremony is imposed solely because that role exists. If the Lead implemented and checked the result, the check is labeled self-assessment. The operator may inspect the resulting change as a separate human review. **An independent review is required only when an applicable governing rule makes it required.**

**Fail if:** Lack of a separate investigator blocks admission despite sufficient qualified information; a required check disappears under the lightweight path; a self-check is mislabeled independent; the Lead reports operator acceptance not actually given.

### EW-X02 — Substantial integration-test suite (primary normal-path case)

**Related:** `AS-05`, `AS-26`, `AS-29`, `AS-30`; `EW-U01.e–f`, `EW-U03.a–e`, `EW-U04.a–h`, `EW-U05.a–e`, `EW-U06.b–f`, `EW-U07.a–h`, `EW-U08.a–d`, `EW-U08.g–h`.

**Given:** The operator requests tests spanning connection establishment, concurrency, failure paths, and cleanup; the initial request is incomplete; the existing project has code and historical architectural rationale.

**When:** AEW elicits requirements; the operator confirms their meaning; the Lead obtains focused research including relevant reasons behind design choices; a plan allocates requirements, implementation and integration verification responsibilities; a distinct required assessor challenges the plan against original requirements; the operator authorizes the consequential plan; work is safely scheduled, reviewed, integrated and finally verified.

**Then:** Each required behavior has an identified delivery and evidence responsibility; the accepted plan is available behind a short BLUF; local checks and composed consumer checks are distinguishable; the final verifier can inspect code and execution evidence; the completion report accurately states proven detection capabilities and limitations.

**Fail if:** Plan misses failure cleanup but passes assessment; operator approval is not obtained before dependent implementation; parallel contributors each pass unit tests but no one proves shared-fixture or lifecycle behavior; verifier asserts that tests detect races solely because they ran green.

### EW-X03 — VM B objective misunderstood

**Related:** `AS-01`, `AS-25`, `AS-33`, `AS-37`; `EW-U01.c–i`, `EW-U02.a–h`, `EW-U03.a–c`, `EW-U04.i`.

**Inject:** Existing installer reaches VM B through intermediary hosts. A porting plan silently assumes local execution and is confidently labeled trivial.

**Expected (intake):** AEW checks original behavior or explicitly qualifies unavailable required classification inputs, identifies the consequential topology assumption, applies governing minimum controls, and obtains required clarification before dependent implementation. A convincing plan narrative does not substitute for intent confirmation.

**Late-discovery follow-on:** Exercise `EW-X09` separately. This scenario tests first-contact fidelity and admission classification only.

### EW-X04 — Adversarial plan assessment finds missing obligation

**Related:** `AS-05`, `AS-29`, `AS-30`; `EW-U01.e–f`, `EW-U04.a–h`, `EW-U05.a–d`.

**Inject:** The operator confirmed failed-connection cleanup as a required acceptance behavior. The plan covers only happy-path connection and thread execution.

**Expected:** Plan assessment cites the original requirement, rejects readiness, and returns a specific missing-work or missing-proof finding. A revised plan must be reassessed for affected obligations before implementation authorization.

### EW-X05 — All children PASS, composed behavior fails

**Related:** `AS-05`, `AS-30`; `EW-U05.d–e`, `EW-U07.a–e`.

**Inject:** Independently developed helper and consumer pass their own tests, but their combined teardown leaks or serializes concurrent operations.

**Expected:** The integration responsibility is already assigned; actual composed evidence is required before parent completion; the parent claim remains unverified or failed until corrected. Neither aggregate PASS counts nor the integration plan itself prove integration.

### EW-X06 — Verification appears green because criteria changed

**Related:** `AS-04`, `AS-19`, `AS-29`; `EW-U06.b–f`, `EW-U07.a–h`, `EW-U08.g–h`.

**Inject:** Builder removes a failing assertion and supplies a successful test log; independent assessor is offered a narrative that the edit is harmless.

**Expected:** Check changes are attributable and assessed under the required authority and independence rules; older failure remains visible; unqualified PASS is refused until evidence is requalified. Review of the patch does not automatically satisfy behavioral verification.

### EW-X07 — Material discovery alters scope or dependencies

**Related:** `AS-03`, `AS-09`, `AS-13`, `AS-37`; `EW-U05.f–h`, `EW-U09.a–c`, `EW-U09.f–k`.

**Inject:** A worker finds that two apparently distinct assignments overlap, and a shared prerequisite contradicts an approved Story assumption.

**Expected:** New facts reach affected work and the Lead; obligations affected by changed work properties are reassessed; overlap can be coordinated within delegation while evidence survives; material scope/objective changes require the responsible authority; invalid dependent mutations wait while unrelated work continues.

### EW-X08 — Lead replacement and emergency revoke

**Related:** `AS-06`, `AS-17`, `AS-21`, `AS-36`; `EW-U09.d–e`, `EW-U09.g`, `EW-U09.h`.

**Inject:** The Lead disappears during implementation, and its old authority is subsequently revoked while the previous agent still retains conversational context.

**Expected:** Project objectives and evidence remain recoverable; only current authorized actors can perform protected effects; valid work can resume without gratuitous re-planning; revocation takes priority over preserving the stale agent's conversation. Any unmediated effect channel is disclosed and may not support unsupported containment claims.

### EW-X09 — Late discovery, false positive and bounded resumption

**Related:** `AS-01`, `AS-03`, `AS-09`, `AS-37`; `EW-U05.h`, `EW-U08.i–j`, `EW-U09.b`, `EW-U09.f–n`.

**Inject A — false positive:** Two active agents rely on a local-install premise. An authenticated third agent reports evidence that a remote hop is mandatory; evidence later proves to concern a different deployment environment. One worker is temporarily unreachable.

**Inject B — credible immediate hazard:** An authenticated worker supplies corroborated evidence that an imminent irreversible installer effect targets the wrong host, while final premise qualification remains pending.

**Expected:** The false-positive finding is recorded, checked against revision/environment evidence, rejected with an attributable reason, and does not cause indefinite interruption. A credible imminent hazard receives narrowly scoped provisional protection only where an adopted rule authorizes it; final qualification, adjudication deadline, and release follow the governing control policy. The affected set uses declared *and* newly discovered relationships. An unreachable worker cannot bypass an enforceable mediated hold. Unrelated work continues.

**Fail if:** A weak claim halts the project indefinitely; a qualified imminent hazard is allowed through a protected channel simply because final adjudication is pending; a deadline silently lifts mandatory protection; or a wrong-environment finding remains an active blocker after authorized rejection.

### EW-X10 — Operator's original requirement is lost in a paraphrase

**Related:** `AS-01`, `AS-25`, `AS-33`; `EW-U01.a–i`, `EW-U03.a–c`, `EW-U04.b`, `EW-U04.g–i`.

**Inject A — ambiguous confirmation:** The operator asks for a port of existing installation behavior. The Lead summarizes it as “install locally on VM B,” omitting intermediate hops, and obtains a casual “sounds good.” The original script visibly uses intermediate remote hops.

**Inject B — intentional departure:** The Lead shows the original remote hops and explicitly proposes omitting them. The responsible authority authorizes the changed topology for a specified scope.

**Expected:** In A, the known original behavior is enumerated and its omitted-hop divergence is disclosed before consequential confirmation; the ambiguous “sounds good” does not establish authority for an undisclosed topology change. In B, explicit authorized departure is preserved and the assessor assesses the changed, current acceptance basis. Routine work requires neither a second ceremonial signoff nor an exhaustive artifact inventory.

**Fail if:** The Lead's shortened wording alone is treated as exclusive authority; the assessor cannot retrieve the source; a consequential interpretation silently becomes accepted because the operator approved an ambiguous summary.

### EW-X11 — Assessor changes tests; routine fixture correction

**Related:** `AS-04`, `AS-19`, `AS-29`; `EW-U02.e–f`, `EW-U06.c–e`, `EW-U07.d–j`, `EW-U08.g–h`.

**Inject A — assessment laundering:** A verifier edits a required assertion after it fails and attempts to certify PASS. A builder independently makes an equivalent alteration in another case.

**Inject B — legitimate maintenance:** A low-risk Ticket updates non-governing test material; a separate legitimate fixture correction changes a relevant governing input.

**Expected:** Neither the verifier nor builder may unilaterally turn an altered governing check into accepted proof of the unchanged obligation. The governing-set classification is determined by independent authorized criteria, not the changer. Non-governing maintenance remains lightweight; material governing-input corrections remain possible but need the prescribed independent requalification.

**Fail if:** An altered assertion is accepted as equivalent solely on the altering assessor's claim; or harmless fixture maintenance is prohibited rather than subjected to its applicable assurance obligations.

### EW-X12 — Malicious finding steers peer execution

**Related:** `AS-03`, `AS-35`, `AS-37`; `EW-U01.a–b`, `EW-U03.d`, `EW-U05.h`, `EW-U09.a–b`, `EW-U09.i–n`.

**Inject A — hostile authored content:** A repository document masquerades as an operator order to stop all workers; a research agent quotes it in a note.

**Inject B — real report:** An authenticated worker submits evidence of a critical shared-interface defect affecting two active assignments.

**Inject C — false authority:** An unrelated authority approves a topology change, or a research recommendation is presented as implementation authorization.

**Expected:** Authored content stays data, not an instruction or authority grant. A qualified critical discovery reaches the proper authority, triggers protection only as permitted by its evidence and current rules, and preserves a traceable decision and resumption path. Unrelated approval and research advice never grant permission to mutate outside the relevant delegation.

**Fail if:** Injection text triggers a project-wide stop solely by claiming operator authority; or a properly evidenced critical contradiction is ignored because the system distrusts all worker findings.

## 6. Initial trace map: foundation to umbrella to scenarios

This table is a **design-time index**, not a claim of completed traceability or conformance. Each normative clause also has its own derivation reference in §3. Scenario links remain versioned at source.

| Umbrella boundary | Principal foundational anchors | Primary exercises / foundational scenarios |
|---|---|---|
| Objective admission and authority | `01.*`, `02.*`, `03.*`, `05.*`, `31.*` | `EW-X03`; `AS-01`, `AS-02`, `AS-25` |
| Proportional path / classification | `03.*`, `06.*`, `09.d`, `39.*` | `EW-X01`, `EW-X03`, `EW-X10`; `AS-01`, `AS-26`, `AS-31`, `AS-33`, `AS-34` |
| Elicitation and research fidelity | `03.*`, `04.*`, `19.*`, `24.d` | `EW-X02`, `EW-X03`, `EW-X09`, `EW-X10`; `AS-01`, `AS-37` |
| Plan assessment and authorization | `02.*`, `07.e`, `12.f`, `16.c` | `EW-X02`, `EW-X04`, `EW-X10`; `AS-25`, `AS-29`, `AS-30` |
| Delegation and integration ownership | `07.*`, `09.*`, `11.*`, `37.*` | `EW-X02`, `EW-X05`, `EW-X07`, `EW-X09`; `AS-05`, `AS-10`, `AS-30` |
| Implementation review and verification | `12.*`, `13.*`, `14.*` | `EW-X01`, `EW-X05`, `EW-X06`, `EW-X11`; `AS-04`, `AS-19`, `AS-29` |
| Completion and operator attention | `15.*`, `16.*`, `17.*`, `28.*` | `EW-X01`, `EW-X02`, `EW-X07`; `AS-15`, `AS-26`, `AS-27` |
| Discovery, recovery, protected effects | `04.*`, `08.*`, `18.*`, `23.*`, `25.*`, `31.*`, `32.*`, `39.*` | `EW-X03`, `EW-X07`, `EW-X08`, `EW-X09`, `EW-X12`; `AS-01`, `AS-06`, `AS-17`, `AS-21`, `AS-37` |

**Out-of-scope trace reminder:** Knowledge-store admission and poisoning, restricted-deployment read paths, detailed resource/advisor scheduling, project-scale isolation, and historical-record migrations remain covered by the candidate foundational baseline but are not fully specified by this normal-workflow umbrella. They need corresponding domain/boundary contracts, not omission from the architecture.

## 7. Required subordinate contract resolutions (deliberately undecided)

| Open contract question | Governing owner / proposed next contract | Must be resolved by |
|---|---|---|
| What observable properties set the minimum assurance/control class, and when is a lightweight path permitted? | Authority, classification and delegation contract; operator-adopted policy | Before controlled dispatch uses classification |
| Precisely which objective/plan revisions require explicit operator approval, and how is it bound to effective authority? | Authority and work-contract boundary | Before consequential plan dispatch |
| What counts as independent plan assessment, implementation review, and final verification for each required assurance class? | Assurance and evidence contract | Before an assessment is accepted for a gate |
| What evidence proves compliance for test suites whose *purpose is to detect failures*? | Test-assurance / affected boundary contract | Before claiming detection capability for such deliverables |
| What obligations and evidence may be carried forward after assignment consolidation or revision? | Work identity, evidence and composition contracts | Before reusing historical evidence for changed work |
| How are integration ownership, shared prerequisites and interface dependencies represented across work items? | Work and coordination boundary contract | Before dependent parallel implementation is admitted |
| What execution/effect channels are controlled, and what are the supported protective-interruption guarantees? | Hosting, containment and authority contracts | Before protected execution or intervention |
| Which stage/milestone makes each foundational or contract obligation due for which profile? | Operator/product authority with relevant domain owners | Before declaring profile/release conformance |
| Which original operator interactions establish accepted intent, and how are consequential interpretations and in-scope corrections ratified? | Authority and work-identity contracts | Before consequential implementation depends on the accepted objective |
| What observable properties require baseline-behavior disposition for a port, and what differences must be shown to the operator? | Authority and work-identity contracts | Before a port, migration or replacement depends on claimed equivalent behavior |
| What are the required classification inputs, protective defaults, assessor independence, and triggers for reclassification? | Authority/classification and assurance contracts | Before class-governed execution or control downgrade |
| Which work premises are tracked, how are unlisted dependencies discovered, and when is an invalidation sufficiently qualified for a protective hold? | Work identity, coordination and authority contracts | Before active multi-agent execution and automated holds |
| Which authenticated reports justify narrow provisional protection, against which effects, under what urgency test, and with what adjudication time bound? | Authority, coordination and containment contracts | Before enabling discretionary automatic provisional holds; effective emergency controls remain binding |
| How promptly must suspected contradictions be adjudicated, and who may release a hold under which evidence conditions? | Coordination and authority contracts | Before enabling automated protective holds for non-emergency findings |
| Which channels can refuse further effects when a worker is unreachable, and how are already-started effects reconciled? | Hosting, containment and authority contracts | Before making active-work intervention or revocation claims |
| Which authorized assurance source determines whether a test/check/input is governing, including before and after legitimate maintenance? | Assurance/evidence contract | Before using changed test results as evidence for an unchanged obligation |
| When may governing test inputs/fixtures change on the lightweight path, and what separate assessor must qualify the resulting PASS? | Assurance/evidence contract | Before accepting altered governing checks as proof |


These are not permissions to guess. Until defined, effective current controls continue, and the governing protective defaults or holds apply at affected boundaries. This first draft **does not adopt any new classifier threshold, model quota, token budget, review tier name, or mandatory agent topology**.

## 8. Pre-adoption architectural war games and evaluation questions

A reviewer assessing this contract **without seeing the current code** should be able to answer:

1. Can a routine well-understood counter change proceed economically without bypassing mandatory controls?
2. Can an operator-confirmed substantial objective be independently recovered and checked against a plan when the Lead's summary is wrong?
3. Can the architecture identify who produces integration proof for separately assigned components before dispatch?
4. Can it refuse a false completion claim based only on local PASS, builder assertion, or altered checks?
5. Can a worker's important discovery stop only the invalid dependent work, preserve existing valid evidence, and cause a decision at the correct authority level?
6. Can a substitute Lead resume valid work without inventing authority or rebuilding the entire historical conversation?
7. Are the required signals and refusal/hold outcomes defined sufficiently for a replacement implementation, or have we smuggled in undocumented ticket states and tools?

A tabletop PASS would indicate proposed-contract clarity under the specified scenario, **not implemented behavior**. Actual conformance requires qualified implementation evidence and executable checks where applicable. A tabletop finding should update the contract proposal, not rewrite a stable foundational scenario merely to manufacture agreement.

## 9. Principal-designer review notes and known limits

**Review integration (design only):** The v0.4 candidate incorporates two further independent reviews. `EW-X09` through `EW-X12` have been exercised as **principal-designer architectural tabletop analyses** in the separate Round 2 report, with conditional and unresolved subordinate-parameter findings; they are **not** executable conformance tests or independent review evidence. Definitive safety, authority, interruption, and integrity behavior remains conditional on the adopted subordinate boundary contracts.

**Round 1 tabletop (design only):** The routine counter remains supported without obligatory role proliferation. The VM B case exposed missing explicit proof/unknown handling for initial classification and inadequate active-work response to late discovery; proposed clauses `EW-U02.g` and `EW-U09.f–g` address those design gaps. The routine check also motivates `EW-U08.g`, making evidence for ordinary technical completion explicit without requiring a separate verifier. Execution enforcement, threshold policies, and actual evidence are not tested.

**Strengths of the proposal:** It gives small work a genuinely economical path; requires substantial planning to trace back to original requirements; explicitly assigns integration evidence before parallel dispatch; prevents local PASS or a green test suite from being laundered into proof of composed behavior; separates independent assurance from self-check; and retains Lead autonomy over routine execution.

**Adoption versus executable capability:** The operator may adopt this umbrella's behavioral guarantees without first settling every subordinate policy parameter. **Affected execution capabilities remain unavailable** until their required controls, delegated authority, classification rules, assurance basis, and mediation boundaries are effective. Undefined parameters are not permissive defaults. The exact prerequisite matrix remains part of §7 and subsequent authority/assurance contracts.

**Issues deliberately not decided:** (i) the exact point at which an initial quick scope confirmation is mandatory for otherwise routine work; (ii) observable classification and escalation thresholds; (iii) required independence profiles and who may fill assessor roles; (iv) whether every substantial plan requires a separate specialist planner or whether a Lead-authored plan plus independent assessment is acceptable; (v) supported deployment, model and concurrency profiles; (vi) the precise state-transition and authority-enforcement implementation. None may be silently treated as operator-adopted.

**Historical reconciliation needed:** The present Workflow Contract, Knowledge Contract, invariant index, effective amendments and protected hosting controls must be checked against these proposed umbrella guarantees. Such evidence may identify omitted guarantees and conforming implementations, but it does not automatically become normative simply because it existed before this draft. No existing effective operational protection is retired by proposing this document.

## 10. v0.4 review disposition and limits

- **Strengthened without mandatory ceremony:** Port/migration/replacement behavior comparison and material-difference disclosure protect the VM B objective; simple bounded changes do not require exhaustive behavior inventories or an extra ritual approval.
- **Assessment remains distinct from authorization:** A rejected plan may be submitted for responsible-authority disposition but cannot proceed as successfully assessed; plan assessors challenge omitted premises and the full source basis.
- **Qualified altered-check rules:** Any participant's changes to governing verification conditions require the applicable separate qualification; independently identified non-governing maintenance remains ordinary authorized work.
- **Qualified provisional protections:** Authenticated evidence meeting an adopted imminent-hazard rule may produce narrowly bounded interim protection of mediated effects; no untrusted text or unsupportable worker claim automatically acquires stop-work authority. Adjudication is attributable, bounded by policy, and independent when needed.
- **Unresolved contract dependencies:** Classification parameters, governing-check boundaries, hazard predicates, adjudication deadlines, and release/continuation mechanics are not invented here. Adoption, operational permission, and conformance evidence remain separate.
- **Designer-tabletop status:** Round 2 tests four adversarial exercises in two or three variants each. Conditional coverage is **not** implementation verification, and unresolved parameterized boundaries are recorded explicitly.

## 11. Verbatim-ready Decision Record — RECOMMENDED, NOT ADOPTED

1. **Candidate umbrella:** Review *AEW Engineering Workflow Umbrella Contract — Candidate v0.4* as the proposed system-wide normal engineering journey, derived from the operator's routine counter and substantial integration-test scenarios.
2. **Proportionality:** Support economically lightweight execution for bounded work, while preserving all applicable authority, safety, review, integration and verification obligations; require classification from observable properties and governing controls, not mere agent confidence.
3. **Requirements fidelity:** For consequential work, preserve operator-confirmed requirements as an independently assessable source for planning, plan assessment, final verification, and completion claims.
4. **Integration accountability:** Identify integration proof responsibility before dependent implementation dispatch; require actual composed evidence where obligations demand it, independent of constituent PASS results.
5. **Assurance integrity:** Distinguish self-check, implementation review, plan assessment, behavioral verification, and operator acceptance; do not convert agent claims or changed tests into unqualified evidence.
6. **War games:** Retain Round 1 design findings and the Round 2 `EW-X09`–`EW-X12` design exercise record. Resolve any open subordinate-policy dependencies before enabling affected execution, and keep stable `AS-XX` links with test/evidence traceability.
7. **Authority and preservation:** Do not treat this candidate as adopted or as a replacement for any current effective safety, authorization, revocation, containment or record-integrity control. Seek explicit operator adoption and resolve necessary subordinate contract decisions before claiming implementation conformance.
