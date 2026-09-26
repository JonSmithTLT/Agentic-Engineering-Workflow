"""Sub-command registration. Handlers only parse/format; all semantics live in the engine."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from aew import doctor
from aew.errors import UsageError


# ---------------------------------------------------------------------- shared helpers


def _cwd(args: argparse.Namespace) -> Path:
    return Path(args.cwd) if args.cwd else Path.cwd()


def _engine(args: argparse.Namespace):
    from aew.engine.api import Engine

    return Engine.discover(_cwd(args))


def _lead_token(args: argparse.Namespace) -> str:
    token = getattr(args, "token", None) or os.environ.get("AEW_LEAD_TOKEN")
    if not token:
        raise UsageError("Lead credential required: pass --token or set AEW_LEAD_TOKEN")
    return token


def _read_text_arg(value: str | None) -> str:
    if not value:
        return ""
    if value == "-":
        import sys

        return sys.stdin.read()
    return Path(value).read_text(encoding="utf-8")


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="machine-readable output")


def _add_lead(p: argparse.ArgumentParser) -> None:
    p.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    p.add_argument("--expect-rev", type=int, required=True, help="control revision this decision is based on")


# ---------------------------------------------------------------------- registration


def register(sub: argparse._SubParsersAction) -> None:
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

    _register_lead(sub)
    _register_authority(sub)

    p = sub.add_parser("manifest", help="project manifest maintenance")
    msub = p.add_subparsers(dest="manifest_cmd", required=True)
    q = msub.add_parser("adopt", help="accept a reviewed manual edit of project.yaml (Lead)")
    _add_lead(q)
    q.add_argument("--reason", required=True)
    q.set_defaults(handler=lambda a: _engine(a).manifest_adopt(token=_lead_token(a), expect_rev=a.expect_rev,
                                                              reason=a.reason))

    from aew.cli import work_commands

    work_commands.register(sub)


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


def _register_authority(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("authority", help="classify candidate authority sources discovered by init")
    asub = p.add_subparsers(dest="authority_cmd", required=True)
    q = asub.add_parser("list")
    q.set_defaults(handler=lambda a: _engine(a).authority_list())
    q = asub.add_parser("accept")
    q.add_argument("candidate")
    q.add_argument("--class", dest="klass", required=True,
                   choices=["contracts", "decisions", "schemas", "source", "orientation"])
    q.add_argument("--decided-by", choices=["lead", "operator"], default="lead")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).authority_accept(
        token=_lead_token(a), expect_rev=a.expect_rev, candidate_id=a.candidate, klass=a.klass,
        decided_by=a.decided_by, reason=a.reason))
    q = asub.add_parser("reject")
    q.add_argument("candidate")
    q.add_argument("--reason")
    _add_lead(q)
    q.set_defaults(handler=lambda a: _engine(a).authority_reject(
        token=_lead_token(a), expect_rev=a.expect_rev, candidate_id=a.candidate, reason=a.reason))


# ---------------------------------------------------------------------- handlers


def _doctor(args: argparse.Namespace) -> Any:
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


def _status(args: argparse.Namespace) -> Any:
    engine = _engine(args)
    report = engine.status(args.work_id)
    return report if args.json else engine.render_status(report)
