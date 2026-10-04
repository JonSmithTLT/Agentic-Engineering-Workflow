# W05 backend questions

All backend adoption and live answers remain PENDING. These are frontend fixture proposals.

| ID | Owner | Question / adoption boundary |
|---|---|---|
| W05-Q01 | Evidence/API owner | How are canonical Evidence IDs, immutable sources, artifact IDs/revisions and snapshot retention supplied? Never resolve fixed links to current content. |
| W05-Q02 | Authorization owner | How are association IDs bound to origin contract/record/item/source/snapshot and authorized visibility? Opaque IDs do not grant access. Filter hidden names/excerpts/candidates before projection. |
| W05-Q03 | Artifact owner | What defines original bytes, encoding, byte/line ranges, omitted coverage, excerpt digest and full-artifact digest? Preview verifies excerpts only. |
| W05-Q04 | Knowledge Capture & Admission owner | Richer claim-level support/counterevidence, evidence basis and admission/evolution receipts extend bindings. Existing Evidence ownership/IDs and ordinary Knowledge → Evidence navigation remain valid. |
| W05-Q05 | Engine/API owner | Accepted API 0.1.2 has no lifecycle transitions. A supplied, separately reviewed transition projection is required before Timeline. No timestamps reconstructed as lifecycle events. |
| W05-Q06 | CLI owner | Current `aew evidence` supports ingestion, not read-only `show`. No speculative command is offered; later supported command requires an allowlisted template and safe quoting. |
| W05-Q07 | API owner | Separately review canonical preview digest/commit before adopting schemas/routes. Worker/HTTP fixture acceptance does not establish live authorization or backend conformance. |

W05-02 is capability assessment only. W05-03–04 benchmarks are deferred until owner-approved export samples exist. No Engine work records are created.
