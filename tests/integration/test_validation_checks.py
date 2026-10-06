"""Checks-mode post-integration validation (M4-D5; the M4-D5 plan, revision 3; ADR-0004 and ADR-0003 amendments).

With ``gates.post_integration.validation`` resolving to ``checks``, ``aew integrate validate`` runs the policy's
post-integration checks on the candidate under the entry's lease, with no model, and records engine-produced
``check_result`` evidence. These tests drive the engine in process, so that the containment the mode requires can be
stood in for on any platform (``contained``); the real sandbox is exercised on Linux at the end of the file. The
oracle (rules 34-42) runs after every step that changes state.
"""

from __future__ import annotations

import errno
import shutil
import sys
import threading
from pathlib import Path

import pytest
from aewflow import create_unit, sample_project, to_commit_ready, verify
from conftest import git
from invariants import assert_control_invariants, load_control

from aew.engine import validation_ops as VO
from aew.engine.api import Engine
from aew.errors import GateUnsatisfied
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.util import dump_yaml, load_yaml

CONTAINED = {"filesystem": "os_readonly_roots", "process_ownership": "pid_namespace", "network": "shared",
             "mechanism": "test stand-in"}


@pytest.fixture
def calc(tmp_path):
    return sample_project(tmp_path)


@pytest.fixture
def contained(monkeypatch):
    """Stand in for Linux containment: the engine believes the integration worktree is immutable for the run."""
    monkeypatch.setattr(VO.Validation, "containment_available", lambda self: True)
    monkeypatch.setattr(VO.Validation, "establish", lambda self, *, workspace, run_dir: (None, dict(CONTAINED)))


def engine(p) -> Engine:
    eng = Engine(p.root, p.root / ".aew")
    eng._validation.backoff_s = 0.0
    return eng


def validate(p, wid, **kw):
    return engine(p).integrate_validate(token=p.token, expect_rev=p.rev(), work_id=wid, **kw)


def control(p) -> dict:
    return load_control(p.root)


def integ(p, wid) -> dict:
    return control(p)["work"][wid]["integration"]


def entry(p, wid):
    return next((e for e in (control(p).get("queue") or {}).get("entries", {}).values() if e["work"] == wid), None)


def py(code: str) -> list[str]:
    return ["{python}", "-c", code]


def policy(p, *, checks: dict | None = None, post: list[str] | None = None, validation=None, deadline=None,
           execution: dict | None = None) -> None:
    """Configure checks mode: extra check definitions, the post-integration check list and the validation setting."""
    pol = p.root / ".aew/policy"
    c = load_yaml((pol / "checks.yaml").read_text(encoding="utf-8"))
    c["checks"].update(checks or {})
    (pol / "checks.yaml").write_text(dump_yaml(c), encoding="utf-8", newline="\n")
    g = load_yaml((pol / "gates.yaml").read_text(encoding="utf-8"))
    g["post_integration"] = {"verification": True, "checks": ["smoke"] if post is None else post,
                             "validation": "checks" if validation is None else validation}
    if deadline:
        g["post_integration"]["validation_deadline_s"] = deadline
    (pol / "gates.yaml").write_text(dump_yaml(g), encoding="utf-8", newline="\n")
    if execution is not None:
        e = load_yaml((pol / "execution.yaml").read_text(encoding="utf-8"))
        e.update(execution)
        (pol / "execution.yaml").write_text(dump_yaml(e), encoding="utf-8", newline="\n")


SMOKE = {"smoke": {"configured": True, "command": py("import calc.core"), "cwd": ".", "timeout_s": 60}}


def prepared(p, tmp_path, **kw) -> str:
    wid, _ = to_commit_ready(p, tmp_path, **kw)
    assert p.lead("integrate", "prepare", wid)["ok"]
    return wid


# --------------------------------------------------------------------------------------------- the happy path

