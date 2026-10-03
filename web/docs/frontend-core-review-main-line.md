# Frontend core review, main line: read-only dashboard D1–D4

| | |
|---|---|
| Implementation commit | `e632cc83135ed98f70804df166d1c88f37a0b674` (branch `feat/aew-dashboard-readonly`) |
| Contract | 0.1.2, SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691`, unchanged at the commit (verified) |
| Later commits | `ed500c3` adds documentation only (`frontend-core-status.json`, the packet, a removed screenshot); no runtime change (verified by diff) |
| Reviewer | Claude, the main AEW agent, for the operator |
| Date | 2026-10-02 |
| **Disposition** | **AMEND (minor).** The read-only boundary, rendering safety, transport and capability gating are sound. Two findings need fixing before core freeze: FR-1 (every archived record's lineage is shown as unknown values) and FR-2 (a false "mixed revisions persist" warning while the project is busy). Once the frontend retests both, a diff limited to them is accepted without another full review. |

## How this review was done

- **Frozen copy:** `git archive e632cc8 web docs/design/dashboard-api-v1-provisional.yaml` into a disposable folder; the worktree was not used.
- **Static review only.** This machine has no Node on Windows, and the gate runs in the SPT carrier under WSL, so I did not rerun `offline-gate.sh` or the browser scripts. The test and browser results are the frontend's own evidence (`validation-core.md`), not re-observed here.
- **Read in full:** the transport, query and freshness layers; the capability gate; the content renderer; the entity links; the shared collection and detail views; History; the Work tree model and virtualized table; the evidence detail; the production-leak check. The other pages were checked for count derivation and rendering paths.

## What I found sound

- **Rendering safety.** Markdown skips raw HTML and drops images, and links are limited to `http(s)` (opened with `noopener noreferrer` and marked external) and same-origin paths. Everything else renders as text. There is no `dangerouslySetInnerHTML`, `innerHTML` or `eval`. JSON is rendered as text.
- **Transport.** GET only, `credentials: same-origin`, `redirect: 'error'`, `no-store`. Routes are allow-listed and checked against URL normalization. Every response is Zod-validated, and 304 reuses the validated representation. A response that arrives after an abort is not cached.
- **Read-only boundary.** No mutation calls and no `.aew`, filesystem or Engine coupling. `localStorage` holds only the theme. Mock Service Worker and the fixtures load only in demo mode, and `check-production.mjs` guards the build against them.
- **Honesty.** Counts and rollups are the backend's. The Work tree orders only the loaded page and says so. The child preview shows its truncation. Integrity requests are suppressed unless the capability is AVAILABLE. Queue sends nothing. Unknown semantic values are shown raw with a warning, not mapped.
- **Robustness.** The page-local tree builder is safe against cyclic parent links, record IDs are validated before any request, and history date filters are validated before any request.

## Findings

### FR-1 (Medium): History lineage shows contract-known relations as unknown, and routes every target to Work and History

`pages/History.tsx:293-306`. Link relations are checked against `annotationRelations` plus `integration_commit`. The contract's `x-known-relations` for `History.links` and `HistoryDetail.links` are `depends_on`, `invocations`, `tokens`, `evidence`, `integration_commit`, `moved_to` and `audit_finding`.

So every archived unit's normal lineage (its invocations, credentials, evidence and dependencies) renders as "Unknown value", on real engine data as well as fixtures. Every target except a commit also gets "Work lookup" and "History lookup" links. An invocation belongs under Runs and an evidence record under Evidence, so for those both links lead to a load error.

**Fix:**
- Add a `historyLinkRelations` vocabulary from the contract's `x-known-relations` and use it for links. Keep `annotationRelations` for annotations.
- Route targets by relation:
  - `invocations` to Runs;
  - `evidence` to Evidence;
  - `depends_on`, `moved_to` and `audit_finding` to Work and History, as now;
  - `tokens` as plain IDs, since there is no credential page;
  - `integration_commit` as a commit, as now.

**Retest:** a fixture whose unit entry carries all seven relations. None shows as unknown, and each links where its kind lives.

### FR-2 (Low): The mixed-revision warning fires while the project is merely busy

`client/queries.ts:15-20`, `client/dashboard.tsx:71-89`, `client/freshness.ts`.

The banner compares `control_revision` across `/capabilities` (polled every 5 s), `/project` (every 10 s), `/overview` (every 2 s) and the page's own projection (5 or 10 s, or never for History). Under the contract the ETag covers the full representation, so each commit changes every projection. But each one is refetched only on its own interval.

While the Lead commits more often than every 10 s, `/project` is always behind. The banner then stays UPDATING, and after 30 s of visible time it says "Mixed revisions persist", which here is untrue. Bursts like that are ordinary during Lead work: a dispatch, an ingest and a transition within seconds of each other.

**Fix:** when any visible projection reports a newer `control_revision` than another visible one, refetch the older ones at once. The views then converge within one round trip, and the 30-second warning keeps its meaning: divergence that refetching did not resolve.

**Retest:** a fixture sequence where revisions advance every 3 s for 60 s. The warning never appears, and a projection the server keeps serving at an old revision does trigger it.

## Not findings (for the record)

- **Bundle size**, 545 kB (161 kB gzip): acceptable for a local operator tool. Split routes later if it matters.
- **Extra annotation relations.** `superseded_by`, `promoted_to` and `lineage` are in the accepted contract's annotation vocabulary, though the engine writes only `moved_to` and `audit_finding` today. That's fine: the vocabulary is open.
- **Two snapshot banners on the History page**, one for the collection and one for the integrity panel. Cosmetic.
- **The transport cache is per route and unbounded within a session.** Low risk for a local tool. Bound it if long sessions with deep paging show growth.
- **Model-written evidence bodies render as formatted Markdown with clickable external links**, labelled external. That's acceptable. An optional improvement is a small "written by a model" label beside the body, as the History pages already have.

## For integration (main line, not frontend)

- **ETags must change when `control_revision` does.** "Full representation" must include the envelope's revision; otherwise a 304 keeps an old revision and the freshness logic, which is correct for the contract, would stick.
- **The backend omits the `completion` relation** (R2-3). P2c now does this on its own surface too (PR #20, `c8d3dad`).
- **Integrity becomes AVAILABLE** when #20 merges. The P2c review fixes added `cold.first_at` and `cold.unverified_since`, so the backend can fill `oldest_unverified_at` without reading the history.

## Gate

Core freeze waits for FR-1 and FR-2. Record the fixing commit and the retest evidence. The main line then checks only that diff and records ACCEPT. Live-state, authentication and security integration stay separate, as `integration-checklist.md` says.

## Fix verification: ACCEPT (2026-10-02)

| | |
|---|---|
| Fixing commit | `7c120b4c39a059508e3b095a9bfd5498c1d7be09` (`fix(web): route history relations and reconcile active revisions`) |
| Diff checked | `e632cc8..7c120b4` for `web/src`, `web/tests`, `web/scripts`, the contract, `package.json` and the lock. The commits in between are documentation only. |
| Contract | Unchanged: SHA-256 `68b46527c4df974fde8ae5808e7d3c6bc588a4010a3d5d2adbe47f4c7583d691` at the fixing commit. No dependency changes. |
| Reviewer, date | Claude, the main AEW agent, 2026-10-02 |
| **Disposition** | **ACCEPT.** FR-1 and FR-2 are resolved as asked, and the diff contains nothing beyond them and their tests. Core freeze may proceed. |

- **FR-1 resolved.**
  - `historyLinkRelations` is exactly the contract's seven `x-known-relations`, separate from `annotationRelations`, so no known link type shows as unknown.
  - Targets route by relation: `invocations` to Runs and `evidence` to Evidence. `depends_on`, `moved_to` and `audit_finding` go to the Work and History lookups. `tokens`, commits and unknown relations stay text.
  - Minor, not blocking: an `audit_finding` target is an audit id, which only the History lookup finds.
- **FR-2 resolved.** `client/revisions.ts` is the fix:
  - It works on active, visible projections of the same project only, comparing decimal revisions as BigInt.
  - When a projection succeeds with a newer revision, each older one is refetched once for that target, never in a loop, and only while the page is visible.
  - It never rewrites a payload, ETag or revision, so a projection that really stays behind still triggers the warning.
  - Disabled projections no longer count toward coherence.
- **Not re-run here**, as before: the offline gate (73 tests), the 34 compiled browser checks and the frozen negative control are the frontend's evidence. The negative control, with five expected failures on `e632cc8`, is the right kind of proof that the new tests catch the defects.
- **Unchanged and still separate:** live-state, authentication, header, Host/Origin and packaging integration (`integration-checklist.md`), and the backend's obligation that ETags change with the envelope revision.
