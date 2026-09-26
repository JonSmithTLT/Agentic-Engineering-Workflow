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
    q.add_argument("--card", help="role card that executes this Ticket (recorded in its role plan)")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_create(
        token=_lead_token(a), expect_rev=a.expect_rev, kind=a.kind, title=a.title, risk_class=a.risk_class,
        mutating=not a.non_mutating, parent=a.parent, depends_on=a.depends_on, scope_paths=a.scope,
        goal_backwards=a.goal, contract=a.contract, mandatory_gates=a.mandatory_gate,
        min_descendant_class=a.min_descendant_class, rationale=a.rationale, external_refs=a.external_ref,
        body=_read_text_arg(a.body_file), card=a.card))

    q = wsub.add_parser("show")
    q.add_argument("work_id")
    q.set_defaults(handler=lambda a: _engine(a).work_show(a.work_id))

    q = wsub.add_parser("list")
    q.add_argument("--state")
    q.set_defaults(handler=lambda a: _engine(a).work_list(state_filter=a.state))

    q = wsub.add_parser("ready", help="Tickets ready for assignment")
    q.set_defaults(handler=lambda a: _engine(a).work_list(state_filter="READY"))

    q = wsub.add_parser("assign", help="READY -> ASSIGNED: workspace + implementer invocation (Lead)")
    q.add_argument("work_id")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_assign(token=_lead_token(a), expect_rev=a.expect_rev,
                                                           work_id=a.work_id))

    q = wsub.add_parser("roles", help="show a Ticket's stored and effective role plan")
    q.add_argument("work_id")
    q.set_defaults(handler=lambda a: _engine(a).work_roles(a.work_id))

    q = wsub.add_parser("staff", help="select role cards for a Ticket's execute/review/verify slots (Lead)")
    q.add_argument("work_id")
    q.add_argument("--execute", action="append", default=[], metavar="CARD")
    q.add_argument("--review", action="append", default=[], metavar="CARD")
    q.add_argument("--verify", action="append", default=[], metavar="CARD")
    q.add_argument("--forbid", action="append", default=[], metavar="CARD")
    q.add_argument("--remove", action="append", default=[], metavar="SLOT=CARD")
    q.add_argument("--by", choices=["lead", "operator"], default="lead",
                   help="who made the selection (operator = recorded on the operator's instruction)")
    q.add_argument("--pin", action="store_true", help="pin the selection (Lead may replace only with --reason)")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_staff(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, execute=a.execute, review=a.review,
        verify=a.verify, forbid=a.forbid, remove=a.remove, selected_by=a.by, pin=a.pin, reason=a.reason))

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

    p = sub.add_parser("role", help="role archetypes and the role-card catalog (deck)")
    rsub = p.add_subparsers(dest="role_cmd", required=True)
    q = rsub.add_parser("list", help="built-in and project role cards")
    q.set_defaults(handler=lambda a: _engine(a).role_list())
    q = rsub.add_parser("show")
    q.add_argument("card")
    q.set_defaults(handler=lambda a: _engine(a).role_show(a.card))
    q = rsub.add_parser("validate", help="validate the project catalog, or one card file")
    q.add_argument("--file")
    q.set_defaults(handler=lambda a: _engine(a).role_validate(a.file))

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
    p = sub.add_parser("invoke", help="bounded role invocations (Lead dispatches; roles never self-assign)")
    isub = p.add_subparsers(dest="invoke_cmd", required=True)
    q = isub.add_parser("create", help="dispatch a role card (explicit, from the role plan, or the default)")
    q.add_argument("work_id")
    q.add_argument("--card", help="role card id (see `aew role list`)")
    q.add_argument("--role", choices=["implementer", "reviewer", "verifier"],
                   help="archetype; picks its default card when --card is omitted")
    q.add_argument("--scope", choices=["ticket", "integration"], default="ticket")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).invoke_create(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, role=a.role, card=a.card,
        scope=a.scope))
    q = isub.add_parser("cancel")
    q.add_argument("invocation")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).invoke_cancel(
        token=_lead_token(a), expect_rev=a.expect_rev, invocation=a.invocation, reason=a.reason))
    q = isub.add_parser("show")
    q.add_argument("invocation")
    q.set_defaults(handler=lambda a: _engine(a).invoke_show(a.invocation))

    p = sub.add_parser("context", help="bounded context packs / launch contracts")
    xsub = p.add_subparsers(dest="context_cmd", required=True)
    q = xsub.add_parser("pack", help="(re)generate an invocation's pack from durable state")
    q.add_argument("invocation")
    q.set_defaults(handler=lambda a: _engine(a).context_pack(a.invocation))
    q = xsub.add_parser("show", help="print an invocation's pack")
    q.add_argument("invocation")
    q.set_defaults(handler=lambda a: _engine(a).context_show(a.invocation))

    p = sub.add_parser("check", help="run a project-defined check as a bounded role")
    csub = p.add_subparsers(dest="check_cmd", required=True)
    q = csub.add_parser("run")
    q.add_argument("check_id", help="a check from policy/checks.yaml, or the built-in `guardrails`")
    q.add_argument("--invocation-token", help="invocation credential (or env AEW_INVOCATION_TOKEN)")
    q.set_defaults(handler=lambda a: _engine(a).check_run(invocation_token=_inv_token(a), check_id=a.check_id))

    q = sub.add_parser("submit", help="submit role evidence (implementation report, review, verification)")
    q.add_argument("--kind", required=True, choices=["implementation_report", "review", "verification"])
    q.add_argument("--file", required=True, help="Markdown with YAML frontmatter (file or - for stdin)")
    q.add_argument("--invocation-token", help="invocation credential (or env AEW_INVOCATION_TOKEN)")
    q.set_defaults(handler=lambda a: _engine(a).submit(invocation_token=_inv_token(a), kind=a.kind,
                                                      text=_read_text_arg(a.file)))

    q = sub.add_parser("gate", help="gate evaluation against the current evaluated snapshot")
    gsub = q.add_subparsers(dest="gate_cmd", required=True)
    r = gsub.add_parser("show")
    r.add_argument("work_id")
    r.set_defaults(handler=lambda a: _engine(a).gate_show(a.work_id))
    r = gsub.add_parser("waive", help="policy-bounded waiver (Lead; decision recorded)")
    r.add_argument("work_id")
    r.add_argument("--gate")
    r.add_argument("--finding")
    r.add_argument("--reason", required=True)
    _add_lead(r)
    r.set_defaults(handler=lambda a: _engine(a).waive(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, reason=a.reason, gate=a.gate,
        finding=a.finding))

    p = sub.add_parser("review", help="Lead: ingest a review report")
    rsub = p.add_subparsers(dest="review_cmd", required=True)
    q = rsub.add_parser("ingest")
    q.add_argument("work_id")
    q.add_argument("--evidence", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).review_ingest(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, evidence_id=a.evidence))

    p = sub.add_parser("verify", help="Lead: ingest verification; classify failures")
    vsub = p.add_subparsers(dest="verify_cmd", required=True)
    q = vsub.add_parser("ingest")
    q.add_argument("work_id")
    q.add_argument("--evidence", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).verify_ingest(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, evidence_id=a.evidence))
    q = vsub.add_parser("classify", help="Lead-owned verification-failure classification (WC §8)")
    q.add_argument("work_id")
    q.add_argument("--as", dest="classification", required=True,
                   choices=["LOCAL_IMPLEMENTATION_DEFECT", "PLAN_OR_DESIGN_DEFECT", "CONTRACT_VIOLATION",
                            "ENVIRONMENT_OR_EVIDENCE_BLOCKED"])
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).verify_classify(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, classification=a.classification,
        reason=a.reason))

    _register_integration(sub)


def _register_integration(sub: argparse._SubParsersAction) -> Any:
    p = sub.add_parser("integrate", help="Lead-controlled integration: validate, then publish by ref CAS")
    isub = p.add_subparsers(dest="integrate_cmd", required=True)
    for name, method, text in (
        ("prepare", "integrate_prepare", "commit the gated workspace and build the integration candidate"),
        ("publish", "integrate_publish", "CAS-publish a validated candidate onto the authoritative branch"),
        ("reconcile", "integrate_reconcile", "finish an interrupted publish after inspecting git"),
    ):
        q = isub.add_parser(name, help=text)
        q.add_argument("work_id")
        _add_lead(q)
        q.set_defaults(handler=lambda a, m=method: getattr(_engine(a), m)(
            token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id))
