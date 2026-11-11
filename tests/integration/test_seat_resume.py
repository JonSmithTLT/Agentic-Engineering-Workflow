"""Operator terminal resume and its generation, invocation and process bindings."""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
from aewflow import assign, create_planned_ticket, sample_project
from conftest import clean_env
from invariants import assert_control_invariants

from aew import operator, process_kind, switch_offer
from aew.engine.api import Engine
from aew.errors import PermissionDenied, StaleAuthority
from aew.harness import lead_broker, procs, seat
from aew.harness.opencode import lead
from aew.harness.procs import same_process


@pytest.fixture
def acquired(tmp_path, monkeypatch):
    project = sample_project(tmp_path)
    engine = Engine.discover(project.root)
    engine.lead_release(token=project.token, expect_rev=project.rev())
    old = engine.lead_acquire(expect_rev=project.rev(), session_label="old", kind=seat.VACANT_START)
    project.token = old["token"]
    seat.write_leftovers(engine.aew_root, old["generation"], seat.empty_leftovers())
    prompts = []

    def authorize(prompt):
        prompts.append(prompt)
        return {"authorized_by": "operator-tty (test)"}

    monkeypatch.setattr(procs, "same_process", lambda *_: False)
    monkeypatch.setattr(switch_offer, "terminal", lambda: True)
    monkeypatch.setattr(operator, "authorize", authorize)
    return project, engine, old, prompts


def test_empty_seat_resumes_without_a_code_and_can_resume_again(acquired):
    project, engine, old, prompts = acquired
    first = engine.lead_resume(session_label="first")
    assert first["generation"] == old["generation"] + 1
    assert first["carried_invocations"] == []
    assert not prompts
    seat.write_leftovers(engine.aew_root, first["generation"], seat.empty_leftovers())
    second = engine.lead_resume()
    assert second["generation"] == first["generation"] + 1
    assert not prompts
    with pytest.raises(StaleAuthority):
        engine.lead_release(token=old["token"], expect_rev=project.rev())
    assert_control_invariants(project)


@pytest.mark.parametrize("with_leftovers", [False, True])
def test_resume_carries_every_active_invocation_and_moves_its_credential(acquired, tmp_path, with_leftovers):
    project, engine, old, prompts = acquired
    work = create_planned_ticket(project, tmp_path)
    assign(project, work)
    invocation, = engine.store.current()["invocations"]
    if with_leftovers:
        left = 2 if sys.platform == "win32" else [(4321, "leftover-a"), (4322, "leftover-b")]
        seat.write_leftovers(engine.aew_root, old["generation"], left)
    else:
        left = seat.empty_leftovers()
    result = engine.lead_resume()
    assert len(prompts) == 1
    assert all(value in prompts[0] for value in (work, invocation, "implementer", seat.describe_leftovers(left)))
    assert result["leftovers"] == left
    assert result["carried_invocations"] == [invocation]
    assert result["generation"] == old["generation"] + 1
    state = engine.store.current()
    carried = state["invocations"][invocation]
    assert carried["status"] == "active"
    assert carried["generation"] == state["tokens"][carried["token_id"]]["scope"]["generation"] == result["generation"]
    decision = (engine.aew_root / "decisions" / f"{result['decision']}.md").read_text(encoding="utf-8")
    assert all(value in decision for value in ("seat_resume", "operator-tty (test)", invocation, "dev-grade"))
    assert_control_invariants(project)


