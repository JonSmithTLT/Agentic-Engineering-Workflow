# ADR-0011 control-plane baselines

These are the control-plane measurements taken before ADR-0011 is implemented. ADR-0011's completion criteria (implementation plan §7) are judged against them:

- `baseline-windows.json` is the **reference**, from the Windows reference machine (§1);
- `baseline-linux.json` is a **supplement**, from a Linux cloud container (§2);
- `baseline-hierarchy-windows.json` is the **hierarchy-history series** on the reference machine (§3);
- `coldwrite-p2a-windows.json` is the first **cold-write series**, of the P2a cold store (§4). It has no "before": the store is new.
- `coldwrite-p2a-review-ab-windows.json` compares the code before and after P2a's independent review back to back, on the same machine state (§4);
- `p3-linux.json`, `p3-hierarchy-linux.json` and `p3-coldwrite-linux.json` are the **P3 results** after ADR-0011, from WSL2 Linux (§5);
- `p3-rocky8-*.json` are the P3 results on Rocky Linux 8.10 (§6);
- `p3-windows.json`, `p3-hierarchy-windows.json`, `p3-coldwrite-windows.json` and `p3-windows-h2-ab.json` are the P3 results on the Windows reference (§7).

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
- **Code:** the P2a cold store (`src/aew/history/`), with the independent review's fixes.
- **Rerun after the review.** The series was measured again after the independent review of P2a. Two things changed:
  - **Index catch-up** now covers exactly the three measured archivals, and the tool asserts that. The first series also took in the setup records that filled the tail: 25 to 256 entries per sample.
  - **An entry lookup in a sealed segment** now proves the segment against the root. It folds the segment's entries, then hashes every later sealed segment and reads only its header.
- **The machine was slower than for the first series.** Operations the review did not touch took 10–25% longer in every run. To separate the code from the machine, `coldwrite-p2a-review-ab-windows.json` runs the code before the review (A, `64c5a22`) and after it (B) back to back, alternating, at 3,000 and 10,000 requested records:
  - Appends, sealing, lookup by id, full verification and rebuild were level between A and B.
  - Entry lookup by sequence number took about 9 ms more in B (33 ms to 43 ms): the fold and the trace to the root.
  - Incremental verification took about 5 ms more in B: its starting point is now in a just-sealed segment, which the lookup folds.
  - Index catch-up took less in B, because A's figure still included the setup records.
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
| one archival, tail at 254 | 95.5 ms | 107.8 ms | 102.6 ms | 97.4 ms |
| one archival that seals | 122.5 ms | 136.7 ms | 132.0 ms | 133.4 ms |
| one archival, empty tail | 52.0 ms | 58.4 ms | 49.2 ms | 61.0 ms |
| incremental verification (3 entries) | 79.0 ms | 73.3 ms | 73.3 ms | 71.6 ms |
| index catch-up (3 entries) | 117.4 ms | 127.4 ms | 112.7 ms | 132.1 ms |
| lookup by id (index) | 0.8 ms | 1.2 ms | 1.1 ms | 1.1 ms |
| entry by sequence number (files) | 37.0 ms | 40.2 ms | 45.2 ms | 53.0 ms |
| full verification (linear by design) | 0.78 s | 1.86 s | 5.68 s | 16.41 s |
| index rebuild (linear by design) | 0.27 s | 0.68 s | 2.10 s | 6.04 s |

### Cold-write reading

- **Appends, verification and index lookups do not depend on how much history there is.** From 1.5k to 30.7k records, every per-operation cost is flat within noise, index catch-up included.
- **An entry lookup by sequence number grows slowly with history, by design.** It proves its segment against the root, so it hashes every later sealed segment and reads its header: 37 ms at 6 segments, 53 ms at 120. That is about 0.14 ms per later segment, and the operator chose this over a one-hop check (plan, P2a review fixes). A lookup in recent history costs the least.
- **Fixed costs dominate index catch-up.** Catching the index up by three entries costs about 110–130 ms here. That is about what the first series measured for 25 to 256 entries, so reading the tail and checking where the index stands outweigh the inserts.
- **What an archival costs depends on the tail.**
  - A full tail is about 150 KB (254 entries), and rewriting it costs about 45 ms more than an empty tail.
  - Sealing adds about 30 ms.
  - These costs are bounded by the segment size (256, plan P2a) and do not grow with history. A smaller segment would lower the worst case, if P3 needs that.
