"""A two-arm lane's runs as pairs, their usage differences, blind grading packets and paired grades: the part of a
report that knows no skill.

Nothing here imports the skill evaluation: it reads a frozen ``aew/eval-prereg/v1`` record, F19's ledger and its run
records, and measures nothing again. It is written to be lifted into ``eval/aew_eval`` as the shared paired report
(the operator, 2026-11-26); :mod:`skill_eval.report` adds what a skill evaluation reads from the same pairs.

* A cell's counted attempt is its latest. A **pair** is one block's two counted runs, named by the caller's two
  ``sides`` (``{name: arm id}``, the reference side first). It is *complete* when both runs are valid and neither
  has a problem of the experiment's own (``problem``); every other pair is listed with why, never dropped.
* **Usage** is what a run record states as numbers: the first step's input tokens, every token category the harness
  reported, the reported cost, the model steps and the wall time. A pair's difference is the second side minus the
  first, for the values both state; a value either lacks is missing for that pair, never zero.
* **Packets** are what a grader may see of each complete pair's runs: never the arm, and nothing of its usage.
* **Grades** join into paired counts. No interval, threshold or verdict is computed here.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew_eval import fixture
from aew_eval.ledger import AttemptLedger
from aew_eval.schemas import Invalid

from skill_eval.walk import blocks, caps, charged, of_cell, record_of

PACKET = "aew/eval-packet/v1"
Problem = Callable[[dict[str, Any], dict[str, Any]], str | None]   # (record, arm) -> why a valid run cannot count
Facts = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]  # (record, arm) -> what else the pair carries


def _flat(value: Any, prefix: str = "") -> dict[str, float]:
    """A usage mapping's numbers by dotted name (``cache.read``); anything that is not a number is left out."""
    out: dict[str, float] = {}
    for key, item in (value.items() if isinstance(value, dict) else ()):
        name = f"{prefix}{key}"
        if isinstance(item, dict):
            out.update(_flat(item, name + "."))
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            out[name] = float(item)
    return out


def usage(record: dict[str, Any]) -> dict[str, float]:
    """What a run record states of its usage, as numbers by name; a value it does not state is absent."""
    harness, outcome, cost = record.get("harness") or {}, record.get("outcome") or {}, record.get("cost") or {}
    out = {f"tokens.{k}": v for k, v in _flat(cost.get("tokens")).items()}
    for name, value in (("first_step_input_tokens", harness.get("first_step_input_tokens")),
                        ("cost_usd", cost.get("provider_reported_usd")), ("steps", outcome.get("model_steps")),
                        ("wall_s", record.get("wall_s"))):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            out[name] = float(value)
    return out


def observation(record: dict[str, Any] | None, arm: dict[str, Any], cap: float, *, problem: Problem | None = None,
                facts: Facts | None = None) -> dict[str, Any]:
    """What one counted run says, for its pair: whether it counts and why not, its usage and its charge."""
    if record is None:
        return {"run_id": None, "counts": False, "why": "runner_lost"}
    status = record["validity"]["status"]
    why = (record["validity"]["reason_code"] or status) if status != "valid" else problem(record, arm) if problem \
        else None
    return {"run_id": record["run_id"], "counts": why is None, "why": why,
            "truncated": (record.get("outcome") or {}).get("truncated"), "usage": usage(record),
            "charged_usd": charged(record, cap), **(facts(record, arm) if facts else {})}


def pairs(frozen: dict[str, Any], ledger_dir: Path, sides: dict[str, str], *, problem: Problem | None = None,
          facts: Facts | None = None) -> list[dict[str, Any]]:
    """Every block of the schedule as a pair, in schedule order. ``sides`` names the two arms, the reference first."""
    first, second = sides
    ledger = AttemptLedger(ledger_dir, frozen)
    by_arm = {a["id"]: a for a in frozen["arms"]}
    arm_caps = caps(frozen)
    out = []
    for block in blocks(frozen):
        seen: dict[str, dict[str, Any]] = {}
        for entry in block:
            attempts = of_cell(ledger, entry["cell"])
            seen[entry["arm"]] = (observation(record_of(ledger, attempts[-1]), by_arm[entry["arm"]],
                                              arm_caps[entry["arm"]], problem=problem, facts=facts)
                                  if attempts else {"run_id": None, "counts": False, "why": "not_run"})
        a, b = seen[sides[first]], seen[sides[second]]
        complete = a["counts"] and b["counts"]
        delta = {name: b["usage"][name] - a["usage"][name]
                 for name in sorted(a["usage"].keys() & b["usage"].keys())} if complete else {}
        out.append({"case": block[0]["case"], "repetition": block[0]["repetition"], "complete": complete,
                    "why": None if complete else {first: a["why"], second: b["why"]},
                    first: a, second: b, "delta": delta})
    return out


