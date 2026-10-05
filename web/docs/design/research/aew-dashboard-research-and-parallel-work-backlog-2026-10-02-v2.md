# AEW dashboard research review and parallel-work backlog — v2

**Date:** 2026-10-02 operator local date / 2026-10-03 UTC  
**Disposition:** Addendum for designer review and ticket sorting; does not amend approved backend semantics  
**Reviewed:** supplied `aew-dashboard-api-waiting-work-and-m6-preview-handoff-v2.md`  
**Environment:** read-only dashboard, Rocky 8/airgap deployment, real API pending, backend testing and benchmarking in progress

## Planning reconciliation — 2026-10-03

This document remains the historical v2 research review; the v3 handoff is now available. The operator approved four tightenings: separate accepted/live contracts from versioned preview schemas; start shared verification immediately; establish cache/scope isolation before comparisons; and make missing explanations plus preparation/delivery/citation/benefit distinctions explicit.

The [milestone and ticket backlog](../dashboard-workbench-milestones-and-tickets.md) reconciles v3 A–T, this document's D01–D25, tracked gaps, and creative experiments. It supersedes the ordering in section 8, preserves the D identifiers as source references, and records which work requires future read projections. Backlog organization does not approve any milestone implementation plan. Each plan must be reviewed and approved separately before work begins; fixture acceptance does not constitute live integration acceptance.

## 1. Recommendation

Keep the v2 handoff. Its strongest concepts are the Knowledge Journal, universal Why inspector, exact provenance, fixture lab, and context-packet inspection. They fit AEW's canonical ownership well.

Use the available developer to build a coherent **engineering investigation workbench** around those concepts. The highest-value additions are:

1. Reusable investigation shell and explicit revision/scope presentation.
2. Scripted scenario replay and local regression evidence.
3. Run flight recorder linking timeline, packets, evidence, and outcomes.
4. Evidence reader and source-pinned excerpts.
5. Benchmark explorer for the results currently being produced.
6. Side-by-side investigations, then bounded lineage and coverage views.
7. Per-run execution-guarantee labeling and unlabeled-state honesty.
8. Fanout/execution-budget visibility integrated with the run flight recorder.
9. Read-side judgment/stage-intent and consequential-observation surfaces once F15/F17 projections exist.
10. Adversarial review-quality training worlds that test operator interpretation rather than duration heuristics.

These can all start with fixtures. Live integration is blocked by particular read projections, not by the absence of a complete API. Prototype schemas are proposals to the backend designer, not accepted contracts merely because a frontend has implemented them.

Build a separate research addendum rather than replace v2: existing commitments remain recognizable. No frontend repository was inspected, so the implementation inventory is taken from the supplied handoff. No feature implementation, target-runtime verification, or user study was performed here.

## 2. Review of v2: retain, consolidate, clarify

| Existing proposal | Assessment | Recommended adjustment |
|---|---|---|
| Scenario Lab + Contract Playground | Excellent first work | Share fixture catalog, transport overrides, schema diagnostics, and replay scripts |
| Universal Why inspector | Reusable core capability | Support missing explanation, denied source, unknown reason, and unresolved reference explicitly |
| Revision compare + run compare + packet diff | Valuable but overlapping | One comparison shell with specialized renderers and independently identified sides |
| Journal + evolution + graph + freshness explorer | Strong flagship | One journal workspace with alternate views, not four isolated navigation destinations |
| Failure archaeology | Useful later | Reuse investigation shell; matching signatures/relations must be supplied |
| Retrieval debugger + index inspector | Useful developer surfaces | Keep behind developer navigation; show coverage/lag and unavailable metadata |
| Candidate inbox | Correctly read-only | Distinguish produced, AEW-received, published, and rejected only if supplied |
| Execution guarantee labeling | High-value safety/honesty surface | Backend-supplied guarantee class + validation receipt; loud UNKNOWN/UNLABELED state |
| Fanout tree | Strong flight-recorder companion | Show registered execution tree, budget, depth, and unknown/unregistered children only when supplied |
| Judgment/stage-intent + consequential observations | Strong future operational surfaces | Fixture-ready now; live semantics wait for F15/F17 read projections |
| Seeded bad-review world | Cheap, valuable training extension | Contrast suspicious and legitimate fast reviews; do not teach duration as the judgment |
| Quality work “if features run out” | Too late in the ordering | Accessibility, hostile-content tests, cache isolation, and local regression begin with the first shared component |
| Timeline and Evidence CLI gaps | Real existing gaps | Preserve them in the backlog; new visual ideas should not hide them |

