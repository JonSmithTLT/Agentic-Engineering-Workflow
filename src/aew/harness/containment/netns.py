"""A contained run's network (F28, network containment design v0.2; STG-05 CS-3b, the hand-off's outcome 1).

On Linux a contained run gets a network namespace of its own (``layout.Layout.network``), so the host's loopback ports
and abstract sockets are not in it. What it may reach instead runs outside the sandbox, in its supervisor, behind
socket files in the run's network directory (:func:`private_dir`), which the layout binds in:

* **the provider relay** (``relay.py``): the harness's provider ``baseURL`` is a loopback port inside, which the shim
  forwards here. It holds the provider's credential and connects to one fixed upstream, the execution policy's.
* **the egress proxy** (``egress.py``, CS-3a): a bounded ``host:port`` allowlist for anything else (OpenCode's model
  catalog, say), credentialless, under ruling R-6. Only when the allowlist names something.
* **the shim** (``shim.py``) runs inside, as the harness's parent: it forwards those two ports out, and the harness
  server's port in, for the supervisor.

The modes (F28 §3.1): ``proxy_only``, the workers' default on Linux (F28 decision 1): the relay and the allowlist are
the only routes out. ``isolated``: none (a check's default, F28 §3.8). ``shared``: the host's own network, an explicit
weaker choice in the execution policy (``containment.network.mode``), labelled as such. Windows has no network
containment (``not_provided``).

In a network of its own the sandbox never holds the provider's credential (F28 §3.6, row 6): each variable the policy's
``provider_env`` names is a sentinel inside (``relay.sentinel``), and only the relay knows what it stands for. The
operator's own proxy variables there are the relay's, for its upstream.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import socket
import sys
import tempfile
from collections.abc import Iterable, Mapping
from typing import Any

from aew.errors import AEWError, ContainmentUnavailable
from aew.harness import agentenv
from aew.harness.containment import egress, relay
from aew.harness.containment.layout import ISOLATED, NET_SHIM, NETWORK_MODES, PROXY_ONLY, SHARED, Layout

NOT_PROVIDED = "not_provided"  # AEW cannot characterize a run's network on this platform
# Loopback ports inside the sandbox. A fresh network namespace holds nothing else, so any port is free there; they are
# fixed so that the harness's configuration can name them before it starts.
SERVER_PORT, PROVIDER_PORT, EGRESS_PORT = 4100, 4101, 4102
# The socket files in the run's network directory: the shim binds the first (in its writable subdirectory), the
# supervisor the others.
SERVER, RELAY, EGRESS = f"{NET_SHIM}/server.sock", "relay.sock", "egress.sock"
SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim.py")
# Provider upstreams AEW knows, by OpenCode's provider id: where OpenCode 2.0.18 itself sends that provider's requests
# (measured on the Rocky VM, 2026-10-24: the free opencode/* models' catalog baseURL, and OpenAI's API). Any other
# provider, or another upstream (an AEW Provider Gateway, F18.8), is named in containment.network.upstreams.
UPSTREAMS = {"openai": "https://api.openai.com/v1", "opencode": "https://opencode.ai/inference/openai/v1"}
PROXY_NAMES = frozenset({*agentenv.PROXY_VARS, "NO_PROXY"})
# The designer's ruling on #246's P8, as the operator decided it (2026-10-24): the one-line form, for the label.
EGRESS_RESIDUAL = ("egress (R-6): a destination the host's own network configuration, root's, rewrites to this host "
                   "is not detected.")


def settings(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    """The execution policy's ``containment.network``."""
    found = (((policy or {}).get("containment") or {}).get("network")) or {}
    return found if isinstance(found, dict) else {}


def mode(policy: Mapping[str, Any] | None) -> str:
    """The network mode a contained run of this policy gets: the policy's, else ``proxy_only`` on Linux (F28
    decision 1). Windows: ``not_provided``. A run that is not contained shares the host's network: ``shared``."""
    if sys.platform == "win32":
        return NOT_PROVIDED
    return str(settings(policy).get("mode") or PROXY_ONLY)


def private_dir() -> str:
    """A fresh directory for a run's network sockets, under the host's ``/tmp`` whatever TMPDIR says (as the bridge's,
    ``bridge.private_address``: socket paths are short there, and each sandbox's ``/tmp`` is its own)."""
    tmp = "/tmp"  # noqa: S108
    directory = tempfile.mkdtemp(prefix="aew-net-", dir=tmp if os.path.isdir(tmp) else None)
    os.chmod(directory, 0o700)
    return directory


def egress_policy(policy: Mapping[str, Any] | None, extra: Iterable[str] = ()) -> egress.Allowlist | None:
    """The run's egress allowlist (F28 §3.4): the policy's ``egress_allow`` and what the harness itself needs
    (``extra``, its adapter's ``EGRESS``), or None when that is nothing, and the run has no egress proxy. Raises
    ``ValidationFailed`` on an entry that is not ``host:port``."""
    entries = list(dict.fromkeys(str(e) for e in [*(settings(policy).get("egress_allow") or []), *extra]))
    return egress.Allowlist(entries) if entries else None


