"""Windows PR selection, including the fail-closed paths of the import walk."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "tools" / "ci" / "windows_selection.py"
sys.path.insert(0, str(PATH.parent))
spec = importlib.util.spec_from_file_location("windows_selection", PATH)
assert spec and spec.loader
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)

TEST = "tests/integration/test_actual.py"
OTHER = "tests/regression/test_other.py"
SOURCE = "src/example/shared.py"


def test_both_added_and_removed_windows_lines_reach_the_test_through_imports():
    sources = {TEST: "from fixture import build", "tests/helpers/fixture.py": "from example import shared",
               "src/example/__init__.py": "", SOURCE: "", OTHER: "import io"}
    assert selection.selected_modules(sources, {SOURCE: ["if sys.platform == 'win32':"]}, set()) == {TEST}
    assert selection.selected_modules(sources, {SOURCE: ["answer = 42"]}, set()) == set()


def test_changed_modules_and_registered_modules_are_selected_without_platform_lines():
    sources = {TEST: "", OTHER: "", "tests/integration/test_unused.py": ""}
    assert selection.selected_modules(sources, {TEST: []}, {OTHER}) == {TEST, OTHER}


@pytest.mark.parametrize("source", [
    "from missing import thing", "if:", "__import__(name)",
    "from importlib import import_module as resolve; resolve(name)", "from ...broken import x",
])
def test_a_module_with_an_unknown_dependency_is_selected(source):
    sources = {TEST: source, OTHER: "import io", SOURCE: ""}
    assert selection.selected_modules(sources, {SOURCE: ["os.replace(source, dest)"]}, set()) == {TEST}


def test_package_initializers_conftest_and_relative_imports_are_in_the_closure():
    sources = {TEST: "from example.sub import use", OTHER: "", "src/example/__init__.py": "",
               "src/example/sub/__init__.py": "", "src/example/sub/use.py": "from .. import shared",
               SOURCE: "", "tests/integration/conftest.py": "import fixture", "tests/helpers/fixture.py": ""}
    for path in ("src/example/__init__.py", SOURCE, "tests/helpers/fixture.py"):
        assert selection.selected_modules(sources, {path: ["raise PermissionError"]}, set()) == {TEST}


def test_deleted_dependency_and_removed_import_still_select_surviving_test():
    base = {TEST: "from fixture import build", "tests/helpers/fixture.py": "from example import shared",
            SOURCE: "if sys.platform == 'win32': pass", OTHER: ""}
    head = {TEST: base[TEST], "tests/helpers/fixture.py": "build = None"}
    changes = {SOURCE: [base[SOURCE]], "tests/helpers/fixture.py": ["build = None"], OTHER: [""]}
    assert selection.select_change(base, head, changes, {OTHER}) == {TEST}


def test_nested_observed_nodes_remain_selected_in_a_real_merge(tmp_path, monkeypatch):
    import subprocess

    def git(*args):
        return subprocess.check_output(["git", "-c", "user.name=fixture", "-c", "user.email=f@example.invalid",
                                        *args], text=True).strip()

    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")
    module = tmp_path / OTHER
    module.parent.mkdir(parents=True)
    module.write_text("def test_check(): pass\n", encoding="utf-8")
    register = tmp_path / "tests/flake-register.yaml"
    register.write_text("schema: aew/flake-register/v1\nentries:\n- evidence:\n  - nodes:\n    - " + OTHER
                        + "::test_check\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "pr")
    (tmp_path / "readme.md").write_text("update", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "documentation")
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "pr", "-m", "merge")
    assert selection.from_merge("HEAD") == {OTHER}


@pytest.mark.parametrize(("event", "base", "run_tier", "label", "trailer", "scoped"), [
    ("pull_request", "main", "full", [], False, True),
    ("pull_request", "main", "full", ["full-ci"], False, False),
    ("pull_request", "main", "full", [], True, False),
    ("pull_request", "main", "full", None, False, False),
    ("pull_request", "main", "full", [], None, False),
    ("pull_request", "main", "docs", [], False, False),
    ("pull_request", "other", "full", [], False, False),
    ("push", "main", "full", [], False, False),
    ("schedule", "main", "full", [], False, False),
])
def test_only_unforced_pull_requests_can_narrow_windows(monkeypatch, event, base, run_tier, label, trailer, scoped):
    monkeypatch.setattr(selection.tier, "live_labels", lambda *args: label)
    monkeypatch.setattr(selection.tier, "forced_by_trailer", lambda merge: trailer)
    monkeypatch.setattr(selection, "from_merge", lambda merge: {TEST})
    assert selection.for_pull_request(event, base, "merge", run_tier, "repo", "1") == ({TEST} if scoped else None)
