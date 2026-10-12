"""D2's rules, each proved differentially: an input that violates the rule is caught and a clean one passes, with the
inputs read from the product (the live ``aew`` parser, ``contract.TOOLS``, ``CREDENTIAL_ENV``, ``agentenv``) rather
than from hand lists (docs/implementation/vertical-uat.md §8)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

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
    through its pack. The pack's own line, as the product renders it, is caught on the model plane."""
    pack = next(text for source, _, text in static.texts(guides()) if source == "pack:implementer")
    line = next(ln for ln in pack.splitlines() if "AEW_INVOCATION_TOKEN=" in ln)
    assert found(Output(site="unit", plane=plane, text=line), "O-SECRET") == ["asks to set AEW_INVOCATION_TOKEN"]
    assert found(Output(site="unit", plane=plane, text="Ask the operator to set AEW_LEAD_TOKEN."), "O-SECRET")
    assert not found(Output(site="unit", plane=plane, text="This session never holds AEW_LEAD_TOKEN."), "O-SECRET")
    key = f"O-SECRET {static.STATIC}pack:implementer|asks to set AEW_INVOCATION_TOKEN"
    assert key in allowed.load()  # listed until the product drops the line; its key stays stable


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
    """U29's shape, from the product itself: `aew lead session` without a credential asks the operator to set it.
    A clean answer of the same command family raises neither rule."""
    from conftest import run_aew

    assert run_aew("init", cwd=repo).returncode == 0
    argv = ["-C", str(repo), "lead", "session", "--", "true"]
    res = run_aew(*argv)
    outputs = capture.cli_outputs(argv, res.stdout, res.stderr)
    assert [o.site for o in outputs] == ["cli:aew lead session|USAGE"]
    assert {"O-WORDS", "O-SECRET"} <= {f.rule for f in rules.check(outputs[0])}
    assert str(repo) not in outputs[0].site  # a key never carries message text
    # U29's own site: `aew opencode` without a credential refuses before anything starts. Run through `run_aew`, so
    # the session's capture sees this site in every run (tests start a live `aew opencode` through Popen, unseen).
    # A stand-in OpenCode that reports a tested version, so the version check passes wherever OpenCode is absent.
    from aew.harness.opencode import capabilities

    binary = repo.parent / "opencode.py"
    binary.write_text(f"print({capabilities.TESTED_VERSIONS[0]!r})\n", encoding="utf-8")
    opened = run_aew("-C", str(repo), "opencode", env={"AEW_OPENCODE_BIN": str(binary)})
    refusal = capture.cli_outputs(["-C", str(repo), "opencode"], opened.stdout, opened.stderr)
    assert [o.site for o in refusal] == ["cli:aew opencode|USAGE"]
    assert "asks to set AEW_LEAD_TOKEN" in [f.detail for f in rules.check(refusal[0]) if f.rule == "O-SECRET"]
    shown = run_aew("-C", str(repo), "lead", "show")
    clean = capture.cli_outputs(["-C", str(repo), "lead", "show"], shown.stdout, shown.stderr)
    assert [o.site for o in clean] == ["cli:aew lead show|result"]
    assert not {"O-WORDS", "O-SECRET"} & {f.rule for f in rules.check(clean[0])}


def test_the_capture_plugin_keys_typed_tool_results_by_tool_and_code():
    ok = capture.tool_output("status", {}, {"ok": True, "stopped": None, "projection": {}})
    refused = capture.tool_output("integration_publish", {"work_id": "T-1"},
                                  {"ok": False, "stopped": {"error": {"code": "GATE_UNSATISFIED", "message": "m"}}})
    assert ok.site == "tool:status|result" and ok.refusal is None and ok.plane == MODEL
    assert refused.site == "tool:integration_publish|GATE_UNSATISFIED" and refused.refusal["code"] == "GATE_UNSATISFIED"


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


def test_main_fails_on_a_stale_entry_of_an_enforced_rule_and_a_pull_request_never_does():
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
])
def test_a_worker_that_goes_down_without_its_findings_is_a_capture_error(output, error, lost):
    """Review of #218, G1: `pytest_testnodedown` merges what a worker handed on, and counts a worker that died, or
    handed nothing on, as a capture error."""
    plugin = capture.CapturePlugin(None, None)  # type: ignore[arg-type]
    node = type("Node", (), {"workeroutput": output, "gateway": type("G", (), {"id": "gw3"})()})()
    plugin.pytest_testnodedown(node, error)
    snapshot = plugin.recorder.as_dict()
    assert bool(snapshot["errors"]) is lost
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


def test_write_refuses_to_add_keys_unless_introducing_and_rescans_the_static_texts(tmp_path, capsys):
    """Review of #218, G2: `--write` may only shrink the list (no `--introduce`), and `--static` rescans the texts."""
    from pathlib import Path

    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render(set()), encoding="utf-8")
    observed = {"O-CMD cli:aew x|result": {"rule": "O-CMD", "site": "cli:aew x|result", "count": 1}}
    reports = _reports(tmp_path, findings=json.dumps({"schema": capture.SCHEMA, "outputs": 1, "findings": observed,
                                                      "errors": {}}))
    assert ratchet.main([str(reports), "--write", "--allowlist", str(head)]) == 1
    assert "refused: 1 key(s) the allow-list lacks" in capsys.readouterr().err
    assert allowed.parse(head.read_text(encoding="utf-8"))[0] == set()
    guides = Path(__file__).resolve().parents[2] / "docs" / "guides"
    rewrite = [str(reports), "--write", "--introduce", "--static", str(guides), "--allowlist", str(head)]
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


def test_a_pull_requests_partial_selection_reports_nothing_stale(tmp_path, capsys):
    """Review of #218, G2: a pull request runs only its tier's lanes, so a listed key it did not observe proves
    nothing there; main and nightly, which run everything, report it."""
    ratchet = _ratchet()
    head = tmp_path / "allowed.yaml"
    head.write_text(allowed.render({"O-CMD cli:aew x|result"}), encoding="utf-8")
    reports = _reports(tmp_path)
    assert ratchet.main([str(reports), "--event", "pull_request", "--allowlist", str(head)]) == 0
    assert "no longer observed" not in capsys.readouterr().out
    assert ratchet.main([str(reports), "--event", "push", "--allowlist", str(head)]) == 0  # shadow: reported only
    assert "1 stale (allow-listed, no longer observed)" in capsys.readouterr().out


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
    observed = {f.key for f in static.scan(guides())}
    listed = {k for k in allowed.load() if allowed.is_static(k)}
    verdict = allowed.decide(observed, listed, stale_scope="static")
    assert verdict.ok, "\n".join(allowed.report(verdict))
    enforced = {r: modes.ENFORCE for r in modes.RULES}
    assert allowed.decide(observed | {"O-IDS static:guide|aew x --expect-rev N"}, listed, stale_scope="static",
                          mode_of=enforced).failing == ["O-IDS static:guide|aew x --expect-rev N"]
    dropped = sorted(listed)[0]
    assert allowed.decide(observed - {dropped}, listed, stale_scope="static", mode_of=enforced).failing == [dropped]


def test_the_committed_allow_list_is_well_formed_and_sorted():
    text = allowed.PATH.read_text(encoding="utf-8")
    keys, residuals = allowed.parse(text)
    assert keys and not residuals
    assert text == allowed.render(keys, residuals.values())
    assert all(" " in k and k.split(" ", 1)[0] in modes.RULES for k in keys)
