"""Ticket field groups: the registry, canonicalization and live digests (register F4, slice S1).

E19-B §2.3 and §2.4 (ledger TRA-04, TRA-05) as the F4 plan applies them (§3.3, §3.4; decisions 1 to 6;
``docs/implementation/f4-ticket-revisions-plan.md``), recorded in ADR-0016 §1.

* **The registry** (``schemas/ticket-field-registry.v1.json``) assigns every revision-governed Ticket input to exactly
  one primary field group, names its canonicalization rule, and lists every other work-unit key as provenance or
  engine bookkeeping. Its identity is ``aew/ticket-field-registry/v<version>@<sha256 of its canonical JSON>``, so the
  identity does not depend on how the file's bytes were checked out.
* **Canonicalization** is exactly E19-B's v1 text set for prose (CR and CRLF to LF, NFC, trailing spaces and tabs
  removed), exact values for everything else, and two declared set rules (``class0_assertions``; the effective edges).
* **Digests are live** (M10): computed from the current record, the unit's control state and the obligations and edges
  derived from its ancestors, at the moment of use. A group's digest is SHA-256 over ``aew/tfg/v1:<group>\\n`` and the
  canonical JSON of its canonicalized fields.
* **Fail closed:** a record field or control key the registry does not classify hashes into the ``unassigned`` group
  (acceptance); a meta-test and invariant 50 refuse such a key, so every slice that adds one classifies it (§9.2).

Pure functions: nothing here reads the project or writes state, and no engine path calls them before S2a. The derived
values come from ``gates.effective_obligations`` and ``hierarchy.effective_edges``, the functions S2b.1 routes through
the inherited-obligations accessor (plan §3.12a), so carried obligations reach these digests without a change here.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

from aew.engine import gates
from aew.engine import hierarchy as H
from aew.errors import IntegrityError, UsageError, ValidationFailed
from aew.schemas import validate
from aew.util import parse_frontmatter, sha256_text

REGISTRY_FILE = "ticket-field-registry.v{version}.json"
DIGEST_PREFIX = "aew/tfg/v1"
STORES = ("record", "control", "derived")
# The values the engine derives for the gate_set and dependencies groups. A registry must classify every one: one it
# left out would leave an inherited obligation unbound.
DERIVED = frozenset({"effective_class", "class_floor", "inherited_mandatory_gates", "effective_edges"})
# The record field that is the Markdown body (a frontmatter key of that name is unclassified).
BODY = "body"


# --------------------------------------------------------------------------- canonicalization (plan §3.4)


def canonical_text(text: str) -> str:
    """E19-B §2.4's v1 text set, and nothing else: CR and CRLF to LF, Unicode NFC, trailing spaces and tabs removed
    at each line's end. Case, punctuation, blank lines, interior whitespace and wording are never folded."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.rstrip(" \t") for line in text.split("\n"))


# The tags a YAML date or timestamp is hashed under. An authored mapping key that starts with ``$`` gains one more
# ``$`` (``$date`` becomes ``$$date``), so no authored value can spell a tag: the mapping stays one to one.
DATE_TAG, DATETIME_TAG = "$date", "$datetime"


