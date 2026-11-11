"""Worker messages through real supervisors, custody bridges and CLI processes against fake V2; no binary probe."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from aewflow import create_planned_ticket
from fake_harness import credential_hits
from harness_conformance import IMPLEMENT, FakeOpenCodeDriver, sync_dir
from racing_read import read_text_or_none
from test_harness_send_when import enable_messaging

from aew.engine.api import Engine

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
MID = "MSG-INV-0001-1"


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path)


def launch(lab, tmp_path, steps, *, qualified=True):
    enable_messaging(lab)
    cls = "FakeWaitOpenCodeAdapter" if qualified else "UnsupportedWaitOpenCodeAdapter"
    lab.env["AEW_HARNESS_ADAPTERS"] = f"opencode={HELPERS / 'message_wait_adapter.py'}:{cls}"
    sync = sync_dir(tmp_path)
    lab.script("R-INV-0001-1", {"steps": [
        {"do": "touch", "path": str(sync / "ready")},
        {"do": "wait_file", "path": str(sync / "go"), "timeout": 60}, *steps,
        {"do": "wait_file", "path": str(sync / "end"), "timeout": 60}]})
    work = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", work, "--launch")["launch"]["run"]
    lab.until(lambda: (sync / "ready").exists(), what="worker ready")
    return run, sync


def send(lab, body="Check the shutdown edge."):
    engine = Engine.discover(lab.root)
    return engine.message_record_lead(token=lab.project.token, expect_rev=engine.store.read()["revision"],
                                      to="INV-0001", body=body)


def steps_done(lab, run, i):
    lab.until(lambda: any(row["i"] == i for row in lab.transcript(run)), what=f"worker step {i}")
    return lab.step(run, i)


def test_worker_reads_and_replies_use_only_their_run_bridge_and_move_no_revision(lab, tmp_path):
    run, sync = launch(lab, tmp_path, [
        {"do": "aew", "args": ["message", "read"]},
        {"do": "aew", "args": ["message", "reply", MID, "--kind", "question", "--file", "-"],
         "stdin": "Does shutdown include the blocked reader?"}])
    first = send(lab)
    engine = Engine.discover(lab.root)
    revision = engine.store.read()["revision"]
    (sync / "go").touch()
    read = steps_done(lab, run, 2)
    reply = steps_done(lab, run, 3)
    assert read["exit"] == reply["exit"] == 0, (read, reply)
    view = json.loads(read["stdout"])
    assert view["thread"] == "INV-0001" and view["messages"][0]["id"] == first["message"]["id"]
    assert "does not change your launch contract" in view["messages"][0]["rendered"]
    thread = engine.message_thread("INV-0001")
    assert thread["messages"][-1]["untrusted_text"] == "Does shutdown include the blocked reader?"
    assert thread["messages"][-1]["in_reply_to"] == MID
    assert engine.store.read()["revision"] == revision
    (sync / "end").touch()
    lab.wait(run)


def test_message_wait_delivers_exactly_the_returned_lead_message_once(lab, tmp_path):
    run, sync = launch(lab, tmp_path, [
        {"do": "aew", "args": ["message", "wait", "--timeout", "5"]},
        {"do": "aew", "args": ["message", "wait", "--after", MID, "--timeout", "0"]}])
    send(lab)
    (sync / "go").touch()
    received = steps_done(lab, run, 2)
    assert received["exit"] == 0, received
    result = json.loads(received["stdout"])
    assert result["outcome"] == "messages" and [m["id"] for m in result["messages"]] == [MID]
    second = steps_done(lab, run, 3)
    assert second["exit"] == 0 and json.loads(second["stdout"])["messages"] == [], second
    thread = Engine.discover(lab.root).message_thread("INV-0001")
    delivered = [f for f in thread["messages"][0]["facts"] if f["kind"] == "DELIVERED"]
    assert len(delivered) == 1 and delivered[0]["via"] == "wait" and delivered[0]["transport_ref"] == run
    (sync / "end").touch()
    lab.wait(run)


def test_a_wait_orphaned_by_a_shorter_shell_timeout_records_no_delivery(lab, tmp_path):
    run, sync = launch(lab, tmp_path, [
        {"do": "shell", "command": "aew message wait --timeout 5", "timeout_s": 1}])
    (sync / "go").touch()
    shell = steps_done(lab, run, 2)
    assert shell["timed_out"]
    send(lab)
    output = Path(shell["stdout_file"])
    lab.until(lambda: "ended_early" in (read_text_or_none(output) or ""),
              what="orphaned wait exits early after its shell call ends")
    thread = Engine.discover(lab.root).message_thread("INV-0001")
    assert not any(f["kind"] == "DELIVERED" for f in thread["messages"][0]["facts"])
    assert shell["shell_pid"] != lab.record(run)["supervisor_pid"]
    (sync / "end").touch()
    lab.wait(run)


def test_an_unqualified_adapter_refuses_wait_without_consuming_a_message(lab, tmp_path):
    # Deterministic on either host: the site adapter declares no qualified call/step reporting.
    run, sync = launch(lab, tmp_path, [{"do": "aew", "args": ["message", "wait", "--timeout", "0"]}],
                       qualified=False)
    send(lab)
    (sync / "go").touch()
    result = steps_done(lab, run, 2)
    assert result["exit"] != 0 and json.loads(result["stderr"])["error"]["code"] == "WAIT_UNSUPPORTED", result
    thread = Engine.discover(lab.root).message_thread("INV-0001")
    assert not any(f["kind"] == "DELIVERED" for f in thread["messages"][0]["facts"])
    (sync / "end").touch()
    lab.wait(run)


def test_final_worker_reply_survives_submit_seal_and_a_post_submit_continuation(lab, tmp_path):
    from test_message_send import broker

    from aew.harness import bridge
    from aew.harness import told_messages as T

    run, sync = launch(lab, tmp_path, [
        {"do": "aew", "args": ["message", "reply", MID, "--file", "-"],
         "stdin": "Final reply before the implementation report."}, *IMPLEMENT])
    send(lab)
    (sync / "go").touch()
    assert steps_done(lab, run, 2)["exit"] == 0
    steps_done(lab, run, 5)  # real worker submit, not an inserted report or sealed owner fact
    e = Engine.discover(lab.root)
    inv = e.store.read()["invocations"]["INV-0001"]
    mid = "MSG-INV-0001-2"
    assert [m["id"] for m in e.message_attention()["awaiting_lead"]] == [mid]
    with broker(SimpleNamespace(e=e, token=lab.project.token)) as b:
        answer = bridge.call("lead.read", {"argv": ["status", "--json"], "cwd": str(lab.root)},
                             endpoint=b.server.address, key=b.server.key_hex)
        assert answer["exit"] == 0 and b.server.drain(10)
        assert T.read(lab.aew_root, b.generation) == {mid}
    # Local receipt must not prevent the final reply from entering the settled unseen list at ingestion.
    current = e.store.read()
    if current["work"][inv["work_unit"]]["state"] == "ASSIGNED":
        e.work_transition(token=lab.project.token, expect_rev=current["revision"],
                          work_id=inv["work_unit"], to="RUNNING")
    e.work_transition(token=lab.project.token, expect_rev=e.store.read()["revision"],
                      work_id=inv["work_unit"], to="REVIEW_PENDING")
    settled = e.message_attention()["awaiting_lead"]
    assert [m["id"] for m in settled] == [mid] and "seal" in settled[0]
    assert e.message_delivery_view()["awaiting_lead"] == []
    assert [m["id"] for m in e.resume()["coordination"]["awaiting_lead"]] == [mid]
    (sync / "end").touch()
    lab.wait(run)


pytestmark = pytest.mark.autopsy
