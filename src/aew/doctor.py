"""``aew doctor``: make absence and damage visible instead of silently degrading.

Each check reports PASS, WARN, FAIL or UNAVAILABLE with a concrete detail.
"""

from __future__ import annotations

import platform
import re
import shutil
import stat
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
                        ("modules", _modules), ("yaml", _yaml)):
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


def store_checks(view: Any, problems: list[tuple[str, int, int]] | None,
                 refused: list[tuple[str, str]] | None) -> list[dict[str, str]]:
    """The store's group, its running writers, its paths, and whether WIS can be qualified here as far as the store
    goes (STG-05 CB-08; WIS-01a and D-CS1-11 as A-36 amends them). ``view`` is ``ControlStore.group_view()``, and
    ``problems`` and ``refused`` are the store's ``path_problems`` and ``walk_refusals``; doctor itself is a store
    writer, so it is one of the writers it reports on. For WIS-Q02 only PASS counts as met (D-CS1-5)."""
    from aew.engine import store_group as sg

    found, target, host = view.answer, view.target, view.host
    record = _record_text(host, view.error)
    modes = f"{target.file_mode:04o} files and {target.dir_mode:04o} directories"
    checks: list[dict[str, str]] = []
    if found.gid is not None:
        name = _group_name(host, found.gid)
        kind = ("your user-private primary group: named for you, with no member, and its ID held by no one else in "
                "any source this host resolves" if found.kind == sg.USER_PRIVATE else
                "the local AEW group root's group record names, with you as its only member and its ID held by no one "
                "else in any source this host resolves")
        checks.append(_check("store-group", "PASS", f"the store's group is {name} (gid {found.gid}), {kind} "
                             f"(WIS-01a). {record}"))
    else:
        checks.append(_check("store-group", "WARN", f"no group is private to you on this host: WIS-01a "
                             f"{_parts(found)} fails ({_why(found, host, view.error)}). The "
                             "store is owner-only (0600 files, 0700 directories) and AEW works as before, but the "
                             f"work-item fact issuer cannot read it, so WIS cannot be qualified here. {record} "
                             f"{_remedy(found, host)}"))
    lacking = view.lacking()
    notes = [*view.problems, *([view.register_problem] if view.register_problem else [])]
    tail = f" ({'; '.join(notes)})" if notes else ""
    if found.gid is None:
        checks.append(_check("store-writers", "PASS", f"no running store writer needs a group: the store is owner-only "
                             f"({len(view.others)} running besides this one){tail}"))
    elif lacking:
        checks.append(_check("store-writers", "WARN", f"these running store writers lack "
                             f"{_group_name(host, found.gid)} (gid {found.gid}): {', '.join(lacking)}. While one does, "
                             "every store writer keeps the store owner-only, so they agree and the issuer cannot read "
                             "it. Restart each: a process that began before root added you to the group does not hold "
                             "it (start a new login session, "
                             "then its `aew`, Lead broker or run supervisor). An `aew` started later from an older "
                             "session, such as a terminal multiplexer that outlived the login, does the same while it "
                             f"runs, and is not listed here while it is not running{tail}"))
    else:
        checks.append(_check("store-writers", "PASS", f"every running store writer holds "
                             f"{_group_name(host, found.gid)} (this one and {len(view.others)} other(s)){tail}"))
    if problems is not None:
        bound = set()
        for rel, _g, m in problems:
            if m & ~(sg.GROUP_READ[1] if rel.endswith("/") else sg.GROUP_READ[0]):
                bound.add(rel)
        shown = ", ".join(f"{rel} ({stat.filemode(m)}, neither a file nor a directory)" if stat.S_IFMT(m) else
                          f"{rel} (gid {g}, {m:04o}{', above the bound' if rel in bound else ''})"
                          for rel, g, m in problems[:5])
        by_hand = "; ".join(_by_hand(rel, g, m, target) for rel, g, m in problems[:5])
        refused = refused or []
        off = (f"{len(problems)} path(s) in the store are not at its target, gid {target.gid} with "
               f"{modes}: {shown}{' ...' if len(problems) > 5 else ''}. AEW walks the store again only "
               "when its record (the store's directories and its control file) differs from the target, "
               "so set these by hand, each path's commands in the order given, as the walk steps "
               f"(narrow, then the group, then widen): {by_hand}"
               f"{'; and the rest the same way' if len(problems) > 5 else ''} (a path another account "
               "owns needs that account). Nothing may exceed 0640 files and 0750 directories (WIS-00)"
               if problems else "")
        cannot = (f"AEW cannot change {len(refused)} path(s) in the store: "
                  f"{', '.join(f'{rel} ({why})' for rel, why in refused[:5])}{' ...' if len(refused) > 5 else ''}. "
                  "While one is there, the store's record is at no target, so every command walks the store again "
                  "and WIS cannot be qualified. Have another account's path given to you or removed, and remove a "
                  "file's other names, which may be outside the store (`find / -xdev -samefile PATH` lists them); "
                  "a symbolic link at the control file is replaced by the next commits" if refused else "")
        checks.append(_check("store-modes", "WARN" if problems or refused else "PASS",
                             ". ".join(x for x in (off, cannot) if x) or
                             f"every path in the store is at its target: gid {target.gid}, {modes}"))
    if found.gid is None:
        why = f"no group is private to you (WIS-01a {_parts(found)}; see store-group)"
    elif lacking:
        why = "a running store writer lacks the store's group (see store-writers)"
    elif refused:
        why = "AEW cannot change some store paths, so its record of the store is at no target (see store-modes)"
    elif problems:
        why = "some store paths are not at the store's group and modes (see store-modes)"
    else:
        why = None
    checks.append(_check("wis-store", "WARN" if why else "PASS",
                         f"WIS cannot be qualified on this host: {why}" if why else
                         "WIS can be qualified on this host as far as the store goes: its group is private to you, "
                         "every running store writer holds it, and every path carries it at 0640/0750. The rest (the "
                         "issuer, its view and the gate's checks WIS-Q01 to WIS-Q09) is the qualification gate's"))
    return checks


