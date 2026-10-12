"""D2's allow-list and how a run is decided against it (discovery-layer spec v3.4, §5; vertical-uat.md §8).

The allow-list (``allowed.yaml`` beside this module) holds every ``(rule, site)`` key observed when D2 was introduced:
the existing violations, which D2 observes and never fixes. It may only shrink:

- **On a pull request**, a key observed but not allow-listed is **new**: reported, and failing the run when its rule
  is in ``enforce``. A key added to the allow-list relative to the base is refused, unless it is an accepted residual
  (the operator's decision, recorded with its reason) on a pull request carrying the ``operator-merge`` label, which
  reserves the merge for the operator (``tools/ci/discovery_ratchet.py`` decides growth).
- **On main and nightly** (the full selection), an allow-listed key no longer observed is **stale**: reported, and
  failing when its rule is in ``enforce``, until a pull request removes it. CI never commits the removal itself.

Static keys (``static:``, ``tool-arguments:``) come from a complete scan, so they are decided on every run of the
scan; runtime keys (``cli:``, ``tool:``) come from the tests a run selected, so only main and nightly can call one
stale.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from discovery import modes

PATH = Path(__file__).with_name("allowed.yaml")
FINDINGS_SUFFIX = ".discovery.json"


def findings_path_for(lane_report: Path) -> Path:
    """The findings file beside a lane report: the capture plugin writes it there and the ratchet expects it there (one
    owner for the pairing). Another schema, so assurance's report loader skips it."""
    return lane_report.with_name(lane_report.stem + FINDINGS_SUFFIX)


SCHEMA = "aew/discovery-allowed/v1"
STATIC_PREFIXES = ("static:", "tool-arguments:")


def is_static(key: str) -> bool:
    return key.split(" ", 1)[1].startswith(STATIC_PREFIXES)


def parse(text: str | None) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """``(keys, residuals)`` of an allow-list's text (``None``: no allow-list, as before D2 existed)."""
    if text is None:
        return set(), {}
    data = yaml.safe_load(text) or {}
    if data.get("schema") != SCHEMA:
        raise ValueError(f"the allow-list's schema is not {SCHEMA}")
    keys = {f"{rule} {site}" for rule, sites in (data.get("allowed") or {}).items() for site in sites or []}
    unknown = {k.split(" ", 1)[0] for k in keys} - set(modes.RULES)
    if unknown:
        raise ValueError(f"the allow-list names rules D2 does not have: {sorted(unknown)}")
    residuals = {f"{r['rule']} {r['site']}": r for r in data.get("residuals") or []}
    for key, r in residuals.items():
        if not (r.get("decision") and r.get("reason")):
            raise ValueError(f"accepted residual {key} lacks the operator's decision or its reason")
    return keys, residuals


def load(path: Path = PATH) -> set[str]:
    return parse(path.read_text(encoding="utf-8") if path.is_file() else None)[0]


def render(keys: Iterable[str], residuals: Iterable[Mapping[str, Any]] = ()) -> str:
    """The allow-list file for ``keys``: grouped by rule, sorted, so a change is a readable diff."""
    by_rule: dict[str, list[str]] = {rule: [] for rule in modes.RULES}
    for key in sorted(set(keys)):
        rule, site = key.split(" ", 1)
        by_rule[rule].append(site)
    head = ("# D2's allow-list (docs/implementation/vertical-uat.md §8): the (rule, output-site key) violations\n"
            "# observed when D2 was introduced. It may only shrink: remove an entry once it is no longer observed.\n"
            "# Regenerate with tools/ci/discovery_ratchet.py --write; never add an entry by hand (an accepted\n"
            "# residual is the operator's, under `residuals`, with its decision and reason).\n")
    body = {"schema": SCHEMA, "allowed": {r: sites for r, sites in by_rule.items() if sites},
            "residuals": list(residuals)}
    return head + yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=1000)


@dataclass
class Verdict:
    new: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    grown: list[str] = field(default_factory=list)
    failing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failing


def decide(observed: Iterable[str], allowed: set[str], *, stale_scope: str | None,
           mode_of: Mapping[str, str] = modes.MODES) -> Verdict:
    """The verdict of one run over new and stale keys. ``stale_scope``: which allow-listed keys the run's selection is
    complete for (``"static"``, ``"runtime"``, ``"all"``, or ``None`` on a pull request's runtime selection, where
    absence proves nothing). Growth of the list against the base has one owner, the ratchet
    (``tools/ci/discovery_ratchet.py``), which alone reads the pull request's labels live and so can tell the
    operator's accepted residual from the author's."""
    seen = set(observed)
    v = Verdict()
    v.new = sorted(seen - allowed)
    if stale_scope is not None:
        in_scope = {k for k in allowed if stale_scope == "all" or (is_static(k) == (stale_scope == "static"))}
        v.stale = sorted(in_scope - seen)
    enforce = {r for r, m in mode_of.items() if m == modes.ENFORCE}
    v.failing = sorted({*(k for k in v.new + v.stale if k.split(" ", 1)[0] in enforce), *v.grown})
    return v


def report(v: Verdict, *, limit: int = 40) -> list[str]:
    lines = []
    for title, keys in (("new (not allow-listed)", v.new), ("stale (allow-listed, no longer observed)", v.stale),
                        ("added to the allow-list (it may only shrink)", v.grown)):
        if keys:
            lines.append(f"{len(keys)} {title}:")
            lines += [f"  {'FAIL ' if k in v.failing else ''}{k}" for k in keys[:limit]]
            if len(keys) > limit:
                lines.append(f"  ... and {len(keys) - limit} more")
    return lines or ["no new, stale or added keys"]
