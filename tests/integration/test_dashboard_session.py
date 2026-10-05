"""F20.3's security acceptance (design note §5.2; ADR-0005, amendment of 2026-10-05): the operator session end to end
over HTTP, with its negative cases. The serving process's console and its clock are substituted in-process; the
commands' terminal refusals run the real CLI with no terminal; the pseudo-terminal flow runs on POSIX in the serial
lane.

Each security test here was shown to fail with its mechanism removed (the cookie check, the single-use consumption, the
expiry check, the table clearing, the Sec-Fetch rule); the PR records those runs.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import socket
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from conftest import IS_WINDOWS, Project, clean_env

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aew import errors  # noqa: E402
from aew.dashboard import contract as CT  # noqa: E402
from aew.dashboard import control, service  # noqa: E402
from aew.dashboard import session as S  # noqa: E402
from aew.dashboard.server import DashboardServer  # noqa: E402
from aew.engine import authority  # noqa: E402
from aew.engine.api import Engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = CT.Contract(ROOT / CT.CONTRACT_REL)
CODE_RE = re.compile(r"confirmation code ([0-9A-F]{6})")


class Clock:
    """The session table's time, movable by the tests (R3: the clock is injected)."""

    def __init__(self) -> None:
        self.offset = timedelta()

    def __call__(self) -> str:
        return (datetime.now(UTC) + self.offset).strftime(S.TIME_FORMAT)


class Console:
    """The serving process's console substitute: what `aew dashboard open` challenges are written to."""

    def __init__(self) -> None:
        self.text = ""

    def __call__(self, text: str) -> None:
        self.text += text

    def last_code(self) -> str:
        return CODE_RE.findall(self.text)[-1]


class Dash:
    def __init__(self, project: Project, svc: service.Service, clock: Clock, console: Console) -> None:
        self.p = project
        self.svc = svc
        self.clock = clock
        self.console = console
        self.responses: list[tuple[int, dict[str, str], bytes]] = []

    def request(self, path: str, *, method: str = "GET", cookie: str | None = None,
                headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.svc.port, timeout=30)
        try:
            hdrs = dict(headers or {})
            if cookie is not None:
                hdrs["Cookie"] = f"{S.COOKIE}={cookie}"
            conn.request(method, path, headers=hdrs)
            resp = conn.getresponse()
            body = resp.read()
            out = (resp.status, {k.lower(): v for k, v in resp.getheaders()}, body)
            self.responses.append(out)
            return out
        finally:
            conn.close()

    def exchange(self, url: str, **kw: Any) -> tuple[int, dict[str, str], bytes]:
        assert url.startswith(self.svc.url + "/session/"), url
        return self.request(url[len(self.svc.url):], **kw)

    def bootstrap(self) -> str:
        """Issue a session and exchange its URL as a browser would; the credential the cookie now holds."""
        status, headers, _ = self.exchange(self.svc.issue())
        assert status == 303 and headers["location"] == "/", (status, headers)
        return cookie_of(headers)

    def api(self, path: str, cookie: str | None, **kw: Any) -> tuple[int, dict[str, str], Any]:
        status, headers, body = self.request(f"/api/v1{path}", cookie=cookie, **kw)
        return status, headers, (json.loads(body) if body else None)


def raw_aew(root: Path, *args: str) -> tuple[int, dict[str, Any]]:
    """The CLI with no terminal and **without** `--print-credential` (which `conftest.run_aew` adds for every test):
    the exit code and the error object, if any."""
    import subprocess

    kwargs: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS
                              else {"start_new_session": True})
    proc = subprocess.run([sys.executable, "-m", "aew", "-C", str(root), *args], env=clean_env(), capture_output=True,
                          text=True, encoding="utf-8", timeout=120, stdin=subprocess.DEVNULL, **kwargs)
    error = json.loads(proc.stderr).get("error", {}) if proc.stderr.strip().startswith("{") else {}
    return proc.returncode, error


