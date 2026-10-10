"""The narrow harness adapter contract (ADR-0009).

One adapter instance serves one run, inside that run's supervisor. It starts the harness processes
through the supervisor's :class:`~aew.harness.procs.ProcessTree`, gives the harness the launch
contract's prompt, and reports what happened. It never holds an AEW credential, never commits AEW
state, and nothing it reports is evidence: the agent acts on AEW only through the custody bridge.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aew.errors import HarnessIncompatible
from aew.harness.contract import LaunchContract
from aew.harness.procs import ProcessTree


class HarnessAdapter(ABC):
    """``launch`` / ``inspect`` / ``send`` / ``interrupt`` / ``terminate`` / ``collect`` for one run."""

    name = ""
    # How the harness's reported token counters overlap, per qualified harness version and provider:
    # ``{version: {provider: semantics}}``, values from ``aew.harness.usage.TOKEN_SEMANTICS``, each pinned by a harness
    # conformance test (F25, cost and usage ledger v0.2 R4 rule 1). A version or provider it does not name resolves to
    # ``unknown``, which is never priced.
    token_semantics: Mapping[str, Mapping[str, str]] = {}
    # The longest a successful ``launch`` can take, for an adapter that does not compute it (``launch_bound_s``).
    LAUNCH_BOUND_S = 240.0

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

    @classmethod
    def launch_bound_s(cls) -> float:
        """The longest a successful ``launch`` can take: its steps' own timeouts in series, from the settings this
        process runs with. The supervisor's start deadline is derived from it, so it never cuts off a start that is
        still within the adapter's own bounds (ADR-0009 amendment 2026-10-09)."""
        return cls.LAUNCH_BOUND_S

    @abstractmethod
    def inspect(self) -> dict[str, Any]:
        """``{"alive": bool, "exit_code": int | None, "session": str | None, ...}`` without side effects. Once the
        harness has ended, ``reason_code`` (from ``aew.harness.contract``, for example ``provider_auth_failed``) says
        why, when the adapter can tell; the supervisor records it on the run."""

    @abstractmethod
    def terminate(self) -> None:
        """Stop the harness and every process it started (idempotent)."""

    def send(self, text: str, delivery: str) -> None:
        """Deliver a Lead message to the running agent (coordination-compatible; M3 exposes it to the Lead).
        ``delivery`` is ``steer`` (at the agent's next step boundary, without interrupting it) or ``queue`` (after its
        current turn): ``aew.coordination.layout.WHEN_DELIVERY`` maps the Lead's ``--when`` onto it (register E55)."""
        raise HarnessIncompatible(f"harness {self.name} does not support delivering messages to a running agent")

    def interrupt(self) -> None:
        """Stop the agent's current turn, keeping the session."""
        raise HarnessIncompatible(f"harness {self.name} does not support interrupting a turn")

    def collect(self) -> dict[str, Any]:
        """Non-authoritative facts after the run: usage, sessions, context sizes, and ``effective``: every
        ``{"provider", "model", "effort"}`` the harness actually ran (``effort`` None when not reported).
        The supervisor compares ``effective`` with the pinned execution profile and flags any mismatch.

        ``usage_record``, when the adapter reports usage, is the run's normalized ``aew/run-usage/v1`` record built by
        ``aew.harness.usage.normalize`` from the adapter's raw snapshot, with the ``token_semantics`` the adapter
        declares (above) for the providers that ran; the supervisor adds the wall time and keeps it beside the raw
        ``usage`` (F25 R2). An adapter that cannot read usage omits it: the run's usage then counts as absent."""
        return {}
