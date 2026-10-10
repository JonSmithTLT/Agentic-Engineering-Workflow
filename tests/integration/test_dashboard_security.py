"""F20.5: the server's security (design note §4.14, R21 to R23; §5.4), over real sockets against a live project.

Every kind of response carries the full header set; the exact-origin rules refuse a foreign ``Host`` (``421``), a
foreign ``Origin`` and a cross-site ``Sec-Fetch-Site`` (``403``); every method but GET and HEAD is ``405``; a body is
``400``; an oversized request line, path, query or header block is ``414`` or ``431``; an id is checked before any
lookup; the seventeenth request in flight is ``503``; no response ever carries a CORS header; the request log
redacts ``/session/`` codes and never records a query. Requests are written raw where ``http.client`` would correct
them.
"""

from __future__ import annotations

import http.client
import json
import logging
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import create_planned_ticket, sample_project  # noqa: E402

from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard import server as SV  # noqa: E402
from aew.dashboard.server import DashboardServer  # noqa: E402
from aew.dashboard.session import SessionTable  # noqa: E402
from aew.engine.api import Engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
HEADERS = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
           "cross-origin-resource-policy": "same-origin", "cross-origin-opener-policy": "same-origin",
           "x-frame-options": "DENY", "permissions-policy": "camera=(), microphone=(), geolocation=()"}


class Live:
    def __init__(self, server: DashboardServer, table: SessionTable, cookie: str, project_id: str) -> None:
        self.server = server
        self.table = table
        self.cookie = cookie
        self.project_id = project_id

    @property
    def host(self) -> str:
        return f"127.0.0.1:{self.server.port}"

    def request(self, method: str, path: str, headers: dict[str, str] | None = None, body: bytes | None = None,
                *, cookie: bool = True) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=30)
        try:
            h = dict(headers or {})
            if cookie:
                h.setdefault("Cookie", self.cookie)
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, raw
        finally:
            conn.close()

    def raw(self, data: bytes) -> tuple[int, dict[str, str], bytes]:
        """One raw request on its own connection; the response parsed by hand (status, headers, body)."""
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=30) as s:
            s.sendall(data)
            chunks = b""
            while b"\r\n\r\n" not in chunks:
                got = s.recv(65536)
                if not got:
                    break
                chunks += got
            head, _, rest = chunks.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").split("\r\n")
            status = int(lines[0].split()[1])
            headers = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
            want = int(headers.get("content-length", "0"))
            while len(rest) < want:
                got = s.recv(65536)
                if not got:
                    break
                rest += got
            return status, headers, rest[:want]


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("security")
    p = sample_project(tmp)
    create_planned_ticket(p, tmp)
    engine = Engine.discover(p.root)
    table = SessionTable("calc")
    server = DashboardServer(engine, authenticator=table, sessions=table, validate_with=CONTRACT)
    server.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
    conn.request("GET", f"/session/{table.mint()}")
    resp = conn.getresponse()
    resp.read()
    conn.close()
    assert resp.status == 303
    cookie = resp.getheader("Set-Cookie").split(";", 1)[0]
    yield Live(server, table, cookie, "calc")
    server.stop()


def assert_headers(headers: dict[str, str], *, cache: str = "no-store") -> None:
    for name, value in HEADERS.items():
        assert headers.get(name) == value, (name, headers.get(name))
    assert headers.get("cache-control") == cache
    assert not any(k.startswith("access-control-") for k in headers), headers
    assert "server" not in headers and "date" not in headers


def error_code(raw: bytes) -> str:
    body = json.loads(raw)
    assert CONTRACT.violations(CT.ERROR_SCHEMA, body) == []
    return body["code"]


# ------------------------------------------------------------------------------------------- headers (R21)

def test_every_kind_of_response_carries_the_full_header_set(live):
    js = next(n for n in (ROOT / "src/aew/dashboard/static/assets").iterdir() if n.suffix == ".js").name
    code = live.table.mint()
    cases: list[tuple[str, str, dict[str, str], bool, int, str]] = [
        ("GET", "/", {}, True, 200, "no-store"),
        ("GET", "/index.html", {}, True, 200, "no-store"),
        ("GET", "/work/T-0001", {}, True, 200, "no-store"),  # the SPA fallback
        ("GET", "/favicon.svg", {}, True, 200, "no-store"),
        ("GET", f"/assets/{js}", {}, True, 200, "max-age=31536000, immutable"),
        ("HEAD", f"/assets/{js}", {}, True, 200, "max-age=31536000, immutable"),
        ("GET", "/api/v1/project", {}, True, 200, "no-store"),
        ("HEAD", "/api/v1/overview", {}, True, 200, "no-store"),
        ("GET", "/api/v1/project", {}, False, 401, "no-store"),
        ("GET", "/api/v1/attention", {}, True, 403, "no-store"),
        ("GET", "/api/v1/work/T-9999", {}, True, 404, "no-store"),
        ("GET", "/api/v1/work?limit=0", {}, True, 400, "no-store"),
        ("GET", "/nope.js", {}, True, 404, "no-store"),
        ("GET", "/%2e%2e/x.js", {}, True, 400, "no-store"),
        ("POST", "/api/v1/project", {}, True, 405, "no-store"),
        ("GET", "/api/v1/project", {"Host": "localhost"}, True, 421, "no-store"),
        ("GET", "/api/v1/project", {"Origin": "http://evil.example"}, True, 403, "no-store"),
        ("GET", "/api/v1/project?" + "x" * 3000, {}, True, 414, "no-store"),
        ("GET", "/session/" + "y" * 43, {}, False, 410, "no-store"),
        ("GET", "/session/" + code, {"Sec-Fetch-Site": "cross-site"}, False, 403, "no-store"),
        ("GET", "/session/" + code, {}, False, 303, "no-store"),
    ]
    for method, path, headers, cookie, status, cache in cases:
        got, response_headers, _ = live.request(method, path, headers, cookie=cookie)
        assert got == status, (method, path, got)
        assert_headers(response_headers, cache=cache)
        if status not in (303, 401):
            assert "set-cookie" not in response_headers, (method, path)


