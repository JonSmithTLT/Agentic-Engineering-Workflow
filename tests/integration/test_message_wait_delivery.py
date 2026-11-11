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
from aew.harness import progress as P
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
        assert b.server.drain(10)
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


def test_post_before_wait_suppresses_messages_but_not_an_explicit_end_and_keeps_end_facts_identical(lab, tmp_path):
    from types import SimpleNamespace

    from test_message_wakes import Poster, queue, shape

    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    (sync / "end").touch()
    lab.wait(run)
    e = Engine.discover(lab.root)
    explicit = e.harness_wait(run, timeout=0, triggers=True, record_return=False)
    b = lead_broker.LeadBroker(e, lab.project.token)
    b.server.start()
    poster = Poster()
    try:
        q = queue(SimpleNamespace(root=lab.root, e=e), b, poster)
        q.tick()
        wake = shape(poster)
        assert wake["why"] == [K.RUN_ENDED, K.WORKER_MESSAGE]
        assert [m["id"] for m in wake["messages"]] == ["MSG-INV-0001-2"]
        assert all(explicit[key] == value for key, value in wake["ended"][run].items())
        after_post = e.harness_wait(run, timeout=0, triggers=True, message_after={})
        assert after_post["why"] == [K.RUN_ENDED] and after_post["messages"] == []
        assert after_post["evidence"] == explicit["evidence"] and after_post["results"] == explicit["results"]
    finally:
        b.close()


def test_worker_message_handler_ablation_breaks_the_actual_wait_assertion_and_restoration_returns(
        lab, tmp_path, monkeypatch):
    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    e = Engine.discover(lab.root)
    original = P.holds

    def disabled(digest, trigger, **kwargs):
        return False if trigger.get("why") == K.WORKER_MESSAGE else original(digest, trigger, **kwargs)

    def require_reply():
        result = e.harness_wait(run, timeout=0, triggers=True, message_after={})
        assert result.get("why") == [K.WORKER_MESSAGE], "worker_message handler did not return the verified reply"
        assert [m["id"] for m in result["messages"]] == ["MSG-INV-0001-2"]

    try:
        with monkeypatch.context() as missing:
            missing.setattr(P, "holds", disabled)
            with pytest.raises(AssertionError, match="worker_message handler did not return the verified reply"):
                require_reply()
        require_reply()
    finally:
        (sync / "end").touch()
    lab.wait(run)


@pytest.mark.parametrize("ended", [False, True])
def test_failed_relayed_wait_send_records_neither_message_nor_sequence_or_end_receipt(lab, tmp_path, ended):
    from aew.errors import AEWError

    run, sync = launch(lab, tmp_path, [REPLY])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    if ended:
        (sync / "end").touch()
        lab.wait(run)
    e = Engine.discover(lab.root)
    directory = runlog.run_dir(lab.aew_root, run)
    paths = [directory / name for name in (runlog.RETURNED_FILE, runlog.END_RETURNED_FILE)]
    before = [p.read_bytes() if p.exists() else None for p in paths]
    b = lead_broker.LeadBroker(e, lab.project.token)
    b.server.start()
    handler = b.server.handler

    def failing(op, args):
        result = handler(op, args)

        def deliver(sender):
            def broken(value):
                raise OSError("scripted wait result write failed")

            result.deliver(broken)

        return bridge.ResultDelivery(deliver)

    b.server.handler = failing
    try:
        with pytest.raises(AEWError, match="scripted wait result write failed") as failed:
            bridge.call("lead.read", {"argv": ["harness", "wait", run, "--timeout", "0"], "cwd": str(lab.root)},
                        endpoint=b.server.address, key=b.server.key_hex)
        assert failed.value.code == "BRIDGE_ERROR" and b.server.drain(10)
        assert [p.read_bytes() if p.exists() else None for p in paths] == before
        assert T.read(lab.aew_root, b.generation) == set()
        assert [m["id"] for m in e.message_attention()["awaiting_lead"]] == ["MSG-INV-0001-2"]
    finally:
        b.close()
        (sync / "end").touch()
    lab.wait(run)


def test_two_real_runs_share_the_twenty_body_wait_budget_and_omitted_replies_return_next(lab, tmp_path):
    from aewflow import create_investigation
    from test_harness_send_when import enable_messaging
    from test_worker_messages import HELPERS

    enable_messaging(lab)
    lab.env["AEW_HARNESS_ADAPTERS"] = f"opencode={HELPERS / 'message_wait_adapter.py'}:FakeWaitOpenCodeAdapter"
    sync = tmp_path / "two-run-sync"
    sync.mkdir()
    runs = []
    e = Engine.discover(lab.root)
    for n in (1, 2):
        run = f"R-INV-{n:04d}-1"
        lab.script(run, {"steps": [
            {"do": "wait_file", "path": str(sync / "go"), "timeout": 90},
            *[{"do": "aew", "args": ["message", "reply", f"MSG-INV-{n:04d}-1", "--file", "-"],
               "stdin": f"worker {n} reply {i}"} for i in range(11)],
            {"do": "touch", "path": str(sync / f"done-{n}")},
            {"do": "wait_file", "path": str(sync / "end"), "timeout": 90}]})
        wid = create_investigation(lab.project, tmp_path)
        launched = lab.lead("work", "dispatch", wid, "--launch")
        assert launched["launch"]["run"] == run
        runs.append(run)
        e.message_record_lead(token=lab.project.token, expect_rev=e.store.read()["revision"],
                              to=launched["invocation"], body=f"Report the observations for worker {n}.")
    (sync / "go").touch()
    try:
        lab.until(lambda: all((sync / f"done-{n}").exists() for n in (1, 2)),
                  60, "both real workers' eleven replies")
        expected = {f"MSG-INV-{n:04d}-{seq}" for n in (1, 2) for seq in range(2, 13)}
        first = e.harness_wait(runs, timeout=0, any_=True, triggers=True, message_after={})
        carried = {m["id"] for m in first["messages"]}
        assert len(carried) == 20 and carried < expected
        assert first["coordination"]["omitted"] == 2
        assert first["coordination"]["recovery"] == "aew message unseen"
        T.record(lab.aew_root, e.store.read()["lead"]["generation"], carried, current=lambda: True)
        second = e.harness_wait(runs, timeout=0, any_=True, triggers=True, message_after={})
        assert {m["id"] for m in second["messages"]} == expected - carried
        assert second["why"] == [K.WORKER_MESSAGE]
    finally:
        (sync / "end").touch()
    for run in runs:
        lab.wait(run)
