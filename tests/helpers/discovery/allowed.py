"""D2's allow-list and how a run is decided against it (discovery-layer spec v3.4, §5; vertical-uat.md §8).

The allow-list (``allowed.yaml`` beside this module) holds every ``(rule, site)`` key observed when D2 was introduced:
the existing violations, which D2 observes and never fixes. It may only shrink:

- **On every run**, a key observed but not allow-listed is **new**: reported, and failing the run when its rule is in
  ``enforce``.
- **On a pull request**, a key added to the allow-list relative to the base is refused, unless it is an accepted
  residual (the operator's decision, recorded with its reason) on a pull request carrying the ``operator-merge`` label,
  which reserves the merge for the operator (``tools/ci/discovery_ratchet.py`` decides growth). A rule's mode lowered
  from ``enforce`` is growth too: it stops the rule failing anything.
- **On a run complete for it**, an allow-listed key no longer observed is **stale**: reported, and failing when its
  rule is in ``enforce``, until a pull request removes it (``discovery_ratchet.py --remove``). CI never commits the
  removal itself.

Static keys (``static:``, ``tool-arguments:``) come from a complete scan, so they are decided on every run of the
scan. Runtime keys (``cli:``, ``tool:``) come from the tests a run selected and finished, so only a run where every
test of the full tier ran and passed can call one stale: main's, nightly's, and a full-tier pull request's, which then
fails on the change that caused it rather than reddening main after the merge.
"""

from __future__ import annotations

import shlex
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
            "# observed when D2 was introduced. It may only shrink: remove an entry once it is no longer observed,\n"
            "# with tools/ci/discovery_ratchet.py --remove KEY...; never add an entry by hand (an accepted\n"
            "# residual is the operator's, under `residuals`, with its decision and reason).\n")
    body = {"schema": SCHEMA, "allowed": {r: sites for r, sites in by_rule.items() if sites},
            "residuals": list(residuals)}
    return head + yaml.safe_dump(body, sort_keys=False, allow_unicode=True, width=1000)


@dataclass
class Verdict:
    new: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    grown: list[str] = field(default_factory=list)
    lowered: list[str] = field(default_factory=list)  # rules whose mode fell from enforce against the base, unsigned
    failing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failing and not self.lowered


def lowered_modes(base: Mapping[str, str], head: Mapping[str, str]) -> list[str]:
    """The rules enforced in ``base`` and not in ``head``, a rule dropped altogether included."""
    return sorted(r for r, mode in base.items() if mode == modes.ENFORCE and head.get(r) != modes.ENFORCE)


def decide(observed: Iterable[str], allowed: set[str], *, stale_scope: str | None,
           mode_of: Mapping[str, str] = modes.MODES) -> Verdict:
    """The verdict of one run over new and stale keys. ``stale_scope``: which allow-listed keys the run is complete for
    (``"static"``, ``"runtime"``, ``"all"``, or ``None`` on a run that did not finish every test of the full tier, where
    absence proves nothing). Growth of the list against the base, and a mode lowered against it, have one owner, the
    ratchet (``tools/ci/discovery_ratchet.py``), which alone reads the pull request's labels live and so can tell the
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


def remove_command(*keys: str) -> str:
    """The command that removes ``keys``, to paste into bash or PowerShell: double quotes hold a key's ``|``, spaces and
    ``<`` in both, and only a key holding what they would still expand falls back to POSIX quoting."""
    quoted = (shlex.quote(k) if set(k) & set('"$`\\') else f'"{k}"' for k in keys)
    return " ".join(("python tools/ci/discovery_ratchet.py --remove", *quoted))


def _failure(key: str, v: Verdict, details: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """One failing key: what fired, the test that reached it, and what to do."""
    seen = details.get(key) or {}
    detail = " ".join(str(seen.get("detail") or "").split()) or "not recorded"
    test = seen.get("test") or ("the static scan (tests/helpers/discovery/static.py)" if is_static(key)
                                else "not recorded")
    if key in v.stale:
        detail, test = "no test of this complete run produced this output", "none"
        todo = (f"remove the entry: {remove_command(key)} (if you did not mean to retire the output, a test stopped "
                "reaching it: restore that test instead)")
    elif key in v.grown:
        todo = ("take the entry off the list, which may only shrink. Only the operator accepts a residual: an entry "
                "under `residuals` with its decision and reason, on a pull request labelled `operator-merge`")
    else:
        todo = ("change the output so it passes the rule (tests/helpers/discovery/rules.py). Only the operator accepts "
                "it instead: an entry under `allowed` and `residuals`, on a pull request labelled `operator-merge`")
    return [f"  FAIL {key}", f"    why:  {detail}", f"    test: {test}", f"    do:   {todo}"]


def report(v: Verdict, *, details: Mapping[str, Mapping[str, Any]] | None = None, limit: int = 40) -> list[str]:
    """The run's report. Failing keys come first and are never cut, each with its ``details`` (key to ``detail`` and
    ``test``, as the findings hold them) and what to do: a failure the author cannot see or act on is friction with no
    safety in it. Keys that fail nothing follow, up to ``limit`` per list."""
    failing = set(v.failing)
    lines = [f"{len(v.failing)} key(s) fail this run:"] if v.failing else []
    for key in v.failing:
        lines += _failure(key, v, details or {})
    for title, keys in (("new (not allow-listed)", v.new), ("stale (allow-listed, no longer observed)", v.stale),
                        ("added to the allow-list (it may only shrink)", v.grown)):
        if keys:
            rest = [k for k in keys if k not in failing]
            shown = f" ({len(keys) - len(rest)} failing, above)" if len(rest) < len(keys) else ""
            lines.append(f"{len(keys)} {title}{shown}:")
            lines += [f"  {k}" for k in rest[:limit]]
            if len(rest) > limit:
                lines.append(f"  ... and {len(rest) - limit} more")
    return lines or ["no new, stale or added keys"]