### Important wording and contract corrections

**“What the model received” needs receipts.** A compiled packet is not necessarily a delivered packet. Delivered context is not proof it was attended to, used, cited, or causally responsible for success. Show separate states: prepared, delivery acknowledged, referenced in an output, and independently evaluated benefit. Unknown stays unknown. Suggested labels are proposals; reuse established AEW vocabulary if different.

**Freshness has several axes.** Request completion time, generated time, control revision, source revision, history root, index watermark, and applicability are different facts. A 304 means the validator matched a representation; it does not establish source applicability or whole-page consistency.

**Revision links need honest availability.** A URL with `rev=844` is a request for that revision, not proof the server retains or can reconstruct it. Unsupported/unavailable historical views must not silently show today's data under yesterday's label.

**Partial graphs are partial knowledge.** “No displayed edge” does not prove “no relation exists.” Show traversal bound, visible node/edge count, continuation availability, and server-declared completeness when available.

**Kind names do not confer truth.** A journal “Fact” or “Discovery” still requires evidence/applicability status. A decision reference is a pointer to the decision, not a newly distilled copy.

**Recently used needs precise meaning.** Call it “Included in context” unless AEW supplies stronger usage evidence. Show later work references separately.

**Browser preferences are allowed presentation state.** Pane layout, density, and filter presets can be local. Claims, decisions, candidates, checkpoint state, source excerpts, and inferred applicability must not become a parallel persistent memory store.

**Guarantee labels are evidence-bearing claims.** A worktree, sandbox flag, or harness permission setting does not by itself prove containment. Show the exact backend-supplied guarantee level, validation environment/receipt, and an explicit `UNKNOWN`/`UNLABELED` state.

**Open-observation counts are not quality scores.** `accepted_open` or `known_limit` may increase because AEW became more honest about unresolved consequences. Show counts, age, movement, and disposition; do not color a lower share as automatically better.

**Review duration is not review quality.** Training fixtures may surface duration as one signal, but operator exercises must require corroborating evidence such as inspected sources, evidence accesses, revision binding, coverage, or supplied anomaly reasons.


## 3. Research patterns worth borrowing

These are interaction/engineering references, not recommendations to deploy additional platforms.

| Primary reference | Documented behavior | AEW adaptation |
|---|---|---|
| Grafana Explore [S1] | Side-by-side exploration, linked time ranges, query inspector, shareable views | Synchronized investigation panes with independently pinned identities |
| Playwright Trace Viewer [S2] | Timeline/action inspection with snapshots, logs, network detail; local trace viewing | Borrow the flight-recorder interaction and use local traces to debug the dashboard |
| OpenTelemetry trace API [S3] | Explicit parent/child contexts and links between spans/traces | Draw supplied execution relations; timing proximity alone does not establish causality |
| Langfuse experiment comparison [S4] | Baseline comparisons, item-level inspection, fixed dataset versions | Benchmark explorer with comparable-task drill-down and evaluation provenance |
| MSW [S5, S6] | Controlled delays and network-error responses | Scripted fixture transport failures rather than just static screenshots |
| TanStack Query [S7, S8] | Query-key-based caching and previous-data placeholders | Explicit scope keys; prevent previous project/attempt data masquerading as the new selection |
| React Flow [S9, S10] | Keyboard/screen-reader support and performance guidance | Read-only bounded graphs with accessible relation lists |
| Playwright visual comparisons [S11] | Screenshot assertions; rendering varies with environment | Pinned local browser/font baseline for airgap regression |
| Storybook accessibility tests [S12] | Component-level automated accessibility checks | Reuse the existing test stack where possible; manual keyboard checks remain necessary |

