"""The launch census (G3 addendum 7, ruling 1; the designer's DV-2 and DV-5): every process start in src/ and eval/
is classified (contained, weaker and registered, or not an agent context), and every handler of a containment failure
re-raises or refuses, held both ways to ``tests/launch-census.yaml`` by two detectors written apart
(``tests/helpers/launch_census.py``). A planted unclassified start, a planted branch that runs on after a containment
failure, a table row with no start, and an unreadable file each fail it."""

from __future__ import annotations

from pathlib import Path

import launch_census as L
import pytest

from aew.util import load_yaml

REPO = Path(__file__).resolve().parents[2]
TABLE = REPO / "tests" / "launch-census.yaml"


def table() -> dict:
    return load_yaml(TABLE.read_text(encoding="utf-8"), source=str(TABLE))


def test_every_process_start_in_src_and_eval_is_classified_as_the_table_says():
    assert L.check(REPO, table()) == []


def test_only_the_fast_lane_reads_the_census_helper():
    """`tests/unit/test_ci_tools.py` lists the helper among its core-only readers, which a reduced tier may skip: that
    holds only while nothing outside tests/unit imports it."""
    readers = [p.relative_to(REPO).as_posix() for root in ("src", "eval", "tests", "tools") for p in
               (REPO / root).rglob("*.py") if "launch_census" in p.read_text(encoding="utf-8", errors="replace")]
    assert [p for p in readers if not p.startswith("tests/unit/") and p != "tests/helpers/launch_census.py"] == []


def test_the_table_excludes_by_name_what_the_census_excludes_and_each_path_exists():
    assert table()["excluded"] == L.EXCLUDED
    for prefix in L.EXCLUDED:
        assert (REPO / prefix).is_dir(), f"{prefix} is excluded and does not exist: remove its exclusion"


def test_nothing_runs_an_excluded_path():
    """The designer, 2026-11-01: if anything referenced a program in an excluded path from the code, the tests, the
    tools, the workflows or the runbooks, a lane, job, tool or runbook could run it, and it would leave the
    exclusion and register like any eval lane. This file is left out: its planted controls name such a program."""
    assert L.excluded_refs(REPO, skip=["tests/unit/test_launch_census.py"]) == []


# ------------------------------------------------------------------------------------------------ planted controls

