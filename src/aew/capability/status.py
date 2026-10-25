"""Each capability's status on this host, in S-01's terms (STG-15, A-38: CAPR-03, CAPR-04, CAPR-12).

The status is derived on every read from the records, the register's state and the payloads on disk, never stored
as a verdict, so ``aew capability list``, ``aew doctor`` and (later) the agents' catalogs and D-01's capabilities read
all say the same (S01-21). AEW's copy of a provider is, in order:

* ``REFUSED``: its record fails validation, its payload does not match its pin, or its last fetch or import was;
* ``UNSUPPORTED``: its record has no payload for this host's platform;
* ``UNAVAILABLE``: its payload is not here (never fetched, or the fetch failed), or its last check failed;
* ``NOT_ESTABLISHED``: its payload is here and was never checked;
* ``STALE``: its record or pin changed since its check, or the host did (the kernel, the C library, the harness);
* ``FUNCTIONAL_ONLY``: its check passed. A check alone never makes a capability ``QUALIFIED``, which needs a
  qualification record (none exists yet).

Where AEW's copy is absent, refused, unsupported or failing, a copy the host has on its PATH serves on its own,
named as an unpinned provider, with its own status beside the cause for AEW's copy (CAPR-04), unless the operator
turned host copies off. With no copy at all, the capability reads AEW's copy's status, with its cause.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew.capability import payload as P
from aew.capability import records, store
from aew.errors import AEWError, ValidationFailed

QUALIFIED, FUNCTIONAL_ONLY, NOT_ESTABLISHED = "QUALIFIED", "FUNCTIONAL_ONLY", "NOT_ESTABLISHED"
UNSUPPORTED, UNAVAILABLE, STALE, REFUSED = "UNSUPPORTED", "UNAVAILABLE", "STALE", "REFUSED"
STATUSES = (QUALIFIED, FUNCTIONAL_ONLY, NOT_ESTABLISHED, UNSUPPORTED, UNAVAILABLE, STALE, REFUSED)  # S01-04
USABLE = frozenset({QUALIFIED, FUNCTIONAL_ONLY})  # "usable means checked" (CAPR-03, AEW-FR-34.b)
NOT_SERVING = frozenset({UNAVAILABLE, REFUSED, UNSUPPORTED})  # AEW's copy cannot serve: a host copy may
AEW_COPY, HOST_COPY = "aew", "host"
UNPINNED = "an unpinned host copy: AEW does not know its version, and did not check it against a pin"
HEALTH_TIMEOUT_S = 30.0  # one step of a health check: `--version`, or the fixture query over a few lines

CHECK = "aew capability check"
IMPORT = "aew capability import"  # given the operator's bundle: a path, never a placeholder in a fix (D2 O-IDS)


@dataclass
class Copy:
    """One copy of a provider and its status: AEW's pinned one, or the host's."""

    kind: str
    status: str
    cause: str | None = None
    fix: str | None = None
    path: str | None = None
    checked_at: str | None = None
    limitations: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        return {"copy": self.kind, "status": self.status, "cause": self.cause, "fix": self.fix, "path": self.path,
                "checked_at": self.checked_at, "limitations": self.limitations}


def host_facts() -> dict[str, str | None]:
    """The host changes that make a check STALE (CAPR-03): the kernel, the C library and the harness."""
    libc = None
    if sys.platform.startswith("linux"):
        libc = " ".join(p for p in platform.libc_ver() if p) or None
    kernel = platform.version() if sys.platform == "win32" else platform.release()
    return {"kernel": kernel or None, "libc": libc, "harness": harness_identity()}


def harness_identity() -> str | None:
    """The harness binary a launch from this environment would run, by its path, size and modification time (a new
    harness version is a new binary); None where there is none. Not its ``--version``: every read of a status would
    start it."""
    from aew.harness.opencode.adapter import binary_command

    try:
        path = Path(binary_command()[-1]).resolve()
        st = path.stat()
    except (AEWError, OSError):
        return None
    return f"{path} ({st.st_size} bytes, modified {st.st_mtime_ns})"


def _changed(then: dict[str, Any], now: dict[str, str | None]) -> list[str]:
    return [f"the {k} changed ({then.get(k)} -> {now[k]})" for k in ("kernel", "libc", "harness")
            if then.get(k) != now[k]]


def effective(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every provider in force: AEW's shipped records under the operator's, which override by name (CAPR-04). Each is
    ``{record, layer, problem, upgrade}``: ``problem`` is why an operator record is refused (its record is then None);
    ``upgrade`` lists where the shipped record now differs from the one the override was made over."""
    out = {name: {"record": rec, "layer": "shipped", "problem": None, "upgrade": []}
           for name, rec in records.shipped().items()}
    for name, held in sorted((state.get("operator_records") or {}).items()):
        entry: dict[str, Any] = {"record": None, "layer": "operator", "problem": None, "upgrade": []}
        try:
            entry["record"] = records.validate({"schema": records.SCHEMA, "providers": {name: held.get("record")}},
                                               source=f"the operator's record {name}")[name]
        except ValidationFailed as exc:  # re-validated on every read: a damaged record is refused, never served
            entry["problem"] = "; ".join(exc.details.get("violations") or [exc.message])
        shipped = records.shipped().get(name)
        if shipped is not None and held.get("base_digest") != records.digest(shipped):
            base = held.get("base_record") or {}
            entry["upgrade"] = records.differences(base, shipped) or ["the shipped record changed"]
        out[name] = entry
    return out