- **Full verification and index rebuild are linear.** That is by design: neither runs on a command's path. A full audit runs off the `resume` path (ADR-0011), and a rebuild runs only when `local/` is lost.

## 5. P3: after ADR-0011 (Linux, WSL2)

- **When and where:** 2026-10-03, at `16c6757` on the P3 branch (`impl/adr-0011-p3-acceptance`), in WSL2 Ubuntu 22.04 on the Windows reference machine (§1). This is a supplement: WSL2 is not the reference, and the host was not idle (a frontend agent worked on it; load about 1.2 to 1.3). Read slopes, not absolute numbers.
- **Software:** Python 3.11.0rc1, PyYAML 6.0.3 with libyaml, git 2.34.1, kernel 6.18 (WSL2). `p3-linux-env.txt` records it.
- **What is measured:** each sweep point is built in the M3 (v1) layout, migrated with `aew migrate`, then measured (P2d). The same points as the baselines.
- **Commands:**

  ```text
  python tools/perf/control_plane.py sweep --points 20:250,20:1000,20:3000,200:250,500:250,1000:250 --reps 3 --work <empty dir> --json eval/adr-0011/perf/p3-linux.json
  python tools/perf/control_plane.py sweep --hierarchy --points 3:250,3:1000,3:3000 --reps 3 --work <empty dir> --json eval/adr-0011/perf/p3-hierarchy-linux.json
  python tools/perf/control_plane.py coldwrite --records 1000,3000,10000,30000 --reps 3 --work <empty dir> --json eval/adr-0011/perf/p3-coldwrite-linux.json
  python tools/perf/adr0011_gate.py eval/adr-0011/perf/p3-linux.json --hierarchy eval/adr-0011/perf/p3-hierarchy-linux.json
  ```

  The cold-write series ran at `b57b681` (`p3-coldwrite-linux-env.txt`); `16c6757` changes only the migration, which it does not use.

### Flat series

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 32.4 KB | 32.9 KB | 34.0 KB | 218.6 KB | 528.8 KB | 1,045.8 KB |
| history's share of it | 7.8% | 7.9% | 7.7% | 1.2% | 0.5% | 0.2% |
| cold store | 5.2 MB | 20.7 MB | 62.3 MB | 5.2 MB | 5.2 MB | 5.2 MB |
| `aew migrate` (once) | 5.2 s | 25.4 s | 85.8 s | 5.4 s | 6.2 s | 6.9 s |
| H3 re-parse (`control_reparse_s`) | 6.1 ms | 6.3 ms | 6.4 ms | 41.2 ms | 143.6 ms | 290.4 ms |
| `lead show` | 0.14 s | 0.14 s | 0.15 s | 0.18 s | 0.27 s | 0.45 s |
| `status` | 0.18 s | 0.18 s | 0.20 s | 0.23 s | 0.32 s | 0.52 s |
| `work tree` | 0.14 s | 0.14 s | 0.15 s | 0.18 s | 0.26 s | 0.42 s |
| `resume` | 0.23 s | 0.25 s | 0.25 s | 0.45 s | 0.82 s | 1.45 s |
| `gate show` | 0.20 s | 0.19 s | 0.21 s | 0.24 s | 0.32 s | 0.48 s |
| `context pack` | 0.18 s | 0.17 s | 0.20 s | 0.22 s | 0.30 s | 0.46 s |
| `harness status` | 0.25 s | 0.25 s | 0.25 s | 0.29 s | 0.37 s | 0.53 s |
| `checkpoint` | 0.19 s | 0.20 s | 0.20 s | 0.28 s | 0.40 s | 0.65 s |
| `work dispatch` | 0.24 s | 0.24 s | 0.26 s | 0.33 s | 0.44 s | 0.70 s |
| `review ingest` | 0.26 s | 0.26 s | 0.26 s | 0.35 s | 0.47 s | 0.76 s |

### Hierarchy series

