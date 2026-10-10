"""The dispatch predicate's structure (M4-A): the entrypoint registry, the CLI enumeration, the decision type, the
reason-code registry and the pure assurance checks behind it."""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from aew.cli.main import build_parser
from aew.engine import assurance as A
from aew.engine.api import Engine
from aew.engine.dispatch import CLI_DISPATCHES, ENTRYPOINTS, MUTATION, Blocker, DispatchDecision, blocker_from
from aew.engine.reasons import REASONS, require_known
from aew.errors import ConcurrencyLimit, DispatchRefused
from aew.harness import lead_broker

# Every CLI command that does not dispatch. A new command must be classified here or registered as a dispatch
# entrypoint (aew.engine.dispatch): that is how the CLI enumeration proves no CLI dispatch bypasses the registry.
NOT_DISPATCHING = {
    "authority accept", "authority list", "authority reject", "check run", "checkpoint", "context pack",
    "context show", "dashboard open", "dashboard serve", "dashboard status",  # reads only (F20.3)
    "lead mode lower", "lead mode raise", "operator ping", "operator serve",  # steering records only (M4-E E2)
    "dispatch explain", "doctor", "evidence ingest", "gate show", "gate waive", "guide",
    "harness config", "harness interrupt", "harness send", "harness status", "harness stop", "harness wait",
    "history audit", "history compact", "history links", "history list", "history log", "history load",
    "history reindex", "history search", "history show", "init",  # search: a read, present only when switched on
    "integrate breaker reset", "integrate breaker status", "integrate defer", "integrate publish",
    "integrate reconcile", "integrate reorder", "integrate requeue", "integrate validate",  # under the lease (M4-D5)
    "invoke cancel", "invoke show", "lead acquire",
    "lead handoff accept", "lead handoff cancel", "lead handoff offer", "lead release", "lead session", "lead show",
    "lead mcp", "lead tool",  # the typed surface's transports: dispatching tools reach the registry through primitives
    # The `resolve` tool's CLI form (M4-E E3c). Abandon never dispatches. Continue makes no decision of its own: each
    # remaining step is a registered primitive whose own commit takes its dispatch decision (the M4-A choke point),
    # and the journal refuses a step whose commit lacks its allowed decision (BY_DECISION, step_primitive_mismatch).
    "stage abandon", "stage continue",
    "lead takeover", "manifest adopt",
    "map diff", "map generate", "map select-architecture", "map show",  # derived map state (F22.1)
    "message list", "message thread", "message unseen",  # coordination reads, present only when switched on (F9-A)
    "migrate", "opencode", "plan accept", "plan adopt", "plan lint",
    "plan propose", "plan reconfirm", "resume", "review ingest", "role list", "role show", "role validate", "status",
    "submit", "verify classify", "verify ingest", "whoami", "work accept", "work acknowledge-input", "work cancel",
    "work close", "work create", "work depend", "work list", "work move", "work promote", "work ready",
    "work reclassify", "work reconcile", "work roles", "work show", "work staff", "work transition", "work tree",
}


def leaves(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()):
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not subs:
        yield path
        return
    for action in subs:
        for name, child in action.choices.items():
            yield from leaves(child, (*path, name))


def test_every_cli_command_is_a_registered_dispatch_or_classified_as_not_dispatching():
    # every command, the switched ones too
    commands = {" ".join(p) for p in leaves(build_parser(recall_search=True, coordination_reads=True))}
    dispatching = {" ".join(p) for p in CLI_DISPATCHES}
    assert dispatching <= commands, dispatching - commands
    assert not dispatching & NOT_DISPATCHING
    unclassified = commands - dispatching - NOT_DISPATCHING
    assert not unclassified, f"classify these commands (dispatch entrypoint or not): {sorted(unclassified)}"
    assert not NOT_DISPATCHING - commands, NOT_DISPATCHING - commands


def test_the_lead_broker_requires_launch_for_exactly_the_dispatches_that_print_a_credential():
    broker = {tuple(sorted(p)) for p in lead_broker.DISPATCHES}
    # launch prints none; integrate prepare's custodian holds no credential at all (M4-D)
    printing = {tuple(sorted(p)) for p in CLI_DISPATCHES if p not in {("harness", "launch"), ("integrate", "prepare")}}
    assert broker == printing


