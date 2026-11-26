"""The two arms of a skill evaluation: F19's ``raw`` and ``scripted`` arms with a skill exposure.

An arm's exposure is three keys of its frozen configuration, beside what its kind already needs:

* ``skills`` and ``optional_skills``: ids, read exactly as a role card's are. What the arm gets of them is
  ``aew.skills.plan``'s answer (requested, offered, exposed), copied by ``aew.skills.deliver`` into the run's own
  folder and re-hashed there. The session's rules are the projection's own skill rules (every other id denied, the
  copy readable and never editable), and its configuration gains the one ``skills`` entry, the copy's absolute path:
  the mechanism a worker's run uses.
* ``skill_sha256``: each exposed id's manifest hash, frozen. A skill whose shipped text changed since the freeze is
  refused before anything is registered: a changed skill is another experiment (guide §8).
* ``told`` (optional): text appended to the case's task, verbatim, after a blank line. The experiment's owner writes
  it; the runner adds no instruction of its own. ``python -m skill_eval told`` prints the lines AEW's workers get.

:class:`SkillRawArm` is the model arm: OpenCode's own ``build`` agent on the pinned model (:class:`aew_eval.raw.RawArm`,
whose containment, key scan, harness pin, cost cap and retention it keeps), with the exposure added. Its record gains
``harness.exposure`` (the plan as delivered, with ``loaded`` and ``skill_other`` as the adapter read them from the
session: absent means unknown, never none) and ``harness.first_step_input_tokens``.

:class:`SkillScriptedArm` runs no model: it delivers the exposure and applies its ``steps``. It qualifies the
schedule, the delivery, the budget and the report; what it records says nothing about a skill.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

from aew_eval import arms as base
from aew_eval import fixture, raw
from aew_eval.schemas import Invalid

from aew import skills
from aew.harness.opencode import projection

EXPOSURE_KEYS = ("skills", "optional_skills", "skill_sha256", "told")  # what the two arms may differ in


def _ids(config: dict[str, Any], key: str) -> list[str]:
    value = config.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise Invalid(f"an arm's {key} is a list of skill ids, as a role card's is")
    return value


def planned(config: dict[str, Any]) -> dict[str, Any]:
    """What an arm of this configuration gets: ``aew.skills.plan`` over its two lists, the one answer a run reads."""
    return skills.plan(_ids(config, "skills"), _ids(config, "optional_skills"))


def check_exposure(config: dict[str, Any]) -> dict[str, Any]:
    """The arm's plan, after refusing a configuration that cannot measure what it froze: a named skill AEW's install
    does not hold as its manifest states it, or one whose hash is not the frozen one."""
    plan = planned(config)
    if plan["reasons"]:
        raise Invalid("an arm exposes only skills AEW's install ships: "
                      + ", ".join(f"{name} ({why})" for name, why in sorted(plan["reasons"].items())))
    pins = config.get("skill_sha256", {})
    now = {d["name"]: d["sha256"] for d in plan["delivered"]}
    if not isinstance(pins, dict) or sorted(pins) != sorted(now):
        raise Invalid(f"skill_sha256 pins exactly the arm's exposed skills ({', '.join(sorted(now)) or 'none'})")
    changed = sorted(name for name in now if pins[name] != now[name])
    if changed:
        raise Invalid(f"the shipped text of {', '.join(changed)} is not the frozen one (its hash differs): a changed "
                      "skill is a new experiment id")
    told = config.get("told")
    if told is not None and (not isinstance(told, str) or not told.strip()):
        raise Invalid("an arm's told is the text appended to the task, or absent")
    return plan


def deliver(config: dict[str, Any], folder: Path) -> dict[str, Any]:
    """The arm's exposure copied into ``folder``; an exposure that did not arrive whole is an error, raised before
    the arm launches anything, so no run is counted as measuring an exposure it did not have."""
    plan = planned(config)
    delivered = skills.deliver(plan, folder)
    if delivered["exposed"] != plan["exposed"]:
        raise Invalid(f"the arm's skills were not delivered: {delivered['reasons']}")
    return delivered


def with_told(task: str | None, config: dict[str, Any]) -> str | None:
    told = config.get("told")
    return task if not told or task is None else task.rstrip("\n") + "\n\n" + told.strip() + "\n"


class SkillRawArm(raw.RawArm):
    """F19's raw arm with a skill exposure (the module's docstring)."""

    def __init__(self) -> None:
        self.delivered: dict[str, Any] | None = None  # the run in progress: one arm runs one cell at a time

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None:
        super().check(config, snap)
        check_exposure(config)
        if not config["provider_env"]:
            # register E135's note of 2026-11-06: a keyed, paid model the operator approves, never a free one
            raise Invalid("a skill evaluation's model arm runs a keyed, paid model (provider_env names its key's "
                          "variable): a model that needs no key is a free one, which the evaluation never uses")

    def session_setup(self, session: Any, headless: ModuleType, profile: dict[str, str], config: dict[str, Any],
                      scratch: Path) -> tuple[dict[str, Any], list[dict[str, str]] | None]:
        session_config, _ = super().session_setup(session, headless, profile, config, scratch)
        # Beside the harness state, never in it: a contained run's writable roots are its work tree and that state,
        # so the copy is read-only from inside (raw.contained_layout).
        at = projection.skills_at(os.path.realpath(scratch), os.sep)
        self.delivered = deliver(config, Path(at.folder))
        session.skills = self.delivered  # what the adapter counts `loaded` against (OpenCodeAdapter.collect)
        exposed = list(self.delivered["exposed"])
        if exposed:
            session_config = {**session_config, "skills": [at.folder]}
        return session_config, projection.lead_skill_rules(exposed, at, contained=True)

    def harness_facts(self, summary: dict[str, Any]) -> dict[str, Any]:
        return {"exposure": {**(self.delivered or {}), "loaded": summary.get("loaded"),
                             "skill_other": summary.get("skill_other")},
                "first_step_input_tokens": summary.get("first_step_input_tokens")}

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> base.ArmResult:
        self.delivered = None
        return super().run(repo, config, deadline_s=deadline_s, task=with_told(task, config))


class SkillScriptedArm(base.ScriptedArm):
    """F19's scripted arm with a skill exposure delivered beside its work tree: no model, so nothing is loaded."""

    def check(self, config: dict[str, Any], snap: fixture.Snapshot) -> None:
        super().check(config, snap)
        check_exposure(config)

    def run(self, repo: Path, config: dict[str, Any], *, deadline_s: float, task: str | None = None) -> base.ArmResult:
        delivered = deliver(config, repo.parent / projection.SKILLS_DIR)
        result = super().run(repo, config, deadline_s=deadline_s, task=with_told(task, config))
        result.harness.update(exposure={**delivered, "loaded": {}, "skill_other": 0}, first_step_input_tokens=None)
        return result


