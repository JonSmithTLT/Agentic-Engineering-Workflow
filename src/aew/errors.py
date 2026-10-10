"""AEW error taxonomy.

Every rejection carries a stable machine-readable ``code`` so harness adapters can
react deterministically (for example, re-read status after ``STALE_REVISION``).
"""

from __future__ import annotations

from typing import Any


class AEWError(Exception):
    code = "AEW_ERROR"
    exit_code = 1

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class UsageError(AEWError):
    code = "USAGE"
    exit_code = 2


class NotFound(AEWError):
    code = "NOT_FOUND"
    exit_code = 2


class ProjectNotFound(NotFound):
    code = "PROJECT_NOT_FOUND"


class ValidationFailed(AEWError):
    code = "VALIDATION_FAILED"
    exit_code = 2


class StaleAuthority(AEWError):
    """A superseded Lead (or revoked token) attempted an authoritative write."""

    code = "STALE_AUTHORITY"
    exit_code = 3


class StalePolicy(AEWError):
    """The legality policy in force is not the one a staged action was bound to (M4-E E3; typed surface §3.4 rule 6):
    the step is not committed, and the caller reads the projection again and decides anew."""

    code = "STALE_POLICY"
    exit_code = 3


class StaleRevision(AEWError):
    """The caller's expected control-state revision is not the current one."""

    code = "STALE_REVISION"
    exit_code = 3


class PermissionDenied(AEWError):
    """The presented credential's role/scope does not permit the operation."""

    code = "PERMISSION_DENIED"
    exit_code = 4


class CapabilityUnavailable(PermissionDenied):
    """A capability that is switched off for this project, or refused where it was called (``details["reason"]``).
    Such a refusal is a discoverability guard, never a security boundary: what the capability reads stays readable."""

    code = "CAPABILITY_UNAVAILABLE"


class OperatorAuthorizationRequired(PermissionDenied):
    """An operation needs out-of-band operator authorization that was not given."""

    code = "OPERATOR_AUTHORIZATION_REQUIRED"


class IllegalTransition(AEWError):
    code = "ILLEGAL_TRANSITION"
    exit_code = 5


class GateUnsatisfied(IllegalTransition):
    code = "GATE_UNSATISFIED"


class DependencyUnsatisfied(IllegalTransition):
    code = "DEPENDENCY_UNSATISFIED"


class ConcurrencyLimit(IllegalTransition):
    code = "CONCURRENCY_LIMIT"


class StaleCandidate(IllegalTransition):
    """The authoritative ref moved; the integration candidate must be rebuilt."""

    code = "STALE_CANDIDATE"


class QueueOrder(IllegalTransition):
    """An earlier integration queue entry can integrate now (M4-D: FIFO among runnable entries)."""

    code = "QUEUE_ORDER"


class LeaseHeld(IllegalTransition):
    """Another queue entry holds the integration lease (M4-D)."""

    code = "LEASE_HELD"


class LeaseNotHeld(IllegalTransition):
    """The operation runs only under the Ticket's own integration lease (M4-D)."""

    code = "LEASE_NOT_HELD"


class LeaseReconcileRequired(IllegalTransition):
    """The integration lease lost its custodian: `aew integrate reconcile` first, never a timeout (M4-D)."""

    code = "LEASE_RECONCILE_REQUIRED"


class InputStale(IllegalTransition):
    """A consumed source-bound record no longer matches the source it would be used against (ADR-0008)."""

    code = "INPUT_STALE"


class DispatchRefused(IllegalTransition):
    """The dispatch predicate refused (M4-A): a protected-condition conflict, or Class 0 requested for work that is not
    eligible. ``details`` carries every blocking condition and reason code (``aew dispatch explain`` shows the same)."""

    code = "DISPATCH_REFUSED"


class SteeringNotConfigured(IllegalTransition):
    """A steering mode command on a project whose adopted execution policy names no ``steering.mode``: the project keeps
    legacy/manual behaviour, which is not a fourth mode (M4-E decision 3)."""

    code = "STEERING_NOT_CONFIGURED"


class MigrationRequired(IllegalTransition):
    """The project's control state is v1: the Lead migrates it (`aew migrate`) before changing work (ADR-0011)."""

    code = "MIGRATION_REQUIRED"


class MessagingDisabled(IllegalTransition):
    """A coordination message on a project whose adopted execution policy does not set ``coordination.messaging:
    enabled`` (F9-A, ADR-0017): nothing is recorded. ``details.reason``: ``switched_off`` (absent or ``disabled``) or
    ``not_adopted`` (the policy differs from what the operator adopted, so the switch reads off)."""

    code = "MESSAGING_DISABLED"


class CoordinationLimit(IllegalTransition):
    """A coordination message beyond one of its bounds (F9-A plan D-7). ``details.bound`` names the bound."""

    code = "COORDINATION_LIMIT"