def test_a_cookie_is_set_only_by_the_exchange_and_cleared_only_by_a_401(live):
    _, headers, _ = live.request("GET", "/api/v1/project", {"Cookie": "aew_session=aew1.tk_0000000000000000.x"},
                                 cookie=False)
    assert headers["set-cookie"].startswith("aew_session=;")  # the dead cookie removed
    _, headers, _ = live.request("GET", "/api/v1/project", cookie=False)
    assert "set-cookie" not in headers  # no cookie sent: nothing to clear


def test_the_frontend_is_served_from_the_package_with_its_types(live):
    status, headers, body = live.request("GET", "/", cookie=False)  # the page itself needs no session: no data
    assert status == 200 and headers["content-type"] == "text/html; charset=utf-8"
    assert body == (ROOT / "src/aew/dashboard/static/index.html").read_bytes()
    js = next(n for n in (ROOT / "src/aew/dashboard/static/assets").iterdir() if n.suffix == ".js")
    status, headers, body = live.request("GET", f"/assets/{js.name}", cookie=False)
    assert status == 200 and headers["content-type"] == "text/javascript; charset=utf-8" and body == js.read_bytes()
    head_status, head_headers, head_body = live.request("HEAD", f"/assets/{js.name}", cookie=False)
    assert head_status == 200 and head_body == b"" and head_headers == headers


@pytest.mark.parametrize("path", ["/mockServiceWorker.js", "/BUILD.json", "/nope.js", "/assets/nope.js"])
def test_unknown_and_withheld_files_are_404(live, path):
    status, headers, raw = live.request("GET", path)
    assert status == 404 and error_code(raw) == "NOT_FOUND"
    assert_headers(headers)


@pytest.mark.parametrize("path", ["/..%2f..%2fpyproject.toml", "/%2e%2e/%2e%2e/pyproject.toml", "/a%5c..%5cb.js",
                                  "/assets/../../pyproject.toml", "/a\\b.js", "/assets//x.js", "/%ff.js"])
def test_traversal_is_refused(live, path):
    status, _, raw = live.raw(f"GET {path} HTTP/1.1\r\nHost: {live.host}\r\n\r\n".encode("latin-1"))
    assert status == 400 and error_code(raw) == "INVALID_REQUEST", path


def test_the_static_build_can_be_an_unpacked_directory(tmp_path):
    root = tmp_path / "build"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>local build</title>", encoding="utf-8")
    p = sample_project(tmp_path)
    server = DashboardServer(Engine.discover(p.root), authenticator=SessionTable("calc"), static_root=root)
    server.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
        conn.request("GET", "/work/T-0001")
        resp = conn.getresponse()
        assert resp.status == 200 and b"local build" in resp.read()
    finally:
        server.stop()


# ------------------------------------------------------------------------------------------- Host and Origin (R22)

@pytest.mark.parametrize("path", ["/api/v1/project", "/", "/work/T-0001", "/session/abc"])
def test_a_foreign_host_is_421_before_routing(live, path):
    port = live.server.port
    for host in ("localhost", f"localhost:{port}", "127.0.0.1", f"127.0.0.1:{port + 1}", f"evil.example:{port}",
                 f"[::1]:{port}", f"127.0.0.2:{port}"):
        status, headers, raw = live.raw(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nCookie: {live.cookie}\r\n\r\n"
                                        .encode("latin-1"))
        assert status == 421 and error_code(raw) == "HOST_NOT_ALLOWED", (path, host)
        assert_headers(headers)
    status, _, raw = live.raw(f"GET {path} HTTP/1.1\r\nCookie: {live.cookie}\r\n\r\n".encode("latin-1"))
    assert status == 421, "a request without Host is refused"


def test_the_exact_host_is_served(live):
    status, _, _ = live.raw(f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\nCookie: {live.cookie}\r\n\r\n"
                            .encode("latin-1"))
    assert status == 200


