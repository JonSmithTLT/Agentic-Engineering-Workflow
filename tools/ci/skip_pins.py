#!/usr/bin/env python3
"""A platform skip with no pin, or a pin with no test, found by reading the test modules (no test runs).

``assurance`` fails on both (``tools/ci/check_assurance.py``), but only after every shard of the run has finished. This
says the same in the fast lane and in the ``static`` job, from the source.

It reads each test module's ``skipif`` marks: on the test, its class, a case of its ``parametrize``, in place or in a
list the module names, its module's ``pytestmark``, and those a module names (``POSIX_ONLY = pytest.mark.skipif(...)``);
and a test's own
``if <platform>: pytest.skip(...)``. Each condition is worked out for each platform in three values, since
``not linux or which("bwrap") is None`` skips on Windows whatever ``which`` says, and ``linux and geteuid() == 0`` skips
nowhere for certain. So a test that certainly skips on a platform must be pinned under that platform.

What it can't see, which stays ``assurance``'s to catch: a skip in a fixture or a helper the test calls, or nested
deeper in the test; a condition on anything but the platform, such as a tool missing on one runner or
``lead.contained_here()``; a platform constant imported under any name but ``IS_WINDOWS``; a parametrized test's
single cases (a pin of any case counts for the test, and a case's pin needs only the test to exist, not that case); a
test file named ``*_test.py``; and it takes a fixture named ``test_*`` for a test, and ``.skip`` on any object for
``pytest.skip``. The tree has none of those three.

    python tools/ci/skip_pins.py [--skips tests/platform-skips.yaml] [--tests tests]
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "helpers"))
import lanes  # noqa: E402  (tests/helpers/lanes.py: which lane a test file is in)

PLATFORMS = ("linux", "win32")  # the platforms the gate requires (ci.yml's --require)
IMPORTED_WINDOWS = "IS_WINDOWS"  # the one platform constant modules import (from conftest, or aew.util)
# Lanes no required job collects, so `assurance` refuses a pin of theirs as "no longer exists" (review of #394, 2).
NOT_GATED = ("live", "vertical", "discovery")
Names = dict[str, ast.expr]


def _truth(node: ast.expr, platform: str, names: Names, seen: frozenset[str] = frozenset()) -> bool | None:
    """Whether ``node`` holds on ``platform``: ``None`` when reading the source can't say."""
    if isinstance(node, ast.BoolOp):
        values = [_truth(v, platform, names, seen) for v in node.values]
        decisive = isinstance(node.op, ast.Or)  # True decides an `or`, False an `and`
        return decisive if decisive in values else None if None in values else not decisive
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        value = _truth(node.operand, platform, names, seen)
        return None if value is None else not value
    if isinstance(node, ast.Name) and node.id in names and node.id not in seen:
        return _truth(names[node.id], platform, names, seen | {node.id})
    if isinstance(node, ast.Name) and node.id == IMPORTED_WINDOWS:
        return platform == "win32"
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.comparators[0], ast.Constant):
        actual = _platform_value(node.left, platform)
        if actual is not None and isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
            return (actual == node.comparators[0].value) == isinstance(node.ops[0], ast.Eq)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "startswith"
            and len(node.args) == 1 and isinstance(node.args[0], ast.Constant)):
        actual = _platform_value(node.func.value, platform)
        if actual is not None:
            return actual.startswith(node.args[0].value)
    return None


def _platform_value(node: ast.expr, platform: str) -> str | None:
    """What ``sys.platform`` or ``os.name`` is on ``platform``, when ``node`` is one of them."""
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr == "platform" and (_is_name(node.value, "sys") or _is_dunder_import_of_sys(node.value)):
        return platform
    if node.attr == "name" and _is_name(node.value, "os"):
        return "nt" if platform == "win32" else "posix"
    return None


def _is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _is_dunder_import_of_sys(node: ast.expr) -> bool:
    return (isinstance(node, ast.Call) and _is_name(node.func, "__import__") and len(node.args) == 1
            and isinstance(node.args[0], ast.Constant) and node.args[0].value == "sys")


