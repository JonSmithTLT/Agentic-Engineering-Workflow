# ADR-0012 — The transaction outbox: the transition log, typed, complete and consumed

- **Status:** **Design frozen — proposed for operator adoption**, 2026-10-04. Not governing until accepted/merged. This version incorporates architecture-review, developer, and design-authority corrections for overflow completeness, sealing/read races, hash coverage, command naming, and consumer semantics.
- **Spec basis:**
  - WC §5, the crash-safe control-authority rule (v0.7 line 246, inside §5.1, as ADR-0001 cites it), and WC §8.2, checkpoint and crash semantics: a transition "either leaves the previous valid state intact or publishes the complete new valid state".
  - WC §15.6: "CLI and MCP must never implement separate state authorities"; a consumer of events is a reader, never a second authority.
  - KC §12.3: consequential transitions "should remain reconstructible"; KC §5.3: rebuildable runtime data lives apart from durable records (`.aew/.gitignore` cites it for `local/`).
  - ADR-0001: one commit point, redo staging, and the sentence this ADR amends: "The transition log (`state/log/<rev>.yaml`) and views such as `CURRENT.md` and `HANDOFF.md` are rebuilt from committed state. They are never authoritative."
  - ADR-0011: history independence (H1, H2, H3), "a derived index never becomes authority", invariant 13 (commit-time work is history-independent).
  - Register: E1 (wait-any), O4 (the wait part), F20 (dashboard refresh), F11 (M5 scheduler), F15 §16 (safety reactions "on the event"); the M6 knowledge drafts: capture §7 to §8 and §23, shared semantics §4.2 (`knowledge_event_seq`).
  - This review: `REVIEW.md` G11, K2, F-A; `m4-ambiguity-report.md` §2.9 (wait-any "woken by the supervisor through a per-project wake file or pipe").
- **Evidence** (reproduced in this directory, `repro/`, against the frozen tree at `dcd43f1`; nothing was run in the live checkout):
  - `repro/log_growth_probe.py` (`.out.txt`): sixteen commits of every kind, including the five that bypass the transaction finalizers, each left exactly one `state/log/<rev>.yaml`; reads (`status`, `resume`, `doctor`) added none; nothing pruned them. Records are 164 to 632 bytes. `.aew/.gitignore` tracks `state/log/` and ignores `local/` and `state/txn/`.
  - `repro/log_recovery_probe.py` (`.out.txt`): a process killed at `txn.after_replace` and at `txn.after_apply` left `control.yaml` at N+1 with no `log/N+1`; the next read repaired it, and the repaired record equals `last_transition` byte for byte.
  - `adr-0011-storage-investigation-2026-10-01.md` §2 and §8.1: one log file per revision, about 20 per Ticket, about 60,000 at 3,000 Tickets; `git status` 0.33 s unsharded against 0.10 s sharded; the first `git add -A` 440 s. "Sharding not required by ADR-0011."
  - Code at `dcd43f1`: `harness wait` polls a run record every 0.2 s (`engine/harness_ops.py:382`); the supervisor stats `control.yaml` every tick and re-parses on change (`harness/supervisor.py:98`); the Lead broker reads and parses the state every 1 s (`harness/lead_broker.py:112`); the dashboard design polls every 2 to 10 s with ETags (`aew-readonly-dashboard-design-v0.2.md` §21).
  - Commit sites: `Kernel.lead_txn` runs the finalizers; five sites commit through `Session.commit` directly and run none: `lead.acquire`, `lead.handoff.accept`, `lead.takeover` (`engine/lead_ops.py`), `harness.{stop,send,interrupt}` (`engine/harness_ops.py:412`), and `migrate` (which runs them by hand). An outbox attached as a finalizer would miss four of them.
- **Nature:** an implementation choice that amends ADR-0001's description of the transition log. No transition, gate, authority rule or piece of provenance changes. What changes is a guarantee (the log is complete and consumable), a record shape (typed events), a bound (sealing), a signal (wake), and a reader protocol.

## Context

Four designs want the same thing and each proposes its own mechanism:

| Who | What it does today | What it wants |
|---|---|---|
| `aew harness wait` (E1, O4) | Polls one run's `run.json` every 0.2 s; waits are 12% of Lead steps (audit L1) | Wait on any of several runs, woken, not polled |
| The dashboard (F20) | HTTP polls every 2 to 10 s; each poll must not take the control lock or parse the state (W01) | Know that something changed, and what kind, so it refetches only the affected projections |
| Knowledge capture (M6 drafts, K2) | Does not exist | "Capture begins from committed AEW events"; at-least-once with idempotent admission; job identity bound to the exact committed event; replay from pinned sources after a crash |
| The scheduler (F11, M5) and F15 §16 | Do not exist | "Safety-relevant authority reactions happen on the event, not when the Lead happens to issue the next command" |

