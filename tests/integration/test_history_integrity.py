"""ADR-0011, the independent P3 review: the derived index never vouches for history (P3-1), and a full audit covers
the evidence a finished unit's completion rests on (P3-2).

Each test builds a real finished mutating Ticket (the perf template: implementation, review, ticket and integration
verification, publication) in the M3 layout and migrates it, then changes one file the way the review did. The
authoritative history and its root are never touched by the index changes.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

HELPERS = Path(__file__).resolve().parents[1] / "helpers"
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "perf"))

import control_plane as CP  # noqa: E402
from conftest import run_aew  # noqa: E402
from invariants import assert_control_invariants, load_control  # noqa: E402

from aew.engine.api import Engine  # noqa: E402
from aew.history.index import INDEX_REL  # noqa: E402
from aew.history.store import bundle_rel  # noqa: E402
from aew.util import dump_yaml, load_yaml, sha256_bytes  # noqa: E402

FORGED = "local/forged-archive.yaml"


def aew(t: CP.Template, *args: str) -> Any:
    return run_aew("-C", str(t.root), *args, env={"AEW_LEAD_TOKEN": t.token})


def migrated(tmp_path: Path) -> CP.Template:
    t = CP.make_template(tmp_path / "repo")
    out = aew(t, "migrate", "--expect-rev", str(t.rev()))
    assert out.returncode == 0 and out.json["migrated"] is True, out.stderr
    return t


def index_db(t: CP.Template) -> sqlite3.Connection:
    return sqlite3.connect(t.root / ".aew" / INDEX_REL, isolation_level=None)


def forge_index_entry(t: CP.Template, wid: str) -> None:
    """Point the index's entry for ``wid`` at a local copy of its bundle that says something else (a different title,
    a mutating unit with an invented integration commit), keeping its position, chain hash and the index's root."""
    aew_root = t.root / ".aew"
    doc = load_yaml((aew_root / bundle_rel(wid)).read_text(encoding="utf-8"))
    doc["unit"]["title"] = "Forged title"
    doc["unit"]["mutating"] = True
    doc["unit"]["integration"] = dict(doc["unit"].get("integration") or {}, commit="a" * 40)
    text = dump_yaml(doc)
    (aew_root / FORGED).write_text(text, encoding="utf-8", newline="\n")
    conn = index_db(t)
    try:
        seq, body = conn.execute("SELECT seq, body FROM entries WHERE id = ? AND kind = 'unit'", (wid,)).fetchone()
        entry = dict(json.loads(body), path=FORGED, sha256=sha256_bytes(text.encode("utf-8")))
        conn.execute("UPDATE entries SET body = ?, path = ?, sha256 = ? WHERE seq = ?",
                     (json.dumps(entry, sort_keys=True), FORGED, entry["sha256"], seq))
    finally:
        conn.close()


def index_paths(t: CP.Template) -> set[str]:
    conn = index_db(t)
    try:
        return {p for (p,) in conn.execute("SELECT path FROM entries").fetchall()}
    finally:
        conn.close()


# ---------------------------------------------------------------------------------------------- P3-1


def test_an_index_entry_that_names_another_record_is_not_believed(tmp_path):
    t = migrated(tmp_path)
    real = aew(t, "history", "show", "T-0001").json["record"]["unit"]["title"]
    forge_index_entry(t, "T-0001")
    shown = aew(t, "history", "show", "T-0001")
    assert shown.returncode == 0, shown.stderr
    assert shown.json["record"]["unit"]["title"] == real  # the history's own entry, found through its position
    assert FORGED not in index_paths(t)  # the index disagreed with the history, so it was rebuilt
    # Facts a new dependency would record come from the authenticated bundle, with that bundle's own hash.
    forge_index_entry(t, "T-0001")
    eng = Engine.discover(t.root)
    state = eng.store.read()
    facts = eng._archive.facts_from_cold(state, "T-0001")
    bundle = (t.root / ".aew" / bundle_rel("T-0001")).read_bytes()
    assert facts["bundle_sha256"] == sha256_bytes(bundle)
    assert (facts.get("integration") or {}).get("commit") != "a" * 40
    assert aew(t, "history", "audit", "--full").json["ok"] is True
    assert_control_invariants(t)


def test_rows_the_index_lost_or_links_it_invented_are_caught(tmp_path):
    t = migrated(tmp_path)
    assert aew(t, "history", "show", "T-0001").returncode == 0
    conn = index_db(t)
    try:
        conn.execute("DELETE FROM entries WHERE id = 'T-0001'")  # a lost row: caught when the index is synced
    finally:
        conn.close()
    assert aew(t, "history", "show", "T-0001").returncode == 0
    conn = index_db(t)
    try:
        seq = conn.execute("SELECT seq FROM entries WHERE id = 'T-0001'").fetchone()[0]
        conn.execute("INSERT INTO links (seq, src, rel, dst) VALUES (?, 'T-0001', 'depends_on', 'T-0999')", (seq,))
    finally:
        conn.close()
    edges = aew(t, "history", "links", "T-0001").json["edges"]
    assert edges and not any(e["to"] == "T-0999" for e in edges)  # links come from the authenticated entries
    assert_control_invariants(t)


