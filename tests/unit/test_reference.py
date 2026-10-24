"""The generated as-built reference, ``docs/reference/`` (STG-12 S12-2): one generator, checked in CI.

``tools/reference.py render`` writes the directory and ``check`` regenerates it in memory and fails on any difference.
This module is how CI runs ``check`` (in the fast lane, on Linux and on Windows, so the same committed bytes must pass
on both: that is the cross-OS proof), and it holds the generator's own guarantees: the output is deterministic (two
renders, and renders in fresh processes under different hash seeds), private (no absolute path, no timestamp, no
carriage return, nothing naming this machine), and in the shape the design side's trace reads (addendum 1). Each check
has its planted wrong case, so a check that stopped checking would fail here.

The entry-points family's own guarantees, which read the source by two independent detectors, are in
``tests/integration/test_reference_entry_points.py``.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import pkgutil
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reference_tool", ROOT / "tools" / "reference.py")
assert _spec is not None and _spec.loader is not None
reference = importlib.util.module_from_spec(_spec)
sys.modules["reference_tool"] = reference
_spec.loader.exec_module(reference)
C, PAGES, FAMILIES = reference._families()
MODULES = FAMILIES[0]
OUT = reference.OUT


@cache
def rendered() -> dict[str, bytes]:
    return reference.render_files(ROOT)


def committed() -> dict[str, bytes]:
    return reference._on_disk(OUT)


def index_of(files: dict[str, bytes]) -> dict[str, Any]:
    return json.loads(files["index.json"])


# ------------------------------------------------------------------------------------------ the CI check

def test_the_committed_reference_is_what_the_code_gives():
    """The check CI runs. A failure names the first file that differs and the command that settles it."""
    found = reference.check(ROOT, OUT, rendered())
    assert found == [], "\n".join(found)


def test_a_planted_drift_fails_the_check_and_the_message_names_the_command(tmp_path):
    """The wrong case and the missing case of the check: a changed byte, a deleted record, a deleted file, a stray
    file, a stray subdirectory (a nested file included), a carriage return. Each is a difference, and the check's last
    line is the command that fixes it."""
    files = rendered()
    index = files["index.json"].decode("utf-8")
    victim = next(k for k in index_of(files)["records"] if k.startswith("entry-points:"))
    planted = {
        "a changed byte": {"index.json": index.replace('"kind"', '"kinD"', 1).encode()},
        "a deleted record": {"index.json": C.dumps({**json.loads(index), "records": {
            k: v for k, v in json.loads(index)["records"].items() if k != victim}}).encode()},
        "a deleted file": {"entry-points.md": None},
        "a carriage return": {"gaps.md": files["gaps.md"].replace(b"\n", b"\r\n")},
        "a stray file": {"stray.md": b"# Stray\n"},
        "a stray nested json": {"extra/stray.json": b"{}\n"},  # review of #241, F4: neither check nor render saw it
        "an empty page": {"README.md": b""},
    }
    for what, change in planted.items():
        out = tmp_path / what.replace(" ", "-")
        out.mkdir()
        for name, data in {**files, **change}.items():
            if data is not None:
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                (out / name).write_bytes(data)
        found = reference.check(ROOT, out, files)
        assert found, f"{what} is not a difference"
        assert C.RENDER_COMMAND in found[-1], what
    nested = reference.check(ROOT, tmp_path / "a-stray-nested-json", files)
    assert any("extra/stray.json" in f and "not a file the generator writes" in f for f in nested), nested
    assert reference.check(ROOT, OUT, files) == []  # the committed directory was not touched


def test_render_writes_what_check_accepts_removes_strays_at_any_depth_and_is_idempotent(tmp_path):
    out = tmp_path / "reference"
    (out / "extra" / "deeper").mkdir(parents=True)
    (out / "stray.md").write_bytes(b"x")
    (out / "extra" / "stray.json").write_bytes(b"{}")
    (out / "extra" / "deeper" / "more.json").write_bytes(b"{}")
    changed = reference.render(ROOT, out, rendered())
    assert {"stray.md", "extra/stray.json", "extra/deeper/more.json", "extra/", "extra/deeper/"} <= set(changed)
    assert not (out / "stray.md").exists() and not (out / "extra").exists()
    assert reference.check(ROOT, out, rendered()) == []
    assert reference.render(ROOT, out, rendered()) == []  # nothing to write the second time
    assert committed() == {name: (out / name).read_bytes() for name in sorted(os.listdir(out))}


# ------------------------------------------------------------------------------------------ determinism

def test_two_renders_in_one_process_are_byte_identical():
    again = reference.render_files(ROOT)
    assert again == rendered()


SNIPPET = """
import hashlib, importlib.util, json, sys
spec = importlib.util.spec_from_file_location("reference_tool", sys.argv[1])
m = importlib.util.module_from_spec(spec)
sys.modules["reference_tool"] = m
spec.loader.exec_module(m)
print(json.dumps({k: hashlib.sha256(v).hexdigest() for k, v in sorted(m.render_files(m.ROOT).items())}))
"""


def test_renders_in_fresh_processes_under_different_hash_seeds_are_byte_identical(tmp_path):
    """A set or dict order that leaks into the output shows up as a different hash under a different seed."""
    env_base = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    procs = [subprocess.Popen([sys.executable, "-c", SNIPPET, str(ROOT / "tools" / "reference.py")],
                              env={**env_base, "PYTHONHASHSEED": seed}, cwd=tmp_path, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, creationflags=flags) for seed in ("1", "2718")]
    digests = []
    for proc in procs:
        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise
        assert proc.returncode == 0, stderr.decode("utf-8", "replace")[-800:]
        digests.append(json.loads(stdout))
    here = {k: hashlib.sha256(v).hexdigest() for k, v in rendered().items()}
    assert digests[0] == digests[1] == here


# ------------------------------------------------------------------------------------------ private, LF, shaped

def test_the_committed_files_are_lf_only_ascii_where_json_and_name_nothing_private():
    files = committed()
    assert files, "docs/reference is empty"
    for name, data in files.items():
        assert C.text_problems(name, data.decode("utf-8"), Path.home()) == []
    assert files["index.json"].isascii() and files["index.json"].endswith(b"}\n")


@pytest.mark.parametrize(("text", "what"), [
    ("path C:\\Users\\someone\\x", "a drive-letter path"),
    ("path C:/Users/someone/x", "a drive-letter path"),
    ("path /home/someone/x", "an absolute path"),
    ("at /Users/someone/x", "an absolute path"),
    ("built 2026-10-23T12:00:00Z", "a timestamp"),
    ("a\r\nb", "carriage return"),
])
def test_the_privacy_check_sees_each_wrong_case(text, what):
    assert any(what in p for p in C.text_problems("f", text))


@pytest.mark.parametrize("text", [
    "src/aew/engine/store.py", "the dashboard, 127.0.0.1:4261", "tools/reference.py", "https://example.invalid/a/b",
    "version 3.11", "aew.process_kind:ENTRY_POINTS"])
def test_the_privacy_check_passes_the_right_case(text):
    assert C.text_problems("f", text) == []


def test_the_privacy_check_sees_this_machines_home_directory_in_every_spelling():
    home = Path("C:\\Users\\Example Person") if os.name == "nt" else Path("/opt/example-person")
    for spelling in (str(home), home.as_posix(), str(home).replace("\\", "\\\\")):
        assert any("home directory" in p for p in C.text_problems("f", f"x {spelling} y", home)), spelling


# The shape of the design workspace's requirement IDs, exactly as its pack cutter matches it. The cutter checks each
# match against its own index of requirements, so a code fact passes there; this repository has no such index, so here
# a match is a hit unless it is allowed below, each entry with its reason. The allowlist is minimal: an entry is added
# when a page first needs it, in the pull request that adds the page, where its reason is reviewed (a standard such as
# SHA-256 or UTF-8, or a family's own name such as DOC-03, is allowed then, not before). Measured over the committed
# pages when this test was written: 2 matches, both `STG-02` (the table's reason for the STG-02 slice's producer).
ID_SHAPE = re.compile(
    r"(?<![\w/.-])([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-[A-Z]?\d{1,3}[a-z]?(?:\.[a-z0-9]{1,3})?)(?![\w-])")
ID_ALLOWED = {
    "STG-02": "a stage: the code's own name for the slice (`aew.process_kind`'s reason for `aew.stg02.server`)",
}


def id_hits(text: str) -> list[str]:
    """What in ``text`` is a requirement or register ID and is not allowed: the design workspace's shape, and the
    repository's own ledger prefixes and register row ids, each exactly as its owner has it."""
    found = {m.group(1) for m in ID_SHAPE.finditer(text)} | {m.group(0) for m in derived_id_pattern().finditer(text)}
    return sorted(found - set(ID_ALLOWED))


