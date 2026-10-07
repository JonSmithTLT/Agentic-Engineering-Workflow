"""The structural map over real git and the real CLI (register F22.1, T5-A; design v0.5 §2 to §3; plan §2, §4, §7).

Git-object binding (the checkout, the index, untracked files and replace refs never reach a record), determinism
across clones, the differential oracle over real commits, freshness, the edge cases built with git plumbing, the
partial-clone refusal, and the ``aew map`` commands: authority, the map registry's own revision domain, and that no
map command changes anything outside ``.aew/local/maps/`` (T5-INV-11)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_investigation, dispatch, sample_project
from map_trees import LFS, PACKAGE_JSON, PYPROJECT

from aew.errors import MapCurrentnessUnproven
from aew.maps import freshness as F
from aew.maps import gitobjects, rules, service, store, structural
from aew.maps.canonical import seal
from aew.workspace import git as aew_git

IS_WINDOWS = sys.platform == "win32"
BIG = b'{"name": "big", "x": "' + b"a" * (structural.BLOB_LIMIT + 10) + b'"}'
FILES: dict[str, bytes] = {
    "README.md": b"# demo\n",
    "pyproject.toml": PYPROJECT,
    ".gitattributes": b"gen/** linguist-generated\n",
    "ui/package.json": PACKAGE_JSON,
    "ui/.gitattributes": b"dist/** linguist-generated\n",
    "ui/index.js": b"module.exports = 1;\n",
    "deep/Cargo.toml": b'[package]\nname = "x"\n[[bin]]\nname = "tool"\npath = "src/tool.rs"\n',
    "big/package.json": BIG,
    "src/demo/__main__.py": b"print('x')\n",
    "src/demo/cli.py": b"def main(): ...\n",
    "tests/test_cli.py": b"def test(): ...\n",
    "docs/guide.md": b"guide\n",
    "deep/a/b/c/d/e.go": b"package e\n",
}


def g(*args: str, cwd: Path, input: bytes | None = None) -> str:
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}  # no console window
    proc = subprocess.run(["git", *args], cwd=cwd, input=input, capture_output=True, check=True, timeout=120,
                          stdin=subprocess.DEVNULL if input is None else None,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}, **kw)
    return proc.stdout.decode("utf-8", "surrogateescape").strip()


def write(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def make_repo(path: Path, files: dict[str, bytes] = FILES) -> Path:
    path.mkdir(parents=True)
    g("init", "-q", "-b", "main", cwd=path)
    for key, value in (("user.name", "AEW Test"), ("user.email", "aew-test@invalid"), ("core.autocrlf", "false")):
        g("config", key, value, cwd=path)
    write(path, files)
    g("add", "-A", cwd=path)
    g("commit", "-q", "-m", "initial", cwd=path)
    return path


def commit(repo: Path, message: str = "change") -> str:
    g("add", "-A", cwd=repo)
    g("commit", "-q", "-m", message, cwd=repo)
    return g("rev-parse", "HEAD", cwd=repo)


def sealed(repo: Path, rev: str) -> dict[str, Any]:
    record = service.build(repo, rev)
    return {**record, "artifact_sha256": seal(record)[0]}


def without_source(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in {"source_revision", "source_tree", "artifact_sha256"}}


def fresh(repo: Path, record: dict[str, Any], rev: str, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return F.freshness(repo, record, rev, identity or service.identity())


# ------------------------------------------------------------------------------------------- binding and determinism


def test_a_commit_is_read_from_its_git_objects_never_the_checkout_index_untracked_files_or_replace_refs(tmp_path):
    repo = make_repo(tmp_path / "repo")
    head = g("rev-parse", "HEAD", cwd=repo)
    clone = tmp_path / "clone"
    g("clone", "-q", repo.as_uri(), str(clone), cwd=tmp_path)
    reference = seal(service.build(clone, head))
    # another branch checked out, with staged and unstaged edits to the descriptors and untracked descriptors
    g("checkout", "-q", "-b", "other", cwd=repo)
    write(repo, {"pyproject.toml": b'[project]\nname = "other"\n'})
    commit(repo)
    write(repo, {"ui/package.json": b'{"main": "staged.js"}'})
    g("add", "ui/package.json", cwd=repo)
    write(repo, {"pyproject.toml": b"[project]\nname = 'unstaged'\n", "new/package.json": b'{"main": "u.js"}',
                 "Cargo.toml": b"[package]\n", ".gitattributes": b"* linguist-vendored\n"})
    blob = g("rev-parse", f"{head}:pyproject.toml", cwd=repo)
    other = g("hash-object", "-w", "--stdin", cwd=repo, input=b'[project]\nname = "replaced"\n')
    g("replace", blob, other, cwd=repo)
    assert "replaced" in g("show", f"{head}:pyproject.toml", cwd=repo)  # the replace ref is live for plain git
    assert seal(service.build(repo, head)) == reference
    assert seal(service.build(repo, head)) == reference  # and again: the same bytes every run


def test_a_replace_ref_for_a_descriptor_never_changes_the_record(tmp_path):
    repo = make_repo(tmp_path / "repo")
    before = seal(service.build(repo, "HEAD"))
    blob = g("rev-parse", "HEAD:ui/package.json", cwd=repo)
    other = g("hash-object", "-w", "--stdin", cwd=repo, input=b'{"main": "evil.js"}')
    g("replace", blob, other, cwd=repo)
    assert "evil.js" in g("cat-file", "-p", "HEAD:ui/package.json", cwd=repo)
    assert seal(service.build(repo, "HEAD")) == before


def test_the_record_is_the_one_the_in_memory_generator_gives_for_the_same_tree(tmp_path):
    """The unit tests' goldens hold for real git too: the listing and blobs git serves are what the generator sees."""
    from map_trees import tree_of

    repo = make_repo(tmp_path / "repo")
    real = service.build(repo, "HEAD")
    memory = structural.generate(tree_of(FILES), rules.load())
    assert without_source(real) == without_source(memory)


