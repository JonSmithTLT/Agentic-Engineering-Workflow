"""A worker's map reads through its run's bridge (register F15.8; the mapping series' PR A): offered only by the run's
launch snapshot, never naming a basis, cooperative, writing no map state, byte-identical when off, and agreeing with
the Lead's read at the same basis."""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_investigation, sample_project
from conftest import git
from fake_harness import POLICY, HarnessLab

from aew import errors
from aew.engine.api import Engine
from aew.engine.authority import ROLE_OPERATIONS
from aew.harness import bridge, runlog
from aew.harness import contract as K
from aew.harness.supervisor import bridge_tables
from aew.maps import EVIDENCE_CLASS, query, store

MAPS = Path(".aew") / store.MAPS_REL


def contract(operations: list[str], extra: dict[str, Any] | None = None) -> K.LaunchContract:
    return K.LaunchContract(
        run="R-INV-0001-1", invocation="INV-0001", work_unit="T-0001", role="investigator", scope="observation",
        card={"id": "investigator", "version": 1, "sha256": "0" * 64}, execution_profile={"harness": "opencode"},
        workspace="/w/obs", expected_kinds=["discovery_record"], operations=operations, pack_path="/p",
        pack_sha256="1" * 64, pack_text="PACK", continuation=None, run_dir="/r", extra=extra or {},
        scratch="/r/scratch")


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------------------------------- the bridge rows


@pytest.mark.parametrize("extra", ["commit", "root", "repo", "workspace"])
def test_a_bridge_map_request_cannot_name_a_basis_or_root(extra):
    """The rows' arguments are exact strings, and none names a commit, root, repository or workspace: a request that
    adds one is refused, so a worker's basis is always its invocation's."""
    tables, _ = bridge_tables(sorted(bridge.MAP_OPERATIONS), messaging=False)
    for op, spec in bridge.MAP_OPERATIONS.items():
        assert all(kind is str for kind in spec.values()) and not {"commit", "root", "repo", "workspace"} & set(spec)
        args = {name: "" for name in spec}
        assert bridge.validate_request({"op": op, "args": args}, tables) == (op, args)
        with pytest.raises(errors.UsageError):
            bridge.validate_request({"op": op, "args": {**args, extra: "HEAD"}}, tables)


def test_map_ops_are_offered_only_when_the_launch_snapshot_turns_them_on(tmp_path):
    """The map ops ride context.read and the run's own launch snapshot: a run launched with the switch on offers them
    to a role that reads context; no snapshot, or a role narrowed without context.read, offers none."""
    engine = Engine.discover(sample_project(tmp_path).root)
    on = {"run": "R-1", **K.maps_reads_snapshot({"maps": {"reads": "structural"}})}
    harness = engine._harness
    assert set(bridge.MAP_OPERATIONS) <= set(harness.operations_of({"role": "investigator", "runs": [on]}))
    assert not set(bridge.MAP_OPERATIONS) & set(harness.operations_of({"role": "investigator", "runs": [{"run": "R"}]}))
    assert not set(bridge.MAP_OPERATIONS) & set(harness.operations_of({"role": "investigator"}))
    narrowed = {"role": "investigator", "runs": [on], "allowed_operations": ["submit.discovery_record"]}
    assert not set(bridge.MAP_OPERATIONS) & set(harness.operations_of(narrowed))
    offered, cooperative = bridge_tables(harness.operations_of({"role": "reviewer", "runs": [on]}), messaging=False)
    assert set(bridge.MAP_OPERATIONS) <= set(offered) and cooperative == frozenset(bridge.MAP_OPERATIONS)


# The worker preamble before map reads existed (origin/main at 2962f12e), for an investigator and for a reviewer with
# messaging on: with the switch off a run's prompt is these bytes exactly, so M4-H's treatment is unchanged.
PREAMBLE_SHA256 = ("98ab21a18807467b887c8f09912a78ea896dd8f30c095ddc37f452f758ca7376",
                   "5bd26e446e02927a065bb5d1d6f3d75695f86c9ca0ee153a21ba46563018be8d")


def test_with_the_switch_off_the_worker_prompt_and_operations_are_byte_identical(tmp_path):
    """F15.8: switched off, the run's prompt is the earlier bytes, its operations are its role's, and its bridge offers
    what it always did; switched on, one line is added, built from the bridge rows' own names."""
    plain = contract(["check.run", "context.read", "submit.discovery_record"])
    messaging = contract(["context.read", "submit.review"], {"coordination": {"messaging": "enabled"}})
    assert tuple(hashlib.sha256(K.preamble(c).encode()).hexdigest() for c in (plain, messaging)) == PREAMBLE_SHA256
    engine = Engine.discover(sample_project(tmp_path).root)
    for role, ops in ROLE_OPERATIONS.items():
        assert engine._harness.operations_of({"role": role, "runs": [{"run": "R-1"}]}) == sorted(ops)
    assert bridge_tables(sorted(ROLE_OPERATIONS["investigator"]), messaging=False) == (bridge.OPERATIONS, frozenset())
    on = contract([*plain.operations, *bridge.MAP_OPERATIONS])
    added = K.preamble(on).removeprefix(K.preamble(plain))
    assert added.startswith("\n- Map reads are on for this run: `aew map show` and `aew map search`")
    assert EVIDENCE_CLASS in added and "\n" not in added[1:]


