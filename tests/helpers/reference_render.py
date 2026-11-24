"""The as-built reference rendered in memory once per test process, for every fast-lane module that reads the whole
render (``tests/unit/test_reference.py``, ``test_reference_machine_controls.py``, ``test_systems.py``).

A render reads and analyses the whole source tree (about 5 s on a workstation, several times that on a CI runner under
coverage). Each of those modules used to keep its own per-process copy, so an xdist worker that ran tests of all three
rendered three times, for the same bytes (the CI headroom work, 2026-11-07). The tests that are about rendering again
(two renders in one process, fresh processes under other hash seeds, an archived tree, another family order) still
render for themselves and compare against this one.

The bytes are returned as the generator gives them; callers must not mutate the mapping (it is a fresh ``dict`` per
call, over the same immutable ``bytes``).

The parsed source tree is shared the same way (:func:`context`): every module that builds or reads a family holds it
for the whole session, as a module global does.
"""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

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


@cache
def context() -> Any:
    """This checkout's source tree, parsed once per process (``reference_families.common.Context``), for every test
    module that builds or reads a family. Its analyses built once (``Context.once``: the parsed program, the writers'
    analysis) are shared as one render shares them.

    Each of those modules used to hold a ``Context`` of its own in a module global, so for the rest of the session: a
    serial session that ran them all kept twelve parses of the package (about a million objects each), and its
    interpreter's collections at exit then outlasted the session deadline's margin (the nightly's reference shards,
    2026-11-17 to 11-22, register E3). Callers must not mutate what it holds."""
    common, _pages, _families = tool()._families()
    return common.Context(ROOT)
