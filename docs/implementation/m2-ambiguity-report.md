# AEW M2 — Ambiguity / implementation report and plan

- **Status:** reviewed by the operator on 2026-09-27. The five operator tightenings are incorporated; the plan is approved. **Implemented** on `impl/m2-hierarchy`; the decisions are recorded in ADR-0007 and ADR-0008 (with amendments to ADR-0003 and ADR-0006), and the reviewer brief is `m2-reviewer-brief.md`.
- **Refinement found during implementation:**
  - `work dispatch` performs the existing READY → ASSIGNED transition whose table `via` is `assign`.
  - The M1 table test pins exactly one `via` per state pair, and the operation (`work assign` or `work dispatch`) is chosen by the Ticket's mutating flag.
  - The new DONE edges for non-mutating Tickets use `via: accept`.
  - Records flow only through edges to non-mutating Tickets. An edge to a Story or Epic is an acceptance dependency satisfied by its closeout, so Story-internal records are not consumed again downstream (found by AT-13; ADR-0007).
  - Executors never start under a stale ancestor plan binding: `work redispatch` and a mutating Ticket's execute-slot `invoke create` are refused too, not only READY → dispatch.
  - A parent pack labels a child as integrated before the baseline when its integrated commit is an ancestor-or-equal of the baseline, and it renders the aggregate diffstat even when empty.

## Context

M1 is merged on `main` (`7ee76c7`). It covers the serial Ticket slice, three rounds of independent review, and the CI lanes plus `assurance` gate. M2 adds:
- the Epic/Story hierarchy;
- non-mutating Tickets;
- dispatch for Investigator, Researcher and Planner;

and enough hierarchical support to import and execute the SPT remediation backlog afterwards. There is no OpenCode adapter (M3) and no M1 redesign.

**Basis:** WC v0.7 (§5, §6, §7, §8, §8.1, §9, §13, §15.1, §15.4–15.6, §16.6, §16.11, §21, §23), KC v0.4 (§7, §9, §10, §12–§18, §26, §27), SPT-R v0.2, ADRs 0001–0006 with their amendments, `review-response-2026-09-26.md`, `testing-and-ci-strategy.md`, and the code on `main`. Work is on branch `impl/m2-hierarchy` (created from `origin/main`).

**What exists today (reconstruction):**
- `work create` handles Ticket/Story/Epic records, with parent kinds (Ticket → Story|Epic, Story → Epic, Epic → none).
- Parents are created in state `OPEN`. `work transition` refuses parents ("state is derived").
- `rollup()` is advisory only. There is no closeout, cancel, promotion or move.
- Parent `policy` (`mandatory_gates`, `min_descendant_class` with a rationale) is honoured by `gates.effective_obligations`.
- Dependency edges exist between Tickets only (`mutating` or `evidence`); an evidence edge is satisfied when the upstream is DONE.
- `--non-mutating` Tickets can be recorded, but `work assign` and `integrate prepare` refuse them. That refusal is pinned by `test_m1_never_assigns_a_non_mutating_ticket` (asserts ILLEGAL_TRANSITION with "M2" in the message) and by the foundation probe.
- The investigator/researcher/planner archetypes exist with evidence kinds `discovery_record`, `research_record` and `plan_proposal`, but their only operation is `context.read`. `resolve_card` refuses them (`DISPATCHABLE_IN_M1`).
- `effective_role_plan` has no default executor for non-mutating Tickets.
- Resume, status and packs are Ticket-centric.
- Decision type `promotion` exists; no operation uses it.

**Operator review of the first draft (2026-09-27): five tightenings, all incorporated.** None is a frozen-contract change; each completes a mechanism.

| # | Tightening | Where |
|---|---|---|
| 1 | Ancestor plan binding fails closed on an ancestor's *first* acceptance too | §2.2 |
| 2 | Non-mutating redispatch supersedes the attempt explicitly: invocation, credential, observation and evidence of the old attempt are retired; at most one active execute invocation | §2.4 |
| 3 | "Dependency satisfied" ≠ "input acceptable for dispatch": STALE/UNKNOWN source-bound inputs block executor dispatch unless refreshed or acknowledged for the current commit; external research keeps `UNKNOWN (external)` semantics | §2.3, §2.5 |
| 4 | Parent review includes every child's own integrated change, independent of the parent baseline, including DONE children moved in later | §2.8 |
| 5 | Dispatch pins executor card/archetype → `expected_kind`; the `execute_record` gate requires that kind | §2.4, §2.6, §2.7 |

---

## 1. Already fully specified by the frozen contracts (implemented as written; no design question)

1. **Hierarchy** Project → Epic → Story → Ticket.
   - Phase is not a work unit (WC §7, KC §9).
   - A Ticket's parent is a Story or Epic, or it has none; a Story's parent is an Epic or none; an Epic has no parent (KC §9.1–9.3).
   - A small Ticket needs no fake Story or Epic (WC inv. 19, KC inv. 7).
