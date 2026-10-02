# ADR-0011 storage investigation

- **Status:** investigation for the operator and designer. Not governing. It is the first half of ADR-0011's "Implementation prerequisite: choose the storage mechanism deliberately". The second half is measurement (§8).
- **Date:** 2026-10-01. Revised the same day for the operator's decisions (§9) and ADR-0011's final pre-implementation text.
- **Brief:** ADR-0011, final pre-implementation text (2026-10-01). It is awaiting a corrected file from the designer (two stale duplicate passages) before it lands on PR #8; nothing below depends on the duplicates. Also ADR-0001 (one commit point, redo staging, advisory lock).
- **Method so far:** reading the code at `main` (`5d4fa62`) and a real project's `.aew/`, plus a standalone spike (`storage_spike.py`, §8) that has only been smoke-tested. **No measured results yet.**

## 1. Recommendation

**Adopt the preferred hypothesis, in the concrete form below.** It meets every invariant (1–14) and criterion (H1–H4, A1) without amending ADR-0001.

| Part | Form |
|---|---|
| **Hot state** | `state/control.yaml`, as today, minus terminal detail. It gains a constant-size `cold` root, an audit status, a bounded list of recent completions, per-parent counters, and bounded current facts on dependency edges that point at archived Tickets. |
| **Cold records** | One immutable **bundle per terminal work unit**: the unit's control record, its ended invocations and their revoked credentials. Written create-if-absent through the existing redo staging, at `work/<id>/archive.yaml`, next to the unit's existing durable records, **automatically at the terminal transition** (operator decision). Never rewritten. |
| **Later facts** | Append-only **annotation records** (for example `work/<id>/annotations/<n>.yaml`): supersession, a move, a promotion, a lineage link. Each links back to the bundle it is about (ADR-0011, "integrity and immutability"). |
| **Cold index (authoritative, bounded)** | Append-only manifest segments in `history/`: a mutable **tail** of at most 256 entries, plus **sealed segments**, each holding the SHA-256 of the one before (a hash chain). The hot root pins the tail's hash, the newest sealed segment's hash and the count. Entries are bundles, annotations and audit records. |
| **Lookup index (derived)** | `local/history.sqlite` (Python's standard library): id → entry, kind and date, provenance edges, annotations joined to their subjects, optionally full-text search. Rebuilt or caught up from the chain whenever missing or stale. Never authority. |
| **Integrity** | **Incremental verification** walks only from the current root back to the last verified root. **Full verification** walks everything reachable. Either runs outside the control lock against a pinned root, and its result is made durable by a short AEW transition and an immutable audit record (operator decision). |

**Cost of archiving one unit.** It writes:
- its bundle (about 20 KB today);
- the tail (at most 256 entries, about 50 KB);
- a sealed segment once every 256 units;
- the hot root.

That is O(1) in history (ADR-0011 invariant 10, H2).

**What the hashes guarantee.** They make cold history tamper-evident, not authenticated. Anyone who can rewrite both cold content and the hot root can forge both. Under ADR-0005's same-user model, containment (F2) is what bounds that, as ADR-0011 now states. Keyed signatures would be a separate ADR-0005 decision.

## 2. What grows with history today

**Control state.** About 20.7 KB per DONE Ticket (ADR-0011): invocations (59%), unit records (29%) and credentials (7%).

**Code that reads the whole state.** 37 places in 13 files iterate every unit, invocation or token. Most become cheap automatically once terminal detail leaves the hot state. The rest need a bounded or explicit path:

| Kind | Where | After archival |
|---|---|---|
| **Active only** | active invocations, busy workspaces and observations (`lead_ops`, `nonmutating_ops`, `workspace_ops`, `harness_ops`, `lead_broker`), readiness (`dependencies.recompute_readiness`), parent derivation (`hierarchy.derive_parent`, `recompute_parents`) | Iterate hot state only. Cheaper with no change, apart from the two facts below. |
| **Facts about archived units that active state needs** | an open parent must know it has archived children (PLANNING vs ACCEPTANCE_PENDING); a dependency edge to a DONE upstream needs its state and integration commit | **Per-parent counter** `archived_children`. **Edge fact** `satisfied: {state, integration_commit, bundle_sha256}`, copied into each open dependant's edge when the upstream is archived (dependants are hot, so finding them is bounded). Both are "bounded current hot facts" in ADR-0011's sense, and rebuildable from the manifest. |
| **Listings that include history** | `status` (DONE and CANCELLED lists), `work tree`, `CURRENT.md`'s work graph (rendered **after every commit**, with a DONE group listing every completed Ticket), hierarchy roots | **Decided:** a bounded summary (counts), the last N completions from a hot ring, and an obvious full-history path (`aew history list …`, named in the output). Full listings scale with what is asked (H2). |
| **Lookup by id that may hit history** | `invoke show` of a completed invocation, `harness status` or `wait` on an old run (`_find_run`), parent closeout and parent review or verification packs (their children's records), pack regeneration | Read the bundle by id through the lookup index (units also by path). The cost is proportional to the request. |
| **Whole-history checks** | `resume`'s evidence sweep (`resume_ops`, the contradiction list); oracle rules that span history, such as rule 17 (no evidence after its credential's revocation) | They move to the audit (H4, invariant 13). The commit path checks only hot state, the transition's delta and bounded summaries. |

**Other growth to note.**
- **The transition log.** `state/log/<rev>.yaml` is one git-tracked file per revision, forever: about 20 per Ticket, so about 60,000 at 3,000 Tickets. **Decided: not required by ADR-0011.** The spike measures its git and filesystem cost (§8 item 5), and sharding happens only if that violates the property or the target envelope.
- **Revoked Lead tokens** accumulate per acquisition or takeover (`lead_ops` iterates `tokens`). They grow with sessions, not Tickets. Archive them into a per-generation bundle.
- **Role cards.** Each invocation embeds its card's full content (about 0.7 KB). Storing cards once by SHA-256 shrinks open units too. This is the ADR's "deduplicate pinned role cards" alternative, worth doing alongside.

## 3. The design in detail

### 3.1 Bundles and annotations

- **Granularity: a terminal work unit**, meaning a Ticket, Story or Epic in DONE or CANCELLED. It includes everything only that unit references:
  - its control record;
  - its ended invocations: pack-source lists, pinned card SHA, snapshot and workspace details;
  - their revoked credential entries: ids and revocation times, which rule 17's audit needs.
- **Location: `work/<id>/archive.yaml`**, beside `ticket.md`, `plan-v*.md` and `completion.md`. One directory holds everything about a unit, which is the inspectability and repair argument. The bundle is immutable (`Session.write(..., immutable=True)` exists) and its SHA-256 is in its manifest entry.
- **Annotations.** A later fact about an archived unit (superseded by a revision, moved, promoted, linked as lineage) is a new small immutable record plus a manifest entry `{kind: annotation, subject, rel, sha256, path}`. The bundle is never rewritten. Staleness is derived from current relationships, never written back (ADR-0011).
- **Trust labels.** Each entry carries the record's source classification (operator-authored, model-authored, external) so that loading it as reference context can keep and label it (invariant 14). Loading is recorded in the loading invocation's context provenance.
- **Invocations of open units stay hot** until their unit is archived. That is bounded per unit (A1); a long-lived Ticket with many attempts is the case to measure.

### 3.2 The authoritative manifest

```text
history/tail.yaml          mutable, at most 256 entries, holds prev: <sha of newest sealed segment>
history/seg-000001.yaml    sealed: 256 entries + prev: <sha of seg-000000 or null>; never rewritten
...
control.yaml: cold: {count, tail_sha256, sealed_head: {seq, sha256},
                     verified: {through_count, root, at, mode}, full: {root, at}}
```

- **Entry:** `{id, kind, terminal_state, at, path, sha256, parent, source, links: [depends_on, decisions, integration_commit, completion record, evidence ids]}`. The links are what history traversal follows (invariant 12).
- **Append:** rewrite the tail through redo staging (replaceable, before-hash checked) and update the hot root, in the same commit. When the tail reaches 256 entries, the same commit writes it out as `seg-N` (create-if-absent) and starts an empty tail pointing at it. That is O(1) in history.
- **Verify one record:**
  - `bundle sha == entry.sha256`;
  - `entry ∈ segment`;
  - the segment's file hash equals the hash recorded for it (the next segment's `prev`, or the hot root).

  Membership of an older segment in the chain is established when the lookup index is built or caught up (§3.3).
