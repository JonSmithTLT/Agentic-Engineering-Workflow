"""The raw arm's configuration and validity rules, retention of kept session databases, and the profile records
(register F19; agent-effectiveness adoption, delta D3: the lower-bound qualification lane).

A raw cell is refused before anything is counted when its case has no task or is held out, its configuration is
incomplete (a session database kept with no retention window or no structured field allowlist; an unpinned or
different harness binary; no pinned profile), its provider variable is missing, or it would run a model other than
its role's pin. A run counts and is not valid when it cannot measure the model: a provider error instead of a model
step, a turn ended by a provider error, a retained secret, a different harness. A kept database is purged past its
window and never read after it. A profile record's qualification state is derived, never asserted.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

from aew_eval import arms, fixture, prereg, profiles, raw, retention, runner  # noqa: E402
from aew_eval.ledger import AttemptLedger  # noqa: E402
from aew_eval.schemas import Invalid, validate  # noqa: E402

FIELDS = [{"field": "tool.name", "transform": "none"}, {"field": "tool.state.input.command", "transform": "prefix_300"}]


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    """A harness binary on this host and the raw configuration that pins it."""
    binary = tmp_path / "bin" / "opencode-cli.py"
    binary.parent.mkdir()
    binary.write_text("# a stand-in harness binary\n", encoding="utf-8")
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(binary))
    return {"role": "worker", "model": "fakeprov/fake-model#high", "steps": 5, "cap_usd": 0.5, "provider_env": [],
            "contain": False,
            "profile": {"id": "lb-demo", "effective_profile": {"context.orientation": None, "tools.presentation": None},
                        "qualification_state": "unqualified"},
            "harness": {"name": "opencode", "version": "2.0.18",
                        "artifact_sha256": {raw.host_platform(): raw._sha256_file(binary)}},  # noqa: SLF001
            "session_db": {"retain": True, "retention_days": 30, "fields": FIELDS}}


def make_case(root: Path, *, task: str | None = "Fix add() in calc.py.") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    manifest = {"schema": "aew/eval-case/v1", "id": "C1", "family": "demo", "fixture": {"base": "base"},
                "hidden_sha256": None, "control_of": None, **({"task": task} if task is not None else {})}
    path = root / "case.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


def plan_for(case_path: Path, config: dict, *, roles: dict | None = None, **over) -> dict:
    case = fixture.load(case_path)
    record = {
        "schema": "aew/eval-prereg/v1", "experiment": "lbq-demo", "question": "Does the profile show the behaviours?",
        "purpose": "qualification",
        "arms": [{"id": "raw", "kind": "raw", "description": "harness alone", "config": config}],
        "cases": [{"id": case.id, "family": "demo", "sha256": fixture.case_sha256(case), "hidden_sha256": None,
                   "control_of": None}],
        "profiles": {"roles": roles or {"worker": "fakeprov/fake-model#high"}, "budget_usd": 1.0},
        "runs_per_cell": 1, "assignment": {"method": "fixed", "seed": 1},
        "primary_measure": "behaviours shown", "metrics": [{"name": "behaviours", "version": "1"}],
        "validity_rules": {"infrastructure_invalid": [], "counted_failures": [],
                           "retry_policy": {"max_retries": 1, "allowed_for": ["invalid_measurement"]},
                           "missing_result_policy": "counted as failure"},
        "stopping_rule": "once", "held_out": [],
        "scoring": {"hidden_channel": "none", "who_scores": "automated", "blinding": "not_possible",
                    "adjudication_policy": "none"},
        "exposure_policy": "n/a", "amendment_policy": "a change is a new id",
    }
    record.update(over)
    return prereg.freeze(record, by="tester")


def run(tmp_path: Path, case_path: Path, f: dict, name: str = "r1", **kw) -> dict:
    return runner.run_cell(f, ledger_dir=tmp_path / "ledger", cell=f["assignment"]["order"][0]["cell"],
                           cases={"C1": case_path}, work=tmp_path / "work", run_name=name, **kw)


def refused(tmp_path: Path, case_path: Path, f: dict, match: str) -> None:
    with pytest.raises(runner.Refused, match=match):
        run(tmp_path, case_path, f)
    assert not (tmp_path / "ledger" / "attempts.jsonl").exists()  # nothing counted


def edit(config: dict, value, *path: str) -> dict:
    """A copy of ``config`` with ``path`` set to ``value`` (or removed, for ``...``)."""
    out = copy.deepcopy(config)
    node = out
    for key in path[:-1]:
        node = node[key]
    if value is ...:
        node.pop(path[-1])
    else:
        node[path[-1]] = value
    return out


# ---------------------------------------------------------------------------------------------- schemas


def test_a_case_task_and_a_qualification_purpose_are_schema_fields(tmp_path, pinned):
    validate("aew/eval-case/v1", {"schema": "aew/eval-case/v1", "id": "C1", "family": "f", "task": "do it",
                                  "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None})
    with pytest.raises(Invalid):
        validate("aew/eval-case/v1", {"schema": "aew/eval-case/v1", "id": "C1", "family": "f", "task": "",
                                      "fixture": {"base": "base"}, "hidden_sha256": None, "control_of": None})
    case_path = make_case(tmp_path / "case")
    assert plan_for(case_path, pinned)["purpose"] == "qualification"
    with pytest.raises(Invalid, match="purpose"):
        plan_for(case_path, pinned, purpose="exploration")


def test_a_task_is_hashed_with_the_case_so_a_changed_prompt_is_a_changed_case(tmp_path):
    a = fixture.case_sha256(fixture.load(make_case(tmp_path / "a", task="Fix add().")))
    b = fixture.case_sha256(fixture.load(make_case(tmp_path / "b", task="Fix add() and sub().")))
    assert a != b


# ---------------------------------------------------------------------------------------------- refusals


@pytest.mark.parametrize("path, value, match", [
    (("model",), "fakeprov", "provider/model"),
    (("steps",), 2.5, "whole number"),
    (("cap_usd",), 0, "positive number"),
    (("provider_env",), "OPENAI_API_KEY", "list of environment variable names"),
    (("provider_env",), ["AEW_LEAD_TOKEN"], "never reach a harness"),
    (("role",), ..., "names the role"),
    (("contain",), ..., "contain: true"),
    (("profile",), ..., "pins its profile record"),
    (("profile", "effective_profile"), {"context.orientation": None}, "effective_profile names exactly"),
    (("harness",), ..., "pins its harness"),
    (("harness", "artifact_sha256"), {"other-os": "0" * 64}, "no pinned harness binary for this host"),
    (("session_db", "retain"), False, "keeps its harness session database"),
    (("session_db", "retention_days"), ..., "retention window has no default"),
    (("session_db", "fields"), [], "non-empty"),
    (("session_db", "fields"), ["tool.state.input.command (first 300 characters)"], "is {field, transform}"),
    (("session_db", "fields"), [{"field": "tool.name", "transform": "truncate"}], "is {field, transform}"),
])
def test_an_incomplete_raw_configuration_is_refused_before_anything_is_counted(tmp_path, pinned, path, value, match):
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, edit(pinned, value, *path)), match)


def test_a_harness_binary_other_than_the_pinned_one_is_refused(tmp_path, pinned):
    case_path = make_case(tmp_path / "case")
    pins = {raw.host_platform(): "0" * 64}
    refused(tmp_path, case_path, plan_for(case_path, edit(pinned, pins, "harness", "artifact_sha256")),
            "is not the pinned one")


def test_a_contained_raw_arm_is_refused_where_it_cannot_be_contained(tmp_path, pinned, monkeypatch):
    monkeypatch.setattr(raw.sys, "platform", "win32")
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, edit(pinned, True, "contain")), "runs only on Linux")


def test_a_raw_cell_whose_case_has_no_task_is_refused(tmp_path, pinned):
    case_path = make_case(tmp_path / "case", task=None)
    refused(tmp_path, case_path, plan_for(case_path, pinned), "has no task")


def test_a_held_out_case_never_runs_on_a_model_arm_before_the_arm_host_split(tmp_path, pinned):
    """Decision of 2026-10-06 on held-out isolation: a model-controlled process never runs on the host that holds
    unreleased held-out material, so the shared runner refuses every held-out cell of a model arm."""
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, pinned, held_out=["C1"]), "held out, and a model-controlled arm")


def test_a_missing_provider_variable_is_refused_and_its_value_is_never_needed_to_say_so(tmp_path, pinned,
                                                                                         monkeypatch):
    monkeypatch.delenv("FAKEPROV_TEST_KEY", raising=False)
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, edit(pinned, ["FAKEPROV_TEST_KEY"], "provider_env")),
            "FAKEPROV_TEST_KEY is not set")


def test_a_raw_arm_never_runs_a_model_other_than_its_roles_pinned_one(tmp_path, pinned):
    case_path = make_case(tmp_path / "case")
    refused(tmp_path, case_path, plan_for(case_path, pinned, roles={"worker": "fakeprov/other-model"}),
            "pins worker to 'fakeprov/other-model'")


# ---------------------------------------------------------------------------------------------- validity


@pytest.mark.parametrize("observed, expected", [
    ([], None),
    ([{"role": "worker", "provider": "opencode", "model": "m-1", "effort": None}], False),
    ([{"role": "worker", "provider": "opencode", "model": "m-2", "effort": None}], True),
    ([{"role": "reviewer", "provider": "opencode", "model": "m-1", "effort": None}], True),
])
def test_a_model_the_preregistration_did_not_pin_is_a_mismatch(observed, expected):
    assert runner.profile_mismatch({"worker": "opencode/m-1"}, observed) is expected


def test_an_unreported_effort_never_matches_a_pinned_effort():
    pinned = {"worker": "openai/m#high"}
    assert runner.profile_mismatch(pinned, [{"role": "worker", "provider": "openai", "model": "m",
                                             "effort": "high"}]) is False
    assert runner.profile_mismatch(pinned, [{"role": "worker", "provider": "openai", "model": "m", "effort": None,
                                             "effort_unreported": True}]) is True


def test_a_mismatched_or_self_invalidated_raw_run_is_counted_but_not_valid(tmp_path, pinned, monkeypatch):
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, pinned)
    outcomes = iter([arms.ArmResult(observed_profiles=[{"role": "worker", "provider": "fakeprov",
                                                        "model": "cheaper-model", "effort": "high"}]),
                     arms.ArmResult(observed_profiles=[{"role": "worker", "provider": "fakeprov",
                                                        "model": "fake-model", "effort": "high"}],
                                    invalid="PROVIDER_KEY_RETAINED")])
    seen_tasks = []

    def fake_run(self, repo, config, *, deadline_s, task=None):
        seen_tasks.append(task)
        return next(outcomes)

    monkeypatch.setattr(raw.RawArm, "run", fake_run)
    first = run(tmp_path, case_path, f)
    assert first["validity"] == {"status": "invalid_measurement", "reason_code": "PROFILE_MISMATCH"}
    assert first["profile"]["mismatch"] is True
    second = run(tmp_path, case_path, f, name="r1b", retry_of="lbq-demo/r1")
    assert second["validity"] == {"status": "invalid_measurement", "reason_code": "PROVIDER_KEY_RETAINED"}
    assert second["profile"]["mismatch"] is False
    assert seen_tasks == ["Fix add() in calc.py."] * 2  # the case's task, verbatim


ERRORED = {"model": {"providerID": "opencode", "id": "m"}, "error": {"type": "APIError", "message": "401"}}
STEP = {"model": {"providerID": "opencode", "id": "m"}, "error": None}


@pytest.mark.parametrize("assistant, reason", [
    ([STEP, STEP], None),
    ([ERRORED], "NO_MODEL_STEP"),                    # a rejected key, a rate limit: the model never acted
    ([], "NO_MODEL_STEP"),
    ([STEP, STEP, ERRORED], "PROVIDER_ERROR_ENDED_TURN"),
    ([STEP, ERRORED, STEP], None),                   # a transient error the session recovered from
])
def test_a_provider_error_is_not_a_model_step(assistant, reason):
    assert raw.raw_invalid(leaked=[], facts=raw.step_facts(assistant)) == reason


def test_the_reasons_a_raw_run_cannot_count_take_precedence_in_order():
    facts = raw.step_facts([STEP])
    assert raw.raw_invalid(leaked=["x"], facts=facts, arm_error="boom", harness_mismatch=True) == \
        "PROVIDER_KEY_RETAINED"
    assert raw.raw_invalid(leaked=[], facts=facts, harness_mismatch=True) == "HARNESS_MISMATCH"
    assert raw.raw_invalid(leaked=[], facts=facts, containment_failed=True) == "CONTAINMENT_FAILED"
    assert raw.raw_invalid(leaked=[], facts=raw.step_facts([]), arm_error="ConnectionError") == "ARM_ERROR"


def test_an_errored_assistant_message_as_the_adapter_records_it_is_not_a_step():
    """Review finding 3, reproduced through the adapter's own snapshot: OpenCode stores an assistant message that
    carries only a provider error, and the adapter records it."""
    from aew.harness.opencode import adapter as oc

    class Client:
        def get(self, path, params=None, timeout=None):
            if path.endswith("/message"):
                return {"data": [
                    {"type": "user", "content": [{"type": "text", "text": "the task"}]},
                    {"type": "assistant", "model": {"providerID": "opencode", "id": "m"}, "tokens": {},
                     "cost": 0, "content": [], "error": {"type": "APIError", "message": "401 invalid api key"}}],
                    "cursor": {}}
            return {"data": {"cost": 0, "tokens": {}}} if path.startswith("/api/session/s1") else {"data": []}

    a = oc.OpenCodeAdapter.__new__(oc.OpenCodeAdapter)
    a.client, a.session, a.directory, a.foreign_sessions = Client(), "s1", ".", []
    a._take_snapshot()
    facts = raw.step_facts(a.snapshot["assistant"])
    assert facts["model_steps"] == 0 and facts["errored_steps"] == 1
    assert raw.raw_invalid(leaked=[], facts=facts) == "NO_MODEL_STEP"


@pytest.mark.parametrize("ended, assistant, why", [
    ("ended", [STEP] * 3, []),
    ("ended", [STEP] * 5, ["step_limit"]),
    ("cost_cap", [STEP] * 2, ["turn:cost_cap"]),
    ("deadline", [STEP] * 2, ["turn:deadline"]),
    ("ended", [STEP, ERRORED], ["provider_error"]),
])
def test_a_run_cut_short_says_why(ended, assistant, why):
    assert raw.truncation(ended=ended, facts=raw.step_facts(assistant), steps_limit=5) == why


def test_an_unknown_cost_is_charged_at_the_cap():
    assert raw.charged(0.12, 0.75) == 0.12
    assert raw.charged(None, 0.75) == 0.75
    assert raw.charged("n/a", 0.75) == 0.75


def test_retained_state_is_scanned_for_a_provider_value_and_holding_files_are_purged(tmp_path):
    (tmp_path / "harness" / "x").mkdir(parents=True)
    (tmp_path / "harness" / "x" / "log.txt").write_bytes(b"value=provider-value-under-test end")
    (tmp_path / "clean.txt").write_text("nothing here", encoding="utf-8")
    hits = raw.files_holding(tmp_path, [b"provider-value-under-test"])
    assert hits == ["harness/x/log.txt"]
    assert raw.purge_files(tmp_path, hits) == hits
    assert not (tmp_path / "harness" / "x" / "log.txt").exists() and (tmp_path / "clean.txt").exists()


def test_a_contained_run_hides_everything_beside_what_it_keeps(tmp_path):
    home = tmp_path / "home"
    for d in ("lane/out/work/run-1", "lane/out/work/run-2", "lane/out/ledger", "lane/hidden/cases",
              "lane/venv/bin", "private/eval", ".ssh"):
        (home / d).mkdir(parents=True)
    (home / "notes.txt").write_text("x", encoding="utf-8")
    keep = [home / "lane/out/work/run-1", home / "lane/venv", home]  # keeping home itself would hide nothing
    dirs, files = raw.hidden_around(home, keep)
    hidden = {Path(p).relative_to(home.resolve()).as_posix() for p in dirs + files}
    assert hidden == {"lane/out/work/run-2", "lane/out/ledger", "lane/hidden", "private", ".ssh", "notes.txt"}
    dirs, files = raw.hidden_around(home, [tmp_path / "elsewhere"])  # nothing kept under home: all of it is hidden
    assert {Path(p).name for p in dirs + files} == {"lane", "private", ".ssh", "notes.txt"}


def test_a_contained_run_keeps_nothing_from_the_import_path_and_hides_the_case_design(tmp_path, monkeypatch):
    """Re-review finding 2: the driver's own directory and the instrument are on the import path; a contained run
    must never see them (the case manifests name the cause, the decoy and the stale note)."""
    lane = raw.EVAL_DIR / "experiments" / "lower-bound-qualification"
    monkeypatch.setattr(sys, "path", [str(lane), str(raw.EVAL_DIR), str(ROOT / "src"), *sys.path])
    scratch = tmp_path / "out" / "work" / "LBQ-1-raw-1"
    keep, design = raw.layout_paths(scratch, binary=tmp_path / "bin" / "opencode-cli")
    kept = {p.resolve() for p in keep}
    assert not any(lane.resolve() == k or lane.resolve() in k.parents for k in kept)
    assert not any(raw.EVAL_DIR.resolve() == k or raw.EVAL_DIR.resolve() in k.parents for k in kept)
    assert design == [str(raw.EVAL_DIR)]
    files = {Path(f).relative_to(lane).as_posix() for f in raw.design_files() if Path(f).is_relative_to(lane)}
    assert {"fixture/LBQ-1.yaml", "behaviours.yaml", "rubric.md", "prereg.yaml"} <= files  # the probe opens each


def test_a_mask_inside_a_hidden_directory_is_left_to_it():
    sep = "/" if "/" in str(Path("/a/b")) else "\\"
    root = sep + "h"
    paths = {f"{root}{sep}.config", f"{root}{sep}.config{sep}gh", f"{root}{sep}.local{sep}share{sep}opencode",
             f"{root}{sep}.localx"}
    assert raw.outermost(paths) == sorted({f"{root}{sep}.config", f"{root}{sep}.local{sep}share{sep}opencode",
                                           f"{root}{sep}.localx"})


# ---------------------------------------------------------------------------------------------- retention


def kept_run(tmp_path: Path, pinned: dict, retain_until: str) -> tuple[dict, Path, Path]:
    """A finalized raw run that kept a session database, retained until ``retain_until``."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, pinned)
    state = tmp_path / "work" / "r1" / "harness"
    db = state / "harness" / "xdg-data" / "opencode" / "opencode.db"

    def fake_run(self, repo, config, *, deadline_s, task=None):
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.execute("create table session_message (seq integer, type text, data text)")
        con.commit()
        con.close()
        return arms.ArmResult(
            outcome={"session_db": {"state_dir": str(state.resolve()), "path": "harness/harness/xdg-data/opencode/"
                                    "opencode.db", "retain_until": retain_until, "fields": FIELDS}},
            observed_profiles=[{"role": "worker", "provider": "fakeprov", "model": "fake-model", "effort": "high"}])

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(raw.RawArm, "run", fake_run)
        run(tmp_path, case_path, f)
    return f, state, db


