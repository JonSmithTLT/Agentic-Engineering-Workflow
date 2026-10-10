"""The OpenCode adapter against a fake V2 server: what the neutral conformance scenarios cannot reach (the
designer's step-4 watch list, docs/implementation/harness-conformance.md §5).

The fake server (tests/helpers/fake_opencode.py) serves V2's shapes and the real 2.0.18 OpenAPI; knobs make
it behave badly in the ways a real server can: a slow catalog, a missing model or variant, a V1 or doctored
API, a lost event stream, a queued prompt at a turn boundary, a permission request, a form, a crash.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import fake_opencode
import pytest
from aewflow import create_planned_ticket
from fake_harness import HarnessLab, credential_hits
from harness_conformance import IMPLEMENT, PROVIDER_SECRET, FakeOpenCodeDriver, evidence_of, sync_dir
from proxy_env import RecordingProxy, proxy_env

from aew.harness import runlog
from aew.harness.opencode import projection

RUN = "R-INV-0001-1"


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def script(lab: HarnessLab, steps: list[dict[str, Any]], key: str = RUN, **server: Any) -> None:
    lab.script(key, {"steps": steps, "server": server})


def launch(lab: HarnessLab, tmp_path: Path) -> tuple[str, str, str]:
    wid = create_planned_ticket(lab.project, tmp_path)
    out = lab.lead("work", "assign", wid, "--launch")
    return wid, out["invocation"], out["launch"]["run"]


def harness_dir(lab: HarnessLab, run: str = RUN) -> Path:
    return runlog.run_dir(lab.aew_root, run) / "harness"


def fake_db(lab: HarnessLab, run: str = RUN) -> dict[str, Any]:
    return json.loads((harness_dir(lab, run) / "xdg-data" / "opencode" / "fake-db.json").read_text(encoding="utf-8"))


def events(lab: HarnessLab, run: str = RUN) -> list[dict[str, Any]]:
    """The run's event log so far; a last line still being written is skipped."""
    path = runlog.run_dir(lab.aew_root, run) / "events.jsonl"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return [json.loads(line) for line in text[:text.rfind("\n") + 1].splitlines()]


def refused_launch(lab: HarnessLab, tmp_path: Path) -> str:
    wid = create_planned_ticket(lab.project, tmp_path)
    res = lab.lead_res("work", "assign", wid, "--launch")
    assert res.error["code"] == "HARNESS_LAUNCH_FAILED" and "HARNESS_INCOMPATIBLE" in res.error["message"], res.error
    record = lab.record(RUN)
    assert record["status"] == "launch_failed"
    assert lab.ok("invoke", "show", "INV-0001")["status"] == "active" and not evidence_of(lab, wid)
    return res.error["message"]


# ---------------------------------------------------------------------------------------------- projection


def test_the_projection_reaches_the_server_and_the_session(lab, tmp_path):
    script(lab, IMPLEMENT)
    wid, inv, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    hdir = harness_dir(lab)
    started = json.loads((hdir / "fake-server.json").read_text(encoding="utf-8"))
    config = json.loads((hdir / "opencode-config.json").read_text(encoding="utf-8"))
    assert started["config"] == config
    denied = [projection.rule(a, "deny") for a in projection.ALWAYS_DENIED]
    private = projection.private_output_dirs(os.path.realpath(hdir), os.sep,
                                             scratch=os.path.realpath(hdir.parent / "scratch"))
    assert config["permissions"][-7:] == denied + [projection.rule("external_directory", "allow", p) for p in private]
    assert projection.rule("edit", "allow") in config["permissions"]  # an implementer
    assert config["plugins"] == [projection.COMPATIBILITY_PLUGIN] and config["share"] == "disabled"
    # the server's environment: the named provider variable, private state, no project config, nothing of AEW's
    assert "OPENAI_API_KEY" in started["env_names"]
    assert not [n for n in started["env_names"] if n.upper().startswith("AEW_")]
    assert started["flags"]["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    for name in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TEMP"):
        assert Path(started["flags"][name]).resolve().is_relative_to(hdir.resolve())
    workspace = os.path.realpath(lab.ok("invoke", "show", inv)["workspace"])
    assert started["cwd"] == workspace
    [session] = fake_db(lab).values()
    info = session["info"]
    assert info["model"] == {"providerID": "fakeprov", "id": "fake-model", "variant": "high"}
    assert info["location"] == {"directory": workspace} and info["permissions"] == config["permissions"]
    assert info["metadata"] == {"aew_invocation": inv, "aew_run": run, "aew_work_unit": wid}
    record = lab.record(run)
    assert record["launch"]["health"]["version"] == "2.0.18" and record["launch"]["health"]["tested"]
    assert record["result"]["effective"] == [{"provider": "fakeprov", "model": "fake-model", "effort": "high"}]
    assert record["model_check"]["status"] == "match" and record["result"]["prompts"] == 1


