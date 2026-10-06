"""Arms: how a case is run (evaluation component design v0.2, §2; decision 2).

An arm takes the built scratch repository and does the case's work in it; the runner does everything around it
(registration, the fixture, collection, finalization). Three kinds exist in the schemas:

* ``scripted``: no model and no provider. Its configuration is the exact edits to make, so a scripted cell is fully
  deterministic: the reference solution, a known-bad control, or the instrument's own end-to-end test.
* ``aew`` (the headless Lead) and ``raw`` (the same harness alone): built by generalizing the M3 driver
  (``eval/m3/dogfood/dogfood.py``), which still runs the M3 experiment as it was. Until then the runner refuses a
  cell of either kind before anything is registered, so nothing is counted that never ran.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aew_eval.schemas import Invalid


@dataclass
class ArmResult:
    """What an arm observed. The runner adds the fixture's facts and the validity verdict."""

    outcome: dict[str, Any] = field(default_factory=dict)
    observed_profiles: list[dict[str, Any]] = field(default_factory=list)
    harness: dict[str, Any] = field(default_factory=dict)
    aew_facts: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)


class Arm(Protocol):
    kind: str

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float) -> ArmResult: ...


class ScriptedArm:
    """Applies its configuration's ``steps`` in order: ``{"write": PATH, "content": TEXT}`` or ``{"delete": PATH}``.
    Paths are relative to the repository and may not leave it. No model, no provider, no network."""

    kind = "scripted"

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float) -> ArmResult:
        root = repo.resolve()
        steps = config.get("steps") or []
        for n, step in enumerate(steps, 1):
            rel = step.get("write") or step.get("delete")
            if not isinstance(rel, str) or not rel:
                raise Invalid(f"scripted step {n} names no path: {step}")
            target = (root / rel).resolve()
            if root not in target.parents:
                raise Invalid(f"scripted step {n} leaves the repository: {rel}")
            if "write" in step:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(step.get("content", "")), encoding="utf-8", newline="\n")
            else:
                target.unlink()
        return ArmResult(outcome={"steps": len(steps)}, harness={"name": "scripted"})


ARMS: dict[str, Arm] = {"scripted": ScriptedArm()}


def arm_for(kind: str) -> Arm:
    """The arm for ``kind``, or a refusal naming what runs it today."""
    if kind not in ARMS:
        raise Invalid(f"arm kind {kind!r} is not built in the shared runner yet: the M3 driver "
                      "(eval/m3/dogfood/dogfood.py) runs it until it is generalized (design §8, step 2)")
    return ARMS[kind]