def _skipif_conditions(node: ast.expr, names: Names, seen: frozenset[str] = frozenset()) -> Iterator[ast.expr]:
    """The condition of each ``pytest.mark.skipif`` that ``node`` is, holds in a list, or names."""
    if isinstance(node, (ast.List, ast.Tuple)):
        for item in node.elts:
            yield from _skipif_conditions(item, names, seen)
    elif isinstance(node, ast.Name) and node.id in names and node.id not in seen:
        yield from _skipif_conditions(names[node.id], names, seen | {node.id})
    elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "skipif"
          and node.args):
        yield node.args[0]
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "parametrize":
        for arg in node.args:  # the cases, in place or in a list the module names (review of #394, 3)
            cases = names[arg.id] if isinstance(arg, ast.Name) and arg.id in names else arg
            for param in ast.walk(cases):  # a case's own marks: pytest.param("a_link", marks=pytest.mark.skipif(...))
                if isinstance(param, ast.keyword) and param.arg == "marks":
                    yield from _skipif_conditions(param.value, names, seen)


def _body_skip_conditions(function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[ast.expr]:
    """The test of each top-level ``if`` in the function whose body is only a ``pytest.skip(...)``."""
    for statement in function.body:
        if isinstance(statement, ast.If) and len(statement.body) == 1 and not statement.orelse:
            call = statement.body[0].value if isinstance(statement.body[0], ast.Expr) else None
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "skip":
                yield statement.test


@dataclass(frozen=True)
class Found:
    """A test's id and the platforms it certainly skips on."""

    nid: str
    platforms: frozenset[str]


def scan_module(source: str, path: str) -> list[Found]:
    """Every test of a module (a parametrized test once, without its cases) and where it certainly skips."""
    tree = ast.parse(source)
    names: Names = {t.id: s.value for s in tree.body if isinstance(s, ast.Assign) for t in s.targets
                    if isinstance(t, ast.Name)}

    def platforms(conditions: Iterable[ast.expr]) -> set[str]:
        return {p for c in conditions for p in PLATFORMS if _truth(c, p, names) is True}

    def marks(owner: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        return platforms(c for d in owner.decorator_list for c in _skipif_conditions(d, names))

    def tests(body: list[ast.stmt], prefix: str, inherited: set[str]) -> Iterator[Found]:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                own = marks(node) | platforms(_body_skip_conditions(node))
                yield Found(f"{prefix}::{node.name}", frozenset(inherited | own))
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                class_marks = set(inherited) | marks(node)
                for inner in node.body:  # a class's own `pytestmark`
                    if isinstance(inner, ast.Assign) and any(_is_name(t, "pytestmark") for t in inner.targets):
                        class_marks |= platforms(_skipif_conditions(inner.value, names))
                yield from tests(node.body, f"{prefix}::{node.name}", class_marks)

    module_mark = names.get("pytestmark")
    inherited = platforms(_skipif_conditions(module_mark, names)) if module_mark is not None else set()
    return list(tests(tree.body, path, inherited))


def _gated(path: str) -> bool:
    """Whether a required job can collect this file. A file with no lane by its path gets one from its tests' marks."""
    try:
        return lanes.lane_of(path, ()) not in NOT_GATED
    except lanes.Unclassified:
        return True


def scan(tests_dir: Path, root: Path) -> list[Found]:
    return [found for path in sorted(tests_dir.rglob("test_*.py")) if _gated(path.relative_to(root).as_posix())
            for found in scan_module(path.read_text(encoding="utf-8"), path.relative_to(root).as_posix())]


def pins_of(skips_file: Path) -> dict[str, set[str]]:
    """Each platform's pinned test ids, cases and all."""
    skipped = (yaml.safe_load(skips_file.read_text(encoding="utf-8")) or {}).get("skipped") or {}
    return {platform: set(pins or ()) for platform, pins in skipped.items()}


def problems(found: list[Found], pins: dict[str, set[str]]) -> list[str]:
    """A test that certainly skips on a platform with no pin there, and a pin whose test the source doesn't hold."""
    out = []
    known = {f.nid for f in found}
    for f in found:
        for platform in sorted(f.platforms):
            mine = pins.get(platform, set())
            if f.nid not in mine and not any(p.startswith(f"{f.nid}[") for p in mine):
                out.append(f"{platform}: {f.nid} skips there with no pin: pin it in tests/platform-skips.yaml with a "
                           "reason, or make it run")
    for platform, mine in sorted(pins.items()):
        for pin in sorted(mine):
            if pin.split("[", 1)[0] not in known:
                out.append(f"{platform}: the pin {pin} names a test that no longer exists: remove it")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skips", type=Path, default=ROOT / "tests" / "platform-skips.yaml")
    ap.add_argument("--tests", type=Path, default=ROOT / "tests")
    args = ap.parse_args(argv)
    tests_dir = args.tests.resolve()
    out = problems(scan(tests_dir, tests_dir.parent), pins_of(args.skips))
    for line in out:
        print(line)
    print(f"skip pins: {len(out)} problem(s)")
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
