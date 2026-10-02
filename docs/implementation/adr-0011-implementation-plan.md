# ADR-0011 implementation plan (with E5)

- **Status:** approved by the operator (2026-10-02). Nothing is implemented yet.
- **Scope:** the gate before M4. That covers [ADR-0011](adr/0011-hot-cold-control-state.md) (register F1) and E5, the Engine collaborator refactor (register E5).
- **Inputs:**
  - ADR-0011 (final pre-implementation text, 2026-10-01);
  - the storage investigation, [`adr-0011-storage-investigation-2026-10-01.md`](../design/adr-0011-storage-investigation-2026-10-01.md) (design "P", spike results, the operator's decisions in its §9);
  - ADR-0001 (one commit point, redo staging, advisory lock).
- **Nature:** implementation choices inside ADR-0011's "Not decided here". No designer question reopens, and ADR-0001 is not amended.

## 1. Sequence (operator, 2026-10-02)

| Phase | Work | Output |
|---|---|---|
| **P0** | Confirm the storage investigation is good enough to implement | This document (§2–§4); the Linux supplementary baseline (§7.1) |
| **P1** | E5: replace the Engine's mixin composition with explicit collaborators | One PR, behaviour-preserving (§5) |
| **P2** | ADR-0011 implementation and migration | PRs P2a–P2d (§6) |
| **P3** | The ADR-0011 acceptance and performance gate | Sweeps, review brief, independent review (§7) |
| **P4** | M4 begins | Planned separately |

E5 goes first. Archival then attaches to an explicit transaction seam, not to a `super()` chain that has to be rewritten later.

## 2. P0 verdict

**Design P is good enough to implement, with the refinements R1–R8 below.**

The core of the recommendation stands:
- immutable bundles per terminal unit;
- an append-only, hash-chained manifest of bounded segments;
- a derived, rebuildable SQLite index;
- automatic archival at the terminal transition;
- incremental and full audits off the `resume` path.

The spike's measurements support it. Archival is flat from 1,000 to 30,000 records, and the archived counter makes parent recomputation constant.

Reviewing the design against the code found eight places where P, as written, would either:
- break an ADR-0011 invariant;
- change behaviour that M1–M3 tests rely on; or
- leave a choice to whoever implements it, when evidence binds to that choice.

Each refinement stays within "Not decided here": the manifest form, parent summaries, the schema version and command names.

### R1. The root is an entry-level hash chain, not the hash of the mutable tail file

**Problem.** P's hot root pins `tail_sha256` (investigation §3.2), but every archival or seal rewrites the tail. The bytes a verified root describes then no longer exist, so "linkage to the last verified root" cannot be proven. An audit running outside the lock would also race those rewrites.

**Fix.**
- **Each manifest entry** carries `seq` and `h = sha256(h_prev ‖ canonical_json(entry))`. Canonical JSON means sorted keys, no whitespace and UTF-8. It is never the YAML bytes.
- **The hot root** is `{count, head_h, sealed_head: {seq, sha256}}`.
- **Any earlier root** `{n, h_n}` stays checkable however entries are later laid out across the tail and sealed segments. The incremental audit confirms the stored `h_n` equals the verified root's hash, folds entries n+1…m, and compares with the current root.
- **Segment `prev` file hashes** stay, as a repair aid. They are no longer the root.

### R2. Recording an audit must not leave a one-entry backlog (operator, 2026-10-02)

The audit record is itself a manifest entry. Recording it naively would advance the current root past the verified root, so the system would always be one entry behind. The sequence is:

1. Under a brief lock, copy the current root R and the tail bytes. Release the lock.
2. Verify through R outside the lock. Sealed segments and bundles are immutable, so this cannot race a commit.
3. Re-take the lock and require `current == R`. If the root has moved, discard this recording attempt and continue incrementally against the new root.
4. Build and stage the audit record A and its manifest entry, and compute the resulting root R′.
5. Verify A and its link to R locally.
6. Commit with `current = verified = R′`.

The audit record states that its substantive target was R. It never claims to have audited itself.

### R3. Parent summaries keep `children_digest` and derivation history-independent

**Problem.**
- `children_digest` (`hierarchy_ops.py:39-68`) is on active paths: `status`, `resume` and next actions (through `_parent_actions` and `_parent_gate_context`), and parent dispatch and ingest.
- It hashes every child and every mutating child's completion file, because `completion_sha256` is never set at publish (`integration_ops.py:321`).
- With archived children, that would read thousands of bundles.
- The v1 digest is a hash over the sorted list of all children, so it cannot be maintained incrementally.

**Hot summary on each parent:** `archived_children: {done, cancelled, done_tickets_subtree, acc}`.
- **`acc`** is pinned exactly, because evidence binds to it:
  - `leaf = SHA256("aew-child-v2\0" ‖ canonical_json({id, state, completion_sha256}))`;
  - `acc = Σ int.from_bytes(leaf, "big") mod 2^256`, stored as 64 lowercase hex characters;
  - moving an archived child out subtracts its leaf, mod 2^256.

  Golden-vector unit tests pin this construction.
- **`done_tickets_subtree`** is transitive: it counts DONE Tickets anywhere below. It is updated on every ancestor in O(depth), and it keeps `work_depend`'s busy check correct (`hierarchy_ops.py:463-468`). Without it, archived DONE Tickets vanish from `descendants`.

**Digest v2:** `sha256("aew-children-v2\0" ‖ done ‖ "\0" ‖ cancelled ‖ "\0" ‖ acc ‖ "\0" ‖ v1-style lines over the hot children)`. The counts are decimal ASCII.

**Existing evidence stays verifiable.**
- Migration stores `legacy_digest: {v1, v2_at_migration}` on each open parent.
- A `+children:<v1>` binding counts as current while the current v2 still equals `v2_at_migration`. This applies in `is_current` (`hierarchy_ops.py:63`), the ingest staleness check (`:149`) and `_classification_unmet` (`:209`).
- The alias is one bounded hot record per open parent.

**Derivation and moves.**
- Publish sets `completion_sha256`, so bundles carry it.
- With no hot children and `done + cancelled > 0`, a parent derives `ACCEPTANCE_PENDING`, not `PLANNING`. `children_complete` needs `done > 0`.
- Moving an archived child updates both ancestor chains and writes a `moved_to` annotation (§3). The index's "children of X" view applies move annotations.
- A property test runs at every commit of the walks: derivation from the full state equals derivation from hot state plus summaries.

### R4. Upstream facts as a hot `archived_refs` map

**Problem.** Investigation §2 copies an edge fact into each open dependant when the upstream is archived. Edges to archived units are also created later:
- `work create --depends-on <DONE id>`;
- `work depend --add`;
- edges inherited from an ancestor that is created or moved later.

Today `_parse_edges` → `self.unit()` (`work_ops.py:257`) would raise `NotFound`, and `_edge_blocker` (`dependencies.py:45-47`) would block forever on `unknown_work_unit`. Worse, `consumed_inputs` (`nonmutating_ops.py:187-189`) skips an upstream it cannot find, so a dependant would dispatch without pinning or freshness-checking its ADR-0008 inputs. That fails open.

**Fix.**
- A hot `archived_refs: {id: {kind, mutating, state, nm_record, completion_sha256, integration_frontier, bundle_sha256}}`.
- Hot edges reference-count it.
- It is filled on demand from the cold index when an edge is parsed, at a cost proportional to the request.
- Every upstream read goes through one `upstream(state, id)` helper.
- `depends_on`, and the edge-set identity bound into invocations, stay unchanged.

### R5. A per-parent integration frontier instead of one "latest" commit

**Problem.** "The latest integration commit is in base, so all are" holds only while AEW is the sole writer of the authoritative ref.
- `_finish_publish` accepts `already_published` (`integration_ops.py:265`).
- An operator can rewrite the branch.
- "Latest" by time is not "latest" by the commit graph.
- `dispatch_binding_problem` evaluates edges at older dispatch commits (`dependencies.py:155`), so the fact must hold commits, not a boolean.

**Fix.**
- Each parent keeps `integration_frontier: {commit: via_ticket}`, an antichain under git ancestry, maintained transitively.
- On each mutating DONE below a parent:
  - drop the members that are ancestors of the new commit;
  - add the new commit unless it is an ancestor of a member.

  That is O(|frontier|) ancestry checks, normally one.
- "Every member is in base" is equivalent to today's per-descendant check (`dependencies.py:51-57`). `via` keeps the blocker text.
- Moving an archived Ticket out keeps the frontier. That over-approximates, so it fails closed.

### R6. Archival runs in a transaction finalizer, as a serialization projection

**Where archival runs.**
- **Not `_after_state_change`.** Parent DONE and CANCELLED are written by `recompute_parents` (`hierarchy.py:93-98`), which bypasses `_set_state`.
- **A `TxnFinalizer` inside `lead_txn`**, just before the commit (`base.py:195`). In order, it:
  1. recomputes the parents;
  2. finds the newly terminal units by diffing against the session's base state, and archives them deepest first;
  3. updates the summaries (R3–R5);
  4. recomputes once more.

**What stays visible to callers.**
- Some code reads `ctx.state` after the commit (`hierarchy_ops.py:126`, `integration_ops.py:333-336`).
- **The finalizer produces the state passed to serialization.** It does not destructively replace the caller-visible `ctx.state`.
- `Session.commit()` serializes `Session.state` itself today (`store.py:223-280`). P2b therefore adds the minimal Session/commit seam this needs: working state → `TxnFinalizer` → hot projection → `Session.commit(projected_state)`.
- The store's cached parse becomes the projected state, which is what the next session loads.

### R7. Current facts about terminal units stay hot, and lookups fall back to cold

- **Retained workspaces.** A DONE Ticket whose workspace was retained (`_settle_ticket_workspace`, `integration_ops.py:339-362`; reported at `status_ops.py:37-40`) stays a contradiction until resolved.
  - A bounded hot `retained_workspaces` list keeps it.
  - An entry is pruned at the next Lead commit after its directory is gone.
- **Observation worktrees** are pruned at archival (`nonmutating_ops.py:94-98`). Otherwise they leak on disk.
- **Credential errors** keep their codes. A revoked token that has been archived must still produce `StaleAuthority`, not `PermissionDenied("unknown")` (`authority.py:86,144-147`). On a miss, consult the cold index, and still deny.
- **Lookups by id fall back to cold:**
  - `work show`, `work list` and `status <id>` (`work_ops.py:442,452`; `status_ops.py:53-56`);
  - `invoke show`;
  - `_find_run`, `harness status` and `harness wait` (`harness_ops.py:301-336`);
  - `gate show` and evidence by an archived id;
  - pack regeneration.
- **Checks that move to the audit:** the record-hash and plan-hash checks of terminal units leave `contradictions` (invariant 13).
- **CURRENT.md** is rendered in `_post_commit`, which also runs on every recovery (`store.py:384`). It shows DONE and CANCELLED as counts plus the recent ring, and names `aew history list`. The same applies to `status`, per the operator's decision.
- **Assertion:** a hot unit never has an archived ancestor.

### R8. Migration stays one transaction, with a bounded redo record

**Problem.** Staging about 60 MB of bundles in one redo record (investigation §6) has two costs beyond wall time:
- it puts about 3,000 write entries into hot `last_transition.txn.writes` (`store.py:247-251`), which breaks H1 and H3 until the next commit;
- every read's `_load_txn` (`store.py:338`) hashes those 60 MB until then.

**Fix.**
- **Bundles are deterministic.** They contain no migration-time fields.
- **They are pre-written before the commit.** An unreferenced bundle is benign (ADR-0011). A retry produces identical bytes, which an immutable write allows (`store.py:237`).
- **The redo record** carries only the tail, the new segments and the root.
- **`last_transition`** records a bounded summary.
- **The store gains** a small extension: pre-verified immutable objects, listed by path and hash, not by content. It gets its own fault point.
- **Timing:** measured in P3. If one transaction still proves impractical, batched quiescent compaction goes to the designer. It is not assumed here.

## 3. The open implementation choices

Investigation §9 left three choices open, and ADR-0011 left two more ("whether the control schema version changes", "CLI names").

### Which authority records an audit: the Lead credential

- `aew history audit [--full] --token …` runs the R2 sequence and commits `history.audited` plus an immutable audit record.
- Without a token, the audit is **advisory**: it verifies and prints, and records nothing. CI runs it this way.
- **No result files are ingested.** Only a verification the engine itself ran can advance the verified root, so a forged CI or local result cannot.
- **Epic closeout** refuses while `verified != current`, and its next action names the audit (ADR-0011: "Epic closeout … require[s] at least an incremental audit through the current root").

### The annotation record

- **Path:** `work/<subject>/annotations/<seq:04d>.yaml`. For Lead-generation bundles: `history/lead/annotations/<seq:04d>.yaml`.
- **Schema:** `aew/annotation/v1`:

  ```yaml
  schema: aew/annotation/v1
  id: AN-0001
  subject: {id: T-0042, entry_seq: 812, bundle_sha256: <hex>}
  rel: moved_to            # superseded_by | moved_to | promoted_to | lineage | audit_finding
  object: S-0007           # the other end of the relation, or null
  at: <ISO-8601>
  actor: {generation: 3}
  decision: D-0123         # the Decision record that caused it, or null
  source: engine           # trust classification (ADR-0011 invariant 14)
  note: <text>
  ```
- Each annotation gets a manifest entry of kind `annotation`. The bundle it is about is never rewritten.
- **Producers in this work:** `audit_finding` (the audit) and `moved_to` (R3). F4 (Ticket revisions) adds `superseded_by` and `lineage` later.

### The history commands

| Command | Authority | Purpose (ADR-0011 invariant 12) |
|---|---|---|
| `aew history show <id>` | read | An exact record by stable id, with its annotations and trust label |
| `aew history list --kind … [--since] [--until] [--limit]` | read | Records by kind and bounded date range |
| `aew history links <id> [--depth N]` | read | Follow the provenance and reference links |
| `aew history load <id> --into <WORK-ID> --reason …` | Lead | Attach a historical record as reference context. Later packs for that unit carry it as a labelled `history:<id>@<sha>` source, never as current evidence (invariant 14) |
| `aew history audit [--full] [--token …]` | read, or Lead to record | Incremental or full verification (R2) |
| `aew history reindex` | read | Rebuild the derived index |
| `aew migrate` | Lead, quiescent | The one-time v1 → v2 migration |

### Schema version

- **`aew/control/v2`.** It adds top-level keys: `cold`, `recent`, `archived_refs` and `retained_workspaces`. The schema rejects unknown keys today.
- **Reading a v1 project** works as before.
- **Lead mutations on v1** are refused, and the next action names `aew migrate`. Migration refuses while any harness run is live (invariant 7).

## 4. Audit status

- `status` reports four things:
  - the current root;
  - the verified root;
  - unverified additions (count and age);
  - the age of the last full verification.
- These are judged against thresholds in an optional `history_audit` block of the gates policy. The block has built-in defaults, so existing projects still validate.
- It is shown as backlog against policy, not as a permanent alarm (invariant 11).

## 5. P1: E5

**Scope.** `Engine.__mro__` has 13 classes behind the facade:
- 12 `*Ops` mixins: HarnessOps, ResumeOps, HierarchyOps, NonMutatingOps, IntegrationOps, ContextOps, EvidenceOps, WorkspaceOps, RoleOps, WorkOps, LeadOps, StatusOps;
- plus `EngineBase`.

E5 replaces all of them with a `Kernel` (today's `EngineBase` contents: roots, store, manifest, policy, `lead_txn`, `new_decision`, `authoritative_commit`) and explicit collaborators.

**Acceptance criteria (operator, 2026-10-02):**
- **`Engine` is the composition root and the public facade.** Its public method set is identical. It also keeps `store`, `gate_context` and `_require_gates`, which tests use.
- **No back-references.** A collaborator depends only on `Kernel` and on narrow collaborator protocols, declared explicitly in its constructor. A collaborator never depends on `Engine`: none holds `self.engine` or a generic back-reference. Otherwise 13 implicit mixins would become 12 objects calling arbitrary methods through a shared facade, which is the same architecture in different syntax.
- **No `super()`-based behavioural chaining remains.**
- **No dynamic `getattr` hook or guard dispatch** remains on the extracted seams.
- **Hook order is explicit and tested.**
  - `before_state_change`: integration.
  - `after_state_change`: workspaces, then integration.

  This copies today's super-first order (`work_ops.py:100-103` → `workspace_ops.py:96` → `integration_ops.py:43,50`).
- **Guard registration is explicit and tested.** Guards are keyed by `(name, kind)`, where kind is one of `mutating`, `nm` or `parent`. This replaces `getattr(self, f"_guard_{name}")` and the non-mutating overrides (`nonmutating_ops.py:590-642`). An unknown guard still raises `GateUnsatisfied`.
- **Per-kind strategies** (`MutatingTicket`, `NonMutatingTicket`, `Parent`) serve `gate_context`, `invoke_evidence_unit`, `ingest_evidence_unit_report` and the next actions. They are dispatched through a `KindRegistry` that mirrors today's resolution order: hierarchy, then non-mutating, then evidence.
- **A `TxnFinalizer` seam** exists inside `lead_txn`, where ADR-0011's `History` collaborator attaches (R6). It has no behaviour in P1.

**Tests.**
- **Existing behavioural tests stay unchanged.** Nobody edits an M1–M3 expected result to make E5 pass.
- **New structural and conformance tests may be added.** They are written first, as characterisation tests:
  - hook order;
  - guard resolution per (guard, kind);
  - the gate-context path per kind.
- **A dependency test** inspects the collaborators' constructors and module imports, and fails on any reference to `Engine`.

**Commit sequence** (the suite stays green at each step):
1. Characterisation tests.
2. Introduce `Kernel`.
3. Add the registries alongside the MRO, with an agreement assertion; then switch the guards, the gate context and `_set_state` to them.
4. Extract the leaf collaborators: roles, Lead, status.
5. Extract the kind strategies: non-mutating, then parent, then mutating.
6. Extract workspaces, integration, context packs, harness and resume.
7. Collapse `Engine` to the facade; delete the mixins and the agreement assertions.

## 6. P2: ADR-0011

Each PR keeps the M1–M3 tests passing.

**P2a: the cold-store core**, in `src/aew/history/` (`store.py`, `manifest.py`, `index.py`).
- **Writes.** Bundles go through `Session.write(..., immutable=True)`. The tail is a replaceable write with its before-hash. A segment is sealed at 256 entries.
- **The R1 chain**, plus the R8 pre-verified objects in the store.
- **The derived index** is `local/history.sqlite`, which catches up or rebuilds itself.
- **Fault points:** `history.after_bundle`, `history.after_tail`, `history.mid_seal`, `history.audit_before_record` and `migrate.after_prewrite`.
- **Tests:** unit tests and crash-matrix entries, including the benign unreachable bundle left by a rollback.
- **`tools/perf/control_plane.py`:** a hierarchy-history series, the active series to 1,000 open units, and a `coldwrite` subcommand (1k, 3k, 10k and 30k records). Their baselines are run against the baseline commit.

**P2a as built** (2026-10-02). Everything above, with these implementation choices:
- **Where the root lives.** The library is pure over a root, `{count, head_h, sealed_head}`, that the caller keeps. P2b keeps it in `control.yaml` under the `cold` key that schema v2 adds. Until then, the tests and the perf tool keep it in a file written in the same transaction, which the redo record makes exactly as atomic.
- **Fault points.**
  - Each history write is tagged with its fault point through a new per-write tag on `Session.write`: `history.after_bundle`, `history.mid_seal` and `history.after_tail`.
  - The pre-write helper hits `history.after_prewrite`. Migration (P2d) uses that helper, so it is the point `migrate.after_prewrite` named.
  - `history.audit_before_record` arrives in P2c, with the code that records an audit.
- **R8 in the store.** `Session.prewritten(path, sha256)`:
  - the commit verifies each declared file;
  - the redo record lists them by path and hash;
  - `last_transition.txn` carries only `{count, sha256}` of that list.
- **Validation.**
  - An entry is validated against its schema when it is created.
  - On read, a file is checked only for its envelope. The hash chain binds the stored entries to the validated ones, because an altered entry breaks the chain.
- **New measurements.**
  - `sweep --hierarchy` puts every Ticket below one open Story and Epic.
  - A `derive` profile phase isolates parent recomputation.
  - `micro.control_reparse_s` is the H3 re-parse.
  - `coldwrite` holds the tail at a fixed occupancy, so that sizes compare.
  - `tools/perf/rocky8-gate.sh` is the exact Rocky 8 script for §7.2.
  - The active series to 1,000 open units was already a `sweep` point.
- **Measured** (`eval/adr-0011/perf/README.md` §3–§4):
  - the hierarchy-history baseline at `0eb8ecf`;
  - the first cold-write series. Appends, incremental verification, index catch-up and lookup are flat from 1.5k to 30.7k records.

**P2b: archival through the `TxnFinalizer`** (R3–R7).
- **Bundle contents:** the unit, its ended invocations and their revoked tokens. Lead tokens are archived per generation at takeover, handoff accept and release.
  - **Carry-forward from the E5 review (2026-10-02).** Lead acquire, handoff accept and takeover commit through their own sessions in `lead_ops.py`, not through `lead_txn`, so the `TxnFinalizer` does not run for them. The same holds for harness stop and kill requests. P2b either archives a Lead generation explicitly in those commits or routes them through the finalizers.
- **Hot structures:** `archived_refs`, the frontier, the counters and the recent ring.
- **Schema v2.**
- **Readers:** `hierarchy.py` and `dependencies.py` read through the summaries and `upstream()`. `contradictions`, the `resume` evidence sweep and CURRENT.md become hot-only.
  - **Found by the P2a hierarchy baseline (2026-10-02).** Parent recomputation is quadratic in a parent's descendants: 0.011 s at 250, 0.29 s at 1,000 and 2.2 s at 3,000 completed, per commit (`eval/adr-0011/perf/README.md` §3). `descendants()` calls `children()` once per descendant, and `children()` scans every unit. P2b builds one children map per recomputation as well as archiving.
- **The cold fallbacks** (R7).

**P2b as built** (2026-10-02). Everything above, with these implementation choices:
- **Schema v2.** `aew init` creates v2. Its top-level keys are:
  - `cold`: `root`, plus `archived` counts by state;
  - `recent`: the last 20 archived units;
  - `archived_refs`;
  - `retained_workspaces`;
  - `retired_observations` (added by the review fixes below).

  A v1 project keeps working unchanged, without archival. The refusal of v1 mutations arrives in P2d together with `aew migrate`, so that no project is refused before the command that clears the refusal exists.
- **Archival (R6).** The `Archive` collaborator is the `TxnFinalizer`. At the commit that finishes a unit, it archives every DONE or CANCELLED unit, deepest first, with its invocations and credentials.
  - The finalizer hands the store a projection (`ctx.commit_state`), so the operation's own code keeps its working state.
  - Retired observation worktrees of archived invocations are removed after the commit (`ctx.after_commit`).
  - The finalizer does not recompute parents again. The operations' own `before_commit` already did, and oracle rule 22 checks that derivation from hot state and summaries equals derivation from the full state.
- **R3.**
  - The summary is `{done, cancelled, done_tickets_subtree, cancelled_tickets_subtree, acc}`. The fourth counter serves `rollup`.
  - The v2 children digest is computed for every v2 project.
  - `children_map` is built once per recomputation. It removes the quadratic recomputation the P2a baseline found.
  - Moving an archived unit writes a `moved_to` annotation and moves its summary entries. A hot parent that moves carries its archived subtree counts and frontier with it.
- **R4.** `archived_refs` is recomputed from the hot edges at each commit, with each entry counting the edges that name it. An edge to work archived earlier fills it from the index when the edge is parsed.
- **R5.** An `integration_frontier` is kept on every ancestor of an archived integrated Ticket.
- **R7.**
  - **Lookups.** `work show`, `status <id>`, `invoke show`, `context pack`, `gate show`, `harness status <inv>` and `harness wait` read archived work by rehydrating that one unit into a copy of the state. `work list --state DONE|CANCELLED` is an explicit history query.
  - **Acting on finished work.** It is still refused as `ILLEGAL_TRANSITION`.
  - **Credentials.** An archived credential is `STALE_AUTHORITY` in the engine, the Lead broker and a run's supervisor.
  - **Views.** The unfiltered `work tree`, `work list`, `resume` and `harness status` add the `recent` items, which are bounded. Views show counts and name `aew history list`.
- **Lead credentials (the E5 carry-forward).** When the seat changes, ended Lead and handoff-offer credentials are archived as `history/lead/<n>.yaml`, with a manifest entry of kind `lead`. The finalizer does it for `lead_txn` commits; acquire, handoff accept and takeover do it explicitly.
- **Manifest entries** carry `unit_kind` and `title`, so history listings need no bundle reads.
- **Test-side changes** (invariant 8: raw layout only).
  - The oracle rebuilds the full state from hot state and archive, runs every rule on it, and adds rules 19–23.
  - The walks' `unit()` helpers and one intent-ingress assertion read archived units through the engine.
  - The oracle-vacuity test corrupts the full state.
  - The perf template builds the M3 (v1) layout. P2d's `migrate` turns it into v2 for the P3 series.
- **Independent review fixes** (2026-10-02, in PR #18).
  - **A read of archived work restores its archived ancestors.** Rehydration brings back the unit's archived Story and Epic as well, bounded by depth, never the whole history. Before this, `context pack` and `gate show` for a Ticket whose Story had closed failed on the missing ancestor.
  - **Removing an archived invocation's observation worktree is a persisted obligation.**
    - `retired_observations` (v2) lists each such worktree until its directory is gone.
    - Every Lead commit retries the removal, and so does the non-mutating operations' pruning. `status` reports any that are left as contradictions.
    - Before this, a crash between the commit and the removal, or a failed removal, lost the worktree for good.
  - **Views follow moves of archived work.** A move updates the unit's `recent` entry, which is hot state, and `work list --state DONE|CANCELLED` applies `moved_to` annotations from the index (`HistoryIndex.moves`). Bundles and their manifest entries are never rewritten.
  - **An index that is ahead stops at the synced root in SQL.** Every query, `links` and `paths` included, binds `seq <= upto` before ordering and limits. Before this, a limited listing could return nothing, and links and paths leaked later entries.

**P2c: the history surface and the R2 audit.**
- The commands in §3, and audit status in `status` (§4).
- `history load` references in packs.
- The Epic-closeout audit check.

**P2d: migration and the oracle.**
- **`aew migrate`** (R8): it refuses while any run is live, and it is idempotent. It is crash-tested at every new fault point on a project built by the M3 code (the perf tool's template).
- **The oracle** (`tests/helpers/invariants.py`) learns the cold root additively. Rules 4, 5, 17 and 18 read bundles through the history API, in tests only.
- **Two test edits**, the only ones to existing test files; invariant 8 allows them because they inspect the raw layout:
  - the AT-15 `tokens()` helper reads hot, then cold;
  - the footprint test splits hot and cold.
- **A timing-free H1 regression** joins the scale tests.
- **The fingerprint** gets `:(exclude).aew` (`snapshot/fingerprint.py:73`), as its own measured commit (investigation §8.1).
- **Optional:** dedupe role-card content into `cards/<sha256>.yaml`, if A1 needs it.

## 7. P3: the acceptance gate

### 7.1 Baselines

- **Linux supplement** (this plan's P0, `eval/adr-0011/perf/`). It ran in a cloud container on `main` at `0eb8ecf` and covers the M3 points plus the active series to 1,000 open units. It is not the reference machine.
- **Windows reference** (operator). On the idle reference machine, at the same commit:

  ```text
  python tools\perf\control_plane.py sweep --points 20:250,20:1000,20:3000,200:250,500:250,1000:250 --reps 3 --work <empty dir> --json eval\adr-0011\perf\baseline-windows.json
  ```

  **Done** (2026-10-02): `eval/adr-0011/perf/baseline-windows.json`, at `aa533c5`. That commit has the same engine as `0eb8ecf`; only the perf tool differs. The README beside it records the machine and the results.

### 7.2 The gate

- **Linux (here):**
  - all four series and the migration timing, against the baseline;
  - H1–H4 and A1, each marked pass or fail in a results section of this document.
- **Windows reference (operator):** the full sweep (ADR-0011 coverage).
- **Rocky 8.10 on aew-q7 (operator):** the hierarchy-history series, the H3 changed-hot-state re-parse, archival-write scaling and the absolute heartbeat bound. P2a adds the exact script.
- **Review.** A review brief states what changed in ADR-0001's model, followed by the independent review. The register then moves F1 and E5 to §9 *Closed*.

### 7.3 Carried into M4's ambiguity report

These are the two findings from the F2 probes.
1. When the engine inspects a run's workspace, it must add that run's private git object store as an alternate. F2 decides the store's lifetime.
2. The E13 conformance scenario must translate namespace-local PIDs (`NSpid`) before it can gate F2.

## 8. Verification for every PR

- **Lanes.** The fast, serial, integration, regression and adversarial lanes run locally. CI's `assurance` check must be green on Linux and Windows.
- **P1:**
  - the public `Engine` name set is unchanged;
  - `git diff --stat tests/` shows only added files;
  - the no-`Engine`-reference test passes.
- **P2:**
  - the crash matrix and both seeded walks include the new fault points;
  - one local run at nightly strength (`AEW_CRASH_ITERATIONS=2000`, extended `AEW_WALK_*`).
