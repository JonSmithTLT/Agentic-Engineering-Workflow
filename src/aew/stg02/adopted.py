"""The adopted STG-01 v0.5.4 machine files the slice serves, vendored byte-exact from the sealed ZIP.

The operator adopted the sealed ``STG-01-v0.5.4.zip`` (SHA-256 :data:`SEALED_ZIP_SHA256`) on 2026-10-19: the D-01
0.3.4 read wire, the O-01 0.2 command wire, the selection profile and the owner pins are normative; the oracle is not.
This package carries only the machine-readable files its code checks against, each pinned here to the ZIP's own
``SHA256SUMS`` line. A file that no longer matches its pin is refused at load: the server never runs against an edited
contract. Where these files and the slice's code disagree, the files govern.
"""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

SEALED_ZIP_SHA256 = "64e65578e9774fd9425c19ceaff30f1a0018ae819baa58d9469ed0c33e8f299f"
HERE = Path(__file__).resolve().parent / "adopted"
# file name -> (its path inside the sealed ZIP, its SHA-256 from the ZIP's SHA256SUMS)
PINS: dict[str, tuple[str, str]] = {
    "aew-d01-read-v0.3.4-FULL.schema.json": (
        "02-WIRE/aew-d01-read-v0.3.4-FULL.schema.json",
        "50bd04a0e8f10fe70bc43ffebca8a0b3b0e08872b339030d6d8dfebee180ebba"),
    "o01-extended-command.schema.json": (
        "02-WIRE/o01-extended-command.schema.json",
        "17f28b3f312bf3cb5f9f134803f68909aef1f49827c655c40deef85556c35f09"),
    "extended-action-registry.json": (
        "02-WIRE/extended-action-registry.json",
        "fbc95cf6ed57263bed8a94a00922c13180341f470161975d1833f0cff5cdc210"),
    "new-command-refusal-reasons.json": (
        "05-INTEGRATED-FIXTURES/new-command-refusal-reasons.json",
        "d54ab0ffd6bd1b40ff7d32b3233e097086069f77152fe6010e67a9e1485c219e"),
    "command-set-problems.json": (
        "05-INTEGRATED-FIXTURES/command-set-problems.json",
        "166f9e409c836fce66ff36d335ba476635f3b13a9bc218bad32a539b51d2d74e"),
    "http-problem-matrix.json": (
        "05-INTEGRATED-FIXTURES/http-problem-matrix.json",
        "3e0f5b7948f35cfd72eba12005f4e571937c7601817347271ab04b2d8930ea87"),
    # the O-01 Problem and OwnerOperationRead are defined only here, not in the standalone command schema
    "openapi-o01-extended-REVIEW-CANDIDATE.yaml": (
        "02-WIRE/openapi-o01-extended-REVIEW-CANDIDATE.yaml",
        "30fe2fc2f557bab49561c3134a568f13b9363aedbfc2dcd6162f3dd0132079e4"),
}


class AdoptedFileChanged(RuntimeError):
    """A vendored adopted file no longer matches its sealed pin."""


@cache
def load(name: str) -> Any:
    raw = (HERE / name).read_bytes()
    want = PINS[name][1]
    if hashlib.sha256(raw).hexdigest() != want:
        raise AdoptedFileChanged(f"{name} does not match its sealed v0.5.4 pin {want}")
    if name.endswith(".yaml"):
        return yaml.safe_load(raw.decode("utf-8"))
    return json.loads(raw.decode("utf-8"))


def registry() -> dict[str, dict[str, Any]]:
    return {r["action"]: r for r in load("extended-action-registry.json")}


def refusals() -> dict[str, dict[str, str]]:
    return load("new-command-refusal-reasons.json")


def set_problems() -> dict[str, dict[str, Any]]:
    return load("command-set-problems.json")


def matrix() -> list[dict[str, Any]]:
    return load("http-problem-matrix.json")["rows"]


@cache
def _validator(schema_file: str, ref: str) -> Draft202012Validator:
    doc = load(schema_file)
    return Draft202012Validator({"$defs": doc["$defs"], "$ref": f"#/$defs/{ref}"}, format_checker=FormatChecker())


def d01_errors(ref: str, body: Any) -> list[str]:
    """Schema errors of a D-01 body against one of the 0.3.4 definitions (``ReadWaiting``, ``Problem``...)."""
    v = _validator("aew-d01-read-v0.3.4-FULL.schema.json", ref)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in v.iter_errors(body)]


def o01_errors(ref: str, body: Any) -> list[str]:
    """Schema errors of an O-01 body against one of the 0.2 definitions (``CommandSet``, ``Receipt``...)."""
    v = _validator("o01-extended-command.schema.json", ref)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in v.iter_errors(body)]


@cache
def _openapi_validator(ref: str) -> Draft202012Validator:
    doc = load("openapi-o01-extended-REVIEW-CANDIDATE.yaml")
    return Draft202012Validator({"components": doc["components"], "$ref": f"#/components/schemas/{ref}"},
                                format_checker=FormatChecker())


def o01_openapi_errors(ref: str, body: Any) -> list[str]:
    """Schema errors against the O-01 OpenAPI components: ``Problem`` and ``OwnerOperationRead`` live only there."""
    v = _openapi_validator(ref)
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in v.iter_errors(body)]
