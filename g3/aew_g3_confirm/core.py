"""The confirmer's core: what it asks the G3 service, what it shows, and what it says back (A-37 G3-03, G3-05, G3-10;
STG-03, G3-B). Standard library only, and Python 3.6: no GTK here, so every test can reach all of it.

What it restates, each held to its owner by ``tests/unit/test_g3_confirm.py`` (this package cannot import ``aew_g3``,
which needs Python 3.11): the confirm socket's path and its two routes (``aew_g3.cli``, ``aew_g3.server``), the
wire's header and version and the rendering's line limit (``g3-wire.schema.json``), the Problem codes a decision can
draw (``aew_g3.wire.STATUS``), and root's command (``aew_g3.COMMAND``).
"""

import http.client
import json
import os
import socket
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

CONFIRM_SOCK = "/run/aew-g3/confirm.sock"
PENDING_PATH = "/g3/v1/pending"
DECISION_PATH = "/g3/v1/approvals/"
WIRE_HEADER = "X-AEW-G3-Wire"
WIRE = "g3-0.6.1-candidate"
MAX_LINES = 243  # PendingApproval.rendering.maxItems (R2-1)
COMMAND = "/usr/local/sbin/aew-g3"
TIMEOUT_S = 30  # the service's own request timeout: a stall is waited out no longer than the service waits for us

# Addendum 4: the confirmer starts at login, with no window, and posts a notification per pending approval.
APP_ID = "org.aew.G3Confirm"  # also both desktop entries' file name, by which a desktop finds the app's notifications
AT_LOGIN = "--at-login"  # the autostart entry's one argument: start with no window. Never a PIN's route (G3-05)
POLL_S = 5  # addendum 4's chosen default: short beside an approval's expiry, 10 minutes at most (G3-02)
NOTIFY_TITLE = "An AEW approval is waiting"  # fixed: no rendering line and no text from the request (G3-03)
NOTIFY_BODY = "Open AEW approvals to see it in full, and approve or decline it there."

# What the operator is told after a decision, by outcome: fixed text, never anything the service or a client sent.
APPROVED, DECLINED = "APPROVED", "DECLINED"
MESSAGES = {
    APPROVED: "Approved. The consent record is issued, and AEW collects it.",
    DECLINED: "Declined. Nothing was approved.",
    "NOT_FOUND": "This approval is no longer pending: it was decided, or the service restarted. The list is refreshed.",
    "APPROVAL_EXPIRED": "This approval has expired. Nothing was approved; AEW asks for it again if it is still wanted.",
    "PIN_INCORRECT": "Wrong PIN. Nothing was approved.",
    "PIN_LOCKED": "The PIN is locked after too many wrong entries, or was set under a lower minimum. Nothing was "
                  "approved. Root sets it again: sudo " + COMMAND + " set-pin",
    "STRUCTURAL": "The service refused the decision as malformed: a PIN is 6 to 128 characters. Nothing was "
                  "approved.",
    "PEER_NOT_PERMITTED": "The service answers only the operator's own account, so nothing was approved. Run the "
                          "confirmer as the operator, on the desktop, outside any sandbox.",
    "G3_UNAVAILABLE": "The G3 service is holding every approval, so nothing was approved. Its journal names the "
                      "cause: journalctl -u aew-g3.service",
}
UNREACHABLE = ("The G3 service did not answer. Nothing is known to be decided: the list is refreshed, and an approval "
               "no longer listed was decided. Its state: systemctl status aew-g3.service")


class Unreachable(Exception):
    """No answer from the service on the socket, or an answer that is not the G3 wire's."""


class NotPermitted(Unreachable):
    """The service is another account's: its socket refuses this one, or it answers PEER_NOT_PERMITTED."""


class Malformed(Exception):
    """A pending approval this confirmer will not show, so it can be declined but never approved."""


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


def _call(sock_path: str, method: str, path: str, body: Optional[bytes]) -> Tuple[int, Any]:
    """One request, one reply. The body, which may hold the PIN, never reaches an exception's text."""
    conn = _UnixHTTP(sock_path)
    try:
        headers = {"Content-Type": "application/json"} if body is not None else {}
        conn.request(method, path, body=body, headers=headers)
        reply = conn.getresponse()
        raw = reply.read()
        if reply.getheader(WIRE_HEADER) != WIRE:
            raise Unreachable("the reply on " + sock_path + " is not the G3 wire's (" + WIRE + ")")
        return reply.status, (json.loads(raw.decode("utf-8")) if raw else None)
    except PermissionError:  # the socket is mode 0600 and another account's
        raise NotPermitted("PermissionError on " + sock_path) from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise Unreachable(type(e).__name__ + " on " + sock_path) from None
    finally:
        conn.close()


def list_pending(sock_path: str = CONFIRM_SOCK) -> List[Dict[str, Any]]:
    """``GET /g3/v1/pending``: the open approvals."""
    status, body = _call(sock_path, "GET", PENDING_PATH, None)
    if status != 200 or not isinstance(body, list):
        code = body.get("code") if isinstance(body, dict) else None
        refusal = NotPermitted if code == "PEER_NOT_PERMITTED" else Unreachable
        raise refusal(MESSAGES.get(str(code), "the service answered " + str(status)))
    return body


