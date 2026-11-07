"""Harness capabilities (steering design §7): each adapter declares what it provides, each feature names what it needs,
and a feature that needs a capability a harness neither provides nor marks as a gap with a register row fails here.
The operator's rule: "supported on both", or "noted as work for us to add to the AEW build of Codex"."""

from __future__ import annotations

from pathlib import Path

import yaml

from aew.harness import harness_capabilities as H
from aew.harness.opencode.adapter import OpenCodeAdapter

REGISTER = Path(__file__).resolve().parents[2] / "docs" / "implementation" / "future-work.yaml"


def register_ids() -> set[str]:
    data = yaml.safe_load(REGISTER.read_text(encoding="utf-8"))
    rows: list[dict] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "#" in node:
                rows.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return {str(r["#"]) for r in rows}


def test_every_feature_is_supported_or_a_recorded_gap_on_every_harness():
    assert H.problems() == []


def test_a_capability_no_harness_column_holds_fails_the_check():  # the control of the case above
    columns = {k: dict(v) for k, v in H.declarations().items()}
    del columns[H.OPENCODE]["read_progress"]
    assert H.problems(columns) == ["opencode: progress_digest needs read_progress, which is neither declared nor a gap"]


def test_a_gap_without_a_register_row_fails_the_check():
    columns = {k: dict(v) for k, v in H.declarations().items()}
    columns[H.CODEX_NAME]["queue_until_turn_end"] = H.Support(H.GAP, "no native queue")
    assert H.problems(columns) == ["codex: push_wake needs queue_until_turn_end, a gap with no register row"]


def test_a_declared_name_that_is_not_a_capability_fails_the_check():
    columns = {k: dict(v) for k, v in H.declarations().items()}
    columns[H.OPENCODE]["read_minds"] = H.Support(H.YES, "no")
    assert H.problems(columns) == ["opencode: 'read_minds' is not a capability"]


def test_the_opencode_adapter_declares_its_own_column_in_code():
    assert H.declarations()[H.OPENCODE] is OpenCodeAdapter.harness_capabilities
    assert set(OpenCodeAdapter.harness_capabilities) == set(H.CAPABILITIES)


def test_every_harness_column_states_every_capability():
    for harness, column in H.declarations().items():
        assert set(column) == set(H.CAPABILITIES), harness


def test_every_gap_names_a_row_of_the_register():
    ids = register_ids()
    gaps = [(h, c, s.register) for h, col in H.declarations().items() for c, s in col.items() if s.status == H.GAP]
    assert gaps, "PR 0 found Codex gaps; they are recorded"
    for harness, cap, row in gaps:
        assert row in ids, f"{harness} {cap}: register row {row} does not exist"


def test_the_codex_column_holds_pr0s_measured_answers():
    codex = H.CODEX
    assert codex["queue_until_turn_end"].status == H.GAP  # C2: a busy thread is steered, no native queue
    assert codex["attach_to_operator_session"].status == H.GAP  # B1/B2: AEW hosts the app-server, TUI --remote
    assert "thread/inject_items" in codex["mark_non_operator_input"].how  # C4: snake case, not injectItems
    assert all(codex[c].status == H.YES for c in ("wake_idle_session", "steer_running_turn", "interrupt_turn"))


def test_every_feature_needs_only_named_capabilities():
    for feature, (needs, _) in H.FEATURES.items():
        assert needs and set(needs) <= set(H.CAPABILITIES), feature
