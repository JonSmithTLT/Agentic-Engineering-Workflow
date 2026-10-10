#!/usr/bin/env python3
"""The CI tier of a change: which lanes the merge gate requires (CI redesign P1; testing-and-ci-strategy.md §3).

Fail closed: ``full`` unless every changed path is provably documentation (``docs``) or documentation plus the
dashboard frontend (``web``). A push to ``main``, a merge group, a manual run, an empty diff or a diff that cannot be
computed is always ``full``. ``main``'s push run is the compensating control for the reduced tiers: a personal-account
repository has no merge queue, so a reduced-tier change is first run in full by the next ``main`` push run, which
verifies the cumulative tip (a superseded pending run may be cancelled; strategy §3).

    python tools/ci/tier.py --event pull_request --base-ref main --base SHA --head SHA [--github-output FILE]
    python tools/ci/tier.py --event pull_request --base-ref main --paths-file changed.txt
    python tools/ci/tier.py --jobs-for TIER --jobs changes=success,core=success,lanes=skipped,web=success,...
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

TIERS = ("docs", "web", "full")
# The lanes each tier requires: `core` runs the fast and serial lanes (every docs, ledger, register and link test).
LANES = {"docs": ("fast", "serial"), "web": ("fast", "serial"),
         "full": ("fast", "serial", "integration", "acceptance", "regression", "adversarial")}
REDUCED_EVENTS = frozenset({"pull_request"})  # every other event is always full
# A reduced tier only for a pull request into main: a pull request into another branch can be retargeted to main
# without a new run, so its run must already be the full one (review of PR #99, finding 6).
REDUCED_BASES = frozenset({"main"})
# The jobs assurance needs, each of which must have succeeded; `lanes` too, unless the tier is known and reduced.
JOBS = ("changes", "core", "lanes", "web", "static")

# Paths that look like documentation but that code or a non-core test reads: a change to one is a code change.
SHARED = (
    "docs/design/dashboard-api-v1-provisional.yaml",  # the dashboard contract: the Python server and web/ both bind it
    "web/docs/c0-approval.json",  # the contract's approval digest, read by src/aew/dashboard/contract.py
    # The contract 0.1.3 change note (register F20.8): its appendix's routes are probed by the dashboard's integration
    # tests (tests/helpers/dashboard_contract.py), and its status line sets how the contract is checked.
    "docs/design/proposals/dashboard-maps-and-history-search-v0.1.md",
)
CODE_ROOTS = ("src/", "tests/", ".github/", "tools/")  # a Markdown file under one of these is not documentation


def classify_path(path: str) -> str:
    """The least tier that covers one changed path (``/``-separated, relative to the repository root). Compared
    case-folded: a Windows checkout puts ``Src/x.md`` in ``src/`` (review of PR #99, finding 5)."""
    folded = path.casefold()
    if folded in SHARED:
        return "full"
    if folded.startswith("docs/"):
        return "docs"
    if folded.endswith(".md") and not folded.startswith(CODE_ROOTS):
        return "docs"
    if folded.startswith("web/"):
        return "web"
    return "full"


def tier_of(paths: list[str]) -> str:
    """The tier of a whole change: the widest tier any path needs; ``full`` for an empty change."""
    if not paths:
        return "full"
    return max((classify_path(p) for p in paths), key=TIERS.index)


def decide(event: str, paths: list[str] | None, base_ref: str) -> str:
    """The tier for ``event``: reduced tiers only for a pull request into ``main`` whose diff is known."""
    if event not in REDUCED_EVENTS or base_ref not in REDUCED_BASES or paths is None:
        return "full"
    return tier_of(paths)


def job_problems(tier: str, results: dict[str, str]) -> list[str]:
    """Why the jobs ``assurance`` needs do not satisfy ``tier``: every one succeeded, except ``lanes``, which is
    skipped exactly when the tier is known and reduced. An unknown tier requires everything. Python, not a shell
    ``&&`` chain, whose middle failures ``bash -e`` ignores (review of PR #99, finding 1)."""
    problems = []
    for job in JOBS:
        got = results.get(job, "missing")
        want = "skipped" if job == "lanes" and tier in ("docs", "web") else "success"
        if got != want:
            problems.append(f"{job}: {got}, {want} required in the {tier or 'unknown'} tier")
    return problems


def changed_paths(base: str, head: str) -> list[str] | None:
    """The paths a pull request changes against its merge base, or ``None`` if git cannot say."""
    if not base or not head or set(base) == {"0"}:
        return None
    try:
        out = subprocess.run(["git", "diff", "--no-renames", "--name-only", f"{base}...{head}"],
                             capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"tier: cannot diff {base}...{head}: {exc}", file=sys.stderr)
        return None
    return [line for line in out.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--event", default="", help="the GitHub event name")
    ap.add_argument("--base-ref", default="", help="the pull request's base branch")
    ap.add_argument("--base", default="", help="the pull request's base commit")
    ap.add_argument("--head", default="", help="the pull request's head commit")
    ap.add_argument("--paths-file", type=Path, help="changed paths, one per line (instead of --base/--head)")
    ap.add_argument("--github-output", type=Path, help="append tier=<tier> and lanes=<csv> here ($GITHUB_OUTPUT)")
    ap.add_argument("--jobs-for", metavar="TIER", help="instead: check the needed jobs' results for this tier")
    ap.add_argument("--jobs", default="", help="with --jobs-for: name=result pairs, comma-separated")
    args = ap.parse_args(argv)
    if args.jobs_for is not None:
        results = dict(pair.split("=", 1) for pair in args.jobs.split(",") if "=" in pair)
        problems = job_problems(args.jobs_for, results)
        print(f"jobs: {args.jobs or '-'} (tier {args.jobs_for or 'unknown'})")
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1 if problems else 0
    if args.paths_file:
        paths: list[str] | None = [line.strip() for line in args.paths_file.read_text(encoding="utf-8").splitlines()
                                   if line.strip()]
    else:
        paths = changed_paths(args.base, args.head) if args.event in REDUCED_EVENTS else None
    tier = decide(args.event, paths, args.base_ref)
    print(f"tier={tier} ({args.event}, {'unknown diff' if paths is None else f'{len(paths)} changed path(s)'})")
    if paths:
        wider = [p for p in paths if classify_path(p) == tier] if tier != "docs" else []
        for p in wider[:20]:
            print(f"  {tier}: {p}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"tier={tier}\nlanes={','.join(LANES[tier])}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
