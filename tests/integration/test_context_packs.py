"""Bounded context packs and launch contracts (WC §10.1, §15.4; KC §15)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from aewflow import (
    SUBTRACT_PATCH,
    Role,
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    dispatch,
    implement,
    plan_unit,
    review,
    sample_project,
    submit_record,
    to_commit_ready,
    verify,
)
from conftest import run_aew

from aew.cli.work_commands import NO_INVOCATION_AUTHORITY
from aew.knowledge.context import CHECK_WRITES_NOTE, OUTPUT_TEMPLATES
from aew.util import load_yaml

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
    # The credential is never in the pack, nor any instruction about one: the pack serves both ways a role runs.
    assert out["invocation_token"].rsplit(".", 1)[1] not in text
    assert "AEW_INVOCATION_TOKEN" not in text
    sources = {s["name"] for s in out["pack"]["sources"]}
    assert {"current_ticket", "accepted_plan", "guardrails", "archetype:reviewer", "role_card:code_reviewer"} <= sources
    assert "Code Reviewer" in text  # the dispatched role card is part of the contract


@pytest.mark.parametrize("command", [("whoami",), ("submit", "--kind", "implementation_report", "--file", "report.md")],
                         ids=["whoami", "submit"])
def test_a_role_with_no_credential_is_told_to_stop_never_to_get_one(calc, tmp_path, command):
    """The one statement a role with neither a bridge nor a credential reads (no preamble, and its pack is silent).
    `check run` takes the same path: tests/unit/test_pack_truth.py holds it there, in process, since a refusal of it
    through the CLI would be a new key for D2's capture."""
    impl = assign(calc, create_planned_ticket(calc, tmp_path))
    (impl.workspace / "report.md").write_text("---\nclaim: c\n---\n", encoding="utf-8", newline="\n")
    refused = run_aew("-C", str(impl.workspace), *command)
    assert refused.error["code"] == "USAGE", refused.stderr
    assert refused.error["message"] == NO_INVOCATION_AUTHORITY


def test_the_refusals_pointer_for_a_role_run_by_hand_covers_it(calc, tmp_path):
    """`aew whoami --help` is where the refusal sends someone running a role by hand: it names how to supply the
    credential, and supplied that way the command works."""
    impl = assign(calc, create_planned_ticket(calc, tmp_path))
    shown = run_aew("-C", str(impl.workspace), "whoami", "--help").stdout
    assert "--invocation-token" in shown and "AEW_INVOCATION_TOKEN" in shown
    assert impl.aew("whoami").returncode == 0


def _for_ticket_review(p, tmp_path) -> Role:
    wid, impl, out = to_review(p, tmp_path)
    return Role(p, out["invocation_token"], impl.workspace)


def _for_ticket_verification(p, tmp_path) -> Role:
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    return Role(p, p.lead("invoke", "create", wid, "--role", "verifier")["invocation_token"], impl.workspace)


def _for_integration_verification(p, tmp_path) -> Role:
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    out = p.lead("invoke", "create", wid, "--role", "verifier", "--scope", "integration")
    return Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["integration"]["workspace"]))


def _executor(card: str):
    return lambda p, tmp_path: dispatch(p, create_investigation(p, tmp_path, card=card))[0]


def _for_record_verification(p, tmp_path) -> Role:
    wid = create_investigation(p, tmp_path, cls=2)
    p.lead("work", "staff", wid, "--verify", "verifier")
    role, _ = dispatch(p, wid)
    p.lead("evidence", "ingest", wid, "--evidence", submit_record(role, "discovery_record")["evidence"])
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    out = p.lead("invoke", "create", wid, "--role", "verifier")
    return Role(p, out["invocation_token"], Path(out["observation"]["path"]))


def _of_a_story(role: str):
    def build(p, tmp_path) -> Role:
        story = create_unit(p, "story", "Understand calc", cls=1)
        plan_unit(p, tmp_path, story, "Investigate, then decide.\n")
        complete_investigation(p, create_investigation(p, tmp_path, parent=story))
        out = p.lead("invoke", "create", story, "--role", role)
        return Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    return build


def _copied_report(p, role: Role, invocation: str) -> dict[str, Any]:
    """The report format in the role's own pack, as it stands, with only the ids filled in that a model would have to
    get from its own run: the checks it ran and the findings it resolves. Everything else is copied."""
    pack = p.aew("context", "show", invocation).stdout
    fence = re.search(r"^```markdown\n---\n(.*?)\n---\n", pack, re.S | re.M)
    assert fence, pack
    meta = load_yaml(fence.group(1))
    if "review" in meta:
        meta["review"]["resolved_findings"] = []
    for claim in (meta.get("verification") or {}).get("claims", []):
        claim["checks"] = []
    return meta


