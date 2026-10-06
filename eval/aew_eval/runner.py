"""One run of one preregistered cell (evaluation component design v0.2, §2, §3, §8 step 2; decisions 4 and 5).

The order is the design's, and nothing else happens here:

1. **Refuse before anything is counted** (:class:`Refused`). The case's fixture is read once and hashed; that hash,
   the oracle commitment, the role profiles and the arm's configuration must be the frozen ones
   (:func:`aew_eval.prereg.require_inputs`); the arm must be one the runner can run, with a configuration valid for
   the case; the scratch root must be outside the AEW checkout and outside every git work tree.
2. **Register the attempt**, durably, before the first action that could reach a provider (decision 5).
3. **Build the fixture** from the same read of it, so the run starts from exactly what was hashed.
4. **Run the arm.** An exception from the arm or the fixture is an ``invalid_measurement`` with a reason code; a
   runner that dies leaves the registered attempt ``runner_lost`` in the ledger, never a vanished sample.
5. **Collect and finalize, once.** The work tree is read as plain files, never through git (an arm may have rewritten
   the scratch repository's configuration): the paths changed against the starting point, and an export of the final
   files outside the scratch repository for the optional scorer. ``outcome.safety.checkout_untouched`` says whether
   the AEW checkout changed.

Scoring through the hidden-evaluator channel is the next slice (design §8 step 3): until then ``outcome.score`` is
whatever the optional ``scorer`` returns over the export, and ``null`` without one.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
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
# The command line's exit codes (2 is argparse's own usage error: nothing registered either).
EXIT_VALID, EXIT_REFUSED, EXIT_COUNTED_NOT_VALID, EXIT_LOST = 0, 1, 3, 4


class Refused(Invalid):
    """The cell was refused before its attempt was registered: nothing is counted."""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _checkout_state() -> str | None:
    """The AEW checkout's status, to prove a run did not touch it (the M3 rule), or None outside a git checkout."""
    try:
        return fixture.git(ROOT, "status", "--porcelain", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError):
        return None


def _inside_a_work_tree(path: Path) -> Path | None:
    """The git work tree (or the AEW checkout) ``path`` lies in, if any: a scratch root must lie in none."""
    resolved = path.resolve()
    for p in (resolved, *resolved.parents):
        if p == ROOT or (p / ".git").exists():
            return p
    return None


def _export(files: dict[str, bytes], dest: Path) -> Path:
    """The final work tree's files, copied outside the scratch repository for scoring (no .gitattributes applies)."""
    dest.mkdir(parents=True)
    for rel, data in files.items():
        if data.startswith(b"link -> "):
            continue  # a link is recorded as changed, never exported (it would point anywhere)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return dest


