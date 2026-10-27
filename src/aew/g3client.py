"""The G3 client: asks the operator to approve a protected command set, then submits the approved set (A-37 G3-02,
G3-07; STG-03, G3-D; the Lead's rulings of 2026-10-25).

    1. the set, a complete O-01 0.2 CommandSet, is checked: every member a protected action, no member with an
       ``origin_proof_ref`` and no ``consent_set_ref`` yet (the client makes both), and nothing else wrong with it;
    2. each member gets a fresh proof from a cryptographically secure source (G3-02), and the set its O-01 schema check;
    3. ``POST /g3/v1/approval-requests`` on ``request.sock``: the operator approves or declines in the confirmer;
    4. ``GET /g3/v1/approval-requests/{approval_ref}`` until a decision, no longer than the approval lives;
    5. the record's ``set_digest`` is checked against the SW-02 digest of the set to be submitted (the G3-07
       invariant), and only then is the set submitted unchanged, with ``consent_set_ref`` set, to the O-01 route.

It never asks for, receives or stores the PIN (G3-05). The bearer token for the O-01 route is read from a file, sent
in one header, and never printed, logged or put in an error. The G3 service and the O-01 route are both on this host:
``request.sock`` is a Unix filesystem socket, and the route must be on the loopback address.

What this module restates, held to its owners by ``tests/unit/test_g3client.py`` (``aew_g3`` is installed apart from
``aew``, so it is not imported here): the request socket's path (``aew_g3.cli``, ``aew_g3.REQUEST_SOCK``), the G3
wire's header and version (``g3-wire.schema.json``), the service's request timeout (``aew_g3.server``) and the
approval expiry's ceiling (``aew_g3.deployment.TRIPWIRES``).
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

# What the operator is told once the set was submitted and its owner did not admit it for want of G3 (fixed text).
NOT_ESTABLISHED = (
    "Approved in the confirmer and submitted. The owner did not admit it, because G3 is not yet established on this "
    "host: owners accept G3 consent only once the owners' side (G3-C) lands, and every agent context, the Lead "
    "included, runs contained (CS-4). Until then no protected action is admitted. Nothing was admitted, and nothing "
    "is wrong with the request.")


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
    def __init__(self, path: str) -> None:
        super().__init__("localhost", timeout=TIMEOUT_S)
        self._path = path

    def connect(self) -> None:
        if sys.platform == "win32":  # G3 is a Linux profile: its sockets are Unix filesystem sockets
            raise OSError("the G3 service runs on Linux only")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT_S)
        s.connect(self._path)
        self.sock = s


def _g3(sock_path: str | None, method: str, path: str, body: Any = None) -> tuple[int, Any]:
    """One request on ``request.sock`` (``REQUEST_SOCK``, read at call time, unless a path is given)."""
    sock_path = sock_path or REQUEST_SOCK
    conn = _UnixHTTP(sock_path)
    try:
        data = None if body is None else json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        reply = conn.getresponse()
        raw = reply.read()
        if reply.getheader(G3_HEADER) != G3_WIRE:
            raise Unavailable(f"the answer on {sock_path} is not the G3 wire's ({G3_WIRE})", reason="g3_not_g3")
        return reply.status, (json.loads(raw.decode("utf-8")) if raw else None)
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


def await_decision(pending: dict[str, Any], sock_path: str | None = None, *,
                   now: Callable[[], datetime] = lambda: datetime.now(UTC),
                   sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Step 4: the ``ConsentRecord`` once the operator approves. A decline, an expiry, or an approval lost to a restart
    of the service refuses; the wait ends with the approval's own life, ``expires_at`` and a grace, and never later
    than G3-02's ceiling."""
    ref = pending["approval_ref"]
    try:
        expires = W.parse_time(pending["expires_at"])
    except (KeyError, AttributeError, TypeError, ValueError):  # absent, not a string, or no time
        raise Unavailable("the G3 service's answer names no expires_at", reason="g3_not_g3") from None
    started = now()
    deadline = min((expires - started).total_seconds(), EXPIRY_CEILING_S) + GRACE_S
    while True:
        status, body = _g3(sock_path, "GET", "/g3/v1/approval-requests/" + ref)
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
        if (now() - started).total_seconds() >= deadline:
            raise OperatorAuthorizationRequired("the approval was still undecided past its expiry; nothing was "
                                                "submitted. Request it again", reason="expired", approval_ref=ref)
        sleep(POLL_S)


# ------------------------------------------------------------------------------------------------ the O-01 route
def o01_target(url: str) -> tuple[str, int]:
    """The route's host and port: an http URL on the loopback address, with no user, path, query or fragment."""
    u = urlsplit(url)
    if u.scheme != "http" or u.hostname not in LOOPBACK or u.username or u.password or u.path not in ("", "/") \
            or u.query or u.fragment:
        raise UsageError(f"--o01 must be the O-01 route's http://127.0.0.1:<port>, on this host; got {url!r}",
                         reason="o01_not_loopback")
    try:
        port = u.port or 80
    except ValueError:
        raise UsageError(f"--o01 names no valid port: {url!r}", reason="o01_not_loopback") from None
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


def submit(cset: dict[str, Any], url: str, token: str) -> dict[str, Any]:
    """Step 5: ``POST /o01/v0/command-sets``, and its receipt (202). Every answer's text is built here, so the token
    reaches the request's one header and nothing else."""
    host, port = o01_target(url)
    conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT_S)
    try:
        conn.request("POST", COMMAND_SETS, body=json.dumps(cset).encode("utf-8"),
                     headers={W.O01_HEADER: W.O01_VERSION, "Content-Type": W.JSON_TYPE,
                              "Authorization": "Bearer " + token})
        reply = conn.getresponse()
        raw = reply.read()
        status = reply.status
    except (OSError, http.client.HTTPException) as e:
        raise Unavailable(f"the O-01 route at http://{host}:{port} did not answer ({type(e).__name__}); the "
                          "approval is unused", reason="o01_unreachable") from None
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
        raise Unavailable("the O-01 route is unavailable; the approval is unused", reason="o01_unavailable")
    raise ValidationFailed(f"the O-01 route refused the set: {code or status}; the approval is unused",
                           reason="o01_refused", o01_code=code, status=status)


def note(receipt: dict[str, Any]) -> str | None:
    """The fixed text for a receipt whose protected members were not admitted for want of G3, or None."""
    reasons = {r.get("reason_code") for r in receipt.get("results", []) if isinstance(r, dict)}
    return NOT_ESTABLISHED if "ORIGIN_NOT_ESTABLISHED" in reasons else None
