#!/usr/bin/env python3
"""The CI tier of a change: which lanes the merge gate requires (CI redesign P1; testing-and-ci-strategy.md §3).

Fail closed: ``full`` unless every changed path is provably documentation (``docs``), documentation plus the
dashboard frontend (``web``), or documentation plus fast-lane test modules and ``tests/durations.json`` (``fast``,
CI plan v7). A push to ``main``, a merge group, a manual run, an empty diff, a diff that cannot be computed, a
``full-ci`` label or a ``CI-Full: yes`` trailer on the pull request's head commit is always ``full``. ``main``'s push
run is the compensating control for the reduced tiers: a personal-account repository has no merge queue, so a
reduced-tier change is first run in full by the next ``main`` push run, which verifies the cumulative tip (a
superseded pending run may be cancelled; strategy §3).

The diff is the tested tree's: ``GITHUB_SHA`` on a pull request is the merge commit GitHub tests, and its first
parent is the base tip (plan v7 §1.1). Anything but a two-parent merge is ``full``.

Two outputs (plan v7 §6, V6-1): ``decision`` is the tier the paths and the forced flag give, whatever the mode;
``tier`` is the tier the run takes. In ``shadow`` mode (PR 1) a ``fast`` decision runs ``full``, while ``fastbase``
and ``assurance``'s non-gating step compute and report everything the ``fast`` tier would check.

    python tools/ci/tier.py --event pull_request --base-ref main --merge-ref SHA [--repo O/R --pr N | --labels L,...]
        [--github-output FILE] [--record FILE] [--modules-out FILE] [--ran TIER]
    python tools/ci/tier.py --event pull_request --base-ref main --paths-file changed.txt
    python tools/ci/tier.py --jobs-for TIER --jobs changes=success,core=success,... [--modules-changed true
        --checks lanecheck=success,premise=success]
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

TIERS = ("docs", "fast", "web", "full")
# The lanes each tier requires: `core` runs the fast and serial lanes (every docs, ledger, register and link test).
LANES = {"docs": ("fast", "serial"), "fast": ("fast", "serial"), "web": ("fast", "serial"),
         "full": ("fast", "serial", "integration", "acceptance", "regression", "adversarial")}
REDUCED = ("docs", "fast", "web")
REDUCED_EVENTS = frozenset({"pull_request"})  # every other event is always full
# A reduced tier only for a pull request into main: a pull request into another branch can be retargeted to main
# without a new run, so its run must already be the full one (review of PR #99, finding 6).
REDUCED_BASES = frozenset({"main"})
# The jobs assurance needs, each of which must have succeeded; `lanes` too, unless the tier is known and reduced;
# `fastbase` only in the `fast` tier (any result elsewhere: it runs on every `fast` decision, shadow included; V6-1).
JOBS = ("changes", "core", "lanes", "web", "static", "fastbase")
# The two runtime checks a reduced tier with a changed fast-lane test module needs (plan v7 §4, V3-1).
CHECKS = ("lanecheck", "premise")

# The mode (plan v7 §7): `shadow` computes and reports the `fast` tier and never takes it; PR 1b sets `enforce` once
# at least 5 eligible shadow runs decided correctly, the premise check ran in each with no unexplained loss, and the
# audit (unit-isolation-audit.yml) is clean.
MODE = "shadow"
MODES = ("shadow", "enforce")

FORCE_LABEL = "full-ci"
FORCE_TRAILER = "CI-Full"

# Paths that look like documentation but that code or a non-core test reads: a change to one is a code change.
SHARED = (
    "docs/design/dashboard-api-v1-provisional.yaml",  # the dashboard contract: the Python server and web/ both bind it
    "web/docs/c0-approval.json",  # the contract's approval digest, read by src/aew/dashboard/contract.py
)
# A Markdown file under one of these is not documentation. `eval/` joined in plan v7 (§3.3, V3-4): the dogfood
# regression reads eval/m3/dogfood, Markdown included.
CODE_ROOTS = ("src/", "tests/", ".github/", "tools/", "eval/")

# The fast-lane test inputs a `fast`-tier change may touch (plan v7 §1.2). Matched exactly, never case-folded: a
# case variant is not what the lane plugin collects, so it is `full`.
UNIT_DIR = "tests/unit/"
SPEC_PIN = "tests/test_spec_pin.py"
DURATIONS = "tests/durations.json"
FAST_LANES = frozenset({"fast", "serial"})
ROOT = Path(__file__).resolve().parents[2]

FORCED_MESSAGE = ("`full-ci` is set but this run took a reduced tier: Re-run all jobs (or push a `CI-Full: yes` "
                  "commit).")


def classify_path(path: str) -> str:
    """The least of ``docs``, ``web`` and ``full`` that covers one changed path (``/``-separated, relative to the
    repository root). Compared case-folded: a Windows checkout puts ``Src/x.md`` in ``src/`` (review of PR #99,
    finding 5). Fast-lane test inputs are ``full`` here; ``fast_kind`` decides whether they may take the ``fast``
    tier."""
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


def fast_kind(path: str) -> str | None:
    """``module`` for a fast-lane test module path (``tests/unit/**/test_*.py`` or the spec pin), ``durations`` for
    ``tests/durations.json``, else ``None``. The module's tests still have to be in the fast or serial lane."""
    if path == DURATIONS:
        return "durations"
    if path == SPEC_PIN:
        return "module"
    if path.startswith(UNIT_DIR) and path.endswith(".py") and path.rsplit("/", 1)[-1].startswith("test_"):
        return "module"
    return None


