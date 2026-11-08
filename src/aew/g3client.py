"""The G3 client: asks the operator to approve a protected command set, then submits the approved set (A-37 G3-02,
G3-07; STG-03, G3-D; the Lead's rulings of 2026-10-25).

    1. the set, a complete O-01 0.2 CommandSet, is checked: every member a protected action, no member with an
       ``origin_proof_ref`` and no ``consent_set_ref`` yet (the client makes both), and nothing else wrong with it;
    2. each member gets a fresh proof from a cryptographically secure source (G3-02), and the set its O-01 schema check;
    3. ``POST /g3/v1/approval-requests`` on ``request.sock``: the operator approves or declines in the confirmer;
    4. ``GET /g3/v1/approval-requests/{approval_ref}`` until a decision, no longer than the approval lives;
    5. the record's ``set_digest`` is checked against the SW-02 digest of the set to be submitted (the G3-07
       invariant), and only then is the set submitted unchanged, with ``consent_set_ref`` set, to the O-01 route.

It also holds an owner's call on the same socket, :func:`consume` (G3-08), and the probe that consumes nothing.

It never asks for, receives or stores the PIN (G3-05). The bearer token for the O-01 route is read from a file, sent
in one header, and never printed, logged or put in an error. The G3 service and the O-01 route are both on this host:
``request.sock`` is a Unix filesystem socket, and the route must be on the loopback address.

What this module restates, held to its owners by ``tests/unit/test_g3client.py`` (``aew_g3`` is installed apart from
``aew``, so it is not imported here): the request socket's path (``aew_g3.cli``, ``aew_g3.REQUEST_SOCK``), the G3
wire's header, version and ``ConsumeResult`` values (``g3-wire.schema.json``), the service's request timeout
(``aew_g3.server``) and the approval expiry's ceiling (``aew_g3.deployment.TRIPWIRES``).
"""

from __future__ import annotations

import copy
import http.client
import json
import secrets
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aew.errors import (
    NotFound,
    OperatorAuthorizationRequired,
    PermissionDenied,
    Unavailable,
    UsageError,
    ValidationFailed,
)
from aew.stg02 import adopted as A
from aew.stg02 import wire as W

REQUEST_SOCK = "/run/aew-g3/request.sock"
G3_HEADER, G3_WIRE = "X-AEW-G3-Wire", "g3-0.6.1-candidate"
TIMEOUT_S = 30  # the service's own request timeout
EXPIRY_CEILING_S = 10 * 60  # G3-02: an approval lives at most 10 minutes (a tripwire the deployment may only shorten)
GRACE_S = 5  # past expires_at, the service answers EXPIRED; the wait ends here at the latest
POLL_S = 1.0
PROOF_BYTES = 16  # "proof:" and 32 lowercase hex characters, the wire's shortest (G3-02)
PROTECTED = "PROTECTED_G3"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
COMMAND_SETS = "/o01/v0/command-sets"

# G3-08's ConsumeResults: what a service that answered says of the member, held to the wire by a test
CONSUME_RESULTS = ("CONSUMED", "ORIGIN_NOT_ESTABLISHED", "CONSENT_ISSUER_UNVERIFIED", "CONSENT_EXPIRED",
                   "CONSENT_SCOPE_MISMATCH", "CONSENT_ALREADY_USED")
PROBE_TIMEOUT_S = 5  # the probe's one read: it asks for an approval no one made, which the service answers at once
PROBE_REF = "g3:approval:probe"  # a well-formed ref (the wire's Ref) that names no approval: the answer is a 404


