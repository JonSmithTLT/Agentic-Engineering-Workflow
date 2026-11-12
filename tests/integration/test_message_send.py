"""MS3's typed send: recording, not delivery, behind the adopted switch; real broker and CLI boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from test_coordination_store import OPERATOR, set_messaging, world

from aew.harness import bridge, lead_broker
from aew.surface import client, contract, lead_text, mcp, run
from aew.surface.context import SurfaceContext, switches_for
from aew.surface.validate import AdapterInputError

SRC = Path(__file__).resolve().parents[2] / "src"
# Full catalogs with messaging off, including E327's optional resolve approval digest.
OFF_LIST_SHA = {"normal": "34786d9f407b2e7bf3f05cab3e4ecbbf2d55438b905ca0e56dbdbf1588b838d0",
                "recovery": "ac57b66069f8001c25b94984975c351e16eddaf02f7e8869eafa0b0eefc80567"}
OFF_CLI_SHA = "c104c7de0b9b070d205ffb3fd03d78f4df1efc07127242b57bf9393843eb8c91"


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def call(w, *, ctx=None, **arguments):
    return run.run_tool(w.e, ctx or SurfaceContext.outside_session(switches=switches_for(w.e)), "message_send",
                        {"expect_rev": w.rev(), "to": w.inv, "body": "Check the shutdown edge.", **arguments},
                        token=w.token)


@contextmanager
def broker(w):
    b = lead_broker.LeadBroker(w.e, w.token)
    b.server.start()  # real bridge, no background steering or model
    try:
        yield b
    finally:
        b.close()


def forwarded(b, w, *, ingress="mcp", **arguments):
    return bridge.call("lead.tool", {"name": "message_send", "profile": "normal", "ingress": ingress,
                                    "arguments": json.dumps({"expect_rev": w.rev(), "to": w.inv,
                                                             "body": "Check shutdown.", **arguments})},
                       endpoint=b.server.address, key=b.server.key_hex)


def cli(w, *arguments):
    return subprocess.run([sys.executable, "-m", "aew", "-C", str(w.root), *arguments],
                          env={**os.environ, "PYTHONPATH": str(SRC), "AEW_LEAD_TOKEN": w.token},
                          text=True, capture_output=True, timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@pytest.mark.parametrize("profile", ["normal", "recovery"])
def test_with_messaging_off_tools_list_is_byte_identical_on_both_profiles(profile):
    assert digest(mcp.tools_list(profile)) == OFF_LIST_SHA[profile]


@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_with_messaging_off_lead_tool_list_is_byte_identical(tmp_path, messaging):
    w = world(tmp_path, messaging=messaging)
    result = cli(w, "lead", "tool", "--list")
    assert result.returncode == 0, result.stderr
    assert digest(json.loads(result.stdout)) == OFF_CLI_SHA


@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_with_messaging_off_message_send_is_an_unknown_tool(tmp_path, messaging):
    w = world(tmp_path, messaging=messaging)
    before = w.control_bytes()
    with pytest.raises(AdapterInputError, match="no tool"):
        call(w)
    assert w.control_bytes() == before and not w.coordination_files()


def test_an_unadopted_switch_edit_leaves_message_send_absent(tmp_path):
    w = world(tmp_path, messaging=None)
    set_messaging(w.root, "enabled")
    assert not switches_for(w.e)
    result = cli(w, "lead", "tool", "--list")
    assert result.returncode == 0, result.stderr
    assert digest(json.loads(result.stdout)) == OFF_CLI_SHA
    assert not w.coordination_files()


def test_message_send_creates_no_invocation_run_or_credential_and_leaves_expect_rev_valid(tmp_path):
    w = world(tmp_path)
    before, rev = w.control_bytes(), w.rev()
    first = call(w)
    assert first["ok"], first["stopped"]
    assert first["revision"] == rev and first["completed_steps"] == [] and first["stage_intent_id"] is None
    assert first["base_operation_class"] == first["effective_operation_class"] == "MECHANICAL"
    assert first["result"]["delivery"] == "not_built" and "not built yet" in first["result"]["next"]
    assert w.control_bytes() == before
    assert call(w, body="A second message at the same revision.")["ok"]
    assert w.control_bytes() == before
    assert not list((w.root / ".aew").rglob("requests/*"))


@pytest.mark.parametrize("ingress,channel", [("mcp", "lead_mcp"), ("cli", "lead_broker")])
def test_a_retried_call_after_a_lost_broker_reply_returns_the_existing_message(tmp_path, ingress, channel):
    w = world(tmp_path)
    with broker(w) as b:
        first = forwarded(b, w, ingress=ingress)["stage_result"]  # discarded by a caller that lost its response
        retry = forwarded(b, w, ingress=ingress)["stage_result"]
    assert first["ok"] and retry["ok"]
    assert not first["result"]["duplicate"] and retry["result"]["duplicate"]
    assert first["result"]["message"] == retry["result"]["message"]
    assert retry["result"]["message"]["channel"] == channel
    assert len(w.e.message_thread(w.inv)["messages"]) == 1


def test_own_shell_typed_send_uses_its_credential_without_a_broker(tmp_path):
    w = world(tmp_path)
    answer = cli(w, "lead", "tool", "message_send", "--arguments",
                 json.dumps({"expect_rev": w.rev(), "to": w.inv, "body": "Check shutdown."}))
    assert answer.returncode == 0, answer.stderr
    out = json.loads(answer.stdout)
    assert out["ok"] and out["result"]["message"]["channel"] == "cli"
    assert w.token not in answer.stdout


@pytest.mark.parametrize("profile", ["normal", "recovery"])
def test_mcp_lists_and_sends_through_the_real_broker_with_its_launch_snapshot(tmp_path, monkeypatch, profile):
    w = world(tmp_path)
    with broker(w) as b:
        for name, value in b.env.items():
            monkeypatch.setenv(name, value)
        server = mcp.Server(lambda name, args, p: client.forward(name, args, ingress="mcp", profile=p), profile=profile)
        monkeypatch.delenv(contract.ENV_SWITCHES)  # later environment edits do not change this server's snapshot
        assert "message_send" in {t["name"] for t in server.dispatch("tools/list", {})["tools"]}
        answer = server.dispatch("tools/call", {"name": "message_send", "arguments": {
            "expect_rev": w.rev(), "to": w.inv, "body": "Check shutdown."}})
        assert not answer["isError"]
        assert answer["structuredContent"]["result"]["message"]["channel"] == "lead_mcp"
        assert w.token not in json.dumps(answer)


def test_message_send_with_a_stale_expect_rev_is_refused_and_never_retried(tmp_path):
    w = world(tmp_path)
    rev = w.rev()
    w.lead("checkpoint", note="The state changed.")
    before = w.control_bytes()
    out = call(w, expect_rev=rev)
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_revision"
    assert not w.coordination_files() and w.control_bytes() == before


def test_a_superseded_generation_cannot_send(tmp_path, monkeypatch):
    import aew.operator

    w = world(tmp_path)
    old = SurfaceContext(lead_session={"holds": True}, generation=w.e.store.current()["lead"]["generation"],
                         switches=contract.ALL_SWITCHES)
    monkeypatch.setattr(aew.operator, "authorize", lambda challenge, **kw: {"authorized_by": "operator-tty (test)"})
    w.e.lead_takeover(expect_rev=w.rev(), reason="the seat was lost", session_label="lead-b")
    out = call(w, ctx=old)
    assert not out["ok"] and out["stopped"]["boundary"] == "stale_authority"
    assert not w.coordination_files()


def test_message_send_reports_unseen_replies_on_its_thread(tmp_path):
    w = world(tmp_path)
    message = call(w)["result"]["message"]["id"]
    reply = w.reply(message)["message"]["id"]
    assert call(w)["result"]["unseen_replies"] == 1
    w.e.message_mark_shown(token=w.token, messages=[reply])
    assert call(w)["result"]["unseen_replies"] == 0


def test_turn_end_is_refused_before_recording_and_names_the_available_timing(tmp_path):
    w = world(tmp_path)
    out = call(w, when="turn-end")
    assert not out["ok"] and out["stopped"]["error"]["details"]["reason"] == "turn_end_not_built"
    assert "use next-step" in out["stopped"]["error"]["message"]
    assert "MS5b" not in out["stopped"]["error"]["message"]
    assert not w.coordination_files()
    assert call(w, when="next-step")["ok"]  # follow the refusal's printed next step


def test_on_guide_keeps_the_standard_ticket_path_descriptions(tmp_path):
    w = world(tmp_path)
    assert lead_text.guide_for(w.e) == str(w.e.lead_guide(lead_text.stages()))
    standard = contract.catalog(contract.ALL_SWITCHES, presentation="standard")
    assert all(s.description == standard[s.tool].description
               for s in lead_text.stages(switches=contract.ALL_SWITCHES))


def test_forged_switch_lists_the_row_but_the_brokers_off_snapshot_refuses_it(tmp_path, monkeypatch):
    w = world(tmp_path, messaging=None)
    with broker(w) as b:
        assert contract.ENV_SWITCHES not in b.env
        monkeypatch.setenv(contract.ENV_SWITCHES, json.dumps(sorted(contract.ALL_SWITCHES)))
        assert "message_send" in {t["name"] for t in mcp.Server(lambda *args: {}).dispatch("tools/list", {})["tools"]}
        result = forwarded(b, w)
        assert result["adapter_input_error"]["code"] == "UNKNOWN_TOOL"
    assert not w.coordination_files()


def test_broker_snapshot_does_not_follow_an_adoption_mid_session(tmp_path):
    w = world(tmp_path, messaging=None)
    with broker(w) as b:
        set_messaging(w.root, "enabled")
        w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="enable messaging", authorization=OPERATOR)
        assert switches_for(w.e) == contract.ALL_SWITCHES
        assert forwarded(b, w)["adapter_input_error"]["code"] == "UNKNOWN_TOOL"
    with broker(w) as fresh:
        assert forwarded(fresh, w)["stage_result"]["ok"]


@pytest.mark.parametrize("messaging", [None, "disabled"])
def test_with_messaging_off_the_lead_session_environment_is_byte_identical(tmp_path, messaging):
    w = world(tmp_path, messaging=messaging)
    with broker(w) as b:
        assert b.env == {lead_broker.ENV_ENDPOINT: b.server.address, lead_broker.ENV_KEY: b.server.key_hex}


def test_an_on_broker_cannot_record_after_the_operator_disables_messaging(tmp_path):
    w = world(tmp_path)
    with broker(w) as b:
        set_messaging(w.root, "disabled")
        w.e.manifest_adopt(token=w.token, expect_rev=w.rev(), reason="disable messaging", authorization=OPERATOR)
        assert b.surface_switches == contract.ALL_SWITCHES
        answer = forwarded(b, w)["stage_result"]
        assert not answer["ok"] and answer["stopped"]["error"]["code"] == "MESSAGING_DISABLED"
    assert not w.coordination_files()


def test_a_forged_runner_snapshot_never_bypasses_the_engine_switch(tmp_path):
    w = world(tmp_path, messaging=None)
    out = call(w, ctx=SurfaceContext.outside_session(switches=contract.ALL_SWITCHES))
    assert not out["ok"] and out["stopped"]["error"]["code"] == "MESSAGING_DISABLED"
    assert out["stopped"]["error"]["details"]["reason"] == "switched_off"
    assert not w.coordination_files()
