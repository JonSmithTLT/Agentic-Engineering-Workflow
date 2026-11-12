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
import ssl
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from aew.errors import AEWError, ContainmentUnavailable, HarnessIncompatible
from aew.harness import agentenv
from aew.harness.containment import client_cert, egress, relay
from aew.harness.containment.layout import ISOLATED, NET_SHIM, NETWORK_MODES, PROXY_ONLY, SHARED, Layout
from aew.harness.opencode import login

NOT_PROVIDED = "not_provided"  # AEW cannot characterize a run's network on this platform
# Loopback ports inside the sandbox. A fresh network namespace holds nothing else, so any port is free there; they are
# fixed so that the harness's configuration can name them before it starts.
SERVER_PORT, PROVIDER_PORT, EGRESS_PORT = 4100, 4101, 4102
# The socket files in the run's network directory: the shim binds the first (in its writable subdirectory), the
# supervisor the others.
SERVER, RELAY, EGRESS = f"{NET_SHIM}/server.sock", "relay.sock", "egress.sock"
SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim.py")
# Provider upstreams AEW knows, by OpenCode's provider id: where OpenCode 2.0.18 itself sends that provider's requests
# (measured on the Rocky VM: 2026-10-24, the free opencode/* models' catalog baseURL and OpenAI's API; 2026-10-25,
# Anthropic's `/v1/messages` and Google's `/v1beta/models/...`, each through a relay at its provider-level baseURL). Any
# other provider, or another upstream (an AEW Provider Gateway, F18.8), is named in containment.network.upstreams.
UPSTREAMS = {"anthropic": "https://api.anthropic.com/v1", "google": "https://generativelanguage.googleapis.com/v1beta",
             "openai": "https://api.openai.com/v1", "opencode": "https://opencode.ai/inference/openai/v1"}
# The variable OpenCode 2.0.18 reads each provider's API key from (its integrations' `env` method), by provider id:
# each carried a synthetic key to its relay on the Rocky VM (2026-10-25). The contained Lead's sentinel goes there.
PROVIDER_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "google": "GOOGLE_GENERATIVE_AI_API_KEY",
                    "openai": "OPENAI_API_KEY", "opencode": "OPENCODE_API_KEY"}
# Providers whose models each carry an address of their own in OpenCode's catalog, which beats the provider-level
# baseURL (measured, 2026-10-24 and 25): the Lead, which switches models from the live catalog, cannot point them at a
# relay, so their key is never relayed for it (STG-05 CS-4). The Lead's configuration switches them off
# (``projection.LEAD_DENIED_PROVIDERS``): AEW does not use OpenCode's free models (the operator, 2026-11-06).
CATALOG_ADDRESSED = frozenset({"opencode"})
# Why AEW never relies on OpenCode's free models (the operator, 2026-11-06): OpenCode Zen's published rule, which every
# refusal for a missing provider key quotes.
FREE_TIER_RULE = ("OpenCode's published rule (https://opencode.ai/docs/zen/) is \"Free-tier chat models require "
                  "OpenCode; use paid models or Go from other clients.\"")
# What `aew init` tells the operator at first use (the designer's decision record of 2026-11-06).
FIRST_USE_LINE = ("AEW needs a provider key and a paid model: name the key's variable in the execution policy's "
                  "provider_env. On contained Linux, use a saved OpenCode API-key login through the built-in relay, "
                  "or set the named variable in the terminal you start AEW from. AEW does not use "
                  "OpenCode's free models; " + FREE_TIER_RULE)
