"""The integration stages and the custodian's custody worker (M4-E E6a; plan v3 §2.3, E6a, §6 and §10).

`ticket_prepare` and `integration_publish` run through ``run_tool`` as a Lead's call would. After a grant, the lease's
custodian does the mechanical integration work under its own custody credential, never the Lead's: these tests take
that credential where the engine hands it to the worker (``spawn_worker``) and drive the worker in process
(``Engine.custody_step``), so each step is deterministic; two tests start a real worker process. Checks mode runs in
process with the containment stand-in of ``test_validation_checks`` (the real sandbox is Linux's, tested there).

Covered: VALIDATE_ONLY (a clean validation releases the lease, the candidate kept, and a later publish revalidates on a
moved head), N2 (the custodian validates and routes, never accepts; it holds no Lead credential and commits nothing
once its custody ended), S1 (the custody credential: bound and checked on every commit, refused outside its closed
family, revoked on each trigger, never handed to a model or harness process, and never a publication grant), S2's
`sync` half (a dead or never-registered worker ends its custodian), S3 (the worker is never the Lead's), T3 (it never
races the Lead's publish), and §10's stage/primitive equivalence and SAE-07 per primitive E6a stages first.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import (
    SUBTRACT_PATCH,
    assign,
    create_planned_ticket,
    implement,
    review,
    sample_project,
    to_commit_ready,
    verify,
)
from conftest import Project, git, run_aew
from invariants import assert_control_invariants, load_control
from stage_equivalence import differences, end_state, recorded_decisions
from test_stage_runner import call, intent, launching
from test_stages_ticket import _declared, _effects, _observe, _twins
from test_validation_checks import CONTAINED, SMOKE, policy

import aew.operator
from aew.engine import api as engine_api
from aew.engine import authority as A
from aew.engine import custody_ops as CO
from aew.engine import stage_intents as SI
from aew.engine import validation_ops as VO
from aew.engine.api import Engine
from aew.errors import AEWError, IllegalTransition, PermissionDenied, StaleAuthority
from aew.harness import procs

CRED = A.TOKEN_RE


def synthetic(fill: str) -> str:
    """A credential-shaped string that is no credential (built here, so no such literal sits in the file)."""
    return "aew1." + "tk_" + "0" * 16 + "." + fill * 43


@pytest.fixture
def custody(monkeypatch):
    """Each grant's custody credential, by custodian, where the engine hands it to the worker it starts: the test
    drives that worker in process instead."""
    held: dict[str, str] = {}
    monkeypatch.setattr(engine_api, "spawn_worker",
                        lambda repo, aew_root, custodian, credential: held.__setitem__(custodian, credential))
    return held


@pytest.fixture
def contained(monkeypatch):
    """The containment stand-in of `test_validation_checks`: the engine believes the candidate is immutable."""
    monkeypatch.setattr(VO.Validation, "containment_available", lambda self: True)
    monkeypatch.setattr(VO.Validation, "establish", lambda self, *, workspace, run_dir: (None, dict(CONTAINED)))


def control(p: Project) -> dict[str, Any]:
    return load_control(p.root)


def engine(p: Project) -> Engine:
    e = Engine.discover(p.root)
    e._validation.backoff_s = 0.0
    return e


def done(p: Project, wid: str) -> bool:
    """The Ticket is DONE (hot, or archived with the DONE commit)."""
    return Engine.discover(p.root).status(wid)["work_unit"]["state"] == "DONE"


def entry(p: Project, wid: str) -> dict[str, Any]:
    return next(e for e in control(p)["queue"]["entries"].values() if e["work"] == wid)


def lease(p: Project) -> dict[str, Any] | None:
    return control(p)["queue"]["lease"]


def checks_mode(p: Project) -> None:
    policy(p, checks=SMOKE, post=["smoke", "guardrails"])


def verifying(p: Project, tmp_path: Path) -> tuple[str, str]:
    """A VERIFY_PENDING Ticket and its Ticket-scope verification report, not accepted yet."""
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    return wid, verify(p, wid)


def prepared(p: Project, tmp_path: Path) -> tuple[str, str, dict[str, Any]]:
    """`ticket_prepare` run: the Ticket, its custodian and the stage's result."""
    wid, report = verifying(p, tmp_path)
    out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report)
    assert out["ok"], out["stopped"]
    held = lease(p)
    assert held is not None
    return wid, held["custodian"], out


def validated(p: Project, tmp_path: Path, held: dict[str, str]) -> tuple[str, str]:
    """Checks mode: prepared by the stage, then validated by its custodian, which releases the lease to VALIDATED."""
    wid, custodian, _out = prepared(p, tmp_path)
    found, result = engine(p).custody_step(custodian, held[custodian])
    assert found == CO.ACTED and result is not None and result["result"] == "pass", result
    return wid, custodian


def outside_commit(p: Project, name: str = "NOTES.md") -> str:
    """A commit on the authoritative branch that AEW did not make: the head moves."""
    (p.root / name).write_text("an unrelated commit\n", encoding="utf-8", newline="\n")
    git("add", name, cwd=p.root)
    git("commit", "-q", "-m", f"outside: {name}", cwd=p.root)
    return git("rev-parse", "HEAD", cwd=p.root)


def take_over(e: Engine) -> None:
    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        e.lead_takeover(expect_rev=int(e.store.read()["revision"]), reason="the Lead's session was lost",
                        session_label="operator")
    finally:
        aew.operator.authorize = original


# The integration verifier's script (verifier mode): one check, then its report, then it waits for the test.
def verifier_script(sync: Path, result: str = "pass") -> list[dict[str, Any]]:
    return [{"do": "check", "id": "unit"},
            {"do": "dump_env", "path": str(sync / "verifier-env.json")},
            {"do": "submit", "kind": "verification", "meta": {
                "claim": "the integrated candidate works", "verification": {"scope": "integration", "claims": [
                    {"type": "goal_backwards", "claim": "subtract works on the candidate", "result": result,
                     "checks": ["{evidence:check-unit}"]}]}}},
            {"do": "wait_file", "path": str(sync / "release"), "ready": str(sync / "ready")}]


# ---------------------------------------------------------------------------------------------- N2 and VALIDATE_ONLY


