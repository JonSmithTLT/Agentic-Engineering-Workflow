"""The G3 wire and the adopted O-01 facts the service derives, each from its one owner.

The wire is A-26's ``g3-wire.schema.json`` (``g3-0.6.1-candidate``), still normative under A-37 (G3 revision 7.1):
vendored byte-exact here and refused at load if it no longer matches its adopted SHA-256. The O-01 0.2 command schema,
the action registry and SW-02's canonical bytes and set digest are not copied: they come from ``aew.stg02``, which
vendors the sealed STG-01 v0.5.4 files under their own pins.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from aew.stg02 import adopted as o01
from aew.stg02.wire import canonical, set_digest

__all__ = ["HEADER", "STATUS", "WIRE", "canonical", "o01_errors", "problem", "registry", "schema", "set_digest",
           "wire_errors"]

SCHEMA_FILE = Path(__file__).resolve().parent / "g3-wire.schema.json"
# A-37's adoption record: the wire stays A-26's, at these bytes.
SCHEMA_SHA256 = "62b67dcab151f454a4af0c8f48e301299af8a90e009a1e70be81cba51f6c5e1c"
HEADER = "X-AEW-G3-Wire"
PROTECTED = "PROTECTED_G3"


class WireChanged(RuntimeError):
    """The vendored wire no longer matches its adopted pin."""


@cache
def schema() -> dict[str, Any]:
    raw = SCHEMA_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SCHEMA_SHA256:
        raise WireChanged(f"{SCHEMA_FILE.name} does not match its adopted pin {SCHEMA_SHA256}")
    return json.loads(raw.decode("utf-8"))


WIRE: str = schema()["$defs"]["Wire"]["const"]

# A-37's Interfaces table: the HTTP status each Problem code is sent with. Its codes and statuses are the wire's
# Problem enums exactly (tests/unit/test_g3_facts.py).
STATUS: dict[str, int] = {
    "STRUCTURAL": 400, "MIXED_AUTHORITY_SET_UNSELECTED": 400, "MEMBER_PROOF_INVALID": 400,
    "PEER_NOT_PERMITTED": 403,
    "NOT_FOUND": 404,
    "APPROVAL_EXPIRED": 409,
    "RENDERING_UNDERIVED": 422, "RENDERING_INCOMPLETE": 422, "PIN_INCORRECT": 422,
    "PIN_LOCKED": 423,
    "G3_UNAVAILABLE": 503,
}


def problem(code: str) -> tuple[int, dict[str, Any]]:
    return STATUS[code], {"wire_version": WIRE, "status": STATUS[code], "code": code}


@cache
def _validator(ref: str) -> Draft202012Validator:
    return Draft202012Validator({"$defs": schema()["$defs"], "$ref": f"#/$defs/{ref}"}, format_checker=FormatChecker())


def wire_errors(ref: str, body: Any) -> list[str]:
    """Schema errors of a body against one of the wire's definitions (``ApprovalRequest``, ``ConsentRecord``...)."""
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in _validator(ref).iter_errors(body)]


def o01_errors(body: Any) -> list[str]:
    """Schema errors of a command set against the sealed O-01 0.2 ``CommandSet`` (G3-02 step 1)."""
    return o01.o01_errors("CommandSet", body)


def registry() -> dict[str, dict[str, Any]]:
    """The adopted action registry: each action's ``origin`` and ``sole_admitting_owner``."""
    return o01.registry()


def o01_schema() -> dict[str, Any]:
    return o01.load("o01-extended-command.schema.json")
