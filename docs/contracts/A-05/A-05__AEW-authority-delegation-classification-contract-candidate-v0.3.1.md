<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-05
source: 10-adopted/RECONCILED-SOURCE-BASELINE/01-ADOPTED-SOURCE-BYTES/A-05__AEW-authority-delegation-classification-contract-candidate-v0.3.1.md
source-sha256: e9e46bdbb6cea70f9f57a0233e834bdcc3f35e39558e43405e4cc1124533611a
edits-sha256: none
-->

# AEW Authority, Delegation, and Classification Contract — Candidate v0.3.1

**Status:** Principal-designer proposal — **NOT OPERATOR-ADOPTED**  
**Date:** 2026-10-14  
**Document role:** Proposed domain/boundary contract for engineering decision authority, delegated execution permissions, role separation, and control classification  
**Normative derivation:** Operator-adopted *AEW Foundational Requirements v0.4* and *AEW Engineering Workflow Umbrella v0.4*, adopted by the explicit 2026-10-14 decision record. This document also reflects subsequent **operator elicitation**, which is not itself the adoption of this proposed contract.  
**Implementation/conformance:** Not assessed or tested. No production authorization follows from this proposal.  
**Revision note:** v0.3.1 is a focused amendment incorporating two independent v0.3 reviews. It corrects disproportionate independent-review wording; requires an evidenced hazard report before provisional protection; applies mutable launch/isolation controls to the Lead as well as workers; protects routine handover classification; excludes author-descendant premise adjudicators; and repairs evidence trace generation. Prior identifiers are retained, with three narrowly scoped atomic clauses added. The prior Round 2 tabletop is retained as historical evidence; a focused delta exercise supplements it.  
**Design evidence:** Operator examples: local counter versus protected-boundary counter; VM B porting; integration-test harness redesign; shared helper owned by another worker; preference-versus-command wording; incidental variable initialization; investigator finding a three-line patch; worker/subcontractor prohibition; contested reviewer findings and Finance-like adjudication; justified classification correction.

## 1. Purpose and ordinary operating experience

**What this boundary must guarantee.** An authorized project authority can delegate engineering to a Lead; the Lead can efficiently research, plan, direct and improve work **inside the grant**; workers and specialists execute only their own assigned permissions; required assurance cannot be bypassed by convenient classifications or managerial assertion. AEW enforces supported effect permissions and leaves an attributable record of changes and contested decisions. It must protect both sides of the tradeoff: no unauthorized scope expansion and no bureaucracy for safe, ordinary work.

**Routine path:** The operator requests a counter. The Lead obtains sufficient scope/impact information from qualified tools or inspection, executes or delegates, and performs required checks. No new investigator, elaborate planner or independent review is obligatory *unless a governing rule actually requires it*. The operator can review the diff; self-checks remain labeled as such.

**Consequential path:** The operator requests an integration-test suite. The Lead elicits intent, researches dependencies and competing approaches, obtains plan assessment and the required authorization, coordinates builders and reviewers, and supplies qualified evidence. If the harness approach fails, the Lead may investigate and present an actionable decision brief *before* spending heavily on an unapproved replacement plan. A legitimate in-scope approach improvement can proceed under the grant with meaningful operator notification. An explicitly mandated approach cannot be changed without authorization.

**Scope honesty:** AEW cannot claim to prevent an effect through a channel it cannot mediate. A grant-free native child is never authorized, but rejecting a parent-submitted diff is not proof the child never changed source. Every admitted submitter must be accountable; assess actual delivered changes and evidence against applicable obligations, with independent assessment only where governing assurance rules require it. Uncertain provenance does not itself imply an independently mandated review unless a governing rule defines that trigger; detected unauthorized contributions remain untrusted. Activation of **any source-mutating agent, including the Lead**, additionally requires effective containment of workspace effects and restrictions on unauthorized agent-creation channels. Mere disclosure or Git attribution does not establish containment or true contribution origin.  

**Non-goals:** This contract does not introduce a new lifecycle state machine, a universal numerical risk score, mandatory role-per-model mapping, an assessor model tier, a token syntax, an MCP protocol, a scheduler, a test framework, or a replacement for existing effective containment. It is not the assurance contract or the hosting/enforcement design.

## 2. Source authority and interpretation

The foundational v0.4 and Engineering Workflow Umbrella v0.4 documents are **operator-adopted**, despite the historical candidate headers on their unchanged source files. Their governing adoption record is `AEW-architecture-baseline-adoption-decision-2026-10-14.md`. This proposed contract may specialize their boundaries but may not reduce any adopted requirement or effective operational safeguard.

A grant remains effective only while its validity context and ending conditions hold; a wall-clock TTL is policy-dependent. **Trust revocation** invalidates dependent grants for new protected effects. **Routine continuity handover** is a different event: an authorized successor can reaffirm still-eligible worker grants in a bounded, recorded transfer before any subsequent protected effect, without forcing individual operator approvals. The authority that issued the Lead's grant, or a previously authorized trusted platform rule, determines whether a Lead authority-generation change is routine or a trust revocation; neither outgoing nor incoming Lead may self-classify that event. Context compaction or conversation continuation under the same effective Lead identity is not an authority-generation change. A custodian grant issued solely under a revoked authority does not survive that revocation; a genuinely independent current custodian grant may continue only its separately authorized bounded duties.

A sentence in a role prompt, a planner's summary, a repository README, the Lead's opinion, an experiential knowledge entry, or a tool's output is **information**, not a new grant. An actual authority decision must be attributable to the decision maker entitled to make it for the affected boundary. External requirements and operator-controlled requirements may coexist in a project; authority follows the governing boundary, not a universal project-wide superuser assumption.

### 2.1 Terms

| Term | Contract meaning |
|---|---|
| **Responsible authority** | Operator or external owner entitled to make a specified decision for an affected boundary |
| **Lead** | Authorized coordinator with bounded delegated research, planning, assignment and execution-direction powers |
| **Worker** | Actor with a separately bounded assignment; does not inherit a right to delegate merely because another actor assigned it |
| **Specialist** | Investigator, researcher, advisor, reviewer or verifier acting under the permissions of that responsibility |
| **Grant** | Attributable, currently effective permission to perform stated effects for an objective under specified scope and restrictions; a logical concept, not a proposed token format |
| **Protected effect** | Action subject to the adopted authority/containment rules, including covered mutations to AEW protected state, records, credentials and any other governed effect boundary |
| **Classification floor** | Minimum controls imposed by an authorized rule and qualified observable properties, not by a Lead's confidence or code size |
| **Discretionary finding** | Advice not establishing violation of an applicable mandatory criterion |
| **Mandatory assurance finding** | Alleged failure anchored to an identifiable *pre-existing applicable* requirement, acceptance condition or governing check; citation existence and applicability are independently assessable and disputed applicability is not resolved by reviewer or Lead fiat |
| **Diagnostic-effect boundary** | Separately authorized scratch/probe output that is not admitted project implementation or governing verification evidence by default |
| **Consequence-bearing premise** | Assumption about scope, behavior, topology or constraints that can change authorized effects or applicability of required controls |

### 2.2 Decision-rights boundaries

This table summarizes responsibility and **does not create grants independent of the atomic clauses and effective governing policies**.

| Decision or effect | Expected accountable authority | Cannot do solely by assertion |
|---|---|---|
| Adopt or change requirement, accepted objective, reserved architecture or acceptance obligation | Responsible governing authority for that boundary | Lead cannot adopt its own research or plan |
| Interpret and investigate a request; propose alternatives | Lead within investigative delegation | Treat an unconfirmed consequential departure as accepted |
| Choose in-scope implementation approach and worker allocation | Lead within scope, constraints and resources | Expand protected-effect rights or disregard a firm operator constraint |
| Reassign helper/prerequisite work | Lead/AEW authorized coordination function | Implicitly grant new write rights to the discovering worker |
| Request information or advice | Worker or other authorized actor | Create or subcontract another authorized agent |
| Execute assigned implementation | Implementer with effective effects grant | Repair unrelated problems on discovery alone |
| Investigate, review, advise or verify | Specialist under explicitly permitted diagnostics/assessment rights | Edit governed code merely to make finding disappear |
| Evaluate a contested mandatory assurance finding | Authorized qualified independent assessor under assurance policy | Waive the requirement or adopt a changed criterion |
| Reduce/remit a mandatory control classification | Separately authorized decision/assessment authority | Original classifier self-approves removal |
| Admit, refuse or revoke protected effects | Applicable mediated authority/enforcement boundary | Treat request text as proof of accepted effects; claim protection over unmediated channels |
| Admit agent-originated source changes or verification evidence | Authorized work/evidence acceptance function | Accept an unattributed nested-agent edit as an authorized deliverable |
| Select adjudicator for mandatory finding or control-reducing correction | Preauthorized independent selection rule or authority with grant-lineage exclusions | Allow disputant, requester, or original classifier to act as assessor for a control-removing correction |
| Continue derived execution after parent authority ends | Revocation authority or properly authorized successor for routine transfer | Treat compromised revocation as routine handover, or inherit invalid grants without reaffirmation |

## 3. Atomic boundary guarantees

Each `ADC-NN.x` is one proposed, separately assessable contract obligation. A section heading is informational; it is not an additional requirement. Each disconfirmation witness is a **counterexample**, not a completed test. The `AEW-FR` and `EW-U` identifiers point to adopted clauses; derived guarantees reflecting new operator decisions remain **proposed** until this document is explicitly adopted.

