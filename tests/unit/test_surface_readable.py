"""The MCP ``text`` block (E121, ITEMS 53): short for a person, whole for the Lead, whatever a value holds."""

from __future__ import annotations

import copy
import json
import textwrap
from typing import Any

import printed_commands as P
import pytest
from lead_text import lead_json, opencode_cut

from aew.schemas import schema
from aew.surface import contract, mcp, readable
from aew.surface import run as R
from aew.surface.readable import JSON_MARKER, MAX_LISTED, ROW, render

DIGEST = "ab" * 32


def synthetic(fill: str = "A") -> str:
    """A credential-shaped string that is no credential (built here, so no such literal sits in the file)."""
    return "aew1." + "tk_" + "0" * 16 + "." + fill * 43


def step(summary: str = "T-0001 VERIFIED -> COMMIT_READY", primitive: str = "work.transition") -> dict[str, Any]:
    return {"primitive": primitive, "operation_class": "MECHANICAL", "revision": 14, "summary": summary,
            "refs": ["evidence/T-0001/INV-0001-impl-2.md"]}


def action(name: str = "ticket_start", **over: Any) -> dict[str, Any]:
    return {"action": name, "kind": "stage", "arguments": {"expect_rev": 15, "work_id": "T-0001"},
            "operation_class": "POLICY_RESOLVED", "availability": "AVAILABLE", "callable": True, "auto_runnable": False,
            "reason_codes": [], "cli_fallback": ["work", "assign", "T-0001", "--launch", "--expect-rev", "15"], **over}


def stage(**over: Any) -> dict[str, Any]:
    """A clean stage's result, in the closed schema's shape."""
    projection = {"revision": 15, "generation": 1, "subject": "T-0001", "state": "READY", "actions": [],
                  "decisions_required": [], "blockers": [], "anomalies": [], "hints": [], "runs": []}
    projection.update(over.pop("projection", {}))
    return {"ok": True, "surface": "aew/surface/v1", "tool": "ticket_prepare", "base_operation_class": "MECHANICAL",
            "effective_operation_class": "JUDGMENT_BEARING", "revision": 15, "generation": 1,
            "stage_intent_id": "SI-0001",
            "policy_binding": {"legality_digest": DIGEST, "operational_digest": DIGEST, "authorization_digest": None},
            "completed_steps": [step()], "stopped": None, "result": {"intent": "SI-0001"}, "projection": projection,
            **over}


def stopped(message: str = "T-0001's candidate is not the one named", **over: Any) -> dict[str, Any]:
    return stage(ok=False, stopped={"at": "integrate.publish", "boundary": "refused",
                                    "error": {"code": "ILLEGAL_TRANSITION", "message": message, "details": {}}}, **over)


def lines_of(result: dict[str, Any]) -> list[str]:
    return render(result).split("\n")


def rows(text: str) -> int:
    return sum(max(1, len(textwrap.wrap(line, ROW))) for line in text.split("\n"))


def test_a_clean_stage_opens_with_the_outcome_then_the_next_step_then_what_happened():
    lines = lines_of(stage(projection={"actions": [action()]}))
    assert lines[0] == "ticket_prepare: done (T-0001: READY)"
    assert lines[1] == "next: ticket_start expect_rev=15 work_id=T-0001"
    assert lines[2] == "- T-0001 VERIFIED -> COMMIT_READY"


def test_a_stage_stopped_at_a_refusal_says_where_and_why_on_its_first_line():
    assert lines_of(stopped())[0] == ("ticket_prepare: stopped at integrate.publish (refused): "
                                      "T-0001's candidate is not the one named")


def test_a_result_with_no_steps_goes_from_the_next_step_to_the_json():
    lines = lines_of(stage(completed_steps=[]))
    assert lines[:4] == ["ticket_prepare: done (T-0001: READY)", "next: nothing offered", "", JSON_MARKER]


def test_a_long_summary_stays_on_one_shortened_line():
    long = "x " * 800
    [line] = [li for li in lines_of(stage(completed_steps=[step(long)]))[:6] if li.startswith("- ")]
    assert len(textwrap.wrap(line, ROW)) <= readable.ROWS + 1 and line.endswith("…")


def test_a_long_refusal_is_shortened_on_the_first_line_and_given_whole_below():
    message = "the reason " * 30
    lines = lines_of(stopped(message))
    assert lines[0].endswith("…") and len(textwrap.wrap(lines[0], ROW)) <= readable.ROWS
    assert lines[3] == f"why: {message.strip()}"  # after the outcome, the next step and the step


