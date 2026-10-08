"""Versioned JSON Schemas for AEW durable artifacts (KC §23: small schemas, not one giant one)."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any, cast

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from aew.errors import ValidationFailed

SCHEMAS = {
    "control": "control.schema.json",
    "project": "project.schema.json",
    "work-unit": "work-unit.schema.json",
    "plan": "plan.schema.json",
    "decision": "decision.schema.json",
    "evidence": "evidence.schema.json",
    "guardrails": "guardrails.schema.json",
    "checks": "checks.schema.json",
    "gates": "gates.schema.json",
    "execution": "execution.schema.json",
    "role": "role.schema.json",
    "role-archetype": "role-archetype.schema.json",
    "history": "history.schema.json",
    "transition": "transition.schema.json",
    "transition-events": "transition-events.schema.json",
    "transition-segment": "transition-segment.schema.json",
    "surface": "surface.schema.json",  # the typed Lead surface's result contract (F15.1)
    "codebase-map": "codebase-map.schema.json",  # project maps (F22.1, ADR-0015)
    "map-registry": "map-registry.schema.json",
}


def _load(name: str) -> dict[str, Any]:
    return json.loads(resources.files(__name__).joinpath(SCHEMAS[name]).read_text(encoding="utf-8"))


@cache
def _registry() -> Registry:
    """Schemas other schemas refer to by ``$id`` (the control state's ``last_transition`` is a transition record)."""
    return Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in (_load(n) for n in SCHEMAS)
        if "$id" in schema)


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = _load(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=_registry())


def validate(name: str, instance: Any, *, source: str) -> None:
    """Raise ValidationFailed listing every schema violation with its location."""
    _raise(_validator(name), instance, f"{source}: does not match schema {name}")


@cache
def _property_validator(name: str, prop: str) -> Draft202012Validator:
    schema = cast(dict[str, Any], _validator(name).schema)
    return Draft202012Validator({**schema["properties"][prop], "$defs": schema.get("$defs", {})},
                                registry=_registry())


def validate_property(name: str, prop: str, instance: Any, *, source: str) -> None:
    """Validate one top-level property of a schema on its own: a submitted section, before the engine uses it
    (M3 step 8: a malformed but parseable section must be refused, never crash the code that reads it)."""
    _raise(_property_validator(name, prop), instance, f"{source}: `{prop}` does not match schema {name}", prop)


@cache
def _def_validator(name: str, definition: str) -> Draft202012Validator:
    schema = cast(dict[str, Any], _validator(name).schema)
    return Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}, registry=_registry())


def validate_def(name: str, definition: str, instance: Any, *, source: str) -> None:
    """Validate against one ``$defs`` entry of a schema (a history entry or root, apart from its file)."""
    _raise(_def_validator(name, definition), instance, f"{source}: does not match {name}#{definition}")


def _raise(validator: Draft202012Validator, instance: Any, message: str, prefix: str | None = None) -> None:
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(map(str, [p for p in (prefix,) if p] + list(e.absolute_path))) or '<root>'}: {e.message}"
                 for e in errors[:20]]
        raise ValidationFailed(message, violations=lines)
