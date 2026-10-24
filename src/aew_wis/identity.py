"""WIS-11's identity rule: one rule, used by both parties (review R4-1).

Root computes the store directory's identity at the store's path when it anchors (WIS-B's anchor tool); the issuer
computes it inside its view on every read (WIS-02's first two rows). Both call :func:`identity_of` on what they see,
so a rule on which they disagree cannot be written twice:

* ``store_fs_id``: ``uuid:`` + the UUID whose ``/dev/disk/by-uuid`` link's device number equals the directory's
  ``st_dev``, else ``dev:<major>:<minor>`` of ``st_dev`` (on btrfs a subvolume's ``st_dev`` is anonymous and matches no
  link, so both sides get ``dev:`` and agree);
* ``store_ino`` and ``store_btime``: from ``statx`` with ``STATX_BTIME`` (Python has no birth time on Linux), the
  birth time in nanoseconds, or None where the file system reports none;
* ``store_fs_path``: the directory's path within its file system. Root takes the containing mount's root field joined
  with the real path relative to its mount point; the issuer takes its bind's root field, which the kernel keeps
  current (a rename shows at once; a removal ends in ``//deleted``).

Kernel text (``/proc/self/mountinfo``) is read as bytes and split on ``b"\\n"`` only; every record is checked against
its fixed format, and one that does not parse fails the whole read (:class:`IdentityUnavailable`), never skipped.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MOUNTINFO = Path("/proc/self/mountinfo")
BY_UUID = Path("/dev/disk/by-uuid")
_UUID = re.compile(r"[0-9A-Za-z-]{1,64}")  # the wire's store_fs_id pattern for a UUID
_OCTAL = re.compile(rb"\\([0-7]{3})")
_DEV = re.compile(rb"([0-9]+):([0-9]+)")
_NUM = re.compile(rb"[0-9]+")


class IdentityUnavailable(OSError):
    """The identity could not be read (no statx, an unparseable mount table, no mount at the view): the check could
    not run, which is not evidence of a replacement (the issuer reads ``STORE_UNREADABLE``, which does not latch)."""


@dataclass(frozen=True)
class Mount:
    """One record of ``/proc/self/mountinfo``: its device, its root field and mount point (both decoded), and type."""

    mount_id: int
    major: int
    minor: int
    root: str
    mount_point: str
    fstype: str


@dataclass(frozen=True)
class Identity:
    fs_id: str
    ino: int
    btime: int | None
    fs_path: str

    def as_anchor_fields(self) -> dict[str, object]:
        return {"store_fs_id": self.fs_id, "store_ino": self.ino, "store_btime": self.btime,
                "store_fs_path": self.fs_path}


def decode_field(raw: bytes) -> str:
    """A mountinfo path field with its ``\\ooo`` octal escapes decoded (space, tab, newline and backslash), as UTF-8.
    A field that is not UTF-8 after decoding is refused: no anchor names such a path."""
    return _OCTAL.sub(lambda m: bytes([int(m.group(1), 8)]), raw).decode("utf-8")


def parse_mountinfo(raw: bytes) -> list[Mount]:
    """Every record, in the kernel's order. Format (proc(5)): ``id parent major:minor root mount-point options
    [optional fields...] - fstype source super-options``. Any record that does not match fails the whole parse."""
    out = []
    lines = raw.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    for n, line in enumerate(lines, 1):
        f = line.split(b" ")
        try:
            sep = f.index(b"-", 6)
        except ValueError:
            raise IdentityUnavailable(f"mountinfo record {n} has no separator") from None
        dev = _DEV.fullmatch(f[2])
        if (len(f) != sep + 4 or not _NUM.fullmatch(f[0]) or not _NUM.fullmatch(f[1]) or dev is None
                or not f[3].startswith(b"/") or not f[4].startswith(b"/") or not f[sep + 1]):
            raise IdentityUnavailable(f"mountinfo record {n} does not have mountinfo's fixed format")
        try:
            out.append(Mount(int(f[0]), int(dev.group(1)), int(dev.group(2)), decode_field(f[3]), decode_field(f[4]),
                             f[sep + 1].decode("ascii")))
        except UnicodeDecodeError:
            raise IdentityUnavailable(f"mountinfo record {n} has a field that is not text") from None
    return out


def read_mountinfo(path: Path = MOUNTINFO) -> list[Mount]:
    try:
        return parse_mountinfo(path.read_bytes())
    except OSError as exc:
        raise IdentityUnavailable(f"{path}: {exc.strerror or exc}") from None


def mount_at(mounts: list[Mount], mount_point: str) -> Mount:
    """The mount at ``mount_point`` that path resolution reaches: the last one listed there (a mount stacked on
    another is listed after it)."""
    found = [m for m in mounts if m.mount_point == mount_point]
    if not found:
        raise IdentityUnavailable(f"nothing is mounted at {mount_point}")
    return found[-1]


def containing_mount(mounts: list[Mount], real_path: str) -> Mount:
    """The mount whose mount point is the longest whole-component prefix of ``real_path`` (the last listed at it)."""
    def covers(mp: str) -> bool:
        return mp == "/" or real_path == mp or real_path.startswith(mp + "/")

    best = None
    for m in mounts:
        if covers(m.mount_point) and (best is None or len(m.mount_point) >= len(best.mount_point)):
            best = m
    if best is None:
        raise IdentityUnavailable(f"no mount contains {real_path}")
    return best


def within_fs(mount: Mount, real_path: str) -> str:
    """WIS-11's ``store_fs_path``: the mount's root field joined with ``real_path`` relative to its mount point."""
    rel = real_path[len(mount.mount_point):].lstrip("/") if mount.mount_point != "/" else real_path.lstrip("/")
    if not rel:
        return mount.root
    return (mount.root.rstrip("/") + "/" + rel) if mount.root != "/" else "/" + rel


# ---------------------------------------------------------------------------------------------- the device rule

def by_uuid_links(directory: Path = BY_UUID) -> list[tuple[str, int, int]]:
    """``(uuid, major, minor)`` for each link in ``/dev/disk/by-uuid`` that names a block device, sorted by UUID. A
    name outside the wire's UUID pattern is left out, by both parties alike."""
    out = []
    try:
        names = sorted(os.listdir(directory))
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise IdentityUnavailable(f"{directory}: {exc.strerror or exc}") from None
    for name in names:
        if not _UUID.fullmatch(name):
            continue
        try:
            st = os.stat(directory / name)
        except OSError:
            continue  # a dangling link names no device
        if (st.st_mode & 0o170000) == 0o060000:  # S_IFBLK
            out.append((name, os.major(st.st_rdev), os.minor(st.st_rdev)))
    return out


