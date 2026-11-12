"""Sub-command registration. Handlers only parse/format; all semantics live in the engine."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from aew.cli import fields
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
    """The Lead credential: the one a Lead session's broker set on ``args``, else the operator's
    (``lead_credential.required``: the variable, the hidden prompt, or a refusal that says how)."""
    from aew import lead_credential

    return getattr(args, "token", None) or lead_credential.required()


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


def add_token(p: argparse.ArgumentParser) -> None:
    """A Lead-authenticated command: it takes the Lead credential from ``AEW_LEAD_TOKEN`` or the hidden prompt
    (``aew.lead_credential``). ``--token`` stays registered, out of the help, so that ``args.token`` marks the command
    (``lead_broker.routes``) and carries the broker's credential; given a value on the command line it is refused
    (``main``)."""
    p.add_argument("--token", help=argparse.SUPPRESS)


def _add_lead(p: argparse.ArgumentParser) -> None:
    add_token(p)
    p.add_argument("--expect-rev", type=int, required=True, help="control revision this decision is based on")


# ---------------------------------------------------------------------- registration


def register(sub: argparse._SubParsersAction, *, recall_search: bool = False,
             coordination_reads: bool = False) -> None:
    p = sub.add_parser("doctor", help="validate the environment and project state")
    _add_json(p)
    p.add_argument("--refresh", action="store_true",
                   help="read the harness's model list again instead of the cached one")
    p.add_argument("--run-checks", action="store_true",
                   help="run the project's checks once on a disposable copy of the project, contained as a worker's "
                        "check, and name each path they change")
    p.set_defaults(handler=_doctor)

    p = sub.add_parser("init", help="initialize AEW in the current git repository")
    p.add_argument("--project-id")
    p.add_argument("--name")
    p.add_argument("--branch", help="authoritative branch (default: current branch)")
    p.add_argument("--workspaces-root", help="where Ticket workspaces are created (relative to repo root)")
    # The first configuration: written before the pin, on `init` only (register E119). Changing any of them later takes
    # the Lead credential and an adopt.
    p.add_argument("--check-command", metavar="COMMAND",
                   help="the project's unit check, split as POSIX with no shell; {python} is the running Python")
    p.add_argument("--check-timeout", metavar="SECONDS", help="with --check-command: the check's timeout")
    p.add_argument("--model", help="the workers' model, as the harness lists it (provider/model). It doesn't set the "
                                   "Lead's own model")
    p.add_argument("--provider", help="with --model: the workers' provider, when the model is a bare id")
    # The tools AEW brings: downloaded only as the operator chooses (the operator, 2026-11-05; aew.capability.consent)
    p.add_argument("--fetch-tool", action="append", metavar="TOOL",
                   help="download this tool AEW brings (`aew capability list` names them), as your choice, with no "
                        "screen; repeat for more. "
                        "With none named, a screen asks at a terminal, and elsewhere nothing downloads")
    p.set_defaults(handler=_init)

    p = sub.add_parser("status", help="work graph, Lead authority and knowledge health")
    p.add_argument("work_id", nargs="?")
    _add_json(p)
    p.set_defaults(handler=_status)

    p = sub.add_parser("resume", help="reconstruct the Lead's context from durable state (read-only)")
    _add_json(p)
    p.set_defaults(handler=_resume)

    p = sub.add_parser("guide", help="how work flows in AEW for this project: risk classes, the gates each "
                                     "requires, the Ticket lifecycle and the tool or command for each step (read-only)")
    _add_json(p)
    p.set_defaults(handler=_guide)

    p = sub.add_parser("checkpoint", help="record a checkpoint and the Lead's next-action note")
    p.add_argument("--note-file", action=fields.FileInput, help="checkpoint notes (file or - for stdin)")
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
    _register_stage(sub)
    _register_authority(sub)

    p = sub.add_parser("manifest", help="project manifest maintenance")
    msub = p.add_subparsers(dest="manifest_cmd", required=True)
    q = msub.add_parser("adopt", help="accept a reviewed manual edit of project.yaml or of the policy files it names "
                                         "(the operator, confirmed at their own terminal)")
    _add_lead(q)
    q.add_argument("--reason", required=True)
    q.set_defaults(handler=_manifest_adopt)

    from aew.cli import (
        capability_commands,
        dashboard_commands,
        g3_commands,
        history_commands,
        map_commands,
        notify_commands,
        operator_commands,
        settings_commands,
        usage_commands,
        work_commands,
    )

    work_commands.register(sub)
    history_commands.register(sub, recall_search=recall_search)
    dashboard_commands.register(sub)
    map_commands.register(sub)
    operator_commands.register(sub)
    settings_commands.register(sub)
    capability_commands.register(sub)  # the capability register (STG-15, CAP-1)
    usage_commands.register(sub)  # the cost and usage ledger's reads (F25 R9)
    g3_commands.register(sub)  # the G3 client (STG-03, G3-D)
    notify_commands.register(sub)  # the notifiers AEW ships (register E104)
    if coordination_reads:  # F9-A (plan D-31): only while messaging is on or a thread exists, never in a run
        from aew.cli import message_commands

        message_commands.register(sub)


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
    q.add_argument("--note-file", action=fields.FileInput, help="handoff notes (file or - for stdin)")
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
    add_token(q)
    q.set_defaults(handler=_lead_tool)

    from aew.cli import operator_commands

    operator_commands.register_lead_mode(lsub)

    q = lsub.add_parser("mcp", help="the Lead's MCP server, aew-lead (F15.1): spawned by the Lead's harness in a Lead "
                                    "session; it holds no credential and forwards every call to the session's broker")
    q.add_argument("--profile", choices=["normal", "recovery"], default="normal",
                   help="the surface profile to advertise; the generic cli escape is offered only on recovery")
    q.set_defaults(handler=_lead_mcp)

    p = sub.add_parser("opencode", help="the Lead's OpenCode TUI as a Lead session: its model never sees the Lead "
                                        "credential or, by default, any provider key (ADR-0009); on Linux it runs "
                                        "contained, at a terminal (STG-05 CS-4)")
    seat_mode = p.add_mutually_exclusive_group()
    seat_mode.add_argument("--acquire", action="store_true",
                           help="take a vacant seat or resume an eligible seat in-process")
    seat_mode.add_argument("--prompt-token", action="store_true",
                           help="use the hidden prompt for an existing Lead credential")
    p.add_argument("--session-label")
    p.add_argument("--keep-seat", action="store_true", help="keep a seat this session took or resumed at exit")
    p.add_argument("--provider-env", action="append", default=[], metavar="NAME",
                   help="use this provider variable for the Lead's model: on Linux it feeds that provider's relay on "
                        "the host and the Lead's shell sees a placeholder; elsewhere it is passed to the Lead's "
                        "OpenCode, whose shell can then read it. By default the Lead's model uses the logins OpenCode "
                        "stores (`opencode auth login`)")
    p.add_argument("--print-config", action="store_true",
                   help="print the Lead projection and the environment names; start nothing")
    p.add_argument("opencode_args", nargs=argparse.REMAINDER, help="-- further OpenCode TUI arguments")
    p.set_defaults(handler=_opencode)


def _register_stage(sub: argparse._SubParsersAction) -> None:
    """``aew stage continue|abandon``: the typed ``resolve`` tool's CLI form (M4-E plan v3 E3; §3.4 rule 8). The same
    runner and result: one semantic implementation (typed surface §5)."""
    p = sub.add_parser("stage", help="resolve an unfinished stage that `aew resume` lists: continue or abandon it")
    ssub = p.add_subparsers(dest="stage_cmd", required=True)
    for choice, text in (("continue", "recheck it, rebind it to this Lead generation and run its remaining steps"),
                         ("abandon", "end it; its committed steps stand")):
        q = ssub.add_parser(choice, help=text)
        q.add_argument("intent", help="the stage intent id, e.g. SI-0003")
        q.add_argument("--rationale", required=True, help="why (recorded on the intent)")
        _add_lead(q)
        q.set_defaults(handler=_stage_resolve, choice=choice)


def _guide(args: argparse.Namespace) -> Any:
    from aew.surface import lead_text

    text = lead_text.guide_for(_engine(args))
    return {"guide": text} if args.json else text


def _stage_resolve(args: argparse.Namespace) -> Any:
    from aew.surface import run
    from aew.surface.context import SurfaceContext
    from aew.surface.errors import AdapterInputError

    arguments = {"expect_rev": args.expect_rev, "subject": args.intent, "choice": args.choice,
                 "rationale": args.rationale}
    try:
        return run.run_tool(_engine(args), SurfaceContext.outside_session(), "resolve", arguments,
                            token=_lead_token(args))
    except AdapterInputError as exc:
        err = UsageError(exc.message, **exc.details)
        err.code = exc.code  # the adapter's own code: an input error, never an engine refusal
        raise err from None


def _register_authority(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("authority", help="classify candidate authority sources discovered by init")
    asub = p.add_subparsers(dest="authority_cmd", required=True)
    q = asub.add_parser("list")
    q.set_defaults(handler=lambda a: _engine(a).authority_list())
    q = asub.add_parser("accept")
    q.add_argument("candidate")
    q.add_argument("--class", dest="klass", required=True,
                   choices=["contracts", "decisions", "schemas", "source", "orientation"])
    q.add_argument("--decided-by", choices=["lead", "operator"], default="operator",
                   help="operator: recorded as the operator's decision, confirmed at their own terminal (a code "
                        "typed back)")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=_authority_decide)
    q = asub.add_parser("reject")
    q.add_argument("candidate")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=_authority_decide, decided_by="operator")


def _manifest_adopt(a: argparse.Namespace) -> Any:
    engine = _engine(a)
    token = _lead_token(a)
    binding = engine.manifest_approval()
    files = "\n".join(f"  {rel}@{sha if sha is not None else 'missing'}" for rel, sha in sorted(binding.items()))
    authorization = operator_attribution("operator", f"ADOPT as YOUR decision: project settings\n{files}")
    return engine.manifest_adopt(token=token, expect_rev=a.expect_rev, reason=a.reason,
                                 authorization=authorization, binding=binding)


def _authority_decide(a: argparse.Namespace) -> Any:
    engine = _engine(a)
    token = _lead_token(a)
    subject = engine.authority_candidate(a.candidate)
    action = a.authority_cmd
    digest = subject["digest"]
    if action == "accept" and subject["kind"] == "file, missing":
        from aew.errors import NotFound
        from aew.harness.contract import EXPECT_REV

        raise NotFound(f"authority candidate file {subject['path']} is missing. "
                       f"The operator can reject it with `aew authority reject {a.candidate} {EXPECT_REV}`.",
                       path=subject["path"])
    summary = f"{action} {subject['path']} ({subject['kind']}, SHA-256 {digest})"
    if action == "accept":
        summary += f" as {a.klass} authority"
    authorization = operator_attribution(a.decided_by, f"RECORD as YOUR decision: {summary}")
    binding = digest
    if a.decided_by == "lead":
        if sys.stderr.isatty():
            print(summary, file=sys.stderr, flush=True)
        else:
            # Redirected commands reserve stderr for the JSON refusal.
            binding = None
    args: dict[str, Any] = {"token": token, "expect_rev": a.expect_rev, "candidate_id": a.candidate,
                            "decided_by": a.decided_by, "reason": a.reason, "binding": binding,
                            "authorization": authorization}
    if action == "accept":
        return engine.authority_accept(klass=a.klass, **args)
    return engine.authority_reject(**args)


# ---------------------------------------------------------------------- handlers


def _doctor(args: argparse.Namespace) -> Any:
    from aew import doctor

    report = doctor.run(cwd=args.cwd, refresh=args.refresh, run_checks=args.run_checks)
    # Both output modes exit 1 when any line is FAIL (WARN and UNAVAILABLE stay 0): the JSON report carries
    # `ok: false`, which main turns into 1, and the rendered text says the same through the command's exit status
    # (review of PR #214, F1: a FAIL the exit status reported as success depended on the output format).
    args.exit_status = lambda _result: 0 if report["ok"] else 1
    return report if args.json else doctor.render(report)


def _init(args: argparse.Namespace) -> Any:
    from aew.capability import consent
    from aew.engine import first_configuration
    from aew.engine.api import Engine
    from aew.harness import contract as K
    from aew.harness.containment import netns
    from aew.policy import execution

    consent.check_names(args.fetch_tool)  # an unknown tool refuses before anything is written
    configuration = first_configuration.from_flags(check_command=args.check_command, check_timeout=args.check_timeout,
                                                   model=args.model, provider=args.provider)
    engine = Engine.initialize(
        _cwd(args), project_id=args.project_id, name=args.name, branch=args.branch,
        workspaces_root=args.workspaces_root, first_configuration=configuration,
    )
    from aew.maps import service as maps

    state = engine.store.current()
    out = {
        "ok": True,
        "project_id": engine.project_id,
        "aew_root": str(engine.aew_root),
        "revision": state["revision"],
        "authority_candidates": engine.manifest["authority"]["candidates"],
        **({"first_configuration": configuration.report()} if configuration is not None else {}),
        "next": configuration.next_step() if configuration is not None
        else (f"this project still has no check command or model. To set both, "
              f"{first_configuration.post_pin_route(first_configuration.CHECKS_REL, execution.REL_PATH, fresh=True)}. "
              f"{K.HELD_SEAT}. Then start the Lead with `aew opencode --acquire`"),
        "provider_key": netns.FIRST_USE_LINE,
        "map": maps.first_map(engine),  # register E184: the first structural map, generated and selected
    }
    if "pricing" not in engine.manifest["policy"]:
        out["price_table"] = ("this package holds no bundled price table, so every cost reads unpriced until the "
                              "project adopts one as policy.pricing")
    return {**out, **consent.init_keys(out["next"], consent.at_init(args.fetch_tool))}


def _lead_tool(args: argparse.Namespace) -> Any:
    """``aew lead tool``: the typed surface's CLI transport (parity, recovery, conformance; F15.1 plan §6)."""
    import json

    from aew.surface import SURFACE, client, contract
    from aew.surface.context import switches_for
    from aew.surface.errors import AdapterInputError

    if args.list:
        if client.in_session():
            switches = contract.switches_from_env()
        else:
            from aew.errors import ProjectNotFound

            try:
                switches = switches_for(_engine(args))
            except ProjectNotFound:
                switches = frozenset()
        return {"ok": True, "surface": SURFACE, "tools": [
            {"name": t.name, "kind": t.kind, "base_operation_class": t.base_class, "status": t.status,
             "progression": t.progression, "profiles": list(t.profiles), "description": t.description}
            for t in contract.catalog(switches).values()]}
    if not args.name:
        raise UsageError("name a tool (see `aew lead tool --list`)")
    try:
        try:
            arguments = json.loads(read_text_input("-") if args.arguments == "-" else args.arguments)
        except ValueError:
            raise AdapterInputError("INVALID_ARGUMENTS", f"{args.name}: --arguments is not a JSON object") from None
        if client.in_session():
            return client.forward(args.name, arguments, ingress="cli", profile=args.profile)
        return _lead_tool_here(args, arguments)
    except AdapterInputError as exc:
        err = UsageError(exc.message, **exc.details)
        err.code = exc.code  # the adapter's own code: an input error, never an engine refusal
        raise err from None


