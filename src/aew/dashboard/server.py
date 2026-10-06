"""The dashboard HTTP server: contract 0.1.2's routes on stdlib ``http.server`` (design note §4.10, §5.1).

GET and HEAD only, bound to ``127.0.0.1``: the API under ``/api/v1/``, the one-time URL exchange under ``/session/``,
and the frontend's production build everywhere else (:mod:`aew.dashboard.frontend`, with the SPA fallback for deep
links). One projection is built at a time (the projections share the engine's read collaborators), and each request
projects one lock-free snapshot. Errors are the contract's ``Error`` object with a registered code; an engine
exception's text goes to the server log, never to the client.

Server security (F20.5, design note §4.14): every response carries R21's header set and never a CORS header, a
``Server`` or a ``Date``. Before any routing, ``Host`` must be exactly ``127.0.0.1:<bound port>`` (else ``421``) and a
present ``Origin`` exactly ``http://127.0.0.1:<bound port>`` (else ``403``), which defeats DNS rebinding; on the API a
present ``Sec-Fetch-Site`` must be ``same-origin`` or ``none``. Requests are bounded (R23): methods, bodies, the
request line, the header count and size, the path, the query, and at most 16 requests in flight. The request log
(standard error, through the ``aew.dashboard`` logger) records the method, the path with ``/session/`` codes
redacted, the status and the milliseconds: never a query string, a header or a cookie.

The server **requires an authenticator** (the enablement rule, designer 2026-10-05): the product's is the operator
session (``session.SessionTable``, F20.3), which also serves the one-time URL exchange at ``/session/<code>`` (design
note §4.3). Every ``200`` carries a strong ``ETag`` over the representation and its scope, and a request whose
``If-None-Match`` names it is a ``304`` with no body (F20.4, :mod:`aew.dashboard.etag`).
"""

from __future__ import annotations

import html
import json
import logging
import re
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from aew.dashboard import etag as E
from aew.dashboard import frontend as ST
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
MAX_REQUEST_LINE = 4096
MAX_HEADER_LINES = 64
MAX_HEADER_BYTES = 16 * 1024
MAX_IN_FLIGHT = 16
ALLOWED_METHODS = "GET, HEAD"
# R21: on every response, static and API alike.
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                                "img-src 'self' data:; font-src 'self'; object-src 'none'; base-uri 'none'; "
                                "frame-ancestors 'none'; form-action 'none'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
)
SAME_SITE_FETCH = frozenset({"same-origin", "none"})
# The status a stdlib parse refusal (``send_error``) becomes, as the contract's Error.
PARSE_ERRORS = {HTTPStatus.REQUEST_URI_TOO_LONG: "REQUEST_TOO_LARGE",
                HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE: "REQUEST_TOO_LARGE",
                HTTPStatus.METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
                HTTPStatus.NOT_IMPLEMENTED: "METHOD_NOT_ALLOWED"}
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


