"""The generated as-built reference, ``docs/reference/`` (STG-12 S12-2): one generator, checked in CI.

``tools/reference.py render`` writes the directory and ``check`` regenerates it in memory and fails on any difference.
This module is how CI runs ``check`` (in the fast lane, on Linux and on Windows, so the same committed bytes must pass
on both: that is the cross-OS proof), and it holds the generator's own guarantees: the output is deterministic (two
renders, and renders in fresh processes under different hash seeds), private (no absolute path, no timestamp, no
carriage return, nothing naming this machine), and in the shape the design side's trace reads (addendum 1). Each check
has its planted wrong case, so a check that stopped checking would fail here.

The entry-points family's own guarantees, which read the source by two independent detectors, are in
``tests/integration/test_reference_entry_points.py``.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import pkgutil
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reference_tool", ROOT / "tools" / "reference.py")
assert _spec is not None and _spec.loader is not None
reference = importlib.util.module_from_spec(_spec)
sys.modules["reference_tool"] = reference
_spec.loader.exec_module(reference)
C, PAGES, FAMILIES = reference._families()
MODULES = FAMILIES[0]
OUT = reference.OUT


@cache
def rendered() -> dict[str, bytes]:
    return reference.render_files(ROOT)


def committed() -> dict[str, bytes]:
    return reference._on_disk(OUT)


def index_of(files: dict[str, bytes]) -> dict[str, Any]:
    return json.loads(files["index.json"])


# ------------------------------------------------------------------------------------------ the CI check

def test_the_committed_reference_is_what_the_code_gives():
    """The check CI runs. A failure names the first file that differs and the command that settles it."""
    found = reference.check(ROOT, OUT)
    assert found == [], "\n".join(found)


def test_a_planted_drift_fails_the_check_and_the_message_names_the_command(tmp_path):
    """The wrong case and the missing case of the check: a changed byte, a deleted record, a deleted file, a stray
    file, a carriage return. Each is a difference, and the check's last line is the command that fixes it."""
    files = rendered()
    index = files["index.json"].decode("utf-8")
    victim = next(k for k in index_of(files)["records"] if k.startswith("entry-points:"))
    planted = {
        "a changed byte": {"index.json": index.replace('"kind"', '"kinD"', 1).encode()},
        "a deleted record": {"index.json": C.dumps({**json.loads(index), "records": {
            k: v for k, v in json.loads(index)["records"].items() if k != victim}}).encode()},
        "a deleted file": {"entry-points.md": None},
        "a carriage return": {"gaps.md": files["gaps.md"].replace(b"\n", b"\r\n")},
        "a stray file": {"stray.md": b"# Stray\n"},
        "an empty page": {"README.md": b""},
    }
    for what, change in planted.items():
        out = tmp_path / what.replace(" ", "-")
        out.mkdir()
        for name, data in {**files, **change}.items():
            if data is not None:
                (out / name).write_bytes(data)
        found = reference.check(ROOT, out, files)
        assert found, f"{what} is not a difference"
        assert C.RENDER_COMMAND in found[-1], what
    assert reference.check(ROOT, OUT, files) == []  # the committed directory was not touched


def test_render_writes_what_check_accepts_removes_a_stray_file_and_is_idempotent(tmp_path):
    out = tmp_path / "reference"
    out.mkdir()
    (out / "stray.md").write_bytes(b"x")
    changed = reference.render(ROOT, out, rendered())
    assert "stray.md" in changed and not (out / "stray.md").exists()
    assert reference.check(ROOT, out, rendered()) == []
    assert reference.render(ROOT, out, rendered()) == []  # nothing to write the second time
    assert committed() == {name: (out / name).read_bytes() for name in sorted(os.listdir(out))}


# ------------------------------------------------------------------------------------------ determinism

def test_two_renders_in_one_process_are_byte_identical():
    again = reference.render_files(ROOT)
    assert again == rendered()


SNIPPET = """
import hashlib, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("reference_tool", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules["reference_tool"] = m
spec.loader.exec_module(m)
print(json.dumps({k: hashlib.sha256(v).hexdigest() for k, v in sorted(m.render_files(m.ROOT).items())}))
"""


def test_renders_in_fresh_processes_under_different_hash_seeds_are_byte_identical(tmp_path):
    """A set or dict order that leaks into the output shows up as a different hash under a different seed."""
    env_base = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    procs = [subprocess.Popen([sys.executable, "-c", SNIPPET, str(ROOT / "tools" / "reference.py")],
                              env={**env_base, "PYTHONHASHSEED": seed}, cwd=tmp_path, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, creationflags=flags) for seed in ("1", "2718")]
    digests = []
    for proc in procs:
        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        assert proc.returncode == 0, stderr.decode("utf-8", "replace")[-800:]
        digests.append(json.loads(stdout))
    here = {k: hashlib.sha256(v).hexdigest() for k, v in rendered().items()}
    assert digests[0] == digests[1] == here


