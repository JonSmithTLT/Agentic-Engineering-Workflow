"""The work-item fact issuer's core against stores the real engine wrote (STG-04 WIS-A: WIS-02 to WIS-06, WIS-09).

Every WIS-02 outcome is made on a scratch store created, committed to and compacted by the engine, then edited as the
gate's WIS-Q04 edits it, and each is checked three ways: the case that must give it, a near miss that must not, and
the case where the file is missing. Latching is checked both ways: each latching outcome stays latched across a
restart until root re-anchors, and each non-latching one clears on the next good read. ``wis-cases.json`` (the adopted
reference's cases, carried unchanged by A-36) is ported: its outcomes, case by case, and its attestations' derivations
byte for byte. What the kernel shows of the bound directory is the test's ``View``; the real identity rule and a real
bind are tested in ``test_wis_identity.py`` and ``tests/integration/test_wis_view.py``.
"""

from __future__ import annotations

import base64
import copy
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

import wis_store as S  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402
from log_fixture import extend_log  # noqa: E402

from aew.engine import log_compact, outbox  # noqa: E402
from aew.engine.store import deserialize_control, serialize_control  # noqa: E402
from aew.util import dump_yaml  # noqa: E402
from aew_wis import engine_rules as R  # noqa: E402
from aew_wis import keys as K  # noqa: E402
from aew_wis import wire as W  # noqa: E402
from aew_wis.identity import Identity  # noqa: E402
from aew_wis.issuer import AnchorRefused, Issuer, held_path, write_atomically  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wis"
SCHEMA = json.loads((FIXTURES / "wis-issuer.schema.json").read_text(encoding="utf-8"))
CASES = json.loads((FIXTURES / "wis-cases.json").read_text(encoding="utf-8"))
MIN = timedelta(minutes=1)


def valid(defn: str, body: dict) -> list[str]:
    v = Draft202012Validator({"$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{defn}"}, format_checker=FormatChecker())
    return [e.message for e in v.iter_errors(body)]


def control_path(store) -> Path:
    return store.root / R.CONTROL_REL


def rewrite_control(store, mutate) -> None:
    """The control file rewritten with a consistent checksum trailer: a store writer's edit, not the engine's commit."""
    path = control_path(store)
    state = deserialize_control(path.read_bytes(), source="test")
    mutate(state)
    path.write_bytes(serialize_control(state))


def log_file(store, revision: int) -> Path:
    return store.root / outbox.record_path(revision)


def record(store, revision: int) -> dict:
    return outbox.read_record(store.root, revision)


def started(tmp_path, commits: int = 1):
    """A store anchored at revision 0 by root, ``commits`` engine commits, and an issuer that has read it."""
    store = S.init(tmp_path / "proj")
    iss = S.issuer(store, tmp_path / "state")
    for _ in range(commits):
        S.commit(store, S.WORK)
    assert iss.read(S.T0) == "OK"
    return store, iss


def restarted(iss: Issuer, store, tmp_path, **kw) -> Issuer:
    """The same issuer as a new process: the same anchor and state directory, its held state read back."""
    return S.issuer(store, tmp_path / "state", view=iss.view, anchor=iss.anchor, signer=iss.signer, **kw)


# ---------------------------------------------------------------------------------------------- the positive

def test_an_issuer_attests_the_engines_committed_state_by_the_wis_fact_rule(tmp_path):
    store, iss = started(tmp_path)
    a = iss.latest
    assert valid("Attestation", a) == [] and valid("Anchor", iss.anchor) == []
    assert (a["revision"], a["h"], a["control_sha256"]) == (1, record(store, 1)["h"],
                                                            W.sha(control_path(store).read_bytes()))
    assert a["store_ref"] == "store:" + S.INSTANCE and a["wis_epoch"] == W.epoch_of(iss.anchor)
    assert W.parse_time(a["valid_until"]) - W.parse_time(a["issued_at"]) == timedelta(minutes=15)
    assert a["facts"] == {
        "ticket:one": {"work_id": "ticket:one", "kind": "ticket", "revision": "plan-1", "state": "READY",
                       "blocked_by": [], "cause": "unknown", "axis_state": "ok"},
        "ticket:two": {"work_id": "ticket:two", "kind": "ticket", "revision": "plan-2", "state": "BLOCKED",
                       "blocked_by": ["ticket:one"], "cause": "dependency", "axis_state": "blocked"}}


