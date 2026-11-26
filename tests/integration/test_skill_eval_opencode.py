"""The skill evaluation's model arm end to end (register E135; ``eval/skill_eval``), through F19's raw arm, the real
headless session and the fake OpenCode server. No provider is called.

Both arms of a pair run the same case on the same pinned model. The candidate arm's server is configured with the one
``skills`` entry, its run's own copy of the exposed skills at their manifest hashes, and its session's rules allow
those ids; the baseline arm's session denies every skill, and no copy of the candidate exists in its run. What the
scripted "model" loaded reaches the run record through the adapter's own reading, and the report pairs it with the
case's expected activation. The fake applies no skill rules, so nothing here shows what a real OpenCode lists.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import fake_opencode
import pytest
import yaml

from aew import skills
from aew.harness.opencode import projection
from aew.harness.opencode.capabilities import TESTED_VERSIONS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import prereg, raw, runner  # noqa: E402
from skill_eval import cases, plan, report  # noqa: E402
from skill_eval import run as lane_run  # noqa: E402

CANDIDATE, OTHER = sorted(skills.shipped())[:2]
EFFECTIVE = [{"provider": "fakeprov", "model": "fake-model", "effort": "high"}]
FIELDS = [{"field": "tool.name", "transform": "none"}]
KEY_VARIABLE = "FAKEPROV_TEST_KEY"
TOLD = "- Told only to the candidate arm."
SOURCE = {"format": "aew-skill-cases/v1", "skill": CANDIDATE, "cases": [
    {"id": "SRC-1", "split": "development", "purpose": "evaluator only",
     "worker": {"task": "Say what calc.py's add() returns.", "context": "Fixture revision v1.",
                "artifacts": {"calc.py": "def add(a, b):\n    return a - b\n"}, "capabilities": ["Read files."],
                "constraints": ["Do not modify calc.py."]},
     "oracle": {"activation": "use", "required_findings": ["it subtracts"]}}]}


def pins(*names: str) -> dict[str, str]:
    return {name: skills.entries()[name]["sha256"] for name in names}


@pytest.fixture
def lane(tmp_path, monkeypatch):
    """The fake OpenCode as the pinned harness binary, one materialized case and a frozen paired preregistration."""
    scripts = tmp_path / "bin" / "scripts"
    scripts.mkdir(parents=True)
    launcher = fake_opencode.write_launcher(tmp_path / "bin", scripts)
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(launcher))
    monkeypatch.setenv(KEY_VARIABLE, "sk-test-provider-value-0123456789")
    source = tmp_path / "cases.yaml"
    source.write_text(yaml.safe_dump(SOURCE, sort_keys=False), encoding="utf-8")
    key = cases.materialize(source, tmp_path / "cases", tmp_path / "evaluator", answer_file="ANSWER.md")
    shared = {"role": "worker", "model": "fakeprov/fake-model#high", "steps": 5, "cap_usd": 0.5,
              "provider_env": [KEY_VARIABLE], "contain": False,
              "profile": {"id": "lb-demo", "qualification_state": "unqualified",
                          "effective_profile": {"context.orientation": None, "tools.presentation": None}},
              "harness": {"name": "opencode", "version": TESTED_VERSIONS[0],
                          "artifact_sha256": {raw.host_platform(): raw._sha256_file(launcher)}},  # noqa: SLF001
              "session_db": {"retain": True, "retention_days": 30, "fields": FIELDS}}
    draft = {
        "schema": "aew/eval-prereg/v1", "experiment": "skill-eval-fake", "purpose": "qualification",
        "question": "Do the two arms differ in the delivered skill alone?",
        "arms": [{"id": "baseline", "kind": "raw", "description": "the candidate absent",
                  "config": {**shared, "skills": [], "optional_skills": [OTHER], "skill_sha256": pins(OTHER)}},
                 {"id": "candidate", "kind": "raw", "description": "the candidate exposed",
                  "config": {**shared, "skills": [], "optional_skills": [OTHER, CANDIDATE],
                             "skill_sha256": pins(OTHER, CANDIDATE), "told": TOLD}}],
        "cases": key["preregistration_cases"],
        "profiles": {"roles": {"worker": "fakeprov/fake-model#high"}, "budget_usd": 2.0},
        "runs_per_cell": 1, "assignment": {"method": "randomized_blocked", "seed": 3},
        "primary_measure": "pairs completed", "metrics": [{"name": "skill-eval-report", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 0, "allowed_for": []},
                           "missing_result_policy": "listed, never dropped"},
        "stopping_rule": "one attempt per cell", "held_out": [],
        "scoring": {"hidden_channel": "the evaluator's directory", "who_scores": "operator",
                    "blinding": "arm_hidden", "adjudication_policy": "none: a fake model"},
        "exposure_policy": "a synthetic case", "amendment_policy": "a change is a new id",
    }
    return {"scripts": scripts, "draft": draft, "key": key, "lane": tmp_path / "lane",
            "manifests": cases.manifests(tmp_path / "cases"), "evaluator": tmp_path / "evaluator"}


def walk(lane: dict, frozen: dict, steps: dict[str, list]) -> list[dict]:
    """The schedule, one cell at a time, the fake "model" scripted for the arm whose cell is next."""
    outs = []
    for entry in frozen["assignment"]["order"]:
        (lane["scripts"] / "default.json").write_text(
            json.dumps({"steps": steps[entry["arm"]], "effective": EFFECTIVE}), encoding="utf-8")
        outs.append(lane_run.run(frozen, cases=lane["manifests"], lane=lane["lane"], evaluator=[lane["evaluator"]],
                                 deadline_s=120, limit=1))
    return outs


def started(lane: dict, run_id: str) -> tuple[dict, dict, Path]:
    """What the run's fake server was started with, its session as the server holds it, and the run's scratch."""
    scratch = lane["lane"] / "work" / run_id.split("/", 1)[1]
    config = json.loads((scratch / "harness" / "harness" / "fake-server.json").read_text(encoding="utf-8"))["config"]
    db = fake_opencode.read_db(scratch / "harness" / "harness" / "xdg-data" / "opencode" / "fake-db.json")
    [session] = db.values()
    return config, session, scratch


ANSWER = {"do": "write", "files": {"ANSWER.md": "add() subtracts.\n"}}


def test_the_two_arms_differ_in_the_delivered_skill_alone_and_what_was_loaded_is_recorded(lane):
    frozen = prereg.freeze(lane["draft"], by="integration test")
    outs = walk(lane, frozen, {"baseline": [{"do": "skill", "id": CANDIDATE}, ANSWER],  # an id it was not given
                               "candidate": [{"do": "skill", "id": CANDIDATE}, ANSWER]})
    assert [o["stopped"] for o in outs] == ["limit", "done"] and all(len(o["ran"]) == 1 for o in outs)
    assert all(o["ran"][0]["validity"]["status"] == "valid" for o in outs), outs
    [pair] = report.pairs(frozen, lane["lane"] / "ledger")
    assert pair["complete"], pair
    base_config, base_session, base_scratch = started(lane, pair["baseline"]["run_id"])
    cand_config, cand_session, cand_scratch = started(lane, pair["candidate"]["run_id"])
    # The configurations differ in the one `skills` entry, each run's own copy, and in nothing else.
    at = projection.skills_at(os.path.realpath(cand_scratch), os.sep)
    assert cand_config.pop("skills") == [at.folder]
    assert base_config.pop("skills") == [projection.skills_at(os.path.realpath(base_scratch), os.sep).folder]
    assert base_config == cand_config
    assert sorted(p.name for p in Path(at.folder).iterdir()) == sorted([CANDIDATE, OTHER])
    assert not (base_scratch / projection.SKILLS_DIR / CANDIDATE).exists()
    assert (base_scratch / projection.SKILLS_DIR / OTHER / skills.SKILL_FILE).is_file()
    assert skills.verify(skills.plan([], [OTHER, CANDIDATE]), Path(at.folder))  # the manifest's bytes, re-hashed
    # The session's rules are the projection's own: every skill denied, then the arm's exposed ids allowed.
    assert cand_session["info"]["permissions"] == projection.lead_skill_rules(
        sorted([CANDIDATE, OTHER]), at, contained=True)
    allowed = [r["resource"] for r in base_session["info"]["permissions"]
               if r["action"] == "skill" and r["effect"] == "allow"]
    assert allowed == [OTHER] and base_session["info"]["permissions"][0] == projection.rule("skill", "deny")
    # Only the candidate arm was told, verbatim, after the case's task.
    task = yaml.safe_load(lane["manifests"]["K01"].read_text(encoding="utf-8"))["task"]
    assert json.dumps(task.rstrip("\n") + "\n\n" + TOLD + "\n")[1:-1] in json.dumps(cand_session["messages"])
    assert TOLD not in json.dumps(base_session) and json.dumps(task)[1:-1] in json.dumps(base_session["messages"])
    # What was loaded is the adapter's reading: an id the run exposed is named, any other call is only counted.
    assert pair["candidate"]["loaded"] == {CANDIDATE: 1} and pair["candidate"]["skill_other"] == 0
    assert pair["baseline"]["loaded"] == {} and pair["baseline"]["skill_other"] == 1
    assert pair["candidate"]["candidate_loaded"] is True and pair["baseline"]["candidate_loaded"] is False
    for side in ("baseline", "candidate"):
        assert pair[side]["usage"]["first_step_input_tokens"] > 0 and pair[side]["usage"]["steps"] >= 2
    out = report.report(frozen, lane["lane"], key=lane["key"])
    assert out["selection"]["candidate_runs_by_expected_activation"] == {
        "use": {"loaded": 1, "not_loaded": 0, "unknown": 0}}
    assert out["selection"]["skill_calls_that_loaded_nothing"] == {"baseline": 1, "candidate": 0}
    assert out["cost"]["candidate_minus_baseline"]["first_step_input_tokens"]["n"] == 1
    assert out["pair"]["kind"] == "raw" and out["pilot"] is True and out["pair"]["told_differs"] is True
    assert out["evaluator_material_hidden"] is False  # not contained: the arm could read the key
    [first, second] = report.packets(frozen, lane["lane"] / "ledger", lane["manifests"])
    assert (Path(first["export"]) / "ANSWER.md").read_text(encoding="utf-8") == "add() subtracts.\n"
    assert first["changed_paths"] == second["changed_paths"] == ["ANSWER.md"]


def test_a_model_that_needs_no_key_is_refused_before_anything_is_registered(lane):
    """Register E135's note of 2026-11-06: the paired runs use a keyed, paid model, never a free one."""
    for arm in lane["draft"]["arms"]:
        arm["config"]["provider_env"] = []
    frozen = prereg.freeze(lane["draft"], by="integration test")
    assert plan.shape(frozen)["kind"] == "raw"
    with pytest.raises(runner.Refused, match="keyed, paid model"):
        lane_run.run(frozen, cases=lane["manifests"], lane=lane["lane"], evaluator=[lane["evaluator"]], limit=1)
    assert not (lane["lane"] / "ledger" / "attempts.jsonl").exists()


