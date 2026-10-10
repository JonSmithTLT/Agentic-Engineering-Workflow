"""The event spool (M4-E plan v3 §2.7, §2.8; amendment 1, E7a): events the operator endpoint cannot derive from control
state, appended by the processes that see them.

**Writers.** ``.aew/local/events/<writer>.jsonl``, one file per writer, so no two processes append to one file: each
run's supervisor (``run-<run id>``: ``hard_deadline`` and ``launch_failed``) and, from M4-E E7b, the broker
(``broker``: the loop's events). An append never fails its writer (:func:`append`: a supervisor ends its run whatever
the spool met). A file is bounded like the typed-tool log: past :data:`MAX_BYTES` it is rotated to ``<writer>.1.jsonl``
(one rotated file is kept).

**Trust (amendment 1, m9).** A spool line is untrusted data: the spool is under ``.aew/local/``, which a same-uid
process (an uncontained run among them) can write. The reader (:class:`Reader`, run by the endpoint's watcher):

- drops and counts a line over :data:`MAX_LINE` bytes;
- validates each line against a closed per-writer event enum (``schemas/spool-event.schema.json``; the writer is the
  file's name, never what the line claims), and a run writer's ``subject`` must be its own run;
- caps every string at :data:`MAX_STRING` characters with control characters removed (:func:`clean`);
- reads at most :data:`LINES_PER_PASS` new lines per file per pass and scans at most :data:`FILES_PER_PASS` files per
  pass, oldest unread first;
- labels every event it yields ``authenticated: false`` (the watcher's payload). The rate bound, ten deliveries per
  writer per minute, is the watcher's.

A run's file is deleted once the run is terminal and every line in it is delivered or dropped (the watcher, through
:meth:`Reader.retire`).
"""

from __future__ import annotations

import errno
import json
import logging
import os
import re
import stat
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aew import errors
from aew.util import sha256_bytes, utc_now

SPOOL_REL = "local/events"
SCHEMA = "aew/spool-event/v1"
MAX_LINE = 4096  # bytes, newline excluded: a longer line is dropped and counted
MAX_STRING = 512  # characters kept of any string a line carries
MAX_BYTES = 256 * 1024  # one file; a run writes a handful of lines
LINES_PER_PASS = 256
FILES_PER_PASS = 64
RUN_PREFIX = "run-"
BROKER = "broker"
WRITER_RE = re.compile(r"^(broker|run-R-[A-Za-z0-9_-]{1,160})$")  # no dot: ``.1`` is the rotated suffix
_FILE_RE = re.compile(r"^(?P<writer>broker|run-R-[A-Za-z0-9_-]{1,160})(?P<rotated>\.1)?\.jsonl$")
NEWLINE, CARRIAGE_RETURN = b"\n", b"\r"
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ‪-‮⁦-⁩]")

log = logging.getLogger(__name__)
_lock = threading.Lock()  # a supervisor appends from more than one thread


def spool_dir(aew_root: Path) -> Path:
    return Path(aew_root) / SPOOL_REL


def run_writer(run: str) -> str:
    return RUN_PREFIX + run


def writer_kind(writer: str) -> str:
    return "broker" if writer == BROKER else "run"


def file_of(aew_root: Path, writer: str, *, rotated: bool = False) -> Path:
    return spool_dir(aew_root) / f"{writer}{'.1' if rotated else ''}.jsonl"


def clean(value: Any, limit: int = MAX_STRING) -> str | None:
    """A string from an untrusted line: control and bidi-override characters removed, cut to ``limit``."""
    if value is None:
        return None
    return _CONTROL.sub("", str(value))[:limit]


# ---------------------------------------------------------------------------------------------- the writer side


