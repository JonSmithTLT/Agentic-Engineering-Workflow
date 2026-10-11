"""PUBLISH_IF_CLEAN: the operator's envelope, the Lead's request and the custodian's exercise (M4-E E6b; plan v3 §2.2,
§2.3, §6; A1 §1, §5; the idea note's §17; HSD-22, HSD-23).

The envelope is granted the way the operator endpoint grants it (``Engine.publication_grant`` with an
``OperatorPrincipal``, which only the endpoint constructs in ``src``; a test builds one as the endpoint would), after
the sealed run manifest and the task file it names are checked. The Lead's request is `ticket_prepare(publish_if_clean:
true)`, run through ``run_tool``. The custodian's worker is driven in process with its custody credential
(``Engine.custody_step``), as in ``test_integration_stages``, under the containment stand-in.

Covered: the Lead requests and never grants (A1 §6); each §17 clause, whose failure is never exercised; each
condition that makes the envelope unusable (VALIDATE_ONLY follows); the one rebuild PIC survives; a held result never
publishes (HSD-22, HSD-23); the publication count across a crash between the CAS and the count (n4); and the PIC
record on publication."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aewflow import assign, create_planned_ticket, implement, review, sample_project, verify
from conftest import Project, git
from invariants import assert_control_invariants
from test_integration_stages import (
    checks_mode,
    contained,  # noqa: F401 (a fixture)
    control,
    custody,  # noqa: F401 (a fixture)
    done,
    engine,
    entry,
    lease,
    outside_commit,
    verifying,
)
from test_stage_runner import call

from aew import errors
from aew.cli.main import build_parser
from aew.engine import custody_ops as CO
from aew.engine import publication_ops as PO
from aew.engine import steering as S
from aew.engine.faults import InjectedFault
from aew.harness import lead_broker
from aew.surface import contract

TASK = b"Add subtract() to calc.core, with a test.\n"
EXTRA_PATCH = {"calc/extra.py": "def double(a):\n    return 2 * a\n",
               "tests/test_extra.py": ("from calc.extra import double\n\n\n"
                                       "def test_double():\n    assert double(2) == 4\n")}


def principal() -> S.OperatorPrincipal:
    """The principal the operator endpoint would construct after its peer check and challenge."""
    return S.OperatorPrincipal(uid=os.getuid() if hasattr(os, "getuid") else None, method="peer_credentials",
                               endpoint_pid=os.getpid(), endpoint_started_at="2026-10-11T00:00:00Z")


def sealed(tmp_path: Path, *, max_publications: int = 3, duration_s: int = 3600, task: bytes = TASK) -> dict[str, Path]:
    """A synthetic sealed run manifest (``aew/m4h-run-manifest/v1``) and the task file it names."""
    task_file = tmp_path / "task.md"
    task_file.write_bytes(task)
    manifest = {"schema": PO.MANIFEST_SCHEMA, "seal_sha256": "1" * 64, "run_id": "m4h-test/run-1", "cell": "c1",
                "task_input_sha256": hashlib.sha256(task).hexdigest(), "caps": {"usd": 1.0, "wall_s": 3600},
                "treatment_sha256": "2" * 64, "max_publications": max_publications,
                "envelope_duration_s": duration_s}
    path = tmp_path / "run-manifest.json"
    path.write_bytes(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {"manifest": path, "task": task_file}


def grant(p: Project, tmp_path: Path, **kw: Any) -> dict[str, Any]:
    files = sealed(tmp_path, **kw)
    e = engine(p)
    bound = e.publication_grant_preview(manifest=str(files["manifest"]), task=str(files["task"]))
    out = e.publication_grant(principal(), bound=bound)
    assert out["ok"] and out["guarantee"] == "dev", out
    return {**out, **files}


def pic_prepared(p: Project, tmp_path: Path) -> tuple[str, str, dict[str, Any]]:
    """`ticket_prepare(publish_if_clean: true)` on a fresh Ticket: the Ticket, its custodian and the stage's result."""
    wid, report = verifying(p, tmp_path)
    out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report, publish_if_clean=True)
    assert out["ok"], out["stopped"]
    held = lease(p)
    assert held is not None
    return wid, held["custodian"], out


def step(p: Project, custodian: str, held: dict[str, str]) -> tuple[str, dict[str, Any] | None]:
    return engine(p).custody_step(custodian, held[custodian])


