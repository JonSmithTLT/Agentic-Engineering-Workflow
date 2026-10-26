<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-01
source: 10-adopted/RECONCILED-SOURCE-BASELINE/01-ADOPTED-SOURCE-BYTES/A-01__AEW-foundational-requirements-candidate-baseline-v0.4.md
source-sha256: cdb052e1bfb5e3b37efdf98e30a2d1fb32db332effb1a92f4f51eab91999ee6b
edits-sha256: 2cdf4600b2fcb013efb1308dd99d7a48e72e66dcc37a1a290c5ed7fdfdaf33af
-->

# AEW Foundational Requirements — Candidate Baseline v0.4

**Status:** Principal-designer amendment proposal; **NOT OPERATOR-ADOPTED**  
**Date:** 2026-10-13  
**Supersedes as a proposal:** Candidate v0.3 (39 topics, 159 atoms), which followed v0.2 and v0.1. This v0.4 is not automatically authoritative merely because it is newer.  
**Scope:** Human-directed, contract-first, multi-agent engineering workflow, independent of current implementation.  
**Structure:** 39 topic headings, **164 atomic candidate requirements**, individually addressable by `AEW-FR-NN.x`, with a disconfirmation question for each. Original 32 topic IDs retained as headings only. Added atoms preserve all existing v0.2 atomic identifiers; no clause was renumbered.

**v0.4 review navigation:** Narrow amendments to v0.3: add `04.d`, `31.i–j`, `39.f–g`; refine `12.f`, `13.a`, and assessor interpretation for `39.e`; make milestone/due-status semantics explicit; require traceability of stable acceptance scenarios; expand to **38 scenarios** and fix selected provisional reverse-trace classifications. Existing v0.3 atomic IDs and scenario IDs remain stable. No requirement is operator-adopted by this revision.

## 1. Purpose and boundaries

AEW must enable responsible project authorities to delegate research, requirements analysis, planning, implementation, review, verification, and coordination while retaining authority over engineering intent, governing constraints, and consequential changes. AEW must preserve credible evidence, durable project history, usable revisable experience, proportional resource usage, and inspectable operation across agent/provider interruptions. The desirable outcome is reliable and economical authorized engineering, not additional workflow ceremony.

### 1.1 Product intent and representative experience (informative)

**Users and purpose.** AEW serves project operators, engineering Leads, delegated workers, reviewers, and other authorized participants. It lets an authority delegate substantive software-engineering work—research, requirements clarification, planning, implementation, coordination, review, and verification—without surrendering control over the intended objective or receiving constant requests about routine implementation choices. Its purpose is to improve delivery of *correct, authorized, evidenced* engineering work while reducing avoidable resource cost, repeated discovery, context loss, and governance friction. It is not principally a workflow-ceremony generator.

**An ordinary successful workday.** An operator requests a bounded feature or correction. AEW recovers the relevant project objectives, governing requirements, implementation context, and known lessons. The Lead investigates consequential ambiguity before proposing a direction and obtains the responsible authority's confirmation when required; otherwise it proceeds within existing delegation. Workers share relevant findings, implement distinct authorized work, and perform applicable checks. Reviews form their own conclusions; evidence demonstrates what was tested. AEW updates linked work and evidence history, reports technical completion with qualifications, and continues other ready work. The operator checks progress without interrupting the Lead and receives a consolidated brief only for decisions that genuinely require their authority.

**When things are not routine.** A VM B port must not silently omit the original connection topology; a failing verification gate must not be weakened to invent a pass; a worker's discovery of a cross-Story regression must propagate without authorizing unrelated fixes; a stuck worker should receive proportionate assistance without reckless context loss; and records remain inspectable when the model gateway is down. These examples explain the desired outcomes; the atomic clauses below, not this narrative, are the proposed normative baseline.

**Boundaries.** AEW is not a substitute for project governance, an unrestricted autonomous programmer, or a claim of correctness based on agent confidence. Adopted authority, implementation behavior, and verified observations are different. This document does not prescribe a specific model provider, queue, database, release plan, interface, or existing code implementation.

### 1.2 Authority of this candidate

- **Operator elicitation:** The user described the intended experiences and boundaries, including VM B topology, Valgrind/test suppression, checkout-specific knowledge, concurrent discovery routing, advisor scarcity, retrospective regressions, cheap status and gateway outages. The candidate wording is still subject to operator approval.
- **Independent review:** The reviewer recommended atomicity, judgment accountability, priority rules, explicit evidence independence, deployment and security constraints, and reverse-trace checks. These are recommendations, not independently adopted requirements.
- **Historical archive:** The dated AEW repository evidence archive includes prior WC/KC, designs, invariant index, amendments and test documentation. Historical adoption claims are preserved as evidence and must be reconciled, not presumed current architectural truth.
- **Safety during reset:** Existing effective operational security, authority, containment, revocation and evidence controls remain in force until explicitly and safely superseded. This proposal does **not** itself authorize any replacement.

### 1.3 Atomicity and traceability rule

Every `AEW-FR-NN.x` below is **one separately assessable obligation**. A heading such as `AEW-FR-13` is an **organizational group, not an additional normative requirement or conformance unit**. Conformance is never aggregated to a group simply because one child passes.

The violation-witness column for each obligation answers the review question “what observation would falsify this requirement?” using a concrete example, not a complete test specification. Future umbrella/boundary contracts must define precise actors, applicability, conditions, evidence acceptance, and tests. Some requirements govern negative guarantees that require adversarial tests; some require multiple test cases. **One atomic requirement may trace to many contracts, work items, tests, and evidence artifacts, while one shared test or implementation may support several requirements. These relationships do not merge obligations.** Stable `AS-XX` scenario identifiers and their versioned descriptions are durable trace targets; scenario references are not substitutes for per-atom conformance evidence.

Track **three independent dimensions** for each atomic clause; none should be collapsed into a single status:

| Dimension | Example values | Meaning |
|---|---|---|
| **Normative authority** | Proposed; operator-adopted; retired/superseded | Whether an obligation governs and by whose decision |
| **Implementation realization** | Not assessed; absent; partial; implemented; contradicted | What the as-built implementation demonstrably provides, under which deployment/revision |
| **Verification qualification** | Not assessed; not tested; verified for stated conditions; partially verified; failed/contradicted; stale | What the available independent observations establish |

An adopted requirement can be partially implemented and contradicted by evidence simultaneously. Unknown remains unknown; an agent's implementation or completion claim is not verification.

### 1.4 Working definitions and interpretation

- **Responsible authority:** Operator or designated authority for the *specific* project or contract boundary; this need not be one universal person.
- **Lead:** Authorized engineering coordinator, independent of a particular model/provider; **worker**, **reviewer**, **advisor** identify responsibilities, not hard-coded topology.
- **Engineering evidence:** Attributable observations with sufficient subject, conditions and provenance to assess what was actually demonstrated. An agent's claim is a statement to evaluate, not independent proof.
- **Experiential knowledge:** A separate, revisable, noncanonical store of observed lessons and techniques; it never creates contractual authority.
- **Material / consequential / appropriate:** Terms whose applicability must be governed by the responsible boundary contract, declared risk policy, and attributable decision authority. They are **not** a self-service exemption an agent can assert without justification.

**Conflict interpretation for this candidate:** Existing enforceable authority and safety obligations take precedence over discretionary context preservation, optimization or convenience. Record integrity, truthful evidence, and historical attribution cannot be sacrificed for efficiency. When current requirements genuinely conflict, AEW must preserve the effective safety controls, identify the conflict, and seek the responsible authority's disposition; this paragraph is not permission to disregard another authority's governing obligation.

### 1.5 Applicability, release selection, and preserved operational controls

The catalogue describes the **intended AEW product**, not a claim that all capabilities are implemented or that every atom must be delivered in the first increment. Treat three questions separately for each requirement: **is it adopted?**; **under what capability, deployment, role, or work condition is it applicable?**; and **by which release or milestone must it be realized and verified?** A later release target does not weaken existing effective safety controls.

| Applicability family | Candidate treatment | Scope decision still needed |
|---|---|---|
| Authority, honest evidence, safety, revocation, and baseline record integrity | Universal whenever AEW is acting within the associated boundary; current effective controls continue operating | Identify current supported boundaries and applicable enforcement channels |
| Concurrency, worker coordination, specialist assistance, knowledge sharing, and cross-project access | Conditional upon the relevant feature, authorized role, sharing permission, or concurrent work being active | Define supported capabilities and initial release coverage |
| Disconnected/restricted deployment and repository-scale guarantees | Applicable to declared supported deployment or project-size profiles, not an unconditional ban on hosted services | Adopt profiles and constraints for each deployment |
| Additional evaluation, user-facing views, and efficiency outcomes | Enduring product outcomes, potentially staged | Assign release/milestone commitments and acceptance expectations |

These families are **candidate classification guidance**, not an adopted applicability assignment for all 164 atoms. A per-atom profile/release column shall be resolved by the responsible authority as adoption and contract recovery proceed; absent such a decision, do not silently label an obligation optional or implemented. **An approved requirement can be adopted but not yet due until a specified effective milestone or condition; that is different from a currently due requirement that remains unmet.** Applicability, effective milestone/condition, and due/not-yet-due disposition must be recorded separately from adoption and verification. **Release deferral is a delivery decision, not an amendment to the substance of a normative obligation.** Where an existing effective protection governs an active deployment, assigning a later milestone to a replacement requirement does not defer or weaken that protection.

### 1.6 Parameter and judgment-resolution register

Terms that depend on thresholds or context are not self-certifying exemptions. Contract recovery must supply the rule, deciding authority, and observability needed to evaluate them. The following are *pending definitions*, not values chosen by this candidate. The proposed accountable owner of each definition is the relevant **domain-contract owner**, with adoption or delegation by the responsible operator/authority. The owner cannot unilaterally grant itself additional scope.

