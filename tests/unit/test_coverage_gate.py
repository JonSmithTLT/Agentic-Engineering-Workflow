"""The coverage ratchet over both operating systems (register E23; tools/ci/coverage_gate.py): Windows data combines
with Linux data, each OS's marked code is measured on its own OS, and a drop below the baseline fails."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import coverage
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("coverage_gate", ROOT / "tools" / "ci" / "coverage_gate.py")
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules["coverage_gate"] = gate
spec.loader.exec_module(gate)

MODULE = """import sys


def only_windows():  # pragma: windows-only
    return "w"


def only_posix():  # pragma: posix-only
    return "p"


def both():
    return "b"
"""
# Statements: 1 (import), 4 and 5 (windows-only), 8 and 9 (posix-only), 12 and 13.
LINUX_LINES = [1, 4, 8, 9, 12, 13]  # the definitions run on import; the POSIX body and `both` run
WINDOWS_LINES = [1, 4, 5, 8, 12, 13]  # the Windows body and `both` run

RCFILE = ROOT / "pyproject.toml"  # the repository's own exclusion markers and path mapping are what is tested


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A checkout with one marked module, and a data directory laid out as CI downloads its artifacts."""
    (tmp_path / "src" / "aew").mkdir(parents=True)
    (tmp_path / "src" / "aew" / "plat.py").write_text(MODULE, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(gate.OTHER_OS_ENV, raising=False)
    return tmp_path


def record(data_dir: Path, artifact: str, recorded_path: str, lines: list[int]) -> None:
    folder = data_dir / artifact
    folder.mkdir(parents=True, exist_ok=True)
    data = coverage.CoverageData(basename=str(folder / ".coverage"), suffix=True)
    data.add_lines({recorded_path: lines})
    data.write()


def lay_out(root: Path, *, windows: bool = True) -> Path:
    data = root / "data"
    record(data, "coverage-core-Linux", "/home/runner/work/aew/aew/src/aew/plat.py", LINUX_LINES)
    if windows:
        record(data, "coverage-core-Windows", "D:\\a\\aew\\aew\\src\\aew\\plat.py", WINDOWS_LINES)
    return data


def run(project: Path, data: Path, baseline: dict, *extra: str) -> tuple[int, str]:
    (project / "baseline.json").write_text(json.dumps({"schema": gate.SCHEMA, **baseline}), encoding="utf-8")
    summary = project / "summary.md"
    summary.unlink(missing_ok=True)
    rc = gate.main([str(data), "--baseline", str(project / "baseline.json"), "--rcfile", str(RCFILE),
                    "--summary", str(summary), *extra])
    return rc, summary.read_text(encoding="utf-8")


def total(summary: str, name: str = "aew/(top)") -> str:
    return next(line for line in summary.splitlines() if line.startswith(f"| {name} |"))


def test_windows_data_combines_with_linux_data_and_each_os_measures_its_own_code(project):
    rc, summary = run(project, lay_out(project), {"line": 100.0, "branch": 100.0}, "--require", "Linux,Windows")
    assert rc == 0, summary
    # Combined: nothing excluded, every block covered by the OS it runs on (7 statements, all covered).
    assert total(summary).startswith("| aew/(top) | 100.0% |") and "| 7 |" in total(summary)
    # Each OS alone excludes the other's marked code: 5 statements each, all covered.
    per_os = summary.split("### Each OS alone")[1].split("###")[0]
    assert "| aew/(top) | 100.0% | 100.0% |" in per_os
    # The marked file is listed, with its combined and per-OS coverage.
    listing = summary.split("### Files with Windows-only or POSIX-only code")[1]
    assert "| `plat.py` | posix, windows | 100.0% | 100.0% | 100.0% |" in listing


def test_the_windows_lanes_raise_what_linux_alone_cannot_reach(project):
    nothing = {"line": 0.0, "branch": 0.0}
    _, linux_only = run(project, lay_out(project, windows=False), nothing)
    # The Windows-only body is counted (the combined view excludes neither OS) and nothing has run it: 6 of 7 lines.
    assert total(linux_only).startswith("| aew/(top) | 85.7% |") and "| 7 |" in total(linux_only)
    _, both = run(project, lay_out(project), nothing)  # the Windows data joins the Linux data
    assert total(both).startswith("| aew/(top) | 100.0% |")


def test_a_drop_below_the_baseline_fails_the_ratchet(project):
    data = lay_out(project)
    rc, summary = run(project, data, {"line": 100.0, "branch": 100.0})
    assert rc == 0 and "Coverage holds the baseline." in summary
    # A test that stopped running: the Windows-only body (line 5) is no longer covered.
    next((data / "coverage-core-Windows").glob(".coverage.*")).unlink()
    record(data, "coverage-core-Windows", "D:\\a\\aew\\aew\\src\\aew\\plat.py", [1, 4, 8, 12, 13])
    rc, summary = run(project, data, {"line": 100.0, "branch": 100.0})
    assert rc == 1 and "**Coverage dropped:** line coverage 85.71% is below the baseline 100.00%" in summary


def test_a_drop_inside_the_tolerance_passes(project):
    rc, _ = run(project, lay_out(project), {"line": 100.2, "branch": 100.0})
    assert rc == 0


def test_a_missing_operating_system_fails_when_it_is_required(project):
    data = lay_out(project, windows=False)
    rc, summary = run(project, data, {"line": 0.0, "branch": 0.0}, "--require", "Linux,Windows")
    assert rc == 1 and "Windows: no coverage data" in summary


def test_data_not_split_by_os_is_one_view_with_the_configured_exclusion(project):
    data = project / "flat"
    record(data, ".", "/home/runner/work/aew/aew/src/aew/plat.py", LINUX_LINES)
    rc, summary = run(project, data, {"line": 100.0, "branch": 100.0})
    assert rc == 0 and "Each OS alone" not in summary
    assert "| 5 |" in total(summary)  # the Windows-only block is excluded by default, as before


def test_update_writes_the_combined_baseline(project):
    rc, _ = run(project, lay_out(project), {"line": 0.0, "branch": 0.0}, "--update")
    written = json.loads((project / "baseline.json").read_text(encoding="utf-8"))
    assert rc == 0 and written["line"] == 100.0 and written["measured"].startswith("Linux and Windows lanes combined")


def test_the_repository_baseline_is_well_formed():
    baseline = json.loads((ROOT / "tests" / "coverage-baseline.json").read_text(encoding="utf-8"))
    assert baseline["schema"] == gate.SCHEMA and 0 < baseline["branch"] <= baseline["line"] <= 100
