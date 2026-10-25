"""The state-write sites of the generated reference (STG-12 S12-2, family 5): where the product changes a state, and
whether the Ticket machine's table is asked there, read from the source by two independently written detectors.

The table (``aew.engine.transitions.RULES``) does not stop code changing a Ticket's state without asking it: its
``check`` is called by the callers of ``WorkUnits.set_state``, which does not call it, and some code assigns
``unit["state"]`` itself. So the ``transitions`` records say, per edge, which unchecked sites can take it. The detectors
are ``machines_writes.py`` (``ast``, identifying ``check`` by where it was imported from) and
``machines_writes_text.py`` (``re``, sharing no code). They agree on the tree and on every planted case; what both
miss is pinned below, one probe per item, and where the text reading differs on purpose is pinned too.

The heavy lanes run this because it reads ``src`` only: a pull request that adds a state write changes ``src`` and so
runs the full gate.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tool_modules():
    """The generator's family modules, with ``tools/`` on the path for the extent of the import only."""
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import common, machines, machines_writes, machines_writes_text
    finally:
        sys.path.remove(here)
    return common, machines, machines_writes, machines_writes_text


C, M, W, X = _tool_modules()
CTX = C.Context(ROOT)


def key(s):
    return (s.module, s.symbol or "", s.form, s.checked)


def ast_sites(source: str, module: str = "aew.m"):
    return sorted(map(key, W.writes(ast.parse(source), module, False)))


def text_sites(source: str, module: str = "aew.m"):
    return sorted(map(key, X.writes(source, module)))


def tree_sites():
    ours, theirs = [], []
    for name, src in CTX.sources().items():
        assert src.tree is not None, f"{name} does not parse"
        ours += W.writes_from(src.tree, CTX.index(name), name)
        theirs += X.writes(src.text, name)
    return sorted(map(key, ours)), sorted(map(key, theirs))


def disagreements(source: str) -> tuple[list, list]:
    a, t = ast_sites(source), text_sites(source)
    return [x for x in a if x not in t], [x for x in t if x not in a]


# ------------------------------------------------------------------------------------------- the tree

def test_the_two_state_write_detectors_agree_on_the_tree():
    ours, theirs = tree_sites()
    assert ours == theirs
    assert len(ours) > 20, "the engine's state writes were not found"


def test_every_state_write_site_is_behind_the_table_or_declared():
    """The declared table (``machines.SITES``) is every site with no ``transitions.check`` in its function, in both
    directions: a new unchecked write is unresolved on every edge until it is declared, and an entry the code no longer
    has fails the build. The assertion here is the second half and its converse: nothing declared is missing a site,
    and no site is unknown."""
    found = M.unchecked_sites(W.tree_writes(CTX))
    from aew.engine import transitions

    vias = {v for r in transitions.RULES.values() for v in (r.via, *r.also)}
    assert M.site_problems(found, M.SITES, vias) == []
    assert set(found) == set(M.SITES), (sorted(set(found) - set(M.SITES)), sorted(set(M.SITES) - set(found)))


def test_the_package_defines_one_set_state_and_the_port_that_declares_it():
    """A ``.set_state(`` call is found by its attribute name, since an attribute call has no import to follow. That is
    sound while the package defines one such function (and the protocol that declares it): a second definition would be
    a second primitive the reading identifies by name alone."""
    defined = {(name, node.name) for name, src in CTX.sources().items() if src.tree is not None
               for node in ast.walk(src.tree) if isinstance(node, ast.FunctionDef) and node.name == "set_state"}
    assert sorted(defined) == [("aew.engine.ports", "set_state"), ("aew.engine.work_ops", "set_state")], defined


# ------------------------------------------------------------------------------------------- planted cases

CHECK = "from aew.engine import transitions\n\n\n"


