# W06 — Recorded execution, fanout and control receipts, revision 1.1

## Outcome and authority boundaries

Deliver W06-01–03 as one compact, demo-only investigation: failed removal → discovery → prepared context → successful retry. Inspect supplied events, typed execution relationships, budget observations and control receipts without generating causal conclusions.

Baseline: merged W05 `da46807d4fb35ec742f042425c347cd480ba8f65`, existing stable frontend checkout, branch `feat/aew-dashboard-w06`. Preserve local files and other checkouts. Production behavior, accepted API 0.1.2, existing preview wire contracts, generated accepted types and dependency lock stay unchanged; no new dependencies.

**T3/outbox firewall:** Execution preview events, ordinals, lane classes and trace relationships are presentation-fixture semantics only. They do not define the future transaction-outbox/event schema, ordering authority, correlation model or retention contract. Live/backend adoption is blocked on the accepted **T3 event/outbox design** and must use an explicit adapter/projection. Fixture familiarity is not backend acceptance.

**Project-only visibility:** W06 `visibility_scope` equals the selected project identity. This is a schema extension point, not an authorization system. No scope selector, cross-project aggregation, membership policy or generalized multi-scope behavior. Cross-preview opaque scope fields are exact provenance bindings, never permission grants. Unexpected W06 project-visibility values reject.

**G7/F7 budget firewall:** Budget observations do not define cost-ledger fields, `budget.remaining`, enforcement or `DispatchDecision`. Accepted G7/F7 interfaces require an explicit adapter/projection.

Exclude live monitoring, replay, reconstructed historical state, backend work, enforcement, containment implementation, Work redesign, benchmarks, ingestion, knowledge creation and W07 topic/evolution. Create no Engine work records.

## Recorder and density

Demo Runs and invocation details offer **Inspect recorded execution**. Filter by supplied invocation and optional owned harness run. Several matching fixed traces require explicit selection, never newest/first selection. `/execution` is the shareable workspace.

Two permanent panes on desktop; below 1024px Results/Detail switching keeps selected identity visible. Events/Fanout results and Details/Controls/Provenance inspector show one activity each. Events use discrete lanes on desktop, ordered lane-labeled rows on phone and a semantic table alternative. Known fixture lanes: invocation/run activity, tools, Evidence publication, reviews, reported transitions and context receipts. Unknown values retain raw warnings.

Choosers, events and execution tables use 50-entry cursor pages, replacing rather than accumulating. Selection survives page/filter/display changes; exact details resolve separately. Distinguish off-page supplied selection from unavailable selection. Previous/Next recorded event navigates supplied records only; no slider/playback or inferred between-event state.

Order by supplied trace-local ordinal ASC, event ID ASC. Missing ordinals form a final **Unordered** group, ID ASC. Source/observation timestamps stay separately labeled. Stable ties imply neither simultaneity nor causation. Show supplied coverage, gaps and retention; ordinal discontinuities alone imply no missing events. Reported transitions establish neither legality nor authoritative historical state. Captured invocation status is labeled as source-capture status, never status at a selected event.

Desktop selection preserves keyboard position in results. Phone and explicit detail navigation focus the heading below the sticky header. Shared tabs retain focus on arrow/Home/End navigation. Close restores entry/heading focus. Reuse system typography, themes, borders, native controls, natural scrolling and safe rendering; no third inspector.

## Typed fanout, budgets and controls

Fanout is a companion hierarchy with a flat semantic table. Every relation supplies kind, typed endpoints, source and provenance. The hierarchy is a view over supplied typed relations, not their canonical meaning. Branches label their relation kind. Registered child invocation is delegation, not process custody; process spawn differs from delegation; harness helper launch is harness-reported; provider suboperations retain coverage limits. Trace correlation stays separate, never parentage or causation. Unknown/process references remain terminal. Never infer ancestry, registration, custody or influence from timestamps, adjacency, work or similar IDs.

Expansion is explicit, bounded to 3 levels, 24 displayed nodes and 80 supplied edges. Cycles, unavailable parents, unknown/unregistered executions and incomplete coverage remain explicit. Only loaded supplied relationships are displayed; absence of a child does not establish none exist.

Configured budget, observed/active/unattributed counts, depth and reported enforcement stay separate with units, measurement scope and completeness. No global counts from loaded pages; browser-loaded counts are labeled. No arithmetic enforcement result.

One reusable Controls presentation serves recorder, disclosed demo invocation details and W04 comparison. Concealed sections make no reads. Inventory/pin Engine vocabulary before fixtures and record source commit/file hashes in the canonical artifact. Reuse `filesystem` (`os_readonly_roots`, `workdir_separation_only`), `process_ownership` (`pid_namespace`, `job_object`, `process_group`), `network` (`not_provided`), mechanism and `self_test` meanings. Process ownership is not stronger process containment; read-only roots are filesystem integrity, not confidentiality or network isolation. Do not reproduce fallback logic.

Configured/available/authorized/active/tested remain distinct. Environment/profile, validation time, currentness and provenance are supplied. Missing values show UNKNOWN/UNLABELED or **No validation receipt supplied.** Absence does not prove validation never occurred. Age invents no expiry/currentness. Existing currentness/receipt vocabulary is reused only when claim meanings match; frontend-only extensions are PROVISIONAL with adoption questions. No installers, credentials, storage paths or executable arguments.

## Cross-navigation and contracts

