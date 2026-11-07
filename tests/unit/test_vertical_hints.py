"""The scripted Lead follows a printed hint with its placeholders filled, or says it cannot (E116).

#319 made the hints' `--expect-rev` name where its value comes from, four words where the driver dropped two tokens. The
leftovers made a usage error, which recorded nothing, so V2 forced-kill stalled at ASSIGNED and its ledger total fell
from 56 to 32. Every text here is built from the owner, ``aew.harness.contract``; the printed forms come from the real
finder and go through the real parser (``printed_commands``)."""

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
from aew.harness import contract as K

T, REV = "T-0001", 17
FILLED = [K.EXPECT_REV.split()[0], str(REV)]  # how every filled command ends


# ---------------------------------------------------------------------------------------------- filling


@pytest.mark.parametrize(("printed", "expected"), [
    (f"work transition {T} --to RUNNING {K.EXPECT_REV}", ["work", "transition", T, "--to", "RUNNING"]),  # #319's form
    (f"work transition {T} --to RUNNING --expect-rev={K.REVISION}", ["work", "transition", T, "--to", "RUNNING"]),
    (f"work transition {T} --to RUNNING --expect-rev N", ["work", "transition", T, "--to", "RUNNING"]),  # before #319
    (f"work transition {T} --to RUNNING --expect-rev=N", ["work", "transition", T, "--to", "RUNNING"]),
    (f"work transition {T} --to RUNNING --expect-rev 3", ["work", "transition", T, "--to", "RUNNING"]),
    (f"work transition {T} --to RUNNING", ["work", "transition", T, "--to", "RUNNING"]),  # none printed: added
    (f"work assign {T} {K.EXPECT_REV} --launch", ["work", "assign", T, "--launch"]),  # the retries need it last
    (f"work transition <T> --to RUNNING {K.EXPECT_REV}", ["work", "transition", T, "--to", "RUNNING"]),
    (f"work close <unit> {K.EXPECT_REV}", ["work", "close", T]),
    (f"work redispatch {T} --reason <reason> {K.EXPECT_REV}", ["work", "redispatch", T, "--reason", H.REASON]),
    (f"work redispatch {T} --reason <why> {K.EXPECT_REV}", ["work", "redispatch", T, "--reason", H.REASON]),
    (f"work transition --to RUNNING {K.EXPECT_REV}", ["work", "transition", T, "--to", "RUNNING"]),  # subject added
    ("integrate prepare", ["integrate", "prepare", T]),
    (f"work redispatch --reason <reason> {K.EXPECT_REV}", ["work", "redispatch", T, "--reason", H.REASON]),
    # The hint already names what it acts on: another id is no reason to add the subject.
    (f"harness launch INV-0012 {K.EXPECT_REV}", ["harness", "launch", "INV-0012"]),
    ("harness wait R-INV-0012-1", ["harness", "wait", "R-INV-0012-1"]),
])
def test_a_hint_is_filled_to_the_exact_argv(printed: str, expected: list[str]) -> None:
    assert H.fill_hint(printed, T, REV) == [*expected, *FILLED]


@pytest.mark.parametrize("printed", [
    f"harness launch <invocation from aew harness status> {K.EXPECT_REV}",  # the Lead would have to go and read it
    f"work staff {T} --execute <card> {K.EXPECT_REV}",
    f"plan accept {T} --revision <n> {K.EXPECT_REV}",
    f"verify classify {T} --as <CLASS> --reason <reason> {K.EXPECT_REV}",
    f"stage <continue|abandon> S-1 {K.EXPECT_REV}",
    f"work transition {T} --to REVIEW_PENDING|VERIFY_PENDING {K.EXPECT_REV}",  # alternatives: no basis to pick
    f"stage continue|abandon S-1 --rationale <reason> {K.EXPECT_REV}",
    f"plan reconfirm {T} --reason ... {K.EXPECT_REV}",
    "evidence ingest {evidence}",
    f"work transition {T} --to <RUNNING {K.EXPECT_REV}",  # a piece of a placeholder
    f"work transition {T} --reason 'unbalanced {K.EXPECT_REV}",
    f"work transition {T} --to RUNNING --expect-rev <the revision>",  # not the owner's text: not assumed to be it
])
def test_a_hint_the_lead_cannot_complete_is_not_followable(printed: str) -> None:
    with pytest.raises(H.NotFollowable):
        H.fill_hint(printed, T, REV)


