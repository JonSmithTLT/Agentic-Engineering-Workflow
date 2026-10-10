"""F20.8, S1: contract 0.1.3's maps routes, served by the dashboard server over real git and the real CLI (the change
note ``docs/design/proposals/dashboard-maps-and-history-search-v0.1.md`` §4 and Appendix A).

The fixture is a project with a structural map generated and selected through ``aew map generate`` (the Lead's
token) and a discovery record selected as the architecture reference. Every maps route is read over HTTP, GET and
HEAD, and validated against the accepted contract; then the states (no registry, an invalid one, a missing,
corrupt, oversized, linked or FIFO artifact), freshness, the architecture reference, the refusals before any file or
git access, the bounded scan, paging, the typed diff, the size ceilings on a generated and a planted worst case, no
disclosure, no writes, no lock, the conditional requests and the git processes a warm read spawns.
"""

from __future__ import annotations

import builtins
import copy
import http.client
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import complete_investigation, create_investigation, sample_project  # noqa: E402
from conftest import Project, git  # noqa: E402

from aew import profile  # noqa: E402
from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard import mapview as MV  # noqa: E402
from aew.dashboard import projections as P  # noqa: E402
from aew.dashboard import reader as R  # noqa: E402
from aew.dashboard.reasons import REASONS, codes_in  # noqa: E402
from aew.dashboard.server import DashboardServer, error_body, pending_routes  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.engine.lock import FileLock  # noqa: E402
from aew.engine.store import LOCK_REL  # noqa: E402
from aew.errors import IntegrityError, LockTimeout  # noqa: E402
from aew.harness.contract import CREDENTIAL_RE  # noqa: E402
from aew.history import index as HI  # noqa: E402
from aew.maps import freshness as MF  # noqa: E402
from aew.maps import rules as MR  # noqa: E402
from aew.maps import store as MS  # noqa: E402
from aew.maps.canonical import seal  # noqa: E402
from aew.workspace import git as aew_git  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
MAPS = P.MAPS_ROUTES
SCHEMA = {route: CT.RESPONSE_SCHEMAS[route] for route in MAPS}
POSIX = os.name != "nt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HEX = "0123456789abcdef"


class OpenAccess:
    """Test-only: every request may read (the session suite covers authentication, ``401`` included)."""

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        return None


class Gate:
    closed = False

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        return error_body("SESSION_REQUIRED") if self.closed else None


class Client:
    def __init__(self, server: DashboardServer) -> None:
        self.server = server

    def get(self, path: str, *, head: bool = False, inm: str | None = None,
            timeout: float = 60) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=timeout)
        try:
            conn.request("HEAD" if head else "GET", f"/api/v1{path}",
                         headers={"If-None-Match": inm} if inm is not None else {})
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, raw
        finally:
            conn.close()

    def ok(self, path: str) -> dict[str, Any]:
        status, _, raw = self.get(path)
        assert status == 200, (path, status, raw[:500])
        body = json.loads(raw)
        schema = SCHEMA[route_of(path)]
        assert CONTRACT.violations(schema, body) == [], (path, CONTRACT.violations(schema, body)[:5])
        assert body["schema_version"] == "0.1.3"
        return body

    def data(self, path: str) -> dict[str, Any]:
        return self.ok(path)["data"]

    def error(self, path: str, status: int, code: str) -> dict[str, Any]:
        got, headers, raw = self.get(path)
        body = json.loads(raw)
        assert got == status, (path, got, body)
        assert CONTRACT.violations(CT.ERROR_SCHEMA, body) == [] and body["code"] == code, body
        assert "etag" not in headers
        return body


def route_of(path: str) -> str:
    bare = path.split("?", 1)[0]
    if bare in ("/maps", "/maps/structural", "/maps/diff"):
        return bare
    return "/maps/structural/{root}/inputs" if bare.endswith("/inputs") else "/maps/structural/{root}"


@contextmanager
def served(p: Project, authenticator: Any = None) -> Iterator[Client]:
    server = DashboardServer(Engine.discover(p.root), authenticator=authenticator or OpenAccess(),
                             validate_with=CONTRACT)
    server.start()
    try:
        yield Client(server)
    finally:
        server.stop()


def map_rev(p: Project) -> str:
    return p.ok("map", "show", "--json")["map_revision"]


def generate(p: Project, *, commit: str | None = None, select: bool = False) -> str:
    args = ["map", "generate", "--token", p.token, "--json"]
    if commit:
        args += ["--commit", commit]
    if select:
        args += ["--select", "--expect-map-rev", map_rev(p)]
    return p.ok(*args)["root"]


def commit_file(p: Project, rel: str, text: str, message: str) -> str:
    path = p.root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    git("add", rel, cwd=p.root)
    git("commit", "-q", "-m", message, cwd=p.root)
    return git("rev-parse", "HEAD", cwd=p.root)


PYPROJECT = '[project]\nname = "calc"\n[project.scripts]\ncalc = "calc.core:add"\n[tool.pytest.ini_options]\n'


def add_metadata(p: Project) -> str:
    """Descriptors and an attributes file the generator reads: the map's metadata inputs."""
    commit_file(p, ".gitattributes", "vendor/** linguist-vendored\n", "attributes")
    commit_file(p, "package.json", '{"name": "calc", "main": "index.js"}\n', "a node descriptor")
    return commit_file(p, "pyproject.toml", PYPROJECT, "a python descriptor")


def maps_dir(p: Project) -> Path:
    return p.root / ".aew" / MS.MAPS_REL


def artifact(p: Project, root: str) -> Path:
    return p.root / ".aew" / MS.artifact_rel(root)


def record_of(p: Project, root: str) -> dict[str, Any]:
    return MS.read_artifact(p.root / ".aew", root)


