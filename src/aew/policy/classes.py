"""Policy field classes and the two policy digests (the pre-F15.2 amendment A3; M4-E plan §2.5).

Every property of the policy schemas the policy pin covers (gates, guardrails, checks, execution) is classified, in
the schema itself, as ``"x-aew-class": "legality_affecting"`` or ``"operational"``. A property that carries no class
must be a container whose own properties are all classified, recursively (through ``properties``, or through
``additionalProperties`` when the map's values are objects with properties). An unclassified leaf fails: a field never
silently defaults to operational because its meaning is unknown (A3 §8).

``legality_digest`` covers the legality-affecting values and ``operational_digest`` the operational ones, both read
from the pinned policy bytes. Only a legality change makes a dispatch decision stale. An operational change takes
effect at the next safe boundary and is recorded, but it never relaxes the policy pin: every edit, operational
included, still needs the operator's adoption (#118).

A policy file with no classified schema (a manifest ``policy`` entry other than the four) counts wholly as legality,
which fails closed. So does an instance key the schema does not name: the schema's open containers accept it, and the
engine may read it (PR #130 review, finding 2), so it is digested as legality rather than dropped. A policy map key
that is not a string is refused: it cannot be ordered against string keys, and ``1`` and ``"1"`` would share a
pointer (finding 3).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

from aew.errors import ValidationFailed

LEGALITY = "legality_affecting"
OPERATIONAL = "operational"
CLASSES = (LEGALITY, OPERATIONAL)
KEY = "x-aew-class"
CLASSIFIED = ("gates", "guardrails", "checks", "execution")


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return _resolve(schema, schema["$defs"][ref.removeprefix("#/$defs/")])
    return node


def _children(schema: dict[str, Any], node: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """A container's named properties, and the schema of its map values when those are objects with properties."""
    node = _resolve(schema, node)
    props = node.get("properties")
    extra = node.get("additionalProperties")
    values = _resolve(schema, extra) if isinstance(extra, dict) else None
    return (props if isinstance(props, dict) else None,
            values if values is not None and isinstance(values.get("properties"), dict) else None)


def unclassified(schema: dict[str, Any]) -> list[str]:
    """Every property path in ``schema`` that has neither a class nor fully classified children (empty: all good)."""
    missing: list[str] = []

    def walk(node: dict[str, Any], path: str) -> None:
        props, values = _children(schema, node)
        if props is None and values is None:
            missing.append(path or "<root>")
            return
        for name, child in (props or {}).items():
            check(child, f"{path}/{name}")
        if values is not None:
            walk(values, f"{path}/*")

    def check(child: dict[str, Any], path: str) -> None:
        cls = child.get(KEY)
        if cls is not None:
            if cls not in CLASSES:
                missing.append(f"{path} (unknown class {cls!r})")
            return
        walk(child, path)

    walk(schema, "")
    return missing


def _pointer(path: str, name: str) -> str:
    return f"{path}/{name.replace('~', '~0').replace('/', '~1')}"  # RFC 6901, so an unnamed key cannot alias a field


def _string_keys(value: Any, path: str = "") -> None:
    """Refuse a mapping key that is not a string anywhere in a policy instance (YAML reads ``1:`` as an integer)."""
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ValidationFailed(f"policy key {k!r} at {path or '/'} is not a string; quote it",
                                       reason="policy_key_not_string", pointer=path or "/")
            _string_keys(v, _pointer(path, k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _string_keys(v, f"{path}/{i}")


def leaves(schema: dict[str, Any], instance: Any) -> Iterator[tuple[str, str, Any]]:
    """``(json-pointer, class, value)`` for every value present in ``instance``: its schema class when classified, and
    legality for a key the schema does not name (fail closed, A3 §8)."""

    def walk(node: dict[str, Any], value: Any, path: str) -> Iterator[tuple[str, str, Any]]:
        if not isinstance(value, dict):
            yield path, LEGALITY, value  # not the container the schema describes: all of it binds legality
            return
        props, values = _children(schema, node)
        for name, child in (props or {}).items():
            if name in value:
                yield from visit(child, value[name], _pointer(path, name))
        for name in sorted(k for k in value if k not in (props or {})):
            if values is not None:
                yield from walk(values, value[name], _pointer(path, name))
            else:
                yield _pointer(path, name), LEGALITY, value[name]

    def visit(child: dict[str, Any], value: Any, path: str) -> Iterator[tuple[str, str, Any]]:
        cls = child.get(KEY)
        if cls is not None:
            yield path, cls, value
        else:
            yield from walk(child, value, path)

    _string_keys(instance)
    yield from walk(schema, instance, "")


def _sha(body: Any) -> str:
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def digests(files: dict[str, tuple[str | None, Any]]) -> dict[str, str]:
    """The two digests over ``{rel path: (schema name or None, parsed content or None when absent)}``."""
    from aew.schemas import schema as load_schema

    legal: dict[str, Any] = {}
    oper: dict[str, Any] = {}
    for rel, (name, data) in sorted(files.items()):
        if name not in CLASSIFIED or data is None:
            legal[rel] = data  # an unclassified policy file, or an absent one, is legality in full
            continue
        schema = load_schema(name)
        missing = unclassified(schema)
        if missing:
            raise ValueError(f"policy schema {name} has unclassified properties (A3 §8): {', '.join(missing)}")
        _string_keys(data)
        legal[rel] = {}
        oper[rel] = {}
        for pointer, cls, value in leaves(schema, data):
            (legal if cls == LEGALITY else oper)[rel][pointer] = value
    return {"legality_digest": _sha(legal), "operational_digest": _sha(oper)}