def new_generation(p: Project) -> None:
    """An operator-authorized takeover (as `test_integration_stages.take_over`), keeping the new Lead's credential."""
    import aew.operator

    original = aew.operator.authorize
    aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (test substitute)"}
    try:
        p.token = engine(p).lead_takeover(expect_rev=p.rev(), reason="the Lead's session was lost",
                                          session_label="operator")["token"]
    finally:
        aew.operator.authorize = original


def envelope(p: Project) -> dict[str, Any]:
    return control(p)["authorization"]


def main_head(p: Project) -> str:
    return git("rev-parse", "main", cwd=p.root)


def second_ticket(p: Project, tmp_path: Path) -> tuple[str, str]:
    """Another VERIFY_PENDING Ticket, with its own change, and its verification report."""
    wid = create_planned_ticket(p, tmp_path, title="Add double()")
    implement(assign(p, wid), EXTRA_PATCH)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    return wid, verify(p, wid)


# ---------------------------------------------------------------------------------------------- the publish


def test_a_clean_validation_publishes_under_the_envelope(tmp_path, contained, custody):  # noqa: F811
    """Plan v3 §2.3, row 1: with the Lead's request and a usable envelope, the custodian's clean validation commit
    begins the publish under the same lease, with no Lead turn between, and its finish publishes to DONE. The Ticket
    carries the envelope's stamp from `work.create`; the PIC record names the envelope, the request, each clause's
    result, H, M and the task hash; the count is published, never left reserved."""
    p = sample_project(tmp_path)
    checks_mode(p)
    granted = grant(p, tmp_path)
    wid, custodian, out = pic_prepared(p, tmp_path)
    state = control(p)
    assert state["work"][wid]["authorization_envelope"] == granted["envelope"]
    request = entry(p, wid)["attempts"][-1]["pic_request"]
    assert request["conditions"] == "pic/v1" and request["generation"] == 1 and request["mode"] == "checks"
    assert request["requested_by"] == out["stage_intent_id"] and not request["execution_override"]
    assert out["result"]["steps"][-1]["publish_if_clean"]["envelope"] == granted["envelope"]
    assert "publish_if_clean" in engine(p).stage_intent(out["stage_intent_id"])["judgment_inputs"]
    head = main_head(p)

    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None and result["integration"] == "publishing", result
    assert result["publish"]["ok"] and result["publish"]["published_under"] == "PUBLISH_IF_CLEAN", result
    assert done(p, wid)
    integ = engine(p).status(wid)["work_unit"]["integration"]
    pic = integ["pic"]
    assert pic["exercised"] and pic["envelope"] == granted["envelope"] and pic["reservation"] == PO.PUBLISHED
    assert [c["clause"] for c in pic["clauses"]] == list(range(1, 9)) and all(c["ok"] for c in pic["clauses"])
    assert pic["h"] == head and pic["m"] == integ["candidate"] and main_head(p) == integ["candidate"]
    assert pic["task_input_sha256"] == hashlib.sha256(TASK).hexdigest() and pic["request"] == request
    env = envelope(p)
    assert env["published"] == 1 and env["reserved"] == 0 and env["status"] == "active"
    assert_control_invariants(p)


def test_the_lead_requests_but_cannot_grant_pic(tmp_path, contained, custody):  # noqa: F811
    """A1 §6 / plan v3 §6: a model Lead cannot grant PIC. A Lead session refuses the grant and the revocation (they are
    the operator endpoint's), the typed surface has no grant, the engine refuses anything but the endpoint's principal,
    and the Lead's request alone publishes nothing: with no envelope, a clean validation is VALIDATE_ONLY."""
    parser = build_parser()
    for argv in (["operator", "grant-publication", "--manifest", "m", "--task", "t"],
                 ["operator", "revoke-publication"]):
        refusal = lead_broker.refuses_locally(parser.parse_args(argv))
        assert refusal and "operator endpoint" in refusal, argv
    assert not [t for t in contract.TOOLS if "grant" in t]
    p = sample_project(tmp_path)
    checks_mode(p)
    files = sealed(tmp_path)
    e = engine(p)
    bound = e.publication_grant_preview(manifest=str(files["manifest"]), task=str(files["task"]))

    class Lookalike:  # what a caller that is not the endpoint could build
        uid, method, endpoint_pid, endpoint_started_at, guarantee = 0, "peer_credentials", 1, "x", "dev"

    for fake in (Lookalike(), {"uid": 0}, None):
        with pytest.raises(errors.PermissionDenied):
            e.publication_grant(fake, bound=bound)  # type: ignore[arg-type]
    assert "authorization" not in control(p)

    wid, custodian, out = pic_prepared(p, tmp_path)
    assert out["result"]["steps"][-1]["publish_if_clean"]["unusable_now"]["condition"] == "revoked"
    assert "authorization_envelope" not in control(p)["work"][wid]
    head = main_head(p)
    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None and result["result"] == "pass"
    assert entry(p, wid)["state"] == "VALIDATED" and main_head(p) == head and not done(p, wid)
    assert control(p)["work"][wid]["integration"]["pic"]["envelope_unusable"]["condition"] == "revoked"
    assert_control_invariants(p)


