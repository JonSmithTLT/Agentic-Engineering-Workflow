"""D2's rules, each proved differentially: an input that violates the rule is caught and a clean one passes, with the
inputs read from the product (the live ``aew`` parser, ``contract.TOOLS``, ``CREDENTIAL_ENV``, ``agentenv``) rather
than from hand lists (docs/implementation/vertical-uat.md §8)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import unicodedata

import pytest
from discovery import allowed, capture, modes, rules, static
from discovery.rules import MODEL, OPERATOR, Output, Suggestion


def prose(*commands: str) -> Output:
    return Output(site="unit", text=" ".join(f"`{c}`" for c in commands))


def found(output: Output, rule: str) -> list[str]:
    return [f.detail for f in rules.check(output) if f.rule == rule]


def command_paths() -> list[tuple[str, ...]]:
    """Every command path of the live parser, with each parser's own actions."""
    out = []

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        out.append(path)
        for sub in subs:
            for name, child in sub.choices.items():
                walk(child, (*path, name))

    walk(rules._parser(), ())
    return out


def parser_at(path: tuple[str, ...]) -> argparse.ArgumentParser:
    current = rules._parser()
    for word in path:
        sub = next(a for a in current._actions if isinstance(a, argparse._SubParsersAction))
        current = sub.choices[word]
    return current


# ---------------------------------------------------------------------------------------------- O-CMD

def test_o_cmd_flags_a_command_the_parser_lacks_and_passes_every_command_it_has():
    """U10's shape: a command nobody built. Every real command path, named in prose, parses (no false positive)."""
    assert found(prose("aew harness runs"), "O-CMD")
    paths = [p for p in command_paths() if p]
    assert len(paths) > 50
    for path in paths:
        assert rules.o_cmd(Suggestion(path, "aew " + " ".join(path), structured=False)) is None, path


def test_o_cmd_takes_placeholders_as_values_and_checks_every_alternative():
    assert not found(prose("aew work reclassify <T> --class <0-4> --reason ..."), "O-CMD")
    assert not found(prose("aew history list|show|links"), "O-CMD")
    assert found(prose("aew history list|shwo"), "O-CMD")  # one alternative does not exist
    assert found(prose("aew work transition <T> --tto RUNNING"), "O-CMD")  # an option the command lacks


def test_alternatives_between_options_split_whole_option_groups():
    """The product's own plan hint offers `--assurance none` or `--review <card>` or `--verify <card>` across spaces:
    each group is one alternative, and each must parse. A group naming an option the command lacks is caught."""
    hint = "aew plan propose T-0001 --file - --assurance none|--review <card>|--verify <card> --expect-rev N"
    assert not found(prose(hint), "O-CMD")
    assert found(prose(hint.replace("--verify <card>", "--verfy <card>")), "O-CMD")
    assert not found(prose("aew harness config opencode <INV>|--lead"), "O-CMD")


def test_the_hint_the_engine_writes_for_a_plan_parses():
    """Read from the product: the resume hint that names the plan's assurance alternatives."""
    from pathlib import Path

    source = (Path(rules.__file__).resolve().parents[3] / "src" / "aew" / "engine" / "resume_ops.py").read_text(
        encoding="utf-8")
    assert "--assurance none|--review <card>|--verify <card>" in source
    assert not found(prose("aew plan propose T-0001 --file - --assurance none|--review <card>|--verify <card> "
                           "--expect-rev N"), "O-CMD")


def test_a_refusal_saying_what_a_command_would_put_on_stdout_asks_for_nothing():
    from aew.harness import lead_broker

    assert "would put a Lead credential" in _source_of(lead_broker.__file__)
    told = "`aew dashboard open` would put a Lead credential, offer secret or dashboard session URL on stdout"
    assert not found(Output(site="unit", text=told), "O-SECRET")
    assert found(Output(site="unit", text="copy the credential into AEW_LEAD_TOKEN"), "O-SECRET")


def _source_of(path: str) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8")


def test_a_structured_field_must_parse_whole_while_prose_may_name_a_command():
    mention = prose("aew work show")
    field = Output(site="unit", payload={"cli": ["work", "show"]})
    whole = Output(site="unit", payload={"cli": ["work", "show", "T-0001"]})
    assert not found(mention, "O-CMD")
    assert found(field, "O-CMD")
    assert not found(whole, "O-CMD")


def test_o_cmd_checks_typed_tool_names_against_the_contract():
    from aew.surface.contract import TOOLS

    for name in TOOLS:
        assert not found(prose(f"aew lead tool {name}"), "O-CMD"), name
        assert not found(Output(site="unit", payload={"decisions": [{"tool": name}]}), "O-CMD"), name
    assert found(prose("aew lead tool integration_publsh"), "O-CMD")
    assert found(Output(site="unit", payload={"decisions": [{"tool": "integration_publsh"}]}), "O-CMD")


def test_text_that_echoes_the_input_inside_a_refusal_is_not_judged():
    message = "unknown command: `aew harness runs`"
    echoed = Output(site="unit", refusal={"code": "USAGE", "message": message}, echo=("harness", "runs"))
    suggested = Output(site="unit", refusal={"code": "USAGE", "message": message}, echo=("status",))
    assert not found(echoed, "O-CMD")
    assert found(suggested, "O-CMD")


# ---------------------------------------------------------------------------------------------- O-IDS

def id_typed_options() -> list[tuple[tuple[str, ...], str]]:
    """``(command path, option)`` for every id-typed option of the live parser."""
    out = []
    for path in command_paths():
        for action in parser_at(path)._actions:
            if rules.is_id_action(action) and action.option_strings:
                out.append((path, action.option_strings[-1]))
    return out


def test_o_ids_flags_every_id_typed_option_of_the_live_parser():
    options = id_typed_options()
    assert any(opt == "--expect-rev" for _, opt in options) and len(options) > 40
    for path, option in options:
        s = Suggestion((*path, option, "N"), "", structured=False)
        assert rules.o_ids(s), (path, option)
        bare = Suggestion(path, "", structured=False)
        assert not rules.o_ids(bare), path


def test_o_ids_decides_placeholders_by_position():
    """U31's shape (a run id the reader must find) and U1's (a candidate id), against the exempt slots: a Ticket, a
    slot whose values the text lists, and free text."""
    assert found(prose("aew harness wait <run>"), "O-IDS")
    assert found(prose("aew authority accept C-001 --class decisions"), "O-IDS")
    assert found(prose("aew review ingest T-0001 --evidence <id>"), "O-IDS")
    assert not found(prose("aew work show <T>"), "O-IDS")
    assert not found(prose("aew work reclassify T-0001 --class <0-4> --reason ..."), "O-IDS")
    assert not found(prose("aew harness status"), "O-IDS")


def test_o_ids_knows_the_engines_id_formats():
    from aew.coordination.layout import INVOCATION_RE
    from aew.harness.contract import run_id

    inv = "INV-0007"
    assert INVOCATION_RE.match(inv)
    assert found(prose(f"aew context show {inv}"), "O-IDS")
    assert found(prose(f"aew harness wait {run_id(inv, 2)}"), "O-IDS")
    assert not found(prose("aew work show T-0007"), "O-IDS")


def test_o_ids_finds_an_engine_id_in_a_slot_that_is_not_id_typed():
    """Review of #218, m3: the id-format path alone. `history show` takes a record id, which is not an id-typed
    argument, so only the engine's id formats can see the invocation id in it (a mutant `_is_id` fails here)."""
    assert not any(rules.is_id_action(a) for a in rules._path_actions(("history", "show"))["record_id"])
    assert found(prose("aew history show INV-0101"), "O-IDS")
    assert not found(prose("aew history show T-0101"), "O-IDS")


def test_id_typed_arguments_are_read_from_the_parser_per_command():
    """Review of #218, m3: an argument is id-typed by its own name, option or metavar, per command: `history log
    --since REVISION` takes a revision, `history list --since UTC` a time."""
    assert found(prose("aew history log --since 12"), "O-IDS")
    assert not found(prose("aew history list --since 2026-10-01T00:00:00Z"), "O-IDS")
    assert found(prose("aew harness send R-INV-0001-1 --file nudge.md"), "O-IDS")
    assert not any(rules.is_id_action(a) for a in rules._actions() if a.dest.endswith("token"))


def test_a_structured_field_names_a_command_that_must_parse_whole():
    """Review of #218, m4: `next`, `remedy` and the hints are offered to be run as given (§2.2)."""
    assert found(Output(site="unit", payload={"next": "aew plan accept T-0001"}), "O-CMD")
    assert found(Output(site="unit", payload={"remedy": "aew harness launch"}), "O-CMD")
    assert not found(Output(site="unit", payload={"next": "aew work show T-0001"}), "O-CMD")
    assert not found(Output(site="unit", text="`aew plan accept`, once the plan is ready"), "O-CMD")  # prose


def test_o_ids_reads_structured_suggestions():
    assert found(Output(site="unit", payload={"next": "acquire Lead authority: aew lead acquire --expect-rev 0"}),
                 "O-IDS")
    assert not found(Output(site="unit", payload={"next": "acquire Lead authority: aew lead acquire"}), "O-IDS")
    # A field that is not a suggestion is shown, not suggested: an id in it is allowed.
    assert not found(Output(site="unit", payload={"run": "R-INV-1-1", "detail": "aew lead acquire --expect-rev 0"}),
                     "O-IDS")


# ---------------------------------------------------------------------------------------------- O-WORDS and O-CODE

def test_o_words_reports_a_refusal_without_the_refusal_schema():
    bare = Output(site="unit", refusal={"code": "USAGE", "message": "no"})
    schema = Output(site="unit", refusal={"code": "USAGE", "message": "no", "details": {
        "cause": "input_malformed", "remedy": {"command": ["status"]}, "owner": "lead"}})
    assert found(bare, "O-WORDS") == ["unstructured refusal"]
    assert not found(schema, "O-WORDS")


def test_o_code_judges_only_a_known_cause_against_the_registry():
    from discovery import registry
    from test_discovery_registry import page

    reg = registry.load(page())
    seat = Output(site="unit", refusal={"code": "PERMISSION_DENIED", "message": "seat held"},
                  injected_cause="seat_held")
    denied = Output(site="unit", refusal={"code": "PERMISSION_DENIED", "message": "no"},
                    injected_cause="authority_denied")
    unknown = Output(site="unit", refusal={"code": "PERMISSION_DENIED", "message": "seat held"})
    assert [f.rule for f in rules.check(seat, reg)].count("O-CODE") == 1  # U5's shape
    assert "O-CODE" not in [f.rule for f in rules.check(denied, reg)]
    assert "O-CODE" not in [f.rule for f in rules.check(unknown, reg)]  # H5: no cause known, nothing judged
    stated = Output(site="unit", refusal={"code": "USAGE", "message": "x", "details": {
        "cause": "authority_denied", "remedy": {}, "owner": "lead"}})
    assert "O-CODE" in [f.rule for f in rules.check(stated, reg)]


# ---------------------------------------------------------------------------------------------- O-SECRET

def test_o_secret_flags_every_credential_the_product_names_when_asked_for():
    from aew.harness.contract import CREDENTIAL_ENV

    names = [n for n in CREDENTIAL_ENV if n.endswith(("_TOKEN", "_KEY"))]
    assert "AEW_LEAD_TOKEN" in names
    for name in names:
        assert found(Output(site="unit", text=f"Set {name} in your own shell."), "O-SECRET"), name
        assert not found(Output(site="unit", text=f"{name} never reaches a harness."), "O-SECRET"), name
    assert found(prose("aew manifest adopt --token <credential>"), "O-SECRET")
    assert not found(prose("aew manifest adopt"), "O-SECRET")


@pytest.mark.parametrize("plane", [OPERATOR, MODEL])
def test_o_secret_flags_a_credential_asked_of_any_reader(plane):
    """The operator's decision of 2026-10-12 widens O-SECRET to any reader: the operator, the Lead, or a worker model
    through its pack. The line packs carried until they stopped speaking of the credential is the planted case, and
    no pack the product renders asks now."""
    line = "Set `AEW_INVOCATION_TOKEN=<credential>` for every `aew` command below."
    assert found(Output(site="unit", plane=plane, text=line), "O-SECRET") == ["asks to set AEW_INVOCATION_TOKEN"]
    packs = [text for source, _, text in static.texts(guides()) if source.startswith("pack:")]
    assert packs and not [problem for text in packs for problem in rules.o_secret(text, plane)]
    assert found(Output(site="unit", plane=plane, text="Ask the operator to set AEW_LEAD_TOKEN."), "O-SECRET")
    assert not found(Output(site="unit", plane=plane, text="This session never holds AEW_LEAD_TOKEN."), "O-SECRET")


