"""The overlay of what G3 reads beyond the sealed files: it carries A-43's ``SET_STEERING_MODE`` forward with one
difference, never changes a sealed file, and reaches the G3 service and client only (the designer's ruling on PR C3)."""

from __future__ import annotations

import copy
import hashlib
import json
import tomllib
from pathlib import Path

import pytest

from aew import g3client
from aew.stg02 import adopted as A
from aew.stg02 import commands
from aew.stg02 import g3_overlay as O
from aew_g3 import render, wire
from g3 import PIN, make

REPO = Path(__file__).resolve().parents[2]
A43 = REPO / "docs" / "contracts" / "A-43"
ACTION = "SET_STEERING_MODE"
# The pins as adopted: a change to any is a change to a sealed contract
SEALED = {"extended-action-registry.json": "fbc95cf6ed57263bed8a94a00922c13180341f470161975d1833f0cff5cdc210",
          "o01-extended-command.schema.json": "17f28b3f312bf3cb5f9f134803f68909aef1f49827c655c40deef85556c35f09",
          "new-command-refusal-reasons.json": "d54ab0ffd6bd1b40ff7d32b3233e097086069f77152fe6010e67a9e1485c219e"}
G3_WIRE_PIN = "62b67dcab151f454a4af0c8f48e301299af8a90e009a1e70be81cba51f6c5e1c"


def _a43(name: str):
    return json.loads((A43 / name).read_text(encoding="utf-8"))


def raise_set() -> dict:
    from aew.harness.g3_adapter import raise_set as build

    return build({"project": "project-one", "mode": "run", "previous": "crawl", "mode_rev": 7, "generation": 3,
                  "legality_digest": "a" * 64})


def test_every_sealed_pin_is_unchanged():
    for name, sha in SEALED.items():
        assert A.PINS[name][1] == sha
        assert hashlib.sha256((A.HERE / name).read_bytes()).hexdigest() == sha
    assert wire.SCHEMA_SHA256 == G3_WIRE_PIN


def test_the_overlay_equals_a43_apart_from_the_owner_label():
    row = O.registry()[ACTION]
    theirs = next(r for r in _a43("action-registry-0.9.json") if r["action"] == ACTION)
    assert {**row, "sole_admitting_owner": "R01"} == theirs and row["sole_admitting_owner"] == "ADC"
    schema = _a43("o01-command-0.9.schema.json")["$defs"]
    assert O.o01_schema()["$defs"]["SET_STEERING_MODETarget"] == schema["SET_STEERING_MODETarget"]
    branch = next(b for b in O.o01_schema()["$defs"]["Intent"]["allOf"]
                  if b["if"]["properties"]["action"]["const"] == ACTION)
    other = copy.deepcopy(next(b for b in schema["Intent"]["allOf"]
                               if b["if"]["properties"]["action"].get("const") == ACTION))
    assert other["then"]["properties"]["owner_hint"]["const"] == "R01"
    other["then"]["properties"]["owner_hint"]["const"] = "ADC"
    assert branch == other


def test_the_overlay_holds_that_one_action_and_nothing_else():
    """The equality above finds its entries by name, so an added one has to be refused here."""
    doc = O._document()
    assert [row["action"] for row in doc["rows"]] == [ACTION]
    assert list(doc["definitions"]) == ["SET_STEERING_MODETarget"]
    assert [b["if"]["properties"]["action"]["const"] for b in doc["branches"]] == [ACTION]


def test_the_wheel_ships_the_overlay():
    """The service reads it at construction, from its installed wheel, so a wheel without it cannot start."""
    data = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8"))
    package = O.FILE.parents[1]
    shipped = {p for glob in data["tool"]["setuptools"]["package-data"]["aew.stg02"] for p in package.glob(glob)}
    assert O.FILE in shipped


def test_adc_is_in_the_pinned_g3_wire_and_r01_is_not():
    owners = wire.schema()["$defs"]["ConsumeRequest"]["properties"]["owner"]["enum"]
    assert "ADC" in owners and "R01" not in owners


def test_an_overlay_row_or_definition_that_collides_with_a_sealed_one_refuses_at_load():
    doc = {"rows": [{"action": "ATTACH_LEAD"}], "definitions": {}, "branches": []}
    with pytest.raises(O.OverlayCollision):
        O.check(doc, A.registry(), A.load(O.SCHEMA))
    doc = {"rows": [], "definitions": {"ATTACH_LEADTarget": {}}, "branches": []}
    with pytest.raises(O.OverlayCollision):
        O.check(doc, A.registry(), A.load(O.SCHEMA))


def test_the_carrier_and_the_sealed_accessors_never_see_the_overlay():
    assert ACTION not in A.registry() and ACTION not in commands.REGISTRY
    assert A.o01_errors("CommandSet", g3client.with_proofs(g3client.check_set(raise_set())))


def test_g3s_side_reads_the_overlay():
    assert wire.registry()[ACTION]["origin"] == "PROTECTED_G3"
    assert wire.o01_errors(g3client.with_proofs(raise_set())) == []
    assert g3client.check_set(raise_set())["intents"][0]["action"] == ACTION


def test_the_set_this_action_builds_passes_the_service_and_the_confirmer_shows_every_target_field(tmp_path):
    from aew_g3_confirm import core

    service = make(tmp_path / "g3").svc
    status, pending = service.request({"wire_version": wire.WIRE, "command_set": g3client.with_proofs(raise_set())})
    assert status == 201, pending
    shown = core.rows(pending)
    text = "\n".join(f"{label} {value}" for label, value in shown)
    target = raise_set()["intents"][0]["target"]
    for field, value in target.items():
        assert field in text, field
        assert (str(value) if value is not None else "") in text
    status, record = service.decide(pending["approval_ref"], {"decision": "APPROVE", "pin": PIN})
    assert status == 200, record


def test_this_actions_member_fits_the_wires_rendering_bound():
    limits = render.member_line_limits(wire.o01_schema(), wire.registry())
    assert limits[ACTION] <= 30, "R2-1: the wire's 243 lines allow 30 per member"


def test_an_o01_set_naming_this_action_fails_at_the_carriers_set_check_and_burns_no_consent(tmp_path, monkeypatch):
    """With a counting G3: the carrier refuses the set before any consume. It has no owner for this action."""
    calls: list[tuple] = []
    monkeypatch.setattr(g3client, "_g3", lambda *a, **k: calls.append(a) or (200, {}))
    approved = dict(g3client.with_proofs(raise_set()), consent_set_ref="consent:g3:" + "b" * 32)

    class Fixture:
        installation = approved["installation_ref"]
        doc = {"receipt_valid_s": 60}

    carrier = commands.Carrier.__new__(commands.Carrier)
    carrier.fx = Fixture()
    with pytest.raises(commands.Refused) as refused:
        carrier.submit(approved, approved["recipient_ref"], None)
    assert refused.value.args[0] == "STRUCTURAL"
    assert calls == []
