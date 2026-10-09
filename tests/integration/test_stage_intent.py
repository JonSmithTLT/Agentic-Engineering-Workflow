"""The StageIntent journal in the engine (M4-E E3a; plan v3 E3 and §2.7; typed surface design §3.4).

A stage's steps are real primitives here (``checkpoint``, ``work.transition``-free: every step below is a Lead
checkpoint, one transaction each), driven the way the surface's executor drives them (E3b): the intent opens by CAS,
then each primitive runs with its step armed (``stage_intents.step``) and commits with it, or not at all."""

from __future__ import annotations

import hashlib

import pytest
import yaml
from aewflow import create_planned_ticket, sample_project
from invariants import assert_control_invariants, load_control

from aew.engine import primitives as P
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.errors import IllegalTransition, IntegrityError, NotFound, StaleAuthority, StalePolicy, StaleRevision

ZERO = "0" * 64


@pytest.fixture
def project(tmp_path):
    return sample_project(tmp_path)


def engine(p) -> Engine:
    return Engine.discover(p.root)


def open_stage(p, *, steps: int = 2, subject: str | None = None, primitive: str = "checkpoint",
               token: str | None = None, expect_rev: int | None = None) -> str:
    out = engine(p).stage_open(token=token or p.token, expect_rev=p.rev() if expect_rev is None else expect_rev,
                               tool="probe", contract_digest=ZERO, arguments={"why": "a test"}, judgment_inputs=[],
                               base_class="MECHANICAL", effective_class="MECHANICAL",
                               plan=[{"primitive": primitive}] * steps, subject=subject, ingress="test")
    return out["intent"]


def run_step(p, intent: str, n: int, *, final: bool = False, token: str | None = None) -> dict:
    with SI.step(intent, n, final=final):
        return engine(p).checkpoint(token=token or p.token, expect_rev=p.rev(), note=f"{intent} step {n}",
                                    next_action=f"after {intent} step {n}")


def hot(p) -> dict:
    return load_control(p.root).get("stage_intents") or {}


def test_a_step_commits_with_its_primitive_and_a_finished_stage_leaves_the_hot_state(project):
    p = project
    opened = p.rev()
    si = open_stage(p)
    assert hot(p)[si]["status"] == "ACTIVE" and hot(p)[si]["opened"]["rev"] == opened + 1
    run_step(p, si, 1)
    assert [s["key"] for s in hot(p)[si]["steps"]] == [f"{si}:1"]
    run_step(p, si, 2, final=True)  # the last step's commit completes the stage: no extra revision
    assert si not in hot(p) and "stage_intents" not in load_control(p.root)
    record = engine(p).stage_intent(si)
    assert record["status"] == "COMPLETED" and record["closed"]["rev"] == opened + 3
    assert [s["revision"] for s in record["steps"]] == [opened + 2, opened + 3]
    assert (p.root / ".aew" / SI.RECORDS_DIR / f"{si}.yaml").is_file()  # no unit: the project's records
    assert si in load_control(p.root)["next_action"]  # the primitive's own effect committed with it
    assert_control_invariants(p)


def test_terminal_intents_leave_hot_state(project):
    """TIS-35: only unfinished intents are hot. Completed, stopped, refused and abandoned ones are cold, each read
    back whole."""
    p = project
    e = engine(p)
    done = open_stage(p, steps=1)
    run_step(p, done, 1, final=True)
    stopped = open_stage(p)
    run_step(p, stopped, 1)
    e.stage_stop(token=p.token, expect_rev=p.rev(), intent=stopped, n=2, boundary="first_refusal",
                 code="ILLEGAL_TRANSITION", message="refused")
    refused = open_stage(p)
    e.stage_stop(token=p.token, expect_rev=p.rev(), intent=refused, n=1, boundary="first_refusal",
                 code="ILLEGAL_TRANSITION", message="refused")
    abandoned = open_stage(p)
    e.stage_abandon(token=p.token, expect_rev=p.rev(), intent=abandoned, rationale="not needed after all")
    assert "stage_intents" not in load_control(p.root)
    assert [e.stage_intent(i)["status"] for i in (done, stopped, refused, abandoned)] == [
        "COMPLETED", "STOPPED_AT_BOUNDARY", "REFUSED", "ABANDONED"]
    assert e.stage_intent(abandoned)["resolution"]["choice"] == "abandon"
    assert_control_invariants(p)


