"""Where credentials go (ADR-0009 custody): only to the controlling terminal unless a script opts in; the operator
prompt says who asked and where the credential will go; host-side git never inherits one."""

from __future__ import annotations

import argparse
import io
import subprocess
from pathlib import Path

import pytest

from aew import errors, lead_credential, operator
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


@pytest.mark.parametrize("argv", [["lead", "acquire", ],
                                  ["lead", "takeover", "--reason", "x"],
                                  ["lead", "handoff", "offer", ],
                                  ["lead", "handoff", "accept", "--offer", "o", ],
                                  ["work", "assign", "T-0001", ],
                                  ["work", "dispatch", "T-0001", ],
                                  ["invoke", "create", "T-0001", ],
                                  ["dashboard", "serve"], ["dashboard", "open"]])
def test_every_command_that_issues_a_credential_is_known(argv):
    assert credentials.issues_credential(parse(*argv))


@pytest.mark.parametrize("argv", [["status"], ["lead", "show"], ["work", "dispatch", "T-0001", "--launch",
                                                                 ], ["dashboard", "status"]])
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
        credentials.before(parse("lead", "acquire"))
    credentials.before(parse("--print-credential", "lead", "acquire"))  # a script opted in
    credentials.before(parse("status"))  # issues nothing


def test_the_credential_goes_to_the_terminal_and_stdout_says_so(monkeypatch):
    term = Terminal()
    monkeypatch.setattr(credentials, "_open_terminal", lambda: term)
    args = parse("lead", "acquire")
    out = credentials.deliver({"ok": True, "token": CRED, "generation": 1}, args)
    assert out == {"ok": True, "token": credentials.WRITTEN, "generation": 1}
    assert f"token: {CRED}" in term.getvalue()
    inv = credentials.deliver({"invocation": "INV-0001", "invocation_token": CRED},
                              parse("work", "assign", "T-0001"))
    assert inv["invocation_token"] == credentials.WRITTEN


def test_print_credential_leaves_it_on_stdout(monkeypatch):
    monkeypatch.setattr(credentials, "_open_terminal", lambda: pytest.fail("no terminal write with the flag"))
    args = parse("--print-credential", "lead", "acquire")
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


def test_the_operator_prompt_escapes_ancestor_and_supplied_requesters(monkeypatch):
    raw = "shell\x1b[0m\x9b0m\nnext\u202e"
    shown = r"shell\u001b[0m\u009b0m\nnext\u202e"
    monkeypatch.setattr(procs, "process_chain", lambda: ["aew (3)", f"{raw} (2)"])
    local = operator.challenge("ABC123", "Confirm this operation")
    remote = operator.challenge("ABC123", "Confirm this operation", requested_by=raw)
    assert f"  requested by   : aew (3) <- {shown} (2)\n" in local
    assert f"  requested by   : {shown}\n" in remote
    for prompt in (local, remote):
        assert "If you did not start this command yourself" in prompt.splitlines()[-3]
        assert prompt.splitlines()[-1] == operator.RELAY_WARNING
        assert all(c.isprintable() or c == "\n" for c in prompt)


def test_the_windows_process_chain_stops_at_a_reused_parent_pid():
    snapshot = {30: (20, "aew"), 20: (10, "shell"), 10: (0, "unrelated")}
    for created in ({30: 300, 20: 200, 10: 250}, {30: 300, 20: 200, 10: 200}):
        assert procs._render_process_chain(snapshot, 30, 6, created=created.get) == [
            "aew (30)", "shell (20)", "(unverified parent, pid 10)",
        ]


def test_the_operator_prompt_preserves_preview_lines_and_escapes_fields_inside_them():
    from aew.harness.operator_client import capability_prompt

    preview = "candidate\x1b[0m\r\nname"
    for prompt in (
        operator.challenge("ABC123", ["Review the change:", preview]),
        capability_prompt({"change": [preview]}, "shell"),
    ):
        assert r"candidate\u001b[0m\r\nname" in prompt.splitlines()
        assert operator.RELAY_WARNING in prompt
    plain = operator.challenge("ABC123", "First line\nSecond line\x1b")
    assert "First line\nSecond line\\u001b\n" in plain


def test_the_requester_cap_applies_to_visible_escapes_and_preserves_attribution():
    prompt = operator.challenge("ABC123", "Confirm", requested_by="\\n\n" + "\x1b" * 400,
                                requester_reported=True)
    field = next(line for line in prompt.splitlines() if "requested by" in line)
    value, attribution = field.split(" : ", 1)[1].split(" (as reported", 1)
    assert value.startswith(r"\\n\n")
    assert len(value) == 400 and value.endswith(" (cut)")
    assert "the code below is the authorization" in attribution


def test_the_hidden_lead_credential_prompt_escapes_ancestor_names(monkeypatch):
    shown = []

    def ask(prompt: str, **_):
        shown.append(prompt)
        return ""

    monkeypatch.setattr(lead_credential, "_prompted", None)
    monkeypatch.setattr(lead_credential, "session_kind", lambda: None)
    monkeypatch.setattr(lead_credential, "can_prompt", lambda: True)
    monkeypatch.setattr(operator, "ask_hidden", ask)
    monkeypatch.setattr(procs, "process_chain", lambda: ["shell\x1b[0m (2)"])
    with pytest.raises(errors.UsageError, match="no Lead credential was entered"):
        lead_credential.required(force_prompt=True)
    assert r"requested by : shell\u001b[0m (2)" in shown[0]
    assert operator.RELAY_WARNING in shown[0]


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
