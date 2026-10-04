# S7 — Large-repository behaviour: a synthetic 10k/100k-file structural benchmark and the C semantic extrapolation

- **Status:** probed fact plus extrapolation, independent architecture review, 2026-10-04 (thread S7 of the designer's second brief: "a synthetic 10k/100k-file structural + C semantic benchmark would tell us very early whether the extension model needs sharding, incremental caches, or a dedicated derived index"). Not governing. Probe: `repro/t5/synthetic_repo_bench.py` (builds a git repository of N small files in a depth-3 tree, two commits, times the Git primitives and the T5 structural generator); output `repro/t5/synth-bench.out.txt`. Ran on the Rocky 8 VM (4 cores, 7 GB), scratch under `~/.aew-test-tmp/review-synth`, removed. The C semantic side is **not** benchmarked synthetically (a synthetic C corpus would measure the generator, not the problem); it is extrapolated from the per-TU constants S1 measured on curl, which is the honest basis available.
- **Answer.** The structural map does not need sharding or a derived index at 100k files: 2.1 s and 162 KB, with the two Git primitives it depends on at 0.3 s and 0.02 s. The semantic map needs the incremental model from the first design (S4), not later: a 50k-TU first build is on the order of an hour single-core, and only the per-unit input sets keep later rebuilds at seconds. The one structural-side scaling concern is record size, which grows with the number of *directories*, not files, and is bounded by shortening what the map says about each directory.

## 1. Structural map [probe]

| Files | Build the repo | `git ls-tree -r` | `git diff --name-status` (0.5% of files touched) | ADR-only diff | Structural map, no imports | Record |
|---|---|---|---|---|---|---|
| 798 (AEW, real) | — | 20–40 ms | — | — | 0.11 s | 3.5 KB |
| 10,000 | 3.2 s | 30 ms | 6 ms | 4 ms | 0.28 s | 18 KB |
| 100,000 | 33 s | 286 ms | 18 ms | 17 ms | 2.1 s | 162 KB |

Linear in files for `ls-tree` and the directory pass; the diff primitives are proportional to the change, not the repository. The record grows with directory count (the synthetic tree has 750 leaf directories at 100k files; the map lists each with count, language and role), so a 100k-file repository with a deep tree produces a map an order of magnitude larger than AEW's. **[rec]** cap the `directories` section at two levels plus a per-top-level summary, which is what the T5 note already specifies, and the record stays in tens of KB at any size.

Freshness at this scale is a `git diff --name-status --diff-filter=ADR` between two commits: 17 ms at 100k files. The listing-plus-config rule from the T5 probe costs nothing extra.

## 2. C semantic map [extrapolation from S1's constants; marked hyp where it is more than arithmetic]

Measured on curl: parse 29 ms and walk 117 ms per TU in Python; `clang-scan-deps` 2 ms per TU; deduplicated artifact about 3.9k symbols and 17k edges for 169 source files; per-TU dumps 100× larger than the deduplicated form.

| Scale (TUs) | First extraction, single core | 8 cores | Dependency index | Deduplicated artifact (est.) | Incremental rebuild after a median header edit (fan-out 5% of TUs) |
|---|---|---|---|---|---|
| 1,400 (curl, all) | 4 min [probe] | ~35 s | 3 s | few MB | ~10 s |
| 10,000 | ~25 min | ~3 min | 20 s | ~20 MB | ~1 min |
| 50,000 | ~2 h | ~15 min | 100 s | ~100 MB | ~5 min |
| 500,000 | ~20 h | ~2.5 h | ~17 min | ~1 GB | ~1 h |

[hyp] The walk is Python over libclang cursors; a C++ extractor against libclang or an index produced by clangd would cut the per-TU cost by 5–10×, which moves every row one column left. The dependency index is cheap at every scale and is the piece that must exist before anything else, because it is what makes the right-hand column possible.

**What the numbers say about the designer's three options:**

- **Sharding** (by directory or by configuration): not needed for the structural map; for the semantic map it falls out of unit identity (S2 §2): facts are already per unit and per configuration, and an artifact per top-level component is a packaging choice, not a redesign. Nothing in the contract would change.
- **Incremental caches**: required for the semantic map at ≥ 10k TUs and already the design (S4): per-unit input sets, per-unit re-extraction, atomic publication. The structural map does not need one.
- **A dedicated derived index**: yes for the semantic map, and it is the existing pattern: ADR-0011's `local/history.sqlite` is a derived, rebuildable index over immutable records; the semantic artifact wants the same (symbols, edges, unit membership, header fan-out in SQLite with FTS over names), rebuilt from the published artifact, never authoritative. At 100 MB–1 GB of facts, queries like `callers(X)` are index lookups, not file scans.

## 3. Where behaviour changes, not just cost [inf]

1. **Per-TU dumps stop being storable** well before 10k TUs (curl's library is 134 MB as dumps); deduplication by symbol identity is mandatory from the first version, not an optimization (S2 §6).
2. **A whole-repository first extraction becomes a scheduled job, not a command**: at 50k TUs it is a quarter-hour on eight cores. The ADR-0012 outbox and a receipt per job (ADR-0013's capture pattern) are the right shape for it; `aew map generate` stays synchronous for the structural map only.
3. **Query answers stay small at any scale** because they are per-symbol (S3): `callers` of a curl function is 55–345 tokens whether the repository has 169 files or 50k; only `neighborhood` radius ≥ 2 grows with connectivity, and that is already the budgeted operation.
4. **Freshness becomes the common state.** On a 50k-TU repository a few units are STALE after every commit; the artifact's status must be a count ("37 of 50,000 units stale"), and answers must carry the staleness of the units they touched, or the map will be reported STALE forever and ignored.

## 4. Not shown [hyp]

- A real 50k-file repository (the synthetic one has no includes, no imports and no build); the structural numbers are for the Git primitives and the directory pass, which is what the structural map is.
- Memory: the probe keeps one TU in memory at a time; the deduplicated assembly of 500k TUs' symbols would need a streaming build into the derived index rather than an in-memory dict.
- Windows timings for the Git primitives at 100k files (the probe ran on Linux); the T5 probe on Windows was 20 ms per `git` call versus a few ms on Linux, so expect a constant factor.