def test_entrypoints_are_declared_with_an_owner_for_every_guard(tmp_path):
    engine = Engine(tmp_path, tmp_path / ".aew")  # construction touches no file
    names = engine._dispatch.guard_names()
    for e in ENTRYPOINTS.values():
        assert set(e.guards) <= names, (e.name, set(e.guards) - names)
        assert (e.surface == "cli") == (e.cli is not None), e.name
        assert e.surface == "cli" or e.covered_by, e.name
    # The M4 assurance guards run last on every entrypoint that can grant mutation.
    for name in ("work.assign", "invoke.create.mutating", "harness.launch"):
        assert ENTRYPOINTS[name].guards[-len(MUTATION):] == MUTATION


def test_the_dispatch_finalizer_runs_before_archival(tmp_path):
    engine = Engine(tmp_path, tmp_path / ".aew")
    steps = [f"{type(s.__self__).__name__}.{s.__func__.__name__}" for s in engine._k.finalizers.steps]
    assert steps == ["StageIntents.finalize", "Dispatch.finalize", "Queue.finalize", "Validation.finalize",
                     "UsageCopy.finalize", "Coordination.finalize", "Archive.finalize"]


# ---------------------------------------------------------------- the decision


def decision(**kw) -> DispatchDecision:
    return DispatchDecision(entrypoint="work.assign", work_id="T-0001", revision=7, generation=1, channel="cli",
                            **kw)


def test_require_raises_a_migrated_checks_own_error_unchanged():
    err = ConcurrencyLimit("mutating concurrency is 1", holding=["T-0002"])
    d = decision(blocking=[blocker_from(err)])
    assert not d.allowed and d.reason_codes == ["CONCURRENCY_LIMIT"]
    with pytest.raises(ConcurrencyLimit) as raised:
        d.require()
    assert raised.value is err


def test_require_names_every_new_blocking_condition_and_its_obligations():
    d = decision(blocking=[Blocker("PROTECTED_CONDITION_OVERLAP", "scope includes vendor/lib.py"),
                           Blocker("CLASS0_ASSERTION_MISSING", "assertions missing")],
                 obligations=[{"code": "ACCEPTANCE_INPUT_IN_SCOPE", "paths": ["tests/data.json"]}])
    with pytest.raises(DispatchRefused) as raised:
        d.require()
    details = raised.value.details
    assert details["reason_codes"] == ["ACCEPTANCE_INPUT_IN_SCOPE", "CLASS0_ASSERTION_MISSING",
                                       "PROTECTED_CONDITION_OVERLAP"]
    assert [b["code"] for b in details["blocking_conditions"]] == ["PROTECTED_CONDITION_OVERLAP",
                                                                  "CLASS0_ASSERTION_MISSING"]


def test_the_digest_covers_the_decision_not_the_guards_working_facts():
    a, b = decision(), decision()
    b.facts = {"card": object(), "inputs": [1, 2]}
    assert a.digest() == b.digest() and a.allowed
    c = decision(dependency_digests={"source": "abc"})
    assert c.digest() != a.digest()
    assert a.provenance()["decision"] == a.digest()


def test_every_reason_code_is_registered_and_unknown_codes_are_refused():
    for code in REASONS:
        assert require_known(code) == code
    with pytest.raises(ValueError, match="not in the registry"):
        require_known("SOMETHING_NEW")


# ---------------------------------------------------------------- the pure assurance checks

FILES = ["calc/core.py", "tests/test_core.py", "tests/data/input.json", "vendor/lib.py", "calc/crypto.py"]
GUARDRAILS = {"protected_paths": ["vendor/**"],
              "review_triggers": [{"name": "security", "paths": ["calc/crypto*.py"]}]}
CHECKS = {"checks": {"unit": {"configured": True, "command": ["pytest"]}, "manual": {"configured": False}}}


def meta(scope=("calc/core.py", "tests/**"), checks=("unit",), inputs=(), goal=("works",), asserts=None):
    return {"scope": {"paths": list(scope)},
            "acceptance": {"goal_backwards": list(goal), "contract": [], "checks": list(checks),
                           "inputs": list(inputs)},
            "class0_assertions": sorted(A.CLASS0_ASSERTIONS) if asserts is None else list(asserts)}