Each consumer, left alone, either polls hot state (an ADR-0011 history-independence violation in waiting, as K2 notes) or couples itself into the commit path. G11 named the remedy a transaction outbox. This ADR places it.

**What already exists.** Every commit writes `last_transition` into `control.yaml` inside the commit point (`store.py:290`), and `_post_commit` copies it to `state/log/<rev>.yaml`, create-if-absent, after the replace (`store.py:412`). Recovery calls `_post_commit` too (`store.py:366`), so a crash between the replace and the copy is repaired by the next lock holder: the probes show this. The record carries `revision, at, actor, op, summary, reason, refs, txn{path, sha256, writes[path, before, after]}`. The `op` vocabulary is already typed: about forty-five names (`work.create`, `work.transition`, `review.ingest`, `integrate.publish`, `lead.handoff.offer`, `history.audit`, …) plus three outcome overrides (`integrate.stale`, `integrate.superseded`, `integrate.withdrawn`).

So the outbox exists in all but four respects: the record says what operation ran but not what changed (which unit moved to which state, which credential was revoked); no reader protocol or position exists; nothing wakes a waiter; and the directory is unbounded (60,000 files at 3,000 Tickets). ADR-0001 also describes the log as "never authoritative" and says nothing about completeness, so no consumer may rely on it today.

## Decision

**The outbox is the transition log.** No second store, no second record of a commit. The log becomes a derived, complete, bounded, consumable copy of what the commit point already records.

### D1. Completeness is a stated guarantee

For every revision `r <= revision`, there is exactly one **logical transition record** for `r`. Its current physical representation is one of:

- an unsealed `state/log/<r>.yaml` transition record, with an optional immutable overflow payload `state/log/<r>.events.yaml`; or
- a sealed-segment representation containing the same logical transition and any overflow payload.

During crash recovery or sealing, both physical representations may temporarily coexist. That is not a duplicate logical transition: they must be byte/hash-equivalent for the transition record and, where present, carry the same overflow digest/count. Any disagreement is corruption and fails audit/reading closed.

The transition is derived from committed state; `control.yaml` remains the single workflow authority, and `last_transition` remains the authoritative bounded description of the newest committed transition. The durable log is therefore **complete and consumable but not workflow authority**.

Recovery already repairs a missing derived log record after the commit point. This ADR makes completeness an explicit consumer guarantee and extends recovery to any staged overflow payload described by D2.

### D2. The record gains typed events, derived in the store

`last_transition` gains a bounded `events` summary plus, when necessary, an `event_overflow` descriptor. The complete logical event set is derived by `ControlStore._commit` from the committed `before` and `after` states plus operation-declared facts.

It is computed in the store, not in a transaction finalizer, so direct `Session.commit` sites are covered.

Derived kinds, by comparing hot collections (bounded by active complexity under ADR-0011 H1, so derivation is history-independent):

| Kind | Fields | From |
|---|---|---|
| `lead.generation` | `from, to` | `lead.generation` |
| `work.state` | `id, kind, from, to` | `work[*].state` (a unit created: `from: null`) |
| `invocation.status` | `id, work, role, from, to` | `invocations[*].status` |
| `run.added` | `invocation, run` | `invocations[*].runs` |
| `credential.revoked` | `id, reason` | `tokens[*].revoked_at` |
| `history.appended` | `from_count, to_count, head_h` | `cold.root` |
| `unit.archived` | `id, kind, state` | `recent` (new entries) |
| `queue.entry`, `queue.lease` (M4-D) | `id, from, to` / `entry, custodian` | `queue.*` |

Operation-declared kinds are appended through `TxnContext.events` for facts the state diff cannot recover precisely, including `decision.recorded {id, type}`, `handoff.recorded {id}`, `evidence.ingested {work, kind, ids}`, and `audit.recorded {id, result}`. Operation-declared events are data supplied by the authoritative Engine operation; they do not allow callers or consumers to invent events independently.

The existing `op`, `actor`, `summary`, `reason`, and `refs` remain. `refs` continues to name durable files written by the transition.

#### Bounded hot representation

`last_transition.events` contains at most 64 event objects.

