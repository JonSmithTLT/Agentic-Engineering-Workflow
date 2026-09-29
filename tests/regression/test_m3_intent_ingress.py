"""M3 hardening B1: authored text reaches AEW as data (``AEW-INV-INTENT-001``; hierarchy design §10.1, Scenario G).

Seen in the M3 dogfood: a model Lead typed ``--goal "... -$15.00"`` in bash, the shell expanded ``$1``, and AEW
stored the goal ``-5.00`` (``INTENT_INGRESS_CORRUPTION``). The Lead's reason for classifying the failure was
corrupted the same way. ``--fields FILE|-`` gives every command a way to take its option values as data, from a
file or a quoted heredoc that no shell expands. The corpus below, the design's list of shell-significant values,
must reach AEW's authoritative state byte for byte by every canonical ingress: ``--fields`` from a file, from stdin
and through a Lead session, and the existing stdin payloads. The ``aew`` process is started with an argument list, never
a shell, as a harness's tool call does; the same test runs on Windows and Linux.
"""

from __future__ import annotations

import json
import sys

import pytest
import yaml

from aewflow import sample_project
from conftest import run_aew
from fake_harness import AGENT

from aew.cli import fields
from aew.cli.main import build_parser
from aew.engine.api import Engine
from aew.errors import UsageError
from aew.util import parse_frontmatter

CORPUS = [
    "format_amount(Decimal('-15')) == '-$15.00' and it costs $5.00",
    "$(echo nope) and ${HOME} and %PATH% and $1",
    "`literal backticks`",
    "glob * and ? and [ab] and ~/x",
    "a & b; c | d > e < f && g || h",
    "it's \"quoted\" both 'ways'",
    "C:\\Users\\x\\new\\table and \\\\server\\share\\",
    "-starts with a dash",
    "--looks-like-an-option",
    "line one\nline two\n  indented\n",
    "Unicode: café – ≠ 日本 🙂",
    "#not a comment: key: value",
    "1.10",
    "yes",
    "~",
]
SCOPE = ["ledger/**", "tests/test_$x?.py", "docs/[ab]*.md"]  # one glob each: a comma is refused (M3-D9)


def spec(title: str = CORPUS[0]) -> dict:
    return {"title": title, "goal": CORPUS, "contract": CORPUS[::-1], "scope": SCOPE}


def dump(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def record(p, wid: str) -> dict:
    return parse_frontmatter((p.root / ".aew" / "work" / wid / "ticket.md").read_text(encoding="utf-8"),
                             source=wid)[0]


def assert_stored(p, wid: str, data: dict) -> None:
    meta = record(p, wid)
    assert meta["title"] == data["title"]
    assert meta["acceptance"]["goal_backwards"] == data["goal"]
    assert meta["acceptance"]["contract"] == data["contract"]
    assert meta["scope"]["paths"] == data["scope"]


def create(p, *extra: str, input: str | None = None):
    return p.aew("work", "create", "ticket", "--class", "1", *extra, "--token", p.token,
                 "--expect-rev", str(p.rev()), input=input)


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])  # utf-16: Windows PowerShell 5.1's `>`
def test_fields_from_a_file_are_stored_byte_for_byte(tmp_path, encoding):
    p = sample_project(tmp_path)
    path = tmp_path / "ticket.yaml"
    path.write_bytes(dump(spec()).encode(encoding))
    res = create(p, "--fields", str(path))
    assert res.returncode == 0, res.stderr
    assert_stored(p, res.json["id"], spec())


def test_fields_from_stdin_are_stored_byte_for_byte(tmp_path):
    p = sample_project(tmp_path)
    res = create(p, "--fields", "-", input=dump(spec()))
    assert res.returncode == 0, res.stderr
    assert_stored(p, res.json["id"], spec())


def test_hand_written_yaml_keeps_every_value_as_the_text_written(tmp_path):
    """Scalars are text: 1.10 stays 1.10, yes stays yes, a date stays a date string."""
    p = sample_project(tmp_path)
    text = ("title: Fix -$15.00 display\n"
            "goal:\n"
            "  - format_amount(Decimal(\"-15\")) == \"-$15.00\"\n"
            "  - 1.10\n"
            "  - yes\n"
            "  - 2026-01-31\n"
            "contract: [changes stay in ledger/]\n"
            "scope:\n  - ledger/**\n")
    res = create(p, "--fields", "-", input=text)
    assert res.returncode == 0, res.stderr
    meta = record(p, res.json["id"])
    assert meta["title"] == "Fix -$15.00 display"
    assert meta["acceptance"]["goal_backwards"] == ['format_amount(Decimal("-15")) == "-$15.00"', "1.10", "yes",
                                                    "2026-01-31"]


