"""The as-built reference rendered in memory once per test process, for every fast-lane module that reads the whole
render (``tests/unit/test_reference.py``, ``test_reference_machine_controls.py``, ``test_systems.py``).

A render reads and analyses the whole source tree (about 5 s on a workstation, several times that on a CI runner under
coverage). Each of those modules used to keep its own per-process copy, so an xdist worker that ran tests of all three
rendered three times, for the same bytes (the CI headroom work, 2026-11-07). The tests that are about rendering again
(two renders in one process, fresh processes under other hash seeds, an archived tree, another family order) still
render for themselves and compare against this one.

The bytes are returned as the generator gives them; callers must not mutate the mapping (it is a fresh ``dict`` per
call, over the same immutable ``bytes``).
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def tool() -> ModuleType:
    """``tools/reference.py``, imported by its path once per process under the name the test modules and
    ``tools/systems.py`` use (``reference_tool``)."""
    if "reference_tool" not in sys.modules:
        spec = importlib.util.spec_from_file_location("reference_tool", ROOT / "tools" / "reference.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["reference_tool"] = module
        spec.loader.exec_module(module)
    return sys.modules["reference_tool"]


@cache
def _rendered() -> dict[str, bytes]:
    return tool().render_files(ROOT)


def rendered() -> dict[str, bytes]:
    """Every file ``docs/reference/`` holds, by name, as this checkout's code renders it (the index included)."""
    return dict(_rendered())
