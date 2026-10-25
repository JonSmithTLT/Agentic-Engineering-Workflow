"""The STG-02 families of the generated reference (STG-12 S12-2, family 6b, the designer's second addendum):
``stg02-routes``, ``commands`` and ``command-refusals`` (``tools/reference_families/stg02*.py``).

A static enumeration that feeds a label is asserted equal to the registry it models, in both directions: the route
records to the vendored matrix, the command records to the vendored action registry (and the registry to the refusal
map), the refusal records to the two tables the lookup reads. Two readings of the source (``ast`` and ``re``, sharing
no code) agree on ``server.py`` and on ``commands.py``, and each static fact is checked against an observation: a
request to every matrix route, with the owners replaced by spies, reaches an owner through exactly the routes the
reading says are served, and a command set for three representative actions reaches the owner's state through exactly
the action the reading says does.

The heavy lanes run this because it reads ``src`` and the vendored files only: a pull request that changes the wire
changes ``src`` and so runs the full gate. The planted controls of the pure rules are in
``tests/unit/test_reference_stg02_controls.py``.
"""

from __future__ import annotations

import ast
import copy
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from aew.stg02 import adopted as A
from aew.stg02 import commands as COMMANDS
from aew.stg02 import server as SV
from aew.stg02 import wire as W

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, stg02_commands, stg02_commands_text, stg02_server, stg02_server_text
    finally:
        sys.path.remove(here)
    return common, stg02_commands, stg02_commands_text, stg02_server, stg02_server_text


C, K, KT, S, ST = _tool_modules()
CTX = C.Context(ROOT)
T0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)


@cache
def records(family: str) -> dict[str, dict[str, Any]]:
    built = [*S.build(CTX), *K.build(CTX)]
    return {r.key: r.as_json() for r in built if r.family == family}


# ------------------------------------------------------------------------------------------------------ the routes

def test_the_route_records_are_the_matrix_both_ways():
    found = records("stg02-routes")
    pairs = {(str(row["method"]).upper(), str(row["route"])): str(row["api"]) for row in A.matrix()}
    matrix = {k: r for k, r in found.items() if not r["fact"]["test_only"]}
    assert set(matrix) == {f"{m} {route}" for m, route in pairs}
    assert len(pairs) == 22, "the vendored matrix has 22 distinct routes"
    for method, route in pairs:
        fact = matrix[f"{method} {route}"]["fact"]
        assert fact == {"route": route, "method": method, "served": fact["served"], "test_only": False}
        assert matrix[f"{method} {route}"]["anchor"] == {"module": "aew.stg02.adopted", "symbol": "matrix"}
    test_only = {k: r["fact"] for k, r in found.items() if r["fact"]["test_only"]}
    assert test_only == {
        "POST /_test/engine-outage": {"route": "/_test/engine-outage", "method": "POST", "served": True,
                                      "test_only": True},
        "POST /_test/read-entitlement": {"route": "/_test/read-entitlement", "method": "POST", "served": True,
                                         "test_only": True}}
    served = {k for k, r in matrix.items() if r["fact"]["served"]}
    assert served == {"GET /v1/read/waiting", "GET /v1/read/owner-operations", "GET /v1/read/runs/{execution_id}",
                      "GET /v1/read/continuation-state/{work_id}", "POST /o01/v0/command-sets",
                      "GET /o01/v0/owner-operations/{owner}/{operation_ref}"}
    assert all(r["basis"] == "static" and r["coverage"]["label"] == "lower-bound" for r in found.values())


def server_text() -> tuple[ast.Module, str]:
    src = CTX.sources()[S.SERVER]
    assert src.tree is not None
    return src.tree, src.text


def test_the_two_server_detectors_agree_on_the_server():
    tree, text = server_text()
    ours = S.read(tree, vars(SV))
    assert ours == ST.read(text, vars(SV))
    assert ours.exact and ours.prefixes and ours.patterns


def test_a_detector_made_blind_makes_the_server_agreement_test_fail(monkeypatch):
    """The control of the agreement test itself: with either reading blind, the server no longer agrees."""
    tree, text = server_text()
    assert S.read(tree, vars(SV)) == ST.read(text, vars(SV))
    blind = S.Reading([], [], [], {})
    monkeypatch.setattr(S, "read", lambda tree, values: blind)
    assert S.read(tree, vars(SV)) != ST.read(text, vars(SV))
    monkeypatch.undo()
    monkeypatch.setattr(ST, "read", lambda text, values: blind)
    assert S.read(tree, vars(SV)) != ST.read(text, vars(SV))


class SpyReads:
    """Stands in for the slice's reads: records which read a request reached, answers an empty body."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def waiting(self, *args: Any) -> dict[str, Any]:
        self.calls.append("waiting")
        return {}

    def owner_operations(self, *args: Any) -> dict[str, Any]:
        self.calls.append("owner_operations")
        return {}

    def run(self, *args: Any) -> dict[str, Any]:
        self.calls.append("run")
        return {}

    def continuation(self, *args: Any) -> dict[str, Any]:
        self.calls.append("continuation")
        return {}


class SpyCarrier:
    """Stands in for the command carrier: records which of its two entry points a request reached."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def submit(self, req: Any, recipient: str, now: datetime) -> tuple[dict[str, Any], bool]:
        self.calls.append("submit")
        return {}, False

    def owner_get(self, owner: str, op: str, recipient: str, now: datetime) -> dict[str, Any]:
        self.calls.append("owner_get")
        return {}


