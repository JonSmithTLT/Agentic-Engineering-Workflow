"""The register of weaker contexts (G3 addendum 7, ruling 2; register E112): every agent context on this host that ran
with less than full containment, while it runs and for G3's window after it ends.

**What is weaker** (:func:`aew.harness.containment.weaker`): a label that is not ``os_readonly_roots`` with a
``proxy_only`` or ``isolated`` network and a passing self-test. Contained launches write nothing here, so the normal
path gains no failure mode.

**Where it lives:** ``weaker-contexts/`` in AEW's per-host state (:mod:`aew.hoststate`), per operator account, beside
the capability register: outside every project and every sandbox's writable binds. A root that resolves into
``/dev``, ``/proc`` or ``/sys`` is refused as unwritable (#316's lesson).

**Writing an entry:** the context's owning host process (the Lead session, a run's supervisor, a validation run's
executor, the operator's check run, an eval lane's host) calls :func:`enter` before the context's first process starts.
It is the only writer of entries. On Linux an entry that cannot be written refuses the launch
(``CONTAINMENT_UNAVAILABLE``, reason ``weaker_register_unwritable``); elsewhere the launch runs, since Windows has no G3
and no containment.

**Ending an entry** (the designer's ruling of 2026-11-01 on E112's entry end): no entry ends while any process of its
context may live. A live owner's ``clean`` outcome ends it only when (a) the owner held the whole tree (a subreaper, a
pid namespace or a job object: :data:`HOLDS_WHOLE`), (b) no survivor is still the process it was (``same_process``),
and (c) a marker scan finds no process carrying the context's marker, nor an unreadable process that is not a host
and started after the entry was written. An owner that held less (a bare process group), or one that died with no
outcome recorded, leaves the context unowned: live until the next boot, or until a scan finds none of it, which
:func:`sweep` records.

**The marker** is :data:`MARKER` in each context's environment: the path of the file that holds its label. It is how
the scan finds a context's processes, and, at the register's first creation, how a running context shows its label.

**Reading it** (:func:`read`, for G3's standing, which G3-C builds): writes nothing. "Was a weaker context live on this
host in the last N seconds?" is ``not read(N).clear``.

**What it cannot see** (addendum 7, "What I accept"): an uncontained context's own acts. It runs as the operator, and
can delete its entry or drop the marker from its children's environment. The register catches what AEW started.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sys
import time
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew import hoststate
from aew.errors import AEWError, ContainmentUnavailable
from aew.util import atomic_write, create_exclusive, utc_now

SCHEMA = "aew/weaker-context/v1"
CREATED_SCHEMA = "aew/weaker-contexts-created/v1"
DIRNAME, CREATED, LOCK = "weaker-contexts", "created.json", "register.lock"
MARKER = "AEW_CONTEXT"
UNWRITABLE = "weaker_register_unwritable"
# G3's window: G3-06's tripwire, the longest a consent stays valid after its approval (g3/aew_g3/deployment.py,
# "consent_validity_minutes": ("max", 15); a deployment may only shorten it). A duration in seconds. An entry stays in
# the register for this long after its context ends, so a consent still consumable was approved after it ended.
WINDOW_S = 15 * 60
# How long a writer waits for the register's lock: every holder only writes or prunes small files.
LOCK_TIMEOUT_S = 10.0
KINDS = frozenset({
    "lead_session",      # `aew lead session`, the dogfood's Lead included
    "lead_opencode",     # `aew opencode`: off Linux always, on Linux when its label is weaker
    "worker_run",        # a run's supervisor
    "validation_run",    # a checks-mode validation run, authoritative or diagnostic
    "check_run",         # the operator's own `aew check run`
    "eval_raw",          # an eval raw arm, the qualification's included
    "eval_scoring",      # eval's scorer of a model-written tree
    "eval_live",         # the qualification's live lane
    "dogfood_scorer",    # the dogfood's hidden scorer
    "dogfood_debrief",   # the dogfood's debrief of a saved Lead session (every tool denied)
    "found_at_creation",  # a context already running when the register was first created on this host
})
# How an owner holds its context's processes: only these hold the whole tree, so that orphaned descendants come back
# to it (ruling (a)). A bare process group does not: a child that starts a session of its own leaves it.
HOLDS_WHOLE = frozenset({"subreaper", "pid_namespace", "job_object"})
OWNERSHIPS = HOLDS_WHOLE | {"process_group", "unowned"}
# Where the register must never resolve to: the kernel's own trees, which a symlink could point into (#316).
FORBIDDEN_ROOTS = ("/dev", "/proc", "/sys")
PROC = Path("/proc")

# Tests point the register at a directory of their own, in process; the product never sets it. (An environment
# variable would let any process that launches AEW choose another register.) The register is still one per
# hoststate base (XDG_DATA_HOME, LOCALAPPDATA on Windows): a writer and a reader started with different values use
# different registers (#321 review, N2).
ROOT_OVERRIDE: Path | None = None


def root() -> Path:
    """This host's register of weaker contexts."""
    return ROOT_OVERRIDE if ROOT_OVERRIDE is not None else hoststate.root() / DIRNAME


