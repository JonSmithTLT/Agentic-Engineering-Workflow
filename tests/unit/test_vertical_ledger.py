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
    assert all(f"`{outcome}`" in ledger_section for outcome in L.OUTCOMES)
    assert doc_minimums(ledger_section) == L.CONTAINMENT_MINIMUM


PLATFORMS = {"Linux": "linux", "Windows": "win32"}


def label_of(cell: str) -> str | None:
    found = re.fullmatch(r"`([a-z_]+)`", cell)
    assert found is not None, cell
    return None if found.group(1) == "none" else found.group(1)


def doc_minimums(ledger_section: str) -> dict[str, dict[str, str | None]]:
    """The containment minimums table: platform, actor, minimum, since."""
    out: dict[str, dict[str, str | None]] = {}
    for platform, actor, minimum, _since in table_after(ledger_section, "**Containment minimums"):
        out.setdefault(PLATFORMS[platform], {})[actor] = label_of(minimum)
    return out


# Every minimum the spec has ever pinned (spec v1, #211; spec v2, the operator's Q8 approval, 2026-10-11). A minimum
# only ratchets up: a later value may be higher, never lower. Append a row when one is raised; never edit or remove one.
MINIMUM_HISTORY: tuple[tuple[str, str, str, str | None], ...] = (
    ("v1", "linux", L.WORKERS, "os_readonly_roots"),
    ("v1", "win32", L.WORKERS, "workdir_separation_only"),
    ("v2", "linux", L.LEAD, None),
    ("v2", "win32", L.LEAD, None),
)


def test_the_containment_minimums_only_ratchet_up():
    """Each platform's minimum, for the workers and for the Lead, is at or above every value it ever had (spec v2)."""
    assert L.LABEL_ORDER == (None, "workdir_separation_only", "os_readonly_roots")
    for version, platform, actor, earlier in MINIMUM_HISTORY:
        now = L.CONTAINMENT_MINIMUM[platform][actor]
        assert L.at_least(now, earlier), f"{platform} {actor}: {now} is below {earlier} ({version})"
    assert {(p, a) for _, p, a, _ in MINIMUM_HISTORY} == {(p, a) for p in L.CONTAINMENT_MINIMUM
                                                          for a in L.CONTAINMENT_MINIMUM[p]}
    assert L.at_least("os_readonly_roots", "workdir_separation_only") and not L.at_least(None, "os_readonly_roots")
    assert not L.at_least("something_new", None)  # a label outside the order is never taken as meeting a minimum


def test_the_lead_is_held_to_its_minimum_and_a_weaker_run_label_fails(tmp_path):
    from types import SimpleNamespace

    from vertical.scripted_operator import containment

    from aew.harness import runlog

    aew_root = tmp_path / ".aew"
    for run, label in (("R-INV-0001-1", "os_readonly_roots"), ("R-INV-0002-1", "workdir_separation_only")):
        d = runlog.run_dir(aew_root, run)
        d.mkdir(parents=True)
        runlog.write_record(d, {"run": run, "containment": {"filesystem": label}})
    led = L.Ledger("unit", platform="linux")
    assert containment(SimpleNamespace(aew_root=aew_root), led) == ["R-INV-0002-1"]
    found = led.hard_limits["containment"]
    assert found["outcome"] == L.NOT_REFUSED and found["lead"] is None and "lead_note" in found
    win = L.Ledger("unit", platform="win32")
    assert containment(SimpleNamespace(aew_root=aew_root), win) == []  # both at or above Windows' minimum
    assert win.hard_limits["containment"]["outcome"] == L.HELD


def test_the_vertical_uat_stays_in_shadow_until_the_operator_flips_it():
    assert L.VERTICAL_MODE == "shadow"
    assert L.VERTICAL_MODE in L.VERTICAL_MODES
    assert DOC.read_text(encoding="utf-8").startswith("# The vertical UAT (v2)")
    assert '**Status:** in shadow (`VERTICAL_MODE = "shadow"`)' in DOC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------- spec v2