def plant(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    return tmp_path


RIGHT = {"src/aew/x.py": "import subprocess\n\n\ndef go():\n    subprocess.run(['git', 'status'])\n"}
RIGHT_TABLE = {"starts": [{"site": "src/aew/x.py::go", "call": "run", "classes": ["not_agent_context"],
                           "reason": "git"}], "handlers": [], "ast_only": [], "token_only": []}


def test_a_right_case_holds(tmp_path):
    assert L.check(plant(tmp_path, RIGHT), RIGHT_TABLE) == []


def test_a_planted_unclassified_start_fails(tmp_path):
    repo = plant(tmp_path, {**RIGHT, "src/aew/y.py": "from aew.harness import procs\n\n\ndef launch():\n"
                                                     "    procs.ProcessTree().spawn(['agent'])\n"})
    assert L.check(repo, RIGHT_TABLE) == ["an unclassified start: src/aew/y.py::launch calls ProcessTree (1x)"]


def test_a_table_row_with_no_start_fails(tmp_path):
    repo = plant(tmp_path, {"src/aew/x.py": "def go():\n    return None\n"})
    assert L.check(repo, RIGHT_TABLE) == ["a table row with no start in the code: src/aew/x.py::go run"]


SWALLOW = """
from aew.errors import ContainmentUnavailable
from aew.harness import containment, procs


def launch(policy):
    layout = None
    try:
        layout, _ = containment.establish(role="r", scope="s", workspace=".", run_dir=None, scratch=".",
                                          bridge_dir=None, policy=policy)
    except ContainmentUnavailable:
        pass  # goes on with no layout: uncontained under required
    procs.ProcessTree(layout=layout).spawn(["agent"])
"""
SWALLOW_TABLE = {"starts": [
    {"site": "src/aew/z.py::launch", "call": "establish", "classes": ["contained"], "reason": "planted",
     "contained_by": ["src/aew/z.py::launch"]},
    {"site": "src/aew/z.py::launch", "call": "ProcessTree", "classes": ["contained"], "reason": "planted",
     "contained_by": ["src/aew/z.py::launch"]}],
    "handlers": [{"site": "src/aew/z.py::launch", "catches": ["ContainmentUnavailable"], "does": "goes_on",
                  "reason": "planted"}], "ast_only": [], "token_only": []}


def test_a_planted_branch_that_runs_on_after_a_containment_failure_fails(tmp_path):
    """DV-2: the site calls establish, so a site-level census reads it as contained; its failure branch goes on."""
    repo = plant(tmp_path, {"src/aew/z.py": SWALLOW})
    assert L.check(repo, SWALLOW_TABLE) == [
        "a containment failure goes on at src/aew/z.py::launch (['ContainmentUnavailable']): src/ refuses under "
        "required"]
    unpinned = {**SWALLOW_TABLE, "handlers": []}
    assert any(p.startswith("handlers in the code but not the table") for p in L.check(repo, unpinned))
    refusing = SWALLOW.replace("        pass  # goes on with no layout: uncontained under required", "        raise")
    pinned = {**SWALLOW_TABLE, "handlers": [{**SWALLOW_TABLE["handlers"][0], "does": "raises"}]}
    assert L.check(plant(tmp_path, {"src/aew/z.py": refusing}), pinned) == []


def test_a_handler_that_raises_on_one_path_only_goes_on(tmp_path):
    """#321 review, F3: a handler is read as raising only when every path through it raises or returns; one that
    raises on a branch and falls through on the other goes on, and the census fails on it in src/."""
    swallowed = "        pass  # goes on with no layout: uncontained under required"
    branch = SWALLOW.replace(swallowed, "        if policy:\n            raise")
    assert branch != SWALLOW
    assert L.check(plant(tmp_path, {"src/aew/z.py": branch}), SWALLOW_TABLE) == [
        "a containment failure goes on at src/aew/z.py::launch (['ContainmentUnavailable']): src/ refuses under "
        "required"]
    both = SWALLOW.replace(swallowed, "        if policy:\n            raise\n        else:\n            return None")
    pinned = {**SWALLOW_TABLE, "handlers": [{**SWALLOW_TABLE["handlers"][0], "does": "returns"}]}
    assert L.check(plant(tmp_path, {"src/aew/z.py": both}), pinned) == []


def test_a_weaker_start_with_no_register_entry_fails(tmp_path):
    repo = plant(tmp_path, {"src/aew/w.py": "from aew.harness import procs\n\n\ndef launch():\n"
                                            "    procs.ProcessTree().spawn(['agent'])\n"})
    row = {"site": "src/aew/w.py::launch", "call": "ProcessTree", "classes": ["weaker_registered"],
           "reason": "planted", "registered_by": ["src/aew/w.py::launch"]}
    assert L.check(repo, {"starts": [row], "handlers": []}) == [
        "src/aew/w.py::launch ProcessTree: src/aew/w.py::launch (registered_by) calls none of "
        f"{sorted(L.REGISTERS)}"]
    registered = ("from aew.harness import procs, weaker_register\n\n\ndef launch():\n"
                  "    weaker_register.enter(kind='eval_raw', label=None, ownership='process_group')\n"
                  "    procs.ProcessTree().spawn(['agent'])\n")
    assert L.check(plant(tmp_path, {"src/aew/w.py": registered}), {"starts": [row], "handlers": []}) == []


def test_an_unreadable_file_is_marked_never_read_as_no_starts(tmp_path):
    repo = plant(tmp_path, {**RIGHT, "src/aew/broken.py": "def (:\n"})
    problems = L.check(repo, RIGHT_TABLE)
    assert problems and problems[0].startswith("unreadable: src/aew/broken.py"), problems


# ------------------------------------------------------------------------------- the detectors, probed by position

@pytest.mark.parametrize("form", [
    "from subprocess import run as r\n\n\ndef go():\n    r(['x'])\n",
    "import subprocess as sp\n\n\ndef go():\n    sp.run(['x'])\n",
    "import subprocess\n\n\ndef go():\n    start = subprocess.run\n    start(['x'])\n",
])
def test_an_aliased_start_is_found_by_its_import_and_only_by_the_ast_detector(tmp_path, form):
    """Binding: the AST detector resolves a start by import, whatever its local name; the token detector, which reads
    text alone, does not. Both forms are absent from src/ and eval/ today (``ast_only`` is empty)."""
    repo = plant(tmp_path, {"src/aew/a.py": form})
    assert L.by_ast(repo).sites() == {("src/aew/a.py", "go", "run"): 1}
    assert L.by_tokens(repo).sites() == {}


@pytest.mark.parametrize("form", [
    "def go(tree):\n    tree.run(['x'])\n    self_run = 1\n",
    "def go():\n    s = 'subprocess.run([\"x\"])'  # subprocess.run(['x'])\n    return s\n",
])
def test_a_name_that_is_not_a_start_is_found_by_neither(tmp_path, form):
    """Position: a method called ``run``, and a start written in a string or a comment, are no starts."""
    repo = plant(tmp_path, {"src/aew/a.py": form})
    assert L.by_ast(repo).sites() == {} and L.by_tokens(repo).sites() == {}


@pytest.mark.parametrize("form", list(L.CANNOT_SEE))
def test_what_both_detectors_cannot_see_is_exactly_the_pinned_list(tmp_path, form):
    """Each form only a value names, pinned: both miss it, so a start written this way would need a census of its
    own. None is in src/ or eval/ (a grep for each in the test below)."""
    body = form.replace("(...)", "(['x'])").replace("\n", "\n    ")
    repo = plant(tmp_path, {"src/aew/a.py": f"import importlib\nimport subprocess\n\n\ndef go():\n    {body}\n"})
    assert L.by_ast(repo).sites() == {} and L.by_tokens(repo).sites() == {}


def test_no_form_both_cannot_see_is_in_src_or_eval():
    """Read as code, not text: a ``getattr`` of a start's name on a process module, or a process module imported by a
    string (``getattr(subprocess, "CREATE_NO_WINDOW", 0)`` is a constant, and no start)."""
    import ast

    modules = {"subprocess", "os", "asyncio", "pty", "multiprocessing", "concurrent.futures"}
    hits = []
    for rel, path in L.sources(REPO):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            first, rest = node.args[0], node.args[1:]
            if (name == "getattr" and isinstance(first, ast.Name) and first.id in modules and rest
                    and isinstance(rest[0], ast.Constant) and rest[0].value in L.NAMES):
                hits.append(f"{rel}:{node.lineno}")
            if name in ("import_module", "__import__") and isinstance(first, ast.Constant) and first.value in modules:
                hits.append(f"{rel}:{node.lineno}")
        for node in ast.walk(ast.parse(path.read_bytes())):  # the forms #321's review added (F3)
            values: list[ast.AST] = []
            if isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                if name in ("subprocess_exec", "subprocess_shell"):
                    hits.append(f"{rel}:{node.lineno}: {name}")
                if name == "partial":
                    values += node.args[:1]
            if isinstance(node, ast.ClassDef):
                values += node.bases
            if isinstance(node, ast.AnnAssign) and node.value is not None:
                values.append(node.value)
            if isinstance(node, ast.Assign) and any(isinstance(x, ast.Attribute) for x in node.targets):
                values.append(node.value)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                values += [d for d in (*node.args.defaults, *node.args.kw_defaults) if d is not None]
            hits += [f"{rel}:{getattr(v, 'lineno', 0)}: {ast.unparse(v)}" for v in values
                     if isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name) and v.value.id in modules
                     and v.attr in L.NAMES]
    assert hits == []


