"""The two delivery timings of a Lead message to a running agent, and the harness mode each is posted with (F9-A plan
v4 amendment 2 §1.1; the designer's decision of 2026-10-10; register E55).

`next-step`, the default, is OpenCode's `steer` (admitted at the next step boundary, without interrupting the agent);
`turn-end` is `queue` (admitted only when the agent's turn would end; the MS0 probe's P1 and P2). One constant, so
`aew harness send` and the F9 delivery loop can never disagree.

A leaf module, outside `aew.coordination`: `harness send` exists with coordination messaging off, and the CLI, the
supervisor and the harness operations read these values without importing coordination (F9 invariant 1, pinned by
`test_legality_modules_never_import_coordination`). `aew.coordination.layout` re-exports them for the F9 side.
"""

from __future__ import annotations

WHEN_DELIVERY = {"next-step": "steer", "turn-end": "queue"}
NEXT_STEP, TURN_END = "next-step", "turn-end"
DEFAULT_WHEN = NEXT_STEP
