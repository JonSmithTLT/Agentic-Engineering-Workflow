"""The CI assurance check and the durations refresher (tools/ci): the merge gate must catch every way a
sharded run can lose, duplicate, skip or fail a test."""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
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
coverage_gate = _load("coverage_gate")
coverage_premise = _load("coverage_premise")
unit_isolation_audit = _load("unit_isolation_audit")

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
    (["AGENTS.md", "CLAUDE.md", "README.md", "web/docs/notes.md"], "docs"),
    # Plan v7 §3.3 (V4-3), an intended narrowing of the docs tier: eval/ is a code root, so its Markdown is full.
    (["eval/m3/README.md"], "full"),
    (["web/src/App.tsx", "docs/README.md"], "web"),
    (["web/package-lock.json"], "web"),
    (["docs/design/dashboard-api-v1-provisional.yaml"], "full"),  # the contract code reads
    (["web/docs/c0-approval.json"], "full"),  # its approval, read by the dashboard server
    (["docs/design/proposals/dashboard-maps-and-history-search-v0.1.md"], "full"),  # its change note (F20.8)
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
        argv = ["--event", "pull_request", "--paths-file", str(changed), "--labels", "", "--github-output", str(out)]
        assert tier.main(argv + (["--base-ref", base] if base else [])) == 0
        assert f"tier={expected}\n" in out.read_text(encoding="utf-8"), base


def test_a_pull_request_into_another_branch_is_full():
    """It can be retargeted to main without a new run, so its run must already be full (review of PR #99, 6)."""
    assert tier.decide("pull_request", ["docs/README.md"], "main") == "docs"
    for base in ("impl/f15-1-broker-cli", "", "Main"):
        assert tier.decide("pull_request", ["docs/README.md"], base) == "full", base


def _git(repo: Path):
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main",
                               *args], cwd=repo, check=True, capture_output=True, text=True,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    return git


def _merge(git, branch: str) -> str:
    """GitHub's test merge: main as the first parent, the pull request's head as the second."""
    git("checkout", "-q", "main")
    git("merge", "-q", "--no-ff", "-m", "merge", branch)
    return git("rev-parse", "HEAD")


def test_a_rename_out_of_the_code_is_full_tier(tmp_path, monkeypatch):
    """With git's default rename detection, moving src/aew/m.py to docs/m.md lists only docs/m.md: the diff must
    name both sides (review of PR #99, finding 2). Real git, real commits, a real merge commit."""
    git = _git(tmp_path)
    git("init", "-q")
    (tmp_path / "src" / "aew").mkdir(parents=True)
    (tmp_path / "src" / "aew" / "m.py").write_text("x = 1\n" * 20, encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "pr")
    (tmp_path / "docs").mkdir()
    git("mv", "src/aew/m.py", "docs/m.md")
    git("commit", "-q", "-m", "move")
    merge = _merge(git, "pr")
    monkeypatch.chdir(tmp_path)
    paths = tier.merge_paths(merge)
    assert paths is not None and "src/aew/m.py" in paths, paths
    assert tier.decide("pull_request", paths, "main") == "full"


GREEN = {"changes": "success", "core": "success", "lanes": "success", "web": "success", "static": "success",
         "fastbase": "skipped"}
REDUCED = {**GREEN, "lanes": "skipped"}
FAST = {**REDUCED, "fastbase": "success"}


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
    ("fast", FAST, True),
    ("fast", {**FAST, "fastbase": "failure"}, False),  # the base footprint is unknown
    ("fast", {**FAST, "fastbase": "skipped"}, False),  # (a module changed: --jobs-for's default)
    ("fast", {**FAST, "lanes": "success"}, False),
    ("fast", {**FAST, "web": "failure"}, False),
    ("full", {**GREEN, "fastbase": "failure"}, True),  # a shadow run: fastbase ran on the decision, the run is full
    ("full", {**GREEN, "fastbase": "cancelled"}, True),
    ("docs", {**REDUCED, "fastbase": "success"}, True),
])
def test_the_gate_requires_every_needed_job_in_every_tier(tier_name, results, ok):
    """Every needed job, any of which failing fails the gate (review of PR #99, finding 1: a shell && chain followed
    by another line let a failing web, core or changes job pass)."""
    assert (tier.job_problems(tier_name, results) == []) is ok
    jobs = ",".join(f"{k}={v}" for k, v in results.items())
    assert (tier.main(["--jobs-for", tier_name, "--jobs", jobs]) == 0) is ok


def test_a_diff_that_cannot_be_computed_is_full(tmp_path, monkeypatch):
    assert tier.decide("pull_request", None, "main") == "full"
    assert tier.merge_paths("") is None
    monkeypatch.chdir(tmp_path)  # not a repository: git fails
    assert tier.merge_paths("abc") is None


PATH_CALLS = ("Path", "PurePath", "PurePosixPath", "PureWindowsPath")
ROOT_HEAD = re.compile(r"__file__|parents\[|\b[A-Z_]*ROOT[A-Z_]*\b")


