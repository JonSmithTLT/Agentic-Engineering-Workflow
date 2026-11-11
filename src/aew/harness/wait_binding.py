"""Foreground-call lifetime for a worker wait (F9-A amendment 1 A3).

The adapter owns the lock: update and snapshot/valid checks run under that same lock. No process ancestry, model
text, digest or run-directory file can establish this binding. Stream loss invalidates every prior snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Qualified Linux 2.2.6: 119.98 s default, conservatively measured maximum 88 s (messaging.shell_timeout).
# Windows runtime remains NOT RUN; this constant does not enable an unsupported adapter's binding.
MAX_WAIT_S = 88
CALL_GRACE_S = 2.0


@dataclass(frozen=True)
class Binding:
    epoch: int
    step: str
    calls: tuple[tuple[str, int], ...]


class Calls:
    def __init__(self) -> None:
        self.epoch = 0
        self.step: str | None = None
        self.calls: dict[str, int] = {}
        self.serial = 0

    def clear(self) -> None:
        self.epoch += 1
        self.step = None
        self.calls.clear()

    def event(self, kind: str, data: dict[str, Any], tool: str | None) -> None:
        step = data.get("assistantMessageID")
        call = data.get("id")
        if kind == "session.step.started":
            if step != self.step or not isinstance(step, str) or not step:
                self.clear()
                self.step = step if isinstance(step, str) and step else None
        elif kind in ("session.step.ended", "session.step.failed", "session.execution.succeeded",
                      "session.execution.failed", "session.execution.interrupted"):
            self.clear()  # even a mismatched end is a backstop: steps in a session are sequential
        elif kind == "session.tool.called" and tool in ("bash", "shell"):
            if self.step is not None and step == self.step and isinstance(call, str) and call:
                self.serial += 1
                self.calls[call] = self.serial
        elif kind in ("session.tool.success", "session.tool.failed") and isinstance(call, str):
            self.calls.pop(call, None)

    def snapshot(self) -> Binding | None:
        if self.step is None or not self.calls:
            return None
        return Binding(self.epoch, self.step, tuple(sorted(self.calls.items())))

    def valid(self, binding: Binding) -> bool:
        return (binding.epoch == self.epoch and binding.step == self.step and bool(binding.calls)
                and all(self.calls.get(call) == serial for call, serial in binding.calls))