# ------------------------------------------------------------------------------------------ private, LF, shaped

def test_the_committed_files_are_lf_only_ascii_where_json_and_name_nothing_private():
    files = committed()
    assert files, "docs/reference is empty"
    for name, data in files.items():
        assert C.text_problems(name, data.decode("utf-8"), Path.home()) == []
    assert files["index.json"].isascii() and files["index.json"].endswith(b"}\n")


@pytest.mark.parametrize(("text", "what"), [
    ("path C:\\Users\\someone\\x", "a drive-letter path"),
    ("path C:/Users/someone/x", "a drive-letter path"),
    ("path /home/someone/x", "an absolute path"),
    ("at /Users/someone/x", "an absolute path"),
    ("built 2026-10-23T12:00:00Z", "a timestamp"),
    ("a\r\nb", "carriage return"),
])
def test_the_privacy_check_sees_each_wrong_case(text, what):
    assert any(what in p for p in C.text_problems("f", text))


@pytest.mark.parametrize("text", [
    "src/aew/engine/store.py", "the dashboard, 127.0.0.1:4261", "tools/reference.py", "https://example.invalid/a/b",
    "version 3.11", "aew.process_kind:ENTRY_POINTS"])
def test_the_privacy_check_passes_the_right_case(text):
    assert C.text_problems("f", text) == []


def test_the_privacy_check_sees_this_machines_home_directory_in_every_spelling():
    home = Path("C:\\Users\\Example Person") if os.name == "nt" else Path("/opt/example-person")
    for spelling in (str(home), home.as_posix(), str(home).replace("\\", "\\\\")):
        assert any("home directory" in p for p in C.text_problems("f", f"x {spelling} y", home)), spelling


# The shape of the design workspace's requirement IDs, exactly as its pack cutter matches it. The cutter checks each
# match against its own index of requirements, so a code fact passes there; this repository has no such index, so here
# a match is a hit unless it is allowed below, each entry with its reason. Measured over the committed pages when this
# test was written: 2 matches, both `STG-02` (the table's reason for the STG-02 slice's producer).
ID_SHAPE = re.compile(
    r"(?<![\w/.-])([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-[A-Z]?\d{1,3}[a-z]?(?:\.[a-z0-9]{1,3})?)(?![\w-])")
ID_ALLOWED = {
    "SHA-256": "an external standard: the hash",
    "UTF-8": "an external standard: the encoding",
    "DOC-01": "a family of this reference (the writer map), the document's own name, not a requirement",
    "DOC-02": "a family of this reference (the entry points), the document's own name, not a requirement",
    "DOC-03": "a family of this reference (concurrency), the document's own name, not a requirement",
    "DOC-04": "a family of this reference (the layout), the document's own name, not a requirement",
    "STG-02": "a stage: the code's own name for the slice (`aew.process_kind`'s reason for `aew.stg02.server`)",
}


def id_hits(text: str) -> list[str]:
    """What in ``text`` is a requirement or register ID and is not allowed: the design workspace's shape, and the
    repository's own ledger prefixes and register row ids, each exactly as its owner has it."""
    found = {m.group(1) for m in ID_SHAPE.finditer(text)} | {m.group(0) for m in derived_id_pattern().finditer(text)}
    return sorted(found - set(ID_ALLOWED))


@cache
def derived_id_pattern() -> re.Pattern[str]:
    """The IDs the repository itself owns, built from their owners (derive, don't restate): the requirements ledger's
    source prefixes (``<PREFIX>-<n>``, the shape ``test_requirements_ledger`` gives them), the register's row-id shape
    (``tools/register.py``'s ``ID_RE``) and the register's own row ids, ``STG-NN`` included."""
    import yaml

    ledger = yaml.safe_load((ROOT / "docs" / "design" / "requirements-ledger.yaml").read_text(encoding="utf-8"))
    prefixes = sorted({s["prefix"] for s in ledger["sources"]}, key=len, reverse=True)
    spec = importlib.util.spec_from_file_location("register_for_reference", ROOT / "tools" / "register.py")
    assert spec is not None and spec.loader is not None
    register = importlib.util.module_from_spec(spec)
    sys.modules["register_for_reference"] = register
    spec.loader.exec_module(register)
    rows = yaml.safe_load(register.YAML.read_text(encoding="utf-8"))["sections"]
    row_ids = {str(r["#"]) for s in rows for r in s.get("rows", []) if isinstance(r, dict) and r.get("#")}
    shaped = {i for i in row_ids if re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[0-9]+[a-z]?)?(?:\.[0-9]+)?", i)
              and any(c.isdigit() for c in i)}
    parts = [r"(?:" + "|".join(re.escape(p) for p in prefixes) + r")-\d+[a-z]?",
             register.ID_RE.pattern.removeprefix("^").removesuffix("$"),
             *(re.escape(i) for i in sorted(shaped, key=len, reverse=True))]
    return re.compile(r"(?<![\w.-])(?:" + "|".join(parts) + r")(?![\w-])")