def test_custodian_runs_checks_validation_after_prepare(tmp_path, contained, custody):
    """Checks mode: `ticket_prepare` accepts the verification, moves the Ticket to COMMIT_READY and prepares under a
    lease; it never validates. The lease's custodian does, under its own credential, and in its commit releases the
    lease to VALIDATED with the candidate kept. Every commit is attributed to the custodian and the stage that
    requested it. The Lead publishes later through `integration_publish`, under a fresh lease."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, out = prepared(p, tmp_path)
    si = intent(p, out)
    assert [s["primitive"] for s in si["steps"]] == ["verify.ingest", "work.transition", "integrate.prepare"]
    assert si["status"] == SI.COMPLETED and si["judgment_inputs"] == ["accept_verification"]
    state = control(p)
    held = state["queue"]["lease"]
    assert held["custody"]["requested_by"] == si["id"] and custodian in custody
    assert state["tokens"][held["custody"]["token_id"]]["kind"] == "custody"
    assert state["work"][wid]["integration"]["status"] == "prepared"  # the stage validates nothing (§2.3)
    assert CRED.match(custody[custodian]) and custody[custodian] not in json.dumps(state)  # only its hash is kept
    assert_control_invariants(p)

    found, result = engine(p).custody_step(custodian, custody[custodian])
    assert found == CO.ACTED and result["result"] == "pass", result
    state = control(p)
    e = entry(p, wid)
    integ = state["work"][wid]["integration"]
    assert e["state"] == "VALIDATED" and state["queue"]["lease"] is None
    assert e["validated"]["mode"] == "checks" and e["validated"]["run"] == result["run"]
    assert e["validated"]["candidate"] == integ["candidate"] and e["validated"]["base"] == integ["base"]
    assert integ["status"] == "validated" and Path(integ["workspace"]).is_dir()  # the candidate is kept
    assert state["invocations"][custodian]["status"] == "completed"
    assert state["tokens"][held["custody"]["token_id"]]["revoked_at"] is not None  # its own lease ended
    actor = state["last_transition"]["actor"]
    assert actor["kind"] == "custodian" and actor["invocation"] == custodian and actor["requested_by"] == si["id"]
    assert "token_id" in actor and actor["token_id"] != state["lead"]["token_id"]
    assert_control_invariants(p)

    published = call(p, "integration_publish", work_id=wid, prepared_candidate=integ["candidate"])
    assert published["ok"], published["stopped"]
    assert [s["primitive"] for s in published["completed_steps"]] == ["integrate.publish"]
    state = control(p)
    assert done(p, wid) and state["queue"]["lease"] is None  # the second custodian's lease ended with DONE
    assert git("rev-parse", "main", cwd=p.root) == integ["candidate"]
    assert_control_invariants(p)


def test_validate_only_releases_and_revalidates(tmp_path, contained, custody):
    """VALIDATE_ONLY (plan v3 §2.3): with no publication requested, a clean validation releases the lease and keeps
    the candidate (another entry could take the lease meanwhile). When the head has moved by the time the Lead
    publishes, `integration_publish` gets a fresh lease and commits the one rebuild under it, never publishing the
    candidate the Lead saw validated: the stage stops there (its `rebuilt` boundary; ADR-0004 amendment 2026-10-10),
    and its result says nothing was published. The new custodian revalidates the rebuilt candidate and the entry
    returns to VALIDATED. Only then does a publish of the rebuilt candidate complete."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, _first = validated(p, tmp_path, custody)
    old = entry(p, wid)["validated"]
    assert lease(p) is None
    head = outside_commit(p)

    refused = call(p, "integration_publish", work_id=wid, prepared_candidate="0" * 40)
    assert not refused["ok"] and refused["stopped"]["error"]["details"]["reason"] == "candidate_mismatch"
    out = call(p, "integration_publish", work_id=wid, prepared_candidate=old["candidate"])
    assert not out["ok"] and out["stopped"]["at"] == "integrate.publish"
    assert out["stopped"]["error"]["code"] == "STALE_CANDIDATE"
    assert out["stopped"]["error"]["details"]["reason"] == "rebuilt"
    assert out["stopped"]["error"]["details"]["published"] is False
    assert [s["primitive"] for s in out["completed_steps"]] == ["integrate.publish"]
    si = intent(p, out)
    assert si["status"] == SI.STOPPED and si["stopped"]["boundary"] == "rebuilt"
    assert si["steps"][0]["disposition"] == "integrate.rebuild"
    state = control(p)
    integ = state["work"][wid]["integration"]
    held = state["queue"]["lease"]
    assert state["work"][wid]["state"] == "COMMIT_READY" and integ["status"] == "prepared"
    assert integ["base"] == head and integ["candidate"] != old["candidate"]
    assert entry(p, wid)["state"] == "LEASED" and entry(p, wid)["attempts"][-1]["from_validated"]["candidate"] == \
        old["candidate"]
    assert_control_invariants(p)

    found, result = engine(p).custody_step(held["custodian"], custody[held["custodian"]])
    assert found == CO.ACTED and result["result"] == "pass"
    again = entry(p, wid)
    assert again["state"] == "VALIDATED" and again["validated"]["candidate"] == integ["candidate"]
    assert again["validated"]["base"] == head and lease(p) is None
    out = call(p, "integration_publish", work_id=wid, prepared_candidate=integ["candidate"])
    assert out["ok"], out["stopped"]
    assert done(p, wid)
    assert git("rev-parse", "main", cwd=p.root) == integ["candidate"]
    assert_control_invariants(p)


