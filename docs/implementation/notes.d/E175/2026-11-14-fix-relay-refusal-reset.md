Separate fix for the refusal-close defect exposed by PR #472 at 166ba978, run 43564068328,
Windows integration 2/14, job 132354038605. The failing ID was
test_harness_qualify.py::test_worker_plan_qualification_wires_the_fake_upstream_and_records_no_credentials;
worker_plan.py:111 raised ConnectionResetError (WinError 10054) while reading the expiry refusal.
Evidence: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/43564068328/job/132354038605
and downloaded artifact lane-report-Windows-integration-2-attempt-1 (14101949239). The downloaded artifact
contains the lane/discovery reports; the job log retains the failing stack. It does not retain the reported autopsy.

ProviderRelay may refuse a request after its head but before reading its body. Closing with unread receive data
can reset TCP on Windows and discard the refusal before the client reads it. After sending a refusal, _answer now
half-closes its write side, then drains received input locally until EOF, an absolute short deadline, or a byte cap.
The source of the named budgets is the existing dashboard.server staged refusal close: 0.5 seconds and 256 KiB,
following RFC 9112 section 9.6. The deadline is not renewed by trickling input. The drain never connects or forwards
anything upstream and cannot consume an unbounded request. Existing shutdown/timeout/socket errors remain tolerated.

Regression/evidence matrix: for both expired 401 and retryable-unreadable 503, send the request head alone, hold
the relay just after its refusal send, then send the body separately. Wait for the handler to close before reading
the full refusal. This forces the previously unread-body close rather than relying on packet timing or sleeps.
Removing the staged drain must fail this control on Windows. The assertion also pins no upstream connection.
Separate stepped-clock and byte-budget controls require termination even when input never ends. The originally
failing fake qualification test remains unchanged and is included in validation; no binary/provider probe or
qualification fixture/adoption change is introduced.

Scope enumeration: every ProviderRelay refusal funnels through _answer (including _grant and pre-body parser
refusals). The staged close is best-effort within its budgets: an endless/oversized body or a vanished peer can
still reach forced close; the fix does not promise successful refusal delivery beyond those limits. No retries,
deadline raises, platform skips or unbounded reads. This branch is fresh from origin/main, separate from #472.
