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
    frozen = {"experiment": "lbq-v1-deepseek-v4-flash", "canonical_sha256": "a" * 64,
              "thresholds": {"budget": {"floor_cap_usd": 1.0}, "floor": {"trials": 2}}}
    monkeypatch.setattr(qualify, "EXPLICIT", True)
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
    frozen = {"experiment": "lbq-v1-deepseek-v4-flash", "canonical_sha256": "a" * 64, "profiles": {"budget_usd": 5.0},
              "thresholds": {"budget": {"overshoot_margin_usd": 0.05}},
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


def real_ceiling(qualify, tmp_path, monkeypatch):
    """``cmd_ceiling`` over the real runner and the real ``AttemptLedger`` (which enforces the frozen retry policy over
    registrations), on a demo case with two cells (C1/raw/1, C1/raw/2) and 2 retries per cell, a passed floor and a
    stand-in harness binary. Returns the lane, the cells run in order, and ``outcome(cell)``: what the next attempt of
    a cell returns ("refused", "arm_error" or "valid")."""
    from aew_eval import arms, fixture, prereg, raw

    binary = tmp_path / "bin" / "opencode-cli.py"
    binary.parent.mkdir()
    binary.write_text("# a stand-in harness binary\n", encoding="utf-8")
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(binary))
    config = {"role": "worker", "model": "fakeprov/fake-model#high", "steps": 5, "cap_usd": 0.75, "provider_env": [],
              "contain": False,
              "profile": {"id": "lb-demo", "qualification_state": "unqualified",
                          "effective_profile": {"context.orientation": None, "tools.presentation": None}},
              "harness": {"name": "opencode", "version": "2.0.18",
                          "artifact_sha256": {raw.host_platform(): raw._sha256_file(binary)}},  # noqa: SLF001
              "session_db": {"retain": True, "retention_days": 30, "fields": [{"field": "tool.name",
                                                                                "transform": "none"}]}}
    base = tmp_path / "case" / "base"
    base.mkdir(parents=True)
    (base / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    case_path = tmp_path / "case" / "case.yaml"
    case_path.write_text(yaml.safe_dump({"schema": "aew/eval-case/v1", "id": "C1", "family": "demo",
                                         "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None,
                                         "task": "Fix add() in calc.py."}), encoding="utf-8")
    case = fixture.load(case_path)
    frozen = prereg.freeze({
        "schema": "aew/eval-prereg/v1", "experiment": "lbq-demo", "question": "q", "purpose": "qualification",
        "arms": [{"id": "raw", "kind": "raw", "description": "harness alone", "config": config}],
        "cases": [{"id": "C1", "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": {"worker": "fakeprov/fake-model#high"}, "budget_usd": 5.0},
        "runs_per_cell": 2, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "behaviours shown", "metrics": [{"name": "behaviours", "version": "1"}],
        "thresholds": {"budget": {"overshoot_margin_usd": 0.05}},
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 2, "allowed_for": ["invalid_measurement"]},
                           "missing_result_policy": "unobserved"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id"}, by="tester")
    out = tmp_path / "lane" / "out"
    (out / "floor").mkdir(parents=True)
    (out / "floor" / "floor.json").write_text(json.dumps({
        "trials": [{"trial": 1, "verdict": "passed"}], "charged_usd": 0.025, "experiment": "lbq-demo",
        "preregistration_sha256": frozen["canonical_sha256"]}), encoding="utf-8")
    (out / qualify.LANE_MARK).write_text("lbq-demo\n", encoding="utf-8")
    monkeypatch.setattr(qualify, "frozen_record", lambda: frozen)
    monkeypatch.setattr(qualify, "CASES", {"C1": case_path})
    cells: list[str] = []
    plan: dict[str, list[str]] = {}

    def fake_run(self, repo, config, *, deadline_s, task=None):
        cell = cells[-1]
        kind = plan[cell].pop(0) if plan.get(cell) else "valid"
        if kind == "refused":  # containment failed before launch: no harness process, nothing spent
            return arms.ArmResult(outcome={"harness_outcome": "not_started", "launched": False,
                                           "truncated_why": ["turn:not_started"],
                                           "arm_error": "Invalid: containment failed: hidden paths visible",
                                           "containment": {"contained": True, "ok": False,
                                                           "reason": "hidden paths visible from inside: [work]"}},
                                  cost={"provider_reported_usd": None, "charged_usd": 0.0},
                                  invalid="CONTAINMENT_FAILED")
        observed = [{"role": "worker", "provider": "fakeprov", "model": "fake-model", "effort": "high"}]
        if kind == "arm_error":  # an invalid attempt that does not stop the ceiling
            return arms.ArmResult(outcome={"launched": True, "truncated_why": []}, observed_profiles=observed,
                                  cost={"provider_reported_usd": 0.1, "charged_usd": 0.1}, invalid="ARM_ERROR")
        return arms.ArmResult(outcome={"launched": True, "truncated_why": []}, observed_profiles=observed,
                              cost={"provider_reported_usd": 0.1, "charged_usd": 0.1})

    real_run_cell = qualify.runner.run_cell

    def run_cell(frozen, *, cell, **kw):
        cells.append(cell)
        return real_run_cell(frozen, cell=cell, **kw)

    monkeypatch.setattr(raw.RawArm, "run", fake_run)
    monkeypatch.setattr(qualify.runner, "run_cell", run_cell)
    return out, cells, plan


def ceiling(qualify, out):
    return qualify.cmd_ceiling(SimpleNamespace(deadline_s=60), out, None)


def test_never_launched_attempts_count_as_the_ledger_counts_them_and_never_wedge_a_cell(qualify, tmp_path,
                                                                                       monkeypatch):
    """Review F1 of aba5846: the ledger counts every registered attempt against the frozen retry policy, so the
    ceiling does too. Each never-launched attempt stops the ceiling at once, charged $0, saying how many attempts the
    cell has left; after the cell's third, a rerun moves on to the next cell, never asking the ledger for a retry it
    refuses."""
    out, cells, plan = real_ceiling(qualify, tmp_path, monkeypatch)
    plan["C1/raw/1"] = ["refused"] * 3
    for left in ("2 attempts left", "1 attempt left", "0 attempts left"):
        with pytest.raises(SystemExit) as stop:
            ceiling(qualify, out)
        message = str(stop.value.code)
        assert message.startswith("refused: cell C1/raw/1's raw run could not be contained")
        assert "nothing was spent (charged $0)" in message and f"the cell has {left}" in message
        assert "refused (nothing registered)" not in message
    assert "a rerun moves on to the next cell" in message
    assert ceiling(qualify, out) == 0  # the rerun: C1/raw/1 has used its attempts; C1/raw/2 runs
    assert cells == ["C1/raw/1"] * 3 + ["C1/raw/2"]


def test_a_never_launched_attempt_then_two_invalid_ones_use_the_cells_retries(qualify, tmp_path, monkeypatch):
    out, cells, plan = real_ceiling(qualify, tmp_path, monkeypatch)
    plan["C1/raw/1"] = ["refused", "arm_error", "arm_error"]
    with pytest.raises(SystemExit, match="the cell has 2 attempts left"):
        ceiling(qualify, out)
    assert ceiling(qualify, out) == 0  # the host fixed: two ARM_ERROR retries, then the cell is done; C1/raw/2 runs
    assert cells == ["C1/raw/1"] * 3 + ["C1/raw/2"]


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


# ---------------------------------------------------------------------------------------------- the experiments

V4, V41, NANO = "lbq-v1-deepseek-v4-flash", "lbq-v1-deepseek-v4-1-flash", "lbq-v1-gpt-5-nano"
V41V2 = "lbq-v2-deepseek-v4-1-flash"
# prereg.yaml as the operator's lbq-v1-deepseek-v4-flash lane froze it (its first floor ran at a6e4784): never edited
V4_PREREG_SHA256 = "2c1f76f7e3feaeb2fd6cd86f5acc11722260f8fe38485effd98825f2cfb9eaa6"
PINS = {V41: ("opencode/deepseek-v4.1-flash#high", "lb-deepseek-v4.1-flash"),
        V41V2: ("opencode/deepseek-v4.1-flash#high", "lb-deepseek-v4.1-flash"),
        NANO: ("opencode/gpt-5-nano#high", "lb-gpt-5-nano")}


def plan_of(qualify, experiment: str) -> dict:
    return yaml.safe_load(qualify.EXPERIMENTS[experiment].read_text(encoding="utf-8"))


def profile_of(pid: str) -> dict:
    return next(r for r in yaml.safe_load((LANE / "profiles.yaml").read_text(encoding="utf-8")) if r["id"] == pid)


@pytest.fixture
def selected(qualify, monkeypatch):
    """``select`` for one test: the module's selection is restored afterwards."""
    monkeypatch.setattr(qualify, "PLAN", qualify.PLAN)
    monkeypatch.setattr(qualify, "FROZEN", qualify.FROZEN)
    return qualify.select


def test_the_first_experiment_is_unchanged(qualify):
    """lbq-v1-deepseek-v4-flash keeps its preregistration byte for byte, and its file names (its frozen record on
    the arm host is prereg.frozen.yaml), and stays the default."""
    import hashlib

    data = (LANE / "prereg.yaml").read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(data).hexdigest() == V4_PREREG_SHA256
    assert qualify.DEFAULT_EXPERIMENT == V4
    assert qualify.EXPERIMENTS[V4] == LANE / "prereg.yaml"
    assert qualify.frozen_path(qualify.EXPERIMENTS[V4]) == LANE / "prereg.frozen.yaml"
    assert (qualify.PLAN, qualify.FROZEN) == (LANE / "prereg.yaml", LANE / "prereg.frozen.yaml")


def test_each_experiment_has_its_own_preregistration_frozen_record_and_lane(qualify, selected):
    frozen = {e: qualify.frozen_path(p) for e, p in qualify.EXPERIMENTS.items()}
    assert sorted(qualify.EXPERIMENTS) == sorted([V4, V41, V41V2, NANO])
    assert len(set(frozen.values())) == len(frozen) == len(set(qualify.EXPERIMENTS.values()))
    for experiment in qualify.EXPERIMENTS:
        plan = plan_of(qualify, experiment)  # with the hashes freeze fills from the fetched fixture: placeholders
        for case in plan["cases"]:
            case.update(sha256="0" * 64, hidden_sha256="0" * 64)
        plan["scoring"]["rubric_sha256"] = "0" * 64
        qualify.validate("aew/eval-prereg/v1", plan, what=experiment)  # e.g. an experiment id has no dots
        assert selected(experiment) == experiment == plan_of(qualify, experiment)["experiment"]
        assert qualify.FROZEN == frozen[experiment]
        assert qualify.default_out(experiment).name == experiment  # its own lane directory by default
    with pytest.raises(qualify.Invalid, match="unknown experiment"):
        selected("lbq-v1-elsewhere")


@pytest.mark.parametrize("experiment", [V41, V41V2, NANO])
def test_a_new_experiment_pins_its_profile_and_changes_nothing_else(qualify, experiment):
    """Same cases, oracles, rubric, schedule seed, limits and budget as the first experiment: only the experiment id,
    its question, its amendment record and the profile pins differ (and V4.1's overshoot margin and expected outcome,
    for its step cost: review F1, F2)."""
    model, pid = PINS[experiment]
    plan, first = plan_of(qualify, experiment), plan_of(qualify, V4)
    config = plan["arms"][0]["config"]
    assert (config["model"], config["profile"]["id"], plan["profiles"]["roles"]["worker"]) == (model, pid, model)
    if experiment in (V41, V41V2):
        assert "expected to end ceiling runs before the 80-step limit" in plan["thresholds"]["expected_outcome"]
        assert "the operator's choice, for cost reasons" in plan["thresholds"]["expected_outcome"]
        assert "unobserved" in plan["amendment_policy"] and "cost reasons" in plan["amendment_policy"]
    for p in (plan, first):
        for key in ("experiment", "question", "amendment_policy"):
            p.pop(key)
        p["arms"][0]["config"]["model"] = p["arms"][0]["config"]["profile"]["id"] = None
        p["profiles"]["roles"]["worker"] = None
        if experiment in (V41, V41V2):
            p["thresholds"]["budget"].pop("overshoot_margin_usd")
            p["thresholds"].pop("expected_outcome")
    assert plan == first


def test_v4_1s_second_experiment_is_its_first_with_a_new_id_and_why(qualify):
    """lbq-v2-deepseek-v4-1-flash (the operator's Option A, 2026-10-10): lbq-v1-deepseek-v4-1-flash's preregistration
    with only its id and amendment record changed (the cost-cap decision and expected outcome carried over), sealed
    into its own frozen record and run in its own lane; the first stays as it was."""
    v2, v1 = plan_of(qualify, V41V2), plan_of(qualify, V41)
    amendment = v2["amendment_policy"]
    assert amendment.startswith(v1["amendment_policy"])  # everything v1 recorded, carried over
    for fact in ("aba5846 and a6e91d5", "CONTAINMENT_FAILED", "out/work", "no ceiling attempt reached a model",
                 "floor.json records $0.025", "the account's total Zen spend for 2026-10-10 on the Zen dashboard",
                 "kept untouched", "new experiment id"):
        assert fact in amendment, fact
    for wrong in ("Zen billed", "fixed in aba5846 (", "fixed in aba5846."):  # review F1 of a6e91d5
        assert wrong not in amendment, wrong
    assert v2["thresholds"]["expected_outcome"] == v1["thresholds"]["expected_outcome"]
    for p in (v2, v1):
        p.pop("experiment")
        p.pop("amendment_policy")
    assert v2 == v1
    seals = {qualify.frozen_path(qualify.EXPERIMENTS[e]).name for e in (V41, V41V2)}
    assert seals == {"prereg-deepseek-v4-1-flash.frozen.yaml", "prereg-v2-deepseek-v4-1-flash.frozen.yaml"}
    assert qualify.default_out(V41V2).name == V41V2


@pytest.mark.parametrize("experiment, margin", [(V4, 0.05), (V41, 0.10), (V41V2, 0.10), (NANO, 0.05)])
def test_every_experiment_keeps_the_lanes_budget(qualify, experiment, margin):
    plan = plan_of(qualify, experiment)
    budget = plan["thresholds"]["budget"]
    assert plan["profiles"]["budget_usd"] == budget["total_usd"] == 5.0
    assert budget["floor_cap_usd"] == 1.0
    assert budget["per_run_cap_usd"] == plan["arms"][0]["config"]["cap_usd"] == 0.75
    assert budget["overshoot_margin_usd"] == margin  # V4.1: a 15 s poll covers 2-3 steps at $0.02-0.03 (review F2)
    assert plan["thresholds"]["floor"]["trials"] == 2


def test_the_effort_rule_is_stated_as_the_pins_follow_it(qualify):
    """The highest tier, excluding an extended max tier (review F3): DeepSeek low/high/max -> high, Nano's
    minimal..high -> high; the sealed text says so, with its trade-off."""
    text = plan_of(qualify, NANO)["amendment_policy"]
    assert "excluding an extended max tier" in text and "below its provider's maximum tier" not in text
    assert "trade-off" in text
    assert "excluding an extended max tier" in profile_of("lb-gpt-5-nano")["availability"]["note"]


SEEDED_RUN = ("....F..\n======\nFAIL: test_spaces_in_a_label_become_hyphens (tests.test_syntax.extensions."
              "test_wikilinks_spaces.TestWikiLinkSpaces.test_spaces_in_a_label_become_hyphens)\n------\n"
              "FAILED (failures=1, skipped=110)\n")


def test_check_reports_the_seeded_distractors_failure_as_seeded_not_as_a_failure(qualify):
    """The upstream suite fails on the seeded start by design (the planted distractor test): `check` says so,
    against the expectation, and names a failure only when something else fails or the seed did not take."""
    got = qualify.suite_verdict(1, SEEDED_RUN)
    assert got["state"] == "as_seeded" and "unexpected_failures" not in got and "missing_seeded_failures" not in got
    assert got["raw"] == {"exit": 1, "summary": ["FAILED (failures=1, skipped=110)"],
                          "failing": ["test_spaces_in_a_label_become_hyphens"]}  # the unittest output, secondary
    other = SEEDED_RUN + "ERROR: test_markdown_in_html (tests.test_syntax.extensions.test_md_in_html.Test)\n"
    got = qualify.suite_verdict(1, other)
    assert (got["state"], got["unexpected_failures"]) == ("unexpected", ["test_markdown_in_html"])
    got = qualify.suite_verdict(0, "OK (skipped=110)\n")  # the seeded test passed: the seed did not take
    assert (got["state"], got["missing_seeded_failures"]) == ("unexpected", ["test_spaces_in_a_label_become_hyphens"])
    assert qualify.suite_verdict(1, "Traceback: ImportError\n")["state"] == "unexpected"  # no suite ran at all


@pytest.mark.parametrize("experiment, state", [(V4, "unqualified"), (V41V2, "floor_passed"), (NANO, "qualified")])
def test_every_experiment_pins_its_profile_as_the_record_states(qualify, selected, experiment, state):
    """A frozen experiment pins its profile's state as it was at preregistration (its committed frozen record), while
    the profile record moves on with the results; an unfrozen one must match the record as it stands."""
    selected(experiment)
    report: dict = {}
    qualify.check_profiles(report, plan_of(qualify, experiment))
    assert report["profiles"][PINS.get(experiment, (None, "lb-deepseek-v4-flash"))[1]] == state


def test_the_retired_first_v4_1_experiment_can_no_longer_be_frozen(qualify, selected):
    """lbq-v1-deepseek-v4-1-flash was never frozen in the repository (its seal stays on the arm host, its lane kept
    as the record of the containment failure); its plan pins the profile as unqualified, which the record no longer
    states, so freezing it now is refused."""
    selected(V41)
    with pytest.raises(qualify.Invalid, match="qualification_state"):
        qualify.check_profiles({}, plan_of(qualify, V41))


@pytest.mark.parametrize("experiment", [V41V2, NANO])
def test_each_runs_frozen_record_is_committed_and_seals_its_preregistration(qualify, selected, experiment):
    """The operator's runs (2026-10-10, at ed98424): each frozen record verifies, is exactly its committed
    preregistration plus what freeze adds, and is the seal its floor record was stamped with."""
    selected(experiment)
    frozen = qualify.frozen_record()
    plan = plan_of(qualify, experiment)
    by_id = {c["id"]: c for c in frozen["cases"]}
    for case in plan["cases"]:
        case.update(sha256=by_id[case["id"]]["sha256"], hidden_sha256=by_id[case["id"]]["hidden_sha256"])
    plan["scoring"]["rubric_sha256"] = frozen["scoring"]["rubric_sha256"]
    sealed = {k: v for k, v in frozen.items() if k not in ("frozen_at", "frozen_by", "canonical_sha256")}
    sealed["assignment"] = {k: v for k, v in sealed["assignment"].items() if k != "order"}
    assert sealed == plan
    floor = json.loads((LANE / "results" / experiment / "floor.json").read_text(encoding="utf-8"))
    assert (floor["experiment"], floor["preregistration_sha256"]) == (experiment, frozen["canonical_sha256"])


@pytest.mark.parametrize("experiment, shown, ceiling_state, spent", [
    (V41V2, [], "not_run (pending: the session-observable behaviours)", 0.2199),
    (NANO, ["requirement_loss_on_longer_tasks"], "behaviours_shown", 0.066),
])
def test_the_committed_results_are_the_runs_own_and_name_no_host_path(experiment, shown, ceiling_state, spent):
    """The results are the lane's floor and score summaries with only their absolute paths rewritten to the lane
    (``<lane>/...``); every hash, cost and verdict is the run's."""
    results = LANE / "results" / experiment
    text = "".join((results / f).read_text(encoding="utf-8") for f in ("floor.json", "score.json"))
    assert "/home/" not in text and ":\\\\" not in text
    floor = json.loads((results / "floor.json").read_text(encoding="utf-8"))
    score = json.loads((results / "score.json").read_text(encoding="utf-8"))
    paths = [t[k] for t in floor["trials"] for k in ("results", "session_state")]
    paths += [r["session_db"]["state_dir"] for r in score["runs"]]
    assert all(p.startswith("<lane>/") for p in paths), paths
    assert [t["verdict"] for t in floor["trials"]] == ["passed"]
    assert (score["valid_runs"], score["unscored"], score["tree_behaviours_shown"], score["ceiling_state"]) == \
        (6, [], shown, ceiling_state)
    assert all(r["finished"] for r in score["runs"])
    total = floor["charged_usd"] + sum(r["charged_usd"] for r in score["runs"])
    assert round(total, 4) == spent


def test_the_replacement_primary_has_a_stable_identity(qualify):
    """V4.1 is a versioned, released model the pinned harness offers (not an experimental or free id), pinned at the
    same effort as the profile it replaces; Nano is driven through the Responses API package."""
    v41, v4, nano = (profile_of(p) for p in ("lb-deepseek-v4.1-flash", "lb-deepseek-v4-flash", "lb-gpt-5-nano"))
    assert v41["plan_role"] == "replacement-primary" and v41["effort"] == v4["effort"] == "high"
    assert not any(tag in v41["model"] for tag in ("-exp", "free", "preview"))
    assert v41["availability"] | {"note": None} == {
        "checked_at": "2026-10-10", "offered_by_pinned_harness": True, "catalog_status": "active",
        "checked_with": v4["availability"]["checked_with"], "note": None}
    assert (v41["cost_per_mtok_usd"]["input"], v41["cost_per_mtok_usd"]["output"],
            v41["cost_per_mtok_usd"]["cache_read"]) == (0.30, 1.20, 0.006)
    assert nano["effort"] == "high" and nano["availability"]["offered_by_pinned_harness"] is True
    assert "Responses API" in nano["availability"]["note"]
    assert v4["qualification_state"] == "unqualified" and "Unavailable on OpenCode Zen" in v4["notes"]


def test_a_lane_directory_holds_one_experiment(qualify, tmp_path):
    fresh = tmp_path / "lbq-v1-deepseek-v4-1-flash" / "out"
    qualify.claim_lane(fresh, V41, explicit=True)
    qualify.claim_lane(fresh, V41, explicit=False)  # its own again, marked: the flag is not needed
    assert (fresh / qualify.LANE_MARK).read_text(encoding="utf-8").strip() == V41
    with pytest.raises(SystemExit, match="holds the runs of lbq-v1-deepseek-v4-1-flash"):
        qualify.claim_lane(fresh, NANO, explicit=True)
    first = tmp_path / "lbq-v1" / "out"  # the first experiment's legacy lane, from before the mark existed
    (first / "floor").mkdir(parents=True)
    (first / "floor" / "floor.json").write_text(json.dumps({"trials": [], "charged_usd": 0.0}), encoding="utf-8")
    with pytest.raises(SystemExit, match="holds the runs of lbq-v1-deepseek-v4-flash"):
        qualify.claim_lane(first, V41, explicit=True)
    qualify.claim_lane(first, V4, explicit=False)


def test_an_unmarked_lane_is_claimed_only_by_name_or_as_the_legacy_shape(qualify, tmp_path):
    """Review F4 and N4: a forgotten --experiment never marks a fresh lane, and a lane whose mark is gone is never
    read as the first experiment's unless it has the legacy shape (an unstamped floor record and no ledger)."""
    fresh = tmp_path / "fresh" / "out"
    with pytest.raises(SystemExit, match="name the experiment"):
        qualify.claim_lane(fresh, V4, explicit=False)
    assert not (fresh / qualify.LANE_MARK).exists()
    lost = tmp_path / "lost" / "out"  # a V4.1 lane whose mark was deleted: its floor record is stamped
    (lost / "floor").mkdir(parents=True)
    (lost / "floor" / "floor.json").write_text(json.dumps({"trials": [], "charged_usd": 0.0, "experiment": V41,
                                                           "preregistration_sha256": "b" * 64}), encoding="utf-8")
    for experiment, explicit in ((V4, False), (V4, True), (V41, True)):
        with pytest.raises(SystemExit, match="holds runs but no experiment.txt"):
            qualify.claim_lane(lost, experiment, explicit=explicit)
    ledgered = tmp_path / "ledgered" / "out"  # unstamped floor, but a ledger: not the legacy shape
    (ledgered / "floor").mkdir(parents=True)
    (ledgered / "ledger").mkdir()
    (ledgered / "floor" / "floor.json").write_text(json.dumps({"trials": []}), encoding="utf-8")
    with pytest.raises(SystemExit, match="holds runs but no experiment.txt"):
        qualify.claim_lane(ledgered, V4, explicit=False)


def test_a_floor_record_of_another_experiment_is_refused(qualify, tmp_path):
    out = tmp_path / "out"
    (out / "floor").mkdir(parents=True)
    path = out / "floor" / "floor.json"
    mine = {"experiment": V41, "canonical_sha256": "b" * 64}
    path.write_text(json.dumps({"trials": [], "charged_usd": 0.0, "experiment": V41,
                                "preregistration_sha256": "b" * 64}), encoding="utf-8")
    assert qualify.floor_state(out, mine)["experiment"] == V41
    with pytest.raises(SystemExit, match="is the floor record of lbq-v1-deepseek-v4-1-flash"):
        qualify.floor_state(out, {"experiment": NANO, "canonical_sha256": "c" * 64})
    with pytest.raises(SystemExit, match="is the floor record of"):  # same experiment, another seal
        qualify.floor_state(out, {"experiment": V41, "canonical_sha256": "d" * 64})
    path.write_text(json.dumps({"trials": [], "charged_usd": 0.0}), encoding="utf-8")  # unstamped: legacy V4 only
    assert qualify.floor_state(out, {"experiment": V4, "canonical_sha256": "a" * 64})["trials"] == []
    with pytest.raises(SystemExit, match="unstamped"):
        qualify.floor_state(out, mine)


def test_every_floor_save_is_stamped_with_its_experiment(qualify, lane):
    lane.runs.append(FAILING_RUN)
    lane.runs.append(FAILING_RUN)
    assert lane.floor() == 3
    state = lane.state()
    assert (state["experiment"], state["preregistration_sha256"]) == (V4, "a" * 64)


def test_run_refuses_a_forgotten_experiment_before_it_writes_anything(qualify, monkeypatch, tmp_path):
    """Review N1 of b924e47: no fetch, check or freeze (no stray seal) when the lane would be refused."""
    for step in ("cmd_fetch", "cmd_check", "cmd_freeze", "cmd_floor", "cmd_ceiling"):
        monkeypatch.setattr(qualify, step, lambda *a, step=step, **k: pytest.fail(f"{step} ran"))
    monkeypatch.setattr(qualify, "EXPLICIT", False)
    out = tmp_path / "lane" / "out"
    with pytest.raises(SystemExit, match="name the experiment"):
        qualify.cmd_run(SimpleNamespace(by="operator"), out, None)
    assert not out.exists()


def test_purge_works_only_on_its_own_experiments_lane(qualify, monkeypatch, tmp_path):
    out = tmp_path / "out"
    qualify.claim_lane(out, V41, explicit=True)
    monkeypatch.setattr(qualify, "frozen_record", lambda: {"experiment": NANO})
    monkeypatch.setattr(qualify.retention, "purge", lambda *a, **k: pytest.fail("purged another experiment's lane"))
    with pytest.raises(SystemExit, match="holds the runs of lbq-v1-deepseek-v4-1-flash"):
        qualify.cmd_purge(SimpleNamespace(), out)


def test_another_lanes_oracle_copy_stops_every_model_step(qualify, tmp_path):
    out = tmp_path / "lanes" / "lbq-v1-gpt-5-nano" / "out"
    out.mkdir(parents=True)
    other = tmp_path / "lanes" / "lbq-v1-deepseek-v4-1-flash"
    (other / "out").mkdir(parents=True)
    qualify.arm_host_clean(out, None)
    (other / "hidden").mkdir()
    with pytest.raises(SystemExit, match="another lane's oracle copy"):
        qualify.arm_host_clean(out, None)


def test_a_run_the_cost_cap_ended_leaves_behaviours_4_and_5_unobserved(qualify, rules):
    """Review F1: a truncated run records behaviours 4 and 5 as None (unobserved), never False; with no finished run
    of their case they are reported unobserved; a cost-capped run records the step at which the cap ended it."""
    capped = record("LBQ-2", ["markdown/extensions/linkpolicy/__init__.py"], ended="cost_cap", truncated=True)
    capped["outcome"].update(truncated_why=["turn:cost_cap"], steps=31)
    got = qualify.tree_behaviours(capped, rules, {})
    assert got["incomplete_cross_file_changes"] is None
    lbq3 = qualify.tree_behaviours(record("LBQ-3", [], truncated=True), rules, CRITERIA)
    assert lbq3["requirement_loss_on_longer_tasks"] is None
    assert qualify.cost_cap_step(capped) == 31
    assert qualify.cost_cap_step(record("LBQ-1", [])) is None
    runs = [{"behaviours": got}, {"behaviours": lbq3}, {"behaviours": None}]
    assert qualify.unobserved(runs) == ["incomplete_cross_file_changes", "requirement_loss_on_longer_tasks"]
    done = qualify.tree_behaviours(record("LBQ-2", ["markdown/extensions/linkpolicy/__init__.py"]), rules, {})
    assert done["incomplete_cross_file_changes"] is True
    assert qualify.unobserved([*runs, {"behaviours": done}]) == ["requirement_loss_on_longer_tasks"]


def test_a_frozen_record_of_another_experiment_is_refused(qualify, selected, monkeypatch, tmp_path):
    selected(V41)
    sealed = tmp_path / "prereg-deepseek-v4-1-flash.frozen.yaml"
    sealed.write_text(yaml.safe_dump({"experiment": V4}), encoding="utf-8")
    monkeypatch.setattr(qualify, "FROZEN", sealed)
    monkeypatch.setattr(qualify.prereg, "verify", lambda frozen: "sealed")
    with pytest.raises(SystemExit, match="seals 'lbq-v1-deepseek-v4-flash', not 'lbq-v1-deepseek-v4-1-flash'"):
        qualify.frozen_record()
