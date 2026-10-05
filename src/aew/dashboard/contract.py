"""Contract 0.1.2 as data: load the accepted OpenAPI document, hash it, and compile its response schemas into
``jsonschema`` validators (register F20.2: every response is validated against the contract in the tests).

The contract's schema objects are JSON Schema 2020-12 (OpenAPI 3.1); the ``x-`` extension keywords are ignored by the
validator, as the specification says they must be. A ``$ref`` of the form ``#/components/schemas/<Name>`` is resolved
against the whole document, so each validator's root is the document itself with the wanted schema at its top.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

CONTRACT_REL = "docs/design/dashboard-api-v1-provisional.yaml"
APPROVAL_REL = "web/docs/c0-approval.json"
SCHEMA_VERSION = "0.1.2"

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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Contract:
    """The loaded contract and its compiled validators."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.sha256 = digest(path)
        self.document: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
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
