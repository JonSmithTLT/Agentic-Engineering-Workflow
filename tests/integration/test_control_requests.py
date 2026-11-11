"""Engine-only request IDs on the six create operations."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from aewflow import (
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    plan_unit,
    sample_project,
    submit_record,
)
from conftest import clean_env
from fake_harness import HarnessLab
from invariants import load_control

from aew.engine import faults
from aew.engine.api import Engine
from aew.engine.request_ids import INDEX
from aew.errors import IdempotencyConflict, StaleAuthority, StaleRevision, UsageError
from aew.harness import runlog


def _call(p, method, **kwargs):
    engine = Engine.discover(p.root)
    return getattr(engine, method)(token=p.token, expect_rev=engine.lead_show()["revision"], **kwargs)


def _replay(p, method, first, **kwargs):
    before = load_control(p.root)
    repeated = _call(p, method, **kwargs)
    assert load_control(p.root) == before
    assert repeated["revision"] == first["revision"]
    return repeated


def _assert_invocation_replay(p, method, first, **kwargs):
    replay = _replay(p, method, first, **kwargs)
    info = replay["credential_replay"]
    assert info["status"] == "NOT_REPLAYABLE"
    assert f"aew harness launch {first['invocation']} --replace" in info["rotate"]
    assert replay == first | {"invocation_token": None, "credential_replay": info}
    assert first["invocation_token"] not in repr(load_control(p.root)[INDEX])


def test_work_create_replays_under_current_revision_and_keys_are_pruned_at_generation_change(project):
    args = {"kind": "epic", "title": "Request IDs", "risk_class": 1}
    first_without_id = _call(project, "work_create", **args)
    second_without_id = _call(project, "work_create", **args)
    assert first_without_id["id"] != second_without_id["id"]
    assert INDEX not in load_control(project.root)
    with pytest.raises(UsageError, match="request_id"):
        _call(project, "work_create", **args, request_id="x" * 65)

    first = _call(project, "work_create", **args, request_id="same")
    _call(project, "work_create", **args)
    assert _replay(project, "work_create", first, **args, request_id="same") == first
    before = load_control(project.root)
    with pytest.raises(IdempotencyConflict) as exc:
        _call(project, "work_create", **(args | {"title": "Other", "risk_class": 99}), request_id="same")
    assert exc.value.details["fields"] == ["risk_class", "title"]
    with pytest.raises(StaleRevision):
        Engine.discover(project.root).work_create(token=project.token, expect_rev=first["revision"],
                                                  **args, request_id="same")
    assert load_control(project.root) == before

    _call(project, "lead_release")
    state = load_control(project.root)
    assert state[INDEX]["generation"] == state["lead"]["generation"]
    engine = Engine.discover(project.root)
    acquired = engine.lead_acquire(expect_rev=state["revision"])
    with pytest.raises(StaleAuthority):
        engine.work_create(token=project.token, expect_rev=acquired["revision"], **args, request_id="same")
    project.token = acquired["token"]
    assert INDEX not in load_control(project.root)
    new = _call(project, "work_create", **args, request_id="same")
    assert new["id"] != first["id"]
    assert load_control(project.root)[INDEX]["generation"] == acquired["generation"]


def test_plan_propose_and_work_promote_replay_the_committed_results(tmp_path):
    p = sample_project(tmp_path)
    t = create_investigation(p, tmp_path)
    plan = {"work_id": t, "body": "Plan a second investigation.", "reason": "New scope",
            "no_assurance": True, "request_id": "same"}
    proposed = _call(p, "plan_propose", **plan)
    assert _replay(p, "plan_propose", proposed, **plan) == proposed

    dispatch(p, t)
    promote = {"work_id": t, "to": "story", "title": "Larger scope", "reason": "Needed", "request_id": "same"}
    promoted = _call(p, "work_promote", **promote)
    assert _replay(p, "work_promote", promoted, **promote) == promoted


def test_ticket_invocation_replays_without_issuing_a_credential_or_resolving_changed_arguments(tmp_path):
    p = sample_project(tmp_path)
    t = create_planned_ticket(p, tmp_path)
    implement(assign(p, t))
    p.lead("work", "transition", t, "--to", "REVIEW_PENDING")
    args = {"work_id": t, "role": "reviewer", "request_id": "review"}
    first = _call(p, "invoke_create", **args)
    _assert_invocation_replay(p, "invoke_create", first, **args)
    with pytest.raises(IdempotencyConflict) as exc:
        _call(p, "invoke_create", **(args | {"work_id": "T-9999"}))
    assert exc.value.details["fields"] == ["work_id"]


def test_nonmutating_redispatch_and_invocation_replay_without_credentials(tmp_path):
    p = sample_project(tmp_path)
    t = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", t, "--review", "code_reviewer")
    dispatch(p, t)
    args = {"work_id": t, "reason": "Start over", "request_id": "try-again"}
    again = _call(p, "work_redispatch", **args)
    _assert_invocation_replay(p, "work_redispatch", again, **args)
    role = Role(p, again["invocation_token"], Path(again["observation"]["path"]))
    p.lead("evidence", "ingest", t, "--evidence", submit_record(role, "discovery_record")["evidence"])
    p.lead("work", "transition", t, "--to", "REVIEW_PENDING")
    review = {"work_id": t, "card": "code_reviewer", "request_id": "review"}
    first = _call(p, "invoke_create", **review)
    _assert_invocation_replay(p, "invoke_create", first, **review)


def test_parent_invocation_replays_without_a_credential(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Acceptance")
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    args = {"work_id": story, "role": "verifier", "request_id": "verify"}
    first = _call(p, "invoke_create", **args)
    _assert_invocation_replay(p, "invoke_create", first, **args)


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_harness_launch_replays_the_run_when_the_original_process_stops_after_commit(lab, tmp_path):
    p = lab.project
    t = create_planned_ticket(p, tmp_path)
    assigned = lab.lead("work", "assign", t)
    inv = assigned["invocation"]
    args = {"invocation": inv, "request_id": "launch"}
    launcher = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from aew.engine.api import Engine\n"
        "Engine.discover(Path.cwd()).harness_launch(**json.load(sys.stdin))\n"
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    crashed = subprocess.run(
        [sys.executable, "-B", "-c", launcher], cwd=p.root,
        input=json.dumps({"token": p.token, "expect_rev": p.rev(), **args}), text=True, capture_output=True,
        timeout=60, creationflags=flags, start_new_session=sys.platform != "win32",
        env=clean_env({**lab.env, "AEW_FAULT": "harness.launch.after_commit", "AEW_FAULT_MODE": "exit"}),
    )
    assert crashed.returncode == faults.CRASH_EXIT_CODE, crashed.stderr
    state = load_control(p.root)
    [run] = state["invocations"][inv]["runs"]
    replay = _replay(p, "harness_launch", state, **args)
    assert replay["run_record"] == {key: value for key, value in run.items() if key != "token_id"}
    assert replay["run"] == run["run"]
    assert replay["supervisor_status"] == f"aew harness status {inv}"
    assert not runlog.run_dir(p.root / ".aew", run["run"]).exists()
