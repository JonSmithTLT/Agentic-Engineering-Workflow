"""The requirements ledger (`docs/design/requirements-ledger.yaml`) is a hard gate: no requirement in a design or
research document goes untracked, and none is lost between versions (operator, 2026-10-04).

- Every document under docs/design/ and docs/research/ is an ingested source or a legacy document.
- Every heading of every source is accounted for: it holds requirements, its requirements are carried by ids
  elsewhere, or it holds none, with the reason. A heading a new version drops fails until its entries are re-pointed.
- Requirement ids are contiguous per source; a requirement is never deleted, only moved to `retired` with its
  disposition.
- Every requirement is tracked by register rows that exist in docs/implementation/future-work.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LEDGER = yaml.safe_load((ROOT / "docs" / "design" / "requirements-ledger.yaml").read_text(encoding="utf-8"))
SOURCES = {s["prefix"]: s for s in LEDGER["sources"]}
REQUIREMENTS: dict[str, dict] = LEDGER["requirements"]
RETIRED: dict[str, dict] = LEDGER.get("retired") or {}
ID = re.compile(r"^([A-Z]+)-(\d+)$")
HEADING = re.compile(r"^#{1,6} +(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
STATUS = re.compile(r"^(done|superseded-by|absorbed-by|rejected): .+")


def headings(path: Path) -> list[str]:
    """Every heading outside code fences, except the document's title (its first heading, when level 1)."""
    found, fenced, first = [], False, True
    for line in path.read_text(encoding="utf-8").splitlines():
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else HEADING.match(line)
        if m:
            if first and line.startswith("# "):
                first = False
                continue
            first = False
            found.append(m.group(1))
    return found


def register_ids() -> set[str]:
    text = (ROOT / "docs" / "implementation" / "future-work.md").read_text(encoding="utf-8")
    return set(re.findall(r"^\| ([A-Z][0-9]+(?:\.[0-9]+)?) \|", text, re.M))


def test_every_design_and_research_document_is_in_the_ledger():
    docs = {p.relative_to(ROOT).as_posix() for d in ("docs/design", "docs/research") for p in (ROOT / d).rglob("*")
            if p.is_file() and p.suffix in (".md", ".yaml") and p.name != "requirements-ledger.yaml"}
    known = {s["path"] for s in LEDGER["sources"]} | set(LEDGER["legacy"])
    assert sorted(docs - known) == [], "ingest these into the requirements ledger, every requirement tracked"
    assert sorted(known - docs - {s["path"] for s in LEDGER["sources"] if s["path"].startswith("docs/archive/")}) == []


def test_legacy_documents_name_register_rows():
    ids = register_ids()
    for path, rows in LEDGER["legacy"].items():
        assert rows and set(rows) <= ids, f"{path}: register rows {rows} must exist"


@pytest.mark.parametrize("prefix", sorted(SOURCES))
def test_every_heading_of_a_source_is_accounted_for(prefix):
    source = SOURCES[prefix]
    path = ROOT / source["path"]
    assert path.exists(), f"{prefix}: {source['path']} is gone; point the source at its new version"
    heads = headings(path)
    dupes = sorted({h for h in heads if heads.count(h) > 1})
    assert dupes == [], f"{prefix}: duplicate headings cannot be told apart: {dupes}"
    with_reqs = {r["section"] for i, r in REQUIREMENTS.items() if i.startswith(prefix + "-")}
    none = set(source.get("no_requirements") or {})
    carried = set(source.get("carried") or {})
    stale = sorted((with_reqs | none | carried) - set(heads))
    assert stale == [], f"{prefix}: these sections no longer exist; re-point or retire their requirements: {stale}"
    unaccounted = [h for h in heads if h not in with_reqs | none | carried]
    assert unaccounted == [], f"{prefix}: sections with no ledger entry, carried ids or no_requirements reason"
    assert sorted(none & (with_reqs | carried)) == [], f"{prefix}: a section marked no_requirements holds requirements"
    assert all(str(reason).strip() for reason in (source.get("no_requirements") or {}).values())


def test_carried_ids_exist():
    for prefix, source in SOURCES.items():
        for section, ids in (source.get("carried") or {}).items():
            missing = [i for i in ids if i not in REQUIREMENTS]
            assert missing == [], f"{prefix} '{section}' carries unknown ids {missing}"


@pytest.mark.parametrize("prefix", sorted(SOURCES))
def test_ids_are_contiguous_so_nothing_is_deleted(prefix):
    matches = [ID.match(i) for i in [*REQUIREMENTS, *RETIRED] if i.startswith(prefix + "-")]
    assert all(matches), f"{prefix}: malformed ids"
    numbers = sorted(int(m.group(2)) for m in matches if m)
    assert numbers == list(range(1, len(numbers) + 1)), f"{prefix}: a gap means a deleted requirement; retire it"
    assert not set(REQUIREMENTS) & set(RETIRED)


def test_every_requirement_is_well_formed_and_tracked():
    ids, kinds = register_ids(), set(LEDGER["kinds"])
    for rid, req in REQUIREMENTS.items():
        m = ID.match(rid)
        assert m and m.group(1) in SOURCES, f"{rid}: id must be <source prefix>-<n>"
        assert req.get("kind") in kinds, f"{rid}: kind {req.get('kind')!r}"
        assert str(req.get("statement", "")).strip(), f"{rid}: statement"
        assert req.get("tracked_by") and set(req["tracked_by"]) <= ids, \
            f"{rid}: tracked_by {req.get('tracked_by')} must name register rows in future-work.md"
        assert "status" not in req or STATUS.match(req["status"]), f"{rid}: status {req['status']!r}"


def test_retired_requirements_keep_their_disposition():
    for rid, entry in RETIRED.items():
        assert ID.match(rid) and STATUS.match(str(entry.get("disposition", ""))), \
            f"{rid}: retired requirements need 'superseded-by: <id>', 'absorbed-by: <id>' or 'rejected: <reason>'"
