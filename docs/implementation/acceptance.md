# Acceptance suite (M1, M2)

The scenarios from the M1 plan (§6), the M2 plan (§6 step 9) and KC §26 are tagged `@pytest.mark.acceptance("<id>")`:

```bash
python -m pytest -m acceptance -q      # just the acceptance scenarios
python -m pytest -q                    # everything (unit, integration, acceptance)
```

In CI the scenarios run in the `acceptance` lane, except the real-process ones marked `serial` (`test_store_processes.py`, the pty takeover), which run in the `serial` lane. The `assurance` job proves every scenario ran on both OSes. See `testing-and-ci-strategy.md`.

Every scenario drives the real `aew` CLI in separate processes against real git repositories. Roles are played by scripted drivers (`tests/helpers/aewflow.py`) that use only the launch contract, the invocation credential and the CLI, exactly as an LLM subagent would.

| ID | Scenario | Tests |
|---|---|---|
| AT-1 | Serial lifecycle → DONE; destroy the Lead session mid-flight; delete `.aew/local`; reconstruct with `aew resume`; operator-authorized takeover; reconcile the interrupted Ticket; complete it | `tests/acceptance/test_at1_serial_lifecycle.py` |
| AT-2 | An unintegrated upstream mutating Ticket (COMMIT_READY, or published but crashed before DONE) keeps its dependent BLOCKED; the output must be in the recorded source snapshot | `test_integration.py::test_unintegrated_dependency_stays_blocked`, `::test_dependency_requires_output_in_recorded_snapshot` |
| AT-3 | A relevant uncommitted input change makes passing evidence STALE; history is kept byte-identical; AEW's own writes never invalidate the fingerprint | `test_evidence_gates.py::test_relevant_uncommitted_change_makes_evidence_stale_but_keeps_history`, `::test_stale_review_cannot_be_ingested`, `test_fingerprint.py::test_aew_files_never_change_the_fingerprint` |
| AT-4a | A crash mid control transition recovers to the previous or next state, never a hybrid | `test_store_processes.py` (real `os._exit` at 8 points; 2×50 racing writers), `tests/acceptance/test_at4a_at7.py` (CLI transition and assignment), `test_integration.py::test_crash_during_publish_reconciles` |
| AT-4b | A superseded Lead is rejected; takeover cannot be self-authorized; operator takeover supersedes every prior credential | `test_authority.py::test_superseded_lead_rejected_after_handoff`, `::test_takeover_cannot_be_self_authorized`, `::test_operator_authorized_takeover_supersedes_everyone` (POSIX pty), `test_integration.py::test_superseded_lead_cannot_publish` |
| AT-5 | Role separation: a Verifier cannot classify, an Implementer cannot review, invocation credentials cannot drive control, the Lead cannot declare VERIFIED, card restrictions narrow credentials | `test_evidence_gates.py::test_role_separation_negatives`, `test_role_cards.py::test_card_restriction_narrows_the_credential`, `tests/unit/test_roles.py` (escalation) |
| AT-6 | Lead-owned verification-failure classification maps to the mandated transitions | `test_evidence_gates.py::test_lead_classifies_verification_failures` |
| AT-7 | Workspace copies of `.aew/` are never authority; a Ticket cannot write AEW state through its workspace | `test_authority.py::test_worktree_copy_of_aew_is_not_an_authority`, `test_workspaces.py::test_aew_inside_workspace_resolves_to_authoritative_project`, `tests/acceptance/test_at4a_at7.py::test_ticket_cannot_write_aew_state_through_its_workspace` |
| KC §26 | Existing-authority project: sources are referenced, not duplicated | `test_resume.py::test_existing_authority_project_is_referenced_not_duplicated` |

## M2 acceptance (hierarchy and non-mutating work)

The M2 scenarios live in `tests/acceptance/test_at8_at13_hierarchy.py`, with the same conventions as M1: real CLI processes, real git repositories, scripted role drivers, and the invariant oracle at the end of each phase.

