# Knowledge records in the history manifest: lessons from the prototype (2026-10-04)

- **What this is:** the lead developer's reading of the knowledge-manifest prototype that the independent architecture review built to test ADR-0013 before it was accepted. The branch (`review/t4-knowledge-manifest`, one commit on `dcd43f1`) is a testbed, not a candidate for merge. It was built against the ADR's draft, so the accepted ADR's tightenings (qualified kind names, the contiguous capture watermark, exact-version dispositions, the bounded vocabulary) are not in it.
- **Purpose:** keep what the prototype proved and the patterns worth reusing, and turn every issue it surfaced into a tracked requirement, so that the M6b plan starts from them rather than rediscovering them.
- **Governs:** nothing. This is a research testbed. [ADR-0013](../implementation/adr/0013-knowledge-storage-placement.md) is the rule (operator, 2026-10-04).
  - The prototype predates the accepted ADR, but that gives it no standing.
  - Every choice it made that the ADR does not make is an issue to fix (section 4), never a precedent.
  - The patterns in section 2 are kept only where the ADR allows them.
- **Evidence:** the review's prototype note and patch, and its runs on Windows (Python 3.13). The new tests passed (14); the touched regression lanes passed after the fixture fixes in section 3. Nothing here was measured at scale; the ADR's own probe has the scale numbers.

## 1. What the prototype proved

- **The manifest takes knowledge with an additive change.** The ADR-0011 manifest, chain, verification, derived index and the `history show/list/links/audit` surface accepted the five knowledge kinds with only the entry-kind enum and the kind list changed.
- **A capture is one transaction.** The Case, its initial disposition and the capture receipt are written in one commit, staged through the redo record, and the commit changes no work, invocation, token or Lead state.
- **The index stays a locator.** Dispositions fold into a current state in the derived index, and FTS5 searches record bodies with every hit authenticated against the chain: a planted index row can hide a record but never invent one.
- **Crash safety holds.** A crash inside a capture commit (at `history.after_tail`) leaves the old or the new history, and the next capture succeeds.
- **No migration is needed.** A v2 project without the knowledge block keeps working, and `aew migrate` is unchanged.

## 2. Patterns worth keeping

- **Engine-owned fields are refused on submission.** The engine assigns `schema`, `id`, `version`, `record_kind`, `authority_class`, `visibility_scope` and `created_at`, and a submission carrying any of them is refused by name.
- **The initial disposition is written by the capture commit**, so a record never exists without an admission state, and the receipt names it.
- **Search falls back to a phrase.** Search accepts FTS5 expressions and retries as a phrase when FTS5 rejects the text (a hyphenated id, stray operators), so a literal query never ends in a syntax error.
- **Kinds are filtered in SQL.** A planted row of the wrong kind is dropped, never read as an index disagreement.
- **The tests to carry forward:** one commit changes only the allowed hot keys; a tampered FTS row hides and never invents; an orphan record is reported; a crash mid-capture leaves old or new history; the full audit covers the records while `resume` and `status` read none of them.

## 3. Registry findings: the checks worked

- **The v2-only hot keys have no single definition.** The set of hot keys that only a v2 control file may carry is spelled out in three places: the control schema's v1 exclusion list, `aew init`, and the hand-written v1 project fixtures (in `tools/perf/control_plane.py` and two integration tests). Each fixture fakes a v1 project by downgrading `init`'s output. The prototype's new `knowledge` block broke 22 tests until each fixture also dropped it. Every new v2 hot key (M4-D's `queue` is next) will hit the same thing.
- **New commands must join the dispatch registry.** The `DispatchDecision` CLI enumeration refused the five new commands until they were classified as non-dispatching. That is the check working as designed; a new command family should budget for it.

## 4. Issues to address when ADR-0013 is implemented

Each item is where the prototype, built on the draft, falls short of the accepted ADR. None blocked the proof; all would be defects in production.

1. **Weak-boundary provenance must not earn default serving.** The prototype ranks `ENGINE_OBSERVED_WEAK_BOUNDARY` with `ENGINE_OBSERVED_CONTAINED`, so a weak-boundary Case gets the coarse source `engine` and the serving envelope `case_recall`.
2. **The capture status must follow the contiguous watermark.** The prototype records the newest receipt's revision as `through_revision`. It also defaults a job's origin revision to the capture transaction's own revision rather than the triggering event.
3. **A duplicate capture must return the prior receipt.** The prototype writes a second receipt for the same origin event, and no test covers it.
4. **Commit-time numbering must not trust the derived index.** The prototype computes the next `disposition_seq`, and with it the record's path, from the index. A lagging or planted row then gives a wrong or colliding number.
5. **Dispositions must target and sequence by exact version.** The prototype's entry `subject` is the bare Knowledge ID, so dispositions of different versions are counted together.
6. **The coarse source must follow the actual actor.** The prototype labels every decision-bearing disposition `operator`, which over-claims operator authority for a Lead's judgment.
7. **The vocabulary is the accepted one.** The prototype allows `visibility_widened` and `audit_finding`, which the accepted ADR excludes, and uses `superseded_by` and the unqualified kind names `disposition` and `receipt`.
8. **The record layout is the accepted one.** The prototype stores dispositions beside their content and lists many `knowledge/...` patterns in its record globs.
9. **The oracle numbering is the accepted one.** The prototype's knowledge rules are numbered 28 and 29, which collide with ADR-0012's rule 28.
10. **The `history list` default keeps the legacy kinds.** The prototype lists knowledge entries by default.
11. **Still to be built:** the service principal and its commit-boundary closure check (the prototype's Lead commits, so closure is only a test), and `PARTIAL` and `NO_CANDIDATE` receipts.
