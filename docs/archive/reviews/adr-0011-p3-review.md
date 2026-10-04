# ADR-0011 P3 independent review — gate before M4

**Recommendation: request changes.** Two independently reproduced defects prevent closing ADR-0011: a derived index can substitute authoritative history and commit false dependency facts (P1), and the full audit misses part of the durable evidence closure (P2). These defects are in the merged P2 implementation, which is explicitly part of this whole-ADR review.

## Frozen scope and isolation

- PR #24: `impl/adr-0011-p3-acceptance`, frozen head **`c6caa4c42f63440c31578bc77cf4d5830a5c92e6`**.
- PR base: `8156f62c1d4a07ed31baa98239a4c507349ec881`.
- Preimplementation baseline: `0eb8ecf80c7103e9762967c617f64380e0ba52b3`.
- Reviewed E5, P2a–P2d and their merged fixes, plus P3's runtime changes, acceptance tools and supplied measurements. Read the reviewer brief, ADR-0011, ADR-0001, implementation plan including §7.4, and performance README §5–§7.
- Extracted the head using `git archive` into this new folder; separate `base/` and `baseline/` archives preserve comparison sources. The private `.venv` uses Windows Python 3.13.1 and an editable install pointing to this folder's `src/aew`.
- The main checkout was used only for read-only Git commands. No implementation files, branches, PRs or remote state were changed.
- Review helpers launch Windows children with `CREATE_NO_WINDOW`. A private venv startup hook also applies it inside pytest workers and subsequent Python children; `review-startup-check.json` verifies child behavior. The final lane logs use this hook.
- `verify_frozen_source.py` compared all **376 tracked files byte for byte** with a fresh archive of the frozen head. Frozen contract and workflow documents are unchanged against the preimplementation baseline.

## Findings, by severity

### P3-1 — P1 / High: authenticate indexed entries before using their record pins or facts

**Locations:** `src/aew/history/index.py:89–96,156–167`; downstream `src/aew/engine/archive_ops.py:519–545,562–566`, `history_ops.py:87–100,209–238`, `context_ops.py:116–135`.

**Contract:** ADR-0011's integrity decision and invariants 2 and 14; the reviewer brief explicitly defines authority as the hot control document plus records reachable through the cold root's hash chain. `local/history.sqlite` is derived and never authority. This is about detecting an unsynchronized change within the repository trust boundary: the reproduction does **not** rewrite the authoritative cold content and hot root together.

**Cause:** `HistoryIndex._sync()` accepts matching SQLite `meta.count/h` as a current index without authenticating its rows. Queries then return the row's JSON entry body. `Archive.record()` verifies the payload against the path and hash supplied by that unverified body, rather than an entry established as a member of the root's chain. A healthy SQLite database with altered row content is therefore trusted. `facts_from_cold()` additionally stamps the real canonical bundle's hash onto facts read from the substituted payload.

**Executed reproduction:** `review_p3_probes.py --cache-only`, output `review-p3-cache.jsonl`; the earlier complete sequence is also preserved in `review-p3-probes.jsonl`.

1. Finish a real investigation, `T-0001`, through the public CLI; populate the history index with `history show`.
2. Leave `control.yaml`, the authoritative archive bundle and the manifest untouched. Add `local/forged-archive.yaml`, copied from the bundle with a changed title, `mutating: true`, and a fabricated integration commit of forty `a` characters.
3. Change only the SQLite entry's JSON body/path/payload hash to name this local file. Keep the original sequence, chain hash and root metadata.
4. `history show T-0001` returns the forged title and `trust.source: engine`. `history audit --full` still returns `ok: true`; the authoritative bundle and cold root are unchanged.
5. Load the record into new current work and dispatch it. Its pack contains the forged engine-history content, and its history reference pins the forged hash.
6. Create another current investigation depending on `T-0001:evidence`. AEW commits `archived_refs[T-0001]` with `mutating: true` and the fabricated integration commit, while `bundle_sha256` names the **unchanged real bundle**.
7. Delete the SQLite database and repeat `history show`. Rebuilding returns the real title again.

**Impact:** derived local data changes an exact historical identity, reference provenance, and durable facts used by current dependencies. Deleting the cache repairs the view but does not remove the false facts and history references already committed by authorized normal operations. The probe demonstrates an integrity/authority defect; it does not claim a credential-protocol or OS containment bypass.

