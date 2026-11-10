"""A run's progress digest, ``aew/run-progress/v1``: what the worker is doing, and the triggers that wake the Lead.

The steering design's digest (§2). The Lead spends most of its time waiting on workers, and a wake shows it this
digest. Like the live usage sample beside it, the digest is non-authoritative local telemetry. No gate reads it, and
nothing in it grants anything.

**One writer, one poll.** The run's meter (:mod:`aew.harness.usage_live`) reads the worker's OpenCode server once a
second. It hands every assistant message it passes to :func:`observe`, and calls :func:`advance` before each sample.
The digest's state lives inside the meter's own state, so a read the meter drops leaves no trace here either, and a
restarted meter carries the digest forward.

**What the harness carries** (the steering PR 1 probe of OpenCode 2.0.18; the tool parts are pinned in
``tests/fixtures/opencode/openapi-2.0.18.min.json``):

- ``write`` and ``edit`` tool parts name their file in ``state.input.path``, and ``edit`` also in
  ``state.metadata.files[].file``. 2.0.18 offers no patch tool to a run.
- A ``shell`` tool part holds its command in ``state.input.command`` and its exit code in ``state.metadata.exit``. A
  failing command is a ``completed`` part with a non-zero exit, not an ``error`` part. A backgrounded or running shell
  is a ``running`` part with no exit, so its exit code reads ``None`` (not known) and it is never a failing test.
- ``state.input.path`` is the path as the model sent it, relative or absolute (the Linux check); ``edit``'s
  ``metadata.files[].file`` is workspace-relative. Every path is made workspace-relative, so the two are one file.
- Every tool part has ``time.completed`` (epoch ms) once it ends. A ``write`` or ``edit`` counts once it is
  ``completed``: a refused one (``error``) touched nothing.
- An assistant message's words are its ``text`` parts. The last words the worker said are ``last_message``, cut to
  :data:`MAX_MESSAGE` characters, its control and bidi-override characters removed, and labelled as data, not
  instructions (steering design r4 §6): a worker that stops with a question wakes the Lead as ``worker_idle``, and the
  question is there.

**What is changed now.** ``files_touched`` is the run's history: every path a ``write`` or ``edit`` part named. The
workspace says what is changed now: ``changed_now`` is its diff against the commit it was made from, read with the
tracker's ``changed`` callable (``aew.snapshot.fingerprint.changed_paths``, which stores no object). It is read in the
meter's read phase, never under its lock, and only when a new tool part has been seen since the last read: at most
every :data:`CHANGED_EVERY_S` while the worker is busy, at once when its turn has ended. So a shell write (``sed -i``,
a redirect, a script) is seen too, and a reverted file leaves it. ``out_of_scope`` is current: the changed-now paths
outside the scope, with any outside path a tool part named since that read. Its trigger still fires once per path.
Without a base or a readable workspace, ``changed_now`` is ``unknown`` and ``out_of_scope`` falls back to the tool
parts' history. The digest's ``counts`` are absolute (steps, files, commands, tests, triggers), so a reader in
another process (the Lead broker) can keep its own mark.

**What is outside the scope** is the Ticket's scope gate's reading (``policy.guardrails.outside_ticket_scope``): a
workspace-relative path the scope paths do not match, and nothing at all when the scope is empty (unbounded, as
``engine.conflicts`` reads it too). A path outside the workspace, such as the run's scratch directory, which the worker
is told to use for its reports, is not a scope question: it is in ``files_touched`` only.

A field the harness does not carry reads ``unknown``. The digest never guesses: a failing test's names are read only
from pytest's ``FAILED <node id>`` and ``ERROR <node id>`` lines, and are ``unknown`` for any other runner. Without the
Ticket's scope paths (a record that could not be read), ``out_of_scope`` is ``unknown``, never "inside".

**Triggers** (the closed ``why`` enum, :data:`WHY`). This poll detects four of them:

- ``run_ended``: the meter's final sample.
- ``test_failed``: a regression, or a stuck failure, each once. Every test run the poll passed is judged, in order,
  not only the newest.

  - A **regression** is a red run that fails a test that passed earlier in this run: a failing name seen passing, or
    a red run of a command whose last run passed and which now passes fewer tests than that green run did (pytest's
    summary counts). Where either run has no count, the same command's last run passing is taken as the evidence. A
    red run that passes as many tests as the green one adds a failing test, which is building (red before green), not
    a regression. A red run takes its command out of the green set, so the next red run of it is no new regression.
    A run that stopped at its first failures (``-x``, ``--exitfirst``, ``--maxfail``, or pytest's "stopping after"
    line) is judged by names only: its pass count is no evidence.
  - A **stuck failure** is the same command failing with the same failing set on :data:`STUCK_RUNS` test runs in a
    row with nothing newly passing (where the runner names no tests, the same command failing three times running).
    It wakes once per streak, and not at all when the streak began with a regression wake.
  - **Its limit:** a regression is seen only by the same command or by a failing name seen passing. A test that
    passed under ``pytest tests/x.py``, whose output names no passing tests, and then fails under plain ``pytest`` is
    a different command with no named evidence, so it shows in ``last_test`` and wakes only once it is stuck.

  A first red run while building wakes no one; it shows in ``last_test``. ``red_commands`` lists the test commands
  whose latest run failed: a ``test_failed`` trigger holds only while its own command is among them (:func:`holds`).
- ``out_of_scope``: a written or edited path outside the Ticket's scope paths.
- ``worker_idle``: the worker's turn ended without the run ending, and it is still idle after :data:`IDLE_DEBOUNCE_S`.

``worker_message`` belongs to the messaging design's reply (it stays reserved while messaging is off). ``quiet`` is
the Lead broker's backstop.

**No stale wakes** (:func:`holds`, :func:`pending`, :func:`wake`): the one rule the Lead's wait applies before it
returns a trigger, and steering PR 2's broker before it posts a wake, with the wake's one shape.

**No spinning:** at most one trigger per ``why`` per :data:`ANTI_SPIN_S`. One that repeats inside that window is
counted in ``suppressed`` and shown in the next digest, and wakes no one. A new trigger bumps the project's wake file,
so a waiting ``harness_wait`` sees it; the per-second rewrite bumps nothing.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import shlex
from collections.abc import Callable, Iterable, Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from aew.harness import contract as K
from aew.harness.runlog import PROGRESS_SCHEMA as SCHEMA
from aew.policy.guardrails import outside_ticket_scope
from aew.util import to_posix

STATE_VERSION = 2

# The closed `why` enum is the wake guide's (steering design §1, §4: `aew.harness.contract.WAKE_GUIDE`); the poll
# detects the ones a wait returns today.
RUN_ENDED, TEST_FAILED, OUT_OF_SCOPE = K.RUN_ENDED, K.TEST_FAILED, K.OUT_OF_SCOPE
WORKER_MESSAGE, WORKER_IDLE, QUIET = K.WORKER_MESSAGE, K.WORKER_IDLE, K.QUIET
WHY: tuple[str, ...] = K.WHY
DETECTED_IN_POLL: tuple[str, ...] = K.WAITED_ON

UNKNOWN = "unknown"
SCOPE_PATHS, WORKSPACE_BASE = K.SCOPE_PATHS, K.WORKSPACE_BASE  # the launch contract's keys (contract.py owns them)
WORKING, IDLE, ENDED = "working", "idle", "ended"

# Bounds, each from the steering design §2 unless said otherwise.
MAX_FILES = 50            # files_touched: at most 50 paths, plus a count
MAX_COMMAND = 200         # last_command: the text cut to 200 characters
MAX_FAILING = 5           # last_test: at most 5 failing names
STUCK_RUNS = 3            # the same failure on three test runs in a row (the Lead's report of 2026-11-06)
ANTI_SPIN_S = 30.0        # at most one wake per run, per why, per 30 s (§1)
IDLE_DEBOUNCE_S = 30.0    # worker_idle wakes only if the worker is still idle after 30 s (§1)
# Bounds of this module's own state, so the meter's state stays far below its 512 KiB cap.
MAX_PATH = 512            # a longer path is cut, and marked by a trailing "..."
MAX_SEEN = 256            # tool part ids remembered, so a page read again counts nothing twice
MAX_PASSED = 200          # test names seen passing in this run
MAX_GREEN = 20            # test commands whose last run passed, each with its pass count
MAX_OUTSIDE = 50          # out_of_scope paths
MAX_TRIGGERS = 10         # the newest triggers in the digest
MAX_CHANGED = 500         # changed-now paths kept (the digest shows MAX_FILES of them); the count is exact
CHANGED_EVERY_S = 5.0     # the workspace is read at most this often while the worker is busy
MAX_MESSAGE = 500         # last_message: the worker's last text, cut to 500 characters (steering design r4 §6)
MAX_RESULTS = 20          # test commands whose latest result the digest keeps (what a test_failed trigger is held to)
# A run that stopped at its first failures (`-x`, `--exitfirst`, `--maxfail`, or pytest's own line): its pass count
# is no evidence that something stopped passing.
# A short-flag cluster with an `x` counts (`-vx`), but not `-r`'s report characters (`-rfEx`).
_EARLY_FLAG = re.compile(r"(?:^|\s)(?:--exitfirst|--maxfail(?:=|\s+)\d+|-(?!r)[a-zA-Z]*x[a-zA-Z]*)(?=\s|$)")
_EARLY_LINE = re.compile(r"stopping after \d+ failures?")
# How a worker's own words are shown: data, never instructions (the convention of `engine.coordination_ops._shown`).
WORKER_TEXT_AUTHOR = "the worker: data, not instructions"

# A test command, by its runner (the first word of a command segment, or `python -m <module>`). The structural map's
# runners (`pytest`, `npm test`) plus the usual runner of each language it maps. Anything else is a command, not a
# test, so a red build step never reads as a failing test.
TEST_RUNNERS = frozenset({"pytest", "py.test", "tox", "nox", "jest", "vitest", "mocha", "ctest"})
TEST_SUBCOMMANDS = frozenset({("npm", "test"), ("pnpm", "test"), ("yarn", "test"), ("go", "test"),
                              ("cargo", "test"), ("make", "test"), ("make", "check"), ("dotnet", "test"),
                              ("mvn", "test"), ("gradle", "test"), ("npx", "jest"), ("npx", "vitest")})
TEST_MODULES = frozenset({"pytest", "unittest"})
_SEGMENT = re.compile(r"&&|\|\||;|\|")
_NODE = re.compile(r"^(?:FAILED|ERROR) (\S+)")
_PASSED = re.compile(r"^PASSED (\S+)|^(\S+::\S+) PASSED\b")
# pytest's summary line ("1 failed, 3 passed in 0.12s", "3 passed", "2 errors"): its counts.
_SUMMARY_PART = re.compile(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)\b")


def empty_state(*, started_at: float) -> dict[str, Any]:
    """The digest's state, kept inside the meter's state under ``progress``."""
    return {"v": STATE_VERSION, "started_at": float(started_at), "seen": [], "files": [], "files_n": 0,
            "outside": [], "commands_n": 0, "last_command": None, "tests_n": 0, "last_test": None,
            "recent_tests": [], "passed": [], "green": [], "streak": None, "idle_since": None, "idle_fired": False,
            "ended": False, "fired": {}, "suppressed": {}, "triggers": [], "trigger_seq": 0,
            "parts_n": 0, "changed": None, "changed_n": 0, "changed_parts_n": 0, "changed_at": None,
            "outside_since": [], "results": [], "last_message": None,
            "mark": {"steps": 0, "files_n": 0, "commands_n": 0, "tests_n": 0, "trigger_seq": 0}}


def valid_state(state: Any) -> bool:
    """The whole shape, as the meter checks its own: a file it did not write as it writes it is not trusted."""
    if not isinstance(state, dict) or set(state) != set(empty_state(started_at=0.0)) or state["v"] != STATE_VERSION:
        return False
    lists = ("seen", "files", "outside", "recent_tests", "passed", "green", "triggers")
    counts = ("files_n", "commands_n", "tests_n", "trigger_seq")
    return (all(isinstance(state[k], list) for k in lists)
            and len(state["seen"]) <= MAX_SEEN and len(state["files"]) <= MAX_FILES
            and len(state["outside"]) <= MAX_OUTSIDE and len(state["recent_tests"]) <= STUCK_RUNS
            and len(state["passed"]) <= MAX_PASSED and len(state["green"]) <= MAX_GREEN
            and len(state["triggers"]) <= MAX_TRIGGERS
            and all(isinstance(state[k], int) and not isinstance(state[k], bool) and state[k] >= 0 for k in counts)
            and isinstance(state["started_at"], (int, float)) and isinstance(state["fired"], dict)
            and isinstance(state["suppressed"], dict) and isinstance(state["mark"], dict)
            and isinstance(state["idle_fired"], bool) and isinstance(state["ended"], bool)
            and all(isinstance(x, str) and len(x) <= MAX_PATH + 3
                    for k in ("seen", "files", "outside", "passed") for x in state[k])
            and all(isinstance(g, list) and len(g) == 2 and isinstance(g[0], str) and len(g[0]) <= MAX_PATH + 3
                    and (g[1] is None or (isinstance(g[1], int) and not isinstance(g[1], bool)))
                    for g in state["green"])
            and all(isinstance(t, dict) and isinstance(t.get("failing"), (list, type(None)))
                    and len(t.get("failing") or []) <= MAX_FAILING for t in state["recent_tests"])
            and (state["streak"] is None or isinstance(state["streak"], dict))
            and isinstance(state["parts_n"], int) and isinstance(state["changed_n"], int)
            and isinstance(state["changed_parts_n"], int) and isinstance(state["outside_since"], list)
            and len(state["outside_since"]) <= MAX_OUTSIDE
            and isinstance(state["results"], list) and len(state["results"]) <= MAX_RESULTS
            and all(isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and len(r[0]) <= MAX_PATH + 3
                    and r[1] in (True, False, None) for r in state["results"])
            and (state["last_message"] is None
                 or (isinstance(state["last_message"], str) and len(state["last_message"]) <= MAX_MESSAGE + 3))
            and (state["changed"] is None or (isinstance(state["changed"], list)
                                              and len(state["changed"]) <= MAX_CHANGED
                                              and all(isinstance(x, str) and len(x) <= MAX_PATH + 3
                                                      for x in state["changed"]))))


class Tracker:
    """One run's digest settings: its workspace, the Ticket's scope paths (None: not known to this run, so
    ``out_of_scope`` reads ``unknown``) and the wall clock. Its methods change only the state they are given."""

    def __init__(self, *, run: str, workspace: str | None, scope_paths: Iterable[str] | None,
                 clock: Callable[[], float], changed: Callable[[], list[str] | None] | None = None) -> None:
        self.run = run
        self.workspace = workspace
        # The workspace as given and as resolved: a path the model sends may name either (a link in the path).
        self._roots = [] if not workspace else list(dict.fromkeys([workspace, os.path.realpath(workspace)]))
        self.scope_paths = None if scope_paths is None else [to_posix(p) for p in scope_paths]
        self.clock = clock
        self.changed = changed  # the workspace's changed paths now, or None when they cannot be read

    # ------------------------------------------------------------------ observing the worker's messages

    def observe(self, state: dict[str, Any], message: Mapping[str, Any]) -> None:
        """One assistant message the meter passed: its tool parts, each once (by part id), and its text, the worker's
        last words (``last_message``). A ``write`` or ``edit`` counts once it completed: a refused one (``error``)
        touched nothing, and a running one is counted when it completes."""
        content = message.get("content")
        if not isinstance(content, list):
            return
        texts = [p["text"] for p in content
                 if isinstance(p, Mapping) and p.get("type") == "text" and isinstance(p.get("text"), str)]
        said = "\n".join(t for t in texts if t.strip())
        if said:  # a message with tool calls only keeps the last words the worker said
            state["last_message"] = _cut(_clean(said), MAX_MESSAGE)
        for part in content:
            if not isinstance(part, Mapping) or part.get("type") != "tool":
                continue
            pid = part.get("id")
            if not isinstance(pid, str) or not pid or len(pid) > MAX_PATH:
                continue
            st = part.get("state")
            if not isinstance(st, Mapping) or st.get("status") not in ("completed", "error", "running"):
                continue  # a streaming part's input may be incomplete
            if pid in state["seen"]:
                continue
            name = part.get("name")
            if name in ("write", "edit") and st.get("status") == "running":
                continue  # not seen yet: counted when it completes
            state["seen"] = (state["seen"] + [pid])[-MAX_SEEN:]
            state["parts_n"] += 1
            if name in ("write", "edit"):
                if st.get("status") == "completed":
                    self._touched(state, st)
            elif name == "shell":
                self._command(state, part, st)

    def _touched(self, state: dict[str, Any], st: Mapping[str, Any]) -> None:
        paths: list[str] = []
        inp = st.get("input")
        if isinstance(inp, Mapping) and isinstance(inp.get("path"), str):
            paths.append(inp["path"])
        meta = st.get("metadata")
        files = meta.get("files") if isinstance(meta, Mapping) else None
        if isinstance(files, list):
            paths += [f["file"] for f in files if isinstance(f, Mapping) and isinstance(f.get("file"), str)]
        for raw in dict.fromkeys(paths):
            rel = self.relative(raw)
            if rel in state["files"]:
                continue
            state["files_n"] += 1
            if len(state["files"]) < MAX_FILES:
                state["files"].append(rel)
            self._outside(state, rel)

    def _outside(self, state: dict[str, Any], rel: str) -> None:
        """A path outside the scope: in the history of outside paths, and among those named since the last read of the
        workspace (so it counts as current until that read says otherwise). A path outside the workspace (the run's
        scratch directory, which the worker is told to use) is not a scope question: it is in ``files_touched`` only."""
        if self.scope_paths is None or not self._outside_scope(rel):
            return
        if rel not in state["outside"] and len(state["outside"]) < MAX_OUTSIDE:
            state["outside"].append(rel)
        if rel not in state["outside_since"] and len(state["outside_since"]) < MAX_OUTSIDE:
            state["outside_since"].append(rel)

    def refresh_changed(self, state: dict[str, Any], *, busy: bool) -> None:
        """Read what is changed now, when a tool part was seen since the last read: at most every
        :data:`CHANGED_EVERY_S` while ``busy``, at once otherwise. Called in the meter's read phase, outside its lock.
        A read that fails leaves ``changed`` as ``None`` (``unknown``)."""
        if self.changed is None or state["parts_n"] == state["changed_parts_n"]:
            return
        now = self.clock()
        if busy and state["changed_at"] is not None and now - float(state["changed_at"]) < CHANGED_EVERY_S:
            return
        try:
            found = self.changed()
        except Exception:  # noqa: BLE001 - a workspace that cannot be read is not known, never empty
            found = None
        state["changed_parts_n"], state["changed_at"] = state["parts_n"], now
        if found is None:
            state["changed"], state["changed_n"] = None, 0
            return
        paths = sorted({self.relative(p) for p in found})
        state["changed"], state["changed_n"] = paths[:MAX_CHANGED], len(paths)
        state["outside_since"] = []
        for rel in paths:
            self._outside(state, rel)
        state["outside_since"] = []  # the read is now current: it names every outside path itself

    def outside_now(self, state: dict[str, Any]) -> list[str] | None:
        """The paths outside the scope now: the last read's, with any named by a tool part since. None without a
        scope. Without a readable workspace, the tool parts' history (a reverted file stays in it)."""
        if self.scope_paths is None:
            return None
        if state["changed"] is None:
            return list(state["outside"])
        now = [p for p in state["changed"] if self._outside_scope(p)]
        return now + [p for p in state["outside_since"] if p not in now]

    def relative(self, raw: str) -> str:
        """A workspace-relative POSIX path. A path outside the workspace keeps its own spelling (it is outside the
        scope too); a path past :data:`MAX_PATH` is cut and marked."""
        text = raw
        if _is_absolute(raw):
            for root in self._roots:
                try:
                    rel = os.path.relpath(raw, root)
                except ValueError:  # another drive on Windows
                    continue
                if not rel.startswith(".."):
                    text = rel
                    break
        text = to_posix(text)
        if text:  # one spelling per file: `src/b/./x.py` is `src/b/x.py`, and `src/a/../b/x.py` is `src/b/x.py`
            text = posixpath.normpath(text)
        return text if len(text) <= MAX_PATH else text[:MAX_PATH] + "..."

    def _outside_scope(self, rel: str) -> bool:
        """Outside the Ticket's scope, as its gate reads it (``policy.guardrails.outside_ticket_scope``: an empty scope
        is unbounded). Only a workspace-relative path is a scope question; one outside the workspace, or cut, is not."""
        if _is_absolute(rel) or rel == ".." or rel.startswith("../") or rel.endswith("..."):
            return False
        return outside_ticket_scope(rel, self.scope_paths)

    def _command(self, state: dict[str, Any], part: Mapping[str, Any], st: Mapping[str, Any]) -> None:
        inp = st.get("input")
        command = inp.get("command") if isinstance(inp, Mapping) else None
        if not isinstance(command, str):
            return
        meta = st.get("metadata")
        exit_code = meta.get("exit") if isinstance(meta, Mapping) else None
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            exit_code = None
        at = _completed_s(part)
        state["commands_n"] += 1
        state["last_command"] = {"text": _cut(command, MAX_COMMAND), "exit": exit_code, "at": at}
        if not is_test_command(command):
            return
        output = _output(st)
        failing, passing = _names(output)
        passed_n = _passed_count(output)
        ok = None if exit_code is None else exit_code == 0
        state["tests_n"] += 1
        key = _cut(" ".join(command.split()), MAX_PATH)
        green = {g[0]: g[1] for g in state["green"]}
        regression = False
        early = bool(_EARLY_FLAG.search(command)) or bool(output and _EARLY_LINE.search(output))
        if ok is False:
            named = failing is not None and any(n in state["passed"] for n in failing)
            if early:
                # The run stopped at its first failures: fewer passing is no evidence. Only a name seen passing in
                # this run that fails now is a regression (#358 review, finding 4).
                regression = named
            elif key in green:
                was = green[key]
                # Fewer passing than the last green run of this command: something that passed fails now. As many
                # passing: a test was added and fails (red before green). No count on either side: the green run is
                # the evidence.
                fewer = True if (was is None or passed_n is None) else passed_n < was
                regression = named or fewer
            else:
                regression = named
            if regression or key not in green:  # its next red run is no new regression
                state["green"] = [g for g in state["green"] if g[0] != key]
            elif not early:  # building: the green run's count stays the mark a later red run is held to (a
                # high-water mark). An early stop says nothing about the count, so the mark stands as it is.
                was = green[key]
                mark = was if passed_n is None else passed_n if was is None else max(was, passed_n)
                state["green"] = [g if g[0] != key else [key, mark] for g in state["green"]]
        if ok is True:
            state["green"] = ([g for g in state["green"] if g[0] != key] + [[key, passed_n]])[-MAX_GREEN:]
        state["results"] = ([r for r in state["results"] if r[0] != key] + [[key, ok]])[-MAX_RESULTS:]
        newly_passing = [n for n in passing if n not in state["passed"]]
        if ok is True and state["recent_tests"]:  # a green run passes everything the last red run of it named
            for t in state["recent_tests"]:
                if t["command"] == key and t["failing"]:
                    newly_passing += [n for n in t["failing"] if n not in newly_passing]
        state["passed"] = (state["passed"] + [n for n in newly_passing if n not in state["passed"]])[-MAX_PASSED:]
        state["last_test"] = {"command": _cut(command, MAX_COMMAND),
                              "result": UNKNOWN if ok is None else ("pass" if ok else "fail"),
                              "failing": (UNKNOWN if failing is None else failing[:MAX_FAILING]) if ok is False else [],
                              "failing_n": (None if failing is None else len(failing)) if ok is False else 0,
                              "at": at}
        # The failing set, bounded: its first names, its count and a digest of the whole set (what "the same failing
        # set" compares), so three huge red runs never push the meter's state past its cap.
        ordered = None if failing is None else sorted(failing)
        digest = None if ordered is None else hashlib.sha256("\n".join(ordered).encode("utf-8")).hexdigest()
        stuck = False
        streak = state["streak"]
        if ok is False:
            if streak is not None and streak["command"] == key and streak["sha"] == digest and not newly_passing:
                streak = {**streak, "n": int(streak["n"]) + 1}
            else:
                streak = {"command": key, "sha": digest, "n": 1, "woke": False}
            if regression:
                streak["woke"] = True
            elif streak["n"] >= STUCK_RUNS and not streak["woke"]:
                stuck = streak["woke"] = True
        else:
            streak = None
        state["streak"] = streak
        record = {"command": key, "ok": ok, "failing": None if ordered is None else ordered[:MAX_FAILING],
                  "failing_n": None if ordered is None else len(ordered), "newly_passing": bool(newly_passing),
                  "regression": regression, "stuck": stuck, "woke": False}
        state["recent_tests"] = (state["recent_tests"] + [record])[-STUCK_RUNS:]

    # ------------------------------------------------------------------ triggers and the digest

    def advance(self, state: dict[str, Any], *, run_state: str, active: bool, prompt_posted: bool) -> list[str]:
        """Detect this poll's triggers, apply the anti-spin rule, and return the ``why`` of each new trigger.
        ``run_state`` is the meter's (``live``, ``final``, ``server_gone``); ``active``: the run's session is in
        ``session.active``; ``prompt_posted``: the launch contract has been posted."""
        now = self.clock()
        found: list[tuple[str, dict[str, Any]]] = []
        if run_state != "live":
            if not state["ended"]:
                state["ended"] = True
                found.append((RUN_ENDED, {}))
        else:
            for t in state["recent_tests"]:  # every run passed since the last poll, in order (parallel calls too)
                if t.get("woke"):
                    continue
                t["woke"] = True
                if t["ok"] is False and (t["regression"] or t.get("stuck")):
                    found.append((TEST_FAILED, {"kind": "regression" if t["regression"] else "stuck",
                                                "command": t["command"][:MAX_COMMAND]}))
            for path in state["outside"]:
                if path not in state["fired"].get("out_of_scope_paths", []):
                    state["fired"]["out_of_scope_paths"] = state["fired"].get("out_of_scope_paths", []) + [path]
                    found.append((OUT_OF_SCOPE, {"path": path}))
            if active or not prompt_posted:
                state["idle_since"], state["idle_fired"] = None, False
            else:
                if state["idle_since"] is None:
                    state["idle_since"] = now
                if not state["idle_fired"] and now - float(state["idle_since"]) >= IDLE_DEBOUNCE_S:
                    state["idle_fired"] = True
                    found.append((WORKER_IDLE, {"idle_s": round(now - float(state["idle_since"]), 1)}))
        fired: list[str] = []
        for why, detail in found:
            last_at = state["fired"].get(why)
            if why != RUN_ENDED and isinstance(last_at, (int, float)) and now - float(last_at) < ANTI_SPIN_S:
                state["suppressed"][why] = int(state["suppressed"].get(why, 0)) + 1
                continue
            state["fired"][why] = now
            state["trigger_seq"] += 1
            state["triggers"] = (state["triggers"] + [{"seq": state["trigger_seq"], "why": why, "at": round(now, 3),
                                                       **detail}])[-MAX_TRIGGERS:]
            if why not in fired:
                fired.append(why)
        return fired

    def mark_woken(self, state: dict[str, Any], *, steps: int) -> None:
        """What the Lead has been shown: ``since_last_wake`` counts from here. The poll marks it when it hands on a
        new trigger; the Lead broker will mark it when it posts a wake."""
        state["mark"] = {"steps": steps, "files_n": state["files_n"], "commands_n": state["commands_n"],
                         "tests_n": state["tests_n"], "trigger_seq": state["trigger_seq"]}
        state["suppressed"] = {}

    def digest(self, state: dict[str, Any], *, run_state: str, active: bool, steps: int, tokens: Any,
               observed_at: str) -> dict[str, Any]:
        """The ``aew/run-progress/v1`` document the meter writes to ``progress.json``."""
        now = self.clock()
        mark = state["mark"]
        new_files = state["files"][max(0, min(len(state["files"]), int(mark["files_n"]))):]
        return {
            "schema": SCHEMA, "run": self.run, "observed_at": observed_at,
            "state": ENDED if run_state != "live" else (WORKING if active else IDLE),
            "elapsed_s": round(max(0.0, now - float(state["started_at"])), 1),
            "steps": steps, "tokens": tokens,
            "files_touched": {"paths": list(state["files"]), "count": state["files_n"]},
            "changed_now": (UNKNOWN if state["changed"] is None
                            else {"paths": state["changed"][:MAX_FILES], "count": state["changed_n"]}),
            "out_of_scope": UNKNOWN if self.scope_paths is None else self.outside_now(state),
            "last_command": state["last_command"],
            "last_test": state["last_test"],
            # The test commands whose latest run failed: what a `test_failed` trigger is held to (`holds`).
            "red_commands": [r[0][:MAX_COMMAND] for r in state["results"] if r[1] is False],
            # The worker's last words, as data: a `worker_idle` question is here (steering design r4 §6).
            "last_message": (None if state["last_message"] is None
                             else {"untrusted_text": state["last_message"], "author": WORKER_TEXT_AUTHOR}),
            "since_last_wake": {"steps": max(0, steps - int(mark["steps"])),
                                "files": new_files, "files_n": state["files_n"] - int(mark["files_n"]),
                                "commands": state["commands_n"] - int(mark["commands_n"]),
                                "tests": state["tests_n"] - int(mark["tests_n"]),
                                "suppressed": dict(state["suppressed"]),
                                # the mark it counts from, in `counts`' keys: since = counts - from (steering PR 2
                                # moves the mark to the broker, which keeps its own)
                                "from": {"steps": int(mark["steps"]), "files": int(mark["files_n"]),
                                         "commands": int(mark["commands_n"]), "tests": int(mark["tests_n"]),
                                         "triggers": int(mark["trigger_seq"])}},
            # The messaging design's delivery facts (D-13) arrive with messaging (MS3 to MS5). Until then the Lead
            # sends a worker no message, so there is none to show.
            "messages_out": [],
            "triggers": list(state["triggers"]), "trigger_seq": state["trigger_seq"],
            "counts": {"steps": steps, "files": state["files_n"], "commands": state["commands_n"],
                       "tests": state["tests_n"], "triggers": state["trigger_seq"]},
        }


