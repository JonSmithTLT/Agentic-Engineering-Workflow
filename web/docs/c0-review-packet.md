# C0 resubmission: dashboard API 0.1.1

Status: **PENDING renewed main-line review**. D1–D4 remain gated.

Canonical artifact: `docs/design/dashboard-api-v1-provisional.yaml`.
SHA-256: `3da20f18768d34bef9ccf15fcb65c24cefd2ca73cfc77e6cada8a586f88a0dc4`.
The commit containing this packet is the candidate review commit. The reviewer must return its full ID with this exact version and digest. No acceptance is inferred from fixture or browser results.

The previous review is retained unchanged in `c0-review-main-line.md`: Claude's **AMEND** of version 0.1.0 at `59081d0136bba947d645c2ec60132e5ca7e12e1a`, checked against engine `main` at `91c0d98`. `c0-approval.json` records that disposition separately from the pending 0.1.1 candidate. Accepted decisions 2, 3 and 8 are preserved; decision 1's capability-key amendment is applied.

## Finding disposition

| Finding | Amended representation and evidence |
|---|---|
| C0-1 | `risk_class` integer 0–4/null; accepted `plan_revision`/null; scalar assurance dropped. Add mutating, archived, blocked_by, parent children/rollup and existing integration facts. Engine work state vocabularies stay open. |
| C0-2 | Capabilities accept new keys as `{state,reasons}`. Unknown names/states display raw warnings without triggering new requests. F11 and component/conformance tests cover this. |
| C0-3 | Unfiltered `/work` contains hot work plus at most 20 recent archived units. Older finished work requires explicit DONE or CANCELLED state filtering. Declare work state/kind/parent, history kind/since/until and evidence work filters. F3 and mock-server tests exercise the distinction. |
| C0-4 | IDs use the server-declared path-safe pattern; cursors are a separate opaque string. Hot cursor snapshots expire on control revision change (409). History snapshots pin starting manifest count and survive appends/revision changes. F7 tests traverse 50,000 initial entries after two appends, then see the appended entries in a new traversal. |
| C0-5 | History is manifest metadata with sequence/hash/trust source and relation links, no currentness or storage path. Detail annotations are a list. Archived lookup preserves the moved parent. Integrity roots are structured; the future P2c shape is explicitly provisional and its capability stays UNSUPPORTED. Overview includes recent ≤20 and backend open/done/cancelled counts. |
| C0-6 | Remove Queue schemas and `/queue`. Keep queue capability UNSUPPORTED until M4/M5. F5 instead uses today's Work integration status/commit/commit_ready_seq. No queue state, custody or publication semantics are invented. |
| C0-7 | `/runs` returns invocations with engine role/status and nested observed harness runs. Manual invocation with an empty run list is covered. Entity links target INV identities; a harness-run ID does not invent an invocation route. |
| C0-8 | Reason codes remain unrestricted strings; messages are displayed without deriving conclusions. Evidence bindings explicitly project evaluated snapshot, accepted plan binding and curated producer metadata; storage paths and credentials are omitted. Main-line integration still owns the reason-code registry. |
| C0-9 | 404 is documented only for detail routes; 409 only for hot collections. Coherent composite wording applies only to Overview. History and annotation cursors use 400 for invalid/scope-mismatched cursors, not expiry. |

## Two boundedness details requiring explicit confirmation

1. Parent `children` is a bounded preview of at most 250 hot/archived IDs, with `children_truncated: boolean`. The backend `rollup` covers all children, including those beyond the preview. The Work list's parent filter is the traversal interface; older archived children require explicit DONE/CANCELLED state filters as well; no count is computed from a truncated preview. Please accept or amend this representation.
2. A historical record can have arbitrarily many annotations. Propose detail query parameters `annotations_limit` (default 100, maximum 250) and `annotations_cursor`, plus `annotations_next_cursor` on the response. Pin the starting manifest count so later annotations do not invalidate traversal. This keeps the required annotation list honest and bounded. The demo models annotation pagination; the production implementation remains main-line integration work. Please accept or amend these names and snapshot rules.

Nullable manifest fields are normalized to explicit null where absent in the underlying entry. `source` is mandatory on every historical projection. `evaluated_snapshot` exposes base revision, relevant-input fingerprint and artifact digests; workspace identity, paths, producer credentials and arbitrary execution-profile fields stay off the wire. These curated projections also need confirmation in renewed shape review.

## Companion artifacts and checks

- `web/src/api/types.ts`: generated with cached openapi-typescript 7.13.0.
- `web/src/api/schema.ts`: strict Zod runtime validation; semantic strings remain open.
- `web/src/api/vocabulary.ts`: known values from the review, plus observed harness statuses checked against `91c0d98`; no reason-code registry.
- `web/src/api/contract-version.json` and F0–F11 pin this version/digest.
- F4 keeps future P2c examples in `provisional_responses`, separately from available responses; queue and integrity are UNSUPPORTED in every baseline world.
- `web/tests/contract.test.ts` checks canonical/runtime conformance, version pins, removed shapes, path-free bindings, known vocabularies and route statuses.
- `web/tests/mock-projection.test.ts` checks default/explicit archive scope, backend filters, bounded active paging, hot cursor expiry, stable history/annotation paging and representation-based ETags at unchanged revision. These are mock-server tests, not Engine adapter verification.

Current validation and its precise scope are in `validation-c0-amend.md`. The same separately repaired immutable SPT builder is consumed; no dependency/lock/cache change accompanies these amendments.

## Renewed acceptance

The user relays this packet and artifact-bearing commit to the main AEW agent. Return disposition, reviewer/date, engine baseline, exact candidate commit, contract version and full SHA-256, with any amended fields. Acceptance must be recorded against that frozen object in `c0-approval.json` before domain expansion. Further amendments update YAML, generated types, Zod, fixtures, digest pins and affected checks together.

This is contract resubmission only. Independent frontend review at core freeze and live integrated-system acceptance remain separate gates.
