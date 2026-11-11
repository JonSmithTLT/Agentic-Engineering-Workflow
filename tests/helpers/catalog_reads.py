"""Enumerate direct off-only typed-catalog readers for a shared source/test guard.

This is syntax, not data-flow or a proof that every hit is wrong. It sees ``contract.TOOLS`` and calls to
``contract.tool``/``contract.exposed`` without switches, plus unaliased imports of those names. It does not follow
aliases, getattr, dynamic access or wrappers. It also does not detect ``contract.catalog()`` or ``check_call(...)``
called without switches (including their direct-import spellings). Callers classify intentional off snapshots and
metadata-only readers; the guard is not evidence that those other readers are switch-aware.
"""

from __future__ import annotations

import ast
from typing import NamedTuple


class CatalogRead(NamedTuple):
    scope: str
    expression: str


def off_only_reads(source: str) -> list[CatalogRead]:
    tree = ast.parse(source)
    direct = {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
              and node.module == "aew.surface.contract" for alias in node.names if alias.asname is None}
    found: list[CatalogRead] = []

    class Reader(ast.NodeVisitor):
        scope: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.scope.append(node.name)
            self.generic_visit(node)
            self.scope.pop()

        def record(self, node: ast.AST) -> None:
            found.append(CatalogRead(".".join(self.scope) or "<module>", ast.unparse(node)))

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if ast.unparse(node) == "contract.TOOLS" and isinstance(node.ctx, ast.Load):
                self.record(node)
            self.generic_visit(node)

        def visit_Name(self, node: ast.Name) -> None:
            if node.id == "TOOLS" and node.id in direct and isinstance(node.ctx, ast.Load):
                self.record(node)

        def visit_Call(self, node: ast.Call) -> None:
            name = ast.unparse(node.func)
            if name in {"contract.tool", "contract.exposed", *(n for n in ("tool", "exposed") if n in direct)}:
                if len(node.args) < 2 and not any(k.arg in ("switches", None) for k in node.keywords):
                    self.record(node)
            self.generic_visit(node)

    Reader().visit(tree)
    return found