class LeadInboxFull(CoordinationLimit):
    """A worker message while the thread already holds the most worker messages not yet shown to the Lead (D-7)."""

    code = "LEAD_INBOX_FULL"


class IdempotencyConflict(IllegalTransition):
    """An idempotency id already names a message on the thread with other content (D-8): a retry must repeat the
    original exactly, and a new message needs a new id."""

    code = "IDEMPOTENCY_CONFLICT"


class ReplyNotInThread(ValidationFailed):
    """``in_reply_to`` does not name an earlier message of the same thread, or a worker message names no Lead message
    (D-10). ``details.reason``: ``missing``, ``unknown`` or ``not_a_lead_message``."""

    code = "REPLY_NOT_IN_THREAD"


class RefUnknown(ValidationFailed):
    """A message ref names an AEW id that does not exist, or is malformed (D-12)."""

    code = "REF_UNKNOWN"


class NotAWorker(IllegalTransition):
    """A coordination message to an invocation that is not a role-bearing worker: an engine custody invocation (D-17).
    """

    code = "NOT_A_WORKER"


class RecipientIndependent(IllegalTransition):
    """A coordination message to an independent confirmer (F4's scope ``revision``), which never receives Lead text
    (F9-A plan D-34)."""

    code = "RECIPIENT_INDEPENDENT"


class RefOutOfScope(PermissionDenied):
    """A worker's message ref names something outside its own unit, thread, Ticket and runs (D-12)."""

    code = "REF_OUT_OF_SCOPE"


class ObservationMutated(PermissionDenied):
    """A read-only (non-mutating) invocation changed its observation workspace (ADR-0008)."""

    code = "OBSERVATION_MUTATED"


class WorkspaceMutated(PermissionDenied):
    """A reviewer's or verifier's workspace (a mutating Ticket's live workspace, or an integration candidate)
    no longer holds what it was dispatched to evaluate (M3-B6)."""

    code = "WORKSPACE_MUTATED"


class IntegrityError(AEWError):
    """Durable state is damaged or was modified outside the engine."""

    code = "INTEGRITY_ERROR"
    exit_code = 6


class DispatchUndecided(IntegrityError):
    """An engine defect: a transaction created an invocation or a harness run without a dispatch decision (M4-A)."""

    code = "DISPATCH_UNDECIDED"


class MapArtifactCorrupt(IntegrityError):
    """A project-map artifact no longer hashes to its name, or fails its schema (ADR-0015). Derived state: delete and
    regenerate it; a map never grants authority, so nothing else depends on it."""

    code = "MAP_ARTIFACT_CORRUPT"


class MapRegistryInvalid(IntegrityError):
    """The project-map registry is malformed (ADR-0015). Deleting ``.aew/local/maps/`` means "no selection"."""

    code = "MAP_REGISTRY_INVALID"


class MapArtifactNondeterministic(IntegrityError):
    """Regenerating the selected map's commit with the same generator identity gave different bytes (design v0.5
    §17.2). A report, never a lock-out: the registry is left as it is unless the Lead replaces the selection."""

    code = "MAP_ARTIFACT_NONDETERMINISTIC"


class MapCurrentnessUnproven(AEWError):
    """A project map cannot be generated or labelled current from complete inputs (design v0.5 §17.2): a needed Git
    object is missing, a partial clone could fetch lazily, or a commit does not resolve (``details.reason``)."""

    code = "MAP_CURRENTNESS_UNPROVEN"
    exit_code = 6


class WorkspaceNotAuthority(AEWError):
    """A workspace copy of AEW state was used as if it were authoritative."""

    code = "WORKSPACE_NOT_AUTHORITY"
    exit_code = 6


class GitError(AEWError):
    code = "GIT_ERROR"
    exit_code = 7


class LockTimeout(AEWError):
    code = "LOCK_TIMEOUT"
    exit_code = 8


class Unavailable(AEWError):
    """This environment cannot provide a capability (``details["reason"]``), such as a SQLite built without FTS5 for
    the raw-history search. Nothing else is affected."""

    code = "UNAVAILABLE"
    exit_code = 10


class HarnessError(AEWError):
    """A harness run could not be started, supervised or reached (ADR-0009). Never an AEW state change."""

    code = "HARNESS_ERROR"
    exit_code = 9


class HarnessIncompatible(HarnessError):
    """The harness is unknown, or lacks a capability, model or variant this run needs."""

    code = "HARNESS_INCOMPATIBLE"


class HarnessLaunchFailed(HarnessError):
    """The launch was committed (a run was recorded) but its supervisor did not take custody."""

    code = "HARNESS_LAUNCH_FAILED"


class ContainmentUnavailable(HarnessError):
    """Policy requires OS filesystem containment (F2) and this run's sandbox could not be established or failed its
    self-test. No harness process started."""

    code = "CONTAINMENT_UNAVAILABLE"


class RunLive(IllegalTransition):
    """The invocation's latest harness run may still be running; relaunching needs --replace."""

    code = "RUN_LIVE"
