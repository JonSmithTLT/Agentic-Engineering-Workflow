"""The state-machine families of the generated reference (STG-12 S12-2, family 5): ``transitions``, ``states``,
``guards``, ``reason-rules``, then ``configuration-states`` and ``usage-live-states``, the two other machines.

Owner of the Ticket machine: ``aew.engine.transitions`` (``RULES``, ``STATES``, ``TERMINAL``, ``PHASE_ORDER``), imported
at run time (basis ``enumerated``). One record per edge, state, guard name and reason rule.

**What the labels claim.** The table is the registry, so every edge, state, guard and reason rule has a record, both
ways (``tests/integration/test_reference_machines.py``). Whether code can change a Ticket's state *without* asking the
table is a separate question, and the code does not stop it: ``WorkUnits.set_state`` does not call
``transitions.check`` (its callers do), and some code assigns ``unit["state"]`` itself. ``machines_writes.py`` reads
every such site with ``ast`` (``machines_writes_text.py`` is the second detector), and a site with no
``transitions.check`` call in its function is unresolved on the edges it can take (:data:`SITES`: the edges of the
operations it performs, narrowed to the source states its owner names where it names them, as ``Lead`` does for the
phases that wait on an invocation). An edge no unchecked site can take stays complete-by-construction; the others are
lower-bound. A site this reading does not know is unresolved on every edge. The declared table is held to the sites in
both directions, and a narrowed site's sources to the owner's registry in both directions.

**The limit of that pin.** The sites are found per function, with the forms of write each makes (a call of
``set_state``, an assignment to ``["state"]``). A new unchecked write in a function the table does not declare is a
difference: the build still renders, the site is unresolved on every edge, and ``check`` and
``test_every_state_write_site_is_behind_the_table_or_declared`` fail. A second write of the same form in a function
that is already declared, or in one that already asks the table, is not a difference: the reading does not count the
writes of a function, and does not say what a declared function writes to.

The ``states`` records are lower-bound because some state sets are in no table: a Story's or Epic's phase is derived
(``aew.engine.hierarchy.PARENT_STATES``), the control schema's state enum admits a state of its own, and the states of
the other machines whose ``["state"]`` key the declared sites write (an integration queue entry, a validation run, a
projected field value) are not read. Each is an unresolved item, read from its owner or from the declared sites, not
restated. ``_state_tuples`` sees only a tuple of strings named ``*STATES`` in the module of a machine; a state set
held any other way (a dict, a frozenset, a name that does not end so) is not seen.

``configuration-states`` and ``usage-live-states`` read ``STATES`` of ``aew.engine.configuration`` and
``aew.harness.usage_live``, each state's ``position`` being its index in the module's order (configuration documents
it as precedence order; usage-live documents no order for ``STATES``). The configuration states are
complete-by-construction on a check that is not the generator's own reading: the states the policy-document producer
(``configuration._policy_state``) returns, found in its source and by running it over every input, are in ``STATES``
(``tests/integration/test_reference_machines.py``). Two other places that give a state are not read: the ``Document``
built for a drifted manifest, and the manifest's own state in the index projection. Neither
module has an edge table, so each state's ``exits`` is an empty list whose ``fact_coverage`` is lower-bound with that
one unresolved item: an empty list found by a detector never means none (addendum 3).

The guards are read from the ``GuardTable`` of an ``Engine`` built in a temporary directory (its construction touches no
file; the engine composition test does the same): each guard name a rule names, with the evaluator it
resolves to per unit kind. Every ``coverage.registry`` of a complete-by-construction record resolves to an object
(``tests/unit/test_reference.py``).
"""

from __future__ import annotations

import importlib
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

from reference_families import common as C
from reference_families import machines_writes as W

TRANSITIONS, STATES, GUARDS, REASONS = "transitions", "states", "guards", "reason-rules"
CONFIGURATION, USAGE_LIVE = "configuration-states", "usage-live-states"
# Said by the machines page and by the state maps (`pages.py`): the machines the records hold are the ones a
# table lists.
NOT_LISTED = ("What no table lists (a Story's or Epic's phase, a second state tuple, the states of another machine) "
              "is in [gaps.md](gaps.md).")