# ------------------------------------------------------------------ lanes from markers (plan v7 §3.1)


class NotLiteral(Exception):
    """A test module whose lanes cannot be read from its source alone: the change is ``full``."""


def _is_pytest_attr(node: ast.expr, *chain: str) -> bool:
    """``node`` is ``pytest.<chain...>`` (for example ``pytest.mark``)."""
    for name in reversed(chain):
        if not (isinstance(node, ast.Attribute) and node.attr == name):
            return False
        node = node.value
    return isinstance(node, ast.Name) and node.id == "pytest"


def _marks(node: ast.expr, aliases: Mapping[str, list[str]]) -> list[str]:
    """The mark names a decorator, a ``pytestmark`` value or a ``marks=`` value applies, read literally."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return [m for elt in node.elts for m in _marks(elt, aliases)]
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name) and target.id in aliases:  # POSIX_ONLY = pytest.mark.skipif(...)
        return list(aliases[target.id])
    if isinstance(target, ast.Attribute) and _is_pytest_attr(target.value, "mark"):
        return [target.attr]
    raise NotLiteral(f"a mark that cannot be read literally: {ast.unparse(node)[:80]}")


def _param_marks(tree: ast.AST, aliases: Mapping[str, list[str]]) -> list[list[str]]:
    """The marks of every ``pytest.param(..., marks=...)`` anywhere in the module."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_pytest_attr(node.func, "param"):
            for kw in node.keywords:
                if kw.arg == "marks":
                    found.append(_marks(kw.value, aliases))
                elif kw.arg is None:
                    raise NotLiteral("pytest.param(**...) cannot be read literally")
    return found


