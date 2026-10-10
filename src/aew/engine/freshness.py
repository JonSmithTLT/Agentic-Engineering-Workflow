"""Freshness contracts for non-mutating records (ADR-0008; KC §13).

Each record kind has its own contract; none of them is the implementation-evidence rule (exact
fingerprint equality with the current workspace), and none is silently equated with it:

* ``discovery_record`` / ``plan_proposal`` are **source-bound**: they describe the authoritative source
  at the commit H they observed. They stay CURRENT while that source is unchanged (whole tree, or only
  the declared ``observed_paths`` / ``affected_paths``), become STALE when it changes, and are UNKNOWN
  when H is no longer in the authoritative lineage.
* ``research_record`` is **not source-bound**: it describes external technology, so project source
  changes never make it stale, and its currency cannot be established by the engine. It is reported
  as ``UNKNOWN`` with basis ``external`` (as of its date and declared versions) rather than an
  overclaimed CURRENT.

Freshness is computed, never written: records stay byte-identical history.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.errors import GitError
from aew.workspace import git

CURRENT, STALE, UNKNOWN = "CURRENT", "STALE", "UNKNOWN"
SOURCE_BOUND = frozenset({"discovery_record", "plan_proposal"})
AEW_EXCLUDE = ":(exclude).aew"


def declared_paths(record: dict[str, Any]) -> list[str]:
    if record["kind"] == "discovery_record":
        return list((record.get("discovery") or {}).get("observed_paths") or [])
    if record["kind"] == "plan_proposal":
        return list((record.get("proposal") or {}).get("affected_paths") or [])
    return []


def record_freshness(repo_root: Path, record: dict[str, Any], authoritative_commit: str | None, *,
                     timeout: float | None = None) -> dict[str, Any]:
    """The record's freshness against ``authoritative_commit``. With ``timeout`` (the dashboard's, register F20.8),
    each git call reads objects as the project maps do (``git.object_git``: no replace refs, no lazy fetch, no window)
    and is bounded by it: a git that does not answer raises ``GitError`` with ``reason`` ``timeout``. Without it the
    CLI's calls are unchanged."""
    kind = record["kind"]
    if kind == "research_record":
        research = record.get("research") or {}
        return {"status": UNKNOWN, "basis": "external", "source_bound": False, "as_of": record.get("created_at"),
                "subjects": [{"name": s.get("name"), "version": s.get("version")}
                             for s in research.get("subjects", [])],
                "detail": "external research: project source changes never make it stale; verify versions before "
                          "relying on it"}
    if kind not in SOURCE_BOUND:
        return {"status": UNKNOWN, "basis": "not-applicable", "source_bound": False}
    observed = (record.get("evaluated_snapshot") or {}).get("base_revision")
    base = {"basis": "authoritative-source", "source_bound": True, "observed_commit": observed,
            "authoritative_commit": authoritative_commit}
    if not observed or not authoritative_commit:
        return {**base, "status": UNKNOWN, "detail": "no observed or authoritative commit"}
    if observed != authoritative_commit and not _is_ancestor(observed, authoritative_commit, repo_root, timeout):
        return {**base, "status": UNKNOWN,
                "detail": f"observed commit {observed[:12]} is no longer in the authoritative lineage"}
    paths = declared_paths(record)
    pathspec = [*paths] if paths else ["."]
    changed = [] if observed == authoritative_commit else _changed(
        repo_root, ["--no-renames", observed, authoritative_commit, "--", *pathspec, AEW_EXCLUDE], timeout)
    scope = "declared paths" if paths else "whole tree"
    if changed:
        return {**base, "status": STALE, "scope": scope, "changed_paths": sorted(changed)}
    return {**base, "status": CURRENT, "scope": scope}


def _is_ancestor(ancestor: str, descendant: str, repo_root: Path, timeout: float | None) -> bool:
    if timeout is None:
        return git.is_ancestor(ancestor, descendant, cwd=repo_root)
    proc = git.object_git("merge-base", "--is-ancestor", ancestor, descendant, cwd=repo_root, check=False,
                          timeout=timeout)
    if proc.returncode not in (0, 1):
        raise GitError("merge-base --is-ancestor failed", stderr=proc.stderr.decode("utf-8", "replace").strip())
    return proc.returncode == 0


def _changed(repo_root: Path, args: list[str], timeout: float | None) -> list[str]:
    if timeout is None:
        return git.out("diff", "--name-only", *args, cwd=repo_root).splitlines()
    # ``git.git`` adds these two to every diff; the object reader is called directly, so they are spelled out here
    proc = git.object_git("diff", "--no-ext-diff", "--no-textconv", "--name-only", *args, cwd=repo_root,
                          timeout=timeout)
    return proc.stdout.decode("utf-8", "replace").strip().splitlines()


def is_acceptable_input(fresh: dict[str, Any]) -> bool:
    """A consumed record may feed a dispatch unchanged only if it is CURRENT or not source-bound."""
    return not fresh.get("source_bound") or fresh["status"] == CURRENT
