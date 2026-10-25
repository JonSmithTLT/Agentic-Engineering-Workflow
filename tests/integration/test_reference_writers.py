"""The writers family of the generated reference (STG-12 S12-2, DOC-01), on the tree: what holds for ``src/aew``.

* the two readers of write primitives (``ast`` in ``writers.py``, tokens in ``writers_text.py``, sharing no code) find
  the same calls in every module;
* the declared set of entries directly under ``.aew`` is the first entry of every write the reading places, and every
  entry of it is the first entry of one (both ways), so a new directory under ``.aew`` is a decision;
* the conventions the reading relies on hold: a name spelled ``aew_root`` is the ``.aew`` directory (every assignment
  of one is a form pinned here), and the write mechanism it excludes (``aew.util``, the store's ``write_file``) is
  still the mechanism;
* the entry points' roots are the owner's table, and every writer names entry points and kinds that are the table's;
* the CLI's roles are cut by the parser, and the cut equals the real parser's own command-to-handler map, command for
  command; no store write is reached from a role that may not write the store; the gate the records name exists;
* a spot check that the reading agrees with a hand reading of the code for writers whose paths matter;
* a writer planted in a copy of the tree is a record, and one under an unknown directory is an unresolved write.

The planted cases of each rule, with their right, wrong and missing cases, are in
``tests/unit/test_reference_writers_flow.py``. The heavy lanes run this because it reads ``src`` only.
"""

from __future__ import annotations

import argparse
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
        from reference_families import common, writers, writers_flow, writers_reach, writers_roles, writers_text
    finally:
        sys.path.remove(here)
    return common, writers, writers_flow, writers_reach, writers_roles, writers_text


C, W, F, R, K, T = _tools()
TABLE = {key: kind for key, (kind, _why) in process_kind.ENTRY_POINTS.items()}
CTX = C.Context(ROOT)


def program(ctx=CTX):
    return F.Program.of({n: (s.tree, s.is_package) for n, s in ctx.sources().items() if s.tree is not None})


PROGRAM = program()
ANALYSIS = W.analyse(PROGRAM, frozenset(W.TOP_LEVEL), R.roots_of(CTX, set(TABLE)), TABLE, R.cli_of(CTX, PROGRAM))


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
    """`aew.util`, the store's `write_file` and its apply step are excluded as writers because they write for others:
    each must exist, and each must make the writes (else the exclusion hides nothing and should go)."""
    counts = W.primitive_counts(PROGRAM)
    for module in sorted(W.MECHANISM_MODULES):
        assert module in PROGRAM.modules and sum(counts[module].values()) > 0, module
    for module, qual in sorted(W.MECHANISM_FUNCTIONS):
        mod = PROGRAM.modules[module]
        func = mod.funcs[qual]
        # `write_file` picks its primitive in a conditional callee, which neither reader sees as a call: it names them
        names = {mod.aliases.resolve(n) for n in ast.walk(func.node) if isinstance(n, (ast.Name, ast.Attribute))}
        names |= {f"{module}.{n}" for n in names if n in mod.funcs}  # a function of the module, called by its bare name
        assert names & set(W.CALL_PRIMITIVES), (module, qual)


def test_the_store_stages_a_file_in_two_places_and_the_page_says_the_one_that_is_no_session_write():
    """Review of the placement pull request, F1: the apply step is not a writer because the staging sites are, and that
    holds for every path but the events sidecar `_commit_unprofiled` stages itself. If a third place stages a file, or
    the sidecar gets a writer, the claim on the page is out of date and this fails."""

    class Stagers(C.Scoped):
        def __init__(self) -> None:
            super().__init__()
            self.where: list[str] = []

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Name) and node.func.id == "PendingWrite":
                self.where.append(self.symbol or "")
            self.generic_visit(node)

    visitor = Stagers()
    visitor.visit(PROGRAM.modules[W.STORE].tree)
    assert sorted(visitor.where) == ["ControlStore._commit_unprofiled", "Session.write"]
    sidecar = [w for w in ANALYSIS.writers.get("state/log/{}.events.yaml", [])]
    assert sidecar and all(w.module != W.STORE for w in sidecar), "the page says nothing here names what creates it"
    page = W.build(CTX).pages["writers.md"]
    assert "the events sidecar `state/log/{}.events.yaml`" in page and "has no staging site among the writers" in page