def _is_str(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _docstrings(tree: ast.AST) -> set[int]:
    """The docstring constants of a module (by id): prose, not references (comments are not in the AST)."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and _is_str(first.value):
                found.add(id(first.value))
    return found


def _path_parts(node: ast.AST) -> list[ast.expr] | None:
    """The parts of a path expression, left to right: a ``/`` chain, ``.joinpath(...)``, ``os.path.join(...)`` or
    ``Path(...)``; ``None`` for anything else."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (_path_parts(node.left) or [node.left]) + [node.right]
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            return (_path_parts(node.func.value) or [node.func.value]) + list(node.args)
        name = ast.unparse(node.func)
        if name == "os.path.join":
            return list(node.args)
        if name.rsplit(".", 1)[-1] in PATH_CALLS and node.args:
            return list(node.args)
    return None


def _inner_paths(tree: ast.AST) -> set[int]:
    """Path expressions that are the left part of a longer one: only the whole chain is a reference."""
    inner = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            inner.add(id(node.left))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
            inner.add(id(node.func.value))
    return inner


FILE_HEAD = re.compile(r"^(?:Path|pathlib\.Path)\(__file__\)(?:\.resolve\(\)|\.absolute\(\))?"
                       r"(?P<up>(?:\.parent)*)(?:\.parents\[(?P<n>\d+)\])?$")


def _anchor(head: ast.AST | None) -> str:
    """Where a path expression's literal parts resolve: ``root`` (the repository, also for ``ROOT``-like names and
    plain literals), ``file:N`` (N directories up from the file: ``Path(__file__).parent`` is 1, ``.parents[1]`` 2),
    or ``file`` (relative to the file in a way not computed here: every directory from the file's up to the root)."""
    if head is None:
        return "root"
    text = ast.unparse(head)
    if "__file__" not in text:
        return "root"
    m = FILE_HEAD.match(text)
    if not m:
        return "file"
    return f"file:{m.group('up').count('.parent') + (int(m.group('n')) + 1 if m.group('n') else 0)}"


def path_references(source: str, allowed: frozenset[str] = frozenset()) -> list[tuple[str, str, str]]:
    """The repository references a module makes (plan v7 §3.3), as (text, kind, anchor):

    - a string constant with at least one ``/`` (``"eval/m3/dogfood"``; docstrings excluded);
    - a path expression of two or more literal parts, or rooted at a repository-root expression (``ROOT``,
      ``parents[n]``, ``Path(__file__)...``), its first part literal or not;
    - a glob: ``.glob``/``.rglob`` on such an expression or on a repository root, and ``glob.glob``/``glob.iglob``,
      the pattern literal or not.

    ``exact`` names a file or a directory and covers everything below it; ``prefix`` (a non-literal tail, a
    non-literal glob pattern) covers everything below its literal base; a literal glob covers what its pattern
    matches (``**`` or ``rglob``: everything below its literal prefix). A bare one-word string (``"docs"``) is not a
    reference, and neither is a wildcard string that no glob reads: ``"docs/**"`` passed as a fixture project's
    scope, ``"**/"`` in a glob translator. The anchor is where the reference resolves (``_anchor``). A rooted
    expression with no literal base that is known not to read the repository widely is listed in ``allowed``
    (``NONLITERAL_ALLOWED``), by its source text."""
    tree = ast.parse(source)
    docs, inner = _docstrings(tree), _inner_paths(tree)
    refs: list[tuple[str, str, str]] = []

    def glob(base: str, pattern: str, recursive: bool, anchor: str) -> None:
        pattern = pattern.replace("\\", "/").removeprefix("./")
        full = f"{base}/{pattern}" if base else pattern
        if recursive or "**" in full:
            head = full.split("**", 1)[0]
            name = full.rsplit("/", 1)[-1]  # any depth below the literal prefix, by the pattern's last part
            refs.append((f"{head.rstrip('/')}/**/{name}" if head.rstrip("/") else f"**/{name}", "rglob", anchor))
        else:
            refs.append((full, "glob", anchor))

    def chain(node: ast.AST) -> tuple[list[str], bool, str, bool] | None:
        """(literal parts, rooted, anchor, open tail) of a path expression, or of a bare repository root."""
        parts = _path_parts(node)
        if parts is None:
            if ROOT_HEAD.search(ast.unparse(node)):
                return [], True, _anchor(node), False
            return None
        head = None if _is_str(parts[0]) else parts.pop(0)
        lits: list[str] = []
        open_tail = False
        for part in parts:
            if not _is_str(part):
                open_tail = True
                break
            lits.append(part.value)  # type: ignore[attr-defined]
        rooted = head is not None and bool(ROOT_HEAD.search(ast.unparse(head)))
        return lits, rooted, _anchor(head), open_tail

    def joined(lits: list[str]) -> str:
        return "/".join(p.strip("/") for p in lits).replace("\\", "/").removeprefix("./")

    for node in ast.walk(tree):
        if _is_str(node) and id(node) not in docs:
            text = node.value.strip()  # type: ignore[attr-defined]
            if ("/" in text and not any(c.isspace() for c in text) and "://" not in text and not text.startswith("/")
                    and not any(c in text for c in "*?[")):
                refs.append((text.replace("\\", "/").removeprefix("./").rstrip("/"), "exact", "root"))
        if id(node) not in inner and _path_parts(node) is not None:
            found = chain(node)
            if found:
                lits, rooted, anchor, open_tail = found
                base = joined(lits)
                if lits and (len(lits) >= 2 or "/" in base or rooted):
                    refs.append((base, "prefix" if open_tail else "exact", anchor))
                elif rooted and open_tail and ast.unparse(node) not in allowed:
                    refs.append(("", "prefix", anchor))  # ROOT / name: everything below the root (PR #163, V7-3)
        if not isinstance(node, ast.Call):
            continue
        literal_pattern = bool(node.args) and _is_str(node.args[0])
        pattern = node.args[0].value if literal_pattern else None  # type: ignore[attr-defined]
        if ast.unparse(node.func) in ("glob.glob", "glob.iglob") and node.args:
            if pattern is not None:
                glob("", pattern, any(k.arg == "recursive" for k in node.keywords), "root")
            elif ast.unparse(node) not in allowed:  # an unknown pattern may name anything below the root
                refs.append(("", "prefix", "root"))
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ("glob", "rglob") and node.args:
            found = chain(node.func.value)
            if found and (found[1] or len(found[0]) >= 2):
                lits, _, anchor, open_tail = found
                base = joined(lits)
                if open_tail or pattern is None:  # everything below the receiver's literal base (V7-3)
                    if base or ast.unparse(node) not in allowed:
                        refs.append((base, "prefix" if not base else "exact", anchor))
                else:
                    glob(base, pattern, node.func.attr == "rglob", anchor)
    return refs


def _tracked() -> list[str]:
    import subprocess

    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return [p for p in out.split("\0") if p]


def covered(refs: list[tuple[str, str, str]], source: Path, tracked: list[str]) -> set[str]:
    """The tracked files the references cover. ``root`` resolves against the repository root, ``file:N`` against
    the directory N levels above the file, ``file`` against every directory from the file's up to the root."""
    import fnmatch
    import posixpath

    rel = source.resolve().relative_to(ROOT).as_posix()
    ancestors = [posixpath.dirname(rel)]
    while ancestors[-1]:
        ancestors.append(posixpath.dirname(ancestors[-1]))
    out: set[str] = set()
    for text, kind, anchor in refs:
        if anchor == "root":
            bases = [""]
        elif anchor == "file":
            bases = ancestors
        else:
            up = int(anchor.split(":")[1])
            base = rel
            for _ in range(up):
                base = posixpath.dirname(base) if base else ".."
            bases = [base]
        for base in bases:
            full = posixpath.normpath(posixpath.join(base, text)) if text or base else ""
            full = "" if full == "." else full + ("/" if text.endswith("/") else "")
            if full.startswith(".."):
                continue
            if kind == "exact":
                out |= {f for f in tracked if f == full or f.startswith(full + "/")}
            elif kind == "prefix":
                out |= {f for f in tracked if f.startswith(full)}
            elif kind == "glob":  # the pattern's own depth
                out |= {f for f in tracked if f.count("/") == full.count("/") and fnmatch.fnmatchcase(f, full)}
            else:  # rglob: any depth below the base
                below, name = (full.split("**/", 1) + [""])[:2] if "**/" in full else ("", full)
                out |= {f for f in tracked if f.startswith(below) and fnmatch.fnmatchcase(f.rsplit("/", 1)[-1], name)}
    return out


# Readers that run only in the core lanes, or never: the register tool is exercised by tests/unit/test_register.py
# and the frontend importer by tests/unit/test_dashboard_static.py (both fast lane); eval/reviews holds archived
# review probes kept as they ran, which nothing executes.
CORE_ONLY_READERS = ("tools/register.py", "tools/ci/tier.py", "tools/dashboard/import_build.py")
# Rooted expressions without a literal base that do not read the repository widely (PR #163 review, V7-3), by file
# and source text. Each needs its reason; anything new of this shape fails the guard until it is listed or rewritten.
_CONTRACT = "ROOT / CT.CONTRACT_REL"  # the dashboard contract: its literal path is in src/aew/dashboard/contract.py,
# which the guard reads (it is `full` through tier.SHARED)
NONLITERAL_ALLOWED: dict[str, frozenset[str]] = {
    **{f"tests/integration/test_dashboard_{name}.py": frozenset({_CONTRACT})
       for name in ("acceptance", "api", "conditional", "maps", "security", "session")},
    # DEBRIEF_ROOT is a directory under the system temp directory, not the repository
    "eval/m3/dogfood/dogfood.py": frozenset({"DEBRIEF_ROOT / name / 'lead-1'"}),
}


def non_core_sources() -> list[Path]:
    sources = [*(ROOT / "src").rglob("*.py"), *(ROOT / "tools").rglob("*.py"), *(ROOT / "eval").rglob("*.py"),
               ROOT / "tests" / "conftest.py", *(ROOT / "tests" / "helpers").rglob("*.py"),
               *(ROOT / "tests" / "integration").rglob("*.py"), *(ROOT / "tests" / "regression").rglob("*.py"),
               *(ROOT / "tests" / "acceptance").rglob("*.py")]
    archived = ROOT / "eval" / "reviews"
    return [f for f in sources if f.relative_to(ROOT).as_posix() not in CORE_ONLY_READERS
            and archived not in f.parents and "__pycache__" not in f.parts]


def reduced_readers(sources: list[Path]) -> tuple[set[str], list[str]]:
    """Every tracked file the sources reference, and the ones a reduced tier may change without running them."""
    tracked = _tracked()
    named: set[str] = set()
    problems = []
    for f in sources:
        try:
            label = f.relative_to(ROOT).as_posix()
            refs = path_references(f.read_text(encoding="utf-8"), NONLITERAL_ALLOWED.get(label, frozenset()))
        except SyntaxError as exc:
            problems.append(f"{f.relative_to(ROOT).as_posix()}: cannot be parsed ({exc})")
            continue
        for path in covered(refs, f, tracked):
            named.add(path)
            if tier.classify_path(path) != "full":
                problems.append(f"{label} reads {path}, which the {tier.classify_path(path)} tier may change")
    return named, problems


def test_every_repository_file_read_outside_the_core_lanes_is_full_tier():
    """A repository file that code, a non-core test, a helper, a CI tool or an eval driver names by its path is an
    input to more than the core lanes, whatever it looks like: changing it must run the full gate (review of PR #99,
    finding 4). Hardened in plan v7 §3.3 (V3-4): a literal with a ``/``, a path expression of two or more parts or
    rooted at the repository, and a glob name a file or a whole directory and cover everything below it, root-level
    Markdown included. Paths that do not exist here (discovery's conventions for other projects, fixture projects) are
    not ours. The fast lane's own readers (tests/unit, the spec pin) run in every tier and are left out; what reaches
    into the fast lane's test modules is the other guard's (test_nothing_outside_the_unit_lane_reaches_a_unit_module),
    and tests/durations.json, a fast-tier input, is read only by the shard partitioner, which decides balance, never
    outcomes."""
    named, problems = reduced_readers(non_core_sources())
    assert "docs/design/dashboard-api-v1-provisional.yaml" in named
    assert problems == []


def test_the_hardened_docs_guard_names_the_two_cases_that_tripped_its_first_wording():
    """Plan v7 §3.3: the dogfood regression names eval/m3/dogfood, under which four Markdown files were `docs`; they
    are `full` now that eval/ is a code root. Discovery's bare "docs" (a convention for target projects) is not a
    directory reference."""
    dogfood = ROOT / "tests" / "regression" / "test_m3_dogfood_findings.py"
    reads = covered(path_references(dogfood.read_text(encoding="utf-8")), dogfood, _tracked())
    markdown = {"eval/m3/dogfood/README.md", "eval/m3/dogfood/rubric.md", "eval/m3/dogfood/fixture/base/README.md",
                "eval/m3/dogfood/fixture/reference/T2/README.md"}
    assert markdown <= reads
    assert {tier.classify_path(p) for p in markdown} == {"full"}
    discovery = ROOT / "src" / "aew" / "knowledge" / "discovery.py"
    refs = path_references(discovery.read_text(encoding="utf-8"))
    assert "docs" not in {text for text, _, _ in refs}
    assert not any(p.startswith("docs/") for p in covered(refs, discovery, _tracked()))


@pytest.mark.parametrize(("source", "reads"), [
    ('P = "docs/README.md"\n', "docs/README.md"),
    ('P = ROOT / "docs" / "README.md"\n', "docs/README.md"),
    ('P = ROOT / "docs"\n', "docs/README.md"),  # rooted: one part names a directory
    ('P = ROOT / "README.md"\n', "README.md"),  # root-level Markdown
    ('P = Path(__file__).resolve().parents[2] / "docs"\n', "docs/README.md"),  # tests/integration -> the root
    ('P = ROOT.joinpath("docs", "README.md")\n', "docs/README.md"),
    ('P = ROOT / "docs" / name\n', "docs/README.md"),  # a non-literal tail covers everything below
    ('P = glob.glob("docs/*.md")\n', "docs/README.md"),
    ('P = glob.glob("docs/**/*.md", recursive=True)\n', "docs/README.md"),
    ('P = ROOT.glob("*.md")\n', "README.md"),
    ('P = (ROOT / "docs").rglob("*.md")\n', "docs/README.md"),
    ('P = tmp / "docs" / "README.md"\n', "docs/README.md"),  # two literal parts: resolved against the root
    # PR #163 review, V7-3: what is read is not known here, so everything below the literal base is
    ('PATTERN = "docs/**/*.md"\nP = sorted(ROOT.glob(PATTERN))\n', "docs/README.md"),
    ('P = (ROOT / "docs").rglob(pattern)\n', "docs/README.md"),
    ('P = glob.glob(pattern)\n', "docs/README.md"),
    ('P = ROOT / name\n', "README.md"),
    ('P = Path(__file__).resolve().parents[2] / name\n', "docs/README.md"),  # tests/integration -> the root
])
def test_the_hardened_docs_guard_sees_every_spelling_of_a_reference(source, reads):
    here = ROOT / "tests" / "integration" / "test_sample.py"
    assert reads in covered(path_references(source), here, _tracked())


def test_a_listed_rooted_expression_is_exempt_and_nothing_else_is():
    here = ROOT / "tests" / "integration" / "test_sample.py"
    source = "P = ROOT / CT.CONTRACT_REL\nQ = ROOT / other\n"
    allowed = path_references(source, frozenset({"ROOT / CT.CONTRACT_REL"}))
    assert len(allowed) == 1 and "README.md" in covered(allowed, here, _tracked())  # Q is still seen
    assert len(path_references(source)) == 2
    assert path_references("P = Path(__file__).parent / name\n") == [("", "prefix", "file:1")]
    assert "tests/integration/test_sample.py" not in covered(  # the file's own directory, not the root
        [("", "prefix", "file:1")], ROOT / "tests" / "regression" / "test_x.py", ["tests/integration/test_sample.py"])


@pytest.mark.parametrize("source", ['P = "docs"\n', 'P = tmp / "README.md"\n', 'def f():\n    """docs/README.md"""\n',
                                    'P = "see docs/README.md for details"\n', 'P = "https://x/docs/README.md"\n',
                                    'SCOPE = "docs/**"\n', 'GLOBSTAR = "**/"\n'])
def test_a_bare_word_a_tmp_file_a_docstring_or_prose_is_not_a_reference(source):
    here = ROOT / "tests" / "integration" / "test_sample.py"
    assert not any(p.startswith(("docs/", "README")) for p in covered(path_references(source), here, _tracked()))


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
    changes_run = next(s["run"] for s in jobs["changes"]["steps"] if "tools/ci/tier.py" in str(s.get("run", "")))
    assert jobs["lanes"]["needs"] == "changes" and jobs["lanes"]["if"] == "needs.changes.outputs.tier == 'full'"
    assert "needs" not in jobs["core"] and "needs" not in jobs["static"]  # core and static run in every tier
    gate = jobs["assurance"]
    assert set(gate["needs"]) == {"changes", "core", "lanes", "web", "static", "fastbase"}
    assert gate["if"] == "always()"
    reports = next(s for s in gate["steps"] if "check_assurance.py" in str(s.get("run", "")))
    assert "if" not in reports  # the lane-report check always runs (review of PR #99, finding 1)
    final = gate["steps"][-1]
    assert final["if"] == "always()" and "tools/ci/tier.py --jobs-for" in final["run"]
    for step in gate["steps"]:  # bash -e ignores a failure in the middle of an && chain: never one in the gate
        assert "&&" not in str(step.get("run", "")), step.get("name")
    runs = "\n".join(str(s.get("run", "")) for s in gate["steps"])
    assert "tools/ci/tier.py" in runs and '--ran "$RAN"' in runs  # the recompute is not narrower (plan v7 §4)
    assert '--tier "$TIER" --event "$EVENT"' in runs
    coverage = next(s for s in gate["steps"] if "coverage_gate.py" in str(s.get("run", "")))
    assert coverage["if"] == "steps.tier.outputs.tier == 'full'"
    assert '--base-ref "$BASE_REF"' in runs and '--base-ref "$BASE_REF"' in changes_run
    # Both compute from the merge commit under test, the label read live (plan v7 §1.1, §4)
    assert '--merge-ref "$GITHUB_SHA"' in runs and '--merge-ref "$GITHUB_SHA"' in changes_run
    assert '--repo "$REPO" --pr "$PR"' in runs and '--repo "$REPO" --pr "$PR"' in changes_run
    assert jobs["changes"]["permissions"]["pull-requests"] == "read"


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
    assert workflow["jobs"]["assurance"]["permissions"] == {"contents": "read", "actions": "read",
                                                             "pull-requests": "read"}
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


# The names that denote this checkout in test code: ROOT and any *_ROOT constant, a ``root`` variable, and a path
# derived from the test file itself. Either quote style; git's ``-C`` and ``--git-dir``, a ``cwd=``, or a git wrapper
# called with the checkout first (review of PR #161, m2).
_CHECKOUT = (r"""(?:\b(?:[A-Z][A-Z0-9_]*_)?ROOT\b|\broot\b"""
             r"""|Path\(__file__\)(?:\.\w+\(\))*(?:\.parents\[\d+\]|\.parent\b))""")
_ARG = rf"""(?:str\(\s*)?{_CHECKOUT}"""
HISTORY_READ = re.compile(
    rf"""["']git["']\s*,\s*["'](?:-C|--git-dir)["']\s*,\s*{_ARG}"""  # ["git", "-C", str(ROOT), ...]
    rf"""|["']--git-dir=\{{?{_ARG}"""  # f"--git-dir={ROOT}/.git"
    rf"""|\bcwd\s*=\s*{_ARG}"""  # subprocess.run(["git", ...], cwd=ROOT)
    rf"""|\bgit\w*\(\s*{_ARG}\s*,""")  # git_in(ROOT, "show", ref)
# Matches that are not history reads, by file and exact source line, each with its reason.
HISTORY_READ_ALLOWED = {
    ("tests/helpers/lanes.py", 'status = subprocess.run(["git", "status", "--porcelain=v1", "-z", '
                               '"--untracked-files=all"], cwd=root,'):
        "the working tree's status, which a depth-1 checkout has: the guard that no test changes the checkout",
    **{("tests/helpers/invariants.py", line): "``root`` is the test's own temporary project repository, never this "
       "checkout: the integration invariants' ancestry checks on the commits the test itself made" for line in (
        'm == commit or _git("merge-base", "--is-ancestor", commit, m, cwd=root).returncode == 0',
        'if not commit or _git("merge-base", "--is-ancestor", commit, ref, cwd=root).returncode != 0:',
        'return bool(commit and base) and _git("merge-base", "--is-ancestor", commit, base, cwd=root).returncode == 0',
    )},
}


def history_reads(text: str) -> list[str]:
    """The source lines of ``text`` that point git at this checkout, stripped."""
    lines = text.splitlines()
    found = []
    for m in HISTORY_READ.finditer(text):
        line = text.count("\n", 0, m.start())
        found.append(lines[line].strip())
    return found


@pytest.mark.parametrize(("source", "fires"), [
    ('subprocess.run(["git", "-C", str(root), "show", f"{commit}:{rel}"])', True),  # the helper B1 removed
    ('subprocess.run(["git", "show", ref], cwd=root)', True),
    ('subprocess.run(["git", "show", ref], cwd=str(root))', True),
    ('subprocess.run(["git", "show", ref], cwd=ROOT)', True),
    ('["git", "-C", str(REPO_ROOT), "show", ref]', True),
    ('["git", "-C", str(Path(__file__).resolve().parents[2]), "show", ref]', True),
    ('["git", "-C", Path(__file__).parent, "log"]', True),
    ("['git', '-C', str(ROOT), 'show', ref]", True),
    ('["git", "--git-dir", str(ROOT / ".git"), "show", ref]', True),
    ('["git", f"--git-dir={ROOT}/.git", "show", ref]', True),
    ('git_in(ROOT, "show", ref)', True),
    ('git(root, "cat-file", "-e", ref)', True),
    ('subprocess.run(["git", *args], cwd=cwd, capture_output=True)', False),  # invariants.py: temporary repositories
    ('subprocess.run(["git", "init"], cwd=repo, check=True)', False),
    ('git("show", f"{head}:pyproject.toml", cwd=repo)', False),
    ('[sys.executable, "-m", "aew", "-C", str(root), "lead"]', False),  # aew's -C, not git's
    ('subprocess.run(["git", *args], cwd=self.root)', False),
    ('subprocess.run(["git", "worktree", "prune"], cwd=p.root)', False),
])
def test_the_history_guard_fires_on_every_spelling_of_this_checkout(source, fires):
    assert bool(history_reads(source)) is fires, source


def test_only_the_core_lanes_read_the_repositorys_git_history():
    """CI's ``lanes`` job checks out at depth 1; only ``core`` (the fast and serial lanes) has the full history. A
    test or helper outside them that reads a historical commit of this repository fails at collection in every
    integration shard (review of PR #161, B1). This is a lint for the usual spellings (``HISTORY_READ``, self-tested
    above): non-core test code may not point git at this checkout, by ``-C``, ``--git-dir``, ``cwd=`` or a git wrapper
    called with ``ROOT``, a ``*_ROOT`` constant, ``root`` or a path derived from ``__file__``, unless the line is in
    ``HISTORY_READ_ALLOWED`` with its reason. A fast-lane module that does so carries no marker moving it to a
    depth-1 lane. A spelling the lint misses is still caught, loudly, by the integration shards failing at collection.
    """
    import re

    non_core = [ROOT / "tests" / "conftest.py", *(ROOT / "tests" / "helpers").rglob("*.py"),
                *(ROOT / "tests" / "integration").rglob("*.py"), *(ROOT / "tests" / "regression").rglob("*.py"),
                *(ROOT / "tests" / "acceptance").rglob("*.py")]
    offenders = []
    used = set()
    for f in non_core:
        rel = f.relative_to(ROOT).as_posix()
        for line in history_reads(f.read_text(encoding="utf-8")):
            if (rel, line) in HISTORY_READ_ALLOWED:
                used.add((rel, line))
            else:
                offenders.append(f"{rel}: {line}")
    assert offenders == [], f"non-core test code points git at this checkout: {offenders}"
    assert used == set(HISTORY_READ_ALLOWED), f"stale allowlist entries: {set(HISTORY_READ_ALLOWED) - used}"
    moved = re.compile(r"pytest\.mark\.(acceptance|exploratory)\b")
    for f in (ROOT / "tests" / "unit").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        if history_reads(text) and f.name != Path(__file__).name:
            assert not moved.search(text), f"{f.name} reads git history but is marked into a depth-1 lane"


# -------------------------------------------------------------- nothing outside tests/unit reaches it (plan v7 §3.2)

# The classifiers that must name the directory: the lane rule (and its error message) and the tier.
UNIT_ALLOWED: dict[str, str | None] = {"tests/helpers/lanes.py": "lane_of", "tools/ci/tier.py": None}
REACH_CALLS = ("import_module", "__import__", "spec_from_file_location", "run_module", "run_path")
SYSPATH_CALLS = ("sys.path.insert", "sys.path.append", "syspath_prepend", "site.addsitedir")
UNIT_PATH = re.compile(r"(?:^|[^\w.])tests/unit(?:$|/|[^\w])|(?:^|[^\w.])tests/test_spec_pin\.py")
UNIT_SEGMENT = re.compile(r"^/?unit(?:/|$)")
IMPORT_TEXT = re.compile(r"\bimport\s+([\w.]+)|\bfrom\s+([\w.]+)\s+import\s+([\w., ]+)")


def unit_module_names() -> set[str]:
    return {p.stem for p in (ROOT / "tests" / "unit").rglob("*.py")} | {"test_spec_pin"}


def _names_unit_module(dotted: str, names: set[str]) -> bool:
    """A dotted module name resolving, by basename or by path, to a unit module (or the directory itself)."""
    parts = dotted.split(".")
    return parts[-1] in names or any(a == "tests" and b == "unit" for a, b in zip(parts, parts[1:], strict=False))


def unit_reach(label: str, source: str, names: set[str]) -> list[str]:
    """How a module outside tests/unit reaches into it (plan v7 §3.2): an import at any depth; a string naming an
    import of one; a string or path expression naming a file under tests/unit or the directory itself (docstrings
    excluded); a literal import_module, __import__, spec_from_file_location or runpy target; a sys.path, syspath_prepend
    or site.addsitedir argument naming it. The allowlisted classifiers are exempt (the lane rule only inside
    ``lane_of``)."""
    allowed = UNIT_ALLOWED.get(label, "")
    if allowed is None:
        return []
    tree = ast.parse(source)
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if allowed and isinstance(node, ast.FunctionDef) and node.name == allowed:
            exempt |= {id(n) for n in ast.walk(node)}
    docs = _docstrings(tree)
    found: set[str] = set()

    def hit(node: ast.AST, why: str) -> None:
        if id(node) not in exempt:
            found.add(f"{label}:{getattr(node, 'lineno', '?')}: {why}")

    def names_path(text: str) -> bool:
        return bool(UNIT_PATH.search(text.replace("\\", "/")))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if _names_unit_module(a.name, names):
                    hit(node, f"imports {a.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for a in node.names:
                if (mod and _names_unit_module(mod, names)) or _names_unit_module(f"{mod}.{a.name}".lstrip("."), names):
                    hit(node, f"imports {a.name} from {mod or '.'}")
        elif _is_str(node) and id(node) not in docs:
            text = node.value  # type: ignore[attr-defined]
            if names_path(text):
                hit(node, f"names {text!r}")
            for m in IMPORT_TEXT.finditer(text):
                mods = [m.group(1)] if m.group(1) else [m.group(2)] + [f"{m.group(2)}.{n.strip()}"
                                                                        for n in m.group(3).split(",") if n.strip()]
                if any(_names_unit_module(x, names) for x in mods):
                    hit(node, f"a generated import: {m.group(0)!r}")
        elif isinstance(node, ast.JoinedStr):
            for before, piece in zip(node.values, node.values[1:], strict=False):
                if (isinstance(before, ast.FormattedValue) and _is_str(piece)
                        and UNIT_SEGMENT.match(piece.value.replace("\\", "/"))):  # type: ignore[attr-defined]
                    hit(node, f"joins 'unit' to an expression: {ast.unparse(node)}")
        parts = _path_parts(node)
        if parts:
            for part in parts[1:]:
                if _is_str(part) and UNIT_SEGMENT.match(part.value.replace("\\", "/")):  # type: ignore[attr-defined]
                    hit(node, f"joins 'unit' to a path: {ast.unparse(node)}")
        if isinstance(node, ast.Call):
            fn = ast.unparse(node.func)
            args = [*node.args, *(k.value for k in node.keywords)]
            if fn.rsplit(".", 1)[-1] in REACH_CALLS:
                for arg in args:
                    if _is_str(arg) and (_names_unit_module(arg.value, names) or names_path(arg.value)):  # type: ignore[attr-defined]
                        hit(node, f"{fn}({arg.value!r})")  # type: ignore[attr-defined]
            if fn.endswith(SYSPATH_CALLS):
                for sub in (n for arg in args for n in ast.walk(arg)):
                    if _is_str(sub) and (names_path(sub.value) or UNIT_SEGMENT.match(sub.value.replace("\\", "/"))):  # type: ignore[attr-defined]
                        hit(node, f"{fn} names {sub.value!r}")  # type: ignore[attr-defined]
    return sorted(found)


def outside_unit_sources() -> list[Path]:
    """Every .py outside tests/unit: tests (conftest and helpers included), src, tools, eval (except the archived
    eval/reviews, which nothing executes), and the repository root."""
    unit, archived = ROOT / "tests" / "unit", ROOT / "eval" / "reviews"
    files = [p for r in ("tests", "src", "tools", "eval") for p in (ROOT / r).rglob("*.py")] + list(ROOT.glob("*.py"))
    return sorted(p for p in files if unit not in p.parents and archived not in p.parents
                  and "__pycache__" not in p.parts)


def test_nothing_outside_the_unit_lane_reaches_a_unit_module():
    """Plan v7 §3.2, the fast tier's safety: a heavy test runs the same code on the same inputs in the tested tree and
    its base only if no changed fast-lane test module can reach it. True today: the only module reference into
    tests/unit is test_map_slices -> test_context_budget, inside the unit lane, and the other mentions of tests/unit
    in src/ are comments and docstrings."""
    names = unit_module_names()
    found = []
    for f in outside_unit_sources():
        label = f.relative_to(ROOT).as_posix()
        try:
            found += unit_reach(label, f.read_text(encoding="utf-8"), names)
        except SyntaxError as exc:
            found.append(f"{label}: cannot be parsed, so cannot be checked ({exc})")
    assert found == []


@pytest.mark.parametrize("source", [
    "import test_context_budget\n",
    "def f():\n    import test_context_budget\n",  # at any depth
    "from test_context_budget import BUDGET\n",
    "from tests.unit import test_lanes\n",
    "import tests.unit.test_lanes\n",
    "from tests import unit\n",
    "from . import test_context_budget\n",
    "SCRIPT = 'import test_context_budget\\nprint(1)'\n",
    "SCRIPT = 'from test_context_budget import BUDGET'\n",
    "P = 'tests/unit/test_lanes.py'\n",
    "P = 'tests/unit'\n",
    "P = r'C:\\repo\\tests\\unit\\x.py'\n",
    "P = 'tests/test_spec_pin.py'\n",
    "P = ROOT / 'tests' / 'unit'\n",
    "P = ROOT / 'tests' / 'unit' / 'test_lanes.py'\n",
    "P = TESTS / 'unit'\n",
    "P = Path(__file__).parent.parent / 'unit'\n",
    "P = ROOT.joinpath('tests', 'unit')\n",
    "P = os.path.join(here, 'unit')\n",
    "P = f'{tests}/unit/x.py'\n",
    "importlib.import_module('test_lanes')\n",
    "__import__('tests.unit.test_lanes')\n",
    "importlib.util.spec_from_file_location('test_lanes', p)\n",
    "runpy.run_module('test_lanes')\n",
    "sys.path.insert(0, str(TESTS / 'unit'))\n",
    "monkeypatch.syspath_prepend(f'{root}/unit')\n",
    "site.addsitedir('tests/unit')\n",
], ids=lambda s: s.strip().replace("\n", " ")[:50])
def test_each_way_of_reaching_a_unit_module_is_a_violation(source):
    assert unit_reach("tests/integration/test_x.py", source, unit_module_names()) != []


@pytest.mark.parametrize("source", [
    'def f():\n    """Pinned by tests/unit/test_lanes.py."""\n',  # a docstring is prose
    "# tests/unit/test_lanes.py pins this\nx = 1\n",  # a comment is not in the AST
    "unit = dict(bundle['unit'])\n",  # 'unit' as a key, not a path
    "P = ROOT / 'tests' / 'integration'\n",
    "import lanes\nfrom conftest import IS_WINDOWS\n",
    "P = ROOT / 'units' / 'x'\n",
    "MSG = 'see tests/unittest_notes'\n",
])
def test_what_does_not_reach_a_unit_module_is_not_a_violation(source):
    assert unit_reach("tests/integration/test_x.py", source, unit_module_names()) == []


def test_only_the_classifiers_may_name_the_unit_directory():
    """The allowlist: tier.py in full, lanes.py only inside lane_of (the rule and its error message)."""
    source = "def lane_of(path):\n    return path.startswith('tests/unit/')\nOTHER = 'tests/unit'\n"
    assert unit_reach("tools/ci/tier.py", source, set()) == []
    found = unit_reach("tests/helpers/lanes.py", source, set())
    assert len(found) == 1 and ":3:" in found[0]
    assert len(unit_reach("tests/helpers/other.py", source, set())) == 2


# ------------------------------------------------------------------ the fast tier (CI plan v7, PR 1: shadow)

FAST_ONLY = {"fast"}


@pytest.mark.parametrize(("paths", "lanes", "expected"), [
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": {"fast"}}, "fast"),
    (["docs/README.md", "tests/unit/test_x.py"], {"tests/unit/test_x.py": {"fast"}}, "fast"),
    (["tests/unit/sub/test_y.py"], {"tests/unit/sub/test_y.py": {"fast"}}, "fast"),
    (["tests/test_spec_pin.py"], {"tests/test_spec_pin.py": {"fast"}}, "fast"),
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": {"serial"}}, "fast"),  # serial runs in core too
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": {"fast", "serial"}}, "fast"),
    (["tests/durations.json"], {}, "fast"),
    (["docs/README.md", "tests/durations.json", "AGENTS.md"], {}, "fast"),
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": {"fast", "acceptance"}}, "full"),  # a heavy test module
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": {"adversarial"}}, "full"),
    (["tests/unit/test_x.py"], {"tests/unit/test_x.py": None}, "full"),  # lanes not readable
    (["tests/unit/test_x.py"], {}, "full"),  # lanes not computed
    (["tests/unit/test_x.py", "web/src/App.tsx"], {"tests/unit/test_x.py": {"fast"}}, "full"),  # V3-1
    (["tests/durations.json", "web/package.json"], {}, "full"),  # V3-1
    (["tests/unit/test_x.py", "src/aew/cli/main.py"], {"tests/unit/test_x.py": {"fast"}}, "full"),
    (["tests/unit/conftest.py"], {}, "full"),
    (["tests/unit/helpers.py"], {}, "full"),  # a helper, not a test module
    (["tests/unit/data.json"], {}, "full"),
    (["tests/conftest.py"], {}, "full"),
    (["tests/helpers/lanes.py"], {}, "full"),
    (["tests/integration/test_x.py"], {"tests/integration/test_x.py": {"fast"}}, "full"),  # a heavy directory
    (["tests/fixtures/notes.md"], {}, "full"),
    (["tests/coverage-baseline.json"], {}, "full"),
    (["tests/platform-skips.yaml"], {}, "full"),
    (["Tests/Unit/test_x.py"], {"Tests/Unit/test_x.py": {"fast"}}, "full"),  # not what the lane plugin collects
    (["eval/m3/dogfood/dogfood.py"], {}, "full"),
    (["pyproject.toml", "tests/durations.json"], {}, "full"),
    (["docs/README.md"], {}, "docs"),  # docs-only stays docs: fast needs at least one path that is not documentation
    (["docs/README.md", "web/src/App.tsx"], {}, "web"),
], ids=lambda v: v if isinstance(v, str) else None)
def test_a_change_takes_the_fast_tier_only_when_every_path_is_docs_or_a_fast_lane_test_input(paths, lanes, expected):
    assert tier.decide("pull_request", paths, "main", lanes) == expected


def test_a_forced_change_or_another_event_is_full_whatever_its_paths():
    lanes = {"tests/unit/test_x.py": FAST_ONLY}
    assert tier.decide("pull_request", ["tests/unit/test_x.py"], "main", lanes) == "fast"
    assert tier.decide("pull_request", ["tests/unit/test_x.py"], "main", lanes, forced=True) == "full"
    assert tier.decide("pull_request", ["docs/README.md"], "main", None, forced=True) == "full"
    assert tier.decide("push", ["tests/unit/test_x.py"], "main", lanes) == "full"
    assert tier.decide("pull_request", ["tests/unit/test_x.py"], "feature", lanes) == "full"


PATH_KINDS = {"doc": "docs/README.md", "web": "web/src/App.tsx", "module": "tests/unit/test_x.py",
              "heavy-module": "tests/unit/test_h.py", "durations": "tests/durations.json", "code": "src/aew/x.py"}
KIND_LANES = {"tests/unit/test_x.py": {"fast", "serial"}, "tests/unit/test_h.py": {"fast", "acceptance"}}


def test_no_tier_and_path_kind_combination_escapes_the_runtime_checks():
    """Plan v7 §4 (V3-1): the lane check and the premise check are keyed on the changed paths, not the tier's name.
    Every combination of path kinds, forced or not, is decided; whenever a fast-lane test module changed and the tier
    is reduced, both checks are required. And for every tier a run could be under, a changed module without both
    checks fails the gate unless the tier is full."""
    import itertools

    kinds = sorted(PATH_KINDS)
    for n in range(1, len(kinds) + 1):
        for combo in itertools.combinations(kinds, n):
            for forced in (False, True):
                paths = [PATH_KINDS[k] for k in combo]
                decision = tier.decide("pull_request", paths, "main", KIND_LANES, forced)
                modules = any(tier.fast_kind(p) == "module" for p in paths)
                if {"web", "module"} <= set(combo) or {"web", "durations"} <= set(combo):
                    assert decision == "full", combo
                if modules and decision != "full":
                    assert decision == "fast", combo
                    assert len(tier.check_problems(decision, True, {})) == 2, combo
                for mode in tier.MODES:
                    taken = tier.run_tier(decision, mode)
                    if modules and taken != "full":
                        assert tier.check_problems(taken, True, {}) != [], (combo, mode)
    for name in tier.TIERS + ("",):
        missing = tier.check_problems(name, True, {"lanecheck": "success"})
        assert (missing == []) is (name == "full"), name
        assert tier.check_problems(name, True, {"lanecheck": "success", "premise": "success"}) == []
        assert tier.check_problems(name, False, {}) == []


def test_the_gate_fails_when_a_required_runtime_check_did_not_run():
    jobs = ",".join(f"{k}={v}" for k, v in FAST.items())
    base = ["--jobs-for", "fast", "--jobs", jobs, "--modules-changed", "true"]
    assert tier.main([*base, "--checks", "lanecheck=success,premise=success"]) == 0
    assert tier.main([*base, "--checks", "lanecheck=success,premise=skipped"]) == 1
    assert tier.main([*base, "--checks", "lanecheck=success,premise="]) == 1
    assert tier.main([*base, "--checks", "lanecheck=failure,premise=success"]) == 1
    full = ",".join(f"{k}={v}" for k, v in GREEN.items())
    assert tier.main(["--jobs-for", "full", "--jobs", full, "--modules-changed", "true", "--checks",
                      "lanecheck=success,premise=skipped"]) == 0


# ------------------------------------------------------------------ lanes from markers (plan v7 §3.1)

@pytest.mark.parametrize(("source", "lanes"), [
    ("def test_a(): pass\n", {"fast"}),
    ("import pytest\npytestmark = pytest.mark.serial\ndef test_a(): pass\n", {"serial"}),
    ("import pytest\npytestmark = [pytest.mark.serial, pytest.mark.skipif(True, reason='x')]\ndef test_a(): pass\n",
     {"serial"}),
    ("import pytest\n@pytest.mark.serial\ndef test_a(): pass\ndef test_b(): pass\n", {"serial", "fast"}),
    ("import pytest\n@pytest.mark.acceptance('AT-1')\nclass TestX:\n    def test_a(self): pass\n", {"acceptance"}),
    ("import pytest\nclass TestX:\n    pytestmark = pytest.mark.exploratory\n    def test_a(self): pass\n",
     {"adversarial"}),
    ("import pytest\n@pytest.mark.serial\nclass TestX:\n    class TestY:\n        def test_a(self): pass\n",
     {"serial"}),
    ("import pytest\n@pytest.mark.parametrize('x', [1, pytest.param(2, marks=pytest.mark.acceptance)])\n"
     "def test_a(x): pass\n", {"fast", "acceptance"}),
    ("import pytest\nCASES = [pytest.param(1, marks=[pytest.mark.serial])]\n"
     "@pytest.mark.parametrize('x', CASES)\ndef test_a(x): pass\n", {"fast", "serial"}),
    ("import pytest\nPOSIX_ONLY = pytest.mark.skipif(True, reason='x')\n@POSIX_ONLY\ndef test_a(): pass\n",
     {"fast"}),
    ("import pytest, sys\nif sys.platform == 'win32':\n    @pytest.mark.acceptance\n    def test_a(): pass\n",
     {"acceptance"}),  # a test under a module-level `if` is still collected
    ("def helper(): pass\nclass Heading:\n    pass\n", set()),
])
def test_a_test_modules_lanes_are_read_from_every_level_of_its_marks(source, lanes):
    assert tier.lanes_in_module("tests/unit/test_m.py", source) == lanes


@pytest.mark.parametrize("source", [
    "import functools\n@functools.cache\ndef test_a(): pass\n",  # an unknown decorator
    "MARKS = make()\npytestmark = MARKS\ndef test_a(): pass\n",
    "import pytest\n@pytest.mark.parametrize('x', [pytest.param(1, marks=heavy())])\ndef test_a(x): pass\n",
    "import pytest\n@pytest.mark.parametrize('x', [pytest.param(1, **kw)])\ndef test_a(x): pass\n",
    "from pytest import mark\n@mark.serial\ndef test_a(): pass\n",
    "pytest_plugins = ['x']\ndef test_a(): pass\n",
    "def pytest_collection_modifyitems(items): pass\ndef test_a(): pass\n",
    "import pytest\n@pytest.fixture\ndef thing(): pass\ndef test_a(thing): pass\n",
    "import pytest\n@pytest.fixture(autouse=True)\ndef thing(): pass\ndef test_a(): pass\n",
    "class TestX(Base):\n    pass\n",  # inherits tests whose marks are elsewhere
    "from tests.helpers import test_shared\n",  # an imported test
    "test_alias = make_test()\n",
    "def test_a(:\n",
], ids=["decorator", "pytestmark-name", "param-call", "param-kwargs", "mark-alias", "plugins", "hook", "fixture",
        "autouse-fixture", "inherited", "imported", "assigned", "syntax"])
def test_a_mark_that_cannot_be_read_literally_makes_the_change_full(source):
    with pytest.raises(tier.NotLiteral):
        tier.lanes_in_module("tests/unit/test_m.py", source)


def test_a_merge_commits_tier_is_decided_from_both_versions_of_each_changed_module(tmp_path, monkeypatch):
    """Real git: the merge commit's diff against its first parent, the module's lanes over the merge's and the
    base's versions, the forced flag from the head commit's trailer and the labels; shadow keeps the run full."""
    git = _git(tmp_path)
    git("init", "-q")
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    module = tmp_path / "tests" / "unit" / "test_m.py"
    module.write_text("def test_a(): pass\n", encoding="utf-8")
    (tmp_path / "docs" / "x.md").write_text("x\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-q", "-m", "base")

    def pr(name: str, content: str, message: str = "change") -> str:
        git("checkout", "-q", "-b", name, "main")
        module.write_text(content, encoding="utf-8")
        (tmp_path / "docs" / "x.md").write_text(f"{name}\n", encoding="utf-8")
        git("commit", "-q", "-am", message)
        return _merge(git, name)

    monkeypatch.chdir(tmp_path)

    def run(merge: str, *extra: str) -> tuple[int, dict]:
        out = tmp_path / f"out-{len(list(tmp_path.glob('out-*')))}"
        rc = tier.main(["--event", "pull_request", "--base-ref", "main", "--merge-ref", merge, "--labels", "",
                        "--github-output", str(out), *extra])
        return rc, dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())

    fast = pr("fast", "def test_a(): pass\ndef test_b(): pass\n")
    rc, got = run(fast)
    assert rc == 0 and (got["decision"], got["tier"], got["modules"]) == ("fast", "full", "true")  # shadow
    monkeypatch.setattr(tier, "MODE", "enforce")  # PR 1b's switch
    assert run(fast)[1]["tier"] == "fast"
    monkeypatch.setattr(tier, "MODE", "shadow")
    assert run(fast, "--labels", "full-ci")[1]["decision"] == "full"
    heavy = pr("heavy", "import pytest\n@pytest.mark.acceptance\ndef test_a(): pass\n")
    assert run(heavy)[1]["decision"] == "full"
    trailer = pr("trailer", "def test_a(): pass\ndef test_c(): pass\n", "change\n\nCI-Full: yes")
    assert run(trailer)[1]["decision"] == "full"
    head = git("rev-parse", "trailer")
    assert run(head)[1]["decision"] == "full"  # not a two-parent merge
    # the base's version held a heavy test: changing it is changing a heavy test module
    git("checkout", "-q", "main")
    module.write_text("import pytest\n@pytest.mark.acceptance\ndef test_a(): pass\n", encoding="utf-8")
    git("commit", "-q", "-am", "heavy on main")
    healed = pr("healed", "def test_a(): pass\n")
    assert run(healed)[1]["decision"] == "full"


def test_the_labels_unread_is_full(tmp_path, monkeypatch):
    changed = tmp_path / "changed.txt"
    changed.write_text("docs/README.md\n", encoding="utf-8")
    out = tmp_path / "out"
    assert tier.main(["--event", "pull_request", "--base-ref", "main", "--paths-file", str(changed),
                      "--github-output", str(out)]) == 0  # no --labels, no --repo/--pr: the labels are unknown
    assert "decision=full\n" in out.read_text(encoding="utf-8")


def test_fastbase_is_required_only_when_a_fast_lane_test_module_changed():
    """PR #163 review, V7-2: a fast decision with only docs and tests/durations.json has no premise, so fastbase does
    not run and is not required; with a changed module it must succeed."""
    skipped = {**FAST, "fastbase": "skipped"}
    assert tier.job_problems("fast", skipped, modules_changed=False) == []
    assert tier.job_problems("fast", skipped, modules_changed=True) != []
    jobs = ",".join(f"{k}={v}" for k, v in skipped.items())
    assert tier.main(["--jobs-for", "fast", "--jobs", jobs, "--modules-changed", "false"]) == 0
    assert tier.main(["--jobs-for", "fast", "--jobs", jobs, "--modules-changed", "true", "--checks",
                      "lanecheck=success,premise=success"]) == 1


def test_an_unreadable_label_in_the_recompute_says_so_and_is_retried_once(tmp_path, monkeypatch, capsys):
    """PR #163 review, V7-1 and V7-5: a gh api failure is not a `full-ci` label. The call is retried once, reads up to
    100 labels, and when it still fails the recompute says the flag could not be read."""
    import subprocess

    calls: list[list[str]] = []

    def failing(cmd: list[str]):
        calls.append(cmd)
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(tier, "_run", failing)
    monkeypatch.setattr(tier.time, "sleep", lambda s: None)
    assert tier.live_labels("o/r", "7") is None
    assert len(calls) == 2 and calls[0][2] == "repos/o/r/issues/7/labels?per_page=100"

    def flaky(cmd: list[str]):
        calls.append(cmd)
        if len(calls) == 3:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="full-ci\nbug\n")

    monkeypatch.setattr(tier, "_run", flaky)
    assert tier.live_labels("o/r", "7") == ["full-ci", "bug"]  # the retry succeeded

    changed = tmp_path / "changed.txt"
    changed.write_text("docs/README.md\n", encoding="utf-8")
    base = ["--event", "pull_request", "--base-ref", "main", "--paths-file", str(changed), "--ran", "docs"]
    monkeypatch.setattr(tier, "live_labels", lambda repo, pr: None)
    capsys.readouterr()
    assert tier.main([*base, "--repo", "o/r", "--pr", "7"]) == 1
    err = capsys.readouterr().err
    assert tier.UNREADABLE_MESSAGE in err and tier.FORCED_MESSAGE not in err
    assert tier.main([*base, "--labels", "full-ci"]) == 1
    err = capsys.readouterr().err
    assert tier.FORCED_MESSAGE in err and tier.UNREADABLE_MESSAGE not in err