| | 5 open, 250 completed | 5 open, 1,000 completed | 5 open, 3,000 completed |
|---|---|---|---|
| `control.yaml` | 19.1 KB | 19.6 KB | 20.7 KB |
| history's share of it | 13.4% | 13.5% | 12.8% |
| `aew migrate` (once) | 5.1 s | 25.1 s | 84.2 s |
| H3 re-parse | 3.3 ms | 3.4 ms | 3.6 ms |
| `lead show` | 0.13 s | 0.13 s | 0.14 s |
| `status` | 0.17 s | 0.18 s | 0.19 s |
| `work tree` | 0.13 s | 0.13 s | 0.14 s |
| `resume` | 0.21 s | 0.21 s | 0.24 s |
| `checkpoint` | 0.18 s | 0.20 s | 0.19 s |
| `work dispatch` | 0.23 s | 0.24 s | 0.24 s |
| `review ingest` | 0.25 s | 0.25 s | 0.32 s |

### Cold-write series

| | 1,537 records | 3,585 records | 10,753 records | 30,721 records |
|---|---|---|---|---|
| one archival, tail at 254 | 100.5 ms | 88.1 ms | 92.3 ms | 87.1 ms |
| one archival that seals | 101.3 ms | 95.9 ms | 97.9 ms | 95.7 ms |
| one archival, empty tail | 43.8 ms | 43.0 ms | 43.5 ms | 42.9 ms |
| incremental verification (3 entries) | 55.9 ms | 52.0 ms | 51.9 ms | 51.8 ms |
| index catch-up (3 entries) | 94.3 ms | 84.0 ms | 89.3 ms | 86.6 ms |
| lookup by id (index) | 0.2 ms | 0.2 ms | 0.2 ms | 0.2 ms |
| entry by sequence number (files) | 26.1 ms | 27.0 ms | 29.4 ms | 34.6 ms |
| full verification (linear by design) | 0.18 s | 0.42 s | 1.26 s | 3.65 s |
| index rebuild (linear by design) | 0.29 s | 0.50 s | 1.59 s | 4.24 s |

### Reading

- **History no longer shows up on the command path.** From 250 to 3,000 completed, every measured command changes by at most 0.07 s (`review ingest` in the hierarchy series; most by 0.02 s or less). The same commands grew about 15x before (§2). Hot state grows 1.05x (flat) and 1.08x (hierarchy); history's share of it is the constant-size aggregates (`cold`, `recent`, summaries), 8% and 13%.
- **The H3 re-parse is milliseconds**, against 28.8 s for the hierarchy baseline on Windows (§3).
- **What is left grows with open work (A1).** From 20 to 1,000 open units, each adds 1.03 KB of hot state (as before) and 0.3 to 0.5 ms to most commands. `resume` adds 1.24 ms per open unit, linearly: 0.23, 0.45, 0.82 and 1.45 s at 20, 200, 500 and 1,000 open, with no knee. The re-parse grows with it, to 0.29 s at 1,000 open: inside the 2.5 s heartbeat bound. H3's 0.25 s is defined at 20 open.
- **Cold writes stay flat from 1.5k to 30.7k records**, as on Windows (§4).
- **Migration is linear in finished work**, about 28 ms per finished Ticket here. It runs once per project.
- **Found by this run and fixed (`16c6757`):** the derived history index was built by the first command to look up finished work after a migration. At 3,000 completed, `harness status` (which shows the runs of the recent ring) paid it once: 0.88 s against 0.25 s at 250. The migration now builds the index itself. The table above is from the rerun.

## 6. P3: Rocky Linux 8.10 (aew-q7)

- **When and where:** 2026-10-03, at `16c6757`, in the WSL2 distro `aew-q7` on the Windows reference machine: Rocky Linux 8.10 from the official container base image. It has Rocky's own userland (Python 3.11.13 from AppStream, git 2.43.7, PyYAML 6.0.3 with libyaml) but **WSL2's kernel, 6.18**, not Rocky 8's 4.18. The cost measured here is Python, YAML and file I/O, which the kernel barely affects. F2's containment work, which depends on the kernel, still needs a real Rocky 8 kernel (register F2). The host's load was about 1.2. `p3-rocky8-env.txt` records it.
- **Commands:** `tools/perf/rocky8-gate.sh` (the hierarchy series, H3 at 20 open and 3,000 completed, the cold-write series), then the full flat sweep, as on Linux (§5). Files: `p3-rocky8-hierarchy.json`, `p3-rocky8-h3.json`, `p3-rocky8-coldwrite.json`, `p3-rocky8-flat.json`.
- **The script's own verdict:** H3 re-parse at 20 open and 3,000 completed, 0.006 s: H3 (≤ 0.25 s) pass, heartbeat bound (≤ 2.5 s) pass.

