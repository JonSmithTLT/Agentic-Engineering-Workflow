"""The structural map in packs and the resume view, over real git and the real CLI (register F22.1 plan §5, §7 PR B;
design v0.5 §10, §11; T5-INV-01, 07, 10).

With the switch off (the default) packs and the resume view are byte-identical to a project without maps, map or no
map. With it on, only a role whose context names codebase_map (today the investigator) gets the bounded slice, its
pack pins the map it used, and regeneration shows the pinned map and freshness. Architecture selection records an
existing discovery record. And no state of ``.aew/local/maps/`` changes what dispatch, gates, transitions or resume
do: the no-authority walk."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from aewflow import (
    assign,
    complete_investigation,
    create_investigation,
    create_planned_ticket,
    dispatch,
    sample_project,
    submit_record,
    to_commit_ready,
)
from conftest import Project, git

from aew.maps import slices, store

MAPS = Path(".aew") / store.MAPS_REL


def switch_on(p: Project) -> None:
    policy = p.root / ".aew" / "policy" / "execution.yaml"
    policy.write_text(policy.read_text(encoding="utf-8") + "maps: {pack_slices: structural}\n", encoding="utf-8",
                      newline="\n")
    p.adopt_policy("turn the structural map slices on")  # the operator's configuration decision (SMQ-01)


def map_rev(p: Project) -> str:
    return p.ok("map", "show", "--json")["map_revision"]


def select_map(p: Project) -> dict[str, Any]:
    rev = map_rev(p)
    if rev == "invalid":
        shutil.rmtree(p.root / MAPS / "registry.json", ignore_errors=True)
        (p.root / MAPS / "registry.json").unlink(missing_ok=True)
        rev = map_rev(p)
    return p.ok("map", "generate", "--token", p.token, "--select", "--expect-map-rev", rev, "--json")


def advance_main(p: Project, name: str) -> str:
    """A new commit on the authoritative branch that adds a path: every earlier map is STALE (path_listing)."""
    (p.root / "notes").mkdir(exist_ok=True)
    (p.root / "notes" / name).write_text("note\n", encoding="utf-8", newline="\n")
    git("add", f"notes/{name}", cwd=p.root)
    git("commit", "-q", "-m", f"add {name}", cwd=p.root)
    return git("rev-parse", "HEAD", cwd=p.root)


def invocations(p: Project) -> dict[str, dict[str, Any]]:
    from aew.engine.api import Engine

    return Engine.discover(p.root).store.read()["invocations"]


def pack_text(p: Project, inv: str) -> str:
    return (p.root / ".aew" / "local" / "packs" / inv / "pack.md").read_text(encoding="utf-8")


def regenerate(p: Project, inv: str) -> dict[str, Any]:
    return p.ok("context", "pack", inv)


def derived(p: Project) -> list[dict[str, Any]]:
    return p.ok("resume", "--json")["derived_knowledge"]


# ------------------------------------------------------------------------------------------- the switch off


def test_with_the_switch_off_every_pack_and_the_resume_view_are_byte_identical_map_or_no_map(tmp_path):
    """Plan §5.4 and SMQ-01: the Q7/M4-H treatment is unchanged by default. Packs built before a map existed
    regenerate to the same bytes once one is selected, a pack built with a map selected is the pack without it, and
    the resume view's derived knowledge does not move."""
    p = sample_project(tmp_path)
    to_commit_ready(p, tmp_path)  # implementer, reviewer and verifier packs
    _, investigator = dispatch(p, create_investigation(p, tmp_path, title="Survey"))
    dispatch(p, create_investigation(p, tmp_path, title="Research", card="researcher"))
    dispatch(p, create_investigation(p, tmp_path, title="Plan it", card="planner"))
    before = {inv: i["pack"]["sha256"] for inv, i in invocations(p).items() if i.get("pack")}
    roles = {i["role"] for i in invocations(p).values()}
    assert roles >= {"implementer", "reviewer", "verifier", "investigator", "researcher", "planner"}, roles
    knowledge = derived(p)
    select_map(p)
    for inv, sha in before.items():
        out = regenerate(p, inv)
        assert out["matches_recorded"] and out["sha256"] == sha, inv
    assert derived(p) == knowledge
    role, out = dispatch(p, create_investigation(p, tmp_path, title="With a map selected"))
    inv = out["invocation"]
    assert not slices.pinned(invocations(p)[inv]["pack"]["sources"])
    assert slices.HEADING not in pack_text(p, inv)
    shutil.rmtree(p.root / MAPS)
    assert regenerate(p, inv)["matches_recorded"]


