"""The chat between the scripted operator and the scripted Lead: what a TUI's input box and transcript carry.

Each side writes its messages as numbered files in its own sequence (``operator-NNNN.json``, ``lead-NNNN.json``),
each written whole (a temporary file, then a rename), and reads the other side's in order. Ordering is by those
files, never by time: a reader waits for the next file to exist. Every wait is bounded, and gives up early when
``gone`` says the other side has ended (a Lead session that exited, or a test that finished).

A read that fails (an ``OSError``, such as a sharing violation on Windows while another process holds the file just
renamed into place, or a ``ValueError`` from a file read whole but not parseable) is never fatal and never loses the
message: the reader stays on that message, reports the error to ``on_error``, and tries it again on its next poll,
within the same bound (review of #213, G2).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import flight_recorder

POLL_S = 0.05
SIDES = ("operator", "lead")


class Gone(Exception):
    """The other side ended (or the bound elapsed) before its next message."""


class Mailbox:
    def __init__(self, directory: Path, side: str,
                 on_error: Callable[[Path, BaseException], None] | None = None) -> None:
        if side not in SIDES:
            raise ValueError(side)
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.side = side
        self.other = SIDES[1 - SIDES.index(side)]
        self.sent = len(list(self.dir.glob(f"{side}-*.json")))  # a reopened session continues the same chat
        self.read = 0
        self.on_error = on_error
        self.errors: list[str] = []  # every failed read, in order (also reported to ``on_error``)

    def send(self, message: dict[str, Any]) -> int:
        n = self.sent
        target = self.dir / f"{self.side}-{n:04d}.json"
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps({"n": n, "from": self.side, **message}), encoding="utf-8")
            os.replace(tmp, target)
        except OSError as exc:  # in the flight recorder with its codes, then raised as before
            flight_recorder.io("replace", target, exc, side=self.side)
            raise
        flight_recorder.io("replace", target, side=self.side)
        self.sent += 1
        return n

    def peek(self) -> dict[str, Any] | None:
        path = self.dir / f"{self.other}-{self.read:04d}.json"
        if not path.exists():
            return None
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # retried on the next poll; the message is never skipped
            self.errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            flight_recorder.io("read", path, exc, side=self.side)
            if self.on_error is not None:
                self.on_error(path, exc)
            return None
        self.read += 1
        flight_recorder.io("read", path, side=self.side)
        return found

    def skip_to_end(self) -> None:
        """Mark every message the other side has written so far as read (a reopened session starts fresh)."""
        self.read = len(list(self.dir.glob(f"{self.other}-*.json")))

    def receive(self, timeout: float, gone: Callable[[], bool] | None = None) -> dict[str, Any]:
        """The other side's next message, within ``timeout`` (a bound declared by the caller, ``bounds.py``). How the
        wait ended goes to the flight recorder: an autopsy then shows where each side was waiting."""
        started = time.monotonic()
        deadline = started + timeout
        name = f"chat.{self.side}.receive"
        while True:
            found = self.peek()
            if found is not None:
                flight_recorder.wait(name, timeout, "ok", time.monotonic() - started, n=self.read - 1)
                return found
            if gone is not None and gone():
                found = self.peek()  # written just before it ended
                if found is not None:
                    return found
                flight_recorder.wait(name, timeout, "gone", time.monotonic() - started, n=self.read)
                raise Gone(f"the {self.other} ended before its next message")
            if time.monotonic() > deadline:
                flight_recorder.wait(name, timeout, "timeout", time.monotonic() - started, n=self.read)
                raise Gone(f"no message from the {self.other} within {timeout:.0f}s")
            time.sleep(POLL_S)