def request(s: SV.Slice, method: str, route: str, api: str) -> int:
    sample = W.b64url("fixture:sample-1") if api == "D01" else "sample01"
    path = re.sub(r"\{[^}]+\}", sample, route)
    name, version = (W.D01_HEADER, W.D01_VERSION) if api == "D01" else (W.O01_HEADER, W.O01_VERSION)
    headers = {name.lower(): version}
    body = None
    if method == "POST":
        headers["content-type"] = W.JSON_TYPE
        body = b"{}"
    return SV.handle(s, method, path, headers, body).status


def test_the_served_routes_are_the_ones_a_request_reaches_an_owner_through(tmp_path):
    """The reading is static; this is the observation. A request to every route of the matrix, the slice's reads and
    carrier replaced by spies, reaches an owner exactly when the reading says the route is served."""
    s = SV.Slice(tmp_path / "state", fixture_recipient=True, test_routes=True, clock=lambda: T0)
    pairs = {(str(r["method"]).upper(), str(r["route"])): str(r["api"]) for r in A.matrix()}
    for (method, route), api in pairs.items():
        reads, carrier = SpyReads(), SpyCarrier()
        s.reads, s.carrier = reads, carrier  # type: ignore[assignment]
        request(s, method, route, api)
        observed = bool(reads.calls or carrier.calls)
        assert observed is records("stg02-routes")[f"{method} {route}"]["fact"]["served"], (method, route)


def test_a_test_route_is_served_only_with_the_test_routes_switch(tmp_path):
    body = json.dumps({"recipient_ref": "fixture:recipient-operator", "entitled": False}).encode()
    headers = {"content-type": W.JSON_TYPE}
    for path in ("/_test/read-entitlement", "/_test/engine-outage"):
        on = SV.Slice(tmp_path / "on", fixture_recipient=True, test_routes=True, clock=lambda: T0)
        off = SV.Slice(tmp_path / "off", fixture_recipient=True, test_routes=False, clock=lambda: T0)
        assert SV.handle(off, "POST", path, headers, body).status == 404
        assert SV.handle(on, "POST", path, headers, body).status != 404
    on = SV.Slice(tmp_path / "on", fixture_recipient=True, test_routes=True, clock=lambda: T0)
    assert SV.handle(on, "GET", "/_test/read-entitlement", headers, None).status == 404  # the route requires POST


# ----------------------------------------------------------------------------------------------------- the commands

def test_the_command_records_are_the_registry_both_ways():
    found = records("commands")
    registry = A.registry()
    assert set(found) == set(registry)
    assert set(registry) == set(A.refusals()), "an action of the registry has no refusal map, or the map has a stranger"
    for action, row in registry.items():
        fact = found[action]["fact"]
        assert (fact["action"], fact["origin"], fact["owner"]) == (action, row["origin"], row["sole_admitting_owner"])
        assert isinstance(fact["reaches_owner"], bool)
        assert (found[action]["anchor"], found[action]["basis"]) == (
            {"module": "aew.stg02.adopted", "symbol": "registry"}, "enumerated")
        assert found[action]["coverage"]["label"] == "complete-by-construction"


def commands_source() -> tuple[ast.Module, str]:
    src = CTX.sources()[K.COMMAND_MODULE]
    assert src.tree is not None
    return src.tree, src.text


def test_the_two_command_detectors_agree_on_the_source():
    tree, text = commands_source()
    ours = K.read(tree)
    assert ours == KT.read(text)
    assert (ours.origin, ours.action) == ("CURRENT_DELEGATED_GRANT", "CONTINUE_ELIGIBLE_WORK")
    assert ours.causes and ours.delegation and ours.unreadable == []


def make_slice(tmp_path: Path) -> SV.Slice:
    return SV.Slice(tmp_path / "state", fixture_recipient=True, clock=lambda: T0)