# ------------------------------------------------------------------------------------------- the switch on


def test_with_the_switch_on_only_the_investigator_gets_the_slice_and_its_pack_pins_the_map(tmp_path):
    p = sample_project(tmp_path)
    switch_on(p)
    first = select_map(p)
    _, out = dispatch(p, create_investigation(p, tmp_path))
    inv = out["invocation"]
    entry = slices.pinned(invocations(p)[inv]["pack"]["sources"])
    assert entry and entry["sha256"] == first["root"] and entry["freshness"]["status"] == "CURRENT"
    text = pack_text(p, inv)
    assert slices.HEADING in text and f"map {first['root'][:12]}" in text and ": CURRENT" in text
    assert text.rstrip().endswith("```")  # the last section of the pack
    impl = create_planned_ticket(p, tmp_path)
    assign(p, impl)
    implementer = next(i for i in invocations(p).values() if i["role"] == "implementer")
    assert not slices.pinned(implementer["pack"]["sources"]) and slices.HEADING not in pack_text(
        p, next(k for k, i in invocations(p).items() if i["role"] == "implementer"))
    # Regeneration after a reselect shows the pinned map and its pinned freshness, never the new ones.
    advance_main(p, "after.txt")
    second = select_map(p)
    assert second["root"] != first["root"]
    again = regenerate(p, inv)
    assert again["matches_recorded"] and f"map {first['root'][:12]}" in pack_text(p, inv)
    # A pinned artifact that is gone is a missing source: regeneration reports the mismatch.
    (p.root / ".aew" / store.artifact_rel(first["root"])).unlink()
    gone = regenerate(p, inv)
    assert not gone["matches_recorded"] and "no longer readable" in pack_text(p, inv)


def test_the_resume_row_carries_the_maps_freshness_and_its_qualification_only_with_the_switch_on(tmp_path):
    p = sample_project(tmp_path)
    off = {r["name"]: r for r in derived(p)}["codebase_map"]
    select_map(p)
    assert {r["name"]: r for r in derived(p)}["codebase_map"] == off
    switch_on(p)
    row = {r["name"]: r for r in derived(p)}["codebase_map"]
    assert row["freshness"] == "CURRENT" and row["artifact_sha256"]
    advance_main(p, "more.txt")
    row = {r["name"]: r for r in derived(p)}["codebase_map"]
    assert row["freshness"] == "STALE" and row["reasons"] == ["path_listing"]  # T5-INV-10: the reason survives
    (p.root / ".aew" / store.artifact_rel(row["artifact_sha256"])).write_bytes(b"{}")
    row = {r["name"]: r for r in derived(p)}["codebase_map"]
    assert row == {"name": "codebase_map", "path": None, "freshness": "UNAVAILABLE", "detail": "corrupt"}


# ------------------------------------------------------------------------------------------- architecture selection


