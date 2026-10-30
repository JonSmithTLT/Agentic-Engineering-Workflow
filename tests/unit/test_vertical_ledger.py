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


# Every minimum the spec has ever pinned (spec v1, #211; spec v2, the operator's Q8 approval, 2026-10-11; #308, the
# operator's decision of 2026-10-30). A minimum only ratchets up: a later value may be higher, never lower. Append a
# row when one is raised; never edit or remove one.
MINIMUM_HISTORY: tuple[tuple[str, str, str, str | None], ...] = (
    ("v1", "linux", L.WORKERS, "os_readonly_roots"),
    ("v1", "win32", L.WORKERS, "workdir_separation_only"),
    ("v2", "linux", L.LEAD, None),
    ("v2", "win32", L.LEAD, None),
    ("#308", "linux", L.LEAD, "os_readonly_roots"),  # the operator's decision of 2026-10-30
    ("#308", "win32", L.LEAD, "workdir_separation_only"),
)


def test_the_containment_minimums_only_ratchet_up():
    """Each platform's minimum, for the workers and for the Lead, is at or above every value it ever had (spec v2)."""
    assert L.LABEL_ORDER == (None, "workdir_separation_only", "os_readonly_roots")
    for version, platform, actor, earlier in MINIMUM_HISTORY:
        now = L.CONTAINMENT_MINIMUM[platform][actor]
        assert L.at_least(now, earlier), f"{platform} {actor}: {now} is below {earlier} ({version})"
    assert {(p, a) for _, p, a, _ in MINIMUM_HISTORY} == {(p, a) for p in L.CONTAINMENT_MINIMUM
                                                          for a in L.CONTAINMENT_MINIMUM[p]}
    lowered = {**L.CONTAINMENT_MINIMUM["linux"], L.LEAD: "workdir_separation_only"}  # planted: a lowering fails
    assert any(not L.at_least(lowered[a], earlier) for _, p, a, earlier in MINIMUM_HISTORY if p == "linux")
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
    lab = SimpleNamespace(aew_root=aew_root, tmp=tmp_path)
    led = L.Ledger("unit", platform="linux")
    # No Lead session recorded a label: below the Lead's minimum on both platforms since #308
    assert containment(lab, led) == ["R-INV-0002-1", L.LEAD]
    found = led.hard_limits["containment"]
    assert found["outcome"] == L.NOT_REFUSED and found["lead"] is None and "lead_note" in found
    win = L.Ledger("unit", platform="win32")
    assert containment(lab, win) == [L.LEAD]  # both runs at or above Windows' minimum; the Lead has no label
    d = runlog.run_dir(aew_root, "lead-20261030T000000Z-1")
    d.mkdir(parents=True)
    (d / "label.json").write_text('{"filesystem": "os_readonly_roots"}', encoding="utf-8")
    win = L.Ledger("unit", platform="win32")
    assert containment(lab, win) == [] and win.hard_limits["containment"]["outcome"] == L.HELD
    assert containment(lab, L.Ledger("unit", platform="linux")) == ["R-INV-0002-1"]  # the Lead now meets it
    # No worker run, a Lead label: the Lead is judged alone (review of #308, m1), never "not exercised"
    alone = SimpleNamespace(aew_root=tmp_path / "alone" / ".aew", tmp=tmp_path / "alone")
    d = runlog.run_dir(alone.aew_root, "lead-20261030T000000Z-1")
    d.mkdir(parents=True)
    (d / "label.json").write_text('{"filesystem": "workdir_separation_only"}', encoding="utf-8")
    led = L.Ledger("unit", platform="linux")
    assert containment(alone, led) == [L.LEAD] and led.hard_limits["containment"]["outcome"] == L.NOT_REFUSED
    win = L.Ledger("unit", platform="win32")
    assert containment(alone, win) == [] and win.hard_limits["containment"]["outcome"] == L.HELD


