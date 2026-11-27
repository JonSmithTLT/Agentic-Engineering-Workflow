"""Plan acceptance and publish are the operator's decisions, confirmed through the operator endpoint (the operator's
ruling of 2026-11-26, delivering part of register E350; ``aew.engine.operator_decisions``).

A Lead session's `plan accept` and publish (its broker's relay and its typed tools) are refused until the operator has
confirmed exactly that plan or candidate with `aew operator confirm`, through the endpoint's challenge, and go through
once with it. Nothing the Lead passes counts as the confirmation. The operator's own call at their own terminal is the
decision itself and needs nothing more."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aewflow import APPLY_PATCH, prepare_and_validate, sample_project, to_commit_ready
from conftest import git, run_aew
from invariants import assert_control_invariants, load_control
from notifier import Console
from operator_confirms import confirm, principal

from aew import errors
from aew.cli.main import build_parser
from aew.engine import dispatch, outbox
from aew.engine import operator_decisions as OD
from aew.engine.api import Engine
from aew.harness import lead_broker, operator_client, operator_endpoint, steering_loop
from aew.surface import run as R
from aew.surface.context import SurfaceContext
from aew.surface.errors import AdapterInputError
from aew.surface.validate import check_call

LEAD_CHANNELS = tuple(sorted(lead_broker.INGRESS_CHANNEL.values()))  # a Lead session's own channels


@pytest.fixture
def endpoint(project):
    console = Console()
    ep = operator_endpoint.OperatorEndpoint(Engine.discover(project.root), console=console, dev=True, timeout=10)
    ep.start()
    yield ep, console
    ep.close()


def _proposed(p, tmp_path: Path, text: str = "1. Add subtract(a, b) to calc/core.py.\n") -> str:
    wid = p.lead("work", "create", "ticket", "--title", "Add subtract()", "--class", "1", "--goal", "g",
                 "--scope", "calc/**", "--scope", "tests/**")["id"]
    _propose(p, tmp_path, wid, text)
    return wid


def _propose(p, tmp_path: Path, wid: str, text: str) -> int:
    plan = tmp_path / f"{wid}-{abs(hash(text))}.md"
    plan.write_text(text, encoding="utf-8")
    return p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan),
                  "--affected", "calc/core.py")["revision_number"]


def _session_cli(p, argv: list[str], channel: str = "lead_broker") -> dict[str, Any]:
    """One command as a Lead session's broker runs it: relayed, with the held credential, on its channel."""
    return lead_broker.run_cli(Engine.discover(p.root), p.token, argv, str(p.root), "", channel=channel)


def _plan_argv(p, wid: str, revision: int = 1) -> list[str]:
    return p.ok("status", wid, "--json")["plan_accept_argv"][str(revision)]


def _accepted(p, wid: str) -> int | None:
    return (load_control(p.root)["work"][wid].get("plan") or {}).get("accepted")


def _refusal(exc: pytest.ExceptionInfo[errors.AEWError], reason: str) -> None:
    assert exc.value.code == "OPERATOR_AUTHORIZATION_REQUIRED" and exc.value.details["reason"] == reason, exc.value


@pytest.mark.parametrize("channel", LEAD_CHANNELS)
def test_a_lead_sessions_plan_accept_is_refused_without_the_operators_confirmation_and_goes_through_with_it(
        project, tmp_path, endpoint, channel):
    """The refusal names what was refused, why, and the command the operator runs; the operator's confirmation, given
    through the endpoint's challenge with the code from its console, lets exactly that acceptance through, once."""
    ep, console = endpoint
    wid = _proposed(project, tmp_path)
    argv = _plan_argv(project, wid)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _session_cli(project, argv, channel)
    _refusal(refused, OD.REQUIRED)
    assert refused.value.details["ask_operator"] == f"aew operator confirm plan {wid} --revision 1"
    assert "operator's decision" in refused.value.message and "call this again" in refused.value.message
    assert _accepted(project, wid) is None

    prompts: list[str] = []

    def typed(prompt: str) -> str:
        prompts.append(prompt)
        return console.code()

    aew, asked_at = project.root / ".aew", project.rev()
    out = operator_client.request_confirmation(aew, "plan", wid, ask=typed, requester="test")
    sha = load_control(project.root)["work"][wid]["plans"][0]["sha256"]
    assert out["decision"] == "plan" and out["subject"]["sha256"] == sha and out["guarantee"] == "dev"
    shown = "".join(console.lines)
    assert sha in shown and "plan v1" in shown and console.code() not in "".join(prompts)
    # It is held beside control state and moves no revision. The Lead retries its same bound request.
    assert [c["id"] for c in OD.standing(aew)] == [out["confirmation"]] and project.rev() == asked_at

    done = _session_cli(project, argv, channel)["result"]
    assert done["accepted"] == 1 and _accepted(project, wid) == 1
    state = load_control(project.root)
    assert not OD.standing(aew) and out["confirmation"] in state["last_transition"]["summary"]
    assert_control_invariants(project)


