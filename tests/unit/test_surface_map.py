"""Anti-drift guard G1, the surface map (docs/implementation/surface-map.md): every `aew` command and every typed Lead
tool is registered in ``docs/implementation/surface-map.yaml`` with one intentional home, its users, the journeys that
exercise it, whether it mutates, the door the Lead reaches it by and its end-state disposition, and the refusal codes
it can raise; the registry is checked against the LIVE parser, the LIVE typed surface and the primitive declarations.

Each check has a pinned mode (``CHECKS``), and the document's table states the same modes (tested below), so changing
a mode means changing the document. An ``enforce`` check fails here, naming each item. A ``report`` check waits for
what A1 (the projection's ``owner``), A2 (the Lead's typed homes and dispositions, structured refusals) and A4 (the
shell door closed) will deliver: it lists what it finds as a warning, whatever the run's warning filters, and never
fails; it becomes ``enforce`` when they land. Nothing is skipped or softened: a report check's findings are computed
every run, by the same code an enforce check uses.

**The standing rule for new surfaces** (operator, 2026-10-12): an entry outside the grandfathered ``BASELINE`` ships
with a decided ``lead_disposition`` that the live code honours (check ``new_surface``). The baseline may only shrink.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
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
from aew.engine import primitives
from aew.harness import bridge, lead_broker
from aew.surface import contract
from aew.surface.context import NORMAL

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs" / "implementation" / "surface-map.yaml"
DOC = ROOT / "docs" / "implementation" / "surface-map.md"
VERTICAL = ROOT / "tests" / "acceptance" / "test_vertical_path.py"
REPORT_ENV = "AEW_SURFACE_MAP_REPORT"  # a directory: each report check writes surface-map-<check>.json there

ENFORCE, REPORT = "enforce", "report"
# The pinned modes. docs/implementation/surface-map.md's table states the same (test_the_pins_equal_the_document).
CHECKS: dict[str, str] = {
    "registered": ENFORCE,  # every live command and tool has an entry
    "live": ENFORCE,  # every entry names a live command or tool, once
    "fields": ENFORCE,  # home, users, journeys, mutates, refusals present and from the vocabulary
    "users": ENFORCE,  # users agree with the live classification (operator-only, Lead-reachable, worker bridge)
    "home": ENFORCE,  # a diagnostic home mutates nothing
    "mutates": ENFORCE,  # the declaration agrees with the code's own markers (contract, credential, revision)
    "door": ENFORCE,  # a Lead-reachable command names its door; a typed door is proved by its primitive
    "disposition": ENFORCE,  # a Lead-reachable command names its disposition; `typed` only with a proved typed door
    "new_surface": ENFORCE,  # outside the baseline: a decided disposition, honoured by the live code
    "ideal_path": ENFORCE,  # every ideal-path command is registered, or listed as proposed
    "codes": ENFORCE,  # every refusal code exists in aew.errors
    "refusal_floor": ENFORCE,  # refusals include the codes the command's own arguments imply
    "owner": REPORT,  # A1: the projection's owner (operator, lead, mechanical) of each Lead lifecycle operation
    "structured_refusals": REPORT,  # A2: every refusal structured (cause, remedy, owner), the inventory complete
    "mutates_unknown": REPORT,  # every surface's `mutates` classified
    "undecided": REPORT,  # A2's plan: every Lead-reachable command's disposition decided
    "disposition_applied": REPORT,  # A4: engine-owned and forbidden-to-lead commands have left LEAD_REACHABLE
    "lead_shell_lifecycle": REPORT,  # A4: Lead shell lifecycle operations = 0
    "unevidenced": REPORT,  # a product, admin or recovery home that no vertical journey exercises yet
}
OWNERS = ("operator", "lead", "mechanical")
REPORT_PREFIX = "SurfaceMapReport: surface map, check"
TYPED, UNDECIDED = "typed", "undecided"
LEAVES_LEAD_DOORS = ("engine-owned", "forbidden-to-lead")
DIAGNOSTIC = "diagnostic"
# A typed door's primitive names its command: its words are the command's words (`work.create` is `aew work create`;
# `invoke.create.mutating` starts with `invoke create`), except for these (PR 215 review, finding 1).
PRIMITIVE_ALIASES: dict[str, frozenset[str]] = {
    "stage.resolve": frozenset({"stage continue", "stage abandon"}),
    "steering": frozenset({"lead mode lower"}),
}

# The grandfathered surfaces (operator, 2026-10-12): every entry registered when the standing rule was adopted. Their
# `undecided` dispositions stay report-only until A2/A4; anything else must satisfy `new_surface`. The list may only
# shrink: FROZEN is pinned by its digest, and BASELINE is FROZEN minus the entries that have graduated.
FROZEN: frozenset[str] = frozenset("""
cli:authority accept|cli:authority list|cli:authority reject|cli:check run|cli:checkpoint|cli:context pack
cli:context show|cli:dashboard open|cli:dashboard serve|cli:dashboard status|cli:dispatch explain|cli:doctor
cli:evidence ingest|cli:gate show|cli:gate waive|cli:guide|cli:harness config|cli:harness interrupt
cli:harness launch|cli:harness send|cli:harness status|cli:harness stop|cli:harness wait|cli:history audit
cli:history compact|cli:history links|cli:history list|cli:history load|cli:history log|cli:history reindex
cli:history search|cli:history show|cli:init|cli:integrate breaker reset|cli:integrate breaker status
cli:integrate custody|cli:integrate defer|cli:integrate prepare|cli:integrate publish|cli:integrate reconcile
cli:integrate reorder|cli:integrate requeue|cli:integrate validate|cli:invoke cancel|cli:invoke create
cli:invoke show|cli:lead acquire|cli:lead handoff accept|cli:lead handoff cancel|cli:lead handoff offer
cli:lead mcp|cli:lead mode lower|cli:lead mode raise|cli:lead release|cli:lead session|cli:lead show
cli:lead takeover|cli:lead tool|cli:manifest adopt|cli:map diff|cli:map generate|cli:map select-architecture
cli:map show|cli:message list|cli:message thread|cli:message unseen|cli:migrate|cli:opencode|cli:operator ping
cli:operator serve|cli:plan accept|cli:plan adopt|cli:plan lint|cli:plan propose|cli:plan reconfirm
cli:resume|cli:review ingest|cli:role list|cli:role show|cli:role validate|cli:stage abandon
cli:stage continue|cli:status|cli:submit|cli:verify classify|cli:verify ingest|cli:whoami|cli:work accept
cli:work acknowledge-input|cli:work assign|cli:work cancel|cli:work close|cli:work create|cli:work depend
cli:work dispatch|cli:work dispose|cli:work list|cli:work move|cli:work promote|cli:work ready
cli:work reclassify|cli:work reconcile|cli:work redispatch|cli:work roles|cli:work show|cli:work staff
cli:work transition|cli:work tree|tool:checkpoint|tool:cli|tool:explain|tool:harness_status
tool:harness_wait|tool:integration_publish|tool:resolve|tool:resume|tool:status|tool:steering
tool:ticket_draft|tool:ticket_prepare|tool:ticket_request_review|tool:ticket_request_verification
tool:ticket_start|tool:work_show
""".replace("\n", "|").strip("|").split("|"))
FROZEN_DIGEST = "1b32b35999eb5a75aeda9ec3723275afa2d6f439de42469d864ab19914ce5d81"
GRADUATED: frozenset[str] = frozenset()  # entries that left the baseline (their disposition decided and honoured)
BASELINE = FROZEN - GRADUATED


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


def dests(name: str) -> set[str]:
    return {a.dest for a in live_commands()[name]._actions}


def revision_dests(name: str) -> set[str]:
    """The expected-revision arguments (`expect_rev`, `expect_map_rev`, ...): each is a compare-and-set."""
    return {d for d in dests(name) if re.fullmatch(r"expect_\w*rev", d)}


def floor(name: str, kind: str) -> set[str]:
    """The refusal codes a command's or tool's own arguments imply."""
    if kind == "tool":
        t = contract.TOOLS[name]
        codes = {"STALE_REVISION"} if "expect_rev" in t.input_schema.get("properties", {}) else set()
        return codes | ({"PERMISSION_DENIED", "STALE_AUTHORITY"} if t.mutates else set())
    p, ds = live_commands()[name], dests(name)
    codes = {"USAGE"} if "--fields" in p._option_string_actions else set()  # expanded by the client, refused there
    if "token" in ds:
        codes |= {"USAGE", "PERMISSION_DENIED", "STALE_AUTHORITY"}  # no credential; not the Lead; superseded
    if revision_dests(name):
        codes.add("STALE_REVISION")
    if "invocation_token" in ds:
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


def is_live(kind: str, name: str) -> bool:
    return name in (live_commands() if kind == "cli" else contract.TOOLS)


def lead_reachable(name: str) -> bool:
    return frozenset(name.split()) in lead_broker.LEAD_REACHABLE


def operator_only(name: str) -> bool:
    return any(p <= frozenset(name.split()) for p in lead_broker.OPERATOR_ONLY)


def mutates(e: dict[str, Any]) -> str:
    """`no`, `yes`, `with` (only with the flags it names) or `unknown`; anything else is `invalid`."""
    m = e.get("mutates")
    if isinstance(m, dict):
        return "with" if set(m) == {"with"} and m["with"] and all(str(f).startswith("--") for f in m["with"]) \
            else "invalid"
    return m if m in ("no", "yes", "unknown") else "invalid"


def primitive_names(name: str, primitive: str) -> bool:
    """Whether ``primitive`` is the step of command ``name`` (its words, or an alias)."""
    if primitive in PRIMITIVE_ALIASES:
        return name in PRIMITIVE_ALIASES[primitive]
    words = name.split()
    return primitive.split(".")[:len(words)] == words


def proved_typed(name: str, e: dict[str, Any]) -> list[str]:
    """Why ``e``'s typed door is not proved (empty when it is): built tools on the normal profile run a primitive that
    names this command and has a side effect."""
    out, p = [], e.get("primitive")
    if not e.get("via"):
        out.append("a typed door names its tools (`via`)")
    if not p:
        return [*out, "a typed door names the primitive its tools run (`primitive`)"]
    if not primitive_names(name, p):
        out.append(f"primitive {p!r} is not this command's step")
    spec = primitives.SPECS.get(p)
    if spec is None or not spec.side_effect_class or spec.side_effect_class == "none":
        out.append(f"primitive {p!r} has no declared side effect in primitives.SPECS")
    for tool_name in e.get("via") or []:
        t = contract.TOOLS.get(tool_name)
        if t is None or not t.built or NORMAL not in t.profiles:
            out.append(f"{tool_name!r} is not a built tool on the normal profile")
        elif p not in t.expands_to:
            out.append(f"tool {tool_name!r} does not run {p!r}")
    return out


def baseline_key(kind: str, name: str) -> str:
    return f"{kind}:{name}"


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
        if not is_live(kind, name):
            out.append(f"{label(kind, name)} is registered but no longer exists")
    return out


def check_fields(reg: dict[str, Any]) -> list[str]:
    vocab = reg.get("vocabulary") or {}
    homes, users, journeys = set(vocab.get("homes") or {}), set(vocab.get("users") or {}), set(vocab.get("journeys")
                                                                                               or {})
    out = []
    for kind, e in entries(reg):
        name = label(kind, str(e.get("name")))
        if not isinstance(e.get("home"), str) or e["home"] not in homes:
            out.append(f"{name}: needs exactly one home from {sorted(homes)}, not {e.get('home')!r}")
        if not e.get("users"):
            out.append(f"{name} names no users")
        out += [f"{name}: unknown user {u!r}" for u in e.get("users") or [] if u not in users]
        if not isinstance(e.get("journeys"), list):
            out.append(f"{name}: `journeys` is the list of vertical journeys that exercise it (possibly empty)")
        out += [f"{name}: unknown journey {j!r}" for j in e.get("journeys") or [] if j not in journeys]
        if mutates(e) == "invalid":
            out.append(f"{name}: `mutates` is \"no\", \"yes\" (quoted: YAML reads a bare yes as true), unknown "
                       f"or {{with: [--flag, ...]}}, not {e.get('mutates')!r}")
        if not e.get("mutates_basis"):
            out.append(f"{name}: `mutates_basis` says how its `mutates` was determined")
        if not isinstance(e.get("refusals"), list):
            out.append(f"{name}: `refusals` is a list of aew.errors codes")
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
        if lead_reachable(name) and "lead" not in users:
            out.append(f"`aew {name}` is the Lead's (lead_broker.LEAD_REACHABLE): its users must name lead")
        if frozenset(name.split()) in lead_broker.NOT_RELAYED and not users & {"lead", "internal"}:
            out.append(f"`aew {name}` is a typed-surface transport: its users must name lead or internal")
        if (name in workers) != ("worker" in users):
            out.append(f"`aew {name}`: `worker` must be named exactly for the worker bridge's commands "
                       f"({sorted(workers)})")
    return out


def check_home(reg: dict[str, Any]) -> list[str]:
    """The designer's positive definition (2026-10-12): a diagnostic surface observes or repairs implementation state,
    is needed by no supported normal workflow, and changes no authority, policy, work state, evidence admissibility,
    publication, lifecycle or external system."""
    return [f"{label(kind, str(e.get('name')))} is homed diagnostic but its mutates is {e.get('mutates')!r}: "
            "re-home it, or split the mutating form into its own command"
            for kind, e in entries(reg) if e.get("home") == DIAGNOSTIC and mutates(e) != "no"]


def check_mutates(reg: dict[str, Any]) -> list[str]:
    out = []
    for kind, e in entries(reg):
        name, m = str(e.get("name")), mutates(e)
        if not is_live(kind, name):
            continue
        if kind == "tool":
            if m != ("yes" if contract.TOOLS[name].mutates else "no"):
                out.append(f"tool `{name}`: mutates {e.get('mutates')!r} contradicts contract.Tool.mutates")
            continue
        flags = set((e.get("mutates") or {}).get("with") or []) if m == "with" else set()
        for dest in sorted(revision_dests(name)):
            flag = "--" + dest.replace("_", "-")
            if m != "yes" and flag not in flags:
                out.append(f"`aew {name}` takes {flag} (a compare-and-set): its mutates must be yes, or name {flag}")
        if "token" in dests(name) and m not in ("yes", "with") and not e.get("mutates_exempt"):
            out.append(f"`aew {name}` takes the Lead credential: its mutates must be yes or with, or give "
                       "`mutates_exempt` with the reason")
        if operator_only(name) and m not in ("yes", "with") and not (m == "no" and e.get("home") == DIAGNOSTIC):
            out.append(f"`aew {name}` is operator-only: it mutates, unless it is a pure read homed diagnostic")
        p = e.get("primitive")
        if p and m == "no":
            out.append(f"`aew {name}` runs primitive {p!r} but is declared `mutates: no`")
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
        if door == TYPED and kind == "cli" and lead_reachable(name):
            out += [f"`aew {name}`: {why}" for why in proved_typed(name, e)]
        elif door == TYPED and not e.get("via"):
            out.append(f"{label(kind, name)}: a typed door names its tools (`via`)")
        if door != TYPED and e.get("via"):
            out.append(f"{label(kind, name)}: only a typed door has `via` (use `partly_via`)")
        for tool_name in [*(e.get("via") or []), *(e.get("partly_via") or [])]:
            t = contract.TOOLS.get(tool_name)
            if t is None or not t.built or NORMAL not in t.profiles:
                out.append(f"{label(kind, name)}: {tool_name!r} is not a built tool on the normal profile")
            elif e.get("primitive") and e["primitive"] not in t.expands_to:
                out.append(f"{label(kind, name)}: tool {tool_name!r} does not run {e['primitive']!r}")
        if e.get("primitive") and not primitive_names(name, e["primitive"]):
            out.append(f"{label(kind, name)}: primitive {e['primitive']!r} is not this command's step")
    return sorted(set(out), key=out.index)


def check_disposition(reg: dict[str, Any]) -> list[str]:
    allowed = set((reg.get("vocabulary") or {}).get("lead_dispositions") or {})
    out = []
    for kind, e in entries(reg):
        name, d = str(e.get("name")), e.get("lead_disposition")
        if kind == "cli" and lead_reachable(name) and d is None:
            out.append(f"`aew {name}` is Lead-reachable: name its lead_disposition ({sorted(allowed)})")
        if d is None:
            continue
        if kind != "cli":
            out.append(f"tool `{name}`: a tool is a typed door itself; dispositions are for commands")
        elif d not in allowed:
            out.append(f"`aew {name}`: unknown lead_disposition {d!r}")
        elif (d == TYPED) != (e.get("door") == TYPED):
            out.append(f"`aew {name}`: lead_disposition typed and door typed go together (door {e.get('door')!r})")
    return out


def check_new_surface(reg: dict[str, Any]) -> list[str]:
    """The standing rule (operator, 2026-10-12): a surface added after the baseline ships with its full entry and, if
    the Lead uses it to change anything, a decided disposition that the code honours in the same change: `typed` is
    reached through a typed tool with a proved primitive and never through the shell (not in LEAD_REACHABLE);
    `engine-owned` and `forbidden-to-lead` are reachable through neither Lead door."""
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if kind != "cli" or baseline_key(kind, name) in BASELINE or not is_live(kind, name):
            continue
        d, users = e.get("lead_disposition"), set(e.get("users") or [])
        lead_change = lead_reachable(name) or ("lead" in users and mutates(e) != "no")
        if lead_change and d in (None, UNDECIDED):
            out.append(f"new `aew {name}`: the Lead uses it to change state, so its lead_disposition must be decided "
                       "(typed, engine-owned or forbidden-to-lead) in the change that adds it")
            continue
        if d == TYPED:
            out += [f"new `aew {name}` (typed): {why}" for why in proved_typed(name, e)]
            if e.get("door") != TYPED:
                out.append(f"new `aew {name}` (typed): its door must be typed")
            if lead_reachable(name):
                out.append(f"new `aew {name}` (typed): the Lead reaches it through its typed tool, not the shell; "
                           "leave it out of lead_broker.LEAD_REACHABLE")
        elif d in LEAVES_LEAD_DOORS:
            if lead_reachable(name):
                out.append(f"new `aew {name}` ({d}): it must not be in lead_broker.LEAD_REACHABLE")
            p = e.get("primitive")
            through = [t.name for t in contract.TOOLS.values() if t.built and p and p in t.expands_to]
            if through or e.get("via"):
                out.append(f"new `aew {name}` ({d}): it must not be reachable through a typed tool "
                           f"({sorted(set(through) | set(e.get('via') or []))})")
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
        if not is_live(kind, name):
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
            out.append(f"{label(kind, str(e.get('name')))}: refusals inventory {status.get('inventory')!r}, "
                       f"structured {status.get('structured')!r} (A2)")
    return out


def check_mutates_unknown(reg: dict[str, Any]) -> list[str]:
    return [f"{label(kind, str(e.get('name')))}: mutates unknown ({e.get('mutates_basis')})"
            for kind, e in entries(reg) if mutates(e) == "unknown"]


def check_undecided(reg: dict[str, Any]) -> list[str]:
    return [f"`aew {e['name']}`: lead_disposition undecided (A2's plan decides: typed, engine-owned or "
            "forbidden-to-lead, with its reason)" for kind, e in entries(reg)
            if kind == "cli" and e.get("lead_disposition") == UNDECIDED]


def check_disposition_applied(reg: dict[str, Any]) -> list[str]:
    return [f"`aew {e['name']}` is {e['lead_disposition']} but still in lead_broker.LEAD_REACHABLE (A4)"
            for kind, e in entries(reg)
            if kind == "cli" and e.get("lead_disposition") in LEAVES_LEAD_DOORS and lead_reachable(str(e["name"]))]


def check_lead_shell_lifecycle(reg: dict[str, Any]) -> list[str]:
    """The end state (designer, 2026-10-12): every Lead lifecycle need is covered by typed or engine-owned behaviour,
    and the Lead's shell lifecycle operations are 0. Today: every Lead-reachable command reached by the shell only."""
    return [f"`aew {e['name']}` is a Lead shell lifecycle operation (disposition {e.get('lead_disposition')})"
            for kind, e in entries(reg)
            if kind == "cli" and lead_reachable(str(e.get("name"))) and e.get("door") not in (None, TYPED)]