# ------------------------------------------------------------------------------------------------ the set
def check_set(cset: Any) -> dict[str, Any]:
    """Step 1: the set as the operator gave it, refused whole and fail-closed when any member is not protected, when a
    member already carries a proof, or when the set already carries a ``consent_set_ref``. Each refusal names what
    was wrong and what to do instead."""
    if not isinstance(cset, dict) or not isinstance(cset.get("intents"), list) or not cset["intents"]:
        raise ValidationFailed("the file is not an O-01 CommandSet: an object with a non-empty `intents` list",
                               reason="not_a_command_set")
    registry = A.registry()
    actions = [str(i.get("action")) if isinstance(i, dict) else "(a member that is not an object)"
               for i in cset["intents"]]
    other = sorted({a for a in actions if registry.get(a, {}).get("origin") != PROTECTED})
    if other:
        raise ValidationFailed(f"every member must be a protected action (origin {PROTECTED}); these are not: "
                               f"{', '.join(other)}. Submit them apart from the protected set: they need no G3 "
                               "approval", reason="member_not_protected", actions=other)
    proved = [str(i.get("intent_ref")) for i in cset["intents"] if i.get("origin_proof_ref") is not None]  # all dicts
    if proved:
        raise ValidationFailed("a member already carries an origin_proof_ref: the client makes every proof itself, "
                               "fresh for each request (G3-02). Set origin_proof_ref to null for: "
                               + ", ".join(proved), reason="origin_proof_ref_set", intents=proved)
    if cset.get("consent_set_ref") is not None:
        raise ValidationFailed("the set already carries a consent_set_ref: it is the approval's, set only after the "
                               "operator approves (G3-07). Set consent_set_ref to null", reason="consent_set_ref_set")
    return cset


def with_proofs(cset: dict[str, Any], token: Callable[[int], str] = secrets.token_hex) -> dict[str, Any]:
    """Step 2: a copy of the set with a fresh proof for each member, from a cryptographically secure source, and
    ``consent_set_ref`` null; refused when the result is not a valid O-01 CommandSet."""
    out = copy.deepcopy(cset)
    out["consent_set_ref"] = None
    for i in out["intents"]:
        i["origin_proof_ref"] = "proof:" + token(PROOF_BYTES)
    errors = A.o01_errors("CommandSet", out)
    if errors:
        raise ValidationFailed("the set is not a valid O-01 0.2 CommandSet: " + "; ".join(errors[:5]),
                               reason="command_set_schema", errors=errors)
    return out


