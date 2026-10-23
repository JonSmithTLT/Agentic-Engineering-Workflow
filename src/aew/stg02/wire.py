"""Wire constants and builders shared by the slice's D-01 reads and O-01 commands (STG-02).

Everything here restates nothing normative that a vendored adopted file already holds: header values, Problem
shapes and stamp shapes are the adopted 0.3.4 / 0.2 ones, and the tests check every emitted body against the vendored
schemas (:mod:`aew.stg02.adopted`).

**Stamps.** The slice never mints a qualified stamp. A qualified ``SourceStamp`` needs an owner-issued renewal with
its own proof and finite validity (D01-WR-12..14), and no AEW owner issues one today; a renewal made up by this
backend would be the carrier renewing an owner's conclusion, which the wire forbids. So a fact read from AEW's own
engine state is stamped with its real identity (``aew:`` fact and epoch) and ``qualification: unqualified``; a fact
served from the fixture world says so with a ``fixture:`` prefix and is unqualified too; an owner with no source at
all is ``not_established`` / ``unavailable``. See ``docs/stg02/BACKEND-REPORT.md``.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

D01_HEADER, D01_VERSION = "X-AEW-Wire-Version", "0.3.4"
O01_HEADER, O01_VERSION = "X-AEW-O01-Wire", "o01-command-0.2-review-candidate"
NO_STORE = ("Cache-Control", "private, no-store")
PROBLEM_TYPE = "application/problem+json"
JSON_TYPE = "application/json"
FIXTURE = "fixture:"  # every fixture-world identifier, fact and epoch starts with this

# The D-01 and O-01 Problem codes, with the status and retry each fixes (both Problem schemas' allOf).
PROBLEM_CODES: dict[str, tuple[int, str, str]] = {
    "invalid_request": (400, "never", "The request is not a valid request for this route"),
    "authentication_unqualified": (401, "reauthenticate", "The request is not authenticated"),
    "not_found_or_not_disclosable": (404, "never", "Not found or not disclosable"),
    "cursor_stale_or_unauthorized": (409, "refresh_read", "The cursor is stale or not yours; read again"),
    "owner_unavailable": (503, "when_source_recovers", "The owner projection is unavailable"),
    "request_key_conflict": (409, "never", "This client request key was used for a different request"),
    "unresolved_no_redispatch": (409, "never", "This key's outcome cannot be resolved; it is never dispatched again"),
    "unsupported_action": (400, "never", "The action is not supported"),
}
REF = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:\-/]{0,191}")


def utc(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def later(t: datetime, seconds: float) -> datetime:
    return t + timedelta(seconds=seconds)


def correlation_id() -> str:
    return "corr:" + uuid.uuid4().hex


def problem(code: str, correlation: str) -> tuple[int, dict[str, Any]]:
    status, retry, title = PROBLEM_CODES[code]
    return status, {"type": "about:blank", "title": title, "status": status, "code": code, "retry": retry,
                    "correlation_id": correlation}


# ------------------------------------------------------------------------------------------- path identifiers

class BadId(ValueError):
    """A path identifier that is not the canonical unpadded base64url of an exact UTF-8 identifier."""


def b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def decode_id(segment: str, *, min_len: int = 1, max_len: int = 300) -> str:
    """The profile's transport rule: decoded once and round-trip re-encoded. Padding, a non-alphabet character
    (which covers percent-encoding, and so double encoding), invalid UTF-8 and a non-NFC identifier are refused."""
    if not (min_len <= len(segment) <= max_len) or not re.fullmatch(r"[A-Za-z0-9_-]+", segment):
        raise BadId(segment)
    try:
        raw = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        text = raw.decode("utf-8", errors="strict")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise BadId(segment) from exc
    if b64url(text) != segment or not unicodedata.is_normalized("NFC", text) or not text:
        raise BadId(segment)
    return text


# ------------------------------------------------------------------------------------------- stamps

RENEWAL_NONE: dict[str, Any] = {"kind": "none", "source_proof_ref": None, "valid_until": None, "qualified_owner": None,
                                "source_epoch": None, "coverage_ref": None, "verification_method": "none",
                                "checked_at": None, "invalidation": "none"}


def stamp(owner: str, fact_ref: str, epoch: str, version: str, observed_at: str, *, coverage_ref: str,
          issuer_ref: str) -> dict[str, Any]:
    """An unqualified report of an owner fact we can name (a real AEW record or a labelled fixture). Its currentness
    is not established by any owner renewal, so it is never ``present_current`` (OP-03)."""
    return {"owner": owner, "fact_ref": fact_ref, "source_epoch": epoch, "source_version": version,
            "coverage_ref": coverage_ref, "observed_at": observed_at, "qualification": "unqualified",
            "observation_state": "unknown", "renewal": dict(RENEWAL_NONE), "closures": [],
            "authority_class": "unqualified_report", "governing_owner": None, "issuer_ref": issuer_ref,
            "owner_coverage_class": "not_established"}


def unavailable(owner: str, observed_at: str, *, coverage_ref: str) -> dict[str, Any]:
    """An owner with no source this backend can read: not established (OP-03, the transport reason)."""
    s = stamp(owner, f"unavailable:{owner}", "unavailable", "unavailable", observed_at, coverage_ref=coverage_ref,
              issuer_ref=f"unavailable:{owner}")
    s.update(qualification="not_established", observation_state="unavailable")
    return s


def subject(kind: str, ident: str, *, revision: str | None = None, generation: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "id": ident, "revision": revision, "generation": generation, "package_digest": None}


def is_fixture(s: dict[str, Any]) -> bool:
    return any(str(s.get(k) or "").startswith(FIXTURE) for k in ("fact_ref", "source_epoch"))


# ------------------------------------------------------------------------------------------- canonical digests

def canonical(o: Any) -> bytes:
    """A-24 SW-02 canonical bytes, frozen: ASCII-escaped, key-sorted, compact, no NaN."""
    return json.dumps(o, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def set_digest(req: dict[str, Any]) -> str:
    """A-24 SW-02 set fingerprint (profile CS-03): the four fields, wire_version outside it."""
    return hashlib.sha256(canonical({k: req[k] for k in ("request_set_ref", "recipient_ref", "installation_ref",
                                                         "intents")})).hexdigest()


def full_digest(req: dict[str, Any]) -> str:
    """CS-03: the client key binds the whole submitted request."""
    return hashlib.sha256(canonical(req)).hexdigest()


def intent_digest(intent: dict[str, Any]) -> str:
    """A-24 SW-04: a delegated grant is bound to the exact intent by this digest."""
    return hashlib.sha256(canonical(intent)).hexdigest()
