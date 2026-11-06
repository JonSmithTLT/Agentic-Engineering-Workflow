#!/usr/bin/env python3
"""D2's ratchet over a CI run (discovery-layer spec v3.4, §5; docs/implementation/vertical-uat.md §8.3).

Merges the findings every lane job wrote beside its lane report (``*.discovery.json``, schema
``aew/discovery-findings/v1``) and decides them against the allow-list (``tests/helpers/discovery/allowed.yaml``):

- every run: a key not on the list is new (reported; failing when its rule is in ``enforce``).
- ``--event pull_request``: a key added to the list relative to ``--base-allowlist`` fails whatever its mode, and so
  does a rule's mode lowered from ``enforce`` relative to ``--base-modes``. The one exception is the operator's: an
  accepted residual, or a lowered mode, passes only while the pull request carries the ``operator-merge`` label, read
  live (``--repo``, ``--pr``).
- ``--tier full --assurance success``, on any event: a listed runtime key not observed anywhere in the run is also
  stale (reported; failing when its rule is in ``enforce``). Only a run where every test of the full tier ran and passed
  can prove an output is gone, and a full-tier pull request is such a run, so the change that retires an output fails
  on itself and not on main after its merge. A reduced tier or a lost shard decides nothing stale. Static keys are
  decided by the fast lane's test and the ``discovery`` lane, over the complete scan.
- Any capture error fails the run: an output left unjudged is not a pass.

``--remove KEY...`` takes entries off the list, and any accepted residual with them. It reads no reports, so it works
from a pull request, whatever else the run reports. A key is its rule and its site together: an output site can sit
under several rules, and only the named rule's entry goes.

``--write`` regenerates the allow-list from a complete run instead (introducing D2): it refuses a run ``assurance``
would refuse, since a partial one would drop every key it never reached, and it refuses to add a key that the current
list lacks unless ``--introduce`` is given, which only the pull request introducing D2 uses.

    python tools/ci/discovery_ratchet.py REPORTS_DIR --event pull_request --base-allowlist BASE.yaml \\
        --base-modes BASE_MODES.py --tier TIER --assurance OUTCOME [--summary F]
    python tools/ci/discovery_ratchet.py REPORTS_DIR --event push --tier full --assurance OUTCOME [--summary F]
    python tools/ci/discovery_ratchet.py --remove "RULE SITE" ...
    python tools/ci/discovery_ratchet.py REPORTS_DIR --write [--introduce] [--static GUIDES_DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "helpers"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_assurance  # noqa: E402  (tools/ci/check_assurance.py)
from discovery import allowed, modes  # noqa: E402

FINDINGS_SCHEMA = "aew/discovery-findings/v1"
# tests/helpers/lanes.py's REPORT_SCHEMA, pinned equal by a test (lanes imports pytest, and this runs without it)
LANE_REPORT_SCHEMA = "aew/lane-report/v1"
OPERATOR_LABEL = "operator-merge"  # AGENTS.md §5: a pull request with it is merged by the operator
FULL_TIER, ASSURED = "full", "success"


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_findings(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[str]]:
    """``(findings by key, capture errors, sources)`` merged over every findings file under ``root``.

    A lane's findings lost on the way count as capture errors, never as silence (review of #218, G1): every lane
    report must have its findings file beside it (``allowed.findings_path_for``), and a findings file that does not
    parse or carries another schema is an error, not a file to skip. Only each shard's latest run attempt counts, as in
    the gate's own check (``check_assurance.latest_attempts``): a superseded lane report and its findings file are
    left out, so an earlier attempt's capture error does not outlive the re-run that passed (review of #251, F1)."""
    findings: dict[str, dict[str, Any]] = {}
    errors: dict[str, int] = {}
    sources = []

    def error(name: str) -> None:
        errors[name] = errors.get(name, 0) + 1

    read = {path: _read(path) for path in (sorted(root.rglob("*.json")) if root.is_dir() else [])}
    reports = [{**data, "_path": path} for path, data in read.items()
               if isinstance(data, dict) and data.get("schema") == LANE_REPORT_SCHEMA]
    kept = {r["_path"] for r in check_assurance.latest_attempts(reports)}
    superseded = {r["_path"] for r in reports if r["_path"] not in kept}
    superseded |= {allowed.findings_path_for(path) for path in superseded}
    for path, data in read.items():
        if path in superseded:
            continue
        rel = path.relative_to(root).as_posix()
        if path.name.endswith(allowed.FINDINGS_SUFFIX):
            if not isinstance(data, dict):
                error(f"findings file unreadable: {rel}")
                continue
            if data.get("schema") != FINDINGS_SCHEMA:
                error(f"findings file of another schema: {rel}")
                continue
        else:
            if isinstance(data, dict) and data.get("schema") == LANE_REPORT_SCHEMA:
                if not allowed.findings_path_for(path).is_file():
                    error(f"lane report without its findings file: {rel}")
            continue
        sources.append(rel)
        for key, entry in (data.get("findings") or {}).items():
            mine = findings.setdefault(key, {**entry, "count": 0})
            mine["count"] += int(entry.get("count") or 0)
        for name, n in (data.get("errors") or {}).items():
            errors[name] = errors.get(name, 0) + int(n)
    return findings, errors, sources


