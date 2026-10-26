"""``aew opencode``: the Lead's OpenCode TUI as a Lead session (ADR-0009; M3 plan §2.6).

The TUI runs through ``aew lead session`` (:mod:`aew.harness.lead_broker`), so the Lead's model never
holds the Lead credential: Lead-authenticated ``aew`` commands reach this session's broker.

**The Lead model's shell environment is curated.** A V2 TUI that runs its own server (``--standalone``)
sends its own environment, minus the server password, as every session's shell environment, and its
private server inherits the same environment. So the environment given to the TUI is exactly what the
Lead's model and its shell commands can see: an allowlist (operating-system basics, ``XDG_*``), ``PATH``
with ``aew`` first, the broker's coordinates, and the Lead projection. It holds no AEW credential and no
provider key. AEW writes nothing into the operator's OpenCode state: the Lead projection is
``OPENCODE_CONFIG_CONTENT``, and project configuration in the repository is not loaded (the Lead's context
comes from ``aew resume``).

**On Linux the Lead runs contained** (STG-05 CS-4; :class:`ContainedLead`). The TUI and everything it starts run in a
``lead`` sandbox (``containment.establish``, self-tested before the TUI starts, in the execution policy's mode,
``required`` by default) that writes only the working tree and its own directories, on a network of its own
(``proxy_only``, any public address through the egress proxy), on a terminal the session reaper relays
(``procs.run_session_tree(relay=True)``). Its OpenCode state is AEW's, kept per project under
``.aew/local/harness/lead/``: the operator's OpenCode login and configuration are not in it. Each provider of the
operator's stored login gets a relay on the host, which holds the key (``login``, ``netns.RunNetwork.start_lead``); the
sandbox holds only a sentinel. ``--provider-env NAME`` feeds NAME's provider relay in the same way. A refreshing login
AEW has measured (openai's ChatGPT login) is relayed as stored (:class:`StoredLogin`): re-read on each request and never
refreshed or written, with a row in the Lead's own login store that holds the relay's sentinel.

**Elsewhere** (Windows) the TUI runs in the operator's normal OpenCode environment (their providers,
configuration and skills), labelled not contained. The Lead's model then authenticates with the credentials
OpenCode stores for the operator, and ``--provider-env NAME`` passes a key explicitly, which the Lead's shell
can then read; the command says so.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aew import process_kind
from aew.errors import AEWError, ContainmentUnavailable, HarnessIncompatible, UsageError
from aew.harness import agentenv, lead_broker, runlog
from aew.harness.opencode import capabilities, login, projection
from aew.harness.opencode.adapter import binary_command

log = logging.getLogger(__name__)

PASSED_THROUGH = ("OPENCODE_CONFIG", "SHELL")  # the operator's own config file and shell choice
LEAD_DIR = "local/harness/lead"  # under the AEW root: the contained Lead's OpenCode state, per project (addendum 1)
# Set inside the contained Lead's sandbox: AEW's CLI there is a non-writer (``process_kind``, its owner), and a write
# that meets the read-only store says why (``cli.main``). Never authority.
CONTAINED_ENV = process_kind.LEAD_CONTAINED_ENV
# The operator's OpenCode configuration files, in its configuration directory (OpenCode 2.0.18).
CONFIG_FILES = ("config.json", "opencode.json", "opencode.jsonc")
# A refreshing login the contained Lead relays as stored (the designer's addendum 1 to the CS-4 hand-off, option a).
# Implementation bound: a request that starts with less than this left on the access token may outlive it mid-answer
# (a 136 KB streamed answer took 7.8 s through a slow client in CS-3b's live lane), so the relay counts it expired.
EXPIRY_MARGIN_S = 60.0
# The cheapest use of the operator's own OpenCode that resolves, and so refreshes, a stored login: `opencode auth list`
# went to the provider's token endpoint with no model call (measured on the Rocky VM, 2026-10-25).
REFRESH_COMMAND = "opencode auth list"
# What the operator runs when a relayed login has expired: the expiry message and the launch's warning both give it.
REFRESH_STEP = (f"`{REFRESH_COMMAND}` at your own terminal: your OpenCode refreshes it there, and the Lead's next "
                "request then works, with no restart")
# A relayed login that expires within this many hours is named at the Lead's launch (the designer's addendum 2,
# ruling 1: one working day's session). The operator's execution policy changes it: containment.lead.login_warning_h.
LOGIN_WARNING_H = 24
# What renews such a login before it expires (addendum 3, ruling 2). A refresh does not: OpenCode refreshes a login
# only in its last 5 minutes. A fresh login does: OpenCode 2.0.18 stores it as a new row, active over the provider's
# others, with a new expiry (`Credential.create`, read in the pinned bundle), and the relay reads the active row.
RENEW_STEP = ("To renew it now, log in again at your own terminal (`opencode auth login {provider}`): your OpenCode "
              "stores a fresh login, and the Lead's next request uses it, with no restart.")
# Headers a refreshing login's requests carry from its stored metadata, which the relay sets so that the operator's
# values never go inside: header -> metadata key. OpenCode 2.0.18's ChatGPT login sends its account id (measured).
LOGIN_HEADERS = {"openai": {"chatgpt-account-id": "accountID"}}
# The Lead's own row for such a login expires this far off, so the TUI never tries to refresh it (that needs the
# operator's refresh token, which never goes inside).
INSIDE_LOGIN_S = 365 * 86400
# OpenCode makes its database in about 5 s, offline, in a sandbox on the Rocky VM (`session list`, 2026-10-25); the
# Lead's first session in a project waits this long at most before it goes on without its refreshing logins.
SEED_TIMEOUT_S = 60.0
# Implementation bound: the operator's recent and favourite models (`<state>/model.json`) are a list of model ids, a
# few hundred bytes; a larger file is not that, and is not copied into the Lead's state.
MODEL_SEED_MAX = 64 * 1024


def guide_of(engine: Any) -> str:
    """The project's Lead guide (F16), or nothing when its policy cannot be read (the Lead then sees why elsewhere)."""
    try:
        return str(engine.lead_guide())
    except AEWError:
        return ""