def _jsonable(value: Any, where: str) -> Any:
    """The value as JSON data, one to one: two different values never give the same JSON.

    A YAML date or timestamp (only an unclassified record field can hold one) becomes ``{"$date": "<ISO>"}`` or
    ``{"$datetime": "<ISO>"}``, so it never hashes like the same text (review F3), and an authored mapping key that
    starts with ``$`` is escaped with one more ``$``, so no authored mapping hashes like a tag. Anything else JSON
    cannot hold exactly (NaN, infinity, a non-text mapping key) is refused, never coerced into a colliding value."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValidationFailed(f"{where}: a Ticket input cannot be NaN or infinite")
        return value
    if isinstance(value, dt.datetime):  # before date: a datetime is a date
        return {DATETIME_TAG: value.isoformat()}
    if isinstance(value, dt.date):
        return {DATE_TAG: value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, where) for v in value]
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValidationFailed(f"{where}: a Ticket input mapping must have text keys")
        return {("$" + k if k.startswith("$") else k): _jsonable(v, f"{where}.{k}") for k, v in value.items()}
    raise ValidationFailed(f"{where}: {type(value).__name__} is not a Ticket input value")


def _set_key(value: Any) -> str:
    return canonical_json(value).decode("ascii")


def canonical(value: Any, rule: str, *, where: str = "value") -> Any:
    """A field's canonical projection under its registry rule.

    - ``text``: :func:`canonical_text` on a string; ``text_list``: the same on each string, order kept.
    - ``exact``: the stored value.
    - ``sorted_set``: deduplicated and sorted (``class0_assertions``, inherited gate names): a declared collision.
    - ``edge_set``: ``{id, kind}`` per edge, deduplicated, sorted by id (then kind): a declared collision; an own and an
      inherited edge to the same unit with the same kind are one edge.

    A value of an unexpected shape is kept exactly (it can only make digests differ, never collide).
    """
    value = _jsonable(value, where)
    if value is None:
        return None
    if rule == "text":
        return canonical_text(value) if isinstance(value, str) else value
    if rule == "text_list":
        if not isinstance(value, list):
            return value
        return [canonical_text(v) if isinstance(v, str) else v for v in value]
    if rule == "exact":
        return value
    if rule == "sorted_set":
        if not isinstance(value, list):
            return value
        return [v for _, v in sorted({_set_key(v): v for v in value}.items())]
    if rule == "edge_set":
        if not isinstance(value, list) or not all(isinstance(e, dict) and {"id", "kind"} <= set(e) for e in value):
            raise ValidationFailed(f"{where}: dependency edges must each name an id and a kind")
        edges = {(e["id"], e["kind"]) for e in value}
        return [{"id": i, "kind": k} for i, k in sorted(edges, key=lambda e: (_set_key(e[0]), _set_key(e[1])))]
    raise ValidationFailed(f"{where}: unknown canonicalization rule {rule!r}")


def canonical_json(value: Any) -> bytes:
    """Sorted keys, no whitespace, ASCII only: the same bytes on every platform."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def group_digest(group: str, payload: Mapping[str, Any]) -> str:
    """SHA-256 over ``aew/tfg/v1:<group>\\n`` followed by the canonical JSON of the group's canonicalized fields."""
    return hashlib.sha256(f"{DIGEST_PREFIX}:{group}\n".encode("ascii") + canonical_json(dict(payload))).hexdigest()


# --------------------------------------------------------------------------- the registry (plan §3.3)


@dataclass(frozen=True)
class Field:
    store: str
    name: str
    group: str
    rule: str
    via: tuple[str, ...] = ()
    also: tuple[str, ...] = ()

    @property
    def ref(self) -> str:
        """The field's name in digests and moves: ``record:acceptance.checks``, ``control:risk_class``."""
        return f"{self.store}:{self.name}"


@dataclass(frozen=True)
class Move:
    field: str
    from_: str
    to: str


@dataclass(frozen=True)
class Registry:
    identity: str
    version: int
    predecessor: str | None
    groups: Mapping[str, bool]  # group -> material
    unassigned: str
    fields: tuple[Field, ...]
    provenance: frozenset[str]
    bookkeeping: frozenset[str]
    moves: tuple[Move, ...]

    def store(self, store: str) -> dict[str, Field]:
        return {f.name: f for f in self.fields if f.store == store}

    @property
    def material_groups(self) -> frozenset[str]:
        return frozenset(g for g, m in self.groups.items() if m)

    def record_paths(self) -> dict[tuple[str, ...], str]:
        """The classified frontmatter fields by key path (``("acceptance", "checks")``); the body is not one."""
        return {tuple(n.split(".")): n for n in self.store("record") if n != BODY}

    def classifies_record(self, keys: tuple[str, ...]) -> bool:
        """Whether a record frontmatter key path (``("acceptance", "checks")``) is a classified field, a container of
        one, or provenance. Paths are matched key by key, never as joined text: a key that contains ``.`` (a literal
        ``"scope.paths"``) is never a field (review F1). The Markdown body is the field ``body``; a frontmatter key
        named ``body`` is not."""
        if not keys or any(not isinstance(k, str) or "." in k for k in keys):
            return False
        if len(keys) == 1 and keys[0] in self.provenance:
            return True
        return any(path[:len(keys)] == keys for path in self.record_paths())

    def classifies_control(self, key: str) -> bool:
        return key in self.store("control") or key in self.bookkeeping


