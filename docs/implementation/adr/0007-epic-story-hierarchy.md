# ADR-0007 — Epic/Story hierarchy: derived parent state, closeout, structure changes, dependencies

- **Status:** Accepted (M2). Operator-reviewed plan: `m2-ambiguity-report.md` (§2.1–§2.3, §2.6, §2.8).
- **Spec basis:**
  - WC §7: work hierarchy, local risk, inherited non-waivable gates, minimum-descendant floor.
  - WC §8: parent state derived; only the Lead closes a Story or Epic; children complete does not prove acceptance.
  - WC §15.1 and KC §9.4: promotion preserves identity, evidence and reason.
  - KC §9.1–§9.5, §15.1, §18, §26.
- **Nature:** An implementation of frozen semantics. The choices below fill gaps the contracts leave open (M2-B2, M2-B6); none changes a normative rule. The mutating-Ticket path of M1 is unchanged.

## Decision

### Derived parent state and the Lead's two decisions

A Story's or Epic's `state` is recomputed inside every Lead commit (`hierarchy.recompute_parents`, called from `before_commit`) and is never set by `work transition`:

| State | When |
|---|---|
| `CANCELLED` | a cancellation decision is recorded on the parent (or inherited from a cancelled ancestor) |
| `DONE` | a closeout decision is recorded |
| `ACCEPTANCE_PENDING` | it has children and every child is terminal |
| `IN_PROGRESS` | some child is not terminal |
| `PLANNING` | it has no children |

- `OPEN` (M1) remains valid in the schema and is replaced by the derived value at the first M2 commit.
- `rollup()` keeps its M1 vocabulary (`EMPTY`/`IN_PROGRESS`/`CHILDREN_COMPLETE`); it is a separate, advisory field.
- A child's failure or blocking never changes the parent's phase. The parent carries a derived `attention` list (children in REPLAN_REQUIRED, VERIFICATION_FAILED, INTERRUPTED or ESCALATED; a failed parent verification awaiting classification) and a derived `blocked_descendants` flag (every open descendant is BLOCKED).
- `before_commit` derives parents, then recomputes readiness, then derives parents again. A parent closed in a commit therefore unblocks its dependants in the same commit, and readiness changes are reflected in the parents' state in the same commit.
- **Closeout** (`aew work close <S|E> --reason`, decision `closeout`) requires ACCEPTANCE_PENDING, at least one DONE child, every parent gate CURRENT, and required parent-level findings resolved or waived. It writes `work/<id>/closeout.md` with every child, its completion-record hash, the children digest and the parent evidence.
- **Cancellation** (`aew work cancel <S|E> --reason`, decision `cancellation`) cancels every non-terminal descendant in one commit through M1's single state-change path, so workspaces are released and every credential is revoked. It is refused while any descendant is `publishing`. DONE children stay DONE.
- Terminal parents are frozen: no child is created under, or moved into, a DONE or CANCELLED parent. There is no reopen; the Lead creates a new unit.

### Parent gates

- New policy table `gates.yaml` `parent_paths` (per class, defaults in `DEFAULT_GATES`): class 0 `[children_complete]`; classes 1–4 `[accepted_plan, children_complete, review_r1, verification_goal_backwards, verification_contract]`.
- Effective obligations are computed by the existing `effective_obligations` with the path table selected by unit type. A unit's own `mandatory_gates` apply to its descendants (WC §7.4), which include sub-parents and non-mutating Tickets (M2-B6, conservative).
- `children_complete`: every child terminal and at least one DONE.
- **Parent snapshot.** Parent review and verification are bound to `git-tree:tree(A)+children:<digest>`, where A is the authoritative commit and the digest covers each child's id, state and completion-record hash. Adding, moving in or completing a child, or integrating anything, makes existing parent reports STALE. A same-source check ignores AEW's own `.aew/` files.
- Parent reviewers and verifiers are dispatched with `aew invoke create <S|E> --role reviewer|verifier` in ACCEPTANCE_PENDING (scope `parent`, their own read-only observation at A). A failed parent verification must be classified (`aew verify classify <S|E>`) before another parent verifier is dispatched; the classification prescribes what closeout then requires (a new remediation child, a new parent plan, or re-verification).

### Plans bound to their ancestors (fail closed)

