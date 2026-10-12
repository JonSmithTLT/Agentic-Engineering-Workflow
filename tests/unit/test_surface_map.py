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
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass
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
    "undecided": REPORT,  # A2's plan: every Lead-reachable command's disposition decided
    "disposition_applied": REPORT,  # A4: engine-owned and forbidden-to-lead commands have left LEAD_REACHABLE
    "lead_shell_lifecycle": REPORT,  # A4: Lead shell lifecycle operations = 0
    "unevidenced": REPORT,  # a product, admin or recovery home that no vertical journey exercises yet
    "probe": ENFORCE,  # a surface declared `mutates: "no"` leaves the sample project unchanged when run
    "probe_coverage": REPORT,  # the pinned PROBE_LIMITED surfaces: refused on the sample, or not run
    "probe_flags": REPORT,  # options of a `mutates: "no"` command that no probe passes (enforced for new ones)
    "shell_reachable_mutation": REPORT,  # grandfathered mutating commands nothing keeps from the Lead's shell
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
    """`no`, `yes` or `with` (only with the flags it names); anything else is `invalid`."""
    m = e.get("mutates")
    if isinstance(m, dict):
        return "with" if set(m) == {"with"} and m["with"] and all(str(f).startswith("--") for f in m["with"]) \
            else "invalid"
    return m if m in ("no", "yes") else "invalid"


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
            out.append(f"{name}: `mutates` is \"no\", \"yes\" (quoted: YAML reads a bare yes as true) or "
                       f"{{with: [--flag, ...]}}, not {e.get('mutates')!r}")
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
    out = [f"{label(kind, str(e.get('name')))} is homed diagnostic but its mutates is {e.get('mutates')!r}: "
           "re-home it, or split the mutating form into its own command"
           for kind, e in entries(reg) if e.get("home") == DIAGNOSTIC and mutates(e) != "no"]
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if e.get("home") == DIAGNOSTIC and e.get("journeys"):
            out.append(f"{label(kind, name)} is homed diagnostic, yet journeys {e['journeys']} use it: a supported "
                       "workflow needs it, so it is not diagnostic (PR 215 second review, finding 6)")
        if e.get("home") == "internal" and not e.get("launcher"):
            out.append(f"{label(kind, name)} is homed internal: name its `launcher` (what starts it)")
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if e.get("home") != DIAGNOSTIC or baseline_key(kind, name) in BASELINE:
            continue
        why = str(e.get("diagnostic_justification") or "")
        if not (re.search(r"\b(observes|repairs)\b", why) and "normal workflow" in why):
            out.append(f"new {label(kind, name)} is homed diagnostic: give `diagnostic_justification`, one line saying "
                       "what implementation state it observes or repairs, for whom, and why no supported normal "
                       "workflow needs it")
    return out


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
        credential = dests(name) & {"token", "invocation_token"}
        if credential and m not in ("yes", "with") and not e.get("mutates_exempt"):
            out.append(f"`aew {name}` takes a credential ({sorted(credential)[0]}): its mutates must be yes or with, "
                       "or give `mutates_exempt` with the reason")
        if operator_only(name) and m not in ("yes", "with") and not e.get("mutates_exempt"):
            out.append(f"`aew {name}` is operator-only: its mutates must be yes or with, or give `mutates_exempt` "
                       "with the reason")
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
    the Lead can use it to change anything, a decided disposition that the code honours in the same change: `typed` is
    reached through a typed tool with a proved primitive and never through the shell (not in LEAD_REACHABLE);
    `engine-owned` and `forbidden-to-lead` are reachable through neither Lead door. Whether the Lead can reach it is
    decided by the mechanism (`lead_kept_out`), never by the `users` label."""
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if kind != "cli" or baseline_key(kind, name) in BASELINE or not is_live(kind, name):
            continue
        d = e.get("lead_disposition")
        if lead_reachable(name) and d in (None, UNDECIDED):
            out.append(f"new `aew {name}`: the Lead uses it to change state, so its lead_disposition must be decided "
                       "(typed, engine-owned or forbidden-to-lead) in the change that adds it")
            continue
        if mutates(e) != "no" and not lead_reachable(name):
            how = lead_kept_out(name, e)
            if how is None:
                out.append(f"new `aew {name}` mutates and takes no credential, so the Lead's shell can run it: "
                           "take the Lead credential, join lead_broker.OPERATOR_ONLY, home it internal with its "
                           "`launcher`, or declare its lead_disposition with `lead_kept_out_by` (the mechanism that "
                           "keeps the Lead out)")
                continue
            if e.get("lead_kept_out_by") and how == e["lead_kept_out_by"] and d in (None, UNDECIDED):
                out.append(f"new `aew {name}`: `lead_kept_out_by` comes with a decided lead_disposition")
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
            if p is None:
                out.append(f"new `aew {name}` ({d}): name its `primitive`, so that no typed tool running it can be "
                           "checked (or `primitive: none` with `primitive_reason`)")
            elif p == "none":
                if not e.get("primitive_reason"):
                    out.append(f"new `aew {name}` ({d}): `primitive: none` needs its `primitive_reason`")
            elif not primitive_names(name, p):
                out.append(f"new `aew {name}` ({d}): primitive {p!r} is not this command's step")
            through = [t.name for t in contract.TOOLS.values() if p not in (None, "none") and p in t.expands_to]
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


# ---------------------------------------------------------------------------------------------- the behavioural probe
# (designer, 2026-10-12): a label cannot make a mutating command "diagnostic". Every surface declared `mutates: "no"`
# runs, in process, against a synthetic sample project with every argument list its entry's `probe` gives, and must
# leave everything the sample holds as it found it: every file under the sample's directory (the project and its
# `.aew/`, which covers the control state and its revision, transitions, evidence and the outbox; the workspaces root
# beside it; `.git/` with its refs, HEAD, config, hooks and worktrees; ignored files) except the stat and read caches
# below. Each probe must run the command's real path (exit 0); one refused or not run at all is accepted only from the
# pinned, shrink-only PROBE_LIMITED list (PR 215 second review, finding 1).

# Rewritten by reads, never a mutation: the derived history index and recall's full-text index (both rebuilt from the
# manifest), git's object store (unreferenced objects are not state; refs are) and git's index stat caches.
UNHASHED = re.compile(r"sample/\.aew/local/history\.sqlite(-wal|-shm|-journal)?"
                      r"|sample/\.aew/local/recall/history-fts\.sqlite(-wal|-shm|-journal)?"
                      r"|sample/\.git/objects/.*|sample/\.git/index|sample/\.git/worktrees/[^/]+/index")
CREDENTIAL_ENV = ("AEW_LEAD_TOKEN", "AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY", "AEW_INVOCATION_TOKEN",
                  "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY")
NO_WINDOW: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
SAMPLE_BASE: list[Path] = []  # set by the module's fixture (pytest's temporary directory)
# Options that change only how a result is printed (or are expanded before parsing): no probe needs to pass them.
PRINT_ONLY = frozenset({"help", "json", "fields"})

# The surfaces whose probe may be refused on the sample, or not run at all (`probe_exempt`), each with its reason in
# the registry. Nothing is ever added: the list is pinned by its digest, and an entry leaves through PROBE_GRADUATED
# once its probe runs its real path.
PROBE_LIMITED: frozenset[str] = frozenset({
    "cli:harness wait", "cli:history links", "cli:history show", "cli:operator ping", "tool:harness_wait",
})
PROBE_LIMITED_DIGEST = "24dd12a6eb5efa52eac76dd27b516ae2985a95b12096532eeee83902f82d29b7"
PROBE_GRADUATED: frozenset[str] = frozenset()


@dataclass
class Sample:
    base: Path
    root: Path
    token: str
    ticket: str
    invocation: str
    invocation_token: str


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True, **NO_WINDOW).stdout


def run_cli(root: Path, argv: list[str]) -> tuple[int, str, str]:
    """``aew -C root *argv`` in this process, with no credential in the environment and its output captured."""
    from aew.cli.main import main

    saved = {k: os.environ.pop(k) for k in CREDENTIAL_ENV if k in os.environ}
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(["-C", str(root), *argv])
            except SystemExit as exc:  # argparse
                code = exc.code if isinstance(exc.code, int) else 2
    finally:
        os.environ.update(saved)
    return code, out.getvalue(), err.getvalue()


def build_sample(base: Path) -> Sample:
    """A fresh project with messaging and recall search switched on (so their commands exist), a Lead, and one Ticket
    with an accepted plan, assigned without a launch: its implementer invocation INV-0001, its workspace and pack."""
    from aew import util
    from aew.engine.api import Engine

    root = base / "sample"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.name", "AEW Probe")
    _git(root, "config", "user.email", "aew-probe@invalid")
    _git(root, "config", "core.autocrlf", "false")
    (root / "README.md").write_text("# sample\n", encoding="utf-8", newline="\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    assert run_cli(root, ["init"])[0] == 0
    code, out, err = run_cli(root, ["--print-credential", "lead", "acquire", "--expect-rev", "0", "--session-label",
                                    "probe"])
    assert code == 0, err
    token = json.loads(out)["token"]

    def rev() -> str:
        return str(json.loads(run_cli(root, ["lead", "show"])[1])["revision"])

    policy = root / ".aew" / "policy" / "execution.yaml"
    data = util.load_yaml(policy.read_text(encoding="utf-8")) or {}
    data["coordination"] = {"messaging": "enabled"}
    data["recall"] = {"raw_history_search": "explicit"}
    policy.write_text(util.dump_yaml(data), encoding="utf-8", newline="\n")
    # The operator's adoption, with the terminal channel substituted in process (as tests/conftest.py's as_operator).
    Engine.discover(root).manifest_adopt(token=token, expect_rev=int(rev()), reason="the probe's sample",
                                         authorization={"authorized_by": "operator-tty"})
    (base / "plan.md").write_text("Change the README.\n", encoding="utf-8")
    invocation_token = ""
    for argv in (["work", "create", "ticket", "--title", "probe", "--class", "2", "--scope", "src/**"],
                 ["plan", "propose", "T-0001", "--file", str(base / "plan.md"), "--assurance", "none"],
                 ["plan", "accept", "T-0001", "--revision", "1"],
                 ["work", "assign", "T-0001"]):
        code, out, err = run_cli(root, ["--print-credential", *argv, "--token", token, "--expect-rev", rev()])
        assert code == 0, (argv, err)
        invocation_token = json.loads(out).get("invocation_token") or invocation_token
    assert invocation_token, "work assign issued no invocation credential"
    s = Sample(base, root, token, "T-0001", "INV-0001", invocation_token)
    # Settle it: the first read after a commit deletes the spent redo records of the commits before it
    # (ControlStore._recover); that housekeeping belongs to the setup's commits, not to the first surface probed.
    for _ in range(3):
        before = snapshot(s)
        assert run_cli(root, ["status"])[0] == 0
        if snapshot(s) == before:
            return s
    raise AssertionError("the sample does not settle: a read keeps changing it")


@cache
def sample() -> Sample:
    assert SAMPLE_BASE, "the probe's sample needs the module fixture"
    return build_sample(SAMPLE_BASE[0])


def snapshot(s: Sample) -> dict[str, str]:
    """Every file the sample holds, by its path under the sample's directory (PR 215 second review, finding 4)."""
    out = {}
    for p in sorted(s.base.rglob("*")):
        rel = p.relative_to(s.base).as_posix()
        if p.is_file() and not UNHASHED.fullmatch(rel):
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def probes(e: dict[str, Any]) -> list[list[str]]:
    """An entry's probe argument lists: `probe` is one list, or a list of lists."""
    p = e.get("probe") or []
    return [[str(a) for a in argv] for argv in p] if p and isinstance(p[0], list) else ([[str(a) for a in p]] if p
                                                                                        else [])


