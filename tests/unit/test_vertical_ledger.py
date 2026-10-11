"""The vertical UAT's burden ledger (docs/implementation/vertical-uat.md): the thresholds the test pins equal the
document's, it stays in shadow until the operator flips it, and the ledger classifies what the actors report the way
the document says."""

from __future__ import annotations

import re
from pathlib import Path

from vertical import ledger as L

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "implementation" / "vertical-uat.md"


def section(text: str, heading: str) -> str:
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else len(text)]


def table_after(text: str, marker: str) -> list[list[str]]:
    """The rows of the first Markdown table after ``marker``: cells stripped, header and rule dropped."""
    lines = text[text.index(marker):].splitlines()
    rows, started = [], False
    for line in lines[1:]:
        if line.startswith("|"):
            started = True
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif started:
            break
    return [r for r in rows[2:]]


def names(rows: list[list[str]]) -> tuple[str, ...]:
    return tuple(re.fullmatch(r"`([a-z_]+)`", r[0]).group(1) for r in rows)  # type: ignore[union-attr]


def test_the_counters_and_their_thresholds_equal_the_documents():
    ledger_section = section(DOC.read_text(encoding="utf-8"), "## 4. The burden ledger")
    assert "**Operator counters (all must be 0):**" in ledger_section
    assert "**Lead counters (all must be 0):**" in ledger_section
    assert names(table_after(ledger_section, "**Operator counters")) == L.OPERATOR_COUNTERS
    assert names(table_after(ledger_section, "**Lead counters")) == L.LEAD_COUNTERS
    assert L.THRESHOLDS == {c: 0 for c in L.OPERATOR_COUNTERS + L.LEAD_COUNTERS}
    assert L.STEERING_ONLY == {"mechanical_calls"} and "only a steering-on run is held to 0" in ledger_section


def test_v1s_decisions_and_the_hard_limits_equal_the_documents():
    text = DOC.read_text(encoding="utf-8")
    ledger_section = section(text, "## 4. The burden ledger")
    listed = re.search(r"V1 must list exactly ((?:`[a-z_]+`(?:, )?)+)\.", ledger_section)
    assert listed is not None
    assert tuple(re.findall(r"`([a-z_]+)`", listed.group(1))) == L.V1_DECISIONS
    assert names(table_after(ledger_section, "**Hard limits")) == L.HARD_LIMITS
    assert f"`{L.NOT_REFUSED}`" in ledger_section and f"`{L.UNNAMED}`" in ledger_section
    minimum = re.search(r"\*\*Today's minimum containment label:\*\* `([a-z_]+)` on Windows, `([a-z_]+)` on Linux",
                        ledger_section)
    assert minimum is not None
    assert {"win32": minimum.group(1), "linux": minimum.group(2)} == L.CONTAINMENT_MINIMUM


def test_the_vertical_uat_stays_in_shadow_until_the_operator_flips_it():
    assert L.VERTICAL_MODE == "shadow"
    assert L.VERTICAL_MODE in L.VERTICAL_MODES
    assert DOC.read_text(encoding="utf-8").startswith("# The vertical UAT (v1)")
    assert '**Status:** in shadow (`VERTICAL_MODE = "shadow"`)' in DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- classification


def test_an_operator_input_counts_every_piece_of_machinery_it_carries():
    led = L.Ledger("unit")
    credential = "aew1.tk_" + "0" * 16 + "." + "A" * 24
    led.operator_input(f"aew manifest adopt --token {credential} --expect-rev 3", step="s",
                       argv=["manifest", "adopt", "--token", "<credential>", "--expect-rev", "3"])
    led.operator_input("aew lead acquire --expect-rev 0", step="s", argv=["lead", "acquire", "--expect-rev", "0"],
                       shown=f"token {credential}")
    led.operator_input("send this to R-INV-0003-1", step="s")
    led.operator_input("yes", step="answer")
    counts = led.counts()
    assert (counts["credentials"], counts["revisions"], counts["manifest_adopts"], counts["seat_operations"],
            counts["run_ids"], counts["invocation_ids"]) == (2, 2, 1, 1, 1, 0)
    assert credential not in str(led.to_json())  # redacted on the way in


def test_a_revision_the_projection_supplied_still_counts():
    led = L.Ledger("unit")
    led.lead_event({"kind": "call", "via": "mcp", "tool": "ticket_start", "offered": True,
                    "arguments": {"expect_rev": 6, "work_id": "T-0001"}, "ok": True, "mechanical": True})
    led.lead_event({"kind": "call", "via": "mcp", "tool": "status", "arguments": {}, "ok": True})
    counts = led.counts()
    assert counts["revision_args"] == 1 and counts["guessed_commands"] == 0 and counts["mechanical_calls"] == 1
    assert "mechanical_calls" not in led.over()  # steering off: measured, not held to 0
    on = L.Ledger("unit", steering=True)
    on.lead_event({"kind": "call", "via": "mcp", "tool": "harness_wait", "offered": True, "arguments": {"runs": []},
                   "ok": True, "mechanical": True})
    assert on.over() == {"mechanical_calls": 1}


def test_each_lead_fallback_lands_on_its_counter():
    led = L.Ledger("unit")
    led.lead_event({"kind": "call", "via": "mcp", "tool": "ticket_draft", "arguments": {"expect_rev": 2},
                    "offered": False, "ok": True})
    led.lead_event({"kind": "call", "via": "mcp", "tool": "explain", "arguments": {"work_id": "T-0001"}, "ok": True})
    led.lead_event({"kind": "call", "via": "mcp", "tool": "cli", "arguments": {"argv": ["status"]}, "ok": False,
                    "stopped": {"error": {"code": "TOOL_NOT_EXPOSED"}}})
    led.lead_event({"kind": "call", "via": "shell", "tool": "aew", "arguments": ["plan", "accept", "--help"],
                    "ok": True})
    led.lead_event({"kind": "ambiguous", "available": ["a", "b"]})
    led.lead_event({"kind": "stale_retry", "evidence": {"tool": "x"}})
    counts = led.counts()
    assert (counts["guessed_commands"], counts["help_calls"], counts["cli_tool_calls"], counts["shell_aew_calls"],
            counts["refusals"], counts["ambiguous_next_action"], counts["stale_retries"],
            counts["revision_args"]) == (1, 2, 1, 1, 1, 1, 1, 1)


def test_the_ledger_and_its_summary_are_written_together(tmp_path):
    led = L.Ledger("unit")
    led.decision("approve the plan?", "yes", label="plan", asked_by="lead")
    led.hard_limit("containment", L.HELD, labels={})
    path = led.write(tmp_path)
    assert path.name == "vertical-ledger.json" and (tmp_path / "vertical-summary.txt").exists()
    summary = (tmp_path / "vertical-summary.txt").read_text(encoding="utf-8")
    assert "decisions: plan -> yes" in summary and "hard limit containment: held" in summary
    assert len(summary.splitlines()) <= 24  # one screen