If the complete event set contains 64 or fewer entries:

```text
events: [complete set]
event_overflow: null
```

If it contains more than 64:

```text
events: [first 64]
event_overflow:
    path: state/log/<rev>.events.yaml
    sha256: <digest of canonical overflow payload>
    event_count: <complete count>
    counts_by_kind: {...}
```

The bounded list is a hot-state summary only. **Consumers are never instructed to reconstruct truncated events by diffing historical control states.** AEW does not retain every prior `control.yaml`, so such reconstruction is not a valid recovery mechanism.

#### Complete overflow payload

For an overflow transition, the **complete event list** is written as immutable `state/log/<rev>.events.yaml`. Its canonical bytes are prepared as a normal staged transaction write and are named/digested by the committed `last_transition.event_overflow` descriptor.

This preserves ADR-0001's one commit point:

- before the control replacement, an overflow payload is at most unreferenced staged/future-revision data;
- after the control replacement, `last_transition` commits the exact overflow path, digest, and count;
- redo/recovery has sufficient staged-write information to publish or verify the identical payload if publication was interrupted;
- a mismatched payload fails closed.

No post-commit process is allowed to regenerate the full event set from unavailable historical control states.

#### Schema and hash coverage

`transition.schema.json` (`aew/transition/v1`) validates the bounded transition record and its optional overflow descriptor, closed at every level; `control.schema.json` references it for `last_transition`. Each per-revision log record carries `schema: aew/transition/v1`.

The overflow payload has its own closed schema (for example `aew/transition-events/v1`) and contains JSON values only.

D7's transition hash commits to the overflow descriptor, including its SHA-256 digest and complete event count. Therefore alteration of the overflow payload breaks verification even though the full list is not embedded in hot state.

### D3. The reader protocol: a cursor is a revision number

A consumer remembers the last revision it has seen and asks for everything after it. The engine offers one surface:

```text
aew history log --since R [--follow] [--kind work.state ...] [--json]
```

It yields logical transitions `R+1 … revision` in order. For an overflow transition the reader resolves and verifies the referenced overflow payload so the consumer sees the **complete logical event set**, not only `last_transition.events`.

The physical files are immutable once published. Reading the log never takes the control lock. Because sealing is also lock-independent from the reader, the reader protocol is explicitly race-safe:

1. resolve the revision in the expected unsealed representation;
2. if absent, refresh the sealed-segment view and resolve it there;
3. if both unsealed and sealed representations are present, require logical/hash equivalence and use either;
4. if neither resolves after a bounded refresh/retry, report corruption/incomplete history rather than inventing a gap.

A reader finds the current revision from the cheap authority-file identity/cached parse already used by the engine. H3 remains untouched: a long-lived waiter does not repeatedly parse `control.yaml`.

`--follow` blocks on the advisory wake signal (D4) and emits each newly committed logical transition. A consumer that has fallen behind transparently walks sealed segments. The cursor remains the revision number regardless of physical representation.

### D4. One wake signal, advisory

`local/wake`: a small file the store bumps after each commit's log write (in `_post_commit`, after `txn.after_log`) and the supervisor bumps after each `run.json` write. A waiter stats that one file at a short interval (20 to 50 ms) and, on a change, checks what it waits for; a coarse full check every 2 s remains, as the supervisor does today. Waking is advisory: a missed or spurious wake costs latency, never correctness, and nothing in `local/` is relied on (ADR-0011 invariant 4). OS notification (inotify, `ReadDirectoryChangesW`) is an optimization that may replace the stat later behind the same interface; the M4 plan's "wake file or pipe" is thereby decided as the file.

### D5. Observed run facts stay outside the outbox

The supervisor's `run.json` and `events.jsonl` (`local/harness/runs/<run>/`) are local observations, not committed facts, and a run's end "moves no state until the Lead ingests it" (WC §8.2, `supervisor.py:289`). They do not enter the outbox. The outbox carries committed facts only. `aew harness wait --any R1 R2 …` therefore combines both lanes on each wake: the run records (did any run end) and the new committed events that end a run from the control side (`invoke.cancel`, `credential.revoked`, `lead.generation`). When F15 §16's immediate revocation on run end lands in M4-D, it lands as a commit and becomes an outbox event with no change here. Whether a supervisor may commit at all is an authority question (ADR-0005, ADR-0009) and is not decided by this ADR.

### D6. Bounding: a 4,096-revision unsealed window, sealed segments, no discard