def check_unevidenced(reg: dict[str, Any]) -> list[str]:
    return [f"{label(kind, e['name'])} is homed {e['home']} but no vertical journey exercises it"
            for kind, e in entries(reg) if e.get("home") not in (DIAGNOSTIC, "internal") and not e.get("journeys")]


CHECK_FUNCTIONS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "registered": check_registered, "live": check_live, "fields": check_fields, "users": check_users,
    "home": check_home, "mutates": check_mutates, "door": check_door, "disposition": check_disposition,
    "new_surface": check_new_surface, "ideal_path": check_ideal_path, "codes": check_codes,
    "refusal_floor": check_refusal_floor, "owner": check_owner, "structured_refusals": check_structured_refusals,
    "mutates_unknown": check_mutates_unknown, "undecided": check_undecided,
    "disposition_applied": check_disposition_applied, "lead_shell_lifecycle": check_lead_shell_lifecycle,
    "unevidenced": check_unevidenced,
}


def report(check: str, findings: list[str]) -> None:
    """A report-only check's findings: printed whatever the run's warning filters (``-W error``, an ignore filter, the
    default, xdist), and written as JSON when ``AEW_SURFACE_MAP_REPORT`` names a directory (PR 215 review, finding 3).
    """
    directory = os.environ.get(REPORT_ENV)
    if directory:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"surface-map-{check}.json").write_text(json.dumps(
            {"schema": "aew/surface-map-report/v1", "check": check, "mode": CHECKS[check], "count": len(findings),
             "findings": findings}, indent=2) + "\n", encoding="utf-8")
    if findings:
        with warnings.catch_warnings():
            warnings.simplefilter("always", UserWarning)
            # A plain UserWarning: xdist rebuilds a warning's class on the controller, which cannot import a test
            # module.
            warnings.warn(UserWarning(f"{REPORT_PREFIX} `{check}` (report-only), {len(findings)} item(s):\n"
                                      + "\n".join(findings)), stacklevel=2)


