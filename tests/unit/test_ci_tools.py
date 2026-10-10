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
tier = _load("tier")
update_durations = _load("update_durations")
cost_record = _load("cost_record")

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


def sharded_reference_run(shards: int = 3) -> list[dict]:
    """The nightly reference run: no lane, ``shards`` shards per platform, every test in exactly one shard."""
    runs = []
    for platform in ("linux", "win32"):
        skip = "skipped" if platform == "win32" else "passed"
        for k in range(1, shards + 1):
            mine = {n: ("passed" if n != SKIP_ID else skip) for i, n in enumerate(ALL) if i % shards == k - 1}
            runs.append(report(platform, None, mine, shard=f"{k}/{shards}"))
    return runs


def test_a_complete_sharded_reference_run_passes():
    assert problems(sharded_reference_run()) == []


@pytest.mark.parametrize("dropped", [0, 1, 2], ids=["first", "middle", "last"])
def test_a_dropped_reference_shard_fails_the_aggregate(dropped):
    """The nightly aggregate (E26): a shard whose job did not run or upload must never read as a green run."""
    runs = sharded_reference_run()
    runs.pop(3 + dropped)  # a Windows shard (the Linux shards come first)
    found = problems(runs)
    assert f"win32: all: shard {dropped + 1}/3 has no report" in "\n".join(found), found
    assert any(p.startswith("win32: never ran: ") for p in found), found  # its tests are missing too


def test_a_dropped_reference_shard_is_a_problem_even_when_it_held_no_tests():
    runs = sharded_reference_run(shards=5)  # more shards than tests: shards 4 and 5 are empty
    runs.pop(4)  # linux shard 5
    assert any(p.startswith("linux: all: shard 5/5 has no report") for p in problems(runs))


def test_shard_reports_that_disagree_on_the_count_are_a_problem():
    runs = sharded_reference_run()
    runs[0]["shard"] = "1/2"
    assert any(p.startswith("linux: all: shard reports disagree on the shard count") for p in problems(runs))


def test_a_failed_reference_shard_fails_the_aggregate():
    runs = sharded_reference_run()
    runs[4].update(exitstatus=1)
    assert any(p.startswith("win32: session win32/all shard 2/3 exited 1") for p in problems(runs))


def test_the_nightly_reference_job_is_sharded_and_aggregated():
    """Structure of .github/workflows/nightly.yml: every OS lists shards 1..N of one N, each under a 60 minute
    timeout, and the aggregate (which `report` waits for) requires both platforms."""
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8"))["jobs"]
    reference = jobs["reference"]
    assert reference["timeout-minutes"] <= 60, "split the job further instead of raising the timeout (E26)"
    per_os: dict[str, list[tuple[int, int]]] = {}
    for entry in reference["strategy"]["matrix"]["include"]:
        per_os.setdefault(entry["os"], []).append((entry["shard"], entry["of"]))
    assert set(per_os) == {"ubuntu-latest", "windows-latest"}
    for os_name, shards in per_os.items():
        counts = {n for _, n in shards}
        assert len(counts) == 1, f"{os_name}: shards disagree on the shard count"
        assert sorted(k for k, _ in shards) == list(range(1, counts.pop() + 1)), f"{os_name}: a shard is missing"
    steps = "\n".join(str(step.get("run", "")) for step in reference["steps"])
    assert "--shard ${{ matrix.shard }}/${{ matrix.of }}" in steps and "-p no:xdist" in steps
    assert "matrix.shard" in steps.split("--lane-report")[1], "each shard needs its own lane report"
    uploads = [step["with"]["name"] for step in reference["steps"] if "upload-artifact" in step.get("uses", "")]
    assert uploads and all("matrix.shard" in name for name in uploads)
    aggregate = jobs["reference-assurance"]
    assert aggregate["needs"] == ["reference"] and aggregate["if"] == "always()"
    runs = "\n".join(str(step.get("run", "")) for step in aggregate["steps"])
    assert "check_assurance.py reference-reports" in runs and "--require linux,win32" in runs
    assert "needs.reference.result" in runs
    assert "reference-assurance" in jobs["report"]["needs"]


