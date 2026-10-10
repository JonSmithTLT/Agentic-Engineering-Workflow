"""The maps projections' pure part: allowlists, caps, the byte cut and the typed diff (register F20.8, S1; the change
note ``docs/design/proposals/dashboard-maps-and-history-search-v0.1.md`` §4.2 and Appendix A).

A stored map is derived context, and its record is trusted no further than its schema (``codebase-map.schema.json``),
which bounds only the top-level section lists: the item objects, ``limits`` and every string are open, and an
integer may have thousands of digits. So nothing of a record is passed through. Each section is projected from its
own allowlist of item fields (:data:`SECTIONS`), with the API's own caps:

* every list is cut to its cap **before** anything is examined, and what is cut is added to the list's omitted count;
* a vocabulary field (``label``, ``kind``, ``status``, ``source``, ``runner``, ``rule``, ``code``, ``reason``, the
  caps-hit section and field names) must belong to the installed generator's vocabulary (:func:`vocabulary`): an
  item with another value is dropped and counted in ``dropped_items``; an unknown language name, in a row or as a
  key of the language counts, is dropped and counted in ``dropped_fields``;
* an item missing a field the contract requires, or holding one of the wrong type, is dropped (``dropped_items``);
  an optional field of the wrong type or range, and every unknown field, is dropped (``dropped_fields``);
* every number kept is an integer with ``0 <= n < 2**53`` (``type(v) is int``: ``bool`` is a subclass of ``int``)
  and every flag a ``bool``;
* every repository-derived string (``path``, ``name``, ``target``, ``pattern``, ``attributes_file``, ``extension``
  and the LFS pointers) is cut so that its serialized JSON form (UTF-8, ``ensure_ascii=False``, as the server sends
  it) is at most 512 bytes, never inside a character or an escape, and then marked with :data:`MARKER`;
  ``cut_strings`` counts the cuts. A control, format or separator character, which a generated record never holds
  (``canonical.render_bytes`` escapes them) but a planted one may, is escaped as the generator would.

The diff is typed and linear: a section's ``changed`` is the equality of the raw sections (the CLI's semantics), and
what changed is computed only after each list is cut to its cap, as sets of canonical JSON, never by a pairwise scan.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from itertools import islice
from typing import Any

from aew.dashboard.reasons import reason
from aew.harness.contract import CREDENTIAL_RE
from aew.maps import structural
from aew.maps.canonical import _ESCAPED
from aew.maps.rules import Rules

LABEL = "derived navigation context: never authority, and a stale or missing map blocks nothing"
ARCHITECTURE_NOTE = "navigation reference: selection is not truth, and a stale reference blocks nothing"
TEXT_BYTES = 512  # the serialized JSON form of a cut string, quotes included, before the marker
MARKER = " \\[cut]"  # an unpaired `\[` never comes from a rendered repository string (`\\` or `\xNN` only)
INT_LIMIT = 2**53  # JavaScript's exact integers: every count is below it
VOCAB_BYTES = 32  # the contract's MapVocab; a unit test holds the installed vocabulary to it
LANGUAGES_PER_ROW = 20
COUNTS_MAX = 100
VALUES_MAX = 128  # MapValueChanges' maxProperties
PATHS_SHOWN = 50  # changed or metadata paths in a freshness
OBJECT_ID = frozenset("0123456789abcdef")
REDACTED = "<redacted credential>"


# ---------------------------------------------------------------------------------------------- counting


@dataclass
class Tally:
    """What a projection cut and dropped."""

    cut: int = 0
    dropped_fields: int = 0
    dropped_items: int = 0

    def add(self, other: Tally) -> None:
        self.cut += other.cut
        self.dropped_fields += other.dropped_fields
        self.dropped_items += other.dropped_items


def bounded_int(value: Any) -> int | None:
    """``value`` when it is an integer the contract can carry (``0 <= n < 2**53``), else None."""
    return value if type(value) is int and 0 <= value < INT_LIMIT else None


def object_id(value: Any) -> str | None:
    """``value`` when it is a full lower-case object id (40 or 64 hex digits), else None."""
    if isinstance(value, str) and len(value) in (40, 64) and set(value) <= OBJECT_ID:
        return value
    return None


def sha256_id(value: Any) -> str | None:
    return value if isinstance(value, str) and len(value) == 64 and set(value) <= OBJECT_ID else None


def clamp(n: int) -> int:
    """A count the contract can carry."""
    return min(n, INT_LIMIT - 1)


# ---------------------------------------------------------------------------------------------- the byte cut


def _token(ch: str) -> str:
    """A character as the generator renders it: a control, format or separator character, or a lone surrogate,
    escaped per UTF-8 byte (``canonical._escape_char``); anything else, a backslash included, unchanged."""
    code = ord(ch)
    if 0xD800 <= code <= 0xDFFF:
        return f"\\u{code:04x}"
    if code in _ESCAPED:
        return "".join(f"\\x{b:02x}" for b in ch.encode("utf-8"))
    return ch


def _serialized(text: str) -> int:
    """The bytes ``text`` takes inside its JSON string as the server serializes it (``ensure_ascii=False``): a quote
    or a backslash is two, a C0 character six, anything else its UTF-8 length."""
    return sum(2 if ch in ('"', "\\") else 6 if ord(ch) < 0x20 else len(ch.encode("utf-8", "surrogatepass"))
               for ch in text)


def cut_text(value: str, tally: Tally) -> str:
    """``value`` with its serialized JSON form at most :data:`TEXT_BYTES` bytes (quotes included), cut between whole
    characters and whole escapes (``\\\\``, ``\\xNN``) and marked; counted in ``tally.cut`` when cut."""
    budget = TEXT_BYTES - 2
    if "aew1." in value:  # a credential-shaped string in a repository file is never shown (before the cut, so no
        value = CREDENTIAL_RE.sub(REDACTED, value)  # prefix of one survives either)
    if not any(ord(ch) in _ESCAPED or 0xD800 <= ord(ch) <= 0xDFFF for ch in value[:budget + 1]) and \
            len(value) <= budget and _serialized(value) <= budget:
        return value  # the common case, decided without walking the string
    out: list[str] = []
    used = 0
    i, n = 0, len(value)
    while i < n:
        ch = value[i]
        if ch == "\\" and i + 1 < n and value[i + 1] == "\\":
            piece, step = "\\\\", 2
        elif ch == "\\" and i + 3 < n and value[i + 1] == "x" and all(c in OBJECT_ID for c in value[i + 2:i + 4]):
            piece, step = value[i:i + 4], 4
        else:
            piece, step = _token(ch), 1
        size = _serialized(piece)
        if used + size > budget:
            tally.cut += 1
            return "".join(out) + MARKER
        out.append(piece)
        used += size
        i += step
    return "".join(out)


# ---------------------------------------------------------------------------------------------- the vocabulary


@cache
def _vocabulary(rules_sha: str, data_json: str) -> dict[str, frozenset[str]]:
    r = json.loads(data_json)
    languages = set(r["languages"].values()) | set(r["language_files"].values())
    build_kinds = {str(v["kind"]) for v in r["build_descriptors"].values() if isinstance(v, dict)}
    build_kinds |= {str(v) for v in r["build_descriptor_globs"].values()}
    caps_fields = {"rows_omitted", "submodules_omitted", "unknown_extensions_omitted", "omitted"}
    return {
        "directory_label": frozenset({"root", "unknown"} | set(r["directory_labels"].values())),
        "language": frozenset(languages),
        "build_kind": frozenset(build_kinds),
        "build_status": frozenset({"listed", "parsed", "parse_failed", "lfs_pointer", "symlink",
                                   structural.CAPPED_SIZE, structural.CAPPED_TOTAL}),
        "entry_label": frozenset({"declared", "convention"}),
        "entry_rule": frozenset(str(p) for p in r["entry_point_conventions"]),
        "test_kind": frozenset({"directory", "file_pattern", "runner_config"}),
        "test_runner": frozenset({"pytest", "npm test"} | {str(v) for v in r["test_runner_configs"].values()}),
        "test_source": frozenset({"convention", "declared"}),
        "gv_kind": frozenset({"generated", "vendored"}),
        "gv_source": frozenset({"convention", "gitattributes"}),
        "semantic_kind": frozenset({"pyright", "mypy"} | {str(v) for v in r["semantic_prerequisites"].values()}),
        "semantic_source": frozenset({"convention", "declared"}),
        "cap_section": frozenset(structural.SECTIONS),
        "cap_field": frozenset(caps_fields),
        "parse_code": frozenset({"not_utf8", "invalid_toml", "invalid_json", "invalid_ini"}),
        "unsupported_reason": frozenset({"symlink"}),
        "object_format": frozenset({"sha1", "sha256"}),
        "generator_name": frozenset({structural.NAME}),
    }


def vocabulary(rules: Rules) -> dict[str, frozenset[str]]:
    """The installed generator's fixed vocabulary, by field: the values ``structural.py`` writes and the installed
    rule table's own (change note §4.2). A value outside it never reaches a response."""
    return _vocabulary(rules.sha256, json.dumps(rules.data, sort_keys=True))