def registry_from_doc(doc: Mapping[str, Any], *, source: str = "ticket field registry") -> Registry:
    """Validate a registry document (its schema, then the rules a schema cannot state) and compute its identity."""
    validate("ticket-field-registry", doc, source=source)
    groups = {g: bool(v["material"]) for g, v in doc["groups"].items()}
    problems: list[str] = []
    if doc["unassigned"] not in groups or not groups[doc["unassigned"]]:
        problems.append(f"unassigned group {doc['unassigned']!r} must be a declared material group")
    fields: list[Field] = []
    for store in STORES:
        seen: set[str] = set()
        for f in doc[store]:
            name = f["field"]
            if name in seen:
                problems.append(f"{store}:{name} is classified twice (E19-B §2.3: exactly one primary group)")
            seen.add(name)
            for g in [f["group"], *f.get("also", [])]:
                if g not in groups:
                    problems.append(f"{store}:{name} names undeclared group {g!r}")
            if f["rule"] == "via" and (store != "control" or not set(f["via"]) <= DERIVED):
                problems.append(f"{store}:{name} may be hashed only through derived values {sorted(DERIVED)}")
            fields.append(Field(store, name, f["group"], f["rule"], tuple(f.get("via", ())), tuple(f.get("also", ()))))
    derived = {f.name for f in fields if f.store == "derived"}
    if derived != DERIVED:
        problems.append(f"derived values must be exactly {sorted(DERIVED)}, not {sorted(derived)}")
    control = {f.name for f in fields if f.store == "control"}
    if control & set(doc["bookkeeping"]):
        problems.append(f"control keys both inputs and bookkeeping: {sorted(control & set(doc['bookkeeping']))}")
    record = {f.name for f in fields if f.store == "record"}
    if record & set(doc["provenance"]) or BODY in doc["provenance"]:
        problems.append("record fields and provenance must be disjoint")
    if (doc["version"] == 1) != (doc["predecessor"] is None) or (doc["version"] == 1 and doc["moves"]):
        problems.append("version 1 alone has no predecessor and no moves")
    refs = {f.ref for f in fields}
    for m in doc["moves"]:
        if m["to"] not in groups or m["field"] not in refs:
            problems.append(f"move of {m['field']} to {m['to']!r} names a field or group this version lacks")
    if problems:
        raise ValidationFailed(f"{source}: " + "; ".join(problems), problems=problems)
    digest = hashlib.sha256(canonical_json(_jsonable(dict(doc), source))).hexdigest()
    return Registry(
        identity=f"aew/ticket-field-registry/v{doc['version']}@{digest}", version=doc["version"],
        predecessor=doc["predecessor"], groups=groups, unassigned=doc["unassigned"], fields=tuple(fields),
        provenance=frozenset(doc["provenance"]), bookkeeping=frozenset(doc["bookkeeping"]),
        moves=tuple(Move(m["field"], m["from"], m["to"]) for m in doc["moves"]))


@cache
def load_registry(version: int = 1) -> Registry:
    """A packaged registry version (the current one is 1)."""
    name = REGISTRY_FILE.format(version=version)
    try:
        text = resources.files("aew.schemas").joinpath(name).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValidationFailed(f"no packaged Ticket field registry version {version}") from None
    return registry_from_doc(json.loads(text), source=name)


@cache
def packaged_registries() -> dict[str, Registry]:
    """Every packaged registry version, by identity: the lineage :func:`changed_groups` reads moves from."""
    out: dict[str, Registry] = {}
    version = 1
    while resources.files("aew.schemas").joinpath(REGISTRY_FILE.format(version=version)).is_file():
        reg = load_registry(version)
        out[reg.identity] = reg
        version += 1
    return out


# --------------------------------------------------------------------------- live digests (plan §3.3, M10)


@dataclass(frozen=True)
class Digests:
    """A Ticket's field-group digests, with the identity of the registry that produced them."""

    registry: str
    groups: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        return {"registry": self.registry, "digests": dict(sorted(self.groups.items()))}


def _record_values(meta: Mapping[str, Any], body: str,
                   reg: Registry) -> tuple[dict[str, Any], dict[tuple[Any, ...], Any]]:
    """The classified record fields by name (absent ones None), and every unclassified frontmatter key path's value.

    The walk matches key by key (review F1): a literal key ``"scope.paths"`` is not the nested field ``scope.paths``,
    and a key that contains ``.`` or is not text is never a field, so it is unclassified wherever it appears."""
    known = reg.record_paths()
    values: dict[str, Any] = {n: None for n in known.values()}
    values[BODY] = body
    unclassified: dict[tuple[Any, ...], Any] = {}

    def walk(obj: Mapping[Any, Any], prefix: tuple[Any, ...]) -> None:
        for key, value in obj.items():
            keys = (*prefix, key)
            if not isinstance(key, str) or "." in key:
                unclassified[keys] = value
            elif keys in known:
                values[known[keys]] = value
            elif not prefix and key in reg.provenance:
                continue
            elif isinstance(value, Mapping) and any(len(p) > len(keys) and p[:len(keys)] == keys for p in known):
                walk(value, keys)
            else:
                unclassified[keys] = value

    walk(meta, ())
    return values, unclassified