def fs_id(major: int, minor: int, links: list[tuple[str, int, int]]) -> str:
    """WIS-11's candidate rule: the UUID whose link's device is ``major:minor``, else ``dev:<major>:<minor>``."""
    for uuid, lmaj, lmin in links:
        if (lmaj, lmin) == (major, minor):
            return "uuid:" + uuid
    return f"dev:{major}:{minor}"


# ---------------------------------------------------------------------------------------------- statx

AT_FDCWD = -100
AT_SYMLINK_NOFOLLOW = 0x100
STATX_BASIC_STATS = 0x7FF
STATX_BTIME = 0x800


class _Timestamp(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_int64), ("tv_nsec", ctypes.c_uint32), ("reserved", ctypes.c_int32)]


class _Statx(ctypes.Structure):
    """``struct statx`` (linux/stat.h)."""

    _fields_ = [("stx_mask", ctypes.c_uint32), ("stx_blksize", ctypes.c_uint32), ("stx_attributes", ctypes.c_uint64),
                ("stx_nlink", ctypes.c_uint32), ("stx_uid", ctypes.c_uint32), ("stx_gid", ctypes.c_uint32),
                ("stx_mode", ctypes.c_uint16), ("spare0", ctypes.c_uint16), ("stx_ino", ctypes.c_uint64),
                ("stx_size", ctypes.c_uint64), ("stx_blocks", ctypes.c_uint64),
                ("stx_attributes_mask", ctypes.c_uint64), ("stx_atime", _Timestamp), ("stx_btime", _Timestamp),
                ("stx_ctime", _Timestamp), ("stx_mtime", _Timestamp), ("stx_rdev_major", ctypes.c_uint32),
                ("stx_rdev_minor", ctypes.c_uint32), ("stx_dev_major", ctypes.c_uint32),
                ("stx_dev_minor", ctypes.c_uint32), ("spare2", ctypes.c_uint64 * 14)]


@dataclass(frozen=True)
class Stat:
    major: int
    minor: int
    ino: int
    btime: int | None
    uid: int


def statx(path: str) -> Stat:
    """The directory's device, inode number, birth time (ns, or None) and owner, by ``statx(2)`` through glibc
    (2.28 and later; Rocky 8 has 2.28). Not following a final symbolic link."""
    if not sys.platform.startswith("linux"):
        raise IdentityUnavailable("statx is Linux's")
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    fn = getattr(libc, "statx", None)
    if fn is None:
        raise IdentityUnavailable("this C library has no statx")
    fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_uint, ctypes.POINTER(_Statx)]
    fn.restype = ctypes.c_int
    buf = _Statx()
    if fn(AT_FDCWD, os.fsencode(path), AT_SYMLINK_NOFOLLOW, STATX_BASIC_STATS | STATX_BTIME, ctypes.byref(buf)) != 0:
        err = ctypes.get_errno()
        raise IdentityUnavailable(err, f"statx {path}: {os.strerror(err)}")
    btime = (buf.stx_btime.tv_sec * 1_000_000_000 + buf.stx_btime.tv_nsec) if buf.stx_mask & STATX_BTIME else None
    return Stat(buf.stx_dev_major, buf.stx_dev_minor, buf.stx_ino, btime, buf.stx_uid)


def identity_of(st: Stat, fs_path: str, links: list[tuple[str, int, int]]) -> Identity:
    """The one rule both parties apply to what each sees."""
    return Identity(fs_id(st.major, st.minor, links), st.ino, st.btime, fs_path)


def root_identity(store_path: str) -> Identity:
    """Root, at the store's path on the host (WIS-11): its real path, the mount that contains it, and the rule."""
    real = os.path.realpath(store_path)
    st = statx(real)
    mount = containing_mount(read_mountinfo(), real)
    if (mount.major, mount.minor) != (st.major, st.minor):
        raise IdentityUnavailable(f"the mount at {mount.mount_point} is {mount.major}:{mount.minor}, but {real} is "
                                  f"on {st.major}:{st.minor}")
    return identity_of(st, within_fs(mount, real), by_uuid_links())


def view_identity(view_path: str) -> tuple[Identity, int]:
    """The issuer, inside its view (WIS-02's first two rows): its bind's root field, the rule on what ``statx`` shows
    of the bound directory, and the directory's owner (the operator: :mod:`aew_wis.service`)."""
    st = statx(view_path)
    mount = mount_at(read_mountinfo(), view_path)
    return identity_of(st, mount.root, by_uuid_links()), st.uid