def test_tool_calls_are_logged_by_name_never_by_input(lab, tmp_path):
    """V2 names a tool in `session.tool.input.started`; `session.tool.called` carries only the call id and input
    (found live in M3 step 8: the log said `"tool": null`). The run's event log names each call's tool and never
    records its input."""
    script(lab, IMPLEMENT)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    called = [e for e in events(lab) if e["event"] == "opencode.session.tool.called"]
    assert [e.get("tool") for e in called] == ["shell"] * len(IMPLEMENT)
    log = (runlog.run_dir(lab.aew_root, run) / "events.jsonl").read_text(encoding="utf-8")
    assert fake_opencode.TOOL_INPUT not in log
    assert lab.record(run)["result"]["tools_called"] == {"shell": len(IMPLEMENT)}


def test_a_read_only_role_gets_no_edit_and_no_web(lab, tmp_path):
    script(lab, IMPLEMENT)
    wid, inv, run = launch(lab, tmp_path)
    lab.wait(run)
    lab.project.lead("work", "transition", wid, "--to", "RUNNING")
    lab.project.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    script(lab, [], key="R-INV-0002-1")
    review = lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")["launch"]["run"]
    lab.wait(review)
    config = json.loads((harness_dir(lab, review) / "opencode-config.json").read_text(encoding="utf-8"))
    assert projection.rule("edit", "deny") in config["permissions"]
    assert projection.rule("edit", "allow") not in config["permissions"]
    assert projection.rule("webfetch", "allow") not in config["permissions"]
    assert "must not modify any file" in config["agents"][projection.AGENT]["system"]


# ---------------------------------------------------------------------------------------------- health


def test_a_slow_model_catalog_is_waited_for(lab, tmp_path):
    script(lab, IMPLEMENT, catalog_delay_s=3)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert lab.record(run)["launch"]["health"]["catalog_wait_s"] >= 2.5


def test_a_launch_behind_a_proxy_runs_and_no_loopback_call_reaches_the_proxy(lab, tmp_path):
    """Every proxy variable set, in both cases, with no NO_PROXY exception for 127.0.0.1: the supervisor's calls to
    the run's own server go direct, so the run ends normally and the proxy (answering 502) sees no connection."""
    with RecordingProxy() as proxy:
        lab.env.update(proxy_env(proxy.url))
        script(lab, IMPLEMENT)
        _, _, run = launch(lab, tmp_path)
        assert lab.wait(run)["status"] == "ended_with_evidence"
    assert (proxy.connections, proxy.request_lines) == (0, [])


def test_a_model_the_harness_does_not_offer_fails_closed(lab, tmp_path):
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, models=[{"id": "cheaper-model", "providerID": "other", "enabled": True, "variants": []}])
    assert "fakeprov/fake-model is not offered" in refused_launch(lab, tmp_path)


def test_a_missing_effort_variant_fails_closed(lab, tmp_path):
    script(lab, IMPLEMENT, models=[{"id": "fake-model", "providerID": "fakeprov", "enabled": True,
                                    "variants": [{"id": "low"}]}])
    assert "no variant 'high'" in refused_launch(lab, tmp_path)


@pytest.mark.parametrize("knobs, expected", [
    ({"version": "1.18.32"}, "is not a V2 server"),
    ({"openapi_drop": ["POST /api/session/{sessionID}/interrupt"]},
     "operation POST /api/session/{sessionID}/interrupt is missing"),
    ({"ignore_config": True}, "did not load AEW's agent"),
    ({"agent_override": {"steps": 5}}, "with a different step limit"),
    ({"agent_override": {"model": {"providerID": "other", "id": "cheaper-model", "variant": "default"}}},
     "with a different model"),
    ({"agent_override": {"permissions": [{"action": "*", "resource": "*", "effect": "allow"}]}},
     "with a different permissions"),
    ({"appended_rules": [{"action": "browser", "resource": "*", "effect": "allow"}]},
     "with a different permissions"),
    ({"appended_rules": [{"action": "shell", "resource": "*", "effect": "ask"}]},
     "with a different permissions"),
], ids=["v1-server", "doctored-openapi", "config-ignored", "steps-differ", "model-differs", "rules-differ",
        "appended-allow", "appended-ask"])
