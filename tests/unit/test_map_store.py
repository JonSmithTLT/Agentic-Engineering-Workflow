"""The project-map store and registry (register F22.1; ADR-0015; plan §4.1, §4.2, §5.3, §7 "Store and registry").

Filesystem only, no git: the records come from the in-memory generator."""

from __future__ import annotations

import json
import threading

import pytest
from map_trees import SAMPLE, tree_of

from aew.errors import MapArtifactCorrupt, MapRegistryInvalid, NotFound, StaleRevision, UsageError
from aew.maps import rules, store, structural
from aew.maps.canonical import seal

ACTOR = {"kind": "lead", "id": "tk_0123456789abcdef", "generation": 1}


def record(**files: bytes) -> dict:
    return structural.generate(tree_of({**SAMPLE, **files}), rules.load())


def entry(sha: str, rec: dict) -> dict:
    return {"root": store.artifact_rel(sha), "sha256": sha, "source_revision": rec["source_revision"],
            "source_tree": rec["source_tree"], "object_format": rec["object_format"],
            "generator_version": rec["generator"]["version"], "ruleset_sha256": rec["generator"]["ruleset_sha256"]}


def test_an_artifact_is_content_addressed_canonical_and_read_back_strictly(tmp_path):
    rec = record()
    sha, rel = store.write_artifact(tmp_path, rec)
    assert rel == f"local/maps/structural/{sha}.json"
    assert (tmp_path / rel).read_bytes() == seal(rec)[1]
    assert store.read_artifact(tmp_path, sha) == {**rec, "artifact_sha256": sha}


def test_concurrent_identical_writes_all_succeed_with_one_file(tmp_path):
    rec = record()
    barrier, errors, shas = threading.Barrier(8), [], []

    def write():
        barrier.wait()
        try:
            shas.append(store.write_artifact(tmp_path, rec)[0])
        except Exception as exc:  # collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=write) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(set(shas)) == 1
    assert [p.name for p in (tmp_path / store.STRUCTURAL_REL).iterdir()] == [f"{shas[0]}.json"]


def test_different_bytes_under_an_existing_name_are_corruption_never_nondeterminism(tmp_path):
    rec = record()
    sha, rel = store.write_artifact(tmp_path, rec)
    (tmp_path / rel).write_bytes(b"{}")
    with pytest.raises(MapArtifactCorrupt) as exc:
        store.write_artifact(tmp_path, rec)
    assert exc.value.code == "MAP_ARTIFACT_CORRUPT"


@pytest.mark.parametrize("tamper", ["bytes", "reformatted", "not-json", "schema"])
def test_a_tampered_artifact_is_refused_by_the_strict_reader_and_unavailable_to_consumers(tmp_path, tamper):
    rec = record()
    sha, rel = store.write_artifact(tmp_path, rec)
    store.select_structural(tmp_path, expect=store.NO_REGISTRY, entry=entry(sha, rec), actor=ACTOR)
    path = tmp_path / rel
    stored = json.loads(path.read_bytes())
    if tamper == "bytes":
        stored["sections"]["directories"]["rows"][0]["files"] += 1
        path.write_bytes(json.dumps(stored, sort_keys=True, separators=(",", ":")).encode())
    elif tamper == "reformatted":  # the same content, not canonical bytes
        path.write_bytes(json.dumps(stored, indent=1).encode())
    elif tamper == "not-json":
        path.write_bytes(b"\x00garbage")
    else:  # resealed with a schema violation: the hash matches, the schema does not
        stored.pop("artifact_sha256")
        stored["schema"] = "aew/codebase-map/v0"
        sha2, data = seal(stored)
        path = tmp_path / store.artifact_rel(sha2)
        path.write_bytes(data)
        sha = sha2
        store.select_structural(tmp_path, expect=store.revision_of(store.read_registry(tmp_path)),
                                entry={**entry(sha, rec)}, actor=ACTOR)
    with pytest.raises(MapArtifactCorrupt):
        store.read_artifact(tmp_path, sha)
    found = store.read_selected(tmp_path)
    assert isinstance(found, store.Unavailable) and found.reason == "corrupt"


def test_the_never_raising_reader_names_why_a_map_is_unavailable(tmp_path):
    assert store.read_selected(tmp_path) == store.Unavailable("none")
    rec = record()
    sha, rel = store.write_artifact(tmp_path, rec)
    store.select_structural(tmp_path, expect="none:0", entry=entry(sha, rec), actor=ACTOR)
    found = store.read_selected(tmp_path)
    assert isinstance(found, store.Available) and found.record["artifact_sha256"] == sha
    (tmp_path / rel).unlink()
    assert store.read_selected(tmp_path) == store.Unavailable("missing")
    (tmp_path / store.REGISTRY_REL).write_text("{not json", encoding="utf-8")
    assert store.read_selected(tmp_path) == store.Unavailable("registry_invalid")
    with pytest.raises(MapRegistryInvalid) as exc:
        store.read_registry(tmp_path)
    assert exc.value.code == "MAP_REGISTRY_INVALID"
    with pytest.raises(NotFound):
        store.read_artifact(tmp_path, sha)
    with pytest.raises(UsageError):
        store.read_artifact(tmp_path, "../../control")


