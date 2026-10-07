"""The structural generator (T5-A; design v0.5 §2.2 to §2.4; plan §2, §3).

A pure function of a tracked tree and the rule table. It imports no process, file, stream or workspace module and
never calls ``open`` (``tests/unit/test_structural_map.py`` walks this module's AST), so no repository byte reaches it
except through ``Tree.read``, which logs every input it serves: the record's ``inputs.metadata`` is the tracker's log,
never a hand-maintained list (PMP-27, decision 3).

What it reads: the descriptors with a bounded parser at depth <= 2 and every ``.gitattributes``, regular blobs only (a
symlink is listed, never read or followed; a gitlink is a path plus its object id, never traversed). A blob over
256 KiB (by the listing's size) is not read and is logged ``capped_size``; reads stop at 2 MiB in total and the rest are
logged ``capped_total``. An LFS pointer is recorded as such and not parsed. A parse failure is recorded, never raised.

Every section is bounded and deterministic: sorted, capped, with what was cut counted. Every repository-derived string
is a rendered name or ``render_text`` (escaped and bounded): map text is data (T5-INV-07).

``VERSION`` is part of the generator's identity with the rule table's sha256: a change here that alters any output
bytes must bump it (the golden test fails until it does), so freshness reports older maps ``STALE (generator)``.
"""

from __future__ import annotations

import configparser
import json
import tomllib
from collections import Counter, defaultdict
from collections.abc import Callable
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Any, Protocol

from aew.maps.canonical import Entry, render_text

if TYPE_CHECKING:
    from aew.maps.rules import Rules

SCHEMA = "aew/codebase-map/v1"
NAME = "structural"
VERSION = 1

BLOB_LIMIT = 256 * 1024
METADATA_LIMIT = 2 * 1024 * 1024
DESCRIPTOR_DEPTH = 2  # descriptors are read at depth <= 2 (the number of directories above them)
DIRECTORY_DEPTH = 3
CAPS = {"directories": 200, "submodules": 200, "unknown_extensions": 20, "build_descriptors": 200,
        "entry_point_candidates": 100, "test_candidates": 100, "generated_and_vendor": 200,
        "semantic_prerequisites": 100, "omissions": 100}
SECTIONS = ("directories", "languages", "build_descriptors", "entry_point_candidates", "test_candidates",
            "generated_and_vendor", "semantic_prerequisites", "limits_and_omissions")
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"
GITATTRIBUTES = ".gitattributes"
CAPPED_SIZE, CAPPED_TOTAL = "capped_size", "capped_total"
GENERATED = {"linguist-generated", "linguist-generated=true", "linguist-generated=set"}
VENDORED = {"linguist-vendored", "linguist-vendored=true", "linguist-vendored=set"}


class Tree(Protocol):
    """What the generator may see: the listing, and blobs through the tracked read (``gitobjects.TrackedTree``)."""

    commit: str
    tree: str
    object_format: str
    entries: tuple[Entry, ...]

    def entry(self, path: str) -> Entry: ...

    def read(self, path: str) -> bytes: ...

    def skip(self, path: str, reason: str) -> None: ...

    def inputs(self) -> list[dict[str, Any]]: ...

    def listing_sha256(self) -> str: ...


def generator_identity(rules: Rules) -> dict[str, Any]:
    return {"name": NAME, "version": VERSION, "ruleset_sha256": rules.sha256}


def _name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _depth(path: str) -> int:
    return path.count("/")


def _ancestors(path: str) -> list[str]:
    parts = path.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _extension(name: str) -> str:
    i = name.rfind(".")
    return name[i:].lower() if i > 0 else ""


