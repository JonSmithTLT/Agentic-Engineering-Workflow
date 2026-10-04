"""M4-A through the CLI: protected conditions, hard triggers, Class 0 eligibility, plan lint, the policy cap, and the
commit-time rule that no invocation or run exists without a dispatch decision (plan assurance v0.4 §10, §18, §22,
§31; the Class 0 Workflow Contract amendment; m4-ambiguity-report.md §2.1-§2.3)."""

from __future__ import annotations

import pytest
from aewflow import SUBTRACT_PATCH, assign, implement, sample_project
from invariants import assert_control_invariants

from aew.engine.api import Engine
from aew.errors import DispatchUndecided, IllegalTransition, UsageError
from aew.util import dump_yaml, load_yaml

ALL_ASSERTIONS = ("--class0-assert", "transformation_clear", "--class0-assert", "inputs_complete",
                  "--class0-assert", "no_consequential_boundary")


def ticket(p, tmp_path, *, cls=1, scope=("calc/**", "tests/**"), extra=(), affected=("calc/core.py",)):
    args = ["work", "create", "ticket", "--title", "Add subtract()", "--class", str(cls),
            "--goal", "calc.core.subtract(5, 3) == 2", *extra]
    for s in scope:
        args += ["--scope", s]
    wid = p.lead(*args)["id"]
    plan = tmp_path / f"{wid}-plan.md"
    plan.write_text("Add subtract and a focused test.\n", encoding="utf-8")
    more = [a for path in affected for a in ("--affected", path)]
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), *more)
    p.lead("plan", "accept", wid, "--revision", "1")
    return wid


def refused(p, *args):
    rev = p.rev()
    res = p.aew(*args, "--token", p.token, "--expect-rev", str(rev))
    assert res.returncode == 5, res.stdout
    assert p.rev() == rev  # a refused dispatch commits nothing
    return res.error


def codes(err):
    return set(err["details"]["reason_codes"])


def set_policy(p, name, change):
    path = p.root / f".aew/policy/{name}.yaml"
    policy = load_yaml(path.read_text(encoding="utf-8"))
    change(policy)
    path.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- protected conditions (v0.4 §10, §31)


def test_a_protected_path_inside_the_scope_refuses_dispatch(tmp_path):
    """§31: protected fixture inside mutable scope -> reject."""
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, scope=("calc/**", "vendor/**"))
    err = refused(p, "work", "assign", wid)
    assert err["code"] == "DISPATCH_REFUSED" and codes(err) == {"PROTECTED_CONDITION_OVERLAP"}
    [cond] = err["details"]["blocking_conditions"]
    assert cond["details"]["paths"] == ["vendor/lib.py"]
    assert p.ok("work", "show", wid)["control"]["state"] == "READY"


def test_a_plan_that_names_a_protected_path_refuses_dispatch_and_lint_says_why(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, affected=("calc/core.py", "vendor/lib.py"))
    lint = p.ok("plan", "lint", wid, "--json")
    assert not lint["clean"] and [e["code"] for e in lint["errors"]] == ["LINT_AFFECTED_PROTECTED"]
    # The out-of-scope warning is reported with it, as an obligation.
    assert codes(refused(p, "work", "assign", wid)) == {"LINT_AFFECTED_PROTECTED", "LINT_AFFECTED_OUTSIDE_SCOPE"}


def test_an_acceptance_input_inside_the_scope_is_an_obligation_not_a_refusal_at_class_1(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, extra=("--acceptance-check", "unit", "--acceptance-input", "tests/test_core.py"))
    out = p.lead("work", "assign", wid)
    obligations = {o["code"]: o for o in out["dispatch"]["effective_obligations"]}
    assert obligations["ACCEPTANCE_INPUT_IN_SCOPE"]["paths"] == ["tests/test_core.py"]
    recorded = p.ok("invoke", "show", out["invocation"])["dispatch"]
    assert "ACCEPTANCE_INPUT_IN_SCOPE" in recorded["obligations"]
    assert_control_invariants(p)


