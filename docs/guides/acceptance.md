# Acceptance suite (M1, M2, M3)

The scenarios from the M1 plan (§6), the M2 plan (§6 step 9), the M3 plan (§5 step 6) and KC §26 are tagged `@pytest.mark.acceptance("<id>")`:

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

## M3 acceptance (harnesses)

The M3 scenarios are written once, adapter-neutrally, in `tests/helpers/harness_acceptance.py`, and run by `tests/acceptance/test_at14_at17_harness.py` against two drivers (`harness_conformance.py`):
- **`fake`:** the fake harness, a scripted agent process with the curated agent environment. The Lead's harness is `aew lead session` with a scripted Lead.
- **`opencode-fake`:** the production OpenCode adapter against a fake V2 server that serves the real 2.0.18 OpenAPI and runs each scripted tool call in the session's shell environment. The Lead's harness is `aew opencode` with a fake TUI that acts in the environment `aew opencode` gave it (a V2 standalone TUI gives that environment to every session's shell).

Roles are harness runs, dispatched with `--launch`. Their scripted "models" act only through `aew` in the harness session, never with a credential. A verifier cites its own check results by reading their ids from its command output, as a model would. Where the scenario concerns the Lead (AT-14, AT-15, AT-17), the Lead also acts through its own harness session and reads run results from `aew harness wait`.

The same scenarios run on **real OpenCode 2.0.18** in the opt-in live lane (`tests/live/test_opencode_acceptance_live.py`, a free model). Two things cannot be observed live and are skipped inside the scenario rather than asserted: the delivered prompt, because the live driver runs scripted steps rather than prompting with the contract, and a second execution profile, because only one free model is used. The live Lead acts through `aew lead session`, because the real TUI needs a terminal; the operator's own TUI session is its live check (M3 plan §9).

| ID | Scenario | What it proves |
|---|---|---|
| AT-14 | **A Ticket from objective to DONE through harnesses.** One Lead session plans the Ticket, dispatches with `--launch`, follows each run with `harness wait` and ingests what it recorded. The implementer, the reviewer (routed to its own execution profile), the verifier and the post-integration verifier are each a harness run. | Each run has the intended role, scope, workspace (its cwd) and model/effort, both requested and effective. The harness received the preamble and exactly the pinned pack. Every piece of evidence carries its run, invocation, credential id and execution profile. `harness status` correlates run, session, invocation and evidence. Each invocation gets a fresh session. No Lead output holds a credential. The Ticket integrates to DONE. |
| AT-15 | **The harness is disposable.** The implementer's run dies from outside mid-work, after writing half the change and recording a check. All harness state is then wiped: `.aew/local` (run records, sessions, databases, packs). A fresh Lead session runs `aew resume`, relaunches with `--replace`, and a third Lead session completes the Ticket. | Harness loss moves nothing (the Ticket stays RUNNING, not INTERRUPTED; the credential is not revoked; M3-B1). `resume` shows the run as unconfirmed with its durable evidence and the relaunch-or-cancel action. The relaunch rotates the credential, and the new run's continuation (earlier run, its evidence, the changed paths) comes from durable state only. A copy of the dead session's state, revived with everything that session had (its environment and bridge coordinates; on real OpenCode, a new server on the copied state), has no authority: `whoami` and `submit` give `STALE_AUTHORITY`. |
| AT-16 | **Review is isolated.** Implementer, reviewer, rework implementer and re-reviewer are each a harness run. The implementer makes a private remark in its own session. The first reviewer edits the code it reviews, is refused, puts the code back and reports a required finding. The rework and the re-review then resolve it. | Four sessions, each run's harness state holding only its own, in disjoint state directories. The implementer's remark stays in its own conversation: in no other run's state or prompt and never in AEW state. What crosses between runs is AEW state (the open finding reaches the rework and the re-review through their packs). A reviewer's edit is refused (`WORKSPACE_MUTATED`, naming the path). The accepted review evaluated the implementer's reported snapshot, and a review run moves nothing until the Lead ingests it. OpenCode: reviewers get `edit` denied, and each run's external-directory allowances name only its own run. |
| AT-17 | **Credential custody, invocation and Lead.** The operator releases the seat, and the Lead's session takes it (`--acquire`), so the Lead credential exists only inside the session's broker. The session dispatches with `--launch`, relaunches while the first run is live, tries the credential-emitting commands, and is then superseded by an operator takeover. | The five custody properties on both sides: authorized operations work without a credential; neither model's environment, a child process nor a shell holds one (nor, for runs and for `aew opencode`, a provider key); no file either could reach holds one, and after the scenario none does anywhere. After the relaunch the old run's bridge refuses (`STALE_AUTHORITY`) and its credential is revoked `rotated`. After the takeover the old Lead session's next command and its broker refuse (`STALE_AUTHORITY`). Credential-emitting commands and a forged credential are refused, and the operator's terminal never shows a credential. |

Each scenario was checked against a deliberate regression, which it fails: relaunch without a continuation (AT-15), a reviewer allowed to edit its workspace (AT-16), the Lead TUI inheriting the operator's whole environment (AT-17), and per-role routing ignored (AT-14).

**Real models (evidence, not acceptance scenarios).** The scenarios above use scripted models, so that each property is asserted deterministically. Real models ran the same machinery twice more, with AEW's invariants asserted on every run and the models' outcomes recorded rather than asserted:
- step 8, free models, every role unscripted, including a rejection and rework of a seeded defect (`harness-conformance.md` §6);
- step 9, the paid dogfood, with a headless model Lead (`m3-dogfood-report.md`).

**Regressions from real models:** `tests/regression/test_m3_live_findings.py` (M3-D2, M3-D4 to M3-D7) and `test_m3_dogfood_findings.py` (M3-D8 to M3-D10, the containment label), plus `test_m3_intent_ingress.py` (`--fields`, companion review B1).

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
