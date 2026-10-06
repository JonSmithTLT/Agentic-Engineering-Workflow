"""``SurfaceContext``: who is calling the typed surface, and through what (F15.1 plan §3.0).

Context, never authority: the engine still validates the actual credential on every mutation. It holds no secret and
is safe to log; the Lead credential travels separately, only to the runner's mutating step and the recovery escape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NORMAL = "normal"  # the normal Lead surface: what a model is offered by default
RECOVERY = "recovery"  # adds the generic `cli` escape (recovery, debug, conformance)
PROFILES = (NORMAL, RECOVERY)

INGRESSES = ("mcp", "cli", "direct")


@dataclass(frozen=True)
class SurfaceContext:
    lead_session: dict[str, Any] | None  # the Lead broker's whoami view ({holds, generation, session_label}), or None
    generation: int | None  # the Lead generation the caller acts for; None when it acts for none in particular
    profile: str = NORMAL  # presentation and callability only: never legality, never auto_runnable
    ingress: str = "direct"

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError(f"unknown surface profile {self.profile!r}")
        if self.ingress not in INGRESSES:
            raise ValueError(f"unknown ingress {self.ingress!r}")

    @classmethod
    def for_session(cls, whoami: dict[str, Any], *, profile: str, ingress: str) -> SurfaceContext:
        """Inside a Lead session: the broker's view of the authority it holds."""
        session = {"holds": True, "generation": whoami["generation"], "session_label": whoami.get("session_label")}
        return cls(lead_session=session, generation=whoami["generation"], profile=profile, ingress=ingress)

    @classmethod
    def outside_session(cls, *, profile: str = NORMAL, ingress: str = "cli") -> SurfaceContext:
        """An operator's own shell (ADR-0005): no broker; the credential, if any, is checked by the engine."""
        return cls(lead_session=None, generation=None, profile=profile, ingress=ingress)
