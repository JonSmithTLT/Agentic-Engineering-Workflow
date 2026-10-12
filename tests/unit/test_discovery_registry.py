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
# Codes the product writes that are not refusals, so outside the refusal registry (review of #218, G3): the assurance
# lint and Class 0 eligibility blockers, which are entries in a refusal's or a lint's details, never its code. Pinned
# here so each is named: a code that leaves this list or is no longer written fails the test.
OUTSIDE_REGISTRY = frozenset({
    "ACCEPTANCE_INPUT_IN_SCOPE", "INHERITED_ELEVATED_OBLIGATION",
    "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC", "CLASS0_ASSERTION_MISSING", "CLASS0_CONSEQUENTIAL_BOUNDARY",
    "CLASS0_HARD_TRIGGER", "CLASS0_INHERITED_ELEVATED_OBLIGATION", "CLASS0_NO_ACCEPTANCE_REFERENCE",
    "CLASS0_PLAN_LINT", "CLASS0_SUBJECT_UNBOUNDED",
    "LINT_ACCEPTANCE_CHECK_UNKNOWN", "LINT_ACCEPTANCE_INPUT_WRITABLE", "LINT_AFFECTED_OUTSIDE_SCOPE",
    "LINT_AFFECTED_PROTECTED", "LINT_NO_ACCEPTANCE_MECHANISM",
})


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def code_writes(root: Path = SRC) -> dict[str, str]:
    """``code -> "module:line"`` for every place the product's source writes a code string (review of #218, m6 and
    G3), in each form it uses: a class's ``code =`` or ``code: T =``, a dict literal's ``"code": "X"``, a keyword
    ``code="X"``, and an ``x.code = "X"`` assignment."""
    out: dict[str, str] = {}

    def add(value: object, path: Path, line: int) -> None:
        if isinstance(value, str) and CODE_SHAPE.match(value):
            out.setdefault(value, f"{path.relative_to(root).as_posix()}:{line}")

    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
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


def defined_codes() -> dict[str, str]:
    """Every refusal code the product defines that the Lead or the operator can see, with where it is written."""
    codes = {c: where for c, where in code_writes().items() if c not in OUTSIDE_REGISTRY}
    codes.update({c: "surface/errors.py:CODES" for c in surface_errors.CODES})
    return codes


def test_the_source_scan_sees_every_class_aew_errors_defines():
    """The scan reads source; `aew.errors`' own classes, enumerated by import, are a subset of what it finds."""
    imported = {cls.code for _, cls in inspect.getmembers(errors, inspect.isclass)
                if issubclass(cls, errors.AEWError) and cls.__module__ == errors.__name__}
    found = code_writes()
    assert len(imported) > 50 and imported <= set(found)
    assert {"INVALID_REQUEST", "VALIDATION_RUNNING", "VALIDATION_CONTAINMENT_UNAVAILABLE"} <= set(found)
    assert {"NOT_COMPLETED", "BRIDGE_ERROR", "DEFECT"} <= set(found)  # dict literals (G3)


@pytest.mark.parametrize("source", [
    "class X(Exception):\n    code = 'BRAND_NEW'\n",
    "class X(Exception):\n    code: str = 'BRAND_NEW'\n",
    "reply = {'ok': False, 'error': {'code': 'BRAND_NEW', 'message': 'm'}}\n",
    "refuse(code='BRAND_NEW')\n",
    "err.code = 'BRAND_NEW'\n",
])
def test_a_new_code_written_in_any_form_is_caught(tmp_path, source):
    (tmp_path / "m.py").write_text(source, encoding="utf-8")
    assert set(code_writes(tmp_path)) == {"BRAND_NEW"}
    (tmp_path / "m.py").write_text("x = {'kind': 'BRAND_NEW'}\ncode_word = 'BRAND_NEW'\n", encoding="utf-8")
    assert code_writes(tmp_path) == {}  # a string that is not written as a code


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
