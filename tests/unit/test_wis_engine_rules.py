"""The issuer's vendored engine rules equal the engine's, and the issuer imports nothing from ``aew`` (STG-04 WIS-A).

``aew_wis.engine_rules`` copies the engine's transition hash, sealed segment check, YAML loader and control trailer
rule (WIS-02 requires the engine's own). Each copied definition must equal its source in ``src/aew`` in its syntax
tree, and each constant its value, so a change on the engine's side fails here until the copy takes it. The trailer
rule, the one slice of a larger function, is also checked by behaviour on engine-written bytes and planted damage.

The package's isolation has two detectors that must agree both ways: every import the source names (``ast``) and every
import that actually runs when each module is imported (an import hook). Both must find exactly the allowed set: the
standard library, ``yaml``, ``cryptography`` and the package itself.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from aew import util
from aew.engine import outbox, store
from aew.history import manifest
from aew.util import dump_yaml
from aew_wis import engine_rules as R

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
PACKAGE = SRC / "aew_wis"
ALLOWED_THIRD_PARTY = {"yaml", "cryptography"}
COPIED = {  # the engine module each vendored definition comes from
    "src/aew/util.py": ["yaml_too_deep", "load_yaml"],
    "src/aew/history/manifest.py": ["canonical_json"],
    "src/aew/engine/outbox.py": ["overflow_path", "transition_hash", "record_path", "segment_of", "segment_path",
                                 "read_optional", "_read_record", "payload_events", "Segment", "_segment_shape_ok",
                                 "verify_segment", "load_segment"],
}
CONSTANTS = {"YAML_MAX_DEPTH": util, "YAML_TOO_DEEP": util, "_FLATTEN_IT": util, "STORE_REL": store,
             "CONTROL_REL": store, "CHECKSUM_PREFIX": store, "TRANSITION_SCHEMA": outbox, "GENESIS_H": outbox,
             "LOG_DIR": outbox, "SEGMENT_SIZE": outbox, "SEGMENT_SCHEMA": outbox}


def definitions(path: Path) -> dict[str, ast.AST]:
    return {n.name: n for n in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def dump(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


@pytest.mark.parametrize("source,name", [(s, n) for s, names in COPIED.items() for n in names])
def test_every_vendored_definition_equals_the_engines_in_its_syntax_tree(source, name):
    ours = definitions(PACKAGE / "engine_rules.py")[name]
    theirs = definitions(ROOT / source)[name]
    assert dump(ours) == dump(theirs), f"aew_wis.engine_rules.{name} differs from {source}: copy the engine's again"


def test_every_vendored_constant_equals_the_engines():
    for name, module in CONSTANTS.items():
        assert getattr(R, name) == getattr(module, name), name
    assert R._SafeLoader is util._SafeLoader and R._OPENS == util._OPENS and R._CLOSES == util._CLOSES


def test_the_copied_set_is_every_definition_the_vendored_module_holds_besides_its_own_shims():
    """Nothing in engine_rules is new logic but the shims the copies need, and the trailer rule's slice."""
    shims = {"_VendoredError", "IntegrityError", "ValidationFailed", "validate", "sha256_bytes", "control_body"}
    copied = {n for names in COPIED.values() for n in names}
    assert set(definitions(PACKAGE / "engine_rules.py")) == copied | shims


def test_the_trailer_rule_is_the_leading_statements_of_deserialize_control():
    ours = definitions(PACKAGE / "engine_rules.py")["control_body"]
    theirs = definitions(ROOT / "src/aew/engine/store.py")["deserialize_control"]
    assert isinstance(ours, ast.FunctionDef) and isinstance(theirs, ast.FunctionDef)
    body = ours.body[1:-1]  # its docstring and its return aside
    assert [dump(s) for s in body] == [dump(s) for s in theirs.body[:len(body)]]
    assert dump(theirs.body[len(body)]).startswith("Assign(targets=[Name(id='state'")  # where the parse begins


def control_bytes() -> bytes:
    return store.serialize_control({"schema": "aew/control/v1", "revision": 3, "note": "a body\nwith lines"})


@pytest.mark.parametrize("damage", ["none", "body", "trailer_hash", "no_trailer", "extra_newlines", "crlf",
                                    "trailer_only", "empty"])
def test_the_trailer_rule_refuses_exactly_what_the_engine_refuses(damage):
    raw = control_bytes()
    body, _, trailer = raw.rstrip(b"\n").rpartition(b"\n")
    planted = {"none": raw, "body": raw.replace(b"a body", b"a bode"),
               "trailer_hash": body + b"\n" + trailer[:-1] + (b"0" if trailer[-1:] != b"0" else b"1") + b"\n",
               "no_trailer": body + b"\n", "extra_newlines": raw + b"\n\n\n", "crlf": raw.replace(b"\n", b"\r\n"),
               "trailer_only": trailer + b"\n", "empty": b""}[damage]
    try:
        store.deserialize_control(planted, source="x")
        engine = None
    except Exception as exc:  # noqa: BLE001 - which class the engine raises is the point
        engine = type(exc).__name__
    try:
        text = R.control_body(planted, source="x")
        ours = None
    except Exception as exc:  # noqa: BLE001
        ours = type(exc).__name__
    if engine in (None, "ValidationFailed"):  # the trailer held; any refusal came after it (the parse, the schema)
        assert ours is None and planted.decode("utf-8").startswith(text)
    else:
        assert ours == engine, (damage, engine, ours)


