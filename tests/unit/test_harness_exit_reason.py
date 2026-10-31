"""Focused coverage for the supervisor's final crashed-run diagnostic."""

from aew.harness import contract as K
from aew.harness.supervisor import Supervisor


def finish_reason(status: dict) -> str:
    supervisor = Supervisor.__new__(Supervisor)
    supervisor.record = {"contract": {"expected_kinds": []}}
    supervisor._evidence = lambda **_kwargs: []
    reasons: list[str] = []
    supervisor._finish = lambda _status, reason: reasons.append(reason)
    Supervisor._finish_exited(supervisor, status)
    return reasons[0]


def test_known_outcome_is_exposed_in_crash_reason() -> None:
    assert finish_reason({"exit_code": 1, "detail": "the agent's turn ended: failed (provider.overloaded)"}) == (
        "harness exited with 1 without recording its expected output; harness outcome: "
        "the agent's turn ended: failed (provider.overloaded)"
    )


def test_content_filter_outcome_gives_relaunch_guidance() -> None:
    reason = finish_reason({"exit_code": 1, "detail": "the agent's turn ended: failed (provider.content_filter)"})
    assert "provider.content_filter" in reason
    assert "Relaunch" in reason and "change the prompt or model" in reason


def test_hyphenated_content_filter_outcome_gives_relaunch_guidance() -> None:
    reason = finish_reason({"exit_code": 1, "detail": "the agent's turn ended: failed (provider.content-filter)"})
    assert "provider.content-filter" in reason
    assert "Relaunch" in reason and "change the prompt or model" in reason


def test_missing_or_empty_outcome_keeps_generic_reason() -> None:
    expected = "harness exited with 1 without recording its expected output"
    assert finish_reason({"exit_code": 1}) == expected
    assert finish_reason({"exit_code": 1, "detail": ""}) == expected


def test_auth_reason_is_unchanged_even_with_outcome() -> None:
    supervisor = Supervisor.__new__(Supervisor)
    supervisor.record = {"contract": {"expected_kinds": [], "extra": {"provider_env": ["OPENAI_API_KEY"]}}}
    supervisor._evidence = lambda **_kwargs: []
    reasons: list[str] = []
    supervisor._finish = lambda _status, reason: reasons.append(reason)
    Supervisor._finish_exited(supervisor, {"exit_code": 1, "reason_code": K.PROVIDER_AUTH_FAILED,
                                           "detail": "the agent's turn ended: failed (provider.auth, 401)"})
    assert reasons == [
        "provider_auth_failed: the model provider rejected the credential, so the harness exited without recording its "
        "expected output; check the key in OPENAI_API_KEY (the execution policy's provider_env), then relaunch. A "
        "relaunch reads the key from the process that launches it: from inside a Lead session (`aew opencode`, "
        "`aew lead session`) that is the session's own, so restart it from a terminal with the new key first"
    ]


def test_zero_exit_without_evidence_is_unchanged() -> None:
    assert finish_reason({"exit_code": 0, "detail": "done"}) == (
        "harness exited successfully without recording its expected output (); no AEW state changed"
    )


def test_success_and_evidence_paths_are_unchanged() -> None:
    supervisor = Supervisor.__new__(Supervisor)
    supervisor.record = {"contract": {"expected_kinds": ["report"]}}
    supervisor._evidence = lambda **_kwargs: [("evidence-id", "report")]
    reasons: list[tuple[str, str]] = []
    supervisor._finish = lambda status, reason: reasons.append((status, reason))
    Supervisor._finish_exited(supervisor, {"exit_code": 0, "detail": "done"})
    assert reasons == [(K.ENDED_WITH_EVIDENCE, "harness exited (0) after recording evidence-id")]
