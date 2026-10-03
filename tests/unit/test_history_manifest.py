"""The history manifest's form (ADR-0011, implementation plan R1): the pinned hash chain, entries and files."""

from __future__ import annotations

import datetime

import pytest

from aew.errors import IntegrityError, ValidationFailed
from aew.history import manifest as M

ENTRY = {"seq": 1, "kind": "unit", "id": "T-0001", "path": "work/T-0001/archive.yaml", "sha256": "a" * 64,
         "at": "2026-10-02T00:00:00Z", "state": "DONE", "links": {"depends_on": ["T-0000"]}}


def test_the_chain_construction_is_pinned_by_golden_vectors():
    # Evidence and roots bind to these values: changing the construction is a schema change, never a refactor.
    assert M.GENESIS_H == "213499cc10fc70e56dd7125616042ffc43bed016f730834af4c59e9b1901f328"
    assert M.canonical_json(ENTRY) == (
        b'{"at":"2026-10-02T00:00:00Z","id":"T-0001","kind":"unit","links":{"depends_on":["T-0000"]},'
        b'"path":"work/T-0001/archive.yaml","seq":1,"sha256":"' + b"a" * 64 + b'","state":"DONE"}')
    h1 = M.chain_hash(M.GENESIS_H, ENTRY)
    assert h1 == "dc497e6347c9cdec9daabb577d137dee6f7962a17e2825ca53a55f9e2378cf37"
    second = dict(ENTRY, seq=2, id="T-0002", path="work/T-0002/archive.yaml")
    assert M.chain_hash(h1, second) == "db9f6c6f2ce52ca5a675502819fc18c79e40bc7a4388795474b1118f2810cc59"


def test_an_entry_is_hashed_without_its_own_hash_and_independently_of_key_order():
    entry = M.new_entry(1, M.GENESIS_H, {k: v for k, v in reversed(list(ENTRY.items())) if k != "seq"})
    assert entry["h"] == M.chain_hash(M.GENESIS_H, ENTRY) == M.chain_hash(M.GENESIS_H, entry)


@pytest.mark.parametrize("value", [1.5, datetime.datetime(2026, 10, 2), ("a", "b"), {1: "x"}])
def test_only_json_values_are_hashed(value):
    with pytest.raises(IntegrityError):
        M.chain_hash(M.GENESIS_H, dict(ENTRY, note=value))


def test_seq_and_hash_are_assigned_by_the_manifest():
    with pytest.raises(IntegrityError):
        M.new_entry(1, M.GENESIS_H, ENTRY)
    with pytest.raises(IntegrityError):
        M.new_entry(1, M.GENESIS_H, {**{k: v for k, v in ENTRY.items() if k != "seq"}, "h": "0" * 64})


@pytest.mark.parametrize("change", [
    {"path": "../outside.yaml"}, {"path": "/abs/path.yaml"}, {"path": "work/../../x"}, {"path": "C:\\x"},
    {"kind": "evidence"}, {"sha256": "XYZ"}, {"source": "rumour"}, {"unknown": 1}, {"id": ""},
])
def test_entries_are_validated(change):
    fields = {**{k: v for k, v in ENTRY.items() if k != "seq"}, **change}
    with pytest.raises(ValidationFailed):
        M.new_entry(1, M.GENESIS_H, fields)


def test_files_hold_bounded_entry_counts():
    entries, h = [], M.GENESIS_H
    for seq in range(1, M.SEGMENT_SIZE + 1):
        entries.append(M.new_entry(seq, h, {**{k: v for k, v in ENTRY.items() if k != "seq"}, "id": f"T-{seq}"}))
        h = entries[-1]["h"]
    start = {"count": 0, "h": M.GENESIS_H}
    sealed = M.render_file(sealed=True, seq=1, start=start, prev=None, entries=entries)
    assert M.parse_file(sealed, source="seg", sealed=True)["entries"] == entries
    with pytest.raises(IntegrityError, match="fewer than"):
        M.parse_file(M.render_file(sealed=False, seq=1, start=start, prev=None, entries=entries), source="tail",
                     sealed=False)
    with pytest.raises(IntegrityError, match="exactly"):
        M.parse_file(M.render_file(sealed=True, seq=1, start=start, prev=None, entries=entries[:-1]), source="seg",
                     sealed=True)
    with pytest.raises(IntegrityError, match="expected"):  # a tail is not a segment
        M.parse_file(sealed, source="seg", sealed=False)
    assert M.fold(start, entries, source="seg") == {"count": M.SEGMENT_SIZE, "h": h}


def test_fold_refuses_a_gap_or_a_broken_link():
    first = M.new_entry(1, M.GENESIS_H, {k: v for k, v in ENTRY.items() if k != "seq"})
    second = M.new_entry(2, first["h"], {**{k: v for k, v in ENTRY.items() if k != "seq"}, "id": "T-0002"})
    start = {"count": 0, "h": M.GENESIS_H}
    with pytest.raises(IntegrityError, match="where 1 was expected"):
        M.fold(start, [second], source="x")
    with pytest.raises(IntegrityError, match="hash chain"):
        M.fold(start, [first, dict(second, id="T-9999")], source="x")


def test_segment_numbers():
    assert [M.segment_of(s) for s in (1, 256, 257, 512, 513)] == [1, 1, 2, 2, 3]
    assert M.segment_rel(3) == "history/seg-000003.yaml"
