"""Uncached, no-cost provider models requests made through the launcher's credentialing relay."""

from __future__ import annotations

import http.client
import os
import time
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any

from aew.errors import AEWError
from aew.harness.containment import client_cert, netns, relay
from aew.harness.containment.layout import Layout
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


def lead_rows(policy: dict[str, Any], providers: set[str]) -> list[dict[str, str]]:
    """Check the default contained Lead's login for the project's providers, independently of worker login policy."""
    if not providers or not lead.contained_here() or netns.mode(policy) != netns.PROXY_ONLY:
        return []
    eligible = providers.intersection(netns.PROVIDER_KEY_ENV.keys() | client_cert.configured(policy).keys())
    eligible.difference_update(netns.CATALOG_ADDRESSED)
    if not eligible:
        return []
    chosen = lead.LeadProviders(policy, [], os.environ)
    keys = {p: chosen.keys[p] for p in providers & chosen.keys.keys()}
    refreshing = {p: login.StoredLogin(p, os.environ) for p in providers & chosen.refreshing.keys()}
    keyless = providers & chosen.certified.keys()
    routes = sorted({*keys, *refreshing, *keyless})
    absent = [result(f"default Lead {p}", "WARN", "no login or client certificate selected for this relay")
              for p in sorted(eligible.difference(routes))]
    if not routes:
        return absent
    # Only the relay runs. No Lead seat, terminal, session, or sandbox process is needed for this request.
    try:
        layout = Layout(role="lead", access="read", bwrap="", writable=(), readonly=(),
                        network=netns.PROXY_ONLY, net_dir=netns.private_dir())
        network = netns.RunNetwork.start_lead(layout, keys=keys, provider_env=[], policy=policy, env=os.environ,
                                              refreshing=refreshing, keyless=keyless)
    except (AEWError, OSError, ValueError):
        return [*absent, *(result(f"default Lead {p}", "WARN", "provider relay unavailable") for p in routes)]
    sources = {**dict.fromkeys(keys, "saved OpenCode API key"), **dict.fromkeys(refreshing, "saved plan login"),
               **dict.fromkeys(keyless, "client certificate")}
    with closing(network):
        return absent + [request(network, p, route=f"default Lead {p}", source=sources[p],
                                 until=time.monotonic() + relay.HEAD_TIMEOUT) for p in routes]
