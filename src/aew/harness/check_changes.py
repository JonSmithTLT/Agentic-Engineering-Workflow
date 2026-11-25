"""``aew doctor --run-checks``: whether the project's checks change the snapshot they run on (register E153; the
designer's ruling (b), relayed 2026-11-07).

A check that writes into the tree it checks makes every verification of it inconclusive: the snapshot it proved is
not the one it leaves. Naming the file means running the check, so it is opt-in: with ``--run-checks`` each configured
check runs once where verification runs it (a worker's sandbox, the project's network policy, an allow-listed
environment), on a disposable copy of the authoritative snapshot that is removed after, bounded by the check's own
timeout. The snapshot is compared before and after as verification compares it (the engine's ``snapshot_of``), and
each changed path is named with its fix. The result is never evidence. Without the flag, one WARN says the checks were
not run and gives the command. Nothing here refuses anything.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.policy import checks as C

if TYPE_CHECKING:
    from aew.harness.procs import CheckTrees

CHECK = "check-changes"
COMMAND = "aew doctor --run-checks"
ROLE, SCOPE = "implementer", "ticket"  # a worker's check runs in its run's sandbox (``check.run``)
WORKSPACE_ID = "doctor-run-checks"
# The selector is an advisory subprocess. Bound how much of its output the engine reads.
SELECTION_OUTPUT_BYTES = 1024 * 1024


def _protocol_bytes(path: Path, maximum: int) -> bytes | None:
    """Read a bounded regular file from this run's scratch, without following links or waiting on a pipe."""
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(path, flags), "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            data = handle.read(maximum + 1)
    except OSError:
        return None
    return data if len(data) <= maximum else None


def remove_copy(path: Path) -> None:
    """Remove the disposable copy whole: git writes its objects read-only, which Windows will not delete as they are."""
    def writable(_func: Any, name: str, _exc: Any) -> None:
        try:
            os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(name) if not os.path.isdir(name) else os.rmdir(name)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=writable)
    else:
        shutil.rmtree(path, onerror=writable)


def _row(status: str, detail: str) -> dict[str, str]:
    return {"check": CHECK, "status": status, "detail": detail}


def configured(engine: Any) -> list[tuple[str, dict[str, Any]]]:
    """The project's configured checks (``policy/checks.yaml``), as ``check run`` resolves them; the builtin guardrails
    check reads the change set, not a tree, so it is not one of them."""
    from aew.errors import AEWError

    policy = engine.policy("checks") or {}
    out = []
    for check_id in sorted(policy.get("checks") or {}):
        try:
            cfg = C.resolve(policy, check_id)
        except AEWError:  # an unconfigured check is the validate rows' to name, not this one's
            continue
        if not cfg.get("builtin"):
            out.append((check_id, cfg))
    return out


def doctor_rows(engine: Any, *, run: bool) -> list[dict[str, str]]:
    checks = configured(engine)
    selector = None
    if run:
        from aew.engine import coverage

        _, pin = coverage.checks_at_pin(engine._k)
        if pin is not None:
            selector = pin["declaration"].get("affected_tests", {}).get("selector")
    if selector is not None:
        from aew.engine import selection

        commit = engine.authoritative_commit()
        result = selection.observe(engine, engine.snapshot_of, selector, commit, [], doctor_probe=True)
        detail = (f"{len(result['items'])} selected for an empty change"
                  if result["result"] == "known" else result["reason"].replace("_", " "))
        selection_row = {"check": "checks-configured",
                         "status": "PASS" if result["result"] == "known" else "WARN",
                         "detail": f"Affected-test selector: {detail} (diagnostic only)"}
        rows = [selection_row]
    else:
        rows = []
    if not checks:
        return rows
    names = ", ".join(c for c, _ in checks)
    if not run:
        return rows + [_row("WARN", f"not checked: needs the project's check to run once ({names}), to see whether it "
                            f"changes the snapshot it runs on, which makes every verification of it inconclusive. Run "
                            f"`{COMMAND}`: it runs each once on a disposable copy, contained as a worker's check")]
    commit = engine.authoritative_commit()
    if commit is None:
        return rows + [_row("WARN", f"not run: the authoritative branch {engine.authoritative_branch} has no commit "
                            "to copy")]
    changed: list[str] = []
    notes: list[str] = []
    for check_id, cfg in checks:
        found = run_once(engine, check_id, cfg, commit)
        if found.get("not_run"):
            notes.append(f"{check_id} was not run: {found['not_run']}")
            continue
        outcome = found["outcome"]
        ran = ("timed out" if outcome == "timeout" else "could not start" if outcome == "spawn_failed"
               else f"exited {found['exit_code']}")
        if found["mutated"]:  # what verification compares: the snapshot's fingerprint (review of #367, F2)
            guidance = fix(engine, found["paths"], check_id=check_id, tracked=found.get("tracked"))
            changed.append(f"check {check_id} ({ran}) changes the snapshot it runs on: it writes "
                           f"{', '.join(found['paths']) or '(paths not named: the two snapshots cannot be compared)'}"
                           f", so each verification of it is inconclusive. {guidance}")
        else:
            notes.append(f"check {check_id} ({ran}) changes nothing in the snapshot")
    detail = "; ".join(changed + notes) + f" (ran once on a copy of {commit[:12]}; never evidence)"
    if changed:
        return rows + [_row("FAIL", detail)]
    return rows + [_row("PASS" if not any("was not run" in n for n in notes) else "WARN", detail)]


