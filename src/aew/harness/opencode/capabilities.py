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
TESTED_VERSIONS = ("2.2.6",)


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

# Fields the adapter reads from responses, and configuration keys it sets, each with the JSON type the adapter
# relies on: the served schema must still offer that type (through ``$ref`` and ``anyOf``/``oneOf``/``allOf``). A dotted
# name is a property of a property. Kept complete against the adapter (independent review R2, 2026-09-30): a field
# read only for telemetry is listed too, since health is the one place drift is caught.
S, I, N, B, O, A = "string", "integer", "number", "boolean", "object", "array"  # noqa: E741 (JSON type shorthands)
REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "ServerInfo": {"version": S},
    "Model.Info": {"id": S, "providerID": S, "variants": A, "enabled": B},
    "Model.Variant": {"id": S},
    "Model.Ref": {"id": S, "providerID": S, "variant": S},
    "Agent.Info": {"id": S, "system": S, "permissions": A, "model": O, "steps": I},
    "Session.Info": {"id": S, "model": O, "outcome": S, "tokens": O, "cost": N},
    "Session.Message.User": {"id": S, "time": O, "type": S},
    "Session.Message.Assistant": {"id": S, "type": S, "agent": S, "model": O, "tokens": O, "cost": N, "finish": S,
                                  "error": O, "time": O, "content": A},
    "Session.Message.Assistant.Tool": {"type": S, "name": S},
    "Session.Message.Idle": {"id": S, "type": S, "outcome": S, "time": O},
    "SessionMessagesResponse": {"data": A, "cursor": O, "cursor.next": S},
    "Permission.Request": {"id": S, "action": S, "resources": A},
    "Permission.Rule": {"action": S, "resource": S, "effect": S},
    # `experimental.policies` carries the Lead's provider deny (projection.LEAD_DENIED_PROVIDERS): a release that
    # respells it fails closed at a worker's launch, which probes this schema; the Lead's TUI is not probed.
    # `warming` and `experimental.image_generate` are the defaults every projection closes (projection.CLOSED), and
    # `pool` the Lead's MCP server's: a release that respells one fails closed rather than leaving it open.
    "Config.InfoEncoded": {"agents": O, "plugins": A, "snapshots": B, "update": S, "share": S, "lsp": B,
                           "formatter": B, "default_agent": S, "permissions": A, "commands": O, "mcp": O,
                           "mcp.servers": O, "experimental": O, "experimental.policies": A, "warming": B,
                           "experimental.image_generate": B},
    # The Lead's typed surface (F15.1): a release that respells local MCP servers fails closed at launch.
    "Mcp.LocalConfigEncoded": {"type": S, "command": A, "codemode": B, "pool": B},
    "Config.AgentEncoded": {"model": O, "system": S, "mode": S, "permissions": A, "steps": I, "description": S},
    "Config.CommandEncoded": {"template": S, "description": S, "agent": S},
}
REQUIRED_ENUMS: dict[str, frozenset[str]] = {
    "Permission.Effect": frozenset({"allow", "deny"}),
    "Permission.Reply": frozenset({"reject"}),
    "Session.Inbox.Delivery": frozenset({"queue"}),
}
# Enums declared inline, under a field of a named schema (``[]`` steps into an array's items): the policy actions AEW
# projects (projection.lead_provider_policies). 2.2.3 changed `integration.use` incompatibly, and the schema check
# alone saw only that the policies are an array, so a release that dropped `provider.use` would have passed.
# `experimental.policies` is deprecated in 2.2.6 for a top-level `policies`, and still honoured: 2.2.6 merges both
# (read from its bundle, 2026-11-07).
REQUIRED_FIELD_ENUMS: dict[tuple[str, str], frozenset[str]] = {
    ("Config.InfoEncoded", "experimental.policies[].action"): frozenset({"provider.use"}),
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


def _property(spec: dict[str, Any], schema: Any, name: str) -> list[Any]:
    """Every declaration of property ``name`` in an object schema (one per ``anyOf``/``oneOf``/``allOf`` branch)."""
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict):
        return []
    found = [schema["properties"][name]] if name in (schema.get("properties") or {}) else []
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key) or []:
            found += _property(spec, part, name)
    return found


def _types(spec: dict[str, Any], schema: Any, depth: int = 0) -> set[str]:
    """The JSON types a schema admits; empty when it declares none (it then admits any)."""
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict) or depth > 10:
        return set()
    declared = schema.get("type")
    out = {declared} if isinstance(declared, str) else set(declared or [])
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key) or []:
            out |= _types(spec, part, depth + 1)
    return out


def _items(spec: dict[str, Any], schema: Any) -> list[Any]:
    """An array schema's ``items`` (one per ``anyOf``/``oneOf``/``allOf`` branch)."""
    schema = _resolve(spec, schema)
    if not isinstance(schema, dict):
        return []
    found = [schema["items"]] if isinstance(schema.get("items"), dict) else []
    for key in ("anyOf", "oneOf", "allOf"):
        for part in schema.get(key) or []:
            found += _items(spec, part)
    return found


def field_enum(spec: dict[str, Any], name: str, path: str) -> set[str]:
    """The values an enum declared inline at ``path`` under schema ``name`` offers: a dotted path, where ``x[]`` steps
    into array ``x``'s items. Empty when the path or the enum is missing."""
    candidates = [((spec.get("components") or {}).get("schemas") or {}).get(name)]
    for part in path.split("."):
        field = part.removesuffix("[]")
        candidates = [d for c in candidates for d in _property(spec, c, field)]
        if part.endswith("[]"):
            candidates = [d for c in candidates for d in _items(spec, c)]
    return {str(v) for c in candidates for v in _enum(spec, c)}


def _field_problem(spec: dict[str, Any], schema: Any, path: str, want: str) -> str | None:
    """Why the schema does not offer ``path`` with type ``want`` (None when it does)."""
    candidates = [schema]
    for part in path.split("."):
        candidates = [d for c in candidates for d in _property(spec, c, part)]
        if not candidates:
            return "missing"
    offered: set[str] = set()
    for c in candidates:
        types = _types(spec, c)
        if not types:
            return None  # no declared type: anything goes
        offered |= types
    if want in offered or (want == "number" and "integer" in offered):
        return None
    return f"not {want} (declares {sorted(offered)})"


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
        found = {field: _field_problem(spec, schemas[name], field, want) for field, want in fields.items()}
        missing = sorted(f for f, problem in found.items() if problem == "missing")
        if missing:
            out.append(f"schema {name} lacks {missing}")
        out += [f"schema {name} field {f} is {problem}" for f, problem in found.items()
                if problem and problem != "missing"]
    for name, values in REQUIRED_ENUMS.items():
        if name not in schemas:
            out.append(f"schema {name} is missing")
            continue
        missing = values - _enum(spec, schemas[name])
        if missing:
            out.append(f"{name} lacks {sorted(missing)}")
    for (name, path), values in REQUIRED_FIELD_ENUMS.items():
        if name not in schemas:
            out.append(f"schema {name} is missing")
            continue
        missing = values - field_enum(spec, name, path)
        if missing:
            out.append(f"schema {name} field {path} lacks {sorted(missing)}")
    return out
