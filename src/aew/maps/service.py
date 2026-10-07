"""What the ``aew map`` commands do (plan §4.4; ADR-0015). The CLI only parses and renders.

* ``generate`` is Lead-authenticated (it writes under ``.aew/``): the current Lead's credential, checked against the
  control state it only reads. It never takes ``--expect-rev`` and never commits a control transition: selection is
  a compare-and-set on the map registry's own revision (T5-INV-11).
* ``show`` and ``diff`` are reads open to any context. ``diff`` of a commit generates the record in memory and stores
  nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine.authority import require_lead
from aew.errors import MapArtifactNondeterministic, MapRegistryInvalid, UsageError
from aew.maps import freshness as F
from aew.maps import gitobjects, rules, store, structural
from aew.maps.canonical import seal

ENVELOPE = ("schema", "source_revision", "source_tree", "object_format", "generator", "artifact_sha256")


def identity() -> dict[str, Any]:
    return structural.generator_identity(rules.load())


def build(repo: Path, commit: str) -> dict[str, Any]:
    """The record for ``commit``, from its Git objects, without ``artifact_sha256``."""
    with gitobjects.open_tree(repo, commit) as tree:
        return structural.generate(tree, rules.load())


def _lead_actor(engine: Any, token: str) -> dict[str, Any]:
    actor = require_lead(engine.store.read(), token, archived=engine.archived_credential)
    return {"kind": "lead", "id": actor["token_id"], "generation": actor["generation"]}


def _default_commit(engine: Any) -> str:
    commit = engine.authoritative_commit()
    if not commit:
        raise UsageError(f"the authoritative branch {engine.authoritative_branch!r} has no commit; pass --commit")
    return commit


def _entry(record: dict[str, Any], sha: str, root: str) -> dict[str, Any]:
    return {"root": root, "sha256": sha, "source_revision": record["source_revision"],
            "source_tree": record["source_tree"], "object_format": record["object_format"],
            "generator_version": record["generator"]["version"],
            "ruleset_sha256": record["generator"]["ruleset_sha256"]}


def _nondeterministic(registry: dict[str, Any] | None, record: dict[str, Any], sha: str) -> dict[str, Any] | None:
    """The selected map's commit regenerated with the same generator identity, giving other bytes (§4.3)."""
    selected = ((registry or {}).get("selected") or {}).get("structural")
    if not selected or selected["source_revision"] != record["source_revision"] or selected["sha256"] == sha:
        return None
    generator = record["generator"]
    if (selected["generator_version"], selected["ruleset_sha256"]) != (generator["version"],
                                                                        generator["ruleset_sha256"]):
        return None
    return {"code": MapArtifactNondeterministic.code, "selected": selected["sha256"], "generated": sha,
            "source_revision": record["source_revision"]}


def generate(engine: Any, *, token: str, commit: str | None = None, select: bool = False,
             expect: str | None = None, replace_nondeterministic: bool = False) -> dict[str, Any]:
    actor = _lead_actor(engine, token)  # authority first, before any work
    if select and expect is None:
        raise UsageError("--select needs --expect-map-rev <epoch>:<revision> (`aew map show` prints it; none:0 "
                         "before the first selection)")
    if not select and (expect is not None or replace_nondeterministic):
        raise UsageError("--expect-map-rev and --replace-nondeterministic go with --select")
    if expect is not None:
        store.parse_expectation(expect)  # a malformed expectation is refused before the work
    record = build(engine.repo_root, commit or _default_commit(engine))
    sha, root = store.write_artifact(engine.aew_root, record)
    result: dict[str, Any] = {"ok": True, "root": sha, "path": f"{engine.aew_root.name}/{root}",
                              "source_revision": record["source_revision"], "source_tree": record["source_tree"],
                              "generator": record["generator"], "limits": record["limits"], "selected": False}
    try:
        registry = store.read_registry(engine.aew_root)
    except MapRegistryInvalid:
        if select:
            raise
        result["map_revision"] = None
        result["registry"] = "invalid"
        return result
    result["map_revision"] = store.revision_of(registry)
    report = _nondeterministic(registry, record, sha)
    if report:
        result["nondeterministic"] = report
    if not select:
        return result
    if report and not replace_nondeterministic:
        raise MapArtifactNondeterministic(
            f"regenerating {record['source_revision']} with the same generator identity gave {sha}, not the selected "
            f"{report['selected']}: the selection is left as it is. The new artifact is stored; select it anyway with "
            "--replace-nondeterministic", **report)
    note = {"replaced_nondeterministic": report} if report else None
    new = store.select_structural(engine.aew_root, expect=str(expect), entry=_entry(record, sha, root), actor=actor,
                                  note=note)
    result.update(selected=True, map_revision=store.revision_of(new))
    return result


