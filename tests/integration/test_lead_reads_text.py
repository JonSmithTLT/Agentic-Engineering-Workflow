"""A Lead loses nothing it acts on in the MCP ``text`` block (E121; ITEMS 53): an OpenCode model reads only that text
(``core/src/session/runner/to-llm-message.ts:125-139``, watched 2026-11-04), so these tests drive a Ticket the way it
does. Every revision, argument and id below comes from the JSON line of the text; ``structuredContent`` is read only to
check that nothing but the named fields was left out."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from aewflow import SUBTRACT_PATCH, implement, redispatch_implementer, review, sample_project
from conftest import git
from fake_harness import IMPL_REPORT
from invariants import assert_control_invariants
from lead_text import lead_json
from test_integration_stages import (  # noqa: F401  (`contained` and `custody` are fixtures, found by name)
    checks_mode,
    contained,
    control,
    custody,
    done,
    engine,
    verifying,
)
from test_stage_runner import launching
from test_stages_request import implemented, unit
from test_stages_ticket import DRAFT, HANG

from aew.engine import custody_ops as CO
from aew.engine.api import Engine
from aew.harness import contract as K
from aew.surface import mcp, readable
from aew.surface import run as R
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()
FAILING = [{"id": "F1", "severity": "major", "summary": "wrong result", "required": True}]


class TextLead:
    """The model's side of a Lead session: it calls a tool and reads the text it gets back."""

    def __init__(self, p: Any) -> None:
        self.server = mcp.Server(lambda name, arguments, profile: R.run_tool(
            Engine.discover(p.root), CTX, name, arguments, token=p.token))
        self.text = ""

    def call(self, tool: str, **arguments: Any) -> dict[str, Any]:
        reply = self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                    "params": {"name": tool, "arguments": arguments}})
        assert reply is not None and "result" in reply, reply
        self.text = reply["result"]["content"][0]["text"]
        got = lead_json(self.text)
        assert got == readable.for_the_lead(reply["result"]["structuredContent"])
        return got

    def status(self, wid: str) -> dict[str, Any]:
        return self.call("status", work_id=wid)

    def offered(self, wid: str, name: str, **more: Any) -> dict[str, Any]:
        """Call what the projection offers, with the arguments it offers: the expected revision among them."""
        [action] = [a for a in self.status(wid)["projection"]["actions"] if a["action"] == name]
        assert action["availability"] == "AVAILABLE" and action["callable"], action
        return self.call(name, **{**action["arguments"], **more})

    @property
    def head(self) -> list[str]:
        return self.text.split("\n")[:2]