### Flat series

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 32.4 KB | 32.9 KB | 34.0 KB | 218.5 KB | 528.7 KB | 1,045.7 KB |
| `aew migrate` (once) | 5.5 s | 25.4 s | 83.0 s | 5.6 s | 5.9 s | 7.0 s |
| H3 re-parse | 6.7 ms | 6.8 ms | 7.0 ms | 53.3 ms | 125.8 ms | 407.4 ms |
| `lead show` | 0.15 s | 0.15 s | 0.16 s | 0.20 s | 0.29 s | 0.46 s |
| `status` | 0.19 s | 0.19 s | 0.20 s | 0.24 s | 0.34 s | 0.52 s |
| `work tree` | 0.15 s | 0.15 s | 0.16 s | 0.20 s | 0.28 s | 0.47 s |
| `resume` | 0.24 s | 0.24 s | 0.24 s | 0.47 s | 0.87 s | 1.56 s |
| `gate show` | 0.20 s | 0.21 s | 0.21 s | 0.24 s | 0.33 s | 0.49 s |
| `context pack` | 0.18 s | 0.19 s | 0.19 s | 0.24 s | 0.31 s | 0.47 s |
| `harness status` | 0.27 s | 0.26 s | 0.28 s | 0.30 s | 0.39 s | 0.54 s |
| `checkpoint` | 0.20 s | 0.20 s | 0.21 s | 0.28 s | 0.42 s | 0.70 s |
| `work dispatch` | 0.24 s | 0.25 s | 0.26 s | 0.32 s | 0.47 s | 0.72 s |
| `review ingest` | 0.25 s | 0.26 s | 0.26 s | 0.34 s | 0.50 s | 0.77 s |

### Hierarchy series

| | 5 open, 250 completed | 5 open, 1,000 completed | 5 open, 3,000 completed |
|---|---|---|---|
| `control.yaml` | 19.1 KB | 19.6 KB | 20.7 KB |
| `aew migrate` (once) | 5.5 s | 26.7 s | 88.9 s |
| H3 re-parse | 3.5 ms | 3.5 ms | 3.9 ms |
| `lead show` | 0.14 s | 0.14 s | 0.17 s |
| `status` | 0.18 s | 0.19 s | 0.19 s |
| `work tree` | 0.14 s | 0.15 s | 0.15 s |
| `resume` | 0.22 s | 0.22 s | 0.22 s |
| `gate show` | 0.19 s | 0.20 s | 0.19 s |
| `context pack` | 0.18 s | 0.18 s | 0.19 s |
| `harness status` | 0.26 s | 0.26 s | 0.26 s |
| `checkpoint` | 0.19 s | 0.20 s | 0.21 s |
| `work dispatch` | 0.24 s | 0.24 s | 0.25 s |
| `review ingest` | 0.25 s | 0.25 s | 0.26 s |

### Cold-write series

| | 1,537 records | 3,585 records | 10,753 records | 30,721 records |
|---|---|---|---|---|
| one archival, tail at 254 | 90.4 ms | 92.4 ms | 92.9 ms | 94.1 ms |
| one archival that seals | 98.0 ms | 100.2 ms | 98.6 ms | 101.2 ms |
| one archival, empty tail | 43.6 ms | 44.0 ms | 43.2 ms | 44.5 ms |
| incremental verification (3 entries) | 54.9 ms | 55.0 ms | 54.3 ms | 56.8 ms |
| index catch-up (3 entries) | 92.6 ms | 90.8 ms | 92.4 ms | 93.5 ms |
| lookup by id (index) | 0.2 ms | 0.2 ms | 0.2 ms | 0.2 ms |
| entry by sequence number (files) | 27.4 ms | 28.7 ms | 31.5 ms | 38.2 ms |
| full verification (linear by design) | 0.19 s | 0.44 s | 1.33 s | 3.95 s |
| index rebuild (linear by design) | 0.24 s | 0.52 s | 1.52 s | 4.37 s |