def stats(values: list[float], of: int) -> dict[str, Any]:
    """Descriptive only: how many pairs gave the value and how many did not, then its mean, median and range."""
    if not values:
        return {"n": 0, "missing": of, "mean": None, "median": None, "min": None, "max": None}
    return {"n": len(values), "missing": of - len(values), "mean": statistics.fmean(values),
            "median": statistics.median(values), "min": min(values), "max": max(values)}


def deltas(found: list[dict[str, Any]]) -> dict[str, Any]:
    names = sorted({name for p in found for name in p["delta"]})
    return {name: stats([p["delta"][name] for p in found if name in p["delta"]], len(found)) for name in names}


def summary(found: list[dict[str, Any]]) -> dict[str, Any]:
    """How many pairs were planned and complete, and each incomplete one with why."""
    return {"planned": len(found), "complete": sum(p["complete"] for p in found),
            "incomplete": [{"case": p["case"], "repetition": p["repetition"], "why": p["why"]}
                           for p in found if not p["complete"]]}


def cost(found: list[dict[str, Any]], sides: dict[str, str]) -> dict[str, Any]:
    """The complete pairs' usage differences, and what each side's counted runs were charged."""
    first, second = sides
    complete = [p for p in found if p["complete"]]
    return {"complete_pairs": len(complete), f"{second}_minus_{first}": deltas(complete),
            "counted_runs_charged_usd": {side: sum(p[side].get("charged_usd") or 0.0 for p in found)
                                         for side in sides}}


def load_grades(path: Path) -> dict[str, Any]:
    """The grader's file: one ``{"run_id", "task_correct"}`` object per line. A line that is not such an object, or
    a run graded twice, is refused."""
    out: dict[str, Any] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if not isinstance(entry, dict) or not isinstance(entry.get("run_id"), str):
            raise Invalid(f"{path} line {n} is not a JSON object with a run_id")
        if entry["run_id"] in out:
            raise Invalid(f"{path} line {n}: {entry['run_id']} is graded twice")
        out[entry["run_id"]] = entry.get("task_correct")
    return out


def benefit(found: list[dict[str, Any]], grades: dict[str, Any] | None, sides: dict[str, str]) -> dict[str, Any]:
    """Paired counts from a grader's file: both right, each side alone, neither, and the pairs left ungraded."""
    first, second = sides
    if grades is None:
        return {"graded": False, "note": "no grades were given: write the packets, grade them blind, and pass the "
                                         "grades file"}
    counts = {"both_correct": 0, f"{second}_only": 0, f"{first}_only": 0, "neither": 0, "ungraded": 0}
    for p in found:
        if not p["complete"]:
            continue
        a, b = (grades.get(p[side]["run_id"]) for side in (first, second))
        if not isinstance(a, bool) or not isinstance(b, bool):
            counts["ungraded"] += 1
        else:
            counts["both_correct" if a and b else f"{second}_only" if b else f"{first}_only" if a else "neither"] += 1
    return {"graded": True, "complete_pairs": counts}


def packets(frozen: dict[str, Any], ledger_dir: Path, cases: dict[str, Path], found: list[dict[str, Any]],
            sides: dict[str, str]) -> list[dict[str, Any]]:
    """What a grader may see of each complete pair's two runs, in run-id order: the case's task, the exported final
    tree and its hash, the changed paths, and whether the run was cut short. Never the arm or what it cost: a run's
    id names its place in the schedule only."""
    out = []
    ledger = AttemptLedger(ledger_dir, frozen)
    records = {a.run_id: record_of(ledger, a) for a in ledger.attempts().values()}
    for p in found:
        if not p["complete"]:
            continue
        task = fixture.load(cases[p["case"]]).manifest.get("task")
        for side in sides:
            record = records[p[side]["run_id"]] or {}
            scoring = (record.get("outcome") or {}).get("scoring") or {}
            out.append({"schema": PACKET, "run_id": record["run_id"], "case": p["case"], "task": task,
                        "export": scoring.get("export"), "export_sha256": scoring.get("export_sha256"),
                        "changed_paths": record["outcome"].get("changed_paths"),
                        "truncated": record["outcome"].get("truncated")})
    return sorted(out, key=lambda packet: packet["run_id"])