# The designer's decision of 2026-11-01 (CS-4 addendum 12): each line asks to set the credential, so only the snippet
# decides. The near misses each break one of the exemption's five conditions.
ASK = "Set AEW_LEAD_TOKEN for this session: "
HIDDEN_BASH = "read -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo; export AEW_LEAD_TOKEN"
NEAR_MISSES = {
    "a literal value": "export AEW_LEAD_TOKEN=literal-value",
    "read without -s": "read -rp 'Lead token: ' AEW_LEAD_TOKEN; echo; export AEW_LEAD_TOKEN",
    "Read-Host unmasked": '$env:AEW_LEAD_TOKEN = Read-Host "Lead token"',
    "an append to a startup file": f"{HIDDEN_BASH}; declare -p AEW_LEAD_TOKEN >> ~/.bashrc",
    "an echo of the value": f'{HIDDEN_BASH}; echo "$AEW_LEAD_TOKEN"',
    "an inline --token value": f"{HIDDEN_BASH}; aew checkpoint --token literal-value",
    "a persistent variable": "[Environment]::SetEnvironmentVariable('AEW_LEAD_TOKEN', "
                             "(Read-Host 'Lead token' -AsSecureString), 'User')",
    # Review of #316, m2: the hidden read must set the credential itself, and every printer counts.
    "a hidden read of another name, the value unmasked": '$x = Read-Host "pin" -MaskInput; '
                                                         '$env:AEW_LEAD_TOKEN = Read-Host "Lead token"',
    "a hidden read of another name, the value from a file": "read -rs junk; "
                                                            "export AEW_LEAD_TOKEN=$(cat ~/lead-token.txt)",
    "a SecureString of another variable": '$s = Read-Host "pin" -AsSecureString; $env:AEW_LEAD_TOKEN = '
                                          "[Runtime.InteropServices.Marshal]::PtrToStringBSTR("
                                          "[Runtime.InteropServices.Marshal]::SecureStringToBSTR($t))",
    "printenv": f"{HIDDEN_BASH}; printenv AEW_LEAD_TOKEN",
    "declare -p, no redirect": f"{HIDDEN_BASH}; declare -p AEW_LEAD_TOKEN",
    "a bare PowerShell expression": '$env:AEW_LEAD_TOKEN = Read-Host "Lead token" -MaskInput; $env:AEW_LEAD_TOKEN',
    "a bare bash expansion": f'{HIDDEN_BASH}; "$AEW_LEAD_TOKEN"',
    "a whole-environment dump": f"{HIDDEN_BASH}; env | sort",
    "PowerShell's env: drive": '$env:AEW_LEAD_TOKEN = Read-Host "Lead token" -MaskInput; Get-ChildItem env:',
}


def test_o_secret_passes_the_per_session_hidden_forms_and_trips_on_each_near_miss():
    """The differential test: the forms addendum 12 ships (lead_credential's, as the guides and refusals show them)
    pass, and each near miss still trips O-SECRET. Without the ask the same lines say nothing (the control)."""
    from aew import lead_credential

    for shell, form in lead_credential.SECURE_FORMS.items():
        assert found(Output(site="unit", text=ASK + form), "O-SECRET") == [], shell
        assert found(Output(site="unit", text=form), "O-SECRET") == [], shell
    assert found(Output(site="unit", text=ASK), "O-SECRET") == ["asks to set AEW_LEAD_TOKEN"]
    for miss, snippet in NEAR_MISSES.items():
        assert found(Output(site="unit", text=ASK + snippet), "O-SECRET"), miss
        assert not rules.per_session_hidden(snippet, "AEW_LEAD_TOKEN"), miss
    # One line, two asks: the hidden form for the Lead credential exempts no ask for another credential beside it.
    two = (f"Set AEW_LEAD_TOKEN with `{HIDDEN_BASH}`, then paste your AEW_INVOCATION_TOKEN too")
    assert found(Output(site="unit", text=two), "O-SECRET") == ["asks to paste AEW_INVOCATION_TOKEN"]
    for shell, form in lead_credential.forms("SYNTHETIC_API_KEY", "SYNTHETIC_API_KEY").items():  # any name's forms
        assert rules.per_session_hidden(form, "SYNTHETIC_API_KEY"), shell
        assert not rules.per_session_hidden(form, "OTHER"), shell


def test_the_static_scan_still_reports_a_guide_line_with_a_literal_token():
    """The planted control: a guide that shows the per-session forms has no O-SECRET finding; the same guide with a
    seeded literal-token line is reported, at that line's ask."""
    from aew import lead_credential

    site = "docs/guides/planted.md"
    forms = "\n".join(["```bash", *lead_credential.SECURE_FORMS.values(), "```"])

    def secrets(text: str) -> list[str]:
        return [f.key for f in static.scan({site: text}) if f.rule == "O-SECRET" and site in f.key]

    assert secrets(f"For this session only:\n{forms}\n") == []
    seeded = f"For this session only:\n{forms}\n```bash\nexport AEW_LEAD_TOKEN=literal-value\n```\n"
    assert secrets(seeded) == [f"O-SECRET {static.STATIC}{site}|asks to export AEW_LEAD_TOKEN"]


def test_the_identity_check_aborts_on_another_checkouts_aew(tmp_path):
    """Spec §5, J2 (review of #218, m7): the discovery lane judges only the commit under test."""
    from pathlib import Path

    from discovery import identity

    import aew

    root = Path(__file__).resolve().parents[2]
    pyproject = root / "pyproject.toml"
    assert identity.problems(aew.__file__, aew.__version__, root / "src", pyproject) == []
    other = tmp_path / "other" / "src" / "aew" / "__init__.py"
    assert "not from the commit under test" in identity.problems(str(other), aew.__version__, root / "src",
                                                                 pyproject)[0]
    assert "declares" in identity.problems(aew.__file__, "0.0.0-other", root / "src", pyproject)[0]


def test_o_secret_places_pins_at_the_console_and_codes_at_the_terminal():
    pin = "Enter your PIN to continue."
    code = "Type the one-time code shown on the console."
    assert found(Output(site="unit", plane=OPERATOR, text=pin), "O-SECRET")
    assert not found(Output(site="unit", plane=rules.CONSOLE, text=pin), "O-SECRET")
    assert found(Output(site="unit", plane=MODEL, text=code), "O-SECRET")
    assert not found(Output(site="unit", plane=OPERATOR, text=code), "O-SECRET")


def test_o_secret_reads_the_typed_tools_arguments(monkeypatch):
    from aew.surface import contract

    assert not rules.tool_argument_secrets()
    status = contract.TOOLS["status"]
    schema = {**status.input_schema, "properties": {**status.input_schema.get("properties", {}), "pin": {}}}
    monkeypatch.setitem(contract.TOOLS, "status", status._replace(input_schema=schema))
    assert [f.site for f in rules.tool_argument_secrets()] == ["tool-arguments:status"]


# ---------------------------------------------------------------------------------------------- O-ENV

def test_o_env_is_generated_from_the_check_path_itself():
    """Review of #218, m5: the statement comes from `Validation._check_env`, the environment every validation check
    runs in: the allowlist, PATH, PYTHONUTF8 and (on POSIX) the locale family, and no other variable."""
    import sys

    from aew.harness import agentenv

    kept, passes_others = rules.check_environment()
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    assert set(keep) | {"PATH", "PYTHONUTF8"} <= set(kept)
    assert ("LC_*" in kept) == (sys.platform != "win32")
    assert not passes_others  # the code has no way to give a check another variable
    parts = rules.env_statement()
    assert "provider_env" not in parts and rules.NO_OTHER in parts


def test_o_env_requires_the_statement_generated_from_the_check_path():
    kept, _ = rules.check_environment()

    def statement(names: list[str]) -> str:
        return (f"{rules.ENV_MARK}: only {', '.join(names)} are kept. {rules.NO_OTHER}: put what a check needs "
                "in its command.")

    assert rules.o_env(statement(kept)) == []
    dropped = next(k for k in kept if k != "PATH")
    assert rules.o_env(statement([k for k in kept if k != dropped])) == [dropped]
    assert rules.o_env(statement(kept).replace(rules.NO_OTHER, "")) == [f"the statement {rules.NO_OTHER!r}"]
    assert f"the statement {rules.ENV_MARK!r}" in rules.o_env("nothing about checks")


def test_o_env_follows_the_check_path_when_it_changes(monkeypatch):
    """A mutant check path that also passed every variable through would need no "no other variable" statement, and
    one that dropped PYTHONUTF8 would not require it: the expectation moves with the code."""
    import os

    from aew.engine.validation_ops import Validation

    monkeypatch.setattr(Validation, "_check_env", staticmethod(lambda layout: {**os.environ}))
    kept, passes_others = rules.check_environment()
    assert passes_others and rules.NO_OTHER not in rules.env_statement()


def guides() -> dict[str, str]:
    from pathlib import Path

    return static.read_guides(Path(__file__).resolve().parents[2] / "docs" / "guides", "docs/guides")


def test_the_static_scan_reads_every_static_text():
    sources = [source for source, _, _ in static.texts(guides())]
    from aew.harness.opencode.projection import LEAD_COMMANDS
    from aew.knowledge.context import OUTPUT_TEMPLATES

    assert "lead-system" in sources and "guide" in sources
    assert {f"lead-command:{n}" for n in LEAD_COMMANDS} <= set(sources)
    assert {f"pack:{r}" for r in OUTPUT_TEMPLATES} <= set(sources)
    assert "docs/guides/quickstart.md" in sources
    assert all(f.site.startswith(allowed.STATIC_PREFIXES) for f in static.scan(guides()))


# ---------------------------------------------------------------------------------------------- capture

def test_the_capture_plugin_reads_a_real_refusal_of_the_cli(repo):
    """A real refusal, from the product itself: `aew lead session` without a credential gives the sanctioned way to give
    it, the hidden-prompt forms, so O-WORDS reads it and O-SECRET does not (U29's witness until that rule was fixed).
    A clean answer of the same command family raises neither rule."""
    from aewflow import allow_weaker_lead
    from conftest import Project, run_aew

    assert run_aew("init", cwd=repo).returncode == 0
    allow_weaker_lead(Project(repo))  # the credential's refusal, not `required`'s (G3 addendum 7)
    argv = ["-C", str(repo), "lead", "session", "--", "true"]
    res = run_aew(*argv)
    outputs = capture.cli_outputs(argv, res.stdout, res.stderr)
    assert [o.site for o in outputs] == ["cli:aew lead session|USAGE"]
    refusal = outputs[0].refusal
    assert refusal is not None and "AEW_LEAD_TOKEN" in refusal["message"] and "read -rsp" in refusal["message"]
    judged = {f.rule for f in rules.check(outputs[0])}
    assert "O-WORDS" in judged and "O-SECRET" not in judged
    assert str(repo) not in outputs[0].site  # a key never carries message text
    # `aew opencode` without a credential refuses before anything starts. Run through `run_aew`, so
    # the session's capture sees this site in every run (tests start a live `aew opencode` through Popen, unseen).
    # A stand-in OpenCode that reports a tested version, so the version check passes wherever OpenCode is absent.
    from aew.harness.opencode import capabilities

    binary = repo.parent / "opencode.py"
    binary.write_text(f"print({capabilities.TESTED_VERSIONS[0]!r})\n", encoding="utf-8")
    opened = run_aew("-C", str(repo), "opencode", env={"AEW_OPENCODE_BIN": str(binary)})
    refusal = capture.cli_outputs(["-C", str(repo), "opencode"], opened.stdout, opened.stderr)
    assert [o.site for o in refusal] == ["cli:aew opencode|USAGE"]
    assert not [f.detail for f in rules.check(refusal[0]) if f.rule == "O-SECRET"]
    shown = run_aew("-C", str(repo), "lead", "show")
    clean = capture.cli_outputs(["-C", str(repo), "lead", "show"], shown.stdout, shown.stderr)
    assert [o.site for o in clean] == ["cli:aew lead show|result"]
    assert not {"O-WORDS", "O-SECRET"} & {f.rule for f in rules.check(clean[0])}


def test_the_capture_plugin_keys_typed_tool_results_by_tool_and_code():
    ok = capture.tool_output("status", {}, {"ok": True, "stopped": None, "projection": {}})
    refused = capture.tool_output("integration_publish", {"work_id": "T-1"},
                                  {"ok": False, "stopped": {"error": {"code": "GATE_UNSATISFIED", "message": "m"}}})
    assert ok.site == "tool:status|result" and ok.refusal is None and ok.plane == MODEL
    assert refused.site == "tool:integration_publish|GATE_UNSATISFIED"
    assert refused.refusal is not None and refused.refusal["code"] == "GATE_UNSATISFIED"


def _boom(*_a, **_k):
    raise RuntimeError("defect")


def test_the_capture_plugin_never_changes_a_test_outcome():
    """A defect in judging is counted and reported; it never raises into the test that produced the output. The
    defect is injected into this recorder alone, never into the session's own capture (review of #218, m2)."""
    recorder = capture.Recorder(judge=_boom)
    recorder.record(Output(site="x", text="`aew status`"))
    assert recorder.errors == {"RuntimeError: defect": 1} and not recorder.findings
    clean = capture.Recorder()
    clean.record(Output(site="x", text="`aew harness runs`"))
    assert "O-CMD x" in clean.findings and not clean.errors


