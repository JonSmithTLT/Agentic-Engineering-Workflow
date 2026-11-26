"""Every `aew` command AEW prints parses as printed (ITEMS 56; #311 review F2, F3; #312 review F2).

The check: every printed command the finders see in ``src/aew`` (``tests/helpers/printed_commands.py`` says how they
find them and what they cannot see) is judged as a reader runs it. A code span that is a bare command path, every word
a real (sub)command and nothing else, is a mention if its parser has no required options. Other sites must parse.
The check fills placeholders from the one table, expands any fenced block's heredoc body with the CLI's own
``fields.expand``, and parses the result with the real
``build_parser()`` (the Lead's ruling, ITEMS 56 (1)-(3)). A site that fails names its file and line. A site the check
does not hold is listed below with why; the lists are pinned both ways (an entry must still be live, and must still
fail).

Its limits:
- what the finders cannot see (``printed_commands``' docstring), each with a probe below.

It is a recogniser feeding an enforced check, so it carries the standard items: a second finder written apart from the
first, with an agreement test both ways; planted controls (a right case, each wrong case, and a missing case); a probe
of each blind spot; and a file the finders cannot read is marked, never dropped.
"""

from __future__ import annotations

import argparse
import ast
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import printed_commands as P
import pytest

from aew.engine import transitions
from aew.engine.custody_ops import LEAD_KEPT_OUT, operator_terminal_refusal
from aew.harness import contract as K
from aew.knowledge.manifest import DEFAULT_CHECKS, DEFAULT_GATES


def test_a_fields_block_keeps_yaml_quotes_backslashes_and_controls_distinct():
    raw = 'a"' + "\\" + "\x1b"
    block = K.fields_block("aew invoke cancel INV-1", {"reason": raw})
    assert block.splitlines()[2] == r'reason: "a\"\\\u001b"'


# Files B3 is changing on fix/e112-weaker-contexts (the ITEMS 56 brief, "Don't overlap"): their failing sites wait for
# a follow-up once that branch merges, rather than conflict with it. Each is pinned by (file, printed text), since B3's
# edits move its line: a failing site in these files that is not pinned fails the check, and a pinned one that is gone
# or now parses fails the liveness test (#319 review F3).
B3 = "deferred: B3's file (E112, fix/e112-weaker-contexts)"
EVIDENCE = "src/aew/engine/evidence_ops.py"
BROKER = "src/aew/harness/lead_broker.py"
DEFERRED = {
    (EVIDENCE, "aew plan reconfirm {work_id} --reason ..."): B3,
    (EVIDENCE, "aew plan reconfirm <id> --reason ..."): B3,
    (BROKER, "aew {command_name(ns)}"): f"{B3}; with the bare names #311 F3 named",
    (BROKER, "aew {name}"): f"{B3}; with the bare names #311 F3 named",
}
DEFERRED_FILES = frozenset(path for path, _ in DEFERRED)  # B3's: the one-owner tests wait for them too

# Sites whose command the finder cannot judge from the source, each with why and the test that checks it instead.
EXEMPT = {
    "src/aew/harness/contract.py:245": "the frame's owner (fields_block): its command and keys are each caller's, "
                                       "checked at each call",
    "src/aew/engine/custody_ops.py:158": "the command word comes from a value: test_operator_terminal_refusals_parse",
    "src/aew/engine/custody_ops.py:159": "the command word comes from a value: test_operator_terminal_refusals_parse",
    "src/aew/cli/capability_commands.py:145": "the command word comes from a value: "
                                              "test_each_capability_change_names_a_capability_command",
    "src/aew/harness/contract.py:392": "the command words come from bridge.MAP_OPERATIONS: "
                                       "test_the_worker_map_reads_line_names_real_commands",
}