def test_a_start_in_a_string_run_by_python_c_is_classified_at_the_start_that_runs_it():
    """procs' session reaper and sentinel are code in strings (``python -c``): no detector reads them, and the start
    that runs each is a row of its own (``run_session_tree``, ``ProcessTree._spawn``)."""
    rows = {(r["site"], r["call"]) for r in table()["starts"]}
    assert {("src/aew/harness/procs.py::run_session_tree", "Popen"),
            ("src/aew/harness/procs.py::ProcessTree._spawn", "Popen")} <= rows


# ------------------------------------------------------------------------------------------- the exclusions' guard

@pytest.mark.parametrize("text, refs", [
    ("# eval/reviews/README.md is a note\n", 0),                       # right: a note, nothing runs it
    ("subprocess.run(['python', 'eval/m3/spike/probe_misc.py'])\n", 1),  # wrong: a program's path
    ("import v2lib\n", 1),                                             # wrong: an import of one of its modules
])
def test_the_guard_finds_a_planted_reference_to_an_excluded_program(tmp_path, text, refs):
    for prefix in L.EXCLUDED:
        (tmp_path / prefix).mkdir(parents=True)
    (tmp_path / "eval/m3/spike/probe_misc.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "eval/m3/spike/v2lib.py").write_text("pass\n", encoding="utf-8")
    plant(tmp_path, {"tools/x.py": text})
    assert len(L.excluded_refs(tmp_path)) == refs


def test_the_guard_fails_on_an_excluded_path_that_no_longer_exists(tmp_path, monkeypatch):
    """Missing: an exclusion whose path is gone would linger unread."""
    monkeypatch.setitem(L.EXCLUDED, "eval/gone/", "planted")
    with pytest.raises(AssertionError, match="eval/gone/ is excluded and does not exist"):
        for prefix in L.EXCLUDED:
            assert (REPO / prefix).is_dir(), f"{prefix} is excluded and does not exist: remove its exclusion"
