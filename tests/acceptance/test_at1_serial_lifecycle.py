"""AT-1 — one complete serial Ticket lifecycle, session destruction, and reconstruction from durable state.

WC §21.2 step 4; KC §26 "Serial foundation path" and "Fresh-session reconstruction":
initialize -> Ticket + accepted plan -> bounded Implementer context -> implement + local checks ->
independent review -> verification against the evaluated snapshot -> COMMIT_READY -> controlled
integration -> post-integration validation -> DONE -> destroy the Lead session -> reconstruct.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from aewflow import (
    APPLY_PATCH,
    assign,
    create_planned_ticket,
    integrate,
    implement,
    redispatch_implementer,
    review,
    sample_project,
    to_commit_ready,
    verify,
)
from conftest import IS_WINDOWS, git

pytestmark = pytest.mark.acceptance("AT-1")


def operator_takeover(p, reason: str) -> str:
    """The operator authorizes a takeover. POSIX: a real pseudo-terminal answering the challenge.
    Windows: the engine API with the terminal channel substituted in-process (a console session on
    the developer desktop would otherwise be required); the semantics under test are identical."""
    rev = p.rev()
    if not IS_WINDOWS:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
        from test_authority import _pty_takeover

        return _pty_takeover(p.root, rev, "lead-b")["token"]
    import aew.operator
    from aew.engine.api import Engine

    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        return Engine.discover(p.root).lead_takeover(expect_rev=rev, reason=reason, session_label="lead-b")["token"]
    finally:
        aew.operator.authorize = original


def test_serial_lifecycle_session_destruction_and_reconstruction(tmp_path):
    p = sample_project(tmp_path)

    # --- One complete serial Ticket path -------------------------------------------------------
    t1, _ = to_commit_ready(p, tmp_path)
    done = integrate(p, t1)
    control = p.ok("work", "show", t1)["control"]
    assert control["state"] == "DONE" and git("rev-parse", "main", cwd=p.root) == done["integrated_commit"]
    kinds = {e["kind"] for e in control["evidence"]}
    assert {"implementation_report", "check_result", "review", "verification"} <= kinds
    completion = (p.root / ".aew" / control["completion_record"]).read_text()
    assert "post_integration_evidence" in completion

    # --- Start a second Ticket, then lose the Lead session mid-flight ---------------------------
    t2 = create_planned_ticket(p, tmp_path, title="Add apply()", extra=("--depends-on", t1))
    assert p.ok("work", "show", t2)["control"]["state"] == "READY"
    impl = assign(p, t2)
    impl.write(APPLY_PATCH)  # work in progress, not yet reported

    lost_token = p.token
    p.token = ""  # the session (and the only copy of its credential) is destroyed
    shutil.rmtree(p.root / ".aew/local")  # derived caches/packs are disposable (KC §5.3, §21)

    # --- Fresh process reconstructs everything from durable state -------------------------------
    resume = p.ok("resume", "--json")
    assert resume["project"]["id"] == "calc"
    assert resume["lead"] == {"status": "active", "generation": 1, "session_label": "lead-a",
                              "holder_reachable": "unknown"}
    work = {w["id"]: w for w in resume["work"]}
    assert work[t1]["state"] == "DONE" and work[t2]["state"] == "RUNNING"
    assert work[t2]["accepted_plan"]["revision"] == 1
    assert work[t2]["role_plan"]["execute"][0]["card"] == "engineer"
    assert resume["open_review_findings"] == [] and resume["verification_failures"] == []
    assert any(t2 in a for a in resume["next_actions"])
    assert "operator" in resume["authority_guidance"]
    assert (p.root / ".aew/state/CURRENT.md").exists()

    # --- Operator-authorized takeover; in-flight work is reconciled, never assumed complete ----
    p.token = operator_takeover(p, "Lead session destroyed (AT-1)")
    assert p.ok("lead", "show")["generation"] == 2
    res = p.aew("work", "transition", t2, "--to", "CANCELLED", "--reason", "x", "--token", lost_token,
                "--expect-rev", str(p.rev()))
    assert res.error["code"] == "STALE_AUTHORITY"
    control = p.ok("work", "show", t2)["control"]
    assert control["state"] == "INTERRUPTED" and control["interrupted_from"] == "RUNNING"
    rec = p.lead("work", "reconcile", t2, "--to", "RUNNING", "--reason", "workspace inspected: partial apply() edit")
    assert rec["inspection"]["changed_since_assignment"] is True
    impl2 = redispatch_implementer(p, t2)
    implement(impl2, APPLY_PATCH)
    p.lead("work", "transition", t2, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", t2, "--evidence", review(p, t2))
    p.lead("work", "transition", t2, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", t2, "--evidence", verify(p, t2))
    p.lead("work", "transition", t2, "--to", "COMMIT_READY")
    integrate(p, t2)
    final = p.ok("resume", "--json")
    assert {w["id"]: w["state"] for w in final["work"]} == {t1: "DONE", t2: "DONE"}
    assert final["contradictions"] == []
    json.dumps(final)  # machine-readable end to end