def cookie_of(headers: dict[str, str]) -> str:
    set_cookie = headers["set-cookie"]
    assert set_cookie.startswith(f"{S.COOKIE}=aew1.")
    attrs = [a.strip() for a in set_cookie.split(";")]
    assert "HttpOnly" in attrs and "SameSite=Strict" in attrs and "Path=/" in attrs, set_cookie
    assert not any(a.lower() == "secure" for a in attrs), set_cookie  # R10: no Secure on plain-http loopback
    assert any(a.startswith("Max-Age=") and int(a[8:]) > 0 for a in attrs), set_cookie
    return attrs[0][len(S.COOKIE) + 1:]


@pytest.fixture
def dash(project: Project) -> Dash:
    clock, console = Clock(), Console()
    engine = Engine.discover(project.root)
    svc = service.Service(engine, port=0, hours=2, console=console, clock=clock, validate_with=CONTRACT)
    svc.start()
    d = Dash(project, svc, clock, console)
    yield d
    svc.stop()


# ---------------------------------------------------------------------------------------------- the happy path


def test_bootstrap_sets_the_cookie_and_the_cookie_reads_the_api(dash: Dash):
    url = dash.svc.issue()
    assert re.fullmatch(re.escape(dash.svc.url) + r"/session/[A-Za-z0-9_-]{43}", url)
    status, headers, body = dash.exchange(url)
    assert status == 303 and headers["location"] == "/" and body == b""
    assert headers["cache-control"] == "no-store" and headers["referrer-policy"] == "no-referrer"
    credential = cookie_of(headers)
    assert "server" not in headers and "date" not in headers
    status, headers, project = dash.api("/project", credential)
    assert status == 200 and CONTRACT.violations(CT.RESPONSE_SCHEMAS["/project"], project) == []
    assert project["project_id"] == project["data"]["id"]
    status, _, caps = dash.api("/capabilities", credential)
    assert status == 200 and CONTRACT.violations(CT.RESPONSE_SCHEMAS["/capabilities"], caps) == []
    status, headers, _ = dash.api("/overview", credential, method="HEAD")
    assert status == 200 and "content-length" in headers
    # the engine's lookup is what verified it: the table holds the verifier, never the secret
    (record,) = dash.svc.table.tokens.values()
    assert record["verifier"] != credential.split(".")[2] and record["kind"] == authority.OPERATOR_SESSION
    assert dash.svc.table.live()[0]["token_id"] == credential.split(".")[1]


def test_the_endpoint_files_locate_the_server_and_never_hold_a_secret(dash: Dash):
    root = dash.svc.engine.aew_root
    info = json.loads((root / service.SERVER_JSON_REL).read_text(encoding="utf-8"))
    assert info["pid"] == os.getpid() and info["port"] == dash.svc.port and info["url"] == dash.svc.url
    key = (root / service.KEY_REL).read_text(encoding="utf-8").strip()
    assert key == dash.svc.control.key_hex
    if not IS_WINDOWS:
        assert (root / service.KEY_REL).stat().st_mode & 0o077 == 0
    found = service.locate(root)
    assert found and found["endpoint"] == dash.svc.control.address and found["key"] == key
    status = control.request_status(found["endpoint"], found["key"])
    assert status["running"] is True and status["port"] == dash.svc.port and status["sessions"] == []
    dash.bootstrap()
    sessions = control.request_status(found["endpoint"], found["key"])["sessions"]
    assert len(sessions) == 1 and set(sessions[0]) == {"token_id", "issued_at", "expires_at"}


# ---------------------------------------------------------------------------------------------- refusals (401)


def test_a_request_without_a_cookie_is_401_session_required(dash: Dash):
    for path in ("/project", "/work", "/overview", "/history/integrity"):
        status, headers, body = dash.api(path, None)
        assert status == 401 and body["code"] == "SESSION_REQUIRED", (path, body)
        assert CONTRACT.violations(CT.ERROR_SCHEMA, body) == []
        assert "set-cookie" not in headers  # nothing to expire
    status, _, _ = dash.api("/project", None, method="HEAD")
    assert status == 401