def test_a_confirmation_counts_once_and_only_for_the_plan_it_was_shown(project, tmp_path):
    """Bound to the plan's SHA-256: a confirmation of revision 1 does not accept revision 2, and an acceptance uses its
    confirmation up."""
    wid = _proposed(project, tmp_path)
    second = _propose(project, tmp_path, wid, "1. Add subtract and a test.\n")
    argv = _plan_argv(project, wid, second)
    confirm(project.root, "plan", wid, revision=1)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _session_cli(project, argv)
    _refusal(refused, OD.STALE)
    assert refused.value.details["ask_operator"] == f"aew operator confirm plan {wid} --revision {second}"
    confirm(project.root, "plan", wid, revision=second)  # replaces the confirmation of revision 1
    assert _session_cli(project, argv)["result"]["accepted"] == second
    assert not OD.standing(project.root / ".aew")


def test_a_plan_that_moved_while_the_operator_was_asked_is_not_confirmed(project, tmp_path):
    engine = Engine.discover(project.root)
    wid = _proposed(project, tmp_path)
    bound = engine.operator_confirmation_preview("plan", wid)
    bound["subject"] = {**bound["subject"], "sha256": "0" * 64}  # what the operator was shown is not there now
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        engine.operator_confirm(principal(), bound)
    _refusal(refused, OD.MOVED)
    assert not OD.standing(project.root / ".aew")


def test_a_flag_or_argument_from_the_lead_never_counts_as_the_confirmation(project, tmp_path):
    """No argument carries a confirmation: the plan's own digest flag still refuses, the typed surface takes no such
    argument, and only the principal the endpoint constructs can commit one."""
    wid = _proposed(project, tmp_path)
    argv = _plan_argv(project, wid)
    with pytest.raises(errors.ChangedSinceRead):
        _session_cli(project, ["plan", "accept", wid, "--revision", "1"])
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        _session_cli(project, argv)
    _refusal(refused, OD.REQUIRED)
    with pytest.raises(AdapterInputError):
        check_call("integration_publish", {"work_id": wid, "prepared_candidate": "a" * 40,
                                          "operator_confirmed": True}, "normal")
    for flag in (["--confirmed"], ["--operator-confirmed"], ["--by", "operator"]):
        with pytest.raises(errors.UsageError):
            _session_cli(project, [*argv, *flag])

    class Lookalike:  # what a caller that is not the endpoint could build
        uid, method, endpoint_pid, endpoint_started_at, guarantee = 0, "peer_credentials", 1, "x", "dev"

        def record(self) -> dict[str, Any]:
            return {"uid": 0}

    engine = Engine.discover(project.root)
    bound = engine.operator_confirmation_preview("plan", wid)
    for fake in (Lookalike(), {"authorized_by": "operator-tty"}, None):
        with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
            engine.operator_confirm(fake, bound)  # type: ignore[arg-type]
        _refusal(refused, OD.NOT_ENDPOINT)
    assert not OD.standing(project.root / ".aew") and _accepted(project, wid) is None


