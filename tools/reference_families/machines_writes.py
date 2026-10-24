"""Where the product changes a state, and whether the transition table is consulted there (STG-12 S12-2, family 5).

``aew.engine.transitions.RULES`` is the Ticket machine's table, and ``check(frm, to, via)`` is how code asks it.
Nothing makes the engine ask: ``WorkUnits.set_state``, where a Lead decision or an event changes a Ticket's state and
the state hooks run, does not call ``check`` (its callers do), and some code assigns ``unit["state"]`` itself (its
docstring names three such writers). This module reads every such site with ``ast`` and says, per site, whether a
``transitions.check`` call (a call identified by where its callee was imported from, never by its name) is in the same
function. A site that has none is not proved to take only table edges; the ``transitions`` records say so, on the
edges the site can take (:data:`SITES`).

Two forms are sites:

* ``set_state``: a call of an attribute named ``set_state`` (an attribute call has no import to follow, so the name is
  what there is; ``tests/integration/test_reference_machine_writes.py`` pins that the package defines exactly one);
* ``assign``: an assignment to a subscript of the constant ``"state"``.

Not seen, and pinned by one probe each in that test: ``update(state=...)`` and ``update({"state": ...})``, a
``setattr``, a ``|=`` merge, and a key held in a variable. A unit built with an initial state is a creation, not a
transition.
``machines_writes_text.py`` is the second, independently written detector.
"""

from __future__ import annotations

import ast
from typing import NamedTuple

from reference_families import common as C

CHECK = "aew.engine.transitions.check"
SET_STATE, ASSIGN = "set_state", "assign"


class StateWrite(NamedTuple):
    module: str
    symbol: str | None
    form: str  # SET_STATE or ASSIGN
    checked: bool  # a call of transitions.check is in the same function


class _Assigns(C.Scoped):
    """The assignments to ``x["state"]``, each with the symbol it sits in."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[str | None] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value == "state"
               for t in node.targets):
            self.found.append(self.symbol)
        super().visit_Assign(node)


def writes_from(tree: ast.Module, index: C.Index, module: str) -> list[StateWrite]:
    """Every state-write site of a module, with whether the table is asked in the same function."""
    checks = {symbol for call, symbol in index.calls if index.aliases.resolve(call.func) == CHECK}
    sites = [StateWrite(module, symbol, SET_STATE, symbol in checks) for call, symbol in index.calls
             if isinstance(call.func, ast.Attribute) and call.func.attr == "set_state"]
    assigns = _Assigns()
    assigns.visit(tree)
    sites += [StateWrite(module, symbol, ASSIGN, symbol in checks) for symbol in assigns.found]
    return sites


def writes(tree: ast.Module, module: str, is_package: bool) -> list[StateWrite]:
    """:func:`writes_from` for a parsed tree on its own (the planted cases of the tests)."""
    return writes_from(tree, C.index_of(tree, module, is_package), module)


def tree_writes(ctx: C.Context) -> list[StateWrite]:
    found: list[StateWrite] = []
    for name, src in ctx.sources().items():
        if src.tree is not None:
            found += writes_from(src.tree, ctx.index(name), name)
    return sorted(found, key=lambda s: (s.module, s.symbol or "", s.form, s.checked))