def _registry_revision(aew_root: Path) -> tuple[dict[str, Any] | None, str]:
    try:
        registry = store.read_registry(aew_root)
    except MapRegistryInvalid:
        return None, "invalid"
    return registry, store.revision_of(registry)


def _section(record: dict[str, Any], name: str | None) -> dict[str, Any]:
    if name is None:
        return record
    if name not in structural.SECTIONS:
        raise UsageError(f"no section {name!r}; the sections are {', '.join(structural.SECTIONS)}")
    return {**{k: record[k] for k in ENVELOPE}, "sections": {name: record["sections"][name]}}


def show(engine: Any, *, commit: str | None = None, root: str | None = None,
         section: str | None = None) -> dict[str, Any]:
    against = commit or _default_commit(engine)
    registry, revision = _registry_revision(engine.aew_root)
    selected_sha = (((registry or {}).get("selected") or {}).get("structural") or {}).get("sha256")
    if root is not None:
        record = store.read_artifact(engine.aew_root, root)  # the strict reader: corrupt is an error here
    else:
        found = store.read_selected(engine.aew_root)
        if isinstance(found, store.Unavailable):
            return {"ok": True, "status": found.status, "reason": found.reason, "map_revision": revision}
        record = found.record
    return {"ok": True, "status": "AVAILABLE", "root": record["artifact_sha256"],
            "selected": record["artifact_sha256"] == selected_sha, "map_revision": revision,
            "freshness": F.freshness(engine.repo_root, record, against, identity()),
            "record": _section(record, section)}


def _operand(engine: Any, kind: str, value: str) -> dict[str, Any]:
    if kind == "root":
        return store.read_artifact(engine.aew_root, value)
    record = build(engine.repo_root, value)  # in memory only: nothing is stored
    sha, _ = seal(record)
    return {**record, "artifact_sha256": sha}


def _diff_value(a: Any, b: Any) -> dict[str, Any]:
    if isinstance(a, list) and isinstance(b, list):
        return {"added": [i for i in b if i not in a], "removed": [i for i in a if i not in b]}
    return {"from": a, "to": b}


def diff(engine: Any, operands: list[tuple[str, str]]) -> dict[str, Any]:
    if len(operands) != 2:
        raise UsageError("map diff compares exactly two maps: give two of --root SHA and --commit H")
    a, b = (_operand(engine, kind, value) for kind, value in operands)
    envelope = {k: _diff_value(a.get(k), b.get(k)) for k in ENVELOPE if a.get(k) != b.get(k)}
    if a["inputs"]["path_listing_sha256"] != b["inputs"]["path_listing_sha256"]:
        envelope["path_listing_sha256"] = _diff_value(a["inputs"]["path_listing_sha256"],
                                                      b["inputs"]["path_listing_sha256"])
    sections: dict[str, Any] = {}
    for name in structural.SECTIONS:
        x, y = a["sections"][name], b["sections"][name]
        if x == y:
            sections[name] = {"changed": False}
            continue
        fields = {k: _diff_value(x.get(k), y.get(k)) for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)}
        sections[name] = {"changed": True, "fields": fields}
    return {"ok": True, "a": {k: a[k] for k in ("artifact_sha256", "source_revision", "source_tree")},
            "b": {k: b[k] for k in ("artifact_sha256", "source_revision", "source_tree")},
            "identical": a["artifact_sha256"] == b["artifact_sha256"], "envelope": envelope, "sections": sections}
