Separate fix for the refusal-close defect exposed by PR #472 at 166ba978, run 43564068328,
Windows integration 2/14, job 132354038605. The failing ID was
test_harness_qualify.py::test_worker_plan_qualification_wires_the_fake_upstream_and_records_no_credentials;
worker_plan.py:111 raised ConnectionResetError (WinError 10054) while reading the expiry refusal.
Evidence: https://github.com/JonSmithTLT/Agentic-Engineering-Workflow/actions/runs/43564068328/job/132354038605
and downloaded artifact lane-report-Windows-integration-2-attempt-1 (14101949239). The downloaded artifact
contains the lane/discovery reports; the job log retains the failing stack. It does not retain the reported autopsy.

ProviderRelay may refuse a request after its head but before reading its body. Closing with unread receive data
can reset TCP on Windows and discard the refusal before the client reads it. After sending a refusal, _answer now
half-closes its write side, then drains received input locally until EOF or an absolute short deadline.
The named deadline is the pre-existing dashboard.server refusal-close budget of 0.5 seconds, following RFC 9112
section 9.6. The initial 256-KiB cap was rejected by review M1: provider-sized bodies can exceed it and still lose
their refusal on Windows (10053). It bounds no memory because input is discarded in fixed 64-KiB receive buffers.
The shared http_close.close_after_response owns half-close, deadline-only drain and final close. The deadline is
not renewed by trickling input. The drain never connects or forwards anything upstream. Shutdown/socket errors and
timeouts still end the close; input continuing past the deadline is not promised successful refusal delivery.

Regression/evidence matrix: for both expired 401 and retryable-unreadable 503, send the request head alone, hold
the relay just after its refusal send, then send the body separately. Wait for the handler to close before reading
the full refusal. This forces the previously unread-body close rather than relying on packet timing or sleeps.
The split pair is now TCP loopback on both hosts, not Linux AF_UNIX (n2). Removing the staged drain must fail the
Windows control. Additional http.client TCP POSTs of 8 MiB require complete 401 and 503 answers; an egress POST
with 64 KiB requires its 405 without a reset. All assert no upstream connection/resolution. Separate stepped-clock
controls pin an absolute deadline and discarding more than the old cap. Fake recv raises after a bounded number
of calls if a loop is broken; no frozen-clock ablation can hang (n1). The originally
failing fake qualification test remains unchanged and is included in validation; no binary/provider probe or
qualification fixture/adoption change is introduced.

Scope enumeration (m1): run rg -n '\.response\(\)\)|_drain\(|SHUT_WR' src, and
rg -n '\.listen\(|create_server|HTTPServer|ExclusiveServer' src. The resulting sites are:

| Site | Disposition |
|---|---|
| ProviderRelay._answer | All relay refusals, including _grant/parser/TLS/upstream failures before an answer; shared staged close |
| EgressProxy._answer | CONNECT refusal and non-CONNECT 405 before body read; now shared staged close |
| dashboard.server._Listener.process_request | Prepared busy 503 before reading; shared helper with unchanged 0.1-second accept-loop budget |
| dashboard.server Handler.finish | Refusals carrying Connection: close; shared helper, no byte cap or copied algorithm |
| ExclusiveServer.shutdown_request | Common fallback after handler finish/flush, including stdlib parse refusals; skips an already-closed dashboard socket |
| stg02/server.py make_server Handler | The other HTTP server using ExclusiveServer directly; pre-body duplicate/Host/Origin/OPTIONS/length replies now say close, so unread bytes cannot become a second request; fallback stages close |
| containment/shim.py _pump/splice/listen | Raw bidirectional forwarding, not an early HTTP answer; half-close propagates peer EOF and both pumps end before close; unchanged |
| containment/netns.py listen | Unix listener socket factory; HTTP answers are owned by the relay/proxy above |
| containment/probe.py listeners and payload | Linux echo and socket-inventory fixtures, not independent HTTP refusal writers; unchanged |
| bridge/control/operator listeners (exclusive-listener test inventory) | Unix/named-pipe framed IPC, not HTTP/TCP early answers; unchanged |

The scan is an inventory plus code inspection, not a proof against dynamic/aliased listeners; see the explicit
limits in test_exclusive_server.py's inventory. No other ExclusiveServer subclasses/direct users are present.
The dashboard endless-input regression now pins the absolute deadline rather than imposing its old byte cap.
STG-02 has a real TCP pre-body refusal/body-reuse regression. No retries, deadline raises, platform skips or
unbounded reads. This branch is fresh from origin/main, separate from #472.
