# ADR-0011 independent review brief

**For:** the independent reviewer of ADR-0011 (hot and cold control state) and E5, the gate before M4 (implementation plan §7.2).
**Code:** `main` after PRs #15 (E5), #17 (P2a), #18 (P2b), #20 (P2c) and #21 (P2d), plus this P3 branch. The pre-implementation baseline is `0eb8ecf`. **Frozen specs:** unchanged.
**Governing texts:** [ADR-0011](adr/0011-hot-cold-control-state.md), the [implementation plan](adr-0011-implementation-plan.md) (R1–R8 in §2, each phase's "as built" in §6, P3's results in §7.4), [ADR-0001](adr/0001-control-state-persistence.md).

Each P2 PR had its own independent review, and their fixes are merged. This review is of the whole, as ADR-0011 asks: the store is the authority, so the brief starts with what changed in ADR-0001's model.

## What changed in ADR-0001's model

ADR-0001 is not amended; its mechanism is unchanged. What it governs is now a smaller, bounded document plus an append-only store pinned from it.

| ADR-0001 (M1) | After ADR-0011 |
|---|---|
| `control.yaml` is the only mutable authority and the single commit point. | **Unchanged.** It is still the one commit point. It now holds only hot state: open work, its invocations and credentials, and constant-size aggregates of finished work (`cold`, `recent`, `archived_refs`, per-parent summaries and frontiers). |
| The authoritative state is `control.yaml`. | The authoritative state is `control.yaml` **plus every history record reachable from `cold.root`**. A history record is reachable only through the hash chain from that root (R1). Anything else under `history/` is unreachable and is not authority: a rollback's leftover bundle is benign, and P2d's migration removes leftovers on v1 before it writes. |
| Files other than `control.yaml` are staged in a redo record and applied after commit, at a before-hash. | **Unchanged**, and the history uses it. Bundles and audit records are immutable, create-if-absent (`Session.write(..., immutable=True)`). The tail is the one replaceable history file, written at its before-hash. Sealed segments (256 entries) are never rewritten. |
| (new) | **Pre-written objects (R8).** A migration writes its bundles before the commit and the redo record lists them by path and hash (`Session.prewritten`); the commit verifies each on disk first. `last_transition` carries only their count and hash. |
| A transition's state is the operation's state. | **A finalizer projects it (R6).** The archival finalizer (`Archive`, the E5 `TxnFinalizer` seam) hands the store a projection, `ctx.commit_state`, with every newly finished unit removed. The operation's own working state is unchanged. |
| Recovery: roll forward the committed redo record, discard newer staged ones. | **Unchanged.** Rolling forward now also writes the tail. Nothing in recovery reads the history. |
| Reads see the whole state. | **Reads of finished work rehydrate (R7).** `work show`, `gate show`, `context pack`, `invoke show` and the harness reads put the one archived unit, and its archived ancestors, into a copy of the state. Listings of finished work are explicit history queries. |
| (new) | **A derived index**, `local/history.sqlite`. Never authority: it catches up from the chain, or rebuilds, and losing `local/` loses nothing. |
| (new) | **Audits outside the lock (R2).** `history audit --expect-rev` reads the root and tail under the lock, verifies outside it, then re-takes the lock and verifies only what was appended meanwhile before it records. |
| (new) | **Schema v2 and the v1 refusal.** v1 Lead mutations are refused with `MIGRATION_REQUIRED` until `aew migrate`, one transaction. |

## What ADR-0011 claims

1. **History independence.** Hot state, active-path latency and a supervisor's re-parse do not grow with finished work (H1–H3). `resume` has no history-linear sweep (H4).
2. **Active complexity is measured** to 1,000 open units (A1).
3. **Historical access.** `history show | list | links | load | audit | reindex`: an exact record by id, listings by kind and date, provenance links, loading a record into a pack as labelled reference context, and full or incremental integrity audits.
4. **Nothing is lost by archival.** The full state (hot state plus every reachable record) is exactly the state an unarchived project would have; the oracle checks it after every step of every walk.
5. **Migration** of an M3 (v1) project is one transaction, crash-safe at every fault point, and refuses while a run may be live.