def append(aew_root: Path, writer: str, event: str, *, subject: str, reason: str | None,
           ref: str | None = None) -> None:
    """Append one event line for ``writer``. Never raises: the spool feeds notification, and a supervisor ends its run
    whatever it met; what is lost is logged."""
    try:
        if not WRITER_RE.match(writer):
            raise ValueError(f"not a spool writer name: {writer!r}")
        text = _encode(event, subject=subject, reason=reason, ref=ref)
        target = file_of(aew_root, writer)
        with _lock:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                if target.stat().st_size + len(text) > MAX_BYTES:
                    os.replace(target, file_of(aew_root, writer, rotated=True))
            except FileNotFoundError:
                pass
            fd = _open_append(target)
            with os.fdopen(fd, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
    except Exception as exc:  # noqa: BLE001  the spool never fails its writer
        log.warning("the event spool dropped %s for %s: %s: %s", event, writer, type(exc).__name__, exc)


def _encode(event: str, *, subject: str, reason: str | None, ref: str | None) -> str:
    """The line, bounded by its encoded length: JSON escapes a character outside ASCII as ``\\uXXXX`` (twelve bytes
    for one outside the BMP), so a character cap alone does not bound it (review of PR #184). The reason, then the
    reference, is shortened until the line, newline excluded, is at most :data:`MAX_LINE` bytes, so the reader never
    drops a line a supervisor wrote."""
    reason_text = None if reason is None else str(reason)[:MAX_STRING]
    ref_text = None if ref is None else str(ref)[:MAX_STRING]
    at = utc_now()
    while True:
        line = {"schema": SCHEMA, "event": event, "at": at, "subject": str(subject)[:200], "reason": reason_text,
                "ref": ref_text}
        text = json.dumps(line, sort_keys=True, separators=(",", ":"))
        if len(text.encode("utf-8")) <= MAX_LINE:
            return text + "\n"
        if reason_text:
            reason_text = reason_text[:len(reason_text) // 2]
        elif ref_text:
            ref_text = ref_text[:len(ref_text) // 2]
        else:
            raise ValueError("a spool line cannot be bounded")  # the subject alone is capped well under MAX_LINE


def _open_append(path: Path) -> int:
    """A descriptor appending to a regular file, never through a link and never blocking on a FIFO (the spool is
    writable by the run's user, as the run directory is: ``runlog._open_append``)."""
    if sys.platform != "win32":
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o644)
    else:
        try:
            if not stat.S_ISREG(os.lstat(path).st_mode):
                raise OSError(errno.EINVAL, "not a regular file", str(path))
        except FileNotFoundError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_BINARY, 0o644)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd


# ---------------------------------------------------------------------------------------------- the reader side


@dataclass
class Line:
    """One valid spool line: its writer (from the file name), its event and cleaned fields, and its occurrence key
    (the digest of the line's bytes: a line is one occurrence, so a repeated identical line is the same one)."""

    writer: str
    event: str
    subject: str | None
    reason: str | None
    ref: str | None
    at: str | None
    key: str
    raw: str  # the line as written (at most MAX_LINE bytes): what is saved while its event is outstanding


@dataclass
class Pass:
    lines: list[Line] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)  # oversize, invalid
    more: bool = False  # a file still has unread lines


def _drop(out: Pass, why: str) -> None:
    out.dropped[why] = out.dropped.get(why, 0) + 1


