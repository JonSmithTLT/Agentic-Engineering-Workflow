"""ITEMS 55: a parent's gate that can never be satisfied blocks every descendant. It is refused at the write, found at
dispatch and in doctor, resume and status, and replaced on the record (designer decision 1 and addenda 1 to 4;
operator, option (b), 2026-11-01).

State from before the refusal existed is planted with one plain commit (``seed``): a Story whose mandatory gate is a
standard written in prose, as dogfood Story S-0001's was."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from aewflow import (
    assign,
    close_parent,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    implement,
    plan_unit,
    review,
    sample_project,
    verify,
)
from discovery import rules
from invariants import assert_control_invariants, load_control

from aew.engine import gate_ops
from aew.engine import gates as G
from aew.engine.api import Engine
from aew.engine.store import Transition
from aew.knowledge.manifest import DEFAULT_GATES
from aew.policy import validation as V
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.surface.validate import AdapterInputError

CTX = SurfaceContext.outside_session()
PROSE = "the targeted tests pass and the module stays under 300 lines"


def err(p, *args: str) -> dict[str, Any]:
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def seed(p, wid: str, gates: list[str]) -> None:
    """Plant ``wid``'s mandatory gates in control state, as a project written before this change holds them."""
    engine = Engine.discover(p.root)
    with engine.store.session() as s:
        s.state["work"][wid]["policy"] = {"mandatory_gates": list(gates), "min_descendant_class": None,
                                          "rationale": None}
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="a parent written before ITEMS 55"))


def resolve(p, subject: str, replacement: str | None, *, rev: int | None = None,
            rationale: str = "the targeted check is that standard, as a configured check") -> dict[str, Any]:
    arguments = {"expect_rev": p.rev() if rev is None else rev, "subject": subject, "choice": "replace_gate",
                 "rationale": rationale, **({"replacement": replacement} if replacement is not None else {})}
    return R.run_tool(Engine.discover(p.root), CTX, "resolve", arguments, token=p.token)


def refusal(out: dict[str, Any]) -> dict[str, Any]:
    assert not out["ok"] and out["stopped"], out
    return out["stopped"]["error"]


def projection(p, subject: str = "project") -> dict[str, Any]:
    return R.run_tool(Engine.discover(p.root), CTX, "status", {} if subject == "project" else
                      {"work_id": subject})["projection"]


def status_items(p, subject: str = "project") -> list[dict[str, Any]]:
    return [d for d in projection(p, subject)["decisions_required"] if d["decision"] == "REPLACE_GATE"]


def status_previews(p, subject: str = "project") -> list[dict[str, Any]]:
    return [b["details"] for b in projection(p, subject)["blockers"] if b["code"] == gate_ops.REASON]


def doctor(p) -> dict[str, Any]:
    """`aew doctor`'s gates check (doctor exits non-zero on any failure, so its JSON is read either way)."""
    return {c["check"]: c for c in json.loads(p.aew("doctor", "--json").stdout)["checks"]}["gates:satisfiable"]


def gates_of(p, wid: str) -> dict[str, Any]:
    return p.ok("gate", "show", wid)["gates"]


def no_command_findings(text: str) -> None:
    """Every `aew` command the text names parses with the live parser (discovery rule O-CMD)."""
    findings = [f for f in rules.check(rules.Output(site="items-55", text=text)) if f.rule == "O-CMD"]
    assert findings == [], findings


# ---------------------------------------------------------------------------------------------- the write


def test_work_create_refuses_a_gate_no_descendant_can_satisfy_and_accepts_every_kind(tmp_path):
    p = sample_project(tmp_path)
    for gate, why in [(PROSE, "AEW has no gate of that kind"), ("review_prose_standard", "specialty `prose_standard`"),
                      ("review_card:ghost", "no card `ghost`"), ("verify_card:ghost", "no card `ghost`"),
                      ("check:lint", "`lint` is not defined and configured")]:
        before = p.rev()
        out = err(p, "work", "create", "story", "--title", "Objective", "--class", "1", "--mandatory-gate", gate)
        assert out["code"] == "VALIDATION_FAILED" and out["details"]["gate"] == gate, out
        assert f"gate `{gate}` can never be satisfied: " in out["message"] and why in out["message"], out["message"]
        assert "`check:<check id>`" in out["message"] and "`--goal`, `--contract`" in out["message"]
        assert out["details"]["candidates"], out  # the kinds or the resolving names that exist
        no_command_findings(out["message"])
        assert p.rev() == before  # nothing written
    every = [*dict.fromkeys(g for t in G.UNIT_TYPES for g in G.FIXED[t]), "review_r1", "review_security",
             "review_card:security_reviewer", "verify_card:verifier", "check:unit", "check:guardrails"]
    story = create_unit(p, "story", "Every kind", extra=tuple(x for g in every for x in ("--mandatory-gate", g)))
    assert load_control(p.root)["work"][story]["policy"]["mandatory_gates"] == every
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- found