Do not adopt Grafana, Langfuse, an OTel collector, or Storybook just to imitate these interactions. Existing React components and test tools may be sufficient. Benchmark data import does not require installing the platform used as inspiration.

## 4. Dependency and effort notation

**F — fixture-ready:** developer can implement and test now without a real AEW API.  
**I — integration blocked:** useful live behavior requires a backend-supplied read projection/capability.  
**X — architecture extension:** involves a new backend policy, computation, export, or execution contract.

Every proposed feature below is F for its mock UI. I/X describe the blocker for real operation. None is permission to add mutation controls.

Effort is relative for one developer: **S** a focused extension; **M** several components/interactions; **L** substantial new surface. These are planning estimates, not promised delivery dates. Use prototypes to revise them.

## 5. Ticket-ready backlog

### D01 — Investigation workspace shell
**Priority:** P0 · **Effort:** M · **Blocker:** I: scoped entity read/detail surfaces

A shared left result list, center evidence/detail pane, and optional right Why/provenance/context pane. Selection survives opening/closing panels; URL encodes permitted entity IDs and presentation state. Work, journal, failures, and runs reuse it.

**Acceptance:** keyboard-only open/close/navigation; focus returns to selection; unknown/deleted/denied references render distinctly; switching project cannot leave the prior project's details on screen; narrow layouts retain readable source identities.

### D02 — Revision and scope presentation
**Priority:** P0 · **Effort:** S/M · **Blocker:** I: identity/revision envelopes; X if atomic snapshot reads are not already supported

Expose project, worktree, attempt, source revision, response revision/root, and live/frozen mode in the relevant view. Mixed revisions are visible. A coherent snapshot is displayed only when the backend supplies the required identity/consistency guarantee.

**Acceptance:** fixtures for coherent, mixed, unavailable historical, lagging index, stale cache, and denied scope; no green “consistent” claim based merely on successful requests; generated time is not labeled “last changed.”

### D03 — Scripted scenario replay
**Priority:** P0 · **Effort:** M · **Blocker:** none for developer fixture mode

Extend v2's selector into a seeded script: start at rev A, begin request, switch attempt, return old response late, supersede source, drop connection, then recover. Maintain fixture version, seed, scripted clock, and scenario link.

**Acceptance:** same script yields the same fixture sequence; late responses do not overwrite the new scope; distinguish HTTP failure, network failure, and invalid payload; production build excludes scenario registration and mock worker startup.

### D04 — Local regression evidence pack
**Priority:** P0 · **Effort:** M · **Blocker:** none; build/browser assets must be staged

Use existing test tools to run the important worlds and capture failures, screenshots, and traces locally. Shared components get accessibility checks from the start.

**Acceptance:** tests cover keyboard inspector access, stale/unknown states, hostile Markdown, scope switching, disconnected states, and readonly graph behavior; screenshots use a fixed browser/font environment; airgap run makes no dependency downloads or cloud visual-test requests.

### D05 — Run flight recorder
**Priority:** P1 · **Effort:** L · **Blocker:** I: bounded event/run timeline, correlation IDs, packet references, delivery receipts; replayable snapshots may require X

A read-only timeline with lanes for role invocations, tool events, evidence publication, reviews, packet preparation/delivery, and canonical transitions. Selecting an event opens its exact packet/evidence/Why detail. Scrubbing changes inspected recorded data, never AEW execution.

**Acceptance:** incomplete intervals and missing lanes stay visible; timestamps are displayed separately from logical order; supplied links distinguish parentage from other relations; no invented exact snapshot between recorded states; an included recall item is not labeled causal influence.

### D06 — Evidence reader
**Priority:** P1 · **Effort:** M · **Blocker:** I: authorized bounded artifact/excerpt read contract, media type, identity/hash, verification result

Read logs, source excerpts, review text, test results, and diffs without bouncing between pages. Pin line selections to artifact identity/hash and backend-declared ranges. Start with text, code, and supplied structured diagnostics.