- **Rejected shape:** a single index file listing every entry or every segment. Rewriting or hashing it is linear in history.
- **Upgrade if needed:** a Merkle mountain range instead of a plain chain gives O(log n) inclusion proofs for any record without the lookup index (ADR-0011 allows O(log n)). The hot root then holds about log₂(n) peak hashes. It is not needed unless membership must be proven without a trusted derived index.

### 3.3 The derived lookup index

- `local/history.sqlite`, with tables `entries(id, kind, state, at, parent, source, segment, path, sha256)`, `links(src, rel, dst)`, `annotations(subject, rel, entry)` and optionally `fts(text)`.
- **Freshness:** it stores the root it was built against. If the current root extends that root, it catches up by walking back from the tail until the stored head appears, a cost proportional to new appends. Otherwise it is rebuilt.
- **Loss of `local/`** costs a rebuild (one chain walk), never knowledge.
- It serves the minimum history surface:
  - show by id;
  - list by kind and date range;
  - follow links and annotations;
  - load one chosen record, labelled, into reference context.

### 3.4 Parent summaries

With terminal descendants archived, `derive_parent` over the hot state sees only open descendants, which is exactly what the attention list and the blocked flag need. The one historical fact a parent needs is whether it has archived children: a counter, `archived_children`, updated in the archiving commit and rebuildable from the manifest (entries carry `parent`). Closed parents are archived themselves, so `recompute_parents` stops visiting them (invariant 9). Closeout and parent review read their own children's bundles, a cost proportional to the request.