def test_a_session_database_inside_its_window_is_kept_and_opened_read_only(tmp_path, pinned):
    until = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
    f, state, db = kept_run(tmp_path, pinned, until)
    assert retention.purge(tmp_path / "ledger", f) == [] and db.exists()
    con = retention.open_session_db(tmp_path / "ledger", f, "lbq-demo/r1")
    try:
        assert con.execute("select count(*) from session_message").fetchone() == (0,)
        with pytest.raises(sqlite3.OperationalError):
            con.execute("insert into session_message values (1, 'x', '{}')")
    finally:
        con.close()


def test_a_session_database_past_its_window_is_refused_purged_and_the_purge_recorded(tmp_path, pinned):
    f, state, db = kept_run(tmp_path, pinned, "2026-01-01")
    with pytest.raises(Invalid, match="past its retention window"):
        retention.open_session_db(tmp_path / "ledger", f, "lbq-demo/r1")
    entries = retention.purge(tmp_path / "ledger", f)
    assert [(e["run_id"], e["deleted"]) for e in entries] == [("lbq-demo/r1", True)] and not state.exists()
    logged = [json.loads(line) for line in (tmp_path / "ledger" / "retention.jsonl").read_text().splitlines()]
    assert logged == entries
    assert retention.purge(tmp_path / "ledger", f) == []  # never purged twice
    with pytest.raises(Invalid, match="was purged"):
        retention.open_session_db(tmp_path / "ledger", f, "lbq-demo/r1")
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"lbq-demo/r1": "valid"}  # the run record is unchanged