def _capped(items: list[Any], cap: int) -> tuple[list[Any], int]:
    return items[:cap], max(0, len(items) - cap)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class _Facts:
    """What the bounded parsers found, and what happened to each candidate blob."""

    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.entry_points: list[dict[str, Any]] = []
        self.runners: list[dict[str, Any]] = []
        self.prerequisites: list[dict[str, Any]] = []
        self.attributes: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.unsupported: list[dict[str, Any]] = []
        self.lfs: list[str] = []

    def entry(self, path: str, name: str, target: str) -> None:
        self.entry_points.append({"label": "declared", "path": path, "name": render_text(name),
                                  "target": render_text(target)})

    def runner(self, path: str, runner: str) -> None:
        self.runners.append({"kind": "runner_config", "path": path, "runner": runner, "source": "declared"})

    def prerequisite(self, path: str, kind: str) -> None:
        self.prerequisites.append({"path": path, "kind": kind, "source": "declared"})


# ------------------------------------------------------------------------------------------- bounded parsers


def _pyproject(path: str, text: str, f: _Facts) -> None:
    doc = tomllib.loads(text)
    project = _dict(doc.get("project"))
    for key in ("scripts", "gui-scripts"):
        for name, target in _dict(project.get(key)).items():
            if isinstance(target, str):
                f.entry(path, name, target)
    tool = _dict(doc.get("tool"))
    for name, target in _dict(_dict(tool.get("poetry")).get("scripts")).items():
        if isinstance(target, str):
            f.entry(path, name, target)
    if isinstance(_dict(tool.get("pytest")).get("ini_options"), dict):
        f.runner(path, "pytest")
    for kind in ("pyright", "mypy"):
        if isinstance(tool.get(kind), dict):
            f.prerequisite(path, kind)


def _package_json(path: str, text: str, f: _Facts) -> None:
    doc = json.loads(text)
    if not isinstance(doc, dict):
        return
    package = doc.get("name") if isinstance(doc.get("name"), str) else "bin"
    binary = doc.get("bin")
    if isinstance(binary, str):
        f.entry(path, str(package), binary)
    for name, target in _dict(binary).items():
        if isinstance(target, str):
            f.entry(path, name, target)
    for key in ("main", "module"):
        if isinstance(doc.get(key), str):
            f.entry(path, key, doc[key])
    if isinstance(_dict(doc.get("scripts")).get("test"), str):
        f.runner(path, "npm test")


def _cargo(path: str, text: str, f: _Facts) -> None:
    doc = tomllib.loads(text)
    bins = doc.get("bin")
    for item in bins if isinstance(bins, list) else []:
        item = _dict(item)
        if isinstance(item.get("name"), str):
            f.entry(path, item["name"], item["path"] if isinstance(item.get("path"), str) else "")


def _setup_cfg(path: str, text: str, f: _Facts) -> None:
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_string(text)
    if cp.has_section("options.entry_points"):
        for key in ("console_scripts", "gui_scripts"):
            for line in cp.get("options.entry_points", key, fallback="").splitlines():
                name, _, target = line.partition("=")
                if name.strip() and target.strip():
                    f.entry(path, name.strip(), target.strip())
    if cp.has_section("tool:pytest"):
        f.runner(path, "pytest")


PARSERS: dict[str, tuple[Callable[[str, str, _Facts], None], str]] = {
    "pyproject": (_pyproject, "invalid_toml"), "cargo": (_cargo, "invalid_toml"),
    "package_json": (_package_json, "invalid_json"), "setup_cfg": (_setup_cfg, "invalid_ini"),
}


def _gitattributes(path: str, text: str, f: _Facts) -> None:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *attrs = line.split()
        for kind, names in (("generated", GENERATED), ("vendored", VENDORED)):
            if any(a in names for a in attrs):
                f.attributes.append({"kind": kind, "source": "gitattributes", "pattern": render_text(pattern),
                                     "attributes_file": path})


# ------------------------------------------------------------------------------------------- the metadata reads


def _parser_of(name: str, r: dict[str, Any]) -> str | None:
    spec = r["build_descriptors"].get(name)
    return spec.get("parser") if isinstance(spec, dict) else None


