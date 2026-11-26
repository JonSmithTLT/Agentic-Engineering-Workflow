"""The skill evaluation's runner (register E135; ``eval/skill_eval``), offline: no model, no provider, no harness.

A candidate's public cases become F19 cases that hold nothing of the oracle; a preregistration is held to the paired
shape before anything is registered; the schedule runs pair by pair under the budget and resumes from the ledger; and
the report takes cost, selection and benefit from the ledger's records, counting an unknown as missing. The scripted
arm qualifies the instrument only: nothing here says anything about a skill. The model arm is exercised against the
fake OpenCode server in ``tests/integration/test_skill_eval_opencode.py``.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
import yaml

from aew import skills
from aew.harness.opencode import projection

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))
from aew_eval import arms as f19_arms  # noqa: E402
from aew_eval import fixture, prereg, raw  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid  # noqa: E402
from skill_eval import __main__ as cli  # noqa: E402
from skill_eval import arms, cases, plan, report  # noqa: E402
from skill_eval import run as lane_run  # noqa: E402

CANDIDATE, OTHER, THIRD = sorted(skills.shipped())[:3]  # any three shipped skills: the runner knows none by name
SECRET = "the-oracle-says-zebra"
SOURCE = {
    "format": "aew-skill-cases/v1", "skill": CANDIDATE,
    "cases": [
        {"id": f"SRC-{n}", "split": "development", "purpose": f"{SECRET} purpose {n}",
         "worker": {"task": f"Review part{n}.py.", "context": f"Fixture revision v{n}.",
                    "artifacts": {f"src/part{n}.py": f"VALUE = {n}\n"}, "capabilities": ["Read supplied files."],
                    "constraints": ["Do not modify supplied files."]},
         "oracle": {"activation": activation, "required_findings": [f"{SECRET} finding {n}"]}}
        for n, activation in enumerate(("use", "skip", "abstain"), 1)],
}


def pins(*names: str) -> dict[str, str]:
    return {name: skills.entries()[name]["sha256"] for name in names}


def exposure(mode: str | None, *, others: tuple[str, ...] = ()) -> dict:
    """An arm's exposure keys: the candidate under ``skills`` (procedure), ``optional_skills`` (selection) or absent."""
    listed = {"skills": [CANDIDATE] if mode == "procedure" else [],
              "optional_skills": [*others, *([CANDIDATE] if mode == "selection" else [])]}
    return {**listed, "skill_sha256": pins(*listed["skills"], *listed["optional_skills"])}


def make_plan(cases_block: list, *, mode: str = "selection", others: tuple[str, ...] = (OTHER,), cap: float = 0.0,
              budget: float = 0.0, runs_per_cell: int = 1, experiment: str = "skill-eval-offline") -> dict:
    shared = {"steps": [], **({"cap_usd": cap} if cap else {})}
    return {
        "schema": "aew/eval-prereg/v1", "experiment": experiment, "purpose": "qualification",
        "question": "Does the instrument deliver each arm's exposure and pair its runs?",
        "arms": [{"id": "baseline", "kind": "scripted", "description": "the candidate absent",
                  "config": {**shared, **exposure(None, others=others)}},
                 {"id": "candidate", "kind": "scripted", "description": "the candidate exposed",
                  "config": {**shared, **exposure(mode, others=others)}}],
        "cases": cases_block, "profiles": {"roles": {"worker": "none"}, "budget_usd": budget},
        "runs_per_cell": runs_per_cell, "assignment": {"method": "randomized_blocked", "seed": 7},
        "primary_measure": "pairs completed", "metrics": [{"name": "skill-eval-report", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 0, "allowed_for": []},
                           "missing_result_policy": "listed, never dropped"},
        "stopping_rule": "one attempt per cell", "held_out": [],
        "scoring": {"hidden_channel": "the evaluator's directory", "who_scores": "operator",
                    "blinding": "arm_hidden", "adjudication_policy": "none: a dry run"},
        "exposure_policy": "synthetic cases", "amendment_policy": "a change is a new id",
    }