When obligations conflict, applicable authority and safety requirements prevail over discretionary context preservation, efficiency or model convenience. Undefined governing parameters do not relax controls: use the established more-protective applicable rule or hold the *affected effect*, while allowing independent authorized research/work. Existing effective controls continue until explicitly and safely superseded.

### ADC-01 — Governing authority and origin of decisions

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-01.a` | AEW shall bind each consequential engineering decision to the authority responsible for the affected project boundary. | `AEW-FR-01.a`, `EW-U01.a` | A deployment change is approved by the operator for a boundary whose requirements are owned by an external governance body. |
| `ADC-01.b` | AEW shall not permit a project agent to adopt or amend requirements owned by an external governing authority without that authority’s decision. | `AEW-FR-01.c`, `EW-U01.b` | A Lead edits an external compliance requirement and treats its revision as effective. |
| `ADC-01.c` | AEW shall retain the attributable originating instruction separately from agent-produced interpretations or recommendations. | `AEW-FR-02.c`, `AEW-FR-03.c`, `EW-U01.c`, `EW-U01.e` | The only surviving requirement text is a shortened Lead summary that omits the remote hops. |
| `ADC-01.d` | AEW shall distinguish an authorized decision from a proposed plan, research conclusion, assessment, or conversational suggestion when granting execution rights. | `AEW-FR-02.a`, `AEW-FR-02.c`, `EW-U01.b`, `EW-U01.f` | A researcher’s proposed harness redesign is treated as an operator-approved implementation change. |
| `ADC-01.e` | Where consequential behavior is inherited from an existing system, AEW shall expose a proposed change to that behavior to the responsible authority before treating the departure as accepted. | `AEW-FR-03.a`, `AEW-FR-03.b`, `EW-U01.h`, `EW-U01.i` | The operator approves “install on VM B” without being shown that the new approach omits the exemplar’s remote hops. |

### ADC-02 — Explicit delegation and authority boundaries

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-02.a` | AEW shall bind admission of delegated protected execution to an attributable, currently effective grant specifying actor, objective, permissible effects, scope and restrictions. | `AEW-FR-05.a`, `AEW-FR-31.b`, `AEW-FR-31.i`, `EW-U01.d`, `EW-U05.a` | An actor receives a protected execution allocation without any current attributable scope/effect grant. |
| `ADC-02.b` | AEW shall constrain every derived assignment to authority already held by its granting coordination authority. | `AEW-FR-31.i`, `AEW-FR-07.e`, `EW-U05.f` | A proposed helper grant authorizes an effect not permitted by the coordination authority’s own current grant. |
| `ADC-02.c` | AEW shall not treat a role name, model capability, prompt, parent conversation, or possession of a tool as an independent source of execution authority. | `AEW-FR-31.a`, `AEW-FR-31.i`, `EW-U01.b` | A reviewer uses an available write-capable tool to modify governed implementation without an implementation grant. |
| `ADC-02.d` | AEW shall reassess authorization before applying a consequential scope or revision change to an existing assignment. | `AEW-FR-07.b`, `AEW-FR-02.b`, `EW-U05.f`, `EW-U09.f` | A worker continues using an old authorization after its Ticket is changed to affect a protected helper. |
| `ADC-02.e` | AEW shall withhold an affected protected effect when a required authorization decision or defining parameter is unresolved and no effective protective rule permits that effect. | `AEW-FR-39.c`, `AEW-FR-39.g`, `EW-U02.g` | An undefined downgrade rule is interpreted as permission to execute without review. |
| `ADC-02.f` | On trust revocation of a parent grant, AEW shall deny descendant grants authority for new protected effects unless an independently current governing authorization explicitly permits a bounded continuation. | `AEW-FR-31.e`, `AEW-FR-31.i`, `EW-U09.e`, `EW-U09.k` | A compromised former Lead revokes while an old worker continues new protected source effects through the old derived grant. |
| `ADC-02.g` | Every execution grant shall identify the current actor, parent authority, applicable objective/scope revision, and the conditions that end its authority. | `AEW-FR-31.b`, `AEW-FR-31.e`, `EW-U01.d`, `EW-U09.e` | A grant outlives its objective revision because no condition ties it to that revision. |
| `ADC-02.h` | AEW shall enforce policy-defined grant expiry when such expiry applies to the authorization. | `AEW-FR-31.b`, `AEW-FR-31.e`, `EW-U09.e` | A grant with an adopted expiration continues authorizing effects afterward. |
| `ADC-02.i` | For routine Lead replacement without trust revocation, AEW shall support a recorded, scope-preserving reaffirmation of eligible derived grants by the properly authorized successor before subsequent protected effects. | `AEW-FR-18.b`, `AEW-FR-31.b`, `EW-U09.d`, `EW-U09.e` | Every worker needs a fresh operator approval solely because the Lead conversation changes, or effects continue under an unconfirmed successor. |
| `ADC-02.j` | A custodian authority derived solely from a revoked parent shall not survive that revocation; continuation requires a separately effective independent grant. | `AEW-FR-31.e`, `AEW-FR-31.i`, `EW-U09.e`, `EW-U09.k` | A compromised Lead creates a custodian immediately before revocation that continues unauthorized writes afterward. |
| `ADC-02.k` | AEW shall preserve the provenance and disposition of transferred, expired, and revoked grants without treating prior authorization as evidence for changed work. | `AEW-FR-14.b`, `AEW-FR-17.a`, `EW-U09.c` | Routine handover overwrites the original grant lineage and conceals which authority admitted prior effects. |
| `ADC-02.l` | AEW shall classify a Lead authority-generation transition as routine handover or trust revocation only under the issuing authority’s decision or a previously authorized trusted platform rule, not an outgoing or incoming Lead’s unilateral label. | `AEW-FR-31.d`, `AEW-FR-31.e`, `EW-U09.e` | A compromised Lead marks its own termination as routine, enabling descendants to be mechanically reaffirmed. |
| `ADC-02.m` | AEW shall preserve the current authorized Lead generation and eligible derived grants across context compaction or conversation continuation that does not change the effective Lead authority identity. | `AEW-FR-18.b`, `AEW-FR-31.b`, `EW-U09.d` | Ordinary prompt compaction produces a new grant generation and interrupts every active worker. |

