"""The history search's clock seam (the test-timing audit's seam #5; flake step 1, B1).

The dashboard's history search reads its deadline from a clock and judges it, and the catch-up's ``budget_s``, by the
same clock, down to the engine's substrate. The clock is a keyword parameter with the real monotonic clock as its
default, so that a test can drive it. These pin that production never chooses it: every default is
``time.monotonic``, every parameter is keyword-only, and no call in ``src/aew`` passes a clock except the five that
hand their own caller's clock on. Nothing an agent can set (a request field, a CLI option, an environment variable, a
configuration key) reaches it.
"""

from __future__ import annotations

import ast
import inspect
import time
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


def _seam_calls() -> tuple[set[tuple[str, str, str]], list[str]]:
    """Every call in ``src/aew`` to a seam name that passes ``clock=``, and every one that forwards ``**`` keywords."""
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

    for path in sorted(SRC.rglob("*.py")):
        visit(path.relative_to(SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8")), ())
    return passed, forwarded


def test_no_call_in_src_chooses_the_search_clock_it_only_passes_its_callers_on():
    """A new call that passes a clock (a production caller choosing one, or a value read from a request, the
    environment or configuration) fails here by name, and so does a call that could carry one in ``**`` keywords.
    ``DashboardServer``'s own callers (the ``serve`` command's service) pass none, so the root is its default."""
    passed, forwarded = _seam_calls()
    assert passed == PASS_THROUGH
    assert forwarded == []
