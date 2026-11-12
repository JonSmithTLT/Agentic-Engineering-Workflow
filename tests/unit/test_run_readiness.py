"""Whether a raise to Run would be accepted and could act, said before the operator raises it (the RUN readiness walk of
2026-11-11, findings 1 to 3 and 6): `aew doctor`'s `steering:run-ready` and `aew status`'s Run line name what is missing
and each fix, the raise refuses a policy in which a profile routing can pick has no deadline (the loop's own
fail-closed rule, A1 §3.2), and an unconfigured policy is said to be one, never a profile named `<none>`."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from notifier import RUN_READY, adopt, raise_to, recorder

from aew import errors
from aew.engine import steering as S
from aew.engine.api import Engine
from aew.harness import operator_client

RUNNING = {"running": True, "pid": 1, "started_at": "2026-11-11T00:00:00Z", "guarantee": "dev"}


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
    assert "the execution policy is not configured" in check["detail"] and "aew lead acquire" in check["detail"]
    assert S.ENDPOINT_DOWN in check["detail"] and "the notifier cannot deliver" not in check["detail"]
    text = engine.render_status(engine.status())
    assert "  Run: not ready:" in text and f"    - {S.ENDPOINT_DOWN}" in text
    engine = adopt(project, command=command)
    monkeypatch.setattr(operator_client, "status", lambda aew_root: RUNNING)
    check = run_ready(engine)
    assert check["status"] == "PASS" and check["detail"].startswith("Run is ready"), check
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
