"""The pin-only shortcut: when a run may reuse an earlier run's lane reports, and how it falls back to its tier."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("pin_shortcut", ROOT / "tools" / "ci" / "pin_shortcut.py")
assert _spec and _spec.loader
pin_shortcut = importlib.util.module_from_spec(_spec)
sys.modules["pin_shortcut"] = pin_shortcut
_spec.loader.exec_module(pin_shortcut)
check_assurance = pin_shortcut.check_assurance
tiers = pin_shortcut.tiers

REPO = "o/r"
PINS = "tests/platform-skips.yaml"
RUN = 500
A, B = "tests/unit/test_a.py::test_a", "tests/unit/test_a.py::test_b"


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                          capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()


def _commit(cwd: Path, message: str, **files: str) -> str:
    for name, text in files.items():
        path = cwd / {"pins": PINS, "code": "src.txt"}[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    _git(cwd, "add", "-A")
    _git(cwd, "commit", "-qm", message)
    return _git(cwd, "rev-parse", "HEAD")


def _merged(cwd: Path) -> str:
    """GitHub's test merge: main first, the pull request's head second."""
    _git(cwd, "checkout", "-q", "main")
    _git(cwd, "merge", "-q", "--no-ff", "-m", "merge", "pr")
    return _git(cwd, "rev-parse", "HEAD")


def _pins(*skips: str) -> str:
    return yaml.safe_dump({"schema": check_assurance.SKIPS_SCHEMA, "skipped": {"linux": dict.fromkeys(skips, "r")}})


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """A pull request: a head that went red for a skip, then a commit pinning it."""
    cwd = tmp_path_factory.mktemp("repo")
    _git(cwd, "init", "-q", "-b", "main")
    base = _commit(cwd, "base", pins=_pins(), code="1\n")
    _git(cwd, "checkout", "-q", "-b", "pr")
    earlier = _commit(cwd, "the change", code="2\n")
    head = _commit(cwd, "pin the skip", pins=_pins(B))
    merge = _merged(cwd)
    _git(cwd, "tag", "the-test-merge")  # only GitHub's test ref holds this: `main` itself stays at the base
    _git(cwd, "checkout", "-q", "pr")
    _git(cwd, "branch", "-q", "-f", "main", base)
    return {"cwd": cwd, "base": base, "earlier": earlier, "head": head, "merge": merge}


def report(platform="linux", b="skipped", *, exitstatus=0, shard=None, results=None):
    results = {A: "passed", B: b} if results is None else results
    return {"schema": check_assurance.REPORT_SCHEMA, "platform": platform, "lane": "fast", "shard": shard,
            "collected": sorted(results),
            "results": {nid: {"outcome": o, "duration": 0.1} for nid, o in results.items()},
            "exitstatus": exitstatus}


JOBS = [{"name": "tier", "conclusion": "success"}, {"name": "fast 1/1 (ubuntu-latest)", "conclusion": "success"},
        {"name": "lanes-skipped", "conclusion": "skipped"}, {"name": "assurance", "conclusion": "failure"}]
ARTIFACTS = ["lane-report-core-fast-1-Linux", "coverage-core-fast-1-Linux", "tier-decision"]
PR = 7


class GitHub:
    """Stands in for the API: one finished run per head it's told of, its jobs, artifacts and reports."""

    def __init__(self, base):
        self.base = base
        self.records = {}
        self.expired = {}
        self.runs = {}
        self.jobs = {}
        self.artifacts = {}
        self.reports = {}

    def has_run(self, sha, run_id=RUN, *, status="completed", conclusion="failure", head_repo=REPO, jobs=None,
                artifacts=None, reports=None, pr=PR, record=None, expired=()):
        self.runs.setdefault(sha, []).append(
            {"id": run_id, "head_sha": sha, "status": status, "conclusion": conclusion, "html_url": f"u/{run_id}",
             "head_repository": {"full_name": head_repo}, "pull_requests": [{"number": pr}] if pr else []})
        self.records[run_id] = {"base": self.base, "base_ref": "main", **(record or {})}
        self.expired[run_id] = list(expired)
        self.jobs[run_id] = JOBS if jobs is None else jobs
        self.artifacts[run_id] = ARTIFACTS if artifacts is None else artifacts
        self.reports[run_id] = [report(), report("win32", "passed")] if reports is None else reports

    def api(self, path):
        if m := re.search(r"runs\?head_sha=(\w+)&", path):
            return {"workflow_runs": self.runs.get(m[1], [])}
        if m := re.search(r"runs/(\d+)/jobs", path):
            return {"total_count": len(self.jobs[int(m[1])]), "jobs": self.jobs[int(m[1])]}
        if m := re.search(r"runs/(\d+)/artifacts", path):
            return {"artifacts": [{"name": n, "expired": False} for n in self.artifacts[int(m[1])]]
                    + [{"name": n, "expired": True} for n in self.expired[int(m[1])]]}
        raise AssertionError(path)

    def record(self, run_id, _repo, _dest):
        return self.records[run_id]

    def download(self, run_id, _repo, dest):
        dest.mkdir(parents=True, exist_ok=True)
        for i, data in enumerate(self.reports[run_id]):
            (dest / f"{i}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def github(monkeypatch, tree):
    fake = GitHub(tree["base"])
    monkeypatch.chdir(tree["cwd"])
    monkeypatch.setattr(pin_shortcut, "_gh_json", fake.api)
    monkeypatch.setattr(pin_shortcut, "download_reports", fake.download)
    monkeypatch.setattr(pin_shortcut, "run_record", fake.record)
    monkeypatch.setattr(tiers, "live_labels", lambda _repo, _pr: [])
    return fake


def reused(tmp_path, merge, *extra, event="pull_request", base="main", head_repo=REPO):
    """What the tier job would hand on: the run id, or ''."""
    out = tmp_path / "out.txt"
    assert pin_shortcut.main(["--event", event, "--base-ref", base, "--merge-ref", merge, "--repo", REPO, "--pr",
                              str(PR), "--head-repo", head_repo, "--reports-dir", str(tmp_path / "reports"),
                              "--github-output", str(out), *extra]) == 0
    return dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())["reuse_run"]