@pytest.fixture
def lane(tmp_path):
    """Materialized synthetic cases, their key, and where a lane's ledger and scratch go."""
    source = tmp_path / "source" / "cases.yaml"
    source.parent.mkdir()
    source.write_text(yaml.safe_dump(SOURCE, sort_keys=False), encoding="utf-8")
    key = cases.materialize(source, tmp_path / "cases", tmp_path / "evaluator", answer_file="ANSWER.md")
    return {"source": source, "cases": tmp_path / "cases", "evaluator": tmp_path / "evaluator", "key": key,
            "lane": tmp_path / "lane", "manifests": cases.manifests(tmp_path / "cases")}


def freeze(lane: dict, **kw) -> dict:
    return prereg.freeze(make_plan(lane["key"]["preregistration_cases"], **kw), by="offline test")


def refrozen(frozen: dict, change) -> dict:
    """``frozen``'s plan with ``change`` applied, frozen again: how a differently written preregistration reads."""
    draft = {k: copy.deepcopy(v) for k, v in frozen.items() if k not in prereg.FROZEN_FIELDS}
    del draft["assignment"]["order"]
    change(draft)
    return prereg.freeze(draft, by="offline test")


# ---------------------------------------------------------------------------------------------- cases


def test_a_materialized_case_holds_the_worker_fields_and_nothing_of_the_oracle(lane, tmp_path):
    key = lane["key"]
    assert sorted(lane["manifests"]) == ["K01", "K02", "K03"] == sorted(key["cases"])
    everything = "\n".join(p.read_text(encoding="utf-8") for p in lane["cases"].rglob("*") if p.is_file())
    assert SECRET not in everything and "SRC-" not in everything and "development" not in everything
    assert not any(word in everything for word in ("purpose", "oracle", "abstain"))
    case = fixture.load(lane["manifests"]["K02"])
    task = case.manifest["task"]
    for given in ("Review part2.py.", "Context:\nFixture revision v2.", "Capabilities:\n- Read supplied files.",
                  "Constraints:\n- Do not modify supplied files.", "`ANSWER.md`"):
        assert given in task
    assert (lane["cases"] / "K02" / "base" / "src" / "part2.py").read_bytes() == b"VALUE = 2\n"
    # The evaluator's side is whole, and apart: the neutral id's own id, its expected activation, its oracle's hash.
    assert key["cases"]["K02"]["id"] == "SRC-2" and key["cases"]["K03"]["activation"] == "abstain"
    assert cases.load_key(lane["evaluator"]) == key and key["skill"] == CANDIDATE
    # Built as the runner builds it, the repository's one commit names the neutral id alone.
    fixture.build(fixture.snapshot(case), tmp_path / "built")
    assert fixture.git(tmp_path / "built", "log", "--format=%B") == "K02: starting point"


def test_a_subset_keeps_each_cases_neutral_id_and_the_preregistered_hash_is_f19s(lane, tmp_path):
    key = cases.materialize(lane["source"], tmp_path / "c2", tmp_path / "e2", only=["SRC-3"], answer_file="ANSWER.md")
    [entry] = key["preregistration_cases"]
    assert entry["id"] == "K03"
    assert entry["sha256"] == fixture.case_sha256(fixture.load(tmp_path / "c2" / "K03" / "case.yaml"))
    assert entry == next(c for c in lane["key"]["preregistration_cases"] if c["id"] == "K03")


@pytest.mark.parametrize("problem", ["inside", "exists", "unknown", "collides", "no_artifacts", "not_the_notation"])
def test_materialize_refuses_what_would_mix_the_two_sides_or_cannot_be_built(lane, tmp_path, problem):
    source, out, evaluator, kw = lane["source"], tmp_path / "c2", tmp_path / "e2", {}
    if problem == "inside":
        evaluator = out / "evaluator"
    elif problem == "exists":
        out = lane["cases"]
    elif problem == "unknown":
        kw["only"] = ["SRC-9"]
    elif problem == "collides":
        kw["answer_file"] = "ANSWER.md"
        changed = copy.deepcopy(SOURCE)
        changed["cases"][0]["worker"]["artifacts"]["answer.md"] = "taken\n"
        source.write_text(yaml.safe_dump(changed), encoding="utf-8")
    elif problem == "no_artifacts":
        changed = copy.deepcopy(SOURCE)
        changed["cases"][0]["worker"]["artifacts"] = {}
        source.write_text(yaml.safe_dump(changed), encoding="utf-8")
    else:
        source.write_text(yaml.safe_dump({**SOURCE, "format": "something-else"}), encoding="utf-8")
    with pytest.raises(Invalid):
        cases.materialize(source, out, evaluator, **kw)