def aew_copy(name: str, record: dict[str, Any] | None, problem: str | None, state: dict[str, Any], *,
             facts: dict[str, str | None], key: str | None = None, directory: Path | None = None) -> Copy:
    """AEW's copy of provider ``name`` on this host (the module's order)."""
    if record is None:
        return Copy(AEW_COPY, REFUSED, f"its record is refused: {problem}",
                    f"fix the operator's record and add it again, or `aew capability remove {name}`")
    key = key or records.platform_key()
    pinned = record["payloads"].get(key)
    if pinned is None:
        return Copy(AEW_COPY, UNSUPPORTED, f"its record has no payload for this platform ({key})",
                    f"install {record['command']} on this host (a host copy serves, named unpinned), or add an "
                    "operator record with a payload for this platform (`aew capability add`)")
    path = P.path_of(name, record["command"], pinned, directory)
    refused = (state.get("refused") or {}).get(f"{name}:{key}")
    if refused and refused.get("sha256") == pinned["sha256"]:
        return Copy(AEW_COPY, REFUSED, f"its payload was refused at {refused.get('at')}: {refused.get('reason')}",
                    f"`{CHECK}` fetches the pinned payload again (online), or `{IMPORT}` imports, from the "
                    "operator's bundle, one that matches its pin (offline)", str(path))
    done = (state.get("checks") or {}).get(f"{AEW_COPY}:{name}")
    if not path.exists() and done is not None and done.get("sha256") != pinned["sha256"] \
            and not (state.get("fetch_failures") or {}).get(f"{name}:{key}"):
        # A new pin (CAPR-03): checked before under another one, and this one's payload is not here yet
        return Copy(AEW_COPY, STALE, f"its pin changed since it was checked (checked {str(done.get('sha256'))[:16]}, "
                    f"now pinned {pinned['sha256'][:16]}), and the newly pinned payload is not on this host yet",
                    f"`{CHECK}` fetches it (online), or `{IMPORT}` imports it from the operator's bundle (offline)",
                    str(path), done.get("at"))
    if not path.exists():
        failed = (state.get("fetch_failures") or {}).get(f"{name}:{key}")
        cause = (f"its pinned payload is not on this host: the fetch failed at {failed.get('at')} "
                 f"({failed.get('reason')})" if failed and failed.get("sha256") == pinned["sha256"] else
                 "its pinned payload is not on this host: it was never fetched or imported")
        return Copy(AEW_COPY, UNAVAILABLE, cause, f"`{CHECK}` fetches it (online), or `{IMPORT}` imports it from "
                    "the operator's bundle (offline)", str(path))
    wrong = P.verify(path, pinned)
    if wrong is not None:
        return Copy(AEW_COPY, REFUSED, f"its payload does not match its pin: {wrong}",
                    f"`{CHECK}` refuses it and fetches it again (online), or `{IMPORT}` with the operator's bundle "
                    "(offline)", str(path))
    return _checked(AEW_COPY, done, path, facts, digest=records.digest(record), sha256=pinned["sha256"],
                    changed="its record or its pin changed since it was checked")


def host_copy(name: str, record: dict[str, Any], state: dict[str, Any], *, facts: dict[str, str | None],
              directory: Path | None = None) -> Copy | None:
    """The host's own copy of the record's command, found on this process's PATH (outside AEW's register), with its
    own status; None when the host has none."""
    found = find_host_copy(record["command"], directory)
    if found is None:
        return None
    try:
        sha256 = file_sha256(found)
    except OSError as exc:
        return Copy(HOST_COPY, UNAVAILABLE, f"the host copy {found} cannot be read ({exc})", None, str(found),
                    limitations=[UNPINNED])
    done = (state.get("checks") or {}).get(f"{HOST_COPY}:{name}")
    if done is not None and done.get("path") != str(found):
        done = None  # another file: never checked
    copy = _checked(HOST_COPY, done, found, facts, digest=None, sha256=sha256,
                    changed="the host copy changed since it was checked")
    copy.limitations.append(UNPINNED)
    if done is not None and done.get("version"):
        copy.limitations.append(f"it reports {done['version']}")
    return copy


