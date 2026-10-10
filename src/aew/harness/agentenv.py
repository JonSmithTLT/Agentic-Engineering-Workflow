"""The environment of every model-controlled process (ADR-0009).

Built from an **allowlist**: operating-system basics, ``PATH`` (with the running ``aew`` first), the run's
bridge coordinates and private scratch directory, and what a contained run's sandbox needs set (its private git
index and object store, a private ``TMPDIR`` and caches; M4-B). It never contains an AEW credential, a provider
secret, the harness server's password, the Lead's environment, or anything else the Lead's shell happened to hold.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

from aew.harness import bridge

WINDOWS_KEEP = frozenset({
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMW6432",
    "COMMONPROGRAMFILES", "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432", "SYSTEMDRIVE", "PUBLIC",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER", "OS", "USERNAME", "USERDOMAIN",
    "COMPUTERNAME",
})
POSIX_KEEP = frozenset({"HOME", "USER", "LOGNAME", "LANG", "LANGUAGE", "TERM", "SHELL", "TMPDIR", "TZ"})
SCRATCH = "AEW_SCRATCH"
AGENT_VARS = ("AEW_INVOCATION", "AEW_RUN", "AEW_WORK_UNIT", bridge.ENV_ENDPOINT, bridge.ENV_KEY, SCRATCH)
PROXY_VARS = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"})
# Bun (OpenCode 2.0.18) and Python's urllib match an IPv6 host in its bracketed URL form, so both spellings
# (PR #159 review, finding 1).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")


def bypass_proxy_for_loopback(env: dict[str, str]) -> None:
    """A proxy variable the operator passes to a harness (``provider_env``, ``--provider-env``) is for its provider
    traffic; its loopback traffic (the run's own server, a loopback-hosted provider, the Lead TUI's link to its server)
    must never go through the proxy. So when one is set, the loopback hosts join ``NO_PROXY``, keeping any entries the
    operator passed. Without a proxy variable the environment is unchanged, and so is an operator's ``NO_PROXY=*``:
    it already bypasses everything, and urllib honours ``*`` only as the whole value (PR #159 review, finding 2)."""
    if not any(k.upper() in PROXY_VARS and v for k, v in env.items()):
        return
    names = [k for k in env if k.upper() == "NO_PROXY"]
    current = [h.strip() for name in names for h in env[name].split(",") if h.strip()]
    if "*" in current:
        return
    value = ",".join(dict.fromkeys([*current, *LOOPBACK_HOSTS]))
    for name in names:
        del env[name]
    # Windows names are case-insensitive, so one entry; POSIX tools read either spelling (curl only the lower one).
    for name in ("NO_PROXY",) if sys.platform == "win32" else ("NO_PROXY", "no_proxy"):
        env[name] = value


def build(base: Mapping[str, str], *, endpoint: str, key_hex: str, invocation: str, run: str,
          work_unit: str, scratch: str = "", contained: Mapping[str, str] | None = None) -> dict[str, str]:
    keep = WINDOWS_KEEP if sys.platform == "win32" else POSIX_KEEP
    env = {k: v for k, v in base.items()
           if k.upper() in keep or (sys.platform != "win32" and k.startswith("LC_"))}
    aew_bin = os.path.dirname(sys.executable)
    path = [p for p in (base.get("PATH") or base.get("Path") or "").split(os.pathsep) if p]
    env["PATH"] = os.pathsep.join([aew_bin, *[p for p in path if os.path.normcase(p) != os.path.normcase(aew_bin)]])
    env["PYTHONUTF8"] = "1"
    env.update({"AEW_INVOCATION": invocation, "AEW_RUN": run, "AEW_WORK_UNIT": work_unit,
                bridge.ENV_ENDPOINT: endpoint, bridge.ENV_KEY: key_hex})
    if scratch:
        env[SCRATCH] = scratch
    env.update(contained or {})
    return env
