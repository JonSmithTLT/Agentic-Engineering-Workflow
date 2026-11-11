"""Fixed-field full-body verification and typed-only durable consumption; text never chooses receipt IDs."""

from __future__ import annotations

import copy
import json

import pytest
from test_coordination_store import world
from test_message_send import broker, cli

from aew.harness import bridge
from aew.harness import told_messages as T


@pytest.mark.parametrize("sealed", [False, True])
@pytest.mark.parametrize("route", ["typed", "relayed"])
def test_failed_bridge_result_send_consumes_no_live_or_sealed_body(w, sealed, route):
    from aew.errors import AEWError

    mid = reply(w)
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="seal before the failed result send")
    with broker(w) as b:
        handler = b.server.handler

        def failing(op, args):
            result = handler(op, args)

            def deliver(sender):
                def broken(value):
                    raise OSError("scripted result write failed")

                if isinstance(result, bridge.ResultDelivery):
                    result.deliver(broken)
                else:
                    broken(result)

            return bridge.ResultDelivery(deliver)

        b.server.handler = failing
        op, args = (("lead.tool", {"name": "status", "profile": "normal", "ingress": "mcp",
                                  "arguments": json.dumps({"work_id": w.wid})}) if route == "typed" else
                    ("lead.read", {"argv": ["status", "--json"], "cwd": str(w.root)}))
        with pytest.raises(AEWError, match="scripted result write failed") as failed:
            bridge.call(op, args, endpoint=b.server.address, key=b.server.key_hex)
        assert failed.value.code == "BRIDGE_ERROR"
        assert b.server.drain(10)
        assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
        assert T.read(w.root / ".aew", b.generation) == set()


@pytest.mark.parametrize("sealed", [False, True])
@pytest.mark.parametrize("failure", ["write", "flush", "none"])
def test_own_shell_receipt_follows_successful_emit_and_flush(w, monkeypatch, sealed, failure):
    import importlib
    import io

    main = importlib.import_module("aew.cli.main")
    mid = reply(w)
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="sealed own-shell output boundary")
    monkeypatch.setenv("AEW_LEAD_TOKEN", w.token)
    monkeypatch.delenv("AEW_LEAD_BROKER", raising=False)

    class Output(io.StringIO):
        def flush(self):
            if failure == "flush":
                raise OSError("scripted output flush failed")
            super().flush()

    def emit(result, **kwargs):
        assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
        if failure == "write":
            raise OSError("scripted output write failed")

    monkeypatch.setattr(main, "_utf8_streams", lambda: None)
    monkeypatch.setattr(main, "emit", emit)
    with monkeypatch.context() as output:
        output.setattr(main.sys, "stdout", Output())
        argv = ["-C", str(w.root), "lead", "tool", "status", "--arguments", json.dumps({"work_id": w.wid})]
        if failure == "none":
            assert main._run_main(argv) == 0
        else:
            with pytest.raises(OSError, match="scripted output"):
                main._run_main(argv)
    assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == ([] if failure == "none" else [mid])


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


@pytest.mark.parametrize("field", ["id", "invocation", "work_unit", "sender", "run", "rendered"])
def test_changed_identity_or_partial_body_is_not_a_receipt(w, field):
    reply(w)
    result = w.e.status(w.wid)
    altered = copy.deepcopy(result)
    altered["coordination"]["awaiting_lead"][0][field] = "forged or partial"
    assert w.e.message_result_ids(altered) == []
    del altered["coordination"]["awaiting_lead"][0][field]
    assert w.e.message_result_ids(altered) == []


def test_an_added_raw_body_copy_is_not_a_verified_receipt(w):
    reply(w)
    altered = w.e.status(w.wid)
    altered["coordination"]["awaiting_lead"][0]["untrusted_text"] = "partial extra body"
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


def test_filtered_typed_read_and_its_project_projection_share_one_body_budget(w):
    from aew.surface import run
    from aew.surface.context import SurfaceContext, switches_for

    first = w.send()["message"]["id"]
    old_ids = {w.reply(first, body=f"settled reply {i}")["message"]["id"] for i in range(20)}
    w.lead("invoke_cancel", invocation=w.inv, reason="retain a full settled attention batch")
    replacement = w.lead("invoke_create", work_id=w.wid, role="implementer")
    second = w.send(to=replacement["invocation"])["message"]["id"]
    new_ids = {w.reply(second, body=f"live reply {i}", invocation_token=replacement["invocation_token"])[
        "message"]["id"] for i in range(20)}
    answer = run.run_tool(w.e, SurfaceContext.outside_session(switches=switches_for(w.e)),
                          "harness_status", {"invocation": w.inv}, token=w.token)
    carried = {m["id"] for key in ("result", "projection")
               for m in answer[key]["coordination"]["awaiting_lead"]}
    assert len(carried) <= 20, "one StageResult carried two independent 20-body batches"
    assert carried == old_ids
    assert answer["projection"]["coordination"]["omitted"] == 20
    assert answer["projection"]["coordination"]["recovery"] == "aew message unseen"
    run.record_message_result(w.e, answer, w.token)
    assert {m["id"] for m in w.e.message_attention()["awaiting_lead"]} == new_ids


