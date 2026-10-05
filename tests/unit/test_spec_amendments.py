"""The spec amendment index (`docs/spec-amendments.yaml`, register E19) is true, and living documents cite it.

Two kinds of check. Structural: the index's schema; every path exists; only adopted documents are overlays; every
target is a real frozen section (and named case) whose replaced text is quoted verbatim; no target is replaced twice
without an order; the written-out `effective` resolution equals the one computed from the overlays; coverage of the
map both ways. Citations: the refined topic rule of the T7 citation test (archived under
`docs/archive/reviews/architecture-review-2026-10-04/`): a living paragraph that cites an overlaid section, unversioned,
on the overlaid topic must cite the overlay. An unversioned citation means the effective section; a citation of the
historical frozen text is version-qualified (`WC v0.7 §7.4`) and is exempt.

The frozen files are only read; `tests/test_spec_pin.py` keeps them pinned.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
INDEX_PATH = DOCS / "spec-amendments.yaml"
PIN = yaml.safe_load((DOCS / "spec-pin.yaml").read_text(encoding="utf-8"))
FROZEN = {d["path"] for d in PIN["documents"]}

ID = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
SECTION = re.compile(r"^\d+(?:\.\d+)*$")
KINDS = {"replaces", "extends"}
NOT_AUTHORITY = ("docs/design/proposals/", "docs/research/", "docs/archive/")
NOT_LIVING = ("archive", "research", "skills")  # top-level folders under docs/; plus design/proposals

# A contract citation: `WC §7.4`, `KC v0.4 §26`, `Workflow Contract's (§7.5)`, with continuations `§7, §8 and §9`.
CONTRACT = r"(?P<doc>WC|KC|Workflow Contract|Knowledge Contract)(?:'s)?(?:\s+v(?P<ver>\d+\.\d+))?"
SECTION_REF = r"\(?§\s?(?P<sec>\d+(?:\.\d+)*)"
CITATION = re.compile(rf"\b{CONTRACT}\s*{SECTION_REF}(?P<more>(?:\s*(?:,|and|or|/|to)\s*§\s?\d+(?:\.\d+)*)*)")
MORE = re.compile(r"§\s?(\d+(?:\.\d+)*)")
DOC_NAMES = {"WC": "WC", "KC": "KC", "Workflow Contract": "WC", "Knowledge Contract": "KC"}
FENCE = re.compile(r"^\s*(```|~~~)")
ITEM = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|\|)")  # a list item or table row starts its own paragraph
GENERIC_CITE = ("as amended",)


def load_index() -> dict:
    return yaml.safe_load(INDEX_PATH.read_text(encoding="utf-8"))


INDEX = load_index()


# ---- the frozen base: its sections and their text ------------------------------------------------------------------


@dataclass(frozen=True)
class Heading:
    line: int
    level: int
    number: str | None
    title: str


HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.*)$")


def headings(text: str) -> list[Heading]:
    found, fenced = [], False
    for i, line in enumerate(text.splitlines()):
        if FENCE.match(line):
            fenced = not fenced
            continue
        m = HEADING.match(line)
        if m and not fenced:
            num = NUMBERED.match(m.group(2))
            number, title = (num.group(1), num.group(2)) if num else (None, m.group(2))
            found.append(Heading(i, len(m.group(1)), number, title))
    return found


def base_text(doc: str) -> str:
    return (ROOT / INDEX["base"][doc]["path"]).read_text(encoding="utf-8")


def section_span(text: str, number: str) -> str | None:
    """The text of a numbered section: its heading to the next heading of the same or a higher level."""
    lines, hs = text.splitlines(), headings(text)
    for k, h in enumerate(hs):
        if h.number == number:
            end = next((n.line for n in hs[k + 1 :] if n.level <= h.level), len(lines))
            return "\n".join(lines[h.line : end])
    return None


def case_span(section: str, case: str) -> str | None:
    lines, hs = section.splitlines(), headings(section)
    for k, h in enumerate(hs[1:], start=1):
        if h.title == case:
            end = next((n.line for n in hs[k + 1 :] if n.level <= h.level), len(lines))
            return "\n".join(lines[h.line : end])
    return None


def frozen_sections(doc: str) -> set[str]:
    return {h.number for h in headings(base_text(doc)) if h.number}


# ---- resolution ----------------------------------------------------------------------------------------------------


def target_key(doc: str, section: str, case: str | None, part: str) -> tuple:
    return (doc, section, case, part)


def overlays_in_order() -> list[dict]:
    """Adopted overlays in adoption order; ties keep file order (an explicit `supersedes` orders a real conflict)."""
    adopted = [o for o in INDEX["overlays"] if o["status"] == "adopted"]
    return sorted(adopted, key=lambda o: _date(o["adoption"]["at"]))


def resolve() -> dict[tuple, dict]:
    """Every overlaid target: the replacement chain in adoption order, its head, and the extensions."""
    out: dict[tuple, dict] = {}
    for overlay in overlays_in_order():
        for t in overlay["targets"]:
            entry = out.setdefault(
                target_key(t["doc"], t["section"], t.get("case"), t["part"]), {"replaced_by": [], "extended_by": []}
            )
            entry["replaced_by" if t["kind"] == "replaces" else "extended_by"].append(overlay["id"])
    for entry in out.values():
        entry["head"] = entry["replaced_by"][-1] if entry["replaced_by"] else None
    return out


def declared_effective() -> dict[tuple, dict]:
    out = {}
    for sec in INDEX["effective"]:
        for p in sec["parts"]:
            out[target_key(sec["doc"], sec["section"], sec.get("case"), p["part"])] = {
                "replaced_by": p.get("replaced_by", []),
                "extended_by": p.get("extended_by", []),
                "head": p.get("head"),
            }
    return out


def _date(value) -> dt.date:
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


# ---- structural tests ----------------------------------------------------------------------------------------------


def test_the_index_has_its_schema():
    assert INDEX["schema"] == "aew/spec-amendments/v1"
    assert INDEX["base_spec_set"] == PIN["spec_set"]
    roles = {d["role"]: d for d in PIN["documents"]}
    for doc, role in (("WC", "workflow_contract"), ("KC", "knowledge_contract")):
        assert INDEX["base"][doc] == {"path": roles[role]["path"], "version": roles[role]["version"]}
    assert set(INDEX) == {"schema", "base_spec_set", "base", "overlays", "effective", "pending", "considered"}

    ids = [o["id"] for o in INDEX["overlays"]]
    assert len(ids) == len(set(ids)), "overlay ids are unique"
    for o in INDEX["overlays"]:
        assert ID.match(o["id"]), o["id"]
        assert set(o) == {"id", "path", "sections", "status", "adoption", "cite_as", "targets"}, o["id"]
        assert set(o["adoption"]) == {"at", "by", "evidence"}, o["id"]
        assert o["adoption"]["by"] and o["adoption"]["evidence"], o["id"]
        assert o["targets"] and o["sections"] and o["cite_as"], o["id"]
        for t in o["targets"]:
            allowed = {"doc", "section", "case", "part", "kind", "by", "quote", "supersedes", "topic"}
            assert set(t) <= allowed, (o["id"], set(t) - allowed)
            assert t["doc"] in INDEX["base"] and SECTION.match(t["section"]), (o["id"], t)
            assert t["kind"] in KINDS and t["part"] and t["by"], (o["id"], t)
            assert all(isinstance(w, str) and w for w in t.get("topic", [])), (o["id"], t)
            if t["kind"] == "replaces":
                assert t.get("quote"), f"{o['id']}: a replacement quotes the text it supersedes"
            else:
                assert "quote" not in t and "supersedes" not in t, f"{o['id']}: an extension replaces nothing"


def test_only_adopted_documents_are_overlays():
    """`design_frozen` and `proposed` never count; nor does a proposal, research note or archived record."""
    for o in INDEX["overlays"]:
        assert o["status"] == "adopted", f"{o['id']}: status {o['status']!r} is not an overlay"
        assert not o["path"].startswith(NOT_AUTHORITY), f"{o['id']}: {o['path']} cannot be an authority"
        text = (ROOT / o["path"]).read_text(encoding="utf-8")
        status = re.search(r"\*\*Status:\*\*\s*(.*)", text)
        assert status, f"{o['path']} has no status line"
        state = status.group(1).lstrip("* ").lower()
        assert state.startswith(("adopted", "governing")), f"{o['path']}: status is {state[:40]!r}"
        evidence = o["adoption"]["evidence"]
        assert evidence in text, f"{o['id']}: adoption evidence not in the document"
        assert _date(o["adoption"]["at"]).isoformat() in evidence, f"{o['id']}: the evidence does not carry the date"


def test_every_path_exists():
    paths = [o["path"] for o in INDEX["overlays"]] + [c["path"] for c in INDEX["considered"]]
    paths += [p["decided_in"] for p in INDEX["pending"]] + [b["path"] for b in INDEX["base"].values()]
    missing = [p for p in paths if not (ROOT / p).is_file()]
    assert missing == []


def test_the_overlay_sections_exist_in_the_overlay_document():
    for o in INDEX["overlays"]:
        numbers = {h.number for h in headings((ROOT / o["path"]).read_text(encoding="utf-8")) if h.number}
        assert set(o["sections"]) <= numbers, (o["id"], set(o["sections"]) - numbers)


def test_every_target_exists_in_the_frozen_base():
    for o in INDEX["overlays"]:
        for t in o["targets"]:
            span = section_span(base_text(t["doc"]), t["section"])
            assert span is not None, f"{o['id']}: {t['doc']} §{t['section']} is not a frozen section"
            if t.get("case"):
                span = case_span(span, t["case"])
                assert span is not None, f"{o['id']}: no case {t['case']!r} in {t['doc']} §{t['section']}"
            if t["kind"] == "replaces" and "supersedes" not in t:
                assert t["quote"] in span, f"{o['id']}: the replaced text is not in {t['doc']} §{t['section']}"


def test_no_target_is_replaced_twice_without_an_order():
    by_id = {o["id"]: o for o in INDEX["overlays"]}
    seen: dict[tuple, dict] = {}
    for overlay in overlays_in_order():
        for t in overlay["targets"]:
            if t["kind"] != "replaces":
                continue
            key = target_key(t["doc"], t["section"], t.get("case"), t["part"])
            earlier = seen.get(key)
            if earlier is None:
                assert "supersedes" not in t, f"{overlay['id']}: supersedes nothing on {key}"
            else:
                assert t.get("supersedes") == earlier["id"], (
                    f"{key} is replaced by {earlier['id']} and {overlay['id']}: the later must name the earlier"
                )
                assert _date(overlay["adoption"]["at"]) >= _date(earlier["adoption"]["at"]), key
                assert t["quote"] in (ROOT / by_id[earlier["id"]]["path"]).read_text(encoding="utf-8"), (
                    f"{overlay['id']}: the superseded text is not in {earlier['id']}"
                )
            seen[key] = overlay


def test_the_written_resolution_is_the_computed_one():
    assert declared_effective() == resolve()


def test_dates_are_valid():
    today = dt.date.today()
    frozen_on = dt.date.fromisoformat(PIN["spec_set"].removeprefix("aew-frozen-"))
    for o in INDEX["overlays"]:
        at = o["adoption"]["at"]
        assert isinstance(at, dt.date) and not isinstance(at, dt.datetime), f"{o['id']}: {at!r} is not a date"
        assert frozen_on <= at <= today, f"{o['id']}: adopted {at} outside {frozen_on}..{today}"


def test_pending_debt_names_real_sections_and_stays_visible():
    """Debt is data, not text: it names frozen sections that exist, and it is never also an effective replacement."""
    replaced = {(k[0], k[1]) for k, v in resolve().items() if v["replaced_by"]}
    debts = []
    for p in INDEX["pending"]:
        assert set(p) == {"id", "reason", "decided_in", "decided_evidence", "register", "targets"}, p["id"]
        assert p["decided_evidence"] in (ROOT / p["decided_in"]).read_text(encoding="utf-8"), p["id"]
        for t in p["targets"]:
            span = section_span(base_text(t["doc"]), t["section"])
            assert span is not None, (p["id"], t)
            if "item" in t:
                assert re.search(rf"^{t['item']}\. \*\*", span, re.M), (p["id"], t)
            assert (t["doc"], t["section"]) not in replaced, (p["id"], t)
            debts.append(f"{t['doc']} §{t['section']}" + (f" item {t['item']}" if "item" in t else ""))
    assert debts == ["KC §12", "WC §7", "WC §8", "WC §23 item 7"], "the Ticket-revision debt changed: update the index"


def governing_amendments_on_the_map() -> set[str]:
    """docs/README.md "What governs", item 2: the adopted amendments and decision records."""
    readme = (DOCS / "README.md").read_text(encoding="utf-8")
    block = readme.split("2. **Adopted amendments and decision records**", 1)[1].split("\n3. ", 1)[0]
    return {f"docs/{t}" for t in re.findall(r"^\s+- \[`[^`]+`\]\(([^)#]+)\)", block, re.M)}


def test_the_map_and_the_index_cover_each_other():
    """Every adopted amendment, decision record and ADR is an overlay or `considered` with a reason; nothing else is."""
    on_map = governing_amendments_on_the_map() | {
        p.relative_to(ROOT).as_posix() for p in (DOCS / "implementation" / "adr").glob("*.md")
    }
    overlays = {o["path"] for o in INDEX["overlays"]}
    considered = [c["path"] for c in INDEX["considered"]]
    assert len(considered) == len(set(considered))
    assert not overlays & set(considered), "a document is an overlay or considered, not both"
    assert all(c["reason"] for c in INDEX["considered"])
    assert sorted(on_map - overlays - set(considered)) == [], "index these documents (overlay or considered)"
    assert sorted((overlays | set(considered)) - on_map) == [], "these are not adopted documents on the map"


# ---- citations -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    path: str
    line: int
    doc: str
    version: str | None
    section: str
    paragraph: str


def living_documents() -> list[Path]:
    """The living set of docs/README.md: not frozen, not archived, not research, a proposal or a skill."""
    overlays = {o["path"] for o in INDEX["overlays"]}
    found = []
    for p in sorted(DOCS.rglob("*.md")):
        rel = p.relative_to(ROOT).as_posix()
        parts = p.relative_to(DOCS).parts
        if rel in FROZEN or rel in overlays or parts[0] in NOT_LIVING or parts[:2] == ("design", "proposals"):
            continue
        found.append(p)
    return found


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Blank-line blocks, each list item or table row its own paragraph; fenced code dropped. (first line, text)."""
    out: list[tuple[int, list[str]]] = []
    fenced, current = False, None
    for i, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            fenced, current = not fenced, None
            continue
        if fenced or not line.strip():
            current = None
            continue
        if current is None or ITEM.match(line):
            current = (i, [line])
            out.append(current)
        else:
            current[1].append(line)
    return [(start, "\n".join(lines)) for start, lines in out]