def upstream(provider: str | None, policy: Mapping[str, Any] | None) -> relay.Upstream:
    """The provider relay's fixed upstream: the policy's ``upstreams.<provider>``, else :data:`UPSTREAMS`. Raises
    ``ContainmentUnavailable`` when there is none, saying what to set."""
    configured = settings(policy).get("upstreams") or {}
    url = configured.get(provider) if isinstance(configured, dict) else None
    url = url or UPSTREAMS.get(provider or "")
    if not url:
        raise ContainmentUnavailable(
            f"the run's provider {provider!r} has no known API address, so its relay has nowhere fixed to send its "
            f"requests (F28 §3.3). Name it in the execution policy as containment.network.upstreams.{provider}: "
            "https://... (the provider's API base URL, as its harness would use it), or set containment.network.mode: "
            "shared to give the run the host's network, labelled shared", provider=provider, reason="no_upstream")
    try:
        return relay.Upstream(str(url))
    except AEWError as exc:
        raise ContainmentUnavailable(f"containment.network.upstreams.{provider}: {exc.message}", provider=provider,
                                     reason="bad_upstream") from None


def shim_spec(directory: str, *, server: str | None = SERVER, relay_sock: str | None = None,
              egress_sock: str | None = None, server_port: int = SERVER_PORT) -> dict[str, Any]:
    """The shim's legs for a run whose network sockets are in ``directory``: the server in, and the relay and the
    egress proxy out where the run has them."""
    out = []
    if relay_sock:
        out.append({"port": PROVIDER_PORT, "unix": os.path.join(directory, relay_sock)})
    if egress_sock:
        out.append({"port": EGRESS_PORT, "unix": os.path.join(directory, egress_sock)})
    return {"in": [{"unix": os.path.join(directory, server), "port": server_port}] if server else [], "out": out}


def shim_argv(spec: Mapping[str, Any], argv: list[str]) -> list[str]:
    """``argv`` under the shim: its text run with ``-c``, isolated, by the interpreter AEW runs on (as the self-test's
    probe is; the shim's own docstring says why it is not an entry point)."""
    return [sys.executable, "-I", "-c", _shim_source(), json.dumps(spec, separators=(",", ":")), "--", *argv]


@functools.cache
def _shim_source() -> str:
    with open(SHIM, encoding="utf-8") as f:
        return f.read() + "\nsys.exit(main(sys.argv[1:]))\n"


def listen(path: str) -> socket.socket:
    """A listening socket file only the operator's account can open."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)  # pyright: ignore[reportAttributeAccessIssue]
    try:
        sock.bind(path)
        os.chmod(path, 0o600)
        sock.listen(64)
    except BaseException:
        sock.close()
        raise
    return sock


def operator_proxy(target: relay.Upstream, names: Iterable[str], env: Mapping[str, str]) -> relay.Proxy | None:
    """The operator's own proxy for the relay's upstream, from the proxy variables ``provider_env`` names: the one
    the scheme selects (``ALL_PROXY`` otherwise), unless ``NO_PROXY`` covers the upstream's host."""
    values = {n.upper(): agentenv.lookup(env, n) or "" for n in names if n.upper() in PROXY_NAMES}
    url = values.get("HTTPS_PROXY" if target.scheme == "https" else "HTTP_PROXY") or values.get("ALL_PROXY")
    if not url:
        return None
    for entry in (h.strip().lower().lstrip(".") for h in values.get("NO_PROXY", "").split(",")):
        if entry == "*" or (entry and (target.host == entry or target.host.endswith("." + entry))):
            return None
    return relay.Proxy(url)


