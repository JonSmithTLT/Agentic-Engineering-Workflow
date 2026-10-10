# ADR-0017 — Coordination messages: first-class Lead-worker messaging (F9-A)

- **Status:** **Accepted** (lead developer, 2026-10-10), with the F9-A plan v4 that it records, after four independent
  plan reviews (v4 CLEAR, 2026-10-09). Built in slices MS0 to MS7. **MS1 built** (the coordination store): D1 to D4;
  D5's derived facts (`RECORDED`, `ACKNOWLEDGED`, `REPLIED_TO`) and the reader of fact lines, but no fact writer; and
  D6's switch read from adopted bytes, its off state, the marker and the defaults, but not its snapshots. **MS2 built**
  (2026-10-10, the sealing slice): D7, D11's engine side, D12, D9's evidence inputs and the operator reads, as the
  amendment of 2026-10-10 records. Everything else is stated here as decided and lands with the slice the build-status
  table names. The transport section (D8)
  waits for MS0's live-delivery probe; each later slice adds a dated amendment section when it lands. Number: the next
  free one at MS1 (ADR-0016 is held by F4).
- **Resolves:** the implementation choices F9-A1 leaves open for F9-A: where messages live and how they are identified,
  how a retry is recognized, what a reply and a ref may name, the bounds, the switch and its off state, when a thread is
  sealed, and what the rollback, delivery and independence rules are.
- **Basis:** [F9-A1 v0.1](../../design/f9-a1-lead-worker-messaging-and-adaptive-supervision-amendment-v0.1.md) §3 to
  §11, §25 (F9-A), §26 to §28 (ledger LWM); the operator's and designer's
  [adoption decision](../../design/decisions-2026-10-09-f9-a1-adoption.md) (ledger LWA: F9-A first, behind a switch with
  disabled-state identity tests, off in M4-H's frozen treatment; transport provisional on the live-delivery probe; no
  model-driven polling); [F9 v0.1](../../design/proposals/AEW_Live_Coordination_and_Assumption_Propagation_Design_v0.1.md)
  §3, §6, §7, §14, §21, §22; ADR-0001 (the control lock, the commit point); ADR-0011 (cold records pinned by bundles);
  ADR-0012 D4 (the advisory wake) and its note of 2026-10-10.
- **Nature:** a new record kind beside control state. Nothing here creates authority: a message moves knowledge, never
  project state (F9 invariant 1), and no gate, transition, dispatch or evidence path reads one.

## Context

F9-A1 asks for a durable, bounded path between the current Lead generation and an active worker that creates no
invocation (its invariant 13). `aew harness send` exists, but it has no message identity, reply path, idempotency or
thread, and it moves the revision. The messages must survive session loss, must not let a contained worker write
another's record, must not make the Lead's `expect_rev` stale by themselves, and must be absent while the operator has
not switched them on: M4-H's frozen treatment runs with messaging off and is not amended.

## Decision

### D1. One append-only thread per invocation, recorded under the control lock without a commit

F9-A is Lead-worker only, so a thread's other party is the Lead (plan D-1). A thread is one JSONL file,
`.aew/work/<T>/coordination/<INV>.jsonl`, outside control state and every run directory (D-3): under bubblewrap the
project is read-only and only a run's own directories are writable, so a contained worker cannot write it. Each line is
canonical JSON whose `h` is `sha256(previous h || the line without h)`, a chain per thread from a genesis hash of the
thread's id; a line is a `message` or a `fact`. Messages are recorded only on v2 projects (`MIGRATION_REQUIRED` on v1),
so `aew migrate` never meets a thread.

Recording takes the control lock and commits nothing (D-4): open the session (recovery runs), check authority and, for a
Lead message, its `expect_rev` against the session's revision (`STALE_REVISION` before anything else), check
idempotency (a match returns the existing message, even if its recipient has ended since), check the recipient and the
bounds, repair a torn final line (only a writer under the lock repairs), append with fsync, and release. The revision
does not move, so neither a Lead message nor a worker reply makes a Lead's `expect_rev` stale; the message records the
revision it was checked against (`checked_rev`). Lock-free readers read complete lines only and never repair. Creating
a thread syncs its new directory. The writer touches `local/wake` after each append (D-5; ADR-0012 D4: advisory).

### D2. Identity and idempotency

