# W04 — Invocation comparison and traceable context

Revision 1.0. Operator approved by explicitly requesting implementation of this plan on 2026-10-03. Approval binds this persisted plan's SHA-256 in `w04-approval.json`.

## Outcome and boundaries

Deliver W04-01–03, demo-only: explicit invocation-source comparison, optional harness-run selection per side, and context packet/receipt inspection. Primary investigation: fictional clangd failed removal → refreshed compilation evidence → successful retry. Establish supplied starting context, reported outcomes, and available delivery/use receipts through product UI.

Baseline: merged W03 `86d301b5dc848de095028470b6efcc3b515c420c`. Reuse the existing frontend checkout through its stable AEW-web directory; branch `feat/aew-dashboard-w04`. Preserve local files and other checkouts. No new dependencies. Accepted API0.1.2, generated types, Journal preview0.1.0 and dependency lock remain unchanged; production retains accepted behavior.

Exclude W04-04 packet diffs/replay, W04-05 dedicated isolation views, Work redesign, evidence artifact lookup, retrieval, topic/evolution exploration, knowledge creation, backend implementation and live integration. Comparison isolation is mandatory from the first checkpoint.

## Workflow

Demo Work/invocation detail offers Compare invocations. Work entry supplies an exact work filter; invocation entry preselects the invocation identity for A, leaving any source/snapshot ambiguity explicit. `/compare` is shareable. Both sources are explicit; never infer previous/successful/equivalent sources. Source chooser: semantic table, 50-entry cursor pages, invocation/work/status/source/snapshot/capture UTC. Exact work filter; no remote prose search. Each side optionally selects a supplied harness run; never choose the first implicitly.

Two comparison value columns on desktop; below1024px stack A/B within each field. Keep both source identities visible. Overview renders accepted invocation fields, summary, reasons and selected run fields. Configuration renders separately supplied preview metadata. References renders evidence and packet references. Show differences is presentation-only. Browser differences are labeled Structural comparison; compare scalar values/reference identities and exact rich text without a new diff library. Missing/denied/unavailable is never same/different. Array order does not imply importance; incomplete reference arrays never produce exhaustive membership claims. Changing one side preserves the other; swapping exchanges complete selections.

Opening a packet replaces comparison with one inspector. Back to comparison restores choices/tab/difference filter/scroll/focus. Contents shows supplied sections/references/bounded excerpts and explicit truncation, never underlying artifact reads. Selection & budget shows included/omitted/truncated dispositions, supplied explanations, token/byte units, limits and tokenizer/estimator identities. Receipts separates preparation/delivery acknowledgment/output citations/benefit evaluations, each with exact packet/source/invocation/run/time/provenance. Provenance shows identities/fingerprint/revision/environment/producer/canonical references and disclosed response metadata.

Absent explanation: “No selection explanation supplied.” Absent delivery array: “No delivery receipt supplied.” Neither proves an event never occurred. Prepared, delivered, cited and evaluated benefit are separate claims; no attention/influence/causation inference. Canonical decisions remain references to their authoritative records. “Included in context” references do not establish delivery, use, or benefit.

Preserve palette/system typography/themes/borders/native controls/safe rendering/document scrolling. No third pane/stacked graphs/new graph mode. Shared keyboard tabs, polite selection status, sticky-header-safe heading focus and restored origin focus.

## Preview and reads

Investigation preview0.1.0 PROVISIONAL: separate canonical artifact, strict runtime schemas/inferred types, fixture manifest/SHA-256 registration and Playground selector. Source includes opaque identity, invocation, current/fixed snapshot, capture time, visibility scope and accepted-parser-validated invocation payload. Configuration includes nullable work/source revision, environment, model/provider/profile/card/capability metadata, prompt ID/version/digest and explicitly bound packet associations. Packet includes identity/source/snapshot/preparation/fingerprint/producer/policy/trigger/sections/accounting/canonical references/completeness. Item includes stable ID/section/source reference/revision/disposition/explanation/excerpt scope/truncation. Receipt includes identity/type/state/result/exact binding/time/provenance.

Raw prompts, credentials, unauthorized candidates and artifact bodies are excluded. Omitted metadata must be authorized for the projection. Unknown semantics show raw warnings; invalid structure fails; mismatched bindings never attach by similar names.

Demo GET/HEAD proposals under `/api/preview/investigation/v0.1`: `/sources` with case/work/cursor/limit≤50; `/sources/{source_id}`; `/packets/{packet_id}` with case/required source_id; `/packets/{packet_id}/items` with ownership/section/disposition/cursor/limit≤50. Bounds:32 section summaries,100 receipts with completeness indicators;16KiB excerpt,128KiB collective page excerpts. Additional pages, no accumulation.

Bootstrap project first. Reuse W01 transport with explicit preview policy and independent side contexts keyed by digest/dataset/case/project/source/snapshot/visibility/session generation/side; packet reads inherit owning context. Retire obsolete requests and owned queries. Refusal removes payload/validators; normal failure retains marked valid data. Fixed snapshots manual refresh; displayed current source details10seconds; chooser/packet pages no interval. Hidden views stop interval reads;304 preserves represented revision/generation. Fixed identities cannot advance silently. Allowlisted copy/reload restores choices/runs/tabs/filter/inspector/pages/case without extending accepted API queries. Unsupported historical links explicit.

Dynamic demo-only UI/registration/schema/fixture/handlers; shared projectors support worker and worker-free HTTP adapters. Production checks reject preview leakage.

## Delivery and acceptance

Checkpoints: contract/story/bindings/ledger → comparison/navigation + compiled desktop/phone inspection → bounded packet/receipts/provenance → validation/freeze/independent review. Each checkpoint is independently reviewable/revertible. Production exclusion is the rollout boundary.

Story uses existing work/evidence/decision/Journal identities with distinct invocation/source/run bindings. Retry context predates J-05 publication and must exclude it; later-ticket packet includes published J-05, acknowledgment and no evaluated benefit. Also exercise parallel agents, missing/partial/contradictory/unknown/denied/not-found/historical-unavailable/malformed/stale/refresh failures/obsolete responses/hostile content.

Run pinned Node22 offline gate, artifact/type/lint/unit checks, production exclusion, W01–W03 regressions and CHROMIUM_PATH-capable W04 suite. CI verifies worker and HTTP modes, with workers blocked in HTTP checks. Cover independent validators/failures, same IDs across scopes, late responses/304/hidden reads/bindings/raw prompt rejection; themes/phone/long/keyboard/back/copy/reload/200%zoom/CSP. Run premium audit and maintain DESIGN/UX ownership. Measure render/requests/DOM bounds against frozen W03 without invented timing guarantees. No Engine suites locally.

Independent reviewer completes failed removal → successful retry on desktop AND phone using product UI only, recording source/invocation/run/packet IDs, starting context, outcomes, receipt availability, canonical references, steps and usability failures. Later task demonstrates inclusion/acknowledgment does not prove benefit. Freeze commit/digest/commands/screenshots/measurements/findings/backend questions. Independent review gates frontend fixture acceptance; backend schema adoption/live integration remain separately pending.

Backend owners must settle snapshots, authorization, accounting, immutable identities and receipt guarantees before live adoption. Update milestone/register facts, not Engine work records.

Designer clarification: packet/receipt/source models remain reusable independently of comparison. No browser-inferred relations/groupings from prose, similarity, timestamps or adjacency. Future canonical/knowledge/subject reference distinctions remain a backend question, not W04 wire fields or Topic UI.
