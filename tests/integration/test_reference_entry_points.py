"""The entry-points family of the generated reference (STG-12 S12-2, DOC-02): what stops code bypassing
``aew.process_kind.ENTRY_POINTS`` (D-CS1-12), read from the source by two independently written detectors.

* every ``python -m aew...`` spawn site in the product names a listed entry point;
* every row of the table declares itself at a site in the product, and every such site declares a row.

The first is the one the table test next door (``test_non_writer_reads.py``) did not have: it compared the table with
the modules that *run* as a process, not with the places that *start* one. The detectors are ``entry_points.py``
(``ast``, identifying a call by where its callee was imported from) and ``entry_points_text.py`` (``re``, sharing no
code). They agree on the tree and on every planted case; what both miss is pinned below, one probe per item.

The heavy lanes run this because it reads ``src`` only: a pull request that adds a spawn site changes ``src`` and so
runs the full gate.
"""

from __future__ import annotations

import ast
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from aew import process_kind

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, entry_points, entry_points_text, modules
    finally:
        sys.path.remove(here)
    return common, entry_points, entry_points_text, modules


C, E, T, M = _tool_modules()
TABLE = dict(process_kind.ENTRY_POINTS)
CTX = C.Context(ROOT)


def tree_sites(ctx=CTX):
    spawns, declares = [], []
    for name, src in ctx.sources().items():
        assert src.tree is not None, f"{name} does not parse"
        spawns += E.spawn_sites(src.tree, name, src.is_package)
        declares += E.declare_sites(src.tree, name, src.is_package)
    return spawns, declares


def unresolved_items(built) -> list[dict]:
    """Every unresolved item of the built records: their own and those of their list facts (``fact_coverage``)."""
    return [i for r in built.records for i in C.unresolved_items(r.as_json())]


def spawn_problems(sites) -> list[str]:
    """The D-CS1-12 check: every ``python -m aew...`` site names a listed entry point, and its name is readable."""
    return [f"{s.module}:{s.symbol} " + ("starts a module whose name is not a plain string" if s.target is None
                                         else f"starts {s.target}, which is not a listed entry point")
            for s in sites if s.target is None or E.entry_for(s.target) not in TABLE]


def declaration_problems(declares, roles) -> list[str]:
    literal = [d for d in declares if d.via == "literal"]
    problems = [f"{d.module}:{d.symbol} declares an entry point this reading cannot read" for d in declares
                if d.via == "unreadable"]
    problems += [f"{d.module}:{d.symbol} declares {d.entry_point!r}, which is not in the table" for d in literal
                 if d.entry_point not in TABLE]
    problems += [f"{d.module}:{d.symbol} declares {d.entry_point!r}, a process that is another module's"
                 for d in literal if d.entry_point in TABLE and d.entry_point != d.module]
    declared = {d.entry_point for d in literal}
    problems += [f"{key} is in the table and declares itself nowhere" for key in sorted(set(TABLE) - roles - declared)]
    if roles != {k for k in TABLE if "." not in k}:
        problems.append("cli_entry_point's roles are not the table's rows that are not modules")
    if {d.module for d in declares if d.via == "cli_entry_point"} != {"aew.cli.main"}:
        problems.append("the CLI roles are not declared by aew.cli.main alone")
    return problems


def planted(source: str, module: str = "aew.planted"):
    tree = ast.parse(source)
    return E.spawn_sites(tree, module, False), E.declare_sites(tree, module, False)


# ------------------------------------------------------------------------------------------ the spawn-site test

def test_every_python_dash_m_aew_spawn_site_names_a_listed_entry_point():
    sites, _ = tree_sites()
    assert {(s.module, s.target) for s in sites} >= {("aew.engine.custody_ops", "aew"),
                                                     ("aew.engine.harness_ops", "aew.harness.supervisor")}
    assert spawn_problems(sites) == []


