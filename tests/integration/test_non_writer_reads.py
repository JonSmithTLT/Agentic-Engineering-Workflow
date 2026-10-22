"""STG-05 CB-09: a process that is not a store writer never takes the control lock.

A non-writer reads through the lock-free reads only (``ControlStore.read_committed``, ``configuration.read_committed``,
``outbox.LogView``, ``outbox.read_transitions``), which work on a read-only store; ``read``, ``session`` and ``create``
are refused before the lock is opened. The `aew` CLI inside a worker's run is such a process. The sandbox side (the
store on a read-only bind, the control lock out of the layout) is in tests/integration/test_containment.py.
"""

from __future__ import annotations

import errno
import json
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


def worker_env(root: Path) -> dict[str, str]:
    """A worker run's environment: a bridge address of the platform's kind that nothing serves."""
    endpoint = r"\\.\pipe\aew-no-such-bridge-cb09" if sys.platform == "win32" else str(root / "no-bridge")
    return {"AEW_AGENT_ENDPOINT": endpoint, "AEW_AGENT_KEY": "00" * 32}


def leaf_commands() -> list[tuple[str, ...]]:
    import argparse

    from aew.cli.main import build_parser

    def walk(parser: argparse.ArgumentParser, prefix: tuple[str, ...]):
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if not subs:
            yield prefix
        for action in subs:
            for name, sub in action.choices.items():
                yield from walk(sub, (*prefix, name))

    return sorted(set(walk(build_parser(), ())))


# Commands a non-writer is refused for want of the lock, each with why it needs it. Shrink-only.
NEEDS_THE_LOCK = {
    ("history", "audit"): ("copies the history's root and its mutable tail together, which only the lock keeps "
                           "consistent"),
}


def test_no_cli_command_inside_a_worker_run_is_refused_only_for_want_of_the_control_lock(project):
    """Output-side over the whole CLI (review of #231, B1): every command with no required argument, run as a worker's
    agent runs it, reads lock-free or is refused for a reason of its own (authority, usage, the bridge), never as a
    non-writer, except the commands that need the lock (NEEDS_THE_LOCK). A command with required arguments stops at
    argparse and is not judged here; the engine reads behind them are the next test's."""
    from concurrent.futures import ThreadPoolExecutor

    env = worker_env(project.root)
    lock = project.root / ".aew" / LOCK_REL
    lock.unlink()  # a locked read or a session would create it again

    def run(cmd: tuple[str, ...]) -> tuple[tuple[str, ...], str | None]:
        res = run_aew("-C", str(project.root), *cmd, env=env, timeout=120)
        try:
            details = json.loads(res.stderr)["error"].get("details") or {}
        except (ValueError, KeyError, TypeError):
            return cmd, None
        return cmd, details.get("reason")

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = dict(pool.map(run, leaf_commands()))
    refused = {cmd for cmd, reason in outcomes.items() if reason == "non_writer_process"}
    assert refused == set(NEEDS_THE_LOCK), sorted(refused)
    assert not lock.exists()


def test_the_cli_inside_a_worker_run_reads_lock_free_and_refuses_a_mutation_before_the_lock(tmp_path):
    from aewflow import assign, create_planned_ticket, sample_project

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    assign(p, wid)
    rev = p.rev()  # a read in this process, a writer: before the lock goes, or it would create it again itself
    lock = p.root / ".aew" / LOCK_REL
    lock.unlink()  # a locked read or a session would create it again
    env = worker_env(p.root)
    for args in (["status", "--json"], ["resume", "--json"], ["invoke", "show", "INV-0001"],
                 ["context", "show", "INV-0001"], ["harness", "status"], ["lead", "show"], ["work", "list"]):
        res = run_aew("-C", str(p.root), *args, env=env)
        assert res.returncode == 0, (args, res.stderr)
    mutation = run_aew("-C", str(p.root), "work", "create", "ticket", "--title", "x", "--class", "1",
                       "--token", p.token, "--expect-rev", str(rev), env=env)
    assert mutation.error["code"] == "PERMISSION_DENIED", mutation.stderr
    assert mutation.error["details"]["reason"] == "non_writer_process"
    whoami = run_aew("-C", str(p.root), "whoami", env=env)  # to the bridge, which is not there: never the store
    assert whoami.error["code"] == "STALE_AUTHORITY", whoami.stderr
    assert not lock.exists()


def test_every_engine_read_goes_through_the_one_place_that_chooses_lock_free_for_a_non_writer():
    """Mechanical (method, not instance): ``ControlStore.current`` picks ``read`` or ``read_committed`` by the
    process's kind, so no code outside the store calls ``store.read()`` itself; the one exception is the manifest's
    reload in ``Kernel.manifest``, which makes the same choice beside it."""
    import re

    src = Path(__file__).resolve().parents[2] / "src" / "aew"
    calls = {f.relative_to(src).as_posix(): len(re.findall(r"\bstore\.read\(\)", f.read_text(encoding="utf-8")))
             for f in src.rglob("*.py")}
    assert {f: n for f, n in calls.items() if n and f != "engine/store.py"} == {"engine/base.py": 1}
