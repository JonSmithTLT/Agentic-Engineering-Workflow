"""`aew map`: the structural codebase map (register F22.1; design v0.5 §2, §3; ADR-0015).

A map is derived navigation context, never authority: no command here takes ``--expect-rev`` or changes control
state. ``map generate`` writes under ``.aew/local/maps/`` and is Lead-authenticated (Lead-reachable in a Lead
session); ``map show``, ``map search`` and ``map diff`` are reads.

Inside a worker's run, ``map show`` and ``map search`` go through the run's bridge (register F15.8), which answers at
the invocation's own base: a flag that would name another basis (``--commit``, ``--root``, ``--work``) is refused there,
never quietly ignored.
"""

from __future__ import annotations

import argparse
from typing import Any

from aew.cli.commands import _add_json, _engine, _lead_token, add_token
from aew.errors import UsageError


def _text(result: dict[str, Any], as_json: bool) -> Any:
    """People get YAML; every repository-derived string in a record is already escaped (no control characters)."""
    if as_json:
        return result
    from aew.util import dump_yaml

    return dump_yaml(result)


def _operand(kind: str):
    return lambda value: (kind, value)


def _generate(a: argparse.Namespace) -> Any:
    from aew.maps import service

    return _text(service.generate(_engine(a), token=_lead_token(a), commit=a.commit, select=a.select,
                                  expect=a.expect_map_rev, replace_nondeterministic=a.replace_nondeterministic),
                 a.json)


WORKER_BASIS = ("a worker's map read answers at its invocation's base, which no flag can change: drop {flags} "
                "(register F15.8)")


def _in_worker_run(a: argparse.Namespace, *flags: str) -> bool:
    """Whether this command runs inside a worker's run, where map reads go through the run's bridge; refuses the
    flags that would name another basis there."""
    from aew.harness import bridge

    if not bridge.available():
        return False
    given = [f"--{f.replace('_', '-')}" for f in flags if getattr(a, f, None)]
    if given:
        raise UsageError(WORKER_BASIS.format(flags=", ".join(given)), refused=given, reason="worker_basis")
    return True


def _context(a: argparse.Namespace, engine: Any, *, scope_paths: tuple[str, ...] = ()) -> Any:
    """The Lead's or the operator's read context: ``--commit``, else the authoritative head, from this project."""
    from aew import lead_credential
    from aew.maps import query, service

    commit = a.commit or service._default_commit(engine)
    kind = "lead" if lead_credential.session_kind() == "lead" else "operator"
    return query.Context(repo_root=engine.repo_root, aew_root=engine.aew_root, commit=commit,
                         chosen_by=query.EXPLICIT if a.commit else query.AUTHORITATIVE_HEAD,
                         recipient={"kind": kind}, workspace=engine.repo_root, scope_paths=scope_paths)


def _show(a: argparse.Namespace) -> Any:
    from aew.maps import query, service

    if _in_worker_run(a, "commit", "root", "work"):
        from aew.harness import bridge

        return _text(bridge.call("map.show", {"section": a.section or "", "scope": a.scope or ""}), a.json)
    if a.scope == "ticket":
        if a.root or not a.work:
            raise UsageError("--scope ticket reads a Ticket's scope: give --work T-n (and not --root; --commit sets "
                             "the basis)")
        engine = _engine(a)
        ctx = _context(a, engine, scope_paths=tuple(engine.work_scope_paths(a.work)))
        return _text(query.serve(ctx, "map.show", {"section": a.section or "", "scope": "ticket"}), a.json)
    if a.work:
        raise UsageError("--work goes with --scope ticket")
    return _text(service.show(_engine(a), commit=a.commit, root=a.root, section=a.section), a.json)


def _search(a: argparse.Namespace) -> Any:
    from aew.maps import query

    args = {"text": a.text, "kind": a.kind, "limit": str(a.limit) if a.limit is not None else ""}
    if _in_worker_run(a, "commit"):
        from aew.harness import bridge

        return _text(bridge.call("map.search", args), a.json)
    return _text(query.serve(_context(a, _engine(a)), "map.search", args), a.json)