def test_the_recompute_refuses_a_run_narrower_than_itself(tmp_path, capsys):
    """Plan v7 §4: the recompute reads the forced flag live, and the tier the jobs ran under must not be narrower."""
    changed = tmp_path / "changed.txt"
    changed.write_text("docs/README.md\n", encoding="utf-8")
    base = ["--event", "pull_request", "--base-ref", "main", "--paths-file", str(changed)]
    assert tier.main([*base, "--labels", "", "--ran", "docs"]) == 0
    assert tier.main([*base, "--labels", "", "--ran", "full"]) == 0  # wider is fine (a label removed meanwhile)
    capsys.readouterr()
    assert tier.main([*base, "--labels", "full-ci", "--ran", "docs"]) == 1
    assert tier.FORCED_MESSAGE in capsys.readouterr().err
    assert tier.main([*base, "--labels", "", "--ran", "web"]) == 1
    assert tier.main([*base, "--labels", "", "--ran", ""]) == 1
    assert [tier.covers(r, "fast") for r in tier.TIERS] == [False, True, False, True]


def test_the_decision_record_names_the_commits_the_mode_and_the_eligible_paths(tmp_path, monkeypatch):
    changed = tmp_path / "changed.txt"
    changed.write_text("docs/README.md\ntests/durations.json\n", encoding="utf-8")
    record = tmp_path / "rec" / "tier-decision.json"
    modules = tmp_path / "modules.txt"
    assert tier.main(["--event", "pull_request", "--base-ref", "main", "--paths-file", str(changed), "--labels", "",
                      "--record", str(record), "--modules-out", str(modules)]) == 0
    rec = json.loads(record.read_text(encoding="utf-8"))
    assert rec["schema"] == "aew/tier-decision/v1" and rec["mode"] == tier.MODE == "shadow"
    assert (rec["decision"], rec["tier"], rec["forced"]) == ("fast", "full", False)
    assert rec["eligible"] == {"tests/durations.json": "durations"}
    assert modules.read_text(encoding="utf-8") == ""  # durations.json is not a test module