def test_the_operators_own_plan_accept_at_their_terminal_needs_no_confirmation(project, tmp_path):
    """The operator running the command with the Lead credential, outside any Lead session, is the decision itself:
    their own CLI, and an in-process call, ask for nothing more."""
    wid = _proposed(project, tmp_path)
    assert project.lead("plan", "accept", wid, "--revision", "1")["accepted"] == 1
    other = _proposed(project, tmp_path, "1. Something else.\n")
    argv = _plan_argv(project, other)
    with dispatch.channel(dispatch.DIRECT):
        Engine.discover(project.root).plan_accept(token=project.token, work_id=other, revision=1,
                                                  binding=argv[argv.index("--approval-digest") + 1])
    assert _accepted(project, other) == 1 and not OD.standing(project.root / ".aew")
    third = _proposed(project, tmp_path, "1. A third thing.\n")
    confirm(project.root, "plan", third)  # confirmed, and then accepted by the operator themselves
    assert project.lead("plan", "accept", third, "--revision", "1")["accepted"] == 1
    assert not OD.standing(project.root / ".aew")  # their own acceptance leaves no confirmation standing
    assert_control_invariants(project)


def test_every_channel_a_lead_session_carries_a_call_on_asks_for_the_confirmation():
    """Who is asked is read from the channel: each of the broker's ingresses and the steering loop's is a Lead
    session's, and only the operator's own CLI and an in-process caller are not."""
    for name in (*lead_broker.INGRESS_CHANNEL.values(), steering_loop.CHANNEL, "anything-new"):
        with dispatch.channel(name):
            assert OD.required(), name
    for name in (dispatch.CLI, dispatch.DIRECT):
        with dispatch.channel(name):
            assert not OD.required(), name
    assert not OD.required()  # no channel set: an in-process caller


def _lead_publish(p, wid: str, candidate: str) -> dict[str, Any]:
    """The typed `integration_publish`, as a Lead session's MCP transport carries it."""
    with dispatch.channel("lead_mcp"):
        return R.run_tool(Engine.discover(p.root), SurfaceContext.outside_session(), "integration_publish",
                          {"work_id": wid, "prepared_candidate": candidate}, token=p.token)


def test_a_lead_sessions_publish_needs_the_operators_confirmation_and_the_operators_own_does_not(tmp_path):
    """The typed `integration_publish` and the relayed `integrate publish`, on a Lead session's channels, are refused
    until the operator confirms the candidate; the confirmation shows the candidate and its base, and the publish then
    goes through once. The operator's own `aew integrate publish` at their terminal publishes with none."""
    project = sample_project(tmp_path)
    first, _ = to_commit_ready(project, tmp_path)
    integ = prepare_and_validate(project, first)
    error = _lead_publish(project, first, integ["candidate"])["stopped"]["error"]
    assert error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED" and error["details"]["reason"] == OD.REQUIRED, error
    assert error["details"]["ask_operator"] == f"aew operator confirm publish {first}"
    with pytest.raises(errors.OperatorAuthorizationRequired):
        _session_cli(project, ["integrate", "publish", first, "--candidate", integ["candidate"]])
    assert load_control(project.root)["work"][first]["state"] == "COMMIT_READY"
    assert project.lead("integrate", "publish", first)["state"] == "DONE"  # the operator's own: no confirmation

    second, _ = to_commit_ready(project, tmp_path, files=APPLY_PATCH, title="Add apply()")
    integ = prepare_and_validate(project, second)
    assert _lead_publish(project, second, integ["candidate"])["stopped"]["error"]["details"]["reason"] == OD.REQUIRED
    shown = confirm(project.root, "publish", second)
    assert shown["subject"]["candidate"] == integ["candidate"] and shown["subject"]["base"] == integ["base"]
    out = _lead_publish(project, second, integ["candidate"])
    assert out["ok"], out["stopped"]
    state = load_control(project.root)
    assert second not in state["work"] or state["work"][second]["state"] == "DONE"
    assert not OD.standing(project.root / ".aew") and git("rev-parse", "main", cwd=project.root) == integ["candidate"]
    assert_control_invariants(project)


