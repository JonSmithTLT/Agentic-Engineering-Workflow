"""Exercise shown approval bindings through the operator prompt and the Lead relay."""

from __future__ import annotations

import pytest
from aewflow import (
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    parent_verify,
    plan_unit,
    review,
    sample_project,
    submit_record,
    verify,
)

from aew.engine.api import Engine
from aew.surface import projection as P
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.util import load_yaml, safe_dump_yaml

OPS = ["work.cancel", "plan.reconfirm", "work.accept", "verify.classify", "waive", "work.close",
       "verify.classify.ticket", "input.acknowledge", "work.dispose.projection"]


def _call(engine, project, method, **args):
    wid = args["work_id"]
    if method == "work_acknowledge_input":
        [shown] = [row for row in engine.input_status(engine.store.current(), wid)
                   if row["id"] == args["evidence_id"]]
        argv = shown["acknowledgement_argv"]
    elif method in {"waive", "work_close"}:
        gates = engine.gate_show(wid)
        argv = (gates["gate_approval_argv"][args["gate"]] if method == "waive"
                else gates["closeout_approval_argv"])
    else:
        argv = engine.status(wid)["approval_subjects"][method.replace("_", ".")]["argv"]
    assert argv[-1] == args["binding"]
    return [args.get("classification", token) if token == "<CLASS>" else
            args.get("reason", "reviewed") if token == "<reason>" else token for token in argv]


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("caller", ["relay", "terminal"])
def test_a_shown_digest_lets_an_unchanged_subject_commit(project, tmp_path, monkeypatch, op, caller):
    if op in {"verify.classify", "work.accept", "work.close", "verify.classify.ticket"}:
        project = sample_project(tmp_path / "workflow")
    engine = Engine.discover(project.root)
    if op == "work.cancel":
        wid = create_unit(project, "story", "Parent", cls=0)
        plan_unit(project, tmp_path, wid)
        create_unit(project, "ticket", "Child", cls=0, parent=wid)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        out = _call(engine, project, "work_cancel", work_id=wid, reason="r", binding=binding)
    elif op == "plan.reconfirm":
        parent = create_unit(project, "story", "Parent", cls=0)
        plan_unit(project, tmp_path, parent)
        wid = create_unit(project, "ticket", "Child", parent=parent, cls=0)
        plan_unit(project, tmp_path, wid)
        plan_unit(project, tmp_path, parent, "Second plan", reason="Changed parent plan")
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        out = _call(engine, project, "plan_reconfirm", work_id=wid, reason="r", binding=binding)
    elif op == "work.accept":
        wid = create_investigation(project, tmp_path, cls=0)
        worker, _ = dispatch(project, wid)
        ev = submit_record(worker, "discovery_record")["evidence"]
        project.lead("evidence", "ingest", wid, "--evidence", ev)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        out = _call(engine, project, "work_accept", work_id=wid, binding=binding)
    elif op == "verify.classify":
        wid = create_unit(project, "story", "Parent", cls=1)
        plan_unit(project, tmp_path, wid)
        complete_investigation(project, create_investigation(project, tmp_path, parent=wid))
        ev = parent_verify(project, wid, result="fail")
        project.lead("verify", "ingest", wid, "--evidence", ev)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        out = _call(engine, project, "verify_classify", work_id=wid, classification="ENVIRONMENT_OR_EVIDENCE_BLOCKED",
                    reason="r", binding=binding)
    elif op == "waive":
        path = engine.aew_root / "policy/gates.yaml"
        policy = load_yaml(path.read_text(encoding="utf-8"))
        policy["waivable_gates"] = ["review_r1"]
        path.write_text(safe_dump_yaml(policy), encoding="utf-8", newline="\n")
        project.adopt_policy()
        wid = create_unit(project, "story", "Parent with a gate", cls=1)
        binding = engine.gate_show(wid)["gate_approval_digests"]["review_r1"]
        out = _call(engine, project, "waive", work_id=wid, gate="review_r1", reason="r", binding=binding)
    elif op == "verify.classify.ticket":
        wid = create_planned_ticket(project, tmp_path)
        implement(assign(project, wid))
        project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        project.lead("review", "ingest", wid, "--evidence", review(project, wid))
        project.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
        project.lead("verify", "ingest", wid, "--evidence", verify(project, wid, goal_result="fail"))
        binding = engine.status(wid)["approval_subjects"]["verify.classify"]["digest"]
        out = _call(engine, project, "verify_classify", work_id=wid, classification="ENVIRONMENT_OR_EVIDENCE_BLOCKED",
                    reason="r", binding=binding)
    elif op == "input.acknowledge":
        source = create_investigation(project, tmp_path, cls=0, title="Survey")
        evidence_id = complete_investigation(project, source)
        consumer = create_investigation(project, tmp_path, cls=0, title="Consumer",
                                        extra=("--depends-on", f"{source}:evidence"))
        [shown] = [i for i in engine.input_status(engine.store.current(), consumer) if i["id"] == evidence_id]
        binding = shown["approval_digest"]
        out = _call(engine, project, "work_acknowledge_input", work_id=consumer, evidence_id=evidence_id,
                    source=source, reason="r", binding=binding)
    elif op == "work.dispose.projection":
        from test_stages_request import seed_anomaly

        seed_anomaly(project, None)
        P.clear_cache()
        view = R.run_tool(Engine.discover(project.root), SurfaceContext.outside_session(), "status", {})["projection"]
        [d] = [d for d in view["decisions_required"] if d["decision"] == "DISPOSE_ANOMALY"]
        assert "approval_digest" in d["arguments"], d
        res = R.run_tool(Engine.discover(project.root), SurfaceContext.outside_session(), "resolve",
                         {**d["arguments"], "choice": "not_applicable", "rationale": "r"}, token=project.token)
        assert res["ok"], res
        return
    else:  # work.close
        wid = create_unit(project, "story", "Parent", cls=0)
        plan_unit(project, tmp_path, wid)
        complete_investigation(project, create_investigation(project, tmp_path, cls=0, parent=wid))
        binding = engine.gate_show(wid)["closeout_approval_digest"]
        out = _call(engine, project, "work_close", work_id=wid, reason="r", binding=binding)
    from aew import operator
    from aew.cli.main import main

    monkeypatch.setenv("AEW_LEAD_TOKEN", project.token)
    monkeypatch.setattr(operator, "has_terminal", lambda: caller == "terminal")
    prompts = []

    def confirm(prompt):
        prompts.append(prompt)
        return {"authorized_by": "operator-tty"}

    monkeypatch.setattr(operator, "authorize", confirm)
    rev = project.rev()
    if caller == "relay":
        from aew.errors import ApprovalSubjectChanged
        from aew.harness.lead_broker import run_cli

        stale = [*out[:-1], "0" * 64]
        with pytest.raises(ApprovalSubjectChanged):
            run_cli(engine, project.token, stale, str(project.root), "", channel="lead.cli")
        assert project.rev() == rev
        result = run_cli(engine, project.token, out, str(project.root), "", channel="lead.cli")
        assert result["result"]["ok"]
    else:
        assert main(["-C", str(project.root), *out[:-2]]) == 0
    assert project.rev() == rev + 1
    if caller == "terminal":
        assert len(prompts) == 1 and binding in prompts[0]
    else:
        assert not prompts
