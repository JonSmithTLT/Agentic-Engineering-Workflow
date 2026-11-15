"""`aew notify`: the notifiers AEW ships (register E104, minimal). The operator endpoint runs the execution policy's
``notify.command`` with one notify event on stdin; `aew notify desktop` is the default `aew init` writes there."""

from __future__ import annotations

import argparse
import sys
from typing import Any


def _desktop(a: argparse.Namespace) -> Any:
    from aew.harness import desktop_notifier

    if a.check:
        return desktop_notifier.availability()
    return desktop_notifier.show(desktop_notifier.read_event(sys.stdin.buffer))


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("notify", help="the notifiers AEW ships, which the operator endpoint runs as `notify.command`")
    nsub = p.add_subparsers(dest="notify_cmd", required=True)
    q = nsub.add_parser("desktop", help="show the notify event on stdin as one desktop notification (notify-send on "
                                        "Linux, a toast on Windows); refuses, with the fix, when no desktop session "
                                        "is present")
    q.add_argument("--check", action="store_true",
                   help="only say whether a notification can be shown here, and if not why and the fix; reads no "
                        "stdin and shows nothing")
    q.set_defaults(handler=_desktop)
