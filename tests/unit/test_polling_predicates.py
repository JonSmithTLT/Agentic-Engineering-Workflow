"""A polled predicate never reads a file raw, and never subscripts a read that can return None.

A file another thread or process replaces can fail to read for a moment on Windows: ``os.replace`` over a file a reader
has open fails with a sharing violation, and a read of the old file while it is delete-pending raises
``PermissionError``. A predicate polled by ``until`` must then answer "not yet", and a test whose predicate raises
instead fails at random. The class has two forms, a lambda passed to a polling helper (``until``, ``wait_for``,
``wait_until``) that:
- reads a file raw, with ``.read_text(``, ``.read_bytes(`` or the builtin ``open(``: ``PermissionError`` at that moment
  (#241's run at b9c4a6b6, ``integration 12/16 (windows-latest)``, test_steering_loop.py reading
  ``.aew/local/steering/loop.json`` while the steering loop replaced it). Read through tests/helpers/racing_read.py,
  ``read_text_or_none(path)`` or ``read_json_or_none(path)``: each returns None for any OSError, and the JSON one also
  for text that does not parse yet (a writer that writes in place can be read half-written);
- subscripts the call of an aew function whose return annotation admits None at its top level,
  ``read(root)["field"]``: AEW's guarded readers (``broker_liveness.read``, ``runlog.read_live``, ...) return None for
  any OSError, so the subscript raises TypeError at that moment (#237's run 40035060397, attempt 2,
  ``test_broker_liveness_is_local_and_beats_every_poll``). Guard the read instead: ``(read(root) or last)["field"]``.

The invariant: no polled lambda contains a raw read, and none subscripts a read that can return None. Two detectors
written separately enumerate it over every test file, and must agree:
- an AST one: a Call in the lambda whose func is an Attribute named ``read_text`` or ``read_bytes``, or the Name
  ``open``; and a Subscript of a Call that it resolves through the module's own aew imports to a function whose
  annotation it reads;
- a text one: a regular expression over the lambda's line for the raw read, and another for the predicate, against the
  names of the functions in src/aew whose return annotation, as written, ends in ``| None``.

What both miss (pinned below): a predicate that is a named function rather than a lambda (a raw read inside it is not
seen), a raw read that is not one of the three spellings (``path.open()``, ``io.open()``), and an aew
reader reached through an object (``self.store.read``) or a module imported without an alias
(``aew.harness.runlog.read_live``). Such a predicate is a defect the reviewer reads for; neither detector claims it. A
lambda spread over several lines, and a read whose argument is itself a call (``read(path(x))["k"]``), are seen by the
AST detector only: the scan still fails on them, and so does the agreement test. The text detector also reads the whole
line of the poll, so a raw read named in a string or a comment on that line is its alone (pinned too, and the
agreement test fails on it).

A read that is not polled is outside this mechanism: whether a writer is live while it runs is semantic. Such a read of
a record a live writer rewrites waits for a whole record, ``until(lambda: read(root))``, as test_notifier.py does.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import re
from pathlib import Path

import pytest
from racing_read import read_json_or_none, read_text_or_none

ROOT = Path(__file__).resolve().parents[2]
EXEMPT = {Path(__file__).resolve()}  # this module plants the banned forms below
POLLERS = {"until", "wait_for", "wait_until"}
RAW_METHODS = {"read_text", "read_bytes"}  # with the builtin open: the raw reads, the spellings of the class


def _top_level_optional(annotation: str) -> bool:
    """Whether an annotation, as text, admits None at its top level: ``X | None``, not ``tuple[str, X | None]``."""
    depth, part, parts = 0, "", []
    for ch in annotation:
        depth += ch in "[(" and 1 or (ch in "])" and -1 or 0)
        if ch == "|" and depth == 0:
            parts.append(part.strip())
            part = ""
        else:
            part += ch
    parts.append(part.strip())
    return "None" in parts and len(parts) > 1 or annotation.startswith("Optional[")


def _aew_names(tree: ast.Module) -> dict[str, str]:
    """Each local name a module binds to an aew object, as the dotted name it refers to."""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "aew":
            names.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
        elif isinstance(node, ast.Import):
            names.update({a.asname: a.name for a in node.names if a.asname and a.name.split(".")[0] == "aew"})
    return names


def _returns_optional(dotted: str) -> bool:
    module, _, attr = dotted.rpartition(".")
    try:
        target = getattr(importlib.import_module(module), attr)
    except (ImportError, AttributeError, ValueError):
        return False
    if isinstance(target, type) or not callable(target):
        return False
    annotation = inspect.signature(target).return_annotation
    return isinstance(annotation, str) and _top_level_optional(annotation)


def _poller(call: ast.Call) -> bool:
    func = call.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    return name in POLLERS and bool(call.args) and isinstance(call.args[0], ast.Lambda)


def _raw_read(node: ast.AST) -> bool:
    """Whether a node is a call that reads a file raw: ``x.read_text(...)``, ``x.read_bytes(...)`` or ``open(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in RAW_METHODS
    return isinstance(func, ast.Name) and func.id == "open"


def ast_sites(source: str) -> set[int]:
    """Lines of each polling call whose lambda reads a file raw, or subscripts a read that can return None."""
    tree = ast.parse(source)
    names = _aew_names(tree)
    found = set()
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _poller(call)):
            continue
        for node in ast.walk(call.args[0]):
            if _raw_read(node):
                found.add(call.lineno)
            if not (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Call)):
                continue
            func = node.value.func
            dotted = (names.get(func.id) if isinstance(func, ast.Name)
                      else f"{names[func.value.id]}.{func.attr}"
                      if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in names
                      else None)
            if dotted and _returns_optional(dotted):
                found.add(call.lineno)
    return found


