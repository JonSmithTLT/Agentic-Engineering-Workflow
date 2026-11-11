"""`aew init`'s first configuration, the flags as parsed and the text they become (register E119; the designer's ruling
of 2026-11-03, §1). Nothing here writes: ``tests/integration/test_init_first_configuration.py`` runs the command."""

from __future__ import annotations

import argparse
import ast
import re
import shlex
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import printed_commands as P
import pytest
import yaml

import aew
from aew import lead_credential
from aew.cli.main import build_parser
from aew.engine import first_configuration as FC
from aew.engine.base import check_policy_bytes
from aew.errors import UsageError, ValidationFailed
from aew.harness import contract as K
from aew.harness import lead_broker
from aew.harness.containment import netns
from aew.harness.models import ModelIdRefused
from aew.policy import execution as X


def parse(**flags: Any) -> FC.FirstConfiguration:
    configuration = FC.from_flags(**{"check_command": None, "check_timeout": None, "model": None, "provider": None,
                                     **flags})
    assert configuration is not None
    return configuration


def init_parser() -> argparse.ArgumentParser:
    root = build_parser(recall_search=True, coordination_reads=True)
    subs = next(a for a in root._actions if isinstance(a, argparse._SubParsersAction))
    return subs.choices["init"]


# ---------------------------------------------------------------------------------------------- the check command


@pytest.mark.parametrize(("text", "argv"), [
    ("{python} -m pytest -q", ["{python}", "-m", "pytest", "-q"]),
    ("make test", ["make", "test"]),
    ("pytest -k 'a or b'", ["pytest", "-k", "a or b"]),
    ('pytest -k "a or b"', ["pytest", "-k", "a or b"]),
    ("pytest -k 'a|b;c<d>e&&f'", ["pytest", "-k", "a|b;c<d>e&&f"]),  # quoted, so an argument: no operator is bare
    ('pytest -k "x|y"', ["pytest", "-k", "x|y"]),
    ("sh -c 'FOO=1 make && make lint'", ["sh", "-c", "FOO=1 make && make lint"]),
    (r"{python} -c 'print(1)\n'", ["{python}", "-c", r"print(1)\n"]),  # a backslash inside single quotes is kept
    ("run --opt=value", ["run", "--opt=value"]),  # an assignment that doesn't lead is an argument
    ("a & b", ["a", "&", "b"]),  # the ruling's list has no single `&`
])
def test_a_check_command_is_split_as_posix_with_no_shell(text, argv):
    assert FC.parse_check_command(text) == argv


@pytest.mark.parametrize(("text", "reason", "names"), [
    ("", "check_command_empty", "empty"),
    ("   ", "check_command_empty", "empty"),
    ("''", "check_command_empty", "empty"),
    ('pytest "unclosed', "check_command_unparseable", "does not parse"),
    ("pytest 'unclosed", "check_command_unparseable", "does not parse"),
    ("make && make lint", "check_command_shell", "sh -c"),
    ("make || true", "check_command_shell", "sh -c"),
    ("make | tee out", "check_command_shell", "sh -c"),
    ("make ; make lint", "check_command_shell", "sh -c"),
    ("make < in", "check_command_shell", "sh -c"),
    ("make > out", "check_command_shell", "sh -c"),
    ("make&&make", "check_command_shell", "sh -c"),  # bare, with no space around it
    ("make;", "check_command_shell", "sh -c"),
    ("FOO=1 make", "check_command_shell", "sh -c"),
    ("'FOO=1' make", "check_command_shell", "sh -c"),
    ("A_b9=x", "check_command_shell", "sh -c"),
    (r"C:\venv\python -m pytest", "check_command_backslash", "`/`"),
    (r'"C:\venv\python" -m pytest', "check_command_backslash", "{python}"),
    (r"a\ b", "check_command_backslash", "`/`"),
    ("a\\", "check_command_backslash", "`/`"),
])
def test_a_check_command_that_would_pin_something_broken_is_refused_naming_what_to_do(text, reason, names):
    with pytest.raises(UsageError) as refused:
        FC.parse_check_command(text)
    assert refused.value.details["reason"] == reason and names in refused.value.message


