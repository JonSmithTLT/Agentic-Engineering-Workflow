"""Bounded loopback-only website fixture host, never a backend implementation.

Adds explicitly derived inherited waiting/run recordings. Other adopted routes
are forwarded to the designer's fixture server, as the handoff permits. Never
targets a live server or operator session. The upstream is a required, separately
started loopback fixture process. All local records are schema-validated first.
"""
import argparse
import base64
import copy
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "web/tests/fixtures/stg02"
VERSION = "0.3.4"


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
        value.update(fact_ref="fixture:" + value["fact_ref"], qualification="unqualified",
                     observation_state="unknown", governing_owner=None, authority_class="unqualified_report")
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
    item["links"].append({"relation": "source", "availability": "navigable", "target": {
        "kind": "execution_activity", "id": "invocation:demo-1", "revision": None,
        "generation": None, "package_digest": None}})
    return body


def run():
    body = unqualify(copy.deepcopy(load("run.json")))
    body["outcome"] = "partial"
    body["continuity"] = "unknown"
    body["limitations"] = ["source_unqualified"]
    body["items"][0]["data"]["work_ref"] = {
        "kind": "ticket", "id": "ticket:one", "revision": "revision:one",
        "generation": None, "package_digest": None}
    return body


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4252)
    parser.add_argument("--upstream-port", type=int, default=4254)
    parser.add_argument("--web-root", type=Path)
    parser.add_argument("--lifetime", type=int, default=900, choices=range(1, 3601))
    args = parser.parse_args()
    # The fixture library is shared with browser validation. Validate derived
    # data against the ORIGINAL 2020-12 schema independently before serving.
    from jsonschema import Draft202012Validator, FormatChecker
    schema = load("../../../src/stg02/contracts/d01.json")
    for name, value in [("ReadWaiting", waiting()), ("ReadRunDetail", run())]:
        Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/" + name}, format_checker=FormatChecker()).validate(value)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def emit(self, status, body, headers=None):
            payload = json.dumps(body).encode()
            self.send_response(status)
            selected = headers or {"Content-Type": "application/json", "X-AEW-Wire-Version": VERSION, "Cache-Control": "private, no-store"}
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
                target = (static_root / ("stg02.html" if path in {"/", "/stg02", "/stg02.html"} else unquote(path).lstrip("/"))).resolve()
                if not target.is_relative_to(static_root) or not target.is_file():
                    return self.problem(404, "not_found_or_not_disclosable")
                payload = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
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
                return self.emit(200, run()) if encoded == expected else self.problem(404, "not_found_or_not_disclosable")
            self.forward()

        def problem(self, status, code):
            return self.emit(status, {"type": "about:blank", "title": "Request could not be completed", "status": status,
                                      "code": code, "correlation_id": "fixture:web-stg02", "retry": "never"},
                             {"Content-Type": "application/problem+json", "X-AEW-Wire-Version": VERSION, "Cache-Control": "private, no-store"})

        def do_POST(self):
            if urlsplit(self.path).path != "/o01/v0/command-sets":
                return self.problem(404, "not_found_or_not_disclosable")
            self.forward()

        def forward(self):
            if not self.path.startswith(("/v1/read/", "/o01/v0/")):
                return self.problem(404, "not_found_or_not_disclosable")
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 65536:
                return self.problem(400, "invalid_request")
            body = self.rfile.read(length) if self.command == "POST" else None
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() in {"x-aew-wire-version", "x-aew-o01-wire", "content-type", "accept"}}
            request = Request(f"http://127.0.0.1:{args.upstream_port}" + self.path, data=body, headers=headers, method=self.command)
            try:
                with urlopen(request, timeout=10) as response:
                    self.emit(response.status, json.load(response), dict(response.headers))
            except HTTPError as failure:
                self.emit(failure.code, json.load(failure), dict(failure.headers))

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    timer = threading.Timer(args.lifetime, server.shutdown)
    timer.daemon = True
    timer.start()
    print(f"Synthetic STG-02 fixture wrapper listening on {args.port}; expires after {args.lifetime}s", flush=True)
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()


if __name__ == "__main__":
    main()
