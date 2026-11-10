"""The perf/migration fixture cloner accepts both string record refs and structured coverage pins."""

from __future__ import annotations

from aew.util import sha256_text
from tools.perf import control_plane as CP


def test_cloning_rehashes_string_record_refs_and_nested_coverage_pins(tmp_path):
    # This is the cloner's data boundary, not a hand-built engine workflow. Migration tests cover real templates.
    cloner = object.__new__(CP.Cloner)
    cloner.aew = tmp_path / ".aew"
    original = "work/T-0001/record.md"
    path = cloner.aew / original
    path.parent.mkdir(parents=True)
    text = "record of T-0001\n"
    path.write_text(text, encoding="utf-8")
    old_hash = sha256_text(text)
    cloner.state = {"work": {"T-0001": {
        "record": original, "record_sha256": old_hash,
        "last_verification": {"coverage": {"record": {"path": original, "sha256": old_hash},
                                           "summary": {"headline": "Validation: within scope"}}}}}}
    cloner.counters = {"ticket": 1}
    wid = cloner.clone("T-0001", {"invocation": [], "token": [], "decision": []})
    unit = cloner.state["work"][wid]
    copied = cloner.aew / unit["record"]
    expected = sha256_text(copied.read_text(encoding="utf-8"))
    assert wid == "T-0002" and copied.read_text(encoding="utf-8") == "record of T-0002\n"
    assert expected != old_hash and unit["record_sha256"] == expected
    assert unit["last_verification"]["coverage"]["record"] == {"path": unit["record"], "sha256": expected}