def enforced() -> bool:
    """Whether a launch whose entry cannot be written is refused: Linux, the one platform with containment and G3."""
    return sys.platform.startswith("linux")


def legacy_markers() -> tuple[str, ...]:
    """The variables older code's contexts carry, for the creation scan: a worker's run (``agentenv``) and a Lead
    session's broker (``lead_broker``)."""
    from aew.harness import agentenv, lead_broker

    return (*agentenv.AGENT_VARS, *lead_broker.ENV_NAMES)


# ------------------------------------------------------------------------------------------------- the marker scan

@dataclass(frozen=True)
class Proc:
    """One of the operator's processes, as the scan read it. ``env`` is None when its environment cannot be read (a
    non-dumpable process); ``ticks`` is when it started, in clock ticks since boot."""

    pid: int
    start_id: str | None
    ticks: int | None
    env: Mapping[str, str] | None
    cmdline: tuple[str, ...]


@dataclass
class Scan:
    """The operator's processes, or ``failed`` when ``/proc`` could not be listed: a failed scan is never clean."""

    procs: list[Proc] = field(default_factory=list)
    failed: str | None = None
    boot: str | None = None
    now_ticks: int | None = None

    def carrying(self, marker: str | None) -> list[Proc]:
        return [p for p in self.procs if marker and p.env is not None and p.env.get(MARKER) == marker]


def scan(proc: Path | None = None, uid: int | None = None) -> Scan | None:
    """Every process of the operator's UID (Linux; None elsewhere, which has no ``/proc``). Reads ``environ``,
    ``cmdline`` and ``stat`` only, as bytes, and never follows a process's ``root`` or ``cwd`` link into its sandbox's
    trees. A process that ends while it is read is left out; one whose environment cannot be read is kept, marked."""
    from aew.harness.procs import linux_start_id

    base = proc or PROC
    if proc is None and not enforced():
        return None
    want = os.getuid() if uid is None else uid  # type: ignore[attr-defined,unused-ignore]
    out = Scan()
    try:
        out.boot = (base / "sys" / "kernel" / "random" / "boot_id").read_bytes().decode("latin-1").strip() or None
        names = sorted(int(p.name) for p in base.iterdir() if p.name.isdigit())
    except OSError as exc:
        out.failed = f"{base}: {exc}"
        return out
    out.now_ticks = _uptime_ticks(base)
    for pid in names:
        here = base / str(pid)
        try:
            if here.stat().st_uid != want:
                continue
            stat = (here / "stat").read_bytes().decode("latin-1")
            cmdline = tuple(os.fsdecode(a) for a in (here / "cmdline").read_bytes().split(b"\0") if a)
        except OSError:  # it ended while it was read
            continue
        try:
            ticks: int | None = int(stat.rsplit(")", 1)[1].split()[19])
        except (IndexError, ValueError):
            ticks = None
        try:
            raw = (here / "environ").read_bytes()
            env: dict[str, str] | None = {}
            for item in raw.split(b"\0"):
                key, sep, value = item.partition(b"=")
                if sep:
                    env[os.fsdecode(key)] = os.fsdecode(value)
        except FileNotFoundError:
            continue
        except OSError:  # PermissionError: non-dumpable (procs.harden_current_process), or a stranger's
            env = None
        start = linux_start_id(out.boot, ticks) if out.boot and ticks is not None else None
        out.procs.append(Proc(pid=pid, start_id=start, ticks=ticks, env=env, cmdline=cmdline))
    return out