def approved_set(cset: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Step 5's set: unchanged, with the record's ``consent_set_ref``; refused, and never submitted, when the record's
    ``set_digest`` is not the SW-02 digest of that set (G3-07)."""
    out = copy.deepcopy(cset)
    out["consent_set_ref"] = record.get("consent_set_ref")
    if record.get("set_digest") != W.set_digest(out):
        raise ValidationFailed("the consent record's set_digest is not the digest of the set to be submitted, so "
                               "nothing was submitted (G3-07). Request the approval again",
                               reason="set_digest_mismatch")
    return out


# ------------------------------------------------------------------------------------------------ the G3 service
class _UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = TIMEOUT_S) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        if sys.platform == "win32":  # G3 is a Linux profile: its sockets are Unix filesystem sockets
            raise OSError("the G3 service runs on Linux only")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._path)
        self.sock = s


def _g3(sock_path: str | None, method: str, path: str, body: Any = None, *,
        timeout: float = TIMEOUT_S) -> tuple[int, Any]:
    """One request on ``request.sock`` (``REQUEST_SOCK``, read at call time, unless a path is given), each socket
    operation bounded by ``timeout``."""
    sock_path = sock_path or REQUEST_SOCK
    conn = _UnixHTTP(sock_path, timeout)
    try:
        data = None if body is None else json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        reply = conn.getresponse()
        raw = reply.read()
        if reply.getheader(G3_HEADER) != G3_WIRE:
            raise Unavailable(f"the answer on {sock_path} is not the G3 wire's ({G3_WIRE})", reason="g3_not_g3")
        try:
            return reply.status, (json.loads(raw.decode("utf-8")) if raw else None)
        except (ValueError, RecursionError) as e:  # RecursionError: a body nested past the parser's limit
            raise Unavailable(f"the answer on {sock_path} cannot be read ({type(e).__name__}): it is not the G3 "
                              "service's. Its journal: journalctl -u aew-g3.service", reason="g3_not_g3") from None
    except PermissionError:
        raise PermissionDenied(f"{sock_path} is not this account's: the G3 service answers only the operator's own "
                               "account, outside any sandbox", reason="g3_peer_not_permitted") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise Unavailable(f"the G3 service did not answer on {sock_path} ({type(e).__name__}). Its state: systemctl "
                          "status aew-g3.service", reason="g3_unreachable") from None
    finally:
        conn.close()


def _g3_refusal(status: int, body: Any) -> Exception:
    code = body.get("code") if isinstance(body, dict) else None
    if code == "PEER_NOT_PERMITTED":
        return PermissionDenied("the G3 service answers only the operator's own account, outside any sandbox",
                                reason="g3_peer_not_permitted")
    if code == "G3_UNAVAILABLE" or status == 503:
        return Unavailable("the G3 service is holding every request; its journal names the cause: journalctl -u "
                           "aew-g3.service", reason="g3_unavailable")
    return ValidationFailed(f"the G3 service refused the request: {code or status}", reason="g3_refused",
                            g3_code=code, status=status)


def request_approval(cset: dict[str, Any], sock_path: str | None = None) -> dict[str, Any]:
    """Step 3: the ``PendingApproval``, once the service has accepted the set."""
    status, body = _g3(sock_path, "POST", "/g3/v1/approval-requests", {"wire_version": G3_WIRE, "command_set": cset})
    if status != 201 or not isinstance(body, dict) or not isinstance(body.get("approval_ref"), str):
        raise _g3_refusal(status, body)
    return body


def expires_at(pending: dict[str, Any]) -> datetime:
    """The pending approval's ``expires_at``; an answer without a readable one, or with a time that names no UTC
    offset, is not G3's (#286 quick check, QC2)."""
    try:
        when = W.parse_time(pending["expires_at"])
    except (KeyError, AttributeError, TypeError, ValueError):  # absent, not a string, or no time
        raise Unavailable("the G3 service's answer names no expires_at", reason="g3_not_g3") from None
    if when.tzinfo is None:
        raise Unavailable("the G3 service's answer names an expires_at with no UTC offset", reason="g3_not_g3")
    return when


def await_decision(pending: dict[str, Any], sock_path: str | None = None, *,
                   now: Callable[[], datetime] = lambda: datetime.now(UTC),
                   clock: Callable[[], float] = time.monotonic,
                   sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Step 4: the ``ConsentRecord`` once the operator approves. A decline, an expiry, or an approval lost to a restart
    of the service refuses; the wait ends with the approval's own life, ``expires_at`` and a grace, and never later
    than G3-02's ceiling. The life left is read once from ``now`` (the service's clock); the wait is measured on
    ``clock``, which no clock step moves, and each read of the service's answer is bounded by the time left: an
    answer sent in pieces can hold the wait longer, by its own length (#286 review F2; its quick check, QC1)."""
    ref = pending["approval_ref"]
    life = (expires_at(pending) - now()).total_seconds()
    deadline = clock() + min(life, EXPIRY_CEILING_S) + GRACE_S
    while True:
        left = deadline - clock()
        if left <= 0:
            raise OperatorAuthorizationRequired("the approval was still undecided past its expiry; nothing was "
                                                "submitted. Request it again", reason="expired", approval_ref=ref)
        status, body = _g3(sock_path, "GET", "/g3/v1/approval-requests/" + ref, timeout=min(TIMEOUT_S, left))
        if status == 404:
            raise OperatorAuthorizationRequired(
                "the approval is no longer known to the G3 service: it restarted, and a pending approval does not "
                "survive a restart. Nothing was approved; request it again", reason="approval_lost",
                approval_ref=ref)
        if status != 200 or not isinstance(body, dict):
            raise _g3_refusal(status, body)
        state = body.get("state")
        if state == "APPROVED" and isinstance(body.get("consent_record"), dict):
            return body["consent_record"]
        if state == "DECLINED":
            raise OperatorAuthorizationRequired("the operator declined the approval in the confirmer; nothing was "
                                                "submitted", reason="declined", approval_ref=ref)
        if state == "EXPIRED":
            raise OperatorAuthorizationRequired("the approval expired before the operator decided; nothing was "
                                                "submitted. Request it again", reason="expired", approval_ref=ref)
        sleep(max(0.0, min(POLL_S, deadline - clock())))


# ------------------------------------------------------------------------------------------------ the O-01 route
def o01_target(url: str) -> tuple[str, int]:
    """The route's host and port: an http URL on the loopback address, with no user, path, query or fragment."""
    u = urlsplit(url)
    if u.scheme != "http" or u.hostname not in LOOPBACK or u.username or u.password or u.path not in ("", "/") \
            or u.query or u.fragment:
        raise UsageError(f"--o01 must be the O-01 route's http://127.0.0.1:<port>, on this host; got {url!r}",
                         reason="o01_not_loopback")
    try:
        port = u.port
    except ValueError:
        port = None
    if not port:  # none, empty or 0: never a default the operator did not name (#286 review F5)
        raise UsageError(f"--o01 must name the O-01 route's port, http://127.0.0.1:<port>; got {url!r}",
                         reason="o01_not_loopback")
    return u.hostname or "127.0.0.1", port


def read_token(path: str) -> str:
    """The bearer token: the file's one line. The token itself is never in a message."""
    p = Path(path)
    try:
        token = p.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise NotFound(f"no token file at {p}", reason="token_file_missing") from None
    except (OSError, UnicodeDecodeError):
        raise UsageError(f"the token file at {p} cannot be read as text", reason="token_file_unreadable") from None
    if not token or any(c.isspace() for c in token):
        raise UsageError(f"the token file at {p} must hold one token on one line", reason="token_file_malformed")
    return token


# A set under a client_request_key that has a receipt is that receipt or a conflict, and `aew g3 request` makes new
# proofs each time, so a new request of the set needs a new key (CS-08: "a new key and ... a new consent").
_NEW_KEY = "with a new client_request_key in the set file"
_UNUSED = f"the approval is unused: request it again {_NEW_KEY}"
# The route consumes a protected member as it admits it, so one that gave no receipt may have used it.
_MAY_BE_USED = ("the approval may have been used: GET /v1/read/owner-operations shows whether it was admitted, and if "
                f"it was not, request it again {_NEW_KEY}")


def submit(cset: dict[str, Any], url: str, token: str) -> dict[str, Any]:
    """Step 5: ``POST /o01/v0/command-sets``, and its receipt (202). Every answer's text is built here, so the token
    reaches the request's one header and nothing else. Each read waits longer than the route can take over a stalled
    service, one bound per member and one for the rest, so a held receipt reaches the operator (G3-11)."""
    host, port = o01_target(url)
    conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT_S * (len(cset.get("intents") or []) + 1))
    try:
        conn.request("POST", COMMAND_SETS, body=json.dumps(cset).encode("utf-8"),
                     headers={W.O01_HEADER: W.O01_VERSION, "Content-Type": W.JSON_TYPE,
                              "Authorization": "Bearer " + token})
        reply = conn.getresponse()
        raw = reply.read()
        status = reply.status
    except (OSError, http.client.HTTPException) as e:
        raise Unavailable(f"the O-01 route at http://{host}:{port} did not answer ({type(e).__name__}); {_MAY_BE_USED}",
                          reason="o01_unreachable") from None
    finally:
        conn.close()
    try:
        body = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, ValueError):
        body = None
    if status == 202 and isinstance(body, dict) and isinstance(body.get("results"), list):
        return body
    code = body.get("code") if isinstance(body, dict) else None
    if status == 401:
        raise PermissionDenied("the O-01 route did not accept the bearer token; the approval is unused",
                               reason="o01_unauthenticated")
    if status == 503:
        raise Unavailable(f"the O-01 route is unavailable; {_MAY_BE_USED}", reason="o01_unavailable")
    if code == "request_key_conflict":
        said = f"the set's client_request_key already has a receipt, for another set; {_UNUSED}"
    elif code == "unresolved_no_redispatch":  # says nothing of this approval: a used member can reach it too
        said = ("the route can no longer show this client_request_key's receipt. GET /v1/read/owner-operations shows "
                f"whether it was admitted, and if it was not, request it again {_NEW_KEY}")
    elif status in (400, 409):  # the statuses the route declares for a set it refuses before any owner
        said = _UNUSED
    else:
        raise ValidationFailed(f"the O-01 route gave no receipt ({code or status}); {_MAY_BE_USED}",
                               reason="o01_refused", o01_code=code, status=status)
    raise ValidationFailed(f"the O-01 route refused the set: {code or status}; {said}", reason="o01_refused",
                           o01_code=code, status=status)