| ID | Scenario | Tests |
|---|---|---|
| AT-8 | Story lifecycle to closeout. Epic → Story → an investigation consumed by an implementation Ticket. COMMIT_READY is not completion. With all children DONE the Story is ACCEPTANCE_PENDING, but closing is refused until its own review and verification pass against the parent snapshot; `work transition` never closes it. The Epic closes after the Story. | `test_story_lifecycle_to_closeout` |
| AT-9 | KC §26 parent risk policy propagation. A Class-3 Story with a Story-level mandatory security review: its locally Class-0 Ticket keeps class 0, inherits the non-waivable gate (a waiver is refused), and needs the security review before COMMIT_READY. A minimum-descendant floor is rejected without a rationale and, with one, raises only the effective class. | `test_parent_risk_policy_propagation` |
| AT-10 | KC §26 Ticket promotion. A running Ticket's implementation report shows hidden cross-component ambiguity. The Lead promotes it to a Story under the same Epic. The Ticket keeps its id, record bytes, evidence and history, moves under the new Story in REPLAN_REQUIRED, and the promotion decision carries the reason. Work continues under the Story. | `test_ticket_promotion_preserves_identity_evidence_and_reason` |
| AT-11 | KC §26 fresh-session reconstruction with an active Epic. The Lead session is destroyed mid-investigation and `.aew/local` is deleted. `aew resume` recovers the tree, derived states, accepted plans, the executor's attempt and pinned output kind, inherited Story-level edges, and the next action (ingest the submitted record). An operator takeover then interrupts the read-only executor. The old credentials are rejected, the submitted record is never inferred, reconciliation records the attempt, and a new attempt completes it. | `test_fresh_session_reconstructs_an_active_hierarchy_and_takeover_interrupts_read_only_work` |
| AT-12 | Read-only concurrency and authority. Investigation, research and planning run beside a mutating Ticket that holds the serial slot. Each has its own observation of the authoritative source and never sees the unintegrated workspace; the serial cap still refuses a second mutating assignment. Read-only roles cannot submit another archetype's kind, drive control state, accept plans or run checks outside their grant, and a mutated observation is refused (`OBSERVATION_MUTATED`). A Planner's proposal becomes a plan only when the Lead adopts and accepts it. | `test_read_only_work_runs_concurrently_and_stays_read_only` |
| AT-13 | Backlog representability (generic, SPT-shaped). An Epic of Stories mixing investigation, research, planning and implementation Tickets, with external refs/priorities, a Story-level dependency, an Epic-level audit, and a standalone small Ticket with no artificial parent. It includes the KC §26 `T1,T2 → T3` + `T4` graph: T3 stays BLOCKED while T1 is only COMMIT_READY, its assignment snapshot contains T1's integrated output, and T2's survey (stale after T1 changed its observed paths) is used only after the Lead's recorded acknowledgement for that commit. Everything closes. | `test_representative_backlog_is_representable_and_executable` |

**Regressions:**
- `tests/regression/test_m2_compositions.py` holds the operator-review sequences: ancestor first-acceptance, attempt supersession, stale inputs (acknowledge, re-refuse, refresh), record freshness at accept, handoff of read-only work, a moved DONE child's review completeness, and parent cancel versus `publishing`.
- `tests/regression/test_hierarchy_walk.py` is a separate seeded walk (`AEW_HWALK_SEEDS`, `AEW_HWALK_STEPS`, `AEW_HWALK_FAULT_RATE`). The M1 walk is unchanged.

## Review regressions (2026-09-26)

The independent M1 review's 12 probes are preserved unchanged in `tests/regression/test_review_2026_09_26.py` and must pass. Composition tests for the same interactions, the cross-operation invariant oracle and a seeded adversarial walk (`test_composition_walk.py`, 5 seeds × 60 steps; widen with `AEW_WALK_SEEDS` / `AEW_WALK_STEPS` / `AEW_WALK_FAULT_RATE`) live alongside them. See `review-response-2026-09-26.md`. The probes and compositions are permanent merge gates (the `regression` lane); the walk's default budget is a merge gate (the `adversarial` lane), and the nightly lane runs larger budgets with rotating seeds.

```bash
python -m pytest tests/regression -q
```

## Platform notes

- **Linux** (WSL Ubuntu 22.04, Python 3.11, ext4) is the reference platform for the Rocky 8 target. There the operator-takeover tests answer a real challenge on a pseudo-terminal.
- **Windows** (Python 3.13) runs everything else. Two Windows-specific choices:
  - AT-1's takeover step substitutes the terminal channel in-process, because a Windows console session would appear on the developer desktop. The positive POSIX pty test is skipped on Windows, and that skip is reported.
  - CLI test processes use `CREATE_NO_WINDOW`, so no console window ever appears.