def test_a_skill_that_fails_to_arrive_on_the_model_arm_is_charged_nothing_and_stops_the_walk(lane, monkeypatch):
    """The arm's configuration is built before the run counts as launched, so a delivery that fails is an arm error
    with nothing started and nothing charged. Every later cell would fail the same way, so the walk stops there and
    the rest of the schedule is not spent (review of #607, 2 and 7)."""
    real = skills.deliver
    monkeypatch.setattr(skills, "deliver", lambda planned, root: {
        **real(planned, root), "exposed": [], "reasons": {name: skills.COPY_FAILED for name in planned["exposed"]}})
    frozen = prereg.freeze(lane["draft"], by="integration test")
    (lane["scripts"] / "default.json").write_text(json.dumps({"steps": [ANSWER], "effective": EFFECTIVE}),
                                                  encoding="utf-8")
    out = lane_run.run(frozen, cases=lane["manifests"], lane=lane["lane"], evaluator=[lane["evaluator"]],
                       deadline_s=120)
    assert out["stopped"] == "lane_error" and out["reason_code"] == "ARM_ERROR" and len(out["ran"]) == 1
    assert out["ran"][0]["charged_usd"] == 0.0 and out["spent_usd"] == 0.0
    [first] = [json.loads(p.read_text(encoding="utf-8")) for p in (lane["lane"] / "ledger" / "runs").glob("*.json")]
    assert first["outcome"]["launched"] is False and "not delivered" in first["outcome"]["arm_error"]
    assert not list((lane["lane"] / "work").glob("*/harness/harness/fake-server.json"))  # no server ever started


