"""Execution profiles through the CLI (ADR-0010): the pin at dispatch, Lead overrides, engine-owned
provenance on evidence, and fail-closed policy handling. Scripted roles only; no harness is launched."""

from __future__ import annotations

from pathlib import Path

from aewflow import (
    Role,
    assign,
    create_investigation,
    create_planned_ticket,
    dispatch,
    implement,
    sample_project,
    submit_record,
)
from invariants import assert_control_invariants

from aew.knowledge import evidence as E
from aew.util import dump_yaml, load_yaml, sha256_file

POLICY = {
    "schema": "aew/execution/v1", "configured": True, "harness": "opencode",
    "profiles": {"standard": {"provider": "prov", "model": "m-standard", "effort": "high"},
                 "review": {"provider": "prov2", "model": "m-review", "effort": "max"},
                 "light": {"provider": "prov", "model": "m-light", "effort": "low", "max_steps": 30}},
    "routing": {"default": "standard", "archetypes": {"reviewer": "review"}, "classes": {"0": "light"},
                "cards": {"researcher": "review"}},
    "provider_env": ["PROV_API_KEY"],
}


def configure(p, policy=POLICY) -> Path:
    path = p.root / ".aew/policy/execution.yaml"
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    p.pin_policy()
    return path


def pin(p, inv_id):
    return p.ok("invoke", "show", inv_id)["execution_profile"]


def evidence(p, wid, eid):
    return E.read(p.root / ".aew/evidence" / wid / f"{eid}.md")[0]


def doctor(p):
    return {c["check"]: c["status"] for c in p.aew("doctor", "--json").json["checks"]}


def refused(p, *args):
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode != 0, res.stdout
    return res.error


def test_init_writes_an_unconfigured_policy_and_dispatch_pins_nothing(tmp_path):
    p = sample_project(tmp_path)
    policy = load_yaml((p.root / ".aew/policy/execution.yaml").read_text(encoding="utf-8"))
    assert policy["configured"] is False and policy["profiles"] == {}
    assert doctor(p)["policy:execution"] == "WARN"
    wid = create_planned_ticket(p, tmp_path)
    out = p.lead("work", "assign", wid)
    assert pin(p, out["invocation"]) is None  # scripted M1/M2 flows are unaffected
    assert_control_invariants(p)


def test_projects_without_a_policy_file_keep_working(tmp_path):
    """A project initialized before M3 has no execution.yaml: it behaves as unconfigured."""
    p = sample_project(tmp_path)
    (p.root / ".aew/policy/execution.yaml").unlink()
    p.pin_policy()
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    implement(impl)
    inv = p.ok("work", "show", wid)["control"]["implementer_invocation"]
    assert pin(p, inv) is None


def test_policy_routing_is_pinned_per_invocation_and_stamped_on_evidence(tmp_path):
    p = sample_project(tmp_path)
    path = configure(p)
    sha = sha256_file(path)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    impl_inv = p.ok("work", "show", wid)["control"]["implementer_invocation"]
    assert pin(p, impl_inv) == {"profile": "standard", "harness": "opencode", "provider": "prov",
                                "model": "m-standard", "effort": "high", "max_steps": None, "deadline_s": None,
                                "selected_by": "policy", "rule": "default", "policy_sha256": sha}
    implement(impl)
    records, problems = E.scan(p.root / ".aew", wid)
    assert not problems
    for ev in records:  # the check result and the implementation report
        producer = ev["producer"]
        assert producer["execution_profile"] == pin(p, impl_inv)
        assert producer["credential"].startswith("tk_") and producer["run"] is None  # no harness run yet
    report = next(ev for ev in records if ev["kind"] == "implementation_report")
    assert report["producer"]["model"] == "scripted"  # the submitter's declaration is kept, labelled as declared


