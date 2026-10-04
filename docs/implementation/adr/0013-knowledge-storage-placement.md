# ADR-0013 — Knowledge records live in the ADR-0011 history manifest

- **Status:** **Design frozen — proposed for operator adoption**, 2026-10-04. Not governing until accepted/merged. This version incorporates the T4 probe, finalized knowledge-semantics terminology, the developer custody review, ADR-0012's finalized oracle numbering, and design-authority corrections for cursor continuity, PARTIAL jobs, audit semantics, staged-entry validation and service-principal custody.
- **Resolves:** `REVIEW.md` §6.2 K1 ("storage is unplaced"), and ADR-0012's former open question 6 (where the capture worker's cursor lives). Touches K2 (the trigger), K3 (visibility), K4 (the service identity) only where storage forces a choice.
- **Basis:** ADR-0011 (Decision; invariants 1–14; "Not decided here"); the storage investigation §3, §4, §8.1 and its refinements R1–R8; `history/{manifest,store,index}.py` and `engine/{archive_ops,history_ops}.py` at `dcd43f1`; `history.schema.json`; the three M6 knowledge drafts (capture §4, §7–§8, §12, §18–§19, §23; shared semantics §4–§7, §13, §17, §26; recall §4, §8, §12, §24); KC §5.2, §5.3, §7.4; `ADR-0012-transaction-outbox.md` D3, D5 and §8.
- **Evidence:** `repro/knowledge_manifest_probe.py` and its output `knowledge_manifest_probe.out.txt` (run against the frozen tree through the test helpers' history workload; the schema enum widened in memory only). Numbers below are from that run on the Windows reference machine.
- **Nature:** primarily a placement decision, with the minimum authority/custody rules forced by that placement. The finalized knowledge designs' semantics (immutable content versions, append-only `knowledge_disposition` folds, admission distinct from serving, retrieval never upgrades authority) are taken as given; this ADR says where their records are written, by what principal, and how they are found, verified and recovered. Adoption of this ADR does **not** authorize production K1/K2 machinery ahead of the accepted M6b stop/go sequence.

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

Two further facts matter for the choice. The dashboard contract 0.1.2 declares `History.kind` an open value with `x-known-values` (unknown values display with a warning), so new entry kinds break no frontend. And ADR-0012 D3 makes the capture trigger a revision-number cursor over the transition log, with the job identity `(project_id, revision, event_index)`; it left the cursor's durable home to this ADR.

## Decision

**Knowledge records are entries of the ADR-0011 history manifest. There is one chain, one hot root, one audit, one derived index and one history surface for terminal work and for knowledge.** Five entry kinds are added: `reference` (K0), `case` (K1), `lesson` (K2 and K3), `knowledge_disposition` (an append-only event about an exact Knowledge version) and `capture_receipt` (a capture job's durable outcome). The shared semantics' global `knowledge_event_seq` **is** the manifest sequence number; no second sequence is introduced. It is globally monotonic and unique, but Knowledge events may have numeric gaps because non-Knowledge history entries share the same manifest sequence.

### D1. Five entry kinds, one additive schema change

`history.schema.json#/$defs/entry.kind` gains `reference`, `case`, `lesson`, `knowledge_disposition`, `capture_receipt`; `manifest.ENTRY_KINDS` follows. The entry gains one optional field, `version` (integer, at least 1). It is required by the Knowledge-record writer for `reference`, `case` and `lesson`; K0 references use `version: 1`, and a changed canonical pointer is a new Knowledge ID rather than an in-place version change. Existing chains are unaffected because old entries simply lack the additive field.

The exact external ID prefixes remain an M6b schema choice. The storage contract needs only stable Knowledge IDs plus exact version identity.

| Kind | Entry identity | `subject` / `rel` | `links` (all optional) | coarse `source` |
|---|---|---|---|---|
| `reference` | stable Knowledge ID, `version: 1` | — | `references: [<canonical id>]`, `subject: [...]`, `job: [<capture receipt id>]` | `engine` when policy-projected |
| `case` | stable Knowledge ID + version | — | `derived_from: [<evidence ids>]`, `subject: [<unit id>, <component>, ...]`, `job: [<capture receipt id>]`, `supersedes: [<K@v>]`, `refines: [...]` | coarse category derived from the record's source classes (D7) |
| `lesson` | stable Knowledge ID + version | — | as `case`, plus `supports`/`challenges: [<K@v>]`, `assessed_by: [<evidence or receipt ids>]` | normally `model` |
| `knowledge_disposition` | unique event ID | `subject = <K@v>`; `rel` = the event (D4) | relation-specific exact-version refs; `decision: [D-nnnn]` when judgment-bearing | `engine`, `model`, or `operator` according to actual actor/provenance |
| `capture_receipt` | unique receipt ID | — | `produced: [<K@v>]`, `origin_event: [<outbox event ref>]`, `subject: [...]` | `engine` |

Hot counters allocate Knowledge IDs, `knowledge_disposition` event IDs and `capture_receipt` IDs. Their concrete field/prefix names are schema details, not a second identity domain.

### D2. Records are immutable files under `.aew/knowledge/`, git-tracked

```text
knowledge/records/cases/K-0017/v1.yaml                       immutable content version
knowledge/records/cases/K-0017/v2.yaml                       later version: new record + entry, never a rewrite
knowledge/records/dispositions/KD-0001.yaml                   append-only `knowledge_disposition`
knowledge/records/lessons/K-0031/v1.yaml                     Lesson content version
knowledge/records/references/K-0042/v1.yaml                  K0 reference (`version: 1`)
knowledge/records/capture-receipts/KCR-0009.yaml             capture receipt
```

They are written with `History.write_record` (create-if-absent, `immutable=True`, through the ADR-0001 redo record) in the same transaction that appends their entries, exactly as bundles, annotations and audit records are. `RECORD_GLOBS` gains only the machine-managed `knowledge/records/**/*.yaml` subtree so that an orphan left by a rolled-back commit is reported as a benign unreachable object (ADR-0011 Decision; probe Q4). `.aew/knowledge/` already holds `PROJECT.md` and `OPEN-QUESTIONS.md` (KC §8); it is "project durable knowledge" in KC §5.2's sense and travels with the repository. Nothing knowledge-authoritative goes under `local/`.

A capture job that yields one case, its initial `knowledge_disposition` and its `capture_receipt` writes three files: about 30 ms on Windows at the measured 9.7 ms per file. Jobs are triggered per capture opportunity (capture §7: a committed evidence receipt, a closeout, a review disposition), a few per Ticket, so this is not a hot-path cost. The investigation's O(1) archival property holds unchanged: the tail is rewritten (at most 255 entries), a segment is sealed every 256 entries, the root is constant-size.

### D3. Identity: manifest `seq` is `knowledge_event_seq`; `knowledge_disposition_seq` is per version

- `knowledge_id` is stable across content versions; `version` identifies the immutable version. `K-0017@v2` is the conceptual exact-version form used throughout this ADR; the final external spelling remains a schema/surface detail.
- The global `knowledge_event_seq` is the manifest `seq` of the relevant entry. It is strictly increasing and globally ordered. **It is not gap-free when viewed only through Knowledge entries**, because terminal-work/audit/Lead entries share the same manifest sequence. Consumers must treat it as an opaque monotonic cursor, not infer missing Knowledge from numeric gaps.
- Every `knowledge_disposition` targets an **exact immutable version** (`subject = K-0017@v2` conceptually).
- The per-version `knowledge_disposition_seq` is the ordinal of `knowledge_disposition` events about that exact version in manifest order. It is stored in the event record for optimistic-concurrency/current-state checks and is validated against authenticated prior history plus any earlier staged entries in the same transaction.
- Current admission/support/conflict/lifecycle/serving state is a fold over those exact-version `knowledge_disposition` events. The fold is never written back into immutable content; it may be cached in the derived index and is always rebuildable.

### D4. `knowledge_disposition` events reuse the history-event mechanism, not Archive ownership

An annotation today is a later immutable fact about an archived unit. A `knowledge_disposition` is the corresponding later immutable fact about an exact Knowledge version. They should share a **history-domain event writer**; Knowledge must not depend on an `Archive` abstraction merely because annotations were the first consumer.

`HistoryEvents.append(...)` (name illustrative) becomes the common primitive. `Archive.annotate` may delegate to it. The index gains `about(subject, kinds=None)`; `annotations()` becomes the compatibility wrapper `about(subject, kinds=("annotation",))`.

Initial v1 `knowledge_disposition.rel` vocabulary is bounded to implemented project-scope semantics, for example:

```text
admitted
held_active
held_dormant
rejected
superseded_proposal
serving_hold
serving_release
supersedes
refines
challenged
reassessed
quarantined
archived
```

`visibility_widened` is **not** a v1 event because visibility is project-only under D10.

Each event carries `policy_version`, exact target version, actor/principal identity, `at`, and the fields required by that relation. An admission event records the serving envelope it establishes. A policy-resolved service event has coarse source `engine`; a Lead-model judgment has coarse source `model` and an attributable decision/Lead generation; a direct operator judgment has source `operator`.

Audit findings are **not** `knowledge_disposition` events. The audit writes/returns its normal audit record referencing the damaged Knowledge entry. Quarantine, if policy or judgment requires it, is a separate attributable `knowledge_disposition`.

### D5. Capture receipts provide the durable safe-resume watermark

A `capture_receipt` is written for every **terminally processed capture job**, including `NO_CANDIDATE`. A job identity binds the exact committed origin event/work/attempt/source required by Capture/Admission §8; extractor/model/prompt/template/policy versions and the pinned input snapshot are recorded in the receipt rather than inferred later.

`PARTIAL` is durable but **does not close the origin event while retryable sub-work remains**. A partial receipt records the already-persisted candidate/output identities plus enough pinned input/version information to resume idempotently. On restart the same job may continue without regenerating accepted provider output. A later terminal receipt closes that job. `RETRYABLE_FAILURE` likewise cannot advance durable capture coverage merely because local job state existed.

The capture consumer's durable recovery position is therefore **not "the highest receipt"**. It is the largest **contiguous safe prefix** of the outbox positions for which every capture opportunity at or before the boundary has a terminal receipt (or deterministic non-opportunity handling can be replayed). Out-of-order completions above a gap do not advance the safe watermark.

This is intentionally conservative: after a crash the worker may re-scan irrelevant events or already-receipted opportunities below a newer in-memory position. Idempotency makes that safe. It must never skip an uncovered opportunity.

The derived index accelerates this fold, but manifest receipts are the durable evidence. Receipt links include exact origin-event identity (conceptually `revision + event_index`, or the accepted ADR-0012 event reference), so a duplicate capture request returns the prior receipt rather than creating another outcome.

In-flight job state (`PENDING → BUNDLE_READY → GENERATING → EVALUATING`) remains operational under `local/knowledge/jobs/` and disposable. Losing it costs replay from pinned sources/outbox. Any accepted provider output that a retry must reuse is persisted before local state claims progress.

Receipt-rate costs remain bounded by actual capture work. Consecutive `NO_CANDIDATE` outcomes are **not folded away** merely to save entries: they are successful terminal outcomes and are what lets the durable coverage fold advance without ambiguity.

### D6. What stays hot: counters, bounded human attention, and a non-authoritative lag summary

Hot state gains only constant-size material under ADR-0011 H1:

- counters for Knowledge IDs, `knowledge_disposition` event IDs, and `capture_receipt` IDs;
- `knowledge.pending`: at most 20 opaque `{id, version, kind, class, since}` attention items for K2/K3 candidates whose next step is judgment-bearing, plus `knowledge.pending_overflow`;
- `knowledge.capture`: a constant-size **status summary** such as `{last_terminal_receipt, safe_through}` updated in the same commit as the receipt that advances the contiguous safe watermark.

`knowledge.pending` is retained because a pending human/Lead decision is active control-plane attention, not historical Knowledge. It contains identity/attention metadata only; content remains cold. Overflow never implies a silent default: the full pending set is queryable from authenticated history/index state.

`knowledge.capture` is explicitly **not the recovery cursor or admission authority**. Recovery recomputes/validates the safe watermark from authenticated receipts. A stale/missing hot summary may make status conservative; it must never cause an event to be skipped.

Everything else is derived from the manifest: counts, folds, subject relationships, holds, and serving eligibility.

### D7. Trust: coarse history `source` never upgrades semantic meaning

ADR-0011's `source` field remains a coarse provenance category (`engine | operator | model | external`). Knowledge records additionally retain the finer Capture/Admission source-authentication classes in the immutable record.

For a K1 Case, the coarse entry source is the most restrictive applicable history category, but **`engine` does not mean semantically correct**. `ENGINE_OBSERVED_CONTAINED` proves provenance/integrity of the observation, not oracle adequacy or the broader proposition; `ENGINE_OBSERVED_WEAK_BOUNDARY` remains explicitly distinguishable in the record and does not gain default-serving standing merely because the coarse entry source is `engine`.

A Lesson is normally coarse-source `model`; external/untrusted contributing material remains represented in the record and serving envelope. A policy-generated reference is `engine`.

Serving eligibility is never inferred from the entry's coarse source. It is a `knowledge_disposition` fold plus request-time applicability/policy.

When a Knowledge record is loaded into context, the existing history pin/hash/trust wrapper is necessary but **not sufficient**. The delivered representation must also preserve the record's fine source-authentication classes, applicability/conditions, limitations and current serving qualification. Recall must not flatten `ENGINE_OBSERVED_WEAK_BOUNDARY` into an unqualified "engine fact."

### D8. The derived index gains `about`, fold caches, and a reusable FTS substrate

`local/history.sqlite` remains disposable and non-authoritative. It gains:

- `about(subject, kinds=None)`;
- `current(knowledge_id, version?)`: exact/latest Knowledge entry plus the authenticated fold of its `knowledge_disposition` events;
- a rebuildable FTS5 substrate whose rows are locators only.

Every returned entry/result is authenticated against the manifest chain and immutable record hash before it is shown or loaded. A tampered index may omit a result until audit/rebuild, but it may not invent an authenticated one. Full audit compares derived rows with history.

**M6b sequencing remains the accepted simple-first sequence.** This ADR does not authorize production K1/K2 machinery merely because storage is now placed:

1. Arm B guarded explicit raw canonical-history search is the first recall implementation.
2. Historical replay measures K1 source-class/default-serving coverage.
3. Only if B leaves a measurable gap and the replay shows a viable substrate is the smallest Case arm C built.
4. K2 follows only if C earns its complexity.

Accordingly, the first FTS consumer may index the raw canonical-history/evidence/decision material permitted by Recall v0.3's Arm B. Knowledge bodies join the same FTS substrate only when those Knowledge kinds actually exist. Request-mode trust labelling remains a recall concern, not a storage permission.

### D9. Who commits: a project-scoped knowledge service principal for closed policy-resolved transactions

**The non-Lead committer is accepted.** AEW may authorize a distinct `knowledge_service` principal to commit a closed `knowledge.*` transaction family. This is not a second workflow authority and not a Lead substitute.

The principal is:

- bound to the project;
- explicitly enabled/revoked by operator-authorized configuration/policy;
- independent of Lead generation, so Lead handoff/takeover does not silently stop capture;
- represented as a **new credential kind** in the existing credential-verifier/custody architecture, not as a Lead credential nested inside the Lead seat;
- held only by the capture/admission service process;
- unreachable from worker shells, worker-visible environment/filesystem state, harness model context and role bridges;
- added to ADR-0009's environment-trust inventory and credential-scrubbing/verification tests;
- denied every operation outside its enumerated `knowledge.*` family.

Exact token encoding/storage/rotation remains an ADR-0005/ADR-0009 implementation amendment, but these authority semantics are frozen here.

For policy-resolved paths, the service may publish K0 references, approved-template K1 Cases, initial/hold `knowledge_disposition` events and `capture_receipt`s when the accepted Knowledge policy resolves every consequential choice. K2/K3 remain subject to the accepted judgment boundary; K3 is never automatically admitted in M6 v1.

Judgment-bearing Knowledge actions are committed through the Lead/operator authority path and linked to their decision records.

#### Runtime closure is a commit invariant

Closure is enforced by the **store commit path**, not merely by a role table, finalizer convention, or test oracle. On every `knowledge_service` commit, the commit invariant verifies:

- credential/principal kind;
- allowed `knowledge.*` operation;
- permitted hot-state delta only;
- permitted history entry kinds only;
- no mutation under work/invocation/Lead/credential authority domains;
- staged immutable record/entry relationships required by the operation.

A bug in a higher-level Knowledge operation therefore cannot use the service credential to smuggle an unrelated control-state mutation through `Session.commit`.

Role run bridges never append `knowledge_disposition` directly in v1. Roles produce evidence/records through their existing authority; committed evidence may trigger capture.

### D10. Visibility is the project in v1; the schema reserves the field

Records carry `visibility_scope: project`; entries carry nothing. Matching, duplicate hints, reverse links and FTS operate over one project's manifest, so scope-before-limit holds trivially. No v1 operation widens visibility because there is no wider scope. Multi-scope waits for Q12/later design and would arrive as record/index policy, not as a second store.

### D11. Migration and compatibility

The storage change is additive for existing projects.

`aew history list` preserves its existing operator experience by default: without an explicit Knowledge filter it lists the legacy `unit, annotation, audit, lead` kinds and prints a bounded hint that Knowledge history exists and how to request it. Knowledge-heavy capture must not drown the terminal-work history surface.

Explicit kind filters accept the new kinds; a future convenience group such as `--knowledge` may be generated over the same filter semantics. Exact `history show <knowledge-id>` remains direct.

Older engines that cannot validate the widened manifest schema must fail closed under the repository's ordinary schema/downgrade policy; "additive" does not mean an old binary may silently ignore unknown entry kinds.

### D12. Audit and commit-time relationship checks

Full audit additionally checks:

- each Knowledge record against its schema/hash;
- canonical/evidence links resolve under their owning domain;
- each `knowledge_disposition.subject` names an exact Knowledge version that existed earlier in manifest order, including an earlier staged entry in the same transaction;
- stored `knowledge_disposition_seq` matches the authenticated exact-version event order;
- supersedes/refines/support/challenge links name valid exact versions where required;
- each `capture_receipt.produced` item resolves to a Knowledge content entry written **before the receipt** in the same transaction, or to a previously authenticated idempotent output explicitly referenced by the receipt;
- terminal receipt coverage folds to a contiguous safe resume watermark with no skipped capture opportunity.

Commit-time checks may use the derived index only as a locator. Every authority-bearing existence/currentness check authenticates the located entry against the manifest/root, and same-transaction checks also inspect earlier staged entries. A stale or absent SQLite index cannot grant permission.

Audit corruption/finding output remains in the existing **audit** domain. It does not invent a `knowledge_disposition` called `audit_finding`. If a damaged Knowledge item must be quarantined, policy or an attributable Lead/operator decision appends a separate `quarantined` `knowledge_disposition`.

These expensive global checks remain off the ordinary commit path under ADR-0011 invariant 13; the commit path enforces only bounded local schema, exact subject/currentness, actor/principal authority, staged ordering and transaction-family closure.

## Invariants (additive to ADR-0011's fourteen)

15. **One chain.** Every durable Knowledge content record, `knowledge_disposition` and `capture_receipt` is pinned by the ADR-0011 history manifest; no second cold root/manifest/audit exists.
16. **Immutable content, appended state.** Content versions are create-if-absent; mutable Knowledge state is append-only `knowledge_disposition`; current state is a fold.
17. **Closed service transactions.** A `knowledge_service` commit is runtime-checked at the store commit boundary and cannot mutate workflow/Lead/invocation/credential authority domains.
18. **Safe cursor from receipts.** Recovery never advances past a gap or incomplete/PARTIAL capture job merely because a later receipt exists.
19. **Locators, not vouchers.** Index, FTS and fold-cache results authenticate against the manifest/record before use.
20. **Bounded hot footprint.** Knowledge content volume does not grow active-path hot-state cost; only counters, bounded attention and a constant-size non-authoritative capture summary are hot.
21. **Provenance is not meaning.** Coarse `source=engine` and `ENGINE_OBSERVED_*` provenance never by themselves establish semantic correctness, oracle adequacy or default serving.

## Oracle rules (continuing finalized ADR-0012 rules 24–28)

29. A `knowledge_service` commit changes only explicitly permitted Knowledge/cold/counter/last-transition fields and appends only permitted Knowledge-history entry kinds; attempted mutation of work/invocation/Lead/credential domains fails before commit.
30. Every `knowledge_disposition` targets an exact `reference`, `case` or `lesson` version that already exists in authenticated history or earlier in the same staged transaction, and its `knowledge_disposition_seq` is correct.
31. `len(knowledge.pending) <= 20`; every listed item is a current judgment-bearing pending Knowledge candidate; overflow count is non-negative and no timeout/default resolves it.
32. The receipt fold's `safe_through` is the largest contiguous terminally covered source position. An out-of-order terminal receipt above a gap and any PARTIAL receipt do not advance it.

## Completion criteria

1. `history.schema.json` accepts the five qualified kinds plus Knowledge `version`; existing history fixtures verify unchanged.
2. A policy-resolved service transaction can append a K1 Case, initial `knowledge_disposition` and terminal `capture_receipt` in one redo-protected commit; each is immutable and manifest-pinned.
3. Crash/recovery at existing history fault points leaves old-or-new valid history; service-transaction closure is rechecked at the store commit boundary.
4. Exact-version show/load preserves hash pinning **and** the fine source-authentication/applicability/limitation qualification required by D7.
5. `unreferenced()` covers only the machine-managed Knowledge-record subtree; full audit detects damaged records/links and records the audit finding without rewriting Knowledge.
6. Capture restart proves: duplicate terminal jobs return the prior receipt; PARTIAL work resumes idempotently; an out-of-order receipt cannot jump the safe watermark; `NO_CANDIDATE` closes its job and advances coverage when contiguous.
7. H1/H2 remain within their accepted bounds with thousands of Knowledge records; `status`, `checkpoint` and `resume` do not scan Knowledge files.
8. Derived-index/FTS acceptance proves locator-not-voucher behavior, rebuildability and bounded query cost. Arm B remains the first actual recall consumer.
9. Pack/reference tests prove a Knowledge load cannot displace mandatory guardrails/current authority and that weak-boundary provenance remains visibly qualified.
10. Oracle rules 29–32 pass seeded walks, including a `knowledge_service` attempt to mutate `work` and a Lead takeover while capture continues under the same project service principal.
11. `aew history list` retains legacy default readability; explicit Knowledge filters/show work; the dashboard treats unknown/new history kinds safely until `/knowledge` receives its own renewed contract.

## Test sketch

- **Unit:** all five entry kinds; exact-version `about`; `knowledge_disposition_seq`; fold semantics; safe cursor fold with gaps/out-of-order/PARTIAL/NO_CANDIDATE; source-authentication qualification; schema/downgrade behavior.
- **Store/authority:** service-principal operation-family tests at `Session.commit`; mutate every forbidden domain in turn and prove refusal; same-transaction Case → disposition → receipt ordering without relying on SQLite authority; Lead takeover leaves the project service principal valid.
- **History integration:** crash matrix with Knowledge records; `unreferenced()` under `knowledge/records/`; audit against damaged FTS/fold rows and damaged immutable records; audit finding remains audit-domain data.
- **End to end:** committed evidence triggers capture; service principal writes a policy-resolved Case/receipt while the Lead seat exists and again across Lead takeover; exact Knowledge load preserves fine trust qualification; a judgment-bearing K2/K3 candidate appears in bounded `decisions_required`; Lead/operator disposition uses the typed authority path; oracle passes.
- **Scale:** replay the probe series and keep measured results labelled measured; larger 30k-Ticket figures remain extrapolations until actually run.

## Alternatives considered

- **A second manifest and root for knowledge** (`knowledge/manifest/`, `cold.knowledge_root`). Rejected. It duplicates the chain, the sealing, the audit lifecycle (incremental and full, with their recorded roots and policy thresholds), the derived index and its P3-1 discipline, and the `status` reporting, and it adds a third sequence beside the manifest's and the outbox's where the drafts asked for one `knowledge_event_seq`. Its only advantage is a separate retention policy, and the drafts do not ask for one: held material stays addressable (capture §12 KH).
- **SQLite as the knowledge authority.** Rejected for the storage investigation's reasons (§4: a binary blob rewritten into the project's git history, a second commit point, no diff or repair) and because the drafts themselves classify every index as rebuildable, never authority (capture §4.4).
- **Knowledge inside the unit bundle** (capture at archival). Rejected. Capture is asynchronous to completion and must not block it (capture §8); bundles are written at the terminal transition and never rewritten; a case can draw on several units and a lesson on several cases. Archival is explicitly "not the primary capture trigger" (capture §7).
- **A separate authoritative cursor record for the capture worker.** Rejected in favour of D5: authenticated terminal receipts determine the safe watermark. The hot `knowledge.capture` field is only a constant-size status summary and cannot advance recovery independently.
- **`knowledge_event_seq` as its own counter.** Rejected: the manifest `seq` already has every property asked of it, and two sequences over one chain invite the drift the drafts warn about.
- **Versions as revision objects inside one file.** Rejected: a rewrite of an existing file is exactly what ADR-0011 forbids for cold records, and per-version files give every version its own hash and entry for free.

## Not decided here

- The final knowledge id prefix (shared semantics §26) and the exact record schemas (`aew/knowledge/{case,lesson,reference,knowledge-disposition,capture-receipt}/v1`), which the M6b plan writes from the drafts' field lists (§5, §9, §11 of the shared semantics; §9–§11 of capture).
- The concrete `knowledge_service` credential encoding/rotation/storage mechanism beyond the frozen project-scoped principal/custody rules in D9 (ADR-0005/ADR-0009 implementation territory).
- Arm B's FTS over evidence bodies and decisions, and the request-mode labelling that must accompany it (REVIEW K9; recall §8).
- Multi-project visibility (K3, Q12).
- Whether a future post-v1 role capability may nominate a Knowledge action remains separate; v1 role run bridges never append `knowledge_disposition` directly.
- The `/knowledge` dashboard projection's contract revision (C0 renewal; F20).

## Frozen designer decisions

1. **Closed non-Lead committer: accepted.** The project-scoped `knowledge_service` principal may commit only the runtime-enforced closed `knowledge.*` family. It is independent of Lead generation, survives Lead takeover, and receives no Lead credential.
2. **K0 references stay durable.** K0 is a reusable Knowledge identity, not merely a rediscovered pointer. A reference gets an immutable v1 record/manifest entry so capture, recall and receipts can name the same exact object. A changed canonical pointer becomes a new reference ID.
3. **`history list` preserves the legacy default.** Knowledge-heavy history is opt-in through kind/group filters or exact show; the default surface does not become a wall of capture records.
4. **Keep bounded hot attention.** `knowledge.pending` is the active decisions-required carrier because unresolved K2/K3 judgment is current control-plane attention. It stores identities only, is capped, has no silent default, and overflow is resolved through the cold/index query surface.
5. **Keep `NO_CANDIDATE` receipts.** `NO_CANDIDATE` is a successful terminal capture outcome and must advance contiguous coverage when appropriate. Do not fold it into a future producing receipt.
6. **Safe cursor is contiguous, not maximal.** Later/out-of-order receipts never skip an uncovered event; PARTIAL does not close coverage while retryable work remains.
7. **Qualified vocabulary is normative.** Use `knowledge_disposition`, `knowledge_disposition_seq` and `capture_receipt`; generic `disposition`/`receipt` names are not frozen schema terms.
8. **Audit stays audit.** Audit findings do not masquerade as Knowledge lifecycle events; quarantine is a separate attributable Knowledge disposition.
9. **Arm B remains first.** Freezing storage placement does not authorize building K1/K2 before the accepted A/B → replay → minimal-C stop/go evaluation sequence.

There are no remaining designer-level questions required to plan M6b storage. Exact schemas/prefixes, concrete service-credential encoding, Arm B request-mode details, multi-project visibility and the `/knowledge` API revision remain implementation/design work explicitly scoped above.

## Checks before relying on this ADR

- `git -C tree rev-parse HEAD` is `dcd43f1901b9999ec65ae6c84490e319384861df`; the probe imports from `tree/src` and `tree/tests/helpers` and widens the schema in memory only.
- The storage probe was run against the review's pinned Knowledge drafts. Before implementation, reconcile field names with finalized Capture/Admission v0.4, Shared Semantics v0.4 and Recall/Context v0.3; the qualified terminology and simple-first sequencing in this ADR already follow those finalized versions.
- `main` may have moved: `git -C tree fetch origin && git -C tree log --oneline dcd43f1..origin/main -- src/aew/history src/aew/engine/archive_ops.py src/aew/schemas/history.schema.json`.
