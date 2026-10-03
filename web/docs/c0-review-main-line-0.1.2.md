# C0 main-line review: dashboard API 0.1.2 (mechanical diff)

|  |  |
| --- | --- |
| Candidate commit | `322301d1200dce54d31a54348dd15ba7a71c9376` (branch `feat/aew-dashboard-readonly`) |
| Contract | `docs/design/dashboard-api-v1-provisional.yaml`, version `0.1.2` |
| SHA-256 | `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691` (verified at the commit and in the worktree) |
| Diff base | `7b0177b76a919e019d2051adff8f7616ae6c2fda` (0.1.1, conditionally accepted in `c0-review-main-line-0.1.1.md`) |
| Engine baseline | AEW `main` at `91c0d98`; integrity checked against P2c (PR #20) at `bdabff9`. |
| Reviewer | Claude, the main AEW agent, for the operator |
| Date | 2026-10-02 |
| **Disposition** | **ACCEPT.** 0.1.2 applies exactly R2-1 to R2-6, plus version, digest and evidence bookkeeping. The condition of the 0.1.1 review is met. D1 to D4 may begin under the approved core plan. |

## How the diff was verified

- **The contract, parsed as data, not as text.** The text diff is 1,084 lines, because the YAML was re-emitted; the parsed documents differ in 53 places. Each one is either an R2 correction below or a version or review bookkeeping change (`info.version`, the `schema_version` constants, `x-c0-review`, two descriptions naming 0.1.2).
- **Every operation, GET and HEAD, on every path.** No `(name, in)` pair repeats, path-level parameters included.
- **The values against the engine.**
  - `VerifiedRoot.at`: the engine writes `utc_now()`, `%Y-%m-%dT%H:%M:%SZ`. It fits `Timestamp`.
  - `VerifiedRoot.h`: the engine's own SHA-256, 64 hex characters (`$defs/sha256` in the control schema). It fits `Sha256`.
  - `VerifiedRoot.audit`: `AU-<n>`. It fits `OpaqueId`.
  - Link values: AEW ids and 40-hex commit hashes fit `OpaqueId`. A completion path such as `work/T-0042/completion.md` does not.
- **The companion files.** `schema.ts` and `vocabulary.ts` change only as the contract does. The other files changed are version and digest pins, generated types, fixtures, tests, the README status line, a historical label on `validation-c0-amend.md`, and appended retest notes in `spt-toolchain-feedback.md`.
- **The earlier reviews.** `c0-review-main-line.md` and `c0-review-main-line-0.1.1.md` are byte-identical to what I wrote.
- **Not rerun here:** the frontend's offline gate (45 tests, the builds, the browser checks). That evidence is the frontend's, in `validation-c0-012.md`.

## The six corrections

| Finding | In 0.1.2 | Verdict |
| --- | --- | --- |
| R2-1 | The duplicates are removed on `/work`, `/evidence`, `/history` and `/history/{id}`, for GET and HEAD. No operation repeats a parameter. | Done |
| R2-2 | `relevant_inputs_fingerprint` and `artifact_digests` items are plain strings, described as opaque, in the contract and in `schema.ts`. | Done |
| R2-3 | `History.links` and `HistoryDetail.links` say the backend omits `completion`, and that values are AEW ids or commit hashes. They list the seven known relations. Items stay `OpaqueId`, so a path is rejected. | Done |
| R2-4 | `WorkCounts` states the whole-subtree Ticket rollup, archived Tickets included, separately from `children` and from Overview's counts. | Done |
| R2-5 | `VerifiedRoot` requires `at` and `audit`. `Integrity` requires `last_full` and `oldest_unverified_at`, both nullable, and keeps `x-provisional: P2c`. `reasons` is backend-supplied. The capability stays UNSUPPORTED until #20 merges. | Done |
| R2-6 | `lost` is a known `HarnessStatus`, and the strings stay open. | Done |

## For integration

None of these condition the acceptance. They are main-line work when the backend is built.

- **`Integrity` from `aew status`.** P2c's `history_audit` block maps to it field by field:
  - `unverified.entries` becomes `backlog`, and `unverified.oldest_at` becomes `oldest_unverified_at`.
  - The backend strips `age_days`, which status adds to `last_full`, because `VerifiedRoot` is closed.
  - `over_policy` holds plain strings. The backend turns each into a `Reason` with a code, under the shared reason-code registry the main line owns.
- **Integrity becomes AVAILABLE** when #20 merges and the backend advertises it. `x-provisional: P2c` can be dropped in the same contract revision.

## The record

- `c0-approval.json`: I set the 0.1.2 acceptance (status, commit, reviewer, date, disposition, this document) and kept both earlier reviews.
- **For the frontend agent:** the tests in `web/tests/contract.test.ts` that pin the record to PENDING (lines 35–36 and 431–432) and `web/src/api/contract-version.json`'s `"approval": "PENDING"` now need to move to the accepted state. I did not edit frontend code or tests.
