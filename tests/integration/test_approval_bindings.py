"""A decision compares the same subject it showed, even at the current revision."""

from __future__ import annotations

from pathlib import Path

import pytest
from aewflow import (
    Role,
    complete_investigation,
    create_investigation,
    create_unit,
    dispatch,
    parent_verify,
    plan_unit,
    prepare_and_validate,
    sample_project,
    submit_record,
    to_commit_ready,
    verify,
)
from conftest import git

from aew import operator
from aew.engine.api import Engine
from aew.engine.approval import input_digest
from aew.engine.primitives import CONTROL_OP_SPECS
from aew.engine.store import Transition
from aew.errors import ApprovalSubjectChanged
from aew.util import load_yaml, safe_dump_yaml, sha256_bytes

C_OPS = sorted(name for name, specs in CONTROL_OP_SPECS.items()
               if any(spec.revision_class == "C" for spec in specs))
PENDING: set[str] = set()


def change_control(engine, change):
    """Model another committed writer where the regular command would also retire the subject."""
    with engine.store.session() as session:
        change(session.state)
        session.commit(Transition(op="test.subject_changed", actor={"kind": "test"}, summary="change reviewed subject"))


def control_bytes(project):
    return (project.root / ".aew/state/control.yaml").read_bytes()


@pytest.mark.parametrize("op", C_OPS)
def test_an_approval_never_pins_content_the_approver_was_not_shown(project, tmp_path, monkeypatch, op):
    if op in PENDING:
        pytest.fail(f"{op}: approval race case pending")

    if op in {"input.acknowledge", "integrate.publishing", "verify.classify", "work.accept", "work.close",
              "work.gate_replace"}:
        project = sample_project(tmp_path / "workflow")
    engine = Engine.discover(project.root)
    manifest = engine.aew_root / "project.yaml"
    if op == "manifest.adopt":
        manifest.write_bytes(manifest.read_bytes() + b"\n# reviewed\n")
        binding = engine.manifest_approval()
        manifest.write_bytes(manifest.read_bytes() + b"# changed after review\n")
        args = {"reason": "reviewed settings"}
    elif op in {"authority.accept", "authority.reject"}:
        candidate = next(c for c in engine.authority_list()["candidates"] if c["path"] == "README.md")
        binding = engine.authority_candidate(candidate["id"])["digest"]
        path = project.root / candidate["path"]
        path.write_bytes(path.read_bytes() + b"\nchanged after review\n")
        args = {"candidate_id": candidate["id"], "decided_by": "operator"}
        if op == "authority.accept":
            args["klass"] = "orientation"
    elif op == "plan.accept":
        wid = create_unit(project, "story", "Review a plan")
        args = {"work_id": wid, "revision": 1}
        proposal = engine.plan_propose(token=project.token, expect_rev=project.rev(), work_id=wid,
                                       body="The plan shown.", no_assurance=True)
        entry = engine.status(wid)["work_unit"]["plans"][0]
        binding = entry["sha256"]
        path = engine.aew_root / proposal["path"]
        path.write_bytes(path.read_bytes() + b"\nchanged after review\n")
    elif op in {"work.cancel", "work.close"}:
        wid = create_unit(project, "story", "Parent whose children change", cls=0)
        plan_unit(project, tmp_path, wid)
        if op == "work.cancel":
            create_unit(project, "ticket", "First child", cls=0, parent=wid)
            binding = engine.status(wid)["approval_subjects"][op]["digest"]
            create_unit(project, "ticket", "Child added after review", cls=0, parent=wid)
        else:
            complete_investigation(project, create_investigation(project, tmp_path, cls=0, parent=wid))
            binding = engine.gate_show(wid)["closeout_approval_digest"]
            child = create_investigation(project, tmp_path, cls=0, parent=wid, title="Child added after review")
            complete_investigation(project, child)
        args = {"work_id": wid, "reason": "Parent decision"}
    elif op == "lead.takeover":
        before_rev = project.rev()
        after_writer = []

        def change_generation(_prompt):
            change_control(engine, lambda state: state["lead"].update(generation=state["lead"]["generation"] + 1))
            after_writer.append(control_bytes(project))
            return {"authorized_by": "operator-tty"}

        monkeypatch.setattr(operator, "authorize", change_generation)
        with pytest.raises(ApprovalSubjectChanged) as failure:
            engine.lead_takeover(expect_rev=project.rev(), reason="Replace the holder shown")
        assert failure.value.details["op"] == op
        assert int(failure.value.details["current"]) == int(failure.value.details["expected"]) + 1
        assert project.rev() == before_rev + 1 and control_bytes(project) == after_writer[0]
        return
    elif op == "integrate.breaker_reset":
        binding = engine.integrate_breaker_status()["approval_digest"]
        from aew.engine.queue_ops import empty

        failure = {"at": "2026-01-01T00:00:00Z", "code": "FAILED", "run": "V-0001", "work": "T-0001"}
        change_control(engine, lambda state: state.setdefault("queue", empty()).update(
            validation_breaker={"failures": [failure], "open": None}))
        args = {"reason": "resume validation"}
    elif op == "integrate.publishing":
        wid, _ = to_commit_ready(project, tmp_path)
        prepare_and_validate(project, wid)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        git("commit", "--allow-empty", "-m", "new authoritative revision", cwd=project.root)
        rebuilt = engine.integrate_publish(token=project.token, expect_rev=project.rev(), work_id=wid)
        assert rebuilt["rebuilt"]
        project.lead("verify", "ingest", wid, "--evidence", verify(project, wid, scope="integration"))
        assert engine.status(wid)["approval_subjects"][op]["digest"] != binding
        args = {"work_id": wid, "candidate": binding}
    elif op == "plan.reconfirm":
        parent = create_unit(project, "story", "Parent", cls=0)
        plan_unit(project, tmp_path, parent)
        wid = create_unit(project, "ticket", "Child", parent=parent, cls=0)
        plan_unit(project, tmp_path, wid)
        plan_unit(project, tmp_path, parent, "Second plan", reason="Changed parent plan")
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        plan_unit(project, tmp_path, parent, "Third plan", reason="Changed again")
        args = {"work_id": wid, "reason": "reconfirm under reviewed ancestors"}
    elif op == "stage.continue":
        digest = "0" * 64
        plan = [{"primitive": "checkpoint"}] * 2
        intent = engine.stage_open(token=project.token, expect_rev=project.rev(), tool="probe",
                                   contract_digest=digest, arguments={}, judgment_inputs=[], base_class="MECHANICAL",
                                   effective_class="MECHANICAL", plan=plan, subject=None, ingress="test")["intent"]
        binding = engine.stage_recheck(intent, contract_digest=digest, plan=plan)["approval"]["digest"]
        from aew.engine.stage_intents import step

        with step(intent, 1, final=False):
            engine.checkpoint(token=project.token, expect_rev=project.rev(), note="completed another step")
        args = {"intent": intent, "contract_digest": digest, "plan": plan, "rationale": "continue reviewed steps"}
    elif op == "verify.classify":
        wid = create_unit(project, "story", "Parent", cls=1)
        plan_unit(project, tmp_path, wid)
        complete_investigation(project, create_investigation(project, tmp_path, parent=wid))
        ev = parent_verify(project, wid, result="fail")
        project.lead("verify", "ingest", wid, "--evidence", ev)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        change_control(engine, lambda state: next(r for r in state["work"][wid]["evidence"]
                                                   if r["id"] == ev).update(sha256="f" * 64))
        args = {"work_id": wid, "classification": "ENVIRONMENT_OR_EVIDENCE_BLOCKED", "reason": "reviewed failure"}
    elif op == "work.accept":
        wid = create_investigation(project, tmp_path, cls=0)
        worker, _ = dispatch(project, wid)
        ev = submit_record(worker, "discovery_record")["evidence"]
        project.lead("evidence", "ingest", wid, "--evidence", ev)
        binding = engine.status(wid)["approval_subjects"][op]["digest"]
        new_attempt = engine.work_redispatch(token=project.token, expect_rev=project.rev(), work_id=wid,
                                             reason="recheck the findings")
        worker = Role(project, new_attempt["invocation_token"], Path(new_attempt["observation"]["path"]))
        revised = submit_record(worker, "discovery_record")["evidence"]
        project.lead("evidence", "ingest", wid, "--evidence", revised)
        args = {"work_id": wid}
    elif op == "work.dispose":
        from test_stages_request import seed_anomaly

        anomaly = seed_anomaly(project, None)
        binding = engine.disposition_approval(anomaly)["digest"]
        change_control(engine, lambda state: state["anomalies"][anomaly].update(detail="new circumstances"))
        args = {"subject": anomaly, "choice": "not_applicable", "rationale": "reviewed anomaly"}
    elif op == "work.gate_replace":
        from test_unsatisfiable_gate import PROSE, seed

        wid = create_unit(project, "story", "Parent", cls=1)
        seed(project, wid, [PROSE])
        item = next(item for item in engine.gate_items(wid) if item["gate"] == PROSE)
        replacement = "check:unit"
        binding = item["approval_subjects"][replacement]["digest"]
        create_unit(project, "ticket", "New affected child", cls=1, parent=wid)
        args = {"subject": item["id"], "replacement": replacement, "rationale": "same standard"}
    elif op == "input.acknowledge":
        source = create_investigation(project, tmp_path, cls=0)
        evidence_id = complete_investigation(project, source)
        rec = engine.status(source)["work_unit"]["execution"]["record"]
        binding = input_digest(evidence_id, rec["sha256"], engine.authoritative_commit())
        git("commit", "--allow-empty", "-m", "new authoritative revision", cwd=project.root)
        wid = create_unit(project, "story", "Consumer", cls=0)
        args = {"work_id": wid, "source": source, "evidence_id": evidence_id, "reason": "reviewed input"}
    elif op == "waive":
        path = engine.aew_root / "policy/gates.yaml"
        policy = load_yaml(path.read_text(encoding="utf-8"))
        gate = "review_r1"
        policy["waivable_gates"] = [gate]
        path.write_text(safe_dump_yaml(policy), encoding="utf-8", newline="\n")
        project.adopt_policy()
        wid = create_unit(project, "story", "Parent with a gate", cls=1)
        binding = engine.gate_show(wid)["gate_approval_digests"][gate]
        git("commit", "--allow-empty", "-m", "new authoritative revision", cwd=project.root)
        args = {"work_id": wid, "gate": gate, "reason": "reviewed gate"}
    else:
        pytest.fail(f"{op}: add an approval race case")

    before = control_bytes(project)
    manifest_before = manifest.read_bytes()
    decisions = sorted((engine.aew_root / "decisions").glob("*.md"))
    rev = project.rev()
    methods = {"input.acknowledge": "work_acknowledge_input", "integrate.publishing": "integrate_publish"}
    method = methods.get(op, op.replace(".", "_"))
    operator_ops = {"authority.accept", "authority.reject", "manifest.adopt", "integrate.breaker_reset"}
    if op in operator_ops:
        args["authorization"] = {"authorized_by": "operator-tty"}
    if op != "integrate.publishing":
        args["binding"] = binding
    with pytest.raises(ApprovalSubjectChanged) as failure:
        getattr(engine, method)(token=project.token, expect_rev=rev, **args)
    assert failure.value.details["op"] == op
    assert failure.value.details["expected"] != failure.value.details["current"]
    assert project.rev() == rev and control_bytes(project) == before
    assert manifest.read_bytes() == manifest_before
    assert sorted((engine.aew_root / "decisions").glob("*.md")) == decisions


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_directory_authority_records_the_candidate_digest(project, action):
    engine = Engine.discover(project.root)
    candidate = next(c for c in engine.authority_list()["candidates"] if c["path"] == "docs/adr/")
    subject = engine.authority_candidate(candidate["id"])
    path = project.root / candidate["path"] / "changed.md"
    path.write_bytes(b"changed directory contents\n")
    assert engine.authority_candidate(candidate["id"]) == subject
    args = {"klass": "decisions"} if action == "accept" else {}
    out = project.as_operator(f"authority_{action}", candidate_id=candidate["id"], decided_by="operator",
                              binding=subject["digest"], **args)
    record = (engine.aew_root / "decisions" / f"{out['decision']}.md").read_text(encoding="utf-8")
    assert f"{candidate['path']}@record:{subject['digest']}" in record