def fix(engine: Any, paths: list[str], *, check_id: str = "", tracked: set[str] | None = None) -> str:
    """The fix for paths a check writes into its snapshot: written elsewhere, or kept out of the snapshot by the rule
    that keeps a path out of it. A path the manifest's ``fingerprint.include_ignored`` puts back in is kept out only by
    taking it off that list; any other by ``.gitignore``, ``.git/info/exclude`` or ``fingerprint.exclude``."""
    included = [str(p).rstrip("/") for p in ((engine.manifest or {}).get("fingerprint") or {}).get("include_ignored")
                or []]
    forced = [p for p in paths if any(p == i or p.startswith(i + "/") for i in included)]
    it = "it" if len(paths) == 1 else "them"
    if forced:
        return (f"Make the check write outside the project, or take {', '.join(sorted(set(forced)))} off the project "
                "manifest's fingerprint.include_ignored, which puts ignored output back into the snapshot")
    if check_id and tracked is not None and not tracked.intersection(paths) and (hint := C.cache_hint(paths)):
        return (f"If these are disposable caches, add `{hint}` under check {check_id!r} in policy/checks.yaml "
                "and adopt the policy. This can change the fingerprint and make existing evidence STALE.")
    return (f"Make the check write outside the project, or, for output it leaves on purpose, list {it} in .gitignore "
            f"(or .git/info/exclude), or in the project manifest's fingerprint.exclude, which keeps {it} out of the "
            "snapshot")


def run_once(engine: Any, check_id: str, cfg: dict[str, Any], commit: str) -> dict[str, Any]:
    """Run one check once, contained as a worker's check, on a disposable clone of ``commit`` with the project's own
    exclusions; return its outcome and the paths it changed. The clone, the run's directory and every process are
    gone when this returns."""
    return run_copy(engine, engine.snapshot_of, cfg, commit)