def finishes(work, limit: float = 120.0):
    """Run ``work`` in a thread and fail fast if it does not finish: a hang is a failure here, never a CI timeout."""
    import threading

    out: dict[str, Any] = {}

    def run() -> None:
        try:
            out["value"] = work()
        except BaseException as exc:  # re-raised below, in the test's own thread
            out["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(limit)
    assert not thread.is_alive(), f"did not finish within {limit}s"
    if "error" in out:
        raise out["error"]
    return out.get("value")


def test_the_batch_reader_serves_many_large_blobs_without_a_pipe_deadlock(tmp_path):
    """One cat-file --batch process for every blob: each reply is drained before the next request, so large blobs
    (well over a pipe's buffer) never block either side."""
    files = {f"d{i:02d}/.gitattributes": bytes([65 + i % 26]) * (1024 * 1024 + i) for i in range(40)}
    repo = make_repo(tmp_path / "repo", files)
    oids = {path: g("rev-parse", f"HEAD:{path}", cwd=repo) for path in files}

    def read_all() -> dict[str, bytes]:
        with aew_git.CatFileBatch(repo) as batch:
            return {path: batch.read(oid) or b"" for path, oid in oids.items()}

    assert finishes(read_all) == files
    record = finishes(lambda: service.build(repo, "HEAD"))  # the generator's own path: every one over the blob cap
    assert record["limits"]["metadata_blob_bytes"]["skipped"] == 40


def test_a_batch_reader_that_stops_answering_fails_fast_instead_of_hanging(tmp_path):
    """The watchdog: a batch process that never replies is stopped after the read timeout and the read fails."""
    import time

    from aew.errors import GitError

    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}
    batch = aew_git.CatFileBatch(tmp_path, timeout=1.0)
    batch._proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **kw)
    started = time.monotonic()
    try:
        with pytest.raises(GitError):
            finishes(lambda: batch.read("0" * 40), limit=60)
    finally:
        batch.__exit__(None, None, None)  # not entered: the stand-in process is the one under test
    assert time.monotonic() - started < 30


