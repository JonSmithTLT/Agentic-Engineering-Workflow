# T4 prototype — knowledge records in the history manifest (`review/t4-knowledge-manifest`)

- **Status:** prototype of `ADR-0013-knowledge-storage-placement-draft.md` (approved by the designer with terminology edits, 2026-10-04), built by the independent architecture review on a branch of `tree/` from `dcd43f1`: `review/t4-knowledge-manifest`, exported as `T4-knowledge-manifest.patch`. Not for merge as is; it exists so that the M6b plan can diff against something concrete, as the T1 branch does for the typed surface.
- **What it proves:** D1 (five kinds, one additive schema change), D2 (records under `.aew/knowledge/`, immutable, in the redo record), D3 (versions and the fold; `knowledge_event_seq` is the manifest `seq`), D4 (dispositions as the generalized annotation; `about()`), D5 (receipts carry the outbox position; the cursor is a `linked("outbox", …)` lookup), D6 (hot state gains counters, `knowledge.capture` and a bounded `knowledge.pending`), D7 (the entry's `source` is the most restrictive class), D8 (`about`, `current`, FTS5 `search`, all locators authenticated against the chain), D11 (no migration: a v2 project without the block works), D12 (index-only link checks on the full audit), oracle rule 29 (a disposition's subject precedes it), and the closed-transaction property of rule 28 as a test over what a knowledge commit changes.
- **What it does not build:** D9's service identity (the Lead commits in the prototype, through `lead_txn`), D10 beyond the constant `visibility_scope: project`, `lesson` and `reference` kinds beyond the schema enum (only `case` has a record schema and a command), the K1 template matcher (the record arrives composed), the pack-side rule, the dashboard projection, and `history list`'s default-kind change (D11's second half).

## 1. The branch

| File | Change |
|---|---|
| `src/aew/schemas/history.schema.json` | entry `kind` enum gains `reference, case, lesson, disposition, receipt`; optional `version` (integer ≥ 1) |
| `src/aew/schemas/control.schema.json` | a `knowledge` block (`capture {last_receipt, through_revision} | null`, `pending` (≤ 20 items), `pending_overflow`), forbidden on v1 like the other v2 keys |
| `src/aew/schemas/knowledge-{case,disposition,receipt}.schema.json` | the three record schemas (`aew/knowledge/{case,disposition,receipt}/v1`), from the drafts' field lists; registered in `schemas/__init__.py` |
| `src/aew/history/manifest.py` | `CONTENT_KINDS`, `KNOWLEDGE_KINDS`, `ENTRY_KINDS` extended |
| `src/aew/history/store.py` | `RECORD_GLOBS` covers `knowledge/**`; `knowledge_rel`, `disposition_rel`, `receipt_rel` |
| `src/aew/history/index.py` | `about(subject, kinds)` (annotations become a special case), `versions`, `current` with `fold_dispositions`, an FTS5 table over knowledge record bodies filled at sync and dropped at rebuild, `search(query, kinds, limit)` with a phrase fallback for text FTS5 rejects, kind filtering in SQL so a planted row is dropped rather than read as index disagreement; `_insert` is an instance method now |
| `src/aew/engine/knowledge_ops.py` | `Knowledge`: `knowledge_case` (case + initial disposition + receipt in one `lead_txn`, records staged with `History.write_record`, entries appended through `ctx.entries`), `knowledge_dispose` (one disposition, `disposition_seq` from the index, pending list maintained), `knowledge_show` (record verified against its entry, fold, trust label), `knowledge_list`, `knowledge_search`; `knowledge_problems(index)` for the full audit |
| `src/aew/engine/history_ops.py` | the full audit appends `knowledge_problems` |
| `src/aew/engine/api.py` | wiring; `aew init` writes the `knowledge` block and three counters |
| `src/aew/cli/knowledge_commands.py` (+ registration) | `aew knowledge case --file FILE|- [--hold] [--job-revision N] [--job-index I] [--template-set S]`, `dispose <K> --rel R [--object O] [--decision D] [--note] [--policy-version] [--serving]`, `show <K>`, `list [--kind] [--limit]`, `search QUERY [--kind …] [--limit]` |
| `tests/helpers/invariants.py` | rule 29 in the cold walk |
| `tools/perf/control_plane.py` | the v1 fixture (`make_template`) drops the `knowledge` block as it drops `cold`: it fakes a v1 project by downgrading `aew init`'s output, so every v2-only key `init` writes must be named there (see §3) |
| `tests/unit/test_dispatch_decision.py` | the five `knowledge` commands classified as not dispatching in `NOT_DISPATCHING` (the CLI enumeration that proves no command bypasses the dispatch registry) |
| `tests/integration/test_history_surface.py`, `tests/integration/test_archival.py` | their hand-rolled v1 projects also drop the `knowledge` block |
| `tests/integration/test_knowledge_manifest.py` | 8 in-process tests over the deterministic history workload: kinds and versions; a capture commit verifies and indexes; dispositions fold in order; the fold is pure; search finds bodies and authenticates hits; a tampered FTS row hides and never invents; an orphan under `knowledge/` is reported |
| `tests/integration/test_knowledge_surface.py` | 6 CLI tests on a real project: one commit admits case + disposition + receipt and changes only the allowed hot keys (rule 28); engine-owned fields refused and the schema enforced; show, list, search and the ADR-0011 surface (`history show/list/links`) read the same record; a held candidate is pending until a disposition settles it; the full audit covers the records and catches a damaged disposition while `resume` and `status` run; a crash at `history.after_tail` inside a capture commit leaves the old or the new history and the next capture succeeds |

## 2. Decisions the prototype made that the ADR left open, for the designer to confirm or reverse

1. **`dispositions` live beside the content versions** (`knowledge/cases/K-0001/dispositions/0001.yaml`), numbered per subject, so one directory holds everything about a record, as a unit's directory does. The index computes the next number; the stored `disposition_seq` is checkable.
2. **The initial disposition is written by the capture commit itself** (`admitted` or `held_active`), so a record never exists without an admission state, and the receipt names it.
3. **The entry's `source` for a case is the most restrictive field class** (`ROLE_ATTESTED` → `model`), and the serving envelope of an engine-only case is `case_recall`, otherwise `explicit_investigation_only`, recorded on the admission disposition, not on the content.
4. **Search accepts FTS5 expressions and falls back to a phrase** when FTS5 rejects the text (a hyphenated id, stray operators), so a Lead's literal query never ends in a syntax error.
5. **`knowledge list` without `--kind`** lists knowledge kinds only; `history list` is unchanged (it shows everything newest first, knowledge entries included), which is the opposite of ADR-0013 D11's suggestion and is the simpler thing to reverse.

## 3. Evidence

New tests: 14 pass. Regression lanes and static checks: see the line appended below after the run.

**Regressions the lanes found, all in test fixtures, none in behaviour.** The first run (22 failures in `test_migration.py` and `test_history_integrity.py`): the v1 project fixture in `tools/perf/control_plane.py` is `aew init`'s v2 output with `schema` rewritten and `cold` popped, so the `knowledge` block `init` now writes survived the downgrade and v1's `not anyOf` rule refused the file. Fixed in the fixture (pop `knowledge` too). The point for the ADR: the set of v2-only hot keys is spelled out in three places (the schema's v1 exclusion list, the fixture, and `init`), with no shared constant; any key ADR-0013 adds has to be added to all three. `aew migrate` is unchanged and correct under D11 (a migrated project has no `knowledge` block until its first capture), which the migration suite now confirms against the new schema. The second run (3 failures): two more hand-rolled v1 projects with the same downgrade (`test_history_surface.py`, `test_archival.py`), and the DispatchDecision CLI enumeration, which refuses any new command until it is registered as a dispatch entrypoint or classified as not dispatching; the five `knowledge` commands are classified. Both are the kind of check the branch is meant to hit: a new command family and a new hot key each have a registry to join.

**Evidence line.** Regression lane (`tests/unit`, `test_history_store`, `test_history_surface`, `test_history_integrity`, `test_archival`, `test_migration`, `test_spec_pin`, the two new files), Windows, Python 3.13: 865 passed, 1 skipped (xdist absent), 3 failed, in 17m58s; the 3 fixed as above and rerun with the whole dispatch-decision file: 27 passed. Full `test_migration.py` rerun after the first fix: 10 passed. `ruff check` clean on `src/aew`, the fixture and the changed tests; `pyright` 0 errors on the changed `src/aew` modules (`tools/perf/control_plane.py` is outside the project's pyright include and reports 49 pre-existing errors unrelated to the one-line edit). Commit `a9a9cd9` on `review/t4-knowledge-manifest`; `T4-knowledge-manifest.patch` is `git format-patch dcd43f1..a9a9cd9`. Measured on the prototype's own fixtures, not at scale (the scale numbers are in the ADR draft's probe, `repro/knowledge_manifest_probe.out.txt`).

## 4. How to run

```bash
git -C tree checkout review/t4-knowledge-manifest
.venv/Scripts/python -m pytest -q tree/tests/integration/test_knowledge_manifest.py tree/tests/integration/test_knowledge_surface.py
git -C tree checkout docs/restructure
```

The venv runs whatever `tree/` has checked out; return to `docs/restructure` so `HANDOFF.md` §6's check holds.
