"""The harness-neutral core: the runner, the record, the fact diff and the fixture check.

A *pack* (one per harness) says how to read the binary's version, which checks there are, which capabilities its
adapter declares, what the pinned version's facts are, and how measured facts become fixtures. The core knows nothing
of any harness: it runs the pack's checks in a private environment, keys them by capability, and compares what they
measured with the pin.

Every check needs no network (no provider, no key: the model is the scripted one on loopback), and every home, config,
data, cache, state and temporary folder is private to the run (:func:`private_env`). Egress is not blocked unless the
run is under ``bwrap --unshare-net`` (the CLI's ``--no-network``), and the record says which: a harness may still try
its own fetches on a networked host. A check that needs the VM (bubblewrap) is skipped elsewhere and says so; it is
never reported as passed.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aew.harness.harness_capabilities import GAP

SCHEMA = "aew/harness-qualify/v1"

# A check's result. ``unchecked`` is a capability's, never a check's: the adapter declares it and no check covers it.
PASS, FAIL, ERROR, SKIPPED, UNCHECKED = "pass", "fail", "error", "skipped", "unchecked"
# Where a check can run: ``ci`` on any CI runner (Linux, Windows) given the binary; ``vm`` needs bubblewrap (the Rocky 8
# VM, or a Linux host that has it).
CI, VM = "ci", "vm"
# How deep a check looks: the served API only (``api``), a citation read in the binary's bundled code (``source``),
# or the binary's own behaviour on a real run with the scripted model (``run``), deepest last.
API, CITATION, BEHAVIOUR = "api", "source", "run"
DEPTHS = (API, CITATION, BEHAVIOUR)
# Whose result a check is: the binary's, or the host's (AEW's own containment on this host, whatever the binary).
BINARY, HOST = "binary", "host"
# Exit codes: 0 every binary check that ran passed and the facts match; 1 a check failed or a fact changed; 2 a usage
# error (an --only id that is no check); 3 no binary check ran, so nothing was qualified.
EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_NOTHING_RAN = 0, 1, 2, 3
ROOT = Path(__file__).resolve().parents[2]
NOT_RUN = "not run"

# Variables never passed to anything a check starts: credentials, proxies and the harnesses' own settings.
_DROPPED_SUFFIXES = ("_API_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_KEY")
# Model providers' and clouds' prefixes; a harness's own prefix (its name) is added by the runner.
_DROPPED_PREFIXES = ("AEW_", "OPENAI", "ANTHROPIC", "GOOGLE", "AWS_", "AZURE_", "GITHUB_")
_WINDOWS_KEEP = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "SYSTEMDRIVE", "NUMBER_OF_PROCESSORS",
                 "PROCESSOR_ARCHITECTURE", "OS")
_POSIX_KEEP = ("LANG", "LC_ALL", "TZ")


class UnknownCheck(ValueError):
    """An ``only`` id that names no check of the pack: a usage error, never a run that skips everything."""


@dataclass
class Outcome:
    """What one check found: ``pass`` or ``fail``, the facts it measured (JSON values by fact id), and notes."""

    status: str
    facts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class Context:
    """What a check is given: the binary, a private folder of its own, the private base environment, and the version
    the pack read. ``memo`` shares one expensive measurement (a served API document) between checks of one run."""

    binary: Path
    work: Path
    env: dict[str, str]
    version: str
    memo: dict[str, Any] = field(default_factory=dict)

    def once(self, key: str, make: Callable[[], Any]) -> Any:
        if key not in self.memo:
            self.memo[key] = make()
        return self.memo[key]


@dataclass(frozen=True)
class Check:
    """One check, named by id and keyed by the capability names it covers (none for a harness-wide check)."""

    id: str
    run: Callable[[Context], Outcome]
    capabilities: tuple[str, ...] = ()
    platform: str = CI
    depth: str = BEHAVIOUR
    slow: bool = False
    says: str = ""
    measures: tuple[str, ...] = ()  # the fact ids it measures, so a skipped check's facts say why they are missing
    scope: str = BINARY


@dataclass(frozen=True)
class Release:
    """One version a version source offers: where to fetch it and the digest its publisher gives."""

    version: str
    url: str
    digest: str
    algorithm: str = "sha512"
    size: int | None = None


class VersionSource(Protocol):
    """Where a harness's new versions come from (an update feed, a release list). The scheduled job reads it."""

    def latest(self) -> list[Release]: ...


