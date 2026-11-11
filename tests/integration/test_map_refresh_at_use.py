"""The structural map is refreshed at use (register E62 with E184; ADR-0015, amended 2026-11-11).

A Lead's dispatch whose selected map is STALE, or absent, against the work's base makes the base's map first, under
the dispatching Lead's own credential, bounded by ``service.REFRESH_S``; at the authoritative head it selects it. Its
outcome is a line inside the slice the pack pins. Nothing else writes a map: the integration custodian's dispatch
and a regenerated pack use the map as it is, and a refresh that fails or runs out of time never fails the pack."""

from __future__ import annotations

import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from aewflow import create_investigation, dispatch, sample_project
from conftest import Project
from test_map_context import advance_main, invocations, pack_text, regenerate, select_map, switch_on

from aew.maps import gitobjects, service, slices, store
from aew.workspace import git as gitmod

LEAD = {"kind": "lead", "session_label": "lead-a", "generation": 1, "token_id": "LT-test"}
REFRESHED = "refresh at dispatch: this map was made for the work's base"


def aew_root(p: Project) -> Path:
    return p.root / ".aew"


def selected_sha(p: Project) -> str | None:
    registry = store.read_registry(aew_root(p)) or {}
    return ((registry.get("selected") or {}).get("structural") or {}).get("sha256")


def artifacts(p: Project) -> set[str]:
    return {f.name for f in (aew_root(p) / store.MAPS_REL).rglob("*.json") if f.name != "registry.json"}


def log_lines(p: Project) -> list[str]:
    path = aew_root(p) / store.LOG_REL
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


@pytest.fixture(autouse=True)
def _fresh_memo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_made", {})


def counted_builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    made: list[str] = []
    real = service.build

    def build(repo: Path, commit: str, **kw: Any) -> dict[str, Any]:
        made.append(commit)
        return real(repo, commit, **kw)

    monkeypatch.setattr(service, "build", build)
    return made


# ------------------------------------------------------------------------------------------- through the CLI


def test_a_lead_dispatch_at_a_stale_head_refreshes_and_selects_the_heads_map_once(tmp_path):
    p = sample_project(tmp_path)
    switch_on(p)
    first = select_map(p)
    head = advance_main(p, "moved.txt")
    _, out = dispatch(p, create_investigation(p, tmp_path, title="After the move"))
    inv = out["invocation"]
    entry = slices.pinned(invocations(p)[inv]["pack"]["sources"])
    assert entry["sha256"] != first["root"] and entry["source_revision"] == head
    assert entry["freshness"]["status"] == "CURRENT" and selected_sha(p) == entry["sha256"]
    text = pack_text(p, inv)
    assert REFRESHED in text and "and is now the selected map" in text
    assert regenerate(p, inv)["matches_recorded"]  # the refresh line is pinned with the slice
    logged = log_lines(p)
    assert '"by":"dispatch_refresh"' in logged[-1] and '"kind":"lead"' in logged[-1]
    # A second dispatch at the same base finds the map CURRENT: nothing is generated or selected again.
    _, again = dispatch(p, create_investigation(p, tmp_path, title="Same base"))
    second = slices.pinned(invocations(p)[again["invocation"]]["pack"]["sources"])
    assert second["sha256"] == entry["sha256"] and "refresh" not in second
    assert "refresh at dispatch" not in pack_text(p, again["invocation"]) and log_lines(p) == logged


# ------------------------------------------------------------------------------------------- in process


def test_a_base_that_is_not_the_head_is_stored_and_pinned_never_selected_and_made_once(tmp_path, monkeypatch):
    """The project's selection never moves back to an older commit, and two bases never trade it."""
    p = sample_project(tmp_path)
    old = select_map(p)
    head = advance_main(p, "moved.txt")
    at_head = select_map(p)
    made = counted_builds(monkeypatch)
    before = log_lines(p)
    entry, lines = slices.pin(aew_root(p), p.root, old["source_revision"], [], lead=LEAD, head=head)
    assert entry["sha256"] == old["root"]  # deterministic: the old commit's map, made again
    assert entry["freshness"]["status"] == "CURRENT" and "stored and not selected" in entry["refresh"]
    assert selected_sha(p) == at_head["root"] and log_lines(p) == before
    again, _ = slices.pin(aew_root(p), p.root, old["source_revision"], [], lead=LEAD, head=head)
    assert again["sha256"] == old["root"] and made == [old["source_revision"]]  # made once in this process
    assert slices.lines(aew_root(p), p.root, entry, []) == lines


