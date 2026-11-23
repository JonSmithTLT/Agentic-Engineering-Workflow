#!/usr/bin/env python3
"""The CI tier of a change: which lanes the merge gate requires (CI redesign P1; testing-and-ci-strategy.md §3).

Only a pull request into main with a known documentation or dashboard-only diff may run a reduced tier.
A verified edit to the flake register also runs the docs tier. Other inputs, pushes and forced runs are full.

The diff is the tested tree's: ``GITHUB_SHA`` on a pull request is the merge commit GitHub tests, and its first
parent is the base tip (plan v7 §1.1). Anything but a two-parent merge is ``full``.

    python tools/ci/tier.py --event pull_request --base-ref main --merge-ref SHA [--repo O/R --pr N | --labels L,...]
        [--github-output FILE] [--record FILE] [--ran TIER]
    python tools/ci/tier.py --event pull_request --base-ref main --paths-file changed.txt
    python tools/ci/tier.py --jobs-for TIER --jobs changes=success,core=success,...
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

TIERS = ("docs", "web", "full")
# The lanes each tier requires: `core` runs the fast and serial lanes (every docs, ledger, register and link test).
LANES = {"docs": ("fast", "serial"), "web": ("fast", "serial"),
         "full": ("fast", "serial", "integration", "acceptance", "regression", "adversarial")}
REDUCED = ("docs", "web")
# Not a tier of the paths: a `full` run whose lanes are an earlier run's (tools/ci/pin_shortcut.py). `assurance` judges
# those reports in full, so its job check is the one place this differs: no lane job of its own may have run.
REUSED = "reused"
REDUCED_EVENTS = frozenset({"pull_request"})  # every other event is always full
# A reduced tier only for a pull request into main: a pull request into another branch can be retargeted to main
# without a new run, so its run must already be the full one (review of PR #99, finding 6).
REDUCED_BASES = frozenset({"main"})
JOBS = ("changes", "core", "lanes", "web", "static")
# CI's own code. A pull request touching it never takes the pin-only shortcut: `core` holds the tests of this code, and
# a shortcut in the merge gate mustn't judge its own change (review of the shortcut, F3).
CI_CODE = ("tools/ci/", ".github/", "tests/helpers/lanes.py")
FORCE_LABEL = "full-ci"
FORCE_TRAILER = "CI-Full"

# Paths that look like documentation but that code or a non-core test reads: a change to one is a code change.
SHARED = (
    "docs/design/dashboard-api-v1-provisional.yaml",  # the dashboard contract: the Python server and web/ both bind it
    "web/docs/c0-approval.json",  # the contract's approval digest, read by src/aew/dashboard/contract.py
    # The contract 0.1.3 change note (register F20.8): its appendix's routes are probed by the dashboard's integration
    # tests (tests/helpers/dashboard_contract.py), and its status line sets how the contract is checked.
    "docs/design/proposals/dashboard-maps-and-history-search-v0.1.md",
    # The contract 0.1.4 change note (register F46.1, slice F1b): read the same way, its appendix merged into 0.1.3.
    "docs/design/proposals/dashboard-configuration-read-v0.1.md",
    # The surface map: its probes are what a worker's agent can run, which the non-writer and containment integration
    # tests run (tests/helpers/worker_surface.py; review of #231, m7).
    "docs/implementation/surface-map.yaml",
)
# A Markdown file under one of these is not documentation. `eval/` joined in plan v7 (§3.3, V3-4): the dogfood
# regression reads eval/m3/dogfood, Markdown included.
CODE_ROOTS = ("src/", "tests/", ".github/", "tools/", "eval/")

FLAKE_REGISTER = "tests/flake-register.yaml"
FAST_LANES = frozenset({"fast", "serial"})
ROOT = Path(__file__).resolve().parents[2]

FORCED_MESSAGE = ("`full-ci` is set but this run took a reduced tier: Re-run all jobs (or push a `CI-Full: yes` "
                  "commit).")
# The forced flag could not be read in the recompute (a `gh api` or git failure): not the author's label (PR #163
# review, V7-1).
UNREADABLE_MESSAGE = ("the forced flag could not be read (the `gh api` label call or git failed), so the recompute is "
                      "full and this run took a reduced tier: Re-run all jobs.")


def classify_path(path: str) -> str:
    """The least of ``docs``, ``web`` and ``full`` that covers one changed path (``/``-separated, relative to the
    repository root). Compared case-folded: a Windows checkout puts ``Src/x.md`` in ``src/`` (review of PR #99,
    finding 5)."""
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
    """Use the widest tier required by any path. An empty change runs in full."""
    kinds = {classify_path(path) for path in paths}
    if not kinds or "full" in kinds:
        return "full"
    return "web" if "web" in kinds else "docs"


def decide(event: str, paths: list[str] | None, base_ref: str,
           forced: bool = False,
           register_valid: bool = False) -> str:
    """The decision for ``event``: reduced tiers only for a pull request into ``main`` whose diff is known and
    which is not forced full."""
    if event not in REDUCED_EVENTS or base_ref not in REDUCED_BASES or paths is None or forced:
        return "full"
    if FLAKE_REGISTER in paths:
        return "docs" if paths == [FLAKE_REGISTER] and register_valid else "full"
    return tier_of(paths)


def covers(ran: str, recomputed: str) -> bool:
    """The tier the jobs ran under is not narrower than the recomputed one (plan v7 §4): the same, or ``full``."""
    return ran in TIERS and (ran == recomputed or ran == "full")


def shortcut_barred(paths: list[str] | None) -> bool:
    """Whether these changed paths, or not knowing them, rule out the pin-only shortcut."""
    flake_inputs = {FLAKE_REGISTER, "tools/flake_register.py"}
    return paths is None or any(path.startswith(CI_CODE) or path in flake_inputs for path in paths)


def job_problems(tier: str, results: dict[str, str]) -> list[str]:
    """Why the jobs ``assurance`` needs do not satisfy ``tier``: every one succeeded, except ``lanes``, which is
    skipped for reduced tiers. A reused run skips both core and lanes."""
    problems = []
    for job in JOBS:
        got = results.get(job, "missing")
        skipped = (job == "lanes" and tier in REDUCED) or (job in ("core", "lanes") and tier == REUSED)
        want = "skipped" if skipped else "success"
        if got != want:
            problems.append(f"{job}: {got}, {want} required in the {tier or 'unknown'} tier")
    return problems


# ------------------------------------------------------------------ git and GitHub


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def merge_paths(merge_ref: str) -> list[str] | None:
    """The paths the merge commit ``merge_ref`` changes against its first parent (the base tip), renames listed as
    both sides; ``None`` if it is not a two-parent merge or git cannot say."""
    if not merge_ref:
        return None
    try:
        parents = _run(["git", "rev-list", "--parents", "-n", "1", merge_ref]).stdout.split()
        if len(parents) != 3:
            print(f"tier: {merge_ref} is not a two-parent merge", file=sys.stderr)
            return None
        out = _run(["git", "diff", "--no-renames", "--name-only", f"{merge_ref}^1", merge_ref]).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"tier: cannot diff {merge_ref}^1 {merge_ref}: {exc}", file=sys.stderr)
        return None
    return [line for line in out.splitlines() if line.strip()]


def show(rev: str, path: str) -> str | None:
    try:
        return _run(["git", "show", f"{rev}:{path}"]).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def verified_register_edit(merge_ref: str) -> bool:
    """Both parents exist and the tested merge modifies the existing regular register in place."""
    try:
        parents = _run(["git", "rev-list", "--parents", "-n", "1", merge_ref]).stdout.split()
        if len(parents) != 3 or any(rev_parse(f"{parent}^{{commit}}") != parent for parent in parents):
            return False
        for rev in (parents[1], parents[0]):
            tree = _run(["git", "ls-tree", rev, "--", FLAKE_REGISTER]).stdout
            if not tree.startswith("100644 blob "):
                return False
        helpers = str(ROOT / "tools")
        if helpers not in sys.path:
            sys.path.insert(0, helpers)
        from flake_register import load_register, validate_history

        text, base = (show(parent, FLAKE_REGISTER) for parent in parents[:2])
        if text is None or base is None:
            return False
        validate_history(load_register(base, source=lambda path: show(parents[1], path)),
                         load_register(text, source=lambda path: show(parents[0], path)))
    except (OSError, subprocess.CalledProcessError, ImportError, ValueError):
        return False
    return True


def rev_parse(rev: str) -> str | None:
    if rev.startswith("^"):
        return None
    try:
        return _run(["git", "rev-parse", "--verify", "--quiet", rev]).stdout.strip() or None
    except (OSError, subprocess.CalledProcessError):
        return None


def forced_by_trailer(merge_ref: str) -> bool | None:
    """A ``CI-Full: yes`` trailer on the pull request's head commit (the merge's second parent); ``None`` if git
    cannot say."""
    try:
        out = _run(["git", "log", "-1", f"--format=%(trailers:key={FORCE_TRAILER},valueonly)",
                    f"{merge_ref}^2"]).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return any(v.strip().casefold() == "yes" for v in out.splitlines())


def live_labels(repo: str, pr: str) -> list[str] | None:
    """The pull request's labels now (not the event's copy), or ``None`` if they cannot be read. One retry: a
    transient API failure would otherwise make the run full (PR #163 review, V7-1). Up to 100 labels (V7-5)."""
    if not repo or not pr:
        return None
    for attempt in (1, 2):
        try:
            out = _run(["gh", "api", f"repos/{repo}/issues/{pr}/labels?per_page=100", "--jq", ".[].name"]).stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"tier: cannot read the labels of {repo}#{pr} (attempt {attempt}): {exc}", file=sys.stderr)
            if attempt == 1:
                time.sleep(3)
            continue
        return [line.strip() for line in out.splitlines() if line.strip()]
    return None


