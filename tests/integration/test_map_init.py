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


def test_init_in_a_repository_with_no_commit_exits_0_and_says_when_the_first_map_comes(tmp_path):
    """The never-fails proof at the command itself (E184 review, 2026-11-08): `aew init` before the first commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    out = Project(repo).ok("init", "--project-id", "calc")  # `ok` asserts exit 0
    assert (out["map"]["selected"], out["map"]["reason"]) == (False, "no_commit")
    assert store.read_registry(repo / ".aew") is None


def test_a_registry_that_selects_no_structural_map_takes_the_first_one(tmp_path):
    """`already_selected` means a structural map is selected (E184 review, 2026-11-08): a leftover registry holding
    only an architecture reference gets the first map at its own revision."""
    engine = _engine(tmp_path)
    leftover = store.select(engine.aew_root, "architecture", expect=store.NO_REGISTRY,
                            entry={"evidence_id": "E-0001"}, actor=service.INIT_ACTOR)
    result = service.first_map(engine)
    assert result["selected"] is True, result
    registry = store.read_registry(engine.aew_root)
    assert registry["selected"]["structural"]["sha256"] == result["root"]
    assert registry["selected"]["architecture"] == {"evidence_id": "E-0001"}
    assert registry["epoch"] == leftover["epoch"] and registry["map_revision"] == leftover["map_revision"] + 1


def test_committing_the_aew_state_leaves_inits_map_current(tmp_path):
    """The map's listing leaves `.aew/` out (ADR-0015, amended 2026-11-11 for register E184): the first commit of the
    project's state is not a change to the map, so init's map stays CURRENT at it."""
    from aew.maps import slices

    repo = make_git_repo(tmp_path / "repo", {"calc/core.py": "def add(a, b):\n    return a + b\n"})
    out = Project(repo).ok("init", "--project-id", "calc")
    git("add", "-f", ".aew", cwd=repo)
    git("commit", "-q", "-m", "the project's AEW state", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo)
    assert head != out["map"]["source_revision"]
    entry = slices.source_entry(repo / ".aew", repo, head)
    assert entry["sha256"] == out["map"]["root"] and entry["freshness"]["status"] == "CURRENT", entry