def test_windows_is_outside_the_enforced_gate_and_says_so_first():
    """The operator's Q1(e): Windows runs and reports, outside the enforced gate, and every summary and verdict it
    prints leads with its unqualified state and the conditions still open. Linux prints no such line."""
    text = DOC.read_text(encoding="utf-8")
    assert L.ENFORCED_PLATFORMS == ("linux",)
    assert f"**{L.WINDOWS_UNQUALIFIED}.**" in text
    assert "B5q" in text and "B5 or B5b" in text and "1(g)" in text
    assert "The enforced gate is Linux only" in text
    win = L.Ledger("unit", platform="win32")
    assert not win.enforced()
    lines = win.summary().splitlines()
    assert lines[0] == L.WINDOWS_UNQUALIFIED and "open conditions: B5q" in lines[1]
    assert all(c in lines[1] for c in L.WINDOWS_OPEN_CONDITIONS)
    assert win.to_json()["qualification"] == {"platform": "win32", "state": L.WINDOWS_UNQUALIFIED,
                                              "open_conditions": list(L.WINDOWS_OPEN_CONDITIONS)}
    linux = L.Ledger("unit", platform="linux")
    assert linux.enforced() and L.WINDOWS_UNQUALIFIED not in linux.summary()
    assert linux.summary().startswith("vertical UAT unit (linux")


def test_the_verdict_on_windows_leads_with_its_state_and_drops_no_problem():
    problems = ["credentials = 3 (must be 0)", "hard limit containment: did_not_refuse"]
    win = L.Ledger("unit", platform="win32").verdict_text(problems)
    assert win.startswith(L.WINDOWS_UNQUALIFIED + "\n  open conditions: B5q")
    assert all(p in win for p in problems)
    linux = L.Ledger("unit", platform="linux").verdict_text(problems)
    assert linux.startswith("credentials = 3") and L.WINDOWS_UNQUALIFIED not in linux
    assert all(p in linux for p in problems)


def test_the_pin_counts_once_per_endpoint_lifetime_and_never_as_a_credential():
    """Authenticate at most once: the first PIN in an endpoint's lifetime is allowed; any further one while it lives
    is counted. A new endpoint (another project, another login session) is a new lifetime."""
    led = L.Ledger("unit", platform="linux")
    led.pin_entered("endpoint-a", step="open")
    assert led.counts()["pin_reentries"] == 0 and led.counts()["credentials"] == 0
    led.pin_entered("endpoint-b", step="open")
    assert led.counts()["pin_reentries"] == 0
    led.pin_entered("endpoint-a", step="configure")
    assert led.counts()["pin_reentries"] == 1 and led.over() == {"pin_reentries": 1}
    assert [o["endpoint"] for o in led.observations if o["kind"] == "pin_entered"] == ["endpoint-a", "endpoint-b"]


def test_a_console_challenge_is_counted_on_windows_and_beyond_the_once_on_linux():
    win = L.Ledger("unit", platform="win32")
    win.console_challenge("configure", step="configure")
    win.console_challenge("open", step="open")
    assert win.over() == {"windows_console_challenges": 2}
    linux = L.Ledger("unit", platform="linux")
    linux.console_challenge("open", step="open")
    assert linux.over() == {"pin_reentries": 1}
    assert L.THRESHOLDS["windows_console_challenges"] == 0 and L.THRESHOLDS["pin_reentries"] == 0


def test_only_the_operators_decisions_are_the_operators():
    """``decisions_required`` counts operator-owned decisions only. One the projection gives to the Lead is listed
    apart, never asked; with no owner stated, today's behaviour is kept and the summary says so."""
    led = L.Ledger("unit")
    led.decision("approve the plan?", "yes", label="plan", asked_by="lead", detail={"owner": "operator"})
    led.decision("publish?", "yes", label="publish", asked_by="lead", detail={"owner": None})
    led.lead_event({"kind": "own_decision", "decision": "ACCEPT_REVIEW_EVIDENCE", "owner": "lead",
                    "tool": "ticket_request_verification"})
    assert tuple(d["label"] for d in led.decisions) == L.V1_DECISIONS
    assert [o["decision"] for o in led.not_the_operators()] == ["ACCEPT_REVIEW_EVIDENCE"]
    summary = led.summary()
    assert "plan [drives -; owner operator]" in summary and "publish [drives -; owner not stated]" in summary
    assert "not the operator's: ACCEPT_REVIEW_EVIDENCE [owner lead]" in summary


class _Lead:
    """The scripted Lead's decision handling, without a session: its calls and events are recorded here."""

    def __init__(self, tools: list[str]) -> None:
        from vertical.lead import Lead

        self.lead = Lead.__new__(Lead)
        self.lead.tools = tools
        self.lead.seen = {}
        self.lead.last_projection = None
        self.calls: list[tuple[str, dict]] = []
        self.events: list[dict] = []
        self.asked: list[str] = []
        self.lead.call = lambda tool, args, **kw: self.calls.append((tool, args)) or {}
        self.lead.event = lambda kind, **facts: self.events.append({"kind": kind, **facts})
        self.lead.ask = lambda question, **kw: self.asked.append(question) or "yes"


