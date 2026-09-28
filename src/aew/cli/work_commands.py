"""Work graph, plan, invocation, evidence and integration commands."""

from __future__ import annotations

import argparse
import os
from typing import Any

from aew.cli.commands import _add_json, _add_lead, _engine, _lead_token, _read_text_arg
from aew.errors import UsageError
from aew.harness import bridge


def _inv_token(args: argparse.Namespace) -> str:
    token = getattr(args, "invocation_token", None) or os.environ.get("AEW_INVOCATION_TOKEN")
    if not token:
        raise UsageError("invocation credential required: pass --invocation-token or set AEW_INVOCATION_TOKEN")
    return token


def _as_invocation(args: argparse.Namespace, op: str, bridge_args: dict[str, Any], direct: Any) -> Any:
    """Act as a bounded role: with an explicit credential, or, inside a harness run that supplied none,
    through the run's custody bridge (the supervisor holds the credential; ADR-0009)."""
    explicit = getattr(args, "invocation_token", None) or os.environ.get("AEW_INVOCATION_TOKEN")
    if not explicit and bridge.available():
        return bridge.call(op, bridge_args)
    return direct(_inv_token(args))


def _submit(a: argparse.Namespace) -> Any:
    text = bridge.read_submission(a.file)  # read once: `--file -` is a stream (M3 step 8)
    return _as_invocation(a, "submit", {"kind": a.kind, "text": text},
                          lambda token: _engine(a).submit(invocation_token=token, kind=a.kind, text=text))


def _add_launch(q: argparse.ArgumentParser) -> None:
    q.add_argument("--launch", action="store_true",
                   help="start a harness run for the new invocation (ADR-0009); its credential goes to the run's "
                        "supervisor and is not printed")


def _dispatch(args: argparse.Namespace, op: str, **kwargs: Any) -> Any:
    engine = _engine(args)
    out = getattr(engine, op)(token=_lead_token(args), expect_rev=args.expect_rev,
                              execution_profile=_execution(args), launch=args.launch, **kwargs)
    return engine.launch_dispatched(out) if args.launch else out


def _add_execution(q: argparse.ArgumentParser) -> None:
    """Lead override of the execution policy for the invocation this dispatch creates (ADR-0010)."""
    g = q.add_argument_group("execution (default: policy/execution.yaml routing)")
    g.add_argument("--profile", help="execution profile to pin (recorded as selected_by: lead)")
    g.add_argument("--model", metavar="PROVIDER/MODEL", help="pin this model instead of a profile")
    g.add_argument("--effort", help="reasoning-effort variant to pin")