IMPORT_TEXT = re.compile(r"^\s*from (aew(?:\.\w+)*) import (?:\(([^)]*)\)|([\w ,]+)$)", re.M)
MODULE_TEXT = re.compile(r"^\s*import (aew(?:\.\w+)*) as (\w+)\s*$", re.M)
POLL_TEXT = re.compile(r"\b(?:until|wait_for|wait_until)\(\s*lambda[^:\n]*:(?P<body>[^\n]*)")
RAW_TEXT = re.compile(r"\.(?:read_text|read_bytes)\(|(?<![\w.])open\(")  # not `.open(`: the AST rule is the Name only
READ_TEXT = re.compile(r"(?<![\w.)\]])(?:(\w+)\.)?(\w+)\([^()\n]*\)\[")


def _aew_modules():
    """Each module of src/aew as ``(dotted name, path)``; never ``__main__``, which runs the CLI when imported."""
    for path in sorted((ROOT / "src" / "aew").rglob("*.py")):
        if path.stem != "__main__":
            yield ".".join(path.relative_to(ROOT / "src").with_suffix("").parts).removesuffix(".__init__"), path


def _optional_functions() -> set[str]:
    """Every function of src/aew whose return annotation, as written, ends in ``| None``: ``module.function``."""
    found = set()
    for module, path in _aew_modules():
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^def (\w+)\((?:[^()]|\([^()]*\))*\)\s*->\s*([^:\n]+):", text, re.M):
            if m.group(2).strip().endswith("| None"):
                found.add(f"{module}.{m.group(1)}")
    return found


OPTIONAL = _optional_functions()


def text_sites(source: str) -> set[int]:
    """The same class, by text: the line where each such polling call starts."""
    names = {m.group(2): m.group(1) for m in MODULE_TEXT.finditer(source)}
    for m in IMPORT_TEXT.finditer(source):
        for item in re.sub(r"#[^\n]*", "", m.group(2) or m.group(3)).split(","):
            name, _, alias = item.strip().partition(" as ")
            if name:
                names[alias or name] = f"{m.group(1)}.{name}"
    found = set()
    for poll in POLL_TEXT.finditer(source):
        line = source.count("\n", 0, poll.start()) + 1
        if RAW_TEXT.search(poll.group("body")):
            found.add(line)
        for read in READ_TEXT.finditer(poll.group("body")):
            qualifier, function = read.groups()
            dotted = f"{names[qualifier]}.{function}" if qualifier in names else names.get(function) if not qualifier \
                else None
            if dotted in OPTIONAL:
                found.add(line)
    return found