def test_the_grant_binds_the_sealed_task_and_bounds(tmp_path):
    """n3 and ADR-0018 D4: the task file must hash to the manifest's task input, and the envelope never lasts longer
    or allows more publications than the sealed manifest (nor longer than 72 h); a new grant supersedes the active one,
    and revocation ends it."""
    p = sample_project(tmp_path)
    files = sealed(tmp_path, max_publications=2, duration_s=7200)
    other = tmp_path / "other-task.md"
    other.write_bytes(b"another task\n")
    e = engine(p)
    with pytest.raises(errors.PermissionDenied) as refused:
        e.publication_grant_preview(manifest=str(files["manifest"]), task=str(other))
    assert refused.value.details["reason"] == "task_mismatch"
    for kw in ({"duration_s": 7201}, {"max_publications": 3}):
        with pytest.raises(errors.UsageError):
            e.publication_grant_preview(manifest=str(files["manifest"]), task=str(files["task"]), **kw)
    bound = e.publication_grant_preview(manifest=str(files["manifest"]), task=str(files["task"]))
    assert bound["duration_s"] == 7200 and bound["max_publications"] == 2
    files["manifest"].write_bytes(files["manifest"].read_bytes() + b" ")
    with pytest.raises(errors.StaleAuthority):  # the bytes the operator was shown changed
        e.publication_grant(principal(), bound=bound)
    first = grant(p, tmp_path)
    second = grant(p, tmp_path)
    assert second["supersedes"] == first["envelope"] and envelope(p)["id"] == second["envelope"]
    e.publication_revoke(principal(), envelope_id=second["envelope"])
    assert envelope(p)["status"] == "ended" and envelope(p)["ended"]["reason"] == "revoked"
    assert PO.parse_duration("24h") == 86400 and PO.parse_duration("90") == 90
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- §17, per clause


