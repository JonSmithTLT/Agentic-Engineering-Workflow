"""Capability probe of a served OpenCode V2 API (ADR-0009): every gap fails closed.

V2 publishes no stability policy and labels its HTTP API experimental, so AEW checks, against the
server actually started for each run, that every operation, request field, response field, enum value
and configuration key the adapter uses is present in that server's own ``/openapi.json``. A missing
item is ``HARNESS_INCOMPATIBLE``, naming it; nothing is emulated or guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SUPPORTED_MAJOR = 2
TESTED_VERSIONS = ("2.0.18",)


@dataclass(frozen=True)
class Op:
    method: str
    path: str
    body: frozenset[str] = frozenset()
    query: frozenset[str] = frozenset()

    def __str__(self) -> str:
        return f"{self.method} {self.path}"


def _op(method: str, path: str, *, body: tuple[str, ...] = (), query: tuple[str, ...] = ()) -> Op:
    return Op(method, path, frozenset(body), frozenset(query))


REQUIRED_OPERATIONS: tuple[Op, ...] = (
    _op("GET", "/api/info"),
    _op("GET", "/api/model", query=("location",)),
    _op("GET", "/api/agent", query=("location",)),
    _op("GET", "/api/event"),
    _op("POST", "/api/session", body=("title", "agent", "model", "location", "permissions", "metadata")),
    _op("GET", "/api/session"),
    _op("GET", "/api/session/active"),
    _op("GET", "/api/session/{sessionID}"),
    _op("PUT", "/api/session/{sessionID}/environment", body=("variables",)),
    _op("POST", "/api/session/{sessionID}/prompt", body=("id", "text", "delivery")),
    _op("POST", "/api/session/{sessionID}/interrupt", query=("resume",)),
    _op("GET", "/api/session/{sessionID}/message", query=("order", "limit", "cursor")),
    _op("GET", "/api/session/{sessionID}/message/{messageID}"),
    _op("GET", "/api/session/{sessionID}/inbox"),
    _op("GET", "/api/session/{sessionID}/permission"),
    _op("POST", "/api/session/{sessionID}/permission/{requestID}/reply", body=("decision", "message")),
    _op("GET", "/api/session/{sessionID}/form"),
    _op("DELETE", "/api/session/{sessionID}/form/{formID}"),
)

# Fields the adapter reads from responses, and configuration keys it sets.
REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "ServerInfo": frozenset({"version"}),
    "Model.Info": frozenset({"id", "providerID", "variants", "enabled"}),
    "Model.Variant": frozenset({"id"}),
    "Model.Ref": frozenset({"id", "providerID", "variant"}),
    "Agent.Info": frozenset({"id", "system", "permissions", "model", "steps"}),
    "Session.Info": frozenset({"id", "model", "outcome", "tokens", "cost"}),
    "Session.Message.User": frozenset({"id", "time", "type"}),
    "Session.Message.Assistant": frozenset({"id", "model", "tokens", "cost", "finish", "error", "time"}),
    "Session.Message.Idle": frozenset({"id", "outcome", "time"}),
    "Permission.Request": frozenset({"id", "action", "resources"}),
    "Config.InfoEncoded": frozenset({"agents", "plugins", "snapshots", "update", "share", "lsp", "formatter",
                                     "default_agent", "permissions", "commands"}),
    "Config.AgentEncoded": frozenset({"model", "system", "mode", "permissions", "steps", "description"}),
    "Config.CommandEncoded": frozenset({"template", "description", "agent"}),
}
REQUIRED_ENUMS: dict[str, frozenset[str]] = {
    "Permission.Effect": frozenset({"allow", "deny"}),
    "Permission.Reply": frozenset({"reject"}),
    "Session.Inbox.Delivery": frozenset({"queue"}),
}


def version_problems(version: Any) -> list[str]:
    try:
        major = int(str(version).split(".")[0])
    except ValueError:
        return [f"unrecognised OpenCode version {version!r}"]
    if major != SUPPORTED_MAJOR:
        return [f"OpenCode {version} is not a V{SUPPORTED_MAJOR} server (the V1 API is not supported)"]
    return []


def _resolve(spec: dict[str, Any], schema: Any) -> Any:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 20:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = (spec.get("components") or {}).get("schemas", {}).get(name, {})
        seen += 1
    return schema


def _properties(spec: dict[str, Any], schema: Any) -> set[str]:
    """Property names of an object schema, looking through ``$ref`` and ``anyOf``/``oneOf``/``allOf``."""
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict):
        return set()
    names = set((schema.get("properties") or {}).keys())
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key) or []:
            names |= _properties(spec, part)
    return names


def _enum(spec: dict[str, Any], schema: Any) -> set[str]:
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict):
        return set()
    values = set(schema.get("enum") or [])
    for key in ("anyOf", "oneOf"):
        for part in schema.get(key) or []:
            values |= _enum(spec, part)
    return values


def problems(spec: Any, extra: tuple[Op, ...] = ()) -> list[str]:
    """Everything the adapter needs that the served API does not declare (empty when compatible)."""
    if not isinstance(spec, dict) or not isinstance(spec.get("paths"), dict):
        return ["the server's /openapi.json is not an OpenAPI document"]
    out: list[str] = []
    paths = spec["paths"]
    for op in (*REQUIRED_OPERATIONS, *extra):
        entry = (paths.get(op.path) or {}).get(op.method.lower())
        if not isinstance(entry, dict):
            out.append(f"operation {op} is missing")
            continue
        if op.body:
            body = ((entry.get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema")
            missing = op.body - _properties(spec, body)
            if missing:
                out.append(f"{op} does not accept {sorted(missing)}")
        if op.query:
            params = {p.get("name") for p in entry.get("parameters") or [] if p.get("in") == "query"}
            missing = op.query - params
            if missing:
                out.append(f"{op} does not accept query {sorted(missing)}")
    schemas = (spec.get("components") or {}).get("schemas") or {}
    for name, fields in REQUIRED_FIELDS.items():
        if name not in schemas:
            out.append(f"schema {name} is missing")
            continue
        missing = fields - _properties(spec, schemas[name])
        if missing:
            out.append(f"schema {name} lacks {sorted(missing)}")
    for name, values in REQUIRED_ENUMS.items():
        if name not in schemas:
            out.append(f"schema {name} is missing")
            continue
        missing = values - _enum(spec, schemas[name])
        if missing:
            out.append(f"{name} lacks {sorted(missing)}")
    return out
