# ADR-0011 — Hot/cold control state: archiving terminal records out of the commit point

- **Status:** **Accepted direction; Q1 and Q2 approved** (operator/designer, latest decision 2026-10-01). **Not implemented.** The control-state schema is unchanged in M3.
- **Amended** (designer, 2026-09-27, during M3 step 8): success is **history independence**, not a smaller file. The completion criteria below are restated around it.
- **Amended** (operator decision, 2026-10-01): Q2 is resolved. `resume` is an active-state operation and **MUST NOT** sweep all historical evidence on every call. Cold history remains first-class durable project knowledge: reachable, discoverable, provenance-preserving and selectively loadable. Archival changes automatic participation in active state, not epistemic value.
- **Q1 approved** (operator/designer decision, 2026-10-01): retain H1, H3 and A1; refine H2 so storage cost is measured independently from intentionally larger historical output; replace H4 with a fully history-independent `resume`. Exact storage technology is not chosen by this ADR and must be investigated before implementation.
- **Amended for pre-implementation review** (operator/designer, 2026-10-01): history independence also covers hierarchy derivation and archival writes; terminal cold records remain immutable when later facts arise; commit-time invariants may not walk completed history; cold-history integrity gets incremental and full audit paths; the M4 gate requires a minimal first-class history-access surface; and Rocky Linux receives target-specific performance validation. The preferred storage hypothesis is immutable content-addressed records plus bounded append-only tamper-evident manifests, with SQLite/FTS-style lookup layers rebuildable and non-authoritative.
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
- **Integrity and immutability:**
  - A cold record is an immutable record of what was committed at that point in history. It is never rewritten, including when the subject later becomes superseded, moved, promoted, reclassified, or affected by a newer ancestor-plan revision.
  - Later facts about an archived subject are represented by new append-only annotation/lineage records, or by bounded current hot facts when current authority requires them. They link back to the original cold record rather than changing it.
  - Staleness is derived from current/revision relationships and bindings; it is not retroactively written into the historical record.
  - Cold records and any new cold-index/manifest version are written as part of the same transaction that makes the item terminal, through the existing redo staging (ADR-0001), unless a later storage ADR explicitly replaces that commit model.
  - Hot state pins the current cold-history root/index hash; the cold structure pins the records and later annotations it names. This transitive pinning avoids one hot stub per completed item.
  - Reading a cold index/record verifies the applicable pinned hash.
  - A missing or changed **referenced** cold index/record is a contradiction when accessed or during an explicit integrity audit. Unreferenced content-addressed objects left by a rolled-back or failed staged transaction are benign unreachable objects, not contradictions; maintenance may report or collect them.
- **History-independent active derivation and archival writes:**
  - No active-path operation may do work proportional to completed historical descendants merely because they share an open ancestor.
  - Parent state derivation therefore uses bounded incrementally maintained summaries sufficient for current derivation, or another mechanism with the same history-independent property. Completed descendants are not rescanned on every Lead commit, and closed parents are not re-derived during unrelated active transitions.
  - Those summaries are derived/rebuildable from durable records; they do not become an independent authority.
  - Making one item terminal must not require O(n) work in total lifetime history. O(1) or O(log n) cold-structure maintenance is acceptable and is measured; rewriting or re-hashing an ever-growing complete history on each archival transition is not.
- **Reads and historical knowledge:**
  - Normal active-path commands parse hot state plus only the cold records they actually need.
  - `resume` reconstructs the current authoritative working state and **does not** sweep completed historical evidence merely because it might be useful.
  - Cold material remains first-class AEW knowledge. AEW must provide a supported historical discovery/reconstruction path that can locate, inspect and trace archived decisions, research, plans, evidence, reviews and provenance without requiring the operator or Lead to browse storage files manually.
  - Historical material may be loaded selectively into current reasoning as reference context. Retrieval does not silently make it current authoritative evidence; version-, source-, environment- or state-sensitive claims must be revalidated through normal AEW evidence/decision paths before current authority depends on them.
  - Derived summaries/search indexes may accelerate discovery but are replaceable. Loss of a derived index may reduce convenience or performance, never erase the durable knowledge.