**Acceptance:** huge payloads stay bounded; truncated excerpts are labeled; missing/denied/hash-mismatched sources are distinct; Markdown cannot fetch external resources; terminal escape sequences are displayed safely; no execution of artifact HTML/SVG; copied citations include exact source identity.

Include the existing Evidence CLI gap here only using backend-approved command shapes. Do not generate arbitrary shell commands from artifact paths.

### D07 — Benchmark explorer
**Priority:** P1 · **Effort:** M/L · **Blocker:** I: agreed read/export format; X: backend statistical analysis if not supplied

Directly useful while Opus benchmarks AEW. Two tabs: **engine performance** (command, scale, runtime, lock time, cold/hot behavior) and **agent quality** (accepted result, repeated investigation, tokens, latency, authority/freshness failures). Compare fixed cohorts and inspect individual trials.

**Acceptance:** task/dataset version, model/config, environment, repetitions, and evaluation method are visible; missing outcomes are not failures or successes by default; microbenchmark speedup is not presented as task-quality improvement; exploratory charts never claim significance without supplied analysis.

A developer can import purpose-built benchmark JSON fixtures now. This is a projection export, not raw AEW DB or storage-file parsing. Live collection is blocked.

### D08 — Paired investigation comparison
**Priority:** P1 · **Effort:** M · **Blocker:** I: two independently identified sources/packets/runs

Apply Grafana-like split exploration to two attempts, two journal states, or two runs. Offer linked scrolling/time controls, with a visible toggle and separate scope labels.

**Acceptance:** each side retains its own identity and errors; a denied right side does not blank or substitute the left; differences are supplied or transparently structural, never inferred applicability; presentation changes do not change underlying query scope.

### D09 — Requirement-to-evidence coverage map
**Priority:** P1/P2 · **Effort:** M · **Blocker:** I: supplied links and coverage judgments; X if coverage evaluation is new

A requirement/acceptance-criterion matrix across plans, attempts, evidence, reviews, and verification. Clicking a cell opens the supporting record or backend-supplied absence reason.

**Acceptance:** partial query coverage is explicit; missing cells do not become “unmet” unless supplied; acceptance and evidence links remain separate; frontend never decides a ticket is done.

### D10 — Context budget anatomy
**Priority:** P1/P2 · **Effort:** M · **Blocker:** I: per-section accounting, selected/omitted/truncated records, packet/delivery identity

Expand v2's packet inspector into a budget breakdown for current constraints, evidence, tool descriptions, historical recall, and other supplied sections. Show omitted reasons where authorized and supplied.

**Acceptance:** bytes and tokens are not interchanged; estimated token counts show estimator/model identity; prepared and delivered totals are distinct; omitted items may be unavailable rather than listed; no disclosure of forbidden-scope candidates.

### D11 — Recall selection comparison
**Priority:** P2 · **Effort:** M · **Blocker:** I: selection diagnostics; X: read-only evaluation/simulation endpoint for genuine counterfactuals

Compare supplied result sets: lexical baseline versus hybrid, budget A versus B, or two projection generations. Show rank movement, overlap, expansion status, and evaluation outcome.

**Acceptance:** cached fixture changes are labeled demo; live sliders do not claim to run the real router unless a supported evaluation endpoint responds; backend-controlled ranking is not reproduced in browser code; score scales remain provider-specific.

### D12 — Attempt isolation view
**Priority:** P1 · **Effort:** M · **Blocker:** I: origin/visibility/binding metadata and permission-safe summaries

A compact lane view for concurrent worktrees, attempts, private observations, and explicitly shared published knowledge. Excellent as both an operator view and an integration regression fixture.

**Acceptance:** unauthorized records never enter payloads/cache/DOM; unknown origin stays unknown; identical titles/IDs cannot merge across scope; shared knowledge retains originating revision and environment; project switch clears privileged cached views.

### D13 — Knowledge evolution with a “what changed?” lens
**Priority:** P2 · **Effort:** M · **Blocker:** I: supplied supersession, contradiction, and environment-change links