def _seed_clause(n: int, p: Project, wid: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make §17 clause ``n`` fail between the request and the custodian's validation commit."""
    if n == 1:  # the Ticket's workspace changed after COMMIT_READY: its prepare decision is refused now
        ws = Path(control(p)["work"][wid]["workspace"]["path"])
        (ws / "calc" / "late.py").write_text("LATE = 1\n", encoding="utf-8")
    elif n == 2:
        real = PO.V.obligation
        monkeypatch.setattr(PO.V, "obligation", lambda *a, **k: {**real(*a, **k), "binding": "0" * 64})
    elif n == 5:
        monkeypatch.setattr(PO, "G", SimpleNamespace(open_required_findings=lambda unit: [{"id": "F-0001"}]))
    elif n == 6:
        fake = SimpleNamespace(**{k: getattr(PO.DO, k) for k in ("unit_items", "marks", "HIGH")},
                               undisposed=lambda items, unit: [{"id": "EV-1#F-0001"}])
        monkeypatch.setattr(PO, "DO", fake)
    elif n == 7:
        engine(p)._dispositions.record_violation(token=p.token, subject=wid, detail="a seeded high anomaly")


@pytest.mark.parametrize("clause", [1, 2, 3, 4, 5, 6, 7, 8])
def test_pic_clause(tmp_path, monkeypatch, contained, custody, clause):  # noqa: F811
    """Plan v3 §2.3 and §6: each clause is evaluated in order, and the first that fails is recorded as the reason PIC
    was not exercised; nothing is published, and the entry waits for the Lead (AWAITING_DISPOSITION). Clause 3 is a
    moved head: PIC survives the one rebuild, so it fails only when the head moves again. Clause 4 is the checks'
    result: a failing check takes M4-D5's own path (VERIFICATION_FAILED), never the publish. Clause 8 is an execution
    override on the request's stage."""
    p = sample_project(tmp_path)
    if clause == 4:
        from test_validation_checks import policy, py
        policy(p, checks={"smoke": {"configured": True, "command": py("raise SystemExit(1)"), "cwd": ".",
                                    "timeout_s": 60}}, post=["smoke"])
    else:
        checks_mode(p)
    grant(p, tmp_path)
    wid, report = verifying(p, tmp_path)
    extra = {"execution": {"effort": "high"}} if clause == 8 else {}
    out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report, publish_if_clean=True, **extra)
    assert out["ok"], out["stopped"]
    custodian = lease(p)["custodian"]
    head = main_head(p)
    if clause == 3:
        outside_commit(p, "ONE.md")
        found, result = step(p, custodian, custody)  # the one rebuild under the same lease
        assert found == CO.ACTED and result is not None and result["integration"] == "prepared", result
        assert entry(p, wid)["state"] == "LEASED" and entry(p, wid)["rebuilds_used"] == 1
        head = outside_commit(p, "TWO.md")
    else:
        _seed_clause(clause, p, wid, monkeypatch)
    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None, result
    assert main_head(p) == head and not done(p, wid)  # nothing published
    state = control(p)
    if clause == 4:
        assert result["result"] == "fail" and state["work"][wid]["state"] == "VERIFICATION_FAILED"
        assert control(p)["authorization"]["reserved"] == 0
        assert_control_invariants(p)
        return
    e = entry(p, wid)
    assert e["state"] == "AWAITING_DISPOSITION", e
    history = state["work"][wid].get("integration_history") or []
    pic = (state["work"][wid].get("integration") or {}).get("pic") or next(
        r["pic"] for r in reversed(history) if r.get("pic"))
    assert not pic["exercised"]
    failed = [c for c in pic["clauses"] if not c["ok"]]
    assert [c["clause"] for c in failed] == [clause] and pic["clauses"][-1]["clause"] == clause
    assert all(c["ok"] for c in pic["clauses"][:-1])
    if clause == 3:
        assert e["disposition"]["reason"] == "head_moved_again"
    else:
        assert e["disposition"]["reason"] == "pic_not_exercised" and e["disposition"]["detail"]["clause"] == clause
    assert envelope(p)["reserved"] == 0 and envelope(p)["published"] == 0
    assert_control_invariants(p)


def test_pic_survives_one_rebuild_only(tmp_path, contained, custody):  # noqa: F811
    """Rebuild rule (m5): after a head move the rebuilt candidate is validated again under the same lease and §17 is
    evaluated against the new H, so it publishes. (A second move goes to disposition: `test_pic_clause[3]`.)"""
    p = sample_project(tmp_path)
    checks_mode(p)
    grant(p, tmp_path)
    wid, custodian, _out = pic_prepared(p, tmp_path)
    first = control(p)["work"][wid]["integration"]["candidate"]
    moved = outside_commit(p)
    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None and result["integration"] == "prepared", result
    integ = control(p)["work"][wid]["integration"]
    assert integ["base"] == moved and integ["candidate"] != first and lease(p)["custodian"] == custodian
    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None and result["publish"]["ok"], result
    assert done(p, wid) and main_head(p) == integ["candidate"]
    pic = engine(p).status(wid)["work_unit"]["integration"]["pic"]
    assert pic["exercised"] and pic["h"] == moved and envelope(p)["published"] == 1
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- the envelope


