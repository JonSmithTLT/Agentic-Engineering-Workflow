"""`aew message`: operator thread reads and run-scoped worker commands (register F9, F9-A MS2/MS4; ADR-0017).

Registered only while the project's switch is on or a thread exists (``main.coordination_reads_for``), and never inside
a worker's run, so no worker is offered a command that reads other threads (D-21). Worker commands register only with
an enabled run's presentation environment; the bridge checks the immutable snapshot and current authority again.
"""

from __future__ import annotations

import argparse

from aew import lead_credential
from aew.cli.commands import _add_json, _engine, add_token


def register(sub: argparse._SubParsersAction, *, operator: bool = True, worker: bool = False) -> None:
    p = sub.add_parser("message", help="coordination messages between the Lead and its workers: read a thread, a "
                                       "unit's threads, or the sealed replies no Lead has seen (read-only)")
    msub = p.add_subparsers(dest="message_cmd", required=True)
    if worker:
        _worker(msub)
    if not operator:
        return

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
    add_token(q)
    _add_json(q)
    q.set_defaults(handler=lambda a: _engine(a).message_unseen(
        token=a.token or lead_credential.optional()))


def _worker(msub: argparse._SubParsersAction) -> None:
    from aew.coordination import layout as L
    from aew.harness import bridge
    from aew.harness.wait_binding import MAX_WAIT_S

    q = msub.add_parser("reply", help="reply to a Lead message on your own thread; coordination grants no authority")
    q.add_argument("message", metavar="MSG")
    q.add_argument("--kind", choices=L.KINDS, default="")
    q.add_argument("--ref", action="append", default=[], dest="refs")
    q.add_argument("--idempotency-id", default="")
    q.add_argument("--file", required=True, metavar="FILE|-")
    _add_json(q)
    q.set_defaults(handler=lambda a: bridge.call("message.reply", {
        "in_reply_to": a.message, "kind": a.kind, "body": bridge.read_submission(a.file), "refs": a.refs,
        "idempotency_id": a.idempotency_id}))

    q = msub.add_parser("read", help="read your own thread's last 20 messages; this consumes nothing")
    _add_json(q)
    q.set_defaults(handler=lambda a: bridge.call("message.read", {}))

    q = msub.add_parser("wait", help=f"one foreground wait, at most {MAX_WAIT_S} seconds; do not set a shorter shell "
                                    "timeout. Unsupported adapters refuse: reply and end your turn instead")
    q.add_argument("--after", default="", metavar="MSG")
    q.add_argument("--timeout", default=str(MAX_WAIT_S), dest="timeout_s", metavar="SECONDS")
    _add_json(q)
    q.set_defaults(handler=lambda a: bridge.call("message.wait", {"after": a.after, "timeout_s": a.timeout_s}))