def test_a_head_that_only_added_pins_after_a_run_only_short_of_pins_reuses_that_run(github, tree, tmp_path, capsys):
    github.has_run(tree["earlier"])
    assert reused(tmp_path, tree["merge"]) == str(RUN)
    assert f"run {RUN}" in capsys.readouterr().out


def test_the_summary_says_which_run_and_head_the_lanes_ran_at(github, tree, tmp_path):
    github.has_run(tree["earlier"])
    summary = tmp_path / "summary.md"
    reused(tmp_path, tree["merge"], "--summary", str(summary))
    text = summary.read_text(encoding="utf-8")
    assert tree["earlier"] in text and f"run {RUN}" in text and f"u/{RUN}" in text and PINS in text


@pytest.mark.parametrize("kwargs", [{"event": "push"}, {"event": "schedule"}, {"base": "release"},
                                    {"head_repo": "someone/fork"}], ids=["push", "nightly", "other_base", "fork"])
def test_only_a_pull_request_into_main_from_this_repository_takes_it(github, tree, tmp_path, kwargs):
    github.has_run(tree["earlier"])
    assert reused(tmp_path, tree["merge"], **kwargs) == ""


@pytest.mark.parametrize("labels", [["full-ci"], None], ids=["full_ci_label", "labels_unreadable"])
def test_the_full_ci_label_or_unreadable_labels_take_the_normal_tier(github, tree, tmp_path, monkeypatch, labels):
    github.has_run(tree["earlier"])
    monkeypatch.setattr(tiers, "live_labels", lambda _repo, _pr: labels)
    assert reused(tmp_path, tree["merge"]) == ""


def _extended(tree, tmp_path, message="more", **files) -> dict[str, str]:
    """A copy of the pull request with one more commit on it, whatever it changes."""
    cwd = tmp_path / "copy"
    _git(tmp_path, "clone", "-q", "--branch", "pr", str(tree["cwd"]), str(cwd))
    _git(cwd, "fetch", "-q", "origin", "main:main")
    _git(cwd, "branch", "-q", "--set-upstream-to", "origin/main")
    head = _commit(cwd, message, **files)
    return {"cwd": cwd, "head": head, "merge": _merged(cwd)}


