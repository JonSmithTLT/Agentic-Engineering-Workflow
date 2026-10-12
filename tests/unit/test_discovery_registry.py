"""D2's pins against the page (docs/implementation/vertical-uat.md §8): the per-rule modes agree with
``tests/helpers/discovery/modes.py``, and the code registry lists every refusal code the product defines, so neither
can drift (discovery-layer spec v3.4, §2.3 and §5)."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from discovery import modes, registry

from aew import errors
from aew.surface import errors as surface_errors

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "implementation" / "vertical-uat.md"
SRC = ROOT / "src" / "aew"
CODE_SHAPE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
# Codes the product writes that are not refusals, so outside the refusal registry (review of #218, G3 and G3b): the
# assurance lint, Class 0 eligibility and dispatch blocker codes, which are entries in a refusal's details or a
# decision's reason codes, never a refusal's code. Pinned here so each is named: a code that leaves this list or is no
# longer written fails the test.
OUTSIDE_REGISTRY = frozenset({
    "ACCEPTANCE_INPUT_IN_SCOPE", "INHERITED_ELEVATED_OBLIGATION",
    "GIT_DRIVER_UNTRUSTED", "PROTECTED_CONDITION_OVERLAP",
    "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC", "CLASS0_ASSERTION_MISSING", "CLASS0_CONSEQUENTIAL_BOUNDARY",
    "CLASS0_HARD_TRIGGER", "CLASS0_INHERITED_ELEVATED_OBLIGATION", "CLASS0_NO_ACCEPTANCE_REFERENCE",
    "CLASS0_PLAN_LINT", "CLASS0_SUBJECT_UNBOUNDED",
    "LINT_ACCEPTANCE_CHECK_UNKNOWN", "LINT_ACCEPTANCE_INPUT_WRITABLE", "LINT_AFFECTED_OUTSIDE_SCOPE",
    "LINT_AFFECTED_PROTECTED", "LINT_NO_ACCEPTANCE_MECHANISM",
})


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def code_writes(root: Path = SRC) -> dict[str, str]:
    """``code -> "module:line"``, the first place the product's source writes each code (``code_write_sites``)."""
    return {code: sites[0] for code, sites in code_write_sites(root).items()}


def code_write_sites(root: Path = SRC) -> dict[str, list[str]]:
    """``code -> ["module:line", ...]`` for every place the product's source writes a code string (review of #218, m6
    and G3), in each form it uses: a class's ``code =`` or ``code: T =``, a dict literal's ``"code": "X"``, a keyword
    ``code="X"``, an ``x.code = "X"`` assignment, and a constructor argument (review of #218, G3b): a class whose
    ``__init__`` stores a parameter in ``self.code``, or a dataclass with a ``code`` field, writes what its call sites
    pass at that position or as ``code=``: a literal, or a module constant's name (G3c)."""
    out: dict[str, list[str]] = {}

    def add(value: object, path: Path, line: int) -> None:
        if isinstance(value, str) and CODE_SHAPE.match(value):
            site = f"{path.relative_to(root).as_posix()}:{line}"
            if site not in out.setdefault(value, []):
                out[value].append(site)

    trees = {path: ast.parse(path.read_text(encoding="utf-8")) for path in sorted(root.rglob("*.py"))}
    takers = {name: index for tree in trees.values() for name, index in code_parameters(tree).items()}
    constants = module_constants(trees, root)
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                index = takers.get(name) if isinstance(name, str) else None
                if index is None:
                    continue
                given = [node.args[index]] if len(node.args) > index else []
                given += [k.value for k in node.keywords if k.arg == "code"]
                for arg in given:  # a literal, or a module constant's name (review of #218, G3c)
                    if isinstance(arg, ast.Constant):
                        add(arg.value, path, node.lineno)
                    elif isinstance(arg, ast.Name) and arg.id in constants[path]:
                        add(constants[path][arg.id], path, node.lineno)
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    targets = (stmt.targets if isinstance(stmt, ast.Assign)
                               else [stmt.target] if isinstance(stmt, ast.AnnAssign) else [])
                    if any(getattr(t, "id", None) == "code" for t in targets) and isinstance(stmt.value, ast.Constant):
                        add(stmt.value.value, path, stmt.lineno)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "code" and isinstance(value, ast.Constant):
                        add(value.value, path, node.lineno)
            elif isinstance(node, ast.keyword) and node.arg == "code" and isinstance(node.value, ast.Constant):
                add(node.value.value, path, node.value.lineno)
            elif (isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                  and any(isinstance(t, ast.Attribute) and t.attr == "code" for t in node.targets)):
                add(node.value.value, path, node.lineno)
    return out