def test_a_full_audit_finds_an_index_row_that_hides_its_entry(tmp_path):
    """A row altered so that no query matches it omits a record rather than inventing one; the explicit full audit
    compares every row with the history and rebuilds the index."""
    t = migrated(tmp_path)
    assert aew(t, "history", "show", "T-0001").returncode == 0
    conn = index_db(t)
    try:
        conn.execute("UPDATE entries SET id = 'T-0998' WHERE id = 'T-0001'")
    finally:
        conn.close()
    assert aew(t, "history", "show", "T-0001").error["code"] == "NOT_FOUND"
    audit = aew(t, "history", "audit", "--full")
    assert audit.returncode == 0 and audit.json["index"] == "rebuilt", audit.stderr
    assert aew(t, "history", "show", "T-0001").returncode == 0
    assert aew(t, "history", "audit", "--full").json["index"] == "consistent"
    assert_control_invariants(t)


# ---------------------------------------------------------------------------------------------- P3-2


def test_the_checks_a_verification_cites_are_kept_and_found_by_id(tmp_path):
    t = migrated(tmp_path)
    shown = aew(t, "history", "show", "INV-0003-check-unit-4")  # cited by INV-0003-verify-6, never ingested
    assert shown.returncode == 0, shown.stderr
    assert shown.json["kind"] == "evidence" and shown.json["held_by"] == "T-0001"
    assert shown.json["record"]["meta"]["kind"] == "check_result"
    links = aew(t, "history", "links", "T-0001").json["edges"]
    assert {"from": "T-0001", "rel": "evidence", "to": "INV-0003-check-unit-4"} in links
    assert_control_invariants(t)


def test_a_full_audit_covers_cited_checks_and_the_logs_records_pin(tmp_path):
    t = migrated(tmp_path)
    clean = aew(t, "history", "audit", "--full")
    assert clean.returncode == 0 and clean.json["ok"] is True, clean.stderr
    aew_root = t.root / ".aew"
    damage = {
        "a cited check changed": ("evidence/T-0001/INV-0003-check-unit-4.md", "change"),
        "an ingested check's log changed": ("evidence/T-0001/logs/INV-0001-check-unit-1.log", "change"),
        "an ingested check's log deleted": ("evidence/T-0001/logs/INV-0001-check-unit-1.log", "delete"),
        "a cited check's log changed": ("evidence/T-0001/logs/INV-0003-check-unit-4.log", "change"),
    }
    for what, (rel, how) in damage.items():
        path = aew_root / rel
        saved = path.read_bytes()
        if how == "change":
            path.write_bytes(saved + b"\nedited\n")
        else:
            path.unlink()
        audit = aew(t, "history", "audit", "--full")
        assert audit.error["code"] == "INTEGRITY_ERROR", what
        problems = audit.error["details"]["audit"]["problems"]
        assert any(rel in p for p in problems), (what, problems)
        path.write_bytes(saved)
    assert aew(t, "history", "audit", "--full").json["ok"] is True
    # A recorded audit that finds damage records it, marks the unit and leaves the verified root where it was.
    log = aew_root / "evidence/T-0001/logs/INV-0003-check-unit-4.log"
    saved = log.read_bytes()
    log.write_bytes(saved + b"\nedited\n")
    before = load_control(t.root)["cold"].get("verified")
    recorded = aew(t, "history", "audit", "--full", "--expect-rev", str(t.rev()))
    assert recorded.error["code"] == "INTEGRITY_ERROR" and recorded.error["details"]["audit"]["recorded"] is True
    assert load_control(t.root)["cold"].get("verified") == before
    findings = [a for a in aew(t, "history", "show", "T-0001").json.get("annotations") or []
                if a["entry"]["rel"] == "audit_finding"]
    assert findings, "the damaged unit gets an audit finding"
    log.write_bytes(saved)
    assert_control_invariants(t)


def test_a_unit_whose_verification_changed_after_ingest_is_not_archived(tmp_path):
    t = CP.make_template(tmp_path / "repo")
    report = t.root / ".aew/evidence/T-0001/INV-0003-verify-6.md"
    report.write_bytes(report.read_bytes() + b"\nedited\n")
    out = aew(t, "migrate", "--expect-rev", str(t.rev()))
    assert out.error["code"] == "INTEGRITY_ERROR" and "INV-0003-verify-6" in out.error["message"]
    assert load_control(t.root)["schema"] == "aew/control/v1"
    shutil.rmtree(t.root / ".aew/local", ignore_errors=True)


# ---------------------------------------------------------------------------------------------- the re-review


CITED = "evidence/T-0001/INV-0003-check-unit-4.md"
CITED_LOG = "evidence/T-0001/logs/INV-0003-check-unit-4.log"
INGESTED_CHECK = "evidence/T-0001/INV-0001-check-unit-1.md"


