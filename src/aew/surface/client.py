"""The client side of the typed Lead surface inside a Lead session (F15.1 plan §4, §6).

A transport inside a Lead session never runs the surface itself: it forwards each call to the session's Lead broker
(``lead.tool``), which holds the Lead credential and runs the one runner. This module holds no credential and imports
no engine code, so a transport built on it (``aew lead mcp``) cannot hold authority of its own.

Two failures stay distinct: the broker *answering* that the session's authority is gone is a ``StageResult`` (it read
committed state); the broker being *unreachable* is an adapter error, ``BROKER_UNREACHABLE``, and nothing about AEW's
state is claimed.
"""

from __future__ import annotations

import json
import os
from typing import Any

from aew import errors
from aew.harness import bridge
from aew.surface.errors import AdapterInputError

ENV_ENDPOINT = "AEW_LEAD_BROKER"  # the same names as aew.harness.lead_broker (tested), without importing it
ENV_KEY = "AEW_LEAD_BROKER_KEY"
ENV_NAMES = (ENV_ENDPOINT, ENV_KEY)


def in_session() -> bool:
    return bool(os.environ.get(ENV_ENDPOINT))


def forward(name: str, arguments: Any, *, ingress: str, profile: str) -> dict[str, Any]:
    """One call through the session's broker: its ``StageResult``, or ``AdapterInputError``."""
    try:
        reply = bridge.call("lead.tool", {"name": name, "arguments": json.dumps(arguments), "ingress": ingress,
                                          "profile": profile}, env_names=ENV_NAMES)
    except (errors.StaleAuthority, errors.PermissionDenied, errors.UsageError) as exc:
        # Not reached, refused the key, or no bridge at all: the broker said nothing about AEW's state.
        raise AdapterInputError("BROKER_UNREACHABLE", f"the Lead broker could not be reached: {exc.message}",
                                cause=exc.code) from None
    if "adapter_input_error" in reply:
        e = reply["adapter_input_error"]
        raise AdapterInputError(e["code"], e["message"], **(e.get("details") or {}))
    return reply["stage_result"]
