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
import shutil
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

import worker_surface  # noqa: E402
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
        (("-C", "/p", "dashboard", "serve", "--port", "0"), ()): "aew dashboard serve",
        (("dashboard", "status"), ()): "aew",
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


def refusal_reason(stderr: str) -> str | None:
    try:
        return (json.loads(stderr)["error"].get("details") or {}).get("reason")
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def test_a_non_writer_is_refused_compact_pack_and_reindex_before_they_start(engine):
    """The engine operations that take the lock or write under `.aew` outside a session (review of #231, MJ1 and m7)
    refuse a non-writer first, saying what they would have written, and nothing under `.aew` changes."""
    e = Engine(engine.repo_root, engine.aew_root)
    (engine.aew_root / LOCK_REL).unlink()  # opening the lock would create it again
    before = worker_surface.snapshot(engine.aew_root)
    calls = {"history compact": e.history_compact, "context pack": lambda: e.context_pack("INV-0001"),
             "history reindex": e.history_reindex}
    with process_kind.declared_as(WORKER):
        for what, call in calls.items():
            with pytest.raises(PermissionDenied) as refused:
                call()
            assert refused.value.details == {"entry_point": WORKER, "operation": what, "reason": "non_writer_process"}
            assert "which writes" in refused.value.message and "before it writes anything" in refused.value.message
    assert worker_surface.changes(before, worker_surface.snapshot(engine.aew_root)) == []


def test_the_reader_git_gap_is_recognised_by_its_mechanism_and_nothing_else_is():
    """Planted cases for ``worker_surface.git_object_store_refused``, the classifier of the pinned READER_GIT_GAP
    (the containment test's sandbox run decides the set)."""
    def refusal(code: str, git_stderr: str) -> str:
        return json.dumps({"ok": False, "error": {"code": code, "message": "git add -A failed (128)",
                                                  "details": {"stderr": git_stderr}}})

    store = "error: unable to create temporary file: Read-only file system\nerror: x: failed to insert into database"
    assert worker_surface.git_object_store_refused(refusal("GIT_ERROR", store))
    assert not worker_surface.git_object_store_refused(refusal("GIT_ERROR", "fatal: not a git repository"))
    assert not worker_surface.git_object_store_refused(refusal("INTEGRITY_ERROR", store))  # another code: not it
    assert not worker_surface.git_object_store_refused("Traceback (most recent call last): Read-only file system")


def test_no_command_a_worker_can_run_writes_under_aew_or_takes_the_lock(tmp_path):
    """Output-side over everything a worker's agent can run (review of #231: B1, MJ1 and m7), outside a sandbox, where
    nothing stops a write. On a project with finished work, a Ticket in flight and a log past the compaction window,
    every command (``worker_surface.commands``: the parser's leaves and the surface map's probes) either works without
    changing anything under `.aew`, the control lock included (deleted first), or is refused for a reason of its own;
    only the commands in WRITER_ONLY are refused as a non-writer's. The one change a reader makes, the derived history
    index's catch-up, is left out by ``worker_surface.changes``, which says why. The judge is the tree, not what a
    command prints: the commands run together, and only a change is attributed, from the same start, one command at a
    time. The same commands inside a reviewer's sandbox are tests/integration/test_containment.py's."""
    from concurrent.futures import ThreadPoolExecutor

    w = worker_surface.worked_project(tmp_path)
    aew = w.p.root / ".aew"
    env = worker_env(w.p.root)
    cmds = worker_surface.commands(w)

    def prepare() -> None:  # what a write would make again: the lock taken, a pack regenerated
        for path in (aew / LOCK_REL, *worker_surface.removals(w)):
            path.unlink(missing_ok=True)

    def run(argv: list[str]):
        return argv, run_aew("-C", str(w.p.root), *argv, env=env, timeout=120)

    prepare()
    pristine = shutil.copytree(aew, tmp_path / "aew-before")  # to attribute a change, should one show
    before = worker_surface.snapshot(aew)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, cmds))
    changed = worker_surface.changes(before, worker_surface.snapshot(aew))
    writers: dict[str, list[str]] = {}
    if changed:  # from the same start, one command at a time: each change goes to the first command that makes it
        shutil.rmtree(aew)
        shutil.copytree(pristine, aew)
        for argv in cmds:
            alone = worker_surface.snapshot(aew)
            run(argv)
            if diff := worker_surface.changes(alone, worker_surface.snapshot(aew)):
                writers[" ".join(argv)] = diff[:4]
    assert changed == [], (changed[:8], writers)
    assert {" ".join(a): r.stderr[-400:] for a, r in results if "Traceback" in r.stderr} == {}
    refused = {worker_surface.words(a) for a, r in results if refusal_reason(r.stderr) == "non_writer_process"}
    assert refused == set(worker_surface.WRITER_ONLY), sorted(refused)