def test_forged_truncated_wrong_id_and_wrong_secret_cookies_are_401_and_expired_in_the_browser(dash: Dash):
    credential = dash.bootstrap()
    tid, secret = credential.split(".")[1:]
    other = S.SessionTable(dash.svc.project_id)
    foreign, _ = other.exchange(other.mint())  # a well-formed credential of a table this server never saw
    cases = {"forged": foreign, "truncated": credential[:-2], "wrong id": f"aew1.tk_0123456789abcdef.{secret}",
             "wrong secret": f"aew1.{tid}." + ("A" if secret[0] != "A" else "B") + secret[1:],
             "garbage": "not-a-credential", "empty": "", "lead-shaped": "aew1.tk_0123456789abcdef." + "A" * 43}
    for name, bad in cases.items():
        status, headers, body = dash.api("/project", bad)
        assert status == 401 and body["code"] == "SESSION_REQUIRED", (name, status, body)
        if bad:
            assert headers["set-cookie"] == S.expired_cookie(), name
    status, _, _ = dash.api("/project", credential)
    assert status == 200  # the real one still works


def test_an_expired_session_is_401_session_expired_by_the_injected_clock(dash: Dash):
    credential = dash.bootstrap()
    assert dash.api("/project", credential)[0] == 200
    dash.clock.offset = timedelta(hours=2, seconds=1)
    status, headers, body = dash.api("/project", credential)
    assert status == 401 and body["code"] == "SESSION_EXPIRED", body
    assert headers["set-cookie"] == S.expired_cookie()
    dash.svc.issue()  # a later minting keeps the expired record (the grace period), so the answer stays "expired"
    status, _, body = dash.api("/project", credential)
    assert status == 401 and body["code"] == "SESSION_EXPIRED", body
    dash.clock.offset = timedelta(hours=2, seconds=1) + S.EXPIRED_GRACE + timedelta(seconds=1)
    dash.svc.issue()  # beyond the grace the record is purged: now the cookie is unknown
    status, _, body = dash.api("/project", credential)
    assert status == 401 and body["code"] == "SESSION_REQUIRED", body


def test_a_displaced_session_is_401_session_expired(dash: Dash):
    first = dash.bootstrap()
    for _ in range(S.MAX_SESSIONS):
        dash.svc.issue()
    status, _, body = dash.api("/project", first)
    assert status == 401 and body["code"] == "SESSION_EXPIRED"
    assert len(dash.svc.table.live()) == S.MAX_SESSIONS


# ---------------------------------------------------------------------------------------------- the one-time URL


def test_the_one_time_url_used_twice_is_410_and_the_first_cookie_still_works(dash: Dash):
    url = dash.svc.issue()
    status, headers, _ = dash.exchange(url)
    credential = cookie_of(headers)
    status, headers, body = dash.exchange(url)
    assert status == 410 and headers["content-type"].startswith("text/html")
    assert "aew dashboard open" in body.decode() and url.rsplit("/", 1)[1] not in body.decode()
    assert "set-cookie" not in headers and headers["cache-control"] == "no-store"
    assert dash.api("/project", credential)[0] == 200


def test_unknown_expired_and_head_requests_never_yield_a_cookie(dash: Dash):
    status, headers, _ = dash.request("/session/" + "x" * 43)
    assert status == 410 and "set-cookie" not in headers
    status, headers, _ = dash.request("/session/")
    assert status == 410 and "set-cookie" not in headers
    url = dash.svc.issue()
    status, headers, body = dash.exchange(url, method="HEAD")
    assert status == 410 and "set-cookie" not in headers and body == b""  # a HEAD never spends a code
    assert dash.exchange(url)[0] == 303  # still unspent
    ticks = dash.svc.table.monotonic
    url = dash.svc.issue()
    dash.svc.table.monotonic = lambda: ticks() + S.CODE_TTL_S + 1
    try:
        status, headers, _ = dash.exchange(url)
    finally:
        dash.svc.table.monotonic = ticks
    assert status == 410 and "set-cookie" not in headers


