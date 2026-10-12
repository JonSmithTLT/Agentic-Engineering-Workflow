"""The configuration read projection (register F46.1; the F46.1 proposal, reviewed CLEAR and designer- and
operator-approved: §3 the projection, §4 the digest and the document states, §7 secrets safe by structure).

One engine read of the selected project's execution policy: its profiles, routing, provider connections and controls,
with the **configuration digest** that F46.2's Save binds to and each document's write capability (UNSUPPORTED until
F46.2). The CLI (`aew settings show`) and, later, an F20 HTTP adapter serve it. It is not a writer and not a second
configuration store.

**Lock-free, and never through ``execution_policy()``** (§3), which raises on drift. It reads the committed control
state (``ControlStore.read_committed``), resolves a policy file's path through the manifest only while the manifest
matches its pin (m1), reads each file's bytes once, derives the state from §4.2's inputs and parses those same bytes. A
torn read between the pins and a file is harmless: F46.2 recomputes the digest under the store lock and refuses on any
difference.

**Secrets are withheld by structure, not redaction** (§7). A value is shown only when it passes its field's shape rule
and holds no credential shape (``aew.harness.contract.credential_shaped``); a withheld value is absent with a reason
code, never ``null``. Errors are rendered from the validator's structure (path, keyword, the schema's side), never
from a message. Every locator comes from the one encoder, ``aew.policy.config_paths``.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from aew.engine import steering as S
from aew.engine.base import POLICY_PINS, Kernel, check_policy_bytes
from aew.engine.store import read_lock_free
from aew.errors import UsageError, ValidationFailed
from aew.harness import agentenv, registry
from aew.harness.contract import credential_shaped
from aew.harness.models import ModelIdRefused
from aew.history.manifest import canonical_json
from aew.knowledge.manifest import MANIFEST
from aew.policy import config_paths as P
from aew.policy import execution as X
from aew.schemas import iter_errors, schema, validate
from aew.util import load_yaml, sha256_bytes

DIGEST_SCHEME = "aew/config-digest/v2"
PROJECT, EXECUTION = "project", "execution"
PROJECTED = (EXECUTION,)  # the documents projected field by field in this slice; the others are UNSUPPORTED

# Document states (§4.2), highest precedence first.
MANIFEST_DRIFTED, DRIFTED, INVALID, ADOPTED, UNPINNED, ABSENT = (
    "MANIFEST_DRIFTED", "DRIFTED", "INVALID", "ADOPTED", "UNPINNED", "ABSENT")
# The digest's `adopted` and `on_disk` inputs besides a hash (§4.1, §4.2): each case is encoded distinctly.
NO_PINS, PINNED_ABSENT, NOT_IN_PINS, ON_DISK_ABSENT = "no_pins", "pinned_absent", "not_in_pins", "absent"
DRIFTED_INPUT = "manifest_drifted"  # `rel`, `adopted` and `on_disk` while the manifest is drifted (N2)

# Capabilities (the dashboard contract's Capability: a state and its reasons).
AVAILABLE, UNAVAILABLE, UNSUPPORTED = "AVAILABLE", "UNAVAILABLE", "UNSUPPORTED"
REASONS = {
    "AWAITS_F46_2": "editing arrives with register F46.2 (validate, preview and apply in the operator session); "
                    "until then this document is read-only",
    "AWAITS_F46_3": "the provider's model catalog arrives with register F46.3",
    "AWAITS_LATER_F46": "a later F46 slice projects and edits this; until then it is not shown field by field",
}
ACTIVITIES = (("execution", AVAILABLE, None), ("providers", AVAILABLE, None),
              ("workflow", UNSUPPORTED, "AWAITS_LATER_F46"), ("project", UNSUPPORTED, "AWAITS_LATER_F46"))

# Where `observed` was checked, and its caption (§3.3): the environment of the process that renders the projection.
CLI_ENVIRONMENT, DASHBOARD_SERVER_ENVIRONMENT = "cli_environment", "dashboard_server_environment"
OBSERVED_CAPTIONS = {
    CLI_ENVIRONMENT: "this terminal's environment",
    DASHBOARD_SERVER_ENVIRONMENT: "the dashboard server's environment, not the environment runs launch from",
}
PINS_NOTE = "Existing invocation pins are unchanged"
RESOLUTION_ORDER = ("card", "class", "archetype", "default")  # aew.policy.execution.route's order
NOT_SUPPLIED = "NOT_SUPPLIED"
MODEL_ID_HINT = "write it as <provider>/<model>"

# The bounds of every list (§3.5): flagged lists carry a `truncated` sibling; the others are complete by an invariant.
MAX_DOCUMENTS, MAX_VIOLATIONS, MAX_PROFILES, MAX_ROUTE_ENTRIES = 16, 50, 64, 256
MAX_ROUTED_BY, MAX_CONNECTIONS, MAX_CONNECTION_PROFILES, MAX_PROVIDER_ENV = 64, 32, 64, 64
MAX_ALLOWED, MAX_SWITCHES, MAX_DESCRIPTION_BYTES = 16, 16, 512

# Shape rules for values that may be shown (§7 rules 4 and 7; rule 5's is config_paths.SHOWN_KEY).
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+-]*(/[A-Za-z0-9][A-Za-z0-9._:@+-]*)*")
MODEL_ID_MAX_BYTES, MODEL_ID_MAX_SEGMENTS = 128, 4
HARNESS_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
HARNESS_NAME_MAX_BYTES = 64
# The withheld reasons (§3.1).
NOT_A_MODEL_ID, NOT_A_NAME, NOT_A_HARNESS_NAME, CREDENTIAL_SHAPED = (
    "not_a_model_id", "not_a_name", "not_a_harness_name", "credential_shaped")
FIELD_WITHHELD = "field_withheld"
# A string over Appendix A's bound ("strings are at most 512 bytes unless stated") is withheld, never clipped: a clipped
# value would show content that is not the file's (the operator's decision on the F1a review, R5). An open code.
MAX_STRING_BYTES, TOO_LONG = 512, "too_long"


def _schema_keys(node: Any) -> set[str]:
    """Every key used anywhere in a schema document (properties' names included; the validator's keywords filter)."""
    if isinstance(node, dict):
        return set(node) | {k for v in node.values() for k in _schema_keys(v)}
    if isinstance(node, list):
        return {k for v in node for k in _schema_keys(v)}
    return set()


# The projection's data-code vocabulary: the codes it writes inside a successful read to describe a policy file's
# content (`document.yaml_error.code`, `document.violations[].code`). They are data, never a refusal's code; the one
# definition, which the code registry's test derives its outside namespace from (vertical-uat.md §8.4).
YAML_SYNTAX = "YAML_SYNTAX"  # a YAML syntax error, located by its line and column only (§7 rule 2)
# A document the structured walk cannot process (F1a review, R3): one violation at the root, no message.
UNPROCESSABLE = "UNPROCESSABLE"
UNPROCESSABLE_VIOLATION = {"path": "", "code": UNPROCESSABLE, "expected": None, "extra_key": None}
# A schema violation's code is the keyword that failed: every validation keyword the execution schema uses.
SCHEMA_KEYWORD_CODES = frozenset(Draft202012Validator.VALIDATORS) & frozenset(_schema_keys(schema(EXECUTION)))
DATA_CODES = frozenset({YAML_SYNTAX, UNPROCESSABLE, X.NO_SUCH_PROFILE, X.NO_DEFAULT_ROUTE, *SCHEMA_KEYWORD_CODES})


def too_long(value: Any) -> bool:
    return isinstance(value, str) and len(value.encode("utf-8")) > MAX_STRING_BYTES


# Edit scope (§3.3): in F46.2's first scope, a later slice, or never.
F46_2, LATER, NEVER = "F46.2", "later", "never"


def capability(state: str, *codes: str) -> dict[str, Any]:
    return {"state": state, "reasons": [{"code": c, "message": REASONS[c]} for c in codes]}


def config_digest(project_id: str, document: str, rel: str, adopted: str, on_disk: str) -> str:
    """The configuration digest (``aew/config-digest/v2``, §4.1): what a Save binds to. The one function; F46.2 calls
    it under the store lock with inputs it reads there. It leaves out the control revision, the manifest pin (for a
    policy document), other documents and the rendering, so an unrelated commit never makes a Save look stale."""
    body = {"v": DIGEST_SCHEME, "project_id": project_id, "document": document, "rel": rel, "adopted": adopted,
            "on_disk": on_disk}
    return "sha256:" + hashlib.sha256(canonical_json(body)).hexdigest()


def connection_id(project_id: str, harness: str, provider: str) -> str:
    """The opaque, stable id of a provider connection (§3.4, n4): over a canonical JSON list, since ``harness`` is a
    free string and a newline join would be ambiguous."""
    return "conn-" + hashlib.sha256(canonical_json([project_id, harness, provider])).hexdigest()[:16]


# ---------------------------------------------------------------------------------------------- documents (§3.2, §4)


@dataclass(frozen=True)
class Committed:
    """What one projection reads, once: the committed control state and the manifest's bytes."""

    state: dict[str, Any]
    manifest_raw: bytes | None
    manifest: dict[str, Any] | None  # parsed from manifest_raw (trusted only while manifest_ok)

    @property
    def manifest_ok(self) -> bool:
        return self.manifest_raw is not None and sha256_bytes(self.manifest_raw) == self.state["manifest_sha256"]

    @property
    def project_id(self) -> str:
        return str(self.state["project_id"])

    @property
    def policy_keys(self) -> dict[Any, Any]:
        policy = (self.manifest or {}).get("policy")
        return policy if isinstance(policy, dict) else {}


