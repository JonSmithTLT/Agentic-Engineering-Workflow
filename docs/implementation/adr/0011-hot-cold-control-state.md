# ADR-0011 — Hot/cold control state: archiving terminal records out of the commit point

- **Status:** **Accepted direction; Q1 and Q2 approved** (operator/designer, latest decision 2026-10-01). **Not implemented.** The control-state schema is unchanged in M3.
- **Amended** (designer, 2026-09-27, during M3 step 8): success is **history independence**, not a smaller file. The completion criteria below are restated around it.
- **Amended** (operator decision, 2026-10-01): Q2 is resolved. `resume` is an active-state operation and **MUST NOT** sweep all historical evidence on every call. Cold history remains first-class durable project knowledge: reachable, discoverable, provenance-preserving and selectively loadable. Archival changes automatic participation in active state, not epistemic value.
- **Q1 approved** (operator/designer decision, 2026-10-01): retain H1, H3 and A1; refine H2 so storage cost is measured independently from intentionally larger historical output; replace H4 with a fully history-independent `resume`. Exact storage technology is not chosen by this ADR and must be investigated before implementation.
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

**The control commit point holds hot state only. Terminal detail moves into immutable, content-addressed cold records. Hot state pins a constant-size cold-history root/index descriptor; that cold index in turn pins the immutable records.**

- **Hot:** everything a current decision or authority check can still depend on:
  - the Lead;
  - active credentials;
  - every non-terminal work unit and every invocation that can still act;
  - counters;
  - the last transition;
  - a **constant-size descriptor** for the current cold-history index/root, including its identity/path and SHA-256;
  - only bounded historical facts that are strictly required by currently active references or invariants.
- **Cold:** durable project knowledge and terminal detail under `.aew/`:
  - a completed, cancelled or superseded invocation's pack sources and card content, and its snapshot and workspace details;
  - a revoked credential entry, beyond what the engine and invariant oracle still need hot;
  - a DONE or CANCELLED unit's evidence references, integration record, history and gate bindings;
  - the immutable/append-only index or manifest that maps stable AEW identities and provenance relationships to those content-addressed records.
- **Integrity:**
  - Cold records and any new cold-index version are written as part of the same transaction that makes the item terminal, through the existing redo staging (ADR-0001), unless a later storage ADR explicitly replaces that commit model.
  - Hot state pins the current cold-history root/index hash; the cold index pins the records it names. This transitive pinning avoids one hot stub per completed item.
  - Reading a cold index or record verifies the applicable pinned hash.
  - A missing or changed cold index/record is a contradiction when accessed or during an explicit full-integrity audit. Normal `resume` does not rediscover that contradiction by exhaustively walking all history.
- **Reads and historical knowledge:**
  - Normal active-path commands parse hot state plus only the cold records they actually need.
  - `resume` reconstructs the current authoritative working state and **does not** sweep completed historical evidence merely because it might be useful.
  - Cold material remains first-class AEW knowledge. AEW must provide a supported historical discovery/reconstruction path that can locate, inspect and trace archived decisions, research, plans, evidence, reviews and provenance without requiring the operator or Lead to browse storage files manually.
  - Historical material may be loaded selectively into current reasoning as reference context. Retrieval does not silently make it current authoritative evidence; version-, source-, environment- or state-sensitive claims must be revalidated through normal AEW evidence/decision paths before current authority depends on them.
  - Derived summaries/search indexes may accelerate discovery but are replaceable. Loss of a derived index may reduce convenience or performance, never erase the durable knowledge.

## Invariants the implementation must keep

1. **One commit point.**
   - Archival happens inside a normal transition. A crash at any point exposes the previous or the next state, never a hybrid.
   - Roll-forward stays idempotent. Every existing fault point, and the new ones, are covered by the crash matrix and the seeded walks.
2. **Nothing becomes unverifiable.** Every cold record is pinned by hash from the hot state. Nothing authority-relevant is dropped, only moved: pack SHA-256, card SHA-256, credential ids, revocation times, evidence hashes and integration commits.
3. **Authority is unchanged.**
   - Active credentials and every invocation that can act stay hot.
   - A stub is enough for every credential check, for rotation and for the harness run model (runs, `R-<INV>-<n>`).
4. **Current reconstruction is unchanged.** Cold records are durable project state, not `local/`. `aew resume` after deleting `.aew/local` remains complete for the current authoritative working state (AT-1, AT-11, AT-15) without loading unrelated completed history.
5. **Historical reconstruction is first-class.** Archiving MUST NOT turn durable AEW knowledge into a storage graveyard. A fresh Lead or operator can discover and reconstruct completed work and its rationale through supported AEW interfaces, following stable identities and provenance links back to the original immutable records. Exact command names and query implementation are left to implementation.
6. **Provenance is unchanged.** Evidence and completion records keep referencing what they reference today, and `invoke show` and pack regeneration for a completed invocation read its cold record transparently.
7. **Existing projects migrate** in one Lead transaction (or on first write), idempotently, crash-safely, with a test on a project built by the M3 code.
8. **M1, M2 and M3 tests stay unchanged**, except tests that inspect the raw layout of `control.yaml` or the deliberately changed history-access path. The invariant oracle learns the cold root/index additively.

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