SERIAL_ID = ALL[2]  # stands for a `serial`-marked test in the nightly's extra-interpreter run


def sharded_extra_run(shards: int = 2) -> list[dict]:
    """The nightly extra-interpreter run: ``-m "not serial"`` in ``shards`` shards, then the serial lane once."""
    runs = []
    for platform in ("linux", "win32"):
        skip = "skipped" if platform == "win32" else "passed"
        rest = [n for n in ALL if n != SERIAL_ID]
        for k in range(1, shards + 1):
            mine = {n: ("passed" if n != SKIP_ID else skip) for i, n in enumerate(rest) if i % shards == k - 1}
            runs.append(report(platform, None, mine, shard=f"{k}/{shards}"))
        runs.append(report(platform, "serial", {SERIAL_ID: "passed"}))
    return runs


def test_a_sharded_extra_run_with_its_serial_lane_passes():
    assert problems(sharded_extra_run()) == []


def test_an_extra_run_whose_serial_lane_did_not_report_fails():
    """The serial tests are deselected from every shard: without the serial lane's report they never ran."""
    runs = [r for r in sharded_extra_run() if not (r["platform"] == "win32" and r["lane"] == "serial")]
    assert f"win32: never ran: {SERIAL_ID}" in problems(runs)


def test_the_nightly_extra_interpreter_job_is_sharded_and_aggregated():
    """Structure of nightly.yml's `matrix-extra`: per OS, shards 1..N of one N over everything but the serial tests,
    under xdist and a 60 minute timeout; the serial lane once per OS without xdist; every report uploaded; and an
    aggregate that `report` waits for, requiring both platforms."""
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8"))["jobs"]
    extra = jobs["matrix-extra"]
    assert extra["timeout-minutes"] <= 60, "split the job further instead of raising the timeout"
    per_os: dict[str, list[tuple[int, int]]] = {}
    pythons: dict[str, set[str]] = {}
    for entry in extra["strategy"]["matrix"]["include"]:
        per_os.setdefault(entry["os"], []).append((entry["shard"], entry["of"]))
        pythons.setdefault(entry["os"], set()).add(entry["python"])
    # The interpreter each OS does not use on pull requests (strategy §4, "Nightly extra").
    assert pythons == {"ubuntu-latest": {"3.13"}, "windows-latest": {"3.11"}}
    for os_name, shards in per_os.items():
        counts = {n for _, n in shards}
        assert len(counts) == 1, f"{os_name}: shards disagree on the shard count"
        assert sorted(k for k, _ in shards) == list(range(1, counts.pop() + 1)), f"{os_name}: a shard is missing"
    runs = [step for step in extra["steps"] if "run" in step and "pytest" in step["run"]]
    sharded = [s["run"] for s in runs if "--shard" in s["run"]]
    serial = [s for s in runs if "--lane serial" in s["run"]]
    assert len(sharded) == 1 and len(serial) == 1
    assert "--shard ${{ matrix.shard }}/${{ matrix.of }}" in sharded[0] and '-m "not serial"' in sharded[0]
    assert "-n auto" in sharded[0] and "matrix.shard" in sharded[0].split("--lane-report")[1]
    assert "-p no:xdist" in serial[0]["run"] and "--lane-report" in serial[0]["run"]
    assert serial[0]["if"].startswith("matrix.shard == 1 && "), "the serial lane runs exactly once per OS"
    uploads = [step for step in extra["steps"] if "upload-artifact" in step.get("uses", "")]
    assert len(uploads) == 1 and "matrix.shard" in uploads[0]["with"]["name"] and uploads[0]["if"] == "always()"
    aggregate = jobs["matrix-extra-assurance"]
    assert aggregate["needs"] == ["matrix-extra"] and aggregate["if"] == "always()"
    pattern = next(s["with"]["pattern"] for s in aggregate["steps"] if "download-artifact" in s.get("uses", ""))
    assert pattern == "nightly-extra-*" and not pattern.startswith("nightly-reference")
    checks = "\n".join(str(step.get("run", "")) for step in aggregate["steps"])
    assert "check_assurance.py extra-reports" in checks and "--require linux,win32" in checks
    assert "needs.matrix-extra.result" in checks
    assert "matrix-extra-assurance" in jobs["report"]["needs"]


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


