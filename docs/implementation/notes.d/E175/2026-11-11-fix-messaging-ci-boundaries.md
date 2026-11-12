CI at 0282a0db after merging main 5c51e388 exposed three boundary problems (run 43115381438). The affected
paths harness_ops.py, lead_broker.py, worker_messages.py and the orphan test/helpers are byte-identical between
fb2947b0 and 0282a0db; this is not evidence that #445 introduced these particular defects. wake_queue.py did change:
#445 added its loop-stop filter. The previous named gate omitted test_harness_wait_any.py.

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

Exact-head q7 reproduction at 0282a0db: the original wait-any parse assertion failed, 88 other cases passed. The first
fix gate found a test-helper regression: a shared fake adapter is also constructed without start, so it has no
harness directory. Keep its behavior unchanged and put the file barrier in an orphan-only subclass instead.
That gate passed the originally reported cases but failed five neighboring helper consumers; it is not a green gate.
The serial Windows four-module diagnostic hit its 600-second session bound after nine passes (exit 70): incomplete,
not a Windows pass. Do not retry that run or raise its bound; final qualification requires the new head's CI.

Delta review CLEAR at d05f27d7, m1: extend successful-send serialization to lead.read and every deferred receipt.
The locked public receipt wrapper calls an unlocked inner helper, so the live bridge never re-enters its Lock.
The forced-boundary send/close pair now covers relayed reads too: they write only generation-local told IDs,
never durable shown facts. n1: close waits at most two seconds for the send lock, then stops even if a client write
stalls; a held-lock regression proves the bound. n2: the attribution above names the unchanged paths and explicitly
excludes wake_queue.py's merged loop-stop change. n3: the orphan barrier's guard is now thirty seconds, below
steps_done's sixty; a barrier failure is returned in the transcript and asserted directly, not lost on child stderr.

Merge with main a41a0866 (#447): preserve both seat resume/prompt selection and the messaging prepare_env callback,
after the new seat's offer and broker snapshot. A combined regression covers resumed sessions with messaging off/on.
The merge gate found six test_opencode_selects_the_seat_or_existing_credential cases whose guide_of stub did not
accept the new snapshot keyword; extend that stub, preserving every seat/credential assertion.

CI b9456c79, run 43135354992: Windows integration 9/13 failed
test_lead_wake_status.py::test_an_edit_not_yet_adopted_is_no_broker_posting_and_a_wait_doesnt_say_end_your_turn,
at its initial some_broker_posts assertion, before editing policy. The isolated Windows case passed; the exact CI
schedule is not reproduced. That assertion mixes the policy property with a live heartbeat's two-second freshness
window and concurrent file replacements. Use the existing clock/idle seams to hold only the heartbeat at its
synchronous initial record and judge it on the same test clock; the real wake/watchdog threads still detect the
actual unadopted policy edit. Keep the original positive and negative posting assertions, and additionally prove
the unmodified liveness judge calls an aged record stale. No production liveness rule, timing threshold, deadline,
platform skip or retry changes. The failing test ID was reported before another push.
