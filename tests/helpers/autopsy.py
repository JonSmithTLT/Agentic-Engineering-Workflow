"""Every hang or marked failure leaves an autopsy (the hang-and-flake diagnosis plan, G3 H1 and H4).

It extends the hang watchdog (``watchdog.py``) rather than duplicating it: nothing here arms faulthandler (its single
timer is the watchdog's). :meth:`AutopsyPlugin.collect` runs:

- **when the watchdog fires:** on POSIX inside its ``SIGALRM`` handler, before it raises; on Windows from an ordinary
  watcher thread armed just **after** the watchdog's deadline and cancelled at the end of every test. That thread
  never writes to the watchdog's dump file (the watchdog detects a hang by that file growing). If the hang holds the
  GIL the thread cannot run: the evidence is then the watchdog's faulthandler dump and the session sentinel's output
  (``session_deadline.py``), and no more is claimed;
- **at the session deadline** (``session_deadline.py``), for the test still running;
- **for any failure of a test marked** ``@pytest.mark.autopsy``;
- **for a crashed xdist worker**, from the controller (``pytest_handlecrashitem`` and ``pytest_testnodedown``).

It writes ``<hang-dir>/autopsy/<test>/``, only through ``harness_diagnostics`` (redacted, capped, never ``.json``):

- ``reason.txt``, ``failure.txt`` (the failure as pytest reports it);
- ``stacks.txt``: every thread of the test process (``sys._current_frames``), and ``watchdog-dump.txt``, the
  watchdog's own faulthandler dump for this test when there is one;
- ``processes.txt``: the processes under the test process, by (pid, start time) (``proctree``);
- ``children/``: each helper child's diagnostics (``childdiag``: periodic stacks, both generations, uncaught
  exceptions, output, flight recorder), copied from the test's private directory (:func:`child_dir`);
- ``recorder.jsonl.txt``: the test process's flight recorder; ``file-holders.txt``: who holds each path of the
  recorder's last failed I/O;
- ``workdir/``: the test's ``tmp_path`` and every directory a helper registered (:func:`register_workdir`), copied,
  never moved: their owner removes the originals as usual (H4).

The test still fails with its own message, plus an ``aew autopsy`` section naming the directory.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Generator
from pathlib import Path
from typing import Any

import flight_recorder
import harness_diagnostics as hd
import proctree
import pytest

PLUGIN_NAME = "aew-autopsy"
MARKER = "autopsy"
WATCHER_GRACE_S = 1.0  # the Windows watcher fires this long after the watchdog's deadline: its dump comes first
CHILD_ROOT_KEY = "aew_childdiag_root"

_plugin: AutopsyPlugin | None = None


def _hang_dir(config: pytest.Config) -> Path:
    import watchdog

    return watchdog.hang_dir(config)


def thread_stacks() -> str:
    names = {t.ident: t.name for t in threading.enumerate()}
    parts = []
    for ident, frame in sys._current_frames().items():
        parts.append(f"--- thread {names.get(ident, '?')} ({ident})\n" + "".join(traceback.format_stack(frame)))
    return f"pid {os.getpid()}, {len(parts)} threads, at {time.strftime('%H:%M:%S')}\n\n" + "\n".join(parts)


class AutopsyPlugin:
    def __init__(self, config: pytest.Config) -> None:
        self.config = config
        self.root = _hang_dir(config) / hd.AUTOPSY_DIR
        self.worker = getattr(config, "workerinput", {}).get("workerid", "main")
        self._child_root_path: Path | None = None
        self.item: pytest.Item | None = None
        self.workdirs: list[Path] = []
        self.collected: dict[str, Path] = {}
        self.counts: dict[str, int] = {}
        self.budgets: dict[str, hd.Budget] = {}
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()

    @property
    def child_root(self) -> Path:
        """Where helper children write their raw diagnostics: under the session's base temporary directory (outside
        the report directory, so nothing unredacted is ever uploaded); one root for the controller and its workers.
        Decided on first use: pytest's temporary directory factory is configured after this plugin."""
        if self._child_root_path is None:
            given = getattr(self.config, "workerinput", {}).get(CHILD_ROOT_KEY)
            if given:
                self._child_root_path = Path(given)
            else:
                factory = getattr(self.config, "_tmp_path_factory", None)
                try:
                    base = Path(factory.getbasetemp()) if factory is not None else None
                except OSError:
                    base = None
                self._child_root_path = (base or Path(tempfile.gettempdir()) / f"aew-childdiag-{os.getpid()}"
                                         ) / "childdiag"
        return self._child_root_path

    @pytest.hookimpl(optionalhook=True)
    def pytest_configure_node(self, node: Any) -> None:
        node.workerinput[CHILD_ROOT_KEY] = str(self.child_root)

    # ------------------------------------------------------------------ the running test

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, Any, None]:
        with self._lock:
            self.item = item
            self.workdirs = []
        flight_recorder.record("test_start", test=item.nodeid)
        try:
            yield
        finally:
            self.disarm()
            flight_recorder.record("test_end", test=item.nodeid)
            with self._lock:
                self.item = None
                self.workdirs = []

    def child_dir(self) -> Path:
        name = self.item.nodeid if self.item is not None else f"outside-a-test-{os.getpid()}"
        path = self.child_root / hd.safe_dir(name)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------ the watchdog's hooks

    def watchdog_fired(self, timeout: float) -> None:
        """POSIX: called from the watchdog's alarm handler, before it raises in the test."""
        self.collect_current(f"the hang watchdog fired: the test was still running after {timeout:g}s")

    def arm(self, timeout: float) -> None:
        """Windows: an ordinary thread that collects just after the watchdog's faulthandler dump is due."""
        self.disarm()
        timer = threading.Timer(timeout + WATCHER_GRACE_S, self.collect_current,
                                (f"the hang watchdog fired: the test was still running after {timeout:g}s",))
        timer.daemon = True
        timer.name = "aew-autopsy-watcher"
        self._timer = timer
        timer.start()

    def disarm(self) -> None:
        timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def collect_current(self, reason: str) -> Path | None:
        item = self.item
        if item is None:
            return None
        return self.collect(item.nodeid, reason, item=item)

    # ------------------------------------------------------------------ the autopsy

    def dest(self, test_id: str) -> Path:
        return self.root / hd.safe_dir(test_id)

    def collect(self, test_id: str, reason: str, *, item: pytest.Item | None = None, failure: str | None = None,
                own_stacks: bool = True) -> Path:
        """Write this test's autopsy. Never raises: an error is itself written down, and the rest carries on."""
        with self._lock:
            dest = self.dest(test_id)
            budget = self.budgets.setdefault(test_id, hd.Budget())  # one total cap for the test's whole autopsy
            errors: list[str] = []
            self.counts[test_id] = n = self.counts.get(test_id, 0) + 1
            # Each collect keeps its own files: a deadline after a watchdog fire, or the controller's collect for a
            # worker that crashed, never overwrites an earlier one (``stacks.gw1-1.txt``, ``stacks.main-1.txt``).
            tag = f".{self.worker}-{n}"

            def name(base: str) -> str:
                return base.replace(".jsonl", "") + tag + (".jsonl" if base.endswith(".jsonl") else "")

            def step(what: str, fn: Any) -> None:
                try:
                    fn()
                except Exception as exc:  # diagnostics never replace the failure they describe
                    errors.append(f"{what}: {type(exc).__name__}: {exc}")

            step("reason", lambda: hd.write_text(dest, "reason", f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                                                 f"[{self.worker} pid {os.getpid()}] {test_id}: {reason}\n",
                                                 budget=budget, append=True))
            if failure:
                step("failure", lambda: hd.write_text(dest, name("failure"), failure, budget=budget))
            if own_stacks:
                step("stacks", lambda: hd.write_text(dest, name("stacks"), thread_stacks(), budget=budget))
            step("watchdog dump", lambda: self._watchdog_dump(test_id, dest, budget))
            step("processes", lambda: hd.write_text(dest, name("processes"), self._processes(), budget=budget))
            step("children", lambda: self._children(test_id, dest, budget, errors))
            step("recorder", lambda: hd.write_text(dest, name("recorder.jsonl"), flight_recorder.lines(),
                                                   budget=budget))
            step("file holders", lambda: hd.write_text(
                dest, name("file-holders"), proctree.describe_holders(proctree.holders(flight_recorder.failed_paths())),
                budget=budget))
            step("workdirs", lambda: self._workdirs(item, dest, budget, errors))
            step("bounds", lambda: hd.write_text(dest, "bounds", bounds_in_force(), budget=budget))
            if budget.refused or errors:
                hd.write_text(dest, "collect-notes", "".join(f"{e}\n" for e in errors + budget.refused),
                              append=True)
            self.collected[test_id] = dest
            return dest

    def _watchdog_dump(self, test_id: str, dest: Path, budget: hd.Budget) -> None:
        import watchdog

        hang = _hang_dir(self.config)
        for path in sorted(hang.glob("hang-*.txt")) if hang.is_dir() else []:
            text = hd._read(path).decode("utf-8", "replace")
            if text.startswith(f"{watchdog.HEADER}{test_id} "):
                hd.write_text(dest, f"watchdog-dump-{path.stem}", text, budget=budget)

    def _processes(self) -> str:
        me = proctree.identity(os.getpid())
        if me is None:
            return "this process's start time could not be read\n"
        return proctree.describe(proctree.descendants(me, proctree.table()),
                                 title=f"processes under the test process (pid {os.getpid()}, worker {self.worker}):")

    def _children(self, test_id: str, dest: Path, budget: hd.Budget, errors: list[str]) -> None:
        src = self.child_root / hd.safe_dir(test_id)
        if src.is_dir():
            errors += hd.copy_tree(src, dest / "children", budget=budget)[1]

    def _workdirs(self, item: pytest.Item | None, dest: Path, budget: hd.Budget, errors: list[str]) -> None:
        dirs: list[tuple[str, Path]] = []
        tmp = getattr(item, "funcargs", {}).get("tmp_path") if item is not None else None
        mark = item.get_closest_marker(MARKER) if item is not None else None
        whole = mark is None or mark.kwargs.get("tmp_path", True)  # autopsy(tmp_path=False): the registered parts only
        if isinstance(tmp, Path) and whole:
            dirs.append(("tmp_path", tmp))
        dirs += [(hd.safe_dir(str(p)), p) for p in self.workdirs if not (tmp and whole and Path(p) == tmp)]
        for name, path in dirs:
            if path.is_dir():
                errors += hd.copy_tree(path, dest / "workdir" / name, budget=budget)[1]
            elif path.is_file():
                try:
                    hd.copy_file(path, dest / "workdir", path.name, budget=budget)
                except OSError as exc:
                    errors.append(f"{path.name}: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ marked failures and crashed workers

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: pytest.Item, call: pytest.CallInfo[None]) -> Generator[None, Any, None]:
        outcome = yield
        rep: pytest.TestReport = outcome.get_result()
        if rep.failed and item.get_closest_marker(MARKER) is not None:
            self.collect(item.nodeid, f"failed in {rep.when}", item=item, failure=str(rep.longrepr))
        dest = self.collected.get(item.nodeid)
        if dest is not None and (rep.failed or rep.when == "call"):
            rep.sections.append(("aew autopsy", f"the autopsy is kept in {dest}"))
        if rep.failed:
            crashed = native_crashes(self.child_root / hd.safe_dir(item.nodeid))
            if crashed:  # a helper child that died natively names itself (review of #217, m5)
                rep.sections.append(("aew helper child crash", crashed))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, Any, None]:
        """Each module's end, after the teardown itself (review of #217, N1): a process a fixture ends in its teardown,
        the module's own fixtures included, is never reported as leaked."""
        yield
        if nextitem is None or nextitem.module is not item.module:
            self.scan_leaks(f"after {item.module.__name__ if item.module else item.nodeid}")

    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        self.scan_leaks("at session end")

    def scan_leaks(self, when: str) -> None:
        """Report-only (review of #217, (a); enforced later, G3b): processes still running whose command line or
        working directory lies in this process's base temporary directory, each named by the test directory it is in.
        Never fails anything; written to ``leaked-processes.<worker>.txt``."""
        try:
            found = leaked_processes(self.basetemp())
            if found:
                hd.write_text(self.root, f"leaked-processes.{self.worker}", f"{time.strftime('%H:%M:%S')} {when}:\n"
                              + "".join(f"  {test}: pid {p.pid} {p.cmdline or p.exe}\n" for test, p in found),
                              append=True)
        except Exception:  # report-only: a scan's own failure is not the test's  # noqa: BLE001, S110
            pass

    def basetemp(self) -> Path | None:
        factory = getattr(self.config, "_tmp_path_factory", None)
        try:
            return Path(factory.getbasetemp()) if factory is not None else None
        except OSError:
            return None

    @pytest.hookimpl(optionalhook=True)
    def pytest_handlecrashitem(self, crashitem: str, report: pytest.TestReport, sched: Any) -> None:
        dest = self.collect(crashitem, "its xdist worker crashed while running it", failure=str(report.longrepr),
                            own_stacks=False)
        report.longrepr = f"{report.longrepr}\n(aew autopsy: {dest})"

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: Any, error: Any) -> None:
        if not error:
            return
        workerid = getattr(node, "gateway", None) and node.gateway.id
        hd.write_text(self.root, f"worker-{workerid}-down",
                      f"{time.strftime('%Y-%m-%d %H:%M:%S')} worker {workerid} went down: {error}\n"
                      f"crashed tests' autopsies: {', '.join(str(p) for p in self.collected.values()) or 'none'}\n")


