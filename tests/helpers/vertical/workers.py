"""The vertical UAT's workers: the fake harness (a real adapter, a real supervisor, a scripted agent process), with each
run's script chosen by the role and scope it was launched as.

The operator and the Lead never name a run or an invocation, so a worker cannot be scripted by its run id the way
the harness tests script theirs. ``RoleAdapter`` is ``FakeAdapter`` with one change: before launching, a run with no
script of its own gets ``role-<role>-<scope>.json`` from the scripts directory (a copy, so the run's own script file
is still what the fake adapter reads and records).

The scripts make a real one-line fix to a real Python sample with a real test, and every check is the project's real
``python -m pytest`` (which writes ``__pycache__``: nothing hides it).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))  # loaded by path in each run's supervisor: its helpers are siblings
from fake_harness import SCRIPTS_ENV, FakeAdapter  # noqa: E402

from aew.harness.contract import LaunchContract  # noqa: E402

ADAPTER = f"fake={HERE}:RoleAdapter"


class RoleAdapter(FakeAdapter):
    name = "fake"

    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        scripts = Path(os.environ[SCRIPTS_ENV])
        own = scripts / f"{contract.run}.json"
        by_role = scripts / f"role-{contract.role}-{contract.scope}.json"
        if not own.exists() and by_role.exists():
            shutil.copyfile(by_role, own)
        return super().launch(contract, agent_env)


# ---------------------------------------------------------------------------------------------- the sample and its fix

# A fresh project: a real bug (the sign of a refund is lost) with a real test that does not yet cover it.
BUGGY = "def format_amount(cents):\n    return f\"${abs(cents) / 100:.2f}\"\n"
FIXED = "def format_amount(cents):\n    return f\"{'-' if cents < 0 else ''}${abs(cents) / 100:.2f}\"\n"
SAMPLE = {
    "README.md": "# ledger\n\nFormats amounts for a small ledger.\n",
    "ledger/__init__.py": "",
    "ledger/money.py": BUGGY,
    "tests/test_money.py": ("from ledger.money import format_amount\n\n\n"
                            "def test_positive():\n    assert format_amount(1500) == \"$15.00\"\n"),
}
GITIGNORE = "__pycache__/\n.pytest_cache/\n*.pyc\n"
FIX = {"ledger/money.py": FIXED,
       "tests/test_money.py": SAMPLE["tests/test_money.py"]
       + "\n\ndef test_negative():\n    assert format_amount(-1500) == \"-$15.00\"\n"}
REQUEST = ("Fix this one-line bug: ledger/money.py's format_amount drops the minus sign, so a refund of -1500 cents "
           "shows as $15.00 instead of -$15.00.")
# The project's unit check: the real pytest, as a user would configure it.
UNIT = ["{python}", "-m", "pytest", "-q", "tests"]

# The Lead's own proposition for the request (its judgement; the vertical Lead's `ticket_draft` fallback).
DRAFT = {
    "title": "Keep the minus sign of negative amounts",
    "risk_class": 1,
    "scope": ["ledger/**", "tests/**"],
    "goal": ["format_amount(-1500) == '-$15.00' through ledger.money"],
    "contract": ["changes stay within ledger/ and tests/"],
    "rationale": "the operator asked for this one-line fix",
    "plan": {"body": "1. In ledger/money.py, keep the sign of negative amounts.\n2. Add a test for a negative "
                     "amount.\n", "affected": ["ledger/money.py", "tests/test_money.py"], "assurance": "none"},
}

IMPL_REPORT = {"claim": "format_amount keeps the minus sign; a focused test covers it", "result": "pass",
               "producer": {"model": "fake-model", "harness": "fake"},
               "implementation": {"files_changed": sorted(FIX), "checks_run": ["unit"], "deviations": [],
                                  "self_review": {"completed": True, "notes": "one-line fix plus its test"}}}
REVIEW = {"claim": "independent review of the change against the plan and contract",
          "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}


def implementer(gate: Path | None = None) -> list[dict[str, Any]]:
    """The fix, the real check, the report. With ``gate``, the implementer waits for that file first (V2: it is still
    running when the operator closes the Lead session), announcing itself in ``<gate>.ready``."""
    wait = ([{"do": "wait_file", "path": str(gate), "ready": f"{gate}.ready", "timeout": 1800}] if gate else [])
    return [*wait, {"do": "write", "files": FIX}, {"do": "check", "id": "unit"},
            {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]


def verifier(scope: str) -> list[dict[str, Any]]:
    checks = [{"do": "check", "id": "unit"}] + ([{"do": "check", "id": "guardrails"}] if scope == "ticket" else [])
    claims = [{"type": "goal_backwards", "claim": "format_amount(-1500) == '-$15.00' observed through the tests",
               "result": "pass", "checks": ["{evidence:check-unit}"]}]
    if scope == "ticket":
        claims.append({"type": "contract", "claim": "the change stays within ledger/ and tests/", "result": "pass",
                       "checks": ["{evidence:check-guardrails}"]})
    return [*checks, {"do": "submit", "kind": "verification", "meta": {
        "claim": "the requested behaviour exists in the evaluated snapshot",
        "verification": {"scope": scope, "claims": claims}}}]


def write_scripts(scripts: Path, *, gate: Path | None = None) -> None:
    scripts.mkdir(parents=True, exist_ok=True)
    for name, steps in (("role-implementer-ticket", implementer(gate)),
                        ("role-reviewer-ticket", [{"do": "submit", "kind": "review", "meta": REVIEW}]),
                        ("role-verifier-ticket", verifier("ticket")),
                        ("role-verifier-integration", verifier("integration"))):
        (scripts / f"{name}.json").write_text(json.dumps(steps), encoding="utf-8")
