"""The ``dashboard-routes`` family (STG-12 S12-2, family 6): the routes the dashboard server answers.

Owner of the API routes: ``aew.dashboard.server`` (``ROUTES`` and ``CONDITIONAL_HANDLERS``, with ``QUERY_PARAMETERS``,
``REPEATABLE_PARAMETERS``, ``ROUTE_LIMITS`` and ``PRECHECKS`` keyed by route), imported at run time (basis
``enumerated``). One record per route template; ``/history/search`` is the one conditional route (answered only while
the adopted policy switches it on, else the ``/history/{id}`` template answers it).

**Why the API routes are complete-by-construction.** An ``/api/`` request reaches ``DashboardServer._respond``, which
finds its route by ``match_route`` (over ``ROUTES``) and calls ``ROUTES.get(route) or CONDITIONAL_HANDLERS[route]``. The
check is that this is the only place a route table is called, and that the functions which name either table are the
three declared in :data:`REFERENCES` (read by two independent detectors, ``interfaces_dashboard_text.py`` the second): a
route served any other way would have to name a table somewhere else.

**What is not an API route.** ``DashboardServer._handle`` tests the path before it reaches the API: a path under the
session prefix is the one-time URL exchange, and any path outside ``/api/`` is the static frontend (with its
single-page-app fallback). Those branches are read from ``_handle`` itself, by the same two detectors, and recorded as
routes of their own (basis ``static``). The HTTP methods are the ``do_`` methods of the server's request handler; any
other method is refused with 405 by its ``__getattr__``.

Not seen, and pinned by one probe each in ``tests/integration/test_reference_dashboard_routes.py``: a handler taken out
of a table into a variable in a function that is not declared (the function still names the table, so it is *reported*,
never passed over), a table reached by ``getattr`` or from another module's alias (the second is a different module's
reading), and a branch of ``_handle`` whose test is not ``url.path.startswith(...)``.
"""

from __future__ import annotations

import ast
from typing import Any, NamedTuple

from reference_families import common as C

FAMILY = "dashboard-routes"
SERVER = "aew.dashboard.server"
OWNER_CLASS = "DashboardServer"
HANDLE = f"{OWNER_CLASS}._handle"
REGISTRY = f"{SERVER}:ROUTES"
TABLES = ("ROUTES", "CONDITIONAL_HANDLERS")
# The functions that name a route table, by table: the dispatch (``_respond``), the route matcher and the pending-route
# derivation. Held to the tree in both directions by ``tests/integration/test_reference_dashboard_routes.py``.
REFERENCES: dict[str, tuple[str, ...]] = {
    "ROUTES": ("DashboardServer._respond", "match_route", "pending_routes"),
    "CONDITIONAL_HANDLERS": ("DashboardServer._respond",),
}
_TESTS = "tests/integration/test_reference_dashboard_routes.py"
ROUTE_TESTS = (
    f"{_TESTS}::test_the_route_records_are_the_server_tables_both_ways",
    f"{_TESTS}::test_the_route_tables_are_named_only_where_the_dispatch_and_the_matcher_are",
    f"{_TESTS}::test_the_two_dashboard_detectors_agree_on_the_server",
)
STATIC = "static"


class Branch(NamedTuple):
    prefix: str | None  # the path prefix the branch tests, resolved; None when it cannot be read
    negated: bool  # ``not url.path.startswith(prefix)``
    handler: str | None  # the method of the server the branch calls


class Reading(NamedTuple):
    branches: list[Branch]
    fallthrough: str | None  # the method an ``/api/`` request is handed to after the branches
    methods: list[str]  # the HTTP methods of the request handler (its ``do_`` methods)
    references: list[tuple[str, str]]  # (table, symbol) for every name of a route table in a function


def _is_url_path(node: ast.AST) -> bool:
    return C.dotted(node) == "url.path"


def _startswith_test(test: ast.expr) -> tuple[ast.expr, bool] | None:
    """The argument of a ``url.path.startswith(arg)`` test and whether it is negated, or None for any other test."""
    negated = False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        negated, test = True, test.operand
    if (isinstance(test, ast.Call) and isinstance(test.func, ast.Attribute) and test.func.attr == "startswith"
            and _is_url_path(test.func.value) and len(test.args) == 1):
        return test.args[0], negated
    return None


def _self_call(stmt: ast.stmt) -> str | None:
    """``self.name(...)`` as a statement (``self.name(...)``, or ``x = self.name(...)``): the name."""
    value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign)) else None
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name)
            and value.func.value.id == "self"):
        return value.func.attr
    return None