# ---------------------------------------------------------------------------------------------- the tests


@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_surface_map_check(check):
    findings = CHECK_FUNCTIONS[check](load())
    if CHECKS[check] == ENFORCE:
        assert not findings, f"surface map, check `{check}`:\n" + "\n".join(findings)
    else:
        report(check, findings)


def test_the_pins_equal_the_document():
    """Every check is pinned enforce or report, and docs/implementation/surface-map.md's table says the same."""
    assert set(CHECKS) == set(CHECK_FUNCTIONS) and set(CHECKS.values()) <= {ENFORCE, REPORT}
    rows = re.findall(r"^\| `([a-z_]+)` \| (enforce|report) \|", DOC.read_text(encoding="utf-8"), re.MULTILINE)
    assert dict(rows) == CHECKS and len(rows) == len(CHECKS)


def test_the_baseline_only_shrinks():
    """FROZEN is the registry when the standing rule was adopted; nothing is ever added to it (its digest is pinned),
    and BASELINE is FROZEN minus what graduated."""
    digest = hashlib.sha256("\n".join(sorted(FROZEN)).encode()).hexdigest()
    assert digest == FROZEN_DIGEST, ("the grandfathered list changed: entries may only leave the baseline, through "
                                     "GRADUATED; a new surface must satisfy the `new_surface` check instead")
    assert GRADUATED <= FROZEN and BASELINE <= FROZEN


