# Designer decisions of 2026-10-11: architecture integration (AIR): the attention spine, the owner registry, base-drift validation, F9 kinds, the operator settings surface

**Status:** Decision record, governing for what it decides. **Approved** by the designer on 2026-10-11, relayed by the
operator, in three rounds: the morning decisions Q1 to Q6 on the lead developer's first brief of the day; the
designer's response to the second brief (the architecture audit and the observability inventory); and the designer's
acceptance, with corrections, of the lead developer's return on that response. Where the acceptance differs from the
response, the acceptance governs. §1 records the morning decisions verbatim. §3 records the response and the
acceptance **in substance**, not verbatim: the designer's text names models from the current roster, which this
record writes generically, and it refers to private evidence that stays outside this public repository. §2 and §4 give
the context; §5 says where each decision is filed. No frozen architectural decision is reopened.

The two inputs of the second brief are not in the repository and are cited by title and date only: **the fresh-context
architecture audit** of `main` at `1dd89d5` (2026-10-11; findings AX-01 to AX-16, automated and report-only), and **the
Observability and Feedback inventory** of what AEW records today (2026-10-11, at the same commit; gaps 1 to 13). Both
cross-check each other.

## 1. The morning decisions (Q1 to Q6), recorded as given

The designer's text, verbatim:

```text
Q1  APPROVE.
    Cross-cutting integration notes become a standing design technique.
    They begin with existing-owner maps and cannot invent duplicate owners.

Q2  APPROVE.
    Observability & Feedback is the first candidate.
    Existing owner split is sound.
    Detectors remain advisory.
    Verification of an accepted improvement on the same metric is REQUIRED.

Q3  KEEP UNDER EXISTING OWNERS.
    Fix-brief / sweep-floor / scope-ceiling belongs to review protocol + F14,
    fed by T5/F30 and F9 scope requests.
    Do not create another standalone subsystem for it.

Q4  APPROVE WITH STRUCTURE
    Record a reviewed parallelism decision, not a magic coupling score.
    SERIAL_REQUIRED / PARALLEL_ALLOWED / CONDITIONAL.
    Existing dependency/overlap data supplies evidence.

Q5  PRIORITIZE F18.6 + F28 AS ONE HARDENING MILESTONE
    Remove credential exposure first.
    Then force all provider egress through AEW-controlled routing.
    Proxy ledger authoritative; harness usage is cross-check.
    Ordinary production qualification requires mediation completeness.

Q6a ACTIVATION AMENDMENTS: DO NOW
    Separate WC/F14 planning amendment and WC§8/E19-B interface amendment.
    Review together, activate v0.5 only after both exist.

Q6b MIC-16 / D4: DROP THE UNBUILDABLE VERIFICATION HALF
    Do not invent verification semantics to save a dead key.
    Consequential non-gating verification facts route through existing
    observation/finding + requires_disposition machinery.
```

What they mean for the record:

- **Q1 and Q2:** a cross-cutting integration note is now a standing design technique. Observability and Feedback is the
  first (register F42): it starts from a map of the existing owners, its detectors are advisory, and an accepted
  improvement is verified on the same metric it was meant to move.
- **Q3:** the fix-brief template (the invariant broken, the sweep floor, the scope ceiling) stays with the review
  protocol and F14, fed by the project maps (T5) and F30 and by F9's scope requests (§3.8, §3.11).
- **Q4** is folded into the parent plan's `interactions[]` (§3.7): the parallelism verdict is recorded there, as one of
  three values, with the engine's dependency and overlap data as its evidence.
- **Q5** makes F18.6 and F28 one hardening milestone. The owner of provider mediation inside it is F18.8 with F28
  (§3.5).
- **Q6a:** the two amendments the cross-feature integration design v0.5 needs before activation (F41.1, the WC/F14
  planning amendment; F41.5, the WC §8 / E19-B interface amendment) are to be written now, reviewed together, and v0.5
  is activated only after both exist. This record does not write them; they are a later pull request.
