"""A fresh repository and a copy start with the same project state and independent authority."""

import json
from pathlib import Path

import aewflow
import conftest
import pytest

from aew.engine.store import deserialize_control
from aew.policy import execution
from aew.util import load_yaml

CONTROL = ".aew/state/control.yaml"


def files(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_fixture_commits_start_no_automatic_git_maintenance(tmp_path, monkeypatch):
    monkeypatch.delenv("AEW_TEST_FRESH_WORLDS", raising=False)
    monkeypatch.setattr(conftest, "_template_cache", {})
    config = tmp_path / "gitconfig"
    config.write_text("[maintenance]\n\tauto = true\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    trace = tmp_path / "git-events.jsonl"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))

    repo = conftest.fixture_repository(tmp_path / "repo", initialized=False)
    conftest.git("commit", "--allow-empty", "-m", "later fixture setup", cwd=repo)
    events = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    assert sum(event.get("event") == "cmd_name" and event["name"] == "commit" for event in events) == 2
    children = [event["argv"] for event in events if event["event"] == "child_start"]
    assert not [argv for argv in children if "maintenance" in argv and "--auto" in argv]


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
    # Capture the exact copy before acquisition writes the new Lead's identity and transition.
    snapshots = []

    def acquire(project):
        snapshots.append(files(project.root))
        return conftest.acquire_test_lead(project)

    def build(parent):
        if kind == "sample":
            return aewflow.sample_project(parent)
        return acquire(conftest.Project(conftest.fixture_repository(parent / "repo", initialized=True)))

    monkeypatch.setattr(aewflow, "acquire_test_lead", acquire)
    first = build(tmp_path / "first")
    second = build(tmp_path / "second")
    seed, = conftest._template_cache.values()
    assert conftest.git("worktree", "list", "--porcelain", cwd=seed).count("worktree ") == 1
    vacant = deserialize_control((seed / CONTROL).read_bytes(), source=CONTROL)
    assert vacant["revision"] == 0 and vacant["lead"]["status"] == "vacant"
    assert vacant["tokens"] == vacant["invocations"] == vacant["work"] == {}

    monkeypatch.setenv("AEW_TEST_FRESH_WORLDS", "1")
    fresh = build(tmp_path / "fresh")
    first_files, second_files, fresh_files = snapshots
    assert first_files == second_files == files(seed)
    for path in (seed, seed.parent):
        for spelling in {str(path), path.as_posix(), str(path).replace("\\", "\\\\")}:
            leaks = [rel for rel, data in first_files.items() if spelling.lower().encode() in data.lower()]
            assert not leaks, leaks
    assert without_init_metadata(first_files) == without_init_metadata(fresh_files)

    assert len({first.token, second.token, fresh.token}) == 3
    (first.root / "README.md").write_text("# only the first copy\n", encoding="utf-8")
    assert (second.root / "README.md").read_bytes() == (fresh.root / "README.md").read_bytes()


@pytest.mark.parametrize("first_off", [False, True], ids=["default-first", "off-first"])
def test_sample_project_keeps_default_and_maps_off_templates_separate(tmp_path, monkeypatch, first_off):
    monkeypatch.delenv("AEW_TEST_FRESH_WORLDS", raising=False)
    monkeypatch.setattr(conftest, "_template_cache", {})
    for i, off in enumerate((first_off, not first_off, first_off, not first_off)):
        parent = tmp_path / str(i)
        project = aewflow.sample_project(parent, maps="off") if off else aewflow.sample_project(parent)
        policy = load_yaml((project.root / ".aew/policy/execution.yaml").read_text(encoding="utf-8"))
        assert execution.pack_slices(policy) == ("off" if off else execution.NEW_PROJECT_PACK_SLICES)
    assert len(conftest._template_cache) == 2


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