# ------------------------------------------------------------------ the runtime lane check (plan v7 §4)

def fast_tier_run(lanes: dict[str, str]) -> list[dict]:
    runs = []
    for platform in ("linux", "win32"):
        runs += [report(platform, "fast", {ALL[0]: "passed"}, lanes=dict(lanes)),
                 report(platform, "serial", {ALL[1]: "passed"}, lanes=dict(lanes))]
    return runs


def test_the_runtime_lane_check_passes_when_every_changed_modules_test_is_fast_or_serial():
    runs = fast_tier_run(LANE_OF)
    assert check_assurance.check(runs, EXPECT, ["linux", "win32"], "fast")[0] == []
    assert check_assurance.lane_check(runs, ["tests/unit/test_a.py"], ["linux", "win32"]) == []


def test_a_changed_module_holding_a_heavy_lane_test_fails_the_runtime_lane_check():
    lanes = {**LANE_OF, ALL[1]: "acceptance"}  # a conftest made test_a.py::t2 an acceptance test at runtime
    found = check_assurance.lane_check(fast_tier_run(lanes), ["tests/unit/test_a.py"], ["linux", "win32"])
    assert found and all(check_assurance.HEAVY_MODULE in p for p in found)
    assert any("test_a.py::t2 is in the acceptance lane" in p for p in found)
    unrecorded = check_assurance.lane_check([{**r, "lanes": {}} for r in fast_tier_run(LANE_OF)],
                                            ["tests/unit/test_a.py"], ["linux", "win32"])
    assert any("unrecorded" in p for p in unrecorded)
    missing = check_assurance.lane_check(fast_tier_run(LANE_OF)[:2], ["tests/unit/test_a.py"], ["linux", "win32"])
    assert any(p.startswith("win32: no lane reports") for p in missing)