def test_checks_mode_validates_and_publishes_with_no_model(calc, tmp_path, contained):
    policy(calc, checks=SMOKE, post=["smoke", "guardrails"])
    wid = prepared(calc, tmp_path)
    out = validate(calc, wid)
    assert out["ok"] and out["result"] == "pass" and out["integration"] == "validated", out
    run = integ(calc, wid)["current_validation_run"]
    assert run["state"] == "committed" and run["id"].startswith("IV-")
    evs = {e["id"]: e for e in E.scan(calc.root / ".aew", wid)[0]}
    for eid in out["evidence"]:
        ev = evs[eid]
        assert ev["kind"] == "check_result" and ev["result"] == "pass"
        assert ev["producer"] == {"kind": "engine", "invocation": run["custodian"], "validation_run": run["id"]}
        assert ev["integration_validation"]["obligation_binding"] == run["identity"]["obligation"]["binding"]
        assert ev["method"]["containment"] == "os_readonly_roots"
    # No verifier ran: no integration-scope role invocation exists.
    assert not [i for i in control(calc)["invocations"].values() if i.get("scope") == "integration"]
    assert_control_invariants(calc)
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"
    assert_control_invariants(calc)


def test_a_committed_run_is_reused_only_for_the_exact_identity(calc, tmp_path, contained):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    first = validate(calc, wid)
    again = validate(calc, wid)
    assert again["noop"] and again["run"] == first["run"] and again["evidence"] == first["evidence"]
    # Same candidate, changed check definition: a new run, and publish refuses the old evidence meanwhile.
    policy(calc, checks={"smoke": {**SMOKE["smoke"], "timeout_s": 61}})
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.returncode != 0 and res.error["code"] == "GATE_UNSATISFIED", res.stdout
    second = validate(calc, wid)
    assert not second.get("noop") and second["run"] != first["run"] and second["result"] == "pass"
    # Every run is kept, immutable: the first one's record survives the second.
    runs = integ(calc, wid)["validation_runs"]["ids"]
    assert runs == [first["run"], second["run"]]
    for rid in runs:
        assert (calc.root / ".aew/work" / wid / "validation-runs" / f"{rid}.yaml").is_file()
    assert_control_invariants(calc)
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"


# --------------------------------------------------------------------------------------------- each result path

