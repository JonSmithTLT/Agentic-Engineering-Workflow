"""How a command gets the Lead credential (STG-05 CS-4 addendum 12, ruling 2 and its tests): never as a command-line
value. At a terminal it asks at a hidden prompt; off one it refuses with the per-session forms; `--token` with a value
is refused before anything runs. Synthetic projects and credentials only."""

from __future__ import annotations

import os
import select
import subprocess
import sys
import textwrap
import time

import pytest
from conftest import Project, clean_env

from aew import lead_credential
from aew.errors import UsageError

CHECKPOINT = ("checkpoint", "--next", "synthetic next step")


def _forms_given(error: dict) -> None:
    """The refusal gives each per-session form, in its message and as data."""
    assert error["details"]["forms"] == lead_credential.SECURE_FORMS
    assert all(form in error["message"] for form in lead_credential.SECURE_FORMS.values())


@pytest.mark.parametrize("value", ["project-token", "", "<credential>"])
def test_a_token_value_on_the_command_line_is_refused_before_anything_runs(project: Project, value: str):
    """`--token` with a value (the real credential, an empty one, a placeholder) is refused, naming the prompt and the
    variable, and the command does not run: the revision is unchanged."""
    rev = project.rev()
    token = project.token if value == "project-token" else value
    res = project.aew(*CHECKPOINT, "--token", token, "--expect-rev", str(rev))  # a --token value, refused
    assert res.returncode == 2 and res.error["code"] == "USAGE", res.stderr
    assert res.error["details"]["reason"] == "token_on_command_line"
    assert "hidden prompt" in res.error["message"] and lead_credential.ENV in res.error["message"]
    _forms_given(res.error)
    assert project.rev() == rev


def test_inside_a_lead_session_a_token_value_is_refused_before_the_broker_is_asked(project: Project, monkeypatch,
                                                                                    capsys):
    """In a Lead session the session holds the credential: the refusal says so, and nothing reaches the broker (its
    coordinates here lead nowhere)."""
    import json

    from aew.cli.main import main

    rev = project.rev()
    argv = ["-C", str(project.root), *CHECKPOINT, "--token", "x", "--expect-rev", str(rev)]  # a --token value, refused
    with monkeypatch.context() as m:
        m.setenv("AEW_LEAD_BROKER", "unreachable")
        assert main(argv) == 2
    error = json.loads(capsys.readouterr().err)["error"]
    assert error["details"]["reason"] == "token_on_command_line" and "Lead session holds" in error["message"]
    assert project.rev() == rev


def test_off_a_terminal_a_command_without_the_credential_refuses_with_the_per_session_forms(project: Project):
    """No terminal (as a harness tool call runs, and as every test's CLI runs): the refusal says how to give the
    credential safely, each form with the shell it is for, and why only for the session; nothing ran."""
    rev = project.rev()
    res = project.aew(*CHECKPOINT, "--expect-rev", str(rev))
    assert res.returncode == 2 and res.error["details"]["reason"] == "lead_credential_required", res.stderr
    _forms_given(res.error)
    assert lead_credential.PER_SESSION_WHY in res.error["message"]
    assert all(f"  {shell}: " in res.error["message"] for shell in lead_credential.SECURE_FORMS)
    assert project.rev() == rev


def test_with_the_variable_set_for_the_session_the_command_proceeds(project: Project):
    rev = project.rev()
    out = project.ok(*CHECKPOINT, "--expect-rev", str(rev), env={lead_credential.ENV: project.token})
    assert out["revision"] == rev + 1


def test_a_lead_session_without_the_credential_refuses_with_the_per_session_forms_and_acquire(project: Project):
    """The Lead session's refusal (lead_broker.require_credential), off a terminal: the forms and the other way in."""
    res = project.aew("lead", "session", "--", sys.executable, "-c", "pass")
    assert res.returncode == 2 and res.error["details"]["reason"] == "lead_credential_required", res.stderr
    _forms_given(res.error)
    assert "--acquire" in res.error["message"]


