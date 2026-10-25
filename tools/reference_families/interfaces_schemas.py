"""The ``schemas`` family (STG-12 S12-2, family 6): the JSON schemas of the durable artifacts, flattened.

Owner: ``aew.schemas.SCHEMAS`` (name -> file), imported at run time (basis ``enumerated``), held to the directory's
``*.schema.json`` files in both directions. One record per schema: its ``$id`` and, flattened, every property path with
its type and the paths it requires.

**Flattening** follows the schema as the repository's own validator does: a ``$ref`` is resolved through the registry
the validator uses (``aew.schemas._registry``: the schemas that refer to one another by ``$id``, such as the control
state's ``last_transition``), and a path is spelled ``a.b`` for a property, ``a[]`` for the items of an array,
``a[0]`` for a positional item, ``a.*`` for the values an ``additionalProperties`` schema describes and
``a.<pattern>`` for a ``patternProperties`` key. A branch of ``oneOf``, ``anyOf``, ``allOf`` or ``then``/``else``
contributes its paths at the node's own path (``if`` and ``not`` only constrain, and name no path). A path reached
twice has the union of its types. A path is *required* when an enclosing object requires it unconditionally:
``required`` under ``oneOf``, ``anyOf`` or ``if`` is not listed. A required key that nothing declares under
``properties`` is still a path: it has the type of the object's ``additionalProperties`` schema or of the
``patternProperties`` schema its name matches, and none (the type ``""``) only when the schema gives it none.

The properties and the required list are what a reading found, so each carries its own coverage (``fact_coverage``).
Every keyword of a schema node is classified: walked (it names paths), constraint-only (it constrains and names none: a
``type``, a ``pattern``, ``not``, ``if``, ``propertyNames``), an annotation (``title``, ``x-...``), or unwalked. They
are lower-bound for a schema that uses an unwalked keyword (``contains``, ``dependentSchemas``,
``unevaluatedProperties``, ``unevaluatedItems``, ``additionalItems``, ``contentSchema``, a dynamic ``$ref``, array-form
``items``), a keyword this reading has not classified, a ``$ref`` that does not resolve, or a ``$ref`` that recurses
(the recursion is cut at the second visit): each is an unresolved item of the schema, by name. The record set is
complete-by-construction over the registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, NamedTuple

from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

from reference_families import common as C

FAMILY = "schemas"
OWNER = "aew.schemas"
REGISTRY = f"{OWNER}:SCHEMAS"
# Data kept beside the schemas, not a schema: the directory holds it and the registry does not.
DATA_FILES = ("ticket-field-registry.v1.json",)
# The keywords of a schema node, each classified (a keyword in none of these is an unresolved item, so a new one is
# seen).
WALKED = frozenset({"properties", "patternProperties", "additionalProperties", "items", "prefixItems", "allOf", "oneOf",
                    "anyOf", "then", "else", "$ref", "required", "$defs", "definitions"})
CONSTRAINTS = frozenset({"type", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                         "multipleOf", "minLength", "maxLength", "pattern", "format", "minItems", "maxItems",
                         "uniqueItems", "minProperties", "maxProperties", "propertyNames", "not", "if",
                         "dependentRequired", "minContains", "maxContains", "contentMediaType", "contentEncoding"})
ANNOTATIONS = frozenset({"title", "description", "default", "examples", "deprecated", "readOnly", "writeOnly",
                         "$schema", "$id", "$comment", "$anchor"})  # and every ``x-...`` keyword
UNWALKED = frozenset({"contains", "dependentSchemas", "dependencies", "unevaluatedProperties", "unevaluatedItems",
                      "additionalItems", "contentSchema", "$dynamicRef", "$recursiveRef", "$dynamicAnchor"})
_TESTS = "tests/integration/test_reference_interfaces.py"
TESTS = (
    f"{_TESTS}::test_the_schema_records_are_the_registry_and_the_directory_both_ways",
    f"{_TESTS}::test_every_registered_schema_flattens_with_its_unresolved_items_named",
)


class Flat(NamedTuple):
    # path -> its types, ``|``-joined and sorted; "" when the schema gives the path none (it is neither under
    # ``properties`` nor typed by an ``additionalProperties`` or matching ``patternProperties`` schema)
    properties: dict[str, str]
    required: list[str]
    unresolved: list[str]  # why, one per distinct item


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _type_of(node: dict[str, Any]) -> str:
    kind = node.get("type")
    if isinstance(kind, list):
        return "|".join(sorted(str(k) for k in kind))
    if isinstance(kind, str):
        return kind
    if "const" in node:
        return "const"
    if "enum" in node:
        return "enum"
    return ""


class _Walk:
    def __init__(self, registry: Registry, base: str) -> None:
        self.resolver = registry.resolver(base_uri=base)
        self.types: dict[str, set[str]] = {}
        self.required: set[str] = set()
        self.unresolved: set[str] = set()

    def visit(self, node: Any, path: str, resolver: Any, stack: list[Any], conditional: bool) -> None:
        if not isinstance(node, dict):
            return  # a boolean schema names no path
        where = path or "the root"
        for key in node:
            if key in UNWALKED:
                self.unresolved.add(f"{key} is used at {where} and this reading does not walk it")
            elif key not in WALKED | CONSTRAINTS | ANNOTATIONS and not key.startswith("x-"):
                self.unresolved.add(f"the keyword {key} at {where} is not one this reading has classified")
        if isinstance(node.get("items"), list):
            self.unresolved.add(f"items is a list at {where}, which this reading does not walk")
        if "$ref" in node:
            try:
                resolved = resolver.lookup(node["$ref"])
            except Unresolvable:
                self.unresolved.add(f"the reference {node['$ref']} at {path or 'the root'} does not resolve")
            else:
                if any(resolved.contents is seen for seen in stack):
                    self.unresolved.add(f"the reference {node['$ref']} at {path or 'the root'} recurses; it is cut at "
                                        "its second visit")
                else:
                    self.visit(resolved.contents, path, resolved.resolver, [*stack, resolved.contents], conditional)
        if path:
            self.types.setdefault(path, set())
            kind = _type_of(node)
            if kind:
                self.types[path].add(kind)
        if not conditional:
            self.required.update(_join(path, str(k)) for k in node.get("required", []) if isinstance(k, str))
        for key, sub in (node.get("properties") or {}).items():
            self.visit(sub, _join(path, key), resolver, stack, conditional)
        for key, sub in (node.get("patternProperties") or {}).items():
            self.visit(sub, _join(path, f"<{key}>"), resolver, stack, conditional)
        if isinstance(node.get("additionalProperties"), dict):
            self.visit(node["additionalProperties"], _join(path, "*"), resolver, stack, conditional)
        if not conditional:  # a required key nothing declares takes the type its object's schemas give any such key
            declared = node.get("properties") or {}
            for key in (k for k in node.get("required", []) if isinstance(k, str) and k not in declared):
                self.type_undeclared(node, _join(path, key), key, resolver, stack)
        if isinstance(node.get("items"), dict):
            self.visit(node["items"], f"{path}[]", resolver, stack, conditional)
        for i, sub in enumerate(node.get("prefixItems") or []):
            self.visit(sub, f"{path}[{i}]", resolver, stack, conditional)
        for key in ("allOf",):
            for sub in node.get(key) or []:
                self.visit(sub, path, resolver, stack, conditional)
        for key in ("oneOf", "anyOf"):
            for sub in node.get(key) or []:
                self.visit(sub, path, resolver, stack, True)
        for key in ("then", "else"):
            if key in node:
                self.visit(node[key], path, resolver, stack, True)

    def type_undeclared(self, node: dict[str, Any], child: str, key: str, resolver: Any, stack: list[Any]) -> None:
        """Type a required key that ``properties`` does not declare, as a validator would: by each ``patternProperties``
        schema whose pattern the key matches, else by the ``additionalProperties`` schema."""
        matched = False
        for pattern, sub in (node.get("patternProperties") or {}).items():
            try:
                hit = re.search(pattern, key) is not None
            except re.error:
                self.unresolved.add(f"the pattern {pattern} at {child} cannot be read")
                continue
            if hit:
                matched = True
                self.visit(sub, child, resolver, stack, False)
        if not matched and isinstance(node.get("additionalProperties"), dict):
            self.visit(node["additionalProperties"], child, resolver, stack, False)


def flatten(schema: dict[str, Any], registry: Registry, name: str = "schema") -> Flat:
    """The flattened paths of one schema, resolving its references through ``registry``."""
    base = str(schema["$id"]) if "$id" in schema else f"urn:aew:flatten:{name}"
    if "$id" not in schema:  # not registered by the validator's registry (no ``$id``): registered here, under a name
        registry = registry.with_resource(base, Resource.from_contents(schema, default_specification=DRAFT202012))
    walk = _Walk(registry, base)
    walk.visit(schema, "", walk.resolver, [schema], False)
    for path in walk.required:  # a key an object requires is a path of the schema even when nothing declares it
        walk.types.setdefault(path, set())
    return Flat({p: "|".join(sorted(t)) for p, t in sorted(walk.types.items())}, sorted(walk.required),
                sorted(walk.unresolved))


def registered(ctx: C.Context) -> tuple[dict[str, str], list[str]]:
    """(the registry's name -> file, the ``*.schema.json`` files in the directory the registry's files are in)."""
    import aew.schemas as schemas

    directory = ctx.src / "aew" / "schemas"
    return dict(schemas.SCHEMAS), sorted(p.name for p in directory.glob("*.schema.json"))


def build(ctx: C.Context) -> list[C.Record]:
    import aew.schemas as schemas

    names, files = registered(ctx)
    registry = schemas._registry()  # the validator's own: the schemas that refer to one another by $id
    by_file = {file: name for name, file in names.items()}
    records: list[C.Record] = []
    directory = ctx.src / "aew" / "schemas"
    for file in sorted(set(files) | set(by_file)):
        name = by_file.get(file, file.removesuffix(".schema.json"))
        path = directory / file
        problems: list[dict[str, Any]] = []
        if file not in by_file:
            problems.append(C.unresolved_item(OWNER, "SCHEMAS", f"{file} is in the directory and registered nowhere"))
        if file not in files:
            problems.append(C.unresolved_item(OWNER, "SCHEMAS", f"{name} is registered and its file {file} is missing"))
        fact: dict[str, Any] = {"name": name, "file": file, "registered": file in by_file}
        fact_coverage: dict[str, dict[str, Any]] = {}
        if path.is_file():
            doc = _load(path)
            flat = flatten(doc, registry, name)
            fact.update(id=doc.get("$id"), properties=flat.properties, required=flat.required)
            items = [C.unresolved_item(OWNER, name, why) for why in flat.unresolved]
            cov = C.lower_bound(items) if items else C.complete(REGISTRY, TESTS)
            fact_coverage = {"properties": cov, "required": cov}
        records.append(C.Record(FAMILY, name, OWNER, "SCHEMAS", "enumerated",
                                C.lower_bound(problems) if problems else C.complete(REGISTRY, TESTS), fact,
                                fact_coverage=fact_coverage or None))
    return records


def _load(path: Path) -> dict[str, Any]:
    return json.loads(C.read_source(path))
