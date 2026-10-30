"""The history search's clock seam (the test-timing audit's seam #5; flake step 1, B1).

The dashboard's history search reads its deadline from a clock and judges it, and the catch-up's ``budget_s``, by the
same clock, down to the engine's substrate. The clock is a keyword parameter with the real monotonic clock as its
default, so that a test can drive it. These pin that production does not choose it: every default is
``time.monotonic``, every parameter is keyword-only, and every direct call in ``src/aew`` that names a seam passes
``clock=`` only where it hands its own caller's clock on (the five pass-throughs), and never forwards ``**`` keywords
into one.

What the scan does not see (#294 review, m1): a seam called through an alias or a ``functools.partial``, a seam
reached through ``getattr`` by name, a ``clock`` or ``_clock`` attribute written after construction, and code outside
``src/aew``. None exists at the review's head; a change that adds one is for its review to catch.
"""

from __future__ import annotations

import ast
import inspect
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

import aew
from aew.dashboard.projections import Projector
from aew.dashboard.server import DashboardServer
from aew.engine.api import Engine
from aew.engine.history_ops import HistoryCommands
from aew.engine.recall import Substrate

SRC = Path(aew.__file__).resolve().parent
SEAM = {"DashboardServer": DashboardServer.__init__, "Projector": Projector.__init__,
        "history_search_committed": Engine.history_search_committed, "search": Substrate.search,
        "catch_up": Substrate.catch_up}
# Each call that passes ``clock=`` on, as (file, enclosing function, the value passed): its own caller's clock.
PASS_THROUGH = {
    ("dashboard/server.py", "DashboardServer._respond", "self.clock"),
    ("dashboard/projections.py", "Projector.history_search", "self.clock"),
    ("engine/api.py", "Engine.history_search_committed", "clock"),
    ("engine/history_ops.py", "HistoryCommands.history_search_committed", "clock"),
    ("engine/recall.py", "Substrate.search", "clock"),
}


@pytest.mark.parametrize("function", [*SEAM.values(), HistoryCommands.history_search_committed],
                         ids=[*SEAM, "HistoryCommands.history_search_committed"])
def test_the_search_clock_is_keyword_only_and_the_real_monotonic_clock_by_default(function):
    clock = inspect.signature(function).parameters["clock"]
    assert clock.kind is inspect.Parameter.KEYWORD_ONLY and clock.default is time.monotonic


def test_a_substrate_judges_by_the_real_clock_until_a_search_passes_one():
    assert Substrate(Path("unused"), lambda entry: {})._clock is time.monotonic


def _src() -> Iterator[tuple[str, str]]:
    for path in sorted(SRC.rglob("*.py")):
        yield path.relative_to(SRC).as_posix(), path.read_text(encoding="utf-8")


def _seam_calls(sources: Iterable[tuple[str, str]]) -> tuple[set[tuple[str, str, str]], list[str]]:
    """Every direct call by a seam's name that passes ``clock=``, and every one that forwards ``**`` keywords, in
    ``sources`` (each a path relative to ``src/aew`` and its text)."""
    passed: set[tuple[str, str, str]] = set()
    forwarded: list[str] = []

    def visit(rel: str, node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = (*scope, child.name)
            if isinstance(child, ast.Call):
                func = child.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if name in SEAM:
                    for kw in child.keywords:
                        if kw.arg == "clock":
                            passed.add((rel, ".".join(scope), ast.unparse(kw.value)))
                        elif kw.arg is None:
                            forwarded.append(f"{rel}:{child.lineno}")
            visit(rel, child, inner)

    for rel, text in sources:
        visit(rel, ast.parse(text), ())
    return passed, forwarded


def _violations(sources: Iterable[tuple[str, str]]) -> list[str]:
    passed, forwarded = _seam_calls(sources)
    return ([f"passes a clock it was not handed: {site}" for site in sorted(passed - PASS_THROUGH)]
            + [f"no longer hands its caller's clock on: {site}" for site in sorted(PASS_THROUGH - passed)]
            + [f"forwards ** keywords into a seam: {where}" for where in forwarded])


def test_no_direct_call_in_src_chooses_the_search_clock_it_only_passes_its_callers_on():
    """A new direct call that passes a clock, a pass-through that stops passing one, or a call that forwards ``**``
    keywords into a seam fails here by name. ``DashboardServer``'s own caller (the ``serve`` command's service) passes
    none, so the root is its default. The scan's blind spots are in the module's docstring."""
    assert _violations(_src()) == []


# The five pass-throughs, planted as the smallest sources the scan reads as each one.
PLANTED = {
    "dashboard/server.py": "class DashboardServer:\n    def _respond(self):\n"
                           "        return P.Projector(snapshot, clock=self.clock)\n",
    "dashboard/projections.py": "class Projector:\n    def history_search(self):\n"
                                "        return self.engine.history_search_committed(state, clock=self.clock)\n",
    "engine/api.py": "class Engine:\n    def history_search_committed(self, *, clock):\n"
                     "        return self._history.history_search_committed(state, clock=clock)\n",
    "engine/history_ops.py": "class HistoryCommands:\n    def history_search_committed(self, *, clock):\n"
                             "        return self._substrate().search(query, clock=clock)\n",
    "engine/recall.py": "class Substrate:\n    def search(self, *, clock):\n"
                        "        return self.catch_up(root, tail, clock=clock)\n",
}
SERVICE = "dashboard/service.py"


def test_the_scan_reads_planted_pass_throughs_as_right():
    assert _violations(PLANTED.items()) == []


@pytest.mark.parametrize("call, violation", [
    ("DashboardServer(engine, authenticator=table, clock=lambda: 0.0)",
     "passes a clock it was not handed: ('dashboard/service.py', 'Service.__init__', 'lambda: 0.0')"),
    ("DashboardServer(engine, authenticator=table, **options)",
     "forwards ** keywords into a seam: dashboard/service.py:3"),
], ids=["a_literal_clock", "a_keyword_forward"])
def test_the_scan_names_a_planted_caller_that_chooses_or_forwards_a_clock(call, violation):
    service = f"class Service:\n    def __init__(self, engine, table, options):\n        self.server = {call}\n"
    assert _violations([*PLANTED.items(), (SERVICE, service)]) == [violation]


def test_the_scan_names_a_planted_pass_through_that_no_longer_passes_the_clock():
    stopped = PLANTED["engine/history_ops.py"].replace(", clock=clock)", ")")
    assert _violations({**PLANTED, "engine/history_ops.py": stopped}.items()) == [
        "no longer hands its caller's clock on: ('engine/history_ops.py', "
        "'HistoryCommands.history_search_committed', 'clock')"]
