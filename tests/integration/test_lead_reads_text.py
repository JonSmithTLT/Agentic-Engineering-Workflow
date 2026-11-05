"""A Lead loses nothing it acts on in the MCP ``text`` block (E121; ITEMS 53): an OpenCode model reads only that text
(``core/src/session/runner/to-llm-message.ts:125-139``, watched 2026-11-04), so these tests drive a Ticket the way it
does. Every revision, argument and id below comes from the JSON line of the text; ``structuredContent`` is read only to
check that nothing but the named fields was left out."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aewflow import SUBTRACT_PATCH, implement, redispatch_implementer, review, sample_project
from conftest import git
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
from test_stages_ticket import HANG

from aew.engine import custody_ops as CO
from aew.engine.api import Engine
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
