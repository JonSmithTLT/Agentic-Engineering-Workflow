"""A supervised run publishes its spend (F25 for M4-H, slice L2): the OpenCode adapter's meter, its live file and its
prompt state, in every turn state.

The adapter runs for real against the fake V2 server in this process, served over HTTP on loopback
(``fake_opencode.handler_for``): ``Server.start`` is replaced by a stub that records when it was called and hands the
adapter that server, so launch, health, the session, the event stream, the watch loop and the meter all run their real
code. Timing-dependent guarantees are driven by the meter's poll iterations (``_meter_tick``), not by the wall clock."""

from __future__ import annotations

import http.server
import inspect
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fake_opencode as F
import pytest

from aew import schemas
from aew.errors import HarnessIncompatible, HarnessLaunchFailed
from aew.harness import runlog
from aew.harness import usage_live as L
from aew.harness.contract import CREDENTIAL_RE, LaunchContract
from aew.harness.opencode import adapter as A
from aew.harness.opencode.client import Client, OpenCodeUnavailable

RUN = "R-INV-0001-1"
PROFILE = {"profile": "standard", "harness": "opencode", "provider": "fakeprov", "model": "fake-model",
           "effort": "high", "max_steps": None, "deadline_s": None, "selected_by": "policy", "rule": "default",
           "policy_sha256": "1" * 64}
PROMPT_TEXT = "PACK-TEXT-THAT-MUST-NOT-REACH-THE-LIVE-FILE"


def wait_for(cond: Any, timeout: float = 10.0, what: str = "condition") -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out waiting for {what}")
        time.sleep(0.02)


class StubProc:
    pid = 4242

    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        return self.returncode


class StubServer:
    """What ``Server.start`` returns, for a fake V2 server already serving on loopback."""

    def __init__(self, url: str, password: str) -> None:
        self.url, self.password = url, password
        self.proc = StubProc()
        self.started_s = 0.01
        self.client = Client(url, password)
        self.closed = False

    def alive(self) -> bool:
        return self.proc.returncode is None

    def close(self, wait_s: float = 5.0) -> int | None:
        self.closed = True
        self.proc.returncode = 0
        return 0


class Rig:
    """The fake server on loopback, a run directory, and an adapter wired to them."""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch, **knobs: Any) -> None:
        self.root = root
        self.app = F.local_app(root / "fake", knobs)
        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), F.handler_for(self.app))
        self.http.daemon_threads = True
        threading.Thread(target=self.http.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.http.server_address[1]}"
        self.run_dir = root / "aew" / "local" / "harness" / "runs" / RUN
        self.run_dir.mkdir(parents=True)
        self.workspace = root / "ws"
        self.workspace.mkdir()
        self.events: list[dict[str, Any]] = []
        self.started: list[dict[str, Any]] = []  # each Server.start call, with the live file as it was then
        self.server: StubServer | None = None
        monkeypatch.setattr(A, "binary_command", lambda: ["fake-opencode"])
        monkeypatch.setattr(A.Server, "start", self._start)

    def _start(self, spawn: Any, command: list[str], *, env: dict[str, str], cwd: str, log_path: Path,
               timeout: float = 0) -> StubServer:
        self.started.append({"live": runlog.read_live(self.run_dir)})
        self.app.config = json.loads(env["OPENCODE_CONFIG_CONTENT"])  # as the real server loads it
        self.server = StubServer(self.url, self.app.password)
        return self.server

    def contract(self) -> LaunchContract:
        return LaunchContract(
            run=RUN, invocation="INV-0001", work_unit="T-0001", role="implementer", scope="ticket",
            card={"id": "python_engineer", "version": 1, "sha256": "0" * 64}, execution_profile=dict(PROFILE),
            workspace=str(self.workspace), expected_kinds=["implementation_report"],
            operations=["submit.implementation_report"], pack_path="/p", pack_sha256="2" * 64,
            pack_text=PROMPT_TEXT, continuation=None, run_dir=str(self.run_dir),
            scratch=str(self.run_dir / "scratch"), extra={"provider_env": []})

    def adapter(self, cls: type[A.OpenCodeAdapter] = A.OpenCodeAdapter) -> A.OpenCodeAdapter:
        return cls(SimpleNamespace(spawn=None), self.run_dir, self.events.append)  # type: ignore[arg-type]  # stubbed start

    def live(self) -> dict[str, Any]:
        sample = runlog.read_live(self.run_dir)
        assert sample is not None, "no live sample"
        schemas.validate("usage-live", sample, source="live sample")
        return sample

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture
def rig(tmp_path, monkeypatch):
    r = Rig(tmp_path, monkeypatch)
    yield r
    r.close()


