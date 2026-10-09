"""`aew operator` and `aew lead mode` (M4-E E2; plan v3 §2.1; A1 §1).

``aew operator serve --dev`` runs the operator endpoint in the operator's own terminal; its console shows the
one-time codes. ``aew lead mode raise`` only sends a request to it and reads the code typed at this terminal: it has
no engine path of its own. ``aew lead mode lower`` is the Lead's (a restriction), relayed in a Lead session like any
Lead-reachable command. The Lead broker refuses ``raise``, ``serve`` and ``ping`` in a Lead session
(``lead_broker.OPERATOR_ENDPOINT``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from aew.cli.commands import _add_json, _add_lead, _engine, _lead_token
from aew.errors import OperatorAuthorizationRequired

# The endpoint module (the one constructor of an OperatorPrincipal) is imported only by `aew operator serve`'s handler.


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("operator", help="the operator endpoint: the only way to raise the Lead's steering mode "
                                        "(run it in your own terminal)")
    osub = p.add_subparsers(dest="operator_cmd", required=True)
    q = osub.add_parser("serve", help="run this project's operator endpoint here until interrupted; its console shows "
                                      "the one-time codes the operator types at the requesting terminal")
    q.add_argument("--dev", action="store_true",
                   help="required: on this host the operator principal cannot be shown distinct from the Lead "
                        "host's, so every record is labelled `guarantee: dev` (not production authority until F18.6)")
    q.set_defaults(handler=_serve)
    q = osub.add_parser("ping", help="whether this project's operator endpoint answers, and its guarantee label")
    _add_json(q)
    q.set_defaults(handler=_ping)


def register_lead_mode(lsub: argparse._SubParsersAction) -> None:
    p = lsub.add_parser("mode", help="the Lead's steering mode: the operator raises it at the operator endpoint; the "
                                     "Lead may lower it for its own generation")
    msub = p.add_subparsers(dest="mode_cmd", required=True)
    q = msub.add_parser("raise", help="ask the operator endpoint to raise the mode for the current Lead generation "
                                      "(its console shows a code; type it here)")
    q.add_argument("mode", choices=["walk", "run"])
    _add_json(q)
    q.set_defaults(handler=_raise)
    q = msub.add_parser("lower", help="lower the mode for the current Lead generation (the Lead's own restriction)")
    q.add_argument("mode", choices=["crawl", "walk"])
    q.add_argument("--rationale", default="", help="recorded with the change")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).steering_lower(token=_lead_token(a), expect_rev=a.expect_rev,
                                                              mode=a.mode, rationale=a.rationale))


def _serve(a: argparse.Namespace) -> None:
    from aew.cli.dashboard_commands import console
    from aew.harness import operator_client, operator_endpoint

    engine = _engine(a)
    endpoint = operator_endpoint.OperatorEndpoint(engine, console=console, dev=a.dev)
    operator_endpoint.harden()  # before any challenge exists in this process's memory
    endpoint.start()
    sys.stdout.write(json.dumps({"ok": True, "pid": endpoint.pid, "guarantee": "dev",
                                 "locator": operator_client.LOCATOR_REL,
                                 "stop": "interrupt this command (Ctrl-C)"}, indent=2) + "\n")
    sys.stdout.flush()
    endpoint.serve_forever()


def _ping(a: argparse.Namespace) -> Any:
    from aew.harness import operator_client

    return operator_client.ping(_engine(a).aew_root)


def _raise(a: argparse.Namespace) -> Any:
    from aew import operator
    from aew.harness import operator_client

    engine = _engine(a)
    if not operator.has_terminal():
        # Refused before the endpoint is contacted: a requester that cannot type the code back must never put a
        # challenge on the operator's console (as `aew dashboard open`).
        raise OperatorAuthorizationRequired(
            "`aew lead mode raise` reads the confirmation code from your terminal, and this process has none (a "
            "harness tool call, a pipe or a scheduled job); run it yourself in a terminal", detail="no terminal")
    return operator_client.request_raise(engine.aew_root, a.mode)
