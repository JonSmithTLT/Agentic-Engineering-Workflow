"""No text AEW shows suggests the Lead credential, or a provider key, as a command-line value (STG-05 CS-4 addendum
12, ruling 3's static test), and none offers a persistent one (the designer's ruling of 2026-10-30): every parser's
help, the operator guides, and the refusals for a missing credential or provider key. No test passes `--token` with a
value either, except the refusal's own tests (the Lead's condition for the migration).

What counts, each with a planted control (a right case, a wrong case and a missing case):
- `--token` followed by a value, in help text or in a guide's code (a code span or a fenced block);
- an `export NAME=` line or a `$env:NAME = '...'` assignment, anywhere, for a credential's or a secret's name;
- `SetEnvironmentVariable` or `setx` with such a name, anywhere: a persistent variable reaches every process.

A known limit: `--invocation-token` (a scripted role's credential) still takes a value; the register tracks it.
"""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

from aew import lead_credential
from aew.harness.contract import CREDENTIAL_ENV

ROOT = Path(__file__).resolve().parents[2]
GUIDES = (*sorted((ROOT / "docs" / "guides").glob("*.md")), ROOT / "README.md")
# Ruling 2: these guides show the prompt first, and the per-session forms second.
FORM_GUIDES = ("docs/guides/quickstart.md", "docs/guides/opencode.md")
# A test of the refusal passes `--token` with a value on purpose, and says so on that line.
MARKER = "# a --token value, refused"

TOKEN_VALUE = re.compile(r"--token(?![-\w])[ \t]*(?:=|[ \t])[ \t]*(?!-)\S")
EXPORT = re.compile(r"\bexport\s+(?P<a>\w+)\s*=|\$env:(?P<b>\w+)\s*=\s*['\"]", re.IGNORECASE)
PERSISTENT = re.compile(r"SetEnvironmentVariable\s*\(\s*['\"]?(?P<a>\w+)|\bsetx(?:\.exe)?\s+(?P<b>\w+)", re.IGNORECASE)
SECRET_NAME = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE)
SPAN = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"^\s*(```|~~~)")


def code_of(markdown: str) -> list[str]:
    """A guide's code: each fenced block's lines and each inline code span."""
    out, fenced = [], False
    for line in markdown.splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        out += [line] if fenced else SPAN.findall(line)
    return out


def problems(text: str, *, markdown: bool) -> list[str]:
    """What ``text`` suggests: a credential's value on a command line, or a persistent credential."""
    code = code_of(text) if markdown else [text]
    found = [f"--token with a value: {m.group(0)!r}" for c in code for m in TOKEN_VALUE.finditer(c)]
    found += [f"a value assigned: {m.group(0)!r}" for m in EXPORT.finditer(text)
              if secret(m.group("a") or m.group("b"))]
    found += [f"a persistent credential: {m.group(0)!r}" for m in PERSISTENT.finditer(text)
              if secret(m.group("a") or m.group("b"))]
    return found


def secret(name: str) -> bool:
    """Whether a variable's name is a credential's (an AEW one) or reads as a secret's (a provider key)."""
    return name.upper() in CREDENTIAL_ENV or bool(SECRET_NAME.search(name))


def missing_forms(text: str) -> list[str]:
    """The per-session forms a guide does not show as written (they are lead_credential's, never restated by hand),
    and whether it shows them before the prompt."""
    missing = [shell for shell, form in lead_credential.SECURE_FORMS.items() if form not in text]
    if "hidden prompt" not in text:
        missing.append("the hidden prompt")
    elif not missing and text.index("hidden prompt") > min(map(text.index, lead_credential.SECURE_FORMS.values())):
        missing.append("the prompt first")
    return missing


def helps() -> dict[str, str]:
    """Every command's help text, by its command path, from the live parser with every optional command on."""
    from aew.cli.main import build_parser

    out: dict[str, str] = {}

    def walk(parser: argparse.ArgumentParser, path: str) -> None:
        out[path] = parser.format_help()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, f"{path} {name}")

    walk(build_parser(recall_search=True, coordination_reads=True), "aew")
    return out


def token_values_in_tests(source: str) -> list[int]:
    """The lines of a test module that pass `--token` with a value (in a call's arguments, or in a list or tuple of
    them) without the refusal's marker."""
    lines = source.splitlines()
    found = []
    for node in ast.walk(ast.parse(source)):
        items = node.args if isinstance(node, ast.Call) else node.elts if isinstance(node, (ast.List, ast.Tuple)) \
            else []
        for a, b in zip(items, items[1:], strict=False):  # each item with the one after it
            if isinstance(a, ast.Constant) and a.value == "--token" and not isinstance(b, ast.Starred) \
                    and MARKER not in lines[a.lineno - 1]:
                found.append(a.lineno)
    return sorted(set(found))


# ---------------------------------------------------------------------------------------------- the product's texts


def test_no_help_text_suggests_a_credential_on_a_command_line_and_token_left_the_help():
    texts = helps()
    assert len(texts) > 100  # the walk reached every command
    assert {path: problems(text, markdown=False) for path, text in texts.items() if problems(text, markdown=False)} \
        == {}
    assert [path for path, text in texts.items() if re.search(r"--token(?![-\w])", text)] == []


def test_no_guide_suggests_a_credential_on_a_command_line_or_a_persistent_one():
    assert {str(Path(g).relative_to(ROOT).as_posix()) for g in GUIDES} >= set(FORM_GUIDES)
    found = {g.name: problems(g.read_text(encoding="utf-8"), markdown=True) for g in GUIDES}
    assert {name: p for name, p in found.items() if p} == {}


