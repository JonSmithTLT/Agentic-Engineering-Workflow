"""M3 acceptance scenarios AT-14..AT-17 (ADR-0009, ADR-0010; M3 plan §5 step 6), stated once for every harness.

Each scenario takes a ``Driver`` (``harness_conformance.py``): in CI the fake harness and the real OpenCode adapter
against the fake V2 server (``tests/acceptance/test_at14_at17_harness.py``); in the live lane the real OpenCode
2.0.18 server with a free model (``tests/live/test_opencode_acceptance_live.py``).

The Lead acts through its own harness session wherever the scenario is about the Lead (AT-14, AT-15, AT-17):
``aew lead session`` (harness-neutral) or ``aew opencode`` (a fake TUI in CI). Every role is a harness run. The
scenarios assert AEW-side outcomes only: state, evidence, run records, files, processes and what each harness
received.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import yaml
from aewflow import SUBTRACT_PATCH, create_planned_ticket
from conftest import git
from fake_harness import IMPL_REPORT, HarnessLab, contains_credential, credential_hits, run_contained
from harness_conformance import (
    PROVIDER_SECRET,
    Driver,
    Scenario,
    code_of,
    evidence_of,
    kill_harness,
    supervisor_gone,
    sync_dir,
)
from invariants import assert_control_invariants

from aew.engine.api import Engine
from aew.harness import bridge, lead_broker, runlog
from aew.util import dump_yaml

WID = "T-0001"
PLAN = "1. Add subtract(a, b) to calc/core.py.\n2. Add a focused test.\n"
TICKET = ["work", "create", "ticket", "--title", "Add subtract()", "--class", "1",
          "--goal", "calc.core.subtract(5, 3) == 2 through the public module",
          "--contract", "changes stay within calc/ and tests/; vendored code untouched",
          "--scope", "calc/**", "--scope", "tests/**"]
REVIEW_PASS = {"claim": "independent review of the change against plan and contracts",
               "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}
NEGATIVE_TEST = (SUBTRACT_PATCH["tests/test_subtract.py"] + "\n\ndef test_subtract_negative():\n"
                 "    from calc.core import subtract\n\n    assert subtract(1, 3) == -2\n")


# ---------------------------------------------------------------------------------------------- the Lead's steps

def lead(*args: str) -> dict[str, Any]:
    """A Lead command at the current revision, through the Lead session's broker."""
    return {"do": "lead", "args": list(args)}


def wait(run: str) -> dict[str, Any]:
    return {"do": "aew", "args": ["harness", "wait", run, "--timeout", "600"]}


def plan_ticket(tmp_path: Path) -> list[dict[str, Any]]:
    """The Lead turns an objective into a planned Ticket."""
    plan = tmp_path / "lead-plan.md"
    return [{"do": "write", "files": {str(plan): PLAN}}, lead(*TICKET),
            lead("plan", "propose", "--assurance", "none", WID, "--file", str(plan), "--affected", "calc/core.py"),
            lead("plan", "accept", WID, "--revision", "1")]


def review_to_done(first: int) -> list[dict[str, Any]]:
    """The Lead's steps from a reported implementation to DONE. The reviewer, the verifier and the integration
    verifier are harness runs of INV-<first>, INV-<first+1> and INV-<first+2>; the Lead ingests what they
    recorded, reading the ids from ``harness wait``."""
    reviewer, verifier, integration = (f"R-INV-{n:04d}-1" for n in (first, first + 1, first + 2))
    return [lead("work", "transition", WID, "--to", "REVIEW_PENDING"),
            lead("invoke", "create", WID, "--role", "reviewer", "--launch"), wait(reviewer),
            lead("review", "ingest", WID, "--evidence", "{evidence:review}"),
            lead("work", "transition", WID, "--to", "VERIFY_PENDING"),
            lead("invoke", "create", WID, "--role", "verifier", "--launch"), wait(verifier),
            lead("verify", "ingest", WID, "--evidence", "{evidence:verify}"),
            lead("work", "transition", WID, "--to", "COMMIT_READY"),
            lead("integrate", "prepare", WID),
            lead("invoke", "create", WID, "--role", "verifier", "--scope", "integration", "--launch"),
            wait(integration),
            lead("verify", "ingest", WID, "--evidence", "{evidence:verify}"),
            lead("integrate", "publish", WID)]