def test_no_requirement_id_is_in_the_reference():
    """The trace is the design side's: the repository states what the code is, never what it should be, and holds no
    requirement ID. The design side's pack cutter checks each ID it finds against its index at the cut; this test is
    the earlier, shape-based check. (Requirement text, as against an ID, is not something either can match.)"""
    found = {name: id_hits(data.decode("utf-8")) for name, data in committed().items()}
    assert {name: hits for name, hits in found.items() if hits} == {}


@pytest.mark.parametrize("text", [
    "see CRD-13", "MOD-08", "WIS-01a", "D-CS1-12", "CS-01", "CB-09", "AIR-75.", "(WCA-3)", "CRD-13a",   # design shapes
    "STG-05",                                           # a stage name nobody has allowed: the allowlist is deliberate
    "register F44", "row F15.2 says", "E71"])           # the register's own row ids
def test_the_id_check_sees_each_wrong_case(text):
    assert id_hits(text), text


@pytest.mark.parametrize("text", [
    "UTF-8", "SHA-256", "DOC-02", "STG-02",                                             # allowed, each with its reason
    "aew.process_kind:ENTRY_POINTS", "python3.11", "http-problem-matrix", "src/aew/engine/store.py", "version 0.5.4",
    "entry-points:aew.stg02.server", "an ordinary sentence."])
def test_the_id_check_leaves_what_is_allowed_or_not_an_id_alone(text):
    assert id_hits(text) == [], text


def test_every_allowed_id_has_its_reason_and_would_otherwise_be_a_hit():
    """An allowlist entry that the shape would not match is dead weight, and one without a reason is a hole."""
    for entry, reason in ID_ALLOWED.items():
        assert reason.strip(), entry
        assert ID_SHAPE.search(entry), f"{entry} is not matched by the shape, so it needs no entry"


def test_the_committed_index_is_in_the_shape_the_trace_reads():
    index = index_of(committed())
    assert C.index_problems(index) == []
    assert list(index) == ["counts", "gaps", "records", "schema"] and index["schema"] == C.SCHEMA
    assert index["counts"]["records"] == len(index["records"])
    for rid, r in index["records"].items():
        assert set(r) <= {"family", "anchor", "basis", "coverage", "fact", "imports"}, rid
        assert set(r["anchor"]) == {"module", "symbol"}, rid


def small_index() -> dict[str, Any]:
    mod = C.Record(C.MODULES, "aew.a", "aew.a", None, "static", C.lower_bound(), {"path": "src/aew/a.py"}, [])
    other = C.Record(C.MODULES, "aew.b", "aew.b", None, "static",
                     C.lower_bound([C.unresolved_item("aew.b", "f", "a computed import")]), {"path": "src/aew/b.py"},
                     ["aew.a"])
    rec = C.Record("things", "t1", "aew.a", "T", "enumerated", C.complete("aew.a:T", ["tests/x.py::t"]), {"n": 1})
    return C.build_index([mod, other, rec], [C.Gap("things", "aew.a", None, "unreadable")])


