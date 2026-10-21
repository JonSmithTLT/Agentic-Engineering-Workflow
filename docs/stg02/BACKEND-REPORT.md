# STG-02 backend report (lead AEW developer)

**For:** the lead designer, who copies this into the architecture workspace (the handoff says not to edit it).
**Contract:** the adopted STG-01 v0.5.4 ZIP, SHA-256 `64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f`: D-01 0.3.4, O-01 `o01-command-0.2-review-candidate`, the selection profile and the owner pins.
**Code:** [`src/aew/stg02/`](../../src/aew/stg02/). The tests are `tests/integration/test_stg02_slice.py` (61), `tests/integration/test_stg02_fence.py` (1, serial lane) and `tests/unit/test_stg02_adopted.py` (15).
**Gap entries:** [`GAP-ENTRIES.md`](GAP-ENTRIES.md), STG02-BE-01 to BE-16.
**Date:** 2026-10-19 (UTC 2026-10-20).

## In one paragraph

The six routes run over real HTTP on 127.0.0.1:4261, in a process of their own beside the provisional dashboard API, which is unchanged.
- `CONTINUE_ELIGIBLE_WORK` is admitted by a fixture HEB under the fixture delegation issuer `delegation:fixture`.
- Every other action is refused or held, and protected actions allocate nothing.
- The conformance driver, on its default clock and authenticated by a synthetic bearer, gives **47 passed, 0 failed, 6 skipped**.
- That run used the driver at workspace commit `75d30cf`: the clock fix of `006f45b` (STG02-BE-02) and the config headers with the A1 authentication check. Before the clock fix, the driver's default clock gave 5 FAILs, all the driver's own; this server and the contract were not changed for them.

The result that matters most for the design is STG02-BE-03. No fact this backend serves is qualified:
- labelled fixture facts may not be;
- AEW's own engine issues no renewals (BE-04).

So every read is `partial`/`unknown`, every continuation axis is `unknown`, every list's membership is `unknown`, and no envelope can equal a recorded positive one. The 4 R6 SKIPs follow from that and could not have been avoided.

## How to run it

The server the driver runs against (it authenticates with the config's synthetic bearer):

```bash
python -m aew.stg02.server --port 4261 --state-dir <dir> --project <AEW repo root> --tokens <synthetic tokens file> --test-routes
```

The server the response recorder runs against (`tools/stg02/record_responses.py` sends no bearer for the operator):

```bash
python -m aew.stg02.server --port 4261 --state-dir <dir> --project <AEW repo root> --tokens <synthetic tokens file> --fixture-recipient --test-routes
```

The driver config:

```bash
python -m aew.stg02.server --state-dir <dir> --tokens <synthetic tokens file> --test-routes --driver-bearer token-operator-synthetic --write-driver-config docs/stg02/driver-config.json
```

- `--project` is optional: without it, only the fixture world is served.
- `--test-routes` exists for the driver (case C17-N03). The driver authenticates with the synthetic bearer that `--driver-bearer` writes into the config's `headers` (STG02-BE-07), so its server runs without `--fixture-recipient`; the response recorder still uses `--fixture-recipient`. With `--project`, `--fixture-recipient` lets any local process read that project's engine state without a token; the server warns at start.
- `--real-recipient` names the one recipient AEW's own records are disclosed to (default: the fixture world's operator; STG02-BE-16).
- The recordings and driver runs below used a scratch AEW project built with the test suite's own helpers:
  - `T-0001` is RUNNING, with implementer invocation `INV-0001`;
  - `T-0002` is BLOCKED on `T-0001`.

## 1. Each displayed consequential field: its owner, real or labelled fixture

**Real** means the value is read from AEW's committed engine state (`aew:` identities). **Fixture** means it is served from `src/aew/stg02/worlds/slice-world.json` (`fixture:` identities). **None** means the slice has no source, so the stamp is `not_established` / `unavailable`. **Nothing is qualified** (STG02-BE-03, BE-04).