def test_a_trailer_forcing_full_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["earlier"])
    copy = _extended(tree, tmp_path, "more pins\n\nCI-Full: yes", pins=_pins(A, B))
    monkeypatch.chdir(copy["cwd"])
    assert reused(tmp_path, copy["merge"]) == ""


def test_a_commit_changing_any_other_path_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["earlier"])
    copy = _extended(tree, tmp_path, pins=_pins(A, B), code="3\n")
    monkeypatch.chdir(copy["cwd"])
    assert reused(tmp_path, copy["merge"]) == ""


def test_a_commit_changing_only_another_path_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["head"])
    copy = _extended(tree, tmp_path, code="3\n")
    monkeypatch.chdir(copy["cwd"])
    assert reused(tmp_path, copy["merge"]) == ""


def test_a_merge_of_main_between_the_heads_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    """Any merge ends the walk, even one whose only change against the earlier head is the pins: `main` came with it."""
    github.has_run(tree["head"])
    cwd = tmp_path / "copy"
    _git(tmp_path, "clone", "-q", "--branch", "pr", str(tree["cwd"]), str(cwd))
    _git(cwd, "fetch", "-q", "origin", "main:main")
    _git(cwd, "checkout", "-q", "main")
    _commit(cwd, "main moved", pins=_pins(A))
    _git(cwd, "checkout", "-q", "pr")
    _git(cwd, "merge", "-q", "--no-ff", "-X", "theirs", "-m", "main in", "main")
    assert len(_git(cwd, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3, "the case needs a real merge"
    assert _git(cwd, "diff-tree", "--name-only", "-r", "HEAD^1", "HEAD") == PINS
    monkeypatch.chdir(cwd)
    assert reused(tmp_path, _merged(cwd)) == ""


def test_the_walk_is_bounded(github, tree, monkeypatch):
    monkeypatch.chdir(tree["cwd"])
    assert list(pin_shortcut.pin_only_ancestors(tree["head"], limit=0)) == []
    assert list(pin_shortcut.pin_only_ancestors(tree["head"])) == [tree["earlier"]]


def test_a_run_at_no_earlier_head_takes_the_normal_tier(github, tree, tmp_path):
    assert reused(tmp_path, tree["merge"]) == ""


@pytest.mark.parametrize("run", [{"status": "in_progress"}, {"head_repo": "someone/fork"}], ids=["running", "fork_run"])
def test_a_run_not_finished_or_from_elsewhere_isnt_used(github, tree, tmp_path, run):
    github.has_run(tree["earlier"], **run)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_job_that_failed_takes_the_normal_tier_whatever_its_reports_say(github, tree, tmp_path):
    github.has_run(tree["earlier"], jobs=[*JOBS, {"name": "static", "conclusion": "failure"}])
    assert reused(tmp_path, tree["merge"]) == ""


@pytest.mark.parametrize("conclusion", ["cancelled", "timed_out", None], ids=["cancelled", "timed_out", "none"])
def test_a_job_that_didnt_end_well_takes_the_normal_tier(github, tree, tmp_path, conclusion):
    github.has_run(tree["earlier"], jobs=[*JOBS, {"name": "integration", "conclusion": conclusion}])
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_list_of_jobs_it_didnt_read_all_of_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    """A failure on the second page mustn't pass as no failure."""
    github.has_run(tree["earlier"])
    real = github.api
    monkeypatch.setattr(pin_shortcut, "_gh_json",
                        lambda path: {**real(path), "total_count": 101} if "/jobs" in path else real(path))
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_run_with_no_gate_job_takes_the_normal_tier(github, tree, tmp_path):
    github.has_run(tree["earlier"], jobs=[j for j in JOBS if j["name"] != "assurance"])
    assert reused(tmp_path, tree["merge"]) == ""


@pytest.mark.parametrize("artifacts", [[], ["lane-report-x", "tier-decision"], ["coverage-x", "tier-decision"],
                                       ["lane-report-x", "coverage-x"]],
                         ids=["none", "coverage_gone", "reports_gone", "record_gone"])
def test_reports_coverage_or_the_record_past_their_days_take_the_normal_tier(github, tree, tmp_path, artifacts):
    github.has_run(tree["earlier"], artifacts=artifacts)
    assert reused(tmp_path, tree["merge"]) == ""


def test_an_artifact_the_api_lists_as_expired_isnt_there(github, tree, tmp_path):
    """Coverage lives 7 days and reports 14, and the real API goes on listing what expired, under its name."""
    github.has_run(tree["earlier"], artifacts=["lane-report-x", "tier-decision"], expired=["coverage-x"])
    assert reused(tmp_path, tree["merge"]) == ""


def test_another_pull_requests_run_at_that_head_isnt_used(github, tree, tmp_path):
    github.has_run(tree["earlier"], pr=PR + 1)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_run_tied_to_no_pull_request_isnt_used(github, tree, tmp_path):
    """The API's list is empty once a pull request has merged: a branch started from its head can't reuse its run."""
    github.has_run(tree["earlier"], pr=None)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_run_that_merged_into_another_branch_isnt_used(github, tree, tmp_path):
    github.has_run(tree["earlier"], record={"base_ref": "release"})
    assert reused(tmp_path, tree["merge"]) == ""


@pytest.mark.parametrize("record", [{"base": "0" * 40}, {"base": None}], ids=["unknown_commit", "no_base"])
def test_a_base_that_cant_be_read_takes_the_normal_tier(github, tree, tmp_path, record):
    github.has_run(tree["earlier"], record=record)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_record_with_no_base_at_all_takes_the_normal_tier(github, tree, tmp_path):
    github.has_run(tree["earlier"])
    del github.records[RUN]["base"]
    assert reused(tmp_path, tree["merge"]) == ""


def test_main_dropping_a_pin_since_the_run_takes_the_normal_tier(github, tree, tmp_path):
    """The run started while `main` still pinned it. Else `assurance` says to pin what `main` just made run, the author
    does, the pull request goes green, and `main`'s push run goes red."""
    github.has_run(tree["earlier"], record={"base": tree["head"]})  # any commit whose pins say more than this base's
    assert reused(tmp_path, tree["merge"]) == ""


def _main_moved(tree, tmp_path, pins) -> Path:
    """A copy where `main` changed the pin file after the pull request's run started, merged keeping `main`'s side."""
    cwd = tmp_path / "copy"
    _git(tmp_path, "clone", "-q", "--branch", "pr", str(tree["cwd"]), str(cwd))
    _git(cwd, "fetch", "-q", "origin", "main:main")
    _git(cwd, "checkout", "-q", "main")
    _commit(cwd, "main moved", pins=pins)
    _git(cwd, "merge", "-q", "--no-ff", "-X", "ours", "-m", "merge", "pr")
    assert len(_git(cwd, "rev-list", "--parents", "-n", "1", "HEAD").split()) == 3, "the case needs a real merge"
    return cwd


def test_main_adding_a_pin_since_the_run_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    """Those reports don't hold `main`'s new test, so `assurance` could only say the pin no longer exists."""
    github.has_run(tree["earlier"])
    cwd = _main_moved(tree, tmp_path, _pins(A))
    monkeypatch.chdir(cwd)
    assert reused(tmp_path, _git(cwd, "rev-parse", "HEAD")) == ""


def test_main_only_reformatting_the_pins_doesnt_refuse_a_shortcut_that_would_pass(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["earlier"])
    cwd = _main_moved(tree, tmp_path, "# a comment\n" + _pins())
    monkeypatch.chdir(cwd)
    assert reused(tmp_path, _git(cwd, "rev-parse", "HEAD")) == str(RUN)


def test_a_merge_of_more_than_two_parents_takes_the_normal_tier(github, tree, tmp_path, monkeypatch):
    """GitHub's test merge has two, and the head is the second."""
    github.has_run(tree["earlier"])
    cwd = tmp_path / "copy"
    _git(tmp_path, "clone", "-q", "--branch", "pr", str(tree["cwd"]), str(cwd))
    _git(cwd, "fetch", "-q", "origin", "main:main")
    _git(cwd, "checkout", "-q", "-b", "other", tree["base"])
    _commit(cwd, "other", code="9\n")
    tree_id = _git(cwd, "rev-parse", "pr^{tree}")
    octopus = _git(cwd, "commit-tree", tree_id, "-p", tree["base"], "-p", "pr", "-p", "other", "-m", "octopus")
    monkeypatch.chdir(cwd)
    assert reused(tmp_path, octopus) == ""


def test_nothing_else_reads_the_pins():
    """A pin-only head runs no lane, so a test reading the pin file's content wouldn't run on the new pins. Each reader
    below is covered at that head, or isn't one. A new one fails here: run its check in `static`, then list it. A reader
    that builds the path indirectly is outside this."""
    readers = {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").rglob("*.py")
               if re.search(r"platform-skips|load_expectations\(|pins_of\(", path.read_text(encoding="utf-8"))}
    assert readers == {
        "tests/integration/test_egress_host_local.py",  # names it in a comment
        "tests/integration/test_store_modes.py",  # names it in a comment
        "tests/unit/test_ci_tools.py",  # calls `manifest_problems`, which `static` runs; a path in the tier table
        "tests/unit/test_discovery_rules.py",  # its own synthetic file
        "tests/unit/test_pin_shortcut.py",  # this file
        "tests/unit/test_skip_pins.py",  # the same check `static` runs
    }


@pytest.mark.parametrize(("data", "says"), [
    ({"skipped": {"win32": {A: "r"}, "linux": {B: "r"}}}, None),
    ({"skipped": {"win32": {A: ""}, "linux": {}}}, "gives no reason"),
    ({"skipped": {"win32": {}, "linux": {A: None}}}, "gives no reason"),
    ({"skipped": {"win32": {A: "  "}, "linux": {}}}, "gives no reason"),
    ({"skipped": {"win32": {}, "linux": {}, "darwin": {A: "r"}}}, "platforms"),
    ({"skipped": {"win32": {}}}, "platforms"),
    ({}, "platforms"),
], ids=["good", "empty_reason", "bare_pin", "blank_reason", "extra_platform", "missing_platform", "nothing"])
def test_the_pin_files_own_content_is_checked_where_a_reused_head_runs_it(data, says, tmp_path, capsys):
    """`skip_pins.py` is in `static`, which runs at every head. Without this, a pin with no reason would pass `static`
    and `assurance`, and `main`'s push run would go red in the fast lane."""
    problems = check_assurance.manifest_problems(data)
    assert (says is None) == (not problems) and (says is None or says in problems[0]), problems
    skips = tmp_path / "skips.yaml"
    skips.write_text(yaml.safe_dump(data), encoding="utf-8")
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / "tests" / "unit" / "test_a.py").write_text("def test_a(): pass\ndef test_b(): pass\n", encoding="utf-8")
    code = pin_shortcut_guard().main(["--skips", str(skips), "--tests", str(tmp_path / "tests")])
    assert code == (0 if says is None else 1)


def pin_shortcut_guard():
    """`tools/ci/skip_pins.py`, the module `static` runs."""
    spec = importlib.util.spec_from_file_location("skip_pins_for_shortcut", ROOT / "tools" / "ci" / "skip_pins.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", ["tools/ci/pin_shortcut.py", "tools/ci/check_assurance.py", "tools/ci/tier.py",
                                  ".github/workflows/ci.yml", ".github/actions/x/action.yml", "tests/helpers/lanes.py"])
def test_a_pull_request_touching_cis_own_code_never_takes_the_shortcut(path, tmp_path):
    """Apart from the walk, so a slip in the walk can't skip the tests that would catch it."""
    assert tiers.shortcut_barred(["src/x.py", path])
    changed = tmp_path / "paths.txt"
    changed.write_text(f"{path}\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    assert tiers.main(["--event", "pull_request", "--paths-file", str(changed), "--labels", "", "--github-output",
                       str(out)]) == 0
    assert "reusable=false\n" in out.read_text(encoding="utf-8")