def fill(argv: list[str], s: Sample) -> list[str]:
    values = {"{token}": s.token, "{ticket}": s.ticket, "{invocation}": s.invocation,
              "{invocation_token}": s.invocation_token}
    out = []
    for a in argv:
        for k, v in values.items():
            a = a.replace(k, v)
        out.append(a)
    return out


def probe_one(argv: list[str], s: Sample) -> tuple[int, str, list[str]]:
    """Run one probe: its exit code, its refusal code (if any), and what it changed."""
    before = snapshot(s)
    code, _, err = run_cli(s.root, fill(argv, s))
    after = snapshot(s)
    refusal = ""
    if code:
        try:
            refusal = json.loads(err)["error"]["code"]
        except (ValueError, KeyError, TypeError):
            refusal = f"exit {code}"
    return code, refusal, sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def probe_target(kind: str, name: str, argv: list[str]) -> bool:
    """Whether a probe's arguments run the entry itself (never another command)."""
    if kind == "tool":
        return argv[:3] == ["lead", "tool", name]
    return resolve(argv) == name


def uncovered_flags(name: str, argvs: list[list[str]]) -> list[str]:
    """The options of a command that no probe passes (PR 215 second review, finding 3): a mutation behind one of them
    is out of the probe's sight."""
    passed = {a.split("=", 1)[0] for argv in argvs for a in argv if a.startswith("-")}
    return [a.option_strings[-1] for a in live_commands()[name]._actions
            if a.option_strings and a.dest not in PRINT_ONLY and not passed & set(a.option_strings)]