# ------------------------------------------------------------------ the tiered gate (CI redesign P1)

LANE_OF = {ALL[0]: "fast", ALL[1]: "serial", ALL[2]: "regression", SKIP_ID: "integration"}


def docs_tier_run(with_lanes: bool = True) -> list[dict]:
    """A docs-tier run: only the core jobs (fast, then serial) on each OS."""
    extra = {"lanes": dict(LANE_OF)} if with_lanes else {}
    runs = []
    for platform in ("linux", "win32"):
        runs += [report(platform, "fast", {ALL[0]: "passed"}, **extra),
                 report(platform, "serial", {ALL[1]: "passed"}, **extra)]
    return runs


@pytest.mark.parametrize(("paths", "expected"), [
    (["docs/README.md"], "docs"),
    (["docs/design/requirements-ledger.yaml", "docs/implementation/future-work.yaml"], "docs"),
    (["AGENTS.md", "CLAUDE.md", "README.md", "eval/m3/README.md", "web/docs/notes.md"], "docs"),
    (["web/src/App.tsx", "docs/README.md"], "web"),
    (["web/package-lock.json"], "web"),
    (["docs/design/dashboard-api-v1-provisional.yaml"], "full"),  # the contract code reads
    (["web/docs/c0-approval.json"], "full"),  # its approval, read by the dashboard server
    (["src/aew/README.md"], "full"),  # Markdown under a code root is not documentation
    (["tests/fixtures/notes.md"], "full"),
    (["tools/ci/tier.py"], "full"),
    (["docs/README.md", "src/aew/cli/main.py"], "full"),
    ([".github/workflows/ci.yml"], "full"),
    (["pyproject.toml"], "full"),
    ([".gitleaksignore"], "full"),
    ([], "full"),  # an empty diff proves nothing
    (["Src/aew/notes.md"], "full"),  # a Windows checkout puts it in src/ (review of PR #99, finding 5)
    (["TESTS/fixture.md"], "full"),
    (["Web/Docs/C0-Approval.json"], "full"),
    (["DOCS/README.md"], "docs"),
], ids=lambda v: v if isinstance(v, str) else ",".join(v)[:40] or "empty")
def test_the_tier_is_the_widest_any_changed_path_needs(paths, expected):
    assert tier.decide("pull_request", paths, "main") == expected


@pytest.mark.parametrize("event", ["push", "merge_group", "workflow_dispatch", "schedule", ""])
def test_only_a_pull_request_may_take_a_reduced_tier(event):
    assert tier.decide(event, ["docs/README.md"], "main") == "full"


def test_the_command_line_passes_the_base_branch(tmp_path):
    """The base branch reaches the decision from the command line (PR #99 re-review, B): a docs-only change is docs
    only into main, and an omitted base is full."""
    changed = tmp_path / "changed.txt"
    changed.write_text("docs/README.md\n", encoding="utf-8")
    for base, expected in (("main", "docs"), ("feature", "full"), (None, "full")):
        out = tmp_path / f"out-{base}"
        argv = ["--event", "pull_request", "--paths-file", str(changed), "--github-output", str(out)]
        assert tier.main(argv + (["--base-ref", base] if base else [])) == 0
        assert f"tier={expected}\n" in out.read_text(encoding="utf-8"), base


def test_a_pull_request_into_another_branch_is_full():
    """It can be retargeted to main without a new run, so its run must already be full (review of PR #99, 6)."""
    assert tier.decide("pull_request", ["docs/README.md"], "main") == "docs"
    for base in ("impl/f15-1-broker-cli", "", "Main"):
        assert tier.decide("pull_request", ["docs/README.md"], base) == "full", base


