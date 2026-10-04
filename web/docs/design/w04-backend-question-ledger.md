# W04 backend questions

All answers/adoption are PENDING. Frontend fixtures are proposals, not backend commitments.

| ID | Owner role | Question / live blocker |
|---|---|---|
| W04-Q01 | Engine projection owner | Which immutable invocation snapshots exist, how are they identified and retained, and how is historical unavailability represented? |
| W04-Q02 | Context/authorization owner | Which source-summary excerpts, packet excerpts, omitted candidates and receipt details are authorized per projection? Filter payloads before delivery; fixture denial tests do not prove backend authorization. |
| W04-Q03 | Context router owner | What identifies packet association, prepared content/fingerprint, source revision and run binding? Do not resolve by similar names. |
| W04-Q04 | Harness/receipt owner | What do acknowledgment, citation and evaluated benefit receipts guarantee? How are conflicts and partial histories supplied? None implies attention. |
| W04-Q05 | Context accounting owner | Which units/tokenizers/estimators/limits are authoritative, and what completeness guarantees apply? Browser counts are not token accounting. |
| W04-Q06 | API owner | Review exact canonical preview version/digest/commit separately before adopting routes/types/parsers; accepted0.1.2 is unchanged. |
| W04-Q07 | M6/W07 knowledge owner | Preserve distinct reusable packet/receipt concepts. Later decide canonical-reference versus knowledge-record-reference versus subject/topic identity. No Topic contract requested in W04. |

Frontend/domain models render only supplied relations and grouping. They do not infer semantics from text similarity, adjacency or timestamps. Packet/source binding validation is identity checking, not semantic inference.