def check_probe(reg: dict[str, Any]) -> list[str]:
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if mutates(e) != "no" or not is_live(kind, name):
            continue
        key, limited = baseline_key(kind, name), baseline_key(kind, name) in PROBE_LIMITED - PROBE_GRADUATED
        if e.get("probe_exempt"):
            if not limited:
                out.append(f"{label(kind, name)} gives `probe_exempt`, which only the pinned PROBE_LIMITED list "
                           "allows: give it a probe that runs its real path on the sample (extend the sample if "
                           "need be)")
            continue
        argvs = probes(e)
        if not argvs:
            out.append(f"{label(kind, name)} is declared mutates \"no\": give its `probe` (argument lists that run it "
                       "on the sample project)")
            continue
        wrong = [argv for argv in argvs if not probe_target(kind, name, argv)]
        if wrong:
            out.append(f"{label(kind, name)}: its probe {wrong[0]} does not run it")
            continue
        refused = []
        for argv in argvs:
            code, refusal, changed = probe_one(argv, sample())
            if changed:
                out.append(f"{label(kind, name)} is declared mutates \"no\", but `{' '.join(argv)}` changed {changed}")
            if code:
                refused.append(f"`{' '.join(argv)}` ({refusal})")
        if refused and not (limited and e.get("probe_refused")):
            out.append(f"{label(kind, name)}: its probe was refused before doing its work ({', '.join(refused)}): a "
                       "probe must run the command's real path (exit 0); give it arguments, or a sample state, it runs "
                       "with")
        elif limited and not refused:
            out.append(f"{label(kind, name)} now runs its real path on the sample: move {key!r} from PROBE_LIMITED to "
                       "PROBE_GRADUATED and drop its `probe_refused`")
        if kind == "cli" and key not in BASELINE:
            missing = uncovered_flags(name, argvs)
            if missing:
                out.append(f"new `aew {name}`: no probe passes {missing}; probe it with each option it takes")
    return out


