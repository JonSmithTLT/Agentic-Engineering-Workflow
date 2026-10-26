<!--
generated: do not edit; regenerated from the adopted design text (see README.md)
position: A-15
source: 10-adopted/RECONCILED-SOURCE-BASELINE/01-ADOPTED-SOURCE-BYTES/A-15__AEW-R01-Resource-and-Progress-Supervision-Contract-candidate-v0.2.1.md
source-sha256: 7d5eed2cca49efb18e32f418821a616da2a5c4a9b2c4cb77e9a8acf2b6ba7550
edits-sha256: none
-->

# AEW R-01 — Resource, Progress, Advice and Recovery Supervision Boundary Contract

**Candidate v0.2.1 · 2026-10-17 · PROPOSED NORMATIVE, NOT ADOPTED**

## 0. Status, authority and scope

**Status:** PROPOSED NORMATIVE — focused v0.2.1 metering-integrity revision for independent architectural review (2026-10-17). Not adopted, not deployed, and not a qualification or permission to activate any automated response.

**Architecture baseline:** The 14 separately operator-adopted normative sources in `03-SOURCES/ADOPTED/`; their pinned digests and decisions are preserved without alteration. LCO v0.2.1 is an approved **nonnormative** composition challenge. Reconstructed foundational requirements are a trace tool, not newly adopted requirements.

**Intent:** AEW must detect useful progress or genuine blockage and allocate scarce resources effectively while remaining an engineering harness, not a new autonomous supervisor free to override protected authority. AEW executes natively on a Rocky 8 VM; selected supporting tool/MCP servers may run in containers. The VM/shared-login arrangement does not establish an agent-inaccessible protected writer.

**Substitutable logical capabilities, not required services:** Resource admission/accounting; qualified run/progress observations; coordination/advice/waiting; intervention/recovery and operator presentation. Existing ADC/HEB/WIS/CNI/AEV owners provide underlying authority. The profiles for their exchange are separately frozen only when an actual implementation/release slice is chosen.

**Normative interpretation:** “SHALL” and “MUST” identify proposed obligations pending operator adoption. Scenario verdicts are unexecuted expectations.

## 1. Authority and producer/consumer map

| Canonical fact/decision | Competent source/owner | R-01 role and consumers | Forbidden inference |
|---|---|---|---|
| Grant, classification, premium escalation, intervention eligibility | ADC/operator-approved policy and authority owner | Ask/qualify; HEB/Lead, operator, AOI | Queue acceptance extends a grant |
| Effective process custody and protected effects | HEB protected execution/effect producer | Qualified run and remote-effect status to CNI/Lead/AOI | Heartbeat implies process or remote effect stopped |
| Work objective/revision, dependency and accepted premise | WIS and CNI | Bind allocations, waits and recovery to current work; never rewrite | An advisor redefines objective |
| Review outcomes/qualified assurance | AEV | Expose blocker and validity of recovery; no override | Retry clears unrelated HOLD |
| Qualified Knowledge and map/context | K-01, P-01 and their source owners | Advisory/citation context for diagnosis and resume | Retrieved text is permission |
| Resource limits and accounting | Operator/ADC policy for limits; qualified resource-control writer for reservations/encumbrances; independently qualified provider/gateway/effect-path meter for consumption and original-operation attribution | Bounded qualified usage/cost comparison, conservative unknowns and admission-bound attribution | An agent-supplied run record or client lineage tag certifies spend, permits settlement or releases headroom |
| Operator/website/agent views | AOI/D-01 consumer of owner-qualified projections | Actionable, confidential status, without second truth | UI “ready” is admission proof |

Required relationships: ADC-governed resource policy→qualified resource-control admission with HEB effect mediation→active run observation→CNI waiting/progress→Lead/operator attention; independently qualified metering and billing→original-admission-bound attribution→resource reconciliation→future capacity decisions; block source→CNI wait→HEB capacity yield→source resolution→requalified work resume; advisor queue→scoped opinion→Lead decision, with AEV independent of consultation; HEB crash/unknown effects→bounded recovery→WIS/AEV/CNI reconciliation. Notifications may be lost and do not replace current owner checks.

## 2. States and composition semantics

**Resource observation and decision are different.** `REQUESTED`, `RESERVED`, `ACTIVE`, `RELEASE_PENDING`, `RELEASED`, `EXHAUSTED`, `UNKNOWN` are illustrative state labels. Any externally spent but unsettled usage is accounted separately. A positive reservation requires an independently qualified protected resource-control writer and enforceable effect path; a UI projection, an agent-writable ledger, or an optimistic scheduler result never creates one. Resource-control semantics are defined here without creating a second policy or grant authority.

**Degraded telemetry integrity:** On the shared-login native VM, a run directory, heartbeat or client-supplied usage file reachable by the metered agent is agent-reported data, not automatically a protected HEB-observed fact or qualified consumption meter. Qualified observations require their own independently demonstrated observation boundary.

**Run health is distinct from work completion.** `OBSERVED_ACTIVE`, `POSSIBLE_STALL`, `PERMISSION_BLOCKED`, `HARNESS_UNRESPONSIVE`, `RUN_LOST`, `RUN_TERMINAL` and `OBSERVATION_UNKNOWN` are provisional semantic labels. Work progression remains with CNI/WIS; verification with AEV. `NONCONVERGENCE_SUSPECTED` is an engineering diagnosis with different evidence than a process stall.