MUTATIONS = {
    "an anchor module with no modules record": lambda i: i["records"]["things:t1"]["anchor"].update(module="aew.zz"),
    "a basis outside the four": lambda i: i["records"]["things:t1"].update(basis="guessed"),
    "a record without its basis": lambda i: i["records"]["things:t1"].pop("basis"),
    "a non-module record without its symbol": lambda i: i["records"]["things:t1"]["anchor"].update(symbol=None),
    "complete-by-construction without its check": lambda i: i["records"]["things:t1"]["coverage"].pop("check"),
    "complete-by-construction with an empty check": lambda i: i["records"]["things:t1"]["coverage"].update(check=[]),
    "complete-by-construction without its registry": lambda i: i["records"]["things:t1"]["coverage"].pop("registry"),
    "lower-bound without its unresolved list": lambda i: i["records"]["modules:aew.b"]["coverage"].pop("unresolved"),
    "an unresolved item without its why": lambda i: i["records"]["modules:aew.b"]["coverage"]["unresolved"][0].pop(
        "why"),
    "a label outside the three": lambda i: i["records"]["things:t1"]["coverage"].update(label="complete"),
    "a module without its imports": lambda i: i["records"]["modules:aew.b"].pop("imports"),
    "imports out of order": lambda i: i["records"]["modules:aew.b"].update(imports=["aew.b", "aew.a"]),
    "an import with no modules record": lambda i: i["records"]["modules:aew.b"].update(imports=["aew.zz"]),
    "imports on a record that is not a module": lambda i: i["records"]["things:t1"].update(imports=[]),
    "a module with a symbol": lambda i: i["records"]["modules:aew.a"]["anchor"].update(symbol="x"),
    "an id that does not start with its family": lambda i: i["records"].update(
        {"other:t1": i["records"].pop("things:t1")}),
    "counts that no longer match": lambda i: i["counts"].update(records=99),
    "a gap without its why": lambda i: i["gaps"][0].pop("why"),
    "a wrong schema": lambda i: i.update(schema="aew/reference-index/v0"),
}


def test_a_sound_index_has_no_problems_and_each_planted_fault_is_one():
    assert C.index_problems(small_index()) == []
    for what, mutate in MUTATIONS.items():
        broken = copy.deepcopy(small_index())
        mutate(broken)
        assert C.index_problems(broken), what


def test_two_records_with_one_id_are_refused():
    rec = C.Record("things", "t1", "aew.a", "T", "enumerated", C.unknown())
    with pytest.raises(C.ReferenceError, match="not unique"):
        C.build_index([rec, rec], [])


# ------------------------------------------------------------------------------------------ one tree