# ---------------------------------------------------------------------------------------------- items

TEXT, INT, OID, LANGS = "text", "int", "oid", "langs"


@dataclass(frozen=True)
class Field:
    kind: str  # TEXT, INT, OID, LANGS, or a vocabulary's name
    required: bool = False


ROW = {"path": Field(TEXT, True), "depth": Field(INT), "files": Field(INT), "languages": Field(LANGS, True),
       "label": Field("directory_label", True)}
SUBMODULE = {"path": Field(TEXT, True), "object": Field(OID)}
UNKNOWN_EXTENSION = {"extension": Field(TEXT, True), "files": Field(INT)}
BUILD_DESCRIPTOR = {"path": Field(TEXT, True), "kind": Field("build_kind", True), "status": Field("build_status", True)}
ENTRY_POINT = {"label": Field("entry_label", True), "path": Field(TEXT, True), "name": Field(TEXT),
               "target": Field(TEXT), "rule": Field("entry_rule")}
TEST_CANDIDATE = {"kind": Field("test_kind", True), "path": Field(TEXT), "pattern": Field(TEXT), "files": Field(INT),
                  "runner": Field("test_runner"), "source": Field("test_source")}
GENERATED_OR_VENDOR = {"kind": Field("gv_kind", True), "source": Field("gv_source", True),
                       "pattern": Field(TEXT, True), "files": Field(INT), "attributes_file": Field(TEXT)}