@pytest.mark.parametrize("path", ["/api/v1/project", "/", "/session/abc"])
def test_a_foreign_origin_is_403(live, path):
    port = live.server.port
    for origin in ("http://evil.example", f"http://localhost:{port}", f"http://127.0.0.1:{port + 1}",
                   f"https://127.0.0.1:{port}", "null", f"http://127.0.0.1:{port}/"):
        status, headers, raw = live.request("GET", path, {"Origin": origin})
        assert status == 403 and error_code(raw) == "ORIGIN_NOT_ALLOWED", (path, origin)
        assert_headers(headers)
    assert live.request("GET", "/api/v1/project", {"Origin": f"http://127.0.0.1:{port}"})[0] == 200


def test_a_cross_site_fetch_of_the_api_is_403(live):
    for site in ("cross-site", "same-site", "bogus"):
        status, _, raw = live.request("GET", "/api/v1/project", {"Sec-Fetch-Site": site})
        assert status == 403 and error_code(raw) == "ORIGIN_NOT_ALLOWED", site
    for site in ("same-origin", "none"):
        assert live.request("GET", "/api/v1/project", {"Sec-Fetch-Site": site})[0] == 200, site
    # The page itself may be reached from elsewhere (a link, a bookmark): it carries no data.
    assert live.request("GET", "/", {"Sec-Fetch-Site": "cross-site"})[0] == 200


def test_the_listener_is_bound_to_loopback_only(live):
    assert live.server.httpd.server_address[0] == "127.0.0.1"
    assert SV.HOST == "127.0.0.1"


# ------------------------------------------------------------------------------------------- methods and bounds (R23)

@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT", "PROPFIND"])
def test_every_other_method_is_405(live, method):
    for path in ("/api/v1/project", "/", "/session/abc"):
        status, headers, raw = live.raw(f"{method} {path} HTTP/1.1\r\nHost: {live.host}\r\nOrigin: http://evil.example"
                                        f"\r\nAccess-Control-Request-Method: GET\r\n\r\n".encode("latin-1"))
        assert status == 405 and headers.get("allow") == "GET, HEAD", (method, path)
        assert error_code(raw) == "METHOD_NOT_ALLOWED"
        assert_headers(headers)


def test_a_request_with_a_body_is_400(live):
    for extra in ("Content-Length: 5\r\n", "Transfer-Encoding: chunked\r\n"):
        for path in ("/api/v1/project", "/"):
            status, headers, raw = live.raw(f"GET {path} HTTP/1.1\r\nHost: {live.host}\r\n{extra}\r\nhello"
                                            .encode("latin-1"))
            assert status == 400 and error_code(raw) == "INVALID_REQUEST", (path, extra)
            assert headers.get("connection") == "close"  # the unread body never reaches a next request


def test_oversized_request_lines_paths_and_queries_are_refused(live):
    cases = [("/api/v1/project?" + "a=1&" * 1100, 414),          # request line over 4 KiB
             ("/" + "p" * 2047 + "?" + "q" * 2048, 414),           # line over 4 KiB, path and query within theirs
             ("/" + "w" * 2100, 414),                              # path over 2 KiB
             ("/api/v1/work?state=" + "x" * 2100, 414),            # query over 2 KiB
             ("/" + "w" * 70000, 414)]                             # beyond stdlib's own line limit
    for target, status in cases:
        got, headers, raw = live.raw(f"GET {target} HTTP/1.1\r\nHost: {live.host}\r\n\r\n".encode("latin-1"))
        assert got == status and error_code(raw) == "REQUEST_TOO_LARGE", (len(target), got)
        assert_headers(headers)


def test_oversized_header_blocks_are_431(live):
    many = "".join(f"X-H{i}: v\r\n" for i in range(64))  # 64 + Host = 65 lines
    big = "X-Big: " + "b" * (16 * 1024) + "\r\n"
    for extra in (many, big):
        status, headers, raw = live.raw(f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\n{extra}\r\n"
                                        .encode("latin-1"))
        assert status == 431 and error_code(raw) == "REQUEST_TOO_LARGE"
        assert_headers(headers)
    fits = "".join(f"X-H{i}: v\r\n" for i in range(60))
    status, _, _ = live.raw(f"GET / HTTP/1.1\r\nHost: {live.host}\r\n{fits}\r\n".encode("latin-1"))
    assert status == 200


def test_a_malformed_request_is_the_contracts_error(live):
    for line in ("GARBAGE\r\n", "GET / HTTP/9.9\r\n", "GET / HTTP/1.1 extra\r\n", "GET /\r\n", "GET / HTTP/0.9\r\n"):
        status, headers, raw = live.raw(f"{line}Host: {live.host}\r\n\r\n".encode("latin-1"))
        assert 400 <= status < 506, line
        assert error_code(raw) in ("INVALID_REQUEST", "METHOD_NOT_ALLOWED"), line
        assert_headers(headers)


