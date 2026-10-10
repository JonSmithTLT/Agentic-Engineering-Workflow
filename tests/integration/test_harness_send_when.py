"""`aew harness send --when next-step|turn-end` against fake V2 (register E55; F9-A plan v4 amendment 2 §3.1, §3.3,
§4): the default is `next-step`, posted as `steer`; with messaging off no Lead path posts `queue` and `turn-end` is
refused; with messaging on, or when the project's switch and the run's launch snapshot disagree, every send is refused.
A refusal writes nothing: no request file, no control-state change, no POST.

The route's matrix and the help are unit-tested in `tests/unit/test_harness_send_timing.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket
from fake_harness import HarnessLab, credential_hits
from harness_conformance import FakeOpenCodeDriver, sync_dir

from aew import util
from aew.engine import harness_ops
from aew.engine.api import Engine
from aew.errors import AEWError
from aew.harness import lead_broker, runlog
from aew.policy import execution as X
from aew.surface import client

EXECUTION = ".aew/policy/execution.yaml"


@pytest.fixture
def lab(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()
    assert not credential_hits(tmp_path), "a credential string was left in a file"


def launch_held_open(lab: HarnessLab, tmp_path: Path) -> str:
    """A run whose turn is under way and stays so until the test writes ``sync/go``."""
    sync = sync_dir(tmp_path)
    lab.script("R-INV-0001-1", {"steps": [{"do": "touch", "path": str(sync / "ready")},
                                          {"do": "wait_file", "path": str(sync / "go"), "timeout": 300}]})
    wid = create_planned_ticket(lab.project, tmp_path)
    run = lab.lead("work", "assign", wid, "--launch")["launch"]["run"]
    lab.until(lambda: (sync / "ready").exists(), what="the turn is under way")
    return run


def release(tmp_path: Path) -> None:
    (sync_dir(tmp_path) / "go").write_text("x", encoding="utf-8")


def posted(lab: HarnessLab, run: str) -> list[dict[str, Any]]:
    """Every prompt fake V2 received for the run's session, in order (the first is the launch contract)."""
    path = runlog.run_dir(lab.aew_root, run) / "harness" / "xdg-data" / "opencode" / "fake-db.json"
    db = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return [p for s in db.values() for p in s.get("prompts") or []]


def lead_posts(lab: HarnessLab, run: str) -> list[str | None]:
    return [p["delivery"] for p in posted(lab, run)[1:]]


def prompt_events(lab: HarnessLab, run: str) -> list[dict[str, Any]]:
    path = runlog.run_dir(lab.aew_root, run) / "events.jsonl"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return [e for e in map(json.loads, text[:text.rfind("\n") + 1].splitlines()) if e["event"] == "opencode.prompt"]


def written(lab: HarnessLab, run: str) -> tuple[bytes, list[str], list[Any]]:
    """What a send could write: control state, the run's `requests/` directory and its control-state request entries."""
    control = (lab.aew_root / "state" / "control.yaml").read_bytes()
    queue = runlog.run_dir(lab.aew_root, run) / "requests"
    files = sorted(p.name for p in queue.iterdir()) if queue.is_dir() else []
    state = Engine.discover(lab.root).store.read()
    entry = next(r for r in state["invocations"]["INV-0001"]["runs"] if r["run"] == run)
    return control, files, list(entry.get("requests") or [])


def enable_messaging(lab: HarnessLab) -> None:
    """The operator adopts `coordination.messaging: enabled` (D-15; the adoption registers the project, D-39)."""
    policy = lab.root / EXECUTION
    data = util.load_yaml(policy.read_text(encoding="utf-8"))
    data["coordination"] = {"messaging": X.MESSAGING_ENABLED}
    policy.write_text(util.dump_yaml(data), encoding="utf-8", newline="\n")
    lab.project.adopt_policy(reason="coordination messaging on")


def stop_and_requests(lab: HarnessLab, run: str) -> list[str]:
    """Stop the run and wait for its end: every request recorded before the stop has been acted on by then, so what
    was posted is final. Returns the kinds of the requests the supervisor acted on."""
    lab.ok("harness", "stop", run, "--reason", "the test is done", "--token", lab.project.token)
    lab.wait(run)
    return [t.get("kind") for t in lab.record(run)["timeline"] if t["event"] == "request"]


def send(lab: HarnessLab, run: str, *args: str):
    return lab.aew("harness", "send", run, *args, "--token", lab.project.token)


# ---------------------------------------------------------------------------------------------- messaging off


def test_harness_send_defaults_to_next_step_and_posts_steer(lab, tmp_path):
    """With no `--when`, a send is `next-step`: a supervisor request file, as before, that fake V2 receives as `steer`
    and admits at the next step boundary, inside the same turn."""
    run = launch_held_open(lab, tmp_path)
    out = lab.ok("harness", "send", run, "--text", "Also note the changed files.", "--token", lab.project.token)
    assert out["requested"] == "send" and out["file"]
    lab.until(lambda: lead_posts(lab, run), what="the message posted")
    assert lead_posts(lab, run) == ["steer"]
    assert [e["delivery"] for e in prompt_events(lab, run)][1:] == ["steer"]
    release(tmp_path)
    assert lab.wait(run)["status"] == "ended_without_evidence"
    session = next(iter(json.loads((runlog.run_dir(lab.aew_root, run) / "harness" / "xdg-data" / "opencode"
                                    / "fake-db.json").read_text(encoding="utf-8")).values()))
    users = [m["text"] for m in session["messages"] if m["type"] == "user"]
    assert users[-1] == "Also note the changed files."
    assert lab.record(run)["result"]["prompts"] == 2


