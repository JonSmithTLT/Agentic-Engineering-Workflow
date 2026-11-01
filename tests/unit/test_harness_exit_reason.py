"""Focused coverage for the supervisor's final crashed-run diagnostic."""

import io
import re
import shlex

import pytest

from aew.cli import fields
from aew.cli.main import build_parser
from aew.harness import contract as K
from aew.harness.supervisor import Supervisor

CONTENT_FILTER = "the agent's turn ended: failed (provider.content-filter, 200: invalid_prompt: flagged)"


def make_supervisor(record: dict | None = None) -> tuple[Supervisor, list[tuple[str, str]]]:
    supervisor = Supervisor.__new__(Supervisor)
    supervisor.inv_id = "INV-0001"
    supervisor.record = record if record is not None else {"contract": {"expected_kinds": []}, "work_unit": "T-0001"}
    supervisor._evidence = lambda **_kwargs: []  # type: ignore[method-assign]
    ended: list[tuple[str, str]] = []

    def finish(status: str, reason: str, *, reason_code: str | None = None) -> None:
        ended.append((status, reason))

    supervisor._finish = finish  # type: ignore[method-assign]
    return supervisor, ended


def finish(status: dict) -> tuple[str, str]:
    supervisor, ended = make_supervisor()
    Supervisor._finish_exited(supervisor, status)
    return ended[0]


def finish_reason(status: dict) -> str:
    ended_as, reason = finish(status)
    assert ended_as == K.CRASHED
    return reason


def test_known_outcome_is_exposed_in_crash_reason() -> None:
    assert finish_reason({"exit_code": 1, "detail": "the agent's turn ended: failed (provider.overloaded)"}) == (
        "harness exited with 1 without recording its expected output; harness outcome: "
        "the agent's turn ended: failed (provider.overloaded)"
    )


@pytest.mark.parametrize("spelling", ["content-filter", "content_filter", "content.filter"])
def test_content_filter_outcome_names_a_relaunch_and_a_new_model_not_a_prompt_change(spelling: str) -> None:
    reason = finish_reason({"exit_code": 1, "detail": f"the agent's turn ended: failed (provider.{spelling})"})
    assert f"provider.{spelling}" in reason
    assert "`aew harness launch INV-0001 --expect-rev <revision from aew status>`" in reason
    assert "aew invoke cancel INV-0001" in reason
    assert "aew invoke create T-0001 --launch --model PROVIDER/MODEL" in reason
    assert "prompt" not in reason  # no governed command changes an invocation's prompt (PR #310 review, F1)


def test_the_filter_marker_is_the_error_type_not_words_in_the_providers_message() -> None:
    """PR #310 review, F3: a message that merely mentions the filter gets the generic reason; a type that is not
    spelled `provider.content-filter` right after the bracket gets none."""
    generic = "harness exited with 1 without recording its expected output; harness outcome: "
    for detail in ("the agent's turn ended: failed (provider.overloaded, 529: content_filter service unavailable)",
                   "the agent's turn ended: failed (provider.overloaded, 529: see provider.content-filter docs)",
                   "the agent's turn ended: failed (provider.content-filtering)"):
        assert finish_reason({"exit_code": 1, "detail": detail}) == generic + detail


def test_missing_or_empty_outcome_keeps_generic_reason() -> None:
    expected = "harness exited with 1 without recording its expected output"
    assert finish_reason({"exit_code": 1}) == expected
    assert finish_reason({"exit_code": 1, "detail": ""}) == expected


def test_provider_text_in_the_reason_is_bounded_and_free_of_control_characters() -> None:
    """PR #310 review, F2: the provider's message is cleaned like every other line of harness text; the run record
    keeps the raw outcome."""
    raw = "the agent's turn ended: failed (provider.overloaded, 529: line one\nline two \x1b[2J" + "x" * 20000 + ")"
    supervisor, ended = make_supervisor()
    Supervisor._finish_exited(supervisor, {"exit_code": 1, "detail": raw})
    reason = ended[0][1]
    assert "\n" not in reason and "\x1b" not in reason
    assert len(reason) < 700
    assert reason.startswith("harness exited with 1 without recording its expected output; harness outcome: the agent")
    assert supervisor.record["harness_outcome"] == raw


def test_content_filter_guidance_survives_a_provider_message_with_control_characters() -> None:
    detail = "the agent's turn ended: failed (provider.content-filter, 200: a\nb\x1b[2J" + "y" * 5000 + ")"
    reason = finish_reason({"exit_code": 1, "detail": detail})
    assert "a\nb" not in reason and "\x1b" not in reason
    assert "aew invoke cancel INV-0001" in reason