- **Q6b** drops the verification half of `gates.requires_disposition` that the designer's D4 of 2026-10-10 had kept
  (MIC-07, MIC-08) and closes the definition it was waiting for (MIC-16). A consequential verification fact that does
  not gate goes through the existing observation and finding records and the review half of `requires_disposition`.

## 2. The second brief: the architecture audit and the observability inventory

The audit studied how the owners built at `1dd89d5` compose and ranked sixteen missing joins (AX-01 to AX-16, P1 to
P4). The inventory listed every durable record bearing on observability and ranked thirteen gaps. They agree on several
points: provider usage through the gateway (AX-09) is the inventory's usage gap and the Q5 milestone; the missing event
vocabulary (AX-04) is what the process-event gaps need; the re-review delta (AX-14) is Q3's scope ceiling; run health
(AX-16) is the inventory's health gap.

The lead developer checked AX-01 against `main` and asked the designer eight questions: whether AX-01's correction is a
precondition of v0.5 activation; which input Observability and Feedback starts from, given that AEW records nothing of
its own development; whether AX-05, AX-04 and AX-03 are F41 rows or mainline work; whether Lead-to-worker instructions
belong in reviewer and verifier packs (AX-02); whether F19's slice S18 is the gateway's metering mode or temporary
(AX-09); what counts as a row of an owner registry for control facts, and whether a parent plan lists its
`interactions[]`; where the inventory's gaps that the audit does not cover belong; and whether the remaining audit
findings are registered now. The brief also listed what neither document covered: work in flight since `1dd89d5`,
failure and recovery across owners, security across the joins, platform asymmetry, the audit's own UNKNOWN list, joins
between evaluation and the product, and drift between the design ledger and the code.

## 3. The designer's response and its acceptance, in substance

The broad direction: the audit found individually sound owners whose outputs are not always connected to the consumers
that need them. Its findings are integration debt under existing owners, not invitations to build parallel
subsystems. The acceptance confirms the response with the lead developer's code-level corrections, which improve the
implementation shape without reopening any frozen decision.

### 3.1 Base drift reaches integration validation (AX-01)

AX-01 is a precondition of F41 (v0.5) activation. v0.5 §9 is not weakened to say that the risk of an undeclared
cross-Ticket relationship is uncovered: `AEW-INV-INTEGRATE-001` says integration validation catches cross-Ticket
conflict and overlap, but the validation obligation and the integration verifier's pack do not receive the facts about
the integrations between a Ticket's base and the integration base.

The join (register F45), on the existing validation and integration owners:

- at prepare and at rebuild, the engine computes the base drift from Git and records its changed paths and their
  overlap with the Ticket's changed paths;
- the validation obligation consumes the recorded overlap through a governed, legality-affecting policy key,
  `gates.post_integration.base_drift_overlap`, and the policy choice is explicit rather than an assumed absence of
  checking;
- the integration verifier's pack gains an engine-derived section, the work integrated since this Ticket's base.

The obligation's existing binding stays the invalidation mechanism; no other is created. F45 is its own slice, after
M4-E's E6a and before F41 activation; E6b is not widened.

**Migration and activation.** An absent key stays absent, so an existing project's behaviour and bindings are
byte-identical on upgrade. But a project activated under F41 may not leave the key absent or disabled while v0.5 §9
claims that integration validation covers undeclared relationships: old, non-activated projects may keep its absence;
`aew init` writes the governing value for new projects; F41's activation gate verifies that the protection is on; and
migrating a project to F41 needs the explicit adoption of that policy value.

**Intervening Ticket identity.** Reliable Ticket ids are not a prerequisite. Path and diff overlap is authoritative
enough to trigger the obligation. Ticket ids recovered from integration subjects and history may be shown, best effort,
until the publication trailers of AX-12 (E59) make that join robust; failing to recover an id never suppresses overlap
detection.

### 3.2 The process-event model and the repository-process adapter

