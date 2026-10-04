"""``aew doctor``: make absence and damage visible instead of silently degrading.

Each check reports PASS, WARN, FAIL or UNAVAILABLE with a concrete detail.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from aew import SPEC_SET, __version__

MIN_PYTHON = (3, 11)
MIN_GIT: tuple[int, int] = (2, 31)


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def environment_checks() -> list[dict[str, str]]:
    checks = []
    py = sys.version_info[:3]
    checks.append(
        _check(
            "python",
            "PASS" if py[:2] >= MIN_PYTHON else "FAIL",
            f"{platform.python_implementation()} {'.'.join(map(str, py))} (need >= {'.'.join(map(str, MIN_PYTHON))})",
        )
    )
    git = shutil.which("git")
    if git is None:
        checks.append(_check("git", "FAIL", "git executable not found on PATH"))
    else:
        out = subprocess.run([git, "--version"], capture_output=True, text=True).stdout.strip()
        match = re.search(r"(\d+)\.(\d+)", out)
        version: tuple[int, int] = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
        checks.append(
            _check(
                "git",
                "PASS" if version >= MIN_GIT else "FAIL",
                f"{out} (need >= {'.'.join(map(str, MIN_GIT))})",
            )
        )
    for module in ("yaml", "jsonschema"):
        try:
            __import__(module)
            checks.append(_check(f"module:{module}", "PASS", "importable"))
        except ImportError as exc:
            checks.append(_check(f"module:{module}", "FAIL", str(exc)))
    from aew.util import yaml_backend  # the step-7 speed-up depends on it (m3-performance.md P1; M3 audit A2)

    if yaml_backend() == "libyaml":
        checks.append(_check("yaml", "PASS", "libyaml: PyYAML's C parser and emitter read and write the control state"))
    else:
        checks.append(_check("yaml", "WARN", "pure-python: this PyYAML has no libyaml, so every command reads and "
                             "writes the control state several times slower on a large project; install a PyYAML "
                             "built with libyaml"))
    return checks


def run(cwd: str | None = None) -> dict[str, Any]:
    checks = environment_checks()
    project_checks: list[dict[str, str]] = []
    try:
        from aew.engine.api import Engine

        engine = Engine.discover(Path(cwd) if cwd else Path.cwd())
        project_checks = engine.doctor_checks()
    except ImportError:
        project_checks = []
    except Exception as exc:  # doctor must report, never crash
        code = getattr(exc, "code", type(exc).__name__)
        status = "UNAVAILABLE" if code == "PROJECT_NOT_FOUND" else "FAIL"
        project_checks = [_check("project", status, f"{code}: {exc}")]
    all_checks = checks + project_checks
    failed = sum(1 for c in all_checks if c["status"] == "FAIL")
    return {
        "ok": failed == 0,
        "aew_version": __version__,
        "spec_set": SPEC_SET,
        "checks": all_checks,
        "failures": failed,
    }


def render(report: dict[str, Any]) -> str:
    width = max(len(c["check"]) for c in report["checks"])
    lines = [f"aew {report['aew_version']} (spec set {report['spec_set']})"]
    for c in report["checks"]:
        lines.append(f"{c['check']:<{width}}  {c['status']:<11}  {c['detail']}")
    lines.append(f"doctor: {report['failures']} failure(s)")
    return "\n".join(lines)