@pytest.mark.parametrize(("failure", "reason"), [
    ("kind", "seat_not_opencode"), ("legacy", "seat_not_opencode"), ("host", "seat_other_principal"),
    ("user", "seat_other_principal"), ("live", "seat_session_live"), ("handoff", "seat_handoff_pending"),
    ("terminal", "seat_operator_terminal_required"), ("inside", "seat_operator_terminal_required"),
    ("non_writer", "seat_operator_terminal_required"),
    ("general_session", "seat_not_opencode"), ("takeover", "seat_not_opencode"),
])
def test_ineligible_seats_refuse_without_prompting(acquired, monkeypatch, failure, reason):
    project, engine, old, prompts = acquired
    host, user = seat.principal()
    if failure in {"kind", "legacy"}:
        engine.lead_release(token=old["token"], expect_rev=project.rev())
        engine.lead_acquire(expect_rev=project.rev(), session_label="old")
    if failure == "general_session":
        engine.lead_release(token=old["token"], expect_rev=project.rev())
        monkeypatch.setattr(procs, "harden_current_process", lambda: None)
        monkeypatch.setattr(procs, "run_session_tree", lambda *_, **__: (0, "clean"))
        lead_broker.run_session(engine, ["synthetic"], acquire=True, session_label="old", keep_seat=True,
                                contained=lambda _dir, env: lead_broker.Harness(
                                    argv=["synthetic"], env=env, relay=False, label={}, close=lambda: None))
    if failure == "takeover":
        engine.lead_takeover(expect_rev=project.rev(), reason="test takeover", session_label="old")
        assert len(prompts) == 1
        prompts.clear()
    if failure == "legacy":
        original = engine.store.current

        def current():
            state = original()
            state["lead"].pop("start")
            return state

        monkeypatch.setattr(engine.store, "current", current)
    if failure == "host":
        monkeypatch.setattr(seat, "principal", lambda: (host + "-other", user))
    if failure == "user":
        monkeypatch.setattr(seat, "principal", lambda: (host, str(user) + "-other"))
    if failure == "live":
        monkeypatch.setattr(procs, "same_process", same_process)  # the acquiring test process is still alive
    if failure == "handoff":
        engine.lead_handoff_offer(token=old["token"], expect_rev=project.rev())
    if failure == "terminal":
        monkeypatch.setattr(switch_offer, "terminal", lambda: False)
    if failure == "inside":
        monkeypatch.setenv(lead_broker.ENV_ENDPOINT, "synthetic-endpoint")
    if failure == "non_writer":
        monkeypatch.setattr(process_kind, "kind", lambda: process_kind.NON_WRITER)
    before = engine.store.current()
    with pytest.raises(PermissionDenied, match="aew lead takeover") as refused:
        engine.lead_resume()
    assert refused.value.details["reason"] == reason
    assert "old" in str(refused.value)
    assert not prompts and engine.store.current() == before


@pytest.mark.parametrize("condition", ["missing", "unreadable", "wrong_generation", "declined"])
def test_unknown_leftovers_require_acknowledgement(acquired, monkeypatch, condition):
    _, engine, old, prompts = acquired
    record = engine.aew_root / "local" / "lead" / f"leftovers-{old['generation']}.json"
    record.unlink()
    if condition == "unreadable":
        record.write_text("{", encoding="utf-8")
    if condition == "wrong_generation":
        record.write_text(json.dumps({"generation": 0, "processes": seat.empty_leftovers()}), encoding="utf-8")
    if condition == "declined":
        before = engine.store.current()

        def decline(_):
            raise PermissionDenied("declined")

        monkeypatch.setattr(operator, "authorize", decline)
        with pytest.raises(PermissionDenied, match="declined"):
            engine.lead_resume()
        assert engine.store.current() == before
    else:
        assert engine.lead_resume()["leftovers"] is None
        assert len(prompts) == 1 and "processes left : unknown" in prompts[0]


@pytest.mark.parametrize("race", ["new_invocation", "generation", "unrelated_revision", "ended"])
def test_resume_rechecks_the_bound_subject_after_the_prompt(acquired, tmp_path, monkeypatch, race):
    project, engine, old, _ = acquired
    work = create_planned_ticket(project, tmp_path)
    seat.write_leftovers(engine.aew_root, old["generation"], None)
    changes = {}
    if race in {"ended", "unrelated_revision"}:
        assign(project, work)
        changes["invocation"], = engine.store.current()["invocations"]

    def authorize(_):
        if race == "new_invocation":
            assign(project, work)
            changes["invocation"], = engine.store.current()["invocations"]
        elif race == "generation":
            engine.lead_release(token=old["token"], expect_rev=project.rev())
            changes.update(engine.lead_acquire(expect_rev=project.rev(), kind=seat.VACANT_START))
        elif race == "ended":
            engine.invoke_cancel(token=project.token, expect_rev=project.rev(), invocation=changes["invocation"],
                                 reason="finished while the operator was reading the prompt")
        else:
            project.lead("checkpoint", "--next", "still working")
        return {"authorized_by": "operator-tty (test)"}

    monkeypatch.setattr(operator, "authorize", authorize)
    if race in {"unrelated_revision", "ended"}:
        result = engine.lead_resume()
        assert result["generation"] == old["generation"] + 1
        assert result["carried_invocations"] == ([changes["invocation"]] if race == "unrelated_revision" else [])
        if race == "ended":
            decision = engine.aew_root / "decisions" / f"{result['decision']}.md"
            assert f"Ended before transfer: {changes['invocation']}" in decision.read_text(encoding="utf-8")
    else:
        with pytest.raises(PermissionDenied) as refused:
            engine.lead_resume()
        assert refused.value.details["reason"] == ("seat_resume_changed" if race == "generation" else
                                                    "seat_resume_unshown")
        if race == "new_invocation":
            assert changes["invocation"] in str(refused.value)
            assert engine.lead_show()["generation"] == old["generation"]
        else:
            assert engine.lead_show()["generation"] == changes["generation"]