def _clock_tick() -> int:
    """Clock ticks per second, the unit of ``/proc/<pid>/stat``'s start time (Linux; elsewhere nothing has ticks, and
    Linux's usual 100 stands in)."""
    sysconf = getattr(os, "sysconf", None)
    return int(sysconf("SC_CLK_TCK")) if sysconf is not None else 100


def _uptime_ticks(base: Path) -> int | None:
    try:
        return int(float((base / "uptime").read_bytes().split()[0]) * _clock_tick())
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _trusted(path: str | Path, roots: Iterable[str]) -> bool:
    """Whether a marker names a record AEW wrote, the only file a marker is followed to (#321 review, F2): an entry's
    own file in this register, or a run's ``label.json`` or ``run.json`` under the ``.aew`` of a project an entry
    records (``<aew_root>/local/harness/runs/<run>/``), which every sandbox hides. Anything else a process's
    environment names (a file in a workspace, a FIFO, a device, a path under ``/proc``) is not read: its process is no
    host, and a label it holds exempts nothing."""
    from aew.harness import runlog

    here = Path(os.path.abspath(path))
    if here.parent == Path(os.path.abspath(root())):
        return True
    runs = os.path.normcase(str(here.parent.parent))
    return here.name in ("label.json", runlog.RECORD) and any(
        runs == os.path.normcase(os.path.abspath(Path(r) / runlog.RUNS_REL)) for r in roots)


def _load(path: str | Path | None, roots: Iterable[str] = ()) -> dict[str, Any] | None:
    """A record AEW wrote (:func:`_trusted`), read as runlog reads a run's files: a regular file, never through a
    symlink and never blocking on a FIFO or a device (``O_NOFOLLOW | O_NONBLOCK``; on Windows, which has no
    ``O_NOFOLLOW``, a link or non-file is refused by ``lstat`` before the open), at most ``runlog.MAX_RECORD_BYTES``,
    the bound of a run record. None for anything else, or anything JSON cannot hold (nesting past the parser's depth
    included, as ``runlog.read_record``)."""
    from aew.harness import runlog

    if not path or not _trusted(path, roots):
        return None
    try:
        data = json.loads(runlog.read_regular(Path(path)))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _label_of(data: dict[str, Any] | None) -> dict[str, Any] | None:
    """The containment label a marker's file holds: ``label.json`` is one, and a run record holds one."""
    if data is None:
        return None
    inner = data.get("containment")
    return inner if isinstance(inner, dict) else data if data.get("filesystem") else None


def hosts(entries: list[dict[str, Any]], seen: Scan, roots: Iterable[str] = ()) -> set[str]:
    """The start ids AEW recorded for its host processes (the designer's ruling of 2026-11-01: a host is decided by
    identity, never by its command line): each entry's owner; the Lead session a marker's ``label.json`` names; the
    supervisor a run record names, found through a readable child's marker or the supervisor's own ``--run-dir``; and
    the operator endpoint of each entry's project. A command line only points to the record to check; the start id's
    match is the proof, so one that names a real record but is another process is no host. A marker is followed only
    to a record AEW wrote, of a project an entry (or ``roots``) names (:func:`_trusted`)."""
    from aew.harness import operator_client, runlog

    found: set[str] = set()
    known_roots = {str(e["aew_root"]) for e in entries if e.get("aew_root")} | {str(r) for r in roots}

    def add(record: dict[str, Any] | None, key: str) -> None:
        value = (record or {}).get(key)
        if isinstance(value, str):
            found.add(value)

    for entry in entries:
        if entry.get("kind") != "found_at_creation":  # that owner is the context itself, not a host
            add(entry.get("owner"), "start_id")
        if entry.get("aew_root"):
            add(operator_client.read_locator(operator_client.locator_path(Path(entry["aew_root"]))), "start_id")
    for p in seen.procs:
        if p.env is not None:
            data = _load(p.env.get(MARKER), known_roots)
            add(data, "session_start_id")
            add(data, "supervisor_start_id")
        elif "--run-dir" in p.cmdline[:-1]:
            directory = p.cmdline[p.cmdline.index("--run-dir") + 1]
            add(_load(Path(directory) / runlog.RECORD, known_roots), "supervisor_start_id")
    return found


