"""Engine-only request IDs on the six create operations."""

import json
import shlex
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
from aew.engine.harness_ops import Harness
from aew.engine.request_ids import INDEX
from aew.errors import IdempotencyConflict, IllegalTransition, StaleAuthority, StaleRevision, UsageError
from aew.harness import runlog
from aew.harness.contract import REVISION


def _call(p, method, **kwargs):
    engine = Engine.discover(p.root)
    return getattr(engine, method)(token=p.token, expect_rev=engine.lead_show()["revision"], **kwargs)


def _replay(p, method, first, **kwargs):
    before = load_control(p.root)
    repeated = _call(p, method, **kwargs)
    assert load_control(p.root) == before
    assert repeated["revision"] == first["revision"]
    assert repeated["replayed"] is True
    return repeated


def _assert_invocation_replay(p, method, first, **kwargs):
    replay = _replay(p, method, first, **kwargs)
    info = replay["credential_replay"]
    assert info["status"] == "NOT_REPLAYABLE"
    assert info["rotate"].startswith(f"aew harness launch {first['invocation']} --expect-rev ")
    assert replay == first | {"replayed": True, "invocation_token": None, "credential_replay": info}
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
    assert _replay(project, "work_create", first, **args, request_id="same") == first | {"replayed": True}
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
    assert _replay(p, "plan_propose", proposed, **plan) == proposed | {"replayed": True}

    dispatch(p, t)
    promote = {"work_id": t, "to": "story", "title": "Larger scope", "reason": "Needed", "request_id": "same"}
    promoted = _call(p, "work_promote", **promote)
    replay = _replay(p, "work_promote", promoted, **promote)
    assert replay == promoted | {"replayed": True}


def test_archiving_prunes_only_receipts_for_the_archived_unit(project):
    args = {"kind": "epic", "title": "Request IDs", "risk_class": 1}
    first = _call(project, "work_create", **args, request_id="archive")
    other = _call(project, "work_create", **args, request_id="keep")
    _call(project, "work_cancel", work_id=first["id"], reason="archive this fixture")
    state = load_control(project.root)
    assert first["id"] not in state["work"]
    [receipt] = state[INDEX]["operations"]["work.create"].values()
    assert set(receipt) == {"arguments", "digest", "unit", "ref", "revision"}
    assert receipt["ref"] == receipt["unit"] == other["id"]
    assert len(receipt["digest"]) == 64 and all(len(v) == 12 for v in receipt["arguments"].values())
    assert _call(project, "work_create", **args, request_id="archive")["id"] != first["id"]


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
    before = load_control(p.root)["revision"]
    with pytest.raises(IllegalTransition, match="aew invoke cancel") as exc:
        _call(p, "invoke_create", work_id=t, card="code_reviewer")
    assert exc.value.details["holding"] == first["invocation"]
    assert load_control(p.root)["revision"] == before


def test_parent_invocation_replays_without_a_credential(tmp_path):
    p = sample_project(tmp_path)
    story = create_unit(p, "story", "Acceptance")
    plan_unit(p, tmp_path, story)
    complete_investigation(p, create_investigation(p, tmp_path, parent=story))
    args = {"work_id": story, "role": "verifier", "request_id": "verify"}
    first = _call(p, "invoke_create", **args)
    _assert_invocation_replay(p, "invoke_create", first, **args)
    before = load_control(p.root)
    assert before["invocations"][first["invocation"]]["status"] == "active"
    with pytest.raises(IllegalTransition, match="aew invoke cancel") as exc:
        _call(p, "invoke_create", work_id=story, role="verifier")
    assert exc.value.details["holding"] == first["invocation"]
    assert load_control(p.root) == before


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_harness_launch_replays_the_run_when_the_original_process_stops_after_commit(lab, tmp_path, monkeypatch):
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
    assert not replay["ok"] and replay["spawn"] == "unconfirmed"
    assert replay["supervisor_status"] in replay["next_action"]
    assert f"aew harness launch {inv}" in replay["recovery"] and "--replace" not in replay["recovery"]
    assert not runlog.run_dir(p.root / ".aew", run["run"]).exists()
    engine = Engine.discover(p.root)
    [pending] = engine.harness_status(inv)["runs"]
    assert pending["status"] == "unconfirmed" and pending["supervisor_pid"] is None
    original = runlog.possibly_live
    monkeypatch.setattr(runlog, "possibly_live", lambda status, at, **kw: original(status, at, grace_s=0))
    [expired] = engine.harness_status(inv)["runs"]
    command = expired["next_action"].split("`")[1]
    assert "--replace" not in command
    spawned = []
    monkeypatch.setattr(Harness, "_spawn_run",
                        lambda self, invocation, run, credential: spawned.append(bool(credential)) or {"run": run})
    for key, value in lab.env.items():
        monkeypatch.setenv(key, value)
    recovery = _follow_launch(p, command)
    assert recovery["run"] != run["run"] and spawned == [True]


