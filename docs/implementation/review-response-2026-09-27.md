# Response to the independent M2 review (2026-09-27)

- **Reviewed branch:** `impl/m2-hierarchy` at `9553cb7`
- **Review:** "AEW Milestone 2 review", with the probe script `M2_independent_probe.py`
- **Verdict received:** do not merge. It found 2 Blockers, 2 Majors, and one M1 dependency regression, which is the mutating case of Blocker 2.
- **Spec set:** `aew-frozen-2026-09-25`. The frozen contracts are unchanged. As the review concluded, no finding is a frozen-contract contradiction. Each is an implementation that failed to enforce an existing rule across a composition of operations. Two ADR-0007 statements are made more precise; see "Decisions an operator should confirm".

## Probes

The probe script was not available in this repository, so the ten probes were **reconstructed** from the report's sequence table: `tests/regression/test_m2_review_2026_09_27.py`. Each probe does the following:

- Runs every step of the reported sequence through the public CLI.
- Does not assume which step refuses.
- Asserts only the safe end state.

All ten reproduced their finding on `9553cb7` before being marked as strict xfails (`158e398`). Each fix commit removed its own markers.

Three end-state assertions were tightened in the fix commit that first made them pass:
- the two B2 probes now assert "DONE *while under the new parent* with the prerequisite unfinished";
- the Major 1 probe now asserts "closed *with that dependency*".

The fixes refuse the move and the edit themselves. A Ticket that stayed where it was, or a Story that never gained the edge, may legitimately finish. The looser assertions would have flagged exactly that. Each tightened probe was re-run against the unfixed engine and still fails there.

| ID | Finding | Root cause | Fix | Main files | Commit | Evidence |
|---|---|---|---|---|---|---|
| B1 | Class 0 work bypassed stale ancestor plans: a non-mutating Ticket reached DONE; a mutating Ticket reached COMMIT_READY, prepared and **published**; a class 0 Story could close | The binding was enforced only through the `accepted_plan` gate's status. Class 0 paths (mutating, non-mutating, parent) do not list that gate, so no check ran. Dispatch checked the binding directly, which is why redispatch refused while completion did not. | Every gate context carries `plan_binding`, and `_require_gates` refuses on it whatever the obligation list. That single choke point covers every gate-guarded transition, `work accept`, `integrate prepare`, both publication checks (phase 1, and pre-CAS finalization, which withdraws the intent) and `work close`. `gate show` reports `accepted_plan: STALE`; resume no longer advises accept/close while the binding blocks. | `engine/evidence_ops.py`, `nonmutating_ops.py`, `hierarchy_ops.py`, `resume_ops.py` | `9aa823a` | 4 probes; `test_a_class0_plan_is_bound_to_its_ancestors_although_its_path_lists_no_plan_gate` (Epic → Story → {non-mutating, mutating}, refused at accept, publish and closeout until each unit is reconfirmed) |
| B2 | Moving active work bypassed inherited dependencies: after `plan reconfirm`, a moved non-mutating Ticket completed before its inherited prerequisite, and a moved mutating Ticket published before its inherited mutating upstream integrated (the M1 regression) | `work move` changes inherited edges, but only invalidated plan bindings. The attempt and its pinned inputs survived, and nothing after dispatch re-checked dependencies. `work redispatch` checked plan and inputs, but not dependencies. | **At the move:** re-parenting is an edge edit for every Ticket below the moved unit, so ADR-0007's `work depend` rule applies. A move (or promotion) that changes a started Ticket's effective edges is refused, naming each Ticket and its edges before and after. The Lead replans those Tickets first; the new plan's acceptance ends the attempt, and the next dispatch waits for, and pins, the new dependencies. **Defense in depth:** every dispatch records its effective edges on the attempt. Every gate check, evidence ingest and a fresh implementer's `invoke create` refuse if the edges changed or one is unsatisfied at the attempt's own source commit. `work redispatch` checks dependencies. | `engine/dependencies.py`, `hierarchy_ops.py`, `workspace_ops.py`, `nonmutating_ops.py`, `evidence_ops.py`, `work_ops.py`, `resume_ops.py` | `c0e0125` | 2 probes; `test_moving_started_work_under_new_dependencies_needs_a_new_dispatch`, `test_a_moved_mutating_ticket_is_reassigned_on_a_base_holding_its_inherited_upstream`, `test_promotion_may_not_change_the_dependencies_of_started_descendants`, `test_an_attempt_is_bound_to_the_dependencies_it_was_dispatched_with`; oracle rule 14 |
| Major 1 | A parent closed with an unsatisfied dependency added after its child reached DONE | `work depend` exempted DONE (and CANCELLED) Tickets from ADR-0007's edit restriction, and `work close` never evaluated the parent's own or inherited edges | `work depend` refuses while any affected Ticket is not BLOCKED, READY or REPLAN_REQUIRED, and names each Ticket with its state; a cancelled Ticket is not affected. `work close` refuses with `DEPENDENCY_UNSATISFIED` while any of the parent's own or inherited edges is unsatisfied, and resume says what it waits on. | `engine/hierarchy_ops.py`, `resume_ops.py` | `2c17ad0` | Probe; `test_edge_edits_wait_for_unstarted_work_and_closeout_waits_for_dependencies` (also covers a DONE child moved under a dependent Story, which is still allowed but cannot close it early) |
| Major 2 | An observation mutated after submission was lost at ingest | Ingest compared the record with the invocation's *stored* snapshot and never re-fingerprinted the observation. Reviewer and verifier submissions from observations were not checked at all, although ADR-0008 says `submit` checks every read-only invocation. | One `require_observation_intact` check runs at submission for every read-only scope, and again at `evidence ingest`, record review/verification ingest and parent review/verification ingest. A report whose invocation ended before ingest can no longer be checked, so it is refused (fail closed). | `engine/nonmutating_ops.py`, `hierarchy_ops.py`, `evidence_ops.py` | `78c75a3` | 3 probes (executor, record reviewer, parent reviewer); `test_a_read_only_invocation_is_checked_for_mutation_until_its_report_is_ingested` |

