"""The typed Lead surface (register F15.1; typed-lead-surface-design-v0.2, governing since 2026-10-05).

The Lead's interface is a catalog of typed actions defined once below transport (:mod:`aew.surface.contract`) plus
one runner (:mod:`aew.surface.run`). Every valid call returns the same ``StageResult`` with an ``ActionProjection``
(:mod:`aew.surface.projection`; ``schemas/surface.schema.json``). Transports (the ``aew-lead`` MCP server and
``aew lead tool``) carry arguments in and a ``StageResult`` out; none decides legality, retries judgment, widens
authority or invents next actions. The engine remains the sole legality and workflow authority, and it never imports
this package.
"""

from __future__ import annotations

SURFACE = "aew/surface/v1"
SERVER_NAME = "aew-lead"  # the Lead's MCP server; `aew-run` and `aew-knowledge` are separate namespaces (§12.6)