# ------------------------------------------------------------------------------------------- the differential oracle


def test_mutating_only_an_unrecorded_blob_never_changes_the_record_and_a_recorded_one_always_shows(tmp_path):
    """PMP-27: for every blob not in the recorded input set, commit a mutation of only that blob (also one that moves
    it across the size cap) and regenerate: the record minus its source binding is byte-identical. The converse: a
    mutated recorded input, read or unread, changes the record and makes the old one STALE (metadata)."""
    repo = make_repo(tmp_path / "repo")
    base_commit = g("rev-parse", "HEAD", cwd=repo)
    base = sealed(repo, base_commit)
    recorded = {i["path"] for i in base["inputs"]["metadata"]}
    assert recorded == {".gitattributes", "big/package.json", "deep/Cargo.toml", "pyproject.toml",
                        "ui/.gitattributes", "ui/package.json"}
    assert {i["path"]: i["read"] for i in base["inputs"]["metadata"]}["big/package.json"] is False
    for path, data in FILES.items():
        mutations = [data + b"\n// changed\n", b"#" * (structural.BLOB_LIMIT + 1)] if path not in recorded else \
            [b"{}\n" if path.endswith(".json") else data + b"\n# changed\n"]
        for mutated in mutations:
            write(repo, {path: mutated})
            changed = commit(repo, f"mutate {path}")
            record = sealed(repo, changed)
            if path in recorded:
                assert record["inputs"] != base["inputs"], path
                status = fresh(repo, base, changed)
                assert status["status"] == "STALE" and status["reasons"] == ["metadata"], (path, status)
                assert status["metadata_paths"] == [path]
            else:
                assert without_source(record) == without_source(base), path
                assert fresh(repo, base, changed)["status"] == "CURRENT", path
            g("reset", "-q", "--hard", base_commit, cwd=repo)


# ------------------------------------------------------------------------------------------- freshness


def test_freshness_follows_the_path_listing_the_recorded_inputs_and_the_generator(tmp_path):
    repo = make_repo(tmp_path / "repo")
    base_commit = g("rev-parse", "HEAD", cwd=repo)
    base = sealed(repo, base_commit)
    assert fresh(repo, base, base_commit)["status"] == "CURRENT"

    def after(change) -> dict[str, Any]:
        change()
        result = fresh(repo, base, commit(repo))
        g("reset", "-q", "--hard", base_commit, cwd=repo)
        return result

    assert after(lambda: write(repo, {"src/demo/new.py": b""}))["reasons"] == ["path_listing"]
    assert after(lambda: (repo / "docs/guide.md").unlink())["reasons"] == ["path_listing"]
    assert after(lambda: g("mv", "docs/guide.md", "docs/moved.md", cwd=repo))["reasons"] == ["path_listing"]
    assert after(lambda: write(repo, {"src/demo/cli.py": b"changed\n"}))["status"] == "CURRENT"
    edited = after(lambda: write(repo, {"pyproject.toml": PYPROJECT + b"\n"}))
    assert edited["reasons"] == ["metadata"] and edited["metadata_paths"] == ["pyproject.toml"]
    ruleset = {**service.identity(), "ruleset_sha256": "0" * 64}
    assert fresh(repo, base, base_commit, ruleset)["reasons"] == ["generator"]
    unknown = fresh(repo, base, "no-such-commit")
    assert unknown["status"] == "UNKNOWN" and unknown["code"] == "MAP_CURRENTNESS_UNPROVEN"


