"""The ``dashboard-routes`` family (STG-12 S12-2, family 6): the routes the dashboard server answers.

Owner of the API routes: ``aew.dashboard.server`` (``ROUTES`` and ``CONDITIONAL_HANDLERS``, with ``QUERY_PARAMETERS``,
``REPEATABLE_PARAMETERS``, ``ROUTE_LIMITS`` and ``PRECHECKS`` keyed by route), imported at run time (basis
``enumerated``). One record per route template; ``/history/search`` is the one conditional route (answered only while
the adopted policy switches it on, else the ``/history/{id}`` template answers it).

**Why the API routes are complete-by-construction.** An ``/api/`` request reaches ``DashboardServer._respond``, which
finds its route by ``match_route`` (over ``ROUTES``) and calls
``ROUTES.get(route) or CONDITIONAL_HANDLERS[route]``. Three things are held to the tree, each read by two independent
detectors (``interfaces_dashboard_text.py`` the second): the functions that name either table are the three declared in
:data:`REFERENCES`; the one call out of a table is that expression (:func:`dispatch_calls`); and every read of the
request path (``url.path``, ``h.path``) in ``_handle`` and ``_respond`` is one of the declared reads, by its form (the
path, a slice of it, a ``startswith`` on it) and what consumes it (:data:`PATH_READS`, a count of each). A route served
by a hand-written branch, an early return, a test on the raw target or a third table would have to read the request
path or name a table in one of those two functions, so it is a difference.

**The limit of that.** A test of the path inside a function that ``_handle`` or ``_respond`` calls (``_admit``,
``_conditional``, ``_exchange``, ``_static``, ``match_route``) is not read. A read is counted by its form and consumer:
one replaced by another of the same form and consumer (``in CONDITIONAL_ROUTES`` for ``in EXTRA``) is not seen. A table
reached through ``getattr`` or ``vars`` is not seen either. The pins that show these are in
``tests/unit/test_reference_interface_controls.py``, one probe each.

**What is not an API route.** ``DashboardServer._handle`` tests the path before it reaches the API: a path under the
session prefix is the one-time URL exchange, and any path outside ``/api/`` is the static frontend (with its
single-page-app fallback). Those branches are read from ``_handle`` itself, by the same two detectors, and recorded as
routes of their own (basis ``static``), with the attribute of the server each is answered only while it is set (the
session store, the static root). The HTTP methods are the ``do_`` methods of the server's request handler.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any, NamedTuple

from reference_families import common as C

FAMILY = "dashboard-routes"
SERVER = "aew.dashboard.server"
OWNER_CLASS = "DashboardServer"
HANDLE = f"{OWNER_CLASS}._handle"
REGISTRY = f"{SERVER}:ROUTES"
TABLES = ("ROUTES", "CONDITIONAL_HANDLERS")
TABLE_READS = ("get", "items", "keys", "values")  # reading a table is not calling a handler out of it
# The functions that name a route table, by table: the dispatch (``_respond``), the route matcher and the pending-route
# derivation. Held to the tree in both directions by ``tests/integration/test_reference_dashboard_routes.py``.
REFERENCES: dict[str, tuple[str, ...]] = {
    "ROUTES": ("DashboardServer._respond", "match_route", "pending_routes"),
    "CONDITIONAL_HANDLERS": ("DashboardServer._respond",),
}
BASES = ("url.path", "h.path")
CHECKED = ("_handle", "_respond")
# Every read of the request path in the checked methods: (method, base, form, consumer), each as many times as it is
# read. A form is ``bare`` (the path), ``slice`` (a slice of it), ``startswith`` (a prefix test on it) or ``any`` (any
# other use); a consumer is the argument of a ``startswith``, ``call:<callee>``, ``compare:<operator>:<other side>``
# (a name, a dotted name or a literal; else ``<expr>``), ``assign`` or ``other``.
PATH_READS: tuple[tuple[str, str, str, str], ...] = (
    ("DashboardServer._handle", "h.path", "bare", "call:urlsplit"),
    ("DashboardServer._handle", "url.path", "bare", "call:self._static"),
    ("DashboardServer._handle", "url.path", "slice", "call:self._exchange"),
    ("DashboardServer._handle", "url.path", "startswith", "'/api/'"),
    ("DashboardServer._handle", "url.path", "startswith", "SESSION_PREFIX"),
    ("DashboardServer._respond", "url.path", "bare", "call:E.scope"),
    ("DashboardServer._respond", "url.path", "slice", "call:match_route"),
    ("DashboardServer._respond", "url.path", "slice", "compare:In:CONDITIONAL_ROUTES"),
    ("DashboardServer._respond", "url.path", "startswith", "API_PREFIX + '/'"),
)
_TESTS = "tests/integration/test_reference_dashboard_routes.py"
ROUTE_TESTS = (
    f"{_TESTS}::test_the_route_records_are_the_server_tables_both_ways",
    f"{_TESTS}::test_the_route_tables_are_named_only_where_the_dispatch_and_the_matcher_are",
    f"{_TESTS}::test_every_read_of_the_request_path_in_the_handler_and_the_dispatch_is_a_declared_one",
    f"{_TESTS}::test_the_two_dashboard_detectors_agree_on_the_server",
    f"{_TESTS}::test_a_limit_the_record_states_is_the_one_the_server_normalises_with",
)
STATIC = "static"


class Branch(NamedTuple):
    prefix: str | None  # the path prefix the branch tests, resolved; None when it cannot be read
    negated: bool  # ``not url.path.startswith(prefix)``
    handler: str | None  # the method of the server the branch calls
    needs: str | None  # the attribute of the server the branch is answered only while it is not None


class Reading(NamedTuple):
    branches: list[Branch]
    fallthrough: str | None  # the method an ``/api/`` request is handed to after the branches
    methods: list[str]  # the HTTP methods of the request handler (its ``do_`` methods)
    references: list[tuple[str, str]]  # (table, symbol) for every name of a route table in a function
    path_reads: list[tuple[str, str, str, str]]  # every read of the request path in the checked methods


def norm(text: str) -> str:
    """Quotes and spacing made one way, so that two readings of an expression spell it alike."""
    return " ".join(text.replace('"', "'").split())


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


def _needs(stmts: list[ast.stmt]) -> str | None:
    """The attribute of ``self`` the first ``if self.x is None`` of these statements tests: what a branch needs set."""
    for stmt in stmts:
        for node in ast.walk(stmt):
            if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1
                    and isinstance(node.test.ops[0], ast.Is) and isinstance(node.test.comparators[0], ast.Constant)
                    and node.test.comparators[0].value is None):
                name = C.dotted(node.test.left)
                if name is not None and name.startswith("self.") and name.count(".") == 1:
                    return name.split(".", 1)[1]
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


def _other_side(node: ast.expr) -> str:
    """The other side of a comparison with the path, when it is a name, a dotted name or a literal."""
    if isinstance(node, (ast.Name, ast.Attribute)) and C.dotted(node):
        return str(C.dotted(node))
    if isinstance(node, ast.Constant):
        return norm(ast.unparse(node))
    return "<expr>"


class _PathReads(ast.NodeVisitor):
    """Every read of the request path in one method: its form and what consumes it. A read is classified by the node
    that consumes it (a call, a comparison, an assignment, a ``startswith``), and one nothing claims is ``any`` /
    ``other``."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.found: list[tuple[str, str, str, str]] = []
        self.claimed: set[tuple[int, int]] = set()  # (line, column) of the path attributes already classified

    def _base(self, node: ast.expr) -> tuple[str, str, ast.expr] | None:
        target, form = (node.value, "slice") if isinstance(node, ast.Subscript) else (node, "bare")
        name = C.dotted(target)
        return (name, form, target) if name in BASES else None

    def _add(self, base: str, form: str, consumer: str, where: ast.expr) -> None:
        self.found.append((self.symbol, base, form, consumer))
        self.claimed.add((where.lineno, where.col_offset))

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "startswith" and C.dotted(func.value) in BASES \
                and len(node.args) == 1:
            self._add(str(C.dotted(func.value)), "startswith", norm(ast.unparse(node.args[0])), func.value)
        else:
            callee = norm(ast.unparse(func))
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                got = self._base(arg)
                if got is not None:
                    self._add(got[0], got[1], f"call:{callee}", got[2])
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        operands = [node.left, *node.comparators]
        for op, left, right in zip(node.ops, operands, operands[1:], strict=False):
            for here, other in ((left, right), (right, left)):
                got = self._base(here)
                if got is not None:
                    self._add(got[0], got[1], f"compare:{type(op).__name__}:{_other_side(other)}", got[2])
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        got = self._base(node.value)
        if got is not None:
            self._add(got[0], got[1], "assign", got[2])
        self.generic_visit(node)

    def rest(self, fn: ast.FunctionDef) -> None:
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and C.dotted(node) in BASES \
                    and (node.lineno, node.col_offset) not in self.claimed:
                self.found.append((self.symbol, str(C.dotted(node)), "any", "other"))


