# ADR-0011 — Hot/cold control state: archiving terminal records out of the commit point

- **Status:** **Accepted direction** (operator and designer, 2026-09-27). **Not implemented.** The control-state schema is unchanged in M3.
- **Amended** (designer, 2026-09-27, during M3 step 8): success is **history independence**, not a smaller file. The completion criteria below are restated around it; the thresholds are proposed from the step-8 baseline and **await the designer's confirmation** before implementation begins.
- **Sequencing:** a **prerequisite for M4**. It is implemented and accepted after M3's acceptance (independent review) and **before any M4 work begins**. M4 does not start while this ADR is open.
- **Spec basis:**
  - ADR-0001: one control file is the atomic commit point, with redo staging and an advisory lock.
  - WC §5: the crash-safe control-authority rule.
  - KC §12.3: durable records.
  - KC §15.1: reconstruction and contradictions.
  - KC §11: validation provenance.
  - ADR-0005: credentials.
  - ADR-0009 and ADR-0010: runs and execution pins.
- **Evidence:** `m3-performance.md` §5, `eval/m3/perf/`, `tools/perf/control_plane.py`.
- **Nature:** a change to how the authoritative state is stored, not to what it means. No transition, gate, authority rule or piece of provenance changes.

## Context

M3 step 7 measured AEW's control plane on projects of 50, 500 and 3,000 units. After fixing three pathologies, every command still costs time linear in the size of `state/control.yaml`: parsing, schema validation and, for a mutation, writing it.

The file grows with completed work, which never leaves it. A DONE Ticket with its four invocations holds about 20 KB; a planned one about 1 KB. At 500 units the file is 7.0 MB:

| Part | Size | Share | What it is |
|---|---|---|---|
| Invocations | 4.16 MB | 59% | Nearly all completed. Each keeps its pinned pack-source list (about 1.5 KB) and the full content of its role card (about 0.7 KB). |
| Work units | 2.01 MB | 29% | Each DONE Ticket keeps its evidence references, integration record and history. |
| Credential entries | 0.49 MB | 7% | Nearly all revoked. |

After step 7, at 500 units, reads take 1.8–2.2 s and commits about 3 s. At 3,000 units (42 MB), reads take about 13.6 s and commits about 23 s. After each Lead commit, every live run's supervisor re-parses for about 13 s, which exceeds the 10 s heartbeat staleness limit, so a healthy run can briefly show as `lost`.

## Decision (direction)

**The control file holds hot state only. Terminal records move into immutable, content-addressed cold records whose hashes the hot state pins.**

- **Hot:** everything a decision can still depend on:
  - the Lead;
  - active credentials;
  - every non-terminal work unit and every invocation that can still act;
  - counters;
  - the last transition;
  - for each terminal item, a **stub**: its identity, terminal status, the facts other records reference, and the path and SHA-256 of its cold record.
