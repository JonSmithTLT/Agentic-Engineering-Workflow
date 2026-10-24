"""WIS-12's install manifest: what a carrier and the qualifier recompute, and ``service_build_sha256`` its hash.

It covers the issuer's installed files (every regular file under the install root, ``/opt/aew-wis``) and **every
unit fragment and drop-in systemd loads for the ``aew-wis*`` units, under all unit search paths**, read from the files
(G3 R2-3): the store-path drop-in, the operator's socket drop-in and any drop-in anyone adds are among them, so each
changes the hash. The hash is the reference model's: the SHA-256 of the canonical JSON of the sorted ``[path, sha256]``
pairs (``verify_wis.py``'s ``manifest_hash``); a symbolic link is hashed as ``symlink:<target>``, and the install root
may hold none.

**Two detectors for the unit files, agreeing both ways.** The scan reads every search path systemd names
(``systemd-analyze unit-paths``) for ``aew-wis*`` fragments and ``.d`` drop-in directories, and, for each loaded
``aew-wis*`` unit, works out which of them systemd loads (the first fragment of the unit or its template in search-path
order; each drop-in name from the highest-priority directory that has it, for the unit and its template). systemd's
own answer is ``systemctl show -p FragmentPath -p DropInPaths``. For every loaded unit the two must name the same files;
any difference, either way, is a refusal: a file systemd loads that the scan missed would go unhashed, and one the scan
expects that systemd ignores means the scan's rule is not systemd's. The hash then covers every scanned file, loaded or
shadowed, so a change to any of them changes it.
"""

from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
from pathlib import Path

from aew_wis.engine_rules import canonical_json
from aew_wis.wire import sha

INSTALL_ROOT = Path("/opt/aew-wis")
UNIT_PREFIX = "aew-wis"
UNIT_SUFFIXES = (".service", ".socket")
CHILD_TIMEOUT_S = 30


class ManifestRefused(Exception):
    """The manifest cannot be computed honestly; the message says why."""


def file_data(path: Path) -> bytes:
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return b"symlink:" + os.fsencode(os.readlink(path))
    if not stat.S_ISREG(st.st_mode):
        raise ManifestRefused(f"{path} is neither a regular file nor a symbolic link")
    return path.read_bytes()


def installed_files(root: Path = INSTALL_ROOT) -> dict[str, bytes]:
    """Every file under the install root, by absolute path. A symbolic link there is refused: what root runs is
    exactly what is hashed."""
    out = {}
    for d, dirs, files in os.walk(root):
        for name in sorted(dirs + files):
            path = Path(d) / name
            if os.path.islink(path):
                raise ManifestRefused(f"{path} is a symbolic link; the install root may hold none")
        for name in files:
            path = Path(d) / name
            out[path.as_posix()] = file_data(path)
    return out


def _unit_name(name: str) -> bool:
    return name.startswith(UNIT_PREFIX) and name.endswith(UNIT_SUFFIXES)


def unit_files(search_paths: list[str]) -> dict[str, bytes]:
    """Every ``aew-wis*`` fragment, and every ``*.conf`` in an ``aew-wis*`` drop-in directory, in every search path."""
    out = {}
    for sp in search_paths:
        base = Path(sp)
        try:
            names = sorted(os.listdir(base))
        except FileNotFoundError:
            continue
        for name in names:
            path = base / name
            if _unit_name(name):
                out[path.as_posix()] = file_data(path)
            elif name.endswith(".d") and _unit_name(name[:-2]) and path.is_dir() and not path.is_symlink():
                for conf in sorted(os.listdir(path)):
                    if conf.endswith(".conf"):
                        out[(path / conf).as_posix()] = file_data(path / conf)
    return out


def manifest_hash(files: dict[str, bytes]) -> str:
    """``service_build_sha256``: the reference model's hash of the sorted ``[path, sha256]`` pairs."""
    return sha(canonical_json(sorted([path, sha(data)] for path, data in files.items())))


# ---------------------------------------------------------------------------------------------- the two detectors

def template_of(unit: str) -> str | None:
    """``aew-wis-issuer@x.service`` -> ``aew-wis-issuer@.service``; None for a unit that is no instance."""
    stem, dot, suffix = unit.rpartition(".")
    if "@" not in stem or stem.endswith("@"):
        return None
    return stem.split("@", 1)[0] + "@." + suffix if dot else None