**Required correction:** treat SQLite as a locator and acceleration structure. Authenticate any entry whose path/hash/source/links or facts will be consumed against the committed root before using it; for example, resolve its sequence through the verified manifest and compare the indexed identity. Reject or rebuild inconsistent cache content. Ensure derived facts and their bundle hash come from the same authenticated record. Cover altered JSON bodies, missing/changed rows and links, a purportedly current index, and an index ahead of the reader's root. Preserve bounded active paths when doing so.

### P3-2 — P2 / Medium: full audit stops before the transitive check and log evidence

**Locations:** `src/aew/engine/archive_ops.py:62–81,353–357`; `src/aew/history/store.py:284–298`; audit entry point `src/aew/engine/history_ops.py:265`.

**Contract:** ADR-0011's full-verification decision and invariants 2, 5, 6 and 12. Periodic full verification must cover the reachable durable corpus, and completed work's verification provenance must remain reconstructible.

**Cause:** `pinned_records()` enumerates only the bundle's immediate unit record, plans, ingested evidence and completion record. `History.verify()` hashes those immediate files but never follows their pins or validates verification reports' referenced engine checks. An ingested check record itself pins its durable log by path and SHA-256; that log is omitted. Accepted verification reports also refer to check-result IDs which are not necessarily separately ingested, so those check records are omitted from both the archive's evidence pins and its history lookup links.

**Executed reproduction:** `review_p3_probes.py` builds a real v1 mutating Ticket through implementation, review, ticket verification, integration verification and publication, then migrates it. `review_p3_audit.py` tests that fixture; results are in `review-p3-audit.jsonl`. These are real engine-created artifacts, not hand-built approximation records.

1. Full audit of migrated `T-0001` passes, reporting 1 manifest entry and 9 checked records.
2. Positive control: change the directly ingested `INV-0001-check-unit-1.md`. Full audit and `history show` correctly return `INTEGRITY_ERROR`. Restore it.
3. Change `INV-0003-check-unit-4.md`, a check cited by accepted `INV-0003-verify-6`. The ordinary evidence scanner detects the broken seal, but full audit still returns `ok: true`, `records: 9`, no problems. `history show` of that check ID returns `NOT_FOUND` even though it is recorded verification provenance. Restore it.
4. Change the log pinned by the directly ingested `INV-0001-check-unit-1.md`: `evidence/T-0001/logs/INV-0001-check-unit-1.log`. Its actual hash differs from the recorded hash. Full audit still returns `ok: true` with the same record count.
5. Delete that log completely. Full audit still passes. The helper restores the original after this negative control.

**Impact:** the explicit historical-integrity operation can report a clean corpus despite corruption or loss of durable test evidence supporting completed work. The missing check lookup also breaks traversal of recorded verification rationale through stable identities. These logs are under durable `evidence/`, not disposable `local/` packs.

**Required correction:** preserve and verify the authority-relevant evidence closure at archival/migration, including engine checks named by accepted verification and the durable files they hash-pin. Make those checks reachable by supported history identities/links. Walk the verified transitive pins with bounded cycle/deduplication handling during explicit audits; do not add a full historical sweep to `resume`. Add positive and negative tests for direct records, referenced checks, changed logs and missing logs, including the recorded audit/closeout gate.

## Validation

**The final required test lanes and extended probes are still running. This section will be completed before the review is handed off.**

The first fast run passed: 620 passed, 1 skipped. Its only skip was the tagged-revision test, because the user-required archive has no `.git`. A second fast and full non-serial run use the verified startup hook in every worker; serial follows them without concurrent probes.

Executed independent probes and results:

| Probe | Result |
|---|---|
| Derived SQLite payload substitution, history load, dispatch, dependency creation, cache-deletion control | P3-1 reproduced; authoritative cold bundle and root unchanged |
| Direct ingested check corruption | Correctly refused by full audit and exact history lookup |
| Accepted verification's referenced check corruption | P3-2 reproduced; scanner detects corruption, full audit misses it |
| Changed and missing hash-pinned check log | P3-2 reproduced in both cases |
| Delete all `local/`, then current `resume` and `status` | Zero `History.walk` calls and zero traversed entries; current reconstruction succeeds |
| Delete all `local/`, then default `harness status` | Rebuilds the index, walking 4/4 history entries; succeeds. This is the documented linear cache-rebuild cost, not steady-state timing evidence |
| Migration crash after prewrite → Lead handoff → retry | Exit 86 at crash, v1 remains; retry succeeds at generation 3, replaces unreachable stale Lead bundle, v2 oracle passes |
| Same-state migration retry; empty migration; repeated migration | All pass, including idempotent no-op at unchanged revision |
| Mixed open/closed hierarchy migration | Full reconstructed state preserved, 3 DONE + 1 CANCELLED archived, correct parent summaries, invariant oracle passes |
| Parent pack regeneration and late pre-migration parent review ingest | Packs match before/after migration, ingest succeeds with legacy digest compatibility |
| Snapshot fingerprint comparisons against PR base | Same result for clean, dirty, tracked/untracked `.aew`, declared ignored input, policy exclusion and staged-only edit; real Git index unchanged |

