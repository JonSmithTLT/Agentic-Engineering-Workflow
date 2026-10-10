"""The dashboard's acceptance project (register F20.6): known records for the server's end-to-end tests and for the
web side's live browser run (``tools/dashboard/acceptance_project.py`` builds the same project into a directory).

An Epic with its plan decision, an integrated (archived) Ticket, an open Ticket, a Ticket whose title is hostile
content, and a recorded audit. The search variant (register F20.8, S2) also adopts the execution policy's
``recall.raw_history_search: explicit``, so the dashboard serves ``/history/search`` and its capability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aewflow import create_planned_ticket, create_unit, integrate, plan_unit, sample_project, to_commit_ready

ESC, RLO, PDF = chr(0x1B), chr(0x202E), chr(0x202C)
# Hostile content the engine stores as data: markup, a script breakout, an event handler, a bidi override and an
# ANSI escape. It must come back as the exact JSON string and be displayed as text, never as markup.
HOSTILE = (f"<img src=x onerror=alert(1)></script><script>alert(2)</script> {RLO}evil{PDF} "
           f"{ESC}[31mred{ESC}[0m")


class World:
    def __init__(self) -> None:
        self.ids: dict[str, str] = {}
        self.root: Path
        self.project: Any


# A term the search variant's history holds: the integrated Ticket's records name the function it added.
SEARCH_TERM = "subtract"


def build_world(tmp: Path, *, search: bool = False) -> World:
    """Build the project under ``tmp`` (its git repository is ``tmp/repo``); ``search``: the variant with raw-history
    search switched on by an adopted policy edit, as the operator would switch it on."""
    w = World()
    p = sample_project(tmp)
    epic = create_unit(p, "epic", "Calculator", cls=1)
    plan_unit(p, tmp, epic)
    done, _ = to_commit_ready(p, tmp, title="Add subtract()", extra=("--parent", epic))
    integrate(p, done)
    open_ticket = create_planned_ticket(p, tmp, title="Add apply()", extra=("--parent", epic))
    hostile = create_unit(p, "ticket", HOSTILE, cls=1, parent=epic)
    p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))
    if search:
        policy = p.root / ".aew/policy/execution.yaml"
        policy.write_text(policy.read_text(encoding="utf-8") + "recall:\n  raw_history_search: explicit\n",
                          encoding="utf-8", newline="\n")
        p.adopt_policy("switch raw-history search on for the acceptance run")
    w.ids = {"epic": epic, "done": done, "open": open_ticket, "hostile": hostile}
    w.root, w.project = p.root, p
    return w