def test_opening_is_a_cas_on_the_expected_revision(project):
    """§3.4 rules 1 and 2: a stale call opens nothing and changes nothing."""
    p = project
    before = load_control(p.root)
    with pytest.raises(StaleRevision):
        open_stage(p, expect_rev=p.rev() - 1)
    assert load_control(p.root) == before


def test_a_committed_step_never_commits_again(project):
    p = project
    si = open_stage(p)
    run_step(p, si, 1)
    rev = p.rev()
    with pytest.raises(IllegalTransition) as exc:
        run_step(p, si, 1)
    assert exc.value.details["reason"] == "step_already_committed" and p.rev() == rev
    with pytest.raises(IllegalTransition) as exc:
        run_step(p, si, 3)
    assert exc.value.details["reason"] == "step_out_of_order" and p.rev() == rev
    assert_control_invariants(p)


def test_a_primitive_that_commits_twice_is_not_one_step(project):
    p = project
    si = open_stage(p)
    with SI.step(si, 1):
        engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note="once")
        with pytest.raises(IllegalTransition) as exc:
            engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note="twice")
    assert exc.value.details["reason"] == "step_commits_twice"
    assert len(hot(p)[si]["steps"]) == 1


def test_a_legality_policy_change_between_steps_is_stale_policy(project):
    """§3.4 rule 6: the step is not committed; the intent stays unfinished for `resume`."""
    p = project
    si = open_stage(p)
    run_step(p, si, 1)
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "mutating_concurrency: 2\n", encoding="utf-8")
    p.adopt_policy()
    rev = p.rev()
    with pytest.raises(StalePolicy) as exc:
        run_step(p, si, 2)
    assert exc.value.code == "STALE_POLICY" and exc.value.details["intent"] == si and p.rev() == rev
    assert len(hot(p)[si]["steps"]) == 1
    assert_control_invariants(p)


def test_a_pending_policy_edit_refuses_every_step_until_it_is_adopted(project):
    """Plan v3 §2.5: an edit not yet adopted refuses every Lead commit (INTEGRITY_ERROR) before the journal judges
    the step, so the intent cannot even record its stop: it stays unfinished."""
    p = project
    si = open_stage(p)
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "mutating_concurrency: 2\n", encoding="utf-8")
    with pytest.raises(IntegrityError):
        run_step(p, si, 1)
    assert hot(p)[si]["steps"] == []


def test_an_operational_policy_change_is_recorded_never_enforced(project):
    """A price edit moves the operational digest only (F25: every price field is operational): the next step commits
    and records the digest it ran under."""
    p = project
    pricing = p.root / ".aew/policy/pricing.yaml"
    table = "schema: aew/pricing/v1\ncurrency: USD\nas_of: 2026-10-01\nsource: \"test\"\nprices:\n  p/m: {input: 1.0}\n"
    pricing.write_text(table, encoding="utf-8")
    manifest = p.root / ".aew/project.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    data["policy"]["pricing"] = "policy/pricing.yaml"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    p.adopt_policy()
    si = open_stage(p)
    run_step(p, si, 1)
    pricing.write_text(table.replace("1.0", "2.0"), encoding="utf-8")
    p.adopt_policy()
    run_step(p, si, 2, final=True)
    first, second = engine(p).stage_intent(si)["steps"]
    assert first["legality_digest"] == second["legality_digest"]
    assert first["operational_digest"] != second["operational_digest"]