class Pack(Protocol):
    """One harness's probe pack. The core calls only these."""

    harness: str
    version_source: VersionSource | None

    def declared(self) -> Mapping[str, Mapping[str, Any]]:
        """The capabilities the harness's adapter declares, by name: ``{"status": yes | partial | gap, "how", and for
        a gap its "register" row}`` (``aew.harness.harness_capabilities``)."""

    def checks(self) -> Sequence[Check]: ...

    def read_version(self, binary: Path, work: Path, env: dict[str, str]) -> str: ...

    def pinned(self, fixtures: Path) -> tuple[str, dict[str, Any]]:
        """The pinned version and its facts, read from the fixtures."""

    def render(self, version: str, facts: Mapping[str, Any], fixtures: Path) -> dict[str, tuple[bytes | None, str]]:
        """Each fixture file name -> (the bytes the measured facts make, or None when a run cannot make them; how)."""

    def unmeasured(self) -> Mapping[str, str]:
        """Pinned facts no offline run can measure, each with the reason (kept as register rows)."""

    def adoptable(self, facts: Mapping[str, Any], pinned: Mapping[str, Any]) -> list[str]:
        """The "worth adopting" hook: what the new version offers that the pinned one did not (may be empty)."""


@dataclass
class Record:
    harness: str
    version: str
    binary_sha256: str
    platform: str
    checks: list[dict[str, Any]]
    capabilities: dict[str, dict[str, Any]]
    facts: dict[str, Any]
    unmeasured: dict[str, str]
    started: str
    seconds: float
    network: str = ""
    aew_revision: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"schema": SCHEMA, "harness": self.harness, "version": self.version,
                "binary_sha256": self.binary_sha256, "platform": self.platform, "started": self.started,
                "seconds": self.seconds, "network": self.network, "aew_revision": self.aew_revision,
                "checks": self.checks, "capabilities": self.capabilities, "unmeasured": self.unmeasured,
                "facts": self.facts}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def has_bubblewrap() -> bool:
    return sys.platform.startswith("linux") and shutil.which("bwrap") is not None


def private_env(root: Path, base: Mapping[str, str] | None = None, *, harness: str = "") -> dict[str, str]:
    """A base environment whose every home, config, data, cache, state and temporary folder is under ``root``, with no
    credential, proxy or harness setting (a variable named for ``harness``) from ``base``. Loopback is never
    proxied."""
    base = os.environ if base is None else base
    keep = _WINDOWS_KEEP if sys.platform == "win32" else _POSIX_KEEP
    env = {k: v for k, v in base.items() if k.upper() == "PATH" or k.upper() in keep or k.upper().startswith("LC_")}
    for k in list(env):
        u = k.upper()
        own = bool(harness) and u.startswith(harness.upper())
        if u.endswith(_DROPPED_SUFFIXES) or u.startswith(_DROPPED_PREFIXES) or "PROXY" in u or own:
            del env[k]
    dirs = {"HOME": "home", "USERPROFILE": "home", "XDG_CONFIG_HOME": "xdg-config", "XDG_DATA_HOME": "xdg-data",
            "XDG_CACHE_HOME": "xdg-cache", "XDG_STATE_HOME": "xdg-state", "APPDATA": "appdata",
            "LOCALAPPDATA": "localappdata", "TMPDIR": "tmp", "TEMP": "tmp", "TMP": "tmp"}
    for name, sub in dirs.items():
        (root / sub).mkdir(parents=True, exist_ok=True)
        env[name] = str(root / sub)
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost,::1"
    return env


