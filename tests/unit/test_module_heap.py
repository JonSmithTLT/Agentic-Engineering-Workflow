"""The module heap guard (register E363; tests/helpers/module_heap.py): a test module that keeps a large build for
itself fails, at import in any session and after its tests in a serial one, while the same build shared through
``shared_setup.once`` or a session-scoped fixture passes. #553's leak (a parse of src/aew per module, in a module
global) is the first case: it fails here the day it lands."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import module_heap
import pytest
import shared_setup
from conftest import IS_WINDOWS

HELPERS = Path(module_heap.__file__).resolve().parent
# Well over the budget: a list of one-element lists keeps two to three blocks per element.
BIG = module_heap.BUDGET_BLOCKS

CONFTEST = f'''
import sys
sys.path.insert(0, {str(HELPERS)!r})
import module_heap


def pytest_configure(config):
    module_heap.configure(config)
'''
SHARED = '''
import shared_setup


@shared_setup.once
def big():
    return [[i] for i in range({big})]
'''


def scratch(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "proj"
    for rel, text in {"pyproject.toml": "[tool.pytest.ini_options]\n", "tests/conftest.py": CONFTEST,
                      "tests/shared_big.py": SHARED.format(big=BIG), **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def inner_pytest(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "AEW_"))}
    env["PYTHONPATH"] = os.pathsep.join([str(root / "tests"), env.get("PYTHONPATH", "")])
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           *args, "tests"], cwd=root, env=env, capture_output=True, text=True, timeout=300, **kwargs)


def test_a_module_that_keeps_a_large_build_in_a_global_fails_its_collection_naming_itself(tmp_path):
    """#553's shape: the build happens when the module is imported, so in every process that collects it."""
    root = scratch(tmp_path, {
        "tests/test_hog.py": f"BIG = [[i] for i in range({BIG})]\n\ndef test_reads():\n    assert BIG\n",
        "tests/test_fine.py": "def test_fine():\n    pass\n",
    })
    proc = inner_pytest(root, "-p", "no:xdist")
    assert proc.returncode == pytest.ExitCode.INTERRUPTED, proc.stdout + proc.stderr  # a collection error
    assert "module heap guard: tests/test_hog.py kept" in proc.stdout and "at import" in proc.stdout
    assert "test_fine.py kept" not in proc.stdout


def test_a_module_whose_tests_fill_a_cache_of_its_own_fails_a_serial_session_naming_itself(tmp_path):
    root = scratch(tmp_path, {
        "tests/test_hog.py": ("from functools import cache\n\n@cache\ndef big():\n"
                              f"    return [[i] for i in range({BIG})]\n\ndef test_reads():\n    assert big()\n"),
        "tests/test_fine.py": "def test_fine():\n    pass\n",
    })
    proc = inner_pytest(root, "-p", "no:xdist")
    assert proc.returncode == pytest.ExitCode.TESTS_FAILED, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout
    assert "module heap guard: tests/test_hog.py kept" in proc.stdout and "after its tests" in proc.stdout
    assert "test_fine.py kept" not in proc.stdout


@pytest.mark.parametrize("when", ["at import", "in a test"])
def test_the_same_build_shared_once_per_process_is_never_charged_to_the_modules_that_read_it(tmp_path, when):
    use = "VALUE = shared_big.big()\n\ndef test_reads():\n    assert VALUE\n" if when == "at import" else (
        "def test_reads():\n    assert shared_big.big()\n")
    root = scratch(tmp_path, {f"tests/test_{n}.py": "import shared_big\n" + use for n in ("a", "b", "c")})
    proc = inner_pytest(root, "-p", "no:xdist")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "3 passed" in proc.stdout and "module heap guard" not in proc.stdout


def test_a_session_fixture_is_shared_setup_and_a_module_fixture_is_torn_down_before_its_module_is_measured(tmp_path):
    fixtures = ("import pytest\n\n@pytest.fixture(scope='session')\ndef shared():\n"
                f"    return [[i] for i in range({BIG})]\n\n"
                "@pytest.fixture(scope='module')\ndef own():\n"
                f"    return [[i] for i in range({BIG})]\n")
    root = scratch(tmp_path, {
        "tests/conftest.py": CONFTEST + "\n" + fixtures,
        "tests/test_a.py": "def test_a(shared, own):\n    assert shared and own\n",
        "tests/test_b.py": "def test_b(shared, own):\n    assert shared and own\n",
    })
    proc = inner_pytest(root, "-p", "no:xdist")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout and "module heap guard" not in proc.stdout


@pytest.mark.skipif(importlib.util.find_spec("xdist") is None, reason="pytest-xdist not installed (extra: parallel)")
def test_under_xdist_every_worker_refuses_a_module_global_build_and_nothing_else_is_attributed(tmp_path):
    root = scratch(tmp_path, {
        "tests/test_hog.py": f"BIG = [[i] for i in range({BIG})]\n\ndef test_reads():\n    assert BIG\n",
        "tests/test_cache.py": ("from functools import cache\n\n@cache\ndef big():\n"
                                f"    return [[i] for i in range({BIG})]\n\ndef test_reads():\n    assert big()\n"),
    })
    proc = inner_pytest(root, "-n", "2")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "module heap guard: tests/test_hog.py kept" in proc.stdout
    assert "test_cache.py kept" not in proc.stdout


def test_a_shared_build_is_recorded_once_and_a_nested_one_is_not_counted_twice():
    calls = []

    @shared_setup.once
    def inner() -> list[list[int]]:
        calls.append("inner")
        return [[i] for i in range(1000)]

    @shared_setup.once
    def outer() -> int:
        calls.append("outer")
        return len(inner())

    before = shared_setup.owners()
    assert outer() == outer() == 1000 and inner() is inner()
    assert calls == ["outer", "inner"]
    added = {k: v for k, v in shared_setup.owners().items() if before.get(k) != v}
    assert list(added) == [f"{__name__}.{outer.__qualname__}"]