Strengthen v2's evolution mode: show claim → challenged claim → new evidence → replacement, with reason/detail comparison. Link the precise changed dependency or source where supplied.

**Acceptance:** changes in wording do not imply changed truth; old records remain inspectable where permitted; red/green is never the only status cue; unknown relationship types remain visible.

### D14 — Knowledge reuse trail
**Priority:** P2 · **Effort:** M · **Blocker:** I: packet inclusion receipts, citations, downstream links; X for evaluated contribution

For a lesson, show contexts it entered, subsequent explicit references, and independently scored outcomes. This answers whether retained knowledge is reaching work without inventing learning benefits.

**Acceptance:** “supplied,” “cited,” and “evaluated benefit” stay separate; no “this lesson fixed five tickets” from inclusion counts; duplicates/retries do not inflate supplied-run counts.

### D15 — Failure-pattern investigation board
**Priority:** P2 · **Effort:** M · **Blocker:** I: backend-supplied signature groups, matches, and source differences

Enhance Failure Archaeology with columns for failure signature, attempted approaches, changed conditions, and successful evidence. Useful for C/Python failures, compiler diagnostics, API mismatch, and tool outages.

**Acceptance:** signature matches show their supplied basis; matching failures across different environments are qualified; frontend does not classify new failures from prose; unsuccessful approaches remain conditional, not permanent prohibitions.

### D16 — Capability and airgap readiness view
**Priority:** P2 · **Effort:** M · **Blocker:** I: approved capability manifest and health/validation receipts

Display the tool/model/provider version, intended role, validation receipt, and availability for the selected run/environment. Compare manifests between runs. Read-only, with no installers or shell execution.

**Acceptance:** configured is distinct from successfully tested; unknown is not available; last validation environment/time is visible; provider outage is shown as degraded recall, not lost project truth.

### D17 — Portable investigation dossier
**Priority:** P2 · **Effort:** M/L · **Blocker:** I: versioned export contract; X: authorization/redaction/retention policy

A locally viewable, read-only report of selected work, reasons, sources, and comparisons. Valuable for airgap transfer and design reviews. Build the viewer from explicit fixture exports now.

**Acceptance:** bounded import size and schema checks; no imported executable HTML; timestamps/identities persist; incomplete/redacted sections stay explicit; imported data remains in a clearly separate offline viewer, never merged into live AEW truth. A bundle hash proves integrity relative to that hash, not issuer authenticity; authenticity requires a separate signed/validated contract.

No silent browser persistence of evidence. Real exports require an approved policy; a “download everything” button is not implied authorization.

### D18 — Guided operator training worlds
**Priority:** P2 · **Effort:** M · **Blocker:** none for fixtures

Turn selected worlds into exercises: find why a ticket is blocked; locate a superseded lesson; spot mixed revisions; explain a failed resume; compare accepted and rejected benchmark trials.

**Acceptance:** answers are fixture-authored; navigation stays read-only; demo mode is unmistakable; each exercise ends with exact source references rather than a generic success toast.

### D19 — Recorded temporal provenance
**Priority:** P3 experimental · **Effort:** L · **Blocker:** I/X: versioned relation projections and snapshot availability

Scrub a bounded provenance graph through supplied snapshots to watch evidence, contradictions, and integration links appear. More useful than an unbounded animated “project universe.”

**Acceptance:** graph shows recorded snapshots only; not-yet-known differs from not-applicable; absent history is labeled; animation respects reduced-motion settings; equivalent relation-list navigation works.

### D20 — Contract evolution explorer
**Priority:** P2 · **Effort:** M · **Blocker:** none for fixtures; I: actual supported schema/capability versions

Compare fixture schema versions and render outcomes. Surface new enum values, removed capabilities, changed required fields, and adapter compatibility cases. Record unresolved fields in a backend question ledger.

**Acceptance:** failure path is exact; unknown fields/enums do not look like healthy state; frontend schema acceptance is not backend contract approval; tests reuse the actual API boundary parser.


