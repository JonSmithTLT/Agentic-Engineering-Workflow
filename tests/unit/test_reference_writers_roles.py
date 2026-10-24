"""The CLI cut per role of the writers family (STG-12 S12-2, DOC-01), on planted parsers.

``tools/reference_families/writers_roles.py`` reads each ``set_defaults(handler=...)`` of the program for the command
path its parser expression spells, and gives each role the handlers of its commands. Every rule has its planted right
case, wrong case and missing case, so a rule that stopped working would fail. That the reading agrees with the real
parser over the tree is in ``tests/integration/test_reference_writers.py``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _tools():
    here = str(ROOT / "tools")
    sys.path.insert(0, here)
    try:
        from reference_families import writers_flow, writers_roles
    finally:
        sys.path.remove(here)
    return writers_flow, writers_roles


F, K = _tools()
HEAD = "import argparse\n\n\ndef h(a):\n    pass\n\n\ndef h2(a):\n    pass\n\n\n"


def program(source: str) -> Any:
    return F.Program.of({"aew.m": (ast.parse(HEAD + source), False)})


def regs(source: str) -> list[tuple[tuple[tuple[str, ...], ...], tuple[tuple[str, str], ...], bool]]:
    return [(r.paths, r.handlers, r.unread) for r in K.registrations(program(source))]


def only(source: str) -> tuple[tuple[tuple[str, ...], ...], tuple[tuple[str, str], ...], bool]:
    found = regs(source)
    assert len(found) == 1, found
    return found[0]


H, H2 = ("aew.m", "h"), ("aew.m", "h2")

# -------------------------------------------------------------------------------- what a parser expression spells

TOP = ("def build():\n    parser = argparse.ArgumentParser(prog='aew')\n    sub = parser.add_subparsers(dest='c')\n"
       "{body}")


def top(body: str) -> str:
    return TOP.replace("{body}", body)


def test_a_command_is_the_words_of_the_parsers_it_is_added_to():
    assert only(top("    p = sub.add_parser('init')\n    p.set_defaults(handler=h)\n")) == ((("init",),), (H,), False)


def test_a_nested_command_through_a_parameter_is_the_path_of_the_argument():
    source = ("def register(sub):\n    p = sub.add_parser('lead')\n    lsub = p.add_subparsers(dest='x')\n"
              "    q = lsub.add_parser('mcp')\n    q.set_defaults(handler=h)\n\n\n"
              "def build():\n    register(argparse.ArgumentParser().add_subparsers())\n")
    assert only(source) == ((("lead", "mcp"),), (H,), False)


def test_a_name_assigned_again_is_read_as_the_assignment_before_the_use_and_not_every_one():
    """The register functions assign `p` and `q` over and over, in straight-line code: a union would give every handler
    every command."""
    found = regs(top("    p = sub.add_parser('a')\n    p.set_defaults(handler=h)\n"
                     "    p = sub.add_parser('b')\n    p.set_defaults(handler=h2)\n"))
    assert found == [((("a",),), (H,), False), ((("b",),), (H2,), False)]


BRANCHES = {
    "if": "    if parser:\n        p = sub.add_parser('b')\n",
    "for": "    for _ in parser:\n        p = sub.add_parser('b')\n",
    "while": "    while parser:\n        p = sub.add_parser('b')\n",
    "try": "    try:\n        p = sub.add_parser('b')\n    finally:\n        pass\n",
    "try-star": "    try:\n        p = sub.add_parser('b')\n    except* ValueError:\n        pass\n",
    "match": "    match parser:\n        case _:\n            p = sub.add_parser('b')\n",
}


@pytest.mark.parametrize("kind", sorted(BRANCHES))
def test_an_assignment_in_a_branch_the_use_is_outside_of_does_not_hide_the_one_before_it(kind):
    found = only(top("    p = sub.add_parser('a')\n" + BRANCHES[kind] + "    p.set_defaults(handler=h)\n"))
    assert found == ((("a",), ("b",)), (H,), False)


def test_an_assignment_in_a_with_block_is_not_in_a_branch():
    found = only(top("    p = sub.add_parser('a')\n    with parser:\n        p = sub.add_parser('b')\n"
                     "    p.set_defaults(handler=h)\n"))
    assert found == ((("b",),), (H,), False)


def test_an_assignment_in_a_branch_the_use_is_inside_of_is_the_one_read():
    found = only(top("    p = sub.add_parser('a')\n    if parser:\n        p = sub.add_parser('b')\n"
                     "        p.set_defaults(handler=h)\n"))
    assert found == ((("b",),), (H,), False)


def test_a_loop_over_literal_rows_gives_a_command_for_each_row():
    found = only(top("    for name, method in (('x', 'mx'), ('y', 'my')):\n        q = sub.add_parser(name)\n"
                     "        q.set_defaults(handler=lambda a, m=method: getattr(a, m)())\n"))
    assert found == ((("x",), ("y",)), (("aew.m", "build.<handler1>"),), False)


def test_a_loop_over_literal_names_gives_a_command_for_each_name():
    found = only(top("    for name in ('x', 'y'):\n        sub.add_parser(name).set_defaults(handler=h)\n"))
    assert found == ((("x",), ("y",)), (H,), False)


def test_a_loop_over_something_else_is_a_command_this_reading_cannot_read():
    found = only(top("    for name in COMMANDS:\n        sub.add_parser(name).set_defaults(handler=h)\n"))
    assert found == ((), (H,), True)


def test_a_parameter_is_every_argument_of_every_static_call():
    source = ("def register(sub):\n    sub.add_parser('c').set_defaults(handler=h)\n\n\n"
              "def build():\n    a = argparse.ArgumentParser().add_subparsers()\n    register(a)\n"
              "    b = argparse.ArgumentParser().add_subparsers().add_parser('b').add_subparsers()\n    register(b)\n")
    assert only(source) == ((("b", "c"), ("c",)), (H,), False)


def test_a_parameter_a_call_leaves_out_takes_its_default():
    source = ("def register(sub, name='dflt'):\n    sub.add_parser(name).set_defaults(handler=h)\n\n\n"
              "def build():\n    register(argparse.ArgumentParser().add_subparsers())\n")
    assert only(source) == ((("dflt",),), (H,), False)


def test_a_conditional_name_is_each_of_its_arms():
    found = only(top("    sub.add_parser('a' if parser else 'b').set_defaults(handler=h)\n"))
    assert found == ((("a",), ("b",)), (H,), False)


def test_a_closure_reads_every_assignment_of_the_enclosing_functions_name():
    """The closure runs when it is called, not where it is defined: whichever assignment came before the call."""
    source = ("def register(sub):\n    p = sub.add_parser('a')\n\n    def later():\n"
              "        p.set_defaults(handler=h)\n\n    p = sub.add_parser('b')\n    later()\n\n\n"
              "def build():\n    register(argparse.ArgumentParser().add_subparsers())\n")
    assert only(source) == ((("a",), ("b",)), (H,), False)


def test_a_registration_outside_any_function_is_the_empty_path_and_belongs_to_the_module():
    found = K.registrations(program("PARSER = argparse.ArgumentParser()\nPARSER.set_defaults(handler=h)\n"))
    assert [(r.registrar, r.paths, r.unread) for r in found] == [(("aew.m", ""), ((),), False)]


@pytest.mark.parametrize("body", [
    "    p = mystery(sub)\n    p.set_defaults(handler=h)\n",                      # a call this reading cannot follow
    "    with mystery() as p:\n        p.set_defaults(handler=h)\n",               # bound by `with`
    "    p = sub.add_parser('a')\n    with mystery() as p:\n        p.set_defaults(handler=h)\n",  # ... after another
    "    sub.add_parser(mystery()).set_defaults(handler=h)\n",                     # a word it cannot read
    "    parser.add_argument('x').set_defaults(handler=h)\n",                      # not a parser expression
])
def test_a_parser_this_reading_cannot_follow_is_unread_never_guessed(body):
    _, handlers, unread = only(top(body))
    assert unread and handlers == (H,)


def test_a_parameter_nothing_calls_is_unread():
    assert only("def register(sub):\n    sub.add_parser('a').set_defaults(handler=h)\n") == ((), (H,), True)


def test_a_parameter_of_a_function_with_more_call_sites_than_the_program_reads_is_unread():
    def source(calls: int) -> str:
        return ("def register(sub):\n    sub.add_parser('a').set_defaults(handler=h)\n\n\ndef build():\n"
                + "    register(argparse.ArgumentParser().add_subparsers())\n" * calls)

    assert only(source(F.CALLERS))[2] is False
    assert only(source(F.CALLERS + 1))[2] is True


@pytest.mark.parametrize(("links", "unread"), [(5, False), (K.DEPTH + 10, True)])
def test_a_chain_of_names_is_followed_to_a_bounded_depth(links, unread):
    chain = "    n0 = sub\n" + "".join(f"    n{i} = n{i - 1}\n" for i in range(1, links + 1))
    found = only(top(chain + f"    n{links}.add_parser('a').set_defaults(handler=h)\n"))
    assert found[2] is unread


# ---------------------------------------------------------------------------------------------------- the handlers

def test_a_handler_is_the_function_a_name_or_a_wrapper_names_and_a_lambda_is_a_function_of_its_own():
    found = regs(top("    sub.add_parser('a').set_defaults(handler=h)\n"
                     "    sub.add_parser('b').set_defaults(handler=lambda a: h2(a))\n"
                     "    sub.add_parser('c').set_defaults(handler=functools.partial(h, 1))\n"))
    assert [handlers for _, handlers, _ in found] == [(H,), (("aew.m", "build.<handler1>"),), (H,)]


def test_a_lambda_handlers_calls_are_its_own_and_not_the_registering_functions():
    funcs = program(top("    sub.add_parser('b').set_defaults(handler=lambda a: h2(a))\n")).modules["aew.m"].funcs
    assert [ast.unparse(c.func) for c in funcs["build.<handler1>"].calls] == ["h2"]
    assert "h2" not in {ast.unparse(c.func) for c in funcs["build"].calls}


def test_handler_lambdas_of_one_function_are_numbered_in_source_order():
    funcs = program(top("    sub.add_parser('a').set_defaults(handler=lambda a: h(a))\n"
                        "    sub.add_parser('b').set_defaults(handler=lambda a: h2(a))\n")).modules["aew.m"].funcs
    assert [ast.unparse(c.func) for c in funcs["build.<handler2>"].calls] == ["h2"]


# ---------------------------------------------------------------------------------------------------------- the cut

def cut(source: str) -> Any:
    return K.cut_of(program(source), lambda path: "named" if path[:1] == ("lead",) else "general")


def test_each_roles_handlers_are_those_of_the_commands_it_runs():
    c = cut(top("    sub.add_parser('init').set_defaults(handler=h)\n"
                "    sub.add_parser('lead').set_defaults(handler=h2)\n"))
    assert c.handlers == {"general": {H}, "named": {H2}} and c.undecided == {}


def test_a_handler_of_a_command_that_cannot_be_read_is_undecided_under_the_function_that_registers_it():
    c = cut(top("    mystery(sub).add_parser('x').set_defaults(handler=h)\n"))
    assert c.handlers == {} and c.undecided == {("aew.m", "build"): {H}}


def test_a_registration_that_also_spells_a_path_it_cannot_read_has_both():
    c = cut(top("    for name in ('lead', MORE):\n        sub.add_parser(name).set_defaults(handler=h)\n"))
    assert c.handlers == {"named": {H}} and c.undecided == {("aew.m", "build"): {H}}


def test_the_roles_are_asked_of_the_owner_and_not_listed():
    def entry(argv: list[str], env: dict[str, str]) -> str:
        return "worker" if env.get("ENV") else ("named" if argv[:1] == ["lead"] else "general")

    roles = K.roles_of({"general", "named", "worker"}, entry, "ENV")
    assert (roles.general, roles.named, roles.worker) == ("general", frozenset({"named"}), "worker")
    assert roles.all == {"general", "named", "worker"}