def path_reads_of(fn: ast.FunctionDef, symbol: str) -> list[tuple[str, str, str, str]]:
    reads = _PathReads(symbol)
    reads.visit(fn)
    reads.rest(fn)
    return reads.found


def read(tree: ast.Module, constants: Mapping[str, str]) -> Reading:
    """The server module as the detector sees it. ``constants`` resolves a module-level name a branch tests against."""
    refs = _Refs()
    refs.visit(tree)
    branches: list[Branch] = []
    fallthrough: str | None = None
    reads: list[tuple[str, str, str, str]] = []
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == OWNER_CLASS):
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        for name in CHECKED:
            if name in methods:
                reads += path_reads_of(methods[name], f"{OWNER_CLASS}.{name}")
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
                needs = _needs(node.body) or (_needs(methods[handler].body) if handler in methods else None)
                branches.append(Branch(prefix, negated, handler, needs))
            for stmt in (s for n in ast.walk(fn) if isinstance(n, ast.Try) for s in n.body):
                if isinstance(stmt, ast.Assign) and _self_call(stmt) is not None:
                    fallthrough = _self_call(stmt)
    return Reading(branches, fallthrough, sorted(set(refs.methods)), sorted(set(refs.found)), sorted(reads))


def path_read_problems(reading: Reading, declared: tuple[tuple[str, str, str, str], ...] = PATH_READS) -> list[str]:
    """The reads of the request path held to the declared ones, in both directions and by count."""
    want, got = sorted(declared), list(reading.path_reads)
    problems = []
    for item in sorted(set(got)):
        if got.count(item) > want.count(item):
            problems.append(f"{item[0]} reads the request path ({item[1]}, {item[2]}, {item[3]}) "
                            f"{got.count(item)} time(s); {want.count(item)} are declared")
    for item in sorted(set(want)):
        if want.count(item) > got.count(item):
            problems.append(f"{item[0]} is declared to read the request path ({item[1]}, {item[2]}, {item[3]}) "
                            f"{want.count(item)} time(s) and reads it {got.count(item)}")
    return problems