def test_a_lost_attempts_session_state_is_purged_by_the_window_from_its_registration(tmp_path, pinned):
    """Re-review finding 1: an attempt that never finished (the runner was killed) has no result naming its state;
    its harness state is still purged once the window, counted from its registration, has passed."""
    case_path = make_case(tmp_path / "case")
    f = plan_for(case_path, pinned)
    ledger = AttemptLedger(tmp_path / "ledger", f)
    ledger.register(run_id="lbq-demo/r1", cell=f["assignment"]["order"][0]["cell"],
                    requested_profile=f["profiles"]["roles"])
    state = tmp_path / "work" / "r1" / "harness"
    (state / "xdg-data" / "opencode").mkdir(parents=True)
    (state / "xdg-data" / "opencode" / "opencode.db").write_bytes(b"session")
    assert retention.purge(tmp_path / "ledger", f) == [] and state.exists()  # inside its window: kept
    later = datetime.now(UTC) + timedelta(days=31)
    entries = retention.purge(tmp_path / "ledger", f, now=later)
    assert [(e["run_id"], e["deleted"]) for e in entries] == [("lbq-demo/r1", True)] and not state.exists()
    assert "without a result" in entries[0]["reason"]
    assert retention.purge(tmp_path / "ledger", f, now=later) == []  # never purged twice
    assert AttemptLedger(tmp_path / "ledger", f).status() == {"lbq-demo/r1": "runner_lost"}


