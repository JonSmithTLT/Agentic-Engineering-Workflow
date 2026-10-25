"""The concurrency family of the generated reference (STG-12 S12-2, DOC-03), on the tree: what holds for ``src/aew``.

* the two readers (``ast`` in ``concurrency.py``, tokens in ``concurrency_text.py``, sharing no code) find the same
  ``FileLock`` constructions and the same calls of the lock openers in every module;
* the control lock's one opener is the store's, and its takers are the functions that call it: counted by the token
  reader, and run (a non-writer is refused at each, with the operation the family reports);
* the other locks are the ones the code is read to take, by a hand reading;
* every function the family lists as working without the control lock does so while another holder has it (the
  syntactic check of ``takes_no_lock`` is held against a run, for the ones a test can run);
* a ``FileLock`` planted in a copy of the tree is a record, a second opener of the control lock is refused.

The planted cases of each rule, with their right, wrong and missing cases, are in
``tests/unit/test_reference_concurrency_rules.py``. The heavy lanes run this because it reads ``src`` only.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from conftest import make_git_repo

from aew import process_kind
from aew.engine import configuration, log_compact, outbox
from aew.engine.api import Engine
from aew.engine.base import Kernel
from aew.engine.store import ControlStore
from aew.errors import LockTimeout, PermissionDenied

ROOT = Path(__file__).resolve().parents[2]
WORKER = "aew (worker run)"


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, concurrency, concurrency_text, writers, writers_flow
    finally:
        sys.path.remove(here)
    return common, concurrency, concurrency_text, writers, writers_flow


C, CO, CT, W, F = _tools()
CTX = C.Context(ROOT)
PROGRAM = F.Program.of({n: (s.tree, s.is_package) for n, s in CTX.sources().items() if s.tree is not None})
BUILT = CO.build(CTX)
RECORDS = {r.key: r for r in BUILT.records}
OPENER_NAMES = ["control_lock"]
CONTROL = RECORDS["lock:local/control.lock"]


# ----------------------------------------------------------------------------------------- the two readers agree

def test_the_two_readers_find_the_same_lock_calls_in_every_module():
    """Per module: how many ``FileLock(`` constructions and how many calls named ``control_lock``. The AST reading
    finds a construction by where its callee was imported from, the token reading by its spelling, so a tree that
    imported ``FileLock`` under another name would show here (the planted alias is the AST's alone, in the unit
    module)."""
    ast_counts = CO.call_counts(PROGRAM, OPENER_NAMES)
    disagree = {}
    for name, src in CTX.sources().items():
        if dict(ast_counts[name]) != dict(CT.counts(src.text, OPENER_NAMES)):
            disagree[name] = (dict(ast_counts[name]), dict(CT.counts(src.text, OPENER_NAMES)))
    assert disagree == {}
    total = sum(sum(c.values()) for c in ast_counts.values())
    assert total >= 8, "the readings found almost nothing"


def test_the_family_found_every_filelock_construction_the_token_reader_counts():
    constructions = sum(CT.counts(src.text, []).get(CO.LOCK[1], 0) for src in CTX.sources().values())
    sites = CO.lock_sites(PROGRAM, F.Evaluator(PROGRAM))
    placed = sum(len(r.fact["openers"]) for r in BUILT.records if r.key.startswith("lock:"))
    assert constructions == len(sites) == placed == 5, (constructions, len(sites), placed)  # 5: CAP-1's register


def test_the_live_instances_the_cannot_see_list_names_exist_in_the_tree():
    """Review of #267, C-9: the list names the checkout sync lock (an `O_EXCL` file) and the `threading` locks."""
    queue = CTX.sources()["aew.engine.queue_ops"]
    assert any(q.endswith("checkout_sync_lock_path") for q in PROGRAM.modules["aew.engine.queue_ops"].funcs)
    assert "O_EXCL" in queue.text
    for module in ("aew.dashboard.server", "aew.harness.bridge"):
        text = CTX.sources()[module].text
        assert any(f"threading.{kind}(" in text for kind in ("Lock", "RLock", "Condition", "Event")), module


# --------------------------------------------------------------------------------------------- the control lock

def test_the_control_locks_only_opener_is_the_stores_and_its_takers_are_the_functions_that_call_it(tmp_path):
    """The check the family's ``complete-by-construction`` names for the control lock, with
    ``test_nothing_but_the_store_names_the_control_locks_path`` (tests/integration/test_non_writer_reads.py).

    The opener is one function, the store's. Its takers are counted twice: from the records, and from the token
    reader's count of the calls of ``control_lock`` per module. And each taker's operation is the one a non-writer is
    refused with when that function is called, so the operation names the report gives are the ones the code uses."""
    fact = CONTROL.fact
    assert fact["openers"] == [{"module": "aew.engine.store", "symbol": "ControlStore.control_lock"}]
    assert fact["refused_in_non_writer"] is True and fact["control"] is True
    takers = {(t["module"], t["symbol"]): t["operation"] for t in fact["takers"]}
    assert takers == {
        ("aew.engine.store", "ControlStore.session"): "ControlStore.session",
        ("aew.engine.store", "ControlStore.read"): "ControlStore.read",
        ("aew.engine.store", "ControlStore.create"): "ControlStore.create",
        ("aew.engine.log_compact", "compact.control_lock"): "history compact",
    }
    by_module: dict[str, int] = {}
    for module, _symbol in takers:
        by_module[module] = by_module.get(module, 0) + 1
    called = {name: CT.counts(src.text, OPENER_NAMES).get("control_lock", 0) for name, src in CTX.sources().items()}
    assert {m: n for m, n in called.items() if n} == by_module

    engine = Kernel(*_initialized(tmp_path))
    store, fresh = ControlStore(engine.aew_root), ControlStore(tmp_path / "fresh" / ".aew")
    refused = {}
    with process_kind.declared_as(WORKER):
        for taker, call in (("ControlStore.read", store.read),
                            ("ControlStore.session", lambda: store.session().__enter__()),
                            ("ControlStore.create", lambda: fresh.create({}, {})),
                            ("compact", lambda: log_compact.compact(store))):
            with pytest.raises(PermissionDenied) as denied:
                call()
            refused[taker] = denied.value.details["operation"]
    assert refused == {"ControlStore.read": "ControlStore.read", "ControlStore.session": "ControlStore.session",
                       "ControlStore.create": "ControlStore.create", "compact": "history compact"}
    assert set(refused.values()) == set(takers.values())


def _initialized(tmp_path: Path) -> tuple[Path, Path]:
    e = Engine.initialize(make_git_repo(tmp_path / "repo", {"README.md": "# c\n"}), project_id="cc")
    return e.repo_root, e.aew_root


# -------------------------------------------------------------------------------------------- the other locks

KNOWN_LOCKS = {
    "local/dashboard/endpoint.lock": ("aew.dashboard.service", "Service._lock",
                                      {"Service.start", "Service._remove_endpoint"}),
    "local/operator/endpoint.lock": ("aew.harness.operator_endpoint", "OperatorEndpoint._claim",
                                     {"OperatorEndpoint._claim"}),
    "local/maps/registry.lock": ("aew.maps.store", "select", {"select"}),
    # the host's capability register (STG-15, CAP-1): outside `.aew`, so unplaced, keyed by its opener
    "unplaced:aew.capability.store:locked": ("aew.capability.store", "locked", {"locked"}),
}


def test_the_locks_are_the_five_the_code_was_read_to_take():
    paths = sorted(k.removeprefix("lock:") for k in RECORDS if k.startswith("lock:"))
    assert paths == sorted(["local/control.lock", *KNOWN_LOCKS])
    for path, (module, symbol, takers) in KNOWN_LOCKS.items():
        fact = RECORDS[f"lock:{path}"].fact
        assert fact["openers"] == [{"module": module, "symbol": symbol}], path
        assert {t["symbol"] for t in fact["takers"]} == takers and all(t["module"] == module for t in fact["takers"])
        assert fact["control"] is False and fact["refused_in_non_writer"] is False, path
        assert RECORDS[f"lock:{path}"].coverage["label"] == C.LOWER


def test_the_dashboards_lock_is_taken_only_from_the_dashboard_server_and_the_control_lock_only_in_a_writer():
    dashboard = RECORDS["lock:local/dashboard/endpoint.lock"].fact["takers"]
    assert {e for t in dashboard for e in t["entry_points"]} == {"aew dashboard serve"}
    for t in CONTROL.fact["takers"]:
        assert "store_writer" in t["entry_kinds"], t


# --------------------------------------------------------------------------------- the members, run with the lock held

MEMBER_KEYS = sorted(k for k in RECORDS if k.startswith("lock-free:"))
STATIC_ONLY = {
    "aew.engine.log_compact:build_segment": "needs a log of a whole segment (SEGMENT_SIZE revisions) to run",
    "aew.engine.log_compact:verify_against_unsealed": "needs a sealed segment beside its unsealed files to run",
}


def test_the_members_are_the_ten_the_code_says_work_without_the_control_lock_and_each_takes_no_lock():
    assert [k.removeprefix("lock-free:") for k in MEMBER_KEYS] == sorted([
        "aew.engine.configuration:read_committed", "aew.engine.log_compact:_unlink",
        "aew.engine.log_compact:build_segment", "aew.engine.log_compact:verify_against_unsealed",
        "aew.engine.outbox:LogView", "aew.engine.outbox:bump_wake", "aew.engine.outbox:read_transitions",
        "aew.engine.outbox:wait_for", "aew.engine.outbox:wake_mark", "aew.engine.store:ControlStore.read_committed"])
    assert [k for k in MEMBER_KEYS if not RECORDS[k].fact["takes_no_lock"]] == []
    silent = [k.removeprefix("lock-free:") for k in MEMBER_KEYS if not RECORDS[k].fact["says"]]
    assert silent == ["aew.engine.outbox:bump_wake", "aew.engine.outbox:wait_for", "aew.engine.outbox:wake_mark"], (
        "the code says in words that it needs no lock for each member but the wake mark's three, which are listed "
        "because the wake signal is advisory (outbox D4) and `takes_no_lock` is the call graph's finding")


def _held(engine: Kernel):
    """The control lock held by another store of this process, and the witness that it is: a locking read of the
    engine's own store cannot take it."""
    engine.store.read()  # recovered once by a writer, as the engine always leaves it
    engine.store.lock_timeout = 0.2
    holder = ControlStore(engine.aew_root)
    return holder, holder.control_lock("held by the test")


@pytest.fixture
def engine(tmp_path) -> Kernel:
    return Kernel(*_initialized(tmp_path))


def test_each_member_a_test_can_run_works_while_another_holder_has_the_control_lock(engine):
    state = engine.store.read()
    since = (state.get("outbox") or {}).get("since", 0)
    scrap = engine.aew_root / "local" / "scrap.tmp"
    scrap.write_text("x", encoding="utf-8")
    ran: dict[str, object] = {}
    _holder, lock = _held(engine)
    with lock:
        with pytest.raises(LockTimeout):
            engine.store.read()  # the witness: the lock is held, and a taker of it waits
        with pytest.raises(LockTimeout):
            with engine.store.session():
                pass
        ran["aew.engine.store:ControlStore.read_committed"] = engine.store.read_committed()["revision"]
        ran["aew.engine.configuration:read_committed"] = configuration.read_committed(engine).manifest_raw is not None
        view = outbox.LogView(engine.aew_root, since)
        ran["aew.engine.outbox:LogView"] = view.root == engine.aew_root
        ran["aew.engine.outbox:read_transitions"] = len(list(outbox.read_transitions(
            engine.aew_root, since, ran["aew.engine.store:ControlStore.read_committed"], outbox=state.get("outbox"))))
        outbox.bump_wake(engine.aew_root, 1)
        ran["aew.engine.outbox:bump_wake"] = outbox.wake_mark(engine.aew_root) is not None
        ran["aew.engine.outbox:wake_mark"] = outbox.wake_mark(engine.aew_root)
        ran["aew.engine.outbox:wait_for"] = outbox.wait_for(lambda: "seen", engine.aew_root, timeout=0.5)
        ran["aew.engine.log_compact:_unlink"] = log_compact._unlink(scrap)
    assert not scrap.exists()
    assert ran["aew.engine.outbox:wait_for"] == "seen" and ran["aew.engine.log_compact:_unlink"] is True
    assert all(v is not None for v in ran.values()) and ran["aew.engine.outbox:bump_wake"] is True
    members = {k.removeprefix("lock-free:") for k in MEMBER_KEYS}
    assert {*ran, *STATIC_ONLY} == members, "a member neither run nor excused"


def test_a_member_a_test_cannot_run_is_one_the_family_lists_with_the_reason_it_is_only_read():
    assert all(reason for reason in STATIC_ONLY.values())
    names = {k.removeprefix("lock-free:") for k in MEMBER_KEYS}
    assert set(STATIC_ONLY) <= names


# ------------------------------------------------------------------------------------------ planted in a tree copy

PLANT = ("from aew.engine.lock import FileLock\n\n\n"
         "def planted(aew_root):\n"
         "    with FileLock(aew_root / 'local' / 'planted.lock', timeout=1.0):\n"
         "        pass\n")
SECOND_OPENER = ("from aew.engine.lock import FileLock\n\n\n"
                 "def planted_second(aew_root):\n"
                 "    return FileLock(aew_root / 'local' / 'control.lock')\n")
CALLER = ("from aew.engine.store import ControlStore\n\n\n"
          "def planted_caller(store: ControlStore):\n"
          "    with store.control_lock('planted operation'):\n"
          "        pass\n")


def planted_copy(tmp_path: Path, extra: str) -> Path:
    shutil.copytree(ROOT / "src" / "aew", tmp_path / "src" / "aew", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "src" / "aew" / "planted.py").write_text(extra, encoding="utf-8")
    return tmp_path


def test_a_lock_planted_in_a_copy_of_the_tree_is_a_record_with_its_taker(tmp_path):
    built = CO.build(C.Context(planted_copy(tmp_path, PLANT)))
    records = {r.key: r for r in built.records}
    fact = records["lock:local/planted.lock"].fact
    assert fact["openers"] == [{"module": "aew.planted", "symbol": "planted"}] and fact["timeout"] == "1.0"
    assert [(t["module"], t["symbol"]) for t in fact["takers"]] == [("aew.planted", "planted")]
    assert set(records) == {*RECORDS, "lock:local/planted.lock"}


def test_a_second_opener_of_the_control_lock_planted_in_a_copy_of_the_tree_is_refused(tmp_path):
    with pytest.raises(C.ReferenceError, match=r"the control lock local/control\.lock is opened in 2 places"):
        CO.build(C.Context(planted_copy(tmp_path, SECOND_OPENER)))


def test_a_caller_of_the_control_lock_planted_in_a_copy_of_the_tree_is_one_more_taker(tmp_path):
    built = CO.build(C.Context(planted_copy(tmp_path, CALLER)))
    takers = {(t["module"], t["symbol"]): t for t in {r.key: r for r in built.records}["lock:local/control.lock"]
              .fact["takers"]}
    planted = takers[("aew.planted", "planted_caller")]
    assert planted["operation"] == "planted operation" and planted["entry_points"] == []
    assert len(takers) == len(CONTROL.fact["takers"]) + 1