# ---------------------------------------------------------------- Class 0 eligibility (WC amendment, v0.4 §22)


def eligible_class0(p, tmp_path, **kw):
    return ticket(p, tmp_path, cls=0, scope=("calc/core.py", "tests/test_subtract.py"),
                  extra=("--acceptance-check", "unit", *ALL_ASSERTIONS), **kw)


def test_an_eligible_class0_ticket_is_dispatched(tmp_path):
    p = sample_project(tmp_path)
    wid = eligible_class0(p, tmp_path)
    out = p.lead("work", "assign", wid)
    assert out["dispatch"]["allowed"] and out["dispatch"]["effective_obligations"] == []
    assert_control_invariants(p)


def test_class0_without_the_leads_assertions_is_refused_and_never_reclassified(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py",), extra=("--acceptance-check", "unit"))
    err = refused(p, "work", "assign", wid)
    assert err["code"] == "DISPATCH_REFUSED" and codes(err) == {"CLASS0_ASSERTION_MISSING"}
    assert f"aew work reclassify {wid}" in err["message"]
    assert p.ok("work", "show", wid)["control"]["risk_class"] == 0  # refused, not reclassified
    explained = p.ok("dispatch", "explain", wid, "--json")
    assert set(explained["reason_codes"]) == codes(err)


def test_class0_needs_an_acceptance_check_and_a_bounded_scope(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, cls=0, scope=(), extra=ALL_ASSERTIONS)
    assert codes(refused(p, "work", "assign", wid)) >= {"CLASS0_NO_ACCEPTANCE_REFERENCE",
                                                         "CLASS0_SUBJECT_UNBOUNDED"}


def test_class0_is_refused_where_a_hard_trigger_or_a_consequential_boundary_applies(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py", "tests/**"),
                 extra=("--acceptance-check", "unit", "--acceptance-input", "tests/test_core.py", *ALL_ASSERTIONS))
    assert "CLASS0_HARD_TRIGGER" in codes(refused(p, "work", "assign", wid))
    set_policy(p, "guardrails", lambda g: g.update(review_triggers=[{"name": "security", "paths": ["calc/**"]}]))
    other = eligible_class0(p, tmp_path)
    assert codes(refused(p, "work", "assign", other)) == {"CLASS0_CONSEQUENTIAL_BOUNDARY"}


def test_class0_under_a_parent_with_an_elevated_obligation_is_refused(tmp_path):
    p = sample_project(tmp_path)
    story = p.lead("work", "create", "story", "--title", "Hardening", "--class", "2", "--mandatory-gate",
                   "review_security", "--rationale", "security-relevant objective")["id"]
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py",),
                 extra=("--parent", story, "--acceptance-check", "unit", *ALL_ASSERTIONS))
    err = refused(p, "work", "assign", wid)
    assert codes(err) == {"CLASS0_INHERITED_ELEVATED_OBLIGATION", "INHERITED_ELEVATED_OBLIGATION"}
    p.lead("work", "reclassify", wid, "--class", "1", "--reason", "the Story's security obligation applies")
    out = p.lead("work", "assign", wid)  # the stronger class is dispatched, and the inherited gate stays required
    assert "INHERITED_ELEVATED_OBLIGATION" in [o["code"] for o in out["dispatch"]["effective_obligations"]]
    assert "review_security" in p.ok("gate", "show", wid)["obligations"]["non_waivable"]


def test_a_tickets_own_acceptance_check_must_pass_before_it_completes(tmp_path):
    """PR #32 review P1: a check the Ticket declares (``--acceptance-check``) and the policy's path lists do not name
    is a non-waivable gate. Missing or failing, the Ticket cannot become COMMIT_READY; passing on the current
    definition, it can."""
    p = sample_project(tmp_path)
    set_policy(p, "checks", lambda c: c["checks"].update(acceptance={
        **c["checks"]["unit"], "command": ["{python}", "-c", "raise SystemExit(1)"]}))
    gates = load_yaml((p.root / ".aew/policy/gates.yaml").read_text(encoding="utf-8"))
    assert "acceptance" not in gates["local_checks"] + gates["post_integration"]["checks"]
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py", "tests/test_subtract.py"),
                 extra=("--acceptance-check", "acceptance", *ALL_ASSERTIONS))
    impl = assign(p, wid)
    implement(impl, SUBTRACT_PATCH)  # passes `unit`, the policy's local check

    def commit_ready_refusal():
        res = p.aew("work", "transition", wid, "--to", "COMMIT_READY", "--token", p.token, "--expect-rev", str(p.rev()))
        assert res.returncode != 0, res.stdout
        return res.error

    missing = commit_ready_refusal()
    assert missing["code"] == "GATE_UNSATISFIED" and missing["details"]["unmet"] == {"acceptance_checks": "MISSING"}
    assert impl.check("acceptance")["result"] == "fail"
    assert commit_ready_refusal()["details"]["unmet"] == {"acceptance_checks": "FAILED"}
    waiver = p.aew("gate", "waive", wid, "--gate", "acceptance_checks", "--reason", "x", "--token", p.token,
                   "--expect-rev", str(p.rev()))
    assert waiver.returncode != 0 and "non-waivable" in waiver.error["message"]

    set_policy(p, "checks", lambda c: c["checks"]["acceptance"].update(command=c["checks"]["unit"]["command"]))
    assert impl.check("acceptance")["result"] == "pass"
    shown = p.ok("gate", "show", wid)
    assert shown["gates"]["acceptance_checks"]["checks"]["acceptance"]["status"] == "CURRENT"
    assert "acceptance_checks" in shown["obligations"]["non_waivable"]
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    assert_control_invariants(p)


def test_reclassify_needs_a_reason_a_valid_class_and_an_unfinished_unit(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    with pytest.raises(UsageError, match="needs the reason"):
        engine.work_reclassify(token=p.token, expect_rev=p.rev(), work_id=wid, risk_class=2, reason="  ")
    with pytest.raises(UsageError, match="0..4"):
        engine.work_reclassify(token=p.token, expect_rev=p.rev(), work_id=wid, risk_class=5, reason="x")
    p.lead("work", "transition", wid, "--to", "CANCELLED", "--reason", "not needed")
    rev = p.rev()
    with pytest.raises(IllegalTransition, match="finished work is archived"):  # a cancelled Ticket is archived
        engine.work_reclassify(token=p.token, expect_rev=rev, work_id=wid, risk_class=2, reason="x")
    assert p.rev() == rev


def test_class0_assertions_are_refused_on_other_classes(tmp_path):
    p = sample_project(tmp_path)
    res = p.aew("work", "create", "ticket", "--title", "x", "--class", "1", *ALL_ASSERTIONS, "--token", p.token,
                "--expect-rev", str(p.rev()))
    assert res.returncode == 2 and res.error["code"] == "USAGE"


def test_a_new_implementer_rechecks_class0_eligibility(tmp_path):
    """A new implementer is a dispatch, too: policy that changed since assignment is seen."""
    p = sample_project(tmp_path)
    wid = eligible_class0(p, tmp_path)
    impl = assign(p, wid)
    implement(impl, SUBTRACT_PATCH)
    p.lead("invoke", "cancel", p.ok("work", "show", wid)["control"]["implementer_invocation"], "--reason", "redo")
    set_policy(p, "checks", lambda c: c["checks"]["unit"].update(configured=False, command=None))
    err = refused(p, "invoke", "create", wid, "--role", "implementer")
    assert "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC" in codes(err)


# ---------------------------------------------------------------- the cap reads policy, clamped until M4-C


def test_the_mutating_cap_reads_policy_but_stays_one_until_m4c(tmp_path):
    p = sample_project(tmp_path, gates=None)
    set_policy(p, "gates", lambda g: g.update(mutating_concurrency=3))
    t1, t2 = ticket(p, tmp_path), ticket(p, tmp_path)
    p.lead("work", "assign", t1)
    err = refused(p, "work", "assign", t2)
    assert err["code"] == "CONCURRENCY_LIMIT" and "mutating concurrency is 1" in err["message"]


# ---------------------------------------------------------------- no invocation without a decision


def test_a_transaction_that_creates_an_invocation_without_a_decision_cannot_commit(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match="without a dispatch decision"):
        with engine._k.lead_txn(p.token, rev, "test.bypass") as ctx:
            engine._invocations.new_invocation(ctx, "reviewer", wid)
    assert p.rev() == rev


def test_a_decision_admits_only_the_invocation_it_checked(tmp_path):
    """PR #32 review P2: admission is bound to what the decision checked. A wrapper entrypoint cannot be decided
    on its own; a decision admits only the role and card its guards resolved; one decision admits one invocation."""
    p = sample_project(tmp_path)
    blocked = ticket(p, tmp_path, scope=("calc/**", "vendor/**"))  # assignment is refused: protected path
    assert refused(p, "work", "assign", blocked)["code"] == "DISPATCH_REFUSED"
    engine = Engine.discover(p.root)
    for wrapper in ("lead_broker.relay", "dispatch.launch"):
        rev = p.rev()
        with pytest.raises(UsageError, match="covered by"):
            with engine._k.lead_txn(p.token, rev, "test.wrapper") as ctx:
                engine._dispatch.decide_in(ctx, wrapper, blocked)
        assert p.rev() == rev

    wid = ticket(p, tmp_path)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match=r"\(reviewer\)"):  # an implementer's decision, a reviewer created
        with engine._k.lead_txn(p.token, rev, "test.other_role") as ctx:
            engine._dispatch.decide_in(ctx, "work.assign", wid)
            engine._invocations.new_invocation(ctx, "reviewer", wid)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match=r"\(implementer\)"):  # an assignment's decision, integration scope
        with engine._k.lead_txn(p.token, rev, "test.other_scope") as ctx:
            card = engine._dispatch.decide_in(ctx, "work.assign", wid).facts["card"]
            engine._invocations.new_invocation(ctx, "implementer", wid, scope="integration", card=card)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match="INV-0002"):  # the same decision used for a second invocation
        with engine._k.lead_txn(p.token, rev, "test.twice") as ctx:
            card = engine._dispatch.decide_in(ctx, "work.assign", wid).facts["card"]
            engine._invocations.new_invocation(ctx, "implementer", wid, card=card)
            engine._invocations.new_invocation(ctx, "implementer", wid, card=card)
    assert p.rev() == rev and p.ok("work", "show", wid)["control"]["invocations"] == []


def test_a_decision_from_another_revision_admits_nothing(tmp_path):
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    stale = engine._dispatch.decide(engine.store.read(), "work.assign", wid)
    p.lead("checkpoint", "--next", "the revision moves")
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match="not this transaction"):
        with engine._k.lead_txn(p.token, rev, "test.stale") as ctx:
            ctx.dispatch_decisions.append(stale)
            engine._invocations.new_invocation(ctx, "reviewer", wid)
    assert p.rev() == rev


# ---------------------------------------------------------------- the dispatch legality review (area 3, 2026-10-03)


def test_a_decision_refuses_a_record_or_plan_edited_outside_aew(tmp_path):
    """D1: the predicate reads the Ticket record and the accepted plan only when they are the files control state
    pins; an out-of-band edit that would turn a refusal into an admission is refused instead."""
    from aew.util import parse_frontmatter, render_frontmatter

    def edit(path, change):
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        change(meta)
        path.write_text(render_frontmatter(meta, body), encoding="utf-8", newline="\n")

    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path, cls=0, scope=("calc/core.py",), extra=("--acceptance-check", "unit"))
    assert codes(refused(p, "work", "assign", wid)) == {"CLASS0_ASSERTION_MISSING"}
    record = p.root / ".aew" / p.ok("work", "show", wid)["control"]["record"]
    edit(record, lambda m: m.update(class0_assertions=["inputs_complete", "no_consequential_boundary",
                                                       "transformation_clear"]))
    res = p.aew("work", "assign", wid, "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "record" in res.error["message"], res.stderr
    assert p.aew("dispatch", "explain", wid, "--json").error["code"] == "INTEGRITY_ERROR"

    p2 = sample_project(tmp_path / "second")
    wid2 = ticket(p2, tmp_path, affected=("calc/core.py", "vendor/lib.py"))
    assert "LINT_AFFECTED_PROTECTED" in codes(refused(p2, "work", "assign", wid2))
    plan = p2.root / ".aew" / p2.ok("work", "show", wid2)["control"]["plan"]["path"]
    edit(plan, lambda m: m.update(affected_paths=["calc/core.py"]))
    res = p2.aew("work", "assign", wid2, "--token", p2.token, "--expect-rev", str(p2.rev()))
    assert res.error["code"] == "INTEGRITY_ERROR" and "accepted plan" in res.error["message"], res.stderr
    assert p2.ok("work", "show", wid2)["control"]["invocations"] == []


def test_class0_refuses_a_scope_that_starts_with_a_globstar_even_without_protected_paths(tmp_path):
    """D2: `**/*.py` is every Python file in the repository, not a bounded subject."""
    p = sample_project(tmp_path, guardrails={"schema": "aew/guardrails/v1", "protected_paths": [],
                                             "generated_paths": [], "ticket_scope_enforcement": True,
                                             "review_triggers": [], "dependency_rules": []})
    wide = ticket(p, tmp_path, cls=0, scope=("**/*.py",), extra=("--acceptance-check", "unit", *ALL_ASSERTIONS))
    err = refused(p, "work", "assign", wide)
    assert codes(err) == {"CLASS0_SUBJECT_UNBOUNDED"}
    [blocker] = [b for b in err["details"]["blocking_conditions"] if b["code"] == "CLASS0_SUBJECT_UNBOUNDED"]
    assert blocker["details"]["subject"]["leading_globstar"] == ["**/*.py"]
    ok = eligible_class0(p, tmp_path)
    assert p.ok("dispatch", "explain", ok, "--json")["dependency_digests"]["class0_subject"]["matched"] == 1


def test_an_acceptance_check_on_a_non_mutating_ticket_is_refused(tmp_path):
    """D3: it would be recorded and never run."""
    p = sample_project(tmp_path)
    res = p.aew("work", "create", "ticket", "--title", "Survey", "--class", "1", "--non-mutating", "--goal", "g",
                "--acceptance-check", "unit", "--token", p.token, "--expect-rev", str(p.rev()))
    assert res.error["code"] == "USAGE" and "non-mutating" in res.error["message"], res.stderr


def test_a_commit_outside_the_lead_transaction_cannot_create_an_undecided_invocation(tmp_path):
    """D4: the rule holds in the store's commit, so a commit path that runs no finalizers is covered too."""
    from aew.engine.store import Transition

    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match="INV-9999"):
        with engine._k.store.session() as s:
            s.state["invocations"]["INV-9999"] = {"work_unit": wid, "role": "implementer", "status": "active"}
            s.commit(Transition(op="test.bypass", actor={"kind": "test"}))
    assert p.rev() == rev


def test_a_decision_made_before_a_policy_edit_admits_nothing(tmp_path):
    """D6: a decision records the policy digests it was made under; the commit refuses it if they changed."""
    p = sample_project(tmp_path)
    wid = ticket(p, tmp_path)
    engine = Engine.discover(p.root)
    rev = p.rev()
    with pytest.raises(DispatchUndecided, match="policy files"):
        with engine._k.lead_txn(p.token, rev, "test.policy") as ctx:
            card = engine._dispatch.decide_in(ctx, "work.assign", wid).facts["card"]
            set_policy(p, "guardrails", lambda g: g["protected_paths"].append("calc/**"))
            engine._invocations.new_invocation(ctx, "implementer", wid, card=card)
    assert p.rev() == rev
