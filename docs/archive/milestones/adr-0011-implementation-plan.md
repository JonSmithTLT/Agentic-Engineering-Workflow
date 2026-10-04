# ADR-0011 implementation plan (with E5)

- **Status:** approved by the operator (2026-10-02). **Complete** (2026-10-03): every phase is merged, P3 last (PR #24, `42239e1`); the register closed F1, E5 and the before-M4 gate.
- **Scope:** the gate before M4. That covers [ADR-0011](../../implementation/adr/0011-hot-cold-control-state.md) (register F1) and E5, the Engine collaborator refactor (register E5).
- **Inputs:**
  - ADR-0011 (final pre-implementation text, 2026-10-01);
  - the storage investigation, [`adr-0011-storage-investigation-2026-10-01.md`](../../research/adr-0011-storage-investigation-2026-10-01.md) (design "P", spike results, the operator's decisions in its §9);
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
  rel: moved_to            # superseded_by | moved_to | promoted_to | lineage | audit_finding | cited_evidence
  object: S-0007           # the other end of the relation, or null
  at: <ISO-8601>
  actor: {generation: 3}
  decision: D-0123         # the Decision record that caused it, or null
  source: engine           # trust classification (ADR-0011 invariant 14)
  note: <text>
  ```
- Each annotation gets a manifest entry of kind `annotation`. The bundle it is about is never rewritten.
- **Producers in this work:** `audit_finding` (the audit), `moved_to` (R3) and `cited_evidence` (`aew migrate` on v2: it pins the cited checks of a bundle archived before bundles recorded them, in a `cited_evidence` list; §7.4). F4 (Ticket revisions) adds `superseded_by` and `lineage` later.

### The history commands

| Command | Authority | Purpose (ADR-0011 invariant 12) |
|---|---|---|
| `aew history show <id>` | read | An exact record by stable id, with its annotations and trust label |
| `aew history list --kind … [--since] [--until] [--limit]` | read | Records by kind and bounded date range |
| `aew history links <id> [--depth N]` | read | Follow the provenance and reference links |
| `aew history load <id> --into <WORK-ID> --reason …` | Lead | Attach a historical record as reference context. Later packs for that unit carry it as a labelled `history:<id>@<sha>` source, never as current evidence (invariant 14) |
| `aew history audit [--full] [--token …]` | read, or Lead to record | Incremental or full verification (R2) |
| `aew history reindex` | read | Rebuild the derived index |
| `aew migrate` | Lead, quiescent | The one-time v1 → v2 migration. On v2, it records the cited checks of bundles archived before bundles recorded them (§7.4), and is otherwise a no-op |

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
- **Independent review fixes** (2026-10-02, in PR #17).
  - **The tail proves where it starts.** It must start at the newest sealed segment's end, or at the genesis for the first tail. Before this, a tail that dropped its committed prefix but still ended at the root was accepted, and the next append committed over it. Once the count is fixed, ending at the root pins the starting hash too.
  - **A sealed lookup proves the segment it reads against the root.**
    - The segment must start at its position, and its entries must continue the chain.
    - Its file hash must be linked to the root through every later sealed segment: each one's `prev` holds the hash of the one before, and the newest one's hash is the root's `sealed_head`.
    - The later segments are only hashed, and only their headers are parsed, at a fraction of a millisecond each. Any change to any of those files, including a coordinated rewrite of several, is therefore a contradiction when it is accessed. The operator chose this over checking only the next segment (2026-10-02). It is cheaper, because it parses one whole segment instead of two, and it is complete.
  - **Verification reports what it reads, never raises.** Bytes that are not UTF-8, and files that cannot be read, are reported as problems.
  - **The index tells busy from damaged.** A lock held past the timeout is a `LockTimeout`, and the file is kept. Metadata that is missing or malformed means a rebuild.
  - **`coldwrite` times only the three measured archivals.** Before this, the timed index catch-up also took in the setup records. The series was rerun (README §4).

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

**P2c as built** (2026-10-02). Everything above, with these implementation choices:
- **Where it lives.** `engine/history_ops.py` holds a new collaborator, `HistoryCommands`. `Hierarchy` uses it for the Epic closeout check, and `Resume` for audit status. The composition test lists it as `_history`. Archive's own `History` store attribute is renamed `cold`, so that the port generator does not mistake it for the collaborator.
- **`history show <id>`.**
  - It reads the exact record a manifest entry pins, verified against its hash when read (`Archive.record`).
  - It also finds a record held inside an archived unit's bundle, through the link the unit recorded: an invocation, a credential, or an evidence record (the evidence is verified against the hash its unit recorded at ingest). Lead records hold credentials as well.
  - Every answer carries the trust label: its source, and that it is reference only. Evidence written by a model is labelled `model`; a check result, `engine`.
  - Credential verifiers are redacted.
  - An archived unit also shows its current parent (moves applied) and its annotations.
- **`history list`:** by kind (`unit`, `annotation`, `audit`, `lead`) and a UTC date range, newest first. The default limit is 50 and the maximum 1,000, and the answer says whether it was truncated.
- **`history links <id> --depth 1..3`:** the recorded links, both directions, at most 500 edges. Each node is marked `history`, `hot` or `other` (a commit, a completion path).
- **`history load <id> --into <unit>`** (Lead) records a reference on the hot unit (`history_refs`: id, kind, entry, hash, source, reason, generation).
  - Each dispatch pins the unit's references onto its invocation. So a later load changes later packs only, and a regenerated pack still matches the one recorded.
  - The pack gets a "Historical reference context" section, which says the records are not current evidence and carry no instruction authority. An archived unit appears as a summary of its outcome and provenance, not its whole bundle. Each reference is a pack source `history:<id>` with its trust label and `reference: true` (invariant 14).
- **`history audit [--full]`:**
  - Without `--expect-rev`, it is advisory: nothing is recorded, and problems exit with `INTEGRITY_ERROR`. CI runs it this way.
  - With `--expect-rev`, it is a Lead mutation that records the audit.
  - **R2 as built:**
    1. Under the lock (a session that is not committed), it copies the root and the tail's bytes, and checks the credential and the revision.
    2. It verifies outside the lock, against those bytes (`tail_raw` through `History.verify`).
    3. It re-takes the lock through `lead_txn` at the then-current revision. If the root moved, it verifies the new entries incrementally and tries again, at most five times.
    4. The audit record (`history/audits/<n>.yaml`, kind `audit`, id `AU-<n>`) is appended through the new `ctx.entries`. The finalizer appends those first, in the transaction's single append, so the verified root is known before the commit, and the audit's link to the audited root is checked locally.
  - A passing audit sets `cold.verified` (`{count, h, at, audit}`) to the root this commit makes current. A full one also sets `cold.last_full`.
  - A failing audit records `fail` and never advances the verified root. Each damaged unit record gets an `audit_finding` annotation.
  - **Fault point:** `history.audit_before_record`. A pause point, `history.audit_after_verify`, lets a test land a commit inside the R2 window.
- **Audit status.** `status` reports `history_audit`: the current root, the verified root, the unverified entries with the age of the oldest, the last full verification, the policy and what is over it.
  - The thresholds come from the gates policy's optional `history_audit` block. The built-in defaults are 1,000 entries, 168 hours and 30 days.
  - A history that was never fully verified is due once its first entry is older than the full-verification threshold, not as soon as it starts.
  - Anything over policy becomes one next action, never an alarm (invariant 11).
- **Epic closeout** is refused with `GATE_UNSATISFIED` while entries are unverified, and the Epic's next action names the audit.
  - The test helper `close_parent` records an audit before it closes an Epic. That is the one edit to shared test code: invariant 8's deliberately changed path. AT-8/AT-13 and the archival tests close Epics through it.
- **The walks.** Both seeded walks now inject `history.after_bundle` and `history.after_tail`, which fire on the commits that archive (§8). P2b had left them out.
- **Independent review fixes** (2026-10-02, in PR #20).
  - **An audit covers every record reachable from the root**, not only each entry's own record. An archived unit's bundle pins records by path and hash: its record, its plans, its ingested evidence and its completion record (`archive_ops.pinned_records`). Context packs are not: they live in the disposable `local/` and are checked by regeneration. Incremental and full verification check each against its pin (`History.verify(..., pinned=)`), outside the lock, and attribute damage to the unit, which gets the `audit_finding`. Before this, a full audit passed with an archived unit's evidence changed, and so released an Epic closeout.
  - **A pack shows a loaded record redacted**, as `history show` does: a loaded Lead record's credential verifiers no longer reach the pack.
  - **`history load` takes an archived evidence record by its id**, as `history show` finds it: pinned by the hash its unit recorded at ingest (`history_refs` kind `evidence`, `held_by` its unit), labelled with who wrote it (`model`, or `engine` for a check result), and shown in the pack as the exact record. An archived invocation or credential is refused with what to load instead. The pack's fence is longer than any run of backticks in the record.
  - **Audit status never reads the history.** `cold.first_at` and `cold.unverified_since` are kept at each append, in the same transaction (`archive_ops.advance_cold`), so `status` and `resume` take the dates from the hot state. A v2 state from before the fix, which lacks them, reads them from the index until an audit makes them unnecessary: its next audit for `unverified_since`, its first full one for `first_at`.
  - **`history reindex`** turns an index another process holds open into `LOCK_TIMEOUT`, not a traceback.
  - **No storage paths on the surface:** `history show` drops the entries' `path` and the `completion` relation (its values are paths), `history links` skips it, and `history reindex` no longer prints the index's location.

**P2d: migration and the oracle.**
- **`aew migrate`** (R8): it refuses while any run is live, and it is idempotent. It is crash-tested at every new fault point on a project built by the M3 code (the perf tool's template).
- **The oracle** (`tests/helpers/invariants.py`) learns the cold root additively. Rules 4, 5, 17 and 18 read bundles through the history API, in tests only.
- **Two test edits**, the only ones to existing test files; invariant 8 allows them because they inspect the raw layout:
  - the AT-15 `tokens()` helper reads hot, then cold;
  - the footprint test splits hot and cold.

  *Amended by the operator, 2026-10-02 (see "P2d as built"):* the edits P2d actually needs are two others, and this constraint now names those instead.
- **A timing-free H1 regression** joins the scale tests.
- **The fingerprint** gets `:(exclude).aew` (`snapshot/fingerprint.py:73`), as its own measured commit (investigation §8.1).
- **Optional:** dedupe role-card content into `cards/<sha256>.yaml`, if A1 needs it.

**P2d as built** (2026-10-02). Everything above, with these implementation choices:
- **`aew migrate --expect-rev N`** (Lead; `engine/migrate_ops.py`, a new collaborator, `Migration`).
  - It runs the archival finalizer once over the whole v1 state, in one transaction: every DONE or CANCELLED unit leaves the hot state, deepest first, with its invocations and credentials, and the summaries, `archived_refs`, frontiers and `recent` follow exactly as if each unit had been archived when it finished. Ended Lead credentials go too.
  - **R8:** a new `TxnContext.prewrite` makes the finalizer write each bundle before the commit (`history.store.prewrite`, fault point `history.after_prewrite`) and reference it by hash (`Session.prewritten`). The redo record carries the sealed segments, the tail and the root; `last_transition` records the count and hash of the pre-written list. Bundles are deterministic, so a retry after a crash before the commit rewrites the same bytes.
  - It refuses while any invocation's latest run may be live (`runlog.may_be_live`, the launch check), and on a v2 project it does nothing (`migrated: false`).
- **The refusal of v1 mutations.** `lead_txn` refuses a v1 project's Lead mutations with the new error `MIGRATION_REQUIRED`, whose `next_action` names `aew migrate`; `resume` and `status` name it too. What the Lead needs to reach the migration still works: the seat (handoff offer and cancel, release; acquire, accept and takeover are outside `lead_txn`), `invoke cancel` (a live run blocks the migration) and `manifest adopt` (the migration checks the pin). Reads are unchanged.
- **Existing parent evidence (R3).** Each open parent gets `legacy_digest: {v1, v2_at_migration}`. `Hierarchy.same_children` accepts a binding to the v1 digest while the v2 digest is still the one recorded at migration, in all three places the plan names: the gate context's `is_current`, the ingest staleness check, and `_classification_unmet` (where comparing the digests directly would have read the unchanged child set as changed, and released a LOCAL_IMPLEMENTATION_DEFECT closeout without its remediation child).
- **The oracle.** P2b already rebuilt the full state from hot state and archive (through `History.walk`, with every record verified), so rules 4, 5, 17 and 18 see archived work; P2d adds nothing to it.
- **The perf tool.** Its template builds the M3 (v1) layout in process, with a Kernel flag only it sets (`legacy_v1_writes`). `migrate()` migrates a built project, timed. `run` and `sweep` measure each project after migrating it (each sweep point is now a project of its own, since a v2 project cannot be grown by cloning hot DONE Tickets), and report the migration time. `project_footprint` reports the cold store on disk, and counts the hot aggregates of archived work as history.
- **Tests.**
  - New: `tests/integration/test_migration.py`: the refusal; what migration archives and keeps, against the full state, with a full audit of the migrated history (every pinned record included); a crash at each of the 11 fault points of a migration (the seal on a project of 256 finished units), each leaving v1 or the whole v2 with the same history root every time; live runs; parent evidence through the migration, including a classified failure.
  - The H1 regression is `test_after_migration_the_hot_state_holds_history_only_as_aggregates` in the scale tests: at 250 and 1,000 completed (four times the history), the hot state grows at most 1.25x and history is at most 20% of it. H1's own points, 250 and 3,000, are P3's measurement; a 3,000-unit migration takes minutes.
- **The fingerprint** skips `.aew/` in its `git add` (`:(exclude).aew`) instead of hashing it and then removing it from the index: the tree is identical, and `.aew/` holding thousands of uncommitted records (the authoritative checkout once history is archived) is no longer read. Measured on Windows with 3,000 uncommitted 20 KB records under `.aew/` and 200 tracked files: 1.74 s to 0.066 s per fingerprint (median of 10), the same tree. `working_tree_id` still reads `.aew/`, which its callers compare.
- **Measured once, for P3:** migrating the template grown to 20 open and 3,000 completed Tickets took 102 s on the Windows development machine (not idle; P3 measures it properly). Most of it is likely serializing the 3,000 bundles (about 60 MB of YAML); P3's profile will show.
- **Independent review fixes** (2026-10-02, in PR #21).
  - **A retry after an interrupted migration survives a change of seat.** The seat may change hands on v1 between a crash after the pre-writes and the retry; the Lead record then has other content at the same path, and the retry used to be refused for good. A v1 project has no history root, so no history record on disk is reachable: the migration removes any it finds, under the lock, before it writes (`Migration.discard_unreachable`, reported as `discarded`). On v2 it does nothing, so a referenced record is never touched.
  - **The recent ring is the most recently finished**, not the last in archive order: each commit's newly archived units join `recent` by completion time (stable for equal times). A migration archives deepest first and by id, which had kept the highest ids instead.
- **Operator decisions on P2d** (2026-10-02):
  - **Migration time:** continue to P3. P3 profiles the migration (§7.2); batching is not adopted now.
  - **The existing-test edits:** approved, and the constraint above is amended. The plan named two edits (AT-15's `tokens()` helper, the footprint test) as the only ones to existing test files. P2d instead edits two others, each because the v1 refusal changes what they test: P2b's v1 test (P2b's interim behaviour, "a v1 project keeps working", was always meant to end in P2d) and the scale regression (its mutations now run on migrated projects). The AT-15 edit was not needed, and the footprint test stays as it was; its hot and cold split is a new test beside it.
  - **The H1 regression** at 250 and 1,000 completed is approved as the CI regression. H1's acceptance gate stays at 250 and 3,000 completed, measured in P3 (§7.2).
  - Edits to existing tests: the scale regression measures migrated projects (two builds, since a migrated project cannot grow by cloning), with the resume scan allowance now per open unit (H4); P2b's v1 test now checks the refusal and the migration. The plan's AT-15 `tokens()` edit was not needed: AT-15 reads only the credentials of invocations still running, which stay hot.

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
  - all four series and the migration timing, against the baseline, with a profile of the migration (operator, 2026-10-02: batching only if the profile shows one transaction is impractical);
  - H1–H4 and A1, each marked pass or fail in a results section of this document. H1 is judged at 250 and 3,000 completed; the CI regression's smaller points do not replace it.
- **Windows reference (operator):** the full sweep (ADR-0011 coverage).
- **Rocky 8.10 on aew-q7 (operator):** the hierarchy-history series, the H3 changed-hot-state re-parse, archival-write scaling and the absolute heartbeat bound. P2a adds the exact script.
- **Review.** A review brief states what changed in ADR-0001's model, followed by the independent review. The register then moves F1 and E5 to §9 *Closed*.

### 7.3 Carried into M4's ambiguity report

These are the two findings from the F2 probes.
1. When the engine inspects a run's workspace, it must add that run's private git object store as an alternate. F2 decides the store's lifetime.
2. The E13 conformance scenario must translate namespace-local PIDs (`NSpid`) before it can gate F2.

From P3 (A1, §7.4):

3. `resume` grows with open work: about 3 ms per open unit on Windows (3.6 s at 1,000 open), 1.2 to 1.4 ms on Linux, in its compute phase. It is linear and inside the 8 s bound, but M4's concurrency raises the open frontier.

### 7.4 P3 results (2026-10-03)

The data and tables are in [`eval/adr-0011/perf/README.md`](../../../eval/adr-0011/perf/README.md) §5–§7. `tools/perf/adr0011_gate.py` judges a flat and a hierarchy sweep against the criteria below and prints the table; on all three platforms every row is pass or report (on Windows with the paired H2 run, `--ab`). Code measured: `16c6757`.

**Who ran what.** With the operator's go-ahead (2026-10-02), Claude ran all three:
- **WSL2 Ubuntu 22.04** (supplement): flat, hierarchy and cold-write series.
- **Rocky Linux 8.10 in `aew-q7`**: `tools/perf/rocky8-gate.sh` and the full flat sweep. It is Rocky's userland on WSL2's 6.18 kernel, not Rocky's 4.18; that is enough for this gate, which measures Python, YAML and file I/O, but not for F2's containment.
- **Windows reference**: the full sweep, flat, hierarchy and cold-write. The operator did light design work during it; nothing else ran.

**Verdicts.**

| Criterion | Windows (reference) | Rocky 8.10 | WSL2 Ubuntu |
|---|---|---|---|
| **H1** hot state at 3,000 vs 250 completed (≤ 1.25x) | 1.05x flat, 1.08x hierarchy | 1.05x flat, 1.08x hierarchy | 1.05x, 1.08x |
| **H1** history's share of hot state at 20 open, 3,000 completed (≤ 20%) | 7.6%; 12.6% hierarchy | 7.7%; 12.8% hierarchy | 7.7%; 12.8% |
| **H2** largest change of any command, 250 to 3,000 completed (≤ +0.25 s) | +0.024 s paired (flat); +0.036 s hierarchy | +0.027 s | +0.076 s |
| **H2** cold-write maintenance sublinear | flat, 1.5k to 30.7k records | flat, 1.5k to 30.7k records | flat |
| **H3** re-parse of a changed hot state, 20 open, 3,000 completed (≤ 0.25 s) | 13.3 ms | 7.0 ms | 6.4 ms |
| **H4** `resume`: no history-linear sweep (same reads and scans at 250 and 3,000; meets H2) | pass | pass | pass |
| **Absolute bounds** at 3,000 (reads ≤ 2 s, commits ≤ 4 s, `resume` ≤ 8 s, heartbeat ≤ 2.5 s) | pass; slowest `resume`, 0.93 s (0.57 s paired) | pass, every command ≤ 0.28 s | pass |
| **A1** (reported): hot bytes and `resume` per open unit, 20 to 1,000 open | 1.03 KB; 3.1 ms, linear, no knee | 1.03 KB; 1.35 ms, linear, no knee | 1.03 KB; 1.24 ms, linear |

**Windows H2 is judged paired.** The sweep measured the 3,000 point once, in a slow moment: `aew --version`, which never reads the project, took 1.7x longer than at 250, and every phase of every command was about 1.6x slower. `status` (+0.255 s) and `resume` (+0.37 s) then exceeded +0.25 s with identical read and scan counters. `control_plane.py ab` measured both points in turns, six rounds: the largest difference is +0.024 s (perf README §7). The sweep's one-sample cap at 3,000, from M3, is removed.

**H1 is judged at 250 and 3,000 completed**, as the operator decided; the CI regression's 250 and 1,000 do not replace it. The historical-access minimum (show, list, links, load) and the full and incremental audits are P2c's, covered by `tests/integration/test_history_surface.py`.

**A1, read.** With history gone from the hot state, what remains grows with open work: about 1 KB and 0.3 to 0.5 ms per open unit for most commands, as in M3, and for `resume` 1.2 to 1.4 ms on Linux and 3.1 ms on Windows (0.56 s at 20 open, 3.59 s at 1,000; it was about 4.4 ms on Windows before ADR-0011). It is linear to 1,000 open, with no knee, and inside the 8 s bound; M4 takes it up (§7.3). The re-parse grows with it (0.29 to 0.41 s at 1,000 open on Linux), inside the 2.5 s heartbeat bound; H3's 0.25 s is defined at 20 open. Nothing here needs the optional role-card dedupe (§6, P2d).

**Migration, profiled** (operator: profile it, batch only if one transaction is impractical). At 20 open and 3,000 completed on Windows, under cProfile (100 s; 102 s unprofiled at P2d):
- parsing the 60 MB v1 `control.yaml` once, with its schema validation: about 30%;
- hashing records on disk: each completion record when its unit is archived, and every pre-written bundle again at the commit (R8): about 27%, mostly opening 12,000 files just written (on Windows, about 2 ms per open);
- serializing 3,000 bundles and the state: about 16%;
- one avoidable cost: the finalizer found each unit's credentials by scanning every credential, N units x 15,000 credentials, about 9%. **Fixed** (`b57b681`): one map per commit.

Unprofiled after the fix: 87 s on Windows (102 s before), 83 to 86 s on Linux. The rest is linear work the migration must do once (read everything, write and verify everything), so **one transaction stays**: a project migrates once, the time is linear (about 28 ms per finished Ticket), and splitting it would trade R8's one commit point for resumable batches with no measured need.

**Found and fixed by the gate** (`16c6757`). The derived history index was built by whichever command first looked up finished work after a migration. At 3,000 completed that was `harness status`, measured once at 0.88 s against 0.25 s at 250: an H2 failure, though its steady state is constant (it rehydrates the bounded `recent` ring). `aew migrate` now builds the index after its commit, outside the lock, and reports it (`index`). The results above are from after the fix.

**Not run, and why.** Nightly-strength crash and walk runs are CI's nightly job (§8). Live models are not part of this gate.

**Independent review fixes** (2026-10-03, in PR #24). The review of the whole (frozen at `c6caa4c`) requested changes for two findings in the merged P2 code:

- **P3-1: the index locates entries; it never vouches for them.**
  - **The defect.** `local/history.sqlite` is derived and covered by no hash. A row whose entry named another record (another path, hash or content) was believed. `history show` then returned that record as engine history, `history load` pinned it into a pack, and a new dependency committed facts from it while naming the real bundle's hash.
  - **What every query returns now.** Each query returns the history's own entries: each row is checked against the entry the root pins at its position (`History.authenticate`), and the authentic entry must satisfy the query itself (its id, kind, state, parent, subject, links). A mismatch rebuilds the index and asks again; a second one is an `IntegrityError`.
  - **Missing rows** are caught at sync: the rows must be exactly the root's positions.
  - **Links** are read from the authenticated entries, not from link rows.
  - **Facts** take the bundle hash from the authenticated entry they were read with.
  - **What remains, and how it is covered.** A row altered so that no query matches it omits a record rather than inventing one. The explicit full audit compares every row, column and link with the history, rebuilds the index if any differ, and reports `index: consistent | rebuilt`.
  - **Cost.** Each history file is read and proven once per query, and once per command through two per-process caches:
    - parses keyed by the file's hash;
    - sealed segments proven to lead to the root's sealed head.

    A command that reads several archived units syncs the index once, while its root and file are unchanged. `harness status` at 3,000 completed, which rehydrates the 20-unit recent ring: 0.50 s, against 0.59 s before.
- **P3-2: the full audit covers the evidence closure.**
  - **What is pinned now.** Archival pins the check results an ingested verification cites but the unit did not ingest (`cited_evidence` in the bundle, with hashes taken then, after the report is checked against its ingest hash). Their ids join the entry's `evidence` links, so `history show` finds them by id (`history load` uses the same lookup). A cited check that is missing, or a report that changed since ingest, refuses the archival (and the migration).
  - **What the audit follows.** A verification follows what each pinned record pins in turn (`verify(..., nested=evidence_pins)`: a check's log), each file once per entry. Recorded audits and the Epic closeout gate use the same verification.
- **Found by the new audit:** the perf tool's cloner rewrote each cloned check's log (its ids change) without rehashing the log pin inside the check record. Cloned evidence records are now written after their logs, with their pins rehashed. Measurements are unaffected: the cloner's files were never audited before.
- **Tests:** `tests/integration/test_history_integrity.py`, six tests on a real finished mutating Ticket (the perf template), migrated:
  - a forged index entry (show, then facts);
  - a lost row and an invented link;
  - a row that hides its entry, until the full audit;
  - a cited check found by id;
  - a changed cited check, and a changed or deleted log, ingested or cited, under advisory and recorded full audits;
  - a verification changed after ingest refusing migration.

  All six fail on `c6caa4c` and pass now.

**Re-review fixes** (2026-10-03, in PR #24). The re-review (frozen at `1911894`) found P3-1 resolved and P3-2 partly resolved, with two remaining findings:

- **P3-R1: archival pinned a cited check as it was found.**
  - **The defect.** A cited check changed before archival was hashed as it stood. The audit then verified that hash and reported success.
  - **The fix.** Archival pins nothing the engine did not record as it is (`cited_checks`). Each cited check must:
    - be schema-valid and still under its seal;
    - be a `check_result` of this unit under its own id;
    - have every file it pins (its log) still match.

    Anything else refuses the archival, so the migration refuses and control stays v1.
  - **The audit.** It now checks the seal of every evidence record it reaches, as well as its hash.
- **P3-R2: units archived before the fix kept the gap.**
  - **The defect.** A bundle archived before bundles recorded `cited_evidence` keeps its cited checks outside the audit. The full audit still passed.
  - **The policy.** An explicit upgrade, append-only:
    - New bundles are `aew/archive/v2`, which always records `cited_evidence` (possibly empty). A bundle still at `aew/archive/v1` predates it.
    - `aew migrate` on a v2 project gives each such unit a `cited_evidence` annotation that pins its cited checks, validated as archival validates them now (the report against its ingest hash from the authenticated bundle). The bundle is never rewritten. A cited check that is not what the engine recorded refuses the whole upgrade. With nothing to upgrade, `migrate` stays a no-op.
    - Until a unit's annotation exists, a full audit reports it as a problem that names `aew migrate`, so the audit cannot pass. It is not damage: the unit gets no `audit_finding`, and a recorded audit leaves the verified root where it was.
    - `history show` finds a check pinned this way by id, held by its unit.
- **Tests:** three more in `tests/integration/test_history_integrity.py`:
  - a cited check changed after its seal, replaced by another sealed record, or whose log changed, each refusing migration;
  - an older v2 archive (built by migrating with the previous bundle format) failing the full audit until `aew migrate` records its closure, with no finding, then passing, then covering the cited check and its log;
  - the upgrade refusing a cited check already changed.

**Merged** by the operator with these fixes (PR #24, `42239e1`, 2026-10-03). The register moved F1, E5 and the before-M4 gate to §9 *Closed*.

## 8. Verification for every PR

- **Lanes.** The fast, serial, integration, regression and adversarial lanes run locally. CI's `assurance` check must be green on Linux and Windows.
- **P1:**
  - the public `Engine` name set is unchanged;
  - `git diff --stat tests/` shows only added files;
  - the no-`Engine`-reference test passes.
- **P2:**
  - the crash matrix and both seeded walks include the new fault points;
  - one local run at nightly strength (`AEW_CRASH_ITERATIONS=2000`, extended `AEW_WALK_*`).
