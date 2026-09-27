"""The narrow harness adapter contract (ADR-0009).

One adapter instance serves one run, inside that run's supervisor. It starts the harness processes
through the supervisor's :class:`~aew.harness.procs.ProcessTree`, gives the harness the launch
contract's prompt, and reports what happened. It never holds an AEW credential, never commits AEW
state, and nothing it reports is evidence: the agent acts on AEW only through the custody bridge.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aew.errors import HarnessIncompatible
from aew.harness.contract import LaunchContract
from aew.harness.procs import ProcessTree


class HarnessAdapter(ABC):
    """``launch`` / ``inspect`` / ``send`` / ``interrupt`` / ``terminate`` / ``collect`` for one run."""

    name = ""

    def __init__(self, tree: ProcessTree, run_dir: Path, emit: Callable[[dict[str, Any]], None]) -> None:
        self.tree = tree
        self.run_dir = run_dir
        self.emit = emit  # append a telemetry event to the run's local event log

    @abstractmethod
    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        """Start the harness and deliver the contract's prompt. Returns health/version/session facts.

        Raises ``HarnessIncompatible`` when the harness lacks a required capability, model or variant
        (checked against the harness actually started for this run), or ``HarnessLaunchFailed``.
        ``agent_env`` is the complete environment for every model-controlled process: it carries no AEW
        credential, no provider secret and no harness server password.
        """

    @abstractmethod
    def inspect(self) -> dict[str, Any]:
        """``{"alive": bool, "exit_code": int | None, "session": str | None, ...}`` without side effects."""

    @abstractmethod
    def terminate(self) -> None:
        """Stop the harness and every process it started (idempotent)."""

    def send(self, text: str) -> None:
        """Deliver a Lead message to the running agent (coordination-compatible; M3 exposes it to the Lead)."""
        raise HarnessIncompatible(f"harness {self.name} does not support delivering messages to a running agent")

    def interrupt(self) -> None:
        """Stop the agent's current turn, keeping the session."""
        raise HarnessIncompatible(f"harness {self.name} does not support interrupting a turn")

    def collect(self) -> dict[str, Any]:
        """Non-authoritative facts after the run: effective model, usage, sessions, context sizes."""
        return {}
