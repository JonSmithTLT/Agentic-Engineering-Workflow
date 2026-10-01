"""Versioned JSON Schemas for AEW durable artifacts (KC §23: small schemas, not one giant one)."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

from jsonschema import Draft202012Validator

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
}


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    text = resources.files(__package__).joinpath(SCHEMAS[name]).read_text(encoding="utf-8")
    schema = json.loads(text)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate(name: str, instance: Any, *, source: str) -> None:
    """Raise ValidationFailed listing every schema violation with its location."""
    _raise(_validator(name), instance, f"{source}: does not match schema {name}")


@lru_cache(maxsize=None)
def _property_validator(name: str, prop: str) -> Draft202012Validator:
    schema = _validator(name).schema
    return Draft202012Validator({**schema["properties"][prop], "$defs": schema.get("$defs", {})})


def validate_property(name: str, prop: str, instance: Any, *, source: str) -> None:
    """Validate one top-level property of a schema on its own: a submitted section, before the engine uses it
    (M3 step 8: a malformed but parseable section must be refused, never crash the code that reads it)."""
    _raise(_property_validator(name, prop), instance, f"{source}: `{prop}` does not match schema {name}", prop)


def _raise(validator: Draft202012Validator, instance: Any, message: str, prefix: str | None = None) -> None:
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(map(str, [p for p in (prefix,) if p] + list(e.absolute_path))) or '<root>'}: {e.message}"
                 for e in errors[:20]]
        raise ValidationFailed(message, violations=lines)
