"""F20.4: conditional requests against live projections (design note §4.12, R19; §5.3).

A project with an integrated (archived) Ticket and a Ticket that ran an implementer through the fake harness to its
end, so ``/runs`` carries a real run and its observed status. Every route is read over HTTP, conditionally and not,
GET and HEAD; the project is then changed three ways (a commit that changes projected fields, a commit that changes
only ``control_revision``, and telemetry alone at the same revision) and each change must be a ``200`` with a new
validator.

Every response passes through a client that checks the frontend's two diagnostics as it goes: a ``200`` never
shows an ETag it has seen before under a different revision, and a ``304`` never carries an ETag other than the one
the client sent.
"""

from __future__ import annotations

import http.client
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import (  # noqa: E402
    SUBTRACT_PATCH,
    create_planned_ticket,
    create_unit,
    integrate,
    plan_unit,
    sample_project,
    to_commit_ready,
)
from fake_harness import IMPL_REPORT, HarnessLab  # noqa: E402
from invariants import assert_control_invariants  # noqa: E402

from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard import reader as R  # noqa: E402
from aew.dashboard.server import DashboardServer, error_body  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.harness import contract as K  # noqa: E402
from aew.harness import runlog  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
IMPLEMENT = [{"do": "write", "files": SUBTRACT_PATCH}, {"do": "check", "id": "unit"},
             {"do": "submit", "kind": "implementation_report", "meta": IMPL_REPORT}]
# The headers every 200 and 304 of a read carry today (F20.5 adds the rest of R21's set to all responses).
COMMON = {"cache-control": "no-store", "x-content-type-options": "nosniff", "referrer-policy": "no-referrer"}


class Gate:
    """Test-only authenticator: open unless ``closed``, so the test can show a conditional request is still
    authenticated first. The product's authenticator is the operator session (F20.3)."""

    closed = False

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        return error_body("SESSION_REQUIRED") if self.closed else None


