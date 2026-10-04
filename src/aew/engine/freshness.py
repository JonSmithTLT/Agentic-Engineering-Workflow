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


def record_freshness(repo_root: Path, record: dict[str, Any], authoritative_commit: str | None) -> dict[str, Any]:
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
    if observed != authoritative_commit and not git.is_ancestor(observed, authoritative_commit, cwd=repo_root):
        return {**base, "status": UNKNOWN,
                "detail": f"observed commit {observed[:12]} is no longer in the authoritative lineage"}
    paths = declared_paths(record)
    pathspec = [*paths] if paths else ["."]
    changed = [] if observed == authoritative_commit else git.out(
        "diff", "--name-only", "--no-renames", observed, authoritative_commit, "--", *pathspec, AEW_EXCLUDE,
        cwd=repo_root).splitlines()
    scope = "declared paths" if paths else "whole tree"
    if changed:
        return {**base, "status": STALE, "scope": scope, "changed_paths": sorted(changed)}
    return {**base, "status": CURRENT, "scope": scope}


def is_acceptable_input(fresh: dict[str, Any]) -> bool:
    """A consumed record may feed a dispatch unchanged only if it is CURRENT or not source-bound."""
    return not fresh.get("source_bound") or fresh["status"] == CURRENT