def test_every_public_candidates_cases_materialize_as_f19_cases(tmp_path):
    """The cases the row's skills come with are in the notation the runner reads, each buildable by F19's fixture."""
    sources = sorted((ROOT / "docs" / "skills" / "candidates").glob("*/evals/cases.yaml"))
    assert len(sources) >= 14
    for source in sources:
        data = cases.read(source)
        buildable = [c["id"] for c in data["cases"] if c["worker"].get("artifacts")]
        name = source.parents[1].name
        key = cases.materialize(source, tmp_path / name / "cases", tmp_path / name / "evaluator", only=buildable)
        assert key["skill"] == name and len(key["cases"]) == len(buildable) >= 4
        assert "use" in {entry["activation"] for entry in key["cases"].values()}
        for case_id, path in cases.manifests(tmp_path / name / "cases").items():
            assert fixture.load(path).id == case_id


# ---------------------------------------------------------------------------------------------- the plan


def test_the_pair_is_named_from_the_two_arms_exposure_and_the_mode_from_where_the_candidate_is(lane):
    selection = plan.shape(freeze(lane))
    assert selection == {"baseline": "baseline", "candidate_arm": "candidate", "candidate": CANDIDATE,
                         "kind": "scripted", "mode": "selection", "also_exposed": [OTHER],
                         "caps": {"baseline": 0.0, "candidate": 0.0},
                         "candidate_bytes": skills.plan([CANDIDATE])["delivered"][0]["bytes"]}
    assert plan.shape(freeze(lane, mode="procedure"))["mode"] == "procedure"
    # The baseline is the arm that exposes less, wherever the plan lists it.
    swapped = refrozen(freeze(lane), lambda draft: draft["arms"].reverse())
    assert plan.shape(swapped)["baseline"] == "baseline"


def _differ_outside(draft):
    draft["arms"][1]["config"]["steps"] = [{"write": "x.txt", "content": "more for one arm\n"}]


def _two_more(draft):
    config = draft["arms"][1]["config"]
    config["optional_skills"].append(THIRD)
    config["skill_sha256"][THIRD] = pins(THIRD)[THIRD]


def _same_exposure(draft):
    draft["arms"][1]["config"] = copy.deepcopy(draft["arms"][0]["config"])


def _changed_skill(draft):
    draft["arms"][1]["config"]["skill_sha256"][CANDIDATE] = "0" * 64


def _unpinned(draft):
    del draft["arms"][1]["config"]["skill_sha256"][CANDIDATE]


def _not_shipped(draft):
    for arm in draft["arms"]:
        arm["config"]["optional_skills"].append("never-shipped-skill")
        arm["config"]["skill_sha256"]["never-shipped-skill"] = "0" * 64


def _fixed_order(draft):
    draft["assignment"]["method"] = "fixed"


def _over_the_limit(draft):
    draft["profiles"]["budget_usd"] = plan.LIMIT_USD + 0.01


def _third_arm(draft):
    draft["arms"].append({**copy.deepcopy(draft["arms"][0]), "id": "another"})


def _placeholder(draft):
    draft["stopping_rule"] = "REQUIRED fixed sample, or the predeclared sequential rule"


def _placeholder_key(draft):
    draft["thresholds"] = {"REQUIRED-name": 1}


@pytest.mark.parametrize("change, says", [
    (_differ_outside, "differ in steps"), (_two_more, "exactly one skill more"),
    (_same_exposure, "exactly one skill more"), (_changed_skill, "not the frozen one"),
    (_unpinned, "pins exactly"), (_not_shipped, "not_shipped"), (_fixed_order, "randomized_blocked"),
    (_over_the_limit, "operator's limit"), (_third_arm, "exactly two arms"), (_placeholder, "stopping_rule"),
    (_placeholder_key, "thresholds.REQUIRED-name")])