def test_a_submodule_bump_is_a_path_listing_change_and_a_changed_directories_row(tmp_path):
    repo = make_repo(tmp_path / "repo")
    g("update-index", "--add", "--cacheinfo", f"160000,{'a' * 40},vendor/lib", cwd=repo)
    g("commit", "-q", "-m", "submodule", cwd=repo)
    first = g("rev-parse", "HEAD", cwd=repo)
    g("update-index", "--cacheinfo", f"160000,{'b' * 40},vendor/lib", cwd=repo)
    g("commit", "-q", "-m", "bump", cwd=repo)
    a, b = sealed(repo, first), sealed(repo, "HEAD")
    assert fresh(repo, a, "HEAD")["reasons"] == ["path_listing"]
    assert a["sections"]["directories"]["submodules"] == [{"path": "vendor/lib", "object": "a" * 40}]
    assert b["sections"]["directories"]["submodules"] == [{"path": "vendor/lib", "object": "b" * 40}]


def test_two_records_of_one_tree_under_different_rulesets_are_never_confused(tmp_path):
    repo = make_repo(tmp_path / "repo")
    raw = (Path(rules.__file__).parent / "rules.yaml").read_bytes()
    other = rules.parse(raw + b"\n# another ruleset\n")
    with gitobjects.open_tree(repo, "HEAD") as tree:
        a = structural.generate(tree, rules.load())
    with gitobjects.open_tree(repo, "HEAD") as tree:
        b = structural.generate(tree, other)
    a, b = ({**r, "artifact_sha256": seal(r)[0]} for r in (a, b))
    ident_a, ident_b = structural.generator_identity(rules.load()), structural.generator_identity(other)
    for _ in range(2):  # the second round is answered from the in-memory cache
        assert fresh(repo, a, "HEAD", ident_a)["status"] == "CURRENT"
        assert fresh(repo, b, "HEAD", ident_a)["reasons"] == ["generator"]
        assert fresh(repo, a, "HEAD", ident_b)["reasons"] == ["generator"]
        assert fresh(repo, b, "HEAD", ident_b)["status"] == "CURRENT"


# ------------------------------------------------------------------------------------------- edge cases (plumbing)


def mktree(repo: Path, entries: list[tuple[str, str, str, bytes]]) -> str:
    body = b"".join(f"{mode} {kind} {oid}\t".encode() + name + b"\0" for mode, kind, oid, name in entries)
    return g("mktree", "-z", cwd=repo, input=body)


def blob(repo: Path, data: bytes) -> str:
    return g("hash-object", "-w", "--stdin", cwd=repo, input=data)


def test_symlinks_submodules_lfs_pointers_and_hostile_names_are_bounded_and_never_followed(tmp_path):
    repo = make_repo(tmp_path / "repo", {"README.md": b"x\n"})
    inner = mktree(repo, [("100644", "blob", blob(repo, b""), b"x.py")])
    tree = mktree(repo, [
        ("120000", "blob", blob(repo, b"../../../../outside/pyproject.toml"), b"pyproject.toml"),
        ("100644", "blob", blob(repo, LFS), b"package.json"),
        ("160000", "commit", "c" * 40, b"sub"),
        ("040000", "tree", inner, b"d\xff"),
        ("040000", "tree", inner, b"new\nline"),
        ("040000", "tree", inner, b"esc\x1b[31m"),
    ])
    head = g("commit-tree", tree, "-m", "edges", cwd=repo)
    record = service.build(repo, head)
    assert [i["path"] for i in record["inputs"]["metadata"]] == ["package.json"]  # the symlink is never read
    s = record["sections"]
    assert s["limits_and_omissions"]["unsupported"] == [{"path": "pyproject.toml", "reason": "symlink"}]
    assert s["limits_and_omissions"]["lfs_pointers"] == ["package.json"]
    assert s["limits_and_omissions"]["non_utf8_names"] == 1 and s["limits_and_omissions"]["symlinks"] == 1
    assert s["directories"]["submodules"] == [{"path": "sub", "object": "c" * 40}]
    rows = {r["path"] for r in s["directories"]["rows"]}
    assert {"d\\xff", "new\\x0aline", "esc\\x1b[31m"} <= rows
    text = json.dumps(record, ensure_ascii=False)
    assert "\x1b" not in text and "\n" not in text and "outside" not in text
    assert seal(record) == seal(service.build(repo, head))


