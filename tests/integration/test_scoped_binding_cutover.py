"""E329's public removal and migration of a real in-flight stage journal."""

import pytest

from aew.engine import stage_intents
from aew.engine.api import Engine
from aew.engine.primitives import CONTROL_OP_SPECS
from aew.engine.store import Transition
from aew.surface import contract, stage
from aew.surface.context import SurfaceContext
from aew.surface.errors import AdapterInputError
from aew.surface.run import run_tool

OLD_DRAFT = "40a8459709d9776e3f250d5e451bcae39c231801c03a239c41feda6185ae460c"


def test_retired_revision_arguments_are_refused_at_each_public_boundary(project):
    e = Engine.discover(project.root)
    revision = project.rev()
    with pytest.raises(TypeError, match="expect_rev"):
        e.checkpoint(token=project.token, expect_rev=revision)
    with pytest.raises(AdapterInputError, match="arguments do not match") as exc:
        run_tool(e, SurfaceContext.outside_session(), "checkpoint", {"expect_rev": revision}, token=project.token)
    assert exc.value.code == "INVALID_ARGUMENTS"
    cli = project.aew("checkpoint", "--expect-rev", str(revision), env={"AEW_LEAD_TOKEN": project.token})
    assert cli.returncode == 2 and "--expect-rev" in cli.stderr
    assert project.rev() == revision


@pytest.mark.parametrize("known", [True, False], ids=["recognized", "unknown-contract"])
def test_migrating_hot_intents_preserves_committed_steps_and_refuses_unproved_plans(project, known):
    e = Engine.discover(project.root)
    t = contract.catalog(contract.ALL_SWITCHES)["ticket_draft"]
    args = {"title": "An observation", "risk_class": 0, "non_mutating": True,
            "plan": {"body": "Read the existing source.", "assurance": "none"}}
    transaction = stage.plan_for(e, t.name, args)
    sid = e.stage_open(token=project.token, tool=t.name, contract_digest=stage.contract_digest(t), arguments=args,
                       judgment_inputs=list(t.required_judgments), base_class=t.base_class,
                       effective_class=t.base_class, plan=transaction, subject=None, ingress="test")["intent"]
    # The old project committed the first step. The test transplants the predecessor's on-disk opening and hash.
    with stage_intents.step(sid, 1):
        unit = e.work_create(token=project.token, **transaction[0]["args"])["id"]
    with e.store.session() as session:
        old = session.state["stage_intents"][sid]
        old["contract_digest"] = OLD_DRAFT if known else "f" * 64
        old_revision = old["opened"]["rev"] - 1
        old["opened"]["expect_rev"] = old["arguments"]["expect_rev"] = old_revision
        old["arguments_digest"] = stage_intents.digest(old["arguments"])
        session.commit(Transition(op="test.fixture", actor={"kind": "test"}, summary="predecessor stage record"))

    preceding = e.stage_intent(sid)
    refused = stage.assess(e, preceding)
    assert not refused["safe_to_continue"] and "`aew migrate`" in refused["checks"]["contract"]["message"]
    upgraded = e.migrate(token=project.token)
    assert upgraded["stage_intents"] == {sid: known}
    migrated = e.stage_intent(sid)
    assert migrated["steps"] == preceding["steps"] and migrated["binding"] == preceding["binding"]
    assert migrated["arguments"] == args and migrated["arguments_digest"] == stage_intents.digest(args)
    assert migrated["opened"] == {k: v for k, v in preceding["opened"].items() if k != "expect_rev"}
    assert "stage_intents" not in e.migrate(token=project.token)
    assert e.store.current()["revision"] == upgraded["revision"]

    assessed = stage.assess(e, migrated)
    assert assessed["safe_to_continue"] == known
    before = project.rev()
    result = run_tool(e, SurfaceContext.outside_session(), "resolve",
                      {"subject": sid, "choice": "continue", "rationale": "The original plan is still wanted.",
                       "approval_digest": assessed["approval"]["digest"]}, token=project.token)
    if known:
        assert result["ok"] and result["result"]["status"] == stage_intents.COMPLETED
        assert [row["primitive"] for row in e.stage_intent(sid)["steps"]] == ["work.create", "plan.propose"]
        assert len(e.status(unit)["work_unit"]["plans"]) == 1
    else:
        assert not result["ok"] and project.rev() == before
        e.stage_abandon(token=project.token, intent=sid, rationale="The prior contract could not be proved.")
        assert e.stage_intent(sid)["steps"] == preceding["steps"]
    assert list(e.store.current()["work"]) == [unit]


def _record_unrelated_commit(e, *, peer="independent"):
    """Advance the shared journal while preserving the subject, including when no Lead currently holds the seat."""
    with e.store.session() as session:
        return session.commit(Transition(op="test.concurrent", actor={"kind": "test"}, summary=peer))


@pytest.mark.parametrize(("op", "variant"), [
    (op, spec.variant)
    for op, specs in CONTROL_OP_SPECS.items()
    for spec in specs if spec.revision_class == "A"
])
def test_an_unrelated_commit_never_stales_a_lead_mutation(project, tmp_path, op, variant):
    """The admission boundary on every A variant, with the four direct writers exercised through their own paths.

    The separately enumerated runtime handler coverage pins which operation enters each boundary. Each handler's
    domain rules remain covered by its workflow and the scoped comparisons have their own two-writer matrices.
    """
    e = Engine.discover(project.root)
    original = project.rev()
    if op == "lead.acquire":
        e.lead_release(token=project.token)
        intervening = _record_unrelated_commit(e)
        assert e.lead_acquire(session_label="second")["revision"] == intervening + 1
    elif op == "lead.handoff.accept":
        offered = e.lead_handoff_offer(token=project.token)
        intervening = _record_unrelated_commit(e)
        assert e.lead_handoff_accept(offer=offered["offer"], session_label="second")["revision"] == intervening + 1
    elif op == "message.record_lead":
        from test_coordination_store import world

        messaging = world(tmp_path / "messaging")
        intervening = _record_unrelated_commit(messaging.e)
        assert messaging.send()["revision"] == intervening
    elif op == "migrate":
        from test_migration import CP, migrate

        legacy = CP.Template(tmp_path / "migration")
        legacy.planned("One unstarted Ticket")
        intervening = _record_unrelated_commit(Engine.discover(legacy.root))
        result = migrate(legacy)
        assert result.json["migrated"] and result.json["revision"] == intervening + 1
    else:
        intervening = e.checkpoint(token=project.token, note="an independent project update")["revision"]
        with e.lead_txn(project.token, op) as ctx:
            assert ctx.session.revision == intervening > original
            assert ctx.actor["generation"] == 1
            ctx.summary = f"{op} {variant or ''} can enter the transaction at the current revision"
        assert e.store.current()["last_transition"]["op"] == op
        assert project.rev() == intervening + 1
