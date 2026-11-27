"""What the Lead is told on every request is true (E367), as ``test_pack_truth`` holds a worker's text.

The audit of 2026-11-25 found four false lines in the Lead's system text and tool list that every existing test passed:
those check names and parseable commands, not claims. Each guard here reads one kind of claim the Lead's text makes and
holds it against the fact's owner, and each is planted with the line the audit found, which it must catch:
- a universal claim about the options a command takes holds for every command a Lead may run (the parser and
  ``lead_broker.LEAD_REACHABLE``; F1: "A shell mutation still needs `--expect-rev`", which `aew harness interrupt`
  refuses);
- a command the text names is one the parser has, an operator-only one is named only as refused here, and the seat's
  refused commands are the broker's own list (``lead_broker.CREDENTIAL_EMITTING``; F3: "handoff" was refused, while
  `aew lead handoff cancel` is the Lead's);
- every pointer resolves: the text points at no part of the guide, which it carries, a fact it leaves to the guide's
  core is there and is said once, and a guide section it names exists (F2 and #593's m5: "as the guide says" and "as
  the guide's first step shows" pointed at text the Lead was not given);
- no line overrides another (U1: "whatever the line above on a timed-out wait says");
- no value the tool list offers is one its runner always refuses (F4: `message_send`'s `turn-end` before MS5b);
- a typed `status` or `resume` holds no large value twice, and costs no more than the shell's `aew status` (the audit's
  R1 to R3: the hints twice, and 7,231 B against 3,520 B).

The matrix is every rendered variant of the Lead's text: messaging off and on, a Lead that waits and one AEW wakes,
contained and not, with the guide's core appended and without it.

Limits (M1): only claims of these forms are read. A claim worded otherwise, and the truth of prose such as the wake
guide's advice, are the periodic audit's (the audit of 2026-11-25, "Keeping it right over time"). The values a runner
always refuses are found for the tools the runners take (``run.RUNNERS``); a stage's are refused by its plan, which
this does not call. The result guard reads one project, a new one with its Lead seated, so a value a busier project
would repeat is not seen.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
from typing import Any

import pytest

from aew import errors
from aew.cli.main import build_parser
from aew.engine import guide
from aew.engine.api import Engine
from aew.harness import contract as K
from aew.harness import lead_broker
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import contract, lead_text, mcp, presentation, readable, run
from aew.surface.context import NORMAL, SurfaceContext

LABEL = {"filesystem": "os_readonly_roots",
         "network": {"mode": "proxy_only", "provider_relays": {"openai": "https://example.invalid/v1"},
                     "egress_policy": "any_public"}}
ON = frozenset({contract.MESSAGING})
VARIANTS = list(itertools.product((frozenset(), ON), (False, True), (False, True), (False, True)))
IDS = [f"{'on' if s else 'off'}-{'woken' if w else 'waits'}-{'contained' if c else 'host'}-"
       f"{'guide' if g else 'no-guide'}" for s, w, c, g in VARIANTS]


def rendered(switches: frozenset[str], push: bool, contained: bool, with_guide: bool) -> tuple[str, str]:
    """The Lead's whole system text in one variant, and the guide's core it carries ("" without one)."""
    core = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches) if with_guide else ""
    config = projection.lead_config(core, contained=LABEL if contained else None, push_wake=push, switches=switches)
    return config["agents"][projection.LEAD_AGENT]["system"], core


def own_text(system: str, core: str) -> str:
    """The system text's own lines: without the guide's core it carries."""
    return system.removesuffix(f"\n\n{core}") if core else system


# --------------------------------------------------------------------------------------------- the parser's commands

def commands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], set[str]]:
    """Every command path of ``parser``, with the options it takes."""
    out = {path: {o for action in parser._actions for o in action.option_strings}}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                out.update(commands(sub, (*path, name)))
    return out


COMMANDS = commands(build_parser())
BRANCHES = {path[:n] for path in COMMANDS for n in range(len(path))}  # a path that only leads to its subcommands
REACHABLE = {path: options for path, options in COMMANDS.items() if frozenset(path) in lead_broker.LEAD_REACHABLE}
OPERATOR_ONLY = {frozenset(path) for path in lead_broker.OPERATOR_ONLY}

# "A shell mutation still needs `--expect-rev`": a claim about every command of a kind, not one that takes the option.
UNIVERSAL = re.compile(r"\b(?:a|any|every) (?:shell )?(?:mutation|change|command) (?:still )?needs? `(--[a-z][a-z-]*)",
                       re.IGNORECASE)
NAMED = re.compile(r"`aew ([a-z][a-z -]*?)(?: [<-][^`]*)?`")


def false_option_claims(text: str) -> list[str]:
    """Each universal claim that a command needs an option, with the Lead-reachable commands that do not take it."""
    return [f"{option}: not taken by `aew {' '.join(path)}`" for option in UNIVERSAL.findall(text)
            for path, options in sorted(REACHABLE.items()) if option not in options]


def command_problems(text: str) -> list[str]:
    """The commands ``text`` names that the parser does not have, and operator-only ones it does not say are refused."""
    problems = []
    for line in text.splitlines():
        for named in NAMED.findall(line):
            words = tuple(named.split())
            # The command is the longest path the parser has, and it takes no subcommand: the words after it are its
            # arguments (`aew guide core`).
            path = max((words[:n] for n in range(len(words) + 1) if words[:n] in COMMANDS), key=len)
            if not path or path in BRANCHES:
                problems.append(f"`aew {named}` is no command")
            elif frozenset(path) in OPERATOR_ONLY and "refused here" not in line:
                problems.append(f"`aew {named}` is the operator's, and the line does not say it is refused here")
            elif "refused here" in line and frozenset(path) in lead_broker.LEAD_REACHABLE:
                problems.append(f"`aew {named}` is said to be refused, and a Lead may run it")
    return problems


# Preserve the planted mistake independently of the retired product option (E329).
F1 = "- A shell mutation still needs `--expect-rev <revision from aew status>` (from `status` or the previous command)."


@pytest.mark.parametrize(("switches", "push", "contained", "with_guide"), VARIANTS, ids=IDS)
def test_a_claim_about_every_command_holds_for_every_command_a_lead_may_run(switches, push, contained, with_guide):
    system, _ = rendered(switches, push, contained, with_guide)
    assert false_option_claims(system) == []
    # The planted line: `aew harness interrupt`, which the wake guide names, takes no --expect-rev.
    assert len(REACHABLE) > 20 and "--expect-rev: not taken by `aew harness interrupt`" in false_option_claims(F1)


@pytest.mark.parametrize(("switches", "push", "contained", "with_guide"), VARIANTS, ids=IDS)
def test_every_command_the_text_names_exists_and_an_operators_is_named_only_as_refused(switches, push, contained,
                                                                                       with_guide):
    system, core = rendered(switches, push, contained, with_guide)
    assert command_problems(own_text(system, core)) == []
    planted = projection.seat_text().replace("`aew lead release`", "`aew lead handoff cancel`")
    assert command_problems(planted) == ["`aew lead handoff cancel` is said to be refused, and a Lead may run it"]
    assert command_problems("- Ask the operator to run `aew lead acquire`.") != []


def test_the_seats_refused_commands_are_the_brokers_own_list():
    """F3: the line is the broker's credential-emitting seat commands, every one, and `aew lead handoff cancel`, which a
    pending handoff leaves the Lead (``lead_broker``'s docstring), is not among them."""
    seat = {frozenset(path) for path in lead_broker.CREDENTIAL_EMITTING} & {frozenset(p) for p in COMMANDS
                                                                          if p[:1] == ("lead",)}
    named = {frozenset(n.split()) for n in NAMED.findall(projection.seat_text())}
    assert named == seat and len(named) == len(K.SEAT_COMMANDS) == 5
    assert frozenset({"lead", "handoff", "cancel"}) in lead_broker.LEAD_REACHABLE
    assert projection.seat_text() in projection.LEAD_SYSTEM


# ---------------------------------------------------------------------------------------------- pointers resolve

# What the system text leaves to the guide's core (E367: one owner each), by a phrase of the core's that says it.
LEFT_TO_THE_GUIDE = {"the Lead never implements": "You never implement",
                     "it reads with its read, glob and grep tools": "read, glob and grep tools",
                     "free text goes through --fields or --file": "Put free text in `--fields -` or `--file -`",
                     "where a scoped mutation gets its binding": "use the prior value or approval digest shown",
                     "the approval channels": "the operator endpoint's challenge, and OpenCode's permission prompt",
                     "a run ending is not progress": "A run ending is not progress"}
# Pointers at the guide's text, which the Lead's own lines never make: they carry the guide's core, and a pointer is
# what drifted (F2: "as the guide says"; #593's m5: "as the guide's first step shows").
POINTER = re.compile(r"\bas the guide\b|\bthe guide's\b|\bthe guide (?:says|shows|names)\b", re.IGNORECASE)
SECTION = re.compile(r"`aew guide ([a-z-]+)`")


def pointer_problems(text: str) -> list[str]:
    return ([f"points at the guide: {m}" for m in POINTER.findall(text)]
            + [f"`aew guide {s}` is no section" for s in SECTION.findall(text)
               if s not in {"core", *guide.SECTION_NAMES}])


@pytest.mark.parametrize(("switches", "push", "contained", "with_guide"), VARIANTS, ids=IDS)
def test_every_pointer_resolves_and_each_fact_left_to_the_guide_is_said_once(switches, push, contained, with_guide):
    system, core = rendered(switches, push, contained, with_guide)
    own = own_text(system, core)
    assert pointer_problems(own) == []
    for fact, phrase in LEFT_TO_THE_GUIDE.items():
        assert phrase not in own, fact
        if with_guide:
            assert system.count(phrase) == 1 and phrase in core, fact
    if not with_guide:  # the core is one command away
        assert projection.NO_GUIDE in own and SECTION.search(projection.NO_GUIDE)
    for planted in ("Approval comes only through the operator's own channels, as the guide says.",
                    "pass them with `--fields -`, as the guide's first step shows.", "Read `aew guide step`."):
        assert pointer_problems(planted), planted


# ---------------------------------------------------------------------------------------------- no line overrides

OVERRIDE = re.compile(r"\b(?:the|a) (?:line|rule|text) (?:above|below)\b", re.IGNORECASE)


@pytest.mark.parametrize(("switches", "push", "contained", "with_guide"), VARIANTS, ids=IDS)
def test_no_line_overrides_another_and_a_timed_out_wait_is_told_once(switches, push, contained, with_guide):
    system, _ = rendered(switches, push, contained, with_guide)
    assert OVERRIDE.findall(system) == []
    timed_out = [line for line in system.splitlines() if line.lstrip().startswith(f"- `{K.TIMED_OUT}`:")]
    assert timed_out == [f"    - {K.wake_line(K.TIMED_OUT, contract.MESSAGING in switches, pushed=push)}"]
    assert OVERRIDE.findall("Otherwise a wait that times out here ends your turn too, whatever the line above says.")


# ------------------------------------------------------------------------------------- no value is always refused

class Reached(Exception):
    """The runner got past its own checks to the engine: the value is not refused there."""


class Engine_:
    def __getattr__(self, name: str) -> Any:
        raise Reached(name)


def always_refused(switches: frozenset[str]) -> dict[tuple[str, str, Any], str]:
    """Each (tool, property, value) the listing offers that its runner refuses before it reaches the engine, as a
    feature not built yet (a ``*_not_built`` reason), with the row's description."""
    out = {}
    for row in mcp.tools_list(NORMAL, switches)["tools"]:
        runner = run.RUNNERS.get(row["name"])
        if runner is None:
            continue
        for prop, schema in (row["inputSchema"].get("properties") or {}).items():
            for value in schema.get("enum") or []:
                reason = ""
                try:
                    runner(run.Call(Engine_(), SurfaceContext.outside_session(), {prop: value}, None))
                except errors.UsageError as refusal:
                    reason = str(refusal.details.get("reason", ""))
                except Exception as passed:  # past the value: the engine (Reached), or an argument the call lacks
                    reason = type(passed).__name__
                if reason.endswith("_not_built"):
                    out[(row["name"], prop, value)] = row["description"]
    return out


@pytest.mark.parametrize("switches", [frozenset(), ON], ids=["off", "on"])
def test_no_value_the_tool_list_offers_is_always_refused(switches):
    assert always_refused(switches) == {}


def test_a_value_a_runner_newly_refuses_as_not_built_is_found(monkeypatch):
    def refuses(call: run.Call) -> Any:
        if call.a.get("action") == "lower":
            raise errors.UsageError("not yet", reason="lower_not_built")
        raise Reached("engine")

    monkeypatch.setitem(run.RUNNERS, "steering", refuses)
    assert ("steering", "action", "lower") in always_refused(ON)


def test_every_compact_property_description_names_a_property_its_row_has():
    """A described property renamed in the catalog would leave its description unused (``presentation.PROPERTIES``)."""
    rows = {t.name: t for t in contract.catalog(contract.ALL_SWITCHES).values()}
    for name, prop in presentation.PROPERTIES:
        assert prop in rows[name].input_schema["properties"], (name, prop)
        compact = presentation.compact(rows[name]).input_schema["properties"][prop]
        assert compact["description"] == presentation.PROPERTIES[(name, prop)]


# ------------------------------------------------------------------------------------------ the typed results

LARGE = 200  # bytes: a value this long, sent twice in one result, is the duplicate R1 was (1,531 B)


def repeated(value: Any, seen: dict[str, str] | None = None, where: str = "") -> list[str]:
    """Each value of at least :data:`LARGE` bytes that appears twice in ``value``, with both places."""
    seen = {} if seen is None else seen
    found = []
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(text) >= LARGE and isinstance(value, dict | list):
        if text in seen:
            found.append(f"{where} repeats {seen[text]}")
        else:
            seen[text] = where
    children = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, child in children:
        found += repeated(child, seen, f"{where}.{key}")
    return found


def lead_reads(engine: Engine, name: str) -> tuple[dict[str, Any], str]:
    result = run.run_tool(engine, SurfaceContext.outside_session(), name, {})
    return readable.for_the_lead(readable.scrub(result)), readable.render(result)


@pytest.mark.parametrize("name", sorted(run.FULL))
def test_a_typed_project_read_holds_no_large_value_twice_and_says_where_the_whole_report_is(project, monkeypatch,
                                                                                          name):
    engine = Engine.discover(project.root)
    line, _ = lead_reads(engine, name)
    assert repeated(line) == [] and line["result"]["full"] == run.FULL[name]
    assert "next_actions" not in line["result"] and line["projection"]["hints"]
    assert "next_actions" not in line["result"].get("order", [])  # its list of parts names none it lacks (#599, m2)
    if name == "resume":  # a card keeps its staffing guidance unless the guide's staffing section gives it (#599, m1)
        whole = {c["id"]: c for c in engine.resume()["role_catalog"]}
        staffed = guide.staffed_cards()
        assert staffed and staffed <= set(whole)
        for card in line["result"]["role_catalog"]:
            kept = "use_when" in card
            assert kept is (card["id"] not in staffed and "use_when" in whole[card["id"]]), card["id"]
            assert card["id"] in staffed or card.get("use_when") == whole[card["id"]].get("use_when")
        assert all(c["id"] in guide.staffing_text() for c in line["result"]["role_catalog"] if c["id"] in staffed)
    monkeypatch.setattr(run, "_compact", lambda name, payload, projection: payload)  # the planted case: as it was
    assert any("next_actions" in r for r in repeated(lead_reads(engine, name)[0]))


def test_a_typed_status_read_costs_no_more_than_the_shells(project):
    """E231's finding 2, reversed: the typed `status` cost 3.9 KB more than `aew status`, every later request."""
    engine = Engine.discover(project.root)
    _, text = lead_reads(engine, "status")
    shell = engine.render_status(engine.status())
    assert len(text.encode("utf-8")) <= len(shell.encode("utf-8")), (len(text.encode()), len(shell.encode()))
