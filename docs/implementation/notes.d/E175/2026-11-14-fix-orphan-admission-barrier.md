Main 3b79d9b8: run 43555974565, Windows integration 9/14, job 132328870678 failed
test_worker_messages.py::test_a_wait_orphaned_by_a_shorter_shell_timeout_records_no_delivery.
Evidence: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/43555974565/job/132328870678
and artifact lane-report-Windows-integration-9-attempt-1 (14099165292). The shell tool was called at 04:34:43Z
and failed at 04:35:14Z; the captured shell output was empty. fake_agent killed the shell when its fixed
30-second admission guard expired; on Windows that kill itself yields exit 1. The log does not prove a natural
CLI refusal or import failure. Startup/admission under load was being mistaken for an orphaned admitted wait.

The barrier now waits for either the actual wait-bound marker or a natural shell exit. It has no startup deadline;
pytest's existing test watchdog is the bound. The orphan scenario's transcript wait likewise uses the watchdog,
not steps_done's separate 60-second guard. Only after the marker appears does the unchanged one-second shell timer
start. The message wait remains five seconds, and the original ended_early/no-DELIVERED/process assertions remain.
A shell that exits without binding fails even if its exit code is zero; it is not killed or called a shell timeout.
No src change, retry, timeout increase, platform skip, runtime qualification or provider probe.

Evidence mechanism scope: barrier-backed fake shell steps (enumerate timeout_after_file in tests/). While waiting,
the helper persists observed shell/descendant pid/start identities and whether an aew child was observed. This uses
the existing proctree observer, with no new host tool. NOT OBSERVED explicitly is not proof of absence: a short-lived
child between samples or an unreadable command line can be missed. The file is kept even for a watchdog failure.
Assertion evidence includes shell output, admission/process evidence and the run's events. Harness failure reports
and copied, redacted bundles now retain shell output and admission files, not merely the transcript's path to them.

Planted evidence/regression matrix:

| Control | Required outcome / evidence | Removed mechanism |
|---|---|---|
| Real shell delays CLI startup for 31 seconds, then the real bridge binds | Still orphan only after binding; ended_early and no DELIVERED | Old 30-second wait_file barrier kills before admission and fails |
| Real shell prints a planted error and exits 7 before binding | Assertion fails with that output, native exit 7, run events and process-observation status | No false timed_out or admitted-wait claim |
| Shell output and observed aew pid planted in a harness run directory | Copied bundle and failure report retain redacted output, process evidence and events | Removing shell-file collection or assertion evidence fails the row |

The first control is real elapsed time, not a raised margin or a probabilistic repeat. The evidence row covers the
missing startup/process context exposed by this recurrence; it does not claim native child stacks or infallible
process observation. Earlier hits at 0282a0db and 083632ed remain historical evidence, not waived by local passes.
