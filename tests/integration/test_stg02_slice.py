"""STG-02, the first vertical slice: the adopted D-01 0.3.4 reads and the O-01 0.2 command route over real HTTP,
against a live AEW project (the real source) and the labelled fixture world.

Each guarantee is the adopted one it names: the exact version cutover (profile rules 1 and 2), the six-field Problem
on the HTTP/Problem matrix, recipient-scoped reads where a hidden member changes nothing, fixture facts never
qualified, the continuation vector as information only (C18, never C17), and the command-set rules CS-01..CS-09 with
A-24's SW-04 delegated-grant origin. Every 200 and 202 body is checked against the vendored adopted schemas.
"""

from __future__ import annotations

import base64
import copy
import http.client
import json
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import assign, create_planned_ticket, sample_project  # noqa: E402

from aew.stg02 import adopted as A  # noqa: E402
from aew.stg02 import ledger as L  # noqa: E402
from aew.stg02 import server as SV  # noqa: E402
from aew.stg02 import wire as W  # noqa: E402

D01 = {W.D01_HEADER: W.D01_VERSION}
O01 = {W.O01_HEADER: W.O01_VERSION}
T0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)
OTHER = "fixture:recipient-other"
TOKENS = {"token-operator": "fixture:recipient-operator", "token-other": OTHER}
ROUTE_REF = {"/v1/read/waiting": "ReadWaiting", "/v1/read/runs/{execution_id}": "ReadRunDetail",
             "/v1/read/continuation-state/{work_id}": "ReadContinuationVector",
             "/v1/read/owner-operations": "ReadOwnerOperations"}


