# C0 main-line review: dashboard API 0.1.1 (resubmission)

| | |
|---|---|
| Candidate commit | `7b0177b76a919e019d2051adff8f7616ae6c2fda` (branch `feat/aew-dashboard-readonly`) |
| Contract | `docs/design/dashboard-api-v1-provisional.yaml`, version `0.1.1` |
| SHA-256 | `3da20f18768d34bef9ccf15fcb65c24cefd2ca73cfc77e6cada8a586f88a0dc4` (verified at the commit) |
| Engine baseline | AEW `main` at `91c0d98`. Integrity is also checked against ADR-0011 P2c as built: PR #20, branch `impl/adr-0011-p2c-history` at `bdabff9`, not yet merged. |
| Reviewer | Claude, the main AEW agent, for the operator |
| Date | 2026-10-02 |
| Previous review | AMEND of 0.1.0 at `59081d0` (`c0-review-main-line.md`) |
| **Disposition** | **AMEND (minor), with conditional acceptance.** All nine earlier findings are resolved in substance, and both boundedness proposals are accepted. Six mechanical corrections remain (R2-1 to R2-6). Real engine data would fail three of them; one is an OpenAPI validity error. A 0.1.2 that applies exactly R2-1 to R2-6, and nothing else, is accepted on resubmission: record it with its own commit and digest, and the main line verifies only that diff. D1 to D4 stay gated until that acceptance is recorded. |

## The nine earlier findings

C0-1 to C0-9 are resolved in substance.

- **C0-6 is resolved as asked.** The queue schema and `/queue` are removed, and the integration facts are on `Work`.
- **C0-7 is resolved as asked.** `/runs` returns invocations, each with its nested harness runs.

The corrections below refine C0-1, C0-5 and C0-8. They introduce nothing new.

## The two boundedness proposals

1. **Parent `children` preview (at most 250 ids) plus `children_truncated`, with the full backend rollup: accepted.** Traversal goes through `/work?parent=…`, with explicit DONE or CANCELLED filters for archived children. Never compute a count from the preview. R2-4 states what the rollup counts.
2. **Annotation paging on `/history/{id}`: accepted as named.**
   - `annotations_limit`: default 100, maximum 250.
   - `annotations_cursor`, and `annotations_next_cursor` on the response.
   - Snapshot pinned to the starting manifest count. That matches the engine's index, which serves queries up to a given count.
   - Today `aew history show` returns every annotation. Paging is main-line integration work, as the packet says.

## Null normalization and curated projections

- **Accepted:** absent manifest fields as explicit `null`, and `source` mandatory on every historical projection.
- **Accepted, apart from the two value formats in R2-2:** the curated, path-free `EvidenceBindings`, `EvaluatedSnapshot` and `Producer`. Workspace identity, paths, credentials and arbitrary execution-profile fields stay off the wire, which is correct.

## Corrections

### R2-1 (high): duplicate GET parameters make the document invalid OpenAPI

Several GET operations list a filter parameter twice:
- `/work`: `state`, `kind`, `parent`;
- `/evidence`: `work`;
- `/history`: `kind`, `since`, `until`;
- `/history/{id}`: `annotations_limit`, `annotations_cursor`.

OpenAPI requires each parameter's name and location to be unique per operation. Generators and validators may reject the document, or keep only one copy. List each parameter once, and check the HEAD operations the same way.

### R2-2 (high): two evidence value formats reject real engine data

- **`EvaluatedSnapshot.relevant_inputs_fingerprint`** is `git-tree:<hex>` in the engine (`snapshot/fingerprint.py`), not a bare SHA-256. Make it an opaque string.
- **`EvaluatedSnapshot.artifact_digests`** items are unconstrained strings in the engine's evidence schema. Make them opaque strings too.

### R2-3 (high): history `links` can carry storage paths

A unit's manifest entry records the relation `completion`, whose values are completion-record paths such as `work/T-0042/completion.md`. They would fail the `OpaqueId` item pattern, and paths must stay off the wire anyway.

- The backend omits the `completion` relation from the projection. The completion record is reachable through the unit itself.
- Document that relation values are AEW ids or git commit hashes (`integration_commit`).
- Known relations today: `depends_on`, `invocations`, `tokens`, `evidence`, `integration_commit`, `moved_to`, `audit_finding`.

### R2-4 (medium): say what the rollup counts

The engine's rollup counts **Tickets in the parent's whole subtree** by state, including archived DONE and CANCELLED Tickets through the parent's summary. It does not count direct children. `children` is the direct children.

Amend the `WorkCounts` description for `rollup`: `open` counts subtree Tickets that are not DONE or CANCELLED, and `done` and `cancelled` count subtree Tickets in those states. Overview's `counts.work` keeps the meaning already stated: hot open units, and archived counts by state.

### R2-5 (medium): integrity, as P2c built it

Now that P2c exists (PR #20), the provisional `Integrity` shape can match it:
- **`verified`:** `{count, h, at, audit}`. The engine records when, and which audit record, verified it.
- **`last_full`:** `{count, h, at, audit} | null`. ADR-0011 invariant 11 requires the last full verification to be told apart from the verified root.
- **`backlog`:** entries not covered by the verified root, computed by the backend. Add `oldest_unverified_at: Timestamp | null`.
- **`reasons`:** carries the backend's over-policy findings. Thresholds may be shown as backend-supplied numbers.
- **`last_audit`:** keep the `EntityRef` (kind `audit`, ids `AU-<n>`).
- **The capability** stays UNSUPPORTED until #20 merges, and AVAILABLE after. Keep `x-provisional: P2c` until then.

### R2-6 (low): harness status `lost`

The engine reports `lost` when a supervisor took custody and stopped reporting heartbeats. It is the status an operator most needs to see, so add it to `HarnessStatus`'s known values. The strings stay open.

## For the record

- **Paths, credentials and verifiers** are not exposed anywhere in 0.1.1. Keep it that way in 0.1.2.
- **Recording the next acceptance** in `c0-approval.json` needs:
  - this review as the previous AMEND of 0.1.1;
  - the 0.1.2 commit and SHA-256;
  - reviewer and date;
  - the disposition, once the main line has verified the diff.