def blockers(entry: dict[str, Any], seen: Scan | None, known_hosts: set[str]) -> list[str]:
    """What keeps an entry's context possibly live by the scan (ruling (c)): a process carrying its marker, and an
    unreadable process that is not a host and started after the entry was written. A failed scan blocks."""
    if seen is None:
        return []  # no /proc (Windows): the job's own count stands in, since nothing can leave the job
    if seen.failed:
        return [f"the scan failed: {seen.failed}"]
    out = [f"{p.pid} carries its marker" for p in seen.carrying(entry.get("marker"))]
    written = entry.get("written_ticks")
    same_boot = seen.boot is not None and entry.get("boot") == seen.boot
    for p in seen.procs:
        if p.env is not None or (p.start_id and p.start_id in known_hosts):
            continue
        if not same_boot or written is None or p.ticks is None or p.ticks >= written:
            out.append(f"{p.pid} cannot be read and started after the entry ({' '.join(p.cmdline)[:80]})")
    return out


# --------------------------------------------------------------------------------------------------------- writing

def _checked_root() -> Path:
    """The register's directory, made if absent (0700). Refused when it resolves into the kernel's own trees."""
    directory = root()
    resolved = os.path.realpath(directory)
    if not sys.platform.startswith("win") and any(
            resolved == r or resolved.startswith(r + "/") for r in FORBIDDEN_ROOTS):
        raise OSError(f"{directory} resolves to {resolved}, inside the kernel's own trees")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


@contextlib.contextmanager
def _locked(directory: Path) -> Iterator[None]:
    from aew.engine.lock import FileLock

    with FileLock(directory / LOCK, timeout=LOCK_TIMEOUT_S):
        yield


def _now_ticks() -> tuple[str | None, int | None]:
    if not enforced():
        return None, None
    try:
        boot = PROC.joinpath("sys", "kernel", "random", "boot_id").read_text().strip() or None
    except OSError:
        boot = None
    return boot, _uptime_ticks(PROC)


def _new(kind: str, *, owner: tuple[int, str | None], project: str | None, aew_root: str | None,
         directory: str | None, label: Mapping[str, Any] | None, marker: str | None,
         reason: str | None = None) -> dict[str, Any]:
    boot, ticks = _now_ticks()
    return {"schema": SCHEMA, "id": f"{kind}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(4)}",
            "kind": kind, "project": project, "aew_root": aew_root, "directory": directory,
            "label": dict(label) if label is not None else None, "marker": marker,
            "owner": {"pid": owner[0], "start_id": owner[1]}, "written_at": utc_now(), "written_epoch": time.time(),
            "boot": boot, "written_ticks": ticks, "outcome": None, "ownership": None, "survivors": [],
            "ended_at": None, "ended_epoch": None, "cleared_at": None, "cleared_epoch": None, "reason": reason}


def _aew_command(cmdline: tuple[str, ...]) -> bool:
    """Whether a command line is AEW's: the ``aew`` program, run directly or by its interpreter, or ``-m aew...``. It
    only selects which unreadable processes the creation scan counts; it never makes a host."""
    if any(os.path.basename(a).lower() in ("aew", "aew.exe") for a in cmdline[:2]):
        return True
    return any(a == "-m" and (b == "aew" or b.startswith("aew.")) for a, b in zip(cmdline, cmdline[1:], strict=False))