def test_nothing_under_src_aew_imports_the_evaluation_instrument():
    """Revision C: AEW's runtime never consumes a session database or the instrument that keeps them."""
    offenders = [p.relative_to(ROOT).as_posix() for p in (ROOT / "src" / "aew").rglob("*.py")
                 if "aew_eval" in p.read_text(encoding="utf-8")]
    assert offenders == []


# ---------------------------------------------------------------------------------------------- profile records

PROFILE = {
    "schema": "aew/eval-profile/v1", "id": "lb-demo", "class": "lower-bound", "ref": "opencode/demo-free",
    "provider": "opencode", "model": "demo-free", "effort": None, "plan_role": "primary", "twin_of": None,
    "harness": {"name": "opencode", "version": "2.0.18", "artifact_sha256": None},
    "effective_profile": {"context.orientation": None, "tools.presentation": None},
    "credential_env": [], "cost_per_mtok_usd": {"input": 0, "output": 0, "source": "catalog"},
    "availability": {"checked_at": "2026-10-10", "offered_by_pinned_harness": True},
    "floor": {"state": "not_run"}, "ceiling": {"state": "not_run"}, "qualification_state": "unqualified",
}


def profile(**over) -> dict:
    record = copy.deepcopy(PROFILE)
    for key, value in over.items():
        record[key] = value
    return record


