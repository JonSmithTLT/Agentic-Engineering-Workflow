"""Bounded context packs and launch contracts (WC §10.1, §15.4; KC §15)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aewflow import (
    SUBTRACT_PATCH,
    Role,
    assign,
    create_planned_ticket,
    implement,
    review,
    sample_project,
    verify,
)

RATIONALE = "IMPLEMENTER-PRIVATE-RATIONALE-7Q2"


@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


def to_review(calc, tmp_path) -> tuple[str, Role, dict]:
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    impl.write(SUBTRACT_PATCH)
    impl.check("unit")
    impl.submit("implementation_report", {
        "claim": "done", "result": "pass",
        "implementation": {"files_changed": sorted(SUBTRACT_PATCH), "checks_run": ["unit"], "deviations": [],
                           "self_review": {"completed": True, "notes": RATIONALE}},
    }, f"My reasoning: {RATIONALE}\n")
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    out = calc.lead("invoke", "create", wid, "--role", "reviewer")
    return wid, impl, out


def test_reviewer_pack_is_bounded_and_independent(calc, tmp_path):
    wid, impl, out = to_review(calc, tmp_path)
    text = (calc.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert calc.aew("context", "show", out["invocation"]).stdout.strip() == text.strip()
    # Launch-contract fields (WC §15.4)
    for needle in ("Role: **reviewer**", f"Work unit: **{wid}**", "Evaluated snapshot", "### Prohibited",
                   "aew submit --kind review", "### Completion criteria", "Governing authority"):
        assert needle in text, needle
    # The change and deterministic check output are present...
    assert "+def subtract(a, b):" in text and "check `unit`" in text
    assert "tests/test_subtract.py" in text
    # ...the implementer's reasoning and self-review notes are not (context independence).
    assert RATIONALE not in text
    # The credential is never in the pack.
    assert out["invocation_token"].rsplit(".", 1)[1] not in text
    assert "supplied by the Lead in the spawn prompt" in text
    sources = {s["name"] for s in out["pack"]["sources"]}
    assert {"current_ticket", "accepted_plan", "guardrails", "role:reviewer"} <= sources


def test_pack_regeneration_is_deterministic(calc, tmp_path):
    wid, impl, out = to_review(calc, tmp_path)
    inv = out["invocation"]
    first = (calc.root / ".aew" / out["pack"]["path"]).read_bytes()
    # The workspace keeps changing and local/ is lost: regeneration still reproduces the pack exactly.
    impl.write({"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "\n# later edit\n"})
    shutil.rmtree(calc.root / ".aew/local")
    regen = calc.ok("context", "pack", inv)
    assert regen["matches_recorded"] is True
    assert Path(regen["path"]).read_bytes() == first


def test_implementer_repack_carries_failure_evidence(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    failing = verify(calc, wid, goal_result="fail")
    calc.lead("verify", "ingest", wid, "--evidence", failing)
    calc.lead("verify", "classify", wid, "--as", "LOCAL_IMPLEMENTATION_DEFECT", "--reason", "off-by-one in test")
    out = calc.lead("invoke", "create", wid, "--role", "implementer")
    text = (calc.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "Failure evidence to address" in text and failing in text
    assert "1. Add subtract(a, b)" in text  # accepted plan slice


def test_verifier_pack_labels_implementer_claims(calc, tmp_path):
    wid = create_planned_ticket(calc, tmp_path)
    impl = assign(calc, wid)
    implement(impl)
    calc.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    calc.lead("review", "ingest", wid, "--evidence", review(calc, wid))
    calc.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    out = calc.lead("invoke", "create", wid, "--role", "verifier")
    text = (calc.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    assert "NOT evidence" in text
    assert "Goal-backwards acceptance criteria" in text and "calc.core.subtract(5, 3) == 2" in text
    assert "Available checks" in text and "## Accepted plan" not in text