**Recovery flow:** original attempt observed → classify effect/result certainty → check original authority and eligible recovery class → reconcile exact basis, resource and negative evidence → admit bounded new attempt (if eligible) OR held decision → preserve original and new outcome. No implicit `exactly once` promise for non-idempotent external effects.

**Wait flow:** responsible owner reports blocked dependency → CNI records condition and authorized independent work → HEB yields only unnecessary capacity under custody policy → qualified resolution or reconciliation becomes discoverable → ADC/HEB and CNI requalify authority/currentness → run continues in a supported manner with explicit transient-context-loss limits.

No transition in these illustrative diagrams can authorize effects absent ADC/HEB/CNI conditions.

## 3. Proposed normative obligations



### Capacity, policy and reservation

**R01-01 — Authority partition and product outcome.** R-01 SHALL support bounded allocation, progress diagnosis, proportionate intervention, advice, waiting/yield and safe restart of authorized work. It SHALL define shared, attributable semantics for reservation, usage, lease, encumbrance and release records **without** becoming a separate budget-policy, grant, accepted-scope, protected-effect, assurance or operator-decision authority. Operator/ADC policy governs applicable limits and delegated eligibility; a policy-authorized, integrity-qualified resource-control writer issues authoritative allocation/accounting state for the selected resource class and HEB mediates supported execution/effects. A record writer is a necessary capability, not a requirement for a new standalone service.

*Anchors:* AEW-FR-10; AEW-FR-24–27; ADC-01/08; HEB-06/08; CNI-03/05.

**R01-02 — Competent producer and subject identity.** Each consequential resource/progress assertion SHALL name its competent producer, subject and exact work/revision, assignment/invocation/run, root grant and generation as applicable; resource **policy scope and ancestor scopes** (project/mission/provider/pool/time window), resource class, policy and price version, original operation intent, source observation and qualification, applicable closure/freshness witness and effective-recipient disclosure. The original operation-intent identity and its equivalence basis SHALL be assigned or qualified by the competent authorized coordination/effect-admission owner from WIS work identity and owner-observed operation class and subject; a requester-supplied intent/idempotency key or lineage header is only an attributed alias and SHALL NOT establish a fresh governed intent or attribution. Attachment/generation and run identifiers SHALL be attribution dimensions, not implied fresh parent limits. Missing, contradictory or non-comparable identity/basis is `NOT_ESTABLISHED`, never positive availability.

*Anchors:* AEW-FR-09; WIS-01/07; ADC-02; HEB-01.

**R01-03 — Resource owners and enforcement.** The operator-approved resource policy and ADC-08.f/i govern authorized hard concurrency, usage, rate and spending limits on **ongoing AEW-controlled effects and new allocations** and permit independent unaffected work when a particular effect is unqualified. R-01 defines necessary reservation/usage/lease record semantics; an independently competent, protected writer qualifies admissions and accounting for each selected class. HEB remains responsible for the execution/effect/custody guarantees adopted in HEB, and may host or mediate an actual resource-control implementation only after an explicit supported profile and any necessary HEB amendment. R-01 SHALL NOT assign an unadopted HEB spending-policy obligation by implication, grant execution through a queue projection, or replace CNI dependency state or AEV assurance.

*Anchors:* AEW-FR-10.a/f; ADC-08.f/i/j; HEB-01/03/05 (effect-path guarantees); CNI-03/05.

**R01-04 — Cost, time and scarcity separation.** Resource decisions and projections SHALL distinguish (a) measured or estimated monetary spend and credit, (b) wall duration and deadline, (c) concurrency and scarce model/advisor/fixture capacity, and (d) rate/quota limits. No one dimension silently substitutes for another; prices and usage semantics are versioned and attributed.

*Anchors:* AEW-FR-10.c/d; AEW-FR-26.b/e.

**R01-05 — Budget policy, parent scope and conservation.** Authorized limits, prices, priorities and time windows SHALL have an **accountable, persistent policy-scope identity** separate from individual attachment, Lead generation, grant, assignment, run, provider call and operation attempt. Every child allocation SHALL identify and charge each applicable enclosing shared limit and policy version; a generation change, handover, nested advisor or alternate pool SHALL NOT mint new budget or omit parent commitments. For each limit, available headroom SHALL be computed against a source-qualified nonoverlapping accounting of (a) qualified settled consumption, (b) protected active reservations for prospective exposure, (c) still-chargeable external/in-flight work and (d) unresolved unpriced or late-billing exposure, avoiding unjustified omission **and** double deduction when reservations settle. An unknown that cannot be conservatively bounded precludes a positive admission against that affected hard limit; proven-independent authorized resources remain available. The operator/ADC policy owner alone may issue additional headroom or change limits.

*Anchors:* AEW-FR-10.a/b/c/f; AEW-FR-42.h; ADC-08.f/i.