def b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class Live:
    def __init__(self, s: SV.Slice, clock: list[datetime]) -> None:
        self.s, self.clock = s, clock
        self.srv = SV.make_server(s, 0)
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    def request(self, method: str, path: str, headers: dict[str, str] | None = None, body: Any = None,
                ) -> tuple[int, dict[str, str], Any]:
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            h = dict(headers or {})
            raw = None
            if body is not None:
                raw = json.dumps(body).encode()
                h.setdefault("Content-Type", "application/json")
            c.request(method, path, body=raw, headers=h)
            r = c.getresponse()
            data = r.read()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, json.loads(data) if data else None
        finally:
            c.close()

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
        return self.request("GET", path, {**D01, **(headers or {})})

    def post(self, body: Any, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
        return self.request("POST", "/o01/v0/command-sets", {**O01, **(headers or {})}, body)

    def owner_get(self, owner: str, op: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], Any]:
        return self.request("GET", f"/o01/v0/owner-operations/{owner}/{op}", {**O01, **(headers or {})})

    def entitle(self, entitled: bool, recipient: str = "fixture:recipient-operator") -> None:
        st, _, _ = self.request("POST", "/_test/read-entitlement",
                                body={"recipient_ref": recipient, "entitled": entitled})
        assert st == 204


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A real AEW project: one running Ticket with an invocation, and one BLOCKED on it (a waiting work unit)."""
    tmp = tmp_path_factory.mktemp("stg02-project")
    p = sample_project(tmp)
    running = create_planned_ticket(p, tmp, title="Add apply()")
    blocked = create_planned_ticket(p, tmp, title="Blocked on apply()", extra=("--depends-on", running))
    assign(p, running)
    return {"root": p.root, "running": running, "blocked": blocked, "project": p}


@pytest.fixture()
def live(project: dict[str, Any], tmp_path: Path):
    clock = [T0]
    s = SV.Slice(tmp_path / "state", project=project["root"], tokens=TOKENS, fixture_recipient=True,
                 test_routes=True, clock=lambda: clock[0])
    lv = Live(s, clock)
    yield lv
    lv.close()


@pytest.fixture()
def cfg(live: Live) -> dict[str, Any]:
    return SV.driver_config(live.s)


def fresh(cset: dict[str, Any], tag: str) -> dict[str, Any]:
    c = copy.deepcopy(cset)
    c["client_request_key"] += "." + tag
    c["request_set_ref"] += "." + tag
    return c


def schema_ok(route: str, body: Any) -> None:
    errs = A.d01_errors(ROUTE_REF[route], body)
    assert not errs, errs[:3]


def problem_ok(api: str, method: str, route: str, st: int, h: dict[str, str], body: Any, code: str) -> None:
    """A non-2xx answer is the six-field Problem and matches its HTTP/Problem matrix row exactly."""
    assert not (A.d01_errors("Problem", body) if api == "D01" else A.o01_openapi_errors("Problem", body))
    rows = [r for r in A.matrix() if (r["api"], r["method"], r["route"], r["status"], r["code"]) ==
            (api, method, route, st, code)]
    assert rows, f"no matrix row for {api} {method} {route} {st} {code}"
    r = rows[0]
    assert body["code"] == code and body["retry"] == r["retry"] and body["status"] == st
    assert h["content-type"] in r["content_type"]
    assert all(h.get(k.lower()) == v for k, v in r["headers"].items())


def stamps(o: Any):
    if isinstance(o, dict):
        if "qualification" in o and "fact_ref" in o:
            yield o
        for v in o.values():
            yield from stamps(v)
    elif isinstance(o, list):
        for v in o:
            yield from stamps(v)


def invocation_id(project: dict[str, Any]) -> str:
    from aew.engine.api import Engine

    state = Engine(project["root"], project["root"] / ".aew").store.read_committed()
    return next(i for i, v in state["invocations"].items() if v["work_unit"] == project["running"])


# ------------------------------------------------------------------------------------------------- reads

def test_every_read_answers_a_schema_valid_recipient_scoped_body_with_the_exact_headers(live: Live,
                                                                                         project: dict[str, Any]):
    inv = invocation_id(project)
    paths = {"/v1/read/waiting": "/v1/read/waiting",
             "/v1/read/runs/{execution_id}": f"/v1/read/runs/{b64('fixture:run-continue-1')}",
             "/v1/read/continuation-state/{work_id}": f"/v1/read/continuation-state/{b64('fixture:ticket-continue')}",
             "/v1/read/owner-operations": "/v1/read/owner-operations"}
    real = {"/v1/read/runs/{execution_id}": f"/v1/read/runs/{b64(inv)}",
            "/v1/read/continuation-state/{work_id}": f"/v1/read/continuation-state/{b64(project['blocked'])}"}
    for route, path in [*paths.items(), *real.items()]:
        st, h, b = live.get(path)
        assert st == 200, (path, b)
        assert h[W.D01_HEADER.lower()] == "0.3.4" and h["cache-control"] == "private, no-store"
        assert h["content-type"] == "application/json"
        schema_ok(route, b)
        assert b["effective_recipient_ref"] == "fixture:recipient-operator"
        assert all(i["disclosure"]["effective_recipient_ref"] == "fixture:recipient-operator" for i in b["items"])


def test_no_stamp_is_ever_qualified_and_every_fixture_fact_is_labelled(live: Live, project: dict[str, Any]):
    """The handoff's rule 2: a fixture fact says so (fixture: prefix, unqualified); a real AEW fact names its real
    record (aew:) and is unqualified too, because no AEW owner issues the renewal a qualified stamp needs."""
    inv = invocation_id(project)
    bodies = [live.get(p)[2] for p in ("/v1/read/waiting", f"/v1/read/runs/{b64('fixture:run-continue-1')}",
                                       f"/v1/read/runs/{b64(inv)}",
                                       f"/v1/read/continuation-state/{b64('fixture:ticket-continue')}",
                                       f"/v1/read/continuation-state/{b64(project['blocked'])}")]
    seen = {"fixture": 0, "aew": 0}
    for b in bodies:
        assert b["outcome"] == "partial" and b["continuity"] == "unknown" and "source_unqualified" in b["limitations"]
        for s in stamps(b):
            assert s["qualification"] != "qualified" and s["observation_state"] != "present_current", s
            if s["qualification"] == "unqualified":
                assert s["fact_ref"].startswith(("fixture:", "aew:", "op-record:")), s
                seen["fixture" if s["source_epoch"].startswith("fixture:") else "aew"] += 1
    assert seen["fixture"] and seen["aew"]


def test_the_waiting_list_carries_real_aew_work_and_the_fixture_journey_item(live: Live, project: dict[str, Any]):
    st, _, b = live.get("/v1/read/waiting")
    by_work = {i["data"]["work"]["id"]: i for i in b["items"]}
    assert project["blocked"] in by_work and "fixture:ticket-continue" in by_work and "fixture:ticket-held" in by_work
    real = by_work[project["blocked"]]
    assert real["data"]["cause"] == "dependency" and real["source"]["fact_ref"] == f"aew:waiting:{project['blocked']}"
    assert [r["id"] for r in real["data"]["basis_refs"]["refs"]] == [project["running"]]
    assert project["running"] not in by_work  # RUNNING is not waiting
    assert b["page"]["membership"] == "unknown" and b["page"]["has_more"] is False


def test_a_hidden_member_changes_nothing_the_recipient_sees(live: Live, cfg: dict[str, Any]):
    """The other recipient's waiting item, run and operations exist; the operator's reads are unchanged by them."""
    def view() -> list[Any]:
        out = []
        for p in ("/v1/read/waiting?limit=2", "/v1/read/owner-operations"):
            b = live.get(p)[2]
            out.append({k: v for k, v in b.items() if k not in ("correlation_id",)})
        return out
    before = view()
    st, _, b = live.get(f"/v1/read/runs/{b64('fixture:run-hidden-1')}")
    assert st == 404 and b["code"] == "not_found_or_not_disclosable"
    st, _, other = live.get("/v1/read/waiting", {"Authorization": "Bearer token-other"})
    assert st == 200 and [i["data"]["work"]["id"] for i in other["items"] if i["data"]["work"]["id"].startswith(
        "fixture:")] == ["fixture:ticket-hidden"]
    assert view() == before
    # an unknown and a hidden id are the same answer
    hidden = live.get(f"/v1/read/continuation-state/{b64('fixture:ticket-hidden')}")
    unknown = live.get(f"/v1/read/continuation-state/{b64('fixture:ticket-nothing')}")
    assert hidden[0] == unknown[0] == 404
    assert {k: v for k, v in hidden[2].items() if k != "correlation_id"} == \
           {k: v for k, v in unknown[2].items() if k != "correlation_id"}


def test_the_waiting_cursor_pages_and_is_bound_to_recipient_and_visible_set(live: Live, project: dict[str, Any]):
    st, _, first = live.get("/v1/read/waiting?limit=1")
    assert first["page"]["has_more"] is True
    cur = first["page"]["next_cursor"]
    st, _, second = live.get(f"/v1/read/waiting?limit=1&cursor={cur}")
    assert st == 200 and second["items"][0]["ref"]["id"] != first["items"][0]["ref"]["id"]
    for path, hdr in ((f"/v1/read/waiting?limit=2&cursor={cur}", {}),  # another page size
                      (f"/v1/read/waiting?limit=1&cursor={cur}", {"Authorization": "Bearer token-other"}),
                      (f"/v1/read/waiting?limit=1&cursor={cur[:-1]}x", {})):
        st, h, b = live.get(path, hdr)
        problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "cursor_stale_or_unauthorized")


def test_the_continuation_vector_is_information_only_and_never_shows_an_axis_ok_or_blocked(live: Live,
                                                                                          project: dict[str, Any]):
    for wid in ("fixture:ticket-continue", "fixture:ticket-held", project["blocked"]):
        st, _, b = live.get(f"/v1/read/continuation-state/{b64(wid)}")
        d = b["items"][0]["data"]
        assert d["informational_only"] is True and d["operation"] == "CONTINUE_ELIGIBLE_WORK"
        assert {a["state"] for a in d["axes"].values()} == {"unknown"}
        assert all(a["reason_code"] in ("SOURCE_UNAVAILABLE", "SOURCE_UNQUALIFIED") for a in d["axes"].values())
        assert "G3_unqualified" in b["limitations"]
        pins = {f["field_path"]: f["source"]["owner"] for f in b["items"][0]["field_sources"]}
        assert pins == {**{f"data.axes.{x}": x for x in ("HEB", "ADC", "WIS", "AEV", "R01", "IF10")},
                        "data.work_ref": "WIS", "data.work_revision": "WIS", "data.generation_ref": "HEB",
                        "data.binding_ref": "HEB", "data.operation": "HEB", "data.informational_only": "HEB"}
    st, _, real = live.get(f"/v1/read/continuation-state/{b64(project['blocked'])}")
    axes = real["items"][0]["data"]["axes"]
    assert axes["WIS"]["qualification"] == "unqualified"
    assert axes["WIS"]["basis_ref"] == f"aew:work:{project['blocked']}"
    assert all(axes[x]["qualification"] == "not_established" for x in ("HEB", "ADC", "AEV", "R01", "IF10"))


def test_the_run_detail_shows_the_unknown_remote_effect_with_its_source_basis_and_last_known_time(live: Live):
    st, _, b = live.get(f"/v1/read/runs/{b64('fixture:run-continue-1')}")
    item = b["items"][0]
    d = item["data"]
    assert d["remote_effect_state"] == "UNKNOWN_EFFECT" and d["remote_effect_basis_ref"].startswith("fixture:")
    assert "unknown_remote_effect" in d["limitations"]
    eff = next(f["source"] for f in item["field_sources"] if f["field_path"] == "data.remote_effect_state")
    assert eff["owner"] == "IF12" and eff["observed_at"] < b["projection_as_of"]
    assert d["whole_invocation_effect_clearance"] == "NOT_ESTABLISHED"


def test_version_cutover_refuses_before_any_data_on_every_route(live: Live, cfg: dict[str, Any]):
    for route, path in (("/v1/read/waiting", "/v1/read/waiting"),
                        ("/v1/read/runs/{execution_id}", f"/v1/read/runs/{b64('fixture:run-continue-1')}"),
                        ("/v1/read/continuation-state/{work_id}",
                         f"/v1/read/continuation-state/{b64('fixture:ticket-continue')}"),
                        ("/v1/read/owner-operations", "/v1/read/owner-operations")):
        for hdr in ({}, {W.D01_HEADER: "0.3.3"}):
            st, h, b = live.request("GET", path, hdr)
            problem_ok("D01", "get", route, st, h, b, "invalid_request")
            assert "items" not in b
    for hdr in ({}, {W.O01_HEADER: "o01-command-0.1-candidate"}):
        st, h, b = live.request("POST", "/o01/v0/command-sets", hdr, fresh(cfg["command"]["continue_eligible_work"],
                                                                           "hdr"))
        problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "invalid_request")
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []  # nothing dispatched


def test_identifiers_are_canonical_base64url_and_anything_else_is_400(live: Live):
    good = b64("fixture:ticket-continue")
    for seg in (good + "=", good.replace("-", "+") + "+", "%2F" + good, "e", b64("cafe\u0301"), "!!"):
        st, h, b = live.get(f"/v1/read/continuation-state/{seg}")
        assert st == 400 and b["code"] == "invalid_request", seg


def test_authentication_401_and_the_owner_get_nondisclosing_404(live: Live):
    for route, path in (("/v1/read/waiting", "/v1/read/waiting"),
                        ("/v1/read/runs/{execution_id}", f"/v1/read/runs/{b64('fixture:run-continue-1')}"),
                        ("/v1/read/continuation-state/{work_id}",
                         f"/v1/read/continuation-state/{b64('fixture:ticket-continue')}"),
                        ("/v1/read/owner-operations", "/v1/read/owner-operations")):
        for hdr in ({"Authorization": "Bearer nope"}, {"Authorization": "Basic abc"}):
            st, h, b = live.get(path, hdr)
            problem_ok("D01", "get", route, st, h, b, "authentication_unqualified")
    st, h, b = live.owner_get("HEB", "op:abc123", {"Authorization": "Bearer nope"})
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b,
               "not_found_or_not_disclosable")


def test_the_real_source_unavailable_is_503_where_no_honest_limited_answer_exists(live: Live,
                                                                                  project: dict[str, Any]):
    live.request("POST", "/_test/engine-outage", body={"unavailable": True})
    try:
        st, h, b = live.get(f"/v1/read/runs/{b64(invocation_id(project))}")
        problem_ok("D01", "get", "/v1/read/runs/{execution_id}", st, h, b, "owner_unavailable")
        st, _, w = live.get("/v1/read/waiting")  # the fixture members are still an honest partial answer
        assert st == 200 and {"source_unavailable", "partial_source"} <= set(w["limitations"])
        assert all(i["data"]["work"]["id"].startswith("fixture:") for i in w["items"])
    finally:
        live.request("POST", "/_test/engine-outage", body={"unavailable": False})


# ------------------------------------------------------------------------------------------------- commands

def receipt_ok(req: dict[str, Any], st: int, h: dict[str, str], r: Any, now: datetime) -> None:
    """202, the O-01 headers, the 0.2 Receipt schema and the SW-06 receipt rules (CS-09), current at ``now``."""
    assert st == 202, r
    assert h[W.O01_HEADER.lower()] == W.O01_VERSION and h["cache-control"] == "private, no-store"
    assert not A.o01_errors("Receipt", r)
    assert W.parse_time(r["observed_at"]) <= now < W.parse_time(r["source_valid_until"])
    assert [x["intent_ref"] for x in r["results"]] == [i["intent_ref"] for i in req["intents"]]
    assert (r["request_set_ref"], r["recipient_ref"], r["wire_version"]) == (req["request_set_ref"],
                                                                           req["recipient_ref"], req["wire_version"])
    for i, x in zip(req["intents"], r["results"], strict=True):
        assert x["owner"] == A.registry()[i["action"]]["sole_admitting_owner"]
        if x["admission_state"] == "ADMITTED":
            assert x["operation_ref"]
        if x["admission_state"] in ("RECEIVED", "ORIGIN_PENDING", "HELD"):
            assert x["operation_ref"] is None
        if x["admission_state"] != "ADMITTED":
            assert x["effect_state"] not in ("EXECUTING", "EFFECT_CONFIRMED", "PARTIAL")
        if x["effect_state"] == "EFFECT_CONFIRMED":
            assert x["owner_evidence_ref"]


def test_p07_a_current_delegation_is_admitted_and_its_operation_reads_back_from_the_owner(live: Live,
                                                                                          cfg: dict[str, Any]):
    req = fresh(cfg["command"]["continue_eligible_work"], "p07")
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["reason_code"]) == ("ADMITTED", "EFFECT_CONFIRMED", None)
    assert x["owner_evidence_ref"].startswith("fixture:")
    st, h, g = live.owner_get("HEB", x["operation_ref"])
    assert st == 200 and not A.o01_openapi_errors("OwnerOperationRead", g)
    assert (g["owner"], g["operation_ref"], g["intent_ref"], g["request_set_ref"], g["recipient_ref"],
            g["installation_ref"]) == ("HEB", x["operation_ref"], x["intent_ref"], req["request_set_ref"],
                                       req["recipient_ref"], req["installation_ref"])
    assert g["source_epoch"].startswith("fixture:") and g["result"] == x
    st, _, idx = live.get("/v1/read/owner-operations")
    schema_ok("/v1/read/owner-operations", idx)
    (entry,) = [i for i in idx["items"] if i["data"]["operation_ref"] == x["operation_ref"]]
    assert entry["ref"]["id"] == f"ownerop:HEB:{x['operation_ref']}"
    assert entry["data"]["detail_path"] == f"/o01/v0/owner-operations/HEB/{x['operation_ref']}"
    assert idx["page"]["membership"] == "unknown"  # never qualified_scoped on unqualified owner records


def test_n21_work_heb_does_not_hold_eligible_is_an_allocated_owner_refusal(live: Live, cfg: dict[str, Any]):
    """A-24 N21 (WORK_NOT_CURRENTLY_ELIGIBLE). The adopted 0.2 refusal map has no code for it: the slice's interim
    PRECONDITION_STALE (gap STG02-BE-01). HEB decided, so it is an allocated, owner-identified refusal."""
    req = fresh(cfg["command"]["continue_eligible_work"], "n21")
    req["intents"] = [live.s.fx.intents["held"]]
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["reason_code"]) == ("REJECTED", "FAILED_CONFIRMED_NO_EFFECT",
                                                                          "PRECONDITION_STALE")
    assert x["operation_ref"] and live.owner_get("HEB", x["operation_ref"])[0] == 200


@pytest.mark.parametrize("name,mutate,reason", [
    ("n22-revision-changed", lambda i: i["target"].update(work_revision="fixture:revision-2"),
     "DELEGATED_GRANT_UNVERIFIED"),
    ("expired", None, "CURRENTNESS_EXPIRED"),
    ("revoked", None, "DELEGATED_GRANT_UNVERIFIED"),
    ("unknown-proof", lambda i: i.update(delegated_grant_proof_ref="fixture:delegation-never-issued"),
     "DELEGATED_GRANT_UNVERIFIED"),
    ("other-actor", lambda i: i.update(actor_ref="fixture:lead-2"), "DELEGATED_GRANT_UNVERIFIED"),
])
def test_an_unqualified_delegation_is_refused_before_any_owner_state_and_allocates_nothing(
        live: Live, cfg: dict[str, Any], name: str, mutate: Any, reason: str):
    req = fresh(cfg["command"]["continue_eligible_work"], name)
    intent = copy.deepcopy(live.s.fx.intents[{"expired": "continue-expired", "revoked": "continue-revoked"}.get(
        name, "continue")])
    if mutate:
        mutate(intent)
    req["intents"] = [intent]
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["operation_ref"], x["reason_code"]) == (
        "REJECTED", "NOT_OBSERVED", None, reason)
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_protected_and_session_actions_are_held_or_refused_with_no_owner_operation(live: Live, cfg: dict[str, Any]):
    req = fresh(cfg["command"]["protected_without_g3"], "attach")
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    assert [(x["admission_state"], x["operation_ref"], x["effect_state"], x["reason_code"]) for x in r["results"]] == \
           [("REJECTED", None, "NOT_OBSERVED", "ORIGIN_NOT_ESTABLISHED")]
    no_consent = dict(fresh(cfg["command"]["protected_without_g3"], "attach-nc"), consent_set_ref=None)
    st, h, b = live.post(no_consent)
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "invalid_request")
    cancel = copy.deepcopy(live.s.fx.intents["continue"])
    cancel.update(action="DELEGATED_CANCEL", intent_ref="fixture:intent-cancel",
                  target={"invocation_ref": "fixture:run-continue-1", "grant_ref": "fixture:grant-ticket-continue",
                          "work_ref": "fixture:ticket-continue", "work_revision": "fixture:revision-1",
                          "cancel_scope": "OWN_DELEGATED_INVOCATION", "handoff_ref": None})
    req = dict(fresh(cfg["command"]["continue_eligible_work"], "cancel"), intents=[cancel])
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    assert r["results"][0]["admission_state"] == "REJECTED"  # its delegation names another intent: never admitted
    mixed = dict(fresh(cfg["command"]["continue_eligible_work"], "mixed"),
                 intents=[*cfg["command"]["protected_without_g3"]["intents"], live.s.fx.intents["continue"]])
    st, h, b = live.post(mixed)
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "invalid_request")
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_an_identical_retry_is_a_lookup_returning_the_stored_receipt_and_never_dispatches(live: Live,
                                                                                          cfg: dict[str, Any]):
    req = fresh(cfg["command"]["continue_eligible_work"], "retry")
    first = live.post(req)[2]
    live.clock[0] = T0 + timedelta(seconds=60)  # the carrier's clock moves; the stored receipt does not
    st, _, again = live.post(req)
    assert st == 202 and again == first
    with live.s.ledger.reading() as t:
        assert len(t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0])) == 1
    for change in ({"request_set_ref": req["request_set_ref"] + "-x"}, {"intents": [live.s.fx.intents["retry"]]}):
        st, h, b = live.post({**req, **change})
        problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "request_key_conflict")


def test_a_lookup_after_read_entitlement_is_withdrawn_is_one_nondisclosing_404(live: Live, cfg: dict[str, Any]):
    known = fresh(cfg["command"]["continue_eligible_work"], "c17n03")
    op = live.post(known)[2]["results"][0]["operation_ref"]
    live.entitle(False)
    try:
        st, h, b = live.post(known)
        problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "not_found_or_not_disclosable")
        st2, _, b2 = live.post({**known, "request_set_ref": known["request_set_ref"] + "-changed"})
        assert st2 == 404 and {k: v for k, v in b2.items() if k != "correlation_id"} == \
               {k: v for k, v in b.items() if k != "correlation_id"}
        assert live.owner_get("HEB", op)[0] == 404
        assert live.get("/v1/read/waiting")[0] == 404
        # LEAD-F21's accepted residual: an unused key is a new submission, decided by its origin
        st, _, r = live.post(fresh(cfg["command"]["continue_eligible_work"], "c17n03-new"))
        assert st == 202 and r["results"][0]["admission_state"] == "ADMITTED"
    finally:
        live.entitle(True)
    assert live.owner_get("HEB", op)[0] == 200


def test_an_expired_entry_is_unresolved_and_a_dropped_receipt_never_makes_the_key_new(live: Live,
                                                                                      cfg: dict[str, Any]):
    req = fresh(cfg["command"]["continue_eligible_work"], "expiry")
    r = live.post(req)[2]
    live.clock[0] = W.parse_time(r["source_valid_until"])
    st, h, b = live.post(req)
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "unresolved_no_redispatch")
    live.clock[0] = W.parse_time(r["source_valid_until"]) + timedelta(seconds=L.RECEIPT_RETAIN_S + 60)
    st, h, b = live.post(req)  # the receipt is gone; the key is kept as a tombstone
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "unresolved_no_redispatch")
    with live.s.ledger.reading() as t:
        row = t.key(req["installation_ref"], req["recipient_ref"], req["client_request_key"])
    assert row is not None and row["receipt"] is None


def test_set_level_refusals_allocate_nothing(live: Live, cfg: dict[str, Any]):
    base = cfg["command"]["continue_eligible_work"]
    two = dict(fresh(base, "order"), intents=[live.s.fx.intents["retry"], live.s.fx.intents["continue"]])
    for body, code, st_want in ((dict(fresh(base, "inst"), installation_ref="fixture:installation-other"),
                                 "invalid_request", 400),
                                (dict(fresh(base, "rcpt"), recipient_ref=OTHER), "authentication_unqualified", 401),
                                (two, "invalid_request", 400),
                                ({"not": "a command set"}, "invalid_request", 400),
                                (dict(fresh(base, "consent"), consent_set_ref="fixture:consent-x"), "invalid_request",
                                 400)):
        st, h, b = live.post(body)
        assert st == st_want
        problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, code)
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_owner_get_is_one_nondisclosing_404_for_unknown_foreign_and_malformed(live: Live, cfg: dict[str, Any]):
    op = live.post(fresh(cfg["command"]["continue_eligible_work"], "og"))[2]["results"][0]["operation_ref"]
    answers = [live.owner_get("HEB", "op:unknown"), live.owner_get("HEB", op, {"Authorization": "Bearer token-other"}),
               live.owner_get("ADC", op), live.owner_get("HEB", "op%2Fx"),
               live.request("GET", f"/o01/v0/owner-operations/HEB/{op}")]  # no O-01 header
    for st, h, b in answers:
        problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b,
                   "not_found_or_not_disclosable")


def test_a_second_server_cannot_take_a_port_the_first_one_holds(live: Live, tmp_path: Path):
    with pytest.raises(OSError):
        SV.make_server(SV.Slice(tmp_path / "other", fixture_recipient=True), live.port)


# ------------------------------------------------------------------------------------------------- transport edges

def raw(port: int, method: str, path: str, headers: dict[str, str] | list[tuple[str, str]],
        ) -> tuple[int, dict[str, str], Any]:
    """A request whose headers this test writes itself, Host included (http.client would set the right one); a list
    of pairs may repeat a header."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        c.putrequest(method, path, skip_host=True)
        for k, v in (headers.items() if isinstance(headers, dict) else headers):
            c.putheader(k, v)
        c.endheaders()
        r = c.getresponse()
        data = r.read()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, json.loads(data) if data else None
    finally:
        c.close()