def test_a_blobless_clone_missing_a_descriptor_is_refused_and_never_fetches(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "repo")
    g("config", "uploadpack.allowFilter", "true", cwd=repo)
    clone = tmp_path / "blobless"
    g("clone", "-q", "--bare", "--filter=blob:none", repo.as_uri(), str(clone), cwd=tmp_path)
    before = g("count-objects", "-v", cwd=clone)
    with pytest.raises(MapCurrentnessUnproven) as exc:
        service.build(clone, "HEAD")
    assert exc.value.details["reason"] == "missing_object"  # every missing input named at once (review F3)
    assert exc.value.details["paths"] == [".gitattributes", "big/package.json", "deep/Cargo.toml", "pyproject.toml",
                                          "ui/.gitattributes", "ui/package.json"]
    assert g("count-objects", "-v", cwd=clone) == before  # nothing was fetched lazily
    monkeypatch.setattr(aew_git, "version", lambda _cwd: (2, 43, 0))  # a git that cannot be told not to fetch
    with pytest.raises(MapCurrentnessUnproven) as exc:
        service.build(clone, "HEAD")
    assert exc.value.details["reason"] == "partial_clone"


def test_an_old_git_partial_clone_is_refused_before_any_object_is_resolved_or_read(tmp_path, monkeypatch):
    """PR #126, operator finding 2: on git older than 2.44 a partial clone may fetch a missing object lazily whatever
    AEW asks, so both generation and freshness refuse before their first object read (only configuration is read)."""
    repo = make_repo(tmp_path / "repo")
    record = sealed(repo, "HEAD")  # from the full repository
    g("config", "uploadpack.allowFilter", "true", cwd=repo)
    clone = tmp_path / "blobless"
    g("clone", "-q", "--bare", "--filter=blob:none", repo.as_uri(), str(clone), cwd=tmp_path)
    monkeypatch.setattr(aew_git, "version", lambda _cwd: (2, 43, 0))
    calls: list[str] = []
    real = aew_git.object_git

    def counted(*args: str, **kw: Any):
        calls.append(args[0])
        return real(*args, **kw)

    monkeypatch.setattr(aew_git, "object_git", counted)
    with pytest.raises(MapCurrentnessUnproven) as exc:
        service.build(clone, "HEAD")
    assert exc.value.details["reason"] == "partial_clone"
    assert calls == ["config"], calls  # no rev-parse, ls-tree or cat-file came first
    calls.clear()
    F.clear_cache()
    result = fresh(clone, record, "HEAD")
    assert result["status"] == "UNKNOWN" and result["reason"] == "partial_clone"
    assert result["code"] == "MAP_CURRENTNESS_UNPROVEN" and calls == ["config"], calls


def _handoff(engine: Any, token: str) -> None:
    """Hand the Lead seat to a new session: the credential the command started with is superseded."""
    offer = engine.lead_handoff_offer(token=token, expect_rev=engine.store.read()["revision"])["offer"]
    engine.lead_handoff_accept(offer=offer, expect_rev=engine.store.read()["revision"])