def test_ids_limits_and_cursors_are_checked_before_any_lookup(live):
    for path in ("/api/v1/work/bad$id", "/api/v1/work/-x", "/api/v1/runs/%20", "/api/v1/work?limit=251",
                 "/api/v1/work?limit=0", "/api/v1/work?limit=x", "/api/v1/work?cursor=" + "c" * 1025):
        status, _, raw = live.request("GET", path)
        assert status == 400 and error_code(raw) in ("INVALID_REQUEST", "CURSOR_INVALID"), path


def test_the_seventeenth_request_in_flight_is_503(live):
    """Sixteen API requests wait behind the projection lock (held here); the next request of any kind is refused at
    once with ``Retry-After``, and once the lock is released every waiting request is answered."""
    results: list[int] = []
    held = live.server._serial  # noqa: SLF001 (the lock every projection takes)
    held.acquire()
    threads = [threading.Thread(target=lambda: results.append(live.request("GET", "/api/v1/project")[0]))
               for _ in range(SV.MAX_IN_FLIGHT)]
    try:
        for t in threads:
            t.start()
        deadline = 0
        while live.server._slots._value > 0 and deadline < 200:  # noqa: SLF001 (wait until all 16 are in flight)
            threading.Event().wait(0.05)
            deadline += 1
        assert live.server._slots._value == 0  # noqa: SLF001
        for path in ("/api/v1/project", "/"):
            status, headers, raw = live.request("GET", path)
            assert status == 503 and headers.get("retry-after") == "1" and error_code(raw) == "SERVER_BUSY"
            assert_headers(headers)
    finally:
        held.release()
        for t in threads:
            t.join(30)
    assert results == [200] * SV.MAX_IN_FLIGHT
    assert live.request("GET", "/api/v1/project")[0] == 200


def test_keep_alive_serves_several_requests_on_one_connection(live):
    conn = http.client.HTTPConnection("127.0.0.1", live.server.port, timeout=30)
    try:
        for path in ("/api/v1/project", "/", "/api/v1/capabilities"):
            conn.request("GET", path, headers={"Cookie": live.cookie})
            resp = conn.getresponse()
            resp.read()
            assert resp.status == 200 and not resp.will_close
    finally:
        conn.close()
    assert SV.SOCKET_TIMEOUT_S == 10.0


# ------------------------------------------------------------------------------------------- the request log (R23)

def test_the_request_log_redacts_session_codes_and_never_records_queries_headers_or_cookies(live, caplog):
    code = live.table.mint()
    with caplog.at_level(logging.INFO, logger="aew.dashboard"):
        live.request("GET", f"/session/{code}", cookie=False)
        live.request("GET", "/api/v1/work?state=SECRET_QUERY_VALUE", {"X-Secret-Header": "SECRET_HEADER_VALUE"})
        live.raw(f"GET /?q=SECRET_IN_A_BAD_LINE HTTP/9.9\r\nHost: {live.host}\r\n\r\n".encode("latin-1"))
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "aew.dashboard")
    assert "GET /session/<redacted> 303" in text
    assert "GET /api/v1/work 200" in text and "ms" in text
    for secret in (code, "SECRET_QUERY_VALUE", "SECRET_HEADER_VALUE", "SECRET_IN_A_BAD_LINE",
                   live.cookie.split("=", 1)[1], "aew_session"):
        assert secret not in text, secret


# ------------------------------------------------------------------------------------------- review of PR #90

@pytest.mark.parametrize("form", ["http://{host}/session/{code}", "//{host}/session/{code}",
                                  "http://user:pw@{host}/session/{code}?q=1"])
def test_a_non_path_target_is_refused_before_routing_and_never_logged(live, caplog, form):
    """An absolute-form (or network-path) target names a one-time code where routing would find it but the log
    redaction did not: it is refused before any route, the code stays unspent, and the log never shows it."""
    code = live.table.mint()
    target = form.format(host=live.host, code=code)
    with caplog.at_level(logging.INFO, logger="aew.dashboard"):
        status, _, raw = live.raw(f"GET {target} HTTP/1.1\r\nHost: {live.host}\r\nSec-Fetch-Site: cross-site\r\n\r\n"
                                  .encode("latin-1"))
    assert status == 400 and error_code(raw) == "INVALID_REQUEST"
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "aew.dashboard")
    assert code not in text and "user:pw" not in text and "q=1" not in text and "<not a path>" in text
    status, headers, _ = live.request("GET", f"/session/{code}", cookie=False)
    assert status == 303  # the code was never spent by the refused request


def test_the_log_redacts_session_paths_however_they_are_spelled():
    for raw in ("/session/abc", "/Session/abc", "/%73ession/abc", "/SESSION/abc?x=1", "/session/abc#f"):
        assert SV.log_target(raw) == "/session/<redacted>", raw
    assert SV.log_target("/127.0.0.1:4280/session/abc") == "/127.0.0.1:4280/session/<redacted>"
    assert SV.log_target("/api/v1/work?state=SECRET") == "/api/v1/work"
    assert SV.log_target("http://127.0.0.1:1/x") == SV.log_target("//h/x") == "<not a path>"
    assert SV.log_target(None) == "-"


