"""Recorded provider responses through the project status CLI."""

from __future__ import annotations

import http.client
import http.server
import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from types import SimpleNamespace

from tcp_pair import tcp_pair

from aew.harness import runlog
from aew.harness.containment import netns, relay


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
            upstream, {token: key}, route="gateway+west:chat@v2", login="key",
            record=relay.RequestLog(journal))) as service:
        assert request(service, method="POST", path="/v1/responses?private-query-marker",
                       headers={"Authorization": f"Bearer {token}"}) == 401
        assert request(service, method="GET", path="/v1/models", headers={}) == 200
        before = journal.read_bytes()
        assert b"private-query-marker" not in before and b"synthetic-provider-body-marker" in before
        view = project.ok("status", "--json")["relay"]["routes"]["gateway+west:chat@v2"]
        model = view["last_model"]
        assert model == {"run": run, "role": "worker", "at": json.loads(before.splitlines()[0])["at"],
                         "operation": "model", "login": "key", "swap": "swapped", "outcome": "forwarded",
                         "status": 401, "answered": 401, "reason": None}
        assert view["last_request"]["operation"] == "models_list" and view["last_request"]["status"] == 200
        assert view["counts"] == {"upstream_2xx": 1, "upstream_non_2xx": 1, "refused": 0, "unknown": 0}
        text = project.aew("status").stdout
        assert "gateway+west:chat@v2: 2 recorded" in text
        assert f"Last recognized model request: upstream HTTP 401, key login, swap swapped, {model['at']}" in text
        assert "Last provider request (models_list): upstream HTTP 200" in text
        assert not any(secret in text + json.dumps(view) for secret in
                       (key, token, "private-query-marker", "synthetic-provider-body-marker"))
        assert journal.read_bytes() == before

        assert request(service, method="POST", path="/v1/responses",
                       headers={"Authorization": f"Bearer {relay.sentinel()}"}) == 401
        refused = project.ok("status", "--json")["relay"]["routes"]["gateway+west:chat@v2"]
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
    assert f"A journal over {runlog.MAX_RECORD_BYTES // (1 << 20)} MiB is omitted in full." in text
    assert "Partial history" in text and "Last recognized model request: none recorded" in text


def test_an_unreadable_journal_does_not_prevent_project_status(project):
    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-1")
    (directory / runlog.RELAY_REQUESTS).mkdir(parents=True)
    report = project.ok("status", "--json")
    assert report["relay"] == {"partial": True, "routes": {}}
    assert report["revision"] == project.rev() and "work_graph" in report


def test_credentials_reports_a_confirmed_send_and_retains_provider_and_local_failures(project):
    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-1")
    directory.mkdir(parents=True)
    journal = directory / runlog.RELAY_REQUESTS
    key, unused = "synthetic-selected-secret", "synthetic-unused-secret"
    token, other = relay.sentinel(), relay.sentinel()
    source, other_source = "environment:EXAMPLE_KEY", "environment:SECOND_KEY"
    revision = project.rev()

    def offline(*args):
        raise OSError("synthetic-offline")

    with provider_endpoint() as (upstream, calls):
        service = relay.ProviderRelay(upstream, {token: key, other: unused}, route="openai", login="key",
                                      sources={token: source, other: other_source}, record=relay.RequestLog(journal))
        with closing(netns.RunNetwork(SimpleNamespace(network="proxy_only", net_dir=""), provider_relay=service,
                                      sentinels={"EXAMPLE_KEY": token, "SECOND_KEY": other},
                                      values={"EXAMPLE_KEY": key, "SECOND_KEY": unused})) as network:
            projected = {"ONE": key, "TWO": f"prefix-{key}"}
            network.record_credential_check(directory, projected, key, gate_matches=network.leaks(*projected.values()))
            evidence = project.ok("credentials", "--json")["credentials"][0]["last_launch"]
            assert (evidence["gate"], evidence["env_matches"], evidence["config_match"]) == ("failed", 2, True)
            environment = {"EXAMPLE_KEY": token, "SECOND_KEY": other}
            network.record_credential_check(directory, environment, "{}",
                                            gate_matches=network.leaks(*environment.values()))
            headers = {"Authorization": f"Bearer {token}"}
            assert request(service, method="POST", path="/v1/responses?private-query-marker", headers=headers) == 401
            with closing(relay.ProviderRelay(upstream, {token: key}, route="openai", login="key", connect=offline,
                                             sources={token: source}, record=relay.RequestLog(journal))) as failed:
                assert request(failed, method="POST", path="/v1/responses", headers=headers) == 502
            assert request(service, method="GET", path="/v1/models", headers=headers) == 200
        assert network.leaks(key, unused) == []
        assert calls == [("POST", "/v1/responses?private-query-marker", f"Bearer {key}"),
                         ("GET", "/v1/models", f"Bearer {key}")]
        address = f"{upstream.host}:{upstream.port}"

    records = [journal, directory / runlog.RELAY_CREDENTIAL_CHECK]
    before = [p.read_bytes() for p in records]
    report = project.ok("credentials", "--json")
    assert report["partial"] is False and report["runtime_process_env_count"] is None
    selected, second = report["credentials"]
    assert (selected["source"], second["source"], second["destinations"]) == (source, other_source, {})
    launch = selected["last_launch"]
    assert (launch["configured_destination"], launch["env_matches"], launch["config_match"], launch["gate"]) == (
        address, 0, False, "passed")
    dest = selected["destinations"][address]
    assert (dest["requests"], dest["confirmed_sends"], dest["unconfirmed_sends"], dest["plain_http_sends"],
            dest["verified_tls_sends"], dest["last_request"]["transport"]) == (3, 2, 0, 2, 0, "http")
    assert {(f["status"], f["reason"], f["answered"]) for f in selected["recent_failures"]} == {
        (401, None, 401), (None, "upstream_unreachable", 502)}
    text = project.aew("credentials").stdout
    assert all(label in text for label in ("environment export EXAMPLE_KEY", address, "upstream HTTP 401",
                                            "relay refusal upstream_unreachable (502)", "0 matching entries",
                                            "2 plain HTTP", "Runtime sandbox process-environment count: unmeasured"))
    assert all(private not in text + json.dumps(report) for private in
               (key, unused, token, other, "synthetic-provider-body-marker", "private-query-marker"))
    assert all(private.encode() not in b"".join(before) for private in (key, unused, token, other))
    assert [p.read_bytes() for p in records] == before and project.rev() == revision


