"""F20.2: contract 0.1.2's GET and HEAD projections, served by the dashboard server and validated against the contract
(design note §5.1). One project is driven through the lifecycle to archival once per module; every route is then read
over HTTP and its body checked with ``jsonschema`` against the accepted contract.

The server here runs with a test-only authenticator that admits everything: F20.3 brings the real one. No code in
``src`` can start a listener without an authenticator (the enablement rule, designer 2026-10-05).
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
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    create_unit,
    integrate,
    plan_unit,
    sample_project,
    to_commit_ready,
)
from invariants import assert_control_invariants  # noqa: E402

from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard.reasons import REASONS, codes_in  # noqa: E402
from aew.dashboard.server import DashboardServer  # noqa: E402
from aew.engine.api import Engine  # noqa: E402
from aew.engine.lock import FileLock  # noqa: E402
from aew.engine.store import LOCK_REL  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)


class OpenAccess:
    """Test-only: every request may read. The product's authenticator is F20.3's operator session."""

    def authenticate(self, headers: Any) -> dict[str, Any] | None:
        return None


class World:
    def __init__(self, project: Any, tmp: Path) -> None:
        self.p = project
        self.tmp = tmp
        self.ids: dict[str, str] = {}
        self.server: DashboardServer | None = None

    def get(self, path: str, *, head: bool = False, raw: bool = False) -> tuple[int, dict[str, str], Any]:
        assert self.server is not None
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=60)
        try:
            conn.request("HEAD" if head else "GET", f"/api/v1{path}")
            resp = conn.getresponse()
            body = resp.read()
            headers = {k.lower(): v for k, v in resp.getheaders()}
            if head or raw:
                return resp.status, headers, body
            return resp.status, headers, json.loads(body.decode("utf-8"))
        finally:
            conn.close()

    def ok(self, path: str, schema: str) -> dict[str, Any]:
        status, headers, body = self.get(path)
        assert status == 200, (path, status, body)
        assert headers["content-type"].startswith("application/json")
        assert CONTRACT.violations(schema, body) == [], (path, CONTRACT.violations(schema, body)[:5])
        return body

    def error(self, path: str, status: int, code: str) -> dict[str, Any]:
        got, _, body = self.get(path)
        assert got == status, (path, got, body)
        assert CONTRACT.violations(CT.ERROR_SCHEMA, body) == []
        assert body["code"] == code, body
        return body


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> World:
    """A project with an Epic, a Story, an integrated (archived) Ticket, a finished (archived) investigation, an open
    Ticket and a Ticket blocked behind it, a recorded audit, and a move of an archived unit (an annotation)."""
    tmp = tmp_path_factory.mktemp("dashboard")
    p = sample_project(tmp)
    w = World(p, tmp)
    epic = create_unit(p, "epic", "Calculator", cls=1)
    plan_unit(p, tmp, epic)
    story = create_unit(p, "story", "Arithmetic", cls=1, parent=epic)
    plan_unit(p, tmp, story)
    done, _ = to_commit_ready(p, tmp, title="Add subtract()", extra=("--parent", story))
    integrate(p, done)
    inv = create_investigation(p, tmp, title="Investigate calc.core", parent=story)
    complete_investigation(p, inv)
    open_ticket = create_planned_ticket(p, tmp, title="Add apply()", extra=("--parent", story))
    blocked = create_planned_ticket(p, tmp, title="Add compose()", extra=("--parent", story))
    p.lead("work", "depend", blocked, "--add", f"{open_ticket}:mutating", "--reason", "compose needs apply")
    p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))
    p.lead("work", "move", done, "--parent", epic, "--reason", "regrouped under the Epic")
    w.ids = {"epic": epic, "story": story, "done": done, "investigation": inv, "open": open_ticket,
             "blocked": blocked}
    engine = Engine.discover(p.root)
    w.server = DashboardServer(engine, authenticator=OpenAccess(), validate_with=CONTRACT)
    w.server.start()
    yield w
    w.server.stop()
    assert_control_invariants(p)


def concrete(world: World, route: str) -> str:
    """A request path for a contract route: the ids of the world for ``{id}``."""
    ids = world.ids
    return {"/work/{id}": f"/work/{ids['done']}", "/runs/{id}": f"/runs/{first_invocation(world)}",
            "/evidence/{id}": f"/evidence/{first_evidence(world)}", "/knowledge/{id}": "/knowledge/D-0001",
            "/history/{id}": f"/history/{ids['done']}"}.get(route, route)


def first_invocation(world: World) -> str:
    return world.ok("/runs", "InvocationListResponse")["data"]["items"][0]["id"]


def first_evidence(world: World) -> str:
    return world.ok(f"/evidence?work={world.ids['open']}&limit=1", "EvidenceListResponse")["data"]["items"][0]["id"] \
        if world.ok(f"/evidence?work={world.ids['open']}", "EvidenceListResponse")["data"]["items"] \
        else world.ok(f"/evidence?work={world.ids['done']}", "EvidenceListResponse")["data"]["items"][0]["id"]


# ---------------------------------------------------------------------------------------------- conformance

@pytest.mark.parametrize("route", sorted(CONTRACT.paths))
def test_every_route_answers_get_and_head_as_the_contract_says(world, route):
    path = concrete(world, route)
    status, headers, body = world.get(path)
    if route == "/attention":  # UNSUPPORTED until F15.1 (designer, 2026-10-05): the capability's 403
        assert status == 403 and body["code"] == "CAPABILITY_UNAVAILABLE"
        assert body["reasons"][0]["code"] == "AWAITS_ACTION_PROJECTION"
    else:
        assert status == 200, (path, body)
        assert CONTRACT.violations(CONTRACT.response_schema(route), body) == [], (
            path, CONTRACT.violations(CONTRACT.response_schema(route), body)[:5])
        assert body["schema_version"] == "0.1.2" and body["project_id"] == "calc"
        assert body["control_revision"].isdigit() and body["generated_at"].endswith("Z")
    head_status, head_headers, head_body = world.get(path, head=True)
    assert head_status == status and head_body == b""
    assert head_headers["content-length"] == headers["content-length"]
    assert head_headers["content-type"] == headers["content-type"]
    assert "server" not in headers and "date" not in headers


def test_capabilities_are_the_designers_decisions(world):
    caps = world.ok("/capabilities", "CapabilitiesResponse")["data"]
    for name in ("overview", "work", "runs", "evidence", "knowledge", "activity", "history", "integrity"):
        assert caps[name]["state"] == "AVAILABLE", name
    assert caps["queue"]["state"] == "UNSUPPORTED" and caps["queue"]["reasons"][0]["code"] == "NOT_IN_CONTRACT_0_1_2"
    assert caps["action_projection"]["state"] == "UNSUPPORTED"
    assert caps["action_projection"]["reasons"][0]["code"] == "AWAITS_ACTION_PROJECTION"


def test_no_response_discloses_a_path_a_verifier_or_a_credential(world):
    from invariants import load_control, with_cold

    hot = load_control(world.p.root)
    full, _ = with_cold(world.p.root, hot)  # every credential record, archived ones included
    verifiers = [t["verifier"] for t in full["tokens"].values()]
    assert verifiers, "the world holds credentials to not disclose"
    forbidden = ["aew1.", '"verifier":', ".aew/", ".aew\\", "run_dir", "workspace_id", str(world.tmp), "C:\\",
                 "/tmp/", "control.yaml", "archive.yaml", "history/tail", *verifiers]
    for route in CONTRACT.paths:
        status, _, raw = world.get(concrete(world, route), raw=True)
        text = raw.decode("utf-8")
        for needle in forbidden:
            assert needle not in text, (route, needle)
        assert status in (200, 403)


def test_every_reason_code_in_every_response_is_registered(world):
    for route in CONTRACT.paths:
        _, _, body = world.get(concrete(world, route))
        unknown = codes_in(body) - set(REASONS)
        assert unknown == set(), (route, unknown)


# ---------------------------------------------------------------------------------------------- work

def test_work_default_scope_is_hot_work_plus_the_recent_ring(world):
    items = world.ok("/work", "WorkListResponse")["data"]["items"]
    by_id = {i["id"]: i for i in items}
    assert {world.ids["epic"], world.ids["story"], world.ids["open"], world.ids["blocked"]} <= set(by_id)
    assert by_id[world.ids["done"]]["archived"] is True and by_id[world.ids["done"]]["state"] == "DONE"
    assert by_id[world.ids["done"]]["parent_id"] == world.ids["epic"]  # the later move is applied
    assert by_id[world.ids["done"]]["integration"]["commit"] and by_id[world.ids["done"]]["integration"]["status"]
    assert by_id[world.ids["open"]]["archived"] is False and by_id[world.ids["open"]]["state"] == "READY"
    blocked = by_id[world.ids["blocked"]]
    assert blocked["state"] == "BLOCKED" and blocked["blocked_by"][0]["code"] == "BLOCKED_BY"
    assert blocked["has_attention"] is True and by_id[world.ids["open"]]["has_attention"] is False
    story = by_id[world.ids["story"]]
    # The integrated Ticket was moved to the Epic, so the Story's subtree holds one finished Ticket (the archived
    # investigation, counted through the summary) and the Epic's subtree holds both.
    assert story["rollup"] == {"open": 2, "done": 1, "cancelled": 0}
    assert by_id[world.ids["epic"]]["rollup"] == {"open": 2, "done": 2, "cancelled": 0}
    assert set(story["children"]) >= {world.ids["open"], world.ids["blocked"], world.ids["investigation"]}
    assert by_id[world.ids["epic"]]["children"] == sorted([world.ids["story"], world.ids["done"]])


def test_work_filters_select_a_scope_and_archived_work_is_an_explicit_query(world):
    done = world.ok("/work?state=DONE", "WorkListResponse")["data"]["items"]
    assert {i["id"] for i in done} == {world.ids["done"], world.ids["investigation"]}
    assert all(i["archived"] for i in done)
    assert world.ok("/work?state=CANCELLED", "WorkListResponse")["data"]["items"] == []
    under_story = world.ok(f"/work?parent={world.ids['story']}", "WorkListResponse")["data"]["items"]
    assert {i["id"] for i in under_story} == {world.ids["open"], world.ids["blocked"], world.ids["investigation"]}
    tickets = world.ok("/work?kind=ticket&state=READY", "WorkListResponse")["data"]["items"]
    assert [i["id"] for i in tickets] == [world.ids["open"]]


def test_work_pages_by_cursor_to_exhaustion_and_the_cursor_dies_with_the_revision(world):
    first = world.ok("/work?limit=2", "WorkListResponse")["data"]
    assert len(first["items"]) == 2 and first["next_cursor"]
    seen = [i["id"] for i in first["items"]]
    cursor = first["next_cursor"]
    while cursor:
        page = world.ok(f"/work?limit=2&cursor={cursor}", "WorkListResponse")["data"]
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == 6
    world.error(f"/work?limit=3&cursor={first['next_cursor']}", 400, "CURSOR_INVALID")  # another limit
    world.p.lead("work", "create", "ticket", "--title", "Later work", "--class", "1", "--parent", world.ids["story"])
    world.error(f"/work?limit=2&cursor={first['next_cursor']}", 409, "CURSOR_EXPIRED")


def test_a_unit_by_id_hot_or_archived(world):
    hot = world.ok(f"/work/{world.ids['open']}", "WorkResponse")["data"]
    assert hot["id"] == world.ids["open"] and hot["plan_revision"] == 1 and hot["mutating"] is True
    archived = world.ok(f"/work/{world.ids['investigation']}", "WorkResponse")["data"]
    assert archived["archived"] is True and archived["mutating"] is False
    world.error("/work/T-9999", 404, "NOT_FOUND")


# ---------------------------------------------------------------------------------- runs, evidence, knowledge

def test_runs_list_the_invocations_of_hot_and_recently_finished_work(world):
    items = world.ok("/runs", "InvocationListResponse")["data"]["items"]
    assert items and [i["id"] for i in items] == sorted(i["id"] for i in items)
    finished = [i for i in items if i["work"]["id"] == world.ids["done"]]
    assert finished and all(i["status"] == "completed" for i in finished)
    assert any(i["evidence"] for i in finished)
    one = world.ok(f"/runs/{finished[0]['id']}", "InvocationResponse")["data"]
    assert one == finished[0]
    world.error("/runs/INV-9999", 404, "NOT_FOUND")


def test_evidence_of_hot_and_archived_work(world):
    archived = world.ok(f"/evidence?work={world.ids['done']}", "EvidenceListResponse")["data"]["items"]
    kinds = {i["kind"] for i in archived}
    assert {"check_result", "implementation_report", "review", "verification"} <= kinds
    assert all(i["subject"]["id"] == world.ids["done"] for i in archived)
    assert all(i["bindings"]["producer"]["invocation"].startswith("INV-") for i in archived)
    assert all(i["bindings"]["evaluated_snapshot"] is None or "workspace_id" not in i["bindings"]["evaluated_snapshot"]
               for i in archived)
    one = world.ok(f"/evidence/{archived[0]['id']}", "EvidenceResponse")["data"]
    assert one["id"] == archived[0]["id"] and one["body"]["format"] == "markdown"
    everything = world.ok("/evidence", "EvidenceListResponse")["data"]["items"]
    hot = set(world.p.ok("status", "--json")["work"])
    assert all(i["subject"]["id"] in hot for i in everything)  # hot units only
    world.error("/evidence/INV-9999-impl-1", 404, "NOT_FOUND")
    world.error("/evidence?work=T-9999", 404, "NOT_FOUND")


def test_knowledge_projects_decision_records(world):
    items = world.ok("/knowledge", "KnowledgeListResponse")["data"]["items"]
    assert items and all(i["kind"] == "decision" and i["decision_type"] for i in items)
    assert any(i["decision_type"] == "plan_acceptance" for i in items)
    one = world.ok("/knowledge/D-0001", "KnowledgeResponse")["data"]
    assert one["id"] == "D-0001"
    world.error("/knowledge/D-9999", 404, "NOT_FOUND")


# ---------------------------------------------------------------------------------------------- history

def test_history_lists_the_manifest_newest_first_with_moves_applied(world):
    items = world.ok("/history", "HistoryListResponse")["data"]["items"]
    seqs = [i["seq"] for i in items]
    assert seqs == sorted(seqs, reverse=True) and seqs[-1] == 1
    kinds = {i["kind"] for i in items}
    assert {"unit", "audit", "annotation"} <= kinds
    unit = next(i for i in items if i["id"] == world.ids["done"])
    assert unit["parent"] == world.ids["epic"] and "completion" not in unit["links"]
    assert set(unit["links"]) >= {"invocations", "tokens", "evidence", "integration_commit"}
    assert [i["kind"] for i in world.ok("/history?kind=audit", "HistoryListResponse")["data"]["items"]] == ["audit"]
    assert world.ok("/history?since=2099-01-01T00:00:00Z", "HistoryListResponse")["data"]["items"] == []


def test_a_history_cursor_survives_appends_and_never_expires(world):
    first = world.ok("/history?limit=1", "HistoryListResponse")["data"]
    cursor = first["next_cursor"]
    newest_before = first["items"][0]["seq"]
    inv = create_investigation(world.p, world.tmp, title="Investigate again", parent=world.ids["story"])
    complete_investigation(world.p, inv)  # appends a manifest entry (and a commit: hot cursors would 409 now)
    second = world.ok(f"/history?limit=1&cursor={cursor}", "HistoryListResponse")["data"]
    assert second["items"][0]["seq"] == newest_before - 1  # the walk continues where it was
    walked = [first["items"][0]["seq"], second["items"][0]["seq"]]
    cursor = second["next_cursor"]
    while cursor:
        page = world.ok(f"/history?limit=1&cursor={cursor}", "HistoryListResponse")["data"]
        walked += [i["seq"] for i in page["items"]]
        cursor = page["next_cursor"]
    assert walked == list(range(newest_before, 0, -1))  # the appended entry never entered this session
    fresh = world.ok("/history?limit=1", "HistoryListResponse")["data"]["items"][0]
    assert fresh["seq"] == newest_before + 1 and fresh["id"] == inv


def test_the_cli_pages_the_history_the_same_way(world):
    """R13: `aew history list --before SEQ` is the CLI's parity with the dashboard's pinned walk."""
    first = world.p.ok("history", "list", "--limit", "2")
    assert len(first["items"]) == 2 and first["truncated"] is True
    oldest = first["items"][-1]["seq"]
    second = world.p.ok("history", "list", "--limit", "2", "--before", str(oldest))
    assert second["before"] == oldest and all(i["seq"] < oldest for i in second["items"])
    assert [i["seq"] for i in first["items"] + second["items"]] == sorted(
        (i["seq"] for i in first["items"] + second["items"]), reverse=True)
    refused = world.p.aew("history", "list", "--before", "0")
    assert refused.returncode != 0 and refused.error["code"] == "USAGE"


def test_a_history_record_with_its_annotations(world):
    detail = world.ok(f"/history/{world.ids['done']}", "HistoryResponse")["data"]
    assert detail["id"] == world.ids["done"] and detail["kind"] == "unit"
    assert [a["rel"] for a in detail["annotations"]] == ["moved_to"]
    assert detail["annotations"][0]["object"] == world.ids["epic"] and detail["annotations_next_cursor"] is None
    audit = world.ok("/history?kind=audit", "HistoryListResponse")["data"]["items"][0]
    assert world.ok(f"/history/{audit['id']}", "HistoryResponse")["data"]["annotations"] == []
    world.error("/history/T-9999", 404, "NOT_FOUND")


def test_integrity_is_the_audit_status_field_by_field(world):
    data = world.ok("/history/integrity", "IntegrityResponse")["data"]
    status = world.p.ok("status", "--json")["history_audit"]
    assert data["current_root"]["count"] == status["current"]["count"]
    assert data["backlog"] == status["unverified"]["entries"]
    assert data["verified"]["audit"].startswith("AU-") and data["last_audit"]["id"] == data["verified"]["audit"]
    assert "age_days" not in (data["last_full"] or {})
    assert data["oldest_unverified_at"] == status["unverified"]["oldest_at"]
    assert [r["code"] for r in data["reasons"]] == [d["code"] for d in status["over_policy_detail"]]
    assert data["status"] in ("VERIFIED", "BACKLOG", "OVER_POLICY")


# ---------------------------------------------------------------------------------------------- activity, overview

def test_activity_is_the_transition_log_newest_first_and_pages_by_pinned_revision(world):
    body = world.ok("/activity?limit=5", "ActivityListResponse")
    first = body["data"]
    revs = [int(i["id"][1:]) for i in first["items"]]
    assert revs == sorted(revs, reverse=True) and revs[0] == int(body["control_revision"])
    assert all(i["subject"]["id"] for i in first["items"])
    walked = list(revs)
    cursor = first["next_cursor"]
    while cursor:
        page = world.ok(f"/activity?limit=5&cursor={cursor}", "ActivityListResponse")["data"]
        walked += [int(i["id"][1:]) for i in page["items"]]
        cursor = page["next_cursor"]
    assert walked == list(range(walked[0], 0, -1))  # every revision from the newest down to 1, once


def test_overview_is_one_coherent_read_with_bounded_lists(world):
    data = world.ok("/overview", "OverviewResponse")["data"]
    assert data["project"] == world.ok("/project", "ProjectResponse")["data"]
    assert len(data["work"]) <= 6 and len(data["runs"]) <= 6 and len(data["attention"]) <= 6
    assert len(data["activity"]) <= 10 and len(data["recent"]) <= 20
    assert data["work"][0]["has_attention"] is True  # attention first
    assert data["counts"]["attention"] == len(data["attention"]) and data["counts"]["runs"] == len(data["runs"])
    assert data["counts"]["work"]["done"] >= 2 and data["counts"]["work"]["open"] >= 4
    assert {w["id"] for w in data["recent"]} >= {world.ids["done"], world.ids["investigation"]}
    assert data["health"]["status"] in ("HEALTHY", "DEGRADED")
    assert data["capabilities"]["queue"]["state"] == "UNSUPPORTED"
    assert any(a["kind"] == "blocker" and a["subject"]["id"] == world.ids["blocked"] for a in data["attention"])


# ---------------------------------------------------------------------------------------------- refusals and the lock

@pytest.mark.parametrize("path, code", [
    ("/work?limit=0", "INVALID_REQUEST"), ("/work?limit=251", "INVALID_REQUEST"),
    ("/work?limit=abc", "INVALID_REQUEST"),
    ("/work?bogus=1", "INVALID_REQUEST"), ("/work?limit=1&limit=2", "INVALID_REQUEST"),
    ("/work?cursor=not-a-cursor", "CURSOR_INVALID"), ("/work?parent=../x", "INVALID_REQUEST"),
    ("/history?kind=bogus", "INVALID_REQUEST"), ("/history?since=yesterday", "INVALID_REQUEST"),
    ("/history?cursor=AAAA", "CURSOR_INVALID"), ("/activity?cursor=AAAA", "CURSOR_INVALID"),
    ("/work/..", "INVALID_REQUEST"), ("/runs/not%20an%20id", "INVALID_REQUEST"),
])
def test_invalid_requests_are_400_with_a_registered_code(world, path, code):
    world.error(path, 400, code)


def test_unknown_routes_and_methods_are_refused(world):
    world.error("/queue", 404, "NOT_FOUND")
    world.error("/work/a/b", 404, "NOT_FOUND")
    assert world.server is not None
    conn = http.client.HTTPConnection("127.0.0.1", world.server.port, timeout=30)
    try:
        conn.request("GET", "/index.html")
        assert conn.getresponse().status == 404
    finally:
        conn.close()
    conn = http.client.HTTPConnection("127.0.0.1", world.server.port, timeout=30)
    try:
        conn.request("POST", "/api/v1/project", body=b"{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        resp.read()
        assert resp.status in (405, 501)  # http.server answers 501 for a method the handler does not implement
    finally:
        conn.close()


def test_a_cursor_from_another_scope_is_invalid_not_expired(world):
    cursor = world.ok("/history?limit=1", "HistoryListResponse")["data"]["next_cursor"]
    world.error(f"/history?limit=1&kind=unit&cursor={cursor}", 400, "CURSOR_INVALID")
    world.error(f"/activity?limit=1&cursor={cursor}", 400, "CURSOR_INVALID")


def test_no_request_takes_the_control_lock(world):
    """ADR-0012 D3, invariant 4: a reader is never behind a writer. The test holds the control lock, as a committing
    writer would, and every route still answers."""
    with FileLock(world.p.root / ".aew" / LOCK_REL, timeout=5):
        for route in CONTRACT.paths:
            status, _, _ = world.get(concrete(world, route))
            assert status in (200, 403), route


def test_a_v1_project_reports_history_and_integrity_unavailable(tmp_path):
    """A project whose control state is still schema v1: the routes that need the cold history are 403 with
    MIGRATION_REQUIRED, never an empty list."""
    from conftest import Project, make_git_repo

    from aew.engine.base import as_v1
    from aew.engine.store import deserialize_control, serialize_control

    p = Project(make_git_repo(tmp_path / "repo"))
    p.ok("init", "--project-id", "legacy")
    control = p.root / ".aew/state/control.yaml"
    state = deserialize_control(control.read_bytes(), source=str(control))
    control.write_bytes(serialize_control(as_v1(state)))
    server = DashboardServer(Engine.discover(p.root), authenticator=OpenAccess(), validate_with=CONTRACT)
    server.start()
    try:
        w = World(p, tmp_path)
        w.server = server
        caps = w.ok("/capabilities", "CapabilitiesResponse")["data"]
        assert caps["history"]["state"] == "UNAVAILABLE"
        assert caps["history"]["reasons"][0]["code"] == "MIGRATION_REQUIRED"
        body = w.error("/history", 403, "CAPABILITY_UNAVAILABLE")
        assert body["reasons"][0]["code"] == "MIGRATION_REQUIRED"
        w.error("/history/integrity", 403, "CAPABILITY_UNAVAILABLE")
        assert w.ok("/work", "WorkListResponse")["data"]["items"] == []
        assert w.ok("/overview", "OverviewResponse")["data"]["counts"]["work"] == {"open": 0, "done": 0, "cancelled": 0}
    finally:
        server.stop()