def _by_hand(rel: str, gid: int, mode: int, target: Any) -> str:
    """The commands that bring one store path (``state/...``, a directory ending in ``/``) to ``target``, in the order
    the walk steps it (``store_group.steps``), from the project's directory. A path that is neither a file nor a
    directory (its ``mode`` keeps its file type) has no place in the store: the command removes it."""
    from aew.engine import store_group as sg

    path = f".aew/{rel}"
    if stat.S_IFMT(mode):
        return f"`rm {path}`"
    return ", ".join(f"`chmod {value:04o} {path}`" if op == "mode" else f"`chgrp {value} {path}`"
                     for op, value in sg.steps(gid, mode, target, rel.endswith("/")))


def _parts(found: Any) -> str:
    """Which part of WIS-01a fails, for the group it concerns."""
    from aew.engine import store_group as sg

    if found.reason == sg.NO_PRIVATE_GROUP and found.primary_reason is not None:
        return (f"{sg.PART.get(found.primary_reason, 'part 1')} (for your primary group) and part 4 (root's record "
                "names no local AEW group)")
    return sg.PART.get(found.reason or "", "part 1")


def _group_name(host: Any, gid: int) -> str:
    names = sorted({g.name for g in (host.groups if host is not None else ()) if g.gid == gid})
    return repr(names[0]) if names else f"gid {gid}"


def _record_text(host: Any, error: str | None) -> str:
    if host is None:
        return f"Root's group record was not read: {error}."
    where = f"Root's group record ({host.record_path})"
    if host.record is None:
        return f"{where}: {host.record_note}."
    group = f"names {host.record.group[0]} (gid {host.record.group[1]})" if host.record.group else "names no group"
    signals = "; ".join(f"for {src}, {s.text!r} covering IDs "
                        f"{','.join(f'{a}-{b}' if a != b else str(a) for a, b in s.ranges)}"
                        for src, s in sorted(host.record.signals.items()))
    return f"{where} {group}{', with signals: ' + signals if signals else ', with no signal'}."