def test_a_slow_map_query_does_not_hold_check_run():
    """The map rows are cooperative: while a map read is still answering, `check run` and `submit` are served."""
    started, release = threading.Event(), threading.Event()

    def handle(op: str, args: dict[str, Any]) -> Any:
        if op in bridge.MAP_OPERATIONS:
            started.set()
            assert release.wait(30)
            return {"op": op}
        return {"op": op}

    offered, cooperative = bridge_tables(["check.run", "context.read", *bridge.MAP_OPERATIONS], messaging=False)
    server = bridge.BridgeServer(handle, operations=offered, cooperative=cooperative)
    server.start()
    try:
        out: dict[str, Any] = {}
        reader = threading.Thread(target=lambda: out.update(bridge.call(
            "map.search", {"text": "x", "kind": "", "limit": ""}, endpoint=server.address, key=server.key_hex)))
        reader.start()
        assert started.wait(30)
        assert bridge.call("check.run", {"check_id": "unit"}, endpoint=server.address,
                           key=server.key_hex) == {"op": "check.run"}
        release.set()
        reader.join(30)
        assert out == {"op": "map.search"}
    finally:
        release.set()
        server.close()
        server.wait_stopped()


# ------------------------------------------------------------------------------------------- through a real run


def test_a_worker_read_never_changes_selection_and_agrees_with_the_leads_read_at_its_base(tmp_path):
    """A worker run launched with the switch on reads through its bridge at its invocation's base: its prompt names
    the reads, a flag naming another basis is refused, and `.aew/local/maps/` (the registry, its log and the
    artifacts) is byte-identical afterwards, though the selected map is STALE for that base (only a Lead's dispatch
    refreshes one). The Lead's `aew map search` and `aew map show --scope ticket` at the same commit give the same
    facts."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path,
                            policy={**POLICY, "maps": {"pack_slices": "structural", "reads": "structural"}})
    try:
        p = lab.project
        wid = create_investigation(p, tmp_path)
        inv = lab.lead("work", "dispatch", wid)["invocation"]
        p.lead("work", "transition", wid, "--to", "RUNNING")
        base = Engine.discover(p.root).store.read()["invocations"][inv]["snapshot"]["base_revision"]
        (p.root / "notes").mkdir()
        (p.root / "notes" / "n.md").write_text("n\n", encoding="utf-8")
        git("add", "notes/n.md", cwd=p.root)
        git("commit", "-q", "-m", "advance", cwd=p.root)
        rev = p.ok("map", "show", "--json")["map_revision"]
        p.ok("map", "generate", "--select", "--expect-map-rev", rev, "--json", env={"AEW_LEAD_TOKEN": p.token})
        before = snapshot(p.root / MAPS)
        lab.script(inv, [{"do": "aew", "args": ["map", "show", "--json"]},
                         {"do": "aew", "args": ["map", "show", "--scope", "ticket", "--json"]},
                         {"do": "aew", "args": ["map", "search", "core.py", "--json"]},
                         {"do": "aew", "args": ["map", "show", "--section", "languages", "--json"]},
                         {"do": "aew", "args": ["map", "search", "core.py", "--commit", "HEAD", "--json"]},
                         {"do": "aew", "args": ["whoami"]}])
        run = lab.lead("harness", "launch", inv)["run"]
        assert lab.wait(run)["status"] == "ended_without_evidence"
        assert snapshot(p.root / MAPS) == before  # nothing written, nothing selected, no refresh

        status, scoped, found, section, refused, whoami = (lab.step(run, i) for i in range(6))
        assert status["exit"] == 0, status
        answer = status["stdout_json"]
        assert answer["basis"]["commit"] == base and answer["basis"]["chosen_by"] == query.INVOCATION_BASE
        assert answer["basis"]["recipient"] == {"kind": "worker", "invocation": inv, "role": "investigator",
                                                "work_unit": wid}
        assert answer["freshness"]["structural"]["status"] == "STALE"
        assert section["stdout_json"]["items"][0]["section"] == "languages"
        assert refused["exit"] != 0 and "worker_basis" in refused["stdout"] + refused["stderr"]
        assert set(bridge.MAP_OPERATIONS) <= set(whoami["stdout_json"]["operations"])
        prompt = (runlog.run_dir(lab.aew_root, run) / "harness" / "prompt.md").read_text(encoding="utf-8")
        assert "- Map reads are on for this run: `aew map show` and `aew map search`" in prompt

        lead_found = p.ok("map", "search", "core.py", "--commit", base, "--json")
        lead_scoped = p.ok("map", "show", "--scope", "ticket", "--work", wid, "--commit", base, "--json")
        for worker, lead in ((found["stdout_json"], lead_found), (scoped["stdout_json"], lead_scoped)):
            for key in ("terminal", "items", "coverage", "omitted", "map", "freshness"):
                assert worker[key] == lead[key], key
            assert worker["basis"]["commit"] == lead["basis"]["commit"] == base
        assert [i["path"] for i in lead_found["items"]] == ["calc/core.py"]
    finally:
        lab.cleanup()
