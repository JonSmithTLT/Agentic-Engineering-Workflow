"""Doing what a printed command says works (ITEMS 56, step 5; the standing rule "follow the message's own advice").

``tests/unit/test_printed_commands_parse.py`` proves every printed command parses. Here, for one refusal or next step
per family (credentials, resume, harness, integrate), the printed command is run on the real CLI as the reader would
run it: the revision taken from `aew status`, as its placeholder says, a reason where it asks for one, a fenced
block's heredoc body on standard input, and the Lead credential in the environment. Each test then checks that the
command did what the message promised, not only that it exited 0.
"""

from __future__ import annotations

import argparse
import re
import shlex

import printed_commands as P
import pytest
from aewflow import create_planned_ticket, sample_project, to_commit_ready
from conftest import Project, make_git_repo
from fake_harness import HarnessLab

from aew import operator
from aew.cli import credentials
from aew.cli import main as cli
from aew.errors import UsageError
from aew.harness import contract as K

REASON = "following the printed advice"


def printed_argv(p: Project, command: str, fenced: bool) -> tuple[list[str], str | None]:
    """Fill a printed command with the current revision and a reason, and extract any heredoc body."""
    head, body = P.split(command, fenced)
    revision = p.ok("status", "--json")["revision"]
    filled = head.replace(K.REVISION, str(revision)).replace("<reason>", shlex.quote(REASON))
    assert "<" not in filled, f"a placeholder this test cannot fill: {filled}"
    argv = shlex.split(filled)
    assert argv[0] == "aew"
    return argv[1:], body


def run_printed(p: Project, command: str, fenced: bool, env: dict[str, str] | None = None):
    argv, body = printed_argv(p, command, fenced)
    return p.aew(*argv, env=env, input=body)


def printed(text: str, word: str) -> tuple[str, bool]:
    """The one printed command in ``text`` whose command line names ``word``."""
    [found] = [(c, f) for c, f in P.commands(text) if word in c.splitlines()[0]]
    return found


def lead_env(p: Project) -> dict[str, str]:
    return {"AEW_LEAD_TOKEN": p.token}


def test_credentials_a_lost_invocation_credential_is_recovered_as_printed(tmp_path, monkeypatch):
    """The terminal went away after a dispatch issued an invocation credential: the refusal's cancel command, run as
    printed, ends that invocation (#311 review, F1)."""
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    out = p.lead("work", "assign", wid)  # without --launch: the credential is issued to the caller
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)
    with pytest.raises(UsageError) as raised:
        credentials.deliver(out, argparse.Namespace())
    res = run_printed(p, *printed(str(raised.value), "invoke cancel"), env=lead_env(p))
    assert res.returncode == 0, res.stderr or res.stdout
    shown = p.ok("invoke", "show", out["invocation"])
    assert shown["status"] == "cancelled", shown


def test_resume_a_vacant_seat_is_acquired_as_printed(tmp_path):
    """`aew resume` on a project with no Lead says how to acquire the seat; that command, run as printed, does."""
    p = Project(make_git_repo(tmp_path / "repo"))
    p.ok("init")
    guidance = p.ok("resume", "--json")["authority_guidance"]
    res = run_printed(p, *printed(guidance, "lead acquire"))
    assert res.returncode == 0, res.stderr or res.stdout
    lead = p.ok("lead", "show")
    assert (lead["status"], lead["generation"]) == ("active", 1), lead


def test_doctor_a_changed_manifest_is_adopted_as_printed(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    path = p.root / ".aew/project.yaml"
    path.write_bytes(path.read_bytes() + b"\n# Reviewed project edit.\n")
    before = p.rev()

    def manifest_pin():
        checks = p.aew("doctor", "--json").json["checks"]
        return next(check for check in checks if check["check"] == "manifest-pin")

    drift = manifest_pin()
    assert drift["status"] == "FAIL" and ".aew/project.yaml" in drift["detail"]
    argv, body = printed_argv(p, *printed(drift["detail"], "manifest adopt"))
    assert body is None
    monkeypatch.setenv("AEW_LEAD_TOKEN", p.token)
    monkeypatch.setattr(operator, "ask", lambda prompt, **_: re.search(r"code ([0-9A-F]{6})", prompt)[1])
    assert cli.main(["-C", str(p.root), *argv]) in (0, None)
    assert p.rev() == before + 1
    assert manifest_pin()["status"] == "PASS"


@pytest.fixture
def fake_lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()


def test_harness_an_ended_run_is_relaunched_as_printed(fake_lab, tmp_path):
    """A run that ended with its invocation still active: `aew resume`'s harness action says to relaunch it, and the
    relaunch, run as printed, starts a new run of the same invocation."""
    lab = fake_lab
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("default", [{"do": "exit", "code": 3}])
    out = lab.lead("work", "assign", wid, "--launch")
    inv, run = out["invocation"], out["launch"]["run"]
    assert lab.wait(run)["status"] == "crashed"
    [action] = [h["action"] for h in lab.ok("resume", "--json")["harness_runs"] if h["run"] == run]
    res = run_printed(lab.project, *printed(action, "harness launch"), env=lab.lead_env(lab.env))
    assert res.returncode == 0, res.stderr or res.stdout
    assert res.json["invocation"] == inv and res.json["run"] != run
    lab.wait(res.json["run"])


def test_integrate_a_deferred_entry_is_requeued_and_prepared_as_printed(tmp_path):
    """A deferred queue entry: preparing it is refused with the requeue command; requeued as printed, the requeue's
    next step, run as printed, prepares the candidate."""
    p = sample_project(tmp_path)
    wid, _impl = to_commit_ready(p, tmp_path)
    p.lead("integrate", "defer", wid, "--reason", "waiting for the release branch")
    refused = p.aew("integrate", "prepare", wid, "--expect-rev", str(p.rev()), env=lead_env(p))
    assert refused.returncode != 0 and refused.error["code"] == "ILLEGAL_TRANSITION", refused.stdout
    res = run_printed(p, *printed(refused.error["message"], "integrate requeue"), env=lead_env(p))
    assert res.returncode == 0, res.stderr or res.stdout
    assert (res.json["from"], res.json["to"]) == ("DEFERRED", "QUEUED"), res.json
    res = run_printed(p, *printed(res.json["next"], "integrate prepare"), env=lead_env(p))
    assert res.returncode == 0, res.stderr or res.stdout
    assert p.ok("status", wid, "--json")["work_unit"]["integration"]["status"] in ("prepared", "validated"), res.json
