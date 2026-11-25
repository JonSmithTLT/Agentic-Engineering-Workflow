"""F19 offline verifier-disposition rehearsal (``eval/experiments/verifier-disposition``): both skill-exposure arms
receive the same candidate through the ordinary runner, each records the role projection it applied and the skill
exposure actually delivered, and the blinded grader grades the first disposition. A scripted verifier qualifies
delivery and grading only: its decisions ignore the skill, so they say nothing about whether the skill helps."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import runpy
import sys
from pathlib import Path

import pytest
import yaml

from aew import skills

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval"
EXPERIMENT = EVAL / "experiments" / "verifier-disposition"
sys.path.insert(0, str(EVAL))
from aew_eval import arms, fixture, prereg, runner  # noqa: E402

CASES = {case: EXPERIMENT / f"case-{case}.yaml" for case in ("VD-1", "VD-2", "VD-3")}
SKILL = "acceptance-verification"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path):
    """A module from its file, private to this test: nothing enters ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(f"vd_rehearsal_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def experiment():
    """The experiment's public adapter, scripted verifier and evaluator-side grader, loaded from their files."""
    return (load(EXPERIMENT / "disposition_adapter.py"), load(EXPERIMENT / "evaluator" / "disposition_grader.py"),
            load(EXPERIMENT / "scripted_verifier.py"))


class VerifierArm(arms.ScriptedArm):
    """One fresh scripted verifier per registered cell: its arm's role projection applied, its skills delivered by
    AEW's own copy, then the verifier's checks and record."""

    def __init__(self, adapter, verifier, tasks):
        self.adapter, self.verifier, self.tasks = adapter, verifier, tasks

    def run(self, repo, config, *, deadline_s, task=None):
        self.tasks.append(task)
        revision = fixture.git(repo, "rev-parse", "HEAD")  # still the runner's own repository: nothing has run in it
        applied = self.adapter.projection(config["skills"])
        folder = repo.parent / "harness" / "skills"
        delivered = skills.deliver(applied["skills"], folder)
        exposure = {**delivered, "loaded": []}  # a scripted verifier never calls the skill tool
        probe = EXPERIMENT / config["probe"]
        assert digest(probe.read_bytes().replace(b"\r\n", b"\n")) == config["probe_sha256"]
        out = self.verifier.verify(repo, probe, repo.parent / "scratch", revision)
        result = super().run(repo, config, deadline_s=deadline_s, task=task)
        result.harness.update({"name": "scripted-verifier", **out, "exposure": exposure,
                               "projection": {k: applied[k] for k in ("card", "card_sha256", "applied_sha256")},
                               "skill_files": sorted(p.relative_to(folder).as_posix()
                                                     for p in folder.rglob("*") if p.is_file())
                               if folder.is_dir() else []})
        return result


def test_the_calibration_reproduces_its_committed_qualification(monkeypatch):
    """The expected decisions agree with the M3 T5 hidden checks, and the grader rejects every wrong control."""
    monkeypatch.setattr(sys, "path", list(sys.path))  # calibrate.py puts the experiment on the path
    found = runpy.run_path(str(EXPERIMENT / "evaluator" / "calibrate.py"))["calibrate"]()
    committed = json.loads((EXPERIMENT / "evaluator" / "qualification.json").read_text(encoding="utf-8"))
    assert found == committed
    grades = {name: control["grade"] for name, control in found["controls"].items()}
    assert grades["false-accept"] == "false_accept" and grades["false-rework"] == "false_rework"
    assert found["controls"]["fabricated-accept"]["unsupported_claims"] == ["check_not_observed"] * 2
    assert all(truth["project_tests"] for truth in found["truth"].values())  # every candidate passes its own tests


def test_the_verifiers_repository_names_no_case_and_no_expected_decision(tmp_path):
    """Built exactly as the runner builds a cell, a candidate's repository holds no descriptive case name, no word of
    the expected decisions and no other case's id; its own neutral id appears only in the instrument's commit subject
    (PR #534 review, finding 1)."""
    expected = yaml.safe_load((EXPERIMENT / "evaluator" / "expected.yaml").read_text(encoding="utf-8"))
    rows = expected["cases"].values()
    forbidden = ({"clean", "repair", "t5", "disposition", "violated", "expected"}
                 | {row["disposition"] for row in rows} | {g.lower() for row in rows for g in row["violated"]})
    for case_id, path in CASES.items():
        repo = tmp_path / case_id
        fixture.build(fixture.snapshot(fixture.load(path)), repo, seeded=True)
        log = fixture.git(repo, "log", "--format=%B")
        assert log == f"{case_id}: starting point (seeded)"
        files = "\n".join(data.decode("utf-8", "replace") for data in fixture.files_of(repo).files.values())
        words = set(re.findall(r"[a-z0-9]+", (files + "\n" + log).lower()))
        assert not words & forbidden, (case_id, sorted(words & forbidden))
        assert not any(other in files + log for other in CASES if other != case_id)
        assert case_id not in files


def test_the_case_task_is_the_m3_t5_ticket(monkeypatch):
    monkeypatch.syspath_prepend(str(EVAL / "m3" / "dogfood"))
    import dogfood

    tasks = {fixture.load(path).manifest["task"] for path in CASES.values()}
    task, = tasks  # every case asks the same question of a different candidate
    assert all(goal in task for goal in dogfood.T5_TICKET["goals"])
    assert dogfood.T5_TICKET["contract"] in task and dogfood.T5_REPORT["claim"] in task


def test_both_arms_see_the_same_candidate_with_their_own_exposure_and_are_graded_blind(experiment, tmp_path,
                                                                                       monkeypatch):
    adapter, grader, verifier = experiment
    plan = prereg.load(EXPERIMENT / "plan.yaml")
    plan["cases"] = []
    for case_id, path in CASES.items():
        case = fixture.load(path)
        plan["cases"].append({"id": case_id, "family": case.manifest["family"], "sha256": fixture.case_sha256(case),
                              "hidden_sha256": None, "control_of": None})
    frozen = prereg.freeze(plan, by="offline rehearsal")
    tasks: list = []
    monkeypatch.setitem(arms.ARMS, "scripted", VerifierArm(adapter, verifier, tasks))
    records = []
    for n, cell in enumerate(frozen["assignment"]["order"], 1):
        # Neutral run names: the run id the grader sees never names the arm.
        records.append(runner.run_cell(frozen, ledger_dir=tmp_path / "ledger", cell=cell["cell"], cases=CASES,
                                       work=tmp_path / "cells", run_name=f"r{n}", defer_scoring=True,
                                       deadline_s=120))
    assert len(records) == 6 and len(set(tasks)) == 1
    for record in records:
        assert record["validity"]["status"] == "valid", record["outcome"]
        assert record["outcome"]["changed_paths"] == []  # the verifier never touched the candidate
        assert record["outcome"]["safety"]["checkout_untouched"]
    by_case: dict = {}
    for record in records:
        by_case.setdefault(record["case"]["id"], {})[record["arm"]["id"]] = record
    expected = grader.load_expected()
    manifest_sha = skills.entries()[SKILL]["sha256"]
    offered = sorted(adapter.projection([])["skills"]["exposed"])  # the verifier card's own offer, derived
    for case_id, pair in by_case.items():
        withheld, exposed = pair["inaccessible"], pair["exposed"]
        # The same candidate artifact, at the same bytes, to both arms.
        assert withheld["outcome"]["scoring"]["export_sha256"] == exposed["outcome"]["scoring"]["export_sha256"]
        assert withheld["case"]["sha256"] == exposed["case"]["sha256"]
        # The projections differ in the skill list alone, and the delivery matches each arm.
        p_w, p_e = withheld["harness"]["projection"], exposed["harness"]["projection"]
        assert p_w["card_sha256"] == p_e["card_sha256"] and p_w["applied_sha256"] != p_e["applied_sha256"]
        # Withheld means acceptance-verification only: what the card offers (`optional_skills`, E136) both arms get.
        assert SKILL not in offered and sorted(withheld["harness"]["exposure"]["exposed"]) == offered
        assert sorted(exposed["harness"]["exposure"]["exposed"]) == sorted([SKILL, *offered])
        assert {d["name"]: d["sha256"] for d in exposed["harness"]["exposure"]["delivered"]}[SKILL] == manifest_sha
        assert sorted(set(exposed["harness"]["skill_files"]) - set(withheld["harness"]["skill_files"])) == [
            f"{SKILL}/SKILL.md"]
        assert not any(f.startswith(f"{SKILL}/") for f in withheld["harness"]["skill_files"])
        grades = []
        for record in (withheld, exposed):
            observation = adapter.from_run(record, frozen)
            assert observation["validity"]["status"] == "valid"
            assert observation["exposure"]["loaded"] == []
            graded = grader.grade(grader.blind(observation), expected)
            assert graded["disposition"] == expected["cases"][case_id]["disposition"]
            assert graded["unsupported_claims"] == [] and graded["authority_violations"] == 0
            grades.append(graded["grade"])
        assert grades[0] == grades[1] == ("correct_accept" if case_id == "VD-1" else "justified_rework")
