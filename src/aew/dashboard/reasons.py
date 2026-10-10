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
    # raw-history search (register F20.8, S2): the capability, then the coverage of one search
    "FTS5_UNAVAILABLE": "this Python's SQLite has no usable FTS5, which raw-history search needs; nothing else is "
                        "affected",
    "RECALL_NOT_IN_INVOCATIONS": ("the dashboard server runs inside an invocation's environment, where raw-history "
                                  "search is not offered (a discoverability guard, not a security boundary)"),
    "SEARCH_BUILD_BUDGET": "the search index had more history to catch up than one search may spend; search again to "
                           "continue",
    "SEARCH_CANDIDATE_BUDGET": "more candidates matched than one search verifies; narrow the terms or the filters",
    "SEARCH_TIME_BUDGET": "the search reached its time limit; the hits verified before it are shown",
    "SEARCH_SUBSTRATE_BUSY": "another AEW process is writing the search index; search again in a moment",
    "SEARCH_SUBSTRATE_REBUILDING": "the search index is being rebuilt; search again in a moment",
    "SEARCH_SUBSTRATE_STALE": ("a search index row disagrees with the history and was left out; the dashboard never "
                               "repairs the index: the next `aew history search` or `aew history reindex` does"),
    "SEARCH_SUBSTRATE_FOREIGN": ("the search index describes another history; the next `aew history search` or "
                                 "`aew history reindex` rebuilds it"),
    "SEARCH_SUBSTRATE_UNUSABLE": ("the search index is damaged or of another version and no hit is served from it; "
                                  "the next `aew history search` or `aew history reindex` rebuilds it"),
    "SEARCH_HISTORY_MOVED": "the history changed while it was read; search again",
    "SEARCH_HISTORY_UNREADABLE": ("part of the history could not be read for the search index; `aew history audit` "
                                  "reports damage"),
    "SEARCH_UNVERIFIED": ("candidates whose history records could not be authenticated were left out: a commit that "
                          "landed during the search can cause this, as can damage, which `aew history audit` reports"),
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
