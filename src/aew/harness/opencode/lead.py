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
sandbox holds only a sentinel. ``--provider-env NAME`` feeds NAME's provider relay in the same way.

**Elsewhere** (Windows) the TUI runs in the operator's normal OpenCode environment (their providers,
configuration and skills), labelled not contained. The Lead's model then authenticates with the credentials
OpenCode stores for the operator, and ``--provider-env NAME`` passes a key explicitly, which the Lead's shell
can then read; the command says so.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
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

PASSED_THROUGH = ("OPENCODE_CONFIG", "SHELL")  # the operator's own config file and shell choice
LEAD_DIR = "local/harness/lead"  # under the AEW root: the contained Lead's OpenCode state, per project (addendum 1)
# Set inside the contained Lead's sandbox: AEW's CLI there is a non-writer (``process_kind``, its owner), and a write
# that meets the read-only store says why (``cli.main``). Never authority.
CONTAINED_ENV = process_kind.LEAD_CONTAINED_ENV
# The operator's OpenCode configuration files, in its configuration directory (OpenCode 2.0.18).
CONFIG_FILES = ("config.json", "opencode.json", "opencode.jsonc")


def guide_of(engine: Any) -> str:
    """The project's Lead guide (F16), or nothing when its policy cannot be read (the Lead then sees why elsewhere)."""
    try:
        return str(engine.lead_guide())
    except AEWError:
        return ""


def tui_env(base: Mapping[str, str], *, provider_env: list[str], guide: str = "") -> dict[str, str]:
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    env = {k: v for k, v in base.items() if k.upper() in keep or k.upper().startswith("XDG_")
           or (sys.platform != "win32" and k.startswith("LC_")) or k.upper() in PASSED_THROUGH}
    aew_bin = os.path.dirname(sys.executable)
    path = [p for p in (base.get("PATH") or base.get("Path") or "").split(os.pathsep) if p]
    env["PATH"] = os.pathsep.join([aew_bin, *[p for p in path if os.path.normcase(p) != os.path.normcase(aew_bin)]])
    env["PYTHONUTF8"] = "1"
    for name, why in agentenv.provider_env_problems(provider_env, base):  # the one rule (doctor and launch share it)
        raise UsageError(f"--provider-env {name}: {why}", variable=name)
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
    version = check_version()
    guide = guide_of(engine)
    argv = command(engine, extra_args)
    if contained_here():
        # Everything that can refuse does so before a seat is taken (an acquired seat whose credential is lost
        # would stay held).
        lead = ContainedLead(engine, argv=argv, provider_env=provider_env, guide=guide, base=os.environ)
        lead.announce(sys.stderr)
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