@pytest.mark.parametrize("code", [r"p.write_text(p.read_text() + 'built\n')", "open('out', 'w').write('x')", "a'b\"c"])
def test_a_command_quoted_as_a_shell_would_comes_back_whole_with_its_backslash(code):
    """`shlex.join` closes and reopens its single quotes around a quote in the text. A backslash stays inside them, so
    the driver's stamp check, which only the vertical lane runs, isn't refused."""
    argv = ["{python}", "-c", code]
    assert FC.parse_check_command(shlex.join(argv)) == argv


def test_a_refused_operator_names_a_shell_form_that_itself_parses():
    with pytest.raises(UsageError) as refused:
        FC.parse_check_command("echo 'it''s' && make")
    named = refused.value.message.split("Name the shell yourself: ", 1)[1]
    assert FC.parse_check_command(named)[:2] == ["sh", "-c"]


def named_shell_form(text: str) -> str:
    with pytest.raises(UsageError) as refused:
        FC.parse_check_command(text)
    return refused.value.message.split("Name the shell yourself: ", 1)[1]


@pytest.mark.parametrize("interpreter", [r"C:\Users\A Person\venv\Scripts\python.exe", "/home/a b/venv/bin/python"])
def test_the_shell_form_a_refusal_names_still_finds_python_once_the_shell_reads_it(interpreter):
    """Review of #329, F5: the check runner expands `{python}` inside the string, and then `sh` reads it. POSIX word
    splitting, which `sh` does and `shlex` follows, must give back the whole path, backslashes and space included."""
    argv = FC.parse_check_command(named_shell_form("{python} -m pytest && make"))
    assert argv == ["sh", "-c", '"{python}" -m pytest && make']
    expanded = argv[2].replace("{python}", interpreter)  # as `policy/checks.py` expands it
    assert shlex.split(expanded)[0] == interpreter


@pytest.mark.parametrize(("text", "script"), [
    ("make && make lint", "make && make lint"),  # nothing to quote
    ("FOO=1 {python} -m pytest", 'FOO=1 "{python}" -m pytest'),
    ('"{python}" -m pytest && make', '"{python}" -m pytest && make'),  # its quotes already there, not doubled
    ("'{python}' -m pytest && make", "'{python}' -m pytest && make"),
    ("{python} a && {python} b", '"{python}" a && "{python}" b'),
])
def test_the_shell_form_quotes_only_a_python_no_quote_touches(text, script):
    assert FC.parse_check_command(named_shell_form(text)) == ["sh", "-c", script]


# ---------------------------------------------------------------------------------------------- what goes with what


def test_no_flag_at_all_is_no_first_configuration():
    assert FC.from_flags(check_command=None, check_timeout=None, model=None, provider=None) is None


@pytest.mark.parametrize(("flags", "reason"), [
    ({"check_timeout": "300"}, "check_timeout_alone"),
    ({"check_timeout": "300", "model": "openai/m"}, "check_timeout_alone"),
    ({"provider": "openai"}, "provider_alone"),
    ({"provider": "openai", "check_command": "make"}, "provider_alone"),
])
def test_a_flag_that_only_goes_with_another_is_refused_alone(flags, reason):
    with pytest.raises(UsageError) as refused:
        parse(**flags)
    assert refused.value.details["reason"] == reason


@pytest.mark.parametrize(("text", "value"), [("300", 300), ("1.5", 1.5), ("300.0", 300), ("0", 0), ("-5", -5)])
def test_a_timeout_is_a_number_and_a_whole_one_stays_whole(text, value):
    """Above zero is the schema's rule, checked with the bytes (`check_policy_bytes`), so 0 and -5 get past here."""
    parsed = parse(check_command="make", check_timeout=text)
    assert parsed.timeout_s == value and type(parsed.timeout_s) is type(value)
    assert yaml.safe_load(parsed.files()[FC.CHECKS_REL])["checks"]["unit"]["timeout_s"] == value


