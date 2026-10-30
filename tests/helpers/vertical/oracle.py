"""V-01's acceptance oracle: row V01-01's ideal path, each step's state derived from the code's own registries.

The designer's ruling of 2026-10-23 (V-UAT-3: each ideal-path step cites an adopted action and its surface; V-UAT-5:
the frozen instrument is retired in the same pull request), built to row V01-01 of STG-13's V-01 matrix. Each step
names its A-32 catalog IDs and the O-01 action, D-01 route or local surface that serves it, as the row gives them; the
row's text stays in the design workspace. A step's state is never kept here. It is derived:

- **a wire action** from the vendored O-01 registry the carrier loads (``aew.stg02.adopted.registry()``) and from the
  carrier's own admission (``Carrier._member``, read by the generated reference's own reader): ``not built`` (not in
  the registry), ``registry only`` (refused at its origin, before any owner state is read), ``admitted`` (past its
  origin, no owner acts on it) or ``reaches an owner``;
- **a D-01 read** from the routes the STG-02 server's dispatch serves (the reference's reader of ``handle``):
  ``served`` or ``not built``;
- **a local step** from its surface: ``built`` when the CLI has the command, ``outside AEW`` for the harness's own act,
  ``not built`` when no code serves it.

A step is as far as its weakest part, and names what holds it (the row's "Held by") until it lands. So a newly built
surface moves its step with no edit here. A step names no proposed command: ``proposed_names`` fails on one.

**The PIN budget** (the operator's decision of 2026-10-24 on F1, the matrix's budgets since A-39): one PIN per
G3-protected step on a scenario's path, the raise included, derived from the path, never kept by hand.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import re
import sys
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

ROOT = Path(__file__).resolve().parents[3]

# The origin classes A-32 gives the path's actions (the O-01 registry's `origin` values).
G3 = "PROTECTED_G3"
DELEGATED, SUCCESSOR = "CURRENT_DELEGATED_GRANT", "CURRENT_SUCCESSOR_GENERATION"

NOT_BUILT, REGISTRY_ONLY, ADMITTED, REACHES_OWNER = "not built", "registry only", "admitted", "reaches an owner"
SERVED, BUILT, OUTSIDE = "served", "built", "outside AEW"
# How far a state is; a step is as far as its weakest part, and has landed at LANDED.
RANK = {NOT_BUILT: 0, REGISTRY_ONLY: 1, ADMITTED: 2, REACHES_OWNER: 3, SERVED: 3, BUILT: 3, OUTSIDE: 3}
LANDED = 3


class Wire(NamedTuple):
    """An O-01 action: its A-32 row, its name, the origin class the row gives it, the adoption that places it."""

    catalog: str
    action: str
    origin: str
    adopted: str


class Read(NamedTuple):
    """A D-01 read: its A-32 row and its route."""

    catalog: str
    route: str


class Local(NamedTuple):
    """A local or manual act: its A-32 row, its act (None: NO_COMMAND), the `aew` command that serves it (None: no
    code surface), and whether it is served outside AEW (the harness's own act)."""

    catalog: str
    act: str | None
    command: tuple[str, ...] | None
    outside: bool = False


class Step(NamedTuple):
    n: int
    key: str
    scenarios: frozenset[str]  # "all", a scenario (V1..V4), or "steering" (the steering-on variants)
    catalog: tuple[str, ...]  # the row's A-32 IDs for the step
    serves: tuple[Wire | Read | Local, ...]
    held_by: tuple[str, ...]  # the row's "Held by", reported until the step lands


def _s(*tags: str) -> frozenset[str]:
    return frozenset(tags)


# Row V01-01, its 13 steps (V-01-MATRIX.md, rows 1 to 13, as refreshed 2026-10-26 for A-39).
STEPS: tuple[Step, ...] = (
    Step(1, "init", _s("all"), ("L10",), (Local("L10", "INIT_OR_REGISTER_PROJECT", ("init",)),), ()),
    # A-39: a setup act at the console beside `aew init`, with no O-01 command and no PIN; no code serves it yet.
    Step(2, "configure", _s("all"), ("L10",), (Local("L10", None, None),), ()),
    Step(3, "open", _s("V1"), ("L01", "L02"),
         (Read("L01", "/v1/read/attachments"), Wire("L02", "ATTACH_LEAD", G3, "A-25")), ("G3",)),
    # R1: the chat line is the outcome's own input; the step cites the action it produces, the Lead's.
    Step(4, "ask", _s("V1"), ("W15",), (Wire("W15", "CREATE_PROPOSED_WORK", SUCCESSOR, "A-29"),), ()),
    Step(5, "plan", _s("V1"), ("W02",), (Wire("W02", "DECIDE_WORK_PROPOSAL", G3, "A-29"),), ("G3",)),
    Step(6, "work", _s("V1"), ("W10", "C17"),
         (Wire("W10", "DELEGATE_NEW_WORKER", SUCCESSOR, "A-30"),
          Wire("C17", "CONTINUE_ELIGIBLE_WORK", DELEGATED, "A-24")), ()),
    Step(7, "publish", _s("V1"), ("W09", "C10"), (Wire("W09", "APPROVE_INTEGRATION", G3, "A-31"),),
         ("G3", "I4-06", "I4-B7")),
    Step(8, "result", _s("V1"), ("U03", "L12"),
         (Read("U03", "/v1/read/assurance/{subject_kind}/{subject_id}"), Read("U03", "/v1/read/resolve"),
          Read("L12", "/v1/read/work/{work_kind}/{work_id}")), ()),
    Step(9, "exit", _s("V2"), ("L09",), (Local("L09", "END_HARNESS_SESSION", None, outside=True),), ()),
    Step(10, "reopen", _s("V2"), ("L03", "U01", "C18", "L07"),
         (Wire("L03", "REATTACH_LEAD", G3, "A-25"), Read("U01", "/v1/read/waiting"), Read("U01", "/v1/read/attention"),
          Read("C18", "/v1/read/continuation-state/{work_id}"), Read("L07", "/v1/read/attachments")), ("G3",)),
    Step(11, "preflight", _s("V3"), ("P03",), (Read("P03", "/v1/read/capabilities"),), ()),
    Step(12, "setting", _s("V4"), ("P04", "P14"), (Wire("P14", "ADOPT_MANIFEST_EDIT", G3, "A-39"),), ("G3",)),
    Step(13, "raise", _s("steering"), ("P08",), (Wire("P08", "SET_STEERING_MODE", G3, "A-39"),), ("G3",)),
)
STEP = {s.key: s for s in STEPS}

# V2 and V4 are V1's path plus their own steps (vertical-uat.md §3); V3 is setup plus readiness, and the open step only
# when its path gets that far (`also`). A path lists its steps in step order, not the order a scenario takes them.
INHERITS: dict[str, tuple[str, ...]] = {"V1": ("V1",), "V2": ("V1", "V2"), "V3": ("V3",), "V4": ("V1", "V4")}


# ---------------------------------------------------------------------------------------------- the code's facts


class Facts(NamedTuple):
    registry: Mapping[str, str]  # action -> origin, the vendored O-01 registry
    admitted_origin: str  # the origin the carrier lets past (Carrier._member)
    owner_action: str  # the one action it hands to an owner
    routes: frozenset[str]  # the D-01 routes of the vendored problem matrix
    served: frozenset[str]  # the ones the STG-02 server serves
    commands: frozenset[str]  # the CLI's leaf commands ("init", "lead mode raise", ...)


def readers() -> tuple[Any, Any]:
    """The generated reference's readers of the carrier and the server (one owner of those facts), with ``tools/`` on
    the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import stg02_commands, stg02_server
    finally:
        sys.path.remove(here)
    return stg02_commands, stg02_server


def cli_commands(parser: argparse.ArgumentParser) -> frozenset[str]:
    """Every leaf command of the CLI, as its words after ``aew``."""
    out: set[str] = set()

    def walk(p: argparse.ArgumentParser, path: list[str]) -> None:
        subs = [a for a in p._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs and path:
            out.add(" ".join(path))
        for a in subs:
            for name, child in a.choices.items():
                walk(child, [*path, name])

    walk(parser, [])
    return frozenset(out)


@cache
def code_facts() -> Facts:
    """The facts at this commit. The carrier's and the server's are read from their source by the reference's own
    readers; a carrier whose admission they cannot read stops the derivation, never guesses."""
    from aew.cli.main import build_parser
    from aew.stg02 import adopted, commands, server

    stg02_commands, stg02_server = readers()
    reading = stg02_commands.read(ast.parse(inspect.getsource(commands)))
    if reading.origin is None or reading.action is None:
        raise RuntimeError("the carrier's admission (Carrier._member) is not where the reference's reader looks: the "
                           "oracle cannot derive the wire states")
    routes = sorted({str(r["route"]) for r in adopted.matrix() if r["api"] == "D01"})
    served = stg02_server.tie(routes, stg02_server.read(ast.parse(inspect.getsource(server)), vars(server))).served
    return Facts({a: r["origin"] for a, r in adopted.registry().items()}, reading.origin, reading.action,
                 frozenset(routes), frozenset(served), cli_commands(build_parser()))


# ---------------------------------------------------------------------------------------------- the derivation


def part_state(item: Wire | Read | Local, facts: Facts) -> str:
    if isinstance(item, Wire):
        origin = facts.registry.get(item.action)
        if origin is None:
            return NOT_BUILT
        if origin != facts.admitted_origin:
            return REGISTRY_ONLY
        return REACHES_OWNER if item.action == facts.owner_action else ADMITTED
    if isinstance(item, Read):
        return SERVED if item.route in facts.served else NOT_BUILT
    if item.outside:
        return OUTSIDE
    return BUILT if item.command is not None and " ".join(item.command) in facts.commands else NOT_BUILT


def _named(item: Wire | Read | Local) -> dict[str, Any]:
    if isinstance(item, Wire):
        return {"action": item.action}
    if isinstance(item, Read):
        return {"route": item.route}
    return {"act": item.act or "NO_COMMAND", "surface": "aew " + " ".join(item.command) if item.command else
            "the harness's own" if item.outside else None}


def landed(state: str) -> bool:
    return RANK[state] >= LANDED


def derive(steps: Iterable[Step] = STEPS, facts: Facts | None = None) -> list[dict[str, Any]]:
    """Each step's state, its parts' states, and what holds it while it has not landed."""
    facts = facts or code_facts()
    out = []
    for s in steps:
        parts = [{"catalog": i.catalog, **_named(i), "state": part_state(i, facts)} for i in s.serves]
        state = min((p["state"] for p in parts), key=RANK.__getitem__) if parts else NOT_BUILT
        out.append({"step": s.n, "key": s.key, "catalog": list(s.catalog), "state": state, "parts": parts,
                    **({"held_by": list(s.held_by)} if s.held_by and not landed(state) else {})})
    return out


def state_of(key: str, facts: Facts | None = None) -> dict[str, Any]:
    return derive([STEP[key]], facts)[0]


def path(scenario: str, *, steering: bool = False, also: tuple[str, ...] = (),
         steps: Iterable[Step] = STEPS) -> tuple[Step, ...]:
    """The scenario's steps: the ones the row tags with it (V2 and V4 inherit V1's), setup's, the raise when steering
    is on, and ``also`` (V3's open, when its path gets that far)."""
    tags = {"all", *INHERITS[scenario], *(("steering",) if steering else ())}
    return tuple(s for s in steps if s.scenarios & tags or s.key in also)


def g3_protected(step: Step) -> bool:
    return any(isinstance(i, Wire) and i.origin == G3 for i in step.serves)


def pin_budget(steps: Iterable[Step]) -> int:
    """One PIN per G3-protected step on the path (the operator's decision of 2026-10-24, F1)."""
    return sum(1 for s in steps if g3_protected(s))


# ---------------------------------------------------------------------------------------------- the checks

ADOPTION = re.compile(r"A-\d+")
ACTION = re.compile(r"[A-Z][A-Z0-9_]*")


def proposed_names(steps: Iterable[Step] = STEPS, facts: Facts | None = None) -> list[str]:
    """Every name on the path that nothing adopted or built carries: a CLI surface the CLI does not have, a route that
    is no route of the vendored D-01 matrix, an action neither in the registry nor placed by an adoption."""
    facts = facts or code_facts()
    out = []
    for s in steps:
        for i in s.serves:
            if isinstance(i, Local) and i.command is not None and " ".join(i.command) not in facts.commands:
                out.append(f"step {s.n} ({s.key}): `aew {' '.join(i.command)}` is no command of the CLI")
            elif isinstance(i, Read) and i.route not in facts.routes:
                out.append(f"step {s.n} ({s.key}): {i.route} is no route of the vendored D-01 matrix")
            elif isinstance(i, Wire) and (not ACTION.fullmatch(i.action) or
                                          (i.action not in facts.registry and not ADOPTION.fullmatch(i.adopted))):
                out.append(f"step {s.n} ({s.key}): {i.action} is neither in the O-01 registry nor placed by an "
                           "adoption")
    return out


def registry_disagreements(steps: Iterable[Step] = STEPS, facts: Facts | None = None) -> list[str]:
    """A step's action that the registry carries must have the origin the row gives it."""
    facts = facts or code_facts()
    return [f"step {s.n} ({s.key}): {i.action} is {i.origin} on the path and {facts.registry[i.action]} in the registry"
            for s in steps for i in s.serves
            if isinstance(i, Wire) and i.action in facts.registry and facts.registry[i.action] != i.origin]


def summary_line(records: Iterable[dict[str, Any]]) -> str:
    """The steps on one line: each step's number, key and state, and what holds it."""
    return "; ".join(f"{r['step']} {r['key']} {r['state']}" + (f" [{', '.join(r['held_by'])}]" if r.get("held_by")
                                                                else "") for r in records)