# Pre-existing bare spans outside this change's adoption scope, pinned by file, text and count.
# The handoff accept form would expose an offer credential on the command line.
# The manifest header is part of the bytes init pins, including its informational adopt and authority references.
# Other entries preserve the existing command references and advice until their callers are updated.
LEGACY_BARE_SPANS = {
    ("engine/disposition_ops.py", "aew work dispose"): 1,
    ("engine/evidence_ops.py", "aew work redispatch"): 1,
    ("engine/guide.py", "aew authority accept"): 1,
    ("engine/guide.py", "aew evidence ingest"): 1,
    ("engine/guide.py", "aew lead takeover"): 1,
    ("engine/guide.py", "aew work transition"): 1,
    ("engine/integration_ops.py", "aew integrate requeue"): 1,
    ("engine/lead_ops.py", "aew lead handoff accept"): 1,
    ("engine/migrate_ops.py", "aew harness stop|wait"): 1,
    ("engine/nonmutating_ops.py", "aew evidence ingest"): 2,
    ("engine/nonmutating_ops.py", "aew review ingest"): 1,
    ("engine/nonmutating_ops.py", "aew verify ingest"): 1,
    ("engine/nonmutating_ops.py", "aew work acknowledge-input"): 1,
    ("engine/nonmutating_ops.py", "aew work redispatch"): 2,
    ("engine/reasons.py", "aew work reclassify"): 1,
    ("engine/resume_ops.py", "aew lead handoff accept"): 1,
    ("engine/resume_ops.py", "aew lead takeover"): 1,
    ("engine/stage_intents.py", "aew stage continue|abandon"): 1,
    ("engine/work_ops.py", "aew work redispatch"): 1,
    ("harness/contract.py", "aew submit"): 2,
    ("harness/lead_broker.py", "aew lead takeover"): 2,
    ("harness/opencode/projection.py", "aew submit"): 1,
    ("knowledge/manifest.py", "aew authority accept"): 1,
    ("knowledge/manifest.py", "aew manifest adopt"): 1,
    ("process_kind.py", "aew submit"): 1,
}


def _legacy_bare_span(site: P.Site) -> tuple[str, str]:
    return site.path.removeprefix("src/aew/"), site.shown


def _held(site: P.Site) -> bool:
    return (site.path, site.shown) not in DEFERRED and site.key not in EXEMPT


def _why_not(site: P.Site) -> str | None:
    try:
        P.check(site.text, site.kind, site.exprs)
    except P.PrintedCommandError as exc:
        return str(exc)
    return None


def test_every_printed_command_parses_as_printed() -> None:
    sites = P.ast_sites()
    assert len(sites) > 300  # the finder sees the source at all
    remaining = Counter(LEGACY_BARE_SPANS)
    failures = []
    for site in sites:
        if not _held(site) or not (why := _why_not(site)):
            continue
        key = _legacy_bare_span(site)
        if site.kind == "span" and remaining[key] > 0:
            remaining[key] -= 1
            continue
        failures.append(f"{site.key} ({site.kind}) {site.shown!r}: {why}")
    assert not +remaining, f"stale bare spans: {+remaining}"
    assert not failures, f"{len(failures)} printed commands do not run as printed:\n" + "\n".join(failures)


def test_every_exemption_and_deferral_is_still_live() -> None:
    """An entry whose site is gone, or now parses, is removed: the lists only say what the check cannot hold."""
    sites = P.ast_sites()
    by_key = {s.key: s for s in sites}
    gone = [k for k in EXEMPT if k not in by_key]
    parses = [k for k in EXEMPT if k in by_key and _why_not(by_key[k]) is None]
    failing = {(s.path, s.shown) for s in sites if _why_not(s)}
    stale = [pin for pin in DEFERRED if pin not in failing]  # gone, or every copy of it now parses
    assert not (gone or parses or stale), f"gone: {gone}; parses: {parses}; deferred site gone or parses: {stale}"


OWNER = "src/aew/harness/contract.py"
# Reject the retired flag in current guidance, including a literal in generated argv.
RETIRED_REVISION = re.compile(r"--expect-rev\b")