def test_a_rename_out_of_the_code_is_full_tier(tmp_path, monkeypatch):
    """With git's default rename detection, moving src/aew/m.py to docs/m.md lists only docs/m.md: the diff must
    name both sides (review of PR #99, finding 2). Real git, real commits."""
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=tmp_path, check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    (tmp_path / "src" / "aew").mkdir(parents=True)
    (tmp_path / "src" / "aew" / "m.py").write_text("x = 1\n" * 20, encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "docs").mkdir()
    git("mv", "src/aew/m.py", "docs/m.md")
    git("commit", "-q", "-m", "move")
    monkeypatch.chdir(tmp_path)
    paths = tier.changed_paths(base, git("rev-parse", "HEAD"))
    assert paths is not None and "src/aew/m.py" in paths, paths
    assert tier.decide("pull_request", paths, "main") == "full"


GREEN = {"changes": "success", "core": "success", "lanes": "success", "web": "success", "static": "success"}
REDUCED = {**GREEN, "lanes": "skipped"}


@pytest.mark.parametrize(("tier_name", "results", "ok"), [
    ("full", GREEN, True),
    ("docs", REDUCED, True),
    ("web", REDUCED, True),
    ("web", {**REDUCED, "web": "failure"}, False),
    ("full", {**GREEN, "web": "failure"}, False),
    ("docs", {**REDUCED, "core": "failure"}, False),
    ("docs", {**REDUCED, "changes": "failure"}, False),
    ("docs", GREEN, False),  # a reduced tier whose lanes ran: the tier and the jobs disagree
    ("full", REDUCED, False),  # the full tier with its lanes skipped
    ("", {**REDUCED, "changes": "failure"}, False),  # the tier unknown: everything required
    ("", REDUCED, False),  # ... the lanes too, though every other job succeeded (PR #99 re-review, A)
    ("full", {k: v for k, v in GREEN.items() if k != "static"}, False),  # a needed job missing
])
def test_the_gate_requires_every_needed_job_in_every_tier(tier_name, results, ok):
    """Every needed job, any of which failing fails the gate (review of PR #99, finding 1: a shell && chain followed
    by another line let a failing web, core or changes job pass)."""
    assert (tier.job_problems(tier_name, results) == []) is ok
    jobs = ",".join(f"{k}={v}" for k, v in results.items())
    assert (tier.main(["--jobs-for", tier_name, "--jobs", jobs]) == 0) is ok


def test_a_diff_that_cannot_be_computed_is_full(tmp_path, monkeypatch):
    assert tier.decide("pull_request", None, "main") == "full"
    assert tier.changed_paths("", "abc") is None and tier.changed_paths("0" * 40, "abc") is None
    monkeypatch.chdir(tmp_path)  # not a repository: git fails
    assert tier.changed_paths("abc", "def") is None


def test_every_repository_file_read_outside_the_core_lanes_is_full_tier():
    """A repository file that code, a non-core test, a helper, a CI tool or an eval driver names by its path is an
    input to more than the core lanes, whatever it looks like: changing it must run the full gate (review of PR #99,
    finding 4). Both spellings count: a "docs/x/y.md" literal and Path parts ("docs" / "x" / "y.md"). Paths that do
    not exist here (discovery's conventions for other projects, fixture projects) are not ours. The fast lane's own
    readers (tests/unit, the spec pin) run in every tier and are left out."""
    import re

    sources = [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").rglob("*.py"), *(ROOT / "eval").rglob("*.py"),
               ROOT / "tests" / "conftest.py", *(ROOT / "tests" / "helpers").rglob("*.py"),
               *(ROOT / "tests" / "integration").rglob("*.py"), *(ROOT / "tests" / "regression").rglob("*.py"),
               *(ROOT / "tests" / "acceptance").rglob("*.py")]
    literal = re.compile(r'"((?:docs|web|eval)/[^"*?\n]+)"')
    parts = re.compile(r'"(docs|web|eval)"((?:\s*/\s*"[^"\n]+")+)')
    # Readers that run only in the core lanes, or never: the register tool is exercised by tests/unit/test_register.py
    # and the frontend importer by tests/unit/test_dashboard_static.py (both fast lane); eval/reviews holds archived
    # review probes kept as they ran, which nothing executes.
    core_only = {ROOT / "tools" / "register.py", ROOT / "tools" / "ci" / "tier.py",
                 ROOT / "tools" / "dashboard" / "import_build.py"}  # exercised by tests/unit/test_dashboard_static.py
    archived = ROOT / "eval" / "reviews"
    named: set[str] = set()
    for f in sources:
        if f in core_only or archived in f.parents:
            continue
        text = f.read_text(encoding="utf-8")
        named |= {m.group(1) for m in literal.finditer(text)}
        named |= {"/".join([m.group(1), *re.findall(r'"([^"]+)"', m.group(2))]) for m in parts.finditer(text)}
    ours = sorted(p for p in named if (ROOT / p).is_file())
    assert "docs/design/dashboard-api-v1-provisional.yaml" in ours
    assert [p for p in ours if tier.classify_path(p) != "full"] == []