A message id is `MSG-<INV>-<n>`, the thread's own sequence (D-2): no global counter, so no control-state commit. The
record (`aew/coordination-message/v1`, D-6) names its sender (`lead:<generation>` or `invocation:<INV>`), recipient,
work unit, Ticket revision (D-9), the thread invocation's latest run, the channel (`lead_mcp`, `lead_broker`, `cli`,
`run_bridge`), `in_reply_to`, `idempotency_id`, kind, body, refs, `created_at` and `checked_rev`.

An idempotency id is scoped to (sender, thread), and the sender carries the Lead generation (D-8), so a new generation's
re-send after a takeover or handoff is a new message. A matching id returns the existing message with `duplicate: true`
and its facts; the same id with other content (body, kind, refs or `in_reply_to`) is `IDEMPOTENCY_CONFLICT`. An
omitted id is derived as `sha256:` of the canonical JSON array `[sender, thread, in_reply_to, kind, body, refs]`, so a
verbatim retry after a lost response returns the original and no two contents collide across a field boundary; a
deliberate verbatim repeat needs an explicit id, and the duplicate answer says so. `expect_rev` is not part of the
derivation: a Lead retry refused as stale re-reads, retries with the new revision, and gets the original back. The
argument is `idempotency_id`, because the catalog refuses any argument name containing `key`.

### D3. Replies, kinds, refs and the Ticket binding

`in_reply_to` names an earlier message of the same thread (`REPLY_NOT_IN_THREAD` otherwise). For the Lead it is
optional; for a worker it is required and names a Lead message (D-10): F9-A's worker direction is a reply, and
unsolicited updates are F9-B's. Kinds are F9-A1 §9's eight (D-11); the defaults are `instruction` for the Lead and
`status` for a worker. Kinds change presentation only, and no engine module branches on one.

Refs are `kind:value` strings (D-12): `evidence`, `ticket` (`T-n` or `T-n@rN`), `finding`, `message`, `run`,
`decision`, and `source` (a workspace-relative path with an optional `#Ln` or `#Ln-Lm`). AEW ids must exist
(`REF_UNKNOWN`); a `source` is checked for its syntax only. A worker cites only its own unit, thread, Ticket and runs
(`REF_OUT_OF_SCOPE`). A ref is a string: it grants no access and is never resolved for the recipient.

A unit stores a review's finding as `<evidence id>#<finding id>`, so a finding ref has two forms. The qualified
`finding:<evidence id>#<finding id>` names one finding of the unit holding that evidence: the Lead may cite any unit's,
a worker only its own unit's. The short `finding:<finding id>` (F9-A1 §10's `finding:F-22`) resolves within the
thread's own unit only, and only when exactly one of its findings has that id; when two reviews used the same id it is
refused (`REF_UNKNOWN`, reason `ambiguous`), naming the qualified ids to cite instead.

`ticket_revision` is the revision the invocation records on an F4-enabled project, read at record time, and `null` on a
dormant project or a non-Ticket unit (D-9). Until F4 binds revisions, a `T-n@rN` ref cannot be shown to exist and is
refused.

### D4. Bounds

Code constants, each refusal naming its bound (D-7): a body of 1 to 4,000 characters that never carries an AEW
credential; at most 8 refs of at most 200 characters each; at most 200 messages per thread; at most 16 Lead messages per
thread that the worker has not had; at most 20 worker messages per thread that the Lead has not seen
(`LEAD_INBOX_FULL`). A message counts as had or seen once a delivery fact names it or the other party has replied to it.
Every refusal is `COORDINATION_LIMIT` (or its subtype `LEAD_INBOX_FULL`) with `details.bound`.

### D5. Delivery facts