RIGHT = 'import sys\nargv = [sys.executable, "-I", "-m", "aew.harness.supervisor", "--run-dir", d]\n'
RIGHT_CLI = 'import sys\nargv = [sys.executable, "-m", "aew", "-C", root, "status"]\n'
WRONG = 'import sys\nargv = [sys.executable, "-I", "-m", "aew.unlisted", "--x"]\n'
WRONG_TUPLE = 'import sys\nargv = (sys.executable, "-m", "aew.also_unlisted")\n'
WRONG_CALL = 'import os, sys\nos.execl(sys.executable, sys.executable, "-m", "aew.unlisted")\n'  # review of #241, B9
NOT_A_SPAWN = [
    'argv = ["git", "log", "-m", "a message"]\n',                       # git's -m
    'argv = ["python", "-m", "pytest", "-q"]\n',                        # a module outside AEW
    '"""python -m aew.unlisted"""\n',                                   # prose
    'argv = ["aew", "-m", "x"]\n',                                      # -m of something else
    'git.git("commit", "-q", "-m", message, cwd=ws)\n',                 # git's -m as call arguments: not an argv
    'git.git("log", "--raw", "-z", "-m", "--no-renames")\n',
]


def test_a_planted_unlisted_spawn_site_fails_the_check_and_a_listed_or_absent_one_does_not():
    assert spawn_problems(planted(RIGHT)[0]) == [] and len(planted(RIGHT)[0]) == 1
    assert spawn_problems(planted(RIGHT_CLI)[0]) == [] and len(planted(RIGHT_CLI)[0]) == 1
    for source in (WRONG, WRONG_TUPLE, WRONG_CALL):
        assert len(spawn_problems(planted(source)[0])) == 1, source
    for source in NOT_A_SPAWN:
        assert planted(source)[0] == [], source


def test_a_spawn_site_added_to_a_copy_of_the_tree_fails_the_check_and_is_a_gap_in_the_reference(tmp_path):
    shutil.copytree(ROOT / "src" / "aew", tmp_path / "src" / "aew", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "src" / "aew" / "planted.py").write_text(WRONG, encoding="utf-8")
    ctx = C.Context(tmp_path)
    sites, _ = tree_sites(ctx)
    assert any("aew.unlisted" in p for p in spawn_problems(sites))
    unresolved = unresolved_items(E.build(ctx))
    assert [i for i in unresolved if "names no listed entry point" in i["why"] and i["module"] == "aew.planted"]


def test_the_reference_of_this_tree_has_no_defect_gap():
    """A gap that says the code and the table disagree is a finding, never a quiet line in gaps.md."""
    defects = ("names no listed entry point", "nothing declares itself", "cannot be read or is not in the table",
               "not a plain string")
    assert [i for i in unresolved_items(E.build(CTX)) if any(d in i["why"] for d in defects)] == []


# ------------------------------------------------------------------------------------------ the second detector

def test_the_two_spawn_detectors_agree_on_every_module_of_the_tree():
    for name, src in CTX.sources().items():
        assert src.tree is not None
        by_ast = sorted(s.target for s in E.spawn_sites(src.tree, name, src.is_package) if s.target is not None)
        assert by_ast == T.spawn_targets(src.text), name


@pytest.mark.parametrize("source", [RIGHT, RIGHT_CLI, WRONG, WRONG_TUPLE, WRONG_CALL, *NOT_A_SPAWN])
def test_the_two_spawn_detectors_agree_on_every_planted_case(source):
    sites, _ = planted(source)
    assert sorted(s.target for s in sites if s.target is not None) == T.spawn_targets(source)


def test_the_declaration_detectors_agree_on_every_module_of_the_tree():
    """Every module, ``aew.process_kind`` included: it is not exempt (a literal planted there must be seen)."""
    for name, src in CTX.sources().items():
        assert src.tree is not None
        declares = E.declare_sites(src.tree, name, src.is_package)
        assert sorted(d.entry_point for d in declares if d.via == "literal") == T.declared(src.text), name
        assert any(d.via == "cli_entry_point" for d in declares) == T.declares_cli_roles(src.text), name


DECLARE_CASES = {
    "a literal through the module": ('from aew import process_kind\nprocess_kind.declare("aew.stg02.server")\n',
                                     ["aew.stg02.server"], 1),
    "scoped, through an alias": ('from aew import process_kind as pk\nwith pk.declared_as("aew.harness.supervisor"):\n'
                                 '    pass\n', ["aew.harness.supervisor"], 1),
    "imported by name": ('from aew.process_kind import declare\ndeclare("aew.stg02.server")\n',
                         ["aew.stg02.server"], 1),
    "the CLI's roles": ('from aew import process_kind\n'
                        'with process_kind.declared_as(process_kind.cli_entry_point(a, e)):\n    pass\n', [], 1),
    "no declaration": ('def declare(x):\n    return x\n', [], 0),
}


