"""What the ``aew map`` commands do (plan §4.4; ADR-0015). The CLI only parses and renders.

* ``generate`` is Lead-authenticated (it writes under ``.aew/``): the current Lead's credential, checked against the
  control state it only reads. It never takes ``--expect-rev`` and never commits a control transition: selection is
  a compare-and-set on the map registry's own revision (T5-INV-11).
* ``select-architecture`` (Lead-authenticated, register F22.1 plan §5.2) records an existing discovery-evidence id
  as the architecture navigation reference. Selection asserts nothing about the record's content (design v0.5 §10),
  and a stale reference is labelled with its evidence's freshness: it never dispatches an investigator and never
  blocks anything.
* ``show`` and ``diff`` are reads open to any context. ``diff`` of a commit generates the record in memory and stores
  nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aew.engine.authority import require_lead
from aew.errors import AEWError, MapArtifactNondeterministic, MapRegistryInvalid, NotFound, UsageError, ValidationFailed
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


def _lead_actor(engine: Any, token: str, *, committed: bool = False) -> dict[str, Any]:
    """The current Lead for ``token``, or the refusal (``STALE_AUTHORITY`` for a superseded Lead). ``committed`` reads
    the committed control state without the control lock (``read_committed``): the check repeated at the publication
    and selection boundary, where the map registry's lock is already held."""
    state = engine.store.read_committed() if committed else engine.store.read()
    actor = require_lead(state, token, archived=engine.archived_credential)
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
    # Authority is checked again where the command writes, not only before the work (PR #126, operator finding 1): a
    # handoff or takeover committed during generation refuses the write and the selection (ADR-0015 D4).
    _lead_actor(engine, token, committed=True)
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
                                  note=note, authorize=lambda: _lead_actor(engine, token, committed=True))
    result.update(selected=True, map_revision=store.revision_of(new))
    return result


DISCOVERY = "discovery_record"


def _evidence(engine: Any, evidence_id: str) -> dict[str, Any]:
    """An existing evidence record by id: in a hot unit's evidence, or held by finished work in the history."""
    from aew.knowledge import evidence as E

    state = engine.store.read()
    for wid in sorted(state["work"]):
        for e in E.scan(engine.aew_root, wid)[0]:
            if e["id"] == evidence_id:
                return e
    try:
        shown = engine.history_show(evidence_id)
    except NotFound:
        raise NotFound(f"no evidence record {evidence_id}: select the id of an existing discovery record",
                       evidence_id=evidence_id) from None
    if shown.get("kind") != "evidence":
        raise ValidationFailed(f"{evidence_id} is a historical {shown.get('kind')}, not an evidence record: select a "
                               "discovery record's id", reason="not_discovery_evidence", evidence_id=evidence_id)
    return dict(shown["record"]["meta"])


def select_architecture(engine: Any, *, token: str, evidence_id: str, expect: str) -> dict[str, Any]:
    """Record ``evidence_id`` as the architecture navigation reference (plan §5.2): it must exist and be discovery
    evidence; nothing else about it is checked or asserted."""
    actor = _lead_actor(engine, token)
    store.parse_expectation(expect)
    record = _evidence(engine, evidence_id)
    if record.get("kind") != DISCOVERY:
        raise ValidationFailed(f"{evidence_id} is a {record.get('kind')}, not discovery evidence: the architecture "
                               "reference is an investigator's discovery record (design v0.5 §10)",
                               reason="not_discovery_evidence", evidence_id=evidence_id, kind=record.get("kind"))
    new = store.select(engine.aew_root, "architecture", expect=expect, entry={"evidence_id": evidence_id},
                       actor=actor, authorize=lambda: _lead_actor(engine, token, committed=True))
    return {"ok": True, "architecture": architecture(engine, new), "map_revision": store.revision_of(new)}


def architecture(engine: Any, registry: dict[str, Any] | None) -> dict[str, Any] | None:
    """The selected architecture reference with its evidence's freshness against the authoritative commit, or None.
    Never raises: a reference whose evidence is gone is reported UNAVAILABLE, and a stale one is labelled STALE."""
    ref = ((registry or {}).get("selected") or {}).get("architecture")
    if not ref:
        return None
    from aew.engine.freshness import record_freshness

    try:
        record = _evidence(engine, ref["evidence_id"])
        fresh = record_freshness(engine.repo_root, record, engine.authoritative_commit())
    except (AEWError, OSError, KeyError) as exc:
        return {"evidence_id": ref["evidence_id"], "freshness": {"status": "UNAVAILABLE",
                                                                 "detail": getattr(exc, "code", type(exc).__name__)}}
    return {"evidence_id": ref["evidence_id"], "freshness": fresh,
            "note": "navigation reference: selection is not truth, and a stale reference blocks nothing"}


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
            return {"ok": True, "status": found.status, "reason": found.reason, "map_revision": revision,
                    **_architecture_field(engine, registry)}
        record = found.record
    return {"ok": True, "status": "AVAILABLE", "root": record["artifact_sha256"],
            "selected": record["artifact_sha256"] == selected_sha, "map_revision": revision,
            "freshness": F.freshness(engine.repo_root, record, against, identity()),
            **_architecture_field(engine, registry), "record": _section(record, section)}


def _architecture_field(engine: Any, registry: dict[str, Any] | None) -> dict[str, Any]:
    ref = architecture(engine, registry)
    return {"architecture": ref} if ref else {}


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