def test_file_authority_subject_uses_exact_bytes(project):
    engine = Engine.discover(project.root)
    candidate = next(c for c in engine.authority_list()["candidates"] if c["path"] == "README.md")
    subject = engine.authority_candidate(candidate["id"])
    assert subject["digest"] == sha256_bytes((project.root / candidate["path"]).read_bytes())


@pytest.mark.parametrize("action", ["accept", "reject"])
def test_authority_prompts_for_the_operator_and_binds_the_directory_record(project, monkeypatch, action):
    from aew.cli.main import main

    engine = Engine.discover(project.root)
    candidate = next(c for c in engine.authority_list()["candidates"] if c["path"] == "docs/adr/")
    subject = engine.authority_candidate(candidate["id"])
    prompts = []

    def authorize(prompt):
        prompts.append(prompt)
        return {"authorized_by": "operator-tty"}

    monkeypatch.setattr(operator, "authorize", authorize)
    monkeypatch.setenv("AEW_LEAD_TOKEN", project.token)
    args = ["-C", str(project.root), "authority", action, candidate["id"], "--expect-rev", str(project.rev())]
    if action == "accept":
        args += ["--class", "decisions"]
    assert main(args) == 0
    assert len(prompts) == 1
    assert subject["path"] in prompts[0] and "directory" in prompts[0] and subject["digest"] in prompts[0]