| Parameter to define | Atoms affected (examples) | Proposed owner / completion point |
|---|---|---|
| Materiality, consequence, observable minimum control classes, conservative defaults and independent downgrade review | `03.b–c`, `05.c`, `15.b`, `39.a–g` | Authority/delegation contract; before classifications authorize dependent work |
| Operator decision urgency and delivery guarantees (e.g., “promptly”) | `08.b`, `18.d`, `22.c`, `28.b–c` | Coordination/attention contract; before advisory/escalation conformance |
| Mandatory reviewer independence and protected assessment basis | `12.c`, `12.f`, `13.a`, `39.e` | Assurance boundary contract; before review is accepted as independent |
| Resource ceilings, enforcement and accounting uncertainty | `10.a`, `10.e–f`, `26.b–c` | Resource/hosting contract; before controlled execution is admitted |
| Operationally reliable observable signals and progress thresholds | `09.d`, `24.a–e`, `25.a–d` | Progress supervision contract; before autonomous intervention is enabled |
| Status recency/freshness and the conditions for “current” | `29.c–e`, `30.b–c` | Operational-observability contract; before live-status claims |
| Core local functions and supported disconnected deployment capabilities | `30.a`, `34.a–b` | Deployment-profile contract; before profile conformance |
| Supported project/repository size, operational feasibility and isolation assurance | `37.a–c`, `31.g–j` | Containment/workspace contract; before concurrency is enabled for a supported profile |
| Evidence admissibility, independent classification of test changes, relevant input/subject changes and upgrade compatibility | `12.f`, `13.a`, `14.a–d`, `35.a–b` | Assurance/evidence/record boundary contracts; before accepting conformance claims |
| Minimum mandatory effect mediation across supported execution profiles | `31.b`, `31.d–j` | Authority/hosting containment contract; before protected agent execution is admitted; reducing the protected minimum requires responsible-authority disposition and safe replacement |
| Requirement due milestone/condition and effective release scope | all adopted atoms as applicable | Product/release authority; before a requirement is counted as presently due or deferred |

Where a required rule is not yet defined, current effective protective controls continue. AEW must not exploit the undefined term to choose a less controlled path. `39.g` governs the dependent action itself, including newly supported deployments without legacy controls; the parameter register alone does not substitute for this requirement. The parameter register is an explicit **contract-recovery worklist**, not a competing policy authority.

### 1.7 Criticality and verification planning

Every adopted atomic requirement needs an explicit verification approach, but not every requirement needs an adversarial test. Tag each atom during contract derivation as **safety/authority/integrity critical** (including effective revocation, isolation, evidence admissibility, and controlled limits) or **ordinary behavioral/operational**. Critical obligations should receive adversarial/negative tests where testable. Other obligations may be evaluated by focused positive and negative scenarios or qualified observations. The tag does not itself reduce any governing gate.

**Permissive obligations** (`03.d`, `05.b`, `08.d`, `10.b`, `16.a`, `16.d`, `26.a`, `27.a`) are falsified by an observable *unjustified prohibition* of the authorized capability, not by the absence of a hypothetical event. Tests must exercise a permitted, controlled example where the system refuses or burdens legitimate behavior.

## 2. Candidate foundational requirements — atomic clauses

### A. Intent, authority, and scope

#### AEW-FR-01 — Respect project-specific normative authority

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-01.a`** | AEW shall identify the governing requirement authority for each affected project boundary before accepting a consequential objective or requirement change. | A change is accepted using the wrong boundary authority. |
| **`AEW-FR-01.b`** | AEW shall enforce the applicable governing requirements for a boundary independently of agent-authored summaries or advice. | An agent summary overrides a governing requirement. |
| **`AEW-FR-01.c`** | AEW shall support boundaries governed by externally controlled requirements without granting project agents power to alter those requirements. | An agent modifies externally owned requirements without the owner's authorization. |
| **`AEW-FR-01.d`** | AEW shall support operator-governed requirement development without presuming that proposed requirements are adopted. | A proposed operator-governed requirement becomes effective without adoption. |

#### AEW-FR-02 — Separate delegated analysis from decision adoption

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-02.a`** | AEW shall permit authorized agents to perform research, requirements analysis, and planning without treating the resulting proposals as adopted decisions. | An unapproved plan changes effective project obligations. |
| **`AEW-FR-02.b`** | AEW shall require the responsible authority's decision before materially revising an accepted objective, scope, acceptance condition, or architectural commitment. | Dependent work proceeds under such a revision without the required decision. |
| **`AEW-FR-02.c`** | AEW shall retain an attributable distinction between proposed decisions and accepted decisions. | An observer cannot determine whether a consequential recommendation was adopted. |

#### AEW-FR-03 — Establish and validate engineering intent before dependent execution

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-03.a`** | AEW shall investigate relevant existing behavior when an objective requires migration, porting, replacement, or extension of an existing capability. | A plan omits a material existing behavior that could have been found in supplied sources. |
| **`AEW-FR-03.b`** | AEW shall seek confirmation when unresolved materially different interpretations would change an engineering outcome. | Implementation commits to one consequential interpretation with no confirmation. |
| **`AEW-FR-03.c`** | AEW shall record consequential unconfirmed assumptions and their implications before authorizing dependent work. | An unconfirmed topology-changing assumption is neither exposed nor recorded. |
| **`AEW-FR-03.d`** | AEW shall allow routine, low-consequence implementation assumptions to be resolved within delegated engineering authority. | Routine implementation choices always require operator signoff. |

#### AEW-FR-04 — Critically assess governing assumptions without self-authorizing change

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-04.a`** | AEW shall surface evidenced material contradictions, unsafe premises, infeasible obligations, or obsolete assumptions to the appropriate decision authority. | A known consequential contradiction is concealed while dependent work proceeds. |
| **`AEW-FR-04.b`** | AEW shall provide the affected authority with the evidence and engineering consequences of a challenged governing assumption. | An escalation states a problem without its relevant basis or impact. |
| **`AEW-FR-04.c`** | AEW shall not change the effective governing obligation solely because an agent judges it defective. | The effective obligation is silently replaced by the agent's preferred rule. |
| **`AEW-FR-04.d`** | AEW shall prevent affected dependent mutation from proceeding on an evidenced, contradicted load-bearing premise until the premise is reassessed or resolved by an authorized decision. | A worker continues irreversible dependent changes after evidence establishes that their governing foundation is invalid, with no reassessment. |

#### AEW-FR-05 — Preserve objective and scope fidelity with bounded autonomy

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-05.a`** | AEW shall execute engineering activities within the authorized objective and scope. | A worker carries out a material out-of-scope change without authorization. |
| **`AEW-FR-05.b`** | AEW shall allow routine engineering choices necessary to fulfill an authorized objective without per-choice operator approval. | An implementation is blocked pending approval for every ordinary code-level decision. |
| **`AEW-FR-05.c`** | AEW shall record and route consequential unrelated discoveries without treating their discovery as authorization to remediate them. | A worker starts unrelated remedial implementation only because it discovered a defect. |

### B. Execution, coordination, and integration

#### AEW-FR-06 — Scale process to risk and complexity

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-06.a`** | AEW shall support a low-overhead execution path for bounded work that does not require a complex engineering process. | A trivial authorized change obligatorily triggers an unrelated full-scale orchestration workflow. |
| **`AEW-FR-06.b`** | AEW shall apply the review and integration obligations required by a work item's governing risk and boundary classification. | A consequential item bypasses an applicable review or integration obligation. |
| **`AEW-FR-06.c`** | AEW shall retain mandatory safety, authority, and verification controls irrespective of a task's chosen lightweight process. | A lightweight classification eliminates a mandatory control. |

#### AEW-FR-07 — Maintain coherent authorized work and controlled integration

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-07.a`** | AEW shall maintain attributable identities and dependency relationships for current authorized work. | An active item's objective or dependent predecessor cannot be determined. |
| **`AEW-FR-07.b`** | AEW shall preserve the relationship between a work revision and its governing acceptance obligations. | A changed revision is treated as having unchanged proof requirements without a valid basis. |
| **`AEW-FR-07.c`** | AEW shall prevent unaccepted or unintegrated dependent changes from being treated as available accepted inputs. | A dependent task proceeds as if rejected or unintegrated output were accepted. |
| **`AEW-FR-07.d`** | AEW shall evaluate required compatibility and integration obligations before accepting changes into a shared system. | Integration is accepted despite unsatisfied applicable compatibility obligations. |
| **`AEW-FR-07.e`** | AEW shall preserve applicable parent-level accepted constraints and verification obligations when decomposing work into dependent work items. | A child task omits a governing security obligation that applied to its parent. |

#### AEW-FR-08 — Coordinate shared discoveries while protecting independent responsibility

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-08.a`** | AEW shall permit agents to contribute investigation findings for use by other authorized active agents. | An eligible finding cannot be made available across affected workers. |
| **`AEW-FR-08.b`** | AEW shall bring consequential discoveries to affected active work in time to reduce avoidable duplicated investigation. | Known applicable blocker information remains unavailable until workers independently rediscover it. |
| **`AEW-FR-08.c`** | AEW shall preserve each receiving work item's distinct objective and acceptance obligations after it consumes a shared discovery. | Receipt of a finding causes another item's verification requirements to be declared satisfied. |
| **`AEW-FR-08.d`** | AEW shall permit deliberately independent investigation when independent judgment is required by the objective or review obligation. | Required independent reviewers are forced to reuse an implementer's unverified correctness conclusion. |

#### AEW-FR-09 — Supply mechanism-assisted coordination rather than requiring Lead bookkeeping

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-09.a`** | AEW shall maintain accessible records of active assignments and dependencies without requiring the Lead to reconstruct them from agent conversations. | Routine status requires the Lead to reconstruct assignments from chat history. |
| **`AEW-FR-09.b`** | AEW shall expose mechanically observable contention or resource conflicts to the responsible coordinator. | A tracked conflicting workspace assignment proceeds without the coordinator being informed. |
| **`AEW-FR-09.c`** | AEW shall distinguish heuristic overlap or relevance signals from authorized work changes. | A probabilistic match alone cancels or re-scopes a task. |
| **`AEW-FR-09.d`** | AEW shall allocate routine, mechanically decidable coordination work to appropriately reliable low-overhead mechanisms. | Routine resource counting systematically requires high-capability model reasoning despite maintained structured state. |

#### AEW-FR-10 — Operate within configured limits and context-specific priorities

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-10.a`** | AEW shall refuse resource allocations that exceed operator-authorized concurrency, usage, rate, or expenditure limits. | Execution exceeds an established resource ceiling without valid authorization. |
| **`AEW-FR-10.b`** | AEW shall permit the Lead to allocate workers within authorized limits without separate approval for each ordinary assignment. | An authorized routine worker allocation requires an extra operator decision. |
| **`AEW-FR-10.c`** | AEW shall distinguish monetary expenditure, elapsed time, and scarcity of model execution capacity in allocation information. | A scarce senior seat is reported as free merely because monetary cost is negligible. |
| **`AEW-FR-10.d`** | AEW shall support project- or environment-specific operator priorities for time-versus-cost tradeoffs. | Home and workplace executions are forced to use the same nonconfigurable spending objective. |
| **`AEW-FR-10.e`** | AEW shall seek the responsible authority's decision for a consequential premium-cost strategy beyond the delegated discretion, stating cost and benefit uncertainty. | AEW adopts a materially more expensive unapproved plan without explaining its tradeoff. |
| **`AEW-FR-10.f`** | AEW shall enforce operator-authorized hard resource limits against continuing execution, not solely against new admissions, within its declared and supported control boundaries. | An AEW-mediated runaway operation continues accruing prohibited resource use after an enforceable hard limit is reached. |

