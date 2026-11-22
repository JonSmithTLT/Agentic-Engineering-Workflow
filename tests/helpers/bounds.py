"""Every bound in the test helpers, declared in one place, and the rule that they nest (the hang-and-flake diagnosis
plan, G3 H5).

In #213 the chat bound (1800 s) equalled the vertical lane's ``--test-timeout 1800``, so no inner bound fired first
and nothing named the part that stalled. The rule, pinned for every lane in every workflow
(``tests/unit/test_ci_tools.py``):

    inner helper bound < enclosing scenario bound < --test-timeout < --session-deadline (+ its margins)
        < the job's timeout-minutes (less JOB_MARGIN_S)

so the innermost wait always fails first, and by name. A helper declares a bound with :func:`declare` (a name, its
seconds, the bound that encloses it, and the lanes it runs in) and waits with :func:`bounded_wait`, which records how
each wait ended in the flight recorder.

This module imports nothing from AEW: helper children may load it.
"""

from __future__ import annotations

import re
import shlex
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import flight_recorder

# The session deadline (session_deadline.py): xdist workers act at the deadline, the controller one margin later and
# the sentinel one more margin later, and that must be at least JOB_MARGIN_S before the job's timeout-minutes. The
# sentinel's longest path ends the set three margins after that, when the session finished only then and its exit or
# evidence hangs: SESSION_END_MARGINS in all, which must still be UPLOAD_CLEARANCE_S before the timeout, so the job's
# `if: always()` upload still runs. A job's AEW_JOB_DEADLINE is its timeout less JOB_MARGIN_S and two margins, 240 s,
# so that path leaves it 90 s. UPLOAD_CLEARANCE_S is a chosen clearance, not a measured need: its evidence is the first
# upload, which took about 2 s in the Windows jobs read on 2026-11-08.
DEADLINE_MARGIN_S = 30.0
JOB_MARGIN_S = 180.0
SESSION_END_MARGINS = 5
UPLOAD_CLEARANCE_S = 60.0


@dataclass(frozen=True)
class Bound:
    name: str
    seconds: float
    within: str | None = None  # the enclosing bound's name; None: directly inside the test's --test-timeout
    lanes: frozenset[str] = frozenset()  # the lanes whose tests use it; empty: every lane
    why: str = ""


BOUNDS: dict[str, Bound] = {}


def declare(name: str, seconds: float, *, within: str | None = None, lanes: Iterable[str] = (), why: str = "") -> float:
    """Declare a helper's bound and return its seconds (``CHAT_S = bounds.declare("vertical.chat", 600, ...)``)."""
    bound = Bound(name, float(seconds), within, frozenset(lanes), why)
    if name in BOUNDS and BOUNDS[name] != bound:
        raise ValueError(f"bound {name} declared twice with different values")
    BOUNDS[name] = bound
    return bound.seconds


# The per-test watchdog's limit (watchdog.py): ``--test-timeout``'s default, and what CI's lanes pass. A start-up or
# admission wait names WATCHDOG instead of a number: it is bounded by the time left to this limit, so it never adds a
# tighter deadline of its own (#497), and on Windows, where the watchdog only dumps stacks, it still fails by name.
TEST_TIMEOUT_S = 600.0
WATCHDOG = "watchdog"
# Past the test's limit, a WATCHDOG wait gives the watchdog's own evidence time to land first: on Windows the
# faulthandler dump at the limit, and the autopsy watcher one WATCHER_GRACE_S later (autopsy.py), which collects while
# the test still runs. On POSIX the watchdog's alarm raises in the test at the limit itself, before this.
WATCHDOG_EVIDENCE_S = 10.0


class BoundExpired(Exception):
    """A bounded wait ran out: its message names the bound."""


# The polled waits' bounds, by what they wait for. Their seconds are those the waits had before they were named (the
# lab's default 60, the notifier helper's 30, and the literals the calls passed): a bound is never raised to pass.
declare("wait.condition", 60, why="a run, a lab or a process reaches the state the test observes next")
declare("wait.chain", 30, why="a notifier or broker chain delivers, or reaches its next state")
declare("wait.exit", 30, why="a supervisor or a process tree exits, or is killed")
declare("wait.run_end", 120, why="a run ends, or its observed progress moves, after a slower step")
declare("wait.kill", 15, why="the notifier's process tree is killed at its timeout")
declare("wait.challenge", 15, why="a resumed seat's challenge is shown")
declare("wait.selector", 10, why="a worker wait reaches the engine's selector, or leaves it")
declare("wait.meter", 10, why="a live run's meter or turn reaches its next state")
declare("wait.beat", 5, why="the broker writes its next liveness beat")
declare("wait.never", 0.1, why="a wait that is meant to time out, to test the timeout itself")
declare("wait.custody", 90, why="a custody worker registers, or exits")
declare("wait.validation", 300, lanes=("integration",), why="a custodian's validation run routes its entry")