@functools.cache
def _test_sites() -> dict[str, tuple[set[int], set[int]]]:
    """Each test file's sites as each detector finds them: ``{path: (by AST, by text)}``."""
    sites = {}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        if path.resolve() not in EXEMPT:
            source = path.read_text(encoding="utf-8")
            sites[path.relative_to(ROOT).as_posix()] = (ast_sites(source), text_sites(source))
    return sites


def test_no_polled_predicate_reads_a_file_raw_or_subscripts_a_read_that_can_return_none():
    found = {f"{path}:{line}" for path, (by_ast, by_text) in _test_sites().items() for line in by_ast | by_text}
    assert not found, ("a racing read fails or is None for a moment: read a file through tests/helpers/racing_read.py "
                       "(read_text_or_none, read_json_or_none), and guard an aew reader, (read(...) or last)[...]: "
                       f"{sorted(found)}")


def test_the_two_detectors_agree_on_every_test_file():
    disagree = {path: (sorted(by_ast), sorted(by_text)) for path, (by_ast, by_text) in _test_sites().items()
                if by_ast != by_text}
    assert not disagree


def test_the_two_detectors_agree_on_which_aew_functions_can_return_none():
    by_ast = set()
    for module, path in _aew_modules():
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.FunctionDef) and _returns_optional(f"{module}.{node.name}"):
                by_ast.add(f"{module}.{node.name}")
    assert by_ast == OPTIONAL
    assert {"aew.harness.broker_liveness.read", "aew.harness.runlog.read_live",
            "aew.harness.notify.summary"} <= OPTIONAL
    assert "aew.harness.runlog.observed_status" not in OPTIONAL  # a tuple holding an optional is not itself one


IMPORTS = ("from aew.harness import (\n    broker_liveness,  # the beat\n    runlog,\n)\n"
           "import aew.harness.notify as notify\n")
LINE = IMPORTS.count("\n") + 1
PLANTED_WRONG = [
    'until(lambda: broker_liveness.read(root)["beat_at"] > t, 10, "x")',
    'self.until(lambda: runlog.read_live(d)["prompt_state"] == "posted")',
    'wait_for(lambda: notify.summary(root)["dropped"])',
    'until(lambda: broker_liveness.read(root)["a"] and broker_liveness.read(root)["b"])',
    'until(lambda: p.exists() and p.read_text(encoding="utf-8").strip(), 10, "x")',  # the raw reads
    'self.until(lambda: p.read_bytes().startswith(b"{"))',
    'wait_for(lambda: open(p).read())',
    'wait_until(lambda: json.loads(p.read_text())["stop"])',
]
PLANTED_RIGHT = [
    'until(lambda: (broker_liveness.read(root) or first)["beat_at"] > t)',
    'until(lambda: (broker_liveness.read(root) or {}).get("closed_at"))',
    'until(lambda: runlog.observed_status(d)[0] == "done")',
    'record = broker_liveness.read(root)["beat_at"]',  # not polled: a deterministic read fails loudly, not at random
    'until(lambda: (read_text_or_none(p) or "").strip(), 10, "x")',  # through the helpers
    'until(lambda: ((read_json_or_none(p) or {}).get("stop") or {}).get("code") == "x")',
    'text = p.read_text(encoding="utf-8")\ndata = p.read_bytes()',  # raw, but outside any poll
    'with open(p) as f:\n    text = f.read()\nuntil(lambda: ready(text))',
]
BOTH_MISS = [
    "def ready():\n    return broker_liveness.read(root)['beat_at'] > t\nuntil(ready)",
    'until(lambda: self.store.read()["revision"] > 3)',
    'import aew.harness.runlog\nuntil(lambda: aew.harness.runlog.read_live(d)["prompt_state"])',
    "def ready():\n    return p.read_text().strip()\nuntil(ready)",  # a raw read inside a named function that is polled
    "until(lambda: p.open().read())",  # raw reads of other spellings: the class is the three above
    "until(lambda: io.open(p).read())",
]
AST_ONLY = [
    'until(lambda: (\n    broker_liveness.read(root)["beat_at"] > t))',
    'until(lambda: broker_liveness.read(project.root())["beat_at"] > t)',
    "until(lambda: (\n    p.read_text().strip()))",
]
TEXT_ONLY = [  # the text detector reads the poll's whole line: a raw read named in a string or a comment is its alone
    'until(lambda: ready(), 5, "p.read_text() is how the old test waited")',
    "until(lambda: ready())  # open(p) would race the replace",
]


