"""The dashboard contract as data: load the accepted OpenAPI document, hash it, and compile its response schemas into
``jsonschema`` validators (register F20.2: every response is validated against the contract in the tests).

The contract's schema objects are JSON Schema 2020-12 (OpenAPI 3.1); the ``x-`` extension keywords are ignored by the
validator, as the specification says they must be. A ``$ref`` of the form ``#/components/schemas/<Name>`` is resolved
against the whole document, so each validator's root is the document itself with the wanted schema at its top.

**Versions and compatibility (register F20.8; the maps and history search change note,
``docs/design/proposals/dashboard-maps-and-history-search-v0.1.md``).** The accepted contract may be any ``0.1.x`` at
or above ``0.1.2`` (:data:`CONTRACT_SERIES`): a rule, not a list, so the web developer's next minor version needs no
edit here. A minor version only adds; what it may not change is decided by :func:`compatibility`, one element-wise
check used for every comparison (the new contract against 0.1.2, the packaged build's contract against the accepted
one, and a later minor version against the adopted one).
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

CONTRACT_REL = "docs/design/dashboard-api-v1-provisional.yaml"
APPROVAL_REL = "web/docs/c0-approval.json"
# The accepted contract's version must be a 0.1.x at or above BASE_VERSION, compared as integers (0.1.10 > 0.1.2).
# A 0.2.0 is refused on purpose: it is the version for a breaking change, which needs this module and the packaged
# build to move together.
CONTRACT_SERIES = "0.1"
BASE_VERSION = "0.1.2"
ACCEPT = "ACCEPT"
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

# Route -> the response schema its 200 body must match (the names are the contract's).
RESPONSE_SCHEMAS: dict[str, str] = {
    "/project": "ProjectResponse",
    "/capabilities": "CapabilitiesResponse",
    "/overview": "OverviewResponse",
    "/history/integrity": "IntegrityResponse",
    "/work": "WorkListResponse",
    "/work/{id}": "WorkResponse",
    "/runs": "InvocationListResponse",
    "/runs/{id}": "InvocationResponse",
    "/evidence": "EvidenceListResponse",
    "/evidence/{id}": "EvidenceResponse",
    "/knowledge": "KnowledgeListResponse",
    "/knowledge/{id}": "KnowledgeResponse",
    "/history": "HistoryListResponse",
    "/history/{id}": "HistoryResponse",
    "/attention": "AttentionListResponse",
    "/activity": "ActivityListResponse",
}
ERROR_SCHEMA = "Error"
METHODS = ("get", "head")
# The one exception to "a covered response schema stays equal": Capabilities may gain keys that are exactly a
# Capability, which its ``additionalProperties`` already admits (a deployed client parses them as a record).
CAPABILITIES_REF = "#/components/schemas/Capabilities"
CAPABILITY_REF = "#/components/schemas/Capability"
# Mappings whose keys are names, not keywords: a property called ``description`` is a field, never stripped.
NAME_MAPS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Contract:
    """The loaded contract and its compiled validators."""

    def __init__(self, path: Path | None = None, *, raw: bytes | None = None) -> None:
        if raw is None:
            if path is None:
                raise ValueError("a contract needs a path or its bytes")
            raw = path.read_bytes()
        self.path = path
        self.sha256 = hashlib.sha256(raw).hexdigest()
        self.document: dict[str, Any] = yaml.safe_load(raw.decode("utf-8"))
        self.version: str = str(self.document["info"]["version"])
        self.schemas: dict[str, Any] = self.document["components"]["schemas"]
        self.paths: dict[str, Any] = self.document["paths"]
        self._validators: dict[str, Draft202012Validator] = {}

    def validator(self, name: str) -> Draft202012Validator:
        if name not in self._validators:
            if name not in self.schemas:
                raise KeyError(f"the contract has no schema {name!r}")
            root = {"$ref": f"#/components/schemas/{name}", "components": {"schemas": self.schemas}}
            Draft202012Validator.check_schema(root)
            self._validators[name] = Draft202012Validator(root)
        return self._validators[name]

    def violations(self, name: str, instance: Any) -> list[str]:
        """Every way ``instance`` fails schema ``name``, as ``path: message`` lines; empty when it conforms."""
        errors = sorted(self.validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
        return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]

    def response_schema(self, route: str) -> str:
        """The schema a route's 200 body must match (``route`` as the contract spells it, ``{id}`` included)."""
        return RESPONSE_SCHEMAS[route]

    def envelope_version(self, schema: str) -> str | None:
        """The ``schema_version`` const of a response schema: the contract version that defined that response."""
        const = ((self.schemas[schema].get("properties") or {}).get("schema_version") or {}).get("const")
        return None if const is None else str(const)

    def query_parameters(self, route: str) -> dict[str, dict[str, Any]]:
        """The query parameters the contract declares for a route's GET, by name."""
        out = {}
        for param in self.paths[route]["get"].get("parameters", []):
            if param.get("in") == "query":
                out[param["name"]] = param
        return out


