"""The history index's seq bounds (design note §4.5, R13): ``max_seq`` pins a page's newest entry and ``before_seq``
excludes what was already served, so a growing history pages without its pages shifting."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from history_model import archive, init, read_root  # noqa: E402

from aew.history.index import HistoryIndex  # noqa: E402


def _index(root: Path) -> HistoryIndex:
    index = HistoryIndex(root)
    index.sync(read_root(root))
    return index


def test_max_seq_and_before_seq_bound_a_page(tmp_path):
    store = init(tmp_path)
    archive(store, units=7)
    index = _index(tmp_path)
    assert [e["seq"] for e in index.list(limit=3)] == [7, 6, 5]
    assert [e["seq"] for e in index.list(limit=3, max_seq=5)] == [5, 4, 3]
    assert [e["seq"] for e in index.list(limit=3, max_seq=5, before_seq=3)] == [2, 1]
    assert index.list(before_seq=1) == []
    assert [e["seq"] for e in index.list(kind="unit", max_seq=2)] == [2, 1]


def test_a_pinned_walk_is_stable_while_the_history_grows(tmp_path):
    store = init(tmp_path)
    archive(store, units=5)
    index = _index(tmp_path)
    pin = read_root(tmp_path)["count"]
    first = index.list(limit=2, max_seq=pin)
    archive(store, units=4)  # appended meanwhile
    index = _index(tmp_path)
    second = index.list(limit=2, max_seq=pin, before_seq=first[-1]["seq"])
    third = index.list(limit=2, max_seq=pin, before_seq=second[-1]["seq"])
    assert [e["seq"] for e in first + second + third] == [5, 4, 3, 2, 1]
    assert [e["seq"] for e in index.list(limit=2)] == [9, 8]  # a fresh walk starts at the new head
