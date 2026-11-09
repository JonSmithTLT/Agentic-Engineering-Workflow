#!/usr/bin/env python3
"""Reuse an earlier run's lane reports when a pull request's new commits change only the platform-skip pins.

Every test ran and passed, and `assurance` went red only because a skip wasn't pinned. Pinning it can't change what any
test does, so running every lane again for an hour proves nothing new (the operator, 2026-11-08: "yes stack them, and
build the pin-only shortcut"). This names the run whose reports `assurance` may judge instead, or nothing, and then the
run takes its normal tier. It never decides the gate: `check_assurance.py` still judges those reports against the new
head's pins, as it judges any run's, so too few pins or too many fail, and no pin can forgive a failed test.

**When it names a run, all of which it checks itself:**
- the event is a pull request into ``main``, from this repository, with no ``full-ci`` label or ``CI-Full: yes``
  trailer;
- the new head descends from the earlier head only through single-parent commits that each change nothing but
  ``tests/platform-skips.yaml``, by their git trees, so a merge of ``main`` or any other path ends the walk;
- ``ci.yml`` has a finished pull-request run at that exact earlier head, and every job of its latest attempt but
  ``assurance`` succeeded or was skipped;
- its lane reports and coverage can still be read, and the only thing `assurance` can say of them under that head's own
  pins is about skips: so a failed test, a test that never ran or a lost shard means no shortcut.

**Anything else, or any error at all, is the normal tier.** That includes a run cancelled by the new push, reports past
their 14 days, coverage past its 7, and a pull request from a fork, whose token and history this doesn't rely on.

**What it accepts on purpose:** the heads are compared, not the merge commits. If ``main`` moved between the two heads,
the reports are of the older merge. A pull request whose run went green while ``main`` moved merges today without a
re-run, with ``main``'s full push run behind it (strategy §3), so this adds no exposure beyond that. To tighten it, have
:func:`pin_only_ancestors` also require the earlier run's merge commit to have the new base as its first parent.

Nothing runs on a push to ``main``, the nightly or a ``full-ci`` run, which stay in full.

    python tools/ci/pin_shortcut.py --event pull_request --base-ref main --merge-ref SHA --repo O/R --pr N \\
        --head-repo O/R --reports-dir DIR [--github-output FILE] [--summary FILE] [--expect RUN_ID]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_assurance  # noqa: E402  (tools/ci/check_assurance.py)
import tier as tiers  # noqa: E402  (tools/ci/tier.py)
import yaml  # noqa: E402

PINS = "tests/platform-skips.yaml"
WORKFLOW = "ci.yml"
GATE_JOB = "assurance"  # the one job whose red this exists for
MAX_WALK = 10  # a limit on API calls, not a rule: a longer chain of pin commits takes the normal tier
# What `check_assurance.check` says of a skip, and nothing else it says: a failure, a test that never ran, a lost shard
# and an unpinned xfail stay out, so they can't count as "only about skips".
SKIP_COMPLAINT = re.compile(rf"^({'|'.join(check_assurance.REQUIRED_PLATFORMS)}): "
                            "(unexpected skip: |pinned skip now |pinned skip no longer exists: )")


class NoShortcut(Exception):
    """Why this run takes its normal tier: it says so in the log, and it isn't a failure."""


# A call that hangs is the step's `timeout-minutes` in ci.yml, and so the normal tier, or a failed `assurance`.
def _git(*args: str) -> str:
    return tiers._run(["git", *args]).stdout


def _gh_json(path: str) -> Any:
    return json.loads(tiers._run(["gh", "api", path]).stdout)