def test_the_scripted_lead_supplies_judgment_inputs_and_never_asks_about_its_own_decisions():
    lead = _Lead(["ticket_request_verification", "ticket_prepare"])
    args = {"expect_rev": 4, "work_id": "T-0001"}
    out = lead.lead.judged({"action": "ticket_request_verification",
                            "judgment_inputs": {"review_evidence": {"options": ["INV-0002-review-5", "x"]}}}, args)
    assert out == {**args, "review_evidence": "INV-0002-review-5"} and args == {"expect_rev": 4, "work_id": "T-0001"}
    assert lead.lead.judged({"action": "a", "judgment_inputs": {"work_id": "T-9"}}, args) == args  # never overrides
    assert lead.lead.judged({"action": "a", "judgment_inputs": ["accept_verification"]}, args) == args
    assert lead.lead.judged({"action": "a"}, args) is args
    assert [e["inputs"] for e in lead.events if e["kind"] == "judgment"] == [
        ["review_evidence"], ["work_id"], ["accept_verification"]]
    decision = {"decision": "ACCEPT_VERIFICATION", "owner": "lead", "tool": "ticket_prepare",
                "arguments": {"expect_rev": 5, "work_id": "T-0001"},
                "judgment_inputs": {"verification_evidence": "INV-0003-verify-7"}}
    assert lead.lead.own_decision(decision) is True
    assert lead.calls[-1] == ("ticket_prepare", {"expect_rev": 5, "work_id": "T-0001",
                                                 "verification_evidence": "INV-0003-verify-7"})
    assert lead.asked == [] and any(e["kind"] == "own_decision" for e in lead.events)


def test_publish_console_attribution_applies_only_from_b1():
    """From the operator's Q3 answer: the publish record must be console-approved and attributed to the operator, from
    B1. Until then the hard limit stays "main moved only after the operator's yes"."""
    assert L.PUBLISH_CONSOLE_ATTRIBUTION is False
    text = DOC.read_text(encoding="utf-8")
    assert "**From B1** (the operator's Q3 answer)" in text and "main moved only after the operator's yes" in text


def test_every_approved_amendment_is_listed_and_the_pycache_one_is_marked_met():
    text = DOC.read_text(encoding="utf-8")
    amendments = section(text, "## 7. Spec v2: the approved amendments")
    assert "Q8" in amendments and "2026-10-11" in amendments
    rows = table_after(amendments, "Approved by the operator on 2026-10-11")
    assert len(rows) == 10
    assert any("`__pycache__`" in r[0] and "**already met**" in r[1] for r in rows)


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
    assert "decisions: plan [drives -; owner not stated] -> yes" in summary
    assert "hard limit containment: held" in summary
    assert len(summary.splitlines()) <= 24  # one screen


def test_a_limit_the_run_never_reached_is_not_exercised_never_a_safety_regression(tmp_path):
    """No harness run at all: containment was never exercised, which fails the test without being scored as a weaker
    label (review of PR #211, F3)."""
    from types import SimpleNamespace

    from vertical.scripted_operator import containment

    led = L.Ledger("unit")
    aew_root = tmp_path / ".aew"
    aew_root.mkdir()
    assert containment(SimpleNamespace(aew_root=aew_root), led) == []
    assert led.hard_limits["containment"]["outcome"] == L.NOT_EXERCISED != L.NOT_REFUSED
    assert L.NOT_EXERCISED in L.OUTCOMES


def test_the_summary_shows_the_tool_each_decision_drives_and_whose_it_is():
    led = L.Ledger("unit")
    led.decision("accept review evidence?", "yes", label="accept_review_evidence", asked_by="lead",
                 detail={"decision": "ACCEPT_REVIEW_EVIDENCE", "tool": "ticket_request_verification", "owner": None})
    assert ("accept_review_evidence [drives ticket_request_verification; owner not stated] -> yes"
            in led.summary())


def test_every_operator_fallback_is_listed_and_the_document_says_it_fails_the_verdict():
    led = L.Ledger("unit")
    led.observe("fallback", step="caches", ideal="(nothing)", observed="GATE_UNSATISFIED", fallback="exclude")
    led.observe("lead.gap", gap="no_ticket")
    assert [o["step"] for o in led.operator_fallbacks()] == ["caches"]
    assert "operator fallbacks: caches" in led.summary()
    assert "**Any operator fallback fails the verdict.**" in DOC.read_text(encoding="utf-8")
