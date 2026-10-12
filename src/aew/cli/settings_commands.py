"""`aew settings show`: the configuration read projection (register F46.1; the F46.1 proposal §6).

A read: it renders ``Engine.configuration`` from the committed state and the files' bytes and takes no lock. With no
document it shows the inventory (every document's state, digest and write capability); `execution` shows the execution
policy field by field. It is the read half of `aew settings set` (proposed, register F46.2). Secrets are withheld by
structure (the proposal's §7); `observed` reports this terminal's environment.
"""

from __future__ import annotations

import argparse
from typing import Any

from aew.cli.commands import _add_json, _engine


def _show(a: argparse.Namespace) -> Any:
    from aew.engine.configuration import CLI_ENVIRONMENT

    result = _engine(a).configuration(a.document, observed_in=CLI_ENVIRONMENT)
    if a.json:
        return result
    from aew.util import dump_yaml

    return dump_yaml(result)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("settings", help="the project's configuration: what is set, where it comes from, and whether it "
                                        "is in force")
    ssub = p.add_subparsers(dest="settings_cmd", required=True)
    q = ssub.add_parser("show", help="show the configuration read-only: with no document, every document's state "
                                     "and digest; `execution`, the execution policy field by field (secrets withheld)")
    q.add_argument("document", nargs="?", help="the document to show field by field, `execution` (default: the "
                                               "inventory of every document)")
    _add_json(q)
    q.set_defaults(handler=_show)