def test_cited_checks_that_are_not_what_the_engine_sealed_are_never_pinned(tmp_path):
    """P3-R1: a cited check changed before archival, replaced by another sealed record, or whose log changed, refuses
    the migration; control stays v1 and nothing is pinned."""
    t = CP.make_template(tmp_path / "repo")
    aew_root = t.root / ".aew"
    cited, log = aew_root / CITED, aew_root / CITED_LOG
    saved, saved_log = cited.read_bytes(), log.read_bytes()
    cases = {
        "changed after it was sealed": lambda: cited.write_bytes(saved + b"\nedited\n"),
        "another sealed record under its name": lambda: cited.write_bytes((aew_root / INGESTED_CHECK).read_bytes()),
        "its log changed": lambda: log.write_bytes(saved_log + b"\nedited\n"),
    }
    for what, damage in cases.items():
        damage()
        out = aew(t, "migrate", "--expect-rev", str(t.rev()))
        assert out.error["code"] == "INTEGRITY_ERROR" and "INV-0003-check-unit-4" in out.error["message"], what
        assert load_control(t.root)["schema"] == "aew/control/v1", what
        cited.write_bytes(saved)
        log.write_bytes(saved_log)
    out = aew(t, "migrate", "--expect-rev", str(t.rev()))
    assert out.returncode == 0 and out.json["migrated"] is True, out.stderr


def legacy_migrated(tmp_path: Path, monkeypatch: Any) -> CP.Template:
    """A project migrated by the head the re-review found (P3-R2): its bundle is ``aew/archive/v1`` and records no
    cited checks."""
    from aew.engine import archive_ops

    t = CP.make_template(tmp_path / "repo")
    with monkeypatch.context() as m:
        m.setattr(archive_ops, "ARCHIVE_SCHEMA", archive_ops.LEGACY_ARCHIVE_SCHEMA)
        m.setattr(archive_ops, "cited_checks", lambda *_: [])
        Engine.discover(t.root).migrate(token=t.token, expect_rev=t.rev())
    bundle = load_yaml((t.root / ".aew" / bundle_rel("T-0001")).read_text(encoding="utf-8"))
    assert bundle["schema"] == archive_ops.LEGACY_ARCHIVE_SCHEMA and not bundle.get("cited_evidence")
    return t


def test_an_older_v2_archive_audits_clean_only_once_its_closure_is_recorded(tmp_path, monkeypatch):
    t = legacy_migrated(tmp_path, monkeypatch)
    # Until the closure is recorded, a full audit cannot pass, but it finds no damage either.
    audit = aew(t, "history", "audit", "--full")
    assert audit.error["code"] == "INTEGRITY_ERROR"
    assert any("T-0001" in p and "aew migrate" in p for p in audit.error["details"]["audit"]["problems"])
    recorded = aew(t, "history", "audit", "--full", "--expect-rev", str(t.rev()))
    assert recorded.error["code"] == "INTEGRITY_ERROR" and "verified" not in load_control(t.root)["cold"]
    assert not [a for a in aew(t, "history", "show", "T-0001").json.get("annotations") or []
                if a["entry"]["rel"] == "audit_finding"]
    # The upgrade: an append-only annotation pins the cited checks; the bundle is untouched.
    bundle = (t.root / ".aew" / bundle_rel("T-0001")).read_bytes()
    up = aew(t, "migrate", "--expect-rev", str(t.rev()))
    assert up.returncode == 0 and up.json["migrated"] is False, up.stderr
    assert [c["id"] for c in up.json["closure"]] == ["T-0001"]
    assert "INV-0003-check-unit-4" in up.json["closure"][0]["cited"]
    assert (t.root / ".aew" / bundle_rel("T-0001")).read_bytes() == bundle
    again = aew(t, "migrate", "--expect-rev", str(t.rev()))
    assert again.json["migrated"] is False and "closure" not in again.json  # idempotent
    clean = aew(t, "history", "audit", "--full")
    assert clean.returncode == 0 and clean.json["ok"] is True, clean.stderr
    shown = aew(t, "history", "show", "INV-0003-check-unit-4")
    assert shown.returncode == 0 and shown.json["held_by"] == "T-0001", shown.stderr
    # The cited check and its log are now covered.
    for rel in (CITED, CITED_LOG):
        path = t.root / ".aew" / rel
        saved = path.read_bytes()
        path.write_bytes(saved + b"\nedited\n")
        audit = aew(t, "history", "audit", "--full")
        assert audit.error["code"] == "INTEGRITY_ERROR", rel
        assert any(rel in p for p in audit.error["details"]["audit"]["problems"]), rel
        path.write_bytes(saved)
    assert_control_invariants(t)


def test_the_upgrade_refuses_a_cited_check_already_changed(tmp_path, monkeypatch):
    t = legacy_migrated(tmp_path, monkeypatch)
    cited = t.root / ".aew" / CITED
    cited.write_bytes(cited.read_bytes() + b"\nedited\n")
    rev = t.rev()
    out = aew(t, "migrate", "--expect-rev", str(rev))
    assert out.error["code"] == "INTEGRITY_ERROR" and "INV-0003-check-unit-4" in out.error["message"]
    assert t.rev() == rev  # nothing recorded
