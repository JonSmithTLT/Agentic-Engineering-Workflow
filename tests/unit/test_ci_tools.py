"""The CI assurance check and the durations refresher (tools/ci): the merge gate must catch every way a
sharded run can lose, duplicate, skip or fail a test."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "ci" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_assurance = _load("check_assurance")
update_durations = _load("update_durations")

ALL = ["tests/unit/test_a.py::t1", "tests/unit/test_a.py::t2", "tests/regression/test_b.py::t3",
       "tests/integration/test_c.py::posix_only"]
SKIP_ID = "tests/integration/test_c.py::posix_only"
EXPECT = {"schema": check_assurance.SKIPS_SCHEMA, "skipped": {"win32": {SKIP_ID: "needs POSIX"}, "linux": {}},
          "xfail": {}}


def report(platform: str, lane: str, results: dict[str, str], shard: str | None = None, **kw) -> dict:
    return {"schema": check_assurance.REPORT_SCHEMA, "platform": platform, "lane": lane, "shard": shard,
            "exitstatus": 0, "python": "3.x", "wall_s": 1.0, "collected": list(ALL),
            "results": {n: {"outcome": o, "duration": 0.5} for n, o in results.items()}, **kw}


def good_run() -> list[dict]:
    runs = []
    for platform in ("linux", "win32"):
        skip = "skipped" if platform == "win32" else "passed"
        runs += [report(platform, "fast", {ALL[0]: "passed", ALL[1]: "passed"}),
                 report(platform, "regression", {ALL[2]: "passed"}, shard="1/1"),
                 report(platform, "integration", {SKIP_ID: skip})]
    return runs


def problems(runs, expect=EXPECT, required=("linux", "win32")) -> list[str]:
    return check_assurance.check(runs, expect, list(required))[0]


def test_a_complete_run_passes():
    assert problems(good_run()) == []


@pytest.mark.parametrize(("mutate", "expected"), [
    (lambda r: r[1]["results"].clear(), "linux: never ran: tests/regression/test_b.py::t3"),
    (lambda r: r.append(copy.deepcopy(r[1])), "linux: ran 2 times: tests/regression/test_b.py::t3"),
    (lambda r: r[0]["results"][ALL[0]].update(outcome="failed"), "linux: failed: tests/unit/test_a.py::t1"),
    (lambda r: r[0]["results"][ALL[0]].update(outcome="error"), "linux: error: tests/unit/test_a.py::t1"),
    (lambda r: r[0]["results"][ALL[0]].update(outcome="skipped"), "linux: unexpected skip: tests/unit/test_a.py::t1"),
    (lambda r: r[0]["results"][ALL[0]].update(outcome="xfailed"), "linux: xfailed but not pinned"),
    (lambda r: r[5]["results"][SKIP_ID].update(outcome="passed"), "win32: pinned skip now passed"),
    (lambda r: r[1]["collected"].pop(), "linux: jobs collected different test sets"),
    (lambda r: r[3].update(exitstatus=1), "win32: session win32/fast exited 1"),
    (lambda r: r[0]["results"].update({"tests/unit/test_z.py::ghost": {"outcome": "passed", "duration": 0}}),
     "linux: ran but was not collected: tests/unit/test_z.py::ghost"),
    (lambda r: [r.pop() for _ in range(3)], "win32: no lane reports"),
], ids=["missing", "duplicate", "failed", "error", "unexpected-skip", "unpinned-xfail", "pinned-skip-ran",
        "collection-differs", "session-failed", "not-collected", "platform-missing"])
def test_every_gap_in_the_envelope_is_a_problem(mutate, expected):
    runs = good_run()
    mutate(runs)
    found = problems(runs)
    assert any(p.startswith(expected) for p in found), found


def test_a_pinned_skip_for_a_vanished_test_is_stale():
    expect = copy.deepcopy(EXPECT)
    expect["skipped"]["win32"]["tests/unit/test_gone.py::x"] = "old"
    assert "win32: pinned skip no longer exists: tests/unit/test_gone.py::x" in problems(good_run(), expect)


def test_a_pinned_xfail_is_allowed():
    runs = good_run()
    runs[0]["results"][ALL[0]]["outcome"] = "xfailed"
    expect = copy.deepcopy(EXPECT)
    expect["xfail"] = {"linux": {ALL[0]: "known, tracked"}}
    assert problems(runs, expect) == []


def test_cli_reads_a_report_tree_and_writes_the_summary(tmp_path):
    for i, r in enumerate(good_run()):
        (tmp_path / "reports" / f"job{i}").mkdir(parents=True)
        (tmp_path / "reports" / f"job{i}" / "lane.json").write_text(json.dumps(r), encoding="utf-8")
    (tmp_path / "skips.yaml").write_text(yaml.safe_dump(EXPECT), encoding="utf-8")
    summary = tmp_path / "summary.md"
    rc = check_assurance.main([str(tmp_path / "reports"), "--skips", str(tmp_path / "skips.yaml"),
                               "--summary", str(summary)])
    assert rc == 0 and "**PASS**" in summary.read_text(encoding="utf-8")
    (tmp_path / "reports" / "job0" / "lane.json").unlink()
    assert check_assurance.main([str(tmp_path / "reports"), "--skips", str(tmp_path / "skips.yaml")]) == 1


def test_the_repository_skip_manifest_is_well_formed():
    data = check_assurance.load_expectations(ROOT / "tests" / "platform-skips.yaml")
    assert set(data["skipped"]) == {"win32", "linux"} and all(data["skipped"]["win32"].values())


def test_durations_merge_updates_and_prunes():
    current = {"platforms": {"win32": {ALL[0]: 9.0, "tests/unit/test_gone.py::x": 1.0}, "darwin": {"k": 1.0}}}
    merged = update_durations.merge(current, [report("win32", "fast", {ALL[0]: "passed", SKIP_ID: "skipped"})])
    assert merged["schema"] == "aew/test-durations/v1"
    assert merged["platforms"]["win32"] == {ALL[0]: 0.5}  # refreshed; the vanished test and the skip are gone
    assert merged["platforms"]["darwin"] == {"k": 1.0}  # platforms without reports are kept