def test_the_registry_is_versioned_and_states_its_vocabulary():
    reg = load()
    assert reg["schema"] == "aew/surface-map/v1" and isinstance(reg["version"], int) and reg["version"] >= 1
    vocab = reg["vocabulary"]
    assert set(vocab["homes"]) == {"product", "operator-admin", "recovery", DIAGNOSTIC, "internal"}
    assert {"operator", "lead", "worker", "internal"} == set(vocab["users"])
    assert set(vocab["journeys"]) == {"V1", "V2", "V3", "V4"}
    assert set(vocab["mutates"]) == {"no", "yes", "with", "unknown"}
    assert set(vocab["doors"]) == {TYPED, "shell-only (pending A2/A4)"}
    assert set(vocab["lead_dispositions"]) == {TYPED, *LEAVES_LEAD_DOORS, UNDECIDED}


def test_the_walk_and_the_ideal_path_are_the_live_ones():
    """The guard sees what it guards: the switched commands, every Lead-reachable command, and the ideal path's
    existing commands resolve to live leaves."""
    commands = live_commands()
    assert {"history search", "message thread", "message unseen"} <= set(commands)
    assert {" ".join(sorted(p)) for p in lead_broker.LEAD_REACHABLE} <= {" ".join(sorted(c.split())) for c in commands}
    rows = ideal_path()
    assert resolve(shlex.split(rows["raise"]["input"])[1:]) == "lead mode raise"
    assert resolve(shlex.split(rows["open"]["input"])[1:]) == "opencode"
    assert worker_commands() == {"whoami", "check run", "submit"}
    # A tripwire: when slice C2 builds `aew preflight`, move it from `proposed` to `commands` in surface-map.yaml and
    # drop this line.
    assert resolve(["preflight"]) is None, "`aew preflight` exists now: move it from `proposed` to `commands`"


