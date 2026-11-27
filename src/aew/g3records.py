"""The G3 client's per-host approval records (A-44 BOY-05.a, BOY-05.c, BOY-05.e; register E101).

One JSON file per approval that ``aew g3 request`` starts, in :func:`aew.g3client.approval_records_dir`, outside every
project's store and outside every contained launch's writable binds. Only the client that started an approval writes
its record (:class:`Writer`): at the start, after each of its reads of G3, and at its exit; and each of its writes
prunes every record whose display window has passed (:func:`prune`). Every other reader (the attention module, so the
dashboard and ``aew status``) only reads (:func:`read_all`). The record grants nothing: it is a display source, and
the decision stays in AEW approvals, with the PIN (BOY-00).

A record holds :data:`FIELDS` and nothing else: never a rendering line, a typed value or a consent record (G3-03).
Its action names are the ``g3:action:`` TEMPLATE lines of G3's own reply, never the client's words.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aew import g3client as C

SCHEMA = "aew/g3-approval-record/v1"
SUFFIX = ".json"
# Every field a record holds (BOY-05.a); a reader ignores a record that holds any other
FIELDS = frozenset({"schema", "approval_ref", "expires_at", "actions", "starter_role", "project", "started_at",
                    "client", "from_request", "state", "read_at", "g3_answered_at", "outcome", "exited_at"})
# What the client last read of G3: the wire's states, its 404, or no answer (none, or a 503)
PENDING, APPROVED, DECLINED, EXPIRED = "PENDING", "APPROVED", "DECLINED", "EXPIRED"
NOT_FOUND, NO_ANSWER = "NOT_FOUND", "NO_ANSWER"
READ_STATES = (PENDING, APPROVED, DECLINED, EXPIRED, NOT_FOUND, NO_ANSWER)
# How the client's wait ended, written at its exit (null while it waits, or when it ended for another reason)
OUTCOMES = ("approved_submitted", "approved_not_submitted", "declined", "expired", "not_found", "unanswered")
ACTION_PREFIX = "g3:action:"
# The client is the operator's alone (custody_ops.refuse_kept_out), so this is all it can claim; it is shown labelled
# as the client's own claim (BOY-01)
STARTER_ROLE = "operator"
OUTSIDE = None  # the project label of an approval started outside any project


def window_s() -> int:
    """How long past its expiry a record stays in view, a final one as a recent outcome: G3-06's consent validity
    ceiling, the register of weaker contexts' window (BOY-05.c; at most 25 minutes after the start in all)."""
    from aew.harness.weaker_register import WINDOW_S

    return WINDOW_S


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def actions(pending: dict[str, Any]) -> list[str]:
    """The action names of G3's own reply: its TEMPLATE lines' ``g3:action:`` ids, in order, each once."""
    out: list[str] = []
    for line in pending.get("rendering") or []:
        if not isinstance(line, dict) or (line.get("source") or {}).get("kind") != "TEMPLATE":
            continue
        tid = line.get("template_id")
        if isinstance(tid, str) and tid.startswith(ACTION_PREFIX) and tid[len(ACTION_PREFIX):] not in out:
            out.append(tid[len(ACTION_PREFIX):])
    return out


def project_label(start: Path) -> str | None:
    """The project the client finds by walking up from ``start``, as every project command does, or None outside one.
    A label only: it grants no scope (BOY-05.a)."""
    from aew.engine.base import Kernel
    from aew.errors import AEWError
    from aew.knowledge.manifest import MANIFEST
    from aew.util import read_yaml

    try:
        _, aew_root = Kernel.locate(start)
        return str(read_yaml(aew_root / MANIFEST)["project"]["id"])
    except (AEWError, OSError, KeyError, TypeError, ValueError):
        return OUTSIDE


