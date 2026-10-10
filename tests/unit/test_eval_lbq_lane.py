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