def _execution(args: argparse.Namespace) -> dict[str, Any] | None:
    chosen = {k: getattr(args, k, None) for k in ("profile", "model", "effort")}
    return {k: v for k, v in chosen.items() if v is not None} or None


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
    _add_execution(q)
    _add_launch(q)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _dispatch(a, "work_assign", work_id=a.work_id))

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

    # ---- M2: non-mutating Tickets (ADR-0008) and the Story/Epic lifecycle (ADR-0007)
    q = wsub.add_parser("dispatch", help="READY -> ASSIGNED for a non-mutating Ticket: executor + observation (Lead)")
    q.add_argument("work_id")
    q.add_argument("--card", help="investigator/researcher/planner card (default: the staffed or default card)")
    _add_execution(q)
    _add_launch(q)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _dispatch(a, "work_dispatch", work_id=a.work_id, card=a.card))
    q = wsub.add_parser("redispatch", help="supersede a non-mutating Ticket's attempt and start the next (Lead)")
    q.add_argument("work_id")
    q.add_argument("--reason", required=True)
    q.add_argument("--card")
    _add_execution(q)
    _add_launch(q)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _dispatch(a, "work_redispatch", work_id=a.work_id, reason=a.reason,
                                               card=a.card))
    q = wsub.add_parser("accept", help="accept a non-mutating Ticket's record: -> DONE (Lead)")
    q.add_argument("work_id")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_accept(token=_lead_token(a), expect_rev=a.expect_rev,
                                                           work_id=a.work_id, reason=a.reason))
    q = wsub.add_parser("close", help="close a Story/Epic after its children and its own gates (Lead)")
    q.add_argument("work_id")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_close(token=_lead_token(a), expect_rev=a.expect_rev,
                                                          work_id=a.work_id, reason=a.reason))
    q = wsub.add_parser("cancel", help="cancel a Story/Epic and its open descendants (Lead)")
    q.add_argument("work_id")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_cancel(token=_lead_token(a), expect_rev=a.expect_rev,
                                                           work_id=a.work_id, reason=a.reason))
    q = wsub.add_parser("move", help="move a unit under another parent (or none); recorded decision (Lead)")
    q.add_argument("work_id")
    q.add_argument("--parent", required=True, help="new parent id, or `none`")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_move(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id,
        parent=None if a.parent.lower() == "none" else a.parent, reason=a.reason))
    q = wsub.add_parser("promote", help="promote a Ticket to a Story (or to an Epic), preserving identity (Lead)")
    q.add_argument("work_id")
    q.add_argument("--to", required=True, choices=["story", "epic"])
    q.add_argument("--title", required=True)
    q.add_argument("--reason", required=True)
    q.add_argument("--class", dest="risk_class", type=int, choices=range(0, 5))
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_promote(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, to=a.to, title=a.title,
        reason=a.reason, risk_class=a.risk_class))
    q = wsub.add_parser("depend", help="add/remove dependency edges; recorded decision (Lead)")
    q.add_argument("work_id")
    q.add_argument("--add", action="append", default=[], metavar="ID[:mutating|evidence]")
    q.add_argument("--remove", action="append", default=[], metavar="ID")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_depend(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, add=a.add, remove=a.remove,
        reason=a.reason))
    q = wsub.add_parser("acknowledge-input", help="accept a stale source-bound input for the current commit (Lead)")
    q.add_argument("work_id")
    q.add_argument("--input", dest="evidence", required=True, help="the consumed record's evidence id")
    q.add_argument("--from", dest="source", required=True, help="the Ticket that produced it")
    q.add_argument("--reason", required=True, help="what was rechecked against the current source")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).work_acknowledge_input(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, evidence_id=a.evidence,
        source=a.source, reason=a.reason))
    q = wsub.add_parser("tree", help="the Epic -> Story -> Ticket tree with derived parent state")
    q.add_argument("work_id", nargs="?")
    q.set_defaults(handler=lambda a: _engine(a).work_tree(a.work_id))

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
    q = psub.add_parser("adopt", help="propose a plan revision from an accepted Planner plan_proposal (Lead)")
    q.add_argument("work_id", help="the unit whose plan it becomes")
    q.add_argument("--evidence", required=True)
    q.add_argument("--from", dest="source", required=True, help="the DONE planning Ticket that produced it")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).plan_adopt(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, evidence_id=a.evidence,
        source=a.source, reason=a.reason))
    q = psub.add_parser("reconfirm", help="rebind an accepted plan after an ancestor's plan changed (Lead)")
    q.add_argument("work_id")
    q.add_argument("--reason", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).plan_reconfirm(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, reason=a.reason))

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
    _add_execution(q)
    _add_launch(q)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _dispatch(a, "invoke_create", work_id=a.work_id, role=a.role, card=a.card,
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
    q.set_defaults(handler=lambda a: _as_invocation(
        a, "check.run", {"check_id": a.check_id},
        lambda token: _engine(a).check_run(invocation_token=token, check_id=a.check_id)))

    q = sub.add_parser("submit", help="submit role evidence (implementation report, review, verification)")
    q.add_argument("--kind", required=True, choices=["implementation_report", "review", "verification",
                                                     "discovery_record", "research_record", "plan_proposal"])
    q.add_argument("--file", required=True, help="Markdown with YAML frontmatter (file or - for stdin)")
    q.add_argument("--invocation-token", help="invocation credential (or env AEW_INVOCATION_TOKEN)")
    q.set_defaults(handler=_submit)

    q = sub.add_parser("whoami", help="the invocation this credential or harness run acts as (bounded role)")
    q.add_argument("--invocation-token", help="invocation credential (or env AEW_INVOCATION_TOKEN)")
    q.set_defaults(handler=lambda a: _as_invocation(
        a, "whoami", {}, lambda token: _engine(a).invocation_whoami(invocation_token=token)))

    p = sub.add_parser("harness", help="harness runs of invocations (ADR-0009)")
    hsub = p.add_subparsers(dest="harness_cmd", required=True)
    q = hsub.add_parser("launch", help="start a harness run for an active invocation; rotates its credential (Lead)")
    q.add_argument("invocation")
    q.add_argument("--replace", action="store_true",
                   help="relaunch even if the latest run may still be running (it loses its authority now)")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).harness_launch(
        token=_lead_token(a), expect_rev=a.expect_rev, invocation=a.invocation, replace=a.replace))
    q = hsub.add_parser("status", help="runs, their local status and whether they still hold authority")
    q.add_argument("invocation", nargs="?")
    q.set_defaults(handler=lambda a: _engine(a).harness_status(a.invocation))
    q = hsub.add_parser("wait", help="wait until a run stops running")
    q.add_argument("run")
    q.add_argument("--timeout", type=float, default=600.0)
    q.set_defaults(handler=lambda a: _engine(a).harness_wait(a.run, timeout=a.timeout))
    q = hsub.add_parser("stop", help="stop a run's harness; no AEW state changes (Lead)")
    q.add_argument("run")
    q.add_argument("--reason", required=True)
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    q.set_defaults(handler=lambda a: _engine(a).harness_stop(token=_lead_token(a), run=a.run, reason=a.reason))
    q = hsub.add_parser("send", help="deliver a message to a running agent after its current step (Lead)")
    q.add_argument("run")
    src = q.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--file", help="message file, or - for stdin")
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    q.set_defaults(handler=lambda a: _engine(a).harness_send(
        token=_lead_token(a), run=a.run, text=a.text if a.text is not None else _read_text_arg(a.file)))
    q = hsub.add_parser("interrupt", help="stop a run's current turn, keeping its session (Lead)")
    q.add_argument("run")
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    q.set_defaults(handler=lambda a: _engine(a).harness_interrupt(token=_lead_token(a), run=a.run))
    q = hsub.add_parser("config", help="print the exact projection a harness receives (read-only)")
    q.add_argument("harness", choices=["opencode"])
    q.add_argument("invocation", nargs="?")
    q.add_argument("--lead", action="store_true", help="the Lead's TUI projection (`aew opencode`)")
    q.set_defaults(handler=lambda a: _engine(a).harness_config(a.harness, invocation=a.invocation, lead=a.lead))

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

    p = sub.add_parser("evidence", help="Lead: ingest a non-mutating Ticket's execute record")
    esub = p.add_subparsers(dest="evidence_cmd", required=True)
    q = esub.add_parser("ingest")
    q.add_argument("work_id")
    q.add_argument("--evidence", required=True)
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).evidence_ingest(
        token=_lead_token(a), expect_rev=a.expect_rev, work_id=a.work_id, evidence_id=a.evidence))

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