def refuse_unusable(provider_env: list[str], base: Mapping[str, str]) -> None:
    """Refuses a ``--provider-env`` variable no harness could be given: the one rule, which doctor and every launch
    share (the contained Lead's and `--print-config`'s included)."""
    for name, why in agentenv.provider_env_problems(provider_env, base):
        raise UsageError(f"--provider-env {name}: {why}", variable=name)


def tui_env(base: Mapping[str, str], *, provider_env: list[str], guide: str = "") -> dict[str, str]:
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    env = {k: v for k, v in base.items() if k.upper() in keep or k.upper().startswith("XDG_")
           or (sys.platform != "win32" and k.startswith("LC_")) or k.upper() in PASSED_THROUGH}
    aew_bin = os.path.dirname(sys.executable)
    path = [p for p in (base.get("PATH") or base.get("Path") or "").split(os.pathsep) if p]
    env["PATH"] = os.pathsep.join([aew_bin, *[p for p in path if os.path.normcase(p) != os.path.normcase(aew_bin)]])
    env["PYTHONUTF8"] = "1"
    refuse_unusable(provider_env, base)
    for name in provider_env:
        env[name] = str(agentenv.lookup(base, name))  # the same lookup the checks use (Windows: any case)
    agentenv.bypass_proxy_for_loopback(env)
    env.update({"OPENCODE_CONFIG_CONTENT": json.dumps(projection.lead_config(guide), sort_keys=True),
                "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_AUTOUPDATE": "1"})
    return env


def command(engine: Any, extra_args: list[str]) -> list[str]:
    args = [a for a in extra_args if a != "--"]
    if "--server" in args or any(a.startswith("--server=") for a in args):
        raise UsageError("`aew opencode` runs the TUI with its own private server (--standalone): with --server the "
                         "TUI would not give sessions its curated environment")
    return [*binary_command(), "--standalone", *args, str(engine.repo_root)]


def check_version() -> str:
    """The CLI's version, refusing a non-V2 OpenCode before anything starts."""
    kwargs: dict[str, Any] = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
    out = subprocess.run([*binary_command(), "--version"], capture_output=True, text=True, timeout=60,
                         stdin=subprocess.DEVNULL, **kwargs)
    version = (out.stdout or "").strip().split()[-1].lstrip("v") if out.stdout.strip() else ""
    gaps = capabilities.version_problems(version)
    if out.returncode != 0 or gaps:
        raise HarnessIncompatible(f"the OpenCode CLI is not usable for the Lead: {gaps or out.stderr.strip()[-300:]}",
                                  version=version or None)
    return version