@pytest.mark.parametrize("line", PLANTED_WRONG)
def test_both_detectors_see_each_raw_or_unguarded_read_in_a_polled_lambda(line):
    source = IMPORTS + line + "\n"
    assert ast_sites(source) == text_sites(source) == {LINE}


@pytest.mark.parametrize("line", PLANTED_RIGHT)
def test_neither_detector_flags_a_helper_guarded_or_unpolled_read(line):
    source = IMPORTS + line + "\n"
    assert ast_sites(source) == text_sites(source) == set()


@pytest.mark.parametrize("source", BOTH_MISS)
def test_what_both_detectors_miss_is_pinned(source):
    source = IMPORTS + source + "\n"
    assert ast_sites(source) == text_sites(source) == set()


@pytest.mark.parametrize("source", AST_ONLY)
def test_what_only_the_ast_detector_sees_is_pinned(source):
    source = IMPORTS + source + "\n"
    assert (ast_sites(source), text_sites(source)) == ({LINE}, set())


@pytest.mark.parametrize("source", TEXT_ONLY)
def test_what_only_the_text_detector_sees_is_pinned(source):
    source = IMPORTS + source + "\n"
    assert (ast_sites(source), text_sites(source)) == (set(), {LINE})


# ---------------------------------------------------------------------------------------------- the helpers


@pytest.mark.parametrize("read", [read_text_or_none, read_json_or_none])
def test_a_read_that_fails_or_races_a_replace_is_none_not_an_error(read, tmp_path, monkeypatch):
    record = tmp_path / "loop.json"
    record.write_text("{}", encoding="utf-8")
    assert read(tmp_path / "absent.json") is None  # not yet written
    assert read(tmp_path) is None  # a directory: IsADirectoryError, or PermissionError on Windows
    assert read(str(record)) is not None  # whole, and a str path reads too

    def delete_pending(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied: the old file is delete-pending")

    monkeypatch.setattr(Path, "read_text", delete_pending)
    assert read(record) is None


def test_the_helpers_return_a_whole_record_unchanged(tmp_path):
    record = tmp_path / "loop.json"
    record.write_text('{"stop": {"code": "repetition", "note": "caf\u00e9"}}', encoding="utf-8")
    assert read_text_or_none(record) == '{"stop": {"code": "repetition", "note": "caf\u00e9"}}'
    assert read_json_or_none(record) == {"stop": {"code": "repetition", "note": "caf\u00e9"}}
    record.write_text("", encoding="utf-8")
    assert read_text_or_none(record) == ""  # empty is a read, not a failure: the caller's `or` decides


@pytest.mark.parametrize("text", ["", '{"stop": {"co', '{"stop": ', "[1, 2"])
def test_a_half_written_json_file_reads_as_not_yet(tmp_path, text):
    record = tmp_path / "loop.json"
    record.write_text(text, encoding="utf-8")
    assert read_json_or_none(record) is None