@cache
def derived_id_pattern() -> re.Pattern[str]:
    """The IDs the repository itself owns, built from their owners (derive, don't restate): the requirements ledger's
    source prefixes (``<PREFIX>-<n>``, the shape ``test_requirements_ledger`` gives them), the register's row-id shape
    (``tools/register.py``'s ``ID_RE``) and the register's own row ids, ``STG-NN`` included."""
    import yaml

    ledger = yaml.safe_load((ROOT / "docs" / "design" / "requirements-ledger.yaml").read_text(encoding="utf-8"))
    prefixes = sorted({s["prefix"] for s in ledger["sources"]}, key=len, reverse=True)
    spec = importlib.util.spec_from_file_location("register_for_reference", ROOT / "tools" / "register.py")
    assert spec is not None and spec.loader is not None
    register = importlib.util.module_from_spec(spec)
    sys.modules["register_for_reference"] = register
    spec.loader.exec_module(register)
    rows = yaml.safe_load(register.YAML.read_text(encoding="utf-8"))["sections"]
    row_ids = {str(r["#"]) for s in rows for r in s.get("rows", []) if isinstance(r, dict) and r.get("#")}
    shaped = {i for i in row_ids if re.fullmatch(r"[A-Z][A-Z0-9]*(?:-[0-9]+[a-z]?)?(?:\.[0-9]+)?", i)
              and any(c.isdigit() for c in i)}
    parts = [r"(?:" + "|".join(re.escape(p) for p in prefixes) + r")-\d+[a-z]?",
             register.ID_RE.pattern.removeprefix("^").removesuffix("$"),
             *(re.escape(i) for i in sorted(shaped, key=len, reverse=True))]
    return re.compile(r"(?<![\w.-])(?:" + "|".join(parts) + r")(?![\w-])")


