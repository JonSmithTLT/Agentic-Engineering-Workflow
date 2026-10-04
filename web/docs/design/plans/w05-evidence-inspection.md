# W05 — Evidence inspection and pinned citations, revision 1.1

## Outcome and boundaries

Deliver W05-01: follow Evidence references, inspect supplied records and bounded artifacts, and copy citations identifying exactly what was viewed. Complete W05-02's capability assessment while preserving unsupported Timeline and Evidence CLI gaps.

Start from merged W04 `211e29c168171201fcce124795b11a22a13b64d7` in the existing stable frontend checkout on `feat/aew-dashboard-w05`. Preserve local files and other checkouts.

Extend the fictional clangd investigation: inspect removal failure, refreshed compilation evidence and opposing evidence behind the conditional lesson. Relate observations to W04's reported retry outcome without generating a causal conclusion.

Evidence IDs remain canonical. A reference/binding has an identity distinct from its target Evidence ID. Future Cases and admitted Lessons have Knowledge identities and reference existing Evidence IDs/hashes; they never copy or replace Evidence. Ordinary Knowledge → Evidence navigation remains valid.

Exclude W05-03–04 benchmarks, image/PDF viewers, downloads/uploads, arbitrary filesystem access, artifact diffs, retrieval, knowledge creation, Work redesign, M6 Capture & Admission, backend implementation and live integration. Accepted API 0.1.2, generated accepted types, both existing preview contracts and dependency lock remain unchanged. No dependencies added. Production retains accepted behavior.

## Experience

Add demo-only Inspect evidence entries to Evidence page/details and connect supplied Evidence references from Journal and comparison/packets through one reusable adapter. Preserve IDs and explicit roles. The `/evidence/inspect` workspace resolves supplied associations, never paths or matching inferred from titles, prose, timestamps or digest resemblance. Several authorized snapshots require explicit selection; fixed references never fall back to current content. Choosers/artifact lists use semantic tables, ID ordering, 50-entry cursor pages and labeled phone rows.

Record / Artifacts / Provenance tabs:

- Record uses the accepted display model for supplied claim, result/currentness, body, findings and deviations.
- Artifacts presents associations and one selected bounded excerpt. Desktop list/reader panes become List/Detail below 1024px, with selected identity visible.
- Provenance discloses producer/invocation/run, evaluated snapshot, plan bindings, canonical references and response metadata once.

Reader navigation replaces the originating investigation. Back restores selection, filters, tabs, cursors, scroll and originating-link focus. Direct links offer Evidence as a return destination. Reuse shared tabs, paging, source display, focus, themes, safe rendering and natural scrolling. No third pane or graph. Focus is visible below sticky chrome; announcements are polite.

Support UTF-8 text/code/logs/JSON diagnostics. Preserve line breaks and escape code/log source. Visibly neutralize ANSI, Unicode bidi and other invisible formatting controls through code-point markers; hash/range identity uses original text. Format JSON only for complete valid values; partial JSON remains source text. Markdown uses existing safe rendering without executable HTML or remote images. Unsupported media exposes only authorized metadata and sends no body request. Show supplied truncation, omitted ranges and excerpt scope. Missing material/explanations do not prove absence.

Copy citation includes Evidence ID, association ID when applicable, source/snapshot, artifact ID/revision, supplied full-artifact digest, half-open byte range, supplied line range when available, excerpt digest and pinned link. No body is copied. Excerpt integrity differs from full-artifact integrity: checking a chunk establishes neither whole-file verification, claim truth nor causal benefit.

## Preview contract and read behavior

Evidence inspection preview 0.1.0 is PROVISIONAL: separate canonical artifact, SHA-256 registration, strict runtime schemas, inferred types and fixture manifest; extend Contract Playground.

Reference association supplies opaque reference ID plus origin contract digest/case/record/item/kind/role, target Evidence ID, nullable originating source/snapshot and visibility scope. Resolution supplies exact association/origin binding, authorized target-source associations and completeness. The same Evidence ID can have different authorized mappings at different origins. Fixture manifest supplies explicit adapter mappings without changing Journal/Investigation wire models. Adapter validates returned origin/target against expected binding. Unmapped references remain unavailable. Opaque locators grant no authorization.