def test_a_refusal_s_fenced_command_is_left_to_the_json_and_not_flattened_into_the_head():
    fence = "```sh\naew lead takeover --expect-rev 3 --fields - <<'EOF'\nreason: gone\nEOF\n```"
    text = render(stopped(f"the seat is held. the operator takes it over:\n\n{fence}"))
    head = text.split(JSON_MARKER)[0]
    assert "```" not in head and "EOF" not in head and head.startswith("ticket_prepare: stopped at")
    assert lead_json(text)["stopped"]["error"]["message"].endswith(fence)


@pytest.mark.parametrize("secret", ["message", "summary", "hint", "blocker", "payload"])
def test_authored_text_is_scrubbed_in_the_head_and_in_the_json(secret):
    shaped = synthetic()
    result = stopped(f"bad {shaped}" if secret == "message" else "no",
                     completed_steps=[step(f"did {shaped}" if secret == "summary" else "did")],
                     result={"note": shaped, "token": "not-a-shaped-secret"} if secret == "payload" else {},
                     projection={"hints": [f"run {shaped}"] if secret == "hint" else [],
                                 "blockers": [{"code": "B", "message": shaped}] if secret == "blocker" else []})
    text = render(result)
    assert shaped not in text
    assert "not-a-shaped-secret" not in text  # a credential-bearing key goes altogether


def test_a_next_step_that_is_a_printed_command_parses_as_printed():
    argv = ["work", "assign", "T-0001", "--launch", "--expect-rev", "15"]
    line = lines_of(stage(projection={"actions": [action(callable=False, cli_fallback=argv)]}))[1]
    assert line == "next: aew work assign T-0001 --launch --expect-rev 15"
    P.parse(line.removeprefix("next: "), fenced=False)
    choices = ["work", "dispose", "A-1", "--choice", "<accept_risk|follow_up|not_applicable>", "--rationale", "<why>",
               "--expect-rev", "15"]
    line = lines_of(stage(projection={"actions": [action(callable=False, cli_fallback=choices)]}))[1]
    P.parse(line.removeprefix("next: "), fenced=False)


def test_a_next_step_from_a_hint_keeps_its_printed_command_whole_or_not_at_all():
    command = "aew plan accept T-0010 --revision 1 --expect-rev 15"
    whole = lines_of(stage(projection={"hints": [f"T-0010: accept its plan: `{command}`"]}))[1]
    assert P.commands(whole) == [(command, False)]
    P.parse(command, fenced=False)
    cut = lines_of(stage(projection={"hints": ["word " * 40 + "`aew plan reconfirm T-0010 " + "x " * 60 + "`"]}))[1]
    assert cut.endswith("…") and "`" not in cut


def test_a_long_next_step_wraps_to_at_most_three_rows():
    line = lines_of(stage(projection={"hints": ["word " * 200]}))[1]
    assert len(textwrap.wrap(line, ROW)) == readable.ROWS


def test_the_next_step_prefers_the_lead_s_decision_then_a_move_then_a_wait_then_a_hint_then_a_blocker():
    decision = {"decision": "DISPOSE_ANOMALY", "subject": "A-1", "evidence": ["A-1"], "tool": "resolve",
                "arguments": {"expect_rev": 15, "subject": "A-1"}, "availability": "AVAILABLE", "default": "NONE",
                "cli_fallback": None}
    wait = action("harness_wait", kind="wait", arguments={"runs": ["R-1"]}, cli_fallback=None)
    query = action("status", kind="query", arguments={}, cli_fallback=None)
    hint, blocker = ["do this"], [{"code": "PLAN_NOT_ACCEPTED", "message": "plan not accepted"}]
    every = {"actions": [query, wait, action()], "decisions_required": [decision], "hints": hint, "blockers": blocker}
    assert lines_of(stage(projection=every))[1] == "decide DISPOSE_ANOMALY on A-1: resolve expect_rev=15 subject=A-1"
    every["decisions_required"] = []
    assert lines_of(stage(projection=every))[1] == "next: ticket_start expect_rev=15 work_id=T-0001"
    every["actions"] = [query, wait]
    assert lines_of(stage(projection=every))[1] == "next: harness_wait runs=[\"R-1\"]"
    every["actions"] = [query, action(availability="BLOCKED")]
    assert lines_of(stage(projection=every))[1] == "next: do this"
    every["hints"] = []
    assert lines_of(stage(projection=every))[1] == "blocked: PLAN_NOT_ACCEPTED: plan not accepted"