def test_the_placeholder_comes_from_its_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing the owner's text changes what is followed: the driver holds no copy of it."""
    old = K.REVISION
    monkeypatch.setattr(K, "REVISION", "<the number aew status prints>")
    assert H.fill_hint(f"work close {T} --expect-rev {K.REVISION}", T, REV) == ["work", "close", T, *FILLED]
    with pytest.raises(H.NotFollowable):
        H.fill_hint(f"work close {T} --expect-rev {old}", T, REV)


def test_a_plain_word_standing_for_a_value_goes_through_as_printed() -> None:
    """The limit ``hints``' docstring states: nothing marks `NAME` or `WHY` as a stand-in, so neither is refused. The
    live one is outside the modules that feed a Lead's hints; if it moves or a change refuses these, the docstring's
    limit needs reading again."""
    assert H.fill_hint("opencode --provider-env NAME", T, REV) == ["opencode", T, "--provider-env", "NAME", *FILLED]
    assert H.fill_hint(f"work redispatch {T} --reason WHY", T, REV)[-3:] == ["WHY", *FILLED]
    live = [site for site in P.ast_sites() if site.text == "aew opencode --provider-env NAME"]
    assert live and not [site.key for site in live if site.path in HINT_SOURCES]


def test_every_placeholder_a_printed_command_may_hold_is_filled_or_refused() -> None:
    """Each entry of ``printed_commands.PLACEHOLDERS``, and the driver's names are all among them, so a name changed
    there cannot leave a fill here that matches nothing."""
    assert {K.REVISION, *H.SUBJECTS, *H.REASONS} <= set(P.PLACEHOLDERS)
    for name in P.PLACEHOLDERS:
        try:
            argv = H.fill_hint(f"work close {T} --option {name}", T, REV)
        except H.NotFollowable:
            assert name not in (K.REVISION, *H.SUBJECTS, *H.REASONS)
        else:
            assert name in (K.REVISION, *H.SUBJECTS, *H.REASONS) and not H.NOT_FILLED & set("".join(argv))


def _census() -> list[tuple[P.Site, list[str] | None]]:
    out = []
    for site in P.ast_sites():
        if site.kind != "span":
            continue
        try:
            out.append((site, H.fill_hint(site.text.removeprefix("aew "), T, REV)))
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
            assert argv[-2:] == FILLED, site.key


# The modules whose text reaches a projection's hints (``ResumeOps.next_actions``, through ``projection._guidance``).
HINT_SOURCES = ("src/aew/engine/resume_ops.py", "src/aew/engine/harness_ops.py", "src/aew/engine/gate_ops.py")
# Commands that take no subject, so the driver's added subject cannot parse. They never reach the Lead's projection: its
# subject is a Ticket, `_guidance` keeps only that subject's lines, and these are the project's, or a parent's.
NOT_A_TICKETS = {f"aew lead acquire {K.EXPECT_REV}", f"aew lead takeover {K.EXPECT_REV} --reason <reason>",
                 f"aew migrate {K.EXPECT_REV}", f"aew history audit {K.EXPECT_REV}",
                 f"aew history audit {K.EXPECT_REV} --full"}


def _parse_failure(argv: list[str], site: P.Site) -> str | None:
    """Why ``argv`` does not parse with the real parser (the driver's own retry without the revision included)."""
    why = None
    for candidate in (argv, argv[:-2]):
        try:
            P.parse("aew " + shlex.join(candidate), fenced=False, exprs=site.exprs)
            return None
        except P.PrintedCommandError as exc:
            why = why or str(exc)
    return why


def test_a_filled_hint_parses_as_printed() -> None:
    """Every whole command a hint can print parses once filled. A mention (`aew evidence ingest`) names a command and is
    not held to its arguments; when a hint prints one, the run's ``hint_usage_error`` shows it. Each exception is
    live."""
    results, whole = {}, 0
    for site, argv in _census():
        if argv is not None and site.path in HINT_SOURCES and (P.SLOT.search(site.text) or not P.mention(site.text)):
            whole += 1
            results[site.key, site.shown] = _parse_failure(argv, site)
    assert len(results) == whole > 20  # two spans on one line are two results (#325's review, F4)
    failing = {key: why for key, why in results.items() if why and key[1] not in NOT_A_TICKETS}
    assert not failing, failing
    assert {shown for (_, shown), why in results.items() if why} == NOT_A_TICKETS