def stale_undecided(tier: str | None, assurance: str | None, sources: list[str], errors: dict[str, int]) -> str | None:
    """Why this run cannot call a runtime key stale, or ``None`` when it can. Fails closed: only the named tier and
    outcome decide, so an absent or unknown value of either decides nothing, and a lost shard cannot read as lost
    output (a fabricated run with one lost shard reported 337 stale keys, before this)."""
    if tier != FULL_TIER:
        return f"the tier is {tier or 'not known'}, not {FULL_TIER}: its tests are not all of them"
    if assurance != ASSURED:
        return f"the assurance check's outcome is {assurance or 'not known'}: tests did not all run and pass"
    if not sources:
        return "no findings file"
    if errors:
        return "capture errors: outputs went unjudged"
    return None


def incomplete(root: Path, skips: Path) -> list[str]:
    """What keeps the lane reports under ``root`` from being a complete run: ``assurance``'s own judgement of them at
    the full tier (derived rather than claimed by a flag, because ``--write`` runs by hand over downloaded reports)."""
    try:
        problems, _ = check_assurance.check(check_assurance.load_reports(root),
                                            check_assurance.load_expectations(skips),
                                            list(check_assurance.REQUIRED_PLATFORMS))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        return [f"the lane reports cannot be read: {type(exc).__name__}: {exc}"]
    return problems


