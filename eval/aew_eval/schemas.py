"""Validation against the instrument's own schemas (``aew_eval/schema/``)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent / "schema"
FILES = {"aew/eval-case/v1": "case.schema.json", "aew/eval-prereg/v1": "preregistration.schema.json",
         "aew/eval-attempt/v1": "attempt.schema.json", "aew/eval-run/v1": "eval-run.schema.json"}


class Invalid(ValueError):
    """A record that does not satisfy its schema, or the instrument's own rules."""


@cache
def _validator(schema_id: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / FILES[schema_id]).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate(schema_id: str, record: Any, *, what: str = "record") -> None:
    errors = sorted(_validator(schema_id).iter_errors(record), key=lambda e: list(e.absolute_path))
    if errors:
        detail = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message}" for e in errors[:5])
        raise Invalid(f"{what} is not a valid {schema_id}: {detail}")