def test_the_ported_cases_attestation_has_the_reference_shape_and_facts(tmp_path):
    """``wis-cases.json`` P1 and P2: the same fields, the same facts (the reference's labelled ``revision:one`` is the
    engine's ``plan-1``), 15 minutes' validity, and a renewal at +11 minutes with the same revision, h and bytes."""
    store, iss = started(tmp_path)
    ref, ours = CASES["P1"]["attestation"], iss.latest
    assert set(ours) == set(ref)
    for wid, fact in ref["facts"].items():
        assert {k: v for k, v in ours["facts"][wid].items() if k != "revision"} == {
            k: v for k, v in fact.items() if k != "revision"}
    assert iss.read(S.T0 + 5 * MIN) == "OK" and iss.latest is ours  # more than the margin left: nothing new
    renewal = CASES["P2"]["renewal_attestation"]
    assert iss.read(S.T0 + 11 * MIN) == "OK"
    hb = iss.latest
    assert hb is not ours and hb["issued_at"] == renewal["issued_at"] and hb["valid_until"] == renewal["valid_until"]
    assert (hb["revision"], hb["h"], hb["control_sha256"]) == (ours["revision"], ours["h"], ours["control_sha256"])


def test_the_issuer_derives_proof_ref_signature_and_epoch_by_the_references_rules_byte_for_byte():
    """The reference's own attestations, re-derived with the wire's functions and the reference's labelled key."""
    key = S.HmacKey()
    for case in (CASES["P1"]["attestation"], CASES["P2"]["renewal_attestation"]):
        unsigned = {k: v for k, v in case.items() if k not in ("proof_ref", "signature")}
        assert W.seal(unsigned, key.sign) == case
        assert case["key_id"] == key.key_id
    assert W.epoch_of(CASES["P1"]["anchor"]) == CASES["P1"]["attestation"]["wis_epoch"]


def test_the_reference_control_file_fails_the_engines_checksum_rule():
    """WIS-A finding F-3: the reference hashes the control body without its final newline; the engine (and so the
    issuer) with it. The carried store files are therefore not readable as they are, and the outcomes are ported."""
    raw = base64.b64decode(CASES["P1"]["store_files_b64"]["control.yaml"])
    with pytest.raises(R.IntegrityError, match="checksum mismatch"):
        R.control_body(raw, source="the reference's control.yaml")


# ---------------------------------------------------------------------------------------------- WIS-02, outcome by outcome

def test_checksum_invalid_right_wrong_and_missing_and_it_does_not_latch(tmp_path):
    store, iss = started(tmp_path)
    good = control_path(store).read_bytes()
    control_path(store).write_bytes(good.replace(b"READY", b"DONE_"))
    assert iss.read(S.T0) == "CHECKSUM_INVALID" and iss.head["state"] == W.ANCHORED
    control_path(store).write_bytes(good.rsplit(b"# aew-checksum", 1)[0])  # the trailer missing
    assert iss.read(S.T0) == "CHECKSUM_INVALID"
    control_path(store).write_bytes(good)  # the near miss: the engine's own bytes
    assert iss.read(S.T0) == "OK"
    control_path(store).unlink()  # the file missing is unreadable, not a checksum failure
    assert iss.read(S.T0) == "STORE_UNREADABLE" and iss.head["state"] == W.ANCHORED