class Reader:
    """Reads new spool lines from ``cursors`` (``{writer: {"offset": n, "head": digest}}``, the watcher's, persisted
    by it), bounded per pass. ``head`` is the digest of a file's first line, so a rotation is noticed."""

    def __init__(self, aew_root: Path, cursors: dict[str, dict[str, Any]]) -> None:
        self.aew_root = Path(aew_root)
        self.cursors = cursors

    def writers(self) -> list[str]:
        """Writers with a spool file, oldest file first."""
        found: dict[str, float] = {}
        try:
            entries = list(os.scandir(spool_dir(self.aew_root)))
        except OSError:
            return []
        for entry in entries:
            m = _FILE_RE.match(entry.name)
            if not m:
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            writer = m.group("writer")
            found[writer] = min(found.get(writer, info.st_mtime), info.st_mtime)
        return sorted(found, key=lambda w: (found[w], w))

    def unread(self, writer: str) -> bool:
        cursor = self.cursors.get(writer) or {}
        current = file_of(self.aew_root, writer)
        try:
            size = os.lstat(current).st_size
        except OSError:
            size = 0
        return size != cursor.get("offset", 0) or _head(current) != cursor.get("head")

    def scan(self) -> Pass:
        out = Pass()
        pending = [w for w in self.writers() if self.unread(w)]
        if len(pending) > FILES_PER_PASS:
            out.more = True
        for writer in pending[:FILES_PER_PASS]:
            if self._read_writer(writer, out):
                out.more = True
        return out

    def _read_writer(self, writer: str, out: Pass) -> bool:
        """Read up to :data:`LINES_PER_PASS` new lines of ``writer``; whether lines remain unread. The cursor's
        ``skip`` is set while it is inside an oversize line, whose rest is skipped, never parsed as a line."""
        cursor = self.cursors.setdefault(writer, {"offset": 0, "head": None})
        current, rotated = file_of(self.aew_root, writer), file_of(self.aew_root, writer, rotated=True)
        budget = [LINES_PER_PASS]
        head = _head(current)
        if cursor.get("head") is not None and head != cursor["head"]:
            # The file was rotated (or replaced) since the last pass: finish the rotated copy if it is the one the
            # cursor was reading, then start the new file from its beginning.
            if _head(rotated) == cursor["head"]:
                pos, more, skip = self._read_file(rotated, writer, cursor["offset"], bool(cursor.get("skip")),
                                                  budget, out)
                if more:
                    cursor.update(offset=pos, skip=skip)
                    return True
            cursor.update(offset=0, head=head, skip=False)
        elif cursor.get("head") is None:
            cursor.update(offset=0, head=head, skip=False)
        cursor["offset"], more, cursor["skip"] = self._read_file(current, writer, cursor["offset"],
                                                                  bool(cursor.get("skip")), budget, out)
        return more

    def _read_file(self, path: Path, writer: str, offset: int, skip: bool, budget: list[int],
                   out: Pass) -> tuple[int, bool, bool]:
        """Consume complete lines from ``offset`` while the budget lasts: ``(the offset to resume from, whether
        lines are left, whether it stopped inside an oversize line)``. A last line with no newline yet is still being
        written and is left for the next pass. A line over :data:`MAX_LINE` is dropped and counted once; it is
        consumed a chunk at a time, each chunk spending budget, so a pass stays bounded however long the line is."""
        try:
            fd = _open_read(path)
        except OSError:
            return offset, False, skip
        with os.fdopen(fd, "rb") as fh:
            fh.seek(offset)
            pos = offset
            while True:
                if budget[0] <= 0:
                    return pos, bool(fh.read(1)), skip
                raw = fh.readline(MAX_LINE + 2)
                if not raw:
                    return pos, False, skip
                complete = raw.endswith(NEWLINE)
                if not complete and len(raw) <= MAX_LINE and not skip:
                    return pos, False, skip  # a line still being written: read it next pass
                pos += len(raw)
                budget[0] -= 1
                if skip:  # the rest of an oversize line, already counted
                    skip = not complete
                    continue
                body = raw[:-1].rstrip(CARRIAGE_RETURN) if complete else raw
                if len(body) > MAX_LINE or not complete:
                    _drop(out, "oversize")
                    skip = not complete
                    continue
                if not body.strip():
                    continue
                line = parse_line(writer, body)
                if line is None:
                    _drop(out, "invalid")
                else:
                    out.lines.append(line)

    def retire(self, writer: str) -> None:
        """Delete a writer's files and forget its cursor (a terminal run whose every line is delivered or dropped)."""
        for p in (file_of(self.aew_root, writer), file_of(self.aew_root, writer, rotated=True)):
            try:
                if stat.S_ISREG(os.lstat(p).st_mode):
                    p.unlink()
            except OSError:
                pass
        self.cursors.pop(writer, None)


def parse_line(writer: str, body: bytes) -> Line | None:
    """One spool line's validation, the only one there is: a line read from a spool file, and one saved while its
    event was outstanding and offered again after a restart, both pass here (review of PR #184). ``None`` for a line
    that is not valid for ``writer``: its size, its kind's closed event enum, a run speaking only of itself; the
    strings it yields are cleaned and capped, and its key is the digest of its bytes, so it cannot be chosen."""
    from aew import schemas

    if not WRITER_RE.match(writer) or len(body) > MAX_LINE:
        return None
    try:
        data = json.loads(body.decode("utf-8"))
        schemas.validate_def("spool-event", writer_kind(writer), data, source=f"spool {writer}")
    except (ValueError, UnicodeDecodeError, RecursionError, errors.ValidationFailed):
        return None
    if writer_kind(writer) == "run" and data.get("subject") != writer[len(RUN_PREFIX):]:
        return None  # a run's supervisor speaks only of its own run
    return Line(writer=writer, event=data["event"], subject=clean(data.get("subject")),
                reason=clean(data.get("reason")), ref=clean(data.get("ref")), at=clean(data.get("at"), 40),
                key=f"spool:{writer}:{sha256_bytes(body)[:32]}", raw=body.decode("utf-8"))


def _open_read(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if sys.platform != "win32":
        flags |= os.O_NOFOLLOW | os.O_NONBLOCK
    elif not stat.S_ISREG(os.lstat(path).st_mode):
        raise OSError(errno.EINVAL, "not a regular file", str(path))
    fd = os.open(path, flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(errno.EINVAL, "not a regular file", str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _head(path: Path) -> str | None:
    """The digest of a file's first line (at most :data:`MAX_LINE` bytes of it), or ``None``."""
    try:
        fd = _open_read(path)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        first = fh.readline(MAX_LINE + 2)
    return sha256_bytes(first) if first else None
