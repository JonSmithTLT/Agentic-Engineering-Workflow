"""Whose judgment a primitive carries out: the one table of primitive owners (register E335; the designer's ruling of
2026-11-11 on E334 and E335, part 2). The action projection reads each decision kind's one owner from it, and text
that says whose decision something is derives it from here. A primitive it does not list is the operator's: the Lead
is given an owner only by an entry here, never by default. An owner is a statement, not a grant: every command keeps
its own authority checks (the review of #597).

This module imports no engine code: the Lead's MCP transport, which the `aew lead mcp` process builds without the
engine (``tests/unit/test_surface_mcp.py``), reads it through the typed catalog's text, and so does the engine."""

from __future__ import annotations

LEAD = "lead"
OPERATOR = "operator"
OWNERS = (LEAD, OPERATOR)
PRIMITIVE_OWNERS: dict[str, str] = {
    # The acceptances that are the Lead's by design (E335's Work): a review report, and a Ticket's own verification.
    "review.ingest": LEAD,
    "verify.ingest": LEAD,
    # A disposition of a finding, claim or anomaly: M4-E plan v3 §2.4, "Who disposes: the Lead".
    "work.dispose": LEAD,
    # An unfinished stage's resolution: plan v3 E3, a replacement Lead continues or abandons it.
    "stage.resolve": LEAD,
    # Finishing a publication whose intent is already committed (E137): MECHANICAL, the publish decision made before it.
    "integrate.reconcile": LEAD,
}


def owner_of(primitive_id: str) -> str:
    """The owner of a primitive's judgment: its entry in ``PRIMITIVE_OWNERS``, else the operator."""
    return PRIMITIVE_OWNERS.get(primitive_id, OPERATOR)


def whose(owner: str | None, *, to_lead: bool = False) -> str:
    """An owner as text says it ("the Lead's", "the operator's"; "your" in text addressed to the Lead about its own),
    so wording about whose decision something is derives from the owner, never restates it. No owner, or one this
    table does not name, reads as the operator's."""
    if owner == LEAD:
        return "your" if to_lead else "the Lead's"
    return "the operator's"