def test_any_other_change_may_take_it_and_unknown_paths_may_not(tmp_path):
    assert not tiers.shortcut_barred(["src/x.py", "tests/unit/test_a.py", PINS, "tests/helpers/other.py"])
    assert tiers.shortcut_barred(None)
    changed = tmp_path / "paths.txt"
    changed.write_text("src/x.py\n", encoding="utf-8")
    out = tmp_path / "out.txt"
    assert tiers.main(["--event", "pull_request", "--paths-file", str(changed), "--labels", "", "--github-output",
                       str(out)]) == 0
    assert "reusable=true\n" in out.read_text(encoding="utf-8")


NOT_ONLY_SKIPS = {
    "failed_test": [report("linux", "failed", exitstatus=1), report("win32", "passed")],
    "error": [report("linux", "error", exitstatus=1), report("win32", "passed")],
    "session_exit": [report("linux", exitstatus=2), report("win32", "passed")],
    "platform_missing": [report("linux")],
    "never_ran": [{**report(), "results": {A: {"outcome": "passed", "duration": 0.1}}}, report("win32", "passed")],
    "lost_shard": [report(shard="1/2"), report("win32", "passed")],
    "unpinned_xfail": [report("linux", "xfailed"), report("win32", "passed")],
    "no_reports": [],
}


