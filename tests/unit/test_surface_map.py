"""Anti-drift guard G1, the surface map (docs/implementation/surface-map.md): every `aew` command and every typed Lead
tool is registered in ``docs/implementation/surface-map.yaml`` with who uses it, the journey that needs it, the door
the Lead reaches it by and the refusal codes it can raise, and the registry is checked against the LIVE parser and
the LIVE typed surface.

Each check has a pinned mode (``CHECKS``), and the document's table states the same modes (tested below), so changing
a mode means changing the document. An ``enforce`` check fails here, naming each item. A ``report`` check waits for
fields A1 (the projection's ``owner``) and A2 (the Lead's typed homes, structured refusals) will deliver: it lists
what it finds as a warning and never fails, and it becomes ``enforce`` when they land. Nothing is skipped or softened:
a report check's findings are computed every run, by the same code an enforce check uses.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import re
import shlex
import warnings
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml

from aew import errors
from aew.cli.main import build_parser
from aew.harness import bridge, lead_broker
from aew.surface import contract
from aew.surface.context import NORMAL

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "implementation" / "surface-map.yaml"
DOC = ROOT / "docs" / "implementation" / "surface-map.md"
VERTICAL = ROOT / "tests" / "acceptance" / "test_vertical_path.py"

ENFORCE, REPORT = "enforce", "report"
# The pinned modes. docs/implementation/surface-map.md's table states the same (test_the_pins_equal_the_document).
CHECKS: dict[str, str] = {
    "registered": ENFORCE,  # every live command and tool has an entry
    "live": ENFORCE,  # every entry names a live command or tool, once
    "fields": ENFORCE,  # users and journeys present, from the vocabulary
    "users": ENFORCE,  # users agree with the live classification (operator-only, Lead-reachable, worker bridge)
    "door": ENFORCE,  # every Lead-reachable command names its door; a typed door names built tools that run it
    "ideal_path": ENFORCE,  # every ideal-path command is registered, or listed as proposed
    "codes": ENFORCE,  # every refusal code exists in aew.errors
    "refusal_floor": ENFORCE,  # refusals include the codes the command's own arguments imply
    "owner": REPORT,  # A1: the projection's owner (operator, lead, mechanical) of each Lead lifecycle operation
    "structured_refusals": REPORT,  # A2: every refusal structured (cause, remedy, owner), the inventory complete
    "one_door": REPORT,  # A2/A4: no Lead-reachable command is shell-only
    "unmapped": REPORT,  # no entry waits for a journey decision
}
OWNERS = ("operator", "lead", "mechanical")
REPORT_PREFIX = "SurfaceMapReport: surface map, check"
TYPED = "typed"


# ---------------------------------------------------------------------------------------------- the live surface


def leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield path, parser
        return
    for action in subs:
        for name, child in action.choices.items():
            yield from leaves(child, (*path, name))


@cache
def parser() -> argparse.ArgumentParser:
    # Every switched command registered (register F21's `history search`, F9-A's `message`), so none escapes.
    return build_parser(recall_search=True, coordination_reads=True)


@cache
def live_commands() -> dict[str, argparse.ArgumentParser]:
    return {" ".join(path): p for path, p in leaves(parser())}


def resolve(argv: list[str]) -> str | None:
    """The leaf command ``argv`` (after ``aew``) names, or ``None`` when its first word is not a command."""
    current, path = parser(), []
    for word in argv:
        subs = [a for a in current._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            break
        child = next((a.choices[word] for a in subs if word in a.choices), None)
        if child is None:
            return None
        current, path = child, [*path, word]
    return " ".join(path) if path and " ".join(path) in live_commands() else None


def error_codes() -> set[str]:
    out, stack = set(), [errors.AEWError]
    while stack:
        cls = stack.pop()
        out.add(cls.code)
        stack.extend(cls.__subclasses__())
    return out


@cache
def ideal_path() -> dict[str, dict[str, str]]:
    """The vertical UAT's IDEAL_PATH table, from the module itself (the plan amends it there; nobody copies it)."""
    spec = importlib.util.spec_from_file_location("g1_vertical_path", VERTICAL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {step: dict(row) for step, row in module.IDEAL_PATH.items()}


def worker_commands() -> set[str]:
    """The commands a worker runs through its run's custody bridge (bridge.OPERATIONS: `check.run` is `check run`)."""
    return {op.replace(".", " ") for op in bridge.OPERATIONS}


def floor(name: str, kind: str) -> set[str]:
    """The refusal codes a command's or tool's own arguments imply."""
    if kind == "tool":
        t = contract.TOOLS[name]
        codes = {"STALE_REVISION"} if "expect_rev" in t.input_schema.get("properties", {}) else set()
        return codes | ({"PERMISSION_DENIED", "STALE_AUTHORITY"} if t.mutates else set())
    p = live_commands()[name]
    dests = {a.dest for a in p._actions}
    codes = {"USAGE"} if "--fields" in p._option_string_actions else set()  # expanded by the client, refused there
    if "token" in dests:
        codes |= {"USAGE", "PERMISSION_DENIED", "STALE_AUTHORITY"}  # no credential; not the Lead; superseded
    if "expect_rev" in dests:
        codes.add("STALE_REVISION")
    if "invocation_token" in dests:
        codes.add("USAGE")
    return codes


# ---------------------------------------------------------------------------------------------- the registry


def load() -> dict[str, Any]:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def entries(reg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [("cli", e) for e in reg.get("commands") or []] + [("tool", e) for e in reg.get("tools") or []]


def by_name(reg: dict[str, Any], kind: str) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for k, e in entries(reg) if k == kind}


def label(kind: str, name: str) -> str:
    return f"`aew {name}`" if kind == "cli" else f"tool `{name}`"


def lead_reachable(name: str) -> bool:
    return frozenset(name.split()) in lead_broker.LEAD_REACHABLE


def operator_only(name: str) -> bool:
    return any(p <= frozenset(name.split()) for p in lead_broker.OPERATOR_ONLY)


# ---------------------------------------------------------------------------------------------- the checks
# Each takes the registry and returns its findings, one line per item, naming it.


def check_registered(reg: dict[str, Any]) -> list[str]:
    commands, tools = by_name(reg, "cli"), by_name(reg, "tool")
    missing = [f"`aew {n}`" for n in live_commands() if n not in commands]
    missing += [f"tool `{n}`" for n in contract.TOOLS if n not in tools]
    return [f"{item} exists but is not registered in surface-map.yaml" for item in missing]


def check_live(reg: dict[str, Any]) -> list[str]:
    out, seen = [], set()
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if (kind, name) in seen:
            out.append(f"{label(kind, name)} is registered twice")
        seen.add((kind, name))
        if name not in (live_commands() if kind == "cli" else contract.TOOLS):
            out.append(f"{label(kind, name)} is registered but no longer exists")
    return out


def check_fields(reg: dict[str, Any]) -> list[str]:
    vocab = reg.get("vocabulary") or {}
    users, journeys = set(vocab.get("users") or {}), set(vocab.get("journeys") or {})
    out = []
    for kind, e in entries(reg):
        name = label(kind, str(e.get("name")))
        if not e.get("users"):
            out.append(f"{name} names no users")
        if not e.get("journeys"):
            out.append(f"{name} names no journeys (a journey, `diagnostic`, or `unmapped`)")
        out += [f"{name}: unknown user {u!r}" for u in e.get("users") or [] if u not in users]
        out += [f"{name}: unknown journey {j!r}" for j in e.get("journeys") or [] if j not in journeys]
        if "unmapped" in (e.get("journeys") or []) and len(e["journeys"]) > 1:
            out.append(f"{name}: `unmapped` cannot stand beside a journey")
    return out


def check_users(reg: dict[str, Any]) -> list[str]:
    out, workers = [], worker_commands()
    for kind, e in entries(reg):
        name, users = str(e.get("name")), set(e.get("users") or [])
        if kind == "tool":
            if users != {"lead"}:
                out.append(f"{label(kind, name)}: a typed Lead tool's only user is the Lead")
            continue
        if name not in live_commands():
            continue
        if operator_only(name) and users != {"operator"}:
            out.append(f"`aew {name}` is operator-only (lead_broker.OPERATOR_ONLY): its users must be [operator]")
        path = frozenset(name.split())
        if lead_reachable(name) and "lead" not in users:
            out.append(f"`aew {name}` is the Lead's (lead_broker.LEAD_REACHABLE): its users must name lead")
        if path in lead_broker.NOT_RELAYED and not users & {"lead", "internal"}:
            out.append(f"`aew {name}` is a typed-surface transport: its users must name lead or internal")
        if (name in workers) != ("worker" in users):
            out.append(f"`aew {name}`: `worker` must be named exactly for the worker bridge's commands "
                       f"({sorted(workers)})")
    return out


def check_door(reg: dict[str, Any]) -> list[str]:
    doors = set((reg.get("vocabulary") or {}).get("doors") or {})
    out = []
    for kind, e in entries(reg):
        name, door = str(e.get("name")), e.get("door")
        if kind == "cli" and lead_reachable(name) and door is None:
            out.append(f"`aew {name}` is Lead-reachable: name its door (typed, or shell-only pending A2/A4)")
        if door is None:
            continue
        if door not in doors:
            out.append(f"{label(kind, name)}: unknown door {door!r}")
        if door == TYPED and not e.get("via"):
            out.append(f"{label(kind, name)}: a typed door names its tools (`via`)")
        if door != TYPED and e.get("via"):
            out.append(f"{label(kind, name)}: only a typed door has `via` (use `partly_via`)")
        for tool_name in [*(e.get("via") or []), *(e.get("partly_via") or [])]:
            t = contract.TOOLS.get(tool_name)
            if t is None or not t.built or NORMAL not in t.profiles:
                out.append(f"{label(kind, name)}: {tool_name!r} is not a built tool on the normal profile")
            elif e.get("primitive") and e["primitive"] not in t.expands_to:
                out.append(f"{label(kind, name)}: tool {tool_name!r} does not run {e['primitive']!r}")
    return out


def check_ideal_path(reg: dict[str, Any]) -> list[str]:
    commands = by_name(reg, "cli")
    proposed = {p["name"]: p for p in reg.get("proposed") or []}
    out, named = [], set()
    for step, row in ideal_path().items():
        if not row["input"].startswith("aew "):
            continue  # a chat line to the Lead, not a command
        argv = shlex.split(row["input"])[1:]
        leaf = resolve(argv)
        if row["status"] == "PROPOSED":
            candidate = next((p for p in proposed if argv[:len(p.split())] == p.split()), None)
            if candidate is None:
                out.append(f"ideal path `{step}` ({row['input']}) is PROPOSED but not listed under `proposed`")
            else:
                named.add(candidate)
                if step not in (proposed[candidate].get("ideal_path") or []):
                    out.append(f"proposed `{candidate}` does not name ideal-path row `{step}`")
            continue
        if leaf is None:
            out.append(f"ideal path `{step}` ({row['input']}) names no live command")
        elif leaf not in commands:
            out.append(f"ideal path `{step}` ({row['input']}) names `aew {leaf}`, which is not registered")
    for name in proposed:
        if name in live_commands():
            out.append(f"proposed `aew {name}` exists now: move it to `commands`, and its ideal-path rows to EXISTS")
        elif name not in named:
            out.append(f"proposed `aew {name}` is named by no PROPOSED ideal-path row")
    return out


def check_codes(reg: dict[str, Any]) -> list[str]:
    known = error_codes()
    return [f"{label(kind, str(e.get('name')))}: {code} is not a code in aew.errors"
            for kind, e in entries(reg) for code in e.get("refusals") or [] if code not in known]


def check_refusal_floor(reg: dict[str, Any]) -> list[str]:
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if name not in (live_commands() if kind == "cli" else contract.TOOLS):
            continue
        missing = floor(name, kind) - set(e.get("refusals") or [])
        if missing:
            out.append(f"{label(kind, name)}: its arguments imply refusals {sorted(missing)}, not listed")
    return out


def check_owner(reg: dict[str, Any]) -> list[str]:
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        lifecycle = lead_reachable(name) if kind == "cli" else getattr(contract.TOOLS.get(name), "mutates", False)
        if lifecycle and e.get("owner") not in OWNERS:
            out.append(f"{label(kind, name)}: owner is {e.get('owner')!r}, not one of {OWNERS} (A1)")
    return out


def check_structured_refusals(reg: dict[str, Any]) -> list[str]:
    default = reg.get("refusal_status") or {}
    out = []
    for kind, e in entries(reg):
        status = {**default, **(e.get("refusal_status") or {})}
        if status.get("inventory") != "complete" or status.get("structured") != "yes":
            out.append(f"{label(kind, str(e.get('name')))}: refusals inventory {status.get('inventory')!r}, structured "
                       f"{status.get('structured')!r} (A2)")
    return out


def check_one_door(reg: dict[str, Any]) -> list[str]:
    return [f"`aew {e['name']}` is reached only from the shell ({e['door']})" for kind, e in entries(reg)
            if kind == "cli" and lead_reachable(str(e.get("name"))) and e.get("door") not in (None, TYPED)]


def check_unmapped(reg: dict[str, Any]) -> list[str]:
    return [f"{label(kind, e['name'])} is unmapped: name the journey that needs it, or retire it"
            for kind, e in entries(reg) if "unmapped" in (e.get("journeys") or [])]


CHECK_FUNCTIONS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "registered": check_registered, "live": check_live, "fields": check_fields, "users": check_users,
    "door": check_door, "ideal_path": check_ideal_path, "codes": check_codes, "refusal_floor": check_refusal_floor,
    "owner": check_owner, "structured_refusals": check_structured_refusals, "one_door": check_one_door,
    "unmapped": check_unmapped,
}