@cache
def load(path: str) -> Contract:
    return Contract(Path(path))


# ---------------------------------------------------------------------------------------------- versions


def parse_version(text: str) -> tuple[int, int, int]:
    """``major.minor.patch`` as integers; anything else (``0.1.x``, ``v0.1.2``, ``0.1``) is a ``ValueError``."""
    m = VERSION_RE.fullmatch(str(text))  # `$` with match would accept a trailing newline
    if not m:
        raise ValueError(f"{text!r} is not a contract version (three non-negative integers)")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def in_series(version: str) -> bool:
    """Whether this server accepts ``version`` as its contract: a ``0.1.x`` at or above ``0.1.2``."""
    try:
        parsed = parse_version(version)
    except ValueError:
        return False
    series = tuple(int(p) for p in CONTRACT_SERIES.split("."))
    return parsed[:2] == series and parsed >= parse_version(BASE_VERSION)


def accepted_reviews(approval: dict[str, Any]) -> list[dict[str, Any]]:
    """Every contract the approval record accepts: the current one (when ``ACCEPTED``) and each predecessor whose
    ``previous_reviews`` entry has ``"disposition": "ACCEPT"`` (an amended or conditional review is not one)."""
    out = []
    if approval.get("status") == "ACCEPTED" and approval.get("disposition") == ACCEPT:
        out.append(approval)
    out += [r for r in approval.get("previous_reviews") or [] if r.get("disposition") == ACCEPT]
    return out


def base_review(approval: dict[str, Any]) -> dict[str, Any]:
    """The accepted review of :data:`BASE_VERSION`, whose ``reviewed_commit`` holds the contract every later minor
    version is compared with."""
    found = [r for r in accepted_reviews(approval) if r.get("contract_version") == BASE_VERSION]
    if len(found) != 1:
        raise ValueError(f"the approval record must accept contract {BASE_VERSION} exactly once, as the current "
                         f"review or as a previous review with disposition {ACCEPT}")
    return found[0]


# ---------------------------------------------------------------------------------------------- compatibility


def normalized(node: Any, *, names: bool = False) -> Any:
    """``node`` with every ``description`` and ``x-`` key removed, at any depth; the keys of a name mapping
    (``properties`` and its kin) are names, so they are kept and only their values are normalized."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if not names and (key == "description" or str(key).startswith("x-")):
                continue
            out[key] = normalized(value, names=not names and key in NAME_MAPS)
        return out
    if isinstance(node, list):
        return [normalized(v) for v in node]
    return node


def _refs(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"]} if isinstance(node.get("$ref"), str) else set()
        for value in node.values():
            found |= _refs(value)
        return found
    if isinstance(node, list):
        return set().union(*(_refs(v) for v in node)) if node else set()
    return set()


def _resolve(document: dict[str, Any], ref: str) -> Any:
    if not ref.startswith("#/"):
        raise KeyError(ref)
    node: Any = document
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def _parameters(document: dict[str, Any], path_item: dict[str, Any], operation: dict[str, Any]) -> dict[
        tuple[str, str], Any]:
    """An operation's parameters by ``(in, name)``: the path item's, overridden by the operation's own."""
    out: dict[tuple[str, str], Any] = {}
    for param in [*(path_item.get("parameters") or []), *(operation.get("parameters") or [])]:
        target = _resolve(document, param["$ref"]) if "$ref" in param else param
        out[(str(target.get("in")), str(target.get("name")))] = param
    return out


def _component_problem(ref: str, old: Any, new: Any) -> str | None:
    a, b = normalized(old), normalized(new)
    if ref == CAPABILITIES_REF and isinstance(a, dict) and isinstance(b, dict):
        old_keys = set(a.get("properties") or {})
        gained = {k: v for k, v in (b.get("properties") or {}).items() if k not in old_keys}
        if all(v == {"$ref": CAPABILITY_REF} for v in gained.values()):
            b = {**b, "properties": {k: v for k, v in (b.get("properties") or {}).items() if k in old_keys}}
    return None if a == b else f"{ref} changed"


