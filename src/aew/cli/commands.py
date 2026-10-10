"""Sub-command registration. Handlers only parse/format; all semantics live in the engine."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from aew.errors import UsageError
from aew.util import read_text_input

# ---------------------------------------------------------------------- shared helpers


def _cwd(args: argparse.Namespace) -> Path:
    return Path(args.cwd) if args.cwd else Path.cwd()


def _engine(args: argparse.Namespace):
    if not Path(_cwd(args)).is_dir():
        raise UsageError(f"no such directory: {_cwd(args)} (a retired workspace or observation?)")
    from aew.engine.api import Engine

    return Engine.discover(_cwd(args))


def _lead_token(args: argparse.Namespace) -> str:
    token = getattr(args, "token", None) or os.environ.get("AEW_LEAD_TOKEN")
    if not token:
        raise UsageError("Lead credential required: pass --token or set AEW_LEAD_TOKEN")
    return token


def operator_attribution(by: str, text: str) -> dict[str, str] | None:
    """When a command records its decision as the operator's, the operator's confirmation, typed back at their own
    terminal (``operator.authorize``); refused without one. Asked before the engine runs anything."""
    if by != "operator":
        return None
    from aew import operator

    return operator.authorize(text)


def _read_text_arg(value: str | None) -> str:
    return read_text_input(value)


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="machine-readable output")


def _add_lead(p: argparse.ArgumentParser) -> None:
    p.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    p.add_argument("--expect-rev", type=int, required=True, help="control revision this decision is based on")


# ---------------------------------------------------------------------- registration


def register(sub: argparse._SubParsersAction, *, recall_search: bool = False) -> None:
    p = sub.add_parser("doctor", help="validate the environment and project state")
    _add_json(p)
    p.set_defaults(handler=_doctor)

    p = sub.add_parser("init", help="initialize AEW in the current git repository")
    p.add_argument("--project-id")
    p.add_argument("--name")
    p.add_argument("--branch", help="authoritative branch (default: current branch)")
    p.add_argument("--workspaces-root", help="where Ticket workspaces are created (relative to repo root)")
    p.set_defaults(handler=_init)

    p = sub.add_parser("status", help="work graph, Lead authority and knowledge health")
    p.add_argument("work_id", nargs="?")
    _add_json(p)
    p.set_defaults(handler=_status)

    p = sub.add_parser("resume", help="reconstruct the Lead's context from durable state (read-only)")
    _add_json(p)
    p.set_defaults(handler=_resume)

    p = sub.add_parser("guide", help="how work flows in AEW for this project: risk classes, the gates each "
                                     "requires, the Ticket lifecycle and the command for each step (read-only)")
    _add_json(p)
    p.set_defaults(handler=lambda a: {"guide": _engine(a).lead_guide()} if a.json else _engine(a).lead_guide())

    p = sub.add_parser("checkpoint", help="record a checkpoint and the Lead's next-action note")
    p.add_argument("--note-file", help="checkpoint notes (file or - for stdin)")
    p.add_argument("--next", dest="next_action", help="the Lead's next intended action")
    _add_lead(p)
    p.set_defaults(handler=lambda a: _engine(a).checkpoint(token=_lead_token(a), expect_rev=a.expect_rev,
                                                          note=_read_text_arg(a.note_file),
                                                          next_action=a.next_action))

    p = sub.add_parser("migrate", help="move a v1 project's control state to v2: finished work leaves the hot state "
                                       "(the operator, at their own terminal; ADR-0011)")
    _add_lead(p)
    p.set_defaults(handler=lambda a: _engine(a).migrate(token=_lead_token(a), expect_rev=a.expect_rev))

    _register_lead(sub)
    _register_authority(sub)

    p = sub.add_parser("manifest", help="project manifest maintenance")
    msub = p.add_subparsers(dest="manifest_cmd", required=True)
    q = msub.add_parser("adopt", help="accept a reviewed manual edit of project.yaml or of the policy files it names "
                                         "(the operator, confirmed at their own terminal)")
    _add_lead(q)
    q.add_argument("--reason", required=True)
    q.set_defaults(handler=lambda a: _engine(a).manifest_adopt(
        token=_lead_token(a), expect_rev=a.expect_rev, reason=a.reason, authorization=operator_attribution(
            "operator", "ADOPT as YOUR decision: the edits of project.yaml and the policy files")))

    from aew.cli import dashboard_commands, history_commands, map_commands, operator_commands, work_commands

    work_commands.register(sub)
    history_commands.register(sub, recall_search=recall_search)
    dashboard_commands.register(sub)
    map_commands.register(sub)
    operator_commands.register(sub)


def _register_lead(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("lead", help="Lead authority: acquire, handoff, takeover, release")
    lsub = p.add_subparsers(dest="lead_cmd", required=True)

    q = lsub.add_parser("show")
    q.set_defaults(handler=lambda a: _engine(a).lead_show())

    q = lsub.add_parser("acquire", help="take the vacant Lead seat")
    q.add_argument("--expect-rev", type=int, required=True)
    q.add_argument("--session-label")
    q.set_defaults(handler=lambda a: _engine(a).lead_acquire(expect_rev=a.expect_rev,
                                                            session_label=a.session_label))

    hp = lsub.add_parser("handoff", help="cooperative Lead handoff")
    hsub = hp.add_subparsers(dest="handoff_cmd", required=True)
    q = hsub.add_parser("offer")
    _add_lead(q)
    q.add_argument("--note-file", help="handoff notes (file or - for stdin)")
    q.add_argument("--carry", action="append", default=[], metavar="INV", help="in-flight invocation to carry")
    q.set_defaults(handler=lambda a: _engine(a).lead_handoff_offer(
        token=_lead_token(a), expect_rev=a.expect_rev, note=_read_text_arg(a.note_file),
        carry_invocations=a.carry))
    q = hsub.add_parser("accept")
    q.add_argument("--offer", required=True, help="the one-time offer secret from the outgoing Lead")
    q.add_argument("--expect-rev", type=int, required=True)
    q.add_argument("--session-label")
    q.set_defaults(handler=lambda a: _engine(a).lead_handoff_accept(
        offer=a.offer, expect_rev=a.expect_rev, session_label=a.session_label))
    q = hsub.add_parser("cancel")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).lead_handoff_cancel(token=_lead_token(a),
                                                                   expect_rev=a.expect_rev))

    q = lsub.add_parser(
        "takeover",
        help="operator-authorized takeover when the prior Lead is lost (interactive terminal required)",
    )
    q.add_argument("--expect-rev", type=int, required=True)
    q.add_argument("--reason", required=True, help="recorded for provenance; never authorizes")
    q.add_argument("--session-label")
    q.set_defaults(handler=lambda a: _engine(a).lead_takeover(
        expect_rev=a.expect_rev, reason=a.reason, session_label=a.session_label))

    q = lsub.add_parser("release", help="vacate the Lead seat cleanly")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).lead_release(token=_lead_token(a), expect_rev=a.expect_rev))

    q = lsub.add_parser("session", help="run a Lead harness session that never sees the Lead credential (ADR-0009)")
    q.add_argument("--acquire", action="store_true",
                   help="take the vacant seat in-process (the credential then exists only in this session)")
    q.add_argument("--session-label")
    q.add_argument("--keep-seat", action="store_true", help="with --acquire: do not release the seat at exit")
    q.add_argument("harness_command", nargs=argparse.REMAINDER, help="-- COMMAND [ARGS...]")
    q.set_defaults(handler=_lead_session)

    q = lsub.add_parser("tool", help="call one typed Lead surface tool (F15.1): the catalog, runner and result of the "
                                     "Lead's MCP server; inside a Lead session it goes through the session's broker")
    q.add_argument("name", nargs="?", help="the tool (see --list)")
    q.add_argument("--arguments", default="{}", metavar="JSON|-",
                   help="the tool's arguments as a JSON object, or - to read it from stdin (no shell sees it)")
    q.add_argument("--profile", choices=["normal", "recovery"], default="normal",
                   help="the surface profile; the generic cli escape is offered only on recovery")
    q.add_argument("--list", action="store_true", help="list the catalog: kinds, classes, status, profiles")
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN); never inside a Lead session")
    q.set_defaults(handler=_lead_tool)

    from aew.cli import operator_commands

    operator_commands.register_lead_mode(lsub)

    q = lsub.add_parser("mcp", help="the Lead's MCP server, aew-lead (F15.1): spawned by the Lead's harness in a Lead "
                                    "session; it holds no credential and forwards every call to the session's broker")
    q.add_argument("--profile", choices=["normal", "recovery"], default="normal",
                   help="the surface profile to advertise; the generic cli escape is offered only on recovery")
    q.set_defaults(handler=_lead_mcp)

    p = sub.add_parser("opencode", help="the Lead's OpenCode TUI as a Lead session: its model never sees the Lead "
                                        "credential or, by default, any provider key (ADR-0009)")
    p.add_argument("--acquire", action="store_true",
                   help="take the vacant seat in-process (the credential then exists only in this session)")
    p.add_argument("--session-label")
    p.add_argument("--keep-seat", action="store_true", help="with --acquire: do not release the seat at exit")
    p.add_argument("--provider-env", action="append", default=[], metavar="NAME",
                   help="pass this provider variable to the Lead's OpenCode (its shell can then read it); by default "
                        "the Lead's model uses the credentials OpenCode stores (`opencode auth login`)")
    p.add_argument("--print-config", action="store_true",
                   help="print the Lead projection and the environment names; start nothing")
    p.add_argument("opencode_args", nargs=argparse.REMAINDER, help="-- further OpenCode TUI arguments")
    p.set_defaults(handler=_opencode)


def _register_authority(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("authority", help="classify candidate authority sources discovered by init")
    asub = p.add_subparsers(dest="authority_cmd", required=True)
    q = asub.add_parser("list")
    q.set_defaults(handler=lambda a: _engine(a).authority_list())
    q = asub.add_parser("accept")
    q.add_argument("candidate")
    q.add_argument("--class", dest="klass", required=True,
                   choices=["contracts", "decisions", "schemas", "source", "orientation"])
    q.add_argument("--decided-by", choices=["lead", "operator"], default="lead",
                   help="operator: recorded as the operator's decision, confirmed at their own terminal (a code "
                        "typed back)")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).authority_accept(
        token=_lead_token(a), expect_rev=a.expect_rev, candidate_id=a.candidate, klass=a.klass,
        decided_by=a.decided_by, reason=a.reason, authorization=operator_attribution(
            a.decided_by, f"RECORD as YOUR decision: accept {a.candidate} as {a.klass} authority")))
    q = asub.add_parser("reject")
    q.add_argument("candidate")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).authority_reject(
        token=_lead_token(a), expect_rev=a.expect_rev, candidate_id=a.candidate, reason=a.reason))


# ---------------------------------------------------------------------- handlers


def _doctor(args: argparse.Namespace) -> Any:
    from aew import doctor

    report = doctor.run(cwd=args.cwd)
    return report if args.json else doctor.render(report)


def _init(args: argparse.Namespace) -> Any:
    from aew.engine.api import Engine

    engine = Engine.initialize(
        _cwd(args), project_id=args.project_id, name=args.name, branch=args.branch,
        workspaces_root=args.workspaces_root,
    )
    state = engine.store.read()
    return {
        "ok": True,
        "project_id": engine.project_id,
        "aew_root": str(engine.aew_root),
        "revision": state["revision"],
        "authority_candidates": engine.manifest["authority"]["candidates"],
        "next": "acquire Lead authority: aew lead acquire --expect-rev 0",
    }


def _lead_tool(args: argparse.Namespace) -> Any:
    """``aew lead tool``: the typed surface's CLI transport (parity, recovery, conformance; F15.1 plan §6)."""
    import json

    from aew.surface import SURFACE, client, contract
    from aew.surface.errors import AdapterInputError

    if args.list:
        return {"ok": True, "surface": SURFACE, "tools": [
            {"name": t.name, "kind": t.kind, "base_operation_class": t.base_class, "status": t.status,
             "progression": t.progression, "profiles": list(t.profiles), "description": t.description}
            for t in contract.TOOLS.values()]}
    if not args.name:
        raise UsageError("name a tool (see `aew lead tool --list`)")
    try:
        try:
            arguments = json.loads(read_text_input("-") if args.arguments == "-" else args.arguments)
        except ValueError:
            raise AdapterInputError("INVALID_ARGUMENTS", f"{args.name}: --arguments is not a JSON object") from None
        if client.in_session():
            if args.token:
                raise UsageError("do not pass --token in a Lead session: the session holds the Lead credential")
            return client.forward(args.name, arguments, ingress="cli", profile=args.profile)
        return _lead_tool_here(args, arguments)
    except AdapterInputError as exc:
        err = UsageError(exc.message, **exc.details)
        err.code = exc.code  # the adapter's own code: an input error, never an engine refusal
        raise err from None


