# Dashboard investigation workbench — milestones and tickets

**Date:** 2026-10-03 (operator local date)  
**Revision:** 0.1  
**Status:** organized backlog; milestone implementation plans NOT YET APPROVED  
**Authority:** operator approved the four design tightenings and requested this ticket organization. This document creates planning tickets only; it creates no AEW Engine records, workflow transitions, remote issues, or backend contracts.

Sources:

- [Frontend handoff v3](aew-dashboard-api-waiting-work-and-m6-preview-handoff-v3.md): A–T and sections 5–7.
- [Research addendum v2](aew-dashboard-research-and-parallel-work-backlog-2026-10-02-v2.md): D01–D25 and six creative experiments.
- [Accepted contract record](../c0-approval.json), [frontend verification lessons](../frontend-verification-lessons.md), and existing optional frontend work.

This is the sequencing/ownership index. Source documents retain detailed product requirements; the four approved constraints and this reconciliation supersede conflicting ordering. Tickets are scoped planning units, not delivery-time estimates. Inspect the current optional implementation when planning to avoid rebuilding existing features.

## 1. Constraints and completion language

1. Accepted API `0.1.2` remains unchanged, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`. New fields use separate versioned preview contracts, schemas, fixtures, and manifest digests. Proposed vocabulary is visibly provisional. Live adoption requires main-line review; coordinate changes across canonical contract, generated types, runtime validation, and fixtures through a renewed acceptance gate.
2. Shared verification starts in W01: accessibility, safe untrusted display/CSP, polling/freshness, boundedness, offline evidence, and cache isolation. Every later ticket extends relevant checks. Scenario Lab and Contract Playground share infrastructure.
3. Establish identity/scope/validator isolation before simultaneous comparisons or multi-scope views. Route-only cache identity is insufficient for new scopes. Use only supported scope inputs, never invent wire fields or credential-bearing keys. Reject obsolete late responses; backend authorization filters data before delivery.
4. Why displays only supplied reasons tied to the selected record/status. Missing, unknown, denied, and unresolved explanations remain explicit. Preparation, acknowledged delivery, citation, and evaluated benefit remain separate evidence claims. No inferred workflow legality, truth, applicability, causality, ranking policy, containment, or hidden relationships.

All feature work belongs in an isolated optional frontend worktree/branch. Preserve the accepted core, original AEW checkout, and running Engine suite. The main line owns authentication, server headers/Host/Origin enforcement, projection semantics, persistence, packaging, and live integration. No installs, commands, recovery actions, publication, approval, or other mutations in the dashboard.

**Ticket readiness labels:**

- **C:** implementable using accepted contract 0.1.2, to the extent its supplied fields support the feature.
- **F:** fixture/developer-only feature; preview wire proposals require versioned schemas and fixture review before use.
- **I:** live behavior requires an accepted backend projection/capability or command definition.
- **X:** live behavior additionally needs backend policy/computation/export design. Frontend must not implement that authority.

Labels may be combined. F means feasible after prerequisite plans are approved, not permission to build now. Each ticket has separate states for plan approval, fixture/frontend acceptance, independent review, and integration acceptance. Missing API access is recorded as an integration blocker, not a reason to invent backend logic.

## 2. Milestones and stories

Use W identifiers to distinguish these dashboard milestones from AEW Engine milestones M4/M6 and backend features F15/F17.

| Milestone / story | Operator outcome | Prerequisites | Initial plan state |
|---|---|---|---|
| W01 — Reliable preview and verification foundation | Reproduce faults and trust scope/refresh labels | Current optional frontend baseline | Accepted frontend foundation |
| W02 — Shared investigation workspace | Inspect a record, its supplied reasons and links without losing place | W01 | Implemented; independent review pending |
| W03 — Knowledge Journal flagship | Follow one discovery/failure/lesson story with exact provenance | W01, W02; reviewed journal preview schema | Frontend task review ACCEPT at 7433ddd; merge and live integration separate |
| W04 — Comparison and context inspection | Compare independently identified records and see context receipts | W01, W02; W03 references for journal/context cross-links | W04-01–03 frontend fixture review ACCEPT at 2808149; CI and operator merge separate |
| W05 — Evidence and benchmark investigation | Read pinned artifacts; benchmark exploration deferred | W01, W02; W04-01 for paired comparisons | W05-01 accepted frontend fixtures; backend/live pending |
| W06 — Execution investigation | Follow recorded events, fanout and execution receipts | W01, W02, W05-01; W04 context components where used | W06-01–03 implemented; independent fixture review pending |
| W07 — Recall and knowledge investigation | Explore supplied evolution, reuse, retrieval and failure relations | W03, W04; evidence components where used | Not proposed |
| W08 — Operational obligations | Inspect supplied judgment, consequences and project aggregates | W01, W02; accepted F15/F17 or reviewed fixture proposals | Not proposed |
| W09 — Portable investigation and evaluated experiments | Rehearse investigations and evaluate narrowly bounded extensions | Feature-specific prerequisites below | Not proposed |

W01 → W02 → W03 is the recommended first delivery sequence. W04 follows the flagship. W05 and a small W06 preview can be brought forward after shared prerequisites if a concrete backend owner supplies representative samples. W08 live integration waits for its named projections. W09 is a menu of separately approved experiments, not one compulsory large release.

### W01 — Reliable preview and verification foundation

**Story:** As an API implementer, I can replay a known fault and see exactly why a response was accepted, rejected, cached, or isolated.

**W01-01 — Preview contract registry and backend question ledger** · F/I  
Scope: inventory current-contract versus preview-only fields; establish separate versioned preview artifacts, runtime schemas, fixture manifests/digests and a review ledger. Reuse approved generation tools where suitable. Keep journal/context/guarantee proposals out of the accepted 0.1.2 schema.  
Accept: accepted contract digest is unchanged; each preview identifies schema/version/digest and has valid/invalid examples; normal production excludes preview fixtures/handlers/unsupported surfaces; missing backend answers have named owner roles and live blockers.  
Sources: v3 boundary and M6 preview; D20; addendum contract questions. Depends on: baseline inspection only.

**W01-02 — Scope-aware queries, payload caches and validators** · C/F/I  
Scope: audit both transport and query caches; identify every supported response-changing scope/snapshot/authorization context. Keep validators and payloads in that identity; discard obsolete responses and clear inaccessible state on identity changes.  
Accept: delayed old-scope 200 and 304 cannot populate the new scope; same IDs in different scopes remain distinct; comparison sides stay independent; no cross-scope placeholders or secrets in keys/diagnostics. Mock authorization fixtures exercise frontend cleanup, while actual permission enforcement remains backend-owned.  
Sources: D02, D12; approved tightening 3. Depends on: W01-01 for proposed scope shapes.

**W01-03 — Scenario Lab and Contract Playground** · C/F  
Scope: one fixture catalog and actual boundary parsers power delay/disconnect/conditional-response/mixed-revision/capability/malformed/future-value controls and exact validation diagnostics. Extend the existing API drawer rather than duplicate it.  
Accept: valid and broken conditional-response scenarios are distinguishable; no healthy classification from invalid payloads; valid cached content survives failed refresh; no initial-error “stale data”; request/validator diagnostics omit sensitive content; F0–F11 remain covered.  
Sources: A, v3 section 5; D03, D20. Depends on: W01-01, W01-02.

**W01-04 — Deterministic replay and local regression evidence** · C/F  
Scope: seeded fixture scripts, controllable time, stable scenario links, pinned browser screenshots/traces, keyboard checks and production exclusion checks. Preserve 2/5/10-second polling, hidden-tab pause, visible refetch, 304 generation-time preservation, and 30 seconds of continuous-visible mixed-revision warning.  
Accept: replayed scripts produce the same response sequence; hidden time does not advance divergence warnings; delayed scope switches and capability loss are covered; offline builder/browser evidence identifies versions, commands, results and test scope. Relevant hostile-display/CSP checks run from this milestone onward.  
Sources: D03, D04; v3 section 7; approved tightening 2. Depends on: W01-02, W01-03.

### W02 — Shared investigation workspace

**Story:** As an operator, I can inspect a selected record and its supporting information without losing selection, scope, or keyboard focus.

**W02-01 — Investigation shell and responsive panel navigation** · C/F  
Scope: reusable results, detail and optional inspector panes; retain selection and permitted presentation state across panel changes. Avoid creating a separate navigation destination for every inspector.  
Accept: keyboard open/close restores focus; narrow layouts preserve readable identity and confine table overflow; demo previews are unmistakable; unknown/deleted/denied references have distinct states.  
Sources: D01. Depends on: W01.

**W02-02 — Revision/scope presentation and Universal Why** · C/F/I  
Scope: shared display of supplied project/scope, generation/check times, revisions/roots and available reasons; explicit missing/unknown/denied explanation states. Context receipt labels are reusable presentation components.  
Accept: a status with no supplied reasons shows that limitation; unrelated reasons are not reassigned to the status; generated time is not “last changed”; unsupported historical links cannot silently display current data; unknown semantic values retain raw-value warnings.  
Sources: B, D02; approved tightening 4. Depends on: W01, W02-01.

**W02-03 — Bounded provenance explorer and relation-list alternative** · C/F/I  
Scope: extend existing History/Work graph patterns with supplied edge provenance, traversal limits, typed entity routing and accessible relation lists. Preserve selection and graph panning after fit.  
Accept: bounds/truncation/continuation and unknown completeness are visible; no displayed edge is never presented as proof of no relation; no edge edits or prose-inferred links; unresolved targets remain references; keyboard/list and pointer navigation work.  
Sources: D, H; D01, D19 foundation. Depends on: W02-01, W02-02.

**W02-04 — Deep links, dashboard-link copy and safe navigation** · C/F/I  
Scope: extend existing jump-to-ID, typed entity routing and shareable presentation links. Historical scope links require supported historical reads.  
Accept: deep-link reload retains permitted scope/selection; unavailable historical revisions have an explicit result; opaque IDs are encoded safely; same-origin and explicit external-navigation rules remain intact; no automatic CLI execution.  
Sources: v3 section 6. Depends on: W02-01, W02-02.

### W03 — Knowledge Journal flagship

**Story:** As a developer, I can follow what was discovered, what failed, and how a retained lesson relates to its original evidence.

**W03-01 — Journal contract proposal and coherent example story** · F/I  
Scope: review one bounded fixture story covering observation, failed approach, evidence, retained lesson and canonical decision reference. Record type/applicability/relations are supplied provisional vocabulary; distinguish source timestamps and response metadata.  
Accept: every displayed semantic claim has a fixture field/source; denied, missing, stale, contradictory and unknown cases exist; record kind confers no truth; main-line open questions and preview digest are recorded.  
Sources: G, G1, G2, L. Depends on: W01-01, W02.

**W03-02 — Journal stream, filters and dense alternate view** · F/I  
Scope: compact chronological journal with restrained type coding, supplied component/type filters and bounded pagination/virtualization; optional dense table without replacing the journal.  
Accept: type color is not a truth/health indicator; selection survives paging/filter changes where valid; keyboard and phone layouts work; missing applicability is explicit; large fixture rendering/request measurements are recorded.  
Sources: G, G2. Depends on: W03-01.

**W03-03 — In-place provenance drawer and origin graph** · F/I  
Scope: claim, limits, positive/negative evidence, origin/revision/environment, producer/prompt identity, canonical references and bounded origin links. Reuse W02 shell/Why/graph.  
Accept: exact source identity is visible; missing receipts/references are not fabricated; canonical decisions remain references; opening graph preserves journal selection; “Included in context” does not imply delivery, use or benefit.  
Sources: G1, H; D14 foundation. Depends on: W03-02, W02-03.

### W04 — Comparison and context inspection

**Story:** As a developer, I can compare two explicit sources and inspect what context was prepared and what delivery/use evidence exists.

**W04-01 — Independent comparison shell and snapshot adapters** · C/F/I  
Scope: side-by-side identities, separate loading/errors, optional linked presentation controls; compare two supplied snapshots/diffs. Structural browser differences are labeled presentation calculations.  
Accept: a failed/denied right side never substitutes left-side data; historical unavailability stays explicit; identity/ETag/cache isolation holds; no inferred semantic state or causal explanation.  
Sources: C; D08. Depends on: W01-02, W02.

**W04-02 — Run/invocation comparison** · C/F/I  
Scope: reuse comparison shell for fields accepted contract supplies; model/profile/card/context/capability fields require preview proposals if absent.  
Accept: each side's work/source/response identities are visible where supplied; unavailable dimensions remain unavailable; changes are not diagnosed as causes; receipts can link to existing details.  
Sources: E; D08, D16 comparison. Depends on: W04-01.

**W04-03 — Context inspector and budget anatomy** · F/I  
Scope: supplied packet sections, selected/omitted/truncated records, reasons, token/byte accounting and preparation/delivery/citation/evaluation receipts.  
Accept: units and estimator identity are explicit; unauthorized omitted candidates never appear in fixtures intended to model an authorized payload; prepared versus acknowledged delivery is unmistakable; absent metadata has no synthetic substitute.  
Sources: J; D10. Depends on: W01-01, W02-02, W03 references where used.

**W04-04 — Packet diff and context-pressure replay** · F/I  
Scope: compare packet identities, sections, fingerprints, supplied constraints/evidence/recall and truncation; optional recorded compaction replay with a static alternative.  
Accept: no attention heat map or influence inference; timestamps do not invent intermediate packets; reduced-motion mode works; exact packet/delivery identities remain attached to both sides.  
Sources: K; creative context-pressure replay. Depends on: W04-01, W04-03.

**W04-05 — Attempt isolation view** · F/I  
Scope: supplied attempt/worktree/visibility lanes and explicitly shared knowledge using W01 isolation mechanisms.  
Accept: unauthorized records are absent from received payloads/cache/DOM, not merely hidden; identical IDs/titles never merge across scope; unknown origin remains unknown; fixture evidence and real backend authorization acceptance are reported separately.  
Sources: D12. Depends on: W01-02, W02, W04-01.

### W05 — Evidence and benchmark investigation

**Story:** As a developer, I can inspect exact bounded evidence and find the individual trials behind a reported benchmark result.

**W05-01 — Safe bounded evidence reader and pinned citations** · C/F/I  
Scope: metadata supported today plus proposed authorized artifact/excerpt reads for text/code/logs/structured diagnostics. Do not derive artifact paths or read `.aew` storage.  
Accept: range/hash/media identity and truncation are explicit; denied/missing/hash-mismatched content differ; terminal escapes and HTML/SVG cannot execute; Markdown cannot fetch remote images; copied citations retain exact identity.  
Sources: D06. Depends on: W01, W02.

**W05-02 — Existing Timeline and Evidence CLI gaps** · C/F/I  
Scope: first verify whether current projections supply timestamped transitions and whether the main owner supplies a supported read-only Evidence command. Implement only verified portions, preserve unresolved gaps.  
Accept: timeline events/gaps have exact supplied timestamps and labeled browser duration calculations; no invented lifecycle events; CLI copy uses approved allowlisted templates and safe quoting, never runs a command.  
Sources: tracked v3 gaps; D05, D06. Depends on: W02; live blockers resolved separately.

**W05-03 — Benchmark fixture/export proposal and owner review** · F/I/X  
Scope: agree a minimal purpose-built export with the benchmark owner: cohort/task/version/config/environment/trial/outcome/evaluation identity and missing results. No raw storage parsing.  
Accept: representative owner-approved samples and versioned schema exist before the explorer; engine performance and agent quality datasets are distinguished; questions about statistical analysis and import limits have dispositions.  
Sources: D07. Depends on: W01-01. Conditional bring-forward candidate if samples become available.

**W05-04 — Benchmark explorer and trial comparisons** · F/I  
Scope: separate performance and agent-quality views, fixed cohort summaries supplied by export, individual trial drill-down and comparison.  
Accept: evaluation provenance and repetitions are visible; missing outcome is neither success nor failure; microbenchmark speed is not task quality; no statistical significance claim without supplied analysis; import remains bounded and labeled.  
Sources: D07. Depends on: W05-03, W04-01; W05-01 for artifact drill-down.

### W06 — Execution investigation

**Story:** As an operator, I can follow recorded execution and distinguish configured controls from validated guarantees.

**W06-01 — Run flight recorder and event contract proposal** · F/I/X  
Scope: bounded recorded event lanes for invocations/tools/evidence/reviews/transitions and packet receipts. Event order, correlation and relationships are supplied. Scrubbing is inspection only.  
Accept: missing intervals/lane coverage are visible; logical order and timestamps differ where necessary; no imaginary exact state between snapshots; event selection opens exact evidence/context; historical retention limitations remain explicit.  
Sources: D05. Depends on: W02, W05-01, W04-03 for packet lanes.

**W06-02 — Fanout and execution budget companion** · F/I  
Scope: registered parent/child execution classes, active/ended state, supplied budget/depth/coverage in the recorder, not a second execution browser.  
Accept: observed count, budget and enforcement are separate; unregistered/unknown children remain explicit; no inferred children from cost/time; large trees are bounded; no browser budget enforcement claim.  
Sources: R; D24. Depends on: W06-01.

**W06-03 — Execution guarantees, capability and airgap receipts** · F/I  
Scope: shared component for backend-supplied guarantee class/validation receipt/environment/time and configured-versus-tested tool/provider availability. Reuse in runs, comparisons and recorder.  
Accept: absent claims/receipts show UNKNOWN/UNLABELED; worktree/configuration is not promoted to containment; availability differs from tested readiness; outdated validation does not silently become current; no installers or commands.  
Sources: O; D16, D21. Depends on: W01-01, W02-02; later attaches to W04/W06 views.

### W07 — Recall and knowledge investigation

**Story:** As a developer, I can inspect supplied knowledge changes, retrieval results and failure relationships without the browser becoming a memory authority.

**W07-01 — Evolution, freshness and disagreement lenses** · F/I  
Scope: alternate journal modes for supplied supersession/contradiction/environment links and applicability; use shared comparison and provenance to inspect disagreements.  
Accept: wording changes do not imply truth changes; applicability is never computed from age; old records remain inspectable where allowed; unknown relationship types are explicit; color is not the only cue.  
Sources: G2, L; D13; creative disagreement view. Depends on: W03, W04-01.

**W07-02 — Inclusion, citation and reuse trail** · F/I/X  
Scope: follow supplied packet inclusion, acknowledged delivery, explicit citations, downstream references and evaluated outcomes. Include evidence-forward navigation.  
Accept: duplicate/retry identities do not inflate supplied counts; inclusion is not causal contribution; no “lesson fixed N tickets” from context counts; no edges inferred from similar prose.  
Sources: G1, G2, H; D14; creative evidence-forward traversal. Depends on: W03-03, W04-03.

**W07-03 — Retrieval debugger and supplied selection comparison** · F/I/X  
Scope: fixture/backend result sets and selection diagnostics with provider-specific scores, scope, exclusions, provenance and budgets. Compare supplied outputs; no browser ranking engine.  
Accept: scores are not truth probabilities; demo controls say demo; live counterfactuals require a separately accepted evaluation interface; forbidden-scope candidates are not disclosed; raw provider tables are never inspected.  
Sources: I; D11. Depends on: W01-01, W04-01, W04-03.

**W07-04 — Index generation inspector and candidate inbox** · F/I  
Scope: developer views for supplied generation/root/watermark/provider/lag/rebuild metadata and inspection-only distillation candidates. Distinguish produced/received/published/rejected only if supplied.  
Accept: no raw database views; degraded index does not imply lost project truth; no publish/approve/reject controls; candidate provenance and limitations are visible; no persistent browser candidate store.  
Sources: M, N. Depends on: W03, W02-02.

**W07-05 — Failure archaeology and pattern board** · F/I  
Scope: supplied failure signatures/matches, attempts, failed approaches, conditions and successful evidence. Reuse journal, evidence and comparison panes.  
Accept: matching basis and environment differences are visible; no prose-derived failure classifier; a failed approach is conditional, not an eternal prohibition; missing source coverage stays explicit.  
Sources: F; D15. Depends on: W03, W04-01, W05-01.

### W08 — Operational obligations

**Story:** As an operator, I can inspect backend-declared obligations and the evidence behind them without the dashboard deciding what action is legal.

**W08-01 — Judgment and stage-intent inspection** · F/I  
Scope: F15-supplied ActionProjection, pending judgment, interrupted intents and anomalies in existing investigation panes. Coordinate with existing Attention/Queue surfaces instead of implying a second engine queue.  
Accept: mechanical/policy-resolved/judgment-bearing distinctions are supplied; dangling intent is not proof an action occurred; recovery history and exact surfaced reasons are inspectable; no recovery/action controls.  
Sources: Q; D23. Depends on: W02; live gate: accepted F15 projection.

**W08-02 — Consequential observations board** · F/I/X  
Scope: F17-supplied dispositions, source/evidence, age, owner/follow-up and supplied trends.  
Accept: missing assessment is not harmlessness; closure evidence/disposition is explicit; counts and accepted-open share are not quality scores; trend/cohort semantics come from accepted projections.  
Sources: P; D22. Depends on: W02; live gate: accepted F17 projection.

**W08-03 — Requirement/evidence coverage lens** · F/I/X  
Scope: supplied requirement/criterion links to plans, attempts, evidence/reviews and backend coverage judgments.  
Accept: partial query coverage is visible; empty cells do not mean unmet; evidence links do not establish acceptance; frontend never decides completion.  
Sources: D09. Depends on: W02, W05-01; live gate: accepted coverage projection.

**W08-04 — Coherent project guarantees and obligations strip** · F/I/X  
Scope: optional compact header from a backend-supplied coherent aggregate, linking to detailed guarantees, observations, judgment, fanout and recall where available.  
Accept: missing/unsupported values are explicit; no aggregation of independently polled detail widgets into a claimed coherent snapshot; no synthetic security/health score; every supplied value has an appropriate detail link.  
Sources: T. Depends on: W06-03 and relevant W08/W07 details; live gate: accepted aggregate projection.

### W09 — Portable investigation and evaluated experiments

**Story:** As a developer, I can rehearse an investigation or inspect a bounded exported record while knowing its authority and completeness limits.

Each experiment receives its own small approved scope, usefulness task, stopping rule and evidence. Selecting one does not approve the rest.

**W09-01 — Portable dossier contract and offline viewer** · F/I/X  
Scope: bounded versioned fixture exports of selected sources/reasons/comparisons; distinct offline viewer. Actual export authorization/redaction/retention require owner policy.  
Accept: schema/size limits and hostile import checks; no executable HTML; redaction/incompleteness explicit; no silent evidence persistence or merge into live truth; hash integrity is not issuer authenticity.  
Sources: D17. Depends on: W02, W05-01; W04 for included comparisons.

**W09-02 — Guided investigations and bad-review control worlds** · F  
Scope: fixture-authored tasks and exact source-referenced answers, including suspicious and legitimate fast reviews, stale revision and partial coverage.  
Accept: duration alone is never an answer key; measure accuracy as well as time; no training controls in normal production; keyboard completion works.  
Sources: S; D18, D25. Depends on: W01-03, W01-04, W02. Can be selected earlier after prerequisites.

**W09-03 — Recorded temporal graph and incident rehearsal** · F/I/X  
Scope: inspect supplied relation snapshots and crash/recovery records with bounded graph/timeline scrubbing.  
Accept: no invented intermediate state or browser recovery simulation; missing history differs from not-applicable; reduced-motion and static relation alternatives work; training cannot execute a retry/recovery.  
Sources: D19; creative incident rehearsal. Depends on: W02-03; W06-01 for recorded event lanes.

**W09-04 — Blind comparison experiment** · F; X for persisted ratings  
Scope: presentation-only concealment of supplied provider/model labels while inspecting outputs/evidence; no new reviewer authority or scoring pipeline.  
Accept: source identity remains available after reveal; no persisted ratings without separate approval/contract; operator accuracy and interpretation are evaluated, not a model leaderboard.  
Sources: creative blind comparison. Depends on: W04-01, W05-01.

**W09-05 — Read-only operator briefing experiment** · F/I; X for generated service  
Scope: deterministic presentation of supplied changes, attention and unknowns. Extend Since Viewed only within its declared loaded-page/revision bounds.  
Accept: browser comparisons are labeled; no synthetic global counts or health conclusions; source links and incompleteness are explicit; an LLM narrative would be advisory and require a separate service design.  
Sources: creative operator briefing; C. Depends on: W02, W04-01.

## 3. Coverage reconciliation

Every source item has a destination. Mapping is coverage, not duplicate implementation authorization.

| v3 source | Destination |
|---|---|
| A Scenario Lab; section 5 Playground | W01-03, W01-04 |
| B Why | W02-02 |
| C Revision compare | W04-01, W09-05 |
| D Provenance | W02-03, W02-04 |
| E Run compare | W04-02 |
| F Failure archaeology | W07-05 |
| G/G1/G2 Journal/detail/modes | W03-01–03; deeper evolution/reuse W07-01–02 |
| H Recall graph | W03-03, W07-02; shared graph W02-03 |
| I Retrieval | W07-03 |
| J Context | W04-03 |
| K Packet diff | W04-04 |
| L Freshness/contradiction | W07-01 |
| M Index; N Candidates | W07-04 |
| O Guarantees | W06-03 |
| P Consequences; Q Judgment | W08-02, W08-01 |
| R Fanout | W06-02 |
| S Training | W09-02 |
| T Project strip | W08-04 |
| Section 6 Navigation | W02-04 |
| Section 7 Quality | W01-04 and all relevant ticket acceptance gates |
| Tracked Timeline / Evidence CLI | W05-02 |

| Research source | Destination |
|---|---|
| D01 | W02-01 |
| D02 | W01-02, W02-02 |
| D03 | W01-03–04 |
| D04 | W01-04 |
| D05 | W06-01; timeline gap W05-02 |
| D06 | W05-01–02 |
| D07 | W05-03–04 |
| D08 | W04-01–02 |
| D09 | W08-03 |
| D10 | W04-03 |
| D11 | W07-03 |
| D12 | W01-02, W04-05 |
| D13 | W07-01 |
| D14 | W07-02 |
| D15 | W07-05 |
| D16 | W06-03; comparison W04-02 |
| D17 | W09-01 |
| D18 | W09-02 |
| D19 | W09-03; shared foundation W02-03 |
| D20 | W01-01, W01-03 |
| D21 | W06-03 |
| D22 | W08-02 |
| D23 | W08-01 |
| D24 | W06-02 |
| D25 | W09-02 |
| Disagreement / evidence-forward experiments | W07-01 / W07-02 |
| Incident / context-pressure experiments | W09-03 / W04-04 |
| Blind compare / briefing experiments | W09-04 / W09-05 |

No adoption of Grafana/Langfuse/OTel/Storybook or additional graph libraries is implied by research references. Use current dependencies first. Each new dependency needs an actual consumer, pinned offline cache support and staged assets; toolchain interactions update `web/docs/spt-toolchain-feedback.md`. Nonblocking SPT improvements remain ticket-ready feedback; frontend/SPT build blockers receive separate minimal fixes and retests. Engine semantic blockers go to the main owner.

## 4. Per-milestone planning and approval procedure

Next planning target: **W01 only**, after the operator reviews this organization. Do not treat this backlog as its implementation plan.

For each milestone, write a separate plan under `web/docs/design/plans/` when requested/selected. The plan must include:

1. Exact baseline commit/worktree and current implementation inventory; scoped tickets and exclusions.
2. Operator tasks and expected UI flow, including a realistic visual preview where relevant.
3. Component/API-boundary changes and minimal dependencies; accepted-contract versus preview field matrix.
4. Versioned schema/fixture artifacts and digests; backend question ledger with owner roles and explicit live blockers.
5. Ticket dependencies, executable sequence, checkpoints and rollback/review boundaries.
6. Unknown/denied/unsupported/stale/error states; scope/validator handling and late-response behavior.
7. Relevant unit/component/contract/refresh/browser/security/offline checks and evidence paths. No Engine suite invocation.
8. Performance/boundedness targets calibrated against the baseline, not unmeasured promises.
9. Independent reviewer and handoff requirements; frontend acceptance versus integration disposition.
10. Operator approval record bound to the exact plan revision/digest. A material scope/schema change requires renewed approval before dependent work.

Approval records are factual: leave them pending until the operator actually approves. Approval of a frontend preview plan does not approve its backend wire proposal. Capture main-line schema acceptance separately against version/digest/commit. Independent review must inspect the frozen implementation, distinguish rerun checks from implementer evidence, and disposition findings before frontend acceptance.

| Milestone | Plan artifact | Operator approval | Frontend / fixture acceptance | Independent review | Live integration |
|---|---|---|---|---|---|
| W01 | [Plan 1.1](plans/w01-foundation.md) | Operator approved | Accepted at ad9ed21 | ACCEPT — Claude, 2026-10-03 | Not claimed |
| W02 | [Plan 1.1](plans/w02-workspace.md) | Operator approved, including both tightenings | Implemented and locally validated at 0e64b31; acceptance pending | Pending frozen main-line review | Not claimed |
| W03 | [Plan 1.1](plans/w03-journal.md) | Operator approved 2026-10-03 | Frontend / fixture task review accepted at 7433ddd; PR merge separate | ACCEPT — main-line lead reviewer, 2026-10-03; findings1–5 resolved | Blocked on accepted journal projection; not claimed |
| W04 | [Plan 1.0](plans/w04-comparison-context.md) | Operator approved 2026-10-03 | W04-01–03 merged at 211e29c | ACCEPT at 2808149; all findings resolved | Preview adoption and live integration pending |
| W05 | [Plan 1.1](plans/w05-evidence-inspection.md) | Operator approved 2026-10-03 | W05-01 implemented; W05-02 capability gaps recorded | ACCEPT at e875e81; all findings fixed; clean committed-source evidence regenerated | Artifact adoption/live pending; Timeline/CLI gaps preserved; benchmarks deferred |
| W06 | [Plan 1.1](plans/w06-execution-investigation.md) | Explicit implementation approval 2026-10-04 | W06-01–03 implemented; verification evidence in `web/docs/w06-evidence/` | ACCEPTED independent frontend fixture re-review, 2026-10-04, source 55c48ec; `web/docs/w06-re-review-55c48ec.md` | Blocked on accepted T3 and Engine projections; G7/F7 adapter required |
| W07 | Not written | Pending | Not started | Pending | Recall projections/policies pending |
| W08 | Not written | Pending | Not started | Pending | F15/F17/coverage/aggregate projections pending |
| W09 | Not written | Pending | Not started | Pending | Ticket-specific; fixture training needs none |

## 5. Common acceptance and handoff

Each selected ticket must demonstrate its operator question against realistic fixtures, with exact source identity and all relevant error/unknown states. Semantics are supplied; browser structural calculations are labeled. All collections/graphs/imports are bounded. Keyboard, focus, both themes, responsive panels and safe display remain requirements throughout.

Milestone evidence includes frozen commit, contract/preview provenance, builder/cache/browser identities, commands/results, screenshots and traces where useful, independent review disposition, integration checklist and updated SPT feedback. Run the applicable frontend offline gate from empty `node_modules` in the immutable Node 22 carrier with networking disabled; browser assets are staged separately to match pinned Playwright. Do not characterize focused checks or historical green results as current full verification.

Normal production builds must not initialize MSW or contain fixture catalogs/preview response data. Developer-only previews require explicit demo builds and labels. Approved future production surfaces must gate requests on capabilities, preserve authenticated same-origin GET/HEAD behavior, avoid credential leakage and display supported-unavailable/unsupported/unknown honestly.

At each milestone boundary, report what is accepted as frontend behavior, what remains a fixture proposal, and what needs live integration. Nonblocking improvements do not silently expand scope or delay an otherwise accepted milestone. Optional features do not reopen accepted core semantics.