@pytest.mark.parametrize("reports", NOT_ONLY_SKIPS.values(), ids=NOT_ONLY_SKIPS.keys())
def test_reports_that_say_more_than_skips_take_the_normal_tier(github, tree, tmp_path, reports):
    """Exactly what `assurance` says of them, so every other thing it can say counts against the shortcut."""
    github.has_run(tree["earlier"], reports=reports)
    assert reused(tmp_path, tree["merge"]) == ""


def test_every_skip_complaint_of_assurance_is_one_it_recognises():
    """The complaints come from `check_assurance`, so its wording is pinned here by running it, not restated by hand."""
    stale = {"skipped": {"linux": {"tests/gone.py::test": "r"}, "win32": {A: "r"}}}
    problems = check_assurance.check([report(), report("win32", "passed")], stale, ["linux", "win32"])[0]
    assert len(problems) == 3
    assert all(pin_shortcut.SKIP_COMPLAINT.match(p) for p in problems), problems


def test_a_run_with_nothing_wrong_at_all_can_be_reused(github, tree, tmp_path):
    """The pins commit then has to be right in its own run: pinning what doesn't skip fails in `assurance`."""
    github.has_run(tree["earlier"], reports=[report("linux", "passed"), report("win32", "passed")])
    assert reused(tmp_path, tree["merge"]) == str(RUN)


