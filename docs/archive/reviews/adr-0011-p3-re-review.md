# PR #24: independent P3 fix re-review

**Target:** `1911894bdc6e7126d31a9de362d792a9b7421fee` (fix commit `1911894`).
**Previous review:** `c6caa4c42f63440c31578bc77cf4d5830a5c92e6`.
**PR base:** `8156f62c1d4a07ed31baa98239a4c507349ec881`.
**Final recommendation:** request changes. **P3-1 is resolved** in the original public composed reproduction. **P3-2 is partially resolved**, with two remaining Medium findings below. All requested Windows lanes and reproductions have completed; there are no test failures in those lanes.

## Scope and isolation

Read the PR comment and implementation plan §7.4, "Independent review fixes", and inspected all seven changed files. Read-only Git commands were used in the main checkout. The new head was frozen with `git archive` into this folder, with its own Windows Python 3.13 venv and editable project installation. No implementation files, PRs, or remotes were changed. All 377 archived source files matched the archive byte for byte (`review-source-verification.json`). The archive is retained as `frozen-head.tar`.

Review launchers explicitly use `CREATE_NO_WINDOW` for Windows children. A startup hook in this private venv also applies the flag to Python children, pytest workers, CLI helpers, and Git subprocesses.

## Original findings

| Finding | Current assessment |
|---|---|
| **P3-1, High: derived index became authority** | **Resolved in the original public composed reproduction.** An altered index entry rebuilds to the authentic entry; the shown title stays real, `history load` pins the real bundle hash, the dispatch pack contains no substituted text, and the committed dependency facts remain nonmutating with the real bundle hash. The canonical bundle and cold root remain unchanged. |
| **P3-2, Medium: incomplete evidence audit closure** | **Partially resolved.** The original reproduction now detects changed cited checks and changed/deleted logs in new archives. Two additional cases below still produce a passing full audit for changed evidence. |

The original reproduction helpers were copied unchanged from the previous frozen review. Results are retained locally alongside the helpers. The new integration test file is included in the full non-serial lane.

## Remaining findings, by severity

### P3-R1 — P2 / Medium: migration pins a cited check already changed after recording

**Location:** `src/aew/engine/archive_ops.py:371`, especially `_cited_checks`'s existence/hash check at lines 394–401, and `evidence_pins` at line 86.

The new archival code checks the ingested verification report against its recorded hash, but takes each cited check's current hash without validating the check's existing seal. Migration can therefore commit a known-invalid engine check as newly pinned historical evidence. The recursive audit verifies the new hash and parses its frontmatter, without checking that original seal, and reports success.

**Reproduction:** run the local helper with this folder's interpreter:

```text
.venv\Scripts\python.exe review_fix_boundaries.py
```

1. Build a real completed mutating v1 Ticket through `CP.make_template` (implementation, checks, review, verification, integration publication).
2. Append bytes to `.aew/evidence/T-0001/INV-0003-check-unit-4.md` before `migrate`. This check is cited by the accepted verification but was not directly ingested.
3. `E.scan` reports that the evidence was modified after recording.
4. Call the public `Engine.migrate` with the current Lead credential and revision: migration succeeds.
5. The archive's `cited_evidence` hashes the changed bytes. Public `history_audit(full=True)` returns `ok: true`, with 1 entry and 16 records checked.

**Evidence:** `review-fix-boundaries-verified.log`, records `changed_cited_check_before_migration` and `changed_cited_check_pin`.

**Required correction:** validate cited evidence's seal, schema, identity, work-unit binding, and kind before pinning it; refuse damaged evidence without advancing control. Add the pre-archival change case to the regressions. Preserve trusted file pins when extending closure.

### P3-R2 — P2 / Medium: existing v2 archives retain the original cited-check audit gap

**Location:** `src/aew/engine/archive_ops.py:62` (`pinned_records` only adds the optional new `cited_evidence` field); `src/aew/engine/migrate_ops.py:84` (already-v2 migration is a no-op).

The new closure is recorded only when a unit is archived. Existing v2 bundles from the previous head have no `cited_evidence`, so their accepted verification's referenced check files remain outside the full audit. Installing the fix does not extend their reachability or require an upgrade before claiming a successful full audit.

**Reproduction:** `review_fix_boundaries.py` copies the genuine completed, archived v2 project from the prior review into this new review folder before exercising it. The prior fixture is never modified.

1. Open that copy with the new engine. Its archive lacks `cited_evidence`; baseline full audit succeeds (1 entry, 10 records).
2. Append bytes to its verification-cited `INV-0003-check-unit-4.md`.
3. `E.scan` reports the changed evidence.
4. Public `history_audit(full=True)` still returns `ok: true`, with the same 10 records checked. Control remains unchanged.

**Evidence:** `review-fix-boundaries-verified.log`, records `pre_fix_v2_baseline` and `pre_fix_v2_changed_cited_check`.