@dataclass(frozen=True)
class Document:
    """One logical document's inputs (§4.2) and what follows from them."""

    name: Any  # the logical name: `project`, a manifest policy key, or `execution` at its conventional path
    index: int
    rel: str | None  # the path under .aew, resolved only while the manifest matches its pin
    adopted: str
    on_disk: str
    raw: bytes | None
    valid: bool | None  # None when the bytes were not read (absent, or the manifest drifted)
    state: str
    in_force: bool
    digest: str
    same_file_as: int | None


def read_committed(k: Kernel) -> Committed:
    """The committed state and the manifest's bytes, without the control lock (``read_committed``) and without
    ``Kernel.manifest`` (which may take the lock to recover)."""
    state = k.store.read_committed()
    raw = read_lock_free(k.aew_root / MANIFEST)
    manifest = None
    if raw is not None:
        try:
            parsed = load_yaml(raw.decode("utf-8"), source=MANIFEST)
            manifest = parsed if isinstance(parsed, dict) else None
        except (ValidationFailed, UnicodeDecodeError):  # a drifted manifest that does not parse names no documents
            manifest = None
    return Committed(state, raw, manifest)


def _hash(raw: bytes | None) -> str:
    return sha256_bytes(raw) if raw is not None else ON_DISK_ABSENT