def citations(path: Path, rel: str | None = None) -> list[Citation]:
    rel = rel or path.relative_to(ROOT).as_posix()
    found = []
    for start, para in paragraphs(path.read_text(encoding="utf-8")):
        for m in CITATION.finditer(para):
            line = start + para.count("\n", 0, m.start())
            sections = [m.group("sec"), *MORE.findall(m.group("more") or "")]
            for sec in sections:
                found.append(Citation(rel, line, DOC_NAMES[m.group("doc")], m.group("ver"), sec, para))
    return found


ALL_CITATIONS = [c for p in living_documents() for c in citations(p)]


def covers(cited: str, target: str) -> bool:
    """A citation of §7.4 or of §7.4.x is about the target §7.4; a citation of the parent §7 is not."""
    return cited == target or cited.startswith(target + ".")


def cites_overlay(paragraph: str, overlay: dict) -> bool:
    low = paragraph.lower()
    names = [Path(overlay["path"]).name, Path(overlay["path"]).stem, *overlay["cite_as"], *GENERIC_CITE]
    return any(n.lower() in low for n in names)


def topic_violations(found: list[Citation]) -> list[str]:
    """One entry per citation that is on an overlaid topic but does not cite the overlay that governs that topic."""
    by_id = {o["id"]: o for o in INDEX["overlays"]}
    effective = resolve()
    bad = []
    for c in found:
        if c.version is not None:
            continue  # a version-qualified citation is the historical frozen text, by convention
        missing = set()
        for overlay in overlays_in_order():
            for t in overlay["targets"]:
                if t["doc"] != c.doc or not covers(c.section, t["section"]) or not t.get("topic"):
                    continue
                if not any(w.lower() in c.paragraph.lower() for w in t["topic"]):
                    continue
                head = effective[target_key(t["doc"], t["section"], t.get("case"), t["part"])]["head"]
                current = by_id[head] if head else overlay
                if not cites_overlay(c.paragraph, current):
                    missing.add(current["id"])
        if missing:
            bad.append(f"{c.path}:{c.line}: {c.doc} §{c.section} on an overlaid topic without {sorted(missing)}")
    return sorted(set(bad))


