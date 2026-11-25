"""Register E100 (the designer's decision of 2026-10-25): an explicit ``containment.mode: required`` on a host that
cannot meet it refuses the launch, on every platform, Windows included; an unset mode still runs weaker, and its
label's ``weaker_because`` names the platform. The platform is simulated (``sys.platform``, and ``supported``), so
both sides of it run on every CI platform. The refusals fail under ``containment.mode``'s old ``win32`` branch,
under which Windows ran weaker under an explicit ``required``; the unset mode's test fails under a ``mode`` that
requires containment where none exists."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from aew.engine.evidence_ops import EvidenceCommands
from aew.errors import ContainmentUnavailable
from aew.harness import containment as C
from aew.harness import lead_broker, supervisor
from aew.harness import weaker_register as W
from aew.harness.containment import netns
from aew.policy import checks

REQUIRED = {"containment": {"mode": "required"}}
# The platforms with no containment: Windows (E100's case) and another POSIX one (the M4-B review's)
UNCONTAINED = ["win32", "darwin"]


@pytest.fixture
def platform(request, monkeypatch) -> str:
    monkeypatch.setattr(C, "supported", lambda: False)
    monkeypatch.setattr(C.sys, "platform", request.param)
    return request.param


def launch_args(tmp_path) -> dict[str, Any]:
    (tmp_path / "ws").mkdir(exist_ok=True)
    return dict(role="implementer", scope="ticket", workspace=str(tmp_path / "ws"), run_dir=tmp_path / "run",
                scratch=str(tmp_path / "run" / "scratch"), bridge_dir=None, project=str(tmp_path))


@pytest.mark.parametrize("platform", UNCONTAINED, indirect=True)
def test_an_explicit_required_mode_refuses_the_launch_on_every_platform_without_containment(platform, tmp_path):
    """The refusal is typed, says what was refused and why, names the platform, and names what works instead: run on
    Linux, or choose allow_weaker. ``aew doctor`` says the same (FAIL)."""
    assert C.mode(REQUIRED) == C.REQUIRED
    with pytest.raises(ContainmentUnavailable) as refused:
        C.establish(**launch_args(tmp_path), policy=REQUIRED)
    error = refused.value
    assert error.code == "CONTAINMENT_UNAVAILABLE"
    assert error.details == {"reason": C.UNSUPPORTED_PLATFORM, "platform": platform}
    assert error.message.startswith("the launch is refused: the execution policy requires containment")
    assert f"this platform ({platform}) has no filesystem containment" in error.message
    assert error.message.endswith(C.NO_CONTAINMENT_REMEDY)
    assert not (tmp_path / "run").exists(), "nothing of the run was made"
    status, detail = C.doctor(REQUIRED, "unsupported")
    assert status == "FAIL" and "harness launches are refused" in detail


@pytest.mark.parametrize("platform", UNCONTAINED, indirect=True)
def test_an_unset_mode_runs_weaker_and_its_label_names_the_platform(platform, tmp_path):
    """No sandbox, labelled ``workdir_separation_only``, with ``weaker_because`` naming the platform; so does an
    explicit ``allow_weaker``. ``aew doctor`` warns."""
    for policy in (None, {}, {"containment": {}}, {"containment": {"mode": "allow_weaker"}}):
        assert C.mode(policy) == C.ALLOW_WEAKER, policy
        layout, label = C.establish(**launch_args(tmp_path), policy=policy)
        assert layout is None and label["filesystem"] == C.WORKDIR_ONLY, policy
        assert f"this platform ({platform}) has no filesystem containment" in label["weaker_because"], policy
        assert C.weaker(label)
    assert C.doctor(None, "unsupported") == ("WARN", "unsupported")


@pytest.mark.parametrize("platform", UNCONTAINED, indirect=True)
def test_every_launch_route_refuses_an_explicit_required_off_linux_before_anything_starts(platform, tmp_path,
                                                                                          monkeypatch):
    """A worker run (the supervisor's ``contain_launch``), the operator's ``aew check run`` and both Lead routes
    (``aew lead session``, and ``aew opencode`` off Linux) are refused with the same reason, before any register entry,
    network, check process or credential read, and none leaves a run directory or a half-started run behind. A Lead
    refused here is not sent to ``aew opencode``, which is not contained here either."""
    entered: list[Any] = []
    monkeypatch.setattr(W, "enter_if_weaker", lambda *a, **k: entered.append(a))
    started: list[Any] = []
    monkeypatch.setattr(netns.RunNetwork, "start", lambda *a, **k: started.append(a))
    ran: list[Any] = []
    monkeypatch.setattr(checks, "run", lambda *a, **k: ran.append(a))
    monkeypatch.setattr(C, "retire_private_git", lambda run_dir: None)

    # A worker run: its supervisor's containment step, which every worker launch takes before its harness starts
    with pytest.raises(ContainmentUnavailable) as worker:
        supervisor.contain_launch(REQUIRED, SimpleNamespace(PROVIDER_RELAY=False, EGRESS=()), provider=None,
                                  provider_env=[], bridge=None, aew_root=tmp_path / ".aew", kind="worker_run",
                                  **launch_args(tmp_path))
    # The operator's own `aew check run`
    commands = object.__new__(EvidenceCommands)
    kernel = SimpleNamespace(execution_policy=lambda: (REQUIRED, None), aew_root=tmp_path / ".aew",
                             repo_root=tmp_path)
    monkeypatch.setattr(commands, "k", kernel, raising=False)
    with pytest.raises(ContainmentUnavailable) as check:
        commands._check_run_direct({"command": ["true"]}, tmp_path / "ws", {"role": "implementer", "scope": "ticket"})
    assert "Nothing ran" in check.value.message
    assert check.value.message.count(C.ALLOW_WEAKER_REMEDY) == 1, "its remedy is given once (review of #578, m1)"
    # Both Lead routes, at the refusal they make before any credential is read or any seat moves
    engine = SimpleNamespace(execution_policy=lambda: (REQUIRED, None))
    leads = []
    for kind in ("lead_session", "lead_opencode"):
        with pytest.raises(ContainmentUnavailable) as lead:
            lead_broker.WeakerLead(engine, ["harness"], kind=kind, who="aew").precheck()
        leads.append(lead.value)

    for error in (worker.value, check.value, *leads):
        assert error.details["reason"] == C.UNSUPPORTED_PLATFORM and error.details["platform"] == platform, error
        assert C.NO_CONTAINMENT_REMEDY in error.message and "instead" not in error.details, error
    assert entered == [] and started == [] and ran == []
    assert not (tmp_path / "run").exists() and not list((tmp_path / ".aew").rglob("check-*")), "no run left behind"
