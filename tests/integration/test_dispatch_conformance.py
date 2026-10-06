"""Dispatch-entrypoint conformance (M4-A; m4-ambiguity-report.md §2.1, plan review 2026-10-03).

Every way to dispatch is a declared entrypoint (``aew.engine.dispatch.ENTRYPOINTS``). These tests drive each one
for real, through the CLI, through ``--launch``, through the Lead broker's relay and through the typed Lead surface's
MCP transport (channel ``lead_mcp``, F15.1), and prove each reached the predicate: the invocation or run it created
records the decision that admitted it. A query (``aew dispatch explain``) equals the execution, and an ALLOW is never
reused once anything it depended on changed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from aewflow import (
    Role,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    plan_unit,
    sample_project,
    submit_record,
)
from conftest import run_aew
from fake_harness import AGENT, HarnessLab
from invariants import assert_control_invariants

from aew.engine.dispatch import ENTRYPOINTS
from aew.util import dump_yaml

# Each declared entrypoint and the test here that drives it (a new entrypoint without a case fails below).
COVERED = {
    "work.assign": "test_assign_and_invoke_for_a_mutating_ticket_record_their_decision",
    "invoke.create.mutating": "test_assign_and_invoke_for_a_mutating_ticket_record_their_decision",
    "work.dispatch": "test_non_mutating_dispatch_redispatch_and_review_record_their_decision",
    "work.redispatch": "test_non_mutating_dispatch_redispatch_and_review_record_their_decision",
    "invoke.create.non_mutating": "test_non_mutating_dispatch_redispatch_and_review_record_their_decision",
    "invoke.create.parent": "test_parent_acceptance_invocations_record_their_decision",
    "harness.launch": "test_launch_relaunch_and_dispatch_launch_record_their_decision",
    "dispatch.launch": "test_launch_relaunch_and_dispatch_launch_record_their_decision",
    "lead_broker.relay": "test_a_lead_session_dispatch_is_relayed_to_the_same_predicate",
    "integrate.prepare": "test_an_integration_lease_records_the_decision_that_granted_it",
}


def inv(p, inv_id):
    return p.ok("invoke", "show", inv_id)


def admitted(p, inv_id, entrypoint, channel="cli"):
    record = inv(p, inv_id)["dispatch"]
    assert record["entrypoint"] == entrypoint and record["channel"] == channel, record
    assert record["decision"].startswith("sha256:") and record["revision"] < p.rev()
    return record


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_assign_and_invoke_for_a_mutating_ticket_record_their_decision(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    out = p.lead("work", "assign", wid)
    admitted(p, out["invocation"], "work.assign")
    assert out["dispatch"]["allowed"] and out["dispatch"]["entrypoint"] == "work.assign"
    p.lead("work", "transition", wid, "--to", "RUNNING")
    p.lead("invoke", "cancel", out["invocation"], "--reason", "a fresh implementer")
    again = p.lead("invoke", "create", wid, "--role", "implementer")
    admitted(p, again["invocation"], "invoke.create.mutating")
    assert_control_invariants(p)


def test_an_integration_lease_records_the_decision_that_granted_it(tmp_path):
    """M4-D: the lease's custody invocation is admitted by the ``integrate.prepare`` decision of its own grant, and
    the query equals the execution."""
    from aewflow import to_commit_ready

    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    explained = p.ok("dispatch", "explain", wid, "--entrypoint", "integrate.prepare")
    assert explained["allowed"] and explained["entrypoint"] == "integrate.prepare"
    out = p.lead("integrate", "prepare", wid)
    custodian = out["queue"]["custodian"]
    assert custodian.startswith("IA-")
    record = admitted(p, custodian, "integrate.prepare")
    assert record["revision"] == explained["revision"]  # decided against the revision the query saw
    assert_control_invariants(p)


def test_non_mutating_dispatch_redispatch_and_review_record_their_decision(tmp_path):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", wid, "--review", "code_reviewer")  # a planned review
    _, out = dispatch(p, wid)
    admitted(p, out["invocation"], "work.dispatch")
    again = p.lead("work", "redispatch", wid, "--reason", "start over")
    admitted(p, again["invocation"], "work.redispatch")
    role = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    rv = p.lead("invoke", "create", wid, "--card", "code_reviewer")
    admitted(p, rv["invocation"], "invoke.create.non_mutating")
    assert_control_invariants(p)


def test_parent_acceptance_invocations_record_their_decision(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Understand calc", cls=1)
    plan_unit(p, tmp_path, story, "Investigate, then decide.\n")
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    out = p.lead("invoke", "create", story, "--role", "reviewer")
    admitted(p, out["invocation"], "invoke.create.parent")
    assert_control_invariants(p)


def test_launch_relaunch_and_dispatch_launch_record_their_decision(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "aew", "args": ["whoami"]}])
    out = lab.lead("work", "assign", wid, "--launch")
    run1 = lab.project.ok("invoke", "show", out["invocation"])["runs"][0]
    assert run1["dispatch"]["entrypoint"] == "dispatch.launch" and run1["dispatch"]["covered_by"] == "work.assign"
    lab.wait(run1["run"])
    relaunched = lab.lead("harness", "launch", out["invocation"])
    run2 = lab.project.ok("invoke", "show", out["invocation"])["runs"][-1]
    assert run2["run"] == relaunched["run"] and run2["dispatch"]["entrypoint"] == "harness.launch"
    lab.wait(run2["run"])
    assert_control_invariants(lab.project)


def test_a_lead_session_dispatch_is_relayed_to_the_same_predicate(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "aew", "args": ["whoami"]}])
    script = tmp_path / "lead.json"
    script.write_text(json.dumps([{"do": "lead", "args": ["work", "assign", wid, "--launch"]}]), encoding="utf-8")
    transcript = tmp_path / "lead.jsonl"
    res = run_aew("-C", str(lab.root), "lead", "session", "--", sys.executable, str(AGENT), "--script", str(script),
                  "--transcript", str(transcript), env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token}, timeout=600)
    assert res.returncode == 0, res.stderr
    inv_id = lab.project.ok("work", "show", wid)["control"]["implementer_invocation"]
    admitted(lab.project, inv_id, "work.assign", channel="lead_broker")
    lab.wait(lab.project.ok("invoke", "show", inv_id)["runs"][0]["run"])


def test_a_typed_surface_dispatch_is_carried_by_lead_mcp_and_waited_on_through_it(lab, tmp_path):
    """The `aew-lead` MCP server's recovery-profile cli escape dispatches through the same predicate; the channel
    records that the MCP transport carried it (provenance only); the run is then waited on through MCP."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "aew", "args": ["whoami"]}])
    probe = Path(__file__).resolve().parents[1] / "helpers" / "mcp_probe_agent.py"
    script, transcript = tmp_path / "mcp.json", tmp_path / "mcp.jsonl"
    script.write_text(json.dumps([
        {"rpc": "initialize", "params": {"protocolVersion": "2025-06-18"}}, {"notify": "notifications/initialized"},
        {"call": "status", "arguments": {}},
        {"call": "cli", "arguments": {"argv": ["work", "assign", wid, "--launch", "--expect-rev", "$revision_text"]}},
    ]), encoding="utf-8")
    res = run_aew("-C", str(lab.root), "lead", "session", "--", sys.executable, str(probe), "--script", str(script),
                  "--transcript", str(transcript), "--profile", "recovery",
                  env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token}, timeout=600)
    assert res.returncode == 0, res.stderr
    steps = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    assigned = steps[3]["reply"]["result"]["structuredContent"]
    assert assigned["ok"], assigned["stopped"]
    inv_id = lab.project.ok("work", "show", wid)["control"]["implementer_invocation"]
    record = admitted(lab.project, inv_id, "work.assign", channel="lead_mcp")
    run = lab.project.ok("invoke", "show", inv_id)["runs"][0]
    assert run["dispatch"]["channel"] == "lead_mcp" and run["dispatch"]["covered_by"] == "work.assign"
    # The decision is the same predicate's: explaining it now through the CLI names the same entrypoint.
    assert record["entrypoint"] == "work.assign"
    # Waiting on the run through MCP: one call until it ends.
    script.write_text(json.dumps([
        {"rpc": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"call": "harness_wait", "arguments": {"runs": [run["run"]], "timeout_s": 120}},
    ]), encoding="utf-8")
    res = run_aew("-C", str(lab.root), "lead", "session", "--", sys.executable, str(probe), "--script", str(script),
                  "--transcript", str(transcript), env={**lab.env, "AEW_LEAD_TOKEN": lab.project.token}, timeout=600)
    assert res.returncode == 0, res.stderr
    waited = json.loads(transcript.read_text(encoding="utf-8").splitlines()[1])["reply"]["result"]
    assert waited["structuredContent"]["ok"] and waited["structuredContent"]["result"]["timed_out"] is False
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------- query equals execution, never a cached ALLOW


