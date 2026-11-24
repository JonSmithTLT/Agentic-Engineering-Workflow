"""A scripted verifier for the offline rehearsal: no model, fixed checks, one emitted verification record.

It qualifies delivery and grading only. Its decision comes from the probe it is given and the candidate's own tests,
never from the skill an arm exposes, so its dispositions carry no information about whether the skill helps.

It runs three checks against the candidate as delivered, and writes nothing inside it (bytecode included):

* ``unit``: the project's tests (``python -m pytest tests``);
* ``goal-probe``: the probe (``probe.py``, or an evaluator's control), copied outside the repository and run with the
  repository as its working directory;
* ``scope``: the implementer's reported files exist and lie inside the Ticket's contract (``ledger/``, ``tests/``).

It then emits an ``aew/evidence/v1`` verification record whose ``goal_backwards`` claim cites the probe and whose
``contract`` claim cites the scope check and the tests. What each check observed is returned beside the record, as
a harness would observe it, so the adapter never takes a claim's word for its evidence.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SCOPE = ("ledger/", "tests/")
REPORTED = ("ledger/money.py", "tests/test_split.py")  # the implementer's report in the case task
CREATED_AT = "2026-01-01T00:00:00Z"  # fixed, so a calibration reproduces byte for byte


def _env(repo: Path) -> dict[str, str]:
    """The caller's environment without its Python and pytest settings, the candidate on the path and no bytecode
    written into it."""
    keep = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "PYTEST", "COV_", "COVERAGE"))}
    return {**keep, "PYTHONPATH": str(repo), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}


def _run(argv: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=repo, env=_env(repo), capture_output=True, text=True, encoding="utf-8",
                          timeout=300, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)


def checks(repo: Path, probe: Path, scratch: Path, revision: str) -> list[dict[str, Any]]:
    """What the three checks observed, each bound to the candidate revision it ran against."""
    unit = _run([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"], repo)
    scratch.mkdir(parents=True, exist_ok=True)
    copy = scratch / "goal_probe.py"
    shutil.copyfile(probe, copy)
    ran = _run([sys.executable, "-B", str(copy)], repo)
    try:
        rows = json.loads(ran.stdout)["checks"] if ran.returncode == 0 else []
    except (ValueError, KeyError, TypeError):
        rows = []
    in_scope = all(rel.startswith(SCOPE) and (repo / rel).is_file() for rel in REPORTED)
    return [
        {"id": "unit", "argv": ["python", "-m", "pytest", "tests"], "snapshot": revision,
         "exit_code": unit.returncode, "ok": unit.returncode == 0, "observations": []},
        {"id": "goal-probe", "argv": ["python", probe.name], "snapshot": revision, "exit_code": ran.returncode,
         "ok": ran.returncode == 0 and bool(rows) and all(r["ok"] for r in rows), "observations": rows},
        {"id": "scope", "argv": None, "snapshot": revision, "exit_code": None, "ok": in_scope,
         "observations": [{"reported": list(REPORTED), "contract": list(SCOPE)}]},
    ]


def record(observed: list[dict[str, Any]], revision: str) -> dict[str, Any]:
    """The verification record those checks support: pass only when every one of them passed."""
    by = {c["id"]: c for c in observed}
    goal = "pass" if by["goal-probe"]["ok"] else "fail"
    contract = "pass" if by["scope"]["ok"] and by["unit"]["ok"] else "fail"
    failed = [r["observed"] for r in by["goal-probe"]["observations"] if not r["ok"]]
    return {
        "schema": "aew/evidence/v1", "id": "E-scripted-1", "kind": "verification", "work_unit": "T-0001",
        "producer": {"invocation": "scripted-verifier", "role": "verifier", "harness": "scripted"},
        "created_at": CREATED_AT,
        "evaluated_snapshot": {"base_revision": revision, "workspace_id": "verifier",
                               "relevant_inputs_fingerprint": revision},
        "method": {"checks": sorted(by)},
        "claim": "T-0001's goals and contract hold for the submitted change",
        "result": "pass" if goal == contract == "pass" else "fail",
        "verification": {
            "scope": "ticket",
            "claims": [
                {"type": "goal_backwards", "claim": "every Ticket goal the probe derives holds", "result": goal,
                 "checks": ["goal-probe"]},
                {"type": "contract", "claim": "the change stays within ledger/ and tests/ and the project's tests "
                 "pass", "result": contract, "checks": ["scope", "unit"]},
            ],
            "suspected_cause": "; ".join(failed) or None,
        },
    }


def verify(repo: Path, probe: Path, scratch: Path, revision: str) -> dict[str, Any]:
    """One scripted verification: what it emitted and what the harness observed."""
    observed = checks(repo, probe, scratch, revision)
    return {"emitted": [record(observed, revision)], "checks": observed}