**Who sees the real records.** AEW's engine records have no recipient (STG02-BE-16). They are disclosed to one recipient, `--real-recipient`, by default the fixture world's operator. To every other recipient they do not exist: no `aew:` item in a list, and the nondisclosing `404` for a real run or work id. Read entitlement is stated by the world (`read_entitled`), never presumed: a recipient it does not name is not entitled (BE-15).

### Step 1: `GET /v1/read/waiting`

| Field | Owner (stamp) | Real AEW work unit | Journey item (`fixture:ticket-*`) |
|---|---|---|---|
| item `source` | CNI | real: `aew:waiting:<id>`, the engine's own listing | fixture |
| `data.work` (id, kind, revision) | WIS | real: id, kind, `plan-<accepted>` | fixture |
| `data.cause` | WIS (real) / the world's responsible owner (fixture) | real: from the state (`BLOCKED` → `dependency`, `ESCALATED`/`REPLAN_REQUIRED` → `operator_need`, the review and verification failures → `mandatory_result`, `INTERRUPTED` → `unknown`) | fixture |
| `data.basis_refs` | WIS | real: the unit's `blocked_by`; `partial_visible` (completeness never claimed) | fixture: `unknown`, none |
| `data.progress` | WIS (real) / HEB (fixture) | real: `blocked` | fixture |
| `data.responsible_owner` | in the CNI item | `WIS` | fixture |
| `data.narrative` | inert text, `service_observation` provenance | real: state and `state_reason` | fixture |
| `collection_basis` | CNI | fixture (the slice's aggregation is not a qualified roster) | fixture |
| `page.membership` | – | always `unknown` | always `unknown` |

### Step 2: `GET /v1/read/runs/{execution_id}`

| Field | Owner | Real AEW invocation | Journey run (`fixture:run-continue-1`) |
|---|---|---|---|
| item `source`, `data.phase`, `phase_observation_class`, `phase_basis_ref`, `started_at` | R01 | real: the latest harness run's observed status (`starting`/`running` → `REPORTED_ACTIVE`, terminal → `REPORTED_FINISHED`, lost/unconfirmed or no run → `UNKNOWN`); first launch time | fixture: `REPORTED_IDLE`, start and last progress |
| `data.work_ref` | WIS | real | fixture |
| `data.remote_effect_state`, `remote_effect_basis_ref` and its stamp's `observed_at` | IF12 | none: `NOT_ESTABLISHED` | fixture: `UNKNOWN_EFFECT`, with basis `fixture:if12-provider-timeout-continue-1` and last-known `observed_at` (field map step 2) |
| `data.stall_assessment` | R01 | none: `NOT_ESTABLISHED` | fixture: `POSSIBLE_STALL` with basis |
| `data.custody_state` | HEB | none: `UNKNOWN` | none: `UNKNOWN` |
| `data.resource_state` | IF10 | none: every field `UNKNOWN` | none |
| `whole_invocation_*_clearance`, `authority_effect`, the domains | constants of the wire | – | – |

### Step 3: `GET /v1/read/continuation-state/{work_id}`

| Field | Owner (pinned, `owner-pins.json`) | Real AEW work unit | Journey item |
|---|---|---|---|
| item `source` | HEB | none | fixture |
| `data.work_ref`, `data.work_revision` | WIS | real | fixture |
| `data.generation_ref`, `data.binding_ref` | HEB | none (`unavailable:HEB`) | fixture |
| `data.operation`, `data.informational_only` | HEB | constants (`CONTINUE_ELIGIBLE_WORK`, `true`) | constants |
| `data.axes.WIS` | WIS | real, `unknown` / `unqualified` / `SOURCE_UNQUALIFIED` | fixture, likewise |
| `data.axes.HEB`, `ADC`, `R01`, `IF10` | each its own owner | none: `unknown` / `not_established` / `SOURCE_UNAVAILABLE` | fixture (`ticket-continue`), likewise unqualified |
| `data.axes.AEV` | AEV | none | none on `ticket-continue` (as the recorded partial vector); fixture on `ticket-held` |

### Step 4: `POST /o01/v0/command-sets`

| Field | Owner | Real or fixture |
|---|---|---|
| origin (delegated grant) | the issuer `delegation:fixture` | fixture: `src/aew/stg02/world.py`, records bound to the exact intent digest |
| admission and result, `operation_ref`, `owner_evidence_ref` | HEB | fixture HEB. **The effect is a labelled record, not scheduling**: nothing in AEW continues or launches; `owner_evidence_ref` is `fixture:heb-evidence-<h>` |
| receipt `observed_at`, `source_valid_until` | the carrier | real clock; validity 900 s (BE-09) |

### Step 5: owner operations and the owner GET

| Field | Owner | Real or fixture |
|---|---|---|
| owner GET body (`source_epoch`, `observed_at`, `source_valid_until`, `result`) | HEB | fixture HEB's own record. `source_epoch` is `fixture:heb-epoch-1`; `observed_at` is the GET's moment, because HEB re-observes its record (the carrier never refreshes it) |
| index entries | `data.owner` (HEB) | fixture: `op-record:<operation_ref>` with HEB's fixture epoch |
| `collection_basis` | CNI | fixture |

### Step 6: protected actions

Shown held. `ATTACH_LEAD`, `REATTACH_LEAD`, `CLOSE_ATTACHMENT` and the rest of the G3 class get `REJECTED` / `ORIGIN_NOT_ESTABLISHED`, with no `operation_ref` and no owner record. `G3_unqualified` is on the continuation-state and owner-operations reads (BE-11).

## 2. Wire fields that cannot be produced yet, and why

| Field or state | Why not |
|---|---|
| any `qualification: qualified`, `observation_state: present_current`, a renewal other than `none` | no owner issues renewals or proofs (BE-04); fixture facts may not be qualified (BE-03) |
| `outcome: provided`, `continuity: source_qualified` on any read | follows from the above (`ReadResult.allOf`) |
| `page.membership: qualified_scoped`, a qualified empty list | follows; also no owner roster or closure evidence (OP-07) |
| any continuation axis `ok` or `blocked` | `FR_OwnerAxis.allOf` needs a qualified fact |
| run `custody_state` other than `UNKNOWN`; `HEB_OBSERVED` phases | AEW's harness supervisor is not a qualified HEB; its run record is reported as `REPORTED_*` (R01) |
| run `resource_state` (amount, units, exposure) | AEW keeps no IF-10 accounting; usage is not attributed per operation |
| run `remote_effect_state` for real runs | AEW does not track IF-12 model-delivery outcomes |
| `elapsed_observed_seconds`, `last_progress_at` for real runs | not recorded in a form with a basis; left null |
| `Link`s | every target must be currently recipient-eligible and reauthorized; the slice emits none rather than claim it |
| an owner effect for any action but `CONTINUE_ELIGIBLE_WORK` | out of scope; `DELEGATED_CANCEL` is held `SOURCE_UNAVAILABLE` after its origin |
| `UNKNOWN_EFFECT` receipts and their reconciliation | the fixture HEB never loses a response; the path is in the model (CS-08) but this backend has no way to exercise it |
| the other 16 D-01 reads | not in the slice; 404 (BE-13) |

## 3. Recorded real HTTP responses

[`recordings/`](recordings/): 36 exchanges, each with the exact request and the response's status, wire headers and body, recorded by `tools/stg02/record_responses.py` from the running server.

| Status | Recordings |
|---|---|
| 200 | `waiting-200`, `waiting-200-page1-limit2`, `waiting-200-page2-limit2`, `waiting-200-partial-real-source-unavailable`, `run-200-fixture-unknown-remote-effect`, `run-200-real-aew-invocation`, `continuation-200-fixture`, `continuation-200-real-aew-work`, `owner-get-200-admitted`, `owner-operations-200` |
| 202 | `command-202-p07-admitted`, `command-202-identical-retry-same-receipt`, `command-202-n21-heb-work-not-eligible`, `command-202-n22-c17n02-intent-not-granted`, `command-202-c17n01-delegation-expired`, `command-202-protected-attach-without-g3` |
| 400 | `waiting-400-no-version`, `waiting-400-version-0.3.3`, `run-400-noncanonical-id`, `owner-operations-400-unknown-owner`, `command-400-no-o01-header` |
| 401 | `waiting-401-unknown-bearer`, `continuation-401-malformed-authorization`, `command-401-recipient-not-authenticated` |
| 404 | `run-404-unknown`, `run-404-hidden-member`, `continuation-404-unknown`, `owner-operations-404-undisclosed-scope`, `owner-get-404-unknown`, `owner-get-404-other-recipient`, `command-404-c17n03-retry-after-entitlement-withdrawn` |
| 409 | `waiting-409-cursor-other-recipient`, `owner-operations-409-forged-cursor`, `command-409-request-key-conflict` |
| 503 | `run-503-real-source-unavailable`, `continuation-503-real-source-unavailable` (the real engine source unavailable; the waiting list stays an honest `partial` with `source_unavailable`) |

**By route.** Each declared status of each route: R means recorded, T means proven by a repository test only, and "never" says why the status cannot occur.

| Route | 200/202 | 400 | 401 | 404 | 409 | 503 |
|---|---|---|---|---|---|---|
| `GET /v1/read/waiting` | R | R | R | T (entitlement withdrawn; BE-15) | R | never as such: with the real source down, the fixture members are still an honest `partial` (R, `source_unavailable`); a ledger lock timeout or an internal error is 503 (T) |
| `GET /v1/read/runs/{execution_id}` | R (fixture, real) | R | T | R (unknown, hidden) | never: no cursor | R |
| `GET /v1/read/continuation-state/{work_id}` | R (fixture, real) | T | R | R | not declared | R |
| `GET /v1/read/owner-operations` | R | R | T | R (undisclosed scope) | R | T (ledger lock, internal error) |
| `POST /o01/v0/command-sets` | R (six cases) | R | R | R (C17-N03) | R (`request_key_conflict`); T (`unresolved_no_redispatch`) | T (ledger lock, internal error) |
| `GET /o01/v0/owner-operations/{owner}/{operation_ref}` | R | not declared: 404 (BE-10) | not declared: 404 (BE-10) | R (unknown, other recipient) | never: no path produces a precondition change for a stored operation | T (ledger lock, internal error) |

The 503s were made with the test-only outage switch (`POST /_test/engine-outage`). It forces the same `SourceUnavailable` path a lock timeout or an unreadable state file takes, and that path is tested on its own. `409 unresolved_no_redispatch` needs the clock moved past a receipt's validity, so it is in the tests rather than the recordings.

## 4. The driver's result

The driver is `30-stages/STG-02-first-vertical-slice/driver/slice_driver.py` at workspace commit `75d30cf`. `006f45b` fixed STG02-BE-02 (without `--now`, each receipt is checked at the instant its answer arrives); `75d30cf` sends the config's `headers` on every request and adds A1, which checks that every read and the command route answer `401` without the bearer and with one never issued, and the owner GET its one `404`. It ran on its default clock against this server at commit `f99c9963` with the scratch project, `--tokens` and no `--fixture-recipient`. The config is [`driver-config.json`](driver-config.json), generated from the fixture world (`--write-driver-config --driver-bearer`); its bearer is a synthetic token.

| Run | Output | Result |
|---|---|---|
| default clock, driver at `75d30cf`, synthetic bearer | [`driver-output.txt`](driver-output.txt) | **PASS: 47 passed, 0 failed, 6 skipped** (A1: 12 of 12) |

Before running against the server, the driver's self-test passed on this machine (clean run; 10 of 10 mutations killed at `006f45b`, 11 of 11 at `75d30cf`, the latter run by the independent reviewer). The same driver without a bearer in the config gives 35 passed, 0 failed, 7 skipped (the seventh is A1). Earlier, the driver at `6b10073` fixed "now" once at its start: its default clock gave 30 passed and 5 failed (C1, C5, C17-N01..N03, all `RECEIPT_INVALID_CURRENTNESS`), and 35 passed with `--now` set past the run's start. Those 5 FAILs were classified before anything changed, as the driver's own (STG02-BE-02). Neither this server nor the contract changed for them; the designer fixed the driver.

**Why each SKIP remains (a SKIP is not a pass):**

| SKIP | Why |
|---|---|
| R6 waiting | no `matches_fixture`: this backend's world is not a recorded world, and no recording exists for 0.3.4 waiting |
| R6 runs | same; and the A-23 run fixtures are 0.3.3 examples, four of them without witnesses (the designer's note of 2026-10-19) |
| R6 continuation-state | the recordings' envelopes (`provided`/`source_qualified`, or `partial` with exactly `["source_unavailable"]`) need qualified owner facts this backend cannot honestly serve (STG02-BE-03) |
| R6 owner-operations | same: the index recordings are `qualified_scoped` with `source_qualified` continuity |
| R3 waiting | a list route has no id to make unknown (the driver checks R3 only through `unknown_params`) |
| R3 owner-operations | same. The route's 404 (an undisclosed `scope_ref`) is recorded and tested instead |

**What the repository tests cover beyond the driver:**
- N21, the HEB owner refusal;
- the revoked delegation, an unknown proof and another actor;
- mixed sets, consent on a delegated set, and member order;
- `DELEGATED_CANCEL` with a current, bound delegation: held `SOURCE_UNAVAILABLE`, nothing allocated;
- A04 `REAFFIRM_ELIGIBLE_CHILD_GRANTS`: `ORIGIN_NOT_ESTABLISHED`, nothing allocated;
- HEB's own outcomes from a fixed state: no eligibility for the work (`HEB_STATE_UNKNOWN`) is held, nothing allocated; a predecessor from an earlier HEB epoch (`HEB_STALE_PREDECESSOR`) is an allocated `PRECONDITION_STALE`;
- an expired entry and a dropped receipt (`409 unresolved_no_redispatch`);
- an owner record past its retention, never disclosed, before any purge has run;
- read entitlement stated, never presumed, and an earlier world's grant ended at restart;
- every identifier encoding rule;
- cursors bound to recipient, page size and visible set (a cursor replayed after the visible set changed is `409`);
- a hidden member changing nothing, for fixture members; AEW's real records reach one recipient only (BE-16);
- a repeated `X-AEW-Wire-Version`, `X-AEW-O01-Wire`, `Authorization`, `Host`, `Origin` or `Content-Length`, refused in either order;
- every other method (`PUT`, `DELETE`, `PATCH`, `TRACE`, `HEAD`, any token) and every unrouted `/o01/` path, answered with the route family's Problem and wire headers;
- the 503 path;
- request text in the server's log: the method only when it is a plain upper-case token, the path and an error's traceback (as one line) escaped and bounded, so a client cannot forge a log line;
- the two-process fence, with the overlap forced, on the key ledger only (BE-08);
- a second server unable to bind the same port;
- every vendored adopted file against its sealed pin.

## 5. The four push-back points: what actually happened

1. **Delegation issuance** (STG02-BE-06). A grant bound to the exact intent digest is per selection, not standing. It is invalidated by any HEB epoch change, and it is never consumed: one grant admitted the same intent under every new key. Revoked and forged are one code.
2. **The session** (STG02-BE-07). Not used for A04, which is refused `ORIGIN_NOT_ESTABLISHED`. For reads, the bearer has no issuer. The driver at `75d30cf` sends the config's synthetic bearer (`--driver-bearer`); the slice's tokens are synthetic, and the labelled tokenless fixture recipient is left to the response recorder.
3. **Compare-and-fence across processes** (STG02-BE-08). No problem in the slice: one SQLite file, one `BEGIN IMMEDIATE` per submission, proved with two real processes. It holds only while the carrier's ledger and HEB share a store. With a separate HEB it becomes two commits, and only HEB-side idempotency on the carrier-derived identity closes the gap. The fence was exercised on the key ledger only: the fixture HEB's state never moves while the server runs, so the slice does not demonstrate the bound the BE-06 ruling assumes.
4. **Retention** (STG02-BE-09). Durations chosen: receipt 900 s, stored receipt 7 days after expiry, owner records 30 days. The finding is that CS-04 forbids ever forgetting a key, so the key ledger is unbounded.

## 6. Context feedback on the handoff

**Missing.**
- The handoff does not say how the driver authenticates. It sent no bearer, and the wire requires one. Needing a tokenless fixture recipient was discovered, not stated. (The designer's `75d30cf` closes this for the driver: config headers, and A1.)
- It does not say that "labelled fixture ⇒ unqualified" makes every positive recording and directive unreachable. That consequence decides the R6 SKIPs and the website's experience, and is worth stating up front (BE-03).
- The O-01 `Problem` and `OwnerOperationRead` are defined only in the O-01 OpenAPI document, not in `o01-extended-command.schema.json`. The field map's table suggests the standalone schema is enough.
- Nothing says which of the A-24 reject cases the 0.2 refusal map can express. N21 cannot (BE-01).

**Wrong or unclear.**
- The field map says the backend should set `matches_fixture` "when your world matches a recording". For a backend following rule 2, that can never happen.
- The driver's default `--now` failed against any real clock (BE-02; fixed by the designer in `006f45b`).

**Unused.** The oracle's `OwnerMachine`. It was read to cross-check the CS-04 order and the receipt rules, never run or imported.

**Rules I would add.**
- "A fixture world's facts are always unqualified; expect `partial`/`unknown` everywhere, and expect R6 to SKIP."
- "A dev server must refuse to start when its port is already held." A stale slice server still holding 4261 answered part of this slice's first recordings; the server now binds exclusively, and the recordings were remade against one server.
- "Generate the driver config from the backend's own world, so delegation digests cannot drift."

## 7. Joint test, run 1 (2026-10-21)

Backend `7acb60f5` on 127.0.0.1:4261, a fresh state directory, the synthetic scratch project, `--fixture-recipient --test-routes`, behind the website's forwarding wrapper (the designer's `JOINT-TEST-BRIEF.md`). The website's `JOINT-TEST-NOTES.md` holds the run record; the backend side of it:

- **JT-02, an implementation defect here, fixed after the run.** The website's owner GET `GET /o01/v0/owner-operations/HEB/op%3Ac3e5…` answered the nondisclosing 404 for an operation that existed and was readable; the literal-colon path answered 200. The route matched the still-encoded segment against the `operation_ref` pattern, so `%` failed it before any lookup. The adopted O-01 route decodes once ("including percent-encoded slash after single decoding; ambiguous/double-encoded paths are rejected before lookup"): each owner GET segment is now percent-decoded exactly once, and a malformed escape, invalid UTF-8, a decoded `%` (double encoding) or a decoded `/` stays the nondisclosing 404. Tests: `test_an_operation_ref_is_percent_decoded_exactly_once_before_its_pattern_is_checked`. The D-01 id segments are unchanged: the adopted D-01 rule refuses any percent sequence in a base64url segment (`400`), pinned by `test_a_d01_id_segment_with_any_percent_sequence_stays_400`.
- **Why the driver did not find it.** Its `quote()` keeps `:` unencoded (`safe=':'`), so it never sends the encoded form. A driver case with `%3A` would have caught it (context feedback for the designer).
- **The request log had no time.** The backend could order the run's three command POSTs (one dispatch, two stored-receipt lookups) but not place them; the website's notes supplied the times. Every log line now starts with its UTC time to the millisecond (`test_every_server_log_line_starts_with_its_utc_time_to_the_millisecond`).
- **Probes, as the backend saw them.** Engine outage armed 00:19:31.8Z and restored 00:20:39.9Z; read entitlement withdrawn 00:22:11.7Z and restored 00:23:30.6Z. At the end, the ledger held 1 key and 1 owner operation; the receipt's `observed_at` was still that of the first submission.
