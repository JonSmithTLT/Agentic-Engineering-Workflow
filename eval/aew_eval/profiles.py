"""Profile records (``aew/eval-profile/v1``): a model through a pinned harness, in a capability class, and how far it
is qualified (agent-effectiveness synthesis §13.1 and §13.4; adoption record §10.3).

Profiles are capability classes, not models: ``frontier``, ``mid`` and ``lower-bound``. A record is reusable across
experiments, so a later lane pins the same ``ref`` and cites the same qualification. Its ``qualification_state`` is
never written freely: :func:`derive_state` computes it from the record's facts, and :func:`check` refuses a record
whose stated state disagrees.

* ``unavailable``: the pinned harness's served catalog did not offer the model when it was checked.
* ``unqualified``: not checked yet, or the floor has not been run.
* ``floor_failed``: it did not complete the bridge handshake and the typed submit path.
* ``floor_passed``: it did; for a lower-bound profile the ceiling has no verdict yet: not run (``not_run``), or run
  with no tree-observable behaviour shown and the session-observable ones not yet scored
  (``pending_session_behaviours``), or the class has none.
* ``not_a_lower_bound``: floor passed, and on the seeded lane it showed none of the eight weak-worker behaviours, so
  it cannot tell whether AEW's scaffolding helps; the next-cheaper profile is tried (synthesis §13.4).
* ``ceiling_inconclusive``: floor passed, none of the observable behaviours was shown, and some behaviour could not be
  observed (ceiling ``inconclusive``, which lists them: for example behaviours 4 and 5 when every run of their case was
  cut short by its cost cap). Not final: neither a lower bound nor ruled out.
* ``qualified``: floor passed and, for a lower-bound profile, at least one behaviour shown on the seeded lane.

    python -m aew_eval.profiles check PROFILES.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

from aew_eval.arms import model_ref
from aew_eval.schemas import Invalid, validate

SCHEMA = "aew/eval-profile/v1"


def derive_state(record: dict[str, Any]) -> str:
    """The qualification state the record's availability, floor and ceiling establish."""
    offered = record["availability"].get("offered_by_pinned_harness")
    if offered is False:
        return "unavailable"
    floor = record["floor"]["state"]
    if offered is None or floor == "not_run":
        return "unqualified"
    if floor == "failed":
        return "floor_failed"
    ceiling = record["ceiling"]["state"]
    if record["class"] != "lower-bound" or ceiling in ("not_run", "not_applicable", "pending_session_behaviours"):
        return "floor_passed"
    if ceiling == "inconclusive":
        return "ceiling_inconclusive"
    return "qualified" if ceiling == "behaviours_shown" else "not_a_lower_bound"


def check(record: dict[str, Any]) -> None:
    """The record's schema and the rules a schema cannot state."""
    validate(SCHEMA, record, what=f"profile {record.get('id')!r}")
    ref = model_ref(record["ref"])
    if (ref["provider"], ref["model"], ref.get("effort")) != (record["provider"], record["model"],
                                                               record.get("effort")):
        raise Invalid(f"profile {record['id']}: ref {record['ref']} is not its provider, model and effort")
    ceiling = record["ceiling"]
    if record["class"] != "lower-bound" and ceiling["state"] not in ("not_run", "not_applicable"):
        raise Invalid(f"profile {record['id']}: only a lower-bound profile has a ceiling (the weak-worker behaviours)")
    if ceiling["state"] == "behaviours_shown" and not ceiling.get("behaviours"):
        raise Invalid(f"profile {record['id']}: behaviours_shown names the behaviours shown")
    if ceiling["state"] != "behaviours_shown" and ceiling.get("behaviours"):
        raise Invalid(f"profile {record['id']}: behaviours are listed only when the ceiling shows them")
    unobserved = ceiling.get("unobserved") or []
    if ceiling["state"] == "inconclusive" and not unobserved:
        raise Invalid(f"profile {record['id']}: an inconclusive ceiling lists the behaviours it could not observe")
    if ceiling["state"] == "none_shown" and unobserved:
        raise Invalid(f"profile {record['id']}: none_shown means every behaviour was observed and none shown, but "
                      f"{sorted(unobserved)} could not be observed: the ceiling is inconclusive")
    if unobserved and ceiling["state"] not in ("inconclusive", "behaviours_shown", "pending_session_behaviours"):
        raise Invalid(f"profile {record['id']}: unobserved behaviours are listed only for a ceiling that was run")
    ran = ("behaviours_shown", "none_shown", "inconclusive", "pending_session_behaviours")
    if ceiling["state"] in ran and record["floor"]["state"] != "passed":
        raise Invalid(f"profile {record['id']}: a ceiling result needs a passed floor (a model that cannot submit "
                      "through the bridge is not measured on the lane)")
    derived = derive_state(record)
    if record["qualification_state"] != derived:
        raise Invalid(f"profile {record['id']}: its qualification_state is {record['qualification_state']}, but its "
                      f"availability, floor and ceiling establish {derived}")


def load(path: Path) -> list[dict[str, Any]]:
    """Every profile record in a YAML file (a list), each checked; ids are unique."""
    records = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise Invalid(f"{path} holds a non-empty list of profile records")
    ids = [r.get("id") if isinstance(r, dict) else None for r in records]
    dupes = sorted({i for i in ids if ids.count(i) > 1 and i is not None})
    if dupes:
        raise Invalid(f"duplicate profile ids {dupes}")
    for record in records:
        if not isinstance(record, dict):
            raise Invalid(f"{path}: a profile record is a mapping")
        check(record)
    known = set(ids)
    for record in records:
        if record.get("twin_of") is not None and record["twin_of"] not in known:
            raise Invalid(f"profile {record['id']} is the twin of {record['twin_of']}, which is not a profile here")
    return records


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("profiles", type=Path)
    args = ap.parse_args(argv)
    try:
        for record in load(args.profiles):
            print(f"{record['id']}: {record['qualification_state']}")
    except Invalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