def test_credentials_keeps_missing_legacy_provenance_and_transport_unknown(project):
    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-2")
    directory.mkdir(parents=True)
    (directory / runlog.RELAY_CREDENTIAL_CHECK).write_text("{")
    relay.RequestLog(directory / runlog.RELAY_REQUESTS)({
        "at": "2026-01-04T01:02:03Z", "route": "gateway+west", "destination": "service.example:443",
        "swap": "swapped", "login": "key", "outcome": "forwarded", "status": 401, "answered": 401})
    report = project.ok("credentials", "--json")
    [view] = report["credentials"]
    assert report["partial"] and view["source"] == "unknown" and view["last_launch"] is None
    dest = view["destinations"]["service.example:443"]
    assert (dest["last_request"]["transport"], dest["confirmed_sends"], dest["unconfirmed_sends"]) == ("unknown", 0, 1)
    assert "Partial history" in project.aew("credentials").stdout


def test_anonymous_provider_failure_stays_separate_from_a_working_export(project):
    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-1")
    directory.mkdir(parents=True)
    token, key = relay.sentinel(), "synthetic-working-secret"
    with provider_endpoint() as (upstream, calls), closing(relay.ProviderRelay(
            upstream, {token: key}, route="openai", login="key", sources={token: "environment:EXAMPLE_KEY"},
            record=relay.RequestLog(directory / runlog.RELAY_REQUESTS))) as service:
        assert request(service, method="POST", path="/v1/responses", headers={}) == 401
        assert request(service, method="GET", path="/v1/models", headers={"Authorization": f"Bearer {token}"}) == 200
        assert calls == [("POST", "/v1/responses", None), ("GET", "/v1/models", f"Bearer {key}")]
    report = project.ok("credentials", "--json")
    keyed, anonymous = report["credentials"]
    assert keyed["source"] == "environment:EXAMPLE_KEY" and keyed["recent_failures"] == []
    assert anonymous["source"] == "no_header_swap" and [f["status"] for f in anonymous["recent_failures"]] == [401]
    used, unsigned = [next(iter(view["destinations"].values())) for view in (keyed, anonymous)]
    assert (used["requests"], used["confirmed_sends"]) == (1, 1)
    assert (unsigned["requests"], unsigned["confirmed_sends"]) == (1, 0)
    text = project.aew("credentials").stdout
    keyed_text, anonymous_text = text.split("openai — no credential swapped into request headers")
    assert "environment export EXAMPLE_KEY" in keyed_text and "HTTP 401" not in keyed_text
    assert "upstream HTTP 401" in anonymous_text


def test_interrupted_outbound_header_write_has_unconfirmed_delivery(project):
    class Interrupted(socket.socket):
        def sendall(self, data):
            assert b"Authorization: Bearer synthetic-interrupted-secret" in data
            raise BrokenPipeError("synthetic interrupted header write")

    directory = runlog.run_dir(project.root / ".aew", "R-INV-0001-1")
    directory.mkdir(parents=True)
    token = relay.sentinel()
    journal = directory / runlog.RELAY_REQUESTS
    with closing(relay.ProviderRelay(
            relay.Upstream("http://provider.example/v1"), {token: "synthetic-interrupted-secret"}, route="openai",
            login="key", sources={token: "saved_key"}, record=relay.RequestLog(journal),
            connect=lambda *_: Interrupted())) as service:
        assert request(service, method="POST", path="/v1/responses",
                       headers={"Authorization": f"Bearer {token}"}) == 502
    [row] = [json.loads(line) for line in journal.read_bytes().splitlines()]
    assert row["upstream_headers_written"] is None and row["swapped_sources"] == ["saved_key"]
    [source] = project.ok("credentials", "--json")["credentials"]
    dest = source["destinations"]["provider.example:80"]
    assert dest["confirmed_sends"] == 0 and dest["unconfirmed_sends"] == 1 and dest["last_confirmed_send"] is None
