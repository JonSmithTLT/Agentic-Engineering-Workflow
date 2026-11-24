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
    monkeypatch.setattr(selection, "from_merge", lambda merge, **opts: {TEST})
    assert selection.for_pull_request(event, base, "merge", run_tier, "repo", "1") == ({TEST} if scoped else None)


@pytest.mark.parametrize(("platform", "lane", "event", "drops"), [
    ("win32", "integration", "pull_request", True), ("win32", "regression", "pull_request", True),
    ("win32", "acceptance", "pull_request", False), ("win32", "serial", "pull_request", False),
    ("win32", "integration", "push", False), ("win32", "integration", "schedule", False),
    ("linux", "integration", "pull_request", False),
])
def test_partition_keeps_full_collection_and_scopes_only_eligible_workers(monkeypatch, platform, lane, event, drops):
    from types import SimpleNamespace

    import lanes

    first, second = (f"tests/{lane}/test_{name}.py::test_case" for name in ("one", "two"))
    markers = [SimpleNamespace(name=lane)] if lane in {"acceptance", "serial"} else []
    items = [SimpleNamespace(nodeid=nid, iter_markers=lambda: markers, stash={}) for nid in (first, second)]
    config = SimpleNamespace(getoption=lambda option: "per-run-durations.json", workeroutput={},
                             workerinput={}, hook=SimpleNamespace(pytest_deselected=lambda **kw: None))
    plugin = object.__new__(lanes.LanePlugin)
    plugin.config, plugin.lane, plugin.shard = config, lane, (1, 1)
    plugin._shard_table = lambda: {"windows_omitted": [second.split("::")[0]]}
    monkeypatch.setattr(lanes, "sys", SimpleNamespace(platform=platform))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    plugin.pytest_collection_modifyitems(config, items)
    assert config.workeroutput["aew_collected"] == [first, second]
    assert [item.nodeid for item in items] == ([first] if drops else [first, second])


def test_assurance_recomputes_missing_nodes_by_platform_lane_and_module():
    from test_ci_tools import check_assurance, report

    keep, omit, accept = TEST + "::test_keep", OTHER + "::test_omit", OTHER + "::test_accept"
    all_nodes = {keep: "integration", omit: "regression", accept: "acceptance"}

    def lane_report(platform, passed):
        return report(platform, "example", dict.fromkeys(passed, "passed"), collected=list(all_nodes), lanes=all_nodes)

    windows = lane_report("win32", [keep, accept])
    linux = lane_report("linux", all_nodes)

    def check(*reports, omitted=None):
        return check_assurance.check(list(reports), {}, ["linux", "win32"], windows_omitted=omitted)[0]

    assert not check(linux, windows, omitted={OTHER})
    assert any(f"win32: never ran: {omit}" in p for p in check(linux, windows))
    assert any(f"linux: never ran: {omit}" in p for p in check(lane_report("linux", [keep, accept]), windows,
                                                               omitted={OTHER}))
    for nid in (keep, accept):
        assert any(f"never ran: {nid}" in p for p in check(linux, lane_report("win32", []), omitted={OTHER}))
    assert any("do not record" in p for p in check(linux, {**windows, "lanes": {}}, omitted={OTHER}))


def test_sizing_omits_a_windows_lane_only_when_no_test_module_is_selected(tmp_path, monkeypatch):
    from test_ci_tools import shard_plan

    for path in (TEST, OTHER):
        target = tmp_path / path
        target.parent.mkdir(parents=True)
        target.touch()
    monkeypatch.setattr(shard_plan, "ROOT", tmp_path)
    sizings = [shard_plan.Sizing(platform, lane, 8, 400, 300.0, 900.0) for platform in ("win32", "linux")
               for lane in ("integration", "regression", "acceptance")]
    shard_plan.resize_windows(sizings, {"platforms": {"win32": {}}}, {TEST}, {})
    assert [s.shards for s in sizings] == [0, 8, 8, 8, 8, 8]
    kept = tmp_path / "tests/integration/test_new.py"
    kept.touch()
    sizings[0].shards = 8
    shard_plan.resize_windows(sizings, {"platforms": {"win32": {}}}, {TEST}, {})
    assert sizings[0].shards == 8
    table = {"platforms": {"win32": {"tests/integration/test_new.py::test_one": 1.0}}}
    shard_plan.resize_windows(sizings, table, {TEST}, {})
    assert 1 <= sizings[0].shards < 8
