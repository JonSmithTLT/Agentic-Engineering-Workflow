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

**``emitted_by``.** A record is a pair the lookup resolves; whether the slice returns it is a separate fact, the sites
of the admission path that return the pair (``{module, symbol}``; an empty list: the slice never returns it). Both
detectors read ``Carrier._member`` as the ordered steps it takes (a test of the origin, of a state a helper decides, of
the action, then the hand-on to a method) and inventory every ``refusal(...)`` call of the module, by name: a call
through an alias of ``refusal`` (``rf = refusal``) or through ``functools.partial`` is not seen (pinned, one probe
each), and the battery test below, which drives every registry action, is what shows a pair returned that way.
:func:`emitted`
replays the steps over the registry's actions, each step taking the actions it refuses and leaving the rest for the
next, so a site returns a pair when both its action and its cause are possible there. The fact is
complete-by-construction only when every ``refusal`` call of the module is placed by a step or by the method handed on
to, and no pair is one the tables lack; otherwise it is lower-bound and the calls it could not place are listed. A test
drives ``Carrier._member`` over a battery of states and compares the pairs it returns with the pairs read.

**Why the causes are complete-by-construction.** Every refusal result is built in one function. ``refusal(action,
cause)`` looks the pair up in the two tables and fails closed (an ``AssertionError``, never a default code) when
neither has it; the only other places that make a result with a ``reason_code`` pass a refusal's through or say there
is none, and the set of those places is declared (:data:`BUILDERS`) and held to the source in both directions. So a
cause the admission path returns is a key of one of the two tables. The string ``"reason_code"`` is read wherever it
occurs in the module, by both detectors, by symbol and by what the node is (a dict key or value, a subscript load,
store or delete, a positional argument of a call by callee, a keyword argument by callee, a comparison, any other), and
the occurrences, counted, are a declared set (:data:`OCCURRENCES`) held to the source in both directions. So
``m.setdefault("reason_code", v)``, an annotated or an augmented store and ``setattr(m, "reason_code", v)`` are each an
occurrence nobody declared, whatever the spelling. The places that make one are read as well, with the kind of the
value (:data:`BUILDERS`): a dict literal, a subscript store and a keyword argument. Not seen, because they hold no
occurrence of the string (pinned, one probe each): a computed key (``m[key] = v``), a ``setattr`` whose name is
computed (``setattr(m, name, v)``) and a ``**`` of a dict built elsewhere (which is read where it is made); any name
built at run time is the same kind of form, so no longer list would close the class. The causes
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
from collections import Counter
from collections.abc import Mapping
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
# Every occurrence of the string ``"reason_code"`` in the module, by symbol and by what the node is, counted: the
# lookup's two dict literals, the owner's success, and the two pass-throughs of a member's reason (a dict key and a
# subscript read each). A new occurrence, of any kind, is a place that may make or change a reason: it is an
# unresolved item until it is declared here.
OCCURRENCES: tuple[tuple[str, str], ...] = (
    ("Carrier._allocate", "dict-key"), ("Carrier._allocate", "subscript-load"),
    ("Carrier._heb_continue", "dict-key"),
    ("Carrier._result", "dict-key"), ("Carrier._result", "subscript-load"),
    ("refusal", "dict-key"), ("refusal", "dict-key"))
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
EMITTED_REGISTRY = f"{COMMAND_MODULE}:Carrier"
EMITTED_TESTS = (
    f"{_TESTS}::test_the_emitted_pairs_are_the_ones_the_carrier_returns_over_a_battery_of_states",
    f"{_TESTS}::test_every_refusal_call_of_the_module_is_placed_by_the_reading",
    f"{_TESTS}::test_the_two_command_detectors_agree_on_the_source",
)


class Reading(NamedTuple):
    origin: str | None  # the origin ``_member`` requires before an action goes on to an owner
    action: str | None  # the one action ``_member`` hands to an owner
    causes: list[str]  # every cause literal given to ``refusal``, and the returns of ``_delegation`` it is handed
    unreadable: list[str]  # symbols of ``refusal`` calls whose cause could not be read
    delegation: list[str]  # the string returns of ``Carrier._delegation``
    builders: list[tuple[str, str, str]]  # (symbol, form, kind) of every place that makes a "reason_code"
    # (symbol, first argument, cause) of every ``refusal(first, cause)`` call: the cause is the literal, ``$<method>``
    # for a variable holding the returns of a method of the carrier, or ``?``
    calls: list[tuple[str, str, str]]
    # the steps of ``Carrier._member``, in order: (symbol, kind, literal, cause), the kind being ``origin-test`` (the
    # origin is not the literal: refused), ``state-test`` (a helper's verdict is true: refused), ``action-test`` (the
    # action is not the literal: refused) or ``hand-on`` (the literal is the method the rest go on to)
    steps: list[tuple[str, str, str, str]]
    # (symbol, kind) of every occurrence of the string "reason_code", sorted, repeats kept
    occurrences: list[tuple[str, str]]


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


