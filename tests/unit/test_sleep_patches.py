"""A test patches ``time.sleep`` only through ``sleep_patch.patch_sleep``, which leaves other threads their real sleep.

``module.time`` is the one shared ``time`` module, so patching ``sleep`` there reaches every thread in the worker. On
#237's run 40035060397 a thread an earlier test left running had its sleeps counted by ``test_store_read_committed``
(15 for 7 retries), and a no-op patch makes such a thread spin. The class is a test that patches ``sleep`` on the shared
module directly. Two detectors written separately enumerate it over every test file, and must agree:
- an AST one: ``setattr``/``patch.object`` on a target named ``time`` (``time`` or ``<x>.time``) with ``"sleep"``, and
  ``setattr``/``patch`` with the string ``"time.sleep"``;
- a text one: regular expressions for the same spellings.

What both miss (pinned below): the ``time`` module bound to another name (``import time as clock``), and a target
built at run time (``getattr``). Such a patch is a defect the reviewer reads for; neither detector claims it.
"""

from __future__ import annotations

import ast
import re
import threading
import time
import types
from pathlib import Path

import pytest
from sleep_patch import patch_sleep

TESTS = Path(__file__).resolve().parents[1]
# This module plants the banned spellings below; the helper is the one sanctioned patch.
EXEMPT = {Path(__file__).resolve(), (TESTS / "helpers" / "sleep_patch.py").resolve()}

TEXT_FORMS = (
    re.compile(r"""\bsetattr\(\s*(?:[\w.]+\.)?time\s*,\s*["']sleep["']"""),
    re.compile(r"""\b(?:setattr|patch)\(\s*["']time\.sleep["']"""),
    re.compile(r"""\bpatch\.object\(\s*(?:[\w.]+\.)?time\s*,\s*["']sleep["']"""),
)


def _names_time(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "time") or (isinstance(node, ast.Attribute)
                                                                   and node.attr == "time")


def _const(node: ast.expr, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def ast_patches(source: str) -> set[int]:
    """Lines of each call that patches ``sleep`` on the shared ``time`` module."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
        owner = func.value.attr if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute) else (
            func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else "")
        first = node.args[0]
        second = node.args[1] if len(node.args) > 1 else None
        if name == "setattr" and second is not None and _names_time(first) and _const(second, "sleep"):
            found.add(node.lineno)
        elif name in ("setattr", "patch") and _const(first, "time.sleep"):
            found.add(node.lineno)
        elif name == "object" and owner == "patch" and second is not None and _names_time(first) \
                and _const(second, "sleep"):
            found.add(node.lineno)
    return found


def text_patches(source: str) -> set[int]:
    """The same class, by text: the line where each match starts."""
    return {source.count("\n", 0, m.start()) + 1 for rx in TEXT_FORMS for m in rx.finditer(source)}


def _test_sources():
    for path in sorted(TESTS.rglob("*.py")):
        if path.resolve() not in EXEMPT:
            yield path, path.read_text(encoding="utf-8")


def test_no_test_patches_sleep_on_the_shared_time_module():
    found = {f"{path.relative_to(TESTS).as_posix()}:{line}" for path, src in _test_sources()
             for line in ast_patches(src) | text_patches(src)}
    assert not found, f"use sleep_patch.patch_sleep instead (it keeps other threads' sleep real): {sorted(found)}"


def test_the_two_detectors_agree_on_every_test_file():
    disagree = {path.relative_to(TESTS).as_posix(): (sorted(ast_patches(src)), sorted(text_patches(src)))
                for path, src in _test_sources() if ast_patches(src) != text_patches(src)}
    assert not disagree


PLANTED_WRONG = [
    'monkeypatch.setattr(time, "sleep", lambda s: None)',
    "monkeypatch.setattr(store.time, 'sleep', sleeps.append)",
    'monkeypatch.setattr(a.b.time, "sleep", f)',
    'monkeypatch.setattr("time.sleep", f)',
    'setattr(time, "sleep", f)',
    'mock.patch("time.sleep")',
    'patch("time.sleep", new=f)',
    'mock.patch.object(time, "sleep")',
    'patch.object(mod.time, "sleep", f)',
]
PLANTED_RIGHT = [
    "patch_sleep(monkeypatch, store)",
    'monkeypatch.setattr(store, "_run", f)',
    'monkeypatch.setattr(time, "monotonic", f)',
    'monkeypatch.setattr(store.os, "replace", f)',
]
BOTH_MISS = [
    'monkeypatch.setattr(clock, "sleep", f)',  # import time as clock
    'monkeypatch.setattr(getattr(store, "time"), "sleep", f)',
]


@pytest.mark.parametrize("line", PLANTED_WRONG)
def test_both_detectors_see_each_banned_spelling(line):
    assert ast_patches(line) == text_patches(line) == {1}


@pytest.mark.parametrize("line", PLANTED_RIGHT)
def test_neither_detector_flags_a_sanctioned_or_unrelated_patch(line):
    assert ast_patches(line) == text_patches(line) == set()


@pytest.mark.parametrize("line", BOTH_MISS)
def test_what_both_detectors_miss_is_pinned(line):
    assert ast_patches(line) == text_patches(line) == set()


def test_the_detectors_report_the_line_a_multiline_call_starts_on():
    src = "x = 1\nmonkeypatch.setattr(\n    store.time,\n    'sleep',\n    f,\n)\n"
    assert ast_patches(src) == text_patches(src) == {2}


def test_patch_sleep_records_only_its_own_thread_and_other_threads_still_sleep(monkeypatch):
    shared = types.SimpleNamespace(time=time)  # a module whose `time` is the shared one, as every module's is
    sleeps = patch_sleep(monkeypatch, shared)
    slept: list[float] = []

    def other():
        start = time.monotonic()
        time.sleep(0.05)
        slept.append(time.monotonic() - start)

    thread = threading.Thread(target=other)
    thread.start()
    time.sleep(30)  # recorded and skipped: this is the patching thread
    thread.join(10)
    assert sleeps == [30] and len(slept) == 1 and slept[0] >= 0.04