SEMANTIC_PREREQUISITE = {"path": Field(TEXT, True), "kind": Field("semantic_kind", True),
                         "source": Field("semantic_source", True)}
CAP_HIT = {"section": Field("cap_section", True), "field": Field("cap_field", True), "limit": Field(INT),
           "omitted": Field(INT)}
PARSE_FAILURE = {"path": Field(TEXT, True), "code": Field("parse_code", True)}
UNSUPPORTED = {"path": Field(TEXT, True), "reason": Field("unsupported_reason", True)}
BARE_TEXT: dict[str, Field] = {}  # a list of strings (the LFS pointers), not of objects


class _Drop(Exception):
    """The item is dropped (``dropped_items``)."""


def _languages(value: Any, vocab: dict[str, frozenset[str]], tally: Tally) -> tuple[list[str], int]:
    if not isinstance(value, list):
        raise _Drop
    kept = []
    for name in value[:LANGUAGES_PER_ROW]:
        if isinstance(name, str) and name in vocab["language"]:
            kept.append(name)
        else:
            tally.dropped_fields += 1
    return kept, max(0, len(value) - LANGUAGES_PER_ROW)


def project_item(raw: Any, spec: dict[str, Field], vocab: dict[str, frozenset[str]], tally: Tally) -> Any:
    """One list item through its allowlist, or None when it is dropped (counted in ``tally``)."""
    mine = Tally()
    try:
        if spec is BARE_TEXT:
            if not isinstance(raw, str):
                raise _Drop
            out: Any = cut_text(raw, mine)
        else:
            if not isinstance(raw, dict):
                raise _Drop
            out = {}
            mine.dropped_fields += sum(1 for k in raw if k not in spec)
            for name, f in spec.items():
                if name not in raw:
                    if f.required:
                        raise _Drop
                    continue
                value = raw[name]
                kept: Any = None
                if f.kind == TEXT:
                    kept = cut_text(value, mine) if isinstance(value, str) else None
                elif f.kind == INT:
                    kept = bounded_int(value)
                elif f.kind == OID:
                    kept = object_id(value)
                elif f.kind == LANGS:
                    kept, omitted = _languages(value, vocab, mine)
                    out["languages_omitted"] = omitted
                elif isinstance(value, str) and value in vocab[f.kind]:
                    kept = value
                else:
                    raise _Drop  # an unknown vocabulary value: the whole item goes (change note §4.2)
                if kept is None:
                    if f.required:
                        raise _Drop
                    mine.dropped_fields += 1
                    continue
                out[name] = kept
    except _Drop:
        tally.dropped_items += 1
        return None
    tally.add(mine)
    return out