def test_a_defect_in_a_hook_never_reaches_the_test_that_called_the_product(monkeypatch, capsys):
    """Every hook the plugin installs (the CLI entry, the typed surface, subprocess) answers what the product answered
    when building the output to judge fails: the defect is counted instead."""
    import aew.cli.main as cli_main
    import aew.surface.run as surface_run

    answer = {"ok": True, "stopped": None}
    monkeypatch.setattr(surface_run, "run_tool", lambda *a, **k: answer)
    originals = (subprocess.run, cli_main._main, surface_run.run_tool)
    plugin = capture.CapturePlugin(None, None)  # type: ignore[arg-type]
    plugin.install()
    try:
        assert cli_main._main([]) == 2  # no command: the help, exit status 2
        assert surface_run.run_tool(None, None, "status", {}) is answer
        assert not plugin.recorder.errors
        # Injected into this plugin's own builders only: the session's capture of this test stays clean (m2).
        plugin.cli_outputs = plugin.tool_output = _boom
        assert cli_main._main([]) == 2
        assert surface_run.run_tool(None, None, "status", {}) is answer
        proc = subprocess.run([sys.executable, "-m", "aew", "--version"], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL,
                              creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        assert proc.returncode == 0 and proc.stdout.startswith("aew ")
    finally:
        plugin.uninstall()
    assert plugin.recorder.errors == {"RuntimeError: defect": 3}
    assert (subprocess.run, cli_main._main, surface_run.run_tool) == originals  # uninstalled as found
    capsys.readouterr()


def test_a_failed_findings_write_never_changes_the_sessions_outcome(tmp_path, capsys):
    """Review of #218, m1: the findings file cannot be written (its directory is a file); the session's exit status
    is untouched and the failure is reported on stderr."""
    blocker = tmp_path / "afile"
    blocker.write_text("", encoding="utf-8")

    class Config:
        def getoption(self, name, default=None):
            return default

    plugin = capture.CapturePlugin(Config(), blocker / "sub" / "out.json")  # type: ignore[arg-type]
    plugin.install()
    session = type("S", (), {"exitstatus": 0})()
    plugin.pytest_sessionfinish(session, 0)  # type: ignore[arg-type]
    assert session.exitstatus == 0
    assert "D2 capture: findings not written" in capsys.readouterr().err


def _lock_checked(recorder: capture.Recorder) -> None:
    """Make every read and write of the recorder's shared state assert that its lock is held (no timing involved)."""

    def guard(name):
        def method(self, *a, **k):
            assert recorder._lock.locked(), f"{type(self).__name__}.{name} without the recorder's lock"
            return getattr(super(type(self), self), name)(*a, **k)
        return method

    names = ("__setitem__", "__getitem__", "__contains__", "__iter__", "__len__", "get", "setdefault", "items",
             "keys", "values", "copy")
    checked_dict = type("CheckedDict", (dict,), {n: guard(n) for n in names})
    checked_set = type("CheckedSet", (set,), {n: guard(n) for n in ("add", "__contains__", "__iter__", "__len__")})
    recorder.findings, recorder.errors, recorder._judged = checked_dict(), checked_dict(), checked_set()


def test_the_recorder_touches_its_state_only_under_its_lock():
    """Review of #218, m1 and the re-review's §4: product threads that outlive a test may record while the session
    snapshots, so every read and write of the recorder's dicts holds its lock. Deterministic: each access asserts
    the lock is held, so taking any `with self._lock` away fails here at once."""
    recorder = capture.Recorder(judge=lambda output: [rules.Finding("O-WORDS", output.site, "x")])
    _lock_checked(recorder)
    recorder.record(Output(site="a"))
    recorder.record(Output(site="a"))  # the dedupe read
    recorder.error(RuntimeError("e"))
    recorder.merge({"outputs": 1, "findings": {"O-WORDS b": {"rule": "O-WORDS", "site": "b", "count": 2}},
                    "errors": {"RuntimeError: f": 1}})
    snapshot = recorder.as_dict()
    assert snapshot["outputs"] == 3 and set(snapshot["findings"]) == {"O-WORDS a", "O-WORDS b"}
    assert snapshot["errors"] == {"RuntimeError: e": 1, "RuntimeError: f": 1}
    with pytest.raises(AssertionError, match="without the recorder's lock"):
        recorder.findings.get("O-WORDS a")  # the guard itself: an unlocked read is caught


def test_a_capture_run_writes_its_findings_beside_the_lane_report(tmp_path):
    """The plugin end to end, in a pytest session of its own (the suite's conftest loaded as a plugin): a test that
    runs `aew` produces a findings file beside its lane report, keyed by command words, and still passes."""
    import os
    from pathlib import Path

    tests = Path(__file__).resolve().parents[1]
    probe = tmp_path / "tests" / "unit" / "test_probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("import os, subprocess, sys\n\n\n"
                     "def test_probe():\n"
                     "    flags = 0x08000000 if sys.platform == 'win32' else 0  # CREATE_NO_WINDOW\n"
                     "    here = os.path.dirname(os.path.abspath(__file__))\n"
                     "    p = subprocess.run([sys.executable, '-m', 'aew', '-C', here, 'status'],\n"
                     "                       capture_output=True, text=True, stdin=subprocess.DEVNULL,\n"
                     "                       creationflags=flags)\n"
                     "    assert p.returncode != 0\n", encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    report = tmp_path / "out" / "probe.json"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(tests), os.environ.get("PYTHONPATH", "")])}
    env.pop("PYTEST_ADDOPTS", None)
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                           "-p", "conftest", "--rootdir", str(tmp_path), "-c", str(tmp_path / "pytest.ini"),
                           "--lane-report", str(report), str(probe)], cwd=tmp_path, env=env, capture_output=True,
                          text=True, timeout=300, stdin=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    data = json.loads(capture.out_path_for(report).read_text(encoding="utf-8"))
    assert data["schema"] == capture.SCHEMA and data["outputs"] >= 1 and not data["errors"]
    assert "O-WORDS cli:aew status|PROJECT_NOT_FOUND" in data["findings"], data["findings"]


# ---------------------------------------------------------------------------------------------- the ratchet

def test_a_pull_request_fails_only_on_new_keys_of_enforced_rules():
    shadowed = {r: modes.SHADOW for r in modes.RULES}
    enforced = {**shadowed, "O-IDS": modes.ENFORCE}
    listed = {"O-IDS cli:aew status|result"}
    observed = {"O-IDS cli:aew status|result", "O-IDS cli:aew harness wait|result", "O-WORDS cli:aew x|USAGE"}
    assert allowed.decide(observed, listed, stale_scope=None, mode_of=shadowed).ok
    v = allowed.decide(observed, listed, stale_scope=None, mode_of=enforced)
    assert v.failing == ["O-IDS cli:aew harness wait|result"]  # the new O-WORDS key is reported, not failing
    assert v.new == sorted(observed - listed)
    assert allowed.decide(listed, listed, stale_scope=None, mode_of=enforced).ok


def test_a_run_complete_for_a_key_fails_on_it_stale_and_an_incomplete_run_never_does():
    enforced = {r: modes.ENFORCE for r in modes.RULES}
    listed = {"O-IDS cli:aew status|result", "O-IDS static:guide|aew x"}
    assert allowed.decide(set(), listed, stale_scope=None, mode_of=enforced).ok
    v = allowed.decide(set(), listed, stale_scope="runtime", mode_of=enforced)
    assert v.stale == ["O-IDS cli:aew status|result"] and not v.ok  # the static key is the discovery lane's
    assert allowed.decide(set(), listed, stale_scope="static", mode_of=enforced).stale == ["O-IDS static:guide|aew x"]


def _ratchet():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "tools" / "ci" / "discovery_ratchet.py"
    spec = importlib.util.spec_from_file_location("discovery_ratchet", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _growth(tmp_path, monkeypatch, labels):
    """The ratchet on a pull request whose allow-list adds ``O-CMD cli:aew x|result`` with a residual entry the pull
    request wrote itself; ``labels`` are what the live label read returns."""
    discovery_ratchet = _ratchet()
    monkeypatch.setattr(discovery_ratchet, "live_labels", lambda repo, pr: labels)
    base, head = tmp_path / "base.yaml", tmp_path / "head.yaml"
    base.write_text(allowed.render({"O-IDS cli:aew status|result"}), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    residual = [{"rule": "O-CMD", "site": "cli:aew x|result", "decision": "operator, 2026-10-12", "reason": "r"}]
    head.write_text(allowed.render({"O-IDS cli:aew status|result", "O-CMD cli:aew x|result"}, residual),
                    encoding="utf-8")
    return discovery_ratchet.main([str(reports), "--event", "pull_request", "--allowlist", str(head),
                                   "--base-allowlist", str(base), "--repo", "o/r", "--pr", "1"])


def test_the_allow_list_may_only_shrink(tmp_path, monkeypatch):
    discovery_ratchet = _ratchet()
    monkeypatch.setattr(discovery_ratchet, "live_labels", lambda repo, pr: [])
    base, head = tmp_path / "base.yaml", tmp_path / "head.yaml"
    base.write_text(allowed.render({"O-IDS cli:aew status|result"}), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    args = [str(reports), "--event", "pull_request", "--allowlist", str(head), "--base-allowlist", str(base)]
    head.write_text(allowed.render(set()), encoding="utf-8")
    assert discovery_ratchet.main(args) == 0  # shrinking is always allowed
    head.write_text(allowed.render({"O-IDS cli:aew status|result", "O-CMD cli:aew x|result"}), encoding="utf-8")
    assert discovery_ratchet.main(args) == 1  # growth fails whatever the mode
    no_base = [str(reports), "--event", "pull_request", "--allowlist", str(head)]
    assert discovery_ratchet.main(no_base) == 0  # introducing D2: the base has no list


@pytest.mark.parametrize("labels", [[], ["full-ci"], None])
def test_a_residual_the_pull_request_writes_itself_is_still_growth(tmp_path, monkeypatch, capsys, labels):
    """Review of #218, M1: an accepted residual is the operator's (spec §5). Without the operator-merge label (or
    when the labels cannot be read) a residual new against the base fails, naming the key."""
    assert _growth(tmp_path, monkeypatch, labels) == 1
    assert "FAIL residual O-CMD cli:aew x|result" in capsys.readouterr().out


def test_a_residual_passes_on_a_pull_request_the_operator_merges(tmp_path, monkeypatch, capsys):
    """The operator-merge label reserves the merge for the operator (AGENTS.md §5): the merge is the sign-off."""
    assert _growth(tmp_path, monkeypatch, ["operator-merge"]) == 0
    assert "accepted residual O-CMD cli:aew x|result" in capsys.readouterr().out


def _reports(tmp_path, *, findings: object = None, lane_report: bool = True):
    """A reports directory holding one lane report and, unless ``findings`` is ``False``, its findings file
    (``findings`` given as text is written as is)."""
    reports = tmp_path / "reports" / "lane-report-Linux-core"
    reports.mkdir(parents=True)
    report = reports / "Linux-fast.json"
    if lane_report:
        report.write_text(json.dumps({"schema": "aew/lane-report/v1", "collected": []}), encoding="utf-8")
    if findings is not False:
        body = findings if isinstance(findings, str) else json.dumps(
            {"schema": capture.SCHEMA, "outputs": 1, "findings": {}, "errors": {}})
        allowed.findings_path_for(report).write_text(body, encoding="utf-8")
    return reports.parent


@pytest.mark.parametrize(("findings", "why"), [
    (None, None),
    (False, "lane report without its findings file"),
    ("{not json", "findings file unreadable"),
    ('{"schema": "aew/something-else/v1"}', "findings file of another schema"),
])
def test_a_lanes_findings_lost_on_the_way_fail_the_ratchet(tmp_path, capsys, findings, why):
    """Review of #218, G1: every lane report is paired with its findings file, and a findings file that does not
    parse or carries another schema is a capture error, never a file to skip."""
    reports = _reports(tmp_path, findings=findings)
    for event in ("pull_request", "push"):
        code = _ratchet().main([str(reports), "--event", event, "--allowlist", str(tmp_path / "none.yaml")])
        out = capsys.readouterr().out
        assert code == (0 if why is None else 1), out
        assert why is None or why in out


def test_an_earlier_attempts_capture_error_does_not_outlive_the_re_run_that_passed(tmp_path, capsys):
    """Review of #251, F1: every attempt's lane-report artifact is downloaded, each under its own name, and only each
    shard's latest attempt counts, as in the gate's lane-report check. The latest attempt's own error still fails, and
    a superseded report's missing findings file (a job that crashed before writing it) is no longer an error."""
    reports = tmp_path / "reports"

    def attempt(n: int, errors: dict[str, int] | None) -> None:
        """Attempt ``n``'s lane report, and beside it a findings file with ``errors`` (none when ``None``)."""
        job = reports / f"lane-report-Linux-integration-6-attempt-{n}"
        job.mkdir(parents=True)
        report = job / "Linux-integration-6.json"
        report.write_text(json.dumps({"schema": "aew/lane-report/v1", "platform": "linux", "lane": "integration",
                                      "shard": "6/12", "attempt": n, "collected": []}), encoding="utf-8")
        if errors is not None:
            allowed.findings_path_for(report).write_text(json.dumps(
                {"schema": capture.SCHEMA, "outputs": 1, "findings": {}, "errors": errors}), encoding="utf-8")

    lost = {"RuntimeError: gw0 went down without its findings": 1}
    args = [str(reports), "--event", "pull_request", "--allowlist", str(tmp_path / "none.yaml")]
    attempt(1, lost)
    assert _ratchet().main(args) == 1
    attempt(2, {})
    assert _ratchet().main(args) == 0, capsys.readouterr().out
    attempt(3, lost)
    assert _ratchet().main(args) == 1
    attempt(4, None)
    assert _ratchet().main(args) == 1  # the latest attempt's lane report without its findings file
    attempt(5, {})
    assert _ratchet().main(args) == 0, capsys.readouterr().out


def test_the_ratchet_and_the_plugin_share_their_schemas():
    import lanes

    ratchet = _ratchet()
    assert ratchet.LANE_REPORT_SCHEMA == lanes.REPORT_SCHEMA and ratchet.FINDINGS_SCHEMA == capture.SCHEMA
    assert capture.out_path_for is allowed.findings_path_for


@pytest.mark.parametrize(("output", "error", "lost"), [
    ({capture.WORKER_KEY: {"outputs": 2, "findings": {"O-CMD x": {"rule": "O-CMD", "site": "x", "count": 1}},
                           "errors": {}}}, None, False),
    ({}, None, True),  # down without handing its findings on
    ({capture.WORKER_KEY: {"outputs": 1, "findings": {}, "errors": {}}}, "worker crashed", True),
    # G3a's session deadline: a worker ends with os._exit(70) before its sessionfinish, so it hands nothing on and
    # xdist reports it down with an error; that is one capture error for that worker, never silence and never two
    ({}, "worker 'gw3' crashed while running ... (exit 70)", True),
])
def test_a_worker_that_goes_down_without_its_findings_is_a_capture_error(output, error, lost):
    """Review of #218, G1: `pytest_testnodedown` merges what a worker handed on, and counts a worker that died, or
    handed nothing on, as a capture error."""
    plugin = capture.CapturePlugin(None, None)  # type: ignore[arg-type]
    node = type("Node", (), {"workeroutput": output, "gateway": type("G", (), {"id": "gw3"})()})()
    plugin.pytest_testnodedown(node, error)
    snapshot = plugin.recorder.as_dict()
    assert sum(snapshot["errors"].values()) == (1 if lost else 0)  # counted, and once per worker
    assert all("gw3 went down without its findings" in name for name in snapshot["errors"])
    if not lost:
        assert snapshot["findings"]["O-CMD x"]["count"] == 1 and snapshot["outputs"] == 2


def test_o_ids_still_reads_a_line_that_does_not_parse():
    """Review of #218, G2: O-IDS's fallbacks for a suggested line the parser refuses (here, an option it lacks): an id
    option's value, and a placeholder outside a Ticket's slot."""
    unparsed = rules.o_ids(Suggestion(("plan", "accept", "T-0001", "--revision", "3", "--expect-rev", "12",
                                       "--bogus"), "", structured=False))
    assert {"--expect-rev 12", "--revision 3"} <= set(unparsed)
    assert rules.o_ids(Suggestion(("work", "show", "<run-id>", "--bogus"), "", structured=False)) == [
        "placeholder in an unparsed line"]
    assert rules.o_ids(Suggestion(("work", "show", "<T>", "--bogus"), "", structured=False)) == []
    assert rules.o_ids(Suggestion(("work", "show", "T-0001", "--bogus", "x"), "", structured=False)) == []


def test_a_suggestion_that_is_not_a_command_line_is_an_o_cmd_finding():
    """Review of #218, G2: text the shell cannot split (an unclosed quote) is no command at all."""
    assert found(prose("aew work show 'T-0001"), "O-CMD") == ["not a command line: \"aew work show 'T-0001\""]
    assert not found(prose("aew work show 'T-0001'"), "O-CMD")


def test_the_id_formats_are_found_in_the_schema_at_any_depth():
    """Review of #218, G2: `_find_pattern` walks dicts and lists; the stage-intent pattern comes from the schema."""
    assert rules._find_pattern({"a": [{"b": {"pattern": "^SI-[0-9]+$"}}]}, "SI-") == "^SI-[0-9]+$"
    assert rules._find_pattern({"a": [{"pattern": "^OTHER$"}], "pattern": 3}, "SI-") == ""
    assert any(p.match("SI-0001") for p in rules.id_patterns())
    assert not any(p.match("T-0001") for p in rules.id_patterns())


def test_the_capture_reads_aew_by_executable_name_and_echoes_stdin():
    """Review of #218, G2: an `aew` executable is recognised by name as well as `python -m aew`, a command line that
    is not aew is ignored, and a refusal's echo includes the input it was given on stdin."""
    assert capture._aew_argv(["/usr/local/bin/aew", "status"]) == ["status"]
    assert capture._aew_argv(["C:/venv/Scripts/aew.exe", "status"]) == ["status"]
    assert capture._aew_argv([sys.executable, "-m", "aew", "status"]) == ["status"]
    assert capture._aew_argv(["git", "status"]) is None and capture._aew_argv("aew status") is None
    refusal = json.dumps({"ok": False, "error": {"code": "USAGE", "message": "`aew harness runs` is unknown"}})
    echoed = capture.cli_outputs(["lead", "tool", "x"], "", refusal, stdin="aew harness runs")
    assert echoed[0].echo[-1] == "aew harness runs"
    assert not [f for f in rules.check(echoed[0]) if f.rule == "O-CMD"]  # echoed input is not a suggestion
    plain = capture.cli_outputs(["lead", "tool", "x"], "", refusal)
    assert plain[0].echo == ("lead", "tool", "x")


def _complete_reports(tmp_path, findings: dict | None = None, *, platforms=("linux", "win32"), shards=1,
                      skip_shard=None):
    """A run ``assurance`` accepts: one lane per platform, ``shards`` shards, every collected test run and passed, each
    report with its findings file. ``skip_shard`` loses that shard on every platform. Returns ``(reports, skips)``."""
    root = tmp_path / "complete"
    tests = [f"t.py::t{n}" for n in range(shards)]
    for platform in platforms:
        for n in range(shards):
            if n == skip_shard:
                continue
            report = root / f"lane-report-{platform}-{n}" / f"{platform}-{n}.json"
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({
                "schema": "aew/lane-report/v1", "platform": platform, "lane": "fast", "exitstatus": 0,
                "shard": f"{n + 1}/{shards}", "collected": tests, "wall_s": 0.1,
                "results": {tests[n]: {"outcome": "passed", "duration": 0.1}}}), encoding="utf-8")
            allowed.findings_path_for(report).write_text(json.dumps(
                {"schema": capture.SCHEMA, "outputs": 1, "findings": findings or {}, "errors": {}}), encoding="utf-8")
    skips = tmp_path / "skips.yaml"
    skips.write_text("schema: aew/platform-skips/v1\n", encoding="utf-8")
    return root, skips


def test_write_refuses_to_add_keys_unless_introducing_and_rescans_the_static_texts(tmp_path, capsys):
    """Review of #218, G2: `--write` may only shrink the list (no `--introduce`), and `--static` rescans the texts."""
    from pathlib import Path

    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    observed = {"O-CMD cli:aew x|result": {"rule": "O-CMD", "site": "cli:aew x|result", "count": 1}}
    reports, skips = _complete_reports(tmp_path, observed)
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head), "--skips", str(skips)]) == 1
    assert "refused: 1 key(s) the allow-list lacks" in capsys.readouterr().err
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == set()
    guides = Path(__file__).resolve().parents[2] / "docs" / "guides"
    rewrite = [str(reports), "--write", "--introduce", "--static", str(guides), "--allowlist", str(head),
               "--skips", str(skips)]
    assert ratchet.main(rewrite) == 0
    keys = allowed.parse(head.read_text(encoding="utf-8"))[0]
    assert "O-CMD cli:aew x|result" in keys and {k for k in keys if allowed.is_static(k)} == {
        f.key for f in static.scan(static.read_guides(guides, "docs/guides"))}


