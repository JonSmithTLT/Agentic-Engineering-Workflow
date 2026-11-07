"""A run's progress digest, ``aew/run-progress/v1`` (steering design §2): what the worker touched, ran and tested, and
the triggers that wake the Lead (``aew.harness.progress``, written by the meter's poll in ``aew.harness.usage_live``).

The tool parts are shaped as the steering PR 1 probe measured them on OpenCode 2.0.18: ``write`` and ``edit`` name
their file in ``state.input.path`` (``edit`` also in ``state.metadata.files[].file``), and ``shell`` holds its command
in ``state.input.command`` and its exit code in ``state.metadata.exit``. Every trigger test has a planted control. The
clock is a value the test sets, never a sleep."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fake_opencode as F
import pytest

from aew.engine import outbox
from aew.harness import progress as P
from aew.harness import runlog
from aew.harness import usage_live as L
from aew.harness.opencode.adapter import OpenCodeAdapter

OPENAPI = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode" /
                      "openapi-2.0.18.min.json").read_text(encoding="utf-8"))
SCOPE = ["src/a/**"]
PYTEST = "python -m pytest tests/test_x.py"


class Clock:
    def __init__(self, t: float = 1_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


_n = [0]


def part(name: str, inp: dict[str, Any], *, metadata: dict[str, Any] | None = None, text: str = "",
         status: str = "completed") -> dict[str, Any]:
    _n[0] += 1
    return {"type": "tool", "id": f"call_{_n[0]}", "name": name, "executed": False,
            "time": {"created": 1_000_000, "ran": 1_000_001, "completed": 1_000_002 + _n[0]},
            "state": {"status": status, "input": inp, "metadata": metadata or {"truncated": False},
                      "content": [{"type": "text", "text": text}] if text else []}}


def write(path: str) -> dict[str, Any]:
    return part("write", {"path": path, "content": "x = 1\n"}, text=f"Created file successfully: {path}")


def edit(path: str) -> dict[str, Any]:
    return part("edit", {"path": path, "oldString": "a", "newString": "b"},
                metadata={"files": [{"file": path, "patch": "", "status": "modified", "additions": 1,
                                     "deletions": 1}], "truncated": False})


def shell(command: str, exit_code: int | None, output: str = "") -> dict[str, Any]:
    meta: dict[str, Any] = {"status": "completed", "truncated": False}
    if exit_code is not None:
        meta["exit"] = exit_code
    return part("shell", {"command": command, "description": "step"}, metadata=meta, text=output)


def failing(*names: str) -> str:
    return "\n".join([*(f"FAILED {n} - assert 1 == 2" for n in names), f"{len(names)} failed"])


def message(*parts: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "id": f"msg_{_n[0]}", "content": [{"type": "text", "text": "step"}, *parts]}


class Run:
    """A tracker and its state, driven step by step."""

    def __init__(self, *, scope: list[str] | None = SCOPE, workspace: str | None = None) -> None:
        self.clock = Clock()
        self.t = P.Tracker(run="R-1", workspace=workspace, scope_paths=scope, clock=self.clock)
        self.state = P.empty_state(started_at=self.clock())

    def step(self, *parts: dict[str, Any], active: bool = True, run_state: str = "live") -> list[str]:
        self.t.observe(self.state, message(*parts))
        return self.t.advance(self.state, run_state=run_state, active=active, prompt_posted=True)

    def digest(self, *, active: bool = True, run_state: str = "live", steps: int = 0) -> dict[str, Any]:
        return self.t.digest(self.state, run_state=run_state, active=active, steps=steps, tokens=None,
                             observed_at="2026-11-07T00:00:00.000Z")


# ---------------------------------------------------------------------------------------------- what the parts carry


def test_the_tool_part_fields_the_digest_reads_are_in_the_pinned_schema():
    schemas = OPENAPI["components"]["schemas"]
    tool = schemas["Session.Message.Assistant.Tool"]["properties"]
    assert {"id", "name", "state", "time"} <= set(tool)
    completed = schemas["Session.Message.ToolState.Completed"]["properties"]
    assert {"status", "input", "metadata", "content"} <= set(completed)
    assert {"input", "metadata"} <= set(schemas["Session.Message.ToolState.Error"]["properties"])
    assert "completed" in json.dumps(tool["time"])


def test_a_write_and_an_edit_are_files_touched_and_a_read_is_not():
    run = Run()
    run.step(write("src/a/new.py"), edit("src/a/old.py"), part("read", {"path": "src/a/other.py"}))
    d = run.digest()
    assert d["files_touched"] == {"paths": ["src/a/new.py", "src/a/old.py"], "count": 2}
    assert d["out_of_scope"] == []


def test_files_touched_keeps_fifty_paths_and_counts_the_rest():
    run = Run(scope=None)
    run.step(*[write(f"src/a/f{i}.py") for i in range(60)])
    d = run.digest()
    assert len(d["files_touched"]["paths"]) == P.MAX_FILES and d["files_touched"]["count"] == 60


def test_an_absolute_path_in_the_workspace_is_made_workspace_relative(tmp_path: Path):
    run = Run(workspace=str(tmp_path))
    run.step(write(str(tmp_path / "src" / "a" / "x.py")))
    assert run.digest()["files_touched"]["paths"] == ["src/a/x.py"]


def test_the_last_command_is_cut_to_200_characters_with_its_exit_code():
    run = Run()
    run.step(shell("echo " + "x" * 400, 3))
    last = run.digest()["last_command"]
    assert last["text"] == ("echo " + "x" * 400)[:200] + "..." and last["exit"] == 3 and last["at"] is not None


def test_a_command_with_no_exit_code_reads_none_never_a_guess():
    run = Run()
    run.step(shell("make build", None))
    assert run.digest()["last_command"]["exit"] is None


def test_a_part_seen_twice_counts_once():
    run = Run()
    w = write("src/a/x.py")
    c = shell("echo hi", 0)
    run.step(w, c)
    run.step(w, c)
    d = run.digest()
    assert d["files_touched"]["count"] == 1 and run.state["commands_n"] == 1


@pytest.mark.parametrize("command, is_test", [
    ("pytest -q", True), ("python -m pytest tests/x.py", True), ("python3 -m unittest", True),
    ("cd src && npm test", True), ("uv run pytest", True), ("go test ./...", True), ("cargo test", True),
    ("FOO=1 pytest", True), (r"C:\venv\Scripts\pytest.exe -q", True),
    ("python build.py", False), ("make build", False), ("echo pytest", False), ("npm install", False),
])
def test_a_test_command_is_known_by_its_runner(command: str, is_test: bool):
    assert P.is_test_command(command) is is_test


def test_failing_names_come_from_pytest_lines_and_are_unknown_for_another_runner():
    run = Run()
    run.step(shell(PYTEST, 1, failing("tests/test_x.py::test_a", "tests/test_x.py::test_b")))
    assert run.digest()["last_test"]["failing"] == ["tests/test_x.py::test_a", "tests/test_x.py::test_b"]
    run.step(shell("go test ./...", 1, "--- FAIL: TestA (0.00s)"))
    t = run.digest()["last_test"]
    assert t["result"] == "fail" and t["failing"] == P.UNKNOWN and t["failing_n"] is None


def test_last_test_names_at_most_five_failing_tests_and_counts_them_all():
    run = Run()
    run.step(shell(PYTEST, 1, failing(*[f"tests/t.py::test_{i}" for i in range(8)])))
    t = run.digest()["last_test"]
    assert len(t["failing"]) == P.MAX_FAILING and t["failing_n"] == 8


# ---------------------------------------------------------------------------------------------- triggers


def test_a_write_outside_the_scope_wakes_once_naming_the_path():
    run = Run()
    assert run.step(write("src/b/x.py")) == [P.OUT_OF_SCOPE]
    assert run.state["triggers"][-1]["path"] == "src/b/x.py"
    assert run.digest()["out_of_scope"] == ["src/b/x.py"]
    run.clock.t += 60
    assert run.step(edit("src/b/x.py")) == []  # the same path again is no new trigger


def test_a_write_inside_the_scope_wakes_no_one():  # the control of the case above
    run = Run()
    assert run.step(write("src/a/x.py"), edit("src/a/y.py")) == []
    assert run.digest()["out_of_scope"] == []


def test_without_scope_paths_out_of_scope_reads_unknown_and_never_wakes():
    run = Run(scope=None)
    assert run.step(write("src/b/x.py")) == []
    assert run.digest()["out_of_scope"] == P.UNKNOWN


def test_a_path_outside_the_workspace_is_out_of_scope(tmp_path: Path):
    run = Run(workspace=str(tmp_path / "ws"))
    assert run.step(write(str(tmp_path / "elsewhere" / "x.py"))) == [P.OUT_OF_SCOPE]


def test_red_before_green_wakes_no_one():
    run = Run()
    assert run.step(shell(PYTEST, 1, failing("tests/test_x.py::test_a"))) == []
    assert run.digest()["last_test"]["result"] == "fail"


def test_a_regression_after_a_green_run_wakes_once():  # the control of red before green
    run = Run()
    assert run.step(shell(PYTEST, 1, failing("tests/test_x.py::test_a"))) == []
    assert run.step(shell(PYTEST, 0, "1 passed")) == []
    assert run.step(shell(PYTEST, 1, failing("tests/test_x.py::test_a"))) == [P.TEST_FAILED]
    assert run.state["triggers"][-1]["kind"] == "regression"


def test_a_named_test_seen_passing_that_fails_later_is_a_regression():
    run = Run()
    assert run.step(shell("pytest -rA", 1, "PASSED tests/t.py::test_ok\n" + failing("tests/t.py::test_new"))) == []
    assert run.step(shell("pytest -k ok", 1, failing("tests/t.py::test_ok"))) == [P.TEST_FAILED]


def test_the_same_failure_on_three_runs_in_a_row_is_stuck():
    run = Run()
    same = failing("tests/t.py::test_a")
    assert run.step(shell(PYTEST, 1, same)) == []
    assert run.step(shell(PYTEST, 1, same)) == []
    assert run.step(shell(PYTEST, 1, same)) == [P.TEST_FAILED]
    assert run.state["triggers"][-1]["kind"] == "stuck"


def test_a_newly_passing_test_is_progress_not_stuck():  # the control of the case above
    run = Run()
    assert run.step(shell(PYTEST, 1, failing("tests/t.py::test_a", "tests/t.py::test_b"))) == []
    assert run.step(shell(PYTEST, 1, failing("tests/t.py::test_a"))) == []
    assert run.step(shell(PYTEST, 1, failing("tests/t.py::test_a"))) == []


def test_a_failing_build_command_is_not_a_failing_test():
    run = Run()
    for _ in range(4):
        assert run.step(shell("make build", 2, "error")) == []
    assert run.digest()["last_test"] is None


def test_a_repeat_inside_thirty_seconds_is_counted_not_woken():
    run = Run()
    assert run.step(write("src/b/one.py")) == [P.OUT_OF_SCOPE]
    run.clock.t += P.ANTI_SPIN_S - 1
    assert run.step(write("src/b/two.py")) == []
    assert run.digest()["since_last_wake"]["suppressed"] == {P.OUT_OF_SCOPE: 1}


def test_a_repeat_after_thirty_seconds_wakes():  # the control of the case above
    run = Run()
    assert run.step(write("src/b/one.py")) == [P.OUT_OF_SCOPE]
    run.clock.t += P.ANTI_SPIN_S + 1
    assert run.step(write("src/b/two.py")) == [P.OUT_OF_SCOPE]


def test_an_idle_worker_wakes_after_thirty_seconds_once():
    run = Run()
    assert run.step(active=False) == []
    run.clock.t += P.IDLE_DEBOUNCE_S - 1
    assert run.step(active=False) == []
    run.clock.t += 1
    assert run.step(active=False) == [P.WORKER_IDLE]
    run.clock.t += 120
    assert run.step(active=False) == []
    assert run.digest(active=False)["state"] == P.IDLE


def test_a_worker_that_resumes_inside_thirty_seconds_never_wakes():  # the control of the case above
    run = Run()
    run.step(active=False)
    run.clock.t += P.IDLE_DEBOUNCE_S - 1
    run.step(active=True)
    run.clock.t += 2
    assert run.step(active=False) == []


def test_a_worker_whose_contract_is_not_yet_posted_is_not_idle():
    run = Run()
    run.t.observe(run.state, message())
    assert run.t.advance(run.state, run_state="live", active=False, prompt_posted=False) == []
    run.clock.t += 120
    assert run.t.advance(run.state, run_state="live", active=False, prompt_posted=False) == []


def test_the_end_of_the_run_wakes_once():
    run = Run()
    assert run.step(run_state="final") == [P.RUN_ENDED]
    assert run.step(run_state="final") == []
    assert run.digest(run_state="final")["state"] == P.ENDED


def test_since_last_wake_counts_from_the_last_trigger():
    run = Run()
    run.step(write("src/a/one.py"), shell("echo 1", 0))
    assert run.step(write("src/b/out.py")) == [P.OUT_OF_SCOPE]
    run.t.mark_woken(run.state, steps=3)
    run.step(write("src/a/two.py"))
    since = run.digest(steps=5)["since_last_wake"]
    assert since == {"steps": 2, "files": ["src/a/two.py"], "files_n": 1, "commands": 0, "tests": 0,
                     "suppressed": {}}


def test_the_why_enum_is_closed_and_the_poll_detects_four():
    assert P.WHY == ("run_ended", "test_failed", "out_of_scope", "worker_message", "worker_idle", "quiet")
    assert set(P.DETECTED_IN_POLL) == set(P.WHY) - {P.WORKER_MESSAGE, P.QUIET}


def test_the_digests_state_at_its_bounds_stays_far_below_the_meters_cap():
    run = Run(scope=[])
    long = "x" * 600
    run.step(*[write(f"{long}/{i}") for i in range(80)],
             *[shell(PYTEST + " " + long + str(i), 1, failing(*[f"{long}::t{j}" for j in range(8)]))
               for i in range(40)])
    for i in range(30):
        run.clock.t += 40
        run.step(write(f"src/b/{i}"))
    assert P.valid_state(run.state)
    assert len(json.dumps(run.state)) < L.MAX_STATE_BYTES // 4


# ---------------------------------------------------------------------------------------------- the meter writes it


class Lab:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.app = F.local_app(root, {})
        self.client = F.LocalClient(self.app)
        self.clock = Clock()
        self.run_dir = root / ".aew" / runlog.RUNS_REL / "R-1"
        self.run_dir.mkdir(parents=True)
        self.sid = self.app.add_session()
        self.n = 0

    def meter(self) -> L.Meter:
        tracker = P.Tracker(run="R-1", workspace=None, scope_paths=SCOPE, clock=self.clock)
        m = L.Meter(self.client, source={"kind": "run", "id": "R-1"}, version="2.0.18",
                    semantics_table=OpenCodeAdapter.token_semantics, s_pot=1,
                    state_path=self.run_dir / runlog.LIVE_STATE_FILE, live_path=self.run_dir / runlog.LIVE_FILE,
                    progress=tracker,
                    progress_path=self.run_dir / runlog.PROGRESS_FILE)
        m.set_prompt_state("posted")
        return m

    def step(self, *parts: dict[str, Any]) -> None:
        self.n += 1
        mid = self.app.start_call(self.sid, created=1000.0 * self.n)
        msg = next(m for m in self.app.sessions[self.sid].messages if m["id"] == mid)
        msg["content"] = [{"type": "text", "text": "step"}, *parts]
        self.app.end_call(self.sid, mid, tokens=F.zero_usage(),
                          completed=1000.0 * self.n + 10)


@pytest.fixture
def lab(tmp_path: Path) -> Lab:
    return Lab(tmp_path)


@pytest.fixture
def wakes(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    seen: list[Path] = []
    monkeypatch.setattr(outbox, "bump_wake", lambda root, revision=None: seen.append(root))
    return seen


def test_the_meters_poll_writes_the_digest_beside_the_sample(lab: Lab, wakes: list[Path]):
    meter = lab.meter()
    lab.step(write("src/a/x.py"), shell(PYTEST, 1, failing("tests/test_x.py::test_a")))
    meter.poll()
    d = runlog.read_progress(lab.run_dir)
    assert d is not None and d["schema"] == "aew/run-progress/v1" and d["run"] == "R-1"
    assert d["files_touched"]["paths"] == ["src/a/x.py"] and d["last_test"]["result"] == "fail"
    assert d["steps"] == 1 and d["triggers"] == []
    assert wakes == []  # the per-second rewrite wakes no waiter


def test_a_new_trigger_bumps_the_wake_file_once(lab: Lab, wakes: list[Path]):  # the control of the case above
    meter = lab.meter()
    lab.step(write("src/b/x.py"))
    meter.poll()
    meter.poll()
    d = runlog.read_progress(lab.run_dir)
    assert [t["why"] for t in d["triggers"]] == [P.OUT_OF_SCOPE] and d["triggers"][0]["path"] == "src/b/x.py"
    assert wakes == [lab.root / ".aew"]


def test_a_read_the_meter_drops_leaves_the_digest_unchanged(lab: Lab, wakes: list[Path]):
    meter = lab.meter()
    lab.step(write("src/a/x.py"))
    before = json.dumps(meter.state["progress"], sort_keys=True)
    meter._read(deadline=None, cancellable=True)  # read, never committed: another commit overtook it
    assert json.dumps(meter.state["progress"], sort_keys=True) == before
    meter.poll()  # the control: a committed read advances it
    assert meter.state["progress"]["files"] == ["src/a/x.py"]


def test_a_restarted_meter_carries_the_digest_forward(lab: Lab, wakes: list[Path]):
    meter = lab.meter()
    lab.step(write("src/b/x.py"))
    meter.poll()
    again = lab.meter()
    assert again.state["progress"]["outside"] == ["src/b/x.py"]
    again.poll()
    assert [t["why"] for t in runlog.read_progress(lab.run_dir)["triggers"]] == [P.OUT_OF_SCOPE]


def test_the_final_sample_ends_the_digest_and_wakes(lab: Lab, wakes: list[Path]):
    meter = lab.meter()
    meter.poll()
    meter.final()
    d = runlog.read_progress(lab.run_dir)
    assert d["state"] == P.ENDED and d["triggers"][-1]["why"] == P.RUN_ENDED
    assert len(wakes) == 1


def test_a_meter_with_no_tracker_writes_no_digest(lab: Lab, wakes: list[Path]):
    m = L.Meter(lab.client, source={"kind": "run", "id": "R-1"}, version="2.0.18",
                semantics_table=OpenCodeAdapter.token_semantics, s_pot=1,
                state_path=lab.run_dir / runlog.LIVE_STATE_FILE, live_path=lab.run_dir / runlog.LIVE_FILE)
    lab.step(write("src/b/x.py"))
    m.poll()
    assert m.state["progress"] is None and not (lab.run_dir / runlog.PROGRESS_FILE).exists()


def test_a_progress_file_of_another_schema_is_not_read(tmp_path: Path):
    (tmp_path / runlog.PROGRESS_FILE).write_text(json.dumps({"schema": "aew/usage-live/v1"}), encoding="utf-8")
    assert runlog.read_progress(tmp_path) is None


# ---------------------------------------------------------------------------------------------- the quiet backstop


@pytest.mark.parametrize("policy, expected", [
    (None, 1200), ({}, 1200), ({"lead": {}}, 1200), ({"lead": {"quiet_wake_s": 900}}, 900),
    ({"lead": {"quiet_wake_s": 599}}, 1200), ({"lead": {"quiet_wake_s": 3601}}, 1200),
    ({"lead": {"quiet_wake_s": True}}, 1200),
])
def test_the_quiet_backstop_is_the_policys_within_the_schemas_bounds(policy, expected):
    from aew.policy import execution

    assert execution.quiet_wake_s(policy) == expected


def test_the_schema_refuses_a_quiet_backstop_outside_its_bounds():
    from aew import schemas
    from aew.errors import ValidationFailed

    schemas.validate_property("execution", "lead", {"quiet_wake_s": 1200}, source="test")
    for bad in (599, 3601, "1200"):
        with pytest.raises(ValidationFailed):
            schemas.validate_property("execution", "lead", {"quiet_wake_s": bad}, source="test")


# ---------------------------------------------------------------------------------------------- what the probes found


def test_a_running_shell_with_no_exit_is_a_command_never_a_failing_test():
    run = Run()
    running = part("shell", {"command": PYTEST, "description": "bg"}, metadata={"status": "running"},
                   status="running")
    assert run.step(running) == []
    assert run.digest()["last_command"]["exit"] is None
    assert run.digest()["last_test"]["result"] == P.UNKNOWN
    for _ in range(3):  # never stuck either
        assert run.step(part("shell", {"command": PYTEST}, metadata={}, status="running")) == []


def test_a_streaming_part_is_not_read_until_it_is_whole():  # the control of the case above
    run = Run()
    run.step(part("write", {"path": "src/b/x.py"}, status="streaming"))
    assert run.digest()["files_touched"]["count"] == 0


def test_an_absolute_input_path_and_the_relative_metadata_name_are_one_file(tmp_path: Path):
    """On Linux `state.input.path` is what the model sent and `metadata.files[].file` is workspace-relative (the
    steering PR 1 probe's Linux check): both are one file."""
    run = Run(workspace=str(tmp_path))
    run.step(part("edit", {"path": str(tmp_path / "big_0.txt"), "oldString": "a", "newString": "b"},
                  metadata={"files": [{"file": "big_0.txt", "status": "modified"}], "truncated": False}))
    assert run.digest()["files_touched"] == {"paths": ["big_0.txt"], "count": 1}


def test_a_meter_state_written_before_the_digest_is_still_trusted(lab: Lab, wakes: list[Path]):
    state = L._empty_state()
    del state["progress"]
    (lab.run_dir / runlog.LIVE_STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
    meter = lab.meter()
    assert meter.state["truncated"] is False and P.valid_state(meter.state["progress"])


def test_a_trigger_whose_digest_write_failed_wakes_with_the_next_write(lab: Lab, wakes: list[Path],
                                                                       monkeypatch: pytest.MonkeyPatch):
    meter = lab.meter()
    lab.step(write("src/b/x.py"))
    real = runlog.write_progress

    def failing_write(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(runlog, "write_progress", failing_write)
    meter.poll()
    assert wakes == [] and meter.progress_errors == 1
    monkeypatch.setattr(runlog, "write_progress", real)
    meter.poll()
    assert wakes == [lab.root / ".aew"]
    meter.poll()
    assert len(wakes) == 1  # owed once, then the per-second rewrite again wakes no one


def test_a_publish_whose_write_fails_leaves_the_committed_digest_as_it_was(lab: Lab, wakes: list[Path],
                                                                           monkeypatch: pytest.MonkeyPatch):
    """A publish with no new read (a prompt-state change) advances the committed state's digest only once its
    writes succeed, as the meter does for the rest of its state."""
    tracker = P.Tracker(run="R-1", workspace=None, scope_paths=SCOPE, clock=lab.clock)
    meter = L.Meter(lab.client, source={"kind": "run", "id": "R-1"}, version="2.0.18",
                    semantics_table=OpenCodeAdapter.token_semantics, s_pot=1,
                    state_path=lab.run_dir / runlog.LIVE_STATE_FILE, live_path=lab.run_dir / runlog.LIVE_FILE,
                    progress=tracker, progress_path=lab.run_dir / runlog.PROGRESS_FILE)

    def full(_state):
        raise OSError("disk full")

    monkeypatch.setattr(meter, "_persist", full)
    with pytest.raises(OSError):
        meter.set_prompt_state("posted")  # an idle worker whose contract is posted would start its idle clock
    assert meter.state["progress"]["idle_since"] is None
