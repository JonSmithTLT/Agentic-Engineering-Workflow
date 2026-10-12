#!/usr/bin/env python3
"""D2's ratchet over a CI run (discovery-layer spec v3.4, §5; docs/implementation/vertical-uat.md §8.3).

Merges the findings every lane job wrote beside its lane report (``*.discovery.json``, schema
``aew/discovery-findings/v1``) and decides them against the allow-list (``tests/helpers/discovery/allowed.yaml``):

- ``--event pull_request``: a key not on the list is new (reported; failing when its rule is in ``enforce``), and a
  key added to the list relative to ``--base-allowlist`` fails whatever its mode. The one exception is an accepted
  residual, which is the operator's: it passes only while the pull request carries the ``operator-merge`` label, read
  live (``--repo``, ``--pr``).
- any other event (main's push run, nightly): a listed runtime key not observed anywhere in the run is also stale
  (reported; failing when its rule is in ``enforce``). Static keys are decided by the fast lane's test and the
  ``discovery`` lane, over the complete scan.
- Any capture error fails the run: an output left unjudged is not a pass.

``--write`` regenerates the allow-list from the run instead (introducing D2, or removing stale keys): it refuses to add
a key that the current list lacks unless ``--introduce`` is given, which only the pull request introducing D2 uses.

    python tools/ci/discovery_ratchet.py REPORTS_DIR --event pull_request --base-allowlist BASE.yaml [--summary F]
    python tools/ci/discovery_ratchet.py REPORTS_DIR --event push [--summary F]
    python tools/ci/discovery_ratchet.py REPORTS_DIR --write [--introduce] [--static GUIDES_DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "helpers"))

from discovery import allowed, modes  # noqa: E402

FINDINGS_SCHEMA = "aew/discovery-findings/v1"
OPERATOR_LABEL = "operator-merge"  # AGENTS.md §5: a pull request with it is merged by the operator


def load_findings(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, int], list[str]]:
    """``(findings by key, capture errors, sources)`` merged over every findings file under ``root``."""
    findings: dict[str, dict[str, Any]] = {}
    errors: dict[str, int] = {}
    sources = []
    for path in sorted(root.rglob("*.json")) if root.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not isinstance(data, dict) or data.get("schema") != FINDINGS_SCHEMA:
            continue
        sources.append(str(path.relative_to(root)))
        for key, entry in (data.get("findings") or {}).items():
            mine = findings.setdefault(key, {**entry, "count": 0})
            mine["count"] += int(entry.get("count") or 0)
        for name, n in (data.get("errors") or {}).items():
            errors[name] = errors.get(name, 0) + int(n)
    return findings, errors, sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", type=Path)
    ap.add_argument("--event", default="pull_request")
    ap.add_argument("--allowlist", type=Path, default=allowed.PATH)
    ap.add_argument("--base-allowlist", type=Path, default=None,
                    help="the base branch's allow-list on a pull request (absent: the base has none)")
    ap.add_argument("--repo", default=None, help="OWNER/REPO, to read the pull request's labels live")
    ap.add_argument("--pr", default=None, help="the pull request's number, to read its labels live")
    ap.add_argument("--summary", type=Path, default=None, help="append a Markdown report (GITHUB_STEP_SUMMARY)")
    ap.add_argument("--write", action="store_true", help="regenerate the allow-list from the run's findings")
    ap.add_argument("--introduce", action="store_true", help="with --write: allow keys the current list lacks")
    ap.add_argument("--static", type=Path, default=None, metavar="GUIDES_DIR",
                    help="with --write: include the static scan's keys, reading the operator guides from this "
                         "directory (the repository's docs/guides)")
    args = ap.parse_args(argv)

    findings, errors, sources = load_findings(args.reports)
    current, residuals = allowed.parse(args.allowlist.read_text(encoding="utf-8")
                                       if args.allowlist.is_file() else None)

    if args.write:
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
        args.allowlist.write_text(allowed.render(keys, residuals.values()), encoding="utf-8", newline="\n")
        print(f"wrote {args.allowlist} ({len(keys)} keys, from {len(sources)} findings file(s))")
        return 0

    runtime_observed = {k for k in findings if not allowed.is_static(k)}
    runtime_allowed = {k for k in current if not allowed.is_static(k)}
    on_pr = args.event == "pull_request"
    base = None
    if on_pr:
        base_text = (args.base_allowlist.read_text(encoding="utf-8")
                     if args.base_allowlist is not None and args.base_allowlist.is_file() else None)
        base = allowed.parse(base_text)[0] if base_text is not None else None
    # Stale only over a run that captured at all: with no findings file, absence proves nothing.
    verdict = allowed.decide(runtime_observed, runtime_allowed, stale_scope=None if on_pr or not sources else "runtime")
    signed: list[str] = []
    if base is not None:  # the whole list, static keys included, may only shrink
        grown = sorted(current - base)
        # An accepted residual is the operator's (spec §5): a residual new against the base counts only when the
        # pull request carries the operator-merge label, read live, which reserves the merge for the operator
        # (AGENTS.md §5): the operator's merge is the sign-off. A label that cannot be read signs nothing.
        labels = live_labels(args.repo, args.pr) if any(k in residuals for k in grown) else []
        operator_merge = OPERATOR_LABEL in (labels or [])
        signed = [k for k in grown if k in residuals and operator_merge]
        verdict.grown = [k for k in grown if k not in signed]
        verdict.failing = sorted({*verdict.failing, *verdict.grown})
    lines = [f"D2 ({'pull request' if on_pr else 'ratchet: ' + args.event}): {len(sources)} findings file(s), "
             f"{len(runtime_observed)} runtime key(s) observed, {len(runtime_allowed)} allow-listed",
             "modes: " + ", ".join(f"{r} {m}" for r, m in modes.MODES.items()),
             *allowed.report(verdict)]
    for key in verdict.grown:
        if key in residuals:
            lines.append(f"  FAIL residual {key}: new against the base, and the pull request lacks the "
                         f"`{OPERATOR_LABEL}` label (an accepted residual is the operator's)")
    lines += [f"  accepted residual {k} (the `{OPERATOR_LABEL}` label: the operator merges)" for k in signed]
    if errors:
        # An output that failed to be judged is not a pass: a crash in a rule would hide its findings.
        lines.append(f"FAIL capture errors (outputs left unjudged): {sum(errors.values())}")
        lines += [f"  {n} x {name}" for name, n in sorted(errors.items())[:20]]
    if not sources:
        lines.append("no findings file: no lane job of this run captured (nothing to decide)")
    print("\n".join(lines))
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write("## D2: output and text rules\n\n```\n" + "\n".join(lines) + "\n```\n")
    return 0 if verdict.ok and not errors else 1


def live_labels(repo: str | None, pr: str | None) -> list[str] | None:
    """The pull request's labels now, through the tier tool's own live read (``None`` if they cannot be read)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("tier", ROOT / "tools" / "ci" / "tier.py")
    tier = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(tier)  # type: ignore[union-attr]
    return tier.live_labels(repo or "", pr or "")


if __name__ == "__main__":
    raise SystemExit(main())
