"""D2's pins against the page (docs/implementation/vertical-uat.md §8): the per-rule modes agree with
``tests/helpers/discovery/modes.py``, and the code registry lists every refusal code the product defines, so neither
can drift (discovery-layer spec v3.4, §2.3 and §5)."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from discovery import modes, registry

from aew import errors
from aew.surface import errors as surface_errors

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "implementation" / "vertical-uat.md"
SRC = ROOT / "src" / "aew"
# The one refusal code written as a literal rather than declared by a class: the `cli` escape's answer when its
# command answered `ok: false`. The test finds it in the module that writes it.
LITERAL_CODES = {"NOT_COMPLETED": SRC / "surface" / "run.py"}


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def class_codes(root: Path = SRC) -> dict[str, str]:
    """``code -> "module:Class"`` for every class in the product's source that declares a string ``code`` (review of
    #218, m6): `aew.errors`, and the error classes other modules define (the dashboard's, the validation runner's)."""
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.ClassDef):
                continue
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign) and any(getattr(t, "id", None) == "code" for t in stmt.targets)
                        and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)):
                    out.setdefault(stmt.value.value, f"{path.relative_to(root).as_posix()}:{node.name}")
    return out


def defined_codes() -> dict[str, str]:
    """Every refusal code the product defines that the Lead or the operator can see, with where it is defined."""
    codes = class_codes()
    codes.update({c: "surface/errors.py:CODES" for c in surface_errors.CODES})
    for code, module in LITERAL_CODES.items():
        assert f'"{code}"' in module.read_text(encoding="utf-8"), f"{code} is no longer written in {module.name}"
        codes[code] = f"{module.relative_to(SRC).as_posix()} (literal)"
    return codes


def test_the_source_scan_sees_every_class_aew_errors_defines():
    """The scan reads source; `aew.errors`' own classes, enumerated by import, are a subset of what it finds."""
    imported = {cls.code for _, cls in inspect.getmembers(errors, inspect.isclass)
                if issubclass(cls, errors.AEWError) and cls.__module__ == errors.__name__}
    assert len(imported) > 50 and imported <= set(class_codes())
    assert {"INVALID_REQUEST", "VALIDATION_RUNNING", "VALIDATION_CONTAINMENT_UNAVAILABLE"} <= set(class_codes())


def test_a_new_error_class_anywhere_in_the_source_is_caught(tmp_path):
    (tmp_path / "m.py").write_text("class X(Exception):\n    code = 'BRAND_NEW'\n", encoding="utf-8")
    assert class_codes(tmp_path) == {"BRAND_NEW": "m.py:X"}


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
