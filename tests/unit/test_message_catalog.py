"""MS3 switch catalog, compact description parity, schemas and normal MCP projection."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pytest
from catalog_reads import CatalogRead, off_only_reads

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


# Audited direct off readers, not a blanket file exemption. Counts pin each function's reads, so a new site must be
# classified even inside an existing file. The shared helper names aliases/getattr/dynamic access as coverage limits;
# a same-count replacement in an audited scope still needs semantic review. Switched invariants live in CATALOGS.
OFF_READERS = {
    "src/aew/harness/opencode/projection.py": (
        "Known MS3 limit: import-time off summary; snapshot-aware naming belongs to reply/attention.", {"_named": 1}),
    "src/aew/harness/steering_loop.py": (
        "Only progression actions are picked, and ingesting_action reads only planned stages; message_send never "
        "progresses and has no planner.", {"SteeringLoop.tick": 1, "ingesting_action": 1}),
    "src/aew/surface/availability.py": (
        "Only planned workflow stages; message_send has no planner.", {"_compose": 1}),
    "src/aew/surface/mcp.py": ("Wait classification only; message_send is not a wait.", {"_is_wait": 1}),
    "src/aew/surface/projection.py": (
        "Only projected workflow actions; message_send is not a projection action.", {"_action": 1, "_project": 1}),
    "src/aew/surface/readable.py": (
        "Primitive-to-stage rendering; record-only send has no completed step.", {"<module>": 1}),
    "src/aew/surface/stage.py": (
        "Intent contract metadata; message_send is never journaled.", {"_always": 1, "_contract_now": 1}),
    "src/aew/surface/validate.py": (
        "Explain's stage argument accepts only planner-backed stages, not message_send.", {"_check_explain": 2}),
    "tests/helpers/discovery/rules.py": (
        "Off text naming and argument audit; on send has no credential-shaped arguments (CATALOGS proves it).",
        {"o_cmd": 1, "check": 1, "tool_argument_secrets": 1}),
    "tests/helpers/relayed_opens.py": (
        "Existing read-only argument probes; send is mutating, not a relay-read case.", {"main": 1}),
    "tests/integration/test_stage_resolve.py": (
        "Named workflow-stage fixtures/contract mutations; message_send has no intent.",
        {"project": 1, "crashed_stage": 1, "test_continue_re_resolves_the_stage_contract": 1,
         "test_a_continued_stage_ends_where_an_uninterrupted_one_and_its_primitives_do": 1}),
    "tests/integration/test_stage_runner.py": ("Named planned-stage fixture.", {"project": 1}),
    "tests/integration/test_stages_request.py": ("Named planned-stage fixture.", {"stages_named": 1}),
    "tests/integration/test_ticket_priority_draft.py": (
        "Named ticket_draft priority field wording; unrelated to message_send or switch-registered rows.",
        {"test_ticket_draft_refuses_a_low_or_critical_priority_with_no_reason_naming_its_field": 1}),
    "tests/integration/test_steering_loop.py": (
        "Planned/progression fixtures and judgment cases; on send is non-progression (CATALOGS proves it).",
        {"p": 1, "test_walk_confirms_unknown_or_undeclared_effects": 1,
         "test_the_live_catalog_meets_what_the_loop_relies_on": 1,
         "test_a_dead_custodian_ended_under_an_auto_run_step": 1}),
    "tests/unit/test_capability_commands.py": (
        "Send's primitive is not a capability command; catalog expansion is pinned separately.",
        {"test_no_typed_tool_and_no_worker_bridge_operation_runs_a_register_command": 1}),
    "tests/unit/test_discovery_rules.py": (
        "Off-text fixtures and planted argument mutations.",
        {"test_o_cmd_checks_typed_tool_names_against_the_contract": 1,
         "test_o_secret_reads_the_typed_tools_arguments": 2}),
    "tests/unit/test_lead_reachability.py": (
        "Send has no operator-only primitive, pinned by the on catalog contract.",
        {"test_no_typed_tool_reaches_an_operator_only_command": 2}),
    "tests/unit/test_lead_text.py": (
        "Off-text goldens/planting and workflow guidance; on message_send omission is the documented MS3 limit.",
        {"plant": 1, "stage_named": 1, "known_words": 1, "stray_arguments": 4,
         "test_every_normal_tool_is_named_in_what_the_lead_is_given": 2,
         "test_the_list_follows_the_catalog_when_a_tool_goes": 1,
         "test_the_text_names_no_tool_the_normal_profile_lacks": 2,
         "test_a_tool_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard": 2,
         "test_an_argument_renamed_on_one_tool_with_its_old_name_left_beside_it_fails_the_guard": 2,
         "test_an_argument_renamed_in_the_catalog_with_its_old_name_left_fails_the_guard": 1,
         "test_a_lead_command_template_names_only_real_tools_and_takes_no_stage_step_from_the_shell": 1,
         "test_a_verifier_mode_decision_names_the_publish_with_its_report_and_candidate": 1}),
    "tests/unit/test_message_catalog.py": (
        "Off baseline must remain unmodified by compacting.",
        {"test_the_compact_presentation_changes_only_descriptions": 2}),
    "tests/unit/test_operator_endpoint.py": (
        "Named raise/confirmation tools; message_send is mechanical, with no operator principal.",
        {"test_no_operator_principal_outside_the_endpoint": 2}),
    "tests/unit/test_scheduler_priority.py": (
        "Named ticket_draft priority schema/authority; messaging changes neither that row nor its level owner.",
        {"test_the_levels_have_one_owner_the_control_schema": 1}),
    "tests/unit/test_stage_availability.py": (
        "Planner-backed stages only; message_send is deliberately outside that table.",
        {"test_the_migrated_stage_table_matches_the_catalog": 2,
         "test_an_unmigrated_guard_makes_the_stage_unknown_never_blocked_and_never_auto_runnable": 1,
         "test_a_judgment_bearing_stage_is_never_auto_runnable_however_available": 1, "disagreements": 1,
         "test_the_agreement_check_binds_a_planner_that_adds_what_a_guard_reads": 1}),
    "tests/unit/test_surface_contract.py": (
        "Exact off list, named rows and planted off mutations; row-wide invariants use all CATALOGS.",
        {"test_the_catalog_is_the_v1_catalog": 2, "test_a_designed_row_is_refused_before_the_runner": 3,
         "test_the_normal_profile_never_offers_the_cli_escape": 3,
         "test_explain_offers_only_entrypoints_a_decision_can_be_asked_of": 1,
         "test_the_effective_class_never_drops_below_the_base_and_fails_closed": 9,
         "test_a_tool_not_offered_on_the_callers_profile_is_concealed": 1,
         "test_the_primitives_still_undeclared_are_exactly_those_pending_f15_2": 1, "resolve_pair_problems": 2}),
    "tests/unit/test_surface_map.py": (
        "Planted row mutations/restoration, not live enumeration (which uses _tools()).",
        {"shared_state": 1, "<module>": 8, "test_home_built_waits_until_every_use_is_covered": 2,
         "test_a_stage_takes_only_the_edges_its_arguments_can": 1,
         "test_a_home_covers_a_state_selected_use_only_if_it_starts_there": 2,
         "test_an_ablation_restores_a_registry_in_its_order": 8}),
    "tests/unit/test_surface_mcp.py": (
        "Off wire golden and named historical stage rows; on budget/profiles are tested here separately.",
        {"test_the_catalogs_listed_tools_are_its_built_rows_only": 2, "_a1_rows": 1, "test_a1_rows_measured": 1}),
    "tests/unit/test_surface_readable.py": (
        "Completed-step bound; message_send has none and cannot increase it.",
        {"test_the_step_bound_is_the_longest_stage_in_the_catalog": 1}),
}


def test_direct_off_only_catalog_readers_in_source_and_tests_are_audited():
    root = Path(__file__).resolve().parents[2]
    actual = {}
    for directory in ("src", "tests"):
        for path in sorted((root / directory).rglob("*.py")):
            reads = off_only_reads(path.read_text(encoding="utf-8"))
            if reads:
                actual[path.relative_to(root).as_posix()] = dict(Counter(r.scope for r in reads))
    assert actual == {path: scopes for path, (reason, scopes) in OFF_READERS.items() if reason}


@pytest.mark.parametrize("body", ["for row in contract.TOOLS: pass", "for row in contract.TOOLS.values(): pass",
                                "rows = [r for r in contract.TOOLS.items()]",
                                "rows = {r for r in contract.TOOLS.keys()}", "row = contract.tool(name)",
                                "rows = contract.exposed(profile)"])
def test_the_shared_guard_catches_planted_off_only_readers(body):
    assert len(off_only_reads(f"def planted():\n    {body}\n")) == 1


def test_the_shared_guard_handles_imports_and_keeps_switch_aware_calls():
    assert off_only_reads("from aew.surface.contract import TOOLS\nrows = list(TOOLS)") == [
        CatalogRead("<module>", "TOOLS")]
    assert not off_only_reads("rows = contract.exposed(profile, switches)\nrow = contract.tool(name, switches=s)")