@pytest.mark.parametrize("case", sorted(DECLARE_CASES))
def test_the_declaration_detectors_agree_on_every_planted_case(case):
    source, literals, sites = DECLARE_CASES[case]
    _, declares = planted(source)
    assert len(declares) == sites
    assert sorted(d.entry_point for d in declares if d.via == "literal") == literals == T.declared(source)
    assert any(d.via == "cli_entry_point" for d in declares) == T.declares_cli_roles(source) == (
        case == "the CLI's roles")


# ------------------------------------------------------------------------------------------ what both miss, pinned

BOTH_MISS = {  # the "cannot see" list: what neither reading sees. Each form is one probe (review of #241, F1)
    "a shell string": 'import subprocess\nsubprocess.run("python -m aew.unlisted --x", shell=True)\n',
    "a string command without a shell": 'import subprocess\nsubprocess.run("python -m aew.unlisted")\n',
    "a joined -maew.x": 'import sys\nargv = [sys.executable, "-maew.unlisted"]\n',
    "a multiprocessing child": 'import multiprocessing\nmultiprocessing.Process(target=f).start()\n',
    "an argv built by append": 'import sys\na = [sys.executable]\na.append("-m")\na.append(name)\n',
    "a -c payload that imports AEW": 'import sys\nargv = [sys.executable, "-c", "from aew.x import main; main()"]\n',
    "runpy, which runs in this process": 'import runpy\nrunpy.run_module("aew.unlisted", run_name="__main__")\n',
    "an exec with a computed name and no sys.executable": 'import os\nos.execl(python, python, "-m", name)\n',
}
REPORTED = {  # a `-m` whose module name is not a plain string: a site with an unreadable name, so the check fails on it
    "the interpreter in a variable": 'python = sys.executable\nargv = [python, "-m", f"aew.{name}"]\n',
    "a string interpreter": 'argv = ["python", "-m", name]\n',
    "sys.executable and a computed name": 'import sys\nargv = [sys.executable, "-m", name]\n',
    "an f-string name": 'import sys\nargv = [sys.executable, "-m", f"aew.{x}"]\n',
    "a name held in a constant": 'import sys\nMODULE = "aew.unlisted"\nargv = [sys.executable, "-m", MODULE]\n',
    "an argv extended in a second step": 'import sys\na = [sys.executable]\na += ["-m", name]\n',
    "an argv that ends in -m": 'import sys\nargv = [sys.executable, "-m"]\na = ["-m"]\n',
    "an exec with sys.executable, computed": 'import os, sys\nos.execl(sys.executable, sys.executable, "-m", name)\n',
}


@pytest.mark.parametrize("form", sorted(BOTH_MISS))
def test_what_neither_spawn_detector_sees_is_pinned_one_probe_per_item(form):
    source = BOTH_MISS[form]
    assert planted(source)[0] == [] and T.spawn_targets(source) == [], form


@pytest.mark.parametrize("form", sorted(REPORTED))
def test_a_dash_m_with_a_computed_name_is_reported_not_passed_over(form):
    """The AST reading reports it as a site with an unreadable name, so the spawn-site test fails on it; the text
    reading cannot see a name it cannot read, and that is why the agreement test compares readable targets only."""
    source = REPORTED[form]
    sites = planted(source)[0]
    assert sites and all(s.target is None for s in sites), form
    assert spawn_problems(sites), form
    assert T.spawn_targets(source) == [], form


def test_runpy_runs_in_this_process_so_the_modules_family_lists_it_as_a_dynamic_import_instead():
    """Not a spawn (no process starts), so the spawn readings rightly miss it; the import graph cannot follow it, and
    says so."""
    known = frozenset({"aew", "aew.unlisted"})
    _, unresolved = M.edges_of(ast.parse(BOTH_MISS["runpy, which runs in this process"]), "aew.planted", False, known)
    assert [u["why"] for u in unresolved] == ["runpy.run_module loads code by file path or name"]


