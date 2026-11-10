"""A Ticket's priority levels (register E227), as the control schema owns them (``work_unit.priority.level``, highest
first). This module imports no engine code: the CLI's parser and the Lead's MCP transport, which the `aew lead mcp`
process builds without the engine, read the levels here, and so does ``aew.engine.priority``."""

from __future__ import annotations

from aew.schemas import schema

LEVELS: tuple[str, ...] = tuple(
    schema("control")["$defs"]["work_unit"]["properties"]["priority"]["properties"]["level"]["enum"])
DEFAULT = "normal"  # a Ticket drafted with no priority, or before priorities existed
LOWEST = LEVELS[-1]  # started only when no higher one is eligible; `status` shows how long it has waited