- Parents are planned like Tickets (`plan propose/accept`, any non-terminal state). A parent plan may also be adopted from a Planner's `plan_proposal` (ADR-0008).
- Accepting a unit's plan records `ancestor_plans`: every ancestor's accepted plan `{revision, sha256}`, or `null` if it had none.
- Any later change makes the unit's `accepted_plan` gate STALE, **including an ancestor's first acceptance** (`null` → v1). A READY/BLOCKED Ticket is kept BLOCKED (`plan_binding_stale`); every executor dispatch (`work assign`, `work dispatch`, `work redispatch`, execute-slot `invoke create`) is refused; gate-guarded transitions (COMMIT_READY, integration, `work accept`, `work close`) fail.
- Recovery is explicit and per unit: `aew plan reconfirm <id> --reason` (decision `plan_reconfirmation`) rebinds to the current ancestor plans, or a new plan revision is accepted. Reconfirming a Story does not reconfirm its children.

### Structure changes (all Lead decisions)

- **Move** (`aew work move <id> --parent <P|none> --reason`, decision `hierarchy_change`): kind rules, cycle checks and the terminal-parent refusal apply. `parent_history` is appended in control state; the immutable record keeps its creation-time `parent` as provenance. The moved subtree's plan bindings are invalidated (fail closed). Moving a DONE child into an active parent is allowed and changes the parent's children digest.
- **Promotion** (`aew work promote <T|S> --to story|epic --title … --reason …`, decision `promotion`): a new unit is created (record `promoted_from`, class at least the original's) under the nearest valid ancestor, and the original is moved under it with its identity, evidence and history. A promoted Ticket goes to REPLAN_REQUIRED (M1 semantics: its attempt ends when the new plan is accepted). Refused from DONE, CANCELLED, VERIFICATION_FAILED (classify first) or while `publishing`.

### Dependencies

- Edges may point at Tickets, Stories or Epics and may be declared on any unit.
- A Ticket upstream is satisfied as in M1. A parent upstream is satisfied when the parent is DONE (closed after its gates); a `mutating` edge to a parent additionally requires every DONE mutating descendant's integrated commit in the downstream base.
- A unit is also blocked by every edge declared on its ancestors (inherited edges, reported with `inherited_from`).
- Cycles are refused at creation and on edits, over the waits-for graph: direct edges, inherited edges, and parents waiting on their children (so no edge may point at one's own ancestor or descendant).
- **Edge edits** (`aew work depend <id> --add X[:kind] --remove X --reason`, decision `dependency_change`) are allowed only while every affected Ticket is BLOCKED, READY or REPLAN_REQUIRED.
- **Records flow only through edges to non-mutating Tickets** (implementation refinement, 2026-09-27). An edge to a Story or Epic is an acceptance dependency: the parent's closeout already judged its children's records against the parent snapshot, so those Story-internal records are not consumed again downstream. (Found by AT-13: Story B depending on Story A would otherwise have been blocked by A's own, already-consumed, pre-integration survey.)
- Dependency satisfaction is not input acceptability; see ADR-0008 (INPUT_STALE).

### Context, resume, status

- Every pack gains a hierarchy section (ancestor chain with objective, acceptance criteria and accepted plan revision; inherited non-waivable gates and floor). It never includes siblings. Upstream records appear only through explicit edges, pinned with freshness.
- **Parent reviewer and verifier packs cover every child's own output.** Each DONE mutating child contributes its own integrated change (`git diff <integrated>^1 <integrated>`, from its completion record), labelled when it is already in the parent's baseline (for example a DONE Ticket moved in later); each DONE non-mutating child contributes its accepted record. The aggregate `baseline..A` diffstat is supplementary context only, and is rendered even when empty, which is exactly when it would hide a child's change.
- `aew work tree [<id>]`, `aew status`, `aew resume` and `CURRENT.md` render the Epic → Story → Ticket tree with derived state, attention, accepted plans and bindings, consumed inputs (and whether they block the next dispatch), acknowledgements, each non-mutating Ticket's current attempt, per-parent next actions, and contradictions (a parent state that disagrees with its derivation, retired observation directories left on disk).

## Consequences

- A Story or Epic cannot be closed by children completing, nor by a generic transition; its own gates, evaluated against the current child set, are required.
- A change of intent anywhere above a unit stops that unit before its next executor dispatch or gate-guarded transition until the Lead reconfirms or replans it.
- M1's tests, probes and walk are unchanged; the schema changes are additive (`OPEN` stays valid).
- Evidence: `tests/unit/test_hierarchy_model.py`, `tests/integration/test_hierarchy.py`, `tests/regression/test_m2_compositions.py`, `tests/regression/test_hierarchy_walk.py`, AT-8, AT-9, AT-10, AT-11, AT-13.

## Designed (not in M2)

- Plan-driven materialization of child Tickets from a parent plan.
- Priority and milestone concepts (KC §28.10); backlog priorities stay in `external_refs` and the body.
