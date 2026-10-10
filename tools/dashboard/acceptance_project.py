#!/usr/bin/env python3
"""Build the dashboard's acceptance project into a directory, for the live browser run (register F20.6).

    python tools/dashboard/acceptance_project.py <empty-dir>
    aew -C <empty-dir>/repo dashboard serve          # at your terminal: confirm the code; the URL is written there
    aew -C <empty-dir>/repo dashboard open           # (or) a further session URL for the session file

The project is the one ``tests/integration/test_dashboard_acceptance.py`` uses (``tests/helpers/dashboard_world.py``):
an Epic with its plan decision, an integrated (archived) Ticket, an open Ticket, a Ticket whose title is hostile
content, and an audit; and, for the maps pages (contract 0.1.3, register F20.8), a structural map generated and
selected and a discovery record selected as the architecture reference (ids ``map`` and ``architecture``). It needs a
development install (the test helpers drive the CLI). The tool prints the project's root and its record ids as JSON,
which the browser runner's live assertions can be given; no credential is made or printed (the session comes from
``aew dashboard serve`` and ``tools/dashboard/session_file.py``).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        raise SystemExit("usage: acceptance_project.py <empty-dir>")
    target = Path(args[0]).resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests" / "helpers")]
    from dashboard_world import HOSTILE, build_world

    world = build_world(target, maps=True)
    record = {"root": str(world.root), "ids": world.ids, "hostile_title": HOSTILE}
    print(json.dumps(record, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