def test_the_vendored_loader_reads_the_engines_yaml_as_the_engine_does():
    doc = {"revision": 7, "h": "ab" * 32, "at": "2026-10-18T13:00:00Z", "events": [{"kind": "work.state", "n": None}],
           "summary": "two\nlines", "deep": [[[[1]]]]}
    text = dump_yaml(doc)
    assert R.load_yaml(text) == util.load_yaml(text) == doc
    assert R.canonical_json(doc) == manifest.canonical_json(doc)
    record = dict(doc, h=None)
    assert R.transition_hash(R.GENESIS_H, record) == outbox.transition_hash(outbox.GENESIS_H, record)
    deep = "a: " + "[" * 70 + "]" * 70 + "\n"  # deeper than YAML_MAX_DEPTH: both refuse it, for the same reason
    with pytest.raises(R.ValidationFailed) as ours:
        R.load_yaml(deep)
    with pytest.raises(Exception) as theirs:  # noqa: B017, PT011 - the engine's own class, compared by its reason
        util.load_yaml(deep)
    assert ours.value.details["reason"] == R.YAML_TOO_DEEP == theirs.value.details["reason"]
    shallow = "a: " + "[" * 8 + "]" * 8 + "\n"
    assert R.load_yaml(shallow) == util.load_yaml(shallow)


# ---------------------------------------------------------------------------------------------- the isolation

def ast_imports() -> dict[str, set[str]]:
    """Detector one: every module each file of the package names in an import, anywhere in it."""
    out: dict[str, set[str]] = {}
    for f in sorted(PACKAGE.rglob("*.py")):
        names: set[str] = set()
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise AssertionError(f"{f}: a relative import; the package names itself in full")
                names.add(node.module or "")
        parts = f.relative_to(SRC).with_suffix("").parts
        out[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = names
    return out


RUNTIME_PROBE = r"""
import builtins, json, sys
seen = {}
real = builtins.__import__
def hook(name, globals=None, locals=None, fromlist=(), level=0):
    importer = (globals or {}).get("__name__", "")
    if importer.split(".")[0] == "aew_wis":
        seen.setdefault(importer, set()).add(name)
    return real(name, globals, locals, fromlist, level)
builtins.__import__ = hook
import importlib, pkgutil
import aew_wis
for m in pkgutil.walk_packages(aew_wis.__path__, "aew_wis."):
    importlib.import_module(m.name)
loaded_aew = sorted(m for m in sys.modules if m == "aew" or m.startswith("aew."))
print(json.dumps({"imports": {k: sorted(v) for k, v in seen.items()}, "aew": loaded_aew}))
"""


def runtime_imports() -> dict:
    """Detector two: the imports that run, in a fresh interpreter that imports every module of the package."""
    path = [str(SRC), *sys.path]  # -I drops PYTHONPATH: the parent's path, so cryptography is found as it is here
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path[:0] = {path!r}\n" + RUNTIME_PROBE],
                         capture_output=True, text=True, timeout=120, check=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(out.stdout)


def top(name: str) -> str:
    return name.split(".")[0]


def test_the_package_imports_nothing_from_aew_by_both_detectors_and_they_agree_both_ways():
    static = ast_imports()
    found = runtime_imports()
    assert found["aew"] == [], f"importing aew_wis loaded {found['aew']}"
    runtime = {m: set(v) for m, v in found["imports"].items()}
    assert set(runtime) == set(static), "a module imported by neither detector, or by one only"
    for module in static:
        assert {top(n) for n in runtime[module]} == {top(n) for n in static[module]}, module
    third = {top(n) for names in static.values() for n in names} - set(sys.stdlib_module_names) - {"aew_wis"}
    assert third == ALLOWED_THIRD_PARTY
    assert "aew" not in {top(n) for names in static.values() for n in names}


def test_the_detectors_see_a_planted_aew_import(tmp_path):
    """The control: a module that imports aew is caught by the static detector and by the runtime one."""
    planted = tmp_path / "src" / "aew_wis"
    planted.mkdir(parents=True)
    (planted / "__init__.py").write_text("", encoding="utf-8")
    (planted / "leak.py").write_text("from aew.engine import outbox\n", encoding="utf-8")
    names = {n.module for n in ast.walk(ast.parse((planted / "leak.py").read_text())) if isinstance(n, ast.ImportFrom)}
    assert names == {"aew.engine"}
    path = [str(tmp_path / "src"), str(SRC), *sys.path]
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path[:0] = {path!r}\n" + RUNTIME_PROBE],
                         capture_output=True, text=True, timeout=120, check=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    found = json.loads(out.stdout)
    assert "aew.engine.outbox" in found["aew"] and "aew.engine" in found["imports"]["aew_wis.leak"]