def _is_reason(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value == "reason_code"


class _Occurrences(C.Scoped):
    """Every occurrence of the string ``"reason_code"``, and every keyword argument of that name, by symbol and by what
    the node is: a dict key or value, a subscript (load, store or delete: an assignment, an annotated or an augmented
    one is a store), a positional argument of a call (by callee), a keyword argument (by callee), a comparison, or any
    other. Positions (line, column) pair a string with the handler that classified it."""

    def __init__(self) -> None:
        super().__init__()
        self.strings: list[tuple[tuple[int, int], str]] = []  # (position, symbol) of every such string
        self.kinds: dict[tuple[int, int], str] = {}
        self.keywords: list[tuple[str, str]] = []

    def _kind(self, node: ast.expr | None, kind: str) -> None:
        if node is not None and _is_reason(node):
            self.kinds[(node.lineno, node.col_offset)] = kind

    def visit_Constant(self, node: ast.Constant) -> None:
        if _is_reason(node):
            self.strings.append(((node.lineno, node.col_offset), self.symbol or ""))

    def visit_Dict(self, node: ast.Dict) -> None:
        for key in node.keys:
            self._kind(key, "dict-key")
        for value in node.values:
            self._kind(value, "dict-value")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        self._kind(node.slice, "subscript-" + type(node.ctx).__name__.lower())
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        callee = ast.unparse(node.func)
        for arg in node.args:
            self._kind(arg, f"call:{callee}")
        for keyword in node.keywords:
            if keyword.arg == "reason_code":
                self.keywords.append((self.symbol or "", f"keyword:{callee}"))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for operand in (node.left, *node.comparators):
            self._kind(operand, "compare")
        self.generic_visit(node)

    def found(self) -> list[tuple[str, str]]:
        return sorted([(symbol, self.kinds.get(position, "other")) for position, symbol in self.strings]
                      + self.keywords)


def _string_returns(fn: ast.FunctionDef) -> list[str]:
    returns = [r.value for r in ast.walk(fn) if isinstance(r, ast.Return) and isinstance(r.value, ast.Constant)]
    return sorted({v.value for v in returns if isinstance(v.value, str)})


def _self_call(node: ast.AST | None) -> str | None:
    """``self.name(...)``: the name."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"):
        return node.func.attr
    return None


def _refusal_call(node: ast.AST | None) -> ast.Call | None:
    """The node, when it is a call of ``refusal``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "refusal":
        return node
    return None


def _cause_ref(node: ast.expr, assigned: dict[str, str]) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in assigned:
        return f"${assigned[node.id]}"
    return "?"


def _held(fn: ast.FunctionDef) -> dict[str, str]:
    """The names assigned a call of a method of the carrier (``e = self._delegation(...)``), and the method."""
    held: dict[str, str] = {}
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and (method := _self_call(node.value)) is not None):
            held[node.targets[0].id] = method
    return held


def _steps(symbol: str, member: ast.FunctionDef) -> list[tuple[str, str, str, str]]:
    """What ``_member`` does with an action, in order. A statement that is none of the forms contributes no step; its
    refusals are then unplaced calls, which the build names."""
    held = _held(member)
    steps: list[tuple[str, str, str, str]] = []
    for stmt in member.body:
        if isinstance(stmt, ast.If) and not stmt.orelse and len(stmt.body) == 1:
            ret = stmt.body[0]
            call = _refusal_call(ret.value) if isinstance(ret, ast.Return) else None
            if call is None or len(call.args) < 2:
                continue
            cause = _cause_ref(call.args[1], held)
            test = stmt.test
            if isinstance(test, ast.Name) and test.id in held:
                steps.append((symbol, "state-test", "", cause))
            elif (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.NotEq)
                  and isinstance(test.comparators[0], ast.Constant) and isinstance(test.comparators[0].value, str)):
                left, literal = test.left, test.comparators[0].value
                if (isinstance(left, ast.Subscript) and isinstance(left.slice, ast.Constant)
                        and left.slice.value == "origin"):
                    steps.append((symbol, "origin-test", literal, cause))
                elif isinstance(left, ast.Name) and left.id == "action":
                    steps.append((symbol, "action-test", literal, cause))
        elif isinstance(stmt, ast.Return) and (method := _self_call(stmt.value)) is not None:
            steps.append((symbol, "hand-on", method, ""))
    return steps


def _calls(tree: ast.Module) -> list[tuple[str, str, str]]:
    """Every ``refusal(first, cause)`` call of the module, by the function or method it is in."""
    found: list[tuple[str, str, str]] = []

    def scan(symbol: str, fn: ast.FunctionDef) -> None:
        held = _held(fn)
        for node in ast.walk(fn):
            call = _refusal_call(node)
            if call is not None and len(call.args) >= 2:
                found.append((symbol, ast.unparse(call.args[0]).replace('"', "'"), _cause_ref(call.args[1], held)))

    for top in tree.body:
        if isinstance(top, ast.FunctionDef):
            scan(top.name, top)
        elif isinstance(top, ast.ClassDef):
            for item in top.body:
                if isinstance(item, ast.FunctionDef):
                    scan(f"{top.name}.{item.name}", item)
    return sorted(found)


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
    steps = _steps("Carrier._member", member) if member is not None else []
    occurrences = _Occurrences()
    occurrences.visit(tree)
    return Reading(origin, action, sorted(causes), sorted(set(unreadable)), delegation, sorted(builders.found),
                   _calls(tree), steps, occurrences.found())


