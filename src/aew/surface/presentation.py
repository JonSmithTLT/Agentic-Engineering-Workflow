"""Description-only compact catalog variant (ADR-0017 D33). Names, schemas and annotations keep their meaning."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aew.surface.contract import Tool

DESCRIPTIONS = {
    "status": "Project state, decisions and actions, or one unit's record.",
    "resume": "Rebuild context from durable state; call it first after a restart. Decisions stay yours.",
    "work_show": "Inspect a work unit and its evidence.",
    "explain": "Explain legality, dispatch or stage availability; changes nothing.",
    "harness_status": "Inspect worker runs and progress; changes nothing.",
    "harness_wait": "Wait for a run to end or need the Lead; one call, no polling.",
    "checkpoint": "Record a bounded handoff note; advances no work.",
    "steering": "Lower steering or request a raise or confirmation; requests grant nothing.",
    "resolve": "Continue or abandon a stage; dispose a finding, claim or anomaly; replace a stuck gate.",
    "ticket_draft": "Create a Ticket and optionally propose, never accept, its plan.",
    "ticket_start": "Assign a READY mutating Ticket by policy, launch and move to RUNNING.",
    "ticket_request_review": "Move a RUNNING Ticket to REVIEW_PENDING and launch required reviewers.",
    "ticket_request_verification": "Accept review if due, move to VERIFY_PENDING and launch required verifiers.",
    "ticket_prepare": "Accept verification if due and prepare integration; publication is separate.",
    "integration_publish": "Publish the prepared candidate; this call is your publication decision.",
}


def _remove_examples(value: Any) -> None:
    if isinstance(value, dict):
        if value.get("description") == "e.g. T-0012":
            del value["description"]
        for child in value.values():
            _remove_examples(child)
    elif isinstance(value, list):
        for child in value:
            _remove_examples(child)


def compact(tool: Tool) -> Tool:
    schema = copy.deepcopy(tool.input_schema)
    _remove_examples(schema)
    return tool._replace(description=DESCRIPTIONS.get(tool.name, tool.description), input_schema=schema)
