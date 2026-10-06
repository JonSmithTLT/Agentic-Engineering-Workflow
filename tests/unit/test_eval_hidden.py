"""The evaluation instrument's third slice, the hidden-evaluator channel (register F19; the evaluation component design
v0.2, §5 and §8 step 3; decisions 5 and 7): an oracle outside every repository a model works in, committed to by its
content hash, refused before registration when it changed or its held-out case was exposed, never reachable through the
environment an arm starts processes from, and run after the arm in an isolated process the model's tree cannot hijack.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, hidden, prereg, runner  # noqa: E402

FIX = {"write": "calc.py", "content": "def add(a, b):\n    return a + b\n"}
CHECKS = '''
import subprocess, sys

def checks(tree):
    out = subprocess.run([sys.executable, "-c", "import calc; print(calc.add(2, 3))"], cwd=tree,
                         capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    yield "add(2, 3) is 5", out == "5", out
'''


def make_oracle(hidden_root: Path, cid: str = "C1", checks: str = CHECKS) -> Path:
    oracle = hidden_root / "cases" / cid / "oracle"
    oracle.mkdir(parents=True)
    (oracle / "checks.py").write_text(checks, encoding="utf-8", newline="\n")
    return oracle


def make_case(root: Path, commitment: str | None, cid: str = "C1") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": cid, "family": "demo", "fixture": {"base": "base"},
                "hidden_sha256": commitment, "control_of": None}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def plan_for(case_path: Path, *, steps: list | None = None, held_out: bool = False) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": "Does the reference fix the bug?",
        "arms": [{"id": "ref", "kind": "scripted", "description": "the reference edit",
                  "config": {"steps": [FIX] if steps is None else steps}}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case),
                   "hidden_sha256": case.manifest["hidden_sha256"], "control_of": None}],
        "profiles": {"roles": {"lead": "none"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "fixed", "metrics": [{"name": "fixed", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement", "runner_lost"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [case.id] if held_out else [],
        "scoring": {"hidden_channel": "aew_eval.hidden", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "an exposed case leaves the held-out pool", "amendment_policy": "a change is a new id",
    }
    return prereg.freeze(record, by="tester")


def setup(tmp_path: Path, **plan) -> tuple[dict, Path, Path]:
    secret = tmp_path / "private"
    oracle = make_oracle(secret)
    case = make_case(tmp_path / "case", hidden.content_sha256(oracle))
    return plan_for(case, **plan), case, secret


def run(f: dict, case_path: Path, tmp_path: Path, name: str = "r1", **kw) -> dict:
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name=name, **kw)


def nothing_registered(tmp_path: Path) -> bool:
    return not (tmp_path / "ledger" / "attempts.jsonl").exists()


# ---------------------------------------------------------------------------------------------- the oracle

def test_the_oracle_hash_covers_its_content_and_ignores_line_ends(tmp_path):
    oracle = make_oracle(tmp_path / "h")
    first = hidden.content_sha256(oracle)
    checks = oracle / "checks.py"
    checks.write_bytes(checks.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout of the private repository
    assert hidden.content_sha256(oracle) == first
    (oracle / "reference").mkdir()
    (oracle / "reference" / "calc.py").write_text("x\n", encoding="utf-8")
    assert hidden.content_sha256(oracle) != first


def test_an_oracle_without_checks_is_refused(tmp_path):
    (tmp_path / "h" / "cases" / "C1" / "oracle").mkdir(parents=True)
    with pytest.raises(hidden.Invalid, match="no checks.py"):
        hidden.Oracle.locate(tmp_path / "h", "C1")


def test_taking_the_root_removes_it_from_the_environment():
    env = {hidden.ENV: "/private/eval", "OTHER": "x"}
    assert hidden.take_root(env) == Path("/private/eval") and env == {"OTHER": "x"}
    assert hidden.take_root({}) is None


# ---------------------------------------------------------------------------------------------- the runner

def test_a_hidden_case_is_scored_by_its_oracle_after_the_arm(tmp_path):
    f, case, secret = setup(tmp_path)
    record = run(f, case, tmp_path, hidden_root=secret)
    score = record["outcome"]["score"]
    assert record["validity"]["status"] == "valid", record
    assert score["passed"] is True and score["hidden_sha256"] == record["case"]["hidden_sha256"]
    assert [c["name"] for c in score["checks"]] == ["add(2, 3) is 5"]


def test_a_failing_change_scores_false_and_stays_valid(tmp_path):
    f, case, secret = setup(tmp_path, steps=[{"write": "NOTES.md", "content": "looked at it\n"}])
    record = run(f, case, tmp_path, hidden_root=secret)
    assert record["validity"]["status"] == "valid" and record["outcome"]["score"]["passed"] is False


def test_no_arm_sees_the_hidden_root(tmp_path, monkeypatch):
    """Decision: the root is evaluator-only. It is out of the environment before the arm runs, so nothing the arm
    starts can inherit it."""
    f, case, secret = setup(tmp_path)
    monkeypatch.setenv(hidden.ENV, str(secret))
    seen = {}
    real = arms.ScriptedArm.run

    def spy(self, repo, config, *, deadline_s):
        import os

        seen["root"] = os.environ.get(hidden.ENV)
        return real(self, repo, config, deadline_s=deadline_s)

    monkeypatch.setattr(arms.ScriptedArm, "run", spy)
    record = run(f, case, tmp_path)  # the root comes from the environment
    assert seen == {"root": None} and record["outcome"]["score"]["passed"] is True


@pytest.mark.parametrize("problem", ["no_root", "changed", "exposed"])
def test_a_cell_with_an_unusable_oracle_is_refused_before_anything_is_counted(tmp_path, problem):
    f, case, secret = setup(tmp_path, held_out=problem == "exposed")
    oracle = secret / "cases" / "C1" / "oracle"
    if problem == "changed":
        (oracle / "checks.py").write_text(CHECKS + "\n# weakened\n", encoding="utf-8")
    if problem == "exposed":
        (oracle.parent / "exposure.yaml").write_text(yaml.safe_dump([{"at": "2026-10-06", "by": "tester",
                                                                       "what": "shown to a model"}]),
                                                     encoding="utf-8")
    with pytest.raises(runner.Refused, match={"no_root": "AEW_EVAL_HIDDEN_ROOT", "changed": "not the preregistered",
                                              "exposed": "has been exposed"}[problem]):
        run(f, case, tmp_path, hidden_root=None if problem == "no_root" else secret)
    assert nothing_registered(tmp_path)


def test_an_exposed_case_still_runs_when_it_is_not_held_out(tmp_path):
    f, case, secret = setup(tmp_path)
    (secret / "cases" / "C1" / "exposure.yaml").write_text("- {at: '2026-10-06', by: t, what: shown}\n",
                                                           encoding="utf-8")
    assert run(f, case, tmp_path, hidden_root=secret)["outcome"]["score"]["passed"] is True


def test_the_models_tree_cannot_replace_the_scorer_or_its_result(tmp_path):
    """The scoring process imports only the standard library before the tree joins its path, and exits straight after
    printing: a planted json.py, an aew_eval package or an exit handler printing a fake result change nothing."""
    planted = [{"write": "json.py", "content": "raise SystemExit('planted json')\n"},
               {"write": "aew_eval/__init__.py", "content": "raise SystemExit('planted aew_eval')\n"},
               {"write": "calc.py", "content": "import atexit\natexit.register(lambda: print("
                "'{\"passed\": true, \"checks\": []}'))\ndef add(a, b):\n    return a - b\n"}]
    in_process = "def checks(tree):\n    import calc\n    yield 'add(2, 3) is 5', calc.add(2, 3) == 5, calc.add(2, 3)\n"
    secret = tmp_path / "private"
    oracle = make_oracle(secret, checks=in_process)  # the model's module is imported into the scoring process
    case = make_case(tmp_path / "case", hidden.content_sha256(oracle))
    record = run(plan_for(case, steps=planted), case, tmp_path, hidden_root=secret)
    score = record["outcome"]["score"]
    assert record["validity"]["status"] == "valid" and score["passed"] is False, score
    assert [c["name"] for c in score["checks"]] == ["add(2, 3) is 5"]


def test_an_oracle_changed_while_scoring_makes_the_run_invalid(tmp_path):
    tamper = CHECKS + '''
from pathlib import Path
Path(__file__).with_name("note.txt").write_text("written while scoring")
'''
    secret = tmp_path / "private"
    oracle = make_oracle(secret, checks=tamper)
    case = make_case(tmp_path / "case", hidden.content_sha256(oracle))
    record = run(plan_for(case), case, tmp_path, hidden_root=secret)
    assert record["validity"]["status"] == "invalid_measurement"
    assert "changed while it scored" in record["outcome"]["error"]


def test_a_check_that_raises_is_a_failed_check(tmp_path):
    secret = tmp_path / "private"
    oracle = make_oracle(secret, checks="def checks(tree):\n    yield 'first', True, ''\n    raise ValueError('x')\n")
    case = make_case(tmp_path / "case", hidden.content_sha256(oracle))
    score = run(plan_for(case), case, tmp_path, hidden_root=secret)["outcome"]["score"]
    assert score["passed"] is False and score["checks"][-1]["name"] == "checks raised"
    assert "ValueError" in score["checks"][-1]["detail"]


def test_a_case_with_an_oracle_takes_no_second_scorer(tmp_path):
    f, case, secret = setup(tmp_path)
    with pytest.raises(runner.Refused, match="second scorer"):
        run(f, case, tmp_path, hidden_root=secret, scorer=lambda tree: {"passed": True})
    assert nothing_registered(tmp_path)
