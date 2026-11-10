"""Every launch route carries its context's marker (``AEW_CONTEXT``, G3 addendum 7; #321 review, F6): the register
of weaker contexts' scan finds a context's processes by it. Each owner the launch census names as entering the register
has a test that sees its context's processes given the marker; this module pins that list against the census, both
ways, and holds the headless OpenCode server's route itself (the worker's server is held in
``test_usage_live_run.py``)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from aew.harness import weaker_register as W
from aew.util import load_yaml

REPO = Path(__file__).resolve().parents[2]

DOCTOR_READ = "src/aew/harness/model_list.py::read"
DOCTOR_READ_OWNER = "src/aew/harness/supervisor.py::contain_launch"

# Each owner that enters the register (the census's registered_by and weaker_registered_by), with the tests that see
# its contexts' processes given the marker: one per context, where an owner has several.
ROUTES = {
    "eval/aew_eval/hidden.py::score":
        "tests/unit/test_eval_hidden.py::test_a_scorer_is_live_in_the_register_of_weaker_contexts_while_it_runs",
    "eval/aew_eval/raw.py::RawArm.run":
        "tests/integration/test_eval_raw_arm_opencode.py::"
        "test_a_raw_arm_is_live_in_the_register_of_weaker_contexts_while_it_runs",
    "eval/experiments/lower-bound-qualification/qualify.py::floor_trial":
        "tests/unit/test_eval_lbq_lane.py::test_the_live_lane_is_live_in_the_register_while_its_trial_runs",
    "eval/m3/dogfood/dogfood.py::debrief_run":
        "tests/unit/test_dogfood_register.py::test_the_dogfoods_debrief_is_live_in_the_register_while_its_model_answers",
    "eval/m3/dogfood/dogfood.py::hidden":
        "tests/unit/test_dogfood_register.py::test_the_dogfoods_hidden_scorer_is_live_in_the_register_while_it_scores",
    "eval/m3/dogfood/dogfood.py::run":
        "tests/unit/test_dogfood_register.py::test_the_dogfoods_raw_arm_is_live_in_the_register_while_its_model_runs",
    "src/aew/engine/evidence_ops.py::EvidenceCommands._check_run_direct":
        "tests/unit/test_check_run_contained.py::"
        "test_where_the_policy_allows_it_a_weaker_check_runs_labelled_and_live_in_the_register",
    "src/aew/engine/validation_ops.py::Validation._execute":
        "tests/integration/test_validation_checks.py::test_a_weaker_validation_run_is_live_in_the_register_while_its_checks_run",
    "src/aew/harness/lead_broker.py::WeakerLead.__call__":
        "tests/integration/test_lead_uncontained.py::"
        "test_under_allow_weaker_the_general_command_runs_labelled_with_its_label_and_a_live_entry",
    "src/aew/harness/opencode/lead.py::ContainedLead.__call__":
        "tests/unit/test_lead_contained.py::test_a_contained_lead_on_the_hosts_network_is_live_in_the_register_while_it_runs",
    "src/aew/harness/check_changes.py::run_once":
        "tests/unit/test_doctor_check_register.py::"
        "test_a_weaker_doctor_check_is_live_in_the_register_while_it_runs_and_carries_the_marker",
    # A run's supervisor and doctor's read of the model list share it (register E153). `model_list.read` is not an owner
    # of its own: it enters the register through this one, so the census names this one for it.
    DOCTOR_READ_OWNER: (
        "tests/integration/test_harness_runs.py::"
        "test_a_weaker_run_is_live_in_the_register_while_its_harness_runs_and_its_agent_carries_the_marker",
        "tests/unit/test_doctor_model_list_read.py::"
        "test_a_weaker_model_list_read_is_live_in_the_register_while_it_runs_and_its_server_carries_the_marker"),
}


def test_every_owner_the_census_names_has_a_test_that_sees_its_marker_and_the_test_exists():
    table = load_yaml((REPO / "tests/launch-census.yaml").read_text(encoding="utf-8"), source="launch-census.yaml")
    owners = {o for r in table["starts"] for f in ("registered_by", "weaker_registered_by") for o in r.get(f) or []}
    assert set(ROUTES) == owners
    # The owner with two contexts keeps a test for each (review of E137, F6): doctor's read is its census row's own.
    [read] = [r for r in table["starts"] if r["site"] == DOCTOR_READ]
    assert read["weaker_registered_by"] == [DOCTOR_READ_OWNER]
    assert sum("test_doctor_model_list_read.py::" in test for test in ROUTES[DOCTOR_READ_OWNER]) == 1
    assert sum("test_harness_runs.py::" in test for test in ROUTES[DOCTOR_READ_OWNER]) == 1
    for owner, tests in ROUTES.items():
        assert tests, f"{owner}: names no test"
        for test in (tests,) if isinstance(tests, str) else tests:
            path, _, name = test.partition("::")
            text = (REPO / path).read_text(encoding="utf-8")
            assert re.search(rf"^def {re.escape(name)}\(", text, re.M), f"{owner}: {test} does not exist"
            # Past its signature: a test named for the marker would otherwise pass on its own name (of E137, N1).
            body = text[text.index(f"def {name}("):]
            body = body[body.index("):\n"):]
            body = body[:m.start()] if (m := re.search(r"^def ", body, re.M)) else body
            assert "marker" in body.lower(), f"{owner}: {test} never looks at the marker"


@pytest.fixture
def headless(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / "eval" / "m3" / "dogfood"))
    import headless as module

    return module


@pytest.mark.parametrize("marked", [True, False])
def test_the_headless_sessions_server_carries_its_contexts_marker(headless, monkeypatch, tmp_path, marked):
    """The dogfood's raw arm, its debrief and eval's raw arm run their model through this session: its server is given
    the marker its shell environment carries, so the server and all it starts carry it too."""
    given = {}

    class Stop(Exception):
        pass

    def start(spawn, command, *, env, **_):
        given.update(env)
        raise Stop

    monkeypatch.setattr(headless.Server, "start", start)
    monkeypatch.setattr(headless.oc, "binary_command", lambda: ["opencode"])
    session = headless.HeadlessSession(tmp_path / "state")
    shell = {W.MARKER: str(tmp_path / "entry.json")} if marked else {}
    with pytest.raises(Stop):
        session.open(directory=tmp_path, profile={"provider": "p", "model": "m"}, agent="build", config={},
                     env=shell, provider_env=[])
    assert given.get(W.MARKER) == shell.get(W.MARKER)
    assert "headless" in sys.modules
