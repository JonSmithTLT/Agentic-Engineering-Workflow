"""The dashboard HTTP server: contract 0.1.2's routes on stdlib ``http.server`` (design note §4.10, §5.1).

GET and HEAD only, under ``/api/v1/``, bound to ``127.0.0.1``. One request is served at a time (the projections share
the engine's read collaborators), and each request projects one lock-free snapshot. Errors are the contract's
``Error`` object with a registered code; an engine exception's text goes to the server log, never to the client.

The server **requires an authenticator** (the enablement rule, designer 2026-10-05): the product's is the operator
session (``session.SessionTable``, F20.3), which also serves the one-time URL exchange at ``/session/<code>`` (design
note §4.3). Conditional requests (F20.4), the static build and the full header set (F20.5) come in their slices.
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from aew.dashboard import projections as P
from aew.dashboard import session as S
from aew.dashboard.contract import Contract
from aew.dashboard.cursors import CursorError
from aew.dashboard.reader import StateReader
from aew.dashboard.reasons import reason
from aew.engine.api import Engine
from aew.errors import AEWError, NotFound

LOG = logging.getLogger("aew.dashboard")
API_PREFIX = "/api/v1"
HOST = "127.0.0.1"
MAX_QUERY = 2048
SOCKET_TIMEOUT_S = 10.0
MAX_PATH = 2048
SESSION_PREFIX = "/session/"
SESSION_PATH = re.compile(r"^/session/[^/?#]+")
# The pages the one-time URL exchange answers with. They name no code and carry no data (R9).
GONE_PAGE = ("This dashboard link was already used, has expired, or was never issued. Run `aew dashboard open` at your "
             "terminal for a new one.")
CROSS_SITE_PAGE = ("This dashboard link is opened by you, from the address bar, not from another page or by a "
                   "prefetch. Paste it into the address bar of this browser; it is still valid.")


class Authenticator(Protocol):
    """Decides whether a request may read. ``None`` lets it through; an ``Error`` body refuses it with 401."""

    def authenticate(self, headers: Any) -> dict[str, Any] | None: ...


def error_body(code: str, message: str | None = None, reasons: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    r = reason(code, message)
    return {"code": r["code"], "message": r["message"], "reasons": reasons or []}


class Refusal(Exception):
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        super().__init__(body["message"])
        self.status = status
        self.body = body


Route = Callable[[P.Projector, dict[str, str], dict[str, str]], dict[str, Any]]


def _q(query: dict[str, str], name: str) -> str | None:
    return query.get(name)


ROUTES: dict[str, Route] = {
    "/project": lambda p, q, m: p.project(),
    "/capabilities": lambda p, q, m: p.capabilities(),
    "/overview": lambda p, q, m: p.overview(),
    "/history/integrity": lambda p, q, m: p.integrity(),
    "/work": lambda p, q, m: p.work_list(state=_q(q, "state"), kind=_q(q, "kind"), parent=_q(q, "parent"),
                                         limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
    "/work/{id}": lambda p, q, m: p.work(m["id"]),
    "/runs": lambda p, q, m: p.runs_list(limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
    "/runs/{id}": lambda p, q, m: p.run(m["id"]),
    "/evidence": lambda p, q, m: p.evidence_list(work=_q(q, "work"), limit=P.parse_limit(_q(q, "limit")),
                                                 cursor=_q(q, "cursor")),
    "/evidence/{id}": lambda p, q, m: p.evidence(m["id"]),
    "/knowledge": lambda p, q, m: p.knowledge_list(limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
    "/knowledge/{id}": lambda p, q, m: p.knowledge(m["id"]),
    "/history": lambda p, q, m: p.history_list(kind=_q(q, "kind"), since=_q(q, "since"), until=_q(q, "until"),
                                               limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
    "/history/{id}": lambda p, q, m: p.history(m["id"], annotations_cursor=_q(q, "annotations_cursor"),
                                               annotations_limit=P.parse_limit(_q(q, "annotations_limit"))),
    "/attention": lambda p, q, m: p.attention_list(limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
    "/activity": lambda p, q, m: p.activity_list(limit=P.parse_limit(_q(q, "limit")), cursor=_q(q, "cursor")),
}
# The query parameters each route accepts (the contract's, plus the detail route's annotation paging).
QUERY_PARAMETERS: dict[str, frozenset[str]] = {
    "/work": frozenset({"limit", "cursor", "state", "kind", "parent"}),
    "/runs": frozenset({"limit", "cursor"}),
    "/evidence": frozenset({"limit", "cursor", "work"}),
    "/knowledge": frozenset({"limit", "cursor"}),
    "/history": frozenset({"limit", "cursor", "kind", "since", "until"}),
    "/history/{id}": frozenset({"annotations_cursor", "annotations_limit"}),
    "/attention": frozenset({"limit", "cursor"}),
    "/activity": frozenset({"limit", "cursor"}),
}


def match_route(path: str) -> tuple[str, dict[str, str]] | None:
    """The contract route a request path names, and its ``{id}``."""
    if path in ROUTES and "{id}" not in path:
        return path, {}
    parts = path.split("/")
    if len(parts) == 3 and parts[0] == "" and parts[2]:
        template = f"/{parts[1]}/{{id}}"
        if template in ROUTES:
            return template, {"id": parts[2]}
    return None


class DashboardServer:
    """Serves one project's projections to authenticated readers on the loopback interface."""

    def __init__(self, engine: Engine, *, authenticator: Authenticator, port: int = 0,
                 validate_with: Contract | None = None, sessions: S.SessionTable | None = None) -> None:
        self.engine = engine
        self.reader = StateReader(engine)
        self.authenticator = authenticator
        self.sessions = sessions  # serves the one-time URL exchange; without a table `/session/` is no route
        self.contract = validate_with  # when set, every 200 body is checked before it leaves (the tests)
        self._serial = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "aew-dashboard"
            sys_version = ""
            timeout = SOCKET_TIMEOUT_S

            def handle(self) -> None:
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError, TimeoutError):
                    pass  # the client went away between keep-alive requests: nothing to answer

            def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
                server.handle(self, head=False)

            def do_HEAD(self) -> None:  # noqa: N802
                server.handle(self, head=True)

            def send_response(self, code: int, message: str | None = None) -> None:
                self.log_request(code)
                self.send_response_only(code, message)  # no Server or Date header

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (http.server's name)
                LOG.info("%s " + format, self.address_string(), *args)

            def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
                path = SESSION_PATH.sub("/session/<redacted>", self.path.split("?", 1)[0])
                LOG.info('%s "%s %s" %s', self.address_string(), self.command, path, code)

        self.httpd = ThreadingHTTPServer((HOST, port), Handler)
        self.httpd.daemon_threads = True
        self._thread = threading.Thread(target=self.httpd.serve_forever, name="aew-dashboard", daemon=True)

    # ---------------------------------------------------------------- lifecycle

    @property
    def port(self) -> int:
        return int(self.httpd.server_address[1])

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._thread.is_alive():
            self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread.is_alive():
            self._thread.join(10)

    # ---------------------------------------------------------------- requests

    def handle(self, h: BaseHTTPRequestHandler, *, head: bool) -> None:
        try:
            url = urlsplit(h.path)
            if self.sessions is not None and url.path.startswith(SESSION_PREFIX) and len(url.path) <= MAX_PATH:
                self._exchange(h, url.path[len(SESSION_PREFIX):], head=head)
                return
            status, body = self._respond(h, url)
        except Refusal as r:
            status, body = r.status, r.body
        except Exception:  # never let a request kill the server; the client learns only that it failed
            LOG.exception("dashboard request failed")
            status, body = HTTPStatus.INTERNAL_SERVER_ERROR, error_body("PROJECTION_FAILED")
        extra: list[tuple[str, str]] = []
        if status == HTTPStatus.UNAUTHORIZED and S.cookie_value(h.headers) is not None:
            extra.append(("Set-Cookie", S.expired_cookie()))  # a dead cookie is removed from the browser (R10)
        self._send(h, status, body, head=head, extra=extra)

    def _exchange(self, h: BaseHTTPRequestHandler, code: str, *, head: bool) -> None:
        """``GET /session/<code>``: the one-time URL becomes the session cookie (R9). A HEAD never spends a code."""
        assert self.sessions is not None
        if S.not_a_user_navigation(h.headers):  # cross-site, or a speculative prefetch: the code is not consumed
            self._page(h, HTTPStatus.FORBIDDEN, CROSS_SITE_PAGE, head=head)
            return
        got = self.sessions.exchange(code) if not head and code else None
        if got is None:
            self._page(h, HTTPStatus.GONE, GONE_PAGE, head=head)
            return
        credential, record = got
        h.send_response(int(HTTPStatus.SEE_OTHER))
        h.send_header("Location", "/")
        h.send_header("Set-Cookie", self.sessions.cookie(credential, record))
        h.send_header("Content-Length", "0")
        for name, value in self._common_headers():
            h.send_header(name, value)
        h.end_headers()

    def _page(self, h: BaseHTTPRequestHandler, status: int, text: str, *, head: bool) -> None:
        page = f'<!doctype html><meta charset="utf-8"><title>AEW dashboard</title><p>{html.escape(text)}</p>\n'
        payload = page.encode()
        h.send_response(int(status))
        h.send_header("Content-Type", "text/html; charset=utf-8")
        h.send_header("Content-Length", str(len(payload)))
        for name, value in self._common_headers():
            h.send_header(name, value)
        h.end_headers()
        if not head:
            h.wfile.write(payload)

    @staticmethod
    def _common_headers() -> list[tuple[str, str]]:
        return [("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                ("Referrer-Policy", "no-referrer")]

    def _respond(self, h: BaseHTTPRequestHandler, url: Any) -> tuple[int, dict[str, Any]]:
        if len(url.path) > MAX_PATH or len(url.query) > MAX_QUERY:
            raise Refusal(HTTPStatus.REQUEST_URI_TOO_LONG, error_body("REQUEST_TOO_LARGE"))
        if h.headers.get("Content-Length") not in (None, "0") or h.headers.get("Transfer-Encoding"):
            raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", "a read carries no body"))
        if not url.path.startswith(API_PREFIX + "/"):
            raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", "no such route"))
        found = match_route(url.path[len(API_PREFIX):])
        if found is None:
            raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", "no such route"))
        route, matched = found
        refused = self.authenticator.authenticate(h.headers)
        if refused is not None:
            raise Refusal(HTTPStatus.UNAUTHORIZED, refused)
        query = self._query(url.query, route)
        with self._serial:
            projector = P.Projector(self.reader.snapshot())
            try:
                body = ROUTES[route](projector, query, matched)
            except CursorError as exc:
                status = HTTPStatus.CONFLICT if exc.code == "CURSOR_EXPIRED" else HTTPStatus.BAD_REQUEST
                raise Refusal(status, error_body(exc.code, exc.message)) from None
            except P.InvalidRequest as exc:
                raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", exc.message)) from None
            except P.CapabilityUnavailable as exc:
                raise Refusal(HTTPStatus.FORBIDDEN, error_body("CAPABILITY_UNAVAILABLE", exc.message, exc.reasons)) \
                    from None
            except NotFound as exc:
                raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", exc.message)) from None
            except AEWError as exc:
                LOG.error("projection %s failed: %s %s", route, exc.code, exc.message)
                raise Refusal(HTTPStatus.INTERNAL_SERVER_ERROR, error_body("PROJECTION_FAILED")) from None
        body = P.scrub(body)
        if self.contract is not None:
            violations = self.contract.violations(self.contract.response_schema(route), body)
            if violations:
                LOG.error("projection %s violates the contract: %s", route, violations[:5])
                raise Refusal(HTTPStatus.INTERNAL_SERVER_ERROR, error_body("PROJECTION_FAILED"))
        return HTTPStatus.OK, body

    @staticmethod
    def _query(raw: str, route: str) -> dict[str, str]:
        allowed = QUERY_PARAMETERS.get(route, frozenset())
        parsed = parse_qs(raw, keep_blank_values=True, strict_parsing=False)
        out: dict[str, str] = {}
        for name, values in parsed.items():
            if name not in allowed:
                raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", f"unknown parameter {name}"))
            if len(values) != 1 or not values[0]:
                raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", f"parameter {name} given badly"))
            out[name] = values[0]
        return out

    @classmethod
    def _send(cls, h: BaseHTTPRequestHandler, status: int, body: dict[str, Any], *, head: bool,
              extra: list[tuple[str, str]] | None = None) -> None:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        h.send_response(int(status))
        h.send_header("Content-Type", "application/json; charset=utf-8")
        h.send_header("Content-Length", str(len(payload)))
        for name, value in cls._common_headers() + (extra or []):
            h.send_header(name, value)
        h.end_headers()
        if not head:
            h.wfile.write(payload)