def run_to_end(rig: Rig, adapter: A.OpenCodeAdapter) -> None:
    adapter.launch(rig.contract(), {"PATH": os.environ.get("PATH", "")})
    wait_for(lambda: not adapter.inspect()["alive"], what="the turn to end")


class Manual(A.OpenCodeAdapter):
    """The meter is bound but its thread never starts: each poll is one explicit ``_meter_tick``."""

    def _bind_meter(self) -> None:
        assert self.meter is not None
        self.meter.client = self.meter_client()


# ---------------------------------------------------------------------------------------------- the launch order


def test_unsent_is_written_before_the_server_starts(rig):
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    [start] = rig.started
    assert start["live"] is not None
    assert (start["live"]["seq"], start["live"]["prompt_state"], start["live"]["source"]) == (
        0, "unsent", {"kind": "run", "id": RUN})
    adapter.terminate()


def test_a_failed_seq0_write_refuses_the_launch(rig, monkeypatch):
    def refuse(path: Path, sample: dict[str, Any]) -> None:
        raise PermissionError("refused")

    monkeypatch.setattr(runlog, "write_live", refuse)
    adapter = rig.adapter()
    with pytest.raises(HarnessLaunchFailed, match="no server was started"):
        adapter.launch(rig.contract(), {})
    assert rig.started == []  # refused before Server.start


def test_no_live_file_without_a_server_is_never_launched(rig, monkeypatch):
    """With a failed seq-0 write no server exists, so a run directory without a live file had no server: such a run
    is never launched (plan v4 R3-m3), and nothing this adapter does leaves a live file behind."""
    monkeypatch.setattr(runlog, "write_live", lambda path, sample: (_ for _ in ()).throw(PermissionError("no")))
    adapter = rig.adapter()
    with pytest.raises(HarnessLaunchFailed):
        adapter.launch(rig.contract(), {})
    adapter.terminate()
    assert rig.started == [] and runlog.read_live(rig.run_dir) is None
    assert not (rig.run_dir / runlog.LIVE_FILE).exists()


def test_the_meter_polls_before_the_contract_is_delivered(rig):
    seen: dict[str, Any] = {}

    class Watched(A.OpenCodeAdapter):
        def deliver_contract(self, contract: LaunchContract) -> None:
            assert self.meter is not None
            wait_for(lambda: self.meter is not None and self.meter.last_success is not None, what="a meter poll")
            seen["polled"] = self.meter.last_success is not None
            seen["live"] = runlog.read_live(self.run_dir)
            super().deliver_contract(contract)

    adapter = rig.adapter(Watched)
    run_to_end(rig, adapter)
    assert seen["polled"] and seen["live"]["state"] == "live"
    adapter.terminate()


def test_the_prompt_state_is_posting_before_the_prompt_post(rig):
    seen: list[str] = []

    class Watched(A.OpenCodeAdapter):
        def _prompt(self, text: str, delivery: str | None = None) -> str:
            seen.append(runlog.read_live(self.run_dir)["prompt_state"])  # type: ignore[index]
            return super()._prompt(text, delivery)

    adapter = rig.adapter(Watched)
    run_to_end(rig, adapter)
    assert seen[0] == "posting"
    assert rig.live()["prompt_state"] == "posted"
    adapter.terminate()


def test_a_launch_failed_before_the_prompt_is_never_launched(rig):
    rig.app.knobs["version"] = "1.0.0"  # a V1 server: health refuses it, before any prompt
    adapter = rig.adapter()
    with pytest.raises(HarnessIncompatible):
        adapter.launch(rig.contract(), {})
    adapter.terminate()
    final = rig.live()
    assert (final["state"], final["prompt_state"]) == ("final", "unsent")
    assert final["steps"] == 0 and rig.server is not None and rig.server.closed


def test_a_start_that_died_after_the_prompt_is_unknown(rig):
    """The prompt went out and then the server died: the live file is past `unsent` with no final sample, which the
    total reads as unknown (plan v4 §2.5), never as a run that was never launched."""

    class Dies(A.OpenCodeAdapter):
        def deliver_contract(self, contract: LaunchContract) -> None:
            super().deliver_contract(contract)
            assert self.server is not None
            self.server.proc.returncode = 1  # type: ignore[union-attr]
            rig.http.shutdown()
            raise OpenCodeUnavailable("the server died after taking the prompt")

    adapter = rig.adapter(Dies)
    with pytest.raises(OpenCodeUnavailable):
        adapter.launch(rig.contract(), {})
    adapter.terminate()
    final = rig.live()
    assert final["prompt_state"] == "posting" and final["state"] == "server_gone"


