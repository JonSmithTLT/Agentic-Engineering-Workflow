"""``aew opencode``: the Lead's OpenCode TUI as a Lead session (ADR-0009; M3 plan §2.6).

The TUI runs through ``aew lead session`` (:mod:`aew.harness.lead_broker`), so the Lead's model never
holds the Lead credential: Lead-authenticated ``aew`` commands reach this session's broker.

**The Lead model's shell environment is curated.** A V2 TUI that runs its own server (``--standalone``)
sends its own environment, minus the server password, as every session's shell environment, and its
private server inherits the same environment. So the environment given to the TUI is exactly what the
Lead's model and its shell commands can see: an allowlist (operating-system basics, ``XDG_*``), ``PATH``
with ``aew`` first, the broker's coordinates, and the Lead projection. It holds no AEW credential and, by
default, **no provider API key**. The Lead's model then authenticates with the credentials OpenCode stores
for the operator (``opencode auth login`` or the Desktop app). ``--provider-env NAME`` passes a key
explicitly, and the Lead's shell can then read it; the command says so.

The TUI otherwise runs in the operator's normal OpenCode environment (their providers, configuration and
skills). AEW writes nothing into it: the Lead projection is ``OPENCODE_CONFIG_CONTENT``, and project
configuration in the repository is not loaded (the Lead's context comes from ``aew resume``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

from aew.errors import HarnessIncompatible, UsageError
from aew.harness import agentenv, lead_broker
from aew.harness.contract import CREDENTIAL_RE
from aew.harness.opencode import capabilities, projection
from aew.harness.opencode.adapter import binary_command

PASSED_THROUGH = ("OPENCODE_CONFIG", "SHELL")  # the operator's own config file and shell choice


def tui_env(base: Mapping[str, str], *, provider_env: list[str]) -> dict[str, str]:
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    env = {k: v for k, v in base.items() if k.upper() in keep or k.upper().startswith("XDG_")
           or (sys.platform != "win32" and k.startswith("LC_")) or k.upper() in PASSED_THROUGH}
    aew_bin = os.path.dirname(sys.executable)
    path = [p for p in (base.get("PATH") or base.get("Path") or "").split(os.pathsep) if p]
    env["PATH"] = os.pathsep.join([aew_bin, *[p for p in path if os.path.normcase(p) != os.path.normcase(aew_bin)]])
    env["PYTHONUTF8"] = "1"
    for name in provider_env:
        if name.upper().startswith("AEW_"):
            raise UsageError(f"--provider-env {name}: AEW variables are never passed to a harness")
        value = base.get(name)
        if not value:
            raise UsageError(f"--provider-env {name}: it is not set in this environment")
        if CREDENTIAL_RE.search(value):
            raise UsageError(f"--provider-env {name}: it holds an AEW credential")
        env[name] = value
    env.update({"OPENCODE_CONFIG_CONTENT": json.dumps(projection.lead_config(), sort_keys=True),
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


def describe(engine: Any, *, provider_env: list[str], extra_args: list[str] | None = None) -> dict[str, Any]:
    """What `aew opencode` would run, without starting anything (no values of environment variables)."""
    env = tui_env(os.environ, provider_env=provider_env)
    try:
        argv: list[str] | str = command(engine, extra_args or [])
    except HarnessIncompatible as exc:
        argv = f"unavailable: {exc.message}"
    return {"command": argv, "config": projection.lead_config(),
            "env_names": sorted([*env, *lead_broker.ENV_NAMES]), "provider_env": provider_env,
            "notes": ["The TUI's own environment becomes every Lead session's shell environment (V2 --standalone).",
                      "No AEW credential and no provider key is in it unless passed with --provider-env."]}


def run(engine: Any, *, acquire: bool, session_label: str | None, keep_seat: bool, provider_env: list[str],
        extra_args: list[str], print_config: bool) -> dict[str, Any]:
    if print_config:
        return {"ok": True, **describe(engine, provider_env=provider_env, extra_args=extra_args)}
    version = check_version()
    env = tui_env(os.environ, provider_env=provider_env)
    if provider_env:
        sys.stderr.write(f"aew opencode: {', '.join(provider_env)} passed to the Lead's OpenCode; the Lead model's "
                         "shell commands can read it.\n")
    out = lead_broker.run_session(engine, command(engine, extra_args), acquire=acquire, session_label=session_label,
                                  keep_seat=keep_seat, env=env)
    return {**out, "opencode": version}