# Each enforced check fails, naming the item, on the drift it exists to catch.
def _drop(kind: str, name: str) -> Callable[[dict[str, Any]], None]:
    def edit(reg: dict[str, Any]) -> None:
        key = "commands" if kind == "cli" else "tools"
        reg[key] = [e for e in reg[key] if e["name"] != name]
    return edit


def _entry(reg: dict[str, Any], name: str, kind: str = "cli") -> dict[str, Any]:
    return by_name(reg, kind)[name]


def _new(reg: dict[str, Any], name: str, **fields: Any) -> None:
    """Pretend a baseline command was added after the rule: take it out of the baseline for this registry."""
    _entry(reg, name).update(fields)
    reg["_not_baseline"] = name


DRIFT: list[tuple[str, Callable[[dict[str, Any]], None], str]] = [
    ("registered", _drop("cli", "work move"), "`aew work move` exists but is not registered"),
    ("registered", _drop("tool", "ticket_start"), "tool `ticket_start` exists but is not registered"),
    ("live", lambda r: r["commands"].append({"name": "work teleport"}), "`aew work teleport` is registered but no"),
    ("live", lambda r: r["tools"].append({"name": "ticket_fly"}), "tool `ticket_fly` is registered but no longer"),
    ("fields", lambda r: _entry(r, "init").update(users=[]), "`aew init` names no users"),
    ("fields", lambda r: _entry(r, "init").update(journeys=["V9"]), "`aew init`: unknown journey 'V9'"),
    ("fields", lambda r: _entry(r, "init").update(home=["product", "recovery"]), "`aew init`: needs exactly one home"),
    ("fields", lambda r: _entry(r, "init").pop("home"), "`aew init`: needs exactly one home"),
    ("fields", lambda r: _entry(r, "init").update(mutates="maybe"), "`aew init`: `mutates` is \"no\", \"yes\""),
    ("users", lambda r: _entry(r, "lead acquire").update(users=["operator", "lead"]),
     "`aew lead acquire` is operator-only"),
    ("users", lambda r: _entry(r, "work create").update(users=["operator"]), "`aew work create` is the Lead's"),
    ("users", lambda r: _entry(r, "submit").update(users=["lead"]), "`aew submit`: `worker` must be named"),
    ("home", lambda r: _entry(r, "history audit").update(home=DIAGNOSTIC),
     "`aew history audit` is homed diagnostic but its mutates is"),
    ("home", lambda r: _entry(r, "init").update(home=DIAGNOSTIC), "`aew init` is homed diagnostic"),
    ("mutates", lambda r: _entry(r, "ticket_start", "tool").update(mutates="no"), "tool `ticket_start`: mutates"),
    ("mutates", lambda r: _entry(r, "plan accept").update(mutates="no"), "`aew plan accept` takes --expect-rev"),
    ("mutates", lambda r: _entry(r, "map select-architecture").update(mutates="no"),
     "`aew map select-architecture` takes --expect-map-rev"),
    ("mutates", lambda r: _entry(r, "harness stop").update(mutates="no"), "`aew harness stop` takes the Lead"),
    ("mutates", lambda r: _entry(r, "dashboard open").update(mutates="no"), "`aew dashboard open` is operator-only"),
    ("door", lambda r: _entry(r, "plan accept").pop("door"), "`aew plan accept` is Lead-reachable: name its door"),
    ("door", lambda r: _entry(r, "work create").update(via=["ticket_start"]),
     "`aew work create`: tool 'ticket_start' does not run 'work.create'"),
    ("door", lambda r: _entry(r, "work create").update(via=["cli"]), "'cli' is not a built tool on the normal"),
    # PR 215 review, finding 1: a typed door without its primitive, or with another command's.
    ("door", lambda r: _entry(r, "harness launch").update(door=TYPED, via=["ticket_start"]),
     "`aew harness launch`: a typed door names the primitive its tools run"),
    ("door", lambda r: _entry(r, "harness launch").update(door=TYPED, via=["ticket_start"],
                                                          primitive="dispatch.launch"),
     "`aew harness launch`: primitive 'dispatch.launch' is not this command's step"),
    ("disposition", lambda r: _entry(r, "plan accept").pop("lead_disposition"),
     "`aew plan accept` is Lead-reachable: name its lead_disposition"),
    ("disposition", lambda r: _entry(r, "plan accept").update(lead_disposition=TYPED),
     "`aew plan accept`: lead_disposition typed and door typed go together"),
    ("disposition", lambda r: _entry(r, "plan accept").update(lead_disposition="maybe"),
     "`aew plan accept`: unknown lead_disposition 'maybe'"),
    # The standing rule: a surface outside the baseline.
    ("new_surface", lambda r: _new(r, "plan accept"), "new `aew plan accept`: the Lead uses it to change state"),
    ("new_surface", lambda r: _new(r, "work create"),
     "new `aew work create` (typed): the Lead reaches it through its typed tool, not the shell"),
    ("new_surface", lambda r: _new(r, "work create", primitive="plan.propose"),
     "new `aew work create` (typed): primitive 'plan.propose' is not this command's step"),
    ("new_surface", lambda r: _new(r, "plan accept", lead_disposition="engine-owned"),
     "new `aew plan accept` (engine-owned): it must not be in lead_broker.LEAD_REACHABLE"),
    ("new_surface", lambda r: _new(r, "work assign", lead_disposition="forbidden-to-lead", door=None, via=None),
     "new `aew work assign` (forbidden-to-lead): it must not be reachable through a typed tool"),
    ("new_surface", lambda r: _new(r, "harness wait", mutates="yes"),
     "new `aew harness wait`: the Lead uses it to change state"),
    ("ideal_path", _drop("cli", "opencode"), "names `aew opencode`, which is not registered"),
    ("ideal_path", lambda r: r.update(proposed=[]), "is PROPOSED but not listed under `proposed`"),
    ("ideal_path", lambda r: r["proposed"].append({"name": "init", "ideal_path": []}),
     "proposed `aew init` exists now"),
    ("codes", lambda r: _entry(r, "init")["refusals"].append("SEAT_HELD"), "SEAT_HELD is not a code in aew.errors"),
    ("refusal_floor", lambda r: _entry(r, "plan accept").update(refusals=["USAGE"]),
     "`aew plan accept`: its arguments imply refusals ['PERMISSION_DENIED', 'STALE_AUTHORITY', 'STALE_REVISION']"),
    ("refusal_floor", lambda r: _entry(r, "map select-architecture")["refusals"].remove("STALE_REVISION"),
     "`aew map select-architecture`: its arguments imply refusals ['STALE_REVISION']"),
    ("refusal_floor", lambda r: _entry(r, "ticket_start", "tool").update(refusals=[]), "tool `ticket_start`: its"),
]


