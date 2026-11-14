"""A fresh revision cannot let a writer act on a value that another writer changed."""

import pytest
from aewflow import create_planned_ticket, create_unit, sample_project

from aew.engine.api import Engine
from aew.engine.primitives import CONTROL_OP_SPECS
from aew.engine.queue_ops import empty as empty_queue
from aew.engine.store import Transition
from aew.errors import ChangedSinceRead

B_OPS = sorted(op for op, specs in CONTROL_OP_SPECS.items()
               if any(spec.revision_class == "B" for spec in specs))


@pytest.mark.parametrize("op", B_OPS)
def test_a_changed_prior_value_refuses_without_a_commit(tmp_path, monkeypatch, request, op):
    project = sample_project(tmp_path)
    engine = Engine.discover(project.root)
    parent = create_unit(project, "story", "Parent", cls=0)
    wid = create_unit(project, "ticket", "Child", cls=0, parent=parent)
    method = op.replace(".", "_")
    args = {"work_id": wid}
    changed_by = None

    if op == "harness.launch":
        # A second writer launches the invocation without starting a real supervisor.
        from fake_harness import HarnessLab

        lab = HarnessLab.create(project, tmp_path)
        request.addfinalizer(lab.cleanup)
        for key, value in lab.env.items():
            monkeypatch.setenv(key, value)
        engine = Engine.discover(project.root)
        ticket = create_planned_ticket(project, tmp_path)
        dispatched = engine.work_assign(token=project.token, expect_rev=project.rev(), work_id=ticket)
        inv = dispatched["invocation"]
        prior, args = engine.harness_status(inv)["launch_argv"][-1], {"invocation": inv}
        monkeypatch.setattr(engine._harness, "_spawn_run", lambda _inv, run, _token: {"run": run})
        engine.harness_launch(token=project.token, expect_rev=project.rev(), invocation=inv, prior_value=prior)
    elif op == "steering.lower":
        prior, args = engine.steering_view()["override_record"], {"mode": "crawl"}
        monkeypatch.setattr(engine._steering, "policy_default", lambda: "crawl")
    else:
        prior = engine.prior_value(method, wid)

    if op != "harness.launch":
        changed_by = _change_prior(engine, op, wid, parent, args)
    revision = project.rev()
    path = engine.aew_root / "state/control.yaml"
    before = path.read_bytes()
    with pytest.raises(ChangedSinceRead) as refused:
        getattr(engine, method)(token=project.token, expect_rev=revision, prior_value=prior, **args)
    details = refused.value.details
    assert details["op"] == op and details["expected"] == prior and details["current"] != prior
    assert details["changed_by"] == (changed_by or f"control revision {revision}")
    assert project.rev() == revision and path.read_bytes() == before


def _change_prior(engine, op, wid, parent, args):
    changed_by = None
    with engine.store.session() as session:
        state = session.state
        unit = state["work"][wid]
        if op == "work.transition":
            unit["state"] = "READY"
            args["to"] = "ESCALATED"
        elif op == "work.move":
            unit["parent"] = None
            args.update(parent=parent, reason="restore parent")
        elif op == "work.promote":
            unit["parent"] = None
            args.update(to="story", title="Promoted", reason="broaden scope")
        elif op == "work.staff":
            unit.setdefault("role_plan", {"execute": [], "review": [], "verify": [], "forbidden": []})[
                "forbidden"].append({"card": "implementer", "selected_by": "lead", "pinned": True, "reason": "review"})
        elif op in {"integrate.defer", "integrate.requeue"}:
            # The ordinary enqueue path runs during sync. Keep the fixture eligible until the compare.
            unit.update(state="COMMIT_READY", mutating=True)
            state.setdefault("queue", empty_queue())
            args["reason"] = "schedule"
            # The operation observes the committed entry written by this writer.
            engine._integration.queue.sync(state)
        elif op == "steering.lower":
            changed_by = "SM-0099"
            state["steering"]["override"] = {"mode": "walk", "generation": state["lead"]["generation"],
                                            "record": changed_by, "rev": session.revision + 1, "by": "operator"}
        else:
            pytest.fail(f"{op}: add a two-writer case")
        session.commit(Transition(op="test.prior_moved", actor={"kind": "test"}, summary="change the prior value"))
    return changed_by