def dispatch_calls(tree: ast.Module) -> list[str]:
    """The calls in the module that call a handler out of a route table: a call whose callee names a table, other than
    reading the table (``ROUTES.get(...)`` on its own, ``.items()``). The dispatch is the one such call."""
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and any(isinstance(n, ast.Name) and n.id in TABLES
                                                    for n in ast.walk(node.func))):
            continue
        reads_a_table = (isinstance(node.func, ast.Attribute) and node.func.attr in TABLE_READS
                         and isinstance(node.func.value, ast.Name) and node.func.value.id in TABLES)
        if not reads_a_table:
            found.append(ast.unparse(node.func))
    return sorted(found)


def routes_of(ctx: C.Context) -> Reading:
    import importlib

    server = importlib.import_module(SERVER)
    src = ctx.sources().get(SERVER)
    if src is None or src.tree is None:
        raise C.ReferenceError(f"{SERVER} cannot be read")
    constants = {n: v for n, v in vars(server).items() if isinstance(v, str) and n.isupper()}
    return read(src.tree, constants)


def limit_bounds(server: Any, route: str, query: list[str]) -> dict[str, Any] | None:
    """The bounds the server normalises a route's limit parameter with: its own (``ROUTE_LIMITS``) or the server's
    default (the projections' ``LIMIT_DEFAULT`` and ``LIMIT_MAX``). None for a route with no limit parameter."""
    from aew.dashboard import projections

    if not (set(query) & set(server.LIMIT_PARAMETERS)):
        return None
    if route in server.ROUTE_LIMITS:
        default, maximum = server.ROUTE_LIMITS[route]
        return {"default": default, "max": maximum, "source": "route"}
    return {"default": projections.LIMIT_DEFAULT, "max": projections.LIMIT_MAX, "source": "server default"}