def test_the_leads_label_is_read_from_what_its_sessions_recorded(tmp_path):
    """Since CS-4 (#283) the product records each Lead session's label: its ``label.json`` beside a ``lead-*`` run,
    and the ``containment`` that ``aew opencode`` answered with. The weakest is the Lead's; none recorded is no label;
    a label outside the order is weaker than every minimum."""
    import json
    from types import SimpleNamespace

    from vertical import scripted_operator as S

    from aew.harness import runlog

    aew_root = tmp_path / ".aew"
    lab = SimpleNamespace(aew_root=aew_root, tmp=tmp_path)
    assert S.lead_label(lab) is None and S.LEAD_LABEL_WIRED is True
    d = runlog.run_dir(aew_root, "lead-20261030T000000Z-1")
    d.mkdir(parents=True)
    (d / "label.json").write_text(json.dumps({"filesystem": "os_readonly_roots"}), encoding="utf-8")
    assert S.lead_label(lab) == "os_readonly_roots"
    answer = {"ok": True, "exit": 0, "containment": {"filesystem": "workdir_separation_only"}}
    (tmp_path / "session-0.out").write_text("starting\n" + json.dumps(answer, indent=2) + "\n", encoding="utf-8")
    assert S.lead_label(lab) == "workdir_separation_only"  # the weaker session is the Lead's
    (tmp_path / "session-1.out").write_text(json.dumps({"containment": {"filesystem": "new_kind"}}), encoding="utf-8")
    assert S.lead_label(lab) == "new_kind" and not L.at_least("new_kind", None)


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


def test_a_pin_that_confirms_a_named_action_within_the_budget_is_an_approval():
    """The PIN rule (the operator's decision of 2026-10-24, F1): each PIN is recorded with its step and the action it
    confirms. Within the budget it is an approval, listed apart from the decisions and never counted, nor ever under
    `credentials`."""
    led = L.Ledger("unit", platform="linux", pin_budget=3)
    for step, action in (("open", "ATTACH_LEAD"), ("plan", "DECIDE_WORK_PROPOSAL"), ("publish", "APPROVE_INTEGRATION")):
        led.pin_entered(step=step, action=action)
    assert led.over() == {} and led.counts()["credentials"] == 0 and led.decisions == []
    assert [(a["step"], a["action"]) for a in led.approvals] == [
        ("open", "ATTACH_LEAD"), ("plan", "DECIDE_WORK_PROPOSAL"), ("publish", "APPROVE_INTEGRATION")]
    assert led.to_json()["approvals"] == led.approvals and led.to_json()["pin_budget"] == 3
    assert ("approvals (PIN budget 3): open ATTACH_LEAD; plan DECIDE_WORK_PROPOSAL; publish APPROVE_INTEGRATION"
            in led.summary())


def test_a_pin_that_confirms_no_named_action_or_goes_over_the_budget_fails():
    led = L.Ledger("unit", platform="linux", pin_budget=1)
    led.pin_entered(step="open", action=None)  # wrong: confirms nothing
    assert led.over() == {"pin_reentries": 1} and led.approvals == []
    led.pin_entered(step="open", action="ATTACH_LEAD")
    led.pin_entered(step="reopen", action="REATTACH_LEAD")  # over the budget of 1
    assert led.over() == {"pin_reentries": 2} and [a["action"] for a in led.approvals] == ["ATTACH_LEAD"]
    assert [e["note"] for e in led.entries] == ["a PIN that confirms no named action",
                                                "a PIN over the scenario's budget"]
    none = L.Ledger("unit", platform="linux")  # missing: no budget, so any PIN is over it
    none.pin_entered(step="open", action="ATTACH_LEAD")
    assert none.over() == {"pin_reentries": 1}


def test_authenticate_at_most_once_counts_aews_own_sign_ins():
    led = L.Ledger("unit", platform="linux", pin_budget=3)
    led.sign_in("startup unlock", step="open")
    assert led.over() == {}
    led.sign_in("website login", step="result")
    assert led.over() == {"pin_reentries": 1} and [s["kind"] for s in led.sign_ins] == ["startup unlock",
                                                                                         "website login"]


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
    assert containment(SimpleNamespace(aew_root=aew_root, tmp=tmp_path), led) == []
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


# ---------------------------------------------------------------------------------------------- review of #213


def test_enforce_is_refused_while_a_lead_minimum_is_no_label_on_an_enforced_platform(monkeypatch):
    """§5: `VERTICAL_MODE` cannot be `enforce` while an enforced platform's Lead minimum is no label, nor while the
    test assumes the Lead's label instead of reading it (F1). The label is read since CS-4 and the Linux minimum is
    raised since #308, so neither blocks it now; the switch to `enforce` stays the operator's (the mode is unchanged).
    A lowered minimum or an unwired label would block it again (planted)."""
    from vertical import scripted_operator

    assert L.enforce_blockers(lead_label_wired=scripted_operator.LEAD_LABEL_WIRED) == []
    assert any("lead_label" in b for b in L.enforce_blockers(lead_label_wired=False))
    monkeypatch.setitem(L.CONTAINMENT_MINIMUM, "linux", {**L.CONTAINMENT_MINIMUM["linux"], L.LEAD: None})
    assert any("linux" in b for b in L.enforce_blockers(lead_label_wired=True))
    assert "No `enforce` while a Lead minimum is no label." in DOC.read_text(encoding="utf-8")


