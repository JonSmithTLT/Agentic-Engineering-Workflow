"""What G3 reads beyond the sealed STG-01 v0.5.4 files: the sealed registry and O-01 schema, plus AEW's own overlay.

The sealed files are byte-pinned (:mod:`aew.stg02.adopted`), so a protected action that has a real owner today cannot be
added to them. The overlay carries A-39's ``SET_STEERING_MODE`` forward from ``docs/contracts/A-43/``, a test pinning
the equality, with one difference: the owner label is ``ADC``, because the pinned G3 wire allows only four owners and
A-43's ``R01`` is not one of them. It is a bridge until O-01 convergence folds it in (the designer's ruling on G3-C's PR
C3; the operator, 2026-11-08: "option 1 makes the most sense").

**Who reads what.** The G3 service and the G3 client's set checks read this module. ``adopted``'s accessors and the
carrier (``stg02.commands``) stay sealed only, so an O-01 set naming an overlay action fails the carrier's set check
before any consume, and burns no consent.
"""

from __future__ import annotations

import copy
import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from aew.stg02 import adopted as A

FILE = Path(__file__).resolve().parent / "overlay" / "set-steering-mode.json"
SCHEMA = "o01-extended-command.schema.json"


class OverlayCollision(RuntimeError):
    """An overlay row names something the sealed files already define: the overlay never changes a sealed fact."""


@cache
def _document() -> dict[str, Any]:
    doc = json.loads(FILE.read_text(encoding="utf-8"))
    return check(doc, A.registry(), A.load(SCHEMA))


def check(doc: dict[str, Any], sealed_registry: dict[str, Any], sealed_schema: dict[str, Any]) -> dict[str, Any]:
    """``doc``, or refused when any of its rows collides with a sealed action or definition."""
    for row in doc["rows"]:
        action = row["action"]
        if action in sealed_registry:
            raise OverlayCollision(f"the overlay's {action} is a sealed action: the overlay only adds")
    for name in doc["definitions"]:
        if name in sealed_schema["$defs"]:
            raise OverlayCollision(f"the overlay's {name} is a sealed definition: the overlay only adds")
    return doc


@cache
def _registry() -> dict[str, dict[str, Any]]:
    return {**A.registry(), **{row["action"]: row for row in _document()["rows"]}}


def registry() -> dict[str, dict[str, Any]]:
    """The sealed action registry plus the overlay's rows."""
    return copy.deepcopy(_registry())


@cache
def _schema() -> dict[str, Any]:
    doc = _document()
    out = copy.deepcopy(A.load(SCHEMA))
    intent = out["$defs"]["Intent"]
    intent["properties"]["action"]["enum"] = [*intent["properties"]["action"]["enum"],
                                              *(row["action"] for row in doc["rows"])]
    intent["allOf"] = [*intent["allOf"], *copy.deepcopy(doc["branches"])]
    out["$defs"].update(copy.deepcopy(doc["definitions"]))
    return out


def o01_schema() -> dict[str, Any]:
    """The sealed O-01 0.2 command schema plus the overlay's actions."""
    return copy.deepcopy(_schema())


@cache
def _validator(ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$defs": _schema()["$defs"], "$ref": f"#/$defs/{ref}"}, format_checker=FormatChecker())


def o01_errors(ref: str, body: Any) -> list[str]:
    """Schema errors of a body against the sealed schema plus the overlay (as ``adopted.o01_errors``)."""
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in _validator(ref).iter_errors(body)]