def test_architecture_selection_records_an_existing_discovery_record_and_refuses_anything_else(tmp_path):
    p = sample_project(tmp_path)
    discovery = complete_investigation(p, create_investigation(p, tmp_path, title="Architecture survey"))
    research = complete_investigation(p, create_investigation(p, tmp_path, title="Library", card="researcher"),
                                      kind="research_record")
    rev = map_rev(p)
    missing = p.aew("map", "select-architecture", "EV-NOPE", "--token", p.token, "--expect-map-rev", rev)
    assert missing.returncode == 2 and missing.error["code"] == "NOT_FOUND"
    wrong = p.aew("map", "select-architecture", research, "--token", p.token, "--expect-map-rev", rev)
    assert wrong.error["code"] == "VALIDATION_FAILED" and wrong.error["details"]["reason"] == "not_discovery_evidence"
    ok = p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", rev, "--json")
    assert ok["architecture"]["evidence_id"] == discovery and ok["architecture"]["freshness"]["status"] == "CURRENT"
    stale = p.aew("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", rev)
    assert stale.returncode == 3 and stale.error["details"]["domain"] == "map_revision"
    shown = p.ok("map", "show", "--json")  # no structural map yet: still reported, never refused
    assert shown["status"] == "UNAVAILABLE" and shown["architecture"]["evidence_id"] == discovery
    # A stale reference is labelled stale and blocks nothing.
    (p.root / "calc" / "core.py").write_text("def add(a, b):\n    return b + a\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "change calc", cwd=p.root)
    assert p.ok("map", "show", "--json")["architecture"]["freshness"]["status"] == "STALE"
    complete_investigation(p, create_investigation(p, tmp_path, title="Still dispatches"))
    log = [json.loads(line) for line in (p.root / MAPS / "registry-log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert log[-1]["capability"] == "architecture" and log[-1]["new"] == discovery


def aew_files(p: Project) -> dict[str, str]:
    """Every file under ``.aew/`` outside ``local/``, by content."""
    aew = p.root / ".aew"
    return {f.relative_to(aew).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in aew.rglob("*")
            if f.is_file() and not f.relative_to(aew).as_posix().startswith("local/")}


def test_architecture_selection_never_touches_control_state_or_control_revision(tmp_path):
    """T5-INV-11 for ``map select-architecture`` (PR #143 review, m2): an accepted and a refused selection leave the
    control state, ``control_revision`` and every file under ``.aew/`` outside ``local/`` byte-identical; only the map
    registry and its log change."""
    p = sample_project(tmp_path)
    discovery = complete_investigation(p, create_investigation(p, tmp_path, title="Architecture survey"))
    control = p.root / ".aew" / "state" / "control.yaml"
    rev, state, files = p.rev(), control.read_bytes(), aew_files(p)
    p.ok("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", map_rev(p), "--json")
    assert (p.rev(), control.read_bytes(), aew_files(p)) == (rev, state, files)
    registry = (p.root / MAPS / "registry.json").read_bytes()
    stale = p.aew("map", "select-architecture", discovery, "--token", p.token, "--expect-map-rev", "none:0")
    assert stale.returncode == 3 and stale.error["details"]["domain"] == "map_revision"
    assert (p.rev(), control.read_bytes(), aew_files(p)) == (rev, state, files)
    assert (p.root / MAPS / "registry.json").read_bytes() == registry  # a refused selection writes nothing


def test_adopting_an_unquoted_off_is_refused_with_its_cause_and_the_quoted_fix(tmp_path):
    """PR #143 review, m1, at adoption: an operator turning the slices off with a bare ``off`` (a YAML boolean) is
    refused with the cause and the fix, nothing is adopted, and the quoted ``"off"`` is adopted."""
    import pytest

    from aew.errors import ValidationFailed

    p = sample_project(tmp_path)
    policy = p.root / ".aew" / "policy" / "execution.yaml"
    original, rev = policy.read_text(encoding="utf-8"), p.rev()
    policy.write_text(original + "maps:\n  pack_slices: off\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValidationFailed) as refused:
        p.adopt_policy("turn the slices off, unquoted")
    assert refused.value.details["reason"] == "yaml_boolean" and 'pack_slices: "off"' in refused.value.message
    assert p.rev() == rev
    policy.write_text(original + 'maps:\n  pack_slices: "off"\n', encoding="utf-8", newline="\n")
    p.adopt_policy("turn the slices off, quoted")
    assert p.rev() == rev + 1


def test_an_invocation_credential_is_refused_architecture_selection(tmp_path):
    p = sample_project(tmp_path)
    role, _ = dispatch(p, create_investigation(p, tmp_path))
    record = submit_record(role, "discovery_record")["evidence"]
    res = p.aew("map", "select-architecture", record, "--token", role.token, "--expect-map-rev", "none:0")
    assert res.returncode == 4 and res.error["code"] == "PERMISSION_DENIED"
    assert not (p.root / MAPS / "registry.json").exists()


# ------------------------------------------------------------------------------------------- the no-authority walk


CONDITIONS = ["none", "stale", "missing", "corrupt", "registry_invalid"]


def set_condition(p: Project, condition: str, n: int) -> str:
    """Put ``.aew/local/maps/`` into ``condition``; returns the text the investigator's pack must show for it."""
    maps = p.root / MAPS
    shutil.rmtree(maps, ignore_errors=True)
    if condition == "none":
        return "- UNAVAILABLE (none)"
    selected = select_map(p)
    artifact = p.root / ".aew" / store.artifact_rel(selected["root"])
    if condition == "stale":
        advance_main(p, f"walk-{n}.txt")
        return "STALE (path_listing)"
    if condition == "missing":
        artifact.unlink()
    elif condition == "corrupt":
        artifact.write_bytes(b"{}")
    else:
        (maps / "registry.json").write_text("{not json", encoding="utf-8")
    return f"- UNAVAILABLE ({condition})"


def test_no_map_state_changes_dispatch_gates_transitions_or_resume(tmp_path):
    """T5-INV-01 with the switch on: a stale, missing or corrupt map, or a malformed registry, gives the same outcomes
    as no map at all: the investigation dispatches, its record is ingested and accepted, its gates read the same, and
    resume works, with the map reported for what it is."""
    p = sample_project(tmp_path)
    switch_on(p)
    outcomes = {}
    for n, condition in enumerate(CONDITIONS):
        shown = set_condition(p, condition, n)
        wid = create_investigation(p, tmp_path, title=f"Walk {condition}")
        role, out = dispatch(p, wid)
        assert shown in pack_text(p, out["invocation"]), condition
        record = submit_record(role, "discovery_record")["evidence"]
        p.lead("evidence", "ingest", wid, "--evidence", record)
        gates = {g: v["status"] for g, v in p.ok("gate", "show", wid)["gates"].items()}
        p.lead("work", "accept", wid)
        state = p.ok("work", "show", wid)["control"]["state"]
        row = {r["name"]: r for r in derived(p)}["codebase_map"]
        assert row["freshness"] in {"UNAVAILABLE", "STALE"}, row
        outcomes[condition] = (gates, state)
    assert all(o == outcomes["none"] for o in outcomes.values()), outcomes
    assert outcomes["none"][1] == "DONE"


def test_a_policy_the_engine_cannot_read_turns_no_map_on(tmp_path, monkeypatch):
    """Defence in depth for T5-INV-01: if the execution policy cannot be read, the switch is off for packs and resume
    (dispatch refuses such a policy on its own; a map never adds a refusal of its own)."""
    from aew.engine.api import Engine
    from aew.engine.base import Kernel
    from aew.errors import ValidationFailed

    p = sample_project(tmp_path)
    switch_on(p)
    select_map(p)
    engine = Engine.discover(p.root)
    assert {r["name"]: r for r in engine.resume()["derived_knowledge"]}["codebase_map"]["freshness"] == "CURRENT"

    def unreadable(_self):
        raise ValidationFailed("unreadable policy")

    monkeypatch.setattr(Kernel, "execution_policy", unreadable)
    row = {r["name"]: r for r in engine.resume()["derived_knowledge"]}["codebase_map"]
    assert row["freshness"] == "UNAVAILABLE" and row["detail"] == "not generated"  # the row as it is without maps