def test_a_cross_site_navigation_is_refused_without_consuming_the_code(dash: Dash):
    url = dash.svc.issue()
    for hdrs in ({"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"},
                 {"Sec-Fetch-Site": "same-site"},
                 {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "cors"},
                 {"Sec-Fetch-Mode": "no-cors"},
                 {"Sec-Purpose": "prefetch"},  # a speculative prefetch must not spend the code
                 {"Purpose": "prefetch", "Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"}):
        status, headers, body = dash.exchange(url, headers=hdrs)
        assert status == 403 and "set-cookie" not in headers, hdrs
        assert "address bar" in body.decode() and url.rsplit("/", 1)[1] not in body.decode()
    status, headers, _ = dash.exchange(url, headers={"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"})
    assert status == 303 and cookie_of(headers)  # the pasted link still works


def test_without_a_table_the_session_route_does_not_exist(project: Project):
    class OpenAccess:
        def authenticate(self, headers: Any) -> dict[str, Any] | None:
            return None

    server = DashboardServer(Engine.discover(project.root), authenticator=OpenAccess())
    server.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
        conn.request("GET", "/session/" + "x" * 43)
        resp = conn.getresponse()
        assert resp.status == 404 and json.loads(resp.read())["code"] == "NOT_FOUND"
        conn.close()
    finally:
        server.stop()


# ---------------------------------------------------------------------------------------------- the process boundary


def test_stopping_the_server_ends_every_session_and_removes_the_endpoint(project: Project):
    clock, console = Clock(), Console()
    engine = Engine.discover(project.root)
    svc = service.Service(engine, port=0, hours=2, console=console, clock=clock)
    svc.start()
    d = Dash(project, svc, clock, console)
    credential = d.bootstrap()
    assert d.api("/project", credential)[0] == 200
    port = svc.port
    assert service.locate(engine.aew_root) is not None
    svc.stop()
    assert svc.table.tokens == {} and svc.table.pending_codes == 0
    with pytest.raises(errors.AEWError):
        svc.table.verify(credential)
    assert not (engine.aew_root / service.SERVER_JSON_REL).exists()
    assert not (engine.aew_root / service.KEY_REL).exists()
    assert service.locate(engine.aew_root) is None
    with pytest.raises(OSError):
        s = socket.create_connection(("127.0.0.1", port), timeout=2)
        s.close()


def test_clearing_the_table_makes_the_next_request_401(dash: Dash):
    credential = dash.bootstrap()
    dash.svc.table.clear()  # what `stop` does first
    status, _, body = dash.api("/project", credential)
    assert status == 401 and body["code"] == "SESSION_REQUIRED"


def test_a_stale_endpoint_file_names_no_server(project: Project, tmp_path: Path):
    root = Engine.discover(project.root).aew_root
    (root / service.DIR_REL).mkdir(parents=True, exist_ok=True)
    (root / service.KEY_REL).write_text("00" * 32, encoding="utf-8")
    (root / service.SERVER_JSON_REL).write_text(json.dumps({"pid": 2**22 - 1, "started_by": 1.0, "port": 1,
                                                            "control": {"endpoint": "x"}}), encoding="utf-8")
    assert service.locate(root) is None
    res = project.aew("dashboard", "status")
    assert res.returncode == 0 and res.json == {"running": False, "start": "aew dashboard serve"}
    # the real command with no terminal refuses before it looks for a server at all (the terminal check comes first)
    res = project.aew("dashboard", "open")
    assert res.error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED" and "terminal" in res.error["message"], res.error
    # with a terminal (substituted), the stale file is not trusted and the answer names the start command
    from aew import operator as op
    from aew.cli import dashboard_commands as dc
    from aew.cli.main import build_parser

    original = op.has_terminal
    op.has_terminal = lambda: True
    try:
        with pytest.raises(errors.NotFound, match="aew dashboard serve"):
            dc._open(build_parser().parse_args(["-C", str(project.root), "dashboard", "open"]))  # noqa: SLF001
    finally:
        op.has_terminal = original