Preserved helpers/results: `review_p3_probes.py`, `review_p3_audit.py`, `review_p3_migration.py`, `review_p3_composition.py`, and their JSONL/stderr files. The initial broad helper deliberately hit the expected direct-evidence `INTEGRITY_ERROR`; the follow-up audit helper catches and records that control and completes the remaining negative cases. No implementation code was changed to obtain these results.

## Performance evidence checked

No new timed workloads were run on the shared busy host. `review_perf_evidence.py` recomputed the gate tables from the supplied JSON and independently checked required points/commands, absolute bounds, H1/H3/H4, and all six Windows A/B raw-sample medians and paired differences. All gate invocations return 0; `review-perf-summary.json` and `review-perf-*.md` preserve the results.

| Dataset | H1 hot growth, flat / hierarchy | Max H2 delta, flat / hierarchy | H3 at 20 open, 3,000 completed | H4 resume counters |
|---|---|---|---|---|
| Windows | 1.048× / 1.080× | +0.024 s paired / +0.036 s | 13.3 ms | identical |
| Ubuntu on WSL2 | 1.048× / 1.082× | +0.025 s / +0.076 s | 6.4 ms | identical |
| Rocky 8.10 userland on WSL2 | 1.048× / 1.082× | +0.018 s / +0.027 s | 7.0 ms | identical |

History's share at 3,000 is 7.6–7.7% flat and 12.6–12.8% hierarchy. The documented A1 slope and cold-write series were inspected separately: they distinguish growth with open work and bounded append/seal costs from intentionally linear full verification/index rebuild and growing old-entry chain proofs. The failing original one-sample Windows flat H2 result is explicitly retained and superseded by the six-round paired result, not silently relabeled as passing.

**Limits:** these are independently checked supplied measurements, not fresh measurements made by this reviewer. WSL2 Linux data are supplemental; Rocky's userland runs on WSL2's 6.18 kernel, not native Rocky 8's 4.18. Nothing here validates native-kernel containment work. Migration's roughly 90–108 second cost is a documented one-time operation; index preparation is best-effort after the authoritative migration commit.

## What was checked and found sound

Subject to the two findings and test scope above:

- E5 composition: explicit Kernel/collaborator wiring, complete per-kind registry, fail-closed guard resolution, ordered state hooks and archival transaction finalizer; existing composition tests are included in the required lanes.
- One mutable control commit point: staged immutable bundle/segment writes, before-hash tail replay, prewritten-object hash verification and bounded `last_transition` metadata. Current reads recover through the store; the extended and default crash cases exercise old/new state rather than a hybrid.
- Migration's merged retry fix handles allowed seat changes after prewriting. Mixed hierarchy reconstruction, aggregate maintenance, exact pack regeneration and legacy parent evidence were independently exercised.
- Removing `local/` leaves current `resume`/`status` complete without history traversal. Full direct-record audit and missing/changed bundle checks are present; P3-2 concerns deeper evidence closure.
- Historical reference source classification, verifier redaction, reference fencing and invocation provenance have dedicated integration coverage. P3-1 concerns whether the chosen entry is authenticated before those mechanisms consume it.
- P3's credential-map optimization retains current, run-rotated and otherwise issued credentials while avoiding repeated whole-token scans. Its migration index preparation runs after commit, outside the control lock, and index errors defer a rebuild rather than undoing committed migration.
- At the exact frozen SHA, GitHub CI run [37099182042](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/37099182042) completed successfully for Windows and Ubuntu lanes, including core/serial and the split integration/acceptance/regression/adversarial jobs. `review-ci-run.json` verifies `headSha`; `review-pr-checks.json` preserves the check list. These are remote CI results, distinct from this review's independent local execution.

## M4 disposition

Do not close ADR-0011 or use this review as approval to begin M4 until P3-1 and P3-2 are corrected and their public composed reproductions are rerun against a newly frozen fix head. Existing green CI and passing performance data do not cover these two failures.