#### AEW-FR-11 — Support safe work reorganization after consequential discoveries

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-11.a`** | AEW shall enable authorized coordinators to restructure execution assignments when new findings invalidate the original decomposition. | A coordinator cannot reassign overlapping work while retaining current scope. |
| **`AEW-FR-11.b`** | AEW shall preserve useful attributable artifacts and evidence when work is reassigned, consolidated, or paused. | A valid investigation disappears because two tasks were combined. |
| **`AEW-FR-11.c`** | AEW shall prevent execution reorganization from silently changing a governing objective or acceptance obligation. | Merging worker assignments changes a Story's accepted purpose without authorization. |

### C. Correctness, evidence, and completion

#### AEW-FR-12 — Verify actual behavior and contract conformance

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-12.a`** | AEW shall distinguish an agent's completion claim from evidence that work actually satisfies an obligation. | A builder's statement of success is itself accepted as proof. |
| **`AEW-FR-12.b`** | AEW shall evaluate the implemented behavior against applicable acceptance and contract obligations using qualified observations. | A completion claim has no pertinent behavior evidence despite a verification obligation. |
| **`AEW-FR-12.c`** | AEW shall distinguish independent review of the implementation from execution-based verification of behavior. | Reviewer approval is accepted as a substitute for a required behavior test. |
| **`AEW-FR-12.d`** | AEW shall obtain consumer or integration evidence where the affected boundary's requirements demand it. | Unit-only results are reported as validating an affected required consumer boundary. |
| **`AEW-FR-12.e`** | AEW shall avoid imposing unrelated broad integration investigations on low-impact work absent a governing verification obligation. | Routine local changes cannot complete without unrelated system-wide tests invented ad hoc. |
| **`AEW-FR-12.f`** | When independent assessment is required, AEW shall ensure the assessor evaluates the assessed party’s claims against authorized acceptance criteria that the assessed party cannot unilaterally change. | A reviewer approves because the builder asserted success, without independently evaluating the authorized criteria, or relies on criteria secretly substituted by that builder. |
| **`AEW-FR-12.g`** | AEW shall not treat successful verification of constituent work items as proof of required composed behavior without applicable composition evidence. | A parent integration claim is marked verified solely because separately tested children passed, despite a required cross-component guarantee. |

#### AEW-FR-13 — Protect verification integrity

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-13.a`** | AEW shall not accept a verification PASS for an unchanged obligation using altered governing checks, criteria, exclusions, thresholds, or relevant test inputs unless the alteration is attributable, independently assessed by an authorized actor other than the altering party, and the resulting evidence is requalified. | A builder deletes a failing assertion, declares the alteration immaterial, and receives an unchanged unqualified PASS without authorized assessment of the changed check. |
| **`AEW-FR-13.b`** | AEW shall retain negative verification results and their applicability rather than erase them on retry or correction. | A failure is deleted or hidden after a successful rerun. |
| **`AEW-FR-13.c`** | AEW shall label an authorized verification deferral or quarantine with its unverified obligation and resumption criteria. | A quarantined test appears as a clean, unqualified pass. |
| **`AEW-FR-13.d`** | AEW shall restrict waiver or alteration of mandatory verification obligations to a decision authority entitled to make that change. | A worker or unauthorized Lead waives a mandatory verification gate. |

#### AEW-FR-14 — Preserve attributable and currently admissible evidence

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-14.a`** | AEW shall bind verification evidence to the observed subject and materially relevant inputs and conditions. | A PASS cannot be associated with the state that was actually tested. |
| **`AEW-FR-14.b`** | AEW shall determine whether historical verification evidence remains admissible for a current claim under its governing applicability rules. | Evidence from a materially changed subject is silently reused as current proof. |
| **`AEW-FR-14.c`** | AEW shall preserve attributable contradictory evidence relevant to a governing obligation. | Contradictory findings are removed merely because they conflict with a preferred conclusion. |
| **`AEW-FR-14.d`** | AEW shall distinguish verified, unverified, unknown, stale, and contradicted claims in reported conformance. | A missing test is represented as verified. |

#### AEW-FR-15 — Make additional verification proportional and decision-ready

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-15.a`** | AEW shall distinguish mandatory verification obligations from discretionary investigation of residual risk. | An optional test is incorrectly presented as a required gate or vice versa. |
| **`AEW-FR-15.b`** | AEW shall evaluate consequential discretionary verification by its credible risk reduction and expected resource cost. | Substantial optional testing begins without a defensible engineering rationale. |
| **`AEW-FR-15.c`** | AEW shall present material optional verification choices with estimated effort, benefit, risk, and uncertainty for the appropriate decision. | The operator is asked to approve hours of testing without an impact or effort estimate. |
| **`AEW-FR-15.d`** | AEW shall not use a percentage of tested functionality alone as proof that the remaining unverified obligations are acceptable. | A safety-critical path is waived solely because 90% of cases passed. |

#### AEW-FR-16 — Distinguish technical completion from intent acceptance

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-16.a`** | AEW shall permit routine work to become technically complete when its applicable engineering and verification conditions are satisfied. | A routine fully verified Ticket remains technically blocked solely for unrequired operator signoff. |
| **`AEW-FR-16.b`** | AEW shall distinguish technical completion from operator acceptance of the intended outcome. | Technical PASS is reported as explicit operator confirmation. |
| **`AEW-FR-16.c`** | AEW shall prevent dependent execution from relying on unresolved foundational intent or architectural assumptions requiring responsible-authority confirmation. | Downstream work starts on a known disputed foundational assumption. |
| **`AEW-FR-16.d`** | AEW shall allow unrelated authorized work to proceed when an outstanding acceptance or discretionary verification decision does not affect it. | One optional investigation globally freezes independent work. |

### D. Durable project record and understanding

#### AEW-FR-17 — Preserve a revisitable engineering history

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-17.a`** | AEW shall retain attributable historical identities, decisions, revisions, outcomes, and evidence for work items after completion. | Completed work cannot be reconstructed from maintained records. |
| **`AEW-FR-17.b`** | AEW shall permit new findings to be linked to previously completed work. | A later regression cannot be related to the original affected Story. |
| **`AEW-FR-17.c`** | AEW shall distinguish a never-satisfied original obligation from a later regression and a subsequently changed requirement. | A later regression causes false rewriting of an originally valid completion as a historical failure. |
| **`AEW-FR-17.d`** | AEW shall preserve legitimate past completion evidence when later observations change current conformance. | A later defect erases the historical verified state. |

#### AEW-FR-18 — Propagate new findings through existing work authority

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-18.a`** | AEW shall allow authorized workers to record a consequential finding through the current work/evidence system. | A worker has no supported way to report a defect linked to its active work. |
| **`AEW-FR-18.b`** | AEW shall establish or propose evidence-qualified links between a new finding and affected work, obligations, and downstream dependencies. | A report is orphaned from identifiable affected work despite available linkage evidence. |
| **`AEW-FR-18.c`** | AEW shall preserve uncertain or disputed defect causality rather than silently asserting a definitive origin. | Story 30 is recorded as proven root cause based solely on a heuristic similarity. |
| **`AEW-FR-18.d`** | AEW shall convey consequential findings to the Lead for a disposition recommendation to the responsible authority. | A material cross-Story regression is recorded but never reaches coordination authority. |
| **`AEW-FR-18.e`** | AEW shall not authorize out-of-scope corrective implementation merely because a finding was recorded. | A newly logged unrelated defect auto-starts unapproved remediation. |

#### AEW-FR-19 — Provide authoritative project understanding without context overload

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-19.a`** | AEW shall provide concise project orientation exposing current objectives, authority sources, relevant boundaries, and work context. | A fresh agent must read the entire repository to discover the current governing objective. |
| **`AEW-FR-19.b`** | AEW shall support targeted retrieval of authoritative project records and supporting history. | An agent cannot locate the governing contract clause for its assigned interface without broad conversational reconstruction. |
| **`AEW-FR-19.c`** | AEW shall surface material unresolved dependency restrictions relevant to the current task without requiring full historical context loading. | A known blocker on a required dependency is omitted from task orientation. |
| **`AEW-FR-19.d`** | AEW shall preserve the nonauthoritative status and provenance of derived maps, indexes, and summaries. | A project map overrides a governing source when they disagree. |

### E. Experiential knowledge and collective learning

#### AEW-FR-20 — Preserve revisable, nonauthoritative engineering experience

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-20.a`** | AEW shall preserve useful agent-learned engineering experience independently of canonical requirement and verification records. | Replacing an agent loses useful recorded discoveries because they existed only in chat memory. |
| **`AEW-FR-20.b`** | AEW shall permit authorized agents to challenge, refine, or correct experiential entries as relevant evidence evolves. | An invalid technique remains uncorrectable despite reproducible counterevidence. |
| **`AEW-FR-20.c`** | AEW shall support evidence-qualified supersession within a lesson's applicable conditions without deleting valid history. | A corrected observation destroys an older observation still valid in another environment. |
| **`AEW-FR-20.d`** | AEW shall prohibit learned knowledge from becoming governing project authority merely by being stored or frequently retrieved. | A knowledge entry changes an adopted requirement without an authorized amendment. |

