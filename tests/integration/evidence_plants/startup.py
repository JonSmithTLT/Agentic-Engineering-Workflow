"""A lane cancelled during start-up, selected by explicit path in the hosted proof's start-up control (register E3;
review of #579, M1). Each xdist worker holds its collection at this module's import, so whenever the control's
cancellation arrives, no test has started. The twin barrier aligns both plants' 360 s deadlines, and the control
cancels about 90 s into their lanes, well inside the hold."""

import os
import threading

KIND = os.environ.get("AEW_EVIDENCE_PLANT", "disabled")
HOLD_S = 330  # inside the plant's 360 s session deadline, and well past the control's trigger

if KIND == "cancel-start" and os.environ.get("PYTEST_XDIST_WORKER"):
    threading.Event().wait(HOLD_S)


def test_start_up_held_until_cancelled():
    assert KIND != "cancel-start", "plant misfired: the start-up hold ended before its cancellation"
