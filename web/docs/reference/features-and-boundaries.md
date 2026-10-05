# Features and boundaries

| Interface | Production | Demo-only additions |
|---|---|---|
| Core pages | Accepted projection/capability behavior | F0–F11 fixtures and fault states |
| Knowledge | Accepted Records behavior | Journal, supplied evidence roles and bounded provenance |
| Work/invocations | Accepted records and relations | Explicit invocation comparison and packet receipts |
| Evidence | Accepted records | Association-bound source/artifact inspection and pinned excerpts |
| Runs/invocations | Accepted records | Recorded execution, typed fanout and control receipts |
| Developer tools | Excluded | Contract Playground and Scenario Lab |

Preview interfaces are provisional, read-only proposals. Production checks reject their schemas, handlers, fixtures and initialization. Opaque locators are not credentials. No arbitrary filesystem lookup, underlying artifact retrieval, downloads/uploads, raw prompts, credentials, backend mutation or enforcement is added.

Unsupported capabilities remain explicit. Accepted API 0.1.2 lacks lifecycle transitions for a real Timeline; the Evidence CLI supplies ingestion rather than a read-only `show` interface. Queue and historical integrity depend on accepted capability support. Do not fill these gaps with a fabricated timeline or speculative command.

Knowledge Capture & Admission, topics/evolution, T3 outbox and G7/F7 integration belong to separately accepted Engine designs. See [backend questions](backend-questions/README.md) and [milestone plans](../design/plans/README.md).