def test_a_preregistration_that_is_not_a_paired_skill_evaluation_is_refused_before_anything_runs(lane, change, says):
    frozen = refrozen(freeze(lane), change)
    with pytest.raises(Invalid, match=says):
        plan.shape(frozen)
    with pytest.raises(Invalid, match=says):
        lane_run.run(frozen, cases=lane["manifests"], lane=lane["lane"])
    assert not (lane["lane"] / "ledger").exists()  # nothing was registered


def test_a_budget_at_the_operators_limit_is_accepted(lane):
    at_limit = refrozen(freeze(lane), lambda draft: draft["profiles"].update(budget_usd=plan.LIMIT_USD))
    assert plan.shape(at_limit)["candidate"] == CANDIDATE and plan.LIMIT_USD == 10.0


def test_the_template_once_filled_is_a_paired_skill_evaluation(lane):
    """The template's fields are the ones the checks read: filled, it freezes and passes; while one placeholder is
    left, the check names it."""
    text = (ROOT / "eval" / "skill_eval" / "plan-template.yaml").read_text(encoding="utf-8")
    draft = yaml.safe_load(text)
    draft["experiment"] = "skill-eval-template"
    draft["cases"] = lane["key"]["preregistration_cases"]
    draft["profiles"]["roles"]["worker"] = "fakeprov/fake-model#high"
    for arm in draft["arms"]:
        arm["config"].update(model="fakeprov/fake-model#high", provider_env=["FAKEPROV_TEST_KEY"])
        arm["config"]["profile"].update(id="lb-demo", qualification_state="unqualified")
        arm["config"]["harness"] = {"name": "opencode", "version": "0", "artifact_sha256": {"linux-x64": "0" * 64}}
    draft["arms"][1]["config"].update(exposure("selection"))
    left = [k for k in ("question", "primary_measure", "stopping_rule", "exposure_policy")]
    half = prereg.freeze(copy.deepcopy(draft), by="template test")
    with pytest.raises(Invalid, match="placeholders") as refused:
        plan.shape(half)
    assert all(name in str(refused.value) for name in [*left, "scoring.adjudication_policy",
                                                       "validity_rules.missing_result_policy"])
    for name in left:
        draft[name] = "decided"
    draft["scoring"]["adjudication_policy"] = draft["validity_rules"]["missing_result_policy"] = "decided"
    shape = plan.shape(prereg.freeze(draft, by="template test"))
    assert (shape["kind"], shape["mode"], shape["candidate"]) == ("raw", "selection", CANDIDATE)
    assert shape["caps"] == {"baseline": 0.25, "candidate": 0.25}


# ---------------------------------------------------------------------------------------------- the walk


def run_all(lane: dict, frozen: dict, **kw) -> dict:
    return lane_run.run(frozen, cases=lane["manifests"], lane=lane["lane"], evaluator=[lane["evaluator"]], **kw)


def skill_folders(lane: dict, run_id: str) -> list[str]:
    folder = lane["lane"] / "work" / run_id.split("/", 1)[1] / projection.SKILLS_DIR
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_every_pair_runs_once_with_each_arms_exposure_delivered_and_a_second_call_runs_nothing(lane):
    frozen = freeze(lane)
    registry = dict(f19_arms.ARMS)
    first = run_all(lane, frozen, limit=1)
    assert first["stopped"] == "limit" and len(first["ran"]) == 1
    rest = run_all(lane, frozen)  # resumed from the ledger
    assert rest["stopped"] == "done" and len(rest["ran"]) == 5 and rest["spent_usd"] == 0
    assert run_all(lane, frozen) == {**rest, "ran": []}
    assert f19_arms.ARMS == registry  # F19's registry is as it was for every other experiment
    found = report.pairs(frozen, lane["lane"] / "ledger")
    assert len(found) == 3 and all(p["complete"] for p in found)
    names = set()
    for p in found:
        names |= {p["baseline"]["run_id"], p["candidate"]["run_id"]}
        assert skill_folders(lane, p["baseline"]["run_id"]) == [OTHER]
        assert skill_folders(lane, p["candidate"]["run_id"]) == sorted([CANDIDATE, OTHER])
    # A run is named for its place in the drawn schedule, never for its arm.
    assert names == {f"skill-eval-offline/r00{n}" for n in range(1, 7)}
    order = [entry["arm"] for entry in frozen["assignment"]["order"]]
    assert order[0::2] != ["baseline"] * 3 and order[0::2] != ["candidate"] * 3  # seed 7 draws both orders


