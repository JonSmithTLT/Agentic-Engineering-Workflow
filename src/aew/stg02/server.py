"""The STG-02 slice's HTTP producer: the adopted D-01 0.3.4 reads and the O-01 0.2 command route, on 127.0.0.1.

    python -m aew.stg02.server --port 4261 --state-dir <dir> [--project <AEW repo>] [--fixture-recipient]
                               [--tokens <file>] [--test-routes] [--allow-origin <origin>]...
                               [--real-recipient <ref>] [--write-driver-config <file> [--driver-bearer <token>]]

Routes (``SLICE-FIELD-MAP.md``'s six steps):

    GET  /v1/read/waiting                              list, cursor
    GET  /v1/read/runs/{execution_id}                  run detail with progress
    GET  /v1/read/continuation-state/{work_id}         information only (C18, never C17)
    GET  /v1/read/owner-operations                     list, cursor
    POST /o01/v0/command-sets                          CONTINUE_ELIGIBLE_WORK admitted; every other action refused
                                                       or held; protected actions allocate nothing
    GET  /o01/v0/owner-operations/{owner}/{operation_ref}

This is **not** the dashboard server and not its provisional contract
(``docs/design/dashboard-api-v1-provisional.yaml``, ``/api/v1``). It runs as its own process, beside it; the two
contracts are not merged (STG-02 handoff, item 1).

**Who is asking.** The D-01 wire's security scheme is an opaque bearer (``readSession``). ``--tokens`` names a file of
synthetic tokens, ``{"<token>": "<recipient_ref>"}``; a request carrying an unknown or malformed ``Authorization`` is
``401``. AEW has no session issuer yet. The conformance driver sends the config's ``headers`` on every request:
``--driver-bearer`` writes one of the synthetic tokens there, so the driver authenticates like any client and its A1
check runs. ``--fixture-recipient`` lets a request **without** an ``Authorization`` header act as the fixture world's
recipient (labelled ``fixture:recipient-operator``), for the response recorder; never use it outside the slice.

**Order of checks.** The version header first (an absent or wrong version is refused ``400`` before any data, profile
cutover rules 1 and 2), then the recipient, then the route's own checks. Every D-01 answer, success or Problem,
carries ``X-AEW-Wire-Version: 0.3.4`` and ``Cache-Control: private, no-store``; every O-01 answer carries
``X-AEW-O01-Wire`` and the same ``Cache-Control``. The owner GET declares only 404, 409 and 503, so its malformed,
unauthenticated and wrong-version requests all get the one nondisclosing 404.

``--test-routes`` adds ``POST /_test/read-entitlement`` (``{"recipient_ref", "entitled"}``: driver case C17-N03) and
``POST /_test/engine-outage`` (``{"unavailable"}``: the real source's 503 path). They are off by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import socket
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from aew.stg02 import wire as W
from aew.stg02.commands import Carrier, Refused
from aew.stg02.ledger import Ledger, LedgerBusy
from aew.stg02.reads import LIMIT_DEFAULT, LIMIT_MAX, ReadProblem, Reads
from aew.stg02.world import EngineSource, Fixture

LOG = logging.getLogger("aew.stg02")
HOST = "127.0.0.1"
DEV_PORT = 4261  # the lead developer's dev port on the operator's machine
MAX_BODY = 64 * 1024
MAX_PATH = 2048
SOCKET_TIMEOUT_S = 10.0
COMMANDS = "/o01/v0/command-sets"
OWNER_GET = re.compile(r"/o01/v0/owner-operations/([^/]*)/([^/]*)")
OWNER_RE = re.compile(r"[A-Za-z][A-Za-z0-9:._/-]{2,127}")
OPREF_RE = re.compile(r"[A-Za-z][A-Za-z0-9:._-]{2,127}")
# Headers that decide the version, the recipient, the origin or the body: each must occur at most once (a repeated
# one is refused, never resolved last-wins; review of the slice, M5).
SINGLE_HEADERS = (W.D01_HEADER, W.O01_HEADER, "Authorization", "Host", "Origin", "Content-Length")
Clock = Callable[[], datetime]


class Slice:
    """The producer's state: the fixture world, the optional real engine source, the ledger and the clock."""

    def __init__(self, state_dir: Path, *, project: Path | None = None, tokens: dict[str, str] | None = None,
                 fixture_recipient: bool = False, test_routes: bool = False, allow_origins: tuple[str, ...] = (),
                 clock: Clock | None = None, world: Path | None = None, real_recipient: str | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.fx = Fixture.load(self.clock(), world) if world else Fixture.load(self.clock())
        self.engine = EngineSource(project) if project else None
        self.ledger = Ledger(state_dir / "stg02-ledger.sqlite3")
        with self.ledger.transaction() as t:
            t.seed_entitlement(list(self.fx.doc["read_entitled"]))
        self.reads = Reads(self.fx, self.engine, self.ledger, real_recipient=real_recipient or self.fx.recipient)
        self.carrier = Carrier(self.fx, self.ledger)
        self.tokens = dict(tokens or {})
        self.fixture_recipient = fixture_recipient
        self.test_routes = test_routes
        self.allow_origins = allow_origins

    def recipient(self, authorization: str | None) -> str | None:
        if authorization is None:
            return self.fx.recipient if self.fixture_recipient else None
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return self.tokens.get(token.strip())


class Answer:
    def __init__(self, status: int, body: Any, headers: dict[str, str]) -> None:
        self.status, self.body, self.headers = status, body, headers


def _d01(status: int, body: Any, *, problem: bool = False) -> Answer:
    return Answer(status, body, {W.D01_HEADER: W.D01_VERSION, W.NO_STORE[0]: W.NO_STORE[1],
                                 "Content-Type": W.PROBLEM_TYPE if problem else W.JSON_TYPE})


def _o01(status: int, body: Any, *, problem: bool = False) -> Answer:
    return Answer(status, body, {W.O01_HEADER: W.O01_VERSION, W.NO_STORE[0]: W.NO_STORE[1],
                                 "Content-Type": W.PROBLEM_TYPE if problem else W.JSON_TYPE})


def d01_problem(code: str, correlation: str) -> Answer:
    status, body = W.problem(code, correlation)
    return _d01(status, body, problem=True)


def o01_problem(code: str, correlation: str) -> Answer:
    status, body = W.problem(code, correlation)
    return _o01(status, body, problem=True)


def _family(raw_path: str) -> str | None:
    path = urlsplit(raw_path).path
    if path.startswith("/v1/read/"):
        return "D01"
    if path.startswith("/o01/v0/owner-operations/"):
        return "OWNER_GET"
    if path.startswith("/o01/"):
        return "O01"
    return None


def refusal(raw_path: str) -> Answer:
    """A request refused before routing (a foreign Host or Origin, an oversize request), as its route family's own
    Problem with its wire headers: invalid_request, or the owner GET's one nondisclosing 404 (it declares no 400)."""
    corr, fam = W.correlation_id(), _family(raw_path)
    if fam == "D01":
        return d01_problem("invalid_request", corr)
    if fam == "O01":
        return o01_problem("invalid_request", corr)
    if fam == "OWNER_GET":
        return o01_problem("not_found_or_not_disclosable", corr)
    return Answer(400, None, {"Content-Type": "text/plain"})


def failure(raw_path: str) -> Answer:
    """An unexpected error: the declared 503 of the route's family, never a bare 500 (profile cutover rule 1)."""
    corr, fam = W.correlation_id(), _family(raw_path)
    if fam == "D01":
        return d01_problem("owner_unavailable", corr)
    if fam in ("O01", "OWNER_GET"):
        return o01_problem("owner_unavailable", corr)
    return Answer(500, None, {"Content-Type": "text/plain"})


def handle(s: Slice, method: str, raw_path: str, headers: dict[str, str], body: bytes | None) -> Answer:
    """One request, routed and answered. ``headers`` are lower-cased."""
    corr = W.correlation_id()
    u = urlsplit(raw_path)
    path = u.path
    if path.startswith("/v1/read/"):
        return _read(s, method, path, u.query, headers, corr)
    if path == COMMANDS:
        return _command(s, method, headers, body, corr)
    if path.startswith("/o01/v0/owner-operations/"):
        return _owner_get(s, method, path, headers, corr)
    if s.test_routes and method == "POST" and path in ("/_test/read-entitlement", "/_test/engine-outage"):
        return _test_route(s, path, body)
    if path.startswith("/o01/"):  # an O-01 path no route matches: the family's refusal, with its wire headers
        return refusal(raw_path)
    return Answer(404, None, {"Content-Type": "text/plain"})


def _read(s: Slice, method: str, path: str, query: str, headers: dict[str, str], corr: str) -> Answer:
    if headers.get(W.D01_HEADER.lower()) != W.D01_VERSION or method != "GET":
        return d01_problem("invalid_request", corr)  # exact cutover: refused before any data
    recipient = s.recipient(headers.get("authorization"))
    if recipient is None:
        return d01_problem("authentication_unqualified", corr)
    try:
        q = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query))
    except ValueError:
        return d01_problem("invalid_request", corr)
    if any(len(v) != 1 for v in q.values()):
        return d01_problem("invalid_request", corr)
    one = {k: v[0] for k, v in q.items()}
    now = s.clock()
    try:
        if path == "/v1/read/waiting":
            _only(one, {"cursor", "limit"})
            return _d01(200, s.reads.waiting(recipient, _limit(one.get("limit")), one.get("cursor"), now, corr))
        if path == "/v1/read/owner-operations":
            _only(one, {"owner", "scope_ref", "attachment_ref", "cursor"})
            return _d01(200, s.reads.owner_operations(recipient, one.get("owner"), one.get("scope_ref"),
                                                      one.get("attachment_ref"), one.get("cursor"), now, corr))
        for prefix, call, lo, hi in (("/v1/read/runs/", s.reads.run, 1, 300),
                                     ("/v1/read/continuation-state/", s.reads.continuation, 2, 256)):
            if path.startswith(prefix) and "/" not in path[len(prefix):]:
                _only(one, set())
                try:
                    ident = W.decode_id(path[len(prefix):], min_len=lo, max_len=hi)
                except W.BadId:
                    return d01_problem("invalid_request", corr)
                return _d01(200, call(recipient, ident, now, corr))
    except ReadProblem as p:
        return d01_problem(p.code, corr)
    except LedgerBusy:
        return d01_problem("owner_unavailable", corr)
    # a D-01 route this slice does not serve (16 of the 20), or no route at all
    return d01_problem("not_found_or_not_disclosable", corr)