def test_a_superseded_generations_stage_is_never_continued_implicitly(project):
    """F18 §14: after a takeover, the new Lead cannot run the old generation's next step; it resolves the stage."""
    import aew.operator

    p = project
    si = open_stage(p)
    run_step(p, si, 1)
    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        new = engine(p).lead_takeover(expect_rev=p.rev(), reason="the Lead's session was lost",
                                      session_label="operator")["token"]
    finally:
        aew.operator.authorize = original
    with pytest.raises(StaleAuthority):
        run_step(p, si, 2)  # the old credential is stale
    rev = p.rev()
    with pytest.raises(StaleAuthority) as exc:
        run_step(p, si, 2, token=new)  # the new Lead does not own the intent
    assert exc.value.details["reason"] == "not_owner" and p.rev() == rev
    with pytest.raises(StaleAuthority):  # nor record its stop: that is the owner's runner's bookkeeping
        engine(p).stage_stop(token=new, expect_rev=p.rev(), intent=si, n=2, boundary="first_refusal", code="X",
                             message="x")
    engine(p).stage_abandon(token=new, expect_rev=p.rev(), intent=si, rationale="the new Lead decides afresh")
    assert engine(p).stage_intent(si)["resolution"]["generation"] == 2


def test_a_unit_stage_ends_under_its_unit_and_travels_into_its_bundle(project, tmp_path):
    """§2.7: an ended stage on a unit is written under the unit, pointed to and pinned by it; archival carries the
    pointer into the bundle, whose pins and links name it."""
    from aew.engine.archive_ops import pinned_records

    p = project
    wid = create_planned_ticket(p, tmp_path)
    si = open_stage(p, subject=wid)
    with pytest.raises(IllegalTransition) as exc:
        open_stage(p, subject=wid)  # one unfinished stage per unit
    assert exc.value.details["reason"] == "open_intent"
    run_step(p, si, 1)
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=si, rationale="the plan changed")
    [pointer] = load_control(p.root)["work"][wid]["stage_intents"]
    assert pointer["path"] == f"work/{wid}/stage-intents/{si}.yaml" and pointer["status"] == "ABANDONED"
    p.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "not needed")
    e = engine(p)
    state = e._k.store.read()
    assert wid not in state["work"]
    bundle = e._archive.bundle(state, wid)
    assert bundle["unit"]["stage_intents"] == [pointer]
    entry = next(x for x in e._archive._index(state).units("CANCELLED") if x["id"] == wid)
    assert entry["links"]["stage_intents"] == [si]
    raw = (p.root / ".aew" / entry["path"]).read_bytes()
    assert (pointer["path"], pointer["sha256"]) in pinned_records(entry, raw)
    assert e.stage_intent(si)["status"] == "ABANDONED"
    assert_control_invariants(p)


def test_a_stage_whose_unit_was_archived_meanwhile_is_annotated_on_it(project, tmp_path):
    p = project
    wid = create_planned_ticket(p, tmp_path)
    si = open_stage(p, subject=wid)
    p.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "cancelled by a primitive meanwhile")
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=si, rationale="its unit is gone")
    e = engine(p)
    state = e._k.store.read()
    [note] = [a for a in e._archive._index(state).annotations(wid) if a["rel"] == "stage_intent"]
    assert note["links"] == {"stage_intent": [si]}
    record = yaml.safe_load((p.root / ".aew" / note["path"]).read_text(encoding="utf-8"))
    rel = f"work/{wid}/stage-intents/{si}.yaml"
    sha = hashlib.sha256((p.root / ".aew" / rel).read_bytes()).hexdigest()
    assert record["note"] == f"{rel} sha256:{sha}"  # the history pins the record the bundle could not
    assert e.stage_intent(si)["subject"]["id"] == wid
    assert_control_invariants(p)