# ---------------------------------------------------------------------------------------------- for helpers and tests

def native_crashes(children: Path) -> str:
    """What the helper children's fatal-error dumps say (``fatal-<pid>.txt``, childdiag): a native crash, such as the
    known faulthandler residual on Windows CPython 3.13, names itself in the failure instead of reading as a mystery.
    On Windows an entry can also be an exception a library handled itself: a crash also ends its process."""
    lines = []
    for path in sorted(children.glob("fatal-*.txt")) if children.is_dir() else []:
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            lines.append(f"{path.name}: {text.splitlines()[0]} (see the file for every thread's stack)")
    return "\n".join(lines)


def leaked_processes(basetemp: Path | None) -> list[tuple[str, proctree.Proc]]:
    """(test directory, process) for every process, not this one, whose command line or working directory (Linux)
    lies under ``basetemp``. pytest's numbered directory is the test's name, so no marker is needed, under xdist
    too (each worker scans its own base temporary directory)."""
    if basetemp is None:
        return []
    base = str(basetemp.resolve())
    found = []
    for p in proctree.table():
        if p.pid == os.getpid():
            continue
        where = ""
        if base in (p.cmdline or ""):
            where = p.cmdline.split(base, 1)[1]
        elif sys.platform.startswith("linux"):
            try:
                cwd = os.readlink(f"/proc/{p.pid}/cwd")
            except OSError:
                cwd = ""
            if cwd.startswith(base):
                where = cwd[len(base):]
        if where:
            test = where.replace("\\", "/").strip("/").split("/")[0].strip('"') or "?"
            found.append((test, p))
    return found