**R01-06 — Owner-qualified resource availability.** Positive available capacity SHALL require a protected resource-control producer/writer, named resource/policy and **applicable ancestor** scope, epoch, qualified completeness of live leases, reservations, observed and unsettled provider consumption, comparable price/version and authoritative policy witness. An agent report, an unprotected CAS on agent-writable storage, stale usage read or local UI estimate is not this proof. Unknown/incompatible commitment or incomplete parent roster renders the affected limit `NOT_ESTABLISHED`; valid sibling resources are not automatically blocked.

*Anchors:* AEW-FR-10.a/f; CNI-03.c/g; HEB-05.d.

**R01-07 — Aggregate atomic allocation and fencing.** Competing protected admissions for either an exclusive seat **or a shared parent spending/quota cap** SHALL be serialized against the same accountable parent scope and all applicable limits by a protected qualified decision using conditional commit, fencing or an equivalent admission mechanism. Each allocation SHALL bind actor and current ADC/effect authority, grant/generation, exact work and **owner-qualified original operation intent**, resource and ancestor-scope policy revisions, worst-case encumbrance where needed, predecessor/version, expiry and idempotency identity. A requester-created key SHALL NOT establish a new intent or reset an existing cap. Parallel child pools/roles and G1→G2 handover SHALL NOT independently reuse shared headroom. On a policy change, reconcile already-authorized ongoing exposure and apply the new competent policy to future/ongoing effects as required by ADC-08.f; loss/retry uses original intent rather than a new authorization.

*Anchors:* ADC-08.f/i/j; CNI-03.c/g; HEB-05 (effect boundary); AEW-FR-10.a/f.

**R01-08 — Reservation, consumption, attribution and unknown cost.** Reservation, measured consumption, priced bill, estimates, still-chargeable external effects, unpriced exposure, release/settlement and remaining encumbrance SHALL be separately typed and comparable to the **same original operation and every applicable parent policy scope**. Consumption, final settlement and lineage attribution used to enforce a hard limit or release capacity SHALL be qualified by a competent observed meter and admission-binding path **outside the metered grant/root lineage's ability to write, substitute or bypass**, with comparable original-intent, effect/provider call, principal/lineage, price/version and usage basis. Provider-side or protected gateway/effect-path records are possible sources, but their integrity, credential custody, admission binding, observation completeness, non-bypassability, replay and correction behavior must be independently qualified for the selected deployment. A requester's run-directory usage record, prompt/client metadata, self-asserted lineage header or unprotected gateway label is not a qualified measurement or attribution receipt. Such reports MAY conservatively increase or flag possible exposure but SHALL NOT decrease an existing worst-case reservation, establish a lower settled charge, release headroom, prove absence of additional chargeable effects or shift consumption to another lineage/scope. Without a comparable qualified final meter or safe competent release evidence, the original **worst-case encumbrance remains accounted** (and further unbounded/unknown exposure remains held); a missing meter cannot manufacture free capacity. A qualified settlement reconciles the corresponding reservation **once**, with attributable correction/late-billing history, rather than double charging. If particular child-lineage attribution is not established, the charge remains against all qualified enclosing limits and any affected root-specific claim cannot assert remaining headroom; a client-chosen attribution cannot bypass root advisor limits. Failed local launches, broken connections, provider timeouts, detach and receipt loss SHALL NOT turn outstanding external spend into zero or release capacity solely from process death. Research episode consumption remains attributable to its originating authorized objective (AEW-FR-42.h), without creating a second spending authority.

*Anchors:* AEW-FR-10.c/f; AEW-FR-42.h; ADC-08.f/i/j; HEB-03/06/08 (effect/credential custody; not an independent budget policy).

**R01-09 — Supported hard-limit enforcement and paid-call granularity.** The resource-control admission/effect profile SHALL implement ADC-08.f/i by declaring, **per resource class and selected provider**, the enforceable granularity (pre-admission, between effects, genuinely interruptible in-flight), trusted observation and response latency, provider-side bounds and residual unknown charges. Where one paid/provider request cannot be reliably stopped after dispatch, admission SHALL encumber a **competently established enforceable worst-case charge** for that operation against every applicable hard spending cap; a configured max-token value without an enforceable provider bound or comparable pricing is insufficient. If no bounded maximum is available, the class is `RESOURCE_UNSUPPORTED_FOR_HARD_LIMIT` and SHALL NOT be represented as hard-limit-supported or granted a protected positive admission that depends on that guarantee. Ongoing effects SHALL be stopped/withheld at actual enforceable boundaries without falsely claiming remote cancellation. HEB provides adopted protected effect/custody mediation; any additional resource-enforcement mechanism must be separately selected and qualified, not assumed from HEB alone.

*Anchors:* AEW-FR-10.f; ADC-08.f/i/j; HEB-03/06/08 (effect/custody, not independent spend-policy authority).

**R01-10 — Stale reservation, release and custody.** On crash, handover, lost response, detached generation, lease expiry or rate/price uncertainty, reservation and unconfirmed external exposure SHALL retain the original parent policy and operation identities until the competent owner proves release, settlement or an expressly bounded expiry that safely accounts for residual work and charges. An agent report, stopped heartbeat, old-generation release or duplicated receipt cannot erase another reservation or parent encumbrance. Custodian drain and late provider bills reconcile to the original scopes; release is not inferred from local process termination.