def check_probe_coverage(reg: dict[str, Any]) -> list[str]:
    """What the probe does not show: the PROBE_LIMITED surfaces (refused on the sample, or not run), with reasons."""
    return [f"{label(kind, str(e.get('name')))}: "
            + (f"not run ({e['probe_exempt']})" if e.get("probe_exempt") else f"refused on the sample "
               f"({e.get('probe_refused')}): its real path is not probed")
            for kind, e in entries(reg) if baseline_key(kind, str(e.get("name"))) in PROBE_LIMITED - PROBE_GRADUATED]


def check_probe_flags(reg: dict[str, Any]) -> list[str]:
    """The options of a `mutates: "no"` command that no probe passes (enforced for new commands by `probe`)."""
    out = []
    for kind, e in entries(reg):
        name = str(e.get("name"))
        if kind == "cli" and mutates(e) == "no" and is_live(kind, name) and not e.get("probe_exempt"):
            missing = uncovered_flags(name, probes(e))
            if missing:
                out.append(f"`aew {name}`: no probe passes {missing}")
    return out


def lead_kept_out(name: str, e: dict[str, Any]) -> str | None:
    """How the code keeps the Lead's shell from running a mutating command by itself, or ``None``. The Lead broker
    gates only commands that take the Lead credential (`lead_broker.refuses_locally`, `routes`), so a command without
    one runs in the Lead's shell whatever its `users` say (PR 215 second review, finding 2): the mechanism decides,
    never the label. Until A4 takes `aew` off the Lead's PATH, closing the shell door is what honours the rest."""
    ds = dests(name)
    if "token" in ds:
        return "it takes the Lead credential: lead_broker classifies it (LEAD_REACHABLE or OPERATOR_ONLY)"
    if operator_only(name):
        return "lead_broker.OPERATOR_ONLY refuses it in a Lead session"
    if "invocation_token" in ds:
        return "it acts only with an invocation credential, which the Lead does not hold"
    if e.get("home") == "internal" and e.get("launcher"):
        return f"internal: {e['launcher']}"
    if e.get("lead_kept_out_by"):
        return str(e["lead_kept_out_by"])
    return None