def test_a_complete_docs_tier_run_passes():
    assert check_assurance.check(docs_tier_run(), EXPECT, ["linux", "win32"], "docs")[0] == []


def test_the_docs_tier_still_needs_every_fast_and_serial_test():
    runs = docs_tier_run()
    runs[1]["results"].clear()  # linux serial ran nothing
    assert "linux: never ran: tests/unit/test_a.py::t2" in check_assurance.check(
        runs, EXPECT, ["linux", "win32"], "docs")[0]


def test_a_reduced_tier_without_recorded_lanes_fails_closed():
    found = check_assurance.check(docs_tier_run(with_lanes=False), EXPECT, ["linux", "win32"], "docs")[0]
    assert any("needs each test's lane" in p for p in found), found


def test_the_full_tier_requires_every_lane():
    assert any("never ran" in p for p in check_assurance.check(docs_tier_run(), EXPECT, ["linux", "win32"])[0])


def test_the_cli_refuses_a_reduced_tier_on_a_push(tmp_path):
    for i, r in enumerate(docs_tier_run()):
        (tmp_path / "reports" / f"job{i}").mkdir(parents=True)
        (tmp_path / "reports" / f"job{i}" / "lane.json").write_text(json.dumps(r), encoding="utf-8")
    (tmp_path / "skips.yaml").write_text(yaml.safe_dump(EXPECT), encoding="utf-8")
    base = [str(tmp_path / "reports"), "--skips", str(tmp_path / "skips.yaml"), "--tier", "docs"]
    assert check_assurance.main([*base, "--event", "pull_request"]) == 0
    assert check_assurance.main([*base, "--event", "push"]) == 1
    assert check_assurance.main([*base, "--event", "merge_group"]) == 1


def test_ci_runs_the_lanes_only_in_the_full_tier_and_assurance_recomputes_the_tier():
    """Structure of .github/workflows/ci.yml: the tier job feeds the lanes and the gate, the gate recomputes it, and a
    reduced tier passes only with the lanes skipped."""
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = wf["jobs"]
    assert "merge_group" in wf[True] and "push" in wf[True]  # PyYAML reads the `on:` key as True
    assert "tools/ci/tier.py" in jobs["changes"]["steps"][-1]["run"]
    assert jobs["lanes"]["needs"] == "changes" and jobs["lanes"]["if"] == "needs.changes.outputs.tier == 'full'"
    assert "needs" not in jobs["core"] and "needs" not in jobs["static"]  # core and static run in every tier
    gate = jobs["assurance"]
    assert set(gate["needs"]) == {"changes", "core", "lanes", "web", "static"} and gate["if"] == "always()"
    reports = next(s for s in gate["steps"] if "check_assurance.py" in str(s.get("run", "")))
    assert "if" not in reports  # the lane-report check always runs (review of PR #99, finding 1)
    final = gate["steps"][-1]
    assert final["if"] == "always()" and "tools/ci/tier.py --jobs-for" in final["run"]
    for step in gate["steps"]:  # bash -e ignores a failure in the middle of an && chain: never one in the gate
        assert "&&" not in str(step.get("run", "")), step.get("name")
    runs = "\n".join(str(s.get("run", "")) for s in gate["steps"])
    assert "tools/ci/tier.py" in runs and 'test "$tier" = "$RAN"' in runs
    assert '--tier "$TIER" --event "$EVENT"' in runs
    coverage = next(s for s in gate["steps"] if "coverage_gate.py" in str(s.get("run", "")))
    assert coverage["if"] == "steps.tier.outputs.tier == 'full'"
    assert '--base-ref "$BASE_REF"' in runs and '--base-ref "$BASE_REF"' in jobs["changes"]["steps"][-1]["run"]