#### AEW-FR-21 — Make knowledge applicable across revisions and projects

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-21.a`** | AEW shall distinguish the origin of an experience from the conditions under which it is applicable. | A lesson learned in a security-research platform is either universally applied or never considered elsewhere solely because of its project of origin. |
| **`AEW-FR-21.b`** | AEW shall enable agents to evaluate experiences against relevant environment, configuration, tool, and behavior conditions. | A command is recommended for a checkout missing its prerequisite solely because it worked at another revision. |
| **`AEW-FR-21.c`** | AEW shall permit multiple apparently conflicting experiences to coexist when their supporting conditions differ. | A successful new test command deletes an older command still valid for another checkout. |
| **`AEW-FR-21.d`** | AEW shall enforce information-sharing permissions for cross-project retrieval. | A private project lesson is disclosed to an unauthorized project. |

#### AEW-FR-22 — Make valuable experience readily usable by every authorized role

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-22.a`** | AEW shall give each authorized engineering role a usable way to retrieve relevant experiential knowledge. | Reviewers cannot access relevant lessons while implementers can, despite equivalent knowledge authorization. |
| **`AEW-FR-22.b`** | AEW shall support concise, task-targeted retrieval instead of obligating agents to ingest the full knowledge corpus. | Answering a routine test-command question requires reading every project lesson. |
| **`AEW-FR-22.c`** | AEW shall promptly make newly submitted qualified discoveries discoverable to authorized agents. | A reproducible finding remains invisible until an operator manually approves routine knowledge sharing. |
| **`AEW-FR-22.d`** | AEW shall support relevant proactive consultation or delivery of experiential knowledge during active work without mandatory periodic agent polling. | A known relevant lesson can only reach an active worker through repeated timer-based polling. |
| **`AEW-FR-22.e`** | AEW shall expose material applicability, evidence provenance, and known limits alongside actionable retrieved advice. | An exact command is supplied without a known condition necessary for it to work. |

### F. Continuity, supervision, and expert assistance

#### AEW-FR-23 — Continue work across sessions, models, and harnesses

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-23.a`** | AEW shall retain the current work objective, authorization, artifacts, and qualified evidence independently of an individual agent's context. | A provider change makes the accepted Ticket objective unavailable. |
| **`AEW-FR-23.b`** | AEW shall enable a fresh authorized agent to recover relevant work state and learned context without exhaustive conversational replay. | Morning resume requires rebuilding the previous session from chat transcripts. |
| **`AEW-FR-23.c`** | AEW shall permit continuation of still-valid previously authorized work without mandatory re-planning or repeated accepted review. | Every agent replacement automatically resets a still-valid plan to initial planning. |
| **`AEW-FR-23.d`** | AEW shall expose stale or contradicted dependencies before permitting an agent to rely on them in resumed work. | A replacement acts on superseded authority without warning or refusal. |
| **`AEW-FR-23.e`** | AEW shall disclose relevant harness/model capability limitations when they affect promised continuity. | In-flight model state is claimed recoverable on a harness that cannot preserve it. |

#### AEW-FR-24 — Detect and qualify work that needs assistance

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-24.a`** | AEW shall identify suspected tool or process stalls using qualified available execution observations. | A persistently unresponsive tool has no observable stall signal despite available monitoring evidence. |
| **`AEW-FR-24.b`** | AEW shall support detection of credible repeated unproductive operations using available attempt outcomes and relevant work changes. | Three materially unchanged timeout attempts with no new diagnostic information go unrecognized despite available observations. |
| **`AEW-FR-24.c`** | AEW shall support recognition of engineering nonconvergence distinct from mechanical inactivity. | Repeated design reversals with preserved evidence cannot be flagged for advisor judgment. |
| **`AEW-FR-24.d`** | AEW shall bring material plan-invalidating worker findings to responsible coordination authority. | A discovered invalid Epic dependency remains local to a worker. |
| **`AEW-FR-24.e`** | AEW shall avoid classifying legitimate repeated operations as unproductive solely because their command syntax or apparent activity pattern is similar. | A valid, evidence-producing randomized regression run is repeatedly blocked solely because the invocation command is unchanged. |

#### AEW-FR-25 — Preserve work and context during intervention

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-25.a`** | AEW shall favor the least disruptive intervention that addresses a non-emergency work-progress problem under applicable controls. | AEW terminates a worker when a non-destructive advice response would suffice. |
| **`AEW-FR-25.b`** | AEW shall not destructively interrupt in-flight work solely on heuristic inactivity or nonconvergence. | An agent is killed only because its worktree has not changed for 30 minutes. |
| **`AEW-FR-25.c`** | AEW shall distinguish durably recoverable work state from transient context that the active harness cannot suspend. | AEW promises lossless resume after discarding inaccessible inference context. |
| **`AEW-FR-25.d`** | AEW shall require permitted authority and qualified recovery/loss handling for a discretionary intervention that may destroy active context. | An autonomous watchdog discards work without meeting the applicable intervention safeguards. |

#### AEW-FR-26 — Allocate expert advice without exhausting scarce engineering capacity

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-26.a`** | AEW shall enable authorized workers to obtain bounded second-opinion engineering assistance. | A blocked worker has no permitted route to consultation within its authorized resources. |
| **`AEW-FR-26.b`** | AEW shall protect scarce high-capability capacity reserved for higher-priority work against routine advisor requests. | Ordinary consultations indefinitely starve a required major-feature review. |
| **`AEW-FR-26.c`** | AEW shall allocate advisory assistance according to operator-defined capacity and priority constraints without making the Lead manually administer every routine request. | Each permitted mid-tier advisory call requires expensive Lead approval and manual scheduling. |
| **`AEW-FR-26.d`** | AEW shall prevent advisory consultation alone from transferring task ownership or changing its accepted objective. | An advisor automatically rewrites the Ticket scope by providing an opinion. |
| **`AEW-FR-26.e`** | AEW shall keep recurring advisor escalation within authorized resource budgets. | Repeated inconclusive consultations grow unbounded despite configured spending limits. |

#### AEW-FR-27 — Yield capacity while blocked and resume safely

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-27.a`** | AEW shall allow a blocked worker to continue useful independent tasks within its existing authority when available. | A worker is forced to idle despite approved independent work it can progress. |
| **`AEW-FR-27.b`** | AEW shall enable work that cannot productively advance to relinquish unnecessary execution capacity without manufactured busywork. | A worker must continuously call a model just to hold its place in an advisor queue. |
| **`AEW-FR-27.c`** | AEW shall make resolved blockers actionable for continuation or reassignment without requiring waiting workers to poll continually. | A response arrives but can be discovered only by periodic worker model calls. |
| **`AEW-FR-27.d`** | AEW shall preserve a qualified resumption basis for waiting work without claiming inaccessible model thoughts were stored. | Resumed worker lacks recorded investigation/evidence, yet the platform claims full preservation. |

### G. Operator attention and operational visibility

#### AEW-FR-28 — Protect operator attention and chain of command

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-28.a`** | AEW shall resolve decisions within current delegated authority without escalating routine implementation details to the operator. | The operator must approve whether a local variable uses one ordinary representation over another. |
| **`AEW-FR-28.b`** | AEW shall consolidate nonurgent decisions requiring the same responsible authority into prioritized actionable briefs. | Five independent workers interrupt the operator with five routine nonurgent authority decisions. |
| **`AEW-FR-28.c`** | AEW shall promptly escalate consequential blockers that require authority beyond the Lead's delegation. | A foundational unresolved design decision is silently deferred while dependent work proceeds. |
| **`AEW-FR-28.d`** | AEW shall present operator decisions with the needed choice, relevant evidence, recommendation, alternatives, and consequence of delay. | A decision brief merely asks 'what should we do?' without alternatives or context. |

#### AEW-FR-29 — Provide inexpensive, non-disruptive operational visibility

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-29.a`** | AEW shall offer an authorized human a routine operational status view without requiring live Lead participation. | Requesting 'where are we?' causes the Lead to stop engineering and write a report. |
| **`AEW-FR-29.b`** | AEW shall report maintained work assignment, current disposition, blockers, pending decisions, and resource allocation information. | A status view cannot identify which Tickets are waiting despite tracked states. |
| **`AEW-FR-29.c`** | AEW shall distinguish observed state and qualified engineering progress from inferred activity or prediction in status reporting. | High CPU usage alone appears as 'engineering progress verified'. |
| **`AEW-FR-29.d`** | AEW shall identify the recency and availability of status information. | An hours-old observation is presented as live state. |
| **`AEW-FR-29.e`** | AEW shall expose recorded engineering activity phase when the phase is already available from normal execution records without additional model analysis. | An already recorded 'testing' phase is omitted from every lightweight view despite an otherwise supported status capability. |

#### AEW-FR-30 — Keep durable engineering information accessible through outages

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-30.a`** | AEW shall provide authorized non-LLM-dependent read access to persisted project information during model-gateway or Lead unavailability. | A gateway failure makes all previously persisted Tickets, lessons, and findings unreadable. |
| **`AEW-FR-30.b`** | AEW shall provide a read path to persisted records that does not require the main live orchestration execution service where independently available storage permits. | A supervisor outage prevents inspection of otherwise readable persisted history solely because all reads are routed through the failed supervisor. |
| **`AEW-FR-30.c`** | AEW shall label status as last-known when it cannot establish current execution state. | A disconnected worker is represented as presently running based on yesterday's observation. |
| **`AEW-FR-30.d`** | AEW shall retain confidentiality, integrity, and mutation restrictions on read paths used during an outage. | A fallback viewer allows unauthorized protected-state edits. |

### H. Trust, safety, and recovery

#### AEW-FR-31 — Enforce authorized effects across trust boundaries

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-31.a`** | AEW shall prevent untrusted instructions or agent-authored text from granting protected-state authority. | A worker prompt claims to be the operator and obtains protected mutation rights. |
| **`AEW-FR-31.b`** | AEW shall bind consequential effects to the current authorized actor, applicable scope, and required enforcement boundary. | A stale generation can publish changes because it remembers an earlier approval. |
| **`AEW-FR-31.c`** | AEW shall distinguish a request to perform an effect from an authorized accepted effect. | A proposed protected action is reported as completed without accepted execution evidence. |
| **`AEW-FR-31.d`** | AEW shall provide the responsible operator with an effective means to revoke AEW-controlled execution authority. | An operator cannot revoke current AEW authority after identifying compromise. |
| **`AEW-FR-31.e`** | AEW shall prevent revoked, suspended, or superseded actors from performing new protected AEW-controlled effects. | A formally revoked actor can still perform protected state writes. |
| **`AEW-FR-31.f`** | AEW shall apply active safety and authority enforcement requirements even when preserving an agent's context would otherwise be preferable. | A compromised actor continues mutating protected state merely because stopping it risks context loss. |
| **`AEW-FR-31.g`** | AEW shall disclose which effect channels and authority boundaries are mediated by each supported deployment configuration. | A deployment advertises generalized containment but provides no intelligible statement of whether worker shell effects are mediated. |
| **`AEW-FR-31.h`** | AEW shall not claim effective containment or revocation for an execution or effect channel outside its demonstrated enforcement coverage. | An operator sees “revocation complete” while an unmediated worker shell still has write authority over the protected target. |
| **`AEW-FR-31.i`** | AEW shall deny delegated agents protected execution or delegation authority unless explicitly granted for their current scope; such authority shall not be obtained merely from parent-agent status, nesting, or inherited conversation context. | A newly spawned worker dispatches another privileged worker solely because the parent possessed delegation authority. |
| **`AEW-FR-31.j`** | AEW shall require effective authorization and revocation enforcement on the paths by which its supported agent execution can affect AEW-protected authority state, engineering records, or credentials; protected execution shall not be admitted where this minimum cannot be enforced. | A deployment honestly discloses that its worker shell can rewrite AEW protected records after revocation, but still admits that worker to protected execution. |

#### AEW-FR-32 — Recover from partial failure without corrupting accepted state

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-32.a`** | AEW shall preserve integrity of accepted engineering state across interrupted operations or service failures. | An interrupted operation partially overwrites an accepted control record. |
| **`AEW-FR-32.b`** | AEW shall distinguish complete, incomplete, failed, and unknown effects when reconciling execution. | A timeout is silently reported as successful without evidence of effect. |
| **`AEW-FR-32.c`** | AEW shall prevent unsafe duplicate consequential effects caused by repeated or retried execution. | A retry repeats an already accepted irreversible effect without applicable safeguards. |
| **`AEW-FR-32.d`** | AEW shall prevent obsolete authority from overwriting accepted state during recovery. | A former Lead resumes and overwrites a newer adopted decision. |

