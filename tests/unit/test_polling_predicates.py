"""A polling predicate never subscripts a read that can return None.

A record another thread or process rewrites can read back as None for a moment on Windows: replacing a file that a
reader has open fails with a sharing violation, and AEW's guarded readers (``broker_liveness.read``,
``runlog.read_live``, ...) return None for any OSError. A predicate polled by ``until`` that subscripts such a read,
``read(root)["field"]``, then raises TypeError at that moment instead of answering "not yet", and the test fails at
random (#237's run 40035060397, attempt 2, ``test_broker_liveness_is_local_and_beats_every_poll``). The class: a lambda
passed to a polling helper (``until``, ``wait_for``, ``wait_until``) that subscripts the call of an aew function whose
return annotation admits None at its top level. Guard the read instead: ``(read(root) or last)["field"]``.

Two detectors written separately enumerate it over every test file, and must agree:
- an AST one, which resolves the call through the module's own aew imports and reads the function's annotation;
- a text one: a regular expression for the predicate, against the names of the functions in src/aew whose return
  annotation, as written, ends in ``| None``.

What both miss (pinned below): a predicate that is a named function rather than a lambda, and a reader reached through
an object (``self.store.read``) or a module imported without an alias (``aew.harness.runlog.read_live``). Such a
predicate is a defect the reviewer reads for; neither detector claims it. A lambda spread over several lines, and a read
whose argument is itself a call (``read(path(x))["k"]``), are seen by the AST detector only: the scan still fails on
them, and so does the agreement test.

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

ROOT = Path(__file__).resolve().parents[2]
EXEMPT = {Path(__file__).resolve()}  # this module plants the banned forms below
POLLERS = {"until", "wait_for", "wait_until"}


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


def ast_sites(source: str) -> set[int]:
    """Lines of each polling call whose lambda subscripts a read that can return None."""
    tree = ast.parse(source)
    names = _aew_names(tree)
    found = set()
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call) and _poller(call)):
            continue
        for node in ast.walk(call.args[0]):
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
        for read in READ_TEXT.finditer(poll.group("body")):
            qualifier, function = read.groups()
            dotted = f"{names[qualifier]}.{function}" if qualifier in names else names.get(function) if not qualifier \
                else None
            if dotted in OPTIONAL:
                found.add(source.count("\n", 0, poll.start()) + 1)
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


def test_no_polling_predicate_subscripts_a_read_that_can_return_none():
    found = {f"{path}:{line}" for path, (by_ast, by_text) in _test_sites().items() for line in by_ast | by_text}
    assert not found, f"guard the read, (read(...) or last)[...]: a racing read is None for a moment: {sorted(found)}"


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
]
PLANTED_RIGHT = [
    'until(lambda: (broker_liveness.read(root) or first)["beat_at"] > t)',
    'until(lambda: (broker_liveness.read(root) or {}).get("closed_at"))',
    'until(lambda: runlog.observed_status(d)[0] == "done")',
    'record = broker_liveness.read(root)["beat_at"]',  # not polled: a deterministic read fails loudly, not at random
]
BOTH_MISS = [
    "def ready():\n    return broker_liveness.read(root)['beat_at'] > t\nuntil(ready)",
    'until(lambda: self.store.read()["revision"] > 3)',
    'import aew.harness.runlog\nuntil(lambda: aew.harness.runlog.read_live(d)["prompt_state"])',
]
AST_ONLY = [
    'until(lambda: (\n    broker_liveness.read(root)["beat_at"] > t))',
    'until(lambda: broker_liveness.read(project.root())["beat_at"] > t)',
]


@pytest.mark.parametrize("line", PLANTED_WRONG)
def test_both_detectors_see_each_unguarded_read_in_a_polled_lambda(line):
    source = IMPORTS + line + "\n"
    assert ast_sites(source) == text_sites(source) == {LINE}


@pytest.mark.parametrize("line", PLANTED_RIGHT)
def test_neither_detector_flags_a_guarded_or_unpolled_read(line):
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
