"""One run of one preregistered cell (evaluation component design v0.2, §2, §3, §8 step 2; decisions 4 and 5).

The order is the design's, and nothing else happens here:

1. **Refuse a changed input before anything is counted.** The case's fixture hash and oracle commitment, the role
   profiles and the arm's configuration must be the frozen ones (:func:`aew_eval.prereg.require_inputs`), and the arm
   must be one the runner can run. A refusal registers nothing.
2. **Register the attempt**, durably, before the first action that could reach a provider (decision 5).
3. **Build the fixture** into a fresh scratch directory outside every repository a model could reach.
4. **Run the arm.** An exception from the arm or the fixture is an ``invalid_measurement`` with a reason code; a
   runner that dies leaves the registered attempt ``runner_lost`` in the ledger, never a vanished sample.
5. **Collect and finalize, once.** The result names its preregistration, case, arm and assignment exactly as
   registered; what was observed (paths changed, the arm's own facts, whether the AEW checkout was touched) is
   recorded, never re-interpreted.

Scoring through the hidden-evaluator channel is the next slice (design §8 step 3): until then ``outcome.score`` is
whatever the optional ``scorer`` returns over an export of the final tree, and ``null`` without one.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew_eval import arms, fixture, prereg
from aew_eval.canonical import sha256_of
from aew_eval.ledger import AttemptLedger
from aew_eval.schemas import Invalid

RUN = "aew/eval-run/v1"
ROOT = Path(__file__).resolve().parents[2]  # the AEW checkout: a run must leave it untouched
Scorer = Callable[[Path], dict[str, Any]]


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checkout_state() -> str | None:
    """The AEW checkout's status, to prove a run did not touch it (the M3 rule), or None outside a git checkout."""
    try:
        return subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, check=True,
                              capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              creationflags=fixture.NO_WINDOW).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _export(repo: Path, dest: Path) -> Path:
    """The final work tree, committed or not, exported outside the scratch repository for scoring."""
    fixture._git(repo, "add", "-A")
    tree = fixture._git(repo, "write-tree")
    data = subprocess.run(["git", "archive", "--format=tar", tree], cwd=repo, check=True, capture_output=True,
                          stdin=subprocess.DEVNULL, creationflags=fixture.NO_WINDOW).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def run_cell(frozen: dict[str, Any], *, ledger_dir: Path, cell: str, cases: dict[str, Path], work: Path,
             run_name: str, retry_of: str | None = None, scorer: Scorer | None = None,
             deadline_s: float = 3600.0) -> dict[str, Any]:
    """Run ``cell`` of the frozen preregistration once; returns the finalized result. ``cases`` maps each case id
    to its ``case.yaml``; ``work`` is the scratch root (a fresh ``work/<run_name>`` is made under it)."""
    experiment = frozen["experiment"]
    order = {o["cell"]: o for o in frozen["assignment"]["order"]}
    if cell not in order:
        raise Invalid(f"{cell} is not a cell of preregistration {experiment!r}")
    entry = order[cell]
    arm = next(a for a in frozen["arms"] if a["id"] == entry["arm"])
    if entry["case"] not in cases:
        raise Invalid(f"no manifest given for case {entry['case']}")
    case = fixture.load(cases[entry["case"]])
    if case.id != entry["case"]:
        raise Invalid(f"{cases[entry['case']]} is case {case.id}, not {entry['case']}")
    # 1. Refuse before anything is counted.
    prereg.require_inputs(frozen, case=case.id, arm=arm["id"], case_sha256=fixture.case_sha256(case),
                          hidden_sha256=case.manifest["hidden_sha256"], roles=frozen["profiles"]["roles"],
                          arm_config=arm["config"])
    runner = arms.arm_for(arm["kind"])
    scratch = work / run_name
    if scratch.exists():
        raise Invalid(f"{scratch} exists: every run gets a fresh scratch directory")
    # 2. Register.
    ledger = AttemptLedger(ledger_dir, frozen)
    run_id = f"{experiment}/{run_name}"
    line = ledger.register(run_id=run_id, cell=cell, requested_profile=frozen["profiles"]["roles"],
                           retry_of=retry_of)
    # 3–4. Build and run; anything that goes wrong is recorded, never swallowed into a valid result.
    before = _checkout_state()
    started, t0 = _now(), time.monotonic()
    validity: dict[str, Any] = {"status": "valid", "reason_code": None}
    result = arms.ArmResult()
    outcome: dict[str, Any] = {}
    base = None
    try:
        repo = scratch / "repo"
        base = fixture.build(case, repo, seeded=bool(arm["config"].get("seeded")))
        result = runner.run(repo, arm["config"], deadline_s=deadline_s)
        outcome["changed_paths"] = fixture.changed_paths(repo, base)
        outcome["score"] = scorer(_export(repo, scratch / "export")) if scorer else None
    except Exception as exc:  # noqa: BLE001 (the attempt is counted either way; the reason is recorded)
        validity = {"status": "invalid_measurement", "reason_code": f"RUNNER_ERROR:{type(exc).__name__}"}
        outcome["error"] = str(exc)[-600:]
    after = _checkout_state()
    # 5. Finalize, once.
    record = {
        "schema": RUN, "experiment": experiment, "preregistration_sha256": frozen["canonical_sha256"],
        "run_id": run_id,
        "case": {"id": case.id, "sha256": fixture.case_sha256(case), "hidden_sha256": case.manifest["hidden_sha256"]},
        "arm": {"id": arm["id"], "kind": arm["kind"], "config_sha256": sha256_of(arm["config"])},
        "profile": {"requested": line["requested_profile"], "observed": result.observed_profiles,
                    "mismatch": None},  # not assessed: no arm built yet observes a model profile
        "aew": {}, "harness": result.harness,
        "environment": {"platform": sys.platform, "python": ".".join(map(str, sys.version_info[:3])),
                        "checkout_untouched": None if before is None else before == after},
        "assignment": {**line["assignment"], "randomization_seed": frozen["assignment"]["seed"]},
        "validity": validity, "started_at": started, "ended_at": _now(), "wall_s": round(time.monotonic() - t0, 3),
        "limits": {"deadline_s": deadline_s},
        "outcome": {**result.outcome, **outcome, "base_commit": base},
        "aew_facts": result.aew_facts, "cost": result.cost, "notes": None,
    }
    ledger.finalize(record)
    return record


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew_eval.runner", description="Run one preregistered cell once.")
    ap.add_argument("prereg", type=Path, help="the frozen preregistration")
    ap.add_argument("--cell", required=True)
    ap.add_argument("--case", action="append", default=[], metavar="ID=CASE.yaml", help="a case manifest (repeat)")
    ap.add_argument("--ledger", type=Path, required=True, help="the experiment's ledger directory")
    ap.add_argument("--work", type=Path, required=True, help="the scratch root, outside every repository")
    ap.add_argument("--name", required=True, help="this run's name (the run id is <experiment>/<name>)")
    ap.add_argument("--retry-of")
    args = ap.parse_args(argv)
    try:
        cases = dict(pair.split("=", 1) for pair in args.case)
        record = run_cell(prereg.load(args.prereg), ledger_dir=args.ledger, cell=args.cell,
                          cases={k: Path(v) for k, v in cases.items()}, work=args.work, run_name=args.name,
                          retry_of=args.retry_of)
    except (Invalid, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(f"{record['run_id']}: {record['validity']['status']}")
    return 0 if record["validity"]["status"] == "valid" else 2


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    sys.exit(main())
