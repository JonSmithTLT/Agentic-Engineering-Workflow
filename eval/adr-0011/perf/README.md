# ADR-0011 control-plane baselines

These are the control-plane measurements taken before ADR-0011 is implemented. ADR-0011's completion criteria (implementation plan §7) are judged against them:

- `baseline-windows.json` is the **reference**, from the Windows reference machine (§1);
- `baseline-linux.json` is a **supplement**, from a Linux cloud container (§2);
- `baseline-hierarchy-windows.json` is the **hierarchy-history series** on the reference machine (§3);
- `coldwrite-p2a-windows.json` is the first **cold-write series**, of the P2a cold store (§4). It has no "before": the store is new.

The first two use the same sweep points.

## 1. Windows reference

- **When and where:** run by the operator on 2026-10-02, at `aa533c5` on the ADR-0011 plan branch. That commit differs from the Linux baseline's `0eb8ecf` only in the perf tool (a Windows retry when it removes a worktree), so the engine measured is the same.
- **Machine:** Windows 11, AMD Ryzen 7 7800X3D (8 cores, 16 threads), 32 GB, local NTFS SSD.
- **Software:** Python 3.13.1, PyYAML 6.0.3 with libyaml, git 2.46.0.windows.1.
- **Command:**

  ```text
  python tools\perf\control_plane.py sweep --points 20:250,20:1000,20:3000,200:250,500:250,1000:250 --reps 3 --work <empty dir> --json eval\adr-0011\perf\baseline-windows.json
  ```

### Windows results

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 5.10 MB | 20.32 MB | 60.92 MB | 5.29 MB | 5.60 MB | 6.11 MB |
| live part | 27 KB | 27 KB | 27 KB | 213 KB | 523 KB | 1,040 KB |
| `lead show` | 1.32 s | 6.75 s | 22.43 s | 1.55 s | 1.65 s | 1.85 s |
| `status` | 1.55 s | 7.28 s | 24.09 s | 1.76 s | 2.04 s | 2.69 s |
| `resume` | 3.86 s | 16.63 s | 50.52 s | 4.96 s | 5.65 s | 8.15 s |
| `checkpoint` | 2.29 s | 12.86 s | 35.67 s | 2.35 s | 2.43 s | 2.94 s |
| `work dispatch` | 2.55 s | 13.32 s | 41.02 s | 2.53 s | 2.68 s | 3.21 s |
| `review ingest` | 2.65 s | 14.74 s | 42.96 s | 2.69 s | 2.90 s | 3.31 s |

### Windows reading

- **Lifetime history is the dominant cost, as on Linux.** From 250 to 3,000 completed Tickets at 20 open units, every command grows about 17× (`lead show` goes from 1.32 s to 22.43 s). That is the cost ADR-0011 removes.
- **The active series is mostly flat**, except for `resume`. From 20 to 1,000 open units at 250 completed:
  - most commands add 0.3 to 0.7 s;
  - `status` adds 1.1 s;
  - `resume` adds 4.3 s (3.86 s to 8.15 s).
- **`resume`'s growth is in compute, not parsing.** Its compute phase goes from 0.60 s to 3.70 s, about 3 ms per open unit, and grows slightly faster than linearly here. Parsing goes from 1.00 s to 1.50 s.
  - On Linux, the same phase goes from 0.47 s to 1.89 s.
  - This is active-complexity cost, which ADR-0011 does not remove. A1 should watch it after archival.
- **This machine parses YAML about 2.4× faster than the Linux container** (libyaml load of the 20/250 file: 1.04 s against 2.49 s). Git and filesystem calls cost more here.

## 2. Linux supplement

`baseline-linux.json` was taken from a Linux cloud container on 2026-10-02 at `main` `0eb8ecf`.

### Command

```text
python tools/perf/control_plane.py sweep --points 20:250,20:1000,20:3000,200:250,500:250,1000:250 --reps 3 --work <scratch> --json eval/adr-0011/perf/baseline-linux.json
```

The points are the M3 sweep (`eval/m3/perf/sweep.json`) plus the ADR-0011 active series up to 1,000 open units (A1). The hierarchy-history and cold-write series do not exist in the tool yet. P2a adds them, and those series are then run against this same commit.

