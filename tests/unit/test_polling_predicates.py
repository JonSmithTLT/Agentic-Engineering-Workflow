"""A polled predicate never reads a file raw, and never consumes a read that can return None.

A file another thread or process replaces can fail to read for a moment on Windows: ``os.replace`` over a file a reader
has open fails with a sharing violation, and a read of the old file while it is delete-pending raises
``PermissionError``. A predicate polled by ``until`` must then answer "not yet", and a test whose predicate raises
instead fails at random. The class has two forms, a lambda passed to a polling helper named in ``POLLERS`` (``until``,
``wait_for``, ``wait_until``, ``_wait_for``, ``bounded_wait``, ``waiting``, ``_retrying``: a list by hand) that:
- reads a file raw, with ``.read_text(``, ``.read_bytes(`` or the builtin ``open(``: ``PermissionError`` at that moment
  (#241's run at b9c4a6b6, ``integration 12/16 (windows-latest)``, test_steering_loop.py reading
  ``.aew/local/steering/loop.json`` while the steering loop replaced it). Read through tests/helpers/racing_read.py,
  ``read_text_or_none(path)`` or ``read_json_or_none(path)``: each returns None for any OSError, and the JSON one also
  for text that does not parse yet (a writer that writes in place can be read half-written);
- consumes the call of an aew function whose return annotation admits None at its top level, by a subscript,
  ``read(root)["field"]``, an attribute, ``read(root).get("field")``, or ``in``, ``"field" in read(root)``:
  ``broker_liveness.read`` returns None for any OSError, so the consumption raises TypeError or AttributeError at that
  moment (#237's run 40035060397, attempt 2, ``test_broker_liveness_is_local_and_beats_every_poll``). The runlog readers
  (``runlog.read_live``) retry a PermissionError on Windows for up to 5 s first, and return None only for an absent or
  invalid file, which is still a reason not to subscript them. Guard the read instead:
  ``(read(root) or last)["field"]``.

The invariant: no polled lambda contains a raw read, and none consumes a read that can return None. A polling call
passes its predicate where the poller's definition calls it, by position or by keyword: ``bounded_wait`` takes it
second (``ready``), and ``gone`` by keyword. ``poller_params`` reads that from the definitions under tests/. Two
detectors written separately enumerate the invariant over every test file, and must agree:
- an AST one: a Call in the lambda whose func is an Attribute named ``read_text`` or ``read_bytes``, or the Name
  ``open``; and a Subscript, an Attribute, an ``in`` comparison or a comprehension over a Call that it resolves
  through the module's own aew imports to a function whose annotation it reads;
- a text one: a regular expression over the lambda's line for the raw read, and others for the predicate, against the
  names of the functions in src/aew whose return annotation, as written, ends in ``| None``.

What both miss (pinned below), each a defect the reviewer reads for, and neither detector claims it:
- a poller not in ``POLLERS``, which nothing finds: ``Chat.receive(timeout, gone=...)`` (tests/helpers/vertical/chat.py)
  calls ``gone`` in a sleeping loop and is not listed; no caller of it reads a file;
- a predicate that is a named function (``until(ready)``) or a lambda bound to a name (``pred = lambda: ...``): a raw
  read inside it is not seen;
- a predicate given by a keyword its poller's definition does not call (``until(cond=lambda: ...)``: ``cond`` is
  ``wait_for``'s);
- a raw read that is not one of the three spellings (``path.open()``, ``io.open()``);
- an aew reader reached through an object (``self.store.read``), through a module imported without an alias
  (``aew.harness.runlog.read_live``), or bound by a walrus (``(r := read(root))["k"]``);
- a None consumed by a comparison or arithmetic (``read(root) > 3``), or passed to a builtin (``len(read(root))``);
- a raw read inside a helper the predicate calls (``until(lambda: control(p)["invocations"])``, which reaches
  ``load_control``): the commonest spelling of the class here. A name-based scan (an over-approximation) finds about 45
  polled predicates that call a function that reads raw. Most read a file that is only appended to, which no replace
  races; ``load_control``, which reads a replaced file, retries the engine's own way (tests/helpers/invariants.py).
A lambda spread over several lines, a lambda in parentheses (given by position or by keyword), an argument before the
predicate that holds a call or a comma (``bounded_wait(f"t.{name()}", lambda: ...)``), and a read whose argument is
itself a call (``read(path(x))["k"]``) are seen by the AST detector only: the scan still fails on them, and so does
the agreement test. The text detector also reads the whole line of the poll, so a raw read named in a string or a
comment on that line is its alone (pinned too, and the agreement test fails on it). This module is exempt from the text
detector alone, because it plants the banned forms below as strings; the AST detector scans it like any other file.

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
EXEMPT = {Path(__file__).resolve()}  # this module plants the banned forms below as strings: the text detector skips it
# The polling helpers, by name; a poller not named here is not scanned (the module docstring). `wait_until` is defined
# by no test; the others are: `until` (tests/helpers/notifier.py and HarnessLab), `wait_for` (test_usage_live_run.py),
# `_wait_for` (test_integration_stages.py), `bounded_wait` (tests/helpers/bounds.py), `waiting`
# (test_harness_wait_any.py) and `_retrying` (tests/helpers/vertical/lead.py, a write retried on OSError: it takes a
# lambda by the same rule).
POLLERS = {"until", "wait_for", "wait_until", "_wait_for", "bounded_wait", "waiting", "_retrying"}
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


DEF_TEXT = re.compile(rf"\bdef (?:{'|'.join(sorted(POLLERS))})\(")  # a cheap filter: parse only files that define one


@functools.cache
def poller_params() -> dict[str, tuple[frozenset[int], frozenset[str]]]:
    """Where each polling helper takes its predicate: ``{name: (positions, keywords)}``, read from the definitions under
    tests/. A predicate is a parameter the body calls (``ready()``), and a method's ``self`` is not counted, as a call
    does not pass it. A helper no test defines takes it first, as ``predicate``."""
    positions: dict[str, set[int]] = {name: set() for name in POLLERS}
    keywords: dict[str, set[str]] = {name: set() for name in POLLERS}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not DEF_TEXT.search(source):
            continue
        for fn in ast.walk(ast.parse(source)):
            if not (isinstance(fn, ast.FunctionDef) and fn.name in POLLERS):
                continue
            positional = [a.arg for a in (*fn.args.posonlyargs, *fn.args.args)]
            if positional[:1] in (["self"], ["cls"]):
                positional = positional[1:]
            called = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
            positions[fn.name] |= {i for i, name in enumerate(positional) if name in called}
            given_by_name = (*positional, *(a.arg for a in fn.args.kwonlyargs))
            keywords[fn.name] |= {name for name in given_by_name if name in called}
    return {name: (frozenset(positions[name]) or frozenset({0}), frozenset(keywords[name]) or frozenset({"predicate"}))
            for name in POLLERS}


def _called_name(call: ast.Call) -> str:
    func = call.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _predicates(call: ast.Call) -> list[ast.Lambda]:
    """The lambdas a polling call passes as its predicate: at a position, or by a keyword, its definition calls."""
    name = _called_name(call)
    if name not in POLLERS:
        return []
    positions, keywords = poller_params()[name]
    given = [call.args[i] for i in sorted(positions) if i < len(call.args)]
    given += [k.value for k in call.keywords if k.arg in keywords]
    return [arg for arg in given if isinstance(arg, ast.Lambda)]


def _raw_read(node: ast.AST) -> bool:
    """Whether a node is a call that reads a file raw: ``x.read_text(...)``, ``x.read_bytes(...)`` or ``open(...)``."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in RAW_METHODS
    return isinstance(func, ast.Name) and func.id == "open"