def test_reasons_and_notes_through_fields_and_stdin_are_stored_byte_for_byte(tmp_path):
    p = sample_project(tmp_path)
    wid = create(p, "--fields", "-", input=dump(spec())).json["id"]
    plan = "".join(f"- {c}\n" if "\n" not in c else c for c in CORPUS)
    res = p.aew("plan", "propose", wid, "--file", "-", "--token", p.token, "--expect-rev", str(p.rev()), input=plan)
    assert res.returncode == 0, res.stderr
    stored = (p.root / ".aew" / "work" / wid / "plan-v1.md").read_text(encoding="utf-8")
    assert parse_frontmatter(stored, source="plan")[1] == plan
    reason = "\n".join(CORPUS)
    res = p.aew("work", "transition", wid, "--to", "CANCELLED", "--token", p.token, "--expect-rev", str(p.rev()),
                "--fields", "-", input=dump({"reason": reason}))
    assert res.returncode == 0, res.stderr
    res = p.aew("checkpoint", "--token", p.token, "--expect-rev", str(p.rev()), "--fields", "-",
                input=dump({"next": CORPUS[1]}))
    assert res.returncode == 0, res.stderr
    state = Engine.discover(p.root).store.read()
    assert state["work"][wid]["history"][-1]["reason"] == reason
    assert state["next_action"] == CORPUS[1]


def test_fields_through_a_lead_session_are_stored_byte_for_byte(tmp_path):
    """The Lead's harness pipes the heredoc to `aew`; the client expands it and the broker receives data."""
    p = sample_project(tmp_path)
    script, transcript = tmp_path / "lead-script.json", tmp_path / "lead.jsonl"
    script.write_text(json.dumps([{"do": "lead", "args": ["work", "create", "ticket", "--class", "1",
                                                          "--fields", "-"], "stdin": dump(spec(CORPUS[4]))}]),
                      encoding="utf-8")
    res = run_aew("-C", str(p.root), "lead", "session", "--", sys.executable, str(AGENT), "--script", str(script),
                  "--transcript", str(transcript), env={"AEW_LEAD_TOKEN": p.token}, timeout=300)
    assert res.returncode == 0, res.stderr
    [step] = [json.loads(line)["result"] for line in transcript.read_text(encoding="utf-8").splitlines()]
    assert step["exit"] == 0, step
    assert_stored(p, json.loads(step["stdout"])["id"], spec(CORPUS[4]))


@pytest.mark.parametrize("text, message", [
    ("title: x\nnope: y\n", "has no option --nope"),
    ("token: aew1.x\n", "credential"),
    ("fields: other.yaml\n", "cannot nest"),
    ("goal: {a: b}\n", "nested"),
    ("- just a list\n", "mapping"),
    ("title: [one, two]\n", "takes one value"),
    ("non_mutating: maybe\n", "switch"),
    ("title: 'unterminated\n", "not a YAML"),
])
def test_malformed_fields_are_refused_before_anything_runs(tmp_path, text, message):
    path = tmp_path / "f.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(UsageError, match=message):
        fields.expand(["work", "create", "ticket", "--class", "1", "--fields", str(path)], build_parser())


def test_fields_given_twice_or_competing_for_stdin_are_refused():
    with pytest.raises(UsageError, match="once"):
        fields.expand(["checkpoint", "--fields", "a", "--fields", "b"], build_parser())
    with pytest.raises(UsageError, match="stdin"):
        fields.expand(["work", "create", "ticket", "--body-file", "-", "--fields", "-"], build_parser())


def test_a_switch_is_set_by_true_and_left_off_by_false(tmp_path):
    for value, expected in (("true", ["--non-mutating"]), ("false", [])):
        path = tmp_path / f"{value}.yaml"
        path.write_text(f"non_mutating: {value}\n", encoding="utf-8")
        argv = fields.expand(["work", "create", "ticket", "--fields", str(path)], build_parser())
        assert argv == ["work", "create", "ticket", *expected]


def test_an_unexpanded_fields_option_is_refused_never_ignored():
    """The broker parses the argv a client already expanded; a raw --fields reaching a parser fails loudly."""
    with pytest.raises(SystemExit):
        build_parser().parse_args(["checkpoint", "--fields", "x.yaml"])