def _ensure_created(directory: Path, *, aew_root: str | Path | None = None, creator: str | None = None) -> None:
    """At the register's first creation on this host: its creation counts as a weaker context that ended then, and
    every AEW context already running counts as weaker until it ends, unless the label its marker names is not. No
    entry names a project yet, so a marker is trusted only into the creating owner's own project (``aew_root``), and
    the creating owner's own process (``creator``, its start id) is a host, not a context found running (#321 N1)."""
    if (directory / CREATED).exists():
        return
    from aew.harness.containment import weaker

    seen = scan()
    found: list[dict[str, Any]] = []
    legacy = legacy_markers()
    roots = {str(aew_root)} if aew_root else set()
    known = (hosts([], seen, roots) if seen is not None else set()) | ({creator} if creator else set())
    for p in (seen.procs if seen is not None else []):
        if p.env is None:
            # An unreadable process with AEW's command line and no record naming it counts as weaker; any other
            # unreadable one (ssh-agent, gpg-agent) does not (the designer's ruling of 2026-11-01 on E112's entry end).
            # Its label cannot be read, and a command line is never trusted to name one: a run's own supervisor is a
            # host by its start id, so only a process no record names is counted.
            if not _aew_command(p.cmdline) or (p.start_id and p.start_id in known):
                continue
            label = None
        elif p.env.get(MARKER) or any(p.env.get(m) for m in legacy):
            label = _label_of(_load(p.env.get(MARKER), roots))
        else:
            continue
        if label is not None and not weaker(label):
            continue
        found.append(_new("found_at_creation", owner=(p.pid, p.start_id), project=None, aew_root=None,
                          directory=None, label=label, marker=(p.env or {}).get(MARKER),
                          reason="running when this host's register was created"))
    for entry in found:
        create_exclusive(directory / f"{entry['id']}.json", json.dumps(entry, indent=1, sort_keys=True) + "\n")
    data = {"schema": CREATED_SCHEMA, "created_at": utc_now(), "created_epoch": time.time(),
            "scan": "unavailable" if seen is None else seen.failed or "ok", "found": [e["id"] for e in found]}
    with contextlib.suppress(AEWError):  # another writer created it first: theirs stands
        create_exclusive(directory / CREATED, json.dumps(data, indent=1, sort_keys=True) + "\n")


class Entry:
    """One context's entry, held by its owner: :meth:`mark` its environment, :meth:`started` at its first process,
    :meth:`end` once its tree is reaped."""

    def __init__(self, path: Path | None, data: dict[str, Any], ownership: str) -> None:
        if ownership not in OWNERSHIPS:
            raise ValueError(f"unknown ownership {ownership!r}")
        self.path, self.data, self.ownership = path, data, ownership
        self._started = False

    @property
    def id(self) -> str:
        return str(self.data["id"])

    def mark(self, env: Mapping[str, str]) -> dict[str, str]:
        out = dict(env)
        if self.data.get("marker"):
            out[MARKER] = str(self.data["marker"])
        return out

    def started(self) -> None:
        self._started = True

    def end(self, survivors: Sequence[tuple[int, str | None]] | None = (), *, ownership: str | None = None) -> None:
        """Record the context's outcome. ``survivors`` are what the reaper could not end, each ``(pid, start_id)``;
        None when the owner does not know (the entry is then unowned). An entry whose context never started a
        process ends ``clean`` at once: nothing ran. Never raises: a register that cannot be written now leaves the
        entry live, which only ever holds G3 longer."""
        from aew.harness.procs import same_process

        if self.path is None or self.data.get("outcome") is not None:
            return
        own = ownership or self.ownership
        now, stamp = time.time(), utc_now()
        # a survivor the reaper could not name (no start id) is never proven ended
        live = [(pid, sid) for pid, sid in (survivors or []) if not sid or same_process(pid, sid)]
        self.data["ownership"] = own
        self.data["survivors"] = [{"pid": pid, "start_id": sid} for pid, sid in live]
        if not self._started:
            self.data.update(outcome="clean", ended_at=stamp, ended_epoch=now, reason="nothing was started")
        else:
            try:
                directory = self.path.parent
                entries = [e for e in _entries(directory) if isinstance(e, dict)]
                seen = scan()
                blocked = blockers(self.data, seen, hosts(entries, seen) if seen is not None else set())
            except Exception as exc:  # noqa: BLE001 (any failure of the scan is a failed scan: unowned, never clean)
                blocked = [f"the scan failed: {type(exc).__name__}: {exc}"[:300]]
            if live:
                self.data["outcome"] = "survivors"
            elif own in HOLDS_WHOLE and survivors is not None and not blocked:
                self.data.update(outcome="clean", ended_at=stamp, ended_epoch=now)
            else:  # held less than the whole tree, or does not know what survived: unowned (ruling (a))
                self.data["outcome"] = "unowned"
                if not blocked:  # "until the marker scan finds none"
                    self.data.update(cleared_at=stamp, cleared_epoch=now)
            if blocked:
                self.data["reason"] = "; ".join(blocked)[:600]
        with contextlib.suppress(OSError, AEWError):
            atomic_write(self.path, json.dumps(self.data, indent=1, sort_keys=True) + "\n")