def module_constants(trees: dict[Path, ast.Module], root: Path) -> dict[Path, dict[str, str]]:
    """``path -> {name: value}``: the string constants each module binds at its top level (``NAME = "X"``), and those
    it imports by name from another scanned module (``from pkg.mod import NAME as ALIAS``, relative imports too)."""
    def dotted(path: Path) -> str:
        return ".".join(path.relative_to(root).with_suffix("").parts)

    own: dict[str, dict[str, str]] = {}
    for path, tree in trees.items():
        own[dotted(path)] = {t.id: stmt.value.value for stmt in tree.body if isinstance(stmt, ast.Assign)
                             and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
                             for t in stmt.targets if isinstance(t, ast.Name)}

    def find(module: str) -> dict[str, str]:  # "aew.harness.x" or "harness.x": the scanned module it names
        return next((c for key, c in own.items() if module == key or module.endswith("." + key)), {})

    out: dict[Path, dict[str, str]] = {}
    for path, tree in trees.items():
        names = dict(own[dotted(path)])
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                package = dotted(path).split(".")[:-1]
                base = ".".join(package[:len(package) - stmt.level + 1] if stmt.level else [])
                module = ".".join(p for p in (base, stmt.module or "") if p)
                source = find(module)
                for alias in stmt.names:
                    if alias.name in source:
                        names[alias.asname or alias.name] = source[alias.name]
        out[path] = names
    return out


def code_parameters(tree: ast.AST) -> dict[str, int]:
    """``class name -> positional index of its code`` for every class in ``tree`` that takes its code as a constructor
    argument: an ``__init__`` storing a parameter in ``self.code``, or a dataclass with a ``code`` field."""
    out: dict[str, int] = {}
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        fields = [s.target.id for s in cls.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)]
        decorated = any((getattr(d, "id", None) or getattr(d, "attr", None)) == "dataclass"
                        or (isinstance(d, ast.Call) and (getattr(d.func, "id", None)
                                                         or getattr(d.func, "attr", None)) == "dataclass")
                        for d in cls.decorator_list)
        if decorated and "code" in fields:
            out[cls.name] = fields.index("code")
        for init in (f for f in cls.body if isinstance(f, ast.FunctionDef) and f.name == "__init__"):
            params = [a.arg for a in init.args.args][1:]
            for stmt in ast.walk(init):
                if (isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Name) and stmt.value.id in params
                        and any(isinstance(t, ast.Attribute) and t.attr == "code" for t in stmt.targets)):
                    out[cls.name] = params.index(stmt.value.id)
    return out


STEERING_LOOP = "harness/steering_loop.py"  # the module that owns the stop vocabulary, relative to the source root


def steering_stop_codes(root: Path = SRC) -> frozenset[str]:
    """The steering loop's stop vocabulary, an outside namespace (review of #218, G3c), derived from the module that
    owns it rather than pinned: the module's own top-level assignments (read from its source, so a name it imports is
    not its own) of an upper-case name to a code. A new stop code is in it the moment it is added."""
    tree = ast.parse((root / STEERING_LOOP).read_text(encoding="utf-8"))
    return frozenset(stmt.value.value for stmt in tree.body
                     if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
                     and isinstance(stmt.value.value, str) and CODE_SHAPE.match(stmt.value.value)
                     for t in stmt.targets if isinstance(t, ast.Name) and t.id.isupper())


def refusal_class_codes() -> frozenset[str]:
    return frozenset(cls.code for _, cls in inspect.getmembers(errors, inspect.isclass)
                     if issubclass(cls, errors.AEWError) and cls.__module__ == errors.__name__)


