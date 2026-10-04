"""Defects found by the M3 step-8 live model trials (harness-conformance.md §6). Each is a permanent regression.

**Text inputs on Windows.** A real model writes its report the way its platform's tools do.
- Windows PowerShell 5.1, the agent's shell on Windows when ``SHELL`` is unset, writes UTF-8 *with a byte-order mark*
  for ``Set-Content -Encoding utf8``, and UTF-16 for ``>`` and ``Out-File``.
- A report piped into ``aew submit --file -`` reaches Python as bytes that it decodes with the ANSI code page.

Found live: a reviewer's BOM-prefixed report was refused as "missing YAML frontmatter", and the model had to inspect
the file's bytes to find out why. Found while fixing it:
- UTF-8 piped to stdin was decoded as cp1252 on Windows, so "—" would have been sealed into evidence as "â€”";
- a UTF-16 file raised an unhandled ``UnicodeDecodeError``;
- with an explicit credential, ``--file -`` read stdin twice, and the (empty) second read was the one submitted.

AEW's text inputs are UTF-8, read once, as bytes. A UTF-8 or UTF-16 byte-order mark is honoured and removed. Anything
else that is not UTF-8 is a USAGE error: never mojibake sealed into evidence, never a traceback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aewflow import SUBTRACT_PATCH, assign, create_planned_ticket, sample_project
from conftest import run_aew
from harness_conformance import FakeDriver, evidence_of, launch_ticket

from aew.util import dump_yaml, parse_frontmatter

META = {"claim": "subtract — implemented with a focused test", "result": "pass",
        "producer": {"model": "windows-agent", "harness": "powershell"},
        "implementation": {"files_changed": sorted(SUBTRACT_PATCH), "checks_run": ["unit"], "deviations": [],
                           "self_review": {"completed": True, "notes": "diff matches plan — no drift"}}}
BODY = "Implemented per plan v1 — nothing else.\n"
REPORT = f"---\n{dump_yaml(META)}---\n{BODY}"
# How each Windows tool delivers the report: (encoding, via stdin, CRLF line endings)
WRITTEN = {"powershell-utf8-bom": ("utf-8-sig", False, True),   # Set-Content -Encoding utf8 (5.1)
           "powershell-redirect-utf16": ("utf-16", False, True),  # `>` / Out-File (5.1)
           "piped-utf8": ("utf-8", True, False)}                  # bash heredoc | aew submit --file -


def written(case: str) -> tuple[bytes, bool]:
    encoding, stdin, crlf = WRITTEN[case]
    return (REPORT.replace("\n", "\r\n") if crlf else REPORT).encode(encoding), stdin


def sealed(root: Path, wid: str, evidence_id: str) -> tuple[dict[str, Any], str]:
    text = (root / ".aew" / "evidence" / wid / f"{evidence_id}.md").read_text(encoding="utf-8")
    assert "﻿" not in text and "â€" not in text, text[:200]
    return parse_frontmatter(text, source=evidence_id)


def implementer(tmp_path: Path):
    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    role = assign(p, wid)
    role.write(SUBTRACT_PATCH)
    assert role.check("unit")["result"] == "pass"
    return p, wid, role


@pytest.mark.parametrize("case", sorted(WRITTEN))
def test_a_report_is_sealed_exactly_as_written_with_a_credential(tmp_path, case):
    p, wid, role = implementer(tmp_path)
    data, stdin = written(case)
    path = tmp_path / "report.md"
    path.write_bytes(data)
    res = run_aew("-C", str(role.workspace), "submit", "--kind", "implementation_report",
                  "--file", "-" if stdin else str(path), env={"AEW_INVOCATION_TOKEN": role.token},
                  input=data.decode("utf-8") if stdin else None)
    assert res.returncode == 0, res.stderr
    meta, body = sealed(p.root, wid, res.json["evidence"])
    assert meta["claim"] == META["claim"] and body.strip() == BODY.strip()


@pytest.mark.parametrize("case", sorted(WRITTEN))
def test_an_agent_report_is_sealed_exactly_as_written_through_the_bridge(tmp_path, case):
    data, stdin = written(case)
    encoding = WRITTEN[case][0]
    driver = FakeDriver()
    lab = driver.create_lab(tmp_path)
    try:
        text = data.decode(encoding)  # the step re-encodes it exactly as the tool did
        wid, _, run = launch_ticket(lab, driver, tmp_path, [
            {"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
            {"do": "submit_raw", "kind": "implementation_report", "text": text.removeprefix("﻿"),
             "encoding": encoding, "stdin": stdin}])
        assert lab.wait(run)["status"] == "ended_with_evidence", lab.step(run, 2)
        [report] = [e for e in evidence_of(lab, wid, run) if e["kind"] == "implementation_report"]
        meta, body = sealed(lab.root, wid, report["id"])
        assert meta["claim"] == META["claim"] and body.strip() == BODY.strip()
    finally:
        lab.cleanup()


def test_text_that_is_not_utf8_is_a_usage_error(tmp_path):
    """Bytes in a Windows code page are refused with a clear AEW error, never decoded as something else."""
    p, wid, role = implementer(tmp_path)
    path = tmp_path / "report.md"
    path.write_bytes(REPORT.encode("cp1252"))
    res = run_aew("-C", str(role.workspace), "submit", "--kind", "implementation_report", "--file", str(path),
                  env={"AEW_INVOCATION_TOKEN": role.token})
    assert res.returncode != 0 and "Traceback" not in res.stderr, res.stderr
    assert res.error["code"] == "USAGE" and "UTF-8" in res.error["message"], res.error
    assert not list((p.root / ".aew" / "evidence" / wid).glob("*impl*"))


@pytest.mark.parametrize("case", sorted(WRITTEN))
def test_the_lead_broker_client_forwards_stdin_as_written(monkeypatch, case):
    """``aew plan propose --file -`` (or any Lead command reading stdin) inside a Lead session: the client forwards
    stdin to the broker, which parses it there. It is decoded like every other text input, whatever the console's
    code page."""
    import io
    import sys

    from aew.harness import bridge, lead_broker

    data, _ = written(case)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="cp1252"))
    sent: dict[str, Any] = {}
    monkeypatch.setattr(bridge, "call", lambda op, args, **kw: sent.update(args) or {"result": {}})
    lead_broker.forward(["plan", "propose", "T-0001", "--file", "-"], type("Args", (), {"cwd": None})())
    assert sent["stdin"].replace("\r\n", "\n") == REPORT


def test_a_relaunch_names_the_evidence_that_went_stale(tmp_path):
    """Found live (M3 step 8, M3-D4). An implementer wrote its report into the workspace, submitted it, then deleted the
    file: the report was evaluated on a workspace state that no longer exists, and AEW rightly refused to send the
    work to review (``self_review`` STALE). The Lead's recovery is a relaunch, whose continuation listed the report as
    "pass", so a relaunched agent had no way to know its evidence no longer counted. The continuation now says which
    of the invocation's evidence is stale; evidence that is still current is shown exactly as before."""
    from harness_conformance import IMPLEMENT

    from aew.harness import runlog

    driver = FakeDriver()
    lab = driver.create_lab(tmp_path)
    try:
        later_edit = {"calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "\n# edited after the report\n"}
        wid, inv, run = launch_ticket(lab, driver, tmp_path, [*IMPLEMENT, {"do": "write", "files": later_edit}])
        assert lab.wait(run)["status"] == "ended_with_evidence"
        lab.project.lead("work", "transition", wid, "--to", "RUNNING")
        refused = lab.lead_res("work", "transition", wid, "--to", "REVIEW_PENDING")
        assert refused.error["code"] == "GATE_UNSATISFIED", refused.error
        driver.script(lab, "R-INV-0001-2", [{"do": "exit", "code": 0}])
        lab.lead("harness", "launch", inv)
        lab.wait("R-INV-0001-2")
        evidence = lab.record("R-INV-0001-2")["contract"]["continuation"]["evidence"]
        assert evidence and all(e.get("stale") is True for e in evidence), evidence
        tail = (runlog.run_dir(lab.aew_root, "R-INV-0001-2") / "prompt.md").read_text(encoding="utf-8")
        tail = tail.split("## Continuation", 1)[1]
        report = next(e["id"] for e in evidence if e["kind"] == "implementation_report")
        assert f"{report} (implementation_report, pass; STALE)" in tail and "record it again" in tail
    finally:
        lab.cleanup()


# A verifier wrote a check citation as `- direct-interpreter-observation: safe_div(7,2)=3.5, ==3.5 True`: YAML reads
# that list item as a mapping, and submit crashed (``TypeError: unhashable type: 'dict'``, BRIDGE_ERROR through the
# bridge) instead of refusing it. Found live (M3 step 8, M3-D5). Every malformed but parseable section is refused.
def _verification(checks: Any = None, claims: Any = None) -> dict[str, Any]:
    claim = {"type": "goal_backwards", "claim": "subtract works", "result": "pass", "checks": checks or []}
    return {"claim": "verified", "verification": {"scope": "ticket", "claims": claims if claims is not None else [
        claim, {"type": "contract", "claim": "in scope", "result": "pass", "checks": []}]}}


MALFORMED = {
    "verification-check-cited-as-a-mapping": ("verifier", "verification", lambda unit: _verification(
        checks=[unit, {"direct-interpreter-observation": "safe_div(7,2)=3.5, ==3.5 True"}])),
    "verification-claims-not-a-list": ("verifier", "verification", lambda unit: _verification(claims="all pass")),
    "verification-claim-as-text": ("verifier", "verification", lambda unit: _verification(claims=["it works"])),
    "verification-not-a-mapping": ("verifier", "verification", lambda unit: {"verification": ["pass"]}),
    "review-finding-as-text": ("reviewer", "review", lambda unit: {"review": {
        "independence": "R1", "disposition": "changes_required", "findings": ["the division floors"]}}),
    "review-not-a-mapping": ("reviewer", "review", lambda unit: {"review": "pass"}),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_a_malformed_section_is_refused_never_a_crash(tmp_path, case):
    from aewflow import Role, implement, review

    role, kind, build = MALFORMED[case]
    p, wid, impl = implementer(tmp_path)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    if role == "verifier":
        p.lead("review", "ingest", wid, "--evidence", review(p, wid))
        p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    out = p.lead("invoke", "create", wid, "--role", role)
    actor = Role(p, out["invocation_token"], impl.workspace)
    unit = actor.check("unit")["evidence"] if role == "verifier" else None
    before = sorted(e.name for e in (p.root / ".aew" / "evidence" / wid).glob("*.md"))
    res = actor.submit(kind, build(unit), expect_ok=False)
    assert res.returncode != 0 and "Traceback" not in res.stderr, res.stderr[-600:]
    assert res.error["code"] == "VALIDATION_FAILED", res.error
    assert sorted(e.name for e in (p.root / ".aew" / "evidence" / wid).glob("*.md")) == before


def test_every_run_is_told_where_to_write_outside_its_workspace(tmp_path):
    """Found live (M3 step 8, M3-D6). The contract said "write report files outside the workspace" and named no place.
    Models guessed: one left its report in the shared workspace (refused: WORKSPACE_MUTATED), one wrote its report
    into the workspace and deleted it after submitting (its evidence went stale), and one wrote into the operator's
    own repository. Every run now has a private scratch directory, created for it, named in the contract and in its
    environment (``AEW_SCRATCH``), and a report written there is submitted like any other."""
    from aew.harness import runlog

    driver = FakeDriver()
    lab = driver.create_lab(tmp_path)
    try:
        sync = tmp_path / "sync"
        sync.mkdir(exist_ok=True)
        wid, inv, run = launch_ticket(lab, driver, tmp_path, [{"do": "dump_env", "path": str(sync / "env")}])
        lab.wait(run)
        env = __import__("json").loads((sync / "env").read_text(encoding="utf-8"))
        scratch = Path(env["AEW_SCRATCH"])
        assert scratch.is_dir() and scratch.resolve().is_relative_to(runlog.run_dir(lab.aew_root, run).resolve())
        assert lab.record(run)["contract"]["scratch"] == str(scratch)
        prompt = (runlog.run_dir(lab.aew_root, run) / "prompt.md").read_text(encoding="utf-8")
        assert f"Your private scratch directory is `{scratch}`" in prompt
    finally:
        lab.cleanup()


def test_a_review_naming_findings_it_resolves_is_checked_when_submitted(tmp_path):
    """Found live (M3 step 8, M3-D7). After a rework, a fresh reviewer passed the corrected code and wrote
    ``resolved_findings: [F1, F2]``, the bare ids, while the pack lists them as ``INV-0002-review-3#F1``. The review
    was accepted at submit and refused only at the Lead's ingest ("resolves unknown finding F1"), after the reviewer's
    run had ended, so the Lead had to dispatch a whole new review. It is now refused at submit, naming the ids to use,
    and the reviewer can correct it in the same run. Ingest still checks."""
    from aewflow import Role, implement, redispatch_implementer, review

    p, wid, impl = implementer(tmp_path)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    bad = review(p, wid, disposition="changes_required",
                 findings=[{"id": "F1", "severity": "blocker", "summary": "floor division", "required": True}])
    assert p.lead("review", "ingest", wid, "--evidence", bad)["transition"]["to"] == "REVIEW_FAILED"
    p.lead("work", "transition", wid, "--to", "RUNNING")
    implement(redispatch_implementer(p, wid), {"tests/test_subtract.py": SUBTRACT_PATCH["tests/test_subtract.py"]
                                               + "\n# covers the finding\n"})
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    reviewer = Role(p, p.lead("invoke", "create", wid, "--role", "reviewer")["invocation_token"], impl.workspace)
    passing = {"claim": "fixed", "review": {"independence": "R1", "disposition": "pass", "findings": []}}
    res = reviewer.submit("review", {**passing, "review": {**passing["review"], "resolved_findings": ["F1"]}},
                          expect_ok=False)
    assert res.returncode != 0, "a review resolving an unknown finding was accepted at submit"
    assert res.error["code"] == "VALIDATION_FAILED" and f"{bad}#F1" in res.error["message"], res.error
    good = reviewer.submit("review", {**passing, "review": {**passing["review"], "resolved_findings": [f"{bad}#F1"]}})
    assert p.lead("review", "ingest", wid, "--evidence", good["evidence"])["transition"]["to"] == "REVIEW_PASSED"