def run_copy(project: Any, snapshot_of: Callable[[Path, str], dict[str, Any]], cfg: dict[str, Any], commit: str,
             *, changed_paths: list[str] | None = None, trees: CheckTrees | None = None,
             kind: str = "doctor_check") -> dict[str, Any]:
    """The check-copy mechanism also runs a declared selector, with input and output outside the copied tree."""
    from aew.errors import AEWError, ContainmentUnavailable
    from aew.harness import containment, procs, runlog, weaker_register
    from aew.workspace import git
    from aew.workspace.integration import changed_between

    copy_trees = procs.CheckTrees() if trees is None else trees
    policy, _ = project.execution_policy()
    stamp = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(3)}"
    run_name = f"{kind.replace('_', '-')}-{stamp}"
    run_dir = runlog.run_dir(project.aew_root, run_name)
    copy = project.workspaces_root() / f".{run_name}"  # a worker workspace, outside the store
    weaker = None
    try:
        run_dir.mkdir(parents=True)
        copy.parent.mkdir(parents=True, exist_ok=True)
        try:
            git.git("clone", "--quiet", "--shared", "--no-checkout", str(project.repo_root), str(copy),
                    cwd=copy.parent)
            git.git("checkout", "--quiet", "--detach", commit, cwd=copy)
            exclude = git.common_dir(project.repo_root) / "info" / "exclude"
            if exclude.is_file():  # a worker's workspace shares the project's exclusions (a linked worktree)
                (copy / ".git" / "info").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(exclude, copy / ".git" / "info" / "exclude")
        except (AEWError, OSError) as exc:
            return {"not_run": f"the copy of {commit[:12]} could not be made ({getattr(exc, 'message', exc)})"}
        if copy_trees.ended:
            return {"outcome": "timeout"}
        scratch = run_dir / "scratch"
        try:
            layout, label = containment.establish(
                role=ROLE, scope=SCOPE, workspace=str(copy), run_dir=run_dir, scratch=str(scratch),
                bridge_dir=None, policy=policy, project=str(project.repo_root))
        except ContainmentUnavailable as exc:
            return {"not_run": f"a worker's sandbox could not be established here ({exc.message})"}
        if layout is not None and layout.net_dir:  # a check never uses a run's routes out (F28 §3.8)
            shutil.rmtree(layout.net_dir, ignore_errors=True)
        marker = run_dir / "label.json"
        marker.write_text(json.dumps(label, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if copy_trees.ended:
            return {"outcome": "timeout"}
        try:
            weaker = weaker_register.enter_if_weaker(
                label, kind=kind, ownership=weaker_register.ownership_of(label), project=project.repo_root,
                aew_root=project.aew_root, directory=run_dir, marker=marker)
        except ContainmentUnavailable as exc:
            return {"not_run": exc.message}
        env = {**C.allowlist_env(layout), weaker_register.MARKER: str(marker)}
        tracked: set[str] = set()
        try:
            if changed_paths is None:
                listing = git.git("ls-files", "--cached", "-z", cwd=copy).stdout
                tracked = set(listing.decode("utf-8", "replace").split("\0"))
            before = snapshot_of(copy, WORKSPACE_ID)
            if copy_trees.ended:
                return {"outcome": "timeout"}
            paths_file, selection_out, expected_paths = None, None, b""
            if changed_paths is not None:
                scratch.mkdir(exist_ok=True)
                paths_file, selection_out = scratch / "changed.txt", scratch / "selection.txt"
                expected_paths = "".join(f"{path}\n" for path in changed_paths).encode()
                paths_file.write_bytes(expected_paths)
            if weaker is not None:
                weaker.started()
            channels: dict[str, Any] = {"paths_file": paths_file, "selection_out": selection_out} if paths_file else {}
            out = C.run(cfg, copy, policy=policy, env=env, layout=layout, trees=copy_trees, **channels)
        except ContainmentUnavailable as exc:
            return {"not_run": f"it was refused at its start ({exc.message})"}
        finally:
            if weaker is not None:
                weaker.end(list(copy_trees.left))
        if copy_trees.ended:
            return {"outcome": "timeout"}
        after = snapshot_of(copy, WORKSPACE_ID)
        a, b = before["relevant_inputs_fingerprint"], after["relevant_inputs_fingerprint"]
        if paths_file is not None:
            if _protocol_bytes(paths_file, len(expected_paths)) != expected_paths:
                return {**out, "mutated": True}
            items = None
            assert selection_out is not None
            raw = _protocol_bytes(selection_out, SELECTION_OUTPUT_BYTES)
            try:
                if raw is not None:
                    items = raw.decode("utf-8").replace("\r\n", "\n").split("\n")
            except UnicodeError:
                pass
            return {**out, "mutated": a != b, "selection_items": items}
        try:  # the paths between the two snapshots, as a workspace's mutation is named (evidence_ops._paths_between)
            paths = sorted(changed_between(copy, a.removeprefix("git-tree:"), b.removeprefix("git-tree:"))) \
                if a != b else []
        except AEWError:  # a process that stores no objects hashed the trees without writing them
            paths = []
        return {"outcome": out["outcome"], "exit_code": out["exit_code"], "paths": paths, "mutated": a != b,
                **({"tracked": tracked} if C.cache_hint(paths) else {})}
    finally:
        containment.retire_private_git(run_dir)
        if copy.exists():
            remove_copy(copy)
        keep = weaker is not None and weaker.data.get("outcome") != "clean"  # the entry's marker names label.json
        for path in run_dir.iterdir() if run_dir.is_dir() else ():
            if keep and path.name == "label.json":
                continue
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)
        if not keep:
            shutil.rmtree(run_dir, ignore_errors=True)
