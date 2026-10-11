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
    # Run 1 of a dispatch made with `launch` (M4-E E5a; plan v3 §1, E4, E5, N4): recorded in that dispatch's own commit
    # and covered by its decision (the registered internal entrypoint, `covered_by`), then handed with the dispatch's
    # credential to the run's supervisor. A stage records it as the step after its dispatch, in the same commit
    # (`stage_intents.StepBinding.covers`); the provenance it stamps on the run is unchanged.
    PrimitiveSpec("dispatch.launch", MECHANICAL, (), ("execution",), (), "control_state+credential+harness_process",
                  "expected_revision", "dispatch.launch"),
    # The Ticket stages' own primitives (M4-E E5a: declared with the first stage that runs them, plan v3 E5). Each
    # guard is the queryable one its execute path requires (E4: `Engine.guard_query`).
    # A unit created from the Lead's proposition: its title, class, scope, criteria and dependencies are the Lead's.
    PrimitiveSpec("work.create", JUDGMENT_BEARING, ("ticket_proposition",), ("gates", "guardrails", "roles"), (),
                  "control_state", "expected_revision", "work.create"),
    # A plan proposed, never accepted: its body and declared assurance are the Lead's.
    PrimitiveSpec("plan.propose", JUDGMENT_BEARING, ("plan_proposal",), ("gates", "roles"), (), "control_state",
                  "expected_revision", "plan.propose"),
    # A Lead transition: legal only by the transition table, the state hooks and the rule's named guard, all read from
    # durable state. A cancellation ends the Ticket's attempt: it revokes its invocations' credentials (`credential`);
    # its ended observations' worktrees are removed when they are archived after its commit (`workspace`; the
    # implementer's worktree is kept); and a live run's supervisor ends its harness once the run's credential is revoked
    # (`harness_process`). Each is observed (test_a_cancellations_effects_are_declared; PR #177 review, finding 1).
    PrimitiveSpec("work.transition", MECHANICAL, (), ("gates",), (),
                  "control_state+workspace+credential+harness_process", "expected_revision", "work.transition"),
    # A mutating Ticket's report, accepted (M4-E E5b: declared with `ticket_request_verification`, plan v3 E5). The
    # acceptance is the Lead's; its legality is the ingest's own guard, `DISPOSITION_REQUIRED` included (§2.4). It
    # completes the reporter's invocation, revoking its credential (`credential`), and a run still live under that
    # credential is ended by its supervisor (`harness_process`); the reporter shares the Ticket's workspace, so no
    # worktree is removed. Each is observed (test_declared_effects_cover_observed_effects).
    PrimitiveSpec("review.ingest", JUDGMENT_BEARING, ("accept_review_evidence",), ("gates", "guardrails", "roles"),
                  ("review",), "control_state+credential+harness_process", "expected_revision", "review.ingest"),
    # The Ticket-scope acceptance of a verification report (`verify ingest` with the Ticket's scope). Declared in E5b
    # with the same guard rule; `ticket_prepare` (E6a) is the first stage to run it.
    PrimitiveSpec("verify.ingest", JUDGMENT_BEARING, ("accept_verification",), ("gates", "checks", "guardrails"),
                  ("verification",), "control_state+credential+harness_process", "expected_revision", "verify.ingest"),
    # The Lead's disposition of a finding, claim or anomaly (M4-E E5b; plan v3 §2.4): one transaction under the
    # caller's expected revision, through `resolve` or `aew work dispose`. Always a judgment; it never resolves a
    # required finding and never moves a unit.
    PrimitiveSpec("work.dispose", JUDGMENT_BEARING, ("disposition",), ("gates",), (), "control_state",
                  "expected_revision", None),
    # Integration (ADR-0004), driven by the M4-D queue: prepare's legality, and the lease it grants, is the
    # ``integrate.prepare`` dispatch decision; publish and post-integration verification run under that lease. The
    # grant mints the custodian's custody credential (M4-E E6a: `credential`), whose worker the granting process then
    # starts (an engine process, never a harness).
    PrimitiveSpec("integrate.prepare", MECHANICAL, (), ("gates", "guardrails"), ("current_gates",),
                  "control_state+workspace+credential", "expected_revision", "integrate.prepare"),
    # Checks-mode validation (M4-D5): the mode and the exact check set are resolved from recorded policy, so the
    # command is policy-resolved; its substeps (pin, execute contained, fingerprint, write evidence) are mechanical.
    PrimitiveSpec("integrate.validate", POLICY_RESOLVED, (), ("gates", "checks", "guardrails", "execution"),
                  ("prepared_candidate",), "control_state", "candidate", None),
    # The Lead's acceptance of the integration verifier's report (M4-E E6a: completed with `integration_publish`, the
    # first stage to run it). It completes the verifier's invocation, revoking its credential (`credential`; a run still
    # live under it is ended by its supervisor, `harness_process`), and on a VALIDATED entry it is granted the fresh
    # lease it runs under, minting its custodian's credential. Its guard is its own query (`verify.ingest.integration`).
    PrimitiveSpec("verify.ingest.integration", JUDGMENT_BEARING, ("accept_verification",), ("gates",),
                  ("integration_verification",), "control_state+credential+harness_process", "expected_revision",
                  "verify.ingest.integration"),
    # The Lead's publication decision (M4-E E6a: completed with `integration_publish`). Its step is the intent
    # commit (`integrate.publishing`, with a VALIDATED entry's fresh lease); the CAS, the sync and DONE follow it as its
    # effect: the authoritative ref, the integration worktree and a removable Ticket workspace (`workspace`), and DONE's
    # revocations (the lease's custody credential, `credential`; a live run's supervisor ends its harness,
    # `harness_process`). A moved head commits the one rebuild instead. Its guard is its own query.
    PrimitiveSpec("integrate.publish", JUDGMENT_BEARING, ("publish_decision",), ("gates",),
                  ("integration_validation",), "authoritative_ref+control_state+workspace+credential+harness_process",
                  "candidate", "integrate.publish"),
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
    # A Lead coordination message (F9-A plan v4 D-17): recorded on its thread under the control lock, committing
    # nothing; the switch it needs is execution policy's `coordination.messaging`. Its `expect_rev` is checked like
    # every stage's, but a repeat is recognized by its `idempotency_id` (D-8): recording moves no revision.
    PrimitiveSpec("message.send", MECHANICAL, (), ("execution",), (), "coordination_record", "idempotency_id", None),
    # The current Lead's resolution of an unfinished stage (M4-E E3c; typed surface §3.4 rule 8): continue (rebind it
    # to this generation, then run its remaining steps, each its own primitive) or abandon. Always a Lead judgment.
    PrimitiveSpec("stage.resolve", JUDGMENT_BEARING, ("stage_resolution",), (), (), "control_state",
                  "expected_revision", None),
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
    "stage.resolve": frozenset({"stage.continue", "stage.abandon"}),
    # M4-E E6a: a publish's step is its intent commit; what follows it is its effect, committed unarmed (the finish,
    # or `integrate reconcile` after a crash). The integration-scoped ingest enters its transaction as itself.
    "integrate.publish": frozenset({"integrate.publishing"}),
}
# The ops a step's commit records instead of its primitive's completion: its disposition (M4-E E6a; plan v3 §2.3 and
# the E4b disposition rule). The journal records it on the step, and the stage stops there unless it planned for it.
DISPOSITION_OPS: dict[str, frozenset[str]] = {
    "integrate.publish": frozenset({"integrate.superseded", "integrate.stale", "integrate.rebuild"}),
}
# Declared primitives that cannot run as one stage step, each with the reason: a step is one primitive in one Lead
# transaction whose op says which primitive committed (#140 re-reviews). They are refused at a stage's opening, never
# left to fail at their first commit. E6a stages a publish as its intent commit (`COMMIT_OPS`) and the integration
# ingest under its own transaction op; validation is the custodian's, never a stage step (plan v3 §2.3).
NOT_STEPS: dict[str, str] = {
    "integrate.validate": "it commits twice (integrate.validate, then integrate.validated), and it is the lease's "
                          "custodian's, never the Lead's stage step (plan v3 §2.3)",
    "integrate.reconcile": "it can finish a publication, committing under integrate.publish",
    # F9-A plan v4 D-17 (v1 review F6): `message_send` has no stage planner and is never journaled.
    "message.send": "it commits nothing (a coordination message is recorded on its thread, not in a transition)",
    "stage.resolve": "it resolves another stage's journal; a stage never runs inside one",
    "work.dispose": "a disposition is one judgment in one transaction, made through `resolve`: never a stage step",
}
# Primitives that share their commit op with another: the dispatch decision the commit recorded (its entrypoint)
# says which one committed (#140 re-review: the three creations are chosen by the unit's kind, not by the caller).
BY_DECISION = frozenset({"invoke.create.mutating", "invoke.create.non_mutating", "invoke.create.parent"})


def commit_ops(primitive_id: str) -> frozenset[str]:
    return COMMIT_OPS.get(primitive_id, frozenset({primitive_id}))


# Primitives whose commit is another step's: a launch is run 1 of the dispatch planned just before it, committed by
# that dispatch's transaction and admitted by its decision (M4-E E5a; plan v3 §1). The stage journal records it in the
# dispatch's commit, as the next step (`stage_intents.StepBinding.covers`), and it never runs as a step of its own.
COVERED_BY_PREVIOUS: dict[str, frozenset[str]] = {
    "dispatch.launch": frozenset({"work.assign", "work.dispatch", "invoke.create.mutating",
                                  "invoke.create.non_mutating", "invoke.create.parent"}),
}


CLASS_RANK = {MECHANICAL: 0, POLICY_RESOLVED: 1, JUDGMENT_BEARING: 2}
