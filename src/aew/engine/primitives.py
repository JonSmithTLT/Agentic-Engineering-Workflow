"""Primitive declarations (M4-A; the two-interaction-surfaces direction v0.4 §3-§4).

A ``PrimitiveSpec`` states, for one engine primitive, what kind of operation it is, which judgments and policy it
needs, what it changes and which guard decides its legality. Stage commands (M4-E) expand into primitives and refuse
any that is unclassified or whose judgment input is missing; the integration queue (M4-D) drives the integration
primitives through these declarations. M4-A declares the dispatch entrypoints and the integration primitives; other
primitives are declared as stages come to use them (§12-§13: one primitive at a time).

An undeclared primitive is ``JUDGMENT_BEARING`` (fail closed, §3).
"""

from __future__ import annotations

from typing import NamedTuple

MECHANICAL = "MECHANICAL"  # fully determined by durable state and engine rules
POLICY_RESOLVED = "POLICY_RESOLVED"  # fully determined by recorded policy; a caller override is attributable
JUDGMENT_BEARING = "JUDGMENT_BEARING"  # needs interpretation, preference, consequence acceptance or disposition
OPERATION_CLASSES = (MECHANICAL, POLICY_RESOLVED, JUDGMENT_BEARING)

POLICY = ("gates", "guardrails", "checks", "roles", "execution")


class PrimitiveSpec(NamedTuple):
    primitive_id: str
    operation_class: str
    required_judgments: tuple[str, ...]
    required_policy_inputs: tuple[str, ...]
    required_evidence: tuple[str, ...]
    side_effect_class: str  # what it changes: control_state, credential, workspace, harness_process, authoritative_ref
    idempotency_scope: str  # what makes a repeat a no-op or a refusal: the expected revision, the run, the candidate
    guard_id: str | None  # the dispatch entrypoint (or, later, the queryable guard) that decides its legality
    declared: bool = True


SPECS: dict[str, PrimitiveSpec] = {s.primitive_id: s for s in (
    # Dispatch: legality is the DispatchDecision of the entrypoint of the same name; the card and execution profile
    # are resolved from policy (a Lead's --card, --profile or --model is an attributable override).
    PrimitiveSpec("work.assign", POLICY_RESOLVED, (), POLICY, (), "control_state+workspace+credential",
                  "expected_revision", "work.assign"),
    PrimitiveSpec("work.dispatch", POLICY_RESOLVED, (), POLICY, (), "control_state+workspace+credential",
                  "expected_revision", "work.dispatch"),
    PrimitiveSpec("work.redispatch", JUDGMENT_BEARING, ("supersession_reason",), POLICY, (),
                  "control_state+workspace+credential", "expected_revision", "work.redispatch"),
    PrimitiveSpec("invoke.create.mutating", POLICY_RESOLVED, (), POLICY, (), "control_state+credential",
                  "expected_revision", "invoke.create.mutating"),
    PrimitiveSpec("invoke.create.non_mutating", POLICY_RESOLVED, (), POLICY, (), "control_state+workspace+credential",
                  "expected_revision", "invoke.create.non_mutating"),
    PrimitiveSpec("invoke.create.parent", POLICY_RESOLVED, (), POLICY, (), "control_state+workspace+credential",
                  "expected_revision", "invoke.create.parent"),
    PrimitiveSpec("harness.launch", MECHANICAL, (), ("execution",), (), "control_state+credential+harness_process",
                  "expected_revision", "harness.launch"),
    # Integration (ADR-0004), driven by the M4-D queue: prepare's legality, and the lease it grants, is the
    # ``integrate.prepare`` dispatch decision; publish and post-integration verification run under that lease.
    PrimitiveSpec("integrate.prepare", MECHANICAL, (), ("gates", "guardrails"), ("current_gates",),
                  "control_state+workspace", "expected_revision", "integrate.prepare"),
    # Checks-mode validation (M4-D5): the mode and the exact check set are resolved from recorded policy, so the
    # command is policy-resolved; its substeps (pin, execute contained, fingerprint, write evidence) are mechanical.
    PrimitiveSpec("integrate.validate", POLICY_RESOLVED, (), ("gates", "checks", "guardrails", "execution"),
                  ("prepared_candidate",), "control_state", "candidate", None),
    PrimitiveSpec("verify.ingest.integration", JUDGMENT_BEARING, ("accept_verification",), ("gates",),
                  ("integration_verification",), "control_state", "expected_revision", None),
    PrimitiveSpec("integrate.publish", JUDGMENT_BEARING, ("publish_decision",), ("gates",),
                  ("integration_validation",), "authoritative_ref+control_state", "candidate", None),
    PrimitiveSpec("integrate.reconcile", MECHANICAL, (), (), (), "authoritative_ref+control_state", "candidate", None),
    # The Lead's queue commands (M4-D4): scheduling, never eligibility; each is the Lead's disposition of an entry.
    PrimitiveSpec("integrate.defer", JUDGMENT_BEARING, ("queue_disposition",), (), (), "control_state+workspace",
                  "expected_revision", None),
    PrimitiveSpec("integrate.requeue", JUDGMENT_BEARING, ("queue_disposition",), (), (), "control_state",
                  "expected_revision", None),
    PrimitiveSpec("integrate.reorder", JUDGMENT_BEARING, ("queue_disposition",), (), (), "control_state",
                  "expected_revision", None),
    # The Lead's checkpoint (F15.1: the typed surface's one normal-profile mutation): a handoff note and next action,
    # one transaction under the caller's expected revision.
    PrimitiveSpec("checkpoint", MECHANICAL, (), (), (), "control_state", "expected_revision", None),
    # The Lead's own steering (M4-E E2): a lowering or a request, one transaction; it never raises authority.
    PrimitiveSpec("steering", MECHANICAL, (), ("execution",), (), "control_state", "expected_revision", None),
)}


def spec_for(primitive_id: str) -> PrimitiveSpec:
    """The declaration of a primitive, or the fail-closed default for one nobody declared."""
    return SPECS.get(primitive_id) or PrimitiveSpec(primitive_id, JUDGMENT_BEARING, ("undeclared",), (), (),
                                                    "unknown", "unknown", None, declared=False)


# The Lead transactions a primitive commits under, where they are not just its own id: the three creations share
# `invoke.create`, and steering is a lowering or a request. The stage journal refuses a step whose commit is not one of
# its planned primitive's (M4-E E3).
COMMIT_OPS: dict[str, frozenset[str]] = {
    "invoke.create.mutating": frozenset({"invoke.create"}),
    "invoke.create.non_mutating": frozenset({"invoke.create"}),
    "invoke.create.parent": frozenset({"invoke.create"}),
    "steering": frozenset({"steering.lower", "steering.request"}),
}
# Declared primitives that do not commit in exactly one Lead transaction: a stage step is one primitive in one commit,
# so these are refused at a stage's opening, never left to fail at their first commit (#140 re-review, finding 1).
# Publication and validation commit twice (a marker, then the outcome); reconciliation finishes a publication;
# integration verification is ingested by the verifier, not in a Lead transaction. Their stages arrive with E6.
NOT_STEPS = frozenset({"integrate.publish", "integrate.validate", "integrate.reconcile", "verify.ingest.integration"})


def commit_ops(primitive_id: str) -> frozenset[str]:
    return COMMIT_OPS.get(primitive_id, frozenset({primitive_id}))


CLASS_RANK = {MECHANICAL: 0, POLICY_RESOLVED: 1, JUDGMENT_BEARING: 2}
