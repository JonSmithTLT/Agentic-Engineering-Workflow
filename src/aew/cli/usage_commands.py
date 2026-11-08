"""`aew usage`: the cost and usage ledger's read surface (F25, the cost and usage ledger design v0.2 R9)."""

from __future__ import annotations

import argparse
from typing import Any

from aew.cli.commands import _add_json, _engine


def _show(a: argparse.Namespace) -> Any:
    from aew.engine import usage_ops

    view = _engine(a).usage_show(a.target, walk_all=a.all, since=a.since, until=a.until)
    return usage_ops.to_json(view) if a.json else usage_ops.render_show(view)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("usage", help="tokens and derived cost of runs, invocations, units and the project")
    usub = p.add_subparsers(dest="usage_cmd", required=True)
    q = usub.add_parser("show", help="usage for a run, an invocation, a unit's tree, or the project (default: the hot "
                                     "work and the recently archived units): tokens by category and the derived "
                                     "cost, or `unpriced` with its reason")
    q.add_argument("target", nargs="?", metavar="ID",
                   help="a run (R-...), an invocation or a work unit, hot or archived")
    q.add_argument("--all", action="store_true", help="the project over every archived unit, not only the recent ones")
    q.add_argument("--since", metavar="UTC",
                   help="with --all: units archived from this time, e.g. 2026-10-01T00:00:00Z")
    q.add_argument("--until", metavar="UTC", help="with --all: units archived up to this time")
    _add_json(q)
    q.set_defaults(handler=_show)