# The closed reason of a launch refused because its provider would get no key: a worker's on the relay route (the
# engine's ``require_launchable`` and the supervisor's ``_contain``), and a contained Lead with no provider relayed
# (``lead.ContainedLead.require_provider``).
PROVIDER_KEY_MISSING = "provider_key_missing"
# A refreshing (OAuth) login's own upstream, by provider id, where it differs from the provider's API: OpenCode
# 2.0.18's ChatGPT login moves openai's requests here (its `model.request` hook; read in the bundle, and the relay
# reached through the provider-level baseURL alone, measured on the Rocky VM, 2026-10-25). The contained Lead relays
# the stored login's access token as it is, never refreshing it (the designer's addendum 1 to the CS-4 hand-off).
REFRESHING_UPSTREAMS = {"openai": "https://chatgpt.com/backend-api/codex"}
# The contained Lead's relays, one per provider, on loopback ports inside from here up (4100-4102 are the workers').
LEAD_RELAY_PORT = 4111
PROXY_NAMES = frozenset({*agentenv.PROXY_VARS, "NO_PROXY"})
# The run record's note on a refused target that is known and expected (the designer's pointer of 2026-11-06): a set
# OPENCODE_API_KEY makes OpenCode fetch its console's configuration from opencode.ai (inferred on 2.0.18; on 2.2.6 the
# `opencode.provider.opencode` plugin's fetch of https://opencode.ai/console/api/v2/config, measured by the #364 review
# from the server's log). That call would bring console-managed providers, MCP servers and policies, and since 2.2.x a
# Console `library` of session instructions and skills, into a contained run, so it stays refused, and it is never an
# allowlist entry. Defined here only, beside the record
# (:meth:`RunNetwork.refused`), and given to no other target.
CONSOLE_SYNC_TARGET = "opencode.ai:443"
CONSOLE_SYNC_NOTE = "expected: OpenCode's console sync, refused by design"
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


def require_plan_route(profile: Mapping[str, Any], policy: Mapping[str, Any] | None, *, on_relay_route: bool) -> None:
    provider = str(profile["provider"])
    name = profile["profile"]
    label = f"profile {name} uses your {provider} plan"
    if stored_key_override(provider, policy):
        raise HarnessIncompatible(f"{label}, but a provider upstream override is set. Remove the override "
                                  f"or set `credential: api_key` on {name}.",
                                  reason="plan_login_override")
    if not on_relay_route or not sys.platform.startswith("linux") or provider not in REFRESHING_UPSTREAMS:
        route = ("the plan login isn't served on Windows yet (E341); set `credential: api_key` "
                 f"and export {PROVIDER_KEY_ENV.get(provider, 'the provider key')}" if sys.platform == "win32" else
                 "the plan login needs the provider relay on Linux")
        raise HarnessIncompatible(f"{label}, but {route}.", reason="plan_login_route")


def check_plan_login(profile: Mapping[str, Any], policy: Mapping[str, Any] | None,
                     env: Mapping[str, str], *, on_relay_route: bool) -> tuple[login.StoredLogin, login.Login]:
    from aew.harness.opencode.lead import login_warning_h
    from aew.policy import execution

    require_plan_route(profile, policy, on_relay_route=on_relay_route)
    provider = str(profile["provider"])
    name = profile["profile"]
    use_key = f"Or set `credential: api_key` on {name}."
    renew = f"log in again with ChatGPT at your own terminal (`opencode auth login {provider}`)"
    label = f"profile {name} uses your {provider} plan"
    resolver = login.StoredLogin(provider, env)
    try:
        entry = resolver.deciding_login()
    except relay.Unavailable as exc:
        action = "Try again once the store is available." if exc.retryable else f"To use the plan, {renew}."
        raise HarnessIncompatible(f"{label}, but the stored login could not be read. {action} {use_key}",
                                  reason="plan_login_unreadable") from None
    if entry is None:
        raise HarnessIncompatible(f"{label}, but you have no stored {provider} login. "
                                  f"To use the plan, {renew}. {use_key}",
                                  reason="plan_login_missing")
    if entry.kind == "key":
        key_profiles = sorted(n for n, p in ((policy or {}).get("profiles") or {}).items()
                              if n != name and p["provider"] == provider
                              and execution.profile_credential(dict(policy or {}), p, provider) == execution.API_KEY)
        needs_export = (f" Profiles {', '.join(key_profiles)} on {provider} use an API key and will then need "
                        f"{PROVIDER_KEY_ENV[provider]} set where AEW starts." if key_profiles else "")
        raise HarnessIncompatible(
            f"{label}, but your stored {provider} login is an API key. To use the plan, log in with ChatGPT "
            f"at your own terminal (`opencode auth login {provider}`).{needs_export} {use_key}",
            reason="plan_login_kind_changed")
    if entry.kind != "oauth" or not entry.secret or entry.expires is None:
        raise HarnessIncompatible(f"{label}, but your stored {provider} login has a shape AEW doesn't read. "
                                  f"Log in again at your own terminal. {use_key}", reason="plan_login_unknown_shape")
    remaining = entry.expires / 1000 - time.time()
    deadline = profile.get("deadline_s")
    minimum = deadline + login.EXPIRY_MARGIN_S if deadline is not None else max(
        login_warning_h(policy) * 3600, login.EXPIRY_MARGIN_S)
    if remaining <= minimum:
        raise HarnessIncompatible(f"{label}, but the login has {max(0, remaining) / 3600:.2f} h left and cannot "
                                  f"cover this launch. To continue, {renew}.", reason="plan_login_expired")
    return resolver, entry