def _only(q: dict[str, str], allowed: set[str]) -> None:
    if set(q) - allowed:
        raise ReadProblem("invalid_request")


def _limit(raw: str | None) -> int:
    if raw is None:
        return LIMIT_DEFAULT
    if not re.fullmatch(r"[1-9][0-9]{0,2}", raw) or int(raw) > LIMIT_MAX:
        raise ReadProblem("invalid_request")
    return int(raw)


def _command(s: Slice, method: str, headers: dict[str, str], body: bytes | None, corr: str) -> Answer:
    if headers.get(W.O01_HEADER.lower()) != W.O01_VERSION or method != "POST":
        return o01_problem("invalid_request", corr)  # rule 2: refused, never transformed or dispatched
    recipient = s.recipient(headers.get("authorization"))
    if recipient is None:
        return o01_problem("authentication_unqualified", corr)
    if (headers.get("content-type") or "").split(";")[0].strip().lower() != W.JSON_TYPE or not body:
        return o01_problem("invalid_request", corr)
    try:
        req = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return o01_problem("invalid_request", corr)
    try:
        receipt, _ = s.carrier.submit(req, recipient, s.clock())
    except Refused as r:
        return o01_problem(r.code, corr)
    except LedgerBusy:
        return o01_problem("owner_unavailable", corr)
    return _o01(202, receipt)


