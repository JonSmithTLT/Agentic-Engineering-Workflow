"""Offline re-evaluation under messaging amendment 3, addendum 1, revision 2.

No binary path, server, model, socket or subprocess is used here. Original records remain immutable; the result is
another core.document with the original runtime provenance and explicit re-evaluation provenance. Only the ruled
post-admission predicate changes. Other required check failures cannot be promoted.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import aew

from . import core
from .opencode import OpenCodePack

SOURCE_REVISION = "e1be99c878ed321eb11d029e842af0ea33d81d6c"
SOURCE_DIGESTS = frozenset({"97b6ce4147051e1de6099a689e97635acb64b753ea392b6058194359b274efc4",
                            "29ef41ae1ce5e73cc8c6b2dd1a03b379b48eacc3e2e0bb4543ae937c7a432ef2"})
RULING_DIGEST = "8bfc9c2dd9a16008b0fda92db878db704106ff2b47b839d116e32e7f1cabc65b"
ADDENDUM_DIGEST = "f91361861601e084d561f4b96ee513508c0e4e6b194f3b028e146539c13c5ef5"
PREDICATE = "post-admission-retry-fields/v2"
REQUIRED = ("api.openapi", "api.steer_running_turn", "api.queue_until_turn_end",
            "messaging.steer_boundary", "messaging.queue_boundary", "messaging.prompt_identity",
            "messaging.held_resume", "messaging.session_loss", "messaging.wait_binding", "messaging.shell_timeout")
RETIRED = ("admitted_created_time_preserved", "changed_admitted_returns_original", "admitted_delivery_preserved")


def fields(value: Any) -> dict[str, Any] | None:
    """Exactly the response fields AEW may use; deliberately never access response time or delivery mode."""
    if not isinstance(value, dict) or not isinstance(value.get("payload"), dict):
        return None
    payload = value["payload"]
    if not all(key in value for key in ("id", "sessionID")) or not all(
            key in payload for key in ("text", "metadata")):
        return None
    return {"id": value["id"], "session": value["sessionID"], "text": payload["text"],
            "metadata": payload["metadata"]}


def admitted_facts(mode: str, raw: Any, observed: dict[str, Any]) -> dict[str, bool]:
    """Compare retained envelopes with the script's sent fields. Original first_identity_valid binds the captured
    first session to the session created by the script; admitted_once is its message-list count and
    metadata_round_trip its REST GET evidence,
    not an inference from a POST's 200. The source digest binds that earlier measurement."""
    raw = raw if isinstance(raw, dict) else {}
    first, retry = fields(raw.get("first")), fields(raw.get("admitted_retry"))
    expected = {"id": "msg_hq_identity_" + mode, "text": "HQ_IDENTITY_" + mode,
                "metadata": {"aew_probe": "identity", "ordinal": 1}}
    first_valid = (first is not None and observed.get(mode + ".first_identity_valid") is True
                   and isinstance(first["session"], str) and bool(first["session"])
                   and all(first[key] == value for key, value in expected.items()))
    retry_valid = bool(first_valid and retry == first and raw.get("admitted_retry_status") == 200)
    return {mode + ".first_identity_valid": bool(first_valid), mode + ".admitted_identity_valid": retry_valid,
            mode + ".changed_admitted_keeps_identity": bool(first_valid and
                fields(raw.get("admitted_changed")) == first and raw.get("admitted_changed_status") == 200),
            mode + ".duplicate_admitted": retry_valid and observed.get(mode + ".admitted_once") is True
            and observed.get(mode + ".metadata_round_trip") is True}


def identity_outcome(observed: dict[str, Any], raw: Any) -> core.Outcome:
    """The amended active predicate; the replaced whole-envelope facts remain observations, not hidden or flipped."""
    from .messaging import IDENTITY_FACTS

    active = {key: value for key, value in observed.items() if key.rsplit(".", 1)[-1] not in RETIRED}
    raw = raw if isinstance(raw, dict) else {}
    for mode in ("steer", "queue"):
        active.update(admitted_facts(mode, raw.get(mode), observed))
    required = [mode + "." + key for mode in ("steer", "queue") for key in IDENTITY_FACTS if key not in RETIRED]
    required += [mode + ".changed_admitted_keeps_identity" for mode in ("steer", "queue")]
    failed = [key for key in required if active.get(key) is not True]
    return core.Outcome(core.FAIL if failed else core.PASS, {
        "messaging.prompt_identity": active, "observation.prompt_identity": copy.deepcopy(observed),
        "measurement.prompt_identity": copy.deepcopy(raw)}, failed)