@pytest.mark.parametrize("text", ["abc", "", "nan", "inf", "-inf"])
def test_a_timeout_that_is_no_number_is_refused(text):
    with pytest.raises(UsageError) as refused:
        parse(check_command="make", check_timeout=text)
    assert refused.value.details["reason"] == "check_timeout_not_a_number"


@pytest.mark.parametrize("timeout", ["0", "-5"])
def test_the_schema_refuses_a_timeout_not_above_zero(timeout):
    text = parse(check_command="make", check_timeout=timeout).files()[FC.CHECKS_REL]
    with pytest.raises(ValidationFailed):
        check_policy_bytes("checks", text.encode(), source="planted")


# ---------------------------------------------------------------------------------------------- the provider rule


@pytest.mark.parametrize("provider", sorted(netns.PROVIDER_KEY_ENV))
def test_a_known_provider_that_needs_a_key_names_its_variable_whichever_flag_named_it(provider):
    want = (netns.PROVIDER_KEY_ENV[provider],)
    assert parse(model=f"{provider}/m").provider_env == want
    assert parse(model="m", provider=provider).provider_env == want
    assert parse(model=f"{provider}/m", provider=provider).provider_env == want


def test_opencode_writes_its_key_variable_as_every_known_provider_does():
    """The operator, 2026-11-06: AEW does not use OpenCode's free models, so opencode needs its key like any other
    provider (a launch whose provider would get no key is refused: `provider_key_missing`). Right: its variable is
    written, whichever flag named it. Wrong (the rule this replaces): nothing written and a note saying none is
    needed. Missing: no note at all."""
    for parsed in (parse(model="opencode/big"), parse(model="big", provider="opencode")):
        assert parsed.provider_env == ("OPENCODE_API_KEY",)
        doc = yaml.safe_load(parsed.files()[X.REL_PATH])
        assert doc["provider_env"] == ["OPENCODE_API_KEY"]
        assert "provider_note" not in parsed.report()
        assert parsed.report()["provider_env"] == ["OPENCODE_API_KEY"]


def test_an_unknown_provider_is_refused_naming_the_route_that_still_works():
    """Review of #329, F1: a successful init has pinned, so `aew init` is refused by then. The refusal, which has
    written nothing, is the one text where it is still a step."""
    with pytest.raises(UsageError) as refused:
        parse(model="fakeprov/m")
    assert "`aew init` without these flags" in refused.value.message and K.HELD_SEAT in refused.value.message


@pytest.mark.parametrize("flags", [{"model": "fakeprov/m"}, {"model": "m", "provider": "vuatprov"},
                                   {"model": "OpenAI/m"}, {"model": "router/vendor/m"}])
def test_an_unknown_provider_is_refused_naming_the_hand_edit_route(flags):
    """An alpha limit: a contained Linux launch would refuse it too. The driver's fake providers are unknown here."""
    with pytest.raises(UsageError) as refused:
        parse(**flags)
    assert refused.value.details["reason"] == "unknown_provider"
    assert "aew lead acquire --expect-rev 0" in refused.value.message
    assert "containment.network.upstreams" in refused.value.message


@pytest.mark.parametrize(("flags", "code"), [
    ({"model": "bare"}, "model_id_no_provider"),
    ({"model": "a b/c"}, "model_id_malformed"),
    ({"model": ""}, "model_id_malformed"),
    ({"model": "openai/"}, "model_id_malformed"),
    ({"model": "<provider>/m"}, "model_id_malformed"),
    ({"model": "openai/MODEL_ID"}, "model_id_malformed"),
    ({"model": "anthropic/m", "provider": "openai"}, "model_id_provider_conflict"),
])
def test_the_model_is_refused_by_the_parser_launch_uses_so_its_refusals_come_early(flags, code):
    with pytest.raises(ModelIdRefused) as refused:
        parse(**flags)
    assert refused.value.details["reason"] == code