def _ticking(lead: _Lead, decisions: list[dict]) -> None:
    """One step of the Lead's policy over a projection that requires ``decisions``."""
    lead.lead.subject, lead.lead.steering, lead.lead.step = "T-0001", False, ""
    projection = {"state": "REVIEW_PENDING", "revision": 4, "decisions_required": decisions, "actions": []}
    lead.lead.read = lambda: {"projection": projection}
    lead.lead.tick()


def test_only_an_exact_lead_or_mechanical_owner_is_taken_by_the_lead():
    """F2: a decision is the Lead's only when its owner is exactly `lead` or `mechanical`. Any other stated owner (a
    case variant, a new value, an empty string) is asked of the operator and recorded as a finding."""
    for owner in ("Operator", "operator_console", ""):
        lead = _Lead(["ticket_request_verification"])
        _ticking(lead, [{"decision": "ACCEPT_REVIEW_EVIDENCE", "owner": owner, "tool": "ticket_request_verification",
                         "arguments": {"expect_rev": 4, "work_id": "T-0001"}}])
        assert len(lead.asked) == 1, owner
        assert [e["owner"] for e in lead.events if e["kind"] == "unknown_owner"] == [owner]
        assert not any(e["kind"] == "own_decision" for e in lead.events)
    for owner in ("lead", "mechanical"):
        lead = _Lead(["ticket_request_verification"])
        _ticking(lead, [{"decision": "ACCEPT_REVIEW_EVIDENCE", "owner": owner, "tool": "ticket_request_verification",
                         "arguments": {"expect_rev": 4, "work_id": "T-0001"}}])
        assert lead.asked == [] and any(e["kind"] == "own_decision" for e in lead.events)
    assert L.SELF_OWNERS == {"lead", "mechanical"}
    led = L.Ledger("unit")
    led.lead_event({"kind": "unknown_owner", "decision": "PUBLISH", "owner": "Operator"})
    assert "unknown owners (asked of the operator): PUBLISH [owner 'Operator']" in led.summary()


def test_the_lead_never_fills_an_operator_decisions_choice():
    """F3: after the operator's answer the Lead calls the decision's tool with the arguments the projection supplied;
    judgment inputs are the Lead's, for actions and its own decisions only."""
    lead = _Lead(["integration_publish"])
    args = {"expect_rev": 4, "work_id": "T-0001"}
    _ticking(lead, [{"decision": "PUBLISH", "owner": "operator", "tool": "integration_publish", "arguments": args,
                     "judgment_inputs": {"prepared_candidate": {"options": ["cand-1", "cand-2"]}}}])
    assert len(lead.asked) == 1
    assert lead.calls == [("integration_publish", args)]
    assert not any(e["kind"] == "judgment" for e in lead.events)


def test_each_stale_revision_names_the_commit_that_staled_it():
    led = L.Ledger("unit", steering=True)
    led.observe("stale_revision", tool="ticket_start", expect_rev=6, actor={"kind": "lead"}, op="work.assign",
                by="not the Lead's own calls (the steering loop, or another)")
    assert ("stale revisions, staled by: ticket_start at 6: work.assign, not the Lead's own calls (the steering loop, "
            "or another)") in led.summary()


