"""Control-plane profiling (M3 plan §2.10): ``AEW_PROFILE=<file>`` records where each ``aew`` command spends its
time, as one JSON line per command appended to ``<file>``.

Phases are exclusive (a nested phase's time is not counted in its parent):

* ``lock``: waiting for the control lock;
* ``recover``: recovery on every read (temp files, redo records), excluding what is listed below;
* ``parse``: reading, checksumming, parsing and validating ``control.yaml``;
* ``render``: rebuilding the derived views (``state/CURRENT.md``);
* ``commit``: staging, serializing and atomically publishing a transition;
* ``git``: git subprocesses;
* ``scan``: reading and verifying a work unit's sealed evidence;
* ``compute``: everything else (the command's own logic, argument parsing, output).

Counts accompany them: ``git`` (subprocesses, and ``git:<subcommand>``), ``parse`` (with ``parse_bytes``),
``render``, ``commit`` and ``scan`` (with ``scan_files``). Counts are deterministic, so the scale regression can
assert them where timings could not (``tests/regression/test_m3_control_plane_scale.py``).

The record names the command by its leading words only (``work assign``), never an option or its value, so no
credential can reach the file. Profiling is off unless ``AEW_PROFILE`` is set, and then costs a clock read per phase.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

ENV = "AEW_PROFILE"
SCHEMA = "aew/profile/v1"
PHASES = ("lock", "recover", "parse", "render", "commit", "git", "scan")
_WORD = re.compile(r"^[a-z][a-z-]*$")


class Profile:
    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.phases: dict[str, float] = dict.fromkeys(PHASES, 0.0)
        self.counts: Counter[str] = Counter()
        self._stack: list[list[Any]] = []  # [name, started, time spent in nested phases]

    def enter(self, name: str) -> None:
        self._stack.append([name, time.perf_counter(), 0.0])

    def exit(self) -> None:
        name, started, nested = self._stack.pop()
        elapsed = time.perf_counter() - started
        self.phases[name] = self.phases.get(name, 0.0) + elapsed - nested
        if self._stack:
            self._stack[-1][2] += elapsed

    def summary(self) -> dict[str, Any]:
        total = time.perf_counter() - self.t0
        phases = {k: round(v, 6) for k, v in self.phases.items()}
        phases["compute"] = round(max(total - sum(self.phases.values()), 0.0), 6)
        return {"total_s": round(total, 6), "phases_s": phases, "counts": dict(sorted(self.counts.items()))}


_active: Profile | None = None


def active() -> Profile | None:
    return _active


def start() -> Profile:
    """Start profiling this process (the CLI does, when ``AEW_PROFILE`` is set; tools may call it directly)."""
    global _active
    _active = Profile()
    return _active


def stop() -> dict[str, Any] | None:
    global _active
    prof, _active = _active, None
    return prof.summary() if prof else None


@contextmanager
def phase(name: str) -> Iterator[None]:
    prof = _active
    if prof is None:
        yield
        return
    prof.enter(name)
    try:
        yield
    finally:
        prof.exit()


def count(name: str, n: int = 1) -> None:
    if _active is not None:
        _active.counts[name] += n


def command_words(argv: list[str]) -> str:
    """The command's leading words (``work assign``): no option and no value, so never a credential."""
    words, skip = [], False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == "-C":
            skip = True
            continue
        if not _WORD.match(arg) or len(words) == 2:
            break
        words.append(arg)
    return " ".join(words)


def cli_start() -> bool:
    if not os.environ.get(ENV):
        return False
    start()
    return True


def cli_finish(argv: list[str], exit_code: int) -> None:
    """Append this command's record to ``AEW_PROFILE`` (one line, one write: concurrent commands may append)."""
    path = os.environ.get(ENV)
    summary = stop()
    if not path or summary is None:
        return
    record = {"schema": SCHEMA, "command": command_words(argv), "exit": exit_code, "pid": os.getpid(), **summary}
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        pass  # profiling never changes a command's outcome