class RunNetwork:
    """One contained run's network, outside its sandbox: its directory, its relay and egress proxy, and the sentinels
    its harness gets for the provider's variables. The run's process tree owns it: killing the tree closes it."""

    def __init__(self, layout: Layout, *, provider_relay: relay.ProviderRelay | None = None,
                 egress_proxy: egress.EgressProxy | None = None, sentinels: Mapping[str, str] | None = None,
                 values: Mapping[str, str] | None = None) -> None:
        self.mode = layout.network
        self.dir = layout.net_dir
        self.relay = provider_relay
        self.egress = egress_proxy
        self.sentinels = dict(sentinels or {})  # provider variable -> its sentinel inside
        self._values = dict(values or {})       # provider variable -> its value, for the leak check only
        self._closed = False

    @classmethod
    def start(cls, layout: Layout, *, provider: str | None, provider_env: Iterable[str],
              policy: Mapping[str, Any] | None, env: Mapping[str, str], relay_needed: bool,
              egress_extra: Iterable[str] = ()) -> RunNetwork:
        """Start what ``layout``'s network needs: under ``proxy_only``, the relay (when the harness calls a provider,
        ``relay_needed``) and the egress proxy (when the allowlist names something). Raises
        ``ContainmentUnavailable`` when the relay has no upstream, or a socket cannot be made."""
        names = [str(n) for n in provider_env]
        secret = [n for n in names if n.upper() not in PROXY_NAMES]
        values = {n: agentenv.lookup(env, n) or "" for n in secret}
        sentinels = {n: relay.sentinel() for n in secret}
        net = cls(layout, sentinels=sentinels, values=values)
        if layout.network != PROXY_ONLY or not layout.net_dir:
            return net
        try:
            if relay_needed:
                target = upstream(provider, policy)
                try:
                    proxy = operator_proxy(target, names, env)
                except AEWError as exc:
                    raise ContainmentUnavailable(exc.message, reason="bad_proxy") from None
                net.relay = relay.ProviderRelay(
                    target, {sentinels[n]: v for n, v in values.items() if v}, proxy=proxy,
                    listener=listen(os.path.join(layout.net_dir, RELAY))).start()
            try:
                allow = egress_policy(policy, egress_extra)
            except AEWError as exc:
                raise ContainmentUnavailable(f"containment.network.egress_allow: {exc.message}",
                                             reason="bad_egress_allow") from None
            if allow is not None:
                net.egress = egress.EgressProxy(allow, listener=listen(os.path.join(layout.net_dir, EGRESS))).start()
        except OSError as exc:
            net.close()
            raise ContainmentUnavailable(f"the run's network could not be set up: {exc}", reason="network") from None
        except BaseException:
            net.close()
            raise
        return net

    @property
    def server_socket(self) -> str | None:
        """Where the supervisor reaches the harness server (through the shim), or None without a network of its own."""
        return os.path.join(self.dir, SERVER) if self.dir else None

    def spec(self) -> dict[str, Any]:
        assert self.dir is not None
        return shim_spec(self.dir, relay_sock=RELAY if self.relay else None,
                         egress_sock=EGRESS if self.egress else None)

    def shim_argv(self, argv: list[str]) -> list[str]:
        if not self.dir:
            return argv
        return shim_argv(self.spec(), argv)

    def harness_env(self, env: dict[str, str]) -> dict[str, str]:
        """The harness's environment with each provider variable's value replaced by its sentinel, the operator's
        proxy variables (the relay's) removed, and, with an egress proxy, ``HTTPS_PROXY`` set to the shim's egress
        port, loopback excepted. Only the HTTPS one: the egress proxy serves CONNECT only (CS-3a), and the provider's
        ``baseURL`` is plain HTTP to loopback, which must never be sent to it. The values are never in what is
        returned."""
        out = {k: v for k, v in env.items() if k.upper() not in PROXY_NAMES}
        for name, value in self.sentinels.items():
            for key in [k for k in out if k == name or (sys.platform == "win32" and k.upper() == name.upper())]:
                del out[key]
            out[name] = value
        if self.egress is not None:
            url = f"http://127.0.0.1:{EGRESS_PORT}"
            out.update({"HTTPS_PROXY": url, "https_proxy": url})
            agentenv.bypass_proxy_for_loopback(out)
        return out

    def leaks(self, *texts: str) -> list[str]:
        """The provider variables whose value appears in any of ``texts`` (the harness's environment and configuration,
        say): F28 §3.6, row 6. Names only."""
        return sorted(n for n, v in self._values.items() if v and any(v in t for t in texts))

    def provider_base(self, upstream_path: str | None = None) -> str | None:
        """The harness's provider ``baseURL``: the relay's loopback port inside, with the upstream's path."""
        if self.relay is None:
            return None
        path = self.relay.upstream.path if upstream_path is None else upstream_path
        return f"http://127.0.0.1:{PROVIDER_PORT}{path}"

    def describe(self) -> dict[str, Any]:
        """The label's ``network`` (F28 §3.1): the mode, the relay, the egress allowlist, and the stated limit."""
        out: dict[str, Any] = {"mode": self.mode, **relay.describe(self.relay)}
        if self.egress is not None:
            out["egress_allow"] = self.egress.policy.describe().get("allow", [])
            out["limits"] = [EGRESS_RESIDUAL]
        return out

    def decisions(self) -> dict[str, dict[str, int]]:
        """What the relay and the egress proxy decided, counted by outcome, for the run's record at its end."""
        return {name: service.counts() for name, service in (("relay", self.relay), ("egress", self.egress))
                if service is not None}

    def close(self) -> None:
        """Stop the relay and the egress proxy and remove the run's network directory. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            for service in (self.relay, self.egress):
                if service is not None:
                    service.close()
        finally:
            self._values.clear()
            if self.dir:
                shutil.rmtree(self.dir, ignore_errors=True)


__all__ = ["EGRESS_PORT", "ISOLATED", "NETWORK_MODES", "NOT_PROVIDED", "PROVIDER_PORT", "PROXY_ONLY", "RunNetwork",
           "SERVER_PORT", "SHARED", "mode", "private_dir", "settings", "shim_spec", "upstream"]
