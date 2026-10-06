"""The evaluation instrument's second slice (register F19; the evaluation component design v0.2, §2 and §8 step 2):
fixtures built from a case manifest with a checkout-independent hash, and the runner that runs one preregistered
cell: a changed input is refused before anything is counted, the attempt is registered before the arm runs, and the
result is finalized once, whatever the arm did.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, prereg, runner  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FIX = {"write": "calc.py", "content": "def add(a, b):\n    return a + b\n"}


def make_case(root: Path, *, cid: str = "C1", overlay: bool = True, seeded: bool = False) -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    (root / "base" / "README.md").write_text("# calc\n", encoding="utf-8", newline="\n")
    fx: dict = {"base": "base"}
    if overlay:
        (root / "overlay").mkdir()
        (root / "overlay" / "NOTES.md").write_text("the bug: add subtracts\n", encoding="utf-8", newline="\n")
        fx["overlay"] = "overlay"
    if seeded:
        (root / "seeded").mkdir()
        (root / "seeded" / "calc.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8",
                                                 newline="\n")
        fx["seeded"] = "seeded"
    manifest = {"schema": "aew/eval-case/v1", "id": cid, "family": "demo", "fixture": fx, "hidden_sha256": None,
                "control_of": None}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def plan_for(case_path: Path, *, steps: list | None = None, kind: str = "scripted", **over) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "demo", "question": "Does the reference fix the bug?",
        "arms": [{"id": "ref", "kind": kind, "description": "the reference edit",
                  "config": {"steps": [FIX] if steps is None else steps}}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": {"lead": "none"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "fixed", "metrics": [{"name": "fixed", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement", "runner_lost"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id",
    }
    record.update(over)
    return prereg.freeze(record, by="tester")


def run(f: dict, case_path: Path, tmp_path: Path, name: str = "r1", **kw) -> dict:
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name=name, **kw)


# ---------------------------------------------------------------------------------------------- fixtures

def test_a_case_hash_covers_the_manifest_and_every_tree_and_ignores_line_ends(tmp_path):
    path = make_case(tmp_path / "c")
    case = fixture.load(path)
    first = fixture.case_sha256(case)
    crlf = tmp_path / "c" / "base" / "calc.py"
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout
    assert fixture.case_sha256(case) == first
    (tmp_path / "c" / "overlay" / "NOTES.md").write_text("changed\n", encoding="utf-8")
    assert fixture.case_sha256(case) != first
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["family"] = "other"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    assert fixture.case_sha256(fixture.load(path)) not in (first,)


def test_a_fixture_builds_a_fresh_repository_with_lf_and_one_commit(tmp_path):
    path = make_case(tmp_path / "c", seeded=True)
    crlf = tmp_path / "c" / "base" / "calc.py"
    crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
    case = fixture.load(path)
    repo = tmp_path / "repo"
    base = fixture.build(case, repo)
    assert b"\r\n" not in (repo / "calc.py").read_bytes() and (repo / "NOTES.md").is_file()
    assert fixture.changed_paths(repo, base) == []
    with pytest.raises(Invalid, match="fresh directory"):
        fixture.build(case, repo)
    seeded = tmp_path / "seeded"
    fixture.build(case, seeded, seeded=True)
    assert "b + a" in (seeded / "calc.py").read_text(encoding="utf-8")


def test_a_case_whose_trees_are_missing_or_outside_it_is_refused(tmp_path):
    path = make_case(tmp_path / "c", overlay=False)
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "x.py").write_text("x = 1\n", encoding="utf-8")
    for bad, match in (({"base": "nowhere"}, "not a directory"), ({"base": "../elsewhere"}, "outside")):
        (tmp_path / "c" / "case.yaml").write_text(yaml.safe_dump({**manifest, "fixture": bad}), encoding="utf-8")
        with pytest.raises(Invalid, match=match):
            fixture.load(tmp_path / "c" / "case.yaml")


# ---------------------------------------------------------------------------------------------- the runner

def test_a_scripted_cell_runs_end_to_end_and_is_finalized_once(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    record = run(f, case_path, tmp_path, scorer=lambda tree: {"fixed": "a + b" in (tree / "calc.py").read_text()})
    validate("aew/eval-run/v1", record)
    assert record["validity"] == {"status": "valid", "reason_code": None}
    assert record["outcome"]["changed_paths"] == ["calc.py"] and record["outcome"]["score"] == {"fixed": True}
    assert record["environment"]["checkout_untouched"] in (True, None)
    ledger = AttemptLedger(tmp_path / "ledger", f)
    assert ledger.status() == {"demo/r1": "valid"} and ledger.verify() == []
    with pytest.raises(Invalid, match="already has attempt"):  # one cell, one counted attempt
        run(f, case_path, tmp_path, name="r2")


def test_a_changed_fixture_or_an_unbuilt_arm_is_refused_before_anything_is_counted(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    (tmp_path / "case" / "base" / "calc.py").write_text("changed after freezing\n", encoding="utf-8")
    with pytest.raises(prereg.Mismatch, match="fixture of C1 changed"):
        run(f, case_path, tmp_path)
    assert not (tmp_path / "ledger" / "attempts.jsonl").exists()
    case2 = make_case(tmp_path / "case2")
    f2 = plan_for(case2, kind="aew", steps=[])
    with pytest.raises(Invalid, match="not built in the shared runner yet"):
        run(f2, case2, tmp_path / "two")
    assert not (tmp_path / "two" / "ledger" / "attempts.jsonl").exists()


def test_an_arm_that_fails_is_counted_as_an_invalid_measurement_and_may_be_retried(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, steps=[{"write": "../escape.txt", "content": "x"}])
    record = run(f, case_path, tmp_path)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "RUNNER_ERROR:Invalid"}
    assert "leaves the repository" in record["outcome"]["error"] and not (tmp_path / "work" / "escape.txt").exists()
    retry = run(f, case_path, tmp_path, name="r1b", retry_of="demo/r1")
    assert retry["validity"]["status"] == "invalid_measurement"
    assert AttemptLedger(tmp_path / "ledger", f).attempts()["demo/r1"].retries == ["demo/r1b"]


def test_a_runner_killed_while_the_arm_runs_leaves_a_visible_attempt(tmp_path, monkeypatch):
    """The attempt is registered before the arm runs: a runner that dies there leaves runner_lost, never nothing."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)

    class Dies:
        kind = "scripted"

        def run(self, repo, config, *, deadline_s):
            raise KeyboardInterrupt  # not an Exception: the runner itself stops here, as a kill would

    monkeypatch.setitem(arms.ARMS, "scripted", Dies())
    with pytest.raises(KeyboardInterrupt):
        run(f, case_path, tmp_path)
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"demo/r1": "runner_lost"}


