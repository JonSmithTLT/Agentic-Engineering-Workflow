"""V-01's profile for the built structural maps, held against A-14's obligations over real git (register E293; the
profile is ``docs/implementation/maps-v01-profile.md``, which names each test here with the obligation it holds).

The scoped slice keeps a Ticket's own directories whatever the record's global cap cut (P01-12, P01-29; an external
audit's reproduction); an orientation names its work revision, source basis and recipient, and a map selected for one
commit never passes as current for another base (P01-04); reading and generating a map runs no repository-controlled
code (P01-10); no map's freshness turns CURRENT on a timer (P01-07, P01-24); and every map a reader serves is labelled
``AGENT_REACHABLE_DERIVED``, selected or not, while the artifact itself never carries the label (P01-37, P01-38)."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_investigation, dispatch, sample_project

from aew.maps import freshness as F
from aew.maps import gitobjects, rules, service, slices, store, structural
from aew.maps.canonical import seal

IS_WINDOWS = sys.platform == "win32"


def g(*args: str, cwd: Path) -> str:
    kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS else {}  # no console window
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True, timeout=120,
                          stdin=subprocess.DEVNULL, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, **kw)
    return proc.stdout.decode("utf-8", "surrogateescape").strip()


def make_repo(path: Path, files: dict[str, bytes]) -> Path:
    path.mkdir(parents=True)
    g("init", "-q", "-b", "main", cwd=path)
    for key, value in (("user.name", "AEW Test"), ("user.email", "aew-test@invalid"), ("core.autocrlf", "false"),
                       ("maintenance.auto", "false")):
        g("config", key, value, cwd=path)
    write(path, files)
    return commit(path, "initial")


def write(root: Path, files: dict[str, bytes]) -> None:
    for rel, data in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def commit(repo: Path, message: str = "change") -> Path:
    g("add", "-A", cwd=repo)
    g("commit", "-q", "-m", message, cwd=repo)
    return repo


def select(aew: Path, repo: Path, rev: str = "HEAD") -> dict[str, Any]:
    """The map of ``rev``, stored and selected as the Lead's `aew map generate --select` stores and selects it."""
    record = service.build(repo, rev)
    sha, rel = store.write_artifact(aew, record)
    store.select_structural(aew, expect=store.NO_REGISTRY, actor={"kind": "lead"}, entry={
        "root": rel, "sha256": sha, "source_revision": record["source_revision"], "source_tree": record["source_tree"],
        "object_format": record["object_format"], "generator_version": record["generator"]["version"],
        "ruleset_sha256": record["generator"]["ruleset_sha256"]})
    return {**record, "artifact_sha256": sha}


def row_paths(lines: list[str]) -> set[str]:
    return {line.split(" | ")[0][2:] for line in lines if re.match(r"- \S+ \| \d+ \| ", line)}


# The audit's reproduction: 205 directories of two files each and `z_task` with one, 411 files and 207 rows with the
# root. The record keeps the 200 largest, so `z_task`, the smallest, is cut before any scope is applied.
CAPPED = {f"d{i:03d}/{name}": b"x\n" for i in range(205) for name in ("a.txt", "b.txt")} | {"z_task/only.txt": b"x\n"}


# ------------------------------------------------------------------------------------------- the scoped slice


def test_a_tickets_small_directory_survives_the_global_directory_cap(tmp_path):
    """P01-12 and P01-29: the record's directory cap bounds the global view, never a Ticket's own directories. The
    slice reads the rows in scope from the map's source tree when the cap cut any, so `z_task` is shown with its
    count, and a regenerated pack is the one built."""
    repo = make_repo(tmp_path / "repo", CAPPED)
    aew = tmp_path / "aew"
    record = select(aew, repo)
    d = record["sections"]["directories"]
    assert (d["rows_total"], len(d["rows"]), d["rows_omitted"]) == (207, 200, 7)
    assert "z_task" not in {r["path"] for r in d["rows"]}  # the global view keeps its cap
    head = g("rev-parse", "HEAD", cwd=repo)
    entry, built = slices.pin(aew, repo, head, ["z_task/**"])
    assert row_paths(built) == {".", "z_task"}
    assert "- z_task | 1 | unknown | Text" in built
    assert any("2 of 2 shown" in line and "read from the map's source tree" in line for line in built)
    assert not any("may be missing" in line or "no directory of commit" in line for line in built)
    assert slices.lines(aew, repo, entry, ["z_task/**"]) == built  # the pinned body, regenerated
    # The unrestricted view is the compact global one, as before, and says how many directories there are.
    whole = slices.pin(aew, repo, head, [])[1]
    assert len(row_paths(whole)) == slices.ROWS and any(f"of {d['rows_total']} directories" in x for x in whole)