def operator_mcp_servers(base: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """``(names, unread)``: the MCP servers the operator's own OpenCode configuration names, which the contained Lead
    does not load, and the configuration files that could not be read. Names only."""
    home = base.get("HOME") or os.path.expanduser("~")
    directory = Path(base.get("XDG_CONFIG_HOME") or Path(home) / ".config") / "opencode"
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


class ContainedLead:
    """The contained Lead's session (STG-05 CS-4), made before the seat is taken: the operator's terminal, the
    providers to relay (their keys in this process's memory only), and what the session leaves out. Called by the
    broker once it serves (``lead_broker.run_session``'s ``contained``), it builds the sandbox and returns what runs.

    Raises ``UsageError`` before anything starts: without a terminal (the TUI runs on a relayed one), or for a
    ``--provider-env`` variable that cannot be passed or that no relayed provider reads."""

    def __init__(self, engine: Any, *, argv: list[str], provider_env: list[str], guide: str,
                 base: Mapping[str, str]) -> None:
        from aew.harness.containment import netns

        if not os.isatty(0):
            raise UsageError("the contained Lead's TUI runs on a terminal AEW relays (STG-05 CS-4): run `aew opencode` "
                             "at a terminal")
        for name, why in agentenv.provider_env_problems(provider_env, base):
            raise UsageError(f"--provider-env {name}: {why}", variable=name)
        self.terminal = _launching_terminal()
        self.engine, self.argv, self.guide, self.base = engine, list(argv), guide, base
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
        for entry in self.logins:
            if entry.integration in self.keys:
                self.lines.append(f"{entry.integration} ({entry.kind}): fed by --provider-env instead")
            elif entry.integration in netns.CATALOG_ADDRESSED:
                self.lines.append(f"{entry.integration} ({entry.kind}): not relayed; OpenCode's catalog gives each "
                                  f"{entry.integration}/* model an address of its own, so its key cannot reach a "
                                  "relay. Its free models still work, through the egress proxy")
            elif entry.integration not in netns.PROVIDER_KEY_ENV:
                self.lines.append(f"{entry.integration} ({entry.kind}): not relayed; AEW does not know which "
                                  "variable OpenCode reads its key from")
            elif entry.kind != "key":
                self.lines.append(f"{entry.integration} ({entry.kind}): not relayed; a refreshing login is not "
                                  "served yet")
            else:
                self.keys[entry.integration] = entry.secret
                self.lines.append(f"{entry.integration} ({entry.kind}): relayed")
        self.mcp, self.unread = operator_mcp_servers(base)

    def announce(self, out: Any) -> None:
        """The session's start lines: names only, never a value."""
        logins = "; ".join(self.lines) or (f"none ({self.no_logins})" if self.no_logins else "none")
        out.write(f"aew opencode: contained Lead (STG-05 CS-4). Your OpenCode logins: {logins}.\n")
        for name, provider in self.fed.items():
            out.write(f"aew opencode: --provider-env {name} feeds the {provider} relay on the host; the Lead's shell "
                      "sees only a placeholder.\n")
        if self.mcp:
            out.write(f"aew opencode: your OpenCode configuration is not loaded in the contained Lead; its MCP servers "
                      f"are left out: {', '.join(self.mcp)}.\n")
        if self.unread:
            out.write(f"aew opencode: could not read {', '.join(self.unread)} for its MCP servers' names.\n")

    def __call__(self, bridge_dir: str | None, child_env: dict[str, str]) -> lead_broker.Harness:
        from aew.harness import containment
        from aew.harness.containment import egress, netns

        engine = self.engine
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
        label["session"] = run_dir.name
        if layout is None:  # allowed weaker by the policy: the TUI runs as it does elsewhere, labelled so
            sys.stderr.write(f"aew opencode: the Lead runs NOT contained ({label['filesystem']}): "
                             f"{label.get('weaker_because')}\n")
            self._record(run_dir, label)
            env = {**child_env, **{n: str(agentenv.lookup(self.base, n)) for n in self.provider_env}}
            return lead_broker.Harness(argv=self.argv, env=env, relay=False, label=label, close=lambda: None)
        network: netns.RunNetwork | None = None
        try:
            if layout.private_network:
                network = netns.RunNetwork.start_lead(layout, keys=self.keys, provider_env=self.provider_env,
                                                      policy=policy, env=self.base)
                label["network"].update(network.describe())
            config = projection.lead_config(self.guide, contained=label,
                                            relays=network.lead_bases() if network else None)
            inside = self._inside(child_env, layout, run_dir, state, config, network)
            leaked = network.leaks(json.dumps(inside), json.dumps(config)) if network else []
            if leaked:  # F28 §3.6, row 6: names only
                raise ContainmentUnavailable(f"a provider key would be inside the Lead's sandbox: {', '.join(leaked)}",
                                             reason="credential_inside")
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
        changed inside lasts that session; data, state and cache per project), the layout's (its private git), the
        contained projection, and the network's sentinels and proxies."""
        env = {k: v for k, v in child_env.items()
               if not k.upper().startswith("XDG_") and k.upper() != "OPENCODE_CONFIG"}
        env.update(layout.env)
        dirs = {"CONFIG": run_dir / "harness" / "xdg-config", "RUNTIME": run_dir / "harness" / "xdg-runtime",
                "DATA": state / "xdg-data", "STATE": state / "xdg-state", "CACHE": state / "xdg-cache"}
        for kind, directory in dirs.items():
            directory.mkdir(parents=True, exist_ok=True)
            env[f"XDG_{kind}_HOME" if kind != "RUNTIME" else "XDG_RUNTIME_DIR"] = str(directory)
        os.chmod(dirs["RUNTIME"], 0o700)
        env.update({"OPENCODE_CONFIG_CONTENT": json.dumps(config, sort_keys=True), CONTAINED_ENV: "1"})
        return network.harness_env(env) if network is not None else env

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
