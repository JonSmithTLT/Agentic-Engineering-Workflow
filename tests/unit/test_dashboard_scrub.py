"""F20: ``projections.scrub``, the second display layer behind the projections' allowlist: the engine's verifier
masking and its credential redaction (``aew.harness.contract.redact``), over every string in a body.

The credential-shaped value is built here from the engine's credential pattern at run time; it is not a credential.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath

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


@dataclass
class Row:
    id: str
    verifier: str
    note: str


@pytest.mark.parametrize("body, expected", [
    ({"rows": ({"id": "TK-1", "verifier": "v"},)}, {"rows": [{"id": "TK-1", "verifier": "<redacted>"}]}),
    ([({"verifier": "v"}, [{"verifier": "v"}])], [[{"verifier": "<redacted>"}, [{"verifier": "<redacted>"}]]]),
    (({"a": ({"b": [({"verifier": "v", "c": 1},)]},)},),
     [{"a": [{"b": [[{"verifier": "<redacted>", "c": 1}]]}]}]),
    ({"rows": frozenset({"x", "y"})}, {"rows": ["x", "y"]}),
    ({"row": Row("TK-1", "v", "n")}, {"row": {"id": "TK-1", "verifier": "<redacted>", "note": "n"}}),
    ({"rows": [Row("TK-2", "v", "n")]}, {"rows": [{"id": "TK-2", "verifier": "<redacted>", "note": "n"}]}),
])
def test_scrub_masks_verifiers_in_every_container(body, expected):
    assert P.scrub(body) == expected


def test_scrub_redacts_credentials_in_every_container():
    body = {"t": (SHAPED,), "s": {SHAPED, "y"}, "d": Row("TK-3", "v", SHAPED), "l": [({"k": SHAPED},)]}
    out = P.scrub(body)
    assert SHAPED not in repr(out)
    assert out["t"] == [MARKER] and set(out["s"]) == {MARKER, "y"} and out["d"]["note"] == MARKER
    assert out["l"] == [[{"k": MARKER}]]


@dataclass
class Held:
    shown: str
    hidden: str = field(repr=False, default="held back")


@dataclass
class Told:
    verifier: str
    note: str

    def __str__(self) -> str:
        return f"told {self.note}"


@dataclass
class Brief:
    verifier: str
    note: str

    def __repr__(self) -> str:
        return "brief"


class Opaque:
    def __repr__(self) -> str:
        return "opaque"

    def __str__(self) -> str:
        return "opaque"


def test_the_walk_never_shows_a_field_the_dataclass_repr_hides():
    out = P.scrub({"row": Held("s")})
    assert out == {"row": {"shown": "s"}} and "held back" not in repr(out)


def test_a_dataclass_with_its_own_str_or_repr_is_shown_as_its_str():
    assert P.scrub(Told("v", SHAPED)) == f"told {MARKER}"
    assert P.scrub([Brief("v", "n")]) == ["brief"]


def test_a_container_whose_members_may_show_more_when_walked_is_shown_as_its_str():
    assert P.scrub({"s": frozenset({Opaque()})}) == {"s": "frozenset({opaque})"}
    assert P.scrub(Row("TK-4", "v", Opaque())) == "Row(id='TK-4', verifier='v', note=opaque)"  # type: ignore[arg-type]


def test_a_walked_dataclass_still_masks_its_verifier():
    assert P.scrub(Row("TK-5", "sha256:abc", SHAPED)) == {"id": "TK-5", "verifier": "<redacted>", "note": MARKER}


def test_scrub_redacts_a_string_subclass_and_bytes():
    class Label(StrEnum):
        A = "x " + SHAPED

    out = P.scrub({"v": Label.A, "b": SHAPED.encode()})
    assert type(out["v"]) is str and SHAPED not in json.dumps(out) and MARKER in out["v"] and MARKER in out["b"]


def test_the_engines_verifier_masking_walks_tuples():
    assert redact({"rows": ({"verifier": "v"},)}) == {"rows": [{"verifier": "<redacted>"}]}


def test_scrub_applies_the_engines_credential_redaction_to_every_string():
    body = {"title": f"see {SHAPED} here", "items": [SHAPED, (f"x{SHAPED}", 3)], f"key {SHAPED}": True,
            "count": 2, "ratio": 0.5, "flag": False, "none": None}
    out = P.scrub(body)
    assert SHAPED not in repr(out)
    assert out["title"] == f"see {MARKER} here" and out["items"] == [MARKER, [f"x{MARKER}", 3]]
    assert out[f"key {MARKER}"] is True
    assert (out["count"], out["ratio"], out["flag"], out["none"]) == (2, 0.5, False, None)


def test_scrub_redacts_a_leaf_the_serializer_would_stringify():
    when = datetime(2026, 1, 1, tzinfo=UTC)
    out = P.scrub({"path": PurePosixPath(f"/x/{SHAPED}"), "at": when})
    assert out == {"path": f"/x/{MARKER}", "at": str(when)}


def test_scrub_is_idempotent():
    once = P.scrub({"a": SHAPED, "verifier": "v"})
    assert P.scrub(once) == once


def test_an_activity_title_is_redacted_before_it_is_cut():
    """A credential straddling the title's cut never leaves a prefix of itself behind."""
    pad = "x" * (1000 - len("op: ") - 30)
    record = {"revision": 7, "at": "2026-01-01T00:00:00Z", "op": "op", "summary": pad + SHAPED}
    title = Projector._activity(None, record)["title"]  # type: ignore[arg-type]  # uses no projector state
    assert SHAPED[:30] not in title and len(title) <= 1000
