"""The typed Lead surface's ActionProjection against real workflows and a real supervised run (F15.1; PR #88 review):
publication is offered exactly when the engine permits it, an acceptance decision binds only a report of its kind,
and the guidance that reads run telemetry and submitted evidence is current without a control commit."""

from __future__ import annotations

from aewflow import create_planned_ticket, implement, review, sample_project, to_commit_ready, verify
from fake_harness import HarnessLab

from aew.engine.api import Engine
from aew.surface import projection
from aew.surface.context import SurfaceContext

CTX = SurfaceContext.outside_session()


def _decisions(out):
    return [(d["decision"], d["tool"], tuple(d["evidence"])) for d in out["decisions_required"]]


def test_publication_is_offered_once_the_candidate_is_validated_and_never_before(tmp_path):
    projection.clear_cache()
    p = sample_project(tmp_path)
    wid, _ = to_commit_ready(p, tmp_path)
    p.lead("integrate", "prepare", wid)
    engine = Engine.discover(p.root)
    prepared = projection.project(engine, CTX, wid)
    assert not any(d["decision"] == "PUBLISH" for d in prepared["decisions_required"]), prepared
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    validated = projection.project(engine, CTX, wid)
    [publish] = [d for d in validated["decisions_required"] if d["decision"] == "PUBLISH"]
    assert publish["tool"] == "integration_publish" and publish["default"] == "NONE"
    assert publish["availability"] == "UNKNOWN"
    assert publish["cli_fallback"][:3] == ["integrate", "publish", wid]
    assert p.lead(*publish["cli_fallback"][:3])["state"] == "DONE"  # the advertised command is the engine's own
    done = projection.project(engine, CTX, wid)
    assert done["state"] == "DONE" and done["decisions_required"] == []


def test_a_verifiers_check_results_are_never_offered_as_its_report_and_guidance_follows_the_run(tmp_path):
    projection.clear_cache()
    p = sample_project(tmp_path)
    lab = HarnessLab.create(p, tmp_path)
    try:
        wid = create_planned_ticket(p, tmp_path)
        from aewflow import assign

        implement(assign(p, wid))
        p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
        p.lead("review", "ingest", wid, "--evidence", review(p, wid))
        p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
        inv = p.lead("invoke", "create", wid, "--role", "verifier")["invocation"]
        sync = tmp_path / "sync"
        lab.script(inv, [
            {"do": "check", "id": "unit"},
            {"do": "check", "id": "guardrails"},
            {"do": "submit", "kind": "verification", "meta": {
                "claim": "verification complete", "verification": {"scope": "ticket", "claims": [
                    {"type": "goal_backwards", "claim": "subtract works", "result": "pass",
                     "checks": ["{evidence:check-unit}"]},
                    {"type": "contract", "claim": "scope respected", "result": "pass",
                     "checks": ["{evidence:check-guardrails}"]}]}}},
            {"do": "wait_file", "path": str(sync / "release"), "ready": str(sync / "ready")}])
        launched = lab.lead("harness", "launch", inv)
        lab.until(lambda: (sync / "ready").exists(), what="the verifier to submit")
        engine = Engine.discover(p.root)
        running = projection.project(engine, CTX, wid)
        assert running["decisions_required"] == []  # the run has not ended: nothing to accept yet
        key = projection.control_key(engine)
        (sync / "release").touch()
        lab.wait(launched["run"])
        ended = projection.project(engine, CTX, wid)
        assert projection.control_key(engine) == key, "the run ended without a control commit"
        # Guidance is read now, not from the cache: the ended run's hint, not the running one's.
        projection.clear_cache()
        assert ended["hints"] == projection.project(engine, CTX, wid)["hints"]
        assert not any("is running" in h for h in ended["hints"]), ended["hints"]
        [accept] = ended["decisions_required"]
        assert accept["decision"] == "ACCEPT_VERIFICATION" and accept["tool"] == "ticket_prepare"
        [report] = accept["evidence"]
        run_evidence = next(r for r in ended["runs"] if r["run"] == launched["run"])["evidence"]
        assert len(run_evidence) == 3 and report in run_evidence  # two check results and the report
        assert accept["arguments"]["verification_evidence"] == report
        assert p.lead(*accept["cli_fallback"][:5])  # the advertised ingest is accepted by the engine
    finally:
        lab.cleanup()