def test_selection_is_a_compare_and_set_on_epoch_and_revision_in_its_own_domain(tmp_path):
    rec_a, rec_b = record(), record(**{"new.py": b""})
    a, _ = store.write_artifact(tmp_path, rec_a)
    b, _ = store.write_artifact(tmp_path, rec_b)
    first = store.select_structural(tmp_path, expect="none:0", entry=entry(a, rec_a), actor=ACTOR)
    assert first["map_revision"] == 1 and len(first["epoch"]) == 16
    rev1 = store.revision_of(first)
    with pytest.raises(StaleRevision) as exc:  # a second "first" selection lost the race
        store.select_structural(tmp_path, expect="none:0", entry=entry(b, rec_b), actor=ACTOR)
    assert exc.value.details["domain"] == "map_revision" and exc.value.details["current"] == rev1
    second = store.select_structural(tmp_path, expect=rev1, entry=entry(b, rec_b), actor=ACTOR)
    assert second["map_revision"] == 2 and second["epoch"] == first["epoch"]
    with pytest.raises(StaleRevision):
        store.select_structural(tmp_path, expect=rev1, entry=entry(a, rec_a), actor=ACTOR)
    log = [json.loads(line) for line in (tmp_path / store.LOG_REL).read_text(encoding="utf-8").splitlines()]
    assert [(e["map_revision"], e["previous"], e["new"]) for e in log] == [(1, None, a), (2, a, b)]
    assert all(e["actor"] == ACTOR and e["epoch"] == first["epoch"] for e in log)


def test_a_registry_recreated_after_deletion_refuses_an_old_expectation(tmp_path):
    rec = record()
    sha, _ = store.write_artifact(tmp_path, rec)
    first = store.select_structural(tmp_path, expect="none:0", entry=entry(sha, rec), actor=ACTOR)
    old = store.revision_of(first)
    (tmp_path / store.REGISTRY_REL).unlink()  # local/ is rebuildable: deleting it means "no selection"
    again = store.select_structural(tmp_path, expect="none:0", entry=entry(sha, rec), actor=ACTOR)
    assert again["map_revision"] == 1 and again["epoch"] != first["epoch"]
    assert store.revision_of(again) != old  # same number, new epoch: no ABA
    with pytest.raises(StaleRevision):
        store.select_structural(tmp_path, expect=old, entry=entry(sha, rec), actor=ACTOR)


@pytest.mark.parametrize("bad", ["", "3", "abc:1", "none", "0123456789abcdef:x", "NONE:0"])
def test_a_malformed_expectation_is_a_usage_error(bad):
    with pytest.raises(UsageError):
        store.parse_expectation(bad)


def test_a_failed_registry_write_leaves_a_log_line_the_selection_chain_tells_apart(tmp_path, monkeypatch):
    """PR #126 review, F2 (repro/log_probe.py): the log line is written, the registry write fails, and the next
    selection logs the same (epoch, map_revision) again. The selection ids say which one took effect."""
    rec_a, rec_b = record(), record(**{"n.py": b""})
    a, _ = store.write_artifact(tmp_path, rec_a)
    b, _ = store.write_artifact(tmp_path, rec_b)
    first = store.select_structural(tmp_path, expect="none:0", entry=entry(a, rec_a), actor=ACTOR)

    def crash(*_args, **_kwargs):
        raise OSError("the registry write failed")

    monkeypatch.setattr(store, "atomic_write", crash)
    with pytest.raises(OSError):
        store.select_structural(tmp_path, expect=store.revision_of(first), entry=entry(b, rec_b), actor=ACTOR)
    monkeypatch.undo()
    final = store.select_structural(tmp_path, expect=store.revision_of(first), entry=entry(a, rec_a), actor=ACTOR)
    log = [json.loads(line) for line in (tmp_path / store.LOG_REL).read_text(encoding="utf-8").splitlines()]
    assert [e["map_revision"] for e in log] == [1, 2, 2]  # one revision, two lines: the case the ADR now describes
    assert len({e["selection_id"] for e in log}) == 3
    assert log[0]["previous_selection_id"] is None and first["selection_id"] == log[0]["selection_id"]
    chain, current = [], final["selection_id"]  # from the registry back through previous_selection_id
    by_id = {e["selection_id"]: e for e in log}
    while current:
        chain.append(by_id[current])
        current = by_id[current]["previous_selection_id"]
    assert [(e["map_revision"], e["new"]) for e in chain] == [(2, a), (1, a)]
    phantom = [e for e in log if e not in chain]
    assert [(e["map_revision"], e["new"]) for e in phantom] == [(2, b)]  # the selection that never took effect