def test_the_nightly_report_fires_on_a_timeout_as_well_as_a_failure():
    """A scheduled job that hits its timeout ends `cancelled`; the report must open the issue for it too (CI posture
    review 2026-10-05, finding 1: six of eight nightlies timed out silently)."""
    nightly = yaml.safe_load((ROOT / ".github/workflows/nightly.yml").read_text(encoding="utf-8"))
    report = nightly["jobs"]["report"]
    condition = " ".join(str(report["if"]).split())
    assert set(report["needs"]) == set(nightly["jobs"]) - {"report"}  # every nightly job is reported on

    # Evaluate the expression itself over every event and job outcome, so its grouping is pinned, not just its parts
    # (PR #92 review: without the parentheses a failed manual run would open the issue). The translation covers
    # exactly the constructs this condition uses; anything else fails the test.
    import re

    # The job must run after a failed or cancelled job at all, so the condition must start from always() (re-review).
    assert condition.startswith("always() && "), condition
    py = condition.replace("always()", "True").replace("&&", " and ").replace("||", " or ")
    py = py.replace("github.event_name", "event")
    py = re.sub(r"contains\(needs\.\*\.result, '(\w+)'\)", r"('\1' in results)", py)
    assert re.fullmatch(r"[\w\s()'=.]+", py) and "needs" not in py and "github" not in py, py
    outcomes = ("success", "failure", "cancelled", "skipped")
    for event in ("schedule", "workflow_dispatch", "push"):
        for results in [(o,) for o in outcomes] + [("success", "cancelled"), ("skipped", "failure")]:
            fires = eval(py, {"__builtins__": {}}, {"event": event, "results": results})  # noqa: S307
            expected = event == "schedule" and bool({"failure", "cancelled"} & set(results))
            assert fires == expected, (event, results, condition)



# ---------------------------------------------------------------------------------------- the cost record (E43, E45)

def timed(platform: str, lane: str, seconds: dict[str, float], shard: str | None = None, **kw) -> dict:
    r = report(platform, lane, {n: "passed" for n in seconds}, shard=shard, **kw)
    for nid, d in seconds.items():
        r["results"][nid]["duration"] = d
    return r


def job(name: str, created: str, started: str, completed: str | None, os_label: str = "ubuntu-latest") -> dict:
    return {"name": name, "created_at": created, "started_at": started, "completed_at": completed,
            "conclusion": "success" if completed else None, "labels": [os_label]}


def test_the_cost_record_reports_each_tests_time_share_and_cli_calls():
    reports = [timed("linux", "regression", {ALL[2]: 90.0}, shard="1/2", cli_calls={ALL[2]: 12}),
               timed("linux", "regression", {"tests/regression/test_b.py::t4": 30.0}, shard="2/2"),
               timed("linux", "fast", {ALL[0]: 1.0, ALL[1]: 2.0})]
    durations = {"platforms": {"linux": {ALL[0]: 1.0, ALL[2]: 80.0}}}
    rec = cost_record.build(reports, None, durations, changed={"tests/unit/test_a.py"})
    f = rec["platforms"]["linux"]
    assert f["pytest_s"] == 123.0 and f["lanes"] == {"fast": 3.0, "regression": 120.0}
    assert f["slowest"][0]["id"] == ALL[2] and f["slowest"][0]["share_of_lane"] == 0.75
    assert f["slowest"][0]["cli_calls"] == 12 and f["cli_calls"]["total"] == 12
    assert f["durations_coverage"] == 0.5  # two of the four collected tests are in the durations file
    assert f["changed_tests"]["count"] == 2 and f["changed_tests"]["seconds"] == 3.0
    # of the two tests in the touched file, only the one the durations file has never seen is new
    assert f["changed_tests"]["new"]["count"] == 1 and f["changed_tests"]["new"]["slowest"][0]["id"] == ALL[1]
    text = cost_record.summary(rec)
    assert "New tests (in the files this change touches" in text and "All tests in the test files" in text
    assert "through the test helper" in text  # the CLI-call count says what it counts


