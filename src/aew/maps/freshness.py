"""Structural-map freshness against a commit (design v0.5 §2.4; PMP-07, PMP-29, T5-INV-02; plan §4.3).

Computed on read and never written into the artifact. The order of the checks:

0. a partial clone on a git that cannot be told not to fetch lazily -> ``UNKNOWN`` (``partial_clone``), before any
   object is read;
1. the commit ``B`` (or the record's own source tree) does not resolve -> ``UNKNOWN`` (``MAP_CURRENTNESS_UNPROVEN``);
2. the record's generator version or ruleset differs from the installed generator's -> ``STALE`` (``generator``);
3. the trees are equal -> ``CURRENT``;
4. ``B``'s canonical path listing differs -> ``STALE`` (``path_listing``);
5. a logged metadata input, read or unread, has another blob at ``B`` or is gone -> ``STALE`` (``metadata``), with
   the paths;
6. otherwise ``CURRENT``: only content outside the recorded inputs changed, which cannot change the record.

Cached in this process's memory only, keyed by ``(artifact_sha256, B's tree, generator identity)``: there is no
persisted cache, so nothing a reader writes can relabel a map, and two records of one tree under different rulesets
are never confused. The cache is a bounded LRU (:data:`CACHE_MAX`), since a long-lived dashboard server sees a new
tree with every new head (register F20.8).

``timeout`` bounds each git process (the default is ``gitobjects``' own): the dashboard passes a short one, because
its projections are built one at a time, and a git that does not answer within it gives ``UNKNOWN`` (``timeout``),
never an error (the change note §4.1). Without it the CLI's behaviour is unchanged.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

from aew.errors import GitError, MapCurrentnessUnproven
from aew.maps import gitobjects
from aew.maps.canonical import listing_sha256
from aew.workspace import git

CURRENT, STALE, UNKNOWN = "CURRENT", "STALE", "UNKNOWN"
PATHS_SHOWN = 50
CACHE_MAX = 1024

_cache: OrderedDict[tuple[str, str, str, int, str], dict[str, Any]] = OrderedDict()


def _unknown(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": UNKNOWN, "code": MapCurrentnessUnproven.code, "reasons": [reason], "reason": reason, **extra}


def freshness(repo: Path, record: dict[str, Any], against: str, identity: dict[str, Any], *,
              timeout: float | None = None) -> dict[str, Any]:
    """The record's freshness against commit ``against``; ``identity`` is the installed generator's. With ``timeout``,
    each git process is bounded by it and a git that does not answer is ``UNKNOWN`` (``timeout``)."""
    if timeout is None:
        return _freshness(repo, record, against, identity, None)
    try:
        return _freshness(repo, record, against, identity, timeout)
    except GitError as exc:
        if (exc.details or {}).get("reason") != "timeout":
            raise
        return _unknown("timeout")


def _freshness(repo: Path, record: dict[str, Any], against: str, identity: dict[str, Any],
               timeout: float | None) -> dict[str, Any]:
    bound = git.OBJECT_TIMEOUT_S if timeout is None else timeout
    try:  # before any object is resolved: an old git in a partial clone could fetch a missing one lazily
        gitobjects.refuse_lazy_fetch(repo, timeout=timeout)
    except MapCurrentnessUnproven:
        return _unknown("partial_clone")
    try:
        commit, tree, _ = gitobjects.resolve(repo, against, timeout=bound)
    except MapCurrentnessUnproven:
        return _unknown("unknown_commit")
    key = (record["artifact_sha256"], tree, identity["name"], int(identity["version"]), identity["ruleset_sha256"])
    result = _cache.get(key)
    if result is None:
        result = _compute(repo, record, tree, identity, bound)
        if result["status"] != UNKNOWN:  # an unproven answer may become provable (an object fetched): never kept
            _cache[key] = result
            while len(_cache) > CACHE_MAX:
                _cache.popitem(last=False)
    else:
        _cache.move_to_end(key)
    return {**result, "against_commit": commit, "against_tree": tree}


def _compute(repo: Path, record: dict[str, Any], tree: str, identity: dict[str, Any],
             bound: float) -> dict[str, Any]:
    source = record["source_tree"]
    if git.object_git("cat-file", "-e", f"{source}^{{tree}}", cwd=repo, check=False, timeout=bound).returncode != 0:
        return _unknown("unknown_source")
    generator = record["generator"]
    if (generator["name"], generator["version"], generator["ruleset_sha256"]) != (
            identity["name"], identity["version"], identity["ruleset_sha256"]):
        return {"status": STALE, "reasons": ["generator"], "reason": "generator",
                "generator": {"record": generator, "installed": identity}}
    if source == tree:
        return {"status": CURRENT, "reasons": [], "reason": None}
    try:
        entries = gitobjects.list_tree(repo, tree, sizes=False, timeout=bound)
    except MapCurrentnessUnproven:
        return _unknown("missing_object")
    reasons: list[str] = []
    if listing_sha256(entries) != record["inputs"]["path_listing_sha256"]:
        reasons.append("path_listing")
    at_b = {e.path: e.oid for e in entries}
    changed = sorted(i["path"] for i in record["inputs"]["metadata"] if at_b.get(i["path"]) != i["git_oid"])
    if changed:
        reasons.append("metadata")
    if not reasons:
        return {"status": CURRENT, "reasons": [], "reason": None}
    out: dict[str, Any] = {"status": STALE, "reasons": reasons, "reason": reasons[0]}
    if changed:
        out["metadata_paths"] = changed[:PATHS_SHOWN]
        out["metadata_paths_omitted"] = max(0, len(changed) - PATHS_SHOWN)
    return out


def clear_cache() -> None:
    _cache.clear()
