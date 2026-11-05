"""What an OpenCode Lead's model receives from a tool call: the MCP ``text`` block, as OpenCode's cut leaves it (E121).

``opencode_cut`` restates ``packages/core/src/tool-output.ts:65-110`` of the pinned tag ``v2.0.18`` (commit
``cd9a14a6``): the bound is 2,000 lines or 50 KiB, it keeps whole lines from the top and stops at the first line over
the bound, and it adds a note naming a saved file. Watched on the pinned TUI, 2026-11-04: a 67 KB one-line result
reached person and model as ``[showing 0 lines of 1; full output saved to ...]`` alone.
"""

from __future__ import annotations

import json
from typing import Any

from aew.surface.readable import JSON_MARKER

MAX_LINES = 2_000
MAX_BYTES = 50 * 1024
SAVED = "/synthetic/tool-output/tool_0"


def opencode_cut(text: str) -> str:
    """``text`` as person and model get it after OpenCode's cut (a refusal goes round the cut: ``step.ts:122``)."""
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    if len(lines) <= MAX_LINES and len(text.encode()) <= MAX_BYTES:
        return text
    kept: list[str] = []
    size = 0
    for line in lines[:MAX_LINES]:
        cost = len(line.encode()) + (1 if kept else 0)
        if size + cost > MAX_BYTES:
            break
        kept.append(line)
        size += cost
    shown = f"lines 1-{len(kept)}" if kept else "0 lines"
    return "\n".join([*kept, f"[showing {shown} of {len(lines)}; full output saved to {SAVED}]"])


def lead_json(text: str) -> dict[str, Any]:
    """The result a model reads from the text: the line after the marker."""
    lines = text.split("\n")
    marker = next(n for n, line in enumerate(lines) if line.startswith(JSON_MARKER))
    parsed = json.loads(lines[marker + 1])
    assert isinstance(parsed, dict)
    return parsed