# ---------------------------------------------------------------------------------------------- freshness


def test_a_completed_call_is_published_within_two_poll_iterations(rig):
    adapter = rig.adapter(Manual)
    run_to_end(rig, adapter)
    adapter._meter_tick()
    before = rig.live()["steps"]
    sid = adapter.session
    assert sid is not None
    mid = rig.app.start_call(sid, created=time.time() * 1000)
    rig.app.end_call(sid, mid, tokens={"input": 900, "output": 90, "reasoning": 0, "cache": {"read": 0, "write": 0}})
    ticks = 0
    while rig.live()["steps"] == before:
        ticks += 1
        assert ticks <= 2, "a completed call was not published within two poll iterations"
        adapter._meter_tick()
    assert rig.live()["steps"] == before + 1
    adapter.terminate()


def stays_fresh(rig: Rig, monkeypatch: pytest.MonkeyPatch, turn: str) -> None:
    monkeypatch.setattr(A, "METER_POLL_S", 0.05)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter.turn = turn  # nothing watches the session now; the meter samples it all the same
    seq = rig.live()["seq"]
    wait_for(lambda: rig.live()["seq"] >= seq + 2, what="two more samples")
    adapter.terminate()


def test_a_held_run_stays_fresh(rig, monkeypatch):
    stays_fresh(rig, monkeypatch, "held")  # after a Lead interrupt


def test_a_run_between_turns_stays_fresh(rig, monkeypatch):
    stays_fresh(rig, monkeypatch, "ended")  # its turn is over; the next prompt has not come


def test_the_turn_over_snapshot_is_published(rig, monkeypatch):
    monkeypatch.setattr(A, "METER_POLL_S", 60.0)  # only the end of the turn can bring a sample this soon
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    wait_for(lambda: rig.live()["steps"] == 1, timeout=5.0, what="the turn's step in the live file")
    adapter.terminate()


def test_a_slow_adapter_request_never_delays_the_live_sample(rig, monkeypatch):
    monkeypatch.setattr(A, "METER_POLL_S", 0.05)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    assert adapter.client is not None
    real = adapter.client.request

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(5.0)
        return real(*args, **kwargs)

    monkeypatch.setattr(adapter.client, "request", slow)  # the adapter's own client: every request takes 5 s
    seq = rig.live()["seq"]
    wait_for(lambda: rig.live()["seq"] >= seq + 2, timeout=2.0, what="samples while the adapter's client is slow")
    monkeypatch.setattr(adapter.client, "request", real)
    adapter.terminate()


# ---------------------------------------------------------------------------------------------- terminate


def test_terminate_takes_a_fresh_final_sample(rig):
    adapter = rig.adapter(Manual)
    run_to_end(rig, adapter)
    assert adapter.snapshot is not None  # the turn's snapshot exists, and is not what the final sample uses (m7)
    sid = adapter.session
    assert sid is not None
    mid = rig.app.start_call(sid, created=time.time() * 1000)
    rig.app.end_call(sid, mid, tokens={"input": 50, "output": 5, "reasoning": 0, "cache": {"read": 0, "write": 0}})
    adapter.terminate()
    final = rig.live()
    assert final["state"] == "final" and final["steps"] == 2
    assert final["tokens"]["input"] == 100 + 50  # the fake's model step, and the call after the turn


def busy_server(rig: Rig, sessions: int = 10) -> None:
    """Sessions whose totals moved, so each poll reads their messages: a poll is many requests long."""
    for _ in range(sessions):
        sid = rig.app.add_session(model={"providerID": "fakeprov", "id": "fake-model", "variant": "default"})
        rig.app.record_usage(sid, {"input": 10, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}})


class SlowClient:
    """A slow but answering server: every request takes ``delay`` (under the meter's 2 s timeout)."""

    def __init__(self, real: Any, delay: float = 0.5) -> None:
        self.real, self.delay = real, delay
        self.started = threading.Event()

    def get(self, path: str, params: Any = None, timeout: float = 30.0) -> Any:
        self.started.set()
        time.sleep(min(self.delay, timeout))
        return self.real.get(path, params, timeout=timeout)


