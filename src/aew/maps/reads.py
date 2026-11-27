"""The map reads' arguments and their bounds (register F15.8): one owner for every door to :mod:`aew.maps.query`.

A worker's bridge rows (``bridge.MAP_OPERATIONS``) and the Lead's typed ``map`` tool (``aew.surface.contract``; the
mapping series' PR A2) take these values, and the query module checks every read against them. This module imports
nothing, so the Lead's MCP process, which holds no authority and imports no engine code, can render its tool's schema
from it.
"""

from __future__ import annotations

SEARCH_LIMIT, SEARCH_LIMIT_MAX, TEXT_MAX = 20, 100, 200
KINDS = ("any", "path")
SCOPES = ("", "none", "ticket")