### ADC-03 — Lead discretion, research, scope and approach changes

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-03.a` | AEW shall permit the Lead to undertake proportionate fact-finding into possible defects and alternative engineering approaches within its existing investigative authority. | `AEW-FR-02.a`, `AEW-FR-05.b`, `EW-U03.a` | A Lead cannot verify a suspected harness limitation without operator approval for the redesign it has not proposed. |
| `ADC-03.b` | AEW shall permit the Lead to reassign or decompose necessary in-scope work after required impact, ownership, dependency and assurance checks have been satisfied. | `AEW-FR-05.b`, `AEW-FR-11.a`, `EW-U05.b`, `EW-U05.f` | The Lead must request operator approval merely to assign a necessary shared-helper change to its existing owner. |
| `ADC-03.c` | AEW shall not confer ownership of newly discovered work automatically on the agent that discovered its necessity. | `AEW-FR-09.b`, `AEW-FR-11.a`, `EW-U05.a` | A discovering worker automatically gains write authority over a helper owned by another active worker. |
| `ADC-03.d` | AEW shall distinguish an explicitly imposed engineering constraint from a stated operator preference when deciding whether a proposed approach is within delegated discretion. | `AEW-FR-03.b`, `AEW-FR-05.a`, `EW-U01.f`, `EW-U03.a` | “Prefer the existing harness” is treated as a binding prohibition, or “must use” is treated as optional. |
| `ADC-03.e` | Where the strictness of an expressed operator preference remains consequentially ambiguous, AEW shall seek targeted clarification before executing a departure that cannot be justified within existing delegated discretion. | `AEW-FR-03.b`, `AEW-FR-39.c`, `EW-U03.a` | The Lead replaces a whole test harness on an unexamined interpretation of “prefer existing” that affects approved interfaces. |
| `ADC-03.f` | AEW shall permit an evidence-supported improvement within the approved objective and existing delegation when it does not change the binding approach or scope elements reserved by the approving authority. | `AEW-FR-05.b`, `AEW-FR-02.b`, `EW-U05.f`, `EW-U09.c` | An implementation variation explicitly permitted by the approved plan is rejected solely because it changes a nonbinding technique. |
| `ADC-03.g` | AEW shall notify the responsible operator of a consequential in-scope approach change without converting that notice into an unnecessary approval gate. | `AEW-FR-28.a`, `AEW-FR-28.d`, `EW-U08.d` | The operator sees that a feature unexpectedly returned to planning but receives no explanation of the pivot. |
| `ADC-03.h` | Before seeking authorization for a consequential change beyond delegation, AEW shall provide an evidence-qualified direction decision brief without requiring a full revised implementation plan merely to obtain that direction decision. | `AEW-FR-02.b`, `AEW-FR-28.d`, `EW-U03.c`, `EW-U08.e` | Hours of revised planning are performed before the operator is asked whether to permit a redesign. |
| `ADC-03.i` | AEW shall restrict unrequested incidental maintenance to localized changes established as nonbehavioral under the applicable maintenance allowance. | `AEW-FR-05.a`, `AEW-FR-05.c`, `EW-U06.a` | An unrelated variable initialization is silently included because the change is only one line. |
| `ADC-03.j` | AEW shall route unrelated potentially behavioral improvements for disposition without incorporating them into the active implementation absent separate authority. | `AEW-FR-05.c`, `EW-U09.a` | A reviewer-discovered cleanup silently becomes another commit in an unrelated Ticket. |
| `ADC-03.k` | In the absence of an operator-authorized incidental-maintenance allowance, AEW shall not admit unrelated maintenance changes into an engineering deliverable as incidental work. | `AEW-FR-05.c`, `AEW-FR-39.g`, `EW-U06.a` | A worker folds an unrelated whitespace-plus-variable-initialization cleanup into an implementation because no allowance was defined. |
| `ADC-03.l` | AEW shall requalify and obtain authorization for any approach revision that changes an element made binding by the accepted plan or scope revision before dependent effects use the revised plan. | `AEW-FR-02.b`, `AEW-FR-31.b`, `EW-U04.f` | The Lead materially replaces the specifically approved implementation topology and dispatches workers using the original plan grant. |
| `ADC-03.m` | AEW shall not treat approval of a proposed engineering direction as an implementation execution grant until the applicable plan, scope, assessment and dispatch prerequisites are satisfied. | `AEW-FR-02.a`, `AEW-FR-31.b`, `EW-U01.d`, `EW-U04.f` | An operator approves exploring a redesign option and the Lead immediately launches implementation without plan assessment. |
| `ADC-03.n` | Before a work-revision policy is adopted, AEW shall treat commitments explicitly designated decision-bearing and visible to the approver at approval time in the accepted decision summary as binding, without retroactive relabeling; descriptive details and stated preferences alone remain nonbinding. | `AEW-FR-02.b`, `AEW-FR-03.b`, `EW-U04.f` | The Lead retroactively marks a hidden plan commitment decision-bearing to justify a scope change, or discards a visibly approved fixture topology as nonbinding. |
| `ADC-03.o` | Where a proposed change alters an ambiguous decision-bearing commitment, AEW shall seek the responsible authority’s interpretation before executing affected new effects. | `AEW-FR-03.b`, `AEW-FR-39.c`, `EW-U04.f` | An uncertain constraint in the approved BLUF is silently treated as implementation discretion for a harness rewrite. |

### ADC-04 — Worker and specialist role boundaries

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-04.a` | AEW shall restrict each agent’s effects to its current assigned responsibility and effective authorization. | `AEW-FR-31.b`, `AEW-FR-31.i`, `EW-U05.a` | An investigator applies a patch in the project source tree despite holding only investigation authority. |
| `ADC-04.b` | AEW shall recognize no worker-originated subordinate execution assignment or transferred grant as authorized, regardless of the path by which the worker attempted to create it. | `AEW-FR-31.i`, `EW-U05.a` | A harness-native child receives effective delegated permissions merely because its parent requested it. |
| `ADC-04.c` | AEW shall permit a worker to request task-relevant research or advisory assistance without treating the request as a delegation grant. | `AEW-FR-26.a`, `AEW-FR-09.d`, `EW-U05.a` | The platform either prohibits any help request or allows the worker to self-authorize a new worker. |
| `ADC-04.d` | AEW shall authorize a helper independently through the established coordination authority before that helper performs controlled effects. | `AEW-FR-31.i`, `AEW-FR-10.a`, `EW-U05.a` | A helper begins editing or investigating restricted material solely on another worker’s invitation. |
| `ADC-04.e` | AEW shall not let investigators, advisors, implementation reviewers, or verifiers change governed implementation merely because they identified a defect or potential fix. | `AEW-FR-05.c`, `AEW-FR-12.f`, `EW-U06.d`, `EW-U07.c` | A verifier fixes the code it must independently certify without new implementation authority. |
| `ADC-04.f` | AEW shall permit properly authorized specialists to create diagnostic artifacts within an expressly bounded diagnostic-effect scope without converting those artifacts into admitted product changes. | `AEW-FR-12.b`, `AEW-FR-05.b`, `EW-U07.b` | A reviewer is denied authorized scratch diagnostics, or its scratch patch is admitted as governed product code. |
| `ADC-04.g` | AEW shall let specialist findings include a proposed patch while keeping that proposal advisory to the authorized implementer. | `AEW-FR-08.c`, `AEW-FR-12.a`, `EW-U06.d` | A suggested patch is automatically applied, or accepted as proven without implementation-specific verification. |
| `ADC-04.h` | AEW shall preserve and route consequential incidental findings to the responsible work authority even when they were discovered outside the specialist’s assigned question. | `AEW-FR-05.c`, `AEW-FR-18.a`, `EW-U09.a` | An investigator finds an unrelated defect and the finding is lost because it was outside its research prompt. |
| `ADC-04.i` | AEW shall accept agent-produced changes only through an accountable submitter holding an effective grant for the submitted work and shall assess the actual delivered bytes against applicable obligations. | `AEW-FR-14.b`, `AEW-FR-31.b`, `AEW-FR-31.i`, `EW-U05.a`, `EW-U07.e` | A granted parent submits a diff without accountable scope or evidence review and AEW declares it verified solely on the parent identity. |
| `ADC-04.j` | Where an unauthorized helper contribution is observable, AEW shall classify it as untrusted rather than authorized work, without claiming to detect concealed origin solely from a parent-submitted diff. | `AEW-FR-31.a`, `AEW-FR-31.i`, `EW-U05.a` | A known child-created patch is accepted as coordinator-authorized; conversely, an opaque patch is falsely certified as child-free based only on Git author. |
| `ADC-04.k` | AEW shall exclude isolated diagnostic artifacts from satisfying required governing verification checks unless those artifacts are admitted and independently qualified under the applicable assurance criteria. | `AEW-FR-13.a`, `AEW-FR-14.b`, `EW-U07.f` | A reviewer’s one-off probe is treated as a PASS for the required integration suite without satisfying that suite’s accepted checks. |
| `ADC-04.l` | AEW shall retain observable unauthorized or unattributed agent-originated changes and supporting evidence in an access-restricted, non-admitted investigation record. | `AEW-FR-14.b`, `AEW-FR-17.a`, `EW-U09.a` | A detected unauthorized patch is either silently merged or destroyed with no audit trail. |
| `ADC-04.m` | Before admitting any agent with source-mutation capability, including the Lead, AEW shall enforce an approved launch capability profile that denies native or indirect agent-creation paths outside the AEW-authorized coordination mechanism. | `AEW-FR-31.i`, `AEW-FR-31.j`, `EW-U05.a` | A mutable Lead or worker starts with usable native child-spawn permission and invokes a helper without the AEW coordination grant. |
| `ADC-04.n` | AEW shall refuse activation of any source-mutating agent, including the Lead, when effective assignment-workspace isolation cannot protect other assignments, governed authority records, and downstream build or evidence consumers across every path available to that agent, mediated or not. | `AEW-FR-31.j`, `AEW-FR-37.a`, `EW-U05.a`, `EW-U09.e` | A mutable Lead can edit a worker’s unrelated workspace or rewrite protected records through an unmediated shell, yet is activated as isolated. |
| `ADC-04.o` | AEW shall not release or consume a workspace or derived build result as trusted downstream input when a detected unauthorized write remains unreconciled. | `AEW-FR-14.b`, `AEW-FR-31.j`, `EW-U07.e` | The parent diff is quarantined, but another worker builds and executes its tainted output as trusted evidence. |