def _restating(pattern: re.Pattern[str], allowed: set[str]) -> list[str]:
    out = []
    for path in sorted(P.SRC.rglob("*.py")):
        rel = path.relative_to(P.ROOT).as_posix()
        if rel not in allowed | {OWNER} | DEFERRED_FILES:
            out += [f"{rel}: {m.group()!r}" for m in pattern.finditer(path.read_text(encoding="utf-8"))]
    return out


def test_no_printed_commands_take_the_retired_revision() -> None:
    sites = [site for site in P.ast_sites() if RETIRED_REVISION.search(site.shown)]
    assert not sites, sites


# The modules besides the owner that name the heredoc without writing the frame: the CLI's own help for `--fields`, and
# the contained Lead's system text telling it to pipe report text through one. Pinned by count both ways.
HEREDOC_NAMED = {"src/aew/cli/fields.py": 2, "src/aew/harness/opencode/projection.py": 1}


def test_the_fields_frame_has_one_owner() -> None:
    """Every printed `--fields - <<'EOF'` frame is written by ``contract.fields_command``/``fields_block`` (item 2;
    #319 review F2): no other module spells the heredoc, except where it is named, not written (pinned by count)."""
    named = {rel: n for rel, n in ((p.relative_to(P.ROOT).as_posix(), p.read_text(encoding="utf-8").count("<<'EOF'"))
                                   for p in sorted(P.SRC.rglob("*.py"))) if n}
    written = {rel: n for rel, n in named.items() if rel not in {OWNER} | DEFERRED_FILES}
    assert written == HEREDOC_NAMED, written


def test_a_full_history_audit_is_printed_whole() -> None:
    """``resume``'s history-audit step prints `--full` inside its command when the policy needs a full audit, so the
    reader copies the whole command (#319 review F5): each form is one span, and each parses."""
    audits = {s.text for s in P.ast_sites() if s.path == "src/aew/engine/resume_ops.py" and "history audit" in s.text}
    assert audits == {"aew history audit --record", "aew history audit --record --full"}
    assert [P.parse(a, fenced=False)[0].full for a in sorted(audits)] == [False, True]


def test_the_two_finders_agree_both_ways() -> None:
    """Finder 1 (the syntax tree) and finder 2 (the token stream), written apart, find the same printed commands at
    the same lines; each one's extra sites are listed."""
    tree = Counter((s.path, s.line, s.kind) for s in P.ast_sites())
    tokens = Counter(P.token_sites())
    only_tree = sorted((tree - tokens).elements())
    only_tokens = sorted((tokens - tree).elements())
    assert not only_tree and not only_tokens, f"syntax tree only: {only_tree}\ntokens only: {only_tokens}"


# ---------------------------------------------------------------------------------------------- planted controls

GOOD = "aew invoke cancel INV-1 --fields - <<'EOF'\nreason: 'why'\nEOF"


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        pytest.param(GOOD, "fence", id="fenced"),
        pytest.param("aew lead handoff cancel", "span", id="inline"),
        pytest.param("aew work transition <T> --to REVIEW_PENDING|VERIFY_PENDING", "span",
                     id="alternatives"),
        pytest.param("aew authority accept <candidate> --class <contracts|decisions>", "span",
                     id="choices"),
        pytest.param("aew work create --help", "span", id="help"),
        pytest.param("aew work show", "span", id="mention"),
        pytest.param("aew lead takeover --reason 'the session is gone'", "field", id="field"),
    ],
)
def test_a_right_command_passes(command: str, kind: str) -> None:
    P.check(command, kind)


