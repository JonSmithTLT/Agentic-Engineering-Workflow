"""The shim's ``serve`` step (the ruling of 2026-11-08): it starts the Lead's server, records the address it announces,
gives it to the TUI, and ends the server with the TUI. A server that doesn't serve never starts the TUI."""

from __future__ import annotations

import _thread
import json
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

from aew.harness.containment import netns, shim
from aew.harness.opencode import adapter, lead

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SERVER = """import json, pathlib, sys
pathlib.Path(sys.argv[1]).write_text("started")
print("anything before its address")
print(json.dumps({"url": sys.argv[2]}), flush=True)
sys.stdin.buffer.read()
pathlib.Path(sys.argv[1]).write_text("lease ended")
"""
TUI = """import pathlib, sys
pathlib.Path(sys.argv[1]).write_text(sys.argv[2])
sys.exit(int(sys.argv[3]))
"""


def _run(tmp_path: Path, url: str = "http://127.0.0.1:4100", server: str = SERVER, code: int = 3,
         tui_text: str = TUI) -> tuple[subprocess.CompletedProcess[str], Path]:
    served, tui = tmp_path / "server.py", tmp_path / "tui.py"
    served.write_text(server, encoding="utf-8")
    tui.write_text(tui_text, encoding="utf-8")
    spec = {"in": [], "out": [], "serve": {"argv": [sys.executable, str(served), str(tmp_path / "state"), url],
                                           "log": str(tmp_path / "server.log"),
                                           "url_file": str(tmp_path / "url.json")}}
    argv = netns.shim_argv(spec, [sys.executable, str(tui), str(tmp_path / "got"), shim.SERVER_URL, str(code)])
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL,
                          creationflags=NO_WINDOW), tmp_path


def test_the_tui_gets_the_address_the_server_announced_and_the_server_ends_with_it(tmp_path: Path) -> None:
    done, _ = _run(tmp_path)
    assert done.returncode == 3, done.stderr  # the harness's status
    assert (tmp_path / "got").read_text() == "http://127.0.0.1:4100"
    assert json.loads((tmp_path / "url.json").read_text()) == {"url": "http://127.0.0.1:4100"}
    assert (tmp_path / "state").read_text() == "lease ended"
    assert "server ended" not in done.stderr  # its lease ended with the TUI: no one lost it


@pytest.mark.parametrize("url", ["http://example.invalid:4100", "http://127.0.0.1:4100@example.invalid"])
def test_a_server_announcing_anywhere_but_loopback_gets_no_tui(tmp_path: Path, url: str) -> None:
    done, _ = _run(tmp_path, url=url)
    assert done.returncode == shim.EXIT_SETUP and "not a http://127.0.0.1 address" in done.stderr
    assert not (tmp_path / "got").exists() and not (tmp_path / "url.json").exists()


class _Harness:
    def __init__(self) -> None:
        self.sent: list[int] = []

    def send_signal(self, sig: int) -> None:
        self.sent.append(sig)


def _handlers(monkeypatch: pytest.MonkeyPatch, *, on_its_terminal: bool) -> tuple[dict[int, Any], _Harness]:
    handlers: dict[int, Any] = {}
    monkeypatch.setattr(signal, "signal", lambda sig, handler: handlers.__setitem__(sig, handler))
    harness = _Harness()
    shim.pass_signals(cast("subprocess.Popen[bytes]", harness), on_its_terminal=on_its_terminal)
    return handlers, harness


def test_ctrl_c_is_left_to_the_terminal_where_it_reaches_the_harness_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Forwarded on Windows, it raises (`Unsupported signal`) and kills the shim with the TUI still running: the
    designer's check of 2026-11-08, item 9. A real console's Ctrl+C is the Windows launch's own check."""
    handlers, harness = _handlers(monkeypatch, on_its_terminal=True)
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert harness.sent == []
    handlers[signal.SIGTERM](signal.SIGTERM, None)  # nobody else tells the harness to end
    assert harness.sent == [signal.SIGTERM]


