"""F20.6: the dashboard's integrated acceptance, server side (design note §5.5; register F20.6).

One project is driven through the lifecycle (an Epic and its plan decision, an integrated and archived Ticket, an
open Ticket, a Ticket whose title is hostile content, an audit), and the product is exercised end to end as the
frontend uses it: the one-time URL exchanged for the cookie, the packaged frontend and its bundle loaded, then every
page's projection fetched with the cookie in the order the pages fetch them, each validated against contract 0.1.2,
carrying R21's headers and a validator that a conditional replay confirms with a ``304``. Then the session's end:
expiry, the server stopping (a new server never honours an old cookie), and scope (another project's server, its
cookie and its validators are its own). On POSIX the same walk runs through the real CLI, ``aew dashboard serve`` at
a pseudo-terminal, with the typed-back code (``serial``).

The browser half (the web side's ``browser-live.mjs`` against this server) is recorded in
``docs/archive/reviews/dashboard-main-line-acceptance-2026-10-05.md``, separately from these tests.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import IS_WINDOWS, clean_env

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import create_unit, sample_project  # noqa: E402
from dashboard_world import HOSTILE, World, build_world  # noqa: E402
from invariants import assert_control_invariants  # noqa: E402

from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard import service  # noqa: E402
from aew.dashboard import session as S  # noqa: E402
from aew.engine.api import Engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
STATIC = ROOT / "src" / "aew" / "dashboard" / "static"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; "
       "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
SECURITY = {"content-security-policy": CSP, "x-content-type-options": "nosniff", "referrer-policy": "no-referrer",
            "cross-origin-resource-policy": "same-origin", "cross-origin-opener-policy": "same-origin",
            "x-frame-options": "DENY", "permissions-policy": "camera=(), microphone=(), geolocation=()"}
NAVIGATION = {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
FETCH = {"Sec-Fetch-Site": "same-origin", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"}


class Clock:
    def __init__(self) -> None:
        self.offset = timedelta()

    def __call__(self) -> str:
        return (datetime.now(UTC) + self.offset).strftime(S.TIME_FORMAT)


class Browser:
    """What the frontend does over HTTP, cookie jar included (one cookie, ``aew_session``)."""

    def __init__(self, base: str) -> None:
        self.base = base
        host, port = base[len("http://"):].split(":")
        self.host, self.port = host, int(port)
        self.cookie: str | None = None
        self.validators: dict[str, str] = {}

    def get(self, path: str, *, headers: dict[str, str] | None = None, method: str = "GET",
            ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
        try:
            h = dict(headers or {})
            if self.cookie is not None:
                h["Cookie"] = f"{S.COOKIE}={self.cookie}"
            if "Origin" not in h and h.get("Sec-Fetch-Mode") == "cors":
                h["Origin"] = self.base  # a same-origin fetch carries its origin
            conn.request(method, path, headers=h)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, raw
        finally:
            conn.close()

    def open(self, url: str) -> None:
        """Follow the one-time URL from the address bar: the cookie is set and the page is ``/``."""
        assert url.startswith(self.base + "/session/"), url
        status, headers, _ = self.get(url[len(self.base):], headers=NAVIGATION)
        assert status == 303 and headers["location"] == "/", (status, headers)
        attrs = [a.strip() for a in headers["set-cookie"].split(";")]
        assert attrs[0].startswith(f"{S.COOKIE}=aew1.") and "HttpOnly" in attrs and "SameSite=Strict" in attrs
        self.cookie = attrs[0][len(S.COOKIE) + 1:]

    def api(self, path: str) -> tuple[int, dict[str, str], Any]:
        status, headers, raw = self.get(f"/api/v1{path}", headers=FETCH)
        return status, headers, (json.loads(raw) if raw else None)


def security_headers(headers: dict[str, str], cache: str = "no-store") -> None:
    for name, value in SECURITY.items():
        assert headers.get(name) == value, name
    assert headers.get("cache-control") == cache
    assert not any(k.startswith("access-control-") for k in headers)
    assert "server" not in headers and "date" not in headers


def contract_route(path: str) -> str:
    bare = path.split("?", 1)[0]
    return bare if bare in CONTRACT.paths else "/" + bare.split("/")[1] + "/{id}"


def walk(browser: Browser, ids: dict[str, str]) -> dict[str, Any]:
    """The frontend's reads, in order: the document, its bundle, a deep link, then each page's projections (the
    bootstrap read first). Every 200 is validated and replayed conditionally. Returns what was seen, for the record."""
    seen: dict[str, Any] = {"pages": [], "api": []}
    status, headers, index = browser.get("/", headers=NAVIGATION)
    assert status == 200 and index == (STATIC / "index.html").read_bytes()
    security_headers(headers)
    for ref in re.findall(rb'(?:src|href)="(/[^"]+)"', index):
        asset = ref.decode()
        status, headers, body = browser.get(asset, headers={"Sec-Fetch-Site": "same-origin"})
        assert status == 200 and body == (STATIC / asset.lstrip("/")).read_bytes(), asset
        security_headers(headers, "no-store" if asset == "/favicon.svg" else "max-age=31536000, immutable")
        seen["pages"].append(asset)
    for deep in ("/work", f"/work/{ids['open']}", "/runs", "/evidence", "/knowledge", "/history",
                 f"/history/{ids['done']}", "/activity", "/attention"):
        status, _, body = browser.get(deep, headers=NAVIGATION)
        assert status == 200 and body == index, deep  # the SPA fallback: a reload of any page
        seen["pages"].append(deep)
    status, _, project = browser.api("/project")  # the bootstrap read binds the project
    assert status == 200
    reads = ["/project", "/capabilities", "/overview", "/work", f"/work/{ids['open']}", f"/work/{ids['done']}",
             f"/work?parent={ids['epic']}", "/work?state=DONE", "/runs", "/evidence", f"/evidence?work={ids['done']}",
             "/knowledge", "/history", "/history?kind=unit", f"/history/{ids['done']}", "/history/integrity",
             "/activity", "/activity?limit=5"]
    for path in reads:
        status, headers, body = browser.api(path)
        assert status == 200, (path, status, body)
        assert CONTRACT.violations(CONTRACT.response_schema(contract_route(path)), body) == [], path
        assert body["project_id"] == project["project_id"] and body["schema_version"] == "0.1.2"
        security_headers(headers)
        assert headers["content-type"] == "application/json; charset=utf-8"
        tag = headers["etag"]
        replay = browser.get(f"/api/v1{path}", headers={**FETCH, "If-None-Match": tag})
        assert replay[0] == 304 and replay[1]["etag"] == tag and replay[2] == b"", path
        security_headers(replay[1])
        browser.validators[path] = tag
        seen["api"].append(path)
    # The detail pages behind the lists (PR #97 review, finding 1): the first record of each, read, validated and
    # replayed like the rest, and its page deep-linked.
    # (Archived evidence is listed by its work unit, as the Evidence page reads it.)
    for listing in ("/runs", f"/evidence?work={ids['done']}", "/knowledge"):
        items = browser.api(listing)[2]["data"]["items"]
        assert items, f"the acceptance project has no {listing} records"
        detail = f"{listing.split('?')[0]}/{items[0]['id']}"
        status, headers, body = browser.api(detail)
        assert status == 200, (detail, status, body)
        assert CONTRACT.violations(CONTRACT.response_schema(contract_route(detail)), body) == [], detail
        assert body["project_id"] == project["project_id"]
        security_headers(headers)
        assert headers["content-type"] == "application/json; charset=utf-8"
        replay = browser.get(f"/api/v1{detail}", headers={**FETCH, "If-None-Match": headers["etag"]})
        assert replay[0] == 304 and replay[1]["etag"] == headers["etag"] and replay[2] == b"", detail
        security_headers(replay[1])  # as for every read above (PR #97 re-review, N1)
        browser.validators[detail] = headers["etag"]
        seen["api"].append(detail)
        status, _, page = browser.get(detail, headers=NAVIGATION)
        assert status == 200 and page == index, detail  # its deep link reloads the frontend
        seen["pages"].append(detail)
    status, _, body = browser.api("/attention")  # UNSUPPORTED until F15.1: the page shows the capability state
    assert status == 403 and body["reasons"][0]["code"] == "AWAITS_ACTION_PROJECTION"
    by_id = {u["id"]: u for u in browser.api("/work")[2]["data"]["items"]}
    seen["revision"] = project["control_revision"]
    seen["work"] = sorted(by_id)
    return seen


# ------------------------------------------------------------------------------------------------- the world

@pytest.fixture(scope="module")
def world(tmp_path_factory) -> World:
    w = build_world(tmp_path_factory.mktemp("acceptance"))
    yield w
    assert_control_invariants(w.project)


def start(root: Path, clock: Clock | None = None) -> service.Service:
    svc = service.Service(Engine.discover(root), port=0, hours=2, console=lambda text: None,
                          clock=clock or Clock(), validate_with=CONTRACT)
    svc.start()
    return svc


# ------------------------------------------------------------------------------------------------- acceptance

def test_the_product_end_to_end_through_one_session(world):
    svc = start(world.root)
    try:
        browser = Browser(svc.url)
        status, _, _ = browser.api("/project")
        assert status == 401  # before the exchange there is no session
        browser.open(svc.issue())
        seen = walk(browser, world.ids)
        assert set(world.ids.values()) <= set(seen["work"]) | {world.ids["done"]}
        assert len(seen["api"]) == 21 and len(seen["pages"]) >= 13
    finally:
        svc.stop()


def test_hostile_content_comes_back_as_data(world):
    svc = start(world.root)
    try:
        browser = Browser(svc.url)
        browser.open(svc.issue())
        status, headers, raw = browser.get(f"/api/v1/work/{world.ids['hostile']}", headers=FETCH)
        assert status == 200 and headers["content-type"] == "application/json; charset=utf-8"
        assert headers["x-content-type-options"] == "nosniff" and headers["content-security-policy"] == CSP
        assert json.loads(raw)["data"]["title"] == HOSTILE  # exactly the stored string, nothing stripped or added
        # Every HTML the server writes is its own: the frontend document is the build, unchanged; no project text
        # ever reaches an HTML response.
        for path in ("/", f"/work/{world.ids['hostile']}"):
            status, headers, body = browser.get(path, headers=NAVIGATION)
            assert body == (STATIC / "index.html").read_bytes() and b"onerror" not in body
    finally:
        svc.stop()


def test_a_session_expires_and_the_page_still_loads_to_say_so(world):
    clock = Clock()
    svc = start(world.root, clock)
    try:
        browser = Browser(svc.url)
        browser.open(svc.issue())
        status, headers, _ = browser.api("/overview")
        tag = headers["etag"]  # a real validator, which matches while the session lives (PR #97 review, finding 2)
        assert status == 200
        assert browser.get("/api/v1/overview", headers={**FETCH, "If-None-Match": tag})[0] == 304
        clock.offset = timedelta(hours=2, seconds=1)
        status, headers, body = browser.api("/overview")
        assert status == 401 and body["code"] == "SESSION_EXPIRED"
        assert headers["set-cookie"].startswith(f"{S.COOKIE}=;")  # the dead cookie is removed
        security_headers(headers)
        assert browser.get("/api/v1/overview", headers={**FETCH, "If-None-Match": tag})[0] == 401  # no 304 either
        assert browser.get("/", headers=NAVIGATION)[0] == 200  # the frontend shows the session-required state
    finally:
        svc.stop()


def test_stopping_the_server_ends_every_session_and_a_new_server_honours_none(world):
    svc = start(world.root)
    browser = Browser(svc.url)
    browser.open(svc.issue())
    assert browser.api("/project")[0] == 200
    svc.stop()
    with pytest.raises(OSError):
        browser.api("/project")  # nothing listens
    assert service.locate(world.root) is None  # the endpoint files are gone
    again = start(world.root)
    try:
        browser.base, browser.port = again.url, again.port
        status, headers, body = browser.api("/project")
        assert status == 401 and body["code"] == "SESSION_REQUIRED"  # sessions are process-local, never durable
    finally:
        again.stop()


def test_each_server_serves_one_project_and_its_scope_is_its_own(world, tmp_path):
    """Another project's server: its session, its data and its validators are its own (Q02: one server, one
    project; a second project is a second server on another port, another browser origin)."""
    p = sample_project(tmp_path)
    theirs_only = create_unit(p, "ticket", "Only in the other project", cls=1)
    mine, theirs = start(world.root), start(p.root)
    try:
        a, b = Browser(mine.url), Browser(theirs.url)
        a.open(mine.issue())
        b.open(theirs.issue())
        a_titles = {u["title"] for u in a.api("/work")[2]["data"]["items"]}
        b_items = {u["id"]: u["title"] for u in b.api("/work")[2]["data"]["items"]}
        assert "Only in the other project" not in a_titles and b_items[theirs_only] == "Only in the other project"
        assert HOSTILE in a_titles and HOSTILE not in b_items.values()
        stolen = Browser(theirs.url)
        stolen.cookie = a.cookie
        assert stolen.api("/project")[0] == 401  # one server's session is nothing to another
        _, ha, _ = a.api("/work")
        status, _, _ = b.get("/api/v1/work", headers={**FETCH, "If-None-Match": ha["etag"]})
        assert status == 200  # a validator of one project's representation never confirms another's
    finally:
        mine.stop()
        theirs.stop()


# ------------------------------------------------------------------------------------------------- the real CLI

@pytest.mark.serial  # a real pseudo-terminal and a forked child answering within a deadline
@pytest.mark.skipif(
    IS_WINDOWS,
    reason="POSIX pty operator path. A Windows console session would appear on the developer desktop, so on "
           "Windows the in-process service runs the same walk",
)
def test_the_real_cli_serves_the_product_end_to_end(world):
    """The terminal is drained by a thread throughout, as a real terminal is: ``serve`` writes its request log to
    standard error, and an undrained pseudo-terminal would block the server mid-walk."""
    import pty
    import signal
    import threading

    argv = [sys.executable, "-m", "aew", "--print-credential", "-C", str(world.root), "dashboard", "serve",
            "--port", "0"]
    pid, fd = pty.fork()
    if pid == 0:
        # The operator's Ctrl-C is SIGINT; a test runner started in the background inherits it ignored, and Python
        # then installs no handler, so the child restores the default before it becomes `aew`.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        os.execvpe(argv[0], argv, clean_env())  # noqa: S606 (argv is fixed above)
    screen = bytearray()
    lock = threading.Lock()

    def drain() -> None:
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                return
            if not chunk:
                return
            with lock:
                screen.extend(chunk)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()

    def wait_for(pattern: bytes) -> re.Match[bytes]:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with lock:
                match = re.search(pattern, bytes(screen))
            if match:
                return match
            time.sleep(0.1)
        raise AssertionError(bytes(screen).decode("utf-8", "replace"))

    reaped = False
    try:
        code = wait_for(rb"confirmation code ([0-9A-F]{6})").group(1)
        os.write(fd, code + bytes([10]))  # the operator reads the screen and types, then Enter
        url = wait_for(rb'"session_url": "(http://127\.0\.0\.1:\d+/session/[A-Za-z0-9_-]+)"').group(1).decode()
        browser = Browser(url.split("/session/")[0])
        browser.open(url)
        seen = walk(browser, world.ids)
        os.kill(pid, signal.SIGINT)  # the operator's Ctrl-C
        deadline = time.monotonic() + 60
        while (got := os.waitpid(pid, os.WNOHANG))[0] == 0:
            assert time.monotonic() < deadline, bytes(screen).decode("utf-8", "replace")  # it must stop
            time.sleep(0.2)
        status, reaped = got[1], True
    finally:
        if not reaped:  # a failed test never leaves a server behind
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        os.close(fd)
        reader.join(10)
    log = bytes(screen).decode("utf-8", "replace")
    assert os.waitstatus_to_exitcode(status) in (0, 130), log
    assert len(seen["api"]) == 18
    assert "GET /session/<redacted> 303" in log and "GET /api/v1/overview 200" in log  # the request log, redacted
    assert url.split("/session/")[1] not in log.split(url, 1)[-1]  # the code never reappears after its URL
    with pytest.raises(OSError):
        browser.api("/project")  # the server is gone with the command
    assert service.locate(world.root) is None


# ------------------------------------------------------------------------------------------------- the browser handoff

def test_the_session_file_tool_writes_the_runners_private_file(world, tmp_path, monkeypatch, capsys):
    """``tools/dashboard/session_file.py``: the one-time URL on stdin becomes the web runner's session file, in its
    agreed format, owner-only, and the credential is never printed."""
    import importlib.util
    import io
    import subprocess

    spec = importlib.util.spec_from_file_location("session_file", ROOT / "tools/dashboard/session_file.py")
    assert spec and spec.loader
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    svc = start(world.root)
    try:
        out = tmp_path / "private" / "session.json"
        monkeypatch.setattr(sys, "stdin", io.StringIO(svc.issue() + "\n"))
        assert tool.main([str(out)]) == 0
        record = json.loads(out.read_text(encoding="utf-8"))
        assert record["version"] == 1 and record["origin"] == svc.url
        assert record["cookie"]["name"] == "aew_session" and record["cookie"]["value"].startswith("aew1.")
        assert record["cookie"]["value"] not in capsys.readouterr().out
        browser = Browser(svc.url)
        browser.cookie = record["cookie"]["value"]
        assert browser.api("/project")[0] == 200  # the file holds a live session
        if IS_WINDOWS:
            acl = subprocess.run(["icacls", str(out)], capture_output=True, text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
            grants = [ln for ln in acl.splitlines()[:-2] if ":(" in ln]
            assert len(grants) == 1 and os.environ["USERNAME"].lower() in grants[0].lower(), acl
            assert "(I)" not in acl  # nothing inherited
        else:
            assert out.stat().st_mode & 0o777 == 0o600
        monkeypatch.setattr(sys, "stdin", io.StringIO(svc.url + "/session/" + "x" * 43 + "\n"))
        with pytest.raises(SystemExit):
            tool.main([str(tmp_path / "again.json")])  # an unknown or spent link is refused
        monkeypatch.setattr(sys, "stdin", io.StringIO("http://evil.example/session/abc\n"))
        with pytest.raises(SystemExit):
            tool.main([str(tmp_path / "again.json")])
    finally:
        svc.stop()