def build(ctx: C.Context) -> list[C.Record]:
    import importlib

    server = importlib.import_module(SERVER)
    reading = routes_of(ctx)
    methods = reading.methods
    method_cov = C.lower_bound([])  # found by a detector; the other methods are refused by ``__getattr__``
    problems = [C.unresolved_item(SERVER, HANDLE, why) for why in path_read_problems(reading)]
    tables = {"ROUTES": dict(server.ROUTES), "CONDITIONAL_HANDLERS": dict(server.CONDITIONAL_HANDLERS)}
    tree = ctx.sources()[SERVER].tree
    dispatch = dispatch_calls(tree) if tree is not None else []
    if len(dispatch) != 1:
        problems.append(C.unresolved_item(SERVER, f"{OWNER_CLASS}._respond",
                                          f"{len(dispatch)} calls out of a route table are read; the dispatch is one"))
    records: list[C.Record] = []
    for table, entries in tables.items():
        for route in sorted(entries):
            query = sorted(server.QUERY_PARAMETERS.get(route, ()))
            fact: dict[str, Any] = {
                "route": route, "path": server.API_PREFIX + route, "methods": methods,
                "conditional": table == "CONDITIONAL_HANDLERS", "prechecked": route in server.PRECHECKS,
                "query": query}
            fact_coverage = {"methods": method_cov, "query": C.complete(f"{SERVER}:QUERY_PARAMETERS", ROUTE_TESTS)}
            repeatable = sorted(server.REPEATABLE_PARAMETERS.get(route, ()))
            if repeatable:  # a list fact is on the record only when the route has one
                fact["repeatable"] = repeatable
                fact_coverage["repeatable"] = C.complete(f"{SERVER}:REPEATABLE_PARAMETERS", ROUTE_TESTS)
            bounds = limit_bounds(server, route, query)
            if bounds is not None:
                fact["limit"] = bounds
            coverage = C.lower_bound(problems) if problems else C.complete(f"{SERVER}:{table}", ROUTE_TESTS)
            records.append(C.Record(FAMILY, route, SERVER, table, "enumerated", coverage, fact,
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
                                 "under": b.prefix, "conditional": b.needs is not None, "needs": b.needs},
                                fact_coverage={"methods": method_cov}))
    if negative:
        outside = sorted({b.prefix for b in reading.branches if b.prefix is not None})
        key = "/{file}"
        records.append(C.Record(FAMILY, key, SERVER, HANDLE, "static", C.lower_bound(unreadable),
                                {"route": key, "path": key, "methods": methods, "api": False,
                                 "handler": negative[0].handler, "outside": outside,
                                 "conditional": negative[0].needs is not None, "needs": negative[0].needs},
                                fact_coverage={"methods": method_cov, "outside": C.lower_bound(unreadable)}))
    return records