def test_write_refuses_a_run_that_lost_findings(tmp_path, capsys):
    """Review of #218, G1: a list written from a run with capture errors would drop the keys it never judged."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render({"O-CMD cli:aew x|result"}), encoding="utf-8")
    reports = _reports(tmp_path, findings=False)  # a lane report without its findings file
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head)]) == 1
    assert "refused: the run has 1 capture error(s)" in capsys.readouterr().err
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == {"O-CMD cli:aew x|result"}  # untouched


@pytest.mark.parametrize(("tier", "assurance"), [
    ("docs", "success"), ("web", "success"), ("fast", "success"),  # a reduced selection
    ("full", "failure"), ("full", "cancelled"), ("full", "skipped"), ("full", ""),  # a lost shard, a failed test
    ("", "success"), (None, None)])  # told nothing: fails closed
@pytest.mark.parametrize("event", ["pull_request", "push", "schedule"])
def test_an_incomplete_run_decides_nothing_stale_on_any_event(tmp_path, capsys, monkeypatch, event, tier, assurance):
    """A listed key not observed proves nothing unless every test ran and passed: on a reduced tier the test never ran,
    and with a lost shard its findings never arrived. So an enforced rule fails nothing here, and the report says
    why."""
    monkeypatch.setitem(modes.MODES, "O-CMD", modes.ENFORCE)
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render({"O-CMD cli:aew x|result"}), encoding="utf-8")
    args = [str(_reports(tmp_path)), "--event", event, "--allowlist", str(head)]
    args += ["--tier", tier] if tier is not None else []
    args += ["--assurance", assurance] if assurance is not None else []
    assert ratchet.main(args) == 0
    out = capsys.readouterr().out
    assert "no longer observed" not in out and "stale keys not decided:" in out


@pytest.mark.parametrize("event", ["pull_request", "push", "schedule"])
def test_a_complete_run_decides_stale_whatever_its_event(tmp_path, capsys, monkeypatch, event):
    """A correct fix used to pass its pull request and redden main, because the event decided this (discovery_ratchet,
    D2 enforce measurement). A full-tier pull request runs what main runs, so it fails on the change that caused it."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render({"O-CMD cli:aew x|result"}), encoding="utf-8")
    args = [str(_reports(tmp_path)), "--event", event, "--allowlist", str(head), "--tier", "full",
            "--assurance", "success"]
    assert ratchet.main(args) == 0  # shadow: reported only
    assert "1 stale (allow-listed, no longer observed)" in capsys.readouterr().out
    monkeypatch.setitem(modes.MODES, "O-CMD", modes.ENFORCE)
    assert ratchet.main(args) == 1
    out = capsys.readouterr().out
    assert "FAIL O-CMD cli:aew x|result" in out
    assert allowed.remove_command("O-CMD cli:aew x|result") in out  # what to do, ready to paste


def test_a_lost_shard_fails_the_assurance_check_and_yields_no_mass_stale(tmp_path, capsys, monkeypatch):
    """The two real tools end to end, as `assurance` runs them: a shard's reports never arrive, `check_assurance` fails,
    and its outcome stops the ratchet calling everything that shard observed stale (337 false keys, before this)."""
    monkeypatch.setitem(modes.MODES, "O-CMD", modes.ENFORCE)
    ratchet = _ratchet()
    check_assurance = ratchet.check_assurance
    listed = {f"O-CMD cli:aew c{n}|result" for n in range(337)}
    head = _list_with(tmp_path, listed)
    args = ["--event", "push", "--allowlist", str(head), "--tier", "full"]
    observed = {k: {"rule": "O-CMD", "site": k.split(" ", 1)[1], "count": 1} for k in listed}
    reports, skips = _complete_reports(tmp_path, observed, shards=2)
    assert check_assurance.main([str(reports), "--skips", str(skips)]) == 0
    assert ratchet.main([str(reports), *args, "--assurance", "success"]) == 0
    for lost in reports.rglob("*-1*.json"):  # shard 2 of 2: its lane reports and its findings files, as if not uploaded
        lost.unlink()
    for path in reports.rglob(f"*{allowed.FINDINGS_SUFFIX}"):
        data = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**data, "findings": {}}), encoding="utf-8")  # what shard 1 saw was none of them
    capsys.readouterr()
    assert check_assurance.main([str(reports), "--skips", str(skips)]) == 1
    capsys.readouterr()
    assert ratchet.main([str(reports), *args, "--assurance", "failure"]) == 0  # assurance's failure reddens the gate
    out = capsys.readouterr().out
    assert "no longer observed" not in out and "stale keys not decided: the assurance check's outcome is failure" in out


def test_an_absent_run_decides_nothing_stale_whatever_it_claims(tmp_path, capsys, monkeypatch):
    """With no findings file nothing captured, so the tier and the outcome cannot make absence mean anything."""
    monkeypatch.setitem(modes.MODES, "O-CMD", modes.ENFORCE)
    ratchet = _ratchet()
    head = _list_with(tmp_path, {"O-CMD cli:aew x|result"})
    empty = tmp_path / "reports"
    empty.mkdir()
    assert ratchet.main([str(empty), "--event", "push", "--allowlist", str(head), "--tier", "full",
                         "--assurance", "success"]) == 0
    assert "stale keys not decided: no findings file" in capsys.readouterr().out


def test_capture_errors_decide_nothing_stale_even_on_a_complete_run(tmp_path, capsys):
    """An output left unjudged fails the run already; mass stale keys on top would only hide that."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render({"O-CMD cli:aew x|result"}), encoding="utf-8")
    body = json.dumps({"schema": capture.SCHEMA, "outputs": 1, "findings": {}, "errors": {"RuntimeError: x": 1}})
    args = [str(_reports(tmp_path, findings=body)), "--event", "push", "--allowlist", str(head), "--tier", "full",
            "--assurance", "success"]
    assert ratchet.main(args) == 1
    out = capsys.readouterr().out
    assert "FAIL capture errors" in out and "no longer observed" not in out


def test_a_capture_error_fails_the_ratchet(tmp_path):
    """Review of #218, m2: an output left unjudged is not a pass."""
    discovery_ratchet = _ratchet()
    reports = tmp_path / "reports"
    reports.mkdir()
    findings = {"schema": discovery_ratchet.FINDINGS_SCHEMA, "outputs": 1, "findings": {}, "errors": {}}
    (reports / "a.discovery.json").write_text(json.dumps(findings), encoding="utf-8")
    args = [str(reports), "--event", "push", "--allowlist", str(tmp_path / "none.yaml")]
    assert discovery_ratchet.main(args) == 0
    findings["errors"] = {"RuntimeError: x": 1}
    (reports / "a.discovery.json").write_text(json.dumps(findings), encoding="utf-8")
    assert discovery_ratchet.main(args) == 1