def test_harness_send_when_turn_end_is_refused_while_messaging_is_off_and_writes_nothing(lab, tmp_path):
    """G1 (§3.3): with messaging off, `turn-end` is unavailable. It is refused `TURN_END_NEEDS_MESSAGING`, and nothing
    is recorded or written: no request file, no control-state change, no thread, marker or `coordination_store` key
    (D-31's byte-identity), and nothing posted."""
    run = launch_held_open(lab, tmp_path)
    before = written(lab, run)
    res = send(lab, run, "--text", "After you finish, also update the changelog.", "--when", "turn-end")
    assert res.returncode != 0 and res.error["code"] == "TURN_END_NEEDS_MESSAGING", res.stderr
    assert "--when next-step" in res.error["message"]
    assert written(lab, run) == before
    assert not (lab.aew_root / "coordination").exists()
    assert "coordination_store" not in Engine.discover(lab.root).store.read()
    # a `next-step` send after it is the first and only Lead post: the refused one never reached the queue
    lab.ok("harness", "send", run, "--text", "Now this.", "--when", "next-step", "--token", lab.project.token)
    lab.until(lambda: lead_posts(lab, run), what="the next-step message posted")
    release(tmp_path)
    assert stop_and_requests(lab, run) in (["send", "stop"], ["send"])
    assert lead_posts(lab, run) == ["steer"]


def test_with_messaging_off_no_lead_path_posts_queue(lab, tmp_path, monkeypatch):
    """G1 (§3.3): with messaging off no Lead path posts `queue`. Every `harness send` form, from the Lead's own shell
    and through the recovery profile's `cli` row (`argv`), posts `steer`; a `turn-end` one posts nothing."""
    run = launch_held_open(lab, tmp_path)
    message = tmp_path / "nudge.md"
    message.write_text("From a file.", encoding="utf-8")
    accepted = [("--text", "Default timing."), ("--text", "Named timing.", "--when", "next-step"),
                ("--file", str(message)), ("--file", str(message), "--when", "next-step")]
    for args in accepted:
        lab.ok("harness", "send", run, *args, "--token", lab.project.token)
    res = lab.project.aew("harness", "send", run, "--file", "-", "--token", lab.project.token, env=lab.env,
                          input="From stdin.")
    assert res.returncode == 0, res.stderr
    res = send(lab, run, "--text", "Turn end.", "--when", "turn-end")
    assert res.error["code"] == "TURN_END_NEEDS_MESSAGING"
    # The recovery escape: the Lead session's broker runs the same command, with the Lead's credential.
    broker = lead_broker.LeadBroker(Engine.discover(lab.root), lab.project.token)
    broker.start()
    try:
        with monkeypatch.context() as session:  # the Lead session's coordinates, here only, never in a CLI child
            for name, value in broker.env.items():
                session.setenv(name, value)
            session.delenv("AEW_LEAD_TOKEN", raising=False)
            out = client.forward("cli", {"argv": ["harness", "send", run, "--text", "Through the cli row."]},
                                 ingress="mcp", profile="recovery")
            assert out["ok"], out
            out = client.forward("cli", {"argv": ["harness", "send", run, "--text", "Through the cli row, after.",
                                                  "--when", "turn-end"]}, ingress="mcp", profile="recovery")
            assert not out["ok"] and "TURN_END_NEEDS_MESSAGING" in json.dumps(out), out
    finally:
        broker.close()
    sends = len(accepted) + 2  # the four own-shell forms, stdin and the cli row
    lab.until(lambda: len(lead_posts(lab, run)) == sends, what="every accepted send posted")
    release(tmp_path)
    assert stop_and_requests(lab, run).count("send") == sends
    assert lead_posts(lab, run) == ["steer"] * sends
    assert all(e["delivery"] != "queue" for e in prompt_events(lab, run))


# ---------------------------------------------------------------------------------------------- messaging on