# ---------------------------------------------------------------------------------------------- the roles' steps

def identify(sync: Path, run: str) -> list[dict[str, Any]]:
    """Steps 0-2 of every role run: who am I, where am I, and one model turn (a real prompt in the live lane)."""
    return [{"do": "aew", "args": ["whoami"]}, {"do": "cwd", "path": str(sync / f"{run}.cwd")}, {"do": "model_step"}]


def implement(files: dict[str, str] | None = None) -> list[dict[str, Any]]:
    files = files or SUBTRACT_PATCH
    report = {**IMPL_REPORT, "implementation": {**IMPL_REPORT["implementation"], "files_changed": sorted(files)}}
    return [{"do": "write", "files": files}, {"do": "check", "id": "unit"},
            {"do": "submit", "kind": "implementation_report", "meta": report}]


def verify(scope: str) -> list[dict[str, Any]]:
    """A verifier runs its checks and cites its own check results (read from their output)."""
    checks = [{"do": "check", "id": "unit"}] + ([{"do": "check", "id": "guardrails"}] if scope == "ticket" else [])
    claims = [{"type": "goal_backwards", "claim": "subtract(5, 3) == 2 observed through the focused tests",
               "result": "pass", "checks": ["{evidence:check-unit}"]}]
    if scope == "ticket":
        claims.append({"type": "contract", "claim": "guardrails and scope respected", "result": "pass",
                       "checks": ["{evidence:check-guardrails}"]})
    return [*checks, {"do": "submit", "kind": "verification", "meta": {
        "claim": "the requested behavior exists in the evaluated snapshot",
        "verification": {"scope": scope, "claims": claims}}}]


def script_review_to_done(lab: HarnessLab, driver: Driver, sync: Path, first: int) -> None:
    reviewer, verifier, integration = (f"R-INV-{n:04d}-1" for n in (first, first + 1, first + 2))
    driver.script(lab, reviewer, [*identify(sync, reviewer), {"do": "submit", "kind": "review", "meta": REVIEW_PASS}])
    driver.script(lab, verifier, [*identify(sync, verifier), *verify("ticket")])
    driver.script(lab, integration, [*identify(sync, integration), *verify("integration")])


# ---------------------------------------------------------------------------------------------- assertions

def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def profile_of(pin: dict[str, Any]) -> dict[str, Any]:
    return {k: pin.get(k) for k in ("provider", "model", "effort")}


def policy_profiles(lab: HarnessLab) -> dict[str, Any]:
    return yaml.safe_load((lab.root / ".aew/policy/execution.yaml").read_text(encoding="utf-8"))["profiles"]


def route_reviewers(lab: HarnessLab, profile: dict[str, Any]) -> None:
    """Execution policy: reviewers run on their own profile (ADR-0010 routing)."""
    path = lab.root / ".aew/policy/execution.yaml"
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    policy["profiles"]["review"] = profile
    policy["routing"]["archetypes"]["reviewer"] = "review"
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")


def tokens(lab: HarnessLab) -> dict[str, Any]:
    return Engine.discover(lab.root).store.read()["tokens"]


def lead_session_ok(res: Any, steps: dict[int, dict[str, Any]]) -> None:
    """Every Lead command succeeded, and nothing the operator or the Lead's model saw holds a credential."""
    assert res.returncode == 0, res.stderr
    failed = {i: s for i, s in steps.items() if s.get("exit") not in (None, 0)}
    assert not failed, failed
    assert not contains_credential(res.stdout + res.stderr + json.dumps(steps))


