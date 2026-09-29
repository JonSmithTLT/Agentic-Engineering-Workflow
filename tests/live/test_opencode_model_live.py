"""Live lane, M3 step 8: a free model carries out real launch contracts through the production OpenCode adapter.

Everywhere else in the live lane the agent's actions are scripted (``opencode_scripted.py``). Here nothing is: each
role run is the production ``opencode`` adapter, a real private ``opencode-cli serve`` with private state, and a real
free model (``AEW_LIVE_OPENCODE_MODEL``) that receives the launch contract as its first message and does whatever it
does. The Lead's steps are the test's (a scripted Lead, as in the acceptance scenarios).

A free model may fail the task: that is its outcome, and it is **recorded, not asserted**. What is asserted, whatever
the model does, is AEW's side (the adapter contract and the invariants):

* every run ends in a terminal status the supervisor derived from the evidence store, never from the model's claims,
  and leaves no process behind;
* no AEW credential in any file (the run's own scan and a scan of everything the test left), and the provider secret
  (which the server holds) in no file the runs left, AEW's or OpenCode's;
* the effective model is the pinned model; no other session exists (no subagent);
* every piece of evidence is attributed to its run, credential and execution profile, and verifies;
* no AEW state moves except by the Lead: the unit's state and the invocation are as the Lead left them;
* a read-only role's evidence is never accepted from a workspace it changed (M3-B6).

Two scenarios:

* **The lifecycle.** The flow goes as far as the model gets: implementer; then, if it submitted an implementation
  report, a reviewer; then, if the Lead's ingest passed the review, a verifier.
* **Rejection and rework** (designer request, 2026-09-28). The Ticket's first implementation is seeded: plausible,
  passing its own happy-path test and the unit check, and wrong against the Ticket's goals (floor division where the
  goal says ``safe_div(7, 2) == 3.5``). Every later role is a real model. Whether the independent reviewer (or,
  failing that, the verifier) catches the defect is recorded, not asserted. When one does, the Lead returns the
  Ticket to implementation through its normal authority, a fresh implementer (a new invocation and credential)
  corrects it, and a fresh reviewer and a verifier follow. Asserted, whatever the models do: a failing review does not
  advance the Ticket; the rejected attempt's credential is dead; its stale evidence cannot be ingested for the
  corrected work; at the end every gate is bound to evidence from the corrected snapshot, none from the rejected
  attempt.

``AEW_LIVE_ROUTING`` routes roles to other models (``implementer=opencode/<model>,reviewer=opencode/<model>#<effort>``;
unnamed roles use ``AEW_LIVE_OPENCODE_MODEL``), through the execution policy's per-archetype routing: each invocation
pins its own model at dispatch. ``AEW_LIVE_PROVIDER_KEY_ENV`` names the environment variable of a paid provider's key
(``OPENAI_API_KEY`` for ``openai/...`` models, M3 step 9): the policy names it, the runs' servers receive its real value
(never an agent's shell), and the leak checks look for that value instead of the placeholder.

Each trial's record (outcomes, usage, telemetry, the project's control-state footprint) is appended to
``AEW_LIVE_RESULTS`` if set. Run it with::

    AEW_LIVE_RESULTS=results.jsonl pytest --live tests/live/test_opencode_model_live.py -p no:xdist -q
"""

from __future__ import annotations

import calendar
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from aewflow import assign, create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab, credential_hits
from harness_conformance import FREE_MODEL, NO_WINDOW, PROVIDER_SECRET, evidence_of
from invariants import assert_control_invariants

from aew.harness import contract as K
from aew.harness import procs
from aew.harness.opencode import adapter
from aew.util import parse_frontmatter

pytestmark = pytest.mark.skipif(not os.environ.get(adapter.BIN_ENV) and adapter.default_binary() is None,
                                reason="no OpenCode binary (set AEW_OPENCODE_BIN)")

