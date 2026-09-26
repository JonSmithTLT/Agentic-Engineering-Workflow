"""A tiny deterministic workload over ControlStore, shared by in-process and subprocess tests.

Each transaction k (1-based) bumps ``counters.n`` to k, creates the immutable
record ``records/item-<k>.md`` and replaces the mutable ``manifest.txt``. The
renderer derives ``state/CURRENT.md``. ``check_invariants`` asserts that the
observable files agree exactly with the committed revision: no hybrid states.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew import SPEC_SET
from aew.engine.store import ControlStore, Transition


def initial_state() -> dict[str, Any]:
    return {
        "schema": "aew/control/v1",
        "project_id": "store-test",
        "spec_set": SPEC_SET,
        "revision": 0,
        "manifest_sha256": "0" * 64,
        "lead": {
            "schema": "aew/lead/v1",
            "status": "vacant",
            "generation": 0,
            "session_label": None,
            "token_id": None,
            "acquired_at": None,
            "handoff": None,
        },
        "tokens": {},
        "counters": {"n": 0},
        "work": {},
        "invocations": {},
        "last_transition": {
            "revision": 0, "at": "t", "actor": {"kind": "init"}, "op": "init",
            "summary": None, "reason": None, "refs": [], "txn": None,
        },
    }


def render(state: dict[str, Any]) -> dict[str, str]:
    return {"state/CURRENT.md": f"revision {state['revision']} n {state['counters']['n']}\n"}


def make_store(root: Path) -> ControlStore:
    return ControlStore(root, renderer=render, lock_timeout=120)


def item_content(k: int) -> str:
    return f"item {k}\n" + ("payload line\n" * 20)


def one_transaction(store: ControlStore, *, expect_rev: int | None = None) -> int:
    with store.session() as s:
        k = s.state["counters"]["n"] + 1
        s.state["counters"]["n"] = k
        s.write(f"records/item-{k}.md", item_content(k))
        s.write("manifest.txt", f"n={k}\n", immutable=False)
        return s.commit(Transition(op="bump", actor={"kind": "test"}), expect_rev=expect_rev)


def check_invariants(root: Path) -> int:
    store = make_store(root)
    state = store.read()
    n = state["counters"]["n"]
    assert state["revision"] == n, (state["revision"], n)
    for k in range(1, n + 1):
        assert (root / f"records/item-{k}.md").read_text() == item_content(k), k
        assert (root / f"state/log/{k:06d}.yaml").exists(), f"log {k} missing"
    assert not (root / f"records/item-{n + 1}.md").exists(), "uncommitted write leaked"
    manifest = root / "manifest.txt"
    if n:
        assert manifest.read_text() == f"n={n}\n"
    else:
        assert not manifest.exists()
    assert (root / "state/CURRENT.md").read_text() == render(state)["state/CURRENT.md"]
    txn_dir = root / "state/txn"
    if txn_dir.exists():
        assert all(int(f.stem) <= n for f in txn_dir.glob("*.yaml")), "uncommitted redo record left"
    leftovers = [p for p in root.rglob(".*.tmp")]
    assert not leftovers, leftovers
    return n


def init(root: Path) -> ControlStore:
    store = make_store(root)
    store.create(initial_state(), {})
    return store