### D21 — Execution guarantee labeling
**Priority:** P0/P1 · **Effort:** S/M · **Blocker:** I: backend guarantee class, validation receipt/environment, guarantee freshness

Every Run detail should display what isolation/containment guarantees actually held. Reuse the same component in Run comparison and the Flight Recorder.

Example dimensions:

- filesystem containment;
- process containment;
- network isolation;
- worktree/workdir separation;
- harness edit restrictions / defense-in-depth controls.

**Acceptance:** `UNKNOWN`/`UNLABELED` is explicit and visually prominent; frontend never promotes configuration into a guarantee; validation environment/time/receipt are visible; old receipts can be shown as stale/unknown-currentness rather than silently current.

Optional project-level summary is permitted only from a coherent backend-supplied aggregate snapshot. Do not compute a dashboard "security score."

### D22 — Consequential observations board
**Priority:** P2 · **Effort:** M · **Blocker:** I: F17 observation/disposition projection; X if trend/cohort computation does not already exist

Read-only board for consequential observations and supplied dispositions such as `awaiting_disposition`, `accepted_open`, `known_limit`, `resolved`, and `superseded`.

Useful presentation:

- open count;
- age distribution / oldest unresolved;
- new and resolved over time;
- affected trust surface/component;
- exact disposition;
- evidence/source links;
- follow-up work/decision if supplied.

**Acceptance:** counts/trends do not become an implicit quality score; `accepted_open` share is descriptive only; silent closure is impossible when disposition/evidence are available; missing consequence assessment remains visibly missing rather than inferred harmless.

### D23 — Judgment queue and stage-intent inspector
**Priority:** P1/P2 · **Effort:** M · **Blocker:** I: F15 ActionProjection, stage-intent, anomaly and recovery read projections

Show pending judgment-bearing items, interrupted/dangling stage intents, anomalies requiring disposition, and exactly what the Lead was shown.

Reuse D01 investigation shell, Why, Evidence, and revision/scope components.

**Acceptance:** browser never decides that judgment is required; resolved/policy-resolved/mechanical work is distinct from genuinely judgment-bearing work; interrupted intents remain traceable after recovery; dangling intent does not imply the underlying action occurred.

### D24 — Fanout tree / execution budget
**Priority:** P1 · **Effort:** M · **Blocker:** I: registered invocation/helper relationships, budget, execution class, active/ended state

Companion to D05 Run Flight Recorder and D12 Attempt Isolation. Render child invocations/helpers against backend-supplied budget and depth.

Where supplied, distinguish:

- AEW invocation;
- harness-native helper;
- provider/internal child;
- unknown/unregistered execution.

**Acceptance:** budget and observed count are separate; missing/unregistered children remain explicit; tree order/parentage comes from supplied relations rather than timestamp proximity; large fanout is bounded/virtualized; frontend does not claim to have enforced a budget.

### D25 — Seeded bad-review training world
**Priority:** P1/P2 · **Effort:** S/M · **Blocker:** none for fixture mode

Extend D18 with adversarial review-quality fixtures. Include both suspicious and legitimate short reviews.

Example pair:

- 30 seconds, zero findings, substantial change, no evidence opened;
- 42 seconds, zero findings, tiny mechanical change, all required evidence inspected.

Add variants for stale revision, partial coverage, missing required evidence, and misleadingly broad review claims.

**Acceptance:** success requires identifying the evidence-supported suspicious case and explaining why; duration alone is never the answer key; scenario ends with exact source/revision/coverage references; measure operator accuracy as well as time.


## 6. Creative experiments worth prototyping

These are optional experiments after the shared shell and fixture controls exist. Give each a short prototype budget and an explicit usefulness test.

### “Show me the disagreement”
A split view showing two contradictory claims, their evidence, source environments, and supplied resolution. A stronger human experience than a contradiction badge. Reuses D06/D08/D13; live blocker is the contradiction projection.

### “Follow this evidence forward”
Start from one artifact and follow supplied references to review, verification, integration, and subsequent reuse. Reverse provenance makes retained evidence feel useful. Bounded traversal and permissions are required; no inferred edges.