def seconds(bound: str | float) -> float | None:
    """A wait's bound in seconds: a declared bound's; for :data:`WATCHDOG`, the time left to the test's limit and
    :data:`WATCHDOG_EVIDENCE_S` (None when the watchdog is off: ``--test-timeout 0``); or ``bound`` itself, when it
    is seconds already."""
    import sys

    if bound == WATCHDOG:
        left_of = getattr(sys.modules.get("watchdog"), "left", None)  # tests/helpers/watchdog.py, not a namesake
        left = left_of() if callable(left_of) else None
        return None if left is None else left + WATCHDOG_EVIDENCE_S
    return BOUNDS[bound].seconds if isinstance(bound, str) else float(bound)


def until(ready: Callable[[], Any], bound: str | float, what: str, *, every: float = 0.05,
         before: Callable[[], None] | None = None, describe: Callable[[], str] | None = None) -> Any:
    """``ready()``'s first truthy result within ``bound``: a declared bound's name, :data:`WATCHDOG`, or seconds
    derived from a product value (never a literal: tests/unit/test_polling_predicates.py). ``before`` runs ahead of
    each check; on a timeout the AssertionError names the bound and, with ``describe``, what was happening then."""
    limit = seconds(bound)
    name = bound if isinstance(bound, str) else f"{limit:g}s"
    started = time.monotonic()
    while limit is None or time.monotonic() < started + limit:
        if before is not None:
            before()
        value = ready()
        if value:
            flight_recorder.wait(name, limit or 0.0, "ok", time.monotonic() - started)
            return value
        time.sleep(every)
    flight_recorder.wait(name, limit, "timeout", time.monotonic() - started)
    message = f"timed out after {limit:g}s ({name}) waiting for {what}"
    if describe is not None:
        try:
            message += f"; at the timeout:\n{describe()}"
        except Exception as exc:  # the timeout is the failure: a broken describer must not hide it  # noqa: BLE001
            message += f"; the describer failed: {type(exc).__name__}: {exc}"
    raise AssertionError(message)


def bounded_wait(name: str, ready: Callable[[], Any], *, seconds: float | None = None, poll_s: float = 0.05,
                 gone: Callable[[], bool] | None = None) -> Any:
    """Wait until ``ready()`` returns something truthy (returned), ``gone()`` holds (``None``), or the declared bound
    ``name`` (or ``seconds``) runs out (:class:`BoundExpired`, naming it). Each end is recorded."""
    limit = BOUNDS[name].seconds if seconds is None else seconds
    started = time.monotonic()
    deadline = started + limit
    while True:
        value = ready()
        if value:
            flight_recorder.wait(name, limit, "ok", time.monotonic() - started)
            return value
        if gone is not None and gone():
            flight_recorder.wait(name, limit, "gone", time.monotonic() - started)
            return None
        if time.monotonic() > deadline:
            flight_recorder.wait(name, limit, "timeout", time.monotonic() - started)
            raise BoundExpired(f"bound {name} ({limit:g}s) ran out")
        time.sleep(poll_s)  # bounded: the loop ends at the deadline above


# ---------------------------------------------------------------------------------------------- the workflows' lanes

@dataclass
class Lane:
    """One pytest invocation in a workflow job, with the bounds it runs under."""

    workflow: str
    job: str
    step: str
    command: str
    job_timeout_s: float | None
    test_timeout_s: float | None
    deadline_s: float | None
    margin_s: float
    lane: str | None
    xdist: bool
    max_worker_restart: str | None
    hang_dir: str | None
    lane_report: str | None
    repeats: int = 1
    uploads: list[dict[str, Any]] = field(default_factory=list)
    job_deadline_s: float | None = None  # the job's AEW_JOB_DEADLINE, as seconds after its first step

    @property
    def label(self) -> str:
        return f"{self.workflow} {self.job} / {self.step}"