@pytest.mark.parametrize("failure", ["git_fails", "other_listing", "other_generator"])
def test_rows_in_scope_the_cap_cut_and_that_cannot_be_listed_are_never_read_as_absent(tmp_path, monkeypatch, failure):
    """P01-12 and P01-18: when the source tree cannot be listed, or its listing is not the one the record was made
    from, or another generator made the map, the slice uses the record's rows, says its count is a lower bound and
    that a directory in scope it does not show is not absent, and makes no claim that a scope path is no directory."""
    repo = make_repo(tmp_path / "repo", CAPPED)
    aew = tmp_path / "aew"
    record = select(aew, repo)
    real = gitobjects.list_tree
    if failure == "git_fails":
        monkeypatch.setattr(gitobjects, "list_tree", lambda *a, **k: (_ for _ in ()).throw(OSError("no git")))
    elif failure == "other_listing":
        monkeypatch.setattr(gitobjects, "list_tree", lambda *a, **k: real(*a, **k)[1:])
    else:
        monkeypatch.setattr(slices, "_identity", lambda: {**record["generator"], "version": 0})
    _, built = slices.pin(aew, repo, g("rev-parse", "HEAD", cwd=repo), ["z_task/**"])
    assert row_paths(built) == {"."}
    assert any("1 of at least 1 shown" in line for line in built)
    missing = next(line for line in built if "may be missing" in line)
    assert "not absent from the project" in missing and "200 largest of 207 directories" in missing
    assert not any("no directory of commit" in line for line in built)


# ------------------------------------------------------------------------------------------- per-consumer identity


def test_a_map_selected_for_one_commit_never_passes_as_current_for_another_base(tmp_path):
    """P01-04: the slice's freshness is the selected map's against the work's own base, never the map's own commit or
    the head. The map of A is CURRENT for a Ticket at A and STALE, with its reason, for one at B."""
    repo = make_repo(tmp_path / "repo", {"src/a.py": b"a\n"})
    a = g("rev-parse", "HEAD", cwd=repo)
    aew = tmp_path / "aew"
    record = select(aew, repo)
    write(repo, {"lib/b.py": b"b\n"})
    b = g("rev-parse", "HEAD", cwd=commit(repo))
    at_a, lines_a = slices.pin(aew, repo, a, ["src/**"])
    at_b, lines_b = slices.pin(aew, repo, b, ["src/**"])
    assert at_a["sha256"] == at_b["sha256"] == record["artifact_sha256"]  # one selected map
    assert at_a["freshness"]["status"] == "CURRENT" and at_a["freshness"]["against_commit"] == a
    assert at_b["freshness"]["status"] == "STALE" and at_b["freshness"]["against_commit"] == b
    assert any(f"freshness against the work's base {b[:12]}: STALE (path_listing)" in x for x in lines_b)
    assert not any(": CURRENT" in x for x in lines_b)
    assert any(f"of commit {a[:12]}" in x for x in lines_b)  # the map names its own commit, not the base


def test_the_orientation_names_its_work_revision_source_basis_and_recipient(tmp_path):
    """P01-04: the pack a worker gets names its recipient (the invocation and its role), its work revision (the work
    unit and the accepted plan) and its source basis (the evaluated snapshot's base), and the map slice inside it is
    qualified against that same base."""
    p = sample_project(tmp_path)
    _, out = dispatch(p, create_investigation(p, tmp_path))
    inv = out["invocation"]
    from aew.engine.api import Engine

    state = Engine.discover(p.root).store.read()["invocations"][inv]
    base = state["snapshot"]["base_revision"]
    text = (p.root / ".aew" / "local" / "packs" / inv / "pack.md").read_text(encoding="utf-8")
    assert f"# AEW launch contract — {inv} (" in text and f"- Role: **{state['role']}**" in text
    assert f"- Work unit: **{state['work_unit']}**" in text and "- Accepted plan: " in text
    assert f"- Evaluated snapshot: base `{base}`" in text
    assert f"freshness against the work's base {base[:12]}: " in text
    assert slices.pinned(state["pack"]["sources"])["freshness"]["against_commit"] == base


# ------------------------------------------------------------------------------------------- safe input handling


