"""The ``control-keys`` family: the keys of the control state, by the code's own name (STG-12 S12-2; F44's seed).

Two key spaces. The **control** keys are the top-level properties of ``control.schema.json``, a closed schema the store
validates every committed state against, so the set is complete by construction. The **unit** keys are those a Ticket,
Story or Epic carries in ``work``: the schema's ``work_unit`` definition is open, so the inventory is the Ticket field
registry's (``ticket_fields.load_registry()``: the keys it classifies as inputs, and the ones it lists as engine
bookkeeping), joined with the schema's own properties; its completeness is the oracle's ``ticket_field_violations`` over
every step of every walk, which is a test and not a proof, so the unit records are lower-bound.

A record is keyed by the key's own string (``control-keys:coordination_unseen``; ``control-keys:unit:coordination``) and
anchored where the code defines it: the module-level constant named ``*_KEY`` whose value is the key
(``aew.coordination.layout:UNSEEN_KEY``); else, for a control key, the constant that names it in the initial state
(``aew.engine.base:POLICY_PINS``), else ``aew.engine.base:V2_ONLY_KEYS`` (the one definition of the keys only a v2
document carries), else the function that makes the initial state, else the function that adds it to that state
(``ControlStore.create`` adds ``outbox``), else the schema registry; for a unit key, the field registry. The facts are
scalars: whether the schema requires it, whether it is v2-only, whether the initial state has it, and, for a unit key,
how the registry classifies it.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reference_families import common as C
from reference_families import writers_flow as F

FAMILY = "control-keys"
UNIT = "unit"  # the key space of a unit in `work`: the record key is `unit:<key>`
SCHEMAS = ("aew.schemas", "SCHEMAS")  # the schema registry: where a control key without a name of its own is defined
V2_ONLY = ("aew.engine.base", "V2_ONLY_KEYS")
REGISTRY = ("aew.engine.ticket_fields", "load_registry")
ORACLE_CHECK = "ticket_field_violations"  # the oracle's check that every unit key is classified (tests/helpers)
CONSTANT_SUFFIX = "_KEY"  # the code's own naming of a state key: `UNSEEN_KEY`, `STORE_KEY`, `UNIT_KEY`
_TESTS = "tests/integration/test_reference_control_keys.py::"
CONTROL_CHECKS = (
    _TESTS + "test_the_control_schema_is_closed_and_refuses_a_key_it_does_not_declare",
    _TESTS + "test_every_load_and_commit_of_the_control_state_is_validated",
)
UNIT_OPEN = ("the control schema's unit definition is open and the registry's inventory is checked by the oracle's "
             f"`{ORACLE_CHECK}` over every step of every walk, so a unit key written on a path no walk "
             "exercises is classified only once a walk reaches it")


@dataclass(frozen=True)
class Inputs:
    """What the family reads, so a planted case can stand in for each owner."""

    control: Mapping[str, Any]  # the control schema
    v2_only: tuple[str, ...]
    inputs: Mapping[str, str]  # the registry's control-state inputs: key -> its field group
    bookkeeping: frozenset[str]  # the registry's engine bookkeeping keys
    trees: Mapping[str, ast.Module]  # module -> its parsed source
    packages: frozenset[str] = frozenset()  # the modules that are packages (a relative import resolves against them)


class _Dicts(C.Scoped):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[ast.Dict, str | None]] = []

    def visit_Dict(self, node: ast.Dict) -> None:
        self.found.append((node, self.symbol))
        self.generic_visit(node)


def _constants(tree: ast.Module) -> dict[str, str]:
    """The module-level string constants of a module, by name."""
    out: dict[str, str] = {}
    for node in tree.body:
        targets = (node.targets if isinstance(node, ast.Assign)
                   else [node.target] if isinstance(node, ast.AnnAssign) else [])
        value = getattr(node, "value", None)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            out.update({t.id: value.value for t in targets if isinstance(t, ast.Name)})
    return out


def key_constants(trees: Mapping[str, ast.Module]) -> dict[str, list[tuple[str, str]]]:
    """Value -> the (module, name) of every module-level constant named ``*_KEY`` that holds it, sorted."""
    out: dict[str, list[tuple[str, str]]] = {}
    for module in sorted(trees):
        for name, value in _constants(trees[module]).items():
            if name.endswith(CONSTANT_SUFFIX):
                out.setdefault(value, []).append((module, name))
    return {value: sorted(found) for value, found in out.items()}


def _name_of(trees: Mapping[str, ast.Module], packages: frozenset[str], module: str, node: ast.Name
             ) -> tuple[str, str, str] | None:
    """The module, name and value of the string constant a name refers to: one of its own module, or imported."""
    own = _constants(trees[module])
    if node.id in own:
        return module, node.id, own[node.id]
    imported = C.index_of(trees[module], module, module in packages).aliases.names.get(node.id)
    if imported and "." in imported:
        owner, _, name = imported.rpartition(".")
        if owner in trees and name in _constants(trees[owner]):
            return owner, name, _constants(trees[owner])[name]
    return None


def initial_state(trees: Mapping[str, ast.Module], packages: frozenset[str], required: set[str]
                  ) -> tuple[str, str, dict[str, tuple[str, str] | None], ast.Dict]:
    """The module, symbol, keys and node of the dict literal that makes the control state: the one that names every key
    the schema requires. A key is a string, or a name for one (then its constant). Not exactly one is an error, never a
    guess."""
    found: list[tuple[str, str, dict[str, tuple[str, str] | None], ast.Dict]] = []
    for module in sorted(trees):
        visitor = _Dicts()
        visitor.visit(trees[module])
        for node, symbol in visitor.found:
            keys: dict[str, tuple[str, str] | None] = {}
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys[k.value] = None
                elif isinstance(k, ast.Name) and (named := _name_of(trees, packages, module, k)) is not None:
                    keys[named[2]] = (named[0], named[1])
            if symbol and required <= set(keys):
                found.append((module, symbol, keys, node))
    if len(found) != 1:
        raise C.ReferenceError(
            f"the control state's constructor is the one dict literal that names every required key "
            f"({', '.join(sorted(required))}); found {len(found)}: {[(m, s) for m, s, _, _ in found]}")
    return found[0]


def created_keys(trees: Mapping[str, ast.Module], packages: frozenset[str], module: str, symbol: str,
                 literal: ast.Dict) -> dict[str, tuple[str, str]]:
    """The keys a function adds to the state the initial-state function hands it (``store.create(state, files)`` adds
    ``outbox``), each with the function that adds it: ``state["key"] = ...`` or ``state.setdefault("key", ...)`` on the
    parameter that receives the dict."""
    program = F.Program.of({name: (tree, name in packages) for name, tree in trees.items()})
    mod = program.modules[module]
    func = mod.funcs[symbol]
    names = {name for name, values in func.assigns.items() if any(v is literal for v in values)}
    out: dict[str, tuple[str, str]] = {}
    for call in func.calls:
        handed = [i for i, a in enumerate(call.args)
                  if a is literal or (isinstance(a, ast.Name) and a.id in names)]
        target = program.target(mod, func, call.func) if handed else None
        if target is None:
            continue
        params = target.params[1:] if target.params[:1] in (["self"], ["cls"]) and target.cls else target.params
        for i in handed:
            if i >= len(params):
                continue
            for node in ast.walk(target.node):
                key = _stored_key(node, params[i])
                if key is not None:
                    out.setdefault(key, (target.module, target.qual))
    return out


def _stored_key(node: ast.AST, param: str) -> str | None:
    """``param["key"] = ...`` or ``param.setdefault("key", ...)``: the constant key, else None."""
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == param
                    and isinstance(t.slice, ast.Constant) and isinstance(t.slice.value, str)):
                return t.slice.value
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault"
            and isinstance(node.func.value, ast.Name) and node.func.value.id == param and node.args
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
        return node.args[0].value
    return None


def records_of(inp: Inputs) -> list[C.Record]:
    schema = inp.control
    props = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    unit_def = (schema.get("$defs") or {}).get("work_unit") or {}
    unit_props, unit_required = set(unit_def.get("properties", {})), set(unit_def.get("required", []))
    constants = key_constants(inp.trees)
    init_module, init_symbol, init_keys, literal = initial_state(inp.trees, inp.packages, required)
    created = created_keys(inp.trees, inp.packages, init_module, init_symbol, literal)
    closed = schema.get("additionalProperties") is False
    control_coverage = (C.complete(f"{SCHEMAS[0]}:{SCHEMAS[1]}", CONTROL_CHECKS) if closed else C.lower_bound(
        [C.unresolved_item(SCHEMAS[0], SCHEMAS[1], "the control schema allows keys it does not declare")]))
    unit_coverage = C.lower_bound([C.unresolved_item(REGISTRY[0], REGISTRY[1], UNIT_OPEN)])
    records = []
    for key in sorted(props):
        if key in constants:
            module, symbol = constants[key][0]
        elif init_keys.get(key):
            module, symbol = init_keys[key]  # type: ignore[misc]
        elif key in inp.v2_only:
            module, symbol = V2_ONLY
        elif key in init_keys:
            module, symbol = init_module, init_symbol
        elif key in created:
            module, symbol = created[key]
        else:
            module, symbol = SCHEMAS
        fact = {"key": key, "scope": "control", "required": key in required, "v2_only": key in inp.v2_only,
                "initial": key in init_keys or key in created}
        records.append(C.Record(FAMILY, key, module, symbol, "declared", control_coverage, fact))
    for key in sorted(unit_props | set(inp.inputs) | inp.bookkeeping):
        module, symbol = constants[key][0] if key in constants else REGISTRY
        classification = f"input:{inp.inputs[key]}" if key in inp.inputs else (
            "bookkeeping" if key in inp.bookkeeping else "unclassified")
        fact = {"key": key, "scope": UNIT, "classification": classification, "in_schema": key in unit_props,
                "required": key in unit_required}
        records.append(C.Record(FAMILY, f"{UNIT}:{key}", module, symbol, "declared", unit_coverage, fact))
    return records


def problems(records: Mapping[str, Any]) -> list[str]:
    """The family's own invariants over its records as JSON: the key is the scope and the fact's key, the facts are
    the scalars of its scope, and a unit key is classified (an unclassified one is stated, the oracle refuses it)."""
    out: list[str] = []
    for rid, r in sorted(records.items()):
        if r.get("family") != FAMILY:
            continue
        fact = r.get("fact") or {}
        key = rid.removeprefix(f"{FAMILY}:")
        scope = fact.get("scope")
        if scope == "control":
            want = {"key", "scope", "required", "v2_only", "initial"}
            if key != fact.get("key"):
                out.append(f"{rid}: the key is not the control key {fact.get('key')!r}")
        elif scope == UNIT:
            want = {"key", "scope", "classification", "in_schema", "required"}
            if key != f"{UNIT}:{fact.get('key')}":
                out.append(f"{rid}: the key is not unit:{fact.get('key')}")
            if fact.get("classification") == "unclassified":
                out.append(f"{rid}: a unit key the registry does not classify "
                           f"(the oracle's `{ORACLE_CHECK}` refuses it)")
        else:
            out.append(f"{rid}: scope {scope!r} is neither control nor unit")
            continue
        flags = want & {"required", "v2_only", "initial", "in_schema"}
        if set(fact) != want or any(not isinstance(fact[k], bool) for k in flags):
            out.append(f"{rid}: the fact is not {sorted(want)} with its booleans")
    return out


def page(records: list[C.Record], skipped: list[tuple[str, str, str]]) -> str:
    control = [r for r in records if (r.fact or {}).get("scope") == "control"]
    unit = [r for r in records if (r.fact or {}).get("scope") == UNIT]
    lines = [
        "# Control-state keys", "",
        "The keys of the control state (`state/control.yaml`), by the code's own name. Generated by `python "
        "tools/reference.py render`; do not edit. Each key is a record, `control-keys:<key>` for a top-level key and "
        "`control-keys:unit:<key>` for a key of a unit in `work`, anchored where the code defines it: the "
        "module-level constant named `*_KEY` that holds it, else the one definition of the keys only a v2 document "
        "carries (`aew.engine.base:V2_ONLY_KEYS`), else the function that makes the initial state, else the schema "
        "registry (a control key) or the Ticket field registry (a unit key).", "",
        f"## Control keys ({len(control)})", "",
        "The top-level properties of the control schema, which is closed and which the store validates every state "
        "against (complete by construction). `required` is the schema's; `v2-only` keys only a v2 document may "
        "carry; `initial` keys are in the state `aew init` writes.", ""]
    for r in control:
        f = r.fact or {}
        flags = [name for name, on in (("required", f["required"]), ("v2-only", f["v2_only"]),
                                       ("initial", f["initial"])) if on]
        lines.append(f"- `{f['key']}`" + (f" ({', '.join(flags)})" if flags else "") + f": `{r.module}:{r.symbol}`")
    lines += ["", f"## Unit keys ({len(unit)})", "",
              "The keys a unit in `work` carries: the properties of the schema's unit definition (open) joined with "
              "the Ticket field registry's inputs and engine bookkeeping. A lower bound: " + UNIT_OPEN + ".", ""]
    for r in unit:
        f = r.fact or {}
        notes = [f["classification"], *(["in the schema"] if f["in_schema"] else []),
                 *(["required"] if f["required"] else [])]
        lines.append(f"- `{f['key']}` ({', '.join(notes)}): `{r.module}:{r.symbol}`")
    lines += ["", "## Constants named `*_KEY` that are not state keys", ""]
    if skipped:
        lines += [f"- `{m}:{n}` = `{v}`" for m, n, v in skipped]
    else:
        lines.append("None.")
    return "\n".join(lines).rstrip("\n") + "\n"


def build(ctx: C.Context) -> C.Built:
    from aew import schemas  # the owners at run time (reference.py checked that aew is this tree's)
    from aew.engine import base, ticket_fields

    registry = ticket_fields.load_registry()
    trees = {name: src.tree for name, src in ctx.sources().items() if src.tree is not None}
    inp = Inputs(schemas.schema("control"), tuple(base.V2_ONLY_KEYS),
                 {name: field.group for name, field in registry.store("control").items()},
                 frozenset(registry.bookkeeping), trees,
                 frozenset(name for name, src in ctx.sources().items() if src.is_package))
    records = records_of(inp)
    bad = problems({r.id: r.as_json() for r in records})
    if bad:
        raise C.ReferenceError("the control-keys records break their own rules:\n  " + "\n  ".join(C.shown(bad)))
    known = {(r.fact or {})["key"] for r in records}
    skipped = sorted((m, n, v) for v, found in key_constants(trees).items() if v not in known for m, n in found)
    return C.Built(records=records, pages={"control-keys.md": page(records, skipped)})
