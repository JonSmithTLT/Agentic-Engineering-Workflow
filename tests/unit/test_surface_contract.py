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
        "status", "resume", "work_show", "explain", "harness_status", "harness_wait", "checkpoint", "steering",
        "resolve", "cli",
        "ticket_draft", "ticket_start", "ticket_request_review", "ticket_request_verification", "ticket_prepare",
        "integration_publish"]
    designed = {t.name for t in contract.TOOLS.values() if not t.built}
    # The stages and publication are built with the journal (F15.2): E5a builds ticket_draft and ticket_start, E5b
    # the two request stages, E6a ticket_prepare and integration_publish.
    assert designed == set()


def test_a_designed_row_is_refused_before_the_runner(monkeypatch):
    """No catalog row is DESIGNED since E6a; a row that is would be refused as TOOL_NOT_BUILT, never run."""
    designed = contract.TOOLS["integration_publish"]._replace(status=contract.DESIGNED)
    monkeypatch.setitem(contract.TOOLS, "integration_publish", designed)
    with pytest.raises(AdapterInputError) as refused:
        check_call("integration_publish", {"expect_rev": 1, "work_id": "T-0001", "prepared_candidate": "c"}, NORMAL)
    assert refused.value.code == "TOOL_NOT_BUILT"
    assert "integration_publish" not in {t.name for t in contract.exposed(NORMAL)}


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
        if t.kind in (contract.QUERY, contract.WAIT, contract.PRIMITIVE) or t.name in ("checkpoint", "steering"):
            assert not t.progression, t.name
        elif t.kind in (contract.STAGE, contract.DECISION):
            assert t.progression, t.name


def test_every_built_tool_has_a_runner_and_every_runner_a_built_tool():
    from aew.surface import stage

    # A built stage of several primitives runs through its planner and the stage executor (M4-E E5a); every other
    # built tool through its runner. Never both.
    assert not set(run.RUNNERS) & set(stage.STAGES)
    assert set(run.RUNNERS) | set(stage.STAGES) == {t.name for t in contract.TOOLS.values() if t.built}


def test_the_normal_profile_never_offers_the_cli_escape():
    assert contract.TOOLS["cli"].profiles == (RECOVERY,)
    assert "cli" not in {t.name for t in contract.exposed(NORMAL)}
    assert all(t.built for t in contract.exposed(RECOVERY))


def test_the_catalogs_engine_vocabulary_mirrors_the_engine():
    from aew.engine import primitives

    assert contract.OPERATION_CLASSES == primitives.OPERATION_CLASSES
    assert (contract.MECHANICAL, contract.POLICY_RESOLVED, contract.JUDGMENT_BEARING) == (
        primitives.MECHANICAL, primitives.POLICY_RESOLVED, primitives.JUDGMENT_BEARING)


