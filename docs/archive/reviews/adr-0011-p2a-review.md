# Independent review: ADR-0011 P2a cold store

Reviewed branch: `impl/adr-0011-p2a-cold-store`.

Reviewed commit: `64c5a22fd91d4c5e3cb422f34935b1f1ee56b3e2`.

Baseline: `c380aea781736541c3a5f30a5ed4f8bc36227a7f` (`main`, the merge base).

The review uses an archive of the requested commit. The working checkout's uncommitted P2b archival changes are outside its scope. Requirements came from ADR-0011, its approved implementation plan (especially R1, R8 and P2a), and the storage investigation. No implementation files were edited.

## Findings

### 1. High: tail validation permits dropping the committed prefix

Location: `src/aew/history/store.py:94-102` (`History.tail`), consumed by `append` at line 215.

The tail's starting chain state comes from the mutable file. Validation checks the segment reference and the end of the chain, but does not require `start.count` to equal the sealed boundary (or zero for the first tail). Moving `start` to the existing root and removing all entries therefore passes validation without changing the root.

Reproduction: archive three entries, settle an unrelated transaction, replace the tail's `start` with `{count: 3, h: root.head_h}` and its entries with `[]`, then archive a fourth record. `tail(root)` accepts the empty tail and the new archival commits at revision 3. Full verification subsequently fails with `history/tail.yaml does not hold the entries after 0`. The committed history now claims four entries but its tail contains only entry four.

Require the tail's starting count and chain anchor to match its actual position before accepting an append. Include first-tail and sealed-boundary controls and assert that refusal leaves the revision unchanged.

### 2. High: sealed-entry lookup returns data whose pinned hash is wrong

Location: `src/aew/history/store.py:111-118` (`History.entry`).

The sealed lookup discards the segment's computed digest and checks only the returned entry's sequence number. It checks neither the entry's chain hash nor the segment's applicable pinned hash. This differs from tail lookup, which runs `tail(root)` validation.

Reproduction: archive 260 entries, then change entry seven's id in sealed segment one from `T-0007` to `T-7777`, leaving its sequence and hash unchanged. The root directly pins segment one's original file hash. `entry(root, 7)` returns `T-7777`; full verification rejects the same segment as a broken hash chain. Untampered lookup and verification both pass.

Validate the applicable pinned segment hash and entry integrity before returning a sealed lookup. ADR-0011 requires corruption to become a contradiction when accessed, not only during a later full audit.

### 3. Medium: an index lock timeout is treated as database corruption

Location: `src/aew/history/index.py:64-68` (`HistoryIndex.sync`).

`sqlite3.OperationalError`, including `database is locked`, inherits from `DatabaseError`. The catch therefore attempts to delete a healthy database after a lock timeout. A slow concurrent rebuild or writer can enter this path.

Reproduction on Windows: initialize a valid index, hold `BEGIN EXCLUSIVE` on another connection, and call `sync(root)`. After its 30-second timeout, the code attempts `unlink` and raises `PermissionError` / WinError 32, with `database is locked` as its context. Release the lock and `sync` returns `current`; the database was healthy. On POSIX, deleting an open database can also separate active connections from the replacement file.

Handle transient busy/locked errors separately from actual corruption. Preserve the file on contention; retry or report the lock failure.

### 4. Medium: corrupt manifest bytes escape verification as exceptions

Location: `src/aew/history/store.py:192-193` (`History.verify`); decoding occurs at lines 79 and 94.

Verification promises to report damage without raising, but catches only `IntegrityError` and `ValidationFailed`. Invalid UTF-8 raises `UnicodeDecodeError` before either can be produced. Filesystem read errors can similarly escape this reporting path.

Reproduction: archive one entry, verify the healthy history, then replace `history/tail.yaml` with bytes `ff fe 80`. `verify(root)` raises `UnicodeDecodeError` instead of returning a failed `Verification` containing the damaged path.

Normalize expected decoding and filesystem failures into integrity problems. Test both tail and sealed-file corruption.

### 5. Medium: malformed cache metadata does not trigger an index rebuild

Location: `src/aew/history/index.py:98-102` (`HistoryIndex._built`).

The metadata reader requires only `version` and `count` to exist, then accesses `h` directly and converts `count` without validation. These failures are outside the `DatabaseError` recovery handler.

Reproduction: build an index over four entries, then delete its `meta.h` row. `sync(root)` raises `KeyError('h')`. Set `meta.count` to `broken` instead and it raises `ValueError`. Deleting the derived database makes both fixtures rebuild successfully, returning all four entries; authoritative history is intact.

Validate cached metadata as a complete chain state and treat malformed or incomplete metadata as a rebuild condition.

### 6. Low: the cold-write benchmark mislabels its index catch-up workload

Location: `tools/perf/control_plane.py:665-676`; results are described in `eval/adr-0011/perf/README.md` as three-entry catch-up timings.

`fill_tail` appends setup records without synchronizing the index. The timed `index.sync(after)` then processes those setup records as well as the three measured archivals.

Reproduction: instrument the real `HistoryIndex.sync` return value while running `coldwrite([1000], ..., reps=3)`. The timed catch-up samples add **25, 256 and 256 entries**, not three. Consequently the committed median timing is for a different workload from its label.

Synchronize the index after filling the tail and before timing, assert that each timed catch-up adds exactly three entries, then rerun and update the affected measurements. This finding concerns the catch-up measurement; it does not establish a defect in append scaling.

## Validation

All runs used the project Windows Python 3.13 interpreter with this archive's `src` inserted first in `sys.path` and exported as `PYTHONPATH`.

- `pytest tests/unit/test_history_manifest.py tests/integration/test_history_store.py -n 4 -q -p no:cacheprovider`: **49 passed**, 24.22 seconds.
- `pytest tests/integration/test_store_processes.py -q -p no:xdist -p no:cacheprovider`: **16 passed**, 33.67 seconds. This includes real-process crash recovery and racing writers.
- `pytest --lane fast -n 8 -q -p no:cacheprovider`: **615 passed, 1 skipped**, 24.95 seconds. The skip requires a Git checkout; the review snapshot is an archive. The manifest unit tests also appear in this lane, so these counts are not additive.
- Independent executable reproductions: `review_p2a_probes.py` and `review_index_lock_probe.py`, retained beside this report. Positive controls passed. Probes mutate only disposable fixtures.

The prewritten-object probe also confirmed that later edits/deletions are detected by full history verification. Prewritten objects are verified at commit; this report does not classify the absence of an exhaustive rehash on every control read as a defect.

The full suite, Linux/Rocky validation, all performance sweep sizes, and nightly-strength seeded walks were not run. Existing seeded Engine walks do not yet invoke the new history library or its history-specific fault points; P2a's deterministic history crash tests do cover the introduced write points.

Recommendation: resolve the integrity and recovery findings before accepting P2a as the foundation for P2b.