def test_an_incompatible_server_fails_closed(lab, tmp_path, knobs, expected):
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, **knobs)
    assert expected in refused_launch(lab, tmp_path)


def test_a_denial_the_server_appends_after_aews_rules_is_accepted(lab, tmp_path):
    """E17: OpenCode 2.0.22 appends a default `browser: deny` after AEW's rules. It can only narrow access, so the
    projection still holds and the run proceeds."""
    script(lab, IMPLEMENT, appended_rules=[{"action": "browser", "resource": "*", "effect": "deny"}])
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"


def test_a_run_server_with_stored_credentials_is_refused(lab, tmp_path):
    """E17: 2.0.22 serves stored integration credentials, values included, and the agent can reach its server. A run's
    server state starts empty; AEW proves it at launch, and refuses a server that holds any."""
    lab.env["AEW_OPENCODE_CATALOG_SETTLE_S"] = "1"
    script(lab, IMPLEMENT, stored_credentials=[{"id": "github", "type": "oauth", "access": "gho_example"}])
    assert "holds 1 stored credential" in refused_launch(lab, tmp_path)


def test_an_empty_credential_store_is_recorded(lab, tmp_path):
    script(lab, IMPLEMENT, stored_credentials=[])
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert lab.record(run)["launch"]["health"]["stored_credentials"] == 0


# ---------------------------------------------------------------------------------------------- completion


def test_losing_the_event_stream_changes_nothing(lab, tmp_path):
    """Every event connection closes after its first frame: completion is still decided correctly (by polling)."""
    script(lab, IMPLEMENT, drop_events_every=1)
    wid, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    record = lab.record(run)
    assert record["result"]["events_dropped"] >= 1
    assert {e["kind"] for e in evidence_of(lab, wid, run)} >= {"implementation_report"}


def test_a_message_queued_at_the_turn_boundary_is_answered_before_the_run_ends(lab, tmp_path):
    """The server goes idle while a prompt AEW queued during the turn is still undelivered, then starts it: the run
    must not be declared over in between."""
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "wait_file", "path": str(sync / "go")}],
           idle_before_queue_s=3)
    _, _, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    lab.ok("harness", "send", run, "--text", "Also note the changed files.", "--token", lab.project.token)
    lab.until(lambda: any(e["event"] == "opencode.prompt" and e["delivery"] == "queue" for e in events(lab)),
              what="the message queued")
    (sync / "go").write_text("x")
    assert lab.wait(run)["status"] == "ended_without_evidence"
    [session] = fake_db(lab).values()
    users = [m for m in session["messages"] if m["type"] == "user"]
    assert users[-1]["text"] == "Also note the changed files."
    assert session["messages"][-1]["type"] == "idle" and session["messages"][-2]["type"] == "assistant"
    assert lab.record(run)["result"]["prompts"] == 2


def test_a_lead_interrupt_holds_the_session_until_send(lab, tmp_path):
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "hang"}])
    _, _, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    lab.ok("harness", "interrupt", run, "--token", lab.project.token)
    lab.until(lambda: any(e["event"] == "opencode.held" for e in events(lab)), what="the session held")
    assert lab.ok("harness", "status")["runs"][0]["status"] == "running"
    lab.ok("harness", "send", run, "--text", "Continue and finish.", "--token", lab.project.token)
    assert lab.wait(run)["status"] == "ended_without_evidence"
    kinds = [t.get("kind") for t in lab.record(run)["timeline"] if t["event"] == "request"]
    assert kinds == ["interrupt", "send"]


# ---------------------------------------------------------------------------------------------- the unexpected


def test_a_permission_request_is_rejected_and_recorded(lab, tmp_path):
    script(lab, IMPLEMENT, ask=True)
    wid, _, run = launch(lab, tmp_path)
    done = lab.wait(run)
    record = lab.record(run)
    assert done["status"] == "crashed" and "interrupted" in record["harness_outcome"]
    assert record["result"]["permission_rejected"] == [{"action": "shell", "resources": ["rm -rf /"]}]
    assert not evidence_of(lab, wid)