# --------------------------------------------------------------------------------------- the owner's table, both ways

def test_the_roots_the_reach_starts_from_are_the_owners_table_and_nothing_else():
    roots = R.roots_of(CTX, set(TABLE))
    assert {k for keys in roots.values() for k in keys} == set(TABLE)
    assert {r[0] for r in roots} == {"aew.cli.main", "aew.harness.supervisor", "aew.stg02.server"}


def test_every_writer_of_this_tree_names_entry_points_that_are_rows_of_the_table_and_their_kinds():
    records = W.records_of(ANALYSIS)
    assert W.record_problems({r.id: r.as_json() for r in records}, TABLE, ANALYSIS.roles, ANALYSIS.undecided) == []
    named = {k for r in records for w in (r.fact or {}).get("writers", []) for k in w["entry_points"]}
    assert named and named <= set(TABLE)


# ------------------------------------------------------------------------------------------------- the CLI cut per role

def runtime_commands() -> dict[tuple[str, ...], tuple[str, str]]:
    """The real parser's own map: each command path that has a handler, with the function it names (a lambda by the
    function that builds it), walked from ``build_parser`` with every optional command on."""
    from aew.cli import main

    found: dict[tuple[str, ...], tuple[str, str]] = {}

    def walk(parser: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        handler = parser.get_default("handler")
        if handler is not None:
            qual = handler.__qualname__.replace(".<locals>.<lambda>", "").replace(".<locals>", "")
            found[path] = (handler.__module__, qual)
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, (*path, name))

    walk(main.build_parser(recall_search=True, coordination_reads=True), ())
    return found


def function_of(handler: tuple[str, str]) -> tuple[str, str]:
    """A static handler key as the runtime names it: a lambda handler by the function that builds it."""
    return handler[0], handler[1].split(".<handler")[0]


def static_commands() -> dict[tuple[str, ...], set[tuple[str, str]]]:
    out: dict[tuple[str, ...], set[tuple[str, str]]] = {}
    for r in ANALYSIS.cut.registrations:
        for path in r.paths:
            out.setdefault(path, set()).update(function_of(h) for h in r.handlers)
    return out


def test_the_cut_is_the_real_parsers_own_map_command_for_command():
    """The static reading of `set_defaults(handler=...)` and the parser the CLI builds give the same handler for every
    command path (two derivations: one reads the source, the other runs `build_parser`)."""
    runtime = runtime_commands()
    static = static_commands()
    assert set(runtime) == set(static), (sorted(set(runtime) - set(static)), sorted(set(static) - set(runtime)))
    assert {path: handler for path, handler in runtime.items() if handler not in static[path]} == {}
    assert len(runtime) > 100, "the parser walk found almost nothing"


def test_every_registration_of_this_tree_names_a_handler():
    assert all(r.handlers for r in ANALYSIS.cut.registrations) and len(ANALYSIS.cut.registrations) > 100


def test_each_named_role_gets_the_handlers_of_the_commands_the_owner_gives_it_and_the_worker_role_none():
    """The roles' keys come from `process_kind.cli_entry_point` (asked, not listed): the handlers of the commands whose
    role it names are that role's, and the role the environment selects is no command's."""
    roles = ANALYSIS.roles
    expected: dict[str, set[tuple[str, str]]] = {}
    for path, handler in runtime_commands().items():
        expected.setdefault(process_kind.cli_entry_point(list(path), {}), set()).add(handler)
    got = {role: {function_of(h) for h in handlers} for role, handlers in ANALYSIS.cut.handlers.items()}
    assert got == expected
    assert roles.worker not in got and roles.general in got
    assert roles.named and roles.all == {k for k in TABLE if "." not in k}
    assert process_kind.cli_entry_point(["status"], {process_kind.AGENT_ENDPOINT_ENV: "x"}) == roles.worker


def test_the_cli_is_the_one_function_that_declares_the_roles_and_their_reach_starts_there():
    roots = R.roots_of(CTX, set(TABLE))
    assert R.cli_roots_of(CTX) == {("aew.cli.main", "_main")}
    assert roots[("aew.cli.main", "_main")] == set(ANALYSIS.roles.all)