*Anchors:* AEW-FR-32; HEB-06/07/08; CNI-05.e.

**R01-11 — Fair admission under priority policy.** Admission scheduling SHALL respect operator-approved priorities, protections for mandatory independent assurance and reserved high-capability capacity, starvation bounds/exception visibility and permitted eligible work. Routine consultations cannot indefinitely displace required verification; no arbitrary first-come rule silently overrides policy.

*Anchors:* AEW-FR-26.b/c; AEW-FR-10.d; ADC-08.

**R01-12 — Nonblocking independent work under contention.** When resource or dependency condition blocks one action, R-01 SHALL preserve and expose existing CNI-03/05 authorization of independently eligible work and source-qualified scoped waiting; it SHALL NOT impose a universal stop or demand synthetic progress to retain a queue position. A missing impact relationship is not affirmative independence. This is a composed consequence of adopted CNI duties, **not** a new mandate giving R-01 authority to alter CNI state.

*Anchors:* AEW-FR-27.a/b; CNI-03/05.

### Progress qualification and proportionate intervention

**R01-13 — Observed versus inferred status.** Status SHALL keep HEB-observed tool/process/run phases, progress evidence qualified by WIS/AEV/CNI, agent-reported narratives, model-inferred health/prognosis and source-unavailable states separately typed. Neither apparent activity nor heartbeat alone proves productive engineering progress, and silence never proves a remote effect stopped.

*Anchors:* AEW-FR-24; AEW-FR-29.c/d/e; CNI-08.e.

**R01-14 — Bounded telemetry provenance.** A health observation SHALL identify run/custody and tool/event identity, source producer, sequence, local-versus-remote observation boundary, observation interval, policy/threshold revision, coverage gaps and effective recipient. Missing or dropped telemetry degrades assessment rather than asserting healthy, idle or finished.

*Anchors:* AEW-FR-24.a; AEW-FR-29.c/d; HEB-08.

**R01-15 — Bounded stall suspicion and duration provenance.** Stall suspicion SHALL account for policy/profile-qualified normal tool-duration ranges, observable tool phases, long checks, deliberative work, permission waits, dropped telemetry and harness connectivity. Agent-reported estimates remain attributed and bounded by the governing profile maximum; an agent cannot extend a timeout indefinitely by self-declaring an unbounded expected duration. A heuristic threshold is only `POSSIBLE_STALL` with confidence and telemetry limits until a competent owner qualifies more. Silence alone neither proves remote stop nor authorizes termination.

*Anchors:* AEW-FR-24.a/e; AEW-FR-25.b; HEB-06/08.

**R01-16 — Repeat-operation usefulness.** Suspected unproductive loops SHALL be evaluated against comparable attempts, material input/configuration changes, new diagnostic evidence and meaningful outcomes, not repeated command text alone. Tests that intentionally repeat (fuzzing, randomized validation, polling legitimately awaiting external effects) must remain eligible with declared comparability bounds.

*Anchors:* AEW-FR-24.b/e; AEW-FR-41/42.

**R01-17 — Engineering nonconvergence distinction.** Nonconvergence SHALL be reported as attributable diagnostic evidence about accepted objective, revisions, repeated unsuccessful approaches, contradictions or unresolved decisions; it MUST NOT be equated to no tool activity, elapsed time or engineering verification FAIL. Lead/competent owner decides redirection and governing failure classification.

*Anchors:* AEW-FR-24.c/d; ADC-03/07; AEV-09.

**R01-18 — Progress-impact propagation.** A credible material plan-invalidating discovery SHALL reach CNI/ADC via qualified scope/basis identity and source qualification, including impacted consumers and unknowns. A health heuristic cannot itself revise accepted objectives, clear holds or announce a source contradiction as governing truth.

*Anchors:* AEW-FR-24.d; CNI-04/05; WIS-05/06.

**R01-19 — Least-disruptive intervention record.** For nonemergency degradation the response SHALL begin with observations and proportionate non-destructive options (diagnostic/query, advice, waiting, safe yield, qualified relaunch) before any context-destroying interruption. The action record SHALL identify competent actor/authority, exact subject, observed versus inferred basis, non-destructive steps **actually attempted or why inapplicable**, proposed benefit, lost-context/unknown-effect risk and expected outcome. Qualified safety-critical protection or a separately authorized emergency can act promptly under its own adopted rules; it is not dependent on an artificial intervention ladder.

*Anchors:* AEW-FR-25.a/b/d; ADC-08; HEB-06/08.

**R01-20 — No destructive response from heuristics.** Destructive cancellation, termination, privilege change, scope reassignment or skipped assurance SHALL NOT have **solely** a stall/nonconvergence/health heuristic as its recorded competent basis, **regardless of whether the actor is the Lead, another agent, or a service**. HEB-06.e permits authorized cancellation, not classification of a heuristic as sufficient evidence. The independently applicable ADC/HEB decision, negative evidence, current authorization and loss/recovery policy must support the specific effect. Genuine safety-critical protections remain available under adopted authority.

*Anchors:* AEW-FR-25.b/d; ADC-08; HEB-07.

### Advice, wait/yield and resumption