@pytest.mark.parametrize("failed_start", [False, True])
def test_resumed_session_keeps_acknowledged_processes_at_exit(acquired, monkeypatch, failed_start):
    _, engine, old, prompts = acquired
    pid = 4321
    left = 1 if sys.platform == "win32" else [(pid, "leftover-start")]
    seat.write_leftovers(engine.aew_root, old["generation"], left)
    monkeypatch.setattr(procs, "same_process", lambda seen_pid, start: (seen_pid, start) == (pid, "leftover-start"))
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setattr(procs, "run_session_tree", lambda *_, **__: (0, "clean"))

    def contained(_dir, env):
        if failed_start:
            raise PermissionDenied("test start refused")
        return lead_broker.Harness(argv=["synthetic"], env=env, relay=False, label={}, close=lambda: None)

    if failed_start:
        with pytest.raises(PermissionDenied, match="test start refused"):
            lead_broker.run_session(engine, ["synthetic"], acquire=True, session_label="new", keep_seat=False,
                                    contained=contained, opencode_kind=seat.VACANT_START)
    else:
        result = lead_broker.run_session(engine, ["synthetic"], acquire=True, session_label="new", keep_seat=False,
                                         contained=contained, opencode_kind=seat.VACANT_START)
        assert result["seat"].startswith("held;")
    assert len(prompts) == 1
    assert engine.lead_show()["status"] == "active"
    assert seat.read_leftovers(engine.aew_root, old["generation"] + 1) == left


@pytest.mark.parametrize("keep_seat", [False, True])
def test_resumed_empty_seat_releases_or_stays_held_as_requested(acquired, monkeypatch, keep_seat):
    _, engine, old, prompts = acquired
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setattr(procs, "run_session_tree", lambda *_, **__: (0, "clean"))
    result = lead_broker.run_session(
        engine, ["synthetic"], acquire=True, session_label="new", keep_seat=keep_seat,
        contained=lambda _dir, env: lead_broker.Harness(
            argv=["synthetic"], env=env, relay=False, label={}, close=lambda: None),
        opencode_kind=seat.VACANT_START,
    )
    assert not prompts and engine.lead_show()["generation"] == old["generation"] + 1
    if keep_seat:
        assert result["seat"].startswith("held;") and engine.lead_show()["status"] == "active"
        assert seat.read_leftovers(engine.aew_root, old["generation"] + 1) == seat.empty_leftovers()
    else:
        assert result["seat"] == "released" and engine.lead_show()["status"] == "vacant"


def test_a_seat_held_by_a_live_lead_session_is_never_resumed(acquired, monkeypatch):
    project, engine, old, prompts = acquired
    engine.lead_release(token=old["token"], expect_rev=project.rev())
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags) as child:
        try:
            start = procs.start_id(child.pid)
            assert start
            record = {**seat.start_identity(seat.OPENCODE_ACQUIRE), "pid": child.pid, "start_id": start}
            with monkeypatch.context() as patch:
                patch.setattr(seat, "start_identity", lambda _: record)
                taken = engine.lead_acquire(expect_rev=project.rev(), kind=seat.OPENCODE_ACQUIRE,
                                            session_label="live child")
            seat.write_leftovers(engine.aew_root, taken["generation"], seat.empty_leftovers())
            monkeypatch.setattr(procs, "same_process", same_process)
            with pytest.raises(PermissionDenied, match="live child.*aew opencode") as refused:
                engine.lead_resume()
            assert refused.value.details["reason"] == "seat_session_live"
            assert "aew lead takeover" in str(refused.value)
        finally:
            child.kill()
            child.wait(timeout=10)
    assert engine.lead_resume()["generation"] == taken["generation"] + 1
    assert not prompts


def test_failed_start_preserves_an_active_invocation(acquired, tmp_path, monkeypatch):
    project, engine, old, prompts = acquired
    work = create_planned_ticket(project, tmp_path)
    assign(project, work)
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)

    def refused(*_):
        raise PermissionDenied("test start refused")

    with pytest.raises(PermissionDenied, match="test start refused"):
        lead_broker.run_session(engine, ["synthetic"], acquire=True, session_label="new", keep_seat=False,
                                contained=refused, opencode_kind=seat.VACANT_START)
    assert len(prompts) == 1
    state = engine.store.current()
    assert state["lead"]["status"] == "active"
    inv, = state["invocations"].values()
    assert inv["status"] == "active" and inv["generation"] == old["generation"] + 1