@pytest.mark.parametrize("error", [subprocess.CalledProcessError(1, "gh"), OSError("gh"), ValueError("bad json")],
                         ids=["gh_fails", "no_gh", "bad_json"])
def test_any_error_reading_the_run_is_the_normal_tier_and_no_failure(github, tree, tmp_path, monkeypatch, error):
    github.has_run(tree["earlier"])

    def broken(*_args):
        raise error
    monkeypatch.setattr(pin_shortcut, "_gh_json", broken)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_report_that_cant_be_read_is_the_normal_tier(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["earlier"])

    def garbled(_run_id, _repo, dest):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "r.json").write_text("{", encoding="utf-8")
    monkeypatch.setattr(pin_shortcut, "download_reports", garbled)
    assert reused(tmp_path, tree["merge"]) == ""


def test_a_download_that_fails_is_the_normal_tier(github, tree, tmp_path, monkeypatch):
    github.has_run(tree["earlier"])

    def fails(*_args):
        raise subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(pin_shortcut, "download_reports", fails)
    assert reused(tmp_path, tree["merge"]) == ""


@pytest.fixture
def two_pin_commits(github, tree, tmp_path, monkeypatch):
    """The first pins were wrong, so a second commit fixes them: the nearest head has a run, the one before it too."""
    copy = _extended(tree, tmp_path, pins=_pins(A, B))
    monkeypatch.chdir(copy["cwd"])
    github.has_run(tree["earlier"], RUN)
    return copy


