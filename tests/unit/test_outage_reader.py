"""O-02 conformance through the operator's ordinary CLI, with a real committed store and no service."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml
from conftest import make_git_repo, run_aew
from jsonschema import Draft202012Validator, FormatChecker

from aew import hoststate, process_kind
from aew.cli.main import main
from aew.engine import outbox
from aew.engine.api import Engine
from aew.engine.store import LOCK_REL, ControlStore
from aew.harness import event_spool, lead_broker, notify, runlog
from aew.stg02 import adopted, outage, outage_host, wire

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))

from aewflow import complete_investigation, create_investigation, dispatch, sample_project, submit_record  # noqa: E402

OPENAPI = Path(__file__).resolve().parents[2] / "docs/contracts/A-25/openapi-d01-v0.3.4-REVIEW-CANDIDATE.yaml"
PATHS = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["paths"]
REFUSAL = ("This is the operator's outage read, run outside AEW's sandbox. In a Lead session use `aew status`; "
           "in a worker run use `aew check run`. Outside a sandbox, run an `aew` command that writes, such as "
           "`aew status`, once to restore `.aew/local`.")
UNSUPPORTED = {
    "coverage": "list what this channel covers",
    "research/claims/{claim_id}": "until research claims are built",
    "knowledge": "archived work units",
    "knowledge/{knowledge_id}/versions/{version_id}": "archived work units",
    "knowledge/{knowledge_id}/versions/{version_id}/activity": "archived work units",
    "capabilities": "until the capability records are pinned",
    "owner-operations": "until owner operations are committed",
    "holds/{hold_id}/recovery": "would bind under",
}


@pytest.fixture(scope="module")
def committed_example(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("outage-example")
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path)
    role, _ = dispatch(p, wid)
    report = submit_record(role, "discovery_record")["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", report)
    engine = Engine.discover(p.root)
    state = engine.store.read_committed()
    inv = state["work"][wid]["invocations"][-1]
    assert state["work"][wid]["evidence"], "fixture must exercise package and resolver items"
    return engine, wid, inv


@pytest.fixture
def project(tmp_path, monkeypatch, committed_example):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "host-state"))
    monkeypatch.setenv(hoststate.base_variable(), str(tmp_path / "host-data"))
    engine, wid, inv = committed_example
    root = tmp_path / "project"
    shutil.copytree(engine.repo_root, root)
    return Engine.discover(root), wid, inv


def command(engine, capsys, route, *, human=False):
    argv = ["-C", str(engine.repo_root), "read", *(["--human"] if human else []), route]
    code = main(argv)
    captured = capsys.readouterr()
    assert captured.err == ""
    return code, captured.out if human else json.loads(captured.out)


def assert_schema(path, body):
    status = str(body.get("status", 200))
    content = PATHS[path]["get"]["responses"][status]["content"]
    name = next(iter(content.values()))["schema"]["$ref"].split("/")[-1]
    frozen = adopted.load("aew-d01-read-v0.3.4-FULL.schema.json")
    checker = Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": frozen["$defs"]},
                                   format_checker=FormatChecker())
    checker.validate(body)


def fixture_routes(engine, wid, inv):
    state = engine.store.read_committed()
    revision = state["work"][wid]["plan"]["accepted"]
    fields = {"attachment_id": wire.b64url(f"aew:attachment:{state['lead']['generation']}"),
              "work_kind": "ticket", "work_id": wire.b64url(wid), "subject_kind": "ticket",
              "subject_id": wire.b64url(wid), "execution_id": wire.b64url(inv)}
    for key in ("claim_id", "knowledge_id", "version_id", "hold_id"):
        fields[key] = wire.b64url(f"example:{key}")
    for path in PATHS:
        request = path.format(**fields)
        if path.endswith("/resolve"):
            request += f"?kind=assurance_basis&id={quote(f'aew:assurance:{wid}')}&revision=plan-{revision}"
        yield path, request


def tree_inventory(root):
    inventory = {}
    if root.exists():
        for path in (root, *root.rglob("*")):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                content = hashlib.sha256(path.read_bytes()).hexdigest()
            elif stat.S_ISLNK(info.st_mode):
                content = os.readlink(path)
            else:
                content = None
            inventory[path.relative_to(root).as_posix()] = (info.st_mode, info.st_size, info.st_mtime_ns, content)
    return inventory


def test_every_route_answers_without_a_service_and_validates_against_its_own_wire_schema(project, monkeypatch, capsys):
    engine, wid, inv = project

    def no_service(*args, **kwargs):
        pytest.fail("the outage reader tried to contact a service")

    monkeypatch.setattr(socket.socket, "connect", no_service)
    assert {outage.PREFIX + row.path for row in outage.ROUTES} == set(PATHS)
    served = unsupported = 0
    for path, request in fixture_routes(engine, wid, inv):
        code, body = command(engine, capsys, request)
        assert_schema(path, body)
        row = path.removeprefix("/v1/read/")
        if row in UNSUPPORTED:
            unsupported += 1
            if row.startswith("holds/"):
                assert code and body["code"] == "not_found_or_not_disclosable"
            else:
                assert code == 0 and body["outcome"] == "unsupported" and body["items"] == []
        else:
            served += 1
            assert code == 0 and body["outcome"] in ("historical", "partial")
            if row not in ("waiting", "attention"):
                assert body["items"], row
    assert (served, unsupported) == (12, 8)


def test_all_unsupported_renderings_name_the_destination_and_skip_the_control_store(project, monkeypatch, capsys):
    engine, wid, inv = project
    routes = list(fixture_routes(engine, wid, inv))

    def no_store(*args, **kwargs):
        pytest.fail("an unsupported route opened the control file")

    monkeypatch.setattr(ControlStore, "read_committed", no_store)
    for path, request in routes:
        row = path.removeprefix("/v1/read/")
        if row in UNSUPPORTED:
            _, rendered = command(engine, capsys, request, human=True)
            assert "not read on this channel" in rendered.lower()
            assert UNSUPPORTED[row] in rendered
    _, rendered = command(engine, capsys, "/v1/read/attention?lane=agent_attention", human=True)
    assert "agent's raise is a committed record" in rendered
    assert main(["-C", str(engine.repo_root), "read", "--help"]) == 0
    profile = capsys.readouterr().out
    assert all(path in profile for path in PATHS)


def test_every_route_never_writes_opens_a_control_lock_or_runs_recovery(project, monkeypatch, capsys):
    engine, wid, inv = project
    routes = list(fixture_routes(engine, wid, inv))

    def never(*args, **kwargs):
        pytest.fail("the outage reader tried to take the control lock or run recovery")

    original = ControlStore.read_committed

    def committed(store):
        assert process_kind.declared() == "aew read"
        assert process_kind.kind() == process_kind.NON_WRITER
        return original(store)

    monkeypatch.setattr(ControlStore, "control_lock", never)
    monkeypatch.setattr(ControlStore, "_recover", never)
    monkeypatch.setattr(ControlStore, "read_committed", committed)
    monkeypatch.setenv("AEW_PROFILE", str(engine.aew_root / "local/profile.jsonl"))
    roots = (engine.repo_root, Path(os.environ["XDG_STATE_HOME"]), Path(os.environ[hoststate.base_variable()]))
    before = {root: tree_inventory(root) for root in roots}
    for _, request in routes:
        command(engine, capsys, request)
        command(engine, capsys, request, human=True)
    assert {root: tree_inventory(root) for root in roots} == before


@pytest.mark.parametrize("marker", [None, lead_broker.ENV_ENDPOINT, lead_broker.ENV_KEY,
                                   process_kind.AGENT_ENDPOINT_ENV, process_kind.LEAD_CONTAINED_ENV])
def test_refusal_has_the_same_d01_problem_before_route_or_store_read(project, monkeypatch, capsys, marker):
    engine, _, _ = project
    if marker is None:
        shutil.rmtree(engine.aew_root / "local")
    else:
        monkeypatch.setenv(marker, "fixture")

    def no_store(*args, **kwargs):
        pytest.fail("a refused caller got as far as the control file")

    with monkeypatch.context() as patch:
        patch.setattr(ControlStore, "read_committed", no_store)
        code, body = command(engine, capsys, "/not/a/route")
        assert code != 0
        assert body == {"type": "about:blank", "title": REFUSAL, "status": 401, "code": "authentication_unqualified",
                        "retry": "reauthenticate", "correlation_id": body["correlation_id"]}
        _, human = command(engine, capsys, "/not/a/route", human=True)
        assert human.strip() == f"authentication_unqualified: {REFUSAL}"
    if marker is None:
        assert main(["-C", str(engine.repo_root), "status"]) == 0
        capsys.readouterr()
        assert (engine.aew_root / LOCK_REL).is_file()
        code, body = command(engine, capsys, "/v1/read/work")
        assert code == 0 and body["items"]


def test_outage_stamps_use_the_wire_shape_and_never_claim_current_entitlement(project, capsys):
    engine, wid, inv = project
    state = engine.store.read_committed()
    scope, version = f"aew:project:{state['project_id']}", f"aew:rev:{state['revision']}"
    for _, request in fixture_routes(engine, wid, inv):
        _, body = command(engine, capsys, request)
        if "outcome" not in body:
            continue
        assert {"historical_only", "source_unqualified", "G4_unqualified"} <= set(body["limitations"])
        assert body["collection_basis"] is None
        assert body["effective_recipient_ref"] == "aew:local-account"
        assert body["continuity"] == ("revalidate_required" if body["items"] else "unknown")
        if body["page"]:
            assert body["page"]["membership"] == "unknown"
        for item in body["items"]:
            assert item["disclosure"] == {"form": "full", "policy_ref": "o02:outage-historical-discovery",
                                          "scope_ref": scope, "effective_recipient_ref": "aew:local-account",
                                          "qualified_release": False}
            for stamp in [item["source"], *(f["source"] for f in item["field_sources"])]:
                assert stamp == wire.stamp(stamp["owner"], stamp["fact_ref"], scope, version, stamp["observed_at"],
                                           coverage_ref=scope, issuer_ref="aew:engine",
                                           observation_state=stamp["observation_state"])
                assert stamp["observation_state"] in ("historical", "stale", "unavailable")
                if stamp["observation_state"] == "historical":
                    assert stamp["observed_at"] == body["projection_as_of"]


@pytest.mark.parametrize("damage", ["control_missing", "control_checksum", "pin_mismatch", "pin_missing", "chain_gap"])
def test_integrity_damage_reports_the_exact_degraded_shape_without_repair(project, capsys, damage):
    engine, wid, _ = project
    state = engine.store.read_committed()
    unit_record = engine.aew_root / state["work"][wid]["record"]
    path = engine.store.control_path
    if damage == "control_missing":
        path.unlink()
    elif damage == "control_checksum":
        path.write_bytes(path.read_bytes().replace(b"project_id: ", b"project_id: changed-", 1))
    elif damage == "pin_mismatch":
        unit_record.write_text("uncommitted text marker", encoding="utf-8")
    elif damage == "pin_missing":
        unit_record.unlink()
    else:
        (engine.aew_root / outbox.record_path(state["revision"] - 1)).unlink()
    before = tree_inventory(engine.repo_root)
    routes = (("/v1/read/work", "/v1/read/work"),
              ("/v1/read/work/{work_kind}/{work_id}", f"/v1/read/work/ticket/{wire.b64url(wid)}"),
              ("/v1/read/continuation-state/{work_id}", f"/v1/read/continuation-state/{wire.b64url(wid)}"))
    for path, request in routes:
        code, body = command(engine, capsys, request)
        assert_schema(path, body)
        if damage.startswith("control"):
            if path.endswith("{work_id}") and "continuation" in path:
                assert code and body["code"] == "owner_unavailable"
            else:
                assert code == 0 and body["outcome"] == "unavailable" and not body["items"]
        else:
            assert code == 0 and body["outcome"] == "partial" and "partial_source" in body["limitations"]
            assert "uncommitted text marker" not in json.dumps(body)
            if damage.startswith("pin"):
                stamps = [field["source"] for field in body["items"][0]["field_sources"]]
                expected = "unavailable" if damage == "pin_missing" else "stale"
                assert any(s["owner"] == "WIS" and s["observation_state"] == expected for s in stamps)
    assert tree_inventory(engine.repo_root) == before


@pytest.mark.parametrize("damage", [False, True], ids=["intact", "damaged"])
def test_archived_work_reads_its_pins_or_falls_back_to_the_committed_summary(tmp_path, capsys, damage):
    p = sample_project(tmp_path)
    wid = create_investigation(p, tmp_path, title="Archived investigation")
    evidence = complete_investigation(p, wid)
    engine = Engine.discover(p.root)
    assert wid not in engine.store.read_committed()["work"]
    if damage:
        bundle = engine.aew_root / "work" / wid / "archive.yaml"
        bundle.write_text("uncommitted archive marker", encoding="utf-8")

    before = tree_inventory(engine.repo_root)
    route = f"/v1/read/work/ticket/{wire.b64url(wid)}"
    code, body = command(engine, capsys, route)
    assert code == 0
    assert_schema("/v1/read/work/{work_kind}/{work_id}", body)
    [item] = body["items"]
    assert item["ref"]["id"] == wid
    assert "Archived investigation [DONE]" in item["data"]["narrative"]["text"]
    if damage:
        assert body["outcome"] == "partial" and "partial_source" in body["limitations"]
        assert item["source"]["observation_state"] == "stale"
        assert "uncommitted archive marker" not in json.dumps(body)
    else:
        assert item["source"]["observation_state"] == "historical"
        code, packages = command(engine, capsys, route + "/packages")
        assert code == 0
        assert_schema("/v1/read/work/{work_kind}/{work_id}/packages", packages)
        [package] = packages["items"]
        assert package["ref"]["id"] == evidence and package["source"]["observation_state"] == "historical"
    assert tree_inventory(engine.repo_root) == before


def test_unknown_membership_and_empty_rendering_only_claim_committed_absence(project, capsys, monkeypatch):
    engine, _, _ = project
    monkeypatch.setattr(outage_host, "g3_present", lambda: False)
    monkeypatch.setattr("aew.stg02.outage_store.g3_present", lambda: False)
    _, body = command(engine, capsys, "/v1/read/work?kind=epic")
    _, human = command(engine, capsys, "/v1/read/work?kind=epic", human=True)
    assert body["items"] == [] and body["page"]["membership"] == "unknown"
    assert body["outcome"] == "partial" and "may still be writing" in human
    assert "None committed as of" in human and "none pending" not in human.lower()


def test_a_complete_empty_list_is_historical_with_unknown_membership(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv(hoststate.base_variable(), str(tmp_path / "host-data"))
    engine = Engine.initialize(make_git_repo(tmp_path / "repo"), project_id="outage")
    code, body = command(engine, capsys, "/v1/read/work")
    assert code == 0 and body["outcome"] == "historical"
    assert body["page"]["membership"] == "unknown" and not body["items"]


def test_the_installed_cli_exits_with_a_local_wire_result_and_problem(project):
    engine, _, _ = project
    route = "/v1/read/work"
    normal = run_aew("-C", str(engine.repo_root), "read", route)
    assert normal.returncode == 0 and not normal.stderr
    assert_schema(route, json.loads(normal.stdout))
    for env in ({"AEW_LEAD_BROKER": "unused", "AEW_LEAD_BROKER_KEY": "unused"}, {"AEW_AGENT_ENDPOINT": "unused"}):
        refused = run_aew("-C", str(engine.repo_root), "read", route, env=env)
        assert refused.returncode != 0 and not refused.stderr
        assert_schema(route, json.loads(refused.stdout))
        assert json.loads(refused.stdout)["title"] == REFUSAL


def test_live_run_observations_are_stale_and_a_stopped_heartbeat_is_a_possible_stall(project):
    engine, _, inv = project
    from aew.stg02.outage_store import OutageStore

    state = engine.store.read_committed()
    run = f"{inv}-run-1"
    directory = runlog.run_dir(engine.aew_root, run)
    directory.mkdir(parents=True)
    runlog.write_record(directory, {"status": "running"})
    heartbeat = directory / "heartbeat"
    heartbeat.touch()
    old = int(datetime.now(UTC).timestamp() - runlog.STALE_AFTER_S - 1)
    os.utime(heartbeat, (old, old))
    # The product's observation is derived from a run named in committed state. This isolates its field projection.
    state["invocations"][inv]["runs"] = [{"run": run, "launched_at": wire.utc(datetime.now(UTC))}]
    store = OutageStore(engine.aew_root, state, wire.utc(datetime.now(UTC)))
    item = store.runs(outage._request(f"/v1/read/runs/{wire.b64url(inv)}"))[0]
    assert item["data"]["phase"] == "UNKNOWN"
    assert item["data"]["phase_observation_class"] == "AGENT_REPORTED"
    assert item["data"]["stall_assessment"] == "POSSIBLE_STALL"
    assert "progress_suspected" in item["data"]["limitations"]
    phase = next(field["source"] for field in item["field_sources"] if field["field_path"] == "data.phase")
    assert phase["observation_state"] == "stale" and phase["observed_at"] == wire.utc(datetime.fromtimestamp(old, UTC))


def test_unread_local_and_per_host_sources_appear_only_as_coverage_limits(project, monkeypatch, capsys):
    from aew import g3client, g3standing

    engine, _, _ = project
    marker = "private fixture marker is never a read item"
    for path in (event_spool.spool_dir(engine.aew_root) / "events.jsonl",
                 notify.notify_dir(engine.aew_root) / notify.STATE,
                 engine.aew_root / "local/lead/tool-calls.jsonl",
                 runlog.run_dir(engine.aew_root, "test-run") / "transcript.jsonl",
                 g3client.approval_records_dir() / "approval.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marker, encoding="utf-8")
    monkeypatch.setattr(g3client, "REQUEST_SOCK", "/no/g3/socket")
    monkeypatch.setattr(g3standing, "CONFIRMER", "/no/g3/confirmer")
    for route, source in (("waiting", "per-host approval records"), ("attention", "notifier's summary")):
        _, body = command(engine, capsys, f"/v1/read/{route}")
        _, human = command(engine, capsys, f"/v1/read/{route}", human=True)
        assert body["outcome"] == "partial"
        assert {"partial_source", "source_unavailable"} <= set(body["limitations"])
        assert source in human and marker not in human and marker not in json.dumps(body)


def test_host_qualification_requires_the_exact_installed_reader_and_all_gate_evidence(project, capsys, monkeypatch):
    engine, _, _ = project
    from types import SimpleNamespace

    monkeypatch.setattr(outage_host, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(outage_host, "binding", lambda: {"reader_sha256": "fixture"})
    record = outage_host.record_template()
    now = datetime.now(UTC)
    record.update(profile="fixture", harness_version="fixture", provider_version="fixture",
                  applicability="fixture", evidence_issuer="fixture", containment_evidence="G3-12 fixture",
                  tested_at=wire.utc(now - timedelta(minutes=1)), valid_until=wire.utc(now + timedelta(minutes=1)),
                  invalidation_triggers=["fixture"], checks=dict.fromkeys(outage_host.GATE, "fixture evidence"))
    path = outage_host.record_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    _, body = command(engine, capsys, "/v1/read/work")
    assert "G4_unqualified" not in body["limitations"]
    record["checks"].pop("O02-Q08")
    path.write_text(json.dumps(record), encoding="utf-8")
    _, body = command(engine, capsys, "/v1/read/work")
    assert "G4_unqualified" in body["limitations"]
    monkeypatch.setattr(outage_host, "sys", SimpleNamespace(platform="win32"))
    assert not outage_host.qualified()
