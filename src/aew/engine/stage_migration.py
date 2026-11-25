"""E329 cutover for hot stage intents. Closed records retain their original bytes and pins."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from aew.engine.stage_intents import REFERENCE, STEP_STATE, digest

_REVISION = "expect_rev"

# Digest pairs pin the recognized predecessor and E329 successor. A later catalog edit still has to pass the normal
# contract and exact-plan checks, and an older unrecognized contract never gains permission from this migration.
_CONTRACTS = {
    "ticket_draft": (
        "40a8459709d9776e3f250d5e451bcae39c231801c03a239c41feda6185ae460c",
        "bc561f82e2a0c7a325fab80470864c29b97252417fb16fd00c1b63d25cf094bb"),
    "ticket_start": (
        "748ac3a327b24f655b7a333eaa4aee71261d16dc97f40ef0d3b2922d0f75230f",
        "fc9ce4a8ae2e59ae133a13b849513110b81653e72dacea1c046b2810d0627203"),
    "ticket_request_review": (
        "2438b0a1502c233b88ed9d87329edec5201424349135ce0304beaab047660bb4",
        "4a764eb5207f2156cdc32ebb630ad51b29c6d1dcfb7cf97944ba741c8d4996da"),
    "ticket_request_verification": (
        "7529ca19c620c10e968a3325e480b91bd136ea3969ed14e77802159d8a62c0a5",
        "c293f9bdaa18792ac9af5117eba62b983fd6b1479c974dfd7ab1f3a50ff133bd"),
    "ticket_prepare": (
        "818daea9fd790430cfdc3dd1560bc4f5223e6a2478a30d379ef897774682e3f6",
        "a7ddca4d35b552f67c8d5dbfd262c50ef2eaf92f5ccc5e8c2961d385988e465c"),
    "integration_publish": (
        "a0741d54e48a1a356f8a89f9fc46b24fcae82c587b9a8480493b8dba53682189",
        "65944572b854de11e24f09f746472ef1b123185e7029511fce10e7154cc1301a"),
}


def needs_upgrade(intent: dict[str, Any]) -> bool:
    return _REVISION in intent["opened"] or has_retired_argument(intent["arguments"], intent["plan"])


def has_retired_argument(arguments: dict[str, Any], plan: list[dict[str, Any]]) -> bool:
    return _REVISION in arguments or any(_REVISION in (step.get("args") or {}) for step in plan)


def _bind_transitions(intent: dict[str, Any]) -> bool:
    """Recover only a prior proved by the old opening commit or by a step preceding this transition."""
    tool, arguments = intent["tool"], intent["arguments"]
    start = (intent["subject"]["start"] or {}).get("state")
    sources = {
        "ticket_start": "work.assign",
        "ticket_request_verification": "review.ingest",
        "ticket_prepare": "verify.ingest",
    }
    seen: dict[str, int] = {}
    for step in intent["plan"]:
        primitive = step["primitive"]
        if primitive == "work.transition":
            args = step.get("args") or {}
            source = sources.get(tool)
            if source in seen:
                prior: str | dict[str, Any] = {REFERENCE: [seen[source], STEP_STATE]}
            elif ((tool == "ticket_request_review" and start == "RUNNING")
                  or (tool == "ticket_request_verification" and start == "REVIEW_PASSED")
                  or (tool == "ticket_prepare" and start in {"REVIEW_PASSED", "VERIFIED"})):
                prior = start
                if arguments.get("prior_value", prior) != prior:
                    return False
                arguments["prior_value"] = prior
            else:
                return False
            if not args or args.get("prior_value", prior) != prior:
                return False
            args["prior_value"] = prior
        if primitive == "integrate.publish":
            candidate = arguments.get("prepared_candidate")
            if not candidate or (step.get("args") or {}).get("candidate") != candidate:
                return False
        seen[primitive] = step["n"]
    return True


def upgrade(intent: dict[str, Any]) -> bool:
    """Strip the retired input. An unprovable intent retains its old digest and cannot continue."""
    opened, arguments = intent["opened"], intent["arguments"]
    prior = opened.pop(_REVISION, None)
    verified = (type(prior) is int and prior == opened["rev"] - 1 and arguments.get(_REVISION) == prior
                and intent["arguments_digest"] == digest(arguments))
    arguments.pop(_REVISION, None)
    for step in intent["plan"]:
        (step.get("args") or {}).pop(_REVISION, None)
    old, new = _CONTRACTS.get(intent["tool"], (None, None))
    candidate = deepcopy(intent)
    rebound = bool(verified and new and intent["contract_digest"] == old and _bind_transitions(candidate))
    if rebound:
        intent["contract_digest"] = new
        intent["arguments"] = candidate["arguments"]
        intent["plan"] = candidate["plan"]
    intent["arguments_digest"] = digest(intent["arguments"])
    return rebound
