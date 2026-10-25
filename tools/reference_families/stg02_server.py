"""The ``stg02-routes`` family (STG-12 S12-2, family 6b, the designer's second addendum): the routes of the STG-02
wire and whether the slice's server serves them.

**The route list** is the vendored HTTP/Problem matrix (``aew.stg02.adopted.matrix()``): its distinct (method, route)
pairs, the D01 reads and the O01 command set and owner read (basis ``static``, because what matters about a record is
its ``served`` fact, read from the source; the list itself is enumerated from the vendored file).

**Whether a route is served** is read from ``aew/stg02/server.py``, whose dispatch is not a table: ``handle`` and
``_read`` are ``path ==`` and ``startswith`` chains, ``COMMANDS`` is a constant, and the owner read is a regex. The
reading collects every route-shaped string (one that starts with ``/``) that the module compares a path with, in any
function: a literal or a module constant on either side of ``==``, ``!=``, ``in`` or ``not in``; a literal given to
``startswith``; the prefixes of a literal tuple the loop in ``_read`` iterates; and the pattern of a compiled regex
given to ``fullmatch``, ``match`` or ``search``. Each is then tied to the matrix:

* an exact literal that is a route (no placeholder) serves it;
* a prefix serves a route when the route is the prefix followed by one placeholder (``/v1/read/runs/`` and
  ``/v1/read/runs/{execution_id}``);
* a regex serves a route when it is the route with each placeholder written ``([^/]*)``;
* a prefix that is the front of a route but does not end at a placeholder (``/v1/read/``, ``/o01/``) is a family prefix,
  which selects a handler and serves no route by itself;
* an exact literal under ``/_test/`` is a test-only route (served only with ``--test-routes``).

Anything else is an unresolved item, anchored at the server: a string the module compares a path with that the matrix
does not explain. ``stg02_server_text.py`` is the second, independently written detector, and the two agree on the
tree (``tests/integration/test_reference_stg02.py``). What neither sees (a route spelled by concatenation, a
comparison held in a variable, a regex built at run time, a route handled by a dict lookup) is pinned there, one probe
each, and an observed cross-check (a request to every matrix route, with the owners replaced by spies) reaches the
same served set.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from typing import Any, NamedTuple

from reference_families import common as C

FAMILY = "stg02-routes"
SERVER = "aew.stg02.server"
ADOPTED = "aew.stg02.adopted"
TEST_PREFIX = "/_test/"
_TESTS = "tests/integration/test_reference_stg02.py"
ROUTE_TESTS = (
    f"{_TESTS}::test_the_route_records_are_the_matrix_both_ways",
    f"{_TESTS}::test_the_two_server_detectors_agree_on_the_server",
    f"{_TESTS}::test_the_served_routes_are_the_ones_a_request_reaches_an_owner_through",
)
PLACEHOLDER = re.compile(r"\{[^}/]+\}")


class Reading(NamedTuple):
    exact: list[str]  # route-shaped strings a path is compared with
    prefixes: list[str]  # route-shaped strings given to startswith, and the prefixes of the loop in _read
    patterns: list[str]  # the text of a compiled regex a path is matched with
    test_methods: dict[str, str]  # a test route -> the method its branch requires


def _route(value: Any) -> str | None:
    return value if isinstance(value, str) and value.startswith("/") else None


def _strings(node: ast.AST, values: Mapping[str, Any]) -> list[str]:
    """The route-shaped strings an expression is made of: a literal, a module constant, or the elements of a tuple, list
    or set of them."""
    if isinstance(node, ast.Constant):
        found = _route(node.value)
        return [found] if found else []
    if isinstance(node, ast.Name):
        found = _route(values.get(node.id))
        return [found] if found else []
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [s for e in node.elts for s in _strings(e, values)]
    return []


class _Reader(ast.NodeVisitor):
    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = values
        self.exact: set[str] = set()
        self.prefixes: set[str] = set()
        self.patterns: set[str] = set()
        self.test_methods: dict[str, str] = {}

    def visit_Compare(self, node: ast.Compare) -> None:
        """A path equal to a route (either side of ``==``), or in a collection of routes (the right side of ``in``): a
        literal on the left of ``in`` is a substring test (``"/" not in rest``), not a route."""
        operands = [node.left, *node.comparators]
        for left, op, right in zip(operands, node.ops, operands[1:], strict=False):  # n operands, n - 1 operators
            if isinstance(op, (ast.Eq, ast.NotEq)):
                self.exact.update(_strings(left, self.values) + _strings(right, self.values))
            elif isinstance(op, (ast.In, ast.NotIn)):
                if isinstance(right, (ast.Tuple, ast.List, ast.Set)):
                    self.exact.update(_strings(right, self.values))
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """``method == "POST" and path in ("/_test/...")``: the method a test route requires."""
        methods: list[str] = []
        for v in node.values:
            if (isinstance(v, ast.Compare) and isinstance(v.left, ast.Name) and v.left.id == "method"
                    and len(v.comparators) == 1):
                (only,) = v.comparators
                if isinstance(only, ast.Constant) and isinstance(only.value, str):
                    methods.append(only.value)
        if methods:
            for v in node.values:
                if isinstance(v, ast.Compare):
                    for s in (s for part in (v.left, *v.comparators) for s in _strings(part, self.values)):
                        if s.startswith(TEST_PREFIX):
                            self.test_methods[s] = methods[0]
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.args:
            if node.func.attr == "startswith":
                self.prefixes.update(_strings(node.args[0], self.values))
            elif node.func.attr in ("fullmatch", "match", "search") and isinstance(node.func.value, ast.Name):
                pattern = self.values.get(node.func.value.id)
                found = _route(getattr(pattern, "pattern", None))
                if found is not None:
                    self.patterns.add(found)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """``for prefix, call, lo, hi in (("/v1/read/runs/", ...), ...)`` with ``path.startswith(prefix)`` in the
        body."""
        if (isinstance(node.target, ast.Tuple) and node.target.elts and isinstance(node.target.elts[0], ast.Name)
                and isinstance(node.iter, (ast.Tuple, ast.List))):
            name = node.target.elts[0].id
            uses = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "startswith"
                       and n.args and isinstance(n.args[0], ast.Name) and n.args[0].id == name
                       for stmt in node.body for n in ast.walk(stmt))
            if uses:
                for row in node.iter.elts:
                    if isinstance(row, ast.Tuple) and row.elts:
                        self.prefixes.update(_strings(row.elts[0], self.values))
        self.generic_visit(node)


def read(tree: ast.Module, values: Mapping[str, Any]) -> Reading:
    """The server module as the detector sees it; ``values`` resolves a module-level name (a constant or a regex)."""
    reader = _Reader(values)
    reader.visit(tree)
    return Reading(sorted(reader.exact), sorted(reader.prefixes), sorted(reader.patterns), dict(reader.test_methods))


def as_pattern(template: str) -> str:
    """The regex text of a route: each placeholder written as the server writes it, ``([^/]*)``."""
    return PLACEHOLDER.sub("([^/]*)", template)


class Served(NamedTuple):
    served: set[str]  # the matrix routes the reading ties to the server
    family: set[str]  # prefixes that select a handler and serve no route
    test_only: dict[str, str]  # a test route -> its method
    unresolved: list[str]  # route-shaped strings the matrix does not explain, with why


def tie(templates: list[str], reading: Reading) -> Served:
    served: set[str] = set()
    family: set[str] = set()
    unresolved: list[str] = []
    for literal in reading.exact:
        if literal in templates:
            served.add(literal)
        elif literal.startswith(TEST_PREFIX):
            continue
        elif not any(t.startswith(literal) for t in templates):
            unresolved.append(f"the module compares a path with {literal!r}, which is no route of the matrix")
    for prefix in reading.prefixes:
        tied = False
        for t in templates:
            if not t.startswith(prefix):
                continue
            tied = True
            if PLACEHOLDER.fullmatch(t[len(prefix):]):
                served.add(t)
            elif t != prefix:
                family.add(prefix)
        if not tied:
            unresolved.append(f"the module tests a path against the prefix {prefix!r}, which starts no route of "
                              "the matrix")
    for pattern in reading.patterns:
        matched = [t for t in templates if as_pattern(t) == pattern]
        if matched:
            served.update(matched)
        else:
            unresolved.append(f"the module matches a path with the pattern {pattern!r}, which is no route of "
                              "the matrix")
    return Served(served, family, {r: m for r, m in reading.test_methods.items()}, sorted(set(unresolved)))


def matrix_routes(matrix: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
    """The distinct (method, route) pairs of the vendored matrix, with the API each belongs to."""
    out: dict[tuple[str, str], str] = {}
    for row in matrix:
        key = (str(row["method"]).upper(), str(row["route"]))
        if out.setdefault(key, str(row["api"])) != str(row["api"]):
            raise C.ReferenceError(f"the vendored matrix names {key} under two APIs")
    return out


def build(ctx: C.Context) -> list[C.Record]:
    import importlib

    adopted = importlib.import_module(ADOPTED)
    server = importlib.import_module(SERVER)
    src = ctx.sources().get(SERVER)
    if src is None or src.tree is None:
        raise C.ReferenceError(f"{SERVER} cannot be read")
    routes = matrix_routes(adopted.matrix())
    reading = read(src.tree, vars(server))
    result = tie(sorted({route for _, route in routes}), reading)
    unresolved = [C.unresolved_item(SERVER, "handle", why) for why in result.unresolved]
    records = []
    for method, route in sorted(routes, key=lambda pair: (pair[1], pair[0])):
        fact = {"route": route, "method": method, "served": route in result.served, "test_only": False}
        records.append(C.Record(FAMILY, f"{method} {route}", ADOPTED, "matrix", "static",
                                C.lower_bound(unresolved), fact))
    for route, method in sorted(result.test_only.items()):
        fact = {"route": route, "method": method, "served": True, "test_only": True}
        records.append(C.Record(FAMILY, f"{method} {route}", SERVER, "handle", "static",
                                C.lower_bound(unresolved), fact))
    return records
