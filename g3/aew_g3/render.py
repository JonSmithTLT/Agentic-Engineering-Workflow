"""The rendering (G3-03): built from records, never from text, and complete.

The line format is the regression aid's (A-26 ``verify_g3.py``, which A-37 keeps binding for G3-03): the three
set-level fields, then for each member its ``g3:action:<ACTION>`` template line, one ``g3:field`` line for every leaf
the SW-02 digest covers in canonical order, and at most one owner fact. The consequence fact is optional under A-37
(G3-03 source 3); the service ships without a fact source, so it renders none, and :func:`derived` refuses any
``OWNER_FACT`` line that does not match a fact the service itself read.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SET_FIELDS = ("request_set_ref", "recipient_ref", "installation_ref")
_PARTS = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]")
_MISSING = object()


def leaves(cs: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Every leaf the SW-02 set digest covers, as (field_path, value), in canonical order (G3-03 source 2)."""
    out: list[tuple[str, Any]] = [(f, cs[f]) for f in SET_FIELDS]

    def walk(path: str, v: Any) -> None:
        if isinstance(v, dict):
            for k in sorted(v):
                walk(f"{path}.{k}", v[k])
        elif isinstance(v, list):
            for n, x in enumerate(v):
                walk(f"{path}[{n}]", x)
        else:
            out.append((path, v))

    for n, intent in enumerate(cs["intents"]):
        walk(f"intents[{n}]", intent)
    return out


def at(cs: Any, path: str) -> Any:
    """The value at a field_path, or a sentinel when the set has no such leaf."""
    v = cs
    for part in _PARTS.findall(path):
        try:
            v = v[int(part[1:-1])] if part.startswith("[") else v[part]
        except (KeyError, IndexError, TypeError, ValueError):
            return _MISSING
    return v


def _field(path: str, value: Any) -> dict[str, Any]:
    return {"template_id": "g3:field", "values": {"name": path, "value": value},
            "source": {"kind": "TYPED_FIELD", "field_path": path}}


def render(cs: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]],
           facts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The service's own rendering of a command set. ``facts`` maps an owner to the fact the service read from it."""
    covered = leaves(cs)
    lines = [_field(f, v) for f, v in covered[:len(SET_FIELDS)]]
    for k, intent in enumerate(cs["intents"]):
        lines.append({"template_id": "g3:action:" + intent["action"], "values": {}, "source": {"kind": "TEMPLATE"}})
        prefix = f"intents[{k}]"
        lines.extend(_field(f, v) for f, v in covered if f.startswith(prefix + ".") or f.startswith(prefix + "["))
        fact = facts.get(registry.get(intent["action"], {}).get("sole_admitting_owner", ""))
        if fact:
            lines.append({"template_id": "g3:owner-fact", "values": dict(fact["values"]),
                          "source": {"kind": "OWNER_FACT", "owner": fact["owner"], "fact_ref": fact["fact_ref"],
                                     "observed_at": fact["observed_at"],
                                     "observation_state": fact["observation_state"]}})
    return lines


def derived(cs: Mapping[str, Any], lines: list[dict[str, Any]], facts: Mapping[str, Mapping[str, Any]]) -> bool:
    """Every line has one of G3-03's three sources and shows the set's own value (else ``RENDERING_UNDERIVED``)."""
    for ln in lines:
        s = ln.get("source", {})
        kind = s.get("kind")
        if kind == "TEMPLATE":
            action = ln["template_id"].removeprefix("g3:action:")
            if ln["values"] or not any(i["action"] == action for i in cs["intents"]):
                return False
        elif kind == "TYPED_FIELD":
            if (ln["template_id"] != "g3:field" or set(ln["values"]) != {"name", "value"}
                    or ln["values"]["name"] != s.get("field_path")):
                return False
            v = at(cs, s["field_path"])
            if v is _MISSING or isinstance(v, (dict, list)) or v != ln["values"]["value"] \
                    or type(v) is not type(ln["values"]["value"]):
                return False
        elif kind == "OWNER_FACT":
            fact = facts.get(s.get("owner", ""))
            if not fact or fact["fact_ref"] != s.get("fact_ref") or ln["values"] != fact["values"]:
                return False
        else:
            return False
    return True


def complete(cs: Mapping[str, Any], lines: list[dict[str, Any]]) -> bool:
    """Every covered leaf and every member's action is shown (else ``RENDERING_INCOMPLETE``)."""
    shown = {ln["source"].get("field_path") for ln in lines if ln["source"].get("kind") == "TYPED_FIELD"}
    templates = {ln["template_id"] for ln in lines if ln["source"].get("kind") == "TEMPLATE"}
    return (all(f in shown for f, _ in leaves(cs))
            and all("g3:action:" + i["action"] in templates for i in cs["intents"]))


def member_line_limits(o01_schema: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]) -> dict[str, int]:
    """R2-1: the most lines each protected action's member can need, derived from the sealed O-01 schema: 1 template
    line, every covered leaf, at most 1 owner fact. Raises on an array or an open object in a protected intent, which
    would make the rendering unbounded."""
    defs = o01_schema["$defs"]

    def resolve(x: Mapping[str, Any]) -> Mapping[str, Any]:
        while "$ref" in x:
            x = defs[x["$ref"].split("/")[-1]]
        return x

    def count(x: Mapping[str, Any], path: str) -> int:
        x = resolve(x)
        for k in ("oneOf", "anyOf"):
            if k in x:
                return max(count(b, path) for b in x[k])
        if x.get("type") == "array" or "items" in x:
            raise ValueError(f"R2-1: an array at {path} makes the rendering unbounded")
        if x.get("type") == "object" or "properties" in x:
            if x.get("additionalProperties", True) is not False:
                raise ValueError(f"R2-1: an open object at {path} makes the rendering unbounded")
            return sum(count(v, f"{path}.{k}") for k, v in x["properties"].items())
        return 1

    common = sum(count(v, k) for k, v in defs["Intent"]["properties"].items() if k != "target")
    out = {}
    for branch in defs["Intent"]["allOf"]:
        action = branch["if"]["properties"]["action"]["const"]
        if registry[action]["origin"] == "PROTECTED_G3":
            out[action] = 1 + common + count(branch["then"]["properties"]["target"], action + ".target") + 1
    return out