def current() -> AutopsyPlugin | None:
    return _plugin


def child_dir() -> Path | None:
    """The running test's private directory for helper children's diagnostics (``childdiag``), or None outside a
    pytest session with the autopsy plugin."""
    return _plugin.child_dir() if _plugin is not None else None


def mark_helper_dir(directory: Path, *, interval: float | None = None) -> Path | None:
    """For a helper the product starts (the fake OpenCode launcher reads it): write ``<directory>/childdiag-dir.txt``
    naming the running test's children directory (and, for a test of the mechanism only, a shorter dump interval).
    Returns that directory, or None outside an autopsy session."""
    import childdiag

    where = child_dir()
    if where is not None:
        Path(directory).mkdir(parents=True, exist_ok=True)
        text = str(where) + (f"\n{interval:g}" if interval is not None else "")
        (Path(directory) / childdiag.DIR_FILE).write_text(text, encoding="utf-8")
    return where


def bounds_in_force() -> str:
    """Every bound the helpers declared (``bounds.py``), as the autopsy keeps them: with the test's own limit, they
    show whether the wait that ran out was the innermost one."""
    import bounds

    rows = [f"{b.name}: {b.seconds:g}s" + (f" within {b.within}" if b.within else "")
            + (f" (lanes {', '.join(sorted(b.lanes))})" if b.lanes else "") + (f": {b.why}" if b.why else "")
            for b in sorted(bounds.BOUNDS.values(), key=lambda b: b.name)]
    return "\n".join(rows or ["no helper bound was declared in this process"]) + "\n"


def register_workdir(path: Path) -> None:
    """A helper's own temporary directory (or one file), copied (redacted, capped) into the autopsy if the test
    fails."""
    if _plugin is not None:
        _plugin.workdirs.append(Path(path))


def addoption(parser: pytest.Parser) -> None:
    pass  # the autopsy has no option of its own: it writes under --hang-dir (watchdog.py)


def configure(config: pytest.Config) -> None:
    global _plugin
    config.addinivalue_line("markers", f"{MARKER}: keep an autopsy (stacks, processes, children, files) if it fails")
    _plugin = AutopsyPlugin(config)
    config.pluginmanager.register(_plugin, PLUGIN_NAME)


def unconfigure() -> None:
    global _plugin
    _plugin = None
