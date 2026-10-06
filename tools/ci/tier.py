#!/usr/bin/env python3
"""The CI tier of a change: which lanes the merge gate requires (CI redesign P1; testing-and-ci-strategy.md §3).

Fail closed: ``full`` unless every changed path is provably documentation (``docs``) or documentation plus the
dashboard frontend (``web``). A push to ``main``, a merge group, a manual run, an empty diff or a diff that cannot be
computed is always ``full``. ``main``'s push run is the compensating control for the reduced tiers: a personal-account
repository has no merge queue, so a reduced-tier change is first run in full when it lands.

    python tools/ci/tier.py --event pull_request --base SHA --head SHA [--github-output FILE]
    python tools/ci/tier.py --event pull_request --paths-file changed.txt
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

# Paths that look like documentation but that code or a non-core test reads: a change to one is a code change.
SHARED = (
    "docs/design/dashboard-api-v1-provisional.yaml",  # the dashboard contract: the Python server and web/ both bind it
    "web/docs/c0-approval.json",  # the contract's approval digest, read by src/aew/dashboard/contract.py
)
CODE_ROOTS = ("src/", "tests/", ".github/", "tools/")  # a Markdown file under one of these is not documentation


def classify_path(path: str) -> str:
    """The least tier that covers one changed path (``/``-separated, relative to the repository root)."""
    if path in SHARED:
        return "full"
    if path.startswith("docs/"):
        return "docs"
    if path.endswith(".md") and not path.startswith(CODE_ROOTS):
        return "docs"
    if path.startswith("web/"):
        return "web"
    return "full"


def tier_of(paths: list[str]) -> str:
    """The tier of a whole change: the widest tier any path needs; ``full`` for an empty change."""
    if not paths:
        return "full"
    return max((classify_path(p) for p in paths), key=TIERS.index)


def decide(event: str, paths: list[str] | None) -> str:
    """The tier for ``event``: reduced tiers only for a pull request whose diff is known."""
    if event not in REDUCED_EVENTS or paths is None:
        return "full"
    return tier_of(paths)


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
    ap.add_argument("--event", required=True, help="the GitHub event name")
    ap.add_argument("--base", default="", help="the pull request's base commit")
    ap.add_argument("--head", default="", help="the pull request's head commit")
    ap.add_argument("--paths-file", type=Path, help="changed paths, one per line (instead of --base/--head)")
    ap.add_argument("--github-output", type=Path, help="append tier=<tier> and lanes=<csv> here ($GITHUB_OUTPUT)")
    args = ap.parse_args(argv)
    if args.paths_file:
        paths: list[str] | None = [line.strip() for line in args.paths_file.read_text(encoding="utf-8").splitlines()
                                   if line.strip()]
    else:
        paths = changed_paths(args.base, args.head) if args.event in REDUCED_EVENTS else None
    tier = decide(args.event, paths)
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
