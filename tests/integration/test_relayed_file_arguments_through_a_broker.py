"""A relayed Lead command takes bytes, through a real broker: the ``aew`` client reads a file argument and sends its
text, the Lead's flows go on working, and the broker refuses a path from anything that sends one, in its own process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from aewflow import create_planned_ticket, sample_project
from conftest import clean_env

from aew import errors
from aew.engine.api import Engine
from aew.harness import bridge, lead_broker
from aew.surface import run
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()
PROBE = Path(__file__).parents[1] / "helpers" / "relayed_opens.py"


@pytest.fixture
def held(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    broker = lead_broker.LeadBroker(engine, p.token)
    broker.start()
    for name, value in broker.env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("AEW_LEAD_TOKEN", raising=False)
    yield p, wid, engine, broker
    broker.close()


def _rev(engine) -> int:
    return engine.store.read()["revision"]


def _handoff(engine) -> str:
    return (engine.aew_root / "state" / "HANDOFF.md").read_text(encoding="utf-8")


def _create(p, engine, broker, *more):
    """A Ticket created as the Lead's shell creates one: no credential, through the broker."""
    res = p.aew("work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g", "--contract", "c",
                "--scope", "calc/**", *more, "--expect-rev", str(_rev(engine)), env=clean_env(broker.env))
    assert res.returncode == 0, res.stderr
    return res.json["id"]


def _relay(argv, cwd, stdin=""):
    return bridge.call("lead.cli", {"argv": argv, "cwd": str(cwd), "stdin": stdin}, env_names=lead_broker.ENV_NAMES)


# ------------------------------------------------------------------------------------------- the Lead's flows


def test_a_file_the_lead_wrote_in_the_project_goes_through_the_client(held):
    p, wid, engine, broker = held
    (p.root / "note.md").write_bytes(b"a note the Lead wrote\n")
    res = p.aew("checkpoint", "--next", "x", "--note-file", "note.md", "--expect-rev", str(_rev(engine)),
                env=clean_env(broker.env))
    assert res.returncode == 0, res.stderr
    assert "a note the Lead wrote" in _handoff(engine)


def test_a_note_piped_with_a_dash_goes_through_the_client(held):
    p, wid, engine, broker = held
    res = p.aew("checkpoint", "--next", "x", "--note-file", "-", "--expect-rev", str(_rev(engine)),
                env=clean_env(broker.env), input="a piped note\n")
    assert res.returncode == 0, res.stderr
    assert "a piped note" in _handoff(engine)


def test_a_plan_from_a_file_or_a_dash_is_proposed_through_the_client(held):
    p, _, engine, broker = held
    env = clean_env(broker.env)
    wid = _create(p, engine, broker)
    (p.root / "plan.md").write_bytes(b"# A plan from a file\n")
    res = p.aew("plan", "propose", wid, "--file", "plan.md", "--assurance", "none", "--expect-rev", str(_rev(engine)),
                env=env)
    assert res.returncode == 0, res.stderr
    res = p.aew("plan", "propose", wid, "--file", "-", "--assurance", "none", "--expect-rev", str(_rev(engine)),
                env=env, input="# A plan from stdin\n")
    assert res.returncode == 0, res.stderr


def test_a_ticket_body_from_a_file_goes_through_the_client(held):
    p, _, engine, broker = held
    (p.root / "body.md").write_bytes(b"the body from a file\n")
    wid = _create(p, engine, broker, "--body-file", "body.md")
    assert "the body from a file" in (engine.aew_root / "work" / wid / "ticket.md").read_text(encoding="utf-8")


def test_fields_from_a_file_are_expanded_by_the_client(held):
    p, wid, engine, broker = held
    (p.root / "fields.yaml").write_bytes(b"next: from a file\nnote-file: note.md\n")
    (p.root / "note.md").write_bytes(b"its note\n")
    res = p.aew("checkpoint", "--fields", str(p.root / "fields.yaml"), "--expect-rev", str(_rev(engine)),
                env=clean_env(broker.env))
    assert res.returncode == 0, res.stderr
    assert engine.store.read()["next_action"] == "from a file" and "its note" in _handoff(engine)


def test_a_file_the_client_cannot_read_stops_the_command_there(held):
    p, wid, engine, broker = held
    rev = _rev(engine)
    res = p.aew("checkpoint", "--next", "x", "--note-file", "gone.md", "--expect-rev", str(rev),
                env=clean_env(broker.env))
    assert res.returncode != 0 and "cannot read" in res.stderr and "gone.md" in res.stderr
    assert _rev(engine) == rev


# ---------------------------------------------------------------------------------------- the broker's refusal