@pytest.mark.parametrize("when", ["during_generation", "after_the_artifact_is_written"])
def test_a_lead_superseded_while_a_map_is_generated_publishes_and_selects_nothing(project, monkeypatch, when):
    """PR #126, operator finding 1 (ADR-0015 D4): authority is checked where the command writes. A handoff committed
    during generation refuses the artifact and the selection; one committed after the artifact is written refuses the
    selection, inside the registry's lock."""
    from aew.engine.api import Engine
    from aew.errors import StaleAuthority

    engine = Engine.discover(project.root)
    if when == "during_generation":
        real_build = service.build

        def build_then_handoff(repo: Path, rev: str) -> dict[str, Any]:
            record = real_build(repo, rev)
            _handoff(engine, project.token)
            return record

        monkeypatch.setattr(service, "build", build_then_handoff)
    else:
        real_write = store.write_artifact

        def write_then_handoff(aew_root: Path, record: dict[str, Any]):
            out = real_write(aew_root, record)
            _handoff(engine, project.token)
            return out

        monkeypatch.setattr(store, "write_artifact", write_then_handoff)
    with pytest.raises(StaleAuthority) as exc:
        service.generate(engine, token=project.token, select=True, expect="none:0")
    assert "superseded" in exc.value.message
    maps = project.root / ".aew" / store.MAPS_REL
    assert not (maps / "registry.json").exists() and not (maps / "registry-log.jsonl").exists()
    written = list((maps / "structural").glob("*.json")) if (maps / "structural").exists() else []
    assert len(written) == (0 if when == "during_generation" else 1)


def test_an_unknown_commit_is_refused_and_an_option_is_never_a_commit(tmp_path):
    repo = make_repo(tmp_path / "repo")
    for rev in ("no-such-commit", "--output=x", "HEAD:README.md"):
        with pytest.raises(MapCurrentnessUnproven) as exc:
            service.build(repo, rev)
        assert exc.value.details["reason"] == "unknown_commit"
    assert not (repo / "x").exists()


# ------------------------------------------------------------------------------------------- the commands


def files_outside_maps(aew: Path) -> dict[str, tuple[bytes, int]]:
    return {p.relative_to(aew).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(aew.rglob("*"))
            if p.is_file() and not p.relative_to(aew).as_posix().startswith("local/maps/")}