RESULTS_ENV = "AEW_LIVE_RESULTS"
PAID_KEY_ENV = "AEW_LIVE_PROVIDER_KEY_ENV"
TRIALS = int(os.environ.get("AEW_LIVE_MODEL_TRIALS", "1"))
DEADLINE_S = float(os.environ.get("AEW_LIVE_MODEL_DEADLINE_S", "900"))
MAX_STEPS = 40
ROOT = Path(__file__).resolve().parents[2]


def routing() -> dict[str, str]:
    """``AEW_LIVE_ROUTING``: role -> ``provider/model[#effort]``."""
    spec = os.environ.get("AEW_LIVE_ROUTING", "")
    return dict(item.split("=", 1) for item in spec.split(",") if item.strip())


def profile(ref: str) -> dict[str, Any]:
    target, _, effort = ref.partition("#")
    provider, _, model = target.partition("/")
    return {"provider": provider, "model": model, **({"effort": effort} if effort else {}),
            "max_steps": MAX_STEPS, "deadline_s": DEADLINE_S}


def provider_key() -> tuple[str, str]:
    """The provider variable the policy names and the value its runs' servers get: a paid provider's real key when
    ``AEW_LIVE_PROVIDER_KEY_ENV`` names one, else a placeholder (the free ``opencode/*`` models need none)."""
    name = os.environ.get(PAID_KEY_ENV)
    if not name:
        return "OPENAI_API_KEY", PROVIDER_SECRET
    if not os.environ.get(name):
        pytest.skip(f"{PAID_KEY_ENV}={name}, but {name} is not set")
    return name, os.environ[name]


def model_lab(tmp_path: Path) -> HarnessLab:
    routes = routing()
    key_name, key_value = provider_key()
    profiles = {"standard": profile(FREE_MODEL)}
    archetypes = {}
    for role, ref in sorted(routes.items()):
        profiles[f"{role}-route"] = profile(ref)
        archetypes[role] = f"{role}-route"
    policy = {**POLICY, "harness": "opencode", "provider_env": [key_name], "profiles": profiles,
              "routing": {**POLICY["routing"], "archetypes": archetypes}}
    return HarnessLab.create(sample_project(tmp_path), tmp_path, policy=policy, extra_env={
        key_name: key_value, "AEW_LAUNCH_ACK_S": "240"})


def new_trial(scenario: str, trial: int) -> dict[str, Any]:
    return {"schema": "aew/live-model-trial/v1", "scenario": scenario, "model": FREE_MODEL, "routing": routing(),
            "trial": trial, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider_key": "real" if os.environ.get(PAID_KEY_ENV) else "placeholder",
            "agent_shell": "bash" if os.environ.get("SHELL") else "powershell", "max_steps": MAX_STEPS,
            "deadline_s": DEADLINE_S, "runs": [], "lead": {}}


