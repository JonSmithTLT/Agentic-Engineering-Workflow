"""Test the installed kit's seed, pin, launch arguments, and receipt."""

from __future__ import annotations

import fnmatch
import json
import os
import socket
import subprocess
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

import pytest

from aew.engine.conflicts import overlapping_scopes
from aew.errors import UsageError
from aew.harness import runlog
from aew.harness.containment import netns
from aew.kit import CHECK_COMMAND, DATES_SCOPE, MONEY_SCOPE, OPENING_REQUEST, git, launch_argv, prepare
from aew.kit import __main__ as kit_main
from aew.kit import receipt as receipt_module
from aew.kit.receipt import FIELDS, SCHEMA, write_receipt
from aew.policy.checks import PYTEST_CACHES
from aew.policy.execution import pack_slices

MODEL = "openai/worker-model"
LEAD_MODEL = "openai/lead-model"
FIX_A = {
    "ledger/money.py": "def format_amount(cents):\n    return f\"{'-' if cents < 0 else ''}${abs(cents) / 100:.2f}\"\n",
    "tests/unit/test_money.py": "from ledger.money import format_amount\n\ndef test_refund():\n"
                               "    assert format_amount(-125) == '-$1.25'\n",
}
FIX_B = {
    "ledger/dates.py": "def format_date(day):\n    return f\"{day.month:02d}/{day.day:02d}/{day.year}\"\n",
    "tests/unit/test_dates.py": "from datetime import date\nfrom ledger.dates import format_date\n"
                               "\ndef test_date():\n    assert format_date(date(2026, 3, 17)) == '03/17/2026'\n",
}


def seed_files(repo, values):
    for name, text in values.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def run(repo, *args):
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return subprocess.run([sys.executable, "-B", *args], cwd=repo, env=env, text=True, capture_output=True, timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def pytest_check(repo, path):
    result = run(repo, "-m", "pytest", "-q", path)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    return result.returncode


def lint(repo):
    result = run(repo, "tools/lint.py")
    assert result.returncode == 1 and not result.stderr
    assert result.stdout.splitlines() == ["ledger/dates.py:5: unfinished marker"]
    return result.stdout


def test_seed_probes_scope_and_width(tmp_path):
    seed = json.loads(files("aew.kit").joinpath("seed.json").read_bytes())
    seed_files(tmp_path, seed)
    assert pytest_check(tmp_path, "tests/unit") == pytest_check(tmp_path, "tests/neighbour") == 0
    seeded_lint = lint(tmp_path)
    seed_files(tmp_path, FIX_B)
    assert pytest_check(tmp_path, "tests/unit") == pytest_check(tmp_path, "tests/neighbour") == 0
    seed_files(tmp_path, {name: seed[name] for name in FIX_B})
    seed_files(tmp_path, FIX_A)
    assert lint(tmp_path) == seeded_lint
    seed_files(tmp_path, FIX_B)
    assert pytest_check(tmp_path, "tests/unit") == 0
    assert pytest_check(tmp_path, "tests/neighbour") == 1


def test_request_names_two_disjoint_reference_scopes():
    assert not overlapping_scopes(MONEY_SCOPE, DATES_SCOPE)
    for path in (*MONEY_SCOPE, *DATES_SCOPE):
        assert path in OPENING_REQUEST
    assert set(MONEY_SCOPE) == set(FIX_A)
    assert set(DATES_SCOPE) == set(FIX_B)


def test_prepare_pins_the_model_check_and_slices_and_owns_seed_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "synthetic must not reach commit")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "aew-test@invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "synthetic must not reach commit")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "aew-probe@invalid")
    engine = prepare(tmp_path, MODEL, LEAD_MODEL)
    policy, _ = engine.execution_policy()
    assert pack_slices(policy) == "structural"
    [profile] = policy["profiles"].values()
    assert profile["model"] == MODEL
    assert engine.policy("gates")["mutating_concurrency"] == 2
    unit = engine.policy("checks")["checks"]["unit"]
    assert unit["command"] == CHECK_COMMAND.split()
    assert unit["caches"] == list(PYTEST_CACHES)
    identity = git(tmp_path / "repo", "log", "-1", "--format=%an <%ae>%n%cn <%ce>")
    assert identity.splitlines() == ["AEW Kit <kit@example.invalid>"] * 2
    assert git(tmp_path / "repo", "rev-list", "--count", "HEAD") == "1"