@pytest.mark.parametrize(("arch", "build"), [
    ("implementer", lambda p, tmp_path: assign(p, create_planned_ticket(p, tmp_path))),
    ("reviewer", _for_ticket_review),
    ("reviewer", _of_a_story("reviewer")),
    ("verifier", _for_ticket_verification),
    ("verifier", _for_integration_verification),
    ("verifier", _for_record_verification),
    ("verifier", _of_a_story("verifier")),
    ("investigator", _executor("investigator")),
    ("researcher", _executor("researcher")),
    ("planner", _executor("planner")),
], ids=["implementer", "reviewer-ticket", "reviewer-parent", "verifier-ticket", "verifier-integration",
        "verifier-observation", "verifier-parent", "investigator", "researcher", "planner"])
def test_a_report_copied_from_its_pack_is_accepted(tmp_path, arch, build):
    """The defects this replaces: a `pass  # or: blocked` value quoted whole, and a verifier's offered scope, which
    a parent or an observation verifier could only get refused by copying."""
    p = sample_project(tmp_path)
    role = build(p, tmp_path)
    who = role.ok("whoami")
    kind = OUTPUT_TEMPLATES[arch][0]
    assert role.submit(kind, _copied_report(p, role, who["invocation"]), "A body.\n")["evidence"]


WRITING_CHECKS = {"schema": "aew/checks/v1", "baseline_failures": [], "checks": {
    "unit": {"configured": True, "command": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]},
    "codegen": {"configured": True, "command": ["{python}", "-c", "open('calc/generated.py','w').write('X=1\\n')"]}}}


def _says_what_the_engine_does(role: Role, out: dict[str, Any], submit: Any, refusal: str) -> None:
    """CHECK_WRITES_NOTE, both ways: in a sandbox the write fails and nothing is lost; without one it lands, the check
    is inconclusive and the submission is refused. Which applies depends on the host, so each holds where it applies."""
    if out["mutated_inputs"]:
        assert out["result"] == "inconclusive", out
        assert submit().error["code"] == refusal
    else:
        assert out["exit_code"] != 0 and out["result"] == "fail", out
        assert submit().returncode == 0


def test_a_check_that_writes_into_an_observation_does_what_the_pack_says(tmp_path):
    p = sample_project(tmp_path, checks=WRITING_CHECKS)
    role, _ = dispatch(p, create_investigation(p, tmp_path))
    assert CHECK_WRITES_NOTE in p.aew("context", "show", role.ok("whoami")["invocation"]).stdout
    _says_what_the_engine_does(role, role.check("codegen"),
                               lambda: submit_record(role, "discovery_record", expect_ok=False), "OBSERVATION_MUTATED")


def test_a_check_that_writes_into_a_verified_workspace_does_what_the_pack_says(tmp_path):
    p = sample_project(tmp_path, checks=WRITING_CHECKS)
    role = _for_ticket_verification(p, tmp_path)
    assert CHECK_WRITES_NOTE in p.aew("context", "show", role.ok("whoami")["invocation"]).stdout
    claims = [{"type": kind, "claim": "c", "result": "pass"} for kind in ("goal_backwards", "contract")]
    _says_what_the_engine_does(role, role.check("codegen"),
                               lambda: role.submit("verification", {"claim": "c", "verification": {"claims": claims}},
                                                   expect_ok=False), "WORKSPACE_MUTATED")


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


def test_a_pack_quotes_only_the_adopted_guardrails(calc, tmp_path):
    """The policy pin (PR #118 review, N2): a pack's guardrails text and its recorded hashes come from the adopted
    bytes, so an edit nobody adopted never reaches the agent; adopting it does."""
    wid, impl, out = to_review(calc, tmp_path)
    inv = out["invocation"]
    guardrails = calc.root / ".aew/policy/guardrails.yaml"
    guardrails.write_bytes(guardrails.read_bytes() + b"# UNADOPTED-GUARDRAIL-EDIT-5K\n")
    res = calc.aew("context", "pack", inv)
    assert res.error["code"] == "INTEGRITY_ERROR", res.error
    assert "UNADOPTED-GUARDRAIL-EDIT-5K" not in (calc.root / ".aew" / out["pack"]["path"]).read_text(encoding="utf-8")
    calc.adopt_policy("the reviewed guardrails edit")
    regen = calc.ok("context", "pack", inv)
    assert "UNADOPTED-GUARDRAIL-EDIT-5K" in Path(regen["path"]).read_text(encoding="utf-8")