def test_reading_or_generating_a_map_never_runs_repository_controlled_code(tmp_path):
    """P01-10: the repository's own Git configuration, hooks, filter and textconv drivers and attributes are untrusted.
    Generating the map, its freshness and the slice's scoped listing read Git objects with plumbing only (no checkout,
    no filters, hooks off). This test holds the outcome, that not one of the planted programs runs; it does not hold
    how (``git.safe_config``'s neutralisation of configured drivers is one way, plumbing that never invokes them is
    another), so a change that keeps the outcome by other means still passes (the review of #567, n2)."""
    files = {".gitattributes": b"* filter=planted diff=planted\n", "pyproject.toml": b"[project]\nname = 'x'\n"}
    files |= {f"d{i:03d}/a.txt": b"x\n" for i in range(205)} | {"z_task/b.txt": b"x\n"}
    repo = make_repo(tmp_path / "repo", files)
    marker = "planted-ran"
    for key in ("core.fsmonitor", "filter.planted.clean", "filter.planted.smudge", "filter.planted.process",
                "diff.planted.textconv", "diff.external", "core.pager", "core.sshCommand", "core.askPass"):
        g("config", key, f"echo {key} >> {marker}", cwd=repo)
    hooks = repo / ".git" / "hooks"
    for hook in ("post-checkout", "post-index-change", "reference-transaction", "pre-auto-gc"):
        (hooks / hook).write_text(f"#!/bin/sh\necho {hook} >> {marker}\n", encoding="utf-8", newline="\n")
        (hooks / hook).chmod(0o755)
    aew = tmp_path / "aew"
    record = select(aew, repo)
    head = g("rev-parse", "HEAD", cwd=repo)
    assert F.freshness(repo, record, head, service.identity())["status"] == "CURRENT"
    _, built = slices.pin(aew, repo, head, ["z_task/**"])
    assert "- z_task | 1 | unknown | Text" in built  # the scoped listing ran too
    assert not list(tmp_path.rglob(marker))


# ------------------------------------------------------------------------------------------- no currentness timer


def test_no_map_freshness_turns_current_on_a_timer(tmp_path, monkeypatch):
    """P01-07 and P01-24: a map's freshness is a comparison of immutable Git objects, computed on read, and no clock
    enters it: the freshness module reads no time, the record holds no freshness, and a STALE map read again a year
    later (the clock moved, the in-process cache cleared) is still STALE for the same reason."""
    tree = ast.parse(Path(F.__file__).read_text(encoding="utf-8"))
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"time", "datetime", "calendar"}, imported
    repo = make_repo(tmp_path / "repo", {"src/a.py": b"a\n"})
    record = service.build(repo, "HEAD")
    record = {**record, "artifact_sha256": seal(record)[0]}
    assert not {"status", "freshness", "current", "expires", "valid_until"} & set(record)
    write(repo, {"lib/b.py": b"b\n"})
    b = g("rev-parse", "HEAD", cwd=commit(repo))
    first = F.freshness(repo, record, b, service.identity())
    later = time.time() + 365 * 24 * 3600
    monkeypatch.setattr(time, "time", lambda: later)
    monkeypatch.setattr(time, "monotonic", lambda: later)
    F.clear_cache()
    assert F.freshness(repo, record, b, service.identity()) == first
    assert first["status"] == "STALE" and first["reasons"] == ["path_listing"]


# ------------------------------------------------------------------------------------------- the evidence class


def test_every_map_read_is_labelled_agent_reachable_derived_and_selection_never_upgrades_it(project):
    """P01-37 and P01-38: the class follows the path that produced the map (agent-reachable code writing
    agent-reachable files), so every reader labels it AGENT_REACHABLE_DERIVED, selected or not, and the artifact
    itself never carries a class (a self-label would be a claim)."""
    import shutil

    from aew.maps import EVIDENCE_CLASS

    shutil.rmtree(project.root / ".aew" / store.MAPS_REL)
    made = project.ok("map", "generate", "--json", env={"AEW_LEAD_TOKEN": project.token})
    assert made["evidence_class"] == EVIDENCE_CLASS == "AGENT_REACHABLE_DERIVED" and not made["selected"]
    picked = project.ok("map", "generate", "--select", "--expect-map-rev", "none:0", "--json",
                        env={"AEW_LEAD_TOKEN": project.token})
    assert picked["selected"] and picked["evidence_class"] == EVIDENCE_CLASS
    shown = project.ok("map", "show", "--json")
    assert shown["selected"] and shown["evidence_class"] == EVIDENCE_CLASS
    # `map diff` too, of stored roots and of records generated in memory (the review of #567, m1), and the shared
    # module's answers (register F15.8)
    diffed = project.ok("map", "diff", "--root", made["root"], "--commit", "HEAD", "--json")
    assert diffed["evidence_class"] == EVIDENCE_CLASS
    for args in (["map", "show", "--section", "languages"], ["map", "search", "README.md"]):
        assert project.ok(*args, "--json")["evidence_class"] == EVIDENCE_CLASS
    assert project.ok("map", "show", "--root", made["root"], "--json")["evidence_class"] == EVIDENCE_CLASS
    artifact = (project.root / ".aew" / store.artifact_rel(made["root"])).read_bytes()
    assert EVIDENCE_CLASS.encode() not in artifact and b"evidence_class" not in artifact
    row = slices.resume_row(project.root / ".aew", project.root, g("rev-parse", "HEAD", cwd=project.root))
    assert row["evidence_class"] == EVIDENCE_CLASS
    record = store.read_artifact(project.root / ".aew", made["root"])
    first = slices.body(record, {"status": "CURRENT", "reasons": []}, [])[0]
    assert first.endswith(f"evidence class {EVIDENCE_CLASS})")
    assert structural.generator_identity(rules.load())["name"] in first