def relay_route(policy: Mapping[str, Any] | None, provider_relay: bool) -> bool:
    """Whether a run of a harness that calls its provider itself (its adapter's ``PROVIDER_RELAY``) reaches the
    provider only through AEW's relay: its network mode under this policy is ``proxy_only`` (:func:`mode`). The
    engine's launch check and the supervisor's both judge it so, from the policy, never from whether a sandbox was
    then established, so the two never disagree."""
    return bool(provider_relay) and mode(policy) == PROXY_ONLY


def provider_key_missing(provider: str | None, provider_env: Iterable[str], env: Mapping[str, str], *,
                         on_relay_route: bool, stored: bool = False) -> str | None:
    """The variable a run's provider reads its key from (:data:`PROVIDER_KEY_ENV`) when no key would reach the run,
    else None. Pure. On the relay route the harness gets only what the execution policy's ``provider_env`` names (a
    sentinel inside, the value in the relay), so the key reaches the run only when ``provider_env`` names that variable
    and ``env`` (the launching environment) holds a value for it; an empty value is no key (:meth:`RunNetwork.start`
    relays none). A provider whose key variable AEW does not know is never judged: a Provider Gateway upstream
    (F18.8) may need none. Off the relay route nothing is judged here."""
    variable = PROVIDER_KEY_ENV.get(provider or "")
    if not on_relay_route or variable is None:
        return None
    if variable in {str(n) for n in provider_env} and (agentenv.lookup(env, variable) or stored):
        return None
    return variable


def stored_key_candidate(provider: str | None, names: Iterable[str], env: Mapping[str, str],
                         policy: Mapping[str, Any] | None, *, on_relay_route: bool) -> bool:
    """Whether the launch is authorized to look for this provider's stored API key."""
    variable = PROVIDER_KEY_ENV.get(provider or "")
    return (
        on_relay_route and mode(policy) == PROXY_ONLY and provider in UPSTREAMS
        and not stored_key_override(provider, policy)
        and variable is not None and variable in names
        and not agentenv.lookup(env, variable)
    )


def worker_provider_names(provider: str | None, names: Iterable[str]) -> list[str]:
    """A built-in provider's worker needs its own key and any non-built-in variables."""
    own = PROVIDER_KEY_ENV.get(provider or "")
    if own is None:
        return list(names)
    other = set(PROVIDER_KEY_ENV.values()) - {own}
    return [name for name in names if (name.upper() if sys.platform == "win32" else name) not in other]


_doctor_keys: ContextVar[list[tuple[Any, set[str], dict[str, login.WorkerKey], dict[str, str]]] | None] = ContextVar(
    "doctor_worker_keys", default=None,
)


@contextmanager
def doctor_key_snapshot():
    """Keep one host snapshot for both readiness lines and all model-list reads in a doctor call."""
    token = _doctor_keys.set([])
    try:
        yield
    finally:
        _doctor_keys.reset(token)


def doctor_worker_keys(env: Mapping[str, str], providers: set[str]
                       ) -> tuple[dict[str, login.WorkerKey], dict[str, str]]:
    snapshot = _doctor_keys.get()
    if snapshot:
        path, requested, keys, why = snapshot[0]
        assert login.db_path(env) == path and providers <= requested, "doctor must preload all candidate providers"
        return ({provider: keys[provider] for provider in providers & keys.keys()},
                {provider: why[provider] for provider in providers & why.keys()})
    keys, why = login.worker_keys(env, providers)
    usable = {provider: key for provider, key in keys.items()
              if agentenv.provider_env_problem(PROVIDER_KEY_ENV[provider], {PROVIDER_KEY_ENV[provider]: key.secret})
              is None}
    why = {provider: worker_key_issue(provider, issue) for provider, issue in why.items()}
    why.update(dict.fromkeys(keys.keys() - usable.keys(), "no usable stored OpenCode API-key row for this provider"))
    if snapshot is not None:
        snapshot.append((login.db_path(env), set(providers), usable, why))
    return usable, why


