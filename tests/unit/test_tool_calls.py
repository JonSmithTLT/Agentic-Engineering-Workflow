"""The Lead broker's per-call typed-tool log (M4-E plan v3 E5a, n7): what one line holds, that it is bounded and
rotated, and that it is never a reason a call fails."""

from __future__ import annotations

from aew.harness import tool_calls as T


def _result(**over):
    return {"ok": False, "effective_operation_class": "POLICY_RESOLVED", "revision": 7, "stage_intent_id": "SI-0002",
            "stopped": {"at": "work.assign", "boundary": "launch_failed",
                        "error": {"code": "HARNESS_LAUNCH_FAILED", "message": "m", "details": {}}}, **over}


def test_a_line_is_built_from_the_stage_result_and_never_holds_the_arguments():
    line = T.entry(tool="ticket_start", arguments='{"work_id": "T-0001"}', ingress="mcp",
                   profile="normal", result=_result(), input_error=None, error=None, revision_before=6,
                   duration_ms=12)
    assert {k: line[k] for k in ("tool", "effective_class", "ok", "boundary", "error_code", "revision_before",
                                 "revision_after", "stage_intent", "duration_ms", "ingress")} == {
        "tool": "ticket_start", "effective_class": "POLICY_RESOLVED", "ok": False, "boundary": "launch_failed",
        "error_code": "HARNESS_LAUNCH_FAILED", "revision_before": 6, "revision_after": 7, "stage_intent": "SI-0002",
        "duration_ms": 12, "ingress": "mcp"}
    assert "T-0001" not in str(line)
    # One digest for the same arguments, however the JSON text was spaced or ordered; the text itself when not JSON.
    assert line["arguments_sha256"] == T.arguments_digest({"work_id": "T-0001"})
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


def test_defects_rotate_to_their_own_files(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "MAX_BYTES", 10)
    monkeypatch.setattr(T, "KEEP", 2)
    T.append(tmp_path, {"n": 0})
    for n in range(4):
        T.append(tmp_path, {"n": n}, log_rel=T.DEFECT_LOG_REL)
    folder = tmp_path / "local/lead"
    assert sorted(p.name for p in folder.iterdir()) == [
        "defects.1.jsonl", "defects.2.jsonl", "defects.jsonl", "tool-calls.jsonl",
    ]
    assert T.read(tmp_path) == [{"n": 0}]


def test_a_line_that_cannot_be_built_never_changes_the_call(tmp_path, caplog, monkeypatch):
    """PR #177 review, finding 4: arguments that are not JSON and not even encodable text (a lone surrogate) are
    digested as given, and anything else that fails while a line is built or written is logged and dropped."""
    line = T.entry(tool="nope", arguments='{"x": "\ud800', ingress="mcp", profile="normal", result=None,
                   input_error={"code": "INVALID_ARGUMENTS"}, error=None, revision_before=1, duration_ms=0)
    assert len(line["arguments_sha256"]) == 64
    T.record(tmp_path, tool="nope", arguments='{"x": "\ud800', ingress="mcp", profile="normal", result=None,
             input_error={"code": "INVALID_ARGUMENTS"}, error=None, revision_before=1, duration_ms=0)
    assert T.read(tmp_path)[0]["error_code"] == "INVALID_ARGUMENTS"

    def broken(**_):
        raise RuntimeError("a defect in the log")

    monkeypatch.setattr(T, "entry", broken)
    with caplog.at_level("WARNING", logger="aew.harness.tool_calls"):
        T.record(tmp_path, tool="status")  # no exception
    assert "dropped a line" in caplog.text


def test_a_line_is_bounded_whatever_the_call_carried(tmp_path):
    huge = "t" * (4 << 20)
    result = {**_result(), "effective_operation_class": huge, "stage_intent_id": huge,
              "stopped": {"boundary": huge, "error": {"code": huge}}}
    T.record(tmp_path, tool=huge, arguments=huge, ingress=huge, profile=huge, result=result, input_error=None,
             error=None, revision_before=1, duration_ms=1)
    text = T.path(tmp_path).read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) <= T.MAX_LINE and T.read(tmp_path)[0]["tool"] == "t" * T.MAX_FIELD

    detail = dict.fromkeys(("exception", "defect", "cause_code"), huge)
    result["stopped"]["error"] = {"code": "DEFECT", "details": detail}
    T.record(tmp_path, tool=huge, arguments=huge, ingress=huge, profile=huge, result=result, input_error=None,
             error=None, revision_before=1, duration_ms=1)
    last = T.path(tmp_path).read_bytes().splitlines()[-1]
    assert len(last) + 1 <= T.MAX_LINE
    line = T.read(tmp_path)[-1]
    assert all(line[key] == "t" * T.MAX_FIELD for key in ("exception", "defect", "cause_code"))


# --------------------------------------------------------------------------- E231: the failure criterion's counters