- **Cold:** the detail of terminal items, under `.aew/`:
  - a completed, cancelled or superseded invocation's pack sources and card content, and its snapshot and workspace details;
  - a revoked credential entry, beyond what the engine and the invariant oracle still need (rule 17 needs each credential's revocation time);
  - a DONE or CANCELLED unit's evidence references, integration record, history and gate bindings.
- **Integrity:**
  - A cold record is written once, as part of the same transaction that makes the item terminal, through the existing redo staging (ADR-0001). It is never modified.
  - Its hash is pinned in the hot stub. Reading it verifies the hash.
  - A missing or changed cold record is a contradiction (KC §15.1), exactly as a changed Ticket record is today.
- **Reads:** a command parses only the hot state, plus the cold records it actually needs:
  - `invoke show` for a completed invocation;
  - a parent closeout that reviews its children;
  - `resume`'s integrity sweep, which verifies hashes rather than parsing.

## Invariants the implementation must keep

1. **One commit point.**
   - Archival happens inside a normal transition. A crash at any point exposes the previous or the next state, never a hybrid.
   - Roll-forward stays idempotent. Every existing fault point, and the new ones, are covered by the crash matrix and the seeded walks.
2. **Nothing becomes unverifiable.** Every cold record is pinned by hash from the hot state. Nothing authority-relevant is dropped, only moved: pack SHA-256, card SHA-256, credential ids, revocation times, evidence hashes and integration commits.
3. **Authority is unchanged.**
   - Active credentials and every invocation that can act stay hot.
   - A stub is enough for every credential check, for rotation and for the harness run model (runs, `R-<INV>-<n>`).
4. **Reconstruction is unchanged.** Cold records are durable project state, not `local/`. `aew resume` after deleting `.aew/local` is exactly as complete as today (AT-1, AT-11, AT-15).
5. **Provenance is unchanged.** Evidence and completion records keep referencing what they reference today, and `invoke show` and pack regeneration for a completed invocation read its cold record transparently.
6. **Existing projects migrate** in one Lead transaction (or on first write), idempotently, crash-safely, with a test on a project built by the M3 code.
7. **M1, M2 and M3 tests stay unchanged**, except tests that inspect the raw layout of `control.yaml`. The invariant oracle learns stubs additively, as oracle rules 17 and 18 were added in M3.

## Completion criteria

This ADR is closed only when all of these hold. They are measured with `tools/perf/control_plane.py` on the reference Windows machine used in `m3-performance.md`.

### The property: history independence (designer, 2026-09-27)

After archival, steady-state hot-state size and command latency must **primarily track active project complexity** (open units, invocations that can act, active credentials), **not lifetime project history** (completed units). A smaller YAML file is not the goal; this property is.

It is measured with `control_plane.py sweep` on two series:
- **history series:** 20 open units, with 250, 1,000 and 3,000 completed Tickets;
- **active series:** 250 completed Tickets, with 20 and 200 open units.

`control_plane.py footprint` attributes every byte of the control state to open units, to history, or to neither (the Lead, counters).

**Baseline (M3, the code as of step 8; `m3-performance.md` §7, `eval/m3/perf/sweep.json`):**

| | 20 open, 250 completed | 20 open, 3,000 completed | 200 open, 250 completed |
|---|---|---|---|
| `control.yaml` | 5.2 MB | 62.1 MB | 5.4 MB |
| of which open units (live and ended records) | 26 KB | 26 KB | 187 KB |
| of which history | 5.17 MB | 62.05 MB (99.96%) | 5.17 MB |
| `lead show` | 1.44 s | 21.6 s | 1.40 s |
| `checkpoint` | 2.09 s | 35.9 s | 2.21 s |
| `resume` | 3.9 s | 50.4 s | 4.3 s |

Today, each completed Ticket adds about 20.7 KB of hot state, 7–13 ms to every command and 17 ms to `resume`; each open (planned) unit adds about 0.9–1.3 KB and no measurable latency.

**Why the per-item stub budget is not enough.** The criterion this ADR first stated, at most 1.5 KB of hot state per DONE Ticket, would still leave hot state at 20 open and 3,000 completed about 99% history (4.5 MB of stubs against 26 KB of open work). Even a 100-byte index entry per completed Ticket would leave it about 92% history. Meeting the property therefore implies that the hot state carries history only as **constant-size aggregates** (counters, and the hash of a cold index), and that lookups by id and listings of completed items are served from a **compact, hash-pinned cold index** that only the commands needing history read. That is a consequence of the property, not a decision on layout (see "Not decided here").

**Proposed thresholds (awaiting the designer's confirmation):**

- **H1, hot state.**
  - Along the history series, hot state at 3,000 completed is at most **1.25×** its size at 250 completed (baseline: 11.9×).
  - At 20 open and 3,000 completed, history is at most **20%** of the hot state (baseline: 99.96%).
  - A timing-free regression asserts both on the scale-regression project.
- **H2, latency.**
  - Along the history series, every measured command except `resume` takes at most **0.25 s longer** at 3,000 completed than at 250 completed (baseline: 20–36 s longer).
  - This includes `status` and `work tree`, whose output lists completed units and may read the cold index.
- **H3, heartbeat.** A supervisor's re-parse of a changed hot state at 20 open and 3,000 completed takes **≤ 0.25 s** (baseline: about 20 s, twice the 10 s staleness limit).
- **H4, `resume`.** Everything except its evidence-integrity sweep meets H2. The sweep verifies every unit's sealed evidence on every call (baseline: 2.0 s → 24.0 s along the history series). Whether it stays exhaustive over history is a KC §15.1 decision for the designer (see "Not decided here"). If it stays, its cost is reported separately as the one history-linear term.
- **A1, active complexity.** Along the active series, the hot bytes and the latency added per open unit are no worse than the M3 baseline (about 0.9–1.3 KB and 0–2 ms per open unit).

The absolute bounds below remain as a floor.

### Absolute bounds and coverage

- **Size.** *Superseded by H1 (2026-09-27).* The original criterion was hot state per DONE Ticket, with its invocations and credentials, ≤ 1.5 KB.
- **Speed at 3,000 units.**
  - Every measured read (`lead show`, `status`, `work tree`, `gate show`, `context pack`, `harness status`): **≤ 2 s**.
  - `checkpoint`, `work dispatch` and `review ingest`: **≤ 4 s**.
  - `resume`: **≤ 8 s**.
- **Heartbeat.** A supervisor's re-parse of a changed 3,000-unit hot state takes **≤ 2.5 s**, a quarter of the 10 s staleness limit.
- **Coverage.**
  - The scale regression still passes.
  - The crash matrix and the seeded walks include archival.
  - The migration test passes.
  - The whole suite passes on both OSes, M1/M2/M3 tests unchanged.
- **Review.** It is reviewed like a milestone: the store is the authority, so a review brief states what changed in ADR-0001's model.

## Not decided here

These are left to the implementation, within the invariants:

- the cold-record layout and naming, and the cold index's form (one file, segments, a hash chain), provided the hot state pins it by hash;
- whether archival happens at the terminal transition or in a Lead-initiated compaction;
- how Stories and Epics archive their closed children's detail;
- whether the control schema version changes.

These are for the designer, before implementation:

- whether `resume`'s evidence-integrity sweep stays exhaustive over completed history on every call (KC §15.1), or verifies a completed unit's evidence once, at archival, and afterwards only the cold records' pinned hashes (H4);
- confirmation of the H1–H3 and A1 thresholds.

## Alternatives considered

- **Deduplicate pinned role cards** (store each card version once). This is smaller in effect (about 14%) and does not address growth. It may be part of the implementation.
- **Accept the envelope** (fine up to a few hundred units). Rejected by the operator and designer (2026-09-27): cost would keep growing with every completed Ticket.
- **A faster format or a parse cache in `local/`.** Rejected: a format change to JSON is a larger change to ADR-0001 than this one. A cache outside the commit point would be a second copy of authority.
