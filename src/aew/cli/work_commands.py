"""Work graph, plan, invocation, evidence and integration commands."""

from __future__ import annotations

import argparse
import os
from typing import Any

from aew.cli.commands import _add_json, _add_lead, _engine, _lead_token, _read_text_arg
from aew.errors import UsageError


def _inv_token(args: argparse.Namespace) -> str:
    token = getattr(args, "invocation_token", None) or os.environ.get("AEW_INVOCATION_TOKEN")
    if not token:
        raise UsageError("invocation credential required: pass --invocation-token or set AEW_INVOCATION_TOKEN")
    return token


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("work", help="Epic/Story/Ticket records and Lead transitions")
    wsub = p.add_subparsers(dest="work_cmd", required=True)

    q = wsub.add_parser("create", help="create a Ticket, Story or Epic (Lead)")
    q.add_argument("kind", choices=["ticket", "story", "epic"])
    q.add_argument("--title", required=True)
    q.add_argument("--class", dest="risk_class", type=int, required=True, choices=range(0, 5))
    q.add_argument("--parent")
    q.add_argument("--depends-on", action="append", default=[], metavar="ID[:mutating|evidence]")
    q.add_argument("--non-mutating", action="store_true", help="Ticket changes no source (evidence only)")
    q.add_argument("--scope", action="append", default=[], metavar="GLOB", help="allowed change paths")
    q.add_argument("--goal", action="append", default=[], help="goal-backwards acceptance criterion")
    q.add_argument("--contract", action="append", default=[], help="contract/conformance criterion")
    q.add_argument("--mandatory-gate", action="append", default=[], help="Story/Epic: non-waivable gate for descendants")
    q.add_argument("--min-descendant-class", type=int, choices=range(0, 5))
    q.add_argument("--rationale")
    q.add_argument("--external-ref", action="append", default=[])
    q.add_argument("--body-file", help="Markdown objective/body (file or - for stdin)")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_create(
        token=_lead_token(a), expect_rev=a.expect_rev, kind=a.kind, title=a.title, risk_class=a.risk_class,
        mutating=not a.non_mutating, parent=a.parent, depends_on=a.depends_on, scope_paths=a.scope,
        goal_backwards=a.goal, contract=a.contract, mandatory_gates=a.mandatory_gate,
        min_descendant_class=a.min_descendant_class, rationale=a.rationale, external_refs=a.external_ref,
        body=_read_text_arg(a.body_file)))

    q = wsub.add_parser("show")
    q.add_argument("work_id")
    q.set_defaults(handler=lambda a: _engine(a).work_show(a.work_id))

    q = wsub.add_parser("list")
    q.add_argument("--state")
    q.set_defaults(handler=lambda a: _engine(a).work_list(state_filter=a.state))

    q = wsub.add_parser("ready", help="Tickets ready for assignment")
    q.set_defaults(handler=lambda a: _engine(a).work_list(state_filter="READY"))

    q = wsub.add_parser("transition", help="Lead transition (guards and reasons enforced)")
    q.add_argument("work_id")
    q.add_argument("--to", required=True)
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_transition(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, to=a.to, reason=a.reason))

    q = wsub.add_parser("reconcile", help="reconcile an INTERRUPTED Ticket after inspection (Lead)")
    q.add_argument("work_id")
    q.add_argument("--to", required=True)
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_reconcile(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, to=a.to, reason=a.reason))

    p = sub.add_parser("plan", help="plan revisions (immutable once accepted)")
    psub = p.add_subparsers(dest="plan_cmd", required=True)
    q = psub.add_parser("propose")
    q.add_argument("work_id")
    q.add_argument("--file", required=True, help="plan body (Markdown; file or - for stdin)")
    q.add_argument("--reason")
    q.add_argument("--affected", action="append", default=[], metavar="PATH")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).plan_propose(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, body=_read_text_arg(a.file),
        reason=a.reason, affected_paths=a.affected))
    q = psub.add_parser("accept")
    q.add_argument("work_id")
    q.add_argument("--revision", type=int, required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).plan_accept(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, revision=a.revision))

    _register_later_steps(sub)


def _register_later_steps(sub: argparse._SubParsersAction) -> Any:
    return None