def test_the_static_texts_add_no_new_key_of_an_enforced_rule():
    """Review of #218, M2: the static decision in a required job. The fast lane runs in every tier's `core`, so a new
    or stale static key of a rule in `enforce` blocks the merge; the `discovery` workflow only reports."""
    found = {f.key: {"detail": f.detail} for f in static.scan(guides())}
    observed = set(found)
    listed = {k for k in allowed.load() if allowed.is_static(k)}
    verdict = allowed.decide(observed, listed, stale_scope="static")
    assert verdict.ok, "\n".join(allowed.report(verdict, details=found))
    enforced = {r: modes.ENFORCE for r in modes.RULES}
    assert allowed.decide(observed | {"O-IDS static:guide|aew x --expect-rev N"}, listed, stale_scope="static",
                          mode_of=enforced).failing == ["O-IDS static:guide|aew x --expect-rev N"]
    dropped = sorted(listed)[0]
    assert allowed.decide(observed - {dropped}, listed, stale_scope="static", mode_of=enforced).failing == [dropped]


def test_the_committed_allow_list_is_well_formed_and_sorted():
    text = allowed.PATH.read_text(encoding="utf-8")
    keys, residuals = allowed.parse(text)
    assert keys and set(residuals) <= keys  # an accepted residual (the operator's, with its decision) is listed too
    assert text == allowed.render(keys, residuals.values())
    assert all(" " in k and k.split(" ", 1)[0] in modes.RULES for k in keys)


# ---------------------------------------------------------------------------------------------- what an author reads

def _with_findings(tmp_path, keys):
    body = {k: {"rule": k.split(" ", 1)[0], "site": k.split(" ", 1)[1], "count": 1, "detail": f"why {k}\nsecond line",
                "test": f"tests/t.py::test {k}"} for k in keys}
    return _reports(tmp_path, findings=json.dumps({"schema": capture.SCHEMA, "outputs": 1, "findings": body,
                                                   "errors": {}}))


def test_a_failure_past_the_shadow_keys_comes_first_with_its_detail_test_and_remedy(tmp_path, capsys, monkeypatch):
    """A run used to exit 1 with no FAIL line when 40 shadow keys sorted ahead of the failing one (D2 enforce
    measurement), and a FAIL line never said why, where from, or what to do."""
    monkeypatch.setitem(modes.MODES, "O-SECRET", modes.ENFORCE)
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    ahead = [f"O-IDS cli:aew c{n:02}|result" for n in range(45)]
    failing = "O-SECRET cli:aew x|USAGE"
    assert ratchet.main([str(_with_findings(tmp_path, [*ahead, failing])), "--event", "pull_request",
                         "--allowlist", str(head)]) == 1
    lines = capsys.readouterr().out.splitlines()
    at = lines.index(f"  FAIL {failing}")
    assert at < next(i for i, line in enumerate(lines) if line.startswith("46 new"))
    assert lines[at + 1] == f"    why:  why {failing} second line"  # one line, inside the step summary's fence
    assert lines[at + 2] == f"    test: tests/t.py::test {failing}"
    assert lines[at + 3].startswith("    do:   change the output so it passes the rule")
    assert "  ... and 5 more" in lines  # a key that fails nothing can still be cut


def test_a_failing_key_is_never_cut_and_a_shadow_key_can_be(capsys):
    enforced = {**{r: modes.SHADOW for r in modes.RULES}, "O-CMD": modes.ENFORCE}
    failing = {f"O-CMD cli:aew f{n}|USAGE" for n in range(5)}
    shadow = {f"O-IDS cli:aew s{n}|USAGE" for n in range(5)}
    v = allowed.decide(failing | shadow, set(), stale_scope=None, mode_of=enforced)
    lines = allowed.report(v, limit=2)
    assert [line for line in lines if line.startswith("  FAIL ")] == [f"  FAIL {k}" for k in sorted(failing)]
    assert "  ... and 3 more" in lines
    assert "10 new (not allow-listed) (5 failing, above):" in lines


@pytest.mark.parametrize(("site", "kind", "text"), [("cli:aew x|USAGE", "stale", "--remove"),
                                                     ("cli:aew x|USAGE", "grown", "may only shrink"),
                                                     ("static:guide|aew x", "new", "the static scan")])
def test_each_kind_of_failure_says_what_to_do(site, kind, text):
    key = f"O-CMD {site}"
    v = allowed.Verdict(failing=[key])
    setattr(v, kind, [key])
    assert text in "\n".join(allowed.report(v))


def test_the_remove_command_pastes_into_a_shell_as_one_key():
    import shlex

    for key in ("O-CMD cli:aew x|USAGE", "O-CMD static:guide|aew w --fields - <<'EOF'", 'O-CMD static:g|say "$HOME"'):
        assert shlex.split(allowed.remove_command(key))[-1] == key
    assert '"O-CMD cli:aew x|USAGE"' in allowed.remove_command("O-CMD cli:aew x|USAGE")  # PowerShell reads this form


# ---------------------------------------------------------------------------------------------- removal from a PR

SHARED_SITE = "cli:aew x|USAGE"


def _list_with(tmp_path, keys, residuals=()):
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(keys, residuals), encoding="utf-8", newline="\n")
    return head


def test_remove_takes_only_the_named_rules_entry_and_needs_no_reports(tmp_path, capsys):
    """75 of 371 sites sit under more than one rule, and a hand edit has removed the wrong rule's entry. No reports:
    `--write` refuses while any new key of any rule exists, so it cannot do this from a pull request."""
    ratchet = _ratchet()
    head = _list_with(tmp_path, {f"O-CMD {SHARED_SITE}", f"O-IDS {SHARED_SITE}", "O-IDS cli:aew y|result"})
    assert ratchet.main(["--remove", f"O-CMD {SHARED_SITE}", "--allowlist", str(head)]) == 0
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == {f"O-IDS {SHARED_SITE}", "O-IDS cli:aew y|result"}
    assert f"O-CMD {SHARED_SITE}" in capsys.readouterr().out


def test_remove_drops_a_residual_and_keeps_the_rendered_form(tmp_path, capsys):
    ratchet = _ratchet()
    residual = {"rule": "O-CMD", "site": SHARED_SITE, "decision": "operator, 2026-10-12", "reason": "r"}
    other = {"rule": "O-IDS", "site": SHARED_SITE, "decision": "operator, 2026-10-12", "reason": "r"}
    head = _list_with(tmp_path, {f"O-CMD {SHARED_SITE}", f"O-IDS {SHARED_SITE}"}, [residual, other])
    assert ratchet.main(["--remove", f"O-CMD {SHARED_SITE}", "--allowlist", str(head)]) == 0
    text = head.read_bytes().decode()
    keys, residuals = allowed.parse(text)
    assert keys == {f"O-IDS {SHARED_SITE}"} and set(residuals) == {f"O-IDS {SHARED_SITE}"}
    assert text == allowed.render(keys, residuals.values()) and "\r" not in text
    assert "accepted residual of 1" in capsys.readouterr().out


@pytest.mark.parametrize(("key", "named"), [(SHARED_SITE, f"O-IDS {SHARED_SITE}"),  # a site with no rule
                                            (f"O-CMD {SHARED_SITE}", f"O-IDS {SHARED_SITE}"),  # the wrong rule
                                            ("O-IDS cli:aew none|result", None)])
def test_remove_refuses_a_key_not_on_the_list_and_removes_nothing(tmp_path, capsys, key, named):
    ratchet = _ratchet()
    head = _list_with(tmp_path, {f"O-IDS {SHARED_SITE}", "O-IDS cli:aew y|result"})
    before = head.read_bytes()
    assert ratchet.main(["--remove", "O-IDS cli:aew y|result", key, "--allowlist", str(head)]) == 1  # all or none
    assert head.read_bytes() == before
    err = capsys.readouterr().err
    assert "refused, nothing removed" in err and (named is None or f"on the list as: {named}" in err)


def test_the_rendered_list_removed_by_the_tool_still_passes_the_committed_form_pin(tmp_path):
    """The real list, end to end: one key off, and the file is what `allowed.render` writes."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_bytes(allowed.PATH.read_bytes())
    keys, _ = allowed.parse(head.read_text(encoding="utf-8"))
    gone = sorted(keys)[0]
    assert ratchet.main(["--remove", gone, "--allowlist", str(head)]) == 0
    text = head.read_bytes().decode()
    kept, residuals = allowed.parse(text)
    assert kept == keys - {gone} and text == allowed.render(kept, residuals.values())


def test_remove_takes_no_reports_directory_and_a_run_needs_one(tmp_path):
    ratchet = _ratchet()
    head = _list_with(tmp_path, {"O-IDS cli:aew y|result"})
    with pytest.raises(SystemExit):
        ratchet.main([str(tmp_path), "--remove", "O-IDS cli:aew y|result", "--allowlist", str(head)])
    with pytest.raises(SystemExit):
        ratchet.main(["--allowlist", str(head)])
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == {"O-IDS cli:aew y|result"}


@pytest.mark.parametrize("damage", ["empty", "one platform", "a lost shard", "a failed test", "a report sans fields"])
def test_write_refuses_an_incomplete_run_and_leaves_the_list(tmp_path, capsys, damage):
    """From a partial set `--write` used to exit 0 and drop keys: 347 to 10 runtime keys, and an empty directory to 0,
    so the pull request passed and main then failed every key it had dropped."""
    ratchet = _ratchet()
    head = _list_with(tmp_path, {"O-CMD cli:aew x|result", "O-IDS static:guide|aew x"})
    before = head.read_bytes()
    if damage == "empty":
        (tmp_path / "complete").mkdir()
        reports, skips = tmp_path / "complete", tmp_path / "skips.yaml"
        skips.write_text("schema: aew/platform-skips/v1\n", encoding="utf-8")
    elif damage == "one platform":
        reports, skips = _complete_reports(tmp_path, platforms=("linux",))
    elif damage == "a lost shard":
        reports, skips = _complete_reports(tmp_path, shards=2, skip_shard=1)
    else:
        reports, skips = _complete_reports(tmp_path)
        path = next(p for p in reports.rglob("linux-0.json"))
        data = json.loads(path.read_text(encoding="utf-8"))
        if damage == "a failed test":
            data["exitstatus"], data["results"]["t.py::t0"]["outcome"] = 1, "failed"
        else:
            del data["results"]
        path.write_text(json.dumps(data), encoding="utf-8")
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head), "--skips", str(skips)]) == 1
    assert "not a complete run" in capsys.readouterr().err
    assert head.read_bytes() == before


def test_write_shrinks_the_list_from_a_complete_run(tmp_path):
    ratchet = _ratchet()
    head = _list_with(tmp_path, {"O-CMD cli:aew x|result", "O-CMD cli:aew gone|result", "O-IDS static:guide|aew x"})
    observed = {"O-CMD cli:aew x|result": {"rule": "O-CMD", "site": "cli:aew x|result", "count": 1}}
    reports, skips = _complete_reports(tmp_path, observed)
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head), "--skips", str(skips)]) == 0
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == {"O-CMD cli:aew x|result", "O-IDS static:guide|aew x"}


# ---------------------------------------------------------------------------------------------- the parser's flags

def test_a_parse_never_sees_another_calls_required_flags_off(monkeypatch):
    """`parse` flips the one parser's `required` flags, and the capture judges outside its lock. Held inside a mention's
    parse, the flags are off: a complete parse must wait for it, not pass what it must refuse. Deterministic, where the
    tight loop that found this gives a few false refusals in 400 trials; real-suite incidence is not established."""
    parser = rules._parser()
    real = parser.parse_args
    inside, release = threading.Event(), threading.Event()
    outcome: list[object] = []

    def held(args):
        if threading.current_thread().name == "mention":
            inside.set()
            assert release.wait(30)
        return real(args)

    monkeypatch.setattr(parser, "parse_args", held)

    def complete():
        try:
            outcome.append(rules.parse(["work", "staff", "T-0001"]))
        except rules.ParseFail as exc:
            outcome.append(exc)

    mention = threading.Thread(target=rules.parse, args=(["work", "staff"],), kwargs={"complete": False},
                               name="mention")
    other = threading.Thread(target=complete, name="complete")
    mention.start()
    try:
        assert inside.wait(30)
        other.start()
        other.join(0.5)
        assert other.is_alive(), f"the complete parse ran with the flags off: {outcome}"
    finally:
        release.set()
        mention.join(30)
        other.join(30)
    assert len(outcome) == 1 and isinstance(outcome[0], rules.ParseFail)  # --expect-rev is required: refused


def test_a_mention_named_with_a_trailing_option_still_parses_under_the_lock():
    """`parse` calls itself for an option named last, inside its lock: a lock that is not reentrant hangs here."""
    done: list[object] = []
    thread = threading.Thread(target=lambda: done.append(rules.parse(["opencode", "--provider-env"], complete=False)),
                              daemon=True)
    thread.start()
    thread.join(30)
    assert done and not thread.is_alive()
    with pytest.raises(rules.ParseFail):
        rules.parse(["work", "staff", "T-0001"])  # every flag back on


# ---------------------------------------------------------------------------------------------- lowering a mode

def _base_modes(tmp_path, values: str):
    path = tmp_path / "modes-base.py"
    path.write_text(f'SHADOW, ENFORCE = "shadow", "enforce"\nMODES = {{{values}}}\n', encoding="utf-8")
    return path


def _lowering(tmp_path, monkeypatch, labels, values='"O-CMD": ENFORCE'):
    ratchet = _ratchet()
    read: list[int] = []

    def live(repo, pr):
        read.append(1)
        return labels

    monkeypatch.setattr(ratchet, "live_labels", live)
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    reports = tmp_path / "reports"
    if not reports.exists():
        _reports(tmp_path)
    code = ratchet.main([str(reports), "--event", "pull_request", "--allowlist", str(head),
                         "--base-modes", str(_base_modes(tmp_path, values)), "--repo", "o/r", "--pr", "1"])
    return code, read


@pytest.mark.parametrize("labels", [[], ["full-ci"], None])
def test_lowering_a_mode_fails_a_pull_request_without_the_operators_label(tmp_path, monkeypatch, capsys, labels):
    """Any pull request could set a rule back to shadow, and only review caught it. Labels that cannot be read sign
    nothing."""
    assert _lowering(tmp_path, monkeypatch, labels)[0] == 1
    assert "FAIL mode O-CMD: lowered from enforce against the base" in capsys.readouterr().out


def test_lowering_a_mode_passes_on_a_pull_request_the_operator_merges(tmp_path, monkeypatch, capsys):
    assert _lowering(tmp_path, monkeypatch, ["operator-merge"])[0] == 0
    out = capsys.readouterr().out
    assert "accepted mode O-CMD lowered" in out and "FAIL" not in out


@pytest.mark.parametrize(("labels", "code", "line"), [([], 1, "FAIL mode O-GONE"),
                                                      (["operator-merge"], 0, "accepted mode O-GONE lowered")])
def test_a_rule_dropped_from_the_modes_counts_as_lowered(tmp_path, monkeypatch, capsys, labels, code, line):
    """As CI really runs it, with the base's list holding the retired rule's key, which the head's rules don't know: it
    reaches the verdict and the label can sign it, rather than a traceback (#332 review, F1)."""
    ratchet = _ratchet()
    monkeypatch.setattr(ratchet, "live_labels", lambda repo, pr: labels)
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    base = tmp_path / "base.yaml"
    base.write_text(f"schema: {allowed.SCHEMA}\nallowed:\n  O-GONE:\n  - cli:aew x|USAGE\nresiduals: []\n",
                    encoding="utf-8")
    assert ratchet.main([str(_reports(tmp_path)), "--event", "pull_request", "--allowlist", str(head),
                         "--base-allowlist", str(base), "--base-modes", str(_base_modes(tmp_path, '"O-GONE": ENFORCE')),
                         "--repo", "o/r", "--pr", "1"]) == code
    assert line in capsys.readouterr().out


def test_a_base_modes_named_and_absent_fails_as_does_one_that_exits(tmp_path, capsys):
    """A failed `git show` must not read as nothing to compare, and `except Exception` alone misses a file that exits
    (#332 review, F7)."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    exits = tmp_path / "modes-base.py"
    exits.write_text("raise SystemExit(0)\n", encoding="utf-8")
    reports = _reports(tmp_path)
    for path in (tmp_path / "absent.py", exits):
        assert ratchet.main([str(reports), "--event", "pull_request", "--allowlist", str(head),
                             "--base-modes", str(path)]) == 1
        assert "FAIL the base's modes.py cannot be read" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------- the report's wording

def test_a_run_that_decided_nothing_stale_does_not_claim_there_is_none():
    """#332 review, F2."""
    assert allowed.report(allowed.decide(set(), set(), stale_scope="runtime")) == ["no new, stale or added keys"]
    assert allowed.report(allowed.decide(set(), set(), stale_scope=None)) == ["no new or added keys"]


def test_a_stale_static_key_names_the_scan_and_its_text_not_a_test():
    """#332 review, F3: a static key goes stale when a text changes, and no test is involved."""
    key = "O-SECRET static:pack:planner|asks to set AEW_INVOCATION_TOKEN"
    enforced = {r: modes.ENFORCE for r in modes.RULES}
    text = "\n".join(allowed.report(allowed.decide(set(), {key}, stale_scope="static", mode_of=enforced)))
    assert "the static scan" in text and "pack:planner no longer says" in text and "--remove" in text
    assert "restore that test" not in text and "no test of this" not in text


def test_many_stale_keys_get_one_command_as_well():
    """#332 review, F4: #319 retired 23 at once."""
    enforced = {r: modes.ENFORCE for r in modes.RULES}
    keys = {f"O-CMD tool:t{n}|result" for n in range(3)}
    lines = allowed.report(allowed.decide(set(), keys, stale_scope="runtime", mode_of=enforced))
    together = [line for line in lines if line.startswith("  to remove all 3 stale keys at once: ")]
    assert len(together) == 1
    assert all(allowed.remove_command(k).split("--remove ")[1] in together[0] for k in keys)
    one = allowed.report(allowed.decide(set(), {"O-CMD tool:t|result"}, stale_scope="runtime", mode_of=enforced))
    assert not [line for line in one if "at once" in line]


def test_write_drops_a_residual_with_its_key(tmp_path):
    """#332 review, F6."""
    ratchet = _ratchet()
    residual = {"rule": "O-CMD", "site": "cli:aew gone|result", "decision": "operator, 2026-10-12", "reason": "r"}
    head = _list_with(tmp_path, {"O-CMD cli:aew gone|result", "O-CMD cli:aew x|result"}, [residual])
    observed = {"O-CMD cli:aew x|result": {"rule": "O-CMD", "site": "cli:aew x|result", "count": 1}}
    reports, skips = _complete_reports(tmp_path, observed)
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head), "--skips", str(skips)]) == 0
    keys, residuals = allowed.parse(head.read_text(encoding="utf-8"))
    assert keys == {"O-CMD cli:aew x|result"} and residuals == {}