def test_no_requirement_id_is_in_the_reference():
    """The trace is the design side's: the repository states what the code is, never what it should be, and holds no
    requirement ID. The design side's pack cutter checks each ID it finds against its index at the cut; this test is
    the earlier, shape-based check. (Requirement text, as against an ID, is not something either can match.)"""
    found = {name: id_hits(data.decode("utf-8")) for name, data in committed().items()}
    assert {name: hits for name, hits in found.items() if hits} == {}


@pytest.mark.parametrize("text", [
    "see CRD-13", "MOD-08", "WIS-01a", "D-CS1-12", "CS-01", "CB-09", "AIR-75.", "(WCA-3)", "CRD-13a",   # design shapes
    "STG-05",                                           # a stage name nobody has allowed: the allowlist is deliberate
    "SHA-256", "UTF-8", "DOC-03",                       # standards and family names too, until a page needs them
    "register F44", "row F15.2 says", "E71"])           # the register's own row ids
def test_the_id_check_sees_each_wrong_case(text):
    assert id_hits(text), text


@pytest.mark.parametrize("text", [
    "STG-02",                                                                        # allowed, with its reason
    "aew.process_kind:ENTRY_POINTS", "python3.11", "http-problem-matrix", "src/aew/engine/store.py", "version 0.5.4",
    "entry-points:aew.stg02.server", "an ordinary sentence."])
def test_the_id_check_leaves_what_is_allowed_or_not_an_id_alone(text):
    assert id_hits(text) == [], text


def test_every_allowed_id_has_its_reason_is_matched_by_the_shape_and_is_used_by_a_committed_page():
    """An allowlist entry that no committed page uses pre-authorises a token before any page needs it (review of #241,
    F5): it is dead, and the next page to quote that token would pass without a review of the allowance. One the shape
    would not match needs no entry, and one without a reason is a hole."""
    pages = " ".join(data.decode("utf-8") for data in committed().values())
    for entry, reason in ID_ALLOWED.items():
        assert reason.strip(), entry
        assert ID_SHAPE.search(entry), f"{entry} is not matched by the shape, so it needs no entry"
        assert entry in pages, f"{entry} occurs in no committed page: drop it until a page needs it"


def test_the_committed_index_is_in_the_shape_the_trace_reads():
    index = index_of(committed())
    assert C.index_problems(index) == []
    assert list(index) == ["counts", "gaps", "records", "schema"] and index["schema"] == C.SCHEMA
    assert index["counts"]["records"] == len(index["records"])
    for rid, r in index["records"].items():
        assert set(r) <= {"family", "anchor", "basis", "coverage", "fact", "fact_coverage", "imports"}, rid
        assert set(r["anchor"]) == {"module", "symbol"}, rid


def small_index() -> dict[str, Any]:
    mod = C.Record(C.MODULES, "aew.a", "aew.a", None, "static", C.lower_bound(), {"path": "src/aew/a.py"}, [])
    other = C.Record(C.MODULES, "aew.b", "aew.b", None, "static",
                     C.lower_bound([C.unresolved_item("aew.b", "f", "a computed import")]), {"path": "src/aew/b.py"},
                     ["aew.a"])
    fact = {"n": 1, "items": [{"x": 1}]}  # a list fact a detector found; how complete it is is on the record
    fact_coverage = {"items": C.lower_bound([C.unresolved_item("aew.a", "T", "an item not resolved")])}
    rec = C.Record("things", "t1", "aew.a", "T", "enumerated", C.complete("aew.a:T", ["tests/x.py::t"]), fact,
                   fact_coverage=fact_coverage)
    return C.build_index([mod, other, rec])


