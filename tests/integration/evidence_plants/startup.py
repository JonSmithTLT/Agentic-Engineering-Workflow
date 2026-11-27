"""A lane cancelled during start-up, selected by explicit path in the hosted proof's start-up controls (register E3;
review of #579, M1). Each process that runs tests holds its collection at this module's import, so whenever the
control's cancellation arrives, no test has started: each xdist worker of the `cancel-start` plant, and the serial
`cancel-start-serial` plant's controller, which runs its tests itself. The twin barrier aligns both plants' 360 s
deadlines, and the control cancels about 90 s into their lanes, well inside the hold."""

import os
import threading

KIND = os.environ.get("AEW_EVIDENCE_PLANT", "disabled")
HOLD_S = 330  # inside the plant's 360 s session deadline, and well past the control's trigger

KINDS = ("cancel-start", "cancel-start-serial")

if KIND == ("cancel-start" if os.environ.get("PYTEST_XDIST_WORKER") else "cancel-start-serial"):
    threading.Event().wait(HOLD_S)


def test_start_up_held_until_cancelled():
    assert KIND not in KINDS, "plant misfired: the start-up hold ended before its cancellation"