def test_a_pass_line_echoing_the_cause_is_not_a_diagnosis():
    """F4 (from the C1 run): V3 counts only a FAIL or WARN entry that names the cause (or its fix). Doctor's PASS line
    that echoes the configured model id is not a diagnosis, nor is an INFO detail inside a PASS line."""
    passing = ("aew 0.1 (spec set x)\n"
               "model-refs            PASS         configured: vuatprov/vuat-missing-model\n"
               "policy:pricing        PASS         INFO: no price table (FAIL means nothing here)\n"
               "doctor: 0 failure(s)\n")
    assert not L.diagnoses(passing, r"vuat-missing-model") and L.failing_entries(passing) == []
    failing = ("model-refs            FAIL         vuat-missing-model is not listed by the harness\n"
               "                                   use vuatprov/vuat-model\n"
               "containment           WARN         workdir separation only\n"
               "git                   PASS         2.45\n")
    assert L.diagnoses(failing, r"vuat-missing-model") and L.diagnoses(failing, r"use vuatprov/vuat-model\b")
    assert len(L.failing_entries(failing)) == 2 and not L.diagnoses(failing, r"2\.45")
    assert L.diagnoses('{"status": "FAIL", "detail": "VUAT_PROVIDER_KEY is unset"}', r"VUAT_PROVIDER_KEY")


def test_a_stale_revision_is_attributed_through_its_stage_intent():
    """F5: the commit is attributed through the stage intent it belongs to: the intent its refs name (stage.open), or
    the one that recorded a step at its revision; `auto_run` makes it the loop's. A failed or multi-step Lead stage is
    still the Lead's. With no intent, the actor's kind stands in and says it cannot separate the Lead from the loop."""
    from vertical.scripted_operator import staled_by

    lead = {"kind": "lead", "generation": 1}
    intents = {
        "SI-0002": {"id": "SI-0002", "tool": "ticket_request_review", "auto_run": {"mode": "run"},
                    "opened": {"rev": 12}, "steps": [{"key": "SI-0002:1", "revision": 13}]},
        "SI-0003": {"id": "SI-0003", "tool": "ticket_start", "status": "STOPPED", "opened": {"rev": 20},
                    "steps": [{"key": "SI-0003:1", "revision": 21}, {"key": "SI-0003:2", "revision": 22}]},
    }
    loop_open = staled_by({"revision": 12, "op": "stage.open", "refs": ["SI-0002"], "actor": lead}, intents)
    assert loop_open == {"by": "the steering loop", "intent": "SI-0002", "via": "stage intent",
                         "intent_tool": "ticket_request_review"}
    assert staled_by({"revision": 13, "op": "work.transition", "refs": [], "actor": lead}, intents)["by"] == \
        "the steering loop"
    # The Lead's stage, stopped after its steps (its call then failed): still the Lead's, at its open and later steps.
    assert staled_by({"revision": 20, "op": "stage.open", "refs": ["SI-0003"], "actor": lead}, intents)["by"] == \
        "the Lead"
    assert staled_by({"revision": 22, "op": "work.assign", "refs": [], "actor": lead}, intents)["intent"] == "SI-0003"
    fallback = staled_by({"revision": 40, "op": "lead.acquire", "refs": [], "actor": lead}, intents)
    assert fallback["via"] == "actor" and "the Lead, or the loop under it" in fallback["by"]
    assert staled_by({"revision": 41, "refs": [], "actor": {"kind": "operator"}}, intents)["by"] == "operator"
    # Recorded beside the call's own fields, as the acceptance module records it: no key collides.
    led = L.Ledger("unit", steering=True)
    led.observe("stale_revision", tool="ticket_start", expect_rev=11, step="s", **loop_open, actor=lead,
                op="stage.open", summary="", revision=12)
    assert "ticket_start at 11: stage.open, the steering loop" in led.summary()


def test_a_json_refusal_is_one_failing_entry_and_an_ok_answer_never_is():
    """F6: the CLI refuses with JSON on stderr. A refusal naming the variable names the cause (in its message or its
    details); an `ok: true` answer echoing it never does; a table keeps the status-word rule."""
    refusal = ('{\n  "ok": false,\n  "error": {\n    "code": "PROVIDER_ENV_UNSET",\n    "message": "the policy names '
               'VUAT_PROVIDER_KEY, which is not set",\n    "details": {"fix": "export VUAT_PROVIDER_KEY"}\n  }\n}\n')
    assert L.diagnoses(refusal, r"VUAT_PROVIDER_KEY") and L.diagnoses(refusal, r"export VUAT_PROVIDER_KEY")
    assert len(L.failing_entries(refusal)) == 1
    in_details = ('{"ok": false, "error": {"code": "X", "message": "not ready", '
                  '"details": {"model": "vuat-missing-model"}}}')
    assert L.diagnoses(in_details, r"vuat-missing-model")
    ok = '{\n  "ok": true,\n  "checks": [{"check": "model", "status": "FAIL", "detail": "vuat-missing-model"}]\n}\n'
    assert not L.diagnoses(ok, r"vuat-missing-model") and L.failing_entries(ok) == []
    mixed = "model-refs  PASS  configured: vuat-missing-model\n" + refusal
    assert L.failing_entries(mixed)[0].startswith("PROVIDER_ENV_UNSET")
    assert not L.diagnoses(mixed, r"vuat-missing-model")


