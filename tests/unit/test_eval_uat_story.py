"""The UAT story workload's starting repository (eval/experiments/uat-story/README.md, "The starting tree").

Both arms of the operator's comparison start from the same tree only if two builds of the same inputs are the same
commits; the configured check (the whole upstream suite) passes at the start only without the lane's distractor and
with the in-tree metadata committed; and the contributor branch holds exactly the seeded change. The upstream base is
replaced by a small stand-in here, so no test fetches anything.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = ROOT / "eval" / "experiments" / "uat-story"
BASE = {"README.md": b"upstream\n", "pyproject.toml": b"[project]\nname = 'Markdown'\n",
        "markdown/__init__.py": b"", ".gitignore": b"*.egg-info/\n__pycache__/\n"}


@pytest.fixture
def materialize(monkeypatch):
    spec = importlib.util.spec_from_file_location("uat_materialize", WORKLOAD / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "base_files", lambda up: (dict(BASE), "a stand-in base"))
    return module


def files_at(repo: Path, ref: str) -> set[str]:
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=repo, capture_output=True, text=True,
                         check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return set(out.split())


def test_two_builds_of_the_uat_starting_tree_are_the_same_commits(materialize, tmp_path):
    first = materialize.materialize(tmp_path / "aew")
    second = materialize.materialize(tmp_path / "raw")
    assert (first["main"], first[materialize.BRANCH]) == (second["main"], second[materialize.BRANCH])


def test_the_uat_starting_tree_drops_the_distractor_and_commits_the_metadata(materialize, tmp_path):
    repo = Path(materialize.materialize(tmp_path / "repo")["repo"])
    main = files_at(repo, "main")
    assert not materialize.LEFT_OUT & main
    assert {"Markdown.egg-info/entry_points.txt", "markdown/extensions/linkpolicy/rules.py"} <= main
    assert set(BASE) <= main


def test_the_contributor_branch_holds_exactly_the_seeded_change(materialize, tmp_path):
    repo = Path(materialize.materialize(tmp_path / "repo")["repo"])
    changed = subprocess.run(["git", "diff", "--name-only", "main", materialize.BRANCH], cwd=repo, capture_output=True,
                             text=True, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    seeded = {p.relative_to(materialize.BRANCH_FILES).as_posix()
              for p in materialize.BRANCH_FILES.rglob("*") if p.is_file()}
    assert set(changed.split()) == seeded


def test_the_uat_starting_tree_is_built_only_into_a_new_directory(materialize, tmp_path):
    (tmp_path / "taken").mkdir()
    with pytest.raises(SystemExit, match="exists"):
        materialize.materialize(tmp_path / "taken")


def test_every_uat_task_names_an_oracle_and_only_earlier_items_as_dependencies():
    workload = yaml.safe_load((WORKLOAD / "workload.yaml").read_text(encoding="utf-8"))
    ids = [t["id"] for t in workload["tasks"]]
    assert len(set(ids)) == len(ids) and all(t["oracle"] for t in workload["tasks"])
    for i, task in enumerate(workload["tasks"]):
        assert set(task["depends_on"]) <= set(ids[:i]), task["id"]
        assert set(task["shares"]) <= set(ids) - {task["id"]}, task["id"]