### ADC-05 — Risk/control-class determination

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-05.a` | AEW shall compute the minimum applicable control obligations from adopted rules and provenance-qualified observations rather than a Lead-authored risk label. | `AEW-FR-39.f`, `AEW-FR-06.b`, `EW-U02.a`, `EW-U02.c` | A Lead labels a protected-boundary change trivial and its assertion overrides the observable mandatory class floor. |
| `ADC-05.b` | AEW shall assess implementation, integration, verification and protected-effect consequences as distinct dimensions, allowing any applicable dimension to impose its mandatory control floor. | `AEW-FR-06.b`, `AEW-FR-12.d`, `AEW-FR-39.f`, `EW-U02.c` | A complex cross-component verification obligation is ignored solely because the code change is small. |
| `ADC-05.c` | AEW shall not treat an unobserved or unavailable required classification input as evidence that the corresponding risk is absent. | `AEW-FR-39.d`, `AEW-FR-39.g`, `EW-U02.g` | An unavailable original installer is treated as proof that no remote effects are involved. |
| `ADC-05.d` | AEW shall use the more protective applicable classification for a material unresolved control-class ambiguity until the responsible authority resolves it. | `AEW-FR-39.d`, `AEW-FR-39.g`, `EW-U02.g` | A classification conflict is resolved toward the lighter path because review would take longer. |
| `ADC-05.e` | AEW shall reassess affected minimum controls when qualified discoveries change the properties used to admit active work. | `AEW-FR-04.d`, `AEW-FR-39.f`, `EW-U09.f` | A newly proven shared protected dependency does not change an existing local-only assignment’s controls. |
| `ADC-05.f` | AEW shall preserve eligibility for the lightweight engineering path when no applicable higher controls are triggered and sufficient scoped understanding exists. | `AEW-FR-06.a`, `AEW-FR-05.b`, `EW-U02.b` | An ordinary counter requires a planner, a dedicated investigator, and an unrelated adversarial review solely because AEW supports those roles. |
| `ADC-05.g` | AEW shall retain the provenance, subject, applicability, and qualification basis of classification inputs and shall not lower a mandatory-control floor on the strength of an interested actor’s unsupported assertion. | `AEW-FR-39.b`, `AEW-FR-39.f`, `EW-U02.a`, `EW-U02.g` | The Lead claims a protected boundary is irrelevant and the floor drops without qualified supporting observation. |
| `ADC-05.h` | Qualification of classification inputs that can remove mandatory controls shall be attributable to an authorized assessor distinct from the interested party or governed by a separately adopted objective qualification rule. | `AEW-FR-39.e`, `AEW-FR-39.f`, `EW-U02.a`, `EW-U02.e` | The requester alone certifies that a production file is an isolated fixture, triggering lighter review. |

### ADC-06 — Classification correction, raising and reduction

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-06.a` | AEW shall permit an authorized Lead to raise a work item’s control or assurance class without a separate downgrade-style approval procedure. | `AEW-FR-39.a`, `AEW-FR-06.b`, `EW-U02.c` | The Lead detects new architectural risk but cannot apply stronger controls without an unnecessary second approval. |
| `ADC-06.b` | AEW shall allow routine classification-input corrections when recomputation under the same adopted rules leaves all applicable mandatory control obligations unchanged. | `AEW-FR-39.b`, `AEW-FR-05.b`, `EW-U02.b` | An irrelevant ticket description typo whose recomputed controls are identical requires an independent downgrade review. |
| `ADC-06.c` | When corrected classification inputs would remove or relax a mandatory control, AEW shall require assessment independent of both the reduction requester and the original classifier. | `AEW-FR-39.e`, `EW-U02.e` | A originally classifies a change; B requests removing mandatory review; A alone approves B’s downgrade. |
| `ADC-06.d` | AEW shall retain the existing mandatory protections while an attempted control-reducing correction remains unresolved. | `AEW-FR-39.d`, `AEW-FR-39.g`, `EW-U02.e` | A pending downgrade is used immediately to skip verification before its reassessment completes. |
| `ADC-06.e` | AEW shall preserve the original classification basis, new evidence, authorized resolution, and effect of a correction on prior work. | `AEW-FR-39.b`, `AEW-FR-14.b`, `EW-U09.c` | A downgrade erases the original higher class and silently carries previously invalid evidence. |
| `ADC-06.f` | AEW shall treat a proposed control reduction unsupported by corrected, qualified classification inputs as a requested waiver or exception rather than a routine factual correction. | `AEW-FR-39.e`, `AEW-FR-13.d`, `EW-U02.e` | A Lead calls a desired removal of required integration tests “metadata cleanup” without any corrected observable input. |
| `ADC-06.g` | AEW shall recompute the mandatory control floor before and after a proposed classification-input correction using the same governing rules, and preserve both computed results. | `AEW-FR-39.e`, `AEW-FR-39.f`, `EW-U02.e` | A classification correction is declared harmless without calculating that it removes an independent-review requirement. |
| `ADC-06.h` | Changes to governing classification rules that could alter mandatory controls shall require adoption by the responsible policy authority rather than classification-input correction authority. | `AEW-FR-01.b`, `AEW-FR-39.e`, `EW-U02.e` | A Lead changes the rule for protected topology to lower all Ticket floors and calls it a local metadata fix. |
| `ADC-06.i` | Adoption of a revised classification rule shall not silently relax the controls applicable to already-authorized active work without the required requalification and current authority decision. | `AEW-FR-39.e`, `AEW-FR-14.b`, `EW-U09.f` | A newly relaxed rule is applied retroactively to skip a pending independent review without an attributable decision. |
| `ADC-06.j` | An independent assessor for a control-reducing correction shall be selected through the authorized independent selection process with applicable grant-lineage exclusions. | `AEW-FR-39.e`, `AEW-FR-12.f`, `EW-U09.n` | The reduction requester selects a descendant agent to certify removing its own mandatory review. |

### ADC-07 — Review disagreement and independent adjudication

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-07.a` | AEW shall permit the Lead to decide discretionary implementation-review recommendations within its delegated engineering authority. | `AEW-FR-05.b`, `EW-U06.d` | A nonbinding style suggestion indefinitely blocks a compliant Ticket despite the Lead’s supported decision. |
| `ADC-07.b` | AEW shall retain an attributable rationale and make it available to the reviewer when the Lead rejects a discretionary review recommendation. | `AEW-FR-14.c`, `AEW-FR-09.a`, `EW-U06.d` | The Lead dismisses a reviewer’s nonbinding suggestion without giving the reviewer a reason. |
| `ADC-07.c` | AEW shall prevent a disputed finding alleging violation of an identifiable mandatory governing criterion from being converted into a PASS solely by a Lead’s disagreement. | `AEW-FR-12.f`, `AEW-FR-14.d`, `EW-U06.d`, `EW-U07.e` | A requirement-cited defect is marked PASS by the Lead despite unresolved contradictory evidence. |
| `ADC-07.d` | AEW shall permit the Lead to submit counterevidence and request reassessment of a disputed mandatory review finding. | `AEW-FR-14.c`, `AEW-FR-12.f`, `EW-U06.d` | A reviewer’s factual error cannot be contested with a demonstration that the suspected leak is actually released. |
| `ADC-07.e` | AEW shall provide an appropriately qualified, independent adjudication path for unresolved factual or mandatory-assurance disputes. | `AEW-FR-12.f`, `AEW-FR-39.e`, `EW-U07.e` | An unresolved defect finding is settled solely by the Lead’s opinion, or cannot be resolved by any authorized assessor. |
| `ADC-07.f` | AEW shall restrict technical adjudication to resolving the disputed claim under governing criteria, without granting the assessor authority to change requirements or waive protected obligations. | `AEW-FR-01.b`, `AEW-FR-13.d`, `EW-U07.e` | A mediator rewrites AF-123 instead of deciding whether the implementation meets it. |
| `ADC-07.g` | AEW shall evaluate both the existence and applicability of a cited pre-existing mandatory criterion for the reviewed subject; an unresolved disagreement about applicability shall use the authorized independent dispute path. | `AEW-FR-12.f`, `AEW-FR-14.b`, `EW-U06.d`, `EW-U07.e` | A reviewer cites a real requirement for a different component and blocks the Ticket indefinitely, or the Lead alone declares an applicable criterion irrelevant. |
| `ADC-07.h` | AEW shall select an adjudicator through a preauthorized impartial selection function or authority, excluding the disputing parties and any actor with a grant derived from a disputing party’s authority. | `AEW-FR-12.f`, `AEW-FR-39.e`, `EW-U07.e` | The disputed Lead appoints its own derived helper as the independent arbiter even if selection is automated. |
| `ADC-07.i` | AEW shall make the original finding, governing criterion and both parties’ attributable primary evidence available to a technical adjudicator without replacing them with a Lead-authored summary. | `AEW-FR-12.f`, `AEW-FR-14.b`, `EW-U07.e` | An adjudicator sees only the Lead’s paraphrase of the reviewer’s leak finding. |
| `ADC-07.j` | AEW shall deny technical adjudicators unilateral authority to alter governing verification checks or criteria as part of resolving the disputed finding. | `AEW-FR-13.a`, `AEW-FR-13.d`, `EW-U07.f` | The mediator deletes the disputed assertion and calls the unchanged obligation satisfied. |
| `ADC-07.k` | AEW shall record an evidenced potential requirements or acceptance-criteria gap for the appropriate authority without treating the gap alone as failure of a criterion that did not govern the current work. | `AEW-FR-03.c`, `AEW-FR-14.b`, `EW-U04.d`, `EW-U07.e` | An identified gap is silently lost, or reviewer invents a mandatory criterion to block technically complete work. |
| `ADC-07.l` | AEW shall disclose a known unresolved criteria gap in the applicable completion and acceptance presentation. | `AEW-FR-14.d`, `AEW-FR-28.d`, `EW-U08.d` | A reviewer discovers an important uncovered scenario, yet the technically complete result is presented with no qualification. |
| `ADC-07.m` | AEW shall apply any new or amended requirement to work prior to acceptance only following an attributable decision by its responsible authority, not a reviewer’s suggestion. | `AEW-FR-01.b`, `AEW-FR-02.b`, `EW-U01.d` | A reviewer’s proposed additional requirement is silently imposed as a new mandatory gate. |
| `ADC-07.n` | Authorized independent adjudication shall be scoped to the disputed criterion and evidence and shall not independently block unrelated work. | `AEW-FR-28.a`, `AEW-FR-16.d`, `EW-U09.g` | A disagreement about one cleanup path globally freezes unrelated Tickets. |

### ADC-08 — Protected effects, revocation and resource limits

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-08.a` | AEW shall require a current effective grant before accepting an AEW-mediated consequential effect from an agent. | `AEW-FR-31.b`, `AEW-FR-31.c`, `EW-U01.d` | A shell mutation is accepted solely because an agent still holds a previous conversation. |
| `ADC-08.b` | AEW shall refuse protected execution where the required minimum mediation and revocation coverage over AEW-protected authority state, records, or credentials is absent. | `AEW-FR-31.j`, `EW-U09.e` | AEW admits a worker whose unmediated shell can overwrite protected records after revocation. |
| `ADC-08.c` | AEW shall deny new mediated protected effects from revoked or suspended authority generations and from superseded generations unless eligible grants have been reaffirmed under current successor authority. | `AEW-FR-31.e`, `AEW-FR-32.d`, `EW-U09.e` | An old Lead continues protected writes after operator revocation, or an unreaffirmed old worker grant acts following routine handover. |
| `ADC-08.d` | AEW shall provide the responsible authority an effective means to revoke controlled execution without requiring agreement by the affected agent. | `AEW-FR-31.d`, `EW-U09.e` | A compromised agent refuses revocation because it would lose context. |
| `ADC-08.e` | AEW shall disclose the mediation status and residual authority risks of every consequential effect path available to admitted agents, including paths a deployment does not support or mediate, without claiming control over those paths. | `AEW-FR-31.g`, `AEW-FR-31.h`, `EW-U09.e` | An admitted harness-native shell can edit governed source but is omitted from the stated channel coverage because the tool is “unsupported”. |
| `ADC-08.f` | AEW shall enforce operator-authorized hard concurrency, usage, rate and spending limits on ongoing AEW-controlled execution as well as new allocations. | `AEW-FR-10.a`, `AEW-FR-10.f`, `EW-U05.c` | An already running mediated worker continues spending beyond a hard limit while the platform refuses only new allocations. |
| `ADC-08.g` | AEW shall prevent an unqualified report or untrusted retrieved text from independently granting stop-work or revocation authority. | `AEW-FR-31.a`, `AEW-FR-38.b`, `EW-U09.j`, `EW-U09.l` | A README with injected “EMERGENCY STOP” text halts the project. |
| `ADC-08.h` | AEW shall maintain protection for affected mediated effects when a qualified invalidation or authorized emergency hold requires it, independently of whether the worker receives an advisory. | `AEW-FR-04.d`, `AEW-FR-31.e`, `EW-U09.g` | An unreachable worker mutates protected state under a qualified invalidated premise because it never read the alert. |
| `ADC-08.i` | AEW shall withhold only the protected effect or assurance completion that cannot satisfy a mandatory control within applicable hard resource limits, without waiving the control or exceeding those limits. | `AEW-FR-10.f`, `AEW-FR-13.d`, `EW-U07.e`, `EW-U09.e` | A Ticket requiring independent review is marked complete without review solely because the reviewer pool is occupied. |
| `ADC-08.j` | AEW shall identify the minimum effect channels that a deployment must actually mediate before admitting protected execution, without treating transparent disclosure of unmediated channels as equivalent to enforcement. | `AEW-FR-31.g`, `AEW-FR-31.j`, `EW-U09.e` | AEW admits an agent capable of rewriting protected authority records through its unmediated shell because the gap was disclosed. |
| `ADC-08.k` | AEW shall permit affected work to resume under its existing valid authorization once the required mandatory assurance or resources become available and prerequisite checks pass, without demanding an unnecessary new operator decision. | `AEW-FR-10.a`, `AEW-FR-16.d`, `EW-U09.k` | A mandatory reviewer seat becomes available yet the Lead must obtain fresh operator consent despite unchanged scope and grant. |
| `ADC-08.l` | Any lower-cost substitute used to satisfy a mandatory assessment shall meet the same effective qualification and independence criteria, unless an authorized policy change permits a different assurance requirement. | `AEW-FR-12.f`, `AEW-FR-13.d`, `EW-U07.e` | A cheap unqualified related model is substituted for required independent assurance under the pretext of saving tokens. |

