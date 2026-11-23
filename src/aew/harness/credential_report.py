"""Operator evidence of provider credential use, grouped by provider and logical source. No live credential lookups."""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
from pathlib import Path
from typing import Any, TypeGuard

from aew.engine.configuration import model_id_problem
from aew.errors import AEWError
from aew.harness import defects, relay_status, runlog
from aew.harness.containment import client_cert, netns, relay
from aew.policy import execution

_RECENT_FAILURES = 5
_SOURCE_NAMES = {"saved_key": "OpenCode saved API key", "saved_oauth": "OpenCode saved OAuth login",
                 "client_certificate": "client certificate", "unknown": "source unrecorded",
                 "no_header_swap": "no credential swapped into request headers"}
_TRANSPORT = ("http", "tls_verified", "tls_unverified", "not_established")


def _source(value: Any) -> str:
    if isinstance(value, str):
        if value in _SOURCE_NAMES:
            return value
        prefix, _, name = value.partition(":")
        if prefix == "environment" and netns.export_source(name) == value:
            return value
    return "unknown"


def _safe(text: Any) -> TypeGuard[str]:
    return isinstance(text, str) and 0 < len(text) <= 4096 and text.isprintable() and (
        relay.SENTINEL_PREFIX not in text and defects.redact_text(text) == text)


def _destination(raw: Any) -> str:
    if not _safe(raw):
        return "unknown"
    host, _, port = raw.rpartition(":")
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 0 < int(port) <= 65535:
        return "unknown"
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return f"[{ip}]:{port}" if ip.version == 6 else f"{ip}:{port}"
    except ValueError:
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", host):
            return f"{host}:{port}"
    return "unknown"