def _run(check: str, reg: dict[str, Any]) -> list[str]:
    global BASELINE
    saved = BASELINE
    if "_not_baseline" in reg:
        BASELINE = BASELINE - {baseline_key("cli", reg["_not_baseline"])}
    try:
        return CHECK_FUNCTIONS[check](reg)
    finally:
        BASELINE = saved


@pytest.mark.parametrize(("check", "edit", "named"), DRIFT, ids=[f"{c}-{i}" for i, (c, _, _) in enumerate(DRIFT)])
def test_an_enforced_check_names_the_drift(check, edit, named):
    reg = copy.deepcopy(load())
    assert not any(named in f for f in _run(check, reg))
    edit(reg)
    findings = _run(check, reg)
    assert any(named in f for f in findings), findings


def test_a_new_surface_that_honours_its_disposition_passes():
    """The rule's positive side: a new command the engine owns, absent from both Lead doors, passes; so does a new
    read the Lead uses."""
    reg = copy.deepcopy(load())
    _new(reg, "integrate custody", lead_disposition="engine-owned")
    assert _run("new_surface", reg) == []
    reg = copy.deepcopy(load())
    _new(reg, "harness wait")
    assert _run("new_surface", reg) == []


def test_a_report_check_sees_its_pending_field_and_clears_when_it_lands():
    """The report checks measure today's gap, and pass on a registry where A1, A2 and A4 have landed."""
    reg = copy.deepcopy(load())
    # A tripwire: when one of these is empty on main, its slice has landed: flip that check to enforce in CHECKS and
    # in surface-map.md's table.
    for check in ("owner", "structured_refusals", "undecided", "lead_shell_lifecycle"):
        assert CHECK_FUNCTIONS[check](reg), f"`{check}` reports nothing now: flip it to enforce (CHECKS and the doc)"
    reg["refusal_status"] = {"inventory": "complete", "structured": "yes"}
    for _, e in entries(reg):
        if "owner" in e:
            e["owner"] = "lead"
        if e.get("lead_disposition") == UNDECIDED:
            e["lead_disposition"] = "engine-owned"
        if e.get("door") not in (None, TYPED):
            e.pop("door")
            e.pop("partly_via", None)
        if e.get("mutates") == "unknown":
            e["mutates"] = "yes"
        if not e.get("journeys") and e.get("home") not in (DIAGNOSTIC, "internal"):
            e["journeys"] = ["V1"]
    for check in ("owner", "structured_refusals", "mutates_unknown", "undecided", "lead_shell_lifecycle",
                  "unevidenced"):
        assert CHECK_FUNCTIONS[check](reg) == [], check
    assert check_disposition_applied(reg)  # engine-owned, yet still Lead-reachable: A4 has not closed the door


def test_a_report_is_printed_under_any_warning_filter_and_written_as_json(tmp_path, monkeypatch):
    monkeypatch.setenv(REPORT_ENV, str(tmp_path))
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("error")  # what `-W error` sets: the report must still print, never raise
        report("undecided", ["x"])
        warnings.simplefilter("ignore")
        report("undecided", ["y"])
    assert [str(w.message).splitlines()[-1] for w in seen] == ["x", "y"]
    data = json.loads((tmp_path / "surface-map-undecided.json").read_text(encoding="utf-8"))
    assert data["findings"] == ["y"] and data["mode"] == "report"
