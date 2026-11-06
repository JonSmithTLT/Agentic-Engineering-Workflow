"""The general Lead command under G3 addendum 7, ruling 1 (register E112): under ``required`` it is refused before any
credential is read and before any seat moves; where the policy allows a weaker run (and on Windows) it runs labelled not
contained, with its ``label.json`` naming the session's process and its entry in the register of weaker contexts live
while it runs. ``run_session``'s ``contained`` is every caller's to give."""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

import conftest
import pytest
from aewflow import lead_project
from conftest import Project, run_aew

from aew import lead_credential
from aew.cli.main import build_parser, main
from aew.engine.api import Engine
from aew.harness import containment, lead_broker, procs
from aew.harness import weaker_register as W

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture
def counted(monkeypatch):
    """Counting stubs of everything that reads or asks for the credential, or moves a seat."""
    from aew import operator

    calls: list[str] = []
    monkeypatch.setattr(lead_credential, "can_prompt", lambda: True)  # a prompt would be asked, if anything asked
    monkeypatch.setattr(operator, "ask_hidden", lambda prompt, **k: calls.append("prompt") or "synthetic")
    monkeypatch.setattr(lead_credential, "required", lambda **k: calls.append("required"))
    monkeypatch.setattr(procs, "harden_current_process", lambda: calls.append("harden"))
    monkeypatch.setattr(Engine, "lead_acquire", lambda self, **k: calls.append("acquire") or {"token": "x"})
    monkeypatch.setattr(procs, "run_session_tree", lambda *a, **k: calls.append("run") or (0, "clean"))
    return calls


def printed_commands(message: str) -> list[list[str]]:
    return [shlex.split(m)[1:] for m in re.findall(r"`(aew [^`]+)`", message)]


def test_under_required_the_general_command_is_refused_before_any_credential_or_seat(project: Project, monkeypatch,
                                                                                       counted, capsys):
    """Planted: the environment holds the credential and the seat is asked for; neither is touched."""
    monkeypatch.setattr(containment, "supported", lambda: True)  # `required`, the Linux default, on any host
    monkeypatch.setenv(lead_credential.ENV, project.token)
    rev = project.rev()
    code = main(["-C", str(project.root), "lead", "session", "--acquire", "--", sys.executable, "-c", "pass"])
    error = json.loads(capsys.readouterr().err)["error"]
    assert code != 0 and error["code"] == "CONTAINMENT_UNAVAILABLE", error
    assert error["details"]["reason"] == "lead_uncontained"
    assert counted == [], "nothing read, asked for, hardened, acquired or run"
    assert lead_credential.ENV in __import__("os").environ, "the credential was never taken from the environment"
    assert project.rev() == rev
    message = error["message"]
    assert "`aew opencode` is the contained Lead" in message and "containment.mode: allow_weaker" in message
    assert "15 minutes after the session ends" in message
    for argv in printed_commands(message):  # printed commands parse as printed
        build_parser().parse_args(argv)
    assert printed_commands(message) == [["lead", "session"], ["opencode"]]


def test_run_session_refuses_a_caller_that_says_nothing_of_containment_before_the_credential(counted):
    """The backstop (DV-5): no route stays uncontained by omission."""
    with pytest.raises(Exception) as refused:
        lead_broker.run_session(object(), ["x"], acquire=True, session_label=None, keep_seat=False,
                                contained=None)  # type: ignore[arg-type]
    assert getattr(refused.value, "code", None) == "CONTAINMENT_UNAVAILABLE" and counted == []
    with pytest.raises(TypeError):
        lead_broker.run_session(object(), ["x"], acquire=True, session_label=None, keep_seat=False)  # type: ignore