def stops_outside(root: Path = SRC) -> frozenset[str]:
    """The stop codes that are only stop codes: a stop code written anywhere outside the steering loop (any form the
    scan reads), or one of the typed surface's codes, is a refusal code too and stays in the registry's scope."""
    elsewhere = {code for code, sites in code_write_sites(root).items()
                 if any(not site.startswith(STEERING_LOOP + ":") for site in sites)}
    return steering_stop_codes(root) - elsewhere - set(surface_errors.CODES)


CONFIGURATION = "engine/configuration.py"  # the module that owns the projection's data codes, relative to the root


def projection_data_outside(root: Path = SRC) -> frozenset[str]:
    """The configuration projection's data-code vocabulary (register F46.1), an outside namespace derived from its one
    definition, `aew.engine.configuration.DATA_CODES`, rather than pinned: the codes a successful read writes to
    describe a policy file's content. A data code also written anywhere outside that module, or one of the typed
    surface's codes, is a refusal code too and stays in the registry's scope (the test below fails on any such
    overlap)."""
    from aew.engine.configuration import DATA_CODES

    elsewhere = {code for code, sites in code_write_sites(root).items()
                 if any(not site.startswith(CONFIGURATION + ":") for site in sites)}
    return frozenset(DATA_CODES) - elsewhere - set(surface_errors.CODES)


def defined_codes(root: Path = SRC) -> dict[str, str]:
    """Every refusal code the product defines that the Lead or the operator can see, with where it is written."""
    outside = OUTSIDE_REGISTRY | stops_outside(root) | projection_data_outside(root)
    codes = {c: where for c, where in code_writes(root).items() if c not in outside}
    codes.update({c: "surface/errors.py:CODES" for c in surface_errors.CODES})
    return codes


def test_a_stop_code_that_is_also_written_elsewhere_stays_a_refusal_code(tmp_path):
    """Review of #218 at cb1e496: a steering-loop constant whose value is also written as a refusal elsewhere (here
    `BRIDGE_ERROR`, by a bridge-like module) stays in the registry's scope; one written only by the loop is outside; a
    name the loop imports is not its own constant."""
    loop = tmp_path / STEERING_LOOP
    loop.parent.mkdir(parents=True)
    (tmp_path / "harness" / "codes.py").write_text("IMPORTED = 'ONLY_IMPORTED'\n", encoding="utf-8")
    loop.write_text("from harness.codes import IMPORTED\nfrom dataclasses import dataclass\n"
                    "ONLY_A_STOP = 'ONLY_A_STOP'\nBRIDGE = 'BRIDGE_ERROR'\nTOOL = 'UNKNOWN_TOOL'\n@dataclass\n"
                    "class Stop:\n    code: str\nStop(ONLY_A_STOP)\nStop(BRIDGE)\nStop(IMPORTED)\n", encoding="utf-8")
    (tmp_path / "harness" / "bridge.py").write_text("reply = {'error': {'code': 'BRIDGE_ERROR'}}\n", encoding="utf-8")
    # not the imported name; UNKNOWN_TOOL is one of the typed surface's codes
    assert steering_stop_codes(tmp_path) == {"ONLY_A_STOP", "BRIDGE_ERROR", "UNKNOWN_TOOL"}
    assert stops_outside(tmp_path) == {"ONLY_A_STOP"}
    kept = defined_codes(tmp_path)
    assert {"BRIDGE_ERROR", "ONLY_IMPORTED", "UNKNOWN_TOOL"} <= set(kept) and "ONLY_A_STOP" not in kept


def test_the_projection_data_codes_are_outside_the_registry_and_overlap_no_refusal_code():
    """The configuration projection's data codes (`aew.engine.configuration.DATA_CODES`) are a derived namespace
    outside the registry: none is a refusal code (an `aew.errors` class's code, a registry row, a typed surface's code,
    or a code the product writes outside the projection's module), and the scan finds them only in that module."""
    from aew.engine.configuration import DATA_CODES

    assert {"YAML_SYNTAX", "UNPROCESSABLE", "NO_SUCH_PROFILE", "NO_DEFAULT_ROUTE"} <= DATA_CODES
    assert projection_data_outside() == DATA_CODES  # nothing in the vocabulary is also written as a refusal
    listed = {str(r["code"]) for r in registry.rows(page())}
    assert not DATA_CODES & listed and not DATA_CODES & refusal_class_codes()
    assert not DATA_CODES & set(surface_errors.CODES)
    for code, sites in code_write_sites().items():
        if code in DATA_CODES:
            assert all(site.startswith(CONFIGURATION + ":") for site in sites), (code, sites)
            assert code not in defined_codes()