def _connect_partial(live: Live) -> socket.socket:
    s = socket.create_connection(("127.0.0.1", live.server.port), timeout=30)
    s.sendall(f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\n".encode("latin-1"))  # no terminator
    return s


def _busy(live: Live) -> None:
    status, headers, raw = live.raw(f"GET / HTTP/1.1\r\nHost: {live.host}\r\n\r\n".encode("latin-1"))
    assert status == 503 and headers.get("retry-after") == "1" and error_code(raw) == "SERVER_BUSY"
    assert headers.get("connection") == "close"
    assert_headers(headers)


def _wait_for_connections(live: Live, free: int) -> None:
    deadline = time.monotonic() + 30
    while live.server.httpd.connections._value != free:  # noqa: SLF001 (the admission semaphore)
        assert time.monotonic() < deadline, live.server.httpd.connections._value  # noqa: SLF001
        time.sleep(0.05)


def test_half_sent_requests_hold_no_more_than_the_connection_bound(live):
    """Connections that never finish their headers each hold a handler thread: at the bound, the next connection
    is answered 503 at once, before anything of it is read, and the server recovers when they go."""
    held = [_connect_partial(live) for _ in range(SV.MAX_CONNECTIONS)]
    try:
        _wait_for_connections(live, 0)
        _busy(live)
    finally:
        for s in held:
            s.close()
    _wait_for_connections(live, SV.MAX_CONNECTIONS)
    assert live.request("GET", "/api/v1/project")[0] == 200


def test_idle_keep_alive_connections_hold_no_more_than_the_connection_bound(live):
    held = []
    try:
        for _ in range(SV.MAX_CONNECTIONS):
            conn = http.client.HTTPConnection("127.0.0.1", live.server.port, timeout=30)
            conn.request("GET", "/api/v1/project", headers={"Cookie": live.cookie})
            resp = conn.getresponse()
            resp.read()
            assert resp.status == 200 and not resp.will_close
            held.append(conn)  # left open and idle
        _wait_for_connections(live, 0)
        _busy(live)
    finally:
        for conn in held:
            conn.close()
    _wait_for_connections(live, SV.MAX_CONNECTIONS)
    assert live.request("GET", "/api/v1/project")[0] == 200


@pytest.mark.parametrize("block", ["X-Big: " + "b" * (17 * 1024), "".join(f"X-H{i}: v\r\n" for i in range(70))])
def test_an_oversized_header_block_is_refused_while_it_is_read(live, block):
    """The bounds hold on the wire: the refusal comes once the bound is passed, without waiting for a terminator
    the client never sends."""
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=5) as s:
        s.sendall(f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\n{block}".encode("latin-1"))
        started = time.monotonic()
        got = s.recv(65536)
    assert got.startswith(b"HTTP/1.1 431 "), got[:40]
    assert time.monotonic() - started < 4.0


def test_withheld_files_are_withheld_in_any_casing(live):
    for path in ("/build.json", "/Build.Json", "/BUILD.JSON", "/mockserviceworker.js", "/MockServiceWorker.JS"):
        status, _, raw = live.request("GET", path)
        assert status == 404 and error_code(raw) == "NOT_FOUND", path


def test_an_oversized_request_line_is_refused_while_it_is_read(live):
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=5) as s:
        s.sendall(b"GET /" + b"a" * 5000)  # past 4 KiB, and never ended
        got = s.recv(65536)
    assert got.startswith(b"HTTP/1.1 414 "), got[:40]


# ------------------------------------------------------------------------------------------- re-review of PR #90

def _closed_within(s: socket.socket, seconds: float) -> bool:
    """Whether the server ends the connection (end of input or a reset) within ``seconds``."""
    s.settimeout(seconds)
    try:
        while s.recv(65536):
            pass
        return True
    except TimeoutError:  # first: TimeoutError is an OSError (re-review R2)
        return False
    except OSError:
        return True


@pytest.mark.parametrize("line", ["GET /api/v1/project HTTP/1.1", "GET /api/v1/project"])
def test_a_slowly_trickled_request_head_is_cut_off_at_the_head_deadline(live, monkeypatch, line):
    """Finding 1: one byte every 0.3 s never trips a per-read timeout, but the whole head must arrive within the
    deadline, so a slow client cannot hold its connection (and with 32 of them, every slot) for ever. A two-word
    request line too, whose headers stdlib would read before refusing it (re-review R1)."""
    monkeypatch.setattr(SV, "HEAD_DEADLINE_S", 1.0)
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=30) as s:
        started = time.monotonic()
        head = f"{line}\r\nHost: {live.host}\r\nX-Slow: ".encode("latin-1")
        s.sendall(head)
        gone = False
        while time.monotonic() - started < 6.0:
            try:
                s.sendall(b"a")
            except OSError:
                gone = True
                break
            if _closed_within(s, 0.3):
                gone = True
                break
        assert gone, "the connection outlived the head deadline"
        assert time.monotonic() - started < 4.0