def pin_only_ancestors(head: str, limit: int = MAX_WALK) -> Iterator[str]:
    """Each ancestor of ``head``, nearest first, that it reaches through commits changing only the pins. It stops at the
    first merge, root commit or commit changing anything else: from the trees, whatever the commits say they are."""
    commit = head
    for _ in range(limit):
        parents = _git("rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) != 1:
            return
        changed = _git("diff-tree", "--no-renames", "--name-only", "-r", "-z", parents[0], commit).split("\0")
        if {p for p in changed if p} != {PINS}:
            return
        commit = parents[0]
        yield commit


def earlier_run(repo: str, sha: str) -> dict[str, Any] | None:
    """The newest finished pull-request run of ``ci.yml`` at exactly ``sha``, from this repository."""
    runs = _gh_json(f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?head_sha={sha}&event=pull_request&per_page=10")
    for run in runs.get("workflow_runs") or []:
        same_repo = (run.get("head_repository") or {}).get("full_name") == repo
        if run.get("head_sha") == sha and same_repo:
            return run if run.get("status") == "completed" else None
    return None


def jobs_problem(repo: str, run_id: int) -> str | None:
    """Why this run's jobs don't qualify: its latest attempt's, as the API's default filter gives them."""
    listed = _gh_json(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
    jobs = listed.get("jobs") or []
    if listed.get("total_count") != len(jobs):  # a failure on a page not read must not pass as no failure
        return f"it lists {listed.get('total_count')} jobs and {len(jobs)} were read"
    if not any(j.get("name") == GATE_JOB for j in jobs):
        return f"it has no {GATE_JOB} job"
    for job in jobs:
        if job.get("name") != GATE_JOB and job.get("conclusion") not in ("success", "skipped"):
            return f"its job {job.get('name')} ended {job.get('conclusion') or job.get('status')}"
    return None


def artifact_names(repo: str, run_id: int) -> list[str]:
    listed = _gh_json(f"repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100").get("artifacts") or []
    return [a["name"] for a in listed if not a.get("expired")]


def download_reports(run_id: int, repo: str, dest: Path) -> None:
    tiers._run(["gh", "run", "download", str(run_id), "--repo", repo, "--pattern", "lane-report-*", "--dir", str(dest)])


def forced(merge_ref: str, repo: str, pr: str) -> bool:
    """Whether this run must be full, or that can't be read, which comes to the same thing (as ``tier.py``)."""
    trailer = tiers.forced_by_trailer(merge_ref)
    labels = tiers.live_labels(repo, pr)
    return trailer is None or labels is None or trailer or tiers.FORCE_LABEL in labels


def decide(args: argparse.Namespace) -> dict[str, Any]:
    """The run to reuse (``run_id``, ``head``, ``url``), or :class:`NoShortcut`."""
    if args.event not in tiers.REDUCED_EVENTS or args.base_ref not in tiers.REDUCED_BASES:
        raise NoShortcut(f"{args.event or 'no'} event into {args.base_ref or 'no base'}")
    if args.head_repo != args.repo:
        raise NoShortcut(f"the head is in {args.head_repo or 'an unknown repository'}, not {args.repo}")
    if forced(args.merge_ref, args.repo, args.pr):
        raise NoShortcut(f"{tiers.FORCE_LABEL}, {tiers.FORCE_TRAILER}, or a flag that can't be read")
    parents = _git("rev-list", "--parents", "-n", "1", args.merge_ref).split()
    if len(parents) != 3:
        raise NoShortcut(f"{args.merge_ref} isn't a two-parent merge")
    why = "no earlier head reached through pin-only commits"
    for sha in pin_only_ancestors(parents[2]):
        run = earlier_run(args.repo, sha)
        # Nothing was judged at this head, so an older one may still say: a run replaced by the next push.
        if run is None or run.get("conclusion") == "cancelled":
            why = f"no run at {sha[:8]} ran to its end"
            continue
        # Whereas a run that did run and said something else ends the walk: the same tree, so an older green run would
        # only hide a flake.
        problem = jobs_problem(args.repo, run["id"])
        if problem:
            raise NoShortcut(f"run {run['id']} at {sha[:8]}: {problem}")
        names = artifact_names(args.repo, run["id"])
        # A run that reused its own lanes has none to give, and the first set of pins can be wrong: the second try goes
        # back to the same reports. Reports past their days leave nothing older either, so that ends the same way.
        if not any(name.startswith("lane-report-") for name in names):
            why = f"run {run['id']} at {sha[:8]} has no lane reports"
            continue
        if not any(name.startswith("coverage-") for name in names):
            raise NoShortcut(f"run {run['id']} at {sha[:8]}: its coverage can't be read")
        download_reports(run["id"], args.repo, args.reports_dir)
        # Under that head's own pins, as its `assurance` judged it. The new pins are judged by this run's `assurance`.
        pins = yaml.safe_load(_git("show", f"{sha}:{PINS}")) or {}
        problems = check_assurance.check(check_assurance.load_reports(args.reports_dir), pins,
                                         list(check_assurance.REQUIRED_PLATFORMS))[0]
        others = [p for p in problems if not SKIP_COMPLAINT.match(p)]
        if others:
            raise NoShortcut(f"run {run['id']} at {sha[:8]} says more than skips: {others[0]}")
        return {"run_id": run["id"], "head": sha, "url": run.get("html_url") or ""}
    raise NoShortcut(why)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--event", default="")
    ap.add_argument("--base-ref", default="")
    ap.add_argument("--merge-ref", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--pr", default="")
    ap.add_argument("--head-repo", default="", help="the repository the pull request's head is in")
    ap.add_argument("--reports-dir", type=Path, required=True, help="where the earlier run's reports are put")
    ap.add_argument("--github-output", type=Path, help="append reuse_run= and reuse_head= here")
    ap.add_argument("--summary", type=Path, help="append what was reused (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--expect", help="`assurance`'s recompute: fail unless it names the run the jobs were skipped for")
    args = ap.parse_args(argv)
    try:
        chosen: dict[str, Any] | None = decide(args)
    except NoShortcut as why:
        chosen = None
        print(f"pin shortcut: no: {why}; this run takes its normal tier")
    # Fail closed, whatever went wrong: an unreadable run, a lost report, a shape nobody expected.
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError,
            yaml.YAMLError) as exc:
        chosen = None
        print(f"pin shortcut: no: {type(exc).__name__}: {exc}; this run takes its normal tier")
    if args.expect is not None and str((chosen or {}).get("run_id", "")) != args.expect:
        print(f"pin shortcut: the jobs were skipped for run {args.expect}, but the recompute says "
              f"{(chosen or {}).get('run_id') or 'no shortcut'}: push again, or add `full-ci`", file=sys.stderr)
        return 1
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"reuse_run={(chosen or {}).get('run_id', '')}\nreuse_head={(chosen or {}).get('head', '')}\n")
    if chosen:
        text = (f"## Lanes reused from an earlier run\n\nThis head differs from `{chosen['head']}` only in `{PINS}`, "
                f"so no lane ran here. `assurance` judged the reports of [run {chosen['run_id']}]({chosen['url']}), at "
                "that head, against this head's pins.\n")
        print(text)
        if args.summary:
            with args.summary.open("a", encoding="utf-8") as fh:
                fh.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