OWNER = "aew.engine.transitions"
REGISTRY = f"{OWNER}:RULES"
GUARD_REGISTRY = "aew.engine.seams:GuardTable"
CONFIGURATION_MODULE, USAGE_LIVE_MODULE = "aew.engine.configuration", "aew.harness.usage_live"
HIERARCHY = "aew.engine.hierarchy"
_MACHINES = "tests/integration/test_reference_machines.py"
_WRITES = "tests/integration/test_reference_machine_writes.py"
EDGE_TESTS = (
    f"{_MACHINES}::test_the_transition_records_are_the_rules_both_ways",
    f"{_MACHINES}::test_the_table_accepts_exactly_its_edges_for_the_operations_it_names",
    f"{_MACHINES}::test_the_interrupt_sites_edges_are_the_phases_that_can_wait_on_an_invocation",
    f"{_WRITES}::test_every_state_write_site_is_behind_the_table_or_declared",
    f"{_WRITES}::test_the_two_state_write_detectors_agree_on_the_tree",
)
GUARD_TESTS = (f"{_MACHINES}::test_the_guard_records_are_the_registered_guards_the_rules_name",)
REASON_TESTS = (f"{_MACHINES}::test_the_reason_rules_are_the_flagged_edges_both_ways",)
# Only the configuration states have a check that is not the generator's own reading of its tuple (usage-live's states
# are lower-bound, and cite none).
CONFIGURATION_TESTS = (
    f"{_MACHINES}::test_the_small_machines_are_their_state_tuples_both_ways",
    f"{_MACHINES}::test_the_configuration_state_constants_are_the_states_in_order",
    f"{_MACHINES}::test_every_document_state_configuration_returns_is_in_states",
)

TICKET, PARENTS, PRIMITIVE, OTHER, COPY = "ticket", "parents", "primitive", "other-machine", "copy"


class Site(NamedTuple):
    kind: str
    vias: tuple[str, ...]  # TICKET only: the operations (``via`` of ``RULES``) whose edges the site can take
    what: str
    # TICKET only: (module, name) of a mapping whose keys are the only source states the site can take an edge from,
    # read from its owner (None: every source of the operations' edges)
    sources_from: tuple[str, str] | None = None


# The sites of ``machines_writes`` that have no ``transitions.check`` call in their function, declared. It is held to
# the detector in both directions (a site missing here is unresolved on every edge; an entry with no site raises), a
# TICKET site's vias are held to the vias of ``RULES``, and a narrowed site's sources to the edges of ``RULES``.
SITES: dict[tuple[str, str], Site] = {
    ("aew.engine.dependencies", "recompute_readiness"): Site(TICKET, ("recompute",), "moves Tickets between BLOCKED "
                                                                                    "and READY"),
    ("aew.engine.lead_ops", "Lead._interrupt_invocations"): Site(
        TICKET, ("interrupt",), "interrupts the Tickets whose invocation was lost",
        ("aew.engine.lead_ops", "PHASE_DRIVERS")),
    ("aew.engine.nonmutating_ops", "NonMutating.work_dispatch"): Site(TICKET, ("assign",), "dispatches a "
                                                                                           "non-mutating Ticket"),
    ("aew.engine.workspace_ops", "Assignment.work_assign"): Site(TICKET, ("assign",), "assigns a mutating Ticket"),
    ("aew.engine.work_ops", "WorkCommands.work_transition"): Site(TICKET, ("transition",), "carries out the Lead's "
                                                                                           "generic transition"),
    ("aew.engine.work_ops", "WorkUnits.set_state"): Site(PRIMITIVE, (), "the primitive: it applies the state its "
                                                                         "caller chose"),
    ("aew.engine.hierarchy", "recompute_parents"): Site(PARENTS, (), "derives a Story's or Epic's phase"),
    ("aew.engine.queue_ops", "Queue.defer"): Site(OTHER, (), "an integration queue entry's state"),
    ("aew.engine.queue_ops", "Queue.grant"): Site(OTHER, (), "an integration queue entry's state"),
    ("aew.engine.queue_ops", "Queue.release"): Site(OTHER, (), "an integration queue entry's state"),
    ("aew.engine.queue_ops", "Queue.requeue"): Site(OTHER, (), "an integration queue entry's state"),
    ("aew.engine.validation_ops", "Validation._terminate"): Site(OTHER, (), "a validation run's state"),
    ("aew.engine.configuration", "_Projector.fv"): Site(OTHER, (), "a projected field value's state"),
    ("aew.surface.availability", "_overlay"): Site(COPY, (), "a scratch copy a stage step's availability is asked of"),
    ("aew.surface.projection", "_control_part"): Site(COPY, (), "a copy of a unit's state in a result"),
}