@pytest.fixture
def lab_project(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    lab.script("default", HANG)
    yield p, lab
    lab.cleanup()


def test_a_lead_reading_only_the_text_goes_through_a_stale_revision_a_refusal_and_a_rework(lab_project, tmp_path):
    p, _lab = lab_project
    wid, _impl = implemented(p, tmp_path)
    lead = TextLead(p)

    # The next step in the text is what the JSON offers.
    seen = lead.status(wid)
    assert lead.head == [f"status: done ({wid}: RUNNING)", readable._next(seen)]

    # A stale revision: the stop says so, and the text holds the revision to go on with.
    stale = seen["revision"]
    assert lead.call("checkpoint", expect_rev=stale, note="another commit", next="go on")["ok"]
    refused = lead.call("ticket_request_review", expect_rev=stale, work_id=wid)
    assert not refused["ok"] and refused["stopped"]["boundary"] == "stale_revision"
    assert refused["revision"] == stale + 1 and lead.head[0].startswith("ticket_request_review: stopped at")
    requested = lead.call("ticket_request_review", expect_rev=refused["revision"], work_id=wid)
    assert requested["ok"], requested["stopped"]
    assert requested["completed_steps"][0]["summary"] in lead.text.split("\n")[2]

    # A review that fails: the stage stops at the refusal, with what it committed and why, in the text.
    failing = review(p, wid, disposition="changes_required", findings=FAILING)
    stopped = lead.call("ticket_request_verification", expect_rev=lead.status(wid)["revision"], work_id=wid,
                        review_evidence=failing)
    assert not stopped["ok"] and stopped["stopped"]["at"] == "work.transition"
    assert [s["primitive"] for s in stopped["completed_steps"]] == ["review.ingest"]
    assert lead.head[0].startswith("ticket_request_verification: stopped at work.transition (")
    assert lead.status(wid)["projection"]["state"] == "REVIEW_FAILED"
    assert unit(p, wid)["state"] == "REVIEW_FAILED"

    # The rework: a new implementer's report, and then the same stages from what the text offers.
    p.lead("work", "transition", wid, "--to", "RUNNING")
    implement(redispatch_implementer(p, wid), {"tests/test_subtract.py": SUBTRACT_PATCH["tests/test_subtract.py"]
                                               + "\n\ndef test_again():\n    assert True\n"})
    again = lead.offered(wid, "ticket_request_review")
    assert again["ok"], again["stopped"]
    passing = review(p, wid, resolved=[f"{failing}#F1"])
    verifying_now = lead.call("ticket_request_verification", expect_rev=lead.status(wid)["revision"], work_id=wid,
                              review_evidence=passing)
    assert verifying_now["ok"], verifying_now["stopped"]
    assert lead.status(wid)["projection"]["state"] == "VERIFY_PENDING"
    assert_control_invariants(p)


def test_a_wait_whose_run_crashed_says_so_through_the_adapter(lab_project):
    p, lab = lab_project
    lab.script("default", [{"do": "exit", "code": 3}])
    lead = TextLead(p)
    drafted = lead.call("ticket_draft", **{**DRAFT, "expect_rev": lead.call("status")["revision"]})
    wid = drafted["projection"]["subject"]
    p.lead("plan", "accept", wid, "--revision", "1")
    started = lead.offered(wid, "ticket_start")
    assert started["ok"], started["stopped"]
    runs = [r["run"] for r in started["projection"]["runs"]]
    assert lead.call("harness_wait", runs=runs, timeout_s=30)["result"]["status"] == "crashed"
    lines = lead.text.split("\n")
    assert lines[0] == f"harness_wait: {runs[0]} crashed"
    assert lines[1].startswith("next: ") and "has no live run" in lines[1] and lines[-2:] == lines[:2]


def test_a_wait_that_timed_out_says_so_through_the_adapter(lab_project):
    p, _lab = lab_project
    lead = TextLead(p)
    drafted = lead.call("ticket_draft", **{**DRAFT, "expect_rev": lead.call("status")["revision"]})
    wid = drafted["projection"]["subject"]
    p.lead("plan", "accept", wid, "--revision", "1")
    started = lead.offered(wid, "ticket_start")
    assert started["ok"], started["stopped"]
    runs = [r["run"] for r in lead.status(wid)["projection"]["runs"]]
    timed_out = lead.call("harness_wait", runs=runs, timeout_s=1)
    assert timed_out["result"]["timed_out"] is True
    assert lead.head[0] == f"harness_wait: timed out: {runs[0]} still running"
    # The wait's own step, not the project's first offer: the guidance for a timed-out wait (E122), which no run woke,
    # so it carries no `why`. The line keeps what fits the view; the JSON holds all of it.
    assert "why" not in timed_out["result"]
    assert timed_out["result"]["next_action"] == K.wait_step(runs, again=True)
    assert lead.head[1] == readable._one_line(f"next: {K.wait_step(runs, again=True)}")
    assert lead.head[1].startswith(f"next: {runs[0]} is still working ({K.TIMED_OUT}): {K.NOT_POLLING}.")


def _named_tool(line: str) -> str:
    """The tool a next line names first: the offered call (`next: harness_wait runs=[...]`), or the first tool in
    backticks of the engine's own step. What a model that only follows the text calls next."""
    call = re.match(r"next(?: for the project)?: ([a-z_]+) ", line)
    return call.group(1) if call else re.findall(r"`([a-z_]+)`", line)[0]


def test_a_lead_reading_only_the_text_waits_through_a_long_run_without_stopping_or_polling(lab_project, tmp_path):
    """E122 (the dogfood finding of 2026-10-31: while a run worked, the Lead ended its turn or polled). A Lead that only
    follows the next line of each result: after the start it waits, every timed-out wait tells it the run still works
    and to wait again, never to poll or to stop, and when the run ends the line moves the Ticket on from its evidence.
    The run is held by a file the test releases, so how many waits time out is the test's, not the clock's."""
    p, lab = lab_project
    release, ready = tmp_path / "release", tmp_path / "ready"
    lab.script("default", [{"do": "wait_file", "path": str(release), "ready": str(ready), "timeout": 300},
                           {"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
                           {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}])
    lead = TextLead(p)
    drafted = lead.call("ticket_draft", **{**DRAFT, "expect_rev": lead.call("status")["revision"]})
    wid = drafted["projection"]["subject"]
    p.lead("plan", "accept", wid, "--revision", "1")
    started = lead.offered(wid, "ticket_start")
    assert started["ok"], started["stopped"]
    runs = [r["run"] for r in started["projection"]["runs"]]
    assert lead.head[1] == f'next: harness_wait runs={json.dumps(runs)} ({K.WAIT_RULE})'  # after a dispatch: wait
    [launched] = [s for s in started["result"]["steps"] if "launch" in s]  # the dispatch's own step says so too
    assert launched["next_action"] == K.wait_step(runs)
    lab.until(ready.exists, what=f"{runs[0]} to be working")
    e = Engine.discover(p.root)  # and what `status` and `resume` say of the running run
    [running] = e.harness_resume(e.store.current())
    assert running["action"] == f"{runs[0]} is running for {running['invocation']}: {K.wait_step(runs)}"

    followed = []
    for _ in range(3):  # a long run: the Lead's waits time out while it works
        tool = _named_tool(lead.head[1])
        followed.append(tool)
        got = lead.call(tool, runs=runs, timeout_s=1)
        assert got["result"]["timed_out"] is True and got["result"]["status"] in ("starting", "running")
        assert "why" not in got["result"]  # no run woke it
        assert lead.head[0] == f"harness_wait: timed out: {runs[0]} still running"
        assert "still working" in lead.head[1] and "do not end your turn" in lead.head[1], lead.head[1]
        assert "status" not in lead.head[1].replace("harness_wait", ""), lead.head[1]  # no poll is offered
        assert lead.text.split("\n")[-1] == lead.head[1]  # where the view lands, too
    release.write_text("go", encoding="utf-8")
    tool = _named_tool(lead.head[1])
    followed.append(tool)
    ended = lead.call(tool, runs=runs, timeout_s=300)
    assert followed == ["harness_wait"] * 4
    assert ended["result"]["status"] == "ended_with_evidence" and not ended["result"]["timed_out"]
    assert ended["result"]["why"] == [K.RUN_ENDED]
    # The run ended: the next line moves the Ticket on from its evidence, and no longer says to wait.
    assert lead.head[1].startswith(f"next: {runs[0]} ended with evidence") and "harness_wait" not in lead.head[1]
    assert f"its implementation report moves {wid} on by transition" in ended["result"]["next_action"]
    assert ended["result"]["next_action"].endswith(f"Tell the operator in a line {K.WAKE_GUIDE[K.RUN_ENDED].tell}")


def test_a_wait_whose_run_failed_leads_with_the_engine_s_headline(lab_project):
    """Through the real runner, the adapter and the engine's own payload: the run submits nothing, so the first line and
    the last two say so, and the next step is the wait's own, not the project's first hint."""
    p, lab = lab_project
    lab.script("default", [])  # the run ends at once, having submitted nothing
    lead = TextLead(p)
    drafted = lead.call("ticket_draft", **{**DRAFT, "expect_rev": lead.call("status")["revision"]})
    wid = drafted["projection"]["subject"]
    p.lead("plan", "accept", wid, "--revision", "1")
    started = lead.offered(wid, "ticket_start")
    assert started["ok"], started["stopped"]
    runs = [r["run"] for r in started["projection"]["runs"]]
    got = lead.call("harness_wait", runs=runs, timeout_s=30)
    payload = got["result"]
    assert payload["status"] == "ended_without_evidence" and "ENDED WITHOUT EVIDENCE" in payload["headline"]
    lines = lead.text.split("\n")
    assert lines[0].startswith(f"harness_wait: {runs[0]} ENDED WITHOUT EVIDENCE") and "done" not in lines[0]
    assert lines[1].startswith("next: ") and "authority" not in lines[1] and payload["next_action"][:20] in lines[1]
    assert "```" not in lines[1] and lines[-2:] == lines[:2]


def test_a_lead_reading_only_the_text_publishes_the_candidate_it_read(
        tmp_path, contained, custody):  # noqa: F811  (the imported fixtures, by the names pytest finds them)
    """`integration_publish` names the candidate: the digest filter must leave a commit id, and this one comes from the
    text of `ticket_prepare`'s own result. A wrong candidate is refused, and the refusal's text says which is
    current."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, report = verifying(p, tmp_path)
    lead = TextLead(p)
    prepared = lead.call("ticket_prepare", expect_rev=lead.status(wid)["revision"], work_id=wid,
                         verification_evidence=report)
    assert prepared["ok"], prepared["stopped"]
    assert lead.head[0] == f"ticket_prepare: done ({wid}: COMMIT_READY)"
    candidate = prepared["result"]["steps"][-1]["integration"]["candidate"]
    assert len(candidate) == 40 and candidate == control(p)["work"][wid]["integration"]["candidate"]

    custodian = control(p)["queue"]["lease"]["custodian"]
    found, result = engine(p).custody_step(custodian, custody[custodian])
    assert found == CO.ACTED and result is not None and result["result"] == "pass", result

    wrong = lead.call("integration_publish", expect_rev=lead.status(wid)["revision"], work_id=wid,
                      prepared_candidate="0" * 40)
    assert not wrong["ok"] and candidate in wrong["stopped"]["error"]["message"]
    published = lead.call("integration_publish", expect_rev=wrong["revision"], work_id=wid,
                          prepared_candidate=candidate)
    assert published["ok"], published["stopped"]
    assert done(p, wid) and git("rev-parse", "main", cwd=Path(p.root)) == candidate
    assert_control_invariants(p)