def test_no_store_write_is_reached_from_a_role_that_may_not_write_the_store():
    """DOC-01's finding, as a check: a store-transaction writer, or a direct writer outside `local/`, that a
    `non_writer` entry point reaches. The page lists what is found; this is the guarantee it reports."""
    store, local = W.role_reach(ANALYSIS, W.records_of(ANALYSIS))
    non_writers = [k for k, kind in TABLE.items() if kind == W.NON_WRITER]
    assert non_writers and {k: sorted(store[k]) for k in non_writers} == {k: [] for k in non_writers}
    assert not store[ANALYSIS.roles.worker] and not local[ANALYSIS.roles.worker], "nothing reaches the worker role"


def test_the_with_limit_the_page_names_is_still_the_live_case():
    """The page says the dashboard server's lock file is attributed to `aew` alone because a `with` is not
    followed. This holds that true: the function takes the lock by `with`, and the records do not list the dashboard
    role. When the reach follows `with`, this fails: update the page text and `WITH_CASE` (or drop the limit)."""
    module, qual, keys = W.WITH_CASE
    func = PROGRAM.modules[module].funcs[qual]
    assert any(isinstance(n, ast.With) for n in ast.walk(func.node))
    records = {r.key: r for r in W.records_of(ANALYSIS)}
    dashboard = process_kind.cli_entry_point(["dashboard", "serve"], {})
    for key in keys:
        reached = {k for w in (records[key].fact or {})["writers"] for k in w["entry_points"]}
        assert dashboard not in reached and reached == {ANALYSIS.roles.general}, (key, reached)


def test_the_directory_the_finding_treats_as_local_is_one_the_project_keeps_out_of_git():
    """Review of #258, N1: `LOCAL` is declared in the generator; the fact (rebuildable data, git-ignored) is owned by
    `AEW_GITIGNORE`, and this holds the two together."""
    from aew.engine.api import AEW_GITIGNORE

    assert f"{W.LOCAL}/" in AEW_GITIGNORE.splitlines()


def test_the_gate_the_records_name_exists_is_called_by_the_control_lock_and_is_tested_at_run_time():
    module, symbol = W.GATE_SYMBOL
    assert symbol in PROGRAM.modules[module].funcs
    lock = PROGRAM.modules["aew.engine.store"].funcs["ControlStore.control_lock"]
    assert any(PROGRAM.modules["aew.engine.store"].aliases.resolve(c.func) == f"{module}.{symbol}" for c in lock.calls)
    tests = ast.parse((ROOT / "tests" / "integration" / "test_non_writer_reads.py").read_text(encoding="utf-8"))
    assert W.GATE_TEST in {n.name for n in ast.walk(tests) if isinstance(n, ast.FunctionDef)}


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
    # placed by the command-line, destructuring and returned-dict rules (the placement pull request)
    ("local/harness/runs/{}/run.json", "aew.harness.runlog", "write_record"),
    ("local/harness/runs/{}/heartbeat", "aew.harness.runlog", "beat"),
    ("work/{}/plan-v{}.md", "aew.engine.work_ops", "WorkUnits.propose"),
    ("history/audits/{}.yaml", "aew.history.store", "History.write_record"),
}


def test_the_reading_agrees_with_a_hand_reading_of_the_writers_whose_paths_matter():
    found = {(t, w.module, w.symbol) for t, ws in ANALYSIS.writers.items() for w in ws}
    assert KNOWN <= found, sorted(KNOWN - found)


def test_the_sites_the_page_lists_as_outside_aew_are_the_outside_records():
    """Each site that the reading follows to a place outside `.aew` is a record (and the page lists the same sites)."""
    records = {r.key for r in W.records_of(ANALYSIS) if r.key.startswith(f"{W.OUTSIDE_KEY}:")}
    listed = {f"{W.OUTSIDE_KEY}:{m}:{s}:{p}" for sites in ANALYSIS.outside.values() for m, s, p in sites}
    assert records == listed and records
    page = W.page(ANALYSIS, W.records_of(ANALYSIS), W.TOP_LEVEL)
    assert all(f"`{m}:{s}` ({p})" in page for sites in ANALYSIS.outside.values() for m, s, p in sites)


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
    analysis = W.analyse(program(ctx), frozenset(W.TOP_LEVEL), {}, TABLE)
    assert [(w.module, w.symbol) for w in analysis.writers["state/planted.yaml"]] == [("aew.planted", "planted")]
    assert any("`brand-new-dir`" in why and "not in the declared set" in why
               for (m, s, _p), (_mech, why) in analysis.unresolved.items() if (m, s) == ("aew.planted", "planted"))
    assert "brand-new-dir/x" not in analysis.writers