def test_a_foreign_host_or_origin_is_refused_with_the_route_familys_own_problem(live: Live):
    host = f"127.0.0.1:{live.port}"
    for hdr in ({"Host": "evil.example:80", **D01}, {"Host": host, "Origin": "http://evil.example", **D01}):
        st, h, b = raw(live.port, "GET", "/v1/read/waiting", hdr)
        problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "invalid_request")
    st, h, b = raw(live.port, "GET", "/o01/v0/owner-operations/HEB/op:abc", {"Host": "evil.example", **O01})
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b,
               "not_found_or_not_disclosable")
    st, h, b = raw(live.port, "OPTIONS", "/v1/read/waiting", {"Host": host})  # a preflight with no origin
    assert st == 400 and "access-control-allow-origin" not in h


def test_cors_is_offered_only_to_an_exactly_allowed_origin(project: dict[str, Any], tmp_path: Path):
    site = "http://127.0.0.1:4251"
    lv = Live(SV.Slice(tmp_path / "state", fixture_recipient=True, allow_origins=(site,)), [T0])
    try:
        host = f"127.0.0.1:{lv.port}"
        st, h, _ = raw(lv.port, "OPTIONS", "/o01/v0/command-sets", {"Host": host, "Origin": site})
        assert st == 204 and h["access-control-allow-origin"] == site
        assert "X-AEW-O01-Wire" in h["access-control-allow-headers"]
        st, h, b = raw(lv.port, "GET", "/v1/read/waiting", {"Host": host, "Origin": site, **D01})
        assert st == 200 and h["access-control-allow-origin"] == site and "X-AEW-Wire-Version" in \
            h["access-control-expose-headers"]
        st, h, b = raw(lv.port, "GET", "/v1/read/waiting", {"Host": host, "Origin": "http://127.0.0.1:9999", **D01})
        assert st == 400 and "access-control-allow-origin" not in h
    finally:
        lv.close()


