"""`aew g3`: the G3 client's command (STG-03, G3-D; A-37 G3-02, G3-07; the Lead's rulings of 2026-10-25).

* `request` asks the operator to approve a protected command set in the G3 confirmer, waits for the decision, and
  submits the approved set to the O-01 route (:mod:`aew.g3client`). It is the operator's, at their own terminal:
  it refuses in a Lead session (:func:`aew.engine.custody_ops.refuse_in_lead_session`) before it reads anything, and
  once CS-4 contains the Lead, ``request.sock`` is out of its reach besides. A Lead asking for an operator approval
  is not built: that is the designer's question. Nothing here asks for the PIN, which is typed only in the confirmer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aew.cli.commands import _add_json
from aew.errors import NotFound, ValidationFailed


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("g3", help="the G3 client: ask the operator to approve a protected command set, and submit it")
    gsub = p.add_subparsers(dest="g3_cmd", required=True)
    q = gsub.add_parser("request", help="ask the operator to approve a protected O-01 command set in the G3 "
                                        "confirmer, wait for the decision, and submit the approved set")
    q.add_argument("set_file", help="a complete O-01 0.2 CommandSet, as JSON, every member a protected action, with "
                                    "origin_proof_ref and consent_set_ref null: the client makes both")
    q.add_argument("--o01", required=True, help="the O-01 route on this host, http://127.0.0.1:<port>")
    q.add_argument("--token-file", required=True, help="a file holding the O-01 route's bearer token on one line; "
                                                       "the token is never printed")
    _add_json(q)
    q.set_defaults(handler=_request)


def _request(a: argparse.Namespace) -> Any:
    from aew import g3client as C
    from aew.engine.custody_ops import refuse_in_lead_session

    refuse_in_lead_session("`aew g3 request` is the operator's, at their own terminal; it never runs in a Lead "
                           "session. Ask the operator to run it")
    C.o01_target(a.o01)
    token = C.read_token(a.token_file)
    path = Path(a.set_file)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise NotFound(f"no command set at {path}", reason="set_file_missing") from None
    try:
        cset = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValidationFailed(f"{path} is not JSON", reason="not_a_command_set") from None
    proved = C.with_proofs(C.check_set(cset))
    pending = C.request_approval(proved)
    sys.stderr.write(f"aew g3: waiting for the operator to approve or decline {pending['approval_ref']} in the "
                     f"confirmer (AEW approvals), until {pending.get('expires_at')}\n")
    sys.stderr.flush()
    record = C.await_decision(pending)
    receipt = C.submit(C.approved_set(proved, record), a.o01, token)
    out = {"approval_ref": pending["approval_ref"], "consent_set_ref": record.get("consent_set_ref"),
           "set_digest": record.get("set_digest"), "receipt": receipt, "note": C.note(receipt)}
    if a.json:
        return out
    lines = [f"approved: {out['approval_ref']} (consent {out['consent_set_ref']})", "submitted; the receipt:"]
    lines += [f"  {r.get('intent_ref')}: {r.get('admission_state')} {r.get('reason_code') or ''}".rstrip()
              for r in receipt["results"]]
    if out["note"]:
        lines.append(out["note"])
    return "\n".join(lines)
