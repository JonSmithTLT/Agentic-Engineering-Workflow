"""The scripted Lead follows a printed hint with its shown inputs, or reports that it is incomplete."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

import printed_commands as P
import pytest
from vertical import hints as H
from vertical.lead import Lead
from vertical.ledger import COUNTERS, Ledger

from aew.cli.main import build_parser
from aew.errors import UsageError

T, REV = "T-0001", 17
PRIOR = ["--prior-value", "ASSIGNED"]


# ---------------------------------------------------------------------------------------------- filling


@pytest.mark.parametrize(("printed", "expected"), [
    (f"work transition {T} --to RUNNING --prior-value ASSIGNED", ["work", "transition", T, "--to", "RUNNING", *PRIOR]),
    (f"work transition {T} --prior-value ASSIGNED --to RUNNING", ["work", "transition", T, *PRIOR, "--to", "RUNNING"]),
    ("work transition <T> --to RUNNING --prior-value ASSIGNED", ["work", "transition", T, "--to", "RUNNING", *PRIOR]),
    ("work transition --to RUNNING --prior-value ASSIGNED", ["work", "transition", T, "--to", "RUNNING", *PRIOR]),
    (f"work assign {T} --launch", ["work", "assign", T, "--launch"]),
    ("work show <unit>", ["work", "show", T]),
    (f"work redispatch {T} --reason <reason>", ["work", "redispatch", T, "--reason", H.REASON]),
    (f"work redispatch {T} --reason <why>", ["work", "redispatch", T, "--reason", H.REASON]),
    ("integrate prepare", ["integrate", "prepare", T]),
    ("work redispatch --reason <reason>", ["work", "redispatch", T, "--reason", H.REASON]),
    ("resume --json", ["resume", "--json"]),
    # The hint already names another subject and binds its current run.
    ("harness launch INV-0012 --prior-value none", ["harness", "launch", "INV-0012", "--prior-value", "none"]),
    ("harness wait R-INV-0012-1", ["harness", "wait", "R-INV-0012-1"]),
])
def test_a_hint_is_filled_to_the_exact_argv(printed: str, expected: list[str]) -> None:
    assert H.fill_hint(printed, T) == expected


@pytest.mark.parametrize("printed", [
    "harness launch <invocation from aew harness status>",  # the Lead would have to go and read it
    f"work staff {T} --execute <card>",
    f"plan accept {T} --revision <n>",
    f"verify classify {T} --as <CLASS> --reason <reason>",
    "stage <continue|abandon> S-1",
    f"work transition {T} --to REVIEW_PENDING|VERIFY_PENDING",  # alternatives: no basis to pick
    "stage continue|abandon S-1 --rationale <reason>",
    f"plan reconfirm {T} --reason ...",
    "evidence ingest {evidence}",
    f"work transition {T} --to <RUNNING",  # a piece of a placeholder
    f"work transition {T} --reason 'unbalanced",
    f"work transition {T} --to RUNNING --prior-value <current state>",  # caller must read it first
])
def test_a_hint_the_lead_cannot_complete_is_not_followable(printed: str) -> None:
    with pytest.raises(H.NotFollowable):
        H.fill_hint(printed, T)


def test_a_scoped_approval_binding_is_copied_exactly() -> None:
    digest = "ab" * 32
    assert H.fill_hint(f"work close {T} --approval-digest {digest}", T) == [
        "work", "close", T, "--approval-digest", digest]


def test_a_plain_word_standing_for_a_value_goes_through_as_printed() -> None:
    """The limit ``hints``' docstring states: nothing marks `NAME` or `WHY` as a stand-in, so neither is refused. The
    live one is outside the modules that feed a Lead's hints; if it moves or a change refuses these, the docstring's
    limit needs reading again."""
    assert H.fill_hint("opencode --provider-env NAME", T) == ["opencode", "--provider-env", "NAME"]
    assert H.fill_hint(f"work redispatch {T} --reason WHY", T)[-1] == "WHY"
    live = [site for site in P.ast_sites() if site.text == "aew opencode --provider-env NAME"]
    assert live and not [site.key for site in live if site.path in HINT_SOURCES]


def test_every_placeholder_a_printed_command_may_hold_is_filled_or_refused() -> None:
    """Each entry of ``printed_commands.PLACEHOLDERS``, and the driver's names are all among them, so a name changed
    there cannot leave a fill here that matches nothing."""
    assert {*H.SUBJECTS, *H.REASONS} <= set(P.PLACEHOLDERS)
    for name in P.PLACEHOLDERS:
        try:
            argv = H.fill_hint(f"work close {T} --option {name}", T)
        except H.NotFollowable:
            assert name not in (*H.SUBJECTS, *H.REASONS)
        else:
            assert name in (*H.SUBJECTS, *H.REASONS) and not H.NOT_FILLED & set("".join(argv))


def _census() -> list[tuple[P.Site, list[str] | None]]:
    out = []
    for site in P.ast_sites():
        if site.kind != "span":
            continue
        try:
            out.append((site, H.fill_hint(site.text.removeprefix("aew "), T)))
        except H.NotFollowable:
            out.append((site, None))
    return out


def test_no_printed_command_goes_through_with_a_placeholder_in_it() -> None:
    """The class, over every code span the finder sees in ``src/aew`` (a superset of what a hint can print; what the
    finder cannot see is listed in ``printed_commands``' docstring)."""
    census = _census()
    assert len(census) > 100  # the finder still finds them
    assert {followed is None for _, followed in census} == {True, False}
    for site, argv in census:
        if argv is not None:
            assert not [a for a in argv if H.NOT_FILLED & set(a)], site.key
            assert all(not word.startswith("--expect-rev") for word in argv), site.key


# The modules whose text reaches a projection's hints (``ResumeOps.next_actions``, through ``projection._guidance``).
HINT_SOURCES = ("src/aew/engine/resume_ops.py", "src/aew/engine/harness_ops.py", "src/aew/engine/gate_ops.py")


def _parse_failure(argv: list[str], site: P.Site) -> str | None:
    """Why the exact argv fails the real parser."""
    try:
        P.parse("aew " + shlex.join(argv), fenced=False, exprs=site.exprs)
    except P.PrintedCommandError as exc:
        return str(exc)
    return None


def test_a_filled_hint_parses_as_printed() -> None:
    """Every whole command a hint can print parses once filled. A mention (`aew evidence ingest`) names a command and is
    not held to its arguments; when a hint prints one, the run's ``hint_usage_error`` shows it."""
    results, whole = {}, 0
    for site, argv in _census():
        if (argv is not None and site.path in HINT_SOURCES
                and (P.SLOT.search(site.text) or not P.mention(site.text, allow_required_options=True))):
            whole += 1
            results[site.key, site.shown] = _parse_failure(argv, site)
    assert len(results) == whole > 20  # two spans on one line are two results (#325's review, F4)
    failing = {key: why for key, why in results.items() if why}
    assert not failing, failing


def test_the_forced_kill_hint_parses_with_the_real_parser() -> None:
    """The one that stalled: the hint at ASSIGNED, filled, binds the displayed starting state."""
    argv = H.fill_hint(f"work transition {T} --to RUNNING --prior-value ASSIGNED", T)
    [parsed] = P.parse("aew " + shlex.join(argv), fenced=False)
    assert (parsed.work_id, parsed.to, parsed.prior_value) == (T, "RUNNING", "ASSIGNED")


# ---------------------------------------------------------------------------------------------- classifying


def _argparse_error(capsys: pytest.CaptureFixture[str], argv: list[str]) -> dict[str, Any]:
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)
    return {"code": None, "message": capsys.readouterr().err.strip()[-400:]}  # as ``Lead.shell`` reports it