LIMIT_PARAMETERS = frozenset({"limit", "annotations_limit"})


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
                 validate_with: Contract | None = None, sessions: S.SessionTable | None = None,
                 static_root: Path | None = None) -> None:
        self.engine = engine
        self.reader = StateReader(engine)
        self.authenticator = authenticator
        self.sessions = sessions  # serves the one-time URL exchange; without a table `/session/` is no route
        self.contract = validate_with  # when set, every 200 body is checked before it leaves (the tests)
        # The frontend: an unpacked build (``serve --static DIR``) or the packaged one; without either, only the API.
        self.static_root = static_root if static_root is not None else ST.packaged_root()
        self._serial = threading.Lock()
        self._slots = threading.BoundedSemaphore(MAX_IN_FLIGHT)
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

            def parse_request(self) -> bool:
                self.started = time.monotonic()
                if not super().parse_request():
                    return False
                if not self.request_version.startswith("HTTP/1."):  # HTTP/0.9 has no headers to carry R21's set
                    self.send_error(HTTPStatus.HTTP_VERSION_NOT_SUPPORTED)
                    return False
                if len(self.raw_requestline) > MAX_REQUEST_LINE:
                    self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                    return False
                lines = self.headers.items()
                if len(lines) > MAX_HEADER_LINES or sum(len(k) + len(v) + 4 for k, v in lines) > MAX_HEADER_BYTES:
                    self.send_error(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE)
                    return False
                return True

            def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
                server.handle(self, head=False)

            def do_HEAD(self) -> None:  # noqa: N802
                server.handle(self, head=True)

            def __getattr__(self, name: str) -> Any:
                if name.startswith("do_"):  # every other method: 405, never stdlib's 501 page
                    return lambda: server.refuse(self, HTTPStatus.METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED",
                                                 close=True)
                raise AttributeError(name)

            def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
                # stdlib's parse refusals (a bad request line, too long, too many headers, a bad version): the
                # contract's Error with the full header set, never its HTML page or the request line in a log.
                status = HTTPStatus(code)
                if not str(getattr(self, "request_version", "")).startswith("HTTP/1."):
                    self.request_version = self.protocol_version  # answer with a status line and the headers
                server.refuse(self, status, PARSE_ERRORS.get(status, "INVALID_REQUEST"), close=True)

            def send_response(self, code: int, message: str | None = None) -> None:
                self.log_request(code)
                self.send_response_only(code, message)  # no Server or Date header

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (http.server's name)
                pass  # stdlib's messages can carry the request line (a query); the request log is log_request

            def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
                raw = getattr(self, "path", None) or "-"
                path = SESSION_PATH.sub("/session/<redacted>", raw.split("?", 1)[0])[:256]
                ms = (time.monotonic() - getattr(self, "started", time.monotonic())) * 1000
                LOG.info("%s %s %s %.0fms", getattr(self, "command", None) or "-", path, int(code), ms)

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

    def refuse(self, h: BaseHTTPRequestHandler, status: int, code: str, *, close: bool = False,
               extra: list[tuple[str, str]] | None = None) -> None:
        """An ``Error`` response outside routing. ``close``: the connection ends with it (its request may carry
        bytes this server did not read)."""
        headers = list(extra or [])
        if status == HTTPStatus.METHOD_NOT_ALLOWED:
            headers.append(("Allow", ALLOWED_METHODS))
        if close:
            headers.append(("Connection", "close"))
        self._send(h, status, error_body(code), head=getattr(h, "command", None) == "HEAD", extra=headers)

    def handle(self, h: BaseHTTPRequestHandler, *, head: bool) -> None:
        if not self._slots.acquire(blocking=False):
            self.refuse(h, HTTPStatus.SERVICE_UNAVAILABLE, "SERVER_BUSY", extra=[("Retry-After", "1")])
            return
        try:
            self._handle(h, head=head)
        finally:
            self._slots.release()

    def _handle(self, h: BaseHTTPRequestHandler, *, head: bool) -> None:
        tag: str | None = None
        try:
            url = urlsplit(h.path)
            self._admit(h, url)
            if url.path.startswith(SESSION_PREFIX):  # reserved: the exchange, or no route (never the SPA fallback)
                if self.sessions is None:
                    raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", "no such route"))
                self._exchange(h, url.path[len(SESSION_PREFIX):], head=head)
                return
            if not url.path.startswith("/api/"):
                self._static(h, url.path, head=head)
                return
            status, body, tag = self._respond(h, url)
        except Refusal as r:
            status, body = r.status, r.body
        except Exception:  # never let a request kill the server; the client learns only that it failed
            LOG.exception("dashboard request failed")
            status, body = HTTPStatus.INTERNAL_SERVER_ERROR, error_body("PROJECTION_FAILED")
        extra: list[tuple[str, str]] = []
        if h.close_connection:
            extra.append(("Connection", "close"))  # its request carried bytes that were never read
        if tag is not None:  # a 200: conditional (R19)
            if E.matches(h.headers.get("If-None-Match"), tag):
                self._not_modified(h, tag)
                return
            extra.append(("ETag", tag))
        if status == HTTPStatus.UNAUTHORIZED and S.cookie_value(h.headers) is not None:
            extra.append(("Set-Cookie", S.expired_cookie()))  # a dead cookie is removed from the browser (R10)
        self._send(h, status, body, head=head, extra=extra)

    def _admit(self, h: BaseHTTPRequestHandler, url: Any) -> None:
        """The checks before any routing (R22, R23): the exact origin, the request's size, no body."""
        if h.headers.get("Host") != f"{HOST}:{self.port}":
            raise Refusal(HTTPStatus.MISDIRECTED_REQUEST, error_body("HOST_NOT_ALLOWED"))
        origin = h.headers.get("Origin")
        if origin is not None and origin != self.url:
            raise Refusal(HTTPStatus.FORBIDDEN, error_body("ORIGIN_NOT_ALLOWED"))
        if len(url.path) > MAX_PATH or len(url.query) > MAX_QUERY:
            raise Refusal(HTTPStatus.REQUEST_URI_TOO_LONG, error_body("REQUEST_TOO_LARGE"))
        if h.headers.get("Content-Length") not in (None, "0") or h.headers.get("Transfer-Encoding"):
            h.close_connection = True  # the body is not read
            raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", "a read carries no body"))
        fetch_site = h.headers.get("Sec-Fetch-Site")
        if url.path.startswith("/api/") and fetch_site is not None and fetch_site not in SAME_SITE_FETCH:
            raise Refusal(HTTPStatus.FORBIDDEN, error_body("ORIGIN_NOT_ALLOWED", "a cross-site read is refused"))

    def _static(self, h: BaseHTTPRequestHandler, path: str, *, head: bool) -> None:
        """The frontend's build (R23): a file, the SPA fallback, or an ``Error``."""
        if self.static_root is None:
            raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", "this install carries no dashboard build"))
        try:
            asset = ST.resolve(self.static_root, path)
        except ST.BadPath as exc:
            raise Refusal(HTTPStatus.BAD_REQUEST, error_body("INVALID_REQUEST", str(exc))) from None
        if asset is None:
            raise Refusal(HTTPStatus.NOT_FOUND, error_body("NOT_FOUND", "no such file"))
        payload = asset.path.read_bytes()
        h.send_response(int(HTTPStatus.OK))
        h.send_header("Content-Type", asset.content_type)
        h.send_header("Content-Length", str(len(payload)))
        for name, value in self._common_headers(asset.cache_control):
            h.send_header(name, value)
        h.end_headers()
        if not head:
            h.wfile.write(payload)

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
    def _common_headers(cache_control: str = ST.NO_STORE) -> list[tuple[str, str]]:
        return [("Cache-Control", cache_control), *SECURITY_HEADERS]

    def _respond(self, h: BaseHTTPRequestHandler, url: Any) -> tuple[int, dict[str, Any], str]:
        """The ``200`` body of a read, stamped with the snapshot's time, and its validator; or a :class:`Refusal`."""
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
            snapshot = self.reader.snapshot()
            projector = P.Projector(snapshot)
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
        tag = E.validator(E.scope(url.path, snapshot.project_id, self._normalized(query)), body)
        body = E.stamp(body, snapshot.generated_at)
        if self.contract is not None:
            violations = self.contract.violations(self.contract.response_schema(route), body)
            if violations:
                LOG.error("projection %s violates the contract: %s", route, violations[:5])
                raise Refusal(HTTPStatus.INTERNAL_SERVER_ERROR, error_body("PROJECTION_FAILED"))
        return HTTPStatus.OK, body, tag

    @staticmethod
    def _normalized(query: dict[str, str]) -> dict[str, Any]:
        """The query as the scope of a validator: limits as the numbers they parse to (``limit=050`` is ``50``)."""
        return {k: P.parse_limit(v) if k in LIMIT_PARAMETERS else v for k, v in query.items()}

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
    def _not_modified(cls, h: BaseHTTPRequestHandler, tag: str) -> None:
        """``304``: the validator the client sent (it matched), the headers of the ``200``, no body (R19)."""
        h.send_response(int(HTTPStatus.NOT_MODIFIED))
        h.send_header("ETag", tag)
        for name, value in cls._common_headers():
            h.send_header(name, value)
        h.end_headers()

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