def test_a_run_the_next_push_cancelled_is_passed_over_for_the_one_before_it(github, tree, two_pin_commits, tmp_path):
    github.has_run(tree["head"], RUN + 1, conclusion="cancelled", jobs=[], artifacts=[], reports=[])
    assert reused(tmp_path, two_pin_commits["merge"]) == str(RUN)


def test_wrong_pins_retried_go_back_to_the_same_reports_not_a_full_run(github, tree, two_pin_commits, tmp_path):
    """The nearest run reused its lanes, so it has none to give; the one it took them from still does."""
    no_lanes = [{"name": "tier", "conclusion": "success"}, {"name": "core", "conclusion": "skipped"},
                {"name": "assurance", "conclusion": "failure"}]
    github.has_run(tree["head"], RUN + 1, jobs=no_lanes, artifacts=[], reports=[])
    assert reused(tmp_path, two_pin_commits["merge"]) == str(RUN)


def test_a_job_failing_at_the_nearest_head_isnt_hidden_by_an_older_green_run(github, tree, two_pin_commits, tmp_path):
    github.has_run(tree["head"], RUN + 1, jobs=[*JOBS, {"name": "static", "conclusion": "failure"}])
    assert reused(tmp_path, two_pin_commits["merge"]) == ""


def test_a_failure_at_the_nearest_head_isnt_hidden_by_an_older_green_run(github, tree, two_pin_commits, tmp_path):
    """The same tree: it would be a flake, and a flake is a defect to look at."""
    github.has_run(tree["head"], RUN + 1, reports=[report("linux", "failed", exitstatus=1), report("win32", "passed")])
    assert reused(tmp_path, two_pin_commits["merge"]) == ""


def test_the_earlier_heads_own_pins_judge_it_so_a_pin_added_since_cant_clear_it(github, tree, tmp_path, monkeypatch):
    """A later xfail pin forgives nothing: at the earlier head it was unpinned, and that isn't a complaint of skips."""
    github.has_run(tree["earlier"], reports=[report("linux", "xfailed"), report("win32", "passed")])
    pins = yaml.safe_load(_pins(B))
    copy = _extended(tree, tmp_path, pins=yaml.safe_dump({**pins, "xfail": {"linux": {B: "r"}}}))
    monkeypatch.chdir(copy["cwd"])
    assert reused(tmp_path, copy["merge"]) == ""


@pytest.mark.parametrize(("pins", "wants"), [
    (_pins(B), []),
    (_pins(), ["unexpected skip"]),
    (_pins(A, B), ["pinned skip now passed"]),
    (_pins(B, "tests/gone.py::test"), ["pinned skip no longer exists"]),
], ids=["right", "too_few", "pins_what_passed", "pins_what_is_gone"])
def test_the_gate_judges_the_reused_reports_against_the_new_pins(pins, wants):
    problems = check_assurance.check([report(), report("win32", "passed")], yaml.safe_load(pins), ["linux", "win32"])[0]
    assert len(problems) == len(wants) and all(w in p for w, p in zip(wants, problems, strict=True)), problems


def test_a_pin_cant_forgive_a_failed_test_in_the_gate():
    problems = check_assurance.check([report("linux", "failed", exitstatus=1), report("win32", "passed")],
                                     yaml.safe_load(_pins(B)), ["linux", "win32"])[0]
    assert any("failed:" in p for p in problems), problems


def test_assurance_fails_if_the_recompute_doesnt_name_the_run_the_jobs_were_skipped_for(github, tree, tmp_path, capsys):
    """A label added while the run went, or a report gone: no lane ran, so green here would be proof of nothing."""
    argv = ["--event", "pull_request", "--base-ref", "main", "--merge-ref", tree["merge"], "--repo", REPO, "--pr",
            str(PR), "--head-repo", REPO, "--reports-dir", str(tmp_path / "reports")]
    assert pin_shortcut.main([*argv, "--expect", str(RUN)]) == 1
    said = capsys.readouterr().err
    assert "add `full-ci`, then Re-run all jobs" in said and "Re-run failed jobs" in said
    github.has_run(tree["earlier"], RUN + 1)
    assert pin_shortcut.main([*argv, "--expect", str(RUN)]) == 1
    assert pin_shortcut.main([*argv, "--expect", str(RUN + 1)]) == 0