@pytest.mark.parametrize("over, state", [
    ({}, "unqualified"),
    ({"availability": {"checked_at": None, "offered_by_pinned_harness": None}}, "unqualified"),
    ({"availability": {"checked_at": "2026-10-10", "offered_by_pinned_harness": False,
                       "catalog_status": "deprecated"}}, "unavailable"),
    ({"floor": {"state": "failed"}}, "floor_failed"),
    ({"floor": {"state": "passed"}}, "floor_passed"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "none_shown"}}, "not_a_lower_bound"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "behaviours_shown", "behaviours": ["repeated_exploration"]}},
     "qualified"),
    ({"class": "mid", "floor": {"state": "passed"}, "ceiling": {"state": "not_applicable"}}, "floor_passed"),
])
def test_a_profile_state_is_derived_from_its_availability_floor_and_ceiling(over, state):
    record = profile(**over, qualification_state=state)
    profiles.check(record)
    assert profiles.derive_state(record) == state


@pytest.mark.parametrize("over, match", [
    ({"qualification_state": "qualified"}, "establish unqualified"),
    ({"ceiling": {"state": "behaviours_shown", "behaviours": ["x"]}, "qualification_state": "qualified"},
     "needs a passed floor"),
    ({"floor": {"state": "passed"}, "ceiling": {"state": "behaviours_shown"}, "qualification_state": "qualified"},
     "names the behaviours"),
    ({"class": "mid", "floor": {"state": "passed"}, "ceiling": {"state": "none_shown"},
      "qualification_state": "floor_passed"}, "only a lower-bound profile"),
    ({"ref": "opencode/other-free"}, "is not its provider, model and effort"),
    ({"credential_env": ["sk-a-value"]}, "credential_env"),
])
def test_a_profile_record_that_contradicts_itself_is_refused(over, match):
    with pytest.raises(Invalid, match=match):
        profiles.check(profile(**over))


def test_a_profiles_file_has_unique_ids_and_known_twins(tmp_path):
    path = tmp_path / "profiles.yaml"
    twin = profile(id="lb-demo-paid", ref="opencode/demo", model="demo", plan_role="paid-twin", twin_of="lb-demo",
                   credential_env=["OPENCODE_API_KEY"])
    path.write_text(yaml.safe_dump([profile(), twin]), encoding="utf-8")
    assert [r["id"] for r in profiles.load(path)] == ["lb-demo", "lb-demo-paid"]
    path.write_text(yaml.safe_dump([twin]), encoding="utf-8")
    with pytest.raises(Invalid, match="twin of lb-demo"):
        profiles.load(path)
    path.write_text(yaml.safe_dump([profile(), profile()]), encoding="utf-8")
    with pytest.raises(Invalid, match="duplicate"):
        profiles.load(path)
