"""The writers family of the generated reference (STG-12 S12-2, DOC-01), on the tree: what holds for ``src/aew``.

* the two readers of write primitives (``ast`` in ``writers.py``, tokens in ``writers_text.py``, sharing no code) find
  the same calls in every module;
* the declared set of entries directly under ``.aew`` is the first entry of every write the reading places, and every
  entry of it is the first entry of one (both ways), so a new directory under ``.aew`` is a decision;
* the conventions the reading relies on hold: a name spelled ``aew_root`` is the ``.aew`` directory (every assignment
  of one is a form pinned here), and the write mechanism it excludes (``aew.util``, the store's ``write_file``) is
  still the mechanism;
* the entry points' roots are the owner's table, and every writer names entry points and kinds that are the table's;
* a spot check that the reading agrees with a hand reading of the code for writers whose paths matter;
* a writer planted in a copy of the tree is a record, and one under an unknown directory is an unresolved write.

The planted cases of each rule, with their right, wrong and missing cases, are in
``tests/unit/test_reference_writers_flow.py``. The heavy lanes run this because it reads ``src`` only.
"""

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

from aew import process_kind

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, writers, writers_flow, writers_reach, writers_text
    finally:
        sys.path.remove(here)
    return common, writers, writers_flow, writers_reach, writers_text


C, W, F, R, T = _tools()
TABLE = {key: kind for key, (kind, _why) in process_kind.ENTRY_POINTS.items()}
CTX = C.Context(ROOT)


def program(ctx=CTX):
    return F.Program.of({n: (s.tree, s.is_package) for n, s in ctx.sources().items() if s.tree is not None})


PROGRAM = program()
ANALYSIS = W.analyse(PROGRAM, frozenset(W.TOP_LEVEL), R.roots_of(CTX, set(TABLE)), TABLE, R.dispatchers_of(CTX))


# ----------------------------------------------------------------------------------------- the two readers agree

def test_the_two_readers_find_the_same_write_primitive_calls_in_every_module():
    """Per module and per primitive, not destinations: the AST reading identifies a call by where its callee was
    imported from and the token reading by its spelling, so a tree that called a primitive through an import alias
    would show here (the planted alias is the AST's alone, in the unit module)."""
    ast_counts = W.primitive_counts(PROGRAM)
    disagree = {}
    for name, src in CTX.sources().items():
        if dict(ast_counts[name]) != dict(T.sites(src.text)):
            disagree[name] = (dict(ast_counts[name]), dict(T.sites(src.text)))
    assert disagree == {}
    assert sum(sum(c.values()) for c in ast_counts.values()) > 150, "the readings found almost nothing"


# --------------------------------------------------------------------------------------------- the declared set

def test_the_declared_top_level_set_is_the_first_entry_of_the_writes_the_reading_places_and_nothing_more():
    derived = W.derived_top_level(ANALYSIS.sites)
    assert set(W.TOP_LEVEL) == derived, (
        f"declare {sorted(derived - set(W.TOP_LEVEL))}, or drop {sorted(set(W.TOP_LEVEL) - derived)}, in TOP_LEVEL")
    assert list(W.TOP_LEVEL) == sorted(W.TOP_LEVEL)


def test_the_declared_entries_include_everything_the_project_manifest_names_under_aew():
    """The manifest is the nearest thing the code has to an owner of the directory names: what its default names under
    `.aew` must be declared here."""
    from aew.knowledge.manifest import default_manifest

    manifest = default_manifest("p", "p", "main", "../w")
    named = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, str) and node not in ("..", "base", "git", "p", "main", "../w", "aew/project/v1"):
            first = node.split("/")[0]
            if first in ("knowledge", "state", "work", "evidence", "decisions", "policy", "roles"):
                named.add(first)
    walk(manifest)
    assert named and named <= set(W.TOP_LEVEL)


# ------------------------------------------------------------------------------------------------- the conventions

AEW_ROOT_FORMS = {
    ("aew.cli.main", "(_, aew_root)", "Kernel.locate("),
    ("aew.cli.main", "(repo_root, aew_root)", "Kernel.locate("),
    ("aew.dashboard.reader", "self.aew_root", "aew_root"),
    ("aew.engine.api", "aew_root", "repo_root / AEW_DIR"),
    ("aew.engine.base", "self.aew_root", "aew_root.resolve()"),
    ("aew.engine.recall", "self.aew_root", "aew_root"),
    ("aew.engine.usage_ops", "(self.aew_root, self.pricing)", "(aew_root, pricing)"),
    ("aew.engine.usage_ops", "self.aew_root", "aew_root"),
    ("aew.harness.broker_liveness", "self.aew_root", "Path(aew_root)"),
    ("aew.harness.event_spool", "self.aew_root", "Path(aew_root)"),
    ("aew.harness.notify", "self.aew_root", "Path(aew_root)"),
    ("aew.harness.runlog", "aew_root", "directory.parents[len(Path(RUNS_REL).parts)]"),
    ("aew.harness.steering_loop", "self.aew_root", "Path(engine.aew_root)"),
    ("aew.harness.supervisor", "aew_root", "run_dir.parents[depth]"),
}


def assignments_to_aew_root() -> set[tuple[str, str, str]]:
    found = set()
    for name, src in CTX.sources().items():
        assert src.tree is not None
        for node in ast.walk(src.tree):
            if isinstance(node, ast.Assign):
                pairs = [(t, node.value) for t in node.targets]
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                pairs = [(node.target, node.value)]
            else:
                continue
            for target, value in pairs:
                names = target.elts if isinstance(target, ast.Tuple) else [target]
                if any((isinstance(n, ast.Name) and n.id == F.ROOT_NAME)
                       or (isinstance(n, ast.Attribute) and n.attr == F.ROOT_NAME) for n in names):
                    found.add((name, ast.unparse(target), ast.unparse(value)))
    return found


