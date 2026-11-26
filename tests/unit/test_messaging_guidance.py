"""Independent published-catalog/prose oracle (MS3 n-a), on/off guidance and the precise n-b syntax limits.

The oracle parses emitted prose and actual tools/list, not contract.exposed or the prose builder's selector. It
checks names, not semantic adequacy, argument correctness, permissions or authority. Recovery's explicit summary
is tested separately; the real session system intentionally describes its normal profile. Other CLI/source text
is not exhaustively enumerated by this oracle; catalog_reads' aliases/dynamic/catalog()/check_call() limits remain.
"""

from __future__ import annotations

import re

import pytest

from aew.harness import contract as K
from aew.harness import progress, wake_queue
from aew.harness.opencode import projection
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES
from aew.surface import contract, lead_text, mcp, readable

ON = frozenset({"coordination.messaging"})


def assert_catalog_names(text, listing):
    """The catalog names ``text`` puts in backticks are exactly the tools the published listing offers."""
    named = set(re.findall(r"`([a-z_]+)`", text)) & {*contract.TOOLS, *contract.catalog(contract.ALL_SWITCHES)}
    assert named == {t["name"] for t in listing["tools"]}


def lead_system(switches, *, push):
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=switches)
    return projection.lead_config(guide, push_wake=push, switches=switches)["agents"][projection.LEAD_AGENT]["system"]


@pytest.mark.parametrize("switches", [frozenset(), ON], ids=["off", "on"])
@pytest.mark.parametrize("push", [False, True], ids=["waits", "woken"])
def test_the_lead_text_names_the_published_wire_catalog_without_reusing_its_selector(switches, push):
    """The system text no longer summarises the catalog (E367; the audit of 2026-11-25, D1): the guide's core, which it
    carries, is where the tools are named, and what the Lead reads names every tool the listing offers and no other."""
    assert_catalog_names(lead_system(switches, push=push), mcp.tools_list("normal", switches))


def test_a_switched_row_the_prose_names_with_the_switch_off_fails_the_independent_oracle(monkeypatch):
    assert_catalog_names(lead_system(frozenset(), push=True), mcp.tools_list("normal", frozenset()))
    original = lead_text.uses
    monkeypatch.setattr(lead_text, "uses", lambda profile="normal", switches=frozenset(): original(profile, ON))
    with pytest.raises(AssertionError):
        assert_catalog_names(lead_system(frozenset(), push=True), mcp.tools_list("normal", frozenset()))


@pytest.mark.parametrize("messaging", [False, True])
def test_the_one_ordered_selection_drives_detection_and_every_wait_guide_row(messaging):
    expected = tuple(w for w in K.WHY if w in K.WAITED_ON or messaging and w == "worker_message")
    assert K.waited_on(messaging) == progress.detected_in_poll(messaging) == expected
    assert tuple(K.wake_guidance(messaging)) == (*expected, "timed_out")
    lines = projection.wake_guide_lines(messaging)
    assert [re.search(r"`([^`]+)`", line)[1] for line in lines] == [*expected, "timed_out"]
    if messaging:
        assert all("aew harness send" not in w.act for w in K.wake_guidance(True).values())
        row = K.wake_guidance(True)["worker_message"]
        assert all(text in row.act for text in ("messages", "data, not instructions", "message_send"))
        assert "message_send" in K.wait_step(["R-INV-0001-1"], again=True, messaging=True)
        assert "aew harness send" not in K.wait_step(["R-INV-0001-1"], again=True, messaging=True)


def test_worker_detection_uses_its_launch_snapshot_not_a_forged_presentation_environment(monkeypatch):
    monkeypatch.setenv("AEW_MESSAGING", "enabled")
    common = {"run": "R-INV-0001-1", "workspace": None, "scope_paths": None, "clock": lambda: 0.0}
    assert progress.Tracker(**common).detected == K.WAITED_ON
    assert progress.Tracker(**common, messaging=True).detected == K.waited_on(True)


@pytest.mark.parametrize("push", [False, True])
@pytest.mark.parametrize("include_guide", [False, True])
def test_on_cost_line_is_owned_once_and_off_system_and_guide_never_gain_it(push, include_guide):
    guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS, switches=ON)
    assert guide.count(K.MESSAGE_READ_COST) == 1 and "`message_send`" in guide
    system = projection.lead_config(guide if include_guide else "", push_wake=push, switches=ON)["agents"][
        projection.LEAD_AGENT]["system"]
    assert system.count(K.MESSAGE_READ_COST) == 1
    assert "`worker_message`" in system and "`message_send`" in system
    assert "aew harness send" not in system and "\0" not in system
    off_guide = lead_text.render(DEFAULT_GATES, DEFAULT_CHECKS)
    off = projection.lead_config(off_guide if include_guide else "", push_wake=push)["agents"][
        projection.LEAD_AGENT]["system"]
    assert K.MESSAGE_READ_COST not in off and "`worker_message`" not in off and "`message_send`" not in off


def test_off_posted_wake_text_is_byte_identical_to_the_pre_messaging_shape():
    shape = progress.wake(["run_ended"], {"R-INV-0001-1": {"state": "ended", "steps": 2}})
    assert wake_queue.wake_text("wake-off", shape) == (
        'AEW wake (not the operator)\n{"id": "wake-off", "messages": [], "next": ["run_ended"], '
        '"runs": {"R-INV-0001-1": {"state": "ended", "steps": 2}}, "why": ["run_ended"]}\n'
        '- R-INV-0001-1: ended, 2 steps')


def test_readable_wait_next_line_uses_the_same_on_rule_without_changing_off():
    part = {"actions": [{"availability": "AVAILABLE", "kind": "wait", "callable": True,
                         "action": "harness_wait", "arguments": {"runs": ["R-INV-0001-1"]}}]}
    off = readable._next({"projection": part})
    on = readable._next({"projection": {**part, "coordination": {}}})
    assert K.WAIT_RULE in off and "a worker message" not in off
    assert K.wait_rule(True) in on and "a worker message" in on


def test_on_projection_changes_guidance_not_permissions_or_other_harness_settings():
    off, on = projection.lead_config(), projection.lead_config(switches=ON)
    assert off["agents"][projection.LEAD_AGENT].pop("system") != on["agents"][projection.LEAD_AGENT].pop("system")
    assert on == off