def _used(p, since: int) -> list[dict[str, Any]]:
    """The confirmations the transitions after revision ``since`` used, as their log records declare them."""
    aew = p.root / ".aew"
    return [dict(e, revision=r) for r in range(since + 1, p.rev() + 1)
            for e in outbox.complete_events(aew, outbox.read_record(aew, r) or {}) or []
            if e["kind"] == outbox.CONFIRMATION_USED]


def test_a_used_confirmation_leaves_its_provenance_on_the_decision_it_authorised(tmp_path):
    """The held confirmation is dropped once the commit that used it lands; that commit's log record keeps who
    confirmed what and when (review of #618, m1). The ids count again if `.aew/local` is removed, so the binding and
    the time beside each id keep two of the same id apart."""
    project = sample_project(tmp_path)
    first, _ = to_commit_ready(project, tmp_path)
    integ = prepare_and_validate(project, first)
    before = project.rev()
    given = confirm(project.root, "publish", first)
    assert _lead_publish(project, first, integ["candidate"])["ok"]
    [used] = _used(project, before)
    assert not OD.standing(project.root / ".aew")
    assert used["id"] == given["confirmation"] and used["decision"] == "publish" and used["work"] == first
    assert used["binds"] == integ["candidate"] and used["by"] == principal().record() and used["at"]
    assert outbox.read_record(project.root / ".aew", used["revision"])["op"] == "integrate.publishing"

    (project.root / ".aew" / OD.REL).unlink()  # the counter goes with it
    wid = _proposed(project, tmp_path)
    before = project.rev()
    again = confirm(project.root, "plan", wid)
    assert again["confirmation"] == given["confirmation"]  # the same id, for another decision
    done = _session_cli(project, _plan_argv(project, wid))["result"]
    [used] = _used(project, before)
    sha = load_control(project.root)["work"][wid]["plans"][0]["sha256"]
    assert used["revision"] == done["revision"] and used["decision"] == "plan" and used["work"] == wid
    assert used["binds"] == sha != integ["candidate"] and used["by"] == principal().record()
    assert outbox.read_record(project.root / ".aew", done["revision"])["op"] == "plan.accept"
    assert_control_invariants(project)


def test_the_operators_own_call_uses_no_confirmation_and_declares_none(project, tmp_path):
    """A confirmation the operator's own acceptance drops was not used: no provenance is claimed for it."""
    wid = _proposed(project, tmp_path)
    confirm(project.root, "plan", wid)
    before = project.rev()
    assert project.lead("plan", "accept", wid, "--revision", "1")["accepted"] == 1
    assert _used(project, before) == [] and not OD.standing(project.root / ".aew")


def test_the_operator_confirms_only_from_their_own_terminal(project):
    """`aew operator confirm` is the operator's: a Lead session's broker refuses it, and with no terminal to type the
    code back at it is refused before the endpoint is asked."""
    parser = build_parser()
    refusal = lead_broker.refuses_locally(parser.parse_args(["operator", "confirm", "plan", "T-0001"]))
    assert refusal and "operator's own confirmation" in refusal and "ask the operator" in refusal
    res = run_aew("-C", str(project.root), "operator", "confirm", "plan", "T-0001")
    assert res.returncode != 0 and res.error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED", res.stderr
    assert res.error["details"]["reason"] == OD.NO_TERMINAL, res.error
    assert "aew operator confirm plan T-0001" in res.error["message"] and "terminal" in res.error["message"]
    res = run_aew("-C", str(project.root), "operator", "confirm", "plan", "T-0001",
                  env={"AEW_LEAD_BROKER": "x", "AEW_LEAD_BROKER_KEY": "y"})
    assert res.returncode != 0 and "operator's own confirmation" in res.stderr, res.stderr


def test_nothing_to_confirm_is_refused_before_the_operator_is_asked(project, tmp_path, endpoint):
    ep, console = endpoint
    wid = project.lead("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g",
                       "--scope", "calc/**")["id"]
    for decision in ("plan", "publish"):
        with pytest.raises(errors.IllegalTransition):
            operator_client.request_confirmation(project.root / ".aew", decision, wid, ask=lambda p: "x",
                                                 requester="test")
    assert console.lines == []