# ------------------------------------------------------------------ the command line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--event", default="", help="the GitHub event name")
    ap.add_argument("--base-ref", default="", help="the pull request's base branch")
    ap.add_argument("--merge-ref", default="", help="the merge commit under test ($GITHUB_SHA on a pull request)")
    ap.add_argument("--paths-file", type=Path, help="changed paths, one per line (instead of --merge-ref)")
    ap.add_argument("--repo", default="", help="owner/name, to read the pull request's labels live")
    ap.add_argument("--pr", default="", help="the pull request's number, to read its labels live")
    ap.add_argument("--labels", help="the labels, comma-separated (instead of reading them live)")
    ap.add_argument("--github-output", type=Path, help="append the tier, lanes and reuse eligibility here")
    ap.add_argument("--record", type=Path, help="write the decision record (JSON) here")
    ap.add_argument("--ran", help="fail unless this tier (the one the jobs ran under) covers the recomputed one")
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

    reasons: list[str] = []
    paths: list[str] | None = None
    register_valid = False
    if args.paths_file:
        paths = [line.strip() for line in args.paths_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif args.event in REDUCED_EVENTS:
        paths = merge_paths(args.merge_ref)
        if paths is None:
            reasons.append("the merge commit's diff is unknown")
        elif paths == [FLAKE_REGISTER]:
            register_valid = verified_register_edit(args.merge_ref)
            if not register_valid:
                reasons.append("the register edit or merge parents could not be verified")
    forced = False
    unreadable = False
    reduced = decide(args.event, paths, args.base_ref, register_valid=register_valid) != "full"
    if reduced:  # the forced flag only matters when the paths alone would reduce the run
        trailer = forced_by_trailer(args.merge_ref) if args.merge_ref else False
        if args.labels is not None:  # given (tests, dry runs): an empty string is no label
            labels: list[str] | None = [x for x in args.labels.split(",") if x]
        else:
            labels = live_labels(args.repo, args.pr)
        if trailer is None or labels is None:
            forced = unreadable = True
            reasons.append("the forced flag cannot be read (label or trailer): full")
        elif trailer or FORCE_LABEL in labels:
            forced = True
            reasons.append(f"forced full ({FORCE_TRAILER}: yes)" if trailer else f"forced full (label {FORCE_LABEL})")
    tier = decide(args.event, paths, args.base_ref, forced=forced, register_valid=register_valid)
    print(f"tier={tier} ({args.event}, {'unknown diff' if paths is None else f'{len(paths)} changed path(s)'})")
    for r in reasons:
        print(f"  {r}")
    if paths and tier != "docs":
        for p in [p for p in paths if classify_path(p) == tier][:20]:
            print(f"  {tier}: {p}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"tier={tier}\nlanes={','.join(LANES[tier])}\n"
                     f"reusable={'false' if shortcut_barred(paths) else 'true'}\n")
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        record = {"schema": "aew/tier-decision/v2", "event": args.event, "base_ref": args.base_ref,
                  "merge": args.merge_ref or None, "base": rev_parse(f"{args.merge_ref}^1"),
                  "head": rev_parse(f"{args.merge_ref}^2"), "tier": tier,
                  "forced": forced, "reasons": reasons, "paths": paths}
        args.record.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    if args.ran is not None and not covers(args.ran, tier):
        if unreadable and args.ran in REDUCED:
            print(UNREADABLE_MESSAGE, file=sys.stderr)
        elif forced and args.ran in REDUCED:
            print(FORCED_MESSAGE, file=sys.stderr)
        else:
            print(f"tier: the jobs ran under {args.ran or 'an unknown tier'}, narrower than the recomputed {tier}",
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