def test_the_cli_runs_the_lane_check_in_a_reduced_tier_only(tmp_path):
    for i, r in enumerate(fast_tier_run({**LANE_OF, ALL[1]: "acceptance"})):
        (tmp_path / "reports" / f"job{i}").mkdir(parents=True)
        (tmp_path / "reports" / f"job{i}" / "lane.json").write_text(json.dumps(r), encoding="utf-8")
    (tmp_path / "skips.yaml").write_text(yaml.safe_dump(EXPECT), encoding="utf-8")
    (tmp_path / "modules.txt").write_text("tests/unit/test_a.py\n", encoding="utf-8")
    base = [str(tmp_path / "reports"), "--skips", str(tmp_path / "skips.yaml"), "--event", "pull_request",
            "--changed-modules", str(tmp_path / "modules.txt")]
    assert check_assurance.main([*base, "--tier", "fast"]) == 1
    (tmp_path / "modules.txt").write_text("tests/unit/test_other.py\n", encoding="utf-8")
    assert check_assurance.main([*base, "--tier", "fast"]) == 0


# ------------------------------------------------------------------ the coverage premise (plan v7 §5)

BASE_ROOT = "/home/runner/work/_temp/base"
HEAD_ROOT = "/home/runner/work/AEW/AEW"
WIN_ROOT = "D:\\a\\AEW\\AEW"


