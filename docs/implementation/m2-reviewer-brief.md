# M2 independent review brief

**For:** the independent reviewer(s) of AEW M2, before M3 (OpenCode) begins.
**Branch:** `impl/m2-hierarchy`, from `main` at `7ee76c7` (M1 accepted and reviewed). **Frozen specs:** WC v0.7, KC v0.4, SPT-R v0.2 (`aew-spec-frozen-2026-09-25`, unchanged).

## What M2 claims

1. **Epic → Story → Ticket hierarchy.**
   - Parent state is derived in every commit.
   - Only the Lead closes or cancels a parent, through recorded decisions.
   - Children completing is not parent acceptance: parent gates are evaluated against the parent snapshot (authoritative source plus children digest).
2. **Non-mutating Tickets** are dispatched to Investigator, Researcher or Planner cards.
   - Each gets a read-only observation per invocation, never a mutation workspace.
   - The executor card and the expected output kind are pinned at dispatch.
   - Attempts are explicit and supersession retires everything from the old attempt.
   - Records are accepted by the Lead with an evidence-only completion record.
3. **Dependency satisfied ≠ input acceptable.**
   - A source-bound record (discovery, plan proposal) that no longer matches the source a consumer will use refuses that consumer's dispatch (`INPUT_STALE`).
   - It proceeds only after a refresh, or a Lead acknowledgement pinned to that exact commit.
   - External research is `UNKNOWN (external)` and never blocks.
4. **Fail-closed plan bindings.** Any change to an ancestor's accepted plan, including its first acceptance, stops every descendant before its next executor dispatch or gate-guarded transition until the Lead reconfirms or replans.
5. **M1 is unchanged.** The mutating path, M1 gate evaluator, integration saga, serial cap, credential scheme, M1 tests, the 22 reviewer probes and the M1 walk are all untouched. Schema changes are additive.

The design and its operator review are in `m2-ambiguity-report.md`. The decisions are in ADR-0007 (hierarchy) and ADR-0008 (non-mutating path), with amendments to ADR-0003 (transitions) and ADR-0006 (dispatchable archetypes).

## Where to look

| Area | Code |
|---|---|
| Derived parent state, cycles, inherited edges, children digest (pure) | `src/aew/engine/hierarchy.py` |
| Record freshness contracts | `src/aew/engine/freshness.py` |
| Dispatch, attempts, observation workspaces, inputs, ingest/accept, record review, plan adopt/reconfirm | `src/aew/engine/nonmutating_ops.py` |
| Parent gates, parent review/verify, close, cancel, move, promote, depend, tree | `src/aew/engine/hierarchy_ops.py` |
| Plan bindings, readiness blocker `plan_binding_stale`, before_commit ordering | `src/aew/engine/work_ops.py`, `dependencies.py` |
| Evaluator for evidence units and parents (M1 `evaluate` untouched) | `src/aew/engine/gates.py::evaluate_evidence_unit` |
| Interruption of non-mutating executors | `src/aew/engine/lead_ops.py::_phase_waits_on` |
| Packs (hierarchy, inputs, subject, per-child integrated diffs) | `src/aew/knowledge/context.py`, `src/aew/engine/context_ops.py` |
| Resume/status/tree | `src/aew/engine/resume_ops.py`, `status_ops.py`, `knowledge/render.py` |

## Invariants to attack

The cross-operation oracle (`tests/helpers/invariants.py`) checks these after every step of every composition and walk. M1 rules 1–5 still apply.

| # | Invariant |
|---|---|
| 6 | Hierarchy shape: valid parent kinds, no parent cycle |
| 7 | A DONE/CANCELLED parent has a recorded Lead decision, every descendant terminal, and no active invocation at or below it. DONE needs at least one DONE child. ACCEPTANCE_PENDING means every child is terminal. |
| 8 | A non-mutating Ticket never holds a workspace, integration or implementer, and never reaches COMMIT_READY |
| 9 | At most one active execute invocation per non-mutating Ticket, and only the current attempt's |
| 10 | An accepted record has the pinned `expected_kind` and comes from the current attempt. DONE requires it plus a completion record. |
| 11 | Discovery/research/proposal records come only from the matching archetype, in observation scope |
| 12 | A retired observation belongs to an ended invocation. An active observation invocation never has a revoked credential. |
| 13 | Every consumed input pinned on an invocation was CURRENT, external, or acknowledged by a recorded decision for exactly the commit that invocation was dispatched against |

Enforced by the operations, not the oracle, and covered by tests:
- plan-binding checks at dispatch and at gate-guarded transitions;
- parent snapshot staleness;
- `OBSERVATION_MUTATED`.

Suggested probes:
- a late or replayed record across attempts, handoffs, takeovers and cancellations;
- an ancestor plan changing while a descendant is ASSIGNED, RUNNING, VERIFIED or COMMIT_READY;
- moving a DONE child into, or out of, a parent that holds a CURRENT review;
- an INPUT_STALE acknowledgement reused after the source moves;
- a research record consumed across many integrations;
- promotion or cancellation while a descendant is `publishing` or holds a live executor;
- a read-only role acting through another archetype's operations, another invocation's observation, or the authoritative worktree;
- cycles introduced through inherited edges plus a move.

## Implementation refinements after the operator-reviewed plan

- **Dispatch reuses `assign`; acceptance uses a new `accept` rule** (the M1 table test pins one `via` per pair).
- **Records flow only through edges to non-mutating Tickets.** An edge to a Story or Epic is an acceptance dependency. Found by AT-13: without this, a Story-internal survey that the Story had already consumed and moved past would block the dependent Story's work.
- **"Integrated before the baseline" means the child's integrated commit is an ancestor-or-equal of the parent baseline.** The aggregate diffstat is rendered even when empty, because that is exactly when it would hide a child's change.
- **Executors never start under a stale ancestor plan binding.** This covers `work redispatch` and a mutating Ticket's execute-slot `invoke create`, not only READY → dispatch.
- **Reconciling an interrupted non-mutating Ticket records the attempt, not a workspace:** executor, status and records submitted.
- **The evidence-only completion record names its `basis`** (what satisfied the gates) and every retired attempt with its record.

## How to run

```bash
python -m pytest -q                                   # everything, serially
python -m pytest -q -n auto -m "not serial" && python -m pytest -q -m serial   # parallel + serial lane
python -m pytest tests/regression/test_m2_compositions.py tests/integration/test_non_mutating.py \
                 tests/integration/test_hierarchy.py -q
python -m pytest -m acceptance -q                     # AT-1..AT-13
AEW_HWALK_SEEDS=1,2,3,4,5 AEW_HWALK_STEPS=150 python -m pytest tests/regression/test_hierarchy_walk.py -q
```

Every M1 reviewer probe file runs unchanged: `tests/regression/test_review_2026_09_26.py`, `test_foundation_review_2026_09_26.py` and `test_remediation_review_2026_09_26.py`.

## Known limits (Staged / Designed, not defects)

- **No live agent harness.** Roles are scripted CLI drivers. The OpenCode adapter is M3 and has not started.
- **Serial mutation.** The mutating cap stays 1 until M5. Read-only concurrency is limited only by optional policy.
- **Designed, not implemented:**
  - provider mutation declarations and capability resolution (M6);
  - card `restrict.paths`;
  - plan-driven child materialization;
  - priority and milestone concepts;
  - lease-expiry takeover.
- **Replan semantics follow M1.** During REPLAN_REQUIRED an executor's credential remains until the new plan is accepted, but nothing it submits can be ingested (ingest requires RUNNING and the current plan).
