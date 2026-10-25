"""The ``commands`` and ``command-refusals`` families (STG-12 S12-2, family 6b, the designer's second addendum): the
actions STG-02's command path admits and the causes it can refuse them with.

**``commands``.** Owner: ``aew.stg02.adopted.registry()``, the vendored action registry the command path loads (basis
``enumerated``): one record per action with its ``origin`` and ``owner`` (``sole_admitting_owner``) as the registry
states them, and ``reaches_owner``: whether admission can hand the action to an owner and an effect. The registry
cannot say that; the code does, in ``Carrier._member``: an action whose origin is not the one delegated-grant origin
is refused before any owner state is read, and of the rest only the one action ``_member`` names goes on to
``_heb_continue``. The two literals are read from ``_member`` (by ``ast``, and by ``stg02_commands_text.py``, an
independently written second reading), so ``reaches_owner`` follows the code: today only ``CONTINUE_ELIGIBLE_WORK``.
If the shape of ``_member`` is not found the field is null and the cause is an unresolved item of every record.

**``command-refusals``.** One record per refusal cause the lookup resolves: ``adopted.refusals()`` (source
``vendored``, the loaded map, anchored at it) and ``commands.SLICE_OWNER_REASONS`` (source ``code``, causes the code
defines itself), with the wire ``reason`` each maps to. ``NOT_MODELLED`` is not a third source: ``Carrier._member``
returns it through ``refusal`` like every other cause, and it is a key of the vendored map for each action that can
return it.

**Why the causes are complete-by-construction.** Every refusal result is built in one function. ``refusal(action,
cause)`` looks the pair up in the two tables and fails closed (an ``AssertionError``, never a default code) when
neither has it; the only other places that make a result with a ``reason_code`` pass a refusal's through or say there
is none, and the set of those places is declared (:data:`BUILDERS`) and held to the source in both directions. So a
cause the admission path returns is a key of one of the two tables. A place that makes a ``reason_code`` is read in
three spellings, by both detectors: a dict literal with the key, a subscript store to it, and a keyword argument of
that name on any call (``dict(...)``, ``.update(...)``, a constructor). A computed key, ``setattr`` and a ``**`` of a
dict built elsewhere are not seen (pinned, one probe each); a dict built elsewhere is read where it is made. The causes
the code spells, as literals in ``refusal`` calls and as the returns of ``_delegation`` (which ``_member`` hands to
``refusal`` through a variable), are read the same two ways, and each must be a key of some table. A literal cause no
table names, a ``refusal`` call whose cause cannot be read, a table action the registry lacks, or a builder outside the
declared set, is an unresolved item of every refusal record, and the label is then lower-bound. A reading that cannot
be sure is stated as unreadable and not guessed: a ``refusal`` call with fewer than two positional arguments, a cause
variable from a helper that returns something other than a string constant, and a second, different
``r["origin"] != ...`` or ``action != ...`` in ``_member`` (which would make the one the reading takes ambiguous) are
all unresolved items.
"""

from __future__ import annotations

import ast
import importlib
from typing import Any, NamedTuple

from reference_families import common as C

COMMANDS, REFUSALS = "commands", "command-refusals"
ADOPTED = "aew.stg02.adopted"
COMMAND_MODULE = "aew.stg02.commands"
LOOKUP = f"{COMMAND_MODULE}:refusal"
REGISTRY = f"{ADOPTED}:registry"
# The places that build a result with a ``reason_code``, by symbol, by how (a dict literal, a subscript store, a keyword
# argument) and by what the value is: the lookup (a name, the reason it found), the owner's success (None) and the two
# pass-throughs of a member's reason (a subscript), into the owner's record and into the receipt.
BUILDERS: frozenset[tuple[str, str, str]] = frozenset({
    ("refusal", "literal", "name"), ("Carrier._heb_continue", "literal", "none"),
    ("Carrier._allocate", "literal", "subscript"), ("Carrier._result", "literal", "subscript")})