def test_explain_takes_a_stage_with_that_stages_own_arguments():
    """M4-E E4: a stage's arguments are checked against its own schema, `expect_rev` aside; `work_id` may be given
    once, beside the stage."""
    assert check_call("explain", {"stage": "ticket_start", "work_id": "T-0001"}, NORMAL).name == "explain"
    assert check_call("explain", {"stage": "ticket_start", "work_id": "T-0001",
                                  "arguments": {"work_id": "T-0001"}}, NORMAL)  # the same unit twice is fine
    assert check_call("explain", {"stage": "ticket_draft", "arguments": {"title": "t", "risk_class": 1}}, NORMAL)
    assert check_call("explain", {"stage": "integration_publish",
                                  "arguments": {"work_id": "T-0001", "prepared_candidate": "c"}}, NORMAL)


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
    # Its primitives are declared (M4-E E5a): policy-resolved, unless an execution override promotes it.
    (contract.TOOLS["ticket_start"], {"expect_rev": 1, "work_id": "T-0001"}, POLICY_RESOLVED),
    (contract.TOOLS["ticket_start"], {"expect_rev": 1, "work_id": "T-0001", "execution": {"model": "p/m"}},
     JUDGMENT_BEARING),
    (contract.TOOLS["ticket_draft"], {"expect_rev": 1, "title": "t", "risk_class": 1}, JUDGMENT_BEARING),
    # Its expansion names primitives nobody has declared yet (E5b declares them): fail closed.
    (contract.TOOLS["ticket_request_verification"], {"expect_rev": 1, "work_id": "T-0001"}, JUDGMENT_BEARING),
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
    ("ticket_prepare", {"expect_rev": 1, "work_id": "T-0001"}, NORMAL, "INVALID_ARGUMENTS"),  # names no report
    ("ticket_start", {"expect_rev": 1, "work_id": "T-0001", "bogus": 1}, NORMAL, "INVALID_ARGUMENTS"),
    ("ticket_draft", {"expect_rev": 1, "title": "t"}, NORMAL, "INVALID_ARGUMENTS"),  # no class
    ("integration_publish", {"expect_rev": 1, "work_id": "T-0001"}, RECOVERY, "INVALID_ARGUMENTS"),  # no candidate
    # M4-E E5b: only the follow_up choice takes, and needs, the Ticket that follows it up
    ("resolve", {"expect_rev": 1, "subject": "ANM-0001", "choice": "follow_up", "rationale": "r"}, NORMAL,
     "INVALID_ARGUMENTS"),
    ("resolve", {"expect_rev": 1, "subject": "ANM-0001", "choice": "accept_risk", "follow_up": "T-0002",
                 "rationale": "r"}, NORMAL, "INVALID_ARGUMENTS"),
    ("resolve", {"expect_rev": 1, "subject": "SI-0001", "choice": "abandon", "follow_up": "T-0002",
                 "rationale": "r"}, NORMAL, "INVALID_ARGUMENTS"),
    ("resolve", {"expect_rev": 1, "subject": "ANM-0001", "choice": "follow_up", "follow_up": "not a ticket",
                 "rationale": "r"}, NORMAL, "INVALID_ARGUMENTS"),
    ("status", {"bogus": 1}, NORMAL, "INVALID_ARGUMENTS"),
    ("status", ["not", "an", "object"], NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {}, NORMAL, "INVALID_ARGUMENTS"),  # names neither a unit, an invocation nor a stage
    ("explain", {"role": "reviewer"}, NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {"stage": "status"}, NORMAL, "INVALID_ARGUMENTS"),  # not a stage (M4-E E4)
    ("explain", {"stage": "ticket_start", "arguments": {"work_id": "T-1", "bogus": 1}}, NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_draft", "arguments": {"title": "t"}}, NORMAL, "INVALID_ARGUMENTS"),  # no class
    ("explain", {"work_id": "T-0001", "arguments": {}}, NORMAL, "INVALID_ARGUMENTS"),  # arguments need a stage
    # a stage takes no dispatch argument, and one unit (PR #170 review, finding 5)
    ("explain", {"stage": "ticket_start", "work_id": "T-0001", "entrypoint": "work.dispatch"}, NORMAL,
     "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_start", "work_id": "T-0001", "invocation": "INV-0009"}, NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_request_review", "work_id": "T-0001", "role": "reviewer"}, NORMAL,
     "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_start", "work_id": "T-0001", "card": "c"}, NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_start", "work_id": "T-0001", "scope": "ticket"}, NORMAL, "INVALID_ARGUMENTS"),
    ("explain", {"stage": "ticket_start", "work_id": "T-0001", "arguments": {"work_id": "T-0002"}}, NORMAL,
     "INVALID_ARGUMENTS"),
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


# The primitives the designed stages expand to that nobody has declared yet. Until F15.2 declares them, fail-closed
# classification makes every stage that names one JUDGMENT_BEARING. This list makes that explicit: it may only shrink,
# and F15.2 empties it as it builds each stage (E5a declared work.create, plan.propose, work.transition and
# dispatch.launch; E5b declared the two ingests, so it is empty).
PENDING_F15_2: frozenset[str] = frozenset()


def test_the_primitives_still_undeclared_are_exactly_those_pending_f15_2():
    from aew.engine.primitives import spec_for

    undeclared = {p for t in contract.TOOLS.values() for p in t.expands_to if not spec_for(p).declared}
    assert undeclared == PENDING_F15_2
    assert all(not contract.TOOLS[t].built for t in contract.TOOLS
               if set(contract.TOOLS[t].expands_to) & PENDING_F15_2), "a built tool expands to an undeclared primitive"
    for name in ("ticket_start", "ticket_request_review"):  # the design's POLICY_RESOLVED stages, declared now
        t = contract.TOOLS[name]
        assert t.base_class == POLICY_RESOLVED and effective_class(t, {}) == POLICY_RESOLVED


def test_every_staged_primitive_is_declared():
    """Plan v3 §10 (SAE-07's precondition, E5a to E6a): every primitive a built stage expands to has its full
    PrimitiveSpec, with a guard that decides it (a queryable guard or a dispatch entrypoint) and the side effects it
    declares; and every built stage has a planner whose plan the stage executor can run (a step runner for each)."""
    from aew.engine.dispatch import ENTRYPOINTS
    from aew.engine.primitives import SPECS, spec_for
    from aew.surface import stage

    effects = {"control_state", "credential", "workspace", "harness_process", "authoritative_ref"}
    for t in contract.TOOLS.values():
        if t.name == "resolve" or not (t.built and t.name in stage.STAGES or (
                t.built and t.kind == contract.STAGE and len(t.expands_to) > 1)):
            continue  # `resolve` runs one of its primitives by choice: never a planned sequence
        assert t.name in stage.STAGES, f"{t.name} is built but has no planner"
        for p in t.expands_to:
            spec = spec_for(p)
            assert spec.declared and p in SPECS, (t.name, p)
            assert spec.guard_id is not None, (t.name, p, "no guard decides it")
            assert spec.guard_id in ENTRYPOINTS or spec.guard_id == p, (t.name, p, spec.guard_id)
            assert set(spec.side_effect_class.split("+")) <= effects, (t.name, p, spec.side_effect_class)
            assert p in stage.STEP_RUNNERS, (t.name, p, "no step runner")