def test_the_cli_inside_a_worker_run_reads_lock_free_and_refuses_a_mutation_before_the_lock(tmp_path):
    from aewflow import assign, create_planned_ticket, sample_project

    p = sample_project(tmp_path)
    wid = create_planned_ticket(p, tmp_path)
    assign(p, wid)
    rev = p.rev()  # a read in this process, a writer: before the lock goes, or it would create it again itself
    lock = p.root / ".aew" / LOCK_REL
    lock.unlink()  # a locked read or a session would create it again
    packs = p.root / ".aew" / "local" / "packs"
    shutil.rmtree(packs)  # as a sandbox sees them, under the mask: `context show` renders without writing one
    env = worker_env(p.root)
    before = worker_surface.snapshot(p.root / ".aew")
    for args in (["status", "--json"], ["resume", "--json"], ["invoke", "show", "INV-0001"],
                 ["context", "show", "INV-0001"], ["harness", "status"], ["lead", "show"], ["work", "list"]):
        res = run_aew("-C", str(p.root), *args, env=env)
        assert res.returncode == 0, (args, res.stderr)
    assert worker_surface.changes(before, worker_surface.snapshot(p.root / ".aew")) == []  # no pack, no lock
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


# ------------------------------------------------------------------ the control lock's one opener (review of #231, MJ1)