def _valid(name: str, raw: bytes, rel: str) -> bool:
    try:
        check_policy_bytes(name, raw, source=rel)
    except Exception:  # any failure to parse or check is INVALID (fail closed); its structure is §7's
        return False
    return True


def _project_document(c: Committed) -> Document:
    raw, adopted = c.manifest_raw, str(c.state["manifest_sha256"])
    if not c.manifest_ok:
        state, valid = DRIFTED, None
    else:
        try:
            validate("project", c.manifest, source=MANIFEST)
            state, valid = ADOPTED, True
        except ValidationFailed:
            state, valid = INVALID, False
    return Document(PROJECT, 0, MANIFEST, adopted, _hash(raw), raw, valid, state, state == ADOPTED,
                    config_digest(c.project_id, PROJECT, MANIFEST, adopted, _hash(raw)), None)


def _policy_state(pins: dict[str, Any] | None, rel: str, raw: bytes | None, valid: bool | None) -> tuple[str, str]:
    """``(state, adopted)`` for a policy document whose manifest matches its pin: §4.2's table, a function of the
    pins, the pin, the bytes on disk and whether they are valid."""
    if pins is None:
        if raw is None:
            return ABSENT, NO_PINS
        return (UNPINNED if valid else INVALID), NO_PINS
    if rel not in pins:
        return DRIFTED, NOT_IN_PINS
    pin = pins[rel]
    if pin is None:
        return (ABSENT if raw is None else DRIFTED), PINNED_ABSENT
    if raw is None or sha256_bytes(raw) != pin:
        return DRIFTED, str(pin)
    return (ADOPTED if valid else INVALID), str(pin)


IN_FORCE = {ADOPTED: True, UNPINNED: True, ABSENT: True}  # every other state is not in force


def documents(k: Kernel, c: Committed) -> list[Document]:
    """Every logical document (§3.2, T1, U1, R1): ``project``, then each key of the manifest's ``policy`` object in its
    order, then ``execution`` at its conventional path, last, when the manifest names none. Pins and drift are per
    file, so two keys naming one file report the same state; the later carries ``same_file_as``."""
    keys = c.policy_keys
    names: list[Any] = list(keys) + ([] if EXECUTION in keys else [EXECUTION])
    out = [_project_document(c)]
    if not c.manifest_ok:
        for i, name in enumerate(names, start=1):
            digest = config_digest(c.project_id, str(name), DRIFTED_INPUT, DRIFTED_INPUT, DRIFTED_INPUT)
            out.append(Document(name, i, None, DRIFTED_INPUT, DRIFTED_INPUT, None, None, MANIFEST_DRIFTED, False,
                                digest, None))
        return out
    pins = c.state.get(POLICY_PINS)
    rels = {name: str(keys[name]) if name in keys else X.REL_PATH for name in names}
    # A file is valid only if it validates under every logical name naming it (T1): two keys naming one file share
    # one state, so the execution policy's file always gets the execution check, whichever key comes last.
    named_as: dict[str, list[str]] = {}
    for name, rel in rels.items():
        named_as.setdefault(rel, []).append(str(name))
    first: dict[str, int] = {}
    read: dict[str, tuple[bytes | None, bool | None]] = {}
    for i, name in enumerate(names, start=1):
        rel = rels[name]
        if rel not in read:
            raw = read_lock_free(k.aew_root / rel)
            read[rel] = (raw, None if raw is None else all(_valid(n, raw, rel) for n in named_as[rel]))
        raw, valid = read[rel]
        state, adopted = _policy_state(pins, rel, raw, valid)
        out.append(Document(name, i, rel, adopted, _hash(raw), raw, valid, state, IN_FORCE.get(state, False),
                            config_digest(c.project_id, str(name), rel, adopted, _hash(raw)), first.get(rel)))
        first.setdefault(rel, i)
    return out


