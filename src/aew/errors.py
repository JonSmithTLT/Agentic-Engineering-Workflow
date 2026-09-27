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


class StaleRevision(AEWError):
    """The caller's expected control-state revision is not the current one."""

    code = "STALE_REVISION"
    exit_code = 3


class PermissionDenied(AEWError):
    """The presented credential's role/scope does not permit the operation."""

    code = "PERMISSION_DENIED"
    exit_code = 4


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


class InputStale(IllegalTransition):
    """A consumed source-bound record no longer matches the source it would be used against (ADR-0008)."""

    code = "INPUT_STALE"


class ObservationMutated(PermissionDenied):
    """A read-only (non-mutating) invocation changed its observation workspace (ADR-0008)."""

    code = "OBSERVATION_MUTATED"


class IntegrityError(AEWError):
    """Durable state is damaged or was modified outside the engine."""

    code = "INTEGRITY_ERROR"
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


class RunLive(IllegalTransition):
    """The invocation's latest harness run may still be running; relaunching needs --replace."""

    code = "RUN_LIVE"