def test_the_counters_read_typed_misuse_guide_reads_and_help_lookups_per_session(tmp_path):
    """E231 (the operator, 2026-11-25: a Lead "fails to use typed tools correctly, is using help all the time for shell
    commands"): per session, its typed calls, each kind of misuse, its guide reads by section and its help lookups by
    command, read back from the one log."""
    def call(session, **over):
        fields = {"tool": "status", "arguments": "{}", "ingress": "mcp", "profile": "normal", "result": None,
                  "input_error": None, "error": None, "revision_before": 1, "duration_ms": 0, "session": session,
                  "generation": 2, **over}
        T.record(tmp_path, **fields)

    call("LS-a", result=_result(ok=True, stopped=None))
    call("LS-a", result=_result())  # stopped with a code (here a launch that failed: not always misuse)
    call("LS-a", input_error={"code": "INVALID_ARGUMENTS"})
    call("LS-a", error={"code": "DEFECT", "details": {}})
    T.lookup(tmp_path, kind=T.GUIDE, session="LS-a", generation=2, command="guide", section="steps", ok=True)
    T.lookup(tmp_path, kind=T.GUIDE, session="LS-a", generation=2, command="guide", section=None, ok=True)
    T.lookup(tmp_path, kind=T.HELP, session="LS-a", generation=2, command="work create")
    T.lookup(tmp_path, kind=T.HELP, session="LS-b", generation=3, command="")
    T.append(tmp_path, {"tool": "status", "ok": True})  # a line from before sessions were named
    counted = T.counters(T.read(tmp_path))
    a = counted["LS-a"]
    assert {k: a[k] for k in T.COUNTERS} == {"typed_calls": 4, "stopped": 1, "defects": 1, "invalid_arguments": 1,
                                             "guide_reads": 2, "help_lookups": 1}
    assert a["stopped_codes"] == {"HARNESS_LAUNCH_FAILED": 1}  # review of #593, m4: by code, to tell misuse apart
    assert a["guide_sections"] == {"steps": 1, "(list)": 1} and a["help_commands"] == {"work create": 1}
    assert (counted["LS-b"]["help_lookups"], counted["LS-b"]["help_commands"]) == (1, {"aew": 1})
    assert counted[None]["typed_calls"] == 1
    assert "LS-a, generation 2" in T.render_counters(counted)


def test_a_lookup_line_is_bounded_and_never_fails(tmp_path, caplog, monkeypatch):
    T.lookup(tmp_path, kind=T.HELP, session="s" * 4096, generation=1, command="c" * 4096, ok="yes")
    [line] = T.read(tmp_path)
    assert len(line["session"]) == len(line["command"]) == T.MAX_FIELD and line["ok"] is None
    monkeypatch.setattr(T, "append", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("broken")))
    with caplog.at_level("WARNING", logger="aew.harness.tool_calls"):
        T.lookup(tmp_path, kind=T.GUIDE, session=None, generation=None, command="guide")  # no exception
    assert "dropped a lookup" in caplog.text


def test_a_help_lookup_is_recognised_and_names_only_command_words():
    """What counts as a help lookup, and what of it is kept: the command words, never a value the Lead typed."""
    from aew.harness import lead_broker as B

    for argv in (["--help"], [], ["help"], ["work", "create", "-h"], ["-C", "x", "work", "show", "--help"]):
        assert B.is_help_lookup(argv), argv
    for argv in (["work", "show", "T-1"], ["harness", "send", "R-1", "--", "--help"]):
        assert not B.is_help_lookup(argv), argv
    assert B.help_command(["work", "create", "--help"]) == "work create"
    assert B.help_command(["-C", "/tmp/x", "map", "show", "-h"]) == "map show"
    assert B.help_command(["help", "work"]) == "work"
    assert B.help_command(["work", "create", "ticket", "my secret title", "--help"]) == "work create"
    assert B.help_command(["no", "such", "--help"]) == ""
    # Review of #593, m2: a command that exists only under a switch is named too
    assert B.help_command(["message", "list", "--help"]) == "message list"
    assert B.help_command(["history", "search", "--help"]) == "history search"


def test_a_guide_read_records_only_a_section_the_guide_has():
    """Review of #593, m1: the log never holds text the Lead typed; an unknown section is a fixed token."""
    from aew.engine import guide
    from aew.harness import lead_broker as B

    assert [B.section_named(n) for n in (None, guide.CORE, *guide.SECTION_NAMES)] == [None, guide.CORE,
                                                                                      *guide.SECTION_NAMES]
    assert B.section_named("my private note") == B.section_named("nope") == B.UNKNOWN_SECTION
    assert B.guide_read(["-C", "x", "guide", "--json", "steps"]) == ("steps",) and B.guide_read(["guide"]) == (None,)
    assert B.guide_read(["status"]) is None


def test_a_torn_line_is_skipped_and_counted_never_a_failed_read(tmp_path):
    """Review of #593, n4: `aew lead telemetry` reads the whole log; a line that does not parse costs a count, never
    the read."""
    T.append(tmp_path, {"tool": "status", "ok": True, "session": "LS-a"})
    with T.path(tmp_path).open("a", encoding="utf-8") as fh:
        fh.write('{"tool": "stat\n[1, 2]\n')
    T.append(tmp_path, {"lookup": T.HELP, "session": "LS-a", "command": "work show"})
    lines, skipped = T.read_counted(tmp_path)
    assert (len(lines), skipped) == (2, 2) and T.read(tmp_path) == lines
    assert "2 line(s) that did not parse were skipped" in T.render_counters(T.counters(lines), skipped)