def evaluate(doc: dict[str, Any], *, source_digest: str, pack: OpenCodePack,
             evaluator_revision: str | None) -> core.Record:
    if source_digest not in SOURCE_DIGESTS or doc.get("schema") != core.SCHEMA:
        raise ValueError("not the retained additional qualification record")
    if (doc.get("harness"), doc.get("version"), doc.get("platform"), doc.get("aew_revision")) != (
            "opencode", "2.2.6", "linux", SOURCE_REVISION):
        raise ValueError("the ruling covers only the retained 2.2.6 Linux measurement")
    if doc.get("network") != ("blocked: run under bwrap --unshare-net "
                              "(verified: loopback only, no external route, egress denied)"):
        raise ValueError("retained measurement lacks verified isolation")
    rows = copy.deepcopy(doc["checks"])
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)) or not set(REQUIRED) <= set(ids):
        raise ValueError("missing or duplicate required qualification checks")
    selected = [row for row in rows if row["status"] != core.SKIPPED]
    if {row["id"] for row in selected} != set(REQUIRED):
        raise ValueError("the retained selection must contain exactly the ten approved checks")
    facts = copy.deepcopy(doc["facts"])
    original = facts.get("messaging.prompt_identity")
    if not isinstance(original, dict):
        raise ValueError("missing original prompt identity observations")
    outcome = identity_outcome(original, facts.get("measurement.prompt_identity"))
    facts.update(outcome.facts)
    for row in rows:
        if row["id"] == "messaging.prompt_identity":
            row.update(status=outcome.status, notes=outcome.notes, facts=sorted(outcome.facts))
    facts["qualification.reevaluation"] = {
        "predicate": PREDICATE, "runtime_executed": False, "source_digest": source_digest,
        "source_revision": SOURCE_REVISION, "source_verdict": doc["verdict"],
        "evaluator_revision": evaluator_revision, "required_checks": list(REQUIRED),
        "ruling": {"title": "Lead ruling, 2026-11-10: post-admission retry premise on OpenCode 2.2.6",
                   "digest": RULING_DIGEST, "sections": [1, 2, 3, 4, 5, 7]},
        "addendum": {"title": "Messaging amendment 3, addendum 1: retry fields", "revision": 2,
                     "digest": ADDENDUM_DIGEST, "parts": [2, 4]},
        "retired_gate_facts": list(RETIRED), "windows_runtime": "NOT RUN; capability GAP"}
    return core.Record(harness=doc["harness"], version=doc["version"], binary_sha256=doc["binary_sha256"],
                       platform=doc["platform"], checks=rows,
                       capabilities=core.capability_report(pack.declared(), rows), facts=facts,
                       unmeasured=copy.deepcopy(doc["unmeasured"]), started=doc["started"], seconds=doc["seconds"],
                       network=doc["network"], aew_revision=doc["aew_revision"])


def run(source: Path, ruling: Path, *, out: Path, fixtures: Path, write_pin: bool = False) -> int:
    checkout_src = Path(__file__).resolve().parents[2] / "src"
    if not aew.__file__ or Path(aew.__file__).resolve() != checkout_src / "aew" / "__init__.py":
        raise ValueError("imported aew is not from this checkout; set PYTHONPATH to this checkout's src")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest not in SOURCE_DIGESTS:
        raise ValueError("source bytes do not match the retained additional record")
    if hashlib.sha256(ruling.read_bytes()).hexdigest() != ADDENDUM_DIGEST:
        raise ValueError("ruling bytes do not match the cited addendum revision 2")
    if out.resolve() == source.resolve().parent or (out.exists() and any(out.iterdir())):
        raise ValueError("use a fresh output directory, not the retained record's directory")
    pack = OpenCodePack(fixtures, platform="linux")
    record = evaluate(json.loads(raw), source_digest=digest, pack=pack, evaluator_revision=core.aew_revision())
    _, pinned = pack.pinned(fixtures)
    diff = core.fact_diff(record.facts, pinned, unmeasured=record.unmeasured, checks=record.checks)
    fixture_rows = core.fixture_report(pack, record.version, record.facts, fixtures)
    adopt = pack.adoptable(record.facts, pinned)
    doc = core.document(record, diff, fixture_rows, adopt)
    out.mkdir(parents=True, exist_ok=True)
    (out / "record.json").write_bytes(core.dump(doc))
    (out / "report.txt").write_text(core.report(record, diff, fixture_rows, adopt), encoding="utf-8")
    (out / "diff.txt").write_text("\n".join(diff.lines()) + "\n", encoding="utf-8")
    status = core.exit_code(record, diff)
    if write_pin and status == core.EXIT_OK:
        name = f"messaging-{record.version}.json"
        made, _ = pack.render(record.version, record.facts, fixtures)[name]
        if made is None:
            raise ValueError("re-evaluation produced no semantic pin")
        path = fixtures / name
        if path.exists() and path.read_bytes() != made:
            raise ValueError("refusing to overwrite a different existing semantic pin")
        path.write_bytes(made)
    print(f"Offline re-evaluation: {doc['verdict']['binary']}; no runtime executed; source {digest}")
    for row in record.checks:
        if row["id"] in REQUIRED:
            print(f"{row['id']}: {row['status']}" + (f" ({'; '.join(row['notes'])})" if row["notes"] else ""))
    return status