- **Cold-history integrity audit:**
  - Normal `resume` does not exhaustively traverse historical records.
  - AEW provides **incremental verification** from the last verified root to the current root, checking newly appended structure/content plus linkage to the previously verified root.
  - AEW also provides a **full verification** that walks all records reachable from the current cold root; this is the periodic bit-rot/corruption check.
  - Epic closeout and an AEW-managed backup/export require at least an incremental audit through the current root. CI runs incremental verification routinely and a periodic/full fixture on the cold-store corpus. Operators may request either form explicitly.
  - AEW records the current cold root, the root verified through incremental/full checking, the last full-verification time, and the number/age of archival transitions since those points.
  - `status` reports audit age/backlog against policy thresholds (for example, unverified additions and age since full audit), rather than presenting a permanently alarming boolean whenever history advanced after the last full pass.

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
7. **Existing projects migrate** in one Lead transaction (or on first write), idempotently and crash-safely, with a test on a project built by the M3 code. Migration requires a quiescent project with no live harness runs; AEW refuses migration otherwise. The one-time migration may be slow on a large M3 control file, but it cannot create false lost-heartbeat semantics because no live supervisors are permitted during it.
8. **M1, M2 and M3 tests stay unchanged**, except tests that inspect the raw layout of `control.yaml` or the deliberately changed history-access path. The invariant oracle learns the cold root/index additively.
9. **Hierarchy derivation is history-independent.** An open parent with thousands of completed descendants does not force those descendants back onto every active commit path. Incremental parent summaries, if used, are transactionally updated and deterministically rebuildable.
10. **Archival writes are sublinear in history.** Closing one item does not rewrite, parse or hash a representation proportional to total history; measured O(1) or O(log n) cold-structure maintenance is acceptable.
11. **Integrity status is explicit.** The system distinguishes the current cold root, the incrementally verified root, and the last full verification, and reports audit age/backlog against policy thresholds.
12. **Minimal historical access is first-class.** Before this ADR closes, AEW can show a historical record by stable id, list historical records by kind and bounded date/range, follow recorded provenance/reference links, and selectively load an exact chosen historical record into current reference context. Rich search/ranking is not required by this ADR.
13. **Commit-time invariants are history-independent.** Any invariant/oracle check on the normal transition commit path is computable from current hot state, the transition delta, and bounded derived summaries. It MUST NOT scan completed history. Full-corpus invariant verification belongs to the explicit historical-integrity audit path.
14. **Historical text remains reference data, not instruction.** Loading archived model-authored or externally sourced material preserves its source/trust classification, marks it as historical/reference context, and records the load in the invocation's provenance. Hash integrity proves identity, not correctness or instruction authority.

## Completion criteria

This ADR is closed only when all of these hold. They are measured with `tools/perf/control_plane.py` on the reference Windows machine used in `m3-performance.md`.

### The property: history independence (designer, 2026-09-27)

After archival, steady-state hot-state size and command latency must **primarily track active project complexity** (open units, invocations that can act, active credentials), **not lifetime project history** (completed units). A smaller YAML file is not the goal; this property is.

It is measured with `control_plane.py sweep` on four series:
- **history series:** 20 open units, with 250, 1,000 and 3,000 completed Tickets;
- **active series:** 250 completed Tickets, with **20, 200, 500 and 1,000** open/planned units;
- **hierarchy-history series:** one open Epic (and a Story layer where representative) with a fixed small active frontier and 250, 1,000 and 3,000 completed descendant Tickets. This specifically catches parent derivation or closeout logic that rescans completed descendants;
- **cold-write series:** synthetic cold stores at **1k, 3k, 10k and 30k** records, measuring one append/update, root/manifest maintenance, exact lookup and incremental verification.

The hierarchy-history series records commit latency, parent-derivation/recomputation cost, `status`, `work tree` and `resume` separately. If the 500/1,000-unit active series shows unacceptable growth, implementation must decide whether all planned work genuinely belongs in hot state or whether a distinct deferred/not-yet-active representation is required; this ADR does not preselect that broader model.

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
  - The same history-independence property holds for the hierarchy-history series: completed descendants do not accumulate as per-item active-state metadata merely because an ancestor remains open.
- **H2, latency — retain the 0.25 s history-growth budget for active-path work, and measure cold-store slope separately.**
  - For active/current-state commands, or any benchmark with fixed output cardinality, the 3,000-completed case takes at most **0.25 s longer** than the 250-completed case (baseline: 20–36 s longer). Active-path work is history-independent except for explicitly requested historical output.
  - A command that intentionally asks to enumerate more historical results may scale with requested output; its lookup overhead must not force unrelated active-path commands to enumerate history.
  - Benchmarks for `status`, `work tree` and future history queries hold returned-result cardinality constant when measuring active-path history independence, and separately report serialization/output cost for deliberately larger listings.
  - Archiving one newly terminal item is included. Cold-structure maintenance must be **sublinear in lifetime history with a measured slope**; O(1) or O(log n) designs are acceptable, O(n) rewrite/re-hash of complete history is not.
  - The hierarchy-history series must meet the same bounded-history overhead for ordinary Lead commits and parent recomputation.
  - The cold-write series at 1k/3k/10k/30k measures append/update slope, root/manifest maintenance, exact lookup and incremental verification independently of normal project construction.