## Where to look

| Area | Code |
|---|---|
| The cold store: chain, tail, segments, verification, pre-written objects | `src/aew/history/store.py`, `manifest.py` |
| The derived index | `src/aew/history/index.py` |
| Archival finalizer, summaries (R3), `archived_refs` (R4), frontiers (R5), rehydration (R7), Lead records | `src/aew/engine/archive_ops.py` |
| History commands, audit (R2), audit status | `src/aew/engine/history_ops.py` |
| Migration, the v1 refusal | `src/aew/engine/migrate_ops.py`, `engine/base.py` (`lead_txn`, `V1_OPS`) |
| Parent derivation through summaries, the children digest, `legacy_digest` | `src/aew/engine/hierarchy.py`, `hierarchy_ops.py` |
| The commit point, redo record, `prewritten` | `src/aew/engine/store.py`, `engine/seams.py` |
| Schemas | `src/aew/schemas/control.schema.json` (v2), `history.schema.json` |
| The fingerprint's `.aew` exclusion | `src/aew/snapshot/fingerprint.py` |
| Oracle (full state from hot plus history, rules 19–23) | `tests/helpers/invariants.py` |

## Invariants to attack

The oracle rebuilds the full state from hot state and the verified history, runs every earlier rule on it, and adds:

| # | Invariant |
|---|---|
| 19 | The history verifies from `cold.root`, and no unit is both hot and archived |
| 20 | Only finished work is archived; a hot unit never has an archived ancestor |
| 21 | Each hot parent's summary is the recount of its archived children and of the archived Tickets below it |
| 22 | Parent derivation from hot state and summaries equals derivation from the full state (R3) |
| 23 | The integration frontier covers every archived integrated Ticket below it (R5) |

Suggested probes:
- a crash at any point of a commit that archives, seals a segment, records an audit or migrates, then any allowed operation, then a retry;
- an out-of-band change to any reachable record, segment or the tail, including a coordinated rewrite of several, then `history show`, `history audit` and `--full`;
- an audit racing commits that archive (the R2 window; pause point `history.audit_after_verify`);
- moving, cancelling or closing a parent whose children are archived; a late ingest against a parent whose evidence predates migration (`legacy_digest`);
- using an archived credential anywhere (engine, Lead broker, a supervisor): `STALE_AUTHORITY`;
- loading records into packs (`history load`): labels, redaction, fencing, and whether loaded text could act as instruction;
- deleting `local/` at any point;
- anything that makes an active-path command read the history (H2): the profile counters (`AEW_PROFILE`) show parses and reads.

## Measurements

The results and the H1–H4 and A1 verdicts are in the implementation plan, §7.4, with the data in `eval/adr-0011/perf/`. Two runs belong to the operator and are recorded there when done: the Windows reference sweep and the Rocky 8.10 gate (`tools/perf/rocky8-gate.sh`).

## How to run

```bash
python -m pytest -q -n auto -m "not serial" && python -m pytest -q --lane serial
python -m pytest -q tests/integration/test_history_store.py tests/integration/test_archival.py \
                    tests/integration/test_history_surface.py tests/integration/test_migration.py \
                    tests/unit/test_history_manifest.py
AEW_CRASH_ITERATIONS=2000 python -m pytest -q tests/unit/test_store.py              # nightly strength
AEW_WALK_STEPS=150 AEW_HWALK_STEPS=150 python -m pytest -q tests/regression/test_composition_walk.py \
                    tests/regression/test_hierarchy_walk.py
python tools/perf/control_plane.py sweep --points 20:250,20:3000 --reps 1 --work <empty dir> --json <file>
```

## Known limits

- **Linux slopes come from WSL2** on the Windows reference machine, a supplement only. The Rocky 8.10 run is the representative Linux target.
- **Migration is one transaction** and takes about a minute and a half at 3,000 finished Tickets on Windows. It is run once per project. Batching was not adopted (operator, 2026-10-02); the profile is in §7.4.
- **Full verification and index rebuild are linear in history**, by design: neither is on a command's path.
- **The dashboard** reads none of this yet (register F20).