### Reading

- **The same result as WSL Ubuntu (§5).** From 250 to 3,000 completed no command changes by more than 0.03 s, hot state grows 1.05x (flat) and 1.08x (hierarchy), and the H3 re-parse stays at 4 to 7 ms.
- **Cold writes are flat from 1.5k to 30.7k records**; full verification and index rebuild are linear, by design.
- **A1:** 1.03 KB of hot state per open unit; `resume` adds 1.35 ms per open unit, linearly (0.24, 0.47, 0.87 and 1.56 s at 20, 200, 500 and 1,000 open). The re-parse at 1,000 open is 0.41 s, inside the 2.5 s heartbeat bound.

## 7. P3: Windows reference

- **When and where:** 2026-10-03, at `16c6757`, on the reference machine (§1): Python 3.13.1, PyYAML 6.0.3 with libyaml, git 2.46.0. The operator did light design work during the run; nothing else ran. `p3-windows-env.txt` records it.
- **Commands:** the three of §5, with `--json` files `p3-windows.json`, `p3-hierarchy-windows.json` and `p3-coldwrite-windows.json`; then the paired run below.

### Flat series

| | 20 open, 250 completed | 20 open, 1,000 completed | 20 open, 3,000 completed | 200 open, 250 completed | 500 open, 250 completed | 1,000 open, 250 completed |
|---|---|---|---|---|---|---|
| `control.yaml` | 32.8 KB | 33.3 KB | 34.3 KB | 218.9 KB | 529.1 KB | 1,046.1 KB |
| `aew migrate` (once) | 7.4 s | 30.8 s | 107.6 s | 6.3 s | 7.8 s | 7.5 s |
| H3 re-parse | 9.9 ms | 12.3 ms | 13.3 ms | 45.1 ms | 199.9 ms | 260.1 ms |
| `lead show` | 0.30 s | 0.30 s | 0.48 s | 0.34 s | 0.42 s | 0.57 s |
| `status` | 0.36 s | 0.37 s | 0.61 s | 0.51 s | 0.79 s | 1.26 s |
| `work tree` | 0.30 s | 0.30 s | 0.52 s | 0.34 s | 0.42 s | 0.57 s |
| `resume` | 0.56 s | 0.56 s | 0.93 s | 1.09 s | 2.03 s | 3.59 s |
| `gate show` | 0.47 s | 0.48 s | 0.62 s | 0.51 s | 0.59 s | 0.75 s |
| `context pack` | 0.36 s | 0.34 s | 0.43 s | 0.39 s | 0.47 s | 0.62 s |
| `harness status` | 0.49 s | 0.48 s | 0.51 s | 0.53 s | 0.62 s | 0.81 s |
| `checkpoint` | 0.33 s | 0.34 s | 0.36 s | 0.41 s | 0.56 s | 0.82 s |
| `work dispatch` | 0.52 s | 0.53 s | 0.55 s | 0.59 s | 0.74 s | 1.02 s |
| `review ingest` | 0.61 s | 0.64 s | 0.67 s | 0.70 s | 0.87 s | 1.12 s |

### Hierarchy series

| | 5 open, 250 completed | 5 open, 1,000 completed | 5 open, 3,000 completed |
|---|---|---|---|
| `control.yaml` | 19.5 KB | 20.0 KB | 21.0 KB |
| `aew migrate` (once) | 7.3 s | 28.4 s | 97.6 s |
| H3 re-parse | 5.5 ms | 4.3 ms | 7.4 ms |
| `lead show` | 0.30 s | 0.29 s | 0.31 s |
| `status` | 0.35 s | 0.35 s | 0.36 s |
| `work tree` | 0.30 s | 0.29 s | 0.30 s |
| `resume` | 0.51 s | 0.51 s | 0.52 s |
| `gate show` | 0.47 s | 0.46 s | 0.47 s |
| `context pack` | 0.35 s | 0.35 s | 0.36 s |
| `harness status` | 0.48 s | 0.49 s | 0.49 s |
| `checkpoint` | 0.34 s | 0.33 s | 0.34 s |
| `work dispatch` | 0.52 s | 0.51 s | 0.55 s |
| `review ingest` | 0.62 s | 0.61 s | 0.64 s |

