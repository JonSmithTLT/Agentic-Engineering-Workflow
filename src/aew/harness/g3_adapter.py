"""G3 at the operator endpoint's challenge: a consumed approval stands in for the typed-back code, for one challenge
(the G3-C brief's PR C3, and the designer's rulings on it, 2026-11-08). Its first binding is the steering raise.

It holds no authority and constructs no ``OperatorPrincipal``: the endpoint does, once :func:`consume_member` says
``CONSUMED``. It never sees the PIN, which is typed only in the confirmer (``G3-05``), and it never accepts a consent
from the requester: the endpoint builds the set, asks for the approval and consumes it itself. A Lead never reaches
this: the operator starts it with ``aew lead mode raise``, at their terminal.

**The path is chosen once, at the start of a challenge** (:func:`choose`). The typed code runs when the operation has no
binding or G3's standing fails. Once a challenge takes the G3 path it never moves to the code, or an outage would
downgrade G3 to it (``G3-11``):

- no answer, a 503, a 403 or a 400, at the request, the wait (:func:`outcomes`) or the consume (no result): HELD;
- declined, expired, or any consume result but ``CONSUMED``: refused, and the reply says to request it again;
- the standing is computed again just before consume, as an owner's rule. If it fails: HELD, consume is not called, and
  the next request takes the code, with the standing's reason.

**What the consent binds:** the values the challenge binds, carried in A-43's target fields (:func:`raise_set`). A-39's
target has no digest field, so ``reason_ref`` carries the legality digest: a deliberate stretch for this bridge,
recorded in the designer's ruling."""

from __future__ import annotations

import contextlib
import hashlib
import secrets
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from aew import errors, g3client, g3standing
from aew.stg02 import wire as W

# The binding table: an endpoint operation and the protected action it is. With no row, it keeps the typed code.
BINDINGS = {"mode_raise": "SET_STEERING_MODE"}
RAISE_INTENT = "intent:steering-raise"
OWNER = "ADC"  # the pinned G3 wire's label for this row (the overlay's module docstring); raise_mode is the operation
LEGALITY = "legality:sha256:"
GENERATION = "gen:"
REVISION = "rev:"
HELD = "g3_held"
REFUSED = "g3_refused"
AGAIN = "Nothing was raised: request it again"
# A 400 at the request is the service refusing the set itself: asking again gets the same answer until this is fixed
OLDER_SERVICE = (f"The likely cause is a G3 service installed from a wheel older than this `aew`, which does not know "
                 f"{BINDINGS['mode_raise']}. Install it again as root, which keeps the ledger, the key and the PIN "
                 f"hash: {g3standing.INSTALL}. Nothing was raised")
EVERY_REQUEST = "Each `aew lead mode raise` asks for a new approval"


def choose(operation: str, policy: dict[str, Any] | None) -> tuple[bool, str | None]:
    """``(use G3, why not)``: the one choice of a challenge's path. ``why not`` is the standing's line, when the
    operation is bound and G3 does not count; an operation with no binding has nothing to say."""
    if operation not in BINDINGS:
        return False, None
    standing = g3standing.standing(policy)
    return standing.counts, None if standing.counts else standing.line()


def mode_version(rev: Any) -> str:
    return f"{REVISION}{rev or 0}"


def _ref(prefix: str, value: str) -> str:
    """``value`` as the rest of an O-01 ref."""
    return prefix + "".join(c if c.isascii() and (c.isalnum() or c in "._/-") else "-" for c in value)[:96]


def raise_set(bound: dict[str, Any], *, token: Callable[[int], str] = secrets.token_hex) -> dict[str, Any]:
    """The command set of a steering raise, from what ``steering_raise_preview`` bound. A mode that was never set counts
    as the lowest (``steering.RANK``), and the wire has no empty mode."""
    project = _ref("project:", str(bound["project"]))
    installation = _ref("installation:", str(bound["project"]))
    generation = f"{GENERATION}{bound['generation']}"
    version = mode_version(bound["mode_rev"])
    return {
        "wire_version": W.O01_VERSION, "request_set_ref": "request:steering-raise:" + token(8),
        "client_request_key": "key:steering-raise:" + token(8), "recipient_ref": "recipient:operator-endpoint",
        "installation_ref": installation, "consent_set_ref": None,
        "intents": [{
            "intent_ref": RAISE_INTENT, "action": BINDINGS["mode_raise"], "actor_ref": "operator:endpoint",
            "authority_class": "OPERATOR_RESERVED", "owner_hint": OWNER, "origin_proof_ref": None,
            "delegated_grant_proof_ref": None,
            "subject": {"project_ref": project, "installation_ref": installation, "attachment_ref": None,
                        "generation_ref": None},
            "predecessor": {"basis_ref": project, "basis_version": version, "source_epoch": generation},
            "target": {"lead_generation_ref": generation, "current_mode": (bound["previous"] or "crawl").upper(),
                       "mode": str(bound["mode"]).upper(), "mode_version": version, "mission_ref": None,
                       "reason_ref": LEGALITY + str(bound["legality_digest"])},
        }]}


@dataclass(frozen=True)
class RaiseValues:
    """What the consent bound, which ``raise_mode`` receives, so its own staleness refusals decide."""

    mode: str
    generation: int
    legality_digest: str


