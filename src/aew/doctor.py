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


# Windows stays outside the enforced vertical gate, and UNQUALIFIED, until its containment exists and passes its
# qualification; that state is never silently absent (operator decision 2026-10-11). The gate's verdicts and the docs
# begin the same way.
WINDOWS_UNQUALIFIED = "Windows: UNQUALIFIED (excluded from the enforced gate)"
WINDOWS_WHY = ("runs here have workdir separation only: no OS filesystem containment, no isolation between runs, and "
               "an uncontained Lead, so an agent's shell can read and write whatever your account can. Windows "
               "qualifies only once a Low-integrity containment backend for the Lead and the workers, with "
               "run-to-run isolation and a withheld set of secrets no run may read, passes its qualification "
               "self-tests. Until then, evaluate on scratch repositories here; real-repository work runs contained on "
               "Linux")


def platform_qualification(platform_name: str | None = None) -> dict[str, str] | None:
    """The Windows line: stated on Windows, absent elsewhere (Linux's containment is the ``containment`` check's)."""
    if (platform_name or sys.platform) != "win32":
        return None
    return _check("platform", "WARN", f"{WINDOWS_UNQUALIFIED}: {WINDOWS_WHY}")


def environment_checks() -> list[dict[str, str]]:
    """The host's checks, each run through one guard: a check that raises is reported as FAIL with what it raised,
    and the other checks still run (doctor reports, never crashes; review of #230, m5)."""
    checks: list[dict[str, str]] = []
    for name, check in (("platform", platform_qualification), ("python", _python), ("git", _git),
                        ("modules", _modules), ("yaml", _yaml), ("capability", _capabilities)):
        try:
            found = check()
        except Exception as exc:
            found = _check(name, "FAIL", f"the check itself failed ({type(exc).__name__}: {exc}); the other checks "
                           "still ran")
        checks += [] if found is None else found if isinstance(found, list) else [found]
    return checks


def _python() -> dict[str, str]:
    py = sys.version_info[:3]
    return _check("python", "PASS" if py[:2] >= MIN_PYTHON else "FAIL",
                  f"{platform.python_implementation()} {'.'.join(map(str, py))} (need >= "
                  f"{'.'.join(map(str, MIN_PYTHON))})")


def _git() -> dict[str, str]:
    git = shutil.which("git")
    if git is None:
        return _check("git", "FAIL", "git executable not found on PATH")
    # No console window on Windows (CREATE_NO_WINDOW; 0, which every platform accepts, where there is none).
    out = subprocess.run([git, "--version"], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    match = re.search(r"(\d+)\.(\d+)", out)
    version: tuple[int, int] = (int(match.group(1)), int(match.group(2))) if match else (0, 0)
    return _check("git", "PASS" if version >= MIN_GIT else "FAIL", f"{out} (need >= {'.'.join(map(str, MIN_GIT))})")


def _modules() -> list[dict[str, str]]:
    out = []
    for module in ("yaml", "jsonschema"):
        try:
            __import__(module)
            out.append(_check(f"module:{module}", "PASS", "importable"))
        except ImportError as exc:
            out.append(_check(f"module:{module}", "FAIL", str(exc)))
    return out


def _yaml() -> dict[str, str]:
    from aew.util import yaml_backend  # the step-7 speed-up depends on it (m3-performance.md P1; M3 audit A2)

    if yaml_backend() == "libyaml":
        return _check("yaml", "PASS", "libyaml: PyYAML's C parser and emitter read and write the control state")
    return _check("yaml", "WARN", "pure-python: this PyYAML has no libyaml, so every command reads and writes the "
                  "control state several times slower on a large project; install a PyYAML built with libyaml")


def _capabilities() -> list[dict[str, str]]:
    """One line per capability of the register (STG-15, CAP-1), read from the status ``aew capability list`` shows
    (S01-21): the host's, so shown outside a project too. WARN, never FAIL, where one is not usable: no provider is
    required for AEW to run (CAPR-12)."""
    from aew.capability import ops

    return [_check(name, status, detail) for name, status, detail in ops.doctor_checks()]


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
