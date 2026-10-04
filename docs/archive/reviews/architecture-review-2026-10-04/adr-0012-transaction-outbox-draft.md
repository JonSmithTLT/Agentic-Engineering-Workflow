# ADR-0012 (draft) — The transaction outbox: the transition log, typed, complete and consumed

- **Status:** **Draft**, written by the architecture review (thread T3 of `HANDOFF.md`), 2026-10-04. Not accepted. For the designer's review before M4-D. Numbered 0012 because 0001 to 0011 exist; renumber freely.
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

For every revision r ≤ `revision`, exactly one record of transition r exists: as `state/log/<r>.yaml` inside the unsealed window, or inside a sealed segment (D6). The record is derived from the committed state transition; `control.yaml` remains the single authority, and `last_transition` is the authoritative copy of the newest record. The repair at recovery already provides this (probe 2); the ADR names it so that consumers may rely on it, and the oracle checks it (rule 24 below).

### D2. The record gains typed events, derived in the store

`last_transition` (and therefore each log record) gains `events`: a bounded list of what the transition changed, derived by `ControlStore._commit` from the committed `before` and `after` states. It is computed in the store, not in a finalizer, so the five direct commit sites are covered.

Derived kinds, by comparing the hot collections (bounded by active complexity under ADR-0011 H1, so the comparison is history-independent, invariant 13):

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

Operation-declared kinds, appended by the operation through `TxnContext.events` for facts the diff cannot see (ids of new records): `decision.recorded {id, type}`, `handoff.recorded {id}`, `evidence.ingested {work, kind, ids}`, `audit.recorded {id, result}`. The existing `op`, `actor`, `summary`, `reason` and `refs` stay as they are; `refs` already names every file the transition wrote.

**Bound.** At most 64 events. Past the cap the list holds the first 64 and a trailer `{kind: "truncated", counts: {work.state: n, …}}`; a consumer that needs the rest diffs the two states. This keeps `last_transition`, and so the hot state, constant in history (H1): the one-transaction migration of 3,000 units (ADR-0011 invariant 7) would otherwise put 3,000 events into `control.yaml`.

**Schema.** A new `transition.schema.json` (`aew/transition/v1`) validates the record, closed at every level; `control.schema.json` references it for `last_transition`. Each log file gains `schema: aew/transition/v1`. Events hold JSON values only (the same rule as history entries, `history/manifest.py:59`).

### D3. The reader protocol: a cursor is a revision number

A consumer remembers the last revision it has seen and asks for everything after it. The engine offers one surface:

```text
aew events --since R [--follow] [--kind work.state ...] [--json]
```

It yields records R+1 … `revision` in order, each `{revision, at, actor, op, summary, reason, refs, events}`, reading `state/log/` files inside the window and sealed segments behind it, and cross-checks the newest against `last_transition`. The files are immutable once written (`atomic_write`, create-if-absent; a repair rewrites identical bytes), so **reading the log never takes the control lock**: a reader finds the current revision from the cheap identity stat of `control.yaml` it already uses (`base.py:_authority_files_identity`) and a cached parse. H3 is untouched: a supervisor's wait costs no parse.

`--follow` blocks on the wake signal (D4) and emits each new record as it lands. Where the cursor has fallen behind a sealed segment, the reader walks the segment; it is slower, never wrong.

### D4. One wake signal, advisory

`local/wake`: a small file the store bumps after each commit's log write (in `_post_commit`, after `txn.after_log`) and the supervisor bumps after each `run.json` write. A waiter stats that one file at a short interval (20 to 50 ms) and, on a change, checks what it waits for; a coarse full check every 2 s remains, as the supervisor does today. Waking is advisory: a missed or spurious wake costs latency, never correctness, and nothing in `local/` is relied on (ADR-0011 invariant 4). OS notification (inotify, `ReadDirectoryChangesW`) is an optimization that may replace the stat later behind the same interface; the M4 plan's "wake file or pipe" is thereby decided as the file.

### D5. Observed run facts stay outside the outbox

