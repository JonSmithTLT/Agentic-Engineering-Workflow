**Partly built, by #362 (`2dc7a186`, 2026-11-07), and the row stays open (the register reconcile of 2026-11-26).** Both
fixes the Work names merged: `BridgeServer.wait_stopped()` waits for the listener's stop within `WAKE_TIMEOUT_S`, and
`LeadBroker.close()` and the supervisor's end call it, pinned by an injected delay in `tests/unit/test_listener_stop.py`;
and the contained refusal test asserts each part on its own with stderr in the message, through
`tests/helpers/lead_session.py`'s `refusal_of`. #362 also showed that the row's suspected mechanism, a double unlink, is
a no-op on the CI Python, and said that it does not close the row. **What remains:** naming what wrote after the
refusal's JSON in CI's failures, which the next failure's stderr now shows; the flake register's
`contained-lead-refusal` entry stays open with it. #362's own follow-on, that the hang autopsy keep a pseudo-terminal
child's stderr and exit code, is part of that.
