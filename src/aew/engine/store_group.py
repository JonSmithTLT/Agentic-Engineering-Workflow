"""The store's group (STG-05 CB-08; WIS-01a and WIS-00's mode bound, A-36): which group, and which modes, the store
writers give ``.aew/state``.

The store is group-readable (files :data:`GROUP_READ`, directories likewise) only while two things hold (D-CS1-11 as
amended): WIS-01a's predicate names a group private to the operator (:func:`answer`), and every running store writer,
this process included, holds that group (:func:`target`, with ``aew.engine.store_writers``). Otherwise the store is
owner-only (:data:`OWNER_ONLY`) under the operator's primary group, so no file is ever group-readable to anyone the rule
does not admit, and AEW keeps working.

**One determination** (WIS-01a part 4): :func:`answer` applies parts 1 to 3 to what the host lists and to root's group
record, and to no signal of its own. A name-service source outside :data:`LOCAL_SOURCES` cannot be listed, whether its
daemon runs or not (a missing daemon is a signal of the engine's own), and only a signal in root's record that covers
the group's ID speaks for it (C1-1). The rule is a port of the reference model's ``wis01a``
(``tests/fixtures/stg11-wis-r9/``), and a test compares the two on every host the model builds.

**The seam.** The store reads the host through :data:`HOST`, a module attribute that tests replace in-process. Nothing
here reads an environment variable (a test checks it): an override of this answer that a process's environment could
set would be a route to widen the store.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import string
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

# The two mode pairs (files, directories). GROUP_READ is also WIS-00's upper bound: no store path ever grants more.
GROUP_READ = (0o640, 0o750)
OWNER_ONLY = (0o600, 0o700)

# Name-service sources whose entries are all on this host, so enumerating them lists every entry they hold. `compat` is
# one unless the files hold NIS `+`/`-` lines, which bring in entries this host does not list.
LOCAL_SOURCES = frozenset({"files", "compat", "systemd", "altfiles"})
# The nsswitch.conf(5) databases that resolve an account or the groups it holds: every source any of them names is one
# the host resolves accounts and groups from (WIS-01a part 2).
GROUP_DATABASES = frozenset({"passwd", "group", "initgroups"})
FILES = "files"
OTHER = "nss"  # an entry the merged enumeration returned that is not in this host's files

# The kinds of the store's group (WIS-01a part 1), and why a group is not private: the reference model's names.
USER_PRIVATE = "USER_PRIVATE"
LOCAL_AEW = "LOCAL_AEW"
NO_ENTRY = "NO_ENTRY"
ID_HELD_ELSEWHERE = "ID_HELD_ELSEWHERE"
MEMBERS = "MEMBERS"
PRIMARY_ELSEWHERE = "PRIMARY_ELSEWHERE"
UNLISTABLE_NO_SIGNAL = "UNLISTABLE_NO_SIGNAL"
RECORD_NAMES_OTHER = "RECORD_NAMES_OTHER"
NO_PRIVATE_GROUP = "NO_PRIVATE_GROUP"
NOT_LOCAL = "NOT_LOCAL"
HOST_UNREADABLE = "HOST_UNREADABLE"  # the engine's own: the listing itself failed, so nothing is private
# The part of WIS-01a each reason fails, for `aew doctor`.
PART = {NO_ENTRY: "part 2", ID_HELD_ELSEWHERE: "part 2", MEMBERS: "part 2", PRIMARY_ELSEWHERE: "part 2",
        UNLISTABLE_NO_SIGNAL: "part 3", RECORD_NAMES_OTHER: "part 4", NOT_LOCAL: "parts 1 and 4",
        NO_PRIVATE_GROUP: "parts 1 and 4", HOST_UNREADABLE: "parts 2 and 3"}

# Root's group record (WIS-01a part 4): an `X-` section, which systemd ignores, in the issuer's store-path drop-in, the
# root-owned place WIS-12's install manifest covers. The issuer's installer writes it, and must take its path, its
# format and `store_ref` from here (record_path, parse_record, store_ref), never restate them.
STORE_REF_PREFIX = "store:"
UNIT_DIR = Path("/etc/systemd/system")
ISSUER_UNIT = "aew-wis-issuer"
RECORD_FILE = "store.conf"
RECORD_SECTION = "X-AEW-Store-Group"
NSSWITCH = Path("/etc/nsswitch.conf")
ETC = Path("/etc")


@dataclass(frozen=True)
class GroupEntry:
    src: str
    name: str
    gid: int
    members: tuple[str, ...]


@dataclass(frozen=True)
class Account:
    src: str
    name: str
    primary: int


@dataclass(frozen=True)
class Signal:
    """Root's word for a source that cannot be listed, and the IDs it covers (inclusive ranges): it shows WIS-01a part 2
    for those IDs only (C1-1)."""

    text: str
    ranges: tuple[tuple[int, int], ...]

    def covers(self, gid: int) -> bool:
        return any(lo <= gid <= hi for lo, hi in self.ranges)


@dataclass(frozen=True)
class Record:
    """Root's group record: the store's group by name and ID (None where it names none), and a signal per source."""

    group: tuple[str, int] | None
    signals: dict[str, Signal] = field(default_factory=dict)


@dataclass(frozen=True)
class HostGroups:
    """What a party can see (WIS-01a part 4): the sources (``True`` where it can be listed), the entries it can list
    (the operator's own account always), and root's record, or why there is none (``record_note``)."""

    operator: str
    primary: int
    sources: dict[str, bool]
    groups: tuple[GroupEntry, ...]
    accounts: tuple[Account, ...]
    record: Record | None
    record_note: str | None = None
    record_path: str | None = None


@dataclass(frozen=True)
class Answer:
    """WIS-01a's answer: the store's group and its kind where it is private, else why not (``reason``). Where the
    primary group is not user-private, ``primary_reason`` says why (doctor reports both)."""

    gid: int | None
    kind: str | None
    reason: str | None
    primary_reason: str | None = None


@dataclass(frozen=True)
class Credentials:
    """A process's groups, as the kernel checks them for ``chown`` (an owner may give a file a group it holds)."""

    egid: int
    groups: frozenset[int]

    def holds(self, gid: int) -> bool:
        return gid == self.egid or gid in self.groups


class Holder(Protocol):
    """A store writer, as far as the target needs it: whether it holds a group (``Credentials``, or a running
    writer's entry, ``store_writers.Writer``)."""

    def holds(self, gid: int) -> bool: ...


@dataclass(frozen=True)
class Target:
    """The group and modes every store publication gets now: (``gid``, ``file_mode``, ``dir_mode``)."""

    gid: int
    file_mode: int
    dir_mode: int

    @property
    def group_readable(self) -> bool:
        return bool(self.file_mode & 0o040)

    def mode(self, is_dir: bool) -> int:
        return self.dir_mode if is_dir else self.file_mode


# ------------------------------------------------------------------------------------------- the rule (parts 1 to 4)

def answer(host: HostGroups) -> Answer:
    """WIS-01a parts 1 to 4 over what ``host`` lists and root's record in it, and nothing else (SG1-3)."""
    record = host.record
    signals = record.signals if record is not None else {}
    unlistable = sorted(s for s, can in host.sources.items() if not can)

    def alone(gid: int, name: str, members: list[str]) -> str | None:
        """Part 2 over the sources that can be listed, and part 3 for each source that cannot."""
        entries = [g for g in host.groups if g.gid == gid]
        if not entries:
            return NO_ENTRY
        if any(g.name != name for g in entries):
            return ID_HELD_ELSEWHERE  # another group entry has the ID (SG1-1)
        if any(list(g.members) != members for g in entries):
            return MEMBERS
        if any(a.primary == gid and a.name != host.operator for a in host.accounts):
            return PRIMARY_ELSEWHERE
        if any(s not in signals or not signals[s].covers(gid) for s in unlistable):
            return UNLISTABLE_NO_SIGNAL  # only root's record speaks for such a source, for the IDs it covers (C1-1)
        return None

    primary_why = alone(host.primary, host.operator, [])
    named = record.group if record is not None else None
    if primary_why is None:
        if named is not None and tuple(named) != (host.operator, host.primary):
            # The record names a group part 1 does not select (C1-1), or the user-private ID under a name other than
            # the operator's, which the listing contradicts (D-CS1-16).
            return Answer(None, None, RECORD_NAMES_OTHER)
        return Answer(host.primary, USER_PRIVATE, None)  # a local AEW group is not used here, even if one exists
    if named is None:
        return Answer(None, None, NO_PRIVATE_GROUP, primary_why)
    local = [g for g in host.groups if g.gid == named[1] and g.src == FILES]
    if not local or local[0].name != named[0]:
        return Answer(None, None, NOT_LOCAL, primary_why)  # absent, in a directory, or contradicting the record
    why = alone(named[1], named[0], [host.operator])
    if why:
        return Answer(None, None, why, primary_why)
    return Answer(named[1], LOCAL_AEW, None, primary_why)


def target(found: Answer, primary: int, me: Holder, others: Iterable[Holder]) -> Target:
    """D-CS1-10 and D-CS1-11 as amended: the store's group, group-readable, only where it is private and every running
    store writer holds it (this process from its own credentials, the others from their entries); otherwise owner-only
    under the primary group. Every running writer computes the same, so they agree (SG1-5)."""
    gid = found.gid
    if gid is not None and me.holds(gid) and all(w.holds(gid) for w in others):
        return Target(gid, *GROUP_READ)
    return Target(primary, *OWNER_ONLY)


def steps(gid: int, mode: int, want: Target, is_dir: bool) -> list[tuple[str, int]]:
    """How one path moves from ``(gid, mode)`` to the target, as ``("mode", m)`` and ``("group", g)`` steps.
    First narrow to what both the start and the end grant (with no group bit at all when the group changes), then
    re-group, then widen. Every intermediate state therefore grants a subset of what the start or the end grants
    (WIS-00's bound at every step, SG1-2): the group changes only while the path grants its group nothing, and a start
    above the bound is brought down first. Going up it is the reference model's "re-group, then re-mode", going down
    "re-mode, then re-group"; going sideways (C1-2) it passes through no group bits."""
    end = want.mode(is_dir)
    narrow = mode & end & (~0o070 if gid != want.gid else 0o7777)
    out: list[tuple[str, int]] = []
    if narrow != mode:
        out.append(("mode", narrow))
    if gid != want.gid:
        out.append(("group", want.gid))
    if end != narrow:
        out.append(("mode", end))
    return out


# --------------------------------------------------------------------------------------------- root's group record

def store_ref(store_dir: Path) -> str:
    """WIS-01's ``store_ref``: ``store:`` and the first 32 hex characters of the SHA-256 of the store's real path."""
    return STORE_REF_PREFIX + hashlib.sha256(os.fsencode(str(store_dir.resolve()))).hexdigest()[:32]


def instance_id(ref: str) -> str:
    """The issuer's systemd instance name for a ``store_ref``: its 32 hex characters (the one place they are cut)."""
    if not ref.startswith(STORE_REF_PREFIX):
        raise ValueError(f"not a store_ref: {ref!r}")
    return ref[len(STORE_REF_PREFIX):]


def record_path(store_dir: Path, unit_dir: Path = UNIT_DIR) -> Path:
    """Where root's group record for the store at ``store_dir`` is: the issuer instance's store-path drop-in."""
    return unit_dir / f"{ISSUER_UNIT}@{instance_id(store_ref(store_dir))}.service.d" / RECORD_FILE


def parse_ids(text: str) -> tuple[tuple[int, int], ...]:
    """``900-999,1000`` as inclusive ranges. Refuses anything else, and an empty or reversed range."""
    out = []
    for part in text.split(","):
        lo, sep, hi = part.partition("-")
        if not lo.isdigit() or (sep and not hi.isdigit()):
            raise ValueError(f"IDs must be N or N-M, comma-separated: {text!r}")
        a, b = int(lo), int(hi) if sep else int(lo)
        if b < a:
            raise ValueError(f"an empty ID range: {part!r}")
        out.append((a, b))
    return tuple(out)


def parse_record(text: str) -> Record | None:
    """Root's group record from a drop-in's text: the ``[X-AEW-Store-Group]`` section, or None where it has none.

    ``Group=<name> <gid>`` names the store's group (at most once). Each ``Signal=<source> <IDs> <words>`` is root's
    signal for one source that cannot be listed: its nsswitch name, the IDs it covers (``N`` or ``N-M``,
    comma-separated) and what shows it. Other sections (the drop-in's ``[Service]``), comments and blank lines are
    ignored. Anything else in the section is refused (``ValueError``): a record that cannot be read is no record."""
    section: str | None = None
    found = False
    group: tuple[str, int] | None = None
    signals: dict[str, Signal] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            found = found or section == RECORD_SECTION
            continue
        if section != RECORD_SECTION:
            continue
        key, sep, value = line.partition("=")
        words = value.split()
        if not sep or key not in ("Group", "Signal"):
            raise ValueError(f"unknown line in [{RECORD_SECTION}]: {line!r}")
        if key == "Group":
            if group is not None or len(words) != 2 or not words[1].isdigit():
                raise ValueError(f"Group= is `<name> <gid>`, given once: {line!r}")
            group = (words[0], int(words[1]))
        else:
            if len(words) < 3 or words[0] in signals:
                raise ValueError(f"Signal= is `<source> <IDs> <what shows it>`, one per source: {line!r}")
            signals[words[0]] = Signal(" ".join(words[2:]), parse_ids(words[1]))
    return Record(group, signals) if found else None


def root_owned(path: Path) -> str | None:
    """Why ``path`` is not a root-owned record, or None: a regular file reached through no symbolic link, it and every
    directory above it owned by root and writable by no one else (WIS-00's path rule). Only root can then have
    written it."""
    try:
        chain = [path, *path.parents]
        for i, p in enumerate(chain):
            st = os.lstat(p)
            if stat.S_ISLNK(st.st_mode):
                return f"{p} is a symbolic link"
            if i == 0 and not stat.S_ISREG(st.st_mode):
                return f"{p} is not a regular file"
            if st.st_uid != 0:
                return f"{p} is owned by uid {st.st_uid}, not root"
            if st.st_mode & 0o022:
                return f"{p} is writable by its group or by others ({stat.S_IMODE(st.st_mode):04o})"
    except OSError as exc:
        return f"cannot inspect it ({exc.strerror or exc})"
    return None


def load_record(path: Path, *, check: Callable[[Path], str | None] = root_owned) -> tuple[Record | None, str | None]:
    """``(record, None)``, or ``(None, why there is none)``: absent, not root's, unreadable or malformed."""
    if not path.exists() and not path.is_symlink():
        return None, "absent"
    problem = check(path)
    if problem is not None:
        return None, f"not root's, so ignored: {problem}"
    try:
        record = parse_record(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, f"unreadable, so ignored: {exc}"
    if record is None:
        return None, f"the drop-in has no [{RECORD_SECTION}] section"
    return record, None


# --------------------------------------------------------------------------------------------- the host's listing

def nss_sources(nsswitch: Path = NSSWITCH, etc: Path = ETC) -> dict[str, bool]:
    """The name-service sources for accounts and groups, each ``True`` where it can be listed: the sources of every
    database in ``nsswitch`` that resolves an account or the groups it holds (:data:`GROUP_DATABASES`), ``files``
    where none is configured (glibc's default). Every source outside :data:`LOCAL_SOURCES` cannot be listed,
    configured and idle alike, and so is `compat` when the files hold NIS lines.

    Each line, which ends at a newline only, is read as glibc reads it: the database's name ends at whitespace or a
    colon, then whitespace and colons are skipped, and every word after them that is not an action is a source. A line
    whose first word starts with ``#`` names no database. A ``#`` later in a line ends it on some glibc versions and
    not on others, so the words after it count as sources too: a word that is no source is one that cannot be listed,
    which fails closed."""
    try:
        lines = _lines(nsswitch)
    except FileNotFoundError:
        return {FILES: True}
    found: dict[str, bool] = {}
    for raw in lines:
        line = raw.lstrip()
        db = re.split(r"[\s:]", line, maxsplit=1)[0]
        rest = line[len(db):].lstrip(string.whitespace + ":")
        if db not in GROUP_DATABASES:
            continue
        for word in re.sub(r"\[[^]]*\]", " ", rest).split():  # without its actions, such as [SUCCESS=merge]
            found[word] = word in LOCAL_SOURCES and not (word == "compat" and _nis_lines(etc))
    return found or {FILES: True}


def _lines(path: Path) -> list[str]:
    """The lines of ``nsswitch.conf`` or of a files database, as glibc reads them: each ends at a newline only. The
    file is read as bytes, because a text read ends a line at a lone carriage return too, and ``str.splitlines`` at
    nine more characters."""
    return path.read_bytes().decode("utf-8", errors="replace").split("\n")


def _nis_lines(etc: Path) -> bool:
    """Whether ``passwd`` or ``group`` under ``etc`` has a NIS ``+``/``-`` line, which `compat` resolves remotely."""
    for name in ("passwd", "group"):
        try:
            lines = _lines(etc / name)
        except OSError:
            continue
        if any(line.startswith(("+", "-")) for line in lines):
            return True
    return False


def _fields(path: Path, count: int) -> list[list[str]]:
    """The colon-separated lines of a files database with at least ``count`` fields; NIS lines and comments skipped."""
    out = []
    try:
        lines = _lines(path)
    except FileNotFoundError:
        return out
    for line in lines:
        if not line or line.startswith(("#", "+", "-")):
            continue
        parts = line.split(":")
        if len(parts) >= count and parts[2].isdigit() and (count < 4 or parts[3].isdigit()):
            out.append(parts)
    return out


def _members(text: str) -> tuple[str, ...]:
    return tuple(m for m in text.strip().split(",") if m)


def read_host(store_dir: Path, *, nsswitch: Path = NSSWITCH, etc: Path = ETC, unit_dir: Path = UNIT_DIR,
              getgrall: Callable[[], Sequence[Any]] | None = None, getpwall: Callable[[], Sequence[Any]] | None = None,
              getpwuid: Callable[[int], Any] | None = None, uid: int | None = None, gid: int | None = None,
              check: Callable[[Path], str | None] = root_owned) -> HostGroups:
    """What this host lists, for the store at ``store_dir``: the sources (:func:`nss_sources`); this host's own files,
    read directly, so an entry's source is known (part 1's "local", and ``NOT_LOCAL``, need it); every other entry the
    merged enumeration returns, as another source's (it still counts against privacy; its absence proves nothing about
    a source that cannot be listed); the operator; and root's record. Every input is an argument, so tests give fixture
    files and functions, and never the host's own database. POSIX only."""
    if sys.platform == "win32":  # pragma: windows-only
        raise OSError("this host has no POSIX accounts or groups")
    import grp  # pragma: posix-only
    import pwd

    getgrall = getgrall or grp.getgrall
    getpwall = getpwall or pwd.getpwall
    getpwuid = getpwuid or pwd.getpwuid
    uid = os.getuid() if uid is None else uid
    sources = nss_sources(nsswitch, etc)
    groups = [GroupEntry(FILES, f[0], int(f[2]), _members(f[3] if len(f) > 3 else ""))
              for f in _fields(etc / "group", 3)]
    accounts = [Account(FILES, f[0], int(f[3])) for f in _fields(etc / "passwd", 4)]
    for g in getgrall():
        if not any(e.name == g.gr_name and e.gid == g.gr_gid and e.members == tuple(g.gr_mem) for e in groups):
            groups.append(GroupEntry(OTHER, g.gr_name, g.gr_gid, tuple(g.gr_mem)))
    for p in getpwall():
        if not any(a.name == p.pw_name and a.primary == p.pw_gid for a in accounts):
            accounts.append(Account(OTHER, p.pw_name, p.pw_gid))
    try:
        me = getpwuid(uid)
        operator, primary = me.pw_name, me.pw_gid
        if not any(a.name == operator and a.primary == primary for a in accounts):
            accounts.append(Account(OTHER, operator, primary))  # the operator's own entry is always seen
    except KeyError:  # a container's or a user namespace's uid: no name, so no user-private group either
        operator, primary = f"uid {uid}", os.getgid() if gid is None else gid
    path = record_path(store_dir, unit_dir)
    record, note = load_record(path, check=check)
    return HostGroups(operator, primary, sources, tuple(groups), tuple(accounts), record, note, str(path))


# The seam: how the store reads the host. Tests set it in-process (`monkeypatch`), or in a child they start through
# tests/helpers/host_seam; nothing in AEW sets it from the environment.
HOST: Callable[[Path], HostGroups] = read_host
