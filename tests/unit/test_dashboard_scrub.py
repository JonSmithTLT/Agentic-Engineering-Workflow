"""F20: ``projections.scrub``, the second display layer behind the projections' allowlist: the engine's verifier
masking and its credential redaction (``aew.harness.contract.redact``), over every string in a body.

The credential-shaped value is built here from the engine's credential pattern at run time; it is not a credential.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath

from aew.dashboard import projections as P
from aew.dashboard.projections import Projector
from aew.harness import contract as K

SHAPED = "aew1." + "tk_" + "0123456789abcdef" + "." + "S" * 12 + "_" + "s" * 12  # matches K.CREDENTIAL_RE
MARKER = K.redact(SHAPED)


def test_the_shaped_value_matches_the_engines_pattern():
    assert K.CREDENTIAL_RE.fullmatch(SHAPED) and SHAPED not in MARKER


def test_scrub_masks_verifiers():
    body = {"tokens": [{"id": "TK-1", "verifier": "sha256:abc"}], "nested": {"verifier": {"any": "shape"}}}
    assert P.scrub(body) == {"tokens": [{"id": "TK-1", "verifier": "<redacted>"}],
                             "nested": {"verifier": "<redacted>"}}


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
