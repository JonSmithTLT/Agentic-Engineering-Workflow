"""`aew message`: the operator's coordination reads (register F9, F9-A MS2; ADR-0017; plan v4 D-24, D-31, D-38).

Registered only while the project's switch is on or a thread exists (``main.coordination_reads_for``), and never inside
a worker's run, so no worker is offered a command that reads other threads (D-21). Off, the parser is exactly the one
without it. The worker's own commands (`reply`, `read`, `wait`) are MS4's.
"""

from __future__ import annotations

import argparse
import os

from aew.cli.commands import _add_json, _engine


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("message", help="coordination messages between the Lead and its workers: read a thread, a "
                                       "unit's threads, or the sealed replies no Lead has seen (read-only)")
    msub = p.add_subparsers(dest="message_cmd", required=True)

    q = msub.add_parser("thread", help="one invocation's thread: its messages and their delivery facts, and its seal "
                                       "once the invocation has ended")
    q.add_argument("invocation", metavar="INV")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).message_thread(a.invocation))

    q = msub.add_parser("list", help="a unit's threads, hot or archived: their state, counts and latest messages")
    q.add_argument("--work", required=True, metavar="WORK-ID")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).message_list(a.work))

    q = msub.add_parser("unseen", help="sealed worker messages beyond the Lead's attention list, recovered from their "
                                       "seals; with the Lead's credential they are recorded as shown")
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN): records the listed messages as shown, so "
                                   "the next commit clears the omitted count")
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).message_unseen(
        token=a.token or os.environ.get("AEW_LEAD_TOKEN") or None))