def bound_values(cset: dict[str, Any]) -> RaiseValues:
    target = cset["intents"][0]["target"]
    return RaiseValues(target["mode"].lower(), int(target["lead_generation_ref"].removeprefix(GENERATION)),
                       target["reason_ref"].removeprefix(LEGALITY))


def moved(cset: dict[str, Any], now: dict[str, Any]) -> str | None:
    """What has moved since the operator approved ``cset``, by ``now``, a fresh preview; None when nothing has."""
    target = cset["intents"][0]["target"]
    current = {"lead_generation_ref": f"{GENERATION}{now['generation']}",
               "current_mode": (now["previous"] or "crawl").upper(), "mode_version": mode_version(now["mode_rev"]),
               "reason_ref": LEGALITY + str(now["legality_digest"])}
    changed = [k for k, v in current.items() if target[k] != v]
    return ", ".join(changed) or None


def operation_ref(consent_set_ref: str, intent_ref: str) -> str:
    digest = hashlib.sha256(f"{consent_set_ref}\0{intent_ref}".encode()).hexdigest()
    return f"aew:steering-raise:{digest}"


def held(why: str, way_on: str = AGAIN) -> errors.Unavailable:
    return errors.Unavailable(f"the raise is held: {why}. {way_on}; the mode stays where it is", reason=HELD)


def refused(why: str) -> errors.OperatorAuthorizationRequired:
    return errors.OperatorAuthorizationRequired(f"the raise was refused: {why}. {AGAIN}", reason=REFUSED)


def requester_gone(approval_ref: str) -> errors.OperatorAuthorizationRequired:
    return errors.OperatorAuthorizationRequired(
        f"the terminal that asked for the raise has gone, so this request ended and nothing will consume {approval_ref}"
        f": approving it now raises nothing, and it stays on the confirmer until it expires. {AGAIN}",
        reason="requester_gone", approval_ref=approval_ref)


@contextlib.contextmanager
def outcomes(bad_request: str = AGAIN) -> Iterator[None]:
    """The G3 path's two endings, for what the client raises (the designer's ruling 1): HELD for no answer, a 503, a 403
    or a 400, with ``bad_request`` as a 400's way on; a refusal for the rest. A decline or an expiry already says so,
    and passes as it is."""
    try:
        yield
    except errors.OperatorAuthorizationRequired:  # declined or expired: a kind of PermissionDenied, and a refusal
        raise
    except errors.Unavailable as exc:
        raise held(exc.message) from None
    except errors.PermissionDenied as exc:  # the 403: the service answers only the operator's account
        raise held(exc.message) from None
    except errors.ValidationFailed as exc:
        if exc.details.get("status") == 400:
            raise held(exc.message, bad_request) from None
        if exc.details.get("status") == 403:
            raise held(exc.message) from None
        raise refused(exc.message) from None


def approve(cset: dict[str, Any], on_pending: Callable[[dict[str, Any]], None],
            wait: Callable[[float], None] = time.sleep) -> tuple[dict[str, Any], dict[str, Any]]:
    """Ask for the approval and wait for the operator: the approved set and its consent record. ``on_pending`` tells the
    requester the approval is on the confirmer, and ``wait`` passes the time between looks at the service, so the
    endpoint can end the wait when the requester has gone."""
    with outcomes():
        proved = g3client.with_proofs(g3client.check_set(cset))
    with outcomes(bad_request=OLDER_SERVICE):
        pending = g3client.request_approval(proved)
    with outcomes():
        g3client.expires_at(pending)
        on_pending(pending)
        record = g3client.await_decision(pending, sleep=wait)
        return g3client.approved_set(proved, record), record


def consume_member(approved: dict[str, Any], record: dict[str, Any], policy: dict[str, Any] | None) -> dict[str, Any]:
    """Compute the standing again, then consume the set's one member (``G3-08``). The origin for the mode's record, on
    ``CONSUMED``; otherwise HELD or refused. Only ``CONSUMED`` admits. A service that gave no result may have used the
    member and lost its reply, so ``held_why``, the client's way on, says a new approval may be needed."""
    standing = g3standing.standing(policy)
    if not standing.counts:
        raise held(f"{standing.line()}. The next request takes the typed code")
    member = approved["intents"][0]
    out = g3client.consume(consent_set_ref=approved["consent_set_ref"], set_digest=W.set_digest(approved),
                           recipient_ref=approved["recipient_ref"], installation_ref=approved["installation_ref"],
                           intent_ref=member["intent_ref"], origin_proof_ref=member["origin_proof_ref"], owner=OWNER,
                           operation_ref=operation_ref(approved["consent_set_ref"], member["intent_ref"]))
    if out.result is None:
        raise errors.Unavailable(f"the raise is held, and the mode stays where it is: {out.held_why}. {EVERY_REQUEST}",
                                 reason=HELD)
    if out.result == "CONSENT_ALREADY_USED":
        raise refused(f"the G3 service answered {out.result}, so the next request needs a new approval")
    if out.result != "CONSUMED":
        raise refused(f"the G3 service answered {out.result}")
    return {"kind": "g3", "consent_set_ref": record.get("consent_set_ref"), "approval_ref": record.get("approval_ref")}
