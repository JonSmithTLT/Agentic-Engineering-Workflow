"""Failure diagnostics are a bounded display, not a replacement for the full sealed log."""

from __future__ import annotations

import pytest

from aew.policy import checks as C


def test_failure_lines_survive_both_a_long_preamble_and_a_long_summary():
    lines = [f"setup {i}" for i in range(200)] + ["context before", "AssertionError: expected 3 got 4", "context after"]
    lines += [f"summary {i}" for i in range(300)]
    out = C.failure_output("\n".join(lines))
    by_line = {row["line"]: row["text"] for row in out["lines"]}
    assert by_line[202] == "AssertionError: expected 3 got 4"
    assert by_line[201] == "context before" and by_line[203] == "context after"
    assert list(by_line) == sorted(by_line)
    assert out["omitted_lines"] == len(lines) - len(by_line) > 0


def test_failure_output_is_scrubbed_before_a_long_line_is_cut():
    secret = "aew1.tk_" + "1" * 16 + "." + "F" * 43
    log = "ERROR: " + "x" * (C.FAILURE_OUTPUT_MAX_LINE_CHARS - 20) + " " + secret + " end"
    out = C.failure_output(log)
    text = out["lines"][0]["text"]
    assert secret not in text and "aew1.tk_" not in text
    assert "aew1.<redact" in text  # even a cut within the replacement contains no credential fragment
    assert log.endswith(secret + " end"), "display scrubbing never mutates the source log"


@pytest.mark.parametrize("kind", ["diagnostics", "tail"])
def test_failure_output_names_and_enforces_its_bounds_and_exact_left_out_count(kind):
    prefix = "ERROR " if kind == "diagnostics" else "detail "
    lines = [prefix + str(i) + " x" * 1000 for i in range(210)]
    out = C.failure_output("\n".join(lines))
    assert len(out["lines"]) == C.FAILURE_OUTPUT_MAX_LINES == 80
    assert out["omitted_lines"] == 130 and out["total_lines"] == 210
    assert out["truncated_lines"] == 80
    assert all(len(row["text"]) == C.FAILURE_OUTPUT_MAX_LINE_CHARS == 1000 for row in out["lines"])
    assert out["limits"] == {"lines": 80, "characters_per_line": 1000,
                             "source": "aew.policy.checks.FAILURE_OUTPUT_MAX_LINES / FAILURE_OUTPUT_MAX_LINE_CHARS"}
    expected_first = 1 if kind == "diagnostics" else 131
    assert out["lines"][0]["line"] == expected_first


def test_an_empty_failure_log_has_no_invented_diagnostic_lines():
    out = C.failure_output("")
    assert out["lines"] == [] and out["omitted_lines"] == out["total_lines"] == 0