def test_editing_the_policy_never_changes_an_in_flight_invocation(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    inv = p.ok("work", "show", wid)["control"]["implementer_invocation"]
    before = pin(p, inv)
    changed = dict(POLICY, profiles={**POLICY["profiles"], "standard": {"provider": "x", "model": "y"}})
    configure(p, changed)
    implement(impl)
    assert pin(p, inv) == before
    report = next(ev for ev in E.scan(p.root / ".aew", wid)[0] if ev["kind"] == "implementation_report")
    assert report["producer"]["execution_profile"]["model"] == "m-standard"


def test_archetype_class_and_card_routes(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    light = create_planned_ticket(p, tmp_path, title="Tiny change", cls=0)
    out = p.lead("work", "assign", light)
    assert (pin(p, out["invocation"])["profile"], pin(p, out["invocation"])["rule"]) == ("light", "class:0")
    research = create_investigation(p, tmp_path, title="Library capability", card="researcher")
    _, out = dispatch(p, research)
    assert pin(p, out["invocation"])["rule"] == "card:researcher"
    assert_control_invariants(p)


def test_reviewer_routes_by_archetype(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    wid = create_planned_ticket(p, tmp_path)
    implement(assign(p, wid))
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    out = p.lead("invoke", "create", wid, "--role", "reviewer")
    got = pin(p, out["invocation"])
    assert (got["profile"], got["model"], got["rule"]) == ("review", "m-review", "archetype:reviewer")


def test_lead_overrides_are_recorded_and_never_widen_authority(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    a = create_planned_ticket(p, tmp_path, title="A")
    out = p.lead("work", "assign", a, "--model", "other/m-x", "--effort", "low")
    got = pin(p, out["invocation"])
    assert (got["provider"], got["model"], got["effort"], got["selected_by"]) == ("other", "m-x", "low", "lead")
    assert p.ok("invoke", "show", out["invocation"])["role"] == "implementer"  # a model choice is not authority
    inv = create_investigation(p, tmp_path, title="Survey")
    res = p.aew("work", "dispatch", inv, "--profile", "light", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.returncode == 0, res.stderr
    assert pin(p, res.json["invocation"])["profile"] == "light"
    redo = p.lead("work", "redispatch", inv, "--reason", "needs a stronger model", "--profile", "review")
    assert pin(p, redo["invocation"])["profile"] == "review"


def test_bad_selections_and_invalid_policies_fail_closed_without_a_commit(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    wid = create_planned_ticket(p, tmp_path)
    rev = p.rev()
    assert refused(p, "work", "assign", wid, "--profile", "nope")["code"] == "USAGE"
    assert refused(p, "work", "assign", wid, "--profile", "light", "--model", "a/b")["code"] == "USAGE"
    assert refused(p, "work", "assign", wid, "--model", "no-slash")["code"] == "USAGE"
    configure(p, dict(POLICY, routing={**POLICY["routing"], "default": "missing"}))
    assert refused(p, "work", "assign", wid)["code"] == "VALIDATION_FAILED"
    configure(p, dict(POLICY, profiles={"standard": {"provider": "p", "model": "m", "api_key": "sk-secret"}}))
    assert refused(p, "work", "assign", wid)["code"] == "VALIDATION_FAILED"
    assert doctor(p)["policy:execution"] == "FAIL"
    assert p.rev() == rev and p.ok("work", "show", wid)["control"]["state"] == "READY"


def test_submitters_cannot_forge_engine_owned_producer_fields(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    wid = create_planned_ticket(p, tmp_path)
    impl = assign(p, wid)
    impl.write({"calc/core.py": "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"})
    for forged in ({"execution_profile": {"model": "frontier"}}, {"run": "R-INV-0001-9"}, {"credential": "tk_0"},
                   {"invocation": "INV-0099"}):
        res = impl.submit("implementation_report", {
            "claim": "done", "result": "pass", "producer": forged,
            "implementation": {"files_changed": ["calc/core.py"], "checks_run": [], "deviations": [],
                               "self_review": {"completed": True, "notes": "n/a"}}}, expect_ok=False)
        assert res.returncode != 0 and res.error["code"] == "VALIDATION_FAILED", res.stdout
        assert f"producer.{next(iter(forged))}" in res.error["details"]["fields"]


def test_non_mutating_record_carries_the_executor_pin(tmp_path):
    p = sample_project(tmp_path)
    configure(p)
    wid = create_investigation(p, tmp_path)
    role, out = dispatch(p, wid)
    rec = submit_record(role, "discovery_record")["evidence"]
    assert evidence(p, wid, rec)["producer"]["execution_profile"]["profile"] == "standard"
    assert isinstance(role, Role)