def project_list(raw: Any, cap: int, spec: dict[str, Field], vocab: dict[str, frozenset[str]],
                 tally: Tally) -> tuple[list[Any], int]:
    """A list cut to ``cap`` before anything is examined, then each item through its allowlist; returns the items
    and the number cut. A value that is not a list is no list (``dropped_fields``)."""
    if not isinstance(raw, list):
        if raw is not None:
            tally.dropped_fields += 1
        return [], 0
    items = [project_item(i, spec, vocab, tally) for i in raw[:cap]]
    return [i for i in items if i is not None], max(0, len(raw) - cap)


# ---------------------------------------------------------------------------------------------- sections


@dataclass(frozen=True)
class Section:
    lists: dict[str, tuple[int, dict[str, Field]]]  # list -> (the API's cap, the item allowlist)
    omitted: dict[str, str]  # list -> its omitted counter in the response
    counters: tuple[str, ...]  # the section's own counters, kept as they are
    required_omitted: tuple[str, ...] = ()  # omitted counters the response always carries
    record_omitted: dict[str, str] = field(default_factory=dict)  # list -> the record's own omitted counter

    def known(self) -> set[str]:
        return set(self.lists) | set(self.record_omitted.values()) | set(self.counters)


C = structural.CAPS
SECTIONS: dict[str, Section] = {
    "directories": Section(
        lists={"rows": (C["directories"], ROW), "submodules": (C["submodules"], SUBMODULE)},
        omitted={"rows": "rows_omitted", "submodules": "submodules_omitted"},
        counters=("max_depth", "rows_total"),
        record_omitted={"rows": "rows_omitted", "submodules": "submodules_omitted"}),
    "languages": Section(
        lists={"unknown_extensions": (C["unknown_extensions"], UNKNOWN_EXTENSION)},
        omitted={"unknown_extensions": "unknown_extensions_omitted"},
        counters=("unknown_files",),
        required_omitted=("counts_omitted",),
        record_omitted={"unknown_extensions": "unknown_extensions_omitted"}),
    "build_descriptors": Section(lists={"items": (C["build_descriptors"], BUILD_DESCRIPTOR)},
                                 omitted={"items": "omitted"}, counters=(), record_omitted={"items": "omitted"}),
    "entry_point_candidates": Section(lists={"items": (C["entry_point_candidates"], ENTRY_POINT)},
                                      omitted={"items": "omitted"}, counters=(), record_omitted={"items": "omitted"}),
    "test_candidates": Section(lists={"items": (C["test_candidates"], TEST_CANDIDATE)},
                               omitted={"items": "omitted"}, counters=(), record_omitted={"items": "omitted"}),
    "generated_and_vendor": Section(lists={"items": (C["generated_and_vendor"], GENERATED_OR_VENDOR)},
                                    omitted={"items": "omitted"}, counters=(), record_omitted={"items": "omitted"}),
    "semantic_prerequisites": Section(lists={"items": (C["semantic_prerequisites"], SEMANTIC_PREREQUISITE)},
                                      omitted={"items": "omitted"}, counters=(), record_omitted={"items": "omitted"}),
    "limits_and_omissions": Section(
        lists={"caps_hit": (20, CAP_HIT), "parse_failures": (100, PARSE_FAILURE),
               "unsupported": (100, UNSUPPORTED), "lfs_pointers": (100, BARE_TEXT)},
        omitted={"caps_hit": "caps_hit_omitted", "parse_failures": "parse_failures_omitted",
                 "unsupported": "unsupported_omitted", "lfs_pointers": "lfs_pointers_omitted"},
        counters=("metadata_unread", "non_utf8_names", "symlinks", "submodules", "unknown_extension_files"),
        record_omitted={"parse_failures": "parse_failures_omitted", "unsupported": "unsupported_omitted",
                        "lfs_pointers": "lfs_pointers_omitted"}),
}
assert tuple(SECTIONS) == structural.SECTIONS