def test_the_final_sample_fits_inside_terminate_s(rig, monkeypatch):
    """The meter's whole share of ``terminate``, the thread's join included, is at most ``METER_FINAL_S`` (4 s), and
    that share plus the lease's own 3 s wait fits the supervisor's ``TERMINATE_S``, whatever the server does."""
    from aew.harness import supervisor

    assert A.METER_FINAL_S + 3.0 <= supervisor.TERMINATE_S
    adapter = rig.adapter(Manual)
    run_to_end(rig, adapter)
    assert adapter.meter is not None

    class Hanging:
        def get(self, path: str, params: Any = None, timeout: float = 30.0) -> Any:
            time.sleep(timeout)  # every request runs to its timeout
            raise OpenCodeUnavailable("timed out")

    adapter.meter.client = Hanging()
    monkeypatch.setattr(A, "METER_FINAL_S", 1.0)
    monkeypatch.setattr(A, "METER_WRITE_MARGIN_S", 0.2)
    t0 = time.monotonic()
    adapter.terminate()
    assert time.monotonic() - t0 < 1.0 + 0.5
    assert rig.live()["state"] == "server_gone"


def test_terminate_never_waits_for_a_poll_in_flight(rig):
    """A poll is in flight on a slow server when the run ends: the meter's share of ``terminate`` stays within
    ``METER_FINAL_S`` (the poll is cancelled at its next request, never waited for), and the final sample is fresh
    (PR #197 review, M1)."""
    adapter = rig.adapter()  # the real meter thread
    run_to_end(rig, adapter)
    busy_server(rig)
    assert adapter.meter is not None
    slow = SlowClient(adapter.meter.client)
    adapter.meter.client = slow
    assert slow.started.wait(5), "the meter thread did not start a poll"
    t0 = time.monotonic()
    adapter._final_sample()  # the meter's share of terminate
    took = time.monotonic() - t0
    assert took <= A.METER_FINAL_S + 0.3, took
    final = rig.live()
    assert final["state"] in ("final", "server_gone")
    adapter.terminate()
    assert rig.live() == final  # a dropped poll never writes after the final sample


def test_posting_never_waits_for_a_poll_in_flight(rig, monkeypatch):
    """The prompt's ``posting`` write happens while a poll on a slow server is in flight: it never waits for that
    poll's requests, so the prompt is not delayed (PR #197 review, M1)."""
    busy_server(rig)
    clients: list[SlowClient] = []
    original = A.OpenCodeAdapter.meter_client

    def slow_client(self: A.OpenCodeAdapter) -> Any:
        clients.append(SlowClient(original(self)))
        return clients[-1]

    monkeypatch.setattr(A.OpenCodeAdapter, "meter_client", slow_client)
    waits: dict[str, float] = {}
    original_set = L.Meter.set_prompt_state

    def timed(self: L.Meter, state: str) -> None:
        if state == "posting":
            assert clients and clients[0].started.wait(5), "no poll was in flight"
        t0 = time.monotonic()
        original_set(self, state)
        waits[state] = time.monotonic() - t0

    monkeypatch.setattr(L.Meter, "set_prompt_state", timed)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter.terminate()
    assert waits["posting"] < 0.3 and waits["posted"] < 0.3, waits


def test_terminate_still_closes_the_server_after_a_failed_final_write(rig, monkeypatch):
    adapter = rig.adapter(Manual)
    run_to_end(rig, adapter)
    monkeypatch.setattr(runlog, "write_live", lambda path, sample: (_ for _ in ()).throw(PermissionError("no")))
    adapter.terminate()  # never raises
    assert rig.server is not None and rig.server.closed and adapter.meter_errors >= 1



def test_no_live_sample_is_written_after_terminate_returns(rig, monkeypatch):
    """``terminate``'s final write fails, so the meter has not ended; a poll whose requests were all done before the
    cancel then reaches its commit on the meter's daemon thread. It writes nothing: once polls are cancelled no poll
    commits (PR #197 review, N1)."""
    adapter = rig.adapter(Manual)
    run_to_end(rig, adapter)
    meter = adapter.meter
    assert meter is not None
    read_done, go = threading.Event(), threading.Event()
    real_read = meter._read_server

    def read_then_hold(state: dict[str, Any]) -> dict[str, Any]:
        out = real_read(state)
        if threading.current_thread().name == "held-poll":
            read_done.set()
            go.wait(10)
        return out

    monkeypatch.setattr(meter, "_read_server", read_then_hold)
    poller = threading.Thread(target=adapter._meter_tick, name="held-poll", daemon=True)
    poller.start()
    assert read_done.wait(10), "the poll's read never finished"
    before = rig.live()
    written: list[dict[str, Any]] = []
    real_write = runlog.write_live

    def refuse_the_final_then_record(path: Path, sample: dict[str, Any]) -> None:
        if threading.current_thread() is not poller:
            raise PermissionError("refused: the final write")
        written.append(sample)
        real_write(path, sample)

    monkeypatch.setattr(runlog, "write_live", refuse_the_final_then_record)
    adapter.terminate()
    assert adapter.meter_errors >= 1 and not meter._ended  # the final sample was not written
    go.set()
    poller.join(10)
    assert not poller.is_alive(), "the poll never returned"
    assert written == [] and rig.live() == before