@pytest.mark.parametrize(
    ("command", "kind", "why"),
    [
        pytest.param("aew invoke cancel INV-1", "field", "required: --reason", id="missing-required"),
        pytest.param(GOOD.replace("reason: 'why'", "- 'why'"), "fence", "mapping", id="non-mapping-body"),
        pytest.param(GOOD.replace("reason:", "raeson:"), "fence", "no option --raeson", id="misspelled-key"),
        pytest.param(GOOD.removesuffix("\nEOF"), "fence", "not closed", id="unterminated-heredoc"),
        pytest.param(GOOD.replace("'why'", "'why'\nEOF\nmore: 'x'"), "fence", "closes early", id="early-eof"),
        pytest.param(GOOD.replace("INV-1", "<INV>"), "fence", "not in PLACEHOLDERS: <INV>", id="unknown-placeholder"),
        pytest.param("aew work create ticket --class N --title example", "span", "invalid int value: 'N'",
                     id="bare-N"),
        pytest.param(GOOD, "span", "one line", id="heredoc-inline"),
        pytest.param("aew invoke create T-1 --role implementer|nobody", "span", "invalid choice",
                     id="bad-alternative"),
        pytest.param("aew lead takeover --expect-rev 17 --reason why", "span",
                     "unrecognized arguments: --expect-rev", id="retired-option"),
        pytest.param("aew lead takeover", "field", "required", id="bare-name-in-a-field"),
        pytest.param("aew manifest adopt", "span", "--reason", id="missing-adopt-options"),
        pytest.param("aew manifest adoptt", "span", "invalid choice", id="misspelled-mention"),
        pytest.param("aew work cancel T-1 --reason ...", "span", "elided value", id="elision"),
    ],
)
def test_the_check_refuses_each_planted_defect(command: str, kind: str, why: str) -> None:
    with pytest.raises(P.PrintedCommandError, match=why.replace("(", r"\(").replace("*", r"\*")):
        P.check(command, kind)


PLANTED = '''"""A module docstring naming `aew lead takeover`, which is not printed."""
import argparse


def refusal(work_id, held, verb):
    """A function docstring naming `aew work cancel`."""
    argparse.ArgumentParser().add_argument("--x", help="see `aew status`")
    a = f"run `aew work show {work_id}` first"
    b = ("held" if held else "run `aew work transition T-1 --prior-value RUNNING`")
    c = dict(next="aew lead takeover")
    d = {"remedy": f"aew work show {work_id}"}
    e = fields_command(f"aew invoke cancel {work_id}", "reason", verb)
    f = "a fenced block:\\n\\n```sh\\naew lead takeover --fields - <<'EOF'\\nreason: 'x'\\nEOF\\n```"
    g = fields_block("aew lead takeover", {"reason": "x"})
    h = {"cli": ["work", "reconcile", work_id, "--to", "<phase>"]}
    i = dict(cli_fallback=["aew", "work", "show", work_id])
    j = dict(cli_fallback=[x for x in ["work", "show"]], cli=held)
    return a, b, c, d, e, f, g, h, i, j
'''
# Line: (kind, whether it passes). The conditional's other branch (9), the bare name in a field (10) and the argv list
# missing reconcile's --reason (15) fail; a comprehension or a variable at an argv key (17) is not a literal.
PLANTED_SITES = {8: ("span", True), 9: ("span", False), 10: ("field", False), 11: ("field", True),
                 12: ("fence", True), 13: ("fence", True), 14: ("fence", True), 15: ("argv", False),
                 16: ("argv", True)}


def _planted(tmp_path: Path, text: str, name: str = "planted.py") -> Path:
    (tmp_path / "src" / "aew").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "aew" / name).write_bytes(text.encode())
    return tmp_path


def test_both_finders_find_each_planted_site_and_skip_what_is_not_printed(tmp_path: Path) -> None:
    """The missing case: each planted form is found by both finders, at its line, and the docstrings and help text
    are not; a finder that dropped one form fails here. Each found site is then judged as the check judges it."""
    root = _planted(tmp_path, PLANTED)
    sites = P.ast_sites(root)
    assert {s.line: s.kind for s in sites} == {n: kind for n, (kind, _) in PLANTED_SITES.items()}
    assert {(line, kind) for _, line, kind in P.token_sites(root)} == {(n, k) for n, (k, _) in PLANTED_SITES.items()}
    assert {s.line: _why_not(s) is None for s in sites} == {n: ok for n, (_, ok) in PLANTED_SITES.items()}