### 3.5 The audit lifecycle

- **Incremental:** verify each entry appended since `verified.through_count`, walking back from the current root to the verified one, and the link between them. The cost is proportional to the new appends.
- **Full:** walk everything reachable from the current root. This is the periodic corruption check.
- **Outside the lock.** Verification reads a lot and must not hold the control lock, which would block every command. It pins the root it starts from, verifies without the lock, and then commits a short transition: `history.audited {mode, root, through_count, result, findings}`, plus an immutable audit record that is itself appended to the manifest. If history advanced meanwhile, the record still says exactly which root was verified, and the backlog is the difference.
- **Durability (decided):** an audit counts once it is recorded through a normal AEW transition. A local or CI run is advisory until its result is ingested that way. Which authority may record it (the Lead, or an operator command) is an implementation detail to settle in the plan.
- **`status`** reports the current root, the verified root, unverified additions (count and age) and the age of the last full verification, against policy thresholds rather than as a permanent alarm (invariant 11).
- **Required:** at least an incremental audit through the current root at Epic closeout and before an AEW-managed backup or export is complete. CI runs incremental verification routinely, plus a periodic full pass on the fixture corpus.

## 4. Alternatives compared

| | **P: files + bounded manifest + derived SQLite** (recommended) | **B: SQLite as the authority** | **C: hot YAML + cold SQLite authority** | **E: git objects** (decided: rejected) |
|---|---|---|---|---|
| ADR-0001 single commit point | Kept: redo staging carries bundles, tail, segments and the root | **Replaced**: needs an ADR-0001 amendment; files outside the DB (work records, evidence) need their own atomicity | **Two commit points** to keep atomic | Two commit points (control.yaml and a ref) |
| Content addressing, tamper evidence | Native (SHA-256 per bundle and segment, chained) | Must be added on top | Must be added | Native (git is a Merkle DAG) |
| Archival write cost | O(1) (bounded tail, sealing) | O(log n) (B-tree insert) | O(log n) | O(log n) (subtree sharing) |
| Historical discovery and traversal | Through the derived index; rebuildable | Native SQL | Native SQL | Needs its own index |
| Immutability plus annotations | Natural (create-if-absent files, appended entries) | Needs append-only discipline in the schema | Same | Natural |
| Inspectability and repair | YAML beside the unit's records; diffable in git | Opaque binary; needs the sqlite CLI | Mixed | Only through `git show`; invisible in the working tree |
| **Git-tracked `.aew/`** (everything but `local/` and `state/txn/` is tracked today) | Small text files, good deltas | **A binary DB rewritten on every commit and committed into the project's history**: bloat, no merge or diff | The cold DB has the same problem | Custom refs may not be pushed; `gc` risk if the ref is lost |
| Offline, backup, portability | Plain files that travel with the repo | One file | Mixed | Only if the ref is pushed |
| Windows | Many small files: Defender and NTFS per-file costs (§8) | File locking and WAL behaviour on Windows and network shares | Both | git's own |

**Why B and C lose.** AEW's durable state is committed to the project's git repository. A database file as authority turns every AEW commit into a new binary blob in the project's history, which outweighs SQLite's query convenience; P keeps that convenience in the derived index. B also needs the ADR-0001 amendment, which ADR-0011 reserves for a material, measured advantage. The spike still times B's appends, so the comparison rests on numbers.

**E** is dropped as an implementation candidate (operator decision) and recorded as a rejected alternative.

## 5. Crash and atomicity

- Everything an archival writes goes through the existing redo record (`state/txn/<rev>.yaml`): the bundle, the tail, any new segment and the hot root. Roll-forward already supports replaceable files with a before-hash, which the tail needs.
- **New fault points:** after the bundle is applied but before the tail; after the tail but before sealing; mid-seal; between an audit's verification and its recording.
- **Rollback.** A crash or refused commit can leave a staged bundle that nothing references. ADR-0011 now calls these benign unreachable objects: the audit reports them, and maintenance may collect them. The crash matrix and seeded walks include this case.
- **The redo record for one archival** is bounded: about 20 KB of bundle plus about 50 KB of tail.