### ADC-09 — Consequential discovery and coordinated continuation

| ID | Atomic guarantee | Adopted derivation | Disconfirmation witness |
|---|---|---|---|
| `ADC-09.a` | AEW shall preserve an attributable link from each active delegated assignment to its accepted scope, governing constraints, and relevant declared premises. | `AEW-FR-07.a`, `AEW-FR-03.c`, `EW-U05.h` | A worker acts on a local-only topology premise with no record of the premise governing its assignment. |
| `ADC-09.b` | AEW shall route consequential discovered conflicts to the Lead or governing decision authority without automatically authorizing the reporting agent to change affected work. | `AEW-FR-04.a`, `AEW-FR-05.c`, `AEW-FR-18.d`, `EW-U09.a`, `EW-U09.b` | An investigator discovering a shared-helper defect both edits it and suppresses reporting because it thinks it fixed the problem. |
| `ADC-09.c` | AEW shall preserve original work and qualified evidence when an authorized Lead redistributes or consolidates assignments. | `AEW-FR-11.b`, `EW-U09.c` | Merging two Tickets deletes one worker’s valid reproducible investigation. |
| `ADC-09.d` | AEW shall prevent reassignment or task decomposition from silently modifying the governing objective or inherited mandatory obligations. | `AEW-FR-11.c`, `AEW-FR-07.e`, `EW-U05.g` | The Lead merges tasks and drops a parent-level cleanup requirement without approval. |
| `ADC-09.e` | AEW shall maintain protection of affected dependent work during an unresolved qualified authority or load-bearing-premise dispute without unnecessarily blocking unrelated authorized work. | `AEW-FR-04.d`, `AEW-FR-16.d`, `EW-U09.g`, `EW-U08.j` | A disproven claim freezes the entire project indefinitely, or a qualified invalidated premise does not protect any dependent work. |
| `ADC-09.f` | AEW shall require current authorization and qualified disposition of an invalidated premise before previously held dependent execution resumes. | `AEW-FR-04.d`, `AEW-FR-31.b`, `EW-U09.k` | The original assumption author removes the hold and resumes on stale authority without qualified resolution. |
| `ADC-09.g` | Until a governing credible-hazard qualification rule takes effect, an authenticated participant report identifying a named imminent mediated protected effect, alleging a concrete safety or authorization hazard with an initial factual basis, and concerning an effect classified as irreversible or conservatively protected pending irreversibility qualification shall trigger provisional refusal of that effect pending authorized triage; reversible and unrelated work shall not be held solely by that report. | `AEW-FR-04.d`, `AEW-FR-39.g`, `EW-U09.l` | A status announcement with no alleged hazard stops an authorized operation, or an evidenced imminent irreversible write proceeds during triage because the final qualification rule is absent. |
| `ADC-09.h` | AEW shall enforce an attributable adjudication deadline and escalation route for provisional protection without silently releasing mandatory protection or permitting an unreviewed hold to persist indefinitely. | `AEW-FR-04.d`, `AEW-FR-28.c`, `EW-U09.m` | A false alert locks a Ticket for weeks without escalation, or the clock expires and a true hazard hold vanishes. |
| `ADC-09.i` | A provisional protected-effect refusal shall be routed to an authorized decision owner with an attributable deadline or, if no deadline is defined, shall remain protected and be promptly escalated rather than silently releasing or waiting indefinitely without an owner. | `AEW-FR-04.d`, `AEW-FR-39.g`, `EW-U09.m` | An interim safety hold has no owner and lasts indefinitely, or a timer lapses and a dangerous effect starts automatically. |
| `ADC-09.j` | Independent adjudication of a contested consequence-bearing premise shall exclude its author and all actors whose grants descend from that author’s grant. | `AEW-FR-12.f`, `EW-U09.n` | A planner’s own native/AEW-granted subagent is appointed the independent decision maker that dismisses the planner’s contradicted premise. |
| `ADC-09.k` | AEW shall preserve the authenticated reporter identity, stated hazard, initial factual basis, and accountable disposition of a provisional hazard report for later qualification or misuse review. | `AEW-FR-14.b`, `AEW-FR-17.a`, `EW-U09.l` | Repeated baseless holds cannot be investigated because AEW loses who reported them or what facts were asserted. |

## 4. Decision interface and cross-contract handoffs

An authorization function or actor must be able to determine the responsible authority, current grant, permissible effect class, active work/revision scope, minimum mandatory controls and applicable refusal conditions. The **logical information** is contractual; the encoding, API, control-storage format and transport are subordinate designs.

**Protected uncertainty:** A stated preference is not automatically an absolute prohibition. When consequential uncertainty remains, AEW preserves binding constraints, forbids unsupported effects beyond delegation, seeks a targeted clarification, and continues independent authorized work. It does not turn every operator preference into an indefinite global hold. A material plan revision requires authorization where it changes approved binding elements (`EW-U04.f`); a direction-level yes is not an execution grant.

**Classification input boundary:** Before/after classifications are computed from the same adopted rule set and independently qualified input provenance. The classifier must use provenance-qualified observation and governing rules for at least affected protected boundaries, architectural/effect topology, integrated/composed behavior, verification obligations, irreversibility and operator constraints. These are *observable dimensions*, not a numeric class taxonomy invented here. Unknown required inputs remain unknown; a confident model assertion does not erase them. A classification may change as research establishes new facts. An expensive or demanding implementation does not itself make a control security-critical, and a three-line patch is not automatically safe.

**Assignment/coordination boundary:** The coordination authority has to know who currently owns work and which protected effects are permitted. When the discovering worker suggests a shared-helper fix, the Lead may give it to an existing worker or open separate authorized work, after preflight and required integration controls. A research/advice request is not a nested right to create assignments. The helper's authorization comes from the proper coordinator/enforcer, not its requester.

**Assurance boundary:** A mandatory finding must cite an existing criterion that actually applies to the affected subject; applicability itself may be disputed and independently adjudicated. New gaps are disclosed and routed for requirements disposition without automatically creating a failed pre-existing obligation. Assessors are assigned through preauthorized rules that exclude grant descendants of interested disputants; a deterministic eligible pool can serve without operator micromanagement. A Lead may resolve discretionary engineering choices but cannot replace required independent assessment. The adjudicator cannot change governing requirements, waiver policy or test checks.

**Diagnostic boundary:** Authorized scratch effects must stay within a declared diagnostic write boundary. A diagnostic may be useful evidence about a problem, but it is not itself execution of a required governing check without separate admission and assurance qualification.

