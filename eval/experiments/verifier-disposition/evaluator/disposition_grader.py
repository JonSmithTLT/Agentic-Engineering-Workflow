"""The blinded disposition grader. Evaluator-only: it holds no arm and reads the expected decisions.

An observation (the public adapter's ``aew/verifier-disposition/v1``) is graded only once :func:`blind` has removed
the arm and its exposure; :func:`grade` refuses anything else. The grade is the first disposition against the
expected one: ``correct_accept``, ``justified_rework``, ``false_accept`` or ``false_rework``; ``no_disposition``
when the verifier emitted none, and ``invalid`` when the cell measured something else (it is reported, never
graded). Unsupported claims, authority violations and cost are carried beside the grade and never change it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
EXPECTED = HERE / "expected.yaml"
SCHEMA = "aew/verifier-disposition-grade/v1"
ARM_FIELDS = ("arm", "exposure")
GRADES = {("accept", "accept"): "correct_accept", ("rework", "rework"): "justified_rework",
          ("accept", "rework"): "false_accept", ("rework", "accept"): "false_rework"}


def expected_sha256(path: Path = EXPECTED) -> str:
    """The commitment ``plan.yaml`` freezes: the expected decisions' bytes with LF line ends."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_expected(path: Path = EXPECTED) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def blind(observation: dict[str, Any]) -> dict[str, Any]:
    """The observation without anything that names or reveals its arm."""
    return {k: v for k, v in observation.items() if k not in ARM_FIELDS}


def grade(blinded: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """One blinded observation's grade."""
    leaked = [k for k in ARM_FIELDS if k in blinded]
    if leaked:
        raise ValueError(f"the grader refuses an unblinded observation (it carries {leaked}); blind() it first")
    want = expected["cases"][blinded["case"]]["disposition"]
    got = blinded["disposition"]
    if blinded["validity"]["status"] != "valid":
        outcome = "invalid"
    elif got is None:
        outcome = "no_disposition"
    else:
        outcome = GRADES[(got, want)]
    return {"schema": SCHEMA, "run_id": blinded["run_id"], "case": blinded["case"], "grade": outcome,
            "expected_disposition": want, "disposition": got, "supported_failure": blinded["supported_failure"],
            "unsupported_claims": [u["reason"] for u in blinded["unsupported_claims"]],
            "authority_violations": len(blinded["authority_violations"]), "cost": blinded["cost"]}