def _inventory_entry(d: Document) -> dict[str, Any]:
    supported = capability(AVAILABLE) if d.name == EXECUTION else capability(UNSUPPORTED, "AWAITS_LATER_F46")
    return {"document": d.name if P.shown_key(d.name) else None, "index": d.index, "same_file_as": d.same_file_as,
            "supported": supported, "state": d.state, "in_force": d.in_force, "digest": d.digest,
            "write": capability(UNSUPPORTED, "AWAITS_F46_2")}


def index_projection(k: Kernel) -> dict[str, Any]:
    """``/configuration`` (§3.2): the manifest's state, the four activities and every document."""
    c = read_committed(k)
    docs = documents(k, c)
    return {
        "manifest": {"state": ADOPTED if c.manifest_ok else DRIFTED},
        "activities": [{"activity": a, "capability": capability(s, *([r] if r else []))} for a, s, r in ACTIVITIES],
        "documents": [_inventory_entry(d) for d in docs[:MAX_DOCUMENTS]],
        "documents_truncated": len(docs) > MAX_DOCUMENTS,
    }


# ---------------------------------------------------------------------------------- structured errors (§7 rules 1-2)


def yaml_error(exc: BaseException | None) -> dict[str, Any]:
    """A YAML syntax error as its line and column only (§7 rule 2, N4): from the parser's ``problem_mark``, which
    ``util.load_yaml`` keeps as the ``ValidationFailed``'s cause, one-based; both null without a mark. Never the
    message, the path or a line of content."""
    mark = getattr(getattr(exc, "__cause__", None), "problem_mark", None)
    if mark is None:
        return {"code": YAML_SYNTAX, "line": None, "column": None}
    return {"code": YAML_SYNTAX, "line": int(mark.line) + 1, "column": int(mark.column) + 1}


def _expected(e: Any) -> str | None:
    """The schema's side of a violation only (the pattern, the type, the enum, a bound), never the instance."""
    value = e.validator_value
    if e.validator in ("type", "enum") and isinstance(value, list):
        return "|".join(map(str, value))
    if e.validator == "required" and isinstance(value, list) and isinstance(e.instance, dict):
        return "|".join(str(p) for p in value if p not in e.instance)
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def violations(data: Any) -> list[dict[str, Any]]:
    """The execution policy's violations as structure (§7 rule 1): ``{path, code, expected, extra_key}``, each path
    from the one encoder, each code the schema keyword (or a semantic code), never the validator's message."""
    out: list[dict[str, Any]] = []
    errors = iter_errors(EXECUTION, data)
    for e in errors:
        where = tuple(e.absolute_path)
        if "propertyNames" in e.schema_path:  # the key itself is the instance: locate it, never echo it
            out.append({"path": P.encode((*where, e.instance), data), "code": "propertyNames",
                        "expected": _expected(e), "extra_key": None})
        elif e.validator == "additionalProperties" and isinstance(e.instance, dict):
            known = set(e.schema.get("properties") or {})
            out += [{"path": P.encode(where, data), "code": "additionalProperties", "expected": None,
                     "extra_key": P.label(e.instance, key)} for key in e.instance if key not in known]
        else:
            out.append({"path": P.encode(where, data), "code": str(e.validator), "expected": _expected(e),
                        "extra_key": None})
    if not errors and isinstance(data, dict):
        out += [{"path": P.encode(where, data), "code": code, "expected": None, "extra_key": None}
                for where, code, _target in X.semantic_problems(data)]
    return sorted(out, key=lambda v: (v["path"], v["code"], v["extra_key"] or ""))