def test_doctor_resume_and_status_name_a_stuck_parent_its_owner_and_the_route(tmp_path):
    p = sample_project(tmp_path)
    clean = doctor(p)
    assert clean["status"] == "PASS" and status_items(p) == []
    story = create_unit(p, "story", "Objective")
    child = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    seed(p, story, [PROSE, "review_r1"])
    found = doctor(p)
    item = gate_ops.item_id(story, PROSE)
    assert found["status"] == "FAIL" and f"{story} sets mandatory gate `{PROSE}` (stuck: {child})" in found["detail"]
    assert f"settle `{item}` with the typed `resolve` tool: choice `replace_gate`" in found["detail"]
    assert "review_r1" not in found["detail"]  # it can be satisfied
    no_command_findings(found["detail"])
    assert any(a.startswith(f"{story}: mandatory gate `{PROSE}` can never be satisfied") and item in a
               for a in p.ok("resume", "--json")["next_actions"])
    [decision] = status_items(p)
    assert decision["arguments"] == {"expect_rev": p.rev(), "subject": item, "choice": "replace_gate"}
    assert decision["tool"] == "resolve" and decision["availability"] == "AVAILABLE" and decision["default"] == "NONE"
    [preview] = status_previews(p)
    assert (preview["id"], preview["stuck_units"], preview["replaceable"]) == (item, [child], True)
    assert [d["evidence"] for d in status_items(p, child)] == [[item]]  # the stuck unit's own status names it too


