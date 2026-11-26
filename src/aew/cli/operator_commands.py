"""`aew operator` and `aew lead mode` (M4-E E2; plan v3 §2.1; A1 §1).

``aew operator serve --dev`` runs the operator endpoint in the operator's own terminal; its console shows the
one-time codes. ``aew operator confirm`` is the operator's confirmation, at that endpoint, of a plan acceptance or a
publish a Lead session then carries out (the operator's ruling of 2026-11-26; :mod:`aew.engine.operator_decisions`).
``aew opencode`` starts an endpoint itself, in the background, unless one is live or
``AEW_OPERATOR_AUTOSTART=off`` is set (:mod:`aew.harness.operator_autostart`). ``aew lead mode raise`` only sends a
request to it, and then reads the code typed at this terminal or,
where G3 counts, waits while the operator approves in G3's confirmer: it has no engine path of its own. ``aew lead mode
lower`` is the Lead's (a restriction), relayed in a Lead session like any Lead-reachable command. The Lead broker
refuses ``raise``, ``serve``, ``ping`` and ``confirm`` in a Lead session (``lead_broker.OPERATOR_ENDPOINT``,
``OPERATOR_CONFIRMS``).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from aew.cli.commands import _add_json, _add_prior, _approval_terminal, _engine, _lead_token
from aew.errors import OperatorAuthorizationRequired

# The endpoint module (the one constructor of an OperatorPrincipal) is imported only by `aew operator serve`'s handler.


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("operator", help="the operator endpoint: the only way to raise the Lead's steering mode (`aew "
                                        "opencode` starts one unless AEW_OPERATOR_AUTOSTART=off; or run it in your "
                                        "own terminal)")
    osub = p.add_subparsers(dest="operator_cmd", required=True)
    q = osub.add_parser("serve", help="run this project's operator endpoint here until interrupted; its console shows "
                                      "the one-time codes the operator types at the requesting terminal")
    q.add_argument("--dev", action="store_true",
                   help="required: on this host the operator principal cannot be shown distinct from the Lead "
                        "host's, so every record is labelled `guarantee: dev` (not production authority until F18.6)")
    q.add_argument("--background", action="store_true",
                   help="as `aew opencode` starts it: it stops when the Lead sessions it serves end. A request that "
                        "needs a typed code shows it in the endpoint's own window on Windows; on Linux, with no "
                        "terminal, it says to run this without --background, and stops so that can start")
    q.set_defaults(handler=_serve)
    q = osub.add_parser("confirm", help="confirm, at the operator endpoint, that the Lead may accept a Ticket's plan "
                                        "or publish its candidate: its console shows exactly what, and a code to "
                                        "type here (the operator's ruling of 2026-11-26)")
    q.add_argument("decision", choices=["plan", "publish"], help="plan: its acceptance; publish: the candidate's")
    q.add_argument("work_id")
    q.add_argument("--revision", type=int, help="the plan revision (default: the newest one proposed)")
    _add_json(q)
    q.set_defaults(handler=_confirm)
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
    _add_prior(q, "override record ID or none")
    q.set_defaults(handler=_lower)


def _lower(a: argparse.Namespace) -> Any:
    engine = _engine(a)
    token = _lead_token(a)
    prior = a.prior_value
    if prior is None and _approval_terminal(a):
        prior = engine.steering_view()["override_record"]
    return engine.steering_lower(token=token, expect_rev=a.expect_rev, mode=a.mode,
                                 rationale=a.rationale, prior_value=prior)


def _serve(a: argparse.Namespace) -> None:
    from aew.cli.dashboard_commands import console
    from aew.harness import operator_client, operator_endpoint, operator_window

    engine = _engine(a)
    if a.background:
        window = operator_window.BackgroundConsole()
        endpoint = operator_endpoint.OperatorEndpoint(engine, console=window, dev=a.dev, background=True,
                                                      console_done=window.done, code_problem=window.problem,
                                                      show_challenge=window.challenge)
    else:
        endpoint = operator_endpoint.OperatorEndpoint(engine, console=console, dev=a.dev)
    operator_endpoint.harden()  # before any challenge exists in this process's memory
    endpoint.start()
    sys.stdout.write(json.dumps({"ok": True, "pid": endpoint.pid, "guarantee": "dev",
                                 "locator": operator_client.LOCATOR_REL,
                                 "stop": "it stops when the Lead sessions it serves end" if a.background
                                 else "interrupt this command (Ctrl-C)"}, indent=2) + "\n")
    sys.stdout.flush()
    endpoint.serve_forever()


def _ping(a: argparse.Namespace) -> Any:
    from aew.harness import operator_client

    return operator_client.ping(_engine(a).aew_root)


def _confirm(a: argparse.Namespace) -> Any:
    from aew import operator
    from aew.engine import operator_decisions
    from aew.harness import operator_client

    engine = _engine(a)
    if not operator.has_terminal():
        # As a raise: a requester that cannot type the code back never puts a challenge on the operator's console.
        raise OperatorAuthorizationRequired(
            f"`{operator_decisions.command(a.decision, a.work_id)}` is answered from your terminal, with the code the "
            "operator endpoint shows, and this process has none (a harness tool call, a pipe or a scheduled job); run "
            "it yourself in a terminal", detail="no terminal")
    return operator_client.request_confirmation(engine.aew_root, a.decision, a.work_id, revision=a.revision)


def _raise(a: argparse.Namespace) -> Any:
    from aew import operator
    from aew.harness import operator_client

    engine = _engine(a)
    if not operator.has_terminal():
        # Refused before the endpoint is contacted: a requester that cannot type the code back must never put a
        # challenge on the operator's console (as `aew dashboard open`), or an approval on their confirmer.
        raise OperatorAuthorizationRequired(
            "`aew lead mode raise` is answered from your terminal (the confirmation code, or waiting while you approve "
            "in G3's confirmer), and this process has none (a harness tool call, a pipe or a scheduled job); run it "
            "yourself in a terminal", detail="no terminal")
    return operator_client.request_raise(engine.aew_root, a.mode)
