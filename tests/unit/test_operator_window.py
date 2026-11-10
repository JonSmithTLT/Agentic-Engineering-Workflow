"""The console of a background operator endpoint, and what it runs with. No test shows a window: Windows' console calls
are fakes."""

from __future__ import annotations

import pytest

from aew.harness import operator_autostart as A
from aew.harness import operator_window as W


def test_on_linux_a_background_endpoint_has_nothing_to_show_a_code_on(monkeypatch):
    monkeypatch.setattr(W, "WINDOWS", False)
    assert W.BackgroundConsole().problem() == W.NO_TERMINAL


def test_on_linux_an_outcome_line_goes_to_the_log(monkeypatch, capsys):
    monkeypatch.setattr(W, "WINDOWS", False)
    W.BackgroundConsole()("raised\n")
    assert capsys.readouterr().out == "raised\n"


def test_an_outcome_line_that_cannot_be_written_changes_nothing(monkeypatch):
    def fails(self, text):
        raise OSError("gone")

    monkeypatch.setattr(W, "WINDOWS", True)
    monkeypatch.setattr(W.BackgroundConsole, "_write_windows", fails)
    W.BackgroundConsole()("raised\n")


def test_a_challenge_that_cannot_be_written_raises(monkeypatch):
    def fails(self, text):
        raise OSError("gone")

    monkeypatch.setattr(W, "WINDOWS", True)
    monkeypatch.setattr(W.BackgroundConsole, "_write_windows", fails)
    with pytest.raises(OSError):
        W.BackgroundConsole().challenge("code\n")


def test_a_challenge_says_first_what_the_window_is_and_what_closing_it_does(monkeypatch):
    written = []
    monkeypatch.setattr(W, "WINDOWS", True)
    monkeypatch.setattr(W.BackgroundConsole, "_write_windows", lambda self, text: written.append(text))
    W.BackgroundConsole().challenge("code\n")
    assert written[0].startswith(W.WINDOW_NOTE) and written[0].endswith("code\n")
    assert "Closing it stops the endpoint" in W.WINDOW_NOTE


def test_on_windows_a_process_with_no_console_cannot_show_a_code(monkeypatch):
    monkeypatch.setattr(W, "WINDOWS", True)
    monkeypatch.setattr(W.BackgroundConsole, "_show", staticmethod(lambda visible: False))
    assert W.BackgroundConsole().problem() == "this process has no console"


def test_a_new_challenge_keeps_the_window_the_last_one_was_closing(monkeypatch):
    monkeypatch.setattr(W, "WINDOWS", True)
    monkeypatch.setattr(W.BackgroundConsole, "_show", staticmethod(lambda visible: True))
    monkeypatch.setattr(W.BackgroundConsole, "_write_windows", lambda self, text: None)
    console = W.BackgroundConsole()
    console.done()
    timer = console._timer
    assert timer is not None
    console("code\n")
    assert console._timer is None
    timer.join(1.0)
    assert not timer.is_alive(), "cancelled"
    console.done()
    assert console._timer is not None
    console._timer.cancel()


def test_the_endpoint_gets_neither_the_lead_credential_nor_a_fed_provider_variable():
    env = A.endpoint_env({"AEW_LEAD_TOKEN": "synthetic", "AEW_INVOCATION_TOKEN": "synthetic",
                          "AEW_AGENT_KEY": "synthetic", "SOME_API_KEY": "synthetic", "AEW_LEAD_BROKER": "kept",
                          "OTHER": "kept"}, ["SOME_API_KEY"])
    assert not {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_KEY", "SOME_API_KEY"} & set(env)
    assert env["AEW_LEAD_BROKER"] == "kept", "the endpoint refuses on it"
    assert env["OTHER"] == "kept"
