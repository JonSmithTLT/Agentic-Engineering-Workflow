"""Description-only compact catalog variant (ADR-0017 D33). Names, schemas and annotations keep their meaning."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from aew.owners import owner_of, whose

if TYPE_CHECKING:
    from aew.surface.contract import Tool

DESCRIPTIONS = {
    "status": "Project state, decisions and actions, or one unit's record.",
    "resume": "Rebuild context from durable state, first after any restart. Each decision names its owner.",
    "harness_status": "Inspect worker runs and progress; changes nothing.",
    "harness_wait": "Wait for a run to end or need the Lead; one call, no polling.",
    "checkpoint": "Record a bounded handoff note; advances no work.",
    # A deliberate short form of `contract.STEERING_TEXT` (and its `STEERING_STEP`), within the compact budget (E183).
    "steering": "Lower (after a raise) or request a raise; grants nothing. Crawl/walk: you take each step. No "
                "steering.mode: all refused.",
    # "Resolve a decision." said nothing of what it takes (E367; the audit of 2026-11-25, U4).
    "resolve": "Settle what `resume` or a decision lists, with the subject and choice it shows, or assess a plan "
               "(W#plan).",
    "ticket_draft": "Create a Ticket and optionally propose, never accept, its plan.",
    "ticket_start": "Assign a READY mutating Ticket by policy, launch and move to RUNNING.",
    "ticket_request_review": "Move a RUNNING Ticket to REVIEW_PENDING and launch required reviewers.",
    "ticket_request_verification": "Accept review if due, move to VERIFY_PENDING and launch required verifiers.",
    "ticket_prepare": "Accept verification if due and prepare integration; publication is separate.",
    # Whose decision it carries out is the owner table's (register E335), never restated here.
    "integration_publish": f"Publish the prepared candidate; this carries out "
                           f"{whose(owner_of('integrate.publish'), to_lead=True)} publication decision.",
    # The guide's core says it changes no scope or authority (`messaging_guide_lines`).
    "message_send": "Message an active worker's invocation. Deliver at its next step (default), turn end or on "
                    "relaunch.",
    "map": "Codebase map at the head: show (status, section, or scope ticket with work_id) or search (exact path, "
           "then text). Hits are candidates.",
}
# Property descriptions, by tool and property (E367; the audit of 2026-11-25, U3 to U5): where an argument's source or
# form was not said. Each names where the Lead finds the value.
PROPERTIES = {
    ("message_send", "to"): "the run's invocation: R-INV-0003-1 is INV-0003",
    ("resolve", "subject"): "as `resume` or the decision lists it",
    ("resolve", "approval_digest"): "the digest the decision shows",
    ("integration_publish", "prepared_candidate"): "the candidate `status` shows",
}
# A property described only as "free text" is told nothing its name and type do not say.
FREE_TEXT = "free text"
EXECUTION = "policy override (judgment-bearing)"


def _trim(value: Any, execution: str) -> None:
    """Drop the examples and the bare "free text" descriptions, and shorten the execution override's, in place."""
    if isinstance(value, dict):
        if value.get("description") in {"e.g. T-0012", FREE_TEXT}:
            del value["description"]
        elif value.get("description") == execution:
            value["description"] = EXECUTION
        for child in value.values():
            _trim(child, execution)
    elif isinstance(value, list):
        for child in value:
            _trim(child, execution)


def compact(tool: Tool) -> Tool:
    from aew.surface.contract import EXECUTION as FULL_EXECUTION

    schema = copy.deepcopy(tool.input_schema)
    _trim(schema, FULL_EXECUTION["description"])
    for (name, prop), text in PROPERTIES.items():
        if name == tool.name and prop in schema.get("properties", {}):
            schema["properties"][prop]["description"] = text
    return tool._replace(description=DESCRIPTIONS.get(tool.name, tool.description), input_schema=schema)