def parse_structured(raw: bytes) -> tuple[Any, list[dict[str, Any]], dict[str, Any] | None]:
    """``(document, violations, yaml_error)`` for an execution policy's bytes: the parsed document (None when it does
    not parse) and what is wrong with it, as structure. A document the walk cannot process (a nesting deep enough to
    exhaust the recursion limit, or any other failure) is one structured violation at the root, ``UNPROCESSABLE``,
    never an exception or its text."""
    try:
        data = load_yaml(raw.decode("utf-8"), source=X.REL_PATH)
    except UnicodeDecodeError:
        return None, [], yaml_error(None)
    except ValidationFailed as exc:
        return None, [], yaml_error(exc)
    except Exception:  # RecursionError and the like: fail closed, as structure
        return None, [UNPROCESSABLE_VIOLATION], None
    try:
        return data, violations(data), None
    except Exception:  # the validator's own walk (and its message formatting) can exhaust the recursion limit
        return None, [UNPROCESSABLE_VIOLATION], None


# ------------------------------------------------------------------------------------- field values (§3.1, §7)

Rule = Callable[[Any], "str | None"]  # a shown value's withheld reason, or None to show it


def _text(value: Any) -> str | None:
    return CREDENTIAL_SHAPED if isinstance(value, str) and credential_shaped(value) else None


def _name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None if isinstance(value, (bool, int, float)) else NOT_A_NAME
    if credential_shaped(value):
        return CREDENTIAL_SHAPED
    ok = P.SHOWN_KEY.fullmatch(value) is not None and len(value.encode("utf-8")) <= P.SHOWN_KEY_MAX_BYTES
    return None if ok else NOT_A_NAME


def _model_id(value: Any) -> str | None:
    text = str(value)
    if credential_shaped(text):
        return CREDENTIAL_SHAPED
    ok = (MODEL_ID.fullmatch(text) is not None and len(text.encode("utf-8")) <= MODEL_ID_MAX_BYTES
          and text.count("/") < MODEL_ID_MAX_SEGMENTS)
    return None if ok else NOT_A_MODEL_ID


def _harness(value: Any) -> str | None:
    text = str(value)
    if credential_shaped(text):
        return CREDENTIAL_SHAPED
    ok = HARNESS_NAME.fullmatch(text) is not None and len(text.encode("utf-8")) <= HARNESS_NAME_MAX_BYTES
    return None if ok else NOT_A_HARNESS_NAME


def _lookup(document: Any, location: tuple[Any, ...]) -> tuple[bool, Any]:
    node = document
    for step in location:
        if not isinstance(node, dict) or step not in node:
            return False, None
        node = node[step]
    return True, node


def _schema_nodes(location: tuple[Any, ...]) -> list[dict[str, Any]]:
    """The execution schema's nodes from the root along ``location`` ($refs resolved), for a field's metadata."""
    root = schema(EXECUTION)

    def deref(node: dict[str, Any]) -> dict[str, Any]:
        while "$ref" in node:
            node = root["$defs"][node["$ref"].rsplit("/", 1)[-1]]
        return node

    nodes = [root]
    node: dict[str, Any] = root
    for step in location:
        node = deref(node)
        props = node.get("properties") or {}
        child: Any = props.get(step) if isinstance(step, str) else None
        if child is None:
            child = next((node[k] for k in ("additionalProperties", "items") if isinstance(node.get(k), dict)), None)
        if not isinstance(child, dict):
            break
        node = child
        nodes.append(node)
        nodes.append(deref(node))
    return nodes


def _clip(text: str) -> str:
    raw = text.encode("utf-8")
    return text if len(raw) <= MAX_DESCRIPTION_BYTES else raw[:MAX_DESCRIPTION_BYTES - 3].decode(
        "utf-8", "ignore") + "…"


def field_metadata(location: tuple[Any, ...]) -> dict[str, Any]:
    """A field's ``class`` (the nearest ``x-aew-class``), ``allowed`` (its own schema ``enum``; absent otherwise, no
    invented enum) and ``description`` (its own only, never an enclosing object's: absent when the schema gives the
    field none, F1a review R7)."""
    nodes = _schema_nodes(location)
    out: dict[str, Any] = {"class": next((n["x-aew-class"] for n in reversed(nodes) if "x-aew-class" in n), None)}
    reached = len(nodes) == 1 + 2 * len(location)  # the walk reached the field itself (two nodes per step)
    own = nodes[-2:] if reached and location else []  # the field's node as written, and dereferenced
    enum = next((n["enum"] for n in own if isinstance(n.get("enum"), list)), None)
    if enum is not None and all(isinstance(v, str) for v in enum):
        out["allowed"] = list(enum)
    description = next((n["description"] for n in own if isinstance(n.get("description"), str)), None)
    if description is not None and not credential_shaped(description):
        out["description"] = _clip(description)
    return out


