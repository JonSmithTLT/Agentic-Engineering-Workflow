"""The maps projections' pure part (register F20.8, S1; the change note §4.2): the vocabulary and its bound, the
allowlists' typing, the byte cut, the typed diff's sets and the keyset cursor. The routes themselves, over real git
and HTTP, are ``tests/integration/test_dashboard_maps.py``."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from aew.dashboard import cursors
from aew.dashboard import mapview as MV
from aew.maps import rules, structural

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "maps"
GOLDENS = sorted(FIXTURES.glob("*.json"))


@pytest.fixture(scope="module")
def vocab() -> dict[str, frozenset[str]]:
    return MV.vocabulary(rules.load())


def test_every_vocabulary_value_fits_the_contracts_map_vocab(vocab):
    """n4: only repository-derived fields can reach the 512-byte cut, because every vocabulary value is at most 32
    bytes. A generator or rule-table change past that fails here, before it reaches a response."""
    longest = max((v for values in vocab.values() for v in values), key=lambda v: len(v.encode("utf-8")))
    assert len(longest.encode("utf-8")) <= MV.VOCAB_BYTES, longest
    assert all(v for values in vocab.values() for v in values)


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda p: p.stem)
def test_the_vocabulary_holds_everything_the_generator_writes(golden, vocab):
    """A generated record loses nothing to the vocabulary check: no dropped item or field in any section."""
    record = json.loads(golden.read_text(encoding="utf-8"))
    detail = MV.project_record(record, vocab)
    for name, section in detail.sections.items():
        assert section["dropped_items"] == 0 and section["dropped_fields"] == 0, (golden.stem, name, section)
    assert detail.dropped_fields == 0
    assert set(detail.sections) == set(structural.SECTIONS)


def test_an_integer_field_is_typed_and_ranged_and_bool_is_not_an_int(vocab):
    """p1: ``type(v) is int`` and ``0 <= v < 2**53``; a boolean, a negative, a 4,300-digit integer, a string, a list
    or an object in an integer field is dropped and counted."""
    tally = MV.Tally()
    for value in (True, False, -1, 2**53, int("9" * 4300), "3", [3], {"n": 3}):
        item = MV.project_item({"extension": ".x", "files": value}, MV.UNKNOWN_EXTENSION, vocab, tally)
        assert item == {"extension": ".x"}, value
    assert tally.dropped_fields == 8 and tally.dropped_items == 0
    assert MV.bounded_int(2**53 - 1) == 2**53 - 1 and MV.bounded_int(0) == 0


def test_an_unknown_vocabulary_value_or_a_missing_required_field_drops_the_item(vocab):
    tally = MV.Tally()
    good = {"path": "pyproject.toml", "kind": "python", "status": "parsed"}
    assert MV.project_item(good, MV.BUILD_DESCRIPTOR, vocab, tally) == good
    assert MV.project_item({**good, "kind": "x" * 4096}, MV.BUILD_DESCRIPTOR, vocab, tally) is None
    assert MV.project_item({**good, "status": 7}, MV.BUILD_DESCRIPTOR, vocab, tally) is None
    assert MV.project_item({"path": "p", "kind": "python"}, MV.BUILD_DESCRIPTOR, vocab, tally) is None
    assert MV.project_item(["not", "an", "object"], MV.BUILD_DESCRIPTOR, vocab, tally) is None
    assert tally.dropped_items == 4
    extra = MV.project_item({**good, "hostile": "x", "also": 1}, MV.BUILD_DESCRIPTOR, vocab, tally)
    assert extra == good and tally.dropped_fields == 2


def test_a_row_keeps_twenty_known_language_names_and_counts_the_rest(vocab):
    tally = MV.Tally()
    row = {"path": "src", "depth": 1, "files": 3, "label": "source",
           "languages": ["Python", "Klingon", *(["C"] * 30)]}
    out = MV.project_item(row, MV.ROW, vocab, tally)
    assert out is not None and out["languages"] == ["Python"] + ["C"] * 18 and out["languages_omitted"] == 12
    assert tally.dropped_fields == 1  # Klingon


def test_a_list_is_cut_to_its_cap_before_its_items_are_examined(vocab):
    examined = []

    class Spy(dict):
        def __iter__(self):
            examined.append(1)
            return super().__iter__()

    raw = [Spy(path=f"p{i}", code="not_utf8") for i in range(10**4)]
    items, cut = MV.project_list(raw, 100, MV.PARSE_FAILURE, vocab, MV.Tally())
    assert len(items) == 100 and cut == 10**4 - 100 and len(examined) <= 100


def test_a_sections_omitted_count_adds_the_apis_cut_to_the_records_own(vocab):
    section = {"items": [{"path": f"p{i}", "kind": "python", "status": "parsed"} for i in range(250)],
               "omitted": 7}
    out = MV.project_section("build_descriptors", section, vocab, MV.Tally())
    assert len(out["items"]) == 200 and out["omitted"] == 7 + 50


def test_limits_are_allowlisted_field_by_field():
    tally = MV.Tally()
    raw = {"tracked_paths": {"seen": 3, "capped": 1, "extra": 2}, "metadata_bytes": {"read": int("9" * 4300)},
           "metadata_blob_bytes": [], "other": {}}
    assert MV.project_limits(raw, tally) == {"tracked_paths": {"seen": 3}, "metadata_bytes": {}}
    assert tally.dropped_fields == 5  # capped (an int), extra, read, metadata_blob_bytes, other


# ---------------------------------------------------------------------------------------------- the cut


@pytest.mark.parametrize("text", ["\U0001F600" * 300, "\\\\" * 400, "a" + "\\x1b" * 200, '"' * 600,
                                  "‮" * 300, "é" * 600, "\ud800" * 300, "x" * 511])
def test_the_cut_never_splits_a_character_or_an_escape(text):
    tally = MV.Tally()
    out = MV.cut_text(text, tally)
    assert out.endswith(MV.MARKER) and tally.cut == 1
    body = out[: -len(MV.MARKER)]
    assert len(json.dumps(body, ensure_ascii=False).encode("utf-8", "surrogatepass")) <= MV.TEXT_BYTES
    assert len(out) <= 520  # the contract's MapText
    rest = body.replace("\\\\", "")
    assert all(rest[i + 1] in "xu" for i, c in enumerate(rest) if c == "\\"), rest[-12:]  # no torn escape
    assert not any(0xD800 <= ord(c) <= 0xDFFF or c == "‮" for c in out)


def test_short_text_is_kept_and_a_credential_is_never_shown():
    tally = MV.Tally()
    assert MV.cut_text("calc/core.py", tally) == "calc/core.py" and tally.cut == 0
    assert MV.cut_text("x" * 510, tally) == "x" * 510 and tally.cut == 0
    secret = "aew1." + "tk_" + "0123456789abcdef" + "." + "A" * 43  # credential-shaped, made up
    assert MV.cut_text(f"bin/{secret}", tally) == f"bin/{MV.REDACTED}"
    assert MV.cut_text("e​x", tally) == "e\\xe2\\x80\\x8bx"  # a planted format character, escaped as rendered


# ---------------------------------------------------------------------------------------------- the diff


def record(**sections: Any) -> dict[str, Any]:
    base = json.loads((FIXTURES / "sample.json").read_text(encoding="utf-8"))
    out = copy.deepcopy(base)
    out["sections"].update(sections)
    return out


def test_the_diff_compares_sets_of_canonical_json_after_the_cap(vocab, monkeypatch):
    a = record()
    lo = copy.deepcopy(a["sections"]["limits_and_omissions"])
    lo["lfs_pointers"] = [f"{i}" for i in range(5000)]
    lo["lfs_pointers_omitted"] = 4900
    b = record(limits_and_omissions=lo)
    calls = []
    real = MV.canon

    def counted(item: Any) -> str:
        calls.append(item)
        return real(item)

    monkeypatch.setattr(MV, "canon", counted)
    data = MV.diff(a, b, vocab)
    change = data["sections"]["limits_and_omissions"]
    assert change["changed"] is True and len(change["lfs_pointers"]["added"]) == 100
    assert len(calls) <= 2 * sum(cap for s in MV.SECTIONS.values() for cap, _ in s.lists.values())
    assert change["values"]["lfs_pointers_omitted"] == {"from": a["sections"]["limits_and_omissions"][
        "lfs_pointers_omitted"], "to": 4900}


def test_identical_records_have_no_change_and_the_envelope_names_only_what_differs(vocab):
    a = record()
    data = MV.diff(a, a, vocab)
    assert data["identical"] is True and data["envelope"] == {}
    assert all(s == {"changed": False, "beyond_cap": False, "values": {}} for s in data["sections"].values())
    b = copy.deepcopy(a)
    b["source_revision"] = "f" * 40
    b["artifact_sha256"] = "e" * 64
    assert MV.diff(a, b, vocab)["envelope"] == {"source_revision": {"from": a["source_revision"], "to": "f" * 40}}


# ---------------------------------------------------------------------------------------------- the cursor


def test_a_keyset_cursor_carries_no_revision_and_is_bound_to_its_scope():
    cursor = cursors.Keyset("maps-inputs", "calc", {"root": "a" * 64}, 10, 20).encode()
    parsed = cursors.Keyset.parse(cursor, route="maps-inputs", project="calc", filters={"root": "a" * 64}, limit=10,
                                  position=True)
    assert parsed.after == 20 and "rev" not in cursors.decode(cursor)
    for kwargs in ({"filters": {"root": "b" * 64}}, {"limit": 11}, {"route": "maps-structural"}):
        args = {"route": "maps-inputs", "project": "calc", "filters": {"root": "a" * 64}, "limit": 10, **kwargs}
        with pytest.raises(cursors.CursorError) as refused:
            cursors.Keyset.parse(cursor, position=True, **args)
        assert refused.value.code == "CURSOR_INVALID"
    root_cursor = cursors.Keyset("maps-structural", "calc", {}, 5, "c" * 64).encode()
    assert cursors.Keyset.parse(root_cursor, route="maps-structural", project="calc", filters={}, limit=5).after == \
        "c" * 64
    for bad in ("../x", "C" * 64, 5, None):
        forged = cursors.encode({**cursors.decode(root_cursor), "after": bad})
        with pytest.raises(cursors.CursorError):
            cursors.Keyset.parse(forged, route="maps-structural", project="calc", filters={}, limit=5)
    assert len(cursors.Keyset("maps-inputs", "calc", {"root": "a" * 64}, 250, 10**15).encode()) < 300