def test_own_shell_typed_resume_records_the_sealed_body_and_the_next_commit_prunes_it(w):
    from aew.coordination import layout as L

    mid = reply(w)
    w.lead("invoke_cancel", invocation=w.inv, reason="ingest before the own-shell resume")
    sealed = w.thread_path().read_bytes()
    before = w.e.store.read()[L.UNSEEN_KEY]
    assert [e["message"] for e in before["entries"]] == [mid]
    plain = cli(w, "resume", "--json")
    assert plain.returncode == 0 and mid in plain.stdout
    assert w.e.store.read()[L.UNSEEN_KEY] == before
    typed = cli(w, "lead", "tool", "resume", "--arguments", "{}")
    assert typed.returncode == 0 and mid in typed.stdout, typed.stderr
    assert w.e.message_attention()["awaiting_lead"] == []
    assert w.e.store.read()[L.UNSEEN_KEY] == before  # the receipt itself commits nothing
    w.lead("checkpoint", note="prune the durably shown settled entry")
    assert L.UNSEEN_KEY not in w.e.store.read()
    assert w.thread_path().read_bytes() == sealed
    assert mid not in cli(w, "resume", "--json").stdout


@pytest.mark.parametrize("body_chars", [600, 3900])
def test_twenty_reply_status_quotes_each_selected_framed_body_once_and_stays_under_the_tool_cut(w, body_chars):
    from aew.surface import readable, run
    from aew.surface.context import SurfaceContext, switches_for

    lead = w.send()["message"]["id"]
    texts = [f"unique-worker-body-{i}-" + "x" * (body_chars - 30) for i in range(20)]
    ids = {w.reply(lead, body=text)["message"]["id"] for text in texts}
    answer = run.run_tool(w.e, SurfaceContext.outside_session(switches=switches_for(w.e)),
                          "status", {"work_id": w.wid}, token=w.token)
    text = readable.render(answer)
    assert len(text.encode()) < readable.CUT_BYTES
    selected = {m["id"] for m in answer["projection"]["coordination"]["awaiting_lead"]}
    assert 0 < len(selected) <= 20
    if body_chars == 600:
        assert len(selected) == 20
    else:
        assert len(selected) < 20
    assert answer["projection"]["coordination"]["omitted"] == 20 - len(selected)
    for body in texts:
        assert text.count(body) in (0, 1)
    assert sum(text.count(body) for body in texts) == len(selected)
    assert all(set(ref) == {"id"} for ref in answer["result"]["coordination"]["awaiting_lead"])
    run.record_message_result(w.e, answer, w.token)
    # No omitted body was consumed; subsequent bounded delivery can recover the remaining batch.
    unseen = w.e.message_attention()["awaiting_lead"]
    assert not selected & {m["id"] for m in unseen}
    assert {m["id"] for m in unseen} <= ids - selected


def test_an_over_cut_result_never_records_its_carried_worker_bodies_as_shown(w):
    from aew.surface import readable, run
    from aew.surface.context import SurfaceContext, switches_for

    mid = reply(w)
    answer = run.run_tool(w.e, SurfaceContext.outside_session(switches=switches_for(w.e)), "status", {}, token=w.token)
    answer["result"]["unrelated_large_field"] = "x" * readable.CUT_BYTES
    assert len(readable.render(answer).encode()) > readable.CUT_BYTES
    run.record_message_result(w.e, answer, w.token)
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
        assert b.server.drain(10)
        assert mid in answer["stdout"]
        assert worker_surface.changes(before, worker_surface.snapshot(w.root / ".aew")) == sorted(
            "+" + p for p in ("local/lead/", T.REL, T.LOCK_REL, T.LOCK_REL + ".queue"))
        assert T.read(w.root / ".aew", b.generation) == {mid}
        assert [m["id"] for m in w.e.message_attention()["awaiting_lead"]] == [mid]
        # A deliberate re-read re-lists the body without clearing the durable inbox or rewriting a thread/seen log.
        again = bridge.call("lead.read", {"argv": argv, "cwd": str(w.root)},
                            endpoint=b.server.address, key=b.server.key_hex)
        assert b.server.drain(10)
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
            result["coordination"]["awaiting_lead"][0]["rendered"] = "partial"
        elif plant == "nested":
            result = {"untrusted_text": result}
        elif plant == "wrong_target":
            ns.work_id = "T-9999"
        else:
            b._stop.set()
        b._read_receipt(result, ns)
        assert not (w.root / ".aew" / T.REL).exists()