Communication facts only (D-13; LWM-09). `RECORDED` and the reply facts (`ACKNOWLEDGED`, `REPLIED_TO`) are derived
from the thread (built with MS1, as is the reader of fact lines). The written facts are planned for their slices
(`POSTED` and `DELIVERED` with MS4 to MS6, `UNDELIVERABLE` with MS2's seal); MS1 writes none: `POSTED {run,
generation, checked_rev}` is to be recorded under the lock immediately before a transport call;
`DELIVERED {via, at, transport_ref}` when the harness admitted the input (`live`), for exactly the ids a relaunch's
continuation carried (`continuation`), when `message.wait` returned it (`wait`), or when a Lead result first carried a
worker message (`lead_result`); `UNDELIVERABLE {reason}` at the seal, for never-posted messages only. A message posted but
never confirmed stays `POSTED` ("outcome unknown"). `DELIVERED` means admitted, not read. No gate, transition, dispatch
or evidence path reads a fact, apart from D9's provenance. A superseded generation's never-posted message is never
delivered later (D-14); it shows as `UNDELIVERABLE: sender_superseded`, and the new Lead may re-send it as new.

### D6. The switch, and off means absent

`coordination.messaging: disabled | enabled` in the execution policy (D-15): absent means `disabled`; a string enum,
not a boolean (a YAML boolean is refused at adoption with its cause); classified `operational`, since it gates no
legality and grants nothing. It is read from the adopted bytes only: the control state's pins must hold the manifest
and the execution policy, and an edit nobody adopted, an unreadable policy or a project without pins all read as off
(`MESSAGING_DISABLED`, `details.reason`: `switched_off`, `not_adopted`, `unreadable`). Only the operator's
`manifest adopt` turns it on. Planned with the slices that read it (not built in MS1): the broker snapshots it at
session start (MS3) and each run at launch (MS4).

Off means absent: no catalog row, CLI command, bridge operation, environment variable, prompt line, policy key,
control-state key or output field. New records, live delivery, `message.wait` and the surface additions are gated by
the switch (D-31); the seal, `UNDELIVERABLE`, pinning and evidence inputs always run, each a no-op where no thread
exists, so turning the switch off never orphans a thread. The read projections key on "the switch is on, or any thread
exists", which is one stat of the project marker `.aew/coordination/marker.yaml` (`aew/coordination-marker/v1`):
written once, create-exclusive and synced with `.aew/coordination/` and `.aew/`, under the control lock before the
project's first thread file, and never removed by AEW. A writer that finds it removed while a thread exists
writes it again with `recreated: true` and the time, so the deletion stays visible. No write-side decision trusts
it. No default writes the key (D-32):
`aew init`, the shipped default execution policy and `migrate` never do, so the policy bytes and both policy digests
stay as they were.

`surface.presentation: standard | compact` (operational, absent means standard) selects the typed surface's compact
presentation without messaging, so an evaluation arm without messaging can present the same text as one with it
(D-33, D13). MS1 adds the key; it changes nothing until MS3 builds the compact text.

### D7. Sealing at every invocation-ending commit

One kernel function seals the threads of the invocations a commit ends (D-16): a `lead_txn` finalizer placed
immediately before archival, so the seal's pointer is on the unit when archival bundles it, and explicit calls on the
direct paths that can end an invocation (takeover, handoff acceptance, acquire). `Session.commit` keeps a fail-closed
check: an ending that missed its call is sealed by fallback on a hot unit, with a `coordination.seal_fallback` event
naming the operation, and refused (`ThreadUnsealed`) only in a commit that archives the unit. The seal record
(`aew/coordination-seal/v1`) is immutable and content-addressed, pins the thread's `sha256` and size, is written before
the commit and referenced by path and hash, and never refuses the ending: a damaged chain is sealed `damaged: true`. A
sealed thread accepts nothing. Archival pins the seal, and `history verify --full` follows the seal to its thread, as an
evidence record pins its log.

### D8. Delivery and the continuation

Live delivery is provisional on MS0's probe of OpenCode 2.0.18 (the operator's decision): `POSTED` before the
transport call and `DELIVERED` on admission, with a deterministic transport id, at the next step boundary (`delivery:
queue`) and never an interrupt (D-28). An adapter without live delivery reports `unsupported`, and messages wait for the
continuation (invariant 16). A relaunch's continuation carries the current generation's never-posted messages, labelled
unconfirmed posts and unresolved earlier ones (at most 10), and the launch contract records exactly the ids it carried
(D-29). MS0 adds the transport section here.

### D9. Independence: confirmers, and inputs on evidence

A message to an F4 confirmer (scope `revision`) is always refused (`RECIPIENT_INDEPENDENT`), and a confirmer's
continuation carries none (D-34); `NOT_A_WORKER` refuses an engine custody invocation. Messages to reviewers and
verifiers stay allowed, as `harness send` allows them, and the evidence an invocation submits records every Lead message
posted or delivered to it before (`coordination_inputs`, D-35), so whoever judges that review's independence sees the
Lead text it received (KDR-03 to KDR-05, AEA-18: Lead text is recorded, not hidden).

### D10. The supervisor checks before posting, and the same-UID residual

Before it posts, the supervisor checks that a message's `checked_rev` is at most the current revision, that its sender
is the current generation, and that the generation began at or before `checked_rev`; otherwise it records a bounded
`message_refused` event and writes no fact (D-36). The residual this leaves: on an uncontained host, a same-UID
forger who also computes a consistent `checked_rev`. Under containment a worker cannot write a thread at all (D1).

### D11. A final reply survives the seal

A worker's last reply before it submits must reach the Lead (D-38): `harness_wait`'s `run_ended` result carries the
ended run's unseen worker messages; the seal lists those shown to no Lead generation (`unseen_by_lead`), and the sealing
commit adds them to a hot list, `coordination_unseen`, capped at 20 with an `omitted` count and revision range; the
reads list them as settled entries until a Lead-credentialed result carries them, which is recorded in
`.aew/coordination/lead-seen.jsonl` and pruned at the next commit; a bounded recovery read lists the omitted ones.

### D12. Rollback safety: the registration key

The operator's adoption that leaves messaging enabled commits a top-level key, `coordination_store: {since_rev,
decision}`, through a hook beside steering's (D-39). The control schema is closed, so an engine built before the
sealing slice refuses such a project at its first read, before it could end a messaged invocation without a seal. From
that slice on, recording also needs the key (`MESSAGING_DISABLED`, reason `not_registered`). No surface that creates a
thread merges before then: the Lead's tool waits for the sealing slice, and a worker's reply needs a Lead message
first.

### D13. The typed surface's budget with messaging on

The typed Lead surface must meet TLS-21 (at most 12,000 bytes and 16 tools) with messaging on as well as off (D-33).
D9's recovery-only rule for a switch-registered row does not fit here, because F19's arm B needs `message_send` on the
normal surface. So:
- with messaging on, every normal row is served in a **compact presentation**: shorter tool and argument
  descriptions, with every name, type, enum, pattern, bound, `required` set and annotation unchanged; semantics are
  unchanged;
- it is a switch variant, so the off configuration (the shipped default and M4-H's treatment) stays byte-identical;
- the on configuration, measured over every catalogued normal row, is held to **at most 11,900 bytes and exactly 16
  tools** (M4-E's 15 normal rows after E6, plus `message_send`), with **no tool headroom**: a later normal row makes the
  on configuration 17 tools and fails its own slice's CI, and that slice's plan makes its own budget decision;
- an E-slice whose catalog change pushes the on configuration past 11,900 bytes adds the matching compact text in the
  same pull request;
- `surface.presentation: compact` gives an arm without messaging the same text.

Built with MS3.

## Crash and damage rules

- A crash between the marker and the first thread file leaves a marker with no thread: the reads show an empty
  section.
- A torn final line (a crash mid-append) is ignored by readers and cut by the next writer under the lock; a complete
  line that breaks the chain is an integrity failure, never shown as text and never extended.
- A seal record written before a commit that never lands is an unreferenced, benign file; the invocation stays active
  and its thread writable, and a retry seals again.

## Amendment of 2026-10-10: the sealing slice (MS2) as built

D7, D11's engine side, D12, D9's evidence inputs and the operator reads are built as decided above. The choices the plan
left to the implementation, and what this slice adds beside them:

- **Where the seal runs.** `Coordination.seal_ending(session, refs)` is the one function: the Lead-transaction finalizer
  `Coordination.finalize`, placed after every finalizer that can end an invocation and immediately before archival
  (`tests/unit/test_engine_composition.py` pins the order), and explicit calls in `lead acquire`, `lead handoff accept`
  and `lead takeover` after their queue sync and before their credentials are archived. `Session.commit`'s check
  (`_require_sealed`) seals a missed ending through the same function, which the composition root sets on the store
  (`ControlStore.seal`) once the collaborator exists; a store without it (the perf tool) refuses instead. Every sealing
  commit names its seal records in the transition's `refs`.
- **A reply is evidence of receipt.** A Lead message the worker replied to is not sealed as undeliverable, and is
  recorded on the worker's evidence with `via: replied`; a worker message the Lead replied to is not listed as unseen.
  Otherwise a Lead message is undeliverable unless a `POSTED` or `DELIVERED` fact names it, and a worker message is
  unseen unless a `DELIVERED via: lead_result` fact names it. The reason is `sender_superseded` when its generation is
  not the current one at the seal, else `invocation_ended`.
- **What the seal records** (`aew/coordination-seal/v1`): the thread's path, sha256 and size as sealed; the chain head,
  verified line and message counts; `damaged` (any bytes after the verified prefix, a torn tail included) with
  `verified_bytes`; the undeliverable messages with their reasons; `unseen_by_lead`; the invocation, unit and
  `closed_rev`. The pointer on the unit is `{invocation, seal, sha256, messages, closed_rev}`, classified `bookkeeping`
  in F4's field registry.
- **The hot list.** `coordination_unseen` holds at most 20 entries `{message, invocation, work_unit, seal}`, with
  `omitted` and `omitted_revs`; it leaves control state when emptied. `message_mark_shown` records that a
  Lead-credentialed result carried worker messages: `DELIVERED via: lead_result` on a live thread, a line in
  `.aew/coordination/lead-seen.jsonl` for a sealed one, and only for a message its seal lists as unseen (one shown or
  answered before the seal is already seen); MS6's broker and own-shell runner call it. Each commit's seal step first
  prunes what the seen log records, and resets the omitted count once a `recovered` line covers its range, and only then
  adds the omissions of the invocations it ends, so a recovery is honoured by a commit that omits more. The recovery read
  reads a seal the transition log names only through the unit pointer that pins its full sha256.
- **The reads.** `work show` and `history show` gain `coordination` (per invocation of the unit with a thread: its
  state, counts and last 10 messages), and the operator reads are `aew message thread`, `aew message list --work` and
  `aew message unseen`. Each exists only while the reads are on: the project marker exists, or the project is registered
  and its adopted switch is on (the H3 refinement of D6: no file is read beyond the marker's stat unless the state
  already holds the key). `aew message` is registered only for a `message` command, never inside a worker's run, and
  `message unseen` is Lead-reachable (with the Lead's credential it records what it listed). A sealed thread is shown
  only once its seal matches the pointer's hash and the thread its seal's; a worker's text is labelled
  `untrusted_text` with its author (MS6 adds the rendering). `doctor` adds a `coordination` line only where messaging
  was ever enabled or a thread exists: the registration it lacks, and every ended invocation whose thread no seal pins.
- **Evidence inputs.** `coordination_inputs` is an engine-owned evidence field, refused in a submission, and recorded on
  every evidence kind an invocation produces: its submissions and its check results (`check run`).
- **Rollback.** The downgrade test vendors main's control and transition schemas from before this slice. That schema
  leaves a unit's keys open, so the unit's seal pointer alone would pass it; the registration key, which every state
  holding a thread or a pointer holds (oracle rule 57), is what an older engine refuses. A v1 project cannot hold the
  v2-only key, so its adoption of `enabled` registers nothing; `aew migrate` registers it in the v1-to-v2 commit
  (`{since_rev, decision: null, via: migrate}`).
- **Not here.** The shared diff helper does not exist yet (E5a, E7 and F4 S2a have not merged), so its named exclusion
  and the stage-step equivalence test land with whichever creates it (the plan's coupling table). The oracle rules are
  52 to 58 (C1 to C7, `tests/helpers/invariants.py`; 51 is E3c's).

## Build status

| Slice | What | Status |
|---|---|---|
| MS0 | The OpenCode 2.0.18 live-delivery probe; D8's transport | Not built |
| MS1 | The coordination store: D1 to D4; D5's derived facts and the fact reader (no fact writer); D6's switch read from adopted bytes, off state, marker and defaults (no snapshots); the engine API (`message_record_lead`, `message_record_worker`, `message_thread`); `message.send` declared and listed in `NOT_STEPS` | **Built (2026-10-10)** |
| MS2 | D7, D11's engine side, D12, D9's evidence inputs, the operator reads | **Built (2026-10-10)**: the amendment of 2026-10-10 |
| MS3 | The Lead's `message_send` typed tool, switch-registered, the compact presentation and D13's budget; the broker's switch snapshot | Not built (after M4-E's E4 and MS2) |
| MS4 | The worker's reply as `aew-run` bridge operations; the run's switch snapshot at launch | Not built (after MS0) |
| MS5 | Live delivery and the continuation | Not built |
| MS6 | Lead attention: the wait, `resume`, untrusted rendering | Not built |
| MS7 | F19 hooks, acceptance, live qualification | Not built |

## Consequences

- Messaging adds no authority path. Its static guarantee is a test: no legality module imports coordination.
- A thread grows with its conversation, bounded at 200 messages; the hot state gains nothing until the sealing slice,
  and then only bounded keys.
- With messaging off, which is the default and M4-H's treatment, every surface MS1 to MS6 touches is byte-identical,
  proven by disabled-state identity tests in each slice.