@pytest.mark.parametrize("result", ["pass", "fail"])
def test_custodian_routes_but_never_accepts_verifier_reports(tmp_path, monkeypatch, custody, result):
    """Verifier mode: `ticket_prepare` launches the integration verifier as the custodian's child. The custodian waits
    for its run to end, then routes the report without accepting it: a clean one releases the lease to VALIDATED,
    anything else to AWAITING_DISPOSITION. Nothing is ingested, and the Ticket stays COMMIT_READY either way. The Lead
    accepts the clean report and publishes in one `integration_publish` call, under a fresh lease."""
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    sync = tmp_path / "sync"
    try:
        wid, report = verifying(p, tmp_path)
        lab.script("default", verifier_script(sync, result))
        out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report)
        assert out["ok"], out["stopped"]
        si = intent(p, out)
        assert [s["primitive"] for s in si["steps"]] == ["verify.ingest", "work.transition", "integrate.prepare",
                                                         "invoke.create.mutating", "dispatch.launch"]
        [verifier] = si["steps"][3]["outputs"]["invocations"]
        [run] = si["steps"][4]["outputs"]["runs"]
        custodian = lease(p)["custodian"]
        assert control(p)["invocations"][verifier]["custodian"] == custodian
        e = engine(p)
        lab.until(lambda: (sync / "ready").exists(), what="the verifier to report")
        assert e.custody_step(custodian, custody[custodian]) == (CO.WAITING, None)  # its run is live
        (sync / "release").touch()
        lab.wait(run)
        found, routed = e.custody_step(custodian, custody[custodian])
        assert found == CO.ACTED, routed
        state = control(p)
        integ = state["work"][wid]["integration"]
        assert state["work"][wid]["state"] == "COMMIT_READY" and integ["status"] == "prepared"
        assert "post_integration_evidence" not in integ  # routed, never accepted
        assert state["queue"]["lease"] is None and state["invocations"][verifier]["status"] != "active"
        assert state["last_transition"]["actor"]["kind"] == "custodian"
        if result == "fail":
            assert routed["routed"]["to"] == "AWAITING_DISPOSITION"
            assert entry(p, wid)["disposition"]["reason"] == "verification_not_clean"
            assert_control_invariants(p)
            return
        evidence = routed["routed"]["report"]
        assert routed["routed"]["to"] == "VALIDATED" and entry(p, wid)["validated"]["report"] == evidence
        assert evidence not in json.dumps(state["work"][wid].get("evidence") or [])  # not ingested
        assert_control_invariants(p)
        out = call(p, "integration_publish", work_id=wid, prepared_candidate=integ["candidate"],
                   verification_evidence=evidence)
        assert out["ok"], out["stopped"]
        si = intent(p, out)
        assert [s["primitive"] for s in si["steps"]] == ["verify.ingest.integration", "integrate.publish"]
        assert si["judgment_inputs"] == ["publish_candidate", "accept_verification"]
        assert done(p, wid)
        assert_control_invariants(p)
    finally:
        lab.cleanup()


@pytest.mark.parametrize("ending", ["takeover", "defer"])
def test_custody_worker_commits_nothing_after_its_custodian_ends(tmp_path, contained, custody, ending):
    """It adds no authority: once its custodian has ended (a takeover makes its generation stale; a deferral ends its
    lease), the worker's pass ends and its credential commits nothing, not even a registration."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    e = engine(p)
    if ending == "takeover":
        take_over(e)
    else:
        e.integrate_defer(token=p.token, expect_rev=p.rev(), work_id=wid, reason="set aside")
    rev = p.rev()
    assert e.custody_step(custodian, custody[custodian]) == (CO.ENDED, None)
    with pytest.raises(StaleAuthority):
        e.custody_register(custody[custodian])
    with pytest.raises(AEWError):  # refused before anything is pinned: no lease of its own to validate under
        e._validation.custody_validate(credential=custody[custodian], work_id=wid)
    assert e.custody_run(custodian, custody[custodian], timeout_s=1)["ended"] == "refused"
    assert p.rev() == rev
    assert_control_invariants(p)


def test_custody_worker_holds_no_lead_credential(tmp_path, monkeypatch):
    """T1: the worker's environment is an allow-list (no `AEW_*` variable, so nothing of a Lead session), its
    credential is never in its argv or environment, only on its stdin pipe, and the Lead's credential admits no
    custody commit."""
    base = {"PATH": "/bin", "AEW_LEAD_TOKEN": synthetic("x"), "AEW_LEAD_BROKER": "127.0.0.1:9",
            "AEW_LEAD_BROKER_KEY": "00", "AEW_INVOCATION_TOKEN": "t", "OPENAI_API_KEY": "secret", "HOME": "/home/x"}
    env = CO.worker_env(base)
    assert not [k for k in env if k.upper().startswith("AEW_")] and "OPENAI_API_KEY" not in env
    assert not CRED.search(json.dumps(env))
    seen: dict[str, Any] = {}

    class Pipe(io.BytesIO):
        def close(self) -> None:
            seen["stdin"] = self.getvalue()

    class Proc:
        pid = 4242
        stdin = Pipe()

    def spawn(argv: list[str], **kw: Any) -> Proc:
        seen.update(argv=argv, env=kw["env"])
        return Proc()

    p = sample_project(tmp_path / "project")
    monkeypatch.delenv(CO.WORKER_SWITCH)
    monkeypatch.setattr(procs, "spawn_detached", spawn)
    credential = synthetic("c")
    for k, v in base.items():
        if k.startswith("AEW_") or k == "OPENAI_API_KEY":  # what a Lead's process could hold
            monkeypatch.setenv(k, v)
    assert CO.spawn_worker(tmp_path, tmp_path / ".aew", "IA-0001", credential) == 4242
    assert credential not in json.dumps(seen["argv"]) and credential not in json.dumps(seen["env"])
    assert not [k for k in seen["env"] if k.upper().startswith("AEW_")]
    assert json.loads(seen["stdin"]) == {"credential": credential}
    e = Engine.discover(p.root)
    with pytest.raises(PermissionDenied):
        with e._k.custody_txn(p.token, "custody.register"):
            pass


# ---------------------------------------------------------------------------------------------- the credential (S1)


def test_custody_credential_bindings_checked_every_commit(tmp_path, contained, custody, monkeypatch):
    """Every custody commit verifies every binding on its own transaction's state: changing any one of the custodian,
    the lease, its entry, its grant, its attempt, the generation or the credential's own record refuses it."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    credential = custody[custodian]
    state = control(p)
    A.require_custodian(state, credential, "custody.register")  # as it stands, admitted

    def mutated(change) -> dict[str, Any]:
        s = json.loads(json.dumps(state))
        change(s)
        return s

    token_id = state["queue"]["lease"]["custody"]["token_id"]
    for change in (
            lambda s: s["invocations"][custodian].update(status="completed"),
            lambda s: s["lead"].update(generation=s["lead"]["generation"] + 1),
            lambda s: s["queue"]["lease"].update(custodian="IA-9999"),
            lambda s: s["queue"]["lease"].update(entry="Q-9999"),
            lambda s: s["queue"]["lease"].update(granted_at="2000-01-01T00:00:00Z"),
            lambda s: s["queue"]["lease"]["custody"].update(token_id="tk_0000000000000000"),
            lambda s: s["queue"]["lease"].update(reconcile={"reason": "test", "at": "2000-01-01T00:00:00Z"}),
            lambda s: next(e for e in s["queue"]["entries"].values() if e["work"] == wid)["attempts"].append(
                {"custodian": custodian}),
            lambda s: s["tokens"][token_id].update(revoked_at="2000-01-01T00:00:00Z"),
            lambda s: s["queue"].update(lease=None)):
        with pytest.raises((StaleAuthority, PermissionDenied)):
            A.require_custodian(mutated(change), credential, "custody.register")
    checked: list[str] = []
    real = A.require_custodian

    def spy(state: dict[str, Any], credential: str, op: str) -> dict[str, Any]:
        checked.append(op)
        return real(state, credential, op)

    monkeypatch.setattr("aew.engine.base.require_custodian", spy)
    found, _ = engine(p).custody_step(custodian, credential)
    assert found == CO.ACTED
    assert checked == ["integrate.validate", "integrate.validated"]  # one check per commit, the pin and the commit


