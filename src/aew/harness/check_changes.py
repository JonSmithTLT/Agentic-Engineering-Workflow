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
from pathlib import Path
from typing import Any

CHECK = "check-changes"
COMMAND = "aew doctor --run-checks"
ROLE, SCOPE = "implementer", "ticket"  # a worker's check runs in its run's sandbox (``check.run``)
WORKSPACE_ID = "doctor-run-checks"


def remove_copy(path: Path) -> None:
    """Remove the disposable copy whole: git writes its objects read-only, which Windows will not delete as they are."""
    def writable(_func: Any, name: str, _exc: Any) -> None:
        try:
            os.chmod(name, stat.S_IWRITE | stat.S_IREAD)
            os.unlink(name) if not os.path.isdir(name) else os.rmdir(name)
        except OSError:
            pass

    shutil.rmtree(path, **({"onexc": writable} if sys.version_info >= (3, 12) else {"onerror": writable}))


def _row(status: str, detail: str) -> dict[str, str]:
    return {"check": CHECK, "status": status, "detail": detail}


def configured(engine: Any) -> list[tuple[str, dict[str, Any]]]:
    """The project's configured checks (``policy/checks.yaml``), as ``check run`` resolves them; the builtin guardrails
    check reads the change set, not a tree, so it is not one of them."""
    from aew.errors import AEWError
    from aew.policy import checks as C

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
    if not checks:
        return []
    names = ", ".join(c for c, _ in checks)
    if not run:
        return [_row("WARN", f"not checked: needs the project's check to run once ({names}), to see whether it changes "
                             f"the snapshot it runs on, which makes every verification of it inconclusive. Run "
                             f"`{COMMAND}`: it runs each once on a disposable copy, contained as a worker's check")]
    commit = engine.authoritative_commit()
    if commit is None:
        return [_row("WARN", f"not run: the authoritative branch {engine.authoritative_branch} has no commit to copy")]
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
            changed.append(f"check {check_id} ({ran}) changes the snapshot it runs on: it writes "
                           f"{', '.join(found['paths']) or '(paths not named: the two snapshots cannot be compared)'}"
                           f", so each verification of it is inconclusive. {fix(engine, found['paths'])}")
        else:
            notes.append(f"check {check_id} ({ran}) changes nothing in the snapshot")
    detail = "; ".join(changed + notes) + f" (ran once on a copy of {commit[:12]}; never evidence)"
    if changed:
        return [_row("FAIL", detail)]
    return [_row("PASS" if not any("was not run" in n for n in notes) else "WARN", detail)]


def fix(engine: Any, paths: list[str]) -> str:
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
    return (f"Make the check write outside the project, or, for output it leaves on purpose, list {it} in .gitignore "
            f"(or .git/info/exclude), or in the project manifest's fingerprint.exclude, which keeps {it} out of the "
            "snapshot")


def run_once(engine: Any, check_id: str, cfg: dict[str, Any], commit: str) -> dict[str, Any]:
    """Run one check once, contained as a worker's check, on a disposable clone of ``commit`` with the project's own
    exclusions; return its outcome and the paths it changed. The clone, the run's directory and every process are
    gone when this returns."""
    from aew.errors import AEWError, ContainmentUnavailable
    from aew.harness import containment, procs, runlog, weaker_register
    from aew.policy import checks as C
    from aew.workspace import git
    from aew.workspace.integration import changed_between

    policy, _ = engine.execution_policy()
    stamp = f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{secrets.token_hex(3)}"
    run_dir = runlog.run_dir(engine.aew_root, f"doctor-check-{stamp}")
    copy = engine.workspaces_root() / f".doctor-check-{stamp}"  # where a worker's workspace lives, outside the store
    weaker = None
    try:
        run_dir.mkdir(parents=True)
        copy.parent.mkdir(parents=True, exist_ok=True)
        try:
            git.git("clone", "--quiet", "--shared", "--no-checkout", str(engine.repo_root), str(copy),
                    cwd=copy.parent)
            git.git("checkout", "--quiet", "--detach", commit, cwd=copy)
            exclude = git.common_dir(engine.repo_root) / "info" / "exclude"
            if exclude.is_file():  # a worker's workspace shares the project's exclusions (a linked worktree)
                (copy / ".git" / "info").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(exclude, copy / ".git" / "info" / "exclude")
        except (AEWError, OSError) as exc:
            return {"not_run": f"the copy of {commit[:12]} could not be made ({getattr(exc, 'message', exc)})"}
        try:
            layout, label = containment.establish(
                role=ROLE, scope=SCOPE, workspace=str(copy), run_dir=run_dir, scratch=str(run_dir / "scratch"),
                bridge_dir=None, policy=policy, project=str(engine.repo_root))
        except ContainmentUnavailable as exc:
            return {"not_run": f"a worker's sandbox could not be established here ({exc.message})"}
        if layout is not None and layout.net_dir:  # a check never uses a run's routes out (F28 §3.8)
            shutil.rmtree(layout.net_dir, ignore_errors=True)
        marker = run_dir / "label.json"
        marker.write_text(json.dumps(label, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        trees = procs.CheckTrees()
        try:
            weaker = weaker_register.enter_if_weaker(
                label, kind="doctor_check", ownership=weaker_register.ownership_of(label), project=engine.repo_root,
                aew_root=engine.aew_root, directory=run_dir, marker=marker)
        except ContainmentUnavailable as exc:
            return {"not_run": exc.message}
        env = {**C.allowlist_env(layout), weaker_register.MARKER: str(marker)}
        before = engine.snapshot_of(copy, WORKSPACE_ID)
        if weaker is not None:
            weaker.started()
        try:
            out = C.run(cfg, copy, policy=policy, env=env, layout=layout, trees=trees)
        except ContainmentUnavailable as exc:
            return {"not_run": f"it was refused at its start ({exc.message})"}
        finally:
            if weaker is not None:
                weaker.end(list(trees.left))
        after = engine.snapshot_of(copy, WORKSPACE_ID)
        a, b = before["relevant_inputs_fingerprint"], after["relevant_inputs_fingerprint"]
        try:  # the paths between the two snapshots, as a workspace's mutation is named (evidence_ops._paths_between)
            paths = sorted(changed_between(copy, a.removeprefix("git-tree:"), b.removeprefix("git-tree:"))) \
                if a != b else []
        except AEWError:  # a process that stores no objects hashed the trees without writing them
            paths = []
        return {"outcome": out["outcome"], "exit_code": out["exit_code"], "paths": paths, "mutated": a != b}
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
