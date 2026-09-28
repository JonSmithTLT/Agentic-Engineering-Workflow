# M3 control-plane performance (step 7)

**Status:** measured on 2026-09-27 on branch `impl/m3-opencode`. **Scope:** AEW's own cost per command: the control plane, not a harness or a model. **Rule (M3 plan §2.10):** only demonstrated pathologies are fixed; everything else is reported.

## 1. Method

- **Profiling.** `AEW_PROFILE=<file>` makes every `aew` command append one JSON line to that file, with its exclusive phase times and deterministic counts (`src/aew/profile.py`).
  - Phases: `lock`, `recover`, `parse`, `render`, `commit`, `git`, `scan` (evidence), and `compute` (the rest).
  - Counts: `git` subprocesses (per subcommand), control-state `parse` (and `parse_cached`), `commit`, `render`, `scan` (and files scanned).
  - The record names the command by its leading words only, so no option value (and no credential) is ever written. Profiling is off unless the variable is set.
- **Projects.** `tools/perf/control_plane.py` builds synthetic projects of a given size.
  - A template is made by the real engine: one Ticket taken through its whole lifecycle to DONE (four invocations, eight pieces of evidence, a completion record), one planned Ticket, one Ticket awaiting review ingest, and one ready investigation.
  - The rest is cloned from the DONE and planned Tickets, two DONE for each planned one. Every id, path, evidence seal and content hash is rewritten.
  - Each build is accepted by the engine: the control state parses and validates, `doctor` passes, `resume` reports no contradiction, and cloned evidence verifies.
- **Measurement.** Each command runs as the real CLI in its own process; wall time is measured around it (median of 3 runs; 1 run at 3,000 units). Mutations are undone after each run.
- **Machine.** Windows 11, Python 3.13, PyYAML 6 built with libyaml, local NTFS SSD. A git subprocess costs 10–20 ms here; the bare CLI floor (`aew --version`) is 0.10 s.
- **Raw results:** `eval/m3/perf/before.json` and `after.json`.

| Project | Units | Invocations | `control.yaml` |
|---|---|---|---|
| S | 50 | 130 | 0.7 MB |
| M | 500 | 1,330 | 7.0 MB |
| L | 3,000 | 7,998 | 42.3 MB |

## 2. Before (the code as of step 6)

| Command | 50 units | 500 units | 3,000 units |
|---|---|---|---|
| `lead show` (a minimal read) | 0.89 s | 7.69 s | 49.3 s |
| `status` | 1.16 s | 9.67 s | 60.4 s |
| `work tree` | 0.91 s | 7.60 s | 48.4 s |
| `resume` | 2.93 s | 27.1 s | 167.7 s |
| `gate show` | 1.06 s | 7.80 s | 48.2 s |
| `context pack` | 0.95 s | 7.66 s | 48.4 s |
| `harness status` | 0.90 s | 7.53 s | 48.9 s |
| `checkpoint` (the commit path) | 1.31 s | 11.8 s | 77.9 s |
| `work dispatch` | 1.51 s | 12.0 s | 77.2 s |
| `review ingest` | 2.24 s | 19.5 s | 125.5 s |

Every command's cost was dominated by `parse`: 7.2 s of the 7.7 s of `lead show` at 500 units.

## 3. Pathologies found and fixed

| # | Pathology | Evidence | Fix | Regression |
|---|---|---|---|---|
| P1 | **YAML was parsed and written by pure-Python PyYAML**, although libyaml was available. | At 500 units: parse 7.5 s (libyaml 1.8 s), write 4.4 s (libyaml 1.3 s). | `load_yaml` and `dump_yaml` use libyaml where PyYAML has it, pure Python otherwise. Both directions go through the same Python constructors and representers, so no value read and no byte written changes. That was checked on 4,442 real documents (control states, logs, redo records, decisions, evidence, fixtures, role cards) and on adversarial strings. | `tests/unit/test_yaml_backends.py` |
| P2 | **`status` and `resume` spawned `git rev-parse` of the authoritative branch once or twice per open unit** (`input_status`), even when the unit consumes no input to compare against it. | `status` at 12 units: 7 git processes; at 48: 19. `resume`: 22, then 46. | `input_status` resolves the dispatch commit only when the unit has inputs. | `tests/regression/test_m3_control_plane_scale.py` (failed before the fix) |
| P3 | **Some processes parsed the unchanged control state again and again.** `resume` parsed it twice (`work_tree` re-read it). `review ingest`, `verify ingest` and `invoke create` parsed it once to route and again in their transaction. A run's supervisor re-reads it every 2 s and on every bridge request, and the Lead broker polls it. At 500 units a supervisor parsed without pause, about 8 s per poll. Its heartbeat, beaten from the same loop, came within 2 s of the 10 s staleness limit; at 3,000 units (47 s per parse) a healthy run would show as `lost`. | Profile counts; the timing of repeated reads. | The store keeps its last parse with the SHA-256 of the bytes parsed. A read still reads the file, but identical bytes reuse that parse (exactly a re-parse, since parsing is deterministic); any other bytes get a full parse with checksum and schema validation. The shared parse is never handed out: a read returns a copy, a transaction changes its own. | `tests/unit/test_store_cache.py`; the scale regression; `test_no_engine_operation_changes_the_shared_parse` checks every load of a real workload against a fresh parse |