def _diff(a: argparse.Namespace) -> Any:
    from aew.maps import service

    return _text(service.diff(_engine(a), a.operands or []), a.json)


def _select_architecture(a: argparse.Namespace) -> Any:
    from aew.maps import service

    return _text(service.select_architecture(_engine(a), token=_lead_token(a), evidence_id=a.evidence_id,
                                             expect=a.expect_map_rev), a.json)


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("map", help="the structural codebase map: derived navigation context, never authority")
    msub = p.add_subparsers(dest="map_cmd", required=True)

    q = msub.add_parser("generate", help="generate the structural map of a commit from its Git objects and store it "
                                         "under .aew/local/maps/ (Lead); --select makes it the current map")
    q.add_argument("--commit", metavar="H", help="the commit (default: the authoritative branch's head)")
    q.add_argument("--select", action="store_true", help="select the generated map in the map registry")
    q.add_argument("--expect-map-rev", metavar="EPOCH:REV",
                   help="the map registry's revision this selection is based on, as `aew map show` prints it "
                        "(none:0 before the first selection); never the control revision")
    q.add_argument("--replace-nondeterministic", action="store_true",
                   help="select even though the selected map's commit regenerated to different bytes")
    add_token(q)
    _add_json(q)
    q.set_defaults(handler=_generate)

    q = msub.add_parser("select-architecture", help="select an existing discovery record as the architecture "
                                                    "navigation reference (Lead); asserts nothing about its content")
    q.add_argument("evidence_id", metavar="EVIDENCE-ID")
    q.add_argument("--expect-map-rev", metavar="EPOCH:REV", required=True,
                   help="the map registry's revision this selection is based on, as `aew map show` prints it")
    add_token(q)
    _add_json(q)
    q.set_defaults(handler=_select_architecture)

    q = msub.add_parser("show", help="the selected (or named) structural map with its freshness against a commit "
                                     "(read-only)")
    which = q.add_mutually_exclusive_group()
    which.add_argument("--commit", metavar="H",
                       help="the commit the selected map's freshness is computed against (default: the "
                            "authoritative branch's head)")
    which.add_argument("--root", metavar="SHA", help="a stored map by its artifact sha256, instead of the selected one")
    q.add_argument("--section", metavar="NAME", help="only this section")
    q.add_argument("--scope", choices=("ticket", "none"),
                   help="ticket: the Ticket's own directories, read past the map's global directory cap (with --work "
                        "outside a worker's run)")
    q.add_argument("--work", metavar="T-n", help="the Ticket whose scope --scope ticket reads (the Lead, the operator)")
    _add_json(q)
    q.set_defaults(handler=_show)

    q = msub.add_parser("search", help="find a path at a commit, exact first, then a lexical search of the workspace "
                                       "when no path matches; every hit is a candidate (read-only)")
    q.add_argument("text", metavar="TEXT", help="a path, a path's last components, or text")
    q.add_argument("--kind", choices=("any", "path"), default="any",
                   help="path: tracked paths only, never the lexical fallback (default: any)")
    q.add_argument("--limit", type=int, metavar="N", help="at most N hits (default 20, at most 100)")
    q.add_argument("--commit", metavar="H", help="the commit paths are resolved at (default: the authoritative "
                                                  "branch's head; a worker's is its invocation's base)")
    _add_json(q)
    q.set_defaults(handler=_search)

    q = msub.add_parser("diff", help="section-by-section differences between two maps, each a stored root or a commit "
                                     "generated in memory (read-only)")
    q.add_argument("--root", dest="operands", action="append", type=_operand("root"), metavar="SHA",
                   help="a stored map by its artifact sha256")
    q.add_argument("--commit", dest="operands", action="append", type=_operand("commit"), metavar="H",
                   help="a commit, generated in memory and not stored")
    _add_json(q)
    q.set_defaults(handler=_diff)