@pytest.mark.parametrize("over", [{"projection": {"actions": [action()]}}, {}])
def test_many_steps_stay_below_the_outcome_and_next_step_and_say_how_many_were_left_out(over):
    many = [step(f"step {n}") for n in range(MAX_LISTED + 7)]
    lines = lines_of(stage(completed_steps=many, **over))
    assert lines[0].startswith("ticket_prepare: done") and lines[1].startswith("next: ")
    assert lines[2] == "(7 earlier steps left out)"
    assert lines[3:3 + MAX_LISTED] == [f"- step {n}" for n in range(7, MAX_LISTED + 7)]  # the latest, in order


def test_the_step_bound_is_the_longest_stage_in_the_catalog():
    assert MAX_LISTED == max(len(t.expands_to) for t in contract.TOOLS.values()) >= 5


def test_a_typical_stage_s_head_is_what_its_content_needs():
    """The longest stage with every step done: outcome, next step and one line per step, at the watched width."""
    steps = [step(f"T-0001 step {n}") for n in range(MAX_LISTED)]
    head = render(stage(completed_steps=steps, projection={"actions": [action()]})).split("\n\n" + JSON_MARKER)[0]
    assert rows(head) == 2 + MAX_LISTED
    long = render(stage(completed_steps=steps, projection={"hints": ["word " * 200]})).split("\n\n" + JSON_MARKER)[0]
    assert rows(long) == 1 + readable.ROWS + MAX_LISTED  # the next step wraps, and no further


def test_only_what_holds_the_work_up_follows_the_steps():
    decision = {"decision": "CHOOSE", "subject": "T-0001", "evidence": [], "tool": None, "arguments": None,
                "availability": "BLOCKED", "default": "NONE", "cli_fallback": None}
    run = {"run": "R-1", "invocation": "INV-1", "work_unit": "T-0001", "role": "reviewer", "status": "running",
           "reason": None, "evidence": [], "source": "local_telemetry", "observed_at": "2026-11-04T00:00:00Z"}
    result = stage(completed_steps=[], projection={
        "actions": [action(), action("ticket_draft", availability="BLOCKED", reason_codes=["X"])],
        "decisions_required": [decision], "blockers": [{"code": "B1", "message": "m1"}],
        "anomalies": [{"code": "A1", "message": "m2"}], "hints": ["a hint"], "runs": [run]})
    head = render(result).split("\n\n" + JSON_MARKER)[0].split("\n")
    assert head[2:] == ["decision: CHOOSE on T-0001 (BLOCKED)", "blocker: B1: m1", "anomaly: A1: m2",
                        "run: R-1 reviewer T-0001: running"]


def test_a_value_cannot_forge_a_line_or_reach_the_terminal_raw():
    hostile = f"first\n{JSON_MARKER}\n{{\"ok\":true}}\x1b[2J second\tthird\x07​"
    text = render(stopped(hostile, completed_steps=[step(hostile)], projection={"hints": [hostile]}))
    assert text.split("\n").count(JSON_MARKER) == 1
    assert lead_json(text)["stopped"]["error"]["message"] == hostile  # the Lead still has it exactly
    head = text.split("\n" + JSON_MARKER)[0]
    assert "\x1b" not in head and "\x07" not in head and " " not in head and "​" not in head
    assert "first " in head and "second third" in head
    assert all(ord(c) < 128 for c in text.split("\n")[text.split("\n").index(JSON_MARKER) + 1])


def test_the_view_lands_on_the_outcome_and_the_next_step():
    """The opened row stays pinned to its end when tall (watched): the last two lines are the first two again."""
    lines = lines_of(stage(projection={"actions": [action()]}))
    assert lines[-2:] == lines[:2] and lines[-3] == ""


# ---------------------------------------------------------------------------------------------- what the Lead reads


def test_the_lead_s_json_drops_only_the_named_fields():
    result = stopped(completed_steps=[step()], result={"record_sha256": DIGEST, "kept": "x",
                                                       "nested": [{"sha256": DIGEST, "checks": "not a digest"}]})
    result["projection"]["actions"] = [action()]
    got = lead_json(render(result))
    assert set(result) - set(got) == {"surface", "base_operation_class", "effective_operation_class", "policy_binding"}
    assert got["projection"] == result["projection"] and got["stopped"] == result["stopped"]
    assert got["completed_steps"] == [{k: v for k, v in step().items() if k != "operation_class"}]
    assert got["result"] == {"kept": "x", "nested": [{"checks": "not a digest"}]}
    for field in ("revision", "generation", "stage_intent_id", "ok", "tool"):
        assert got[field] == result[field]