def _read_metadata(tree: Tree, r: dict[str, Any]) -> _Facts:
    f = _Facts()
    candidates: list[Entry] = []
    for e in tree.entries:
        if e.type != "blob":
            continue
        name = _name(e.path)
        wanted = name == GITATTRIBUTES or (_parser_of(name, r) is not None and _depth(e.path) <= DESCRIPTOR_DEPTH)
        if not wanted:
            continue
        if e.regular:
            candidates.append(e)
        else:  # a symlink: listed, never read or followed (PMP-28)
            f.status[e.path] = "symlink"
            f.unsupported.append({"path": e.path, "reason": "symlink"})
    total, stopped = 0, False
    for e in sorted(candidates, key=lambda c: c.path):
        size = e.size or 0
        if size > BLOB_LIMIT:
            tree.skip(e.path, CAPPED_SIZE)
            f.status[e.path] = CAPPED_SIZE
            continue
        if stopped or total + size > METADATA_LIMIT:
            stopped = True
            tree.skip(e.path, CAPPED_TOTAL)
            f.status[e.path] = CAPPED_TOTAL
            continue
        data = tree.read(e.path)
        total += len(data)
        if data.startswith(LFS_POINTER):
            f.status[e.path] = "lfs_pointer"
            f.lfs.append(e.path)
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            f.status[e.path] = "parse_failed"
            f.failures.append({"path": e.path, "code": "not_utf8"})
            continue
        name = _name(e.path)
        if name == GITATTRIBUTES:
            _gitattributes(e.path, text, f)
            f.status[e.path] = "parsed"
            continue
        parser, code = PARSERS[str(_parser_of(name, r))]
        try:
            parser(e.path, text, f)
        except (ValueError, configparser.Error, RecursionError):  # json and tomllib errors are ValueErrors
            f.status[e.path] = "parse_failed"
            f.failures.append({"path": e.path, "code": code})
            continue
        f.status[e.path] = "parsed"
    return f


# ------------------------------------------------------------------------------------------- the sections


def _directories(files: list[Entry], gitlinks: list[Entry], r: dict[str, Any]) -> dict[str, Any]:
    count: Counter[str] = Counter()
    langs: defaultdict[str, set[str]] = defaultdict(set)
    every_language: set[str] = set()
    for e in files:  # a deeper directory folds into its depth-3 ancestor
        lang = _language(e, r)
        if lang:
            every_language.add(lang)
        for d in _ancestors(e.path)[:DIRECTORY_DEPTH]:
            count[d] += 1
            if lang:
                langs[d].add(lang)
    names = set(count)
    for g in gitlinks:
        names.update(_ancestors(g.path)[:DIRECTORY_DEPTH])
    labels = r["directory_labels"]
    rows = [{"path": ".", "depth": 0, "files": len(files), "languages": sorted(every_language), "label": "root"}]
    rows += [{"path": d, "depth": d.count("/") + 1, "files": count[d], "languages": sorted(langs[d]),
              "label": labels.get(_name(d).lower(), "unknown")} for d in names]
    rows.sort(key=lambda row: (-row["files"], row["path"]))
    shown, omitted = _capped(rows, CAPS["directories"])
    subs, subs_omitted = _capped([{"path": g.path, "object": g.oid} for g in sorted(gitlinks, key=lambda g: g.path)],
                                 CAPS["submodules"])
    return {"max_depth": DIRECTORY_DEPTH, "rows": shown, "rows_total": len(rows), "rows_omitted": omitted,
            "submodules": subs, "submodules_omitted": subs_omitted}


def _language(e: Entry, r: dict[str, Any]) -> str | None:
    if not e.regular:
        return None
    name = _name(e.path)
    return r["language_files"].get(name) or r["languages"].get(_extension(name))


def _languages(regular: list[Entry], r: dict[str, Any]) -> dict[str, Any]:
    known: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    for e in regular:
        lang = _language(e, r)
        if lang:
            known[lang] += 1
        else:
            unknown[_extension(_name(e.path))] += 1
    top = sorted(unknown.items(), key=lambda kv: (-kv[1], kv[0]))
    shown, omitted = _capped([{"extension": render_text(ext), "files": n} for ext, n in top],
                             CAPS["unknown_extensions"])
    return {"counts": dict(sorted(known.items())), "unknown_files": sum(unknown.values()),
            "unknown_extensions": shown, "unknown_extensions_omitted": omitted}