def test_an_unexpected_error_is_the_familys_declared_503_with_its_wire_headers(live: Live, cfg: dict[str, Any],
                                                                              monkeypatch: pytest.MonkeyPatch):
    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("unexpected")
    monkeypatch.setattr(live.s.reads, "waiting", boom)
    monkeypatch.setattr(live.s.carrier, "submit", boom)
    monkeypatch.setattr(live.s.carrier, "owner_get", boom)
    st, h, b = live.get("/v1/read/waiting")
    problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "owner_unavailable")
    st, h, b = live.post(fresh(cfg["command"]["continue_eligible_work"], "boom"))
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "owner_unavailable")
    st, h, b = live.owner_get("HEB", "op:abc123")
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b, "owner_unavailable")


def test_a_ledger_lock_not_granted_in_time_is_503_and_never_a_dispatch(live: Live, cfg: dict[str, Any],
                                                                       monkeypatch: pytest.MonkeyPatch):
    import contextlib

    @contextlib.contextmanager
    def busy(*a: Any, **k: Any) -> Any:
        raise L.LedgerBusy("database is locked")
        yield
    monkeypatch.setattr(live.s.ledger, "transaction", busy)
    monkeypatch.setattr(live.s.ledger, "reading", busy)
    st, h, b = live.post(fresh(cfg["command"]["continue_eligible_work"], "busy"))
    problem_ok("O01", "post", "/o01/v0/command-sets", st, h, b, "owner_unavailable")
    st, h, b = live.get("/v1/read/waiting")
    problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "owner_unavailable")
    st, h, b = live.get("/v1/read/owner-operations")
    problem_ok("D01", "get", "/v1/read/owner-operations", st, h, b, "owner_unavailable")
    st, h, b = live.owner_get("HEB", "op:abc123")
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b, "owner_unavailable")