def test_an_occupied_port_fails_and_never_moves(project: Project):
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen(1)
    port = taken.getsockname()[1]
    try:
        with pytest.raises(errors.UsageError, match="--port") as exc:
            service.Service(Engine.discover(project.root), port=port, console=None)
        assert exc.value.details["port"] == port
    finally:
        taken.close()


# ---------------------------------------------------------------------------------------------- aew dashboard open


def test_open_mints_exactly_one_session_with_the_code_from_the_servers_console(dash: Dash):
    found = service.locate(dash.svc.engine.aew_root)
    assert found
    before = len(dash.svc.table.live())
    seen: list[str] = []

    def ask(prompt: str) -> str:
        seen.append(prompt)
        return dash.console.last_code().lower()  # typed back, case-insensitively

    result = control.request_session(found["endpoint"], found["key"], ask=ask, requester="aew (1) <- test (0)")
    assert len(dash.svc.table.live()) == before + 1
    assert "requested by   : aew (1) <- test (0)" in dash.console.text and "aew dashboard open" in dash.console.text
    assert "Never give it to an agent or paste it into a chat" in dash.console.text  # the relay warning, every time
    assert not CODE_RE.search(seen[0]) and "aew dashboard serve" in seen[0]  # the code is never on this side
    assert result["expires_at"] == dash.svc.table.newest()["expires_at"]
    status, headers, _ = dash.exchange(result["session_url"])
    assert status == 303 and dash.api("/project", cookie_of(headers))[0] == 200
    assert dash.svc.control.opened == 1


def test_open_with_a_wrong_code_mints_nothing(dash: Dash):
    found = service.locate(dash.svc.engine.aew_root)
    assert found
    with pytest.raises(errors.PermissionDenied, match="refused or mistyped"):
        control.request_session(found["endpoint"], found["key"], ask=lambda prompt: "000000", requester="x")
    assert dash.svc.table.live() == [] and dash.svc.table.pending_codes == 0
    code = dash.console.last_code()
    with pytest.raises(errors.PermissionDenied):  # a shown code is void once answered
        control.request_session(found["endpoint"], found["key"], ask=lambda prompt: code, requester="x")
    assert dash.svc.table.live() == [] and dash.svc.control.opened == 0


def test_open_without_a_terminal_is_refused_before_anything_is_minted(dash: Dash):
    found = service.locate(dash.svc.engine.aew_root)
    assert found

    def no_terminal(prompt: str) -> str:
        raise errors.OperatorAuthorizationRequired("no terminal")

    with pytest.raises(errors.OperatorAuthorizationRequired):
        control.request_session(found["endpoint"], found["key"], ask=no_terminal, requester="x")
    assert dash.svc.table.live() == []
    # the real command, as a process with no terminal: refused by the delivery rule before it connects
    console_before = dash.console.text
    code, error = raw_aew(dash.p.root, "dashboard", "open")
    assert code == 2 and error["code"] == "USAGE" and "your terminal" in error["message"], error
    assert dash.svc.control.opened == 0 and dash.console.text == console_before  # no challenge was even shown
    # and with --print-credential (what the test runner adds): the command checks its own terminal before it contacts
    # the server, so the operator's console never shows a challenge nobody can answer (lead developer's review)
    res = dash.p.aew("dashboard", "open")
    assert res.error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED", res.error
    assert dash.svc.table.live() == [] and dash.svc.control.opened == 0 and dash.console.text == console_before