The transition history is the durable record of committed transition provenance by revision. It is never discarded.

- `LOG_WINDOW` is **4,096 revisions** for v1.
- Records older than the window are sealed in groups of 256 logical transitions into `state/log/seg-NNNNNN.yaml`.
- A segment contains each bounded transition record and, for any overflow transition, the complete overflow event payload (or an equivalently hashed segment-local representation). The segment verifier recomputes the overflow digest/count from the sealed payload and requires it to match the transition's committed descriptor.
- The segment is written create-if-absent, fsynced, re-read, schema-validated, and hash-verified before any per-revision transition file or overflow sidecar is removed.
- Pruning is idempotent. A crash may leave only unsealed files, or both a valid segment and some/all equivalent unsealed files; it must never leave neither logical representation.
- Physical coexistence during sealing/recovery is permitted by D1. Readers do not rely on the control lock; they follow D3's refresh/retry algorithm. The control lock may still serialize pruning against other writers/compactors, but it is **not** the mechanism that makes lockless readers safe.
- Compaction is **off the commit path**. `aew history compact` is the v1 mechanism. `aew doctor` reports when the unsealed window exceeds `LOG_WINDOW + 256`. A future background maintenance service may invoke the same compaction primitive, but no archival/transaction finalizer performs sealing synchronously.

With 60,000 revisions this reduces the repository from tens of thousands of per-revision files to roughly a few hundred sealed segments plus the bounded unsealed window, while preserving every logical transition.

### D7. The records are hash-chained

Each transition record carries `h = SHA-256(bytes.fromhex(prev_h) || canonical_json(record without h))`, with `prev_h` the previous transition's `h` and the genesis convention reused from ADR-0011. `last_transition.h` is the current head and is committed with the state.

For overflow transitions the canonical record includes `event_overflow.path`, `event_overflow.sha256`, and `event_overflow.event_count`, so the chain commits to the complete event payload without placing it in hot state.

One transition hash is computed per commit. A repaired record is derived from committed `last_transition` and therefore hashes identically. Sealed segments preserve and verify the same chain rather than minting a new event identity.

The chain makes the transition history tamper-evident and lets incremental audit, dashboard projection code, and knowledge capture verify the records they consume. It does not turn the transition log into workflow authority; control state remains authoritative.

### D8. Consumers, and what each gets

- **E1 wait-any (M4-D).** `aew harness wait --any`: block on `local/wake`, check both lanes (D5), return the first run to end with its next action, as §2.9 of the M4 report asks. The 0.2 s poll goes; the coarse fallback stays.
- **Supervisor and Lead broker watchdogs.** May keep their identity stat; with the outbox they react to `lead.generation` and `credential.revoked` events instead of re-parsing on every change. H3 is unaffected either way.
- **F20 dashboard.** The backend keeps a cursor and initially serves `GET /api/v1/events?since=R` as a **bounded long poll**. SSE is a later transport optimization over the same cursor/event service and is not required by this ADR. The notification says only that committed revision(s) changed specified kinds/ids; the frontend refetches authoritative projections with ETags. It is a contract addition and renews the C0 review; the composite Overview stays coherent because it is served per revision. No poll takes the control lock, which W01 requires.
- **Knowledge capture (K2, M6b).** The capture worker's cursor is a durable knowledge-domain record, never a file in `local/`; a job's identity is `(project_id, revision, event_index)`; a debounce window is a revision range; duplicate capture of the same `(revision, index)` returns the prior receipt (capture §8). The knowledge store's own `knowledge_event_seq` (shared semantics §4.2) stays its own sequence; the outbox position is recorded on receipts as the source pointer. A worker far behind reads sealed segments. Its credential is K4's service identity, read-only on the outbox.
- **Scheduler (F11, M5) and F15 §16.** Consume `queue.*`, `work.state`, `run.added`, `credential.revoked`, `lead.generation` and react on the event; the `ActionProjection` behind `/attention` is recomputed when an affecting kind lands, not per poll.

### D9. Crash semantics under ADR-0001

`events`, `event_overflow`, and `h` are fields of `last_transition` inside `control.yaml` and are committed atomically with the state.

For a non-overflow transition, the derived per-revision log record is repaired exactly as today if the process dies after the control replacement.

For an overflow transition:

1. the complete overflow payload is prepared as a staged transaction write;
2. the committed `last_transition` names and hashes that exact payload;
3. recovery publishes/verifies the identical payload from transaction staging/redo if the commit occurred but publication was interrupted;
4. recovery never attempts to reconstruct missing overflow events by diffing unavailable historical control states.