# ------------------------------------------------------------------ what a wake may say (the wait and the broker)

def holds(digest: Mapping[str, Any], trigger: Mapping[str, Any]) -> bool:
    """Whether a trigger's condition still holds in the run's digest now: no stale wakes (steering design §1). The one
    rule the Lead's wait applies before it returns a trigger, and steering PR 2's broker before it posts a wake.

    ``out_of_scope``: the path is still outside the scope. ``test_failed``: the trigger's own test command's latest run
    still fails (``red_commands``; a digest without it: ``last_test``, when it is that command). The same command, not
    the same failing set. ``worker_idle``: the worker is still idle. ``run_ended`` is the record lane's, and the other
    reasons are not detected in the poll."""
    why = trigger.get("why")
    if why == OUT_OF_SCOPE:
        outside = digest.get("out_of_scope")
        return isinstance(outside, list) and trigger.get("path") in outside
    if why == TEST_FAILED:
        command = _same(trigger.get("command"))
        red = digest.get("red_commands")
        if isinstance(red, list):
            return bool(command) and command in {_same(c) for c in red}
        last = digest.get("last_test") or {}
        return last.get("result") == "fail" and bool(command) and _same(last.get("command")) == command
    if why == WORKER_IDLE:
        return digest.get("state") == IDLE
    return False