**R01-21 — Advice request, authorization and non-effecting profile.** Any authorized role may **request** bounded, concise advice scoped to exact objective/revision, question/evidence and effective recipient disclosure. Record `REQUESTED` and resource `QUEUED/RESERVED` separately from **ADC/coordination-authorized advisor assignment/grant**, HEB-admitted invocation and received opinion. A worker request or capacity receipt never delegates agent execution, enlarges document/secret access or creates effectful tools. Advisor invocation SHALL use a profile that is non-delegating and non-effecting beyond independently authorized bounded, read-only/diagnostic observations; inference-based testing may not become unauthorized agentic work (HEB-03.c/n, ADC-04). It cannot modify governed code, scope or assurance. A non-effecting permitted consultation may be automatically authorized by a qualified coordination mechanism acting within existing ADC-approved delegation; no mandatory per-call human/Lead approval is introduced.

*Anchors:* AEW-FR-26.a/c/d/e; ADC-04.a–d/m; HEB-03.c/n; WIS-07; K01-03.

**R01-22 — Advisor resource admission versus helper launch.** Ordinary advisor **capacity** requests SHALL be evaluated against approved policy/aggregate budgets, lineage-specific quotas and priority reserves without case-by-case Lead mediation; available capacity permits queuing/reservation, **not** an advisor launch or recipient read. Before protected invocation, independently qualified ADC/coordination authorization SHALL bind advisor identity/root lineage, generation, allowed subject and diagnostic/read profile, recipient/source disclosure, advisor-seat lease, aggregate budget and permitted recursion/attempt count; HEB effect admission independently verifies these facts. Substitution serving mandatory assurance SHALL meet ADC-08.l eligibility/independence, not merely model compatibility.

*Anchors:* AEW-FR-26.b/c; ADC-04.a/b/c; ADC-08.l; HEB-03.c/n.

**R01-23 — Root-lineage fan-out and cost bounds.** Advisor consultation limits SHALL apply to the **requesting root lineage** across children, concurrent helpers, restarts, models, generations and nested/duplicate questions: cap total simultaneous consultations, aggregate reserved and unsettled cost, rate, cumulative attempts and recursion depth under each applicable parent budget. Duplicate materially equivalent open questions in a lineage SHALL be consolidated or explicitly counted rather than admitted as fresh free capacity. A single-request depth bound does not qualify a broad fan-out. UNKNOWN/UNPRICED usage consumes a policy-qualified conservative encumbrance; a missing bound holds affected paid admission. Retries and advisor-in-advisor calls do not grant additional coordination authority.

*Anchors:* AEW-FR-26.e; AEW-FR-10.a/f; ADC-08.f; HEB-03.c/n.

**R01-24 — Advisor information is not certified evidence.** Advice SHALL be attributed as opinion/hypothesis with sources and limits; it may inform Lead judgment but cannot become independently qualified verification, accepted work scope, canonical Knowledge Lesson or protected command without the respective owner’s assessment and decision. An advisor from interested lineage is not an independent assurance assessor.

*Anchors:* AEW-FR-26.d; ADC-04/07; AEV-03; K01-43.

**R01-25 — Wait/yield semantics.** A blocked invocation MAY relinquish unnecessary compute/advisor capacity under a competent HEB execution/custody transition while CNI retains the blocked work identity, outstanding dependency and continuation intent. Yielding capacity does not erase grants or imply they remain current indefinitely; in-flight effect and context loss are represented explicitly.

*Anchors:* AEW-FR-27.a/b/d; HEB-06/07/08; CNI-05.

**R01-26 — Wakeups, reconciliation and overdue attention.** Qualified blocker resolution SHALL become discoverable as bounded continuation/reassignment eligibility without requiring idle worker LLM polling. A **qualified deterministic non-model reconciliation owner** SHALL compare waiting items with current CNI/block-owner dependency membership on a **selected-profile declared, verifiably supported maximum interval** and upon attach/resume; a lost notice cannot indefinitely strand work without observable diagnosis. If that bound elapses after a qualified resolved blocker without delivery/reconciliation, expose `WAKE_OVERDUE` with exact subject, source/basis, last comparable check and uncertainty to eligible Lead/operator attention. Delayed, duplicated and reordered wakes recheck current blockers; a stale wake cannot clear a newer one. If no qualified scheduling/reconciliation facility can meet the declared bound, report `NOT_ESTABLISHED` for that wake service rather than asserting supported liveness; preserve independent work.

*Anchors:* AEW-FR-27.c; CNI-03.f/05.e; HEB-07/08.

**R01-27 — Safe resume basis.** Resume SHALL reconstruct from durable WIS/CNI/HEB state: exact objective/revision/grant status, material artifacts/evidence, outstanding holds, unresolved external effects, changed dependencies and model/harness capability limitations. It SHALL NOT claim to preserve inaccessible transient reasoning or automatically renew a stale generation or grant.

*Anchors:* AEW-FR-23.a–e; AEW-FR-27.d; HEB-07/08; P01-01/30.