def test_a_credential_status_message_never_reaches_the_reason_or_its_next_step() -> None:
    from aew.harness.opencode.adapter import describe_error, error_view

    error = {"type": "provider.content-filter", "status": 401, "message": "key sk-proj-SYNTHETICabc123XYZ"}
    detail = f"the agent's turn ended: failed ({describe_error(error_view(error))})"
    reason = finish_reason({"exit_code": 1, "detail": detail})
    assert "sk-proj" not in reason and "SYNTHETIC" not in reason


def test_a_crashed_run_with_an_outcome_still_ends_crashed_with_the_exit_code_recorded() -> None:
    supervisor, ended = make_supervisor()
    Supervisor._finish_exited(supervisor, {"exit_code": 1, "detail": "the agent's turn ended: failed (provider.x)"})
    assert [status for status, _ in ended] == [K.CRASHED] and supervisor.record["exit_code"] == 1


# ------------------------------------------------------------------------------ the printed commands parse as printed

FENCE = re.compile(r"```sh\n(.*?)```", re.S)
INLINE = re.compile(r"`(aew [^`]*)`")
FILL = {"<revision from aew status>": "7", "PROVIDER/MODEL": "vendor/model-a"}


def printed_commands(message: str):
    """Every `aew ...` command in a message, as `(argv, stdin)`: the fenced blocks (a heredoc body is the stdin), then
    the inline ones; placeholders filled."""
    for block in FENCE.findall(message):
        lines = block.splitlines()
        if lines[0].endswith("<<'EOF'"):
            assert lines[-1] == "EOF", lines
            yield shlex.split(fill(lines[0][: -len("<<'EOF'")]))[1:], "\n".join(lines[1:-1]) + "\n"
        else:
            assert len(lines) == 1, lines
            yield shlex.split(fill(lines[0]))[1:], ""
    for command in INLINE.findall(FENCE.sub("", message)):
        yield shlex.split(fill(command))[1:], ""


def fill(text: str) -> str:
    for placeholder, value in FILL.items():
        text = text.replace(placeholder, value)
    return text


def parse(argv: list[str], stdin: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    parser = build_parser()
    return parser.parse_args(fields.expand(argv, parser))


def test_every_command_the_content_filter_reason_prints_parses_as_printed(monkeypatch: pytest.MonkeyPatch) -> None:
    reason = finish_reason({"exit_code": 1, "detail": CONTENT_FILTER})
    parsed = [parse(argv, stdin, monkeypatch) for argv, stdin in printed_commands(reason)]
    assert len(parsed) == 4, reason
    cancel, create, redispatch, launch = parsed  # the fenced blocks in order, then the inline command
    assert (launch.harness_cmd, launch.invocation, launch.expect_rev) == ("launch", "INV-0001", 7)
    assert (cancel.invoke_cmd, cancel.invocation, cancel.expect_rev) == ("cancel", "INV-0001", 7)
    assert cancel.reason == "why this invocation must end"
    assert (create.invoke_cmd, create.work_id, create.launch, create.model, create.expect_rev) == (
        "create", "T-0001", True, "vendor/model-a", 7)
    assert (redispatch.work_id, redispatch.launch, redispatch.model, redispatch.expect_rev) == (
        "T-0001", True, "vendor/model-a", 7)
    assert redispatch.reason == "why this Ticket is redispatched"
    # the convention (#311): every revision comes from `aew status`, and no reason is typed inline
    assert reason.count("--expect-rev <revision from aew status>") == 4 and "--reason" not in reason


def test_auth_reason_is_unchanged_even_with_outcome() -> None:
    contract = {"expected_kinds": [], "extra": {"provider_env": ["OPENAI_API_KEY"]}}
    supervisor, ended = make_supervisor({"contract": contract})
    Supervisor._finish_exited(supervisor, {"exit_code": 1, "reason_code": K.PROVIDER_AUTH_FAILED,
                                           "detail": "the agent's turn ended: failed (provider.auth, 401)"})
    assert ended == [(K.CRASHED,
        "provider_auth_failed: the model provider rejected the credential, so the harness exited without recording its "
        "expected output; check the key in OPENAI_API_KEY (the execution policy's provider_env), then relaunch. A "
        "relaunch reads the key from the process that launches it: from inside a Lead session (`aew opencode`, "
        "`aew lead session`) that is the session's own, so restart it from a terminal with the new key first"
    )]


def test_zero_exit_without_evidence_is_unchanged() -> None:
    assert finish({"exit_code": 0, "detail": "done"}) == (
        K.ENDED_WITHOUT_EVIDENCE,
        "harness exited successfully without recording its expected output (); no AEW state changed"
    )


def test_success_and_evidence_paths_are_unchanged() -> None:
    supervisor, ended = make_supervisor({"contract": {"expected_kinds": ["report"]}})
    supervisor._evidence = lambda **_kwargs: [("evidence-id", "report")]  # type: ignore[method-assign]
    Supervisor._finish_exited(supervisor, {"exit_code": 0, "detail": "done"})
    assert ended == [(K.ENDED_WITH_EVIDENCE, "harness exited (0) after recording evidence-id")]