def lock_path_refs(source: str) -> set[int]:
    """Lines that name the engine's control lock's path, resolved by import: ``LOCK_REL`` imported from
    ``aew.engine.store`` under any alias, the attribute ``LOCK_REL`` of that module under any alias or spelled out,
    or the path's literal (``control.lock``)."""
    import ast

    tree = ast.parse(source)
    names: set[str] = set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "aew.engine.store":
            names |= {a.asname or a.name for a in node.names if a.name == "LOCK_REL"}
        elif isinstance(node, ast.ImportFrom) and node.module == "aew.engine":
            modules |= {a.asname or a.name for a in node.names if a.name == "store"}
        elif isinstance(node, ast.Import):
            modules |= {a.asname for a in node.names if a.name == "aew.engine.store" and a.asname}
    hits = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "aew.engine.store" and \
                any(a.name == "LOCK_REL" for a in node.names):
            hits.add(node.lineno)
        elif isinstance(node, ast.Name) and node.id in names:
            hits.add(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr == "LOCK_REL" and (
                (isinstance(node.value, ast.Name) and node.value.id in modules)
                or ast.unparse(node.value) == "aew.engine.store"):
            hits.add(node.lineno)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "control.lock" in node.value:
            hits.add(node.lineno)
    return hits


def lock_path_refs_by_text(source: str) -> set[int]:
    """The second detector, written apart from the first: a line naming ``LOCK_REL`` in a file that imports the store
    module or a name from it, or a line with the path's literal."""
    import re

    lines = source.splitlines()
    imports = r"from aew\.engine\.store import|import aew\.engine\.store|from aew\.engine import .*\bstore\b"
    store = any(re.search(imports, line) for line in lines)
    return {n for n, line in enumerate(lines, 1)
            if (store and re.search(r"\bLOCK_REL\b", line)) or "control.lock" in line}


PLANTED_LOCK_REFS = {  # source -> does it name the control lock's path
    "from aew.engine.store import LOCK_REL\nL = FileLock(root / LOCK_REL)\n": True,
    "from aew.engine.store import ControlStore, LOCK_REL as L\nx = root / L\n": True,
    "from aew.engine import store as S\nx = FileLock(root / S.LOCK_REL)\n": True,
    "import aew.engine.store\nx = aew.engine.store.LOCK_REL\n": True,
    'x = FileLock(root / "local" / "control.lock")\n': True,
    "from aew.dashboard.service import LOCK_REL\nx = FileLock(root / LOCK_REL)\n": False,  # its own endpoint lock
    "from aew.maps.store import LOCK_REL\nx = FileLock(root / LOCK_REL)\n": False,  # the map registry's lock
    'from aew.engine.store import ControlStore\nx = store.control_lock("op")\n': False,  # the one opener: right
}


def test_the_lock_path_detectors_agree_on_every_planted_case_and_on_the_tree():
    """Per file, the finest grain both give: the text detector cannot follow an alias to the line that uses it."""
    for source, names_it in PLANTED_LOCK_REFS.items():
        assert bool(lock_path_refs(source)) is names_it, source
        assert bool(lock_path_refs_by_text(source)) is names_it, source
    src = Path(__file__).resolve().parents[2] / "src" / "aew"
    for f in src.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert bool(lock_path_refs(text)) == bool(lock_path_refs_by_text(text)), f


def test_nothing_but_the_store_names_the_control_locks_path():
    """Mechanical (method, not instance): ``ControlStore.control_lock`` is the only place AEW opens the control lock,
    and it refuses a non-writer before it does. So no module but the store names the lock's path: a ``FileLock`` there
    of its own was how a worker's `history compact` took the lock (review of #231, MJ1)."""
    src = Path(__file__).resolve().parents[2] / "src" / "aew"
    named = {f.relative_to(src).as_posix(): sorted(lock_path_refs(f.read_text(encoding="utf-8")))
             for f in src.rglob("*.py")}
    assert {f: lines for f, lines in named.items() if lines and f != "engine/store.py"} == {}


# ------------------------------------------------------------------ the entry-point table (review of #231, m6 and m9)

def test_every_module_that_runs_as_a_process_is_in_the_entry_point_table_and_every_row_is_one():
    """Both ways (a table pinned against the live tree): every `python -m` module (``if __name__ == "__main__"``, or a
    package's ``__main__.py``), in ``aew`` and in the work-item fact issuer's ``aew_wis`` (STG-04, which WIS-Q01's
    inventory classifies with AEW's own), other than the CLI's is a dotted row, and every dotted row is such a module; every
    other row is a role the CLI's own ``cli_entry_point`` gives some command, in a worker's run or not."""
    import ast
    import tomllib

    root = Path(__file__).resolve().parents[2]
    src = root / "src"

    def runs_as_main(tree: ast.Module) -> bool:
        return any(isinstance(n, ast.If) and isinstance(n.test, ast.Compare)
                   and ast.unparse(n.test).replace("'", '"') == '__name__ == "__main__"' for n in ast.walk(tree))

    modules = {".".join(f.relative_to(src).with_suffix("").parts) for package in ("aew", "aew_wis")
               for f in (src / package).rglob("*.py")
               if f.name == "__main__.py" or runs_as_main(ast.parse(f.read_text(encoding="utf-8")))}
    scripts = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    cli = {"aew.__main__"} | {target.split(":")[0] for target in scripts.values()}
    assert cli <= modules  # the console script's module and `python -m aew` are among them
    roles = {process_kind.cli_entry_point(list(w), env) for w in worker_surface.leaf_commands()
             for env in ({}, worker_env(Path("p")))}
    rows = set(process_kind.ENTRY_POINTS)
    assert {r for r in rows if "." in r} == modules - cli
    assert {r for r in rows if "." not in r} == roles