def test_custody_credential_refused_outside_the_closed_family(tmp_path, contained, custody):
    """The credential admits only integration-custody operations, through `custody_txn` alone: no Lead transaction, no
    invocation's operation, no other op."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    credential = custody[custodian]
    e = engine(p)
    rev = p.rev()
    for op in ("work.transition", "integrate.prepare", "invoke.create", "stage.open", "lead.release"):
        with pytest.raises(PermissionDenied):
            with e._k.custody_txn(credential, op):
                pass
    with pytest.raises(PermissionDenied):
        e.work_transition(token=credential, expect_rev=rev, work_id=wid, to="RUNNING")
    with pytest.raises(PermissionDenied):
        e.integrate_publish(token=credential, expect_rev=rev, work_id=wid)
    with pytest.raises(PermissionDenied):
        A.require_invocation(control(p), credential, None)
    assert p.rev() == rev


@pytest.mark.parametrize("trigger", ["custodian_death", "generation", "cancel", "reconcile", "lease_end"])
def test_custody_credential_revoked_on_each_trigger(tmp_path, contained, custody, monkeypatch, trigger):
    """Revoked in the very transaction that ends the custody: the custodian's death (its worker gone, S2), a new Lead
    generation, a cancel, a reconcile, and the lease's own end."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    credential = custody[custodian]
    token_id = lease(p)["custody"]["token_id"]
    e = engine(p)
    if trigger == "custodian_death":
        e.custody_register(credential)
        monkeypatch.setattr(procs, "same_process", lambda pid, started: False)
        e.checkpoint(token=p.token, expect_rev=p.rev(), note="any Lead commit runs sync")
    elif trigger == "generation":
        take_over(e)
    elif trigger in ("cancel", "reconcile"):
        e.invoke_cancel(token=p.token, expect_rev=p.rev(), invocation=custodian, reason="stop it")
        if trigger == "reconcile":
            e.integrate_reconcile(token=p.token, expect_rev=p.rev(), work_id=wid)
            assert lease(p) is None
    else:
        e.custody_step(custodian, credential)  # validates: its lease ends, VALIDATED
        assert lease(p) is None
    assert control(p)["tokens"][token_id]["revoked_at"] is not None
    with pytest.raises((StaleAuthority, PermissionDenied)):
        e.custody_register(credential)
    assert_control_invariants(p)


def test_custody_credential_never_reaches_a_model_or_harness_process(tmp_path, monkeypatch, custody):
    """V2, W1: the integration verifier (launched by the Lead's stage, never by the worker), its environment, its run
    record and logs, and control state never carry the custody credential; nor do the checks the worker runs, whose
    environment is an allow-list."""
    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    sync = tmp_path / "sync"
    try:
        wid, report = verifying(p, tmp_path)
        lab.script("default", verifier_script(sync))
        out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report)
        assert out["ok"], out["stopped"]
        [run] = intent(p, out)["steps"][4]["outputs"]["runs"]
        credential = custody[lease(p)["custodian"]]
        lab.until(lambda: (sync / "ready").exists(), what="the verifier to report")
        (sync / "release").touch()
        lab.wait(run)
        assert credential not in (sync / "verifier-env.json").read_text(encoding="utf-8")
        for path in (p.root / ".aew").rglob("*"):
            if path.is_file():
                assert credential.encode() not in path.read_bytes(), path
        assert credential not in json.dumps(out)
    finally:
        lab.cleanup()
    for name in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN"):
        monkeypatch.setenv(name, synthetic("y"))
    env = VO.Validation._check_env(None)  # the worker's checks: an allow-list, whatever it inherited
    assert not [k for k in env if k.upper().startswith("AEW_")] and not CRED.search(json.dumps(env))


