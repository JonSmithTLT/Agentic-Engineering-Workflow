"""Harness capabilities: what each harness adapter provides, and what each steering feature needs (steering design §7).

The operator's rule: a feature is "supported on both" harnesses, or its gap is "noted as work for us to add to the AEW
build of Codex" (or of OpenCode). So:

- each adapter **declares** the capabilities it provides, in code: ``OpenCodeAdapter.harness_capabilities``
  (``aew.harness.opencode.adapter``). Codex has no adapter yet, so its column is recorded here (:data:`CODEX`), from
  steering PR 0's probe of the Codex 0.160.0 app-server and the 0.162.1 standalone app-server. The Codex adapter
  declares its own when it lands, and this table goes;
- each feature **names** the capabilities it needs (:data:`FEATURES`);
- :func:`problems` lists every feature that needs a capability an adapter neither provides nor marks as a gap with a
  register row. ``tests/integration/test_harness_capabilities.py`` fails on any, and the generated reference renders the
  table (``docs/reference/harness-capabilities.md``).

"Supported on both" never makes OpenCode wait: an OpenCode feature ships once its Codex rows are recorded here,
whether supported or a gap with its register row.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

OPENCODE, CODEX_NAME = "opencode", "codex"

# Each capability, and what it means (the steering design §7's names).
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

# Each steering feature, the capabilities it needs, and the steering pull request that builds it.
FEATURES: dict[str, tuple[tuple[str, ...], str]] = {
    "progress_digest": (("read_progress", "read_usage"), "steering PR 1"),
    "push_wake": (("wake_idle_session", "queue_until_turn_end", "attach_to_operator_session",
                   "mark_non_operator_input"), "steering PR 2"),
    "steer_worker": (("steer_running_turn",), "messaging MS5"),
    "interrupt_worker": (("interrupt_turn",), "steering design §3"),
}

# yes: the harness provides it. partial: it provides it in a weaker form the feature's design accepts, which the
# declaration's text says (OpenCode's non-operator mark is a text header the model reads, not a role of its own).
# gap: it does not, and a register row holds the work.
YES, PARTIAL, GAP = "yes", "partial", "gap"


class Support(NamedTuple):
    """One capability on one harness: ``yes``, ``partial`` or ``gap``; how it is provided (or what the gap is); and,
    for a gap, the register row that holds the work."""

    status: str
    how: str
    register: str | None = None


# Codex's column, recorded from steering PR 0 until the Codex adapter declares its own. Register row F24 is the Codex
# adapter; its note of 2026-11-07 lists these rows as its work.
CODEX: dict[str, Support] = {
    "wake_idle_session": Support(YES, "`turn/start` on an idle thread"),
    "queue_until_turn_end": Support(GAP, "`turn/start` on a busy thread steers the running turn and there is no "
                                         "native queue: the adapter holds a wake until `thread/status/changed` "
                                         "reports idle", "F24"),
    "steer_running_turn": Support(YES, "`turn/steer` with `expectedTurnId`"),
    "interrupt_turn": Support(YES, "`turn/interrupt`"),
    "read_progress": Support(YES, "pushed: `item/started`, `item/completed`, `item/commandExecution/*`, "
                                  "`item/fileChange/patchUpdated` (not probed yet)"),
    "read_usage": Support(YES, "pushed: `thread/tokenUsage/updated` (not probed yet)"),
    "attach_to_operator_session": Support(GAP, "AEW hosts the Lead's app-server (`--listen unix://` or a loopback "
                                               "`ws://` with a token) and the operator runs `codex --remote`: the "
                                               "adapter's launch shape", "F24"),
    "mark_non_operator_input": Support(YES, "`thread/inject_items` with a developer-role message, and the text "
                                            "header"),
}


def declarations() -> dict[str, Mapping[str, Support]]:
    """Every harness's column: an adapter's own declaration, or the recorded column of a harness with no adapter."""
    from aew.harness.opencode.adapter import OpenCodeAdapter

    return {OPENCODE: OpenCodeAdapter.harness_capabilities, CODEX_NAME: CODEX}


def problems(columns: Mapping[str, Mapping[str, Support]] | None = None) -> list[str]:
    """Each (harness, feature, capability) a feature needs that the harness neither provides nor marks as a gap with a
    register row; and each declared name that is not a capability."""
    out: list[str] = []
    for harness, column in sorted((columns if columns is not None else declarations()).items()):
        out += [f"{harness}: {name!r} is not a capability" for name in sorted(set(column) - set(CAPABILITIES))]
        for feature, (needs, _) in sorted(FEATURES.items()):
            for cap in needs:
                s = column.get(cap)
                if s is None:
                    out.append(f"{harness}: {feature} needs {cap}, which is neither declared nor a gap")
                elif s.status == GAP and not s.register:
                    out.append(f"{harness}: {feature} needs {cap}, a gap with no register row")
                elif s.status not in (YES, PARTIAL, GAP):
                    out.append(f"{harness}: {cap} has status {s.status!r}, not yes, partial or gap")
    return out
