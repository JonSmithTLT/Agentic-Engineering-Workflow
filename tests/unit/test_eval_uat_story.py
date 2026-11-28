"""The UAT story workload's starting repository (eval/experiments/uat-story/README.md, "The starting tree").

Both arms of the operator's comparison start from the same tree only if two builds of the same inputs are the same
commits; the configured check (the whole upstream suite) passes at the start only without the lane's distractor and
with the in-tree metadata committed; the contributor branch holds exactly the seeded change; and a base that is not
the pinned upstream is refused. The upstream base is replaced by a small stand-in here, so no test fetches anything.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = ROOT / "eval" / "experiments" / "uat-story"
BASE = {"README.md": b"upstream\n", "pyproject.toml": b"[project]\nname = 'Markdown'\n",
        "markdown/__init__.py": b"", ".gitignore": b"*.egg-info/\n__pycache__/\n"}


def load():
    spec = importlib.util.spec_from_file_location("uat_materialize", WORKLOAD / "materialize.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def materialize(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "base_files", lambda up: (dict(BASE), "a stand-in base"))
    return module


def git_out(module, repo: Path, *args: str) -> str:
    """Git on the built repository, with the caller's GIT_* variables scrubbed as the script scrubs its own."""
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True,
                          env=module.git_env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout


def files_at(module, repo: Path, ref: str) -> set[str]:
    return set(git_out(module, repo, "ls-tree", "-r", "--name-only", ref).split())


def test_two_builds_of_the_uat_starting_tree_are_the_same_commits(materialize, tmp_path):
    first = materialize.materialize(tmp_path / "aew")
    second = materialize.materialize(tmp_path / "raw")
    assert (first["main"], first[materialize.BRANCH]) == (second["main"], second[materialize.BRANCH])


def test_the_uat_starting_tree_drops_the_distractor_and_commits_the_metadata(materialize, tmp_path):
    repo = Path(materialize.materialize(tmp_path / "repo")["repo"])
    main = files_at(materialize, repo, "main")
    assert not materialize.LEFT_OUT & main
    assert {"Markdown.egg-info/entry_points.txt", "markdown/extensions/linkpolicy/rules.py"} <= main
    assert set(BASE) <= main
    assert set(materialize.tree_files(materialize.OVERLAY)) <= main


def test_the_contributor_branch_holds_exactly_the_seeded_change(materialize, tmp_path):
    repo = Path(materialize.materialize(tmp_path / "repo")["repo"])
    changed = git_out(materialize, repo, "diff", "--name-only", "main", materialize.BRANCH)
    seeded = {p.relative_to(materialize.BRANCH_FILES).as_posix()
              for p in materialize.BRANCH_FILES.rglob("*") if p.is_file()}
    assert set(changed.split()) == seeded


def test_the_uat_starting_tree_is_built_only_into_a_new_directory(materialize, tmp_path):
    (tmp_path / "taken").mkdir()
    with pytest.raises(SystemExit, match="exists"):
        materialize.materialize(tmp_path / "taken")


def test_a_fetched_base_that_is_not_the_pinned_upstream_is_refused(monkeypatch, tmp_path):
    module = load()
    up = yaml.safe_load(module.UPSTREAM.read_text(encoding="utf-8"))
    base, receipt = tmp_path / "base", tmp_path / "base.receipt.json"
    (base / "markdown").mkdir(parents=True)
    (base / "markdown" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(module, "LBQ_BASE", base)
    monkeypatch.setattr(module, "LBQ_RECEIPT", receipt)
    receipt.write_text(json.dumps({"commit": "0" * 40, "tree": up["tree"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match="refused: the lane's fetched base is 0{40}, not the pinned"):
        module.base_files(up)
    receipt.write_text(json.dumps({"commit": up["commit"], "tree": up["tree"]}), encoding="utf-8")
    with pytest.raises(SystemExit, match=f"refused: 1 upstream files, the pin says {up['file_count']}"):
        module.base_files(up)


def test_every_uat_task_names_an_oracle_and_only_earlier_items_as_dependencies():
    workload = yaml.safe_load((WORKLOAD / "workload.yaml").read_text(encoding="utf-8"))
    ids = [t["id"] for t in workload["tasks"]]
    assert len(set(ids)) == len(ids) and all(t["oracle"] for t in workload["tasks"])
    for i, task in enumerate(workload["tasks"]):
        assert set(task["depends_on"]) <= set(ids[:i]), task["id"]
        assert set(task["shares"]) <= set(ids) - {task["id"]}, task["id"]
