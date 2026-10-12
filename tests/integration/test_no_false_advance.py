"""The seeded false-advance corpus (M4-E plan v3 §6 and §10: "no false advance in the seeded corpus"; §7: any false
advance is a release blocker).

A false advance is the typed surface treating a step as legal when its guard refuses it: the projection or `explain`
answering AVAILABLE (or auto-runnable) for a stage its own commit would refuse, or a stage committing a step past a
guard that refuses it, so a Ticket reaches a state its guard forbids.

Each case is a file in ``tests/corpus/false_advance/``: ``seed`` names a builder below, which makes the state on a
real project; ``stage`` and ``arguments`` are the call (``$work_id`` is the seeded Ticket, ``$stale`` a revision
behind the current one, ``$evidence`` the report a seed made); ``expect`` is the stage's composed availability now,
and where the call stops (its boundary, the steps that committed, the Ticket's state after it; a null boundary is a
call that completes). The projection never offers a case's stage as auto-runnable unless it is AVAILABLE, and a case
may say it is not (``auto_runnable: false``: an open high anomaly, which adds no guard). The corpus begins with E5a
(`ticket_draft`, `ticket_start`) and grows with each later slice, which seeds the cases its stages reach: E5b the
unmigrated guard (a non-mutating Ticket's own transition guard, which its request stage reaches), stale evidence,
pending disposition and high anomaly; E6a and E6b the moved head, the second move and the unusable envelope per
clause (E6b: a request under a revoked envelope; each clause and each unusable condition is
`test_integration_pic`'s, where the custodian, not a stage, would publish); E7 the stale confirmation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from aewflow import (
    assign,
    create_investigation,
    create_planned_ticket,
    dispatch,
    implement,
    review,
    sample_project,
)
from conftest import Project
from invariants import assert_control_invariants, load_control
from test_stage_runner import launching

from aew.engine import harness_ops
from aew.engine.api import Engine
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CORPUS = Path(__file__).resolve().parents[1] / "corpus" / "false_advance"
CASES = {doc["case"]: doc for doc in (yaml.safe_load(f.read_text(encoding="utf-8"))
                                      for f in sorted(CORPUS.glob("*.yaml")))}
CTX = SurfaceContext.outside_session()

Seed = Callable[[Path, pytest.MonkeyPatch], tuple[Project, str | None, list[Callable[[], None]]]]


def _ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Callable[[], None]]]:
    p = sample_project(tmp_path)
    return p, create_planned_ticket(p, tmp_path), []


def _proposed_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    p = sample_project(tmp_path)
    wid = p.lead("work", "create", "ticket", "--title", "Add subtract()", "--class", "1", "--scope", "calc/**")["id"]
    plan = tmp_path / "plan.md"
    plan.write_text("1. Add subtract.\n", encoding="utf-8")
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", "calc/core.py")
    return p, wid, []


def _cap_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    p = sample_project(tmp_path)
    first = create_planned_ticket(p, tmp_path, title="Hold the workspace")
    second = create_planned_ticket(p, tmp_path, title="Add subtract()")
    p.lead("work", "assign", first)  # holds the one mutating workspace (default `mutating_concurrency: 1`)
    return p, second, []


def _non_mutating_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    p = sample_project(tmp_path)
    return p, create_investigation(p, tmp_path), []


def _unadopted_policy_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    p, wid, done = _ready(tmp_path, monkeypatch)
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "mutating_concurrency: 2\n", encoding="utf-8")
    return p, wid, done


def _unlaunchable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    wid = create_planned_ticket(p, tmp_path)

    def no_process(*_: Any, **__: Any) -> Any:
        raise OSError("no process slot")

    monkeypatch.setattr(harness_ops.procs, "spawn_detached", no_process)
    return p, wid, [lab.cleanup]


def _held_by_intent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """A READY Ticket an unfinished stage holds: one whose executor died right after opening its intent."""
    p, wid, done = _ready(tmp_path, monkeypatch)
    e = Engine.discover(p.root)
    e.stage_open(token=p.token, expect_rev=int(e.store.read()["revision"]), tool="ticket_start",
                 contract_digest="0" * 64, arguments={"work_id": wid}, judgment_inputs=[], base_class="POLICY_RESOLVED",
                 effective_class="POLICY_RESOLVED", plan=[{"primitive": "checkpoint"}], subject=wid, ingress="test")
    return p, wid, done


def _empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    return sample_project(tmp_path), None, []


# ---- E5b's seeds: the request stages, a disposition pending, an open high anomaly
EVIDENCE: dict[str, str] = {}  # the report a seed made, by project root (`$evidence`)


def _non_mutating_running(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """A non-mutating Ticket under way: its transition out of RUNNING has a guard with no query form (the rule's
    named guard for its kind), so its request stage is never answered AVAILABLE."""
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    dispatch(p, wid)
    return p, wid, []


def _reviewed(p: Project, tmp_path: Path, **kw: Any) -> str:
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    EVIDENCE[str(p.root)] = review(p, wid, **kw)
    return wid


def _stale_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """A review of a snapshot the workspace no longer holds (a file changed after it was reviewed)."""
    p = sample_project(tmp_path)
    wid = _reviewed(p, tmp_path)
    workspace = Path(p.ok("work", "show", wid)["control"]["workspace"]["path"])
    (workspace / "calc" / "core.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8")
    return p, wid, []


def _disposition_pending(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """Policy marks minor findings `requires_disposition`, and the review reports one the Lead has not disposed of."""
    p = sample_project(tmp_path)
    gates = p.root / ".aew/policy/gates.yaml"
    gates.write_text(gates.read_text(encoding="utf-8") + "requires_disposition:\n  review_severities: [minor]\n",
                     encoding="utf-8", newline="\n")
    p.pin_policy()
    wid = _reviewed(p, tmp_path, findings=[{"id": "F1", "severity": "minor", "summary": "a nit", "required": False}])
    return p, wid, []


def _high_anomaly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """A READY Ticket with an open high anomaly about it (recorded as a signalled WORKSPACE_MUTATED is)."""
    from test_stages_request import seed_anomaly

    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", [{"do": "hang"}])
    wid = create_planned_ticket(p, tmp_path)
    seed_anomaly(p, wid)
    return p, wid, [lab.cleanup]


def _unusable_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Project, str | None, list[Any]]:
    """M4-E E6b: a VERIFY_PENDING Ticket of the sealed run whose publication envelope the operator has revoked. The
    Lead's PUBLISH_IF_CLEAN request is recorded and never advances the Ticket past COMMIT_READY by itself
    (`test_integration_pic` proves the custodian never publishes it either)."""
    from test_integration_pic import grant, principal
    from test_integration_stages import checks_mode, verifying

    p = sample_project(tmp_path)
    checks_mode(p)
    granted = grant(p, tmp_path)
    wid, report = verifying(p, tmp_path)
    Engine.discover(p.root).publication_revoke(principal(), envelope_id=granted["envelope"])
    EVIDENCE[str(p.root)] = report
    return p, wid, []


SEEDS: dict[str, Seed] = {"ready": _ready, "proposed_plan": _proposed_plan, "cap_held": _cap_held,
                          "non_mutating_ready": _non_mutating_ready, "unadopted_policy_edit": _unadopted_policy_edit,
                          "unlaunchable": _unlaunchable, "held_by_intent": _held_by_intent, "empty": _empty,
                          "non_mutating_running": _non_mutating_running, "stale_review": _stale_review,
                          "disposition_pending": _disposition_pending, "high_anomaly": _high_anomaly,
                          "unusable_envelope": _unusable_envelope}


def test_the_corpus_is_well_formed():
    assert CASES, "the seeded corpus is empty"
    for name, case in CASES.items():
        assert set(case) == {"case", "slice", "description", "seed", "stage", "arguments", "expect"}, name
        assert case["seed"] in SEEDS, f"{name}: no seed {case['seed']}"
        assert {"availability", "boundary", "steps", "unit_state"} <= set(case["expect"]), name
        assert set(case["expect"]) <= {"availability", "reason_codes", "auto_runnable", "boundary", "steps",
                                       "unit_state"}, name


def _bind(value: Any, wid: str | None, rev: int, evidence: str | None = None) -> Any:
    if value == "$work_id":
        return wid
    if value == "$stale":
        return rev - 1
    if value == "$evidence":
        return evidence
    if isinstance(value, dict):
        return {k: _bind(v, wid, rev, evidence) for k, v in value.items()}
    return value


@pytest.mark.parametrize("name", sorted(CASES))
def test_no_false_advance(tmp_path, monkeypatch, name):
    case = CASES[name]
    expect = case["expect"]
    p, wid, cleanups = SEEDS[case["seed"]](tmp_path, monkeypatch)
    try:
        engine = Engine.discover(p.root)
        rev = int(engine.store.read()["revision"])
        held = set(engine.store.read().get("stage_intents") or {})  # a seed's own unfinished stage stays as it was
        arguments = {"expect_rev": rev, **_bind(case["arguments"], wid, rev, EVIDENCE.get(str(p.root)))}
        explain_args = {k: v for k, v in arguments.items() if k != "expect_rev"}
        explained = R.run_tool(engine, CTX, "explain", {"stage": case["stage"], "arguments": explain_args})
        assert explained["ok"], explained["stopped"]
        assert explained["result"]["availability"] == expect["availability"], explained["result"]
        if "reason_codes" in expect:
            assert explained["result"]["reason_codes"] == expect["reason_codes"]
        if wid is not None:  # the projection never offers it to a stage runner unless it is legal now
            projected = R.run_tool(engine, CTX, "status", {"work_id": wid})["projection"]["actions"]
            for action in projected:
                if action["action"] == case["stage"]:
                    assert action["availability"] == expect["availability"]
                    assert not action["auto_runnable"] or expect["availability"] == "AVAILABLE"
                    if "auto_runnable" in expect:
                        assert action["auto_runnable"] == expect["auto_runnable"]
        out = R.run_tool(Engine.discover(p.root), CTX, case["stage"], arguments, token=p.token)
        if expect["boundary"] is None:  # nothing refuses it: the Lead's explicit call runs (E5b: no anomaly guard)
            assert out["ok"], out["stopped"]
        else:
            assert not out["ok"] and out["stopped"]["boundary"] == expect["boundary"], out["stopped"]
        assert [s["primitive"] for s in out["completed_steps"]] == expect["steps"]
        state = load_control(p.root)
        subject = wid or (Engine.discover(p.root).stage_intent(out["stage_intent_id"])["subject"]["id"]
                          if expect["steps"] else None)  # the Ticket a draft created before it stopped
        if subject is not None:
            assert state["work"][subject]["state"] == expect["unit_state"]
        assert set(state.get("stage_intents") or {}) == held  # every stop it could record ended its intent
        assert_control_invariants(p)
    finally:
        for cleanup in cleanups:
            cleanup()
