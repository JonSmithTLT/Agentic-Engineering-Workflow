# ADR-0013 (draft) — Knowledge records live in the ADR-0011 history manifest

- **Status:** draft for the designer, written by the independent architecture review (T4 of `HANDOFF.md`), 2026-10-04. Not governing. Numbered like the next ADR only so that other notes can cite it; the repository assigns the real number.
- **Resolves:** `REVIEW.md` §6.2 K1 ("storage is unplaced"), and the outbox draft's open question 6 (where the capture worker's cursor lives). Touches K2 (the trigger), K3 (visibility), K4 (the service identity) only where storage forces a choice.
- **Basis:** ADR-0011 (Decision; invariants 1–14; "Not decided here"); the storage investigation §3, §4, §8.1 and its refinements R1–R8; `history/{manifest,store,index}.py` and `engine/{archive_ops,history_ops}.py` at `dcd43f1`; `history.schema.json`; the three M6 knowledge drafts (capture §4, §7–§8, §12, §18–§19, §23; shared semantics §4–§7, §13, §17, §26; recall §4, §8, §12, §24); KC §5.2, §5.3, §7.4; `ADR-0012-transaction-outbox-draft.md` D3, D5 and §8.
- **Evidence:** `repro/knowledge_manifest_probe.py` and its output `knowledge_manifest_probe.out.txt` (run against the frozen tree through the test helpers' history workload; the schema enum widened in memory only). Numbers below are from that run on the Windows reference machine.
- **Nature:** a placement decision. No transition, gate, authority rule or piece of provenance changes. The knowledge drafts' semantics (immutable content version, append-only disposition fold, admission distinct from serving, retrieval never upgrades authority) are taken as given; this ADR says where their records are written, by what, and how they are found, verified and lost.

## Context

The three M6 drafts put "capture jobs, candidate outputs, disposition events, and delivery receipts" in "dedicated durable/cold knowledge-history structures and incremental indexes rather than hot workflow control state" (shared semantics §17; capture §18). They deliberately leave open "physical storage path" and "whether versions are separate files or revision objects" (shared semantics §26). They also require: knowledge identity and version stable across every projection; a global monotonic `knowledge_event_seq` for cursors, invalidation and recovery (shared semantics §4.2); derived indexes that are rebuildable and never authority (capture §4.4; recall §4.5); idempotent at-least-once capture whose duplicate returns the prior receipt (capture §8); and historical text that stays reference data, not instruction (both drafts, and ADR-0011 invariant 14).

AEW already has a durable, append-only, hash-chained, audited, indexed cold store with exactly those properties: the ADR-0011 history manifest. Its entries are typed by a closed enum (`unit`, `annotation`, `audit`, `lead`), its records are immutable files pinned by SHA-256 from a constant-size hot root (`cold.root`), it has incremental and full verification with a recorded verified root, a derived SQLite index that locates but never vouches (independent P3 review, P3-1), a first-class history surface (`show`, `list`, `links`, `load`, `audit`, `reindex`) and a trust-labelled path for loading a record into a unit's reference context. The question K1 asks is whether knowledge joins it or gets a second structure with the same properties built again.

What the probe established (Q1–Q6 in the output):

| Fact | Measured |
|---|---|
| The only thing refusing a `case` entry today is the entry schema's `kind` enum (plus `ENTRY_KINDS` for `history list --kind`) | Q1 |
| With the enum widened in memory, append, chain, verification with records, index sync, `by_id`, `list(kind)`, `linked(rel, target)` and `links(id)` work on unchanged code | Q2 |
| `annotations(subject)` is bound to `kind = 'annotation'`; a disposition about a case is invisible to it, though the entry's `subject` and `rel` columns already hold what it needs | Q3 |
| `History.unreferenced` is bound to `RECORD_GLOBS`; an orphaned record under `knowledge/` is not reported until the globs include it | Q4 |
| 3,000 cases plus 3,000 dispositions (6,006 entries, 23 sealed segments): a 100-record commit takes 977 ms median (about 9.7 ms per record file, Windows fsync); full verification with records 1.9 s (0.32 ms per 1 KB record, against about 3 ms per 20 KB bundle); chain-only 0.7 s; index rebuild 0.9 s; `by_id` 36 ms authenticated; a 1,000-row `linked` query 770 ms (it authenticates every row returned) | Q5 |
| FTS5 is compiled into the venv's SQLite 3.45.3; indexing 6,003 record bodies takes 1.8 s; a top-20 `MATCH` over 3,001 hits takes 3–5 ms; the index file with entries, links and FTS is 10 MB at 6,006 entries | Q6 |

Two further facts matter for the choice. The dashboard contract 0.1.2 declares `History.kind` an open value with `x-known-values` (unknown values display with a warning), so new entry kinds break no frontend. And the transition outbox draft (ADR-0012 D3) makes the capture trigger a revision-number cursor over the transition log, with the job identity `(project_id, revision, event_index)`; it left the cursor's durable home to this ADR.

## Decision

**Knowledge records are entries of the ADR-0011 history manifest. There is one chain, one hot root, one audit, one derived index and one history surface for terminal work and for knowledge.** Five entry kinds are added: `reference` (K0), `case` (K1), `lesson` (K2 and K3), `disposition` (an append-only event about a knowledge record) and `receipt` (a capture job's durable outcome). The shared semantics' global `knowledge_event_seq` **is** the manifest sequence number; no second sequence is introduced.

### D1. Five entry kinds, one additive schema change

`history.schema.json#/$defs/entry.kind` gains `reference`, `case`, `lesson`, `disposition`, `receipt`; `manifest.ENTRY_KINDS` follows. The entry gains one optional field, `version` (integer, at least 1), used by `case` and `lesson` entries. Nothing else in the entry changes. Existing chains are unaffected: `canonical_json` hashes the fields an entry has, and old entries have no `version`.

| Kind | Entry `id` | `subject` / `rel` | `links` (all optional) | `source` |
|---|---|---|---|---|
| `reference` | `KR-nnnn` is taken by receipts; references use `K-nnnn` like every knowledge id | — | `references: [<canonical id>]`, `subject: [...]`, `job: [<receipt id>]` | `engine` |
| `case` | `K-nnnn` | — | `derived_from: [<evidence ids>]`, `subject: [<unit id>, <component>, ...]`, `job: [<receipt id>]`, `supersedes: [K-mmmm@v<k>]`, `refines: [...]` | the most restrictive source class among its fields (D7) |
| `lesson` | `K-nnnn` | — | as `case`, plus `supports`/`challenges: [<K ids>]`, `assessed_by: [<evidence or receipt ids>]` | `model` |
| `disposition` | `KD-nnnn` | `subject = K-nnnn`, `rel` = the event (D4) | `<rel>: [K-nnnn@v<k>]`, `decision: [D-nnnn]` when the Lead decided, `hold: [...]` | `engine` for policy-resolved events, `operator` for Lead or operator decisions |
| `receipt` | `KR-nnnn` | — | `produced: [K ids]`, `outbox: ["rev:<a>-<b>"]`, `subject: [<unit ids the bundle covered>]` | `engine` |

Ids come from hot counters (`counters.knowledge`, `counters.disposition`, `counters.receipt`), like `annotation` and `audit` do today. The `K-` prefix is the drafts' example prefix (shared semantics §4.2 leaves the final one open); nothing here depends on it.

### D2. Records are immutable files under `.aew/knowledge/`, git-tracked

```text
knowledge/cases/K-0017/v1.yaml                  the immutable content version (schema aew/knowledge/case/v1)
knowledge/cases/K-0017/v2.yaml                  a later version: a new record and a new entry, never a rewrite
knowledge/cases/K-0017/dispositions/0001.yaml   an append-only event about K-0017 (schema aew/knowledge/disposition/v1)
knowledge/lessons/K-0031/v1.yaml                a Lesson (K2/K3)
knowledge/references/K-0042.yaml                a K0 reference (no versions: a changed pointer is a new reference)
knowledge/receipts/KR-0009.yaml                 a capture job's receipt
```

They are written with `History.write_record` (create-if-absent, `immutable=True`, through the ADR-0001 redo record) in the same transaction that appends their entries, exactly as bundles, annotations and audit records are. `RECORD_GLOBS` gains `knowledge/**/*.yaml` so that an orphan left by a rolled-back commit is reported as a benign unreachable object (ADR-0011 Decision; probe Q4). `.aew/knowledge/` already holds `PROJECT.md` and `OPEN-QUESTIONS.md` (KC §8); it is "project durable knowledge" in KC §5.2's sense and travels with the repository. Nothing knowledge-authoritative goes under `local/`.

A capture job that yields one case, its initial disposition and its receipt writes three files: about 30 ms on Windows at the measured 9.7 ms per file. Jobs are triggered per capture opportunity (capture §7: a committed evidence receipt, a closeout, a review disposition), a few per Ticket, so this is not a hot-path cost. The investigation's O(1) archival property holds unchanged: the tail is rewritten (at most 255 entries), a segment is sealed every 256 entries, the root is constant-size.

### D3. Identity: the manifest sequence is `knowledge_event_seq`; `disposition_seq` is derived

- `knowledge_id` is the entry `id`; `version` is the entry's `version` and the record's. `K-0017@v2` names an exact version on every surface (the `@` form is already how loaded history refs are pinned: `history:<id>@<sha>`).
- The drafts' **global** `knowledge_event_seq` (shared semantics §4.2: "for incremental projections, Journal/API cursors, cache/index invalidation, and recovery") is the manifest `seq` of the entry. It is monotonic, gap-free, hash-chained and already what the derived index syncs by. The dashboard's `/knowledge` cursor and the capture worker's recovery use it unchanged.
- The **per-record** `disposition_seq` is the position of a disposition among those about its subject, in manifest order. It is stored in the disposition record for optimistic-concurrency checks (capture §18) and is checkable: the index's `about(K-0017, kinds=("disposition",))` count must equal it. A disposition whose stored `disposition_seq` does not match is an audit finding.
- **Current state is a fold** (shared semantics §4.2, §7): admission, support, conflict, lifecycle and serving eligibility of `K-0017@v2` are computed from its disposition entries in `seq` order. The fold is never written back into the content record or into a mutable file; it may be cached in the derived index (D8) and is rebuilt with it.

### D4. Disposition events are the annotation mechanism, generalised

An annotation today is "a later fact about an archived unit": a small immutable record with `subject`, `rel`, `object`, `decision`, written by the finalizer and entered with `kind: annotation`. A disposition is the same thing about a knowledge record. The `rel` vocabulary for `disposition` is the drafts': `admitted`, `held_active`, `held_dormant`, `rejected`, `superseded_proposal`, `serving_hold`, `serving_release`, `supersedes` (scoped), `refines`, `challenged`, `reassessed`, `visibility_widened`, `quarantined`, `archived`. Each disposition record carries `policy_version`, the actor (service identity, Lead generation or operator), `at`, and for an admission the serving envelope it establishes (`serving_eligibility`, source classes considered). `aew.history.index.HistoryIndex` gains `about(subject, kinds=None)`; `annotations()` becomes `about(subject, kinds=("annotation",))` (probe Q3). The engine's `Archive.annotate` keeps its name; the generalised writer is `Archive.event(ctx, kind, subject, rel, ...)` which both use.

### D5. Capture receipts are the cursor

A receipt is written for every finished capture job, including `NO_CANDIDATE` ones (capture §7: a successful outcome) and `PARTIAL` ones (capture §8). It records the job identity `(project_id, revision range, event_index)` from the outbox (ADR-0012 D3), what it produced, what it held, the extractor, template set and policy versions, and the input snapshot's hash. **The capture worker's durable cursor is derived: the highest outbox revision covered by any receipt in the manifest**, found through the index (`list(kind="receipt", limit=1)` on a fresh start, then the worker's own memory). No separate cursor record exists, so there is nothing to lose, repair or audit separately; a worker that restarts anywhere reads the last receipt and resumes from the outbox there. Idempotency is a lookup: before running a job for `(revision range, event_index)` the worker asks `linked("outbox", "rev:<a>-<b>")`; a hit is the prior receipt and is returned (capture §8 "duplicate capture of the same event returns the prior receipt").

In-flight job state (`PENDING → BUNDLE_READY → GENERATING → EVALUATING`) is **not** durable knowledge: it lives in `local/knowledge/jobs/` and is disposable. Losing it costs a replay from the pinned sources and the outbox, which capture §23 requires to be possible anyway. Accepted provider output that a disposition will later refer to is persisted **as a record** (a `lesson` with a `held_active` disposition, or a receipt's `candidates` section for rejected ones) before the job is marked complete, so "a retry does not silently regenerate a different answer" (capture §8).

Receipt rate bounds entry growth. The probe's shape, two knowledge entries per job, is what a K1 template replay would produce; with a receipt that is three. At three to five jobs per Ticket the manifest grows about ten entries per Ticket instead of about one, and the entry-count-driven costs scale accordingly: chain-only verification 0.11 ms per entry, index rebuild 0.15 ms per entry, full verification 0.32 ms per 1 KB record. At 30,000 Tickets (300,000 entries, the investigation's largest fixture scaled by ten) that is about 35 s to walk the chain, 45 s to rebuild the index and about three minutes for a full verification with records, all explicit operations (ADR-0011 invariant 13; incremental verification is proportional to new entries). Hot state does not grow (D6).

### D6. What stays hot: counters and one bounded attention list

Hot state gains only constant-size material, under ADR-0011 H1:

- `counters.knowledge`, `counters.disposition`, `counters.receipt`;
- `knowledge.pending`: a bounded list (at most 20, like `recent`) of `{id, version, kind, class, since}` for K2/K3 candidates whose admission is **judgment-bearing** and awaits the Lead or operator (capture §19 "Judgment boundary": "must appear in AEW's decisions-required/action projection with no silent default"), plus `knowledge.pending_overflow: n`. This is what `ActionProjection.decisions_required` (T1 note §3.3) reads; the full list is a `list(kind="lesson")` joined with the fold in the index;
- `knowledge.capture`: `{last_receipt: KR-nnnn, through_revision: n}`, written by the receipt's own commit, so that `status` can report capture lag (capture §8 "capture lag is visible") without reading the history (the `cold.first_at` discipline, P2c).

Everything else is derived from the manifest: how many cases exist, which are held, what a subject has, what a request may be served.

### D7. Trust: the entry's `source` is the most restrictive source class in the record

ADR-0011 invariant 14 and `history load` already label every loaded record with its `source` (`engine`, `operator`, `model`, `external`) and the fixed `TRUST_LABEL`. Knowledge entries use the same four values, mapped from the capture draft's source classes (§10): a K1 case composed only of `ENGINE_OBSERVED_*` fields is `engine`; one with any `ROLE_ATTESTED` field is `model`; any `EXTERNAL_UNTRUSTED` field makes it `external`; a Lesson is `model`; a reference is `engine`. The finer per-field classes stay in the record. **Serving eligibility is not in the entry**: it is a disposition fold (D3), so a case's eligibility can change without a new entry for the case, and the entry's trust label never claims eligibility. Loading a knowledge record into a unit (`history load K-0017@v2 --into T-0031`) uses the existing path and pin; a pack carries it as `history:K-0017@<sha>` with `reference: true`, the same way archived evidence is carried today. The context-budget rule the review asked for (REVIEW §6.3: mandatory instructions, current work and authority, current evidence, then recall) is a pack-generator rule, not a storage one, and is stated as a completion criterion so that it exists before any recall does.

### D8. The derived index gains a fold cache, `about`, `current` and FTS5

`local/history.sqlite` (never authority; rebuilt from the manifest; P3-1 locator rule) gains:

- `about(subject, kinds=None)`, D4;
- `current(knowledge_id)`: the latest version's entry plus the fold of its dispositions, `(version, seq, admission, lifecycle, serving_eligibility, holds, disposition_seq)`, computed at sync and stored in a `knowledge_state` table that is rebuilt with the index;
- `search(query, kinds, limit)` over an FTS5 table of record bodies for the knowledge kinds (probe Q6: 1.8 s to index 6,003 bodies, single-digit milliseconds per query). A hit is a locator: its id is authenticated against the chain (`History.authenticate`) and its record read and hash-checked before anything is shown, so a tampered FTS row can hide a record but never invent one. The full audit's `index.check()` compares FTS rows with the history as it compares entries today.

FTS over **evidence bodies** inside archived bundles and over decisions, which `REVIEW.md` K9 proposes as arm B (`aew history search`), is the same table with more kinds and is **not decided here**; it needs the recall draft's request-mode labelling (§8) first. This ADR only makes sure the table exists where arm B wants it.

The index at 6,006 entries with FTS was 10 MB. That is `local/`, disposable, and proportional to entries; it is reported, not bounded, here.

### D9. Who commits: policy-resolved knowledge transactions by the service identity, judgment-bearing ones by the Lead

A knowledge write is an ADR-0001 transaction: records then entries then root, in one redo record, through the existing finalizer path (`Archive.finalize` already appends "the operation's own entries" from `ctx.entries` first). Two actors append:

- **The capture service identity** (K4; capture §19) commits `knowledge.capture` transitions for what policy resolves deterministically: K0 references, approved-template K1 cases with their initial disposition, `held_active` dispositions for candidates, receipts. Its credential is a new kind in the `lead` record's schema-versioned token table, scoped to a role table that allows exactly these operations and **nothing under `work`, `invocations`, `tokens` or `lead`** (new oracle rule, below). It never holds a Lead credential and is unreachable from worker shells (M4-B's boundary, capture §19).
- **The Lead** (or the operator through the Lead's path) commits K2 and K3 admissions, rejections, scoped supersessions, serving holds and releases, visibility widenings and reassessment requests, each with a decision record (`D-nnnn`) linked from the disposition. These are judgment-bearing (`engine/primitives.py` classification), appear in `decisions_required`, and have no default (capture §19). In the T1 surface they are `knowledge_admit`, `knowledge_hold`, `knowledge_reject`, `knowledge_supersede` stage tools, with the `cli` fallback.

This introduces a non-Lead committer, the second after the harness supervisor question ADR-0012 §8 raised. It is the one authority question this ADR cannot settle and is put to the designer (Q1 below) with the recommendation that it is acceptable **because** the transaction family is closed, the oracle checks the closure on every commit, and the alternative (the Lead relays every capture result) couples capture to the Lead's session, which capture §8 forbids ("a distiller outage … must not block a Ticket from completing").

### D10. Visibility is the project in v1; the schema reserves the field

Records carry `visibility_scope: project`; entries carry nothing. Matching, duplicate hints, reverse links and FTS all operate over one project's manifest, so "most restrictive root" and "scope before limits" (shared semantics §7.7) hold trivially. `REVIEW.md` K3's position is adopted: multi-scope waits for the hosting decision (Q12) and would arrive as a record field plus an index filter, not as a second store.

### D11. Migration and compatibility

None for existing projects: the change is additive. A v2 project without knowledge has the same chain, root and index it has today. `history list` with no `--kind` lists everything newest first and will, once capture runs, show mostly knowledge entries; the surface gains `--kind` filters that accept the new kinds and `aew history list` defaults to `unit,annotation,audit,lead` with a hint, so the ADR-0011 minimum access path reads as it does today. A full audit covers knowledge records as it covers bundles (`pinned_records` returns nothing further for them; D12 adds a link check).

### D12. Audit coverage

The full audit additionally checks, per knowledge entry: the record validates against its schema; `derived_from` and `references` links resolve to a history entry, a hot record or a canonical id the project manifest knows; a disposition's subject exists at a lower `seq` and its stored `disposition_seq` matches its position; a `supersedes` link names a version that exists; a receipt's `produced` ids exist at higher or equal `seq` in the same commit. A failure is a finding and, as today, a `disposition` with `rel: audit_finding` about the damaged knowledge record (never a rewrite). These are audit-time checks (ADR-0011 invariant 13); the commit path checks only the entry's schema, the subject's existence through the index (as `_annotation_entries` does today), and the actor's role table.

## Invariants (additive to ADR-0011's fourteen)

15. **One chain.** Every durable knowledge record is pinned by an entry of the history manifest; there is no second cold root, manifest, sequence or audit for knowledge.
16. **Immutable content, appended state.** A knowledge content version is a create-if-absent record; every later fact about it is a `disposition` entry; the fold is derived and never written back.
17. **Closed knowledge transactions.** A commit by the capture service identity changes only `cold`, `counters.{knowledge,disposition,receipt}`, `knowledge.*` and `last_transition`, and appends only knowledge-kind entries. The oracle checks this on every commit (rule 28).
18. **The cursor is a receipt.** Capture progress is read from receipts in the manifest; nothing under `local/` is the only record of what was captured.
19. **Locators, not vouchers, including FTS.** Every result of the derived index, including a full-text hit and a fold, is authenticated against the chain and the record's hash before it is shown or loaded.
20. **Hot state is knowledge-independent.** Hot bytes added by knowledge are constants and one bounded list; `status`, `resume` and every active-path command read no knowledge record unless asked (H1, H2 hold with 3,000 cases as with none).

## Oracle rules (continuing ADR-0012's 24–27)

28. A `knowledge.*` transition's state delta touches no key under `work`, `invocations`, `tokens` or `lead`, and every entry it appends has a kind in {`reference`, `case`, `lesson`, `disposition`, `receipt`}.
29. Every `disposition` entry's `subject` is a `case`, `lesson` or `reference` entry at a lower `seq` (checked through the index at commit; re-checked by the audit).
30. `len(knowledge.pending) ≤ 20`, and `knowledge.pending` contains only ids whose current fold is a held K2/K3 candidate (checked by the full audit, which has the fold).

## Completion criteria

1. `history.schema.json` accepts the five kinds and `version`; existing fixtures and the 30k synthetic cold store verify unchanged (no hash changes).
2. A knowledge transaction appends a case, its disposition and a receipt in one commit; a crash at `history.after_bundle`, `history.mid_seal` and `history.after_tail` leaves the old or the new history (the existing crash matrix, run with knowledge items; no new fault points).
3. `aew history show K-0017` shows the latest version, its fold and its dispositions; `K-0017@v1` shows the exact version; `history load K-0017@v1 --into T-…` pins it and a later pack carries it as `history:K-0017@<sha>` with `reference: true` and `trust.source` from D7.
4. `unreferenced()` reports an orphan under `knowledge/`; `aew history audit --full` resolves links per D12 and records a `disposition` finding for a damaged case without rewriting it.
5. The capture worker, killed after reading the outbox and before committing its receipt, re-runs the job on restart, is answered with the prior receipt where one exists, and produces exactly one receipt per `(revision range, event_index)` (idempotency, D5).
6. H1 and H2 on the history series with 3,000 cases and 3,000 dispositions added: hot state within 1.25× and the history share within 20% as today; `status`, `checkpoint` and `resume` within 0.25 s of the no-knowledge run; `resume` opens no file under `knowledge/`.
7. Full verification with records at 6,000 knowledge entries under 5 s on the reference machine (probe: 1.9 s); index rebuild under 3 s (probe: 0.9 s); an FTS query under 50 ms including authentication of the top 20.
8. The pack generator orders sections mandatory instructions, current work and authority, current evidence, then reference history, and a test asserts a loaded knowledge record cannot displace the guardrails section (REVIEW §6.3).
9. The oracle rules 28–30 hold on every seeded walk; a seeded walk includes a service-identity commit that attempts to touch `work` and is refused.
10. The dashboard's `/history` projection shows the new kinds with their raw value (contract 0.1.2 `x-known-values`), and `/knowledge` is served from `current()` once its contract is renewed (C0).

## Test sketch

- **Unit:** `new_entry` with each kind and `version`; `about(subject)` across annotation and disposition kinds; fold from a disposition sequence (admitted → serving_hold → serving_release → superseded) gives the expected current state and `disposition_seq`; `search()` returns only authenticated ids and a tampered FTS row hides, never invents.
- **Integration (the history workload, as in the probe):** one capture commit per batch; the crash matrix at the three history fault points with knowledge items; `unreferenced()` with a `knowledge/` orphan; `check()` after altering an FTS row, a `knowledge_state` row and a disposition record on disk.
- **End to end:** a Lead session dispatches an investigator whose discovery record triggers a capture job; the service identity commits a case and receipt while the Lead holds the seat; `aew history show`, `load`, a pack with the reference, an incremental audit, `status` showing capture lag and one pending K2 candidate in `decisions_required`; the Lead admits it through the T1 `knowledge_admit` tool with a decision record; the oracle passes.
- **Scale:** the probe's Q5 as a regression series (1k, 3k, 10k cases) alongside the cold-write series.

## Alternatives considered

- **A second manifest and root for knowledge** (`knowledge/manifest/`, `cold.knowledge_root`). Rejected. It duplicates the chain, the sealing, the audit lifecycle (incremental and full, with their recorded roots and policy thresholds), the derived index and its P3-1 discipline, and the `status` reporting, and it adds a third sequence beside the manifest's and the outbox's where the drafts asked for one `knowledge_event_seq`. Its only advantage is a separate retention policy, and the drafts do not ask for one: held material stays addressable (capture §12 KH).
- **SQLite as the knowledge authority.** Rejected for the storage investigation's reasons (§4: a binary blob rewritten into the project's git history, a second commit point, no diff or repair) and because the drafts themselves classify every index as rebuildable, never authority (capture §4.4).
- **Knowledge inside the unit bundle** (capture at archival). Rejected. Capture is asynchronous to completion and must not block it (capture §8); bundles are written at the terminal transition and never rewritten; a case can draw on several units and a lesson on several cases. Archival is explicitly "not the primary capture trigger" (capture §7).
- **A separate cursor record for the capture worker.** Rejected in favour of D5: the receipt already carries the position, and a separate record is a second place to lose, repair and audit.
- **`knowledge_event_seq` as its own counter.** Rejected: the manifest `seq` already has every property asked of it, and two sequences over one chain invite the drift the drafts warn about.
- **Versions as revision objects inside one file.** Rejected: a rewrite of an existing file is exactly what ADR-0011 forbids for cold records, and per-version files give every version its own hash and entry for free.

## Not decided here

- The final knowledge id prefix (shared semantics §26) and the exact record schemas (`aew/knowledge/{case,lesson,reference,disposition,receipt}/v1`), which the M6b plan writes from the drafts' field lists (§5, §9, §11 of the shared semantics; §9–§11 of capture).
- The service identity's credential shape beyond "a kind in the `lead` token table with a role table" (K4; ADR-0005 territory).
- Arm B's FTS over evidence bodies and decisions, and the request-mode labelling that must accompany it (REVIEW K9; recall §8).
- Multi-project visibility (K3, Q12).
- Whether a `disposition` may ever be appended by a role's run bridge (`submit`), or only by the service identity and the Lead. The recommendation is never: roles produce evidence, and evidence triggers capture.
- The `/knowledge` dashboard projection's contract revision (C0 renewal; F20).

## Questions for the designer

1. **A second non-Lead committer.** Is a closed `knowledge.*` transaction family, committed by the capture service identity under oracle rule 28, acceptable under ADR-0001's authority model, or must every knowledge write go through the Lead's session? (D9; the recommendation is the former.)
2. **K0 references in the chain.** A reference is a pointer to a canonical id the project already owns; is it worth an entry and a file, or should references be derived (resolved from the manifest and decisions at read time) and never stored? The draft stores them because the drafts list "publish K0 reference" as a service capability (capture §19), but derived K0 would remove a kind.
3. **`history list` default.** Should the default listing hide knowledge kinds (D11), or show everything and let `--kind` narrow it?
4. **Hot attention.** Is a bounded `knowledge.pending` list in control state the right carrier for K2/K3 candidates awaiting judgment, or should `decisions_required` read them from the index (one derived-index read on the projection path, never on the commit path)?
5. **Receipts for `NO_CANDIDATE` jobs.** They are what makes the cursor derivable (D5) and they cost one 1 KB record and one entry each. Accept, or fold consecutive no-candidate outcomes into the next producing receipt's `outbox` range (which delays cursor advance until something is produced)?

## Checks before relying on this draft

- `git -C tree rev-parse HEAD` is `dcd43f1901b9999ec65ae6c84490e319384861df`; the probe imports from `tree/src` and `tree/tests/helpers` and widens the schema in memory only.
- The three knowledge drafts are the `extra-docs/` copies (`sha256sum -c extra-docs/SHA256SUMS`); if they have been revised, re-read shared semantics §4.2, §17 and §26 and capture §8, §18–§19 before reusing D3, D5 and D9.
- `main` may have moved: `git -C tree fetch origin && git -C tree log --oneline dcd43f1..origin/main -- src/aew/history src/aew/engine/archive_ops.py src/aew/schemas/history.schema.json`.
