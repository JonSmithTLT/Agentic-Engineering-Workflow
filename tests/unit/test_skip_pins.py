"""The fast check of a platform skip with no pin, and of a pin with no test (tools/ci/skip_pins.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("skip_pins", ROOT / "tools" / "ci" / "skip_pins.py")
assert _spec and _spec.loader
skip_pins = importlib.util.module_from_spec(_spec)
sys.modules["skip_pins"] = skip_pins
_spec.loader.exec_module(skip_pins)

PATH = "tests/integration/test_x.py"


def skips_on(source: str, test: str = "test_a") -> set[str]:
    found = {f.nid.rsplit("::", 1)[-1]: f.platforms for f in skip_pins.scan_module(source, PATH)}
    return set(found[test])


def test_the_tree_has_no_unpinned_platform_skip_and_no_pin_without_its_test():
    """The check itself, on this checkout: fails in the gate and the fast lane, before any lane job has run."""
    found = skip_pins.scan(ROOT / "tests", ROOT)
    problems = skip_pins.problems(found, skip_pins.pins_of(ROOT / "tests" / "platform-skips.yaml"))
    assert problems == [], "\n".join(problems)
    assert sum(1 for f in found if f.platforms) > 200, "the scan stopped seeing the tree's skips"


def test_it_catches_the_skip_a_new_contained_test_inherits_from_its_module():
    """How a new test in a Linux-only module skips on Windows: its module's mark, with a condition on a tool too. The
    tool can't change that Windows skips."""
    source = ('pytestmark = [pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("bwrap") is None, '
              'reason="r"), pytest.mark.autopsy]\ndef test_a(tmp_path): pass\n')
    found = skip_pins.scan_module(source, PATH)
    assert skips_on(source) == {"win32"}
    assert skip_pins.problems(found, {"win32": set()}) == [
        f"win32: {PATH}::test_a skips there with no pin: pin it in tests/platform-skips.yaml with a reason, or make it "
        "run"]
    assert skip_pins.problems(found, {"win32": {f"{PATH}::test_a"}}) == []


@pytest.mark.parametrize(("source", "platforms"), [
    ('@pytest.mark.skipif(sys.platform == "win32", reason="r")\ndef test_a(): pass\n', {"win32"}),
    ('@pytest.mark.skipif(sys.platform != "win32", reason="r")\ndef test_a(): pass\n', {"linux"}),
    ('@pytest.mark.skipif(os.name == "nt", reason="r")\ndef test_a(): pass\n', {"win32"}),
    ('@pytest.mark.skipif(not __import__("sys").platform.startswith("linux"), reason="r")\ndef test_a(): pass\n',
     {"win32"}),
    ('@pytest.mark.skipif(IS_WINDOWS, reason="r")\ndef test_a(): pass\n', {"win32"}),
    ('IS_LINUX = sys.platform == "linux"\n@pytest.mark.skipif(not IS_LINUX, reason="r")\ndef test_a(): pass\n',
     {"win32"}),
    ('POSIX = pytest.mark.skipif(sys.platform == "win32", reason="r")\n@POSIX\ndef test_a(): pass\n', {"win32"}),
    ('@pytest.mark.parametrize("c", ["x", pytest.param("y", marks=pytest.mark.skipif(sys.platform == "win32", '
     'reason="r"))])\ndef test_a(c): pass\n', {"win32"}),
    ('CASES = ["x", pytest.param("y", marks=pytest.mark.skipif(sys.platform == "win32", reason="r"))]\n'
     '@pytest.mark.parametrize("c", CASES)\ndef test_a(c): pass\n', {"win32"}),
    ('@pytest.mark.parametrize("c", argvalues=["x", pytest.param("y", marks=pytest.mark.skipif('
     'sys.platform == "win32", reason="r"))])\ndef test_a(c): pass\n', {"win32"}),
    ('def test_a():\n    if sys.platform == "win32":\n        pytest.skip("r")\n', {"win32"}),
    ('@pytest.mark.skipif(sys.platform == "win32", reason="r")\nclass TestK:\n    def test_a(self): pass\n', {"win32"}),
    ('class TestK:\n    pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="r")\n'
     '    def test_a(self): pass\n', {"win32"}),
], ids=["equal", "not_equal", "os_name", "dunder_import", "imported_constant", "module_constant", "named_mark",
        "parametrize_case", "named_cases", "argvalues", "in_the_body", "class_decorator", "class_pytestmark"])
