"""The console of a background operator endpoint, and what it runs with: a window shown when a challenge needs one, and
no code on any command line. No test opens a window: the spawn is a fake."""

from __future__ import annotations

import os
import sys

import pytest

from aew import errors
from aew.harness import operator_autostart as A
from aew.harness import operator_window as W

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal is POSIX's")


def test_with_no_display_there_is_no_window_to_open():
    assert W.terminal_command("/dev/pts/9", env={}, which=lambda name: "/usr/bin/" + name) == "no display"


def test_with_no_terminal_emulator_there_is_no_window_to_open():
    assert W.terminal_command("/dev/pts/9", env={"DISPLAY": ":0"}, which=lambda name: None) == \
        "no terminal emulator on PATH"


@pytest.mark.parametrize("env", [{"DISPLAY": ":0"}, {"WAYLAND_DISPLAY": "wayland-0"}])
def test_the_first_terminal_emulator_on_the_path_shows_the_device_and_nothing_else(env):
    found = W.terminal_command("/dev/pts/9", env=env,
                               which=lambda name: f"/usr/bin/{name}" if name == "xterm" else None)
    assert found == ["/usr/bin/xterm", "-e", "sh", "-c", 'exec cat "$0"', "/dev/pts/9"]


@posix_only
def test_the_window_gets_the_text_through_the_terminal_and_never_on_its_command_line(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(W.shutil, "which", lambda name: "/usr/bin/xterm" if name == "xterm" else None)
    started: list[list[str]] = []
    console = W.WindowConsole(spawn=started.append)
    try:
        console("code ABC123\n")
        console("and the result\n")
        assert len(started) == 1, "one window for one challenge"
        assert not any("ABC123" in word for word in started[0])
        with open(started[0][-1], "rb", buffering=0) as device:
            assert device.read(64) == b"code ABC123\n"
            assert device.read(64) == b"and the result\n"
    finally:
        console.close()


@posix_only
def test_closing_the_console_ends_what_the_window_reads(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(W.shutil, "which", lambda name: "/usr/bin/xterm" if name == "xterm" else None)
    started: list[list[str]] = []
    console = W.WindowConsole(spawn=started.append)
    console("code\n")
    fd = os.open(started[0][-1], os.O_RDONLY)
    try:
        assert os.read(fd, 16) == b"code\n"
        console.close()
        with pytest.raises(OSError):  # EIO on Linux: the other end has gone
            assert os.read(fd, 16) == b""
            raise OSError("end of file")
    finally:
        os.close(fd)


def test_no_window_refuses_and_tells_the_endpoint_to_give_up_its_lock(monkeypatch):
    monkeypatch.setattr(W.WindowConsole, "_write_windows", lambda self, text: "no display")
    monkeypatch.setattr(W.WindowConsole, "_write_posix", lambda self, text: "no display")
    console = W.WindowConsole()
    retired: list[bool] = []
    console.on_unavailable = lambda: retired.append(True)
    with pytest.raises(errors.OperatorAuthorizationRequired) as refused:
        console("code\n")
    assert retired == [True] and "aew operator serve --dev" in refused.value.message


def test_a_new_challenge_keeps_the_window_the_last_one_was_closing(monkeypatch):
    monkeypatch.setattr(W.WindowConsole, "_write_windows", lambda self, text: None)
    monkeypatch.setattr(W.WindowConsole, "_write_posix", lambda self, text: None)
    console = W.WindowConsole()
    console.done()
    timer = console._timer
    assert timer is not None
    console("code\n")
    assert console._timer is None and timer.finished.is_set() or not timer.is_alive()
    console.done()
    assert console._timer is not None
    console._timer.cancel()


def test_the_endpoint_gets_neither_the_lead_credential_nor_a_fed_provider_variable():
    env = A.endpoint_env({"AEW_LEAD_TOKEN": "synthetic", "AEW_INVOCATION_TOKEN": "synthetic",
                          "SOME_API_KEY": "synthetic", "AEW_LEAD_BROKER": "kept", "DISPLAY": ":0"}, ["SOME_API_KEY"])
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "SOME_API_KEY"} & set(env)
    assert env["AEW_LEAD_BROKER"] == "kept", "the endpoint refuses on it"
    assert env["DISPLAY"] == ":0", "the window needs it"
