Main `7afa8aef` completed all required test cases for CI run `45627643471`. Windows integration 11/14
reported 235 passes and 17 pinned skips. Its xdist `gw3` channel closed at 14:04:32 UTC, before the last
six test results from the other workers. Pytest exited 0. D2 caught the missing handoff, but the published
findings named only `gw3`. The archive did not identify the failed process or its exit status, so the cause
of the original worker exit remains open. [Windows job](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45627643471/job/139252182793) ·
[Original report bundle](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45627643471/artifacts/15030745724) ·
[Failed assurance](https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/45627643471/job/139262105491)

The ratchet now names the report path for capture errors. The existing scanned discovery report records the
xdist worker, local child PID and exit status when available, whether its findings arrived, and its last
reported test phase and outcome. The last report identifies an observation and does not attribute the exit
to that test. Missing findings still fail D2 with the existing rules and allow-list.

| Failure evidence case | Deterministic control | Required report |
| --- | --- | --- |
| An xdist worker disappears after all its tests pass | A one-worker session exits the worker with status 37 before its final handoff | The lane stays complete. The scanned discovery report retains the worker, PID, observed exit status and passed teardown. D2 fails and points to that report. |
