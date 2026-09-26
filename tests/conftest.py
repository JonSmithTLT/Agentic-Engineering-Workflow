from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@dataclass
class CLIResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def json(self) -> Any:
        return json.loads(self.stdout)

    @property
    def error(self) -> dict[str, Any]:
        return json.loads(self.stderr)["error"]


def run_aew(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None,
            input: str | None = None, timeout: float = 120) -> CLIResult:
    """Run the CLI in a separate process, exactly as a harness would."""
    full_env = dict(os.environ)
    full_env.pop("AEW_LEAD_TOKEN", None)
    full_env.pop("AEW_INVOCATION_TOKEN", None)
    full_env.pop("AEW_FAULT", None)
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, "-m", "aew", *args],
        cwd=cwd,
        env=full_env,
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return CLIResult(proc.returncode, proc.stdout, proc.stderr)


@pytest.fixture
def aew_cli():
    return run_aew