def _seed_unusable(condition: str, p: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                   granted: dict[str, Any], held: dict[str, str]) -> tuple[str, str]:
    """A Ticket prepared with the request, its envelope made unusable by ``condition``: the Ticket and its custodian."""
    if condition == "stamp":  # a Ticket that existed before the grant never belongs to the sealed run
        envelope_id = granted["envelope"]
        wid, custodian, _out = pic_prepared(p, tmp_path)
        assert control(p)["work"][wid].get("authorization_envelope") != envelope_id
        return wid, custodian
    if condition == "exhausted":  # the one publication it allows is used by another Ticket first
        first, first_custodian, _out = pic_prepared(p, tmp_path)
        assert step(p, first_custodian, held)[1]["publish"]["ok"]  # type: ignore[index]
        assert done(p, first)
        wid, report = second_ticket(p, tmp_path)
        out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report, publish_if_clean=True)
        assert out["ok"], out["stopped"]
        return wid, lease(p)["custodian"]
    wid, custodian, _out = pic_prepared(p, tmp_path)
    e = engine(p)
    if condition == "expiry":
        later = datetime.now(UTC) + timedelta(hours=2)
        monkeypatch.setattr(PO, "_now", lambda: later)
    elif condition == "generation":
        # HSD-23: the envelope is the granting generation's. A takeover ends the custodian; the new generation
        # reconciles the lease and prepares again with its own request, which falls outside the old envelope.
        new_generation(p)
        p.lead("integrate", "reconcile", wid)
        engine(p).integrate_prepare(token=p.token, expect_rev=p.rev(), work_id=wid, publish_if_clean=True)
        return wid, lease(p)["custodian"]
    elif condition == "manifest":
        granted["manifest"].write_bytes(granted["manifest"].read_bytes() + b"\n")
    elif condition == "ref":
        monkeypatch.setattr(PO.Publication, "_target_ref", lambda self: "refs/heads/elsewhere")
    elif condition == "legality":  # an operational edit the operator adopts: the pins move
        gates = p.root / ".aew/policy/gates.yaml"
        gates.write_text(gates.read_text(encoding="utf-8").replace("validation: checks",
                                                                   "validation: checks\n  validation_deadline_s: 901"),
                         encoding="utf-8", newline="\n")
        p.adopt_policy()
    elif condition == "revoked":
        e.publication_revoke(principal(), envelope_id=granted["envelope"])
    return wid, custodian


@pytest.mark.parametrize("condition", ["expiry", "exhausted", "generation", "manifest", "stamp", "ref", "legality",
                                       "revoked"])
def test_envelope_unusable(tmp_path, monkeypatch, contained, custody, condition):  # noqa: F811
    """Plan v3 §2.2, `envelope_usable`, per condition: when it fails, the request falls outside the envelope, PIC is not
    exercised and nothing is published; the clean result is VALIDATE_ONLY (VALIDATED), exactly as with no request, and
    the condition is recorded."""
    p = sample_project(tmp_path)
    checks_mode(p)
    if condition == "stamp":
        wid0 = create_planned_ticket(p, tmp_path)  # made before the grant
        assert wid0
    granted = grant(p, tmp_path, max_publications=1 if condition == "exhausted" else 3)
    if condition == "stamp":
        # The Ticket made before the grant is the one prepared: drive it to VERIFY_PENDING and prepare it.
        implement(assign(p, wid0))
        p.lead("work", "transition", wid0, "--to", "REVIEW_PENDING")
        p.lead("review", "ingest", wid0, "--evidence", review(p, wid0))
        p.lead("work", "transition", wid0, "--to", "VERIFY_PENDING")
        out = call(p, "ticket_prepare", work_id=wid0, verification_evidence=verify(p, wid0), publish_if_clean=True)
        assert out["ok"], out["stopped"]
        wid, custodian = wid0, lease(p)["custodian"]
        assert "authorization_envelope" not in control(p)["work"][wid]
    else:
        wid, custodian = _seed_unusable(condition, p, tmp_path, monkeypatch, granted, custody)
    head = main_head(p)
    found, result = step(p, custodian, custody)
    assert found == CO.ACTED and result is not None and result["result"] == "pass", result
    assert entry(p, wid)["state"] == "VALIDATED" and main_head(p) == head and not done(p, wid)
    pic = control(p)["work"][wid]["integration"]["pic"]
    assert not pic["exercised"] and pic["envelope_unusable"]["condition"] == condition, pic
    assert_control_invariants(p)


# ---------------------------------------------------------------------------------------------- HSD-22/23, n4