def write_coverage(where: Path, root: str, arcs: dict[str, set[tuple[int, int]]], sep: str = "/") -> Path:
    """A coverage data file as a Linux job writes it: arcs (branch = true) keyed by absolute path under ``root``."""
    import coverage

    where.mkdir(parents=True, exist_ok=True)
    data = coverage.CoverageData(basename=str(where / ".coverage"), suffix="run1")
    data.add_arcs({sep.join([root, "src", "aew", *rel.split("/")]): a for rel, a in arcs.items()})
    data.write()
    return where


FOOTPRINT = {"engine/a.py": {(-1, 1), (1, 2), (2, 3), (3, -1)}, "cli/b.py": {(-1, 1), (1, -1)}}


def premise(tmp_path: Path, base: dict, head: dict, base_result: str | None = "success", **kw) -> dict:
    return coverage_premise.evaluate(write_coverage(tmp_path / "base", BASE_ROOT, base),
                                     write_coverage(tmp_path / "head", kw.get("head_root", HEAD_ROOT), head,
                                                    kw.get("sep", "/")),
                                     ROOT / "pyproject.toml", base_result)


def test_the_premise_holds_when_this_run_covers_every_base_line_and_arc(tmp_path):
    more = {**FOOTPRINT, "engine/c.py": {(-1, 1), (1, -1)}}  # coverage may rise freely
    result = premise(tmp_path, FOOTPRINT, more)
    assert result["result"] == "holds" and result["files"] == 2


