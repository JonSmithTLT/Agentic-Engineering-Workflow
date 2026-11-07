"""The capability names checks are keyed by.

They are steering's names (steering design §7), which each adapter will declare in code as
``<Adapter>.harness_capabilities`` once steering PR 1 (#354) merges. Until then this list stands in for that
declaration, so a run already answers "does this binary still have every capability its adapter declares?".

Follow-on, when #354 merges: read the adapter's own declaration (and ``harness_capabilities.CAPABILITIES``) here
instead of this list, and delete it, so the names have one owner.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The eight names #354 defines, with its meanings (local until #354 merges; then derived from it).
CAPABILITIES: dict[str, str] = {
    "wake_idle_session": "post input that starts an idle session's turn",
    "queue_until_turn_end": "input admitted when the current turn ends",
    "steer_running_turn": "input admitted at the running turn's next step",
    "interrupt_turn": "stop the current turn and keep the session",
    "read_progress": "read the worker's tool calls: paths, commands and exit codes",
    "read_usage": "read the worker's token usage",
    "attach_to_operator_session": "reach the session the operator is talking to",
    "mark_non_operator_input": "input the model can tell from the operator's",
}


def declared_capabilities(adapter: Any) -> Mapping[str, str]:
    """The capabilities ``adapter`` declares: its own ``harness_capabilities`` when it has one (after #354), else
    every name above (OpenCode's adapter in #354 declares all eight, as yes or partial)."""
    own = getattr(adapter, "harness_capabilities", None)
    if isinstance(own, Mapping):
        return {name: str(getattr(s, "how", s)) for name, s in own.items()}
    return dict(CAPABILITIES)
