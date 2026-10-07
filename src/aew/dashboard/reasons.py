"""Every reason code the dashboard server can put in a response (design note §4.11).

The contract types every explanation as a ``Reason {code, message}`` and tells the frontend to display the message
and never to conclude anything from the code. The codes still form one registry, so a test can check that every code a
response carries is known here and has a message; an unregistered code is a bug, not a vocabulary extension.
"""

from __future__ import annotations

from typing import Any

REASONS: dict[str, str] = {
    # the session (F20.3)
    "SESSION_REQUIRED": "a dashboard session is required: run `aew dashboard open` and follow the URL it prints",
    "SESSION_EXPIRED": "the dashboard session ended: run `aew dashboard open` for a new one",
    # requests
    "INVALID_REQUEST": "the request is not valid for this route",
    "CURSOR_INVALID": "the cursor does not belong to this query scope; restart the query without it",
    "CURSOR_EXPIRED": "the control revision changed since this page was taken; restart the query",
    "NOT_FOUND": "no such record",
    "CAPABILITY_UNAVAILABLE": "this capability is not available on this project",
    "PROJECTION_FAILED": "the projection could not be refreshed; the last known content stands",
    "METHOD_NOT_ALLOWED": "only GET and HEAD are served",
    "REQUEST_TOO_LARGE": "the request exceeds the server's bounds",
    "SERVER_BUSY": "the server is answering as many requests as it allows at once; retry in a second",
    "HOST_NOT_ALLOWED": "the request names a host this server does not serve",
    "ORIGIN_NOT_ALLOWED": "the request comes from an origin this server does not serve",
    # capabilities
    "MIGRATION_REQUIRED": ("this project's control state is schema v1; the operator runs `aew migrate` to "
                           "enable history"),
    "HISTORY_INDEX_UNAVAILABLE": "the history index could not be read or synced",
    "NOT_IN_CONTRACT_0_1_2": "no route of contract 0.1.2 projects this; a later contract version may",
    "AWAITS_ACTION_PROJECTION": "the action projection arrives with the typed Lead surface (register F15.1); until "
                                "then this capability is unsupported",
    # integrity (the engine's over-policy findings, by code)
    "UNVERIFIED_ENTRIES_OVER_POLICY": "more unverified history entries than the gates policy allows",
    "UNVERIFIED_AGE_OVER_POLICY": "the oldest unverified history entry is older than the gates policy allows",
    "FULL_VERIFICATION_OVERDUE": "no full verification of the history within the gates policy's window",
    # health and attention
    "CONTRADICTION": "the engine detected an inconsistency the Lead must resolve",
    "RUN_LOST": "a harness run's supervisor stopped reporting",
    "RUN_CRASHED": "a harness run ended abnormally",
    "MANIFEST_PIN_MISMATCH": "project.yaml does not match the hash control state pins",
    "POLICY_PIN_MISMATCH": "a policy file project.yaml names does not match the hash control state pins",
    "BLOCKED_BY": "a dependency or plan condition blocks this unit",
    "STATE_REASON": "the reason the engine recorded with the unit's current state",
    "TRANSITION_REASON": "the reason recorded with the transition",
    "FINDING": "a finding the producing role recorded",
    "DEVIATION": "a deviation from the plan the producing role recorded",
    "NEXT_ACTION": "the engine's next action for this unit",
}


def reason(code: str, message: str | None = None) -> dict[str, Any]:
    """A contract ``Reason`` with a registered code; the message defaults to the registry's."""
    if code not in REASONS:
        raise KeyError(f"unregistered dashboard reason code {code!r}")
    return {"code": code, "message": REASONS[code] if message is None else message}


def codes_in(value: Any) -> set[str]:
    """Every ``code`` string in a response body (nested ``Reason`` objects and the ``Error`` envelope): what the
    registry test checks."""
    found: set[str] = set()
    if isinstance(value, dict):
        if isinstance(value.get("code"), str) and "message" in value:
            found.add(value["code"])
        for v in value.values():
            found |= codes_in(v)
    elif isinstance(value, list):
        for v in value:
            found |= codes_in(v)
    return found