def _language_counts(raw: Any, vocab: dict[str, frozenset[str]], tally: Tally) -> tuple[dict[str, int], int]:
    if not isinstance(raw, dict):
        if raw is not None:
            tally.dropped_fields += 1
        return {}, 0
    counts: dict[str, int] = {}
    for key, value in islice(raw.items(), COUNTS_MAX):
        n = bounded_int(value)
        if key in vocab["language"] and n is not None:
            counts[key] = n
        else:
            tally.dropped_fields += 1
    return counts, max(0, len(raw) - COUNTS_MAX)


def project_section(name: str, raw: Any, vocab: dict[str, frozenset[str]], tally: Tally) -> dict[str, Any]:
    """One section through its allowlist: its lists cut and checked, its counters typed, the API's cuts added to
    the omitted counts, and its own ``dropped_fields`` and ``dropped_items``. ``tally`` collects the cuts."""
    spec = SECTIONS[name]
    mine = Tally()
    section = raw if isinstance(raw, dict) else {}
    if not isinstance(raw, dict):
        mine.dropped_fields += 1
    known = spec.known() | ({"counts"} if name == "languages" else set())
    mine.dropped_fields += sum(1 for k in section if k not in known)
    out: dict[str, Any] = {}
    for key in spec.counters:
        if key in section:
            n = bounded_int(section[key])
            if n is None:
                mine.dropped_fields += 1
            else:
                out[key] = n
    for list_name, (cap, item_spec) in spec.lists.items():
        items, cut = project_list(section.get(list_name), cap, item_spec, vocab, mine)
        out[list_name] = items
        own_key = spec.record_omitted.get(list_name)
        own = None
        if own_key is not None and own_key in section:
            own = bounded_int(section[own_key])
            if own is None:
                mine.dropped_fields += 1
        if own is not None or cut:
            out[spec.omitted[list_name]] = clamp((own or 0) + cut)
    if name == "languages":
        out["counts"], out["counts_omitted"] = _language_counts(section.get("counts"), vocab, mine)
    for key in spec.required_omitted:
        out.setdefault(key, 0)
    out["dropped_fields"] = mine.dropped_fields
    out["dropped_items"] = mine.dropped_items
    tally.add(mine)
    return out


LIMITS = {"tracked_paths": {"seen": INT, "capped": "bool"},
          "metadata_bytes": {"read": INT, "limit": INT, "capped": "bool"},
          "metadata_blob_bytes": {"limit": INT, "skipped": INT}}


