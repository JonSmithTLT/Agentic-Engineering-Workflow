"""STG-05 CB-09: a process that is not a store writer never takes the control lock.

A non-writer reads through the lock-free reads only (``ControlStore.read_committed``, ``configuration.read_committed``,
``outbox.LogView``, ``outbox.read_transitions``), which work on a read-only store; ``read``, ``session`` and ``create``
are refused before the lock is opened. The `aew` CLI inside a worker's run is such a process. The sandbox side (the
store on a read-only bind, the control lock out of the layout) is in tests/integration/test_containment.py.
"""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from conftest import make_git_repo, run_aew  # noqa: E402

from aew import process_kind  # noqa: E402
from aew.engine import configuration, outbox  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.engine.base import Kernel  # noqa: E402
from aew.engine.store import LOCK_REL, ControlStore  # noqa: E402
from aew.errors import PermissionDenied  # noqa: E402

WORKER = "aew (worker run)"


def test_every_entry_point_has_a_kind_and_the_cli_knows_which_it_is():
    assert {k for k, _ in process_kind.ENTRY_POINTS.values()} == {process_kind.STORE_WRITER, process_kind.NON_WRITER}
    cases = {
        (("status",), ()): "aew",
        (("-C", "lead", "mcp"), ()): "aew",  # `lead` here is -C's directory, not a word of the command
        (("lead", "mcp"), ()): "aew lead mcp",
        (("-C", "/p", "lead", "mcp"), ()): "aew lead mcp",
        (("--print-credential", "lead", "mcp"), ()): "aew lead mcp",
        (("status",), (("AEW_AGENT_ENDPOINT", "/tmp/aew-x/s"),)): WORKER,
        (("lead", "mcp"), (("AEW_AGENT_ENDPOINT", "/tmp/aew-x/s"),)): WORKER,
    }
    for (argv, env), want in cases.items():
        assert process_kind.cli_entry_point(list(argv), dict(env)) == want, argv
    with pytest.raises(KeyError):
        process_kind.declare("aew-something-new")


def test_an_undeclared_process_is_a_writer_and_a_declaration_is_scoped():
    assert process_kind.declared() is None and process_kind.kind() == process_kind.STORE_WRITER
    with process_kind.declared_as(WORKER):
        assert process_kind.kind() == process_kind.NON_WRITER
    assert process_kind.declared() is None


@pytest.fixture
def engine(tmp_path) -> Kernel:
    e = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# nw\n"}), project_id="nw")
    return Kernel(e.repo_root, e.aew_root)


def test_a_non_writer_is_refused_read_session_and_create_before_the_lock_is_opened(engine, tmp_path):
    lock = engine.aew_root / LOCK_REL
    lock.unlink()  # opening the lock would create it again: its absence afterwards shows nothing opened it
    store = ControlStore(engine.aew_root)
    fresh = ControlStore(tmp_path / "fresh" / ".aew")
    with process_kind.declared_as(WORKER):
        for what, call in (("ControlStore.read", store.read),
                           ("ControlStore.session", lambda: store.session().__enter__()),
                           ("ControlStore.create", lambda: fresh.create({}, {}))):
            with pytest.raises(PermissionDenied) as refused:
                call()
            assert refused.value.code == "PERMISSION_DENIED"
            assert refused.value.details == {"entry_point": WORKER, "operation": what, "reason": "non_writer_process"}
            assert "lock-free" in refused.value.message and "bridge" in refused.value.message
    assert not lock.exists() and not (tmp_path / "fresh").exists()


def lock_free_reads(k: Kernel) -> dict:
    """Every read a non-writer may make, once each."""
    state = k.store.read_committed()
    committed = configuration.read_committed(k)
    since = (state.get("outbox") or {}).get("since", 0)
    view = outbox.LogView(k.aew_root, since)
    records = list(outbox.read_transitions(k.aew_root, since, state["revision"], outbox=state.get("outbox")))
    return {"revision": state["revision"], "manifest": committed.manifest_raw is not None,
            "view": view.root == k.aew_root, "records": len(records)}


def test_a_non_writers_reads_are_lock_free_and_take_nothing_from_the_lock(engine):
    engine.store.read()  # recovered once by a writer, as the engine always leaves it
    (engine.aew_root / LOCK_REL).unlink()
    with process_kind.declared_as(WORKER):
        got = lock_free_reads(engine)
    assert got == {"revision": 0, "manifest": True, "view": True, "records": 0}
    assert not (engine.aew_root / LOCK_REL).exists()


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="POSIX permission bits, as a non-root user (root ignores them)")
def test_a_non_writers_reads_work_on_a_read_only_store_with_no_erofs_or_eacces(engine):
    """The read-only bind of a sandbox, approximated outside one: nothing under .aew writable, the lock unwritable."""
    engine.store.read()
    changed = []
    for d, dirs, files in os.walk(engine.aew_root, topdown=False):
        for name in [*files, *dirs, ""]:
            path = Path(d) / name if name else Path(d)
            mode = stat.S_IMODE(os.lstat(path).st_mode)
            os.chmod(path, mode & ~0o222)
            changed.append((path, mode))
    try:
        with process_kind.declared_as(WORKER):
            try:
                got = lock_free_reads(engine)
            except OSError as exc:  # EROFS or EACCES here is the defect this test exists for
                pytest.fail(f"a lock-free read failed with {errno.errorcode.get(exc.errno or 0)}: {exc}")
        assert got["revision"] == 0
        with pytest.raises(PermissionError):  # what a writer meets on such a store: no read-only fallback (CBF-1)
            ControlStore(engine.aew_root).read()
    finally:
        for path, mode in reversed(changed):
            os.chmod(path, mode)


def test_the_cli_inside_a_worker_run_refuses_a_locked_read_and_routes_its_operations_to_the_bridge(project):
    # A bridge address of the platform's kind that nothing serves.
    endpoint = r"\\.\pipe\aew-no-such-bridge-cb09" if sys.platform == "win32" else str(project.root / "no-bridge")
    env = {"AEW_AGENT_ENDPOINT": endpoint, "AEW_AGENT_KEY": "00" * 32}
    status = run_aew("-C", str(project.root), "status", "--json", env=env)
    err = status.error
    assert status.returncode != 0 and err["code"] == "PERMISSION_DENIED", status.stderr
    assert err["details"]["reason"] == "non_writer_process" and err["details"]["entry_point"] == WORKER
    whoami = run_aew("-C", str(project.root), "whoami", env=env)  # to the bridge, which is not there: never the store
    assert whoami.error["code"] == "STALE_AUTHORITY", whoami.stderr