def _descriptor_kind(name: str, r: dict[str, Any]) -> str | None:
    spec = r["build_descriptors"].get(name)
    if isinstance(spec, dict):
        return str(spec["kind"])
    for pattern, kind in sorted(r["build_descriptor_globs"].items()):
        if fnmatchcase(name, pattern):
            return str(kind)
    return None


def _build_descriptors(files: list[Entry], r: dict[str, Any], f: _Facts) -> dict[str, Any]:
    items = []
    for e in files:
        kind = _descriptor_kind(_name(e.path), r)
        if kind:
            items.append({"path": e.path, "kind": kind, "status": f.status.get(e.path, "listed")})
    items.sort(key=lambda i: i["path"])
    shown, omitted = _capped(items, CAPS["build_descriptors"])
    return {"items": shown, "omitted": omitted}


def _entry_points(regular: list[Entry], r: dict[str, Any], f: _Facts) -> dict[str, Any]:
    items = list(f.entry_points)
    for e in regular:
        for pattern in r["entry_point_conventions"]:
            if fnmatchcase(e.path, pattern):
                items.append({"label": "convention", "path": e.path, "rule": pattern})
                break
    items.sort(key=lambda i: (i["label"], i["path"], i.get("name", ""), i.get("target", "")))
    shown, omitted = _capped(items, CAPS["entry_point_candidates"])
    return {"items": shown, "omitted": omitted}


def _under(files: list[Entry]) -> Counter[str]:
    """Files under every directory, at any depth."""
    out: Counter[str] = Counter()
    for e in files:
        for d in _ancestors(e.path):
            out[d] += 1
    return out


def _test_candidates(files: list[Entry], regular: list[Entry], under: Counter[str], r: dict[str, Any],
                     f: _Facts) -> dict[str, Any]:
    test_dirs = set(r["test_directories"])
    items: list[dict[str, Any]] = [{"kind": "directory", "path": d, "files": n} for d, n in under.items()
                                   if _name(d).lower() in test_dirs]
    for pattern in r["test_file_patterns"]:
        n = sum(1 for e in regular if fnmatchcase(_name(e.path), pattern))
        if n:
            items.append({"kind": "file_pattern", "pattern": pattern, "files": n})
    runners = r["test_runner_configs"]
    items += [{"kind": "runner_config", "path": e.path, "runner": runners[_name(e.path)], "source": "convention"}
              for e in files if _name(e.path) in runners]
    items += f.runners
    items.sort(key=lambda i: (i["kind"], i.get("path", i.get("pattern", "")), i.get("runner", ""),
                              i.get("source", "")))
    shown, omitted = _capped(items, CAPS["test_candidates"])
    return {"items": shown, "omitted": omitted}


def _generated_and_vendor(regular: list[Entry], under: Counter[str], r: dict[str, Any], f: _Facts) -> dict[str, Any]:
    kinds = {**{n: "generated" for n in r["generated_directories"]}, **{n: "vendored" for n in r["vendor_directories"]}}
    items: list[dict[str, Any]] = []
    for d in sorted(under):
        kind = kinds.get(_name(d).lower())
        if kind and not any(kinds.get(_name(a).lower()) for a in _ancestors(d + "/x")[:-1]):
            items.append({"kind": kind, "source": "convention", "pattern": d + "/", "files": under[d]})
    for kind, key in (("generated", "generated_globs"), ("vendored", "vendor_globs")):
        for pattern in r[key]:
            n = sum(1 for e in regular if fnmatchcase(_name(e.path), pattern))
            if n:
                items.append({"kind": kind, "source": "convention", "pattern": pattern, "files": n})
    items += f.attributes
    items.sort(key=lambda i: (i["source"], i["pattern"], i["kind"], i.get("attributes_file", "")))
    shown, omitted = _capped(items, CAPS["generated_and_vendor"])
    return {"items": shown, "omitted": omitted}


