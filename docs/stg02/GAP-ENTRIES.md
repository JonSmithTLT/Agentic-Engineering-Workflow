# STG-02 gap entries: backend (lead AEW developer)

**For:** the lead designer, who copies these into the architecture workspace's `30-stages/STG-02-first-vertical-slice/GAP-REGISTER.md` and triages them (STG02-BE-01 to BE-16). The format and the five classes are the field map's (`handoff/SLICE-FIELD-MAP.md`, "The gap register").
**Adopted bytes:** `STG-01-v0.5.4.zip`, SHA-256 `64e65578…f299f`. Paths such as `02-WIRE/…`, `00-DESIGN/…` and `05-INTEGRATED-FIXTURES/…` are inside it.
**Written:** 2026-10-19 (UTC 2026-10-20), from the backend in [`src/aew/stg02/`](../../src/aew/stg02/); the report is [`BACKEND-REPORT.md`](BACKEND-REPORT.md).
**Independence:** nothing here was agreed with the web developer; each interim choice is this backend's own.

| ID | Class | One line |
|---|---|---|
| [STG02-BE-01](#stg02-be-01) | wire defect | `CONTINUE_ELIGIBLE_WORK` has no reason code for HEB's own refusals (A-24 N21) |
| [STG02-BE-02](#stg02-be-02) | implementation defect (driver) | The driver's default `--now` failed every receipt a real clock issued a second later (fixed in `006f45b`) |
| [STG02-BE-03](#stg02-be-03) | architecture gap | A labelled fixture fact can never be shown as a positive state, so the slice cannot exercise any positive website state |
| [STG02-BE-04](#stg02-be-04) | host or profile qualification deficit | No AEW owner issues a renewal, so even real AEW facts are unqualified |
| [STG02-BE-05](#stg02-be-05) | wire defect | An owner axis that is available but unqualified has no permitted reason code |
| [STG02-BE-06](#stg02-be-06) | architecture gap | Delegated grant issuance (push-back 1): per-selection binding and no use limit |
| [STG02-BE-07](#stg02-be-07) | host or profile qualification deficit | No read-session issuer, and the driver sends no bearer (push-back 2) |
| [STG02-BE-08](#stg02-be-08) | architecture gap | Compare-and-fence holds across processes only if the key ledger and HEB share one store (push-back 3) |
| [STG02-BE-09](#stg02-be-09) | architecture gap | Retention (push-back 4): CS-04 makes the key ledger grow forever |
| [STG02-BE-10](#stg02-be-10) | wire defect | The owner GET declares no 400 or 401 |
| [STG02-BE-11](#stg02-be-11) | architecture gap | No read carries "held" for protected actions; `G3_unqualified` has no home |
| [STG02-BE-12](#stg02-be-12) | wire defect | `owner-operations` declares a 404 the contract gives no cause for |
| [STG02-BE-13](#stg02-be-13) | wire defect | A deployment serving a subset of the 20 reads has no defined answer for the rest |
| [STG02-BE-14](#stg02-be-14) | new feature or scope request | The provisional dashboard API, the browser origin, and where the adopted wire runs |
| [STG02-BE-15](#stg02-be-15) | wire defect | Read entitlement is defined for lookups; what a withdrawn entitlement does to a D-01 read is not |
| [STG02-BE-16](#stg02-be-16) | host or profile qualification deficit | AEW's engine has no per-recipient visibility, so its real records can be disclosed to one recipient only |

---

## STG02-BE-01

**Class:** wire defect.

**Clause.**
- `05-INTEGRATED-FIXTURES/new-command-refusal-reasons.json`, `$.CONTINUE_ELIGIBLE_WORK`: it lists only `DELEGATED_GRANT_UNVERIFIED`, `DELEGATED_INTENT_NOT_GRANTED`, `DELEGATION_EXPIRED` and `NOT_MODELLED`.
- `00-DESIGN/SELECTION-PROFILE-AND-SUBSTITUTABILITY.md` line 55: the map is "complete and fail-closed … a cause outside it is a model defect, never a default code".
- The adopted A-24 case N21 (`05-FIXTURES/cases.json`, "AEV HOLD/stale work cannot resume") expects `WORK_NOT_CURRENTLY_ELIGIBLE`. In A-24 that name is a `layer_b.py` verifier prefix (line 166), not a member reason code. `03-ORACLE/verify_adopted_replay.py` (line 109) puts N21 in `OWNER`, meaning unmodelled.

**What happened.** The handoff names N21 as an adopted reject case for this action. A real HEB owner check produces at least three outcomes the map does not cover:
- the work is not currently eligible (N21);
- the intent's predecessor, attachment or generation is stale against HEB's own state;
- HEB has no state for the work.

A fail-closed map means a backend that implements the owner check has no conforming reason code to send.

**Two readings.**
- (a) `PRECONDITION_STALE`: the eligibility basis the intent names is no longer current.
- (b) `AUTHORITY_REFUSED`: HEB refuses to continue the work.

N21's own wording ("stale work cannot resume") fits (a) better.

**Interim choice** (`src/aew/stg02/commands.py`, `SLICE_OWNER_REASONS`):
- not currently eligible → `PRECONDITION_STALE`, as an **allocated** owner refusal: `REJECTED`, `FAILED_CONFIRMED_NO_EFFECT`, with an owner `operation_ref`;
- stale predecessor → `PRECONDITION_STALE`, allocated;
- no HEB state → `HELD` / `SOURCE_UNAVAILABLE`, nothing allocated.

The adopted map is consulted first. The slice map is labelled interim and applies to `CONTINUE_ELIGIBLE_WORK` only.

**Coverage.** The driver has no N21 case. The repository covers it in `tests/integration/test_stg02_slice.py::test_n21_…`, and the recording is `recordings/command-202-n21-heb-work-not-eligible.json`.

## STG02-BE-02

**Status:** fixed by the designer in workspace commit `006f45b`: without `--now`, the driver checks each receipt at the instant its answer arrives. On the fixed driver's default clock this backend gave 35 passed, 0 failed, 6 skipped. The current output, from the driver at `75d30cf` with the config's synthetic bearer (BE-07), is 47 passed, 0 failed, 6 skipped ([`driver-output.txt`](driver-output.txt)). The text below is the entry as raised.

**Class:** implementation defect, in the conformance driver (non-normative tooling; neither this server nor the contract).

**Clause.**
- `driver/slice_driver.py` line 296 fixes `now` once, at the driver's start, with whole-second precision.
- Every 202 is then checked by `receipt_errors(request, b, now)`, which needs `observed_at ≤ now` (`03-ORACLE/command_admission.py` line 158).

**What happened.** A backend that stamps a receipt with its real admission time fails C1, C5 and C17-N01..N03 with `RECEIPT_INVALID_CURRENTNESS` whenever the receipt is issued a second or more after the driver started. That is nearly every receipt after the first. The fixture server passes only because its world clock is frozen.
- The default run gave 30 passed, 5 failed, 6 skipped; with `--now` set to the run's start plus 120 s, 35 passed, 0 failed, 6 skipped. Those outputs were committed at `b73021b1` and replaced after the fix (git history keeps them).

**Two readings.**
- (a) The driver should take "now" when it receives each answer.
- (b) "Current at a single instant" is intended, and the instant should be after the run (as the workaround does).

**Interim choice.** Neither the server nor the contract was changed; the workaround is the driver's own documented `--now` flag. Both outputs are kept. This is a driver erratum (working-method amendment 1, A2).

## STG02-BE-03

**Class:** architecture gap.

**Clause.**
- `HANDOFF-backend-lead-AEW-dev.md` lines 33–38 ("Never present a fixture fact as qualified"); the driver's R4.
- The 0.3.4 schema:
  - `SourceStamp.allOf`: `present_current` requires `qualified`;
  - `ReadResult.allOf`: `source_qualified` requires every item `present_current`;
  - `FR_OwnerAxis.allOf`: `ok` or `blocked` requires `qualified`;
  - `ReadOwnerOperations.allOf`: `qualified_scoped` requires a qualified `present_current` `collection_basis`.
- `00-DESIGN/consumer-expectations.json`: every positive recording expects `source_qualified`, and the partial continuation expects `limitations` to be exactly `["source_unavailable"]`.

**What happened.** The chain of rules is:
1. a fixture fact must be unqualified;
2. an unqualified stamp is never `present_current`;
3. a read with such a stamp is never `provided`/`source_qualified`;
4. an axis with such a fact can only be `unknown`;
5. an index page can only have `membership: unknown`.

So no envelope this backend serves can equal any recorded positive envelope. `matches_fixture` cannot honestly be set, and **R6 is SKIPPED on every read** by necessity, not by omission.

What the website gets is all-unknown. The directives `no_unknown_owners`, `list_closed` and `list_empty_closed` can never be exercised against a real backend until some owner is qualified. The fixture world also cannot express a fixture owner's *reported* state, such as "AEV reports a hold": the axis carries only a basis reference (`fixture:aev-hold-held`) and `state: unknown`.

**Two readings.**
- (a) This is the intended honest state of a pre-qualification slice. The positive views are validated only against the recordings.
- (b) A W0 fixture world was meant to be a "qualified world" whose stamps may be qualified *within* the world, as the recordings are.

**Interim choice.** (a), as the handoff requires. Every stamp is unqualified, every read is `partial`/`unknown`, and the R6 SKIP reason is this chain. The decision that would change it is whether a labelled fixture owner may ever issue a qualified stamp, and under which `issuer_ref`.

## STG02-BE-04

**Class:** host or profile qualification deficit.

**Clause.**
- D01-WR-12..14, via `00-DESIGN/OWNER-PIN-RULES.md` OP-03, OP-04, OP-06 and OP-09: a qualified stamp is the owner's own fact, with an owner-issued renewal (`source_proof_ref`, finite `valid_until`).
- `ReadResult.collection_basis`; `Renewal.description`: "Provider receipt timestamp never renews source conclusion".

**What happened.** AEW's engine is the real record for the work units (WIS facts: state, accepted plan revision, blockers) and for invocations and runs (R-01 progress facts). It issues no renewal, no proof and no validity interval, and no G1-qualified issuer exists. A backend-minted renewal would be the carrier renewing an owner's conclusion.

**Interim choice.** Real facts are stamped with their real identity and stay unqualified:
- `fact_ref`: `aew:work:<id>`, `aew:invocation:<id>` or `aew:waiting:<id>`;
- `source_epoch`: `aew:project:<id>`;
- `source_version`: `aew:rev:<n>`;
- `issuer_ref`: `aew:engine-state`;
- `qualification: unqualified`, `observation_state: unknown`, `renewal.kind: none`.

## STG02-BE-05

**Class:** wire defect.

**Clause.**
- `00-DESIGN/SELECTION-PROFILE-AND-SUBSTITUTABILITY.md` line 49: "a reason must be an exact qualified owner reason or a bounded source-unavailable transport reason".
- `FR_OwnerAxis.reason_code`: a free string.

**What happened.** An axis whose owner is reachable but unqualified (every fixture axis, and the real WIS axis) is neither. Calling it `SOURCE_UNAVAILABLE` would be false, because the source answered.

**Two readings.**
- (a) Use `SOURCE_UNAVAILABLE` for every non-qualified axis.
- (b) A bounded transport reason for "available, unqualified" is missing from the vocabulary.

**Interim choice.**
- `SOURCE_UNQUALIFIED`, with `qualification: unqualified` and the axis's `basis_ref`, `owner_epoch`, `source_version` and `observed_at` filled in.
- `SOURCE_UNAVAILABLE` with `qualification: not_established` and every field null, where the slice has no source at all.

## STG02-BE-06

**Class:** architecture gap. This is push-back 1, delegation issuance.

**Clause.**
- A-24 SW-04, as `03-ORACLE/command_admission.py` `_delegation` encodes it: the proof binds `intent_ref`, `actor_ref`, `installation_ref`, `recipient_ref` and `intent_digest`, the SHA-256 of the full canonical intent.
- `02-WIRE/extended-action-registry.json`, `CONTINUE_ELIGIBLE_WORK.preview_runtime` = `ONLY_WHEN_EXISTING_CURRENT_DELEGATION_ACTUALLY_QUALIFIES`.

**What happened.** The slice's issuer is `delegation:fixture`. Its records are the fields above plus `status` and `valid_until`, built from the world's intents when the server starts. Three things surfaced:
1. **The grant is per selection, not standing.** The digest covers the whole intent, including `predecessor.source_epoch`, `basis_ref`, `attachment_ref`, `generation_ref` and `work_revision`. An issuer must therefore know the exact intent before the operator selects the work, and any HEB epoch change invalidates every outstanding grant.
   - Who issues it, and when, is unanswered.
   - "Existing current delegation" reads as a standing grant, but a standing grant cannot be bound this way.
2. **No use limit.** Nothing in SW-04 or CS-01..09 consumes a delegation. The same grant admits the same intent under every new client key, and the driver's repeated runs did exactly that. A protected consent is consumed once per member (CS-06); a delegated grant is not.
3. **Revocation has one shape.** `status != CURRENT` is the only revoked form, and it maps to `DELEGATED_GRANT_UNVERIFIED`, not to a revocation reason. The operator therefore cannot tell "revoked" from "forged" (driver case C17-N01 accepts either code).

**Interim choice.** The issuer's records are computed from the world's intents (`src/aew/stg02/world.py`), so a delegation's digest and the configured intent cannot drift apart. A delegation is not consumed. Revoked is `DELEGATED_GRANT_UNVERIFIED`.

## STG02-BE-07

**Class:** host or profile qualification deficit. This is push-back 2, the session.

**Clause.**
- `02-WIRE/openapi-d01-v0.3.4-REVIEW-CANDIDATE.yaml` line 13 (`security: readSession`) and line 2391: an opaque bearer.
- The driver's `http()` sent no credentials, and its config had no auth field except on setup and teardown steps (the driver up to `006f45b`; `75d30cf` sends the config's `headers` on every request and adds the A1 check).

**What happened.** AEW has no read-session issuer. The A04 session is not used in the slice: `REAFFIRM_ELIGIBLE_CHILD_GRANTS` is refused `ORIGIN_NOT_ESTABLISHED` and nothing is allocated.

**Interim choice.**
- `--tokens` takes a file of synthetic opaque tokens, each mapped to a recipient. An unknown or malformed `Authorization` is `401 authentication_unqualified` (recorded).
- `--driver-bearer` writes one of those synthetic tokens into the driver config's `headers`, refused unless it maps to the world's recipient. The driver then authenticates like any client, and A1 passes (12 of 12).
- `--fixture-recipient` makes a request **without** `Authorization` act as `fixture:recipient-operator`. It is labelled, now used only by the response recorder, and the server warns when it is combined with `--project`.

## STG02-BE-08

**Class:** architecture gap. This is push-back 3, compare-and-fence across processes.

**Clause.**
- `00-DESIGN/SELECTION-PROFILE-AND-SUBSTITUTABILITY.md` line 31 ("compare-and-fence atomic in the competent HEB owner's linearizable state").
- CS-03, CS-04 and CS-08, lines 63–68: key lookup, then owner check, then one effect, as one step.

**What happened.** No problem *within the slice*. Each submission is one SQLite `BEGIN IMMEDIATE` transaction over one file that holds the key ledger, HEB's operation records and read entitlement (`src/aew/stg02/ledger.py`). The write lock is taken before the first read.

`tests/integration/test_stg02_fence.py` (serial lane) starts two real processes with the same key at the same instant, and holds each one's transaction open for 0.5 s after its key lookup, so the two lookups always overlap. Exactly one dispatches, the other replays the identical receipt, and HEB holds one operation. With the lock removed (a plain `BEGIN`), the test fails.

**What this does not show.** The fence was exercised on the **key ledger** only. The fixture HEB's state (its epoch, the work's eligibility) never moves while the server runs, so no test races a submission against a change in HEB's state: the slice does not demonstrate the bound that the BE-06 ruling assumes (an HEB epoch change invalidating outstanding grants at the moment of admission). The HEB outcomes are each tested from a fixed state: `HEB_STALE_PREDECESSOR` (an epoch changed before the submission) is an allocated `PRECONDITION_STALE`, and `HEB_STATE_UNKNOWN` (no eligibility for the work) is `HELD`, nothing allocated.

The atomicity depends on the carrier's ledger and HEB's state being **one store**. Once HEB is its own process or service, the model's single step becomes two commits, carrier and owner. A crash between them leaves either an owner effect with no stored receipt, or a receipt with no effect. The profile's lost-response path (`UNKNOWN_EFFECT`, reconcile by `(owner, operation_ref)`) covers only the first case, and only if HEB can be asked for an operation by the identity the carrier derived.

**Two readings.**
- (a) HEB must accept the carrier-derived operation identity as an idempotency key, so the carrier can always reconcile.
- (b) The carrier and HEB share one transactional store, which is a deployment constraint.

**Interim choice.** (b): one store, one host.

## STG02-BE-09

**Class:** architecture gap. This is push-back 4, retention.

**Clause.**
- CS-04 (line 64): "expiry alone never makes a request new, so a new effect needs a new key".
- CS-08: the stored receipt is returned exactly as issued.
- No duration is given anywhere.

**What happened.** The durations had to be chosen (`src/aew/stg02/ledger.py`):

| What | Kept for | Then |
|---|---|---|
| Receipt validity (`source_valid_until`) | 900 s after issue (`receipt_valid_s` in the world) | An identical retry is `409 unresolved_no_redispatch` |
| Stored receipt and member outcomes | 7 days after expiry | Dropped |
| The key and its request digest | **Never dropped** | A key whose receipt was dropped is `409 unresolved_no_redispatch` |
| HEB operation record | 30 days after issue | The owner GET is the nondisclosing 404, and the record leaves the `owner-operations` list. Enforced on every read, so it holds before the purge runs (the purge runs only on a submission) |
| Owner GET observation | 900 s (`owner_observation_valid_s`) | HEB re-observes its own record on each GET |

Under CS-04, a key can never be forgotten. If a dropped key came back as unused, a lost response's retry would dispatch a second time. The key ledger therefore grows without bound: one row per key per `(installation, recipient)`, forever.

**Two readings.**
- (a) Keys are kept forever, so the contract should say the ledger is unbounded.
- (b) Keys may expire after a bound the contract states. Clients must then never retry past it, and the contract should name that bound.

**Interim choice.** (a): tombstones are kept forever. The tests are `test_an_expired_entry_is_unresolved_and_a_dropped_receipt_never_makes_the_key_new` and `test_an_owner_record_past_its_retention_is_never_disclosed_even_before_any_purge`.

## STG02-BE-10

**Class:** wire defect.

**Clause.**
- `02-WIRE/openapi-o01-extended-REVIEW-CANDIDATE.yaml` line 115: `GET /o01/v0/owner-operations/{owner}/{operation_ref}` declares 200, 404, 409 and 503 only.
- `http-problem-matrix.json` has no 400 or 401 row for it.
- Profile rule 2 (line 12): "a v0.2 endpoint refuses a mismatched header/body".

**What happened.** A malformed path, an absent or 0.1 `X-AEW-O01-Wire`, and an unauthenticated request have no declared status on this route. On the POST route the same conditions are 400 and 401.

**Two readings.**
- (a) Every one of them is the nondisclosing 404, consistent with "a refusal is a nondisclosing 404".
- (b) The route should declare 400 and 401 like the POST.

**Interim choice.** (a). Tested in `test_owner_get_is_one_nondisclosing_404_for_unknown_foreign_and_malformed`.

## STG02-BE-11

**Class:** architecture gap.

**Clause.**
- `handoff/SLICE-FIELD-MAP.md`, step 6: protected actions are "shown as held … `limitations: G3_unqualified`".
- `ReadResult.limitations` includes `G3_unqualified`.

**What happened.** None of the slice's reads lists actions, so no response carries "close" or "reattach is held". The only place a held protected action exists is a command receipt, *after* the operator tries it.

**Two readings.**
- (a) The website shows protected actions as held from its own static knowledge of the registry, and a read's `G3_unqualified` is the deployment-level fact that justifies it.
- (b) A read, for example a capability or attachment read, should carry per-action availability.

**Interim choice.**
- `G3_unqualified` is included in the limitations of `continuation-state` (where the operator decides what to do next) and `owner-operations`.
- A protected set without G3 is refused per intent with `ORIGIN_NOT_ESTABLISHED`, nothing allocated, no owner operation.
- A protected set without a `consent_set_ref` is `400`.

## STG02-BE-12

**Class:** wire defect.

**Clause.** `GET /v1/read/owner-operations` declares a 404, and the matrix has its row, but no clause says when a list read is "not found".

**Interim choice.**
- A `scope_ref` that is not the recipient's disclosed scope → 404.
- An `owner` filter outside the O-01 owner enum → 400.
- An unknown query parameter, on any route → 400.

## STG02-BE-13

**Class:** wire defect.

**Clause.** Profile rule 1 (line 11) binds a route group to one D-01 version. The adopted wire has 20 reads, and the slice serves 4.

**What happened.** The answer for the other 16 on a 0.3.4 deployment is undefined.

**Two readings.**
- (a) `404 not_found_or_not_disclosable`.
- (b) `200` with `outcome: unsupported`.

**Interim choice.** (a), with the D-01 headers. It is never `200`.

## STG02-BE-14

**Class:** new feature or scope request.

**What happened.**
- **Two contracts, two processes.** The repository's dashboard server (`src/aew/dashboard/server.py`) serves the provisional contract (`docs/design/dashboard-api-v1-provisional.yaml`, `/api/v1`). It is GET/HEAD only, authenticates by its own session cookie, and puts a strong `ETag` and `304` on every 200. A `304` would be a D-01 answer without `X-AEW-Wire-Version`.
  - The slice therefore runs as its own process (`python -m aew.stg02.server`, port 4261). It reuses only the engine's lock-free state reader (`aew.dashboard.reader.StateReader`), and none of the provisional envelope, routes or projections.
  - Values that both contracts compute come from the same engine records: work state, blockers and invocation status.
  - The operator decides later whether the adopted wire is mounted in the dashboard process, replaces `/api/v1`, or the two coexist.
- **The browser origin.** The website runs on another origin (port 4251). The adopted wire says nothing about CORS or a same-origin proxy. Interim: `--allow-origin <origin>` (exact match) adds CORS for named origins only; by default every request carrying another `Origin`, or a `Host` other than the bound loopback address, is refused with the route family's own Problem (`400 invalid_request`; the owner GET's `404`), wire headers included.
- **No `aew` command.** The slice adds no `aew` command (so no surface-map entry). It is started with `python -m aew.stg02.server`. A supported command, and its surface-map entry, are part of the same decision.

## STG02-BE-15

**Class:** wire defect.

**Clause.**
- CS-04 (line 64): current read entitlement qualifies **lookups**: an identical retry and the owner GET (SW-07, SW-08).
- D-01: every read "is qualified for the authenticated recipient", and the 404 means "not found or not disclosable".
- No clause says what a recipient whose read entitlement is withdrawn gets from a D-01 read.

**Two readings.**
- (a) Entitlement is the recipient's read right everywhere: every D-01 read answers the nondisclosing `404`, as the lookups do.
- (b) Entitlement is an O-01 reconciliation fact only. D-01 reads stay governed by their own disclosure policy, and keep answering.

**Interim choice.** (a). While the entitlement is withdrawn, every D-01 read, the owner GET and every lookup answer `404 not_found_or_not_disclosable`. A submission under an unused key is still decided by its origin (the profile's accepted residual LEAD-F21). Test: `test_a_lookup_after_read_entitlement_is_withdrawn_is_one_nondisclosing_404`.

**Entitlement is stated, never presumed.** CS-04 step 1 refuses a lookup when the recipient lacks current read entitlement "or the world does not state it". The fixture world states it (`read_entitled`: the operator and the other recipient), and the server records it at start; a withdrawal is recorded and kept across restarts, and a grant the world no longer states is dropped at the next start. A recipient the world does not name, even with a valid token, is not entitled: every read is the nondisclosing `404`, and the test-only route cannot grant it. Tests: `test_a_recipient_whose_read_entitlement_the_world_does_not_state_is_never_entitled` and `test_a_grant_the_world_no_longer_states_ends_at_restart_and_a_withdrawal_survives_it`.

## STG02-BE-16

**Class:** host or profile qualification deficit.

**Clause.**
- D-01: every read "is qualified for the authenticated recipient", and a hidden member changes nothing the recipient sees.
- `handoff/SLICE-FIELD-MAP.md`, rule 2: real owner facts where AEW has them.

**What happened.** AEW's engine records (its work units, invocations and runs) have no recipient. Any recipient the server authenticates would see all of them, which the fixture world's other recipient must not: for that recipient, real records would be a disclosure the engine never decided.

**Two readings.**
- (a) AEW's records belong to the installation's one operator. Disclose them to one named recipient, and to everyone else they do not exist.
- (b) The engine gains per-recipient visibility (a disclosure policy over work and runs) before real records are served to more than one recipient.

**Interim choice.** (a). `--real-recipient` names the one recipient AEW's records are disclosed to (default: the fixture world's operator). Every other recipient gets no `aew:` item in a list, and the nondisclosing `404` for a real run or work id, the same answer as for an id that does not exist. Test: `test_real_aew_records_are_disclosed_to_the_one_real_recipient_and_to_nobody_else`.

---

**A-23 fixtures (the designer's note of 2026-10-19).** No entry is needed. This backend copies no stamp or qualification value from `LEGACY/F01`, `F32`, `NEW/F03` or `F04`; it used F01 and F05 only to see body shapes. Every stamp it emits is a real `aew:` record or a `fixture:` value, both unqualified. No test treats an A-23 fixture as proof: the tests check every body against the vendored 0.3.4 schema and assert their own rules (labels, no qualified stamp, informational-only, recipient scope).

---

<!-- Website entries; merged without interpreting or changing the existing main-line register. -->

# STG-02 website gap entries

Date: 2026-10-19. Author-side entries for designer triage. No architecture-workspace changes. Classes below use the handoff's vocabulary. An observation is not a reopened contract boundary or an acceptance verdict.

## WEB-STG02-001 — coherent fixture journey is not supplied by the named examples

- Class: **host or profile qualification deficit**.
- Source: adopted A-23 `04-FIXTURES/LEGACY/F01-waiting-positive.json`, `$.items[*].data.work` and `$.items[*].links`; A-23 `04-FIXTURES/NEW/F05-run-multiaxis-HEB-observed.json`, `$.items[0].data.work_ref`; v0.5.4 `05-INTEGRATED-FIXTURES/continuation-full-http-200.json`, `$.body.items[0].data.work_ref`; `command-requests.json` top-level keys.
- Observation: the waiting example names `T-A` and `STORY-1`, without a run link; the run names `invocation:demo-1` with null work; continuation names `ticket:one`. The integrated command examples contain attach, reattach and reaffirm, not inherited C17. These examples cannot themselves establish the one-work-item journey.
- Plausible readings: examples are independent specimens and the slice needs a separately labelled coherent fixture world; or they were intended as a directly navigable story. The latter is unsupported by their bindings.
- Interim choice: validate examples independently, never infer a run/work relation or rewrite it in the browser. Extract inherited C17 from adopted A-24, then distinguish any explicitly authored synthetic journey fixture from immutable recordings. Do not claim end-to-end journey coverage until all bindings are explicit and validated.
- Status: addressed for the author fixture journey by an explicitly derived, unqualified waiting/run fixture: same supplied `ticket:one` and `revision:one`, plus a supplied source link to `invocation:demo-1`. Original recordings remain unchanged. Browser construction/guessing is not used. Designer triage and real joint bindings remain pending; no wire change requested.

## WEB-STG02-002 — historical fixture time versus current qualification

- Class: **host or profile qualification deficit**.
- Source: v0.5.4 `05-INTEGRATED-FIXTURES/continuation-full-http-200.json`, `$.body.projection_as_of`, `$.body.items[0].source.renewal.valid_until` and axis `valid_until`; A-23 waiting/run `source.renewal.valid_until`; selection profile section “Reason and observation contract”.
- Observation: recordings describe finite validity intervals at their recorded clock. The referenced A-23 recordings expire before the date of this implementation; new recordings expire during 2026-10-19. Replaying today cannot establish current owner facts merely because HTTP just succeeded.
- Plausible readings: replay is explicitly at the recorded fixture clock; or a current demo uses fixture-issued unqualified observations. Silently advancing timestamps is neither.
- Interim choice: show a clear recorded-fixture identity and its as-of/last-known times; never renew or upgrade owner qualification in the browser. A current synthetic world needs separate fixture provenance and explicit unqualified stamps. Preserve immutable original recordings.
- Status: author fixture host and desktop/phone rendered checks completed. Designer triage and real source/currentness qualification remain pending; no contract amendment requested and no independent acceptance claimed.

## WEB-STG02-003 — retention duration remains an owner/host choice

- Class: **architecture gap**.
- Source: handoff field map “Where the design is expected to bend”, item 4; adopted selection profile CS-03/CS-04/CS-08, client key/ledger lifetime and expired-ledger behavior.
- Missing: a selected operational duration for request keys, receipts and owner records; schema timestamps and expired-ledger behavior do not specify that duration.
- Plausible readings: a host sets a documented finite retention policy; or retention is an additional selected profile requirement. The website cannot choose the owner's ledger duration.
- Interim choice: no browser-based expiry causes redispatch. Preserve an unresolved submission's exact request identity for reconciliation and show unresolved/unknown when the owner cannot establish it. Website-local recovery uses origin-local, package-digest-keyed tab sessionStorage for this one synthetic recipient/installation; its lifetime is the tab session, not an owner-ledger promise. Storage failure prevents sending a new command. Reload never automatically resubmits.
- Status: open design feedback; does not block fixture UI construction. Run 1's operator-relayed owner observation reports a 15-minute receipt and an operation retained until 2026-11-20. These test-host choices do not select an adopted retention policy. Backend implementation has not been inspected or retention negotiated.

## WEB-STG02-004 — pre-qualification waiting-to-run navigation

- Class: **host or profile qualification deficit**, for designer triage.
- Source: shared `JOINT-TEST-BRIEF.md`, steps 1–2; actual joint-run waiting responses, all supplied `links` arrays empty.
- Observation: waiting work cannot open its run through a supplied eligible link. A separately provided fixture run ID lets the test continue, but does not make that journey connected.
- Interim choice: preserve the absence of a supplied link. Do not manufacture associations from work IDs, prose, timestamps or the test world's known topology.
- Status: open; tracked as JT-01 in `JOINT-TEST-NOTES.md`. No frontend workaround or adopted wire change.

## WEB-STG02-005 — interim continuation reason vocabulary

- Class: **wire defect**, provisional semantic-vocabulary classification for designer triage.
- Source: shared joint brief step 3 and its BE-05/E-2 warning; actual continuation axis `reason_code: SOURCE_UNQUALIFIED`.
- Observation: the adopted structural schema accepts a string, while the brief explicitly identifies this value as interim rather than adopted vocabulary. Structural acceptance does not settle semantic adoption.
- Interim choice: render the exact supplied reason with unknown/unqualified state; assign no inferred meaning, qualification or command permission.
- Status: open; JT-02 in the website notes. This differs from the backend's JT-02 name for the encoded owner-locator defect (website JT-03).

## WEB-STG02-006 — controlled response-loss staging

- Class: **host or profile qualification deficit**, limited to test staging.
- Source: shared joint brief's lost-response probe; run 1's held-response and wrapper-stop timestamps.
- Observation: the application deadline elapsed before the wrapper was stopped. Identical-body reconciliation worked, but a wrapper-stop-only cause was not isolated.
- Interim choice: preserve the failed staging and distinguish timeout/lost-reply recovery from the strict requested variant. A fresh-state rerun must record its actual fault mechanism and timing rather than inherit a blanket pass.
- Status: run 1 remains limited (JT-04); run 2 is recorded separately in the joint notes. This requests no contract change.

## Clarification incorporated — unwitnessed A-23 examples

The operator's later 2026-10-19 field-map clarification identifies F01/F32/F03/F04 as shape examples without independent witnesses, and F05/F13 as witnessed. No new gap entry or contract reopening is requested: the independent intake already claimed structural checks only. The website renders stamps as supplied, never as a locally proven guarantee. Derived waiting/run fixtures use explicit `fixture:` references and unqualified stamps. The source recordings and sealed archive are unchanged.