def reseal(index: dict[str, Any]) -> None:
    """Recompute the summaries a record edit changes (``gaps``, ``counts`` and its ``digest``) from the mutated records,
    as the generator would. ``counts.digest`` covers every record, so without this every planted record fault is also
    refused for a stale digest, and a rule that stopped checking would still pass (review of #241, F9)."""
    try:
        gaps = C.gaps_of(index["records"])
    except (KeyError, TypeError, AttributeError):
        return  # a malformed unresolved item: index_problems returns early on it, and says so
    rows = [(r.get("family", ""), r["coverage"]["label"]) for r in index["records"].values()
            if isinstance(r.get("coverage"), dict) and r["coverage"].get("label") in C.LABELS]
    index["gaps"] = gaps
    index["counts"] = {**C.counts_of(rows, len(gaps)), "digest": C.digest_of(index["records"], gaps)}


def plant(mutate, *fragments: str, sealed: bool = True, only: bool = False):
    """A planted fault: how to plant it; the fragments of the message of the rule that must refuse it (a fault refused
    by another rule does not count); whether the index is resealed after planting (a fault in the summaries themselves
    is planted on a sealed index and left unsealed); and whether that rule must be the only one to speak."""
    return mutate, fragments, sealed, only


def t1(i: dict[str, Any]) -> dict[str, Any]:
    return i["records"]["things:t1"]


def mod_a(i: dict[str, Any]) -> dict[str, Any]:
    return i["records"]["modules:aew.a"]


def mod_b(i: dict[str, Any]) -> dict[str, Any]:
    return i["records"]["modules:aew.b"]


