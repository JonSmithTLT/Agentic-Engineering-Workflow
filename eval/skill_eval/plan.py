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
* the budget is at most the operator's limit for this evaluation (:data:`LIMIT_USD`);
* no value is still a placeholder (``REQUIRED``, as the template writes what its owner must decide).
"""

from __future__ import annotations

from typing import Any

from aew_eval import prereg
from aew_eval.schemas import Invalid

from skill_eval import arms, walk

LIMIT_USD = 10.0  # the operator's limit on this evaluation's spend (register E135, Source)
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


def shape(frozen: dict[str, Any]) -> dict[str, Any]:
    """The pair a frozen preregistration describes: ``{baseline, candidate_arm, candidate, mode, kind, caps}``, with
    ``caps`` each arm's charge when its cost is unknown. Refuses one that is not a paired skill evaluation."""
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
    plans = {a["id"]: arms.check_exposure(a["config"]) for a in (first, second)}
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
        raise Invalid(f"budget_usd {budget:g} is above the operator's limit for this evaluation, USD {LIMIT_USD:g} "
                      "(register E135): a larger one is the operator's to set, in the register")
    return {"baseline": baseline, "candidate_arm": candidate_arm, "candidate": extra[0], "kind": kind,
            "caps": walk.caps(frozen),
            "mode": MODES[0] if extra[0] in plans[candidate_arm]["requested"] else MODES[1],
            "also_exposed": sorted(exposed[baseline]),
            "candidate_bytes": next(d["bytes"] for d in plans[candidate_arm]["delivered"] if d["name"] == extra[0])}

