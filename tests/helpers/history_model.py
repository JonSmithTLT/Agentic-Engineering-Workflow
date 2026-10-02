"""A deterministic history workload over ControlStore, shared by in-process and subprocess tests (ADR-0011 P2a).

Each archival transaction writes one bundle per archived unit (``work/T-<k>/archive.yaml``), appends their manifest
entries, and stores the new root. The engine will keep the root in ``control.yaml`` (the ``cold`` key that control
schema v2 adds in P2b); until then this workload keeps it in a mutable file written in the same transaction, which
the redo record makes exactly as atomic. ``counters.n`` counts the archived units.

``check`` asserts that what is on disk agrees with the committed state: the root pins exactly ``n`` entries, the
whole chain and every record verify, the index syncs to the root, and no record is left unreferenced except the
ones a test expects (a pre-written bundle whose commit never happened).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from store_model import initial_state, make_store

from aew.engine.store import ControlStore, Transition
from aew.history import manifest as M
from aew.history.index import HistoryIndex
from aew.history.store import History, bundle_rel, prewrite
from aew.util import dump_yaml, load_yaml

ROOT_REL = "state/history-root.yaml"
AT = "2026-10-02T00:00:00Z"


def init(root: Path) -> ControlStore:
    store = make_store(root)
    store.create(initial_state(), {})
    return store


def read_root(aew_root: Path) -> dict[str, Any]:
    path = aew_root / ROOT_REL
    return load_yaml(path.read_text(encoding="utf-8"), source=ROOT_REL) if path.exists() else M.empty_root()


def bundle(k: int) -> str:
    return f"schema: test/bundle\nid: T-{k:04d}\nstate: DONE\n" + "payload: line\n" * 10


def fields(k: int, sha: str) -> dict[str, Any]:
    links = {"depends_on": [f"T-{k - 1:04d}"]} if k > 1 else {}
    return {"kind": "unit", "id": f"T-{k:04d}", "path": bundle_rel(f"T-{k:04d}"), "sha256": sha, "at": AT,
            "state": "DONE", "parent": None, "source": "engine", "links": links}


def archive(store: ControlStore, units: int = 1, *, prewritten: bool = False) -> dict[str, Any]:
    """Archive ``units`` more units in one transaction; the new root. With ``prewritten`` the bundles are written
    before the transaction and referenced by hash (plan R8), as a migration does."""
    history = History(store.root)
    if prewritten:  # written outside the lock, before the session, exactly as a migration pre-writes
        k0 = store.read()["counters"]["n"]
        shas = {k: prewrite(store.root, bundle_rel(f"T-{k:04d}"), bundle(k)) for k in range(k0 + 1, k0 + units + 1)}
    with store.session() as s:
        k0 = s.state["counters"]["n"]
        items = []
        for k in range(k0 + 1, k0 + units + 1):
            rel = bundle_rel(f"T-{k:04d}")
            if prewritten:
                s.prewritten(rel, shas[k])
                sha = shas[k]
            else:
                sha = history.write_record(s, rel, bundle(k))
            items.append(fields(k, sha))
        new_root = history.append(s, read_root(store.root), items)
        s.write(ROOT_REL, dump_yaml(new_root), immutable=False)
        s.state["counters"]["n"] = k0 + units
        s.commit(Transition(op="history.archive", actor={"kind": "test"}, summary=f"archived {units}"))
    return new_root


def check(aew_root: Path, *, unreferenced: tuple[str, ...] = ()) -> int:
    """The number of archived units, after asserting that history and committed state agree."""
    store = make_store(aew_root)
    n = store.read()["counters"]["n"]  # recovery first: a crashed transaction is rolled forward or discarded
    root = read_root(aew_root)
    assert root["count"] == n, (root, n)
    report = History(aew_root).verify(root)
    assert report.ok, report.problems
    assert report.entries == report.records == n
    index = HistoryIndex(aew_root)
    index.sync(root)
    assert len(index.list(kind="unit")) == n
    assert tuple(History(aew_root).unreferenced(index.paths())) == unreferenced
    return n