### I. Additional baseline coverage candidates from independent review

#### AEW-FR-33 — Evaluate AEW against simpler engineering approaches

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-33.a`** | AEW shall support repeatable measurement of engineering outcome quality, resource use, and completion performance under declared evaluation conditions. | AEW cannot report comparable outcome and resource observations for representative tasks. |
| **`AEW-FR-33.b`** | AEW shall permit comparison with simpler authorized engineering approaches using equivalent task objectives and qualification criteria. | Claims of orchestration benefit cannot be tested against a single-agent or other simpler baseline. |

#### AEW-FR-34 — Support approved restricted deployment environments

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-34.a`** | AEW shall support authorized deployment profiles that do not depend on access to hosted external services for core local project-record and orchestration functions. | An approved disconnected environment cannot operate core local functions solely because a nonessential hosted SaaS is unreachable. |
| **`AEW-FR-34.b`** | AEW shall expose the operational capabilities unavailable in a configured disconnected deployment without falsely claiming those features are usable. | A disconnected deployment advertises remote-model execution as available when no permitted gateway exists. |

#### AEW-FR-35 — Preserve engineering records across AEW upgrades

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-35.a`** | AEW shall preserve the accessibility and meaning of accepted engineering records through supported AEW software upgrades. | A supported upgrade silently makes historical accepted evidence unreadable or changes its interpretation. |
| **`AEW-FR-35.b`** | AEW shall provide a qualified recovery or migration disposition when it cannot safely interpret a prior supported record format. | An unknown old format is silently reinterpreted as current canonical status. |

#### AEW-FR-36 — Prevent secret disclosure through engineering artifacts

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-36.a`** | AEW shall prevent unauthorized disclosure of protected credentials and secrets through generated evidence, logs, summaries, or experiential knowledge. | An agent writes an access token into a broadly readable knowledge entry. |
| **`AEW-FR-36.b`** | AEW shall support recording proof of operations involving secrets without requiring persistence of secret values in ordinary engineering records. | A test receipt can exist only by copying a credential into a report. |
| **`AEW-FR-36.c`** | AEW shall enforce the applicable access and retention policy on any sensitive information that is legitimately present in retained artifacts. | A restricted source artifact becomes public when linked from a work history entry. |

#### AEW-FR-37 — Protect concurrent engineering work at supported project scale

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-37.a`** | AEW shall prevent concurrent authorized workers from unintentionally corrupting one another's work or accepted shared state. | Two parallel tasks overwrite each other's accepted changes without detection or protection. |
| **`AEW-FR-37.b`** | AEW shall ensure the chosen concurrency approach remains operationally feasible within documented supported project sizes and environments. | Required isolation becomes unusable for an otherwise supported repository size. |
| **`AEW-FR-37.c`** | AEW shall not equate separate work directories with sufficient protection against cross-worker or external-state interference. | Concurrent workers are declared isolated despite sharing unprotected mutable resources that affect correctness. |

#### AEW-FR-38 — Protect consumers of agent-authored knowledge

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-38.a`** | AEW shall attribute experiential entries to their source and relevant supporting observations. | An agent-authored instruction is presented as provenance-free trusted platform guidance. |
| **`AEW-FR-38.b`** | AEW shall treat retrieved experiential content as untrusted data rather than executable authority over agents or tools. | A retrieved lesson injects new privileged instructions into an unrelated worker. |
| **`AEW-FR-38.c`** | AEW shall allow defective or malicious experiential entries to be qualified, quarantined, retracted, or superseded without destroying legitimate provenance. | A confirmed poisoned entry must continue to be recommended as valid guidance. |

#### AEW-FR-39 — Govern consequential judgment and uncertainty classifications

| Atomic ID | One requirement | Violation witness (what observation would falsify it?) |
|---|---|---|
| **`AEW-FR-39.a`** | AEW shall identify the delegated authority responsible for classifying the materiality or risk of consequential engineering decisions. | A high-consequence decision is classified by an actor with no assigned decision authority. |
| **`AEW-FR-39.b`** | AEW shall retain an attributable, inspectable basis when a consequential assumption or scope decision is classified as safe to proceed without further confirmation. | An irreversible topology change proceeds on an unexplained 'trivial' classification. |
| **`AEW-FR-39.c`** | AEW shall require confirmation by the responsible authority when uncertainty could change an irreversible, cross-boundary, or foundational outcome and no applicable rule establishes safe delegated discretion. | AEW silently resolves a disputed installation topology and executes a destructive migration. |
| **`AEW-FR-39.d`** | AEW shall apply the more protective applicable classification when materially uncertain categories impose different mandatory controls and no authorized decision resolves the uncertainty. | A disputed topology-changing task is admitted on the lighter path solely because the classifier prefers it. |
| **`AEW-FR-39.e`** | AEW shall require an authorized assessor other than the original classifier to evaluate a proposed reclassification that removes a mandatory control. | A Lead downgrades its own task and removes a required review without any separately attributable authorized assessment. |
| **`AEW-FR-39.f`** | AEW shall establish the minimum applicable control class for consequential work using observable work properties and an authorized classification rule, and shall not permit a classifier to lower that floor by its own assertion. | A Lead confidently assigns a deployment-topology change to a no-review class despite a governing rule that its observable effects require a higher control floor. |
| **`AEW-FR-39.g`** | AEW shall not use an undefined governing rule or required parameter to authorize a less-protective action; it shall apply an established applicable protective control or hold the affected action for responsible-authority resolution. | A new deployment admits a risky action without review because the classification threshold has not yet been defined. |

## 3. Candidate acceptance and adversarial scenarios

These are intended examples for contract derivation; **no scenario is asserted to pass**. A scenario may exercise multiple requirements, while each atomic obligation still needs its own conformance disposition. Contracts determine the executable test boundaries and expected outputs.

**Scenario identity and preservation:** `AS-01` etc. are stable references to versioned acceptance intent. They must remain traceable from applicable atomic requirements through contract acceptance cases and executable tests to qualified observations. Do not silently delete, renumber, or rewrite a scenario to make a test pass; record scenario changes and impacted traces. Scenarios explain representative behavior, but are not an independent authority to expand adopted atomic obligations. A zero-scenario-reference atom is a **coverage-review signal**, not automatically a missing requirement or a test failure.