def _register_error(directory: Path, exc: BaseException) -> ContainmentUnavailable:
    return ContainmentUnavailable(
        f"this weaker launch cannot be entered in the register of weaker contexts at {directory} ({exc}), so it is "
        f"refused: G3 reads that register to know a weaker context was live on this host (G3 addendum 7). Make "
        f"{directory} writable by your account (and its disk not full), or run the launch contained",
        reason=UNWRITABLE, register=str(directory))


def enter(*, kind: str, label: Mapping[str, Any] | None, ownership: str, project: str | Path | None = None,
          aew_root: str | Path | None = None, directory: str | Path | None = None,
          marker: str | Path | None = None, owner_pid: int | None = None) -> Entry:
    """Enter a weaker context, before its first process starts. ``marker`` is the file that holds its label (default:
    the entry itself). ``ownership`` is how the owner will hold its processes (:data:`OWNERSHIPS`). Raises
    ``ContainmentUnavailable`` on Linux when the entry cannot be written; elsewhere returns an entry that records
    nothing."""
    from aew.harness.procs import start_id

    if kind not in KINDS:
        raise ValueError(f"unknown weaker-context kind {kind!r}")
    pid = owner_pid or os.getpid()
    data = _new(kind, owner=(pid, start_id(pid)), project=str(project) if project else None,
                aew_root=str(aew_root) if aew_root else None, directory=str(directory) if directory else None,
                label=label, marker=str(marker) if marker else None)
    reg = root()
    try:
        reg = _checked_root()
        path = reg / f"{data['id']}.json"
        data["marker"] = data["marker"] or str(path)
        with _locked(reg):
            _ensure_created(reg, aew_root=aew_root, creator=data["owner"]["start_id"])
            _prune(reg, time.time())
            create_exclusive(path, json.dumps(data, indent=1, sort_keys=True) + "\n")
    except (OSError, AEWError) as exc:
        if enforced():
            raise _register_error(reg, exc) from None
        return Entry(None, data, ownership)
    return Entry(path, data, ownership)


def ownership_of(label: Mapping[str, Any]) -> str:
    """How a run's processes are held, from its label's ``process_ownership`` (``containment.label``): a pid
    namespace, a job object or a process group. A label that does not say is unowned, which only ever holds longer."""
    value = label.get("process_ownership")
    return value if value in OWNERSHIPS else "unowned"


def enter_if_weaker(label: Mapping[str, Any], **kw: Any) -> Entry | None:
    """:func:`enter` when ``label`` is weaker; None for a contained one, which writes nothing."""
    from aew.harness.containment import weaker

    return enter(label=label, **kw) if weaker(label) else None


@contextlib.contextmanager
def context(**kw: Any) -> Iterator[Entry]:
    """:func:`enter`, and an outcome however the body ends: one the body did not record is an unknown one."""
    entry = enter(**kw)
    try:
        yield entry
    finally:
        entry.end(None)


# --------------------------------------------------------------------------------------------- reading and sweeping

def _entries(directory: Path) -> list[dict[str, Any] | str]:
    """Every entry, or the file's name where one cannot be read: marked, never dropped."""
    out: list[dict[str, Any] | str] = []
    for path in sorted(directory.glob("*.json")):
        if path.name == CREATED:
            continue
        try:
            data = json.loads(path.read_bytes())
        except (OSError, ValueError):
            out.append(path.name)
            continue
        out.append(data if isinstance(data, dict) and data.get("schema") == SCHEMA else path.name)
    return out


def _ended(entry: dict[str, Any]) -> float | None:
    when = entry.get("ended_epoch") or entry.get("cleared_epoch")
    return float(when) if isinstance(when, (int, float)) else None


def _why_live(entry: dict[str, Any], boot: str | None) -> str | None:
    """Why an entry with no end is still live, or None when its context is proven over (a new boot)."""
    from aew.harness.procs import same_process

    owner = entry.get("owner") or {}
    if entry.get("outcome") is None and owner.get("pid") and same_process(owner["pid"], owner.get("start_id") or ""):
        return "running"
    if boot is not None and entry.get("boot") and entry["boot"] != boot:
        return None
    # a survivor the reaper could not name (no start id) is never proven ended: it holds the entry until a new boot
    left = [s for s in entry.get("survivors") or []
            if not s.get("start_id") or same_process(s.get("pid"), s.get("start_id") or "")]
    if left:
        return f"survivors still running: {', '.join(str(s['pid']) if s.get('start_id') else 'unnamed' for s in left)}"
    return "unowned: its owner ended with no outcome proving its processes ended" \
        if entry.get("outcome") in (None, "unowned") else "its processes are not yet proven ended"