def test_a_test_over_a_quarter_of_its_lane_or_a_slow_fast_lane_test_is_a_health_violation():
    reports = [timed("linux", "regression", {ALL[2]: 90.0, "tests/regression/test_b.py::t4": 30.0}),
               timed("linux", "fast", {ALL[0]: 31.0, ALL[1]: 29.0})]
    health = cost_record.build(reports, None, None)["platforms"]["linux"]["health"]
    assert {(h["kind"], h["test"]) for h in health} == {("test_share", ALL[2]), ("fast_test_time", ALL[0]),
                                                         ("test_share", ALL[0]), ("test_share", ALL[1])}
    assert all(h["level"] == "violation" for h in health)


def test_a_share_of_a_lane_too_small_to_matter_is_not_a_violation():
    reports = [timed("linux", "integration", {ALL[3]: 5.0, ALL[2]: 1.0})]
    assert cost_record.build(reports, None, None)["platforms"]["linux"]["health"] == []


@pytest.mark.parametrize("minutes, level", [(19, None), (21, "warning"), (26, "violation")])
def test_a_lane_job_over_20_minutes_warns_and_over_25_is_a_violation(minutes, level):
    jobs = [job("integration 1/5 (ubuntu-latest)", "2026-10-07T00:00:00Z", "2026-10-07T00:02:00Z",
                f"2026-10-07T00:{2 + minutes:02d}:00Z"),
            job("static", "2026-10-07T00:00:00Z", "2026-10-07T00:00:10Z", "2026-10-07T00:40:00Z"),
            job("assurance", "2026-10-07T00:30:00Z", "2026-10-07T00:30:05Z", None)]
    rec = cost_record.build([], jobs, None)
    # only test jobs are judged by the shard rule (static's 40 minutes is not a shard)
    assert [h["level"] for h in rec["health"] if h["kind"] == "job_time"] == ([level] if level else [])
    assert rec["run"]["still_running"] == ["assurance"]
    assert rec["run"]["queue_s"]["max"] == 120.0
    assert rec["run"]["runner_minutes"] == {"ubuntu-latest": round(minutes + 39 + 50 / 60, 1)}
    assert rec["run"]["wall_clock_s"] == max(40, 2 + minutes) * 60


def test_the_cost_record_never_fails_the_job_whatever_it_finds(tmp_path):
    (tmp_path / "r").mkdir()
    (tmp_path / "r" / "fast.json").write_text(json.dumps(timed("linux", "fast", {ALL[0]: 600.0})), encoding="utf-8")
    jobs = tmp_path / "jobs.json"
    jobs.write_text(json.dumps({"jobs": [job("core (ubuntu-latest)", "2026-10-07T00:00:00Z",
                                             "2026-10-07T00:00:00Z", "2026-10-07T00:29:00Z")]}), encoding="utf-8")
    out, summary_md = tmp_path / "cost.json", tmp_path / "summary.md"
    assert cost_record.main([str(tmp_path / "r"), "--jobs", str(jobs), "--out", str(out),
                             "--summary", str(summary_md)]) == 0
    rec = json.loads(out.read_text(encoding="utf-8"))
    assert rec["schema"] == cost_record.SCHEMA and any(h["level"] == "violation" for h in rec["health"])
    assert "CI health: 3 violation(s)" in summary_md.read_text(encoding="utf-8")


def test_ci_writes_the_cost_record_after_assurance_and_lanes_print_their_slowest_20():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert ci.count("--durations=20") == 3  # the fast and serial steps of core, and every lane shard
    assert '--run "$RUNNER_TEMP/run.json"' in ci
    workflow = yaml.safe_load(ci)
    steps = workflow["jobs"]["assurance"]["steps"]
    cost = next(s for s in steps if "cost_record.py" in s.get("run", ""))
    assert cost.get("continue-on-error") is True and cost.get("if") == "always()"
    # continue-on-error does not cover the job timeout: the step's own timeout keeps a hang from cancelling the gate
    assert cost.get("timeout-minutes") and cost["timeout-minutes"] < workflow["jobs"]["assurance"]["timeout-minutes"]
    assert workflow["jobs"]["assurance"]["permissions"] == {"contents": "read", "actions": "read"}
    assert any(s.get("with", {}).get("name") == "cost-record" for s in steps)