def _is_fixture(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _is_pytest_attr(target, "fixture")


def lanes_in_module(path: str, source: str, lane_of: Callable[[str, Iterable[str]], str] | None = None) -> set[str]:
    """Every lane a test of this module runs in, by ``lanes.lane_of`` applied to each test's marks: the module's
    ``pytestmark``, its classes' decorators and ``pytestmark``, its functions' decorators, and every
    ``pytest.param(..., marks=...)`` (combined with every test's marks, a superset of the real pairs). Raises
    ``NotLiteral`` for what cannot be read from the source alone: a non-literal mark or decorator, ``pytest_plugins``,
    a module-level ``pytest_*`` hook or ``@pytest.fixture``, an inherited or imported test, a syntax error."""
    if lane_of is None:
        helpers = str(ROOT / "tests" / "helpers")
        if helpers not in sys.path:
            sys.path.insert(0, helpers)
        from lanes import lane_of  # tests/helpers/lanes.py: the one place lanes are defined
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise NotLiteral(f"does not parse: {exc}") from None
    aliases: dict[str, list[str]] = {}
    module_marks: list[str] = []
    tests: list[list[str]] = []  # each test's marks, module marks excluded

    def module_level(stmts: list[ast.stmt]) -> Iterable[ast.stmt]:
        """The module's statements, through `if`/`try`/`with` blocks (a test defined under one is still collected)."""
        for st in stmts:
            if isinstance(st, ast.If):
                yield from module_level(st.body + st.orelse)
            elif isinstance(st, ast.Try):
                yield from module_level(st.body + [s for h in st.handlers for s in h.body] + st.orelse
                                        + st.finalbody)
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                yield from module_level(st.body)
            else:
                yield st

    statements = list(module_level(tree.body))
    for st in statements:  # names bound to a literal mark (`POSIX_ONLY = pytest.mark.skipif(...)`)
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
            try:
                aliases[st.targets[0].id] = _marks(st.value, aliases)
            except NotLiteral:
                pass

    def collect_class(cls: ast.ClassDef, inherited: list[str]) -> None:
        if [b for b in cls.bases if not (isinstance(b, ast.Name) and b.id == "object")] or cls.keywords:
            raise NotLiteral(f"class {cls.name} inherits its tests")
        marks = inherited + [m for d in cls.decorator_list for m in _marks(d, aliases)]
        for st in cls.body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in st.targets):
                marks = marks + _marks(st.value, aliases)
        for st in cls.body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)) and st.name.startswith("test"):
                tests.append(marks + [m for d in st.decorator_list for m in _marks(d, aliases)])
            elif isinstance(st, ast.ClassDef) and st.name.startswith("Test"):
                collect_class(st, marks)

    for st in statements:
        if isinstance(st, (ast.Assign, ast.AnnAssign)):
            targets = st.targets if isinstance(st, ast.Assign) else [st.target]
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            if "pytest_plugins" in names:
                raise NotLiteral("pytest_plugins")
            if "pytestmark" in names and st.value is not None:
                module_marks += _marks(st.value, aliases)
            elif any(n.startswith(("test", "Test")) for n in names):
                raise NotLiteral(f"a test bound by assignment: {names}")
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            bound = [(a.asname or a.name).split(".")[0] for a in st.names]
            if any(n.startswith(("test", "Test")) for n in bound):
                raise NotLiteral(f"an imported test: {bound}")
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if st.name.startswith("pytest_"):
                raise NotLiteral(f"a module-level hook: {st.name}")
            if any(_is_fixture(d) for d in st.decorator_list):
                raise NotLiteral(f"a module-level fixture: {st.name}")
            if st.name.startswith("test"):
                tests.append([m for d in st.decorator_list for m in _marks(d, aliases)])
        elif isinstance(st, ast.ClassDef) and st.name.startswith("Test"):
            collect_class(st, [])
    params = _param_marks(tree, aliases)
    found = {lane_of(path, module_marks + marks) for marks in tests}
    found |= {lane_of(path, module_marks + marks + p) for marks in tests for p in params}
    return found


# ------------------------------------------------------------------ the decision


def tier_of(paths: list[str], module_lanes: Mapping[str, set[str] | None] | None = None) -> str:
    """The tier of a whole change. ``module_lanes`` gives each changed fast-lane test module's lanes (``None``:
    unreadable). ``full`` for an empty change; ``fast`` needs at least one path that is not documentation, and is
    ``full`` together with any ``web/**`` path (V3-1: the ``web`` tier runs neither runtime check)."""
    if not paths:
        return "full"
    module_lanes = module_lanes or {}
    fast = web = False
    for p in paths:
        kind = fast_kind(p)
        if kind == "module":
            lanes = module_lanes.get(p)
            if lanes is None or not lanes <= FAST_LANES:
                return "full"
            fast = True
        elif kind == "durations":
            fast = True
        else:
            least = classify_path(p)
            if least == "full":
                return "full"
            web = web or least == "web"
    if fast and web:
        return "full"
    return "fast" if fast else "web" if web else "docs"


def decide(event: str, paths: list[str] | None, base_ref: str,
           module_lanes: Mapping[str, set[str] | None] | None = None, forced: bool = False) -> str:
    """The decision for ``event``: reduced tiers only for a pull request into ``main`` whose diff is known and
    which is not forced full."""
    if event not in REDUCED_EVENTS or base_ref not in REDUCED_BASES or paths is None or forced:
        return "full"
    return tier_of(paths, module_lanes)