The supervisor's `run.json` and `events.jsonl` (`local/harness/runs/<run>/`) are local observations, not committed facts, and a run's end "moves no state until the Lead ingests it" (WC §8.2, `supervisor.py:289`). They do not enter the outbox. The outbox carries committed facts only. `aew harness wait --any R1 R2 …` therefore combines both lanes on each wake: the run records (did any run end) and the new committed events that end a run from the control side (`invoke.cancel`, `credential.revoked`, `lead.generation`). When F15 §16's immediate revocation on run end lands in M4-D, it lands as a commit and becomes an outbox event with no change here. Whether a supervisor may commit at all is an authority question (ADR-0005, ADR-0009) and is not decided by this ADR.

### D6. Bounding: an unsealed window, sealed segments, no discard

The transition history is the only record of who did what per revision (the hot state keeps the last transition; the history manifest keeps terminal records). It is never discarded.

- The **unsealed window** is the newest `LOG_WINDOW` per-revision files, proposed 4,096 (about 200 Tickets of commits, from about 20 commits per Ticket in the dogfood; two orders above what any live consumer lags by).
- Records older than the window are **sealed** into `state/log/seg-NNNNNN.yaml`, 256 records each, in the history's segment form (`schema`, `seq`, `start`, `prev`, `entries`), create-if-absent. The per-revision files of a segment are removed only after the segment is written, fsynced and re-read with a matching hash. Idempotent: a crash leaves the files, or the files and the segment, never neither. The removal takes the control lock for its bounded 256 unlinks so that no reader sees a gap; the segment write does not.
- Sealing runs off the commit path: `aew history compact` for operators and CI, and `aew doctor` reports a window more than one segment over size. The commit path is unchanged in cost. (ADR-0011's "sharding not required" was a performance call; this is a consumption and git-cost call: 60,000 files become about 240 segments plus the window.)

### D7. The records are chained (proposed; strike if unwanted)

Each record carries `h = SHA-256(bytes.fromhex(prev_h) || canonical_json(record without h))`, with `prev_h` the previous record's `h` and the genesis of ADR-0011's form; `last_transition.h` is the head and lives inside the commit point. One hash per commit; a repaired record is derived from `last_transition`, so it hashes identically. This makes the transition history tamper-evident at O(1), in the discipline the cold history already uses (`history/manifest.py:chain_hash`), lets the incremental audit (ADR-0011 R2) fold the log from its last verified record, and lets the dashboard and the capture worker authenticate what they act on. Sealed segments carry `start` and `prev` as the history's do. Without D7, `events` is still exactly-once with the state; D7 adds tamper evidence, not correctness.

### D8. Consumers, and what each gets

- **E1 wait-any (M4-D).** `aew harness wait --any`: block on `local/wake`, check both lanes (D5), return the first run to end with its next action, as §2.9 of the M4 report asks. The 0.2 s poll goes; the coarse fallback stays.
- **Supervisor and Lead broker watchdogs.** May keep their identity stat; with the outbox they react to `lead.generation` and `credential.revoked` events instead of re-parsing on every change. H3 is unaffected either way.
- **F20 dashboard.** The backend keeps a cursor and serves `GET /api/v1/events?since=R` as a long poll (or SSE; the frontend design's "start with polling" is kept: the push says only "revision N changed these kinds and ids", and the frontend refetches the affected projections with ETags). It is a contract addition and renews the C0 review; the composite Overview stays coherent because it is served per revision. No poll takes the control lock, which W01 requires.
- **Knowledge capture (K2, M6b).** The capture worker's cursor is a durable knowledge-domain record, never a file in `local/`; a job's identity is `(project_id, revision, event_index)`; a debounce window is a revision range; duplicate capture of the same `(revision, index)` returns the prior receipt (capture §8). The knowledge store's own `knowledge_event_seq` (shared semantics §4.2) stays its own sequence; the outbox position is recorded on receipts as the source pointer. A worker far behind reads sealed segments. Its credential is K4's service identity, read-only on the outbox.
- **Scheduler (F11, M5) and F15 §16.** Consume `queue.*`, `work.state`, `run.added`, `credential.revoked`, `lead.generation` and react on the event; the `ActionProjection` behind `/attention` is recomputed when an affecting kind lands, not per poll.

### D9. Crash semantics under ADR-0001

`events` and `h` are fields of `last_transition`, inside `control.yaml`, inside the commit point: they are committed atomically with the state, and the redo record is unchanged. The log file is the derived copy, repaired by recovery (probe 2). Existing fault points cover the new fields: `txn.after_replace` and `txn.after_apply` (log missing, repaired), `txn.after_log` (wake missing, latency only). New fault points for sealing: `log.seal.after_segment` (segment written, files still present: idempotent re-run), `log.seal.mid_prune` (some files gone, segment present: complete the prune). Migration's bounded `events` (D2 cap) is exercised by the existing migration crash test.

### D10. Downgrade safety

`last_transition.events` and `h` are additive, but every engine validates `control.yaml` with `additionalProperties: false` on load, so an older engine refuses an outbox-era control file and fails closed, exactly as the M4 report's §2.6 argues for the `queue` key. Ship these fields with M4-D under whichever schema decision that phase makes (v2 additive with the refusal as the guarantee, or v3 with a no-op `aew migrate` step); do not ship them separately.

## Invariants the implementation must keep

1. **One commit point** (ADR-0001). Nothing new is staged; the outbox adds fields to a record that is already inside it.
2. **History independence** (ADR-0011 H1, H2, invariant 13). Event derivation compares hot collections only; `events` is capped; the commit path does no sealing.
3. **Nothing in `local/` is authority.** The wake file is advisory; `aew resume` after deleting `local/` is unchanged (ADR-0011 invariant 4).
4. **Readers take no control lock.** The log is immutable once written; the only lock a reader may need is the one it holds anyway to find the current revision, and a long-lived reader uses the identity stat instead.
5. **The log is never discarded.** Sealing moves records; it does not drop them.
6. **Observed facts are not committed facts** (D5). A run record is telemetry until the Lead ingests it.

## Oracle rules (additive)

- **24. Log completeness.** For every r ≤ `revision`, record r exists in the window or in a sealed segment, exactly once; the newest record equals `last_transition`.
- **25. Event fidelity.** The `events` of record r equal the derivation over (state r−1, state r). Checkable wherever both states are known: the store model test, the crash matrix walks, and the integration flows (the test keeps the previous state from the previous commit).
- **26. Hot-state bound.** `len(events) ≤ 64`, with a `truncated` trailer when the derivation found more.
- **27. Segments.** A sealed segment holds exactly 256 records and, under D7, continues the chain from `start`; the window holds fewer than `LOG_WINDOW + 256` files after `compact`.

## Completion criteria

Measured with `tools/perf/control_plane.py` on the reference Windows machine and the Rocky 8 target, as ADR-0011's were.

- **H2 budget.** Derivation plus hash add at most 10 ms to a commit at 20 open / 3,000 completed, flat along the history series (they read hot collections only).
- **Wake latency.** Commit to waiter wake, two processes: median under 50 ms on both platforms (against the 200 ms poll and the dashboard's 2 to 10 s). Measured by a test that commits in one process and blocks in another.
- **No parse while waiting.** `aew harness wait --any` performs zero `control.yaml` parses between wakes (profile counter `parse`), and the dashboard backend's event endpoint performs none per request.
- **Git cost.** With 60,000 revisions sealed, `git status` ≤ 0.15 s on the reference machine (investigation: 0.10 s sharded).
- **Coverage.** Crash matrix and seeded walks include the two sealing fault points and the repaired-log cases of probe 2; the migration test passes with capped events; rules 24 to 27 run in the oracle; M1 to M4-C tests unchanged except those that inspect `last_transition`'s raw shape.
- **Review.** Reviewed like a store change (ADR-0011 "Review"): a brief states what changed in ADR-0001's model.

## Test sketch

- **Unit.** Table-driven derivation over before/after fixtures for every kind in D2, including a created unit, a revoked credential, an archived unit, and the cap with its trailer; schema validation of `aew/transition/v1`; chain hash over a repaired record equals the original.
- **Store.** Extend `tests/helpers/store_model.py` so every modelled commit also asserts rule 25; add `log.seal.*` to the fault matrix; probe 2 as a regression (`tests/regression/`).
- **Integration.** Two processes: writer commits, waiter wakes (latency recorded); `harness wait --any` over two fake-harness runs (`tests/helpers/fake_harness.py`) ends on the first and reports its next action; a waiter that misses the wake still returns within the coarse interval; `compact` under a reader that is mid-walk sees no gap.
- **Regression.** Rules 24 to 27 in `tests/helpers/invariants.py`; the downgrade test of M4-D also covers an outbox-era control file.
- **Perf.** The sweep's commit latency delta; a `git status` timing on the 60,000-revision fixture before and after `compact`.

## Alternatives considered

- **A separate `state/outbox/` ring rewritten each commit.** Rejected. It is a second record of the same commit, a new redo-staged file on every transition, and O(ring) per commit. The log already exists and is already exactly-once.
- **Every commit as a history-manifest entry (`kind: txn`).** Rejected. The manifest holds durable terminal knowledge and is audited as such; twenty times the entries changes its audit cost profile, and the two have different retention and trust roles. If the transition history must one day be verifiable from the cold root, D7's head can be pinned into the manifest by each audit record (one field) without moving the records.
- **A SQLite table in `local/` as the outbox.** Rejected as the record (`local/` is disposable); accepted as an optional reader index later, in the pattern of `local/history.sqlite`: a locator, never a voucher.
- **OS file notification alone.** Rejected. It carries no content, is lossy, and the dashboard and capture need the record. It remains the optimization behind D4.
- **Supervisor-committed run events.** Deferred: the supervisor holds an invocation credential, not the Lead's; letting it commit is an authority decision (ADR-0005, ADR-0009), and the F15 §16 reactions that need it are M4-D work. D5 keeps the two lanes distinct so that decision can be made on its own.

## Consequences

- Three polling loops (`harness wait`, the dashboard, the watchdogs' re-parse) and three future designs (capture, scheduler, `ActionProjection`) share one mechanism with one position protocol: the revision number.
- ADR-0001's "never authoritative" is refined to "derived, complete, consumed, never authoritative"; the record is also tamper-evident if D7 stands.
- `state/log/` is bounded in file count; the 60,000-file git cost the investigation chose to tolerate goes away as a side effect.
- `last_transition` gains two fields and a schema; every engine older than the change refuses the file (D10); the dashboard API gets a new endpoint and a renewed C0 review; `future-work.md` gets a register row (proposed id E15, "transaction outbox", M4-D, source G11/K2) and E1's row points at it.

## Not decided here (for the designer)

1. `LOG_WINDOW` (proposed 4,096) and whether `compact` may also run from the archival finalizer when the window is grossly exceeded, or only from maintenance.
2. D7, the chain: keep, or defer until an audit requirement names it.
3. The surface name: `aew events` here; `aew history log` would put it beside the other history commands.
4. The dashboard transport: long poll or SSE for `/events`; both fit contract 0.1.2's envelope and ETag rules.
5. Whether a supervisor may commit a `harness.ended` transition (the authority question D5 leaves open), which decides whether run ends ever become committed events.
6. Where the knowledge capture worker's cursor lives, which is T4's storage question (K1): in the ADR-0011 manifest as a `receipt` entry, or in the second store if that is chosen.

## Checks before relying on this draft

- The probes ran against `tree/` at `dcd43f1` with a venv in this directory (`.venv/`, editable install of `tree/`). Re-run `repro/log_growth_probe.py` then `repro/log_recovery_probe.py` (the second needs the token the first leaves in `repro/work/token.txt`).
- Line references are to `dcd43f1`. M4-B (`b057a61`) touches `harness/containment` and tests, not the store or the log; `main` and `docs/restructure` had not moved as of 2026-10-04.
- The live checkout's three M6 drafts still match `extra-docs/SHA256SUMS`; K2's wording quoted here is from those copies.