Evidence source supplies opaque ID, canonical Evidence ID, fixed snapshot/capture/visibility/revision and an Evidence payload parsed by the unchanged accepted parser. Artifact association supplies source/Evidence binding, artifact ID/revision, authorized name/media/encoding, supplied full digest, nullable size and availability/completeness. Excerpt supplies source/artifact/revision binding, original UTF-8 text, byte/nullable line ranges, excerpt SHA-256, scope/truncation/coverage and next cursor.

GET/HEAD proposals under `/api/preview/evidence/v0.1`:

- `/references/{reference_id}`: case-bound supplied association.
- `/sources`: case, exact Evidence/work filters, cursor and limit up to 50.
- `/sources/{source_id}`: fixed Evidence source.
- `/sources/{source_id}/artifacts`: bounded associations.
- `/sources/{source_id}/artifacts/{artifact_id}/excerpt`: required artifact revision and bounded cursor.

Implementation locator filters allow exact `reference_id` on source collection and exact `artifact_id` on association collection, avoiding full scans on pinned reload. They filter supplied identities, never infer relationships.

Excerpts max 16 KiB UTF-8; character-safe boundaries and original byte ranges before escaping. Verify SHA-256 and all range/identity bindings before caching/rendering. Mismatch hides rejected content. Full digest remains supplied metadata; accepted opaque digests never become storage paths. Denied payloads reveal no hidden names/excerpts/candidates. Exclude prompts, credentials and storage locations. Raw unknown semantics warn; malformed structures reject. Distinguish missing/denied/not-found/historical-unavailable/unsupported/integrity states.

Bootstrap project first. Reader identities isolate digest/dataset/case/project/visibility/session/source/snapshot. Resolution additionally keys reference ID and expected origin. Excerpt identity explicitly includes source ID + artifact ID + artifact revision + cursor/range; revisions are not globally unique. Retire obsolete reads; refusal clears affected payloads/validators; refresh failure retains marked valid data. Fixed snapshots refresh manually only. No intervals/prefetch or concealed reads. Valid 304 preserves revision/generation time. Keep only active excerpt query per artifact; bound DOM and cached bodies.

Copy/reload allowlists reference/source/artifact IDs, artifact revision, tab, cursor and case. No bodies, credentials, arbitrary paths or unrestricted return URLs. Dynamically import preview modules only in demo. Worker and service-worker-free HTTP paths share projectors. Cross-reference adapters change presentation only; future M6 bindings extend details without coupling Evidence ownership to Knowledge Capture & Admission.

## Checkpoints and acceptance

1. Contract/story: explicit mappings, identity/hash checks, projectors and backend questions.
2. Reader: selection/tabs/bounded excerpts/citations, compiled desktop/phone inspection.
3. Cross-navigation: Journal/comparison/packets, Back/copy/reload/focus and scope isolation.
4. Validation/freeze: regressions, production exclusion, measurements and independent review.

Preserve CLANGD-E871/E875/E880, Journal IDs and W04 source/run IDs. Include paged artifacts and unavailable mappings. Test same Evidence across origins/snapshots/visibility and distinct artifacts sharing revision/cursor; binding/hash mismatch, Unicode boundaries/long lines/ANSI/bidi/invisibles; missing/partial/denied/unknown/unsupported/historical/obsolete/304/stale/refresh failure; themes/phone/keyboard/200% zoom/Back/copy/reload/CSP.

Run pinned Node 22 offline gate, artifacts/typecheck/lint/unit/component/production checks, W01–W04 browser regressions and CHROMIUM_PATH-capable W05 suite. CI tests worker and HTTP with workers blocked. Run premium audit; maintain DESIGN/UX contracts. Measure rendering/requests/bounded DOM/cache against frozen W04 without invented SLA.

Independent reviewer investigates on desktop AND phone using product UI only: supporting/opposing references, failure/refreshed compilation artifacts, canonical/source/artifact/range IDs, reopened citation, restored origin. Record steps/IDs/outcomes/citation checks/usability failures; demonstrate excerpt/outcome does not prove coverage or causation. Freeze commit/digest/commands/screenshots/measurements/findings/questions. Frontend fixture review gates acceptance; backend adoption/live integration remain pending.

Persist factual operator approval against plan digest after approval. Update milestone status, preserve W04 merged acceptance and create no Engine work records. W05-02 records missing accepted lifecycle transitions/read-only Evidence CLI; no fabricated timeline or speculative command. Backend owners separately settle association authorization, snapshot retention and range/digest/live semantics.