def test_a_pair_is_not_started_when_the_budget_cannot_finish_it(lane):
    """A run whose cost is unknown is charged its cap, and a block starts only if every cell it still needs fits."""
    frozen = freeze(lane, cap=0.25, budget=0.8)  # room for a third run, not for the pair it would begin
    out = run_all(lane, frozen)
    assert out["stopped"] == "budget" and len(out["ran"]) == 2 and out["spent_usd"] == 0.5
    assert [r["charged_usd"] for r in out["ran"]] == [0.25, 0.25]
    block = plan.blocks(frozen)[1]
    assert out["next_cell"] == block[0]["cell"]  # the second pair's first cell: nothing of that pair ran
    assert run_all(lane, frozen)["ran"] == []    # and a rerun does not creep past the budget
    found = report.pairs(frozen, lane["lane"] / "ledger")
    assert [p["complete"] for p in found] == [True, False, False]
    assert found[1]["why"] == {"baseline": "not_run", "candidate": "not_run"}


def test_a_lost_attempt_is_charged_its_cap(lane):
    frozen = freeze(lane, cap=0.25, budget=1.0)
    ledger = AttemptLedger(lane["lane"] / "ledger", frozen)
    first = frozen["assignment"]["order"][0]
    ledger.register(run_id=f"{frozen['experiment']}/r001", cell=first["cell"],
                    requested_profile=frozen["profiles"]["roles"])  # registered, then the runner died
    assert lane_run.spent(ledger, plan.shape(frozen)["caps"]) == 0.25
    out = run_all(lane, frozen)
    assert out["stopped"] == "budget" and len(out["ran"]) == 3  # the lost cell is never retried: 0.25 + 3 × 0.25
    lost = report.pairs(frozen, lane["lane"] / "ledger")[0]
    assert not lost["complete"] and "runner_lost" in lost["why"].values()


def test_an_attempt_that_measured_the_host_stops_the_walk(lane, monkeypatch):
    class NoModel(arms.SkillScriptedArm):
        def run(self, repo, config, *, deadline_s, task=None):
            result = super().run(repo, config, deadline_s=deadline_s, task=task)
            result.invalid = "NO_MODEL_STEP"
            return result

    monkeypatch.setattr(arms, "SkillScriptedArm", NoModel)
    out = run_all(lane, freeze(lane))
    assert out["stopped"] == "lane_error" and out["reason_code"] == "NO_MODEL_STEP" and len(out["ran"]) == 1
    assert "NO_MODEL_STEP" in lane_run.LANE_ERRORS and raw.raw_invalid(leaked=[], facts={"model_steps": 0}) \
        == "NO_MODEL_STEP"


def test_a_lane_holds_one_experiment(lane):
    run_all(lane, freeze(lane), limit=1)
    with pytest.raises(Invalid, match="a lane of its own"):
        run_all(lane, freeze(lane, experiment="another-experiment"))


def test_a_lane_whose_evaluator_material_was_once_readable_stays_a_pilot(lane):
    frozen = freeze(lane)
    assert lane_run.claim(lane["lane"], frozen, True)["evaluator_material_hidden"] is True
    assert lane_run.claim(lane["lane"], frozen, False)["evaluator_material_hidden"] is False
    assert lane_run.claim(lane["lane"], frozen, True)["evaluator_material_hidden"] is False
    assert report.report(frozen, lane["lane"])["pilot"] is True


def test_a_skill_that_does_not_arrive_whole_is_an_error_before_the_arm_runs(lane, monkeypatch):
    """The run is counted, as an error and never as a measurement of an exposure it did not have."""
    real = skills.deliver
    monkeypatch.setattr(skills, "deliver", lambda planned, root: {
        **real(planned, root), "exposed": [], "reasons": {CANDIDATE: skills.COPY_FAILED}})
    out = run_all(lane, freeze(lane), limit=1)
    assert out["ran"][0]["validity"] == {"status": "invalid_measurement", "reason_code": "RUNNER_ERROR:Invalid"}