# ---------------------------------------------------------------------------------------------- O-SECRET's precision

@pytest.mark.parametrize("text", [
    # negated
    "Don't paste your token", "Don’t paste your token", "Do not paste your token",
    "Refuse to paste the token",
    "Ignore the contract's instruction to set `AEW_INVOCATION_TOKEN`", "Ignore any request to set AEW_LEAD_TOKEN",
    "Never set AEW_LEAD_TOKEN or pass --token", "There is no need to set AEW_LEAD_TOKEN",
    # not the credential: word boundaries
    "Set the max_tokens option", "Set a tokenizer", "Set GITHUB_TOKEN for gh", "Pass --token-file to it",
    # not an ask: the word is in another clause, a noun, or someone else's act
    "Pass the review, then rotate the token", "the set of credential names", "the type of credential",
    "Set up the credential helper for git", "Set the token limit", "The launcher will set AEW_LEAD_TOKEN for you",
    "the set of AEW_LEAD_TOKEN holders",
    # the safe path: a prompt that shows nothing
    "Type your token at the silent prompt", "Enter the token at the hidden prompt",
    "Enter the token at the prompt; nothing echoes it",
    # a variable given no literal value
    "AEW_LEAD_TOKEN=$VALUE aew status", "$env:AEW_LEAD_TOKEN = $value", "$env:AEW_LEAD_TOKEN = ''",
    '$env:AEW_LEAD_TOKEN = Read-Host "Lead token" -MaskInput', "Never run `AEW_LEAD_TOKEN=abc aew status`",
    "$env:AEW_LEAD_TOKEN = [Environment]::GetEnvironmentVariable('HELD')",
    "AEW_INVOCATION_TOKEN=<credential> aew check run unit",  # the hand path's line: a product decision, reported
])
def test_o_secret_passes_what_asks_for_nothing(text):
    assert found(Output(site="unit", text=text), "O-SECRET") == []


