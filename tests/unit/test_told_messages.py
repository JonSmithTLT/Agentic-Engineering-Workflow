"""Local delivery IDs: closed payload, grow-only union, generation scope and stable-lock fail-closed checks."""

from __future__ import annotations

import json
import sys

import pytest

from aew import process_kind
from aew.errors import IntegrityError, PermissionDenied, StaleAuthority, UsageError
from aew.harness import told_messages as T

A, B = "MSG-INV-0001-1", "MSG-INV-0002-1"


def test_normal_unions_leave_only_the_closed_json_and_two_stable_empty_lock_files(tmp_path):
    assert T.read(tmp_path, 1) == set() and not list(tmp_path.iterdir())
    assert T.record(tmp_path, 1, [B, A], current=lambda: True) == {A, B}
    assert T.record(tmp_path, 1, [A], current=lambda: True) == {A, B}
    assert json.loads((tmp_path / T.REL).read_bytes()) == {"generation": 1, "messages": [A, B]}
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == {
        T.REL, T.LOCK_REL, T.LOCK_REL + ".queue"}
    assert (tmp_path / T.LOCK_REL).read_bytes() == (tmp_path / (T.LOCK_REL + ".queue")).read_bytes() == b""


@pytest.mark.parametrize("doc", [None, [], {}, {"generation": True, "messages": [A]},
    {"generation": 1, "messages": [A], "body": "not allowed"}, {"generation": 1, "messages": ["forged"]},
    {"generation": 1, "messages": [A, A]}, {"generation": 1, "messages": [B, A]},
    {"generation": "1", "messages": [A]}, {"generation": 1, "messages": "not a list"}])
def test_invalid_or_partial_records_supply_no_suppression(tmp_path, doc):
    path = tmp_path / T.REL
    path.parent.mkdir(parents=True)
    path.write_text("{" if doc is None else json.dumps(doc), encoding="utf-8")
    assert T.read(tmp_path, 1) == set()
    T.record(tmp_path, 1, [B], current=lambda: True)
    assert T.read(tmp_path, 1) == {B}


def test_a_restart_keeps_the_union_a_new_generation_resets_and_an_old_broker_cannot_regress_it(tmp_path):
    T.record(tmp_path, 1, [A], current=lambda: True)
    T.record(tmp_path, 1, [B], current=lambda: True)  # another broker object/process, same generation
    assert T.read(tmp_path, 1) == {A, B} and T.read(tmp_path, 2) == set()
    T.record(tmp_path, 2, [B], current=lambda: True)
    before = (tmp_path / T.REL).read_bytes()
    with pytest.raises(StaleAuthority):
        T.record(tmp_path, 1, [A], current=lambda: True)
    assert (tmp_path / T.REL).read_bytes() == before and T.read(tmp_path, 2) == {B}


def test_even_a_damaged_future_generation_is_not_overwritten(tmp_path):
    path = tmp_path / T.REL
    path.parent.mkdir(parents=True)
    raw = json.dumps({"generation": 2, "messages": ["bad"], "extra": "bad"}).encode()
    path.write_bytes(raw)
    with pytest.raises(StaleAuthority):
        T.record(tmp_path, 1, [A], current=lambda: True)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("lost_at", [0, 1, 2])
def test_authority_is_rechecked_before_lock_after_wait_and_immediately_before_replace(tmp_path, lost_at):
    T.record(tmp_path, 1, [A], current=lambda: True)
    before = (tmp_path / T.REL).read_bytes()
    calls = []

    def current():
        calls.append(True)
        return len(calls) <= lost_at

    with pytest.raises(StaleAuthority):
        T.record(tmp_path, 1, [B], current=current)
    assert len(calls) == lost_at + 1 and (tmp_path / T.REL).read_bytes() == before


def test_a_lost_stable_lock_prevents_any_replace(tmp_path, monkeypatch):
    T.record(tmp_path, 1, [A], current=lambda: True)
    before = (tmp_path / T.REL).read_bytes()

    def lose(name):
        assert name == "messaging.told.before_replace"
        if sys.platform == "win32":
            with pytest.raises(OSError):  # an open Windows lock file cannot be removed
                (tmp_path / T.LOCK_REL).unlink()
            monkeypatch.setattr(T.FileLock, "intact", lambda lock: False)
        else:
            (tmp_path / T.LOCK_REL).unlink()
            (tmp_path / T.LOCK_REL).touch()  # a new inode is not the held lock

    monkeypatch.setattr(T.faults, "pause", lose)
    with pytest.raises(IntegrityError, match="stable told-message lock"):
        T.record(tmp_path, 1, [B], current=lambda: True)
    assert (tmp_path / T.REL).read_bytes() == before


def test_atomic_write_errors_leave_the_previous_union_intact(tmp_path, monkeypatch):
    T.record(tmp_path, 1, [A], current=lambda: True)
    before = (tmp_path / T.REL).read_bytes()

    def fail(src, dest):
        raise OSError("planted replace error")

    monkeypatch.setattr(T.util, "replace_with_retry", fail)
    with pytest.raises(OSError):
        T.record(tmp_path, 1, [B], current=lambda: True)
    assert (tmp_path / T.REL).read_bytes() == before
    assert not list((tmp_path / T.REL).parent.glob(".told-messages.json.*"))


def test_a_nonwriter_read_process_cannot_create_even_the_local_parent_directory(tmp_path):
    with process_kind.declared_as("aew (contained Lead)"), pytest.raises(PermissionDenied):
        T.record(tmp_path, 1, [A], current=lambda: True)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("ids", [["not-an-id"], ["MSG-INV-0001-0"], ["MSG-INV-0001-1\nbody"]])
def test_invalid_ids_are_refused_before_creating_a_lock(tmp_path, ids):
    with pytest.raises(UsageError):
        T.record(tmp_path, 1, ids, current=lambda: True)
    assert not list(tmp_path.iterdir())