def resolve_worker_key(provider: str | None, names: Iterable[str], env: Mapping[str, str],
                       policy: Mapping[str, Any] | None, *, on_relay_route: bool
                       ) -> tuple[login.WorkerKey | None, str | None]:
    """Resolve the stored fallback only. Explicit values retain the ordinary environment checks."""
    if not stored_key_candidate(provider, names, env, policy, on_relay_route=on_relay_route):
        return None, None
    assert provider is not None
    keys, why = doctor_worker_keys(env, {provider})
    key = keys.get(provider)
    return key, why.get(provider)


STORED_REQUIRES_RELAY = "the stored OpenCode login needs the provider relay"
STORED_REQUIRES_BUILTIN = "the stored OpenCode login is used only with the built-in upstream"


def worker_key_issue(provider: str, issue: str) -> str:
    if issue == login.REFRESHING_LOGIN:
        kind = "ChatGPT" if provider == "openai" else "OAuth"
        detail = (f"the stored login is a refreshing ({kind}) login; set {PROVIDER_KEY_ENV[provider]} "
                  "where AEW starts for API-key workers")
        if provider in REFRESHING_UPSTREAMS:
            detail += (f", or set `credential: plan_login` on the profile or "
                       f"`credentials: {{{provider}: plan_login}}` to use your plan once qualified")
        return detail
    return issue


def stored_key_remedy(provider: str, detail: str | None) -> str:
    if not detail:
        return ""
    remedy = (f" At your own terminal run `opencode auth login {provider}` and choose the API-key method "
              "when it is appropriate to change that provider's deciding login, or use the named export."
              if detail not in (STORED_REQUIRES_RELAY, STORED_REQUIRES_BUILTIN)
              and worker_key_issue(provider, login.REFRESHING_LOGIN) not in detail else "")
    return f". {detail}." + remedy


def stored_key_override(provider: str | None, policy: Mapping[str, Any] | None) -> bool:
    return provider in (settings(policy).get("upstreams") or {})


def provider_key_message(provider: str, variable: str, *, stored_detail: str | None = None) -> str:
    """The refusal of a worker launch whose provider would get no key (:func:`provider_key_missing`): why, the
    published rule, and both steps."""
    return (f"the run's provider {provider} would get no key: a contained run reaches its provider only through AEW's "
            f"provider relay, which adds the key {variable} holds, and the execution policy's provider_env does not "
            f"name {variable}, or it is not set where AEW launches. AEW does not use OpenCode's free models; "
            f"{FREE_TIER_RULE} Set a key: name {variable} in the execution policy's provider_env "
            f"(`provider_env: [{variable}]`) and set it in the terminal you start AEW from, or the Lead session you "
            f"launch from (`aew opencode` keeps the environment it started with). Then pin a paid model of {provider} "
            "in the execution policy's profile, or dispatch a new invocation with --profile or --model"
            + stored_key_remedy(provider, stored_detail))


def refused_note(target: str, provider: str | None, key_relayed: bool) -> str | None:
    """The fixed note a refused target gets in the run's record: :data:`CONSOLE_SYNC_NOTE` for
    :data:`CONSOLE_SYNC_TARGET` on a run whose provider is ``opencode`` with its key relayed; None for anything
    else."""
    if target == CONSOLE_SYNC_TARGET and provider == "opencode" and key_relayed:
        return CONSOLE_SYNC_NOTE
    return None


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


def upstream(provider: str | None, policy: Mapping[str, Any] | None,
             known: Mapping[str, str] = UPSTREAMS) -> relay.Upstream:
    """The provider relay's fixed upstream: the policy's ``upstreams.<provider>``, else ``known``'s
    (:data:`UPSTREAMS` by default). Raises ``ContainmentUnavailable``
    when there is none, saying what to set."""
    configured = settings(policy).get("upstreams") or {}
    url = configured.get(provider) if isinstance(configured, dict) else None
    url = url or known.get(provider or "")
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