def test_what_only_the_text_reading_sees_is_pinned_and_what_only_the_ast_reading_sees():
    """The text reading cannot tell a comment from code, so a spawn written in a comment is its alone; the AST reading
    sees through a comment between ``"-m",`` and the module, which the text reading's pattern does not. Both fail the
    agreement test closed, which is why the AST reading is the source and the text reading the cross-check."""
    comment = '# [sys.executable, "-m", "aew.unlisted"]\nx = 1\n'
    assert planted(comment)[0] == [] and T.spawn_targets(comment) == ["aew.unlisted"]
    between = 'import sys\nargv = [sys.executable, "-m",  # why\n        "aew.unlisted"]\n'
    assert [s.target for s in planted(between)[0]] == ["aew.unlisted"] and T.spawn_targets(between) == []


def test_what_the_declaration_detectors_cannot_see_is_pinned_one_probe_per_item():
    """A declaration with a computed name is reported as unreadable by the AST reading (and fails the check); the text
    reading misses it. A same-named call that is not process_kind's is not a declaration to the AST reading, which
    identifies the callee by its import source, and is one to the text reading, the cruder of the two."""
    computed = 'from aew import process_kind\nprocess_kind.declare(name)\n'
    _, declares = planted(computed)
    assert [d.via for d in declares] == ["unreadable"] and T.declared(computed) == []
    lookalike = 'import other\nother.declare("aew.stg02.server")\n'
    assert planted(lookalike)[1] == [] and T.declared(lookalike) == ["aew.stg02.server"]


def test_the_console_script_forms_that_no_dash_m_detector_sees_are_found_and_kept_on_the_records():
    path_form = 'import os, sys\ndef build():\n    return os.path.dirname(sys.executable)\n'
    list_form = 'LEAD_MCP_COMMAND = ["aew", "lead", "mcp"]\n'
    pair = 'NAMES = ("aew", "aew.exe")\nOTHER = ["python", "-c", "x"]\n'

    def found(source: str) -> list[str | None]:
        return [c.symbol for c in E.console_script_sites(ast.parse(source), "aew.planted", False)]

    assert found(path_form) == ["build"]
    assert found(list_form) == ["LEAD_MCP_COMMAND"]
    assert found(pair) == []
    # what this reading cannot see (review of #241, F1), one probe each: a tuple argv, a lookup, a path join, a string
    for source in ('NAMES = ("aew", "lead", "mcp")\n',
                   'import shutil\nargv = [shutil.which("aew"), "status"]\n',
                   'import sys\nfrom pathlib import Path\nexe = Path(sys.executable).parent / "aew"\n',
                   'CMD = "aew status"\n'):
        assert found(source) == [], source


def test_one_list_holds_every_start_of_an_entry_point_with_its_form_and_says_how_complete_it_is():
    """Addendum 3 (review of #241, F2): a reader that reads ``records`` only sees the console-script starts as well as
    the ``-m`` spawns, each with its form, and each list fact says how complete it is."""
    built = E.build(CTX)
    roles = E.cli_roles(CTX, TABLE)
    spawns, _ = tree_sites()
    consoles = [(name, c) for name in CTX.sources() for c in E.console_script_sites_from(CTX.index(name))]
    path_sites = {(m, c.symbol) for m, c in consoles if c.form == E.PATH_FORM}
    assert path_sites and any(c.form == E.ARGV_FORM for _, c in consoles)
    by_key = {r.key: r.fact or {} for r in built.records}
    coverage_of = {r.key: r.fact_coverage or {} for r in built.records}
    for key, fact in by_key.items():
        assert {i["form"] for i in fact["starts"]} <= {E.DASH_M, E.ARGV_FORM, E.PATH_FORM}, key
        assert all(set(i) == {"module", "symbol", "form", "attribution"} for i in fact["starts"]), key
        assert "fact_coverage" not in fact, key  # it is on the record, beside coverage (addendum 3)
        assert set(coverage_of[key]) == {"declared_at", "starts"} and all(
            c["label"] == C.LOWER for c in coverage_of[key].values()), key
        mine = {(i["module"], i["symbol"]) for i in fact["starts"] if i["form"] == E.PATH_FORM}
        assert mine == (path_sites if key in roles else set()), key  # the PATH makes every role of the CLI startable
        assert {(i["module"], i["symbol"]) for i in fact["starts"] if i["form"] == E.DASH_M} == {
            (s.module, s.symbol) for s in spawns if s.target is not None and E.entry_for(s.target) == key}, key
    argv_sites = {(m, c.symbol) for m, c in consoles if c.form == E.ARGV_FORM}
    lead = {(i["module"], i["symbol"]) for i in by_key["aew lead mcp"]["starts"] if i["form"] == E.ARGV_FORM}
    assert ("aew.harness.opencode.projection", "LEAD_MCP_COMMAND") in lead  # cli_entry_point decides the role
    assert ("aew.dashboard.projections", "Projector._search_hit") in {
        (i["module"], i["symbol"]) for i in by_key["aew"]["starts"] if i["form"] == E.ARGV_FORM}
    unresolved = {(i["module"], i["symbol"])
                  for k in by_key for i in coverage_of[k]["starts"]["unresolved"]}
    assert set(argv_sites) <= unresolved  # an argv constant is listed, and its being run is not decided