The **scale regression** runs every measured command on one project at 12 and again at 48 units. It asserts that the counts of git processes, parses, commits and renders are identical at both sizes. It allows exactly one growth: `resume` scans the evidence of every unit and of every open Ticket, because reporting integrity contradictions (KC §15.1) and unmet gates is its job. The test is timing-free, so it runs in CI.

## 4. After

| Command | 50 units | 500 units | 3,000 units | 500 units: before → after |
|---|---|---|---|---|
| `lead show` | 0.36 s | 1.80 s | 13.6 s | 4.3× |
| `status` | 0.43 s | 2.16 s | 15.5 s | 4.5× |
| `work tree` | 0.36 s | 1.79 s | 13.6 s | 4.2× |
| `resume` | 0.89 s | 5.43 s | 34.8 s | 5.0× |
| `gate show` | 0.51 s | 1.98 s | 13.6 s | 3.9× |
| `context pack` | 0.41 s | 1.86 s | 13.7 s | 4.1× |
| `harness status` | 0.37 s | 1.83 s | 13.5 s | 4.1× |
| `checkpoint` | 0.48 s | 2.98 s | 23.3 s | 4.0× |
| `work dispatch` | 0.66 s | 3.15 s | 23.5 s | 3.8× |
| `review ingest` | 0.76 s | 3.29 s | 30.6 s | 5.9× |

- Every command now parses the control state exactly once, at every size. Git process counts are constant (`status` 3, `resume` 14, `work dispatch` 13, `review ingest` 24).
- A polling process's read of an unchanged 500-unit state: **1.65 s → 0.10 s**.

## 5. Remaining: the control state grows with completed work (decision needed)

After the fixes, every command still costs time **linear in the size of `control.yaml`**. At 500 units that is 1.5 s to parse; a commit adds about 1.1 s to write it. The file grows with **completed** work, which never leaves it.

What the 7.0 MB at 500 units consists of:

| Part | Size | Share | Notes |
|---|---|---|---|
| Invocations (1,330, nearly all completed) | 4.16 MB | 59% | Per invocation: the pinned pack-source list (about 1.5 KB) and the full role-card content (about 0.7 KB) |
| Work units | 2.01 MB | 29% | Per DONE Ticket: evidence references 1.3 KB, integration record 1.2 KB, history 0.8 KB |
| Credential entries (revoked) | 0.49 MB | 7% | |

A DONE Ticket with its four invocations costs about 20 KB of control state; a planned one about 1 KB. With libyaml, PyYAML still builds the Python objects in Python, which caps parsing at about 4–5 MB/s.

This is a property of the persistence design (ADR-0001: one control file is the commit point and holds everything), not a defect a small change removes. Fixing it changes the control-state schema, so it is **not done in M3** (whose schemas change only additively). Options, for a decision:

1. **Archive terminal records out of the hot state.** When an invocation ends and its unit is terminal, move its pack sources and card content into an immutable, content-addressed record committed through the existing redo mechanism, leaving a stub with its hash. Revoked credential entries shrink to what rule 17 needs. Moving DONE units' detail into their completion records as well would bring a DONE Ticket to roughly 1 KB.
2. **Deduplicate pinned role cards.** Store each (card, version, sha256) once and reference it from invocations. This is smaller in effect (about 14%) and in scope.
3. **Accept it and state the envelope.** Up to a few hundred units, commands take 0.4–3 s. Mature projects approaching 1,000 or more finished Tickets need option 1.

Also measured but not changed:

- **`resume`'s integrity sweep.** It verifies every unit's sealed evidence on every call: 16 s of its 35 s at 3,000 units. That is its job (KC §15.1). A cheaper sweep, comparing pinned hashes instead of re-verifying seals, would not cover evidence nobody has ingested.
- **Per-read schema validation** of the control state: 0.12 s at 500 units. It is kept as integrity defense.
- **Heartbeat at 3,000 units.** An unchanged state now costs a supervisor 0.1 s per poll. After each Lead commit, though, every live supervisor re-parses the changed file, and at 3,000 units that takes 13 s, longer than the 10 s staleness limit (`AEW_RUN_STALE_S`). So a healthy run can briefly show as `lost` after a commit. The heartbeat is deliberately beaten from the watchdog loop, so that a stalled watchdog shows as stale. This is a consequence of the growth above, not a separate fix.

## 6. Reproducing

```bash
python tools/perf/control_plane.py run --sizes 50,500 --work /tmp/aew-perf --reps 3 --json results.json
AEW_PROFILE=/tmp/profile.jsonl aew resume --json        # one command's phases and counts
python -m pytest tests/regression/test_m3_control_plane_scale.py -q
```