# ------------------------------------------------------------------------------------------------------------ the caps

# The constants to double: derived from `caps()`, the one list, so a cap that is listed cannot escape the hold
# (review of the placement pull request, F3).
def cap_constants() -> tuple[tuple[object, str], ...]:
    return tuple(({"writers_flow": F, "writers_roles": K}[cap.name.split(".")[0]], cap.name.split(".")[1])
                 for cap in (*F.caps(), *K.caps()))


CAPS = cap_constants()


def without_the_caps_section(page: str) -> str:
    start = page.index("## Caps of the reading")
    return page[:start] + page[page.index("\n## ", start):]


def test_doubling_every_cap_changes_no_record_and_nothing_on_the_page_but_the_caps_own_section(monkeypatch):
    """The designer's proof that a cap loses nothing silently, as a test: if any record of this tree depended on a cap,
    raising it would change the records. (At the caps the committed reference is what the code gives; doubled, it is the
    same.) A change that makes a cap bind fails here, naming nothing quietly lost, and is a decision."""
    base = W.build(CTX)
    for module, name in CAPS:
        monkeypatch.setattr(module, name, getattr(module, name) * 2)
    doubled = W.build(CTX)
    assert {r.id: r.as_json() for r in doubled.records} == {r.id: r.as_json() for r in base.records}
    assert (without_the_caps_section(doubled.pages["writers.md"])
            == without_the_caps_section(base.pages["writers.md"]))
    assert doubled.pages["writers.md"] != base.pages["writers.md"], "the caps' own section prints the doubled values"


def test_halving_the_depth_cap_changes_no_record_so_it_is_at_least_twice_what_the_tree_needs(monkeypatch):
    base = {r.id: r.as_json() for r in W.build(CTX).records}
    monkeypatch.setattr(F, "DEPTH", F.DEPTH // 2)
    halved = {r.id: r.as_json() for r in W.build(CTX).records}
    assert halved == base, f"a chain needs more than {F.DEPTH} calls or parameters: raise the cap, and say why"


def test_a_cap_listed_later_is_doubled_too(monkeypatch):
    """Review of the placement pull request, F3 (its planted `NEWCAP_DEPTH`): the list the hold doubles is `caps()`'s,
    read when the test runs, so a cap added to either list is held without a second edit."""
    real = K.caps()
    extra = F.Cap("writers_roles.NEWCAP_DEPTH", 5, "a planted cap", "chosen", "nothing")
    monkeypatch.setattr(K, "caps", lambda: (*real, extra))
    assert (K, "NEWCAP_DEPTH") in cap_constants() and len(cap_constants()) == len(CAPS) + 1


def test_every_cap_the_caps_derive_is_a_constant_of_its_module():
    assert len(CAPS) == len({(m.__name__, name) for m, name in CAPS}) == len([*F.caps(), *K.caps()])
    assert all(isinstance(getattr(module, name), int) for module, name in CAPS)


def test_every_measured_cap_is_at_least_twice_the_largest_figure_the_tree_reaches():
    """VALUES, FSTRING_LIMIT, MRO_DEPTH and ASSIGNMENT_DEPTH are measured, not chosen (the page prints the figure): a
    tree that grows toward one fails here, before the cap binds, and the cap is raised on purpose."""
    with F.measuring() as peaks:
        W.build(CTX)
    measured = [cap for cap in F.caps(peaks) if cap.measured is not None]
    assert len(measured) == len(F.MEASURED) and peaks["values"] > 0
    for cap in measured:
        assert cap.value >= 2 * (cap.measured or 0), (
            f"the tree reaches {cap.measured} and the cap `{cap.name}` is {cap.value}: raise the cap, and say why")


def test_the_caps_section_of_the_page_is_what_the_caps_say():
    section = without_the_caps_section(W.build(CTX).pages["writers.md"])
    assert section and "## Caps of the reading" not in section
    page = W.build(CTX).pages["writers.md"]
    assert all(f"`{cap.name}` = {cap.value}:" in page for cap in (*F.caps(), *K.caps()))
