"""Role archetypes and cards: validation and authority-escalation rejection (ADR-0006)."""

from __future__ import annotations

import pytest

from aew import roles
from aew.engine.authority import ROLE_OPERATIONS
from aew.errors import PermissionDenied, ValidationFailed
from aew.util import dump_yaml


def card(**overrides):
    base = {"schema": "aew/role/v1", "role": "test_card", "display_name": "Test", "extends": "implementer",
            "purpose": "test"}
    base.update(overrides)
    return base


@pytest.mark.parametrize("name", roles.ARCHETYPES)
def test_archetypes_load(name):
    assert roles.archetype(name)["role"] == name


def test_archetype_documentation_matches_enforced_authority():
    for name in roles.ARCHETYPES:
        arch = roles.archetype(name)
        if arch["dispatchable"]:
            assert set(arch["engine_operations"]) == ROLE_OPERATIONS[name], name
    assert "specialist" not in ROLE_OPERATIONS  # specialist expertise is a card concern (WC §5.8)


def test_builtin_deck_is_valid_and_defaults_exist():
    deck = roles.builtin_cards()
    for name in ("implementer", "reviewer", "verifier"):
        assert roles.default_card(name) in deck
    assert deck["security_reviewer"].meta["specialty"] == "security"
    assert all(c.source == "builtin" and len(c.sha256) == 64 for c in deck.values())


@pytest.mark.parametrize(
    ("meta", "error"),
    [
        (card(extends="lead"), PermissionDenied),                       # single Lead lineage
        (card(extends="frontier_advisor"), PermissionDenied),
        (card(extends="product_owner"), ValidationFailed),              # unknown archetype
        (card(authority=["publish"]), ValidationFailed),                # no field can grant authority
        (card(allowed_operations=["integrate.publish"]), ValidationFailed),
        (card(restrict={"operations": ["check.run", "integrate.publish"]}), PermissionDenied),
        (card(extends="reviewer", required_capabilities=["source_mutation"]), PermissionDenied),
        (card(optional_capabilities=["integration_control"]), PermissionDenied),
        (card(extends="verifier", required_capabilities=["verification_failure_classification"]), PermissionDenied),
        (card(specialty="security"), ValidationFailed),                 # specialty is reviewer-only
    ],
)
def test_escalation_is_rejected(meta, error):
    with pytest.raises(error):
        roles.validate_card(meta, source="test")


def test_narrowing_and_ordinary_capabilities_are_allowed():
    roles.validate_card(card(restrict={"operations": ["submit.implementation_report"]}), source="t")
    roles.validate_card(card(extends="investigator", role="vulnerability_triager",
                             required_capabilities=["candidate_finding_query", "exact_code_search"],
                             optional_capabilities=["binary_analysis", "crash_replay", "relationship_discovery"],
                             skills=["example/finding-triage"], outputs=["vulnerability_triage_report"],
                             use_when=["sanitizer crash", "suspected duplicate"]), source="t")


def test_project_catalog_loading(tmp_path):
    (tmp_path / "rust_engineer.yaml").write_text(dump_yaml(card(role="rust_engineer", display_name="Rust Engineer")))
    (tmp_path / "evil.yaml").write_text(dump_yaml(card(role="evil", extends="lead")))
    (tmp_path / "dupe.yaml").write_text(dump_yaml(card(role="c_engineer", display_name="Shadow")))
    catalog = roles.load_catalog(tmp_path)
    assert catalog.cards["rust_engineer"].source == "project"
    assert "evil" not in catalog.cards
    assert catalog.cards["c_engineer"].source == "builtin"  # never silently shadowed
    assert len(catalog.problems) == 2
    assert any("collides" in p for p in catalog.problems)