@pytest.mark.parametrize(("source", "want"), [
    # right: a write with the table asked in the same function
    (CHECK + "def f(units, u, to):\n    transitions.check(u['state'], to, 'x')\n    units.set_state(u, to, 'r')\n",
     [("aew.m", "f", "set_state", True)]),
    (CHECK + "def f(u, to):\n    transitions.check(u['state'], to, 'x')\n    u['state'] = to\n",
     [("aew.m", "f", "assign", True)]),
    # wrong: a write with no check in its function
    ("def f(units, u, to):\n    units.set_state(u, to, 'r')\n", [("aew.m", "f", "set_state", False)]),
    ("def f(u):\n    u['state'] = 'DONE'\n", [("aew.m", "f", "assign", False)]),
    # the check is in another function: not this site's
    (CHECK + "def g(u):\n    transitions.check(u['state'], 'DONE', 'x')\n\n\ndef f(u):\n    u['state'] = 'DONE'\n",
     [("aew.m", "f", "assign", False)]),
    # a method, and a function inside one: the qualified symbol
    ("class K:\n    def m(self, u):\n        def inner():\n            u['state'] = 'X'\n        inner()\n",
     [("aew.m", "K.m.inner", "assign", False)]),
    # a comparison and a read are not writes
    ("def f(u):\n    return u['state'] == 'DONE' or u['state'] != 'X'\n", []),
    # two writes in one function are two sites, both checked or not together
    ("def f(units, u):\n    units.set_state(u, 'A', 'r')\n    u['state'] = 'B'\n",
     [("aew.m", "f", "assign", False), ("aew.m", "f", "set_state", False)]),
    # missing: nothing at all
    ("def f(u):\n    return u\n", []),
])
def test_both_detectors_read_each_planted_case_alike(source, want):
    assert ast_sites(source) == sorted(want)
    assert text_sites(source) == sorted(want)


@pytest.mark.parametrize("source", [
    "def f(u):\n    u.update(state='X')\n",
    "def f(u):\n    u.update({'state': 'X'})\n",
    "def f(u):\n    setattr(u, 'state', 'X')\n",
    "def f(u):\n    u |= {'state': 'X'}\n",
    "def f(u):\n    k = 'state'\n    u[k] = 'X'\n",
    "def f(u):\n    u['hist'] = u['state']\n",   # not a write of the state
    "def f(units, u):\n    getattr(units, 'set_' + 'state')(u, 'X', 'r')\n",
])
def test_what_both_detectors_miss_is_pinned_one_probe_each(source):
    """The 'cannot see' list: a change of state spelled any of these ways is in neither reading."""
    assert ast_sites(source) == [] and text_sites(source) == []


def test_the_text_reading_is_deliberately_cruder_where_a_check_is_aliased_or_another_modules():
    """The AST reading identifies ``check`` by where it was imported from; the text reading by the two spellings the
    package uses. They differ on exactly these two, and the AST reading is the source."""
    aliased = ("from aew.engine.transitions import check as ask\n\n\n"
               "def f(u, to):\n    ask(u['state'], to, 'x')\n    u['state'] = to\n")
    assert ast_sites(aliased) == [("aew.m", "f", "assign", True)]
    assert text_sites(aliased) == [("aew.m", "f", "assign", False)]
    impostor = ("from other import transitions\n\n\n"
                "def f(u, to):\n    transitions.check(u['state'], to, 'x')\n    u['state'] = to\n")
    assert ast_sites(impostor) == [("aew.m", "f", "assign", False)]
    assert text_sites(impostor) == [("aew.m", "f", "assign", True)]
    other_check = ("from aew.other import check\n\n\n"
                   "def f(u, to):\n    check(u['state'], to, 'x')\n    u['state'] = to\n")
    assert ast_sites(other_check) == [("aew.m", "f", "assign", False)]


def test_a_comment_is_not_a_site_in_either_reading():
    source = "def f(u):\n    # u.set_state(u, 'X', 'r') and u['state'] = 'Y' were here\n    return u\n"
    assert ast_sites(source) == [] and text_sites(source) == []


# ------------------------------------------------------------------------------------- the detectors are not blind

def test_a_detector_made_blind_makes_the_agreement_test_fail(monkeypatch):
    """The control of the agreement test itself: with either reading blind, the tree no longer agrees."""
    ours, theirs = tree_sites()
    assert ours == theirs
    monkeypatch.setattr(W, "writes_from", lambda tree, index, module: [])
    blind_ast, same_text = tree_sites()
    assert blind_ast != same_text
    monkeypatch.undo()
    monkeypatch.setattr(X, "writes", lambda text, module: [])
    same_ast, blind_text = tree_sites()
    assert same_ast != blind_text


def test_a_planted_unchecked_write_is_a_difference_in_the_declared_table():
    planted = M.unchecked_sites([*W.tree_writes(CTX), W.StateWrite("aew.engine.new_ops", "New.f", W.SET_STATE, False)])
    assert ("aew.engine.new_ops", "New.f") in planted and ("aew.engine.new_ops", "New.f") not in M.SITES
    assert set(planted) - set(M.SITES) == {("aew.engine.new_ops", "New.f")}