def test_dispatch_refuses_a_child_whose_inherited_gate_can_never_be_satisfied(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective")
    child = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    seed(p, story, [PROSE])
    before = p.rev()
    out = err(p, "work", "assign", child)
    assert out["code"] == "DISPATCH_REFUSED" and gate_ops.REASON in out["details"]["reason_codes"], out
    blockers = {b["code"]: b for b in out["details"]["blocking_conditions"]}
    stuck = blockers[gate_ops.REASON]
    assert stuck["details"]["items"] == [gate_ops.item_id(story, PROSE)] and stuck["details"]["owners"] == [story]
    assert f"{child} inherits gate `{PROSE}` from {story}, which can never be satisfied" in stuck["message"]
    assert "choice `replace_gate`" in stuck["message"]
    no_command_findings(stuck["message"])
    assert p.rev() == before
    explained = p.ok("dispatch", "explain", child, "--json")
    assert gate_ops.REASON in explained["reason_codes"] and not explained["allowed"]


# ---------------------------------------------------------------------------------------------- the replacement


def test_each_refusal_of_the_replacement_names_its_condition_and_changes_nothing(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective")
    seed(p, story, [PROSE, "review_r1"])
    stuck = gate_ops.item_id(story, PROSE)
    cases = [
        # condition 2: a gate that can be satisfied stays the operator's decision
        (gate_ops.item_id(story, "review_r1"), "check:unit", None, "OPERATOR_AUTHORIZATION_REQUIRED",
         "this route does not apply"),
        # the replacement fails the predicate
        (stuck, "review_prose_standard", None, "VALIDATION_FAILED", "specialty `prose_standard`"),
        # the old gate is not on that unit
        (gate_ops.item_id(story, "review_security"), "check:unit", None, "NOT_FOUND", "is not a mandatory gate of"),
        # replacing with a gate the unit already has would drop one
        (stuck, "review_r1", None, "OPERATOR_AUTHORIZATION_REQUIRED", "without a replacement"),
        # a stale revision
        (stuck, "check:unit", 0, "STALE_REVISION", "expected control revision 0"),
    ]
    for subject, replacement, rev, code, says in cases:
        before = load_control(p.root)
        out = resolve(p, subject, replacement, rev=rev)
        error = refusal(out) if out.get("stopped") else out["error"]
        assert error["code"] == code and says in (error["message"] + str(error.get("violations"))), (code, error)
        assert load_control(p.root)["revision"] == before["revision"]
        assert load_control(p.root)["work"][story]["policy"] == before["work"][story]["policy"]
    # condition 1: replace, never drop. A missing or blank replacement is refused by the adapter, before the engine.
    for replacement in (None, "  "):
        with pytest.raises(AdapterInputError) as refused:
            resolve(p, stuck, replacement)
        assert refused.value.code == "INVALID_ARGUMENTS" and refused.value.details["violations"] == [
            "replacement: required for choice replace_gate" if replacement is None else "replacement: blank"]
    assert not (p.root / ".aew" / "work" / story / "gate-corrections").exists()


def test_the_s0001_shape_end_to_end_only_the_replaced_gate_re_evaluates(tmp_path):
    """A Story with a prose gate; one child passed review, verification and every check and sits idle, refused
    COMMIT_READY; another child is running. The replacement names only the running child's invocation and how to
    re-dispatch it; afterwards the idle child's other gates keep their status and evidence, only the replaced gate
    re-evaluates, and the child reaches COMMIT_READY. The Story's record never changes (addendum 2)."""
    p = sample_project(tmp_path, gates={**DEFAULT_GATES, "mutating_concurrency": 2})
    story = create_unit(p, "story", "Objective")
    record = p.root / ".aew" / load_control(p.root)["work"][story]["record"]
    idle = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    impl = assign(p, idle)
    implement(impl)
    p.lead("work", "transition", idle, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", idle, "--evidence", review(p, idle))
    p.lead("work", "transition", idle, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", idle, "--evidence", verify(p, idle))
    running = create_planned_ticket(p, tmp_path, title="Add multiply()", extra=("--parent", story))
    assign(p, running)
    survey = create_investigation(p, tmp_path, parent=story, title="Survey")
    complete_investigation(p, survey)
    consumer = create_investigation(p, tmp_path, parent=story, title="Consumer",
                                    extra=("--depends-on", f"{survey}:evidence"))
    seed(p, story, [PROSE])
    state = load_control(p.root)
    record_bytes, record_sha = record.read_bytes(), state["work"][story]["record_sha256"]
    live = sorted(i for i, inv in state["invocations"].items() if inv["status"] == "active")
    assert [state["invocations"][i]["work_unit"] for i in live] == [running], live  # the idle child has none

    before = gates_of(p, idle)
    assert before[PROSE]["status"] == "MISSING" and "can never be satisfied" in before[PROSE]["detail"]
    others = {g: (r["status"], r.get("evidence")) for g, r in before.items() if g != PROSE}
    assert {s for s, _ in others.values()} == {"CURRENT"}, others
    assert err(p, "work", "transition", idle, "--to", "COMMIT_READY")["code"] == "GATE_UNSATISFIED"

    item = gate_ops.item_id(story, PROSE)
    [preview] = status_previews(p)  # what it would make stale, before it is committed (addendum 3)
    [stale] = preview["stale_invocations"]
    assert (stale["invocation"], stale["work_id"]) == (live[0], running)
    out = resolve(p, item, "check:unit")
    assert out["ok"], out
    result = out["result"]
    assert result["stale_invocations"] == [stale] and result["mandatory_gates"] == ["check:unit"]
    for command in stale["commands"]:
        no_command_findings(f"`{command}`")

    # condition 3: the record of it, immutable, and control state's policy points to it; the unit's record is unchanged
    state = load_control(p.root)
    policy = state["work"][story]["policy"]
    [pointer] = policy["corrections"]
    correction = yaml.safe_load((p.root / ".aew" / pointer["path"]).read_text(encoding="utf-8"))
    assert (correction["work_unit"], correction["replaced"], correction["with"]) == (story, PROSE, "check:unit")
    assert correction["reason"] == "the targeted check is that standard, as a configured check"
    assert correction["by"]["kind"] == "lead" and correction["expected_revision"] + 1 == correction["rev"]
    assert correction["stale_invocations"] == [stale] and policy["mandatory_gates"] == ["check:unit"]
    assert record.read_bytes() == record_bytes and state["work"][story]["record_sha256"] == record_sha

    # condition 4: only the replaced gate re-evaluates; every other gate keeps its status and its evidence
    after = gates_of(p, idle)
    assert PROSE not in after and after["check:unit"]["status"] == "CURRENT"
    assert {g: (r["status"], r.get("evidence")) for g, r in after.items() if g != "check:unit"} == others
    p.lead("work", "transition", idle, "--to", "COMMIT_READY")
    assert p.ok("work", "show", idle)["control"]["state"] == "COMMIT_READY"
    # no child's consumed input goes stale (addendum 3): the consumer's dispatch is admitted, its input current
    consumed = p.ok("dispatch", "explain", consumer, "--json")
    assert consumed["allowed"] and "INPUT_STALE" not in consumed["reason_codes"], consumed

    # addendum 3: the running child is re-dispatched, and its new pack shows the new gate and the correction
    inv = live[0]
    p.ok("invoke", "cancel", inv, "--reason", stale["fields"]["reason"], "--token", p.token,
         "--expect-rev", str(p.rev()))
    card = state["invocations"][inv]["card"]["id"]
    fresh = p.lead("invoke", "create", running, "--card", card)["invocation"]
    shown = p.aew("context", "show", fresh)
    assert shown.returncode == 0, shown.stderr
    pack = shown.stdout
    assert "check:unit" in pack and f"{story}'s gate `{PROSE}` was replaced by `check:unit`" in pack
    assert status_items(p) == [] and status_previews(p) == []
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- addendum 2


def test_a_storys_check_gate_binds_its_mutating_child_and_passes_through_its_non_mutating_one(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective", extra=("--mandatory-gate", "check:unit"))
    plan_unit(p, tmp_path, story)
    change = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    look = create_investigation(p, tmp_path, parent=story)
    assert "check:unit" in gates_of(p, change)
    shown = p.ok("gate", "show", look)
    assert "check:unit" not in shown["gates"]
    assert shown["obligations"]["pass_through"] == {"check:unit": G.CHANGE_ONLY_NOTE}
    complete_investigation(p, look)  # the non-mutating child completes: the check never had a subject on it
    assert p.ok("work", "show", look)["control"]["state"] == "DONE"
    assert_control_invariants(p)


def test_an_epics_change_only_gates_bind_its_tickets_and_never_wait_a_storys_own_closeout(tmp_path):
    """Addendum 2: the Story's own closeout does not wait on the Epic's `check:unit` or `post_integration_verifier`
    (addendum 2's pointer line); its mutating Tickets carry both, and `validation.obligation`, untouched, still
    requires the Ticket's integration verifier."""
    p = sample_project(tmp_path)
    epic = create_unit(p, "epic", "Initiative", extra=("--mandatory-gate", "check:unit",
                                                       "--mandatory-gate", "post_integration_verifier"))
    story = create_unit(p, "story", "Objective", parent=epic)
    plan_unit(p, tmp_path, story)
    change = create_planned_ticket(p, tmp_path, extra=("--parent", story))
    assert {"check:unit", "post_integration_verifier"} <= set(gates_of(p, change))
    obligation = V.obligation(load_control(p.root), change, DEFAULT_GATES)
    assert obligation["verifier_required"] and obligation["mode"] == V.VERIFIER
    # the Story closes on its other child
    p.lead("work", "transition", change, "--to", "CANCELLED", "--reason", "not needed for the closeout")
    look = create_investigation(p, tmp_path, parent=story)
    complete_investigation(p, look)
    shown = p.ok("gate", "show", story)
    assert set(shown["obligations"]["pass_through"]) == {"check:unit", "post_integration_verifier"}
    assert not {"check:unit", "post_integration_verifier"} & set(shown["gates"])
    close_parent(p, story)  # its reviewer and verifier are dispatched, and it closes
    assert p.ok("work", "show", story)["control"]["state"] == "DONE"
    assert_control_invariants(p)


def test_an_archived_parent_pins_its_correction_record(tmp_path):
    """The correction record is pinned as a disposition is: archival carries it into the parent's bundle, so a full
    history verification detects an altered one."""
    from aew.engine.archive_ops import pinned_records
    from aew.errors import IntegrityError

    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Objective")
    seed(p, story, [PROSE])
    assert resolve(p, gate_ops.item_id(story, PROSE), "check:unit")["ok"]
    [pointer] = load_control(p.root)["work"][story]["policy"]["corrections"]
    p.lead("work", "cancel", story, "--reason", "the objective moved elsewhere")
    engine = Engine.discover(p.root)
    entry = next(e for e in engine.archive.index(engine.store.current()).list(kind="unit") if e["id"] == story)
    raw = (p.root / ".aew" / entry["path"]).read_bytes()
    assert (pointer["path"], pointer["sha256"]) in pinned_records(entry, raw)
    assert engine.history_audit(full=True)["ok"]
    record = p.root / ".aew" / pointer["path"]
    record.write_bytes(record.read_bytes().replace(b"check:unit", b"check:lint"))
    with pytest.raises(IntegrityError) as exc:
        Engine.discover(p.root).history_audit(full=True)
    assert any(pointer["path"] in problem for problem in exc.value.details["audit"]["problems"])