def project_limits(raw: Any, tally: Tally) -> dict[str, Any]:
    """``limits``, allowlisted field by field: nothing else under it is projected (the change note §4.2)."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        tally.dropped_fields += 1
        return out
    tally.dropped_fields += sum(1 for k in raw if k not in LIMITS)
    for group, fields in LIMITS.items():
        if group not in raw:
            continue
        value = raw[group]
        if not isinstance(value, dict):
            tally.dropped_fields += 1
            continue
        tally.dropped_fields += sum(1 for k in value if k not in fields)
        kept: dict[str, Any] = {}
        for name, kind in fields.items():
            if name not in value:
                continue
            v = bounded_int(value[name]) if kind == INT else (value[name] if type(value[name]) is bool else None)
            if v is None:
                tally.dropped_fields += 1
            else:
                kept[name] = v
        out[group] = kept
    return out


def inputs_summary(record: dict[str, Any]) -> dict[str, Any]:
    """The inputs' counts (the list itself is paged by ``/inputs``); the record's schema closes each input."""
    metadata = record["inputs"]["metadata"]
    return {"path_listing_sha256": record["inputs"]["path_listing_sha256"], "count": clamp(len(metadata)),
            "read": sum(1 for i in metadata if i["read"] is True),
            "capped_size": sum(1 for i in metadata if i.get("reason") == structural.CAPPED_SIZE),
            "capped_total": sum(1 for i in metadata if i.get("reason") == structural.CAPPED_TOTAL)}


def generator(record: dict[str, Any], vocab: dict[str, frozenset[str]]) -> dict[str, Any] | None:
    g = record.get("generator")
    if not isinstance(g, dict):
        return None
    version, sha = bounded_int(g.get("version")), sha256_id(g.get("ruleset_sha256"))
    if g.get("name") not in vocab["generator_name"] or version is None or sha is None:
        return None
    return {"name": g["name"], "version": version, "ruleset_sha256": sha}


def summary(root: str, *, selected: bool, record: dict[str, Any] | None, vocab: dict[str, frozenset[str]],
            corrupt: str | None = None) -> dict[str, Any]:
    """A stored map's ``MapSummary``: named by its root only; the record-derived fields are null when it is corrupt."""
    if record is None:
        return {"root": root, "status": "CORRUPT",
                "reasons": [reason("MAP_CORRUPT", f"the stored map is corrupt ({corrupt or 'unreadable'}): delete "
                                                  "it and generate the map again")],
                "selected": selected, "source_revision": None, "source_tree": None, "object_format": None,
                "generator": None}
    fmt = record.get("object_format")
    return {"root": root, "status": "AVAILABLE", "reasons": [], "selected": selected,
            "source_revision": object_id(record.get("source_revision")),
            "source_tree": object_id(record.get("source_tree")),
            "object_format": fmt if fmt in vocab["object_format"] else None, "generator": generator(record, vocab)}


@dataclass
class Detail:
    """A record's projection, kept by the reader's cache: everything of a detail but its freshness."""

    limits: dict[str, Any]
    inputs: dict[str, Any]
    sections: dict[str, dict[str, Any]]
    section_cuts: dict[str, int]
    dropped_fields: int  # outside the sections: ``limits``
    size: int  # its serialized size, for the size-aware cache


def project_record(record: dict[str, Any], vocab: dict[str, frozenset[str]]) -> Detail:
    tally = Tally()
    limits = project_limits(record.get("limits"), tally)
    sections, cuts = {}, {}
    raw_sections = record.get("sections") or {}
    for name in SECTIONS:
        mine = Tally()
        sections[name] = project_section(name, raw_sections.get(name), vocab, mine)
        cuts[name] = mine.cut
    detail = Detail(limits, inputs_summary(record), sections, cuts, tally.dropped_fields, 0)
    detail.size = len(json.dumps([limits, detail.inputs, sections], ensure_ascii=False).encode("utf-8"))
    return detail


# ---------------------------------------------------------------------------------------------- inputs


def project_input(raw: dict[str, Any], tally: Tally) -> dict[str, Any]:
    """One ``inputs.metadata`` item: the schema closes it, so only ``size``'s range and the cut remain."""
    out: dict[str, Any] = {"path": cut_text(raw["path"], tally), "read": raw["read"] is True}
    oid = object_id(raw.get("git_oid"))
    if oid is not None:
        out["git_oid"] = oid
    size = bounded_int(raw.get("size"))
    if size is None:
        tally.dropped_fields += 1
    else:
        out["size"] = size
    if "sha256" in raw:
        out["sha256"] = raw["sha256"]
    if "reason" in raw:
        out["reason"] = raw["reason"]
    return out


# ---------------------------------------------------------------------------------------------- freshness

STALE_CODES = {"generator": "MAP_STALE_GENERATOR", "path_listing": "MAP_STALE_PATH_LISTING",
               "metadata": "MAP_STALE_METADATA"}
UNPROVEN = {
    "partial_clone": "a partial clone on a git that cannot be told not to fetch missing objects lazily",
    "unknown_commit": "the commit does not resolve in this repository",
    "unknown_source": "the map's source tree is not in this repository",
    "missing_object": "a git object it needs is missing from this repository (a partial clone?)",
    "timeout": "git did not answer within the dashboard's bound; read again later",
}