def expected_loads(unit: str, search_paths: list[str], scanned: dict[str, bytes]) -> set[str]:
    """What systemd 239 loads for ``unit``, by its rules, from the scanned files: the first fragment found for the unit
    (then its template) in search-path order, and each drop-in file name from the highest-priority directory that has
    it, for the unit and its template alike."""
    template = template_of(unit)
    names = [unit] + ([template] if template else [])
    out: set[str] = set()
    for name in names:
        hit = next((f"{sp}/{name}" for sp in search_paths if f"{sp}/{name}" in scanned), None)
        if hit is not None:
            out.add(hit)
            break
    for name in names:
        seen: set[str] = set()
        for sp in search_paths:
            prefix = f"{sp}/{name}.d/"
            for path in sorted(p for p in scanned if p.startswith(prefix)):
                conf = path[len(prefix):]
                if conf not in seen:
                    seen.add(conf)
                    out.add(path)
    return out


def parse_show(raw: bytes) -> list[set[str]]:
    """``systemctl show -p FragmentPath -p DropInPaths <unit>...``: one set of paths per unit, in the order asked
    (records are separated by a blank line). Read as bytes, split on ``b"\\n"``; a line that is neither property is
    refused."""
    records = []
    for group in raw.split(b"\n\n"):
        lines = [line for line in group.split(b"\n") if line]
        if not lines:
            continue
        paths: set[str] = set()
        for line in lines:
            key, sep, value = line.partition(b"=")
            if not sep or key not in (b"FragmentPath", b"DropInPaths"):
                raise ManifestRefused(f"systemctl show printed {line[:80]!r}")
            paths.update(os.fsdecode(v) for v in value.split(b" ") if v)
        records.append(paths)
    return records


def cross_check(units: list[str], shown: list[set[str]], search_paths: list[str],
                scanned: dict[str, bytes]) -> list[str]:
    """Every loaded unit's files, by the scan's rule and by systemd's answer: each difference, either way."""
    if len(shown) != len(units):
        return [f"systemctl show answered for {len(shown)} unit(s), not the {len(units)} asked"]
    problems = []
    for unit, systemd_says in zip(units, shown, strict=True):
        ours = expected_loads(unit, search_paths, scanned)
        for path in sorted(systemd_says - ours):
            problems.append(f"{unit}: systemd loads {path}, which the manifest's scan does not expect")
        for path in sorted(ours - systemd_says):
            problems.append(f"{unit}: the scan expects {path}, which systemd does not load")
    return problems


# ---------------------------------------------------------------------------------------------- on the host

def _run(argv: list[str]) -> bytes:
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,  # noqa: S603
                            stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "SYSTEMD_PAGER": ""},
                            start_new_session=sys.platform != "win32")
    try:
        out, err = proc.communicate(timeout=CHILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            os.killpg(proc.pid, signal.SIGKILL)
        else:  # pragma: no cover - the manifest is computed on Linux hosts
            proc.kill()
        proc.communicate()
        raise ManifestRefused(f"{argv[0]} did not finish within {CHILD_TIMEOUT_S} s") from None
    if proc.returncode != 0:
        first = err.split(b"\n")[0].decode("utf-8", "replace")[:200]
        raise ManifestRefused(f"{' '.join(argv)} failed: {first}")
    return out


def host_manifest(install_root: Path = INSTALL_ROOT) -> dict[str, object]:
    """The manifest on this host, both detectors run and compared."""
    search_paths = [os.fsdecode(p) for p in _run(["systemd-analyze", "unit-paths"]).split(b"\n") if p.startswith(b"/")]
    scanned = unit_files(search_paths)
    listed = _run(["systemctl", "list-units", "--all", "--plain", "--no-legend", "--no-pager", f"{UNIT_PREFIX}*"])
    units = sorted({os.fsdecode(line.split(b" ")[0]) for line in listed.split(b"\n")
                    if line and _unit_name(os.fsdecode(line.split(b" ")[0]))})
    shown = parse_show(_run(["systemctl", "show", "-p", "FragmentPath", "-p", "DropInPaths", *units])) if units else []
    problems = cross_check(units, shown, search_paths, scanned)
    files = {**installed_files(install_root), **scanned}
    return {"service_build_sha256": manifest_hash(files), "files": sorted([p, sha(d)] for p, d in files.items()),
            "units": units, "problems": problems}