def _doctor_json(ok: bool, checks: list[tuple[str, str, str]]) -> str:
    """Doctor's JSON shape (``aew doctor --json``): ``{ok, aew_version, spec_set, checks: [{check, status, detail}],
    failures}``, pretty-printed as the CLI prints it."""
    import json

    return json.dumps({"ok": ok, "aew_version": "0", "spec_set": "x",
                       "checks": [{"check": c, "status": s, "detail": d} for c, s, d in checks],
                       "failures": sum(1 for _, s, _ in checks if s == "FAIL")}, indent=2) + "\n"


def test_a_json_status_report_is_read_per_check_by_its_own_status():
    """G1: each object with a `status` is one entry with its own status. A FAIL after a PASS is found; a PASS that
    echoes the id after a FAIL elsewhere does not count; `ok: false` without an `error` drops no check and adds no
    empty entry."""
    pass_then_fail = _doctor_json(False, [
        ("git", "PASS", "2.45"), ("model-refs", "FAIL", "vuat-missing-model is not listed; use vuatprov/vuat-model")])
    assert L.diagnoses(pass_then_fail, r"vuat-missing-model") and L.diagnoses(pass_then_fail, r"vuatprov/vuat-model\b")
    fail_then_echo = _doctor_json(False, [("git", "FAIL", "git not found"),
                                          ("model-refs", "PASS", "configured: vuat-missing-model")])
    assert not L.diagnoses(fail_then_echo, r"vuat-missing-model") and L.diagnoses(fail_then_echo, r"git not found")
    entries = L.failing_entries(pass_then_fail)
    assert len(entries) == 1 and "" not in entries
    warn_only = _doctor_json(False, [("containment", "WARN", "workdir separation only")])
    assert len(L.failing_entries(warn_only)) == 1 and '"status": "WARN"' in L.failing_entries(warn_only)[0]
    assert L.failing_entries('{"ok": false}') == []
    assert L.failing_entries(_doctor_json(True, [("model-refs", "FAIL", "vuat-missing-model")])) == []


def test_a_chat_read_error_is_recorded_retried_and_loses_no_message(tmp_path, monkeypatch):
    """G2: a failed read (a sharing violation on Windows, say) neither kills the reader nor skips the message: it is
    reported, retried within the bound, and the message arrives. The scripted Lead's listener records it as
    `listener_error` and keeps hearing the operator."""
    import queue
    import threading
    from pathlib import Path

    from vertical import chat as C
    from vertical.lead import Lead

    seen: list[str] = []
    reader = C.Mailbox(tmp_path, "lead", on_error=lambda path, exc: seen.append(f"{path.name} {exc}"))
    C.Mailbox(tmp_path, "operator").send({"text": "Where do things stand?"})
    real = Path.read_text
    failures = {"left": 2}

    def flaky(self, *args, **kwargs):
        if self.name.startswith("operator-") and failures["left"]:
            failures["left"] -= 1
            raise PermissionError(32, "The process cannot access the file because it is being used by another process")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    assert reader.receive(5)["text"] == "Where do things stand?"
    assert len(seen) == 2 and len(reader.errors) == 2 and reader.read == 1

    # The Lead's listener, over the same fault: it survives, records it, and puts the line in the Lead's inbox.
    failures["left"] = 1
    lead = Lead.__new__(Lead)
    events: list[dict] = []
    lead.event = lambda kind, **facts: events.append({"kind": kind, **facts})
    lead.chat = C.Mailbox(tmp_path / "second", "lead", on_error=lead._read_error)
    lead.inbox = queue.Queue()
    C.Mailbox(tmp_path / "second", "operator").send({"text": "carry on"})
    threading.Thread(target=lead._listen, daemon=True).start()
    assert lead.inbox.get(timeout=5)["text"] == "carry on"
    assert [e["kind"] for e in events] == ["listener_error"] and "PermissionError" in events[0]["error"]


