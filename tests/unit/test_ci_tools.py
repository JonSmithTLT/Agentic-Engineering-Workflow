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
    # (fast lane); eval/reviews holds archived review probes kept as they ran, which nothing executes.
    core_only = {ROOT / "tools" / "register.py", ROOT / "tools" / "ci" / "tier.py"}
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