@pytest.mark.parametrize("argv", [
    ["checkpoint", "--next", "x", "--note-file", "{file}"],
    ["checkpoint", "--next", "x", "--note-file={file}"],
    ["checkpoint", "--next", "x", "--note", "{file}"],
    ["checkpoint", "--fields", "{file}"],
    ["checkpoint", "--fields={file}"],
    ["work", "create", "ticket", "--title", "t", "--class", "1", "--goal", "g", "--contract", "c", "--scope", "c/**",
     "--body-file", "{file}"],
    ["plan", "propose", "{wid}", "--file", "{file}", "--assurance", "none"],
])
def test_the_broker_refuses_a_path_on_the_relay_naming_the_dash_and_stores_nothing_of_it(held, argv):
    p, wid, engine, broker = held
    rev = _rev(engine)
    content = "content only this file holds"
    target = p.root / "given.txt"
    target.write_text(f"next: {content}\n", encoding="utf-8")
    sent = [a.replace("{file}", str(target)).replace("{wid}", wid) for a in argv] + ["--expect-rev", str(rev)]
    with pytest.raises(errors.UsageError, match="give - as the file") as refused:
        _relay(sent, p.root)
    assert refused.value.details["reason"] == "relayed_path"
    assert _rev(engine) == rev
    assert content not in json.dumps(engine.store.read())
    handoff = engine.aew_root / "state" / "HANDOFF.md"
    assert not handoff.exists() or content not in handoff.read_text(encoding="utf-8")


def test_the_broker_takes_the_text_a_client_sends_with_a_dash(held):
    p, wid, engine, broker = held
    out = _relay(["checkpoint", "--next", "x", "--note-file=-", "--expect-rev", str(_rev(engine))], p.root,
                 stdin="sent as bytes")
    assert out["result"]
    assert "sent as bytes" in _handoff(engine)


def test_a_harness_message_from_a_path_is_refused_by_the_broker_too(held):
    p, wid, engine, broker = held
    with pytest.raises(errors.UsageError, match="give - as the file"):
        _relay(["harness", "send", "R-1", "--file", str(p.root / "message.md")], p.root)


def test_a_stage_intent_is_found_by_its_id_alone(tmp_path):
    p = sample_project(tmp_path)
    engine = Engine.discover(p.root)
    records = engine.aew_root / "records" / "stage-intents"
    records.mkdir(parents=True, exist_ok=True)
    (engine.aew_root / "beside.yaml").write_text("id: SI-0001\n", encoding="utf-8")
    for name in ("../../beside", str(engine.aew_root / "beside")):
        with pytest.raises(errors.NotFound, match="no stage intent"):
            engine.stage_intent(name)
    (engine.aew_root / "records" / "dispositions").mkdir(parents=True, exist_ok=True)
    with pytest.raises(errors.NotFound, match="no disposition"):
        engine.disposition("../../beside")
    out = run.run_tool(engine, CTX, "resolve", {"subject": "../../beside", "choice": "abandon", "rationale": "r",
                                                "expect_rev": _rev(engine)}, token=p.token)
    assert not out["ok"] and out["stopped"]["error"]["code"] == "NOT_FOUND", out["stopped"]


# ------------------------------------------------------------------------------------- what the broker opens


# What a row may do with its value, and why: `git rev-parse` resolves a revision, and refuses an option-shaped one.
MAY_TOUCH = {("map generate", "--commit"): {"subprocess.Popen"}}


def _walk(tmp_path, *more):
    """The walk, in a process of its own, with no way to start a real harness."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    done = subprocess.run(
        [sys.executable, "-B", str(PROBE), str(p.root), p.token, wid, str(tmp_path / "values"), *more],
        capture_output=True, text=True, cwd=p.root, stdin=subprocess.DEVNULL, timeout=540,
        env={**clean_env({}), "PYTHONPATH": os.pathsep.join(q for q in sys.path if q),
             "AEW_OPENCODE_BIN": str(tmp_path / "no-such-harness")},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.splitlines()[-1])


def test_no_relayed_command_or_typed_tool_touches_a_path_it_is_given_in_any_one_argument(tmp_path):
    """Each argument alone, on the command's required arguments: what the parser walks cannot see, an argument whose
    name says nothing. The walk's own docstring says what it does not see."""
    report = _walk(tmp_path)
    touched = [(r["command"], r["argument"], r["events"]) for r in report["rows"]
               if r["events"] and not set(r["events"]) <= MAY_TOUCH.get((r["command"], r["argument"]), set())]
    assert touched == []
    assert report["commands"] >= 50 and len(report["rows"]) >= 200  # it walked the command set, not a part of it
    assert {r["route"] for r in report["rows"]} == {"lead.cli", "lead.tool"}
    # A row that never parsed proves nothing: this is how a walk comes to reach less than it says.
    assert [(r["command"], r["argument"], r["outcome"]) for r in report["rows"]
            if "invalid command" in r["outcome"]] == []


@pytest.mark.parametrize(("plant", "words"), [("open", ["open"]), ("exists", ["stat", "exists"])])
def test_the_walk_fails_on_a_silent_argument_read_through_a_helper(tmp_path, plant, words):
    """Planted: `checkpoint --attachment`, no help text, read by a helper, directly or behind a check it exists."""
    report = _walk(tmp_path, "--only", "checkpoint", "--plant", plant)
    rows = [r for r in report["rows"] if r["argument"] == "--attachment"]
    assert rows and all(any(word in e for e in r["events"] for word in words) for r in rows), rows