def test_the_run_counts_its_pending_time_and_skipped_jobs_count_for_nothing():
    jobs = [job("core (ubuntu-latest)", "2026-10-07T00:10:00Z", "2026-10-07T00:11:00Z", "2026-10-07T00:13:00Z"),
            {**job("web / web checks", "2026-10-07T00:10:00Z", "2026-10-07T00:10:05Z", "2026-10-07T00:10:04Z"),
             "conclusion": "skipped"}]
    rec = cost_record.build([], jobs, None, run={"created_at": "2026-10-07T00:00:00Z"})
    assert rec["run"]["run_pending_s"] == 11 * 60  # created, then pending, then the first job started
    assert rec["run"]["wall_clock_s"] == 13 * 60  # from the run's creation, a fact...
    assert rec["run"]["assurance_s"] == 3 * 60  # ...while §8's measure starts at the first job's creation
    assert [j["name"] for j in rec["run"]["jobs"]] == ["core (ubuntu-latest)"]
    assert rec["run"]["runner_minutes"] == {"ubuntu-latest": 2.0}


def test_the_strategy_budgets_are_reported_as_warnings():
    jobs = [job("core (ubuntu-latest)", "2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "2026-10-07T00:04:00Z"),
            job("core (windows-latest)", "2026-10-07T00:00:00Z", "2026-10-07T00:00:00Z", "2026-10-07T00:07:00Z",
                "windows-latest")]
    jobs.append(job("integration 1/5 (ubuntu-latest)", "2026-10-07T00:00:00Z", "2026-10-07T00:01:00Z",
                    "2026-10-07T00:16:00Z"))
    slow_fast = {ALL[0]: 20.0, ALL[1]: 20.0} | {f"x{i}": 20.0 for i in range(8)}
    rec = cost_record.build([timed("linux", "fast", slow_fast), timed("win32", "fast", slow_fast)],
                            jobs, None, run={"created_at": "2026-10-06T23:00:00Z"})
    budgets = [h for h in rec["health"] + rec["platforms"]["linux"]["health"] if h["kind"] == "budget"]
    # the run took 16 minutes from its first job (over 15), however long it waited before that
    assert {(h.get("job") or h.get("test")) for h in budgets} == {"core (ubuntu-latest)", "the run", "fast lane"}
    assert rec["platforms"]["win32"]["health"] == []  # §8's fast-lane budget is the Linux lane's
    assert all(h["level"] == "warning" for h in budgets)  # §8 budgets are reported, never violations


def test_a_rerun_attempt_counts_only_its_own_jobs():
    """PR #125 review B: jobs carried over from an earlier attempt keep their old times; they count for nothing."""
    jobs = [job("integration 1/5 (ubuntu-latest)", "2026-10-07T02:00:00Z", "2026-10-07T00:01:00Z",
                "2026-10-07T00:20:00Z"),  # carried over: created_at rewritten, started before the attempt
            job("assurance", "2026-10-07T02:00:00Z", "2026-10-07T02:00:30Z", "2026-10-07T02:01:30Z")]
    rec = cost_record.build([], jobs, None, run={"created_at": "2026-10-07T00:00:00Z",
                                                 "run_started_at": "2026-10-07T02:00:00Z"})
    run = rec["run"]
    assert run["carried_over"] == ["integration 1/5 (ubuntu-latest)"]
    assert [j["name"] for j in run["jobs"]] == ["assurance"]
    assert run["runner_minutes"] == {"ubuntu-latest": 1.0} and run["queue_s"]["total"] == 30.0
    assert run["assurance_s"] == 90.0 and run["wall_clock_s"] == 90.0 and rec["health"] == []
    assert "Carried over from an earlier attempt, not counted: integration 1/5" in cost_record.summary(rec)
