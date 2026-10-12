"""The chat between the scripted operator and the scripted Lead: what a TUI's input box and transcript carry.

Each side writes its messages as numbered files in its own sequence (``operator-NNNN.json``, ``lead-NNNN.json``),
each written whole (a temporary file, then a rename), and reads the other side's in order. Ordering is by those
files, never by time: a reader waits for the next file to exist. Every wait is bounded, and gives up early when
``gone`` says the other side has ended (a Lead session that exited, or a test that finished).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

POLL_S = 0.05
SIDES = ("operator", "lead")


class Gone(Exception):
    """The other side ended (or the bound elapsed) before its next message."""


class Mailbox:
    def __init__(self, directory: Path, side: str) -> None:
        if side not in SIDES:
            raise ValueError(side)
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.side = side
        self.other = SIDES[1 - SIDES.index(side)]
        self.sent = len(list(self.dir.glob(f"{side}-*.json")))  # a reopened session continues the same chat
        self.read = 0

    def send(self, message: dict[str, Any]) -> int:
        n = self.sent
        target = self.dir / f"{self.side}-{n:04d}.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({"n": n, "from": self.side, **message}), encoding="utf-8")
        os.replace(tmp, target)
        self.sent += 1
        return n

    def peek(self) -> dict[str, Any] | None:
        path = self.dir / f"{self.other}-{self.read:04d}.json"
        if not path.exists():
            return None
        self.read += 1
        return json.loads(path.read_text(encoding="utf-8"))

    def skip_to_end(self) -> None:
        """Mark every message the other side has written so far as read (a reopened session starts fresh)."""
        self.read = len(list(self.dir.glob(f"{self.other}-*.json")))

    def receive(self, timeout: float, gone: Callable[[], bool] | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            found = self.peek()
            if found is not None:
                return found
            if gone is not None and gone():
                found = self.peek()  # written just before it ended
                if found is not None:
                    return found
                raise Gone(f"the {self.other} ended before its next message")
            if time.monotonic() > deadline:
                raise Gone(f"no message from the {self.other} within {timeout:.0f}s")
            time.sleep(POLL_S)