def _unlistable(host: Any) -> list[str]:
    return sorted(s for s, can in (host.sources.items() if host is not None else ()) if not can)


def _why(found: Any, host: Any, error: str | None) -> str:
    """What failed, in words, for the gid it concerns: the primary group's, or the group root's record names."""
    from aew.engine import store_group as sg

    if found.reason == sg.HOST_UNREADABLE or host is None:
        return f"the host's account and group listing failed: {error}"
    named = host.record.group if host.record is not None else None

    def words(reason: str | None, gid: int) -> str:
        return {
            sg.NO_ENTRY: f"gid {gid} has no group entry this host lists",
            sg.ID_HELD_ELSEWHERE: f"another group entry has gid {gid}",
            sg.MEMBERS: f"gid {gid}'s members are not what the rule allows (none for a user-private group, you alone "
                        "for a local AEW group)",
            sg.PRIMARY_ELSEWHERE: f"gid {gid} is another account's primary group too",
            sg.UNLISTABLE_NO_SIGNAL: f"this host also resolves accounts and groups from "
                                     f"{', '.join(_unlistable(host))}, which cannot be listed (configured counts, "
                                     f"running or not), and root's record has no signal for each covering gid {gid}",
            sg.RECORD_NAMES_OTHER: f"root's record names gid {named[1] if named else '?'}, not your user-private "
                                   f"primary group (gid {host.primary})",
            sg.NOT_LOCAL: f"the group root's record names (gid {gid}) is not in this host's own /etc/group under that "
                          "name and ID",
        }.get(reason or "", reason or "unknown")

    if found.reason == sg.NO_PRIVATE_GROUP:
        return (f"your primary group (gid {host.primary}) is not user-private: "
                f"{words(found.primary_reason, host.primary)}; and root's record names no local AEW group")
    if found.primary_reason is None or named is None:  # it concerns the primary group
        return words(found.reason, host.primary)
    return (f"{words(found.reason, named[1])}; and your primary group (gid {host.primary}) is not user-private: "
            f"{words(found.primary_reason, host.primary)}")


def _remedy(found: Any, host: Any) -> str:
    """What root does to give the store its group back. AEW creates, changes and adds members to no group (CB-08)."""
    from aew.engine import store_group as sg

    if host is None:
        return "Fix the host's account listing, then run any `aew` command."
    named = host.record.group if host.record is not None else None
    unlistable = _unlistable(host)
    signal = "".join(f"\n    Signal={src} <the IDs it covers, including the group's> <what shows that no account or "
                     f"group of {src} holds them>" for src in unlistable)
    section = f"[{sg.RECORD_SECTION}]"
    primary_only = found.reason == sg.NO_PRIVATE_GROUP and found.primary_reason == sg.UNLISTABLE_NO_SIGNAL
    if found.reason == sg.UNLISTABLE_NO_SIGNAL or primary_only:
        aew = found.primary_reason is not None and named is not None and not primary_only
        gid = named[1] if aew and named else host.primary
        name = named[0] if aew and named else _group_name(host, gid).strip("'")
        return (f"To get the group mode back, root writes in {host.record_path}:\n    {section}\n    Group={name} {gid}"
                f"{signal}\nwith the signal true for gid {gid} (for example the site's reservation of an ID range "
                "for local groups). AEW changes no group.")
    if found.reason in (sg.NO_PRIVATE_GROUP, sg.NOT_LOCAL):
        return ("To get the group mode back, root creates a local group for you alone (`groupadd <name>`, then "
                f"`gpasswd -a <you> <name>`), and writes in {host.record_path}:\n    {section}\n    Group=<name> <gid>"
                f"{signal}\nthen restart every running AEW process. AEW creates and changes no group.")
    if found.reason == sg.RECORD_NAMES_OTHER:
        return (f"Your primary group is user-private, so it is the store's group: root's record must name it "
                f"(Group={_group_name(host, host.primary).strip(chr(39))} {host.primary}) or be removed.")
    return "The group's entries are root's and the site's to settle; AEW changes no group."


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