### Incident rehearsal
Replay a supplied crash/recovery scenario with a timeline of durable transitions and ambiguous side effects. Teach why AEW reconciles before retrying. This is a demo/training tool; it cannot execute recovery or simulate real workflow legality independently.

### Context-pressure replay
Animate recorded compaction and packet delivery, showing which sections survived, expanded, or were omitted. Preserve a static accessible table. Data comes from fixtures or recorded packets, never an invented model-attention heat map.

### Evaluation “blind compare”
Temporarily conceal model/provider labels while a reviewer compares already supplied outputs and evidence. Presentation-only concealment can be built now. Persisting ratings, changing scoring, or assigning review authority is X and needs its own contract.

### Read-only operator briefing
A deterministic briefing built from backend-supplied change records: what changed, what needs attention, what evidence arrived, and what remains unknown. Do not make an LLM summarizer the source of workflow conclusions. A generated narrative is advisory and requires a separate service if desired.

Do not invest in a 3D galaxy, fictional attention visualization, model/persona leaderboard, browser memory engine, or dashboard-side agent orchestration. They either add little investigative value or create authority/measurement problems.

## 7. Shared contract questions for ticket sorting

Treat this as a read-projection question ledger for the designer. Avoid forcing the backend to imitate a preferred screen.

1. Which identities distinguish project, repository, worktree, work, attempt, invocation, run, and artifact?
2. What revision/root/watermark binds each response? Is a consistent multi-resource snapshot supported?
3. Can historical revisions be fetched? What is the explicit unavailable result?
4. What distinguishes denied, missing, pruned, unsupported, stale, and temporarily unavailable?
5. Which statuses have supplied reason codes, source links, and policy references?
6. Do relation queries declare bound/truncation/continuation/completeness?
7. How are artifact excerpts authorized, range-bounded, pinned, and verified?
8. Are packet preparation, delivery acknowledgment, citations, and later evaluation recorded separately?
9. Which recall exclusions can be disclosed without revealing inaccessible records?
10. What benchmark export supplies cohort/version/config/trial/evaluation provenance?
11. Which tools/CLI command templates are validated and safe to copy?
12. Does production support polling only, or another read transport? Do not invent streaming to implement a timeline.
13. What capabilities govern exports and developer diagnostics?
14. Which frontend operations are presentation transformations versus backend semantic judgments?

Illustrative response metadata may include schema version, scope binding, snapshot reference, generated time, source references, capability declaration, coverage/truncation, and diagnostic reasons. These are **contract requirements to discuss**, not a new durable AEW schema or mandated field names.

## 8. Original implementation-order recommendation

**Historical ordering:** superseded by the [reconciled milestone backlog](../dashboard-workbench-milestones-and-tickets.md). Retained below to preserve research context.

### First batch: immediately useful
D01 shell + D02 scope/revision + D03 scripted worlds + D04 local checks. Add D21 execution-guarantee fixtures and D25 seeded bad-review worlds early because both expose known failure modes cheaply. Start the Knowledge Journal using these shared components. This avoids building a polished flagship on inconsistent cache and navigation behavior.

### Second batch: valuable during backend validation
D07 benchmark explorer, D06 evidence reader, existing Timeline work and D05 flight-recorder prototype. Fold D24 fanout-tree fixtures into the Flight Recorder rather than creating a separate execution browser. Agree a small benchmark projection with the benchmarking owner when available; use fixture inputs meanwhile.

### Third batch: deepen the workbench
D08 comparisons + D10 context anatomy + D12 isolation view. Extend existing Why and provenance inspectors rather than introduce parallel components. D16 should reuse the same guarantee-label component as D21.

### Fourth batch: backend-semantics-dependent operational surfaces
When their read projections exist, add D23 judgment/stage-intent inspection (F15) and D22 consequential-observation tracking (F17). Their fixture UX may be prototyped earlier, but frontend code must not invent those semantics.

### Fifth batch: controlled exploration
D09 coverage, D13 evolution, D14 reuse, D15 failures, D17 dossier, and selected experiments. Build only those that demonstrate operator value or resolve a concrete integration risk.

