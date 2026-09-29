"""M3 step 9: defects the dogfood found (a real model Lead acting on AEW's own guidance). Permanent regressions.

M3-D8. AEW's next actions sent a Lead after harness runs the wrong way:

- for a run that ended with evidence it always said "ingest it", but an implementer's report is never ingested (a
  model Lead tried ``aew evidence ingest`` and ``aew review ingest`` on it before finding the transition);
- an ASSIGNED Ticket whose implementer was already launched (``--launch``) still said "launch the implementer from
  its pack";
- a RUNNING Ticket said "advance to REVIEW_PENDING" whatever its gates are (a Class 0 Ticket goes to COMMIT_READY).

Now each next action names the command that applies, and following it is legal.

M3-D9. Two model Leads (a free model and GPT-5.6 Luna) gave a Ticket's scope as one comma-separated value
(``--scope "ledger/money.py,tests/test_money.py"``). AEW stored it as a single glob that matches no path, so the
implementer's correct change was out of scope and the Lead cancelled and recreated the Ticket. A scope glob with a
comma is now refused at creation, saying to repeat ``--scope``.

M3-D10. Inside a Lead session (``aew opencode``, or the dogfood's headless Lead), ``aew resume`` told the Lead that
"this session must not act as Lead unless authority is transferred" (handoff or takeover): resume is read-only, runs
without the broker, and assumed the reader holds no authority. A GPT-5.6 Luna Lead believed it, wrote a checkpoint
asking the operator for a takeover, and stopped. Resume now asks the session's Lead broker, and says that this session
holds Lead authority, or that its broker no longer does. Outside a Lead session its guidance is unchanged.
"""

from __future__ import annotations

import json
import sys

import pytest

from aewflow import SUBTRACT_PATCH, create_planned_ticket, sample_project
from conftest import IS_WINDOWS, run_aew
from fake_harness import AGENT, IMPL_REPORT, HarnessLab, credential_hits
from invariants import assert_control_invariants

IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
REVIEW = {"claim": "independent review of the change against plan and contracts",
          "producer": {"model": "fake-model"},
          "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}


@pytest.fixture
def lab(tmp_path):
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path)
    yield lab
    lab.cleanup()
    assert not credential_hits(tmp_path)


def actions(lab, wid: str) -> list[str]:
    return [a for a in lab.ok("status", "--json")["next_actions"] if a.startswith(f"{wid}:")]


def says_ingest(action: str) -> bool:
    return "ingest it" in action or any(f"aew {c} ingest" in action for c in ("evidence", "review", "verify"))


@pytest.mark.parametrize("cls, after", [(0, "COMMIT_READY"), (1, "REVIEW_PENDING")])
def test_after_an_implementer_run_the_next_action_is_its_transition_never_an_ingest(lab, tmp_path, cls, after):
    wid = create_planned_ticket(lab.project, tmp_path, cls=cls)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    assert lab.wait("R-INV-0001-1")["status"] == "ended_with_evidence"

    assigned = actions(lab, wid)
    assert not any(says_ingest(a) or "from its pack" in a for a in assigned), assigned
    assert any(f"aew work transition {wid} --to RUNNING" in a for a in assigned), assigned
    lab.lead("work", "transition", wid, "--to", "RUNNING")

    running = actions(lab, wid)
    assert not any(says_ingest(a) for a in running), running
    assert any(f"aew work transition {wid} --to {after}" in a for a in running), running
    lab.lead("work", "transition", wid, "--to", after)  # the advice is a legal step
    assert_control_invariants(lab.project)


