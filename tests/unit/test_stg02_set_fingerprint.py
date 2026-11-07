"""E82: the command set's fingerprint is A-24's frozen SW-02 algorithm (profile CS-03), which G3-C binds consent to.

The known answers are the adopted A-24 package's own: each fixture case's request with the ``consent_set_digest`` its
owner operation records (``tests/fixtures/stg02/a24-sw02-set-digests.json``, copied unchanged with the package's
sha256). A value AEW disagrees with is a finding against AEW, never a fixture to edit."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from aew.stg02 import wire as W

VECTORS_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "stg02" / "a24-sw02-set-digests.json"
VECTORS = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
FIELDS = ("request_set_ref", "recipient_ref", "installation_ref", "intents")


def by_case(case: str) -> dict[str, Any]:
    return next(v for v in VECTORS["vectors"] if v["case"] == case)


def test_the_known_answers_are_the_adopted_packages_and_cover_a_two_member_set():
    """The fixture is what it says: A-24's adopted package (its verified sha256), one case per distinct digest, and
    among them a set of two members, so the fingerprint's member order is known too."""
    assert VECTORS["source"]["package_sha256"] == "7fc128f576f22ba9be995a2d334d6e4245f6594d2cd5e2b3a80b4002b1899e22"
    digests = [v["set_digest"] for v in VECTORS["vectors"]]
    assert len(digests) == len(set(digests)) == 21
    assert {len(v["request"]["intents"]) for v in VECTORS["vectors"]} == {1, 2}


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["case"])
def test_the_set_fingerprint_is_a24s_sw02_digest_of_each_adopted_case(vector: dict[str, Any]):
    """CS-03: lowercase hex SHA-256 of the canonical JSON of the four fields, exactly as A-24's oracle computed it."""
    assert W.set_digest(vector["request"]) == vector["set_digest"]


def test_only_the_four_fields_are_fingerprinted():
    """CS-03 and SW-02: ``wire_version``, ``client_request_key`` and ``consent_set_ref`` are outside the fingerprint
    (the client key binds the whole request instead); each of the four fields is inside it."""
    v = by_case("P01")
    req = v["request"]
    assert set(FIELDS) <= set(req) and {"wire_version", "client_request_key", "consent_set_ref"} <= set(req)
    for outside in ("wire_version", "client_request_key", "consent_set_ref"):
        assert W.set_digest({**req, outside: "fixture:other"}) == v["set_digest"], outside
        assert W.full_digest({**req, outside: "fixture:other"}) != W.full_digest(req), outside
    for inside in FIELDS[:3]:
        assert W.set_digest({**req, inside: req[inside] + "x"}) != v["set_digest"], inside
    assert W.set_digest({**req, "intents": []}) != v["set_digest"]


def test_the_member_order_is_part_of_the_fingerprint():
    """CS-01 orders members by ``intent_ref``, and the fingerprint is over that order: the adopted two-member set's
    known answer holds as submitted, and the same members reversed fingerprint differently."""
    v = by_case("P08")
    req = v["request"]
    assert len(req["intents"]) == 2
    assert [i["intent_ref"] for i in req["intents"]] == sorted(i["intent_ref"] for i in req["intents"])
    assert W.set_digest(req) == v["set_digest"]
    reversed_set = {**req, "intents": list(reversed(req["intents"]))}
    assert W.set_digest(reversed_set) != v["set_digest"]


def test_the_canonical_bytes_are_ascii_escaped_key_sorted_and_compact():
    """SW-02's canonical bytes: keys in codepoint order at every depth, no insignificant whitespace, non-ASCII escaped,
    and no float that is not a number (the fingerprint is cross-language)."""
    assert W.canonical({"b": 1, "a": {"d": [1, 2], "c": "é"}}) == b'{"a":{"c":"\\u00e9","d":[1,2]},"b":1}'
    with pytest.raises(ValueError):
        W.canonical({"x": float("nan")})
    req = copy.deepcopy(by_case("P01")["request"])
    shuffled = {k: req[k] for k in reversed(list(req))}
    assert W.set_digest(shuffled) == W.set_digest(req)  # the submitter's key order is not the fingerprint's