def explain(p, *args):
    return p.ok("dispatch", "explain", *args, "--json")


def test_explain_equals_the_execution_when_allowed(tmp_path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    asked = explain(p, wid)
    out = p.lead("work", "assign", wid)
    assert asked["allowed"] and asked["entrypoint"] == "work.assign"
    done = {k: v for k, v in out["dispatch"].items()}
    assert {k: v for k, v in asked.items() if k not in {"ok", "channel"}} == done
    assert inv(p, out["invocation"])["dispatch"]["decision"] == out_digest(done)


def out_digest(decision):
    import hashlib

    body = json.dumps(decision, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def test_explain_equals_the_execution_when_refused(tmp_path):
    p = sample_project(tmp_path)
    t1 = create_planned_ticket(p, tmp_path)
    t2 = create_planned_ticket(p, tmp_path, title="Independent change")
    p.lead("work", "assign", t1)
    asked = explain(p, t2)
    res = p.aew("work", "assign", t2, "--token", p.token, "--expect-rev", str(p.rev()))
    assert not asked["allowed"] and asked["reason_codes"] == ["CONCURRENCY_LIMIT"]
    assert res.returncode == 5 and res.error["code"] == "CONCURRENCY_LIMIT"
    assert asked["blocking_conditions"][0]["message"] == res.error["message"]


def test_an_allow_is_never_reused_after_policy_changes(tmp_path):
    """A decision is computed at dispatch, never cached: a policy change after the query (no control revision
    moves) is seen by the dispatch itself."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    assert explain(p, wid)["allowed"]
    guardrails = p.root / ".aew/policy/guardrails.yaml"
    from aew.util import load_yaml
    policy = load_yaml(guardrails.read_text(encoding="utf-8"))
    policy["protected_paths"] = [*policy["protected_paths"], "tests/test_core.py"]
    guardrails.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    rev = p.rev()
    res = p.aew("work", "assign", wid, "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode == 5 and res.error["code"] == "DISPATCH_REFUSED"
    assert "PROTECTED_CONDITION_OVERLAP" in res.error["details"]["reason_codes"]
    assert p.rev() == rev  # nothing committed


def test_every_declared_entrypoint_has_a_conformance_case():
    assert set(COVERED) == set(ENTRYPOINTS), sorted(set(ENTRYPOINTS) ^ set(COVERED))
    for name, test in COVERED.items():
        assert callable(globals().get(test)), (name, test)
