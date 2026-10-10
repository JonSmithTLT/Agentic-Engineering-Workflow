"""The lower-bound qualification lane's own rules (agent-effectiveness adoption, delta D3; review of PR #153).

The tree-observable behaviours never count a run cut short by its limits for behaviours 4 and 5; following the
distractor or the stale note shows behaviour 8; every attempt is charged against the budget, at its cap when its cost
is unknown or the run was lost; and no model runs while an oracle is on the host.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LANE = ROOT / "eval" / "experiments" / "lower-bound-qualification"


@pytest.fixture(scope="module")
def qualify():
    spec = importlib.util.spec_from_file_location("lbq_qualify", LANE / "qualify.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rules():
    return yaml.safe_load((LANE / "behaviours.yaml").read_text(encoding="utf-8"))


CRITERIA = {"criterion 1: md.reset() empties report(); a document's report holds only its links": True,
            "criterion 2: each blocked URL once, in first-appearance order": False,
            "criterion 3: strict mode's LinkPolicyError names the URL and carries it as .url": True,
            "criterion 4: the documentation describes report() and md.reset()": False,
            "structure: the link policy runs after the inline processor": True}


def record(case: str, changed: list[str], *, ended: str = "ended", truncated: bool = False) -> dict:
    return {"case": {"id": case}, "outcome": {"changed_paths": changed, "harness_outcome": ended,
                                              "truncated": truncated}}


def test_requirement_loss_is_read_only_from_a_finished_run(qualify, rules):
    changed = ["markdown/extensions/linkpolicy/__init__.py"]
    assert qualify.tree_behaviours(record("LBQ-3", changed), rules, CRITERIA)["requirement_loss_on_longer_tasks"]
    for cut in (record("LBQ-3", changed, truncated=True), record("LBQ-3", changed, ended="cost_cap"),
                record("LBQ-3", changed, ended="deadline")):
        assert not qualify.tree_behaviours(cut, rules, CRITERIA)["requirement_loss_on_longer_tasks"]


def test_an_incomplete_cross_file_change_is_read_only_from_a_finished_run(qualify, rules):
    partial = ["markdown/extensions/linkpolicy/__init__.py", "tests/test_syntax/extensions/test_link_policy.py"]
    complete = [*partial, "markdown/extensions/linkpolicy/schema.py", "docs/extensions/link_policy.md"]
    assert qualify.tree_behaviours(record("LBQ-2", partial), rules, {})["incomplete_cross_file_changes"]
    assert not qualify.tree_behaviours(record("LBQ-2", complete), rules, {})["incomplete_cross_file_changes"]
    assert not qualify.tree_behaviours(record("LBQ-2", partial, ended="cost_cap", truncated=True), rules,
                                       {})["incomplete_cross_file_changes"]
    assert not qualify.tree_behaviours(record("LBQ-2", partial, truncated=True), rules,
                                       {})["incomplete_cross_file_changes"]  # the step limit


def test_bytecode_left_by_running_the_code_is_never_a_change(qualify, rules):
    changed = ["markdown/extensions/linkpolicy/__pycache__/rules.cpython-311.pyc",
               "markdown/extensions/linkpolicy/rules.py"]
    assert qualify.meaningful(changed, rules) == ["markdown/extensions/linkpolicy/rules.py"]


@pytest.mark.parametrize("changed, structure_ok, shown", [
    (["markdown/extensions/linkpolicy/rules.py"], True, False),
    (["tests/test_syntax/extensions/test_wikilinks_spaces.py"], True, True),
    (["markdown/extensions/wikilinks.py"], True, True),
    (["markdown/extensions/linkpolicy/__init__.py"], False, True),  # the stale TODO followed
])
def test_following_the_distractor_or_the_stale_note_shows_behaviour_8(qualify, rules, changed, structure_ok, shown):
    checks = {"structure: the link policy runs after the inline processor": structure_ok}
    got = qualify.tree_behaviours(record("LBQ-1", changed), rules, checks)
    assert got["difficulty_recovering_after_distraction"] is shown


def test_an_edit_under_the_decoy_root_shows_bad_search_root_selection(qualify, rules):
    got = qualify.tree_behaviours(record("LBQ-1", ["tools/linkpolicy/rules.py"]), rules, {})
    assert got["bad_search_root_selection"]


def test_every_attempt_is_charged_and_an_unknown_or_lost_one_at_its_cap(qualify, tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "a.json").write_text(json.dumps({"cost": {"provider_reported_usd": 0.2, "charged_usd": 0.2}}))
    (runs / "b.json").write_text(json.dumps({"cost": {}}))  # the arm failed before it knew its cost
    attempts = {
        "x/a": SimpleNamespace(run_id="x/a", registered={"arm": "raw"}, finalized={"validity": "valid"}),
        "x/b": SimpleNamespace(run_id="x/b", registered={"arm": "raw"}, finalized={"validity": "invalid_measurement"}),
        "x/c": SimpleNamespace(run_id="x/c", registered={"arm": "raw"}, finalized=None),  # runner_lost
    }
    ledger = SimpleNamespace(attempts=lambda: attempts, runs=runs)
    out = tmp_path / "out"
    (out / "floor").mkdir(parents=True)
    (out / "floor" / "floor.json").write_text(json.dumps({"trials": [], "charged_usd": 0.3}))
    assert qualify.spent_so_far(out, ledger, {"raw": 0.75}) == pytest.approx(0.3 + 0.2 + 0.75 + 0.75)


@pytest.mark.parametrize("costs, alive_polls, reason", [
    ([0.1, 0.3, 0.6], 5, "cap"),                   # the cap is reached (0.4 before + 0.6)
    ([None, None, None], 5, "unreadable"),         # fails closed: an unknown spend is never zero
    ([None, 0.1, None, 0.2, 0.3], 5, None),        # a transient unreadable poll is not three in a row
    ([0.1, 0.2], 2, None),                         # the trial ended by itself under the cap
])
def test_the_floor_watcher_stops_a_trial_at_the_cap_and_fails_closed_on_an_unknown_spend(qualify, costs,
                                                                                         alive_polls, reason):
    polls = iter(costs)
    alive = iter([True] * min(alive_polls, len(costs)) + [False])
    got = qualify.watch_floor(lambda: next(alive), lambda: next(polls), spent_before=0.4, cap=1.0,
                              sleep=lambda s: None)
    if reason is None:
        assert got is None
    else:
        assert got and reason in got


def test_no_model_runs_while_an_oracle_is_on_the_host(qualify, tmp_path):
    out = tmp_path / "lane" / "out"
    out.mkdir(parents=True)
    qualify.arm_host_clean(out, None)
    with pytest.raises(SystemExit, match="AEW_EVAL_HIDDEN_ROOT is set"):
        qualify.arm_host_clean(out, tmp_path / "private")
    (tmp_path / "lane" / "hidden").mkdir()
    with pytest.raises(SystemExit, match="the oracles are on this host"):
        qualify.arm_host_clean(out, None)


def test_the_lane_files_are_consistent(qualify):
    """The plan's arm pins its profile record as the record states it; the profiles derive their states; every case
    commits to an oracle; the overlay is portable and replaces no upstream file."""
    report: dict = {}
    plan = yaml.safe_load((LANE / "prereg.yaml").read_text(encoding="utf-8"))
    qualify.check_cases(report)
    qualify.check_overlay(report)
    qualify.check_profiles(report, plan)
    assert report["profiles"]["lb-deepseek-v4-flash"] == "unqualified"
    assert all(yaml.safe_load(p.read_text(encoding="utf-8"))["hidden_sha256"] for p in qualify.CASES.values())


# ---------------------------------------------------------------------------------------------- provider failures

# A floor trial's record exactly as the live test wrote it when the provider rejected the key: the implementer
# crashed, the harness outcome names the provider's error, and the model produced nothing. The test still passed.
AUTH_RUN = {"role": "implementer", "status": "crashed",
            "harness_outcome": "the agent's turn ended: failed (provider.auth: Invalid API key.)",
            "reason": "harness exited with 1 without recording its expected output", "steps": 1,
            "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}, "cost": 0,
            "bridge": {"requests": 0, "refused": 0, "outcomes": {}}, "evidence": [], "model_check": "no_model_step",
            "tools_called": {}, "workspace_changed": False, "changed_paths": []}
PASSING_RUN = {"role": "implementer", "status": "ended_with_evidence", "harness_outcome": "ended", "steps": 9,
               "tokens": {"input": 4000, "output": 300}, "cost": 0.01, "bridge": {"requests": 2},
               "evidence": [{"id": "ev-1", "kind": "implementation_report", "result": "pass"}]}
FAILING_RUN = {**AUTH_RUN, "tokens": {"input": 5200, "output": 410}, "steps": 12,
               "harness_outcome": "the agent's turn ended: failed (provider.overloaded: try again later)"}


def trial_of(run: dict) -> dict:
    return {"schema": "aew/live-model-trial/v1", "scenario": "lifecycle", "trial": 0, "runs": [run], "lead": {}}


def write_results(path: Path, run: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trial_of(run), sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def lane(qualify, tmp_path, monkeypatch):
    """``cmd_floor`` with the frozen record, the profile and the live trial faked: ``runs`` lists the implementer
    run each successive trial records (a placeholder key; no provider is called)."""
    frozen = {"thresholds": {"budget": {"floor_cap_usd": 1.0}, "floor": {"trials": 2}}}
    monkeypatch.setattr(qualify, "frozen_record", lambda: frozen)
    monkeypatch.setattr(qualify, "worker_profile", lambda f: {"id": "lb-fake", "ref": "opencode/fake",
                                                              "credential_env": ["OPENCODE_API_KEY"]})
    monkeypatch.setenv("OPENCODE_API_KEY", qualify.PLACEHOLDER)
    calls: list[Path] = []
    runs: list[dict] = []

    def fake_trial(where, record, names, *, cap, spent_before):
        calls.append(where)
        results = write_results(where / "results.jsonl", runs.pop(0))
        return 0, qualify.read_results(results), 0.0, []  # pytest passed, as it did on the real run

    monkeypatch.setattr(qualify, "floor_trial", fake_trial)
    out = tmp_path / "lane" / "out"
    return SimpleNamespace(out=out, calls=calls, runs=runs,
                           floor=lambda: qualify.cmd_floor(SimpleNamespace(), out, None),
                           state=lambda: json.loads((out / "floor" / "floor.json").read_text(encoding="utf-8")))


def test_a_provider_auth_failure_is_a_lane_error_not_a_failed_trial(qualify):
    got = qualify.floor_verdict([trial_of(AUTH_RUN)])
    assert got["state"] == qualify.LANE_ERROR
    assert got["reason_code"] == "PROVIDER_AUTH_FAILED"
    assert got["provider_error"] == {"type": "provider.auth", "message": "Invalid API key."}


def test_a_provider_auth_failure_never_uses_a_floor_trial(qualify, lane):
    lane.runs.append(AUTH_RUN)
    with pytest.raises(SystemExit):
        lane.floor()
    state = lane.state()
    assert [t["verdict"] for t in state["trials"]] == ["lane_error"]
    assert state["trials"][0]["reason_code"] == "PROVIDER_AUTH_FAILED"
    assert qualify.counted_trials(state) == []


def test_the_floor_stops_at_once_on_a_rejected_key(qualify, lane):
    lane.runs.extend([AUTH_RUN, PASSING_RUN])  # a second trial is there to take, and is never taken
    with pytest.raises(SystemExit) as stop:
        lane.floor()
    assert len(lane.calls) == 1
    message = str(stop.value.code)
    assert message.startswith("refused: the provider rejected the key (provider.auth: Invalid API key.)")
    assert "OPENCODE_API_KEY" in message and "no floor trial was used" in message


def test_a_rerun_after_fixing_the_key_runs_the_floor_fresh(qualify, lane):
    lane.runs.append(AUTH_RUN)
    with pytest.raises(SystemExit):
        lane.floor()
    lane.runs.extend([FAILING_RUN, FAILING_RUN])  # both preregistered trials are still there to use
    assert lane.floor() == 3
    assert [t["verdict"] for t in lane.state()["trials"]] == ["lane_error", "failed", "failed"]
    assert len(lane.calls) == 3 and lane.calls[-1].name == "trial-3"  # every trial keeps its own directory


def test_trials_a_rejected_key_used_up_before_this_fix_are_read_as_lane_errors(qualify, lane):
    """The recovery for a lane directory whose two trials were recorded ``failed`` on a rejected key: the next run
    reads them from their stored results as the lane errors they were, and runs the floor."""
    floor = lane.out / "floor"
    old = [{"trial": n, "verdict": "failed", "pytest_exit": 0, "charged_usd": 0.0, "cost_known": True, "stopped": [],
            "results": str(write_results(floor / f"trial-{n}" / "results.jsonl", AUTH_RUN)),
            "session_state": str(floor / f"trial-{n}" / "tmp")} for n in (1, 2)]
    (floor / "floor.json").write_text(json.dumps({"trials": old, "charged_usd": 0.0}), encoding="utf-8")
    state = qualify.floor_state(lane.out)
    assert [(t["verdict"], t["reclassified_from"]) for t in state["trials"]] == [("lane_error", "failed")] * 2
    lane.runs.append(PASSING_RUN)
    assert lane.floor() == 0
    assert [t["verdict"] for t in lane.state()["trials"]] == ["lane_error", "lane_error", "passed"]


def test_a_model_that_acted_and_failed_still_uses_a_floor_trial(qualify):
    assert qualify.floor_verdict([trial_of(FAILING_RUN)])["state"] == "failed"  # tokens: the model acted
    crashed = {**AUTH_RUN, "harness_outcome": "the agent's turn ended: failed"}  # no provider error named
    assert qualify.floor_verdict([trial_of(crashed)])["state"] == "failed"
    assert qualify.floor_verdict([trial_of(PASSING_RUN), trial_of(AUTH_RUN)])["state"] == "passed"


@pytest.mark.parametrize("outcome, reason", [
    ("the agent's turn ended: failed (provider.auth: Invalid API key.)", "PROVIDER_AUTH_FAILED"),
    ("the agent's turn ended: failed (provider.api: HTTP 401 Unauthorized)", "PROVIDER_AUTH_FAILED"),
    ("the agent's turn ended: failed (provider.rate_limit: slow down)", "NO_MODEL_STEP"),
    ("the agent's turn ended: failed (provider.api: request of 403 k tokens rejected)", "NO_MODEL_STEP"),
])
def test_a_provider_failure_is_named_for_its_remedy(qualify, outcome, reason):
    got = qualify.floor_verdict([trial_of({**AUTH_RUN, "harness_outcome": outcome})])
    assert (got["state"], got["reason_code"]) == ("lane_error", reason)


@pytest.mark.parametrize("outcome", [
    "the agent's turn ended: failed (UnknownError: status 403 forbidden)",
    "the agent's turn ended: failed (ContextOverflowError: prompt of 403 k tokens too long)",
])
def test_an_error_that_is_not_the_providers_still_uses_a_floor_trial(qualify, outcome):
    assert qualify.floor_verdict([trial_of({**AUTH_RUN, "harness_outcome": outcome})])["state"] == "failed"


@pytest.mark.parametrize("acted", [
    {"bridge": {"requests": 1, "refused": 0, "outcomes": {}}},
    {"evidence": [{"id": "ev-1", "kind": "progress", "result": None}]},
    {"tools_called": {"bash": 2}},
    {"workspace_changed": True, "changed_paths": ["calc/core.py"]},
    {"workspace_changed": None},
    {"bridge": {}},
    {"tokens": None},
    {"tokens": {}},
    {"tokens": {"input": "5200", "output": 0}},
    {"drop": "evidence"},
    {"drop": "tools_called"},
    {"evidence": None},
    {"tools_called": None},
])
def test_a_model_that_reached_the_bridge_is_never_a_lane_error(qualify, acted):
    """A lane error needs AEW's own proof that the model did nothing; anything it acted on, a fact that is missing,
    or a usage that is missing or not a number, leaves the trial counted."""
    acted = dict(acted)
    drop = acted.pop("drop", None)
    run = {**AUTH_RUN, "harness_outcome": "the agent's turn ended: failed (provider.overloaded: try again)", **acted}
    run.pop(drop, None)
    assert qualify.floor_verdict([trial_of(run)])["state"] == "failed"


def test_a_trial_this_version_judged_is_never_reread(qualify, tmp_path):
    out = tmp_path / "out"
    results = write_results(out / "floor" / "trial-1" / "results.jsonl", AUTH_RUN)
    trial = {"trial": 1, "verdict": "failed", "results": str(results), "judged_by": qualify.JUDGED_BY}
    (out / "floor" / "floor.json").write_text(json.dumps({"trials": [trial], "charged_usd": 0.0}), encoding="utf-8")
    assert [t["verdict"] for t in qualify.floor_state(out)["trials"]] == ["failed"]


def test_the_ceiling_stops_at_once_on_a_rejected_key(qualify, tmp_path, monkeypatch):
    out = tmp_path / "lane" / "out"
    (out / "floor").mkdir(parents=True)
    (out / "floor" / "floor.json").write_text(json.dumps({"trials": [{"trial": 1, "verdict": "passed"}],
                                                          "charged_usd": 0.1}), encoding="utf-8")
    frozen = {"profiles": {"budget_usd": 5.0}, "thresholds": {"budget": {"overshoot_margin_usd": 0.05}},
              "arms": [{"id": "raw", "config": {"cap_usd": 0.75, "provider_env": ["OPENCODE_API_KEY"]}}],
              "validity_rules": {"retry_policy": {"max_retries": 2, "allowed_for": ["invalid_measurement"]}},
              "assignment": {"order": [{"cell": "LBQ-1/raw/1", "arm": "raw"}, {"cell": "LBQ-2/raw/1", "arm": "raw"}]}}
    monkeypatch.setattr(qualify, "frozen_record", lambda: frozen)
    monkeypatch.setattr(qualify, "AttemptLedger", lambda d, f: SimpleNamespace(attempts=dict, status=dict))
    cells: list[str] = []

    def run_cell(frozen, *, cell, **kw):
        cells.append(cell)
        return {"run_id": f"x/{cell}", "validity": {"status": "invalid_measurement", "reason_code": "NO_MODEL_STEP"},
                "cost": {"charged_usd": 0.0}, "outcome": {"truncated_why": [], "model_steps": 0, "errors": [
                    {"type": "provider.auth", "message": "Invalid API key."}]}}

    monkeypatch.setattr(qualify.runner, "run_cell", run_cell)
    with pytest.raises(SystemExit) as stop:
        qualify.cmd_ceiling(SimpleNamespace(deadline_s=60), out, None)
    assert cells == ["LBQ-1/raw/1"]  # no retry of the cell, no later cell
    message = str(stop.value.code)
    assert message.startswith("refused: the provider rejected the key (provider.auth")
    assert "the cell has 2 attempts left" in message  # its first attempt: both preregistered retries remain
    assert qualify.ceiling_stop({"validity": {"status": "valid", "reason_code": None}}) is None


def test_a_ceiling_stop_without_a_provider_error_blames_no_provider(qualify):
    stop = qualify.ceiling_stop({"validity": {"status": "invalid_measurement", "reason_code": "NO_MODEL_STEP"},
                                 "outcome": {"errors": []}})
    message = qualify.lane_error_message(stop, ["OPENCODE_API_KEY"], where="x", again="qualify.py ceiling")
    assert message.startswith("refused: no model step was recorded") and "provider" not in message
    stop = qualify.ceiling_stop({"validity": {"status": "invalid_measurement", "reason_code": "NO_MODEL_STEP"},
                                 "outcome": {"errors": [{"type": "UnknownError", "message": "boom"}]}})
    message = qualify.lane_error_message(stop, ["OPENCODE_API_KEY"], where="x", again="qualify.py ceiling")
    assert message.startswith("refused: no model step was recorded (UnknownError: boom)")
    assert "the provider" not in message
