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
    checks = []
    windows = platform_qualification()
    if windows is not None:
        checks.append(windows)
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
        # No console window on Windows (CREATE_NO_WINDOW; 0, which every platform accepts, where there is none).
        out = subprocess.run([git, "--version"], capture_output=True, text=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
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
    group = primary_group()
    if group is not None:
        checks.append(group)
    return checks


def primary_group() -> dict[str, str] | None:
    """Whether the operator's primary group is user-private (STG-05 CB-08): the store is group-readable, so its group
    must hold the operator alone. None on Windows, which has no such groups. AEW never changes or creates a group."""
    if sys.platform == "win32":  # pragma: windows-only
        return None
    import os  # pragma: posix-only

    try:
        import grp
        import pwd
    except ImportError:  # a test that claims a POSIX platform on Windows: there are still no groups to check
        return None
    user = pwd.getpwuid(os.getuid())
    try:
        group = grp.getgrgid(user.pw_gid)
    except KeyError:
        return _check("primary-group", "WARN", f"your primary group (gid {user.pw_gid}) has no entry on this host, "
                      "so nobody can tell who else is in it; the store is readable by that group")
    accounts = pwd.getpwall()
    sharing = sorted(u.pw_name for u in accounts if u.pw_gid == user.pw_gid and u.pw_name != user.pw_name)
    return private_group_check(user.pw_name, group.gr_name, group.gr_mem, sharing, listed=len(accounts),
                               remote=directory_sources())


# Name-service sources whose accounts are all on this host, so enumerating them lists every account they hold.
LOCAL_SOURCES = frozenset({"files", "compat", "systemd", "altfiles"})


def directory_sources(nsswitch: Path = Path("/etc/nsswitch.conf")) -> list[str]:
    """The name-service sources for accounts and groups other than this host's own files (``sss``, ``ldap``, ``nis``,
    ``winbind`` ...): their accounts need not all be listed when enumerated, so a group check cannot see them all."""
    try:
        text = nsswitch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found: list[str] = []
    for line in text.splitlines():
        db, _, rest = line.split("#", 1)[0].partition(":")
        if db.strip() in ("passwd", "group"):
            for word in rest.split():
                if not word.startswith("[") and word not in LOCAL_SOURCES and word not in found:
                    found.append(word)
    return found


def private_group_check(user: str, group: str, members: list[str], sharing: list[str], *, listed: int,
                        remote: list[str]) -> dict[str, str]:
    """``primary-group``: a user-private group is named for ``user``, has no member but ``user``, and is no other
    account's primary group (``sharing``, among the ``listed`` accounts this host lists). Accounts from a directory
    service (``remote``) may not all be listed, so then a group that looks private is reported as not confirmed."""
    problems = []
    if group != user:
        problems.append(f"it is named {group!r}, not for you")
    others = sorted(set(members) - {user})
    if others:
        problems.append(f"it has other members ({', '.join(others)})")
    if sharing:
        problems.append(f"it is also the primary group of {', '.join(sharing)}")
    if problems:
        return _check("primary-group", "WARN", f"your primary group {group!r} is not user-private: "
                      f"{'; '.join(problems)}. AEW's store is group-readable, so they can read it too, and a reader "
                      "that relies on the group holding only you (the work-item fact issuer) does not qualify on this "
                      "host. AEW changes no group: your administrator can give your account a user-private primary "
                      "group")
    seen = (f"your primary group {group!r} is named for you and has no other member among the {listed} accounts "
            "this host lists")
    if remote:
        return _check("primary-group", "WARN", f"{seen}, but this host also takes accounts and groups from "
                      f"{', '.join(remote)}, which need not all be listed, so AEW cannot confirm that only you are in "
                      "it (AEW's store is group-readable). Your administrator can confirm it")
    return _check("primary-group", "PASS", f"{seen}: it is user-private, and AEW's store is group-readable to you "
                  "alone")


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
