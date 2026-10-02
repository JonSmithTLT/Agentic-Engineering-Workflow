"""Lead authority, credentials and role permissions (WC §5, §6; KC §7.2, §16).

Credentials are ``aew1.<token_id>.<secret>`` strings. The secret is 256-bit
random and exists only in the harness/session that received it. Durable control
state holds a *verifier* (sha256 of the secret) plus scope, issuance, expiry and
revocation metadata, so any separate process can verify a presented token
without the secret ever being written to disk.

Tokens are a protocol guard against accidental cross-role writes and stale
writers. All roles run as the same OS user, so they are not an OS security
boundary; a same-UID agent that deliberately subverts the process is outside the
M1 threat model.
"""

from __future__ import annotations

import hmac
import re
import secrets
from collections.abc import Callable
from typing import Any

from aew.errors import PermissionDenied, StaleAuthority
from aew.util import sha256_text, utc_now

TOKEN_RE = re.compile(r"^aew1\.(tk_[0-9a-f]{16})\.([A-Za-z0-9_-]{40,})$")

# Operations an invocation token may perform, by role. Everything that mutates
# control state requires the Lead token instead.
# This table is the enforcement of archetype authority (ADR-0006); archetype YAML documents it
# and tests/unit/test_roles.py keeps the two equal. Role cards can only narrow it.
ROLE_OPERATIONS: dict[str, frozenset[str]] = {
    "implementer": frozenset({"check.run", "submit.implementation_report", "context.read"}),
    "reviewer": frozenset({"submit.review", "context.read"}),
    "verifier": frozenset({"check.run", "submit.verification", "context.read"}),
    # Non-mutating executors (ADR-0008): each submits exactly its own record kind; the investigator may
    # also gather runtime evidence by running project checks in its read-only observation workspace.
    "planner": frozenset({"submit.plan_proposal", "context.read"}),
    "investigator": frozenset({"check.run", "submit.discovery_record", "context.read"}),
    "researcher": frozenset({"submit.research_record", "context.read"}),
}


def issue_token(state: dict[str, Any], kind: str, scope: dict[str, Any]) -> str:
    """Create a credential, store only its verifier, and return the secret string once."""
    token_id = "tk_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    state["tokens"][token_id] = {
        "kind": kind,
        "verifier": sha256_text(secret),
        "scope": scope,
        "issued_at": utc_now(),
        "issued_by_generation": state["lead"]["generation"],
        "expires_at": None,
        "revoked_at": None,
        "revoke_reason": None,
    }
    return f"aew1.{token_id}.{secret}"


def rotate_invocation_token(state: dict[str, Any], inv_id: str, reason: str) -> str:
    """Re-issue an active invocation's credential with the same scope and revoke the old one (ADR-0009).

    Re-issuance, not new authority: the scope (invocation, role, work unit, generation) is copied. Every
    process still holding the old credential loses its authority in the same commit.
    """
    inv = state["invocations"][inv_id]
    old = inv["token_id"]
    scope = dict(state["tokens"][old]["scope"])
    token = issue_token(state, "invocation", scope)
    revoke(state, old, reason)
    inv["token_id"] = token.split(".")[1]
    return token


def token_id_of(token: str) -> str:
    match = TOKEN_RE.match(token or "")
    if not match:
        raise PermissionDenied("malformed credential")
    return match.group(1)


# Looks up a credential that was archived with finished work (ADR-0011, plan R7); None if it never was.
ArchivedCredential = Callable[[dict[str, Any], str], "dict[str, Any] | None"]


def _lookup(state: dict[str, Any], token: str,
            archived: ArchivedCredential | None = None) -> tuple[str, dict[str, Any]]:
    match = TOKEN_RE.match(token or "")
    if not match:
        raise PermissionDenied("malformed credential")
    token_id, secret = match.groups()
    record = state["tokens"].get(token_id)
    if record is None and archived is not None:
        old = archived(state, token_id)
        if old is not None and hmac.compare_digest(old["verifier"], sha256_text(secret)):
            # Finished work keeps its credentials only in its archive: still revoked authority, never an unknown one.
            raise StaleAuthority(f"this credential belongs to finished work and was revoked: "
                                 f"{old.get('revoke_reason') or 'its work unit is archived'}",
                                 token_id=token_id, revoke_reason=old.get("revoke_reason"), archived=True)
    if record is None or not hmac.compare_digest(record["verifier"], sha256_text(secret)):
        raise PermissionDenied("unknown or invalid credential")
    if record.get("expires_at") and record["expires_at"] <= utc_now():
        raise StaleAuthority("credential expired", token_id=token_id)
    return token_id, record


