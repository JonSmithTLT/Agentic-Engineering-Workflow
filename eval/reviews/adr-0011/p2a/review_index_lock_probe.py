"""Reproduce a transient index lock being treated as damage on Windows."""
from pathlib import Path
import json
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path.cwd() / "tests/helpers"))
from history_model import archive, init, read_root
from aew.history.index import HistoryIndex

with tempfile.TemporaryDirectory(prefix="aew-p2a-lock-") as td:
    store = init(Path(td))
    archive(store, 1)
    root = read_root(store.root)
    index = HistoryIndex(store.root)
    assert index.sync(root) == {"mode": "rebuilt", "added": 1}
    conn = sqlite3.connect(index.path)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        try:
            result = index.sync(root)
        except Exception as exc:
            print(json.dumps({"raised": type(exc).__name__, "message": str(exc),
                              "cause": str(exc.__context__)}), flush=True)
            assert isinstance(exc, PermissionError)
            assert str(exc.__context__) == "database is locked"
        else:
            raise AssertionError(result)
    finally:
        conn.rollback()
        conn.close()
    assert index.sync(root) == {"mode": "current", "added": 0}
    assert len(index.list()) == 1
    print("PASS: index remained intact; lock was transient, but sync attempted to delete it", flush=True)
