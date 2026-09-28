"""The control store reuses a parse only for identical bytes (M3 step 7; ``store.py``): a process re-parses and
re-verifies ``control.yaml`` whenever its bytes differ from the last bytes it parsed, and nothing a caller does to
a state it was given can change what the next read returns."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from store_model import init, make_store, one_transaction  # noqa: E402

from aew import profile  # noqa: E402
from aew.errors import IntegrityError  # noqa: E402


def counts(fn) -> dict[str, int]:
    profile.start()
    try:
        fn()
    finally:
        summary = profile.stop()
    return summary["counts"]


def test_unchanged_bytes_are_parsed_once(tmp_path):
    store = init(tmp_path)
    one_transaction(store)  # the commit wrote new bytes: the next read parses them, the rest reuse that parse
    c = counts(lambda: [store.read() for _ in range(5)])
    assert (c.get("parse"), c.get("parse_cached")) == (1, 4)


def test_another_process_commit_is_read(tmp_path):
    ours, theirs = init(tmp_path), make_store(tmp_path)
    assert ours.read()["counters"]["n"] == 0
    one_transaction(theirs)
    assert ours.read()["counters"]["n"] == 1 and ours.read()["revision"] == 1


def test_damage_after_a_reused_parse_still_fails_closed(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    store.read()
    control = tmp_path / "state/control.yaml"
    control.write_text(control.read_text().replace("n: 1", "n: 7"))  # same size, same file, edited in place
    with pytest.raises(IntegrityError):
        store.read()


def test_callers_cannot_change_what_the_next_read_returns(tmp_path):
    store = init(tmp_path)
    one_transaction(store)
    given = store.read()
    given["counters"]["n"] = 999
    given["work"]["X"] = {"forged": True}
    with pytest.raises(RuntimeError):
        with store.session() as s:
            s.state["counters"]["n"] = 777  # a transaction that never commits
            raise RuntimeError("abandoned")
    again = store.read()
    assert again["counters"]["n"] == 1 and "X" not in again["work"]
