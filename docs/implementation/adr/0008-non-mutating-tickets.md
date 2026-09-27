# ADR-0008 — Non-mutating Tickets: executor pinning, attempts, observation workspaces, record freshness

- **Status:** Accepted (M2). Operator-reviewed plan: `m2-ambiguity-report.md` (§2.3–§2.7).
- **Spec basis:**
  - WC §5.2–§5.4 and §6: the Investigator is read-only and records discovery; the Researcher establishes what external technology supports; the Planner proposes and the Lead accepts.
  - WC §8.1 and §21.1: read-only work may run concurrently where tool semantics are safe; the mutating cap stays 1 until M5.
  - WC §9.3–§9.4 and §4.1: discovery separates facts from hypotheses; research carries versions, constraints and uncertainties; plans carry the §4.1 contract.
  - KC §13: consequential claims are rechecked; freshness states.
  - WC §16.6 and §16.11: capability authority comes from the role grant, never from a label.
- **Nature:** An implementation of frozen semantics (M2-B1, B3, B4, B5 in the report). M1's mutating path, gate evaluator and credential scheme are unchanged.

## Decision

### Classification and executors

- `work create --non-mutating` classifies a Ticket as evidence-only. Authority comes from the executing card's archetype, never from the flag.
- The execute slot of a non-mutating Ticket accepts only `investigator`, `researcher` or `planner` cards (`NON_MUTATING_EXECUTORS`); a mutating Ticket's execute slot stays implementer-only. A non-mutating Ticket never receives a mutation workspace, an implementer or an integration.
- Operations (ROLE_OPERATIONS equals the archetype YAML, test-enforced): investigator `check.run`, `submit.discovery_record`, `context.read`; researcher `submit.research_record`, `context.read`; planner `submit.plan_proposal`, `context.read`.

### Dispatch pins the executor and its output contract

- `aew work dispatch <T> [--card C]` (Lead) moves READY → ASSIGNED through the existing `assign` rule (the M1 table test pins exactly one `via` per state pair). It creates attempt 1 and **allocates no mutation workspace**; it does not count against the serial cap.
- `unit.execution = {attempt, invocation, archetype, card {id, version, sha256}, expected_kind, selected_by, observed_commit, record}` is recorded durably. `expected_kind` is `discovery_record` (investigator), `research_record` (researcher) or `plan_proposal` (planner). `selected_by` is `operator`, `lead` (staffed or `--card`) or `workflow-default`.
- An unstaffed Ticket defaults to the `investigator` card, and that is visible: the dispatch output, the history entry, resume and the completion record all show `selected_by: workflow-default` and `expected_kind: discovery_record`. Research and planning Tickets must be staffed (`--card` at creation, `work staff`, or `work dispatch --card`).
- The `execute_record` gate is satisfied only by an ingested record of exactly `expected_kind`, produced by the current attempt's executor, bound to the accepted plan, with result `pass` and fresh per its contract.
- `work assign` keeps refusing non-mutating Tickets and points to `work dispatch` (its message still says "M2", as the M1 test requires).

### Attempts are explicit