@dataclass
class Reading:
    """The register as :func:`read` found it. ``live`` and ``recent`` hold ``{id, kind, project, why}``;
    ``unreadable`` names what could not be read. ``created_epoch`` is None when it was never created here."""

    window_s: float
    created_at: str | None = None
    created_epoch: float | None = None
    live: list[dict[str, Any]] = field(default_factory=list)
    recent: list[dict[str, Any]] = field(default_factory=list)
    unreadable: list[str] = field(default_factory=list)
    now: float = 0.0

    @property
    def clear(self) -> bool:
        """No weaker context was live on this host in the window: the register exists, was created before the
        window, and holds nothing live, nothing that ended inside it, and nothing unreadable."""
        return (self.created_epoch is not None and self.now - self.created_epoch >= self.window_s
                and not self.live and not self.recent and not self.unreadable)


def read(window_s: float = WINDOW_S, now: float | None = None) -> Reading:
    """The register for G3's standing: what was live on this host in the last ``window_s`` seconds. Writes nothing,
    so any reader can call it; an unowned context stays live here until :func:`sweep` records that it ended, so G3's
    reader calls :func:`sweep` first, then this (#321 review, N1)."""
    now = time.time() if now is None else now
    out = Reading(window_s=window_s, now=now)
    directory = root()
    if not directory.exists():
        return out
    created = _load(directory / CREATED)
    if created is None:
        if (directory / CREATED).exists():
            out.unreadable.append(CREATED)
    else:
        out.created_at, out.created_epoch = created.get("created_at"), created.get("created_epoch")
    try:
        entries = _entries(directory)
    except OSError as exc:
        out.unreadable.append(f"{directory}: {exc}")
        return out
    boot, ticks = _now_ticks()
    booted = now - ticks / _clock_tick() if ticks is not None else None
    for entry in entries:
        if isinstance(entry, str):
            out.unreadable.append(entry)
            continue
        brief = {"id": entry.get("id"), "kind": entry.get("kind"), "project": entry.get("project")}
        ended = _ended(entry)
        if ended is not None:
            if now - ended < window_s:
                out.recent.append({**brief, "why": f"ended at {entry.get('ended_at') or entry.get('cleared_at')}"})
            continue
        why = _why_live(entry, boot)
        if why is not None:
            out.live.append({**brief, "why": why})
        elif booted is None or now - booted < window_s:  # ended by a reboot inside the window
            out.recent.append({**brief, "why": "ended by a reboot"})
    return out


def _prune(directory: Path, now: float) -> None:
    for entry in _entries(directory):
        if isinstance(entry, dict):
            ended = _ended(entry)
            if ended is not None and now - ended >= WINDOW_S:
                with contextlib.suppress(OSError):
                    (directory / f"{entry['id']}.json").unlink()


def sweep(now: float | None = None) -> None:
    """Record the end of every context proven over since its owner last wrote (a writer; under the register's lock):
    an unowned context, or one whose survivors have all ended, whose marker scan is clean, or that a new boot ended.
    Then prune what ended before the window. Creates the register on its first call on a host."""
    now = time.time() if now is None else now
    directory = _checked_root()
    with _locked(directory):
        _ensure_created(directory)
        entries = [e for e in _entries(directory) if isinstance(e, dict)]
        seen = scan()
        known = hosts(entries, seen) if seen is not None else set()
        boot, _ = _now_ticks()
        for entry in entries:
            if _ended(entry) is not None:
                continue
            why = _why_live(entry, boot)
            if why == "running" or (why or "").startswith("survivors"):
                continue
            if why is not None and blockers(entry, seen, known):
                continue
            stamp = utc_now()
            entry.update(cleared_at=stamp, cleared_epoch=now,
                         reason=(entry.get("reason") or "") + ("; ended by a reboot" if why is None else
                                                               "; a scan found none of its processes"))
            with contextlib.suppress(OSError, AEWError):
                atomic_write(directory / f"{entry['id']}.json", json.dumps(entry, indent=1, sort_keys=True) + "\n")
        _prune(directory, now)
