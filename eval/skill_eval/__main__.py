"""The skill evaluation's command line (``README.md`` walks through it)::

    python -m skill_eval materialize CASES.yaml --cases DIR --evaluator DIR [--only ID ...] [--answer-file NAME]
    python -m skill_eval told [--skills ID ...] [--optional ID ...]
    python -m skill_eval check FROZEN.yaml
    python -m skill_eval run FROZEN.yaml --cases DIR --lane DIR --evaluator DIR [--limit N] [--deadline-s S]
    python -m skill_eval packets FROZEN.yaml --cases DIR --lane DIR
    python -m skill_eval report FROZEN.yaml --lane DIR [--evaluator DIR] [--grades FILE]

Run with ``eval/`` on ``PYTHONPATH``, as F19's own commands are (``python -m aew_eval.prereg freeze`` freezes the
plan). Exit 0 done; 1 refused, nothing registered by this call; 2 usage; 3 stopped before the schedule's end (the
budget, ``--limit`` or a lane error), with what ran recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aew_eval import prereg
from aew_eval.schemas import Invalid

from aew import skills
from aew.harness.opencode import projection
from skill_eval import cases, plan, report
from skill_eval import run as lane_run


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m skill_eval",
                                 description="The skill evaluation's runner (register E135).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("materialize", help="a candidate's public cases as F19 cases, and the evaluator's key")
    m.add_argument("source", type=Path)
    m.add_argument("--cases", type=Path, required=True)
    m.add_argument("--evaluator", type=Path, required=True)
    m.add_argument("--only", nargs="+")
    m.add_argument("--answer-file")
    t = sub.add_parser("told", help="the lines AEW tells a worker whose card names these skills")
    t.add_argument("--skills", nargs="*", default=[])
    t.add_argument("--optional", nargs="*", default=[])
    for name, text in (("check", "whether a frozen preregistration is a paired skill evaluation"),
                       ("run", "the cells that still need an attempt, under the budget"),
                       ("packets", "what a grader may see of each complete pair, blind"),
                       ("report", "the pairs and the three measures")):
        p = sub.add_parser(name, help=text)
        p.add_argument("frozen", type=Path)
        if name in ("run", "packets"):
            p.add_argument("--cases", type=Path, required=True)
        if name != "check":
            p.add_argument("--lane", type=Path, required=True)
        if name in ("run", "report"):
            p.add_argument("--evaluator", type=Path, required=name == "run")
        if name == "run":
            p.add_argument("--limit", type=int)
            p.add_argument("--deadline-s", type=float, default=3600.0)
        if name == "report":
            p.add_argument("--grades", type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "materialize":
            key = cases.materialize(args.source, args.cases, args.evaluator, only=args.only,
                                    answer_file=args.answer_file)
            out: object = {"cases": key["preregistration_cases"]}
        elif args.cmd == "told":
            out = {"told": "\n".join(projection.skills_text(skills.plan(args.skills, args.optional)))}
        else:
            frozen = prereg.load(args.frozen)
            if args.cmd == "check":
                out = plan.shape(frozen)
            elif args.cmd == "run":
                out = lane_run.run(frozen, cases=cases.manifests(args.cases), lane=args.lane,
                                   evaluator=[args.evaluator, args.cases], deadline_s=args.deadline_s,
                                   limit=args.limit)
            elif args.cmd == "packets":
                out = report.packets(frozen, args.lane / "ledger", cases.manifests(args.cases))
            else:
                out = report.report(frozen, args.lane,
                                    key=cases.load_key(args.evaluator) if args.evaluator else None,
                                    grades=report.load_grades(args.grades) if args.grades else None)
    except Invalid as exc:  # F19's Refused is one: nothing was registered by the call that raised it
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=1, sort_keys=True))
    return 3 if args.cmd == "run" and isinstance(out, dict) and out["stopped"] != "done" else 0


if __name__ == "__main__":
    sys.exit(main())