### Cold-write series

| | 1,537 records | 3,585 records | 10,753 records | 30,721 records |
|---|---|---|---|---|
| one archival, tail at 254 | 86.6 ms | 98.1 ms | 87.6 ms | 101.3 ms |
| one archival that seals | 116.6 ms | 151.1 ms | 108.8 ms | 137.9 ms |
| one archival, empty tail | 57.0 ms | 62.9 ms | 46.8 ms | 63.5 ms |
| incremental verification (3 entries) | 60.1 ms | 72.2 ms | 59.2 ms | 76.5 ms |
| index catch-up (3 entries) | 102.3 ms | 133.8 ms | 120.0 ms | 126.5 ms |
| lookup by id (index) | 0.7 ms | 0.9 ms | 1.1 ms | 1.0 ms |
| entry by sequence number (files) | 31.4 ms | 44.9 ms | 44.1 ms | 59.0 ms |
| full verification (linear by design) | 0.34 s | 0.98 s | 3.00 s | 9.71 s |
| index rebuild (linear by design) | 0.24 s | 0.72 s | 1.67 s | 5.94 s |

### H2, paired

In the flat sweep, the 3,000 point was measured once, and that sample was slow throughout: `aew --version`, which never reads the project, took 0.22 s against 0.13 s at 250, and every phase of every command was about 1.6x slower, including the parse of the same 34 KB file. That made `status` +0.255 s and `resume` +0.37 s against 250, over H2's +0.25 s, with identical read and scan counters. To separate the machine from the code, `control_plane.py ab` builds both points and measures them in turns, six rounds, one sample each (`p3-windows-h2-ab.json`):

```text
python tools/perf/control_plane.py ab --points 20:250,20:3000 --rounds 6 --work <empty dir> --json eval/adr-0011/perf/p3-windows-h2-ab.json
```

| Command | 250 completed (median) | 3,000 completed (median) | paired difference (median) |
|---|---|---|---|
| `CLI floor (aew --version)` | 0.133 s | 0.129 s | -0.004 s |
| `lead show` | 0.303 s | 0.312 s | +0.011 s |
| `status` | 0.406 s | 0.405 s | +0.004 s |
| `work tree` | 0.300 s | 0.305 s | +0.007 s |
| `resume` | 0.571 s | 0.572 s | -0.002 s |
| `gate show` | 0.479 s | 0.474 s | -0.001 s |
| `context pack` | 0.349 s | 0.354 s | +0.006 s |
| `harness status` | 0.593 s | 0.593 s | -0.000 s |
| `checkpoint` | 0.343 s | 0.361 s | +0.013 s |
| `work dispatch` | 0.529 s | 0.529 s | +0.015 s |
| `review ingest` | 0.626 s | 0.653 s | +0.024 s |

The largest difference is +0.024 s. The sweep no longer caps the samples at 3,000 (that cap dated from M3, when a command took 50 s there), so a future sweep takes three.

### Reading

- **History is off the command path on the reference machine too.** Paired, no command changes by more than 0.024 s from 250 to 3,000 completed; in the hierarchy series, by at most 0.036 s. Before ADR-0011 the same step cost 21 to 47 s (§1). Hot state grows 1.05x (flat) and 1.08x (hierarchy).
- **H3:** the re-parse is 13 ms at 20 open and 3,000 completed, against 28.8 s before (§3).
- **Cold writes are flat**; entry lookup by sequence number grows slowly by design (31 to 59 ms), and full verification and rebuild are linear.
- **A1: `resume` is the cost that is left.** It grows by about 3 ms per open unit here (0.56 s at 20 open to 3.59 s at 1,000), linearly, with no knee: the compute phase §1 already pointed at, about 2.4x Linux's 1.2 to 1.4 ms. It stays inside the 8 s bound and is unrelated to history. It is carried to M4's ambiguity report (implementation plan §7.3).
- **Migration** took 108 s at 3,000 completed in this run (87 s measured alone, §7.4 of the plan): once per project, linear.