def compatibility(old: dict[str, Any], new: dict[str, Any], covered: Iterable[str]) -> list[str]:
    """Why ``new`` breaks a client of ``old`` on the ``covered`` paths; empty when it does not (the change note's
    compatibility check, element by element):

    * each covered path is in ``new`` and keeps every method (``get``, ``head``) it had;
    * each covered operation's ``responses`` and ``security``, and every component reachable from them or from its
      parameters through ``$ref``, are equal once ``description`` and ``x-`` keys are removed, except that
      ``Capabilities`` may gain properties that are exactly ``$ref: Capability``. A new optional property, a new enum
      value or a changed bound is a difference: every response object is closed, and the client parses strictly;
    * every old parameter is present and equal, and a new one is optional.

    Paths outside ``covered``, and components reachable only from them, are never compared.
    """
    problems: list[str] = []
    reachable: set[str] = set()
    paths = sorted(covered)
    for key in ("servers", "security"):  # what every request is sent to and authenticated with
        if paths and normalized(old.get(key)) != normalized(new.get(key)):
            problems.append(f"the contract's {key} changed")
    for path in paths:
        old_item = old["paths"].get(path)
        if old_item is None:
            problems.append(f"{path}: not a path of the old contract, so it cannot be covered")
            continue
        new_item = new["paths"].get(path)
        if new_item is None:
            problems.append(f"{path}: removed")
            continue
        for method in METHODS:
            if method not in old_item:
                continue
            if method not in new_item:
                problems.append(f"{path}: {method.upper()} removed")
                continue
            before, after = old_item[method], new_item[method]
            for key in ("responses", "security"):
                if normalized(before.get(key)) != normalized(after.get(key)):
                    problems.append(f"{path} {method.upper()}: {key} changed")
                reachable |= _refs(before.get(key))
            old_params = _parameters(old, old_item, before)
            new_params = _parameters(new, new_item, after)
            for key, param in sorted(old_params.items()):
                if key not in new_params:
                    problems.append(f"{path} {method.upper()}: parameter {key[1]} ({key[0]}) removed")
                elif normalized(param) != normalized(new_params[key]):
                    problems.append(f"{path} {method.upper()}: parameter {key[1]} ({key[0]}) changed")
                reachable |= _refs(param)
            for key, param in sorted(new_params.items()):
                target = _resolve(new, param["$ref"]) if "$ref" in param else param
                if key not in old_params and target.get("required"):
                    problems.append(f"{path} {method.upper()}: new parameter {key[1]} ({key[0]}) is required")
    seen: set[str] = set()
    while reachable - seen:
        ref = min(reachable - seen)
        seen.add(ref)
        try:
            before = _resolve(old, ref)
        except (KeyError, TypeError):
            problems.append(f"{ref}: does not resolve in the old contract")
            continue
        try:
            after = _resolve(new, ref)
        except (KeyError, TypeError):
            problems.append(f"{ref}: removed")
            continue
        problem = _component_problem(ref, before, after)
        if problem:
            problems.append(problem)
        reachable |= _refs(before)
    return problems


def compile_problems(document: dict[str, Any]) -> list[str]:
    """Every component schema and parameter schema of ``document`` that is not valid JSON Schema 2020-12."""
    problems = []
    schemas = document.get("components", {}).get("schemas", {})
    for name in sorted(schemas):
        root = {"$ref": f"#/components/schemas/{name}", "components": {"schemas": schemas}}
        try:
            Draft202012Validator.check_schema(root)
        except Exception as exc:  # noqa: BLE001 (any failure to compile is the finding)
            problems.append(f"#/components/schemas/{name}: {type(exc).__name__}: {str(exc).splitlines()[0]}")
    for ref in sorted(_refs(document.get("paths")) | _refs(document.get("components"))):
        try:
            _resolve(document, ref)
        except (KeyError, TypeError):
            problems.append(f"{ref}: does not resolve")
    for path, item in sorted(document.get("paths", {}).items()):
        for method in METHODS:
            for (where, name), param in _parameters(document, item, item.get(method) or {}).items():
                target = _resolve(document, param["$ref"]) if "$ref" in param else param
                root = {**target.get("schema", {}), "components": {"schemas": schemas}}
                try:
                    Draft202012Validator.check_schema(root)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{path} {method.upper()} parameter {name} ({where}): {exc}")
    return problems


def merged(base: dict[str, Any], *additions: dict[str, Any]) -> dict[str, Any]:
    """``base`` with each addition merged in, in order: mappings merge key by key, anything else replaces. This is
    how the change note's appendix applies to the 0.1.2 contract."""

    def into(target: dict[str, Any], extra: dict[str, Any]) -> None:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                into(target[key], value)
            else:
                target[key] = copy.deepcopy(value)

    out = copy.deepcopy(base)
    for addition in additions:
        into(out, addition)
    return out