def causes_of(reading: Reading, ref: str) -> list[str] | None:
    """The causes a call can give, from its cause ref: the literal, or the returns of ``_delegation``; None when the
    reading cannot say (a variable of another method, or an expression)."""
    if ref == "$_delegation":
        return list(reading.delegation)
    return None if ref.startswith("$") or ref == "?" else [ref]


def emitted(reading: Reading, registry: Mapping[str, Mapping[str, Any]],
            named: set[tuple[str, str]]) -> tuple[dict[tuple[str, str], list[str]], list[str]]:
    """The (action, cause) pairs the admission path returns, each with the symbols that return it, and why the
    reading is not complete (empty when it is). The steps of ``_member`` are replayed over the registry's actions in
    order, each step taking the actions it refuses and leaving the rest for the next; the method the last step hands
    on to returns for the actions that are left. ``named``: the pairs the tables name."""
    if reading.origin is None or reading.action is None:
        return {}, ["the steps of Carrier._member are not where this reading looks for them (the origin and the one "
                    "action it hands on are not found)"]
    problems: list[str] = []
    pairs: dict[tuple[str, str], set[str]] = {}
    placed: Counter[tuple[str, str, str]] = Counter()
    handed: list[tuple[str, set[str]]] = []
    remaining = set(registry)

    def returns(symbol: str, first: str, ref: str, actions: set[str]) -> None:
        placed[(symbol, first, ref)] += 1
        causes = causes_of(reading, ref)
        if causes is None:
            problems.append(f"{symbol} returns a refusal whose cause this reading cannot read ({ref})")
            return
        for action in actions:
            for cause in causes:
                pairs.setdefault((action, cause), set()).add(symbol)

    for symbol, kind, literal, cause in reading.steps:
        if kind == "origin-test":
            taken = {a for a in remaining if registry[a]["origin"] != literal}
            remaining -= taken
            returns(symbol, "action", cause, taken)
        elif kind == "state-test":
            returns(symbol, "action", cause, set(remaining))
        elif kind == "action-test":
            taken = {a for a in remaining if a != literal}
            remaining -= taken
            returns(symbol, "action", cause, taken)
        elif kind == "hand-on":
            handed.append((f"{symbol.rsplit('.', 1)[0]}.{literal}", set(remaining)))
    for symbol, actions in handed:
        for site, first, ref in reading.calls:
            if site == symbol and first == "i['action']":
                returns(symbol, first, ref, actions)
    for site, first, ref in sorted((Counter(reading.calls) - placed).elements()):
        problems.append(f"{site} returns a refusal on a path this reading cannot place ({first}, {ref})")
    for action, cause in sorted(set(pairs) - named):
        problems.append(f"the code can return {cause} for {action}, which no table names (the lookup fails closed)")
    return {pair: sorted(symbols) for pair, symbols in pairs.items()}, sorted(set(problems))


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
    found_here, declared_here = Counter(reading.occurrences), Counter(OCCURRENCES)
    for (symbol, kind), n in sorted((found_here - declared_here).items()):
        problems.append(C.unresolved_item(COMMAND_MODULE, symbol or None,
                                          f"has the string reason_code as {kind} outside the declared places "
                                          f"({n} more than declared)"))
    for (symbol, kind), n in sorted((declared_here - found_here).items()):
        problems.append(C.unresolved_item(COMMAND_MODULE, symbol or None,
                                          f"no longer has the {kind} of reason_code the declared places list "
                                          f"({n} fewer than declared)"))
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
    named_pairs = {(action, cause) for table in (vendored, own) for action, causes in table.items() for cause in causes}
    pairs, why_not = emitted(reading, registry, named_pairs)
    emitted_items = [C.unresolved_item(COMMAND_MODULE, "Carrier._member", why) for why in why_not]
    emitted_coverage = C.lower_bound(emitted_items) if emitted_items else C.complete(EMITTED_REGISTRY, EMITTED_TESTS)
    for source, table, module_name, symbol in (("vendored", vendored, ADOPTED, "refusals"),
                                               ("code", own, COMMAND_MODULE, "SLICE_OWNER_REASONS")):
        for action, causes in sorted(table.items()):
            for cause, reason in sorted(causes.items()):
                if source == "code" and cause in vendored.get(action, {}):
                    continue  # the lookup finds the vendored one first: the pair is the vendored record's
                sites = [{"module": COMMAND_MODULE, "symbol": s} for s in pairs.get((action, cause), [])]
                fact = {"action": action, "cause": cause, "reason": reason, "source": source, "emitted_by": sites}
                records.append(C.Record(REFUSALS, f"{action}:{cause}", module_name, symbol, "enumerated", coverage,
                                        fact, fact_coverage={"emitted_by": emitted_coverage}))
    return records