def contained_here() -> bool:
    """Whether this platform runs the Lead contained (STG-05 CS-4): Linux. Windows has no bubblewrap (F48)."""
    return sys.platform.startswith("linux")


def describe(engine: Any, *, provider_env: list[str], extra_args: list[str] | None = None) -> dict[str, Any]:
    """What `aew opencode` would run, without starting anything (no values of environment variables)."""
    guide = guide_of(engine)
    refuse_unusable(provider_env, os.environ)  # contained, the variables feed relays and stay out of the TUI's env
    env = tui_env(os.environ, provider_env=[] if contained_here() else provider_env, guide=guide)
    try:
        argv: list[str] | str = command(engine, extra_args or [])
    except HarnessIncompatible as exc:
        argv = f"unavailable: {exc.message}"
    notes = ["The TUI's own environment becomes every Lead session's shell environment (V2 --standalone)."]
    if contained_here():
        notes += ["On Linux the TUI runs contained (STG-05 CS-4): in a self-tested sandbox, on its own network, on a "
                  "relayed terminal; the configuration shown gains the session's relayed providers and its "
                  "contained line.",
                  "No AEW credential and no provider key is in it: --provider-env feeds a provider's relay on the "
                  "host, and the sandbox holds a placeholder."]
    else:
        notes.append("No AEW credential and no provider key is in it unless passed with --provider-env.")
    return {"command": argv, "config": projection.lead_config(guide),
            "env_names": sorted([*env, *lead_broker.ENV_NAMES]), "provider_env": provider_env, "notes": notes}


def run(engine: Any, *, acquire: bool, session_label: str | None, keep_seat: bool, provider_env: list[str],
        extra_args: list[str], print_config: bool) -> dict[str, Any]:
    if print_config:
        return {"ok": True, **describe(engine, provider_env=provider_env, extra_args=extra_args)}
    stages = StartStages()
    version = check_version()
    stages.mark("version")
    guide = guide_of(engine)
    argv = command(engine, extra_args)
    if contained_here():
        # Everything that can refuse does so before a seat is taken (an acquired seat whose credential is lost
        # would stay held), a missing credential first.
        lead_broker.require_credential(acquire)
        lead = ContainedLead(engine, argv=argv, provider_env=provider_env, guide=guide, base=os.environ,
                             stages=stages)
        lead.announce(sys.stderr)
        stages.mark("logins")
        out = lead_broker.run_session(engine, argv, acquire=acquire, session_label=session_label, keep_seat=keep_seat,
                                      env=tui_env(os.environ, provider_env=[], guide=guide), contained=lead)
        return {**out, "opencode": version}
    env = tui_env(os.environ, provider_env=provider_env, guide=guide)
    if provider_env:
        sys.stderr.write(f"aew opencode: {', '.join(provider_env)} passed to the Lead's OpenCode; the Lead model's "
                         "shell commands can read it.\n")
    from aew.harness import containment

    out = lead_broker.run_session(engine, argv, acquire=acquire, session_label=session_label, keep_seat=keep_seat,
                                  env=env)
    return {**out, "containment": containment.label(contained=False), "opencode": version}


# ---------------------------------------------------------------------------------------- the contained Lead (Linux)

def _jsonc(text: str) -> Any:
    """JSON with comments and trailing commas, as OpenCode reads its configuration (strings are left whole)."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            i = text.find("\n", i) if "\n" in text[i:] else n
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(c)
            i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def _operator_dir(base: Mapping[str, str], kind: str) -> Path:
    """The operator's OpenCode directory of ``kind`` (``config`` or ``state``), from their environment."""
    home = Path(base.get("HOME") or os.path.expanduser("~"))
    default = {"config": home / ".config", "state": home / ".local" / "state"}[kind]
    return Path(base.get(f"XDG_{kind.upper()}_HOME") or default) / "opencode"


def operator_preferences(base: Mapping[str, str]) -> tuple[dict[str, Any] | None, list[str], str | None]:
    """``(preferences, plugins, unread)``: the operator's TUI preferences (OpenCode 2.0.18's ``cli.json`` in its
    configuration directory: theme, keybinds and the like, no credential) without its ``plugins``, which stay out of
    the contained Lead (A-38's CAPR-05; the designer's addendum 1, item 2); the plugins' names; and the file, when it
    could not be read. ``None`` when there is no such file."""
    path = _operator_dir(base, "config") / "cli.json"
    if not path.is_file():
        return None, [], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [], f"{path} ({type(exc).__name__})"
    if not isinstance(data, dict):
        return None, [], f"{path} (not a JSON object)"
    plugins = data.pop("plugins", None)
    items = plugins if isinstance(plugins, list) else list(plugins) if isinstance(plugins, dict) else []
    names = [str(p.get("name", "?") if isinstance(p, dict) else p) for p in items]
    return data, names, None