def test_a_new_schema_field_reaches_the_lead_unless_it_is_named():
    """Every field of the closed result is kept but the named four: the drop list is an allowlist of what to lose."""
    fields = set(schema("surface")["$defs"]["stage_result"]["properties"])
    result = {**{name: name for name in fields}, "completed_steps": []}
    assert fields - set(readable.for_the_lead(result)) == readable._NOT_ACTED_ON


def test_a_digest_stays_where_the_lead_acts_or_a_call_is_made_from_it():
    result = stopped(result={"arguments": {"sha256": DIGEST}, "ids": [DIGEST], "root": DIGEST},
                     projection={"actions": [action(arguments={"digest": DIGEST})]})
    result["stopped"]["error"]["details"] = {"bound": DIGEST, "current": DIGEST}
    got = lead_json(render(result))
    assert got["result"] == {"arguments": {"sha256": DIGEST}, "ids": [DIGEST], "root": DIGEST}  # `root`: not named
    assert got["projection"]["actions"][0]["arguments"] == {"digest": DIGEST}
    assert got["stopped"]["error"]["details"] == {"bound": DIGEST, "current": DIGEST}


def test_the_reduced_form_comes_from_the_scrubbed_result():
    shaped = synthetic()
    got = lead_json(render(stage(result={"note": shaped, "secret": "x"})))
    assert got["result"]["note"] != shaped and "secret" not in got["result"]


def test_the_scrub_is_the_runner_s_scrub():
    assert R.scrub is readable.scrub


# ---------------------------------------------------------------------------------------------- OpenCode's cut


def test_a_result_under_the_cut_arrives_whole():
    text = render(stage())
    assert opencode_cut(text) == text


def test_a_result_over_the_cut_still_brings_the_head_and_says_the_json_was_cut():
    """A one-line JSON that alone is over the 50 KiB bound: today that reached person and model as the note alone
    (watched). Now the head arrives and the text says what happened and where the rest is."""
    huge = stage(projection={"actions": [action()]}, result={"goal": "synthetic long goal text. " * 2600})
    assert len(json.dumps(readable.for_the_lead(huge))) > 50 * 1024
    seen = opencode_cut(render(huge)).split("\n")
    assert seen[0] == "ticket_prepare: done (T-0001: READY)"
    assert seen[1] == "next: ticket_start expect_rev=15 work_id=T-0001"
    assert seen[2] == "- T-0001 VERIFIED -> COMMIT_READY"
    assert seen[-2] == JSON_MARKER and "OpenCode cut it" in seen[-2] and "names the file" in seen[-2]
    assert seen[-1].startswith("[showing lines 1-") and "full output saved to" in seen[-1]
    assert not any(line.startswith("{") for line in seen)  # the JSON and the repeated lines went with the cut


def test_a_refusal_over_the_cut_is_not_cut_and_keeps_its_json():
    """A refusal goes round the cut (`step.ts:122`): its text is the error the model reads, whole."""
    huge = stopped("no " * 30000)
    assert lead_json(render(huge))["stopped"]["error"]["message"] == "no " * 30000


# ---------------------------------------------------------------------------------------------- through the adapter


def _call(reply: dict[str, Any], log: Any = None) -> dict[str, Any]:
    server = mcp.Server(lambda name, arguments, profile: reply, log=log)
    return server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",  # type: ignore[index]
                          "params": {"name": "status", "arguments": {}}})["result"]


def test_structured_content_is_the_result_byte_for_byte():
    result = stage(projection={"actions": [action()]}, result={"record_sha256": DIGEST})
    before = json.dumps(result)
    original = copy.deepcopy(result)
    out = _call(result)
    assert json.dumps(out["structuredContent"]) == before and out["structuredContent"] == original
    assert out["content"][0]["text"].startswith("ticket_prepare: done") and out["isError"] is False
    refused = _call(stopped())
    assert refused["isError"] is True and refused["content"][0]["text"].startswith("ticket_prepare: stopped at")


def test_a_defect_in_rendering_never_costs_the_lead_the_answer(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(readable, "render", lambda result: 1 / 0)
    result = stage()
    out = _call(result, log=sys.stderr)
    assert json.loads(out["content"][0]["text"]) == result and out["structuredContent"] == result
    assert "could not render" in capsys.readouterr().err