def test_only_declared_primitives_are_planned(project):
    p = project
    with pytest.raises(IllegalTransition) as exc:
        open_stage(p, primitive="work.create")  # not declared until E5
    assert exc.value.details["reason"] == "undeclared_primitive" and "stage_intents" not in load_control(p.root)


def test_an_unknown_intent_is_not_found(project):
    p = project
    with pytest.raises(NotFound):
        engine(p).stage_intent("SI-9999")
    with pytest.raises(NotFound):
        engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent="SI-9999", rationale="x")


def test_a_step_commits_only_the_primitive_it_planned(project, tmp_path):
    """#140 review, finding 1: the journal checks the transaction that commits, not only the plan: an undeclared or
    judgment-bearing primitive never lands as a planned step."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    si = open_stage(p)
    rev = p.rev()
    with SI.step(si, 1), pytest.raises(IllegalTransition) as exc:
        engine(p).work_transition(token=p.token, expect_rev=p.rev(), work_id=wid, to="CANCELLED",
                                  reason="not the planned step")
    assert exc.value.details["reason"] == "step_primitive_mismatch" and p.rev() == rev
    assert load_control(p.root)["work"][wid]["state"] != "CANCELLED" and hot(p)[si]["steps"] == []


def test_a_judgment_bearing_step_is_never_committed_as_a_retry(project):
    """#140 review, finding 2 (§3.4 rules 4 and 5): only a non-judgment step of a non-judgment stage is retried after a
    stale revision; the engine refuses the rest, and records the retry it allows."""
    p = project
    judged = engine(p).stage_open(token=p.token, expect_rev=p.rev(), tool="probe", contract_digest=ZERO, arguments={},
                                  judgment_inputs=["why"], base_class="JUDGMENT_BEARING",
                                  effective_class="JUDGMENT_BEARING", plan=[{"primitive": "checkpoint"}],
                                  subject=None, ingress="test")["intent"]
    with SI.step(judged, 1, retried=True), pytest.raises(IllegalTransition) as exc:
        engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note="replayed judgment")
    assert exc.value.details["reason"] == "judgment_replay"
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=judged, rationale="a test")
    si = open_stage(p, steps=1)
    with SI.step(si, 1, retried=True, final=True):
        engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note="a mechanical retry")
    record = engine(p).stage_intent(si)
    assert record["retried_after_stale_revision"] and record["steps"][0]["retried_after_stale_revision"]
    assert_control_invariants(p)


@pytest.mark.parametrize("base, effective, primitive", [
    ("MECHANICAL", "MECHANICAL", "work.redispatch"),  # a judgment-bearing step in a stage said to be mechanical
    ("JUDGMENT_BEARING", "POLICY_RESOLVED", "checkpoint"),  # below the stage's own row
], ids=["below-a-step", "below-its-row"])
def test_a_stages_effective_class_is_never_understated(project, base, effective, primitive):
    """#140 review, finding 2: R5-1 gates on the effective class, so it is at least the row's and every step's."""
    p = project
    with pytest.raises(IllegalTransition) as exc:
        engine(p).stage_open(token=p.token, expect_rev=p.rev(), tool="probe", contract_digest=ZERO, arguments={},
                             judgment_inputs=[], base_class=base, effective_class=effective,
                             plan=[{"primitive": primitive}], subject=None, ingress="test")
    assert exc.value.details["reason"] == "class_understated" and "stage_intents" not in load_control(p.root)


