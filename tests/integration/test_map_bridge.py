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
from aew.knowledge import evidence as E
from aew.maps import EVIDENCE_CLASS, query, store
from aew.util import dump_yaml

MAPS = Path(".aew") / store.MAPS_REL


def contract(operations: list[str], extra: dict[str, Any] | None = None) -> K.LaunchContract:
    return K.LaunchContract(
        run="R-INV-0001-1", invocation="INV-0001", work_unit="T-0001", role="investigator", scope="observation",
        card={"id": "investigator", "version": 1, "sha256": "0" * 64}, execution_profile={"harness": "fake"},
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


# The worker preamble with map reads off, for an investigator and for a reviewer with messaging on. The second is the
# bytes from before map reads existed (origin/main at 2962f12e). The first is those bytes (98ab21a1...) with one token
# changed by E368's truth fixes (#613 review m3): `aew check run <check-id>` where it read `<check>`. So the switch adds
# nothing when it is off; a role that may run a check no longer gets 2962f12e's bytes, and no M4-H run was recorded on
# them. The harness is one with no measured wait, so the messaging line is the same on every platform
# (`preamble_wait_supported`).
PREAMBLE_SHA256 = ("a03df6c0b4e72312b003875d2e29d407a14f3615b1c816c3e085994f305a4d06",
                   "d5f53501542bfa2d0da969aca8d9eac777b16e4e10c4b91838487bcaaec5babc")


def test_with_the_switch_off_the_worker_prompt_and_operations_are_byte_identical(tmp_path):
    """F15.8: switched off, the run's prompt is the pinned bytes, its operations are its role's, and its bridge offers
    what it always did; switched on, one line is added, built from the bridge rows' own names."""
    plain = contract(["check.run", "context.read", "submit.discovery_record"])
    messaging = contract(["context.read", "submit.review"], {"coordination": {"messaging": "enabled"}})
    assert tuple(hashlib.sha256(K.preamble(c).encode()).hexdigest() for c in (plain, messaging)) == PREAMBLE_SHA256
    engine = Engine.discover(sample_project(tmp_path).root)
    for role, ops in ROLE_OPERATIONS.items():  # its role's, less a submit its scope never takes (E160, #581 F1)
        assert engine._harness.operations_of({"role": role, "runs": [{"run": "R-1"}]}) == sorted(
            E.submit_operations(ops, role, None))
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


# ------------------------------------------------------------------------------------------- the supervisor's handler


def test_the_supervisors_map_read_holds_no_serialization_while_it_answers(tmp_path, monkeypatch):
    """m5 of #576's review: `Supervisor._map_read` takes the bridge's serialization only for the credential check and
    the state read, so while a map read is still answering (here `query.serve` blocks), `check run` is served. The
    proof fails if the query runs inside `bridge.serialized()`."""
    from types import SimpleNamespace

    from aew.engine import api
    from aew.harness import supervisor

    store = SimpleNamespace(read_committed=lambda: {})
    engine = SimpleNamespace(
        store=store, repo_root=tmp_path, aew_root=tmp_path, run_authority_problem=lambda *a: None,
        map_read_basis=lambda **kw: {"workspace": str(tmp_path), "base": "HEAD", "scope_paths": [],
                                     "recipient": {"kind": "worker"}},
        check_run=lambda **kw: {"op": "check.run"})
    monkeypatch.setattr(api, "Engine", lambda repo_root, aew_root: engine)
    monkeypatch.setattr(supervisor, "token_id_of", lambda credential: "tok-1")
    sup = supervisor.Supervisor(tmp_path, {"run": "R-INV-0001-1", "invocation": "INV-0001", "credential": "tok-1",
                                           "repo_root": str(tmp_path), "aew_root": str(tmp_path)}, ack=None)
    started, release = threading.Event(), threading.Event()

    def blocking(ctx: Any, op: str, args: dict[str, Any]) -> Any:
        started.set()
        assert release.wait(30)
        return {"op": op}

    monkeypatch.setattr(query, "serve", blocking)
    offered, cooperative = bridge_tables(["check.run", "context.read", *bridge.MAP_OPERATIONS], messaging=False)
    sup.bridge = bridge.BridgeServer(sup.handle, operations=offered, cooperative=cooperative)
    sup.bridge.start()
    call = {"endpoint": sup.bridge.address, "key": sup.bridge.key_hex}
    try:
        reader = threading.Thread(target=lambda: bridge.call("map.show", {"section": "", "scope": ""}, **call))
        reader.start()
        assert started.wait(30)
        checked: dict[str, Any] = {}
        check = threading.Thread(target=lambda: checked.update(bridge.call("check.run", {"check_id": "unit"}, **call)))
        check.start()
        check.join(10)
        assert checked == {"op": "check.run"}, "check run waited for a map read"
    finally:
        release.set()
        reader.join(30)
        sup.bridge.close()
        sup.bridge.wait_stopped()


# ------------------------------------------------------------------------------------------- a dispatch's --launch


@pytest.mark.parametrize("reads", ["structural", "off"])
def test_a_dispatch_launch_records_the_maps_snapshot_and_an_off_run_names_why_it_has_no_reads(tmp_path, reads):
    """m7 and m8 of #576's review: a dispatch's `--launch` records the run's `maps.reads` snapshot exactly when the
    switch is on; and in a run launched with it off, a worker's `aew map show` and `aew map search` are refused with
    the cause and the next step, typed (PERMISSION_DENIED, reason maps_reads_off)."""
    lab = HarnessLab.create(sample_project(tmp_path), tmp_path,
                            policy={**POLICY, "maps": {"pack_slices": "structural", "reads": reads}})
    try:
        p = lab.project
        wid = create_investigation(p, tmp_path)
        lab.script("default", [{"do": "aew", "args": ["map", "show", "--json"]},
                               {"do": "aew", "args": ["map", "search", "core.py", "--json"]}])
        run = lab.lead("work", "dispatch", wid, "--launch")["launch"]["run"]
        assert lab.wait(run)["status"] == "ended_without_evidence"
        inv = next(i for i in Engine.discover(p.root).store.read()["invocations"].values() if i["work_unit"] == wid)
        [entry] = inv["runs"]
        shown, searched = lab.step(run, 0), lab.step(run, 1)
        if reads == "structural":
            assert entry["maps"] == {"reads": "structural"}
            assert shown["exit"] == 0 and shown["stdout_json"]["schema"] == query.SCHEMA
        else:
            assert "maps" not in entry
            for refused in (shown, searched):
                error = (refused.get("stderr_json") or refused.get("stdout_json") or {})["error"]
                assert refused["exit"] != 0 and error["code"] == "PERMISSION_DENIED"
                assert error["details"]["reason"] == "maps_reads_off"
                assert "launched with maps.reads off" in error["message"]
                assert "read the source in your workspace, or ask the Lead" in error["message"]
    finally:
        lab.cleanup()


# A project card that narrows the investigator's operations and leaves out context.read, which the map reads ride.
NO_CONTEXT_INVESTIGATOR = {
    "schema": "aew/role/v1", "role": "no_context_investigator", "display_name": "No-context Investigator",
    "version": 1, "extends": "investigator", "purpose": "Investigates without reading context.",
    "restrict": {"operations": ["check.run", "submit.discovery_record"]},
}


@pytest.mark.parametrize(("reads", "card", "reason"), [
    ("off", None, "maps_reads_off"),
    ("structural", NO_CONTEXT_INVESTIGATOR, "context_read_narrowed"),
    ("off", NO_CONTEXT_INVESTIGATOR, "context_read_narrowed"),
], ids=["switch-off", "card-narrowed", "both"])
def test_a_refused_worker_map_read_names_the_switch_only_when_the_invocation_reads_context(tmp_path, reads, card,
                                                                                            reason):
    """q1 of #576's quick check: a run that offers no map read is refused with the cause that holds. The switch is
    named only when the invocation is offered context.read; a role card that narrows context.read away is named as the
    cause instead, even with the switch on, and turning the switch on would not help it. Either way the refusal is
    typed (PERMISSION_DENIED with its reason) and gives the same next step."""
    p = sample_project(tmp_path)
    if card:
        roles = p.root / ".aew" / "roles"
        roles.mkdir(exist_ok=True)
        (roles / f"{card['role']}.yaml").write_text(dump_yaml(card), encoding="utf-8", newline="\n")
    lab = HarnessLab.create(p, tmp_path, policy={**POLICY, "maps": {"pack_slices": "structural", "reads": reads}})
    try:
        wid = create_investigation(lab.project, tmp_path, card=card["role"] if card else None)
        lab.script("default", [{"do": "aew", "args": ["map", "show", "--json"]},
                               {"do": "aew", "args": ["map", "search", "core.py", "--json"]}])
        run = lab.lead("work", "dispatch", wid, "--launch")["launch"]["run"]
        assert lab.wait(run)["status"] == "ended_without_evidence"
        for refused in (lab.step(run, 0), lab.step(run, 1)):
            error = (refused.get("stderr_json") or refused.get("stdout_json") or {})["error"]
            assert refused["exit"] != 0 and error["code"] == "PERMISSION_DENIED"
            assert error["details"]["reason"] == reason
            assert ("launched with maps.reads off" in error["message"]) == (reason == "maps_reads_off")
            if card:
                assert error["details"]["card"] == card["role"]
                assert f"role card {card['role']} narrows" in error["message"]
            assert "read the source in your workspace, or ask the Lead" in error["message"]
    finally:
        lab.cleanup()
