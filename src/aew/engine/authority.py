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


# The credential kind of a read-only dashboard browser session (ADR-0005, amendment of 2026-10-05 for F20.3). It never
# enters control state: the dashboard server keeps its records in its own table and verifies them with `lookup`.
OPERATOR_SESSION = "operator_session"


def mint(tokens: dict[str, Any], kind: str, scope: dict[str, Any], *, generation: int,
         expires_at: str | None = None) -> str:
    """Create a credential in ``tokens`` (a token table of the control state's shape), store only its verifier, and
    return the secret string once. ``issue_token`` mints into control state; the dashboard mints into its own table."""
    token_id = "tk_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    tokens[token_id] = {
        "kind": kind,
        "verifier": sha256_text(secret),
        "scope": scope,
        "issued_at": utc_now(),
        "issued_by_generation": generation,
        "expires_at": expires_at,
        "revoked_at": None,
        "revoke_reason": None,
    }
    return f"aew1.{token_id}.{secret}"


def issue_token(state: dict[str, Any], kind: str, scope: dict[str, Any]) -> str:
    """Create a credential, store only its verifier, and return the secret string once."""
    return mint(state["tokens"], kind, scope, generation=state["lead"]["generation"])


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


def lookup(tokens: dict[str, Any], token: str, *, archived: Callable[[str], dict[str, Any] | None] | None = None,
           now: str | None = None) -> tuple[str, dict[str, Any]]:
    """Verify a presented credential against a token table: the form, the verifier in constant time, the expiry.

    The table is control state's (``_lookup``) or the dashboard server's own (ADR-0005, 2026-10-05). ``archived``
    finds a credential that left the table with finished work; ``now`` is the clock the expiry is judged by (the
    current time when omitted). Revocation is the caller's check: what a revoked record means depends on its kind."""
    match = TOKEN_RE.match(token or "")
    if not match:
        raise PermissionDenied("malformed credential")
    token_id, secret = match.groups()
    record = tokens.get(token_id)
    if record is None and archived is not None:
        old = archived(token_id)
        if old is not None and hmac.compare_digest(old["verifier"], sha256_text(secret)):
            # Finished work keeps its credentials only in its archive: still revoked authority, never an unknown one.
            raise StaleAuthority(f"this credential belongs to finished work and was revoked: "
                                 f"{old.get('revoke_reason') or 'its work unit is archived'}",
                                 token_id=token_id, revoke_reason=old.get("revoke_reason"), archived=True)
    if record is None or not hmac.compare_digest(record["verifier"], sha256_text(secret)):
        raise PermissionDenied("unknown or invalid credential")
    if record.get("expires_at") and record["expires_at"] <= (now or utc_now()):
        raise StaleAuthority("credential expired", token_id=token_id)
    return token_id, record


def _lookup(state: dict[str, Any], token: str,
            archived: ArchivedCredential | None = None) -> tuple[str, dict[str, Any]]:
    find = (lambda token_id: archived(state, token_id)) if archived is not None else None
    return lookup(state["tokens"], token, archived=find)


def revoke(state: dict[str, Any], token_id: str | None, reason: str) -> None:
    if not token_id:
        return
    record = state["tokens"].get(token_id)
    if record and record["revoked_at"] is None:
        record["revoked_at"] = utc_now()
        record["revoke_reason"] = reason


_SUPERSEDED = "Lead authority superseded; this credential can no longer change control state"
_VACANT = "no Lead holds authority"