def pending(digest: Mapping[str, Any] | None, returned: int) -> tuple[list[dict[str, Any]], int]:
    """A run's triggers newer than ``returned`` (the newest seq already returned) whose condition still holds, and the
    newest seq looked at (the mark a return moves to)."""
    if not digest:
        return [], returned
    fresh = [dict(t) for t in digest.get("triggers") or [] if isinstance(t, Mapping)
             and isinstance(t.get("seq"), int) and not isinstance(t.get("seq"), bool) and t["seq"] > returned]
    newest = max([t["seq"] for t in fresh], default=returned)
    return [t for t in fresh if holds(digest, t)], newest


def wake(why: list[str], runs: Mapping[str, Any]) -> dict[str, Any]:
    """The wake's shape (steering design §2): why, each named run's digest, the worker messages (none while messaging
    is off) and the wake guide's keys for what to do next. The Lead's wait returns it; steering PR 2's broker will
    post it."""
    whys = [w for w in WHY if w in why]
    return {"why": whys, "runs": dict(runs), "messages": [], "next": whys}


def _same(command: Any) -> str:
    """A test command as a trigger and ``red_commands`` hold it: redacted, whitespace folded, cut to
    :data:`MAX_COMMAND`."""
    return " ".join(K.redact(command).split())[:MAX_COMMAND] if isinstance(command, str) else ""