# ---------------------------------------------------------------------------------------------- the tests


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_surface_map_check(check):
    findings = CHECK_FUNCTIONS[check](load())
    if CHECKS[check] == ENFORCE:
        assert not findings, f"surface map, check `{check}`:\n" + "\n".join(findings)
    elif findings:
        # A plain UserWarning: xdist rebuilds a warning's class on the controller, which cannot import a test module.
        warnings.warn(UserWarning(f"{REPORT_PREFIX} `{check}` (report-only), {len(findings)} item(s):\n"
                                  + "\n".join(findings)), stacklevel=1)


def test_the_pins_equal_the_document():
    """Every check is pinned enforce or report, and docs/implementation/surface-map.md's table says the same."""
    assert set(CHECKS) == set(CHECK_FUNCTIONS) and set(CHECKS.values()) <= {ENFORCE, REPORT}
    rows = re.findall(r"^\| `([a-z_]+)` \| (enforce|report) \|", DOC.read_text(encoding="utf-8"), re.MULTILINE)
    assert dict(rows) == CHECKS and len(rows) == len(CHECKS)


def test_the_registry_is_versioned_and_states_its_vocabulary():
    reg = load()
    assert reg["schema"] == "aew/surface-map/v1" and isinstance(reg["version"], int) and reg["version"] >= 1
    vocab = reg["vocabulary"]
    assert {"operator", "lead", "worker", "diagnostic"} <= set(vocab["users"])
    assert {"diagnostic", "unmapped"} <= set(vocab["journeys"])
    assert set(vocab["doors"]) == {TYPED, "shell-only (pending A2/A4)"}


