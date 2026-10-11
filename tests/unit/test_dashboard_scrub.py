"""F20: ``projections.scrub``, the second display layer behind the projections' allowlist: the engine's verifier
masking and its credential redaction (``aew.harness.contract.redact``) over JSON-native structure, refusing anything
else.

The credential-shaped value is built here from the engine's credential pattern at run time; it is not a credential.
"""

from __future__ import annotations

import enum
import json
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType

import pytest

from aew.dashboard import projections as P
from aew.dashboard.projections import Projector
from aew.engine.archive_ops import redact
from aew.harness import contract as K

SHAPED = "aew1." + "tk_" + "0123456789abcdef" + "." + "S" * 12 + "_" + "s" * 12  # matches K.CREDENTIAL_RE
MARKER = K.redact(SHAPED)


def test_the_shaped_value_matches_the_engines_pattern():
    assert K.CREDENTIAL_RE.fullmatch(SHAPED) and SHAPED not in MARKER


def test_scrub_masks_verifiers():
    body = {"tokens": [{"id": "TK-1", "verifier": "sha256:abc"}], "nested": {"verifier": {"any": "shape"}}}
    assert P.scrub(body) == {"tokens": [{"id": "TK-1", "verifier": "<redacted>"}],
                             "nested": {"verifier": "<redacted>"}}


@pytest.mark.parametrize("body, expected", [
    ({"rows": ({"id": "TK-1", "verifier": "v"},)}, {"rows": [{"id": "TK-1", "verifier": "<redacted>"}]}),
    ([({"verifier": "v"}, [{"verifier": "v"}])], [[{"verifier": "<redacted>"}, [{"verifier": "<redacted>"}]]]),
    (({"a": ({"b": [({"verifier": "v", "c": 1},)]},)},),
     [{"a": [{"b": [[{"verifier": "<redacted>", "c": 1}]]}]}]),
    ({"x": [[[{"y": ({"verifier": ["v"]},)}]]]}, {"x": [[[{"y": [{"verifier": "<redacted>"}]}]]]}),
])
def test_scrub_masks_a_verifier_at_any_depth(body, expected):
    assert P.scrub(body) == expected


def test_scrub_applies_the_engines_credential_redaction_to_every_string():
    body = {"title": f"see {SHAPED} here", "items": [SHAPED, (f"x{SHAPED}", 3)], f"key {SHAPED}": True,
            "count": 2, "ratio": 0.5, "flag": False, "none": None}
    out = P.scrub(body)
    assert SHAPED not in repr(out)
    assert out["title"] == f"see {MARKER} here" and out["items"] == [MARKER, [f"x{MARKER}", 3]]
    assert out[f"key {MARKER}"] is True
    assert (out["count"], out["ratio"], out["flag"], out["none"]) == (2, 0.5, False, None)


def test_scrub_redacts_a_plain_leaf_as_its_str():
    when = datetime(2026, 1, 1, tzinfo=UTC)
    ident = uuid.UUID(int=7)
    out = P.scrub({"path": PurePosixPath(f"/x/{SHAPED}"), "at": when, "day": date(2026, 1, 2),
                   "b": SHAPED.encode(), "n": Decimal("1.5"), "id": ident})
    assert out == {"path": f"/x/{MARKER}", "at": str(when), "day": "2026-01-02", "b": str(SHAPED.encode()).replace(
        SHAPED, MARKER), "n": "1.5", "id": str(ident)}
    assert SHAPED not in json.dumps(out)


def test_scrub_emits_scalar_and_string_subclasses_as_plain_values():
    class Label(StrEnum):
        A = "x " + SHAPED

    class Count(IntEnum):
        ONE = 1

    class Colour(enum.Enum):
        RED = "red"

    out = P.scrub({"v": Label.A, "n": Count.ONE, "c": Colour.RED})
    assert type(out["v"]) is str and out["v"] == f"x {MARKER}"
    assert type(out["n"]) is int and out["n"] == 1 and out["c"] == "Colour.RED"


@dataclass
class Row:
    id: str
    verifier: str


class Thing:
    def __str__(self) -> str:
        return "thing"


@pytest.mark.parametrize("value", [
    {"x", "y"}, frozenset({"x"}), Row("TK-1", "v"), MappingProxyType({"verifier": "v"}), (v for v in [1]), Thing(),
    {1: "an integer key"},
], ids=["set", "frozenset", "dataclass", "mapping", "generator", "object", "non-string-key"])
def test_scrub_refuses_what_is_not_json_native_structure(value):
    with pytest.raises(TypeError):
        P.scrub({"rows": [value]})


def test_a_dict_subclass_is_walked_as_a_dict():
    assert P.scrub(OrderedDict(verifier="v", a=SHAPED)) == {"verifier": "<redacted>", "a": MARKER}


def test_scrub_is_idempotent():
    once = P.scrub({"a": SHAPED, "verifier": "v", "t": (1, PurePosixPath("/p"))})
    assert P.scrub(once) == once


def test_the_engines_verifier_masking_walks_tuples():
    assert redact({"rows": ({"verifier": "v"},)}) == {"rows": [{"verifier": "<redacted>"}]}


def test_an_activity_title_is_redacted_before_it_is_cut():
    """A credential straddling the title's cut never leaves a prefix of itself behind."""
    pad = "x" * (1000 - len("op: ") - 30)
    record = {"revision": 7, "at": "2026-01-01T00:00:00Z", "op": "op", "summary": pad + SHAPED}
    title = Projector._activity(None, record)["title"]  # type: ignore[arg-type]  # uses no projector state
    assert SHAPED[:30] not in title and len(title) <= 1000


class _Reply:
    """Records what ``DashboardServer._send`` writes."""

    def __init__(self) -> None:
        self.status: int | None = None
        self.body = b""

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status = code

    def send_header(self, keyword: str, value: str) -> None:
        pass

    def end_headers(self) -> None:
        pass

    @property
    def wfile(self) -> _Reply:
        return self

    def write(self, data: bytes) -> None:
        self.body += data


def test_a_body_the_layer_refuses_is_answered_as_a_projection_failure():
    from aew.dashboard.server import DashboardServer

    reply = _Reply()
    DashboardServer._send(reply, 200, {"rows": [Row("TK-1", "secret-verifier")]}, head=False)  # type: ignore[arg-type]
    assert reply.status == 500
    assert json.loads(reply.body)["code"] == "PROJECTION_FAILED"
    assert b"secret-verifier" not in reply.body