DIGEST = "counts (with its digest) is not what the records and gaps give"
MUTATIONS = {
    # the record-level rules
    "an anchor module with no modules record": plant(lambda i: t1(i)["anchor"].update(module="aew.zz"),
                                                     "its module aew.zz has no modules record"),
    "an anchor without its module": plant(lambda i: t1(i)["anchor"].update(module=""), "no anchor.module"),
    "a basis outside the four": plant(lambda i: t1(i).update(basis="guessed"), "is not one of"),
    "a record without its basis": plant(lambda i: t1(i).pop("basis"), "is not one of"),
    "a non-module record without its symbol": plant(lambda i: t1(i)["anchor"].update(symbol=None),
                                                    "no anchor.symbol"),
    "a module with a symbol": plant(lambda i: mod_a(i)["anchor"].update(symbol="x"), "symbol must be null"),
    "a module without its imports": plant(lambda i: mod_b(i).pop("imports"), "imports is not a sorted list"),
    "imports out of order": plant(lambda i: mod_b(i).update(imports=["aew.b", "aew.a"]),
                                  "imports is not a sorted list"),
    "an import with no modules record": plant(lambda i: mod_b(i).update(imports=["aew.zz"]),
                                              "imports aew.zz, which has no modules record"),
    "imports on a record that is not a module": plant(lambda i: t1(i).update(imports=[]),
                                                      "only a modules record has imports"),
    "an id that does not start with its family": plant(
        lambda i: i["records"].update({"other:t1": i["records"].pop("things:t1")}),
        "does not start with its family"),
    # the coverage rules, on a record and on a list fact
    "a coverage that is not an object": plant(lambda i: t1(i).update(coverage=[]), "coverage is not an object"),
    "complete-by-construction without its check": plant(lambda i: t1(i)["coverage"].pop("check"),
                                                        "complete-by-construction without its check"),
    "complete-by-construction with an empty check": plant(lambda i: t1(i)["coverage"].update(check=[]),
                                                          "complete-by-construction without its check"),
    "complete-by-construction without its registry": plant(lambda i: t1(i)["coverage"].pop("registry"),
                                                           "complete-by-construction without its registry"),
    # the clauses of those rules (review of #241, N3): an empty registry; a check that is a string, or has a non-string;
    # an unresolved item, and a gap, with an empty why. The generator refuses each; a reader that checks presence only
    # accepts them, so nothing else holds them
    "complete-by-construction with an empty registry": plant(lambda i: t1(i)["coverage"].update(registry=""),
                                                             "complete-by-construction without its registry"),
    "complete-by-construction with a check that is a string": plant(
        lambda i: t1(i)["coverage"].update(check="tests/x.py::t"), "complete-by-construction without its check"),
    "complete-by-construction with a non-string in its check": plant(
        lambda i: t1(i)["coverage"].update(check=["tests/x.py::t", 3]), "complete-by-construction without its check"),
    "an unresolved item with an empty why": plant(lambda i: mod_b(i)["coverage"]["unresolved"][0].update(why=""),
                                                  "an unresolved item is not"),
    "a gap with an empty why": plant(lambda i: i["gaps"][0].update(why=""), "a gap is not", sealed=False),
    "lower-bound without its unresolved list": plant(lambda i: mod_b(i)["coverage"].pop("unresolved"),
                                                     "lower-bound without its unresolved list"),
    "an unresolved item without its why": plant(lambda i: mod_b(i)["coverage"]["unresolved"][0].pop("why"),
                                                "an unresolved item is not", "an unresolved item is malformed"),
    "a label outside the three": plant(lambda i: t1(i)["coverage"].update(label="complete"),
                                       "coverage label 'complete'"),
    # addendum 3: how complete a list fact is, on the record beside coverage
    "a list fact without its fact_coverage entry": plant(lambda i: t1(i)["fact_coverage"].pop("items"),
                                                         "the list fact 'items' has no fact_coverage entry"),
    "a fact_coverage for a fact the record lacks": plant(
        lambda i: t1(i)["fact_coverage"].update(missing={"label": "unknown"}),
        "fact_coverage for 'missing', which is not a fact of the record"),
    "a fact_coverage label outside the three": plant(lambda i: t1(i)["fact_coverage"]["items"].update(label="complete"),
                                                     "fact_coverage.items: coverage label 'complete'"),
    "a fact_coverage lower-bound without its unresolved list": plant(
        lambda i: t1(i)["fact_coverage"]["items"].pop("unresolved"),
        "fact_coverage.items: lower-bound without its unresolved list"),
    "a fact_coverage unresolved item without its why": plant(
        lambda i: t1(i)["fact_coverage"]["items"]["unresolved"][0].pop("why"),
        "fact_coverage.items: an unresolved item is not", "an unresolved item is malformed"),
    "a fact_coverage that is not an object": plant(lambda i: t1(i).update(fact_coverage=[]),
                                                   "fact_coverage is not an object"),
    "a fact_coverage moved inside fact": plant(
        lambda i: t1(i)["fact"].update(fact_coverage=t1(i).pop("fact_coverage")), "fact_coverage is inside fact"),
    # the case only the nested-placement rule can refuse: a copy left inside fact with the record-level key present
    "a fact_coverage left inside fact beside the record-level one": plant(
        lambda i: t1(i)["fact"].update(fact_coverage=copy.deepcopy(t1(i)["fact_coverage"])),
        "fact_coverage is inside fact", only=True),
    # the summaries themselves: planted on a sealed index and left unsealed
    "no records at all": plant(lambda i: i.update(records={}), "no records object", sealed=False),
    "a wrong schema": plant(lambda i: i.update(schema="aew/reference-index/v0"), "schema is", sealed=False),
    "a gap without its why": plant(lambda i: i["gaps"][0].pop("why"), "a gap is not", sealed=False),
    "an unresolved item of a list fact missing from gaps": plant(
        lambda i: i.update(gaps=[g for g in i["gaps"] if g["family"] != "things"]), "gaps is not the summary",
        sealed=False),
    "a gap that is on no record": plant(
        lambda i: i["gaps"].append({"family": "things", "module": "aew.a", "symbol": None, "why": "only in gaps"}),
        "gaps is not the summary", sealed=False),
    "counts that no longer match": plant(lambda i: i["counts"].update(records=99), DIGEST, sealed=False),
    "a stale digest": plant(lambda i: i["counts"].update(digest="sha256:" + "0" * 64), DIGEST, sealed=False),
}


def test_a_sound_index_has_no_problems_and_each_planted_fault_is_refused_by_its_own_rule():
    """Each planted fault is planted on a sealed index (``reseal``) and must be refused by the rule it plants: the
    message's fragment is asserted, not just a non-empty list, because ``counts.digest`` refuses any edit to a record
    and would mask every rule (review of #241, F9). The faults in the summaries themselves are left unsealed."""
    assert C.index_problems(small_index()) == []
    for what, (mutate, fragments, sealed, only) in MUTATIONS.items():
        broken = copy.deepcopy(small_index())
        mutate(broken)
        if sealed:
            reseal(broken)
        problems = C.index_problems(broken)
        for fragment in fragments:
            assert any(fragment in p for p in problems), (what, fragment, problems)
        if sealed:  # neither the digest nor a stale gaps summary may be what refused it (review of #241, N4)
            assert not any(DIGEST in p for p in problems), (what, problems)
            assert not any("gaps is not the summary" in p for p in problems), (what, problems)
        if only:
            assert len(problems) == 1, (what, problems)