2. **Review and verification are gates on work units, not synthetic Tickets.** They become a Ticket only when the work itself is substantial (WC §7).
3. **Risk is local.**
   - There is no numeric inheritance.
   - Non-waivable ancestor gates and guardrails propagate.
   - An explicit minimum-descendant floor requires a Lead rationale (WC §7.4, inv. 8–9; KC §9.5, §26).
4. **Parent state is derived from children plus parent-specific gates** and is never hand-maintained where it can be computed (WC §8; KC §9.2).
   - Only the Lead closes a Story or Epic (WC §8).
   - Children completing does not prove parent acceptance: goal-backwards and contract checks apply at the parent (WC §7.2, §8).
5. **Mutating dependencies need an accepted integrated output**, and that is unchanged. For an evidence-only dependency, "an accepted durable artifact may be sufficient" (WC §8, KC §9.5).
6. **Read-only work.**
   - Read-only investigation or research may run concurrently where tool semantics are safe (WC §8.1, §21.1).
   - The mutating cap stays at 1 until M5.
7. **Authority and write targets** (WC §5.2–5.4, §6; KC §16):
   - the Investigator is read-only and records discovery;
   - the Researcher establishes what external technology supports;
   - the Planner proposes and the Lead accepts;
   - the Lead owns the accepted-plan pointer, classification, promotion and completion.
8. **Artifact content.** Discovery records separate facts from hypotheses (WC §9.3, §4.1); research records carry versions, constraints and uncertainties (§9.4); plans carry the §4.1 contract. Every artifact is attributable to its producer, parent and evaluated snapshot (WC §9).
9. **Promotion** Ticket → Story → Epic preserves identity, evidence and reason, is a Lead decision, and never silently rewrites the record (WC §15.1, KC §9.4, §26).
10. **Resume** reconstructs the active Epic/Story/Ticket, the graph, accepted plans, open findings, guardrails and the next action (KC §15.1, §26). Status projects the canonical graph (KC §18).
11. **Packs are bounded.**
    - Investigator pack: the question, authority refs, fresh maps, allowed discovery capabilities; it writes only a discovery artifact.
    - Planner pack: the requirement, discovery/research evidence, contracts, validation requirements (KC §15.2–15.3).
12. **Capability authority** comes from the role grant (archetype ceiling plus card), never from a label (WC §16.6, §16.11).

## 2. Genuine implementation choices

These are decided here and recorded in new ADR-0007 and ADR-0008 plus amendments to ADR-0003 and ADR-0006. None of them changes normative semantics.

### 2.1 Parent (Story/Epic) state: derived, plus two Lead decisions (ADR-0007)
- **Derived value.** The parent `state` is recomputed inside every Lead commit, in the same place as BLOCKED/READY:
  - `CANCELLED` if a cancellation decision is recorded;
  - otherwise `DONE` if a closeout decision is recorded;
  - otherwise `ACCEPTANCE_PENDING` if it has children and all of them are terminal;
  - otherwise `IN_PROGRESS` if any child is non-terminal;
  - otherwise `PLANNING` (no children).
- **Legacy value.** `OPEN` stays readable in the schema and is recomputed on the first M2 commit.
- **Two roll-up vocabularies.** `rollup()` keeps its M1 vocabulary (`EMPTY`/`IN_PROGRESS`/`CHILDREN_COMPLETE`) for children. The parent state above is a separate field.
- **Child failure or blocking never changes the parent's phase.**
  - The parent carries a derived `attention` list: children in REPLAN_REQUIRED, VERIFICATION_FAILED, INTERRUPTED or ESCALATED, and a failed parent verification.
  - It also carries a derived `blocked` flag, set when every non-terminal descendant is BLOCKED.
  - A child failure never cancels or closes the parent.
- **Closeout: `aew work close <S|E> --reason`** (Lead; decision `closeout`). It requires:
  - state ACCEPTANCE_PENDING and at least one DONE child;
  - every parent gate CURRENT (§2.6);
  - required parent-level findings resolved or waived.

  It writes `work/<id>/closeout.md` listing every child, each child's completion record hash, cancelled children with their decisions, and the parent evidence.
- **Cancellation: `aew work cancel <S|E> --reason`** (Lead; decision `cancellation`) cancels all non-terminal descendants atomically.
  - Workspaces are released and credentials revoked through M1's single state-change path.
  - It is refused while any descendant is `publishing` (the M1 rule).
  - DONE children stay DONE.
  - `work transition <parent>` stays refused (the M1 test is unchanged).
- **Terminal parents are frozen.** A child can never be created under, or moved into, a DONE or CANCELLED parent. A new unit is created instead; there is no reopen.

### 2.2 Replanning, moves, promotion, and hierarchy provenance (ADR-0007)
- **Parents are planned like Tickets.**
  - Plan revisions, `plan propose/accept` and the "supersedes needs a reason" rule are reused.
  - A parent plan may be accepted in any non-terminal parent state.
  - A parent plan may also be adopted from Planner evidence (§2.4).