**Q1 approved threshold disposition (operator/designer, 2026-10-01):**

- **H1, hot state — retain.**
  - Along the history series, hot state at 3,000 completed is at most **1.25×** its size at 250 completed (baseline: 11.9×).
  - At 20 open and 3,000 completed, history is at most **20%** of the hot state (baseline: 99.96%).
  - A timing-free regression asserts both on the scale-regression project.
  - The implementation MUST NOT satisfy this by hiding per-item history in another always-read authority file; the active commit path must remain history-independent.
- **H2, latency — retain the 0.25 s history-growth budget, but measure storage cost separately from requested output volume.**
  - For active/current-state commands, or any benchmark with fixed output cardinality, the 3,000-completed case takes at most **0.25 s longer** than the 250-completed case (baseline: 20–36 s longer).
  - A command that intentionally asks to enumerate more historical results may scale with the amount of requested output; its storage/index lookup overhead must still be bounded and it must not force unrelated active-path commands to enumerate history.
  - Benchmarks for `status`, `work tree` and future history queries therefore hold returned-result cardinality constant when measuring history-independence, and separately report serialization/output cost when the user explicitly asks for a larger historical listing.
- **H3, heartbeat — retain.** A supervisor's re-parse of a changed hot state at 20 open and 3,000 completed takes **≤ 0.25 s** (baseline: about 20 s, twice the 10 s staleness limit).
- **H4, `resume` — replace the historical sweep.**
  - `resume` itself meets H2; it has **no history-linear evidence sweep**.
  - A terminal unit's sealed evidence and cold representation are verified when archived. Later use verifies the cold index/record hashes that are actually read.
  - AEW provides an explicit full historical-integrity operation for operators/tests that need to verify the complete cold corpus; that operation is not on the normal `resume` path.
  - `resume` may read cold records only when current active state explicitly depends on them, not merely because old information might be useful.
- **A1, active complexity — retain.** Along the active series, the hot bytes and latency added per open unit are no worse than the M3 baseline (about 0.9–1.3 KB and 0–2 ms per open unit).

**Historical-access acceptance.** Performance work must not make AEW more opaque. A fresh Lead must be able, through a supported AEW history/reconstruction surface, to locate a completed decision or investigation without knowing its storage path, inspect its original immutable records, trace its provenance/relationships, and selectively load relevant material as reference context. Deleting any derived search/index cache must not destroy this ability; the derived structure must be rebuildable from durable project state.

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

## Implementation prerequisite: choose the storage mechanism deliberately

This ADR decides the **semantic split** (hot active authority versus durable cold knowledge), not the physical database/file layout. Before implementation code is accepted, the implementation plan must investigate the best storage mechanism for AEW rather than assuming that today's YAML-plus-files layout should simply be extended.

At minimum, compare plausible designs such as a file-backed content-addressed store with a compact durable index, a transactional indexed store, segmented/append-only manifests, or a hybrid in which immutable artifacts remain canonical and an index is rebuildable. The comparison must cover:

- the one-commit-point/crash-recovery guarantees of ADR-0001;
- immutable provenance and content-addressed verification;
- history-independent hot reads/writes;
- first-class historical discovery, relationship traversal and reconstruction;
- migration and schema evolution;
- offline portability and backup/restore;
- human inspectability and repair;
- index rebuildability and the rule that a disposable cache never becomes authority;
- scale for long-lived Epics/projects, not only the 3,000-unit fixture.

A broader AEW storage layer is explicitly in scope for this investigation if it materially improves these properties. If the preferred design changes ADR-0001's authority/commit-point model, or makes a database/index independently authoritative rather than a hash-pinned representation of durable records, that change requires an explicit ADR-0001 amendment (or a new superseding storage ADR) before implementation proceeds.

## Not decided here

These are left to the implementation, within the invariants:

- the cold-record layout and naming, and the cold index's form (one file, segments, a hash chain), provided the hot state pins it by hash;
- whether archival happens at the terminal transition or in a Lead-initiated compaction;
- how Stories and Epics archive their closed children's detail;
- whether the control schema version changes.

No designer questions remain open in this ADR.

- **Q1 is approved:** H1, H2, H3, H4 and A1 are the completion criteria above. The storage-design investigation remains an implementation prerequisite and may propose an ADR amendment if meeting those criteria safely requires changing ADR-0001's storage/commit model.
- **Q2 is approved:** normal `resume` is history-independent; exhaustive cold-history validation belongs to an explicit integrity/audit path, while cold knowledge remains first-class, discoverable and queryable.

## Alternatives considered

- **Deduplicate pinned role cards** (store each card version once). This is smaller in effect (about 14%) and does not address growth. It may be part of the implementation.
- **Accept the envelope** (fine up to a few hundred units). Rejected by the operator and designer (2026-09-27): cost would keep growing with every completed Ticket.
- **A faster serialization format alone, or an authoritative parse cache in `local/`.** Rejected: neither addresses the semantic requirement for history independence. A disposable cache outside the commit point must not become a second copy of authority. A broader durable storage mechanism is not rejected here; it is subject to the implementation-prerequisite investigation above and to ADR-0001's authority constraints.