def is_test_command(command: str) -> bool:
    """Whether one of the command's segments runs a test runner (:data:`TEST_RUNNERS` and its neighbours)."""
    for segment in _SEGMENT.split(command):
        try:  # not POSIX mode: a Windows path keeps its backslashes
            words = [w.strip("'\"") for w in shlex.split(segment, posix=False)]
        except ValueError:
            words = segment.split()
        while words and ("=" in words[0] and not words[0].startswith("=")):
            words = words[1:]  # VAR=value prefixes
        if not words:
            continue
        head = _stem(words[0])
        if head in TEST_RUNNERS or tuple(_stem(w) for w in words[:2]) in TEST_SUBCOMMANDS:
            return True
        if head.startswith("python") and len(words) >= 3 and words[1] == "-m" and words[2] in TEST_MODULES:
            return True
        if head in ("uv", "poetry", "pipenv", "hatch") and "pytest" in words[1:4]:
            return True
    return False


def _stem(word: str) -> str:
    name = PureWindowsPath(word).name if "\\" in word else PurePosixPath(word).name
    return name[:-4].lower() if name.lower().endswith(".exe") else name.lower()


def _names(output: str | None) -> tuple[list[str] | None, list[str]]:
    """(failing node ids, or None when the output names none; passing node ids) from pytest's summary lines."""
    if output is None:
        return None, []
    failing: list[str] = []
    passing: list[str] = []
    for line in output.splitlines():
        line = line.strip()
        m = _NODE.match(line)
        if m and m.group(1) not in failing:
            failing.append(_cut(m.group(1), MAX_PATH))
            continue
        p = _PASSED.match(line)
        if p:
            passing.append(_cut(p.group(1) or p.group(2), MAX_PATH))
    return (failing or None), passing