def test_the_command_line_runs_a_cell_and_refuses_a_bad_one(tmp_path):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path)
    frozen_path = tmp_path / "prereg.yaml"
    prereg.dump(f, frozen_path)
    base = [sys.executable, "-m", "aew_eval.runner", str(frozen_path), "--case", f"C1={case_path}",
            "--ledger", str(tmp_path / "ledger"), "--work", str(tmp_path / "work")]
    env = {**__import__("os").environ, "PYTHONPATH": str(ROOT / "eval")}
    ok = subprocess.run([*base, "--cell", f["assignment"]["order"][0]["cell"], "--name", "cli1"], env=env,
                        capture_output=True, text=True, timeout=120, creationflags=NO_WINDOW)
    assert ok.returncode == 0 and "demo/cli1: valid" in ok.stdout, ok.stderr
    bad = subprocess.run([*base, "--cell", "C9/ref/1", "--name", "cli2"], env=env, capture_output=True, text=True,
                         timeout=120, creationflags=NO_WINDOW)
    assert bad.returncode == 1 and "not a cell" in bad.stderr
    lines = [json.loads(x) for x in (tmp_path / "ledger" / "attempts.jsonl").read_text().splitlines()]
    assert [x["run_id"] for x in lines] == ["demo/cli1", "demo/cli1"]  # registered, finalized; nothing for cli2