def test_only_a_leads_transaction_refreshes_the_map(tmp_path, monkeypatch):
    """No new writer: a custodian's dispatch, a regenerated pack and a pin with no Lead write nothing under maps/."""
    from aew.engine.api import Engine

    p = sample_project(tmp_path)
    switch_on(p)
    _, out = dispatch(p, create_investigation(p, tmp_path))
    inv = out["invocation"]
    advance_main(p, "moved.txt")
    kept = artifacts(p)
    entry, _ = slices.pin(aew_root(p), p.root, gitmod.out("rev-parse", "HEAD", cwd=p.root), [])
    assert entry["freshness"]["status"] == "STALE" and "refresh" not in entry and artifacts(p) == kept

    engine = Engine.discover(p.root)
    seen: list[Any] = []
    real = slices.pin

    def pin(*a: Any, **kw: Any) -> Any:
        seen.append(kw.get("lead"))
        return real(*a, **kw)

    monkeypatch.setattr(slices, "pin", pin)
    state = engine.store.current()
    for actor in ({"kind": "custodian", "id": "IA-0001"}, LEAD):
        state["invocations"][inv].pop("pack", None)  # as a new invocation's first build (a rebuild keeps its map)
        engine._packs.build_pack(SimpleNamespace(actor=actor, state=state), inv)
    assert seen == [None, LEAD]


def test_a_refresh_past_its_limit_is_one_pinned_line_and_never_fails_the_pack(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    select_map(p)
    head = advance_main(p, "moved.txt")
    kept, before = artifacts(p), log_lines(p)
    monkeypatch.setattr(service, "REFRESH_S", 0.5)
    real = gitobjects.list_tree

    def slow(repo: Path, tree: str, **kw: Any) -> Any:  # a git that answers, slowly, inside the refresh only
        if kw.get("timeout", gitmod.OBJECT_TIMEOUT_S) <= 0.5:
            time.sleep(0.8)
        return real(repo, tree, **kw)

    monkeypatch.setattr(gitobjects, "list_tree", slow)
    entry, lines = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert entry["freshness"]["status"] == "STALE"
    took = re.search(r"not refreshed \(timeout, after ([\d.]+) s of the 0\.5 s allowed\)", entry["refresh"])
    assert took and float(took.group(1)) < 0.5 + 1.0, entry["refresh"]  # one bound on the whole refresh
    assert any(line == entry["refresh"] for line in lines)
    assert artifacts(p) == kept and log_lines(p) == before
    assert slices.lines(aew_root(p), p.root, entry, []) == lines  # a regenerated pack renders the same line


def test_a_failed_refresh_of_an_absent_map_is_pinned_in_its_unavailable_reason(tmp_path, monkeypatch):
    p = sample_project(tmp_path)
    for f in (aew_root(p) / store.MAPS_REL).iterdir():
        if f.is_file():
            f.unlink()
    head = gitmod.out("rev-parse", "HEAD", cwd=p.root)

    def broken(*_a: Any, **_kw: Any) -> Any:
        raise OSError("the commit's objects cannot be read")

    monkeypatch.setattr(service, "build", broken)
    entry, lines = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert entry["unavailable"].startswith("none; refresh at dispatch: not refreshed (OSError")
    assert slices.lines(aew_root(p), p.root, entry, []) == lines


def test_a_selection_that_lands_during_a_refresh_wins_and_the_pack_pins_its_own_map(tmp_path, monkeypatch):
    """The race with `aew map generate --select`, which takes the registry's lock and not the control lock: the
    compare-and-set lets the other selection stand, and this pack pins the map it made, CURRENT for its base."""
    p = sample_project(tmp_path)
    old = select_map(p)
    head = advance_main(p, "moved.txt")
    real = service.build

    def build(repo: Path, commit: str, **kw: Any) -> dict[str, Any]:
        record = real(repo, commit, **kw)
        select_map(p)  # lands between the refresh's read of the registry and its selection
        return record

    monkeypatch.setattr(service, "build", build)
    other = selected_sha(p)
    entry, _ = slices.pin(aew_root(p), p.root, head, [], lead=LEAD, head=head)
    assert other == old["root"] and selected_sha(p) != old["root"]  # the other selection stands
    assert entry["freshness"]["status"] == "CURRENT" and entry["source_revision"] == head
    assert "another selection landed meanwhile" in entry["refresh"]