def operator_mcp_servers(base: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """``(names, unread)``: the MCP servers the operator's own OpenCode configuration names, which the contained Lead
    does not load, and the configuration files that could not be read. Names only."""
    directory = _operator_dir(base, "config")
    paths = [directory / name for name in CONFIG_FILES] + ([Path(base["OPENCODE_CONFIG"])]
                                                           if base.get("OPENCODE_CONFIG") else [])
    names: list[str] = []
    unread: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            data = _jsonc(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unread.append(str(path))
            continue
        mcp = data.get("mcp") if isinstance(data, dict) else None
        servers = mcp.get("servers") if isinstance(mcp, dict) and isinstance(mcp.get("servers"), dict) else mcp
        if isinstance(servers, dict):
            names += [str(k) for k in servers if str(k) not in names]
    return names, unread


def _launching_terminal() -> list[int]:
    """The operator's terminal, standard input's device: what row 4 must not find open in the Lead's sandbox."""
    if sys.platform == "win32":
        raise UsageError("the Lead is contained on Linux only (STG-05 CS-4); on Windows it runs labelled not contained")
    rdev = os.fstat(0).st_rdev
    return [os.major(rdev), os.minor(rdev)]


def login_warning_h(policy: Mapping[str, Any] | None) -> int:
    """The execution policy's ``containment.lead.login_warning_h``, else :data:`LOGIN_WARNING_H`."""
    found = (((policy or {}).get("containment") or {}).get("lead") or {}).get("login_warning_h")
    return found if isinstance(found, int) and not isinstance(found, bool) and found >= 0 else LOGIN_WARNING_H


def _unknown(provider: str) -> str:
    """Why a stored login in a shape AEW does not know is not used, and what serves its provider instead."""
    from aew.harness.containment import netns

    variable = netns.PROVIDER_KEY_ENV.get(provider)
    return (f"in a shape AEW does not know (AEW reads OpenCode {', '.join(capabilities.TESTED_VERSIONS)}'s, and never "
            "guesses at another), so the contained Lead does not use it"
            + (f"; to serve {provider} with an API key instead, start `aew opencode --provider-env {variable}`"
               if variable and provider not in netns.CATALOG_ADDRESSED else ""))


def _not_served(provider: str) -> str:
    """Why a provider whose models carry their own catalogue address gets no relay (the designer's addendum 2, ruling
    2): its key, stored or in the environment, never goes inside, and OpenCode 2.0.18 offers only the provider's free
    models without one (it turns off every model with an input cost, read in the pinned bundle)."""
    return (f"not served yet: OpenCode's catalog gives each {provider}/* model an address of its own, so no relay can "
            f"carry its key, and the key stays out of the Lead; without it OpenCode offers only the free {provider} "
            "models, which work through the egress proxy")


def _left(entry: login.Login) -> str:
    """How long a refreshing login's access token has left, for the start line."""
    if entry.expires is None:
        return "its expiry unknown"
    hours = (entry.expires / 1000 - time.time()) / 3600
    if hours <= 0:
        return "expired now"
    return f"{max(1, round(hours * 60))} min left" if hours < 1 else f"{hours:.0f} h left"


class StoredLogin:
    """A refreshing login the contained Lead's relay serves as stored (the designer's addendum 1, option a): the
    operator's login store is read on each request, read-only (``login.stored``), so a refresh by the operator's own
    OpenCode is used from the next request on. AEW never refreshes it and never writes it. Raises
    ``relay.Unavailable`` with what to do when the login is gone, is in a shape AEW does not know, has changed kind or
    has expired: the TUI shows that message as the request's error."""

    def __init__(self, integration: str, base: Mapping[str, str]) -> None:
        self.integration, self.base = integration, dict(base)

    def __call__(self) -> tuple[str, dict[str, str]]:
        from aew.harness.containment import relay

        logins, why = login.stored(self.base)
        entry = next((e for e in logins if e.integration == self.integration), None)
        if entry is None:
            raise relay.Unavailable(f"AEW: your stored {self.integration} login could not be read "
                                    f"({why or 'it is no longer there'}). Log in with your own OpenCode "
                                    "(`opencode auth login`); the Lead's next request then works, with no restart.")
        if entry.kind == login.UNKNOWN:
            raise relay.Unavailable(f"AEW: your stored {self.integration} login is now {_unknown(self.integration)}.")
        if entry.kind != "oauth":
            raise relay.Unavailable(f"AEW: your stored {self.integration} login is now an API key, which this Lead "
                                    "session's relay was not set up for. Restart `aew opencode` to use it.")
        if entry.expires is None or entry.expires / 1000 - EXPIRY_MARGIN_S <= time.time():
            raise relay.Unavailable(f"AEW: your stored {self.integration} login has expired, and the contained Lead "
                                    "never refreshes it (that would write your OpenCode's own login). "
                                    f"Run {REFRESH_STEP}.")
        meta = entry.metadata
        return entry.secret, {h: str(meta[k]) for h, k in LOGIN_HEADERS.get(self.integration, {}).items()
                              if meta.get(k)}


class StartStages:
    """How long each stage of the contained Lead's start took, in seconds, on its label and in the debug log (the
    designer's addendum 3: five starts of 15 to 31 s on the Rocky VM went unexplained, so a recurrence in the
    operator's trial names its stage): ``version`` (the OpenCode CLI's), ``logins`` (the stored logins, the policy
    and the start lines), ``seat`` (the seat and the broker), ``sandbox`` (built and self-tested), ``network`` (the
    relays and the egress proxy), ``lead_logins`` (the Lead's own login rows; its database the first time)."""

    def __init__(self) -> None:
        self.last = time.monotonic()
        self.seconds: dict[str, float] = {}

    def mark(self, stage: str) -> None:
        now = time.monotonic()
        self.seconds[stage] = round(now - self.last, 3)
        self.last = now
        log.debug("aew opencode: start stage %s took %.3f s", stage, self.seconds[stage])


class ContainedLead:
    """The contained Lead's session (STG-05 CS-4), made before the seat is taken: the operator's terminal, the
    providers to relay (their keys in this process's memory only), and what the session leaves out. Called by the
    broker once it serves (``lead_broker.run_session``'s ``contained``), it builds the sandbox and returns what runs.

    Raises ``UsageError`` before anything starts: without a terminal (the TUI runs on a relayed one), or for a
    ``--provider-env`` variable that cannot be passed or that no relayed provider reads."""

    def __init__(self, engine: Any, *, argv: list[str], provider_env: list[str], guide: str,
                 base: Mapping[str, str], stages: StartStages | None = None) -> None:
        from aew.harness.containment import netns

        self.stages = stages or StartStages()

        if not os.isatty(0):
            raise UsageError("the contained Lead's TUI runs on a terminal AEW relays (STG-05 CS-4): run `aew opencode` "
                             "at a terminal")
        refuse_unusable(provider_env, base)
        self.terminal = _launching_terminal()
        self.engine, self.argv, self.guide, self.base = engine, list(argv), guide, base
        self.warning_h = login_warning_h(engine.execution_policy()[0])
        self.provider_env = [str(n) for n in provider_env]
        by_variable = {v: p for p, v in netns.PROVIDER_KEY_ENV.items() if p not in netns.CATALOG_ADDRESSED}
        self.keys: dict[str, str] = {}
        self.fed: dict[str, str] = {}  # --provider-env variable -> the provider whose relay it feeds
        for name in self.provider_env:
            if name.upper() in netns.PROXY_NAMES:
                continue  # the relays' own route to their upstreams, as a worker's
            provider = by_variable.get(name)
            if provider is None:
                raise UsageError(f"--provider-env {name}: the contained Lead passes a provider variable to that "
                                 "provider's relay on the host, and no provider it relays reads this one (it relays "
                                 f"{', '.join(sorted(by_variable))})", variable=name)
            self.fed[name] = provider
            self.keys[provider] = str(agentenv.lookup(base, name))
        self.logins, self.no_logins = login.stored(base)
        self.lines: list[str] = []
        self.refreshing: dict[str, login.Login] = {}  # provider -> its refreshing login, relayed as stored
        for entry in self.logins:
            if entry.integration in self.keys:
                self.lines.append(f"{entry.integration} ({entry.kind}): fed by --provider-env instead")
            elif entry.kind == login.UNKNOWN:
                self.lines.append(f"{entry.integration}: not relayed; its stored login is "
                                  f"{_unknown(entry.integration)}")
            elif entry.integration in netns.CATALOG_ADDRESSED:
                self.lines.append(f"{entry.integration} ({entry.kind}): {_not_served(entry.integration)}")
            elif entry.kind != "key" and entry.integration in netns.REFRESHING_UPSTREAMS:
                self.refreshing[entry.integration] = entry
                self.lines.append(f"{entry.integration} ({entry.kind}): relayed as stored, {_left(entry)}; AEW never "
                                  f"refreshes it: when it expires, `{REFRESH_COMMAND}` at your own terminal refreshes "
                                  "it, and the Lead's next request works")
            elif entry.kind != "key":
                self.lines.append(f"{entry.integration} ({entry.kind}): not relayed; of the refreshing logins, AEW "
                                  "serves those whose requests it has measured: "
                                  f"{', '.join(sorted(netns.REFRESHING_UPSTREAMS))}")
            elif entry.integration not in netns.PROVIDER_KEY_ENV:
                self.lines.append(f"{entry.integration} ({entry.kind}): not relayed; AEW does not know which "
                                  "variable OpenCode reads its key from")
            else:
                self.keys[entry.integration] = entry.secret
                self.lines.append(f"{entry.integration} ({entry.kind}): relayed")
        # the provider variables AEW knows that are set in the operator's environment and not fed: names only
        unfed = sorted({v: p for p, v in netns.PROVIDER_KEY_ENV.items()
                        if v not in self.fed and agentenv.lookup(base, v)}.items())
        self.unfed = [v for v, p in unfed if v in by_variable]
        self.unserved = [(v, p) for v, p in unfed if v not in by_variable]
        self.mcp, self.unread = operator_mcp_servers(base)
        self.preferences, self.plugins, self.unread_preferences = operator_preferences(base)

    def announce(self, out: Any) -> None:
        """The session's start lines: names only, never a value."""
        logins = "; ".join(self.lines) or (f"none ({self.no_logins})" if self.no_logins else "none")
        out.write(f"aew opencode: contained Lead (STG-05 CS-4). Your OpenCode logins: {logins}.\n")
        for name, provider in self.fed.items():
            out.write(f"aew opencode: --provider-env {name} feeds the {provider} relay on the host; the Lead's shell "
                      "sees only a placeholder.\n")
        if self.unfed:
            out.write(f"aew opencode: {', '.join(self.unfed)} {'is' if len(self.unfed) == 1 else 'are'} set in your "
                      "environment and not given to the Lead; `aew opencode --provider-env NAME` feeds one to its "
                      "provider's relay on the host.\n")
        for name, provider in self.unserved:
            out.write(f"aew opencode: {name} is set in your environment: {_not_served(provider)}.\n")
        if not self.keys and not self.refreshing:
            out.write("aew opencode: no provider is relayed to the Lead, so only OpenCode's free models work. Log in "
                      "with your own OpenCode at your own terminal, outside AEW (`opencode auth login`), or feed a key "
                      "with `--provider-env NAME`; then start `aew opencode` again.\n")
        for entry in self.refreshing.values():  # addendum 2, ruling 1: it warns, and blocks nothing
            hours = (entry.expires / 1000 - time.time()) / 3600 if entry.expires is not None else 0.0
            if hours <= 0:
                out.write(f"aew opencode: your stored {entry.integration} login has expired. Run {REFRESH_STEP}.\n")
            elif hours <= self.warning_h:
                out.write(f"aew opencode: your stored {entry.integration} login expires in "
                          f"{_left(entry).removesuffix(' left')} (named when {self.warning_h} h or less is left: "
                          f"containment.lead.login_warning_h). {RENEW_STEP.format(provider=entry.integration)}\n")
        if self.mcp:
            out.write(f"aew opencode: your OpenCode configuration is not loaded in the contained Lead; its MCP servers "
                      f"are left out: {', '.join(self.mcp)}.\n")
        if self.unread:
            out.write(f"aew opencode: could not read {', '.join(self.unread)} for its MCP servers' names.\n")
        if self.preferences is not None:
            out.write("aew opencode: your TUI preferences come from your own OpenCode at each start; one you change in "
                      "the Lead lasts this session only"
                      + (f"; its TUI plugins are left out: {', '.join(self.plugins)}" if self.plugins else "") + ".\n")
        if self.unread_preferences:
            out.write(f"aew opencode: could not read your TUI preferences, {self.unread_preferences}: the Lead uses "
                      "OpenCode's defaults.\n")

    def __call__(self, bridge_dir: str | None, child_env: dict[str, str]) -> lead_broker.Harness:
        from aew.harness import containment
        from aew.harness.containment import egress, netns

        engine = self.engine
        self.stages.mark("seat")
        run_dir = runlog.run_dir(engine.aew_root, f"lead-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
                                                  f"{secrets.token_hex(3)}")
        run_dir.mkdir(parents=True)
        state = engine.aew_root / LEAD_DIR
        policy, _ = engine.execution_policy()
        project = str(engine.repo_root)
        layout, label = containment.establish(
            role="lead", scope="project", workspace=project, run_dir=run_dir, scratch=str(run_dir / "scratch"),
            bridge_dir=bridge_dir, policy=policy, project=project, bridge=child_env.get(lead_broker.ENV_ENDPOINT),
            egress_policy=egress.AnyPublic(), state_dir=str(state), relayed_terminal={"forbid": self.terminal})
        self.stages.mark("sandbox")
        label["session"] = run_dir.name
        label["start_s"] = self.stages.seconds  # the stages to come are added in place, before the label is recorded
        if layout is None:  # allowed weaker by the policy: the TUI runs as it does elsewhere, labelled so
            sys.stderr.write(f"aew opencode: the Lead runs NOT contained ({label['filesystem']}): "
                             f"{label.get('weaker_because')}\n")
            self._record(run_dir, label)
            env = {**child_env, **{n: str(agentenv.lookup(self.base, n)) for n in self.provider_env}}
            return lead_broker.Harness(argv=self.argv, env=env, relay=False, label=label, close=lambda: None)
        network: netns.RunNetwork | None = None
        try:
            if layout.private_network:
                network = netns.RunNetwork.start_lead(
                    layout, keys=self.keys, provider_env=self.provider_env, policy=policy, env=self.base,
                    refreshing={p: StoredLogin(p, self.base) for p in self.refreshing})
                label["network"].update(network.describe())
                self.stages.mark("network")
            config = projection.lead_config(self.guide, contained=label,
                                            relays=network.lead_bases() if network else None)
            inside = self._inside(child_env, layout, run_dir, state, config, network)
            leaked = network.leaks(json.dumps(inside), json.dumps(config)) if network else []
            if leaked:  # F28 §3.6, row 6: names only
                raise ContainmentUnavailable(f"a provider key would be inside the Lead's sandbox: {', '.join(leaked)}",
                                             reason="credential_inside")
            if network is not None and network.login_sentinels:
                try:
                    self._seed_logins(layout, inside, project, state, network.login_sentinels)
                except (OSError, subprocess.SubprocessError, sqlite3.Error) as exc:  # the Lead goes on without them
                    sys.stderr.write(f"aew opencode: {', '.join(sorted(network.login_sentinels))} could not be given "
                                     f"to the contained Lead ({type(exc).__name__}): the Lead cannot use "
                                     f"{'it' if len(network.login_sentinels) == 1 else 'them'} this session.\n")
                self.stages.mark("lead_logins")
            spec = network.spec() if network is not None and network.dir else {"in": [], "out": []}
            argv = containment.bwrap_argv(layout, netns.shim_argv({**spec, "ctty": True}, self.argv), cwd=project)
        except BaseException:
            self._retire(run_dir, layout, network)
            raise
        self._record(run_dir, label)
        return lead_broker.Harness(argv=argv, env=inside, relay=True, label=label,
                                   close=lambda: self._retire(run_dir, layout, network))

    def _inside(self, child_env: Mapping[str, str], layout: Any, run_dir: Path, state: Path,
                config: dict[str, Any], network: Any) -> dict[str, str]:
        """The TUI's environment in the sandbox: the curated one without the operator's ``XDG_*`` or OpenCode
        configuration file, AEW's own XDG directories (configuration and runtime per session, so a preference
        changed inside lasts that session; data, state and cache per project, the state seeded once with the
        operator's recent models), the layout's (its private git), the contained projection, the operator's TUI
        preferences without their plugins, and the network's sentinels and proxies."""
        env = {k: v for k, v in child_env.items()
               if not k.upper().startswith("XDG_") and k.upper() != "OPENCODE_CONFIG"}
        env.update(layout.env)
        dirs = {"CONFIG": run_dir / "harness" / "xdg-config", "RUNTIME": run_dir / "harness" / "xdg-runtime",
                "DATA": state / "xdg-data", "STATE": state / "xdg-state", "CACHE": state / "xdg-cache"}
        created = not dirs["STATE"].exists()
        for kind, directory in dirs.items():
            directory.mkdir(parents=True, exist_ok=True)
            env[f"XDG_{kind}_HOME" if kind != "RUNTIME" else "XDG_RUNTIME_DIR"] = str(directory)
        os.chmod(dirs["RUNTIME"], 0o700)
        if created:
            self._seed_models(dirs["STATE"])
        env.update({"OPENCODE_CONFIG_CONTENT": json.dumps(config, sort_keys=True), CONTAINED_ENV: "1"})
        if self.preferences is not None:  # merged over the session's own cli.json by OpenCode (addendum 1, item 2)
            env["OPENCODE_CLI_CONFIG_CONTENT"] = json.dumps(self.preferences, sort_keys=True)
        return network.harness_env(env) if network is not None else env

    def _seed_models(self, state_home: Path) -> None:
        """The Lead's recent and favourite models, once, as its state is created: a copy of the operator's
        ``model.json`` (model ids: no credential and no prompt), when it is a small JSON object. Never the prompt
        history, which carries other projects' prompts (the designer's addendum 1, item 3)."""
        source = _operator_dir(self.base, "state") / "model.json"
        try:
            if not source.is_file() or source.stat().st_size > MODEL_SEED_MAX:
                return
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            target = state_home / "opencode" / "model.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(data), encoding="utf-8")

    def _seed_logins(self, layout: Any, inside: Mapping[str, str], project: str, state: Path,
                     sentinels: Mapping[str, str]) -> None:
        """The Lead's own login store gets a row for each refreshing login its relays serve: its access token the
        relay's sentinel, its expiry :data:`INSIDE_LOGIN_S` off and its metadata placeholders, so the TUI's own code
        uses the login as it would the operator's (the account header included, which the relay replaces) and never
        tries to refresh it. AEW's rows only (``cred_aew_<provider>``), written each session, since the sentinels
        are new each time; an AEW row whose login is gone goes. The first time, OpenCode makes the database itself,
        in the sandbox with no route out (``session list``), so its schema is always its own."""
        from aew.harness import containment

        db = state / "xdg-data" / "opencode" / login.DB
        if not db.is_file():
            subprocess.run(containment.bwrap_argv(layout, [*binary_command(), "session", "list"], cwd=project),
                           env=dict(inside), capture_output=True, timeout=SEED_TIMEOUT_S, stdin=subprocess.DEVNULL,
                           check=False)
        if not db.is_file():
            raise FileNotFoundError(f"OpenCode made no database at {db}")
        now = int(time.time() * 1000)
        con = sqlite3.connect(db, timeout=login.BUSY_TIMEOUT_S)
        try:
            with con:
                con.execute("DELETE FROM credential WHERE id LIKE 'cred_aew_%'")
                for provider, token in sorted(sentinels.items()):
                    entry = self.refreshing[provider]
                    meta = {k: "aew-relay-placeholder" for k in LOGIN_HEADERS.get(provider, {}).values()
                            if entry.metadata.get(k)}
                    value = {"type": "oauth", "methodID": entry.method, "refresh": "aew-relay-no-refresh",
                             "access": token, "expires": now + INSIDE_LOGIN_S * 1000, "metadata": meta}
                    con.execute("UPDATE credential SET active = 0 WHERE integration_id = ?", (provider,))
                    con.execute("INSERT INTO credential (id, integration_id, label, value, method_id, active, "
                                "time_created, time_updated) VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                                (f"cred_aew_{provider}", provider, "AEW relay", json.dumps(value), entry.method, now,
                                 now))
        finally:
            con.close()

    @staticmethod
    def _record(run_dir: Path, label: dict[str, Any]) -> None:
        """The session's label, beside its run directory's state, for what reads it (G3, #269)."""
        (run_dir / "label.json").write_text(json.dumps(label, indent=2, sort_keys=True, default=str) + "\n",
                                            encoding="utf-8")

    @staticmethod
    def _retire(run_dir: Path, layout: Any, network: Any) -> None:
        from aew.harness import containment

        if network is not None:
            network.close()
        elif layout is not None and layout.net_dir:
            shutil.rmtree(layout.net_dir, ignore_errors=True)
        containment.retire_private_git(run_dir)
