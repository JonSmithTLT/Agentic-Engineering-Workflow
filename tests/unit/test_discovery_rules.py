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
            if action.dest in rules.ID_DESTS and action.option_strings and action.nargs != 0:
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

@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_o_env_requires_the_statement_generated_from_the_allowlist(platform):
    from aew.harness import agentenv

    keep = agentenv.WINDOWS_KEEP if platform == "win32" else agentenv.POSIX_KEEP
    def statement(names: list[str]) -> str:
        return (f"{rules.ENV_MARK}: only {', '.join(names)} and PATH are kept. To give a check a variable, name it "
                "in the harness profile's provider_env.")

    assert rules.o_env(statement(sorted(keep)), platform) == []
    dropped = sorted(keep)[0]
    assert rules.o_env(statement(sorted(keep - {dropped})), platform) == [dropped]
    assert "the scrubbed-environment statement" in rules.o_env("nothing about checks", platform)


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


def test_the_capture_plugin_never_changes_a_test_outcome(monkeypatch):
    """A defect in judging is counted and reported; it never raises into the test that produced the output."""
    def boom(*_a, **_k):
        raise RuntimeError("defect")

    recorder = capture.Recorder()
    monkeypatch.setattr(rules, "check", boom)
    recorder.record(Output(site="x", text="`aew status`"))
    assert recorder.errors == {"RuntimeError: defect": 1} and not recorder.findings
    monkeypatch.undo()
    recorder.record(Output(site="x", text="`aew harness runs`"))
    assert "O-CMD x" in recorder.findings


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


def test_the_allow_list_may_only_shrink_unless_the_operator_accepts_a_residual(tmp_path):
    discovery_ratchet = _ratchet()
    base = tmp_path / "base.yaml"
    head = tmp_path / "head.yaml"
    base.write_text(allowed.render({"O-IDS cli:aew status|result"}), encoding="utf-8")
    reports = tmp_path / "reports"
    reports.mkdir()
    head.write_text(allowed.render(set()), encoding="utf-8")
    args = [str(reports), "--event", "pull_request", "--allowlist", str(head), "--base-allowlist", str(base)]
    assert discovery_ratchet.main(args) == 0  # shrinking is always allowed
    head.write_text(allowed.render({"O-IDS cli:aew status|result", "O-CMD cli:aew x|result"}), encoding="utf-8")
    assert discovery_ratchet.main(args) == 1  # growth fails whatever the mode
    residual = [{"rule": "O-CMD", "site": "cli:aew x|result", "decision": "operator, 2026-10-12", "reason": "r"}]
    head.write_text(allowed.render({"O-IDS cli:aew status|result", "O-CMD cli:aew x|result"}, residual),
                    encoding="utf-8")
    assert discovery_ratchet.main(args) == 0
    no_base = [str(reports), "--event", "pull_request", "--allowlist", str(head)]
    assert discovery_ratchet.main(no_base) == 0  # introducing D2: the base has no list


def test_the_committed_allow_list_is_well_formed_and_sorted():
    text = allowed.PATH.read_text(encoding="utf-8")
    keys, residuals = allowed.parse(text)
    assert keys and not residuals
    assert text == allowed.render(keys, residuals.values())
    assert all(" " in k and k.split(" ", 1)[0] in modes.RULES for k in keys)