def test_a_data_code_also_written_elsewhere_stays_a_refusal_code(tmp_path):
    """A projection data code that another module writes as a refusal leaves the derived namespace, so the registry
    must list it (the overlap is caught, never hidden)."""
    (tmp_path / "engine").mkdir()
    (tmp_path / STEERING_LOOP).parent.mkdir(parents=True)
    (tmp_path / STEERING_LOOP).write_text("", encoding="utf-8")  # no stop codes in this tree
    (tmp_path / "engine" / "configuration.py").write_text("yaml_error = {'code': 'YAML_SYNTAX'}\n", encoding="utf-8")
    assert "YAML_SYNTAX" in projection_data_outside(tmp_path) and "YAML_SYNTAX" not in defined_codes(tmp_path)
    (tmp_path / "engine" / "other.py").write_text("refusal = {'code': 'YAML_SYNTAX'}\n", encoding="utf-8")
    assert "YAML_SYNTAX" not in projection_data_outside(tmp_path) and "YAML_SYNTAX" in defined_codes(tmp_path)


def test_the_steering_stop_codes_are_named_outside_and_the_scan_reads_them_through_constants():
    """Review of #218, G3c: `Stop` is called with the module's constants by name (`Stop(BLOCKED)`); the scan resolves
    them, and every stop code it finds is in the derived namespace, none of them in the registry unless it is also a
    refusal code."""
    stops = steering_stop_codes()
    assert {"BLOCKED", "NOTHING_TO_DO", "STEERING_OFF", "ACTION_STOPPED", "LOOP_DEADLINE"} <= stops
    found_in_loop = {c for c, where in code_writes().items() if where.startswith("harness/steering_loop.py")}
    assert {"BLOCKED", "ANOMALY_HIGH", "LOOP_DEADLINE", "MAX_AUTO_ACTIONS"} <= found_in_loop <= stops
    listed = {str(r["code"]) for r in registry.rows(page())}
    assert stops - stops_outside() == stops & listed == {"STALE_AUTHORITY", "STALE_POLICY"}


def test_the_source_scan_sees_every_class_aew_errors_defines():
    """The scan reads source; `aew.errors`' own classes, enumerated by import, are a subset of what it finds."""
    imported = {cls.code for _, cls in inspect.getmembers(errors, inspect.isclass)
                if issubclass(cls, errors.AEWError) and cls.__module__ == errors.__name__}
    found = code_writes()
    assert len(imported) > 50 and imported <= set(found)
    assert {"INVALID_REQUEST", "VALIDATION_RUNNING", "VALIDATION_CONTAINMENT_UNAVAILABLE"} <= set(found)
    assert {"NOT_COMPLETED", "BRIDGE_ERROR", "DEFECT"} <= set(found)  # dict literals (G3)
    assert {"CURSOR_INVALID", "CURSOR_EXPIRED", "GIT_DRIVER_UNTRUSTED"} <= set(found)  # constructor arguments (G3b)


@pytest.mark.parametrize("source", [
    "class X(Exception):\n    code = 'BRAND_NEW'\n",
    "class X(Exception):\n    code: str = 'BRAND_NEW'\n",
    "reply = {'ok': False, 'error': {'code': 'BRAND_NEW', 'message': 'm'}}\n",
    "refuse(code='BRAND_NEW')\n",
    "err.code = 'BRAND_NEW'\n",
    "class E(Exception):\n    def __init__(self, message, code):\n        self.code = code\n"
    "raise E('m', 'BRAND_NEW')\n",
    "import dataclasses\n@dataclasses.dataclass\nclass B:\n    subject: str\n    code: str\n"
    "B('s', 'BRAND_NEW')\n",
    "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass B:\n    code: str\nB('BRAND_NEW')\n",
    "from dataclasses import dataclass\nNEW = 'BRAND_NEW'\n@dataclass\nclass B:\n    code: str\nB(NEW)\n",
    "from dataclasses import dataclass\nNEW = 'BRAND_NEW'\n@dataclass\nclass B:\n    code: str\nB(code=NEW)\n",
])
def test_a_new_code_written_in_any_form_is_caught(tmp_path, source):
    (tmp_path / "m.py").write_text(source, encoding="utf-8")
    assert set(code_writes(tmp_path)) == {"BRAND_NEW"}
    (tmp_path / "m.py").write_text("x = {'kind': 'BRAND_NEW'}\ncode_word = 'BRAND_NEW'\n", encoding="utf-8")
    assert code_writes(tmp_path) == {}  # a string that is not written as a code


