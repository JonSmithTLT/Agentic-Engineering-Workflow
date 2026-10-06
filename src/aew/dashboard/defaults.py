"""The dashboard's defaults, importable without the server stack: the CLI builds its parser from these on every command
(`aew status` included), and must not pay for importing the server to do it (CI redesign P2)."""

from __future__ import annotations

DEFAULT_PORT = 4280  # the dashboard API track's port (operator, 2026-10-05)
DEFAULT_HOURS = 24  # a browser session's lifetime
MIN_HOURS, MAX_HOURS = 1, 168
