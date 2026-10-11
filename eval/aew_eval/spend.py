"""Spend, the caps and the counted cost of one supervised run (F19 plan v5 §2.6, §2.6.1, §2.6.3, §2.6.4; F25 plan v4
§2.3, §2.5, §3.3).

**The feeds.** :class:`SpendFeed` is F25 v4's ``total_spend`` and ``settle`` with the run's prices, limits and
``d_floor`` bound (S14 binds the real ones; tests use a fake). :class:`ProxyFeed` is the metering proxy's per-run
ledger (S18), which under layer (c) sees every provider request, generation calls included.

**Termination** (:func:`check`), F19's rule: end the run when any of these holds.

1. The total is ``unknown`` (at once).
2. A source's age passes the hard staleness ceiling.
3. More sessions are in flight than ``S_pot_hard`` (``S_POT_EXCEEDED``; only where R has no sealed subagent cap).
4. F25's test: ``usd + projection + guard >= cap``, where
   ``guard = S_pot × k_assumed × c × (⌊W/d⌋ + 2)``, ``W = L_m + P + T_k``, ``d = min(observed d_min, d_floor)``, and
   ``S_pot`` is the preregistered ``S_pot_arm`` (``max(S_pot_arm, the run's largest in_flight)`` where R has no cap
   key). A stale source (older than ``stale_after_s``, or gone) adds its own ``s_pot × k_assumed × c ×
   (⌊age/d⌋ + 2)`` to its last figure, which ``usd`` already holds.
5. Under layer (c), the proxy's test: ``proxy_usd + open_requests × c >= cap`` (``proxy_usd`` includes estimates).

**The counted cost** (the lead developer's placement, 2026-10-10): under layer (c) the counted cost and the cap come
from the proxy's ledger, which meters every provider request; F25's settled figure is a cross-check, and a
divergence between the two above the run's reconciliation tolerance is CF evidence (:func:`divergence`). Under the
fallback layer (b) the counted cost is F25's settled figure, recorded as a lower bound and charged at the cap when it
is not complete. Layer (a) is not admissible for counted runs.

**State.** Every meter's state lives under the evaluator's own root, created 0700, and each file and its parents up to
that root are checked (:func:`require_private`): owned by this uid, writable by no one else, and never a link.
"""

from __future__ import annotations

import math
import os
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from aew_eval.schemas import Invalid

LAYERS = ("c", "b", "a")
GONE = "server_gone"
FINAL = "final"


@dataclass(frozen=True)
class SpendTerms:
    """The sealed values a run's spend rules use (plan v5 §5; S12 seals them)."""

    cap_usd: float
    s_pot_arm: int
    c_usd: float                     # the guard's per-call value
    c_choice: str                    # "c_ceil" (a bound) or "heuristic" (g × max_step_usd)
    d_floor_s: float
    reconciliation_margin: float     # the sealed relative margin of §2.6.4 (S12)
    layer: str = "c"
    k_assumed: int = 2
    latency_s: float = 2.0           # L_m (F25 v4 §2.3)
    poll_s: float = 1.0              # P
    kill_s: float = 3.0              # T_k
    stale_after_s: float = 5.0
    stale_ceiling_s: float = 30.0
    s_pot_hard: int | None = None    # R without a sealed subagent cap: S_pot_arm(A)
    settle_deadline_s: float = 60.0

    def __post_init__(self) -> None:
        positive = {"cap_usd": self.cap_usd, "s_pot_arm": self.s_pot_arm, "c_usd": self.c_usd,
                    "d_floor_s": self.d_floor_s, "k_assumed": self.k_assumed, "stale_after_s": self.stale_after_s,
                    "stale_ceiling_s": self.stale_ceiling_s, "settle_deadline_s": self.settle_deadline_s}
        bad = [k for k, v in positive.items() if not (isinstance(v, int | float) and math.isfinite(v) and v > 0)]
        if bad or self.layer not in LAYERS or self.c_choice not in ("c_ceil", "heuristic") \
                or not 0 <= self.reconciliation_margin < 1 or (self.s_pot_hard is not None and self.s_pot_hard < 1):
            raise Invalid(f"the spend terms are not sound: {bad or 'layer, c choice, margin or S_pot_hard'}")