def _passed_count(output: str | None) -> int | None:
    """The passed count of pytest's last summary line ("1 failed, 3 passed in 0.1s"): 0 when that line names no passed
    tests, None with no summary line (another runner, or output cut short)."""
    if output is None:
        return None
    for line in reversed(output.splitlines()):
        parts = _SUMMARY_PART.findall(line)
        if any(kind in ("passed", "failed") or kind.startswith("error") for _, kind in parts):
            return next((int(n) for n, kind in parts if kind == "passed"), 0)
    return None


def _output(st: Mapping[str, Any]) -> str | None:
    content = st.get("content")
    if not isinstance(content, list):
        return None
    texts = [str(c["text"]) for c in content if isinstance(c, Mapping) and isinstance(c.get("text"), str)]
    return "\n".join(texts) if texts else None


def _completed_s(part: Mapping[str, Any]) -> float | None:
    t = part.get("time")
    v = t.get("completed") if isinstance(t, Mapping) else None
    return round(float(v) / 1000.0, 3) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _clean(text: str) -> str:
    """A worker's text with control and bidi-override characters removed (a line break stays)."""
    from aew.harness.event_spool import clean

    return "\n".join(clean(line, len(line)) or "" for line in text.splitlines())


def _cut(text: str, limit: int) -> str:
    """``text`` redacted (``contract.redact``, the scrub's own), then cut to ``limit``: a cut never leaves part of a
    credential that the redaction would no longer recognise."""
    text = K.redact(text)
    return text if len(text) <= limit else text[:limit] + "..."


def _is_absolute(path: str) -> bool:
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute() or path.startswith("\\\\")
