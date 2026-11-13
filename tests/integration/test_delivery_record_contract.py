"""Six-condition delivery-record oracle, with independent payload checks and a plant for every condition/member.

The oracle observes the test project's .aew paths/bytes, not arbitrary host filesystem I/O or a proof of model
understanding. Normal successful writes, corruption recovery and process custody have separate real-boundary tests.
Synthetic mutations below test the oracle, not reachability of a forged owner fact. Positive cases use real broker
reads and real run results. Declared-path overrides exist only to show that a future member cannot waive local-only.
"""

from __future__ import annotations

import json
import re

import pytest
import test_lead_relayed_reads as R
from aewflow import create_planned_ticket
from harness_conformance import FakeOpenCodeDriver, supervisor_gone
from test_coordination_store import world
from test_message_send import broker

from aew.engine.api import Engine
from aew.harness import bridge, lead_broker, runlog

TOLD = "local/lead/told-messages.json"
LOCKS = {"local/lead/told-messages.lock", "local/lead/told-messages.lock.queue"}
MID = "MSG-INV-0001-2"


def snapshot(root):
    return {p.relative_to(root).as_posix() + ("/" if p.is_dir() else ""):
            None if p.is_dir() else p.read_bytes() for p in root.rglob("*")}


def parsed(raw):
    try:
        return json.loads(raw) if isinstance(raw, bytes) else None
    except (ValueError, RecursionError):
        return None


def valid_told(doc):
    return (isinstance(doc, dict) and set(doc) == {"generation", "messages"}
            and type(doc["generation"]) is int and doc["generation"] >= 0 and isinstance(doc["messages"], list)
            and all(isinstance(mid, str) and re.fullmatch(r"MSG-INV-[0-9]+-[1-9][0-9]*", mid)
                    for mid in doc["messages"])
            and doc["messages"] == sorted(set(doc["messages"])))


def findings(before, after, *, run=None, generation=1, returned=frozenset(), actor="broker",
             sequence=None, ended=False, declared=None):
    """The exact destination list is necessary but not sufficient: every member also remains local-only."""
    allowed = R.delivery_records(run, messages=True) if declared is None else set(declared)
    directories = {"/".join(path.split("/")[:n]) + "/" for path in allowed
                   for n in range(1, len(path.split("/")))}
    changed = {p for p in before.keys() | after.keys()
               if before.get(p) != after.get(p) or (p in before) != (p in after)}
    out = set()
    if changed and actor != "broker":
        out.add("C1: delivery record written by read process")
    for path in changed:
        if not path.startswith("local/"):
            out.add("C6: delivery record outside local")
        if path.endswith("/"):
            if path not in directories or after.get(path) is not None or path not in after:
                out.add("C3: undeclared directory")
            continue
        if path not in allowed:
            out.add("C3: undeclared destination")
            continue
        if path not in after:
            out.add("C4: delivery record deleted")
            continue
        if path == TOLD:
            doc, old = parsed(after[path]), parsed(before.get(path))
            if not valid_told(doc):
                out.add("C5: invalid told payload")
                continue
            if doc["generation"] != generation or valid_told(old) and old["generation"] > generation:
                out.add("C4: generation regressed or mismatched")
            previous = set(old["messages"]) if valid_told(old) and old["generation"] == generation else set()
            now = set(doc["messages"])
            if not previous <= now:
                out.add("C4: same-generation IDs dropped")
            if not now - previous <= set(returned) or path not in before and not returned:
                out.add("C2: non-result or unreturned identity")
        elif path in LOCKS or path.endswith("/" + runlog.END_RETURNED_FILE):
            if after[path] != b"":
                out.add("C5: nonempty flag or synchronization file")
            if path not in LOCKS and not ended:
                out.add("C2: unreturned end")
        elif path.endswith("/" + runlog.RETURNED_FILE):
            doc, old = parsed(after[path]), parsed(before.get(path))
            if not isinstance(doc, dict) or set(doc) != {"trigger_seq"} or type(doc["trigger_seq"]) is not int \
                    or doc["trigger_seq"] < 0:
                out.add("C5: invalid sequence payload")
                continue
            if sequence is None or doc["trigger_seq"] > sequence:
                out.add("C2: unreturned sequence")
            if (isinstance(old, dict) and type(old.get("trigger_seq")) is int
                    and doc["trigger_seq"] < old["trigger_seq"]):
                out.add("C4: sequence regressed")
    return out


@pytest.mark.parametrize("sealed", [False, True])
def test_real_broker_message_receipts_satisfy_all_six_conditions_and_leave_all_other_bytes_unchanged(tmp_path, sealed):
    w = world(tmp_path)
    mid = w.reply(w.send()["message"]["id"])["message"]["id"]
    if sealed:
        w.lead("invoke_cancel", invocation=w.inv, reason="sealed receipt oracle")
    with broker(w) as b:
        before = snapshot(w.root / ".aew")
        answer = bridge.call("lead.read", {"argv": ["status", "--json"], "cwd": str(w.root)},
                             endpoint=b.server.address, key=b.server.key_hex)
        assert answer["exit"] == 0
        assert b.server.drain(10)
        carried = w.e.message_result_ids(json.loads(answer["stdout"]))
        assert carried == [mid]
        after = snapshot(w.root / ".aew")
        assert findings(before, after, generation=b.generation, returned=set(carried)) == set()
        assert set(after) - set(before) == {"local/lead/", TOLD, *LOCKS}