def test_missing_directory_can_be_rejected_but_cannot_be_accepted(project):
    from aew.errors import IllegalTransition

    engine = Engine.discover(project.root)
    candidate = next(c for c in engine.authority_list()["candidates"] if c["path"] == "docs/adr/")
    subject = engine.authority_candidate(candidate["id"])
    path = project.root / candidate["path"]
    path.rename(path.with_name("adr-moved"))
    args = {"candidate_id": candidate["id"], "decided_by": "operator", "binding": subject["digest"]}
    rev = project.rev()
    with pytest.raises(IllegalTransition, match="docs/adr/ is no longer a directory"):
        project.as_operator("authority_accept", klass="decisions", **args)
    assert project.rev() == rev
    assert project.as_operator("authority_reject", **args)["ok"]


def test_manifest_adoption_distinguishes_missing_from_empty_policy(project):
    engine = Engine.discover(project.root)
    rel = engine.manifest["policy"]["execution"]
    path = engine.aew_root / rel
    path.unlink()
    binding = engine.manifest_approval()
    assert binding[rel] is None
    path.write_bytes(b"")
    rev = project.rev()
    with pytest.raises(ApprovalSubjectChanged) as refused:
        project.as_operator("manifest_adopt", reason="reviewed removal", binding=binding)
    assert refused.value.details["subject"] == rel
    assert refused.value.details["current"] == sha256_bytes(b"")
    assert project.rev() == rev