def _lead_tool_here(args: argparse.Namespace, arguments: Any) -> Any:
    """Outside a Lead session: the runner in this process, with the operator's own credential (ADR-0005)."""
    from aew import lead_credential
    from aew.harness import lead_broker
    from aew.surface import contract, run
    from aew.surface.context import SurfaceContext, switches_for

    engine = _engine(args)
    switches = switches_for(engine)
    tool = contract.tool(args.name, switches)
    # a query or a wait reads, and needs no credential; anything else asks for it (an unknown name: the runner refuses)
    reads = tool is None or tool.kind in ("query", "wait")
    token = (lead_credential.optional() if reads else lead_credential.required()) or ""

    def cli(argv: list[str], stdin: str) -> dict[str, Any]:
        return lead_broker.run_cli(engine, token, argv, str(engine.repo_root), stdin, channel="cli")

    return run.run_tool(engine, SurfaceContext.outside_session(profile=args.profile, switches=switches),
                        args.name, arguments,
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
    engine = _engine(args)
    # Refused here under `required`, before any credential is read or any seat moves (G3 addendum 7, ruling 1);
    # run_session asks it again, as the backstop.
    harness = lead_broker.WeakerLead(engine, command, kind="lead_session", who="aew lead session")
    if command:
        harness.precheck()
    return lead_broker.run_session(engine, command, acquire=args.acquire, session_label=args.session_label,
                                   keep_seat=args.keep_seat, contained=harness)


def _opencode(args: argparse.Namespace) -> Any:
    from aew.harness.opencode import lead

    return lead.run(_engine(args), acquire=args.acquire, session_label=args.session_label, keep_seat=args.keep_seat,
                    provider_env=list(args.provider_env), extra_args=list(args.opencode_args),
                    print_config=args.print_config, prompt_token=args.prompt_token)


def _resume(args: argparse.Namespace) -> Any:
    from aew.harness import lead_broker
    from aew.surface import stage

    engine = _engine(args)
    report = engine.resume(session=lead_broker.session_authority())
    report["stage_intents"] = stage.unfinished(engine)  # as the typed `resume` lists them (M4-E E3c)
    return report if args.json else engine.render_resume(report)


def _status(args: argparse.Namespace) -> Any:
    engine = _engine(args)
    report = engine.status(args.work_id)
    return report if args.json else engine.render_status(report)