def test_held_result_never_publishes_under_pic(tmp_path, contained, custody):  # noqa: F811
    """HSD-22, HSD-23: the envelope is bound to the generation that granted it. After a takeover, the custodian of the
    earlier generation commits nothing (its credential is stale), nothing publishes because a result is clean, and
    the envelope ends with its generation."""
    p = sample_project(tmp_path)
    checks_mode(p)
    granted = grant(p, tmp_path)
    wid, custodian, _out = pic_prepared(p, tmp_path)
    head = main_head(p)
    new_generation(p)
    found, result = step(p, custodian, custody)
    assert (found, result) == (CO.ENDED, None)
    assert main_head(p) == head and not done(p, wid)
    with pytest.raises(errors.StaleAuthority):
        with engine(p)._k.custody_txn(custody[custodian], "integrate.validated"):
            pass
    engine(p).checkpoint(token=p.token, expect_rev=p.rev(), note="after the takeover")  # any new-generation commit
    env = envelope(p)
    assert env["id"] == granted["envelope"] and env["status"] == "ended" and env["ended"]["reason"] == "generation"
    assert env["published"] == 0 and env["reserved"] == 0
    assert_control_invariants(p)


@pytest.mark.parametrize("cas", ["landed", "not_landed"])
def test_publication_count_survives_a_crash_between_cas_and_count(tmp_path, monkeypatch, contained, custody, cas):  # noqa: F811
    """n4: a crash after the begin leaves one publication reserved, so published + reserved never exceeds the maximum.
    `integrate reconcile` settles it: a CAS that landed becomes the publication (DONE); one that never landed is
    released, and the candidate returns VALIDATED for the current generation's own decision (HSD-22), never published
    by the reconcile."""
    p = sample_project(tmp_path)
    checks_mode(p)
    grant(p, tmp_path, max_publications=1)
    wid, custodian, _out = pic_prepared(p, tmp_path)
    head = main_head(p)
    e = engine(p)
    if cas == "landed":  # the worker dies after its CAS, before the commit that counts it
        monkeypatch.setenv("AEW_FAULT", "integrate.after_cas")
        monkeypatch.setenv("AEW_FAULT_MODE", "raise")
    else:  # the worker dies after the begin, before its finish

        def crash(credential: str, work_id: str) -> dict[str, Any]:
            raise InjectedFault("the worker died after the begin")

        e._custody.finish = crash
    with pytest.raises(InjectedFault):
        e.custody_step(custodian, custody[custodian])
    monkeypatch.delenv("AEW_FAULT", raising=False)
    state = control(p)
    integ = state["work"][wid]["integration"]
    assert integ["status"] == "publishing" and integ["pic"]["reservation"] == PO.HELD
    env = envelope(p)
    assert env["reserved"] == 1 and env["published"] == 0 and env["published"] + env["reserved"] <= 1
    assert (main_head(p) == integ["candidate"]) == (cas == "landed")
    assert_control_invariants(p)

    out = engine(p).integrate_reconcile(token=p.token, expect_rev=p.rev(), work_id=wid)
    env = envelope(p)
    assert env["reserved"] == 0
    if cas == "landed":
        assert out["state"] == "DONE" and done(p, wid) and env["published"] == 1
    else:
        assert out["reconciled"] == "pic_publish_not_landed" and not out["published"]
        assert main_head(p) == head and env["published"] == 0 and entry(p, wid)["state"] == "VALIDATED"
    assert_control_invariants(p)


def _begun(p: Project, tmp_path: Path, held: dict[str, str]) -> tuple[str, str]:
    """The custodian's validation commit has begun the publish under PIC; its finish has not run yet."""
    p_wid, custodian, _out = pic_prepared(p, tmp_path)
    out = engine(p)._validation.custody_validate(credential=held[custodian], work_id=p_wid)
    assert out["integration"] == "publishing" and envelope(p)["reserved"] == 1, out
    return p_wid, custodian