**Required correction:** define and implement an upgrade/compatibility policy for existing v2 history. For example, authenticate old verification reports, discover and validate their referenced checks and file pins during explicit full verification, and record any new trusted pins through append-only history. If old records cannot be fully authenticated, report incomplete coverage or require an explicit upgrade instead of a clean full-audit result. Do not rewrite immutable bundles silently.

These are remaining gaps in P3-2's remediation, not two repeats of the now-fixed local-index substitution.

## Validation

Commands run through `review_launch.py`, which selects this folder's private interpreter and retains stdout, stderr, exit code and elapsed time.

| Check | Result |
|---|---|
| Fast: `run_review_lane.py -q -p no:cacheprovider --lane fast` | **620 passed, 1 skipped**, 16.56 s. Skip: spec tag probe needs `.git`; the archive has none. |
| Full non-serial: `run_review_lane.py -q -p no:cacheprovider -n auto --dist worksteal -m "not serial"` | **1,171 passed, 5 skipped**, 1,187.09 s (19m 47s). Includes all six new `test_history_integrity.py` tests. |
| Serial: `run_review_lane.py -q -p no:cacheprovider --lane serial` | **16 passed, 1 skipped**, 50.56 s. Run after non-serial and all probes completed. Skip: POSIX pty operator path. |
| Focused new integrity file: `run_review_lane.py -q -p no:cacheprovider -n 2 --dist worksteal tests/integration/test_history_integrity.py` | **6 passed**, 198.62 s. |
| Original public composed `review_p3_probes.py` | Completed, exit 0; authentic history/context/dependency facts, cache-loss counters, and direct evidence-change control verified. |
| Original `review_p3_audit.py` | Completed, exit 0; baseline clean, changed ingested and cited checks rejected, changed/deleted pinned log rejected. |
| Upgrade/pre-archival boundary probes | Both remaining gaps reproduced in `review-fix-boundaries-verified.log`, exit 0. |
| Actual perf clone positive control: `review_cloner_control.py` | Added one completed Ticket; full audit passes for 2 entries and 32 records. |

Historical CI or implementer counts are not substituted for this execution. The full non-serial skips are the absent Git tag checkout (1) and POSIX filemode/symlink cases (4). Thus the implementer's 1,172/4 and this archive's 1,171/5 differ by the Git-only test. `review-probe-verdicts.json` records assertions over the original and additional probe outputs. The boundary helper's first attempt had a reviewer argument error in the optional cloner control; it was corrected and the boundary cases rerun successfully. A separate cloner control verifies that one additional Ticket really was created.

This execution is Windows only: no new Linux/Rocky run, extended nightly crash/walk budgets, or timed performance sweep. The default crash and walk cases are included in the completed non-serial lane. After validation, all 377 tracked source files were checked again against the retained archive and remained identical; both original reproduction helpers are byte identical to their previous-review copies.

## What was checked and found sound

- The original local-index substitution is corrected across history show, loading into context, and a public dependency-creation transition, with matching authentic data and bundle hashes.
- Index query results are compared with the root-authenticated entry and the query predicate. Returned links are derived from authenticated entries rather than link rows. A cache row hidden by altered query columns is documented to require the explicit full index check; it is not accepted as invented authority.
- `resume` and `status` still make zero history walks after deleting local derived data in the original four-finished-unit probe. Default `harness status` rebuilds the missing index once, as documented; this is not a steady-state timing result.
- Full audits follow nested evidence file pins for newly created bundles. Advisory, recorded, and concurrent appended-root paths use the same nested callback. The six new tests verify advisory and recorded findings, unchanged verified root on damage, missing rows and invented links, lookup of cited evidence by id, and refusal to migrate a changed accepted verification report.
- The modified perf cloner correctly rehashes renamed logs in the executed two-completed-Ticket fixture; its full audit passes.
- Source changes are confined to the seven advertised fix files; frozen contracts and workflow definitions were not changed by this fix commit.

## Performance scope

The claimed 3,000-finished-Ticket `harness status` result (0.50 s versus 0.59 s) is an implementer measurement, not independently established here. No new timed benchmark was run: an idle measurement window was not established during this review. The cost claim remains unverified by this re-review. The cache/authentication changes were inspected and functionally exercised; those results establish correctness for the stated cases, not timing parity at 3,000 Tickets.

## Gate decision

The six advertised regressions and both original reproductions support the fixes on newly archived, initially valid evidence. The passing full lanes show no additional regression in their covered cases. The additional executable sequences demonstrate that P3-2's assurance is still incomplete at the archival boundary and for existing v2 history. Resolve P3-R1 and define/implement P3-R2's compatibility policy before treating the independent ADR-0011 gate as closed. Re-run these retained cases at the next frozen head.