class _Refs(C.Scoped):
    def __init__(self) -> None:
        super().__init__()
        self.found: list[tuple[str, str]] = []
        self.methods: list[str] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in TABLES:
            self.found.append((node.id, self.symbol or ""))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("do_") and node.name[3:].isupper():
            self.methods.append(node.name[3:])
        super().visit_FunctionDef(node)


def read(tree: ast.Module, constants: dict[str, str]) -> Reading:
    """The server module as the detector sees it. ``constants`` resolves a module-level name a branch tests against."""
    refs = _Refs()
    refs.visit(tree)
    branches: list[Branch] = []
    fallthrough: str | None = None
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == OWNER_CLASS):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_handle"):
            for node in ast.walk(fn):
                if not isinstance(node, ast.If):
                    continue
                found = _startswith_test(node.test)
                if found is None:
                    continue
                arg, negated = found
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    prefix = arg.value
                elif isinstance(arg, ast.Name):
                    prefix = constants.get(arg.id)
                else:
                    prefix = None
                handler = next((name for stmt in node.body if (name := _self_call(stmt)) is not None), None)
                branches.append(Branch(prefix, negated, handler))
            for stmt in (s for n in ast.walk(fn) if isinstance(n, ast.Try) for s in n.body):
                if isinstance(stmt, ast.Assign) and _self_call(stmt) is not None:
                    fallthrough = _self_call(stmt)
    return Reading(branches, fallthrough, sorted(set(refs.methods)), sorted(set(refs.found)))


def routes_of(ctx: C.Context) -> Reading:
    import importlib

    server = importlib.import_module(SERVER)
    src = ctx.sources().get(SERVER)
    if src is None or src.tree is None:
        raise C.ReferenceError(f"{SERVER} cannot be read")
    constants = {n: v for n, v in vars(server).items() if isinstance(v, str) and n.isupper()}
    return read(src.tree, constants)


def build(ctx: C.Context) -> list[C.Record]:
    import importlib

    server = importlib.import_module(SERVER)
    reading = routes_of(ctx)
    methods = reading.methods
    method_cov = C.lower_bound([])  # found by a detector; the other methods are refused by ``__getattr__``
    tables = {"ROUTES": dict(server.ROUTES), "CONDITIONAL_HANDLERS": dict(server.CONDITIONAL_HANDLERS)}
    records: list[C.Record] = []
    for table, entries in tables.items():
        for route in sorted(entries):
            fact: dict[str, Any] = {
                "route": route, "path": server.API_PREFIX + route, "methods": methods,
                "conditional": table == "CONDITIONAL_HANDLERS", "prechecked": route in server.PRECHECKS,
                "query": sorted(server.QUERY_PARAMETERS.get(route, ()))}
            fact_coverage = {"methods": method_cov, "query": C.complete(f"{SERVER}:QUERY_PARAMETERS", ROUTE_TESTS)}
            repeatable = sorted(server.REPEATABLE_PARAMETERS.get(route, ()))
            if repeatable:  # a list fact is on the record only when the route has one
                fact["repeatable"] = repeatable
                fact_coverage["repeatable"] = C.complete(f"{SERVER}:REPEATABLE_PARAMETERS", ROUTE_TESTS)
            if route in server.ROUTE_LIMITS:
                default, maximum = server.ROUTE_LIMITS[route]
                fact["limit"] = {"default": default, "max": maximum}
            records.append(C.Record(FAMILY, route, SERVER, table, "enumerated",
                                    C.complete(f"{SERVER}:{table}", ROUTE_TESTS), fact,
                                    fact_coverage=fact_coverage))
    # the branches of _handle that are not the API, read from the source
    positive = [b for b in reading.branches if not b.negated]
    negative = [b for b in reading.branches if b.negated]
    unreadable = [C.unresolved_item(SERVER, HANDLE, "a branch of _handle tests a path prefix this reading cannot "
                                    "resolve")
                  for b in reading.branches if b.prefix is None]
    for b in positive:
        if b.prefix is None:
            continue
        key = f"{b.prefix}{{rest}}"
        records.append(C.Record(FAMILY, key, SERVER, HANDLE, "static", C.lower_bound(unreadable),
                                {"route": key, "path": key, "methods": methods, "api": False, "handler": b.handler,
                                 "under": b.prefix},
                                fact_coverage={"methods": method_cov}))
    if negative:
        outside = sorted({b.prefix for b in reading.branches if b.prefix is not None})
        key = "/{file}"
        records.append(C.Record(FAMILY, key, SERVER, HANDLE, "static", C.lower_bound(unreadable),
                                {"route": key, "path": key, "methods": methods, "api": False,
                                 "handler": negative[0].handler, "outside": outside},
                                fact_coverage={"methods": method_cov, "outside": C.lower_bound(unreadable)}))
    return records