## 6. Migration

- ADR-0011 invariant 7 (final text): **one Lead transaction on a quiescent project**. No live harness runs are allowed, so a slow migration cannot produce false `lost` heartbeats.
- At 3,000 terminal units, that one transaction stages about 60 MB of bundles in its redo record, then applies them: slow once, but bounded and crash-safe. The spike should time it (§8 item 7). If it proves impractical, ADR-0011's "or on first write" leaves room for batched compaction transitions under the same quiescence rule.
- **Mixed state** (terminal units both hot and archived) must stay readable regardless, because a crash can stop migration and because old projects may migrate late.
- **Test:** a project built by the M3 code (the perf tool's template), migrated with crashes injected at each new fault point, then `resume`, `status`, an incremental audit and the oracle.

## 7. Scale beyond the fixture

- **Long-lived Epics.** With parent counters (§3.4) and the hierarchy-history series, an open Epic's active cost does not depend on its completed descendants. Parent *closeout* and parent *review packs* still read every child. That is proportional to the request, but at thousands of children it becomes a context-size problem for pack design (bounded summaries of children), not a storage one.
- **30,000 cold records.** About 120 sealed segments. Only the full audit and a full index rebuild grow with history, and both are explicit.
- **A large active frontier.** ADR-0011 now measures up to 1,000 open or planned units. At about 1–1.3 KB each, that is about 1.0–1.3 MB of hot state, which libyaml parses at about 4–5 MB/s. So expect roughly 0.2–0.3 s per command, and per supervisor re-parse, from the frontier alone. That is within the absolute bounds but close to H3's 0.25 s heartbeat budget, which is stated for 20 open units. It is the first place a "deferred residency tier" for not-yet-active work could become necessary. The spike's active series will show where the knee is.

## 8. The spike that decides it (next step)

`storage_spike.py` is standalone, with no product code. Run it on the Windows reference machine and on Rocky 8.10:

1. **Cold-write series** (ADR-0011) at 1,000, 3,000, 10,000 and 30,000 records: archival latency (bundle, tail rewrite, a seal every 256, atomic writes with fsync). Target: a flat slope.
2. **B for comparison:** the same appends as SQLite WAL transactions, latency only.
3. **Exact lookup** by id through the derived index; **index rebuild** and **incremental catch-up** times.
4. **Incremental and full verification** times.
5. **Filesystem and git cost:** `git status` and `git add -A` with 3,000 to 30,000 bundles plus segments; the transition log unsharded against sharded (decided: shard only if it violates the property or the envelope). On Windows, include Defender as it is configured on the machine.
6. **Hierarchy series:** prototype `derive_parent` with the counter on one open Epic with 250, 1,000 and 3,000 archived children (in memory).
7. **Migration:** one transaction archiving 3,000 units from an M3-built project (redo size, wall time).

Pass condition for P: items 1 and 6 are flat within H2; 3 and 4 take seconds at 30,000; 5 shows no regression beyond the envelope; 7 completes in minutes.

Smoke run, under load and not representative: about 20 ms per archival for P and about 4 ms for B, at 300 and 600 records. Both are small next to command latency.

## 9. Operator decisions (2026-10-01)

| Question | Decision | Effect here |
|---|---|---|
| `CURRENT.md` and `status` with history | **Yes:** a bounded summary, recent items, and an obvious full-history path | §2 listings row |
| Audit result | **Durable** through a normal AEW transition and an immutable audit record; local or CI results are advisory until ingested | §3.5 |
| Archival timing | **Automatic** at the terminal transition | §1, §3.1 |
| Sharding `state/log/` | **Not required** by ADR-0011; measure, and implement only if it violates the property or the target envelope | §2, §8 item 5 |
| Git object store | **Dropped** as an implementation candidate; kept as a rejected alternative | §4 |

**Still open (implementation plan, not designer questions):**
- which authority records an audit;
- the annotation record's exact shape;
- the history command names.

## Sources in the repo

- ADR-0001; ADR-0011 (final pre-implementation text, 2026-10-01).
- `src/aew/engine/store.py` (`Session.write`, redo staging); `hierarchy.py` (`derive_parent`, `recompute_parents`); `dependencies.py` (`recompute_readiness`); `knowledge/render.py` (`work_graph_lines`); `status_ops.py`; `resume_ops.py`; `engine/api.py` (`.aew/.gitignore`).
- A real project's `.aew/` (the UAT `spt` project); `m3-performance.md` §5 and §7.