def test_under_allow_weaker_the_general_command_runs_labelled_with_its_label_and_a_live_entry(tmp_path):
    """Its label.json holds the weaker label and the session's own process; its entry is live while the harness runs
    and ends when the session ends. Planted: the harness reads both from inside the session."""
    p = lead_project(tmp_path)
    out = tmp_path / "seen.json"
    probe = (f"import json, os, sys; sys.path.insert(0, {str(SRC)!r}); from aew.harness import weaker_register as W;"
             f"m = os.environ[W.MARKER]; r = W.read();"
             f"json.dump({{'marker': m, 'label': json.load(open(m)), 'live': r.live}}, open({str(out)!r}, 'w'))")
    res = run_aew("-C", str(p.root), "lead", "session", "--", sys.executable, "-c", probe,
                  env={"AEW_LEAD_TOKEN": p.token}, timeout=300)
    assert res.returncode == 0, res.stderr
    assert "aew lead session: the Lead runs NOT contained (workdir_separation_only)" in res.stderr
    seen = json.loads(out.read_text(encoding="utf-8"))
    label = seen["label"]
    assert label["filesystem"] == containment.WORKDIR_ONLY and label["weaker_because"]
    assert Path(seen["marker"]).name == "label.json" and Path(seen["marker"]).parent.name.startswith("lead-")
    assert res.json["containment"]["filesystem"] == containment.WORKDIR_ONLY
    # every `aew` the session starts shares one register, so another test's Lead session may be live in it too (an
    # entry the scan cannot prove ended stays live): this session's is the one its own marker names
    register = conftest.CHILD_DATA_BASE / "aew" / W.DIRNAME
    entries = {e["id"]: e for e in (json.loads(f.read_text()) for f in register.glob("lead_session-*.json"))}
    [live] = [e for e in seen["live"] if e["kind"] == "lead_session" and entries[e["id"]]["marker"] == seen["marker"]]
    assert live["why"] == "running"
    entry = entries[live["id"]]
    assert entry["owner"] == {"pid": label["session_pid"], "start_id": label["session_start_id"]}
    # This `aew` scans the host's real processes. Another worker's hardened supervisor cannot be read and started after
    # this entry, which holds it open by condition (c) of the entry-end ruling: that is the rule, and nothing of this
    # session's. Its own processes, or a failed scan, never pass here.
    held = (entry["outcome"] == "unowned" and entry["ownership"] in W.HOLDS_WHOLE
            and "cannot be read" in entry["reason"])
    assert held and not re.search("carries its marker|the scan failed", entry["reason"]) or (
        entry["outcome"] == "clean" and entry["ended_epoch"]), entry
    assert entry["marker"] == seen["marker"]


def test_off_linux_aew_opencode_runs_through_the_same_weaker_route_with_its_reason(monkeypatch, tmp_path):
    """Off Linux the label `aew opencode` returns says why it is weaker (E112's note), and the route is WeakerLead,
    which writes label.json and the register entry like the general command's."""
    from aew.harness.opencode import lead

    seen = {}
    # The credential is checked before any start line (review of #340, m2), as at an operator's shell; the login
    # database is a synthetic absent one, so the start line reads no stored login of the machine's.
    monkeypatch.setenv("AEW_LEAD_TOKEN", "synthetic-not-a-token")
    monkeypatch.setenv("OPENCODE_DB", str(tmp_path / "no-login.db"))
    monkeypatch.setattr(lead, "contained_here", lambda: False)
    monkeypatch.setattr(lead, "check_version", lambda: "2.0.18")
    monkeypatch.setattr(lead, "guide_of", lambda engine: "")
    monkeypatch.setattr(lead, "command", lambda engine, extra: ["opencode"])
    monkeypatch.setattr(lead_broker, "run_session",
                        lambda engine, argv, **k: seen.update(k) or {"ok": True})
    engine = type("E", (), {"execution_policy": lambda self: ({"containment": {"mode": "allow_weaker"}}, None)})()
    lead.run(engine, acquire=False, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
             print_config=False)
    weaker = seen["contained"]
    assert isinstance(weaker, lead_broker.WeakerLead) and weaker.kind == "lead_opencode"
    explicit = type("E", (), {"execution_policy": lambda self: ({"containment": {"mode": "required"}}, None)})()
    monkeypatch.setattr(containment, "supported", lambda: False)
    monkeypatch.setattr(containment.sys, "platform", "freebsd14")
    with pytest.raises(Exception, match="this platform .freebsd14. has no filesystem containment"):
        lead.run(explicit, acquire=False, session_label=None, keep_seat=False, provider_env=[], extra_args=[],
                 print_config=False)
    assert containment.label(contained=False, reason=containment.uncontained_reason())["weaker_because"]