def _semantic_prerequisites(regular: list[Entry], r: dict[str, Any], f: _Facts) -> dict[str, Any]:
    table = r["semantic_prerequisites"]
    items = [{"path": e.path, "kind": table[_name(e.path)], "source": "convention"} for e in regular
             if _name(e.path) in table]
    items += f.prerequisites
    items.sort(key=lambda i: (i["path"], i["kind"], i["source"]))
    shown, omitted = _capped(items, CAPS["semantic_prerequisites"])
    return {"items": shown, "omitted": omitted}


def _omissions(sections: dict[str, Any], entries: tuple[Entry, ...], f: _Facts,
               inputs: list[dict[str, Any]]) -> dict[str, Any]:
    caps = []
    for name in SECTIONS[:-1]:
        section = sections[name]
        for key, value in sorted(section.items()):
            if key.endswith("omitted") and value:
                cap = {"rows_omitted": "directories", "submodules_omitted": "submodules",
                       "unknown_extensions_omitted": "unknown_extensions"}.get(key, name)
                caps.append({"section": name, "field": key, "limit": CAPS[cap], "omitted": value})
    cap = CAPS["omissions"]
    failures, failures_omitted = _capped(sorted(f.failures, key=lambda i: i["path"]), cap)
    unsupported, unsupported_omitted = _capped(sorted(f.unsupported, key=lambda i: i["path"]), cap)
    lfs, lfs_omitted = _capped(sorted(f.lfs), cap)
    return {"caps_hit": caps, "parse_failures": failures, "parse_failures_omitted": failures_omitted,
            "unsupported": unsupported, "unsupported_omitted": unsupported_omitted,
            "lfs_pointers": lfs, "lfs_pointers_omitted": lfs_omitted,
            "metadata_unread": sum(1 for i in inputs if not i["read"]),
            "non_utf8_names": sum(1 for e in entries if not e.utf8),
            "symlinks": sum(1 for e in entries if e.symlink),
            "submodules": sum(1 for e in entries if e.gitlink),
            "unknown_extension_files": sections["languages"]["unknown_files"]}


def generate(tree: Tree, rules: Rules) -> dict[str, Any]:
    """The record for ``tree`` without ``artifact_sha256`` (``canonical.seal`` adds it)."""
    r = rules.data
    files = [e for e in tree.entries if e.type == "blob"]  # regular files and symlinks
    regular = [e for e in files if e.regular]
    gitlinks = [e for e in tree.entries if e.gitlink]
    facts = _read_metadata(tree, r)
    under = _under(files)
    sections: dict[str, Any] = {
        "directories": _directories(files, gitlinks, r),
        "languages": _languages(regular, r),
        "build_descriptors": _build_descriptors(files, r, facts),
        "entry_point_candidates": _entry_points(regular, r, facts),
        "test_candidates": _test_candidates(files, regular, under, r, facts),
        "generated_and_vendor": _generated_and_vendor(regular, under, r, facts),
        "semantic_prerequisites": _semantic_prerequisites(regular, r, facts),
    }
    inputs = tree.inputs()
    sections["limits_and_omissions"] = _omissions(sections, tree.entries, facts, inputs)
    read = sum(i["size"] for i in inputs if i["read"])
    return {
        "schema": SCHEMA,
        "source_revision": tree.commit,
        "source_tree": tree.tree,
        "object_format": tree.object_format,
        "generator": generator_identity(rules),
        "inputs": {"path_listing_sha256": tree.listing_sha256(), "metadata": inputs},
        "limits": {
            "tracked_paths": {"seen": len(tree.entries), "capped": False},
            "metadata_bytes": {"read": read, "limit": METADATA_LIMIT,
                               "capped": any(i.get("reason") == CAPPED_TOTAL for i in inputs)},
            "metadata_blob_bytes": {"limit": BLOB_LIMIT,
                                    "skipped": sum(1 for i in inputs if i.get("reason") == CAPPED_SIZE)},
        },
        "sections": sections,
    }