class Client:
    def __init__(self, port: int) -> None:
        self.port = port
        self.revision_of: dict[str, str] = {}  # every ETag seen on a 200, and the revision it came with

    def get(self, path: str, *, head: bool = False, inm: str | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            conn.request("HEAD" if head else "GET", f"/api/v1{path}",
                         headers={"If-None-Match": inm} if inm is not None else {})
            resp = conn.getresponse()
            raw = resp.read()
            headers = {k.lower(): v for k, v in resp.getheaders()}
        finally:
            conn.close()
        if resp.status == 304:  # diagnostic 2: a 304 never carries a validator the client did not send
            assert inm is not None and headers["etag"] in [m.strip() for m in inm.split(",")], (path, inm, headers)
            assert raw == b""
        if resp.status == 200 and not head:  # diagnostic 1: an ETag never stands for two revisions
            revision = json.loads(raw)["control_revision"]
            assert self.revision_of.setdefault(headers["etag"], revision) == revision, (path, headers["etag"])
        return resp.status, headers, raw

    def ok(self, path: str, inm: str | None = None) -> tuple[str, dict[str, Any]]:
        status, headers, raw = self.get(path, inm=inm)
        assert status == 200, (path, status, raw)
        body = json.loads(raw)
        route = CONTRACT_ROUTE(path)
        assert CONTRACT.violations(CONTRACT.response_schema(route), body) == []
        return headers["etag"], body


def CONTRACT_ROUTE(path: str) -> str:  # noqa: N802 (reads as the constant table it stands for)
    bare = path.split("?", 1)[0]
    if bare in CONTRACT.paths:
        return bare
    return "/" + bare.split("/")[1] + "/{id}"


class World:
    def __init__(self) -> None:
        self.lab: HarnessLab
        self.server: DashboardServer
        self.client: Client
        self.gate = Gate()
        self.paths: dict[str, str] = {}
        self.run = ""
        self.invocation = ""
        self.ticket = ""


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("conditional")
    w = World()
    w.lab = HarnessLab.create(sample_project(tmp), tmp)
    p = w.lab.project
    epic = create_unit(p, "epic", "Calculator", cls=1)
    plan_unit(p, tmp, epic)  # records a decision, for /knowledge/{id}
    done, _ = to_commit_ready(p, tmp, title="Add subtract()", extra=("--parent", epic))
    integrate(p, done)  # archived, for /history/{id}
    w.ticket = create_planned_ticket(p, tmp, title="Subtract again", extra=("--parent", epic))
    w.lab.script("default", IMPLEMENT)
    out = w.lab.lead("work", "assign", w.ticket, "--launch")
    w.run, w.invocation = out["launch"]["run"], out["invocation"]
    p.lead("work", "transition", w.ticket, "--to", "RUNNING")
    assert w.lab.wait(w.run)["status"] == K.ENDED_WITH_EVIDENCE
    w.server = DashboardServer(Engine.discover(p.root), authenticator=w.gate, validate_with=CONTRACT)
    w.server.start()
    w.client = Client(w.server.port)
    _, evidence = w.client.ok(f"/evidence?work={w.ticket}")
    _, knowledge = w.client.ok("/knowledge")
    assert evidence["data"]["items"] and knowledge["data"]["items"], "the world needs evidence and a decision"
    w.paths = {"/work/{id}": f"/work/{w.ticket}", "/runs/{id}": f"/runs/{w.invocation}",
               "/evidence/{id}": f"/evidence/{evidence['data']['items'][0]['id']}",
               "/knowledge/{id}": f"/knowledge/{knowledge['data']['items'][0]['id']}",
               "/history/{id}": f"/history/{done}"}
    yield w
    w.server.stop()
    w.lab.cleanup()
    assert_control_invariants(p)


def served_routes() -> list[str]:
    return sorted(r for r in CONTRACT.paths if r != "/attention")  # /attention: 403 until F15.1


def path_of(world: World, route: str) -> str:
    return world.paths.get(route, route)


# ------------------------------------------------------------------------------------- nothing changed

@pytest.mark.parametrize("route", served_routes())
def test_an_unchanged_representation_is_a_304_on_every_route_get_and_head(world, route):
    path = path_of(world, route)
    tag, _ = world.client.ok(path)
    for head in (False, True):
        status, headers, raw = world.client.get(path, head=head, inm=tag)
        assert status == 304, (path, head, status, raw)
        assert headers["etag"] == tag and raw == b""
        assert {k: headers.get(k) for k in COMMON} == COMMON
        assert "content-type" not in headers and "set-cookie" not in headers
        assert "server" not in headers and "date" not in headers


@pytest.mark.parametrize("route", served_routes())
def test_head_carries_gets_headers_etag_and_content_length_included(world, route):
    path = path_of(world, route)
    _, get_headers, get_raw = world.client.get(path)
    status, head_headers, head_raw = world.client.get(path, head=True)
    assert status == 200 and head_raw == b""
    assert head_headers == get_headers and int(get_headers["content-length"]) == len(get_raw)


def test_the_time_of_a_read_is_not_part_of_the_validator(world, monkeypatch):
    """``generated_at`` and ``Health.observed_at`` are the snapshot's time: a later read of the same state is the same
    validator, and its body carries the later time."""
    tag, before = world.client.ok("/overview")
    monkeypatch.setattr(R, "utc_now", lambda: "2099-01-01T00:00:00Z")
    later_tag, later = world.client.ok("/overview")
    assert later_tag == tag
    assert later["generated_at"] == later["data"]["health"]["observed_at"] == "2099-01-01T00:00:00Z"
    assert before["generated_at"] != later["generated_at"]
    assert world.client.get("/overview", inm=tag)[0] == 304


def test_weak_star_and_foreign_validators_never_match_and_a_list_does(world):
    tag, _ = world.client.ok("/work")
    assert world.client.get("/work", inm=f"W/{tag}")[0] == 200
    assert world.client.get("/work", inm="*")[0] == 200
    assert world.client.get("/work", inm='"0000"')[0] == 200
    assert world.client.get("/work", inm=f'"0000", {tag}')[0] == 304


def test_a_validator_belongs_to_its_scope(world):
    """The same representation under another scope is another validator, so a client's cached copy for one scope is
    never confirmed for another; a limit that parses to the same number is the same scope."""
    every, _ = world.client.ok("/work")
    one, _ = world.client.ok("/work?limit=1")
    assert len({every, one}) == 2
    assert world.client.get("/work?limit=1", inm=every)[0] == 200
    assert world.client.ok("/work?limit=01")[0] == one
    run_tag, _ = world.client.ok(f"/runs/{world.invocation}")
    assert world.client.get("/runs", inm=run_tag)[0] == 200


def test_a_conditional_request_is_authenticated_first(world):
    tag, _ = world.client.ok("/project")
    world.gate.closed = True
    try:
        status, headers, raw = world.client.get("/project", inm=tag)
    finally:
        world.gate.closed = False
    assert status == 401 and json.loads(raw)["code"] == "SESSION_REQUIRED" and "etag" not in headers


def test_errors_carry_no_validator_and_never_answer_304(world):
    for path, status in (("/attention", 403), ("/work/T-9999", 404), ("/work?limit=0", 400), ("/nope", 404)):
        got, headers, _ = world.client.get(path, inm="*")
        assert got == status and "etag" not in headers, path


# ------------------------------------------------------------------------------------- changes

def every_tag(world: World) -> dict[str, tuple[str, str]]:
    out = {}
    for route in served_routes():
        tag, body = world.client.ok(path_of(world, route))
        out[route] = (tag, body["control_revision"])
    return out


def test_a_commit_is_a_200_with_a_new_validator_on_every_route(world):
    before = every_tag(world)
    world.lab.project.lead("work", "create", "ticket", "--title", "Later work", "--class", "1")
    for route, (tag, revision) in before.items():
        path = path_of(world, route)
        status, headers, raw = world.client.get(path, inm=tag)
        assert status == 200, (route, status)
        assert headers["etag"] != tag and json.loads(raw)["control_revision"] != revision


def test_control_revision_alone_changes_the_validator(world):
    """A commit that changes no field ``/project`` or ``/capabilities`` projects (an audit record) is still a 200:
    the revision is part of the representation."""
    p = world.lab.project
    tags = {path: world.client.ok(path) for path in ("/project", "/capabilities")}
    p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))
    for path, (tag, body) in tags.items():
        new_tag, new = world.client.ok(path, inm=tag)
        assert new_tag != tag and new["data"] == body["data"]
        assert int(new["control_revision"]) > int(body["control_revision"])