Observability starts from a **repository-process adapter** for AEW's own development (the brief's option (b)): pull
request, CI, merge, review and blocking events are ingested into the same canonical process-event model that AEW-native
runs will use. Events worth normalizing include a pull request opened, ready or merged; a review round opened or
settled; a fix round; CI queued, started or settled; a merge-main round; a conflict and its resolution; a lane blocked
or unblocked; an integration wait. What matters is common ids and one vocabulary, not telemetry volume. There is no
separate repository-host analytics subsystem, and when AEW's own development runs under AEW it becomes one more
producer of the same model, with no migration to another schema.

The acceptance's correction: the canonical model is a **read-time schema**, not an extension of the authoritative
outbox, whose events only the engine declares. It has two producers: native events derived from the transition log (as
F25 derives its projections), and adapter events in their own append-only store outside control state. AEW's own
repository has no project yet, so the common ids need a project id and a mapping from pull request to work unit
(register F42.1, F42.2).

### 3.3 The attention spine: AX-05, then AX-04, then AX-03

These are mainline integration work. They are not F41 rows merely because F41 depends on them; F41 depends on them. In
order (register F43, slices S1 to S3):

1. **S1 (AX-05):** the next-action derivations converge on the canonical `ActionProjection`. The acceptance makes it
   absorb every duplicate the lead developer's consolidation pass found: `resume`'s next actions, `ActionProjection`
   itself, the dashboard's attention and health derivation, the operator notifier's condition derivation, the steering
   loop's consumption of decisions, and the wake interpretation of invocation status. The notifier stays the operator's
   delivery channel but keeps no semantic implementation of "what changed". Channels may differ; the derivation does
   not:

   ```text
   authoritative/control facts
           ↓
   ActionProjection
           ↓
   typed outbox consequences
           ↓
   wait / notifier / loop / dashboard
   ```

2. **S2 (AX-04):** every consequential control fact has a typed outbox kind.
3. **S3 (AX-03):** Lead-actionable facts reach the existing `wait --any` control lane, which needs a **run-less** form:
   today the lane wakes only when an invocation leaves `active`, so a Lead with no live run has nothing to wait on. It is
   **one decision-keyed Lead-attention lane**: v0.5 §11.1's "D5/F9 coordination lane" and the F9 coordination lane of
   the designer's D5 of 2026-10-10 (MIC-09) are this lane, not separate mechanisms.

The larger rule: consequential control state is not introduced without declaring how the canonical action projection,
the outbox, the Lead's attention surface and the relevant packs consume it (enforced by §3.6).

### 3.4 Admitted Lead instructions in review and verification context (AX-02)

Lead-to-worker instructions belong in review and verification context. Reviewer independence excludes the implementer's
private reasoning; it does not hide authoritative or admitted Lead steering that changed what the worker was told to
do. Reviewer and verifier packs receive the admitted Lead instructions that materially apply to the reviewed attempt,
with at least the message id, kind, admission time, the Ticket, revision and attempt binding, canonical sanitized
content and provenance. When visibility rules redact content, the pack shows that a redaction exists. A digest alone is
not equivalent to the text when the instruction materially changed the assignment.

The acceptance rules out the alternative of packs receiving instructions only with F9 messaging on: an admitted
instruction can change the assignment with messaging off, and after delivery only its hash remains today. So AEW keeps a
**bounded, engine-owned, immutable content record for admitted Lead sends**, one canonical content object that both
paths reference (with messaging off, `harness send` admits it and then delivers it; with messaging on, the F9 message
carries the same admitted content semantics in its durable thread), never two histories of one instruction. The
durable body limit is deliberately small, aligned with F9's message discipline of about 4,000 characters rather than
the current send ceiling; large material belongs in referenced artifacts (register F9.2).

### 3.5 Provider-usage convergence (AX-09, Q5)

F19's slice S18 is temporary unless it is factored into the common gateway. The long-term owners:

```text
F18.8 + F28 provider gateway        -> mediation completeness
common gateway accounting hook       -> the authoritative provider-usage event
F19                                  -> an evaluator consumer of that mechanism
F25                                  -> usage projection and cross-check
```