# The engine methods the `resolve` runner calls first, by the primitive it runs (aew.surface.stage.resolve_stage).
_FIRST_CALL = {"work_dispose": "work.dispose", "stage_intent": "stage.resolve"}


class _Called(Exception):
    pass


def _runner_primitive(choice: str) -> str:
    """The primitive the live `resolve` runner runs for ``choice``: the engine method it calls first, recorded and
    stopped there (no project, nothing commits)."""
    class Engine:
        def __getattr__(self, name: str) -> Any:
            def record(*args: Any, **kwargs: Any) -> Any:
                raise _Called(name)
            return record

    args = {"expect_rev": 1, "subject": "X-0001", "choice": choice, "rationale": "r"}
    with pytest.raises(_Called) as called:
        run.RUNNERS["resolve"](run.Call(Engine(), SurfaceContext(lead_session=None, generation=None), args, "t"))
    return _FIRST_CALL[str(called.value)]


def resolve_pair_problems(mapping: dict[tuple[str, str], str]) -> list[str]:
    from aew.engine.primitives import SPECS

    schema = json.loads((SRC / "schemas" / "disposition.schema.json").read_text(encoding="utf-8"))
    kinds = tuple(schema["properties"]["subject"]["properties"]["kind"]["enum"])
    out = []
    if contract.DISPOSITION_SUBJECTS != kinds:
        out.append(f"the disposition subject kinds are {kinds} (disposition.schema.json), not "
                   f"{contract.DISPOSITION_SUBJECTS}")
    if tuple(dict.fromkeys(c for c, _ in mapping)) != contract.RESOLVE_CHOICES:
        out.append("RESOLVE_CHOICES is not the mapping's choices, in its order")
    if set(contract.TOOLS["resolve"].expands_to) != set(mapping.values()):
        out.append(f"resolve.expands_to {contract.TOOLS['resolve'].expands_to} is not the mapping's image")
    for (choice, kind), primitive in mapping.items():
        spec = SPECS.get(primitive)
        if spec is None or spec.side_effect_class in ("", "none"):
            out.append(f"({choice}, {kind}) runs {primitive!r}, which has no declared side effect")
        if _runner_primitive(choice) != primitive:
            out.append(f"({choice}, {kind}) maps to {primitive!r}, but the resolve runner runs "
                       f"{_runner_primitive(choice)!r} for {choice!r}")
    return out


def test_resolve_choice_primitive_pairs():
    """The A1 slice plan (reviewed CLEAR) §2.1 item 4 and §7: RESOLVE_CHOICE_PRIMITIVE lands with today's pairs, each
    (choice, subject kind) mapped to the one primitive the live runner runs for it, every pair's primitive declared,
    the choices and `resolve.expands_to` derived from it, and the subject kinds the disposition record's own. A1a-2 and
    A2 extend it, pair by pair.

    What it cannot see: the runner routes by `contract.DISPOSITION_CHOICES`, which is derived from this mapping at
    import, so a source edit that moves a choice from one primitive to the other moves the runner with it and passes.
    That is by design (the mapping owns the routing); the pin on today's pairs below is what names such a move. The
    runner does not route by subject kind today, so the kinds are checked against the schema, not the runner."""
    mapping = contract.RESOLVE_CHOICE_PRIMITIVE
    assert resolve_pair_problems(mapping) == []
    assert {p: sorted({c for (c, _), q in mapping.items() if q == p}) for p in set(mapping.values())} == {
        "stage.resolve": ["abandon", "continue"], "work.dispose": ["accept_risk", "follow_up", "not_applicable"]}
    # Differential: a pair that disagrees with the runner, or a choice the mapping loses, is named.
    swapped = {**mapping, ("accept_risk", "finding"): "stage.resolve"}
    assert any("(accept_risk, finding) maps to 'stage.resolve', but the resolve runner runs 'work.dispose'" in p
               for p in resolve_pair_problems(swapped))
    lost = {k: v for k, v in mapping.items() if k[0] != "abandon"}
    assert "RESOLVE_CHOICES is not the mapping's choices, in its order" in resolve_pair_problems(lost)