**Effect-enforcement boundary:** The supported deployment must inventory all consequential channels available to an admitted agent, including unsupported/unmediated ones, and identify its minimum mandatory mediation set. To activate any source-mutating agent—including a Lead directly editing a lightweight Ticket—it must enforce the adopted launch capability profile and assignment-workspace isolation over every agent-accessible path, mediated or otherwise; otherwise that mutable capability is unavailable. An authorized Lead requests or issues helper assignments only through AEW-controlled coordination, not a harness-native spawn bypass. The minimum isolation is an enforceable outcome, not a requirement for a particular Linux user, container or worktree implementation. Acceptance-time provenance screening provides defense in depth but does not reverse unmediated writes. This contract specifies the grants and mandatory refusal outcome but deliberately does not specify how a shell, gateway, credentials broker, filesystem or harness enforces them. The subsequent hosting/execution-boundary contract must identify every actually mediated channel, minimum coverage, revocation behavior, already-started effects, and supported deployment limitations. **A role prompt alone is not containment**. If a required control is not enforceable, protected execution does not become permissible by truthful disclosure alone.

**Provisional protection boundary:** The umbrella already establishes an authenticated credible-hazard route (`EW-U09.l`), an adjudication deadline and escalation (`EW-U09.m`), and adjudicator independence (`EW-U09.n`). Pending adopted qualification parameters, the limited fallback in `ADC-09.g` protects a specifically identified imminent irreversible mediated effect **only where an authenticated participant alleges a concrete hazard or unauthorized effect with an initial factual basis**. A routine announcement that an authorized effect is about to execute is not a hazard report. Irreversibility is judged from the qualified effect classification or its conservative unknown-state treatment—not solely the reporter's label. This does not qualify the report as true, authorize a project-wide hold, or command effects from repository text. Deadline, resolution and escalation are required; a missing time value must not imply automatic expiry or a permission to wait without accountable triage. If the decision owner is unavailable, protection continues for the named effect while accountable escalation proceeds; authorized unrelated work continues. Record reporter identity and reported factual basis without treating an unsubstantiated report as a proven malicious report.

**Work/evidence boundary:** Grant changes, significant scope and classification decisions, contested findings, adjudications and effect outcomes must remain separately attributable. Work reassignment may preserve valid historical evidence but cannot manufacture current proof for a changed subject. Technical completion continues to be determined by the adopted Workflow/Assurance obligations, not the Lead’s assertion.

## 5. Parameter register — owners and adoption dependencies

These are **not decided values**. The given owner is the proposed accountable contract/authority boundary, not carte blanche to adopt new powers. Critical missing parameters prevent affected execution/assurance claims; they do **not** prohibit permitted research, status reads or unrelated work.

| Parameter needing a governing definition | Proposed responsible boundary | Required before |
|---|---|---|
| Classification categories, minimum observable triggers and protective fallback | Authority/classification policy adopted by responsible authority | Any classification-based admission or removal of controls |
| Objective/plan authorization extent and binding-versus-preference interpretation criteria | Authority and work-revision contracts | Consequential approach departures or revised execution |
| What constitutes material scope expansion and consequential notification | Authority and operator-attention contracts | Granting contested additional work or claiming timely notification |
| Issuer-authorized routine handover versus trust revocation, grant lineage, reassignment and policy-defined expiry | Authority and work-revision contracts | Any admission or continuity of delegated protected effects |
| Standing incidental-maintenance allowance and criteria for nonbehavioral change | Responsible operator/engineering policy | Automatic unrelated maintenance |
| Allowed helper/advisor roles, budget allocation and grant procedure | Coordination and resource contracts | Delegating assistance with protected effects |
| Diagnostic write boundaries and admission/evidence separation | Assurance and hosting/containment contracts | Diagnostic privileges or use of probes as governing evidence |
| Independent finding-adjudicator selection and primary record delivery | Assurance and coordination contracts | Disposition of unresolved mandatory findings |
| Reviewer independence, mandatory/discretionary finding classification and technical adjudication | Assurance/evidence contract | Accepting contested mandatory review or downgrades removing protection |
| Minimum mediated effect channels, effect acceptance, emergency revocation and stale-authority handling | Hosting/containment boundary, subject to adopted security minimum | Protected execution and claims of effective revocation |
| All mutable-agent launch permissions (including Lead), assignment-workspace isolation, build consumption quarantine and source effect coverage | Hosting/containment and work/evidence contracts | Activating any source-mutating agent or trusting shared outputs |
| Hold/provisional hold qualification, fallback effect scope, protected deadlines, affected-work mapping and resumption | Authority/containment and coordination contracts | Automated consequential stop, release and recovery |
| Record and evidence applicability across changed assignments/revisions | Work/evidence contracts | Carry-forward of previously accepted proof |
| Resource hard ceilings and ongoing limit enforcement | Resource/hosting contracts under operator-configured limits | Controlled multi-agent execution |

**Undefined-parameter rule:** Until adopted boundaries specify effective controls, no new protected effect obtains permission merely because a contract remains incomplete. Where immediate provisional protection must apply, use the bounded authenticated-effect fallback in `ADC-09.g–i`. Research/status and unaffected authorized work continue. Missing launch isolation, independent-assessment eligibility, or minimum mediation coverage cannot be solved by accurate disclosure alone.

**Preservation rule:** Current effective authority, classification, containment, revocation and evidence controls remain effective. Adoption of this candidate without these lower-level definitions must not be interpreted as permission to bypass them or to activate unsupported protected execution.

## 6. Architecture tabletop exercises

These exercises are proposed **design evaluations**, not executed implementation tests. An exercise must record: source authority and active grant; classification inputs and unknowns; findings/evidence; permitted/refused effects; required communication; accountable disposition; history preserved; and safe resumption. A scenario can cross many obligations; each atomic clause remains separately testable.

### ADC-X01 — Counter stays lightweight

**Source references:** `AS-26`, `AS-31`; `EW-X01`.  
**Relevant guarantees:** `ADC-02.a`, `ADC-03.b`, `ADC-04.a`, `ADC-05.f`, `ADC-07.a`.  
**Inject:** A counter change has current map and test evidence, ordinary boundaries and no special assurance requirement.  
**Expected:** AEW admits a bounded assignment, allows Lead implementation or delegation, does not compel separate investigators or independent assessment, and retains required behavior evidence.  
**Disconfirm if:** Automatic bureaucratic planning or skipped mandatory check.

### ADC-X02 — Three-line authorization counter

**Source references:** `AS-19`, `AS-31`; `EW-X01`.  
**Relevant guarantees:** `ADC-05.a`, `ADC-05.b`, `ADC-05.d`, `ADC-06.c`.  
**Inject:** A three-line counter affects an authorization decision; the Lead claims implementation is trivial.  
**Expected:** AEW derives the protected minimum and requires corresponding assurance; Lead opinion cannot lower it.  
**Disconfirm if:** The counter runs on an ordinary local-only control path because its patch is small.

### ADC-X03 — VM B remote-hop omission

**Source references:** `AS-01`, `AS-33`; `EW-X03`, `EW-X10`.  
**Relevant guarantees:** `ADC-01.c`, `ADC-01.e`, `ADC-03.d`, `ADC-05.c`, `ADC-05.d`.  
**Inject:** Existing installer performs remote hops; requested port summary omits them; operator replies “sounds good.”  
**Expected:** The old behavior and the proposed departure are visible; unexplained unknown topology does not trigger a lighter path; explicit approved removal is respected.  
**Disconfirm if:** An ambiguous paraphrase is treated as authorization to remove hops.

### ADC-X04 — Shared helper discovered mid-Ticket

**Source references:** `AS-03`, `AS-10`; `EW-X07`.  
**Relevant guarantees:** `ADC-03.b`, `ADC-03.c`, `ADC-02.d`, `ADC-09.c`, `ADC-09.d`, `ADC-09.a`.  
**Inject:** Worker A finds a prerequisite helper change while Worker C is already editing that helper.  
**Expected:** Lead/AEW coordination evaluates impact and assigns appropriate owner without implicitly authorizing A to edit it; relevant evidence carries forward.  
**Disconfirm if:** A automatically edits the same helper or valid work is discarded.

### ADC-X05 — Change of preferred harness

**Source references:** `AS-03`, `AS-27`; `EW-X02`.  
**Relevant guarantees:** `ADC-03.d`, `ADC-03.e`, `ADC-03.f`, `ADC-03.g`, `ADC-03.h`, `ADC-03.l`, `ADC-03.m`, `ADC-03.n`, `ADC-03.o`.  
**Inject:** Operator prefers existing harness but has not forbidden replacement; Lead discovers stronger alternative during implementation.  
**Expected:** Where consequential, preference strictness is clarified; in-scope better path can proceed with notification after appropriate checks; a prohibited or out-of-scope redesign gets a decision brief before replanning.  
**Disconfirm if:** Lead silently rewrites the whole harness or wastes hours planning unapproved scope.

### ADC-X06 — Investigator finds exact patch

**Source references:** `AS-03`, `AS-13`; `EW-X07`.  
**Relevant guarantees:** `ADC-04.a`, `ADC-04.e`, `ADC-04.g`, `ADC-04.h`, `ADC-09.b`.  
**Inject:** Research helper finds a three-line fix, and an unrelated defect, within seconds.  
**Expected:** Helper reports evidence and suggested patch but does not change governed implementation; issues reach responsible work authority.  
**Disconfirm if:** Investigator edits project source without authorization, or incidental defect disappears.

### ADC-X07 — Worker attempts subcontract

