"""The Lead broker's per-call typed-tool log (M4-E plan v3 E5a, n7): what one line holds, that it is bounded and
rotated, and that it is never a reason a call fails."""

from __future__ import annotations

from aew.harness import tool_calls as T


def _result(**over):
    return {"ok": False, "effective_operation_class": "POLICY_RESOLVED", "revision": 7, "stage_intent_id": "SI-0002",
            "stopped": {"at": "work.assign", "boundary": "launch_failed",
                        "error": {"code": "HARNESS_LAUNCH_FAILED", "message": "m", "details": {}}}, **over}


def test_a_line_is_built_from_the_stage_result_and_never_holds_the_arguments():
    line = T.entry(tool="ticket_start", arguments='{"work_id": "T-0001", "expect_rev": 6}', ingress="mcp",
                   profile="normal", result=_result(), input_error=None, error=None, revision_before=6,
                   duration_ms=12)
    assert {k: line[k] for k in ("tool", "effective_class", "ok", "boundary", "error_code", "revision_before",
                                 "revision_after", "stage_intent", "duration_ms", "ingress")} == {
        "tool": "ticket_start", "effective_class": "POLICY_RESOLVED", "ok": False, "boundary": "launch_failed",
        "error_code": "HARNESS_LAUNCH_FAILED", "revision_before": 6, "revision_after": 7, "stage_intent": "SI-0002",
        "duration_ms": 12, "ingress": "mcp"}
    assert "T-0001" not in str(line)
    # One digest for the same arguments, however the JSON text was spaced or ordered; the text itself when not JSON.
    assert line["arguments_sha256"] == T.arguments_digest({"expect_rev": 6, "work_id": "T-0001"})
    assert T.arguments_digest("{not json") != T.arguments_digest("{not  json")


def test_an_input_error_and_a_refusal_before_the_runner_are_lines_too():
    bad = T.entry(tool="nope", arguments="{}", ingress="cli", profile="normal", result=None,
                  input_error={"code": "UNKNOWN_TOOL"}, error=None, revision_before=3, duration_ms=0)
    assert (bad["ok"], bad["boundary"], bad["error_code"], bad["revision_after"]) == (
        False, T.INPUT_ERROR, "UNKNOWN_TOOL", None)
    lost = T.entry(tool="status", arguments="{}", ingress="mcp", profile="normal", result=None, input_error=None,
                   error={"code": "STALE_AUTHORITY"}, revision_before=None, duration_ms=1)
    assert (lost["boundary"], lost["error_code"]) == ("error", "STALE_AUTHORITY")


def test_the_log_is_bounded_and_rotated(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "MAX_BYTES", 400)
    monkeypatch.setattr(T, "KEEP", 2)
    for n in range(40):
        T.append(tmp_path, {"n": n, "pad": "x" * 60})
    files = sorted(p.name for p in (tmp_path / "local/lead").iterdir())
    assert files == ["tool-calls.1.jsonl", "tool-calls.2.jsonl", "tool-calls.jsonl"]
    assert all((tmp_path / "local/lead" / f).stat().st_size <= 400 for f in files)
    kept = [x["n"] for x in T.read(tmp_path)]
    assert kept == sorted(kept) and kept[-1] == 39 and kept[0] > 0  # the oldest are gone, the rest in order


def test_a_log_that_cannot_be_written_never_fails_the_call(tmp_path, caplog):
    (tmp_path / "local").write_text("a file where the log's directory should be", encoding="utf-8")
    with caplog.at_level("WARNING", logger="aew.harness.tool_calls"):
        T.append(tmp_path, {"tool": "status"})  # no exception
    assert "could not be written" in caplog.text