def test_the_real_parsers_errors_are_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    mangled = _argparse_error(capsys, ["work", "transition", T, "--to", "RUNNING", "from", "aew", "status>",
                                       ])
    assert "unrecognized arguments: from aew status>" in mangled["message"]
    assert H.is_usage_error(mangled) and H.parse_failed(mangled)
    usage_lists_launch = _argparse_error(capsys, ["work", "assign"])
    assert "--launch" in usage_lists_launch["message"] and H.parse_failed(usage_lists_launch)


@pytest.mark.parametrize(("error", "usage", "parse"), [
    ({"code": UsageError.code, "message": "in a Lead session, dispatch with --launch"}, True, False),  # right: AEW's
    ({"code": "GATE_UNSATISFIED", "message": f"{T} has no active implementer invocation"}, False, False),  # wrong
    ({"code": "GATE_UNSATISFIED", "message": "see: error: in the message"}, False, False),  # a code says it is AEW's
    ({"code": None, "message": "no such thing"}, False, False),
    ({}, False, False),  # missing
])
def test_only_a_usage_error_is_classified_as_one(error: dict[str, Any], usage: bool, parse: bool) -> None:
    assert (H.is_usage_error(error), H.parse_failed(error)) == (usage, parse)


# ---------------------------------------------------------------------------------------------- the Lead's fallback