def test_store_unreadable_right_wrong_and_missing_renews_nothing_and_does_not_latch(tmp_path):
    store, iss = started(tmp_path)
    first = iss.latest
    iss.view.unavailable = True  # the mount table or statx cannot be read: no evidence of a replacement
    assert iss.read(S.T0 + 11 * MIN) == "STORE_UNREADABLE" and iss.latest is first
    iss.view.unavailable = False
    good = control_path(store).read_bytes()
    body = good.decode().rsplit("# aew-checksum", 1)[0]
    garbled = (body.replace("revision: 1\n", "revision: [1\n", 1)).encode()
    control_path(store).write_bytes(garbled + f"# aew-checksum sha256:{W.sha(garbled)}\n".encode())
    assert iss.read(S.T0 + 11 * MIN) == "STORE_UNREADABLE"  # a consistent trailer over YAML that does not parse
    control_path(store).write_bytes(good)
    rewrite_control(store, lambda st: st["work"]["ticket:one"].update(kind="widget"))
    assert iss.read(S.T0 + 11 * MIN) == "STORE_UNREADABLE"  # a unit the fact rule cannot derive
    control_path(store).write_bytes(good)
    assert iss.read(S.T0 + 11 * MIN) == "OK" and iss.latest is not first and iss.head["state"] == W.ANCHORED
    witnessed = iss.witness(iss.latest["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0 + 11 * MIN)
    assert witnessed[1]["head"]["last_read"] == "OK"


def test_revision_gap_right_wrong_and_missing_never_latches(tmp_path):
    store, iss = started(tmp_path)
    S.commit(store)
    S.commit(store)
    saved = log_file(store, 2).read_bytes()
    log_file(store, 2).unlink()
    assert iss.read(S.T0) == "REVISION_GAP" and iss.head["revision"] == 1
    assert all(iss.read(S.T0 + m * MIN) == "REVISION_GAP" for m in (1, 30, 60)) and iss.head["state"] == W.ANCHORED
    assert iss.gap_age(S.T0 + 60 * MIN) == timedelta(minutes=60)
    log_file(store, 2).write_bytes(saved)
    assert iss.read(S.T0 + 61 * MIN) == "OK" and iss.head["revision"] == 3 and iss.gap_age(S.T0) is None
    log_file(store, 3).unlink()  # the near miss: the newest record's log copy may lag; control.yaml carries it
    assert iss.read(S.T0 + 61 * MIN) == "OK"


def test_the_held_heads_own_record_must_be_there_once_a_newer_commit_exists(tmp_path):
    store, iss = started(tmp_path, commits=2)
    S.commit(store)
    log_file(store, 2).unlink()
    assert iss.read(S.T0) == "REVISION_GAP" and iss.head["state"] == W.ANCHORED


def test_chain_broken_right_wrong_and_it_latches_until_root_re_anchors(tmp_path):
    store, iss = started(tmp_path)
    S.commit(store)
    S.commit(store)
    good = log_file(store, 2).read_bytes()
    rec = record(store, 2)
    log_file(store, 2).write_text(dump_yaml(dict(rec, op="edited")), encoding="utf-8")
    assert iss.read(S.T0) == "CHAIN_BROKEN" and iss.head["state"] == W.FORKED
    log_file(store, 2).write_bytes(good)
    assert iss.read(S.T0) == "CHAIN_FORK"  # put back as it was, still latched
    assert restarted(iss, store, tmp_path).read(S.T0 + MIN) == "CHAIN_FORK"  # and across a restart
    re = S.issuer(store, tmp_path / "state", view=iss.view, anchor=S.anchor_of(store, at=S.T0 + 2 * MIN))
    assert re.read(S.T0 + 3 * MIN) == "OK" and re.wis_epoch != iss.wis_epoch  # only root's re-anchor clears it


def test_state_mismatch_a_newest_record_that_chains_but_differs_from_its_log_copy(tmp_path):
    store, iss = started(tmp_path)
    S.commit(store)
    h1 = record(store, 1)["h"]

    def alternate(st):
        alt = {k: v for k, v in st["last_transition"].items() if k != "h"} | {"op": "other"}
        st["last_transition"] = dict(alt, h=outbox.transition_hash(h1, alt))

    rewrite_control(store, alternate)
    assert iss.read(S.T0) == "STATE_MISMATCH" and iss.head["state"] == W.FORKED
    assert restarted(iss, store, tmp_path).read(S.T0 + MIN) == "CHAIN_FORK"


def test_state_mismatch_wrong_a_newest_record_equal_to_its_log_copy_reads_ok(tmp_path):
    store, iss = started(tmp_path)
    S.commit(store)
    assert log_file(store, 2).exists() and iss.read(S.T0) == "OK"


def test_chain_fork_a_rewritten_past_at_the_held_head(tmp_path):
    store, iss = started(tmp_path, commits=3)
    first = iss.latest

    def rewrite(st):  # revision 3's record rewritten, chained consistently from revision 2
        rec = {k: v for k, v in st["last_transition"].items() if k != "h"} | {"op": "rewritten"}
        st["last_transition"] = dict(rec, h=outbox.transition_hash(record(store, 2)["h"], rec))
        log_file(store, 3).write_text(dump_yaml(st["last_transition"]), encoding="utf-8")

    rewrite_control(store, rewrite)
    assert iss.read(S.T0) == "CHAIN_FORK" and iss.head["state"] == W.FORKED
    assert iss.current(first, S.T0) is False
    assert iss.witness(first["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0)[1]["head"]["state"] == W.FORKED
    assert valid("WitnessResponse", iss.witness(first["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0)[1]) == []


def test_chain_fork_a_rewritten_past_followed_by_a_newer_commit(tmp_path):
    store, iss = started(tmp_path, commits=3)
    rec3 = record(store, 3)
    alt = {k: v for k, v in rec3.items() if k != "h"} | {"op": "rewritten"}
    log_file(store, 3).write_text(dump_yaml(dict(alt, h=outbox.transition_hash(record(store, 2)["h"], alt))),
                                  encoding="utf-8")
    S.commit(store)  # revision 4 chains from the engine's own revision 3 (in control.yaml), not the rewritten file
    assert iss.read(S.T0) == "CHAIN_FORK"


def test_chain_fork_history_that_went_backwards_and_a_head_that_is_not_the_anchor(tmp_path):
    store, iss = started(tmp_path, commits=2)
    rec1 = record(store, 1)
    rewrite_control(store, lambda st: st.update(revision=1, last_transition=rec1))
    assert iss.read(S.T0) == "CHAIN_FORK"
    other = S.init(tmp_path / "other")
    wrong = S.issuer(other, tmp_path / "state-other", anchor=dict(S.anchor_of(other), h="ab" * 32))
    assert wrong.read(S.T0) == "CHAIN_FORK"  # the store's head is not the one root anchored


def test_chain_fork_the_control_bytes_changed_under_the_same_revision(tmp_path):
    store, iss = started(tmp_path)
    rewrite_control(store, lambda st: st["work"]["ticket:two"].update(blocked_by=[]))  # in no record: h unchanged
    assert iss.read(S.T0 + 11 * MIN) == "CHAIN_FORK"
    assert iss.latest["facts"]["ticket:two"]["blocked_by"] == ["ticket:one"]  # the change is never attested


def test_commits_the_issuer_was_not_woken_for_are_attested_on_its_next_read(tmp_path):
    store, iss = started(tmp_path)
    S.commit(store)
    S.commit(store, dict(S.WORK, **{"ticket:one": S.unit("BLOCKED", plan=1)}))
    assert iss.read(S.T0 + 30 * timedelta(seconds=1)) == "OK" and iss.latest["revision"] == 3
    assert iss.latest["facts"]["ticket:one"]["state"] == "BLOCKED"


def test_store_replaced_by_the_root_field_and_by_identity_latches(tmp_path):
    """WIS-02's first two rows, as the kernel would show them: a rename of the store or an ancestor, a deletion, a
    directory replaced at the path (another inode, or the same inode number with another birth time), and a device
    number that moved with no UUID to say it is the same file system. The near misses read OK."""
    fs = S.IDENTITY.fs_path
    cases = {
        "an ancestor renamed": Identity(S.IDENTITY.fs_id, S.IDENTITY.ino, S.IDENTITY.btime, fs.replace(".aew/", ".aew-orphan/")),
        "the store renamed itself": Identity(S.IDENTITY.fs_id, S.IDENTITY.ino, S.IDENTITY.btime, fs + "-moved"),
        "deleted": Identity(S.IDENTITY.fs_id, S.IDENTITY.ino, S.IDENTITY.btime, fs + "//deleted"),
        "another inode at the path": Identity(S.IDENTITY.fs_id, 7002, S.IDENTITY.btime, fs),
        "the inode number reused, another birth time": Identity(S.IDENTITY.fs_id, S.IDENTITY.ino, S.IDENTITY.btime + 1, fs),
        "another file system": Identity("uuid:00000000-0000-0000-0000-000000000000", S.IDENTITY.ino, S.IDENTITY.btime, fs),
        "a dev: identity whose device moved": Identity("dev:253:3", S.IDENTITY.ino, S.IDENTITY.btime, fs),
    }
    for n, (label, ident) in enumerate(cases.items()):
        root = tmp_path / str(n)
        store, iss = started(root)
        iss.view.identity = ident
        assert iss.read(S.T0 + MIN) == "STORE_REPLACED", label
        assert iss.head["state"] == W.FORKED and not iss.current(iss.latest, S.T0 + MIN), label
        assert restarted(iss, store, root).read(S.T0 + 2 * MIN) == "CHAIN_FORK", label
    store, iss = started(tmp_path / "near")
    iss.view.identity = Identity(S.IDENTITY.fs_id, S.IDENTITY.ino, S.IDENTITY.btime, fs)  # an equal identity
    assert iss.read(S.T0 + MIN) == "OK"


def test_an_issuer_started_on_a_substitute_refuses_it_and_only_root_re_anchors_it(tmp_path):
    store, iss = started(tmp_path)
    substitute = S.View(store.root, Identity(S.IDENTITY.fs_id, 9999, 1, S.IDENTITY.fs_path))
    fresh = S.issuer(store, tmp_path / "state", view=substitute, anchor=iss.anchor)
    assert fresh.read(S.T0 + 20 * MIN) == "STORE_REPLACED"
    root = S.issuer(store, tmp_path / "state", view=substitute, anchor=S.anchor_of(store, substitute.identity,
                                                                                  at=S.T0 + 30 * MIN))
    assert root.read(S.T0 + 31 * MIN) == "OK" and root.wis_epoch != iss.wis_epoch
    assert valid("Anchor", root.anchor) == [] and valid("Anchor", dict(root.anchor, store_btime=None)) == []


# ---------------------------------------------------------------------------------------------- sealed segments

def long_store(tmp_path, to: int = 300):
    """A store anchored at revision 0, with a log long enough for one sealed segment (revisions 0 to 255), overflow
    records among them, as the engine's own fixture writes them; compacted by the engine."""
    store = S.init(tmp_path / "proj")
    iss = S.issuer(store, tmp_path / "state")
    extend_log(store.root, to, overflow_every=7)
    S.commit(store, S.WORK)
    return store, iss


def test_an_issuer_that_missed_a_compaction_reads_through_the_sealed_segments(tmp_path):
    store, iss = long_store(tmp_path)
    result = log_compact.compact(store, window=8)
    assert result["sealed"] and (store.root / outbox.segment_path(0)).exists()
    assert not log_file(store, 100).exists()
    assert iss.read(S.T0) == "OK" and iss.head["revision"] == 301


def test_a_record_whose_file_and_sealed_copy_differ_is_chain_fork(tmp_path):
    store, iss = long_store(tmp_path)
    log_compact.compact(store, window=8)
    sealed = record(store, 100)
    log_file(store, 100).write_text(dump_yaml(dict(sealed, summary="sealed differently")), encoding="utf-8")
    assert iss.read(S.T0) == "CHAIN_FORK" and iss.head["state"] == W.FORKED


def test_a_sealed_segment_that_fails_verification_is_chain_broken(tmp_path):
    store, iss = long_store(tmp_path)
    log_compact.compact(store, window=8)
    seg = store.root / outbox.segment_path(0)
    seg.write_bytes(seg.read_bytes().replace(b"synthetic transition 100", b"synthetic transition 1OO", 1))
    assert iss.read(S.T0) == "CHAIN_BROKEN" and iss.head["state"] == W.FORKED


def test_a_sealed_segment_wrong_case_an_honest_segment_beside_its_files_reads_ok(tmp_path):
    store, iss = long_store(tmp_path)
    log_compact.compact(store, window=8)
    log_file(store, 100).write_text(dump_yaml(record(store, 100)), encoding="utf-8")  # an equal copy beside it
    assert iss.read(S.T0) == "OK"


def test_an_out_of_band_gap_with_no_segment_is_revision_gap_until_root_re_anchors(tmp_path):
    store, iss = started(tmp_path)
    for _ in range(3):
        S.commit(store)
    log_file(store, 3).unlink()
    assert all(iss.read(S.T0 + m * MIN) == "REVISION_GAP" for m in (1, 30, 60)) and iss.head["revision"] == 1
    assert not iss.current(iss.latest, S.T0 + 60 * MIN)  # the last attestation expired
    re = S.issuer(store, tmp_path / "state", view=iss.view, anchor=S.anchor_of(store, at=S.T0 + 60 * MIN))
    assert re.read(S.T0 + 61 * MIN) == "OK"


# ---------------------------------------------------------------------------------------------- held state, latch, restart

def test_every_revision_is_attested_after_a_restart_with_no_gap(tmp_path):
    store, iss = started(tmp_path)
    for _ in range(4):
        S.commit(store)  # committed while the issuer was down
    again = restarted(iss, store, tmp_path)
    assert again.latest == iss.latest and again.head == iss.head  # held state is durable
    assert again.read(S.T0 + MIN) == "OK" and again.latest["revision"] == 5


def test_a_held_state_that_cannot_be_read_is_latched(tmp_path):
    store, iss = started(tmp_path)
    held_path(tmp_path / "state", iss.wis_epoch).write_bytes(b"{not json")
    again = restarted(iss, store, tmp_path)
    assert again.head["state"] == W.FORKED and again.read(S.T0 + MIN) == "CHAIN_FORK"


def test_a_held_state_write_interrupted_before_its_rename_leaves_the_old_state(tmp_path, monkeypatch):
    path = tmp_path / "held.json"
    write_atomically(path, b"old")

    def boom(src, dst):
        raise OSError("the stop signal arrived")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        write_atomically(path, b"new")
    assert path.read_bytes() == b"old"


def test_on_a_stop_signal_the_issuer_attests_nothing_more(tmp_path):
    store, iss = started(tmp_path)
    first = iss.latest
    S.commit(store)
    iss.stopping = True
    iss.read(S.T0 + MIN)
    assert iss.latest is first
    assert iss.witness(first["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0 + MIN)[0] == 503


def test_a_non_latching_outcome_changes_nothing_across_a_restart(tmp_path):
    store, iss = started(tmp_path)
    good = control_path(store).read_bytes()
    control_path(store).write_bytes(good.replace(b"READY", b"DONE_"))
    assert iss.read(S.T0) == "CHECKSUM_INVALID"
    control_path(store).write_bytes(good)
    assert restarted(iss, store, tmp_path).read(S.T0 + MIN) == "OK"


# ---------------------------------------------------------------------------------------------- WIS-06 and the witness

def test_only_the_latest_attestation_is_current_and_a_superseded_one_answers_false(tmp_path):
    store, iss = started(tmp_path)
    first = iss.latest
    assert iss.read(S.T0 + 11 * MIN) == "OK"
    status, body = iss.witness(first["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0 + 11 * MIN)
    assert status == 200 and body["current"] is False and valid("WitnessResponse", body) == []
    status, body = iss.witness(iss.latest["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0 + 11 * MIN)
    assert status == 200 and body["current"] is True and body["head"]["proof_ref"] == iss.latest["proof_ref"]
    later = W.parse_time(iss.latest["valid_until"])
    assert iss.witness(iss.latest["proof_ref"], S.OPERATOR, S.OPERATOR, later)[1]["current"] is False  # expired


@pytest.mark.parametrize("case", ["right", "wrong", "missing"])
def test_each_witness_problem_right_wrong_and_missing(tmp_path, case):
    store = S.init(tmp_path / "proj")
    iss = S.issuer(store, tmp_path / "state")
    S.commit(store, S.WORK)
    pref = "proof:wis:" + "0" * 32
    if case == "right":
        assert iss.witness(pref, S.OPERATOR, S.OPERATOR, S.T0) == (503, W.problem("ISSUER_UNAVAILABLE"))
        iss.read(S.T0)
        assert iss.witness(iss.latest["proof_ref"], 1001, S.OPERATOR, S.T0) == (403, W.problem("PEER_NOT_PERMITTED"))
        assert iss.witness(pref, S.OPERATOR, S.OPERATOR, S.T0) == (404, W.problem("NOT_FOUND"))
    elif case == "wrong":  # the operator, after a read, asking for the latest: no problem at all
        iss.read(S.T0)
        assert iss.witness(iss.latest["proof_ref"], S.OPERATOR, S.OPERATOR, S.T0)[0] == 200
    else:  # nothing named, before and after the first read
        assert iss.witness("", 0, S.OPERATOR, S.T0)[1]["code"] == "PEER_NOT_PERMITTED"
        iss.read(S.T0)
        assert iss.witness("", S.OPERATOR, S.OPERATOR, S.T0)[1]["code"] == "NOT_FOUND"
    for code in W.PROBLEMS:
        assert valid("Problem", W.problem(code)) == []


def test_a_verifier_with_only_the_public_key_checks_live_stamps_across_a_renewal(tmp_path):
    """WIS-Q08's rehearsal with the real Ed25519 key: every untampered attestation verifies under the published key;
    an altered field fails; another store's attestation fails on store_ref and on the epoch from this anchor."""
    (tmp_path / "state").mkdir()
    signer = K.load_signer(tmp_path / "state")
    store = S.init(tmp_path / "proj")
    iss = S.issuer(store, tmp_path / "state", signer=signer)
    S.commit(store, S.WORK)
    iss.read(S.T0)
    iss.read(S.T0 + 11 * MIN)
    publics = K.recorded_publics(tmp_path / "state")
    from cryptography.hazmat.primitives import serialization

    def der(key_id):
        return serialization.load_pem_public_key(publics[key_id]).public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    def verifies(a, store_ref, epoch):
        return (K.verify(der(a["key_id"]), W.signed_bytes(a), a["signature"]) and a["proof_ref"] == W.proof_ref_of(a)
                and a["store_ref"] == store_ref and a["wis_epoch"] == epoch)

    for a in [iss.latest, *iss.held.recent]:
        assert verifies(a, iss.store_ref, W.epoch_of(iss.anchor))
    altered = copy.deepcopy(iss.latest)
    altered["facts"]["ticket:one"]["axis_state"] = "blocked"
    assert not verifies(altered, iss.store_ref, W.epoch_of(iss.anchor))
    other_store = S.init(tmp_path / "proj2")
    other = S.issuer(other_store, tmp_path / "state2", signer=signer, instance=S.OTHER)
    S.commit(other_store, S.WORK)
    other.read(S.T0)
    assert K.verify(der(other.latest["key_id"]), W.signed_bytes(other.latest), other.latest["signature"])
    assert not verifies(other.latest, iss.store_ref, W.epoch_of(iss.anchor))


def test_key_rotation_keeps_old_attestations_verifiable_and_never_current(tmp_path):
    store = S.init(tmp_path / "proj")
    (tmp_path / "state").mkdir()
    signer = K.load_signer(tmp_path / "state")
    iss = S.issuer(store, tmp_path / "state", signer=signer)
    S.commit(store, S.WORK)
    iss.read(S.T0)
    old = iss.latest
    iss.signer = K.rotate(tmp_path / "state", signer)
    assert iss.signer.key_id != old["key_id"] and not iss.current(old, S.T0)
    assert iss.read(S.T0 + timedelta(seconds=30)) == "OK" and iss.latest["key_id"] == iss.signer.key_id
    assert set(K.recorded_publics(tmp_path / "state")) == {old["key_id"], iss.signer.key_id}


# ---------------------------------------------------------------------------------------------- refusals at start

def test_the_issuer_refuses_an_anchor_for_another_store_or_not_on_the_wire(tmp_path):
    store = S.init(tmp_path / "proj")
    anchor = S.anchor_of(store)
    for bad in (dict(anchor, store_ref="store:" + S.OTHER), dict(anchor, store_ino=0), dict(anchor, h="x"),
                {k: v for k, v in anchor.items() if k != "anchored_at"}, dict(anchor, extra=1),
                dict(anchor, anchored_at="2026-10-18T13:00:00")):
        with pytest.raises(AnchorRefused):
            S.issuer(store, tmp_path / "state", anchor=bad)
        assert valid("Anchor", bad) != [] or bad["store_ref"] != anchor["store_ref"]
    with pytest.raises(AnchorRefused):
        S.issuer(store, tmp_path / "state", instance="not-an-instance")


def test_the_issuers_public_surface_takes_no_content_from_any_caller():
    """The reference's N02: read, witness and accessors; nothing a caller could push content through."""
    public = sorted(m for m in dir(Issuer) if not m.startswith("_"))
    assert public == ["current", "gap_age", "head", "latest", "read", "witness"]
    assert not any(k.startswith("Ingest") for k in SCHEMA["$defs"])