@pytest.mark.parametrize("case", ["on_off"])  # `off_on` lands with MS4, which writes the run's snapshot (§3.1, §7)
def test_harness_send_refuses_when_the_project_switch_and_the_runs_snapshot_disagree(lab, tmp_path, case):
    """§3.1: the run launched with messaging off and the operator then switched it on. Neither path is safe (a record
    would never be delivered live; a request file would be the unrecorded path G4 forbids), so every send is refused
    `MESSAGING_SNAPSHOT_MISMATCH`, with no request file, no control-state change and no POST."""
    run = launch_held_open(lab, tmp_path)
    enable_messaging(lab)
    before = written(lab, run)
    for when in ("next-step", "turn-end"):
        res = send(lab, run, "--text", "Check the shutdown path.", "--when", when)
        assert res.returncode != 0 and res.error["code"] == "MESSAGING_SNAPSHOT_MISMATCH", (when, res.stderr)
        assert "relaunch" not in res.error["message"].lower() and "needs messaging switched off" in res.error["message"]
        assert res.error["details"] == {"project": "enabled", "snapshot": "disabled", "when": when}
        assert written(lab, run) == before
    release(tmp_path)
    assert "send" not in stop_and_requests(lab, run)
    assert lead_posts(lab, run) == []


def test_before_ms4_a_run_launched_after_messaging_was_switched_on_is_refused_alike_and_no_relaunch_is_advised(
        lab, tmp_path):
    """Review of PR #176, finding 1: until MS4 writes the run's snapshot, every run reads as launched off, so a run
    launched after the operator switched messaging on is refused `MESSAGING_SNAPSHOT_MISMATCH` exactly like one
    launched before. The refusal must not send the Lead to relaunch (it costs a working run and never helps): it says
    that sending needs messaging switched off. MS4 replaces this test when it deletes `SNAPSHOT_RECORDED`."""
    assert harness_ops.SNAPSHOT_RECORDED is False
    enable_messaging(lab)  # the operator adopts messaging BEFORE the run is launched
    run = launch_held_open(lab, tmp_path)
    before = written(lab, run)
    res = send(lab, run, "--text", "Check the shutdown path.")
    assert res.returncode != 0 and res.error["code"] == "MESSAGING_SNAPSHOT_MISMATCH", res.stderr
    assert res.error["details"] == {"project": "enabled", "snapshot": "disabled", "when": "next-step"}
    message = res.error["message"]
    assert "relaunch" not in message.lower() and "aew harness launch" not in message
    assert "cannot yet launch a run with coordination messaging on" in message
    assert "needs messaging switched off" in message
    assert written(lab, run) == before
    release(tmp_path)
    assert "send" not in stop_and_requests(lab, run)
    assert lead_posts(lab, run) == []


def test_snapshot_mismatch_takes_precedence_over_turn_end_needs_messaging(lab, tmp_path, monkeypatch):
    """§3.1: the mismatch is checked before any timing's own refusal. In the `off_on` cell (project off, run launched
    on) a `turn-end` send is `MESSAGING_SNAPSHOT_MISMATCH`, not `TURN_END_NEEDS_MESSAGING`, because it says what to do:
    relaunch (with the project switched off, a relaunched run agrees with it; with it switched on, a relaunch helps
    once MS4 records snapshots). Until MS4 writes the snapshot no run can be launched on, so the snapshot read stands
    in for it here."""
    run = launch_held_open(lab, tmp_path)
    monkeypatch.setattr(harness_ops, "run_messaging_snapshot", lambda entry: X.MESSAGING_ENABLED)
    engine = Engine.discover(lab.root)
    before = written(lab, run)
    with pytest.raises(AEWError) as refused:
        engine.harness_send(token=lab.project.token, run=run, text="After you finish.", when="turn-end")
    assert refused.value.code == "MESSAGING_SNAPSHOT_MISMATCH"
    assert "Relaunch the run" in refused.value.message  # the project is off: a relaunch clears it
    assert written(lab, run) == before
    monkeypatch.undo()  # without the disagreement, the same send is the timing's own refusal
    with pytest.raises(AEWError) as refused:
        engine.harness_send(token=lab.project.token, run=run, text="After you finish.", when="turn-end")
    assert refused.value.code == "TURN_END_NEEDS_MESSAGING"
    release(tmp_path)
    assert "send" not in stop_and_requests(lab, run)
    assert lead_posts(lab, run) == []


@pytest.mark.parametrize("when", ["next-step", "turn-end"])
def test_with_messaging_on_before_ms5b_harness_send_is_refused_needs_store(lab, tmp_path, monkeypatch, when):
    """G4, fail-closed (§3.1): with messaging on, every `harness send` is recorded in the message store or refused,
    never the unrecorded request file. Until MS5b builds the store path it is refused `HARNESS_SEND_NEEDS_STORE` in
    both timings: no request file, no control-state change, no POST. Both values are on: the project's adopted switch,
    and the run's launch snapshot, which MS4 will write and the snapshot read stands in for here."""
    run = launch_held_open(lab, tmp_path)
    enable_messaging(lab)
    monkeypatch.setattr(harness_ops, "run_messaging_snapshot", lambda entry: X.MESSAGING_ENABLED)
    before = written(lab, run)
    with pytest.raises(AEWError) as refused:
        Engine.discover(lab.root).harness_send(token=lab.project.token, run=run, text="Check the shutdown path.",
                                               when=when)
    assert refused.value.code == "HARNESS_SEND_NEEDS_STORE" and "not yet available" in refused.value.message
    assert written(lab, run) == before
    release(tmp_path)
    assert "send" not in stop_and_requests(lab, run)
    assert lead_posts(lab, run) == []
