"""`aew init` makes the first structural map (register E184; ADR-0015 D4 as amended 2026-11-07).

Init generates the authoritative branch head's map and selects it, as the operator's own action, so a project has a
map before the first merge. A map is derived navigation data and grants nothing (D1): whatever stops it is one
labelled line in init's report, never a failed init."""

from __future__ import annotations

import json

from conftest import Project, git, make_git_repo

from aew.maps import service, store


def test_init_selects_the_map_of_the_branch_head_as_the_operator(tmp_path):
    repo = make_git_repo(tmp_path / "repo", {"calc/core.py": "def add(a, b):\n    return a + b\n"})
    out = Project(repo).ok("init", "--project-id", "calc")
    head = git("rev-parse", "HEAD", cwd=repo)
    assert out["map"]["selected"] is True and out["map"]["source_revision"] == head
    shown = Project(repo).ok("map", "show", "--json")
    assert shown["map_revision"] == out["map"]["map_revision"] != store.NO_REGISTRY
    assert shown["root"] == out["map"]["root"]
    [line] = (repo / ".aew" / store.LOG_REL).read_text(encoding="utf-8").splitlines()
    # attributable: the operator's init, not a Lead (ADR-0015's amendment of 2026-11-07)
    assert json.loads(line)["actor"] == {"kind": "operator", "id": "aew init", "generation": None}


def _engine(tmp_path):
    from aew.engine.api import Engine

    repo = make_git_repo(tmp_path / "repo")
    return Engine.initialize(repo, project_id="calc")


def test_a_map_that_cannot_be_built_never_fails_init(tmp_path, monkeypatch):
    """T5-INV-01: a map never refuses or breaks anything. A generator failure is a labelled line, and nothing is
    selected."""
    engine = _engine(tmp_path)

    def broken(repo, commit):
        raise OSError("the commit's objects cannot be read")

    monkeypatch.setattr(service, "build", broken)
    result = service.first_map(engine)
    assert result["selected"] is False and result["reason"] == "generation_failed"
    assert "OSError" in result["detail"] and "aew map generate --select --expect-map-rev none:0" in result["detail"]
    assert store.read_registry(engine.aew_root) is None


def test_init_without_a_commit_says_when_the_first_map_comes(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    monkeypatch.setattr(type(engine), "authoritative_commit", lambda self: None)
    result = service.first_map(engine)
    assert (result["selected"], result["reason"]) == (False, "no_commit")
    assert store.read_registry(engine.aew_root) is None


def test_init_never_replaces_a_selected_map(tmp_path):
    """A registry that exists is left as it is: init makes the first map only, never a second selection."""
    engine = _engine(tmp_path)
    first = service.first_map(engine)
    assert first["selected"] is True
    again = service.first_map(engine)
    assert (again["selected"], again["reason"]) == (False, "already_selected")
    assert store.revision_of(store.read_registry(engine.aew_root)) == first["map_revision"]
