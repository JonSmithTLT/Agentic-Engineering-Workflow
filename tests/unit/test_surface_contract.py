"""The typed Lead surface's catalog and result contract (F15.1, typed-lead-surface-design-v0.2 §3): closed schemas,
the catalog against the dispatch registry, effective-class promotion, auto-run eligibility and the adapter's input
errors. No project is needed here; the runner and projection are exercised in test_surface_runner.py."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from aew.engine.dispatch import ENTRYPOINTS
from aew.engine.primitives import JUDGMENT_BEARING, MECHANICAL, POLICY_RESOLVED
from aew.errors import ValidationFailed
from aew.schemas import _validator, validate_def
from aew.surface import contract, run
from aew.surface.classify import AVAILABLE, BLOCKED, UNKNOWN, auto_runnable, effective_class
from aew.surface.context import NORMAL, RECOVERY, SurfaceContext
from aew.surface.contract import Tool
from aew.surface.validate import AdapterInputError, check_call

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"


def _object_schemas(schema: Any):
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            yield schema
        for v in schema.values():
            yield from _object_schemas(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _object_schemas(v)


def _property_names(schema: Any):
    if isinstance(schema, dict):
        yield from (schema.get("properties") or {})
        for v in schema.values():
            yield from _property_names(v)
    elif isinstance(schema, list):
        for v in schema:
            yield from _property_names(v)


# ---------------------------------------------------------------------------------------------- schemas


def test_every_argument_schema_is_valid_and_closed():
    for t in contract.TOOLS.values():
        Draft202012Validator.check_schema(t.input_schema)
        objects = list(_object_schemas(t.input_schema))
        assert objects, t.name
        for obj in objects:
            assert obj.get("additionalProperties") is False, f"{t.name}: an open object schema"
        assert t.description and len(t.description) < 300, t.name  # context cost: short, specific


def test_the_result_schema_is_valid_and_every_object_in_it_is_closed():
    schema = _validator("surface").schema
    for obj in _object_schemas(schema):
        assert obj.get("additionalProperties") is False, obj


def test_expect_rev_is_required_on_every_stage_and_absent_from_every_query():
    for t in contract.TOOLS.values():
        props = t.input_schema["properties"]
        if t.kind in (contract.STAGE, contract.DECISION):
            assert "expect_rev" in props and "expect_rev" in t.input_schema["required"], t.name
        else:
            assert "expect_rev" not in props, t.name


def test_no_argument_can_carry_a_credential():
    shaped = ("token", "key", "secret", "offer", "credential", "password")
    for t in contract.TOOLS.values():
        for name in _property_names(t.input_schema):
            assert not any(s in name.lower() for s in shaped), (t.name, name)


def test_checkpoint_text_is_bounded():
    ctx_profile = NORMAL
    with pytest.raises(AdapterInputError) as exc:
        check_call("checkpoint", {"expect_rev": 1, "note": "x" * (contract.NOTE_MAX + 1)}, ctx_profile)
    assert exc.value.code == "INVALID_ARGUMENTS"
    with pytest.raises(AdapterInputError):
        check_call("checkpoint", {"expect_rev": 1, "next": "x" * (contract.NEXT_MAX + 1)}, ctx_profile)
    check_call("checkpoint", {"expect_rev": 1, "note": "x" * contract.NOTE_MAX, "next": "y" * contract.NEXT_MAX},
               ctx_profile)


# ---------------------------------------------------------------------------------------------- the catalog


def test_the_catalog_is_the_v1_catalog():
    assert list(contract.TOOLS) == [
        "status", "resume", "work_show", "explain", "harness_status", "harness_wait", "checkpoint", "cli",
        "ticket_draft", "ticket_start", "ticket_request_review", "ticket_request_verification", "ticket_prepare",
        "integration_publish"]
    designed = {t.name for t in contract.TOOLS.values() if not t.built}
    # The cli escape is built with the broker (slice B); the stages and publication with the journal (F15.2).
    assert designed == {"cli", "ticket_draft", "ticket_start", "ticket_request_review",
                        "ticket_request_verification", "ticket_prepare", "integration_publish"}


def test_dispatching_tools_name_a_registered_entrypoint_and_the_launch_and_no_other_tool_does():
    for t in contract.TOOLS.values():
        reached = set(t.expands_to) & set(ENTRYPOINTS)
        assert bool(reached) == t.dispatches, (t.name, reached)
        if t.dispatches:
            assert "dispatch.launch" in t.expands_to, f"{t.name}: a dispatching stage always launches (custody)"


def test_judgment_bearing_rows_name_their_judgments_and_others_name_none():
    for t in contract.TOOLS.values():
        if t.base_class == JUDGMENT_BEARING:
            assert t.required_judgments, t.name
        else:
            assert not t.required_judgments, t.name
        for p in t.promotes:
            assert p in t.input_schema["properties"], (t.name, p)


def test_only_workflow_advancing_rows_are_progression_rows():
    for t in contract.TOOLS.values():
        if t.kind in (contract.QUERY, contract.WAIT, contract.PRIMITIVE) or t.name == "checkpoint":
            assert not t.progression, t.name
        elif t.kind in (contract.STAGE, contract.DECISION):
            assert t.progression, t.name


def test_every_built_tool_has_a_runner_and_every_runner_a_built_tool():
    assert set(run.RUNNERS) == {t.name for t in contract.TOOLS.values() if t.built}


def test_the_normal_profile_never_offers_the_cli_escape():
    assert contract.TOOLS["cli"].profiles == (RECOVERY,)
    assert "cli" not in {t.name for t in contract.exposed(NORMAL)}
    assert all(t.built for t in contract.exposed(RECOVERY))


def test_explain_offers_only_entrypoints_a_decision_can_be_asked_of():
    offered = contract.TOOLS["explain"].input_schema["properties"]["entrypoint"]["enum"]
    assert set(offered) == {n for n, e in ENTRYPOINTS.items() if e.covered_by is None}
    assert "dispatch.launch" not in offered and "lead_broker.relay" not in offered


# ---------------------------------------------------------------------------------------------- classification

SYNTHETIC = Tool("synthetic_start", contract.STAGE, POLICY_RESOLVED, "a declared-primitive stage",
                 contract._obj({"expect_rev": contract.EXPECT_REV, "execution": contract.EXECUTION}),
                 expands_to=("work.assign", "harness.launch"), promotes=("execution",), dispatches=True,
                 mutates=True, progression=True)


@pytest.mark.parametrize(("t", "arguments", "want"), [
    (SYNTHETIC, {"expect_rev": 1}, POLICY_RESOLVED),
    (SYNTHETIC, {"expect_rev": 1, "execution": {"model": "p/m"}}, JUDGMENT_BEARING),  # an override promotes
    (contract.TOOLS["status"], {}, MECHANICAL),
    (contract.TOOLS["checkpoint"], {"expect_rev": 1}, MECHANICAL),
    (contract.TOOLS["cli"], {"argv": ["status"]}, JUDGMENT_BEARING),
    (contract.TOOLS["ticket_request_verification"], {}, JUDGMENT_BEARING),
    (contract.TOOLS["integration_publish"], {}, JUDGMENT_BEARING),
    # Its expansion names primitives nobody has declared yet (F15.2 declares them): fail closed.
    (contract.TOOLS["ticket_start"], {"expect_rev": 1, "work_id": "T-0001"}, JUDGMENT_BEARING),
    (None, {}, JUDGMENT_BEARING),
])
def test_the_effective_class_never_drops_below_the_base_and_fails_closed(t, arguments, want):
    assert effective_class(t, arguments) == want
    if t is not None:
        order = (MECHANICAL, POLICY_RESOLVED, JUDGMENT_BEARING)
        assert order.index(effective_class(t, arguments)) >= order.index(t.base_class)


def test_auto_runnable_is_only_a_built_legal_non_judgment_progression_row():
    built = SYNTHETIC
    assert auto_runnable(built, AVAILABLE, POLICY_RESOLVED)
    assert not auto_runnable(built, AVAILABLE, JUDGMENT_BEARING)
    assert not auto_runnable(built, BLOCKED, POLICY_RESOLVED)
    assert not auto_runnable(built, UNKNOWN, POLICY_RESOLVED)  # UNKNOWN is never runnable, never BLOCKED either
    assert not auto_runnable(built._replace(status=contract.DESIGNED), AVAILABLE, POLICY_RESOLVED)
    assert not auto_runnable(None, AVAILABLE, MECHANICAL)
    for t in contract.TOOLS.values():  # queries, the wait, checkpoint and cli: callable, never workflow advancement
        if not t.progression:
            assert not auto_runnable(t, AVAILABLE, MECHANICAL), t.name
    assert "profile" not in auto_runnable.__code__.co_varnames  # presentation never decides eligibility


def test_the_schema_refuses_an_auto_runnable_wait_or_unknown_action():
    action = {"action": "harness_wait", "kind": "wait", "arguments": {"runs": ["R-1"]},
              "operation_class": MECHANICAL, "availability": AVAILABLE, "callable": True, "auto_runnable": False,
              "reason_codes": [], "cli_fallback": None}
    validate_def("surface", "action", action, source="test")
    for bad in ({**action, "auto_runnable": True},
                {**action, "kind": "stage", "availability": UNKNOWN, "auto_runnable": True},
                {**action, "kind": "stage", "operation_class": JUDGMENT_BEARING, "auto_runnable": True}):
        with pytest.raises(ValidationFailed):
            validate_def("surface", "action", bad, source="test")


def test_a_decision_never_carries_a_default():
    decision = {"decision": "PUBLISH", "subject": "T-0001", "evidence": [], "tool": None, "arguments": None,
                "availability": UNKNOWN, "default": "NONE", "cli_fallback": None}
    validate_def("surface", "decision", decision, source="test")
    with pytest.raises(ValidationFailed):
        validate_def("surface", "decision", {**decision, "default": "PUBLISH"}, source="test")


# ---------------------------------------------------------------------------------------------- adapter input errors


@pytest.mark.parametrize(("name", "arguments", "profile", "code"), [
    ("no_such_tool", {}, NORMAL, "UNKNOWN_TOOL"),
    (7, {}, NORMAL, "UNKNOWN_TOOL"),
    ("ticket_start", {"expect_rev": 1, "work_id": "T-0001"}, NORMAL, "TOOL_NOT_BUILT"),
    ("integration_publish", {}, RECOVERY, "TOOL_NOT_BUILT"),
    ("status", {"bogus": 1}, NORMAL, "INVALID_ARGUMENTS"),
    ("status", ["not", "an", "object"], NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {}, NORMAL, "INVALID_ARGUMENTS"),  # names neither a unit nor an invocation
    ("harness_wait", {"runs": ["R-1", "R-1"]}, NORMAL, "INVALID_ARGUMENTS"),
    ("harness_wait", {"runs": ["R-1"], "timeout_s": 601}, NORMAL, "INVALID_ARGUMENTS"),
])
def test_ill_formed_calls_are_adapter_input_errors(name, arguments, profile, code):
    with pytest.raises(AdapterInputError) as exc:
        check_call(name, arguments, profile)
    assert exc.value.code == code
    validate_def("surface", "adapter_input_error", exc.value.to_dict(), source="test")


def test_a_tool_not_offered_on_the_callers_profile_is_concealed(monkeypatch):
    monkeypatch.setitem(contract.TOOLS, "recovery_only", Tool(
        "recovery_only", contract.QUERY, MECHANICAL, "a recovery-only query", contract._obj({}),
        profiles=(RECOVERY,)))
    with pytest.raises(AdapterInputError) as exc:
        check_call("recovery_only", {}, NORMAL)
    assert exc.value.code == "TOOL_NOT_EXPOSED" and "recovery_only" not in exc.value.details["offered"]
    assert check_call("recovery_only", {}, RECOVERY).name == "recovery_only"


def test_an_adapter_input_error_is_not_an_engine_refusal():
    from aew.errors import AEWError

    assert not issubclass(AdapterInputError, AEWError)


# ---------------------------------------------------------------------------------------------- boundaries


def test_surface_context_holds_no_secret_and_rejects_unknown_profiles():
    names = set(SurfaceContext.__dataclass_fields__)
    assert names == {"lead_session", "generation", "profile", "ingress"}
    with pytest.raises(ValueError):
        SurfaceContext(lead_session=None, generation=None, profile="godmode")
    with pytest.raises(ValueError):
        SurfaceContext(lead_session=None, generation=None, ingress="smoke-signal")


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


def test_the_engine_never_imports_the_surface():
    """The surface is an adapter over the engine; it can never become an authority the engine consults."""
    for path in (SRC / "engine").rglob("*.py"):
        assert not any(m == "aew.surface" or m.startswith("aew.surface.") for m in _imports(path)), path


def test_the_result_schema_is_registered_and_its_surface_version_matches():
    schema = _validator("surface").schema
    assert schema["$id"] == "aew/surface/v1"
    from aew.surface import SURFACE

    assert schema["$defs"]["stage_result"]["properties"]["surface"]["const"] == SURFACE
    json.dumps(schema)
