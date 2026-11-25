"""The module heap guard: no test module keeps more than :data:`BUDGET_BLOCKS` of the process's memory for itself
(register E363).

#553: twelve test modules each kept a parse of ``src/aew`` in a module global, so one serial process ended with 12.1 M
tracked objects (2.4 GB) and its interpreter's exit outlasted the session deadline's margin; under xdist every worker
paid the same at collection, since a module global is built when the module is imported. Nothing failed the day the
first of them landed. This guard does, in two places:

- **At import, in every process and every lane.** pytest imports a test module when it collects it, in the controller
  of a serial session and in every xdist worker alike, and every lane collects every module. What the import keeps
  beyond the budget fails that module's collection, naming it, what it kept and the budget.
- **After its tests, in a serial session** (no xdist: the ``serial`` lane, the nightly ``reference`` shards, a local
  ``-p no:xdist`` run), where a module's tests run together. What the process keeps across the module's tests, beyond
  the budget, fails the session at its end, naming the module, as the isolation guard does (``lanes.py``). Under xdist
  one module's tests interleave with others' on each worker, so nothing is attributed there.

What is shared is not charged to the module that asked first: a value built by ``shared_setup.once`` and a
session-scoped fixture's setup are shared once per process by definition (``shared_setup.building``). A module-scoped
fixture is torn down before its module is measured, so it is never charged either.

**The measure** is ``sys.getallocatedblocks()``: cheap enough to read around every module (it walks the allocator's
arenas, not the heap). It counts allocations, not bytes: each allocation through Python's object allocator is one
block, whatever its size (one over 512 bytes, which pymalloc hands to the system allocator, is still one). The budget's
"about 30 MB" is an average over the small objects a parse or a list of records is made of. A module over the budget at
that reading is measured again after a full collection, so its uncollected garbage is never charged; only then does it
fail.

**Limits.**

- Garbage left by earlier modules and collected during that confirming collection lowers the module's figure, so a
  module can pass that a fully collected baseline would fail by that much.
- Memory a module's tests leave in a product cache is charged to the module that filled it.
- The first module to import a product or third-party package is charged for that package, so a module's figure
  depends on the collection order: ``test_opencode_units.py`` read 18,638 blocks in the whole suite's collection and
  119,436 collected alone (review of #559, m1).
- pytest's own objects for each test are charged to its module: about 50 blocks per collected item at import, and
  about 80 to 120 per test after its tests (the reports pytest keeps). So a module of about 2,500 to 3,000 tests could
  reach the budget after its tests from that alone; the largest today has 738.
- Allocations a C extension makes with its own allocator are not counted, and under ``PYTHONMALLOC=malloc`` nothing
  is: the reading stays flat and the guard is inert.
"""

from __future__ import annotations

import gc
from collections.abc import Generator
from typing import Any

import pytest
import shared_setup

# 300,000 blocks: allocations, about 30 MB over small objects. A parse of src/aew keeps about 2.2 M blocks (1.0 M
# tracked objects), on Python 3.11 and 3.13 alike, so a module that keeps one, or any build of that order, is over.
# Once #553 and this change shared what they share, no module kept a third of it for itself at import, and none of the
# fast lane's kept 30,000 tracked objects after its tests (the measurement: register E363's note).
BUDGET_BLOCKS = 300_000
GUARD = "module heap guard"


def _charge(before: int, credit_before: int) -> int:
    return (shared_setup.blocks() - before) - (shared_setup.credited() - credit_before)


def _over(before: int, credit_before: int) -> int | None:
    """What the module kept, when it is over the budget after its garbage is collected; else None."""
    if _charge(before, credit_before) <= BUDGET_BLOCKS:
        return None
    gc.collect()
    kept = _charge(before, credit_before)
    return kept if kept > BUDGET_BLOCKS else None


def explain(module: str, kept: int, when: str) -> str:
    return (f"{GUARD}: {module} kept {kept:,} memory blocks {when}, over the budget of {BUDGET_BLOCKS:,} "
            "(tests/helpers/module_heap.py; register E363). Share expensive setup once per process through "
            "shared_setup.once (or a session-scoped fixture), or build it in a fixture that is torn down with the "
            "module, rather than keeping it in a module global or a cache of the module's own.")


def _module_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


class ModuleHeapGuard:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        # Run-phase measurement only where a module's tests run together in this process.
        self.serial = not hasattr(config, "workerinput") and not (
            config.pluginmanager.hasplugin("xdist") and config.getoption("numprocesses", None))
        self.module: str | None = None
        self.start: tuple[int, int] = (0, 0)
        self.problems: list[str] = []

    @pytest.hookimpl(hookwrapper=True)
    def pytest_make_collect_report(self, collector: pytest.Collector) -> Generator[None, Any, None]:
        if not isinstance(collector, pytest.Module):
            yield
            return
        before, credit = shared_setup.blocks(), shared_setup.credited()
        outcome = yield
        report = outcome.get_result()
        kept = _over(before, credit)
        if kept is not None and report.passed:
            outcome.force_result(pytest.CollectReport(
                report.nodeid, "failed", explain(report.nodeid, kept, "at import"), [], sections=report.sections))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(self, fixturedef: pytest.FixtureDef[Any]) -> Generator[None, Any, None]:
        if fixturedef.scope != "session":
            yield
            return
        with shared_setup.building(f"session fixture {fixturedef.argname}"):
            yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, Any, None]:
        if not self.serial:
            yield
            return
        module = _module_of(item.nodeid)
        if module != self.module:
            self.module = module
            self.start = (shared_setup.blocks(), shared_setup.credited())
        yield
        if nextitem is None or _module_of(nextitem.nodeid) != module:
            kept = _over(*self.start)
            if kept is not None:
                self.problems.append(explain(module, kept, "after its tests"))

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        if not self.problems:
            return
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        tr = self.config.pluginmanager.get_plugin("terminalreporter")
        if tr:
            tr.write_sep("!", f"{GUARD}: a test module kept more than its share of memory", red=True)
            for line in self.problems:
                tr.write_line(f"  {line}")


def configure(config: pytest.Config) -> None:
    config.pluginmanager.register(ModuleHeapGuard(config), "aew-module-heap")
