"""Project-defined deterministic check runner (WC §11.1-11.2, §16.14).

Checks are the cheapest reliable evidence producers: build, focused tests,
linters. The command comes from project policy, never from the agent. The
placeholder ``{python}`` expands to the running interpreter.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aew.errors import GateUnsatisfied, NotFound

BUILTIN = {"guardrails"}
DEFAULT_TIMEOUT_S = 900


def definition_digest(cfg: dict[str, Any], *, guardrails: dict[str, Any] | None = None) -> str:
    """What a result of this check proves: the definition that ran (independent audit I1). For a configured check,
    its command, working directory and timeout (a description is not part of it); for the builtin guardrails check,
    the guardrails policy it evaluated."""
    if cfg.get("builtin"):
        basis: dict[str, Any] = {"builtin": "guardrails", "policy": guardrails}
    else:
        basis = {"command": cfg.get("command"), "cwd": cfg.get("cwd", "."),
                 "timeout_s": cfg.get("timeout_s", DEFAULT_TIMEOUT_S)}
    return hashlib.sha256(json.dumps(basis, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def current_definitions(checks_policy: dict[str, Any], guardrails: dict[str, Any]) -> dict[str, str]:
    """Each check id's definition digest under the policy now in force. An unconfigured check has none."""
    out = {"guardrails": definition_digest({"builtin": True}, guardrails=guardrails)}
    for check_id, cfg in (checks_policy.get("checks") or {}).items():
        if cfg.get("configured") and cfg.get("command"):
            out[check_id] = definition_digest(cfg)
    return out


def proves_current_definition(evidence: dict[str, Any], definitions: dict[str, str]) -> bool:
    """A check result counts only for the check as it is defined now (decision (a), independent audit I1). A result
    recorded without a definition, or for a check no longer configured, proves nothing about the current one."""
    check = evidence.get("check") or {}
    current = definitions.get(str(check.get("check_id")))
    return current is not None and check.get("definition_sha256") == current


def resolve(checks_policy: dict[str, Any], check_id: str) -> dict[str, Any]:
    if check_id in BUILTIN:
        return {"builtin": True}
    cfg = checks_policy["checks"].get(check_id)
    if cfg is None:
        raise NotFound(f"no check {check_id!r} in policy/checks.yaml")
    if not cfg.get("configured") or not cfg.get("command"):
        raise GateUnsatisfied(
            f"check {check_id!r} is not configured; configure policy/checks.yaml rather than guessing a command")
    return cfg


def run(cfg: dict[str, Any], workspace: Path, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run a check in its own process tree. Every process it started has ended when this returns, so the caller's
    after-snapshot describes everything the check did (independent audit I2)."""
    from aew.harness.procs import ProcessTree

    command = [part.replace("{python}", sys.executable) for part in cfg["command"]]
    cwd = (workspace / cfg.get("cwd", ".")).resolve()
    timeout = cfg.get("timeout_s", DEFAULT_TIMEOUT_S)
    started = time.monotonic()
    tree = ProcessTree()
    exit_code: int | None = None
    try:
        try:
            proc = tree.spawn(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              stdin=subprocess.DEVNULL, env=env, text=True)
        except OSError as exc:
            log = f"$ {' '.join(command)}\nfailed to start: {exc}"
        else:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                exit_code = proc.returncode
                log = f"$ {' '.join(command)}\n(cwd {cwd})\n\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
            except subprocess.TimeoutExpired:
                tree.kill()
                stdout, stderr = proc.communicate()
                log = f"$ {' '.join(command)}\nTIMEOUT after {timeout}s\n{stdout or ''}\n{stderr or ''}"
    finally:
        left = tree.close()
    if left and exit_code is not None:
        log += "\n--- processes the check left running were ended when it returned ---\n"
    return {"exit_code": exit_code, "duration_s": round(time.monotonic() - started, 3), "log": log,
            "command": command}
