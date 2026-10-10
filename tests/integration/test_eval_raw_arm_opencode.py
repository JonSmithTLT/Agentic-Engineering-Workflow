"""The raw arm end to end, through the real headless session and a fake OpenCode server (register F19; agent-
effectiveness adoption, delta D3).

A preregistered raw cell builds the case, starts a private OpenCode server, sends the case's task as the only
message, lets the scripted "model" edit the work tree, and finalizes one record: the observed model checked against
the pinned one, the work tree's changes, the harness's identity, and where the run's harness state is kept with the
date its retention ends. A provider variable reaches only the server, and a value of it found in retained state makes
the measurement invalid.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import fake_opencode
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import fixture, prereg, runner  # noqa: E402

TASK = "calc.py's add() subtracts. Make it add. Nobody will answer questions during this session."
FIXED = "def add(a, b):\n    return a + b\n"
RAW = {"role": "worker", "model": "fakeprov/fake-model", "steps": 5, "cap_usd": 0.5, "provider_env": [],
       "session_db": {"retain": True, "retention_days": 30, "fields": ["tool.name", "tool.input.path"]}}


def make_case(root: Path) -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": "C1", "family": "demo", "task": TASK,
                "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def frozen(case_path: Path, config: dict) -> dict:
    case = fixture.load(case_path)
    return prereg.freeze({
        "schema": "aew/eval-prereg/v1", "experiment": "lbq-demo", "question": "Does the raw arm run?",
        "purpose": "qualification",
        "arms": [{"id": "raw", "kind": "raw", "description": "harness alone", "config": config}],
        "cases": [{"id": "C1", "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": {"worker": "fakeprov/fake-model"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "runs", "metrics": [{"name": "runs", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 0, "allowed_for": []},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id",
    }, by="tester")


@pytest.fixture
def fake_server(tmp_path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(fake_opencode.write_launcher(tmp_path / "bin", scripts)))
    return scripts


def run_raw(tmp_path: Path, config: dict) -> dict:
    case_path = make_case(tmp_path / "case")
    f = frozen(case_path, config)
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name="r1", deadline_s=120,
                           scorer=lambda tree: {"passed": (tree / "calc.py").read_text(encoding="utf-8") == FIXED})


def test_a_raw_cell_runs_the_pinned_model_on_the_task_and_keeps_its_harness_state(tmp_path, fake_server):
    (fake_server / "default.json").write_text(json.dumps({
        "steps": [{"do": "write", "files": {"calc.py": FIXED}}],
        "effective": [{"provider": "fakeprov", "model": "fake-model"}]}), encoding="utf-8")
    record = run_raw(tmp_path, RAW)
    assert record["validity"] == {"status": "valid", "reason_code": None}, record["outcome"]
    assert record["profile"]["mismatch"] is False
    assert record["profile"]["observed"] == [{"role": "worker", "provider": "fakeprov", "model": "fake-model",
                                              "effort": None}]
    out = record["outcome"]
    assert out["changed_paths"] == ["calc.py"] and out["score"] == {"passed": True}
    assert out["harness_outcome"] == "ended" and out["provider_key_files"] == []
    assert out["session_db"]["retain_until"] and out["session_db"]["fields"] == RAW["session_db"]["fields"]
    assert record["harness"]["name"] == "opencode" and record["harness"]["agent"] == "build"
    assert record["harness"]["version"] == "2.0.18"
    scratch = tmp_path / "work" / "r1"
    started = json.loads((scratch / "harness" / "harness" / "fake-server.json").read_text(encoding="utf-8"))
    assert started["config"]["agents"]["build"]["model"] == {"providerID": "fakeprov", "model": "fake-model"}
    transcript = (scratch / "harness" / "harness" / "xdg-data" / "opencode" / "fake-db.json").read_text(
        encoding="utf-8")
    assert TASK in transcript  # the task, verbatim, was the session's message
    assert (scratch / "harness").is_dir()  # the run's harness state is kept with its scratch directory


def test_a_raw_run_on_a_model_it_did_not_pin_is_counted_as_invalid(tmp_path, fake_server):
    (fake_server / "default.json").write_text(json.dumps({
        "steps": [{"do": "write", "files": {"calc.py": FIXED}}],
        "effective": [{"provider": "other", "model": "cheaper-model"}]}), encoding="utf-8")
    record = run_raw(tmp_path, RAW)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "PROFILE_MISMATCH"}


def test_a_provider_value_reaches_only_the_server_and_retained_state_holding_it_is_invalid(tmp_path, fake_server,
                                                                                          monkeypatch):
    secret = "sk-test-provider-value-0123456789"
    monkeypatch.setenv("FAKEPROV_TEST_KEY", secret)
    # The scripted "model" writes the value into the work tree, as a leak would: the record says so.
    (fake_server / "default.json").write_text(json.dumps({
        "steps": [{"do": "write", "files": {"calc.py": FIXED, "notes.txt": f"key={secret}\n"}}],
        "effective": [{"provider": "fakeprov", "model": "fake-model"}]}), encoding="utf-8")
    record = run_raw(tmp_path, {**RAW, "provider_env": ["FAKEPROV_TEST_KEY"]})
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "PROVIDER_KEY_RETAINED"}
    assert "repo/notes.txt" in record["outcome"]["provider_key_files"]
    started = json.loads((tmp_path / "work" / "r1" / "harness" / "harness" / "fake-server.json").read_text(
        encoding="utf-8"))
    assert "FAKEPROV_TEST_KEY" in started["env_names"]  # the server has it; the agent's shell never did
    assert secret not in json.dumps(record)
    assert os.environ["FAKEPROV_TEST_KEY"] == secret