def test_a_silence_is_a_harness_fault_only_with_harness_evidence():
    """H1: a silent Lead is the harness's only with harness evidence (a chat read error, or the Lead waiting to hear
    while an operator message it has not read exists). A call that never returned, or no Lead at all, is not
    established and reads as a possible product hang, never as the harness's."""
    from vertical.scripted_operator import silence_fault

    now = "s-now"
    waiting = {"doing": "waiting_to_hear", "chat_read": 3, "session": now}
    calling = {"doing": "calling", "tool": "harness_wait", "chat_read": 3, "session": now}

    def fault_of(**kw):
        return silence_fault(**{"chat_errors": [], "events": [], "state": None, "sent": 4, "session": now, **kw})

    assert fault_of(chat_errors=["operator-0003.json: PermissionError"])[0] == "harness"
    assert fault_of(events=[{"kind": "listener_error", "session": now}], state=waiting, sent=3)[0] == "harness"
    fault, why = fault_of(state=waiting)
    assert fault == "harness" and "1 operator message" in why
    # Product-side silences: no evidence of the harness.
    assert fault_of(state=waiting, sent=3)[0] == "not established"  # every operator message read
    fault, why = fault_of(state=calling)
    assert fault == "not established" and "harness_wait" in why
    fault, why = fault_of(sent=1)
    assert fault == "not established" and "no TUI started" in why

    led = L.Ledger("unit")
    led.observe("lead_silent", waiting_for="the conversation", fault="not established",
                why="the Lead is in a call that has not returned: harness_wait")
    assert "lead silent or ended: lead_silent (not established) the Lead is in a call" in led.summary()
    assert "harness faults" not in led.summary()
    led.lead_event({"kind": "listener_error", "file": "operator-0003.json", "error": "PermissionError: busy"})
    led.observe("lead_silent", waiting_for="first words", fault="harness", why="chat read errors")
    summary = led.summary()
    assert "harness faults: lead.listener_error operator-0003.json" in summary and "lead_silent first words" in summary


def test_the_lead_records_why_it_ended_and_whose_fault_it_is(tmp_path):
    """H2 (a): an exception in the Lead's main thread is recorded as `lead_error` with its fault: the aew-lead MCP
    server ending is the product's; anything else is not established."""
    import json

    from vertical import lead as V

    events = tmp_path / "lead-events.jsonl"
    spec = tmp_path / "lead-tui.json"
    spec.write_text(json.dumps({"events": str(events), "chat": str(tmp_path / "chat"), "pidfile": str(tmp_path / "p"),
                                "state": str(tmp_path / "lead-state.json")}), encoding="utf-8")

    def ends(exc):
        def run(self):
            self.step = "T-0001:REVIEW"
            raise exc
        return run

    for exc, fault in ((RuntimeError(V.MCP_ENDED), "product"), (KeyError("x"), "not established")):
        events.unlink(missing_ok=True)
        original = V.Lead.run
        V.Lead.run = ends(exc)
        try:
            assert V.main(spec) == 1
        finally:
            V.Lead.run = original
        recorded = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
        assert recorded[-1]["kind"] == "lead_error" and recorded[-1]["fault"] == fault
        assert recorded[-1]["step"] == "T-0001:REVIEW"
    led = L.Ledger("unit")
    led.lead_event(recorded[-1])
    assert "lead silent or ended: lead.lead_error (not established) KeyError" in led.summary()


