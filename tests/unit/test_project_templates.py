"""A fresh repository and a copy start with the same project state and independent authority."""

from pathlib import Path

import conftest
from aewflow import sample_project

from aew.engine.base import POLICY_PINS
from aew.engine.store import deserialize_control
from aew.util import dump_yaml


def test_a_project_template_matches_fresh_setup_and_each_copy_acquires_its_own_lead(tmp_path, monkeypatch):
    monkeypatch.delenv("AEW_TEST_FRESH_WORLDS", raising=False)
    checks = {"schema": "aew/checks/v1", "checks": {}, "baseline_failures": []}
    first = sample_project(tmp_path / "first", checks=checks)
    second = sample_project(tmp_path / "second", checks=checks)
    seed = conftest._template_cache["sample", dump_yaml([None, checks, None])]
    assert conftest.git("worktree", "list", "--porcelain", cwd=seed).count("worktree ") == 1
    control = seed / ".aew/state/control.yaml"
    vacant = deserialize_control(control.read_bytes(), source=str(control))
    assert vacant["revision"] == 0 and vacant["lead"]["status"] == "vacant"
    assert vacant["tokens"] == vacant["invocations"] == vacant["work"] == {}

    monkeypatch.setenv("AEW_TEST_FRESH_WORLDS", "1")
    fresh = sample_project(tmp_path / "fresh", checks=checks)
    assert len({first.token, second.token, fresh.token}) == 3

    def contents(root: Path):
        control = root / ".aew/state/control.yaml"
        state = deserialize_control(control.read_bytes(), source=str(control))
        tree = conftest.git("rev-parse", "HEAD^{tree}", cwd=root)
        return tree, state["project_id"], state[POLICY_PINS], state["revision"], state["counters"]

    assert contents(first.root) == contents(second.root) == contents(fresh.root)
    (first.root / "calc/core.py").write_text("# only the first copy\n", encoding="utf-8")
    assert (second.root / "calc/core.py").read_bytes() == (fresh.root / "calc/core.py").read_bytes()