**R01-28 — Cross-boundary resumption preflight.** Before resuming consequential work, effective ADC/HEB authority, work revision, accepted interface/dependency set, resource admission and applicable AEV/CNI holds SHALL be requalified against current competent owners. Valid unaffected work can continue without full replan; stale/unknown material prerequisites hold only affected actions.

*Anchors:* AEW-FR-23.c/d; CNI-03.g/05; WIS-07; ADC-08.

### Recovery, independent authority and operator visibility

**R01-29 — Recovery classification ownership.** A crash, refusal, local tool error, incomplete check, design defect and inconclusive evidence SHALL remain distinct. HEB owns observable process/effect outcomes; AEV owns check evidence; Lead or eligible adjudicator owns judgment-bearing failure classification according to ADC. A mechanically detected failure must not silently become permission to repair scope or override an assurance HOLD.

*Anchors:* AEW-FR-25; AEW-FR-32; ADC-03/07; AEV-09; HEB-08.

**R01-30 — Scoped automatic mechanical recovery.** Automatic repetition SHALL require an **authorized recovery class declared idempotent or non-effecting by competent governing policy/profile**, exact original operation intent, attempt identity, qualified unchanged accepted input and a current resource/authority basis. It additionally requires qualified absence or resolution of **applicable** adverse evidence and material unconfirmed effects for this exact repeat: work/package, accepted input, dependencies, affected shared resources, assurance obligations and changed-scope relationships, as supplied by competent WIS/CNI/AEV/HEB owners. An unresolved HOLD on proven-independent work does not block the repeat or disappear; missing impact closure is not proof of independence. If a material effect remains unknown, use original-intent reconciliation or request competent disposition rather than replay.

*Anchors:* AEW-FR-32; ADC-08.i; HEB-06/08; CNI-05.c/e; AEV-09.

**R01-31 — Attempt limits survive identity changes.** Recovery attempt, total cost, elapsed time and advisor spend ceilings SHALL be keyed to the **stable work identity and owner-qualified original operation intent** plus applicable ancestor policy scopes, not solely requester-supplied idempotency key, lineage tag, assignment, attempt, run or Lead generation identifiers. Reissued keys, reworded requests and changed client tags for materially the same owner-observed work/operation subject SHALL NOT reset a bound; independent per-work and ancestor ceilings apply even when intent equivalence is unresolved. Preserve all prior attempts, bills/encumbrances, adverse findings and exact work basis across detach, handover, model/provider restart and custodian drain. Only an attributable competent authorization may grant extra headroom. Exhaustion leads to a held/waiting decision, not a new identity to reset a cap.

*Anchors:* AEW-FR-10.f; AEW-FR-24.b; AEW-FR-32.

**R01-32 — Unknown effect, protected retries and operator commands.** Uncertain remote/non-idempotent effects SHALL remain `UNKNOWN_EFFECT` under the original operation intent and reconciled through the HEB/ADC protected effect and owner-specific result path, not retried as a second effect on timeout. Protected operator command semantics are governed by adopted AOI/ADC/HEB; the separately planned O-01 command profile is **not** an already adopted `O-01` clause or bypass. Custodian-held verifier results and old-generation communications cannot confer new authority.

*Anchors:* AEW-FR-32; HEB-06/08; ADC-08; AOI-03–05; planned O-01 (NOT an adopted clause).

**R01-33 — Evidence and assurance preservation.** Recovery, retry, advisor intervention and model change SHALL preserve applicable AEV findings/HOLDs, WIS versions, accepted material closure and evidence lineage; no retry success supersedes a separate adverse determination without competent explicit resolution. Valid unaffected evidence should be retained.

*Anchors:* AEW-FR-14; AEV-06/09/10; CNI-05.e.

**R01-34 — Supervision under detach and custodian drain.** Attachment/Lead generation end, custodian drain, verifier-held result, run custody and reservation status SHALL be distinguished. A Lead or autonomous supervisor cannot renew revoked authority by waking/yielding/retrying; custodian continuation is limited to previously admitted protected scope and held results retain their own publication limitations.

*Anchors:* HEB-07; ADC-08; CNI-06.

**R01-35 — Decision requests and escalation.** Supervision SHALL route decisions only to the competent Lead/operator or independent assurance authority under ADC, with basis, affected subjects, options, reasons, risk of delay and source qualification. Routine nonurgent similar requests are consolidated; urgent hazards and authority blockers remain promptly discoverable on an actually supported response channel. Silence is not consent.

*Anchors:* AEW-FR-28.a–d; CNI-08.b/c; AOI.

**R01-36 — Disclosure-safe supervision and accounting.** Operator/agent/website resource and progress projections SHALL attribute qualified resource-control admission/accounting, HEB run observations, CNI waiting, ADC delegated policy, WIS work and AEV assurance separately. Effective-recipient noninterference SHALL apply to private review **resource usage, tokens, duration, cost, reserved capacity, hidden pool existence**, counts, ranking and ordering as well as result content. Stale, withheld, unsupported or unqualified sources cannot be flattened into a positive status, and a UI never issues a grant.

*Anchors:* AEW-FR-29; AOI-03–05; D01; CNI-08.

### Composition and conformance