Existing fault points continue to cover the control/log relationship. Add an overflow-specific fault point covering a committed `last_transition` with the overflow payload not yet published, and prove recovery restores the exact staged bytes.

Sealing adds:

- `log.seal.after_segment`: segment durable, unsealed files still present — re-run verifies segment then resumes pruning;
- `log.seal.mid_prune`: segment durable, some unsealed files removed — reader uses the segment; re-run completes pruning.

At every point at least one valid physical representation of each committed logical transition remains available. Migration/mass-transition tests must exercise an overflow larger than 64 events.

### D10. Downgrade safety

`last_transition.events` and `h` are additive, but every engine validates `control.yaml` with `additionalProperties: false` on load, so an older engine refuses an outbox-era control file and fails closed, exactly as the M4 report's §2.6 argues for the `queue` key. Ship these fields with M4-D under whichever schema decision that phase makes (v2 additive with the refusal as the guarantee, or v3 with a no-op `aew migrate` step); do not ship them separately.

## Invariants the implementation must keep

1. **One commit point** (ADR-0001). Nothing new is staged; the outbox adds fields to a record that is already inside it.
2. **History independence** (ADR-0011 H1, H2, invariant 13). Event derivation compares hot collections only; hot `events` is capped at 64; overflow bytes are staged/durable without remaining in hot state; the commit path does no sealing.
3. **Nothing in `local/` is authority.** The wake file is advisory; `aew resume` after deleting `local/` is unchanged (ADR-0011 invariant 4).
4. **Readers take no control lock.** The log is immutable once written; the only lock a reader may need is the one it holds anyway to find the current revision, and a long-lived reader uses the identity stat instead.
5. **The log is never discarded.** Sealing changes physical representation; it does not drop a logical transition or its overflow payload.
6. **Observed facts are not committed facts** (D5). A run record is telemetry until the Lead ingests it.

## Oracle rules (additive)

- **24. Logical log completeness.** For every `r <= revision`, exactly one logical transition is resolvable. Equivalent unsealed/sealed physical copies may coexist transiently; disagreement is corruption. The newest logical transition equals committed `last_transition`.
- **25. Event fidelity.** The complete logical events for revision `r` equal the derivation over `(state r−1, state r)` plus operation-declared authoritative facts wherever both states/facts are available in the model test.
- **26. Hot-state bound.** `len(last_transition.events) <= 64`. If the complete set exceeds 64, `event_overflow` exists, its count/digest match the complete immutable payload, and the reader returns the complete set.
- **27. Segment fidelity.** A sealed segment holds exactly 256 logical transitions except a final partial segment if a future policy permits it; each overflow payload is preserved and digest-verified; chain continuity is unchanged across the segment boundary.
- **28. Reader race safety.** For each modeled sealing/crash interleaving, a lockless reader either resolves the logical transition from an equivalent representation or returns an explicit corruption/incomplete-history error; it never reports a false gap.

## Completion criteria

Measured with `tools/perf/control_plane.py` on the reference Windows machine and the Rocky 8 target, as ADR-0011's were.