def test_a_two_root_sample_compares_equal_after_path_remapping(tmp_path):
    """V4-3: the base was measured under $RUNNER_TEMP/base, this run under the workspace (and a Windows-style root
    for good measure): keyed by repository-relative path under src/aew, they are the same files."""
    assert premise(tmp_path, FOOTPRINT, FOOTPRINT)["result"] == "holds"
    assert premise(tmp_path / "w", FOOTPRINT, FOOTPRINT, head_root=WIN_ROOT, sep="\\")["result"] == "holds"
    assert coverage_premise.repo_relative(f"{BASE_ROOT}/src/aew/engine/a.py") == "src/aew/engine/a.py"
    assert coverage_premise.repo_relative(f"{WIN_ROOT}\\src\\aew\\engine\\a.py") == "src/aew/engine/a.py"
    assert coverage_premise.repo_relative("/usr/lib/python3/json/__init__.py") is None


def test_a_lost_line_fails_the_premise_with_the_lines(tmp_path):
    lost = {**FOOTPRINT, "engine/a.py": {(-1, 1), (1, 2), (2, -1)}}  # line 3 and two arcs no longer run
    result = premise(tmp_path, FOOTPRINT, lost)
    assert result["result"] == "loss" and result["message"] == coverage_premise.LOSS
    assert result["lost"]["src/aew/engine/a.py"]["lines"] == [3]
    assert "`src/aew/engine/a.py`: lines 3" in coverage_premise.summary(result)


def test_a_test_moved_to_serial_fails_the_premise(tmp_path):
    """Serial runs without coverage: the lines only that test reached vanish from this run's fast lane."""
    result = premise(tmp_path, FOOTPRINT, {"engine/a.py": FOOTPRINT["engine/a.py"]})
    assert result["result"] == "loss" and set(result["lost"]) == {"src/aew/cli/b.py"}


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped", ""])
def test_a_base_that_did_not_pass_leaves_the_premise_unknown(tmp_path, outcome):
    result = premise(tmp_path, FOOTPRINT, FOOTPRINT, base_result=outcome)
    assert result["result"] == "unknown"
    assert result["message"] == f"base footprint unknown (`fastbase`: {outcome}): add `full-ci`, then Re-run all jobs."


def test_missing_base_data_leaves_the_premise_unknown(tmp_path):
    head = write_coverage(tmp_path / "head", HEAD_ROOT, FOOTPRINT)
    for base in (tmp_path / "absent", tmp_path / "empty"):
        (tmp_path / "empty").mkdir(exist_ok=True)
        result = coverage_premise.evaluate(base, head, ROOT / "pyproject.toml", "success")
        assert result["result"] == "unknown" and result["message"].startswith("base footprint unknown (")
    rc = coverage_premise.main(["--base", str(tmp_path / "absent"), "--head", str(head), "--rcfile",
                                str(ROOT / "pyproject.toml"), "--out", str(tmp_path / "p.json")])
    assert rc == 1 and json.loads((tmp_path / "p.json").read_text(encoding="utf-8"))["result"] == "unknown"


def test_the_premise_never_writes_into_the_data_the_ratchet_reads(tmp_path):
    premise(tmp_path, FOOTPRINT, FOOTPRINT)
    assert sorted(p.name for p in (tmp_path / "head").iterdir()) == [".coverage.run1"]


# ------------------------------------------------------------------ the workflow (plan v7 §6, §7)

def strategy_fast_lane_minutes() -> tuple[float, float]:
    """The slowest measured fast-lane step and setup-aew step, from strategy §8."""
    import re

    text = (ROOT / "docs" / "implementation" / "testing-and-ci-strategy.md").read_text(encoding="utf-8")
    section = text.split("## 8. Runtime budgets", 1)[1].split("\n## 9.", 1)[0]
    step = re.search(r"fast-lane step: [\d.]+ to ([\d.]+) minutes", section)
    setup = re.search(r"setup: [\d.]+ to ([\d.]+) minutes", section)
    assert step and setup, "strategy §8 records the fast lane's measured wall time"
    return float(step.group(1)), float(setup.group(1))


def test_fastbase_runs_the_whole_fast_lane_at_the_base_in_its_own_job():
    """Plan v7 §5 (V5-1, V6-1): fastbase needs changes, runs on the mode-independent decision, has a timeout of at
    least twice the slowest measured fast-lane step plus setup, writes its coverage outside the checkout and outside
    the ratchet's artifacts, with exactly the fast step's flags; core is unchanged."""
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]
    outputs = jobs["changes"]["outputs"]
    assert outputs["decision"] == "${{ steps.tier.outputs.decision }}"
    assert outputs["tier"] == "${{ steps.tier.outputs.tier }}"
    base = jobs["fastbase"]
    assert base["needs"] == "changes"
    # only with a changed fast-lane test module: docs plus durations has no premise to check (PR #163 review, V7-2)
    assert base["if"] == "needs.changes.outputs.decision == 'fast' && needs.changes.outputs.modules == 'true'"
    assert outputs["modules"] == "${{ steps.tier.outputs.modules }}"
    assert base["runs-on"] == "ubuntu-latest"
    step, setup = strategy_fast_lane_minutes()
    assert base["timeout-minutes"] == 15 and base["timeout-minutes"] >= 2 * step + setup
    runs = "\n".join(str(s.get("run", "")) for s in base["steps"])
    assert 'git worktree add --detach "$RUNNER_TEMP/base" "$GITHUB_SHA^1"' in runs
    lane = next(s for s in base["steps"] if "pytest" in str(s.get("run", "")))
    assert lane["run"] == ("python -m coverage run -m pytest -q -p no:cacheprovider --lane fast -p no:xdist "
                           "--test-timeout 600")
    assert lane["env"]["COVERAGE_FILE"] == "${{ runner.temp }}/fastbase/.coverage"
    assert lane["env"]["PYTHONPATH"] == "${{ runner.temp }}/base/src"  # absolute: the base's code, not the merge's
    assert lane["working-directory"] == "${{ runner.temp }}/base"
    upload = next(s for s in base["steps"] if "upload-artifact" in s.get("uses", ""))
    assert upload["with"]["name"] == "fastbase-coverage" and upload["if"] == "always()"
    assert not upload["with"]["name"].startswith("coverage-")  # the ratchet combines coverage-* only
    assert "fastbase" in jobs["assurance"]["needs"]
    core = jobs["core"]
    assert core["timeout-minutes"] == 20
    core_runs = "\n".join(str(s.get("run", "")) for s in core["steps"])
    assert "worktree" not in core_runs and "^1" not in core_runs and "fastbase" not in str(core)