@pytest.mark.parametrize("importer", ["from pkg.codes import NEW as N\n", "from .codes import NEW as N\n"])
def test_a_code_constant_imported_from_another_module_is_resolved(tmp_path, importer):
    """Review of #218, G3c: the constant may be bound in another module and imported by name (absolute or
    relative); a name that is not a scanned constant is not read."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "codes.py").write_text("NEW = 'BRAND_NEW'\nlower = 'not a code'\n", encoding="utf-8")
    (pkg / "use.py").write_text(importer + "from dataclasses import dataclass\n@dataclass\nclass S:\n    code: str\n"
                                "S(N)\nS(undefined_name)\n", encoding="utf-8")
    assert code_writes(tmp_path) == {"BRAND_NEW": "pkg/use.py:6"}


def test_the_codes_outside_the_registry_are_named_and_still_written():
    found = code_writes()
    assert OUTSIDE_REGISTRY <= set(found), sorted(OUTSIDE_REGISTRY - set(found))
    assert not OUTSIDE_REGISTRY & {str(r["code"]) for r in registry.rows(page())}


def test_the_per_rule_modes_on_the_page_are_the_modes_the_helpers_pin():
    assert registry.doc_modes(page()) == modes.MODES
    assert set(modes.MODES) == set(modes.RULES)
    assert set(modes.MODES.values()) <= set(modes.MODE_VALUES)


def test_a_mode_on_the_page_that_differs_from_the_helpers_is_caught():
    text = page()
    mutant = text.replace("| O-IDS | `shadow` |", "| O-IDS | `enforce` |", 1)
    assert mutant != text
    assert registry.doc_modes(mutant) != modes.MODES


def test_every_refusal_code_the_product_defines_is_in_the_registry():
    codes = defined_codes()
    assert len(codes) > 60 and "PERMISSION_DENIED" in codes and set(surface_errors.CODES) <= set(codes)
    rows = registry.rows(page())
    listed = [r["code"] for r in rows]
    assert len(listed) == len(set(listed)), "a code is listed twice"
    assert sorted(set(codes) - set(listed)) == []
    assert sorted(set(listed) - set(codes)) == []  # nothing listed that the product no longer defines
    for r in rows:
        assert r["meaning"] and r["causes"], r["code"]
        assert r["owner"] in registry.OWNERS, r["code"]


def test_a_code_missing_from_the_registry_is_caught():
    text = page()
    line = next(ln for ln in text.splitlines() if ln.startswith("| `RUN_LIVE` |"))
    listed = {r["code"] for r in registry.rows(text.replace(line + "\n", ""))}
    assert sorted(set(defined_codes()) - listed) == ["RUN_LIVE"]


def test_the_registry_holds_the_specifications_minimum():
    """§2.3: PERMISSION_DENIED only for an authority that denied the caller (never "seat held", never an unset or
    malformed input); STALE_REVISION only a CAS mismatch; ILLEGAL_TRANSITION only a transition-table refusal; USAGE
    only malformed input."""
    reg = registry.load(page())
    assert reg["PERMISSION_DENIED"] == {"authority_denied"}
    assert reg["STALE_REVISION"] == {"cas_mismatch"}
    assert reg["ILLEGAL_TRANSITION"] == {"transition_refused"}
    assert {"input_malformed"} <= reg["USAGE"] and "authority_denied" not in reg["USAGE"]
    for code, causes in reg.items():
        if code != "PERMISSION_DENIED":
            assert "authority_denied" not in causes, code
        assert not {"seat_held"} & causes, code  # no code is registered for "seat held" yet: O-CODE flags any use