- **H2 budget.** Derivation plus hash add at most 10 ms to a commit at 20 open / 3,000 completed, flat along the history series (they read hot collections only).
- **Wake latency.** Commit to waiter wake, two processes: median under 50 ms on both platforms (against the 200 ms poll and the dashboard's 2 to 10 s). Measured by a test that commits in one process and blocks in another.
- **No parse while waiting.** `aew harness wait --any` performs zero `control.yaml` parses between wakes (profile counter `parse`), and the dashboard backend's event endpoint performs none per request.
- **Git cost.** With 60,000 revisions compacted behind the 4,096-revision window, `git status` ≤ 0.15 s on the reference machine (investigation: 0.10 s sharded).
- **Coverage.** Crash matrix and seeded walks include overflow publication recovery, both sealing fault points, lockless reader/compaction races, and repaired-log cases; migration/mass-transition tests exceed 64 events and prove full recovery; rules 24 to 28 run in the oracle; M1 to M4-C tests remain unchanged except tests intentionally updated for the transition schema.
- **Review.** Reviewed like a store change (ADR-0011 "Review"): a brief states what changed in ADR-0001's model.

## Test sketch

- **Unit.** Table-driven derivation over before/after fixtures for every kind in D2, including creation, revocation, archive, and >64-event overflow; validate both transition and overflow schemas; prove the transition hash commits to the overflow digest/count.
- **Store.** Extend `tests/helpers/store_model.py` so every modeled commit asserts complete event fidelity where inputs are retained; add overflow-publication and `log.seal.*` fault points; keep the repaired-log probe as a regression.
- **Integration.** Two processes: writer commits, waiter wakes; `harness wait --any` over two fake-harness runs ends on the first and reports its next action; a missed wake still returns within the coarse interval; a lockless reader mid-walk while compaction publishes/prunes never sees a false logical gap; overflow events remain complete before and after sealing.
- **Regression.** Rules 24 to 28 in `tests/helpers/invariants.py`; the downgrade test also covers an outbox-era control file.
- **Perf.** The sweep's commit latency delta; a `git status` timing on the 60,000-revision fixture before and after `compact`.

## Alternatives considered

- **A separate `state/outbox/` ring rewritten each commit.** Rejected. It is a second record of the same commit, a new redo-staged file on every transition, and O(ring) per commit. The log already exists and already has one committed logical transition identity per revision.
- **Every commit as a history-manifest entry (`kind: txn`).** Rejected. The manifest holds durable terminal knowledge and is audited as such; twenty times the entries changes its audit cost profile, and the two have different retention and trust roles. If the transition history must one day be verifiable from the cold root, D7's head can be pinned into the manifest by each audit record (one field) without moving the records.
- **A SQLite table in `local/` as the outbox.** Rejected as the record (`local/` is disposable); accepted as an optional reader index later, in the pattern of `local/history.sqlite`: a locator, never a voucher.
- **OS file notification alone.** Rejected. It carries no content, is lossy, and the dashboard and capture need the record. It remains the optimization behind D4.
- **Supervisor-committed run events.** Deferred: the supervisor holds an invocation credential, not the Lead's; letting it commit is an authority decision (ADR-0005, ADR-0009), and the F15 §16 reactions that need it are M4-D work. D5 keeps the two lanes distinct so that decision can be made on its own.

## Consequences

- Polling/waiting consumers and future designs (wait-any, dashboard change notification, capture, scheduler, `ActionProjection`) share one committed-transition mechanism and one cursor protocol: the revision number.
- ADR-0001's "never authoritative" is refined to "derived, complete, consumed, never authoritative"; the record is also tamper-evident if D7 stands.
- `state/log/` is bounded in file count; the 60,000-file git cost the investigation chose to tolerate goes away as a side effect.
- `last_transition` gains two fields and a schema; every engine older than the change refuses the file (D10); the dashboard API gets a new endpoint and a renewed C0 review; `future-work.md` gets a register row (proposed id E15, "transaction outbox", M4-D, source G11/K2) and E1's row points at it.

## Frozen design decisions and deferred dependency

The designer resolves the former open questions as follows:

1. **Window:** `LOG_WINDOW = 4,096` for v1. Compaction is maintenance-only/off the commit path; a future background caller may invoke the same primitive.
2. **Hash chain:** D7 is **kept**. One hash per committed transition is justified by the consumers that rely on the log and by reuse of ADR-0011's tamper-evident discipline.
3. **Command name:** use **`aew history log`**, not `aew events`. The outbox is a consumable historical projection, not a new state authority.
4. **Dashboard transport:** the initial backend transport is bounded **long poll** over the cursor service. SSE may be added later without changing event semantics.
5. **Supervisor commits:** **not authorized by this ADR**. Observed run completion remains outside the committed transition log until an explicit ADR-0005/ADR-0009 authority decision says otherwise.
6. **Knowledge capture cursor storage:** the cursor must be durable, project-bound knowledge-domain state and must not live in `local/` or hot control state. Its exact physical placement is intentionally delegated to T4 / the Knowledge Storage ADR. That dependency does not block this ADR's event semantics.

There are no remaining designer-level choices required to implement ADR-0012. Operator adoption of the ADR remains the governing approval step.

## Checks before relying on this ADR

- The probes ran against `tree/` at `dcd43f1` with a venv in this directory (`.venv/`, editable install of `tree/`). Re-run `repro/log_growth_probe.py` then `repro/log_recovery_probe.py` (the second needs the token the first leaves in `repro/work/token.txt`).
- Line references are to `dcd43f1`. M4-B (`b057a61`) touches `harness/containment` and tests, not the store or the log; `main` and `docs/restructure` had not moved as of 2026-10-04.
- The live checkout's three M6 drafts still match `extra-docs/SHA256SUMS`; K2's wording quoted here is from those copies.