def _checked(kind: str, done: dict[str, Any] | None, path: Path, facts: dict[str, str | None], *, digest: str | None,
             sha256: str, changed: str) -> Copy:
    if done is None:
        return Copy(kind, NOT_ESTABLISHED, "it was never checked on this host", f"`{CHECK}`", str(path))
    at = done.get("at")
    if (digest is not None and done.get("record_digest") != digest) or done.get("sha256") != sha256:
        return Copy(kind, STALE, changed, f"`{CHECK}`", str(path), at)
    host = _changed(done.get("facts") or {}, facts)
    if host:
        return Copy(kind, STALE, "the host changed since it was checked: " + "; ".join(host), f"`{CHECK}`", str(path),
                    at)
    if not done.get("ok"):
        return Copy(kind, UNAVAILABLE, f"its check failed: {done.get('cause')}",
                    f"fix what the check names, then `{CHECK}`", str(path), at)
    return Copy(kind, FUNCTIONAL_ONLY, None, None, str(path), at)


def find_host_copy(command: str, directory: Path | None = None) -> Path | None:
    """``command`` on this process's PATH, leaving out AEW's own register: the host copy CAPR-04 lets serve."""
    reg = os.path.normcase(os.path.realpath(directory or store.root()))
    entries = [p for p in (os.environ.get("PATH") or "").split(os.pathsep) if p
               and not os.path.normcase(os.path.realpath(p)).startswith(reg)]
    found = shutil.which(command, path=os.pathsep.join(entries))
    return Path(found).resolve() if found else None


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(P.CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def health(executable: Path, record: dict[str, Any], *, pinned: bool = True) -> tuple[bool, str | None, str | None]:
    """``(passed, cause, first line of --version)``: the record's version check, then its fixture query, run on a
    fixture written to a fresh directory. A host copy (``pinned=False``) is not AEW's pin, so its version check asks
    only that it is the provider: the record's expected line without the record's version (``ripgrep``, for
    ``ripgrep 15.1.0``); what version it is, is recorded. Run on the host in this slice; CAPR-13 runs a sandbox-placed
    provider's check contained, as its uses run, which comes with the bind into every contained context (CAP-1's
    second PR)."""
    spec = record["health"]
    expect = spec["version"]["expect"]
    if not pinned and expect.endswith(record["version"]):
        expect = expect[: -len(record["version"])].rstrip() or expect
    with tempfile.TemporaryDirectory(prefix="aew-capability-") as tmp:
        for name, text in spec["fixture"]["files"].items():
            (Path(tmp) / name).write_bytes(text.encode("utf-8"))
        ok, out, why = _run([str(executable), *spec["version"]["args"]], tmp)
        if not ok:
            return False, f"`{record['command']} {' '.join(spec['version']['args'])}` {why}", None
        first = (out.strip().splitlines() or [""])[0].strip()
        if not first.startswith(expect):
            return False, f"its version check printed {first[:200]!r}, not {expect!r}", first
        ok, out, why = _run([str(executable), *spec["fixture"]["args"]], tmp)
        if not ok:
            return False, f"its fixture query {why}", first
        if out.strip() != spec["fixture"]["expect"].strip():
            return False, (f"its fixture query printed {out.strip()[:200]!r}, not "
                           f"{spec['fixture']['expect'].strip()!r}"), first
    return True, None, first


def _run(argv: list[str], cwd: str) -> tuple[bool, str, str]:
    """One health-check step: an owned child with no window and no stdin, waited for; on its timeout
    ``subprocess.run`` kills it (a CLI provider's check starts no children of its own)."""
    from aew.harness import agentenv

    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    # The operating system's basics and PATH, as a use has them; no tool's own configuration (RIPGREP_CONFIG_PATH)
    env = {k: v for k, v in os.environ.items() if k.upper() in keep or k.upper() == "PATH"}
    env.setdefault("LANG", "C.UTF-8")
    try:
        done = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, errors="replace",
                              stdin=subprocess.DEVNULL, timeout=HEALTH_TIMEOUT_S,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, "", f"did not finish within {HEALTH_TIMEOUT_S:g} s"
    except OSError as exc:
        return False, "", f"could not start ({exc})"
    if done.returncode != 0:
        err = (done.stderr or "").strip().splitlines()
        return False, done.stdout, f"exited {done.returncode}" + (f": {err[-1][:200]}" if err else "")
    return True, done.stdout, ""
