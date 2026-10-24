"""Bounded loopback-only STG-02 website test host.

Adds explicitly derived inherited waiting/run recordings. Other adopted routes
are forwarded to the designer's fixture server, as the handoff permits. Never
targets an operator session. Fixture mode validates all local records first.
Explicit joint mode serves static web assets but forwards every API route to the
separately started synthetic joint backend, without fixture substitution.
"""

import argparse
import base64
import copy
import http.client
import json
import mimetypes
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "web/tests/fixtures/stg02"
VERSION = "0.3.4"


class LoopbackHTTPServer(ThreadingHTTPServer):
    # SO_REUSEADDR on Windows permits competing listeners, unlike POSIX.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def load(name):
    return json.loads((FIXTURES / name).read_text())


def unqualify(value):
    """Derived fixture provenance, never rewriting the original recordings."""
    if isinstance(value, list):
        return [unqualify(x) for x in value]
    if not isinstance(value, dict):
        return value
    value = {key: unqualify(child) for key, child in value.items()}
    if {"fact_ref", "observation_state", "qualification"}.issubset(value):
        value.update(
            fact_ref="fixture:" + value["fact_ref"],
            qualification="unqualified",
            observation_state="unknown",
            governing_owner=None,
            authority_class="unqualified_report",
        )
    return value


def waiting():
    body = unqualify(copy.deepcopy(load("waiting.json")))
    body["outcome"] = "partial"
    body["continuity"] = "unknown"
    body["limitations"] = ["source_unqualified"]
    body["items"] = body["items"][:1]
    body["page"]["membership"] = "unknown"
    item = body["items"][0]
    item["data"]["work"]["id"] = "ticket:one"
    item["data"]["work"]["revision"] = "revision:one"
    item["links"].append(
        {
            "relation": "source",
            "availability": "navigable",
            "target": {
                "kind": "execution_activity",
                "id": "invocation:demo-1",
                "revision": None,
                "generation": None,
                "package_digest": None,
            },
        }
    )
    return body


def run():
    body = unqualify(copy.deepcopy(load("run.json")))
    body["outcome"] = "partial"
    body["continuity"] = "unknown"
    body["limitations"] = ["source_unqualified"]
    body["items"][0]["data"]["work_ref"] = {
        "kind": "ticket",
        "id": "ticket:one",
        "revision": "revision:one",
        "generation": None,
        "package_digest": None,
    }
    return body