def check_shell_reachable_mutation(reg: dict[str, Any]) -> list[str]:
    """The grandfathered commands that mutate, take no credential and are kept from the Lead by no stated mechanism:
    the Lead's shell can run them today (for a new command, `new_surface` refuses this)."""
    return [f"`aew {e['name']}` mutates ({e.get('mutates')}) and nothing keeps the Lead's shell from running it"
            for kind, e in entries(reg)
            if kind == "cli" and is_live(kind, str(e.get("name"))) and mutates(e) != "no"
            and not lead_reachable(str(e["name"])) and lead_kept_out(str(e["name"]), e) is None]


CHECK_FUNCTIONS: dict[str, Callable[[dict[str, Any]], list[str]]] = {
    "registered": check_registered, "live": check_live, "fields": check_fields, "users": check_users,
    "home": check_home, "mutates": check_mutates, "door": check_door, "disposition": check_disposition,
    "new_surface": check_new_surface, "ideal_path": check_ideal_path, "codes": check_codes,
    "refusal_floor": check_refusal_floor, "owner": check_owner, "structured_refusals": check_structured_refusals,
    "undecided": check_undecided,
    "disposition_applied": check_disposition_applied, "lead_shell_lifecycle": check_lead_shell_lifecycle,
    "unevidenced": check_unevidenced, "probe": check_probe, "probe_coverage": check_probe_coverage,
    "probe_flags": check_probe_flags, "shell_reachable_mutation": check_shell_reachable_mutation,
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


@pytest.fixture(scope="module", autouse=True)
def _sample_base(tmp_path_factory):
    SAMPLE_BASE[:] = [tmp_path_factory.mktemp("g1-probe")]
    yield
    sample.cache_clear()


NOT_MUTATING = [(kind, str(e["name"])) for kind, e in entries(load()) if mutates(e) == "no"]


@pytest.mark.parametrize(("kind", "name"), NOT_MUTATING, ids=[f"{k}:{n}" for k, n in NOT_MUTATING])
def test_the_probe(kind, name):
    """The `probe` check, one surface per test (so xdist spreads it and a failure names its own node): run on the
    shared sample, a surface declared `mutates: "no"` changes nothing."""
    assert CHECKS["probe"] == ENFORCE
    reg = load()
    findings = check_probe({"commands": [], "tools": [], ("commands" if kind == "cli" else "tools"):
                            [by_name(reg, kind)[name]]})
    assert not findings, "surface map, check `probe`:\n" + "\n".join(findings)


@pytest.mark.parametrize("check", sorted(set(CHECKS) - {"probe"}))
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
    digest = hashlib.sha256("\n".join(sorted(PROBE_LIMITED)).encode()).hexdigest()
    assert digest == PROBE_LIMITED_DIGEST, ("PROBE_LIMITED changed: a surface may only leave it, through "
                                            "PROBE_GRADUATED; a new probe must run its command's real path")
    assert PROBE_GRADUATED <= PROBE_LIMITED


def test_the_registry_is_versioned_and_states_its_vocabulary():
    reg = load()
    assert reg["schema"] == "aew/surface-map/v1" and isinstance(reg["version"], int) and reg["version"] >= 1
    vocab = reg["vocabulary"]
    assert set(vocab["homes"]) == {"product", "operator-admin", "recovery", DIAGNOSTIC, "internal"}
    assert {"operator", "lead", "worker", "internal"} == set(vocab["users"])
    assert set(vocab["journeys"]) == {"V1", "V2", "V3", "V4"}
    assert set(vocab["mutates"]) == {"no", "yes", "with"}
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
    ("home", lambda r: _entry(r, "work list").update(journeys=["V1"]),
     "`aew work list` is homed diagnostic, yet journeys ['V1'] use it"),
    ("home", lambda r: _entry(r, "lead mcp").pop("launcher"), "`aew lead mcp` is homed internal: name its"),
    ("home", lambda r: _new(r, "work list"), "new `aew work list` is homed diagnostic: give `diagnostic_just"),
    ("home", lambda r: _new(r, "work list", diagnostic_justification="handy"), "new `aew work list` is homed diag"),
    ("mutates", lambda r: _entry(r, "ticket_start", "tool").update(mutates="no"), "tool `ticket_start`: mutates"),
    ("mutates", lambda r: _entry(r, "plan accept").update(mutates="no"), "`aew plan accept` takes --expect-rev"),
    ("mutates", lambda r: _entry(r, "map select-architecture").update(mutates="no"),
     "`aew map select-architecture` takes --expect-map-rev"),
    ("mutates", lambda r: _entry(r, "harness stop").update(mutates="no"), "`aew harness stop` takes a credential"),
    ("mutates", lambda r: _entry(r, "whoami").pop("mutates_exempt"), "`aew whoami` takes a credential"),
    ("mutates", lambda r: _entry(r, "operator ping").pop("mutates_exempt"), "`aew operator ping` is operator-only"),
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
    # A home never exempts a Lead-reachable command (designer question, 2026-10-12): homed diagnostic, it still needs a
    # disposition, and a new one a decided disposition.
    ("disposition", lambda r: _entry(r, "message unseen").update(home=DIAGNOSTIC, mutates="no",
                                                                 lead_disposition=None),
     "`aew message unseen` is Lead-reachable: name its lead_disposition"),
    ("new_surface", lambda r: _new(r, "message unseen", home=DIAGNOSTIC, mutates="no"),
     "new `aew message unseen`: the Lead uses it to change state"),
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
    # PR 215 second review, finding 2: a new mutating command with no credential, whatever its `users` say.
    ("new_surface", lambda r: _new(r, "context pack", home="recovery", mutates="yes", users=["operator"]),
     "new `aew context pack` mutates and takes no credential, so the Lead's shell can run it"),
    ("new_surface", lambda r: _new(r, "context pack", mutates="yes", lead_kept_out_by="refuses in a Lead session"),
     "new `aew context pack`: `lead_kept_out_by` comes with a decided lead_disposition"),
    ("new_surface", lambda r: _new(r, "integrate custody", lead_disposition="engine-owned"),
     "new `aew integrate custody` (engine-owned): name its `primitive`"),
    ("new_surface", lambda r: _new(r, "integrate custody", lead_disposition="engine-owned", primitive="none"),
     "`primitive: none` needs its `primitive_reason`"),
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


def _mutate_on_read(how: str) -> Callable[..., Any]:
    from aew.engine.api import Engine

    original = Engine.work_list

    def work_list(self: Any, *args: Any, **kwargs: Any) -> Any:
        aew = Path(self.aew_root)
        if how == "file":  # a record written beside the control state
            (aew / "state" / "probe-drift.json").write_text("{}", encoding="utf-8")
        elif how == "ref":  # a ref moved
            _git(aew.parent, "update-ref", "refs/heads/probe-drift", "HEAD")
        elif how == "workspaces":  # outside .aew/: the workspaces root beside the project (second review, finding 4)
            (aew.parent.parent / ".aew-workspaces" / "drift.txt").write_text("x", encoding="utf-8")
        elif how == "git-config":
            _git(aew.parent, "config", "aew.drift", "1")
        elif how == "flag" and kwargs.get("state_filter"):  # only behind an option (second review, finding 3)
            (aew / "state" / "probe-drift.json").write_text("{}", encoding="utf-8")
        return original(self, *args, **kwargs)
    return work_list


@pytest.mark.parametrize(("how", "changed"), [
    ("file", "sample/.aew/state/probe-drift.json"), ("ref", "sample/.git/refs/heads/probe-drift"),
    ("workspaces", ".aew-workspaces/drift.txt"), ("git-config", "sample/.git/config"),
    ("flag", "sample/.aew/state/probe-drift.json"),
])
def test_the_probe_catches_a_mutating_command_labelled_diagnostic(tmp_path, monkeypatch, how, changed):
    """The designer's question (2026-10-12): can a command that changes state pass as diagnostic by its label? No: a
    command declared `mutates: "no"`, homed diagnostic and taking no credential is run, and what it changed is named.
    Here `aew work list`'s implementation is made to write a record, move a ref, write beside the project, change the
    git config, or write only when given `--state` (which one of its probes passes)."""
    import sys as _sys

    from aew.engine.api import Engine

    module = _sys.modules[__name__]
    own = build_sample(tmp_path)
    monkeypatch.setattr(module, "sample", lambda: own)
    reg = {"commands": [copy.deepcopy(_entry(load(), "work list"))], "tools": []}
    assert reg["commands"][0]["home"] == DIAGNOSTIC and "token" not in dests("work list")
    assert check_probe(reg) == []
    monkeypatch.setattr(Engine, "work_list", _mutate_on_read(how))
    findings = check_probe(reg)
    assert len(findings) == 1 and "`aew work list` is declared mutates" in findings[0] and changed in findings[0], \
        findings


def _probe_findings(edit: Callable[[dict[str, Any]], None], name: str, kind: str = "cli",
                    not_baseline: bool = False) -> list[str]:
    reg = copy.deepcopy(load())
    if not_baseline:
        reg["_not_baseline"] = name
    edit(reg)
    one = {"commands": [], "tools": [], ("commands" if kind == "cli" else "tools"): [by_name(reg, kind)[name]]}
    if not_baseline:
        one["_not_baseline"] = name
    return _run("probe", one)


@pytest.mark.parametrize(("edit", "name", "not_baseline", "named"), [
    (lambda r: _entry(r, "work list").pop("probe"), "work list", False,
     "`aew work list` is declared mutates \"no\": give"),
    (lambda r: _entry(r, "work list").update(probe=["work", "show", "{ticket}"]), "work list", False,
     "`aew work list`: its probe ['work', 'show', '{ticket}'] does not run it"),
    # PR 215 second review, finding 1: a refused probe, or a free-text exemption, outside the pinned list.
    (lambda r: _entry(r, "invoke show").update(probe=["invoke", "show", "INV-9999"]), "invoke show", False,
     "`aew invoke show`: its probe was refused before doing its work (`invoke show INV-9999` (NOT_FOUND))"),
    (lambda r: _entry(r, "invoke show").update(probe_exempt="the sample has no invocation"), "invoke show", False,
     "`aew invoke show` gives `probe_exempt`, which only the pinned PROBE_LIMITED list allows"),
    (lambda r: _entry(r, "context pack").update(home=DIAGNOSTIC, mutates="no", probe=["context", "pack", "INV-9999"]),
     "context pack", True, "`aew context pack`: its probe was refused before doing its work"),
    # finding 3, for a new command: every option it takes is probed.
    (lambda r: _entry(r, "work list").update(probe=["work", "list"]), "work list", True,
     "new `aew work list`: no probe passes ['--state']"),
])
def test_the_probe_names_what_it_cannot_prove(edit, name, not_baseline, named):
    findings = _probe_findings(edit, name, not_baseline=not_baseline)
    assert any(named in f for f in findings), findings


PROVED = [str(e["name"]) for _, e in entries(load()) if e.get("mutates_proof")]


@pytest.mark.parametrize("name", PROVED)
def test_a_declared_mutation_is_shown_on_the_sample(name):
    """A surface whose mutation the sample would not show by itself (a no-op when its output is current) is proved
    `"yes"` by its `mutates_proof`: remove the file it maintains, run it, and it writes that file again (`context pack`,
    whose own help says it regenerates a pack after `local/` was deleted). The sample ends as it began."""
    proof = _entry(load(), name)["mutates_proof"]
    s = sample()
    target = s.root / fill([proof["remove"]], s)[0]
    assert target.is_file(), f"{target} is not on the sample: the proof names nothing to remove"
    start = snapshot(s)
    target.unlink()
    removed = snapshot(s)
    code, _, changed = probe_one([str(a) for a in proof["probe"]], s)
    assert code == 0 and "sample/" + fill([proof["remove"]], s)[0] in changed, (code, changed)
    assert snapshot(s) == start and removed != start


def test_a_new_surface_that_honours_its_disposition_passes():
    """The rule's positive side: a new command the engine owns, absent from both Lead doors, passes; so does a new
    read the Lead uses."""
    reg = copy.deepcopy(load())
    _new(reg, "integrate custody", lead_disposition="engine-owned", primitive="none",
         primitive_reason="the custody worker runs the custodian's own steps, not a typed-surface primitive")
    assert _run("new_surface", reg) == []
    reg = copy.deepcopy(load())
    _new(reg, "context pack", mutates="yes", lead_disposition="engine-owned", primitive="none",
         primitive_reason="a pack is rebuilt from durable state", lead_kept_out_by="refuses in a Lead session")
    assert _run("new_surface", reg) == []
    reg = copy.deepcopy(load())
    _new(reg, "harness wait")
    assert _run("new_surface", reg) == []
    reg = copy.deepcopy(load())
    _new(reg, "work list", diagnostic_justification="observes the work units for the operator; no supported normal "
                                                    "workflow needs it")
    assert _run("home", reg) == []


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
        if not e.get("journeys") and e.get("home") not in (DIAGNOSTIC, "internal"):
            e["journeys"] = ["V1"]
    for check in ("owner", "structured_refusals", "undecided", "lead_shell_lifecycle",
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
