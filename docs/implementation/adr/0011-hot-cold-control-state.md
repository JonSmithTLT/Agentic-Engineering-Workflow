# ADR-0011 — Hot/cold control state: archiving terminal records out of the commit point

- **Status:** **Accepted direction** (operator and designer, 2026-09-27). **Not implemented.** The control-state schema is unchanged in M3.
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

- **Size.** Hot state per DONE Ticket, with its invocations and credentials, is **≤ 1.5 KB** (from about 20 KB). A timing-free regression asserts the hot bytes added per cloned DONE Ticket.
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

- the cold-record layout and naming;
- whether archival happens at the terminal transition or in a Lead-initiated compaction;
- how Stories and Epics archive their closed children's detail;
- whether the control schema version changes.

## Alternatives considered

- **Deduplicate pinned role cards** (store each card version once). This is smaller in effect (about 14%) and does not address growth. It may be part of the implementation.
- **Accept the envelope** (fine up to a few hundred units). Rejected by the operator and designer (2026-09-27): cost would keep growing with every completed Ticket.
- **A faster format or a parse cache in `local/`.** Rejected: a format change to JSON is a larger change to ADR-0001 than this one. A cache outside the commit point would be a second copy of authority.