_HELD_WAY_ON = ("This action is not admitted. Request it again once this is fixed, with a new approval if this one is "
                "refused as used")


@dataclass(frozen=True)
class Consumed:
    """What an owner's one consume call found: ``result``, the service's ``ConsumeResult``, or None when it gave none
    (``held_why``: no answer, a ``503``, a ``403``, a ``400``, or an answer that is not one). An owner holds the action
    for a None, allocates nothing and falls back to no other origin (G3-11; addendum 7, ruling 2).

    A None after the request went out may follow a member the service did use, its reply lost, so ``held_why`` says the
    next request may need a new approval. Only ``result == "CONSUMED"`` admits: the object itself is always true."""

    result: str | None
    held_why: str | None = None


def consume(*, consent_set_ref: str, set_digest: str, recipient_ref: str, installation_ref: str, intent_ref: str,
            origin_proof_ref: str, owner: str, operation_ref: str, sock_path: str | None = None) -> Consumed:
    """An owner's ``POST /g3/v1/consume`` at allocation (G3-08), with the SW-02 digest of the set it received and the
    member's own proof. ``CONSUMED`` records the member as used, against ``(owner, operation_ref)``, so an owner makes
    this call once per member. A reply lost after that fails closed: the next call is refused, ``CONSENT_ALREADY_USED``
    while the consent is current. Each read of the service's answer is bounded by ``TIMEOUT_S``: an answer sent in
    pieces can hold the call longer, by its own length."""
    body = {"wire_version": G3_WIRE, "consent_set_ref": consent_set_ref, "intent_ref": intent_ref,
            "origin_proof_ref": origin_proof_ref, "set_digest": set_digest, "recipient_ref": recipient_ref,
            "installation_ref": installation_ref, "owner": owner, "operation_ref": operation_ref}
    try:
        status, reply = _g3(sock_path, "POST", "/g3/v1/consume", body, timeout=TIMEOUT_S)
    except (Unavailable, PermissionDenied) as exc:
        return Consumed(None, f"{exc.message}. {_HELD_WAY_ON}")
    if status != 200:
        refused = _g3_refusal(status, reply)
        return Consumed(None, f"{getattr(refused, 'message', str(refused))}. {_HELD_WAY_ON}")
    # The wire's whole answer (G3-13: CONSUMED alone is G3 origin), so a body that merely says the word is none.
    answer = reply if isinstance(reply, dict) else {}
    result = answer.get("result")
    if (result not in CONSUME_RESULTS or answer.get("wire_version") != G3_WIRE
            or (result == "CONSUMED" and not isinstance(answer.get("consumed_at"), str))):
        return Consumed(None, f"the answer on {sock_path or REQUEST_SOCK} is no ConsumeResult. {_HELD_WAY_ON}")
    return Consumed(result)