def test_a_literal_declaration_planted_in_the_defining_module_is_seen_and_its_own_forwarding_is_not_one():
    """The forgotten-mask rule: ``aew.process_kind`` is not exempt (review of #241, F6). Its ``declared_as`` forwards a
    parameter to ``declare``, which is the machinery; a literal there is a declaration like any other."""
    text = (ROOT / "src" / "aew" / "process_kind.py").read_text(encoding="utf-8")
    assert E.declare_sites(ast.parse(text), E.PROCESS_KIND, False) == []
    assert T.declared(text) == [] and not T.declares_cli_roles(text)
    _, declares = tree_sites()
    roles = E.cli_roles(CTX, TABLE)
    for name, problem in (("aew.unlisted", "not in the table"), ("aew.stg02.server", "another module's")):
        planted_text = text + f'\n\ndef _planted():\n    declare("{name}")\n'
        sites = E.declare_sites(ast.parse(planted_text), E.PROCESS_KIND, False)
        assert [(s.entry_point, s.via) for s in sites] == [(name, "literal")]
        assert T.declared(planted_text) == [name]
        assert any(problem in p for p in declaration_problems(declares + sites, roles)), name


# ---------------------------------------------------------------------------------- the table and its declarations

def test_every_entry_point_declares_itself_and_every_declaration_is_one():
    _, declares = tree_sites()
    assert declaration_problems(declares, E.cli_roles(CTX, TABLE)) == []


def test_a_planted_declaration_of_an_unlisted_entry_point_and_a_missing_one_fail_the_check():
    _, declares = tree_sites()
    roles = E.cli_roles(CTX, TABLE)
    wrong = declares + planted('from aew import process_kind\nprocess_kind.declare("aew.unlisted")\n')[1]
    assert any("aew.unlisted" in p for p in declaration_problems(wrong, roles))
    missing = [d for d in declares if d.entry_point != "aew.stg02.server"]
    assert any("aew.stg02.server" in p and "nowhere" in p for p in declaration_problems(missing, roles))
    lost_cli = [d for d in declares if d.via != "cli_entry_point"]
    assert declaration_problems(lost_cli, roles)
    elsewhere = declares + planted('from aew import process_kind\nprocess_kind.declare("aew.stg02.server")\n',
                                   "aew.somewhere_else")[1]
    assert any("another module's" in p for p in declaration_problems(elsewhere, roles))


def test_the_clis_dash_m_module_is_the_console_scripts_module():
    """``entry_for`` maps ``-m aew`` to the CLI row; that holds while ``aew/__main__.py`` runs the console script's
    ``main``."""
    scripts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    module, _, function = scripts["aew"].partition(":")
    tree = ast.parse((ROOT / "src" / "aew" / "__main__.py").read_text(encoding="utf-8"))
    imported = {(n.module, a.name) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    assert (module, function) in imported
    assert E.entry_for("aew") == E.entry_for("aew.__main__") == E.CLI_ENTRY and E.CLI_ENTRY in TABLE