def test_a_subagent_session_is_never_invisible(lab, tmp_path):
    """Brief attack 7: `subagent` is denied, and a session started anyway (by the model or anything else) is recorded
    on the run and shown by `aew harness status`: nothing runs for the invocation unseen."""
    script(lab, IMPLEMENT, subagent=True)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    [child] = lab.record(run)["result"]["foreign_sessions"]
    assert child != lab.record(run)["launch"]["session"]
    assert lab.ok("harness", "status")["runs"][0]["foreign_sessions"] == [child]


def test_a_form_is_cancelled_and_the_run_continues(lab, tmp_path):
    script(lab, IMPLEMENT, form=True)
    _, _, run = launch(lab, tmp_path)
    assert lab.wait(run)["status"] == "ended_with_evidence"
    assert len(lab.record(run)["result"]["forms_cancelled"]) == 1


def test_the_server_dying_mid_run_is_a_crash(lab, tmp_path):
    sync = sync_dir(tmp_path)
    script(lab, [{"do": "touch", "path": str(sync / "ready")}, {"do": "wait_file", "path": str(sync / "go")},
                 {"do": "exit", "code": 9}])
    _, inv, run = launch(lab, tmp_path)
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    rev = lab.project.rev()
    (sync / "go").write_text("x")
    assert lab.wait(run)["status"] == "crashed"
    record = lab.record(run)
    assert record["exit_code"] == 9 and "server exited (9)" in record["harness_outcome"]
    assert lab.project.rev() == rev and lab.ok("invoke", "show", inv)["status"] == "active"


# ---------------------------------------------------------------------------------------------- Lead requests


def test_send_refuses_a_credential_and_a_run_that_is_not_running(lab, tmp_path):
    script(lab, [{"do": "exit", "code": 0}])
    _, _, run = launch(lab, tmp_path)
    lab.wait(run)
    res = lab.aew("harness", "send", run, "--text", f"use {lab.project.token}", "--token", lab.project.token)
    assert res.error["code"] == "USAGE" and lab.project.token not in res.stderr
    res = lab.aew("harness", "send", run, "--text", "hello", "--token", lab.project.token)
    assert res.error["code"] == "ILLEGAL_TRANSITION"


def test_harness_config_prints_the_projection_without_secrets(lab, tmp_path):
    script(lab, IMPLEMENT)
    _, inv, run = launch(lab, tmp_path)
    lab.wait(run)
    out = lab.aew("harness", "config", "opencode", inv)
    assert out.returncode == 0 and PROVIDER_SECRET not in out.stdout and not credential_hits(tmp_path)
    shown = out.json
    used = json.loads((harness_dir(lab) / "opencode-config.json").read_text(encoding="utf-8"))
    assert shown["for_run"] == "R-INV-0001-2"  # the next run: the same rules, its own private output directories
    # The run's own private output directories and scratch directory come last.
    assert shown["config"]["permissions"][:-4] == used["permissions"][:-4]
    assert all("R-INV-0001-2" in r["resource"] for r in shown["config"]["permissions"][-4:])
    assert shown["session"]["model"] == {"providerID": "fakeprov", "id": "fake-model", "variant": "high"}
    assert shown["server_env"]["provider_variables"] == ["OPENAI_API_KEY"]
    lead = lab.ok("harness", "config", "opencode", "--lead")
    from aew.engine.api import Engine

    assert lead["config"] == projection.lead_config(Engine.discover(lab.root).lead_guide())
    assert "OPENAI_API_KEY" not in lead["env_names"] and "AEW_LEAD_TOKEN" not in lead["env_names"]


@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="/proc: Linux only")
def test_residual_the_harness_servers_environment_is_readable_from_the_agents_shell(lab, tmp_path):
    """ADR-0009 residual (independent review, area 2, F3), asserted as it is rather than as hoped. The agent's own
    environment carries no provider secret and no server password, but the harness server is its shell's parent, runs
    as the same user and, contained or not, in the same PID namespace: its environment (the provider key the policy
    names, the server password) is one read of /proc/<parent>/environ away. No AEW credential is ever there. Closing
    this needs the server outside the agent's user or namespace (register); until then it is documented, and this
    test fails the day it stops being true, so the ADR is updated with it."""
    script(lab, [{"do": "read_parent_environ", "pid": "ppid", "names": ["OPENAI_API_KEY", "OPENCODE_PASSWORD"]}])
    launch(lab, tmp_path)
    lab.wait(RUN)
    parent = lab.step(RUN, 0)
    assert parent["readable"] is True, parent
    assert parent["names_present"] == ["OPENAI_API_KEY", "OPENCODE_PASSWORD"], parent
    assert parent["has_credential"] is False and parent["has_lead_var"] is False
