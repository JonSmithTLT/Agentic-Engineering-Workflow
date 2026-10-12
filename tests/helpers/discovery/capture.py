"""D2's capture plugin (discovery-layer spec v3.4, §2.1, m5): every human- or Lead-facing output the existing suite
produces, judged by D2's rules. It changes no product code and no test's outcome: it only observes.

**Hooks.** The CLI's in-process entry (``aew.cli.main._main``: its stdout and its error renderer's stderr, teed for
the call), the typed surface's result builder (``aew.surface.run.run_tool``), and ``subprocess.run`` for the ``aew``
processes tests start (``python -m aew``, or an ``aew`` executable), whose stdout and stderr are read. A process a
test drives through ``Popen`` (a Lead session, the MCP server) is not seen.

**Output-site key.** ``cli:aew <command words>|<refusal code or "result">`` for the CLI, the words read from the
argument vector with the live parser; ``tool:<name>|<refusal code or "result">`` for the typed surface. Message text
never enters a key: messages carry temporary paths and live ids, and keys are committed to the allow-list.

**Activation and output.** On with ``--discovery-out PATH``, or beside a lane report (``--lane-report X.json`` writes
``X.discovery.json``), so every CI lane job reports with no change to its command. Under xdist each worker hands its
findings to the controller (``workeroutput``), which merges them and writes the one file at the end of the session.
"""

from __future__ import annotations

import functools
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from discovery import rules

SCHEMA = "aew/discovery-findings/v1"
WORKER_KEY = "aew_discovery"


def out_path_for(lane_report: Path) -> Path:
    """The findings file beside a lane report (another schema, so assurance's report loader skips it)."""
    return lane_report.with_name(lane_report.stem + ".discovery.json")


def out_path(config: pytest.Config) -> Path | None:
    explicit = config.getoption("aew_discovery_out", None)
    if explicit:
        return Path(explicit)
    report = config.getoption("aew_lane_report", None)
    return out_path_for(Path(report)) if report else None


def _current_test() -> str:
    return (os.environ.get("PYTEST_CURRENT_TEST") or "").rsplit(" (", 1)[0]


class Recorder:
    """The findings of one process: ``key -> {rule, site, count, detail, test}``. Product threads still running in a
    test (a steering loop, a broker) may record concurrently, so every change and every snapshot holds the lock.
    ``judge`` is the rules' ``check``; a test passes its own to inject a defect without touching the session's."""

    def __init__(self, judge: Any = None) -> None:
        self.findings: dict[str, dict[str, Any]] = {}
        self.outputs = 0
        self.errors: dict[str, int] = {}
        self._judged: set[str] = set()
        self._judge = judge
        self._lock = threading.Lock()

    def error(self, exc: BaseException) -> None:
        name = f"{type(exc).__name__}: {str(exc)[:200]}"
        with self._lock:
            self.errors[name] = self.errors.get(name, 0) + 1

    def record(self, output: rules.Output) -> None:
        """Judge one output, at most once per identical (site, content). Never raises: a defect here must not change a
        test's outcome, so it is counted and reported instead (and a counted error fails D2's ratchet)."""
        try:
            digest = hashlib.sha256(json.dumps([output.site, output.payload, output.text, output.refusal,
                                                output.echo], default=str, sort_keys=True).encode()).hexdigest()
            with self._lock:
                self.outputs += 1
                if digest in self._judged:
                    return
                self._judged.add(digest)
            found = (self._judge or rules.check)(output)
            test = _current_test()
            with self._lock:
                for f in found:
                    entry = self.findings.setdefault(f.key, {"rule": f.rule, "site": f.site, "count": 0,
                                                             "detail": f.detail[:300], "test": test})
                    entry["count"] += 1
        except Exception as exc:  # noqa: BLE001  (observing only: see the docstring)
            self.error(exc)

    def merge(self, other: dict[str, Any]) -> None:
        with self._lock:
            self.outputs += int(other.get("outputs") or 0)
            for key, entry in (other.get("findings") or {}).items():
                mine = self.findings.setdefault(key, {**entry, "count": 0})
                mine["count"] += int(entry.get("count") or 0)
            for name, n in (other.get("errors") or {}).items():
                self.errors[name] = self.errors.get(name, 0) + int(n)

    def as_dict(self) -> dict[str, Any]:
        """A snapshot, copied under the lock."""
        with self._lock:
            return {"outputs": self.outputs, "findings": {k: dict(v) for k, v in self.findings.items()},
                    "errors": dict(self.errors)}


# ---------------------------------------------------------------------------------------------- what is captured

def _aew_argv(args: Any) -> list[str] | None:
    """The ``aew`` arguments of a subprocess command line, or ``None`` when it does not run ``aew``."""
    if not isinstance(args, list | tuple) or not args:
        return None
    argv = [str(a) for a in args]
    if len(argv) >= 3 and argv[1:3] == ["-m", "aew"]:
        return argv[3:]
    if Path(argv[0]).name.lower() in ("aew", "aew.exe"):
        return argv[1:]
    return None


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value if isinstance(value, str) else ""


def cli_outputs(argv: list[str], stdout: str, stderr: str, stdin: str = "") -> list[rules.Output]:
    """The outputs of one ``aew`` command: its answer on stdout, and its refusal (the CLI's JSON shape) on stderr."""
    words = " ".join(("aew", *rules.command_words(argv)))
    echo = (*argv, stdin) if stdin else tuple(argv)
    out: list[rules.Output] = []
    refusal = rules.refusal_of(stderr)
    if refusal is not None:
        out.append(rules.Output(site=f"cli:{words}|{refusal.get('code')}", refusal=refusal, echo=echo))
    if stdout.strip():
        try:
            payload = json.loads(stdout)
            text = ""
        except ValueError:
            payload, text = None, stdout
        out.append(rules.Output(site=f"cli:{words}|result", payload=payload, text=text, echo=echo))
    return out