def test_custody_credential_grants_no_publication_without_the_envelope_and_predicate(tmp_path, contained, custody):
    """The credential never authorizes a publication by itself: a custody publish needs the operator's envelope and the
    §17 predicate (E6b), so it is refused; and a candidate the custodian validated is published only by the Lead."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    credential = custody[custodian]
    with pytest.raises(IllegalTransition) as refused:
        with engine(p)._k.custody_txn(credential, A.CUSTODY_PUBLISH):
            pass
    assert refused.value.details["reason"] == "no_publication_envelope"
    engine(p).custody_step(custodian, credential)
    assert entry(p, wid)["state"] == "VALIDATED" and control(p)["work"][wid]["state"] == "COMMIT_READY"
    assert git("rev-parse", "main", cwd=p.root) == entry(p, wid)["validated"]["base"]  # nothing published


# ---------------------------------------------------------------------------------------------- S2, `sync`'s half


def test_dead_custody_worker_marks_reconcile(tmp_path, contained, custody, monkeypatch):
    """A registered worker that is gone ends its custodian at the next commit's `sync`: the lease is marked for
    reconciliation (never released) and the credential revoked; `integrate reconcile` then settles it."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    e = engine(p)
    e.custody_register(custody[custodian])
    worker = control(p)["invocations"][custodian]["worker"]
    assert worker["host_pid"] and worker["started_at"]
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="a live worker is never ended")
    assert lease(p)["reconcile"] is None
    monkeypatch.setattr(procs, "same_process", lambda pid, started: False)
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="any Lead commit runs sync")
    held = lease(p)
    assert held["reconcile"] is not None and "custody worker" in held["reconcile"]["reason"]
    assert control(p)["invocations"][custodian]["status"] == "interrupted"
    assert entry(p, wid)["state"] == "LEASED"  # nothing released by it
    assert_control_invariants(p)
    e.integrate_reconcile(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert lease(p) is None and entry(p, wid)["state"] == "QUEUED"


def test_unregistered_custodian_marks_reconcile(tmp_path, contained, custody):
    """No worker registered within `custody_register_s` of the grant (a spawn that failed, or never happened): the next
    commit's `sync` ends the custodian, which marks the lease for reconciliation."""
    p = sample_project(tmp_path)
    checks_mode(p)
    from aew.util import dump_yaml, load_yaml

    gates = p.root / ".aew/policy/gates.yaml"
    data = load_yaml(gates.read_text(encoding="utf-8"))
    data["post_integration"]["custody_register_s"] = 1
    gates.write_text(dump_yaml(data), encoding="utf-8", newline="\n")
    p.pin_policy()
    wid, custodian, _out = prepared(p, tmp_path)
    e = engine(p)
    time.sleep(2.5)
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="past the bound")
    held = lease(p)
    assert held["reconcile"] is not None and "no custody worker registered" in held["reconcile"]["reason"]
    assert control(p)["invocations"][custodian]["status"] == "interrupted" and entry(p, wid)["state"] == "LEASED"
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- S3 and T3


def _wait_for(predicate, what: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, f"timed out waiting for {what}"
        time.sleep(0.2)


def test_broker_spawned_custody_worker_registers(tmp_path, monkeypatch):
    """A grant made in a Lead broker's process (its environment holds the Lead session's variables) starts the worker
    with that environment stripped: it registers, waits (verifier mode, no verifier yet), and exits once its
    custodian's lease ends."""
    p = sample_project(tmp_path)
    wid, _impl = to_commit_ready(p, tmp_path)
    monkeypatch.delenv(CO.WORKER_SWITCH)
    monkeypatch.setenv("AEW_LEAD_BROKER", "127.0.0.1:1")
    monkeypatch.setenv("AEW_LEAD_BROKER_KEY", "00" * 16)
    monkeypatch.setenv("AEW_LEAD_TOKEN", p.token)
    e = Engine.discover(p.root)
    e.integrate_prepare(token=p.token, expect_rev=int(e.store.read()["revision"]), work_id=wid)
    custodian = lease(p)["custodian"]
    _wait_for(lambda: "worker" in control(p)["invocations"][custodian], "the custody worker to register")
    worker = control(p)["invocations"][custodian]["worker"]
    assert procs.pid_alive(worker["host_pid"])
    assert control(p)["last_transition"]["actor"]["kind"] == "custodian"
    e.integrate_defer(token=p.token, expect_rev=int(e.store.read()["revision"]), work_id=wid,
                      reason="end the custody")
    _wait_for(lambda: not procs.pid_alive(worker["host_pid"]), "the custody worker to exit")
    assert_control_invariants(p)


def test_lead_shell_custody_run_commits_nothing(tmp_path, custody):
    """S3/T1: `aew integrate custody` refuses to run in a Lead session's environment, and outside one a Lead's shell
    cannot present the custody credential: with the Lead's credential, or none, it commits nothing."""
    p = sample_project(tmp_path)
    wid, _impl = to_commit_ready(p, tmp_path)
    e = Engine.discover(p.root)
    e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid)
    custodian = lease(p)["custodian"]
    rev = p.rev()
    refused = run_aew("-C", str(p.root), "integrate", "custody", custodian,
                      env={"AEW_LEAD_BROKER": "127.0.0.1:1"}, input=json.dumps({"credential": p.token}))
    assert refused.returncode != 0 and "never runs in a Lead session" in refused.stderr
    lead = run_aew("-C", str(p.root), "integrate", "custody", custodian, input=json.dumps({"credential": p.token}))
    assert lead.json["ok"] is False and lead.json["ended"] == "refused"
    nothing = run_aew("-C", str(p.root), "integrate", "custody", custodian, input="")
    assert nothing.returncode != 0
    assert p.rev() == rev and "worker" not in control(p)["invocations"][custodian]