def test_the_walk_and_the_ideal_path_are_the_live_ones():
    """The guard sees what it guards: the switched commands, every Lead-reachable command, and the ideal path's
    existing commands resolve to live leaves."""
    commands = live_commands()
    assert {"history search", "message thread", "message unseen"} <= set(commands)
    assert {" ".join(sorted(p)) for p in lead_broker.LEAD_REACHABLE} <= {" ".join(sorted(c.split())) for c in commands}
    rows = ideal_path()
    assert resolve(shlex.split(rows["raise"]["input"])[1:]) == "lead mode raise"
    assert resolve(shlex.split(rows["open"]["input"])[1:]) == "opencode"
    assert resolve(["preflight"]) is None and worker_commands() == {"whoami", "check run", "submit"}


# Each enforced check fails, naming the item, on the drift it exists to catch.
def _drop(kind: str, name: str) -> Callable[[dict[str, Any]], None]:
    def edit(reg: dict[str, Any]) -> None:
        key = "commands" if kind == "cli" else "tools"
        reg[key] = [e for e in reg[key] if e["name"] != name]
    return edit


def _entry(reg: dict[str, Any], name: str, kind: str = "cli") -> dict[str, Any]:
    return by_name(reg, kind)[name]


DRIFT: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    ("registered", _drop("cli", "work move"), "`aew work move` exists but is not registered"),
    ("registered", _drop("tool", "ticket_start"), "tool `ticket_start` exists but is not registered"),
    ("live", lambda r: r["commands"].append({"name": "work teleport", "users": ["lead"], "journeys": ["unmapped"]}),
     "`aew work teleport` is registered but no longer exists"),
    ("live", lambda r: r["tools"].append({"name": "ticket_fly", "users": ["lead"], "journeys": ["unmapped"]}),
     "tool `ticket_fly` is registered but no longer exists"),
    ("fields", lambda r: _entry(r, "init").pop("journeys"), "`aew init` names no journeys"),
    ("fields", lambda r: _entry(r, "init").update(users=[]), "`aew init` names no users"),
    ("fields", lambda r: _entry(r, "init").update(journeys=["V9"]), "`aew init`: unknown journey 'V9'"),
    ("users", lambda r: _entry(r, "lead acquire").update(users=["operator", "lead"]),
     "`aew lead acquire` is operator-only"),
    ("users", lambda r: _entry(r, "work create").update(users=["operator"]), "`aew work create` is the Lead's"),
    ("users", lambda r: _entry(r, "submit").update(users=["lead"]), "`aew submit`: `worker` must be named"),
    ("door", lambda r: _entry(r, "plan accept").pop("door"), "`aew plan accept` is Lead-reachable: name its door"),
    ("door", lambda r: _entry(r, "work create").update(via=["ticket_start"]),
     "`aew work create`: tool 'ticket_start' does not run 'work.create'"),
    ("door", lambda r: _entry(r, "work create").update(via=["cli"]), "'cli' is not a built tool on the normal"),
    ("ideal_path", _drop("cli", "opencode"), "names `aew opencode`, which is not registered"),
    ("ideal_path", lambda r: r.update(proposed=[]), "is PROPOSED but not listed under `proposed`"),
    ("ideal_path", lambda r: r["proposed"].append({"name": "init", "ideal_path": []}),
     "proposed `aew init` exists now"),
    ("codes", lambda r: _entry(r, "init")["refusals"].append("SEAT_HELD"), "SEAT_HELD is not a code in aew.errors"),
    ("refusal_floor", lambda r: _entry(r, "plan accept").update(refusals=["USAGE"]),
     "`aew plan accept`: its arguments imply refusals ['PERMISSION_DENIED', 'STALE_AUTHORITY', 'STALE_REVISION']"),
    ("refusal_floor", lambda r: _entry(r, "ticket_start", "tool").update(refusals=[]), "tool `ticket_start`: its"),
]


@pytest.mark.parametrize(("check", "edit", "named"), DRIFT, ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(DRIFT)])
def test_an_enforced_check_names_the_drift(check, edit, named):
    reg = copy.deepcopy(load())
    assert not any(named in f for f in CHECK_FUNCTIONS[check](reg))
    edit(reg)
    findings = CHECK_FUNCTIONS[check](reg)
    assert any(named in f for f in findings), findings


def test_a_report_check_sees_its_pending_field_and_clears_when_it_lands():
    """The report checks measure today's gap, and pass on a registry where A1 and A2 have landed."""
    reg = copy.deepcopy(load())
    assert check_owner(reg) and check_structured_refusals(reg) and check_one_door(reg)
    reg["refusal_status"] = {"inventory": "complete", "structured": "yes"}
    for _, e in entries(reg):
        if "owner" in e:
            e["owner"] = "lead"
        if e.get("door") not in (None, TYPED):
            e.update(door=TYPED, via=["status"], primitive=None)
            e.pop("partly_via", None)
        e["journeys"] = ["diagnostic"] if "unmapped" in e["journeys"] else e["journeys"]
    for check in ("owner", "structured_refusals", "one_door", "unmapped"):
        assert CHECK_FUNCTIONS[check](reg) == [], check