@pytest.mark.parametrize("observed,phase", [("running", "REPORTED_ACTIVE"),
                                            ("ended_with_evidence", "REPORTED_FINISHED"),
                                            ("lost", "UNKNOWN")])
def test_a_real_runs_phase_is_its_supervisors_reported_status(live: Live, project: dict[str, Any],
                                                              monkeypatch: pytest.MonkeyPatch, observed: str,
                                                              phase: str):
    import dataclasses

    eng = live.s.engine
    assert eng is not None
    snap = eng.snapshot()
    inv = invocation_id(project)
    state = copy.deepcopy(snap.state)
    state["invocations"][inv]["runs"] = [{"run": "run-x1", "launched_at": "2026-10-19T11:00:00Z", "harness": "fake"}]
    monkeypatch.setattr(eng, "snapshot", lambda: dataclasses.replace(snap, state=state))
    monkeypatch.setattr(eng, "observed", lambda run: observed)
    st, _, b = live.get(f"/v1/read/runs/{b64(inv)}")
    schema_ok("/v1/read/runs/{execution_id}", b)
    d = b["items"][0]["data"]
    assert d["phase"] == phase and d["started_at"] == "2026-10-19T11:00:00Z"
    assert d["phase_basis_ref"] == ("aew:run:run-x1" if phase != "UNKNOWN" else None)