def _optional_call(node: ast.AST, names: dict[str, str]) -> bool:
    """Whether a node is the call of an aew function (resolved through the module's own aew imports) whose return
    annotation admits None."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    dotted = (names.get(func.id) if isinstance(func, ast.Name)
              else f"{names[func.value.id]}.{func.attr}"
              if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id in names
              else None)
    return bool(dotted) and _returns_optional(dotted)


def _consumes_none(node: ast.AST, names: dict[str, str]) -> bool:
    """Whether a node uses the call of an optional aew function in a way None breaks: a subscript, an attribute
    (``.get``), ``in`` (a comparison, or a comprehension's iterable): TypeError or AttributeError on None."""
    if isinstance(node, ast.Subscript | ast.Attribute):
        return _optional_call(node.value, names)
    if isinstance(node, ast.Compare):
        return any(isinstance(op, ast.In | ast.NotIn) and _optional_call(right, names)
                   for op, right in zip(node.ops, node.comparators, strict=True))
    return isinstance(node, ast.comprehension) and _optional_call(node.iter, names)


def ast_sites(source: str) -> set[int]:
    """Lines of each polling call whose lambda reads a file raw, or consumes a read that can return None."""
    tree = ast.parse(source)
    names = _aew_names(tree)
    found = set()
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        for predicate in _predicates(call):
            if any(_raw_read(node) or _consumes_none(node, names) for node in ast.walk(predicate)):
                found.add(call.lineno)
    return found


IMPORT_TEXT = re.compile(r"^\s*from (aew(?:\.\w+)*) import (?:\(([^)]*)\)|([\w ,]+)$)", re.M)
MODULE_TEXT = re.compile(r"^\s*import (aew(?:\.\w+)*) as (\w+)\s*$", re.M)
RAW_TEXT = re.compile(r"\.(?:read_text|read_bytes)\(|(?<![\w.])open\(")  # not `.open(`: the AST rule is the Name only
READ_TEXT = re.compile(r"(?<![\w.)\]])(?:(\w+)\.)?(\w+)\([^()\n]*\)(?:\[|\.\w)")  # `read(x)[`, `read(x).get`
IN_TEXT = re.compile(r"\bin\s+(?:(\w+)\.)?(\w+)\([^()\n]*\)")  # `k in read(x)`, `for k in read(x)`


@functools.cache
def _poll_texts() -> list[re.Pattern[str]]:
    """One expression per place a polling helper takes its predicate: its n-th argument is a lambda (the arguments
    before it simple, with no comma or parenthesis inside), or the keyword it is given by is. The rest of the line is
    the lambda's body."""
    patterns = []
    for name, (positions, keywords) in sorted(poller_params().items()):
        patterns += [re.compile(rf"\b{name}\(\s*(?:[^,()\n]*,\s*){{{n}}}lambda[^:\n]*:(?P<body>[^\n]*)")
                     for n in sorted(positions)]
        patterns += [re.compile(rf"\b{name}\([^\n]*?\b{keyword}\s*=\s*lambda[^:\n]*:(?P<body>[^\n]*)")
                     for keyword in sorted(keywords)]
    return patterns


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
    for pattern in _poll_texts():
        for poll in pattern.finditer(source):
            line = source.count("\n", 0, poll.start()) + 1
            body = poll.group("body")
            if RAW_TEXT.search(body):
                found.add(line)
            for read in (*READ_TEXT.finditer(body), *IN_TEXT.finditer(body)):
                qualifier, function = read.groups()
                dotted = f"{names[qualifier]}.{function}" if qualifier in names else names.get(function) \
                    if not qualifier else None
                if dotted in OPTIONAL:
                    found.add(line)
    return found


@functools.cache
def _test_sites() -> dict[str, tuple[set[int], set[int]]]:
    """Each test file's sites as each detector finds them: ``{path: (by AST, by text)}``. The text detector skips this
    module alone (EXEMPT): the AST one reads it like any other file, so a polled raw read added here is found."""
    sites = {}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        sites[path.relative_to(ROOT).as_posix()] = (
            ast_sites(source), set() if path.resolve() in EXEMPT else text_sites(source))
    return sites


def test_no_polled_predicate_reads_a_file_raw_or_consumes_a_read_that_can_return_none():
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
    # the private pollers; a predicate by keyword, or at the position its poller's definition calls it
    '_wait_for(lambda: p.read_text(), "the file")',
    'bounded_wait("test.x", lambda: p.read_text(), seconds=5)',
    'bounds.bounded_wait("test.x", ready, gone=lambda: p.read_bytes())',
    'bounded_wait("test.x", ready=lambda: open(p).read())',
    'waiting(lambda: p.read_text())',
    '_retrying(lambda: p.read_text())',
    'until(predicate=lambda: p.read_text(), timeout=5)',
    'wait_for(cond=lambda: broker_liveness.read(root)["beat_at"])',
    # a None used another way than by a subscript
    'until(lambda: broker_liveness.read(root).get("closed_at"))',
    'until(lambda: "beat_at" in broker_liveness.read(root))',
    'until(lambda: "x" not in runlog.read_live(d))',
    'until(lambda: [k for k in notify.summary(root)])',
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
    'bounded_wait("test.x", lambda: (read_text_or_none(p) or "").strip(), seconds=5)',
    'until(lambda: "beat_at" in (broker_liveness.read(root) or {}))',
    'until(lambda: (broker_liveness.read(root) or first).get("beat_at"))',
]
BOTH_MISS = [
    "chat.receive(5, gone=lambda: p.read_text())",  # a poller not in POLLERS
    "def ready():\n    return broker_liveness.read(root)['beat_at'] > t\nuntil(ready)",
    'until(lambda: self.store.read()["revision"] > 3)',
    'import aew.harness.runlog\nuntil(lambda: aew.harness.runlog.read_live(d)["prompt_state"])',
    "def ready():\n    return p.read_text().strip()\nuntil(ready)",  # a raw read inside a named function that is polled
    "until(lambda: p.open().read())",  # raw reads of other spellings: the class is the three above
    "until(lambda: io.open(p).read())",
    "pred = lambda: p.read_text()\nuntil(pred)",  # a lambda bound to a name
    'until(lambda: (r := broker_liveness.read(root))["beat_at"] > 1)',  # an aew reader bound by a walrus
    'until(lambda: control(p)["invocations"])',  # a raw read behind a helper the predicate calls (`load_control`)
    "until(cond=lambda: p.read_text())",  # a keyword that `until`'s definition does not call (`wait_for`'s is `cond`)
    "until(lambda: broker_liveness.read(root) > 3)",  # a None consumed by a comparison, arithmetic or a builtin
    "until(lambda: len(broker_liveness.read(root)))",
]
AST_ONLY = [
    'until(lambda: (\n    broker_liveness.read(root)["beat_at"] > t))',
    'until(lambda: broker_liveness.read(project.root())["beat_at"] > t)',
    "until(lambda: (\n    p.read_text().strip()))",
    "until((lambda: p.read_text()), 5)",
    'bounded_wait("t", ready=(lambda: p.read_text()))',  # a keyword's lambda in parentheses
    'bounded_wait(f"t.{name()}", lambda: p.read_text(), seconds=5)',  # an argument before the predicate holds a call
    'until(lambda: "beat_at" in broker_liveness.read(project.root()))',
    'until(lambda: broker_liveness.read(project.root()).get("closed_at"))',
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


def test_each_poller_takes_its_predicate_where_its_definition_calls_it():
    """Read from the definitions under tests/, so a parameter that moves moves the detectors with it. This pins the
    result: a poller added, or one whose predicate moves, has to update it."""
    assert poller_params() == {
        "until": ({0}, {"predicate"}),
        "wait_for": ({0}, {"cond"}),
        "wait_until": ({0}, {"predicate"}),  # no test defines it: the default
        "_wait_for": ({0}, {"predicate"}),
        "bounded_wait": ({1}, {"ready", "gone"}),  # `name` comes first: the predicate is the second argument
        "waiting": ({0}, {"predicate"}),
        "_retrying": ({0}, {"write"}),
    }


def test_the_exempt_module_is_skipped_by_the_text_detector_only(tmp_path, monkeypatch):
    """A polled raw read planted in the exempt module (it plants the banned forms as strings, so the text detector
    cannot read it) is still found by the AST detector, and so by the scan and the agreement test."""
    poller_params()  # derived from the real tree before ROOT moves
    plants = tmp_path / "tests" / "unit" / "plants.py"
    plants.parent.mkdir(parents=True)
    plants.write_text('until(lambda: p.read_text(), 5, "x")\n', encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setitem(globals(), "EXEMPT", {plants.resolve()})
    assert _test_sites.__wrapped__() == {"tests/unit/plants.py": ({1}, set())}


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