def unchecked_sites(sites: list[W.StateWrite]) -> dict[tuple[str, str], set[str]]:
    """The sites with no ``transitions.check`` in their function, by (module, symbol), with their forms."""
    found: dict[tuple[str, str], set[str]] = {}
    for s in sites:
        if not s.checked:
            found.setdefault((s.module, s.symbol or ""), set()).add(s.form)
    return found


def site_problems(found: dict[tuple[str, str], set[str]], table: dict[tuple[str, str], Site],
                  rule_vias: set[str]) -> list[str]:
    """The declared table held to the detector (an entry no site matches) and to the machine (a via it lacks)."""
    problems = [f"{m}:{s} is declared as a state write with no transitions.check, and the reading finds no such site"
                for (m, s) in sorted(set(table) - set(found))]
    for (m, s), site in sorted(table.items()):
        if site.kind == TICKET and (not site.vias or not set(site.vias) <= rule_vias):
            problems.append(f"{m}:{s} is declared for vias {list(site.vias)}, which are not all operations of RULES")
    return problems


def site_sources(table: dict[tuple[str, str], Site]) -> dict[tuple[str, str], frozenset[str]]:
    """The source states each narrowed site can take an edge from: the keys of the registry its owner holds."""
    out: dict[tuple[str, str], frozenset[str]] = {}
    for key, site in sorted(table.items()):
        if site.sources_from is None:
            continue
        module, name = site.sources_from
        owner = getattr(importlib.import_module(module), name, None)
        if not isinstance(owner, Mapping):
            raise C.ReferenceError(f"{module}.{name}, which names the source states of {key[0]}:{key[1]}, is not a "
                                   "mapping")
        out[key] = frozenset(str(state) for state in owner)
    return out


def source_problems(table: dict[tuple[str, str], Site], sources: dict[tuple[str, str], frozenset[str]],
                    edges: dict[tuple[str, str], set[str]]) -> list[str]:
    """A narrowed site's sources held to ``RULES``: each state its owner names is the source of an edge of the site's
    operations (else the owner names a state the table has no edge from, and the narrowing drifted)."""
    problems = []
    for key, states in sorted(sources.items()):
        site = table[key]
        for state in sorted(states):
            if not any(frm == state and set(site.vias) & vias for (frm, _), vias in edges.items()):
                module, name = site.sources_from or ("", "")
                problems.append(f"{key[0]}:{key[1]} can take edges from {state} ({module}.{name} names it), and RULES "
                                f"has no {'/'.join(site.vias)} edge from {state}")
    return problems


