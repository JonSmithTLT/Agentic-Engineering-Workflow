"""The typed surface's adapter input error (typed-lead-surface-design-v0.2 §3.3, §12.8). Dependency-free, so a
transport that must not import the engine (``aew lead mcp``) can still report one."""

from __future__ import annotations

from typing import Any

CODES = ("INVALID_ARGUMENTS", "UNKNOWN_TOOL", "TOOL_NOT_BUILT", "TOOL_NOT_EXPOSED", "BROKER_UNREACHABLE")


class AdapterInputError(Exception):
    """A transport-level input error: the call never reached the runner, or the broker could not be reached, and
    nothing committed. Deliberately not an ``AEWError``: it is not the engine's answer."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        if code not in CODES:
            raise ValueError(f"unknown adapter input error code {code!r}")
        super().__init__(message)
        self.code, self.message, self.details = code, message, details

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": dict(self.details)}
