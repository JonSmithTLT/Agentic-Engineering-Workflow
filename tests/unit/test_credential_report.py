"""The operator's report across retained worker and Lead records."""

from __future__ import annotations

import json

from aew.harness import credential_report, runlog
from aew.harness.containment import relay


def test_report_keeps_latest_five_failures_across_runs_and_destinations(tmp_path):
    address = "api.example:443"
    source = "environment:EXAMPLE_KEY"
    worker = "R-INV-0001-1"
    lead = "lead-20260101T000000Z-abcdef"
    # The newer run is written first. Each start contributed its own environment check.
    for run, day, destination in [(lead, "02", address), (worker, "01", "127.0.0.1:8080")]:
        directory = runlog.run_dir(tmp_path, run)
        directory.mkdir(parents=True)
        stamp = f"2026-01-{day}T00:00:00Z"
        launch = {"at": stamp, "launch_check": "passed", "providers": [{
            "provider": "example", "destination": destination,
            "sources": [{"source": source, "env_matches": 0, "config_match": False}]}]}
        (directory / runlog.RELAY_CREDENTIAL_CHECK).write_text(json.dumps(launch))
        journal = relay.RequestLog(directory / runlog.RELAY_REQUESTS)
        for status in (401, 429, 503, 200):
            journal({"at": stamp, "route": "example", "destination": destination, "login": "key",
                     "swap": "swapped", "swapped_sources": [source], "upstream_headers_written": True,
                     "outcome": "forwarded", "status": status, "transport": "tls_verified" if run == lead else "http"})

    report = credential_report.summary(tmp_path, None)
    [view] = report["credentials"]
    assert not report["partial"] and view["source"] == source
    assert view["last_launch"] == {
        "at": "2026-01-02T00:00:00Z", "run": lead, "gate": "passed", "configured_destination": address,
        "env_matches": 0, "config_match": False}
    assert [(failure["run"], failure["status"]) for failure in view["recent_failures"]] == [
        (lead, 503), (lead, 429), (lead, 401), (worker, 503), (worker, 429)]
    https, http = view["destinations"][address], view["destinations"]["127.0.0.1:8080"]
    assert (https["requests"], https["confirmed_sends"], https["verified_tls_sends"], https["plain_http_sends"]) == (
        4, 4, 4, 0)
    assert (http["requests"], http["confirmed_sends"], http["verified_tls_sends"], http["plain_http_sends"]) == (
        4, 4, 0, 4)
    assert https["last_confirmed_send"] == "2026-01-02T00:00:00Z"
    assert http["last_confirmed_send"] == "2026-01-01T00:00:00Z"
    text = credential_report.render(report)
    assert "environment export EXAMPLE_KEY" in text and "4 verified TLS, 0 plain HTTP" in text
    assert text.count("upstream HTTP") == 5


def test_certificate_report_distinguishes_current_policy_from_retained_launch(tmp_path):
    directory = runlog.run_dir(tmp_path, "R-INV-0001-1")
    directory.mkdir(parents=True)
    at, expires = "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
    public = {"file": "previous.pem", "sha256": "ab" * 32, "expires": expires}
    launch = {"at": at, "launch_check": "passed", "providers": [{
        "provider": "example", "destination": "::1:8443", "sources": [], "certificate": public}]}
    (directory / runlog.RELAY_CREDENTIAL_CHECK).write_text(json.dumps(launch))
    relay.RequestLog(directory / runlog.RELAY_REQUESTS)({
        "at": at, "route": "example", "destination": "::1:8443", "login": "none", "swap": "none",
        "swapped_sources": [], "outcome": "forwarded", "transport": "tls_verified", "status": 200})
    files = {"cert": "replacement.pem", "key": "private-key.pem", "ca": "trust.pem"}
    policy = {"profiles": {"worker": {"model": "example/model"}}, "provider_env": ["EXAMPLE_KEY", "HTTPS_PROXY"],
              "containment": {"network": {"upstreams": {"example": "https://replacement.example/v1"},
                                          "client_certs": {"example": files}}}}
    report = credential_report.summary(tmp_path, policy)
    assert report["configured"] == {
        "profiles": [{"profile": "worker", "provider": "example", "credential": "api_key",
                      "configured_destination": "replacement.example:443"}],
        "export_names": ["EXAMPLE_KEY"], "client_certificates": [{"provider": "example", "file": "replacement.pem"}]}
    [view] = report["credentials"]
    assert view["source"] == "client_certificate" and view["last_launch"]["certificate"] == public
    assert view["last_launch"]["env_matches"] is None
    dest = view["destinations"]["[::1]:8443"]
    assert (dest["verified_handshakes"], dest["confirmed_sends"]) == (1, 0)
    text = credential_report.render(report)
    assert "example client certificate: replacement.pem" in text
    assert "Public certificate file at launch: previous.pem" in text
    assert "1 verified TLS handshake(s)" in text and public["sha256"] in text and expires in text
    assert files["key"] not in text + json.dumps(report)


