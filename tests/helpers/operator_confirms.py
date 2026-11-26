"""The operator's confirmation of a plan acceptance or a publish, for a test that is not about it (the operator's ruling
of 2026-11-26; ``aew.engine.operator_decisions``).

In the product the operator gives it with ``aew operator confirm`` at their own terminal, through the operator
endpoint's challenge (``tests/integration/test_operator_decisions.py`` drives that path). A test whose Lead session
accepts a plan or publishes, and which tests something else, has the operator confirm it here: the endpoint's record,
with the principal the endpoint would construct, bound to exactly the plan or candidate there is now. It stands in for
the challenge, never for the decision: the session's call still needs it and still uses it up."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew import errors
from aew.engine import steering as S
from aew.engine.api import Engine


def principal() -> S.OperatorPrincipal:
    """The principal the operator endpoint constructs once its challenge is answered."""
    return S.OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                               endpoint_pid=os.getpid(), endpoint_started_at="2026-11-26T00:00:00Z")


def confirm(root: Path, decision: str, work_id: str, revision: int | None = None) -> dict[str, Any]:
    """The operator confirms ``decision`` (``plan`` or ``publish``) on ``work_id`` as it stands now."""
    engine = Engine.discover(root)
    return engine.operator_confirm(principal(), engine.operator_confirmation_preview(decision, work_id, revision))


# A scripted Lead's step that waits for the operator: the step's key, and the two commands that need a confirmation.
AFTER = "after_file"
ASKED = {("plan", "accept"): "plan", ("integrate", "publish"): "publish"}


def asked(step: dict[str, Any], sync: Path) -> dict[str, Any]:
    """A scripted Lead's `plan accept` or `integrate publish` step, made to wait until the operator has confirmed it
    (:func:`standing_by` writes the file): a Lead asks the operator and goes on at their word. The step keeps its
    place in the script, so a test's step numbers do not move."""
    decision = ASKED[tuple(step["args"][:2])]
    return {**step, AFTER: str(sync / f"operator-confirmed-{decision}-{step['args'][2]}")}


def standing_by(root: Path, steps: list[dict[str, Any]], alive: Callable[[], bool]) -> None:
    """The operator at their own terminal while a scripted Lead session runs ``steps``: as each plan or candidate the
    script waits on (:func:`asked`) comes to exist, they confirm it, and the Lead's step goes on. It ends with the
    session (``alive``). With no such step it does nothing."""
    waits = [(ASKED[tuple(s["args"][:2])], s["args"][2], Path(s[AFTER])) for s in steps if s.get(AFTER)]
    if not waits:
        return

    def watch() -> None:
        pending = [w for w in waits if not w[2].exists()]
        while pending and alive():
            for wait in list(pending):
                decision, work_id, flag = wait
                try:
                    confirm(root, decision, work_id)
                except errors.AEWError:  # nothing to confirm yet (or the store is busy): look again
                    continue
                flag.write_text("x", encoding="utf-8")
                pending.remove(wait)
            time.sleep(0.1)

    threading.Thread(target=watch, name="operator-standing-by", daemon=True).start()
