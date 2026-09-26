# M1 acceptance suite

The scenarios from the M1 plan (§6) and KC §26 are tagged `@pytest.mark.acceptance("<id>")`:

```bash
python -m pytest -m acceptance -q      # just the acceptance scenarios
python -m pytest -q                    # everything (unit, integration, acceptance)
```

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

## Platform notes

- **Linux** (WSL Ubuntu 22.04, Python 3.11, ext4) is the reference platform for the Rocky 8 target. There the operator-takeover tests answer a real challenge on a pseudo-terminal.
- **Windows** (Python 3.13) runs everything else. Two Windows-specific choices:
  - AT-1's takeover step substitutes the terminal channel in-process, because a Windows console session would appear on the developer desktop. The positive POSIX pty test is skipped on Windows, and that skip is reported.
  - CLI test processes use `CREATE_NO_WINDOW`, so no console window ever appears.