**R01-37 — Deliberate non-connections and record semantics.** R-01 specifies minimum shared resource **record identities and accounting semantics** that a protected qualified producer must implement for supported classes; this is not a new operator budget policy, additional grant authority or mandate for one database/service. No universal board, standup, separate health authority, LLM progress referee, new billing authority or global state machine is required. Optional cost ledger, context, steering and evaluations may project these attributable facts without superseding competent producers or opening a new resource truth writer.

*Anchors:* AEW-FR-09/10/24; AEW-FR-42.h; ADC-08.f; CNI-01; P01-02; K01-01.

**R01-38 — Crawl/walk/run modes are nonauthoritative.** An optional operator-approved steering mode may determine whether otherwise eligible, explicitly auto-runnable actions wait for confirmation; it SHALL NOT alter risk class, grant/effect scope, assurance eligibility, holds, independent adjudication, resource hard limits or judgment-bearing decisions. A mode change affects future admissions only, with attributable version/fencing.

*Anchors:* AEW-FR-10; ADC-03/08; CNI-03/05.

**R01-39 — Policy change and competing admissions.** Change in operator policy, price, entitlement, parent-scope roster, shared capacity, affected grant or steering rule between observation and effect SHALL force owner-qualified comparison and new protected admission as relevant. All independent child pool allocations SHALL contend on common parent hard limits; no local reservation token can be double-spent or renewed by a stale generation. Actual in-flight effects under new policy are treated according to ADC-08.f and supported enforcement granularity; lost events do not substitute for effect-time checks.

*Anchors:* AEW-FR-10.a/f; ADC-08; HEB-03; CNI-03.g.

**R01-40 — Provider and external quota outage.** Unknown provider availability, prices, chargeability, comparable billing, rate state or shared encumbrance SHALL differ from confirmed exhaustion, permission denial and free capacity. Paid recovery retains exact original intent, cost uncertainty and accountable parent scopes; only separately authorized provider substitution is permitted, and any substitution serving mandatory assurance SHALL independently satisfy ADC-08.l (qualification and independence). Missing bounded maximum prevents a positive supported-hard-limit claim for that affected paid class without stopping proven independent non-billable work.

*Anchors:* AEW-FR-10.c/e/f; ADC-08.f/l; AEW-FR-23.e; HEB-08.

**R01-41 — Conformance and supervision benefit.** Independent producer/consumer/VM/advisor/operator tests SHALL cover shared-parent admission across generations/pools, **meter and attribution forgery, protected settlement and gateway/credential bypass, owner-derived intent equivalence across client-key changes**, unsettled provider charges, worst-case paid requests, effects during dispatch, unqualified-writer refusal, healthy-idle versus destructive heuristic, root-lineage advisor fan-out and unauthorized spawn, scoped HOLD/recovery, missed wake and maximum reconciliation interval, late custodian bills/results, resource-accounting disclosure and safe unsupported modes. Report subject, exact policy/source witness, profile, supported limits, false-positive rates and residual unknowns. Tabletop JSON alone is not live conformance.

*Anchors:* AEW-FR-24/25/26/27/29; ADC/HEB/CNI/AOI.

**R01-42 — Supported release and qualified limits.** Every selected release profile SHALL explicitly enumerate supported protected resource writers/authorizing principals, **qualified consumption/settlement meter and writer/effect source, attribution binding and bypass coverage, operation-intent derivation**, policy-scope/usage owners, hard-limit resource classes and enforceable granularity, charged worst-case method, non-model reconciliation bounds, advisor authorization, recovery keys and protected operator response routes. Unsupported or unavailable classes SHALL report refusal/`NOT_ESTABLISHED`, not optimistic admission. Any additional HEB-specific spending effect interface shall be separately amended/adopted where required; operative safety controls remain until qualified replacement.

*Anchors:* AEW-FR-10/24/27/39; HEB-10; CNI-08.

**R01-43 — Unqualified-host and resource-class degradation.** Where the actual execution environment lacks an independently qualified agent-inaccessible **resource-record writer, protected admission path or necessary effect mediation** for a resource class, R-01 SHALL NOT issue or display positive `RESERVED`, protected admission, hard-limit-enforced or guaranteed remaining-capacity claims for that class. An unprotected local mutex/CAS or same-UID lease file is not a substitute. Any scheduling hints may be treated only as explicitly labelled **cooperative/unqualified**, never as AEW-protected execution authorization; operator-attended external/manual development remains governed by HEB-02.k and does not inherit AEW grants. Report the class's hard-control result and applicable FR-10.a/f conformance as `NOT_ESTABLISHED`/unsupported. Qualified canonical read-only/status and truly independent permitted work remain available, subject to their own entitlements. Only separately evidenced host/resource-profile qualification can leave this degraded state.

*Anchors:* ADC-08.b/e/f/i/j; HEB-01.e/h, HEB-02.k; AEW-FR-10.a/f; AOI-03/05.

## 4. Admission and failure-ordering contract