For each ticket require: problem and operator question; fixture demo; read-projection requirements; live blockers; unknown/error states; authority boundary; boundedness; accessibility; relevant regression evidence. “UI done against fixtures” and “live integration accepted” are separate completion gates.

## 9. Performance, safety, and evaluation

### Frontend engineering checks

- Scope query keys by every input that changes the response, including permission context when relevant. Clear inaccessible cached data on identity/authorization changes.
- Never use previous-data placeholders across different project/attempt scopes. Same-scope pagination still needs visible transitional state and correct action/link bindings.
- Debounce/cancel obsolete requests; test delayed responses after selection changes.
- Bound graphs and paginate/virtualize long streams; avoid subscribing every detail panel to the entire graph state.
- Disable node/edge deletion, connection creation, and mutation callbacks in read-only graphs. Customize keyboard instructions so they do not advertise editing.
- Keep a relation-list alternative, useful both for accessibility and dense graphs.
- Treat source prose, logs, links, filenames, and diagnostic fields as untrusted display data. Use existing sanitization/CSP policy and test external resource behavior.
- Keep diagnostic and export payloads permission-aware. Do not expose raw credentials/prompts in a broad developer drawer.
- Prefer existing dependencies. New packages need a demonstrated role, pinned assets, and an airgap-compatible installation path.

- Guarantee components must default to `UNKNOWN`/`UNLABELED` when the backend claim or validation receipt is absent.
- Fanout views must display backend-supplied budget/coverage and never infer hidden children from timing or cost anomalies.
- Observation dashboards must not map lower unresolved counts directly to success colors or a health score.
- Training worlds must include control cases so operators learn evidence-based suspicion rather than simplistic heuristics.


### Measure whether the dashboard helps

Use operator tasks, not number of pages built:

- Time and accuracy finding why a work item is blocked.
- Time locating exact evidence and its source revision.
- Accuracy detecting a stale/superseded claim.
- Accuracy distinguishing prepared versus delivered context.
- Accuracy spotting cross-attempt or mixed-revision data.
- Time locating the individual benchmark cases behind an aggregate regression.
- Keyboard completion and navigation errors.
- Rendering latency, request count, memory/bundle growth on agreed large worlds.

Do not use fast task completion alone: a dashboard that confidently leads the operator to the wrong conclusion is a regression. Record incorrect authority/freshness interpretations as failures.

## 10. Sources

Primary sources checked during this review; current documentation is not a pinned deployment guarantee.

- [S1] [Grafana Explore: split, time synchronization, inspector, links](https://grafana.com/docs/grafana/latest/visualizations/explore/get-started-with-explore/)
- [S2] [Playwright Trace Viewer](https://playwright.dev/docs/trace-viewer)
- [S3] [OpenTelemetry tracing API and links](https://opentelemetry.io/docs/specs/otel/trace/api/)
- [S4] [Langfuse experiment comparison](https://langfuse.com/docs/evaluation/experiments/compare-experiments)
- [S5] [MSW network errors](https://mswjs.io/docs/http/mocking-responses/network-errors)
- [S6] [MSW delay](https://mswjs.io/api/delay)
- [S7] [TanStack Query keys](https://tanstack.com/query/latest/docs/framework/react/guides/query-keys)
- [S8] [TanStack placeholder query data](https://tanstack.com/query/latest/docs/framework/react/guides/placeholder-query-data)
- [S9] [React Flow accessibility](https://reactflow.dev/learn/advanced-use/accessibility)
- [S10] [React Flow performance](https://reactflow.dev/learn/advanced-use/performance)
- [S11] [Playwright visual comparisons](https://playwright.dev/docs/test-snapshots)
- [S12] [Storybook accessibility testing](https://storybook.js.org/docs/writing-tests/accessibility-testing)

The supplied v2 handoff is the authority for the existing frontend inventory. The ticket ideas and priorities are this review's recommendations. The AEW memory research from the preceding conversation provides the ownership boundary; the subsequently approved design itself was not attached or inspected.