def test_a_benign_edit_to_a_record_is_a_problem_only_until_the_index_is_resealed():
    """Why the planted faults are resealed: the digest alone refuses any edit, benign or not."""
    benign = small_index()
    t1(benign)["fact"]["n"] = 2
    assert C.index_problems(benign) == [DIGEST]
    reseal(benign)
    assert C.index_problems(benign) == []


def test_two_records_with_one_id_are_refused():
    rec = C.Record("things", "t1", "aew.a", "T", "enumerated", C.unknown())
    with pytest.raises(C.ReferenceError, match="not unique"):
        C.build_index([rec, rec])


# ------------------------------------------------------------------------------------------ one tree

def test_the_generator_refuses_an_aew_that_is_not_this_trees(tmp_path):
    (tmp_path / "src").mkdir()
    with pytest.raises(C.ReferenceError, match="absolute PYTHONPATH"):
        reference._one_tree(C, tmp_path)
    reference._one_tree(C, ROOT)  # this tree's own: the tests run with an absolute PYTHONPATH to it


def test_without_an_importable_aew_the_generator_refuses_with_exit_2_not_a_traceback_with_exit_1(monkeypatch, capsys):
    """Exit 1 means the pages differ, and the remedy is `render`; an interpreter that cannot import aew must not look
    like that (review of #241, F7). It is "cannot generate": exit 2, naming the absolute-PYTHONPATH rule."""
    monkeypatch.setitem(sys.modules, "aew", None)  # `import aew` then raises ImportError
    with pytest.raises(C.ReferenceError, match="cannot be imported.*absolute PYTHONPATH"):
        reference._one_tree(C, ROOT)
    assert reference.main(["check"]) == 2
    assert "absolute PYTHONPATH" in capsys.readouterr().err


def test_an_index_problem_states_the_fault_not_the_rule():
    """An error message is behaviour (AGENTS.md): it says what is wrong, not the opposite (review of #241, F8)."""
    broken = small_index()
    broken["records"]["modules:aew.a"]["anchor"]["symbol"] = "x"
    problems = C.index_problems(broken)
    assert any("symbol must be null" in p for p in problems), problems
    assert not any(p.endswith("symbol is null") for p in problems)


# ------------------------------------------------------------------------------- a stale clean merge cannot happen