def finish_trial(tmp_path: Path, trial_record: dict[str, Any]) -> None:
    """Write the trial's record (and append it to ``AEW_LIVE_RESULTS``), then the checks on everything it left."""
    trial_record["ended_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    text = json.dumps(trial_record, sort_keys=True)
    (tmp_path / "trial.json").write_text(text, encoding="utf-8")
    if os.environ.get(RESULTS_ENV):
        with open(os.environ[RESULTS_ENV], "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def git(workspace: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=workspace, capture_output=True, text=True, encoding="utf-8",
                          check=True, **NO_WINDOW).stdout


def changes(workspace: Path, base: str) -> dict[str, Any]:
    """The workspace's changes against the dispatch base (committed or not), and a fingerprint of their content."""
    paths = set(git(workspace, "diff", "--name-only", base).split())
    paths |= set(git(workspace, "ls-files", "--others", "--exclude-standard").split())
    digest = hashlib.sha256(git(workspace, "diff", base).encode("utf-8"))
    for rel in sorted(paths):
        target = workspace / rel
        digest.update(rel.encode() + b"\0" + (target.read_bytes() if target.is_file() else b"<gone>"))
    return {"paths": sorted(paths), "sha256": digest.hexdigest()}


def epoch(stamp: str) -> int:
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def footprint(root: Path) -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("aew_perf_control_plane", ROOT / "tools/perf/control_plane.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.project_footprint(root)


def workspace_of(lab: HarnessLab, wid: str) -> tuple[Path, str]:
    ws = lab.ok("work", "show", wid)["control"]["workspace"]
    return Path(ws["path"]), ws["base_commit"]


def role_run(lab: HarnessLab, wid: str, launch: list[str], *, read_only: bool) -> dict[str, Any]:
    """Dispatch one role with ``--launch``, let the model work, and check AEW's side of it."""
    before = changes(*workspace_of(lab, wid)) if read_only else None  # a reader shares the implementer's workspace
    out = lab.lead(*launch, "--launch")
    return observe(lab, wid, out["invocation"], out["launch"]["run"], before, read_only=read_only)


def relaunch(lab: HarnessLab, wid: str, inv: str, *, read_only: bool) -> dict[str, Any]:
    """The Lead relaunches an invocation whose run ended (a new run, a rotated credential, a continuation)."""
    before = changes(*workspace_of(lab, wid)) if read_only else None
    return observe(lab, wid, inv, lab.lead("harness", "launch", inv)["run"], before, read_only=read_only)


def observe(lab: HarnessLab, wid: str, inv: str, run: str, before: dict[str, Any] | None, *,
            read_only: bool) -> dict[str, Any]:
    """Wait for a run, check AEW's side of it, and return what happened."""
    workspace = lambda: workspace_of(lab, wid)  # noqa: E731
    state = lab.ok("work", "show", wid)["control"]["state"]  # as the Lead's launch left it
    lab.wait(run, timeout=DEADLINE_S + 300)
    record = lab.record(run)
    result = record.get("result") or {}
    after = changes(*workspace())
    changed = after["sha256"] != before["sha256"] if before is not None else bool(after["paths"])
    pin = lab.ok("invoke", "show", inv)
    mine = evidence_of(lab, wid, run)  # verifies every record of the unit (no problems)

    # --- AEW's side: asserted whatever the model did
    status = record["status"]
    assert status in K.TERMINAL and status != K.LAUNCH_FAILED, record
    assert record["credential_scan"] == {"clean": True, "files": []}, record["credential_scan"]
    assert record["model_check"]["status"] in ("match", "no_model_step"), record["model_check"]
    assert result.get("foreign_sessions") == [], result.get("foreign_sessions")
    assert isinstance(result.get("tools_called"), dict) and isinstance(result.get("permission_rejected"), list)
    expected = set(record["contract"]["expected_kinds"])
    produced = {e["kind"] for e in mine}
    if status in (K.ENDED_WITH_EVIDENCE, K.ENDED_WITHOUT_EVIDENCE, K.CRASHED):
        assert (status == K.ENDED_WITH_EVIDENCE) == bool(produced & expected), (status, produced)
    credential_of = {r["run"]: r["token_id"] for r in pin["runs"]}  # each run acts with its own (rotated) credential
    for e in evidence_of(lab, wid):
        if e["producer"].get("invocation") == inv:
            assert e["producer"]["credential"] == credential_of.get(e["producer"]["run"]), e
            assert e["producer"]["execution_profile"] == pin["execution_profile"], e
    assert lab.ok("work", "show", wid)["control"]["state"] == state  # only the Lead moves it
    assert pin["status"] == "active"
    if read_only and changed:
        assert not produced & expected, "a read-only role's evidence was accepted from a workspace it changed"
    lab.until(lambda: not procs.same_process(record.get("supervisor_pid"), epoch(record["custody_at"])), 30,
              "the supervisor to exit")
    for pid in record.get("harness_pids") or []:
        lab.until(lambda pid=pid: not procs.same_process(pid, epoch(record["started_at"])), 30,
                  f"harness process {pid} to exit")
    assert_control_invariants(lab.project)

    # --- the model's side: recorded
    usage = result.get("usage") or {}
    return {"invocation": inv, "run": run, "role": record["contract"]["role"], "status": status,
            "token_id": credential_of.get(run), "continuation": record["contract"].get("continuation"),
            "model": {k: pin["execution_profile"].get(k) for k in ("provider", "model", "effort")},
            "reason": record.get("reason"), "harness_outcome": record.get("harness_outcome"),
            "wall_s": epoch(record["ended_at"]) - epoch(record["started_at"]),
            "model_check": record["model_check"]["status"], "effective": record["model_check"].get("effective"),
            "steps": result.get("steps"), "tools_called": result.get("tools_called"),
            "tokens": usage.get("tokens"), "cost": usage.get("cost"),
            "first_step_input_tokens": result.get("first_step_input_tokens"),
            "context": (record.get("launch") or {}).get("context"),
            "permission_rejected": [r.get("action") for r in result.get("permission_rejected") or []],
            "forms_cancelled": len(result.get("forms_cancelled") or []),
            "bridge": {k: (record.get("bridge") or {}).get(k) for k in ("requests", "refused", "outcomes")},
            "evidence": [{"id": e["id"], "kind": e["kind"], "result": e.get("result")} for e in mine],
            "workspace_changed": changed, "changed_paths": after["paths"]}


def hidden_test(workspace: Path) -> bool:
    """The Ticket's goal, checked independently of anything the model wrote or ran."""
    probe = "import calc.core as c; assert c.subtract(5, 3) == 2 and c.subtract(0, 7) == -7 and c.add(2, 3) == 5"
    res = subprocess.run([sys.executable, "-c", probe], cwd=workspace, capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=60, **NO_WINDOW)
    return res.returncode == 0


def lead_step(lab: HarnessLab, *args: str) -> str:
    """A Lead step whose success depends on the model's evidence: its outcome is recorded."""
    res = lab.lead_res(*args)
    return "ok" if res.returncode == 0 else str((res.error or {}).get("code"))


def of_kind(entry: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((e for e in entry["evidence"] if e["kind"] == kind), None)


@pytest.mark.parametrize("trial", range(TRIALS))
def test_a_free_model_carries_out_real_launch_contracts(trial, tmp_path):
    lab = model_lab(tmp_path)
    trial_record = new_trial("lifecycle", trial)
    try:
        wid = create_planned_ticket(lab.project, tmp_path)
        impl = role_run(lab, wid, ["work", "assign", wid], read_only=False)
        trial_record["runs"].append(impl)
        workspace = Path(lab.ok("work", "show", wid)["control"]["workspace"]["path"])
        trial_record["implementation"] = {"hidden_test": hidden_test(workspace),
                                          "in_scope": all(p.startswith(("calc/", "tests/"))
                                                          for p in impl["changed_paths"])}
        version = (lab.record(impl["run"]).get("launch") or {}).get("version")
        trial_record["opencode"] = version
        if of_kind(impl, "implementation_report"):
            trial_record["lead"]["running"] = lead_step(lab, "work", "transition", wid, "--to", "RUNNING")
            trial_record["lead"]["review_pending"] = lead_step(lab, "work", "transition", wid, "--to",
                                                                "REVIEW_PENDING")
        if trial_record["lead"].get("review_pending") == "ok":
            rev = role_run(lab, wid, ["invoke", "create", wid, "--role", "reviewer"], read_only=True)
            trial_record["runs"].append(rev)
            review = of_kind(rev, "review")
            if review:
                trial_record["lead"]["review_ingest"] = lead_step(lab, "review", "ingest", wid, "--evidence",
                                                                  review["id"])
                trial_record["lead"]["after_review"] = lab.ok("work", "show", wid)["control"]["state"]
        if trial_record["lead"].get("after_review") == "REVIEW_PASSED":
            trial_record["lead"]["verify_pending"] = lead_step(lab, "work", "transition", wid, "--to",
                                                                "VERIFY_PENDING")
            ver = role_run(lab, wid, ["invoke", "create", wid, "--role", "verifier"], read_only=True)
            trial_record["runs"].append(ver)
            verification = of_kind(ver, "verification")
            if verification:
                trial_record["lead"]["verify_ingest"] = lead_step(lab, "verify", "ingest", wid, "--evidence",
                                                                  verification["id"])
        trial_record["final_state"] = lab.ok("work", "show", wid)["control"]["state"]
        trial_record["footprint"] = footprint(lab.root)
    finally:
        lab.cleanup()
        finish_trial(tmp_path, trial_record)
    nothing_leaked(tmp_path)


def nothing_leaked(tmp_path: Path) -> None:
    assert not credential_hits(tmp_path), "a credential string was left in a file"
    secret = provider_key()[1].encode()
    leaked = [str(p) for p in tmp_path.rglob("*") if p.is_file() and secret in p.read_bytes()]
    assert not leaked, leaked


# ---------------------------------------------------------------------------------------------- rejection and rework

SAFE_DIV_GOALS = ["calc.core.safe_div(7, 2) == 3.5", "calc.core.safe_div(1, 0) is None"]
SAFE_DIV_PLAN = "1. Add safe_div(a, b) to calc/core.py: divide a by b; return None when b is 0.\n2. Add focused tests.\n"
# The seeded first attempt: plausible, and wrong. Floor division passes the happy-path test it came with and the unit
# check; compared with the goals, safe_div(7, 2) returns 3, not 3.5.
SEEDED = {
    "calc/core.py": "def add(a, b):\n    return a + b\n\n\ndef safe_div(a, b):\n"
                    "    \"\"\"Divide a by b; None when b is 0.\"\"\"\n    if b == 0:\n        return None\n"
                    "    return a // b\n",
    "tests/test_safe_div.py": "from calc.core import safe_div\n\n\ndef test_safe_div():\n"
                              "    assert safe_div(6, 3) == 2\n    assert safe_div(1, 0) is None\n",
}
SEEDED_REPORT = {"claim": "safe_div(a, b) added with focused tests", "result": "pass",
                 "producer": {"model": "seeded-first-attempt", "harness": "scripted"},
                 "implementation": {"files_changed": sorted(SEEDED), "checks_run": ["unit"], "deviations": [],
                                    "self_review": {"completed": True, "notes": "matches the plan"}}}


def safe_div_ticket(lab: HarnessLab, tmp_path: Path) -> str:
    p = lab.project
    args = ["work", "create", "ticket", "--title", "Add safe_div()", "--class", "1",
            "--contract", "changes stay within calc/ and tests/; vendored code untouched",
            "--scope", "calc/**", "--scope", "tests/**"]
    for goal in SAFE_DIV_GOALS:
        args += ["--goal", goal]
    wid = p.lead(*args)["id"]
    plan = tmp_path / f"{wid}-plan.md"
    plan.write_text(SAFE_DIV_PLAN, encoding="utf-8")
    p.lead("plan", "propose", wid, "--file", str(plan), "--affected", "calc/core.py")
    p.lead("plan", "accept", wid, "--revision", "1")
    return wid


def safe_div_correct(workspace: Path) -> bool:
    """The Ticket's goals, checked independently of anything a model wrote or ran."""
    probe = ("import calc.core as c; assert c.safe_div(7, 2) == 3.5 and c.safe_div(1, 0) is None "
             "and c.safe_div(-7, 2) == -3.5 and c.safe_div(6, 3) == 2 and c.add(2, 3) == 5")
    res = subprocess.run([sys.executable, "-c", probe], cwd=workspace, capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=60, **NO_WINDOW)
    return res.returncode == 0


def sealed_meta(lab: HarnessLab, wid: str, evidence_id: str) -> dict[str, Any]:
    text = (lab.aew_root / "evidence" / wid / f"{evidence_id}.md").read_text(encoding="utf-8")
    return parse_frontmatter(text, source=evidence_id)[0]


def state_of(lab: HarnessLab, wid: str) -> str:
    return lab.ok("work", "show", wid)["control"]["state"]


@pytest.mark.parametrize("trial", range(TRIALS))
def test_a_seeded_defect_is_caught_and_reworked_by_real_models(trial, tmp_path):
    lab = model_lab(tmp_path)
    trial_record = new_trial("rework", trial)
    lead = lab.project.lead
    try:
        wid = safe_div_ticket(lab, tmp_path)
        seeded = assign(lab.project, wid)  # a scripted first implementer: explicit credential, no harness
        seeded.write(SEEDED)
        seeded_check = seeded.check("unit")
        seeded.submit("implementation_report", SEEDED_REPORT, "Implemented per plan v1.\n")
        seeded_inv = lab.ok("work", "show", wid)["control"]["implementer_invocation"]
        workspace = Path(lab.ok("work", "show", wid)["control"]["workspace"]["path"])
        fingerprint = lambda: lab.ok("gate", "show", wid)["snapshot"]["relevant_inputs_fingerprint"]  # noqa: E731
        attempts = [{"implementer": "seeded", "invocation": seeded_inv, "correct": safe_div_correct(workspace),
                     "unit_check": seeded_check["result"], "fingerprint": fingerprint()}]
        trial_record.update(attempts=attempts, reviews=[], verifications=[], probes={})
        lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        rejected: set[str] = set()  # evidence of a rejected attempt: it must never satisfy a gate afterwards

        def reject_current_attempt() -> None:
            rejected.update(e["id"] for e in evidence_of(lab, wid)
                            if e["producer"].get("invocation") == attempts[-1]["invocation"])

        def rework(reason: str) -> bool:
            """The Ticket is back in RUNNING: a fresh implementer (a real model) corrects the work."""
            impl = role_run(lab, wid, ["invoke", "create", wid, "--role", "implementer"], read_only=False)
            trial_record["runs"].append(impl)
            before = {a["invocation"] for a in attempts}
            assert impl["invocation"] not in before  # a new invocation, a new credential, a new run
            attempts.append({"implementer": "model", "invocation": impl["invocation"], "reason": reason,
                             "correct": safe_div_correct(workspace), "fingerprint": fingerprint(),
                             "reported": bool(of_kind(impl, "implementation_report"))})
            if not attempts[-1]["reported"]:
                return False
            outcome = lead_step(lab, "work", "transition", wid, "--to", "REVIEW_PENDING")
            trial_record["lead"].setdefault("to_review_pending", []).append(outcome)
            if outcome == "GATE_UNSATISFIED":  # e.g. its evidence went stale: the Lead relaunches it once
                again = relaunch(lab, wid, impl["invocation"], read_only=False)
                trial_record["runs"].append(again)
                attempts[-1]["relaunch"] = {"run": again["run"], "correct": safe_div_correct(workspace),
                                            "fingerprint": fingerprint(),
                                            "evidence": [e["id"] for e in again["evidence"]]}
                trial_record["lead"]["to_review_pending"].append(
                    lead_step(lab, "work", "transition", wid, "--to", "REVIEW_PENDING"))
            return state_of(lab, wid) == "REVIEW_PENDING"

        for cycle in range(2):  # at most one rework
            rev = role_run(lab, wid, ["invoke", "create", wid, "--role", "reviewer"], read_only=True)
            trial_record["runs"].append(rev)
            review = of_kind(rev, "review")
            if not review:
                break
            meta = sealed_meta(lab, wid, review["id"])["review"]
            outcome = lead_step(lab, "review", "ingest", wid, "--evidence", review["id"])
            after = state_of(lab, wid)
            trial_record["reviews"].append({
                "cycle": cycle, "invocation": rev["invocation"], "evidence": review["id"],
                "disposition": meta.get("disposition"), "ingest": outcome, "state_after": after,
                "findings": [{k: f.get(k) for k in ("id", "severity", "required", "summary")}
                             for f in meta.get("findings") or []],
                "resolved": list(meta.get("resolved_findings") or [])})
            if meta.get("disposition") != "pass":
                assert after == "REVIEW_FAILED", after  # AEW does not advance as though the review passed
            if after == "REVIEW_FAILED":
                reject_current_attempt()
                trial_record["lead"].setdefault("to_running", []).append(
                    lead_step(lab, "work", "transition", wid, "--to", "RUNNING"))
                if state_of(lab, wid) != "RUNNING":
                    break
                if cycle == 0:  # the rejected implementer's credential died when its report was accepted
                    trial_record["probes"]["rejected_implementer_credential"] = (seeded.aew("whoami").error
                                                                                 or {}).get("code")
                    assert trial_record["probes"]["rejected_implementer_credential"] == "STALE_AUTHORITY"
                if cycle == 1 or not rework(f"review {review['id']} failed"):
                    break
                stale = lab.lead_res("review", "ingest", wid, "--evidence", review["id"])
                trial_record["probes"]["stale_review_ingest"] = (stale.error or {}).get("code")
                assert stale.returncode != 0 and state_of(lab, wid) == "REVIEW_PENDING", stale.error
                continue
            if after != "REVIEW_PASSED":
                break
            lead("work", "transition", wid, "--to", "VERIFY_PENDING")
            ver = role_run(lab, wid, ["invoke", "create", wid, "--role", "verifier"], read_only=True)
            trial_record["runs"].append(ver)
            verification = of_kind(ver, "verification")
            if not verification:
                break
            outcome = lead_step(lab, "verify", "ingest", wid, "--evidence", verification["id"])
            after = state_of(lab, wid)
            claims = sealed_meta(lab, wid, verification["id"])["verification"].get("claims") or []
            trial_record["verifications"].append({
                "cycle": cycle, "invocation": ver["invocation"], "evidence": verification["id"],
                "result": verification["result"], "ingest": outcome, "state_after": after,
                "claims": [{k: c.get(k) for k in ("type", "claim", "result")} for c in claims]})
            if after == "VERIFICATION_FAILED" and cycle == 0:
                reject_current_attempt()
                trial_record["lead"]["classify"] = lead_step(
                    lab, "verify", "classify", wid, "--as", "LOCAL_IMPLEMENTATION_DEFECT", "--reason",
                    f"verification {verification['id']} failed against the goals")
                if state_of(lab, wid) != "RUNNING" or not rework(f"verification {verification['id']} failed"):
                    break
                continue
            break

        final = state_of(lab, wid)
        trial_record["final_state"] = final
        trial_record["final_correct"] = safe_div_correct(workspace)
        trial_record["history"] = [(h["from"], h["to"], h.get("reason")) for h in
                                   lab.ok("work", "show", wid)["control"]["history"]]
        shown = {inv: lab.ok("invoke", "show", inv) for inv in lab.ok("work", "show", wid)["control"]["invocations"]}
        trial_record["invocations"] = {inv: {"role": v["role"], "status": v["status"],
                                             "runs": [[r["run"], r["token_id"]] for r in v.get("runs") or []]}
                                       for inv, v in shown.items()}
        trial_record["defect_caught_by"] = next(
            ([r["invocation"], "review"] for r in trial_record["reviews"] if r["state_after"] == "REVIEW_FAILED"),
            next(([v["invocation"], "verification"] for v in trial_record["verifications"]
                  if v["state_after"] == "VERIFICATION_FAILED"), None))
        gates = lab.ok("gate", "show", wid)
        bound = sorted({g.get("evidence") for g in gates["gates"].values() if g.get("evidence")}
                       | {c.get("evidence") for g in gates["gates"].values() for c in (g.get("checks") or {}).values()
                          if c.get("evidence")})
        trial_record["gates"] = {"unmet": gates["unmet"], "bound_evidence": bound,
                                 "fingerprint": gates["snapshot"]["relevant_inputs_fingerprint"]}
        if final == "VERIFIED":  # the corrected work is judged only by evidence about the corrected work
            assert not gates["unmet"], gates["unmet"]
            assert not set(bound) & rejected, set(bound) & rejected
            records = {e["id"]: e for e in evidence_of(lab, wid)}
            for eid in bound:
                snap = records[eid].get("evaluated_snapshot") or {}
                assert snap.get("relevant_inputs_fingerprint") == trial_record["gates"]["fingerprint"], (eid, snap)
            assert trial_record["gates"]["fingerprint"] != attempts[0]["fingerprint"]
        trial_record["footprint"] = footprint(lab.root)
    finally:
        lab.cleanup()
        finish_trial(tmp_path, trial_record)
    nothing_leaked(tmp_path)