def test_the_guides_show_the_prompt_first_and_each_per_session_form_as_the_refusal_gives_it():
    assert {g: missing_forms((ROOT / g).read_text(encoding="utf-8")) for g in FORM_GUIDES} == dict.fromkeys(
        FORM_GUIDES, [])


def test_quickstart_shows_each_provider_key_form():
    guide = (ROOT / FORM_GUIDES[0]).read_text(encoding="utf-8")
    forms = lead_credential.forms("OPENAI_API_KEY", "OPENAI_API_KEY")
    assert all(form in guide.splitlines() for form in forms.values())


def test_the_refusals_give_each_form_and_suggest_no_value_on_a_command_line():
    for refusal in (lead_credential.token_value_refusal(lead_session=False).message, lead_credential.how_to_set()):
        assert all(form in refusal for form in lead_credential.SECURE_FORMS.values())
        assert problems(refusal.replace("--token takes no value", ""), markdown=False) == []


def test_a_refusal_for_a_missing_provider_key_gives_the_per_session_forms_for_its_name_and_no_value():
    """Review of #316, M2: a provider key is a secret, and its refusal (`aew doctor`, a refused launch) gives the
    per-session forms with the key's own name, outside a Lead session and inside one; only a variable that holds no
    secret (`BIN_ENV`, a path) keeps the plain form."""
    from aew.harness import agentenv
    from aew.harness.opencode.adapter import BIN_ENV

    name = "SYNTHETIC_PROVIDER_API_KEY"
    texts = [agentenv.provider_env_problems([name], {})[0][1], agentenv.env_fix(name)]
    with agentenv.session_host("this Lead session (`aew opencode` or `aew lead session`)"):
        texts += [agentenv.provider_env_problems([name], {})[0][1], agentenv.env_fix(name)]
    for text in texts:
        assert problems(text, markdown=False) == [], text
        assert all(form in text for form in lead_credential.forms(name, name).values()), text
    plain = agentenv.env_fix(BIN_ENV, secret=False)
    assert not secret(BIN_ENV) and problems(plain, markdown=False) == []
    assert problems(plain.replace(BIN_ENV, name), markdown=False)  # the control: the plain form, for a secret, trips


def test_no_test_passes_a_token_value_except_the_refusals_own_tests():
    """The migration's guard: the credential reaches a test's CLI the way it reaches the operator's, by the
    variable; a `--token` value appears only where a test checks that it is refused, marked so."""
    files = sorted((ROOT / "tests").rglob("*.py"))
    found = {f"{p.relative_to(ROOT).as_posix()}:{n}" for p in files
             for n in token_values_in_tests(p.read_text(encoding="utf-8"))}
    assert found == set()
    marked = [p for p in files if MARKER in p.read_text(encoding="utf-8") and p.name != Path(__file__).name]
    assert any(p.name == "test_lead_credential_input.py" for p in marked)  # the refusal's tests are still there


# ---------------------------------------------------------------------------------------------- the planted controls


def test_the_static_check_finds_each_wrong_case_and_passes_the_right_one():
    right = "\n".join(["Never put the credential on a command line: `--token` takes no value.", "```bash",
                       *lead_credential.SECURE_FORMS.values(), "aew manifest adopt --reason r --expect-rev 1",
                       "aew g3 confirm --token-file f", "```"])
    assert problems(right, markdown=True) == []
    wrong = {
        "```bash\naew manifest adopt --token <credential> --expect-rev 1\n```": "--token with a value",
        "Run `aew checkpoint --token=$T`.": "--token with a value",
        "export AEW_LEAD_TOKEN=$T": "a value assigned",
        "export OPENAI_API_KEY=$K": "a value assigned",
        "In PowerShell, $env:VENDOR_KEY = '...'": "a value assigned",
        "[Environment]::SetEnvironmentVariable('AEW_LEAD_TOKEN', $t, 'User')": "a persistent credential",
        "setx OPENAI_API_KEY synthetic": "a persistent credential",
    }
    for text, kind in wrong.items():
        assert [p.split(":")[0] for p in problems(text, markdown=True)] == [kind], text
    assert problems("aew checkpoint --token SYNTHETIC", markdown=False)  # help text: all of it is code
    assert not problems("[Environment]::SetEnvironmentVariable('PATH', $p, 'User')", markdown=True)
    assert not problems("export PATH=$HOME/bin:$PATH; $env:AEW_OPENCODE_BIN = 'C:/opencode.exe'", markdown=True)


def test_the_forms_check_finds_a_missing_form_and_a_prompt_shown_second():
    forms = "\n".join(lead_credential.SECURE_FORMS.values())
    assert missing_forms(f"It asks at a hidden prompt.\n{forms}") == []
    first = next(iter(lead_credential.SECURE_FORMS))
    assert missing_forms("hidden prompt\n" + forms.replace(lead_credential.SECURE_FORMS[first], "")) == [first]
    assert missing_forms(f"{forms}\nor at a hidden prompt") == ["the prompt first"]
    assert missing_forms(forms) == ["the hidden prompt"]


def test_the_tests_guard_finds_a_token_value_in_a_call_and_a_list_and_passes_the_marked_and_the_variable():
    source = "\n".join([
        'p.aew("checkpoint", "--token", p.token, "--expect-rev", "1")',
        'argv = ["map", "generate", "--token", p.token]',
        f'p.aew("checkpoint", "--token", p.token)  {MARKER}',
        'p.aew("checkpoint", "--expect-rev", "1", env={"AEW_LEAD_TOKEN": p.token})',
        'g3("confirm", "--token-file", path)',
    ])
    assert token_values_in_tests(source) == [1, 2]