def _name(ref: str) -> str:
    """The record's file name: the ref's characters a file name may hold (G3's Ref has ':' and '/')."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in ref) + SUFFIX


def prune(directory: Path, now: datetime) -> list[str]:
    """Remove every record whose expiry plus :func:`window_s` has passed, and every one that cannot be read and is
    older than that window by its modification time: the client's own housekeeping, at each of its writes
    (BOY-05.c). Returns the names removed."""
    gone = []
    if not directory.is_dir():
        return gone
    limit = timedelta(seconds=window_s())
    for path in sorted(directory.glob("*" + SUFFIX)):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            expiry = _parse(data.get("expires_at")) if isinstance(data, dict) else None
        except (OSError, ValueError):
            expiry = None
        if expiry is None:
            try:
                expiry = datetime.fromtimestamp(path.stat().st_mtime, UTC) + timedelta(seconds=C.EXPIRY_CEILING_S)
            except OSError:
                continue
        if now > expiry + limit:
            path.unlink(missing_ok=True)
            gone.append(path.name)
    return gone


class Writer:
    """The one writer of one approval's record: the client that started the approval. Each write is atomic (a
    temporary file renamed over the record), so a reader never sees a torn record, and prunes what has left the
    view."""

    def __init__(self, pending: dict[str, Any], *, project: str | None, directory: Path | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC), pid: int | None = None) -> None:
        from aew.harness import procs

        self.directory = directory or C.approval_records_dir()
        self.now = now
        pid = os.getpid() if pid is None else pid
        started = _iso(now())
        self.record: dict[str, Any] = {
            "schema": SCHEMA, "approval_ref": str(pending["approval_ref"]),
            "expires_at": _iso(C.expires_at(pending)), "actions": actions(pending), "starter_role": STARTER_ROLE,
            "project": project, "started_at": started, "client": {"pid": pid, "start_id": procs.start_id(pid)},
            "from_request": None,  # reserved (BOY-B7): nothing fills it yet
            "state": str(pending.get("state") or PENDING), "read_at": started, "g3_answered_at": started,
            "outcome": None, "exited_at": None}
        self.path = self.directory / _name(self.record["approval_ref"])
        self.failed: str | None = None
        self._write()

    def _write(self) -> None:
        """Write the record, pruning first. A write that fails is kept as :attr:`failed` and never stops the client:
        the record only shows the wait, and the confirmer lists the approval whatever happens here."""
        from aew.util import atomic_write

        try:
            if not self.directory.is_dir():
                self.directory.mkdir(parents=True, exist_ok=True)
                if sys.platform != "win32":  # the operator's own account only; files are 0600 already (mkstemp)
                    os.chmod(self.directory, 0o700)
            prune(self.directory, self.now())
            atomic_write(self.path, json.dumps(self.record, sort_keys=True) + "\n")
            self.failed = None
        except OSError as exc:
            self.failed = f"{type(exc).__name__}: {exc.strerror or exc}"

    def read(self, state: str) -> None:
        """After each of the client's reads of G3: what it read (:data:`READ_STATES`), and when that read completed;
        the time G3 last answered moves only when it answered."""
        at = _iso(self.now())
        self.record.update(state=state, read_at=at)
        if state != NO_ANSWER:
            self.record["g3_answered_at"] = at
        self._write()

    def finish(self, outcome: str | None) -> None:
        """At the client's exit: how its wait ended (:data:`OUTCOMES`), or None when it ended another way."""
        self.record.update(outcome=outcome, exited_at=_iso(self.now()))
        self._write()


@dataclass(frozen=True)
class Found:
    """One file of the directory as a reader found it: its record, or None when it cannot be read as one."""

    name: str
    record: dict[str, Any] | None


def valid(data: Any) -> bool:
    """A record of :data:`SCHEMA` holding exactly its fields, with the values a reader relies on."""
    return (isinstance(data, dict) and set(data) == FIELDS and data["schema"] == SCHEMA
            and isinstance(data["approval_ref"], str) and _parse(data["expires_at"]) is not None
            and _parse(data["started_at"]) is not None and _parse(data["read_at"]) is not None
            and isinstance(data["actions"], list) and all(isinstance(a, str) for a in data["actions"])
            and data["state"] in READ_STATES and data["outcome"] in (None, *OUTCOMES)
            and isinstance(data["client"], dict) and (data["project"] is None or isinstance(data["project"], str)))


def read_all(directory: Path | None = None) -> list[Found]:
    """Every record in the directory, read only: never created, changed or pruned here."""
    directory = directory or C.approval_records_dir()
    out = []
    try:
        paths = sorted(directory.glob("*" + SUFFIX)) if directory.is_dir() else []
    except OSError:
        return [Found(directory.name, None)]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        out.append(Found(path.name, data if valid(data) else None))
    return out


def parse_time(value: Any) -> datetime | None:
    """A record's time, or None when it is not one."""
    return _parse(value)