@pytest.mark.parametrize("line", ["GET / HTTP/01.1", "GET\xa0/ HTTP/1.1", "GET /"])
def test_every_request_stdlib_would_read_headers_for_is_bounded_while_it_is_read(live, line):
    """Finding 2: a request line stdlib tokenizes differently from bytes (a padded version, a non-breaking space)
    still has its header block bounded on the wire, not read whole or waited on."""
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=5) as s:
        s.sendall(f"{line}\r\nHost: {live.host}\r\nX-Big: {'b' * (17 * 1024)}".encode("latin-1"))
        started = time.monotonic()
        got = s.recv(65536)
    assert got.startswith(b"HTTP/1.1 431 "), got[:40]
    assert time.monotonic() - started < 4.0


def test_every_refused_connection_reads_its_503_rather_than_a_reset(live):
    """Finding 3: the busy answer is completed and the client's request drained before the close, so a refused
    client reads the 503 instead of a connection reset."""
    held = [_connect_partial(live) for _ in range(SV.MAX_CONNECTIONS)]
    try:
        _wait_for_connections(live, 0)
        for _ in range(40):
            _busy(live)
    finally:
        for s in held:
            s.close()
    _wait_for_connections(live, SV.MAX_CONNECTIONS)


def test_a_request_whose_client_leaves_mid_head_is_never_processed(live, caplog):
    """Finding 4: input that ends before the blank line is a client that went away: nothing is routed, answered
    or logged as a failure, and no traceback reaches standard error."""
    with caplog.at_level(logging.INFO, logger="aew.dashboard"):
        with socket.create_connection(("127.0.0.1", live.server.port), timeout=5) as s:
            s.sendall(f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\nCookie: {live.cookie}\r\n"
                      .encode("latin-1"))
            s.shutdown(socket.SHUT_WR)
            assert s.recv(65536) == b""  # no response: the request was never complete
        assert live.request("GET", "/api/v1/project")[0] == 200
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "aew.dashboard")
    assert "request failed" not in text and "connection failed" not in text
    assert text.count("GET /api/v1/project 200") == 1, text


def test_a_client_gone_is_never_a_traceback_and_anything_else_goes_to_the_log(live, caplog, capsys):
    httpd = live.server.httpd
    for gone in (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, TimeoutError):
        try:
            raise gone("client went away")
        except gone:
            httpd.handle_error(None, ("127.0.0.1", 1))
    with caplog.at_level(logging.ERROR, logger="aew.dashboard"):
        try:
            raise ValueError("a real defect")
        except ValueError:
            httpd.handle_error(None, ("127.0.0.1", 1))
    assert capsys.readouterr().err == ""  # stdlib's handler would have printed a traceback here
    assert [r.getMessage() for r in caplog.records if r.name == "aew.dashboard"] == ["dashboard connection failed"]


def test_a_logged_path_can_neither_forge_a_line_nor_grow_without_bound():
    """Finding 5: the path before a redacted session segment, and any other path, is re-encoded and capped."""
    forged = SV.log_target("/%0d%0aGET%20/admin%20200%201ms%0d%0a/session/abc")
    assert "\r" not in forged and "\n" not in forged and forged.endswith("/session/<redacted>"), forged
    assert "%0D%0A" in forged
    assert len(SV.log_target("/" + "p" * 1500 + "/session/abc")) <= SV.LOG_PATH_MAX + len("/session/<redacted>")
    assert "\x1b" not in SV.log_target("/\x1b[31mred") and len(SV.log_target("/" + "x" * 3000)) == SV.LOG_PATH_MAX


def test_the_logged_method_never_carries_control_bytes(live, caplog):
    """Re-review R3: a request line whose method token is an escape sequence is refused, and the log records
    `<bad method>`, never the bytes a terminal would act on."""
    with caplog.at_level(logging.INFO, logger="aew.dashboard"):
        status, _, _ = live.raw(f"\x1b]0;owned\x07\x1b[2J / HTTP/1.1\r\nHost: {live.host}\r\n\r\n".encode("latin-1"))
        live.request("GET", "/api/v1/project")
    assert 400 <= status < 506
    text = "\n".join(r.getMessage() for r in caplog.records if r.name == "aew.dashboard")
    assert "\x1b" not in text and "\x07" not in text and "<bad method>" in text, text
    assert "GET /api/v1/project 200" in text


# ------------------------------------------------------------------------------------------- refusals that close

def _read_to_end(s: socket.socket) -> tuple[int, dict[str, str], bytes]:
    """Everything the server sends until its end of output, parsed (status, headers, the body Content-Length
    names): a reset on the way raises, so a lost answer can never pass for a complete one."""
    data = b""
    while got := s.recv(65536):
        data += got
    head, _, rest = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
    body = rest[:int(headers.get("content-length", "0"))]
    assert len(body) == int(headers.get("content-length", "0")), (lines[0], len(rest))
    return int(lines[0].split()[1]), headers, body