@pytest.mark.parametrize("why", ["revoked", "anomaly"])
def test_the_finish_withdraws_a_publish_whose_authority_no_longer_holds(tmp_path, contained, custody, why):  # noqa: F811
    """Plan v3 §2.3, S1: the finish re-checks the request, the envelope and §17 in its own transaction, before any CAS.
    An envelope no longer usable (revoked meanwhile) withdraws the publish to VALIDATE_ONLY; a clause that no longer
    holds (a high anomaly opened meanwhile) withdraws it to AWAITING_DISPOSITION. Either way nothing is published, the
    reservation is released and the custodian's lease ends, so the worker has nothing left to retry."""
    p = sample_project(tmp_path)
    checks_mode(p)
    granted = grant(p, tmp_path)
    wid, custodian = _begun(p, tmp_path, custody)
    head = main_head(p)
    e = engine(p)
    if why == "revoked":
        e.publication_revoke(principal(), envelope_id=granted["envelope"])
    else:
        e._dispositions.record_violation(token=p.token, subject=wid, detail="a seeded high anomaly")
    found, result = e.custody_step(custodian, custody[custodian])
    assert found == CO.ACTED and result is not None and result["error"]["reason"] == "pic_withdrawn", result
    assert main_head(p) == head and not done(p, wid) and lease(p) is None
    env = envelope(p)
    assert env["reserved"] == 0 and env["published"] == 0
    integ = control(p)["work"][wid]["integration"]
    assert integ["status"] == "validated" and integ["pic"]["reservation"] == PO.RELEASED
    if why == "revoked":
        assert entry(p, wid)["state"] == "VALIDATED" and integ["pic"]["withdrawn"]["which"] == "revoked"
    else:
        assert entry(p, wid)["state"] == "AWAITING_DISPOSITION" and integ["pic"]["withdrawn"]["which"] == "7"
    assert e.custody_step(custodian, custody[custodian]) == (CO.ENDED, None)
    assert_control_invariants(p)


def test_a_reconcile_after_a_lost_worker_never_completes_an_unlanded_pic_publish(  # noqa: F811
        tmp_path, monkeypatch, contained, custody):  # noqa: F811
    """HSD-22, n4: the worker dies after the begin, so the next commit's sync ends its custodian and marks the lease for
    reconciliation (S2). `integrate reconcile` then releases the reservation and returns the candidate VALIDATED: the
    current generation publishes it, if at all, by its own decision."""
    from aew.harness import procs

    p = sample_project(tmp_path)
    checks_mode(p)
    grant(p, tmp_path)
    wid, custodian = _begun(p, tmp_path, custody)
    e = engine(p)
    e.custody_register(custody[custodian])
    monkeypatch.setattr(procs, "same_process", lambda pid, started: False)
    e.checkpoint(token=p.token, expect_rev=p.rev(), note="any Lead commit runs sync")
    assert lease(p)["reconcile"] is not None and envelope(p)["reserved"] == 1
    head = main_head(p)
    out = e.integrate_reconcile(token=p.token, expect_rev=p.rev(), work_id=wid)
    assert out["reconciled"] == "pic_publish_not_landed" and main_head(p) == head
    assert lease(p) is None and entry(p, wid)["state"] == "VALIDATED" and envelope(p)["reserved"] == 0
    assert_control_invariants(p)


def test_a_request_is_never_exercised_in_verifier_mode(tmp_path, monkeypatch, custody):  # noqa: F811
    """Designer, 2026-10-07: PIC is checks mode only, and the engine never accepts a verifier report for the Lead. With
    an envelope and the request, a clean integration report is routed to VALIDATED, never published."""
    from test_integration_stages import verifier_script
    from test_stage_runner import launching

    p = sample_project(tmp_path)
    lab = launching(p, tmp_path, monkeypatch)
    sync = tmp_path / "sync"
    try:
        grant(p, tmp_path)
        wid, report = verifying(p, tmp_path)
        lab.script("default", verifier_script(sync))
        out = call(p, "ticket_prepare", work_id=wid, verification_evidence=report, publish_if_clean=True)
        assert out["ok"], out["stopped"]
        assert entry(p, wid)["attempts"][-1]["pic_request"]["mode"] == "verifier"
        assert "verifier mode" in out["result"]["steps"][2]["publish_if_clean"]["note"]
        custodian = lease(p)["custodian"]
        head = main_head(p)
        lab.until(lambda: (sync / "ready").exists(), what="the verifier to report")
        (sync / "release").touch()
        [run] = engine(p).stage_intent(out["stage_intent_id"])["steps"][4]["outputs"]["runs"]
        lab.wait(run)
        found, routed = engine(p).custody_step(custodian, custody[custodian])
        assert found == CO.ACTED and routed is not None and routed["routed"]["to"] == "VALIDATED", routed
        integ = control(p)["work"][wid]["integration"]
        assert "pic" not in integ and main_head(p) == head and not done(p, wid)
        assert envelope(p)["reserved"] == 0 and envelope(p)["published"] == 0
        assert_control_invariants(p)
    finally:
        lab.cleanup()
