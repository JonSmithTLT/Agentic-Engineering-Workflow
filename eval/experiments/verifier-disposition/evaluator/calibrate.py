"""Qualify the expected decisions and the grader on the public cases, with fixed trusted scripts only.

1. **Truth.** Each case's candidate is built as the verifier receives it and judged by the M3 T5 hidden checks
   (``eval/m3/dogfood/hidden.py``). The goals it violates and its expected disposition (accept only when none is
   violated) must be ``expected.yaml``'s.
2. **Decision controls.** The scripted verifier runs on each case with the honest probe, and three deliberately wrong
   decisions are made: a plausible false accept (a probe that never checks the leftover order, on VD-3), a
   plausible false rework (a probe that expects the leftover on the last shares, on VD-1) and a fabricated accept
   (a passing record citing checks nobody ran, on VD-2). Each goes through the public adapter, is blinded and graded,
   and must get its named grade.

Prints JSON that reproduces ``qualification.json``; a mismatch with any expected result exits with an error. Execution
is uncontained: these are known public programs, and no candidate tree from a model is accepted here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
EVAL = EXPERIMENT.parents[1]
sys.path[:0] = [str(EVAL), str(EVAL.parent / "src"), str(EXPERIMENT), str(HERE)]

import disposition_adapter as adapter  # noqa: E402
import disposition_grader as grade  # noqa: E402
import scripted_verifier  # noqa: E402
from aew_eval import fixture  # noqa: E402

CASES = ("VD-1", "VD-2", "VD-3")
HIDDEN = EVAL / "m3" / "dogfood" / "hidden.py"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROBE = EXPERIMENT / "probe.py"
# name: (case, probe or None for the fabricated record, the grade the grader must give)
CONTROLS = {
    "honest-clean": ("VD-1", PROBE, "correct_accept"),
    "honest-t5": ("VD-2", PROBE, "justified_rework"),
    "honest-repair": ("VD-3", PROBE, "justified_rework"),
    "false-accept": ("VD-3", HERE / "controls" / "sum_only.py", "false_accept"),
    "false-rework": ("VD-1", HERE / "controls" / "last_leftover.py", "false_rework"),
    "fabricated-accept": ("VD-2", None, "false_accept"),
}


def goal_of(hidden_check: str) -> str:
    """The T-0001 goal an M3 T5 hidden check observes: the leftover examples are G1, the totals G2, the refusal G3."""
    if "raises" in hidden_check:
        return "G3"
    if "adds up" in hidden_check or hidden_check == "one part":
        return "G2"
    return "G1"


def build(case_id: str, root: Path) -> tuple[Path, str]:
    """The candidate as delivered: base and the case's candidate in a fresh one-commit repository."""
    snap = fixture.snapshot(fixture.load(EXPERIMENT / f"case-{case_id}.yaml"))
    repo = root / "repo"
    fixture.build(snap, repo, seeded=True)
    return repo, fixture.git(repo, "rev-parse", "HEAD")


def truth(case_id: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="vd-truth-") as temporary:
        repo, _ = build(case_id, Path(temporary))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "COV_", "COVERAGE"))}
        ran = subprocess.run([sys.executable, "-B", str(HIDDEN), "T5", str(repo)], capture_output=True, text=True,
                             encoding="utf-8", env={**env, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=600,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, check=True)
    result = json.loads(ran.stdout)
    failed = [c["name"] for c in result["checks"] if not c["ok"]]
    violated = sorted({goal_of(name) for name in failed})
    return {"hidden_failures": failed, "violated": violated, "disposition": "rework" if violated else "accept",
            "project_tests": result["project_tests"]}


def control(name: str, case_id: str, probe: Path | None) -> dict:
    with tempfile.TemporaryDirectory(prefix="vd-control-") as temporary:
        root = Path(temporary)
        repo, revision = build(case_id, root)
        if probe is None:
            honest = scripted_verifier.verify(repo, PROBE, root / "scratch", revision)
            record = copy.deepcopy(honest["emitted"][0])
            record["result"] = "pass"
            for claim in record["verification"]["claims"]:
                claim["result"] = "pass"
            record["verification"]["suspected_cause"] = None
            emitted, observed = [record], []  # nothing the harness saw backs its citations
        else:
            run = scripted_verifier.verify(repo, probe, root / "scratch", revision)
            emitted, observed = run["emitted"], run["checks"]
        changed = fixture.changed_paths(fixture.starting_files(
            fixture.snapshot(fixture.load(EXPERIMENT / f"case-{case_id}.yaml")), seeded=True), fixture.files_of(repo))
        observation = adapter.observe(run_id=f"calibration/{name}", case=case_id, arm="calibration",
                                      emitted=emitted, checks=observed, candidate_revision=revision,
                                      intended_skills=[], exposure=adapter.projection([])["skills"],
                                      changed_paths=changed, cost=None)
    graded = grade.grade(grade.blind(observation), grade.load_expected())
    return {"case": case_id, "probe_sha256": None if probe is None else
            hashlib.sha256(probe.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "disposition": graded["disposition"], "grade": graded["grade"],
            "supported_failure": graded["supported_failure"], "unsupported_claims": graded["unsupported_claims"],
            "authority_violations": graded["authority_violations"]}


def calibrate() -> dict:
    expected = grade.load_expected()
    truths = {case_id: truth(case_id) for case_id in CASES}
    for case_id, found in truths.items():
        want = expected["cases"][case_id]
        if (found["disposition"], found["violated"]) != (want["disposition"], sorted(want["violated"])):
            raise ValueError(f"{case_id}: the hidden checks give {found}, expected.yaml says {want}")
    controls = {}
    for name, (case_id, probe, wanted) in CONTROLS.items():
        controls[name] = control(name, case_id, probe)
        if controls[name]["grade"] != wanted:
            raise ValueError(f"{name}: graded {controls[name]['grade']}, expected {wanted}")
    return {"instrument": "public adapter and blinded grader on fixed trusted scripts", "contained": False,
            "expected_sha256": grade.expected_sha256(), "truth": truths, "controls": controls}


if __name__ == "__main__":
    print(json.dumps(calibrate(), indent=2))