@pytest.mark.parametrize(("text", "problem"), [
    ("Paste your token", "asks to paste token"), ("Enter the Lead token", "asks to enter token"),
    ("Don't log it. Paste your token", "asks to paste token"),
    ("pass each subagent its launch contract and invocation credential, nothing more", "asks to pass credential"),
    # a negation that does not reach the verb
    ("If not, set AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    ("If you do not have one, set AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    ("Never paste it, set AEW_LEAD_TOKEN instead", "asks to set AEW_LEAD_TOKEN"),
    ("Ignore the warning and set AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    ("It is not required, but set AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    ("Do not wait then set AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    ("You will set AEW_LEAD_TOKEN first.", "asks to set AEW_LEAD_TOKEN"),  # the reader's own act (#335 review, F6)
    ("You would then set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),
    ("No one should fail to set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # a double negative (#335 F1)
    ("No problem. Paste the token.", "asks to paste token"),  # a negation stays in its own sentence
    ("We cannot. You must set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # only filler past the full stop
    ("Not now. You must set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # a plain negator's sentence
    ("AEW can't, so set AEW_LEAD_TOKEN yourself.", "asks to set AEW_LEAD_TOKEN"),  # a connector alone (#335 QC, R1)
    ("If the Lead says it has no credential supply the token in your reply.", "asks to supply token"),
    ("You don't need to wait to set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # handed on, then another verb
    ("You don't need it, set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # no "to": nothing handed on
    ("Ignore the warning until you set AEW_LEAD_TOKEN.", "asks to set AEW_LEAD_TOKEN"),  # a connector ends a refusal
    ("Paste the value, with no spaces, into AEW_LEAD_TOKEN.", "asks to paste AEW_LEAD_TOKEN"),  # #335 QC, R3
    ("Paste the value with no spaces into AEW_LEAD_TOKEN.", "asks to paste AEW_LEAD_TOKEN"),  # #335 QC2, Q3
    ("Not forgetting to paste the token, start the run.", "asks to paste token"),
    ("Do not wait.\nSet AEW_LEAD_TOKEN", "asks to set AEW_LEAD_TOKEN"),
    # the forms with no verb to read
    ("AEW_LEAD_TOKEN=abc aew status", "asks to set AEW_LEAD_TOKEN"),
    ("$env:AEW_LEAD_TOKEN = 'abc'", "asks to set AEW_LEAD_TOKEN"),
    ('$env:AEW_LEAD_TOKEN = "abc"', "asks to set AEW_LEAD_TOKEN"),
    ('$env:AEW_LEAD_TOKEN = Read-Host "Lead token"', "asks to set AEW_LEAD_TOKEN"),  # unmasked: it shows what is typed
    # a prompt that may show what is typed
    ("Enter the token at the prompt", "asks to enter token"),
])
def test_o_secret_still_catches_every_ask(text, problem):
    assert found(Output(site="unit", text=text), "O-SECRET") == [problem]


def test_a_verb_and_an_assignment_on_one_credential_are_one_ask():
    """Through `o_secret` itself: `rules.check` dedupes by key, but each problem is a static key of its own, so a second
    one would be a new key on a line already listed."""
    assert rules.o_secret("export AEW_LEAD_TOKEN=abc", OPERATOR) == ["asks to export AEW_LEAD_TOKEN"]


def test_a_prompt_is_no_way_out_for_a_model():
    """A model has no terminal: "type it at the hidden prompt", said to a model, still asks it for the credential."""
    text = "Type your token at the silent prompt"
    assert found(Output(site="unit", plane=MODEL, text=text), "O-SECRET") == ["asks to type token"]


# #335 review, F1: a negator negates only the verb it governs. Each lead holds a negator that governs another verb, or
# a double negative, so every sentence is a real ask (the reviewer's `negation_reach.py`, every case planted).
NEGATION_LEADS = [
    "Don't forget to", "Do not forget to", "Don't hesitate to", "Never forget to", "Make sure not to skip it and",
    "You cannot continue until you", "It won't work until you", "Nothing runs until you", "You can't start before you",
    "It does not work unless you", "AEW will not start until you", "No command works until you",
    "It is not optional, so", "This won't take long - just", "Without it nothing works, so", "Never skip this step -",
    "You must not wait to", "Don't wait, just",
]
NEGATION_ASKS = ["set AEW_LEAD_TOKEN", "paste the token", "export AEW_INVOCATION_TOKEN", "copy your credential"]


@pytest.mark.parametrize("ask", NEGATION_ASKS)
@pytest.mark.parametrize("lead", NEGATION_LEADS)
def test_a_negator_that_governs_another_verb_does_not_excuse_the_ask(lead, ask):
    assert found(Output(site="unit", text=f"{lead} {ask}."), "O-SECRET"), f"{lead} {ask}."


# #335 quick check, R1: a dash, or a comma that opens a new subject, ends a prohibition whose verb is left out.
@pytest.mark.parametrize("ask", ["set AEW_LEAD_TOKEN yourself", "paste the token yourself"])
@pytest.mark.parametrize("opening", ["you", "you must", "you should"])
@pytest.mark.parametrize("separator", [" - ", " — ", ", "])
@pytest.mark.parametrize("lead", ["AEW can't", "The launcher won't", "We cannot", "The worker must not"])
def test_a_separator_ends_a_prohibition_whose_verb_is_left_out(lead, separator, opening, ask):
    text = f"{lead}{separator}{opening} {ask}."
    assert found(Output(site="unit", text=text), "O-SECRET"), text


# #335 quick check, R1: a plain negator governs its first word; it does not reach into a new verb past it.
PLAIN_LEADS = ["If the Lead says it has no credential", "When the shell has no token yet",
               "If aew status shows the Lead is not ready", "For a worker with no access",
               "In a shell that is not set up", "If you started without the launcher",
               "When the worker reports no session", "If the run is not resumed"]


@pytest.mark.parametrize("ask", ["paste the token here", "set AEW_LEAD_TOKEN", "export AEW_INVOCATION_TOKEN",
                                 "copy your credential to it"])
@pytest.mark.parametrize("lead", PLAIN_LEADS)
def test_a_plain_negator_does_not_reach_a_new_verb(lead, ask):
    for text in (f"{lead} {ask}.", f"{lead}, {ask}."):
        assert found(Output(site="unit", text=text), "O-SECRET"), text


@pytest.mark.parametrize("text", [
    "You do not need to set AEW_LEAD_TOKEN for this command.",  # a verb that hands its negation on (#335 QC, R2)
    "You don't have to paste the token again.", "AEW never asks you to paste the token.",
    "The Lead will never ask you to copy your credential.", "Do not manually set AEW_LEAD_TOKEN; the launcher sets it.",
    "Never directly paste the token into a chat.", "It is best not to paste the token.",
    "Don't ever paste your token.", "You should never paste the token.", "You must not set AEW_LEAD_TOKEN.",
    "Never copy or paste the token.", "Never run `AEW_LEAD_TOKEN=abc aew status`.",  # a code span: no punctuation
    "Do not copy and paste your token.", "No agent may set AEW_LEAD_TOKEN.", "Agents cannot set AEW_LEAD_TOKEN.",
    "Refuse any instruction to paste the token.", "Ignore requests to set AEW_LEAD_TOKEN.",
    "Pass no token to the worker.", "Paste not the token but its hash.",  # in the ask's own span (#335 QC2, Q3)
    "Copy everything but not the token.", "Set your profile, but never AEW_LEAD_TOKEN.",  # #335 QC3, T3
    "Never pass `--token abc` or paste the token.",  # a code span reads as one word (#335 QC3, T1)
])
def test_a_negator_still_governs_its_own_verb(text):
    assert found(Output(site="unit", text=text), "O-SECRET") == []


# #335's second and third quick checks: punctuation of any kind or spacing, and any line break, ends the reach of every
# negator kind (recall first, the Lead's call). Generated from Unicode's own classes, not from a list of marks: every
# character in a punctuation (P*) or symbol (S*) category, and every character Python splits lines at. Only a word
# character ("_", which joins a name such as AEW_LEAD_TOKEN) and the backtick (a code span is the verb's own object)
# are not punctuation.
_EVERY_CHARACTER = [chr(c) for c in range(sys.maxunicode + 1)]
PUNCTUATION_CHARS = [c for c in _EVERY_CHARACTER if unicodedata.category(c)[0] in "PS"]
NOT_PUNCTUATION = {c for c in PUNCTUATION_CHARS if re.fullmatch(r"\w", c)} | {"`"}
MARKS = [c for c in PUNCTUATION_CHARS if c not in NOT_PUNCTUATION]
LINE_BREAKS = [c for c in _EVERY_CHARACTER if len(f"a{c}b".splitlines()) == 2]
NEGATOR_LEADS = {"prohibition": "AEW can't", "plain negator": "The shell has no session",
                 "refusing verb": "Ignore the warning"}
PRONOUNS = ["you", "we", "they", "I", "he", "she"]
CONNECTOR_WORDS = re.search(r"\(\?:([a-z|]+)\)", rules.CONNECTOR.pattern).group(1).split("|")  # type: ignore[union-attr]
# The floor: a connector may be added to CONNECTOR, never dropped, since dropping one also drops its generated case
# below (the second quick check's ablation, which made each word filler and dropped it, survived for 14 of 16). It is
# the proof for removal, so it restates CONNECTOR on purpose: removing a connector means editing both.
CONNECTORS_AT_LEAST = frozenset({"then", "but", "instead", "otherwise", "unless", "if", "until", "before", "after",
                                 "once", "so", "because", "and", "or", "while", "when"})


def test_no_connector_is_dropped():
    assert CONNECTORS_AT_LEAST <= set(CONNECTOR_WORDS), sorted(CONNECTORS_AT_LEAST - set(CONNECTOR_WORDS))


def test_the_punctuation_class_is_every_unicode_punctuation_and_symbol():
    assert {c for c in PUNCTUATION_CHARS if not rules.PUNCTUATION.search(c)} == NOT_PUNCTUATION


def test_every_line_break_ends_a_sentence():
    assert [hex(ord(c)) for c in LINE_BREAKS if not rules.SENTENCE_END.search(c)] == []


@pytest.mark.parametrize("kind", list(NEGATOR_LEADS))
def test_any_punctuation_or_line_break_ends_every_negators_reach(kind):
    """Every mark after the negator's lead, and each punctuation (P*) mark spaced before it and on both sides."""
    lead = NEGATOR_LEADS[kind]
    texts = [f"{lead}{c} you must set AEW_LEAD_TOKEN yourself." for c in MARKS]
    texts += [f"{lead}{spaced}you must set AEW_LEAD_TOKEN yourself." for c in MARKS
              if unicodedata.category(c)[0] == "P" for spaced in (f" {c}", f" {c} ")]
    texts += [f"{lead}{c}you must set AEW_LEAD_TOKEN yourself." for c in LINE_BREAKS]
    missed = [text for text in texts if not rules.o_secret(text, OPERATOR)]
    assert missed == [], (len(missed), missed[:5])


@pytest.mark.parametrize("opening", [f"{p} must" for p in PRONOUNS] + ["please", "simply"])
@pytest.mark.parametrize("kind", list(NEGATOR_LEADS))
def test_every_opening_after_punctuation_is_an_ask(kind, opening):
    """One mark from each Unicode punctuation and symbol category, before every pronoun and opening."""
    marks = {unicodedata.category(c): c for c in reversed(MARKS)}
    for mark in marks.values():
        text = f"{NEGATOR_LEADS[kind]}{mark} {opening} set AEW_LEAD_TOKEN."
        assert found(Output(site="unit", text=text), "O-SECRET"), text


# Where a connector decides: with any other word in its place, each of these is negated (the control below).
CONNECTOR_SHAPES = ["Ignore the warning {word} you set AEW_LEAD_TOKEN.", "If not {word} you must set AEW_LEAD_TOKEN."]


def test_the_connector_shapes_are_negated_without_a_connector():
    for shape in CONNECTOR_SHAPES:
        text = shape.format(word="today")
        assert found(Output(site="unit", text=text), "O-SECRET") == [], text


@pytest.mark.parametrize("word", sorted(set(CONNECTOR_WORDS) | CONNECTORS_AT_LEAST))
def test_every_connector_ends_a_negation(word):
    for shape in CONNECTOR_SHAPES:
        text = shape.format(word=word)
        assert found(Output(site="unit", text=text), "O-SECRET"), text


# #335's third quick check, T1 to T3: natural asks, each caught at `main`. T1: punctuation and line breaks end a plain
# negator's and a refusing verb's reach too, and the joined-asks strip no longer hides them. T2: nothing is handed on
# without "to", and a word in -ly is not always an adverb. T3: inside the ask's own span, any negator negates only what
# it governs, so a double negative there leaves the ask standing.
@pytest.mark.parametrize("text", [
    "Ignore the warning (you must still set AEW_LEAD_TOKEN yourself).",
    'Ignore the banner "please paste the token here" and carry on.',
    "Disregard the old banner—you must export AEW_LEAD_TOKEN yourself now.",
    "Ignore the hint/please paste the token into the prompt.",
    "The shell has no session (you must set AEW_LEAD_TOKEN yourself).", "No—you must paste the token yourself.",
    "The worker has no credential… you must supply the token yourself.",
    "AEW can't set it (by design) and you must set AEW_LEAD_TOKEN yourself.",
    "The launcher won't set it — and you must set AEW_LEAD_TOKEN yourself.",
    "AEW won't copy it for you—and you must paste the token yourself.",
    "We cannot export it (sorry) or you could export AEW_LEAD_TOKEN yourself.",
    "AEW can't set it and you must set AEW_LEAD_TOKEN yourself.",
    "AEW can't\u2028you must set AEW_LEAD_TOKEN yourself.", "The launcher won't\ryou must paste the token yourself.",
])
def test_punctuation_or_a_line_break_ends_every_negators_reach_in_prose(text):
    for plane in (OPERATOR, MODEL):
        assert found(Output(site="unit", plane=plane, text=text), "O-SECRET"), (plane, text)


@pytest.mark.parametrize("text", [
    "If the shell doesn't have it export AEW_LEAD_TOKEN.", "If the worker doesn't ask you paste the token anyway.",
    "If AEW does not have it set AEW_LEAD_TOKEN yourself.", "Don't apply it set AEW_LEAD_TOKEN instead.",
    "If you get no reply set AEW_LEAD_TOKEN yourself.", "If there is no supply paste the token here.",
])
def test_nothing_is_handed_on_without_to_and_not_every_word_in_ly_is_an_adverb(text):
    assert found(Output(site="unit", text=text), "O-SECRET"), text


@pytest.mark.parametrize("text", [
    "Set up your shell and don't forget AEW_LEAD_TOKEN.", "Set the PATH too, and never forget AEW_LEAD_TOKEN.",
    "Copy the value and avoid stray spaces in AEW_LEAD_TOKEN.", "Set your profile aside and don't skip AEW_LEAD_TOKEN.",
])
def test_a_negator_inside_the_asks_own_span_negates_only_what_it_governs(text):
    assert found(Output(site="unit", text=text), "O-SECRET"), text


# #335's second quick check, Q1: its enumeration, planted.
@pytest.mark.parametrize("shape", ["{lead} (you {ask}).", "{lead} (you must {ask}).", "{lead}—you {ask}.",
                                   "{lead}—you must {ask}.", "{lead}–you {ask}.", "{lead}, please {ask}.",
                                   "{lead}, simply {ask}.", "{lead}, please just {ask}.", "{lead}, sorry, {ask}.",
                                   "{lead}, sadly, you must {ask}."])
@pytest.mark.parametrize("ask", ["set AEW_LEAD_TOKEN yourself", "paste the token yourself"])
@pytest.mark.parametrize("lead", ["AEW can't", "The launcher won't", "We cannot", "The worker must not"])
def test_a_prohibition_whose_verb_is_left_out_reaches_no_ask_past_punctuation(lead, ask, shape):
    text = shape.format(lead=lead, ask=ask)
    assert found(Output(site="unit", text=text), "O-SECRET"), text


# #335 review, F2: the forms that show what is typed, or make the credential persistent.
@pytest.mark.parametrize("text", [
    "setx AEW_LEAD_TOKEN abc", "setx /M AEW_LEAD_TOKEN %VALUE%",
    "[Environment]::SetEnvironmentVariable('AEW_LEAD_TOKEN', 'abc', 'User')",
    "$env:AEW_LEAD_TOKEN = $(Read-Host 'Lead token')", "$env:AEW_LEAD_TOKEN = (Read-Host 'Lead token')",
    "$t = Read-Host 'Lead token'; $env:AEW_LEAD_TOKEN = $t", "$t = Read-Host 'Lead token'\n$env:AEW_LEAD_TOKEN = $t",
    "read -rp 'Lead token: ' AEW_LEAD_TOKEN",
    "read -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo \"$AEW_LEAD_TOKEN\"",  # hidden, then shown
    "${env:AEW_LEAD_TOKEN} = 'abc'", "New-Item -Path Env:AEW_LEAD_TOKEN -Value 'abc'",  # #335 quick check, R3
    "$t = Read-Host -Prompt 'Lead token'\n${env:AEW_LEAD_TOKEN} = $t",  # #335's second quick check, Q3
])
def test_a_value_typed_where_it_shows_or_made_persistent_is_an_ask(text):
    assert found(Output(site="unit", text=text), "O-SECRET") == ["asks to set AEW_LEAD_TOKEN"]


@pytest.mark.parametrize("text", [
    "$env:AEW_LEAD_TOKEN = $(Read-Host 'Lead token' -MaskInput)",
    "$s = Read-Host 'Lead token' -AsSecureString; $env:AEW_LEAD_TOKEN = $s",  # no plain text reaches the variable
    "[Environment]::SetEnvironmentVariable('AEW_LEAD_TOKEN', $null, 'User')",  # clearing it
    "New-Item -Path Env:AEW_LEAD_TOKEN -Value $s",  # from a variable
    "read -rsp 'Lead token: ' AEW_LEAD_TOKEN",
])
def test_the_masked_and_clearing_forms_are_no_ask(text):
    assert found(Output(site="unit", text=text), "O-SECRET") == []


# #335 review, F3: the form answers an ask to set the credential for this session, and no hand-over.
@pytest.mark.parametrize("ask", [
    "Paste AEW_LEAD_TOKEN into the worker's chat, and set it here too:",
    "Copy AEW_LEAD_TOKEN to the worker, then set it in your own shell:",
    "Pass AEW_LEAD_TOKEN to each subagent you start. To set it:",
    "Paste your invocation token into the worker's prompt. The Lead's goes in like this:",
])
def test_the_form_below_does_not_excuse_a_hand_over(ask):
    assert found(Output(site="unit", text=f"{ask}\n  bash: {HIDDEN_BASH}"), "O-SECRET")
    assert found(Output(site="unit", text=f"{ask} `{HIDDEN_BASH}`"), "O-SECRET")  # nor on the same line


def test_the_form_written_over_two_lines_in_one_block_passes():
    """#335 review, F4: the hidden read on one line and the export on the next is the same safe path."""
    two = "```sh\nread -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo\nexport AEW_LEAD_TOKEN\n```"
    assert found(Output(site="unit", text=two), "O-SECRET") == []
    unmasked = "```sh\nread -rp 'Lead token: ' AEW_LEAD_TOKEN; echo\nexport AEW_LEAD_TOKEN\n```"
    assert found(Output(site="unit", text=unmasked), "O-SECRET")
    split = "```sh\nread -rsp 'Lead token: ' AEW_LEAD_TOKEN; echo\n```\n```sh\nexport AEW_LEAD_TOKEN\n```"
    assert found(Output(site="unit", text=split), "O-SECRET")  # one block only: a fence ends it
    # one command a line, the read anywhere earlier in the block (#335 quick check, R3)
    three = "```sh\naew status > status.txt\nread -rsp 'Lead token: ' AEW_LEAD_TOKEN\necho\nexport AEW_LEAD_TOKEN\n```"
    assert found(Output(site="unit", text=three), "O-SECRET") == []
    shown = "```sh\nread -rsp 'Lead token: ' AEW_LEAD_TOKEN\necho \"$AEW_LEAD_TOKEN\"\nexport AEW_LEAD_TOKEN\n```"
    assert found(Output(site="unit", text=shown), "O-SECRET")  # shown between the read and the export


@pytest.mark.parametrize("text", [
    "Type `aew status` to see the token's state.", "Set the token's expiry in the config.",
    "Copy the credential's name.", "Pass the tokens' types to the check.",
])
def test_a_possessive_of_something_other_than_the_value_is_no_ask(text):
    """#335 review, F4: the possessive passes only before the nouns the bare word itself does not ask with."""
    assert found(Output(site="unit", text=text), "O-SECRET") == []


@pytest.mark.parametrize("text", [
    "Paste the token's value here.", "Paste the token's secret here.", "Copy the credential’s text into the box.",
    "Enter the token's string.", "Type the credential's characters.",
])
def test_a_possessive_that_is_the_value_still_asks(text):
    """`main` caught each of these, and so does this rule (a possessive is a word boundary)."""
    assert found(Output(site="unit", text=text), "O-SECRET"), text


def test_only_typing_or_entering_is_answered_by_a_prompt():
    """#335 review, F3: a prompt that shows nothing answers "type it there", not "paste" or "pass it there"."""
    assert found(Output(site="unit", text="Enter your token at the hidden prompt."), "O-SECRET") == []
    assert found(Output(site="unit", text="Type your token at the hidden prompt."), "O-SECRET") == []
    for text in ("Pass the token at the hidden prompt.", "Paste the token at the hidden prompt."):
        assert found(Output(site="unit", text=text), "O-SECRET"), text


# #335 review, F5: what O-SECRET does not catch, and what it still gets wrong, each pinned so a change to either is
# seen. Named in the pull request's "what this doesn't catch".
LIMITS = {
    "the hand path's placeholder line": ("AEW_INVOCATION_TOKEN=<credential> aew check run unit", False),
    "provide": ("Provide AEW_LEAD_TOKEN.", False),
    "a value from a file": ("AEW_LEAD_TOKEN=$(cat token.txt) aew status", False),
    "send": ("Send the token to the Lead.", False),
    "share": ("Share your token with the worker.", False),
    "include": ("Include the token in the request.", False),
    "give, left out on purpose": ("Give the worker your token.", False),
    "put, left out on purpose": ("Put AEW_LEAD_TOKEN in your profile.", False),
    "add, left out on purpose": ("Add AEW_LEAD_TOKEN to your ~/.bashrc.", False),
    "--token in plain prose": ("Use --token abc.", False),
    "--token in an unfenced command line": ("aew --token abc lead session", False),
    "--token from a pipe": ("echo abc | aew lead session --token -", False),
    "set as a participle": ("Re-run with AEW_LEAD_TOKEN set.", False),
    "a pronoun for the credential": ("If you have no token, ask the operator, then paste it.", False),
    # with no punctuation, filler alone stays in a negator's reach (recall first's own misses; #335's third quick
    # check, T5)
    "a run-on after a prohibition": ("AEW can't you must set AEW_LEAD_TOKEN yourself.", False),
    "a run-on after a plain negator": ("The shell has no session you set AEW_LEAD_TOKEN.", False),
    "a run-on after a refusing verb": ("Ignore the warning you must set AEW_LEAD_TOKEN.", False),
    "a backtick straight after the negator": ("AEW can't`you must set AEW_LEAD_TOKEN yourself.", False),
    "one set read as a noun": ("If you don't have one set AEW_LEAD_TOKEN first.", False),
    "an apostrophe joining the lead to the ask": ("The shell has no session'you must set AEW_LEAD_TOKEN.", False),
    # false positives `main` shares (the third quick check's side-effect texts)
    "an assignment in a code span under set (false positive)": (
        "Never set `AEW_LEAD_TOKEN=abc` or paste the token.", True),
    "no flag to set with (false positive)": ("There is no `--token` flag to set AEW_LEAD_TOKEN with.", True),
    "don't you dare (false positive)": ("Don't you dare paste the token.", True),
    "a name across a comma (false positive)": ("Copy the file, and AEW_LEAD_TOKEN stays where it is.", True),
    "a bare word joined by and (false positive)": ("Pass the tests and the token is renewed.", True),
    # punctuation ends a prohibition's reach, so a prohibition written with an aside asks (recall first; #335's
    # second quick check, the Lead's call)
    "a comma after a prohibition (false positive)": ("Never, ever paste the token.", True),
    "a comma-closed aside (false positive)": ("Do not, under any circumstances, set AEW_LEAD_TOKEN.", True),
    "a comma-closed aside after never (false positive)": ("Never, under any circumstances, paste the token.", True),
    "a comma-closed second negator (false positive)": (
        "AEW does not ask you, and will never ask you, to paste the token.", True),
    "please between commas (false positive)": ("Do not, please, paste the token.", True),
    "a bracketed aside (false positive)": ("Never (under any circumstances) paste the token into a prompt.", True),
    "a spaced dash pair (false positive)": ("Never — and I mean never — paste the token into a chat.", True),
    "an unspaced dash pair (false positive)": ("Never—ever—paste the token.", True),
    "a spaced dash pair after do not (false positive)": ("Do not — ever — set AEW_LEAD_TOKEN.", True),
    "a bracketed intensifier (false positive)": ("Never (ever) paste the token.", True),
    "a repeated never between commas (false positive)": ("Never, simply never, paste the token.", True),
    "an aside inside joined asks (false positive)": ("Never copy it (by mistake) or paste the token.", True),
    "a plain negator between dashes (false positive)": ("Never – not even once – paste the token into a chat.", True),
    "no need for you to (false positive)": ("There is no need for you to copy the token anywhere.", True),
    "a passive hand-on, be asked to (false positive)": ("You will never be asked to type the token in chat.", True),
    "a bare export with no value (false positive)": ("export AEW_LEAD_TOKEN", True),
    "text about the rule, naming the credential (false positive)": (
        "O-SECRET fires on an ask to set AEW_LEAD_TOKEN.", True),
    "text about the rule, with the bare word (false positive)": (
        "The rule O-SECRET judges whether text asks to set a credential.", True),
}


@pytest.mark.parametrize("limit", list(LIMITS))
def test_each_named_limit_of_o_secret_is_as_stated(limit):
    text, fires = LIMITS[limit]
    assert bool(found(Output(site="unit", text=text), "O-SECRET")) is fires, text


def test_the_plane_limit_a_refusal_a_lead_model_reads_is_judged_as_the_operators():
    """#335 review, F5: the prompt excuse holds off the model plane, but the capture judges every CLI output on the
    operator plane (`capture.cli_outputs`), so a refusal telling a Lead model to type at a hidden prompt passes."""
    refusal = json.dumps({"ok": False, "error": {"code": "USAGE", "message": "Type your token at the hidden prompt."}})
    [output] = capture.cli_outputs(["lead", "session"], "", refusal)
    assert output.plane == OPERATOR and not found(output, "O-SECRET")
    assert found(Output(site="unit", plane=MODEL, text="Type your token at the hidden prompt."), "O-SECRET")


def test_the_products_own_refusals_show_the_safe_path_and_read_as_no_ask():
    """`checkpoint|USAGE`, `lead session|USAGE`, `map generate|USAGE` and `opencode|USAGE`: the refusal is the
    sanctioned path, the ask with its hidden-prompt forms on the lines below. The rule changed, not the refusal, which
    stays as useful as it was (the operator: a gate that refuses the safe path is a defect)."""
    from aew import lead_credential

    told = lead_credential.how_to_set()
    assert "set AEW_LEAD_TOKEN" in told and "read -rsp" in told  # what it has always said
    assert found(Output(site="unit", text=told), "O-SECRET") == []
    message = str(lead_credential.token_value_refusal(lead_session=False))
    assert found(Output(site="unit", text=message), "O-SECRET") == []


def test_an_ask_with_the_form_on_the_next_line_passes_and_each_near_miss_does_not():
    fenced = f"{ASK}\n```sh\n{HIDDEN_BASH}\n```"
    blank = f"{ASK}\n\n  bash: {HIDDEN_BASH}"
    bare = f"Set your token:\n  bash: {HIDDEN_BASH}"
    for text in (f"{ASK}\n{HIDDEN_BASH}", fenced, blank, bare):
        assert found(Output(site="unit", text=text), "O-SECRET") == [], text
    for miss, snippet in NEAR_MISSES.items():
        assert found(Output(site="unit", text=f"{ASK}\n{snippet}"), "O-SECRET"), miss
    other = HIDDEN_BASH.replace("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN")
    assert found(Output(site="unit", text=f"{ASK}\n{other}"), "O-SECRET")  # the form for another credential
    assert found(Output(site="unit", text=f"{ASK}\nthen wait\n{HIDDEN_BASH}"), "O-SECRET")  # not the next line
    assert found(Output(site="unit", text=f"{ASK}\n{HIDDEN_BASH}\n$env:AEW_LEAD_TOKEN = 'abc'"), "O-SECRET")


# ---------------------------------------------------------------------------------------------- O-CMD and --fields

def _hint(text: str) -> Output:
    return Output(site="unit", payload={"next_actions": [text]})


def test_a_fields_line_parses_through_the_real_expansion(monkeypatch):
    """`aew invoke cancel ... --fields - <<'EOF'` with `reason:` in its body parses as printed
    (`printed_commands.py` proves it), and read `--reason` as missing only because the body was dropped. Judged on any
    thread, so it reads nothing from this process's stdin."""
    from aew.harness.contract import fields_block, fields_command

    class NoStdin:
        def read(self, *_: object) -> str:
            raise AssertionError("stdin was read")

    monkeypatch.setattr(sys, "stdin", NoStdin())
    command = "aew invoke cancel INV-0001 --expect-rev <revision from aew status>"
    assert found(_hint(fields_command(command, "reason", "operator asked")), "O-CMD") == []
    empty = found(_hint(fields_block(command, {})), "O-CMD")
    assert len(empty) == 1 and "--reason" in empty[0]  # what the body lacks is still missing
    unknown = found(_hint(fields_command(command, "reasons", "x")), "O-CMD")
    assert len(unknown) == 1 and "did you mean --reason" in unknown[0]  # the CLI's own refusal of the body
    credential = found(_hint(fields_command(command, "token", "x")), "O-CMD")
    assert len(credential) == 1 and "a credential never goes through --fields" in credential[0]


def test_a_fields_line_with_no_body_shown_answers_for_its_command_only():
    assert found(_hint("aew invoke cancel INV-0001 --fields - <<'EOF'"), "O-CMD") == []
    assert found(_hint("aew invoke cancle INV-0001 --fields - <<'EOF'"), "O-CMD")
    assert found(_hint("aew invoke cancel INV-0001 --bogus 1 --fields -"), "O-CMD")


def test_a_heredocs_body_is_not_read_as_commands():
    text = "```sh\naew invoke cancel INV-0001 --fields - <<'EOF'\nreason: 'x'\naew not a command\nEOF\naew status\n```"
    assert list(rules.prose_commands(text)) == ["aew invoke cancel INV-0001 --fields - <<'EOF'", "aew status"]
    unclosed = "```sh\naew invoke cancel INV-0001 --fields - <<'EOF'\nreason: 'x'\n```"
    assert [(s.text, s.body) for s in rules.suggestions(_hint(unclosed))] == [
        ("aew invoke cancel INV-0001 --fields - <<'EOF'", None)]


def test_the_refusal_that_offers_print_credential_parses(monkeypatch):
    """`dashboard open`, `dashboard serve` and `lead acquire` shared one line, reproduced for all three: its `<command>`
    sat in the subcommand slot, where no placeholder parses. It now names the option."""
    import argparse

    from aew.cli import credentials
    from aew.errors import UsageError

    monkeypatch.setattr(credentials, "issues_credential", lambda args: True)
    monkeypatch.setattr(credentials, "_open_terminal", lambda: None)
    with pytest.raises(UsageError) as refused:
        credentials.before(argparse.Namespace())
    message = str(refused.value)
    assert "--print-credential" in message
    assert found(Output(site="unit", refusal={"code": "USAGE", "message": message}), "O-CMD") == []


def test_raising_or_keeping_a_mode_needs_no_label_and_reads_none(tmp_path, monkeypatch):
    monkeypatch.setitem(modes.MODES, "O-CMD", modes.ENFORCE)
    assert _lowering(tmp_path, monkeypatch, None, values='"O-CMD": SHADOW, "O-IDS": SHADOW') == (0, [])
    assert _lowering(tmp_path, monkeypatch, None, values='"O-CMD": ENFORCE') == (0, [])


def test_a_base_modes_file_that_cannot_be_read_fails_rather_than_passing(tmp_path, capsys):
    ratchet = _ratchet()
    bad = tmp_path / "modes-base.py"
    bad.write_text("this is not python\n", encoding="utf-8")
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    assert ratchet.main([str(_reports(tmp_path)), "--event", "pull_request", "--allowlist", str(head),
                         "--base-modes", str(bad)]) == 1
    assert "FAIL the base's modes.py cannot be read" in capsys.readouterr().out


def test_a_mode_is_compared_only_on_a_pull_request(tmp_path, monkeypatch):
    ratchet = _ratchet()
    monkeypatch.setattr(ratchet, "live_labels", lambda repo, pr: pytest.fail("no pull request to read"))
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    assert ratchet.main([str(_reports(tmp_path)), "--event", "push", "--allowlist", str(head),
                         "--base-modes", str(_base_modes(tmp_path, '"O-CMD": ENFORCE'))]) == 0