def test_the_evaluators_material_must_be_hidden_from_a_contained_arm(lane, tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "skill-eval" / "evaluator").mkdir(parents=True)
    (home / "skill-eval" / "lane" / "work").mkdir(parents=True)
    outside = tmp_path / "elsewhere" / "evaluator"
    outside.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(raw, "harness_binary", lambda: tmp_path / "bin" / "opencode")
    scratch = home / "skill-eval" / "lane" / "work" / "r000"
    binary = tmp_path / "bin" / "opencode"
    assert arms.readable_inside([home / "skill-eval" / "evaluator"], scratch, binary=binary) == []
    assert arms.readable_inside([outside], scratch, binary=binary) == [str(outside)]
    contained = refrozen(freeze(lane), lambda draft: [a["config"].update(contain=True) for a in draft["arms"]])
    with pytest.raises(Invalid, match="could read the evaluator's material"):
        lane_run.hidden_from_arms(contained, scratch.parent, [outside])
    # An arm that is not contained can read what its user can: its lane says so, and its report is a pilot.
    assert lane_run.hidden_from_arms(freeze(lane), scratch.parent, [outside]) is False
    # Hidden is a claim about named paths: with none named, a contained lane is still not called hidden.
    assert lane_run.hidden_from_arms(contained, scratch.parent, []) is False
    assert lane_run.hidden_from_arms(contained, scratch.parent, [home / "skill-eval" / "evaluator"]) is True
    assert Path(lane["key"]["source_dir"]) == lane["source"].parent.resolve()


# ---------------------------------------------------------------------------------------------- the report


class Observed(arms.SkillScriptedArm):
    """A scripted arm that reports what a model arm would: per case, what the candidate arm loaded and each arm's
    usage. ``None`` leaves a value unknown, as a session that could not be read does."""

    loads: dict = {}
    tokens: dict = {}

    def run(self, repo, config, *, deadline_s, task=None):
        result = super().run(repo, config, deadline_s=deadline_s, task=task)
        case = fixture.git(repo, "log", "--format=%s").split(":")[0]
        side = "candidate" if CANDIDATE in result.harness["exposure"]["exposed"] else "baseline"
        loaded = self.loads.get((case, side), {})
        result.harness["exposure"].update(loaded=loaded, skill_other=1 if side == "baseline" else 0)
        first = self.tokens.get((case, side))
        result.harness["first_step_input_tokens"] = first
        if first is not None:
            result.cost = {"provider_reported_usd": first / 10000, "charged_usd": first / 10000,
                           "tokens": {"input": first * 3, "output": 50, "cache": {"read": 10, "write": 0}}}
        (repo / "ANSWER.md").write_text(f"answer of {side}\n", encoding="utf-8")
        return result


@pytest.fixture
def observed(lane, monkeypatch):
    """A finished lane of three pairs: K01 (use) loaded once, K02 (skip) loaded twice, K03 (abstain) not loaded and
    its baseline's usage unknown."""
    Observed.loads = {("K01", "candidate"): {CANDIDATE: 1}, ("K02", "candidate"): {CANDIDATE: 2, OTHER: 1},
                      ("K03", "candidate"): {}, ("K02", "baseline"): {OTHER: 1}}
    Observed.tokens = {("K01", "baseline"): 1000, ("K01", "candidate"): 1300, ("K02", "baseline"): 1000,
                       ("K02", "candidate"): 1500, ("K03", "candidate"): 1200}
    monkeypatch.setattr(arms, "SkillScriptedArm", Observed)
    frozen = freeze(lane, cap=0.5, budget=10.0)
    assert run_all(lane, frozen)["stopped"] == "done"
    return frozen


