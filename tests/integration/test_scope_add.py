"""Register E126: the pre-F4 scope add. The Lead adds one exact test path to one Ticket's scope, on the record with a
reason, in place of cancel and replace (the operator's order of 2026-11-03; the designer's decisions of 2026-11-03, §2).
The Ticket's record never changes; one accessor gives the effective scope; a stop needs a sign-off."""

from __future__ import annotations

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