F19 must not become the permanent product owner of provider mediation because evaluation needed the mechanism first.
The acceptance names the gateway owner as F18.8 with F28 (F18.6, principal separation, stays in Q5's hardening
milestone but is not the gateway's owner). S18 is not built, so nothing moves: it is specified now as a client of the
common accounting hook (register F18.15).

### 3.6 The consequential-fact owner registry

A test-enforced registry of consequential control facts is approved as the most useful future-prevention mechanism of
the audit. A row represents a semantic control fact or evidence kind, not every JSON property. A row is required for
every durable fact that may influence dispatch, `ActionProjection`, a gate, progression or lifecycle, evidence
admissibility, publication, Lead or operator attention, or reviewer, verifier or model context. Each row records at
least:

```text
fact / key
owner
producer(s)
authority = authoritative | advisory
A3 field classification reference, where applicable
outbox consequences
Lead/operator projection carrying its decision
consuming packs
staleness / freshness rule
data / redaction class
schema version
```

A row points at A3's existing field classification and never restates it in a parallel vocabulary. The registry covers
the top-level control keys and a declared inventory of unit-level keys, so a consequential unit-level fact (a
disposition's follow-up, a finding, an integration record) cannot evade the test. CI and static checks fail on an
incomplete row; the intended failure is "a consequential control fact was added, but nobody declared how the rest of
AEW learns about it", the class of AX-04, AX-05 and AX-13 (register F44).

### 3.7 Parent-plan interactions and the parallelism verdict (Q4)

F14's permanent composition-prevention rule is represented in the parent plan, inside the same parent-plan contract
being amended for F41 (F41.1), never a second plan contract. A parent plan lists structured `interactions[]` between
sibling slices or work units wherever a material interaction exists:

```text
interactions:
  - between: [T-A, T-B]
    dependency_refs: [...]
    interface_refs: [...]
    shared_surfaces: [...]
    allocated_identifiers: [...]
    parallelism: PARALLEL_ALLOWED | SERIAL_REQUIRED | CONDITIONAL
    conditions: [...]
    rationale_refs: [...]
```

This is where Q4's reviewed parallelism verdict lives. `SERIAL_REQUIRED` is a governing scheduling constraint and
compiles to the existing blocking dependency semantics. `PARALLEL_ALLOWED` is permission only; it never forces
concurrency. `CONDITIONAL` permits concurrency only while its named conditions hold, and governs only when each
condition is a closed, engine-evaluable predicate (for example: an accepted interface digest is still current; a
specified overlap set is still empty; a named dependency state holds). Free-text conditions may explain a plan but never
govern scheduling. There is no model-generated coupling score: the engine supplies deterministic dependency, interface
and overlap evidence, and plan review judges the verdict. Parent-plan lint runs at plan acceptance, not only at a
descendant's dispatch.

**The composition invariant:** a Story or Epic is not plan-complete until every material cross-feature interaction its
plan introduces or changes is connected to an existing owner or explicitly dispositioned. It is enforced through F14's
parent-plan assurance, not on ordinary Tickets (register F14.1).

### 3.8 Observability gaps routed to their owners

Observability consumes these facts; it owns none of them.

- **Gap 3, a fix round is not linked to the review it answers:** a minimal `answers` link on the repair or re-dispatch
  record. Owner: the review-to-repair protocol (register E63).
- **Gap 4, findings have no class:** the canonical finding and fix-brief data can name the invariant or property
  broken, the finding class where one applies, the known site as an example, the sweep or candidate sites, and the
  scope floor and ceiling. Owner: the review protocol and F14, fed by T5 and F30. It comes before telemetry can count
  "rounds spent fixing one instance of the same class" (Q3).
- **Gap 5, F25's projections have no surface:** a real consumer surface. Owner: F25, with the Lead's and F20's
  presentation.
- **Gap 8, blocked and queue time:** identity-bearing process events. The acceptance's correction: blocked time comes
  from the dependency engine, queue-wait time from the queue. Observability aggregates them (register E64).
- **Gap 11, redaction and work-safe diagnostics:** an F37 diagnostics and security requirement from the beginning; no
  rich telemetry corpus is built first and sanitized later. It covers at least normal logs, check logs, evidence,
  coordination bodies, absolute paths, the supervisor's log, the per-run event log, and size and retention bounds.
- **Gap 12, typed worker messages:** F9 message kinds (§3.10, §3.11).
- **Gap 13, CI and check time:** process metrics, elapsed resource use, never F25's model-usage accounting stretched into
  a universal cost subsystem (register F42.1).

### 3.9 The remaining audit findings as integration debt

AX-06, AX-07, AX-08 and AX-12 to AX-15 are registered now as integration debt under their existing owners (register
E56 to E62), so they do not live only in the audit. Registration is not adoption of the auditor's proposed solution.
Each entry records the audit finding, its existing owners, the current evidence, its priority and its designer
disposition, **pending / local-owner review**. The audit's priority order stands unless a local owner's review finds a
contradiction. AX-14 already belongs to F41.10 and AX-13 to F9's worker-reply slice; their entries point at those owners.

The audit's other findings land on rows that already exist or are added by this record: AX-01 on F45; AX-02 on F9.2;
AX-03 to AX-05 on F43; AX-09 on F18.15; AX-10, the Lead's usage, on F25's Lead part; AX-11, the live step meter and the
supervisor's stop, on E54; AX-16, run health, on U1.

### 3.10 F9 extensibility: the tolerant read and structured data

The lead developer's assessment confirmed the intended architecture: F9's ids, ordering, chain, sealing, unseen state,
delivery and recovery are kind-blind. It found two small defects, fixed once in a prerequisite slice, F9-X0:

- **D1, future kind compatibility:** a newly written kind never makes a durable thread unreadable by an older engine.
  The read contract is versioned and tolerant: an older engine treats an unknown kind as semantically unsupported but
  still reads the thread, preserves ordering, hashes and ids, renders a generic unknown-kind representation, and refuses
  any action that needs semantics it does not understand. Writing stays strict against the local registered kind table.
- **D2, structured `data`:** an optional structured `data` object whose schema the registered kind selects, included in
  the message's derived content and idempotency identity.

**An extensibility acceptance criterion for F9:** after F9-X0, a new semantic message kind normally needs only a
kind-table entry, a data schema, sender and recipient legality, a routing and presentation rule, an optional budget,
tests and role-card awareness. It never needs broker, store, ordering or sealing changes (register F9.1).

### 3.11 The F9.1 message kinds

Approved kinds: `advice_request`, `advice`, `scope_request`, `scope_answer` and `confusion_report`. The existing
`question` kind stays; no second generic question is invented. `design_decision_required` and `REPLAN_REQUIRED` are
not messages: they stay F14 and lifecycle concepts.

- **`advice_request`:** the worker keeps the authority to proceed and has a candidate interpretation, but wants a
  bounded sanity check from a stronger model. Its data: `question`, `proposed_answer`, `uncertainty_reason`, an
  optional coarse `confidence` (`low` or `medium`, never a precise percentage) and `refs[]`. The answer, `advice`, is
  `AGREE`, `DISAGREE`, `UNCERTAIN` or `ESCALATE`.
- **Messages grant no authority.** An escalation is followed, where appropriate, by the Lead exercising an existing
  authoritative path (a recontextualization, a Ticket replan, a scope change).
- **Deterministic resolution first:** when existing maps, knowledge, evidence or tests can answer the worker, AEW serves
  that context; otherwise the worker sends `advice_request` when the judgment is still its own, and asks the Lead for a
  decision when it is the Lead's. AEW compiles bounded supporting context from authoritative sources (the relevant plan
  section, constraints, the diff and changed surface, tests, findings, evidence, map and knowledge references) rather
  than relying only on the worker's retelling.
- **The budget:** two advice requests per worker attempt by default, for initial qualification. Repetition is decided
  by explicit references and history, never by semantic similarity, and a repeated unresolved consultation becomes Lead
  attention rather than an indefinite advice loop.
- **The v1 advisor is the Lead**: a lower-bound worker consults a frontier-class Lead, with no separate advisor role.
  The `frontier_advisor` role is not repurposed for routine sanity checks; a separate advisor role, if ever useful, is a
  later routing and role-design question.
- **`scope_request`** asks the Lead whether work outside the admitted brief is `IN_SCOPE`, a `FOLLOW_UP` or a `REPLAN`
  (the answer, `scope_answer`). **`confusion_report`** is feedback ("this tool, context or workflow misled me") into
  Observability and Feedback's intake, not a request for judgment. All of them reuse F9's generic durable-message
  machinery.
- **Telemetry, advisory:** the request category, the worker's model profile, the response's disposition, whether it
  escalated, the eventual verification result, repeats, and the rework or replan outcome.

### 3.12 Reviewer independence for advice exchanges

The acceptance refines the response's first statement. Reviewer and verifier context can always see that a
consultation occurred, its message id and provenance, the bounded question, the evidence and references supplied, and
the advisor's disposition and response. By default it does not see the worker's `proposed_answer` or
`uncertainty_reason`: they are the implementer's reasoning and private working state, so hiding them preserves
reviewer independence. When the Lead wants advice to become part of the authoritative assignment, the Lead issues an
admitted instruction or decision through the normal path, and the reviewer sees that (§3.4). An investigation or debug
mode may reveal the worker-authored fields, with their provenance, when policy permits. There is no general
reviewer-independence exception because a conversation used `advice_request`. This refines the designer's
reviewer-independence ruling of 2026-10-09; it changes no Workflow Contract text.

### 3.13 The consolidation pass

The lead developer tested whether overlapping vocabularies and mechanisms should share one owner. The dispositions:

- **Liveness, LINK:** the mechanisms and their thresholds stay distinct. Externally projected liveness outcomes share
  one canonical reason vocabulary where their meanings coincide (`lost`, `stale`, `wedged`, `gone`), and the owner
  registry names the predicate and owner producing each reason.
- **Freshness and staleness, PARTIAL LINK:** the engine's and the maps' freshness states converge where they mean the
  same thing; gate states such as `MISSING`, `FAILED` and `WAIVED` keep their own type. The owner registry makes every
  freshness or staleness predicate explicit and owned.
- **Refusal and deadline reasons, LINK:** the hard deadline is one semantic fact, canonical in the error and reason
  vocabulary and projected into the spool, anomaly and loop surfaces, not three independent names.
- **Telemetry logs, LINK through correlation ids:** the stores are not consolidated (authority logs, untrusted run
  events, tool-call logs, the delivery spool, profiling and stderr differ in trust and retention). F37 owns the safe
  correlation and redaction boundary.
- **Health:** F20's dashboard projection is renamed project health; run health is reserved for U1 and H1.
- **Redaction:** F37 establishes one canonical source of redaction patterns and an explicit redaction policy, while each
  surface keeps its own allowlist and serialization responsibilities.
- **Usage, LINK:** under F25's usage vocabulary; F18.15 adds the gateway's trust and source classification.
- **Credentials, FINE:** the distinct capability and credential semantics stay.
- **Wait and wake, LINK through F43:** one wake primitive may have many consumers; "what changed" comes from
  `ActionProjection` and the outbox facts.
- **Notifier conditions, CONSOLIDATE** into F43 and `ActionProjection`.

### 3.14 The second composition audit

A second, narrow, fresh-context, report-only composition audit runs after M4-E's E7d, which also puts E6b's
publication path in scope (register E65). It covers only: the new actors and control seams since `1dd89d5`; failure and
recovery composed across owners; and credential, security and authority flow across the joins. For every recovery path
it asks what authority survived, what was revoked, what is reconstructed, what evidence stays admissible, which
generation or revision owns the result, what wakes whom, and whether recovery can resurrect stale authority. It
prefers dynamic fault scenarios to static inspection where practical: a generation replaced with notifications queued;
a delayed or duplicate stale result; custody lost during validation; a broker or steering-loop interruption; a provider
gateway restart; a plan or policy change during active work; a concurrent interface change; the queue with more than one
lane on the Rocky host. It is not another complete architecture review.

### 3.15 Areas kept out of Observability's ownership

Tracked explicitly, each with its own owner: Linux and Windows asymmetry of the joins (packs, wakes, usage), under
adapter and containment qualification (register E66); the audit's UNKNOWN areas, as audit coverage debt (E67);
correlation of evaluator records with product ids, under F19's evaluator correlation; and built-claim conformance
(E68). The acceptance's correction for the last: the ledger has no built field, so the future machine check applies to
the actual claims, the free-text `status: done` entries of the requirements ledger and the "Implemented" or "Built"
paragraphs of the implementation status page, each resolving to a test or path anchor.

### 3.16 The operator settings surface

The operator's goal is approved: the operator should not need to search YAML or JSON files to discover or change a
normal AEW-operable setting. The completeness rule applies to **operator-editable** settings, marked by an explicit
schema or registry annotation, not to every field of an internal schema. For each such field the dashboard provides,
automatically where possible, the current value, a human description, the valid values or range, its classification,
its effective boundary, the proposed value, the validation result, the diff, and a summary of the authority and effect.
A generic schema renderer covers ordinary scalar, enum, list and map values; an exceptional setting may use a custom
editor, but the completeness test proves that every operator-editable setting has one.

F20 owns the presentation, F15.4 the classification and effective-boundary semantics, and the existing operator
endpoint the mutation authority. The dashboard stays non-authoritative and never writes control state directly; the
site never becomes a model-visible control channel. The surface is gated by a security design for the first
write-capable dashboard flow (register F46).

### 3.17 Models per role

The first concrete setting is which models each role may use, split into four concepts:

- **A. The live model catalog** comes from the provider's model-information endpoint: the models that actually exist
  and their provider-advertised properties. No separate offline catalog is needed for this feature.
- **B. AEW's eligibility and recommendation** is owned by the execution-profile and model-routing policy, which
  consumes the model roster and capability information, qualification evidence, live provider availability, harness
  compatibility, required capabilities and qualified context and tool behaviour. F19 does not own product eligibility:
  it runs qualification experiments and produces evidence. The result is an advisory table per role and model, with a
  verdict (`recommended`, `eligible`, `not_recommended` or `incompatible`), evidence references and reasons. It keeps a
  hard distinction between a model that is technically incompatible or unavailable and one AEW does not recommend.
- **C. The operator's allowed set,** `allowed_models[role]`, is the operator's and legality-affecting, because it
  changes which model identities may be admitted to a governed role: changes go through the operator's `adopt`. An
  override of AEW's recommendation is allowed with an explicit confirmation and an override record. No override can
  make an unavailable model exist or bypass a hard execution or security incompatibility.
- **D. The preference order,** `model_preference_order[role]`, is separate: operational when it only reorders the
  adopted allowed set; a change of the set's membership stays legality-affecting.

**Fallback:** AEW may automatically choose the next currently usable model in the operator's preference order only when
that model is already in the adopted allowed set. It never introduces an unapproved model; when no allowed model is
usable, it raises operator attention.

### 3.18 The four layers of composition enforcement

The standing architectural discipline, with no Integration Manager or any other cross-cutting authority owner: narrow
owners stay authoritative and the joins between them become explicit and testable.

```text
1. PLAN                   F14 interactions[]           What interactions should exist?
2. STRUCTURAL             F44 owner-registry tests     Did every consequential fact declare its consumers?
3. INDEPENDENT AUDIT      fresh-context composition    What did the plan and the registry miss?
                          audits at milestones
4. OPERATIONAL FEEDBACK   F42 Observability and        What actually caused failures or waste,
                          Feedback                     and did the repair improve it?
```

### 3.19 The order of work

```text
record the AIR decisions
    ↓
F44
    ↓
F43 S1 → S2 → S3
    ↓
F45, after M4-E's E6a
    ↓
F41 activation (which also needs F45 and the two Q6a amendments)

in parallel, where dependencies permit:
    F9-X0 → F9.1, after F9's worker-direction prerequisites
    F42's design and input work
    the F18.15 convergence specification
    F46's security design
    the integration-debt rows' local-owner passes
after E7d:
    E65, the second composition audit
```

No frozen architectural decision needs reopening.

## 4. What the lead developer's check found

Context for §3; the acceptance governs. Checked against `main` at `8f4dabb`: seven of the response's dispositions were
confirmed as written and six corrected, none needing a frozen decision reopened. The corrections are the ones §3
records as the acceptance's: the process-event model is read-time, not the outbox (§3.2); the `--any` control lane
needs a run-less form and is one lane (§3.3); with messaging off only a digest of a sent instruction survives delivery
(§3.4); the gateway's owner is F18.8 with F28, and S18 is unbuilt (§3.5); blocked time belongs to the dependency engine
(§3.8); and the ledger has no built field (§3.15). It refined the registry (A3's classification referenced; unit-level
keys declared) and `interactions[]` (`SERIAL_REQUIRED` compiled to the existing dependency edge; closed conditions; lint
at acceptance, where none runs today).

On F9 it found the substrate generic where it matters, with two small defects (D1, a closed kind enum validated on read;
D2, no structured payload slot) and two dependencies that are not defects: worker-initiated messages are F9-B's, and the
Lead's wake for replies is F43 S3 with F9's reply slice. Per-kind routing needs an amendment of ADR-0017 D3 ("no engine
module branches on a kind"), which F9-A1 already allows at the design level. Who answers an advice request: in v1 the
Lead, in its own context; the `frontier_advisor` role is not dispatchable, and routine sanity checks would stretch its
trigger. It also confirmed that AX-01 can close without widening E6b: F45 touches the prepare record, the obligation,
the gates schema and the context packs, and an overlap only escalates the validation mode, never relaxes it.

## 5. Filing (lead developer)

- **Ledger:** AIR-01 to AIR-76, prefix AIR; this record is their source.
- **New register rows:** F42 (Observability and Feedback), F42.1 (the canonical process-event model), F42.2 (the
  repository-process adapter), F43 (the attention spine, slices S1 to S3), F44 (the consequential-fact owner registry),
  F45 (base-drift integration validation), F46 (the operator settings surface, with models per role), F14.1 (parent
  `interactions[]` and the composition rule), F9.1 (F9-X0 and the typed worker consultation and feedback kinds), F9.2
  (the admitted Lead instruction record in review context, AX-02), F18.15 (gateway usage convergence), and E56 to E70:
  the integration-debt rows (E56 to E62 for AX-06 to AX-08 and AX-12 to AX-15; E63 and E64 for gaps 3 and 8), the second
  composition audit (E65), the areas of §3.15 (E66 to E68), and the two consolidation links with no owner row (E69, the
  liveness reason vocabulary; E70, the single hard-deadline reason).
- **Dependencies:** AIR → F44 → F43 S1 → S2 → S3 → F45 (after E6a) → F41 activation. F41's activation also waits for
  F45 and for the two Q6a amendments (F41.1, F41.5).
- **Q6b:** MIC-07, MIC-08 and MIC-16 are marked `superseded-by:` AIR-08, and F15.2's decisions-due item for MIC-16's
  definition is removed: nothing is owed for it any more.
- **Q6a:** F41.1's and F41.5's decisions-due items stay open (owed now); F14.1 is added to what F41.1's item blocks.
- **Owed by this record:** F42's design (the first cross-cutting integration note) and F46's security design, each a
  decisions-due item.
- **Notes** on F9, F14, F15.2, F15.3, F15.4, F18.6, F18.8, F19, F20, F25, F28, F36, F37, F41, F41.1, F41.5, F41.7,
  F41.10, E43, E45, E54 and U1, each saying what changed with its AIR ids.
- **Q15**, the nit-rule divergence of v0.5 §21, is closed separately from these decisions: the operator aligned
  AGENTS.md with the product rule in pull request 193 (2026-10-10; one short delta review after nits following a CLEAR),
  so the register moves it to §9 and its decisions-due item is removed.
