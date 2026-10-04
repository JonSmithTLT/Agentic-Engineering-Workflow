"""T4 probe: can knowledge records (cases, dispositions, capture receipts) live in the ADR-0011 history manifest as
new entry kinds, and what does that cost?

Runs against the frozen tree (dcd43f1) through the test helpers' deterministic history workload. Nothing in
``tree/`` is modified: the schema enum is widened in memory only, which is exactly the one-line change the ADR draft
proposes. Output: ``knowledge_manifest_probe.out.txt`` beside this file.

Questions answered:
  Q1  What refuses a ``case`` entry today?                              (expect: the history schema's kind enum)
  Q2  With the enum widened, do append, chain, verify and index work?   (expect: yes, unchanged code)
  Q3  Which index queries need a generalisation?                         (annotations(subject) is kind-bound)
  Q4  Are orphaned knowledge records reported as unreferenced?           (RECORD_GLOBS is path-bound)
  Q5  Append cost per knowledge entry, full-verify cost per small record, index rebuild at 3,000 cases
  Q6  FTS5 over record bodies in the derived index: build time and query latency at 3,000 cases
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import stat
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TREE = HERE.parent / "tree"
sys.path.insert(0, str(TREE / "tests" / "helpers"))
sys.path.insert(0, str(TREE / "src"))

from history_model import ROOT_REL, archive, init, read_root  # noqa: E402

import aew.schemas as S  # noqa: E402
from aew.engine.store import Transition  # noqa: E402
from aew.errors import ValidationFailed  # noqa: E402
from aew.history import manifest as M  # noqa: E402
from aew.history.index import HistoryIndex  # noqa: E402
from aew.history.store import History  # noqa: E402
from aew.util import dump_yaml  # noqa: E402

OUT: list[str] = []
AT = "2026-10-04T00:00:00Z"
NEW_KINDS = ("case", "lesson", "disposition", "receipt", "reference")


def say(line: str = "") -> None:
    print(line)
    OUT.append(line)


def rm_rf(path: Path) -> None:
    def onexc(fn, p, exc):
        Path(p).chmod(stat.S_IWRITE)
        fn(p)

    if path.exists():
        shutil.rmtree(path, onexc=onexc)


def case_record(n: int, unit: str, evidence: str) -> str:
    return dump_yaml({
        "schema": "aew/knowledge/case/v1", "id": f"K-{n:04d}", "version": 1, "record_kind": "case",
        "template": "attempt-outcome/v1", "authority_class": "advisory",
        "subject_refs": [unit, "component:calc.core"], "canonical_refs": [],
        "root_evidence_bindings": [{"evidence_id": evidence, "relation": "derived_from", "basis": "literal_outcome"}],
        "observed_conditions": {"platform": "windows", "python": "3.12", "check": "unit"},
        "fields": {"condition": f"check unit failed on attempt {n}", "action": "regenerated fixture",
                   "result": f"check unit passed, {n % 7} tests"},
        "source_classes": {"condition": "ENGINE_OBSERVED_WEAK_BOUNDARY", "result": "ENGINE_OBSERVED_WEAK_BOUNDARY",
                           "action": "ROLE_ATTESTED"},
        "limitations": ["single attempt"], "unknowns": ["root cause"], "created_at": AT,
    })


def disposition_record(n: int, case_id: str, rel: str) -> str:
    return dump_yaml({"schema": "aew/knowledge/disposition/v1", "id": f"KD-{n:04d}", "subject": {"id": case_id,
                      "version": 1}, "rel": rel, "disposition_seq": 1, "policy_version": "k1-templates/v1",
                      "serving_eligibility": "explicit_investigation_only", "actor": {"kind": "service",
                      "identity": "knowledge-capture"}, "at": AT})


def receipt_record(n: int, revision: int, produced: list[str]) -> str:
    return dump_yaml({"schema": "aew/knowledge/receipt/v1", "id": f"KR-{n:04d}", "job": {"project": "probe",
                      "revision": revision, "event_index": 0}, "status": "COMPLETE", "produced": produced,
                      "no_candidate": not produced, "extractor": {"template_set": "k1-templates/v1"}, "at": AT})


def widen_schema() -> None:
    """The in-memory equivalent of the ADR's schema change: five new entry kinds, and the module constant."""
    schema = S._validator("history").schema  # cached; _def_validator shares its $defs dict
    enum = schema["$defs"]["entry"]["properties"]["kind"]["enum"]
    enum.extend(k for k in NEW_KINDS if k not in enum)
    M.ENTRY_KINDS = tuple(enum)  # type: ignore[misc]


def append_knowledge(store, items: list[tuple[str, str, dict]]) -> dict:
    """One capture-job commit: records then entries, like Archive.finalize does for bundles."""
    history = History(store.root)
    with store.session() as s:
        fields = []
        for rel, content, f in items:
            sha = history.write_record(s, rel, content)
            fields.append({**f, "path": rel, "sha256": sha})
        root = history.append(s, read_root(store.root), fields)
        s.write(ROOT_REL, dump_yaml(root), immutable=False)
        s.commit(Transition(op="knowledge.capture", actor={"kind": "service", "identity": "knowledge-capture"},
                            summary=f"{len(items)} knowledge records"))
    return root


