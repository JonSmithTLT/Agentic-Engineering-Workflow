"""`aew g3`: the G3 client's command (STG-03, G3-D; A-37 G3-02, G3-07; the Lead's rulings of 2026-10-25).

* `request` asks the operator to approve a protected command set in the G3 confirmer, waits for the decision, and
  submits the approved set to the O-01 route (:mod:`aew.g3client`). It is the operator's, at their own terminal:
  it refuses in a Lead session (:func:`aew.engine.custody_ops.refuse_kept_out`) before it reads anything, and
  once CS-4 contains the Lead, ``request.sock`` is out of its reach besides. No typed tool asks for it (the steering
  tool hides ``request_confirmation``, register E183): a Lead names the action in its reply, and the operator runs
  this. Nothing here asks for the PIN, which is typed only in the confirmer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aew.cli.commands import _add_json, _cwd
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
    from aew import g3standing as S
    from aew.engine.custody_ops import refuse_kept_out

    refuse_kept_out(("g3", "request"))
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
    # Before the confirmer is asked: whether G3 counts here, and whether its service answers (addendum 7, ruling 2).
    # The request goes ahead either way: an approval made while G3 does not count admits nothing, and says so.
    standing = S.standing(project=False)
    answers = C.probe()
    sys.stderr.write(f"aew g3: {standing.line()}\n")
    if answers is not None:
        sys.stderr.write(f"aew g3: the G3 service does not answer: {answers}\n")
    if not standing.counts:
        sys.stderr.write("aew g3: approving admits nothing; the action stays held\n")
    sys.stderr.flush()
    pending = C.request_approval(proved)
    C.expires_at(pending)  # read first: an answer without one is refused, and nothing is said to wait for (F2)
    sys.stderr.write(f"aew g3: waiting for the operator to approve or decline {pending['approval_ref']} in the "
                     f"confirmer (AEW approvals), until {pending['expires_at']}\n")
    sys.stderr.flush()
    # The approval's per-host record (A-44 BOY-05.a): written by this client alone, at the start, after each read of
    # G3 and at the exit, so the dashboard and `aew status` show the wait without connecting to G3
    from aew import g3records as R
    from aew.errors import OperatorAuthorizationRequired

    writer = R.Writer(pending, project=R.project_label(_cwd(a)))
    outcome = None
    if writer.failed:
        sys.stderr.write(f"aew g3: {R.unwritten(writer)}\n")

    def say(text: str) -> None:
        sys.stderr.write(f"aew g3: {text}\n")
        sys.stderr.flush()

    try:
        try:
            record = C.await_decision(pending, on_read=writer.read, say=say, keep_reading=True)
        except OperatorAuthorizationRequired as exc:
            outcome = R.outcome_of(exc)
            raise
        outcome = "approved_not_submitted"
        receipt = C.submit(C.approved_set(proved, record), a.o01, token)
        outcome = "approved_submitted"
    finally:
        writer.finish(outcome)
    out = {"approval_ref": pending["approval_ref"], "consent_set_ref": record.get("consent_set_ref"),
           "set_digest": record.get("set_digest"), "receipt": receipt,
           "note": C.note(receipt, S.standing(project=False), C.probe())}
    if a.json:
        return out
    # the ref names itself (`consent:g3:...`): no label before it (the operator's G3-D trial, 2026-10-28)
    lines = [f"approved: {out['approval_ref']}; consent set {out['consent_set_ref']}", "submitted; the receipt:"]
    lines += [f"  {r.get('intent_ref')}: {r.get('admission_state')} "
              f"{r.get('reason_code') or 'effect ' + str(r.get('effect_state'))}" for r in receipt["results"]]
    if out["note"]:
        lines.append(out["note"])
    return "\n".join(lines)