def test_the_driver_config_is_written_from_the_world_its_delegations_are_bound_to(tmp_path: Path):
    out = tmp_path / "driver-config.json"
    argv = ["--state-dir", str(tmp_path / "state"), "--fixture-recipient", "--write-driver-config", str(out)]
    assert SV.main(argv) == 0
    cfg = json.loads(out.read_text(encoding="utf-8"))
    fx = SV.Slice(tmp_path / "state2", fixture_recipient=True).fx
    (intent,) = cfg["command"]["continue_eligible_work"]["intents"]
    proof = fx.delegations[intent["delegated_grant_proof_ref"]]
    assert proof["intent_digest"] == W.intent_digest(intent) and proof["status"] == "CURRENT"
    assert not A.o01_errors("CommandSet", cfg["command"]["continue_eligible_work"])
    assert all(not A.o01_errors("CommandSet", c["request"]) for c in cfg["c17_cases"].values())
    assert not any("matches_fixture" in r for r in cfg["reads"])  # every fact unqualified: no recorded envelope fits


# ------------------------------------------------------------------------------------------------- review fixes

def test_an_owner_record_past_its_retention_is_never_disclosed_even_before_any_purge(live: Live,
                                                                                    cfg: dict[str, Any]):
    """Review M2: retention is enforced on the read, not only by the purge a later submission runs."""
    op = live.post(fresh(cfg["command"]["continue_eligible_work"], "retain"))[2]["results"][0]["operation_ref"]
    assert live.owner_get("HEB", op)[0] == 200
    live.clock[0] = T0 + timedelta(seconds=L.OWNER_RECORD_RETAIN_S + 1)  # no submission since: nothing purged
    with live.s.ledger.reading() as t:
        assert t.c.execute("SELECT COUNT(*) FROM owner_ops").fetchone()[0] == 1
    st, h, b = live.owner_get("HEB", op)
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b,
               "not_found_or_not_disclosable")
    st, _, idx = live.get("/v1/read/owner-operations")
    assert st == 200 and not [i for i in idx["items"] if i["data"]["operation_ref"] == op]