def test_a_killed_supervisor_leaves_a_non_final_sample(rig):
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter._meter_stop.set()  # the supervisor is killed: nothing takes a final sample
    adapter._meter_wake.set()
    sample = rig.live()
    assert sample["state"] == "live" and sample["prompt_state"] == "posted"


# ---------------------------------------------------------------------------------------------- the live file


def test_live_seq_strictly_increases(rig, monkeypatch):
    written: list[dict[str, Any]] = []
    real = runlog.write_live

    def record(path: Path, sample: dict[str, Any]) -> None:
        written.append(sample)
        real(path, sample)

    monkeypatch.setattr(runlog, "write_live", record)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter.terminate()
    assert len({s["epoch"] for s in written}) == 1
    assert [s["seq"] for s in written] == list(range(len(written)))
    assert written[0]["prompt_state"] == "unsent" and written[-1]["state"] == "final"


def test_the_meter_is_the_only_writer_of_the_live_file(rig, monkeypatch):
    callers: set[str] = set()
    real = runlog.write_live

    def record(path: Path, sample: dict[str, Any]) -> None:
        callers.add(inspect.stack()[1].frame.f_globals["__name__"])
        real(path, sample)

    monkeypatch.setattr(runlog, "write_live", record)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter.terminate()
    assert callers == {"aew.harness.usage_live"}
    assert "LIVE_FILE" not in inspect.getsource(A).replace("runlog.LIVE_FILE, request_timeout_s", "")


def test_a_live_write_wakes_no_waiter(tmp_path, monkeypatch):
    from aew.engine import outbox

    bumps: list[Path] = []
    monkeypatch.setattr(outbox, "bump_wake", lambda root, revision=None: bumps.append(root))
    run_dir = tmp_path / "local" / "harness" / "runs" / RUN
    run_dir.mkdir(parents=True)
    runlog.write_live(run_dir / runlog.LIVE_FILE, {"schema": runlog.LIVE_SCHEMA, "seq": 0})
    assert bumps == []
    runlog.write_record(run_dir, {"run": RUN})  # what does wake waiters
    assert bumps == [tmp_path]


def test_a_malformed_or_foreign_live_file_is_no_sample(tmp_path):
    for text in ("{not json", "[]", json.dumps({"schema": "aew/run-usage/v1"})):
        (tmp_path / runlog.LIVE_FILE).write_text(text, encoding="utf-8")
        assert runlog.read_live(tmp_path) is None
    assert runlog.read_live(tmp_path / "missing") is None


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX symlinks and FIFOs")
def test_a_linked_or_fifo_live_file_is_no_sample(tmp_path):
    real = tmp_path / "elsewhere.json"
    real.write_text(json.dumps({"schema": runlog.LIVE_SCHEMA, "seq": 1}), encoding="utf-8")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / runlog.LIVE_FILE).symlink_to(real)
    assert runlog.read_live(linked) is None
    fifo = tmp_path / "fifo"
    fifo.mkdir()
    os.mkfifo(fifo / runlog.LIVE_FILE)
    assert runlog.read_live(fifo) is None  # returns at once: a FIFO never blocks the read


def test_the_live_file_holds_no_text_path_or_credential(rig):
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    adapter.terminate()
    text = (rig.run_dir / runlog.LIVE_FILE).read_text(encoding="utf-8")
    assert PROMPT_TEXT not in text and str(rig.root) not in text and str(rig.workspace) not in text
    assert "\\" not in text and not CREDENTIAL_RE.search(text)
    assert rig.server is not None and (not rig.server.password or rig.server.password not in text)