def test_recording_an_error_never_kills_the_listener(tmp_path, monkeypatch):
    """H2 (b): the listener's own event writes are best-effort. A write that keeps failing (a sharing violation on the
    events file) goes to stderr, and the listener goes on; one that fails a few times is retried and recorded."""
    import json
    import queue
    import threading

    from vertical import chat as C
    from vertical import lead as V

    monkeypatch.setattr(V, "POLL_S", 0.001)
    lead = V.Lead.__new__(V.Lead)
    lead.events_path, lead.lock, lead.step, lead.subject = tmp_path / "events.jsonl", threading.Lock(), "s", None
    lead.last_projection, lead.spec = None, {}
    real = V._append
    failing = {"left": 3}

    def flaky(path, line):
        if failing["left"]:
            failing["left"] -= 1
            raise PermissionError(32, "being used by another process")
        real(path, line)

    monkeypatch.setattr(V, "_append", flaky)
    lead.best_effort_event("listener_error", error="x")  # three failures, then written
    assert json.loads(lead.events_path.read_text(encoding="utf-8"))["kind"] == "listener_error"
    failing["left"] = 10 ** 6  # it never succeeds: reported on stderr, and the caller goes on
    lead.best_effort_event("listener_error", error="y")

    # The listener itself: a receive that raises, whose recording also fails, still delivers the next line.
    lead.chat = C.Mailbox(tmp_path / "chat", "lead")
    lead.inbox = queue.Queue()
    real_receive, calls = lead.chat.receive, {"n": 0}

    def receive(timeout, gone=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("the chat directory is busy")
        return real_receive(timeout, gone)

    lead.chat.receive = receive
    C.Mailbox(tmp_path / "chat", "operator").send({"text": "carry on"})
    threading.Thread(target=lead._listen, daemon=True).start()
    assert lead.inbox.get(timeout=5)["text"] == "carry on"


def test_a_silence_is_judged_only_on_its_own_sessions_evidence():
    """I1: on a reopen whose new Lead never starts, the previous session's state (waiting to hear, two messages read)
    and the operator's later messages (`/exit`, the reopen) must not read as a chat deadlock; nor may an earlier
    session's `listener_error`. Both are "not established"."""
    from vertical.scripted_operator import silence_fault

    before = {"doing": "waiting_to_hear", "chat_read": 2, "session": "s-old"}
    fault, why = silence_fault(chat_errors=[], events=[], state=before, sent=3, session="s-new")
    assert fault == "not established" and "no TUI started" in why
    old_error = [{"kind": "listener_error", "session": "s-old", "pid": 4242, "error": "PermissionError"}]
    later = silence_fault(chat_errors=[], events=old_error, state=None, sent=3, session="s-new")
    assert later[0] == "not established"
    # The same evidence in the session it belongs to is the harness's.
    assert silence_fault(chat_errors=[], events=old_error, state=None, sent=3, session="s-old")[0] == "harness"


def test_each_open_starts_a_fresh_session_with_no_state_left(tmp_path):
    """I1: every open gets its own id (a reused pid cannot match it), the previous session's state file is removed,
    and the operator's earlier chat errors are not this session's."""
    import json
    from types import SimpleNamespace

    from vertical import scripted_operator as S

    sync = tmp_path / "sync"
    sync.mkdir()
    (sync / "lead-state.json").write_text(json.dumps({"doing": "waiting_to_hear", "session": "s-old"}),
                                          encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    op = S.Operator.__new__(S.Operator)
    op.lab = SimpleNamespace(env={S.SCRIPTS_ENV: str(scripts)})
    op.chat = SimpleNamespace(errors=["operator-0001.json: PermissionError"])
    spec = {"state": str(sync / "lead-state.json"), "pidfile": str(sync / "lead-0.pid")}
    ids = set()
    for _ in range(2):
        written = op.new_session(spec)
        ids.add(op.session_id)
        assert written["session"] == op.session_id and "session" not in spec
        assert not (sync / "lead-state.json").exists()
        assert json.loads((scripts / S.TUI_SCRIPT).read_text(encoding="utf-8"))["session"] == op.session_id
        (sync / "lead-state.json").write_text("{}", encoding="utf-8")  # the session's own state, removed next open
    assert len(ids) == 2 and "" not in ids and op.chat_errors_at_open == 1


def test_a_scripted_lead_thread_that_dies_is_a_harness_fault_in_the_ledger():
    """Review of #217, m3 (#213's G2): a thread of the scripted Lead that dies (childdiag's exception hook, through
    the Lead's subscription) is recorded as `thread_died` with fault `harness`, and the ledger lists it among the
    harness's faults, never as AEW's silence. The product ending under it stays the product's."""
    from vertical import lead as V

    lead = V.Lead.__new__(V.Lead)
    events: list[dict] = []
    lead.event = lambda kind, **facts: events.append({"kind": kind, **facts})
    hook = V.recorded(lead)
    hook("thread_exception", "vertical-chat", RuntimeError("synthetic"), {"stack": "Traceback ..."})
    hook("thread_exception", "reader", RuntimeError(V.MCP_ENDED), {"stack": "Traceback ..."})
    assert [(e["kind"], e["fault"]) for e in events] == [("thread_died", "harness"), ("thread_died", "product")]
    led = L.Ledger("unit")
    led.lead_event(events[0])
    assert "harness faults: lead.thread_died" in led.summary()
    assert "lead silent or ended" not in led.summary()
