"""What a Lead-surface result may carry: credential-bearing keys dropped, credential strings redacted.

The runner scrubs the whole result (:mod:`aew.surface.run`, PR #88 review), and the readable text scrubs what it renders
(:mod:`aew.surface.readable`). It lives apart because the MCP transport imports no engine code, and the runner does.
"""

from __future__ import annotations

from aew.harness.contract import SECRET_KEYS, scrub

__all__ = ["SECRET_KEYS", "scrub"]