class SpendFeed(Protocol):
    """F25 v4's ``total_spend`` and ``settle`` (``aew.engine.usage_meter``), the run's prices, limits and ``d_floor``
    bound; both return ``aew/usage-total/v1``."""

    def total_spend(self, samples: Sequence[dict[str, Any]], now: float) -> dict[str, Any]: ...

    def settle(self, samples: Sequence[dict[str, Any]], *, closed_at: float,
               residual_sessions_in_flight: int) -> dict[str, Any]: ...


class ProxyFeed(Protocol):
    """The metering proxy's per-run ledger (S18): every provider request of the run, generation calls included."""

    def run_usd(self) -> float: ...           # including every ``usage_estimated`` charge

    def estimated_usd(self) -> float: ...     # the ``usage_estimated`` charges alone

    def open_requests(self) -> int: ...

    def throttle_events(self) -> list[dict[str, Any]]: ...   # 429s and retries since the last call: {at, kind}

    def close(self) -> dict[str, Any]: ...    # closes the run's ledger; returns its summary


def usd(value: Any) -> float:
    """A total's ``usd`` (a Decimal string), as a float; refused when it is not a finite number."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise Invalid(f"a spend figure is a decimal string, not {value!r}") from None
    if not number.is_finite():
        raise Invalid(f"a spend figure is finite, not {value!r}")
    return float(number)


def d_used(terms: SpendTerms, d_min_s: float | None) -> float:
    return terms.d_floor_s if d_min_s is None else min(d_min_s, terms.d_floor_s)


def s_pot_used(terms: SpendTerms, max_in_flight: int) -> int:
    """The guard's ``S_pot``: the preregistered ``S_pot_arm``, never the sources' sum (R3-m2); where R has no sealed
    subagent cap (``s_pot_hard`` set), the largest ``in_flight`` the run has shown if that is larger (R3-n3)."""
    return terms.s_pot_arm if terms.s_pot_hard is None else max(terms.s_pot_arm, max_in_flight)


def guard(terms: SpendTerms, *, d_min_s: float | None, max_in_flight: int) -> float:
    d = d_used(terms, d_min_s)
    window = terms.latency_s + terms.poll_s + terms.kill_s
    return s_pot_used(terms, max_in_flight) * terms.k_assumed * terms.c_usd * (math.floor(window / d) + 2)


def projection(terms: SpendTerms, sources: Sequence[dict[str, Any]], *, d_min_s: float | None) -> float:
    """What the stale sources may have spent since their last figure: each with its own ``s_pot`` (R2-M1)."""
    d = d_used(terms, d_min_s)
    extra = 0.0
    for source in sources:
        if source.get("state") == FINAL:  # finished: nothing left to spend (PR #196 review, F3)
            continue
        age = float(source.get("age_s") or 0.0)
        if source.get("state") == GONE or age > terms.stale_after_s:
            extra += int(source.get("s_pot") or terms.s_pot_arm) * terms.k_assumed * terms.c_usd * \
                (math.floor(age / d) + 2)
    return extra


@dataclass(frozen=True)
class Check:
    """One termination check: the end reason (``None`` while the run may go on) and the figures it compared."""

    reason: str | None
    figures: dict[str, Any]


def check(terms: SpendTerms, total: dict[str, Any], *, max_in_flight: int,
          proxy: ProxyFeed | None) -> Check:
    """F19's termination rule (module docstring): which end, if any, the run's spend calls for now."""
    sources = list(total.get("sources") or [])
    d_min = total.get("d_min_s")
    figures: dict[str, Any] = {"usd": usd(total["usd"]), "completeness": total["completeness"],
                               "in_flight": int(total.get("in_flight") or 0),
                               "guard": guard(terms, d_min_s=d_min, max_in_flight=max_in_flight),
                               "projection": projection(terms, sources, d_min_s=d_min), "cap_usd": terms.cap_usd}
    oldest = max((float(s.get("age_s") or 0.0) for s in sources if s.get("state") != FINAL), default=0.0)
    figures["oldest_age_s"] = oldest
    if proxy is not None and terms.layer == "c":
        figures["proxy_usd"], figures["proxy_open"] = proxy.run_usd(), proxy.open_requests()
    if total["completeness"] == "unknown":
        return Check("UNKNOWN_TOTAL", figures)
    if oldest > terms.stale_ceiling_s:
        return Check("STALE_CEILING", figures)
    if terms.s_pot_hard is not None and figures["in_flight"] > terms.s_pot_hard:
        return Check("S_POT_EXCEEDED", figures)
    if figures["usd"] + figures["projection"] + figures["guard"] >= terms.cap_usd:
        return Check("USD_CAP", figures)
    if "proxy_usd" in figures and figures["proxy_usd"] + figures["proxy_open"] * terms.c_usd >= terms.cap_usd:
        return Check("PROXY_CAP", figures)
    return Check(None, figures)


def divergence(terms: SpendTerms, *, proxy_usd: float, live_usd: float, residual_sessions: int, open_at_close: int,
               estimated_usd: float) -> dict[str, Any]:
    """The proxy-versus-live comparison of one run (§2.6.4's tolerance). ``exceeds`` is CF evidence: the live meter
    missed spend the proxy saw (an unmetered path), or the reverse."""
    tolerance = (residual_sessions * terms.k_assumed * terms.c_usd + open_at_close * terms.c_usd + estimated_usd
                 + terms.reconciliation_margin * max(proxy_usd, live_usd))
    return {"proxy_usd": round(proxy_usd, 6), "live_usd": round(live_usd, 6), "tolerance_usd": round(tolerance, 6),
            "exceeds": abs(proxy_usd - live_usd) > tolerance}


def counted(terms: SpendTerms, settled: dict[str, Any], proxy_usd: float | None) -> dict[str, Any]:
    """The run's counted and charged cost (module docstring). Nothing here is ever zero by default: a figure that is
    not known is ``None``, unresolved, and charged at the cap.

    * Layer (c): the proxy's ledger (``proxy_usd``; ``None`` when it could not be closed, so unresolved).
    * Layer (b): F25's settled figure, and it is a **lower bound** (``lower_bound: true``): spend the live meter does
      not see is bounded only by the provider's per-key limit. Charged at the cap when not complete.
    * Layer (a) is not admissible for counted runs: refused."""
    if terms.layer == "a":
        raise Invalid("layer (a) is not admissible for counted runs")
    live = None if settled.get("usd") is None else usd(settled["usd"])
    base = {"layer": terms.layer, "live_usd": live, "live_completeness": settled["completeness"]}
    if terms.layer == "c":
        if proxy_usd is None:
            return {**base, "counted_usd": None, "counted_resolved": False, "charged_usd": terms.cap_usd,
                    "source": "proxy", "unresolved_reason": "proxy_ledger_not_closed"}
        return {**base, "counted_usd": proxy_usd, "counted_resolved": True, "charged_usd": proxy_usd,
                "source": "proxy"}
    if live is None:
        return {**base, "counted_usd": None, "counted_resolved": False, "charged_usd": terms.cap_usd,
                "source": "live", "lower_bound": True, "unresolved_reason": "no_live_figure"}
    complete = settled["completeness"] == "complete"
    return {**base, "counted_usd": live, "counted_resolved": True, "lower_bound": True, "source": "live",
            "charged_usd": live if complete else max(live, terms.cap_usd)}


# ---------------------------------------------------------------------------------------------- private state

def require_private(path: Path, root: Path) -> None:
    """``path`` and every directory between it and ``root`` (inclusive): never a link, and on POSIX owned by this uid
    and writable by no one else. Refused otherwise: a meter's high-water state is the evaluator's alone (§2.6)."""
    path, root = Path(path), Path(root)
    chain = [path]
    here = path
    while here != root:
        if here.parent == here:
            raise Invalid(f"{path} is not under the evaluator's state root {root}")
        here = here.parent
        chain.append(here)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    for p in chain:
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode) or (reparse and getattr(st, "st_file_attributes", 0) & reparse):
            raise Invalid(f"{p} is a link: meter state never lives behind one")
        if sys.platform != "win32":
            if st.st_uid != os.geteuid():
                raise Invalid(f"{p} is owned by uid {st.st_uid}, not the evaluator's ({os.geteuid()})")
            if st.st_mode & 0o022:
                raise Invalid(f"{p} is writable by others (mode {stat.S_IMODE(st.st_mode):o})")


def private_dir(root: Path, *parts: str, fresh: bool = False) -> Path:
    """``root/parts...``, created 0700 where missing, and checked with :func:`require_private`. ``fresh`` refuses a
    last directory that already exists: a meter's state is never one another run or meter left (PR #196 review,
    F8)."""
    root = Path(root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    here = root
    for n, part in enumerate(parts, 1):
        here = here / part
        try:
            os.mkdir(here, 0o700)
        except FileExistsError:
            if fresh and n == len(parts):
                raise Invalid(f"{here} exists: a meter's state directory is made fresh for it") from None
    require_private(here, root)
    return here