def test_open_times_out_and_one_challenge_at_a_time(dash: Dash):
    found = service.locate(dash.svc.engine.aew_root)
    assert found
    dash.svc.control.timeout = 0.3
    try:
        with pytest.raises(errors.PermissionDenied, match="timed out"):
            control.request_session(found["endpoint"], found["key"], ask=lambda p: (time.sleep(0.8), "")[1],
                                    requester="slow")
        assert dash.svc.table.live() == []
        dash.svc.control.timeout = 5.0
        gate = threading.Event()
        outcome: dict[str, Any] = {}

        def first() -> None:
            def ask(prompt: str) -> str:
                gate.wait(5)
                return dash.console.last_code()
            outcome["first"] = control.request_session(found["endpoint"], found["key"], ask=ask, requester="one")

        t = threading.Thread(target=first)
        t.start()
        for _ in range(100):
            if "requested by   : one" in dash.console.text:
                break
            time.sleep(0.05)
        with pytest.raises(errors.PermissionDenied, match="another"):
            control.request_session(found["endpoint"], found["key"], ask=lambda p: "x", requester="two")
        gate.set()
        t.join(10)
        assert "session_url" in outcome["first"] and len(dash.svc.table.live()) == 1
    finally:
        dash.svc.control.timeout = control.OPEN_TIMEOUT_S


def test_a_server_without_a_console_authorizes_nothing(project: Project):
    svc = service.Service(Engine.discover(project.root), port=0, console=None)
    svc.start()
    try:
        found = service.locate(svc.engine.aew_root)
        assert found
        with pytest.raises(errors.OperatorAuthorizationRequired, match="no console"):
            control.request_session(found["endpoint"], found["key"], ask=lambda p: "x", requester="x")
        assert svc.table.live() == []
    finally:
        svc.stop()


def test_the_control_channel_refuses_a_wrong_key_and_unknown_operations(dash: Dash):
    found = service.locate(dash.svc.engine.aew_root)
    assert found
    with pytest.raises(errors.PermissionDenied, match="refused this key"):
        control.request_status(found["endpoint"], "11" * 32)
    conn = control._connect(found["endpoint"], found["key"])  # noqa: SLF001
    try:
        conn.send_bytes(json.dumps({"op": "mint", "args": {}}).encode())
        with pytest.raises(errors.PermissionDenied, match="does not offer"):
            control._reply(conn)  # noqa: SLF001
    finally:
        conn.close()
    assert dash.svc.table.live() == []


# ---------------------------------------------------------------------------------------------- the commands


def test_serve_without_a_terminal_is_refused_before_anything_is_minted_or_bound(project: Project):
    root = Engine.discover(project.root).aew_root
    code, error = raw_aew(project.root, "dashboard", "serve", "--port", "0")
    assert code == 2 and error["code"] == "USAGE" and "your terminal" in error["message"], error
    assert not (root / service.SERVER_JSON_REL).exists()
    # a script's opt-in puts the URL on stdout, but the operator's typed-back code is still needed, at a terminal
    res = project.aew("dashboard", "serve", "--port", "0")  # the runner adds --print-credential
    assert res.error["code"] == "OPERATOR_AUTHORIZATION_REQUIRED", res.error
    assert not (root / service.SERVER_JSON_REL).exists() and not (root / service.KEY_REL).exists()
    res = project.aew("dashboard", "serve", "--session-hours", "0")
    assert res.error["code"] == "USAGE" and "session-hours" in res.error["message"]


def test_a_lead_session_refuses_both_commands(project: Project):
    env = {"AEW_LEAD_BROKER": "x", "AEW_LEAD_BROKER_KEY": "00"}
    for argv in (("dashboard", "serve"), ("dashboard", "open"), ("--print-credential", "dashboard", "open")):
        res = project.aew(*argv, env=env)
        assert res.error["code"] == "USAGE", (argv, res.error)
        assert "dashboard session URL" in res.error["message"] or "print-credential" in res.error["message"]
    res = project.aew("dashboard", "status", env=env)
    assert res.returncode == 0 and res.json["running"] is False


# ---------------------------------------------------------------------------------------------- disclosure