def revoke(state: dict[str, Any], token_id: str | None, reason: str) -> None:
    if not token_id:
        return
    record = state["tokens"].get(token_id)
    if record and record["revoked_at"] is None:
        record["revoked_at"] = utc_now()
        record["revoke_reason"] = reason


def require_lead(state: dict[str, Any], token: str, *, allow_pending: bool = False,
                 archived: ArchivedCredential | None = None) -> dict[str, Any]:
    """Return the actor record for a valid *current* Lead credential."""
    token_id, record = _lookup(state, token, archived)
    if record["kind"] != "lead":
        raise PermissionDenied("this operation requires the Lead credential", presented=record["kind"])
    lead = state["lead"]
    if record["revoked_at"] is not None or token_id != lead.get("token_id"):
        raise StaleAuthority(
            "Lead authority superseded; this credential can no longer change control state",
            token_generation=record["scope"].get("generation"),
            current_generation=lead["generation"],
            revoke_reason=record.get("revoke_reason"),
        )
    if record["scope"].get("generation") != lead["generation"]:
        raise StaleAuthority(
            "stale Lead authority generation",
            token_generation=record["scope"].get("generation"),
            current_generation=lead["generation"],
        )
    if lead["status"] == "handoff_pending" and not allow_pending:
        raise PermissionDenied("a Lead handoff is pending; only `aew lead handoff cancel` is allowed")
    if lead["status"] == "vacant":
        raise StaleAuthority("no Lead holds authority")
    return {"kind": "lead", "session_label": lead.get("session_label"), "generation": lead["generation"],
            "token_id": token_id}


def require_invocation(
    state: dict[str, Any], token: str, operation: str, *, work_unit: str | None = None,
    archived: ArchivedCredential | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Validate an invocation credential for ``operation``; return (invocation_id, invocation, actor)."""
    token_id, record = _lookup(state, token, archived)
    if record["kind"] != "invocation":
        raise PermissionDenied(
            "this operation requires an invocation credential issued to a bounded role",
            presented=record["kind"],
        )
    scope = record["scope"]
    invocation_id = scope["invocation_id"]
    invocation = state["invocations"].get(invocation_id)
    if invocation is not None and record["revoked_at"] is not None and invocation["token_id"] != token_id:
        # A rotated credential (a later harness run of the same invocation holds a new one) is stale
        # authority, reported as such rather than as an unknown credential (ADR-0009).
        raise StaleAuthority(f"this credential for invocation {invocation_id} was revoked: "
                             f"{record.get('revoke_reason')}", revoke_reason=record.get("revoke_reason"))
    if invocation is None or invocation["token_id"] != token_id:
        raise PermissionDenied("credential does not match a known invocation")
    if record["revoked_at"] is not None or invocation["status"] != "active":
        raise StaleAuthority(
            f"invocation {invocation_id} is {invocation['status']}; its credential is no longer valid",
            revoke_reason=record.get("revoke_reason"),
        )
    if scope.get("generation") != state["lead"]["generation"]:
        raise StaleAuthority("invocation was issued under a superseded Lead generation")
    role = scope["role"]
    if operation not in ROLE_OPERATIONS.get(role, frozenset()):
        raise PermissionDenied(f"role {role} may not perform {operation}", role=role, operation=operation)
    narrowed = invocation.get("allowed_operations")
    if narrowed is not None and operation not in narrowed:
        card = (invocation.get("card") or {}).get("id")
        raise PermissionDenied(f"role card {card} narrows this invocation; {operation} is not permitted",
                               card=card, operation=operation)
    if work_unit is not None and scope["work_unit"] != work_unit:
        raise PermissionDenied("credential is scoped to a different work unit",
                               scoped_to=scope["work_unit"], requested=work_unit)
    actor = {"kind": "invocation", "invocation": invocation_id, "role": role, "work_unit": scope["work_unit"]}
    return invocation_id, invocation, actor


def verify_offer(state: dict[str, Any], offer: str) -> str:
    token_id, record = _lookup(state, offer)
    handoff = state["lead"].get("handoff") or {}
    if record["kind"] != "handoff_offer" or token_id != handoff.get("offer_token_id"):
        raise PermissionDenied("not the pending handoff offer")
    if record["revoked_at"] is not None or state["lead"]["status"] != "handoff_pending":
        raise StaleAuthority("handoff offer is no longer valid")
    return token_id