def edge_unresolved(rule_vias: set[str], found: dict[tuple[str, str], set[str]],
                    table: dict[tuple[str, str], Site], frm: str | None = None,
                    sources: dict[tuple[str, str], frozenset[str]] | None = None) -> list[dict[str, Any]]:
    """The unresolved items of an edge performed by the operations ``rule_vias`` and leaving the state ``frm``: every
    unchecked site of the Ticket machine that can take it (a narrowed site only from the sources its owner names), and
    every unchecked site this reading does not know (it could take any edge)."""
    items = []
    for (module, symbol), forms in sorted(found.items()):
        site = table.get((module, symbol))
        how = " and ".join(sorted("calls set_state" if f == W.SET_STATE else "assigns the unit's state" for f in forms))
        if site is None:
            items.append(C.unresolved_item(module, symbol or None, f"{how} with no transitions.check in the function, "
                                           "and is not a site this reading knows"))
            continue
        allowed = (sources or {}).get((module, symbol))
        if site.kind == TICKET and rule_vias & set(site.vias) and (allowed is None or frm is None or frm in allowed):
            narrowed = f", from a key of {site.sources_from[1]}" if allowed is not None and site.sources_from else ""
            items.append(C.unresolved_item(module, symbol, f"{how} with no transitions.check in the function; it "
                                           f"{site.what} (operation {', '.join(site.vias)}{narrowed})"))
    return items


def other_machine_items(found: dict[tuple[str, str], set[str]], table: dict[tuple[str, str], Site]
                        ) -> list[dict[str, Any]]:
    """One unresolved item for each other machine whose ``["state"]`` key a declared site writes: its states are in no
    table this reading reads. Anchored at the first site (in order) that writes it."""
    first: dict[str, tuple[str, str]] = {}
    for key in sorted(found):
        site = table.get(key)
        if site is not None and site.kind == OTHER:
            first.setdefault(site.what, key)
    return [C.unresolved_item(module, symbol, f"writes a state key for another machine ({what}); that machine's states "
                              "are in no table this reading reads") for what, (module, symbol) in sorted(first.items())]


def _state_tuples(module: Any) -> dict[str, tuple[str, ...]]:
    """Every module-level tuple of strings whose name ends in STATES, other than ``STATES`` itself."""
    return {name: value for name, value in sorted(vars(module).items())
            if name.endswith("STATES") and name != "STATES" and isinstance(value, tuple)
            and all(isinstance(v, str) for v in value)}


def schema_state_enum() -> list[str] | None:
    """The control schema's work unit ``state`` enum, or None when the schema does not have it where it was."""
    from aew import schemas

    node: Any = schemas.schema("control")
    for key in ("$defs", "work_unit", "properties", "state", "enum"):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return list(node) if isinstance(node, list) else None


def guard_table() -> tuple[dict[tuple[str, str], Any], dict[tuple[str, str], Any]]:
    """The (name, unit kind) -> evaluator table and the (name, unit kind) -> query table of a freshly built Engine."""
    from aew.engine.api import Engine

    with tempfile.TemporaryDirectory(prefix="aew-reference-") as tmp:
        root = Path(tmp)
        guards = getattr(getattr(Engine(root, root / ".aew"), "_units", None), "guards", None)
        if guards is None:
            raise C.ReferenceError("aew.engine.api.Engine no longer holds its guard table at _units.guards")
        return guards.table(), guards.queries()