At a consequential allocation, dispatch, recovery or restart, a conforming boundary rechecks: (1) actual grant/effective generation and allowed effect; (2) exact work/assignment and dependency/preconditions; (3) operator/ADC-authorized resource policy, **all parent scope limits**, price and billable call maximum; (4) protected resource-control witness, **nonoverlapping qualified aggregate encumbrance**, independently qualified meter/settlement and attribution evidence whenever headroom is released, availability, reservation version and concurrency fence; (5) **only applicable** adverse evidence, holds, unresolved original effects and protected operator-origin prerequisites; (6) chosen class is qualified as enforceable on the actual host/provider, otherwise deny the protected effect. The **protected competent owner** commits only its own atomic decision; R-01 cannot claim globally atomic transactions across HEB, provider, WIS and CNI. If positive claims require a current external fact without a sufficient witness, they remain `NOT_ESTABLISHED`/held rather than pretending cross-owner atomicity.

**Refusal categories (proposed semantic, not frozen wire):** `NOT_AUTHORIZED`, `STALE_GRANT`, `STALE_BASIS`, `CAPACITY_EXHAUSTED`, `RATE_LIMITED`, `BUDGET_EXHAUSTED`, `COMPETING_RESERVATION`, `UNKNOWN_PROVIDER_USAGE`, `OBSERVATION_NOT_ESTABLISHED`, `ADVISOR_SCOPE_DENIED`, `HEURISTIC_ONLY`, `UNKNOWN_REMOTE_EFFECT`, `RECOVERY_ATTEMPT_LIMIT`, `HOLD_UNRESOLVED`, `RESPONDER_UNAVAILABLE`, `RESOURCE_UNSUPPORTED_FOR_HARD_LIMIT`, `RESOURCE_WRITER_NOT_QUALIFIED`, `WAKE_OVERDUE` (attention, not authorization). A denial or uncertain response must preserve the original operation identity to enable safe reconciliation, not silently rerun. Error precedence needs exact selected-profile fixtures before live implementation.

**Context integrity:** Any packet containing resource/hold/permission restrictions must retain source-owner identities, full recipient-safe applicable conditions, source coverage and currentness. An agent summarizer may add narrative but cannot omit a governing restriction; later consequential admissions independently recheck mutable owner facts.

## 5. Non-authoritative predecessor reconciliation

Historical research supplies useful candidates but is not, by itself, requirement authority.

- **R1 coordination board:** reuse attributable updates/projection and targeted delivery where justified; no mandatory shared board or indiscriminate peer-polling requirement.
- **R2 scratchpads:** preserve contextual provenance and bounded lifetime; drafts are untrusted working data, not accepted facts.
- **R3 health extension:** use qualified event/heartbeat telemetry with calibrated thresholds; avoid hardcoded 300/600-second production guarantee. Do not let tool silence become destructive permission.
- **R4 Crawl/Walk/Run:** optional explicit steering of already permitted automatic actions, not a new authority level or skip-review switch.
- **R5 bounded recovery:** retain the distinction between mechanical relaunch, qualified redispatch and judgment-bearing replanning. Legacy retry counts, schema paths and exact status strings remain profile candidates, not universal normative defaults.
- **F25 usage ledger v0.2:** significant historical designer-approved direction for nonoverlapping billable buckets, attributed pricing snapshots, unpriced/unknown handling, session/generation binding; no silent new normative record authority or claim that it is implemented.
- **Guided resource recovery v5:** consumer UX and intervention vocabulary to challenge, not permission to invent control APIs or recover lost context.

Any still-effective earlier safety restrictions remain in force until their replacement is independently qualified and explicitly dispositioned.

## 6. Decisions deferred for selected-profile work

- **R-DEC-01:** Which resource/encumbrance classes have an actual **protected qualified writer and non-bypassable independent measurement/attribution boundary**, accountable policy scopes and enforceable effect admission on the native shared-login Rocky 8 VM? R01-43 governs unqualified states now; selection does not create a new policy owner or assume supervisor-only identity.
- **R-DEC-02:** Which operator/ADC policy scope hierarchy, monetary/rate/concurrency caps, provider-side enforceable maxima, qualified provider/gateway usage and credential-attribution witnesses, reservation granularity and unknown-cost conservatism are selected, with parent-scope conservation across generation changes? Material policy changes require operator authority.
- **R-DEC-03:** Which initial supervision/health and wait/yield/recovery routes are due, and what qualified duration sources, deterministic wake reconciliation schedule and attention channels can meet an explicitly stated bound without consuming idle LLM tokens?
- **R-DEC-04:** If operator chooses optional autonomy steering, specify eligible primitives, side effects, confirming actor and nonbypass proof. No mode changes current safeguards.
- **R-DEC-05:** Freeze exact resource-control writer/reader identities, **meter origin/receipt integrity, per-effect admission and lineage binding, completeness/non-bypassability, original-intent minting/equivalence**, ancestor scope and lease/enforcement witnesses, advisor authorization stages, wait reconciliation, error/disclosure ordering, receipt retention and executable independent fixtures for selected profiles only. If HEB protected execution/effect interfaces require new resource-control obligations, propose an explicit compatible amendment; preserve D-01 GET-only scope until a separately adopted profile.

**Safety/release:** **R01-43 applies even before R-DEC-01 is selected**; current shared-login host has not qualified any positive resource-control writer. G1–G4 and D-01 W1–W5 remain OPEN. A semantic contract may be reviewed/adopted without a qualified resource allocator or protected execution. Do not claim such a runtime exists based on this package.