def test_the_forced_kill_hint_parses_with_the_real_parser() -> None:
    """The one that stalled: the hint at ASSIGNED, filled, is a command the real CLI parses, with a number."""
    argv = H.fill_hint(f"work transition {T} --to RUNNING {K.EXPECT_REV}", T, REV)
    [parsed] = P.parse("aew " + shlex.join(argv), fenced=False)
    assert (parsed.work_id, parsed.to, parsed.expect_rev) == (T, "RUNNING", REV)


# ---------------------------------------------------------------------------------------------- classifying


def _argparse_error(capsys: pytest.CaptureFixture[str], argv: list[str]) -> dict[str, Any]:
    with pytest.raises(SystemExit):
        build_parser().parse_args(argv)
    return {"code": None, "message": capsys.readouterr().err.strip()[-400:]}  # as ``Lead.shell`` reports it


def test_the_real_parsers_errors_are_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    mangled = _argparse_error(capsys, ["work", "transition", T, "--to", "RUNNING", "from", "aew", "status>",
                                       "--expect-rev", "17"])
    assert "unrecognized arguments: from aew status>" in mangled["message"]
    assert H.is_usage_error(mangled) and H.parse_failed(mangled)
    usage_lists_launch = _argparse_error(capsys, ["work", "assign", T, "--expect-rev", "x"])
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
HINT = f"work transition {T} --to RUNNING {K.EXPECT_REV}"
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
    assert lead.ran == [["work", "transition", T, "--to", "RUNNING", *FILLED]]
    assert lead.kinds() == ["gap", "stale_hint"]
    assert "no active implementer invocation" in lead.last_refusal


def test_a_hint_the_lead_cannot_complete_runs_nothing_and_is_recorded(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [])
    assert lead.gap_hint(f"harness launch <invocation from aew harness status> {K.EXPECT_REV}", PROJECTION)
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


def test_a_read_command_refusing_the_revision_is_retried_without_it_and_not_observed(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(None, "aew work roles: error: unrecognized arguments: --expect-rev 17"),
                            {"ok": True, "json": {}, "error": None}])
    lead.gap_hint(f"work roles {T}", PROJECTION)
    assert lead.ran == [["work", "roles", T, *FILLED], ["work", "roles", T]]
    assert lead.kinds() == ["gap"]


def test_a_retry_that_is_a_usage_error_is_observed_too(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(None, "aew x: error: unrecognized arguments: --expect-rev 17"),
                            _refused(None, "aew x: error: the following arguments are required: --evidence")])
    lead.gap_hint("evidence ingest", PROJECTION)
    assert lead.kinds() == ["gap", "hint_usage_error"]


def test_a_launch_retry_that_is_a_usage_error_is_observed_too(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(UsageError.code, "in a Lead session, dispatch with --launch"),
                            _refused(None, "aew work assign: error: unrecognized arguments: --launch")])
    lead.gap_hint(f"work assign {T} {K.EXPECT_REV}", PROJECTION)
    assert lead.ran[-1] == ["work", "assign", T, "--launch", "--expect-rev", str(REV + 1)]
    assert lead.kinds() == ["gap", "hint_usage_error"]


def test_a_refusal_asking_for_launch_is_retried_with_it(tmp_path: Path) -> None:
    lead = _Lead(tmp_path, [_refused(UsageError.code, "in a Lead session, dispatch with --launch"),
                            {"ok": True, "json": {}, "error": None}])
    lead.gap_hint(f"work assign {T} {K.EXPECT_REV}", PROJECTION)
    assert lead.ran[-1] == ["work", "assign", T, "--launch", "--expect-rev", str(REV + 1)]
    assert lead.kinds() == ["gap"]


def test_a_usage_message_listing_launch_does_not_ask_for_it(tmp_path: Path) -> None:
    """argparse prints the command's options: `[--launch]` in a usage message is not a refusal asking for it."""
    lead = _Lead(tmp_path, [_refused(None, "usage: aew work assign [--launch]\naew work assign: error: bad argument")])
    lead.gap_hint(f"work assign {T} {K.EXPECT_REV}", PROJECTION)
    assert len(lead.ran) == 1
    assert lead.kinds() == ["gap", "hint_usage_error"]
