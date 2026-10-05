"""Where credentials go (ADR-0009 custody): only to the controlling terminal unless a script opts in; the operator
prompt says who asked and where the credential will go; host-side git never inherits one."""

from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import pytest

from aew import errors, operator
from aew.cli import credentials
from aew.cli.main import build_parser
from aew.harness import procs
from aew.workspace import git

CRED = "aew1.tk_0123456789abcdef." + "A" * 43


class Terminal(io.StringIO):
    def close(self) -> None:  # keep the text readable after `with`
        self.closed_by_caller = True


def parse(*argv: str) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


@pytest.mark.parametrize("argv", [["lead", "acquire", "--expect-rev", "0"],
                                  ["lead", "takeover", "--expect-rev", "0", "--reason", "x"],
                                  ["lead", "handoff", "offer", "--expect-rev", "0"],
                                  ["lead", "handoff", "accept", "--offer", "o", "--expect-rev", "0"],
                                  ["work", "assign", "T-0001", "--expect-rev", "0"],
                                  ["work", "dispatch", "T-0001", "--expect-rev", "0"],
                                  ["invoke", "create", "T-0001", "--expect-rev", "0"],
                                  ["dashboard", "serve"], ["dashboard", "open"]])
def test_every_command_that_issues_a_credential_is_known(argv):
    assert credentials.issues_credential(parse(*argv))


@pytest.mark.parametrize("argv", [["status"], ["lead", "show"], ["work", "dispatch", "T-0001", "--launch",
                                                                 "--expect-rev", "0"], ["dashboard", "status"]])
def test_commands_that_issue_none_are_not(argv):
    assert not credentials.issues_credential(parse(*argv))


def test_a_session_url_is_delivered_like_a_token(monkeypatch):
    term = Terminal()
    monkeypatch.setattr(credentials, "_open_terminal", lambda: term)
    url = "http://127.0.0.1:4280/session/" + "c" * 43
    out = credentials.deliver({"ok": True, "url": "http://127.0.0.1:4280", "session_url": url},
                              parse("dashboard", "open"))
    assert out["session_url"] == credentials.WRITTEN and out["url"] == "http://127.0.0.1:4280"
    assert f"session_url: {url}" in term.getvalue()
    term2 = Terminal()
    monkeypatch.setattr(credentials, "_open_terminal", lambda: term2)
    credentials.write_to_terminal("session_url", url)  # the long-running `serve` writes each URL itself
    assert f"session_url: {url}" in term2.getvalue() and "keep it out of any agent's reach" in term2.getvalue()


def test_with_no_terminal_a_credential_command_is_refused_before_it_runs(monkeypatch):
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)
    with pytest.raises(errors.UsageError, match="your terminal"):
        credentials.before(parse("lead", "acquire", "--expect-rev", "0"))
    credentials.before(parse("--print-credential", "lead", "acquire", "--expect-rev", "0"))  # a script opted in
    credentials.before(parse("status"))  # issues nothing


def test_the_credential_goes_to_the_terminal_and_stdout_says_so(monkeypatch):
    term = Terminal()
    monkeypatch.setattr(credentials, "_open_terminal", lambda: term)
    args = parse("lead", "acquire", "--expect-rev", "0")
    out = credentials.deliver({"ok": True, "token": CRED, "generation": 1}, args)
    assert out == {"ok": True, "token": credentials.WRITTEN, "generation": 1}
    assert f"token: {CRED}" in term.getvalue()
    inv = credentials.deliver({"invocation": "INV-0001", "invocation_token": CRED},
                              parse("work", "assign", "T-0001", "--expect-rev", "0"))
    assert inv["invocation_token"] == credentials.WRITTEN


def test_print_credential_leaves_it_on_stdout(monkeypatch):
    monkeypatch.setattr(credentials, "_open_terminal", lambda: pytest.fail("no terminal write with the flag"))
    args = parse("--print-credential", "lead", "acquire", "--expect-rev", "0")
    assert credentials.deliver({"token": CRED}, args) == {"token": CRED}


def test_the_operator_prompt_names_the_requester_and_the_destination(monkeypatch):
    shown: list[str] = []

    def ask(prompt: str, timeout: float) -> str:
        shown.append(prompt)
        return "no"

    monkeypatch.setattr(operator, "_ask_windows", ask)
    monkeypatch.setattr(operator, "_ask_posix", ask)
    monkeypatch.setattr(procs, "process_chain", lambda: ["aew (3)", "opencode (2)", "bash (1)"])
    for destination in (operator.TERMINAL_ONLY, "standard output (--print-credential)"):
        token = operator.credential_destination.set(destination)
        try:
            with pytest.raises(errors.PermissionDenied):
                operator.authorize("TAKE OVER")
        finally:
            operator.credential_destination.reset(token)
        assert "requested by   : aew (3) <- opencode (2) <- bash (1)" in shown[-1]
        assert f"credential to  : {destination}" in shown[-1]


def test_the_process_chain_starts_at_this_process():
    import os

    chain = procs.process_chain()
    assert chain and chain[0].endswith(f"({os.getpid()})")


def test_host_side_git_never_inherits_a_credential(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AEW_LEAD_TOKEN", CRED)
    monkeypatch.setenv("SOMETHING_ELSE", f"carries {CRED}")
    seen: list[dict[str, str]] = []
    real = subprocess.run

    def spy(*a, **kw):
        if kw.get("env") is not None:
            seen.append(kw["env"])
        return real(*a, **kw)

    monkeypatch.setattr(git.subprocess, "run", spy)
    git.git("init", "-q", cwd=tmp_path)
    assert seen and all("AEW_LEAD_TOKEN" not in env and "SOMETHING_ELSE" not in env for env in seen)
