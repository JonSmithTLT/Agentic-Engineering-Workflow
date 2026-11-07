"""Harness capabilities (steering design §7): each adapter declares what it provides, each feature names what it needs,
and a feature that needs a capability a harness neither provides nor marks as a gap with a register row fails here.
That each gap's register row exists is checked by ``tests/unit/test_harness_capability_register.py`` (the register is
a docs file, which a unit test may read). The operator's rule: "supported on both", or "noted as work for us to add
to the AEW build of Codex"."""

from __future__ import annotations

from aew.harness import harness_capabilities as H
from aew.harness.opencode.adapter import OpenCodeAdapter


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


def test_the_codex_column_holds_pr0s_measured_answers():
    codex = H.CODEX
    assert codex["queue_until_turn_end"].status == H.GAP  # C2: a busy thread is steered, no native queue
    assert codex["attach_to_operator_session"].status == H.GAP  # B1/B2: AEW hosts the app-server, TUI --remote
    assert "thread/inject_items" in codex["mark_non_operator_input"].how  # C4: snake case, not injectItems
    assert all(codex[c].status == H.YES for c in ("wake_idle_session", "steer_running_turn", "interrupt_turn"))


def test_opencodes_non_operator_mark_is_declared_as_the_text_header_it_is():
    """The design records OpenCode's mark as "text only": a header the model reads, not a role of its own (Codex's
    `thread/inject_items` gives one). The declaration says so, rather than `yes`."""
    mark = OpenCodeAdapter.harness_capabilities["mark_non_operator_input"]
    assert mark.status == H.PARTIAL and "text only" in mark.how
    assert H.CODEX["mark_non_operator_input"].status == H.YES


def test_a_status_outside_yes_partial_and_gap_fails_the_check():
    columns = {k: dict(v) for k, v in H.declarations().items()}
    columns[H.OPENCODE]["read_usage"] = H.Support("maybe", "unsure")
    assert H.problems(columns) == ["opencode: read_usage has status 'maybe', not yes, partial or gap"]


def test_every_feature_needs_only_named_capabilities():
    for feature, (needs, _) in H.FEATURES.items():
        assert needs and set(needs) <= set(H.CAPABILITIES), feature