def _lead_tool_here(args: argparse.Namespace, arguments: Any) -> Any:
    """Outside a Lead session: the runner in this process, with the operator's own credential (ADR-0005)."""
    from aew.harness import lead_broker
    from aew.surface import run
    from aew.surface.context import SurfaceContext

    engine = _engine(args)
    token = args.token or os.environ.get("AEW_LEAD_TOKEN") or ""

    def cli(argv: list[str], stdin: str) -> dict[str, Any]:
        return lead_broker.run_cli(engine, token, argv, str(engine.repo_root), stdin, channel="cli")

    return run.run_tool(engine, SurfaceContext.outside_session(profile=args.profile), args.name, arguments,
                        token=token or None, run_cli=cli)


def _lead_mcp(args: argparse.Namespace) -> Any:
    """``aew lead mcp``: serve the typed surface over stdio. It never builds an engine and never reads a credential:
    every call goes to the Lead session's broker, and without one it refuses to start."""
    from aew.surface import mcp

    mcp.serve(args.profile)
    return None


def _lead_session(args: argparse.Namespace) -> Any:
    from aew.harness import lead_broker

    command = list(args.harness_command)
    if command[:1] == ["--"]:
        command = command[1:]
    return lead_broker.run_session(_engine(args), command, acquire=args.acquire, session_label=args.session_label,
                                   keep_seat=args.keep_seat)


def _opencode(args: argparse.Namespace) -> Any:
    from aew.harness.opencode import lead

    return lead.run(_engine(args), acquire=args.acquire, session_label=args.session_label, keep_seat=args.keep_seat,
                    provider_env=list(args.provider_env), extra_args=list(args.opencode_args),
                    print_config=args.print_config)


def _resume(args: argparse.Namespace) -> Any:
    from aew.harness import lead_broker

    engine = _engine(args)
    report = engine.resume(session=lead_broker.session_authority())
    return report if args.json else engine.render_resume(report)


def _status(args: argparse.Namespace) -> Any:
    engine = _engine(args)
    report = engine.status(args.work_id)
    return report if args.json else engine.render_status(report)