@pytest.mark.skipif(sys.platform == "win32", reason="a pseudo-terminal is POSIX's")
@pytest.mark.parametrize("answer", ["credential", "empty"])
def test_at_a_terminal_the_command_asks_at_a_hidden_prompt_and_proceeds(project: Project, answer: str):
    """The prompt, on a pseudo-terminal that is the command's controlling terminal and standard input (as at the
    operator's shell): it names who asked, nothing typed is echoed, and the command runs with what was typed, for that
    command only. An empty answer refuses, and nothing runs."""
    assert sys.platform != "win32"  # narrows pty for the type checker
    import pty

    master, slave = pty.openpty()
    wrapper = textwrap.dedent("""
        import fcntl, os, sys, termios
        os.setsid()
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)
        os.execv(sys.executable, [sys.executable, "-m", "aew", *sys.argv[1:]])
    """)
    rev = project.rev()
    proc = subprocess.Popen([sys.executable, "-c", wrapper, "-C", str(project.root), *CHECKPOINT, "--expect-rev",
                             str(rev)], stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=clean_env())
    shown, sent = bytearray(), False
    reply = project.token.encode() if answer == "credential" else b""
    try:
        deadline = time.monotonic() + 120
        while proc.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                shown += os.read(master, 65536)
            if not sent and b"Lead token: " in shown:
                os.write(master, reply + b"\n")
                sent = True
        if proc.poll() is None:
            proc.kill()
        out, err = proc.communicate(timeout=30)
    finally:
        os.close(master)
        os.close(slave)
    assert b"requested by" in shown and b"Lead token: " in shown
    assert project.token.encode() not in bytes(shown) + out + err  # never echoed, never printed
    if answer == "credential":
        assert proc.returncode == 0, err.decode()
        assert project.rev() == rev + 1
    else:
        assert proc.returncode == 2 and b"no Lead credential was entered" in err
        assert project.rev() == rev


def test_inside_an_aew_session_nothing_asks_for_the_credential(monkeypatch):
    """The contained Lead's harness has a terminal of its own (the relay's): a prompt there would ask the operator to
    type the credential into a process the agent started. Inside any AEW session nothing asks, even at a terminal."""
    from aew import operator

    monkeypatch.delenv(lead_credential.ENV, raising=False)
    monkeypatch.setattr(operator, "has_terminal", lambda: True)
    monkeypatch.setattr(sys, "stdin", type("Tty", (), {"isatty": lambda self: True})())

    def asked(*a, **k):
        raise AssertionError("the prompt was shown")

    monkeypatch.setattr(operator, "ask_hidden", asked)
    for name in ("AEW_LEAD_CONTAINED", "AEW_LEAD_BROKER", "AEW_AGENT_ENDPOINT", "AEW_INVOCATION_TOKEN"):
        monkeypatch.setenv(name, "1")
        assert lead_credential.in_session() and not lead_credential.can_prompt()
        with pytest.raises(UsageError, match="nothing asks for it inside an AEW session"):
            lead_credential.required()
        monkeypatch.delenv(name)
    assert lead_credential.can_prompt()  # the control: the same process outside a session would ask


def test_what_the_prompt_took_is_for_one_command_only(monkeypatch):
    """The answer is held in memory for the command that asked (and a Lead session's broker takes it once); the next
    command asks again."""
    from aew import operator

    shown: list[str] = []
    monkeypatch.delenv(lead_credential.ENV, raising=False)
    monkeypatch.setattr(lead_credential, "can_prompt", lambda: True)
    monkeypatch.setattr(operator, "ask_hidden", lambda prompt, **k: shown.append(prompt) or "  synthetic-value \n")
    assert lead_credential.required() == "synthetic-value"
    assert lead_credential.required() == "synthetic-value" and len(shown) == 1  # the same command asks once
    assert lead_credential.take_prompted() == "synthetic-value" and lead_credential.take_prompted() == ""
    assert lead_credential.optional() is None  # a command that works without it never asks
    assert "requested by" in shown[0] and operator.RELAY_WARNING in shown[0]