def map_freshness(fresh: dict[str, Any], tally: Tally) -> dict[str, Any]:
    """``maps.freshness.freshness``'s answer as a ``MapFreshness``: STALE and UNKNOWN stay visible with their reasons
    (T5-INV-10)."""
    status = str(fresh.get("status"))
    reasons = []
    for cause in fresh.get("reasons") or []:
        if status == "UNKNOWN":
            reasons.append(reason("MAP_CURRENTNESS_UNPROVEN", "the map's currentness cannot be proven: "
                                  + UNPROVEN.get(str(cause), "the cause is not known")))
        elif cause in STALE_CODES:
            reasons.append(reason(STALE_CODES[cause]))
    paths = [cut_text(p, tally) for p in (fresh.get("metadata_paths") or [])[:PATHS_SHOWN] if isinstance(p, str)]
    omitted = bounded_int(fresh.get("metadata_paths_omitted")) or 0
    return {"status": status, "reasons": reasons, "against_commit": object_id(fresh.get("against_commit")),
            "against_tree": object_id(fresh.get("against_tree")), "metadata_paths": paths,
            "metadata_paths_omitted": omitted}


def architecture(ref: dict[str, Any] | None, *, valid_id: Callable[[str], bool], tally: Tally) -> dict[str, Any] | None:
    """``maps.service.architecture``'s answer as an ``ArchitectureReference``, or None when none is selected."""
    if ref is None:
        return None
    ident = ref.get("evidence_id")
    evidence = {"id": ident, "kind": "evidence", "title": None} if isinstance(ident, str) and valid_id(ident) else None
    fresh = ref.get("freshness") or {}
    status = str(fresh.get("status") or "UNAVAILABLE")
    detail = fresh.get("detail")
    detail = detail if isinstance(detail, str) and len(detail) <= 300 else None
    code = {"STALE": "ARCHITECTURE_STALE", "UNKNOWN": "ARCHITECTURE_UNKNOWN",
            "UNAVAILABLE": "ARCHITECTURE_UNAVAILABLE"}.get(status)
    reasons = [reason(code, f"{reason(code)['message']}: {detail}" if detail and status == "UNKNOWN" else None)] \
        if code else []
    changed = [p for p in fresh.get("changed_paths") or [] if isinstance(p, str)]

    def vocab_text(value: Any) -> str | None:
        return value if isinstance(value, str) and 0 < len(value.encode("utf-8")) <= VOCAB_BYTES else None

    return {"evidence": evidence,
            "freshness": {"status": status, "reasons": reasons, "basis": vocab_text(fresh.get("basis")),
                          "observed_commit": object_id(fresh.get("observed_commit")),
                          "authoritative_commit": object_id(fresh.get("authoritative_commit")),
                          "scope": vocab_text(fresh.get("scope")),
                          "changed_paths": [cut_text(p, tally) for p in changed[:PATHS_SHOWN]],
                          "changed_paths_omitted": clamp(max(0, len(changed) - PATHS_SHOWN))},
            "note": ARCHITECTURE_NOTE}


# ---------------------------------------------------------------------------------------------- the diff


def canon(item: Any) -> str:
    """An item's identity in a diff: its canonical JSON (one call per item: the comparison is linear)."""
    return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _list_diff(x: Any, y: Any, cap: int, spec: dict[str, Field], vocab: dict[str, frozenset[str]],
               tally: Tally) -> tuple[dict[str, list[Any]], bool]:
    """The ``added`` and ``removed`` items of one list, each side cut to ``cap`` first and compared as sets of
    canonical JSON; and whether the lists differ only past the cap."""
    xs = x if isinstance(x, list) else []
    ys = y if isinstance(y, list) else []
    a = [(canon(i), i) for i in xs[:cap]]
    b = [(canon(i), i) for i in ys[:cap]]
    in_a, in_b = {k for k, _ in a}, {k for k, _ in b}
    added_raw = [i for k, i in b if k not in in_a]
    removed_raw = [i for k, i in a if k not in in_b]
    added = [p for p in (project_item(i, spec, vocab, tally) for i in added_raw) if p is not None]
    removed = [p for p in (project_item(i, spec, vocab, tally) for i in removed_raw) if p is not None]
    beyond = not added_raw and not removed_raw and xs != ys
    return {"added": added, "removed": removed}, beyond


def _value(raw: Any, tally: Tally) -> int | bool | None:
    if raw is None:
        return None
    if type(raw) is bool:
        return raw
    n = bounded_int(raw)
    if n is None:
        tally.dropped_fields += 1
    return n