@dataclass
class _Projector:
    """Renders one execution policy document (``{}`` when no values are shown) into §3.3's shape."""

    k: Kernel
    c: Committed
    document: dict[str, Any]
    write_state: str

    def fv(self, location: tuple[Any, ...], rule: Rule, edit: str, *, value_of: Callable[[Any], Any] | None = None,
           effective: Any = None, effective_source: str | None = None) -> dict[str, Any]:
        """A FieldValue (§3.1): one withheld representation, a value absent when withheld, never ``null``."""
        path = P.encode(location, self.document)
        present, value = _lookup(self.document, location)
        out: dict[str, Any] = {"path": path}
        withheld = None
        if not present:
            out["state"] = "ABSENT"
        elif value is None:
            out.update(state="NULL", value=None)
        else:
            shown = value_of(value) if value_of else value
            withheld = None if value_of else rule(value) or (TOO_LONG if too_long(value) else None)
            out["state"] = "SET"
            if withheld:
                out["withheld"] = withheld
            else:
                out["value"] = shown
        if (effective is not None and rule(effective) is None and not too_long(effective)
                and not (withheld and effective == value)):
            out.update(effective=effective, effective_source=effective_source)
        meta = field_metadata(location)
        out.update(meta)
        out["edit"] = edit
        out["editable"] = edit == F46_2 and self.write_state == AVAILABLE and P.is_identity(path)
        return out

    # -------------------------------------------------------------------------------------------- profiles

    @property
    def profiles(self) -> dict[Any, Any]:
        value = self.document.get("profiles")
        return value if isinstance(value, dict) else {}

    @property
    def routing(self) -> dict[str, Any]:
        value = self.document.get("routing")
        return value if isinstance(value, dict) else {}

    def identity(self, key: Any, profile: dict[str, Any], fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """The profile's identity (C1's ``ModelIdentity``), its rule, or why there is none (§3.3, §5, §7 rules 7-8).
        Never derived from a withheld value; a non-builtin harness gets C1's inherited rule, with no import."""
        harness = X.profile_harness(self.document, profile)
        rule = "adapter" if harness in registry.BUILTIN else "inherited"
        none = {"identity": None, "identity_rule": rule, "identity_error": None, "harness": None, "provider": None}
        harness_why = _harness(harness)
        if harness_why:
            at = ("profiles", key, "harness") if "harness" in profile else ("harness",)
            return none | {"identity_rule": "inherited", "identity_error": self.withheld_error(harness_why, at)}
        for field in ("model", "provider"):
            if fields[field].get("withheld"):
                return none | {"identity_error": self.withheld_error(fields[field]["withheld"],
                                                                     ("profiles", key, field))}
        try:
            pair = X.model_pair(self.document, key, registry.model_identity if rule == "adapter" else None)
        except ModelIdRefused as exc:
            suggestion = next((s for s in exc.details.get("suggestions") or [] if _model_id(s) is None), None)
            return none | {"identity_error": {
                "code": str(exc.details.get("reason")), "withheld_reason": None,
                "field_path": P.encode(("profiles", key, "model"), self.document), "suggestion": suggestion,
                "hint": MODEL_ID_HINT}}
        found = pair.as_dict()
        if any(credential_shaped(v) for v in found.values()):
            return none | {"identity_error": self.withheld_error(CREDENTIAL_SHAPED, ("profiles", key, "model"))}
        return none | {"identity": found, "harness": harness, "provider": pair.provider}

    def withheld_error(self, why: str, location: tuple[Any, ...]) -> dict[str, Any]:
        return {"code": FIELD_WITHHELD, "withheld_reason": why, "field_path": P.encode(location, self.document),
                "suggestion": None, "hint": MODEL_ID_HINT}

    def routed_by(self, key: Any) -> list[str]:
        """What routes to profile ``key``, in resolution order (§3.3): a card id or archetype only when it may be
        shown, else ``@i`` from the one encoder."""
        out = []
        for table, kind in (("cards", "card"), ("classes", "class"), ("archetypes", "archetype")):
            routes = self.routing.get(table)
            if isinstance(routes, dict):
                out += [f"{kind}:{P.label(routes, r)}" for r, target in routes.items() if target == key]
        if self.routing.get("default") == key:
            out.append("default")
        return out

    def project_profiles(self) -> tuple[list[dict[str, Any]], dict[Any, str | None], list[dict[str, Any]]]:
        """``(profiles, connection id by profile key, connections)``. Connections are computed over every profile,
        so a truncated list never makes a profile look disconnected (§3.4, §3.5)."""
        rows, by_key, conns = [], {}, {}
        for index, (key, profile) in enumerate(self.profiles.items()):
            profile = profile if isinstance(profile, dict) else {}
            fields = {
                "harness": self.fv(("profiles", key, "harness"), _harness, F46_2,
                                   effective=X.profile_harness(self.document, profile),
                                   effective_source=("profile" if "harness" in profile else
                                                     "policy" if "harness" in self.document else "default")),
                "provider": self.fv(("profiles", key, "provider"), _model_id, F46_2),
                "model": self.fv(("profiles", key, "model"), _model_id, F46_2),
                "effort": self.fv(("profiles", key, "effort"), _text, F46_2),
                "max_steps": self.fv(("profiles", key, "max_steps"), _text, F46_2),
                "deadline_s": self.fv(("profiles", key, "deadline_s"), _text, F46_2),
                "description": self.fv(("profiles", key, "description"), _text, F46_2),
            }
            ident = self.identity(key, profile, fields)
            conn = None
            if ident["identity"] is not None:
                conn = connection_id(self.c.project_id, ident["harness"], ident["provider"])
                conns.setdefault((ident["harness"], ident["provider"]), (conn, []))[1].append(index)
            by_key[key] = conn
            routed = self.routed_by(key)
            rows.append({"name": key if P.shown_key(key) else None, "index": index,
                         "fields": fields, "identity": ident["identity"], "identity_rule": ident["identity_rule"],
                         "identity_error": ident["identity_error"], "connection_id": conn,
                         "routed_by": routed[:MAX_ROUTED_BY], "routed_by_truncated": len(routed) > MAX_ROUTED_BY})
        rows.sort(key=lambda r: (r["name"] is None, r["name"] or "", r["index"]))
        connections = [{
            "connection_id": cid, "harness": harness, "provider": provider,
            "profiles": members[:MAX_CONNECTION_PROFILES], "profiles_truncated": len(members) > MAX_CONNECTION_PROFILES,
            "credential_sources": {"provider_env": {"scope": "policy_wide", "ref": "/provider_env"},
                                   "saved_login": NOT_SUPPLIED},
            "endpoint": NOT_SUPPLIED, "catalog": capability(UNSUPPORTED, "AWAITS_F46_3"),
        } for (harness, provider), (cid, members) in conns.items()]
        return rows, by_key, connections

    # ------------------------------------------------------------------------------------- routing, providers

    def route_table(self, table: str) -> dict[str, Any]:
        routes = self.routing.get(table)
        routes = routes if isinstance(routes, dict) else {}
        entries = [{"key": key if P.shown_key(key) else None, "index": i,
                    "profile": self.fv(("routing", table, key), _name, F46_2)} for i, key in enumerate(routes)]
        return {"entries": entries[:MAX_ROUTE_ENTRIES], "truncated": len(entries) > MAX_ROUTE_ENTRIES}

    def provider_env(self, env: Mapping[str, str], observed_in: str) -> tuple[dict[str, Any], dict[str, Any]]:
        names = self.document.get("provider_env")
        names = names if isinstance(names, list) else []
        shape = re.compile(schema(EXECUTION)["properties"]["provider_env"]["items"]["pattern"])
        entries = []
        for i, name in enumerate(names):
            valid = isinstance(name, str) and shape.search(name) is not None
            shown = valid and not credential_shaped(name) and not too_long(name)
            entries.append({"index": i, "name": name if shown else None,
                            "valid_name": valid})
        listed = entries[:MAX_PROVIDER_ENV]
        configured = {"state": self.fv(("provider_env",), _text, F46_2, value_of=len), "entries": listed,
                      "entries_truncated": len(entries) > MAX_PROVIDER_ENV}
        observed = {
            "checked_in": observed_in, "caption": OBSERVED_CAPTIONS[observed_in],
            "provider_env": [{"index": e["index"], "name": e["name"],
                              "present": bool(e["valid_name"] and agentenv.lookup(env, names[e["index"]])),
                              "problem": (agentenv.provider_env_problem(names[e["index"]], env)
                                          if e["valid_name"] else None)} for e in listed],
            "provider_env_truncated": len(entries) > MAX_PROVIDER_ENV,
        }
        return configured, observed

    # ------------------------------------------------------------------------------------------- controls

    def controls(self) -> dict[str, Any]:
        envelope = {k: self.fv(("steering", "envelope", k), _text, LATER, effective=v if not _lookup(
            self.document, ("steering", "envelope", k))[0] else None, effective_source="default")
            for k, v in S.ENVELOPE_DEFAULTS.items()}
        effective = S.effective(self.c.state)
        containment = self.document.get("containment")
        containment = containment if isinstance(containment, dict) else {}
        notify = self.document.get("notify")
        notify = notify if isinstance(notify, dict) else {}

        def count(name: str) -> int:
            value = containment.get(name)
            return len(value) if isinstance(value, list) else 0

        return {
            "steering": {"mode": self.fv(("steering", "mode"), _text, LATER), "envelope": envelope,
                         "effective": {"mode": effective.get("mode"), "source": effective.get("source")}},
            "containment": {"mode": self.fv(("containment", "mode"), _text, LATER),
                            "writable_count": count("writable"), "hide_count": count("hide"),
                            "trusted_git_drivers_count": count("trusted_git_drivers"), "effective": NOT_SUPPLIED},
            "switches": [{"path": P.encode((block, key), self.document),
                          "value": self.fv((block, key), _text, LATER), "default": allowed[0]}
                         for (block, key), allowed in X.STRING_SWITCHES.items()][:MAX_SWITCHES],
            "notify": {"configured": bool(notify.get("command")),
                       "timeout_s": self.fv(("notify", "timeout_s"), _text, LATER),
                       "max_output_bytes": self.fv(("notify", "max_output_bytes"), _text, LATER)},
        }


def _execution_document(docs: list[Document]) -> Document:
    return next(d for d in docs if d.name == EXECUTION)


def execution_projection(k: Kernel, *, observed_in: str = CLI_ENVIRONMENT,
                         env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """``/configuration/execution`` (§3.3). Values are shown for ADOPTED and UNPINNED, and for a DRIFTED file whose
    on-disk content is valid (labelled not in force); an INVALID or drifted invalid file shows its violations only;
    ABSENT, a removed file and MANIFEST_DRIFTED show none."""
    if observed_in not in OBSERVED_CAPTIONS:
        raise ValueError(f"unknown observation site {observed_in!r}")
    c = read_committed(k)
    d = _execution_document(documents(k, c))
    found, yaml_err, document = [], None, {}
    if d.raw is not None:
        parsed, found, yaml_err = parse_structured(d.raw)
        # Values only for bytes with no structured violation: the projector never sees a document the execution
        # schema rejects, whatever the state says (F1a review R1).
        if d.valid and not found and yaml_err is None and isinstance(parsed, dict):
            document = parsed
    write = capability(UNSUPPORTED, "AWAITS_F46_2")
    proj = _Projector(k, c, document, write["state"])
    profiles, _by_key, connections = proj.project_profiles()
    provider_env, observed = proj.provider_env(os.environ if env is None else env, observed_in)
    # Only real inputs compare: while the manifest is drifted both are the same constant and nothing was read (R2).
    matches = c.manifest_ok and ((d.adopted == d.on_disk != ON_DISK_ABSENT)
                                 or (d.adopted == PINNED_ABSENT and d.on_disk == ON_DISK_ABSENT))
    return {
        "document": {"state": d.state, "in_force": d.in_force, "digest": d.digest, "on_disk_matches_adopted": matches,
                     "write": write, "violations": found[:MAX_VIOLATIONS],
                     "violations_truncated": len(found) > MAX_VIOLATIONS, "yaml_error": yaml_err},
        "configured": proj.fv(("configured",), _text, F46_2),
        "harness": proj.fv(("harness",), _harness, F46_2, effective=document.get("harness") or X.DEFAULT_HARNESS,
                           effective_source="policy" if "harness" in document else "default"),
        "description": proj.fv(("description",), _text, F46_2),
        "profiles": profiles[:MAX_PROFILES],
        "profiles_truncated": len(profiles) > MAX_PROFILES,
        "routing": {"default": proj.fv(("routing", "default"), _name, F46_2),
                    **{t: proj.route_table(t) for t in X.ROUTE_TABLES},
                    "resolution_order": list(RESOLUTION_ORDER)},
        "connections": connections[:MAX_CONNECTIONS],
        "connections_truncated": len(connections) > MAX_CONNECTIONS,
        "provider_env": provider_env,
        "observed": observed,
        "controls": proj.controls(),
        "pins_note": PINS_NOTE,
    }


class Configuration:
    """The configuration read projection's collaborator (register F46.1): reads only, takes no lock."""

    def __init__(self, k: Kernel) -> None:
        self.k = k

    def configuration(self, document: str | None = None, *, observed_in: str = CLI_ENVIRONMENT,
                      env: Mapping[str, str] | None = None) -> dict[str, Any]:
        """The index (``document`` None, §3.2) or one document's projection (``execution``, §3.3)."""
        if document is None:
            return index_projection(self.k)
        if document == EXECUTION:
            return execution_projection(self.k, observed_in=observed_in, env=env)
        raise UsageError(f"no field-by-field projection of {document!r}: the documents shown field by field are "
                         f"{', '.join(PROJECTED)}; with no document, `aew settings show` lists every document",
                         documents=list(PROJECTED))