def require_lead(state: dict[str, Any], token: str, *, allow_pending: bool = False,
                 archived: ArchivedCredential | None = None) -> dict[str, Any]:
    """Return the actor record for a valid *current* Lead credential."""
    token_id, record = _lookup(state, token, archived)
    if record["kind"] != "lead":
        raise PermissionDenied("this operation requires the Lead credential", presented=record["kind"])
    lead = state["lead"]
    if record["revoked_at"] is not None or token_id != lead.get("token_id"):
        raise StaleAuthority(
            _SUPERSEDED,
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
        raise StaleAuthority(_VACANT)
    return {"kind": "lead", "session_label": lead.get("session_label"), "generation": lead["generation"],
            "token_id": token_id}


def require_held_lead(state: dict[str, Any], token: str) -> dict[str, Any]:
    """``require_lead`` for a holder checking its own credential, from the hot control state alone. A credential that
    has left the token table has lost the seat: the current Lead's credential is always in the table (``require_lead``
    reads it there), and an ended one leaves it only for its archive (ADR-0011 R7), which could add only its reason.
    So a holder that polls (the Lead broker's watchdog) never waits on the derived history index, whose SQLite busy
    wait no poll's bound counts (CI on PR #281). A credential presented to the engine is still verified by
    ``require_lead``, where an archived one is stale authority and an unknown one is refused as unknown."""
    token_id = token_id_of(token)
    if token_id not in state["tokens"]:
        lead = state["lead"]
        raise StaleAuthority(_VACANT if lead["status"] == "vacant" else _SUPERSEDED, token_id=token_id,
                             current_generation=lead["generation"])
    return require_lead(state, token)  # the credential is in the table: no archive is read


def require_invocation(
    state: dict[str, Any], token: str, operation: str | None, *, work_unit: str | None = None,
    archived: ArchivedCredential | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Validate an invocation credential for ``operation``; return (invocation_id, invocation, actor).

    ``operation=None`` checks identity only: a live credential of an active invocation under the current Lead
    generation. Custody (a supervisor taking its run's credential) and ``whoami`` need nothing more, so a role
    card that narrows the invocation's operations can never make them fail (area 2 review, F7)."""
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
    if operation is None:
        pass
    elif operation not in ROLE_OPERATIONS.get(role, frozenset()):
        raise PermissionDenied(f"role {role} may not perform {operation}", role=role, operation=operation)
    narrowed = invocation.get("allowed_operations")
    if operation is not None and narrowed is not None and operation not in narrowed:
        card = (invocation.get("card") or {}).get("id")
        raise PermissionDenied(f"role card {card} narrows this invocation; {operation} is not permitted",
                               card=card, operation=operation)
    if work_unit is not None and scope["work_unit"] != work_unit:
        raise PermissionDenied("credential is scoped to a different work unit",
                               scoped_to=scope["work_unit"], requested=work_unit)
    actor = {"kind": "invocation", "invocation": invocation_id, "role": role, "work_unit": scope["work_unit"]}
    return invocation_id, invocation, actor


# ---------------------------------------------------------------------------------------------- the custody credential
# M4-E E6a (plan v3 §2.3, S1; ADR-0004 amendment 2026-10-10): the integration custodian holds no Lead, role, model or
# harness credential. It holds one engine-issued custody credential, restricted to the closed integration-custody
# transaction family below. Minted in the commit that grants the lease (only its verifier is stored), handed to the
# custody worker over a pipe, and revoked when the lease ends, its custodian dies, the generation changes or the lease
# is reconciled (``queue_ops``). Same-uid, it is a protocol guard (``guarantee: dev``), like every credential here.

CUSTODY = "custody"
# The closed family (§2.3): the validation pin and commit and their infrastructure outcomes, routing a result (never
# accepting a report), the custodian's own lease release, the worker's registration (S2), and the PIC publish, which
# also needs the operator's envelope and the §17 predicate in the same transaction (E6b: until then it is refused).
CUSTODY_OPS = ("custody.register", "integrate.validate", "integrate.validated", "integrate.validation_abandoned",
               "integrate.validation_unavailable", "integrate.validation_released", "integrate.route",
               "integrate.release", "integrate.publishing")
CUSTODY_PUBLISH = "integrate.publishing"


def mint_custody(state: dict[str, Any], *, custodian: str, entry: str, attempt: int, lease_at: str) -> str:
    """The custody credential of a lease just granted, bound to its custodian, queue entry, queue attempt, lease and
    Lead generation, and to the closed operation family. Returned once; control state keeps its verifier."""
    generation = state["lead"]["generation"]
    # `invocation_id` is the custodian's too: archival bundles the credential with its unit, as every credential
    # issued to one of the unit's invocations (ADR-0011 R7).
    return mint(state["tokens"], CUSTODY, {"custodian": custodian, "invocation_id": custodian, "entry": entry,
                                           "attempt": attempt, "lease": lease_at, "generation": generation,
                                           "ops": list(CUSTODY_OPS)},
                generation=generation)


def require_custodian(state: dict[str, Any], credential: str, op: str) -> dict[str, Any]:
    """The actor of a custody transaction ``op`` presented with ``credential``, or a refusal. Every binding is checked
    independently on this state (§2.3: on every commit): the credential is a live custody credential; its custodian is
    the active ``integration_attempt`` invocation of the current Lead generation that holds the lease, unmarked for
    reconciliation, of the same entry, grant and attempt; and ``op`` is in the closed family the credential carries.
    A Lead, invocation or handoff credential is refused here, and a custody credential everywhere else."""
    token_id, record = _lookup(state, credential)
    if record["kind"] != CUSTODY:
        raise PermissionDenied("a custody transaction needs the custodian's custody credential",
                               presented=record["kind"])
    scope = record["scope"]
    if record["revoked_at"] is not None:
        raise StaleAuthority(f"the custody credential of {scope.get('custodian')} was revoked: "
                             f"{record.get('revoke_reason')}", revoke_reason=record.get("revoke_reason"))
    if op not in CUSTODY_OPS or op not in (scope.get("ops") or []):
        raise PermissionDenied(f"{op} is outside the integration-custody family: a custody credential commits only "
                               "validation, routing, its own lease release and registration", op=op)
    generation = state["lead"]["generation"]
    if scope.get("generation") != generation:
        raise StaleAuthority("the custody credential was issued under a superseded Lead generation",
                             token_generation=scope.get("generation"), current_generation=generation)
    custodian = scope.get("custodian")
    inv = state["invocations"].get(custodian or "") or {}
    if inv.get("kind") != "integration_attempt" or inv.get("status") != "active" or inv.get("generation") != generation:
        raise StaleAuthority(f"custodian {custodian} is {inv.get('status') or 'unknown'}: its custody ended",
                             custodian=custodian)
    lease = (state.get("queue") or {}).get("lease") or {}
    held = ((state.get("queue") or {}).get("entries") or {}).get(lease.get("entry") or "") or {}
    attempts = held.get("attempts") or []
    if (lease.get("custodian") != custodian or lease.get("entry") != scope.get("entry")
            or lease.get("granted_at") != scope.get("lease") or lease.get("generation") != generation
            or (lease.get("custody") or {}).get("token_id") != token_id or len(attempts) != scope.get("attempt")
            or attempts[-1].get("custodian") != custodian):
        raise StaleAuthority(f"custodian {custodian} no longer holds the lease it was granted", custodian=custodian)
    if lease.get("reconcile") is not None:
        raise StaleAuthority(f"{custodian}'s lease is marked for reconciliation ({lease['reconcile']['reason']})",
                             custodian=custodian)
    return {"kind": "custodian", "invocation": custodian, "work_unit": inv.get("work_unit"),
            "lease": {"entry": lease["entry"], "granted_at": lease["granted_at"]}, "generation": generation,
            "requested_by": (lease.get("custody") or {}).get("requested_by"), "token_id": token_id}


def verify_offer(state: dict[str, Any], offer: str) -> str:
    token_id, record = _lookup(state, offer)
    handoff = state["lead"].get("handoff") or {}
    if record["kind"] != "handoff_offer" or token_id != handoff.get("offer_token_id"):
        raise PermissionDenied("not the pending handoff offer")
    if record["revoked_at"] is not None or state["lead"]["status"] != "handoff_pending":
        raise StaleAuthority("handoff offer is no longer valid")
    return token_id