def run_tier(decision: str, mode: str | None = None) -> str:
    """The tier the run takes in ``mode`` (default ``MODE``): the decision when enforcing; in shadow, ``full``
    instead of ``fast``. An unknown mode is ``full``."""
    mode = MODE if mode is None else mode
    if mode not in MODES:
        return "full"
    return "full" if decision == "fast" and mode == "shadow" else decision


def covers(ran: str, recomputed: str) -> bool:
    """The tier the jobs ran under is not narrower than the recomputed one (plan v7 §4): the same, or ``full``."""
    return ran in TIERS and (ran == recomputed or ran == "full")


def job_problems(tier: str, results: dict[str, str]) -> list[str]:
    """Why the jobs ``assurance`` needs do not satisfy ``tier``: every one succeeded, except ``lanes``, which is
    skipped exactly when the tier is known and reduced, and ``fastbase``, which must succeed in the ``fast`` tier and
    may have any result in every other (V6-1). An unknown tier requires everything else. Python, not a shell ``&&``
    chain, whose middle failures ``bash -e`` ignores (review of PR #99, finding 1)."""
    problems = []
    for job in JOBS:
        got = results.get(job, "missing")
        if job == "fastbase":
            if tier == "fast" and got != "success":
                problems.append(f"base footprint unknown (`fastbase`: {got}): add `full-ci`, then Re-run all jobs.")
            continue
        want = "skipped" if job == "lanes" and tier in REDUCED else "success"
        if got != want:
            problems.append(f"{job}: {got}, {want} required in the {tier or 'unknown'} tier")
    return problems


def check_problems(tier: str, modules_changed: bool, checks: Mapping[str, str]) -> list[str]:
    """Keyed on the changed paths, not the tier's name (V3-1): whenever a fast-lane test module changed and the tier
    is not ``full``, the runtime lane check and the premise check must both have run and passed."""
    if tier == "full" or not modules_changed:
        return []
    return [f"{name}: {checks.get(name) or 'did not run'}, success required: a fast-lane test module changed in the "
            f"{tier or 'unknown'} tier" for name in CHECKS if checks.get(name) != "success"]


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


