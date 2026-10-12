"""Every bound in the test helpers, declared in one place, and the rule that they nest (the hang-and-flake diagnosis
plan, G3 H5).

In #213 the chat bound (1800 s) equalled the vertical lane's ``--test-timeout 1800``, so no inner bound fired first
and nothing named the part that stalled. The rule, pinned for every lane in every workflow
(``tests/unit/test_hang_autopsy_pins.py``):

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
# the sentinel one more margin later; all of it must end at least JOB_MARGIN_S before the job's timeout-minutes, so
# the job's `if: always()` upload still runs with every file closed.
DEADLINE_MARGIN_S = 30.0
JOB_MARGIN_S = 180.0


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


class BoundExpired(Exception):
    """A bounded wait ran out: its message names the bound."""


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
                        repeats=repeats, uploads=uploads))
    return lanes


def nesting_problems(lane: Lane, bounds: Iterable[Bound] | None = None) -> list[str]:
    """What breaks the nesting rule for one lane: the helper bounds its tests use, its --test-timeout, its
    --session-deadline with both margins, and its job's timeout less :data:`JOB_MARGIN_S`."""
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