def test_a_failing_check_is_verification_failed_from_engine_evidence_alone(calc, tmp_path, contained):
    policy(calc, checks={**SMOKE, "broken": {"configured": True, "command": py("raise SystemExit(1)"), "cwd": ".",
                                             "timeout_s": 60}}, post=["smoke", "broken"])
    wid = prepared(calc, tmp_path)
    out = validate(calc, wid)
    assert out["result"] == "fail" and out["transition"]["to"] == "VERIFICATION_FAILED", out
    unit = control(calc)["work"][wid]
    assert unit["state"] == "VERIFICATION_FAILED" and unit["integration"]["status"] == "validation_failed"
    kinds = {e["kind"] for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine"}
    assert kinds == {"check_result"}  # no verification evidence is manufactured
    assert unit["history"][-1]["to"] == "VERIFICATION_FAILED"
    # The failure pointer names the failing check, though a passing one ran first (PR #91 review, finding 5).
    assert "-check-broken-" in unit["last_verification"]["evidence"], unit["last_verification"]
    assert entry(calc, wid) is None  # the entry retires with the Ticket, as for a failed verifier
    assert_control_invariants(calc)


def test_a_timeout_is_inconclusive_and_releases_the_entry_to_disposition(calc, tmp_path, contained):
    policy(calc, checks={"slow": {"configured": True, "command": py("import time; time.sleep(30)"), "cwd": ".",
                                  "timeout_s": 1}}, post=["slow"])
    wid = prepared(calc, tmp_path)
    out = validate(calc, wid)
    assert out["result"] == "inconclusive", out
    assert control(calc)["work"][wid]["state"] == "COMMIT_READY"
    assert integ(calc, wid)["status"] == "validation_inconclusive"
    assert entry(calc, wid)["state"] == "AWAITING_DISPOSITION"
    assert control(calc)["queue"]["lease"] is None
    assert_control_invariants(calc)


def test_a_missing_executable_is_unavailable_with_no_retry_and_the_queue_moves_on(calc, tmp_path, contained):
    policy(calc, checks={"ghost": {"configured": True, "command": ["aew-no-such-executable-d5"], "cwd": ".",
                                   "timeout_s": 60}}, post=["ghost"])
    from test_queue_disposition import tickets  # two independent COMMIT_READY Tickets

    a, b = tickets(calc, tmp_path, 2)
    assert calc.lead("integrate", "prepare", a)["ok"]
    out = validate(calc, a)
    assert out["unavailable"] and out["code"] == "CHECK_EXECUTABLE_MISSING" and out["attempts"] == 1, out
    assert out["proofs"] == {"ref_unchanged": True, "candidate_unchanged": True}
    assert integ(calc, a)["current_validation_run"]["state"] == "unavailable"
    assert entry(calc, a)["state"] == "AWAITING_DISPOSITION" and control(calc)["queue"]["lease"] is None
    assert not [e for e in E.scan(calc.root / ".aew", a)[0] if e["producer"].get("kind") == "engine"]
    assert calc.lead("integrate", "prepare", b)["ok"]  # the independent entry behind it integrates meanwhile
    assert_control_invariants(calc)


# ------------------------------------------------------------------------------- correction 3: containment

def test_without_immutable_source_containment_checks_mode_is_refused_and_nothing_moves(calc, tmp_path):
    policy(calc, checks=SMOKE, execution={"containment": {"mode": "allow_weaker"}})
    wid = prepared(calc, tmp_path)
    rev, before = calc.rev(), entry(calc, wid)
    res = calc.aew("integrate", "validate", wid, "--token", calc.token, "--expect-rev", str(rev))
    assert res.returncode != 0 and res.error["code"] == "VALIDATION_CONTAINMENT_UNAVAILABLE", res.stdout
    assert calc.rev() == rev and entry(calc, wid) == before and "current_validation_run" not in integ(calc, wid)


def test_a_diagnostic_run_is_advisory_only(calc, tmp_path):
    policy(calc, checks=SMOKE, execution={"containment": {"mode": "allow_weaker"}})
    wid = prepared(calc, tmp_path)
    out = calc.lead("integrate", "validate", wid, "--diagnostic")
    assert out["diagnostic"] and out["advisory"][0]["result"] == "pass", out
    assert integ(calc, wid)["status"] == "prepared"
    assert integ(calc, wid)["diagnostic_run"]["state"] == "advisory"  # its own slot (PR #91 review, finding 4)
    assert not [e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine"]
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.returncode != 0  # advisory results never satisfy validation
    assert_control_invariants(calc)


# ---------------------------------------------------------------- correction 1: the obligation binding is pinned

def test_an_obligation_imposed_while_the_checks_run_abandons_the_run(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    real = VO.Validation._execute

    def execute(self, work_id, run):
        out = real(self, work_id, run)
        policy(calc, validation={"by_class": {}, "default": "verifier"})  # the class now needs a verifier
        return out

    monkeypatch.setattr(VO.Validation, "_execute", execute)
    out = validate(calc, wid)
    assert out["abandoned"] == "STALE_OBLIGATION" and not out["ok"], out
    assert integ(calc, wid)["status"] == "prepared"
    assert not [e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine"]
    monkeypatch.setattr(VO.Validation, "_execute", real)
    with pytest.raises(GateUnsatisfied):
        validate(calc, wid)  # the mode is now verifier: checks mode is refused
    assert_control_invariants(calc)


def test_an_operational_change_during_the_run_does_not_abandon_it(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    real = VO.Validation._execute

    def execute(self, work_id, run):
        out = real(self, work_id, run)
        policy(calc, execution={"containment": {"mode": "required", "hide": ["~/.aew-d5-extra"]}})
        return out

    monkeypatch.setattr(VO.Validation, "_execute", execute)
    assert validate(calc, wid)["result"] == "pass"


def test_an_inherited_integration_verifier_obligation_refuses_checks_mode(calc, tmp_path, contained):
    policy(calc, checks=SMOKE, post=["unit"])  # the check the verifier helper cites
    story = create_unit(calc, "story", "Story", cls=2, extra=("--mandatory-gate", "post_integration_verifier"))
    wid, _ = to_commit_ready(calc, tmp_path, extra=("--parent", story))
    assert calc.lead("integrate", "prepare", wid)["ok"]
    with pytest.raises(GateUnsatisfied) as caught:
        validate(calc, wid)
    assert caught.value.details["code_reason"] == "VERIFIER_OBLIGATION" and story in caught.value.details["sources"][0]
    # The verifier path still works, and publish accepts it.
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, scope="integration"))
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"


def test_a_class_zero_child_under_a_higher_class_story_may_use_checks(calc, tmp_path, contained):
    policy(calc, checks=SMOKE, validation={"by_class": {"0": "checks", "1": "checks"}, "default": "verifier"})
    story = create_unit(calc, "story", "Story", cls=2)
    wid, _ = to_commit_ready(calc, tmp_path, cls=1, extra=("--parent", story))
    assert calc.lead("integrate", "prepare", wid)["ok"]
    assert validate(calc, wid)["result"] == "pass"


# --------------------------------------------------- correction 2 and the crash table: durable, exact runs

def counting_check(tmp_path) -> tuple[dict, Path]:
    counter = tmp_path / "runs.txt"
    return {"count": {"configured": True, "cwd": ".", "timeout_s": 60,
                      "command": py(f"open({str(counter)!r}, 'a').write('x')")}}, counter


def test_a_finished_but_uncommitted_run_is_ingested_without_rerunning(calc, tmp_path, contained, monkeypatch):
    checks, counter = counting_check(tmp_path)
    policy(calc, checks=checks, post=["count"])
    wid = prepared(calc, tmp_path)
    monkeypatch.setenv("AEW_FAULT", "validate.after_finished")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    from aew.engine.faults import InjectedFault

    with pytest.raises(InjectedFault):
        validate(calc, wid)
    monkeypatch.delenv("AEW_FAULT")
    assert integ(calc, wid)["current_validation_run"]["state"] == "running"
    with pytest.raises(VO.ValidationRunning):  # its executor (this process) is alive: a second run is refused
        validate(calc, wid)
    monkeypatch.setattr(VO, "executor_alive", lambda run: False)  # now the executor is gone
    out = validate(calc, wid)
    assert out["result"] == "pass" and counter.read_text() == "x", out  # one execution, ingested
    assert_control_invariants(calc)


def test_an_interrupted_run_is_abandoned_and_counts_as_an_attempt(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    monkeypatch.setenv("AEW_FAULT", "validate.before_check")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    from aew.engine.faults import InjectedFault

    with pytest.raises(InjectedFault):
        validate(calc, wid)
    monkeypatch.delenv("AEW_FAULT")
    monkeypatch.setattr(VO, "executor_alive", lambda run: False)
    out = validate(calc, wid)
    assert out["abandoned"] == "VALIDATION_INTERRUPTED", out
    out = validate(calc, wid)  # within the bound: a new run
    assert out["result"] == "pass" and integ(calc, wid)["current_validation_run"]["infra_attempt"] == 2
    assert_control_invariants(calc)


def test_a_lost_lease_while_the_checks_run_records_nothing_satisfying(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    real = VO.Validation._execute

    def execute(self, work_id, run):
        out = real(self, work_id, run)
        calc.lead("integrate", "defer", wid, "--reason", "set aside while the checks ran")
        return out

    monkeypatch.setattr(VO.Validation, "_execute", execute)
    out = validate(calc, wid)
    assert not out["ok"] and out["abandoned"] == "SUPERSEDED", out  # deferring retired the candidate and its run
    assert not [e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine"]
    retired = control(calc)["work"][wid]["integration_history"][-1]["current_validation_run"]
    assert retired["state"] == "abandoned" and retired["reason"] == "SUPERSEDED"
    # ...and its immutable record, written in the retiring transaction (PR #91 review, finding 6).
    assert (calc.root / ".aew" / retired["record"]["path"]).is_file()
    assert_control_invariants(calc)


# --------------------------------------------------------------------------- correction 4: the hard deadline

def test_a_hung_run_is_ended_at_its_deadline_and_its_late_commit_is_refused(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE, deadline=20)
    wid = prepared(calc, tmp_path)
    started, release = threading.Event(), threading.Event()
    real = VO.Validation._execute
    killed: list[int] = []
    monkeypatch.setattr(VO.procs, "kill_pid", lambda pid: killed.append(pid))

    def hang(self, work_id, run):
        out = real(self, work_id, run)
        started.set()
        release.wait(30)  # the executor hangs after its checks, before transaction 2
        return out

    monkeypatch.setattr(VO.Validation, "_execute", hang)
    results: list = []
    t = threading.Thread(target=lambda: results.append(validate(calc, wid)))
    t.start()
    assert started.wait(30)
    with pytest.raises(VO.ValidationRunning):
        validate(calc, wid)
    run = integ(calc, wid)["current_validation_run"]
    import time

    while not VO._past(run["deadline_at"]):  # wait out the deadline
        time.sleep(0.5)
    run_id = run["id"]
    out = validate(calc, wid)
    assert out["abandoned"] == "VALIDATION_DEADLINE_EXPIRED" and killed, out
    assert entry(calc, wid)["state"] == "LEASED"  # the deadline never releases the lease by itself
    release.set()
    t.join(30)
    assert results[0]["abandoned"] == "SUPERSEDED" and results[0]["run"] == run_id  # its late commit: refused
    assert not [e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine"]
    assert_control_invariants(calc)


def test_a_check_past_the_deadline_is_killed_and_the_run_released_through_disposition(calc, tmp_path, contained):
    policy(calc, checks={"slow": {"configured": True, "command": py("import time; time.sleep(60)"), "cwd": ".",
                                  "timeout_s": 300}}, post=["slow"], deadline=2)
    wid = prepared(calc, tmp_path)
    out = validate(calc, wid)
    assert out["unavailable"] and out["code"] == "VALIDATION_DEADLINE_EXPIRED", out
    assert integ(calc, wid)["current_validation_run"]["state"] == "abandoned"
    assert entry(calc, wid)["state"] == "AWAITING_DISPOSITION"
    assert_control_invariants(calc)
    # The Lead's disposition may requeue it: QUEUED after the release is legal (re-review R2, oracle rule 43).
    calc.lead("integrate", "requeue", wid, "--reason", "the slow check is fixed")
    assert entry(calc, wid)["state"] == "QUEUED"
    assert_control_invariants(calc)


def _runs_in(value) -> list[dict]:
    """Every validation run record anywhere in a document (an archive bundle's shape is not this test's concern)."""
    if isinstance(value, dict):
        found = [value] if str(value.get("id", "")).startswith("IV-") and "state" in value else []
        return found + [r for v in value.values() for r in _runs_in(v)]
    if isinstance(value, list):
        return [r for v in value for r in _runs_in(v)]
    return []


def test_publishing_through_the_verifier_ends_a_run_left_running(calc, tmp_path, contained, monkeypatch):
    """Re-review R1: a checks run interrupted before the Lead validated through the verifier ends with the
    publication, abandoned and recorded, never archived as running."""
    policy(calc, checks=SMOKE, post=["unit"])  # the check the verifier helper cites
    wid = prepared(calc, tmp_path)
    monkeypatch.setenv("AEW_FAULT", "validate.before_check")
    monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    from aew.engine.faults import InjectedFault

    with pytest.raises(InjectedFault):
        validate(calc, wid)
    monkeypatch.delenv("AEW_FAULT")
    assert integ(calc, wid)["current_validation_run"]["state"] == "running"
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, scope="integration"))
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"
    # The DONE Ticket is archived out of the hot state: its bundle is what keeps the run for good.
    bundle = load_yaml((calc.root / ".aew/work" / wid / "archive.yaml").read_text(encoding="utf-8"))
    text = dump_yaml(bundle)
    assert "state: running" not in text, "a run is archived as running"
    run = next(r for r in _runs_in(bundle) if r.get("id", "").startswith("IV-"))
    assert run["state"] == "abandoned" and run["reason"] == "SUPERSEDED", run
    assert (calc.root / ".aew" / run["record"]["path"]).is_file()
    assert_control_invariants(calc)


# ----------------------------------------------------- infrastructure: allow-list, backoff, circuit breaker

def spawn_failure(monkeypatch, codes: list[int]):
    real = C.run

    def run(cfg, workspace, env=None, layout=None, trees=None):
        if codes:
            code = codes.pop(0)
            return {"exit_code": None, "duration_s": 0.0, "log": f"$ x\nfailed to start: [Errno {code}]",
                    "command": ["x"], "outcome": "spawn_failed", "spawn_errno": code}
        return real(cfg, workspace, env=env, layout=layout, trees=trees)

    monkeypatch.setattr(C, "run", run)


@pytest.mark.skipif(not hasattr(errno, "ETXTBSY"), reason="ETXTBSY")
def test_an_allow_listed_transient_failure_is_retried_once(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    spawn_failure(monkeypatch, [errno.ETXTBSY])
    out = validate(calc, wid)
    assert out["result"] == "pass", out
    ids = integ(calc, wid)["validation_runs"]["ids"]
    assert len(ids) == 2 and integ(calc, wid)["current_validation_run"]["infra_attempt"] == 2
    assert_control_invariants(calc)


def test_resource_exhaustion_and_unknown_failures_are_not_retried(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    spawn_failure(monkeypatch, [errno.ENOMEM])
    out = validate(calc, wid)
    assert out["unavailable"] and out["code"] == "SPAWN_RESOURCE_EXHAUSTED", out
    assert len(integ(calc, wid)["validation_runs"]["ids"]) == 1


def test_clustered_failures_trip_the_breaker_and_only_the_operator_resets_it(calc, tmp_path, contained, monkeypatch):
    policy(calc, checks=SMOKE)
    from test_queue_disposition import tickets

    wids = tickets(calc, tmp_path, 3)
    spawn_failure(monkeypatch, [errno.ENOMEM] * 3)
    for wid in wids:
        assert calc.lead("integrate", "prepare", wid)["ok"]
        validate(calc, wid)
    status = engine(calc).integrate_breaker_status()
    assert status["open"] and len(status["failures"]) == 3, status
    assert_control_invariants(calc)
    # A transient failure now goes straight to disposition: no automatic retry while the breaker is open.
    if hasattr(errno, "ETXTBSY"):
        calc.lead("integrate", "requeue", wids[0], "--reason", "environment fixed")
        assert calc.lead("integrate", "prepare", wids[0])["ok"]
        spawn_failure(monkeypatch, [errno.ETXTBSY])
        out = validate(calc, wids[0])
        assert out["unavailable"] and out["breaker_open"], out
    res = calc.aew("integrate", "breaker", "reset", "--reason", "fixed", "--token", calc.token, "--expect-rev",
                   str(calc.rev()))
    assert res.returncode != 0  # no terminal here: the operator's typed-back confirmation is required
    out = engine(calc).integrate_breaker_reset(token=calc.token, expect_rev=calc.rev(), reason="fixed",
                                               authorization={"authorized_by": "operator-tty", "challenge_code": "T"})
    assert out["was_open"] and not engine(calc).integrate_breaker_status()["open"]
    assert_control_invariants(calc)


# ------------------------------------------------------------------------------------------- the rebuild

def test_the_rebuild_retires_the_validation_and_validate_reruns_on_the_new_candidate(calc, tmp_path, contained):
    from test_queue_disposition import outside_commit

    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    first = validate(calc, wid)
    outside_commit(calc)
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.json["rebuilt"] and "aew integrate validate" in res.json["next"], res.stdout
    second = validate(calc, wid)
    assert second["result"] == "pass" and second["run"] != first["run"]
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"
    assert_control_invariants(calc)


# ---------------------------------------------------------------------------------------- the producer rules

def _record(**producer):
    return {"schema": "aew/evidence/v1", "id": "T-1", "kind": "check_result", "work_unit": "T-0001",
            "producer": producer, "created_at": "2026-10-05T00:00:00Z",
            "evaluated_snapshot": {"base_revision": "x", "workspace_id": "w", "relevant_inputs_fingerprint": "f"},
            "method": {}, "claim": "c", "result": "pass"}


def test_engine_evidence_stays_in_its_lane():
    from aew.errors import ValidationFailed

    E.seal(_record(kind="engine", invocation="IA-0001", validation_run="IV-0001-1"), "")
    E.seal(_record(role="implementer", invocation="INV-0001"), "")  # no kind: a role's, as before
    for bad in (_record(kind="engine", invocation="IA-0001"),  # no validation run
                _record(kind="engine", invocation="IA-0001", validation_run="IV-0001-1", role="verifier"),
                {**_record(kind="engine", invocation="IA-0001", validation_run="IV-0001-1"), "kind": "verification"},
                _record(invocation="INV-0001")):  # a role's record needs its role
        with pytest.raises(ValidationFailed):
            E.seal(bad, "")


def test_a_submitter_can_never_claim_the_engine_producer():
    from aew.errors import ValidationFailed

    with pytest.raises(ValidationFailed):
        E.check_submission("implementer", "implementation_report",
                           {"producer": {"kind": "engine"}, "result": "pass", "implementation": {}})


# ------------------------------------------------------------------------- Linux: the real sandbox, end to end

@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None,
                    reason="Linux bubblewrap containment")
def test_linux_checks_run_contained_and_a_write_to_the_candidate_is_refused(calc, tmp_path):
    attack = py("import pathlib, sys\n"
                "try:\n    pathlib.Path('calc/core.py').write_text('tampered')\nexcept OSError:\n    sys.exit(0)\n"
                "sys.exit(3)")
    policy(calc, checks={**SMOKE, "attack": {"configured": True, "command": attack, "cwd": ".", "timeout_s": 60}},
           post=["smoke", "attack"])
    wid = prepared(calc, tmp_path)
    before = git("rev-parse", "HEAD", cwd=Path(integ(calc, wid)["workspace"]))
    out = calc.lead("integrate", "validate", wid)
    assert out["result"] == "pass", out  # the write was refused by the OS, so the attack check exits 0
    assert git("rev-parse", "HEAD", cwd=Path(integ(calc, wid)["workspace"])) == before
    assert (Path(integ(calc, wid)["workspace"]) / "calc/core.py").read_text() != "tampered"
    ev = next(e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine")
    assert ev["method"]["containment"] == "os_readonly_roots"
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"
    assert_control_invariants(calc)


def test_a_policy_choosing_checks_with_no_checks_is_inconsistent(calc):
    from aew.policy import consistency, validation

    gates = {"post_integration": {"verification": True, "checks": [], "validation": "checks"}}
    assert validation.policy_problems(gates)
    assert any("checks-mode" in p for p in consistency.problems(gates, {"checks": {}}, set()))


# ---------------------------------------------------------------------------------- PR #91 review findings

def test_the_checks_execute_the_definition_that_was_pinned(calc, tmp_path, contained, monkeypatch):
    """Finding 1: policy edited while the checks run, and restored before transaction 2, never changes what ran."""
    failing = {"configured": True, "command": py("raise SystemExit(1)"), "cwd": ".", "timeout_s": 60}
    policy(calc, checks={"gate": failing}, post=["gate"])
    wid = prepared(calc, tmp_path)
    real = VO.Validation._one_check

    def swap(self, run, check_id, *a, **k):
        policy(calc, checks={"gate": {**failing, "command": py("raise SystemExit(0)")}}, post=["gate"])  # would pass
        try:
            return real(self, run, check_id, *a, **k)
        finally:
            policy(calc, checks={"gate": failing}, post=["gate"])  # restored before transaction 2 re-verifies

    monkeypatch.setattr(VO.Validation, "_one_check", swap)
    out = validate(calc, wid)
    assert out["result"] == "fail", out  # the pinned definition ran, and its digest is what the evidence carries
    ev = next(e for e in E.scan(calc.root / ".aew", wid)[0] if e["producer"].get("kind") == "engine")
    assert ev["method"]["command"][-1] == "raise SystemExit(1)"
    assert ev["check"]["definition_sha256"] == C.definition_digest(failing)


def test_checks_mode_with_no_checks_never_validates(calc, tmp_path, contained):
    """Finding 2: an empty check set is refused before pinning and at publication, never a vacuous pass."""
    policy(calc, checks=SMOKE, post=[])
    wid = prepared(calc, tmp_path)
    with pytest.raises(GateUnsatisfied) as caught:
        validate(calc, wid)
    assert caught.value.details["code_reason"] == "VALIDATION_CHECKS_EMPTY"
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.returncode != 0 and res.error["code"] == "GATE_UNSATISFIED", res.stdout
    assert control(calc)["work"][wid]["state"] == "COMMIT_READY"


def test_each_ancestors_minimum_class_rule_is_checked_on_its_own():
    """Finding 3: a Story's floor 4 mapped to checks must not hide an Epic's floor 3 mapped to a verifier."""
    from aew.policy import validation as V

    state = {"work": {"T-1": {"risk_class": 4, "parent": "S-1"},
                      "S-1": {"parent": "E-1", "policy": {"min_descendant_class": 4}},
                      "E-1": {"policy": {"min_descendant_class": 3}}}}
    gates = {"post_integration": {"verification": True, "checks": ["smoke"],
                                  "validation": {"by_class": {"3": "verifier", "4": "checks"}}}}
    ob = V.obligation(state, "T-1", gates)
    assert ob["mode"] == "verifier" and ob["verifier_required"], ob
    assert any(s.startswith("E-1 ") for s in ob["sources"]) and not any(s.startswith("S-1 ") for s in ob["sources"])


def test_a_diagnostic_run_never_displaces_the_satisfying_validation(calc, tmp_path, contained):
    """Finding 4: an advisory run has its own slot; the validation publication relies on is untouched."""
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    passed = validate(calc, wid)
    advisory = validate(calc, wid, diagnostic=True)
    assert advisory["diagnostic"] and not advisory.get("evidence"), advisory
    integration = integ(calc, wid)
    assert integration["current_validation_run"]["id"] == passed["run"]
    assert integration["diagnostic_run"]["state"] == "advisory"
    assert_control_invariants(calc)
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"


# ------------------------------------------------------------------------------------- PR #91 re-review findings

def _gates(p, **post) -> None:
    pol = p.root / ".aew/policy/gates.yaml"
    g = load_yaml(pol.read_text(encoding="utf-8"))
    g["post_integration"] = post
    pol.write_text(dump_yaml(g), encoding="utf-8", newline="\n")


def test_with_no_checks_listed_a_verifiers_pass_still_publishes(calc, tmp_path, contained):
    """Re-review finding 1: checks mode with an empty list refuses checks, never the verifier the refusal points to."""
    policy(calc, checks=SMOKE, post=[])
    wid = prepared(calc, tmp_path)
    with pytest.raises(GateUnsatisfied):
        validate(calc, wid)
    calc.lead("verify", "ingest", wid, "--evidence", verify(calc, wid, scope="integration"))
    assert integ(calc, wid)["status"] == "validated"
    assert calc.lead("integrate", "publish", wid)["state"] == "DONE"


def test_a_checks_validation_never_publishes_once_policy_lists_no_checks(calc, tmp_path, contained):
    """Re-review finding 4: a candidate validated by its checks, after policy empties the list and turns verification
    off, is refused at publication (VALIDATION_CHECKS_EMPTY), never published as 'nothing required'."""
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    assert validate(calc, wid)["result"] == "pass" and integ(calc, wid)["status"] == "validated"
    _gates(calc, verification=False, checks=[], validation="checks")
    res = calc.aew("integrate", "publish", wid, "--token", calc.token, "--expect-rev", str(calc.rev()))
    assert res.returncode != 0 and res.error["code"] == "GATE_UNSATISFIED", res.stdout
    assert res.error["details"]["code_reason"] == "VALIDATION_CHECKS_EMPTY", res.error
    assert control(calc)["work"][wid]["state"] == "COMMIT_READY"


def test_a_diagnostic_run_never_spends_or_ends_the_authoritative_attempts(calc, tmp_path, contained, monkeypatch):
    """Re-review finding 2: with the authoritative attempt bound used up, a diagnostic run is still only advisory: it
    never releases the lease or marks the candidate unavailable."""
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    from aew.engine.faults import InjectedFault

    monkeypatch.setattr(VO, "executor_alive", lambda run: False)
    for _ in range(2):  # two interrupted authoritative runs: the bound is used up
        monkeypatch.setenv("AEW_FAULT", "validate.before_check")
        monkeypatch.setenv("AEW_FAULT_MODE", "raise")
        with pytest.raises(InjectedFault):
            validate(calc, wid)
        monkeypatch.delenv("AEW_FAULT")
        assert validate(calc, wid)["abandoned"] == "VALIDATION_INTERRUPTED"
    advisory = validate(calc, wid, diagnostic=True)
    assert advisory["diagnostic"], advisory
    assert entry(calc, wid)["state"] == "LEASED" and integ(calc, wid)["status"] == "prepared"
    assert_control_invariants(calc)


def test_a_deadline_found_at_commit_is_counted_by_the_breaker(calc, tmp_path, contained, monkeypatch):
    """Re-review finding 3: a run whose deadline passed while its checks ran, found by its own transaction 2, is an
    infrastructure failure for the breaker, as the same expiry found by a later call is."""
    policy(calc, checks=SMOKE)
    wid = prepared(calc, tmp_path)
    real = VO.Validation._execute
    executed = {"done": False}

    def execute(self, work_id, run):
        out = real(self, work_id, run)
        executed["done"] = True  # from here on, the deadline has passed
        return out

    monkeypatch.setattr(VO.Validation, "_execute", execute)
    monkeypatch.setattr(VO, "_past", lambda stamp: executed["done"])
    out = validate(calc, wid)
    assert out["abandoned"] == "VALIDATION_DEADLINE_EXPIRED", out
    breaker = control(calc)["queue"]["validation_breaker"]
    assert [f["code"] for f in breaker["failures"]] == ["VALIDATION_DEADLINE_EXPIRED"], breaker
    assert "breaker_open" in integ(calc, wid)["current_validation_run"]
    assert entry(calc, wid)["state"] == "LEASED"
    assert_control_invariants(calc)