def test_cost_is_the_paired_difference_in_usage_and_an_unknown_is_missing_never_zero(lane, observed):
    out = report.report(observed, lane["lane"], key=lane["key"])
    cost = out["cost"]
    assert cost["complete_pairs"] == 3
    first = cost["candidate_minus_baseline"]["first_step_input_tokens"]
    assert first == {"n": 2, "missing": 1, "mean": 400.0, "median": 400.0, "min": 300.0, "max": 500.0}
    assert cost["candidate_minus_baseline"]["tokens.input"]["mean"] == 1200.0
    assert cost["candidate_minus_baseline"]["tokens.cache.read"]["mean"] == 0.0
    assert cost["candidate_minus_baseline"]["cost_usd"]["n"] == 2
    # Split by whether the candidate run loaded the candidate; K03's pair, not loaded, has no known difference.
    assert cost["when_the_candidate_was_loaded"]["pairs"] == 2
    assert cost["when_it_was_not"]["pairs"] == 1 and "first_step_input_tokens" not in cost["when_it_was_not"]
    size = skills.plan([CANDIDATE])["delivered"][0]["bytes"]
    assert cost["loads"] == {"runs_with_loaded_known": 3, "loads": 3, "skill_md_bytes": size,
                             "loaded_bytes_lower_bound": 3 * size}
    # The unknown baseline was charged its cap, so the budget never undercounts it.
    assert cost["counted_runs_charged_usd"]["baseline"] == pytest.approx(0.1 + 0.1 + 0.5)
    assert out["decision"] is None and out["pilot"] is True


def test_selection_sets_what_was_loaded_beside_the_cases_expected_activation(lane, observed):
    selection = report.report(observed, lane["lane"], key=lane["key"])["selection"]
    assert selection["candidate_runs_by_expected_activation"] == {
        "abstain": {"loaded": 0, "not_loaded": 1, "unknown": 0}, "skip": {"loaded": 1, "not_loaded": 0, "unknown": 0},
        "use": {"loaded": 1, "not_loaded": 0, "unknown": 0}}
    assert selection["false_activations"] == 1 and selection["missed_activations"] == 0
    assert selection["runs_that_loaded_another_exposed_skill"] == {"baseline": {OTHER: 1}, "candidate": {OTHER: 1}}
    assert selection["skill_calls_that_loaded_nothing"] == {"baseline": 3, "candidate": 0}
    # Without the evaluator's key nothing is guessed: every run's expected activation is unknown.
    blind = report.report(observed, lane["lane"])["selection"]
    assert list(blind["candidate_runs_by_expected_activation"]) == ["unknown"]
    assert blind["false_activations"] == blind["missed_activations"] == 0


def test_a_grading_packet_names_no_arm_exposure_load_or_cost(lane, observed):
    packets = report.packets(observed, lane["lane"] / "ledger", lane["manifests"])
    assert len(packets) == 6 and [p["run_id"] for p in packets] == sorted(p["run_id"] for p in packets)
    for packet in packets:
        assert set(packet) == {"schema", "run_id", "case", "task", "export", "export_sha256", "changed_paths",
                               "truncated"}
        text = json.dumps(packet)
        assert not any(word in text for word in ("baseline", "candidate", CANDIDATE, OTHER, "loaded", "usd"))
        assert packet["changed_paths"] == ["ANSWER.md"]
        assert (Path(packet["export"]) / "ANSWER.md").read_text(encoding="utf-8").startswith("answer of ")
        assert packet["task"] == fixture.load(lane["manifests"][packet["case"]]).manifest["task"]


def test_benefit_is_paired_counts_from_the_graders_file_and_no_decision(lane, observed, tmp_path):
    found = {p["case"]: p for p in report.pairs(observed, lane["lane"] / "ledger")}
    grades = tmp_path / "grades.jsonl"
    rows = [(found["K01"]["baseline"], False), (found["K01"]["candidate"], True),
            (found["K02"]["baseline"], True), (found["K02"]["candidate"], True),
            (found["K03"]["candidate"], True)]  # K03's baseline is left ungraded
    grades.write_text("".join(json.dumps({"run_id": run["run_id"], "task_correct": right}) + "\n"
                              for run, right in rows), encoding="utf-8")
    out = report.report(observed, lane["lane"], key=lane["key"], grades=report.load_grades(grades))
    assert out["benefit"] == {"graded": True, "complete_pairs": {"both_correct": 1, "candidate_only": 1,
                                                                "baseline_only": 0, "neither": 0, "ungraded": 1}}
    assert out["decision"] is None
    assert report.report(observed, lane["lane"])["benefit"]["graded"] is False
    grades.write_text(grades.read_text(encoding="utf-8") * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="graded twice"):
        report.load_grades(grades)


