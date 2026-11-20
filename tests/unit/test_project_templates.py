"""A fresh repository and a copy start with the same project state and independent authority."""

import json
from functools import partial
from pathlib import Path

import conftest
import pytest
from aewflow import _sample_repository

from aew.engine.store import deserialize_control
from aew.util import dump_yaml

CONTROL = ".aew/state/control.yaml"


def files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def without_init_metadata(contents: dict[str, bytes]) -> dict[str, bytes]:
    """Ignore the index stat cache and values generated anew at init, keeping the rest of each file."""
    contents = contents.copy()
    contents.pop(".git/index")
    state = deserialize_control(contents[CONTROL], source=CONTROL)
    transition = state["last_transition"]
    at, digest = transition["at"].encode(), transition["h"].encode()
    for rel in (CONTROL, ".aew/state/log/000000.yaml"):
        contents[rel] = contents[rel].replace(at, b"<init time>").replace(digest, b"<transition hash>")
    contents[CONTROL] = contents[CONTROL].rsplit(b"# aew-checksum ", 1)[0]
    steering, = [rel for rel in contents if rel.startswith(".aew/records/steering/")]
    data = contents.pop(steering)
    contents[".aew/records/steering/<init day>.jsonl"] = data.replace(json.loads(data)["at"].encode(), b"<init time>")
    wake = ".aew/local/wake"
    contents[wake] = contents[wake].split(b" ", 1)[0]
    registry = ".aew/local/maps/registry.json"
    if registry in contents:
        snapshot = json.loads(contents[registry])
        for rel in (registry, ".aew/local/maps/registry-log.jsonl"):
            data = contents[rel]
            if rel.endswith(".jsonl"):
                data = data.replace(json.loads(data)["at"].encode(), b"<init time>")
            for field in ("epoch", "selection_id"):
                data = data.replace(snapshot[field].encode(), field.encode())
            contents[rel] = data
    return contents


@pytest.mark.parametrize("kind", ["sample", "project"])
def test_a_project_template_matches_fresh_setup_and_each_copy_acquires_its_own_lead(tmp_path, monkeypatch, kind):
    monkeypatch.delenv("AEW_TEST_FRESH_WORLDS", raising=False)
    monkeypatch.setattr(conftest, "_template_cache", {})
    for name in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        monkeypatch.setenv(name, "2001-01-01T00:00:00+00:00")  # equal initial Git objects and reflogs
    variant = ("sample", dump_yaml([None, None, None])) if kind == "sample" else ("repo", "True")
    sample = partial(_sample_repository, guardrails=None, checks=None, gates=None)
    build = (partial(conftest.copy_test_repository, variant=variant, build=sample) if kind == "sample"
             else partial(conftest.fixture_repository, initialized=True))
    first = build(tmp_path / "first" / "repo")
    second = build(tmp_path / "second" / "repo")
    seed = conftest._template_cache[variant]
    assert conftest.git("worktree", "list", "--porcelain", cwd=seed).count("worktree ") == 1
    vacant = deserialize_control((seed / CONTROL).read_bytes(), source=CONTROL)
    assert vacant["revision"] == 0 and vacant["lead"]["status"] == "vacant"
    assert vacant["tokens"] == vacant["invocations"] == vacant["work"] == {}

    monkeypatch.setenv("AEW_TEST_FRESH_WORLDS", "1")
    fresh = build(tmp_path / "fresh" / "repo")
    first_files = files(first)
    assert first_files == files(second) == files(seed)
    for path in (seed, seed.parent):
        for spelling in {str(path), path.as_posix(), str(path).replace("\\", "\\\\")}:
            leaks = [rel for rel, data in first_files.items() if spelling.lower().encode() in data.lower()]
            assert not leaks, leaks
    assert without_init_metadata(first_files) == without_init_metadata(files(fresh))

    projects = [conftest.acquire_test_lead(conftest.Project(root)) for root in (first, second, fresh)]
    assert len({p.token for p in projects}) == 3
    (first / "README.md").write_text("# only the first copy\n", encoding="utf-8")
    assert (second / "README.md").read_bytes() == (fresh / "README.md").read_bytes()


def test_each_copy_of_a_released_world_acquires_at_its_own_revision(project, tmp_path):
    original_token = project.token
    project.lead("work", "create", "ticket", "--title", "Shared substrate", "--class", "1")
    project.lead("lead", "release")
    revision = project.rev()
    first = conftest.copy_released_world(project.root, tmp_path / "first")
    second = conftest.copy_released_world(project.root, tmp_path / "second")
    assert len({first.token, second.token, original_token}) == 3
    assert first.rev() == second.rev() == revision + 1
    assert project.rev() == revision