_TESTS = "tests/integration/test_reference_stg02.py"
COMMAND_TESTS = (
    f"{_TESTS}::test_the_command_records_are_the_registry_both_ways",
    f"{_TESTS}::test_only_the_continue_action_reaches_an_owner_by_the_reading_and_by_a_request",
)
REFUSAL_TESTS = (
    f"{_TESTS}::test_the_refusal_records_are_the_two_tables_both_ways",
    f"{_TESTS}::test_every_refusal_result_comes_through_the_one_lookup",
    f"{_TESTS}::test_the_two_command_detectors_agree_on_the_source",
)


class Reading(NamedTuple):
    origin: str | None  # the origin ``_member`` requires before an action goes on to an owner
    action: str | None  # the one action ``_member`` hands to an owner
    causes: list[str]  # every cause literal given to ``refusal``, and the returns of ``_delegation`` it is handed
    unreadable: list[str]  # symbols of ``refusal`` calls whose cause could not be read
    delegation: list[str]  # the string returns of ``Carrier._delegation``
    builders: list[tuple[str, str, str]]  # (symbol, form, kind) of every place that makes a "reason_code"


def _kind(value: ast.expr) -> str:
    if isinstance(value, ast.Constant) and value.value is None:
        return "none"
    if isinstance(value, ast.Name):
        return "name"
    if isinstance(value, ast.Subscript):
        return "subscript"
    return "other"


class _Builders(C.Scoped):
    """Every place that makes a ``reason_code``, by symbol, form and what the value is: a dict literal with the key, a
    subscript store to the key, and a keyword argument of that name on any call. A computed key, ``setattr`` and a
    ``**`` of a dict built elsewhere are not seen."""

    def __init__(self) -> None:
        super().__init__()
        self.found: set[tuple[str, str, str]] = set()

    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "reason_code":
                self.found.add((self.symbol or "", "literal", _kind(value)))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if (isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "reason_code"):
                self.found.add((self.symbol or "", "store", _kind(node.value)))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        for keyword in node.keywords:
            if keyword.arg == "reason_code":
                self.found.add((self.symbol or "", "keyword", _kind(keyword.value)))
        self.generic_visit(node)


def _string_returns(fn: ast.FunctionDef) -> list[str]:
    returns = [r.value for r in ast.walk(fn) if isinstance(r, ast.Return) and isinstance(r.value, ast.Constant)]
    return sorted({v.value for v in returns if isinstance(v.value, str)})


def _other_returns(fn: ast.FunctionDef) -> bool:
    """Whether the function returns anything but a string constant or None: a cause read from it would be incomplete."""
    return any(isinstance(r, ast.Return) and r.value is not None
               and not (isinstance(r.value, ast.Constant) and (isinstance(r.value.value, str) or r.value.value is None))
               for r in ast.walk(fn))


def read(tree: ast.Module) -> Reading:
    origins: set[str] = set()
    actions: set[str] = set()
    causes: set[str] = set()
    unreadable: list[str] = []
    delegation: list[str] = []
    methods: dict[str, ast.FunctionDef] = {}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Carrier"):
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    if "_delegation" in methods:
        delegation = _string_returns(methods["_delegation"])
    member = methods.get("_member")
    if member is not None:
        for node in ast.walk(member):
            if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotEq)
                    and isinstance(node.comparators[0], ast.Constant) and isinstance(node.comparators[0].value, str)):
                continue
            left = node.left
            if (isinstance(left, ast.Subscript) and isinstance(left.slice, ast.Constant)
                    and left.slice.value == "origin"):
                origins.add(node.comparators[0].value)
            elif isinstance(left, ast.Name) and left.id == "action":
                actions.add(node.comparators[0].value)
    # two different literals make the one the reading takes ambiguous: not found, never "the last one"
    origin = next(iter(origins)) if len(origins) == 1 else None
    action = next(iter(actions)) if len(actions) == 1 else None
    scopes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    for fn in scopes:
        assigned: dict[str, str] = {}  # name -> the method of the carrier whose returns it holds
        for node in ast.walk(fn):
            if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                    and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                    and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "self"):
                assigned[node.targets[0].id] = node.value.func.attr
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "refusal"):
                continue
            if len(node.args) < 2:  # the cause is a keyword, or missing: not read
                unreadable.append(fn.name)
                continue
            cause = node.args[1]
            if isinstance(cause, ast.Constant) and isinstance(cause.value, str):
                causes.add(cause.value)
            elif (isinstance(cause, ast.Name) and assigned.get(cause.id) in methods
                  and not _other_returns(methods[assigned[cause.id]])):
                causes.update(_string_returns(methods[assigned[cause.id]]))
            else:
                unreadable.append(fn.name)
    builders = _Builders()
    builders.visit(tree)
    return Reading(origin, action, sorted(causes), sorted(set(unreadable)), delegation, sorted(builders.found))