@pytest.mark.parametrize(("model", "lead", "message"), [
    (None, LEAD_MODEL, "--model is required"),
    (MODEL, None, "--lead-model is required"),
    ("openai/model-free", LEAD_MODEL, "a -free id"),
    (MODEL, "openai/model-free", "a -free id"),
])
def test_prepare_refuses_absent_or_free_model_ids(tmp_path, model, lead, message):
    with pytest.raises(UsageError, match=message):
        prepare(tmp_path, model, lead)
    assert not (tmp_path / "repo").exists()


def test_prepare_requires_a_selected_first_map(tmp_path, monkeypatch):
    monkeypatch.setattr("aew.kit.first_map", lambda engine: {"selected": False, "reason": "no_commit"})
    with pytest.raises(UsageError, match="no_commit"):
        prepare(tmp_path, MODEL, LEAD_MODEL)
    assert not (tmp_path / "kit.json").exists()
    with pytest.raises(UsageError, match="Choose a new destination"):
        prepare(tmp_path, MODEL, LEAD_MODEL)


def test_launch_argv_uses_this_python_and_only_named_provider_variables(tmp_path):
    prefix = [sys.executable, "-m", "aew", "-C", str(tmp_path / "repo"), "opencode", "--acquire"]
    model = ["--", "--model", LEAD_MODEL]
    assert launch_argv(tmp_path, (), LEAD_MODEL) == prefix + model
    assert launch_argv(tmp_path, ("ONE", "TWO"), LEAD_MODEL) == prefix + [
        "--provider-env", "ONE", "--provider-env", "TWO"] + model


def test_seed_is_a_packaged_resource():
    assert files("aew.kit").joinpath("seed.json").is_file()
    root = Path(__file__).resolve().parents[2]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = metadata["tool"]["setuptools"]["package-data"]["aew.kit"]
    assert any(fnmatch.fnmatchcase("seed.json", pattern) for pattern in patterns)


def test_written_receipt_has_reader_fields_and_no_host_paths(tmp_path, monkeypatch):
    engine = prepare(tmp_path, MODEL, LEAD_MODEL)
    run = "R-INV-0001-1"
    directory = runlog.run_dir(engine.aew_root, run)
    directory.mkdir(parents=True)
    runlog.write_record(directory, {"run": run, "launch": {"harness": "fake", "version": "2.2.6"}})
    upstreams = {provider: f"https://{provider}.invalid" for provider in netns.PROVIDER_KEY_ENV}
    policy = {"harness": "fake", "containment": {"network": {"upstreams": upstreams}}}
    monkeypatch.setattr("aew.kit.receipt.Engine.discover", lambda repo: engine)
    monkeypatch.setattr(engine, "execution_policy", lambda: (policy, None))
    path = write_receipt(tmp_path)
    body = path.read_text(encoding="utf-8")
    receipt = json.loads(body)
    assert receipt["schema"] == SCHEMA
    assert set(receipt) == {"schema", "kind", "header", "systems", *FIELDS}
    assert receipt["kind"] == "dry_run"
    assert receipt["readability"] == "not asked"
    assert str(tmp_path) not in body and tmp_path.as_posix() not in body
    assert Path.home().name not in body and socket.gethostname() not in body
    assert json.loads(write_receipt(tmp_path, readable="no").read_text(encoding="utf-8"))["readability"] == "no"


@pytest.mark.parametrize("provider", ["opencode", "opencode-go"])
def test_prepare_refuses_a_provider_denied_to_the_lead(tmp_path, provider):
    with pytest.raises(UsageError, match="Lead denies provider"):
        prepare(tmp_path, MODEL, f"{provider}/model")
    assert not (tmp_path / "repo").exists()


def test_real_lead_receipt_without_worker_launches(tmp_path):
    engine = prepare(tmp_path, MODEL, LEAD_MODEL)
    directory = runlog.run_dir(engine.aew_root, "lead-test")
    directory.mkdir(parents=True)
    (directory / "label.json").write_text('{"filesystem":"os_readonly_roots"}', encoding="utf-8")
    receipt = json.loads(write_receipt(tmp_path).read_text(encoding="utf-8"))
    assert receipt["kind"] == "real"
    assert receipt["header"]["workers_launched"] == "no worker launched"
    assert receipt["systems"]["SYS-09"] == "not seen"
    assert receipt["no_wake"]["live_reach"].startswith("not recorded:")


