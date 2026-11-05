"""What a Lead-surface result may carry: credential-bearing keys dropped, credential strings redacted.

The runner scrubs the whole result (:mod:`aew.surface.run`, PR #88 review), and the readable text scrubs what it renders
(:mod:`aew.surface.readable`). It lives apart because the MCP transport imports no engine code, and the runner does.
"""

from __future__ import annotations

from typing import Any

from aew.harness.contract import redact

SECRET_KEYS = frozenset({"token", "invocation_token", "offer", "secret", "credential"})


def scrub(value: Any) -> Any:
    """``value`` without credential-bearing keys, and with credential strings redacted."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value
