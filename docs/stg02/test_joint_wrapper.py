"""Standalone wrapper tests: synthetic upstream only, no Engine imports/state."""
import http.client
import importlib.util
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("website_wrapper", Path(__file__).with_name("serve_recordings.py"))
wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrapper)


class JointWrapperTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        seen = self.seen

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                seen.append((self.command, self.path, dict(self.headers), body))
                status = 409 if "problem" in self.path else 307 if "redirect" in self.path else 200
                payload = b'{ "upstream_only": true, "stamp": "not interpreted", "value": 1, "value": 2 }\n'
                self.send_response(status)
                if "missing-headers" not in self.path:
                    self.send_header("Content-Type", "application/problem+json" if status == 409 else "application/json; charset=utf-8")
                    self.send_header("Cache-Control", "private, no-store")
                    self.send_header("X-AEW-Wire-Version", "backend-supplied-value")
                if status == 307:
                    self.send_header("Location", "/v1/read/should-not-follow")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)

            do_GET = do_POST = do_HEAD = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = handle_request

        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        self.upstream_thread = threading.Thread(target=self.upstream.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.upstream_thread.start()
        self.temp = tempfile.TemporaryDirectory()
        self.static = Path(self.temp.name)
        (self.static / "stg02.html").write_bytes(b"<title>exact frozen fixture build</title>")
        self.local_fixture = patch.object(wrapper, "waiting", side_effect=AssertionError("joint mode read a local fixture"))
        self.local_fixture.start()
        self.server = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        self.upstream.shutdown()
        self.upstream.server_close()
        self.local_fixture.stop()
        self.temp.cleanup()

    def start(self, upstream_port=None, *, mode="joint"):
        self.server = wrapper.create_server(0, upstream_port or self.upstream.server_port, self.static, mode=mode)
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()

    def request(self, method, path, body=None, headers=None):
        # Bound the wait above the wrapper's ten-second transport deadline;
        # Windows may delay reporting a closed upstream socket.
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=12)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_static_startup_does_not_probe_or_initialize_upstream(self):
        self.start()
        self.assertEqual(self.seen, [])
        status, headers, body = self.request("GET", "/stg02")
        self.assertEqual(status, 200)
        self.assertEqual(body, (self.static / "stg02.html").read_bytes())
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(self.seen, [])

    def test_all_api_paths_preserve_raw_body_query_status_and_source_headers(self):
        self.start()
        for path in ["/v1/read/waiting?limit=25&cursor=opaque%3Aa%2Fb", "/v1/read/runs/ZXhhY3Q", "/v1/read/continuation-state/ZXhhY3Q", "/v1/read/owner-operations", "/o01/v0/owner-operations/HEB/op%3Aone", "/v1/read/future-route/problem"]:
            with self.subTest(path=path):
                status, headers, body = self.request("GET", path, headers={"X-AEW-Wire-Version": "exact-request-version"})
                self.assertEqual(status, 409 if "problem" in path else 200)
                self.assertEqual(body, b'{ "upstream_only": true, "stamp": "not interpreted", "value": 1, "value": 2 }\n')
                self.assertEqual(headers["X-AEW-Wire-Version"], "backend-supplied-value")
                self.assertEqual(headers["Cache-Control"], "private, no-store")
                self.assertEqual(self.seen[-1][1], path)
                self.assertEqual(self.seen[-1][2]["X-AEW-Wire-Version"], "exact-request-version")

    def test_post_bytes_and_methods_are_not_rewritten_and_credentials_are_not_forwarded(self):
        self.start()
        body = b' { "client_request_key": "key:exact", "intents": [] }\n'
        for method in ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
            with self.subTest(method=method):
                self.request(method, "/o01/v0/command-sets?opaque=%2F", body, {"Content-Type": "application/json", "X-AEW-O01-Wire": "exact-o01", "Authorization": "synthetic-not-a-credential", "Cookie": "synthetic=not-a-session"})
                received = self.seen[-1]
                self.assertEqual(received[:2], (method, "/o01/v0/command-sets?opaque=%2F"))
                self.assertEqual(received[3], body)
                self.assertEqual(received[2]["X-AEW-O01-Wire"], "exact-o01")
                self.assertNotIn("Authorization", received[2])
                self.assertNotIn("Cookie", received[2])

    def test_missing_headers_and_redirects_are_not_repaired_or_followed(self):
        self.start()
        _, headers, _ = self.request("GET", "/v1/read/missing-headers")
        self.assertNotIn("X-AEW-Wire-Version", headers)
        self.assertNotIn("Content-Type", headers)
        before = len(self.seen)
        status, headers, _ = self.request("GET", "/v1/read/redirect")
        self.assertEqual(status, 307)
        self.assertEqual(headers["Location"], "/v1/read/should-not-follow")
        self.assertEqual(len(self.seen), before + 1)

    def test_head_forwards_without_a_body_and_preserves_representation_length(self):
        self.start()
        status, headers, body = self.request("HEAD", "/v1/read/waiting")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertGreater(int(headers["Content-Length"]), 0)
        self.assertEqual(self.seen[-1][0], "HEAD")

    def test_unreachable_backend_is_transport_failure_not_fixture_data(self):
        port = self.upstream.server_port
        self.upstream.shutdown()
        self.upstream.server_close()
        self.start(port)
        status, headers, body = self.request("GET", "/v1/read/waiting")
        self.assertEqual(status, 502)
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertNotIn("X-AEW-Wire-Version", headers)
        self.assertIn(b"no backend representation", body)

    def test_non_api_routes_are_not_forwarded(self):
        self.start()
        status, _, _ = self.request("POST", "/_test/engine-outage", b"{}")
        self.assertEqual(status, 404)
        self.assertEqual(self.seen, [])

    def test_fixture_mode_still_answers_waiting_locally(self):
        self.local_fixture.stop()
        self.start(mode="fixture")
        status, headers, body = self.request("GET", "/v1/read/waiting", headers={"X-AEW-Wire-Version": "0.3.4"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-AEW-Wire-Version"], "0.3.4")
        self.assertIn(b"fixture:CNI:fact:01", body)
        self.assertNotIn(b"upstream_only", body)
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
