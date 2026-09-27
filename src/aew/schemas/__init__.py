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
    errors = sorted(_validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    if errors:
        lines = [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors[:20]]
        raise ValidationFailed(f"{source}: does not match schema {name}", violations=lines)