def aew_revision() -> str | None:
    """The commit of the AEW checkout whose checks made the record (``+dirty`` with local changes), or None."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                             timeout=30, creationflags=flags).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=30, creationflags=flags).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return (sha + ("+dirty" if dirty else "")) if sha else None


NETWORK_BLOCKED_ENV = "HQ_UNSHARE_NET"  # set by the CLI when it runs the tool under bwrap --unshare-net


def network_state() -> str:
    """Whether egress was blocked, and how that was seen: under ``bwrap --unshare-net`` a connection to a public
    address finds no route at once."""
    if os.environ.get(NETWORK_BLOCKED_ENV) != "1":
        return ("not blocked: no check needs the network (no provider, no key, a loopback model), but the harness may "
                "still try its own fetches")
    try:
        socket.create_connection(("192.0.2.1", 443), timeout=2).close()  # TEST-NET-1 (RFC 5737): never a real host
    except OSError as exc:
        if exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH):
            return "blocked: run under bwrap --unshare-net (verified: no route out)"
        return f"blocked: run under bwrap --unshare-net (not verified: {type(exc).__name__})"
    return "NOT blocked: a connection out succeeded under --unshare-net"


def _platform_ok(check: Check) -> str | None:
    if check.platform == VM and not has_bubblewrap():
        return "needs the VM: the containment self-test needs bubblewrap, which this host lacks"
    return None


def qualify(pack: Pack, binary: Path, *, out: Path, only: Iterable[str] | None = None, slow: bool = False,
            keep: bool = False) -> Record:
    """Run ``pack``'s checks against ``binary`` and return the record. ``only`` limits the run to those check ids;
    ``slow`` adds the slow checks (the conformance suite, the containment self-test)."""
    binary = Path(binary).resolve()
    if not binary.is_file():
        raise FileNotFoundError(f"no harness binary at {binary}")
    ids = [c.id for c in pack.checks()]
    unknown = sorted(set(only or ()) - set(ids))
    if unknown:  # a typo would otherwise skip everything and look clean (review of #357, minor 1)
        raise UnknownCheck(f"no such check: {', '.join(unknown)} (the checks: {', '.join(ids)})")
    out.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="hq-", dir=out))
    t0 = time.monotonic()
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    wanted = set(only) if only is not None else None
    try:
        version = pack.read_version(binary, root / "version", private_env(root / "version", harness=pack.harness))
        memo: dict[str, Any] = {}
        results: list[dict[str, Any]] = []
        facts: dict[str, Any] = {}
        for check in pack.checks():
            row: dict[str, Any] = {"id": check.id, "capabilities": list(check.capabilities),
                                   "measures": list(check.measures), "scope": check.scope,
                                   "platform": check.platform, "depth": check.depth, "says": check.says}
            if wanted is not None and check.id not in wanted:
                results.append({**row, "status": SKIPPED, "notes": ["not selected (--only)"]})
                continue
            why = _platform_ok(check) or (None if slow or not check.slow or wanted is not None
                                           else "slow: run with --slow")
            if why:
                results.append({**row, "status": SKIPPED, "notes": [why]})
                continue
            work = root / check.id.replace("/", "_")
            ctx = Context(binary=binary, work=work, env=private_env(work, harness=pack.harness), version=version,
                          memo=memo)
            c0 = time.monotonic()
            try:
                outcome = check.run(ctx)
            except Exception as exc:  # a check that breaks is an error, never a pass
                # the exception line only: a traceback carries host paths, and records are shared
                outcome = Outcome(ERROR, notes=[f"{type(exc).__name__}: {exc}"])
            facts.update(outcome.facts)
            results.append({**row, "status": outcome.status, "notes": outcome.notes,
                            "facts": sorted(outcome.facts), "seconds": round(time.monotonic() - c0, 1)})
        return Record(harness=pack.harness, version=version, binary_sha256=sha256_file(binary),
                      platform=sys.platform, checks=results, capabilities=capability_report(pack.declared(), results),
                      facts=facts, unmeasured=dict(pack.unmeasured()), started=started,
                      seconds=round(time.monotonic() - t0, 1), network=network_state(), aew_revision=aew_revision())
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)


def capability_report(declared: Mapping[str, Mapping[str, Any]],
                      results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """For each capability the adapter declares: the checks that cover it, their statuses, and how deep the passing
    ones looked (``depth``: api, source or run, the deepest). A capability the adapter declares as a gap reads ``gap``
    with its register row; one no check covers is ``unchecked``; one whose every check was skipped is ``skipped``; any
    failing or broken check fails it."""
    out: dict[str, dict[str, Any]] = {}
    for name in sorted(declared):
        rows = [r for r in results if name in r.get("capabilities", ())]
        statuses = {r["status"] for r in rows}
        decl = declared[name]
        if decl.get("status") == GAP:
            status = GAP
        elif not rows:
            status = UNCHECKED
        elif statuses & {FAIL, ERROR}:
            status = FAIL
        elif statuses <= {SKIPPED}:
            status = SKIPPED
        else:
            status = PASS
        passed = [r["depth"] for r in rows if r["status"] == PASS]
        out[name] = {"status": status, "declared": decl.get("status"), "register": decl.get("register"),
                     "depth": max(passed, key=DEPTHS.index) if status == PASS else None,
                     "checks": [f"{r['id']} ({r['status']}, {r['depth']})" for r in rows]}
    stray = sorted({c for r in results for c in r.get("capabilities", ())} - set(declared))
    for name in stray:  # a check keyed by a name the adapter does not declare: say so, never drop it
        out[name] = {"status": "undeclared", "checks": [r["id"] for r in results if name in r["capabilities"]]}
    return out


@dataclass(frozen=True)
class FactDiff:
    fact: str
    path: str
    pinned: Any
    measured: Any

    def line(self) -> str:
        where = f"{self.fact}{self.path}"
        if self.pinned is _MISSING:
            return f"+ {where}: {_short(self.measured)}"
        if self.measured is _MISSING:
            return f"- {where}: {_short(self.pinned)}"
        return f"~ {where}: {_short(self.pinned)} -> {_short(self.measured)}"


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Any = _Missing()


def _short(value: Any, width: int = 160) -> str:
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= width else text[: width - 3] + "..."


def _walk(fact: str, path: str, a: Any, b: Any, out: list[FactDiff]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            _walk(fact, f"{path}.{k}", a.get(k, _MISSING), b.get(k, _MISSING), out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _walk(fact, f"{path}[{i}]", x, y, out)
    elif a != b or type(a) is not type(b):
        out.append(FactDiff(fact, path, a, b))


@dataclass
class Diff:
    """The measured facts against the pinned version's: what changed, what is new, and what was not measured."""

    changed: list[FactDiff]
    new: list[str]
    not_measured: dict[str, str]

    @property
    def clean(self) -> bool:
        return not self.changed

    def lines(self) -> list[str]:
        out = [d.line() for d in self.changed]
        out += [f"+ {name}: measured, no pin" for name in self.new]
        out += [f"? {name}: not measured ({why})" for name, why in sorted(self.not_measured.items())]
        return out