| Scenario | Expected outcome / disconfirmation target | Representative atomic IDs |
|---|---|---|
| **AS-01 — VM B port loses remote hops** | Agent plans to port installer but omits existing remote-hop topology. Agent must inspect supplied implementation, record consequential assumptions, seek clarification when topology ambiguous, and refrain from silently changing deployment objective. | `AEW-FR-03.a`, `AEW-FR-03.b`, `AEW-FR-03.c`, `AEW-FR-39.b`, `AEW-FR-39.c`, `AEW-FR-39.f` |
| **AS-02 — Mixed authority within a project** | Externally controlled security contract and operator-owned design coexist; advisory critique does not change the former. | `AEW-FR-01.a`, `AEW-FR-01.c`, `AEW-FR-02.b`, `AEW-FR-04.c` |
| **AS-03 — Scope expansion temptation** | A limited test-harness task discovers a larger production defect; report and link it but do not implement unrelated changes. | `AEW-FR-05.a`, `AEW-FR-05.c`, `AEW-FR-18.a`, `AEW-FR-18.e` |
| **AS-04 — Valgrind failure and silent suppression** | A required check fails and a worker attempts to disable it to declare success; suppressing the check must not produce an unqualified PASS. | `AEW-FR-13.a`, `AEW-FR-13.b`, `AEW-FR-13.c`, `AEW-FR-13.d` |
| **AS-05 — Consumer obligation missed by unit tests** | Local tests pass but a changed boundary requires integration validation; the completion claim must accurately qualify missing evidence. | `AEW-FR-07.a`, `AEW-FR-07.b`, `AEW-FR-07.c`, `AEW-FR-07.d`, `AEW-FR-12.b`, `AEW-FR-12.d`, `AEW-FR-14.d`, `AEW-FR-16.b` |
| **AS-06 — Fresh-context morning resume** | Fresh Lead recovers current objective and qualified evidence; continues valid authorized work without mandatory replanning and identifies stale authority. | `AEW-FR-19.a`, `AEW-FR-19.b`, `AEW-FR-23.a`, `AEW-FR-23.b`, `AEW-FR-23.c`, `AEW-FR-23.d`, `AEW-FR-20.a` |
| **AS-07 — Two checkout-specific test techniques** | A second agent verifies a new test command on a different configuration; both techniques retain applicable evidence rather than overwrite each other. | `AEW-FR-20.b`, `AEW-FR-20.c`, `AEW-FR-21.b`, `AEW-FR-21.c`, `AEW-FR-22.e` |
| **AS-08 — Cross-project lesson** | Relevant shared experience can be found in a new authorized project, without exposing private original project notes. | `AEW-FR-21.a`, `AEW-FR-21.b`, `AEW-FR-21.d`, `AEW-FR-22.a` |
| **AS-09 — Immediate shared prerequisite** | A worker finds a build prerequisite relevant to two active workers; discovery reaches them without every worker polling, and individual objectives remain distinct. | `AEW-FR-08.a`, `AEW-FR-08.b`, `AEW-FR-08.c`, `AEW-FR-22.c`, `AEW-FR-22.d` |
| **AS-10 — Parallel workers conflict** | Two independent assignments collide on shared mutable work; detect, qualify and support authorized reorganization while preserving progress. | `AEW-FR-09.b`, `AEW-FR-09.c`, `AEW-FR-11.a`, `AEW-FR-11.b`, `AEW-FR-37.a` |
| **AS-11 — Timeout loop versus legitimate analysis** | Repeated unchanged timeouts are detected without wrongly terminating an agent that has not modified files while reasoning. | `AEW-FR-24.a`, `AEW-FR-24.b`, `AEW-FR-24.c`, `AEW-FR-24.e`, `AEW-FR-25.a`, `AEW-FR-25.b`, `AEW-FR-25.c` |
| **AS-12 — Advisor resource contention** | Advisor requests from routine implementation do not displace critical reviews; blocked work yields capacity instead of artificial busywork. | `AEW-FR-10.a`, `AEW-FR-10.c`, `AEW-FR-26.a`, `AEW-FR-26.b`, `AEW-FR-26.c`, `AEW-FR-26.e`, `AEW-FR-27.b`, `AEW-FR-27.c` |
| **AS-13 — Story 30 regresses Story 2** | Preserve Story 2 historical verification; attach new finding to both the origin behavior and causing change with qualified evidence. | `AEW-FR-17.a`, `AEW-FR-17.b`, `AEW-FR-17.c`, `AEW-FR-17.d`, `AEW-FR-18.b`, `AEW-FR-18.c`, `AEW-FR-14.b` |
| **AS-14 — Original Story 2 obligation was never met** | New evidence shows original criterion not satisfied; enable corrective work without falsely stating Story 2 once passed or auto-authorizing a fix. | `AEW-FR-17.c`, `AEW-FR-18.b`, `AEW-FR-18.e`, `AEW-FR-16.b` |
| **AS-15 — Four-hour optional verification** | Applicable gates pass; an extra test might help. Present expected benefit/cost and residual gap, without treating a percentage as an acceptance rule. | `AEW-FR-15.a`, `AEW-FR-15.b`, `AEW-FR-15.c`, `AEW-FR-15.d`, `AEW-FR-16.a` |
| **AS-16 — Cheap status and gateway outage** | Read current or explicitly stale status and inspect persisted engineering history and lessons with no Lead or LLM gateway. | `AEW-FR-29.a`, `AEW-FR-29.b`, `AEW-FR-29.c`, `AEW-FR-29.d`, `AEW-FR-30.a`, `AEW-FR-30.c` |
| **AS-17 — Former Lead asserts current authority** | Stale generation requests protected action; enforce current authorization and reject mutation. | `AEW-FR-31.a`, `AEW-FR-31.b`, `AEW-FR-31.e`, `AEW-FR-31.i` |
| **AS-18 — Crash during protected transition** | Interrupted effect and retry produce qualified unknown/incomplete state until reconciled, not fabricated success. | `AEW-FR-32.a`, `AEW-FR-32.b`, `AEW-FR-32.c`, `AEW-FR-32.d` |
| **AS-19 — False builder completion claim** | Builder reports success; independent review and actual behavior verification disagree. Treat claim as data and retain contradictory evidence. | `AEW-FR-12.a`, `AEW-FR-12.b`, `AEW-FR-12.c`, `AEW-FR-14.c` |
| **AS-20 — Poisoned cross-project knowledge entry** | Malicious retrieved knowledge attempts tool authority escalation; consumer must not obey it and must support quarantine while retaining provenance. | `AEW-FR-20.d`, `AEW-FR-38.a`, `AEW-FR-38.b`, `AEW-FR-38.c` |
| **AS-21 — Operator emergency revoke despite in-flight model** | An operator revokes a compromised actor while it is reasoning; AEW refuses new protected effects even if context preservation is impossible. | `AEW-FR-31.d`, `AEW-FR-31.e`, `AEW-FR-31.f`, `AEW-FR-31.g`, `AEW-FR-31.h`, `AEW-FR-25.d` |
| **AS-22 — Large-repository concurrent isolation** | An otherwise supported very large repository makes worktree-per-worker infeasible; concurrent work still must not corrupt each other, while declaring real containment accurately. | `AEW-FR-37.a`, `AEW-FR-37.b`, `AEW-FR-37.c` |
| **AS-23 — Evaluation against simpler baseline** | Run representative tasks under qualified objectives and evidence criteria; compare AEW orchestration with authorized simpler approach without claiming universal superiority. | `AEW-FR-33.a`, `AEW-FR-33.b` |
| **AS-24 — Disconnected upgrade and sensitive evidence** | Approved offline profile retains local record access across supported upgrade; secrets in underlying test artifacts do not leak into general logs/knowledge. | `AEW-FR-30.a`, `AEW-FR-34.a`, `AEW-FR-35.a`, `AEW-FR-35.b`, `AEW-FR-36.a`, `AEW-FR-36.b`, `AEW-FR-36.c` |
| **AS-25 — Unconfirmed low-risk classification** | A proposed change is called trivial though it changes execution topology; its classification and assumptions are auditable and the consequential ambiguity receives authority review. | `AEW-FR-03.b`, `AEW-FR-03.c`, `AEW-FR-39.a`, `AEW-FR-39.b`, `AEW-FR-39.c` |
| **AS-26 — Normal bounded engineering task** | Operator delegates an ordinary bounded change; AEW retrieves relevant project context, applies a lightweight path retaining mandatory controls, implements and independently checks the result where required, reports qualified completion, and continues without unneeded approvals. | `AEW-FR-03.d`, `AEW-FR-05.b`, `AEW-FR-06.a`, `AEW-FR-06.b`, `AEW-FR-06.c`, `AEW-FR-12.a`, `AEW-FR-16.a`, `AEW-FR-28.a` |
| **AS-27 — Scope/authority decisions batched; blocker promptly escalated** | Routine implementation choices stay with the Lead; nonurgent operator decisions arrive together with recommendations, while a foundational dependent-work blocker reaches the operator promptly and unaffected work continues. | `AEW-FR-02.b`, `AEW-FR-16.c`, `AEW-FR-16.d`, `AEW-FR-28.a`, `AEW-FR-28.b`, `AEW-FR-28.c`, `AEW-FR-28.d` |
| **AS-28 — Hard ceiling reached during ongoing work** | AEW prevents an already running mediated worker from continuing to spend past an enforceable ceiling, honestly identifies any unmediated channel, and preserves or qualifies lost context. | `AEW-FR-10.a`, `AEW-FR-10.f`, `AEW-FR-25.d`, `AEW-FR-31.g`, `AEW-FR-31.h`, `AEW-FR-31.j` |
| **AS-29 — Assessor independence and changed checks** | Builder supplies a success claim and modifies a governing test; independent assessor applies protected acceptance criteria and rejects the purported pass absent required authorization/requalification. | `AEW-FR-12.a`, `AEW-FR-12.c`, `AEW-FR-12.f`, `AEW-FR-13.a`, `AEW-FR-14.a`, `AEW-FR-39.e` |
| **AS-30 — Composition and inherited gates** | Each child implementation passes locally, but a required consumer boundary fails and a parent security gate remains in force; parent cannot be declared verified or downgraded via decomposition. | `AEW-FR-06.c`, `AEW-FR-07.d`, `AEW-FR-07.e`, `AEW-FR-12.d`, `AEW-FR-12.g` |
| **AS-31 — Deliberate low-risk classification and improper downgrade** | A routine bounded change is allowed a light path, while an uncertain topology-changing modification uses the protected path; a proposed downgrade removing mandatory review is independently assessed. | `AEW-FR-06.a`, `AEW-FR-06.c`, `AEW-FR-39.a`, `AEW-FR-39.b`, `AEW-FR-39.c`, `AEW-FR-39.d`, `AEW-FR-39.e` |
| **AS-32 — Restricted-deployment profile with explicit limitations** | In a declared supported disconnected deployment, local work records and available local coordination operate without hosted SaaS; unavailable remote-model features are clearly reported, without pretending live execution exists. | `AEW-FR-30.a`, `AEW-FR-34.a`, `AEW-FR-34.b` |
| **AS-33 — Confidently wrong intake classification** | A Lead labels a deployment topology change trivial with a confident rationale. The observable protected-boundary properties force the governing minimum class; neither confidence nor a recorded explanation lowers the floor. | `AEW-FR-03.a`, `AEW-FR-39.b`, `AEW-FR-39.f`, `AEW-FR-06.c` |
| **AS-34 — Undefined parameter fails protectively** | A new deployment lacks a required control classification threshold. AEW does not treat the absence as permission to use a weaker path; it applies an established protective rule or holds the dependent action for authority resolution. | `AEW-FR-39.g`, `AEW-FR-39.c`, `AEW-FR-06.c` |
| **AS-35 — Delegation does not grant inherited privilege** | An unprivileged worker attempts to delegate a protected effect based only on its parent’s rights or instruction text; AEW rejects the effect without an explicit bounded grant. | `AEW-FR-31.a`, `AEW-FR-31.b`, `AEW-FR-31.i`, `AEW-FR-31.c` |
| **AS-36 — Honest disclosure cannot substitute for minimum containment** | A supported worker-execution profile truthfully labels its shell channel unmediated, but that channel can mutate AEW protected records after revocation. AEW refuses protected execution until the minimum protections are enforceable. | `AEW-FR-31.e`, `AEW-FR-31.g`, `AEW-FR-31.h`, `AEW-FR-31.j`, `AEW-FR-10.f` |
| **AS-37 — Contradicted dependency holds affected work** | A worker produces credible evidence that a foundational premise relied upon by downstream work is false. Affected mutations do not proceed until authorized reassessment, while unrelated valid work can continue. | `AEW-FR-04.a`, `AEW-FR-04.b`, `AEW-FR-04.d`, `AEW-FR-16.c`, `AEW-FR-11.c`, `AEW-FR-24.d` |
| **AS-38 — Outage read path retains authorization** | The LLM gateway and main orchestration service are unavailable. An authorized operator retrieves time-qualified records through a fallback read path; an unauthorized actor cannot use that path to read secrets or modify protected state. | `AEW-FR-30.a`, `AEW-FR-30.b`, `AEW-FR-30.c`, `AEW-FR-30.d`, `AEW-FR-31.j` |