def test_a_stop_names_the_step_it_stopped_at(project):
    """#140 review, finding 3 (§3.4 rule 3): the recorded boundary is the next step, or the last one when what followed
    its commit failed; never a step that does not exist."""
    p = project
    si = open_stage(p)
    run_step(p, si, 1)
    for n in (1, 3, 9):
        with pytest.raises(IllegalTransition) as exc:
            engine(p).stage_stop(token=p.token, expect_rev=p.rev(), intent=si, n=n, boundary="first_refusal",
                                 code="X", message="x")
        assert exc.value.details["reason"] == "stop_out_of_order"
    engine(p).stage_stop(token=p.token, expect_rev=p.rev(), intent=si, n=2, boundary="first_refusal", code="X",
                         message="x")
    assert engine(p).stage_intent(si)["stopped"]["n"] == 2
    done = open_stage(p, steps=1)
    run_step(p, done, 1)  # every step committed; its after-commit effect failed (a launch: rule 7)
    engine(p).stage_stop(token=p.token, expect_rev=p.rev(), intent=done, n=1, boundary="launch_failed", code="X",
                         message="the launch failed")
    assert engine(p).stage_intent(done)["status"] == "STOPPED_AT_BOUNDARY"
    assert_control_invariants(p)


def test_one_unfinished_stage_without_a_unit(project):
    """#140 review, finding 6 (§2.7): hot intents are bounded by live work; with no unit, one at a time."""
    p = project
    open_stage(p)
    with pytest.raises(IllegalTransition) as exc:
        open_stage(p)
    assert exc.value.details["reason"] == "open_intent"


@pytest.mark.parametrize("primitive", sorted(P.NOT_STEPS))
def test_a_primitive_that_is_not_one_commit_is_refused_at_opening(project, primitive):
    """#140 re-reviews: a stage step is one primitive in one Lead transaction whose op says which primitive committed.
    A primitive that commits twice, or shares its op, is refused when the stage opens, with its reason."""
    p = project
    with pytest.raises(IllegalTransition) as exc:
        open_stage(p, steps=1, primitive=primitive)
    assert exc.value.details["reason"] == "not_a_step" and P.NOT_STEPS[primitive] in exc.value.message
    assert "stage_intents" not in load_control(p.root)


def test_a_record_pinned_by_its_unit_is_never_shadowed_by_an_unpinned_copy(project, tmp_path):
    """#140 review, finding 5: a copy placed in records/ (the home of a stage with no unit, which no hash pins) never
    shadows the record a unit's pointer pins by hash."""
    p = project
    wid = create_planned_ticket(p, tmp_path)
    si = open_stage(p, subject=wid)
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=si, rationale="the genuine record")
    forged = p.root / ".aew" / SI.RECORDS_DIR / f"{si}.yaml"
    forged.parent.mkdir(parents=True, exist_ok=True)
    genuine = (p.root / ".aew" / f"work/{wid}/stage-intents/{si}.yaml").read_text(encoding="utf-8")
    forged.write_text(genuine.replace("the genuine record", "a forged record"), encoding="utf-8")
    assert engine(p).stage_intent(si)["resolution"]["rationale"] == "the genuine record"


def test_a_units_stage_record_must_be_pinned_by_its_pointer_or_annotation(project, tmp_path):
    """Invariant 49 refuses a unit's stage record that no pointer or annotation pins by its hash."""
    from invariants import control_violations

    p = project
    hot_wid = create_planned_ticket(p, tmp_path, title="Kept hot")
    kept = open_stage(p, subject=hot_wid)
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=kept, rationale="pinned by its pointer")
    gone_wid = create_planned_ticket(p, tmp_path, title="Archived first")
    noted = open_stage(p, subject=gone_wid)
    p.lead("work", "transition", gone_wid, "--to", "CANCELLED", "--reason", "archived before its stage ended")
    engine(p).stage_abandon(token=p.token, expect_rev=p.rev(), intent=noted, rationale="pinned by an annotation")
    assert_control_invariants(p)
    for wid, si in ((hot_wid, kept), (gone_wid, noted)):
        record = p.root / ".aew" / f"work/{wid}/stage-intents/{si}.yaml"
        original = record.read_bytes()
        record.write_bytes(original + b"# altered\n")
        assert any(f"{wid}" in v and si in v for v in control_violations(p.root)), si
        record.write_bytes(original)
    assert_control_invariants(p)