## Test-gap response

The review listed four missing compositions, and each is now a deterministic regression:

- class 0 ancestor-plan changes at completion and publication;
- active moves that add inherited dependencies;
- dependency edits after children finish;
- observation changes between submission and ingestion.

Beyond the probes:

- **Oracle rule 14** (`tests/helpers/invariants.py`, `a9c88f3`) runs after every step of every composition and both walks. It checks that every started Ticket's current effective edges equal the ones its attempt was dispatched with, and that each is satisfied in the source the attempt works from. The oracle computes this independently of the engine code. The non-vacuity test shows it firing on both halves.
- **Defense-in-depth tests** use corrupted copies of a real state, since no operation can produce these states any more. They show that the gate context refuses, and that an attempt recorded before bindings existed is still checked for satisfaction.

## Behaviour changes an operator will notice

- **Class 0 units need reconfirmation too.** After an ancestor's plan changes, a class 0 Ticket or Story is refused at the next gate-guarded step until `aew plan reconfirm` (or a new plan revision). `gate show` lists `accepted_plan: STALE` although the path has no such gate.
- **Moving started work that gains or loses inherited dependencies is refused.** Move the named Tickets to REPLAN_REQUIRED first, move, then accept a plan revision. Their next dispatch waits for the new dependencies. Moves that do not change a started Ticket's dependencies, and moves of finished Tickets, work as before.
- **Promoting a Story whose started Tickets would lose or gain inherited edges is refused** on the same terms.
- **`work depend` on a Story or Epic with a DONE descendant Ticket is refused.** Cancelled descendants do not block it.
- **`work close` waits for the parent's dependencies**, including edges inherited from its ancestors.
- **A read-only report whose invocation ended before ingest is not ingested.** Dispatch another reviewer or verifier, or redispatch the attempt.

## Decisions an operator should confirm

These are implementation choices, not contract changes. ADR-0007 and ADR-0008 record them.