def assert_role_run(lab: HarnessLab, driver: Driver, sync: Path, run: str, *, role: str, scope: str,
                    profile: dict[str, Any]) -> dict[str, Any]:
    """AT-14's per-run properties: the intended role, workspace (cwd), context, model and effort; correlation from
    the run to its session, its invocation and every piece of evidence it recorded."""
    inv = run.rsplit("-", 1)[0][2:]
    record = lab.record(run)
    assert record["status"] == "ended_with_evidence", record
    who = lab.step(run, 0)["stdout_json"]
    assert (who["invocation"], who["run"], who["role"], who["work_unit"], who["scope"]) == (inv, run, role, WID, scope)
    assert profile_of(who["execution_profile"]) == profile_of(profile)
    contract = record["contract"]
    assert same_path((sync / f"{run}.cwd").read_text(encoding="utf-8"), contract["workspace"])
    shown = lab.ok("invoke", "show", inv)
    assert contract["pack_sha256"] == shown["pack"]["sha256"]
    prompt = driver.delivered_prompt(lab, run)
    if prompt is not None:  # the harness received the preamble and exactly the pinned pack
        pack = Path(contract["pack_path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(pack.encode("utf-8")).hexdigest() == contract["pack_sha256"]
        assert prompt.startswith(f"# AEW harness run {run}") and pack in prompt
    check = record["model_check"]
    assert check["status"] == "match" and profile_of(check["requested"]) == profile_of(profile), check
    assert record["launch"]["session"]
    evidence = evidence_of(lab, WID, run)
    assert evidence, f"{run} recorded no evidence"
    for ev in evidence:
        producer = ev["producer"]
        assert (producer["run"], producer["invocation"], producer["role"]) == (run, inv, role)
        assert producer["credential"] == shown["runs"][-1]["token_id"]
        assert producer["execution_profile"] == who["execution_profile"]
    row = next(r for r in lab.ok("harness", "status")["runs"] if r["run"] == run)
    assert (row["invocation"], row["role"], row["work_unit"]) == (inv, role, WID)
    assert row["evidence"] == sorted(e["id"] for e in evidence)
    return record


def files_containing(root: Path, text: str, *, skip: tuple[Path, ...] = ()) -> list[str]:
    hits = []
    if not root.exists():
        return hits
    for path in root.rglob("*"):
        if path.is_file() and not any(path.is_relative_to(s) for s in skip):
            try:
                if text in path.read_bytes().decode("utf-8", "replace"):
                    hits.append(str(path))
            except OSError:
                pass
    return hits


def rmtree(path: Path) -> None:
    """Delete a directory tree (Windows: a file closed a moment ago can still be held briefly)."""
    for _ in range(50):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.2)
    shutil.rmtree(path)


def operator_takeover(lab: HarnessLab, reason: str) -> str:
    """The operator authorizes a takeover at their own terminal. The terminal channel is substituted in-process
    (the pty path itself is tested in test_authority.py); the semantics under test are identical."""
    import aew.operator

    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        return Engine.discover(lab.root).lead_takeover(expect_rev=lab.project.rev(), reason=reason,
                                                       session_label="operator")["token"]
    finally:
        aew.operator.authorize = original


# ---------------------------------------------------------------------------------------------- AT-14

def at14_ticket_end_to_end(lab: HarnessLab, driver: Driver, tmp_path: Path) -> None:
    """AT-14: a Ticket from objective to DONE through harnesses. The Lead's own harness session plans, dispatches
    with --launch, follows the runs and ingests what they recorded; the implementer, the reviewer (on its own
    execution profile), the verifier and the post-integration verifier are each a harness run with the intended
    role, workspace, context and model/effort, correlated from run to session to evidence."""
    sync = sync_dir(tmp_path)
    standard = policy_profiles(lab)["standard"]
    review_profile = driver.review_profile or standard
    if driver.review_profile:
        route_reviewers(lab, driver.review_profile)
    driver.script(lab, "R-INV-0001-1", [*identify(sync, "R-INV-0001-1"), *implement()])
    script_review_to_done(lab, driver, sync, 2)
    res, steps = driver.lead(lab, "lead-at14", [
        *plan_ticket(tmp_path),
        lead("work", "assign", WID, "--launch"),                              # 4
        lead("work", "transition", WID, "--to", "RUNNING"),
        wait("R-INV-0001-1"),                                                 # 6
        *review_to_done(2),
        {"do": "aew", "args": ["resume", "--json"]}])
    lead_session_ok(res, steps)
    assigned = steps[4]["stdout_json"]
    assert assigned["launch"]["run"] == "R-INV-0001-1" and "invocation_token" not in assigned
    assert steps[6]["stdout_json"]["status"] == "ended_with_evidence"

    assert_role_run(lab, driver, sync, "R-INV-0001-1", role="implementer", scope="ticket", profile=standard)
    assert_role_run(lab, driver, sync, "R-INV-0002-1", role="reviewer", scope="ticket", profile=review_profile)
    assert_role_run(lab, driver, sync, "R-INV-0003-1", role="verifier", scope="ticket", profile=standard)
    integration = assert_role_run(lab, driver, sync, "R-INV-0004-1", role="verifier", scope="integration",
                                  profile=standard)
    runs = ["R-INV-0001-1", "R-INV-0002-1", "R-INV-0003-1", "R-INV-0004-1"]
    assert len({lab.record(r)["launch"]["session"] for r in runs}) == 4  # a fresh session per invocation

    assert lab.ok("work", "show", WID)["control"]["state"] == "DONE"
    published = steps[max(steps) - 1]["stdout_json"]
    assert published["state"] == "DONE" and git("rev-parse", "main", cwd=lab.root) == published["integrated_commit"]
    assert "def subtract" in git("show", "main:calc/core.py", cwd=lab.root)
    assert not same_path(integration["contract"]["workspace"], lab.record("R-INV-0001-1")["contract"]["workspace"])
    final = steps[max(steps)]["stdout_json"]
    assert final["contradictions"] == [] and final.get("harness_runs", []) == []
    assert {w["id"]: w["state"] for w in final["work"]} == {WID: "DONE"}
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- AT-15

def at15_disposable_harness(lab: HarnessLab, driver: Driver, tmp_path: Path) -> None:
    """AT-15: the harness is disposable. A run dies mid-work from outside; every piece of harness state is wiped
    (the run's sessions and database, the run records, the packs: all of ``.aew/local``); a fresh Lead session
    reconstructs from ``aew resume``, relaunches (the credential rotates; the new run continues from durable state
    only) and completes the Ticket. Harness loss is not an interruption (M3-B1), and the superseded session, revived
    with everything it had, has no authority."""
    sync = sync_dir(tmp_path)
    r1, r2 = "R-INV-0001-1", "R-INV-0001-2"
    driver.script(lab, r1, [
        {"do": "dump_env", "path": str(sync / "r1-env")}, {"do": "aew", "args": ["whoami"]},
        {"do": "write", "files": {"calc/core.py": SUBTRACT_PATCH["calc/core.py"]}},  # half the work ...
        {"do": "check", "id": "unit"},                                              # ... and a recorded check
        {"do": "touch", "path": str(sync / "r1-ready")},
        {"do": "wait_file", "path": str(sync / "never"), "timeout": 900}])
    res, steps = driver.lead(lab, "lead-at15-a", [
        *plan_ticket(tmp_path), lead("work", "assign", WID, "--launch"),
        lead("work", "transition", WID, "--to", "RUNNING"),
        {"do": "wait_file", "path": str(sync / "r1-ready"), "timeout": 600}])
    lead_session_ok(res, steps)
    assert steps[max(steps)]["found"], "run 1 never got going"

    # --- the harness dies from outside; nothing in AEW moves -------------------------------------------------
    rev = lab.project.rev()
    kill_harness(lab, r1)
    assert lab.wait(r1)["status"] == "crashed"
    record = lab.record(r1)
    lab.until(lambda: supervisor_gone(record), 30, "run 1's supervisor to exit")
    assert lab.project.rev() == rev
    assert lab.ok("work", "show", WID)["control"]["state"] == "RUNNING"          # not INTERRUPTED (M3-B1)
    old_token = lab.ok("invoke", "show", "INV-0001")["runs"][0]["token_id"]
    assert not tokens(lab)[old_token].get("revoked_at")
    [check] = evidence_of(lab, WID, r1)

    # --- wipe every piece of harness state; someone keeps a copy of the dead session's --------------------------
    copy = tmp_path / "r1-harness-copy"
    shutil.copytree(driver.state_dir(lab, r1), copy)
    rmtree(lab.aew_root / "local")
    assert not runlog.run_dir(lab.aew_root, r1).exists()

    # --- a fresh Lead session: resume and relaunch ------------------------------------------------------------
    driver.script(lab, r2, [{"do": "aew", "args": ["whoami"]}, {"do": "cwd", "path": str(sync / f"{r2}.cwd")},
                            {"do": "model_step"}, *implement()])
    res, steps = driver.lead(lab, "lead-at15-b", [
        {"do": "aew", "args": ["resume", "--json"]},
        {"do": "aew", "args": ["harness", "status"]},
        # The run's local record is gone, so AEW cannot rule out a live supervisor: --replace revokes its credential
        # either way (rotation).
        lead("harness", "launch", "INV-0001", "--replace"),
        wait(r2)])
    lead_session_ok(res, steps)
    resumed = steps[0]["stdout_json"]
    assert {w["id"]: w["state"] for w in resumed["work"]} == {WID: "RUNNING"}
    [hr] = resumed["harness_runs"]
    assert (hr["invocation"], hr["run"], hr["status"], hr["evidence"]) == ("INV-0001", r1, "unconfirmed",
                                                                          [check["id"]])
    assert hr["action"].startswith("INV-0001 has no live run") and "relaunch" in hr["action"]
    [row] = steps[1]["stdout_json"]["runs"]
    assert (row["status"], row["authority"]) == ("unconfirmed", "current")  # loss revoked nothing
    launched = steps[2]["stdout_json"]
    assert (launched["run"], launched["superseded"]) == (r2, r1)

    contract = lab.record(r2)["contract"]
    assert contract["continuation"] == {"previous_runs": [r1], "changed_paths": ["calc/core.py"],
                                        "evidence": [{"id": check["id"], "kind": "check_result", "result": "pass"}]}
    prompt = driver.delivered_prompt(lab, r2)
    if prompt is not None:
        assert "## Continuation" in prompt and check["id"] in prompt and r1 in prompt
    assert lab.step(r2, 0)["stdout_json"]["run"] == r2
    assert tokens(lab)[old_token]["revoke_reason"] == f"rotated: {r2}"

    # --- the superseded session, revived with everything it had, has no authority ------------------------------
    old_env = json.loads((sync / "r1-env").read_text(encoding="utf-8"))
    workspace = record["contract"]["workspace"]
    report = tmp_path / "late-report.md"
    report.write_text(f"---\n{yaml.safe_dump(IMPL_REPORT)}---\nlate\n", encoding="utf-8")
    for argv in (["whoami"], ["submit", "--kind", "implementation_report", "--file", report.as_posix()]):
        out = driver.revive(lab, state_copy=copy, session=record["launch"]["session"], workspace=workspace,
                            old_env=old_env, argv=argv)
        assert "STALE_AUTHORITY" in out, out
    assert [e["id"] for e in evidence_of(lab, WID, r1)] == [check["id"]]

    # --- the Lead completes the Ticket (from yet another session: the Lead's sessions are disposable too) --------
    script_review_to_done(lab, driver, sync, 2)
    res, steps = driver.lead(lab, "lead-at15-c", [*review_to_done(2), {"do": "aew", "args": ["resume", "--json"]}])
    lead_session_ok(res, steps)
    control = lab.ok("work", "show", WID)["control"]
    assert control["state"] == "DONE"
    assert {e["producer"]["run"] for e in evidence_of(lab, WID) if e["kind"] == "implementation_report"} == {r2}
    final = steps[max(steps)]["stdout_json"]
    assert final["contradictions"] == [] and final.get("harness_runs", []) == []
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- AT-16

SCRATCH = "IMPLEMENTER-SCRATCH-7f3a: left out the negative case; the reviewer will not look"
FINDING = {"id": "F1", "severity": "major", "summary": "no test covers a negative result", "required": True}


def at16_isolated_review(lab: HarnessLab, driver: Driver, tmp_path: Path) -> None:
    """AT-16: review is isolated. Implementer, reviewer, rework implementer and re-reviewer are each a fresh
    session with private harness state. The implementer's own conversation (a remark it made) reaches no one; what
    crosses between them is AEW state only (the report, the diff, the open finding). A reviewer cannot change the
    code it reviews (WORKSPACE_MUTATED), and review results move nothing until the Lead ingests them."""
    sync = sync_dir(tmp_path)
    impl1, rev1, impl2, rev2 = "R-INV-0001-1", "R-INV-0002-1", "R-INV-0003-1", "R-INV-0004-1"
    create_planned_ticket(lab.project, tmp_path)
    driver.script(lab, impl1, [*identify(sync, impl1), {"do": "note", "text": SCRATCH}, *implement()])
    lab.lead("work", "assign", WID, "--launch")
    lab.lead("work", "transition", WID, "--to", "RUNNING")
    assert lab.wait(impl1)["status"] == "ended_with_evidence"
    [report] = [e for e in evidence_of(lab, WID, impl1) if e["kind"] == "implementation_report"]
    lab.lead("work", "transition", WID, "--to", "REVIEW_PENDING")

    tidied = SUBTRACT_PATCH["calc/core.py"] + "\n\n# reviewer tidy-up\n"
    driver.script(lab, rev1, [
        *identify(sync, rev1),
        {"do": "write", "files": {"calc/core.py": tidied}},                                     # 3
        {"do": "submit", "kind": "review", "meta": REVIEW_PASS},                                # 4: refused
        {"do": "write", "files": {"calc/core.py": SUBTRACT_PATCH["calc/core.py"]}},             # 5: put back
        {"do": "submit", "kind": "review", "meta": {"claim": "the negative case is untested", "review": {
            "independence": "R1", "disposition": "changes_required", "findings": [FINDING],
            "resolved_findings": []}}}])
    lab.lead("invoke", "create", WID, "--role", "reviewer", "--launch")
    assert lab.wait(rev1)["status"] == "ended_with_evidence"
    if run_contained(lab, rev1):  # M4-B: the reviewer's source is read-only, so its edit is refused where it is made
        assert lab.step(rev1, 3)["refused"] == {"calc/core.py": "EROFS"}
        assert lab.step(rev1, 5)["refused"] == {"calc/core.py": "EROFS"}
        review1 = next(e for e in evidence_of(lab, WID, rev1) if e["review"]["disposition"] == "changes_required")
    else:  # uncontained, the edit happens and the review of edited code is refused
        refused = lab.step(rev1, 4)
        assert code_of(refused) == "WORKSPACE_MUTATED" and "calc/core.py" in refused["stderr"], refused
        [review1] = evidence_of(lab, WID, rev1)
    assert review1["review"]["disposition"] == "changes_required"
    assert review1["evaluated_snapshot"]["relevant_inputs_fingerprint"] == \
        report["evaluated_snapshot"]["relevant_inputs_fingerprint"]
    assert lab.ok("work", "show", WID)["control"]["state"] == "REVIEW_PENDING"  # a review run decides nothing
    assert lab.lead("review", "ingest", WID, "--evidence", review1["id"])["transition"]["to"] == "REVIEW_FAILED"
    finding = f"{review1['id']}#F1"

    lab.lead("work", "transition", WID, "--to", "RUNNING")
    driver.script(lab, impl2, [*identify(sync, impl2), *implement({"tests/test_subtract.py": NEGATIVE_TEST})])
    lab.lead("invoke", "create", WID, "--role", "implementer", "--launch")
    assert lab.wait(impl2)["status"] == "ended_with_evidence"
    lab.lead("work", "transition", WID, "--to", "REVIEW_PENDING")
    driver.script(lab, rev2, [*identify(sync, rev2), {"do": "submit", "kind": "review", "meta": {
        **REVIEW_PASS, "review": {**REVIEW_PASS["review"], "resolved_findings": [finding]}}}])
    lab.lead("invoke", "create", WID, "--role", "reviewer", "--launch")
    assert lab.wait(rev2)["status"] == "ended_with_evidence"
    [review2] = evidence_of(lab, WID, rev2)
    assert lab.lead("review", "ingest", WID, "--evidence", review2["id"])["transition"]["to"] == "REVIEW_PASSED"

    runs = [impl1, rev1, impl2, rev2]
    roles = [lab.step(r, 0)["stdout_json"]["role"] for r in runs]
    invocations = [lab.step(r, 0)["stdout_json"]["invocation"] for r in runs]
    assert roles == ["implementer", "reviewer", "implementer", "reviewer"] and len(set(invocations)) == 4
    sessions = [lab.record(r)["launch"]["session"] for r in runs]
    assert len(set(sessions)) == 4
    for run, session in zip(runs, sessions, strict=True):
        assert driver.sessions(lab, run) == {session}  # each run's harness state: its own session, nothing else
    dirs = [driver.state_dir(lab, r).resolve() for r in runs]
    assert all(not a.is_relative_to(b) for a in dirs for b in dirs if a != b)

    # The implementer's own remark stayed in its own conversation; nothing else ever carried it.
    assert files_containing(driver.state_dir(lab, impl1), SCRATCH)
    for run in runs[1:]:
        assert not files_containing(driver.state_dir(lab, run), SCRATCH)
        assert SCRATCH not in (driver.delivered_prompt(lab, run) or "")
    assert not files_containing(lab.aew_root, SCRATCH, skip=(lab.aew_root / "local",))  # never AEW state
    # What crossed was AEW state: the open finding reached the rework and the re-review through their packs.
    for run in (impl2, rev2):
        prompt = driver.delivered_prompt(lab, run)
        if prompt is not None:
            assert finding in prompt and FINDING["summary"] in prompt
    for run, may_edit in ((impl1, True), (rev1, False), (impl2, True), (rev2, False)):
        config = driver.projection(lab, run)
        if config is None:
            continue
        edits = [r["effect"] for r in config["permissions"] if r["action"] == "edit"]
        assert edits[-1] == ("allow" if may_edit else "deny"), (run, edits)
        others = [r for r in runs if r != run]
        for rule in config["permissions"]:
            if rule["effect"] == "allow" and rule["action"] == "external_directory":
                assert run in rule["resource"] and not any(o in rule["resource"] for o in others), rule
    assert_control_invariants(lab.project)


# ---------------------------------------------------------------------------------------------- AT-17

def env_blobs(sync: Path, prefix: str) -> tuple[dict[str, str], list[str]]:
    env = json.loads((sync / f"{prefix}-env").read_text(encoding="utf-8"))
    return env, [json.dumps(env), (sync / f"{prefix}-child").read_text(encoding="utf-8"),
                 (sync / f"{prefix}-shell").read_text(encoding="utf-8")]


def at17_credential_custody(lab: HarnessLab, driver: Driver, tmp_path: Path) -> None:
    """AT-17: credential custody end to end, for an invocation and for the Lead. The Lead's session takes the
    vacant seat itself (the Lead credential exists only inside its broker) and dispatches work whose credential
    goes straight to the run's supervisor. Neither model, nor any process either starts, nor any file, nor the
    operator's terminal ever holds a raw credential; authorized operations work without one; credential-emitting
    commands are refused; a relaunch leaves the old run's bridge dead, and an operator takeover leaves the old Lead
    session's broker dead."""
    sync = sync_dir(tmp_path)
    r1, r2 = "R-INV-0001-1", "R-INV-0001-2"
    lab.lead("lead", "release")  # the operator's own seat is given up: the Lead's session acquires it
    lab.project.token = ""
    roots = [str(lab.root), str(tmp_path)]
    driver.script(lab, r1, [
        {"do": "dump_env", "path": str(sync / "r1-env")},
        {"do": "child_env", "path": str(sync / "r1-child"), "shell_path": str(sync / "r1-shell")},
        {"do": "aew", "args": ["whoami"]}, *implement()[:2],
        {"do": "scan", "out": str(sync / "r1-hits"), "roots": roots},                       # 5
        {"do": "touch", "path": str(sync / "r1-ready")},
        {"do": "wait_file", "path": str(sync / "never"), "timeout": 900}])
    driver.script(lab, r2, [{"do": "aew", "args": ["whoami"]}, *implement()])
    session = driver.start_lead(lab, "lead-custody", [
        {"do": "dump_env", "path": str(sync / "lead-env")},
        {"do": "child_env", "path": str(sync / "lead-child"), "shell_path": str(sync / "lead-shell")},
        *plan_ticket(tmp_path),                                                                 # 2-5
        lead("work", "assign", WID, "--launch"),                                                # 6
        lead("work", "transition", WID, "--to", "RUNNING"),
        {"do": "wait_file", "path": str(sync / "r1-ready"), "timeout": 600},
        lead("harness", "launch", "INV-0001", "--replace"),                                     # 9: rotation
        wait(r2),
        lead("lead", "handoff", "offer"),                                                       # 11
        {"do": "aew", "args": ["lead", "acquire", "--expect-rev", "0"]},                        # 12
        lead("work", "assign", WID),                                                            # 13: no --launch
        lead("checkpoint", "--next", "x", "--token", "{FORGED_CREDENTIAL}"),                    # 14
        {"do": "scan", "out": str(sync / "lead-hits"), "roots": roots},                         # 15
        {"do": "touch", "path": str(sync / "lead-ready")},
        {"do": "wait_file", "path": str(sync / "lead-go"), "timeout": 600},
        lead("checkpoint", "--next", "after the takeover")], acquire=True)                      # 18
    lab.until((sync / "lead-ready").exists, 900, "the Lead session to finish its work")

    # --- while the Lead's session is live: the relaunch left run 1 without authority ---------------------------
    assert lab.wait(r1)["status"] == "terminated" and lab.wait(r2)["status"] == "ended_with_evidence"
    r1_env, r1_blobs = env_blobs(sync, "r1")
    try:
        bridge.call("whoami", {}, endpoint=r1_env[bridge.ENV_ENDPOINT], key=r1_env[bridge.ENV_KEY])
        raise AssertionError("run 1's bridge still answers after the relaunch")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == "STALE_AUTHORITY", exc
    shown = lab.ok("invoke", "show", "INV-0001")
    old, new = (r["token_id"] for r in shown["runs"])
    assert tokens(lab)[old]["revoke_reason"] == f"rotated: {r2}" and not tokens(lab)[new].get("revoked_at")
    assert {e["producer"]["credential"] for e in evidence_of(lab, WID, r2)} == {new}
    assert lab.ok("lead", "show")["session_label"] == "lead-custody"  # the session holds the seat

    # --- the operator takes over at their own terminal: the old Lead session loses its broker ------------------
    lab.project.token = operator_takeover(lab, "AT-17: the operator takes the seat back")
    (sync / "lead-go").touch()
    res, steps = session.result()
    assert res.returncode == 0, res.stderr
    out = res.json
    assert out["exit"] == 0 and out["seat"] == "superseded" and "superseded" in out["superseded"], out
    assert not contains_credential(res.stdout + res.stderr)  # the operator's terminal never showed one
    lead_env, lead_blobs = env_blobs(sync, "lead")
    try:
        bridge.call("lead.cli", {"argv": ["lead", "show"], "cwd": str(lab.root), "stdin": ""},
                    endpoint=lead_env[lead_broker.ENV_ENDPOINT], key=lead_env[lead_broker.ENV_KEY])
        raise AssertionError("the superseded Lead session's broker still answers")
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == "STALE_AUTHORITY", exc

    # 1. authorized operations worked without a credential: the Lead's through its broker, the run's through its
    #    bridge
    assert all(steps[i]["exit"] == 0 for i in (3, 4, 5, 6, 7, 9, 10)), steps
    assert lab.step(r1, 2)["stdout_json"]["run"] == r1 and lab.step(r2, 0)["stdout_json"]["run"] == r2
    assert steps[10]["stdout_json"]["status"] == "ended_with_evidence"
    # ... and no dispatch or launch output carried one
    assert "invocation_token" not in steps[6]["stdout_json"] and "invocation_token" not in steps[9]["stdout_json"]
    # 2-3. neither model's environment, nor a child process, nor a shell holds a credential
    for blob in (*r1_blobs, *lead_blobs):
        assert not contains_credential(blob)
    for blob in r1_blobs:
        assert PROVIDER_SECRET not in blob
    if driver.curated_lead_env:
        for blob in lead_blobs:
            assert PROVIDER_SECRET not in blob
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN"} & (set(r1_env) | set(lead_env))
    assert {bridge.ENV_ENDPOINT, bridge.ENV_KEY} <= set(r1_env)
    assert {lead_broker.ENV_ENDPOINT, lead_broker.ENV_KEY} <= set(lead_env)
    # 4. no file either could reach held one, while they ran (and, below, afterwards)
    assert lab.step(r1, 5)["hits"] == [] and steps[15]["hits"] == []
    # credential-emitting commands are refused in a Lead session; a forged credential is rejected
    assert [code_of(steps[i]) for i in (11, 12, 13, 14)] == ["USAGE", "USAGE", "PERMISSION_DENIED",
                                                             "PERMISSION_DENIED"]
    # 5. after the takeover, the old session's next Lead command is refused
    assert code_of(steps[18]) == "STALE_AUTHORITY", steps[18]
    assert not contains_credential(json.dumps(steps))
    assert not credential_hits(tmp_path)
    assert_control_invariants(lab.project)


ACCEPTANCE = {
    "AT-14": Scenario("at14_ticket_end_to_end", at14_ticket_end_to_end),
    "AT-15": Scenario("at15_disposable_harness", at15_disposable_harness),
    "AT-16": Scenario("at16_isolated_review", at16_isolated_review),
    "AT-17": Scenario("at17_credential_custody", at17_credential_custody),
}
