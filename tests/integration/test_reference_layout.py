"""The layout family of the generated reference (STG-12 S12-2, DOC-04), on the tree: what holds for ``src/aew``.

* the two readers of read primitives (``ast`` in ``layout_reads.py``, tokens in ``layout_reads_text.py``, sharing no
  code) find the same calls in every module;
* the entries are the declared top-level set and every directory above a path the writers and the readers place, both
  ways;
* each flag is checked against the thing it describes, not against the owner it was derived from: git says which entries
  it ignores, the engine says where its store is, the containment layout says which paths it hides;
* a spot check that the reading agrees with a hand reading of the code for the readers and writers that matter;
* a reader planted in a copy of the tree is a record, one under an unknown directory is an unplaced read, and a read at
  import time is refused.

The planted cases of each rule, with their right, wrong and missing cases, are in
``tests/unit/test_reference_layout_rules.py``. The heavy lanes run this because it reads ``src`` only.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import git, make_git_repo

from aew.engine.api import AEW_GITIGNORE, Engine
from aew.engine.store import STORE_REL
from aew.harness.containment import layout as containment

ROOT = Path(__file__).resolve().parents[2]
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, layout, layout_reads, layout_reads_text, writers, writers_flow
    finally:
        sys.path.remove(here)
    return common, layout, layout_reads, layout_reads_text, writers, writers_flow


C, LY, L, LT, W, F = _tools()
CTX = C.Context(ROOT)
PROGRAM = F.Program.of({n: (s.tree, s.is_package) for n, s in CTX.sources().items() if s.tree is not None})
TOP = frozenset(W.TOP_LEVEL)
BUILT = LY.build(CTX)
RECORDS = {r.key: r for r in BUILT.records}


def concrete(prefix: str) -> str:
    """A path a computed segment could be, for asking git or the filesystem about it."""
    return prefix.replace("{}", "x")


# ----------------------------------------------------------------------------------------- the two readers agree

def test_the_two_readers_find_the_same_read_primitive_calls_in_every_module():
    """Per module and per primitive, not destinations: the AST reading identifies a call by where its callee was
    imported from and the token reading by its spelling, so a tree that called a primitive through an import alias
    would show here (the planted alias is the AST's alone, in the unit module)."""
    ast_counts = L.read_counts(PROGRAM)
    disagree = {}
    for name, src in CTX.sources().items():
        if dict(ast_counts[name]) != dict(LT.sites(src.text)):
            disagree[name] = (dict(ast_counts[name]), dict(LT.sites(src.text)))
    assert disagree == {}
    assert sum(sum(c.values()) for c in ast_counts.values()) > 250, "the readings found almost nothing"


def test_no_module_reads_at_import_time_so_every_read_has_a_function_to_anchor_to():
    for name, mod in PROGRAM.modules.items():
        assert [c for c in mod.module_calls if L.read_of(mod, c, None) is not None] == [], name


# ------------------------------------------------------------------------------------------------- the entries

def test_the_entries_are_the_declared_top_level_and_every_directory_above_a_path_the_writers_and_readers_place():
    analysis = W.analyse(PROGRAM, TOP)
    reads = L.place(L.read_sites(PROGRAM, F.Evaluator(PROGRAM)), TOP).reads
    templates = set(analysis.writers) | set(reads)
    above = {"/".join(t.split("/")[:i]) for t in templates for i in range(1, len(t.split("/")))}
    assert set(RECORDS) == TOP | above
    assert len(RECORDS) > 40


def test_every_record_is_anchored_in_a_module_of_the_tree_and_the_family_breaks_none_of_its_own_rules():
    modules = set(CTX.sources())
    assert {r.module for r in RECORDS.values()} <= modules
    assert LY.problems({r.id: r.as_json() for r in BUILT.records}) == []


def test_the_gitignore_the_flags_are_derived_from_is_the_one_the_reading_understands_line_for_line():
    """A line added to `AEW_GITIGNORE` that is not a plain path is refused by the family; one that is, is a decision
    this test records."""
    assert LY.ignored_prefixes(AEW_GITIGNORE) == ["local", "state/txn"]


# ------------------------------------------------------------------------ the flags, against what they describe

@pytest.fixture(scope="module")
def project(tmp_path_factory):
    repo = make_git_repo(tmp_path_factory.mktemp("layout") / "repo", {"README.md": "# layout\n"})
    engine = Engine.initialize(repo, project_id="layout")
    return repo, engine


def test_git_ignores_exactly_the_entries_the_records_call_git_ignored(project):
    """A second derivation of the flag: git's own reading of the `.gitignore` the engine wrote."""
    repo, _ = project
    asked = {}
    for prefix in RECORDS:
        done = subprocess.run(["git", "check-ignore", "--no-index", "-q", f".aew/{concrete(prefix)}/leaf"], cwd=repo,
                              capture_output=True, **NO_WINDOW)
        assert done.returncode in (0, 1), (prefix, done.stderr)
        asked[prefix] = done.returncode == 0
    assert asked == {prefix: record.fact["git_ignored"] for prefix, record in RECORDS.items()}
    assert any(asked.values()) and not all(asked.values())


def test_the_store_the_records_name_is_the_directory_the_engine_keeps_its_store_in(project):
    _, engine = project
    kept = engine.store.store_dir.relative_to(Path(engine.aew_root).resolve()).as_posix()
    assert [k for k, r in RECORDS.items() if r.fact["store"] and "/" not in k] == [kept]
    assert all(r.fact["store"] == (k == kept or k.startswith(kept + "/")) for k, r in RECORDS.items())


def test_the_containment_layouts_own_spelling_of_the_store_is_the_store_the_records_name():
    """The layout restates the store's place (`STORE`, to refuse a bind that reaches it) and nothing pinned it to the
    engine's: a store moved in `STORE_REL` alone would leave the layout guarding the old directory."""
    assert containment.STORE == (".aew", STORE_REL)
    assert RECORDS[STORE_REL].fact["store"]


def test_the_entries_the_records_call_masked_are_the_paths_the_containment_layout_masks(tmp_path, monkeypatch):
    """A second derivation of the flag: the layout a run gets, made for a project that has an `.aew`, with the run's
    own directory inside it (as the harness makes it: review of the layout pull request, N-1). The mask is the fact the
    records hold; the run's own directories are bound back into it, which the page states and this pins: every
    writable bind under `.aew` lies inside a masked entry, so the exception is a run-owned directory in a mask and no
    entry the records leave unmasked."""
    monkeypatch.setattr(containment, "find_bwrap", lambda: "/usr/bin/bwrap")
    repo = make_git_repo(tmp_path / "repo")
    git("worktree", "add", "-q", "-b", "w", str(tmp_path / "ws"), cwd=repo)
    run = repo / ".aew" / "local" / "harness" / "runs" / "R-1-1"
    (repo / ".aew" / "state").mkdir(parents=True)
    run.mkdir(parents=True)
    layout = containment.for_run(role="reviewer", scope="ticket", workspace=str(tmp_path / "ws"), run_dir=run,
                                 scratch=str(run / "scratch"), bridge_dir=None, policy=None,
                                 home=str(tmp_path / "home"), project=str(repo), env={})
    masked = [Path(p) for p in layout.hide_runs]
    assert masked, "the layout masks nothing"
    aew = Path(os.path.realpath(repo / ".aew"))

    def under(path: Path, roots: list[Path]) -> bool:
        return any(path == h or h in path.parents for h in roots)

    assert {k: under(aew / concrete(k), masked) for k in RECORDS} == {
        k: r.fact["masked_by_containment"] for k, r in RECORDS.items()}
    bound_back = [Path(p) for p in layout.writable if aew in Path(p).parents]
    assert bound_back, "a run's own directories are bound back into the mask: this layout has them"
    assert all(under(p, masked) for p in bound_back), sorted(map(str, bound_back))


# -------------------------------------------------------------------------------------- a hand reading

KNOWN_READERS = {
    ("project.yaml", "aew.knowledge.manifest", "load_manifest"),
    ("history", "aew.history.store", "History._read"),
    ("policy", "aew.policy.execution", "load"),
    ("state/log", "aew.engine.outbox", "load_segment"),
    ("local/steering", "aew.engine.steering", "loop_state"),
    ("records/dispositions", "aew.engine.disposition_ops", "Dispositions.read"),
    ("pricing", "aew.engine.usage_ops", "read_pricing_snapshot"),
    ("local/lead", "aew.harness.broker_liveness", "read"),
    ("local/dashboard", "aew.dashboard.service", "locate"),
}
KNOWN_WRITERS = {
    ("local/notify", "aew.harness.notify", "Watcher._write_state"),
    ("history", "aew.history.store", "History.append"),
    ("state/handoffs", "aew.engine.lead_ops", "Lead.write_handoff"),
}


def test_the_reading_agrees_with_a_hand_reading_of_the_readers_and_writers_that_matter():
    readers = {(k, i["module"], i["symbol"]) for k, r in RECORDS.items() for i in r.fact["readers"]}
    writers = {(k, i["module"], i["symbol"]) for k, r in RECORDS.items() for i in r.fact["writers"]}
    assert KNOWN_READERS <= readers, sorted(KNOWN_READERS - readers)
    assert KNOWN_WRITERS <= writers, sorted(KNOWN_WRITERS - writers)


def test_every_constant_that_names_an_entry_holds_that_entry_when_it_is_imported():
    """Review of #261, N-11: `named_by` is found by `ast`; the second derivation imports each constant."""
    seen = 0
    for prefix, record in RECORDS.items():
        for named in record.fact["named_by"]:
            value = getattr(importlib.import_module(named["module"]), named["symbol"])
            assert str(value).replace("\\", "/") == prefix, (prefix, named)
            seen += 1
    assert seen >= 15


def test_an_entry_the_writers_family_has_as_a_constant_is_named_by_it_here_too():
    assert {"module": "aew.history.manifest", "symbol": "HISTORY_DIR"} in RECORDS["history"].fact["named_by"]
    assert RECORDS["history"].module == "aew.history.manifest" and RECORDS["history"].symbol == "HISTORY_DIR"


def test_the_page_links_the_writers_page_it_takes_its_writers_from():
    """That the file exists is `test_docs_links`'s: it checks every relative link of `docs/`."""
    assert "(writers.md)" in BUILT.pages["layout.md"]


# ------------------------------------------------------------------------------------------------ a planted reader

PLANT = ("from pathlib import Path\n\n\n"
         "def planted(aew_root):\n"
         "    return (aew_root / 'state' / 'planted.yaml').read_text()\n\n\n"
         "def planted_new(aew_root):\n"
         "    return (aew_root / 'brand-new-dir' / 'x').read_text()\n")


def planted_copy(tmp_path: Path, extra: str) -> Path:
    shutil.copytree(ROOT / "src" / "aew", tmp_path / "src" / "aew", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "src" / "aew" / "planted.py").write_text(extra, encoding="utf-8")
    return tmp_path


def test_a_reader_planted_in_a_copy_of_the_tree_is_a_reader_and_one_under_a_new_directory_is_unplaced(tmp_path):
    ctx = C.Context(planted_copy(tmp_path, PLANT))
    program = F.Program.of({n: (s.tree, s.is_package) for n, s in ctx.sources().items() if s.tree is not None})
    placed = L.place(L.read_sites(program, F.Evaluator(program)), TOP)
    assert ("aew.planted", "planted") in placed.reads["state/planted.yaml"]
    assert ("aew.planted", "planted_new", "Path.read_text") in placed.unplaced
    assert "brand-new-dir/x" not in placed.reads
    assert placed.placed_sites + placed.outside_sites + placed.unplaced_sites == placed.sites


def test_a_read_at_import_time_planted_in_a_copy_of_the_tree_is_refused(tmp_path):
    ctx = C.Context(planted_copy(tmp_path, "from pathlib import Path\n\nTEXT = Path('x').read_text()\n"))
    program = F.Program.of({n: (s.tree, s.is_package) for n, s in ctx.sources().items() if s.tree is not None})
    with pytest.raises(C.ReferenceError, match=r"aew\.planted reads at import time"):
        L.read_sites(program, F.Evaluator(program))