def test_an_empty_provider_is_refused_rather_than_read_as_no_provider():
    with pytest.raises(UsageError) as refused:
        parse(model="openai/m", provider="")
    assert refused.value.details["reason"] == "provider_empty"


# ---------------------------------------------------------------------------------------------- the text


@pytest.mark.parametrize("model", ["on", "null", "123", "1.5", "~", "a:b", "#x", "@x", "-x", "x#y", "é", "'q'", '"q"',
                                   "true", "%x", "!x", "*x", "&x", "{x}", "[x]"])
def test_a_value_that_needs_quoting_comes_back_from_the_file_as_it_was_typed(model):
    """YAML's own dumper quotes it, in the commented template, and the policy's own parser reads it back."""
    parsed = parse(model=model, provider="openai")
    doc = check_policy_bytes("execution", parsed.files()[X.REL_PATH].encode(), source="planted")
    assert doc["profiles"]["default"] == {"provider": "openai", "model": model, "deadline_s": FC.DEADLINE_S,
                                          "deadline_scope": "run"}


@pytest.mark.parametrize("word", ["on", "null", "123", "a: b", "#x", "é", "x y", "{python}", "a\nb", "'", '"'])
def test_a_check_argument_that_needs_quoting_comes_back_as_it_was_typed(word):
    text = parse(check_command=shlex.join(["run", word])).files()[FC.CHECKS_REL]
    doc = check_policy_bytes("checks", text.encode(), source="planted")
    assert doc["checks"]["unit"]["command"] == ["run", word]


def test_a_flagged_execution_policy_keeps_the_templates_comments_and_changes_only_its_values():
    text = parse(model="openai/m").files()[X.REL_PATH]
    comments = [line for line in X.TEMPLATE.splitlines() if line.startswith("#")]
    assert [line for line in text.splitlines() if line.startswith("#")] == comments
    assert yaml.safe_load(text) == {**yaml.safe_load(X.TEMPLATE), "configured": True,
                                    "profiles": {"default": {"model": "openai/m", "deadline_s": FC.DEADLINE_S,
                                                             "deadline_scope": "run"}},
                                    "routing": {**yaml.safe_load(X.TEMPLATE)["routing"], "default": "default"},
                                    "provider_env": ["OPENAI_API_KEY"]}


def test_a_template_line_that_moved_fails_rather_than_writing_half_a_policy(monkeypatch):
    monkeypatch.setattr(X, "TEMPLATE", X.TEMPLATE.replace("\nprofiles: {}\n", "\nprofiles:\n  {}\n"))
    with pytest.raises(AssertionError, match="profiles"):
        parse(model="openai/m").files()


def test_the_flags_write_only_what_the_ruling_says():
    """What they never reach: `containment`, `network`, `upstreams`, `checks.*.network`, a `harness` name, and no other
    file. `unit` is the only check id."""
    parsed = parse(check_command="make test", check_timeout="60", model="openai/m", provider="openai")
    files = parsed.files()
    assert set(files) == {FC.CHECKS_REL, X.REL_PATH}
    execution = yaml.safe_load(files[X.REL_PATH])
    assert execution["harness"] == X.DEFAULT_HARNESS and set(execution) == set(yaml.safe_load(X.TEMPLATE))
    assert "containment" not in execution and "network" not in files[X.REL_PATH].split("schema:", 1)[1]
    assert execution["profiles"] == {"default": {"provider": "openai", "model": "openai/m",
                                                 "deadline_s": FC.DEADLINE_S, "deadline_scope": "run"}}  # and Run's
    checks = yaml.safe_load(files[FC.CHECKS_REL])
    assert set(checks["checks"]) == {"unit"}
    assert checks["checks"]["unit"] == {"configured": True, "command": ["make", "test"], "cwd": ".", "timeout_s": 60,
                                        "description": "set at aew init"}
    assert set(parse(check_command="make").files()) == {FC.CHECKS_REL}
    assert set(parse(model="openai/m").files()) == {X.REL_PATH}
    # A timeout left out stays the default.
    assert yaml.safe_load(parse(check_command="make").files()[FC.CHECKS_REL])["checks"]["unit"]["timeout_s"] == 900


