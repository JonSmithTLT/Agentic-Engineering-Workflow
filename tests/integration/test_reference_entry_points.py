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
        from reference_families import common, entry_points, entry_points_text
    finally:
        sys.path.remove(here)
    return common, entry_points, entry_points_text


C, E, T = _tool_modules()
TABLE = dict(process_kind.ENTRY_POINTS)
CTX = C.Context(ROOT)


def tree_sites(ctx=CTX):
    spawns, declares = [], []
    for name, src in ctx.sources().items():
        assert src.tree is not None, f"{name} does not parse"
        spawns += E.spawn_sites(src.tree, name, src.is_package)
        declares += E.declare_sites(src.tree, name, src.is_package)
    return spawns, declares


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
NOT_A_SPAWN = [
    'argv = ["git", "log", "-m", "a message"]\n',                       # git's -m
    'argv = ["python", "-m", "pytest", "-q"]\n',                        # a module outside AEW
    '"""python -m aew.unlisted"""\n',                                   # prose
    'argv = ["-m"]\n',                                                 # nothing after it
    'argv = ["aew", "-m", "x"]\n',                                      # -m of something else
]


def test_a_planted_unlisted_spawn_site_fails_the_check_and_a_listed_or_absent_one_does_not():
    assert spawn_problems(planted(RIGHT)[0]) == [] and len(planted(RIGHT)[0]) == 1
    assert spawn_problems(planted(RIGHT_CLI)[0]) == [] and len(planted(RIGHT_CLI)[0]) == 1
    for source in (WRONG, WRONG_TUPLE):
        assert len(spawn_problems(planted(source)[0])) == 1, source
    for source in NOT_A_SPAWN:
        assert planted(source)[0] == [], source


def test_a_spawn_site_added_to_a_copy_of_the_tree_fails_the_check_and_is_a_gap_in_the_reference(tmp_path):
    shutil.copytree(ROOT / "src" / "aew", tmp_path / "src" / "aew", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "src" / "aew" / "planted.py").write_text(WRONG, encoding="utf-8")
    ctx = C.Context(tmp_path)
    sites, _ = tree_sites(ctx)
    assert any("aew.unlisted" in p for p in spawn_problems(sites))
    built = E.build(ctx)
    assert [g for g in built.gaps if "names no listed entry point" in g.why and g.module == "aew.planted"]


def test_the_reference_of_this_tree_has_no_defect_gap():
    """A gap that says the code and the table disagree is a finding, never a quiet line in gaps.md."""
    defects = ("names no listed entry point", "nothing declares itself", "cannot be read or is not in the table",
               "not a plain string")
    assert [g for g in E.build(CTX).gaps if any(d in g.why for d in defects)] == []


# ------------------------------------------------------------------------------------------ the second detector

def test_the_two_spawn_detectors_agree_on_every_module_of_the_tree():
    for name, src in CTX.sources().items():
        assert src.tree is not None
        by_ast = sorted(s.target for s in E.spawn_sites(src.tree, name, src.is_package) if s.target is not None)
        assert by_ast == T.spawn_targets(src.text), name


@pytest.mark.parametrize("source", [RIGHT, RIGHT_CLI, WRONG, WRONG_TUPLE, *NOT_A_SPAWN])
def test_the_two_spawn_detectors_agree_on_every_planted_case(source):
    sites, _ = planted(source)
    assert sorted(s.target for s in sites if s.target is not None) == T.spawn_targets(source)


def test_the_declaration_detectors_agree_on_every_module_of_the_tree():
    for name, src in CTX.sources().items():
        if name == E.PROCESS_KIND:
            continue  # defines the calls; declares nothing
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

def test_what_the_spawn_detectors_cannot_see_is_pinned_one_probe_per_item():
    """The "cannot see" list. A shell string and a joined ``-maew.x`` are missed by both. A module name that is not a
    plain string is missed by the text reading and *reported* by the AST reading as an unreadable site, so the check
    fails on it instead of passing over it."""
    both_miss = ['import subprocess\nsubprocess.run("python -m aew.unlisted --x", shell=True)\n',
                 'import sys\nargv = [sys.executable, "-maew.unlisted"]\n',
                 'import multiprocessing\nmultiprocessing.Process(target=f).start()\n']
    for source in both_miss:
        assert planted(source)[0] == [] and T.spawn_targets(source) == [], source
    unreadable = ['import sys\nargv = [sys.executable, "-m", name]\n',
                  'import sys\nargv = [sys.executable, "-m", f"aew.{x}"]\n',
                  'import sys\nMODULE = "aew.unlisted"\nargv = [sys.executable, "-m", MODULE]\n']
    for source in unreadable:
        sites = planted(source)[0]
        assert [s.target for s in sites] == [None] and T.spawn_targets(source) == [], source
        assert spawn_problems(sites), source


def test_what_only_the_text_reading_sees_is_pinned():
    """The text reading cannot tell a comment from code, so a spawn written in a comment is its alone. That is why the
    AST reading is the source and the text reading the cross-check: on the tree they agree, so no comment has one."""
    comment = '# [sys.executable, "-m", "aew.unlisted"]\nx = 1\n'
    assert planted(comment)[0] == [] and T.spawn_targets(comment) == ["aew.unlisted"]


def test_what_the_declaration_detectors_cannot_see_is_pinned_one_probe_per_item():
    """A declaration with a computed name is reported as unreadable by the AST reading (and fails the check); the text
    reading misses it. A same-named call that is not process_kind's is not a declaration to the AST reading, which
    identifies the callee by its import source, and is one to the text reading, the cruder of the two."""
    computed = 'from aew import process_kind\nprocess_kind.declare(name)\n'
    _, declares = planted(computed)
    assert [d.via for d in declares] == ["unreadable"] and T.declared(computed) == []
    lookalike = 'import other\nother.declare("aew.stg02.server")\n'
    assert planted(lookalike)[1] == [] and T.declared(lookalike) == ["aew.stg02.server"]


def test_the_console_script_forms_that_no_dash_m_detector_sees_are_found_for_the_gaps_page():
    path_form = 'import os, sys\ndef build():\n    return os.path.dirname(sys.executable)\n'
    list_form = 'LEAD_MCP_COMMAND = ["aew", "lead", "mcp"]\n'
    pair = 'NAMES = ("aew", "aew.exe")\nOTHER = ["python", "-c", "x"]\n'

    def found(source: str) -> list[str | None]:
        return [symbol for symbol, _ in E.console_script_sites(ast.parse(source), "aew.planted", False)]

    assert found(path_form) == ["build"]
    assert found(list_form) == ["LEAD_MCP_COMMAND"]
    assert found(pair) == []


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