def _counters(spec: Section) -> tuple[str, ...]:
    """A section's counters as the record holds them: its own and its lists' omitted counts."""
    return tuple(dict.fromkeys(spec.counters + tuple(spec.record_omitted.values())))


def section_diff(name: str, x: Any, y: Any, vocab: dict[str, frozenset[str]], tally: Tally) -> dict[str, Any]:
    """One section's typed change. ``beyond_cap`` says a difference is not shown: a list differs only past its cap,
    the counters exceed what one response carries, or the sections differ only in what the allowlists leave out."""
    if x == y:
        return {"changed": False, "beyond_cap": False, "values": {}}
    spec = SECTIONS[name]
    xs = x if isinstance(x, dict) else {}
    ys = y if isinstance(y, dict) else {}
    out: dict[str, Any] = {"changed": True, "beyond_cap": False}
    beyond = False
    shown = False
    for list_name, (cap, item_spec) in spec.lists.items():
        change, past = _list_diff(xs.get(list_name), ys.get(list_name), cap, item_spec, vocab, tally)
        out[list_name] = change
        beyond = beyond or past
        shown = shown or bool(change["added"] or change["removed"])
    values: dict[str, Any] = {}
    for key in _counters(spec):
        if xs.get(key) != ys.get(key):
            frm, to = _value(xs.get(key), tally), _value(ys.get(key), tally)
            if frm != to or type(frm) is not type(to):
                values[key] = {"from": frm, "to": to}
    if name == "languages":
        xc: dict[Any, Any] = xs["counts"] if isinstance(xs.get("counts"), dict) else {}
        yc: dict[Any, Any] = ys["counts"] if isinstance(ys.get("counts"), dict) else {}
        keys = sorted(set(islice(xc, COUNTS_MAX)) | set(islice(yc, COUNTS_MAX)))
        for key in keys:
            if xc.get(key) == yc.get(key):
                continue
            if not isinstance(key, str) or key not in vocab["language"]:
                tally.dropped_fields += 1
                continue
            if len(values) >= VALUES_MAX:
                beyond = True
                break
            values[f"counts.{key}"] = {"from": _value(xc.get(key), tally), "to": _value(yc.get(key), tally)}
        if len(xc) > COUNTS_MAX or len(yc) > COUNTS_MAX:  # the language counts past the cap, compared linearly
            beyond = beyond or dict(islice(xc.items(), COUNTS_MAX, None)) != dict(islice(yc.items(), COUNTS_MAX, None))
    out["values"] = values
    out["beyond_cap"] = beyond or not (shown or values)
    return out


ENVELOPE_FIELDS = ("source_revision", "source_tree", "object_format")


def operand(record: dict[str, Any]) -> dict[str, Any]:
    return {"root": record["artifact_sha256"], "source_revision": record["source_revision"],
            "source_tree": record["source_tree"]}


def diff(a: dict[str, Any], b: dict[str, Any], vocab: dict[str, frozenset[str]]) -> dict[str, Any]:
    """Two schema-valid records' typed comparison (``MapDiffResponse.data``)."""
    tally = Tally()
    envelope: dict[str, Any] = {}
    for key in ENVELOPE_FIELDS:
        if a[key] != b[key]:
            envelope[key] = {"from": a[key], "to": b[key]}
    if a["generator"] != b["generator"]:
        ga, gb = generator(a, vocab), generator(b, vocab)
        if ga is not None and gb is not None:
            envelope["generator"] = {"from": ga, "to": gb}
        else:
            tally.dropped_fields += 1
    pa, pb = a["inputs"]["path_listing_sha256"], b["inputs"]["path_listing_sha256"]
    if pa != pb:
        envelope["path_listing_sha256"] = {"from": pa, "to": pb}
    sections = {name: section_diff(name, a["sections"][name], b["sections"][name], vocab, tally) for name in SECTIONS}
    return {"a": operand(a), "b": operand(b), "identical": a["artifact_sha256"] == b["artifact_sha256"],
            "envelope": envelope, "sections": sections, "cut_strings": clamp(tally.cut),
            "dropped_fields": clamp(tally.dropped_fields), "dropped_items": clamp(tally.dropped_items),
            "label": LABEL}