def create_server(port, upstream_port, web_root=None, *, mode="fixture"):
    if mode not in {"fixture", "joint"} or not 1 <= upstream_port <= 65535:
        raise ValueError("Explicit fixture/joint mode and valid loopback upstream port required")
    if port != 0 and port == upstream_port:
        raise ValueError("Wrapper cannot forward to itself")
    args = argparse.Namespace(port=port, upstream_port=upstream_port, web_root=Path(web_root) if web_root else None)
    # The fixture library is shared with browser validation. Validate derived
    # data against the ORIGINAL 2020-12 schema independently before serving.
    if mode == "fixture":
        from jsonschema import Draft202012Validator, FormatChecker

        schema = load("../../../src/stg02/contracts/d01.json")
        for name, value in [("ReadWaiting", waiting()), ("ReadRunDetail", run())]:
            Draft202012Validator(
                {"$defs": schema["$defs"], "$ref": "#/$defs/" + name}, format_checker=FormatChecker()
            ).validate(value)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def emit(self, status, body, headers=None):
            payload = json.dumps(body).encode()
            self.send_response(status)
            selected = headers or {
                "Content-Type": "application/json",
                "X-AEW-Wire-Version": VERSION,
                "Cache-Control": "private, no-store",
            }
            for key, value in selected.items():
                if key.lower() not in {"content-length", "connection", "server", "date", "transfer-encoding"}:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path
            if args.web_root and (path in {"/", "/stg02", "/stg02.html"} or path.startswith("/assets/")):
                static_root = args.web_root.resolve()
                target = (
                    static_root
                    / ("stg02.html" if path in {"/", "/stg02", "/stg02.html"} else unquote(path).lstrip("/"))
                ).resolve()
                if not target.is_relative_to(static_root) or not target.is_file():
                    return self.problem(404, "not_found_or_not_disclosable")
                payload = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                    "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                    "frame-ancestors 'none'; form-action 'self'",
                )
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
                return
            if mode == "joint":
                return self.forward_joint()
            if path == "/v1/read/waiting" or path.startswith("/v1/read/runs/"):
                if self.headers.get("X-AEW-Wire-Version") != VERSION:
                    return self.problem(400, "invalid_request")
                if path == "/v1/read/waiting":
                    if set(parse_qs(urlsplit(self.path).query)) - {"limit", "cursor"}:
                        return self.problem(400, "invalid_request")
                    if "cursor" in parse_qs(urlsplit(self.path).query):
                        return self.problem(409, "stale_cursor")
                    return self.emit(200, waiting())
                encoded = unquote(path.rsplit("/", 1)[-1])
                expected = base64.urlsafe_b64encode(b"invocation:demo-1").decode().rstrip("=")
                return (
                    self.emit(200, run()) if encoded == expected else self.problem(404, "not_found_or_not_disclosable")
                )
            self.forward()

        def problem(self, status, code):
            return self.emit(
                status,
                {
                    "type": "about:blank",
                    "title": "Request could not be completed",
                    "status": status,
                    "code": code,
                    "correlation_id": "fixture:web-stg02",
                    "retry": "never",
                },
                {
                    "Content-Type": "application/problem+json",
                    "X-AEW-Wire-Version": VERSION,
                    "Cache-Control": "private, no-store",
                },
            )

        def do_POST(self):
            if mode == "joint":
                return self.forward_joint()
            if urlsplit(self.path).path != "/o01/v0/command-sets":
                return self.problem(404, "not_found_or_not_disclosable")
            self.forward()

        def do_HEAD(self):
            if mode == "joint":
                return self.do_GET()
            self.send_error(405)

        def other_method(self):
            if mode == "joint":
                return self.forward_joint()
            self.send_error(405)

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = other_method

        def transport_error(self, status, message):
            payload = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def forward_joint(self):
            # Never repair a version/header/body, follow a redirect, interpret a
            # stamp, or replay a request. The browser validates what it receives.
            if not self.path.startswith(("/v1/read/", "/o01/v0/")):
                return self.transport_error(404, "Outside the joint API route prefixes")
            length = self.headers.get("Content-Length", "0")
            if self.headers.get("Transfer-Encoding") or not length.isdecimal() or int(length) > 65536:
                return self.transport_error(400, "Unsupported request framing or body exceeds 64 KiB")
            self.connection.settimeout(10)
            try:
                body = self.rfile.read(int(length))
            except OSError:
                return self.transport_error(400, "Incomplete request body")
            if len(body) != int(length):
                return self.transport_error(400, "Incomplete request body")
            # The joint brief explicitly excludes Authorization and Cookie.
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() in {"x-aew-wire-version", "x-aew-o01-wire", "content-type", "accept"}
            }
            connection = http.client.HTTPConnection("127.0.0.1", args.upstream_port, timeout=10)
            try:
                connection.request(self.command, self.path, body=body or None, headers=headers)
                response = connection.getresponse()
                status, reason, received_headers = response.status, response.reason, response.getheaders()
                lengths = [value for key, value in received_headers if key.lower() == "content-length"]
                if (
                    len(lengths) > 1
                    or (lengths and not lengths[0].isascii())
                    or (lengths and not lengths[0].isdecimal())
                ):
                    raise ValueError("Invalid upstream response framing")
                if lengths and response.getheader("Transfer-Encoding"):
                    raise ValueError("Conflicting upstream response framing")
                payload = response.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    raise ValueError("Response exceeds test-tool transport bound")
                if lengths and self.command != "HEAD" and status not in {204, 304} and len(payload) != int(lengths[0]):
                    raise ValueError("Truncated upstream response")
            except (OSError, http.client.HTTPException, ValueError):
                return self.transport_error(
                    502,
                    "Upstream transport failed; no backend representation is established. "
                    "A command outcome may be unknown. No fixture was substituted.",
                )
            finally:
                connection.close()
            hop = {
                "connection",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailer",
                "transfer-encoding",
                "upgrade",
                "content-length",
            }
            for key, value in received_headers:
                if key.lower() == "connection":
                    hop.update(part.strip().lower() for part in value.split(","))
            self.send_response_only(status, reason)
            for key, value in received_headers:
                if key.lower() not in hop:
                    self.send_header(key, value)
            head_length = next((value for key, value in received_headers if key.lower() == "content-length"), None)
            self.send_header(
                "Content-Length",
                head_length
                if self.command == "HEAD" and head_length and head_length.isdecimal()
                else str(len(payload)),
            )
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def forward(self):
            if not self.path.startswith(("/v1/read/", "/o01/v0/")):
                return self.problem(404, "not_found_or_not_disclosable")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 65536:
                return self.problem(400, "invalid_request")
            body = self.rfile.read(length) if self.command == "POST" else None
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() in {"x-aew-wire-version", "x-aew-o01-wire", "content-type", "accept"}
            }
            request = Request(
                f"http://127.0.0.1:{args.upstream_port}" + self.path, data=body, headers=headers, method=self.command
            )
            try:
                # Fixture-only URL above has a fixed HTTP loopback host and numeric port.
                with urlopen(request, timeout=10) as response:  # noqa: S310
                    self.emit(response.status, json.load(response), dict(response.headers))
            except HTTPError as failure:
                self.emit(failure.code, json.load(failure), dict(failure.headers))

    return LoopbackHTTPServer(("127.0.0.1", args.port), Handler)


def main():
    def port_number(value):
        number = int(value)
        if not 1 <= number <= 65535:
            raise argparse.ArgumentTypeError("Port must be between 1 and 65535")
        return number

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["fixture", "joint"], default="fixture")
    parser.add_argument("--port", type=port_number, default=4252)
    parser.add_argument("--upstream-port", type=port_number)
    parser.add_argument("--web-root", type=Path)
    parser.add_argument("--lifetime", type=int, default=900, choices=range(1, 3601))
    args = parser.parse_args()
    if args.mode == "joint" and (args.upstream_port is None or args.web_root is None):
        parser.error("Joint mode requires explicit --upstream-port and --web-root")
    server = create_server(args.port, args.upstream_port or 4254, args.web_root, mode=args.mode)
    timer = threading.Timer(args.lifetime, server.shutdown)
    timer.daemon = True
    timer.start()
    print(
        f"STG-02 {args.mode} wrapper listening on {args.port}; "
        f"upstream loopback port {args.upstream_port or 4254}; "
        f"expires after {args.lifetime}s; no startup upstream requests",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