def probe(sock_path: str | None = None) -> str | None:
    """The probe that consumes nothing (addendum 7, ruling 2): a read of an approval request no one made, on
    ``request.sock``. None when the G3 service answers; otherwise why not, in the client's own words."""
    try:
        status, body = _g3(sock_path, "GET", "/g3/v1/approval-requests/" + PROBE_REF, timeout=PROBE_TIMEOUT_S)
    except (Unavailable, PermissionDenied) as exc:
        return exc.message
    if status == 404:
        return None
    refused = _g3_refusal(status, body)
    return getattr(refused, "message", str(refused))


def _held(standing: Any, answers: str | None) -> str:
    """Why a member was held for want of an origin, as the client finds it: what failed on this host, else that the
    service did not answer the probe (``answers``), else the project's policy, the client being bound to no project
    (addendum 7)."""
    from aew.g3standing import POLICY_FIX

    if not standing.counts:
        return f"{standing.reason}. Fix: {standing.fix}"
    if answers is not None:
        return f"the G3 service does not answer: {answers}"
    return ("on this host G3 counts as far as the client can tell, and the service answers. The route's log names the "
            "cause. If it names none, it is the project's policy, which must keep every launch contained, or a route "
            f"started with no --project. For the policy: {POLICY_FIX}")


# What the operator is told of a member the owner did not admit, by its admission state and reason (addendum 7: the
# notes are keyed on both). Each takes the host's standing, as the client found it after the submission, and the probe's
# answer then (None when the service answered).
AGAIN = f"Nothing was admitted, and this approval is not used again: request the action again {_NEW_KEY}"
SOME_ADMITTED = ("Requesting the whole set again would admit the admitted members a second time: request only the "
                 f"members not admitted, {_NEW_KEY}, on a new approval")
