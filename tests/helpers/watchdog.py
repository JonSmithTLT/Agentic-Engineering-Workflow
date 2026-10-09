"""A per-test hang watchdog (docs/implementation/testing-and-ci-strategy.md §3, "A test that hangs fails by name").

On 2026-10-08 two Linux integration shards hung until GitHub cancelled the job at its 30-minute limit. A cancelled job
writes no lane report and prints nothing, so the run said only "lanes: cancelled" and named no test. With
``--test-timeout S`` a test still running after S seconds fails by name, with every thread's stack in its report:

- **POSIX:** a ``SIGALRM`` timer. Its handler writes every thread's stack and raises in the test, so a blocking call is
  interrupted and the test fails in place; the run (and xdist) carries on. If the test's teardown then hangs as well,
  a second alarm writes the stacks again and ends the process.
- **Windows** (no ``SIGALRM``): ``faulthandler.dump_traceback_later`` writes the stacks to the dump file and the test
  runs on. Nothing can interrupt a blocking call there without ending the process, and ending an xdist worker makes
  xdist fail the whole session (an internal assertion when the replacement worker finishes), so the job still runs to
  its limit; the uploaded dump names the test. Every stall seen so far was on Linux.

The limit catches hangs, not slowness: it sits well above the slowest recorded test, and a test that grows towards it
is a regression to find, never a reason to raise it.

The stacks also go to a dump file in ``--hang-dir`` (default: the lane report's directory, which CI uploads even when
a job fails; else the system temporary directory). Each process has one file, emptied after every test that finishes,
so a non-empty file after a run is a hang.
"""

from __future__ import annotations

import faulthandler
import os
import signal
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import IO, Any

import pytest

HEADER = "aew hang watchdog: "
USE_ALARM = hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer")


def addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("aew-lanes")
    group.addoption("--test-timeout", dest="aew_test_timeout", type=float, default=0.0, metavar="SECONDS",
                    help="fail a test still running after SECONDS, with every thread's stack (0: off)")
    group.addoption("--hang-dir", dest="aew_hang_dir", default=None, metavar="DIR",
                    help="where the watchdog writes stack dumps (default: the lane report's directory)")


def hang_dir(config: pytest.Config) -> Path:
    explicit = config.getoption("aew_hang_dir")
    if explicit:
        return Path(explicit)
    report = config.getoption("aew_lane_report", None)
    return Path(report).resolve().parent if report else Path(tempfile.gettempdir())


class HungTest(BaseException):
    """Raised in a hung test by the alarm. A BaseException, so a test's ``except Exception`` cannot swallow it."""


class HangWatchdog:
    def __init__(self, config: pytest.Config, timeout: float) -> None:
        self.timeout = timeout
        self.dir = hang_dir(config)
        worker = getattr(config, "workerinput", {}).get("workerid", "main")
        self.path = self.dir / f"hang-{worker}-{os.getpid()}.txt"
        self._file: IO[str] | None = None
        self._fired = 0
        self._hangs = 0

    def _dump_file(self) -> IO[str]:
        if self._file is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, "w+", encoding="utf-8")  # noqa: SIM115  (held for the session)
        return self._file

    def _reset(self, header: str) -> IO[str]:
        f = self._dump_file()
        f.seek(0)
        f.truncate()
        f.write(header)
        f.flush()
        return f

    def _on_alarm(self, signum: int, frame: Any) -> None:
        self._fired += 1
        f = self._dump_file()
        again = " (its teardown hung too; ending the process)" if self._fired > 1 else ""
        f.write(f"\n--- alarm {self._fired}{again}\n")
        f.flush()
        faulthandler.dump_traceback(file=f, all_threads=True)
        f.flush()
        if self._fired > 1:  # the teardown hung too: nothing in this process can be trusted to finish
            os._exit(1)
        signal.setitimer(signal.ITIMER_REAL, self.timeout)  # one more period for the teardown
        f.seek(0)
        raise HungTest(f.read())

    def _header(self, item: pytest.Item) -> str:
        return f"{HEADER}{item.nodeid} was still running after {self.timeout:g}s; every thread's stack:\n"

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item, nextitem: pytest.Item | None) -> Generator[None, Any, None]:
        self._fired = 0
        f = self._reset(self._header(item))
        if USE_ALARM:
            previous = signal.signal(signal.SIGALRM, self._on_alarm)
            signal.setitimer(signal.ITIMER_REAL, self.timeout)
        else:  # pragma: windows-only
            previous = None
            faulthandler.dump_traceback_later(self.timeout, file=f)
        try:
            yield
        finally:
            if USE_ALARM:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
            else:  # pragma: windows-only
                faulthandler.cancel_dump_traceback_later()
            if not USE_ALARM:  # pragma: windows-only (the dump, if it ran, is past the header)
                if os.fstat(f.fileno()).st_size > len(self._header(item).encode("utf-8")):
                    self._fired = 1  # faulthandler wrote through the descriptor: only the size shows it
            if self._fired:  # keep this hang's stacks on disk: the next test starts a new file
                assert self._file is not None
                self._file.close()
                self._file = None
                self.path.replace(self.path.with_name(f"{self.path.stem}-{self._hangs}.txt"))
                self._hangs += 1
            else:
                self._reset("")  # a test that finished leaves no dump

    def pytest_unconfigure(self, config: pytest.Config) -> None:
        if self._file is not None:
            self._file.close()
            self.path.unlink(missing_ok=True)  # emptied after the last test; a hang's file was renamed

    @pytest.hookimpl(optionalhook=True)
    def pytest_handlecrashitem(self, crashitem: str, report: pytest.TestReport, sched: Any) -> None:
        """xdist's report for a worker that died mid-test: attach the watchdog's dump, when it names this test."""
        for path in sorted(self.dir.glob("hang-*.txt")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if text.startswith(f"{HEADER}{crashitem} "):
                report.longrepr = f"{report.longrepr}\n{text}\n(the dump is kept at {path})"
                return


def configure(config: pytest.Config) -> None:
    timeout = float(config.getoption("aew_test_timeout") or 0.0)
    if timeout > 0:
        config.pluginmanager.register(HangWatchdog(config, timeout), "aew-hang-watchdog")