def test_the_secret_appears_in_no_file_log_or_response(dash: Dash, caplog):
    caplog.set_level(logging.INFO, logger="aew.dashboard")
    url = dash.svc.issue()
    code = url.rsplit("/", 1)[1]
    status, headers, _ = dash.exchange(url)
    credential = cookie_of(headers)
    secret = credential.split(".")[2]
    dash.api("/project", credential)
    dash.api("/work", credential)
    dash.exchange(url)  # the 410
    dash.api("/project", "aew1.tk_0123456789abcdef." + "A" * 43)
    found = service.locate(dash.svc.engine.aew_root)
    assert found
    control.request_status(found["endpoint"], found["key"])
    needles = [secret, code]
    for path in dash.svc.engine.aew_root.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            for needle in needles:
                assert needle.encode() not in data, path
    log = caplog.text
    assert "/session/<redacted>" in log
    for needle in needles:
        assert needle not in log
    for status, headers, body in dash.responses:
        if status == 303:
            continue  # the Set-Cookie of the exchange is the one delivery
        assert secret.encode() not in body and code.encode() not in body
        assert secret not in json.dumps(headers) and code not in json.dumps(headers)
    assert all("verifier" not in json.dumps(s) for s in dash.svc.table.live())


# ---------------------------------------------------------------------------------------------- the terminal (pty)


def _pty_serve(root: Path) -> tuple[str, int, str]:
    """Run `aew dashboard serve` at a real pseudo-terminal: answer the challenge, read the URL off the terminal,
    use it, interrupt the server. Returns (screen, exit code, server.json presence while running)."""
    import pty
    import select
    import signal

    argv = [sys.executable, "-m", "aew", "-C", str(root), "dashboard", "serve", "--port", "0"]
    pid, fd = pty.fork()
    if pid == 0:  # child: controlling terminal is the pty slave
        os.execvpe(argv[0], argv, clean_env())  # noqa: S606 (argv is fixed above)
    buf = b""
    answered = False
    url: str | None = None
    endpoint_seen = ""
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 1.0)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        if not answered:
            match = re.search(rb"confirmation code ([0-9A-F]{6})", buf)
            if match:
                os.write(fd, match.group(1) + b"\n")  # the operator reads the screen and types
                answered = True
        if url is None:
            match = re.search(rb"session_url: (http://127\.0\.0\.1:\d+/session/[A-Za-z0-9_-]+)", buf)
            if match and b'"session_url": "(written to your terminal)"' in buf:
                url = match.group(1).decode()
                endpoint_seen = (root / ".aew" / service.SERVER_JSON_REL).read_text(encoding="utf-8")
                base = url.split("/session/")[0]
                host, port = base[len("http://"):].split(":")
                conn = http.client.HTTPConnection(host, int(port), timeout=30)
                conn.request("GET", url[len(base):], headers={"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate"})
                resp = conn.getresponse()
                assert resp.status == 303, resp.status
                credential = cookie_of({k.lower(): v for k, v in resp.getheaders()})
                conn.close()
                conn = http.client.HTTPConnection(host, int(port), timeout=30)
                conn.request("GET", "/api/v1/project", headers={"Cookie": f"{S.COOKIE}={credential}"})
                assert conn.getresponse().status == 200
                conn.close()
                os.kill(pid, signal.SIGINT)
    _, status = os.waitpid(pid, 0)
    text = buf.decode("utf-8", "replace").replace("\r\n", "\n")
    return text, os.waitstatus_to_exitcode(status), endpoint_seen


@pytest.mark.serial  # a real pseudo-terminal and a forked child answering within a deadline
@pytest.mark.skipif(
    IS_WINDOWS,
    reason="POSIX pty operator path. A Windows console session would appear on the developer desktop, so on "
           "Windows the refusal paths are tested here and the console is substituted in-process",
)
def test_serve_at_a_real_terminal_shows_the_challenge_and_writes_the_url(project: Project):
    screen, code, endpoint = _pty_serve(project.root)
    assert "START the read-only dashboard" in screen and "requested by" in screen, screen
    assert "credential to  : this terminal only" in screen
    assert re.search(r"^session_url: http://127\.0\.0\.1:\d+/session/", screen, re.M), screen
    assert '"session_url": "(written to your terminal)"' in screen  # stdout carries the placeholder only
    assert code in (0, 130), (code, screen)
    assert '"pid"' in endpoint
    assert not (project.root / ".aew" / service.SERVER_JSON_REL).exists()  # removed on exit