def test_the_way_out_it_prints_reaches_the_normal_tier(github, tree, tmp_path, monkeypatch):
    """Following it: the label, then Re-run all jobs, which starts again at the tier job, which names no run."""
    github.has_run(tree["earlier"])
    assert reused(tmp_path, tree["merge"]) == str(RUN)
    monkeypatch.setattr(tiers, "live_labels", lambda _repo, _pr: [tiers.FORCE_LABEL])
    assert reused(tmp_path, tree["merge"]) == ""


def test_under_a_reused_run_core_and_lanes_must_be_skipped_and_the_rest_still_pass():
    good = {"changes": "success", "core": "skipped", "lanes": "skipped", "web": "success", "static": "success",
            "fastbase": "skipped"}
    assert tiers.job_problems(tiers.REUSED, good) == []
    for job, result in (("core", "success"), ("lanes", "failure"), ("static", "failure"), ("web", "skipped")):
        assert tiers.job_problems(tiers.REUSED, {**good, job: result}), job
    assert tiers.job_problems("full", good), "a plain full run with its lanes skipped still fails"
    assert tiers.check_problems(tiers.REUSED, True, {}) == []


def test_reused_isnt_a_tier_a_change_can_be_given():
    assert tiers.REUSED not in tiers.TIERS


def _workflow():
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _uses(job, name):
    return [s for s in job["steps"] if name in (s.get("name") or s.get("id") or "")]


def test_only_core_and_lanes_stop_for_a_reused_run_and_only_when_it_names_one():
    jobs = _workflow()
    assert jobs["core"]["if"] == "needs.changes.outputs.reuse_run == ''"
    assert jobs["lanes"]["if"].endswith("&& needs.changes.outputs.reuse_run == ''")
    for job in ("web", "static", "assurance"):
        assert "reuse_run" not in str(jobs[job].get("if")), job


def test_the_tier_jobs_step_cant_fail_the_run_or_outlast_the_job():
    job = _workflow()["changes"]
    step = next(s for s in job["steps"] if s.get("id") == "reuse")
    assert step["continue-on-error"] is True
    assert step["timeout-minutes"] < job["timeout-minutes"]
    assert "steps.tier.outputs.tier == 'full'" in step["if"]
    assert "steps.tier.outputs.reusable == 'true'" in step["if"], "apart from the walk"
    assert job["outputs"]["reuse_run"] == "${{ steps.reuse.outputs.reuse_run }}"
    assert job["permissions"]["actions"] == "read"


def test_assurance_works_it_out_again_reads_that_runs_reports_and_checks_the_jobs_as_reused():
    job = _workflow()["assurance"]
    recheck = _uses(job, "The pin-only shortcut")
    assert len(recheck) == 1 and '--expect "$REUSE_RUN"' in recheck[0]["run"]
    assert "continue-on-error" not in recheck[0], "this one decides"
    assert job["permissions"]["actions"] == "read"
    downloads = [s for s in job["steps"] if "download-artifact" in s.get("uses", "")]
    for pattern in ("lane-report-*", "coverage-*"):
        both = [s for s in downloads if s["with"]["pattern"] == pattern]
        assert {s["if"] for s in both} == {"needs.changes.outputs.reuse_run == ''",
                                           "needs.changes.outputs.reuse_run != ''"}
        for step in both:
            assert ("run-id" in step["with"]) == step["if"].endswith("!= ''"), pattern
    assure = next(s for s in job["steps"] if s.get("id") == "assure")
    assert assure["env"]["TIER"] == "${{ steps.tier.outputs.tier }}", "judged in full, never a narrower tier"
    jobs_check = _uses(job, "Every test job the tier requires")[0]
    assert "reused" in jobs_check["env"]["TIER"] and tiers.REUSED == "reused"


def test_a_run_of_static_reads_the_pins_on_the_new_tree():
    """No lane runs, so this is the proof at this head that each pin's test exists and each skip has its pin."""
    assert "reuse_run" not in str(_workflow()["static"].get("if"))
    assert any("tools/ci/skip_pins.py" in (s.get("run") or "") for s in _workflow()["static"]["steps"])