def build(ctx: C.Context) -> list[C.Record]:
    adopted = importlib.import_module(ADOPTED)
    module = importlib.import_module(COMMAND_MODULE)
    src = ctx.sources().get(COMMAND_MODULE)
    if src is None or src.tree is None:
        raise C.ReferenceError(f"{COMMAND_MODULE} cannot be read")
    registry: dict[str, dict[str, Any]] = adopted.registry()
    vendored: dict[str, dict[str, str]] = adopted.refusals()
    own: dict[str, dict[str, str]] = module.SLICE_OWNER_REASONS
    reading = read(src.tree)
    found_shape = reading.origin is not None and reading.action is not None

    records: list[C.Record] = []
    for action, row in sorted(registry.items()):
        reaches = (row["origin"] == reading.origin and action == reading.action) if found_shape else None
        fact = {"action": action, "origin": row["origin"], "owner": row["sole_admitting_owner"],
                "reaches_owner": reaches}
        problems = [] if found_shape else [C.unresolved_item(
            COMMAND_MODULE, "Carrier._member",
            "the origin and the one action it hands to an owner are not where this reading looks for them")]
        records.append(C.Record(COMMANDS, action, ADOPTED, "registry", "enumerated",
                                C.lower_bound(problems) if problems else C.complete(REGISTRY, COMMAND_TESTS), fact))

    named = {cause for table in (vendored, own) for causes in table.values() for cause in causes}
    problems = []
    for cause in reading.causes:
        if cause not in named:
            problems.append(C.unresolved_item(COMMAND_MODULE, "refusal",
                                              f"the code refuses with {cause}, which no table names (the lookup fails "
                                              "closed on it)"))
    problems += [C.unresolved_item(COMMAND_MODULE, symbol, "a refusal whose cause this reading cannot read")
                 for symbol in reading.unreadable]
    for symbol, form, kind in sorted(set(reading.builders) - BUILDERS):
        problems.append(C.unresolved_item(COMMAND_MODULE, symbol or None,
                                          f"makes a reason_code ({form}, {kind}) outside the declared places"))
    for action in sorted((set(vendored) | set(own)) - set(registry)):
        problems.append(C.unresolved_item(ADOPTED, "refusals", f"{action} has refusal causes and is no action of the "
                                          "registry"))
    for action in sorted(set(registry) - set(vendored)):
        problems.append(C.unresolved_item(ADOPTED, "refusals",
                                          f"{action} is an action of the registry and has no entry in the refusal map"))
    coverage = C.lower_bound(problems) if problems else C.complete(LOOKUP, REFUSAL_TESTS)
    for source, table, module_name, symbol in (("vendored", vendored, ADOPTED, "refusals"),
                                               ("code", own, COMMAND_MODULE, "SLICE_OWNER_REASONS")):
        for action, causes in sorted(table.items()):
            for cause, reason in sorted(causes.items()):
                if source == "code" and cause in vendored.get(action, {}):
                    continue  # the lookup finds the vendored one first: the pair is the vendored record's
                fact = {"action": action, "cause": cause, "reason": reason, "source": source}
                records.append(C.Record(REFUSALS, f"{action}:{cause}", module_name, symbol, "enumerated", coverage,
                                        fact))
    return records