def test_custody_worker_never_races_the_leads_publish(tmp_path, contained, custody, monkeypatch):
    """T3: on a lease granted to publish a VALIDATED candidate, the worker registers and waits: between the publish's
    intent commit and its finish it commits nothing, and after DONE its custody has ended."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, _first = validated(p, tmp_path, custody)
    candidate = entry(p, wid)["validated"]["candidate"]
    e = engine(p)
    seen: dict[str, Any] = {}
    real = e._integration._finish_publish

    def finish(token: str, expect_rev: int, work_id: str, **kw: Any) -> dict[str, Any]:
        held = lease(p)
        seen["custodian"] = custodian = held["custodian"]
        e.custody_register(custody[custodian])
        rev = p.rev()
        seen["between"] = e.custody_step(custodian, custody[custodian])
        seen["committed"] = p.rev() != rev
        return real(token, p.rev(), work_id, **kw)

    monkeypatch.setattr(e._integration, "_finish_publish", finish)
    out = e.integrate_publish(token=p.token, expect_rev=p.rev(), work_id=wid, candidate=candidate)
    assert out["state"] == "DONE"
    assert seen["between"] == (CO.WAITING, None) and not seen["committed"]
    assert e.custody_step(seen["custodian"], custody[seen["custodian"]]) == (CO.ENDED, None)
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- §10 and SAE-07


def _verified(p: Project, held: dict[str, str], *, validate: bool, mode: str) -> dict[str, str]:
    """In one copy: the Ticket to VERIFY_PENDING with its report; with ``validate``, accepted, COMMIT_READY, prepared,
    and validated by its custodian (checks mode), or its integration verifier run and its report routed (verifier
    mode), so the entry is VALIDATED."""
    implement(assign(p, "T-0001"), SUBTRACT_PATCH)
    p.lead("work", "transition", "T-0001", "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", "T-0001", "--evidence", review(p, "T-0001"))
    p.lead("work", "transition", "T-0001", "--to", "VERIFY_PENDING")
    found = {"report": verify(p, "T-0001")}
    if not validate:
        return found
    e = engine(p)
    e.verify_ingest(token=p.token, expect_rev=p.rev(), work_id="T-0001", evidence_id=found["report"])
    e.work_transition(token=p.token, expect_rev=p.rev(), work_id="T-0001", to="COMMIT_READY")
    e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id="T-0001")
    custodian = lease(p)["custodian"]
    if mode == "verifier":
        out = e.launch_dispatched(e.invoke_create(token=p.token, expect_rev=p.rev(), work_id="T-0001",
                                                  role="verifier", scope="integration", launch=True))
        assert not e.harness_wait(out["launch"]["run"], timeout=300)["timed_out"]
    found_step, routed = e.custody_step(custodian, held[f"{p.root / '.aew'}|{custodian}"])
    assert found_step == CO.ACTED, routed
    validated = entry(p, "T-0001")["validated"]
    found["candidate"] = validated["candidate"]
    found["integration_report"] = validated.get("report", "")
    return found


# Every terminal shape of the two integration stages (plan v3 §6, §10; PR #200 review): the steps a stage plans for the
# state it is called in, each compared with its primitives run directly.
EQUIVALENCE_CASES = [("ticket_prepare", "checks"), ("ticket_prepare", "verifier"),
                     ("integration_publish", "done"), ("integration_publish", "rebuild"),
                     ("integration_publish", "verifier"), ("integration_publish", "rebuild_verifier")]
PLANNED = {
    ("ticket_prepare", "checks"): ["verify.ingest", "work.transition", "integrate.prepare"],
    ("ticket_prepare", "verifier"): ["verify.ingest", "work.transition", "integrate.prepare", "invoke.create.mutating",
                                     "dispatch.launch"],
    ("integration_publish", "done"): ["integrate.publish"],
    ("integration_publish", "rebuild"): ["integrate.publish"],
    ("integration_publish", "verifier"): ["verify.ingest.integration", "integrate.publish"],
    ("integration_publish", "rebuild_verifier"): ["integrate.publish", "invoke.create.mutating", "dispatch.launch"]}


@pytest.mark.parametrize(("name", "case"), EQUIVALENCE_CASES, ids=[f"{n}-{c}" for n, c in EQUIVALENCE_CASES])
def test_stage_matches_primitives(tmp_path, monkeypatch, name, case):
    """Plan v3 §10: the stage and its primitives run directly, with the same arguments, end in the same state,
    compared without the journal's own records (``stage_equivalence``), for each shape the stage plans:
    `ticket_prepare` in checks mode (three steps) and in verifier mode (the integration verifier launched);
    `integration_publish` on a VALIDATED entry publishing to DONE (the unit archived, its intent then annotating it),
    on a moved head (the fresh lease and the one rebuild), in verifier mode (the report accepted, then published to
    DONE), and on a moved head in verifier mode (the rebuild, then the rebuilt candidate's verifier). Commit times are
    fixed so the two copies' candidates are the same commits; a verifier's harness run is the fake harness's."""
    verifier = "verifier" in case
    monkeypatch.setenv("GIT_AUTHOR_DATE", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2026-01-01T00:00:00Z")
    monkeypatch.setattr(VO.Validation, "containment_available", lambda self: True)
    monkeypatch.setattr(VO.Validation, "establish", lambda self, *, workspace, run_dir: (None, dict(CONTAINED)))
    held: dict[str, str] = {}
    monkeypatch.setattr(engine_api, "spawn_worker",
                        lambda repo, aew_root, custodian, credential: held.__setitem__(f"{aew_root}|{custodian}",
                                                                                       credential))
    labs: list[Any] = []

    def prepare(p: Project) -> None:
        if verifier:
            labs.append(launching(p, tmp_path, monkeypatch))
            # The first verifier reports and ends; one the stage launches stays live in both copies.
            labs[0].script("default", [{"do": "hang"}] if name == "ticket_prepare"
                           else verifier_script(tmp_path / "sync")[:3])
        else:
            checks_mode(p)
        create_planned_ticket(p, tmp_path)

    staged, direct = _twins(tmp_path, prepare)
    try:
        found: dict[str, str] = {}
        for p in (staged, direct):  # the same work in each copy, after the copy: each has its own workspace
            found = _verified(p, held, validate=name == "integration_publish",
                              mode="verifier" if verifier else "checks")
            if "rebuild" in case:  # the same commit in each copy: the publish rebuilds under a fresh lease
                outside_commit(p)
        if labs:
            labs[0].script("default", [{"do": "hang"}])
        decisions = recorded_decisions()
        recorded = decisions.__enter__()
        try:
            e = engine(direct)
            before = differences(end_state(staged.root, recorded), end_state(direct.root, recorded))
            assert all(d.startswith("/files/evidence/") or "validation-runs" in d for d in before), before
            if name == "ticket_prepare":
                out = call(staged, name, work_id="T-0001", verification_evidence=found["report"])
                e.verify_ingest(token=direct.token, expect_rev=direct.rev(), work_id="T-0001",
                                evidence_id=found["report"], scope="ticket")
                e.work_transition(token=direct.token, expect_rev=direct.rev(), work_id="T-0001", to="COMMIT_READY")
                e.integrate_prepare(token=direct.token, expect_rev=direct.rev(), work_id="T-0001")
            else:
                accept = {"verification_evidence": found["integration_report"]} if case == "verifier" else {}
                out = call(staged, name, work_id="T-0001", prepared_candidate=found["candidate"], **accept)
                if accept:
                    e.verify_ingest(token=direct.token, expect_rev=direct.rev(), work_id="T-0001",
                                    evidence_id=found["integration_report"], scope="integration")
                e.integrate_publish(token=direct.token, expect_rev=direct.rev(), work_id="T-0001",
                                    candidate=found["candidate"])
            if (name, case) in (("ticket_prepare", "verifier"), ("integration_publish", "rebuild_verifier")):
                # the integration verifier the stage launches, launched directly
                e.launch_dispatched(e.invoke_create(token=direct.token, expect_rev=direct.rev(), work_id="T-0001",
                                                    role="verifier", scope="integration", launch=True))
            if (name, case) == ("integration_publish", "rebuild"):  # it stops at its `rebuilt` boundary
                assert out["stopped"]["error"]["details"]["reason"] == "rebuilt", out["stopped"]
            else:
                assert out["ok"], out["stopped"]
            assert [s["primitive"] for s in intent(staged, out)["steps"]] == PLANNED[(name, case)]
            assert done(staged, "T-0001") == (name == "integration_publish" and case in ("done", "verifier"))
            a, b = end_state(staged.root, recorded), end_state(direct.root, recorded)
            assert differences(a, b) == before, "\n".join(sorted(set(differences(a, b)) ^ set(before)))
        finally:
            decisions.__exit__(None, None, None)
    finally:
        for lab in labs:
            lab.cleanup()
            lab.project = direct  # the copy's runs are its own: end them the same way
            lab.cleanup()


@pytest.mark.parametrize("primitive", ["integrate.prepare", "verify.ingest.integration", "integrate.publish"])
def test_declared_effects_cover_observed_effects(tmp_path, contained, custody, primitive):
    """A1 §6 / SAE-07, per primitive E6a stages first: what running it is observed to change never exceeds what its
    PrimitiveSpec declares. The prepare mints its custodian's credential; the integration ingest, on a VALIDATED entry,
    is granted a fresh lease (another credential) and completes the verifier; the publish moves the authoritative ref
    and removes worktrees."""
    p = sample_project(tmp_path)
    if primitive != "verify.ingest.integration":
        checks_mode(p)
    wid, _impl = to_commit_ready(p, tmp_path)
    e = engine(p)
    if primitive == "integrate.prepare":
        before = _observe(p)
        e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid)
    elif primitive == "verify.ingest.integration":
        e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid)
        evidence = verify(p, wid, scope="integration")
        before = _observe(p)
        e.verify_ingest(token=p.token, expect_rev=p.rev(), work_id=wid, evidence_id=evidence, scope="integration")
    else:
        e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid)
        custodian = lease(p)["custodian"]
        e.custody_step(custodian, custody[custodian])
        before = _observe(p)
        e.integrate_publish(token=p.token, expect_rev=p.rev(), work_id=wid)
    seen = _effects(before, _observe(p))
    assert "control_state" in seen and seen <= _declared(primitive), seen
    assert "credential" in seen
    if primitive == "integrate.publish":
        assert {"authoritative_ref", "workspace"} <= seen