class _Lead(Lead):
    """The Lead's ``gap_hint`` with the shell and the typed surface answered by the test."""

    def __init__(self, tmp: Path, answers: list[dict[str, Any]]) -> None:
        super().__init__({"events": str(tmp / "events.jsonl"), "chat": str(tmp / "chat")})
        self.subject, self.step = T, f"{T}:ASSIGNED"
        self.answers = answers
        self.ran: list[list[str]] = []

    def shell(self, argv: list[str], *, why: str, stdin: str | None = None) -> dict[str, Any]:
        self.ran.append(argv)
        return self.answers.pop(0)

    def call(self, tool: str, arguments: dict[str, Any], *, offered: bool = False, mechanical: bool = False,
             why: str = "") -> dict[str, Any]:
        return {"revision": REV + 1}

    def events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines()]

    def kinds(self) -> list[str]:
        return [e["kind"] for e in self.events()]


def _refused(code: str | None, message: str) -> dict[str, Any]:
    return {"ok": False, "json": None, "error": {"code": code, "message": message}}


USAGE = "usage: aew work transition [-h]\naew work transition: error: unrecognized arguments: from aew status>"
HINT = f"work transition {T} --to RUNNING --prior-value ASSIGNED"
PROJECTION = {"revision": REV, "hints": [f"implementer INV-0001 was launched: `aew {HINT}`"]}


def _after_twelve_gaps(*events: dict[str, Any]) -> Ledger:
    """A ledger with 12 gaps ahead of ``events``. The summary's list holds 12, and forced-kill reaches its hint at
    ASSIGNED as number 15, so a test with only the event never meets the cap (#325's review, F1)."""
    ledger = Ledger("unit")
    for n in range(12):
        ledger.lead_event({"kind": "gap", "step": f"{T}:{n}", "gap": "earlier", "why": "an earlier gap"})
    for event in events:
        ledger.lead_event(event)
    return ledger


def _times_printed_alone(event: dict[str, Any]) -> int:
    """How many of the summary's lines show ``event``, with room in the list of gaps, where a second line would go."""
    ledger = Ledger("unit")
    ledger.lead_event(event)
    return sum(event["why"] in line for line in ledger.summary().splitlines())


def test_the_lead_reads_the_hint_as_printed() -> None:
    lead = Lead.__new__(Lead)
    assert lead.hinted_command(PROJECTION) == HINT
    assert lead.hinted_command({"hints": ["launch the implementer, then move to RUNNING"]}) is None
    assert lead.hinted_command({}) is None


def test_the_hints_refusal_reaches_the_redispatch_branch(tmp_path: Path) -> None:
    """The forced-kill stall: the filled command runs, the product refuses it, and the refusal is what `gap`
    redispatches on. Dropping two tokens instead makes a usage error and leaves ``last_refusal`` empty."""
    lead = _Lead(tmp_path, [_refused("GATE_UNSATISFIED", f"{T} has no active implementer invocation")])
    assert lead.gap_hint(HINT, PROJECTION)
    assert lead.ran == [["work", "transition", T, "--to", "RUNNING", *PRIOR]]
    assert lead.kinds() == ["gap", "stale_hint"]
    assert "no active implementer invocation" in lead.last_refusal