def test_a_file_the_finders_cannot_read_is_marked_not_dropped(tmp_path: Path) -> None:
    root = _planted(tmp_path, "x = (\n", "broken.py")
    [site] = P.ast_sites(root)
    assert site.kind == "unreadable" and site.path.endswith("broken.py")
    assert _why_not(site)
    assert [kind for _, _, kind in P.token_sites(root)] == ["unreadable"]


def test_every_placeholder_fill_parses_where_it_is_used() -> None:
    """The table is only what is in use: each placeholder appears in some printed command, in the source or in the
    guide the source renders (E130: the guide's commands are the transition table's, filled when it renders)."""
    from discovery.static import rendered_guide

    from aew.engine.harness_ops import send_route
    from aew.errors import MessagingSnapshotMismatch
    from aew.policy import execution as X

    # The fallback invocation placeholder is printed only after the f-string has been evaluated.
    with pytest.raises(MessagingSnapshotMismatch) as mismatch:
        send_route(X.MESSAGING_ENABLED, X.MESSAGING_DISABLED, "next-step")
    [(relaunch, fenced)] = P.commands(str(mismatch.value))
    [args] = P.parse(relaunch, fenced=fenced)
    assert args.invocation == "INV-0012" and args.prior_value == "R-INV-0012-1"
    # So is the run a steering step over several runs names (#547 review m1): a value the step passes in.
    steer = [c for c, _ in P.commands(K.wait_step(["R-1", "R-2"], again=True)) if c.startswith("aew harness send")]
    assert [a.run for c in steer for a in P.parse(c, fenced=False)] == ["R-0003"]
    printed = "\n".join([*(s.text for s in P.ast_sites() if _held(s)), rendered_guide(),
                         relaunch, *steer, transitions.operation_command("integrate.requeue", "T-0007")])
    unused = [name for name in P.PLACEHOLDERS if name not in printed]
    assert not unused, unused


# ---------------------------------------------------------------------------------------------- blind spots, probed

def test_operator_terminal_refusals_parse() -> None:
    """Blind spot 1, a command word from a value (``custody_ops``' ``aew {command}``): each refusal it renders, for
    every command it is given, passes once rendered."""
    for words in LEAD_KEPT_OUT:
        for printed, fenced in P.commands(operator_terminal_refusal(" ".join(words))):
            if printed == "aew g3 request" and not fenced:
                # This refusal tells the Lead whom to ask. The operator's client supplies the required inputs.
                P.parse(f"{printed} --help", fenced=False)
            else:
                P.check(printed, "fence" if fenced else "span")


def test_each_capability_change_names_a_capability_command() -> None:
    """Blind spot 1 again (``capability_commands``' ``aew capability {command}``): every change kind the module sends
    names a real `aew capability` command once rendered."""
    source = (P.SRC / "cli" / "capability_commands.py").read_text(encoding="utf-8")
    kinds = [n.args[1].value for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Call)
             and getattr(n.func, "id", None) == "_change" and isinstance(n.args[1], ast.Constant)]
    assert len(kinds) >= 4
    for kind in kinds:
        P.check(f"aew capability {kind.replace('_', '-')}", "span")


def test_the_worker_map_reads_line_names_real_commands() -> None:
    """Blind spot 1 again (the worker preamble's map-reads line, ``aew {op}`` from ``bridge.MAP_OPERATIONS``; register
    F15.8): every command the line renders is a real `aew` command."""
    from aew.harness.bridge import MAP_OPERATIONS

    line = K.preamble(K.LaunchContract(
        run="R-1", invocation="INV-1", work_unit="T-1", role="investigator", scope="observation", card=None,
        execution_profile={}, workspace="w", expected_kinds=[], operations=sorted(MAP_OPERATIONS), pack_path="p",
        pack_sha256="0", pack_text="", continuation=None, run_dir="r")).splitlines()[-1]
    printed = [text for text, _ in P.commands(line)]
    assert printed == [f"aew {op.replace('.', ' ')}" for op in MAP_OPERATIONS]
    for text in printed:
        P.check(text, "span")