def test_a_meter_failure_never_ends_or_delays_the_run(rig, monkeypatch):
    def broken(self: L.Meter) -> dict[str, Any]:
        raise RuntimeError("the meter broke")

    monkeypatch.setattr(L.Meter, "poll", broken)
    monkeypatch.setattr(A, "METER_POLL_S", 0.05)
    adapter = rig.adapter()
    run_to_end(rig, adapter)
    state = adapter.inspect()
    assert (state["exit_code"], state["detail"]) == (0, "the agent's turn ended: succeeded")
    assert adapter.meter_errors >= 1 and any(e.get("event") == "opencode.meter_error" for e in rig.events)
    adapter.terminate()
    assert rig.live()["state"] == "final"


# ---------------------------------------------------------------------------------------------- F19 v5 §2.6.2


def test_opencode_meter_reads_a_supervised_run_server_with_its_password(tmp_path, monkeypatch):
    """F19 meters a supervised worker's server itself: basic auth with the server's password, and a root session it
    finds. ``OpenCodeMeter`` needs nothing else."""
    monkeypatch.setenv("OPENCODE_PASSWORD", "worker-server-password")
    rig = Rig(tmp_path, monkeypatch)
    try:
        assert rig.app.password == "worker-server-password"
        adapter = rig.adapter()
        run_to_end(rig, adapter)
        root = adapter.session
        assert root is not None
        outside = L.OpenCodeMeter(Client(rig.url, "worker-server-password"), root_session=root, version="2.0.18",
                                  s_pot=1, state_path=tmp_path / "f19-state.json",
                                  pinned_model={"providerID": "fakeprov", "id": "fake-model", "variant": "high"})
        sample = outside.poll()
        assert sample is not None and sample["steps"] == 1 and sample["sessions"] == 1
        assert sample["source"] == {"kind": "session", "id": root}
        wrong = L.OpenCodeMeter(Client(rig.url, "not-the-password"), root_session=root, version="2.0.18", s_pot=1,
                                state_path=tmp_path / "wrong.json")
        assert wrong.poll() is None and wrong.errors == 1  # refused (401): no sample, never a zero
        adapter.terminate()
    finally:
        rig.close()


def test_two_meters_on_one_server_agree_and_stay_within_the_request_budget(tmp_path):
    app = F.local_app(tmp_path)
    clients = [F.LocalClient(app), F.LocalClient(app)]
    meters = [L.OpenCodeMeter(c, root_session="ses_root", version="2.0.18", s_pot=1,
                              state_path=tmp_path / f"m{i}.json") for i, c in enumerate(clients)]
    sid = app.add_session()
    tok = {"input": 10, "output": 1, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    for n in range(3):
        mid = app.start_call(sid, created=1000.0 * (n + 1))
        app.end_call(sid, mid, tokens=tok, completed=1000.0 * (n + 1) + 400)
        for c in clients:
            c.requests.clear()
        samples = [m.poll() for m in meters]
        assert samples[0] is not None and samples[1] is not None
        assert samples[0]["tokens"] == samples[1]["tokens"] and samples[0]["steps"] == samples[1]["steps"] == n + 1
        for c in clients:
            # One poll of a one-session server: info (first poll only), one list page, active, and one page of each
            # message type for the session whose totals moved.
            assert len(c.requests) <= 5, c.requests


# ---------------------------------------------------------------------------------------------- who can write it


def test_the_lead_projection_cannot_edit_the_runs_directory():
    """The Lead's projection (the golden) denies every edit, and its shell asks (the responder denies) except for
    `aew` and read-only git: it can read a run's live file, as it can read `run.json` (plan v4 §2.6, m5), but its tools
    cannot write it. Under M4-H's same-uid deployment its processes still could: a residual until F18.6 (F19 v5
    §2.6.2)."""
    golden = json.loads((Path(__file__).resolve().parents[1] / "fixtures" / "opencode" /
                         "projection-lead.golden.json").read_text(encoding="utf-8"))
    [lead] = [a for a in golden["agents"].values() if a.get("mode") == "primary"]
    rules = lead["permissions"]
    edits = [r for r in rules if r["action"] in ("edit", "write", "patch")]
    assert edits == [{"action": "edit", "effect": "deny", "resource": "*"}]
    shells = [r for r in rules if r["action"] == "shell"]
    assert shells[0] == {"action": "shell", "effect": "ask", "resource": "*"}
    assert {r["resource"] for r in shells[1:]} == {"aew *", "git status*", "git diff*", "git log*", "git show*"}
    assert all(r["effect"] == "allow" for r in shells[1:])
