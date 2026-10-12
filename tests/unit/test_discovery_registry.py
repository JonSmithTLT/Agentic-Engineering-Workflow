"""D2's pins against the page (docs/implementation/vertical-uat.md §8): the per-rule modes agree with
``tests/helpers/discovery/modes.py``, and the code registry lists every code ``aew.errors`` defines, so neither can
drift (discovery-layer spec v3.4, §2.3 and §5)."""

from __future__ import annotations

import inspect
from pathlib import Path

from discovery import modes, registry

from aew import errors

DOC = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "vertical-uat.md"


def page() -> str:
    return DOC.read_text(encoding="utf-8")


def defined_codes() -> dict[str, type[errors.AEWError]]:
    """Every refusal code ``aew.errors`` defines, from its classes."""
    out = {}
    for _, cls in inspect.getmembers(errors, inspect.isclass):
        if issubclass(cls, errors.AEWError) and cls.__module__ == errors.__name__:
            out[cls.code] = cls
    return out


def test_the_per_rule_modes_on_the_page_are_the_modes_the_helpers_pin():
    assert registry.doc_modes(page()) == modes.MODES
    assert set(modes.MODES) == set(modes.RULES)
    assert set(modes.MODES.values()) <= set(modes.MODE_VALUES)


def test_a_mode_on_the_page_that_differs_from_the_helpers_is_caught():
    text = page()
    mutant = text.replace("| O-IDS | `shadow` |", "| O-IDS | `enforce` |", 1)
    assert mutant != text
    assert registry.doc_modes(mutant) != modes.MODES


def test_every_code_aew_errors_defines_is_in_the_registry():
    codes = defined_codes()
    assert len(codes) > 50 and "PERMISSION_DENIED" in codes
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
