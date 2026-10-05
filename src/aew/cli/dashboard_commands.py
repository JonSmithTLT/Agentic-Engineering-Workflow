"""`aew dashboard`: serve the read-only dashboard, open a browser session, show its status (register F20.3; the design
note §4.2 and §5.2; ADR-0005, amendment of 2026-10-05).

``serve`` and ``open`` are credential-emitting commands (ADR-0009): the one-time session URL goes only to the
operator's terminal unless ``--print-credential`` puts it on standard output for a script, and a Lead session refuses
both. Authorization is the operator's typed-back code: at this terminal for ``serve``, at the serving process's console
for ``open``. No flag, environment variable, stdin input or file authorizes a session.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from aew import operator
from aew.cli import credentials
from aew.cli.commands import _add_json, _engine
from aew.dashboard import control, service
from aew.dashboard.session import DEFAULT_HOURS, MAX_HOURS, MIN_HOURS
from aew.errors import NotFound, OperatorAuthorizationRequired, UsageError


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("dashboard", help="the read-only dashboard: serve it on 127.0.0.1, open a browser session, "
                                         "see its status")
    dsub = p.add_subparsers(dest="dashboard_cmd", required=True)

    q = dsub.add_parser("serve", help="start the dashboard server from this terminal (you confirm with a typed-back "
                                      "code) and get the first one-time session URL; runs until interrupted")
    q.add_argument("--port", type=int, default=service.DEFAULT_PORT,
                   help=f"TCP port on 127.0.0.1 (default {service.DEFAULT_PORT}; 0 for an ephemeral port). An "
                        "occupied port is an error, never a silent move to another port")
    q.add_argument("--session-hours", type=int, default=DEFAULT_HOURS,
                   help=f"how long a browser session lasts, {MIN_HOURS} to {MAX_HOURS} (default {DEFAULT_HOURS})")
    _add_json(q)
    q.set_defaults(handler=_serve)

    q = dsub.add_parser("open", help="ask the running server for a new one-time session URL: its console shows a "
                                     "code, which you type here")
    _add_json(q)
    q.set_defaults(handler=_open)

    q = dsub.add_parser("status", help="whether a dashboard server runs for this project, and its live sessions "
                                       "(ids and times, never secrets)")
    _add_json(q)
    q.set_defaults(handler=_status)


def console(text: str) -> None:
    """The serving process's console, where `aew dashboard open` challenges are shown (never stdout)."""
    out = credentials._open_terminal()  # noqa: SLF001 (the one terminal path, shared with credential delivery)
    if out is None:
        raise OperatorAuthorizationRequired("the dashboard server has no console to show a confirmation code on, so "
                                            "no new session can be authorized; restart `aew dashboard serve` at a "
                                            "terminal")
    with out:
        out.write(text)
        out.flush()


def _serve(a: argparse.Namespace) -> None:
    if not MIN_HOURS <= a.session_hours <= MAX_HOURS:
        raise UsageError(f"--session-hours is {MIN_HOURS} to {MAX_HOURS}")
    if not 0 <= a.port <= 65535:
        raise UsageError("--port is 0 to 65535")
    engine = _engine(a)
    svc = service.Service(engine, port=a.port, hours=a.session_hours, console=console)
    try:
        operator.authorize(f"START the read-only dashboard of project {svc.project_id} on {svc.url} and ISSUE a "
                           f"browser session of {a.session_hours} h")
    except BaseException:
        svc.close()
        raise
    svc.start()
    url = svc.issue()
    to_stdout = bool(getattr(a, "print_credential", False))
    if not to_stdout:
        credentials.write_to_terminal("session_url", url)
    status: dict[str, Any] = {"ok": True, "url": svc.url, "port": svc.port, "pid": svc.status()["pid"],
                              "session_hours": a.session_hours,
                              "session_url": url if to_stdout else credentials.WRITTEN,
                              "endpoint_file": service.SERVER_JSON_REL,
                              "stop": "interrupt this command (Ctrl-C); every session ends with it"}
    sys.stdout.write(json.dumps(status, indent=2) + "\n")
    sys.stdout.flush()
    try:
        svc.wait()
    finally:
        svc.stop()


def _open(a: argparse.Namespace) -> dict[str, Any]:
    engine = _engine(a)
    if not operator.has_terminal():
        # Refused before the server is contacted: a requester that cannot type the code back must never put a
        # challenge on the operator's console (lead developer's review).
        raise OperatorAuthorizationRequired(
            "`aew dashboard open` reads the confirmation code from your terminal, and this process has none (a "
            "harness tool call, a pipe or a scheduled job); run it yourself in a terminal", detail="no terminal")
    found = service.locate(engine.aew_root)
    if found is None:
        raise NotFound("no dashboard server is running for this project; start one with `aew dashboard serve`")
    result = control.request_session(found["endpoint"], found["key"])
    return {"ok": True, "url": found["url"], "session_url": result["session_url"],
            "expires_at": result.get("expires_at")}


def _status(a: argparse.Namespace) -> dict[str, Any]:
    engine = _engine(a)
    found = service.locate(engine.aew_root)
    if found is None:
        return {"running": False, "start": "aew dashboard serve"}
    try:
        return control.request_status(found["endpoint"], found["key"])
    except NotFound:
        return {"running": False, "stale_endpoint": service.SERVER_JSON_REL, "start": "aew dashboard serve"}