def build(ctx: C.Context) -> C.Built:
    from aew.engine import hierarchy
    from aew.engine import transitions as T
    from aew.engine.seams import KINDS

    rules = dict(T.RULES)
    rule_vias = {v for r in rules.values() for v in (r.via, *r.also)}
    found = unchecked_sites(W.tree_writes(ctx))
    sources = site_sources(SITES)
    edge_vias = {edge: {r.via, *r.also} for edge, r in rules.items()}
    problems = site_problems(found, SITES, rule_vias) + source_problems(SITES, sources, edge_vias)
    if problems:
        raise C.ReferenceError("the declared state-write sites are not what the code has (tools/reference_families/"
                               "machines.py SITES):\n  " + "\n  ".join(problems))

    records: list[C.Record] = []
    for (frm, to), rule in sorted(rules.items()):
        items = edge_unresolved({rule.via, *rule.also}, found, SITES, frm, sources)
        fact: dict[str, Any] = {"from": frm, "to": to, "via": rule.via, "reason_required": rule.reason_required,
                                "guard": rule.guard}
        if rule.also:  # a list fact is on the record only when the rule has one, with how complete it is
            fact["also"] = list(rule.also)
        coverage = C.lower_bound(items) if items else C.complete(REGISTRY, EDGE_TESTS)
        records.append(C.Record(TRANSITIONS, f"{frm}->{to}", OWNER, "RULES", "enumerated", coverage, fact,
                                fact_coverage={"also": C.complete(REGISTRY, EDGE_TESTS)} if rule.also else None))
        if rule.reason_required:
            records.append(C.Record(REASONS, f"{frm}->{to}", OWNER, "RULES", "enumerated",
                                    C.complete(REGISTRY, REASON_TESTS), {"from": frm, "to": to, "via": rule.via}))

    parent_states = tuple(hierarchy.PARENT_STATES)
    enum = schema_state_enum()
    only_parents = ", ".join(s for s in parent_states if s not in T.STATES)
    state_items = [C.unresolved_item(HIERARCHY, "PARENT_STATES",
                                     "a Story's or Epic's phase is derived from its children "
                                     f"({', '.join(parent_states)}); that is a second state set, and {only_parents} "
                                     "are in no Ticket state")]
    if enum is None:
        state_items.append(C.unresolved_item("aew.schemas", "SCHEMAS", "the control schema's work unit state enum "
                                             "is not where this reading looks for it"))
    else:
        extra = [s for s in enum if s not in T.STATES and s not in parent_states]
        if extra:
            state_items.append(C.unresolved_item("aew.schemas", "SCHEMAS", f"the control schema's work unit state enum "
                                                 f"also admits {', '.join(extra)}, which is in no state table"))
    state_items += other_machine_items(found, SITES)
    for state in T.STATES:
        records.append(C.Record(STATES, state, OWNER, "STATES", "enumerated", C.lower_bound(state_items),
                                {"state": state, "terminal": state in T.TERMINAL, "phase": T.PHASE_ORDER.get(state)}))

    table, queries = guard_table()
    guard_names = sorted({r.guard for r in rules.values() if r.guard})
    for name in guard_names:
        evaluators = []
        for kind in KINDS:
            fn = getattr(table.get((name, kind)), "__func__", table.get((name, kind)))
            if fn is not None:
                evaluators.append({"kind": kind, "module": fn.__module__, "symbol": fn.__qualname__,
                                   "query": (name, kind) in queries})
        if not evaluators:
            records.append(C.Record(GUARDS, name, OWNER, "RULES", "enumerated",
                                    C.lower_bound([C.unresolved_item(OWNER, "RULES", f"a rule names the guard {name}, "
                                                                     "which is registered for no unit kind")]),
                                    {"name": name, "evaluators": []},
                                    fact_coverage={"evaluators": C.lower_bound(
                                        [C.unresolved_item(OWNER, "RULES", f"{name} is registered nowhere")])}))
            continue
        general = next((e for e in evaluators if e["kind"] == KINDS[0]), evaluators[0])
        records.append(C.Record(GUARDS, name, general["module"], general["symbol"], "enumerated",
                                C.complete(GUARD_REGISTRY, GUARD_TESTS), {"name": name, "evaluators": evaluators},
                                fact_coverage={"evaluators": C.complete(GUARD_REGISTRY, GUARD_TESTS)}))

    records += _small(CONFIGURATION, CONFIGURATION_MODULE, CONFIGURATION_TESTS)
    records += _small(USAGE_LIVE, USAGE_LIVE_MODULE, ())
    return C.Built(records=records, pages={"state-machines.md": page(records)})


