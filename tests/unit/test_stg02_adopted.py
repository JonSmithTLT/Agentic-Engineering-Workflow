"""STG-02: the vendored adopted files are the sealed v0.5.4 bytes, the path-id codec is the profile's, and the fixture
world can never pass a fact off as real."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aew.stg02 import adopted as A
from aew.stg02 import wire as W
from aew.stg02.world import WORLD_PATH, Fixture

T0 = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)


def test_every_vendored_adopted_file_matches_its_sealed_pin_and_nothing_else_is_vendored():
    names = {p.name for p in A.HERE.iterdir()}
    assert names == set(A.PINS)
    for name, (_, sha) in A.PINS.items():
        assert hashlib.sha256((A.HERE / name).read_bytes()).hexdigest() == sha
        A.load(name)


def test_an_edited_adopted_file_is_refused_at_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    edited = tmp_path / "adopted"
    edited.mkdir()
    for name in A.PINS:
        (edited / name).write_bytes((A.HERE / name).read_bytes())
    (edited / "command-set-problems.json").write_bytes(b"{}")
    monkeypatch.setattr(A, "HERE", edited)
    A.load.cache_clear()
    try:
        with pytest.raises(A.AdoptedFileChanged):
            A.load("command-set-problems.json")
    finally:
        A.load.cache_clear()


@pytest.mark.parametrize("text", ["fixture:ticket-continue", "T-0001", "x/y:z", "caf\u00e9"])
def test_a_canonical_id_round_trips(text: str):
    assert W.decode_id(W.b64url(text)) == text


@pytest.mark.parametrize("segment", [W.b64url("abc") + "=", "YWJj+", "YW%2Fj", "", "_w", "4pyT4p",
                                     W.b64url("cafe\u0301")])
def test_a_noncanonical_id_is_refused(segment: str):
    with pytest.raises(W.BadId):
        W.decode_id(segment)


def test_every_identifier_in_the_fixture_world_is_labelled(tmp_path: Path):
    fx = Fixture.load(T0)
    for i in fx.intents.values():
        assert all(str(v).startswith("fixture:") for k, v in i.items() if k.endswith("_ref") and v)
    doc = json.loads(WORLD_PATH.read_text(encoding="utf-8"))
    doc["work"][0]["work_ref"] = "ticket:unlabelled"
    bad = tmp_path / "unlabelled-world.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="not labelled"):
        Fixture.load(T0, bad)


def test_a_delegation_is_bound_to_the_exact_intent_its_world_names():
    fx = Fixture.load(T0)
    for d in fx.delegations.values():
        intent = next(i for i in fx.intents.values() if i["intent_ref"] == d["intent_ref"])
        assert d["intent_digest"] == W.intent_digest(intent) and d["issuer_ref"] == "delegation:fixture"