def may_use(sock_path: str = CONFIRM_SOCK) -> bool:
    """False when the socket is there and not this account's to use: another user's login, where the autostart entry
    runs too (addendum 4). A missing socket is a service not yet up, which the confirmer waits for."""
    return not os.path.exists(sock_path) or os.access(sock_path, os.R_OK | os.W_OK)


class Watch:
    """Which notifications to post and withdraw (addendum 4): one per pending ``approval_ref``, posted once, withdrawn
    when its approval leaves the list (decided, expired, or lost to a restart). Only a successful list is given here:
    a failed one changes nothing, so a stalled read never withdraws a notification only to post it again."""

    def __init__(self) -> None:
        self.posted: Set[str] = set()

    def update(self, pending: List[Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """The refs to notify of, and the refs to withdraw, from one successful list."""
        now = {summary(p)[0] for p in pending} - {""}
        post, withdraw = sorted(now - self.posted), sorted(self.posted - now)
        self.posted = now
        return post, withdraw


def notification_id(approval_ref: str) -> str:
    """The desktop's id for an approval's notification: a key, never shown."""
    return "pending:" + approval_ref


def decision_body(pin: Optional[str]) -> bytes:
    """An ``ApprovalDecision``: APPROVE carries the PIN; DECLINE carries none (G3-05)."""
    if pin is None:
        return json.dumps({"decision": "DECLINE"}).encode("utf-8")
    return json.dumps({"decision": "APPROVE", "pin": pin}).encode("utf-8")


def decide(approval_ref: str, pin: Optional[str], sock_path: str = CONFIRM_SOCK) -> str:
    """Sends one decision, once, and returns its outcome: ``APPROVED``, ``DECLINED`` or the service's Problem code.
    Never retried here: a lost reply is ``Unreachable``, and a second decision on the same approval is ``NOT_FOUND``
    (addendum 2 §1)."""
    status, body = _call(sock_path, "POST", DECISION_PATH + approval_ref, decision_body(pin))
    if status == 200 and pin is not None:
        return APPROVED
    if status == 204 and pin is None:
        return DECLINED
    code = body.get("code") if isinstance(body, dict) else None
    if not isinstance(code, str):
        raise Unreachable("the service answered " + str(status) + " with no Problem")
    return code


def message(outcome: str) -> str:
    """The fixed text for an outcome; a code this table lacks is named as the service sent it."""
    return MESSAGES.get(outcome, "The service refused the decision: " + outcome + ". Nothing was approved.")


# ------------------------------------------------------------------------------------------------ what is shown
# The labels are the only text the confirmer adds; every value is one of the served line's own fields (G3-03).
LABEL_ACTION, LABEL_FACT = "action", "owner fact"
LABELS = (LABEL_ACTION, LABEL_FACT)  # a TYPED_FIELD row's label is its own field_path


def shown(value: Any) -> str:
    """A served value as JSON with every non-ASCII character escaped: a string shows its quotes, so null, true and
    "null" never look alike, and no control, bidirectional or look-alike character can disguise what is approved."""
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def rows(pending: Dict[str, Any]) -> List[Tuple[str, str]]:
    """The rendering of one pending approval as (label, value) rows, one per served line, in order. A line this
    confirmer cannot show exactly is ``Malformed``: nothing is shown in its place, and Approve is never offered."""
    rendering = pending.get("rendering")
    if not isinstance(rendering, list) or not 1 <= len(rendering) <= MAX_LINES:
        raise Malformed("the rendering is not a list of 1 to " + str(MAX_LINES) + " lines")
    out = []
    for i, line in enumerate(rendering):
        out.append(_row(i, line))
    return out


def _row(i: int, line: Any) -> Tuple[str, str]:
    where = "line " + str(i + 1)
    if not isinstance(line, dict) or set(line) != {"template_id", "values", "source"}:
        raise Malformed(where + " is not a rendering line")
    values, source = line["values"], line["source"]
    if not isinstance(values, dict) or not isinstance(source, dict) or not isinstance(line["template_id"], str):
        raise Malformed(where + " is not a rendering line")
    kind = source.get("kind")
    if kind == "TEMPLATE":
        if values or set(source) != {"kind"}:
            raise Malformed(where + ": a template line carries no values")
        return LABEL_ACTION, line["template_id"]
    if kind == "TYPED_FIELD":
        path = source.get("field_path")
        if set(source) != {"kind", "field_path"} or set(values) != {"name", "value"} or values["name"] != path \
                or not isinstance(path, str):
            raise Malformed(where + ": a typed field shows its own path and value")
        return path, shown(values["value"])
    if kind == "OWNER_FACT":
        keys = {"kind", "owner", "fact_ref", "observed_at", "observation_state"}
        if set(source) != keys:
            raise Malformed(where + ": an owner fact names its owner, fact and observation")
        return LABEL_FACT, " ".join(shown(source[k]) for k in ("owner", "fact_ref", "observation_state",
                                                                "observed_at")) + " " + shown(values)
    raise Malformed(where + " has no source G3-03 allows")


def summary(pending: Dict[str, Any]) -> Tuple[str, str]:
    """The served approval_ref and expires_at, which name an approval in the list."""
    return str(pending.get("approval_ref", "")), str(pending.get("expires_at", ""))