def _small(family: str, module_name: str, tests: tuple[str, ...]) -> list[C.Record]:
    """The states of a machine that has no edge table. Complete-by-construction only where a check other than this
    reading of the tuple is cited and the module holds no second state set; else lower-bound."""
    module = importlib.import_module(module_name)
    states = tuple(module.STATES)
    unresolved = [C.unresolved_item(module_name, name,
                                    f"a second state set of this module ({', '.join(values)}) is not recorded")
                  for name, values in _state_tuples(module).items()]
    if unresolved:
        coverage = C.lower_bound(unresolved)
    elif tests:
        coverage = C.complete(f"{module_name}:STATES", tests)
    else:  # no check cited: nothing is claimed
        coverage = C.unknown()
    exits = C.lower_bound([C.unresolved_item(module_name, "STATES", "no edge table: how a state follows another is not "
                                             "recorded in a table, so no exit is enumerated")])
    return [C.Record(family, state, module_name, "STATES", "enumerated", coverage,
                     {"state": state, "position": i, "exits": []}, fact_coverage={"exits": exits})
            for i, state in enumerate(states)]


def page(records: list[C.Record]) -> str:
    by = {f: [r for r in records if r.family == f] for f in (TRANSITIONS, STATES, GUARDS, REASONS, CONFIGURATION,
                                                             USAGE_LIVE)}
    operations = sorted({v for site in SITES.values() if site.kind == TICKET for v in site.vias})
    whole = {v for site in SITES.values() if site.kind == TICKET and site.sources_from is None for v in site.vias}
    narrowed = {v: site.sources_from for site in SITES.values()
                if site.kind == TICKET and site.sources_from is not None for v in site.vias if v not in whole}
    only = "".join(f", and for `{v}` only the edges leaving a key of `{src[0].rsplit('.', 1)[-1]}.{src[1]}`"
                   for v, src in sorted(narrowed.items()))
    lines = ["# State machines", "",
             "The Ticket machine from `aew.engine.transitions` (`RULES`, `STATES`, `TERMINAL`, `PHASE_ORDER`), its "
             "guards from the engine's guard table, and the two other state sets the product has a table for. "
             "Generated by `python tools/reference.py render`; do not edit. Every edge, state, guard and reason rule "
             "has a record. An edge is **lower-bound** when code that changes a Ticket's state without asking the "
             "table in the same function can take it (its `coverage.unresolved` names the code); the others are "
             "complete-by-construction. Today the lower-bound edges are those of the operations "
             f"{', '.join(f'`{o}`' for o in operations)}{only}; the Coverage column says which. {NOT_LISTED} The "
             "sites are found per function: a second write in a function already declared is not seen.", "",
             "## Ticket states", "", "| State | Terminal | Phase |", "|---|---|---|"]
    for r in by[STATES]:
        f = r.fact or {}
        lines.append(f"| `{f['state']}` | {'yes' if f['terminal'] else 'no'} | "
                     f"{'-' if f['phase'] is None else f['phase']} |")
    lines += ["", "## Transitions", "", "| From | To | Operation | Reason | Guard | Coverage |",
              "|---|---|---|---|---|---|"]
    for r in by[TRANSITIONS]:
        f = r.fact or {}
        via = f["via"] + (" (also " + ", ".join(f["also"]) + ")" if f.get("also") else "")
        label = r.coverage["label"]
        lines.append(f"| `{f['from']}` | `{f['to']}` | {via} | {'required' if f['reason_required'] else '-'} | "
                     f"{'`' + f['guard'] + '`' if f['guard'] else '-'} | {label} |")
    lines += ["", "## Guards", "", "| Guard | Evaluators, per unit kind |", "|---|---|"]
    for r in by[GUARDS]:
        f = r.fact or {}
        shown = "; ".join(f"{e['kind']}: `{e['symbol']}`" + (" (query)" if e["query"] else "") for e in f["evaluators"])
        lines.append(f"| `{f['name']}` | {shown or 'none registered'} |")
    for family, title, owner in ((CONFIGURATION, "Configuration document states", CONFIGURATION_MODULE),
                                 (USAGE_LIVE, "Live usage states", USAGE_LIVE_MODULE)):
        lines += ["", f"## {title}", "", f"From `{owner}.STATES`, in the order the module gives. No edge table "
                  "exists, so no exit is listed.", ""]
        lines += [f"{(r.fact or {})['position'] + 1}. `{(r.fact or {})['state']}`" for r in by[family]]
    return "\n".join(lines).rstrip("\n") + "\n"