def test_a_recipient_whose_read_entitlement_the_world_does_not_state_is_never_entitled(project: dict[str, Any],
                                                                                       tmp_path: Path):
    """Review M3: entitlement is stated (the world's ``read_entitled``), never presumed for an unknown recipient."""
    s = SV.Slice(tmp_path / "state", project=project["root"],
                 tokens={**TOKENS, "token-stranger": "fixture:recipient-stranger"}, test_routes=True,
                 clock=lambda: T0)
    lv = Live(s, [T0])
    try:
        stranger = {"Authorization": "Bearer token-stranger"}
        for path in ("/v1/read/waiting", "/v1/read/owner-operations",
                     f"/v1/read/continuation-state/{b64('fixture:ticket-continue')}"):
            st, h, b = lv.get(path, stranger)
            assert st == 404 and b["code"] == "not_found_or_not_disclosable", (path, b)
        assert lv.get("/v1/read/waiting", {"Authorization": "Bearer token-other"})[0] == 200
    finally:
        lv.close()


def test_real_aew_records_are_disclosed_to_the_one_real_recipient_and_to_nobody_else(live: Live,
                                                                                     project: dict[str, Any],
                                                                                     tmp_path: Path):
    """Review M4: AEW's engine has no per-recipient visibility (gap STG02-BE-16), so its records go to one recipient
    (``--real-recipient``, default the fixture operator). To any other they do not exist."""
    inv = invocation_id(project)
    other = {"Authorization": "Bearer token-other"}
    st, _, b = live.get("/v1/read/waiting", other)
    assert st == 200 and not [i for i in b["items"] if not i["data"]["work"]["id"].startswith("fixture:")]
    hidden = [live.get(f"/v1/read/runs/{b64(inv)}", other),
              live.get(f"/v1/read/continuation-state/{b64(project['blocked'])}", other)]
    assert [x[0] for x in hidden] == [404, 404]
    assert live.get(f"/v1/read/runs/{b64(inv)}")[0] == 200  # the operator still sees them
    lv = Live(SV.Slice(tmp_path / "state", project=project["root"], tokens=TOKENS, fixture_recipient=True,
                       clock=lambda: T0, real_recipient=OTHER), [T0])
    try:
        st, _, b = lv.get("/v1/read/waiting")
        assert not [i for i in b["items"] if not i["data"]["work"]["id"].startswith("fixture:")]
        assert lv.get(f"/v1/read/runs/{b64(inv)}")[0] == 404
        assert lv.get(f"/v1/read/runs/{b64(inv)}", other)[0] == 200
    finally:
        lv.close()


@pytest.mark.parametrize("name", ["X-AEW-Wire-Version", "Authorization", "Host", "Origin", "Content-Length"])
def test_a_repeated_selecting_header_is_refused_in_either_order_never_last_wins(live: Live, name: str):
    """Review M5: the stdlib would answer with the first (or the last) of a repeated header."""
    host = f"127.0.0.1:{live.port}"
    values = {"X-AEW-Wire-Version": ["0.3.4", "0.3.3"],
              "Authorization": ["Bearer token-operator", "Bearer token-other"],
              "Host": [host, f"localhost:{live.port}"], "Origin": ["http://127.0.0.1:4251", "http://127.0.0.1:4252"],
              "Content-Length": ["0", "0"]}[name]
    live.s.allow_origins = ("http://127.0.0.1:4251", "http://127.0.0.1:4252")  # each one alone would be admitted
    for vs in (values, values[::-1]):
        base = [("Host", host), (W.D01_HEADER, W.D01_VERSION)]
        hdrs = [*[(k, v) for k, v in base if k != name], *[(name, v) for v in vs]]
        st, h, b = raw(live.port, "GET", "/v1/read/waiting", hdrs)
        problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "invalid_request")
    o01 = [("Host", host), (W.O01_HEADER, W.O01_VERSION), (W.O01_HEADER, W.O01_VERSION)]
    st, h, b = raw(live.port, "GET", "/o01/v0/owner-operations/HEB/op:abc", o01)
    problem_ok("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", st, h, b,
               "not_found_or_not_disclosable")


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH", "TRACE", "HEAD", "PROPFIND"])
def test_every_method_and_every_unrouted_o01_path_answers_the_familys_problem_with_its_headers(live: Live,
                                                                                              method: str):
    """Review M6: no method reaches the stdlib's bare 501, and no O-01 path its plain 404."""
    host = f"127.0.0.1:{live.port}"
    cases = [("D01", "get", "/v1/read/waiting", "/v1/read/waiting", D01, "invalid_request"),
             ("O01", "post", "/o01/v0/command-sets", "/o01/v0/command-sets", O01, "invalid_request"),
             ("O01", "get", "/o01/v0/owner-operations/{owner}/{operation_ref}", "/o01/v0/owner-operations/HEB/op:abc",
              O01, "not_found_or_not_disclosable")]
    for api, route_method, route, path, hdr, code in cases:
        st, h, b = raw(live.port, method, path, {"Host": host, **hdr})
        if method == "HEAD":  # the headers of the answer, and no body
            assert b is None and h["content-type"] == "application/problem+json" and st in (400, 404)
            wire = W.D01_HEADER if api == "D01" else W.O01_HEADER
            assert wire.lower() in h and h["cache-control"] == "private, no-store"
        else:
            problem_ok(api, route_method, route, st, h, b, code)
    st, h, b = raw(live.port, method, "/o01/v0/nothing-here", {"Host": host, **O01})
    if method != "HEAD":
        assert st == 400 and not A.o01_openapi_errors("Problem", b) and b["code"] == "invalid_request"
    assert h[W.O01_HEADER.lower()] == W.O01_VERSION and h["cache-control"] == "private, no-store"