- **Plans are bound to their ancestors' plans, failing closed.**
  - When a unit's plan is accepted, it records `ancestor_plans` for **every** ancestor: either `{revision, sha256}` or `none` if that ancestor had no accepted plan yet.
  - **Any** later change to an ancestor's accepted plan makes the unit's `accepted_plan` gate **STALE**, so forward transitions fail closed. This includes an ancestor's **first** acceptance (none → v1), because a newly accepted ancestor plan may change the intent the descendant was planned under.
  - Recovery is either:
    - `aew plan reconfirm <id> --reason` (decision `plan_reconfirmation`; rebinds to the current ancestor plans), or
    - a new plan revision.
  - Children are never mutated silently. A unit with no accepted plan yet binds when its plan is accepted.
- **Moving a unit: `aew work move <id> --parent <P|none> --reason`** (decision `hierarchy_change`).
  - Kind rules, cycle checks and the terminal-parent refusal apply.
  - The move appends to `parent_history` in control state and marks the moved subtree's plan bindings stale.
  - The immutable record keeps its creation-time `parent`, which is creation provenance. Control state holds the current structure.
- **Promotion: `aew work promote <T|S> --to story|epic --title … --reason …`** (decision `promotion`).
  - It creates the new unit (record `promoted_from`, class ≥ the original's) under the nearest valid ancestor.
  - The original is moved under the new unit, keeping its identity, evidence and history.
  - A promoted Ticket goes to REPLAN_REQUIRED, because its scope no longer fits its plan.
  - Promotion is refused from DONE, CANCELLED, VERIFICATION_FAILED (classify first) or `publishing`.

### 2.3 Dependencies (ADR-0007)
- **Edges may point at Tickets, Stories or Epics**, and may be declared on any unit.
- **Satisfaction by upstream kind:**
  - a Ticket upstream is satisfied as in M1;
  - a parent upstream is satisfied when the parent is `DONE` (closed after its gates);
  - a `mutating` edge to a parent additionally requires every DONE mutating descendant's integrated commit to be an ancestor of the downstream base.
- **Inherited edges.** A unit is also blocked by every edge declared on its ancestors, so Story S2 → S1 blocks all of S2's Tickets.
- **Cycles are refused at creation and on edits.** The check covers direct edges, inherited edges and hierarchy: no edge to one's own ancestor or descendant.
- **Editing edges: `aew work depend <id> --add X[:kind] | --remove X --reason`** (decision `dependency_change`).
  - Allowed only while every affected Ticket is BLOCKED, READY or REPLAN_REQUIRED.
  - Otherwise the Lead replans first.
- **Dependency satisfied ≠ input acceptable for dispatch.**
  - An evidence edge is satisfied by upstream acceptance (DONE). That governs BLOCKED/READY only (WC "may be sufficient").
  - Separately, **every executor dispatch** checks each consumed input's freshness (§2.5) against the authoritative commit A it will observe or be based on. Executor dispatch covers `work assign` (mutating), `work dispatch`, `work redispatch`, and execute-slot `invoke create`.
- **The rule for source-bound inputs** (`discovery_record`, `plan_proposal`):
  - An input that is **STALE, or UNKNOWN** (for example H no longer an ancestor of A), **blocks the dispatch** with `INPUT_STALE`, naming each input and the paths that changed.
  - The Lead unblocks it in one of two ways:
    - **refresh:** a new CURRENT accepted record reaches the consumer, either through a new attempt of the upstream Ticket before its DONE, or through a new investigation Ticket plus an edge change (`work depend`, a decision);
    - **acknowledge:** `aew work acknowledge-input <T> --input <E> --reason` (decision `input_acknowledgement`).
  - An acknowledgement pins exactly `(evidence id, sha256, authoritative commit A)` and is valid only while A is unchanged. If the source moves again, a new acknowledgement is required. This makes "consequential claims must be rechecked" (KC §13) an enforced step, not guidance.
- **External research** (`research_record`, not source-bound) never blocks. It is shown as `UNKNOWN (external, as of …)`.
- **Every consuming invocation pins its inputs**: `{id, sha256, kind, freshness, acknowledgement?}`. They appear in its pack and in resume.
- **Consumption by a mutating Ticket.** A mutating Ticket consumes non-mutating output only through such an edge.
- **Non-mutating downstream of a mutating upstream.** It uses the M1 mutating-edge rule, with the base set to the authoritative commit it will observe.
- **Priorities.** SPT P0/P1/P2 priorities stay in `external_refs` and body; AEW adds no priority concept.

### 2.4 The non-mutating execution path (ADR-0008; ADR-0003 amendment)
- **Classification is explicit.** `work create --non-mutating` sets it. Authority comes from the executing card's archetype, never from the flag.
  - The execute slot of a non-mutating Ticket accepts only `investigator`, `researcher` or `planner` cards.
  - A mutating Ticket's execute slot stays `implementer`-only.
  - Substantial review or audit work ("security audit", "performance characterization") is a non-mutating Ticket run by an investigator-based card. Routine review and verification remain gates (WC §7).
- **Dispatch: `aew work dispatch <T> [--card C]`** (Lead) moves READY → ASSIGNED (the `assign` transition, without a mutation workspace).
  - It creates attempt `n` with an executor invocation and **allocates no mutation workspace**.
  - It is not counted by the serial cap and never gets an implementer.
  - `work assign` keeps refusing non-mutating Tickets; its message points to `work dispatch` and still says "M2", so the M1 test is unchanged.
- **Executor pinning (output contract).** Dispatch durably records `unit.execution = {attempt, card {id, version, sha256}, archetype, expected_kind, selected_by}`. `expected_kind` is `discovery_record` for investigator, `research_record` for researcher and `plan_proposal` for planner.
  - The Ticket's `execute_record` gate (formerly "evidence_record") is satisfied only by a record of **exactly that kind** from **this attempt's** executor.
  - `selected_by` is `operator`, `lead` (staffed or `--card`) or `workflow-default`. A default executor is visible in the dispatch output, history, resume and the completion record, so an unstaffed Ticket becomes an investigation deliberately and visibly, never accidentally.
  - `work create --non-mutating --card …` pins the intended executor at creation.
- **Attempts are explicit** (applying the M1 review lesson to observation work):
  - Each attempt owns exactly one execute invocation `I_n`, its credential `K_n` and its observation `O_n`.
  - **At most one active execute invocation per non-mutating Ticket**: execute-slot `invoke create` refuses while one is active, as in M1.
  - **`aew work redispatch <T> --reason`** (Lead; decision `attempt_supersession`) supersedes the attempt atomically:
    - `I_n` → `superseded`;
    - `K_n` revoked;
    - `O_n` retired (the worktree is removed after commit);
    - every record from attempt `n` becomes historical: it cannot be ingested and cannot satisfy any gate of the current attempt.
    - Attempt `n+1` then gets a new `I`, `K` and `O` at the current authoritative commit.
  - REPLAN, cancellation, takeover and handoff (when not carried) also end the attempt and revoke its credentials, reusing M1's single state-change path.
  - Evidence records carry the engine-bound `attempt`. `submit`, `check run` and `evidence ingest` all require the invocation to be the current attempt's executor, and ingest also checks the record's attempt, observation and plan binding. Late submission or ingest replay of an earlier attempt's record is refused.
- **Observation workspaces.**
  - Every non-mutating invocation gets its own detached worktree at the authoritative commit H (`obs-<INV>`), stored on the invocation (`inv.observation`), never in `unit.workspace`.
  - Nothing is shared between agents, the authoritative worktree is never used, and another Ticket's unintegrated workspace is never visible.
  - It is removed after the invocation ends; orphans are pruned and reported.
- **Accidental mutation is detected.**
  - `check run` compares the fingerprint before and after, as in M1.
  - `submit` refuses (`OBSERVATION_MUTATED`, naming the paths) if the observation fingerprint differs from the dispatch snapshot.
  - External shared state (services, databases, indexes) is governed by capability grants: authority-sensitive capabilities are rejected by the archetype ceiling now, and provider mutation declarations arrive in M6 (Designed).
- **Operations** (ROLE_OPERATIONS and the archetype YAML stay equal):
  - investigator: `check.run`, `submit.discovery_record`, `context.read`;
  - researcher: `submit.research_record`, `context.read`;
  - planner: `submit.plan_proposal`, `context.read`.
- **Lifecycle:** ASSIGNED → RUNNING (Lead) → the executor submits → `aew evidence ingest <T> --evidence E` (Lead).
  - Ingest pins the record, checks it is bound to the current attempt, observation and accepted plan, and completes the invocation.
  - The Ticket then goes RUNNING → REVIEW_PENDING/VERIFY_PENDING if review or verification gates apply.
  - Finally `aew work accept <T>` moves RUNNING/REVIEW_PASSED/VERIFIED → **DONE** (new `via: accept`; guard `evidence_only_complete`; never available to mutating Tickets). It writes an evidence-only completion record and decision `evidence_acceptance`.
- **Interruption.** Takeover, or a handoff that does not carry the executor, interrupts it through generalized `PHASE_DRIVERS` (execute archetype, observation scope). That **ends the attempt**, so its records are historical even if one was submitted before the interruption.
  - The Ticket is reconciled with M1 `work reconcile` (never forward, with an inspection record).
  - It continues only through `work redispatch`, which starts attempt `n+1`. Success is never inferred.
  - An executor carried across a cooperative handoff keeps its attempt.
- **Optional policy `non_mutating_concurrency`** (default unlimited) is enforced at dispatch.
- **Planner writeback: `aew plan adopt <target> --evidence E`** (Lead) creates a *proposed* plan revision on any target unit from an accepted `plan_proposal`, with provenance (source Ticket, invocation, evidence sha256). The Lead still accepts it. The Planner never writes plans or the plan pointer.

### 2.5 Evidence kinds and their freshness contracts (ADR-0008)

The engine binds identity, producer, snapshot and plan, exactly as in M1. Submitters supply only schema-validated content. Each record kind has its own freshness contract, deliberately different from implementation evidence:

| Kind | Content (schema) | Bound to | Freshness |
|---|---|---|---|
| `discovery_record` | `facts[{statement, evidence[]}]`, `hypotheses[{statement, confirm_by}]`, `unresolved_questions[]`, `observed_paths[]`; result `pass/blocked/inconclusive` | Observation snapshot (H, `git-tree:tree(H)`) | **Source-bound.** CURRENT if the authoritative tree still equals `tree(H)`, or if `observed_paths` are declared and unchanged since H. STALE otherwise. UNKNOWN if H is no longer an ancestor. |
| `research_record` | `conclusions[]`, `subjects[{name, version, source}]`, `constraints[]`, `uncertainties[]` | Observation snapshot (context only) | **Not source-bound.** Reported as `UNKNOWN (external, as of <date>/<versions>)`. Source changes never make it stale; only a later accepted record, or the Lead, supersedes it. |
| `plan_proposal` | §4.1 plan fields + `affected_paths[]`, body = plan text | Observation snapshot | Source-bound, like discovery (path-scoped by `affected_paths`), until adopted. After acceptance it is accepted intent, and contradicting evidence leads to REPLAN. |
| Implementation / review / verification (M1) | Unchanged | Workspace/candidate snapshot | Exact fingerprint equality, unchanged. |

- **Freshness has two enforcement points:**
  1. a non-mutating Ticket's own `execute_record` gate before DONE;
  2. **every executor dispatch that consumes the record** (§2.3). A STALE or UNKNOWN source-bound input blocks dispatch unless it is refreshed or acknowledged for the current authoritative commit.

  External research is never blocked by source changes.

### 2.6 Gates for non-mutating Tickets and for parents (ADR-0008 / ADR-0007)
- **New policy sections** in `gates.yaml` (schema v1 extended, with defaults, and projects may override): `non_mutating_paths` and `parent_paths`, per class.
- **Non-mutating defaults:**
  - class 0: `[execute_record]`;
  - classes 1–4: `[accepted_plan, execute_record]`.
- **Parent defaults:**
  - class 0: `[children_complete]`;
  - classes 1–4: `[accepted_plan, children_complete, review_r1, verification_goal_backwards, verification_contract]`.
- **Effective obligations** are still `local path + inherited non-waivable ancestor gates + floor + role-plan cards`, all computed by the existing `effective_obligations` with the path table selected by unit type.
  - A unit's own `mandatory_gates` apply to its **descendants** (WC §7.4 literal), not to itself.
  - Ancestor gates reach non-mutating Tickets and sub-parents too.
- **A separate evaluator** (`gates.evaluate_evidence_unit`) handles non-mutating Tickets and parents; M1's `evaluate` is untouched.
  - `execute_record`: an ingested record whose kind equals the attempt's pinned `expected_kind`, produced by the current attempt's executor, bound to the current plan, with result `pass` and fresh per its contract.
  - Review/verify gates on a non-mutating Ticket: reports whose subject is the currently ingested record (`inv.subject = {id, sha256}`).
  - Parent review/verify gates: reports bound to the **parent snapshot** `git-tree:tree(A)+children:<digest of child ids, states and completion-record hashes>`, where A is the authoritative commit. Adding a child or integrating anything makes them STALE.
  - `children_complete`: every child terminal and at least one DONE.
- **Parent review and verification.**
  - `invoke create <S> --role reviewer|verifier` works in ACCEPTANCE_PENDING (scope `parent`, observation at the current A).
  - `review/verify ingest <S>` records evidence and findings on the parent.
  - A failed parent verification requires `verify classify <S>` (decision) before another parent verifier is dispatched. It prescribes the next step: add a remediation child, a new parent plan, or re-verification once the environment is fixed.

### 2.7 Roles (ADR-0006 amendment)
- Investigator, researcher and planner become dispatchable (`DISPATCHABLE_IN_M1` → per-slot rules).
- New generic built-in cards `investigator`, `researcher` and `planner` become the archetype `default_card`s.
- The default executor of an unstaffed non-mutating Ticket is `investigator`. The dispatch records it as `selected_by: workflow-default` and pins `expected_kind: discovery_record` (§2.4), so it is an explicit, visible choice. Research or planning Tickets must be staffed (`--card` at create, `work staff`, or `work dispatch --card`).
- Selection precedence, `use_when` (advisory), operator pins (execute-slot enforcement), forbids and escalation checks are all unchanged. Specialist stays a card modifier.
- No new archetype.

### 2.8 Context, resume, status, handoff (ADR-0007)
- **Packs gain a hierarchy section.**
  - It contains the ancestor chain (id, title, objective, acceptance criteria, accepted plan revision) and the inherited non-waivable gates and floor.
  - It never includes siblings.
  - Upstream artifacts appear only through explicit dependency edges (pinned, with freshness).
- **New pack types.** Investigator, researcher and planner packs and output templates follow KC §15.2–15.3. Each includes the pinned `expected_kind` and the attempt number.
- **Parent reviewer and verifier packs cover every child's output, whatever the baseline.**
  - They contain the parent acceptance criteria and every child with its completion record (id and sha256).
  - Each DONE mutating child gets **its own integrated change**: `git diff <integrated>^1 <integrated>` from its completion record, with the commit ids.
  - A child integrated before the parent's baseline (for example a DONE Ticket later moved in with `work move`) is included and labelled as such.
  - Each DONE non-mutating child contributes its accepted record.
  - The aggregate diff `baseline_commit..A` is **supplementary context**, never the only view of the children's work.
  - The verifier pack carries the per-child diffstats.
  - The parent snapshot's children digest (completion-record hashes) is the identity that ties the review to exactly these outputs.
  - `work move` of a DONE child into an active parent is allowed and recorded (`hierarchy_change`). It changes the digest, so any existing parent review or verification becomes STALE.
- **Packs stay deterministic** and record their sources with sha256 values.
- **Resume, status, CURRENT and handoff show the Epic → Story → Ticket tree.** They include:
  - derived parent state, attention and blocked flags;
  - accepted plans with their bindings;
  - open findings, including parent-level findings;
  - inputs that block dispatch (`INPUT_STALE`), and acknowledgements with the commit they cover;
  - each non-mutating Ticket's current attempt and pinned executor/`expected_kind`;
  - per-parent next actions (for example "all children terminal: dispatch Story review/verification, then `aew work close`");
  - contradictions: stale plan bindings, orphan observation worktrees, and a parent state that disagrees with its derivation.
- `aew work tree [<id>]` renders the tree.

## 3. Frozen-contract wording tensions (resolved without new semantics)

| ID | Tension | Resolution |
|---|---|---|
| M2-B1 | WC §8's state model and §7.5 minimum paths are written for mutating work. A non-mutating Ticket's path to DONE without integration is implied ("a *mutating* Ticket reaches DONE only after integration") but not drawn. | `dispatch` + `accept` transitions, policy `non_mutating_paths` (§2.4, §2.6). |
| M2-B2 | "Parent state derived" versus "only the Lead may close" and Lead cancellation. | Derived phase plus recorded closeout/cancellation decisions (§2.1). |
| M2-B3 | Evidence dependency: "an accepted durable artifact **may** be sufficient". | Acceptance satisfies the *edge* (BLOCKED/READY). *Dispatch* separately requires source-bound inputs to be CURRENT, or explicitly acknowledged for the current authoritative commit. External research is exempt (§2.3). |
| M2-B4 | WC §8.1 lets read-only work *share* a worktree "when … safe". | We choose not to share: one observation worktree per invocation, which is stricter and permitted. |
| M2-B5 | Freshness states (KC §13) are defined for derived knowledge, not for research evidence. | Per-kind contracts (§2.5). Research is `UNKNOWN (external)` rather than an overclaimed CURRENT. |
| M2-B6 | WC §7.4's example scopes a mandatory ancestor gate to "affected child Tickets". | Applied to all descendants, including non-mutating Tickets and sub-parents (conservative). The gate only adds ceremony. |

## 4. Operator escalation: none required

- **No frozen-contract contradiction.**
- **No missing authority boundary.** Promotion, moves, dependency edits, plan adoption, closeout and cancellation are Lead-only, per KC §16. The Planner, Investigator and Researcher only submit evidence.
- **No unsafe spec transition.** Every new transition is Lead-initiated or mechanical, and non-mutating Tickets can never reach integration.
- **No unsatisfiable invariant.**
- **Carried-over open items that do not block M2:**
  - lease-expiry takeover (A2);
  - the Ghidra environment (C3);
  - workbench capability resolution and provider mutation declarations (M6);
  - card `restrict.paths` (Designed);
  - plan-driven child materialization (Designed).

## 5. M1 compatibility constraints (must stay byte-for-byte green)

- The mutating-Ticket path is untouched: M1 `gates.evaluate`, assignment, workspaces, snapshots, integration saga, the serial cap and the credential scheme.
- These M1 tests and probes keep passing **unchanged**:
  - `test_m1_never_assigns_a_non_mutating_ticket` (refusal message still contains "M2");
  - the foundation probe;
  - `test_story_rollup_and_inherited_policy_representation` (`work transition <story>` → exit 5; rollup keys and vocabulary);
  - all 22 reviewer probes, the M1 walk (default seeds, same paths) and the whole regression and acceptance suite.
- Schema changes are additive:
  - new enum values: parent states, evidence kinds, decision types, invocation scopes `observation`/`parent`, verification scope `parent`;
  - new optional fields.
  - `OPEN` remains valid.

## 6. Implementation steps (branch `impl/m2-hierarchy`; one commit or more per step; tests in the same commit)

0. **Report** → `docs/implementation/m2-ambiguity-report.md` (this document) and draft ADR-0007/0008.
1. **Schemas and records.**
   - Extend these schemas:
     - work-unit: `promoted_from`;
     - control:
       - parent state, attention, closeout, cancellation, `parent_history`, `baseline_commit`;
       - `ancestor_plans`, including `none` entries;
       - `unit.execution` (attempt, card, archetype, expected_kind, selected_by);
       - `input_acknowledgements`;
       - invocation `observation`, `subject`, `inputs`, `attempt`, and status `superseded`;
     - evidence: the three kinds with their sections, an engine-bound `attempt`, and verification scope `parent`;
     - decision: new types `closeout`, `evidence_acceptance`, `hierarchy_change`, `dependency_change`, `plan_reconfirmation`, `input_acknowledgement`, `attempt_supersession`;
     - gates: `non_mutating_paths`, `parent_paths`, `non_mutating_concurrency`;
     - plan: `source_evidence`.
   - `DEFAULT_GATES` gains the new defaults.
   - Unit tests.
2. **Hierarchy core** (`work_ops.py`, `dependencies.py`, new `hierarchy.py` pure module):
   - validation and cycles (parent kinds, terminal parents);
   - derived parent state/attention/blocked, recomputed in `before_commit`;
   - parent and inherited dependency edges;
   - `work cancel` (cascade), `work move`, `work promote`, `work depend`, `work tree`.
3. **Non-mutating path** (`workspace/worktrees.py` observation allocate/remove; `workspace_ops.py`; `evidence_ops.py`; `authority.py` + archetype YAML; `roles/__init__.py` + three built-in cards; `role_ops.py` slot rules; `transitions.py` `dispatch`/`accept`; `lead_ops.py` PHASE_DRIVERS):
   - `work dispatch` with executor pinning (`unit.execution`, `expected_kind`, `selected_by`);
   - **attempt lifecycle:** `work redispatch` (supersede, revoke, retire, historical), one active execute invocation per attempt, attempt-bound `submit`/`check run`/`ingest`;
   - `evidence ingest`, `work accept` and the evidence-only completion record;
   - `submit` for the new kinds with the mutation check;
   - `_invocation_workspace` for observation scope;
   - `work assign` refusal text.
4. **Evidence gates and freshness** (`gates.py` `evaluate_evidence_unit`, a freshness module):
   - `execute_record`, matched to the pinned `expected_kind` and the current attempt;
   - subject-bound review/verify for non-mutating Tickets;
   - **dispatch input check** (`INPUT_STALE`) at `work assign`, `work dispatch`, `work redispatch` and execute-slot `invoke create`, plus `work acknowledge-input` (pins evidence + sha256 + authoritative commit);
   - pinned inputs on invocations;
   - `plan adopt`;
   - **fail-closed ancestor plan bindings** (including `none` → first acceptance) and `plan reconfirm`.
5. **Parent gates and closeout:**
   - parent snapshot (tree + children digest);
   - parent-scope reviewer/verifier dispatch and ingest, and parent classification;
   - `children_complete`;
   - `work close` + `closeout.md`;
   - **per-child integrated-change sections** in parent packs, independent of `baseline_commit`.
6. **Context packs** (`knowledge/context.py`, `context_ops.py`): the hierarchy section, the three new role packs with launch contracts and templates, parent review/verify packs. Determinism tests.
7. **Resume, status, CURRENT, handoff** (`resume_ops.py`, `status_ops.py`, `knowledge/render.py`): the tree, next actions and contradictions. Golden tests.
8. **Oracle, compositions, walk.**
   - `tests/helpers/invariants.py` gains hierarchy and non-mutating invariants:
     - a non-mutating Ticket never has a workspace, integration or implementer;
     - DONE has an ingested record and a completion record;
     - a parent DONE/CANCELLED has all descendants terminal and no active invocations below it;
     - the derived parent state is consistent;
     - the hierarchy and dependency graphs are acyclic;
     - discovery, research and plan evidence comes only from the matching archetype on an observation snapshot;
     - **at most one active execute invocation per non-mutating Ticket, and none from a superseded attempt**;
     - an ingested execute record's kind equals its attempt's pinned `expected_kind`, and its attempt is current (or it is the accepted record of a DONE Ticket);
     - no evidence postdates its credential's revocation (extends the M1 rule to observation invocations);
     - every executor invocation's source-bound inputs were CURRENT or acknowledged for the commit it was dispatched against;
     - every plan-bound unit that advanced did so with current ancestor bindings.
   - New adversarial compositions.
   - A **separate** seeded walk `tests/regression/test_hierarchy_walk.py` (`exploratory`, with its own knobs) mixes parents, non-mutating/mutating concurrency, promotions, moves, cancellations, stale research via integration, handoff and takeover. The M1 walk is untouched.
   - `aewflow.py` gains scripted Investigator/Researcher/Planner drivers.
9. **Acceptance scenarios** (CLI, scripted roles; `acceptance(id)`):
   - AT-8: Story lifecycle to closeout; children complete ≠ accepted.
   - AT-9: KC §26 parent risk policy propagation (full scenario).
   - AT-10: KC §26 Ticket promotion.
   - AT-11: KC §26 fresh-session reconstruction with an active Epic hierarchy, plus takeover interrupting non-mutating work.
   - AT-12: non-mutating concurrency plus read-only authority denials.
   - AT-13: the representative backlog fixture (Epic → Stories → investigate [non-mutating] / implement [mutating] / verify via gate or evidence Ticket), with generic content and no SPT concepts in core.
10. **Documentation.**
    - ADR-0007 (hierarchy), ADR-0008 (non-mutating path, observation workspaces, evidence freshness), and amendments to ADR-0003 (transitions) and ADR-0006 (dispatchable archetypes, cards).
    - `acceptance.md`, `implementation-status.md` (Implemented/Staged/Designed), `quickstart.md`, and the testing strategy doc if lanes or shards change.
    - **Reviewer brief** `docs/implementation/m2-reviewer-brief.md`, focused on the hierarchy and non-mutating invariants.
    - Memory update.

## 7. Test coverage mapped to the M2 brief

| Brief item | Where |
|---|---|
| Construction, invalid hierarchy, cycles | `tests/unit/test_hierarchy.py`, `tests/integration/test_hierarchy.py` |
| Independent risk classification, inherited policy, floor | AT-9, unit |
| Aggregate completion; parent DONE only after descendants and gates | AT-8, integration, oracle |
| Child blocking/failure → attention; parent never auto-closed | integration, compositions |
| Parent cancellation (cascade, publishing guard), replanning (stale bindings, reconfirm) | integration, compositions |
| **Ancestor first-acceptance hole**: a Ticket plan is accepted while its Story has no plan, then the Story's first plan is accepted → the Ticket's `accepted_plan` is STALE, forward transitions are refused, and `plan reconfirm` restores it | compositions (deterministic regression) |
| **Attempt supersession (M1-review-style sequence)**: attempt 1 (I1/K1/O1) submits E1 → `work redispatch` → I1 superseded, K1 rejected for `submit`/`check run` (STALE_AUTHORITY), O1 removed, ingesting E1 refused (earlier attempt), late submit with K1 refused, replaying E1 refused → attempt 2 (I2/K2/O2); only E2 satisfies `execute_record`; the oracle holds after every step | compositions + hierarchy walk (`late_submit`/`replay` ops across attempts) |
| **Stale source-bound input**: an investigation observes H → DONE → an integration changes observed paths → dispatching the consuming implementation Ticket is refused with `INPUT_STALE`; `work acknowledge-input` allows exactly that commit; after another source change it is refused again; refreshing through a new CURRENT record works; external research never blocks | compositions + integration |
| **Parent review completeness**: a DONE Ticket integrated before a Story's baseline is moved into the Story → the parent reviewer pack contains that child's own integrated diff; an earlier parent review becomes STALE (children digest changed) | integration |
| **Executor output contract**: an unstaffed Ticket dispatches as `investigator` (`selected_by: workflow-default`, `expected_kind: discovery_record`, visible in resume/completion); a Ticket staffed `researcher` refuses a `discovery_record` for `execute_record`; changing the executor between attempts pins a new `expected_kind` | integration |
| Resume after session destruction with an active hierarchy | AT-11, golden resume |
| Non-mutating dispatch, multiple simultaneous non-mutating Tickets, mutating/non-mutating concurrency | AT-12, `tests/integration/test_non_mutating.py` |
| Authority denial for read-only roles (wrong kinds, control ops, observation mutation) | AT-12, integration |
| Evidence dependency and freshness (discovery stale after integration; research external) | integration, compositions |
| Handoff/takeover interaction | AT-11, compositions, hierarchy walk |
| Role plans (non-mutating execute slot, pins, forbids, default card) | integration |
| Stale evidence interaction (discovery `execute_record` STALE before accept; consumer dispatch blocked until refreshed or acknowledged; M1 implementation evidence unchanged) | compositions |
| Adversarial compositions | `tests/regression/test_m2_compositions.py` + hierarchy walk + oracle |

New files go in the existing lane directories. No lane rules change, and `tests/durations.json` is refreshed from CI.

## 8. Completion criteria and verification

- **Local Windows:**
  - plain `pytest -q` passes in full;
  - `pytest -n auto -m "not serial"` plus `--lane serial` passes;
  - the lane reports pass `check_assurance.py`.
- **CI** on the PR is green on both OSes (`assurance`). The nightly runs via `workflow_dispatch` after merge, including the new walk's extended budget.
- **M1 acceptance and regression** are green, with no M1 test file changed except additive oracle rules in `tests/helpers/invariants.py`, reviewed.
- **Reviewer probes:** the three original files run unchanged, 22/22 (exec-bit probe on Linux).
- **Frozen docs:** no diff, and the spec pin is green.
- **Manual smoke:** in a scratch copy of the sample project, run init → Epic/Story → investigation (dispatch, submit, ingest, accept) → an implementation Ticket consuming it → Story review/verify → close → resume. Then the SPT-shaped fixture renders correctly in `aew work tree`.
- **Deliverables:** the reviewer brief and the status table distinguishing Implemented, Staged and Designed. M3 (OpenCode) is not started.

## 9. Out of scope / Designed

- Plan-driven child materialization.
- Provider mutation declarations and capability resolution (M6).
- Mutating concurrency > 1 (M5).
- Card `restrict.paths`.
- Priority/milestone concepts (KC §28.10).
- Importing the real SPT backlog (after M2 is accepted).