def test_real_run_sequence_and_end_records_satisfy_the_same_class_oracle(tmp_path):
    lab = FakeOpenCodeDriver().create_lab(tmp_path)
    try:
        lab.script("default", [{"do": "exit"}])
        run = lab.lead("work", "assign", create_planned_ticket(lab.project, tmp_path), "--launch")["launch"]["run"]
        lab.wait(run)
        record = lab.record(run)
        lab.until(lambda: supervisor_gone(record), 30, "the supervisor to finish all record writes")
        directory = runlog.run_dir(lab.aew_root, run)
        # Disposable delivery-state loss is allowed; derive the recreated records from the actual ended-run result.
        for name in (runlog.RETURNED_FILE, runlog.END_RETURNED_FILE):
            (directory / name).unlink(missing_ok=True)
        result = Engine.discover(lab.root).harness_wait(run, timeout=0, triggers=True, record_return=False)
        before = snapshot(lab.aew_root)
        lead_broker.record_delivery(lab.aew_root, [run], json.dumps(result))
        after = snapshot(lab.aew_root)
        seq = result["runs"][run]["trigger_seq"]
        assert seq > 0
        assert findings(before, after, run=run, sequence=seq, ended=True) == set()
        assert set(after) - set(before) == R.delivery_records(run)
    finally:
        lab.cleanup()


@pytest.mark.parametrize(("plant", "code"), [
    ("read_process", "C1"), ("non_result", "C2"), ("omitted", "C2"), ("wrong_path", "C3"),
    ("drop_id", "C4"), ("regress_generation", "C4"), ("overwrite_newer", "C4"),
    ("body_field", "C5"), ("credential_field", "C5"), ("invalid_id", "C5"), ("boolean_generation", "C5")])
def test_each_planted_violation_of_the_message_record_is_rejected(plant, code):
    def raw(generation, messages, **extra):
        return json.dumps({"generation": generation, "messages": messages, **extra}).encode()

    before, after = {}, {TOLD: raw(1, [MID])}
    actor, returned = "broker", {MID}
    if plant == "read_process":
        actor = "read"
    elif plant == "non_result":
        returned = set()
    elif plant == "omitted":
        after[TOLD] = raw(1, [MID, "MSG-INV-9999-1"])
    elif plant == "wrong_path":
        after = {"local/lead/wrong.json": after[TOLD]}
    elif plant == "drop_id":
        before, after = after, {TOLD: raw(1, [])}
    elif plant == "regress_generation":
        before, after = after, {TOLD: raw(0, [MID])}
    elif plant == "overwrite_newer":
        before = {TOLD: raw(2, [MID])}
    elif plant == "body_field":
        after[TOLD] = raw(1, [MID], body="worker text must not be in this record")
    elif plant == "credential_field":
        after[TOLD] = raw(1, [MID], token="synthetic, not a credential")
    elif plant == "invalid_id":
        after[TOLD] = raw(1, ["not-a-message"])
    elif plant == "boolean_generation":
        after[TOLD] = raw(True, [MID])
    assert any(f.startswith(code + ":") for f in findings(before, after, returned=returned, actor=actor))


@pytest.mark.parametrize("member", [TOLD, *sorted(LOCKS),
    "local/harness/runs/R-INV-0001-1/" + runlog.RETURNED_FILE,
    "local/harness/runs/R-INV-0001-1/" + runlog.END_RETURNED_FILE])
def test_no_member_can_waive_local_only_even_if_its_wrong_destination_is_declared(member):
    outside = "work/escaped/" + member.rsplit("/", 1)[1]
    # Widening a declaration cannot waive condition 6, including for old seq/flag and synchronization members.
    found = findings({}, {outside: b""}, declared={outside})
    assert "C6: delivery record outside local" in found


@pytest.mark.parametrize("member", ["progress.returned.json", "progress.end-returned"])
def test_old_members_reject_body_payloads_wrong_result_facts_and_regression(member):
    run = "R-INV-0001-1"
    path = f"local/harness/runs/{run}/{member}"
    invalid = b'{"trigger_seq":2,"body":"no bodies"}' if member.endswith("json") else b"body"
    assert "C5" in {f[:2] for f in findings({}, {path: invalid}, run=run, sequence=2, ended=True)}
    if member.endswith("json"):
        assert "C2" in {f[:2] for f in findings({}, {path: b'{"trigger_seq":3}'}, run=run, sequence=2)}
        assert "C4" in {f[:2] for f in findings({path: b'{"trigger_seq":2}'}, {path: b'{"trigger_seq":1}'},
                                               run=run, sequence=2)}
    else:
        assert "C2" in {f[:2] for f in findings({}, {path: b""}, run=run, ended=False)}


def test_a_real_wrong_path_writer_plant_is_caught_without_widening_the_destination_list(tmp_path, monkeypatch):
    from aew.harness import told_messages

    w = world(tmp_path)
    mid = w.reply(w.send()["message"]["id"])["message"]["id"]
    with broker(w) as b:
        before = snapshot(w.root / ".aew")
        monkeypatch.setattr(told_messages, "REL", "work/escaped-told.json")
        answer = bridge.call("lead.read", {"argv": ["status", "--json"], "cwd": str(w.root)},
                             endpoint=b.server.address, key=b.server.key_hex)
        assert answer["exit"] == 0
        assert b.server.drain(10)
        found = findings(before, snapshot(w.root / ".aew"), generation=b.generation, returned={mid})
        assert "C6: delivery record outside local" in found
        assert "C3: undeclared destination" in found
