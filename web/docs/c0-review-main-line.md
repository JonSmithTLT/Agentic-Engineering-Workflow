# C0 main-line review: dashboard API 0.1.0

| | |
|---|---|
| Reviewed commit | `59081d0136bba947d645c2ec60132e5ca7e12e1a` (branch `feat/aew-dashboard-readonly`) |
| Contract | `docs/design/dashboard-api-v1-provisional.yaml`, version `0.1.0` |
| SHA-256 | `f956f0b2f1f2de0840667c28301be08b6cc0b462271651a0d3cc9117b6034b70` (verified at the commit) |
| Reviewed against | AEW `main` at `91c0d98`, which includes ADR-0011 P2a and P2b (cold history and archival, PRs #17 and #18, merged after the branch's base `c380aea`) |
| Reviewer | Claude, the main AEW agent, for the operator |
| Date | 2026-10-02 |
| **Disposition** | **AMEND.** The direction is accepted: read-only, same-origin, bounded, backend-owned semantics. The wire representation is not accepted as-is. Apply C0-1 to C0-9 below and resubmit for renewed approval. Until then D1 to D4 stay gated. |

The review covers the contract only. It does not cover the React code, the mocks, the screenshots or the SPT toolchain.

## The eight decisions

| # | Decision | Disposition |
|---|---|---|
| 1 | Capability names | **Accepted with amendment.** `action_projection` and `integrity` are accepted. Deferred metrics, search and graph are accepted as omitted. Amend: an unknown capability key must validate (C0-2). Today `queue` is UNSUPPORTED (C0-6), and `integrity` is UNSUPPORTED until P2c ships the audit (C0-5). |
| 2 | `{state, reasons}` objects | **Accepted.** The four states are accepted, and a missing capability means UNKNOWN. The backend owns explanations. The reason-code caveat is C0-8. |
| 3 | Envelope | **Accepted.** See "Engine facts for the envelope" below for what the backend will put there. |
| 4 | Cursors, filters, IDs | **Amend** (C0-3, C0-4). |
| 5 | Wire shapes and vocabularies | **Amend** (C0-1, C0-7, C0-8). |
| 6 | Queue | **Not confirmable: no queue exists in the engine** (C0-6). |
| 7 | History and integrity | **Amend** to the cold-history model now on `main` (C0-5). |
| 8 | Endpoints, ETag, security | **Accepted.** GET and HEAD only, same-origin, redirects rejected, representation-scoped ETags. The cookie name stays illustrative pending the integration security design. Low: C0-9. |

## Findings

### C0-1 (high): `Work` does not match the engine's work unit

- **`classification` collides with an engine term.** In the engine, "classification" is the verification-failure classification (`LOCAL_IMPLEMENTATION_DEFECT`, `PLAN_OR_DESIGN_DEFECT`, `CONTRACT_VIOLATION`, `ENVIRONMENT_OR_EVIDENCE_BLOCKED`). The unit's class is `risk_class`, an integer from 0 to 4. Rename the field to `risk_class: integer | null`.
- **`assurance` is not a scalar.** It is part of the accepted plan: the review and verification cards the plan commits to, which become required gates. Either make it a structure (`{review: [card], verification: [card]} | null`) or drop it from 0.1.0.
- **`revision` is ambiguous.** A unit has no revision. Rename it to `plan_revision` (the accepted plan's revision number, null if none), or drop it.
- **Missing fields the views need:**
  - `mutating: boolean | null`: mutating versus non-mutating Tickets are different kinds of work (null for parents);
  - `archived: boolean`: see C0-5;
  - `blocked_by: Reason[]`: why a Ticket is BLOCKED, from the engine's readiness blockers;
  - for parents, `children` (ids of hot and archived children) and a `rollup` of counts.
- **The vocabularies** are in the appendix. Keep the strings open, as the contract does.

### C0-2 (medium): new capabilities would fail validation

`Capabilities` has `additionalProperties: false`, so a backend that adds a capability breaks every older client. That contradicts decision 2's own rule, that unknown values are explicit warnings and never failures. Use `additionalProperties: {$ref: Capability}` and show unknown capabilities with a warning.

### C0-3 (high): `/work` must not page through all history

On `main`, finished work leaves the hot state (ADR-0011). Views show the hot units plus a bounded `recent` ring of 20, and reaching all finished work is an explicit history query. "No fetch-all route" is right, but an unfiltered cursor over `/work` would be one. Amend:

- **`/work` with no filter:** the hot units, plus the `recent` items marked `archived: true`.
- **Filters the backend will supply:**
  - `/work`: `state`, `kind` and `parent`. `state=DONE|CANCELLED` is the explicit query over archived work.
  - `/history`: `kind`, `since` and `until` (`aew history list`).
  - `/evidence`: `work`.
  - Declare them as query parameters now, so the ETag and cursor scopes include them.

### C0-4 (medium): cursors and IDs

- **History cursors never need to expire.** The history is append-only, with a stable sequence number. A history cursor can be bound to the history count when paging started (the index stops at that count), so it stays valid while new entries are appended. Keep 409 for the cursors of hot collections, which expire when `control_revision` changes.
- **IDs are path-safe, by engine construction.** Every record id matches `^[A-Za-z0-9][A-Za-z0-9-]*$`:
  - `T-0001`, `S-0001`, `E-0001`, `INV-0001`, `R-INV-0001-1`, `D-0001`, `AN-0001`, `H-0001` and `LEAD-0001`;
  - evidence ids such as `INV-0001-review-1`.

  Slugs (the project id, card names) match `^[a-z0-9][a-z0-9._-]*$`. No id can be `.`, `..` or contain `/`. The main line declares `OpaqueId.pattern: ^[A-Za-z0-9][A-Za-z0-9._-]*$`. This is a server-declared restriction, so the client may rely on it without inferring anything.

### C0-5 (high): history and integrity predate the cold-history model

The contract was drafted on `c380aea`, before ADR-0011 P2a and P2b. History now has an exact form, so align with it:

- **A `History` item is a manifest entry.** Its fields:
  - `seq` (integer, stable order);
  - `kind`: `unit`, `annotation`, `audit` or `lead`;
  - `id`, `at`, `state`, `unit_kind`, `title`, and `parent` (the current parent, with moves applied);
  - `subject` and `rel` (for annotations);
  - `links`: a map from relation to ids;
  - `sha256`: the pinned content hash;
  - `source`, the trust label: `engine`, `operator`, `model` or `external`.

  ADR-0011 invariant 14 requires the trust label wherever a historical record is shown.
- **Drop `currentness` from `History`.** A historical record is never current evidence (invariant 14). A currentness field invites a "current" rendering.
- **`annotation` must be a list.** A record has any number of annotations. `/history/{id}` returns `annotations: [{id, rel, object, at, decision, source, note}]`. Known relations: `moved_to`, `superseded_by`, `promoted_to`, `lineage` and `audit_finding`. `lineage` is one of those relations, so replace the `lineage` array with `links`.
- **`Integrity` roots are structures, not strings:**
  - `current_root`: `{count, head_h, sealed_head: {seq, sha256} | null}`;
  - `verified`: `{count, h} | null`;
  - `backlog`: entries not yet audited (current count minus verified count), computed by the backend;
  - `last_audit`: an `EntityRef` to the audit record (kind `audit`).

  Status stays an open string.
- **The audit is P2c, not built yet.** `integrity` reports UNSUPPORTED until P2c ships, and the integrity fields stay provisional until then.
- **`Work` and `Overview` need the archived side:**
  - `Work.archived: boolean`;
  - Overview `counts` split into hot work and finished work: `{open, done, cancelled}`, the last two from the engine's archived counts;
  - an Overview `recent` list (at most 20), as `CURRENT.md` already shows them.
- **Never expose `path`**, though manifest entries have one: storage layout stays off the wire, as the contract already says.

### C0-6 (high): the queue has no engine counterpart

The engine has no integration queue. Concurrency and scheduling are M4 and M5 work (future-work F3 and F11). `QUEUED`, `LEASED`, `DEFERRED`, `AWAITING_DISPOSITION`, `PUBLISH_IF_CLEAN`, `VALIDATE_ONLY`, `custodian`, `position` and `lease_started_at` are not engine vocabulary, so they can't be confirmed. Remove `Queue` and `/queue` from 0.1.0, or keep them marked `x-provisional: unscheduled` with the capability UNSUPPORTED.

What exists today belongs on `Work`:
- a Ticket's `commit_ready_seq`;
- its integration status (for example `prepared`, `publishing`, `conflict` or `superseded`);
- its integrated commit.

Add them as `integration: {status, commit, commit_ready_seq} | null`.

### C0-7 (medium): `Run` names neither engine object

The engine has invocations (`INV-0001`: role, status, Work Unit, execution profile) and, within them, harness runs (`R-INV-0001-1`: harness, launch, kind, observed status, authority, heartbeat). Many invocations have no harness run, for example a manual submission. A `Run` list would miss those, and its `status` mixes two vocabularies. Amend:
- `/runs` lists invocations: `id` (INV), `role`, `status` (see appendix) and `work`;
- each invocation nests `runs: [{id, harness, launched_at, kind, status, authority}]`.

The backend never passes on `run_dir`, workspace paths or observation paths. The engine's `harness status` prints `run_dir`, so the projection must drop it.

### C0-8 (medium): reason codes are an engine deliverable

`Reason.code` is required, and only part of what feeds Attention has a code in the engine today:
- **Readiness blockers** carry a `kind` that can serve as a code: `plan_not_accepted`, `plan_binding_stale`, or the edge kind of an unsatisfied dependency, with its upstream id.
- **Errors** carry the engine's error codes (`STALE_AUTHORITY`, `DEPENDENCY_UNSATISFIED`, `ILLEGAL_TRANSITION`, ...).
- **Contradictions** (`status`) are free text, with no code.

The main line will define one reason-code registry at integration, covering contradictions too. Until then, contract tests must accept any code string, and the UI must show the message, never infer from the code. `Evidence.bindings` must not stay free-form (`additionalProperties: true`): make it explicit and path-free, as `evaluated_snapshot`, `plan_revision` and `producer: {role, invocation, run, model, provider, harness}`.

### C0-9 (low): the response template applies everywhere

Every route documents every status code:
- 409 (cursor expired) on routes that have no cursor;
- 404 on collection and singleton routes, which have no id;
- "Overview is a coherent composite" on every 200.

Document per route what can happen. It changes no shape, but generated clients and reviewers read these.

## Engine facts for the envelope (decision 3)

- **`project_id`:** the manifest's slug, chosen by the operator. It defaults to the repository directory's base name, never a path.
- **`control_revision`:** the engine's integer revision as a decimal string. It is monotonic per project, and every commit advances it, archival included.
- **A coherent Overview** is one read of the control state.
- **Observed run status** (heartbeat, supervisor state) comes from run directories. It changes without a new revision, so an ETag must be computed from the representation, never from `control_revision`, as the contract already says.

## Appendix: engine vocabularies at `91c0d98`

Treat these as known values. The strings stay open on the wire.

- **Work kinds:** `epic`, `story`, `ticket`.
- **Ticket states:** `BLOCKED`, `READY`, `ASSIGNED`, `RUNNING`, `REVIEW_PENDING`, `REVIEW_FAILED`, `REVIEW_PASSED`, `VERIFY_PENDING`, `VERIFICATION_FAILED`, `VERIFICATION_INCONCLUSIVE`, `VERIFIED`, `COMMIT_READY`, `DONE`, `INTERRUPTED`, `REPLAN_REQUIRED`, `ESCALATED`, `CANCELLED`.
- **Story and Epic states:** `PLANNING`, `IN_PROGRESS`, `ACCEPTANCE_PENDING`, `DONE`, `CANCELLED`.
- **Invocation roles:** `implementer`, `reviewer`, `verifier`, `planner`, `investigator`, `researcher`.
- **Invocation status:** `active`, `completed`, `cancelled`, `interrupted`, `revoked`, `superseded`.
- **Evidence kinds:** `implementation_report`, `review`, `verification`, `check_result`, `discovery_record`, `research_record`, `plan_proposal`.
- **Evidence results:** `pass`, `fail`, `inconclusive`, `blocked`.
- **Evidence currentness:** `CURRENT`, `STALE`, `UNKNOWN`.
- **Decision types** (19): `verification_failure_classification`, `authority_transfer`, `authority_acceptance`, `authority_rejection`, `waiver`, `manifest_adoption`, `state_regression`, `cancellation`, `reconciliation`, `plan_acceptance`, `promotion`, `role_plan_change`, `closeout`, `evidence_acceptance`, `hierarchy_change`, `dependency_change`, `plan_reconfirmation`, `input_acknowledgement`, `attempt_supersession`.
- **History entry kinds:** `unit`, `annotation`, `audit`, `lead`.
- **Trust sources:** `engine`, `operator`, `model`, `external`.
- **Annotation relations:** `moved_to` (built); `audit_finding` (P2c); `superseded_by`, `promoted_to` and `lineage` (later).

## Resubmission

Apply the amendments across the YAML, generated types, Zod, fixtures, pins and conformance together, as the packet's procedure says. Then resubmit with the new version, digest and commit. Fixtures F0 to F11 need an archived-work world, covering the `recent` ring, an archived unit by id and a move annotation, and a history page whose cursor survives new entries.