def test_the_result_prints_the_argv_and_what_was_written():
    report = parse(check_command="{python} -m pytest", model="openai/m").report()
    assert report["check"] == {"id": "unit", "argv": ["{python}", "-m", "pytest"], "timeout_s": 900}
    assert report["model"]["harness_ref"] == "openai/m" and report["provider_env"] == ["OPENAI_API_KEY"]


# ---------------------------------------------------------------------------------------------- `next`


def printed(text: str) -> list[str]:
    """Each command `next` prints, checked as printed by the real parser (`printed_commands`)."""
    spans = [span for span, fenced in P.commands(text) if not fenced]
    for span in spans:
        P.check(span, "span")
    return spans


def test_next_with_a_check_and_a_model_that_needs_a_key():
    text = parse(check_command="make", model="anthropic/m").next_step()
    assert printed(text) == ["aew doctor", "aew opencode --acquire --provider-env ANTHROPIC_API_KEY"]
    assert "stored login" in text and "a seat already held refuses" in text


def test_next_gives_each_hidden_form_its_one_owner_has():
    """Review of #329, F4: derived, so the Windows PowerShell 5.1 form, which has no `-MaskInput`, is there too."""
    text = parse(check_command="make", model="anthropic/m").next_step()
    forms = lead_credential.forms("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    assert "Windows PowerShell 5.1" in forms  # control: the owner has it
    for shell, form in forms.items():
        assert f"{shell}: `{form}`" in text


def test_next_with_a_check_and_an_opencode_model_sets_its_key_for_workers_and_names_another_provider_for_the_lead():
    """opencode's key is for the workers: the contained Lead never relays it (its models carry addresses of their
    own), so the Lead's step names a login of another provider or `--provider-env` for one AEW relays, never
    `--provider-env OPENCODE_API_KEY`, which the Lead refuses."""
    text = parse(check_command="make", model="opencode/big").next_step()
    assert printed(text) == ["aew doctor", "aew opencode --acquire"]
    assert "Set OPENCODE_API_KEY by the hidden form" in text and "a worker reads it" in text
    assert "(`opencode auth login`)" in text and "`--provider-env NAME`" in text
    assert "--provider-env OPENCODE_API_KEY" not in text and "a seat already held refuses" in text
    assert "ANTHROPIC_API_KEY, GOOGLE_GENERATIVE_AI_API_KEY, OPENAI_API_KEY" in text


@pytest.mark.parametrize(("flags", "missing", "file"), [
    ({"check_command": "make"}, "model", X.REL_PATH),
    ({"check_command": "make", "check_timeout": "60"}, "model", X.REL_PATH),
    ({"model": "openai/m"}, "check command", FC.CHECKS_REL),
    ({"model": "opencode/m"}, "check command", FC.CHECKS_REL),
    ({"model": "m", "provider": "openai"}, "check command", FC.CHECKS_REL),
])
def test_next_with_some_flags_says_whats_missing_and_what_adding_it_takes(flags, missing, file):
    text = parse(**flags).next_step()
    assert f"no {missing}." in text and f".aew/{file}" in text
    spans = printed(text)
    assert spans[0] == "aew lead acquire --expect-rev 0" and spans[1].startswith("aew manifest adopt --reason")
    assert spans[2] == "aew opencode --acquire" and K.HELD_SEAT in text
    assert spans[3] == f"aew lead release {K.EXPECT_REV}"


# ---------------------------------------------------------------------------------------------- the seat, in each text


# The literals that name `aew lead acquire` without the seat's sentence, and why each may.
NO_SEAT_SENTENCE = {
    "commands.py": "the flagless `next`, which the ruling keeps as it always was",
    "lead_ops.py": "a takeover refused on a vacant seat: not a first step, and its reader already holds the route",
    "first_configuration.py": "`post_pin_route`: each caller adds the sentence, as the tests above and below say",
}


def shown_texts(tree: ast.AST) -> Iterator[str]:
    """Every string the program can show, whole, with each f-string value read as its source, and no docstring."""
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body
                  and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings | parts:
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(str(v.value) if isinstance(v, ast.Constant) else ast.unparse(v) for v in node.values)


def test_every_text_that_names_lead_acquire_says_it_holds_the_seat():
    """Review of #329, F3's class: an operator who follows such a text gets a held seat, which then refuses the
    `--acquire` that `aew init`'s `next` named. So the text says so, in the one sentence with the way back. Limits: the
    literal spelling `aew lead acquire`, in what `src/aew` can show (the guides are the test below); it reads no
    meaning, so an entry above stays only for the reason it gives."""
    src = Path(aew.__file__).parent
    exempt = set()
    missing = []
    for path in sorted(src.rglob("*.py")):
        for text in shown_texts(ast.parse(path.read_text(encoding="utf-8"))):
            if "aew lead acquire" not in text or "HELD_SEAT" in text:
                continue
            if path.name in NO_SEAT_SENTENCE:
                exempt.add(path.name)
            else:
                missing.append(f"{path.name}: {text[:100]}")
    assert missing == []
    assert exempt == set(NO_SEAT_SENTENCE)  # an entry with nothing left to excuse goes


@pytest.mark.parametrize("guide", ["quickstart.md", "lead-guide.md"])
def test_every_guide_section_that_names_lead_acquire_names_the_way_back(guide):
    """Review of #329, F2: classifying leaves the seat held, and `aew lead release` is what gives `--acquire` back."""
    text = (Path(aew.__file__).resolve().parents[2] / "docs" / "guides" / guide).read_text(encoding="utf-8")
    sections = [s for s in re.split(r"^#+ ", text, flags=re.M) if "aew lead acquire" in s]
    assert sections  # control: the guide still names it, or this test looks at nothing
    for section in sections:
        assert "`aew lead release`" in section and "--acquire" in section, section[:80]
        assert "holds the seat" in section, section[:80]


def test_the_refusal_on_an_initialized_project_says_what_it_takes_now():
    """Review of #329, F8: the code stays as ruled, and the message gives the way forward."""
    text = FC.already_initialized("/repo/.aew")
    assert "already an initialized AEW project" in text and K.HELD_SEAT in text
    assert ".aew/policy/checks.yaml or .aew/policy/execution.yaml" in text
    assert printed(text)[1:3] == [f"aew lead acquire {K.EXPECT_REV}",
                                  f"aew manifest adopt --reason <reason> {K.EXPECT_REV}"]


# ---------------------------------------------------------------------------------------------- where the flags are


def test_inits_option_set_is_exactly_these():
    """The invariant: none of the driver's fixtures (`harness: fake`, `containment.writable`, the fake providers, V3's
    causes, the steering extras) is a parser option, here or on any later row without changing this pin."""
    options = {o for a in init_parser()._actions for o in a.option_strings}
    assert options == {"-h", "--help", "--fields", "--project-id", "--name", "--branch", "--workspaces-root",
                       "--check-command", "--check-timeout", "--model", "--provider",
                       "--fetch-tool"}  # --fields: every leaf has it; --fetch-tool: the operator's choice of tools
    assert {a.dest for a in init_parser()._actions} >= set(FC.FLAGS)
    assert set(FC.FLAGS.values()) <= options


def test_no_sibling_command_takes_a_first_configuration_flag():
    """On `init` only: a sibling that writes after the pin is the credential-free adopt that was rejected."""
    root = build_parser(recall_search=True, coordination_reads=True)
    found = []

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        for action in parser._actions:
            found.extend((path, o) for o in action.option_strings if o in ("--check-command", "--check-timeout"))
        for sub in subs:
            for name, child in sub.choices.items():
                walk(child, (*path, name))

    walk(root, ())
    assert {path for path, _ in found} == {("init",)}


def test_the_help_says_the_flags_set_the_workers_model():
    text = init_parser().format_help()
    assert "workers' model" in " ".join(text.split()) and "Lead's own model" in " ".join(text.split())


@pytest.mark.parametrize("argv", [["--check-command", "make"], ["--check-command", ""],
                                  ["--check-command", "make", "--check-timeout", "1"], ["--model", "openai/m"],
                                  ["--model", ""], ["--model", "m", "--provider", "openai"], ["--provider", "x"],
                                  ["--check-timeout", "1"]])
def test_each_flag_is_refused_in_a_lead_session_and_init_itself_stays_as_it_was(argv):
    refusal = lead_broker.refuses_locally(build_parser().parse_args(["init", *argv]))
    assert refusal is not None and "ask the operator" in refusal and argv[0] in refusal
    assert lead_broker.refuses_locally(build_parser().parse_args(["init"])) is None
    assert lead_broker.refuses_locally(build_parser().parse_args(["init", "--name", "x"])) is None


def test_the_profiles_deadline_is_the_provisional_one_its_note_records():
    """Register E228 (the chain's third PR): a raise to Run needs `deadline_s` on every profile routing can pick, so
    first configuration writes one. No recorded run carries a wall time yet, so the value is provisional: the steering
    envelope's activation bound, derived, never restated, and the note that records the measurement says so."""
    from aew.engine import steering as S

    assert FC.DEADLINE_S == S.ENVELOPE_DEFAULTS["loop_deadline_s"]
    note = (Path(__file__).resolve().parents[2] / "docs" / "implementation" / "notes.d" / "E228"
            / "2026-11-10-feat-scheduler-run-defaults.md").read_text(encoding="utf-8")
    assert "provisional" in note and 'ENVELOPE_DEFAULTS["loop_deadline_s"]' in note and "0 wall times" in note
    assert S.profiles_without_deadline(yaml.safe_load(parse(model="openai/m").files()[X.REL_PATH])) == []


@pytest.mark.parametrize("mode", [None, "crawl", "walk", "run"])
def test_the_provisional_deadline_bounds_only_a_run_started_under_run(mode):
    """Review of E228's third PR, F5: first configuration's deadline is Run's (`deadline_scope: run`): the pin carries
    the scope as written, and the supervisor applies the deadline only to a run that starts while the effective mode is
    Run, so an attended run gets none. A deadline the operator wrote (no scope, or `always`) bounds every run, and a
    state that cannot be read keeps the deadline."""
    from aew.engine import steering as S
    from aew.harness.supervisor import Supervisor

    policy = yaml.safe_load(parse(model="openai/m").files()[X.REL_PATH])

    def pin(policy: dict[str, Any]) -> Any:
        return X.resolve(policy, None, archetype="implementer", card_id=None, risk_class=1,
                         identity=lambda h, p, m, f: SimpleNamespace(provider="openai", model="m"))

    state = {"lead": {"generation": 1, "status": "held"},
             "steering": {**S.empty(), "standing": {"mode": mode, "record": None, "rev": 0}}}

    def applied(profile: dict[str, Any], read: Any = state) -> Any:
        return Supervisor.applied_deadline(SimpleNamespace(record={"execution_profile": profile},  # type: ignore[arg-type]
                                                           _committed_state=lambda: read))

    first = pin(policy)
    assert first["deadline_s"] == FC.DEADLINE_S and first["deadline_scope"] == "run"
    assert applied(first) == (FC.DEADLINE_S if mode == "run" else None)
    assert applied(first, read=None) == FC.DEADLINE_S
    for scope in ({}, {"deadline_scope": "always"}):
        own = pin({**policy, "profiles": {"default": {"model": "openai/m", "deadline_s": 900, **scope}}})
        assert own.get("deadline_scope") == scope.get("deadline_scope") and applied(own) == 900