def test_a_hint_the_lead_cannot_complete_runs_nothing_and_is_recorded(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [])
    assert lead.gap_hint("harness launch <invocation from aew harness status>", PROJECTION)
    assert lead.ran == []
    [gap] = lead.events()
    assert gap["gap"] == "hint_not_followable" and "<invocation from aew harness status>" in gap["why"]
    lines = _after_twelve_gaps(gap).summary().splitlines()
    assert lines.count(f"hint_not_followable: {T}:ASSIGNED {gap['why']}") == 1  # past the 12
    assert _times_printed_alone(gap) == 1


def test_a_mangled_hint_is_an_observation_with_no_counter_and_no_threshold(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(None, USAGE)])
    lead.gap_hint(HINT, PROJECTION)
    assert lead.kinds() == ["gap", "hint_usage_error"]  # a usage error is not a refusal of the hint's step
    assert lead.last_refusal == ""
    usage = lead.events()[-1]
    assert usage["why"].endswith("unrecognized arguments: from aew status>")

    ledger = _after_twelve_gaps(usage)
    assert ledger.observations[-1]["kind"] == "lead.hint_usage_error"
    assert ledger.counts() == dict.fromkeys(COUNTERS, 0) and not ledger.over()
    line = f"lead.hint_usage_error: {T}:ASSIGNED {usage['why']}"
    assert ledger.summary().splitlines().count(line) == 1  # where a reader of the run sees it, past the 12
    assert _times_printed_alone(usage) == 1
    assert _after_twelve_gaps(*[usage] * 13).summary().splitlines().count(line) == 13  # its own list has no cap


def test_a_read_command_uses_its_printed_arguments_and_runs_once(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [{"ok": True, "json": {}, "error": None}])
    lead.gap_hint(f"work roles {T}", PROJECTION)
    assert lead.ran == [["work", "roles", T]]
    assert lead.kinds() == ["gap"]


def test_a_launch_retry_that_is_a_usage_error_is_observed_too(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(UsageError.code, "in a Lead session, dispatch with --launch"),
                            _refused(None, "aew work assign: error: unrecognized arguments: --launch")])
    lead.gap_hint(f"work assign {T}", PROJECTION)
    assert lead.ran[-1] == ["work", "assign", T, "--launch", ]
    assert lead.kinds() == ["gap", "hint_usage_error"]


def test_a_refusal_asking_for_launch_is_retried_with_it(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(UsageError.code, "in a Lead session, dispatch with --launch"),
                            {"ok": True, "json": {}, "error": None}])
    lead.gap_hint(f"work assign {T}", PROJECTION)
    assert lead.ran[-1] == ["work", "assign", T, "--launch", ]
    assert lead.kinds() == ["gap"]


def test_a_usage_message_listing_launch_does_not_ask_for_it(tmp_path: Path) -> None:
    """argparse prints the command's options: `[--launch]` in a usage message is not a refusal asking for it."""
    lead = _Lead(tmp_path, [_refused(None, "usage: aew work assign [--launch]\naew work assign: error: bad argument")])
    lead.gap_hint(f"work assign {T}", PROJECTION)
    assert len(lead.ran) == 1
    assert lead.kinds() == ["gap", "hint_usage_error"]


def test_the_leads_first_words_are_the_readable_head_of_resumes_text_never_its_json() -> None:
    """The scripted Lead's status line says what ``resume`` says to a person: the head of the MCP text block
    (``aew.surface.readable``), before the JSON it carries for a model (the V-01 re-measure of 2026-11-26, C8)."""
    from vertical.lead import _text, _words

    from aew.surface import readable

    result = {"ok": True, "tool": "resume", "stopped": None, "result": {"work": [{"id": T, "kind": "ticket"}]},
              "projection": {"subject": "project", "hints": [f"{T} waits for its implementer"]}}
    text = readable.render(result)
    words = _words(_text({"content": [{"type": "text", "text": text}], "structuredContent": result}))
    assert words == text.split(readable.JSON_MARKER, 1)[0].strip()
    assert words and words.startswith("resume: done") and f"{T} waits for its implementer" in words
    assert readable.JSON_MARKER not in words and '"work"' not in words
    assert _words(_text({"structuredContent": result})) is None  # no text block: no words, never the data
