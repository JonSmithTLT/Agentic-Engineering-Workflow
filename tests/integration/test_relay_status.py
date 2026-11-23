"""Recorded provider responses through the project status CLI."""

from __future__ import annotations

import http.client
import http.server
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager

from tcp_pair import tcp_pair

from aew.harness import runlog
from aew.harness.containment import relay


@contextmanager
def provider_endpoint():
    calls = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def answer(self, status):
            calls.append((self.command, self.path, self.headers.get("Authorization")))
            body = b"synthetic-provider-body-marker"
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.answer(401)

        def do_GET(self):
            self.answer(200)

        def log_message(self, *_):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield relay.Upstream(f"http://127.0.0.1:{server.server_port}/v1"), calls
        finally:
            server.shutdown()
            thread.join(5)


def request(service, *, method, path, headers):
    client, served = tcp_pair()
    with ThreadPoolExecutor(1) as pool, closing(client):
        handling = pool.submit(service.handle, served)
        connection = http.client.HTTPConnection("localhost", timeout=5)
        connection.sock = client
        with closing(connection):
            connection.request(method, path, headers=headers)
            with connection.getresponse() as response:
                response.read()
                status = response.status
        handling.result(timeout=5)
    return status


def test_model_failure_stays_visible_after_a_models_list_succeeds(project):
    root = project.root / ".aew"
    run = "R-INV-0001-1"
    directory = runlog.run_dir(root, run)
    directory.mkdir(parents=True)
    journal = directory / runlog.RELAY_REQUESTS
    key, token = "synthetic-relay-status-key", relay.sentinel()
    revision = project.rev()
    with provider_endpoint() as (upstream, calls), closing(relay.ProviderRelay(
            upstream, {token: key}, route="openai", login="key",
            record=relay.RequestLog(journal))) as service:
        assert request(service, method="POST", path="/v1/responses?private-query-marker",
                       headers={"Authorization": f"Bearer {token}"}) == 401
        assert request(service, method="GET", path="/v1/models", headers={}) == 200
        before = journal.read_bytes()
        assert b"private-query-marker" not in before and b"synthetic-provider-body-marker" in before
        view = project.ok("status", "--json")["relay"]["routes"]["openai"]
        model = view["last_model"]
        assert model == {"run": run, "role": "worker", "at": json.loads(before.splitlines()[0])["at"],
                         "operation": "model", "login": "key", "swap": "swapped", "outcome": "forwarded",
                         "status": 401, "answered": 401, "reason": None}
        assert view["last_request"]["operation"] == "models_list" and view["last_request"]["status"] == 200
        assert view["counts"] == {"upstream_2xx": 1, "upstream_non_2xx": 1, "refused": 0, "unknown": 0}
        text = project.aew("status").stdout
        assert f"Last recognized model request: upstream HTTP 401, key login, swap swapped, {model['at']}" in text
        assert "Last provider request (models_list): upstream HTTP 200" in text
        assert not any(secret in text + json.dumps(view) for secret in
                       (key, token, "private-query-marker", "synthetic-provider-body-marker"))
        assert journal.read_bytes() == before

        assert request(service, method="POST", path="/v1/responses",
                       headers={"Authorization": f"Bearer {relay.sentinel()}"}) == 401
        refused = project.ok("status", "--json")["relay"]["routes"]["openai"]
        assert refused["counts"] == dict(view["counts"], refused=1)
        last = refused["last_model"]
        assert last["answered"] == 401 and last["status"] is None and last["swap"] == "refused_unknown_placeholder"
        assert "relay refused HTTP 401 (stale_placeholder)" in project.aew("status").stdout
        assert calls == [("POST", "/v1/responses?private-query-marker", f"Bearer {key}"), ("GET", "/v1/models", None)]
    assert project.rev() == revision


def test_status_selects_each_route_across_retained_runs_and_handles_incomplete_history(project):
    root = project.root / ".aew"
    empty = {"partial": False, "routes": {}}
    assert project.ok("status", "--json")["relay"] == empty
    wid = project.lead("work", "create", "ticket", "--title", "Relay test", "--class", "1")["id"]
    assert "relay" not in project.ok("status", wid, "--json")
    row = {"at": "2026-01-04T01:02:03Z", "route": "openai", "swap": "none", "login": "none",
           "outcome": "forwarded", "status": 201, "answered": 201, "reason": None}
    worker, lead = "R-INV-0001-1", "lead-20260104T010203Z-abcdef"
    for run, rows in [
            (lead, [dict(row, status=400, answered=400, operation="model"),
                    dict(row, status=429, answered=429, operation="model")]),
            ("R-INV-0001-2", []),  # pre-journal run
            ("doctor-20260104T010210Z-aabbcc", [dict(row, at="2026-01-04T01:02:10Z", operation="model")]),
            (worker, [dict(row, operation="model"), dict(row, route="anthropic"),
                      dict(row, at="2026-01-04T01:02:00Z", operation="model")])]:
        directory = runlog.run_dir(root, run)
        directory.mkdir(parents=True)
        for entry in rows:
            relay.RequestLog(directory / runlog.RELAY_REQUESTS)(entry)
    path = runlog.run_dir(root, worker) / runlog.RELAY_REQUESTS
    with path.open("ab") as out:
        out.write(b"{}\n{")  # invalid complete row, followed by an unfinished append
    report = project.ok("status", "--json")["relay"]
    assert report["partial"] and sorted(report["routes"]) == ["anthropic", "openai"]
    openai, anthropic = report["routes"]["openai"], report["routes"]["anthropic"]
    assert openai["last_model"]["run"] == lead and openai["last_model"]["status"] == 429
    assert openai["counts"] == {"upstream_2xx": 2, "upstream_non_2xx": 2, "refused": 0, "unknown": 0}
    assert anthropic["last_model"] is None and anthropic["last_request"]["operation"] == "unknown"
    assert anthropic["last_request"]["status"] == 201
    text = project.aew("status").stdout
    assert "Partial history" in text and "Last recognized model request: none recorded" in text


def test_an_unreadable_journal_does_not_prevent_project_status(project):
    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-1")
    (directory / runlog.RELAY_REQUESTS).mkdir(parents=True)
    report = project.ok("status", "--json")
    assert report["relay"] == {"partial": True, "routes": {}}
    assert report["revision"] == project.rev() and "work_graph" in report
