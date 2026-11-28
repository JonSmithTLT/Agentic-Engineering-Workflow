"""The map reads' argument values and bounds (register F15.8): the one owner of the kinds, the scopes, the search
text's length and the search limits.

Each consumer takes them from here. ``aew map search``'s parser takes its `--kind` choices and its `--limit` help,
and the Lead's typed ``map`` tool (``aew.surface.contract``; the mapping series' PR A2) renders its schema from them.
The Lead broker takes the relayed search's text bound, and :mod:`aew.maps.query` checks every read against them, a
worker's included. A worker's bridge rows (``bridge.MAP_OPERATIONS``) name the arguments and their types only.

This module imports nothing, so the Lead's MCP process, which holds no authority and imports no engine code, can
render the tool's schema from it.
"""

from __future__ import annotations

SEARCH_LIMIT, SEARCH_LIMIT_MAX, TEXT_MAX = 20, 100, 200
KINDS = ("any", "path")
SCOPES = ("", "none", "ticket")
