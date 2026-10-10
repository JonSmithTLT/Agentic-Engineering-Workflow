"""The raw arm end to end, through the real headless session and a fake OpenCode server (register F19; agent-
effectiveness adoption, delta D3).

A preregistered raw cell builds the case, starts a private OpenCode server (the pinned binary only), sends the case's
task as the only message, lets the scripted "model" edit the work tree, and finalizes one record: the observed model
checked against the pinned one, the work tree's changes, the harness's identity, and where the run's harness state is
kept with the date its retention ends. A provider variable reaches only the server; a value of it found in retained
state makes the measurement invalid and the files holding it are deleted at once. A session that fails after it
started still records its database, its leak scan and a conservative cost. On Linux the run can be contained: its
OpenCode tree runs in bubblewrap with every other run and everything beside the lane's state hidden.
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

from aew_eval import fixture, prereg, raw, runner  # noqa: E402

TASK = "calc.py's add() subtracts. Make it add. Nobody will answer questions during this session."
FIXED = "def add(a, b):\n    return a + b\n"
FIELDS = [{"field": "tool.name", "transform": "none"}, {"field": "tool.state.input.command", "transform": "prefix_300"}]
EFFECTIVE = [{"provider": "fakeprov", "model": "fake-model", "effort": "high"}]


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
        "profiles": {"roles": {"worker": "fakeprov/fake-model#high"}, "budget_usd": 1.0},
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
    """The fake OpenCode as the pinned harness binary, and the raw configuration that pins it."""
    scripts = tmp_path / "bin" / "scripts"  # beside the launcher: a contained run sees the binary's directory only
    scripts.mkdir(parents=True)
    launcher = fake_opencode.write_launcher(tmp_path / "bin", scripts)
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(launcher))
    config = {"role": "worker", "model": "fakeprov/fake-model#high", "steps": 5, "cap_usd": 0.5, "provider_env": [],
              "contain": False,
              "profile": {"id": "lb-demo", "qualification_state": "unqualified",
                          "effective_profile": {"context.orientation": None, "tools.presentation": None}},
              "harness": {"name": "opencode", "version": "2.0.18",
                          "artifact_sha256": {raw.host_platform(): raw._sha256_file(launcher)}},  # noqa: SLF001
              "session_db": {"retain": True, "retention_days": 30, "fields": FIELDS}}
    return scripts, config


def script(scripts: Path, steps: list, effective: list | None = None) -> None:
    (scripts / "default.json").write_text(json.dumps({"steps": steps, "effective": effective or EFFECTIVE}),
                                          encoding="utf-8")


def run_raw(tmp_path: Path, config: dict, *, work: Path | None = None, run_name: str = "r1") -> dict:
    case_path = make_case(tmp_path / "case")
    f = frozen(case_path, config)
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=work or tmp_path / "work", run_name=run_name,
                           deadline_s=120,
                           scorer=lambda tree: {"passed": (tree / "calc.py").read_text(encoding="utf-8") == FIXED})


def test_a_raw_cell_runs_the_pinned_model_on_the_task_and_keeps_its_harness_state(tmp_path, fake_server):
    scripts, config = fake_server
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED}}])
    record = run_raw(tmp_path, config)
    assert record["validity"] == {"status": "valid", "reason_code": None}, record["outcome"]
    assert record["profile"]["mismatch"] is False
    assert record["profile"]["observed"] == [{"role": "worker", "provider": "fakeprov", "model": "fake-model",
                                              "effort": "high"}]
    out = record["outcome"]
    assert out["changed_paths"] == ["calc.py"] and out["score"] == {"passed": True}
    assert out["harness_outcome"] == "ended" and out["provider_key_files"] == [] and out["arm_error"] is None
    assert out["model_steps"] >= 1 and out["errored_steps"] == 0 and out["truncated"] is False
    db = out["session_db"]
    assert db["retain_until"] and db["fields"] == FIELDS
    assert Path(db["state_dir"]) == (tmp_path / "work" / "r1" / "harness").resolve()
    assert record["harness"]["version"] == "2.0.18" == record["harness"]["pinned_version"]
    assert record["cost"]["charged_usd"] is not None
    scratch = tmp_path / "work" / "r1"
    started = json.loads((scratch / "harness" / "harness" / "fake-server.json").read_text(encoding="utf-8"))
    assert started["config"]["agents"]["build"]["model"] == {"providerID": "fakeprov", "model": "fake-model",
                                                             "variant": "high"}
    transcript = (scratch / "harness" / "harness" / "xdg-data" / "opencode" / "fake-db.json").read_text(
        encoding="utf-8")
    assert TASK in transcript  # the task, verbatim, was the session's message


def test_a_raw_run_on_a_model_it_did_not_pin_is_counted_as_invalid(tmp_path, fake_server):
    scripts, config = fake_server
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED}}],
           effective=[{"provider": "other", "model": "cheaper-model"}])
    record = run_raw(tmp_path, config)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "PROFILE_MISMATCH"}


def test_a_provider_value_reaches_only_the_server_and_retained_state_holding_it_is_deleted(tmp_path, fake_server,
                                                                                          monkeypatch):
    scripts, config = fake_server
    secret = "sk-test-provider-value-0123456789"
    monkeypatch.setenv("FAKEPROV_TEST_KEY", secret)
    # The scripted "model" writes the value into the work tree, as a leak would: the record says so.
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED, "notes.txt": f"key={secret}\n"}}])
    record = run_raw(tmp_path, {**config, "provider_env": ["FAKEPROV_TEST_KEY"]})
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "PROVIDER_KEY_RETAINED"}
    assert "repo/notes.txt" in record["outcome"]["provider_key_files"]
    assert record["outcome"]["provider_key_files_purged"] == record["outcome"]["provider_key_files"]
    assert not (tmp_path / "work" / "r1" / "repo" / "notes.txt").exists()  # deleted at once, not kept 180 days
    started = json.loads((tmp_path / "work" / "r1" / "harness" / "harness" / "fake-server.json").read_text(
        encoding="utf-8"))
    assert "FAKEPROV_TEST_KEY" in started["env_names"]  # the server has it; the agent's shell never did
    assert secret not in json.dumps(record)
    assert os.environ["FAKEPROV_TEST_KEY"] == secret


def test_a_session_that_fails_after_it_started_still_records_its_database_leak_scan_and_cost(tmp_path, fake_server,
                                                                                           monkeypatch):
    """Review finding 5: the arm raising must not lose the retention entry, the leak scan or the cost, so the
    budget never undercounts a run."""
    scripts, config = fake_server
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED}}])
    real = raw._headless  # noqa: SLF001

    def failing_headless():
        module = real()

        class Failing(module.HeadlessSession):
            def wait_turn(self, deadline, tick=None):
                raise ConnectionError("the server went away mid-turn")

        module.HeadlessSession = Failing
        return module

    monkeypatch.setattr(raw, "_headless", failing_headless)
    record = run_raw(tmp_path, config)
    assert record["validity"] == {"status": "invalid_measurement", "reason_code": "ARM_ERROR"}
    out = record["outcome"]
    assert "the server went away" in out["arm_error"]
    assert out["session_db"]["retain_until"] and out["session_db"]["state_dir"]
    assert out["provider_key_files"] == []
    reported = record["cost"]["provider_reported_usd"]
    assert record["cost"]["charged_usd"] == (reported if reported is not None else config["cap_usd"])


def test_on_linux_a_contained_raw_run_sees_only_its_own_state(tmp_path, fake_server, monkeypatch):
    """The whole OpenCode tree runs in bubblewrap: its writable roots are the work tree and its harness state, every
    other run and everything beside the lane's run state is hidden, and both are verified before OpenCode starts."""
    if not sys.platform.startswith("linux"):
        pytest.skip("bubblewrap containment is Linux-only; Windows refuses a contained raw arm (tested)")
    scripts, config = fake_server
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "private").mkdir(parents=True)
    (tmp_path / "home" / "private" / "oracle.txt").write_text("hidden material\n", encoding="utf-8")
    (tmp_path / "work" / "other-run").mkdir(parents=True)
    (tmp_path / "work" / "other-run" / "transcript.txt").write_text("another run\n", encoding="utf-8")
    (tmp_path / "work" / ".r1.aew-mask").write_bytes(b"")  # left by an earlier layout of the same run name
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED}}])
    record = run_raw(tmp_path, {**config, "contain": True})
    assert record["validity"]["status"] == "valid", record["outcome"]
    containment = record["outcome"]["containment"]
    assert containment["contained"] and containment["ok"], containment
    assert containment["hidden_dirs"] >= 1  # the home directory's private entry, at least
    assert containment["design_files_checked"] >= 5  # the lane's manifests, rubric and behaviours: unreadable
    assert record["outcome"]["changed_paths"] == ["calc.py"]  # the work tree stayed writable
    assert (tmp_path / "work" / "other-run" / "transcript.txt").read_text(encoding="utf-8") == "another run\n"


