"""Lead waits carry verified message bodies without borrowing telemetry authority or losing own-shell cursors."""

from __future__ import annotations

import threading

import pytest
from fake_harness import credential_hits
from harness_conformance import FakeOpenCodeDriver
from test_worker_messages import MID, launch, send, steps_done

from aew.engine import outbox
from aew.engine.api import Engine
from aew.harness import bridge, lead_broker, runlog
from aew.harness import contract as K
from aew.harness import told_messages as T


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path)


REPLY = {"do": "aew", "args": ["message", "reply", MID, "--file", "-"], "stdin": "The reader is blocked."}


def test_broker_wait_returns_existing_live_reply_but_local_told_suppresses_new_news(lab, tmp_path, monkeypatch):
    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    e = Engine.discover(lab.root)
    result = e.harness_wait(run, timeout=0, triggers=True, message_after={})
    assert result["why"] == [K.WORKER_MESSAGE]
    ids = [m["id"] for m in result["messages"]]
    assert ids == ["MSG-INV-0001-2"] and e.message_result_ids(result) == ids
    with monkeypatch.context() as missing_digest:
        missing_digest.setattr(runlog, "read_progress", lambda directory: None)
        without_telemetry = e.harness_wait(run, timeout=0, triggers=True, message_after={})
    assert without_telemetry["why"] == [K.WORKER_MESSAGE]
    assert [m["id"] for m in without_telemetry["messages"]] == ids
    # A brokerless operator-shell wait takes an entry cursor, even if the local receipt is absent.
    assert e.harness_wait(run, timeout=0, triggers=True)["timed_out"] is True
    T.record(lab.aew_root, e.store.read()["lead"]["generation"], ids, current=lambda: True)
    assert e.harness_wait(run, timeout=0, triggers=True, message_after={})["timed_out"] is True
    assert [m["id"] for m in e.message_attention()["awaiting_lead"]] == ids
    (sync / "end").touch()
    lab.wait(run)
    ended = e.harness_wait(run, timeout=0, triggers=True, message_after={})
    assert ended["why"] == [K.RUN_ENDED] and ended["messages"] == []


def test_an_own_shell_wait_wakes_on_a_reply_created_after_its_entry_cursor(lab, tmp_path, monkeypatch):
    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    entered = threading.Event()
    original = outbox.wait_for

    def observing(check, root, **kwargs):
        def observed():
            result = check()
            entered.set()
            return result

        return original(observed, root, **kwargs)

    monkeypatch.setattr(outbox, "wait_for", observing)
    answers, errors = [], []

    def wait():
        try:
            answers.append(Engine.discover(lab.root).harness_wait(run, timeout=15, triggers=True))
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=wait)
    thread.start()
    try:
        assert entered.wait(10)
        (sync / "go").touch()
        thread.join(25)
        assert not thread.is_alive() and not errors
        assert answers[0]["why"] == [K.WORKER_MESSAGE]
        assert [m["id"] for m in answers[0]["messages"]] == ["MSG-INV-0001-2"]
    finally:
        (sync / "end").touch()
        thread.join(20)
    lab.wait(run)


def test_explicit_ended_run_carries_its_existing_reply_even_after_end_was_reported(lab, tmp_path):
    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    (sync / "end").touch()
    lab.wait(run)
    e = Engine.discover(lab.root)
    first = e.harness_wait(run, timeout=0, triggers=True)
    second = e.harness_wait(run, timeout=0, triggers=True)
    assert first["why"] == second["why"] == [K.RUN_ENDED, K.WORKER_MESSAGE]
    assert [m["id"] for m in second["messages"]] == ["MSG-INV-0001-2"]
    assert first["evidence"] == second["evidence"] and first["results"] == second["results"]


def test_a_relayed_live_wait_records_only_its_carried_body_locally(lab, tmp_path):
    import json

    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    e = Engine.discover(lab.root)
    # Use the engine's verified identity rather than assuming which planning unit came first.
    inv = e.store.read()["invocations"]["INV-0001"]
    thread = lab.aew_root / "work" / inv["work_unit"] / "coordination/INV-0001.jsonl"
    before = thread.read_bytes()
    b = lead_broker.LeadBroker(e, lab.project.token)
    b.server.start()
    try:
        answer = bridge.call("lead.read", {"argv": ["harness", "wait", run, "--timeout", "0"], "cwd": str(lab.root)},
                             endpoint=b.server.address, key=b.server.key_hex)
        assert answer["exit"] == 0, answer
        ids = {m["id"] for m in json.loads(answer["stdout"])["messages"]}
        assert ids == {"MSG-INV-0001-2"} and T.read(lab.aew_root, b.generation) == ids
        assert thread.read_bytes() == before
        assert {m["id"] for m in e.message_attention()["awaiting_lead"]} == ids
        again = bridge.call("lead.read", {"argv": ["harness", "wait", run, "--timeout", "0"], "cwd": str(lab.root)},
                            endpoint=b.server.address, key=b.server.key_hex)
        assert json.loads(again["stdout"])["timed_out"] is True
    finally:
        b.close()
        (sync / "end").touch()
    lab.wait(run)