def _follow_launch(p, command):
    command = shlex.split(command.replace(REVISION, str(p.rev())))
    assert command[:3] == ["aew", "harness", "launch"]
    assert command[4] == "--expect-rev"
    return Engine.discover(p.root).harness_launch(token=p.token, invocation=command[3],
                                                  expect_rev=int(command[5]), replace="--replace" in command)


def test_following_the_rotate_step_and_forwarding_a_launch_replay(lab, tmp_path, monkeypatch):
    p = lab.project
    for key, value in lab.env.items():
        monkeypatch.setenv(key, value)
    lab.script("default", [{"do": "exit", "code": 0}])
    t = create_planned_ticket(p, tmp_path)
    implement(assign(p, t))
    p.lead("work", "transition", t, "--to", "REVIEW_PENDING")
    manual = {"work_id": t, "role": "reviewer", "request_id": "manual"}
    first = _call(p, "invoke_create", **manual)
    replay = _replay(p, "invoke_create", first, **manual)
    command = shlex.split(replay["credential_replay"]["rotate"].replace(REVISION, str(p.rev())))
    assert command[:3] == ["aew", "harness", "launch"] and "--replace" not in command
    inv = first["invocation"]
    before = load_control(p.root)["invocations"][inv]["token_id"]
    rotated = lab.ok(*command[1:], env={"AEW_LEAD_TOKEN": p.token})
    assert rotated["run"] == load_control(p.root)["invocations"][inv]["runs"][-1]["run"]
    assert load_control(p.root)["invocations"][inv]["token_id"] != before

    spawned = []
    monkeypatch.setattr(Harness, "_spawn_run",
                        lambda self, invocation, run, credential: spawned.append((run, bool(credential)))
                        or {"run": run})

    launch = {"work_id": t, "card": "security_reviewer", "request_id": "launch", "launch": True}
    first = _call(p, "invoke_create", **launch)
    engine = Engine.discover(p.root)
    started = engine.launch_dispatched(first.copy())
    replay = _replay(p, "invoke_create", first, **launch)
    assert replay["credential_replay"] == {"status": "NOT_REPLAYABLE",
                                          "next_action": f"aew harness status {first['invocation']}"}
    assert "launch" not in replay and replay["invocation_token"] is None
    assert engine.launch_dispatched(replay) == replay
    assert spawned == [(started["launch"]["run"], True)]


@pytest.mark.parametrize("scope", ["observation", "arbitrary"])
def test_invoke_create_refuses_non_dispatch_scopes(project, scope):
    rev = project.rev()
    with pytest.raises(UsageError, match="ticket or integration"):
        _call(project, "invoke_create", work_id="T-0001", scope=scope)
    assert project.rev() == rev


def test_work_create_replays_scope_warnings(project):
    args = {"kind": "ticket", "title": "New source", "risk_class": 1, "scope_paths": ["not-yet-created/**"],
            "goal_backwards": ["the planned source exists"], "request_id": "scope-warning"}
    first = _call(project, "work_create", **args)
    assert first["warnings"] and "not-yet-created/**" in first["warnings"][0]
    assert _replay(project, "work_create", first, **args) == first | {"replayed": True}