def test_a_windows_console_and_a_terminal_of_its_own_deliver_ctrl_c_and_nothing_else_does(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    assert shim.terminal_signals_reach_it({})
    monkeypatch.setattr(sys, "platform", "linux")
    assert not shim.terminal_signals_reach_it({}) and shim.terminal_signals_reach_it({"ctty": True})


def test_an_earlier_sessions_address_is_gone_before_the_server_starts(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A broker that read it would post to a server that is no longer this session's."""
    monkeypatch.setenv(adapter.BIN_ENV, sys.executable)
    (tmp_path / lead.SERVER_URL_FILE).write_text(json.dumps({"url": "http://127.0.0.1:1"}), encoding="utf-8")
    spec = lead.serve_spec(tmp_path)
    assert spec["url_file"] == str(tmp_path / lead.SERVER_URL_FILE) and not Path(spec["url_file"]).exists()


def test_ctrl_c_is_forwarded_where_the_harness_has_no_terminal_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers, harness = _handlers(monkeypatch, on_its_terminal=False)
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert harness.sent == [signal.SIGINT]


def test_a_server_that_exits_gets_no_tui(tmp_path: Path) -> None:
    done, _ = _run(tmp_path, server="import sys\nsys.exit(1)\n")
    assert done.returncode == shim.EXIT_SETUP and "no address" in done.stderr
    assert "`aew doctor`" in done.stderr and str(tmp_path / "server.log") in done.stderr  # what to do about it
    assert not (tmp_path / "got").exists()


def test_a_server_that_dies_mid_session_ends_the_session_and_says_so(tmp_path: Path) -> None:
    """Nothing restarts it, and the TUI would go on reconnecting."""
    server = "import json\nprint(json.dumps({'url': 'http://127.0.0.1:4100'}), flush=True)\n"
    # The TUI's own end is inside _run's limit: on Windows a timed-out `run` still waits for whoever holds its pipes.
    done, _ = _run(tmp_path, server=server, tui_text="import time\ntime.sleep(90)\n")
    assert "the Lead's server ended" in done.stderr and "says how to go on" in done.stderr
    assert done.returncode == shim.EXIT_SERVER_LOST  # whatever the TUI exits with when it is ended


def test_a_long_wait_for_the_server_says_so_once(capsys: pytest.CaptureFixture[str],
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shim, "SERVE_NOTICE_S", 0.0)
    monkeypatch.setattr(shim, "SERVE_TIMEOUT_S", 1.0)
    shim._wait_for(threading.Event())
    assert capsys.readouterr().err.count("waiting for the Lead's server") == 1


def test_ctrl_c_before_the_announcement_ends_the_server_and_gives_no_traceback(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A server that never announces and survives the Ctrl+C: the shim's wait still sees it, on Windows too, whose plain
    wait can't be interrupted. `shim.main` runs here because a Windows test can't send a child a Ctrl+C with no
    window."""
    served = tmp_path / "server.py"
    served.write_text("import pathlib, sys, time\npathlib.Path(sys.argv[1]).write_text('started')\ntime.sleep(600)\n",
                      encoding="utf-8")
    started = tmp_path / "started"
    spec = {"in": [], "out": [], "serve": {"argv": [sys.executable, str(served), str(started)],
                                           "log": str(tmp_path / "server.log"), "url_file": str(tmp_path / "url.json")}}
    real, made = subprocess.Popen, []

    def popen(*args: Any, **kwargs: Any) -> Any:
        made.append(real(*args, **{**kwargs, "creationflags": NO_WINDOW}))
        return made[-1]

    monkeypatch.setattr(subprocess, "Popen", popen)

    def press() -> None:
        while not started.exists():
            time.sleep(0.05)
        _thread.interrupt_main()

    threading.Thread(target=press, daemon=True).start()
    began = time.monotonic()
    assert shim.main([json.dumps(spec), "--", sys.executable, "-c", "raise SystemExit(9)"]) == 130
    assert time.monotonic() - began < 30, "the wait did not see it"
    assert made[0].wait(30) is not None and len(made) == 1  # the server is gone, and no TUI started


def test_a_launch_that_never_started_the_tui_is_no_success() -> None:
    failed = lead._outcome({"ok": True, "exit": shim.EXIT_SETUP}, "2.2.6")
    assert failed["ok"] is False and "aew doctor" in failed["not_started"]
    lost = lead._outcome({"ok": True, "exit": shim.EXIT_SERVER_LOST}, "2.2.6")
    assert lost["ok"] is False and "`aew opencode` again" in lost["server_lost"] and "not_started" not in lost
    held = lead._outcome({"ok": True, "exit": shim.EXIT_SERVER_LOST, "seat": "held; `aew lead takeover`"}, "2.2.6")
    assert "as `seat` says" in held["server_lost"] and "`aew opencode` again" not in held["server_lost"]
    ran = lead._outcome({"ok": True, "exit": 3}, "2.2.6")  # the TUI's own status
    assert ran == {"ok": True, "exit": 3, "opencode": "2.2.6"}


def test_a_server_lost_with_a_run_in_flight_says_a_step_that_works_and_following_it_works(tmp_path: Path) -> None:
    """Review, m2. On the `--acquire` route the credential died with the session and the seat stays held for the run, so
    `aew opencode` alone would be refused. The result says to go as `seat` says, and that step is followed here."""
    import fake_opencode
    from fake_harness import SCRIPTS_ENV
    from harness_acceptance import WID, lead, operator_takeover, plan_ticket
    from harness_conformance import FakeOpenCodeDriver, sync_dir

    from aew.engine.api import Engine

    driver = FakeOpenCodeDriver()
    lab = driver.create_lab(tmp_path, lead_session=True)
    try:
        lab.lead("lead", "release")  # the operator's own seat is given up: the Lead's session acquires it
        lab.project.token = ""
        lab.script("default", {"steps": [{"do": "hang"}], "server": {"tool_parts": True, "live_usage": {}}})
        session = driver.start_lead(lab, "lead-lost", [
            *plan_ticket(tmp_path), lead("work", "assign", WID, "--launch"),
            {"do": "wait_file", "path": str(sync_dir(tmp_path) / "never"), "timeout": 300}], acquire=True)

        def active() -> list[str]:
            state = Engine.discover(lab.root).store.current()
            return [i for i, inv in state["invocations"].items() if inv["status"] == "active" and inv.get("runs")]

        lab.until(active, what="the Lead's run to be in flight", timeout=120)
        kill = Path(lab.env[SCRIPTS_ENV]) / fake_opencode.KILL_LEAD_SERVER
        kill.write_text("", encoding="utf-8")
        res, _steps = session.result(timeout=120)
        out = json.loads(res.stdout)
        assert res.returncode == 1 and out["ok"] is False and out["exit"] == shim.EXIT_SERVER_LOST, res.stdout
        assert out["seat"].startswith("held;") and "`aew lead takeover`" in out["seat"], out["seat"]
        assert "continue as `seat` says" in out["server_lost"] and "again" not in out["server_lost"], out["server_lost"]

        kill.unlink()
        lab.project.token = operator_takeover(lab, "the Lead's server was lost")  # what `seat` says
        again, _ = driver.lead(lab, "lead-after", [{"do": "aew", "args": ["status", "--json"]}])
        assert again.returncode == 0, again.stderr
    finally:
        lab.cleanup()