def tool_output(name: Any, arguments: Any, result: Any) -> rules.Output:
    stopped = result.get("stopped") if isinstance(result, dict) else None
    refusal = stopped.get("error") if isinstance(stopped, dict) else None
    code = (refusal or {}).get("code") or "result"
    return rules.Output(site=f"tool:{name}|{code}", plane=rules.MODEL, payload=result, refusal=refusal,
                        echo=(json.dumps(arguments, default=str),))


class _Tee(io.TextIOBase):
    """A stream that keeps what is written and passes it on."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.kept = inner, io.StringIO()

    def write(self, s: str) -> int:
        self.kept.write(s)
        return self.inner.write(s)

    def flush(self) -> None:
        self.inner.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


class CapturePlugin:
    """One process's capture. The output builders are the instance's own (``cli_outputs``, ``tool_output``), so a test
    can inject a defect into a plugin it installs without touching the session's."""

    def __init__(self, config: pytest.Config, path: Path | None, recorder: Recorder | None = None) -> None:
        self.config = config
        self.path = path
        self.recorder = recorder or Recorder()
        self.started = time.perf_counter()
        self.cli_outputs = cli_outputs
        self.tool_output = tool_output
        self._undo: list[tuple[Any, str, Any]] = []

    # ------------------------------------------------------------------ hooks into the product and subprocess

    def _patch(self, owner: Any, name: str, wrapper: Any) -> None:
        self._undo.append((owner, name, getattr(owner, name)))
        setattr(owner, name, wrapper)

    def install(self) -> None:
        import aew.cli.main as cli_main
        import aew.surface.run as surface_run

        recorder = self.recorder
        real_run, real_main, real_tool = subprocess.run, cli_main._main, surface_run.run_tool

        def observe(make: Any) -> None:
            """Record what ``make()`` builds; a defect in building it is counted, never raised into the test."""
            try:
                built = make()
                for output in built if isinstance(built, list) else [built]:
                    recorder.record(output)
            except Exception as exc:  # noqa: BLE001  (observing only: see the module docstring)
                recorder.error(exc)

        @functools.wraps(real_run)
        def run(*args: Any, **kwargs: Any) -> Any:
            result = real_run(*args, **kwargs)

            def outputs() -> list[rules.Output]:
                argv = _aew_argv(args[0] if args else kwargs.get("args"))
                if argv is None:
                    return []
                return self.cli_outputs(argv, _text(result.stdout), _text(result.stderr), _text(kwargs.get("input")))

            observe(outputs)
            return result

        @functools.wraps(real_main)
        def main(argv: list[str]) -> int:
            out, err = _Tee(sys.stdout), _Tee(sys.stderr)
            saved = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = out, err  # type: ignore[assignment]
            try:
                return real_main(argv)
            finally:
                sys.stdout, sys.stderr = saved
                observe(lambda: self.cli_outputs(list(argv), out.kept.getvalue(), err.kept.getvalue()))

        @functools.wraps(real_tool)
        def run_tool(engine: Any, ctx: Any, name: Any, arguments: Any, **kwargs: Any) -> Any:
            result = real_tool(engine, ctx, name, arguments, **kwargs)
            observe(lambda: self.tool_output(name, arguments, result))
            return result

        self._patch(subprocess, "run", run)
        self._patch(cli_main, "_main", main)
        self._patch(surface_run, "run_tool", run_tool)

    def uninstall(self) -> None:
        while self._undo:
            owner, name, value = self._undo.pop()
            setattr(owner, name, value)

    # ------------------------------------------------------------------ the session

    def pytest_sessionstart(self, session: pytest.Session) -> None:
        self.install()

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node: Any, error: Any) -> None:
        try:
            theirs = getattr(node, "workeroutput", {}).get(WORKER_KEY)
            if theirs:
                self.recorder.merge(theirs)
        except Exception as exc:  # noqa: BLE001  (observing only)
            self.recorder.error(exc)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Hand the findings on, or write them. A failure here is reported on stderr and never changes the session's
        exit status: the tests' outcome is theirs alone (a missing findings file is then the ratchet's to notice)."""
        try:
            self.uninstall()
            if hasattr(self.config, "workerinput"):
                self.config.workeroutput[WORKER_KEY] = self.recorder.as_dict()  # type: ignore[attr-defined]
                return
            if self.path is None:
                return
            data = {"schema": SCHEMA, "platform": sys.platform, "lane": self.config.getoption("aew_lane", None),
                    "shard": self.config.getoption("aew_shard", None),
                    "wall_s": round(time.perf_counter() - self.started, 2), **self.recorder.as_dict()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001  (observing only: see the docstring)
            sys.stderr.write(f"D2 capture: findings not written ({type(exc).__name__}: {exc})\n")


def addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("aew-discovery", "D2 output rules (docs/implementation/vertical-uat.md §8)")
    group.addoption("--discovery-out", dest="aew_discovery_out", default=None, metavar="PATH",
                    help="capture every aew output the tests produce and write D2's findings here as JSON "
                         "(also on, beside it, with --lane-report)")


def configure(config: pytest.Config) -> None:
    path = out_path(config)  # an xdist worker sees the same options, and hands its findings to the controller
    if path is not None:
        config.pluginmanager.register(CapturePlugin(config, path), "aew-discovery")