**Scenario coverage status:** This is a representative *candidate* scenario suite, not a claim that every atomic requirement has an implemented test. Traceability coverage must be measured against all adopted atomic clauses and actual contract acceptance cases after adoption.

## 4. Reverse trace against archival invariants — preliminary, not complete

The independent reviewer requested reverse tracing currently adopted invariants/ADRs before adoption. The archived `repo-main/docs/design/invariant-index.md` identifies cross-cutting invariant claims and governing-source pointers. This is a **preliminary mapping of that index into the candidate atomic FRs**, not verification of which individual historical clauses are operator-adopted, not a review of every ADR, and not a completed as-built audit. A full effective-obligation inventory is **not asserted complete**. The provisional triage below is intended to expose candidate coverage gaps while contract recovery proceeds; historical protective controls remain effective.

| Archived invariant | Candidate foundational anchor(s) | Preliminary sufficiency triage — **source and adoption unverified** |
|---|---|---|
| `AEW-INV-AUTH-001` — Coordination may move knowledge; only existing AEW authority paths may move project state. | `AEW-FR-01.b`, `AEW-FR-31.a`, `AEW-FR-31.b` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-CLASS-001` — If a classifier can choose categories with different ceremony, default to the heavier category; downgrading requires recorded justification reviewable by an independent actor. | `AEW-FR-39.a`, `AEW-FR-39.b`, `AEW-FR-39.c`, `AEW-FR-39.d`, `AEW-FR-39.e`, `AEW-FR-39.f` | **Partial anchor** — historical rule strength and independent-review scope require source-grounded reconciliation |
| `AEW-INV-RESOURCE-001` — Individually legal delegation, isolation, retry, capability, or parallelism choices must not compose into globally pathological behavior. | `AEW-FR-10.a`, `AEW-FR-09.d`, `AEW-FR-26.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-TRACE-001` — Registries/indexes improve discoverability but do not become alternate workflow authority. | `AEW-FR-19.d`, `AEW-FR-20.d` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-LEAD-001` — Lead investigates engineering-derivable facts before asking the stakeholder. | `AEW-FR-03.a`, `AEW-FR-03.d`, `AEW-FR-28.a` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-LEAD-002` — Work proceeds autonomously inside the approved envelope; material departure returns to stakeholder authority. | `AEW-FR-02.b`, `AEW-FR-05.a`, `AEW-FR-05.b` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-DELEG-001` — Worker roles receive no dispatch/delegate capability by default. | `AEW-FR-31.a`, `AEW-FR-31.b`, `AEW-FR-31.i` | **Partial anchor** — establish precise effective default-deny delegation before replacing current safeguards |
| `AEW-INV-DELEG-002` — Nested delegation requires explicit bounded AEW capability authority and is not inherited. | `AEW-FR-31.b`, `AEW-FR-31.i`, `AEW-FR-10.a` | **Partial anchor** — concrete nested-delegation safeguards require source-grounded reconciliation |
| `AEW-INV-DELEG-003` — Duplicate work requires explicit ensemble/evaluation purpose. | `AEW-FR-08.d`, `AEW-FR-12.f`, `AEW-FR-06.a` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-PERM-001` — Capability aggregation is exact-match by capability, scope, and approved objective unless a future deterministic rule proves safe reuse. | `AEW-FR-31.b` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-CANCEL-001` — Canceling an objective revokes descendant credentials/capability authority. | `AEW-FR-31.d`, `AEW-FR-31.e` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-ATTN-001` — Human-interruption budgets batch questions; they never authorize silent answers to consequential questions. | `AEW-FR-28.b`, `AEW-FR-28.c`, `AEW-FR-39.c` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-INTENT-001` — Free-form authored semantics cross ingress as opaque data, not shell-interpreted syntax. | `AEW-FR-31.a`, `AEW-FR-36.a` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-HIER-001` — Parents preserve purpose; Tickets preserve proof. | `AEW-FR-07.a`, `AEW-FR-07.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-HIER-002` — After acceptance-bearing evidence is bound, semantic field changes are MATERIAL by default. | `AEW-FR-07.b`, `AEW-FR-14.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-HIER-003` — Downgrading to CLARIFICATION requires recorded justification plus fresh-context independent confirmation. | `AEW-FR-39.b`, `AEW-FR-39.e`, `AEW-FR-39.c`, `AEW-FR-39.f` | **Partial anchor** — fresh-context condition is not established by generic independence |
| `AEW-INV-HIER-004` — Supersession is a relationship over existing lifecycle states, not a new execution state. | `AEW-FR-17.a`, `AEW-FR-17.d` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-HIER-005` — Parent closeout requires explicit disposition of every superseded descendant. | `AEW-FR-07.a`, `AEW-FR-17.a` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-HIER-006` — Story/Epic revisions are compared to the approved envelope baseline, not only the previous revision. | `AEW-FR-02.b`, `AEW-FR-07.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-EVID-001` — Historically valid evidence and currently admissible evidence are distinct; history is preserved while gates use current admissibility. | `AEW-FR-14.b`, `AEW-FR-17.d` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-VERIFY-001` — Verifier reports evidence and may propose classification; Lead decides; uncertainty/design signals default to heavier replan path. | `AEW-FR-12.c`, `AEW-FR-39.a` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ISO-001` — Workdir separation is not OS-level containment and must be labeled honestly. | `AEW-FR-37.c` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-ISO-002` — Strong containment must pass the containment regression gate before real-repository dogfood/internal alpha. | `AEW-FR-37.a`, `AEW-FR-31.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ISO-003` — Isolation benchmarks gate selection of a project-default strategy. | `AEW-FR-37.b`, `AEW-FR-33.a` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-ISO-004` — Shared-mutable serialization locks are invocation-bound; stale owners are reconciled before release. | `AEW-FR-37.a`, `AEW-FR-32.a` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-INTEGRATE-001` — Filesystem isolation does not prove semantic independence; integration-stage checks must catch cross-Ticket conflict/overlap. | `AEW-FR-07.d`, `AEW-FR-12.g`, `AEW-FR-37.c` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-SCRATCH-001` — Temporary output uses explicit scoped scratch; scratch does not become authoritative evidence by existence. | `AEW-FR-14.a`, `AEW-FR-31.a` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-COORD-001` — Relevance hints are advisory only and cannot route, hold, mutate, widen scope, or grant authority. | `AEW-FR-09.c`, `AEW-FR-31.a` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-COORD-002` — Absence of declared dependency/overlap hint never proves work unaffected. | `AEW-FR-09.b`, `AEW-FR-14.d` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-COORD-003` — Material assignment changes supersede/re-dispatch; they are not smuggled through as context deltas. | `AEW-FR-11.c`, `AEW-FR-07.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-COORD-004` — Contradictory findings remain separately attributable until explicitly resolved. | `AEW-FR-14.c`, `AEW-FR-18.c` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-COORD-005` — Coordination history cannot satisfy evidence/review/verification gates merely because it was routed or summarized. | `AEW-FR-08.c`, `AEW-FR-12.a` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-ASSURE-001` — When independent assurance is required, acceptance is independently reconstructed before the proposed plan is revealed to the assurance role. | `AEW-FR-12.f` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-ASSURE-002` — Acceptance resources and protected conditions are distinct from the mutation subject. | `AEW-FR-12.f`, `AEW-FR-13.a`, `AEW-FR-31.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ASSURE-003` — A baseline counts only if it exercised the intended proposition. | `AEW-FR-12.b`, `AEW-FR-14.a` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-ASSURE-004` — Assurance binds the versioned dependency set, not plan text alone. | `AEW-FR-14.a`, `AEW-FR-14.b` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ASSURE-005` — Review metadata cannot change the payload it reviews. | `AEW-FR-12.f`, `AEW-FR-14.a`, `AEW-FR-14.c` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ASSURE-006` — Clearing a blocker is a separate attributable artifact; the blocking finding is never rewritten. | `AEW-FR-13.b`, `AEW-FR-14.c` | **Partial anchor** — governing detail needs further outcome review |
| `AEW-INV-ASSURE-007` — Every dispatch path uses one computed predicate. | `AEW-FR-07.c`, `AEW-FR-31.b` | **Potential mechanism** — assess necessity without auto-ratification |
| `AEW-INV-ASSURE-008` — A contradicted load-bearing premise holds the affected mutation until reassessed. | `AEW-FR-04.a`, `AEW-FR-04.d`, `AEW-FR-16.c` | **Partial anchor** — determine whether historical hold semantics require stronger boundary guarantees |
| `AEW-INV-ASSURE-009` — Inherited parent obligations cannot disappear at a child. | `AEW-FR-06.c`, `AEW-FR-07.b`, `AEW-FR-07.e` | **General outcome candidate** — governing source still to be checked |
| `AEW-INV-ASSURE-010` — Passing child work does not prove composed parent behavior. | `AEW-FR-12.d`, `AEW-FR-12.g`, `AEW-FR-16.b` | **General outcome candidate** — governing source still to be checked |

**How to interpret this triage:** “General outcome candidate” means the index summary appears supported by a foundational outcome; it does **not** establish complete equivalence to the governing clause. “Partial anchor” marks possible missing strength or a contract-specific obligation. “Potential mechanism” flags a particular historically effective implementation/review technique that may be replaceable; it **must not be disabled simply because it is not repeated as an FR**. No row is a claim of implemented or verified conformance.

**Reverse-trace observations that require deliberate review:**

1. The index includes more precise historical implementation policies than any foundational requirement should specify (e.g., exact-match capability aggregation, plan disclosure ordering, lock lifetimes, named risk categories, review metadata rules). Determine which implement real general guarantees and which are replaceable domain mechanisms. Do not automatically ratify all as new FR text.
2. Some existing controls implement authority/revocation and containment protections with consequences not fully captured by an abstract feature statement. Preserve the effective controls while reviewing them against `31.*`, `32.*`, and `37.*`.
3. The invariant index itself is explicitly **nonauthoritative**; its referenced governing sources must be inspected, along with effective adopted overlays and ADR dispositions. The mapping above is an evidence locator, not adoption validation.
4. The archival `docs/spec-amendments.yaml` purports to identify effective adopted WC/KC overlays; `docs/design/requirements-ledger.yaml` tracks design headings/work rows; `docs/implementation/future-work.yaml` tracks execution work. Reuse suitable mechanisms, but do not confuse index presence, adopted language, implemented behavior, or passing tests.
5. **Adoption decision:** An exhaustive historical inventory can be performed incrementally during contract recovery rather than delaying product-purpose adoption indefinitely. Before replacing or retiring any effective protection, trace its controlling source to the adopted outcome and secure explicit safe disposition. Any newly discovered foundational gap returns for operator amendment; no silent promotion of historical mechanism to product purpose.