def test_heb_with_no_eligibility_for_the_work_holds_it_and_allocates_nothing(live: Live, cfg: dict[str, Any]):
    """Review M7: HEB_STATE_UNKNOWN is a hold (SOURCE_UNAVAILABLE), never an operation."""
    work = live.s.fx.work("fixture:ticket-retry")
    assert work is not None
    work["heb_eligibility"] = None
    req = dict(fresh(cfg["command"]["continue_eligible_work"], "heb-unknown"), intents=[live.s.fx.intents["retry"]])
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["operation_ref"], x["reason_code"]) == (
        "HELD", "NOT_OBSERVED", None, "SOURCE_UNAVAILABLE")
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_a_predecessor_from_an_earlier_heb_epoch_is_an_allocated_stale_refusal(live: Live, cfg: dict[str, Any]):
    """Review M7: HEB's state moved after the intent was written (a new epoch): HEB_STALE_PREDECESSOR, which HEB
    decides, so it is allocated."""
    live.s.fx.doc["heb"]["epoch"] = "fixture:heb-epoch-2"
    req = fresh(cfg["command"]["continue_eligible_work"], "heb-stale")
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["reason_code"]) == ("REJECTED", "FAILED_CONFIRMED_NO_EFFECT",
                                                                          "PRECONDITION_STALE")
    st, _, g = live.owner_get("HEB", x["operation_ref"])
    assert st == 200 and g["result"] == x
    with live.s.ledger.reading() as t:
        (rec,) = t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0])
    assert rec["owner_reason"] == "HEB_STALE_PREDECESSOR"


def test_a_delegated_cancel_with_a_current_bound_delegation_is_held_and_allocates_nothing(live: Live,
                                                                                         cfg: dict[str, Any]):
    """Review M8: its origin is established, but its HEB effect is not in the slice (NOT_MODELLED): a hold."""
    cancel = copy.deepcopy(live.s.fx.intents["continue"])
    cancel.update(action="DELEGATED_CANCEL", intent_ref="fixture:intent-cancel",
                  delegated_grant_proof_ref="fixture:delegation-cancel-current",
                  target={"invocation_ref": "fixture:run-continue-1", "grant_ref": "fixture:grant-ticket-continue",
                          "work_ref": "fixture:ticket-continue", "work_revision": "fixture:revision-1",
                          "cancel_scope": "OWN_DELEGATED_INVOCATION", "handoff_ref": None})
    live.s.fx.delegations["fixture:delegation-cancel-current"] = {
        "issuer_ref": "delegation:fixture", "status": "CURRENT", "intent_ref": cancel["intent_ref"],
        "actor_ref": cancel["actor_ref"], "installation_ref": live.s.fx.installation,
        "recipient_ref": live.s.fx.recipient, "intent_digest": W.intent_digest(cancel),
        "valid_until": W.utc(T0 + timedelta(hours=1))}
    req = dict(fresh(cfg["command"]["continue_eligible_work"], "cancel-held"), intents=[cancel])
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["admission_state"], x["effect_state"], x["operation_ref"], x["reason_code"]) == (
        "HELD", "NOT_OBSERVED", None, "SOURCE_UNAVAILABLE")
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_a_successor_generation_reaffirm_has_no_origin_in_the_slice_and_allocates_nothing(live: Live,
                                                                                         cfg: dict[str, Any]):
    """Review M8: A04, REAFFIRM_ELIGIBLE_CHILD_GRANTS. No authenticated successor session exists in the slice."""
    base = live.s.fx.intents["continue"]
    digest = "sha256:" + "0" * 64
    reaffirm = {
        "intent_ref": "fixture:intent-reaffirm", "action": "REAFFIRM_ELIGIBLE_CHILD_GRANTS",
        "actor_ref": base["actor_ref"], "authority_class": "CURRENT_SUCCESSOR_GENERATION", "owner_hint": "ADC",
        "subject": copy.deepcopy(base["subject"]), "predecessor": copy.deepcopy(base["predecessor"]),
        "origin_proof_ref": None, "delegated_grant_proof_ref": None,
        "target": {"child": {"child_ref": "fixture:child-1", "prior_grant_ref": "fixture:grant-child-1",
                             "work_ref": "fixture:ticket-continue", "work_revision": "fixture:revision-1",
                             "prior_grant_version": "fixture:grant-v1",
                             "predecessor_generation": "fixture:generation-1",
                             "scope_digest": digest, "constraints_digest": digest,
                             "prior_grant_expiry": "2026-10-19T13:00:00Z"},
                   "successor_attachment_ref": "fixture:attachment-lead-2",
                   "successor_generation": "fixture:generation-2", "successor_lead_ref": "fixture:lead-2",
                   "recovery_classification_ref": "fixture:recovery-1",
                   "recovery_classification_version": "fixture:recovery-v1",
                   "recovery_classification_issuer_ref": "fixture:recovery-issuer",
                   "successor_generation_basis_ref": "fixture:generation-basis-2",
                   "successor_generation_version": "fixture:generation-v2",
                   "successor_seat_epoch": "fixture:seat-epoch-2"}}
    req = dict(fresh(cfg["command"]["continue_eligible_work"], "reaffirm"), intents=[reaffirm], consent_set_ref=None)
    assert not A.o01_errors("CommandSet", req)
    st, h, r = live.post(req)
    receipt_ok(req, st, h, r, T0)
    (x,) = r["results"]
    assert (x["owner"], x["admission_state"], x["operation_ref"], x["reason_code"]) == (
        "ADC", "REJECTED", None, "ORIGIN_NOT_ESTABLISHED")
    with live.s.ledger.reading() as t:
        assert t.owner_ops(live.s.fx.installation, live.s.fx.recipient, live.clock[0]) == []


def test_a_cursor_is_refused_once_the_visible_set_it_was_issued_for_has_changed(live: Live):
    """Review M8: the cursor binds the visible set, not only the recipient and the page size."""
    st, _, first = live.get("/v1/read/waiting?limit=1")
    cur = first["page"]["next_cursor"]
    work = live.s.fx.work("fixture:ticket-retry")
    assert work is not None and work["waiting"] is None
    work["waiting"] = {"cause": "dependency", "responsible_owner": "WIS", "progress": "blocked", "narrative": None}
    st, h, b = live.get(f"/v1/read/waiting?limit=1&cursor={cur}")
    problem_ok("D01", "get", "/v1/read/waiting", st, h, b, "cursor_stale_or_unauthorized")