def fact_diff(measured: Mapping[str, Any], pinned: Mapping[str, Any], *, unmeasured: Mapping[str, str] | None = None,
              checks: Sequence[Mapping[str, Any]] = ()) -> Diff:
    """Compare each measured fact with the pin, key by key. A pinned fact this run did not measure is listed with
    why: the pack says it cannot be measured offline, or the check that measures it was skipped or broke."""
    changed: list[FactDiff] = []
    for name in sorted(set(measured) & set(pinned)):
        _walk(name, "", pinned[name], measured[name], changed)
    why_skipped = {f: f"{r['id']} {r['status']}: {'; '.join(r.get('notes') or [])}" for r in checks
                   if r.get("status") != PASS for f in (*r.get("measures", ()), *r.get("facts", ()))}
    not_measured: dict[str, str] = {}
    for name in sorted(set(pinned) - set(measured)):
        not_measured[name] = (unmeasured or {}).get(name) or why_skipped.get(name) or "no check in this run measures it"
    return Diff(changed=changed, new=sorted(set(measured) - set(pinned)), not_measured=not_measured)


def fixture_report(pack: Pack, version: str, facts: Mapping[str, Any], fixtures: Path) -> list[dict[str, str]]:
    """Each fixture the pack makes, against the file in ``fixtures``: ``identical`` (byte for byte), ``differs``,
    ``new`` (no such file yet) or ``not regenerated`` (with the reason)."""
    out = []
    for name, (made, how) in sorted(pack.render(version, facts, fixtures).items()):
        path = fixtures / name
        if made is None:
            status = "not regenerated"
        elif not path.exists():
            status = "new"
        else:
            status = "identical" if path.read_bytes() == made else "differs"
        out.append({"fixture": name, "status": status, "how": how})
    return out


def write_fixtures(pack: Pack, version: str, facts: Mapping[str, Any], fixtures: Path) -> list[str]:
    """Write each fixture the measured facts make (the bump's new fixtures come from here, never by hand)."""
    written = []
    for name, (made, _how) in sorted(pack.render(version, facts, fixtures).items()):
        if made is not None:
            (fixtures / name).write_bytes(made)
            written.append(name)
    return written