def test_receipt_reads_persisted_capability_declines(tmp_path, monkeypatch):
    prepare(tmp_path, MODEL, LEAD_MODEL)
    prepared = json.loads((tmp_path / "kit.json").read_text(encoding="utf-8"))["prepared_at"]
    monkeypatch.setattr(receipt_module.capability_store, "read", lambda: {"declined": {
        "recent-tool:linux": {"at": prepared}, "earlier-tool:linux": {"at": "2000-01-01T00:00:00Z"},
    }})
    receipt = json.loads(write_receipt(tmp_path).read_text(encoding="utf-8"))
    assert receipt["systems"]["SYS-09"]["tool_declines_since_prepare"] == ["recent-tool"]


def test_receipt_filters_planted_ticket_paths_after_scope_comparison(tmp_path, monkeypatch):
    engine = prepare(tmp_path, MODEL, LEAD_MODEL)
    monkeypatch.setattr("aew.kit.receipt.Engine.discover", lambda repo: engine)
    monkeypatch.setattr("aew.kit.receipt.socket.gethostname", lambda: "synthetic-host")
    event = {"kind": "work.state", "unit": "ticket", "to": "CANCELLED", "id": "T-0001"}
    monkeypatch.setattr("aew.kit.receipt._records", lambda _engine: [{"op": "work.transition", "events": [event]}])
    record = """---
scope:
  paths:
  - ledger/has space.py
---
"""
    changed = ["ledger/has space.py", "outside.py", "/private/absolute.py", "../parent.py", "synthetic-host/file.py"]
    monkeypatch.setattr(engine, "work_show", lambda _: {
        "record": record, "control": {"integration": {"changed_paths": changed}},
    })
    text = write_receipt(tmp_path).read_text(encoding="utf-8")
    scope = json.loads(text)["scope"]
    assert scope["cancelled_tickets"] == ["T-0001"]
    assert scope["tickets"]["T-0001"] == {
        "scope": {"paths": [], "withheld": 1},
        "changed": {"paths": ["outside.py"], "withheld": 4},
        "outside": {"paths": ["outside.py"], "withheld": 3},
    }
    assert all(path not in text for path in ("/private/absolute.py", "../parent.py", "synthetic-host"))


def test_sys39_non_overlapping_mutating_runs_do_not_count(tmp_path):
    runs = [
        {"run": f"R-INV-000{i}-1", "contract": {"role": "implementer", "work_unit": f"T-000{i}"},
         "started_at": f"2026-11-11T0{i}:00:00Z", "ended_at": f"2026-11-11T0{i}:30:00Z"}
        for i in (1, 2)
    ]
    systems = receipt_module._system_facts(tmp_path, runs, [], [], None, {}, {}, [])
    assert systems["SYS-39"]["overlapping_mutating_runs"] == []


def test_windows_main_prints_install_check_first(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "argv", ["kit", "start", str(tmp_path), "--model", MODEL, "--lead-model", LEAD_MODEL])
    monkeypatch.setattr(kit_main, "prepare", lambda *args, **kwargs: None)
    monkeypatch.setattr(kit_main.subprocess, "call", lambda argv: pytest.fail("Windows must not start the Lead"))
    assert kit_main.main() == 0
    output = capsys.readouterr().out
    assert output.startswith("Windows: UNQUALIFIED")
    assert OPENING_REQUEST not in output


@pytest.mark.parametrize(("flag", "typed", "expected"), [("yes", "", "yes"), (None, "n", "no"), (None, "y", "yes")])
def test_main_records_readability(tmp_path, monkeypatch, flag, typed, expected):
    argv = ["kit", "receipt", str(tmp_path)] + (["--readable", flag] if flag else [])
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: typed)
    answers = []
    monkeypatch.setattr(kit_main, "write_receipt", lambda dest, *, readable: answers.append(readable) or dest)
    assert kit_main.main() == 0
    assert answers == [expected]


def test_main_refuses_to_run_in_an_agent_session(monkeypatch, capsys):
    monkeypatch.setenv("AEW_AGENT_ENDPOINT", "fixture")
    assert kit_main.main() == 1
    assert capsys.readouterr().err == (
        "Run the seeded kit from the operator's own terminal, outside an AEW agent session.\n"
    )


def test_main_refuses_when_lead_session_check_reports_a_problem(monkeypatch, capsys):
    monkeypatch.delenv("AEW_AGENT_ENDPOINT", raising=False)
    monkeypatch.setattr(kit_main, "lead_session_problem", lambda: "fixture Lead session problem")
    assert kit_main.main() == 1
    assert capsys.readouterr().err == (
        "Run the seeded kit from the operator's own terminal, outside an AEW agent session.\n"
    )
