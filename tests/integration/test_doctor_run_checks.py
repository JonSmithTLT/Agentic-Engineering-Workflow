"""`aew doctor --run-checks` runs each configured check once, contained as a worker's check, on a disposable copy of the
authoritative snapshot, and names each path a check changes with its fix; without the flag doctor says the checks were
not run and how to run them (register E153; the designer's ruling (b), relayed 2026-11-07). Never evidence, never a
refusal."""

from __future__ import annotations

import pytest
from aewflow import sample_project

from aew.harness import check_changes, runlog
from aew.util import dump_yaml, load_yaml

WRITES = "open('check-output.txt', 'w').write('x')"


def project_with(tmp_path, code: str):
    checks = {"schema": "aew/checks/v1", "baseline_failures": [],
              "checks": {"probe": {"configured": True, "command": ["{python}", "-c", code], "cwd": ".",
                                   "timeout_s": 120}}}
    project = sample_project(tmp_path, checks=checks)
    project.pin_policy()
    return project


def fingerprint(project, **rules) -> None:
    """The manifest's fingerprint rules, as the operator adopts them."""
    path = project.root / ".aew" / "project.yaml"
    manifest = load_yaml(path.read_text(encoding="utf-8"))
    manifest["fingerprint"] = rules
    path.write_text(dump_yaml(manifest), encoding="utf-8", newline="\n")
    project.adopt_policy("the snapshot's rules")


def row(project, *args: str):
    res = project.aew("doctor", "--json", *args)
    found = {c["check"]: c for c in res.json["checks"]}.get(check_changes.CHECK)
    return res.returncode, found


def leftovers(project) -> list[str]:
    runs = runlog.run_dir(project.root / ".aew", "x").parent
    names = sorted(d.name for d in runs.iterdir()) if runs.is_dir() else []
    copies = [p.name for p in project.root.parent.glob("**/.doctor-check-*")]
    return names + copies


def test_without_the_flag_doctor_says_the_check_was_not_run_and_how_to_run_it(tmp_path):
    project = project_with(tmp_path, WRITES)
    _, found = row(project)
    assert found is not None and found["status"] == "WARN", found
    assert found["detail"].startswith("not checked: needs the project's check to run once (probe)"), found
    assert "Run `aew doctor --run-checks`" in found["detail"], found
    assert not (project.root / "check-output.txt").exists()  # nothing ran
    assert leftovers(project) == [], leftovers(project)


def test_a_check_that_writes_into_its_snapshot_is_a_fail_naming_the_path_and_the_fix(tmp_path):
    project = project_with(tmp_path, WRITES)
    code, found = row(project, "--run-checks")
    assert code == 1 and found is not None and found["status"] == "FAIL", found
    assert "check probe (exited 0) changes the snapshot it runs on: it writes check-output.txt" in found["detail"]
    assert "list it in .gitignore (or .git/info/exclude)" in found["detail"], found
    assert "never evidence" in found["detail"], found
    # On a copy, removed after: the project is untouched, and nothing is left behind.
    assert not (project.root / "check-output.txt").exists()
    assert leftovers(project) == [], leftovers(project)
    assert not list((project.root / ".aew").glob("evidence/**/*.md"))


def test_a_path_the_project_excludes_is_not_a_change(tmp_path):
    project = project_with(tmp_path, WRITES)
    exclude = project.root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("check-output.txt\n", encoding="utf-8")  # a worker's workspace shares the project's exclusions
    _, found = row(project, "--run-checks")
    assert found is not None and found["status"] == "PASS", found
    assert "check probe (exited 0) changes nothing in the snapshot" in found["detail"], found


@pytest.mark.parametrize("code, ran", [("import sys; sys.exit(3)", "exited 3")])
def test_a_check_that_leaves_the_snapshot_alone_passes_whatever_its_exit(tmp_path, code, ran):
    project = project_with(tmp_path, code)
    _, found = row(project, "--run-checks")
    assert found is not None and found["status"] == "PASS", found
    assert f"check probe ({ran}) changes nothing" in found["detail"], found


def test_a_tracked_file_the_check_edits_is_named(tmp_path):
    project = project_with(tmp_path, "open('README.md', 'a').write('more')")  # tracked (aewflow.SAMPLE_FILES)
    _, found = row(project, "--run-checks")
    assert found is not None and found["status"] == "FAIL" and "it writes README.md" in found["detail"], found


def test_a_path_the_snapshot_excludes_is_not_a_change(tmp_path):
    """Review of #367, F2: the verdict is the snapshot's, as verification compares it, not git's: a path the manifest's
    fingerprint.exclude leaves out changes nothing."""
    project = project_with(tmp_path, "import os; os.makedirs('build-out', exist_ok=True); "
                                     "open('build-out/x.txt', 'w').write('x')")
    fingerprint(project, exclude=["build-out"])
    _, found = row(project, "--run-checks")
    assert found is not None and found["status"] == "PASS", found


def test_an_ignored_path_the_snapshot_puts_back_is_named_with_that_rule_as_its_fix(tmp_path):
    """Review of #367, F2: a path the manifest's fingerprint.include_ignored puts back into the snapshot changes it
    though git ignores it; the row names it, and its fix is that rule, never .gitignore, which it already is in."""
    project = project_with(tmp_path, "open('build.log', 'w').write('x')")
    (project.root / ".git" / "info").mkdir(parents=True, exist_ok=True)
    (project.root / ".git" / "info" / "exclude").write_text("build.log\n", encoding="utf-8")
    fingerprint(project, include_ignored=["build.log"])
    _, found = row(project, "--run-checks")
    assert found is not None and found["status"] == "FAIL", found
    assert "it writes build.log" in found["detail"], found
    assert "take build.log off the project manifest's fingerprint.include_ignored" in found["detail"], found
    assert ".gitignore" not in found["detail"], found