@pytest.mark.parametrize(("role", "unit"), [("reviewer", {"kind": "ticket"}), ("verifier", {"kind": "ticket"}),
                                            ("investigator", {"kind": "ticket", "mutating": False})])
def test_a_finished_runs_ingest_command_parses(role: str, unit: dict[str, object]) -> None:
    """Blind spot 1 whole (``harness_ops._after_run``'s `{command} {wid} ...`): a span that opens with a value is not
    seen at all, so the ingest step a finished run names is rendered for each role that has one."""
    from aew.engine.harness_ops import Harness

    state = {"work": {"T-0007": unit}}
    produced = [{"id": "EV-0003", "kind": "review" if role == "reviewer" else "verification"}]
    harness = Harness.__new__(Harness)
    harness.gates = SimpleNamespace(stage_for=lambda state, wid, frm, dst: None)  # type: ignore[assignment]
    message = harness._after_run(state, {"work_unit": "T-0007", "role": role}, produced, "INV-0003")
    [(printed, fenced)] = P.commands(message)
    [args] = P.parse(printed, fenced=fenced)
    assert (args.work_id, args.evidence) == ("T-0007", "EV-0003")


@pytest.mark.parametrize("state", transitions.STATES)
def test_each_next_step_a_refusal_names_parses(state: str) -> None:
    """Blind spot 2, text joined at run time (``transitions.next_steps`` formats commands from a table and joins
    them): every state's next steps, rendered, parse as commands."""
    for printed, fenced in P.commands(transitions.next_steps(state, "T-0007")):
        assert all(isinstance(ns, argparse.Namespace) for ns in P.parse(printed, fenced=fenced))


@pytest.mark.parametrize("post_verify", [False, True])
def test_every_command_the_rendered_guide_prints_passes(post_verify: bool) -> None:
    """Blind spot 2 at its largest: the guide joins its moves from the transition table at run time. Rendered for the
    default policy (and with a post-integration verifier), every command it prints, in its core or a section `aew guide`
    prints (E231), passes the check."""
    from aew.surface import lead_text

    gates = {**DEFAULT_GATES, "post_integration": {**(DEFAULT_GATES.get("post_integration") or {}),
                                                   "verification": post_verify}}
    printed = P.commands(lead_text.document(gates, DEFAULT_CHECKS).full())
    assert len(printed) > 30  # a floor on the finder: E130's guide prints each command once, not per move
    # The guide names these commands in its explanations. Its runnable examples are checked below.
    references = {
        "aew authority accept", "aew authority reject", "aew lead acquire", "aew lead takeover",
        "aew lead release", "aew evidence ingest", "aew work transition",
    }
    for command, fenced in printed:
        if not fenced and command in references:
            P.parse(f"{command} --help", fenced=False)
        else:
            P.check(command, "fence" if fenced else "span")


def test_a_slot_is_filled_as_one_word() -> None:
    """Blind spot 3: a slot that renders several words is filled as one, so a value that changes the command's shape
    is not seen. Probed on a planted case: the template parses, the rendered text does not."""
    template = "aew work show \x010\x02"
    assert P.parse(template, fenced=False, exprs=("ids",))
    with pytest.raises(P.PrintedCommandError):
        P.parse("aew work show T-1 T-2", fenced=False)


def test_migrate_is_a_complete_command_without_caller_arguments() -> None:
    [site] = [s for s in P.ast_sites() if s.path == "src/aew/engine/history_ops.py" and s.text == "aew migrate"]
    assert _why_not(site) is None
