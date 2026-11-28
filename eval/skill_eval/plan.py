"""What a paired skill evaluation's preregistration must be, checked before anything is registered.

The preregistration is F19's (``aew/eval-prereg/v1``): one record, frozen once, whose schedule and hash every attempt
names. :func:`shape` holds it to the guide's A/B contract (§2) and to the register row's terms, and names the pair:

* exactly two arms of one kind (``raw`` or ``scripted``) whose configurations are equal outside their exposure
  (:data:`skill_eval.arms.EXPOSURE_KEYS`): the task, the model, the limits and every pin are the same bytes;
* the **baseline** arm exposes a subset of what the **candidate** arm exposes, and the candidate arm exactly one skill
  more: the candidate. Skills both arms expose are the other candidates the guide's selection trial keeps frozen;
* the **mode** is where the candidate arm names the candidate: ``procedure`` in its ``skills`` (a worker is told to
  load those), ``selection`` in its ``optional_skills`` (a worker picks from the listing);
* the order is ``randomized_blocked``, so each case and repetition is one block holding both arms in an order drawn
  from the frozen seed, and a run's place in the schedule does not name its arm;
* the budget is at most the operator's limit (:data:`LIMIT_USD`). This bounds one preregistration: nothing here
  sums the budgets of several experiments, which is the operator's to keep;
* no value is still a placeholder (``REQUIRED``, as the template writes what its owner must decide).
"""

from __future__ import annotations

from typing import Any

from aew_eval import prereg, walk
from aew_eval.schemas import Invalid

from skill_eval import arms

# The operator's limit of USD 10 (register E135, Source). The runner holds each preregistration's budget to it and
# sums nothing across experiments: what the limit covers in total is the operator's to say and to keep.
LIMIT_USD = 10.0
KINDS = ("raw", "scripted")
METHOD = "randomized_blocked"
PLACEHOLDER = "REQUIRED"
MODES = ("procedure", "selection")


def _placeholders(value: Any, where: str) -> list[str]:
    if isinstance(value, str):
        return [where] if value.startswith(PLACEHOLDER) else []
    if isinstance(value, dict):
        return [hit for k, v in value.items() for name in [f"{where}.{k}" if where else str(k)]
                for hit in ([name] if str(k).startswith(PLACEHOLDER) else _placeholders(v, name))]
    if isinstance(value, list):
        return [hit for n, v in enumerate(value) for hit in _placeholders(v, f"{where}[{n}]")]
    return []


def _as_frozen(config: dict[str, Any]) -> dict[str, Any]:
    """An arm's plan read from its frozen configuration alone: what it pinned is what it exposed (a run checks that
    before it is registered), and its ``skills`` are what it requested. Nothing of today's install is read."""
    pins = config.get("skill_sha256", {})
    if not isinstance(pins, dict):
        raise Invalid("an arm's skill_sha256 maps each exposed skill to its frozen hash")
    return {"exposed": sorted(pins), "requested": [s for s in config.get("skills") or [] if s in pins],
            "delivered": []}


def shape(frozen: dict[str, Any], *, installed: bool = True) -> dict[str, Any]:
    """The pair a frozen preregistration describes: ``{baseline, candidate_arm, candidate, mode, kind, caps}``, with
    ``caps`` each arm's charge when its cost is unknown. Refuses one that is not a paired skill evaluation.

    Before a run, each arm's exposure is also held to today's install (``installed``): a skill that is not shipped,
    or whose text changed since the freeze, is refused. A report of runs already made passes ``installed=False`` and
    reads the pair from the frozen record alone, so a finished lane stays reportable after a skill's text moves on;
    ``candidate_bytes`` is then unknown here and comes from the run records."""
    prereg.verify(frozen)
    left = _placeholders({k: v for k, v in frozen.items() if k != "assignment"}, "")
    if left:
        raise Invalid(f"the preregistration still holds placeholders its owner decides: {', '.join(left)}")
    if len(frozen["arms"]) != 2 or len({a["kind"] for a in frozen["arms"]}) != 1:
        raise Invalid("a skill evaluation has exactly two arms of one kind: the baseline and the candidate")
    kind = frozen["arms"][0]["kind"]
    if kind not in KINDS:
        raise Invalid(f"a skill evaluation's arms are {' or '.join(KINDS)}, not {kind}")
    first, second = frozen["arms"]
    rest = [{k: v for k, v in a["config"].items() if k not in arms.EXPOSURE_KEYS} for a in (first, second)]
    if rest[0] != rest[1]:
        differ = sorted(k for k in rest[0].keys() | rest[1].keys() if rest[0].get(k) != rest[1].get(k))
        raise Invalid(f"the two arms differ in {', '.join(differ)}: they may differ in their exposure alone "
                      f"({', '.join(arms.EXPOSURE_KEYS)})")
    plans = {a["id"]: arms.check_exposure(a["config"]) if installed else _as_frozen(a["config"])
             for a in (first, second)}
    exposed = {arm: set(plan["exposed"]) for arm, plan in plans.items()}
    baseline, candidate_arm = sorted(plans, key=lambda arm: len(exposed[arm]))
    extra = sorted(exposed[candidate_arm] - exposed[baseline])
    if not exposed[baseline] < exposed[candidate_arm] or len(extra) != 1:
        raise Invalid("the candidate arm exposes what the baseline arm exposes and exactly one skill more, the "
                      f"candidate; here {sorted(exposed[first['id']])} and {sorted(exposed[second['id']])}")
    if frozen["assignment"]["method"] != METHOD:
        raise Invalid(f"a skill evaluation's order is {METHOD}: each case and repetition holds both arms, in an "
                      "order drawn from the frozen seed")
    budget = float(frozen["profiles"]["budget_usd"])
    if budget > LIMIT_USD:
        raise Invalid(f"budget_usd {budget:g} is above USD {LIMIT_USD:g}, the operator's limit (register E135), which "
                      "no one preregistration may exceed. This check bounds this preregistration alone: the total "
                      "across experiments is the operator's to keep")
    return {"baseline": baseline, "candidate_arm": candidate_arm, "candidate": extra[0], "kind": kind,
            "caps": walk.caps(frozen),
            "mode": MODES[0] if extra[0] in plans[candidate_arm]["requested"] else MODES[1],
            "also_exposed": sorted(exposed[baseline]),
            "told_differs": first["config"].get("told") != second["config"].get("told"),
            "candidate_bytes": next((d["bytes"] for d in plans[candidate_arm]["delivered"] if d["name"] == extra[0]),
                                    None)}

