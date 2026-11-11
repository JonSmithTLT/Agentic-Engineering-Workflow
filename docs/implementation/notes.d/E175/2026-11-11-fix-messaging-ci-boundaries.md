CI at 0282a0db after merging main 5c51e388 exposed three boundary problems (run 43115381438). The affected
implementation and orphan-test files are byte-identical between fb2947b0 and 0282a0db; this is not evidence that
#445's scheduler logic introduced them. The previous named gate omitted test_harness_wait_any.py.

- OBX-38: harness_wait's final snapshot was read again by _wait_on, once for every still-running run whose
  guidance harness_resume renders and once for the follow-on wait. Pass that snapshot through both paths. Preserve
  the original no-parse-between-commits integration assertion, including its final-read accounting.
- Typed successful-send receipts: send happened before acquiring broker serialization, so the wake's final check
  could select a just-shown body. A client closing immediately after receiving the result could also set the stop
  flag before its receipt, discarding it. Keep typed send and receipt in one serialized section; close takes that
  serialization before invalidating receipts. Receipt remains after successful send, never before. Forced-boundary
  regressions reproduce the send gap for live and sealed bodies and the close loss without probabilistic scheduling.
- The real-process orphan test started its one-second shell timer before PowerShell/CLI startup or bridge admission.
  The Windows CI failure does not prove there was an admitted wait to orphan. A test-only adapter barrier now marks
  the real captured call binding; the fake shell starts its same one-second timer after that barrier. The five-second
  message wait, one-second shell timeout, sixty-second hang guards, real shell/CLI/supervisor/bridge boundaries and
  no-DELIVERED assertion stay intact. The barrier neither supplies nor relaxes production call/step lifetime checks.

The original targeted Windows diagnostic at 0282a0db passed all six selected cases; it does not reproduce CI's
schedule. The forced send-gap and close-boundary tests fail against that head's broker implementation. No retries,
deadline raises, new runtime/provider probe, qualification change or context-pool change.