# ---------------------------------------------------------------------------------------------- PR #200 review


def test_resume_says_the_custodian_validates_a_prepared_checks_candidate(tmp_path, contained, custody):
    """Plan v3 §2.3: the lease's custodian validates; the Lead never does. `resume` tells the Lead so, and to publish
    the VALIDATED candidate with `integration_publish`; `aew integrate validate` is named only as recovery, while no
    custody worker has registered."""
    p = sample_project(tmp_path)
    checks_mode(p)
    wid, custodian, _out = prepared(p, tmp_path)
    e = engine(p)
    [unregistered] = [a for a in e._resume.next_actions(e.store.read()) if wid in a]
    assert "custodian" in unregistered and "integration_publish" in unregistered
    assert "recovery" in unregistered and "aew integrate validate" in unregistered
    e.custody_register(custody[custodian])
    [registered] = [a for a in e._resume.next_actions(e.store.read()) if wid in a]
    assert "custodian" in registered and "aew integrate validate" not in registered


@pytest.mark.parametrize("observed", ["lost", "unconfirmed_past_grace", "unconfirmed_within_grace"])
def test_a_lost_verifier_run_is_routed_never_waited_on(tmp_path, monkeypatch, custody, observed):
    """Plan v3 §2.3, verifier mode: a run no supervisor holds any more (its supervisor stopped reporting, or none ever
    took custody past the launch's grace) is routed to AWAITING_DISPOSITION as a lost run, like a failed one; the
    custodian never waits on it with the lease held. A run that may still be starting is waited on."""
    from aew.harness import contract as K
    from aew.harness import runlog

    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    try:
        wid, report = verifying(p, tmp_path)
        lab.script("default", [{"do": "hang"}])
        out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report)
        assert out["ok"], out["stopped"]
        custodian = lease(p)["custodian"]
        status = K.LOST if observed == "lost" else K.UNCONFIRMED
        monkeypatch.setattr(runlog, "observed_status", lambda directory: (status, None))
        if observed == "unconfirmed_past_grace":
            monkeypatch.setattr(runlog, "possibly_live", lambda status, launched_at, **kw: False)
        found, routed = engine(p).custody_step(custodian, custody[custodian])
        if observed == "unconfirmed_within_grace":
            assert (found, routed) == (CO.WAITING, None) and lease(p) is not None
            return
        assert found == CO.ACTED and routed["routed"]["to"] == "AWAITING_DISPOSITION"
        assert routed["routed"]["why"] == CO.RUN_LOST
        assert lease(p) is None and entry(p, wid)["state"] == "AWAITING_DISPOSITION"
        assert control(p)["work"][wid]["state"] == "COMMIT_READY"
        assert_control_invariants(p)
    finally:
        lab.cleanup()


def _capture_spawn(monkeypatch) -> dict[str, Any]:
    """The argv, cwd and environment the next detached spawn is given; it starts nothing."""
    seen: dict[str, Any] = {}

    class Proc:
        pid = 4242
        stdin = io.BytesIO()
        stdout = io.BytesIO()

        def kill(self) -> None:
            pass

    def spawn(argv: list[str], **kw: Any) -> Proc:
        seen.update(argv=list(argv), cwd=str(kw["cwd"]), env=dict(kw["env"]))
        return Proc()

    monkeypatch.setattr(procs, "spawn_detached", spawn)
    return seen