def _commands(run: str) -> list[tuple[str, int]]:
    """The pytest command lines in a step's ``run`` (folded ``>-`` text or a shell script), each with how many times
    a ``for ... in $(seq 1 N)`` loop around it repeats it."""
    out = []
    repeat = 1
    for raw in run.replace("\\\n", " ").splitlines() if "\n" in run.strip() else [run]:
        line = raw.strip()
        loop = re.match(r"for \w+ in \$\(seq 1 (\d+)\)", line)
        if loop:
            repeat = int(loop.group(1))
        elif line == "done":
            repeat = 1
        if "-m pytest" in line or line.startswith("pytest "):
            out.append((line, repeat))
    return out


def _option(argv: list[str], name: str) -> str | None:
    for i, a in enumerate(argv):
        if a == name and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(name + "="):
            return a.split("=", 1)[1]
    return None


def _seconds(argv: list[str], name: str) -> float | None:
    value = _option(argv, name)
    return float(value) if value is not None else None


def workflow_lanes(workflows: Path) -> list[Lane]:
    """Every pytest invocation in every workflow under ``workflows``."""
    import yaml

    lanes = []
    for path in sorted(workflows.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            uploads = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")]
            set_at = next((m for m in (JOB_DEADLINE_RE.search(str(s.get("run") or "")) for s in steps) if m), None)
            for step in steps:
                for command, repeats in _commands(str(step.get("run") or "")):
                    text = re.sub(r"\$\{\{[^}]*\}\}", "X", command)  # expressions are one word to the parser
                    try:
                        argv = shlex.split(text)
                    except ValueError:
                        argv = text.split()
                    lanes.append(Lane(
                        workflow=path.name, job=job_name, step=str(step.get("name") or command[:60]), command=command,
                        job_timeout_s=float(job["timeout-minutes"]) * 60 if job.get("timeout-minutes") else None,
                        test_timeout_s=_seconds(argv, "--test-timeout"),
                        deadline_s=_seconds(argv, "--session-deadline"),
                        margin_s=_seconds(argv, "--session-deadline-margin") or DEADLINE_MARGIN_S,
                        lane=_option(argv, "--lane"), xdist="-n" in argv,
                        max_worker_restart=_option(argv, "--max-worker-restart"),
                        hang_dir=_option(argv, "--hang-dir"), lane_report=_option(argv, "--lane-report"),
                        repeats=repeats, uploads=uploads,
                        job_deadline_s=float(set_at.group(1)) if set_at else None))
    return lanes


def nesting_problems(lane: Lane, bounds: Iterable[Bound] | None = None) -> list[str]:
    """What breaks the nesting rule for one lane: the helper bounds its tests use, its --test-timeout, its
    --session-deadline with both margins, and its job's timeout less :data:`JOB_MARGIN_S`; and the sentinel's longest
    path, :data:`SESSION_END_MARGINS`, and its job's timeout less :data:`UPLOAD_CLEARANCE_S`."""
    problems = []
    every = {b.name: b for b in (BOUNDS.values() if bounds is None else bounds)}
    if lane.test_timeout_s is None:
        problems.append(f"{lane.label}: no --test-timeout")
    if lane.deadline_s is None:
        problems.append(f"{lane.label}: no --session-deadline")
    if lane.test_timeout_s is not None and lane.deadline_s is not None and not lane.test_timeout_s < lane.deadline_s:
        problems.append(f"{lane.label}: --test-timeout {lane.test_timeout_s:g}s is not below "
                        f"--session-deadline {lane.deadline_s:g}s")
    if lane.deadline_s is not None and lane.job_timeout_s is not None:
        latest = lane.repeats * (lane.deadline_s + 2 * lane.margin_s)  # a loop runs its sessions one after another
        if latest > lane.job_timeout_s - JOB_MARGIN_S:
            problems.append(f"{lane.label}: the session deadline ends at {latest:g}s (deadline plus two margins"
                            f"{f', {lane.repeats} times' if lane.repeats > 1 else ''}), not {JOB_MARGIN_S:g}s "
                            f"before the job's timeout-minutes ({lane.job_timeout_s:g}s)")
        ended = latest + (SESSION_END_MARGINS - 2) * lane.margin_s  # the last session's longest path, on top of those
        if ended > lane.job_timeout_s - UPLOAD_CLEARANCE_S:
            problems.append(f"{lane.label}: the sentinel's longest path ends the set at {ended:g}s (deadline plus "
                            f"{SESSION_END_MARGINS} margins), not {UPLOAD_CLEARANCE_S:g}s before the job's "
                            f"timeout-minutes ({lane.job_timeout_s:g}s)")
    for b in every.values():
        if b.lanes and (lane.lane or "all") not in b.lanes:
            continue
        outer = every.get(b.within) if b.within else None
        if b.within and outer is None:
            problems.append(f"bound {b.name}: its enclosing bound {b.within} is not declared")
        elif outer is not None and not b.seconds < outer.seconds:
            problems.append(f"bound {b.name} ({b.seconds:g}s) is not below its enclosing bound {outer.name} "
                            f"({outer.seconds:g}s)")
        if lane.test_timeout_s is not None and not b.seconds < lane.test_timeout_s:
            problems.append(f"{lane.label}: bound {b.name} ({b.seconds:g}s) is not below --test-timeout "
                            f"{lane.test_timeout_s:g}s, so the test's own limit fires before the wait can name itself")
    return problems


JOB_DEADLINE_RE = re.compile(r'echo "AEW_JOB_DEADLINE=\$\(\( \$\(date \+%s\) \+ (\d+) \)\)" >> "\$GITHUB_ENV"')


def job_deadline_problems(workflows: Path) -> list[str]:
    """Every job that runs pytest sets its sessions' absolute deadline first (``AEW_JOB_DEADLINE``, which
    ``session_deadline`` takes as a cap): the job's start plus its timeout, less :data:`JOB_MARGIN_S` and the two
    deadline margins. Sessions run one after another in a job (``core``'s fast and serial lanes, a loop of serial runs)
    then all end in time, whatever each one's own ``--session-deadline`` says (review of #217, M1)."""
    import yaml

    problems = []
    for path in sorted(workflows.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            pytest_at = [i for i, st in enumerate(steps) if _commands(str(st.get("run") or ""))]
            if not pytest_at:
                continue
            found = [(i, JOB_DEADLINE_RE.search(str(st.get("run") or ""))) for i, st in enumerate(steps)]
            setting = [(i, m) for i, m in found if m]
            label = f"{path.name} {name}"
            if not setting:
                problems.append(f"{label}: runs pytest but never sets AEW_JOB_DEADLINE")
                continue
            i, m = setting[0]
            want = float(job.get("timeout-minutes") or 0) * 60 - JOB_MARGIN_S - 2 * DEADLINE_MARGIN_S
            if i > min(pytest_at):
                problems.append(f"{label}: AEW_JOB_DEADLINE is set after a pytest step")
            if steps[i].get("shell") != "bash":
                problems.append(f"{label}: the AEW_JOB_DEADLINE step must run in bash")
            if float(m.group(1)) != want:
                problems.append(f"{label}: AEW_JOB_DEADLINE is start + {m.group(1)}s, not start + {want:g}s "
                                f"(timeout-minutes less {JOB_MARGIN_S:g}s and two {DEADLINE_MARGIN_S:g}s margins)")
    return problems


def restored_timeout_problems(workflows: Path, before: dict[str, dict[str, float]]) -> list[str]:
    """Every job that sets ``AEW_JOB_DEADLINE`` keeps its test time: its ``timeout-minutes`` is its timeout before the
    session deadline (``before``, by workflow file and job) plus the deadline's clearance, ``JOB_MARGIN_S`` and two
    ``DEADLINE_MARGIN_S``. A job missing from ``before`` is named too, so a new one is decided, never left out; and
    so is a row of ``before`` whose job is gone or no longer sets a deadline step, so the table never keeps a stale
    row (review of #217 at c2685a4)."""
    import yaml

    clearance = (JOB_MARGIN_S + 2 * DEADLINE_MARGIN_S) / 60
    problems = []
    present: dict[tuple[str, str], bool] = {}  # (file, job) -> whether it sets a deadline step
    for path in sorted(workflows.glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, job in (doc.get("jobs") or {}).items():
            sets = any(JOB_DEADLINE_RE.search(str(st.get("run") or "")) for st in (job or {}).get("steps") or [])
            present[(path.name, name)] = sets
            if not sets:
                continue
            was = before.get(path.name, {}).get(name)
            have = float(job.get("timeout-minutes") or 0)
            if was is None:
                problems.append(f"{path.name} {name}: sets AEW_JOB_DEADLINE but has no timeout before G3a recorded")
            elif have != was + clearance:
                problems.append(f"{path.name} {name}: timeout-minutes {have:g}, not its {was:g} before G3a plus the "
                                f"session deadline's clearance ({clearance:g}): it would lose test time")
    for file, jobs in sorted(before.items()):
        for name in sorted(jobs):
            if (file, name) not in present:
                problems.append(f"{file} {name}: a row of the table, but no such job: remove the row")
            elif not present[(file, name)]:
                problems.append(f"{file} {name}: a row of the table, but the job sets no AEW_JOB_DEADLINE: remove the "
                                "row (or restore the step)")
    return problems