def test_a_scope_glob_with_a_comma_is_refused_saying_to_repeat_the_option(tmp_path):
    p = sample_project(tmp_path)
    rev = p.rev()
    ticket = ["work", "create", "ticket", "--title", "Fix negatives", "--class", "0", "--goal", "negatives print -$1"]
    res = p.aew(*ticket, "--scope", "calc/core.py,tests/test_core.py", "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode != 0, res.stdout
    message = res.error["message"]
    assert "calc/core.py,tests/test_core.py" in message and "repeat --scope" in message, message
    assert p.rev() == rev  # nothing was created
    wid = p.lead(*ticket, "--scope", "calc/core.py", "--scope", "tests/test_core.py")["id"]
    assert p.ok("work", "show", wid)["control"]["kind"] == "ticket"


def test_resume_inside_a_lead_session_says_this_session_holds_lead_authority(tmp_path):
    p = sample_project(tmp_path)
    script, transcript = tmp_path / "lead-script.json", tmp_path / "lead.jsonl"
    script.write_text(json.dumps([{"do": "aew", "args": ["resume", "--json"]}]), encoding="utf-8")
    res = run_aew("-C", str(p.root), "lead", "session", "--", sys.executable, str(AGENT), "--script", str(script),
                  "--transcript", str(transcript), env={"AEW_LEAD_TOKEN": p.token}, timeout=300)
    assert res.returncode == 0, res.stderr
    [step] = [json.loads(line)["result"] for line in transcript.read_text(encoding="utf-8").splitlines()]
    inside = json.loads(step["stdout"])
    assert inside["lead"]["holder_reachable"] == "this_session"
    assert inside["authority_guidance"].startswith("This session holds Lead authority"), inside["authority_guidance"]
    assert "must not act as Lead" not in inside["authority_guidance"]

    outside = p.ok("resume", "--json")  # no Lead session: the guidance for a fresh reader is unchanged
    assert outside["lead"]["holder_reachable"] == "unknown" and "must not act as Lead" in outside["authority_guidance"]


def test_resume_in_a_lead_session_whose_broker_is_gone_says_it_holds_no_authority(tmp_path):
    p = sample_project(tmp_path)
    gone = r"\\.\pipe\aew-lead-broker-gone" if IS_WINDOWS else str(tmp_path / "gone.sock")
    report = p.ok("resume", "--json", env={"AEW_LEAD_BROKER": gone, "AEW_LEAD_BROKER_KEY": "00" * 32})
    assert report["lead"]["holder_reachable"] == "no"
    assert report["authority_guidance"].startswith("This session's Lead broker does not hold Lead authority")
    assert "must not act as Lead" in report["authority_guidance"]


def test_every_run_states_its_real_containment_and_nothing_claims_more(lab, tmp_path):
    """Companion review B2 (AEW-INV-ISO-001, FALSE_CONTAINMENT_CLAIM): until AEW has OS-level containment, run
    metadata and operator status say `workdir_separation_only`, so its absence is never read as containment."""
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    assert lab.record("R-INV-0001-1")["containment"] == "workdir_separation_only"
    [run] = lab.ok("harness", "status")["runs"]
    assert run["containment"] == "workdir_separation_only"
    doctor = {c["check"]: c for c in lab.ok("doctor", "--json")["checks"]}
    assert doctor["containment"]["status"] == "WARN"
    assert doctor["containment"]["detail"].startswith("workdir separation only")
    assert "no OS-level filesystem containment" in doctor["containment"]["detail"]


def test_after_a_reviewer_run_the_next_action_names_the_review_ingest(lab, tmp_path):
    wid = create_planned_ticket(lab.project, tmp_path)
    lab.script("R-INV-0001-1", IMPLEMENT)
    lab.lead("work", "assign", wid, "--launch")
    lab.wait("R-INV-0001-1")
    lab.lead("work", "transition", wid, "--to", "RUNNING")
    lab.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    lab.script("R-INV-0002-1", [{"do": "submit", "kind": "review", "meta": REVIEW}])
    lab.lead("invoke", "create", wid, "--role", "reviewer", "--launch")
    assert lab.wait("R-INV-0002-1")["status"] == "ended_with_evidence"

    review = [a for a in actions(lab, wid) if "R-INV-0002-1" in a]
    assert review and all(f"aew review ingest {wid} --evidence INV-0002-" in a for a in review), review
    evidence = review[0].split("--evidence ")[1].split("`")[0]
    lab.lead("review", "ingest", wid, "--evidence", evidence)  # the advice is a legal step
    assert lab.ok("work", "show", wid)["control"]["state"] == "REVIEW_PASSED"