def test_telemetry_alone_at_the_same_revision_is_a_200(world):
    """A run's observed status is telemetry: it changes without a commit, and the validator changes with it."""
    p = world.lab.project
    paths = ["/runs", f"/runs/{world.invocation}", "/overview"]
    before = {path: world.client.ok(path) for path in paths}
    revision = p.rev()
    directory = runlog.run_dir(world.lab.aew_root, world.run)
    record = runlog.read_record(directory)
    assert record is not None and record["status"] == K.ENDED_WITH_EVIDENCE
    runlog.write_record(directory, dict(record, status=K.CRASHED))
    try:
        assert p.rev() == revision
        for path, (tag, body) in before.items():
            new_tag, new = world.client.ok(path, inm=tag)
            assert new_tag != tag and new["control_revision"] == body["control_revision"], path
        _, run = world.client.ok(f"/runs/{world.invocation}")
        assert run["data"]["runs"][-1]["status"] == K.CRASHED
    finally:
        runlog.write_record(directory, record)
    restored, _ = world.client.ok(f"/runs/{world.invocation}")
    assert restored == before[f"/runs/{world.invocation}"][0]  # the same representation is the same validator


def test_the_frontends_two_diagnostics_hold_across_changes(world):
    """A client of its own polls every route, conditionally with what it holds, across a commit that changes
    projections and a commit that changes only the revision; ``Client.get`` asserts both diagnostics on each
    response, and the client must have seen enough validators and revisions for that to mean something."""
    p = world.lab.project
    client = Client(world.server.port)
    held = {route: client.ok(path_of(world, route))[0] for route in served_routes()}
    changes = [lambda: None, lambda: p.lead("work", "create", "ticket", "--title", "More work", "--class", "1"),
               lambda: p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev())), lambda: None]
    for change in changes:
        change()
        for route in served_routes():
            status, headers, _ = client.get(path_of(world, route), inm=held[route])
            assert status in (200, 304)
            held[route] = headers["etag"]
    assert len(client.revision_of) >= 3 * len(served_routes())
    assert len(set(client.revision_of.values())) == 3