def run_cell(frozen: dict[str, Any], *, ledger_dir: Path, cell: str, cases: dict[str, Path], work: Path,
             run_name: str, retry_of: str | None = None, scorer: Scorer | None = None,
             deadline_s: float = 3600.0) -> dict[str, Any]:
    """Run ``cell`` of the frozen preregistration once; returns the finalized result. ``cases`` maps each case id
    to its ``case.yaml``; ``work`` is the scratch root (a fresh ``work/<run_name>`` is made under it). Raises
    :class:`Refused` when nothing was registered."""
    experiment = frozen["experiment"]
    # 1. Refuse before anything is counted.
    try:
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
        snap = fixture.snapshot(case)  # read once: hashed now, built from below
        prereg.require_inputs(frozen, case=case.id, arm=arm["id"], case_sha256=snap.sha256,
                              hidden_sha256=case.manifest["hidden_sha256"], roles=frozen["profiles"]["roles"],
                              arm_config=arm["config"])
        runner = arms.arm_for(arm["kind"])
        runner.check(arm["config"], snap)
        owner = _inside_a_work_tree(work)
        if owner is not None:
            raise Invalid(f"the scratch root {work} lies inside the git work tree {owner}: a run is built outside "
                          "every repository (the AEW checkout above all)")
        scratch = work / run_name
        if scratch.exists():
            raise Invalid(f"{scratch} exists: every run gets a fresh scratch directory")
    except Invalid as exc:
        raise Refused(str(exc)) from None
    # 2. Register.
    ledger = AttemptLedger(ledger_dir, frozen)
    run_id = f"{experiment}/{run_name}"
    try:
        line = ledger.register(run_id=run_id, cell=cell, requested_profile=frozen["profiles"]["roles"],
                               retry_of=retry_of)
    except Invalid as exc:  # the ledger refused it (a counted cell, a retry its policy forbids): nothing registered
        raise Refused(str(exc)) from None
    # 3–4. Build and run; anything that goes wrong is recorded, never swallowed into a valid result.
    before = _checkout_state()
    started, t0 = _now(), time.monotonic()
    validity: dict[str, Any] = {"status": "valid", "reason_code": None}
    result = arms.ArmResult()
    outcome: dict[str, Any] = {}
    base = None
    try:
        repo = scratch / "repo"
        start = fixture.build(snap, repo, seeded=bool(arm["config"].get("seeded")))
        base = fixture.git(repo, "rev-parse", "HEAD")  # the repository is still the runner's own here
        result = runner.run(repo, arm["config"], deadline_s=deadline_s)
        final = fixture.files_of(repo)
        outcome["changed_paths"] = fixture.changed_paths(start, final)
        outcome["score"] = scorer(_export(final, scratch / "export")) if scorer else None
    except Exception as exc:  # noqa: BLE001 (the attempt is counted either way; the reason is recorded)
        validity = {"status": "invalid_measurement", "reason_code": f"RUNNER_ERROR:{type(exc).__name__}"}
        outcome["error"] = str(exc)[-600:]
    after = _checkout_state()
    # 5. Finalize, once.
    record = {
        "schema": RUN, "experiment": experiment, "preregistration_sha256": frozen["canonical_sha256"],
        "run_id": run_id,
        "case": {"id": case.id, "sha256": snap.sha256, "hidden_sha256": case.manifest["hidden_sha256"]},
        "arm": {"id": arm["id"], "kind": arm["kind"], "config_sha256": sha256_of(arm["config"])},
        "profile": {"requested": line["requested_profile"], "observed": result.observed_profiles,
                    "mismatch": None},  # not assessed: no arm built yet observes a model profile
        "aew": {}, "harness": result.harness,
        "environment": {"platform": sys.platform, "python": ".".join(map(str, sys.version_info[:3]))},
        "assignment": {**line["assignment"], "randomization_seed": frozen["assignment"]["seed"]},
        "validity": validity, "started_at": started, "ended_at": _now(), "wall_s": round(time.monotonic() - t0, 3),
        "limits": {"deadline_s": deadline_s},
        "outcome": {**result.outcome, **outcome, "base_commit": base,
                    "safety": {"checkout_untouched": None if before is None else before == after}},
        "aew_facts": result.aew_facts, "cost": result.cost, "notes": None,
    }
    ledger.finalize(record)
    return record


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="python -m aew_eval.runner", description="Run one preregistered cell once. "
                                 "Exit 0 valid; 1 refused, nothing registered; 2 usage; 3 counted, not valid; "
                                 "4 registered, then the runner failed (the attempt is runner_lost)")
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
        frozen = prereg.load(args.prereg)
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        record = run_cell(frozen, ledger_dir=args.ledger, cell=args.cell, cases={k: Path(v) for k, v in cases.items()},
                          work=args.work, run_name=args.name, retry_of=args.retry_of)
    except Refused as exc:
        print(f"refused (nothing registered): {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Invalid as exc:
        print(f"failed after registering: {exc}", file=sys.stderr)
        return EXIT_LOST
    print(f"{record['run_id']}: {record['validity']['status']}")
    return EXIT_VALID if record["validity"]["status"] == "valid" else EXIT_COUNTED_NOT_VALID


if __name__ == "__main__":
    sys.exit(main())