def test_the_generator_refuses_an_aew_that_is_not_this_trees(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(C.ReferenceError, match="absolute PYTHONPATH"):
        reference._one_tree(C, tmp_path)
    reference._one_tree(C, ROOT)  # this tree's own: the tests run with an absolute PYTHONPATH to it


# ------------------------------------------------------------------------------- every coverage claim names tests

def test_every_check_a_record_names_is_a_test_that_exists():
    """A coverage claim is only as good as the test it names: the file exists and defines the function."""
    seen = 0
    for rid, r in index_of(committed())["records"].items():
        for node_id in r["coverage"].get("check", []):
            path, _, name = node_id.partition("::")
            file = ROOT / path
            assert file.is_file(), f"{rid} names {node_id}, whose file does not exist"
            tree = ast.parse(file.read_text(encoding="utf-8"))
            assert any(isinstance(n, ast.FunctionDef) and n.name == name for n in ast.walk(tree)), f"{rid}: {node_id}"
            seen += 1
    assert seen


# ------------------------------------------------------------------------------------------ the entry-points family

def test_the_entry_point_records_are_the_registry_both_ways():
    """A table pinned against live data, checked both ways: one record per key of ``ENTRY_POINTS`` and no other, each
    carrying the table's own kind and reason."""
    from aew import process_kind

    records = {rid: r for rid, r in index_of(committed())["records"].items() if r["family"] == "entry-points"}
    assert set(records) == {f"entry-points:{key}" for key in process_kind.ENTRY_POINTS}
    for key, (kind, reason) in process_kind.ENTRY_POINTS.items():
        record = records[f"entry-points:{key}"]
        assert (record["fact"]["entry_point"], record["fact"]["kind"], record["fact"]["reason"]) == (key, kind, reason)
        assert record["basis"] == "enumerated" and record["coverage"]["label"] == "complete-by-construction"
        assert record["coverage"]["registry"] == "aew.process_kind:ENTRY_POINTS"
        assert record["fact"]["declared_at"], f"{key} declares itself nowhere"
        assert record["anchor"]["module"] == record["fact"]["declared_at"][0]["module"]


# ------------------------------------------------------------------------------------------ the modules family

def test_the_modules_family_is_the_packages_modules_by_two_derivations():
    """The generator walks the files; the import system walks the package. They must name the same modules."""
    import aew

    by_walk = {"aew"} | {m.name for m in pkgutil.walk_packages(aew.__path__, "aew.")}
    records = {r["anchor"]["module"]: r for r in index_of(committed())["records"].values() if r["family"] == C.MODULES}
    assert set(records) == by_walk
    for name, r in records.items():
        assert (ROOT / r["fact"]["path"]).is_file(), name
        assert not r["fact"]["path"].startswith(("/", "src/../")) and "\\" not in r["fact"]["path"]
        assert r["fact"]["package"] == (Path(r["fact"]["path"]).name == "__init__.py")


KNOWN = frozenset({"aew", "aew.a", "aew.other", "aew.pkg", "aew.pkg.mod", "aew.pkg.sub", "aew.pkg.sub.leaf"})


def edges(source: str, module: str = "aew.pkg.mod", is_package: bool = False):
    return MODULES.edges_of(ast.parse(source), module, is_package, KNOWN)


@pytest.mark.parametrize(("source", "want"), [
    ("from . import sub\n", {"aew.pkg.sub"}),                       # a sibling module imported by name
    ("from .sub import leaf\n", {"aew.pkg.sub.leaf"}),               # a module below it
    ("from .sub import not_a_module\n", {"aew.pkg.sub"}),            # a name in the module: the edge is to the module
    ("from .. import other\n", {"aew.other"}),                       # one level up
    ("from ..other import thing\n", {"aew.other"}),
    ("import aew.a\n", {"aew.a"}),
    ("import aew.a.nope.deeper\n", {"aew.a"}),                       # the longest module that exists
    ("from aew import a\n", {"aew.a"}),
    ("from aew import something\n", {"aew"}),                        # a name in the package itself
    ("def f():\n    from aew.other import x\n", {"aew.other"}),     # in a function: still a static import
    ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from aew import a\n", {"aew.a"}),
    ("import os, json\nfrom json import dumps\n", set()),            # outside the package
    ("import aew.pkg.mod\n", set()),                                 # itself
])
def test_the_import_graph_reads_each_form_of_import(source, want):
    assert edges(source)[0] == want


def test_a_package_resolves_a_relative_import_against_itself():
    assert edges("from . import mod\n", "aew.pkg", is_package=True)[0] == {"aew.pkg.mod"}
    assert edges("from .mod import x\n", "aew.pkg", is_package=True)[0] == {"aew.pkg.mod"}


@pytest.mark.parametrize(("source", "edge", "why"), [
    ("import importlib\ndef f(n):\n    return importlib.import_module(n)\n", set(), "computed module name"),
    ("import importlib\nimportlib.import_module('aew.other')\n", {"aew.other"}, None),   # a constant AEW name
    ("import importlib\nimportlib.import_module('json')\n", set(), None),                # a constant outside AEW
    ("import importlib\nimportlib.import_module('aew.nope')\n", set(), "cannot resolve"),
    ("import importlib\nimportlib.import_module('.x', 'aew.pkg')\n", set(), "cannot resolve"),
    ("from importlib import import_module as im\ndef f(n):\n    im(n)\n", set(), "computed module name"),
    ("def f(n):\n    __import__(n)\n", set(), "computed module name"),
    ("import importlib.util\nimportlib.util.spec_from_file_location('n', p)\n", set(), "by file path"),
    ("from importlib import util\nutil.spec_from_file_location('n', p)\n", set(), "by file path"),
    ("def import_module(n):\n    return n\nimport_module(x)\n", set(), None),            # its own, not importlib's
    ("class C:\n    def m(self, n):\n        __import__(n)\n", set(), "computed module name"),
])
def test_a_dynamic_import_is_an_edge_when_its_name_is_constant_and_unresolved_otherwise(source, edge, why):
    found, unresolved = edges(source)
    assert found == edge
    if why is None:
        assert unresolved == []
    else:
        assert len(unresolved) == 1 and why in unresolved[0]["why"], unresolved


def test_an_unresolved_dynamic_import_is_anchored_at_its_enclosing_symbol():
    _, unresolved = edges("class C:\n    def m(self, n):\n        __import__(n)\n")
    assert unresolved[0]["module"] == "aew.pkg.mod" and unresolved[0]["symbol"] == "C.m"


def test_a_module_that_does_not_parse_is_listed_as_unreadable_not_as_having_no_imports(tmp_path):
    package = tmp_path / "src" / "aew"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "ok.py").write_text("from aew import broken\n", encoding="utf-8")
    (package / "broken.py").write_text("def (:\n", encoding="utf-8")
    mods = {m.name: m for m in MODULES.scan(C.Context(tmp_path))}
    assert mods["aew.broken"].imports == () and "does not parse" in mods["aew.broken"].unresolved[0]["why"]
    assert mods["aew.ok"].imports == ("aew.broken",)


def test_a_tree_with_no_package_is_refused_not_rendered_empty(tmp_path):
    with pytest.raises(C.ReferenceError, match="no aew package"):
        C.Context(tmp_path).sources()
