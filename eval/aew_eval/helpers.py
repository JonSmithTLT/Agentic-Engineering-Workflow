"""The arm helpers' contract (F19 plan v5 §2.1, §2.3, §2.6.1; S8a defines it, S8b implements it, S17 installs it).

Every read of the arm's data and every process the arm runs goes through four root-owned helpers that run **as
``arm``** (one sudoers rule), never through the evaluator's own uid (``aeweval``), so a link in the arm's tree reaches
only what ``arm`` could already read (the confused deputy, §2.3):

* ``arm-launch`` starts a process as ``arm``, in the run's own process namespace, and reports its pid and start time;
* ``arm-kill`` ends every process of the run and proves none remains;
* ``arm-pack`` streams the deliverable, the session databases, the AEW state and the CF inputs as a bundle;
* ``arm-tap`` is the run's one long-lived sampler (§2.6.1, R3-n4): every second it reports each ``opencode … serve``
  process ``arm`` runs (its pid and start time, its password from ``/proc/<pid>/environ``, its loopback port from
  its socket inodes, its run directory and that run's root session) and each worker run's live usage file, as events
  on a pipe only the evaluator reads. Nothing it reports is written to disk.

This module holds the contract only: the protocol the supervisor (:mod:`aew_eval.supervisor`) calls and the event
shapes it consumes. It imports nothing of the supervisor, the meters or AEW's product code, so S8b's implementation
and S17's packaging depend on it alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Launched:
    """A process ``arm-launch`` started: its pid and kernel start time (the pair names it; a pid can be reused)."""

    pid: int
    start_time: str


@dataclass(frozen=True)
class KillProof:
    """``arm-kill``'s answer: the run's processes it ended, and those still present afterwards (empty when sound)."""

    ended: tuple[int, ...]
    remaining: tuple[int, ...]


@dataclass(frozen=True)
class TapServer:
    """``arm-tap`` saw an OpenCode server ``arm`` runs. ``password`` is held in memory only: it is never written,
    logged or put in a record (its ``repr`` hides it)."""

    pid: int
    start_time: str
    port: int
    run_dir: str | None
    root_session: str | None
    password: str = field(repr=False)

    @property
    def key(self) -> str:
        return f"{self.pid}@{self.start_time}"


@dataclass(frozen=True)
class TapServerGone:
    """A server ``arm-tap`` reported before is no longer running."""

    key: str


@dataclass(frozen=True)
class TapLiveFile:
    """A worker run's ``usage.live.json`` as ``arm-tap`` read it: a cross-check only, never the counted figure, since
    ``arm`` can write it (§2.6.1). ``sample`` is ``None`` when the file has gone."""

    run_dir: str
    sample: dict[str, Any] | None


TapEvent = TapServer | TapServerGone | TapLiveFile


class ArmHelpers(Protocol):
    """The four helpers, as the supervisor calls them. S8b implements this protocol."""

    def launch(self, argv: list[str], *, env: dict[str, str], cwd: str, stdin: bytes = b"") -> Launched: ...

    def kill(self) -> KillProof: ...

    def pack(self) -> tuple[bytes, str, dict[str, str]]: ...  # (bundle, manifest sha256, paths not read)

    def tap(self) -> Iterator[list[TapEvent]]: ...  # one batch of events per sampling round