def test_every_way_the_tree_declares_a_platform_skip_is_seen(source, platforms):
    assert skips_on(source) == platforms


@pytest.mark.parametrize("condition", [
    'sys.platform.startswith("linux") and os.geteuid() == 0',  # only as root: CI's runners aren't
    'sys.platform != "win32" and os.geteuid() == 0',
    'shutil.which("bwrap") is None',
    'lead.contained_here()',
])
def test_a_condition_the_source_cannot_settle_asks_for_no_pin(condition):
    """Certain skips only: a pin that a run wouldn't skip fails `assurance` the other way, so this never demands one."""
    assert skips_on(f'@pytest.mark.skipif({condition}, reason="r")\ndef test_a(): pass\n') == set()


def test_a_pin_of_a_case_counts_for_its_parametrized_test():
    found = [skip_pins.Found(f"{PATH}::test_a", frozenset({"win32"}))]
    assert skip_pins.problems(found, {"win32": {f"{PATH}::test_a[x]"}}) == []


def test_a_pin_under_the_other_platform_does_not_count():
    found = [skip_pins.Found(f"{PATH}::test_a", frozenset({"win32"}))]
    assert any("skips there with no pin" in p for p in skip_pins.problems(found, {"linux": {f"{PATH}::test_a"}}))


@pytest.mark.parametrize("pin", [f"{PATH}::test_gone", f"{PATH}::test_gone[x]"])
def test_a_pin_of_a_test_that_no_longer_exists_fails(pin):
    found = [skip_pins.Found(f"{PATH}::test_a", frozenset())]
    assert skip_pins.problems(found, {"win32": {pin}}) == [
        f"win32: the pin {pin} names a test that no longer exists: remove it"]


def test_a_test_no_required_job_collects_needs_no_pin_since_assurance_would_refuse_one(tmp_path):
    """Review of #394, 2: a guard asking for a pin `assurance` calls stale would leave no state of the file green."""
    tests = tmp_path / "tests"
    source = '@pytest.mark.skipif(sys.platform == "win32", reason="r")\ndef test_a(): pass\n'
    for rel in ("live/test_m.py", "discovery/test_m.py", "acceptance/test_vertical_path.py", "unit/test_m.py",
                "acceptance/test_m.py"):
        (tests / rel).parent.mkdir(parents=True, exist_ok=True)
        (tests / rel).write_text(source, encoding="utf-8")
    assert sorted(f.nid for f in skip_pins.scan(tests, tmp_path)) == ["tests/acceptance/test_m.py::test_a",
                                                                       "tests/unit/test_m.py::test_a"]


def test_the_command_says_its_problems_and_fails(tmp_path, capsys):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_m.py").write_text('@pytest.mark.skipif(os.name == "nt", reason="r")\ndef test_a(): pass\n',
                                     encoding="utf-8")
    skips = tmp_path / "skips.yaml"
    skips.write_text("schema: aew/platform-skips/v1\n", encoding="utf-8")
    assert skip_pins.main(["--skips", str(skips), "--tests", str(tests)]) == 1
    assert "win32: tests/test_m.py::test_a skips there" in capsys.readouterr().out
    skips.write_text("skipped:\n  linux: {}\n  win32:\n    tests/test_m.py::test_a: why\n", encoding="utf-8")
    assert skip_pins.main(["--skips", str(skips), "--tests", str(tests)]) == 0


def test_its_usage_line_works_from_the_tree_root(tmp_path, monkeypatch):
    """Review of #394, 4: a relative `--tests tests`, as its docstring gives it."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_m.py").write_text("def test_a(): pass\n", encoding="utf-8")
    (tmp_path / "skips.yaml").write_text("schema: aew/platform-skips/v1\nskipped: {win32: {}, linux: {}}\n",
                                         encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert skip_pins.main(["--skips", "skips.yaml", "--tests", "tests"]) == 0