**Source references:** `AS-17`, `AS-31`; `EW-X08`.  
**Relevant guarantees:** `ADC-02.c`, `ADC-04.b`, `ADC-04.c`, `ADC-04.d`, `ADC-04.i`, `ADC-04.j`, `ADC-08.e`, `ADC-04.l`, `ADC-04.m`, `ADC-04.n`, `ADC-04.o`.  
**Inject:** Implementer attempts to spawn another coding agent from its harness and asks it to modify code.  
**Expected:** Assistance request is allowed but nested execution has no authorized grant. A compliant mutable launch denies the unauthorized native spawn capability and confines effects to the assignment workspace. In an unsuitable deployment, mutable activation is refused. If an unauthorized contribution is nonetheless detected, it is quarantined before trusted consumption; if concealed in a parent diff, accountable submission and byte-level assessment under applicable assurance rules do not prove true author origin.  
**Disconfirm if:** Child has permissions solely because parent spawned it.

### ADC-X08 — Disputed mandatory review

**Source references:** `AS-19`, `AS-29`; `EW-X04`, `EW-X11`.  
**Relevant guarantees:** `ADC-07.a`, `ADC-07.b`, `ADC-07.c`, `ADC-07.d`, `ADC-07.e`, `ADC-07.f`, `ADC-07.g`, `ADC-07.h`, `ADC-07.i`, `ADC-07.j`, `ADC-07.k`, `ADC-07.l`, `ADC-07.m`, `ADC-07.n`.  
**Inject:** Reviewer reports a socket leak; engineering Lead asserts it is false; reviewer disagrees after counterevidence.  
**Expected:** Lead can reject mere style preference with reasons, but mandatory claim stays disputed until qualified independent mediator resolves the technical fact without rewriting requirements.  
**Disconfirm if:** Lead stamps PASS itself or reviewer blocks indefinitely without a dispute path.

### ADC-X09 — Honest downgrade versus disguised waiver

**Source references:** `AS-29`, `AS-31`; `EW-X04`.  
**Relevant guarantees:** `ADC-06.b`, `ADC-06.c`, `ADC-06.d`, `ADC-06.e`, `ADC-06.f`, `ADC-06.g`, `ADC-06.j`, `ADC-05.g`, `ADC-05.h`.  
**Inject:** Protected classification is based on mistaken fixture identity; Lead presents evidence that the affected subject is isolated.  
**Expected:** Routine metadata fixes remain cheap, but removing mandatory control requires independent assessment; original evidence and disposition survive; waiver cannot masquerade as correction.  
**Disconfirm if:** Lead self-approves the reduction, or correction destroys valid earlier evidence.

### ADC-X10 — One-line unrelated initialization

**Source references:** `AS-03`, `AS-19`; `EW-X07`.  
**Relevant guarantees:** `ADC-03.i`, `ADC-03.j`, `ADC-04.h`, `ADC-03.k`.  
**Inject:** Implementer sees an uninitialized variable unrelated to its Ticket; initialization could affect existing tests.  
**Expected:** Report/recommend, do not silently add behavior-changing fix; if necessary to authorized objective, establish a revised in-scope assignment and checks.  
**Disconfirm if:** One-line patch is smuggled into Ticket as harmless hygiene.

### ADC-X11 — Stale Lead and protected effects

**Source references:** `AS-21`, `AS-36`; `EW-X08`.  
**Relevant guarantees:** `ADC-02.a`, `ADC-08.a`, `ADC-08.b`, `ADC-08.c`, `ADC-08.d`, `ADC-08.e`, `ADC-02.f`, `ADC-02.g`, `ADC-02.i`, `ADC-02.j`, `ADC-08.j`.  
**Inject:** Lead is revoked while worker shell or old Lead context still exists.  
**Expected:** Derived grants cease to authorize new protected effects on parent revocation. Previously authorized bounded custodian effects, if any, require separate current authority. Unmediated channels are disclosed and cannot be called contained.  
**Disconfirm if:** Revoked actor writes protected records while dashboard reports complete revocation.

### ADC-X12 — False premise and urgent real hazard

**Source references:** `AS-37`, `AS-09`; `EW-X09`, `EW-X12`.  
**Relevant guarantees:** `ADC-05.e`, `ADC-08.g`, `ADC-08.h`, `ADC-09.e`, `ADC-09.f`, `ADC-09.g`, `ADC-09.h`, `ADC-09.i`, `ADC-09.j`, `ADC-09.k`.  
**Inject:** A reported contradiction concerns another environment; separately a corroborated imminent hazard targets a protected effect.  
**Expected:** Untrusted text cannot create hold authority; qualifying and protecting affected effects follow governing hold rules, with bounded resolution and release under current authorization; unaffected work proceeds.  
**Disconfirm if:** False claim permanently holds all work or true imminent hazard is ignored because worker missed notice.

### ADC-X13 — Premium resource or assurance escalation

**Source references:** `AS-28`, `AS-31`; `EW-X02`.  
**Relevant guarantees:** `ADC-03.a`, `ADC-06.a`, `ADC-08.f`, `ADC-08.i`, `ADC-08.k`, `ADC-08.l`.  
**Inject:** Lead raises assurance on a cross-boundary Ticket; extra senior-model use would exceed configured spending.  
**Expected:** Raise protection without treating it as authority to exceed budget; request cost disposition or wait, while eligible work can proceed.  
**Disconfirm if:** Higher class automatically grants extra model spending without permission.

### ADC-X14 — External-owner conflict and recommendation laundering

**Source references:** `AS-01`, `AS-33`; `EW-X10`.  
**Relevant guarantees:** `ADC-01.a`, `ADC-01.b`, `ADC-01.c`, `ADC-01.d`.  
**Inject:** A research note claims external security owner approved an installer topology change; the real owner has issued no adoption.  
**Expected:** The actual boundary owner is identified; research remains advisory and the departure cannot borrow operator or Lead approval.  
**Disconfirm if:** The Lead approves requirements owned by a separate authority based on a research note.

### ADC-X15 — Over-broad derived helper grant and undefined rule

**Source references:** `AS-17`, `AS-25`; `EW-X07`.  
**Relevant guarantees:** `ADC-02.b`, `ADC-02.e`, `ADC-02.f`, `ADC-02.g`, `ADC-02.h`.  
**Inject:** A Lead granted ordinary source changes issues a helper grant to change protected credentials while mandatory grant scope parameters are undefined.  
**Expected:** Grant exceeds parent scope and is rejected; required unknown parameters prohibit the affected protected effect; ordinary unaffected work proceeds.  
**Disconfirm if:** The derived grant creates new privilege or an absent parameter means no check is needed.

### ADC-X16 — Mandatory-review label with no governing criterion

**Source references:** `AS-19`, `AS-29`; `EW-X04`.  
**Relevant guarantees:** `ADC-07.a`, `ADC-07.c`, `ADC-07.g`, `ADC-07.h`, `ADC-07.i`, `ADC-07.k`.  
**Inject:** Reviewer vetoes completion because of an invented mandatory styling convention without a criterion ID; another finding cites a real cleanup requirement.  
**Expected:** Unsupported mandatory label cannot veto indefinitely, but is recorded for criteria/applicability disposition; cited requirement remains a mandatory dispute resolved by a separately selected independent adjudicator using original records.  
**Disconfirm if:** Either the reviewer fabricates a permanent mandatory gate or the Lead dismisses the cited requirement itself.

### ADC-X17 — Provisional hazard deadline and independent work

**Source references:** `AS-09`, `AS-37`; `EW-X09`, `EW-X12`.  
**Relevant guarantees:** `ADC-08.g`, `ADC-09.e`, `ADC-09.f`, `ADC-09.g`, `ADC-09.h`, `ADC-09.k`.  
**Inject:** An authenticated worker shows credible evidence that a pending protected effect could irreversibly damage data; investigation is not yet complete, and another Ticket is independent.  
**Expected:** Narrow provisional protection applies to covered effect before final qualification; deadline and independent adjudication control resolution; unaffected work continues; no automatic release at timeout.  
**Disconfirm if:** The effect proceeds while qualification is pending, or unrelated project work is globally frozen with no review deadline.

### ADC-X18 — Falsely harmless plan pivot and preference

**Source references:** `AS-01`, `AS-33`; `EW-X03`, `EW-X10`.  
**Relevant guarantees:** `ADC-03.d`, `ADC-03.e`, `ADC-03.f`, `ADC-03.g`, `ADC-03.l`, `ADC-03.m`, `ADC-03.n`.  
**Inject:** Operator says “prefer the existing harness,” and approves a plan with a fixture-topology commitment visibly labeled decision-bearing at approval time; Lead later changes the topology and tries to relabel what was binding after approval.  
**Expected:** Binding labels are fixed at presentation/approval time, not authored retroactively; changed approved elements require appropriate reauthorization, but an evidence-supported compatible method variation can proceed with notice.  
**Disconfirm if:** A preference is silently elevated to a hard prohibition or exploited as blanket permission for a whole-harness rewrite.

### ADC-X19 — Diagnostic probe mistaken for governing verification

**Source references:** `AS-04`, `AS-19`; `EW-X06`, `EW-X11`.  
**Relevant guarantees:** `ADC-04.f`, `ADC-04.k`, `ADC-07.j`.  
**Inject:** Reviewer writes a scratch reproducer which passes, then tries to count it as the accepted integration test; subsequently edits the governing assertion during dispute.  
**Expected:** Diagnostics remain within authorized write boundaries and cannot substitute for the required checks; mediator cannot alter the governing check to make a PASS.  
**Disconfirm if:** The probe PASS masks a failing governing test, or a mediator rewrites its criterion.

### ADC-X20 — Protected grant ends while approved custodian drains