@pytest.mark.parametrize(("args", "exported", "mode"), [
    ([], False, "self"), (["--acquire"], False, "self"), (["--acquire"], True, "self"),
    ([], True, "export"), (["--prompt-token"], False, "prompt"), (["--prompt-token"], True, "prompt"),
])
def test_opencode_selects_the_seat_or_existing_credential(acquired, monkeypatch, args, exported, mode):
    from aew import lead_credential
    from aew.cli.main import build_parser

    project, engine, old, _ = acquired
    if mode == "self":
        engine.lead_release(token=old["token"], expect_rev=project.rev())
    monkeypatch.delenv(lead_credential.ENV, raising=False)
    if exported:
        monkeypatch.setenv(lead_credential.ENV, old["token"] if mode == "export" else "unused")
    asked = []

    def hidden(*_, **__):
        asked.append(True)
        return old["token"]

    monkeypatch.setattr(lead_credential, "can_prompt", lambda: True)
    monkeypatch.setattr(operator, "ask_hidden", hidden)
    monkeypatch.setattr(lead, "contained_here", lambda: False)
    monkeypatch.setattr(lead, "check_version", lambda: "test")
    monkeypatch.setattr(lead, "guide_of", lambda _: "")
    monkeypatch.setattr(lead, "command", lambda *_: ["synthetic"])
    monkeypatch.setattr(lead, "_readiness", lambda _: None)
    monkeypatch.setattr(lead, "_tools_before_the_tui", lambda **_: None)
    monkeypatch.setattr(lead, "_unrelayed", lambda _: None)
    monkeypatch.setattr(lead, "_switch_offers", lambda _: SimpleNamespace(apply=lambda _: None))
    monkeypatch.setattr(lead, "session_services", lambda *_, **__: contextlib.nullcontext(lambda: None))
    monkeypatch.setattr(procs, "harden_current_process", lambda: None)
    monkeypatch.setattr(procs, "run_session_tree", lambda *_, **__: (0, "clean"))

    class Harness:
        def __init__(self, *_, **__):
            pass

        def precheck(self):
            pass

        def __call__(self, _dir, env):
            assert lead_credential.ENV not in env
            lead_state = engine.store.current()["lead"]
            start = lead_state["start"]
            expected_kind = seat.OPENCODE_ACQUIRE if "--acquire" in args else seat.VACANT_START
            assert start["kind"] == expected_kind
            assert start["at"] == lead_state["acquired_at"] and start["generation"] == lead_state["generation"]
            assert set(start) == {"generation", "kind", "at", "host", "user", "pid", "start_id"}
            assert (start["host"], start["user"]) == seat.principal()
            assert start["pid"] and start["start_id"]
            return lead_broker.Harness(argv=["synthetic"], env=env, relay=False, label={}, close=lambda: None)

    monkeypatch.setattr(lead, "WeakerOpenCode", Harness)
    parser = build_parser()
    with pytest.raises(SystemExit) as incompatible:
        parser.parse_args(["opencode", "--acquire", "--prompt-token"])
    assert incompatible.value.code == 2
    parsed = parser.parse_args(["opencode", *args])
    outcome = lead.run(engine, acquire=parsed.acquire, prompt_token=parsed.prompt_token, session_label=None,
                       keep_seat=False, provider_env=[], extra_args=[], print_config=False)
    assert outcome["seat"] == ("released" if mode == "self" else "held by your AEW_LEAD_TOKEN")
    assert engine.lead_show()["generation"] == old["generation"] + (mode == "self")
    assert len(asked) == (mode == "prompt")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="requires a Linux controlling pseudo-terminal")
def test_v2_driver_answers_and_counts_the_resume_prompt(tmp_path):
    from notifier import until
    from vertical.ledger import Ledger
    from vertical.scripted_operator import Operator, Session, start_on_terminal

    out, err = tmp_path / "out", tmp_path / "err"
    argv = [sys.executable, "-B", "-c",
            "from aew import operator; operator.authorize('RESUME Lead seat'); print('ready', flush=True)"]
    with out.open("wb") as stdout, err.open("wb") as stderr:
        proc, master = start_on_terminal(argv, env=clean_env(), stdout=stdout, stderr=stderr,
                                         resume_prompt=True)
    session = Session(proc, out, err, tmp_path / "pid", master)

    def receive(_timeout, gone):
        until(lambda: gone() or out.read_text(encoding="utf-8").strip() == "ready", 15, "resume challenge")
        assert out.read_text(encoding="utf-8").strip() == "ready", err.read_text(encoding="utf-8")
        return {"words": "ready"}

    ledger = Ledger("V2-forced-mid-stage", platform="linux")
    driver = SimpleNamespace(chat=SimpleNamespace(receive=receive), ledger=ledger, said=[])
    try:
        assert Operator.first_words(driver, session, resume_step="reopen:start") == {"words": "ready"}
        assert proc.wait(timeout=10) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
        session.close()
    assert ledger.to_json()["counts"]["pin_reentries"] == 1
    assert ledger.to_json()["counts"]["windows_console_challenges"] == 0