- Each attempt owns exactly one execute invocation `I_n`, its credential `K_n` and its observation `O_n`. At most one execute invocation is active per non-mutating Ticket; execute-slot `invoke create` is refused.
- `aew work redispatch <T> --reason [--card C]` (decision `attempt_supersession`) supersedes the attempt in one commit: `I_n` → `superseded`, `K_n` revoked, `O_n` retired (the worktree is removed after the commit), the execution moved to `execution_history`, and attempt `n+1` started with a new `I`, `K`, `O` at the current authoritative commit (a new card pins a new `expected_kind`).
- Every record carries the engine-bound `attempt`. `submit` and `check run` require the invocation to be the current attempt's executor (`PERMISSION_DENIED`/`STALE_AUTHORITY` otherwise). `evidence ingest` requires state RUNNING and checks the record's kind, attempt, executor status, plan binding and observation snapshot. Late submission and replayed ingestion of an earlier attempt's record are refused; a record ingested and then superseded satisfies nothing afterwards.
- Takeover, or a handoff that does not carry the executor, interrupts it (the phase waits on the current attempt's executor in ASSIGNED/RUNNING, on the reviewer/verifier of the record in REVIEW_PENDING/VERIFY_PENDING). The attempt is over, even if a record was already submitted: `work reconcile` records an inspection of the attempt (executor, status, records submitted) and continuation is only through `work redispatch`. Success is never inferred.
- Cancellation (Ticket or cascading) and replan acceptance end the attempt through M1's single state-change path.
- An executor never starts under a stale ancestor plan binding (ADR-0007): `work redispatch` and execute-slot dispatch are refused until the Lead reconfirms or replans.

### Observation workspaces (M2-B4: stricter than the spec permits)

- Every non-mutating invocation (executors, and reviewers/verifiers of a record or of a parent) gets its own detached worktree `obs/<INV>` at the authoritative commit, recorded on the invocation (`inv.observation`), never in `unit.workspace`. Nothing is shared between agents, the authoritative worktree is never used, and another Ticket's unintegrated workspace is never visible.
- It is retired when the invocation ends and removed after the commit; orphans are pruned. A retired directory left on disk is reported as a contradiction.
- `submit` refuses with `OBSERVATION_MUTATED` (naming the changed paths) if the observation's fingerprint differs from the dispatch snapshot. External shared state (services, databases, indexes) is governed by capability grants; provider mutation declarations are M6 (Designed).
- Optional policy `non_mutating_concurrency` (default unlimited) is enforced at dispatch.

### Records and their freshness contracts (M2-B5)

| Kind | Content | Freshness |
|---|---|---|
| `discovery_record` | question, `facts[{statement, evidence[]}]`, `hypotheses[{statement, confirm_by}]`, `unresolved_questions[]`, `observed_paths[]` | **Source-bound.** CURRENT if the source is unchanged since the observed commit H, or if `observed_paths` are declared and unchanged since H (AEW's own `.aew/` excluded); STALE otherwise; UNKNOWN if H is no longer an ancestor of the authoritative commit. |
| `research_record` | question, `conclusions[]`, `subjects[{name, version, source}]`, `constraints[]`, `uncertainties[]` | **Not source-bound:** `UNKNOWN (external, as of …)`. Source changes never make it stale; only a later accepted record, or the Lead, supersedes it. |
| `plan_proposal` | §4.1 plan fields plus `affected_paths[]`; body is the plan text | Source-bound like discovery (path-scoped by `affected_paths`) until adopted. |

Identity, producer, snapshot, plan and attempt are engine-bound; submitters supply only schema-validated content. Result is `pass` (answered), `blocked` or `inconclusive`.

### Dependency satisfied is not input acceptable (M2-B3)

- An evidence edge is satisfied by upstream acceptance (DONE). That governs BLOCKED/READY only.
- **Every executor dispatch** (`work assign`, `work dispatch`, `work redispatch`, execute-slot `invoke create`) re-evaluates each consumed record against the commit the executor will work from (a live mutation workspace's base, otherwise the authoritative commit). A source-bound record that is STALE or UNKNOWN refuses the dispatch with `INPUT_STALE`, naming each input, its changed paths and the commit.
- The Lead unblocks it by **refreshing** (a new CURRENT record reaches the consumer: a new attempt of the upstream before DONE, or a new investigation plus `work depend`) or by **acknowledging** (`aew work acknowledge-input <T> --input E --from U --reason`, decision `input_acknowledgement`). An acknowledgement pins `(evidence id, sha256, commit)` and holds only for that commit; after the source moves again, a new one is required.
- External research never blocks.
- Every consuming invocation pins its inputs `{id, sha256, kind, from, freshness, basis, acknowledgement}`; they appear in its pack, and resume shows whether each would block the next dispatch.
- Records flow only through edges to non-mutating Tickets (ADR-0007).

### Lifecycle and completion

- ASSIGNED → RUNNING (Lead) → executor submits → `aew evidence ingest <T> --evidence E` (Lead; pins the record, completes the invocation) → optional REVIEW_PENDING / VERIFY_PENDING when gates apply (reviewers and verifiers are bound to the ingested record as their `subject`) → `aew work accept <T>`.
- `work accept` moves RUNNING / REVIEW_PASSED / VERIFIED → DONE through the new `accept` rule (guard `evidence_only_complete`, never available to mutating Tickets). It writes an evidence-only completion record (`work/<T>/completion.md`: the pinned execution, the accepted record, its freshness, gate statuses, the `basis` that satisfied them, and every retired attempt with its record and reason) and decision `evidence_acceptance`.
- New policy table `non_mutating_paths`: class 0 `[execute_record]`; classes 1–4 `[accepted_plan, execute_record]`. Review and verification gates apply when a project adds them or an ancestor mandates them.
- **Planner writeback:** `aew plan adopt <target> --evidence E --from P` (Lead) creates a *proposed* plan revision on any unit from an accepted `plan_proposal`, with provenance (`source_evidence`: id, sha256, source Ticket, invocation). The Lead still accepts it. A Planner never writes plans or the plan pointer.

## Consequences

- An unstaffed Ticket becomes an investigation deliberately and visibly; a research or planning Ticket cannot silently satisfy its gate with the wrong kind of record.
- A superseded, interrupted or cancelled attempt can never contribute evidence to a later one.
- A consumer is never dispatched against source its inputs no longer describe, unless the Lead recorded that it rechecked them for exactly that commit.
- Evidence: `tests/integration/test_non_mutating.py`, `tests/regression/test_m2_compositions.py`, `tests/regression/test_hierarchy_walk.py`, the oracle's M2 rules (`tests/helpers/invariants.py`), AT-11, AT-12, AT-13.

## Designed (not in M2)

- Provider mutation declarations and capability resolution (M6).
- Per-card output-contract payload schemas (ADR-0006).
- Sharing one observation between read-only invocations (WC §8.1 permits it; AEW chooses isolation).
