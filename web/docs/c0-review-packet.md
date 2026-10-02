# C0 review packet: dashboard API 0.1.0

Status: **PENDING main-line review**. No domain implementation approval is recorded.

Canonical artifact: `docs/design/dashboard-api-v1-provisional.yaml` (repository root).
SHA-256: `f956f0b2f1f2de0840667c28301be08b6cc0b462271651a0d3cc9117b6034b70`.
The D0 commit containing this packet is the review commit; record its full ID with acceptance in `c0-approval.json`. Approval must name this exact version, digest, and commit, not the current React shapes.

Companion artifacts:

- `web/src/api/types.ts`: generated using cached openapi-typescript 7.13.0.
- `web/src/api/schema.ts`: Zod runtime validators.
- `web/src/api/contract-version.json`: fixture/conformance version pin.
- `web/src/api/mock/fixtures/F0.json`–`F11.json`: bounded projection worlds, including error/unknown/mixed-revision scenarios and additional F6 pages.
- `web/tests/contract.test.ts`: contract/runtime conformance and boundary checks.

D0 validation and screenshots: `web/docs/validation-d0.md`; reproducible browser report: `web/docs/browser-d0-report.json`. The compiled demo is running locally on `http://127.0.0.1:4173/?fixture=F1`.

## Decisions required from the main AEW owner

1. Accept or amend capability names. Proposal: the Attention view uses `action_projection`; `/attention` remains its read route. History integrity is separately advertised as `integrity`. The core capability set omits deferred metrics, search and graph.
2. Accept or amend `{state, reasons}` capability objects. Four known states: AVAILABLE, UNAVAILABLE, UNSUPPORTED, UNKNOWN. Missing capability means UNKNOWN; future states are explicit unknown warnings. Backend reasons own explanations.
3. Confirm envelope names/schema version, opaque string `project_id` and `control_revision`, UTC `generated_at`, and coherent Overview. Client `last_checked_at` is not a wire field and is updated on valid 200 or 304. Project identity/revision must not encode storage paths.
4. Confirm cursor snapshots: default 100, maximum 250, opaque cursors scoped to route/project/filters/revision, 409 on expiration. No fetch-all route. Confirm which filters the backend supplies before Work explorer implementation. Dot-only IDs need a server-agreed path encoding or alternate lookup shape; the client must not infer identity restrictions.
5. Confirm wire shapes, state vocabularies, reason codes, parent/provenance references and kind naming against Engine contracts. Open semantic strings accommodate future values without assigning conclusions. Work classification/assurance and evidence currentness are verbatim backend values.
6. Confirm queue state, position/sequence, custody, publication mode, base and validation fields. Their display does not decide runnability or publication legality.
7. Confirm History annotation/lineage/currentness representation, integrity roots/audit/backlog fields, and historical-reference warnings. Frontend ages or mixed revisions never establish integrity failure.
8. Confirm endpoint availability and ETag scope, including pagination/filter variants. Cookie scheme/name is illustrative pending integration security design. GET/HEAD only; redirect rejection keeps API fetches on-origin.

## Acceptance procedure

The user relays this packet and canonical artifact to the main AEW agent. Main-line review returns accepted/amended wire representation plus version/digest/commit. Any amendment updates YAML, generated types, Zod, fixtures, pins and conformance together, reruns affected checks, and receives renewed approval.

Record acceptance in `web/docs/c0-approval.json` with reviewer identity, date, reviewed commit, contract version, SHA-256, findings and disposition. Update the conformance assertion from pending to accepted with the reviewed artifact pinned. Until then only generic components, shell and explicitly provisional previews are eligible; D1–D4 remain gated.

Independent frontend review at core freeze is a separate main-line gate; passing mocks does not satisfy it. Live integration and full-system acceptance are separate again.