def test_a_run_without_its_arms_frozen_exposure_leaves_its_pair_incomplete_and_listed(lane, monkeypatch):
    class Short(arms.SkillScriptedArm):
        def run(self, repo, config, *, deadline_s, task=None):
            result = super().run(repo, config, deadline_s=deadline_s, task=task)
            if fixture.git(repo, "log", "--format=%s").startswith("K02") and CANDIDATE in config["optional_skills"]:
                result.harness["exposure"]["delivered"] = []
            return result

    monkeypatch.setattr(arms, "SkillScriptedArm", Short)
    frozen = freeze(lane)
    run_all(lane, frozen)
    out = report.report(frozen, lane["lane"], key=lane["key"])
    assert out["pairs"] == {"planned": 3, "complete": 2, "incomplete": [
        {"case": "K02", "repetition": 1, "why": {"baseline": None, "candidate": "EXPOSURE_MISMATCH"}}]}
    assert out["cost"]["complete_pairs"] == 2
    assert sum(sum(row.values()) for row in out["selection"]["candidate_runs_by_expected_activation"].values()) == 2


# ---------------------------------------------------------------------------------------------- the command line


def test_the_command_line_walks_a_dry_lane_from_cases_to_report(lane, tmp_path, capsys):
    out, evaluator = tmp_path / "cli-cases", tmp_path / "cli-evaluator"
    assert cli.main(["materialize", str(lane["source"]), "--cases", str(out), "--evaluator", str(evaluator)]) == 0
    block = json.loads(capsys.readouterr().out)["cases"]
    frozen = tmp_path / "plan.frozen.yaml"
    prereg.dump(prereg.freeze(make_plan(block, cap=0.25, budget=0.6), by="cli test"), frozen)
    assert cli.main(["check", str(frozen)]) == 0
    assert json.loads(capsys.readouterr().out)["candidate"] == CANDIDATE
    walk = ["run", str(frozen), "--cases", str(out), "--lane", str(tmp_path / "cli-lane"), "--evaluator",
            str(evaluator)]
    assert cli.main(walk) == 3  # stopped at the budget, with what ran recorded
    assert json.loads(capsys.readouterr().out)["stopped"] == "budget"
    assert cli.main(["packets", str(frozen), "--cases", str(out), "--lane", str(tmp_path / "cli-lane")]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2
    assert cli.main(["report", str(frozen), "--lane", str(tmp_path / "cli-lane"), "--evaluator", str(evaluator)]) == 0
    told = json.loads(capsys.readouterr().out)
    assert told["pairs"]["complete"] == 1 and told["pilot"] is True
    assert cli.main(["materialize", str(lane["source"]), "--cases", str(out), "--evaluator", str(evaluator)]) == 1
    assert "refused" in capsys.readouterr().err


def test_told_prints_the_lines_a_worker_gets_from_their_owner(capsys):
    assert cli.main(["told", "--skills", CANDIDATE, "--optional", OTHER]) == 0
    assert json.loads(capsys.readouterr().out)["told"] == "\n".join(
        projection.skills_text(skills.plan([CANDIDATE], [OTHER])))


def test_what_an_arm_is_told_is_appended_to_the_task_verbatim_and_only_when_the_plan_says(lane, monkeypatch):
    seen: dict = {}
    real = f19_arms.ScriptedArm.run

    def watching(self, repo, config, *, deadline_s, task=None):
        seen[tuple(config["optional_skills"])] = task
        return real(self, repo, config, deadline_s=deadline_s, task=task)

    monkeypatch.setattr(f19_arms.ScriptedArm, "run", watching)
    frozen = refrozen(freeze(lane), lambda draft: draft["arms"][1]["config"].update(told="- Told line.\n"))
    run_all(lane, frozen, limit=2)
    tasks = {fixture.load(path).manifest["task"] for path in lane["manifests"].values()}
    plain, told = seen[(OTHER,)], seen[(OTHER, CANDIDATE)]
    assert plain in tasks  # the baseline's task is the case's, byte for byte
    assert told.endswith("\n\n- Told line.\n") and told[: -len("\n- Told line.\n")] in tasks