def test_map_commands_change_nothing_outside_local_maps_and_never_the_control_revision(project):
    """T5-INV-11 and plan §4.2: generation and selection are derived state with their own revision domain."""
    write(project.root, {"pyproject.toml": PYPROJECT})
    commit(project.root)
    rev = project.rev()
    aew = project.root / ".aew"
    before = files_outside_maps(aew)
    first = project.ok("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "none:0", "--json")
    assert first["selected"] and first["map_revision"].endswith(":1")
    shown = project.ok("map", "show", "--json")
    assert shown["status"] == "AVAILABLE" and shown["root"] == first["root"] and shown["selected"]
    assert shown["freshness"]["status"] == "CURRENT" and shown["map_revision"] == first["map_revision"]
    assert project.ok("map", "show", "--section", "languages", "--json")["record"]["sections"].keys() == {"languages"}
    assert project.ok("map", "show", "--root", first["root"], "--json")["root"] == first["root"]
    same = project.ok("map", "diff", "--root", first["root"], "--commit", "HEAD", "--json")
    assert same["identical"] and not any(s["changed"] for s in same["sections"].values())
    again = project.ok("map", "generate", "--token", project.token, "--json")  # idempotent, not selected
    assert again["root"] == first["root"] and not again["selected"] and "nondeterministic" not in again
    text = project.aew("map", "show")
    assert text.returncode == 0 and "status: AVAILABLE" in text.stdout
    assert files_outside_maps(aew) == before
    assert project.rev() == rev
    assert g("status", "--porcelain", cwd=project.root) == ""  # .aew/local/ is git-ignored


def test_a_selection_is_refused_on_a_stale_map_revision_in_its_own_domain(project):
    out = project.ok("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "none:0", "--json")
    res = project.aew("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "none:0")
    assert res.returncode == 3
    error = res.error
    assert error["code"] == "STALE_REVISION" and error["details"]["domain"] == "map_revision"
    assert error["details"]["current"] == out["map_revision"]
    bad = project.aew("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "7")
    assert bad.returncode == 2 and bad.error["code"] == "USAGE"
    assert project.aew("map", "generate", "--token", project.token, "--select").error["code"] == "USAGE"


def test_a_regenerated_selected_commit_with_other_bytes_is_reported_never_a_lock_out(project):
    out = project.ok("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "none:0", "--json")
    registry_path = project.root / ".aew" / store.REGISTRY_REL
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    fake = "f" * 64  # as if an earlier run of the same generator had produced other bytes for this commit
    registry["selected"]["structural"].update(sha256=fake, root=store.artifact_rel(fake))
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    report = project.ok("map", "generate", "--token", project.token, "--json")
    assert report["nondeterministic"] == {"code": "MAP_ARTIFACT_NONDETERMINISTIC", "selected": fake,
                                          "generated": out["root"], "source_revision": out["source_revision"]}
    refused = project.aew("map", "generate", "--token", project.token, "--select", "--expect-map-rev",
                          out["map_revision"])
    assert refused.returncode == 6 and refused.error["code"] == "MAP_ARTIFACT_NONDETERMINISTIC"
    assert json.loads(registry_path.read_text(encoding="utf-8")) == registry  # left as it is
    replaced = project.ok("map", "generate", "--token", project.token, "--select", "--expect-map-rev",
                          out["map_revision"], "--replace-nondeterministic", "--json")
    assert replaced["selected"] and replaced["root"] == out["root"]
    log = (project.root / ".aew" / store.LOG_REL).read_text(encoding="utf-8").splitlines()
    last = json.loads(log[-1])
    assert last["previous"] == fake and last["new"] == out["root"]
    assert last["replaced_nondeterministic"]["selected"] == fake and last["actor"]["kind"] == "lead"


def test_a_corrupt_selected_map_is_unavailable_to_show_and_refused_by_root(project):
    out = project.ok("map", "generate", "--token", project.token, "--select", "--expect-map-rev", "none:0", "--json")
    (project.root / ".aew" / store.artifact_rel(out["root"])).write_bytes(b"{}")
    shown = project.ok("map", "show", "--json")
    assert shown == {"ok": True, "status": "UNAVAILABLE", "reason": "corrupt", "map_revision": out["map_revision"]}
    res = project.aew("map", "show", "--root", out["root"])
    assert res.returncode == 6 and res.error["code"] == "MAP_ARTIFACT_CORRUPT"
    shutil.rmtree(project.root / ".aew" / store.MAPS_REL)  # deleting local/maps means "no selection"
    assert project.ok("map", "show", "--json") == {"ok": True, "status": "UNAVAILABLE", "reason": "none",
                                                     "map_revision": "none:0"}


def test_map_diff_compares_section_by_section_and_stores_nothing(project):
    first = g("rev-parse", "HEAD", cwd=project.root)
    write(project.root, {"pyproject.toml": PYPROJECT, "tests/test_x.py": b""})
    commit(project.root)
    out = project.ok("map", "diff", "--commit", first, "--commit", "HEAD", "--json")
    assert not out["identical"] and out["sections"]["entry_point_candidates"]["changed"]
    assert out["sections"]["test_candidates"]["changed"] and "path_listing_sha256" in out["envelope"]
    assert not (project.root / ".aew" / store.MAPS_REL).exists()
    assert project.aew("map", "diff", "--commit", "HEAD").error["code"] == "USAGE"


def test_an_invocation_credential_is_refused_map_generate(tmp_path):
    p = sample_project(tmp_path)
    role, _ = dispatch(p, create_investigation(p, tmp_path))
    res = p.aew("map", "generate", "--token", role.token, "--select", "--expect-map-rev", "none:0")
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"
    assert not (p.root / ".aew" / store.MAPS_REL).exists()
    res = p.aew("map", "generate")
    assert res.returncode == 2 and "Lead credential required" in res.error["message"]