## 5. Traceability and conformance governance proposal

**Recommended unit of traceability: one `AEW-FR-NN.x` atomic clause.** A topic heading has no conformance result. An atomic clause may map to several umbrella/domain contract clauses, work items, implementation boundaries, acceptance cases and distinct evidence receipts. A test can support multiple clauses, but the evidence qualification and disposition must be explicit **per clause**. This accommodates the operator's one-requirement-to-one-or-many implementation/test relationships without forcing a false uniqueness of implementation.

**Forward:** `atomic FR → governing umbrella obligation → domain/boundary contract → implementation responsibility/work item → versioned AS scenario(s) and contract acceptance cases → executable test(s) → qualified evidence/disposition`.

**Reverse:** `implementation change or failing observation → test and acceptance case → versioned AS scenario(s) → affected domain obligation(s) → umbrella guarantee(s) → atomic FRs → dependent work and previously accepted evidence`.

Minimal per-clause trace metadata: exact atomic ID, source version/adoption authority, controlling contract clause(s), applicable versioned AS identifiers, implementation owner/work IDs, executable verification case(s), observed evidence and applicability, current qualification and last validated conditions. Scenario trace metadata shall include stable AS ID, text/version, affected atomic IDs, contract cases, test IDs, and corresponding evidence once these exist. Relationships are many-to-many at the graph level but **never replace an atomic requirement with a compound one**. Traceability completion is not equivalent to conforming implementation.

**No parallel authority:** Reuse or repair the nonauthoritative requirements ledger, invariant index, amendment index and work tracking rather than building another normative register. A materialized RTM and scenario-reference index can be generated as nonauthoritative views when useful. If a structured source later becomes the adopted source of truth, migrate rather than maintain competing manually edited normative copies. Keep stable AS identities and reject unreviewed orphaning or silent revision of previously linked cases. Mechanically report atomic clauses with no scenario or verification-case reference and scenarios with broken atomic references, without confusing scenario coverage with executed proof. No presumption that any of the archival checks ran successfully in this review.

## 6. Review dispositions on both independent reviews

| Finding | Proposed disposition |
|---|---|
| Compound requirements | **Accept.** 32 former headlines are groups only; 164 atomic independently addressable clauses with one disconfirmation question each. |
| Judgment words lack authority | **Accept with operational guardrail.** Use `39.*` including an observable control floor and recorded material assumptions (`03.c`); require confirmation for ungoverned consequential uncertainty without mandatory independent agent review of trivial decisions. |
| Priority and emergency revoke | **Accept.** Explicit interpretation priority and `31.d–f`; preservation preference never defeats valid protective action. |
| Claims versus evidence, evaluability | **Accept.** `12.a–c`, `33.*`; comparison with simpler approaches, no universal superiority assumption. |
| Disconnected deployment | **Accept with nuance.** `34.*` describes supported restricted operating profiles; does not forbid hosted capabilities in other deployments. |
| Record upgrade compatibility / secret leakage / large-repo isolation / knowledge poisoning | **Accept.** `35.*–38.*`; avoid technology and fixed repository-size prescriptions. |
| Advisor tiers and waiting mechanism | **Accept.** `26.*–27.*` express scarce-capacity protection and non-wasteful blocked work without mandating Astra, a queue type, or a new lifecycle state. |
| Reverse trace and adoption sequencing | **Accept with sequencing correction.** Invariant summaries have preliminary three-way sufficiency triage in §4; effective governing sources still need reconciliation. Adoption need not await an unbounded full inventory, but no current protective control may be weakened or retired on an unverified mapping. |
| Scenario linkage and adversarial coverage | **Accept.** Scenarios use atomic IDs; add false-completion, knowledge poisoning, emergency revocation, deployment and evaluation cases. |
| Duplicate old FR identifiers | **Accept.** Seed `FR-01…11` and conversation `FR-12…44` are retired as *non-adopted drafting references*; only `AEW-FR-NN.x` are current v0.4 proposal IDs. |
| Protected assessor independence and composition | **Accept; refine.** Add `12.f–g`, `07.e`, and scenarios; historical review ordering remains contract-level until justified by outcome. |
| Objective verification manipulation | **Accept.** Reframe `13.a` around observable modifications and evidence acceptance instead of inferring purpose; separately authorized test corrections remain possible. |
| Ongoing limits and mediator completeness | **Accept.** Use `10.f`, `31.g–j`; do not claim control over unmediated execution channels or admit execution that evades the mandatory protected-state minimum. |
| Classification downgrade accountability | **Accept.** Add separate conservative-default and independent-downgrade obligations `39.d–e`. |
| Product intent, release scope and status axes | **Accept.** Add ordinary user journey and explicit authority/realization/verification dimensions; release planning remains a separate operator decision. |
| Deferred contract parameters and test criticality | **Accept.** Add named parameter resolution worklist and criticality approach; do not pretend numeric limits are already adopted. |
| Full historic reconciliation as adoption gate | **Qualify.** Continue it alongside contract recovery. No historical operational safeguard is superseded until explicitly and safely disposed. |
| Two-sided nonconvergence classification | **Accept.** Separate false-negative (`24.b`) and false-positive (`24.e`) obligations. |


### v0.4 final-review dispositions (designer recommendation; not adopted)

- **Accept with refinement:** `39.f` sets an observable classification floor against confident misclassification. `39.g` makes undefined critical parameters fail protectively. Independent downgrade review remains necessary when a change *actually removes* an otherwise mandatory control. Recomputing a classification according to an authorized rule without removing mandatory controls is not automatically a downgrade review event. An appropriately authorized operator can serve as the independent assessor if not the original classifier.
- **Accept with deployment boundary:** `31.i` establishes explicit, non-inherited delegation; `31.j` establishes a *non-vacuous minimum* for supported agent-execution pathways that can affect protected AEW authority state, records, or credentials. This does **not** pretend AEW can control arbitrary external OS actions outside declared mediation. `31.g–h` still require honest channel-level coverage claims.
- **Accept with evidence discipline:** `12.f` protects independent assessment of authorized criteria while permitting examination of builder claims; `13.a` prevents an unchecked verification PASS after alteration of governing checks. Detection and attribution of alterations must not rest solely on the author deciding an alteration was immaterial.
- **Accept:** requirement adoption is distinct from when an applicable obligation becomes due; currently operative protections cannot be postponed by a new release label.
- **Accept, retaining original intent:** stable acceptance/adversarial scenario identities and bidirectional links must survive contract derivation and later evidence qualification; the scenarios are not independent normative authorities.
- **Defer source-format choice:** a structured requirements source and generated Markdown may ultimately be useful for mechanical integrity checks, but switching normative source formats is not necessary to approve a correct v0.4 wording. A generated nonauthoritative scenario index accompanies this candidate for inspection, not as a second normative catalogue.
- **Do not automatically adopt archival mechanisms:** maintain the pending partial mappings until the actual governing source is examined. Continue effective legacy protections while reconciling.

## 7. Explicit non-decisions

This candidate does **not** mandate a specific database, graph, vector index, MCP server, queue, activity monitor, model tier hierarchy, harness, revision scheme, test framework, number of workers, worktree isolation algorithm, extra Ticket lifecycle state, web dashboard, particular numeric cost/latency threshold, or universal conformance scoring algorithm. Contract boundaries may legitimately specify such mechanisms only where the user adopts them as applicable requirements or they are implementation decisions that satisfy the independent obligations.

The independent reviewer's proposed exact historical review classes, held-state mechanics, and advisor seats are subjects for contract/as-built reconciliation, not automatic new foundational truth. Existing effective protective controls still remain operative during that work.

## 8. Open operator decisions and recommended sequence

1. **Review product purpose:** Confirm §1.1 accurately represents the ordinary AEW operator/Lead/worker experience and the important exceptions from elicitation. The narrative is explanatory; adopted authority resides in the atomic clauses.
2. **Review amended atoms:** Focus on revised `12.f`, `13.a`, and added `04.d`, `31.i–j`, `39.f–g`, alongside previously added `10.f`, `31.g–h`, and `39.d–e`. Existing v0.3 atomic IDs are preserved. **None are adopted by this revision.**
3. **Set baseline applicability:** Distinguish enduring product obligations, supported deployment or capability conditions, and release/milestone implementation commitments. No delivery schedule or universal rollout claim is adopted here.
4. **Adopt selectively or amend:** The operator may adopt the reviewed requirements without pretending historical reverse reconciliation is complete; the currently effective operational controls continue until explicitly and safely superseded. Uncovered foundational outcomes uncovered during reconciliation require operator amendment, not retroactive silent insertion.
5. **Contract recovery:** Start with decision/delegation authority, independent assurance, effect-channel coverage, and work/evidence composition guarantees. Resolve the parameter register (§1.6) in the owning contracts before those promises are claimed verified.
6. **Trace and validate:** Map adopted clauses to recovered umbrella/domain guarantees, source responsibility, acceptance cases, qualified evidence, and release/applicability. Let as-built evidence decide realization, never normative authority.

### Verbatim-ready Decision Record — recommendation only, **not operator-adopted**

1. **Product foundation:** Review the AEW product-purpose and ordinary-workday description in §1.1 as explanatory context for the foundational requirements; do not make it a second source of normative authority.
2. **Atomic amendment:** Consider `AEW Foundational Requirements — Candidate Baseline v0.4`, preserving v0.3 atomic IDs and strengthening classification floors, default-deny delegation, minimum mediated protected effects, contradicted foundations, and fail-protectively undefined controls.
3. **Scope and evidence status:** Track normative adoption, as-built realization, and verification qualification separately. Adopt deployment and release scope deliberately; do not infer that a requirement has been implemented or tested from its adoption.
4. **Historical reconciliation:** Continue source-grounded reverse tracing during contract recovery. Distinguish general outcome coverage, partial coverage, and potentially replaceable mechanisms. Existing effective safety/authority/evidence protections remain operative until safely and explicitly superseded.
5. **Next action:** Obtain operator review of the candidate baseline, including the 38 stable acceptance scenarios and their traces, and record approved clauses or requested amendments. Only an explicit authority decision adopts foundational obligations.

**End — candidate baseline v0.4.**