def main() -> None:
    work = HERE / "work-t4"
    rm_rf(work)
    work.mkdir()
    store = init(work)
    for _ in range(3):
        archive(store, 1)
    say("# T4 knowledge manifest probe (tree dcd43f1, in-memory schema widening only)")
    say(f"baseline: 3 archived units, root count {read_root(work)['count']}")

    # Q1 -------------------------------------------------------------------------------------------------------
    say("\n## Q1: what refuses a `case` entry today")
    try:
        M.new_entry(4, read_root(work)["head_h"], {"kind": "case", "id": "K-0001", "path": "knowledge/cases/K-0001/v1.yaml",
                                                    "sha256": "0" * 64, "at": AT, "source": "engine"})
        say("UNEXPECTED: accepted")
    except ValidationFailed as exc:
        say(f"refused by: {exc.message}")
        for v in exc.details.get("violations", []):
            say(f"  {v}")
    say("nothing else in manifest.py / store.py / index.py names a kind: the enum (and ENTRY_KINDS for `history "
        "list --kind`) is the only gate")

    # Q2 -------------------------------------------------------------------------------------------------------
    say("\n## Q2: with the enum widened, append / chain / verify / index on unchanged code")
    widen_schema()
    rev = store.read()["revision"]
    items = [
        ("knowledge/cases/K-0001/v1.yaml", case_record(1, "T-0001", "E-0001"),
         {"kind": "case", "id": "K-0001", "at": AT, "source": "engine",
          "links": {"derived_from": ["E-0001"], "subject": ["T-0001", "component:calc.core"], "job": ["KR-0001"]}}),
        ("knowledge/cases/K-0001/dispositions/0001.yaml", disposition_record(1, "K-0001", "admitted"),
         {"kind": "disposition", "id": "KD-0001", "at": AT, "source": "engine", "subject": "K-0001",
          "rel": "admitted", "links": {"admitted": ["K-0001"]}}),
        ("knowledge/receipts/KR-0001.yaml", receipt_record(1, rev, ["K-0001"]),
         {"kind": "receipt", "id": "KR-0001", "at": AT, "source": "engine",
          "links": {"produced": ["K-0001"], "outbox": [f"rev:{rev}"]}}),
    ]
    root = append_knowledge(store, items)
    say(f"appended 3 knowledge entries in one commit; root count {root['count']}")
    report = History(work).verify(root)
    say(f"verify(records=True): ok={report.ok} entries={report.entries} records={report.records} "
        f"problems={report.problems}")
    index = HistoryIndex(work)
    say(f"index.sync: {index.sync(root)}")
    say(f"by_id(K-0001): {[(e['seq'], e['kind']) for e in index.by_id('K-0001')]}")
    say(f"list(kind=case): {[e['id'] for e in index.list(kind='case')]}")
    say(f"linked(derived_from, E-0001): {[e['id'] for e in index.linked('derived_from', 'E-0001')]}")
    say(f"linked(subject, T-0001): {[e['id'] for e in index.linked('subject', 'T-0001')]}")
    say(f"links(K-0001): {index.links('K-0001')}")

    # Q3 -------------------------------------------------------------------------------------------------------
    say("\n## Q3: which queries are kind-bound")
    say(f"annotations('K-0001') (kind='annotation' only): {index.annotations('K-0001')}  <- dispositions invisible")
    rows = index._rows("SELECT body FROM entries WHERE subject = ? AND seq <= ? ORDER BY seq", ("K-0001", index._upto()),
                       lambda e: e.get("subject") == "K-0001")
    say(f"a kind-free about(subject) query finds: {[(e['kind'], e['id'], e.get('rel')) for e in rows]}")
    say("finding: the index needs `about(subject, kinds=None)`; `annotations()` becomes a special case. The entry's "
        "`subject`/`rel` columns already carry what a disposition needs (schema unchanged)")

    # Q4 -------------------------------------------------------------------------------------------------------
    say("\n## Q4: orphaned knowledge records and RECORD_GLOBS")
    orphan = work / "knowledge/cases/K-9999/v1.yaml"
    orphan.parent.mkdir(parents=True)
    orphan.write_text(case_record(9999, "T-0001", "E-0001"), encoding="utf-8")
    say(f"unreferenced() with an orphan under knowledge/: {History(work).unreferenced(index.paths())}  <- not seen")
    from aew.history import store as HS
    HS.RECORD_GLOBS = HS.RECORD_GLOBS + ("knowledge/**/*.yaml",)
    say(f"with RECORD_GLOBS += knowledge/**/*.yaml: {History(work).unreferenced(index.paths())}")
    orphan.unlink()

    # Q5 -------------------------------------------------------------------------------------------------------
    say("\n## Q5: cost at 3,000 cases (one case + one disposition per capture job, 50 jobs per commit)")
    n = 1
    lat = []
    t_all = time.perf_counter()
    for batch in range(60):
        items = []
        rev = store.read()["revision"]
        for _ in range(50):
            n += 1
            unit = f"T-{(n % 3) + 1:04d}"
            items.append((f"knowledge/cases/K-{n:04d}/v1.yaml", case_record(n, unit, f"E-{n:04d}"),
                          {"kind": "case", "id": f"K-{n:04d}", "at": AT, "source": "engine",
                           "links": {"derived_from": [f"E-{n:04d}"], "subject": [unit], "job": [f"KR-{n:04d}"]}}))
            items.append((f"knowledge/cases/K-{n:04d}/dispositions/0001.yaml",
                          disposition_record(n, f"K-{n:04d}", "admitted"),
                          {"kind": "disposition", "id": f"KD-{n:04d}", "at": AT, "source": "engine",
                           "subject": f"K-{n:04d}", "rel": "admitted", "links": {"admitted": [f"K-{n:04d}"]}}))
        t0 = time.perf_counter()
        root = append_knowledge(store, items)
        lat.append((time.perf_counter() - t0) * 1000)
    t_all = time.perf_counter() - t_all
    lat.sort()
    say(f"root count {root['count']} ({root['sealed_head']['seq']} sealed segments); 60 commits of 100 records: "
        f"median {lat[len(lat)//2]:.0f} ms, p95 {lat[int(len(lat)*0.95)]:.0f} ms, first {lat[0]:.0f} ms, "
        f"last-sorted {lat[-1]:.0f} ms; total {t_all:.1f} s")
    sizes = [p.stat().st_size for p in (work / "knowledge/cases").glob("K-0002/**/*.yaml")]
    say(f"record sizes: case+disposition for one job = {sum(sizes)} bytes")
    t0 = time.perf_counter()
    report = History(work).verify(root)
    dt = time.perf_counter() - t0
    say(f"full verify(records=True): ok={report.ok} entries={report.entries} records={report.records} in {dt:.2f} s "
        f"= {dt / report.records * 1000:.2f} ms/record (investigation: ~3 ms per 20 KB bundle)")
    t0 = time.perf_counter()
    report = History(work).verify(root, records=False)
    say(f"chain-only verify: {time.perf_counter() - t0:.2f} s")
    (work / "local/history.sqlite").unlink(missing_ok=True)
    index = HistoryIndex(work)
    t0 = time.perf_counter()
    out = index.sync(root)
    say(f"index rebuild from manifest: {out} in {time.perf_counter() - t0:.2f} s")
    t0 = time.perf_counter()
    hit = index.by_id("K-1500")
    say(f"by_id(K-1500): {len(hit)} entry in {(time.perf_counter() - t0) * 1000:.1f} ms (authenticated against the chain)")
    t0 = time.perf_counter()
    subj = index.linked("subject", "T-0002")
    say(f"linked(subject, T-0002): {len(subj)} cases in {(time.perf_counter() - t0) * 1000:.0f} ms "
        "(authenticates every returned entry: cost scales with the result, as the investigation says it may)")

    # Q6 -------------------------------------------------------------------------------------------------------
    say("\n## Q6: FTS5 over record bodies, as a derived table in the same local/ index")
    say(f"sqlite {sqlite3.sqlite_version}; fts5 compiled in: "
        f"{any('FTS5' in r[0] for r in sqlite3.connect(':memory:').execute('PRAGMA compile_options'))}")
    conn = sqlite3.connect(work / "local/history.sqlite")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(id UNINDEXED, kind UNINDEXED, body)")
    t0 = time.perf_counter()
    rows = []
    for e in History(work).walk(root):
        if e["kind"] in NEW_KINDS:
            rows.append((e["id"], e["kind"], (work / e["path"]).read_text(encoding="utf-8")))
    conn.executemany("INSERT INTO fts (id, kind, body) VALUES (?, ?, ?)", rows)
    conn.commit()
    say(f"indexed {len(rows)} record bodies in {time.perf_counter() - t0:.2f} s (walk + read + insert)")
    for q in ("regenerated AND fixture", "\"check unit failed\"", "ROLE_ATTESTED", "\"calc.core\"", "fixture NOT regenerated"):
        t0 = time.perf_counter()
        hits = conn.execute("SELECT id FROM fts WHERE fts MATCH ? ORDER BY rank LIMIT 20", (q,)).fetchall()
        total = conn.execute("SELECT count(*) FROM fts WHERE fts MATCH ?", (q,)).fetchone()[0]
        say(f"  MATCH {q!r}: {total} hits, top 20 in {(time.perf_counter() - t0) * 1000:.1f} ms")
    size = (work / "local/history.sqlite").stat().st_size
    say(f"local/history.sqlite with entries + links + fts: {size / 1024:.0f} KB for {root['count']} entries")
    conn.close()
    say("\nfts rows are locators like every other index row: a hit's id goes through by_id() -> authenticate() -> "
        "record() before anything is shown, so a tampered fts body can hide a record, never invent one (P3-1 rule).")

    (HERE / "knowledge_manifest_probe.out.txt").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    rm_rf(work)


if __name__ == "__main__":
    main()