def test_the_living_set_has_citations_to_check():
    """A guard on the scanner: if the regular expression or the living set broke, the rules would pass vacuously."""
    sections = {(c.doc, c.section) for c in ALL_CITATIONS}
    assert len(ALL_CITATIONS) >= 60
    assert {("WC", "7.4"), ("WC", "7.5"), ("KC", "26"), ("WC", "15.6")} <= sections


# Citations that resolve to no frozen section, found when this index was built and listed in its PR for their owners
# rather than silently fixed. Both use a "section.item" shorthand for a numbered list item of a section with no
# subsections (KC §27 invariants 3 and 4; KC §28 open question 10). Fixing one fails this test: remove its entry.
KNOWN_UNRESOLVED = {
    "docs/implementation/adr/0001-control-state-persistence.md: KC §27.3",
    "docs/implementation/adr/0007-epic-story-hierarchy.md: KC §28.10",
}


def test_citations_name_real_sections_of_a_known_version():
    """An unversioned citation names a real (effective) section; a versioned one names the frozen base version."""
    bad = []
    known = {doc: frozen_sections(doc) for doc in INDEX["base"]}
    for c in ALL_CITATIONS:
        if c.version is not None and c.version != INDEX["base"][c.doc]["version"]:
            bad.append(f"{c.path}: {c.doc} v{c.version} is not the frozen version")
        elif c.section not in known[c.doc]:
            bad.append(f"{c.path}: {c.doc} §{c.section}")
    assert sorted(bad) == sorted(KNOWN_UNRESOLVED)