def test_a_protected_path_inside_an_explicit_scope_is_an_overlap():
    assert A.protected_overlap(["calc/**"], GUARDRAILS, FILES) == []
    assert A.protected_overlap(["**"], GUARDRAILS, FILES) == ["vendor/lib.py"]
    assert A.protected_overlap(["vendor/lib.py"], GUARDRAILS, FILES) == ["vendor/lib.py"]
    assert A.protected_overlap([], GUARDRAILS, FILES) == []  # unbounded: the gates still hold it to the policy


def test_acceptance_inputs_inside_the_scope_are_a_hard_trigger():
    assert A.acceptance_inputs_in_scope(["tests/**"], ["tests/data/input.json"], FILES) == ["tests/data/input.json"]
    assert A.acceptance_inputs_in_scope(["calc/**"], ["tests/data/input.json"], FILES) == []
    assert A.acceptance_inputs_in_scope([], ["tests/data/*.json"], FILES) == ["tests/data/*.json"]


def test_an_eligible_class0_ticket_has_no_blocker():
    assert A.class0_blockers(meta=meta(), files=FILES, guardrails=GUARDRAILS, checks=CHECKS, triggers=[],
                             lint=[]) == []


@pytest.mark.parametrize("change, code", [
    ({"scope": ()}, "CLASS0_SUBJECT_UNBOUNDED"),
    ({"scope": ("**",)}, ["CLASS0_SUBJECT_UNBOUNDED", "CLASS0_CONSEQUENTIAL_BOUNDARY"]),  # it reaches calc/crypto.py
    ({"scope": ("nowhere/**",)}, "CLASS0_SUBJECT_UNBOUNDED"),
    ({"checks": ()}, "CLASS0_NO_ACCEPTANCE_REFERENCE"),
    ({"goal": ()}, "CLASS0_NO_ACCEPTANCE_REFERENCE"),
    ({"checks": ("manual",)}, "CLASS0_ACCEPTANCE_NOT_DETERMINISTIC"),
    ({"asserts": ("transformation_clear",)}, "CLASS0_ASSERTION_MISSING"),
    ({"scope": ("calc/**",)}, "CLASS0_CONSEQUENTIAL_BOUNDARY"),
])
def test_each_class0_condition_refuses_on_its_own(change, code):
    found = A.class0_blockers(meta=meta(**change), files=FILES, guardrails=GUARDRAILS, checks=CHECKS, triggers=[],
                              lint=[])
    assert [b["code"] for b in found] == (code if isinstance(code, list) else [code])


def subject_codes(scope, files=FILES, gates=None):
    found = A.class0_blockers(meta=meta(scope=scope), files=files, guardrails={}, checks=CHECKS, triggers=[],
                              lint=[], gates=gates)
    return [b for b in found if b["code"] == "CLASS0_SUBJECT_UNBOUNDED"]


def test_class0_bounded_subject_is_measured_not_listed():
    """D2 (area 3 F2): a glob whose first segment is `**` is never bounded, and a scope over more than 50 tracked
    files is refused; in a tree of at least 40 tracked files, so is one over a quarter of it. The measure is in the
    refusal; every bound comes from policy (operator, 2026-10-03 and 2026-10-04)."""
    assert subject_codes(("**/*.py",)) and subject_codes(("./**/x",))  # whatever they match today
    tree = [f"lib/m{i}.py" for i in range(30)] + [f"docs/p{i}.md" for i in range(70)]  # 100 tracked files
    [wide] = subject_codes(("lib/**",), files=tree)  # 30 of 100: more than a quarter
    assert wide["details"]["subject"]["matched"] == 30 and wide["details"]["subject"]["tracked"] == 100
    assert "30 of 100" in wide["message"]
    assert not subject_codes(("lib/m1*.py",), files=tree)  # 11 of 100
    assert not subject_codes(("lib/**",), files=tree, gates={"class0": {"max_scope_fraction": 0.5}})
    big = [f"src/m{i}.py" for i in range(60)] + [f"other/f{i}.txt" for i in range(400)]
    assert subject_codes(("src/**",), files=big)  # 60 files: over the 50-file bound, though only 13% of the tree
    assert not subject_codes(("src/**",), files=big, gates={"class0": {"max_scope_files": 100}})