def test_assurance_requires_the_runtime_checks_by_path_and_reports_them_in_shadow():
    """Plan v7 §4, §7: the premise step runs when a fast-lane module changed in a reduced tier; --jobs-for gets the
    fastbase result and both checks' outcomes; the shadow step evaluates both on a fast decision the run did not
    take, and can never fail the run."""
    gate = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]["assurance"]
    steps = {s.get("id"): s for s in gate["steps"] if s.get("id")}
    assert '--changed-modules "$RUNNER_TEMP/changed-modules.txt"' in steps["assure"]["run"]
    assert '--modules-out "$RUNNER_TEMP/changed-modules.txt"' in steps["tier"]["run"]
    premise_step = steps["premise"]
    assert premise_step["if"] == ("(success() || failure()) && steps.tier.outputs.tier != 'full' && "
                                  "steps.tier.outputs.modules == 'true'")
    assert "coverage_premise.py --base fastbase-data --head coverage-data/coverage-core-Linux" in premise_step["run"]
    assert '--base-result "$BASE_RESULT"' in premise_step["run"]
    assert premise_step["env"]["BASE_RESULT"] == "${{ needs.fastbase.result }}"
    download = [s["with"]["pattern"] for s in gate["steps"] if "download-artifact" in s.get("uses", "")]
    assert "fastbase-coverage" in download
    final = gate["steps"][-1]
    assert "fastbase=$FASTBASE" in final["run"] and '--checks "lanecheck=$LANECHECK,premise=$PREMISE"' in final["run"]
    assert final["env"]["LANECHECK"] == "${{ steps.assure.outcome }}"
    assert final["env"]["PREMISE"] == "${{ steps.premise.outcome }}"
    assert final["env"]["MODULES"] == "${{ steps.tier.outputs.modules }}"
    shadow = steps["shadow"]
    assert shadow["if"] == "always() && steps.tier.outputs.decision == 'fast' && steps.tier.outputs.tier != 'fast'"
    assert shadow["continue-on-error"] is True and shadow["timeout-minutes"] < gate["timeout-minutes"]
    assert "--tier fast" in shadow["run"] and "coverage_premise.py" in shadow["run"] and "--out" in shadow["run"]
    assert shadow["run"].rstrip().endswith("exit 0")
    assert any(s.get("with", {}).get("name") == "tier-shadow" for s in gate["steps"])


def test_the_shadow_path_runs_fastbase_reports_the_premise_and_never_fails_the_run(tmp_path):
    """Plan v7 §7 (V6-1): decision fast, tier full. fastbase runs (it is keyed on the decision); the premise is
    evaluated from its data and reported; neither its result nor the premise's can fail the full run."""
    assert tier.MODE == "shadow" and tier.run_tier("fast") == "full"
    assert tier.run_tier("fast", "enforce") == "fast" and tier.run_tier("docs") == "docs"
    for fastbase in ("success", "failure", "cancelled"):
        assert tier.job_problems("full", {**GREEN, "fastbase": fastbase}) == []
    assert tier.check_problems("full", True, {}) == []  # the gating checks are not required in shadow
    lost = premise(tmp_path, FOOTPRINT, {"engine/a.py": FOOTPRINT["engine/a.py"]})
    assert lost["result"] == "loss"  # evaluated and reported, by the non-gating step


def test_the_audit_workflow_collects_only_the_heavy_directories_under_the_plugin():
    """Plan v7 §7 (V3-3, V4-3): dispatched by hand only; sharded jobs with -m "not serial" -n auto --dist worksteal and
    one serial job per OS with -p no:xdist, each over tests/integration tests/regression tests/acceptance only."""
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "unit-isolation-audit.yml").read_text(encoding="utf-8"))
    assert set(wf[True]) == {"workflow_dispatch"}  # never on a pull request, a push or a schedule
    jobs = wf["jobs"]
    collect = "python -m pytest tests/integration tests/regression tests/acceptance"
    plugin = "-p unit_isolation_audit --unit-isolation-dir tests/unit"
    parallel = next(s["run"] for s in jobs["parallel"]["steps"] if "pytest" in str(s.get("run", "")))
    serial = next(s["run"] for s in jobs["serial"]["steps"] if "pytest" in str(s.get("run", "")))
    assert parallel.startswith(collect) and serial.startswith(collect)
    assert '-m "not serial" -n auto --dist worksteal' in parallel and "--shard ${{ matrix.shard }}" in parallel
    assert "-m serial -p no:xdist" in serial
    assert plugin in parallel and plugin in serial
    assert {e["os"] for e in jobs["parallel"]["strategy"]["matrix"]["include"]} == {"ubuntu-latest", "windows-latest"}
    assert {e["os"] for e in jobs["serial"]["strategy"]["matrix"]["include"]} == {"ubuntu-latest", "windows-latest"}
    result = "\n".join(str(s.get("run", "")) for s in jobs["result"]["steps"])
    assert "unit_isolation_audit.py --check audit" in result and jobs["result"]["if"] == "always()"
    # a shard that stopped at collection still writes a clean report: both audited jobs must succeed (V7-4)
    assert 'test "$PARALLEL" = success' in result and 'test "$SERIAL" = success' in result
    assert jobs["result"]["steps"][-1]["env"] == {"PARALLEL": "${{ needs.parallel.result }}",
                                                  "SERIAL": "${{ needs.serial.result }}"}


def test_the_audit_plugin_catches_a_heavy_module_importing_a_unit_module(tmp_path):
    """Plan v7 §7: a synthetic heavy module imports a unit module at top level and inside a test; the audit records
    the import by module name and the open of the unit file by path, names the test and the importer."""
    import subprocess

    unit, heavy, out = tmp_path / "unit", tmp_path / "heavy", tmp_path / "audit"
    unit.mkdir()
    heavy.mkdir()
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")  # keeps the repository's conftest out
    (unit / "test_widget.py").write_text("VALUE = 1\n", encoding="utf-8")
    (unit / "test_gadget.py").write_text("VALUE = 2\n", encoding="utf-8")
    (heavy / "test_heavy.py").write_text(
        "import test_widget\n\n"
        "def test_reaches_in():\n"
        "    import test_gadget\n"
        "    assert test_widget.VALUE + test_gadget.VALUE == 3\n", encoding="utf-8")
    env = {k: v for k, v in __import__("os").environ.items() if not k.startswith(("PYTEST_", "COV_", "COVERAGE"))}
    env["PYTHONPATH"] = __import__("os").pathsep.join([str(ROOT / "tools" / "ci"), str(unit)])
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                           "-p", "unit_isolation_audit", "--unit-isolation-dir", str(unit),
                           "--unit-isolation-report", str(out), "heavy"],
                          cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    violations = [v for f in out.glob("audit-*.json") for v in json.loads(f.read_text(encoding="utf-8"))["violations"]]
    whys = [v["why"] for v in violations]
    assert "import of test_widget" in whys and "import of test_gadget" in whys  # top level and inside a function
    opened = [w for w in whys if w.startswith("open of ")]
    assert any(w.endswith("test_widget.py") for w in opened) and any(w.endswith("test_gadget.py") for w in opened)
    inside = next(v for v in violations if v["why"] == "import of test_gadget")
    assert "test_reaches_in" in (inside["test"] or "") and "test_heavy.py" in (inside["importer"] or "")
    problems = unit_isolation_audit.check(out)
    assert problems and all("test_" in p for p in problems)
    assert unit_isolation_audit.check(tmp_path / "nothing") == [f"no audit reports under {tmp_path / 'nothing'}: "
                                                                "the audit did not run"]


def test_the_audit_flags_a_subprocess_naming_a_unit_file_and_ignores_the_rest(tmp_path):
    (tmp_path / "unit").mkdir()
    (tmp_path / "unit" / "test_widget.py").write_text("", encoding="utf-8")
    auditor = unit_isolation_audit.Auditor(tmp_path / "unit")
    target = str(tmp_path / "unit" / "test_widget.py")
    assert auditor.classify("subprocess.Popen", ("python", ["python", target], None, None))
    assert auditor.classify("subprocess.Popen", ("python", ["python", "-c", "1"], None, {"X": target}))
    assert auditor.classify("open", (target, "r", 0))
    assert auditor.classify("import", ("pkg.test_widget", None, [], [], []))
    assert auditor.classify("subprocess.Popen", ("python", ["python", "-c", "1"], None, None)) is None
    assert auditor.classify("open", (str(tmp_path / "unit" / "notes.txt"), "r", 0)) is None
    assert auditor.classify("import", ("json", None, [], [], [])) is None
