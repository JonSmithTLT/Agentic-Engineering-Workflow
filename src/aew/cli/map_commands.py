"""`aew map`: the structural codebase map (register F22.1; design v0.5 §2, §3; ADR-0015).

A map is derived navigation context, never authority: no command here takes ``--expect-rev`` or changes control
state. ``map generate`` writes under ``.aew/local/maps/`` and is Lead-authenticated (Lead-reachable in a Lead
session); ``map show`` and ``map diff`` are reads.
"""

from __future__ import annotations

import argparse
from typing import Any

from aew.cli.commands import _add_json, _engine, _lead_token


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


def _show(a: argparse.Namespace) -> Any:
    from aew.maps import service

    return _text(service.show(_engine(a), commit=a.commit, root=a.root, section=a.section), a.json)


def _diff(a: argparse.Namespace) -> Any:
    from aew.maps import service

    return _text(service.diff(_engine(a), a.operands or []), a.json)


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
    q.add_argument("--token", help="Lead credential (or env AEW_LEAD_TOKEN)")
    _add_json(q)
    q.set_defaults(handler=_generate)

    q = msub.add_parser("show", help="the selected (or named) structural map with its freshness against a commit "
                                     "(read-only)")
    which = q.add_mutually_exclusive_group()
    which.add_argument("--commit", metavar="H",
                       help="the commit the selected map's freshness is computed against (default: the "
                            "authoritative branch's head)")
    which.add_argument("--root", metavar="SHA", help="a stored map by its artifact sha256, instead of the selected one")
    q.add_argument("--section", metavar="NAME", help="only this section")
    _add_json(q)
    q.set_defaults(handler=_show)

    q = msub.add_parser("diff", help="section-by-section differences between two maps, each a stored root or a commit "
                                     "generated in memory (read-only)")
    q.add_argument("--root", dest="operands", action="append", type=_operand("root"), metavar="SHA",
                   help="a stored map by its artifact sha256")
    q.add_argument("--commit", dest="operands", action="append", type=_operand("commit"), metavar="H",
                   help="a commit, generated in memory and not stored")
    _add_json(q)
    q.set_defaults(handler=_diff)