def base_modes(path: Path) -> Mapping[str, str]:
    """The base branch's modes, from its copy of ``modes.py``, whose values are names rather than literals. It is the
    base's own file, as the tier tool is this checkout's (``live_labels``)."""
    spec = importlib.util.spec_from_file_location("discovery_modes_base", path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.MODES


def remove(allowlist: Path, keys: list[str]) -> int:
    """Take ``keys`` off the list, all or none: a key not on the list is a mistake to show, and a site named without its
    rule, or under another, is exactly how a hand edit removed the wrong rule's entry."""
    current, residuals = allowed.parse(allowlist.read_text(encoding="utf-8") if allowlist.is_file() else None)
    missing = [k for k in keys if k not in current]
    if missing:
        print(f"refused, nothing removed: {len(missing)} key(s) not on {allowlist} (a key is 'RULE SITE'):",
              file=sys.stderr)
        for key in missing:
            site = key.split(" ", 1)[1] if key.split(" ", 1)[0] in modes.RULES and " " in key else key
            near = sorted(k for k in current if k.split(" ", 1)[1] == site)
            print(f"  {key}" + (f" (on the list as: {'; '.join(near)})" if near else ""), file=sys.stderr)
        return 1
    gone = set(keys)
    dropped = sorted(gone & set(residuals))
    allowlist.write_text(allowed.render(current - gone, [r for k, r in residuals.items() if k not in gone]),
                         encoding="utf-8", newline="\n")
    print(f"removed {len(gone)} key(s) from {allowlist}, {len(current) - len(gone)} left:")
    print("\n".join(f"  {k}" for k in sorted(gone)))
    if dropped:
        print(f"and the accepted residual of {len(dropped)}:\n" + "\n".join(f"  {k}" for k in dropped))
    return 0


def write(args: argparse.Namespace, findings: dict[str, dict[str, Any]], errors: dict[str, int], sources: list[str],
          current: set[str], residuals: dict[str, dict[str, Any]]) -> int:
    if errors:  # a list written from a run that lost findings would drop keys it never judged
        print(f"refused: the run has {sum(errors.values())} capture error(s):", file=sys.stderr)
        print("\n".join(f"  {n} x {name}" for name, n in sorted(errors.items())[:20]), file=sys.stderr)
        return 1
    problems = incomplete(args.reports, args.skips)
    if problems:
        print(f"refused: these reports are not a complete run, so a key they lack proves nothing "
              f"({len(problems)} problem(s), first 20). To remove known keys, use --remove:", file=sys.stderr)
        print("\n".join(f"  {p}" for p in problems[:20]), file=sys.stderr)
        return 1
    keys = set(findings)
    if args.static:
        from discovery import static

        guides = static.read_guides(args.static, args.static.resolve().relative_to(ROOT).as_posix())
        keys |= {f.key for f in static.scan(guides)}
    else:
        keys |= {k for k in current if allowed.is_static(k)}
    added = sorted(keys - current)
    if added and not args.introduce:
        print(f"refused: {len(added)} key(s) the allow-list lacks (it may only shrink):", file=sys.stderr)
        print("\n".join(f"  {k}" for k in added[:40]), file=sys.stderr)
        return 1
    kept = [r for k, r in residuals.items() if k in keys]  # a residual goes with its key (#332 review, F6)
    args.allowlist.write_text(allowed.render(keys, kept), encoding="utf-8", newline="\n")
    print(f"wrote {args.allowlist} ({len(keys)} keys, from {len(sources)} findings file(s))")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", type=Path, nargs="?", default=None, help="the run's lane reports (not with --remove)")
    ap.add_argument("--event", default="pull_request")
    ap.add_argument("--tier", default=None, help="the run's tier (tools/ci/tier.py): only full can decide stale")
    ap.add_argument("--assurance", default=None, metavar="OUTCOME",
                    help="the outcome of check_assurance.py's step: only success can decide stale")
    ap.add_argument("--allowlist", type=Path, default=allowed.PATH)
    ap.add_argument("--base-allowlist", type=Path, default=None,
                    help="the base branch's allow-list on a pull request (absent: the base has none)")
    ap.add_argument("--base-modes", type=Path, default=None,
                    help="the base branch's modes.py on a pull request (not given: nothing to compare; given and "
                         "unreadable: fails)")
    ap.add_argument("--repo", default=None, help="OWNER/REPO, to read the pull request's labels live")
    ap.add_argument("--pr", default=None, help="the pull request's number, to read its labels live")
    ap.add_argument("--summary", type=Path, default=None, help="append a Markdown report (GITHUB_STEP_SUMMARY)")
    ap.add_argument("--remove", nargs="+", default=None, metavar="KEY",
                    help="take these 'RULE SITE' entries off the list, and any residual with them (reads no reports)")
    ap.add_argument("--write", action="store_true", help="regenerate the allow-list from a complete run's findings")
    ap.add_argument("--introduce", action="store_true", help="with --write: allow keys the current list lacks")
    ap.add_argument("--static", type=Path, default=None, metavar="GUIDES_DIR",
                    help="with --write: include the static scan's keys, reading the operator guides from this "
                         "directory (the repository's docs/guides)")
    ap.add_argument("--skips", type=Path, default=ROOT / "tests" / "platform-skips.yaml",
                    help="with --write: the pinned skips the completeness check reads")
    args = ap.parse_args(argv)

    if args.remove is not None:
        if args.reports is not None or args.write:
            ap.error("--remove reads no reports, and takes neither a reports directory nor --write")
        return remove(args.allowlist, args.remove)
    if args.reports is None:
        ap.error("the reports directory is required, except with --remove")

    findings, errors, sources = load_findings(args.reports)
    current, residuals = allowed.parse(args.allowlist.read_text(encoding="utf-8")
                                       if args.allowlist.is_file() else None)

    if args.write:
        return write(args, findings, errors, sources, current, residuals)

    runtime_observed = {k for k in findings if not allowed.is_static(k)}
    runtime_allowed = {k for k in current if not allowed.is_static(k)}
    on_pr = args.event == "pull_request"
    base = None
    if on_pr:
        base_text = (args.base_allowlist.read_text(encoding="utf-8")
                     if args.base_allowlist is not None and args.base_allowlist.is_file() else None)
        base = allowed.parse(base_text, known_rules=False)[0] if base_text is not None else None
    undecided = stale_undecided(args.tier, args.assurance, sources, errors)
    verdict = allowed.decide(runtime_observed, runtime_allowed, stale_scope=None if undecided else "runtime")
    signed: list[str] = []
    grown = sorted(current - base) if base is not None else []  # the whole list, static keys included, may only shrink
    lowered: list[str] = []
    unreadable_modes = None
    if on_pr and args.base_modes is not None:
        try:  # named and absent is a failed read of the base, never "nothing to compare" (#332 review, F7)
            lowered = allowed.lowered_modes(base_modes(args.base_modes), modes.MODES)
        except (Exception, SystemExit) as exc:  # noqa: BLE001  (the base's file, run as code: unread signs nothing)
            unreadable_modes = f"{type(exc).__name__}: {str(exc)[:200]}"
    # An accepted residual, and a lowered mode, are the operator's (spec §5): each counts only when the pull request
    # carries the operator-merge label, read live, which reserves the merge for the operator (AGENTS.md §5): the
    # operator's merge is the sign-off. A label that cannot be read signs nothing.
    labels = live_labels(args.repo, args.pr) if lowered or any(k in residuals for k in grown) else []
    operator_merge = OPERATOR_LABEL in (labels or [])
    signed = [k for k in grown if k in residuals and operator_merge]
    verdict.grown = [k for k in grown if k not in signed]
    verdict.failing = sorted({*verdict.failing, *verdict.grown})
    verdict.lowered = [] if operator_merge else lowered
    lines = [f"D2 ({'pull request' if on_pr else 'ratchet: ' + args.event}): {len(sources)} findings file(s), "
             f"{len(runtime_observed)} runtime key(s) observed, {len(runtime_allowed)} allow-listed",
             "modes: " + ", ".join(f"{r} {m}" for r, m in modes.MODES.items())]
    # What fails comes first, whatever follows it: a long report must not bury the reason a run is red.
    if errors:
        # An output that failed to be judged is not a pass: a crash in a rule would hide its findings.
        lines.append(f"FAIL capture errors (outputs left unjudged): {sum(errors.values())}")
        lines += [f"  {n} x {name}" for name, n in sorted(errors.items())[:20]]
        if len(errors) > 20:
            lines.append(f"  ... and {len(errors) - 20} more kinds")
    if unreadable_modes:
        lines.append(f"FAIL the base's modes.py cannot be read, so a lowered mode cannot be ruled out: "
                     f"{unreadable_modes}")
    lines += [f"FAIL mode {r}: lowered from enforce against the base. A mode changes only by the operator's decision: "
              f"restore it, or the `{OPERATOR_LABEL}` label reserves the merge for the operator (add the label, then "
              "Re-run all jobs)" for r in verdict.lowered]
    if operator_merge:
        lines += [f"accepted mode {r} lowered (the `{OPERATOR_LABEL}` label: the operator merges)" for r in lowered]
    for key in verdict.grown:
        if key in residuals:
            lines.append(f"FAIL residual {key}: new against the base, and the pull request lacks the "
                         f"`{OPERATOR_LABEL}` label (an accepted residual is the operator's)")
    lines += [f"accepted residual {k} (the `{OPERATOR_LABEL}` label: the operator merges)" for k in signed]
    lines += allowed.report(verdict, details=findings)
    if undecided:
        lines.append(f"stale keys not decided: {undecided}")
    if not sources:
        lines.append("no findings file: no lane job of this run captured (nothing to decide)")
    print("\n".join(lines))
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write("## D2: output and text rules\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 0 if verdict.ok and not errors and not unreadable_modes else 1


def live_labels(repo: str | None, pr: str | None) -> list[str] | None:
    """The pull request's labels now, through the tier tool's own live read (``None`` if they cannot be read)."""
    spec = importlib.util.spec_from_file_location("tier", ROOT / "tools" / "ci" / "tier.py")
    tier = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(tier)  # type: ignore[union-attr]
    return tier.live_labels(repo or "", pr or "")


if __name__ == "__main__":
    raise SystemExit(main())