def test_a_name_spelled_aew_root_is_the_dot_aew_directory_by_forms_this_test_pins():
    """The reading takes a name or attribute `aew_root` to be the `.aew` directory (the repository's own spelling).
    It is one of five forms: a pass-through of a parameter of that name, the owner's `repo_root / AEW_DIR`, the tuple
    `Kernel.locate` returns, the engine's own, and (in the two harness run-directory readers) a parent of the run
    directory. A new assignment is a form to look at before it is a writer to trust."""
    found = assignments_to_aew_root()

    def pinned(form, seen):
        return form[0] == seen[0] and form[1] == seen[1] and seen[2].startswith(form[2])

    assert {s for s in found if not any(pinned(f, s) for f in AEW_ROOT_FORMS)} == set(), "a form to look at"
    assert {f for f in AEW_ROOT_FORMS if not any(pinned(f, s) for s in found)} == set(), "a pinned form that is gone"


def test_the_write_mechanism_the_reading_excludes_is_still_the_mechanism():
    """`aew.util` and the store's `write_file` are excluded as writers because their callers are the writers: each must
    exist, and each must make the writes (else the exclusion hides nothing and should go)."""
    counts = W.primitive_counts(PROGRAM)
    for module in sorted(W.MECHANISM_MODULES):
        assert module in PROGRAM.modules and sum(counts[module].values()) > 0, module
    for module, qual in sorted(W.MECHANISM_FUNCTIONS):
        mod = PROGRAM.modules[module]
        func = mod.funcs[qual]
        # `write_file` picks its primitive in a conditional callee, which neither reader sees as a call: it names them
        names = {mod.aliases.resolve(n) for n in ast.walk(func.node) if isinstance(n, (ast.Name, ast.Attribute))}
        assert names & set(W.CALL_PRIMITIVES), (module, qual)


# --------------------------------------------------------------------------------------- the owner's table, both ways

def test_the_roots_the_reach_starts_from_are_the_owners_table_and_nothing_else():
    roots = R.roots_of(CTX, set(TABLE))
    assert {k for keys in roots.values() for k in keys} == set(TABLE)
    assert {r[0] for r in roots} == {"aew.cli.main", "aew.harness.supervisor", "aew.stg02.server"}


def test_every_writer_of_this_tree_names_entry_points_that_are_rows_of_the_table_and_their_kinds():
    records = W.records_of(ANALYSIS)
    assert W.record_problems({r.id: r.as_json() for r in records}, TABLE) == []
    named = {k for r in records for w in (r.fact or {}).get("writers", []) for k in w["entry_points"]}
    assert named and named <= set(TABLE)


# -------------------------------------------------------------- the reading against a hand reading of the code

KNOWN = {
    # (prefix, writer) read by hand from the code
    ("state/control.yaml", "aew.engine.store", "ControlStore._commit_unprofiled"),
    ("local/wake", "aew.engine.outbox", "bump_wake"),
    ("work/{}/completion.md", "aew.engine.integration_ops", "Integration._finish_publish"),
    ("work/{}/completion.md", "aew.engine.nonmutating_ops", "NonMutating.work_accept"),
    ("local/lead/broker.json", "aew.harness.broker_liveness", "write"),
    ("local/notify/state.json", "aew.harness.notify", "Watcher._write_state"),
    ("state/handoffs/H-{}.md", "aew.engine.lead_ops", "Lead.write_handoff"),
    ("knowledge/PROJECT.md", "aew.engine.store", "ControlStore.create"),
    ("local/control.lock", "aew.engine.lock", "FileLock._open"),
}


def test_the_reading_agrees_with_a_hand_reading_of_the_writers_whose_paths_matter():
    found = {(t, w.module, w.symbol) for t, ws in ANALYSIS.writers.items() for w in ws}
    assert KNOWN <= found, sorted(KNOWN - found)


def test_the_store_transaction_writers_are_exactly_the_session_write_sites():
    stage = {(s.module, s.symbol) for s in ANALYSIS.sites if s.primitive == "session.write"}
    placed = {(w.module, w.symbol) for ws in ANALYSIS.writers.values() for w in ws
              if w.mechanism == W.STORE_TRANSACTION}
    unplaced = {(m, s) for (m, s, p) in ANALYSIS.unresolved if p == "session.write"}
    assert placed | unplaced == stage and stage


# ------------------------------------------------------------------------------------------------ a planted writer

PLANT = ("from aew.util import atomic_write\n\n\ndef planted(aew_root):\n"
         "    atomic_write(aew_root / 'state' / 'planted.yaml', 'x')\n"
         "    (aew_root / 'brand-new-dir' / 'x').write_text('x')\n")


def test_a_writer_planted_in_a_copy_of_the_tree_is_a_record_and_one_under_a_new_directory_is_unresolved(tmp_path):
    shutil.copytree(ROOT / "src" / "aew", tmp_path / "src" / "aew", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "src" / "aew" / "planted.py").write_text(PLANT, encoding="utf-8")
    ctx = C.Context(tmp_path)
    analysis = W.analyse(program(ctx), frozenset(W.TOP_LEVEL), {}, TABLE, set())
    assert [(w.module, w.symbol) for w in analysis.writers["state/planted.yaml"]] == [("aew.planted", "planted")]
    assert any("`brand-new-dir`" in why and "not in the declared set" in why
               for (m, s, _p), (_mech, why) in analysis.unresolved.items() if (m, s) == ("aew.planted", "planted"))
    assert "brand-new-dir/x" not in analysis.writers
