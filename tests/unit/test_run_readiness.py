"""Whether a raise to Run would be accepted and could act, said before the operator raises it: `aew doctor`'s
`steering:run-ready` and `aew status`'s Run line name what is missing and each fix (a Lead in the seat, the notifier,
the deadlines, an endpoint that answers), the raise refuses a policy in which a profile routing can pick has no
deadline (the loop's own fail-closed rule, A1 §3.2) with a route the operator can follow from where it is shown, and
an unconfigured policy is said to be one, never a profile named `<none>`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from notifier import RUN_READY, adopt, raise_to, recorder

from aew import errors
from aew.engine import steering as S
from aew.engine.api import DOCTOR_PING_S, Engine
from aew.harness import contract as K
from aew.harness import operator_client

RUNNING = {"running": True, "pid": 1, "started_at": "2026-11-11T00:00:00Z", "guarantee": "dev"}
QUICKSTART = Path(__file__).resolve().parents[2] / "docs" / "guides" / "quickstart.md"


def live(monkeypatch: pytest.MonkeyPatch) -> None:
    """An endpoint whose process is running and which answers a ping."""
    monkeypatch.setattr(operator_client, "status", lambda aew_root: RUNNING)
    monkeypatch.setattr(operator_client, "ping", lambda aew_root, **kw: {"ok": True, "pid": 1, "guarantee": "dev"})


def run_ready(engine: Engine) -> dict[str, Any]:
    return next(c for c in engine.doctor_checks() if c["check"] == "steering:run-ready")


def profiles(project: Any, doc: dict[str, Any]) -> Engine:
    """Adopt ``doc``'s profiles and routing over the steering and notifier already adopted."""
    path = project.root / ".aew" / "policy" / "execution.yaml"
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    policy.update(doc)
    path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8", newline="\n")
    project.adopt_policy()
    return Engine.discover(project.root)


def test_doctor_and_status_say_what_run_lacks_and_each_fix_then_that_it_is_ready(project, tmp_path, monkeypatch):
    command, _ = recorder(tmp_path)
    engine = adopt(project, command=command, ready=False)
    check = run_ready(engine)
    assert check["status"] == "WARN", check
    assert "the execution policy is not configured" in check["detail"]
    assert "end the Lead session first" in check["detail"], "the fixture's Lead holds the seat"
    assert S.ENDPOINT_DOWN in check["detail"] and "the notifier cannot deliver" not in check["detail"]
    text = engine.render_status(engine.status())
    assert "  Run: not ready:" in text and f"    - {S.ENDPOINT_DOWN}" in text
    engine = adopt(project, command=command)
    live(monkeypatch)
    check = run_ready(engine)
    assert check["status"] == "PASS" and check["detail"].startswith("Run is ready: a Lead holds the seat"), check
    assert "  Run: ready" in engine.render_status(engine.status())


def test_status_says_when_run_is_in_force_and_cannot_act(project, tmp_path):
    command, _ = recorder(tmp_path)
    engine = adopt(project, command=command)
    raise_to(engine, "run")
    text = engine.render_status(engine.status())
    assert "Steering: effective run" in text
    assert "  Run: not ready (Run is in force, and cannot act):" in text and S.ENDPOINT_DOWN in text


def test_the_notifier_is_named_with_its_fix(project):
    engine = adopt(project)  # the template's desktop notifier, which no test may show (conftest)
    check = run_ready(engine)
    assert check["status"] == "WARN" and "the notifier cannot deliver" in check["detail"]
    assert "aew, notify, file" in check["detail"], "the headless notifier is named as the fix"
    # judged in doctor's environment, which may not be the endpoint's: it says so, and where the check that counts runs
    assert ("judged in this terminal's environment" in check["detail"]
            and "run `aew notify desktop --check` in the endpoint's terminal" in check["detail"]), check


def test_the_raise_to_run_refuses_a_policy_where_a_routable_profile_has_no_deadline(project, tmp_path):
    command, _ = recorder(tmp_path)
    engine = adopt(project, command=command, ready=False)
    with pytest.raises(errors.IllegalTransition) as refused:
        engine.steering_raise_preview("run")
    assert refused.value.details["reason"] == "no_hard_deadline"
    assert "the execution policy is not configured" in refused.value.message and "<none>" not in refused.value.message
    unbounded = {**RUN_READY, "profiles": {**RUN_READY["profiles"], "fast": {"model": "openai/gpt-fast"}},
                 "routing": {**RUN_READY["routing"], "archetypes": {"reviewer": "fast"}}}
    engine = profiles(project, unbounded)
    with pytest.raises(errors.IllegalTransition) as refused:
        engine.steering_raise_preview("run")
    assert refused.value.details["reason"] == "no_hard_deadline"
    assert "execution profile(s) fast set no deadline_s" in refused.value.message
    assert "aew manifest adopt" in refused.value.message, "the route to fix it"
    raise_to(engine, "walk")  # Walk starts no run on its own: no deadline is asked of it
    assert engine.steering_view()["effective"] == "walk"
    engine = profiles(project, RUN_READY)
    raise_to(engine, "run")
    assert engine.steering_view()["effective"] == "run"


