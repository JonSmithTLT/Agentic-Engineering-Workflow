# W04 implementation notes

The approved W04-01–03 scope is demo-only. No accepted wire/type/Journal/dependency artifacts changed. Source detail embeds the accepted invocation schema; CURRENT adapters project accepted demo invocations with all absent metadata null and unknown completeness explicit. Collection rows are summaries only. Invocation entry seeds an invocation identity but ambiguous snapshot choice remains explicit.

The identity discovery read is not used as rendered data: it obtains exact snapshot/visibility metadata, clears its temporary payload, then an independent side reader validates the source again before caching. Readers are separated by contract digest, case, dataset, project, source, snapshot, visibility, session and side. Packet/receipt binding validation runs in transport parsers, not just after rendering. Scope refusal clears owned representations and query payloads without clearing the other side or accepted projections.

Packet/source/receipt types, binding functions and ContextReferences are domain modules. PacketInspector is a separate component, not embedded in Comparison. Future supplied relationship inputs can reuse these abstractions; no semantic relationship/grouping is inferred from prose, similarity, adjacency or timestamps. Canonical/knowledge/subject distinctions are explicitly deferred in W04-Q07.

Cursor encoding is a bounded opaque presentation token checked against complete dataset/project/revision/case/route/filter/page-size identity. It survives demo adapter restart/reload; it is not a signed authorization credential. The backend proposal must independently settle live cursor/authorization semantics. Snapshot identity is never inferred from capture times.

Preview commands reuse the pinned Node22 carrier and staged Chromium described in the existing operator docs. Build demo, then run `node --experimental-strip-types scripts/demo-server.mjs` for worker-free HTTP fixtures, or Vite preview mode demo for worker-backed fixtures. W04 browser checks own separate ports4260/4261 and support CHROMIUM_PATH. Existing previews/checkouts are preserved.

The failed-removal and retry fixtures are separate invocations within the fictional A-2 investigation, with runs CLANGD-R-A2-2 and CLANGD-R-A2-4. Retry preparation16:33UTC includes J-04 and CLANGD-E875, before J-05 publication16:40UTC. Later preparation17:00UTC includes J-05 and an acknowledgment but no citation/benefit receipt. Accepted invocation completion does not imply a successful work outcome; the supplied summary and evidence references describe the recorded result.

Frontend acceptance remains pending independent product-UI review. Backend adoption/live integration are not claimed. No Engine suites or work records are created by this milestone.

Fixed-source and packet-page queries opt out of visibility/focus/revision reconciliation and retain their cached representation across inspector navigation. Explicit refresh/retry remains available for source details and failed packet reads. Current displayed sources keep automatic revalidation. The default accepted-query policy is unchanged. Unknown receipt types use the same reusable ReceiptCard and retain every supplied binding and provenance reference.