@pytest.mark.parametrize("kind", ["line", "headers", "body", "method"])
def test_a_refused_request_always_delivers_its_complete_error_body(live, monkeypatch, kind):
    """A refusal that ends the connection leaves the client's input unread (the rest of a 70 KB request line, a
    header block past its bound, a body). Closing over unread input resets the connection, and on Windows the reset
    discards the answer in flight (a once-seen flake of the oversized-line test under load): the server half-closes
    and reads what the client sends before the close, so the client always reads the whole ``Error``. The client
    here sends more after the answer has begun, which a close without that drain turns into a reset every time."""
    monkeypatch.setattr(SV, "REFUSAL_DRAIN_S", 10.0)  # the late bytes below arrive within it however loaded the host
    host = f"Host: {live.host}\r\n"
    request, status, code = {
        "line": (b"GET /" + b"w" * 70000, 414, "REQUEST_TOO_LARGE"),
        "headers": (f"GET / HTTP/1.1\r\n{host}X-Big: {'b' * 70000}".encode("latin-1"), 431, "REQUEST_TOO_LARGE"),
        "body": (f"GET / HTTP/1.1\r\n{host}Content-Length: 140000\r\n\r\n{'b' * 70000}".encode("latin-1"), 400,
                 "INVALID_REQUEST"),
        "method": (f"POST / HTTP/1.1\r\n{host}Content-Length: 140000\r\n\r\n{'b' * 70000}".encode("latin-1"), 405,
                   "METHOD_NOT_ALLOWED"),
    }[kind]
    for _ in range(3):
        with socket.create_connection(("127.0.0.1", live.server.port), timeout=30) as s:
            s.sendall(request)
            first = s.recv(1)  # the answer has begun: the server has refused, and is ending the connection
            time.sleep(0.05)
            s.sendall(b"b" * 70000)  # input the server never asked for, after its answer
            got, headers, body = _read_to_end(s)
            assert first == b"H" and got == status and error_code(body) == code, (kind, got)
            assert headers.get("connection") == "close"
            assert_headers(headers)


def _inner_read(live: Live) -> bytes:
    """An authenticated read, sent as a body: answered on its own only if the server parsed the body as a request."""
    return f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\nCookie: {live.cookie}\r\n\r\n".encode("latin-1")


def _one_answer_then_the_end(live: Live, request: bytes) -> tuple[int, dict[str, str], bytes]:
    """Send ``request`` and read until the server's end of output: exactly one answer, complete, saying
    ``Connection: close``. A body read as the next request would show as a second status line."""
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=30) as s:
        s.sendall(request)
        data = b""
        while got := s.recv(65536):  # the end of output: the server ended the connection after one answer
            data += got
    assert data.count(b"HTTP/1.1 ") == 1, data
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {k.strip().lower(): v.strip() for k, v in (ln.split(":", 1) for ln in lines[1:] if ":" in ln)}
    assert len(body) == int(headers["content-length"]), lines[0]
    assert headers.get("connection") == "close"
    assert_headers(headers)
    return int(lines[0].split()[1]), headers, body


@pytest.mark.parametrize("refusal", [421, 403, 414])
def test_a_refused_request_with_a_body_never_has_its_body_read_as_a_second_request(live, refusal):
    """A body is never read, so a request carrying one ends its connection whichever check refuses it. The refusals
    checked before the body (a foreign ``Host``, a foreign ``Origin``, an over-long path) used to keep the
    connection, so the body was parsed as the next request: here a body that is itself an authenticated read gets
    no answer of its own, only the refusal, with ``Connection: close`` and the end of the connection."""
    inner = _inner_read(live)
    host, extra, path = {
        421: ("evil.example", "", "/"),
        403: (live.host, "Origin: http://evil.example\r\n", "/"),
        414: (live.host, "", "/" + "p" * (SV.MAX_PATH + 1)),
    }[refusal]
    outer = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n{extra}Content-Length: {len(inner)}\r\n\r\n".encode("latin-1")
    assert _one_answer_then_the_end(live, outer + inner)[0] == refusal


