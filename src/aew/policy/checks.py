"""Project-defined deterministic check runner (WC §11.1-11.2, §16.14).

Checks are the cheapest reliable evidence producers: build, focused tests,
linters. The command comes from project policy, never from the agent. The
placeholder ``{python}`` expands to the running interpreter.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from aew.errors import GateUnsatisfied, NotFound

BUILTIN = {"guardrails"}


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
    command = [part.replace("{python}", sys.executable) for part in cfg["command"]]
    cwd = (workspace / cfg.get("cwd", ".")).resolve()
    started = time.monotonic()
    try:
        proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              timeout=cfg.get("timeout_s", 900), stdin=subprocess.DEVNULL, env=env)
        exit_code: int | None = proc.returncode
        log = f"$ {' '.join(command)}\n(cwd {cwd})\n\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        log = f"$ {' '.join(command)}\nTIMEOUT after {exc.timeout}s\n{exc.stdout or ''}\n{exc.stderr or ''}"
    except OSError as exc:
        exit_code = None
        log = f"$ {' '.join(command)}\nfailed to start: {exc}"
    return {"exit_code": exit_code, "duration_s": round(time.monotonic() - started, 3), "log": log,
            "command": command}