@contextmanager
def installed() -> Iterator[None]:
    """F19's runner resolves an arm by its kind (``aew_eval.arms.ARMS``). Inside this block the two kinds a skill
    evaluation uses resolve to the arms above; afterwards the registry is as it was, for every other experiment."""
    before = dict(base.ARMS)
    base.ARMS.update(raw=SkillRawArm(), scripted=SkillScriptedArm())
    try:
        yield
    finally:
        base.ARMS.clear()
        base.ARMS.update(before)


def readable_inside(paths: list[Path], scratch: Path, *, binary: Path) -> list[str]:
    """Which of ``paths`` a contained raw run at ``scratch`` could still read: those F19's layout neither hides with
    the home directory's other entries and the instrument's own files (``raw.hidden_around``, ``raw.layout_paths``)
    nor with the other runs beside it. The evaluator's material must be among the hidden."""
    keep, design = raw.layout_paths(scratch, binary=binary)
    dirs, files = raw.hidden_around(Path(os.path.expanduser("~")), keep)
    hidden = [*dirs, *files, *design, os.path.realpath(scratch.parent)]
    out = []
    for path in paths:
        real = os.path.realpath(path)
        if not any(real == h or real.startswith(h.rstrip(os.sep) + os.sep) for h in hidden):
            out.append(str(path))
    return out