Evidence events use supplied W05 association IDs. Packet events replace recorder with the shared W04 inspector, bound exactly to owning source/run/snapshot. Back restores trace, view, filters, cursor, selection, scroll and originating focus. Unmapped references remain unavailable; direct links offer Runs. Canonical decisions remain references to authoritative records. Prepared context, delivery acknowledgment, output citation and evaluated benefit stay distinct.

Register Execution preview 0.1.0 PROVISIONAL: canonical JSON, strict runtime schemas/inferred types, fixture manifest/SHA-256, firewalls and vocabulary inventory. Extend Contract Playground and both fixture adapters using shared projectors. Trace source includes fixed snapshot/capture/project/work/root/source revision/environment/project visibility. Coverage includes lane/completeness/supplied gaps/explanation/retention. Events include IDs/nullable ordinals/timestamps/lane/kind/summary/reasons/exact execution/references. Executions/relations include class/registration/invocation/run/typed endpoints/source/provenance/completeness. Budgets include policy/units/scope/counts/depth/enforcement. Controls/receipts include exact execution/source/snapshot/environment/result/currentness/time/provenance. Locators bind origin digest/case/record/item/project to exact target contract/case/reference/source/snapshot/run.

GET/HEAD demo proposals under `/api/preview/execution/v0.1`:

- `/traces`: case, exact work/invocation/run filters, cursor, limit ≤50; run requires invocation.
- `/traces/{source_id}`: exact fixed metadata.
- `/traces/{source_id}/events` and `/events/{event_id}` beneath that trace.
- `/traces/{source_id}/executions` and `/executions/{execution_id}` beneath that trace.
- `/traces/{source_id}/executions/{execution_id}/controls`.
- `/traces/{source_id}/executions/{execution_id}/receipts`: 50-entry pages.

Cap lane summaries/guarantee dimensions at32, budgets at16, detail relations at80; summaries bounded; tool bodies stay Evidence references. Validate invocation/run ownership, trace/snapshot/project, relation endpoints/sources and receipts before caching. Unknown semantics warn; malformed/mismatched structures reject. Denied projections expose no hidden identity/summary.

Cross-preview mappings live in Execution manifest; shared locator/inspector adapters extend presentation without old wire changes. Origin/target cases remain explicit. Bootstrap project first. Reader/validator identity includes digest,dataset/case,project,fixed trace/snapshot,session generation,reader ownership and object/filter/cursor. Retire pending reads on changes; refusal clears owned payloads/validators; ordinary failure retains marked valid data. All W06 reads manual-only; no polling/prefetch/concealed reads. Fixed snapshots never advance silently; valid304 preserves revision/generation.

Copy/reload allowlists trace,event/execution,view/display,filters,cursor,detail tab,inspector locator andcase; no unrestricted return URLs. Historical unsupported links are explicit. Dynamically import all preview code only in demo; HTTP and worker adapters share projectors.

## Story, checkpoints and acceptance

Preserve existing clangd Evidence/Journal/invocation/run/packet/snapshot identities. Add fictional traces/events/helpers and supplied typed relations. Primary trace includes removal failure, compilation discovery, retry preparation/delivery/citation/success. J-05 publishes afterward and remains absent from earlier retry packet. Include supplied recording gap, unknown/unregistered execution and configured-versus-validated controls. Secondary cases: excessive fanout, missing enforcement, relation differences, correlation, partial coverage, cycles, out-of-order timestamps, unordered events, stale/mismatched validation, unavailable capabilities, denied/historical sources, malformed bindings, failed refresh, obsolete responses and hostile summaries.

Four independently reviewable checkpoints: (1) contract/story/vocabulary/mappings/ownership/projectors/backend questions; (2) recorder/lanes/table/coverage/detail/navigation and compiled desktop/phone inspection; (3) typed fanout/budgets/shared Controls/cross-navigation; (4) validation/measurements/committed-source freeze/independent review.

Run pinned Node22 offline gate, artifact/type/lint/unit/component checks, both builds, production exclusion, W01–W05 browser regressions and CHROMIUM_PATH-capable W06 suite. CI exercises worker and HTTP with service workers blocked. Verify ordinal/time/gap boundaries, project-only rejection, relation kinds/correlation/cycles/bounds/source attribution, budgets without ledger/enforcement, Engine vocabulary/provisional metadata, configured/tested, missing/stale/mismatched receipts, paging/selection/cross-binding/cache/obsolete/refusal/304/concealed reads. Exercise both themes, desktop/phone, keyboard, 200% zoom, long/hostile content under CSP. Premium audit and shared design/behavior contracts remain gates.

Measure requests/rendering/DOM/cache bounds against frozen W05, disclose workflow differences; no timing SLA. Commit runtime first. Build/test a clean detached checkout of that exact commit. Freeze source/tree/runtime identities, complete build manifests, commands/screenshots/measurements/questions; verify source/build unchanged afterward.

Independent reviewer completes desktop and phone clangd tasks using only product UI and records IDs, steps, outcomes, coverage, typed relations, budget/enforcement/control/receipt distinctions, exact Evidence/packet navigation and restored position. Demonstrate correlation is not custody/causation, configured controls are not validated guarantees and observed fanout is not enforcement. No time target or developer-tool substitute. Review gates frontend fixture acceptance; backend/live remain blocked on T3 and Engine projections; G7/F7 requires adapter.

Operator approval record is bound to this revision/digest following the explicit implementation request. Preserve W05 acceptance and deferred density review in `docs/implementation/future-work.md`.