def _owner_get(s: Slice, method: str, path: str, headers: dict[str, str], corr: str) -> Answer:
    m = OWNER_GET.fullmatch(path)
    recipient = s.recipient(headers.get("authorization"))
    if (method != "GET" or headers.get(W.O01_HEADER.lower()) != W.O01_VERSION or recipient is None or m is None
            or not OWNER_RE.fullmatch(m.group(1)) or not OPREF_RE.fullmatch(m.group(2))):
        return o01_problem("not_found_or_not_disclosable", corr)  # the route declares 404, 409 and 503 only
    try:
        body = s.carrier.owner_get(m.group(1), m.group(2), recipient, s.clock())
    except LedgerBusy:
        return o01_problem("owner_unavailable", corr)
    if body is None:
        return o01_problem("not_found_or_not_disclosable", corr)
    return _o01(200, body)


def _test_route(s: Slice, path: str, body: bytes | None) -> Answer:
    try:
        req = json.loads((body or b"{}").decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Answer(400, None, {"Content-Type": "text/plain"})
    if path == "/_test/read-entitlement":
        with s.ledger.transaction() as t:
            t.set_entitled(str(req.get("recipient_ref") or s.fx.recipient), bool(req.get("entitled")))
    elif s.engine is not None:
        s.engine.outage = bool(req.get("unavailable"))
    return Answer(204, None, {})


def make_server(s: Slice, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        timeout = SOCKET_TIMEOUT_S

        def _do(self, method: str) -> None:
            t0 = time.monotonic()
            h = {k.lower(): v for k, v in self.headers.items()}
            bound = cast(Any, self.server).server_port
            origin = h.get("origin")
            if any(len(self.headers.get_all(name) or []) > 1 for name in SINGLE_HEADERS):
                self._send(refusal(self.path), method, t0)  # an ambiguous selection is refused, never last-wins
                return
            if h.get("host") not in (f"{HOST}:{bound}", f"localhost:{bound}") or len(self.path) > MAX_PATH:
                self._send(refusal(self.path), method, t0)  # DNS rebinding, oversize
                return
            if origin is not None and origin not in s.allow_origins:
                self._send(refusal(self.path), method, t0)  # a page on another origin, not allowed by CORS
                return
            if method == "OPTIONS":
                # a CORS preflight, only from an allowed origin: it carries no data and needs no wire header
                self._send(Answer(204, None, {}) if origin else refusal(self.path), method, t0, preflight=True)
                return
            try:
                n = int(h.get("content-length") or 0)
            except ValueError:
                n = -1
            if n < 0 or n > MAX_BODY:
                self._send(refusal(self.path), method, t0)
                return
            body = self.rfile.read(n) if n else None
            try:
                answer = handle(s, method, self.path, h, body)
            except Exception:  # never a traceback to the client, and never an answer without the wire headers
                LOG.exception("aew stg02: request failed")
                answer = failure(self.path)
            self._send(answer, method, t0)

        def _send(self, a: Answer, method: str, t0: float, *, preflight: bool = False) -> None:
            raw = b"" if a.body is None else json.dumps(a.body, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(a.status)
            for k, v in a.headers.items():
                self.send_header(k, v)
            origin = self.headers.get("Origin")
            if origin is not None and origin in s.allow_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Expose-Headers", f"{W.D01_HEADER}, {W.O01_HEADER}")
                if preflight:
                    self.send_header("Access-Control-Allow-Methods", "GET, POST")
                    self.send_header("Access-Control-Allow-Headers",
                                     f"{W.D01_HEADER}, {W.O01_HEADER}, Authorization, Content-Type")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if method != "HEAD":  # a HEAD answer has the headers of the GET it stands for, and no body
                self.wfile.write(raw)
            LOG.info("%s %s %d %.0fms", method, urlsplit(self.path).path[:256], a.status, (time.monotonic() - t0) * 1e3)

        def __getattr__(self, name: str) -> Any:
            """Every method the request line names (GET, POST, OPTIONS, HEAD, PATCH, TRACE, ``get``, any token) reaches
            :meth:`_do`, so an unhandled one is the route family's refusal with its wire headers, never the stdlib's
            bare 501. Nothing else looks up a missing ``do_*`` attribute."""
            if name.startswith("do_"):
                return lambda: self._do(name[3:])
            raise AttributeError(name)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (stdlib signature)
            pass  # the request log is _send's line: no query, no header

    srv = ExclusiveServer((HOST, port), Handler)
    srv.daemon_threads = True
    return srv


class ExclusiveServer(ThreadingHTTPServer):
    """A port held by exactly one server: a second server on the same port fails to start instead of sharing it (a
    stale slice server once answered part of a new one's requests)."""

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32":  # pragma: windows-only
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def driver_config(s: Slice, bearer: str | None = None) -> dict[str, Any]:
    """The STG-02 driver's config for this world, derived from the same intents the delegations are bound to (so a
    delegation's intent digest and the configured intent cannot drift apart). ``bearer``, a synthetic token this
    server maps to the world's recipient, goes in the ``headers`` the driver sends on every request."""
    fx, rcpt = s.fx, s.fx.recipient
    if bearer is not None and s.tokens.get(bearer) != rcpt:
        raise ValueError(f"--driver-bearer: --tokens does not map that token to {rcpt}")

    def cset(key: str, intents: list[dict[str, Any]], consent: str | None = None) -> dict[str, Any]:
        return {"wire_version": W.O01_VERSION, "request_set_ref": f"fixture:request-{key}",
                "client_request_key": f"fixture:key-{key}", "recipient_ref": rcpt, "installation_ref": fx.installation,
                "consent_set_ref": consent, "intents": intents}

    heb = fx.heb
    attach = {"intent_ref": "fixture:intent-attach-lead", "action": "ATTACH_LEAD", "actor_ref": rcpt,
              "authority_class": "OPERATOR_RESERVED", "owner_hint": "HEB",
              "subject": {"project_ref": fx.doc["project_ref"], "installation_ref": fx.installation,
                          "attachment_ref": None, "generation_ref": None},
              "predecessor": {"basis_ref": "fixture:basis-attach", "basis_version": "fixture:revision-1",
                              "source_epoch": heb["epoch"]},
              "target": {"project_ref": fx.doc["project_ref"], "profile_binding_ref": "fixture:profile-1",
                         "requested_lead_ref": "fixture:lead-2", "seat_class": "LEAD"},
              "origin_proof_ref": "fixture:origin-proof-never-issued", "delegated_grant_proof_ref": None}
    not_granted = json.loads(json.dumps(fx.intents["continue"]))
    not_granted["target"]["work_revision"] = "fixture:revision-2"  # a revision the delegation does not name (N22)
    withdraw = {"method": "post", "path": "/_test/read-entitlement", "body": {"recipient_ref": rcpt, "entitled": False}}
    restore = {"method": "post", "path": "/_test/read-entitlement", "body": {"recipient_ref": rcpt, "entitled": True}}
    return {
        **({"headers": {"Authorization": f"Bearer {bearer}"}} if bearer is not None else {}),
        "_note": ("Generated by `python -m aew.stg02.server --write-driver-config` from the slice's fixture world. "
                  "No read sets matches_fixture: every fact this backend serves is unqualified, so no envelope can "
                  "equal a recorded positive one (docs/stg02/BACKEND-REPORT.md, the R6 SKIPs)."),
        "reads": [
            {"route": "/v1/read/waiting", "query": {"limit": 20}},
            {"route": "/v1/read/runs/{execution_id}", "params": {"execution_id": W.b64url("fixture:run-continue-1")},
             "unknown_params": {"execution_id": W.b64url("fixture:run-unknown")}},
            {"route": "/v1/read/continuation-state/{work_id}",
             "params": {"work_id": W.b64url("fixture:ticket-continue")},
             "unknown_params": {"work_id": W.b64url("fixture:ticket-unknown")}},
            {"route": "/v1/read/owner-operations", "query": {"scope_ref": fx.doc["scope_ref"]}}],
        "command": {"continue_eligible_work": cset("continue", [fx.intents["continue"]]),
                    "protected_without_g3": cset("attach-lead-no-g3", [attach], "fixture:consent-never-issued")},
        "c17_cases": {
            "C17-N01": {"request": cset("c17-n01", [fx.intents["continue-expired"]])},
            "C17-N02": {"request": cset("c17-n02", [not_granted])},
            "C17-N03": {"request": cset("c17-n03", [fx.intents["retry"]]), "setup": [withdraw], "teardown": [restore]}},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m aew.stg02.server", description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--port", type=int, default=DEV_PORT)
    ap.add_argument("--state-dir", type=Path, required=True, help="where the key ledger and owner records live")
    ap.add_argument("--project", type=Path, help="an AEW project's repository root: the real source of work and runs")
    ap.add_argument("--tokens", type=Path, help='a JSON file of synthetic bearer tokens {"<token>": "<recipient_ref>"}')
    ap.add_argument("--real-recipient", help="the one recipient AEW's own records are disclosed to "
                                             "(default: the fixture world's recipient)")
    ap.add_argument("--fixture-recipient", action="store_true",
                    help="a request without Authorization acts as the fixture world's recipient (slice only)")
    ap.add_argument("--test-routes", action="store_true", help="serve the test-only /_test/ routes")
    ap.add_argument("--allow-origin", action="append", default=[], help="an exact browser origin allowed by CORS")
    ap.add_argument("--write-driver-config", type=Path, help="write the STG-02 driver config for this world, and exit")
    ap.add_argument("--driver-bearer", help="a synthetic token from --tokens for the world's recipient, written into "
                                            "the driver config's headers")
    a = ap.parse_args(argv)
    tokens = json.loads(a.tokens.read_text(encoding="utf-8")) if a.tokens else None
    s = Slice(a.state_dir, project=a.project, tokens=tokens, fixture_recipient=a.fixture_recipient,
              test_routes=a.test_routes, allow_origins=tuple(a.allow_origin), real_recipient=a.real_recipient)
    if a.write_driver_config:
        try:
            cfg = driver_config(s, a.driver_bearer)
        except ValueError as exc:
            print(f"aew stg02: {exc}", file=sys.stderr)
            return 2
        a.write_driver_config.write_text(json.dumps(cfg, indent=1) + "\n", encoding="utf-8", newline="\n")
        return 0
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    srv = make_server(s, a.port)
    if a.fixture_recipient and a.project:
        print("aew stg02: --fixture-recipient with --project: any local process can read this project's engine state "
              "through the server without a token", file=sys.stderr, flush=True)
    print(f"aew stg02 slice producer on http://{HOST}:{srv.server_port}", file=sys.stderr, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