NO_EFFECT = "Consumed and recorded: no owner on this route performs a protected action, so nothing else happens"
NOTES: dict[tuple[str, str], Callable[[Any, str | None], str]] = {
    ("HELD", "ORIGIN_NOT_ESTABLISHED"): lambda st, answers: (
        f"Approved in the confirmer and submitted, and the owner held it: {_held(st, answers)}. It can be requested "
        "again once this is fixed (addendum 5)"),
    ("REJECTED", "ORIGIN_NOT_ESTABLISHED"): lambda st, answers: (
        "Approved in the confirmer and submitted, and the owner refused it: the G3 service has no consent record for "
        "this member"),
    ("REJECTED", "ORIGIN_UNQUALIFIED"): lambda st, answers: (
        "Approved in the confirmer and submitted, and the owner refused it: the consent is not one the G3 service "
        "issued for exactly this set, member and owner"),
    ("REJECTED", "CURRENTNESS_EXPIRED"): lambda st, answers: (
        "Approved in the confirmer and submitted, and the owner refused it: the consent has expired"),
    ("REJECTED", "CONSENT_ALREADY_USED_OR_MISSING"): lambda st, answers: (
        "Approved in the confirmer and submitted, and the owner refused it: this member's consent was already used, "
        "and each is used once"),
}


def note(receipt: dict[str, Any], standing: Any, answers: str | None = None) -> str | None:
    """What the operator is told of a receipt, or None. An admitted member with no effect observed says so. The first
    member the owner did not admit for a reason the client explains (:data:`NOTES`) gets that reason, with the way on:
    a set of which some members were admitted names each side, since requesting all of it again would admit them twice.
    ``standing`` is the host's, as :func:`aew.g3standing.standing` gives it to a reader bound to no project, and
    ``answers`` is :func:`probe`'s."""
    results = [r for r in receipt.get("results", []) if isinstance(r, dict)]
    admitted = [r for r in results if r.get("admission_state") == "ADMITTED"]
    others = [r for r in results if r.get("admission_state") != "ADMITTED"]
    said = next((NOTES[key](standing, answers) for r in others
                 if (key := (str(r.get("admission_state")), str(r.get("reason_code")))) in NOTES), None)
    parts = []
    if any(r.get("effect_state") == "NOT_OBSERVED" for r in admitted):
        parts.append(NO_EFFECT)
    if admitted and others:
        listed = ", ".join(f"{r.get('intent_ref')} ({r.get('admission_state')} {r.get('reason_code')})" for r in others)
        parts.append(f"Admitted: {', '.join(str(r.get('intent_ref')) for r in admitted)}. Not admitted: {listed}")
    if said:
        parts.extend([said, SOME_ADMITTED if admitted else AGAIN])
    return ". ".join(parts) + "." if parts else None