def test_on_linux_a_lane_under_home_contains_each_run_beside_its_earlier_runs(tmp_path, fake_server, monkeypatch):
    """The arm host's real layout, which the test above missed (its work directory is outside its home, so the home
    scan never lists the other runs): <home>/aew-eval/<experiment>/out/work/<run>, with an earlier run, its mask file
    and a check's leftover mask beside this run, and another experiment's lane beside this lane. At b924e47 every
    attempt after the first failed CONTAINMENT_FAILED ("hidden paths visible from inside: [.../out/work]")."""
    if not sys.platform.startswith("linux"):
        pytest.skip("bubblewrap containment is Linux-only; Windows refuses a contained raw arm (tested)")
    scripts, config = fake_server
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    out = home / "aew-eval" / "lbq-v1-deepseek-v4-1-flash" / "out"
    work = out / "work"
    (work / "LBQ-2-raw-2" / "repo").mkdir(parents=True)
    (work / "LBQ-2-raw-2" / "repo" / "transcript.txt").write_text("another run\n", encoding="utf-8")
    (work / ".LBQ-2-raw-2.aew-mask").write_bytes(b"")
    (work / ".containment-check.aew-mask").write_bytes(b"")
    (out / "floor").mkdir()
    (out / "floor" / "floor.json").write_text("{}", encoding="utf-8")
    (home / "aew-eval" / "lbq-v1" / "out" / "floor").mkdir(parents=True)
    script(scripts, [{"do": "write", "files": {"calc.py": FIXED}}])
    record = run_raw(tmp_path, {**config, "contain": True}, work=work, run_name="LBQ-3-raw-1")
    containment = record["outcome"]["containment"]
    assert containment["ok"], containment
    assert record["validity"]["status"] == "valid", record["outcome"]
    assert record["outcome"]["launched"] is True
    assert record["outcome"]["changed_paths"] == ["calc.py"]