@pytest.mark.parametrize("framing", ["content-length-0-then-n", "empty-then-chunked-transfer-encoding"])
@pytest.mark.parametrize("host", ["foreign", "exact"])
def test_a_body_announced_by_any_framing_header_is_never_read_as_a_second_request(live, framing, host):
    """Every framing header counts, not only the first of its name: ``Content-Length: 0`` followed by
    ``Content-Length: N``, or an empty ``Transfer-Encoding`` followed by ``chunked``, still announces a body. With a
    foreign ``Host`` the answer is the ``421``; with the exact one, a read that would otherwise be served is the
    ``400`` "a read carries no body". Either way one answer, and the body is never answered as a request."""
    inner = _inner_read(live)
    framing_headers, body = {
        "content-length-0-then-n": (f"Content-Length: 0\r\nContent-Length: {len(inner)}\r\n", inner),
        "empty-then-chunked-transfer-encoding": ("Transfer-Encoding: \r\nTransfer-Encoding: chunked\r\n",
                                                 f"{len(inner):x}\r\n".encode() + inner + b"\r\n0\r\n\r\n"),
    }[framing]
    host_line = "evil.example" if host == "foreign" else live.host
    outer = (f"GET /api/v1/project HTTP/1.1\r\nHost: {host_line}\r\nCookie: {live.cookie}\r\n{framing_headers}\r\n"
             .encode("latin-1"))
    status, _, raw = _one_answer_then_the_end(live, outer + body)
    assert status == (421 if host == "foreign" else 400), (framing, host, status)
    if host == "exact":
        assert error_code(raw) == "INVALID_REQUEST"


@pytest.mark.parametrize("form", ["space-before-colon", "tab-before-colon", "folded-line"])
def test_a_header_block_outside_strict_field_syntax_is_refused_and_ends_its_connection(live, form):
    """RFC 9112 §5.1 and §5.2: whitespace between a field name and its colon, or a line folded onto the one before
    it, is refused with ``400`` before any header is acted on, with one answer, ``Connection: close`` and the end
    of the connection."""
    inner = _inner_read(live)
    field = {
        "space-before-colon": f"Content-Length : {len(inner)}\r\n",
        "tab-before-colon": f"Content-Length\t: {len(inner)}\r\n",
        "folded-line": f"X-A: a\r\n Content-Length: {len(inner)}\r\n",
    }[form]
    outer = f"GET /api/v1/project HTTP/1.1\r\nHost: {live.host}\r\nCookie: {live.cookie}\r\n{field}\r\n"
    status, _, raw = _one_answer_then_the_end(live, outer.encode("latin-1") + inner)
    assert status == 400 and error_code(raw) == "INVALID_REQUEST", (form, status)


def test_a_request_with_a_body_answered_busy_never_has_its_body_read_as_a_second_request(live):
    """The in-flight ``503`` is answered before the admission checks see the request: a body there is unread too,
    so the ``503`` says ``Connection: close``, is drained, and the body is never answered as the next request."""
    inner = _inner_read(live)
    outer = f"GET / HTTP/1.1\r\nHost: {live.host}\r\nContent-Length: {len(inner)}\r\n\r\n".encode("latin-1")
    slots = live.server._slots  # noqa: SLF001 (the in-flight bound, filled in-process)
    held = 0
    while slots.acquire(blocking=False):
        held += 1
    try:
        assert held == SV.MAX_IN_FLIGHT
        status, headers, raw = _one_answer_then_the_end(live, outer + inner)
    finally:
        for _ in range(held):
            slots.release()
    assert status == 503 and error_code(raw) == "SERVER_BUSY" and headers.get("retry-after") == "1"


def test_a_refused_client_that_keeps_sending_is_cut_off_at_the_drain_byte_bound(live, monkeypatch):
    """R23 bounds the drain too: with its deadline out of reach, a refused client sending without end is still cut
    off once ``DRAIN_MAX_BYTES`` are read, never read for as long as it cares to send."""
    monkeypatch.setattr(SV, "REFUSAL_DRAIN_S", 60.0)
    chunk = b"w" * 65536
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=10) as s:
        started = time.monotonic()
        cut = False
        s.sendall(b"GET /" + chunk)
        while time.monotonic() - started < 8.0:
            try:
                s.sendall(chunk)
            except OSError:  # the server closed over the unread rest: a reset
                cut = True
                break
        assert cut, "the server read a refused client's input without bound"
        assert time.monotonic() - started < 6.0


def test_a_refused_client_that_neither_sends_nor_closes_is_let_go_at_the_drain_deadline(live):
    """R23's short deadline: a refused client that reads its answer and then holds the connection open, sending
    nothing, holds its handler (and a connection slot) for ``REFUSAL_DRAIN_S`` at most, and is not let go before
    it: the drain's deadline starts after the request was sent, so the slot cannot come back sooner than that."""
    _wait_for_connections(live, SV.MAX_CONNECTIONS)
    with socket.create_connection(("127.0.0.1", live.server.port), timeout=30) as s:
        sent = time.monotonic()
        s.sendall(b"GET /" + b"w" * 5000 + b" HTTP/1.1\r\n\r\n")
        got, _, body = _read_to_end(s)  # the end of output is the half-close; the connection itself stays open
        assert got == 414 and error_code(body) == "REQUEST_TOO_LARGE"
        started = time.monotonic()
        _wait_for_connections(live, SV.MAX_CONNECTIONS)
        released = time.monotonic()
        assert released - started < SV.REFUSAL_DRAIN_S + 2.0
        assert released - sent >= SV.REFUSAL_DRAIN_S / 2  # held by the drain, not closed at once (half: timer slack)