- **H3, heartbeat — retain.** A supervisor's re-parse of a changed hot state at 20 open and 3,000 completed takes **≤ 0.25 s** (baseline: about 20 s, twice the 10 s staleness limit).
- **H4, `resume` — replace the historical sweep.**
  - `resume` itself meets H2; it has **no history-linear evidence sweep**.
  - A terminal unit's sealed evidence and cold representation are verified when archived. Later use verifies the cold index/record hashes that are actually read.
  - AEW provides an explicit full historical-integrity operation for operators/tests that need to verify the complete cold corpus; that operation is not on the normal `resume` path.
  - `resume` may read cold records only when current active state explicitly depends on them, not merely because old information might be useful.
  - Incremental verification advances the verified root over newly appended history; periodic full verification covers the complete reachable corpus. `status` reports verified root, current root, unverified-addition count/age, and last full-verification age against policy thresholds.
- **A1, active complexity — retain and extend.** Along the active series through 1,000 open/planned units, hot bytes and latency added per active unit are measured against the M3 baseline (about 0.9–1.3 KB and 0–2 ms per open unit). Report the measured slope and any knee rather than assuming linear growth remains acceptable indefinitely. If the extended series violates the absolute latency bounds, the storage investigation must address planned/deferred-unit residency before this ADR closes.

**Historical-access acceptance.** Performance work must not make AEW more opaque. The minimum gate for ADR-0011 is deliberately small and does not require semantic search:
- show an exact historical record by stable AEW id;
- list historical records by kind and bounded date/range;
- follow recorded provenance/reference links between historical records;
- selectively load an exact chosen historical record (or a bounded linked set) into current reference context without silently promoting it to current authoritative evidence; the load preserves source/trust labels and is recorded in the invocation's context provenance.

A fresh Lead must therefore be able to locate and reconstruct completed work without knowing storage paths. Rich text/semantic search, ranking and “explain why” synthesis may come later. Deleting any derived search/index cache must not destroy the minimum capability; the derived structure must be rebuildable from durable project state.

The absolute bounds below remain as a floor.

### Absolute bounds and coverage

- **Size.** *Superseded by H1 (2026-09-27).* The original criterion was hot state per DONE Ticket, with its invocations and credentials, ≤ 1.5 KB.
- **Speed at 3,000 units.**
  - Every measured read (`lead show`, `status`, `work tree`, `gate show`, `context pack`, `harness status`): **≤ 2 s**.
  - `checkpoint`, `work dispatch` and `review ingest`: **≤ 4 s**.
  - `resume`: **≤ 8 s**.
- **Heartbeat.** A supervisor's re-parse of a changed 3,000-unit hot state takes **≤ 2.5 s**, a quarter of the 10 s staleness limit.
- **Coverage.**
  - The scale regression still passes, including hierarchy-history, extended active-frontier and cold-write series.
  - The crash matrix and seeded walks include archival, rollback-created unreachable cold objects, incremental parent-summary maintenance if used, and cold-root/index updates.
  - The migration test passes.
  - The whole suite passes on both OSes, M1/M2/M3 tests unchanged.
  - The Windows reference machine runs the full H1–H4/A1 sweep.
  - A representative Rocky Linux target runs at minimum the hierarchy-history sweep, H3 changed-hot-state supervisor reparse, archival-write scaling, and the absolute heartbeat bound. If practical, run the full sweep there as well.
- **Review.** It is reviewed like a milestone: the store is the authority, so a review brief states what changed in ADR-0001's model.

## Implementation prerequisite: choose the storage mechanism deliberately

This ADR decides the **semantic split** (hot active authority versus durable cold knowledge), not the physical database/file layout. Before implementation code is accepted, the implementation plan must investigate the best storage mechanism for AEW rather than assuming that today's YAML-plus-files layout should simply be extended.

The current **preferred hypothesis**, to test rather than assume, is:

- immutable content-addressed files remain authoritative durable records;
- a bounded append-only **tamper-evident** manifest/segment structure is pinned from the constant-size hot cold-history root;
- appending one terminal record creates O(1) or O(log n) authoritative metadata, never O(n) work in lifetime history;
- a SQLite/FTS/other lookup database, if useful, is derived and rebuildable, never authority;
- hash pinning detects corruption and unsynchronized change inside the repository trust boundary; it is **not keyed authentication**. An actor able to rewrite both cold content and the hot root can forge both unless the surrounding containment/custody boundary prevents that. If keyed signatures are ever required, key lifecycle belongs with ADR-0005 and requires an explicit design decision.

