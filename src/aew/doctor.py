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
                        ("modules", _modules), ("yaml", _yaml), ("primary-group", primary_group)):
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


def primary_gid() -> int | None:
    """The operator's primary group: their account's, or this process's own group when the uid has no account entry.
    None on Windows."""
    if sys.platform == "win32":  # pragma: windows-only
        return None
    import os  # pragma: posix-only
    import pwd

    try:
        return pwd.getpwuid(os.getuid()).pw_gid
    except KeyError:
        return os.getgid()


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
    try:
        user = pwd.getpwuid(os.getuid())
    except KeyError:  # a container's or a user namespace's uid, or a directory account while its directory is down
        return _check("primary-group", "WARN", f"your uid {os.getuid()} has no account entry on this host, so nobody "
                      f"can tell who else is in your group (gid {os.getgid()}); AEW's store is readable by that group")
    try:
        group = grp.getgrgid(user.pw_gid)
    except KeyError:
        return _check("primary-group", "WARN", f"your primary group (gid {user.pw_gid}) has no entry on this host, "
                      "so nobody can tell who else is in it; the store is readable by that group")
    accounts = pwd.getpwall()
    sharing = sorted(u.pw_name for u in accounts if u.pw_gid == user.pw_gid and u.pw_name != user.pw_name)
    remote, idle = directory_sources()
    return private_group_check(user.pw_name, group.gr_name, group.gr_mem, sharing, listed=len(accounts),
                               remote=remote, idle=idle)


# Name-service sources whose accounts are all on this host, so enumerating them lists every account they hold.
# `compat` is one unless the files hold NIS `+`/`-` lines, which bring in accounts this host does not list.
LOCAL_SOURCES = frozenset({"files", "compat", "systemd", "altfiles"})
# sssd's name-service responder: `sss` in nsswitch.conf serves nothing while it is absent (RL8's default authselect
# profile lists `sss` whether or not sssd runs; review of #230, m7).
SSS_NSS_PIPE = Path("/var/lib/sss/pipes/nss")


def directory_sources(nsswitch: Path = Path("/etc/nsswitch.conf"), *, sss_pipe: Path = SSS_NSS_PIPE,
                      etc: Path = Path("/etc")) -> tuple[list[str], list[str]]:
    """``(serving, idle)``: the name-service sources for accounts and groups other than this host's own files
    (``sss``, ``ldap``, ``nis``, ``winbind`` ...), whose accounts need not all be listed when enumerated, so a group
    check cannot see them all; and those configured but not serving now (``sss`` without its responder)."""
    try:
        text = nsswitch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], []
    found: list[str] = []
    for line in text.splitlines():
        db, _, rest = line.split("#", 1)[0].partition(":")
        if db.strip() in ("passwd", "group"):
            for word in rest.split():
                if word == "compat" and _nis_lines(etc):
                    word = "compat (NIS lines in /etc/passwd or /etc/group)"
                elif word.startswith("[") or word in LOCAL_SOURCES:
                    continue
                if word not in found:
                    found.append(word)
    idle = [w for w in found if w == "sss" and not sss_pipe.exists()]
    return [w for w in found if w not in idle], idle


def _nis_lines(etc: Path) -> bool:
    """Whether ``passwd`` or ``group`` under ``etc`` has a NIS ``+``/``-`` line, which `compat` resolves remotely."""
    for name in ("passwd", "group"):
        try:
            lines = (etc / name).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if any(line.startswith(("+", "-")) for line in lines):
            return True
    return False


def private_group_check(user: str, group: str, members: list[str], sharing: list[str], *, listed: int,
                        remote: list[str], idle: list[str] | tuple[str, ...] = ()) -> dict[str, str]:
    """``primary-group``: a user-private group is named for ``user``, has no member but ``user``, and is no other
    account's primary group (``sharing``, among the ``listed`` accounts this host lists). Accounts from a directory
    service (``remote``) may not all be listed, so then a group that looks private is reported as not confirmed. A
    source configured but not serving (``idle``) is named, and does not stop a PASS. The check is of the group, not of
    the store's files: ``store-group`` checks that their group is this one."""
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
    note = (f" ({', '.join(idle)} is configured for accounts but not serving now; if it starts, this check cannot "
            "confirm the group any more)") if idle else ""
    return _check("primary-group", "PASS", f"{seen}: it is user-private{note}. Store files with this group are "
                  "readable by you alone (`store-group` checks their group)")


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