def test_partial_launch_preserves_older_request_and_scopes_a_refused_grant(tmp_path):
    directory = runlog.run_dir(tmp_path, "R-INV-0001-1")
    directory.mkdir(parents=True)
    (directory / runlog.RELAY_CREDENTIAL_CHECK).write_text("{")
    journal = relay.RequestLog(directory / runlog.RELAY_REQUESTS)
    row = {"at": "2026-01-01T00:00:00Z", "route": "openai", "destination": "api.example:443", "login": "oauth"}
    # The old row records a swap but has neither a source nor a completed-write observation.
    journal(dict(row, swap="swapped", outcome="forwarded", status=401, answered=401))
    journal(dict(row, at="2026-01-02T00:00:00Z", swap="none", configured_sources=["saved_oauth"],
                 swapped_sources=[], outcome="refused", reason="credential_unavailable", answered=401,
                 upstream_headers_written=False, transport="not_established"))
    report = credential_report.summary(tmp_path, None, policy_problem="VALIDATION_FAILED")
    oauth, legacy = report["credentials"]
    assert report["partial"] and oauth["source"] == "saved_oauth" and legacy["source"] == "unknown"
    legacy_dest = legacy["destinations"]["api.example:443"]
    assert legacy_dest["confirmed_sends"] == 0 and legacy_dest["unconfirmed_sends"] == 1
    assert legacy_dest["last_request"]["transport"] == "unknown" and legacy["last_launch"] is None
    assert [failure["status"] for failure in legacy["recent_failures"]] == [401]
    [refused] = oauth["recent_failures"]
    assert (refused["status"], refused["answered"], refused["reason"]) == (None, 401, "credential_unavailable")
    assert oauth["destinations"]["api.example:443"]["unconfirmed_sends"] == 0
    text = credential_report.render(report)
    assert "Partial history" in text and "Configuration unavailable (VALIDATION_FAILED)" in text
    assert "relay refusal credential_unavailable (401)" in text and "upstream HTTP 401" in text


def test_a_request_sent_with_no_header_swap_whose_outcome_is_unknown_is_still_named_no_header_swap(tmp_path):
    """Review of #542, m4: an unknown outcome went upstream as a forwarded one did, so its source is the same."""
    directory = runlog.run_dir(tmp_path, "R-INV-0001-1")
    directory.mkdir(parents=True)
    relay.RequestLog(directory / runlog.RELAY_REQUESTS)({
        "at": "2026-01-01T00:00:00Z", "route": "example", "destination": "api.example:443", "login": "none",
        "swap": "none", "swapped_sources": [], "configured_sources": [], "upstream_headers_written": True,
        "outcome": "unknown", "reason": relay.UPSTREAM_OUTCOME_UNKNOWN, "status": None, "transport": "tls_verified"})
    [view] = credential_report.summary(tmp_path, None)["credentials"]
    assert view["source"] == "no_header_swap"
    [failure] = view["recent_failures"]
    assert failure["outcome"] == "unknown"
