"""Arms: how a case is run (evaluation component design v0.2, §2; decision 2).

An arm takes the built scratch repository and does the case's work in it; the runner does everything around it
(registration, the fixture, collection, finalization). Three kinds exist in the schemas:

* ``scripted``: no model and no provider. Its configuration is the exact edits to make, so a scripted cell is fully
  deterministic: the reference solution, a known-bad control, or the instrument's own end-to-end test.
* ``raw``: the harness alone (:mod:`aew_eval.raw`): OpenCode's own ``build`` agent, the pinned model, the case's
  ``task`` as its only message, nobody answering; the M3 raw mode, generalized.
* ``aew`` (the headless Lead): built by generalizing the M3 driver, which still runs the M3 experiment as it was.
  Until then the runner refuses an ``aew`` cell before anything is registered, so nothing is counted that never ran.

An arm's configuration is checked against its case before the attempt is registered (:meth:`Arm.check`), so a
malformed configuration is a refusal, never a counted ``invalid_measurement`` that spends a retry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aew_eval import fixture
from aew_eval.schemas import Invalid

MODEL_REF = re.compile(r"^(?P<provider>[A-Za-z0-9][A-Za-z0-9._-]*)/(?P<model>[A-Za-z0-9][A-Za-z0-9._/-]*)"
                       r"(?:#(?P<effort>[A-Za-z0-9._-]+))?$")
MODEL_ARMS = frozenset({"aew", "raw"})  # arm kinds whose processes a model controls


@dataclass
class ArmResult:
    """What an arm observed. The runner adds the fixture's facts and the validity verdict."""

    outcome: dict[str, Any] = field(default_factory=dict)
    observed_profiles: list[dict[str, Any]] = field(default_factory=list)
    harness: dict[str, Any] = field(default_factory=dict)
    aew_facts: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    invalid: str | None = None  # a reason code when the arm observed that its own measurement cannot count


class Arm(Protocol):
    kind: str

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None: ...

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        ...


class ScriptedArm:
    """Applies its configuration's ``steps`` in order: ``{"write": PATH, "content": TEXT}`` or ``{"delete": PATH}``.
    Paths are relative, ``/``-separated and stay inside the repository, never in ``.git``. No model, no provider,
    no network."""

    kind = "scripted"

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None:
        if config.get("seeded"):
            fixture.starting_files(snap, seeded=True)  # refuses a case without a seeded tree
        steps = config.get("steps", [])
        if not isinstance(steps, list):
            raise Invalid("a scripted arm's steps are a list")
        for n, step in enumerate(steps, 1):
            if not isinstance(step, dict) or len({"write", "delete"} & step.keys()) != 1:
                raise Invalid(f"scripted step {n} is one of write or delete: {step!r}")
            rel = step.get("write", step.get("delete"))
            if not isinstance(rel, str):
                raise Invalid(f"scripted step {n} names no path: {step!r}")
            fixture.safe_relative(rel, f"scripted step {n}")
            if "write" in step and not isinstance(step.get("content", ""), str):
                raise Invalid(f"scripted step {n}: content is text")

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> ArmResult:
        root = repo.resolve()
        steps = config.get("steps") or []
        for n, step in enumerate(steps, 1):
            rel = fixture.safe_relative(step.get("write") or step.get("delete"), f"scripted step {n}")
            target = root / rel
            if root not in target.resolve().parents:  # a link made by an earlier step is never followed out
                raise Invalid(f"scripted step {n} leaves the repository: {rel}")
            if "write" in step:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(step.get("content", "")), encoding="utf-8", newline="\n")
            else:
                target.unlink()
        return ArmResult(outcome={"steps": len(steps)}, harness={"name": "scripted"})


def model_ref(ref: Any) -> dict[str, str]:
    """``provider/model[#effort]`` as the profile the harness pins: ``{provider, model[, effort]}``."""
    found = MODEL_REF.match(ref) if isinstance(ref, str) else None
    if found is None:
        raise Invalid(f"a model is provider/model[#effort], not {ref!r}")
    return {k: v for k, v in found.groupdict().items() if v}


ARMS: dict[str, Arm] = {"scripted": ScriptedArm()}


def arm_for(kind: str) -> Arm:
    """The arm for ``kind``, or a refusal naming what runs it today."""
    if kind == "raw" and kind not in ARMS:
        from aew_eval.raw import RawArm  # it builds on ArmResult and model_ref above

        ARMS[kind] = RawArm()
    if kind not in ARMS:
        raise Invalid(f"arm kind {kind!r} is not built in the shared runner yet: the M3 driver "
                      "(eval/m3/dogfood/dogfood.py) runs it until it is generalized (design §8, step 2)")
    return ARMS[kind]