def verdict(record: Record, diff: Diff) -> dict[str, str]:
    """The binary's verdict and the host's, apart: a host-scoped check (the containment self-test) never decides the
    binary's (review of #357, minor 9)."""
    def of(scope: str) -> str:
        ran = [r for r in record.checks if r.get("scope", BINARY) == scope and r["status"] != SKIPPED]
        if any(r["status"] in (FAIL, ERROR) for r in ran):
            return FAIL
        return PASS if ran else NOT_RUN

    binary = of(BINARY)
    if binary == PASS and not diff.clean:
        binary = FAIL
    return {"binary": binary, "host": of(HOST)}


def exit_code(record: Record, diff: Diff) -> int:
    v = verdict(record, diff)["binary"]
    return EXIT_OK if v == PASS else EXIT_NOTHING_RAN if v == NOT_RUN else EXIT_FAILED


def document(record: Record, diff: Diff, fixtures: Sequence[Mapping[str, str]],
             adopt: Sequence[str] = ()) -> dict[str, Any]:
    """The published record (``record.json``, schema v1): the run, the verdicts, the diff as data and as lines, the
    fixtures, and what is worth adopting. A wrapper of :func:`qualify` publishes this, never a shape of its own."""
    def value(x: Any) -> Any:
        return None if x is _MISSING else x

    rows = [{"fact": d.fact, "path": d.path, "pinned": value(d.pinned), "measured": value(d.measured),
             "kind": "added" if d.pinned is _MISSING else "removed" if d.measured is _MISSING else "changed"}
            for d in diff.changed]
    return {**record.to_json(), "verdict": verdict(record, diff),
            "diff": {"changed": rows, "new": diff.new, "not_measured": diff.not_measured, "lines": diff.lines()},
            "fixtures": list(fixtures), "adoptable": list(adopt)}


def report(record: Record, diff: Diff, fixtures: Sequence[Mapping[str, str]], adopt: Sequence[str] = ()) -> str:
    """The run as text: checks by platform, capabilities, the fact diff, the fixtures and what is worth adopting."""
    v = verdict(record, diff)
    lines = [f"{record.harness} {record.version} (sha256 {record.binary_sha256}) on {record.platform}, "
             f"{record.seconds}s; AEW {record.aew_revision or 'unknown'}",
             f"Verdict: binary {v['binary']}; host {v['host']} (the host's checks never decide the binary's)",
             f"Network: {record.network}", "", "Checks:"]
    for plat in (CI, VM):
        rows = [r for r in record.checks if r["platform"] == plat]
        if rows:
            lines.append(f"  {plat}:")
            for r in rows:
                host = " [host result, not the binary's]" if r.get("scope") == HOST else ""
                note = f" ({'; '.join(r['notes'][:1])})" if r["notes"] and r["status"] != PASS else ""
                lines.append(f"    {r['status']:8} {r['id']} [{r['depth']}]{host}{note}")
    lines += ["", "Capabilities (declared by the adapter):"]
    for name, c in record.capabilities.items():
        status = c["status"] + (f" ({c['depth']})" if c.get("depth") else "")
        gap = f" [gap: {c['register']}]" if c["status"] == GAP else ""
        lines.append(f"  {status:15} {name}: {', '.join(c['checks']) or 'no check'}{gap}")
    lines += ["", "Fact diff against the pin:"] + ([f"  {x}" for x in diff.lines()] or ["  none"])
    lines += ["", "Not measurable offline (kept as citations and register rows):"]
    lines += [f"  {k}: {v}" for k, v in sorted(record.unmeasured.items())] or ["  none"]
    lines += ["", "Fixtures:"] + [f"  {f['status']:15} {f['fixture']}: {f['how']}" for f in fixtures]
    if adopt:
        lines += ["", "Worth adopting (new in this version):"] + [f"  {a}" for a in adopt]
    from harness_qualify import verdicts  # the record a bump writes and the next one reads

    lines += ["", "Feature verdicts:"] + verdicts.lines(record.harness, record.version)
    return "\n".join(lines) + "\n"


def dump(value: Any) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()
