"""Uncached, no-cost provider models requests made through the launcher's credentialing relay."""

from __future__ import annotations

import http.client
import os
import sqlite3
import tempfile
import time
from contextlib import ExitStack, closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.errors import AEWError
from aew.harness import containment, runlog
from aew.harness.containment import netns, relay
from aew.harness.opencode import capabilities, lead, login
from aew.harness.opencode.client import UnixConnection


def result(route: str, status: str, detail: str) -> dict[str, str]:
    return {"check": "provider-relay", "status": status, "detail": f"{route}: {detail}"}


def request(network: netns.RunNetwork, provider: str, *, route: str, source: str,
            until: float) -> dict[str, str]:
    """Use the socket the run's shim forwards to, with the same sentinel its SDK sends. Inspect only the HTTP
    status. No redirects, raw response, credentials or arbitrary upstream header values enter a doctor row."""
    service = network.relays[provider][1] if network.lead else network.relay
    if service is None or service.listener is None:
        return result(route, "WARN", "no provider relay available for the models request")
    token = network.login_sentinels.get(provider) or network.sentinels.get(netns.PROVIDER_KEY_ENV.get(provider, ""))
    if not token and service.login != "none":
        return result(route, "WARN", "the credential header for this provider's models request is unknown")
    headers = {"Accept": "application/json"}
    if token:
        if provider == "anthropic":
            headers.update({"x-api-key": token, "anthropic-version": "2023-06-01"})
        elif provider == "google":
            headers["x-goog-api-key"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"
    path = service.upstream.path + "/models"
    # The ChatGPT backend requires a client_version on its models listing.
    if provider in network.login_sentinels and provider == "openai":
        path += f"?client_version={capabilities.TESTED_VERSIONS[0]}"
    label = f"{source}, GET models through the relay"
    timeout = min(relay.HEAD_TIMEOUT, until - time.monotonic())
    if timeout <= 0:
        return result(route, "WARN", f"{label}: unavailable (deadline expired)")
    before = service.counts()
    try:
        with closing(UnixConnection(service.listener.getsockname(), timeout)) as conn:
            conn.request("GET", path, headers=headers)
            with conn.getresponse() as response:
                code = response.status
                refused = response.getheader("X-AEW-Refusal")
    except (OSError, http.client.HTTPException):
        return result(route, "WARN", f"{label}: unavailable (no response)")
    if refused and service.counts().get(refused, 0) > before.get(refused, 0):
        return result(route, "FAIL" if code in (401, 403) else "WARN",
                      f"{label}: relay answered HTTP {code}; no provider response verified")
    if 200 <= code < 300:
        return result(route, "PASS", f"{label}: provider answered HTTP {code}")
    status = "FAIL" if code in (401, 403) else "WARN"
    return result(route, status, f"{label}: provider answered HTTP {code}")


@dataclass
class WorkerProbe:
    """One provider/credential route in this doctor invocation, including a catalog served from disk."""

    provider: str
    route: str
    row: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.row = result(self.route, "WARN", "no provider relay available for a live models request")

    def check(self, network: netns.RunNetwork | None, until: float) -> None:
        if network is not None and network.relay is not None:
            self.row = request(network, self.provider, route=self.route,
                               source=network.key_source or ("client certificate" if network.relay.client
                                                             else "no known provider key"), until=until)


def lead_rows(engine: Any) -> list[dict[str, str]]:
    """Check the routes a default contained Lead would open, independently of worker profiles."""
    policy, _ = engine.execution_policy()
    if not lead.contained_here() or netns.mode(policy) != netns.PROXY_ONLY:
        return []
    chosen = lead.LeadProviders(policy, [], os.environ)
    routes = sorted({*chosen.keys, *chosen.refreshing, *chosen.certified})
    if not routes:
        return [result("default Lead", "WARN", "no login or client certificate selected for a provider relay")]
    state = engine.aew_root / lead.LEAD_DIR
    try:
        surviving = login.surviving_login_providers(state / login.STORE_REL, state)
    except (AEWError, OSError, sqlite3.Error, ValueError):
        return [result(f"default Lead {p}", "WARN", "could not verify logins in the project's OpenCode store")
                for p in routes]
    # An OAuth route seeds its own active row. On the other routes a surviving project login may override the key.
    conflicts = surviving.difference(chosen.refreshing).intersection(routes)
    rows = [result(f"default Lead {p}", "WARN", "the project's OpenCode store has its own login; "
                   "the credential a launch would send could not be verified") for p in sorted(conflicts)]
    routes = [p for p in routes if p not in conflicts]
    if not routes:
        return rows
    keys = {p: chosen.keys[p] for p in routes if p in chosen.keys}
    refreshing = {p: login.StoredLogin(p, os.environ) for p in routes if p in chosen.refreshing}
    keyless = [p for p in routes if p in chosen.certified]
    sources = {**dict.fromkeys(keys, "saved OpenCode API key"), **dict.fromkeys(refreshing, "saved plan login"),
               **dict.fromkeys(keyless, "client certificate")}
    try:
        parent = engine.aew_root / runlog.RUNS_REL
        parent.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            run_dir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="doctor-lead-", dir=parent)))
            stack.callback(containment.retire_private_git, run_dir)
            layout, _ = lead.establish_layout(engine, policy, run_dir,
                                              terminal=lead._launching_terminal() if os.isatty(0) else None)
            if layout is None or not layout.private_network:
                return rows + [result(f"default Lead {p}", "WARN", "no provider relay on the Lead's launch route")
                               for p in routes]
            network = netns.RunNetwork.start_lead(layout, keys=keys, provider_env=[], policy=policy,
                                                  env=os.environ, refreshing=refreshing, keyless=keyless)
            stack.callback(network.close)
            rows.extend(request(network, p, route=f"default Lead {p}", source=sources[p],
                                until=time.monotonic() + relay.HEAD_TIMEOUT) for p in routes)
    except (AEWError, OSError, ValueError):
        rows.extend(result(f"default Lead {p}", "WARN", "the Lead's provider relay could not be established")
                    for p in routes)
    return rows
