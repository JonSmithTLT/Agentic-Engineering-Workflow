"""Fixed-field full-body verification and typed-only durable consumption; text never chooses receipt IDs."""

from __future__ import annotations

import copy
import json

import pytest
from test_coordination_store import world
from test_message_send import broker, cli

from aew.harness import bridge
from aew.harness import told_messages as T


@pytest.fixture
def w(tmp_path):
    return world(tmp_path)


def reply(w):
    lead = w.send()["message"]["id"]
    return w.reply(lead)["message"]["id"]


@pytest.mark.parametrize("sealed", [False, True])
def test_complete_verified_result_ids_are_read_only_scoped_and_never_recursive(w, sealed):
    mid = reply(w)
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="verify a pinned settled receipt")
    result = w.e.status(w.wid)
    thread = w.thread_path().read_bytes()
    control = w.control_bytes()
    assert w.e.message_result_ids(result, work_id=w.wid, invocations={w.inv}) == [mid]
    assert w.e.message_result_ids(result, work_id="T-9999") == []
    assert w.e.message_result_ids(result, invocations={"INV-9999"}) == []
    assert w.e.message_result_ids({"untrusted_text": result}) == []
    assert w.e.message_result_ids({**result, "ok": False}) == []
    assert w.thread_path().read_bytes() == thread and w.control_bytes() == control


@pytest.mark.parametrize("field", ["id", "invocation", "work_unit", "sender", "run", "untrusted_text", "rendered"])
def test_changed_identity_or_partial_body_is_not_a_receipt(w, field):
    reply(w)
    result = w.e.status(w.wid)
    altered = copy.deepcopy(result)
    altered["coordination"]["awaiting_lead"][0][field] = "forged or partial"
    assert w.e.message_result_ids(altered) == []
    del altered["coordination"]["awaiting_lead"][0][field]
    assert w.e.message_result_ids(altered) == []


@pytest.mark.parametrize("sealed", [False, True])
def test_typed_broker_status_records_only_carried_messages_durably(w, sealed):
    mid = reply(w)
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="settle before the typed read")
    revision = w.rev()
    with broker(w) as b:
        answer = bridge.call("lead.tool", {"name": "status", "profile": "normal", "ingress": "mcp",
                                          "arguments": json.dumps({"work_id": w.wid})},
                             endpoint=b.server.address, key=b.server.key_hex)
    assert answer["stage_result"]["ok"] is True
    assert [m["id"] for m in answer["stage_result"]["projection"]["coordination"]["awaiting_lead"]] == [mid]
    assert w.e.message_attention()["awaiting_lead"] == [] and w.rev() == revision
    assert not (w.root / ".aew/local/lead/told-messages.json").exists()


def test_own_shell_lead_tool_consumes_but_plain_operator_status_does_not(w):
    mid = reply(w)
    plain = cli(w, "status", "--json")
    assert plain.returncode == 0 and mid in plain.stdout
    assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
    typed = cli(w, "lead", "tool", "status", "--arguments", json.dumps({"work_id": w.wid}))
    assert typed.returncode == 0, typed.stderr
    assert json.loads(typed.stdout)["ok"] is True
    assert w.e.message_attention()["awaiting_lead"] == []


def test_failed_typed_result_does_not_consume_its_attention_overlay(w):
    mid = reply(w)
    with broker(w) as b:
        answer = bridge.call("lead.tool", {"name": "work_show", "profile": "normal", "ingress": "mcp",
                                          "arguments": json.dumps({"work_id": "T-9999"})},
                             endpoint=b.server.address, key=b.server.key_hex)
    assert answer["stage_result"]["ok"] is False
    assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]


@pytest.mark.parametrize("sealed", [False, True])
@pytest.mark.parametrize("argv", [["status"], ["status", "--json"], ["resume"], ["resume", "--json"],
                                  ["harness", "status"]])
def test_relayed_complete_bodies_write_only_local_receipts_and_never_durable_shown(w, sealed, argv):
    import worker_surface

    mid = reply(w)
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="read a sealed reply through the relay")
    with broker(w) as b:
        before = worker_surface.snapshot(w.root / ".aew")
        answer = bridge.call("lead.read", {"argv": argv, "cwd": str(w.root)},
                             endpoint=b.server.address, key=b.server.key_hex)
        assert answer["exit"] == 0, answer["stderr"]
        assert mid in answer["stdout"]
        assert worker_surface.changes(before, worker_surface.snapshot(w.root / ".aew")) == sorted(
            "+" + p for p in ("local/lead/", T.REL, T.LOCK_REL, T.LOCK_REL + ".queue"))
        assert T.read(w.root / ".aew", b.generation) == {mid}
        assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
        # A deliberate re-read re-lists the body without clearing the durable inbox or rewriting a thread/seen log.
        again = bridge.call("lead.read", {"argv": argv, "cwd": str(w.root)},
                            endpoint=b.server.address, key=b.server.key_hex)
        assert again["exit"] == 0 and mid in again["stdout"]


def test_relayed_work_and_invocation_filters_cannot_consume_an_out_of_target_body(w):
    mid = reply(w)
    with broker(w) as b:
        for argv in (["status", "T-9999", "--json"], ["harness", "status", "INV-9999"]):
            answer = bridge.call("lead.read", {"argv": argv, "cwd": str(w.root)},
                                 endpoint=b.server.address, key=b.server.key_hex)
            assert mid not in answer["stdout"]
            assert T.read(w.root / ".aew", b.generation) == set()
        assert not (w.root / ".aew" / T.REL).exists()


@pytest.mark.parametrize("plant", ["failed", "partial", "nested", "wrong_target", "lost_authority"])
def test_a_relayed_receipt_rejects_failed_partial_nested_out_of_target_or_stale_results(w, plant):
    import argparse

    reply(w)
    result = w.e.status(w.wid)
    ns = argparse.Namespace(command="status", work_id=w.wid)
    with broker(w) as b:
        if plant == "failed":
            result["ok"] = False
        elif plant == "partial":
            result["coordination"]["awaiting_lead"][0]["untrusted_text"] = "partial"
        elif plant == "nested":
            result = {"untrusted_text": result}
        elif plant == "wrong_target":
            ns.work_id = "T-9999"
        else:
            b._stop.set()
        b._read_receipt(result, ns)
        assert not (w.root / ".aew" / T.REL).exists()