def test_an_unconfigured_policy_is_said_to_be_one():
    said = S.deadline_problem({"configured": False})
    assert said is not None and said.startswith("the execution policy is not configured: no profile can be routed")
    assert "<none>" not in said
    assert S.deadline_problem(RUN_READY) is None


def test_the_no_deadline_route_is_followed_from_where_it_is_shown_to_an_accepted_raise(project, tmp_path):
    """The raise reaches the deadline only with a Lead in the seat, where `aew lead acquire` is refused, so its route
    starts with the Lead session ending and names the quickstart's section for a pinned edit. With the seat vacant,
    doctor names the commands, with the seat they hold and how it is given back. Followed: the operator acquires, edits,
    adopts and releases, the Lead starts again, and the raise is accepted."""
    command, _ = recorder(tmp_path)
    engine = adopt(project, command=command, ready=False)
    with pytest.raises(errors.IllegalTransition) as refused:
        engine.steering_raise_preview("run")
    said = refused.value.message
    assert refused.value.details["reason"] == "no_hard_deadline"
    assert "end the Lead session first" in said and "aew lead acquire" not in said, said
    assert f'"{S.PINNED_EDIT}"' in said and f"\n### {S.PINNED_EDIT}\n" in QUICKSTART.read_text(encoding="utf-8")
    assert "start the Lead again with `aew opencode --acquire` and raise to Run again" in said
    engine.lead_release(token=project.token, expect_rev=project.rev())  # the Lead session ends
    detail = run_ready(Engine.discover(project.root))["detail"]
    assert "aew lead acquire" in detail and K.HELD_SEAT in detail, detail
    # the section's commands, at the operator's terminal
    project.token = Engine.discover(project.root).lead_acquire(expect_rev=project.rev(), session_label="op")["token"]
    profiles(project, RUN_READY)  # the edit, adopted
    Engine.discover(project.root).lead_release(token=project.token, expect_rev=project.rev())
    # the Lead starts again (`aew opencode --acquire`), and the raise is asked again
    project.token = Engine.discover(project.root).lead_acquire(expect_rev=project.rev(), session_label="lead")["token"]
    engine = Engine.discover(project.root)
    raise_to(engine, "run")
    assert engine.steering_view()["effective"] == "run"


def test_doctor_and_status_never_say_run_is_ready_while_no_lead_holds_the_seat(project, tmp_path, monkeypatch):
    """The raise refuses first when no Lead holds the seat, and the steering loop runs in the Lead's session, so a
    vacant seat is what Run lacks, with the command that fills it."""
    command, _ = recorder(tmp_path)
    adopt(project, command=command)
    Engine.discover(project.root).lead_release(token=project.token, expect_rev=project.rev())
    engine = Engine.discover(project.root)
    live(monkeypatch)
    check = run_ready(engine)
    assert check["status"] == "WARN" and check["detail"] == f"Run is not ready: (1) {S.SEAT_VACANT}", check
    assert f"    - {S.SEAT_VACANT}" in engine.render_status(engine.status())
    with pytest.raises(errors.IllegalTransition, match="no Lead holds the seat"):
        engine.steering_raise_preview("run")


def test_doctor_pings_the_endpoint_as_each_run_activation_does(project, tmp_path, monkeypatch):
    """A live process that does not answer is no endpoint for Run, whose activations ping it before each action: doctor
    pings within its short bound and says so; status keeps the cheap read of the locator and process, and says that."""
    command, _ = recorder(tmp_path)
    engine = adopt(project, command=command)
    monkeypatch.setattr(operator_client, "status", lambda aew_root: RUNNING)
    asked = []

    def silent(aew_root: Any, *, timeout_s: float = operator_client.PING_TIMEOUT_S) -> dict[str, Any]:
        asked.append(timeout_s)
        raise errors.NotFound(f"the operator endpoint did not answer a ping within {timeout_s:g} s")

    monkeypatch.setattr(operator_client, "ping", silent)
    check = run_ready(engine)
    assert check["status"] == "WARN" and DOCTOR_PING_S in asked, check
    assert check["detail"] == ("Run is not ready: (1) " + S.endpoint_silent(
        f"the operator endpoint did not answer a ping within {DOCTOR_PING_S:g} s")), check
    asked.clear()
    text = engine.render_status(engine.status())
    assert "its process is alive, and `aew doctor` checks it answers" in text and asked == [], "status never pings"