def merge(base: str, ours: str, theirs: str, tmp_path: Path) -> tuple[int, str]:
    """A real three-way merge of three versions of one file: (the number of conflicts, the merged text)."""
    paths = []
    for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
        paths.append(tmp_path / f"{name}.json")
        paths[-1].write_bytes(text.encode("utf-8"))
    proc = subprocess.run(["git", "merge-file", "-p", *map(str, paths)], capture_output=True, text=True, timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert proc.returncode >= 0, proc.stderr
    return proc.returncode, proc.stdout


def modules_index(names: list[str]) -> dict[str, Any]:
    return C.build_index([C.Record(C.MODULES, n, n, None, "static", C.lower_bound(),
                                   {"path": f"src/{n.replace('.', '/')}.py", "package": False}, []) for n in names])


def test_two_changes_that_each_add_a_module_conflict_instead_of_merging_into_stale_totals(tmp_path):
    """The hazard (review of #241, F3): two pull requests each add a module, each re-renders and passes `check`. Both
    edit the totals (`records`, `by_family`...) to the same text, so git keeps one edit and reports no conflict, and the
    merged `main` says 3 records over 4. The `digest` of every record is on the line that differs, so the merge
    conflicts and the documented step (take either side, run `render`) applies."""
    base, ours, theirs = (modules_index(names) for names in (
        ["aew.m1", "aew.m5"], ["aew.m0", "aew.m1", "aew.m5"], ["aew.m1", "aew.m5", "aew.m9"]))
    merged_by_hand = modules_index(["aew.m0", "aew.m1", "aew.m5", "aew.m9"])
    assert ours["counts"]["records"] == theirs["counts"]["records"] == 3  # the same edit to the totals, from both sides

    conflicts, _ = merge(C.dumps(base), C.dumps(ours), C.dumps(theirs), tmp_path)
    assert conflicts > 0
    # the control: the same merge without the digest line is clean, and its totals are stale
    for index in (base, ours, theirs):
        del index["counts"]["digest"]
    conflicts, text = merge(C.dumps(base), C.dumps(ours), C.dumps(theirs), tmp_path)
    merged = json.loads(text)
    assert conflicts == 0 and len(merged["records"]) == 4 and merged["counts"]["records"] == 3
    assert merged_by_hand["counts"]["records"] == 4


def test_a_change_to_a_record_changes_the_digest_and_no_change_does_not():
    base = modules_index(["aew.m1", "aew.m5"])
    assert modules_index(["aew.m1", "aew.m5"])["counts"]["digest"] == base["counts"]["digest"]
    assert modules_index(["aew.m1", "aew.m6"])["counts"]["digest"] != base["counts"]["digest"]
    changed = small_index()
    changed["records"]["modules:aew.b"]["imports"] = []
    assert C.index_problems(changed)  # the digest (and the shape) notice a record edited in place


# ------------------------------------------------------------------------------- nothing lives only in gaps

def test_every_gap_is_on_a_record_and_nothing_lives_only_in_gaps():
    """`gaps` is a summary computed from the records (addendum 3): the trace reads records only, so each unresolved
    item is on a record, in its `coverage` or in the `fact_coverage` of a list fact, and the summary holds exactly
    those."""
    index = index_of(committed())
    on_records = {(r["family"], i["module"], i["symbol"], i["why"])
                  for r in index["records"].values() for i in C.unresolved_items(r)}
    in_gaps = [(g["family"], g["module"], g["symbol"], g["why"]) for g in index["gaps"]]
    assert set(in_gaps) == on_records and len(in_gaps) == len(set(in_gaps))
    assert on_records, "the tree has dynamic imports and argv constants: they are the items"
    assert index["counts"]["unresolved"] == len(in_gaps)


def test_every_list_fact_a_detector_found_says_how_complete_it_is():
    """A list fact with no entry reads as unknown, and an empty list never means none (addendum 3)."""
    seen = 0
    for rid, r in index_of(committed())["records"].items():
        fact = r.get("fact", {})
        for name, value in fact.items():
            if isinstance(value, list):
                assert r["fact_coverage"][name]["label"] in C.LABELS, (rid, name)
                assert "fact_coverage" not in fact, rid  # on the record, beside coverage
                seen += 1
    assert seen


# ------------------------------------------------------------------------------- every coverage claim names tests

def test_every_check_a_record_names_is_a_test_that_exists():
    """A coverage claim is only as good as the test it names: the file exists and defines the function."""
    seen = 0
    for rid, r in index_of(committed())["records"].items():
        for node_id in r["coverage"].get("check", []):
            path, _, name = node_id.partition("::")
            file = ROOT / path
            assert file.is_file(), f"{rid} names {node_id}, whose file does not exist"
            tree = ast.parse(file.read_text(encoding="utf-8"))
            assert any(isinstance(n, ast.FunctionDef) and n.name == name for n in ast.walk(tree)), f"{rid}: {node_id}"
            seen += 1
    assert seen


# ------------------------------------------------------------------------------------------ the entry-points family

def test_the_entry_point_records_are_the_registry_both_ways():
    """A table pinned against live data, checked both ways: one record per key of ``ENTRY_POINTS`` and no other, each
    carrying the table's own kind and reason."""
    from aew import process_kind

    records = {rid: r for rid, r in index_of(committed())["records"].items() if r["family"] == "entry-points"}
    assert set(records) == {f"entry-points:{key}" for key in process_kind.ENTRY_POINTS}
    for key, (kind, reason) in process_kind.ENTRY_POINTS.items():
        record = records[f"entry-points:{key}"]
        assert (record["fact"]["entry_point"], record["fact"]["kind"], record["fact"]["reason"]) == (key, kind, reason)
        assert record["basis"] == "enumerated" and record["coverage"]["label"] == "complete-by-construction"
        assert record["coverage"]["registry"] == "aew.process_kind:ENTRY_POINTS"
        assert record["fact"]["declared_at"], f"{key} declares itself nowhere"
        assert record["anchor"]["module"] == record["fact"]["declared_at"][0]["module"]


# ------------------------------------------------------------------------------------------ the modules family

def test_the_modules_family_is_the_packages_modules_by_two_derivations():
    """The generator walks the files; the import system walks the package. They must name the same modules."""
    import aew

    by_walk = {"aew"} | {m.name for m in pkgutil.walk_packages(aew.__path__, "aew.")}
    records = {r["anchor"]["module"]: r for r in index_of(committed())["records"].values() if r["family"] == C.MODULES}
    assert set(records) == by_walk
    for name, r in records.items():
        assert (ROOT / r["fact"]["path"]).is_file(), name
        assert not r["fact"]["path"].startswith(("/", "src/../")) and "\\" not in r["fact"]["path"]
        assert r["fact"]["package"] == (Path(r["fact"]["path"]).name == "__init__.py")


KNOWN = frozenset({"aew", "aew.a", "aew.other", "aew.pkg", "aew.pkg.mod", "aew.pkg.sub", "aew.pkg.sub.leaf"})


def edges(source: str, module: str = "aew.pkg.mod", is_package: bool = False):
    return MODULES.edges_of(ast.parse(source), module, is_package, KNOWN)


@pytest.mark.parametrize(("source", "want"), [
    ("from . import sub\n", {"aew.pkg.sub"}),                       # a sibling module imported by name
    ("from .sub import leaf\n", {"aew.pkg.sub.leaf"}),               # a module below it
    ("from .sub import not_a_module\n", {"aew.pkg.sub"}),            # a name in the module: the edge is to the module
    ("from .. import other\n", {"aew.other"}),                       # one level up
    ("from ..other import thing\n", {"aew.other"}),
    ("import aew.a\n", {"aew.a"}),
    ("import aew.a.nope.deeper\n", {"aew.a"}),                       # the longest module that exists
    ("from aew import a\n", {"aew.a"}),
    ("from aew import something\n", {"aew"}),                        # a name in the package itself
    ("def f():\n    from aew.other import x\n", {"aew.other"}),     # in a function: still a static import
    ("from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from aew import a\n", {"aew.a"}),
    ("import os, json\nfrom json import dumps\n", set()),            # outside the package
    ("import aew.pkg.mod\n", set()),                                 # itself
])
def test_the_import_graph_reads_each_form_of_import(source, want):
    assert edges(source)[0] == want


def test_a_package_resolves_a_relative_import_against_itself():
    assert edges("from . import mod\n", "aew.pkg", is_package=True)[0] == {"aew.pkg.mod"}
    assert edges("from .mod import x\n", "aew.pkg", is_package=True)[0] == {"aew.pkg.mod"}


@pytest.mark.parametrize(("source", "edge", "why"), [
    ("import importlib\ndef f(n):\n    return importlib.import_module(n)\n", set(), "computed module name"),
    ("import importlib\nimportlib.import_module('aew.other')\n", {"aew.other"}, None),   # a constant AEW name
    ("import importlib\nimportlib.import_module('json')\n", set(), None),                # a constant outside AEW
    ("import importlib\nimportlib.import_module('aew.nope')\n", set(), "cannot resolve"),
    ("import importlib\nimportlib.import_module('.x', 'aew.pkg')\n", set(), "cannot resolve"),
    ("from importlib import import_module as im\ndef f(n):\n    im(n)\n", set(), "computed module name"),
    ("def f(n):\n    __import__(n)\n", set(), "computed module name"),
    ("import importlib.util\nimportlib.util.spec_from_file_location('n', p)\n", set(), "by file path"),
    ("from importlib import util\nutil.spec_from_file_location('n', p)\n", set(), "by file path"),
    ("def import_module(n):\n    return n\nimport_module(x)\n", set(), None),            # its own, not importlib's
    ("class C:\n    def m(self, n):\n        __import__(n)\n", set(), "computed module name"),
])
def test_a_dynamic_import_is_an_edge_when_its_name_is_constant_and_unresolved_otherwise(source, edge, why):
    found, unresolved = edges(source)
    assert found == edge
    if why is None:
        assert unresolved == []
    else:
        assert len(unresolved) == 1 and why in unresolved[0]["why"], unresolved


def test_an_unresolved_dynamic_import_is_anchored_at_its_enclosing_symbol():
    _, unresolved = edges("class C:\n    def m(self, n):\n        __import__(n)\n")
    assert unresolved[0]["module"] == "aew.pkg.mod" and unresolved[0]["symbol"] == "C.m"


def test_a_module_that_does_not_parse_is_listed_as_unreadable_not_as_having_no_imports(tmp_path):
    package = tmp_path / "src" / "aew"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "ok.py").write_text("from aew import broken\n", encoding="utf-8")
    (package / "broken.py").write_text("def (:\n", encoding="utf-8")
    mods = {m.name: m for m in MODULES.scan(C.Context(tmp_path))}
    assert mods["aew.broken"].imports == () and "does not parse" in mods["aew.broken"].unresolved[0]["why"]
    assert mods["aew.ok"].imports == ("aew.broken",)


def test_a_tree_with_no_package_is_refused_not_rendered_empty(tmp_path):
    with pytest.raises(C.ReferenceError, match="no aew package"):
        C.Context(tmp_path).sources()