def relay_tls(provider: str | None,
              policy: Mapping[str, Any] | None) -> tuple[ssl.SSLContext | None, client_cert.ClientCert | None]:
    """The relay's upstream TLS context for ``provider``: its client certificate's, read now, at the relay's start
    (register E123), and the files it was read from; (None, None) when the policy names none, and the relay uses the
    system's verifying context. Raises ``ContainmentUnavailable`` on a certificate that cannot be used: no fallback."""
    found = client_cert.for_provider(provider, policy)
    return (client_cert.context(found), found) if found is not None else (None, None)


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


def _relay_sock(provider: str) -> str:
    """The socket file of the Lead's relay for ``provider``, in the run's network directory."""
    return f"relay-{provider}.sock"


def _grant(token: str, resolve: Callable[[], tuple[str, Mapping[str, str]]]) -> relay.Grant:
    """One request's grant from a refreshing login's resolver: its credential for the relay's sentinel, and its
    headers."""
    value, headers = resolve()
    return {token: value}, headers


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
        self.relays: dict[str, tuple[int, relay.ProviderRelay]] = {}  # the Lead's: provider -> (port inside, relay)
        self.login_sentinels: dict[str, str] = {}  # the Lead's refreshing logins: provider -> its sentinel inside
        self.server_leg = True    # the harness server is reached through the shim: a worker's, and the Lead's (E210)
        self.lead = False         # the Lead's network: its relays are per provider
        self.http_proxy = False   # the Lead's HTTP_PROXY names the egress proxy too, for its refusal's https form
        self.provider: str | None = None  # a worker's provider, and whether its key reached its relay: kept from the
        self.key_relayed = False          # start for the record's note (:meth:`refused`), as close() clears the values
        self.key_source: str | None = None
        self.stored_key_variable: str | None = None
        self._closed = False

    @classmethod
    def start(cls, layout: Layout, *, provider: str | None, provider_env: Iterable[str],
              policy: Mapping[str, Any] | None, env: Mapping[str, str], relay_needed: bool,
              allow: egress.Allowlist | None = None, stored: login.WorkerKey | None = None,
              plan: tuple[login.StoredLogin, login.Login] | None = None) -> RunNetwork:
        """Start what ``layout``'s network needs: under ``proxy_only``, the relay (when the harness calls a provider,
        ``relay_needed``) and the egress proxy with ``allow``, the run's allowlist (``egress_policy``), when there is
        one. The caller builds that allowlist once and gives the same one to the run's self-test, so the self-test
        checks the proxy the run gets (register E143). Raises ``ContainmentUnavailable`` when the relay has no
        upstream, or a socket cannot be made."""
        names = [str(n) for n in provider_env]
        secret = [n for n in names if n.upper() not in PROXY_NAMES]
        values = {n: agentenv.lookup(env, n) or "" for n in secret}
        sentinels = {n: relay.sentinel() for n in secret}
        if plan is not None:
            variable = PROVIDER_KEY_ENV[plan[0].integration]
            values[variable] = agentenv.lookup(env, variable) or ""
            sentinels.pop(variable, None)
        net = cls(layout, sentinels=sentinels, values=values)
        net.provider = provider
        if layout.network != PROXY_ONLY or not layout.net_dir:
            return net
        try:
            if plan is not None:
                resolver, initial = plan
                target = relay.Upstream(REFRESHING_UPSTREAMS[resolver.integration])
                token = relay.sentinel()
                net._values[f"{resolver.integration} login"] = initial.secret
                net.login_sentinels[resolver.integration] = token
                net.key_source = "plan login"
                try:
                    proxy = operator_proxy(target, names, env)
                except AEWError as exc:
                    raise ContainmentUnavailable(exc.message, reason="bad_proxy") from None
                net.relay = relay.ProviderRelay(
                    target, {}, proxy=proxy, resolve=functools.partial(_grant, token, resolver.worker_grant),
                    listener=listen(os.path.join(layout.net_dir, RELAY))).start()
            elif relay_needed:
                target = upstream(provider, policy)
                if stored is not None and stored_key_candidate(provider, names, env, policy, on_relay_route=True):
                    variable = PROVIDER_KEY_ENV[provider or ""]
                    net._values[variable] = values[variable] = stored.secret
                    net.stored_key_variable = variable
                try:
                    proxy = operator_proxy(target, names, env)
                except AEWError as exc:
                    raise ContainmentUnavailable(exc.message, reason="bad_proxy") from None
                tls, client = relay_tls(provider, policy)
                relayed_names = worker_provider_names(provider, values)
                net.relay = relay.ProviderRelay(
                    target, {sentinels[n]: values[n] for n in relayed_names if values[n]},
                    proxy=proxy, tls=tls, client=client,
                    listener=listen(os.path.join(layout.net_dir, RELAY))).start()
                net.key_relayed = bool(values.get(PROVIDER_KEY_ENV.get(provider or "", "")))
                if net.key_relayed:
                    net.key_source = "stored OpenCode login" if net.stored_key_variable else "environment"
            if allow is not None:
                net.egress = egress.EgressProxy(allow, listener=listen(os.path.join(layout.net_dir, EGRESS))).start()
        except OSError as exc:
            net.close()
            raise ContainmentUnavailable(f"the run's network could not be set up: {exc}", reason="network") from None
        except BaseException:
            net.close()
            raise
        return net

    @classmethod
    def start_lead(cls, layout: Layout, *, keys: Mapping[str, str], provider_env: Iterable[str],
                   policy: Mapping[str, Any] | None, env: Mapping[str, str],
                   refreshing: Mapping[str, Callable[[], tuple[str, Mapping[str, str]]]] | None = None,
                   keyless: Iterable[str] = ()) -> RunNetwork:
        """The contained Lead's network (STG-05 CS-4, outcome 3). Under ``proxy_only``: a relay for each provider in
        ``keys`` (provider id -> its key, from the operator's stored login or a ``--provider-env`` variable), on its
        own loopback port inside from :data:`LEAD_RELAY_PORT`, with its sentinel in the provider's variable
        (:data:`PROVIDER_KEY_ENV`); a relay for each provider in ``refreshing`` (provider id -> what gives its stored
        login's credential and headers for each request, raising ``relay.Unavailable`` when it has none), to
        :data:`REFRESHING_UPSTREAMS`, whose sentinel the session puts in the Lead's own login store
        (:attr:`login_sentinels`); and the egress proxy under the any-public policy (the operator's decision 3 of
        2026-10-21), which ``HTTPS_PROXY`` and ``HTTP_PROXY`` both name inside. ``provider_env``'s proxy variables are
        the relays' own route to their upstreams, as a worker's are. ``keyless`` names providers of their own id whose
        relay presents a client certificate and carries no key (register E123): their upstream is the policy's
        ``containment.network.upstreams``. Raises ``ContainmentUnavailable`` as :meth:`start` does."""
        names = [str(n) for n in provider_env]
        net = cls(layout)
        net.lead, net.http_proxy = True, True
        if layout.network != PROXY_ONLY or not layout.net_dir:
            return net
        resolvers = {p: resolve for p, resolve in (refreshing or {}).items()
                     if p in REFRESHING_UPSTREAMS and not stored_key_override(p, policy)}
        try:
            for i, provider in enumerate(sorted({*keys, *resolvers, *keyless})):
                resolve = resolvers.get(provider)
                target = relay.Upstream(REFRESHING_UPSTREAMS[provider]) if resolve else upstream(provider, policy)
                try:
                    proxy = operator_proxy(target, names, env)
                except AEWError as exc:
                    raise ContainmentUnavailable(exc.message, reason="bad_proxy") from None
                token = relay.sentinel()
                tls, client = relay_tls(provider, policy)
                listener = listen(os.path.join(layout.net_dir, _relay_sock(provider)))
                if resolve is None and provider not in keys:  # a client certificate alone: nothing to swap in
                    served = relay.ProviderRelay(target, {}, proxy=proxy, listener=listener, tls=tls, client=client)
                elif resolve is None:
                    net.sentinels[PROVIDER_KEY_ENV[provider]] = token
                    net._values[PROVIDER_KEY_ENV[provider]] = keys[provider]
                    served = relay.ProviderRelay(target, {token: keys[provider]}, proxy=proxy, listener=listener,
                                                 tls=tls, client=client)
                else:
                    net.login_sentinels[provider] = token
                    try:  # what the login holds now, for the leak check; one already expired has nothing to leak
                        net._values[f"{provider} login"] = resolve()[0]
                    except relay.Unavailable:
                        pass
                    served = relay.ProviderRelay(target, {}, proxy=proxy, listener=listener, tls=tls, client=client,
                                                 resolve=functools.partial(_grant, token, resolve))
                net.relays[provider] = (LEAD_RELAY_PORT + i, served.start())
            net.egress = egress.EgressProxy(egress.AnyPublic(),
                                            listener=listen(os.path.join(layout.net_dir, EGRESS))).start()
        except OSError as exc:
            net.close()
            raise ContainmentUnavailable(f"the Lead's network could not be set up: {exc}", reason="network") from None
        except BaseException:
            net.close()
            raise
        return net

    def lead_bases(self) -> dict[str, str]:
        """The Lead's provider ``baseURL`` for each relayed provider: its relay's loopback port inside, with the
        upstream's path."""
        return {p: f"http://127.0.0.1:{port}{r.upstream.path}" for p, (port, r) in self.relays.items()}

    @property
    def server_socket(self) -> str | None:
        """Where the supervisor reaches the harness server (through the shim), or None without a network of its own."""
        return os.path.join(self.dir, SERVER) if self.dir else None

    def spec(self) -> dict[str, Any]:
        assert self.dir is not None
        spec = shim_spec(self.dir, server=SERVER if self.server_leg else None, relay_sock=RELAY if self.relay else None,
                         egress_sock=EGRESS if self.egress else None)
        spec["out"] += [{"port": port, "unix": os.path.join(self.dir, _relay_sock(p))}
                        for p, (port, _) in self.relays.items()]
        return spec

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
            if self.http_proxy:  # NO_PROXY keeps the loopback relays direct (measured on the Rocky VM, 2026-10-25)
                out.update({"HTTP_PROXY": url, "http_proxy": url})
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
        out: dict[str, Any] = {"mode": self.mode}
        if not self.lead:
            out.update(relay.describe(self.relay))
            if self.key_source:
                out["provider_key_source"] = self.key_source
        else:  # the Lead's: each relayed provider's fixed upstream
            out["provider_relay"] = "configured" if self.relays else "none"
            out["provider_relays"] = {p: r.upstream.url for p, (_, r) in self.relays.items()}
        if self.egress is not None:
            policy = self.egress.policy.describe()
            if "allow" in policy:
                out["egress_allow"] = policy["allow"]
            else:
                out["egress_policy"] = policy.get("policy")
            out["limits"] = [EGRESS_RESIDUAL]
        return out

    def _services(self) -> list[tuple[str, Any]]:
        return [*(("relay", self.relay), ("egress", self.egress)),
                *((f"relay:{p}", r) for p, (_, r) in self.relays.items())]

    def refused(self) -> dict[str, Any] | None:
        """The run's refused egress targets, for its record at its end, or None without an egress proxy: the proxy's
        (``egress.EgressProxy.refused_targets``), each with its fixed note where :func:`refused_note` gives one.
        Records only: it is written beside the run's ``containment`` label, never in it, so no Lead read of the
        label (``harness status``, ``harness wait``) and no system text carries it, and nothing offers a target as an
        allowlist entry. The agent chose the string: today it is only in the run's JSON record, and any reader that
        shows it escapes it."""
        if self.egress is None:
            return None
        found = self.egress.refused_targets()
        for entry in found["targets"]:
            note = refused_note(entry["target"], self.provider, self.key_relayed)
            if note is not None:
                entry["note"] = note
        return found

    def decisions(self) -> dict[str, dict[str, int]]:
        """What the relays and the egress proxy decided, counted by outcome, for the run's record at its end."""
        return {name: service.counts() for name, service in self._services() if service is not None}

    def close(self) -> None:
        """Stop the relays and the egress proxy and remove the run's network directory. Idempotent."""
        if self._closed:
            return
        self._closed = True
        try:
            for _, service in self._services():
                if service is not None:
                    service.close()
        finally:
            self._values.clear()
            if self.dir:
                shutil.rmtree(self.dir, ignore_errors=True)


__all__ = ["EGRESS_PORT", "ISOLATED", "NETWORK_MODES", "NOT_PROVIDED", "PROVIDER_PORT", "PROXY_ONLY", "RunNetwork",
           "SERVER_PORT", "SHARED", "mode", "private_dir", "settings", "shim_spec", "upstream"]