1. **A cancelled Ticket is not "affected" by an edge edit.** ADR-0007 lists only BLOCKED, READY and REPLAN_REQUIRED. Read literally, a Story with any cancelled child could never have its edges edited again. A cancelled Ticket never runs again and contributes nothing, so it is exempt; DONE is not exempt.
2. **Moves of started work are refused rather than applied with an automatic replan.** Refusing matches the existing `work depend` rule, keeps every attempt-ending decision explicit, and needs no new state transition. The alternative was to move the affected Tickets to REPLAN_REQUIRED automatically, as promotion does for the promoted Ticket itself.
3. **Moving a DONE Ticket under a Story with unfinished dependencies stays allowed** (ADR-0007 allows moving DONE children). Its assignment is over; the Story's closeout now waits for the Story's dependencies.

## Verification

- **Full suite, Linux/Python 3.11, on the final tree:** 656 passed under `-n 4 -m "not serial"`, plus the serial lane (11 passed).
  - The one skip is `test_spec_pin.py`: the frozen-spec tag was absent from that clone. It passes once the tag is fetched, and so does the fast lane (448 passed).
- **Probes and targeted suites:** all ten probes pass. The M2 composition, hierarchy and non-mutating suites, AT-8..AT-13 and the hierarchy walk pass, with oracle rules 1–14 checked after every step.
- **M1 compatibility:** the M1 probe files, compositions, walk and AT-1..AT-7 pass unchanged. No existing test expectation changed.
  - Existing tests were edited only by appending (new compositions, and rule 14 in the oracle's non-vacuity test).
  - The mutating path of blocker 2 now holds the M1 dependency rule: an inherited mutating upstream is in the new assignment's base before the dependent can be dispatched again.
- **Not run here:** Windows, and the CI lane timing. The new regression tests add roughly 2–3 minutes of serial test time to the `regression` lane; the durations file has no entries for them yet, so the shard balance uses the median until the next refresh.

## Re-review of `0552116`

- **Review:** the follow-up review of the fixes, with the probe script `M2_followup_probe.py`.
- **Verdict received:** the four original findings are resolved. One new Major must be fixed before merge. One contract question was left open for an operator decision and not counted as a defect.

| ID | Finding | Root cause | Fix | Evidence |
|---|---|---|---|---|
| R-Major | `work redispatch` bypassed `non_mutating_concurrency`. With a cap of one: A's record ingested, B dispatched, A redispatched → two active executors | Dispatch checked the cap before starting an attempt; redispatch called the attempt start directly | The cap is checked in `_start_attempt`, the one place every attempt starts. It runs after the previous attempt is retired in the same transaction, so a redispatch replacing its own active executor stays within the cap (the reviewer's control probe) | The reviewer's probe and control probe (fails on `0552116`, passes now); oracle rule 15 (active executors ≤ cap) after every step of every composition and walk; the hierarchy walk now runs with a cap of 2 |
| R-Question | A parent could receive review and verification before an evidence prerequisite completed, then close on those reports once it did | ADR-0007 applied parent dependencies only to closeout (ordering) | **Operator decision: parent acceptance is a downstream assignment** (WC §8: a dependency is satisfied only when the upstream output is in the downstream assignment's recorded input/source snapshot). Parent reviewer/verifier dispatch waits for the parent's own and inherited dependencies (`DEPENDENCY_UNSATISFIED`). It pins the prerequisite records under the ADR-0008 input rule (`INPUT_STALE` unless acknowledged; shown in the pack). Each report is bound to the dependency set it was dispatched under, so a later move or edit makes it STALE, and ingest refuses it. The closeout records its dependencies and the `basis` of each gate. Resume says what the acceptance waits on. | The reviewer's probe (reconstructed, safe end state; fails on `0552116`, passes now); `test_parent_acceptance_is_a_downstream_assignment_of_its_dependencies`; oracle rule 16 (a closed parent relied only on reports dispatched under the dependencies its closeout records, each DONE), with its non-vacuity check |

- **The three early-refusal probes** from the follow-up script are preserved as regressions. They confirm that the round-one fixes refuse at the move or edge edit and leave the structure unchanged.
- **Behaviour an operator will notice:**
  - A Story or Epic with an unfinished prerequisite cannot dispatch its reviewer or verifier.
  - A stale prerequisite survey must be acknowledged for the Story (`aew work acknowledge-input <S>`), as for a Ticket.
  - Moving a Story under a parent with dependencies makes its existing acceptance reports STALE.