def owner_reached(s: SV.Slice, req: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """The actions whose member went on to the owner's state (``_heb_continue``), and the results of the receipt."""
    reached: list[str] = []
    real = s.carrier._heb_continue

    def spy(i: dict[str, Any], t: Any) -> dict[str, Any]:
        reached.append(i["action"])
        return real(i, t)

    s.carrier._heb_continue = spy  # type: ignore[method-assign]
    receipt, _ = s.carrier.submit(req, s.fx.recipient, T0)
    return reached, receipt["results"]


def test_only_the_continue_action_reaches_an_owner_by_the_reading_and_by_a_request(tmp_path):
    """The reading says one action goes on to an owner. A request for a protected action, for a delegated action that
    is not that one (with a current, bound delegation, so its origin is established) and for that one agrees."""
    reaches = {action: r["fact"]["reaches_owner"] for action, r in records("commands").items()}
    assert [a for a, yes in reaches.items() if yes] == ["CONTINUE_ELIGIBLE_WORK"]

    s = make_slice(tmp_path / "continue")
    cfg = SV.driver_config(s)
    reached, results = owner_reached(s, copy.deepcopy(cfg["command"]["continue_eligible_work"]))
    assert reached == ["CONTINUE_ELIGIBLE_WORK"] and len(results) == 1

    s = make_slice(tmp_path / "protected")
    reached, results = owner_reached(s, copy.deepcopy(SV.driver_config(s)["command"]["protected_without_g3"]))
    assert reached == [] and results[0]["reason_code"] == "ORIGIN_NOT_ESTABLISHED"

    s = make_slice(tmp_path / "cancel")
    cancel = copy.deepcopy(s.fx.intents["continue"])
    cancel.update(action="DELEGATED_CANCEL", intent_ref="fixture:intent-cancel",
                  delegated_grant_proof_ref="fixture:delegation-cancel-current",
                  target={"invocation_ref": "fixture:run-continue-1", "grant_ref": "fixture:grant-ticket-continue",
                          "work_ref": "fixture:ticket-continue", "work_revision": "fixture:revision-1",
                          "cancel_scope": "OWN_DELEGATED_INVOCATION", "handoff_ref": None})
    s.fx.delegations["fixture:delegation-cancel-current"] = {
        "issuer_ref": "delegation:fixture", "status": "CURRENT", "intent_ref": cancel["intent_ref"],
        "actor_ref": cancel["actor_ref"], "installation_ref": s.fx.installation, "recipient_ref": s.fx.recipient,
        "intent_digest": W.intent_digest(cancel), "valid_until": W.utc(T0 + timedelta(hours=1))}
    req = dict(copy.deepcopy(SV.driver_config(s)["command"]["continue_eligible_work"]), intents=[cancel])
    reached, results = owner_reached(s, req)
    assert reached == [] and results[0]["reason_code"] == "SOURCE_UNAVAILABLE"  # its effect is not modelled: a hold
    assert reaches["DELEGATED_CANCEL"] is False and reaches["ATTACH_LEAD"] is False


# ---------------------------------------------------------------------------------------------------- the refusals

def test_the_refusal_records_are_the_two_tables_both_ways():
    found = records("command-refusals")
    vendored, own = A.refusals(), COMMANDS.SLICE_OWNER_REASONS
    want = {f"{action}:{cause}": ("vendored", reason) for action, causes in vendored.items()
            for cause, reason in causes.items()}
    for action, causes in own.items():
        for cause, reason in causes.items():
            want.setdefault(f"{action}:{cause}", ("code", reason))
    assert set(found) == set(want) and len(found) == len(want)
    for key, (source, reason) in want.items():
        fact = found[key]["fact"]
        assert (fact["action"], fact["cause"], fact["reason"], fact["source"]) == (
            *key.split(":"), reason, source)
        anchor = found[key]["anchor"]
        owner = ("aew.stg02.adopted", "refusals") if source == "vendored" else ("aew.stg02.commands",
                                                                                "SLICE_OWNER_REASONS")
        assert (anchor["module"], anchor["symbol"]) == owner
    assert {r["fact"]["source"] for r in found.values()} == {"vendored", "code"}
    assert {r["coverage"]["label"] for r in found.values()} == {"complete-by-construction"}


def test_every_refusal_result_comes_through_the_one_lookup():
    """A refusal is built in one function, which fails closed. The places that make a result with a ``reason_code``
    are the declared ones, both ways; the cause literals the code spells are keys of some table; and the lookup
    returns exactly a table's reason for each pair it names and refuses every pair it does not."""
    tree, _ = commands_source()
    reading = K.read(tree)
    assert set(reading.builders) == K.BUILDERS, sorted(set(reading.builders) ^ K.BUILDERS)
    tables = (A.refusals(), COMMANDS.SLICE_OWNER_REASONS)
    named = {cause for table in tables for causes in table.values() for cause in causes}
    assert set(reading.causes) <= named, sorted(set(reading.causes) - named)
    assert set(reading.delegation) <= set(reading.causes)
    for action, causes in {**A.refusals(), **{a: {**A.refusals().get(a, {}), **c}
                                              for a, c in COMMANDS.SLICE_OWNER_REASONS.items()}}.items():
        for cause, reason in causes.items():
            result = COMMANDS.refusal(action, cause)
            assert result["reason_code"] == reason and result["owner_reason"] == cause
            assert result["outcome"] == ("HELD" if reason == "SOURCE_UNAVAILABLE" else "REFUSED")
        with pytest.raises(AssertionError, match="no reason code"):
            COMMANDS.refusal(action, "A_CAUSE_NO_TABLE_NAMES")
    with pytest.raises(AssertionError, match="no reason code"):
        COMMANDS.refusal("AN_ACTION_NO_TABLE_NAMES", "ORIGIN_NOT_ESTABLISHED")
