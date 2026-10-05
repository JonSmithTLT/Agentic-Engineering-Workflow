"""Preregistration (evaluation component design v0.2, section 4; decisions 4 and 5).

A preregistration is frozen before the first paid run. Freezing checks the record's own consistency, materializes the
assignment schedule from the preregistered seed (so the order of runs is decided before any outcome is visible), and
stamps the canonical hash of everything that decides what a run means. Every attempt and result then names that hash,
and a run whose material inputs (a fixture, an oracle commitment, a profile, an arm's configuration) differ from the
frozen record is refused: a change after outcomes are visible is a new experiment id, never an edit.

    python -m aew_eval.prereg freeze PLAN.yaml --by NAME [--out FROZEN.yaml]
    python -m aew_eval.prereg verify FROZEN.yaml
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from aew_eval.canonical import sha256_of
from aew_eval.schemas import Invalid, validate

SCHEMA = "aew/eval-prereg/v1"
FROZEN_FIELDS = ("frozen_at", "frozen_by", "canonical_sha256")


class Mismatch(Invalid):
    """A run's material inputs differ from its frozen preregistration."""


def load(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def dump(record: dict[str, Any], path: Path) -> None:
    path.write_text(yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8",
                    newline="\n")


def check(record: dict[str, Any]) -> None:
    """The record's schema and the rules a schema cannot state."""
    validate(SCHEMA, record, what=f"preregistration {record.get('experiment')!r}")
    arms = [a["id"] for a in record["arms"]]
    cases = [c["id"] for c in record["cases"]]
    for kind, ids in (("arm", arms), ("case", cases)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise Invalid(f"duplicate {kind} ids {dupes}")
    for c in record["cases"]:
        if c["control_of"] is not None and c["control_of"] not in cases:
            raise Invalid(f"case {c['id']} is the control of {c['control_of']}, which is not a case")
    unknown = sorted(set(record["held_out"]) - set(cases))
    if unknown:
        raise Invalid(f"held-out ids {unknown} are not cases")


def schedule(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The run order, decided by the preregistered method and seed alone (decision 4).

    * ``fixed``: cases in order, each arm in order, repetitions innermost.
    * ``counterbalanced``: per case and repetition, the arms in order on odd repetitions and reversed on even ones.
    * ``randomized_blocked``: one block per (case, repetition) holding every arm once; arms shuffled within a block,
      then the blocks shuffled, all from ``random.Random(seed)``.
    """
    arms = [a["id"] for a in record["arms"]]
    reps = range(1, record["runs_per_cell"] + 1)
    method = record["assignment"]["method"]
    rng = random.Random(record["assignment"]["seed"])  # noqa: S311 (a reproducible schedule, not a secret)
    blocks: list[list[tuple[str, str, int]]] = []
    for case in (c["id"] for c in record["cases"]):
        for rep in reps:
            order = list(arms)
            if method == "counterbalanced" and rep % 2 == 0:
                order.reverse()
            elif method == "randomized_blocked":
                rng.shuffle(order)
            blocks.append([(case, arm, rep) for arm in order])
    if method == "randomized_blocked":
        rng.shuffle(blocks)
    flat = [cell for block in blocks for cell in block]
    return [{"order_index": i, "cell": f"{case}/{arm}/{rep}", "case": case, "arm": arm, "repetition": rep}
            for i, (case, arm, rep) in enumerate(flat)]


def digest(record: dict[str, Any]) -> str:
    """The canonical hash of a frozen record: everything except the hash itself."""
    return sha256_of({k: v for k, v in record.items() if k != "canonical_sha256"})


def freeze(record: dict[str, Any], *, by: str, at: datetime | None = None) -> dict[str, Any]:
    """A frozen copy of ``record``: consistent, its schedule materialized, stamped and hashed. Refuses a record that
    is already frozen (a material change is a new experiment, not a refreeze)."""
    if any(k in record for k in FROZEN_FIELDS):
        raise Invalid(f"preregistration {record.get('experiment')!r} is already frozen; a change after freezing is a "
                      "new experiment id")
    if "order" in record.get("assignment", {}):
        raise Invalid("assignment.order is materialized by freezing, from the method and seed; do not write it")
    if not by.strip():
        raise Invalid("a preregistration is frozen by someone")
    check(record)
    frozen = {**record, "assignment": {**record["assignment"], "order": schedule(record)},
              "frozen_at": (at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"), "frozen_by": by}
    check(frozen)
    frozen["canonical_sha256"] = digest(frozen)
    return frozen


def verify(frozen: dict[str, Any]) -> str:
    """The frozen record's hash, after proving it is frozen, consistent and unedited."""
    missing = [k for k in FROZEN_FIELDS if k not in frozen]
    if missing:
        raise Invalid(f"preregistration {frozen.get('experiment')!r} is not frozen (no {', '.join(missing)})")
    check(frozen)
    if frozen["assignment"].get("order") != schedule(frozen):
        raise Invalid("assignment.order is not the schedule the method and seed produce")
    if digest(frozen) != frozen["canonical_sha256"]:
        raise Invalid(f"preregistration {frozen['experiment']!r} was edited after it was frozen: its content no "
                      "longer matches canonical_sha256")
    return frozen["canonical_sha256"]


def require_inputs(frozen: dict[str, Any], *, case: str, arm: str, case_sha256: str, hidden_sha256: str | None,
                   roles: dict[str, str], arm_config: dict[str, Any]) -> None:
    """Refuse a run whose material inputs differ from the frozen preregistration (design §4, completion criteria)."""
    verify(frozen)
    cases = {c["id"]: c for c in frozen["cases"]}
    arms = {a["id"]: a for a in frozen["arms"]}
    if case not in cases or arm not in arms:
        raise Mismatch(f"{case}/{arm} is not a cell of preregistration {frozen['experiment']!r}")
    problems = []
    if cases[case]["sha256"] != case_sha256:
        problems.append(f"the fixture of {case} changed")
    if cases[case]["hidden_sha256"] != hidden_sha256:
        problems.append(f"the oracle commitment of {case} changed")
    if frozen["profiles"]["roles"] != roles:
        problems.append("the role profiles changed")
    if arms[arm]["config"] != arm_config:
        problems.append(f"the configuration of arm {arm} changed")
    if problems:
        raise Mismatch(f"preregistration {frozen['experiment']!r} refuses this run: {'; '.join(problems)}. A "
                       "material change is a new experiment id")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.prereg")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("plan", type=Path)
    f.add_argument("--by", required=True)
    f.add_argument("--out", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("frozen", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "freeze":
            frozen = freeze(load(args.plan), by=args.by)
            dump(frozen, args.out or args.plan)
            print(frozen["canonical_sha256"])
        else:
            print(verify(load(args.frozen)))
    except Invalid as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
