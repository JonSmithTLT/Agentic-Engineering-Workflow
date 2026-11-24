"""Register E126: the pre-F4 scope add. The Lead adds one exact test path to one Ticket's scope, on the record with a
reason, in place of cancel and replace (the operator's order of 2026-11-03; the designer's decisions of 2026-11-03, §2).
The Ticket's record never changes; one accessor gives the effective scope; a stop needs a sign-off."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from aewflow import assign, create_planned_ticket, sample_project
from invariants import assert_control_invariants, load_control

from aew.engine import scope_ops as SC
from aew.engine.api import Engine
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()
WHY = "the change to core needs its existing test extended"


def add(p, wid: str, path: str, *, signed: bool = False, rationale: str = WHY) -> dict[str, Any]:
    arguments = {"expect_rev": p.rev(), "subject": SC.item_id(wid, path), "rationale": rationale,
                 "choice": SC.SIGNED_CHOICE if signed else SC.CHOICE}
    return R.run_tool(Engine.discover(p.root), CTX, "resolve", arguments, token=p.token)


def refusal(out: dict[str, Any]) -> dict[str, Any]:
    assert not out["ok"] and out["stopped"], out
    return out["stopped"]["error"]


@pytest.fixture
def running(tmp_path):
    """A class 1 Ticket whose scope is its module only, running, with its implementer's workspace."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path, scope=("calc/core.py",))
    impl = assign(p, wid)
    return p, wid, impl


def test_a_scope_add_widens_the_effective_scope_and_never_changes_the_tickets_record(running):
    p, wid, impl = running
    before = load_control(p.root)["work"][wid]
    record = (p.root / ".aew" / before["record"]).read_bytes()
    out = add(p, wid, "tests/test_core.py")
    assert out["ok"], out
    unit = load_control(p.root)["work"][wid]
    # The record and its hash are untouched; the pointer names an immutable record that hashes to it.
    assert (p.root / ".aew" / unit["record"]).read_bytes() == record
    assert unit["record_sha256"] == before["record_sha256"]
    [ptr] = unit[SC.UNIT_KEY]
    assert ptr["added"] == "tests/test_core.py" and not ptr["signed_off"]
    doc = yaml.safe_load((p.root / ".aew" / ptr["record"]).read_text(encoding="utf-8"))
    assert doc["path"] == "tests/test_core.py" and doc["names_module"] == "core" and doc["at_base"]
    assert not doc["created_by_ticket"] and doc["rationale"] == WHY and doc["signoff"] is None
    assert any(o["code"] == SC.OBLIGATION and o["paths"] == ["tests/test_core.py"] for o in doc["obligations"])
    assert (p.root / ".aew" / "decisions" / f"{doc['decision']}.md").is_file()
    assert unit["history"][-1]["event"] == "scope_added"
    # The live implementer's pack changed: the add names it with the commands that re-dispatch it.
    assert [s["invocation"] for s in doc["stale_invocations"]] == [unit["implementer_invocation"]]
    # Every reader sees the effective scope: work show, and the gate context (an edit there is in scope now).
    assert p.ok("work", "show", wid)["effective_scope"] == ["calc/core.py", "tests/test_core.py"]
    impl.write({"tests/test_core.py": "from calc.core import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n\n\n"
                                      "def test_add_zero():\n    assert add(0, 0) == 0\n"})
    gc = Engine.discover(p.root).gate_show(wid)
    assert not gc["guardrails"]["violations"], gc["guardrails"]
    assert_control_invariants(p)


def test_a_test_removed_from_an_added_path_stops_for_a_signoff_after_the_add(running):
    p, wid, impl = running
    assert add(p, wid, "tests/test_core.py")["ok"]
    impl.write({"tests/test_core.py": "from calc.core import add\n"})  # its one test definition is gone
    violations = Engine.discover(p.root).gate_show(wid)["guardrails"]["violations"]
    assert [v["rule"] for v in violations] == [SC.SIGNOFF], violations
    assert "1 test definitions" not in violations[0]["detail"] and "0 test definitions" in violations[0]["detail"]


@pytest.mark.parametrize(("path", "reason"), [
    ("tests/*.py", "not_exact"),
    ("../tests/test_core.py", "not_exact"),
    ("calc/other.py", "not_a_test_path"),
    ("calc/core.py", "already_in_scope"),
    ("vendor/test_lib.py", "protected_path"),
])
def test_a_path_outside_the_rules_is_refused_and_nothing_is_written(running, path, reason):
    p, wid, _ = running
    error = refusal(add(p, wid, path))
    assert error["details"]["reason"] == reason, error
    assert SC.UNIT_KEY not in load_control(p.root)["work"][wid]
    assert not (p.root / ".aew" / "work" / wid / "scope-corrections").exists()


def test_an_existing_test_that_names_no_module_in_scope_is_refused(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path, scope=("calc/__init__.py",))
    error = refusal(add(p, wid, "tests/test_core.py"))
    assert error["details"]["reason"] == "names_no_scope_module", error
    # A new test file under a test directory names nothing yet, and is admitted.
    assert add(p, wid, "tests/test_init.py")["ok"]


def test_a_ticket_no_one_else_reads_is_refused_pointing_at_reclassify(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path, cls=0, scope=("calc/core.py",))
    error = refusal(add(p, wid, "tests/test_core.py"))
    assert error["details"]["reason"] == "no_independent_reader" and "aew work reclassify" in error["message"], error