def plant(p: Project, record: dict[str, Any]) -> str:
    """Write ``record`` as a sealed, schema-valid artifact, as a hand (or a bug) could: the generator never made it."""
    body = {k: v for k, v in record.items() if k != "artifact_sha256"}
    sha, data = seal(body)
    MS.validate("codebase-map", {**body, "artifact_sha256": sha}, source="planted")
    path = artifact(p, sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha


def concrete(route: str, root: str, other: str) -> str:
    return {"/maps/structural/{root}": f"/maps/structural/{root}",
            "/maps/structural/{root}/inputs": f"/maps/structural/{root}/inputs",
            "/maps/diff": f"/maps/diff?a={root}&b={other}"}.get(route, route)


class World:
    p: Project
    tmp: Path
    client: Client
    selected: str
    older: str
    discovery: str
    head: str


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> Iterator[World]:
    """A map of the first commit (not selected), then a map of the head selected, and a discovery record selected as
    the architecture reference."""
    w = World()
    w.tmp = tmp_path_factory.mktemp("maps")
    w.p = sample_project(w.tmp)
    first = git("rev-parse", "HEAD", cwd=w.p.root)
    w.discovery = complete_investigation(w.p, create_investigation(w.p, w.tmp, title="Architecture survey"))
    add_metadata(w.p)
    w.head = commit_file(w.p, "calc/extra.py", "X = 1\n", "add calc/extra.py")
    w.older = generate(w.p, commit=first)
    w.selected = generate(w.p, select=True)
    w.p.ok("map", "select-architecture", w.discovery, "--token", w.p.token, "--expect-map-rev", map_rev(w.p), "--json")
    with served(w.p) as client:
        w.client = client
        yield w


# ---------------------------------------------------------------------------------------------- conformance


@pytest.mark.parametrize("route", MAPS)
def test_every_maps_route_answers_get_and_head_as_the_contract_says(world, route):
    path = concrete(route, world.selected, world.older)
    status, headers, raw = world.client.get(path)
    assert status == 200, (path, raw[:300])
    body = json.loads(raw)
    assert CONTRACT.violations(SCHEMA[route], body) == []
    assert body["schema_version"] == "0.1.3" == P.ENVELOPE_VERSION[route] and body["project_id"] == "calc"
    assert headers["cache-control"] == "no-store" and headers["etag"].startswith('"')
    assert body["data"]["label"] == MV.LABEL
    head_status, head_headers, head_raw = world.client.get(path, head=True)
    assert head_status == 200 and head_raw == b""
    assert head_headers == headers


def test_the_maps_routes_are_served_and_no_longer_pending():
    assert not pending_routes(CONTRACT.paths) & set(MAPS)
    assert set(MAPS) <= set(CONTRACT.paths)


def test_maps_is_a_capability_available_on_every_project(world):
    status, _, raw = world.client.get("/capabilities")
    caps = json.loads(raw)["data"]
    assert status == 200 and caps["maps"] == {"state": "AVAILABLE", "reasons": []}
    assert "history_search" not in caps  # S2's key, absent until it serves the route


def test_maps_shows_the_selected_map_its_freshness_and_the_architecture_reference(world):
    data = world.client.data("/maps")
    assert data["registry"] == {"state": "PRESENT", "reasons": []}
    epoch, n = data["map_revision"].split(":")
    assert len(epoch) == 16 and int(n) == 2
    structural = data["structural"]
    assert structural["state"] == "AVAILABLE" and structural["summary"]["root"] == world.selected
    assert structural["summary"]["selected"] is True and structural["summary"]["source_revision"] == world.head
    assert structural["freshness"]["status"] == "CURRENT" and structural["freshness"]["against_commit"] == world.head
    arch = data["architecture"]
    assert arch["evidence"] == {"id": world.discovery, "kind": "evidence", "title": None}
    assert arch["freshness"]["authoritative_commit"] == world.head and arch["note"] == MV.ARCHITECTURE_NOTE
    assert arch["freshness"]["status"] in ("CURRENT", "STALE")  # the survey observed calc/**, then calc/extra.py
    assert data["stored"] == {"count": 2}


def test_the_architecture_evidence_link_answers(world):
    arch = world.client.data("/maps")["architecture"]
    status, _, _ = world.client.get(f"/evidence/{arch['evidence']['id']}")
    assert status == 200  # archived evidence, found without the lock


def test_freshness_against_another_full_id_and_an_unknown_one(world):
    first = record_of(world.p, world.older)["source_revision"]
    against_first = world.client.data(f"/maps?against={first}")["structural"]["freshness"]
    assert against_first["status"] == "STALE" and against_first["against_commit"] == first
    assert "MAP_STALE_PATH_LISTING" in [r["code"] for r in against_first["reasons"]]
    unknown = world.client.data(f"/maps?against={'e' * 40}")["structural"]["freshness"]
    assert unknown["status"] == "UNKNOWN" and unknown["against_commit"] is None
    assert unknown["reasons"][0]["code"] == "MAP_CURRENTNESS_UNPROVEN"
    assert "does not resolve" in unknown["reasons"][0]["message"]


def test_the_detail_projects_every_section_or_the_one_asked_for(world):
    data = world.client.data(f"/maps/structural/{world.selected}")
    assert set(data["sections"]) == set(MV.SECTIONS)
    assert data["summary"]["selected"] is True and data["freshness"]["status"] == "CURRENT"
    assert data["inputs"]["count"] >= 0 and data["inputs"]["path_listing_sha256"]
    assert data["limits"]["tracked_paths"]["seen"] > 0
    assert all(s["dropped_fields"] == 0 and s["dropped_items"] == 0 for s in data["sections"].values())
    assert data["dropped_fields"] == 0 and data["cut_strings"] == 0
    rows = data["sections"]["directories"]["rows"]
    assert {r["path"] for r in rows} >= {".", "calc", "tests", "vendor"}
    one = world.client.data(f"/maps/structural/{world.selected}?section=languages")
    assert set(one["sections"]) == {"languages"} and one["sections"]["languages"]["counts"]["Python"] >= 3
    older = world.client.data(f"/maps/structural/{world.older}")
    assert older["summary"]["selected"] is False and older["freshness"]["status"] == "STALE"


def test_the_list_pages_the_stored_maps_and_marks_the_selected_one(world):
    first = world.client.data("/maps/structural?limit=1")
    assert len(first["items"]) == 1 and first["next_cursor"] and first["scan_incomplete"] is None
    second = world.client.data(f"/maps/structural?limit=1&cursor={first['next_cursor']}")
    assert second["next_cursor"] is None
    items = first["items"] + second["items"]
    assert sorted(i["root"] for i in items) == sorted([world.selected, world.older])
    assert [i["root"] for i in items] == sorted(i["root"] for i in items)
    assert {i["root"]: i["selected"] for i in items} == {world.selected: True, world.older: False}
    assert all(i["status"] == "AVAILABLE" and i["generator"]["name"] == "structural" for i in items)


def test_source_revision_selects_the_map_of_that_commit(world):
    head = world.client.data(f"/maps/structural?source_revision={world.head}")["items"]
    assert [i["root"] for i in head] == [world.selected]
    first = record_of(world.p, world.older)["source_revision"]
    assert [i["root"] for i in world.client.data(f"/maps/structural?source_revision={first}")["items"]] == [
        world.older]
    assert world.client.data(f"/maps/structural?source_revision={'a' * 64}")["items"] == []


def test_the_inputs_page_by_position_to_their_end(world):
    record = record_of(world.p, world.selected)
    expected = [i["path"] for i in record["inputs"]["metadata"]]
    assert len(expected) >= 3, "the world has metadata inputs (its descriptors and attributes)"
    seen, cursor = [], None
    while True:
        path = f"/maps/structural/{world.selected}/inputs?limit=1" + (f"&cursor={cursor}" if cursor else "")
        page = world.client.data(path)
        assert page["root"] == world.selected and len(page["items"]) <= 1
        seen += [i["path"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == expected


def test_an_inputs_cursor_is_bound_to_its_root_and_a_forged_one_is_refused(world):
    cursor = world.client.data(f"/maps/structural/{world.selected}/inputs?limit=1")["next_cursor"]
    world.client.error(f"/maps/structural/{world.older}/inputs?limit=1&cursor={cursor}", 400, "CURSOR_INVALID")
    world.client.error(f"/maps/structural/{world.selected}/inputs?limit=2&cursor={cursor}", 400, "CURSOR_INVALID")
    world.client.error(f"/maps/structural/{world.selected}/inputs?cursor=AAAA", 400, "CURSOR_INVALID")
    forged = cursor_with(cursor, after=10**6)
    world.client.error(f"/maps/structural/{world.selected}/inputs?limit=1&cursor={forged}", 400, "CURSOR_INVALID")
    list_cursor = world.client.data("/maps/structural?limit=1")["next_cursor"]
    world.client.error(f"/maps/structural?limit=1&cursor={cursor_with(list_cursor, after='../x')}", 400,
                       "CURSOR_INVALID")


def cursor_with(cursor: str, **changes: Any) -> str:
    from aew.dashboard import cursors

    payload = cursors.decode(cursor)
    payload.update(changes)
    return cursors.encode(payload)


def test_an_inputs_list_with_a_4_kib_path_at_a_page_boundary_pages_to_its_end(lab):
    """m5: the inputs cursor is a position, never a path, so a 4 KiB path at a page boundary keeps the cursor (and the
    request's query) far below their bounds."""
    p, _ = lab
    record = record_of(p, generate(p))
    long = "d" + "a" * 4096  # a 4 KiB name that sorts first
    record["inputs"]["metadata"] = sorted(
        [{"path": f"m{i}", "git_oid": "a" * 40, "size": 1, "read": True, "sha256": "b" * 64} for i in range(5)]
        + [{"path": long, "git_oid": "c" * 40, "size": 2, "read": False, "reason": "capped_size"}],
        key=lambda i: i["path"])
    root = plant(p, record)
    expected = [i["path"] for i in record["inputs"]["metadata"]]
    assert expected.index(long) == 0  # the first page ends on it
    with served(p) as client:
        seen, cursor = [], None
        while True:
            page = client.data(f"/maps/structural/{root}/inputs?limit=1" + (f"&cursor={cursor}" if cursor else ""))
            seen += [i["path"] for i in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert len(cursor) < 300  # a position and a root: whatever the paths are
        assert len(seen) == 6 and seen[0].endswith(MV.MARKER) and seen[1:] == expected[1:]
        assert client.data(f"/maps/structural/{root}")["inputs"] == {
            "path_listing_sha256": record["inputs"]["path_listing_sha256"], "count": 6, "read": 5, "capped_size": 1,
            "capped_total": 0}


def test_a_control_commit_does_not_expire_a_maps_cursor(world):
    cursor = world.client.data("/maps/structural?limit=1")["next_cursor"]
    p = world.p
    p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))
    assert world.client.data(f"/maps/structural?limit=1&cursor={cursor}")["items"]


def test_the_diff_of_two_maps_is_typed(world):
    data = world.client.data(f"/maps/diff?a={world.older}&b={world.selected}")
    assert data["identical"] is False and data["a"]["root"] == world.older and data["b"]["root"] == world.selected
    assert set(data["envelope"]) >= {"source_revision", "source_tree", "path_listing_sha256"}
    rows = data["sections"]["directories"]
    assert rows["changed"] is True
    changed_rows = rows["rows"]["added"] + rows["rows"]["removed"]
    assert any(r["path"] == "calc" for r in changed_rows)  # its file count moved: one removal, one addition
    assert data["sections"]["languages"]["values"]["counts.Python"]["to"] == \
        data["sections"]["languages"]["values"]["counts.Python"]["from"] + 1
    same = world.client.data(f"/maps/diff?a={world.selected}&b={world.selected}")
    assert same["identical"] is True and same["envelope"] == {}
    assert all(s == {"changed": False, "beyond_cap": False, "values": {}} for s in same["sections"].values())


def test_no_maps_response_discloses_a_path_or_a_credential(world):
    forbidden = [".aew/", ".aew\\", "local/maps", "registry.json", "registry-log", str(world.tmp), "C:\\", "/tmp/",
                 '"actor"', "selection_id", '"verifier":']
    for route in MAPS:
        status, _, raw = world.client.get(concrete(route, world.selected, world.older))
        text = raw.decode("utf-8")
        assert status == 200
        for needle in forbidden:
            assert needle not in text, (route, needle)
        assert not CREDENTIAL_RE.search(text)
        assert codes_in(json.loads(text)) <= set(REASONS)


# ---------------------------------------------------------------------------------------------- refusals

BAD_COMMITS = ["HEAD", "main", "--output=x", "abc1234", "a" * 39, "a" * 41, "a" * 63, "a" * 65, "A" * 40,
               "a" * 40 + "%0A"]
BAD_ROOTS = ["..%2f..%2fx", "%2e%2e", "A" * 64, "a" * 63, "a" * 65, "a" * 64 + "%0A"]


def refused_paths(root: str) -> list[str]:
    out = [f"/maps?against={c}" for c in BAD_COMMITS]
    out += [f"/maps/structural/{root}?against={c}" for c in BAD_COMMITS]
    out += [f"/maps/structural?source_revision={c}" for c in BAD_COMMITS]
    out += [f"/maps/structural/{r}" for r in BAD_ROOTS] + [f"/maps/structural/{r}/inputs" for r in BAD_ROOTS]
    out += [f"/maps/diff?a={r}&b={root}" for r in BAD_ROOTS] + [f"/maps/diff?a={root}&b={r}" for r in BAD_ROOTS]
    out += [f"/maps/diff?a={root}", f"/maps/diff?b={root}", "/maps/diff",
            f"/maps/structural/{root}?section=bogus", f"/maps/structural/{root}?section=",
            "/maps/structural?limit=0", "/maps/structural?limit=51", "/maps/structural?limit=x",
            f"/maps/structural/{root}/inputs?limit=0", f"/maps/structural/{root}/inputs?limit=251",
            "/maps?bogus=1", "/maps/structural?section=directories", f"/maps/diff?a={root}&b={root}&c=1",
            f"/maps?against={'a' * 40}&against={'b' * 40}"]
    return out


def test_malformed_ids_commits_sections_and_limits_are_refused_before_any_file_or_git_access(world, monkeypatch):
    opened: list[str] = []
    real_open, real_os_open = io.open, os.open

    def counting_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    def counting_os_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(path))
        return real_os_open(path, *args, **kwargs)

    world.client.data("/maps")  # warm
    for path in refused_paths(world.selected):
        opened.clear()
        profile.start()
        monkeypatch.setattr(builtins, "open", counting_open)
        monkeypatch.setattr(io, "open", counting_open)
        monkeypatch.setattr(os, "open", counting_os_open)
        try:
            status, headers, raw = world.client.get(path)
        finally:
            monkeypatch.undo()
            counts = (profile.stop() or {}).get("counts", {})
        assert status == 400, (path, status, raw[:200])
        assert json.loads(raw)["code"] == "INVALID_REQUEST", path
        assert counts.get("git", 0) == 0, (path, counts)
        assert not [f for f in opened if ".aew" in f], (path, opened)


# ---------------------------------------------------------------------------------------------- lock-free, writes


def test_every_maps_route_answers_while_the_control_and_registry_locks_are_held(world):
    with FileLock(world.p.root / ".aew" / LOCK_REL, timeout=5), \
            FileLock(world.p.root / ".aew" / MS.LOCK_REL, timeout=5):
        for route in MAPS:
            status, _, raw = world.client.get(concrete(route, world.selected, world.older), timeout=30)
            assert status == 200, (route, raw[:200])


def test_a_warm_read_spawns_only_the_partial_clone_check_and_the_head_resolve(world):
    """n7: a warm ``/maps`` and a warm detail each run ``git config`` (the partial-clone check) and ``git
    rev-parse`` (the head), nothing else, in the fixture's full clone."""
    for path in ("/maps", f"/maps/structural/{world.selected}"):
        world.client.data(path)  # warm the caches
        profile.start()
        try:
            world.client.data(path)
        finally:
            counts = (profile.stop() or {}).get("counts", {})
        git_counts = {k: v for k, v in counts.items() if k.startswith("git")}
        assert git_counts == {"git": 2, "git:config": 1, "git:rev-parse": 1}, (path, git_counts)


# ---------------------------------------------------------------------------------------------- state fixtures


@pytest.fixture
def lab(tmp_path) -> Iterator[tuple[Project, Path]]:
    """A fresh project for a test that changes its maps or its repository."""
    p = sample_project(tmp_path)
    yield p, tmp_path


def test_no_registry_is_none_never_an_empty_map_and_nothing_is_created(lab):
    p, _ = lab
    with served(p) as client:
        for route in MAPS:
            client.get(concrete(route, "0" * 64, "1" * 64))
        data = client.data("/maps")
        assert data["registry"]["state"] == "NONE" and data["map_revision"] == "none:0"
        assert data["structural"] == {"state": "UNAVAILABLE", "reasons": [{"code": "MAP_NONE",
                                                                            "message": REASONS["MAP_NONE"]}],
                                      "summary": None, "freshness": None}
        assert data["architecture"] is None and data["stored"] == {"count": 0}
        assert client.data("/maps/structural")["items"] == []
        client.error(f"/maps/structural/{'0' * 64}", 404, "NOT_FOUND")
        client.error(f"/maps/diff?a={'0' * 64}&b={'1' * 64}", 404, "NOT_FOUND")
    assert not maps_dir(p).exists()  # no maps route creates local/maps/


def test_an_invalid_registry_is_a_state_malformed_oversized_or_not_a_regular_file(lab):
    p, _ = lab
    root = generate(p, select=True)
    registry = maps_dir(p) / "registry.json"
    original = registry.read_bytes()
    with served(p) as client:
        cases = [b"{not json", json.dumps({"schema": "aew/map-registry/v1"}).encode(),
                 original + b" " * (65 * 1024)]
        for content in cases:
            registry.write_bytes(content)
            data = client.data("/maps")
            assert data["registry"]["state"] == "INVALID" and data["map_revision"] is None, content[:40]
            assert data["structural"]["state"] == "UNAVAILABLE"
            assert data["structural"]["reasons"][0]["code"] == "MAP_REGISTRY_INVALID"
            assert client.data("/maps/structural")["items"][0]["selected"] is False
        registry.unlink()
        registry.mkdir()
        assert client.data("/maps")["registry"]["state"] == "INVALID"
        registry.rmdir()
        registry.write_bytes(original)
        assert client.data("/maps")["structural"]["summary"]["root"] == root


def test_a_missing_or_corrupt_selected_map_is_data_and_by_root_a_404_or_a_422(lab):
    p, _ = lab
    root = generate(p, select=True)
    path = artifact(p, root)
    good = path.read_bytes()
    with served(p) as client:
        path.write_bytes(good.replace(b'"structural"', b'"structuraX"', 1))
        data = client.data("/maps")["structural"]
        assert data["state"] == "UNAVAILABLE" and data["reasons"][0]["code"] == "MAP_CORRUPT"
        assert data["summary"]["status"] == "CORRUPT" and data["summary"]["source_revision"] is None
        body = client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
        assert "hash_mismatch" in body["message"] and ".aew" not in body["message"]
        client.error(f"/maps/structural/{root}/inputs", 422, "MAP_ARTIFACT_CORRUPT")
        client.error(f"/maps/diff?a={root}&b={root}", 422, "MAP_ARTIFACT_CORRUPT")
        listed = client.data("/maps/structural")["items"]
        assert [(i["root"], i["status"], i["selected"]) for i in listed] == [(root, "CORRUPT", True)]
        path.unlink()
        data = client.data("/maps")["structural"]
        assert data["reasons"][0]["code"] == "MAP_MISSING" and data["summary"] is None
        client.error(f"/maps/structural/{root}", 404, "NOT_FOUND")
        path.write_bytes(good)
        st = os.lstat(path)  # a new mtime, whatever the clock's tick (the same-tick case is the next test's)
        os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        assert client.data("/maps")["structural"]["state"] == "AVAILABLE"


def test_a_repaired_map_reads_available_even_when_its_inode_size_and_mtime_repeat(lab):
    """Review of #178, finding A: a same-size artifact unlinked and written again within one timestamp tick keeps
    its device, inode (reused at once on xfs and ext4), size and ``mtime``. The tick is simulated by restoring the
    corrupt file's ``mtime``: the repaired map must read AVAILABLE (a corrupt verdict is never cached, and the
    identity carries ``ctime``, which a restore cannot set)."""
    p, _ = lab
    root = generate(p, select=True)
    path = artifact(p, root)
    good = path.read_bytes()
    with served(p) as client:
        path.write_bytes(good.replace(b'"structural"', b'"structuraX"', 1))  # the same size
        corrupt = os.lstat(path)
        assert client.data("/maps")["structural"]["reasons"][0]["code"] == "MAP_CORRUPT"
        client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
        path.unlink()
        path.write_bytes(good)
        os.utime(path, ns=(corrupt.st_atime_ns, corrupt.st_mtime_ns))  # the same tick
        assert os.lstat(path).st_size == corrupt.st_size
        assert client.data("/maps")["structural"]["state"] == "AVAILABLE"
        assert client.data(f"/maps/structural/{root}")["summary"]["status"] == "AVAILABLE"


def test_a_float_in_a_record_is_not_canonical_and_refused(lab):
    p, _ = lab
    root = generate(p)
    record = record_of(p, root)
    record["limits"]["tracked_paths"]["seen"] = 1.5
    body = {k: v for k, v in record.items() if k != "artifact_sha256"}
    raw = json.dumps({**body, "artifact_sha256": "f" * 64}, sort_keys=True, separators=(",", ":")).encode()
    target = artifact(p, "f" * 64)
    target.write_bytes(raw)
    with served(p) as client:
        body = client.error(f"/maps/structural/{'f' * 64}", 422, "MAP_ARTIFACT_CORRUPT")
        assert "not_canonical" in body["message"] or "hash_mismatch" in body["message"]


def test_an_oversized_or_linked_artifact_is_refused_and_never_read_past_the_cap(lab, monkeypatch):
    p, _ = lab
    root = generate(p, select=True)
    path = artifact(p, root)
    good = path.read_bytes()
    reads: list[int] = []
    real_read = os.read

    def counting_read(fd: int, n: int) -> bytes:
        reads.append(n)
        return real_read(fd, n)

    with served(p) as client:
        with open(path, "wb") as fh:  # 17 MiB: past the dashboard's bound
            fh.truncate(17 << 20)
        monkeypatch.setattr(os, "read", counting_read)
        body = client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
        assert "too_large" in body["message"]
        data = client.data("/maps")["structural"]
        assert data["state"] == "UNAVAILABLE" and "too_large" in data["reasons"][0]["message"]
        monkeypatch.undo()
        assert sum(reads) <= MS.MAP_FILE_MAX + 1
        path.write_bytes(good)
        if POSIX:
            big = p.root / "big.bin"
            with open(big, "wb") as fh:
                fh.truncate(17 << 20)
            path.unlink()
            path.symlink_to(big)
            body = client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
            assert "not_a_file" in body["message"]
            assert "not_a_file" in client.data("/maps")["structural"]["reasons"][0]["message"]


@pytest.mark.skipif(not POSIX, reason="FIFOs are POSIX")
def test_a_fifo_artifact_or_registry_is_never_opened_and_a_swap_race_does_not_block(lab, monkeypatch):
    p, _ = lab
    root = generate(p, select=True)
    path = artifact(p, root)
    good = path.read_bytes()
    with served(p) as client:
        path.unlink()
        os.mkfifo(path)
        started = time.monotonic()
        client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
        assert client.data("/maps")["structural"]["state"] == "UNAVAILABLE"
        assert time.monotonic() - started < 10
        path.unlink()
        path.write_bytes(good)

        # n6: a FIFO swapped in between the lstat and the open: the open returns at once and fstat refuses it
        real_open = os.open

        def swapping_open(target: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if str(target).endswith(f"{root}.json") and not os.path.exists(str(target) + ".swapped"):
                Path(str(target) + ".swapped").touch()
                os.unlink(target)
                os.mkfifo(target)
            return real_open(target, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", swapping_open)
        started = time.monotonic()
        body = client.error(f"/maps/structural/{root}", 422, "MAP_ARTIFACT_CORRUPT")
        assert "not_a_file" in body["message"] and time.monotonic() - started < 10
        monkeypatch.undo()

        registry = maps_dir(p) / "registry.json"
        saved = registry.read_bytes()
        registry.write_bytes(saved.rstrip() + b"\n\n")  # a new identity, so the reader opens it again

        def swapping_registry(target: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            if str(target).endswith("registry.json") and not os.path.exists(str(target) + ".swapped"):
                Path(str(target) + ".swapped").touch()
                os.unlink(target)
                os.mkfifo(target)
            return real_open(target, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", swapping_registry)
        started = time.monotonic()
        assert client.data("/maps")["registry"]["state"] == "INVALID"
        assert time.monotonic() - started < 10
        monkeypatch.undo()
        registry.unlink()
        registry.write_bytes(saved)


def test_freshness_stale_on_paths_on_metadata_and_on_the_generator_and_unknown_when_git_hangs(lab, monkeypatch):
    p, _ = lab
    add_metadata(p)
    root = generate(p, select=True)
    with served(p) as client:
        assert client.data("/maps")["structural"]["freshness"]["status"] == "CURRENT"
        commit_file(p, "notes/a.txt", "a\n", "add a path")
        fresh = client.data("/maps")["structural"]["freshness"]
        assert fresh["status"] == "STALE" and [r["code"] for r in fresh["reasons"]] == ["MAP_STALE_PATH_LISTING"]
        commit_file(p, "pyproject.toml", PYPROJECT + "# edited\n", "edit a metadata input")
        fresh = client.data(f"/maps/structural/{root}")["freshness"]
        assert "MAP_STALE_METADATA" in [r["code"] for r in fresh["reasons"]]
        assert fresh["metadata_paths"] == ["pyproject.toml"] and fresh["metadata_paths_omitted"] == 0
        identity = {"name": "structural", "version": 99, "ruleset_sha256": "0" * 64}
        monkeypatch.setattr(P.MSV, "identity", lambda: identity)
        fresh = client.data("/maps")["structural"]["freshness"]
        assert [r["code"] for r in fresh["reasons"]] == ["MAP_STALE_GENERATOR"]
        monkeypatch.undo()

        MF.clear_cache()
        monkeypatch.setattr(P, "MAPS_GIT_TIMEOUT_S", 0.5)
        real_run = subprocess.run

        def hanging(args: Any, *a: Any, **kw: Any) -> Any:
            if isinstance(args, list) and "rev-parse" in args and kw.get("timeout") == 0.5:
                raise subprocess.TimeoutExpired(args, 0.5)
            return real_run(args, *a, **kw)

        monkeypatch.setattr(aew_git.subprocess, "run", hanging)
        started = time.monotonic()
        fresh = client.data("/maps")["structural"]["freshness"]
        assert fresh["status"] == "UNKNOWN" and "did not answer" in fresh["reasons"][0]["message"]
        assert time.monotonic() - started < 10


def test_the_architecture_reference_stale_unavailable_none_and_a_hanging_git(lab, monkeypatch):
    p, tmp = lab
    with served(p) as client:
        assert client.data("/maps")["architecture"] is None
        discovery = complete_investigation(p, create_investigation(p, tmp, title="Survey"))
        p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", map_rev(p), "--json")
        arch = client.data("/maps")["architecture"]
        assert arch["freshness"]["status"] == "CURRENT" and arch["freshness"]["reasons"] == []
        assert client.data("/maps")["structural"]["reasons"][0]["code"] == "MAP_NONE"  # still no structural map
        commit_file(p, "calc/core.py", "def add(a, b):\n    return b + a\n", "change calc")
        arch = client.data("/maps")["architecture"]
        assert arch["freshness"]["status"] == "STALE" and arch["freshness"]["changed_paths"] == ["calc/core.py"]
        assert arch["freshness"]["reasons"][0]["code"] == "ARCHITECTURE_STALE"

        monkeypatch.setattr(P, "MAPS_GIT_TIMEOUT_S", 0.5)
        real_run = subprocess.run

        def hanging(args: Any, *a: Any, **kw: Any) -> Any:
            if isinstance(args, list) and "merge-base" in args:
                raise subprocess.TimeoutExpired(args, 0.5)
            return real_run(args, *a, **kw)

        monkeypatch.setattr(aew_git.subprocess, "run", hanging)
        commit_file(p, "calc/core.py", "def add(a, b):\n    return a + b\n", "change calc back")
        arch = client.data("/maps")["architecture"]
        assert arch["freshness"]["status"] == "UNKNOWN"
        assert arch["freshness"]["reasons"][0]["code"] == "ARCHITECTURE_UNKNOWN"
        monkeypatch.undo()

        registry = maps_dir(p) / "registry.json"
        data = json.loads(registry.read_text(encoding="utf-8"))
        data["selected"]["architecture"]["evidence_id"] = "INV-9999-gone-1"
        registry.write_text(json.dumps(data), encoding="utf-8")
        arch = client.data("/maps")["architecture"]
        assert arch["freshness"]["status"] == "UNAVAILABLE"
        assert arch["freshness"]["reasons"][0]["code"] == "ARCHITECTURE_UNAVAILABLE"


@pytest.mark.parametrize("failure", [IntegrityError("simulated: a later commit replaced the tail"),
                                     LockTimeout("simulated: the history index is busy")],
                         ids=["history_moved", "index_busy"])
def test_archived_architecture_evidence_never_takes_the_control_lock_or_waits_on_the_index(lab, monkeypatch,
                                                                                           failure):
    """Review of #178, finding 1: the evidence is archived (a finished investigation), nothing syncs the history index
    first, the control lock is held, and the index sync meets a moved history or a busy index. ``/maps`` neither
    re-reads state under the lock nor waits: the reference is ``UNKNOWN`` ("read again later"), never ``UNAVAILABLE``,
    and the next read, with the index free, answers."""
    p, tmp = lab
    discovery = complete_investigation(p, create_investigation(p, tmp, title="Survey"))
    p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", map_rev(p), "--json")
    with served(p) as client:
        engine = client.server.engine
        engine.store.lock_timeout = 30.0  # a lookup that took the lock would wait this long, then fail
        engine.archive._synced = None  # nothing synced: the lookup must sync the index itself
        real_sync, real_read = HI.HistoryIndex.sync, engine.store.read
        calls = {"sync": 0, "read": 0}

        def failing_once(self: Any, root: Any, **kwargs: Any) -> Any:
            calls["sync"] += 1
            if calls["sync"] == 1:
                raise failure
            return real_sync(self, root, **kwargs)

        def counted_read(*args: Any, **kwargs: Any) -> Any:
            calls["read"] += 1
            return real_read(*args, **kwargs)

        monkeypatch.setattr(HI.HistoryIndex, "sync", failing_once)
        monkeypatch.setattr(engine.store, "read", counted_read)
        with FileLock(p.root / ".aew" / LOCK_REL, timeout=5):
            started = time.monotonic()
            status, _, raw = client.get("/maps", timeout=120)
            took = time.monotonic() - started
            assert status == 200, raw[:300]
            arch = json.loads(raw)["data"]["architecture"]
            assert took < 10, took  # neither the 30 s control lock nor the 30 s index wait
            assert calls["read"] == 0  # no state re-read: it would take the control lock
            assert arch["evidence"]["id"] == discovery and arch["freshness"]["status"] == "UNKNOWN"
            assert arch["freshness"]["reasons"][0]["code"] == "ARCHITECTURE_UNKNOWN"
            assert "read again later" in arch["freshness"]["reasons"][0]["message"]
            again = client.data("/maps")["architecture"]["freshness"]  # the lock still held, the index free
            assert again["status"] == "CURRENT" and calls["read"] == 0


def test_a_locked_index_on_a_warm_read_is_unknown_not_a_500(lab):
    """Review of #178, finding B: once a plain reader has synced and kept the history index, the archived lookup
    queries it without a sync; another process holding it ``BEGIN EXCLUSIVE`` then raises SQLite's own error after the
    2 s bound, which is ``ARCHITECTURE_UNKNOWN`` ("read again later"), with the structural map still served."""
    p, tmp = lab
    generate(p, select=True)
    discovery = complete_investigation(p, create_investigation(p, tmp, title="Survey"))
    p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", map_rev(p), "--json")
    with served(p) as client:
        assert client.data("/maps")["architecture"]["freshness"]["status"] == "CURRENT"
        assert client.get("/history")[0] == 200  # a plain reader syncs and keeps the index
        conn = sqlite3.connect(p.root / ".aew" / HI.INDEX_REL, timeout=1, isolation_level=None)
        conn.execute("BEGIN EXCLUSIVE")
        try:
            started = time.monotonic()
            status, _, raw = client.get("/maps", timeout=120)
            took = time.monotonic() - started
        finally:
            conn.execute("ROLLBACK")
            conn.close()
        assert status == 200, raw[:300]
        data = json.loads(raw)["data"]
        assert took < 10, took
        assert data["structural"]["state"] == "AVAILABLE"
        arch = data["architecture"]["freshness"]
        assert arch["status"] == "UNKNOWN" and arch["reasons"][0]["code"] == "ARCHITECTURE_UNKNOWN"
        assert "read again later" in arch["reasons"][0]["message"]
        assert client.data("/maps")["architecture"]["freshness"]["status"] == "CURRENT"  # the index free again


def test_damaged_history_is_unavailable_not_busy(lab, monkeypatch):
    """Review of #178, finding C: only the sync's race and a busy index are "read again later". A missing or altered
    history record is damage: the reference stays ``ARCHITECTURE_UNAVAILABLE``, as before the lock-free mode."""
    p, tmp = lab
    discovery = complete_investigation(p, create_investigation(p, tmp, title="Survey"))
    p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", map_rev(p), "--json")
    with served(p) as client:
        assert client.data("/maps")["architecture"]["freshness"]["status"] == "CURRENT"
        engine = client.server.engine
        engine.archive._synced = None

        def damaged(*args: Any, **kwargs: Any) -> Any:
            raise IntegrityError("history record work/T-0001/archive.yaml is missing")

        monkeypatch.setattr(engine.archive, "bundle", damaged)
        arch = client.data("/maps")["architecture"]["freshness"]
        assert arch["status"] == "UNAVAILABLE" and arch["reasons"][0]["code"] == "ARCHITECTURE_UNAVAILABLE"
        assert "read again later" not in json.dumps(arch)


def test_a_lock_free_reader_bounds_the_index_wait_and_leaves_the_cli_readers_alone(lab):
    """The lock-free mode is per thread and per block: inside it a sync uses the short bound and is not kept for
    other readers; outside it the archive reads exactly as before (the 30 s default)."""
    p, tmp = lab
    complete_investigation(p, create_investigation(p, tmp, title="Survey"))
    engine = Engine.discover(p.root)
    state = engine.store.read()
    with engine.archive.lockfree_reads(P.ARCHIVE_WAIT_S):
        bounded = engine.archive.index(state)
    assert bounded.timeout == P.ARCHIVE_WAIT_S and engine.archive._synced is None
    plain = engine.archive.index(state)
    assert plain.timeout == 30.0 and engine.archive._synced is not None
    with engine.archive.lockfree_reads(P.ARCHIVE_WAIT_S):
        reused = engine.archive.index(state)
    assert reused.timeout == P.ARCHIVE_WAIT_S and engine.archive.index(state).timeout == 30.0


def test_a_planted_evidence_id_that_names_a_path_is_unavailable_and_opens_nothing_outside(lab, monkeypatch):
    """m4: the registry allows any 1 to 64 characters; ``../../x`` is refused before any path is built."""
    p, _ = lab
    generate(p, select=True)
    registry = maps_dir(p) / "registry.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["selected"]["architecture"] = {"evidence_id": "../../x"}
    registry.write_text(json.dumps(data), encoding="utf-8")
    seen: list[str] = []
    real_stat = Path.stat

    def watching(self: Path, *a: Any, **kw: Any) -> Any:
        seen.append(str(self))
        return real_stat(self, *a, **kw)

    with served(p) as client:
        monkeypatch.setattr(Path, "stat", watching)
        status, _, raw = client.get("/maps")
        monkeypatch.undo()
    assert status == 200
    arch = json.loads(raw)["data"]["architecture"]
    assert arch["evidence"] is None and arch["freshness"]["status"] == "UNAVAILABLE"
    assert not [s for s in seen if "x.md" in s or s.endswith("x")]


def test_a_selection_between_two_requests_is_seen_whole(lab):
    p, _ = lab
    first = generate(p, select=True)
    with served(p) as client:
        assert client.data("/maps")["structural"]["summary"]["root"] == first
        commit_file(p, "notes/b.txt", "b\n", "a path")
        second = generate(p, select=True)
        data = client.data("/maps")
        assert data["structural"]["summary"]["root"] == second and data["map_revision"].endswith(":2")
        assert {i["root"]: i["selected"] for i in client.data("/maps/structural")["items"]} == {
            first: False, second: True}


def test_no_maps_route_writes_under_the_project(lab, monkeypatch):
    p, _ = lab
    root = generate(p, select=True)
    aew = str(p.root / ".aew")
    real_open, real_os_open = io.open, os.open

    def refuse_writes(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if str(file).startswith(aew) and any(c in mode for c in "wax+"):
            raise AssertionError(f"a maps route wrote {file}")
        return real_open(file, mode, *args, **kwargs)

    def refuse_os_writes(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if str(path).startswith(aew) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND):
            raise AssertionError(f"a maps route opened {path} for writing")
        return real_os_open(path, flags, *args, **kwargs)

    with served(p) as client:
        client.get("/history")  # the history index, which the archived evidence lookup reads, is synced first
        monkeypatch.setattr(builtins, "open", refuse_writes)
        monkeypatch.setattr(io, "open", refuse_writes)
        monkeypatch.setattr(os, "open", refuse_os_writes)
        try:
            for route in MAPS:
                status, _, raw = client.get(concrete(route, root, root))
                assert status == 200, (route, raw[:300])
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------------------------- the scan bound


def test_past_the_scan_bound_the_page_says_so_and_the_cursor_continues(lab, monkeypatch):
    p, _ = lab
    roots = {generate(p)}
    for n in range(4):
        commit_file(p, f"notes/{n}.txt", f"{n}\n", f"path {n}")
        roots.add(generate(p))
    head = git("rev-parse", "HEAD", cwd=p.root)
    monkeypatch.setattr(P, "SCAN_MAPS", 3)
    with served(p) as client:
        first = client.data("/maps/structural?limit=50")
        assert len(first["items"]) == 3 and first["next_cursor"]
        assert first["scan_incomplete"]["examined"] == 3 and first["scan_incomplete"]["stored"] == 5
        assert first["scan_incomplete"]["reasons"][0]["code"] == "MAP_SCAN_LIMIT"
        second = client.data(f"/maps/structural?limit=50&cursor={first['next_cursor']}")
        assert second["next_cursor"] is None and second["scan_incomplete"] is None
        assert sorted(i["root"] for i in first["items"] + second["items"]) == sorted(roots)
        found, cursor = [], None
        while True:
            page = client.data(f"/maps/structural?source_revision={head}"
                               + (f"&cursor={cursor}" if cursor else ""))
            found += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
            assert page["scan_incomplete"]["reasons"][0]["code"] == "MAP_SCAN_LIMIT"
        assert [i["source_revision"] for i in found] == [head]
    monkeypatch.setattr(P, "SCAN_BYTES", 1)
    with served(p) as cold:  # a new server: nothing cached, so every map must be read
        limited = cold.data("/maps/structural?limit=50")
        assert limited["scan_incomplete"]["examined"] == 1 and len(limited["items"]) == 1  # the first is always read
        assert limited["next_cursor"]


# ---------------------------------------------------------------------------------------------- the diff


def grow(record: dict[str, Any], n: int, *, languages: int = 0) -> dict[str, Any]:
    """``record`` with ``n`` LFS pointers (and a row's language list), past every cap: a planted map."""
    out = copy.deepcopy(record)
    lo = out["sections"]["limits_and_omissions"]
    lo["lfs_pointers"] = [f"{i:x}" for i in range(n)]  # short names: a million stay below the 16 MiB bound
    if languages:
        out["sections"]["directories"]["rows"][0]["languages"] = [f"{i:x}" for i in range(languages)]
    return out


def test_a_difference_only_past_a_cap_is_beyond_cap_and_a_missing_operand_is_404(lab):
    p, _ = lab
    record = record_of(p, generate(p))
    a = plant(p, grow(record, 150))
    b_record = grow(record, 150)
    b_record["sections"]["limits_and_omissions"]["lfs_pointers"][140] = "lfs/changed.bin"
    b = plant(p, b_record)
    with served(p) as client:
        data = client.data(f"/maps/diff?a={a}&b={b}")
        lo = data["sections"]["limits_and_omissions"]
        assert lo["changed"] is True and lo["beyond_cap"] is True
        assert lo["lfs_pointers"] == {"added": [], "removed": []}
        assert all(not s["changed"] for n, s in data["sections"].items() if n != "limits_and_omissions")
        client.error(f"/maps/diff?a={a}&b={'0' * 64}", 404, "NOT_FOUND")
        client.error(f"/maps/diff?a={'0' * 64}&b={b}", 404, "NOT_FOUND")


def test_the_diff_is_linear_on_planted_lists_of_a_million_items(lab, monkeypatch):
    """n3: each list is cut to its cap before anything is compared, and the comparison is by sets of canonical
    JSON: the instrumented ``canon`` runs once per kept item, never pairwise."""
    p, _ = lab
    generated = generate(p)
    record = record_of(p, generated)
    big = plant(p, grow(record, 10**6, languages=6 * 10**5))
    record2 = grow(record, 10**6, languages=6 * 10**5)
    record2["sections"]["limits_and_omissions"]["lfs_pointers"][0] = "first"
    other = plant(p, record2)
    calls = []
    real_canon = MV.canon

    def counted(item: Any) -> str:
        calls.append(1)
        return real_canon(item)

    with served(p) as client:
        monkeypatch.setattr(MV, "canon", counted)
        for a, b in ((generated, big), (big, other)):
            calls.clear()
            started = time.monotonic()
            data = client.data(f"/maps/diff?a={a}&b={b}")
            assert time.monotonic() - started < 60  # a hang guard, not a benchmark
            caps = sum(2 * cap for section in MV.SECTIONS.values() for cap, _ in section.lists.values())
            assert len(calls) <= caps, len(calls)
            assert data["sections"]["limits_and_omissions"]["changed"] is True
        removed = data["sections"]["limits_and_omissions"]["lfs_pointers"]
        assert removed == {"added": ["first"], "removed": ["0"]}


# ---------------------------------------------------------------------------------------------- size


def hostile_project(tmp: Path) -> tuple[Project, str]:
    """A generated map at the generator's caps, with hostile names: 4-byte characters, backslashes, bidi,
    zero-width, ESC, ``<script>``, Markdown, a fake cut marker, and a credential-shaped package.json entry. The names
    go straight into git's index (``update-index --index-info``), since no checkout can hold all of them on every
    platform; the map is generated from the commit's objects, never from the checkout."""
    p = sample_project(tmp)
    long_dir = "\U0001F600" * 40 + "\\" * 30
    names = {f"{long_dir}/d{i:03d}/f.py": "x\n" for i in range(210)}
    names.update({f"bidi\u202e{i}/z\u200b/e\x1b[31m/f.py": "x\n" for i in range(5)})
    names["<script>alert(1)</script>/**bold**/f.py"] = "x\n"
    names["fake \\[cut] marker/f.py"] = "x\n"
    secret = "aew1." + "tk_" + "0123456789abcdef" + "." + "A" * 43  # credential-shaped, made up
    names["package.json"] = json.dumps({"name": "calc", "bin": {"tool": secret}, "main": "\U0001F600" * 300,
                                        "scripts": {"test": secret}})
    names.update({f"ext/f.x{i:02d}": "x\n" for i in range(30)})
    lines = []
    for rel, text in names.items():
        oid = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=p.root, input=text.encode("utf-8"),
                             capture_output=True, check=True, creationflags=NO_WINDOW).stdout.decode().strip()
        lines.append(f"100644 {oid}\t{rel}".encode())
    lax = ["git", "-c", "core.protectNTFS=false"]  # names a Windows checkout refuses: they never reach a checkout
    subprocess.run([*lax, "update-index", "--add", "-z", "--index-info"], cwd=p.root,
                   input=b"\0".join(lines) + b"\0", capture_output=True, check=True, creationflags=NO_WINDOW)
    subprocess.run([*lax, "commit", "-q", "-m", "hostile names"], cwd=p.root, capture_output=True, check=True,
                   creationflags=NO_WINDOW)
    return p, generate(p, select=True)


def planted_worst_case(record: dict[str, Any]) -> dict[str, Any]:
    """Every allowlisted field of every item filled at its maximum (p1, n4): 4 KiB repository strings of 4-byte
    characters, invalid or valid vocabulary, wrong types and 4,300-digit integers wherever a number goes."""
    # Every repository-derived string is far past the 512-byte cut. Not 4 KiB each, as the plan's sketch had it: the
    # artifact's canonical JSON writes a 4-byte character as a 12-byte escape, and 1,920 strings of 4 KiB would put
    # the planted map past the 16 MiB bound, where it is refused before it is read. The cut is the same either way.
    long = "\U0001F600" * 200  # 800 bytes of UTF-8
    langs = [f"{n:x}" for n in range(10**4)]
    huge = int("9" * 4300)
    wrong = [[1], {"a": 1}, "x" * 4096, True, -1, huge]
    out = copy.deepcopy(record)
    s = out["sections"]
    rows = []
    for i in range(200):
        row = {"path": long + str(i), "depth": wrong[i % 6], "files": wrong[(i + 1) % 6],
               "languages": ["Python", "bogus" * 10] + (langs if i < 40 else langs[:100]),
               "label": "source" if i % 2 else "x" * 4096, "hostile key": "x" * 4096}
        rows.append(row)
    s["directories"] = {"max_depth": huge, "rows": rows, "rows_total": huge, "rows_omitted": -1,
                        "submodules": [{"path": long, "object": "z" * 40}] * 200, "submodules_omitted": huge,
                        "extra": [1, 2]}
    s["languages"] = {"counts": {**{f"L{n}": n for n in range(150)}, "Python": huge, "C": 3},
                      "unknown_files": huge, "unknown_extensions": [{"extension": long, "files": huge}] * 20,
                      "unknown_extensions_omitted": 0}
    s["build_descriptors"] = {"items": [{"path": long, "kind": "python", "status": "parsed"}] * 200, "omitted": 0}
    s["entry_point_candidates"] = {"items": [{"label": "declared", "path": long, "name": long, "target": long,
                                              "rule": "main.py"}] * 100, "omitted": 0}
    s["test_candidates"] = {"items": [{"kind": "directory", "path": long, "pattern": long, "files": huge,
                                       "runner": "pytest", "source": "convention"}] * 100, "omitted": 0}
    s["generated_and_vendor"] = {"items": [{"kind": "generated", "source": "convention", "pattern": long,
                                            "files": huge, "attributes_file": long}] * 200, "omitted": 0}
    s["semantic_prerequisites"] = {"items": [{"path": long, "kind": "mypy", "source": "declared"}] * 100,
                                   "omitted": 0}
    s["limits_and_omissions"] = {
        "caps_hit": [{"section": "directories", "field": "rows_omitted", "limit": huge, "omitted": huge}] * 20,
        "parse_failures": [{"path": long, "code": "invalid_json"}] * 100, "parse_failures_omitted": 0,
        "unsupported": [{"path": long, "reason": "symlink"}] * 100, "unsupported_omitted": 0,
        "lfs_pointers": [long] * 100, "lfs_pointers_omitted": 0, "metadata_unread": {"a": 1},
        "non_utf8_names": 0, "symlinks": 0, "submodules": 0, "unknown_extension_files": huge}
    out["limits"] = {"tracked_paths": {"seen": 1, "capped": False, "extra": 1},
                     "metadata_bytes": {"read": huge, "capped": False}, "metadata_blob_bytes": {"limit": 1}}
    out["inputs"]["metadata"] = [{"path": long + f"{i:04d}", "git_oid": "a" * 40, "size": huge, "read": True,
                                  "sha256": "b" * 64} for i in range(300)]
    return out


CONTROL = frozenset({"Cc", "Cf", "Zl", "Zp"})


def walk(value: Any) -> Iterator[Any]:
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v)
    else:
        yield value


def assert_bounded(body: dict[str, Any]) -> None:
    for value in walk(body):
        if isinstance(value, str):
            assert not any(unicodedata.category(c) in CONTROL for c in value), repr(value[:80])
            assert len(json.dumps(value, ensure_ascii=False).encode("utf-8")) <= MV.TEXT_BYTES + len(MV.MARKER) + 1
        elif isinstance(value, bool) or value is None:
            pass
        else:
            assert type(value) is int and 0 <= value < 2**53, value
    text = json.dumps(body)
    assert "bogus" not in text and "hostile key" not in text and not CREDENTIAL_RE.search(text)


CEILINGS = {"/maps/structural/{root}": 2 << 20, "/maps/diff": 4 << 20, "/maps/structural/{root}/inputs": 256 << 10,
            "/maps/structural": 64 << 10, "/maps": 64 << 10}


def valid_maximal(record: dict[str, Any], tag: str) -> dict[str, Any]:
    """Review of #178, finding 2: every allowlisted field of every item at its maximum and valid, so nothing is dropped:
    every list at the API's cap, every row with the 20 longest language names, a count for every known language (at
    most 100), the longest vocabulary values, every repository string past the cut (backslashes: two serialized bytes
    each) and every number at ``2**53 - 1`` (``2**53 - 2`` for any tag but ``a``). ``tag`` makes two such maps
    disjoint, item for item, and differ in every counter."""
    vocab = MV.vocabulary(MR.load())

    def longest(name: str, n: int = 1) -> list[str]:
        return sorted(vocab[name], key=lambda v: (-len(v.encode("utf-8")), v))[:n]

    def text(i: int) -> str:
        return f"{tag}{i}" + "\\" * 300

    big = 2**53 - 1 if tag == "a" else 2**53 - 2  # two maps: every counter differs between them
    langs = longest("language", 20)
    out = copy.deepcopy(record)
    s = out["sections"]
    s["directories"] = {"max_depth": big, "rows_total": big, "rows_omitted": big, "submodules_omitted": big,
                        "rows": [{"path": text(i), "depth": big, "files": big, "languages": langs,
                                  "label": longest("directory_label")[0]} for i in range(200)],
                        "submodules": [{"path": text(i), "object": "a" * 64} for i in range(200)]}
    s["languages"] = {"counts": dict.fromkeys(longest("language", 100), big), "unknown_files": big,
                      "unknown_extensions": [{"extension": text(i), "files": big} for i in range(20)],
                      "unknown_extensions_omitted": big}
    s["build_descriptors"] = {"items": [{"path": text(i), "kind": longest("build_kind")[0],
                                         "status": longest("build_status")[0]} for i in range(200)], "omitted": big}
    s["entry_point_candidates"] = {"items": [{"label": longest("entry_label")[0], "path": text(i), "name": text(i),
                                              "target": text(i), "rule": longest("entry_rule")[0]}
                                             for i in range(100)], "omitted": big}
    s["test_candidates"] = {"items": [{"kind": longest("test_kind")[0], "path": text(i), "pattern": text(i),
                                       "files": big, "runner": longest("test_runner")[0],
                                       "source": longest("test_source")[0]} for i in range(100)], "omitted": big}
    s["generated_and_vendor"] = {"items": [{"kind": longest("gv_kind")[0], "source": longest("gv_source")[0],
                                            "pattern": text(i), "files": big, "attributes_file": text(i)}
                                           for i in range(200)], "omitted": big}
    s["semantic_prerequisites"] = {"items": [{"path": text(i), "kind": longest("semantic_kind")[0],
                                              "source": longest("semantic_source")[0]} for i in range(100)],
                                   "omitted": big}
    s["limits_and_omissions"] = {
        "caps_hit": [{"section": longest("cap_section")[0], "field": longest("cap_field")[0], "limit": big,
                      "omitted": big} for _ in range(20)],
        "parse_failures": [{"path": text(i), "code": longest("parse_code")[0]} for i in range(100)],
        "parse_failures_omitted": big,
        "unsupported": [{"path": text(i), "reason": longest("unsupported_reason")[0]} for i in range(100)],
        "unsupported_omitted": big, "lfs_pointers": [text(i) for i in range(100)], "lfs_pointers_omitted": big,
        "metadata_unread": big, "non_utf8_names": big, "symlinks": big, "submodules": big,
        "unknown_extension_files": big}
    out["limits"] = {"tracked_paths": {"seen": big, "capped": True},
                     "metadata_bytes": {"read": big, "limit": big, "capped": True},
                     "metadata_blob_bytes": {"limit": big, "skipped": big}}
    return out


def test_the_ceilings_hold_on_a_valid_maximal_map_and_on_the_diff_of_two_disjoint_ones(tmp_path):
    """Review of #178, finding 2: the detail of a valid maximal map within 2 MiB, and the diff of two disjoint maximal
    maps (every list item added or removed, every counter changed) within 4 MiB, with nothing dropped, so the bound
    tested is the real worst case's."""
    p = sample_project(tmp_path)
    record = record_of(p, generate(p))
    a, b = plant(p, valid_maximal(record, "a")), plant(p, valid_maximal(record, "b"))
    with served(p) as client:
        status, _, raw = client.get(f"/maps/structural/{a}")
        assert status == 200, raw[:300]
        assert len(raw) <= CEILINGS["/maps/structural/{root}"], len(raw)
        print(f"valid maximal detail: {len(raw)} bytes")
        detail = json.loads(raw)
        assert_bounded(detail)
        sections = detail["data"]["sections"]
        assert all(s["dropped_items"] == 0 and s["dropped_fields"] == 0 for s in sections.values())
        assert detail["data"]["dropped_fields"] == 0
        every_language = min(MV.COUNTS_MAX, len(MV.vocabulary(MR.load())["language"]))  # the vocabulary has fewer
        assert len(sections["directories"]["rows"]) == 200 and len(sections["languages"]["counts"]) == every_language
        assert all(len(r["languages"]) == 20 for r in sections["directories"]["rows"])
        status, _, raw = client.get(f"/maps/diff?a={a}&b={b}")
        assert status == 200, raw[:300]
        assert len(raw) <= CEILINGS["/maps/diff"], len(raw)
        print(f"disjoint maximal diff: {len(raw)} bytes")
        diff = json.loads(raw)
        assert_bounded(diff)
        rows = diff["data"]["sections"]["directories"]["rows"]
        assert len(rows["added"]) == 200 and len(rows["removed"]) == 200  # disjoint: every kept item on both sides
        sections = diff["data"]["sections"]
        assert len(sections["languages"]["values"]) == 2 + every_language  # 2: unknown_files and its omitted count
        assert all(s["values"] for s in sections.values())  # every section has its counters changed


def test_every_response_stays_within_its_ceiling_on_a_generated_and_a_planted_worst_case(tmp_path):
    p, generated = hostile_project(tmp_path)
    planted = plant(p, planted_worst_case(record_of(p, generated)))
    with served(p) as client:
        for root, other in ((generated, planted), (planted, generated)):
            for route in MAPS:
                path = concrete(route, root, other)
                if route.endswith("/inputs"):
                    path += "?limit=250"
                status, _, raw = client.get(path)
                assert status == 200, (route, raw[:300])
                assert len(raw) <= CEILINGS[route], (route, len(raw))
                assert_bounded(json.loads(raw))
        gen = client.data(f"/maps/structural/{generated}")
        assert gen["cut_strings"] > 0 and gen["dropped_fields"] == 0
        assert all(s["dropped_items"] == 0 and s["dropped_fields"] == 0 for s in gen["sections"].values())
        paths = [r["path"] for r in gen["sections"]["directories"]["rows"]]
        assert any("\\x1b" in r and "\\xe2\\x80\\xae" in r for r in paths), paths[:8]  # inert, escaped as rendered
        assert any(r.startswith("<script>") for r in paths)  # data, never markup
        detail = client.data(f"/maps/structural/{planted}")
        sections = detail["sections"]
        rows = sections["directories"]
        assert len(rows["rows"]) == 100 and rows["dropped_items"] == 100  # the label "x" * 4096 drops half
        assert all(len(r["languages"]) <= 20 and r["languages_omitted"] in (10**4 + 2 - 20, 100 + 2 - 20)
                   for r in rows["rows"])
        assert all("depth" not in r or type(r["depth"]) is int for r in rows["rows"])
        assert "max_depth" not in rows and "rows_total" not in rows
        assert rows["dropped_fields"] >= 200 + 4  # a hostile key per row, the extra key and three counters
        assert sections["languages"]["counts_omitted"] == 52 and "Python" not in sections["languages"]["counts"]
        assert sections["limits_and_omissions"]["caps_hit"][0] == {"section": "directories", "field": "rows_omitted"}
        assert "metadata_unread" not in sections["limits_and_omissions"]
        assert detail["limits"] == {"tracked_paths": {"seen": 1, "capped": False}, "metadata_bytes": {"capped": False},
                                    "metadata_blob_bytes": {"limit": 1}}
        assert detail["dropped_fields"] == 2 and detail["cut_strings"] >= 1000
        page = client.data(f"/maps/structural/{planted}/inputs?limit=250")
        assert len(page["items"]) == 250 and page["dropped_fields"] == 250
        assert all("size" not in i and i["git_oid"] == "a" * 40 and i["path"].endswith(MV.MARKER)
                   for i in page["items"])


# ---------------------------------------------------------------------------------------------- conditional


def test_conditional_replays_and_what_changes_a_maps_validator(lab):
    p, _ = lab
    generate(p, select=True)
    with served(p) as client:
        def tag(path: str) -> str:
            status, headers, _ = client.get(path)
            assert status == 200
            return headers["etag"]

        before = tag("/maps")
        assert client.get("/maps", inm=before)[0] == 304
        assert client.get("/maps", inm=before, head=True)[0] == 304
        project_tag, work_tag = tag("/project"), tag("/work")
        commit_file(p, "notes/c.txt", "c\n", "a new head")  # the authoritative head moves
        after_commit = tag("/maps")
        assert after_commit != before
        generate(p, select=True)  # a selection
        after_select = tag("/maps")
        assert after_select != after_commit
        assert tag("/project") == project_tag and tag("/work") == work_tag  # 0.1.2 validators: a selection alone
        p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))  # an unrelated control commit
        after_audit = tag("/maps")
        assert after_audit != after_select
        registry = maps_dir(p) / "registry.json"
        registry.unlink()  # deleted and recreated: a new epoch
        generate(p, select=True)
        assert tag("/maps") != after_audit


def test_without_a_session_every_maps_route_is_401(lab):
    p, _ = lab
    gate = Gate()
    gate.closed = True
    with served(p, gate) as client:
        for route in MAPS:
            for head in (False, True):
                status, headers, raw = client.get(concrete(route, "0" * 64, "1" * 64), head=head)
                assert status == 401 and "etag" not in headers, route
                if not head:
                    assert json.loads(raw)["code"] == "SESSION_REQUIRED"


def test_the_reader_caches_are_bounded():
    cache: R.LRU[str, int] = R.LRU(3)
    for n in range(5):
        cache.put(str(n), n)
    assert len(cache) == 3 and cache.get("0") is None and cache.get("4") == 4
    sized: R.LRU[str, str] = R.LRU(10)
    sized.put("a", "x", 6)
    sized.put("b", "y", 6)
    assert sized.get("a") is None and sized.get("b") == "y"
    sized.put("c", "z", 11)  # larger than the whole cache: never kept
    assert sized.get("c") is None and sized.get("b") == "y"
    assert len(MF._cache) <= MF.CACHE_MAX
