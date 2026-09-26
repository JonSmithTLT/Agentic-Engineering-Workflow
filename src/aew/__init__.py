"""Agent Engineering Workflow (AEW).

Implements the frozen specification set ``aew-frozen-2026-09-25``: a deterministic
state engine, durable knowledge store and role/launch-contract generator. AEW does
not run models; harnesses drive it through the ``aew`` CLI (and, later, an MCP
adapter) over one engine API.
"""

from __future__ import annotations

__version__ = "0.1.0.dev0"
SPEC_SET = "aew-frozen-2026-09-25"