def test_a_small_tree_can_be_a_class0_subject_whatever_share_of_it_the_scope_covers():
    """D2, refined (operator, 2026-10-04): small repositories and utilities are where Class 0 work is most common, so
    below 40 tracked files the quarter-of-the-tree bound does not apply. The 50-file and `**` rules still do."""
    small = ["calc/core.py", "calc/__init__.py", "tests/test_core.py", "README.md", "vendor/lib.py"]
    assert not subject_codes(("calc/**", "tests/**"), files=small)  # 3 of 5
    assert A.subject_measure(["calc/**"], small)["fraction_applies"] is False
    assert subject_codes(("**/*.py",), files=small)
    assert subject_codes(("calc/**",), files=small, gates={"class0": {"fraction_min_tree_files": 5}})


def test_an_inherited_elevated_obligation_has_its_own_class0_refusal():
    found = A.class0_blockers(meta=meta(), files=FILES, guardrails=GUARDRAILS, checks=CHECKS,
                              triggers=[{"code": "INHERITED_ELEVATED_OBLIGATION", "floor": 2, "gates": []}], lint=[])
    assert [b["code"] for b in found] == ["CLASS0_INHERITED_ELEVATED_OBLIGATION"]
    assert found[0]["details"] == {"floor": 2, "gates": []} and "minimum class 2" in found[0]["message"]


def test_a_hard_trigger_or_a_lint_finding_makes_class0_ineligible():
    found = A.class0_blockers(meta=meta(), files=FILES, guardrails=GUARDRAILS, checks=CHECKS,
                              triggers=[{"code": "ACCEPTANCE_INPUT_IN_SCOPE"}],
                              lint=[{"code": "LINT_AFFECTED_OUTSIDE_SCOPE", "severity": "warning"}])
    assert [b["code"] for b in found] == ["CLASS0_HARD_TRIGGER", "CLASS0_PLAN_LINT"]


def test_plan_lint_finds_the_structural_defects():
    m = meta(scope=("calc/**",), checks=("unit", "nope"), inputs=("calc/data.json",))
    found = {f["code"]: f["severity"] for f in A.plan_lint(
        meta=m, affected=["calc/data.json", "vendor/lib.py", "docs/x.md"], guardrails=GUARDRAILS, checks=CHECKS,
        mutating=True)}
    assert found == {"LINT_ACCEPTANCE_CHECK_UNKNOWN": "error", "LINT_AFFECTED_PROTECTED": "error",
                     "LINT_AFFECTED_OUTSIDE_SCOPE": "warning", "LINT_ACCEPTANCE_INPUT_WRITABLE": "warning"}
    bare = A.plan_lint(meta=meta(checks=(), goal=()), affected=[], guardrails=GUARDRAILS, checks=CHECKS,
                       mutating=True)
    assert [f["code"] for f in bare] == ["LINT_NO_ACCEPTANCE_MECHANISM"]
    assert A.plan_lint(meta=meta(), affected=["calc/core.py"], guardrails=GUARDRAILS, checks=CHECKS,
                       mutating=True) == []
    for code in found:
        assert code in REASONS


def test_the_reason_registry_maps_only_to_canonical_failure_classes():
    registry = (Path(__file__).resolve().parents[2] / "docs/design/failure-class-registry.md").read_text(
        encoding="utf-8")
    for code, reason in REASONS.items():
        if reason.failure_class:
            assert f"`{reason.failure_class}`" in registry, (code, reason.failure_class)


# ---------------------------------------------------------------- primitive declarations (v0.4 idea note §3-§4)


def test_every_dispatch_entrypoint_and_integration_primitive_is_declared():
    from aew.engine import primitives as P

    for e in ENTRYPOINTS.values():
        if e.surface == "cli":
            spec = P.spec_for(e.name)
            assert spec.declared and spec.guard_id == e.name, e.name
    for name in ("integrate.prepare", "verify.ingest.integration", "integrate.publish", "integrate.reconcile",
                 "integrate.defer", "integrate.requeue", "integrate.reorder"):
        assert P.spec_for(name).declared, name
    for spec in P.SPECS.values():
        assert spec.operation_class in P.OPERATION_CLASSES, spec
        assert (spec.operation_class == P.JUDGMENT_BEARING) == bool(spec.required_judgments), spec
    assert P.spec_for("integrate.publish").operation_class == P.JUDGMENT_BEARING  # §11: publish stays a decision


def test_an_undeclared_primitive_is_judgment_bearing():
    from aew.engine import primitives as P

    spec = P.spec_for("work.something_new")
    assert not spec.declared and spec.operation_class == P.JUDGMENT_BEARING and spec.required_judgments