def test_the_raw_arm_alone_is_configured_as_before(lane, tmp_path):
    """The two hooks the skill arm extends leave F19's own raw arm as it was: no ``skills`` entry, no session rules."""
    config = {k: v for k, v in lane["draft"]["arms"][0]["config"].items()
              if k not in ("skills", "optional_skills", "skill_sha256")}
    draft = {**lane["draft"], "experiment": "raw-alone", "assignment": {"method": "fixed", "seed": 1},
             "arms": [{"id": "raw", "kind": "raw", "description": "harness alone", "config": config}]}
    frozen = prereg.freeze(draft, by="integration test")
    (lane["scripts"] / "default.json").write_text(json.dumps({"steps": [ANSWER], "effective": EFFECTIVE}),
                                                  encoding="utf-8")
    record = runner.run_cell(frozen, ledger_dir=tmp_path / "raw-ledger", cell=frozen["assignment"]["order"][0]["cell"],
                             cases=lane["manifests"], work=tmp_path / "raw-work", run_name="r1", deadline_s=120)
    assert record["validity"]["status"] == "valid", record["outcome"]
    assert "exposure" not in record["harness"] and "first_step_input_tokens" not in record["harness"]
    state = tmp_path / "raw-work" / "r1" / "harness" / "harness"
    assert "skills" not in json.loads((state / "fake-server.json").read_text(encoding="utf-8"))["config"]
    [session] = fake_opencode.read_db(state / "xdg-data" / "opencode" / "fake-db.json").values()
    assert session["info"]["permissions"] == []
