"""The shim's ``serve`` step (the ruling of 2026-11-08): it starts the Lead's server, records the address it announces,
gives it to the TUI, and ends the server with the TUI. A server that doesn't serve never starts the TUI."""

from __future__ import annotations

import json
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from aew.harness.containment import netns, shim
from aew.harness.opencode import adapter, lead

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


def _run(tmp_path: Path, url: str = "http://127.0.0.1:4100", server: str = SERVER, code: int = 3) -> tuple[
        subprocess.CompletedProcess[str], Path]:
    served, tui = tmp_path / "server.py", tmp_path / "tui.py"
    served.write_text(server, encoding="utf-8")
    tui.write_text(TUI, encoding="utf-8")
    spec = {"in": [], "out": [], "serve": {"argv": [sys.executable, str(served), str(tmp_path / "state"), url],
                                           "log": str(tmp_path / "server.log"),
                                           "url_file": str(tmp_path / "url.json")}}
    argv = netns.shim_argv(spec, [sys.executable, str(tui), str(tmp_path / "got"), shim.SERVER_URL, str(code)])
    return subprocess.run(argv, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL), tmp_path


def test_the_tui_gets_the_address_the_server_announced_and_the_server_ends_with_it(tmp_path: Path) -> None:
    done, _ = _run(tmp_path)
    assert done.returncode == 3, done.stderr  # the harness's status
    assert (tmp_path / "got").read_text() == "http://127.0.0.1:4100"
    assert json.loads((tmp_path / "url.json").read_text()) == {"url": "http://127.0.0.1:4100"}
    assert (tmp_path / "state").read_text() == "lease ended"


def test_a_server_announcing_anywhere_but_loopback_gets_no_tui(tmp_path: Path) -> None:
    done, _ = _run(tmp_path, url="http://example.invalid:4100")
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
    assert not (tmp_path / "got").exists()