### Conditions

- A cloud container with 4 CPUs.
- Ubuntu's Python 3.11.15, in a venv, with PyYAML 6.0.3 from the PyPI wheel, which includes libyaml (`yaml.__with_libyaml__` checked before the run).
- git 2.43.0.
- Load average 0.07 at the start of the run. Nothing else ran during it except editors and git commits.
- Cloud CPUs are noisier than a dedicated machine. Read slopes, not absolute numbers.

### Linux results

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 5.20 MB | 20.70 MB | 62.07 MB | 5.38 MB | 5.69 MB | 6.21 MB |
| live part | 27 KB | 27 KB | 27 KB | 213 KB | 523 KB | 1,040 KB |
| `lead show` | 2.82 s | 14.28 s | 42.81 s | 2.78 s | 2.90 s | 3.77 s |
| `status` | 2.71 s | 14.66 s | 40.75 s | 2.80 s | 2.89 s | 3.91 s |
| `resume` | 4.60 s | 20.78 s | 59.98 s | 4.89 s | 5.32 s | 6.96 s |
| `checkpoint` | 4.04 s | 19.23 s | 62.68 s | 4.19 s | 4.75 s | 5.59 s |
| `work dispatch` | 4.11 s | 19.37 s | 63.34 s | 4.52 s | 5.04 s | 5.59 s |
| `review ingest` | 4.15 s | 19.22 s | 65.77 s | 4.65 s | 4.97 s | 5.99 s |

The JSON also holds `work tree`, `gate show`, `context pack`, `harness status`, the CLI floor, and per-phase and micro timings.

### Linux reading

- **Same shape as the Windows baseline.** Each completed Ticket adds about 20.7 KB to the control file. Each open or planned unit adds about 1.03 KB, and that stays linear up to 1,000 open, with no knee.
- **This container is about 2.4× slower at YAML parsing** than the Windows reference: a libyaml load of the 20/250 file takes 2.49 s here against 1.04 s there. Command latencies scale accordingly; `lead show` at 20/250 is 2.82 s here and 1.44 s there. Builds run about 1.8× faster here, because git and filesystem calls cost less on Linux. Compare against Windows numbers by slope.
- **The active series** adds about 1 s of read latency from 20 to 1,000 open units at 250 completed (`lead show` goes from 2.82 s to 3.77 s, mostly parsing about 1 MB of open units). ADR-0011's A1 asks for this slope. Against the Windows absolute bounds it is not a problem, but it matters for H3's 0.25 s heartbeat budget, which investigation §7 also flags.

## 3. Hierarchy-history series (Windows reference)

- **When and where:** 2026-10-02, on the reference machine (§1).
- **Code:** the baseline commit `0eb8ecf`, run with the P2a perf tool. One measurement-only change was applied to that checkout: P2a's `derive` profile phase, two `with profile.phase("derive")` wrappers around parent recomputation. It changes no behaviour.
- **Shape:** one open Epic and one open Story. Every Ticket is below the Story: the frontier T-0002 to T-0004, and the completed T-0001 with its clones. "Open" counts the Epic and Story as well.
- **Command:**

  ```text
  set PYTHONPATH=<checkout of 0eb8ecf>\src
  python tools\perf\control_plane.py sweep --hierarchy --points 3:250,3:1000,3:3000 --reps 3 --work <empty dir> --json eval\adr-0011\perf\baseline-hierarchy-windows.json
  ```

### Hierarchy results

| | 5 open, 250 completed | 5 open, 1,000 completed | 5 open, 3,000 completed |
|---|---|---|---|
| `control.yaml` | 5.29 MB | 21.12 MB | 63.35 MB |
| live part | 12 KB | 12 KB | 12 KB |
| H3 re-parse (`control_reparse_s`) | 1.12 s | 8.22 s | 28.78 s |
| `lead show` | 1.39 s | 7.17 s | 22.66 s |
| `status` | 1.64 s | 8.74 s | 26.69 s |
| `work tree` | 1.36 s | 7.50 s | 22.43 s |
| `resume` | 3.89 s | 19.78 s | 51.99 s |
| `checkpoint` | 2.20 s | 12.74 s | 35.46 s |
| `work dispatch` | 2.47 s | 13.69 s | 37.36 s |
| `review ingest` | 2.61 s | 14.04 s | 39.72 s |
| parent recomputation (`derive`, per commit) | 0.011 s | 0.29 s | 2.19 s |