class _Stop(Exception):
    """Raised by a captured spawn: nothing is started."""


def _capture_popen(monkeypatch) -> dict[str, Any]:
    """The argv, cwd and environment of the next ``procs`` Popen (the session helper's); it starts nothing."""
    seen: dict[str, Any] = {}

    def popen(argv: list[str], **kw: Any) -> Any:
        seen.update(argv=list(argv), cwd=str(kw.get("cwd")), env=dict(kw.get("env") or {}))
        raise _Stop

    monkeypatch.setattr(procs.subprocess, "Popen", popen)
    return seen


WORKERS = ["custody_worker", "run_supervisor",
           pytest.param("session_reaper", marks=pytest.mark.skipif(not sys.platform.startswith("linux"),
                                                                   reason="the session helper is Linux's"))]


@pytest.mark.parametrize("launcher_path", ["none", "absolute", "relative"])
@pytest.mark.parametrize("worker", WORKERS)
def test_credential_holding_workers_never_import_from_the_project_tree(tmp_path, monkeypatch, worker, launcher_path):
    """The engine's Python processes that receive a credential (the custody worker, a run's supervisor) or a session's
    environment (the Lead session's helper) import only the engine's own paths and the standard library: never their
    working directory, the project's tree, a `PYTHONPATH` their launcher had (absolute, or relative to where they
    start) or a user site. The workers start in an engine-owned directory; a `json.py` planted anywhere they could
    look is never imported."""
    import os

    p = sample_project(tmp_path)
    e = Engine.discover(p.root)
    monkeypatch.delenv(CO.WORKER_SWITCH)
    if launcher_path != "none":  # a developer of a Python project often has its source on PYTHONPATH
        entry_ = str(p.root / "src") if launcher_path == "absolute" else "src"
        monkeypatch.setenv("PYTHONPATH", os.pathsep.join([entry_, os.environ.get("PYTHONPATH", "")]))
    if worker == "session_reaper":
        seen = _capture_popen(monkeypatch)
        with pytest.raises(_Stop):
            procs.run_session_tree([sys.executable, "-c", "pass"], env=dict(os.environ), cwd=str(p.root))
        monkeypatch.undo()  # Popen back, before this test starts anything itself
        cwd = Path(seen["cwd"]).resolve()  # the session's own project, by design
        interpreter = seen["argv"][:seen["argv"].index("-c")]
    else:
        seen = _capture_spawn(monkeypatch)
        if worker == "custody_worker":
            CO.spawn_worker(p.root, p.root / ".aew", "IA-0001", synthetic("c"))
        else:
            from aew.errors import HarnessLaunchFailed

            monkeypatch.setattr("aew.engine.harness_ops.ACK_WAIT_S", 0.1)
            with pytest.raises(HarnessLaunchFailed):
                e._harness._spawn_run("INV-0001", "R-INV-0001-1", synthetic("r"))
        cwd = Path(seen["cwd"]).resolve()
        assert cwd.is_relative_to((p.root / ".aew" / "local").resolve()), cwd  # the engine's own runtime directory
        interpreter = seen["argv"][:seen["argv"].index("-m")]
    shadow = "import sys\nprint('IMPORTED FROM THE PROJECT TREE')\nsys.exit(0)\n"
    for where in (p.root, p.root / "src", cwd, cwd / "src"):
        where.mkdir(parents=True, exist_ok=True)
        (where / "json.py").write_text(shadow, encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if worker != "session_reaper":  # the worker itself, as started, up to reading its pipe
        run = subprocess.run(seen["argv"], cwd=cwd, env=seen["env"], stdin=subprocess.DEVNULL, capture_output=True,
                             text=True, timeout=180, creationflags=flags)
        assert "IMPORTED FROM THE PROJECT TREE" not in run.stdout + run.stderr
    probe = ("import json, os, site, sys; print(json.dumps({'path': sys.path, 'user_site': site.ENABLE_USER_SITE, "
             "'user': site.getusersitepackages()}))")
    out = subprocess.run([*interpreter, "-c", probe], cwd=cwd, env=seen["env"], capture_output=True, text=True,
                         timeout=60, creationflags=flags, check=True).stdout
    assert "IMPORTED FROM THE PROJECT TREE" not in out
    found = json.loads(out)
    project = p.root.resolve()
    for entry_ in found["path"]:
        assert entry_ and not Path(entry_).resolve().is_relative_to(project), (entry_, found["path"])
    assert not found["user_site"] and found["user"] not in found["path"]


def test_a_spawned_custody_worker_validates_end_to_end(tmp_path):
    """The production path in its own process: a grant starts `aew integrate custody`, which reads its credential from
    its pipe, registers, runs checks-mode validation under its custody credential and routes the result. Where this
    host's containment keeps the candidate immutable the entry ends VALIDATED; elsewhere the worker parks it for the
    Lead (AWAITING_DISPOSITION, containment unavailable). Either way only the custodian committed, and its worker
    exits."""
    import os

    p = sample_project(tmp_path)
    checks_mode(p)
    wid, _impl = to_commit_ready(p, tmp_path)
    e = engine(p)
    contained_here = e._validation.containment_available()
    switch = os.environ.pop(CO.WORKER_SWITCH, None)
    try:
        e.integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid)
    finally:
        if switch is not None:
            os.environ[CO.WORKER_SWITCH] = switch
    custodian = control(p)["queue"]["lease"]["custodian"]
    _wait_for(lambda: entry(p, wid)["state"] in ("VALIDATED", "AWAITING_DISPOSITION"), "the custodian's routing",
              timeout=300)
    state = control(p)
    worker = state["invocations"][custodian]["worker"]
    assert state["last_transition"]["actor"]["kind"] == "custodian"
    if contained_here:
        assert entry(p, wid)["state"] == "VALIDATED" and entry(p, wid)["validated"]["mode"] == "checks"
    else:
        assert entry(p, wid)["state"] == "AWAITING_DISPOSITION"
        assert "VALIDATION_CONTAINMENT_UNAVAILABLE" in json.dumps(entry(p, wid)["disposition"])
    _wait_for(lambda: not procs.pid_alive(worker["host_pid"]), "the custody worker to exit", timeout=120)
    assert_control_invariants(p)
