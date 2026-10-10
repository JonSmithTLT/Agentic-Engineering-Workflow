#!/usr/bin/env python3
"""Build the dashboard's acceptance project into a directory, for the live browser run (register F20.6).

    python tools/dashboard/acceptance_project.py [--search] <empty-dir>
    aew -C <empty-dir>/repo dashboard serve          # at your terminal: confirm the code; the URL is written there
    aew -C <empty-dir>/repo dashboard open           # (or) a further session URL for the session file

The project is the one ``tests/integration/test_dashboard_acceptance.py`` uses (``tests/helpers/dashboard_world.py``):
an Epic with its plan decision, an integrated (archived) Ticket, an open Ticket, a Ticket whose title is hostile
content, and an audit. It needs a development install (the test helpers drive the CLI). The tool prints the
project's root and its record ids as JSON, which the browser runner's live assertions can be given; no credential is
made or printed (the session comes from ``aew dashboard serve`` and ``tools/dashboard/session_file.py``).

``--search`` builds the variant with raw-history search switched on by an adopted policy edit (register F20.8, S2):
the server then offers the ``history_search`` capability and ``/history/search``, and the record names a term the
history holds. Without it, the search is off and absent, as on any project that has not adopted it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    search = "--search" in args
    args = [a for a in args if a != "--search"]
    if len(args) != 1:
        raise SystemExit("usage: acceptance_project.py [--search] <empty-dir>")
    target = Path(args[0]).resolve()
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "tests" / "helpers")]
    from dashboard_world import HOSTILE, SEARCH_TERM, build_world

    world = build_world(target, search=search)
    record: dict[str, object] = {"root": str(world.root), "ids": world.ids, "hostile_title": HOSTILE,
                                 "history_search": search}
    if search:
        record["search_term"] = SEARCH_TERM
    print(json.dumps(record, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