### Hierarchy reading

- **Parent recomputation grows quadratically with completed descendants.** This is what the series is meant to catch (ADR-0011: "parent derivation or closeout logic that rescans completed descendants"). Going from 250 to 1,000 descendants (4×) costs 26× more; from 1,000 to 3,000 (3×) costs 7.5× more.
  - **The cause:** `hierarchy.descendants()` calls `children()` once per descendant, and `children()` scans every unit.
  - **The fix:** archival removes most of the cost, because it bounds the units scanned to the hot ones (R3). Building one children map per recomputation removes the D × N shape itself. P2b records that as part of its reader changes.
- **Every command also pays the history cost seen in the flat series.** Hierarchy adds a little on top: `status` at 1,000 completed is 8.74 s here, against 7.28 s flat.
- **H3 baseline.** A supervisor's re-parse of the changed state takes 28.8 s at 3,000 completed. H3 requires ≤ 0.25 s, and the absolute heartbeat bound is ≤ 2.5 s.

## 4. Cold-write series (P2a, Windows reference)

- **When and where:** 2026-10-02, on the reference machine (§1).
- **Code:** the P2a cold store (`src/aew/history/`).
- **Command:**

  ```text
  python tools\perf\control_plane.py coldwrite --records 1000,3000,10000,30000 --reps 3 --work <empty dir> --json eval\adr-0011\perf\coldwrite-p2a-windows.json
  ```

- **How the stores are built.**
  - Each store is built from small pre-written bundles (plan R8). Each measured archival writes a realistic bundle of about 20 KB through the normal transaction path.
  - Entries carry realistic links: dependencies, decisions, evidence, the integration commit and the completion record.
  - The root is kept in a file written in the same transaction, until schema v2 (P2b).
- **How the appends are measured.** Before each repetition the tail is filled to 254 entries. Three appends are then measured:
  1. into a nearly full tail;
  2. the one that seals the segment;
  3. the first into the new, empty tail.

  That way every size is measured at the same tail occupancy. The record counts are therefore a little above the requested sizes.

### Cold-write results

| | 1,537 records | 3,585 records | 10,753 records | 30,721 records |
|---|---|---|---|---|
| one archival, tail at 254 | 87.8 ms | 88.9 ms | 88.7 ms | 88.6 ms |
| one archival that seals | 112.4 ms | 110.8 ms | 102.7 ms | 109.5 ms |
| one archival, empty tail | 51.7 ms | 56.0 ms | 47.2 ms | 54.7 ms |
| incremental verification (3 entries) | 59.2 ms | 60.4 ms | 56.5 ms | 55.6 ms |
| index catch-up (3 entries) | 101.9 ms | 105.3 ms | 109.0 ms | 113.3 ms |
| lookup by id (index) | 0.8 ms | 0.7 ms | 0.7 ms | 0.7 ms |
| entry by sequence number (files) | 27.2 ms | 27.4 ms | 27.6 ms | 27.2 ms |
| full verification (linear by design) | 0.66 s | 1.57 s | 4.80 s | 16.23 s |
| index rebuild (linear by design) | 0.28 s | 0.53 s | 1.62 s | 4.72 s |

### Cold-write reading

- **Appends, verification and lookup do not depend on how much history there is.** From 1.5k to 30.7k records, every per-operation cost is flat within noise. Index catch-up rises by about 11% over a 20× larger store, which is the SQLite B-tree.
- **What an archival costs depends on the tail.**
  - A full tail is about 150 KB (254 entries), and rewriting it costs about 35 ms more than an empty tail.
  - Sealing adds about 20 ms.
  - These costs are bounded by the segment size (256, plan P2a) and do not grow with history. A smaller segment would lower the worst case, if P3 needs that.
- **Full verification and index rebuild are linear.** That is by design: neither runs on a command's path. A full audit runs off the `resume` path (ADR-0011), and a rebuild runs only when `local/` is lost.

