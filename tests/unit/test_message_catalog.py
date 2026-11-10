"""MS3 switch catalog, compact description parity, schemas and the normal MCP byte cap."""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from aew.surface import contract, mcp, run, stage
from aew.surface.classify import AVAILABLE, auto_runnable
from aew.surface.validate import AdapterInputError, check_call


def without_descriptions(value):
    if isinstance(value, dict):
        return {k: without_descriptions(v) for k, v in value.items() if k != "description"}
    if isinstance(value, list):
        return [without_descriptions(v) for v in value]
    return value


def test_the_catalog_with_every_switch_is_the_v1_catalog_plus_message_send():
    assert list(contract.catalog(contract.ALL_SWITCHES)) == [*contract.catalog(), "message_send"]
    assert set(contract.ALL_SWITCHES) == {"coordination.messaging"}
    assert "message_send" not in contract.catalog()


def test_the_compact_presentation_changes_only_descriptions():
    before = copy.deepcopy(contract.TOOLS)
    off = contract.catalog()
    compact = contract.catalog(presentation="compact")
    for name, original in off.items():
        changed = compact[name]
        assert without_descriptions(original.input_schema) == without_descriptions(changed.input_schema)
        assert original._replace(description=changed.description, input_schema=changed.input_schema) == changed
        assert mcp.tool_entry(original)["annotations"] == mcp.tool_entry(changed)["annotations"]
    assert contract.TOOLS == before
    assert "message_send" not in compact  # no standalone compact policy switch is enabled by this slice


def test_the_normal_surface_fits_the_budget_in_both_configurations():
    for switches, pin, count in [(frozenset(), 11704, 15), (contract.ALL_SWITCHES, 11772, 16)]:
        # Designed normal rows count too, even though tools/list does not offer them yet.
        listing = {"tools": [mcp.tool_entry(t) for t in contract.catalog(switches).values() if "normal" in t.profiles]}
        assert len(listing["tools"]) == count
        assert len(json.dumps(listing, separators=(",", ":"))) == pin
        assert pin <= 11900


@pytest.mark.parametrize("switches", [frozenset(), contract.ALL_SWITCHES], ids=["off", "on"])
@pytest.mark.parametrize("profile", ["normal", "recovery"])
def test_every_built_row_is_offered_on_exactly_its_declared_profiles(switches, profile):
    rows = contract.catalog(switches)
    offered = contract.exposed(profile, switches)
    assert offered == [t for t in rows.values() if t.built and profile in t.profiles]
    assert ("cli" in {t.name for t in offered}) == (profile == "recovery")
    assert ("message_send" in {t.name for t in offered}) == bool(switches)


@pytest.mark.parametrize("value", ["not JSON", "{}", '"coordination.messaging"', '[7]', '["unknown"]'])
def test_malformed_or_unknown_environment_hints_offer_no_switched_tools(monkeypatch, value):
    monkeypatch.setenv(contract.ENV_SWITCHES, value)
    assert not contract.switches_from_env()


def test_message_send_is_mechanical_never_auto_runnable_never_journaled_and_dispatches_nothing():
    tool = contract.catalog(contract.ALL_SWITCHES)["message_send"]
    assert tool.kind == contract.STAGE and tool.base_class == contract.MECHANICAL
    assert tool.expands_to == ("message.send",) and tool.mutates
    assert not tool.dispatches and not tool.progression and not tool.required_judgments
    assert not auto_runnable(tool, AVAILABLE, contract.MECHANICAL)
    assert "message_send" in run.RUNNERS and "message_send" not in stage.STAGES


@pytest.mark.parametrize("change", [{"expect_rev": None}, {"body": ""}, {"body": "x" * 4001},
                                    {"when": "queue"}, {"idempotency_id": "invalid/ID"},
                                    {"refs": ["source:x"] * 9}, {"token": "not-an-argument"}])
def test_message_send_bounds_are_enforced_before_the_runner(change):
    args = {"expect_rev": 1, "to": "INV-0001", "body": "Check shutdown.", **change}
    with pytest.raises(AdapterInputError):
        check_call("message_send", args, "normal", contract.ALL_SWITCHES)


def _off_only_iterations(tree):
    """Direct catalog iteration, including comprehensions; not alias or dynamically generated iteration."""
    offenders = []
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")):
        if fn.name == "test_the_catalog_is_the_v1_catalog":
            continue
        for node in ast.walk(fn):
            if isinstance(node, (ast.For, ast.comprehension)):
                expression = ast.unparse(node.iter)
                if expression == "contract.TOOLS" or expression.startswith("contract.TOOLS."):
                    offenders.append(fn.name)
    return offenders


def test_every_catalog_test_covers_every_switch_configuration():
    path = Path(__file__).with_name("test_surface_contract.py")
    assert not _off_only_iterations(ast.parse(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("body", ["for row in contract.TOOLS: pass", "for row in contract.TOOLS.values(): pass",
                                "rows = [r for r in contract.TOOLS.items()]",
                                "rows = {r for r in contract.TOOLS.keys()}"])
def test_the_catalog_iteration_guard_catches_planted_off_only_loops(body):
    assert _off_only_iterations(ast.parse(f"def test_new():\n    {body}\n")) == ["test_new"]