**Source references:** `AS-21`, `AS-36`; `EW-X08`.  
**Relevant guarantees:** `ADC-02.f`, `ADC-02.g`, `ADC-02.i`, `ADC-02.j`, `ADC-02.l`, `ADC-02.m`, `ADC-08.c`, `ADC-08.d`, `ADC-08.e`.  
**Inject:** Operator closes the Lead generation while an ordinary worker shell and a separately authorized verifier custodian are still active.  
**Expected:** On trust revocation, worker-derived and parent-derived custodian grants cease granting protected effects; separately independently authorized custodian may continue bounded work. On routine Lead replacement, successor may reaffirm eligible grants without a new operator approval; historical context remains accessible.  
**Disconfirm if:** Worker inherits old Lead authority, or valid custodian is mistakenly assumed to be authorized solely because it survived the revoke.

### ADC-X21 — Recomputed class floor prevents waiver laundering

**Source references:** `AS-25`, `AS-31`; `EW-X01`, `EW-X04`.  
**Relevant guarantees:** `ADC-05.a`, `ADC-05.b`, `ADC-05.g`, `ADC-06.b`, `ADC-06.c`, `ADC-06.f`, `ADC-06.g`, `ADC-06.h`, `ADC-06.j`.  
**Inject:** Lead edits a classification input from protected production boundary to isolated fixture and labels it routine metadata correction.  
**Expected:** Provenance qualification and old/new floor recomputation reveal removal of mandatory assurance; independent of both original classifier and downgrade requester assessment required before effect.  
**Disconfirm if:** A changed label alone drops the floor and skips review.

### ADC-X22 — Parent-laundered child work and workspace contamination

**Source references:** `AS-17`, `AS-25`; `EW-X08`.  
**Relevant guarantees:** `ADC-04.b`, `ADC-04.i`, `ADC-04.j`, `ADC-04.m`, `ADC-04.n`, `ADC-04.o`.  
**Inject:** Native child invisibly edits the parent worktree; parent submits a legitimate-looking diff; second worker attempts to consume the tainted build. In a separate variant, a mutable Lead invokes the native spawn path and can write outside its own assignment.  
**Expected:** No native child-spawn bypass for any mutable admitted agent, including the Lead; workspace effects isolated; a detected taint is not consumed. If concealment defeats provenance, admission verifies accountable submitter and bytes but never claims verified original author.  
**Disconfirm if:** Treating Git author as definitive authorship or permitting cross-workspace contamination.

### ADC-X23 — Classifier and requester are different actors

**Source references:** `AS-25`, `AS-31`; `EW-X01`.  
**Relevant guarantees:** `ADC-06.c`, `ADC-06.g`, `ADC-06.j`, `ADC-07.h`.  
**Inject:** Actor A originally classified protected work; B proposes removing mandatory review; A is nominated as the neutral assessor.  
**Expected:** Both A and B are excluded for control-reducing adjudication; eligible assessor chosen under preauthorized impartial rule and original floor retained pending decision.  
**Disconfirm if:** Original classifier approves downgrade requested by someone else.

### ADC-X24 — Reviewer cites real but inapplicable criterion

**Source references:** `AS-19`, `AS-29`; `EW-X04`.  
**Relevant guarantees:** `ADC-07.g`, `ADC-07.h`, `ADC-07.k`, `ADC-07.l`, `ADC-07.n`.  
**Inject:** Reviewer cites legitimate criterion for a different module; Lead disputes applicability; reviewer also reports an uncovered desired behavior.  
**Expected:** Independent qualified assessor decides applicability; cited obligation remains unresolved only where actually affected; uncovered new expectation is disclosed without inventing failed criteria.  
**Disconfirm if:** Either Lead or reviewer unilaterally determines applicability, or the gap becomes a new requirement by assertion.

### ADC-X25 — Routine Lead handover versus compromised revocation

**Source references:** `AS-21`, `AS-36`; `EW-X08`.  
**Relevant guarantees:** `ADC-02.f`, `ADC-02.i`, `ADC-02.j`, `ADC-02.k`, `ADC-02.l`, `ADC-02.m`, `ADC-08.c`.  
**Inject:** A legitimate issuer-classified provider rollover takes place, followed in separate variants by a compromised Lead falsely labeling its own replacement routine, and by ordinary same-identity context compaction while worker and custodian descendants remain live.  
**Expected:** The issuer or preauthorized trusted platform rule classifies the event; eligible grants can be reaffirmed in a scope-preserving authorized batch on routine handover; on trust revocation all derived authority ceases, including Lead-created custodian grants; same-identity compaction does not cause handover.  
**Disconfirm if:** Routine rollover needs individual operator approvals, or compromised Lead precreates surviving child authority.

### ADC-X26 — Imminent protected hazard before qualification rule

**Source references:** `AS-09`, `AS-37`; `EW-X09`, `EW-X12`.  
**Relevant guarantees:** `ADC-09.g`, `ADC-09.h`, `ADC-09.i`, `ADC-09.j`, `ADC-09.k`.  
**Inject:** No hazard threshold has been adopted; authenticated worker reports a pending irreversible protected write and evidence alleging it would damage protected state; separately an authenticated worker merely announces an authorized irreversible write without alleging a hazard; unrelated reversible work continues.  
**Expected:** The first, factually grounded hazard report provisionally refuses only the named mediated protected effect and reaches an authorized decision owner; the ordinary announcement does not impose a hold. Missing deadline or unavailable owner escalates without automatically releasing the held effect; reporter provenance is retained.  
**Disconfirm if:** Missing rule allows irreversible effect or authenticated claim halts entire project.

### ADC-X27 — Mandatory assurance capacity returns

**Source references:** `AS-28`, `AS-31`; `EW-X02`.  
**Relevant guarantees:** `ADC-08.i`, `ADC-08.k`, `ADC-08.l`.  
**Inject:** Mandatory qualified assessor temporarily unavailable under hard budget; later eligible slot returns within existing authorization.  
**Expected:** Affected completion waits while other work proceeds; when qualified capacity returns, no new operator approval is demanded.  
**Disconfirm if:** Review quietly skipped, budget exceeded, or newly available capacity still forces operator approval.

### ADC-X28 — Classification rules amended mid-flight

**Source references:** `AS-25`, `AS-31`; `EW-X01`.  
**Relevant guarantees:** `ADC-05.g`, `ADC-05.h`, `ADC-06.g`, `ADC-06.h`, `ADC-06.i`.  
**Inject:** Lead changes the underlying classification rule instead of the input, aiming to remove current mandatory integration assurance.  
**Expected:** Policy amendment reserved for its authority; recompute under effective policy with explicit non-retroactive control handling and audit history.  
**Disconfirm if:** Lead self-edits governing rule and ongoing Tickets instantly lose required protections.

## 7. Review challenges and scope of this draft

**Adversarial checks to run before recommending adoption:**

1. **Authority amplification:** Can an implementer, nested agent, reviewer or untrusted file convert a request or prompt into execution rights?
2. **Confident misclassification:** Can a Lead confidently assign a protected change the lightest class despite observable cross-boundary effects, or relabel a mandatory waiver as correction?
3. **Review capture:** Can a Lead bypass a mandatory rejection or bias a second assessor into accepting its own unsupported explanation? Can a reviewer veto a discretionary engineering choice indefinitely?
4. **False/true premise invalidation:** Can a false report halt the system without adjudication, or an unreachable worker continue a mediated harmful effect after qualified invalidation?
5. **Ordinary-path friction:** Can the Lead add a counter with existing scoped information and proportionate checks, without ceremonial agent spawning or operator micromanagement?
6. **Scope and plan pivot:** Can the Lead investigate a harness problem and preserve valuable research before asking for a consequential decision, while making an authorized in-scope improvement with a useful heads-up?

**Not settled by this draft:** Exact class names/thresholds, any universal numerical complexity score, how to technically constrain a shell or harness, approval latency, formal reviewer credential levels, implementation of issue tracking, number of agent seats, telemetry, and whether the current AEW code conforms. All remain explicit subordinate-contract/policy matters.

**Recommended targeted historical reconciliation:** Obtain the current effective authority/delegation/classification/hosting-control sources from the Development Lead and reverse-map each effective safeguard to these clauses and the two adopted baselines. Classify any mismatch as covered, partially covered, replaceable mechanism, contradicted, or authority decision needed. This is evidence reconciliation, **not** automatic promotion of historical implementation into new requirements.

## 8. Proposed decision record — not operator-adopted

1. **CANDIDATE:** Treat *AEW Authority, Delegation, and Classification Contract v0.3.1* as a proposed domain contract under adopted foundational and workflow v0.4, not as effective permission or evidence of current conformance.
2. **PROPOSED:** Delegated authority is explicit, bounded, non-transitive to workers, and validated at affected execution boundaries; the Lead retains in-scope research, assignment and engineering discretion.
3. **PROPOSED:** Separate classified control obligations from effort estimates; make upward control adjustment easy and reduction of mandatory controls independently accountable.
4. **PROPOSED:** Specialized investigators, reviewers, advisors and verifiers report findings but do not opportunistically implement; disputed mandatory findings receive independent targeted resolution, while discretionary engineering choices remain with the Lead.
5. **PRESERVE:** All existing effective protective controls pending safe, explicit supersession; no new effect channel or capability is authorized by this draft.
6. **NEXT:** Retain Round 2 and the focused v0.3.1 delta tabletop as qualified design evidence; seek the operator’s separate adoption decision on this candidate after consideration of the narrow reviewer amendments. Complete Hosting/Execution and Assurance subordinate contracts and qualified enforcement tests before any applicable conformance or protected-execution permission is claimed.