def test_a_citation_of_an_overlaid_section_on_its_topic_cites_the_overlay():
    """The refined T7 rule: only a paragraph about the overlaid text must name the overlay (or say "as amended")."""
    assert topic_violations(ALL_CITATIONS) == []


@pytest.mark.parametrize(
    ("paragraph", "expected"),
    [
        ("- A Class 0 Ticket needs no review (WC §7.4).", 1),  # on topic, no overlay named: stale
        ("- A Class 0 Ticket is refused unless eligible (WC §7.4, as amended).", 0),
        ("- Classify each unit by its own change surface (WC §7.4).", 0),  # off topic: noise under the naive rule
        ("- The frozen Class 0 bullet read: trivial (WC v0.7 §7.4).", 0),  # historical, version-qualified
        ("- KC §26 parent risk policy propagation: the Ticket keeps Class 0.", 1),
        ("- KC §26 parent risk policy, per `workflow-contract-amendment-class0-2026-10-01.md` §9.2.", 0),
        ("- WC §7.5: the Class 0 path; WC §15.6: MCP is the first normal transport.", 2),
    ],
)
def test_the_topic_rule_on_examples(tmp_path, paragraph, expected):
    doc = tmp_path / "example.md"
    doc.write_text(paragraph + "\n", encoding="utf-8")
    assert len(topic_violations(citations(doc, rel="example.md"))) == expected

