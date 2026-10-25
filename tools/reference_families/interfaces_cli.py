"""The ``cli-commands`` family (STG-12 S12-2, family 6): the ``aew`` commands, linked into the surface map.

The surface map (``docs/implementation/surface-map.yaml``) owns what each command is for, who uses it, whether it
mutates and the rest; this family does not copy any of it (the hand-off: "read from ``surface-map.yaml`` and linked,
not copied"). One record per command: its name, a link to its entry in the map's ``commands`` section, and the handler
of the live parser's leaf (``build_parser`` with every switched command registered, the idiom of ``test_surface_map``)
as the anchor.

A handler written as a lambda is anchored at the function that registers it (``register``), since a lambda has no name
of its own. A command with a leaf and no entry, or an entry and no leaf, is a record with an unresolved item naming
which is missing; ``test_surface_map`` is what holds the map equal to the live parser, and this family holds only that
every link resolves.
"""

from __future__ import annotations

import argparse
from typing import Any

import yaml

from reference_families import common as C

FAMILY = "cli-commands"
SURFACE_MAP = "docs/implementation/surface-map.yaml"
SECTION = "commands"
REGISTRY = f"{SURFACE_MAP}#{SECTION}"
PARSER = ("aew.cli.main", "build_parser")
_TESTS = "tests/integration/test_reference_interfaces.py"
TESTS = (
    f"{_TESTS}::test_every_surface_map_command_links_to_a_live_command_and_back",
    f"{_TESTS}::test_the_parser_is_built_with_every_switch_it_takes",
)


def leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()) -> Any:
    """Every command of the parser: the words that name it and the leaf parser that runs it."""
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield path, parser
        return
    for action in subs:
        for name, child in action.choices.items():
            yield from leaves(child, (*path, name))


def anchor_of(handler: Any) -> tuple[str, str] | None:
    """The module and symbol a leaf's handler is anchored at, or None when the leaf has none."""
    qualified = getattr(handler, "__qualname__", None)
    module = getattr(handler, "__module__", None)
    if not qualified or not module:
        return None
    return module, qualified.split(".<locals>")[0]


def live_commands() -> dict[str, tuple[str, str] | None]:
    from aew.cli.main import build_parser

    parser = build_parser(recall_search=True, coordination_reads=True)
    return {" ".join(path): anchor_of(leaf.get_default("handler")) for path, leaf in leaves(parser)}


def entries(ctx: C.Context) -> list[str]:
    """The names of the surface map's ``commands`` entries, in the map's order."""
    path = ctx.root / SURFACE_MAP
    try:
        doc = yaml.safe_load(C.read_source(path))
    except (C.ReferenceError, yaml.YAMLError) as exc:
        raise C.ReferenceError(f"{SURFACE_MAP} cannot be read ({exc})") from exc
    rows = doc.get(SECTION) if isinstance(doc, dict) else None
    if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in rows):
        raise C.ReferenceError(f"{SURFACE_MAP} has no {SECTION} list of named entries")
    return [r["name"] for r in rows]


def build(ctx: C.Context) -> list[C.Record]:
    live = live_commands()
    mapped = set(entries(ctx))
    records = []
    for name in sorted(mapped | set(live)):
        problems = []
        if name not in mapped:
            problems.append(C.unresolved_item(PARSER[0], PARSER[1],
                                              f"{name} is a command of the parser and has no entry in the surface map"))
        if name not in live:
            problems.append(C.unresolved_item(PARSER[0], PARSER[1],
                                              f"{name} has an entry in the surface map and is not a command of the "
                                              "parser"))
        if name in live and live[name] is None:
            problems.append(C.unresolved_item(PARSER[0], PARSER[1],
                                              f"{name} has no handler this reading can anchor (it is not a function "
                                              "with a module and a name)"))
        module, symbol = live.get(name) or PARSER
        link = {"file": SURFACE_MAP, "section": SECTION, "name": name} if name in mapped else None
        records.append(C.Record(FAMILY, name, module, symbol, "declared",
                                C.lower_bound(problems) if problems else C.complete(REGISTRY, TESTS),
                                {"command": name, "surface_map": link, "live": name in live}))
    return records