def _path_key(keys: tuple[Any, ...], where: str) -> str:
    """An unclassified key path in a digest payload: the canonical JSON of its keys, so two paths never share a key."""
    return canonical_json(_jsonable(list(keys), where)).decode("ascii")


def _path_name(keys: tuple[Any, ...], where: str) -> str:
    """An unclassified key path for people: dotted when that is unambiguous, else its keys as JSON."""
    if all(isinstance(k, str) and k and "." not in k and not k.startswith("[") for k in keys):
        return ".".join(keys)
    return _path_key(keys, where)


def unclassified_record_paths(meta: Mapping[str, Any], *, registry: Registry | None = None) -> list[str]:
    """The frontmatter key paths of a record the registry does not classify (they hash into ``unassigned``): dotted
    (``acceptance.edge_cases``), or as a JSON list of keys when a key contains ``.`` (``["scope.paths"]``)."""
    unclassified = _record_values(meta, "", registry or load_registry())[1]
    return sorted(_path_name(keys, "record frontmatter") for keys in unclassified)


def unclassified_control_keys(unit: Mapping[str, Any], *, registry: Registry | None = None) -> list[str]:
    """The unit's control-state keys the registry does not classify (they hash into ``unassigned``)."""
    reg = registry or load_registry()
    return sorted(k for k in unit if not reg.classifies_control(k))


def _derived_values(state: dict[str, Any], work_id: str) -> dict[str, Any]:
    """The obligations and edges the Ticket inherits, from the engine's own functions (gates and dispatch use these;
    S2b.1 routes them through ``hierarchy.inherited``)."""
    # The class path's own gates are policy, bound by the legality digest of the Policy Binding and Digest Amendment
    # (docs/design/policy-binding-digest-amendment-v0.1.md, ledger PBD; not the F4 plan's §3.1 A3), not a Ticket
    # input: only what the Ticket inherits is hashed here, so every class maps to no path gates.
    no_path_gates: dict[str, Any] = {"risk_paths": defaultdict(list)}
    obligations = gates.effective_obligations(state, work_id, no_path_gates)
    return {
        "effective_class": obligations["effective_class"],
        "class_floor": obligations["floor"],
        "inherited_mandatory_gates": obligations["non_waivable"],
        "effective_edges": H.effective_edges(state, work_id),
    }


def group_payloads(state: dict[str, Any], work_id: str, record_text: str, *,
                   registry: Registry | None = None) -> dict[str, dict[str, Any]]:
    """Each group's canonicalized fields, keyed ``<store>:<field>``: what its digest is computed over.

    ``record_text`` is the Ticket's current record as stored; it must hash to the ``record_sha256`` control state
    pins, so a digest is never computed over another record than the one the unit names. Unclassified record paths and
    control keys are hashed into the ``unassigned`` group, each under ``record:?<path>`` or ``control:?<key>``, where
    ``<path>`` is the JSON list of the path's keys (``record:?["acceptance","edge_cases"]``), so no two paths share one.
    """
    reg = registry or load_registry()
    unit = state["work"].get(work_id)
    if unit is None:
        raise UsageError(f"no hot work unit {work_id}")
    if unit.get("kind") != "ticket":
        raise UsageError(f"{work_id} is a {unit.get('kind')}: field-group digests are a Ticket's (E19-B §2.3)")
    pinned = unit.get("record_sha256")
    if pinned is not None and sha256_text(record_text) != pinned:
        raise IntegrityError(f"{work_id}: the record given does not hash to the record_sha256 control state pins",
                             reason="RECORD_MISMATCH", work_id=work_id)
    meta, body = parse_frontmatter(record_text, source=f"{work_id} record")
    record, unclassified_record = _record_values(meta, body, reg)
    derived = _derived_values(state, work_id)
    payloads: dict[str, dict[str, Any]] = {g: {} for g in reg.groups}
    for f in reg.fields:
        if f.rule == "via":  # hashed through the derived values it feeds
            continue
        source = record if f.store == "record" else unit if f.store == "control" else derived
        payloads[f.group][f.ref] = canonical(source.get(f.name), f.rule, where=f"{work_id} {f.ref}")
    fallback = payloads[reg.unassigned]
    for keys, value in unclassified_record.items():
        path = _path_key(keys, f"{work_id} record")
        fallback[f"record:?{path}"] = canonical(value, "exact", where=f"{work_id} record:{path}")
    for key in unclassified_control_keys(unit, registry=reg):
        fallback[f"control:?{key}"] = canonical(unit[key], "exact", where=f"{work_id} control:{key}")
    return payloads