def _certificate(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    fingerprint, expires = raw.get("sha256"), raw.get("expires")
    valid_hash = isinstance(fingerprint, str) and re.fullmatch("[0-9a-f]{64}", fingerprint)
    return {"file": raw["file"] if _safe(raw.get("file")) else None,
            "sha256": fingerprint if valid_hash else None,
            "expires": expires if relay_status.valid_stamp(expires) else None}


def configured(policy: dict[str, Any] | None) -> dict[str, Any]:
    """What the policy selects. Presence in the environment or credential stores is deliberately unobserved."""
    policy = policy or {}
    profiles = []
    for name, profile in sorted(policy.get("profiles", {}).items()):
        try:
            provider = execution.model_pair(policy, name).provider
        except AEWError:
            continue
        if _safe(provider) and not model_id_problem(provider) and _safe(name):
            credential = execution.profile_credential(policy, profile, provider)
            try:
                target = (relay.Upstream(netns.REFRESHING_UPSTREAMS[provider]) if credential == execution.PLAN_LOGIN
                          else netns.upstream(provider, policy))
                address = _destination(f"{target.host}:{target.port}")
            except (AEWError, KeyError, ValueError):
                address = "unknown"
            profiles.append({"profile": name, "provider": provider, "credential": credential,
                             "configured_destination": address})
    certificates = [{"provider": provider, "file": cert.cert if _safe(cert.cert) and cert.cert != cert.key else None}
                    for provider, cert in sorted(client_cert.configured(policy).items())
                    if _safe(provider) and not model_id_problem(provider)]
    return {"profiles": profiles, "export_names": [name for name in policy.get("provider_env", []) if
            netns.export_source(name) != "unknown" and name.upper() not in netns.PROXY_NAMES],
            "client_certificates": certificates}


def summary(aew_root: Path, policy: dict[str, Any] | None, *, policy_problem: str | None = None) -> dict[str, Any]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    certified: set[tuple[str, str]] = set()

    def group(provider: str, source: str) -> dict[str, Any]:
        key = (provider, source)
        if key not in groups:
            groups[key] = {"provider": provider, "source": source, "last_launch": None, "destinations": {},
                           "recent_failures": []}
        return groups[key]

    def launch(directory: Path) -> bool:
        try:
            record = json.loads(runlog.read_regular(directory / runlog.RELAY_CREDENTIAL_CHECK))
        except FileNotFoundError:
            return True  # pre-report run, no relay, or no recorded check
        except (OSError, ValueError, RecursionError):
            return False
        if not isinstance(record, dict) or not relay_status.valid_stamp(record.get("at")):
            return False
        at, gate, routes = record["at"], record.get("launch_check"), record.get("providers")
        if gate not in ("passed", "failed") or not isinstance(routes, list):
            return False
        complete = True
        for route in routes:
            provider = route.get("provider") if isinstance(route, dict) else None
            if not _safe(provider) or model_id_problem(provider):
                complete = False
                continue
            sources = route.get("sources")
            if not isinstance(sources, list):
                complete = False
                continue
            if isinstance(route.get("certificate"), dict):
                sources = [*sources, {"source": "client_certificate", "certificate": route["certificate"]}]
                certified.add((directory.name, provider))
            for entry in sources:
                if not isinstance(entry, dict):
                    complete = False
                    continue
                view = group(provider, _source(entry.get("source")))
                last = view["last_launch"]
                if last is not None and (at, directory.name) < (last["at"], last["run"]):
                    continue
                matches, config = entry.get("env_matches"), entry.get("config_match")
                view["last_launch"] = {"at": at, "run": directory.name, "gate": gate,
                                       "configured_destination": _destination(route.get("destination")),
                                       "env_matches": matches if type(matches) is int and matches >= 0 else None,
                                       "config_match": config if type(config) is bool else None}
                if view["source"] == "client_certificate":
                    view["last_launch"]["certificate"] = _certificate(entry.get("certificate"))
        return complete

    def observe(provider: str, row: dict[str, Any], raw: dict[str, Any]) -> None:
        def sources(field: str) -> set[str]:
            values = raw.get(field)
            return {_source(v) for v in values} if isinstance(values, list) else set()

        swapped = sources("swapped_sources")
        offered = sources("configured_sources")
        certificate = raw.get("client_certificate_configured") is True or (row["run"], provider) in certified
        chosen = set(swapped)
        if not chosen:
            if len(offered) == 1 and row["reason"] in ("credential_unavailable", "credential_unreadable"):
                chosen.update(offered)  # the configured grant failed before the relay could swap its credential
            elif raw.get("swapped_sources") == [] and row["swap"] == "none" and row["outcome"] == "forwarded":
                if not certificate:
                    chosen.add("no_header_swap")
            elif not certificate or offered or row["login"] != "none":
                chosen.add("unknown")
        if certificate:
            chosen.add("client_certificate")
        transport = raw.get("transport")
        transport = transport if transport in _TRANSPORT else "unknown"
        address = _destination(raw.get("destination"))
        for source in chosen:
            view = group(provider, source)
            by_address = view["destinations"]
            if address not in by_address:
                by_address[address] = {"requests": 0, "confirmed_sends": 0, "unconfirmed_sends": 0,
                                       "verified_tls_sends": 0, "plain_http_sends": 0, "verified_handshakes": 0,
                                       "last_request": None, "last_confirmed_send": None}
            dest = by_address[address]
            dest["requests"] += 1
            dest["verified_handshakes"] += int(transport == "tls_verified")
            latest = dest["last_request"]
            if latest is None or (row["at"], row["run"]) >= (latest["at"], latest["run"]):
                dest["last_request"] = {"at": row["at"], "run": row["run"], "transport": transport}
            written = raw.get("upstream_headers_written")
            if source in swapped and written is True:
                dest["confirmed_sends"] += 1
                dest["verified_tls_sends"] += int(transport == "tls_verified")
                dest["plain_http_sends"] += int(transport == "http")
                dest["last_confirmed_send"] = max(dest["last_confirmed_send"] or "", row["at"])
            elif source != "client_certificate" and row["swap"] == "swapped" and written is None:
                dest["unconfirmed_sends"] += 1
            code = row["status"]
            if row["outcome"] == "refused" or (code is not None and not 200 <= code < 300):
                failure = {k: row[k] for k in ("at", "run", "outcome", "reason", "status", "answered")}
                failure["destination"] = address
                recent = view["recent_failures"]
                recent.insert(0, failure)
                recent.sort(key=lambda f: (f["at"], f["run"]), reverse=True)
                del recent[_RECENT_FAILURES:]

    partial = relay_status.visit(aew_root, observe, on_run=launch)
    return {"configured": configured(policy), "policy_problem": policy_problem,
            "credentials": [groups[k] for k in sorted(groups)], "partial": partial,
            "runtime_process_env_count": None}


def render(report: dict[str, Any]) -> str:
    policy = report["configured"]
    lines = ["Current execution policy"]
    if report["policy_problem"]:
        lines.append(f"  Configuration unavailable ({report['policy_problem']}).")
    for profile in policy["profiles"]:
        lines.append(f"  {profile['profile']}: {profile['provider']} ({profile['credential']}), "
                     f"relay destination {profile['configured_destination']}")
    if not report["policy_problem"]:
        lines.append(f"  Provider environment names: {', '.join(policy['export_names']) or 'none configured'}")
    for cert in policy["client_certificates"]:
        lines.append(f"  {cert['provider']} client certificate: {cert['file'] or 'file not shown'}")
    lines += ["", "Recorded credential use by provider and logical source (retained Lead and worker runs)"]
    if report["partial"]:
        lines.append(f"  Partial history. Unreadable records and journals over {runlog.MAX_RECORD_BYTES >> 20} MiB "
                     "are omitted.")
    if not report["credentials"]:
        lines.append("  No recorded credential evidence found.")
    for view in report["credentials"]:
        source = view["source"]
        name = _SOURCE_NAMES.get(source) or f"environment export {source.removeprefix('environment:')}"
        lines.append(f"  {view['provider']} — {name}")
        if last := view["last_launch"]:
            lines.append(f"    Last launch at {last['at']} ({last['run']}): configured destination "
                         f"{last['configured_destination']}. Launch credential check {last['gate']}.")
            if source == "client_certificate":
                cert = last["certificate"]
                lines.append(f"    Public certificate file at launch: {cert['file'] or 'unknown'}, "
                             f"SHA-256 {cert['sha256'] or 'unknown'}, expires {cert['expires'] or 'unknown'}.")
            else:
                matches = last["env_matches"]
                config = {True: "matched", False: "no match", None: "unmeasured"}[last["config_match"]]
                lines.append(f"    Projected process environment: {matches if matches is not None else 'unmeasured'} "
                             f"matching entries. Generated configuration: {config}.")
        else:
            lines.append("    Launch credential check and environment matches: unrecorded.")
        if not view["destinations"]:
            lines.append("    No recorded requests.")
        for address, dest in sorted(view["destinations"].items()):
            last = dest["last_request"]
            lines.append(f"    {address}: {dest['requests']} recorded request(s), latest {last['at']} "
                         f"({last['transport']}).")
            if source == "client_certificate":
                lines.append(f"      {dest['verified_handshakes']} verified TLS handshake(s). "
                             "The relay does not record whether the peer requested the client certificate.")
            else:
                lines.append(f"      Swapped into completed outbound header writes: {dest['confirmed_sends']} "
                             f"({dest['verified_tls_sends']} verified TLS, {dest['plain_http_sends']} plain HTTP). "
                             f"Last confirmed: {dest['last_confirmed_send'] or 'none recorded'}. "
                             f"Delivery unconfirmed: {dest['unconfirmed_sends']}.")
        for failure in view["recent_failures"]:
            cause = (f"relay refusal {failure['reason'] or 'unknown'} ({failure['answered'] or 'no HTTP status'})"
                     if failure["outcome"] == "refused" else
                     f"upstream HTTP {failure['status']} {http.client.responses.get(failure['status'], '')}".rstrip())
            lines.append(f"    {failure['at']} ({failure['run']}) {failure['destination']}: {cause}")
    lines.append("Runtime sandbox process-environment count: unmeasured. Launch checks cover only the supplied "
                 "environment and generated configuration at launch.")
    return "\n".join(lines)