def test_a_runner_config_needs_a_cited_signoff(running):
    p, wid, _ = running
    error = refusal(add(p, wid, "tests/conftest.py"))
    assert error["code"] == "GATE_UNSATISFIED" and error["details"]["reason"] == SC.SIGNOFF, error
    assert SC.SIGNED_CHOICE in error["message"]
    uncited = refusal(add(p, wid, "tests/conftest.py", signed=True, rationale="the operator said it is fine"))
    assert uncited["details"]["reason"] == "signoff_uncited", uncited
    quoted = 'the operator: "yes, give the suite a shared fixture for the socket mock"'
    assert add(p, wid, "tests/conftest.py", signed=True, rationale=quoted)["ok"]
    [ptr] = load_control(p.root)["work"][wid][SC.UNIT_KEY]
    doc = yaml.safe_load((p.root / ".aew" / ptr["record"]).read_text(encoding="utf-8"))
    assert ptr["signed_off"] and doc["signoff"]["source"] == "operator_quote"
    assert doc["signoff"]["label"] == SC.LEAD_REPORT and doc["stops"][0]["stop"] == "runner_config"
    assert_control_invariants(p)


def test_the_signoff_a_stop_names_after_the_add_is_recorded_and_clears_the_gate(running):
    """PR #540 review, M1: the stop raised after an add names `add_scope_signed`; following it records the sign-off as a
    second correction that signs the first, and the gate context is clear."""
    p, wid, impl = running
    assert add(p, wid, "tests/test_core.py")["ok"]
    impl.write({"tests/test_core.py": "from calc.core import add\n"})
    [violation] = Engine.discover(p.root).gate_show(wid)["guardrails"]["violations"]
    assert SC.SIGNED_CHOICE in violation["detail"] and SC.ITEM in violation["detail"], violation
    again = refusal(add(p, wid, "tests/test_core.py"))  # the unsigned choice names the signed one
    assert again["details"]["reason"] == "already_in_scope" and SC.SIGNED_CHOICE in again["message"], again
    quoted = 'the operator: "yes, remove the obsolete addition test"'
    out = add(p, wid, "tests/test_core.py", signed=True, rationale=quoted)
    assert out["ok"], out
    first, second = load_control(p.root)["work"][wid][SC.UNIT_KEY]
    assert not first["signed_off"] and second["signed_off"] and second["signs"] == first["id"]
    assert Engine.discover(p.root).gate_show(wid)["guardrails"]["violations"] == []
    assert p.ok("work", "show", wid)["effective_scope"] == ["calc/core.py", "tests/test_core.py"]
    # A path is signed off once: a second signed choice is refused.
    assert refusal(add(p, wid, "tests/test_core.py", signed=True, rationale=quoted))["details"]["reason"] == \
        "already_in_scope"
    assert_control_invariants(p)


def test_the_pack_lists_added_paths_apart_labelled_as_the_leads_with_their_correction_in_its_sources(running):
    """PR #540 review, M2: a reviewer sees the widening for what it is, not as declared scope."""
    from aew.knowledge import context as ctxmod

    p, wid, _ = running
    engine = Engine.discover(p.root)
    inv = load_control(p.root)["work"][wid]["implementer_invocation"]
    before = ctxmod.render(engine._packs.pack_inputs(engine.store.current(), inv)[0])
    assert "Ticket scope (allowed change paths): calc/core.py" in before and "SCOPE_CORRECTION_ADDED" not in before
    assert add(p, wid, "tests/test_core.py")["ok"]
    engine = Engine.discover(p.root)
    inputs, sources = engine._packs.pack_inputs(engine.store.current(), inv)
    text = ctxmod.render(inputs)
    assert "Ticket scope (allowed change paths), as declared: calc/core.py\n" in text, text
    assert f"- `tests/test_core.py` (SC-0001, added by the Lead on the record): {WHY}" in text, text
    assert "SCOPE_CORRECTION_ADDED" in text
    [source] = [s for s in sources if s["name"].startswith("scope_correction:")]
    assert source["name"] == "scope_correction:SC-0001" and source["path"].endswith("SC-0001.yaml")


def test_the_builtin_guardrails_check_reports_the_stop_the_gates_refuse(running):
    """PR #540 review, m4: the check the implementer acts on says what the gate context refuses."""
    p, wid, impl = running
    assert add(p, wid, "tests/test_core.py")["ok"]
    impl.write({"tests/test_core.py": "from calc.core import add\n"})
    res = impl.aew("check", "run", "guardrails")
    assert res.returncode == 0, res.stderr
    assert res.json["result"] == "fail" and SC.SIGNOFF in json.dumps(res.json), res.json


def test_a_base_that_cannot_be_listed_refuses_the_add(running, monkeypatch):
    """PR #540 review, m2: an unreadable base never reads as "every path is new"."""
    from aew.errors import GitError

    p, wid, _ = running
    real = SC.git.out

    def out(*args, **kw):
        if args[:1] == ("ls-tree",):
            raise GitError("planted: the base cannot be listed")
        return real(*args, **kw)

    monkeypatch.setattr(SC.git, "out", out)
    assert refusal(add(p, wid, "tests/test_core.py"))["details"]["reason"] == "base_unreadable"
    assert SC.UNIT_KEY not in load_control(p.root)["work"][wid]


def test_an_add_that_would_make_two_live_tickets_meet_is_refused(tmp_path):
    """PR #540 review, m3: the widened scope meets another live Ticket's (E151), which only the add creates."""
    p = sample_project(tmp_path)
    first = create_planned_ticket(p, tmp_path, title="core", scope=("calc/core.py",))
    other = create_planned_ticket(p, tmp_path, title="tests", scope=("tests/test_core.py",))
    assign(p, first)
    assign(p, other)
    error = refusal(add(p, first, "tests/test_core.py"))
    assert error["details"]["reason"] == "files_conflict", error
    assert SC.UNIT_KEY not in load_control(p.root)["work"][first]