def live_digests(state: dict[str, Any], work_id: str, record_text: str, *,
                 registry: Registry | None = None) -> Digests:
    """The Ticket's current digest of every group, computed now from its record, its control state and what it
    inherits (plan §3.3, M10). The caller reads the record the unit names (``unit.record``); the function stays pure."""
    reg = registry or load_registry()
    payloads = group_payloads(state, work_id, record_text, registry=reg)
    return Digests(reg.identity, {g: group_digest(g, p) for g, p in payloads.items()})


# --------------------------------------------------------------------------- comparing (plan §3.3, §3.5)


def _lineage(older: str, newer: str, registries: Mapping[str, Registry]) -> list[Registry] | None:
    """The versions from ``older`` to ``newer``, oldest first, or None when ``newer`` does not descend from it."""
    chain: list[Registry] = []
    current = registries.get(newer)
    while current is not None:
        chain.append(current)
        if current.identity == older:
            return chain[::-1]
        current = registries.get(current.predecessor) if current.predecessor else None
    return None


def _registry_delta(old: Registry, new: Registry) -> set[str]:
    """The groups one version step affects, read from the two registries themselves, not only from the declared
    moves (E19-B §2.3, review F2).

    - Every field added, removed, regrouped (its primary or ``also`` groups), given another rule, or hashed through
      other derived values counts in each of its old and new groups. That includes a field hashed only through derived
      values (``depends_on``, ``carried_obligations``), which has no payload entry of its own.
    - Every group added, removed, or whose materiality changed counts.
    - The old and new ``unassigned`` groups count when the unassigned group, the provenance or the bookkeeping list
      changed, because those decide which keys fall into it.
    - The step's declared moves count as well.
    """
    def shape(reg: Registry) -> dict[str, tuple[str, tuple[str, ...], str, tuple[str, ...]]]:
        return {f.ref: (f.group, f.also, f.rule, f.via) for f in reg.fields}

    before, after = shape(old), shape(new)
    changed: set[str] = set()
    for ref in set(before) | set(after):
        if before.get(ref) != after.get(ref):
            for side in (before.get(ref), after.get(ref)):
                if side is not None:
                    changed |= {side[0], *side[1]}
    changed |= {g for g in set(old.groups) | set(new.groups) if old.groups.get(g) != new.groups.get(g)}
    if (old.unassigned, old.provenance, old.bookkeeping) != (new.unassigned, new.provenance, new.bookkeeping):
        changed |= {old.unassigned, new.unassigned}
    for m in new.moves:
        changed |= {m.from_, m.to}
    return changed


def changed_groups(before: Digests, after: Digests, *,
                   registries: Mapping[str, Registry] | None = None) -> frozenset[str]:
    """The groups whose digests differ between two computations.

    Across registry versions (E19-B §2.3), every group that a version step between the two affects counts as changed,
    whatever the digests say (:func:`_registry_delta`): the old and new groups of a field that was moved, regrouped,
    given another rule or hashed through other derived values, each group whose materiality changed, and each group
    one side lacks. When neither registry descends from the other in ``registries`` (by default the packaged ones),
    every group counts as changed.
    """
    groups = set(before.groups) | set(after.groups)
    changed = {g for g in groups if before.groups.get(g) != after.groups.get(g)}
    if before.registry != after.registry:
        known = packaged_registries() if registries is None else registries
        chain = _lineage(before.registry, after.registry, known) or _lineage(after.registry, before.registry, known)
        if chain is None:
            return frozenset(groups)
        for old, new in zip(chain, chain[1:], strict=False):
            changed |= _registry_delta(old, new)
    return frozenset(changed)


def material(groups: Iterable[str], *, registry: Registry | None = None,
             card_acceptance_bearing: bool = False) -> frozenset[str]:
    """The material groups among ``groups`` (E19-B §4.3). A group the registry does not declare counts as material
    (fail closed); ``card`` is material while the Ticket's per-Ticket override ``card_acceptance_bearing`` is set
    (plan §3.3, the title)."""
    reg = registry or load_registry()
    return frozenset(g for g in groups
                     if reg.groups.get(g, True) or (card_acceptance_bearing and g == "card"))