def merge_module_lanes(merge_ref: str, paths: list[str]) -> tuple[dict[str, set[str] | None], dict[str, str]]:
    """Each changed fast-lane test module's lanes over both versions (the merge commit's and the base tip's; a
    deleted module has only the base's): a module whose base version held a heavy test is a heavy test module.
    Returns the lanes and, for each unreadable module, why."""
    lanes: dict[str, set[str] | None] = {}
    why: dict[str, str] = {}
    for p in paths:
        if fast_kind(p) != "module":
            continue
        versions = [s for s in (show(merge_ref, p), show(f"{merge_ref}^1", p)) if s is not None]
        try:
            if not versions:
                raise NotLiteral("neither version can be read")
            lanes[p] = set().union(*(lanes_in_module(p, s) for s in versions))
        except NotLiteral as exc:
            lanes[p], why[p] = None, str(exc)
        except ImportError as exc:  # pytest is not installed: tests/helpers/lanes.py cannot load (fail closed)
            lanes[p], why[p] = None, f"the lanes cannot be computed: {exc}"
    return lanes, why


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
    """The pull request's labels now (not the event's copy), or ``None`` if they cannot be read."""
    if not repo or not pr:
        return None
    try:
        out = _run(["gh", "api", f"repos/{repo}/issues/{pr}/labels", "--jq", ".[].name"]).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"tier: cannot read the labels of {repo}#{pr}: {exc}", file=sys.stderr)
        return None
    return [line.strip() for line in out.splitlines() if line.strip()]


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
    ap.add_argument("--github-output", type=Path, help="append decision=, tier=, lanes=, modules= here")
    ap.add_argument("--record", type=Path, help="write the decision record (JSON) here")
    ap.add_argument("--modules-out", type=Path, help="write the changed fast-lane test modules here, one per line")
    ap.add_argument("--ran", help="fail unless this tier (the one the jobs ran under) covers the recomputed one")
    ap.add_argument("--jobs-for", metavar="TIER", help="instead: check the needed jobs' results for this tier")
    ap.add_argument("--jobs", default="", help="with --jobs-for: name=result pairs, comma-separated")
    ap.add_argument("--modules-changed", default="", help="with --jobs-for: true if a fast-lane test module changed")
    ap.add_argument("--checks", default="", help="with --jobs-for: lanecheck=<outcome>,premise=<outcome>")
    args = ap.parse_args(argv)
    if args.jobs_for is not None:
        results = dict(pair.split("=", 1) for pair in args.jobs.split(",") if "=" in pair)
        checks = dict(pair.split("=", 1) for pair in args.checks.split(",") if "=" in pair)
        problems = job_problems(args.jobs_for, results)
        problems += check_problems(args.jobs_for, args.modules_changed == "true", checks)
        print(f"jobs: {args.jobs or '-'} (tier {args.jobs_for or 'unknown'})")
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1 if problems else 0

    reasons: list[str] = []
    paths: list[str] | None = None
    module_lanes: dict[str, set[str] | None] = {}
    if args.paths_file:
        paths = [line.strip() for line in args.paths_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif args.event in REDUCED_EVENTS:
        paths = merge_paths(args.merge_ref)
        if paths is None:
            reasons.append("the merge commit's diff is unknown")
        else:
            module_lanes, why = merge_module_lanes(args.merge_ref, paths)
            reasons += [f"{p}: {w}" for p, w in sorted(why.items())]
    forced = False
    reduced = decide(args.event, paths, args.base_ref, module_lanes) != "full"
    if reduced:  # the forced flag only matters when the paths alone would reduce the run
        trailer = forced_by_trailer(args.merge_ref) if args.merge_ref else False
        if args.labels is not None:  # given (tests, dry runs): an empty string is no label
            labels: list[str] | None = [x for x in args.labels.split(",") if x]
        else:
            labels = live_labels(args.repo, args.pr)
        if trailer is None or labels is None:
            forced = True
            reasons.append("the forced flag cannot be read (label or trailer): full")
        elif trailer or FORCE_LABEL in labels:
            forced = True
            reasons.append(f"forced full ({FORCE_TRAILER}: yes)" if trailer else f"forced full (label {FORCE_LABEL})")
    decision = decide(args.event, paths, args.base_ref, module_lanes, forced)
    tier = run_tier(decision)
    modules = sorted(p for p in paths or [] if fast_kind(p) == "module")
    print(f"decision={decision} tier={tier} mode={MODE} ({args.event}, "
          f"{'unknown diff' if paths is None else f'{len(paths)} changed path(s)'})")
    for r in reasons:
        print(f"  {r}")
    for p in modules:
        print(f"  module: {p} lanes={','.join(sorted(module_lanes.get(p) or [])) or 'unknown'}")
    if paths and decision != "docs":
        for p in [p for p in paths if classify_path(p) == decision and not fast_kind(p)][:20]:
            print(f"  {decision}: {p}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"decision={decision}\ntier={tier}\nlanes={','.join(LANES[tier])}\n"
                     f"modules={'true' if modules else 'false'}\nmode={MODE}\n")
    if args.modules_out:
        args.modules_out.parent.mkdir(parents=True, exist_ok=True)
        args.modules_out.write_text("".join(f"{p}\n" for p in modules), encoding="utf-8")
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        record = {"schema": "aew/tier-decision/v1", "event": args.event, "base_ref": args.base_ref,
                  "merge": args.merge_ref or None, "base": rev_parse(f"{args.merge_ref}^1"),
                  "head": rev_parse(f"{args.merge_ref}^2"), "mode": MODE,
                  "decision": decision, "tier": tier, "forced": forced, "reasons": reasons,
                  "paths": paths, "eligible": {p: sorted(module_lanes.get(p) or []) if fast_kind(p) == "module"
                                               else fast_kind(p) for p in paths or [] if fast_kind(p)}}
        args.record.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    if args.ran is not None and not covers(args.ran, tier):
        print(FORCED_MESSAGE if forced and args.ran in REDUCED else
              f"tier: the jobs ran under {args.ran or 'an unknown tier'}, narrower than the recomputed {tier}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