Do not implement the root as an ever-growing list whose rewrite or hash cost becomes linear. Plausible forms include bounded append-only segments with a hash-linked tail/root, a bounded-fanout persistent/Merkle structure, or another design that proves the required measured slope.

At minimum, compare the preferred hypothesis with other plausible designs such as a transactional indexed store or hybrid layout. The comparison must cover:

- the one-commit-point/crash-recovery guarantees of ADR-0001;
- immutable provenance, later append-only annotations/lineage, and content-addressed verification;
- history-independent hot reads/writes and sublinear archival writes;
- first-class historical discovery, relationship traversal and reconstruction;
- incremental/rebuildable hierarchy summaries for active parent derivation;
- incremental and periodic full integrity verification;
- migration and schema evolution;
- offline portability and backup/restore;
- human inspectability and repair;
- index rebuildability and the rule that a disposable cache never becomes authority;
- filesystem/Git metadata cost as history grows, especially on Windows;
- active-frontier scaling for large up-front decompositions;
- scale for long-lived Epics/projects, including the 30k-record synthetic cold-store fixture.

A broader AEW storage layer is explicitly in scope if measurement shows it materially improves these properties. If the preferred design changes ADR-0001's authority/commit-point model, or makes a database/index independently authoritative rather than a hash-pinned/rebuildable representation of durable records, that change requires an explicit ADR-0001 amendment (or a new superseding storage ADR) before implementation proceeds.

## Not decided here

These implementation choices remain open, within the approved invariants and completion criteria:

- exact cold-record layout/naming and tamper-evident manifest/index form;
- the append-only annotation/lineage representation for facts learned after an item was archived;
- whether archival happens directly at the terminal transition or through a bounded Lead-initiated compaction that preserves the same atomicity and cost properties;
- the concrete incremental parent-summary representation and rebuild path;
- how Stories and Epics archive closed children's detail;
- whether extended active-frontier measurements require a distinct residency tier for approved but deferred/not-yet-active work;
- whether the control schema version changes;
- the exact CLI/API names for minimum history access and incremental/full integrity-audit surfaces.

No designer questions remain open in this ADR.

- **Q1 is approved:** H1, H2, H3, H4 and A1 are the completion criteria above, including hierarchy-history, extended active-frontier and cold-write scaling. The storage-design investigation remains an implementation prerequisite and may propose an ADR amendment if meeting those criteria safely requires changing ADR-0001's storage/commit model.
- **Q2 is approved:** normal `resume` is history-independent; exhaustive cold-history traversal is not on the resume path. Cold knowledge remains first-class, discoverable, traceable and selectively loadable, with incremental/full integrity verification provided separately.

## Pre-implementation review disposition (2026-10-01)

Independent document review identified one substantive gap and several tightening points. This revision incorporates them without reopening Q1 or Q2:

- terminal cold records remain immutable; later supersession/move/promotion/lineage facts are append-only linked records or bounded current facts;
- commit-time invariant checking may not traverse completed history;
- hashes are described as tamper-evident, not keyed authentication;
- active-path operations remain history-independent, while cold-store maintenance must be sublinear and is measured through 30k synthetic records;
- active-frontier scaling is measured through 1,000 open/planned units;
- integrity auditing supports incremental verification plus periodic full passes;
- rollback-created unreferenced cold objects are benign;
- migration requires quiescence;
- historical context retains its original trust classification and load provenance.

## Alternatives considered

- **Deduplicate pinned role cards** (store each card version once). This is smaller in effect (about 14%) and does not address growth. It may be part of the implementation.
- **Accept the envelope** (fine up to a few hundred units). Rejected by the operator and designer (2026-09-27): cost would keep growing with every completed Ticket.
- **A faster serialization format alone, or an authoritative parse cache in `local/`.** Rejected: neither addresses the semantic requirement for history independence. A disposable cache outside the commit point must not become a second copy of authority. A broader durable storage mechanism is not rejected here; it is subject to the implementation-prerequisite investigation above and to ADR-0001's authority constraints.
- **Authoritative relational database as the default hypothesis.** Not selected. The preferred investigation starts from immutable content-addressed files plus bounded tamper-evident manifests and a rebuildable lookup index because that most directly preserves ADR-0001, offline portability, inspectability and repair. A database-backed authority remains a candidate only if measurement demonstrates a material advantage worth explicitly amending the storage/commit model.
