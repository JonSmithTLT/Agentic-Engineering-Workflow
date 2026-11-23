"""F19 offline rehearsal at the implementer dispatch, adapter delivery and deferred scoring boundaries."""

from __future__ import annotations

import hashlib
import http.server
import json
import runpy
import shutil
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import fake_opencode as fake
import pytest
from conftest import Project, acquire_test_lead

from aew.engine.api import Engine
from aew.harness.contract import preamble
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.opencode.client import Client
from aew.harness.procs import ProcessTree
from aew.knowledge import context

EVAL = Path(__file__).resolve().parents[2] / "eval"
sys.path.insert(0, str(EVAL))
from aew_eval import arms, fixture, hidden, prereg, runner  # noqa: E402

EXPERIMENT = EVAL / "experiments/context-pack-rehearsal"
CASE = EXPERIMENT / "case.yaml"
COMMON = {"contract", "role-card", "requirement", "guardrails", "authority", "checks", "open-findings"}
LIMIT = 32_000


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dispatch(root, case):
    """Freeze one normal Lead assignment for every treatment; keep its source records and exact pack."""
    repo = root / "lead"
    fixture.build(fixture.snapshot(case), repo)
    project = Project(repo)
    project.ok("init", "--project-id", "report")
    acquire_test_lead(project, expect_rev=project.rev())
    wid = project.lead("work", "create", "ticket", "--title", case.manifest["task"], "--class", "1",
                       "--scope", "exporter.py", "--goal", "JSON reports include a status field.")["id"]
    plan = root / "plan.md"
    plan.write_text("Update exporter.py. Read docs/status-current.md, docs/legacy.md and docs/csv.md.\n",
                    encoding="utf-8")
    project.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", "exporter.py")
    project.lead("plan", "accept", wid, "--revision", "1")
    invocation = project.lead("work", "assign", wid)["invocation"]
    engine = Engine.discover(repo)
    state = engine.store.read()
    contract = engine.harness_contract(state, invocation, f"R-{invocation}-1")
    recorded = state["invocations"][invocation]["pack"]
    assert engine.context_pack(invocation)["matches_recorded"]
    assert digest(contract.pack_text) == recorded["sha256"] == contract.pack_sha256
    inputs, _ = engine._packs.pack_inputs(state, invocation)
    full = context.assemble(inputs)
    assert full.text == contract.pack_text and not full.truncations
    sections = [s for s in context.sections(inputs) if s.name in COMMON]
    # The launch header enumerates the sections actually included, so use the builder's own header for A and C.
    lines = context._launch_contract(inputs, COMMON)
    for section in sections:
        if section.name != "contract":
            lines.extend(context._whole(section))
    common = "\n".join([*lines, ""])
    reference = common + "\n" + (EXPERIMENT / "reference.md").read_text(encoding="utf-8")
    packs = {"A": common, "B": contract.pack_text, "C": reference}
    assert len(set(packs.values())) == 3 and all(len(pack) <= LIMIT for pack in packs.values())
    assert "docs/status-current.md" not in common
    assert all(pointer in contract.pack_text for pointer in ("docs/status-current.md", "docs/legacy.md", "docs/csv.md"))
    assert all(fact not in contract.pack_text for fact in ("`queued`", "`unknown`", "final CRLF"))
    assert all(fact in reference for fact in ("`queued`", "`unknown`", "`waiting`", "final record"))
    assert "accepted_plan" not in next(line for line in common.splitlines() if "Required knowledge (included" in line)
    (root / "current.md").write_bytes(contract.pack_text.encode())
    (root / "dispatch.json").write_text(json.dumps(recorded, indent=2), encoding="utf-8")
    return contract, packs


class DeliveryArm(arms.ScriptedArm):
    """Receive the normal adapter's first client POST inside each registered, fresh scripted cell."""

    def __init__(self, contract, packs, expected_files):
        self.contract = contract
        self.packs = packs
        self.expected_files = expected_files

    def run(self, repo, config, *, deadline_s, task=None):
        assert fixture.files_of(repo) == fixture.WorkTree(self.expected_files, {})
        assert task == "Add status to JSON reports"
        variant = config["variant"]
        pack = self.packs[variant]
        contract = replace(self.contract, pack_text=pack, pack_sha256=digest(pack))
        app = fake.local_app(repo.parent / "harness")
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), fake.handler_for(app)) as server:
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
            thread.start()
            try:
                client = Client(f"http://127.0.0.1:{server.server_port}", app.password)
                session_input = {"agent": "build", "location": {"directory": str(repo)}}
                session = client.post("/api/session", session_input)["data"]["id"]
                path = f"/api/session/{session}/message"
                assert client.get(path)["data"] == []
                adapter = OpenCodeAdapter(ProcessTree(), repo.parent, lambda event: None)
                adapter.client, adapter.session = client, session
                adapter.deliver_contract(contract)
                end = time.monotonic() + deadline_s
                while client.get("/api/session/active")["data"] and time.monotonic() < end:
                    time.sleep(0.01)
                assert not client.get("/api/session/active")["data"]
                messages = client.get(path)["data"]
            finally:
                server.shutdown()
                thread.join()
        received, = (m["text"] for m in messages if m["type"] == "user")
        assert received == preamble(self.contract) + "\n\n" + pack
        assert digest(received) == config["prompt_sha256"] and digest(pack) == config["pack_sha256"]
        (repo.parent / "received.md").write_bytes(received.encode())
        result = super().run(repo, config, deadline_s=deadline_s, task=task)
        result.harness.update({"session": adapter.session, "received_sha256": digest(received),
                               "pack_sha256": digest(pack), "received_bytes": len(received.encode()),
                               "pack_chars": len(pack)})
        return result


@pytest.fixture
def rehearsal(tmp_path, monkeypatch):
    # Git includes its clock in commit IDs. Pin only the synthetic fixture clock after the runner sanitizes git.
    git_env = fixture.git_env
    fixture_date = "2026-01-01T00:00:00Z"
    monkeypatch.setattr(fixture, "git_env", lambda: {**git_env(), "GIT_AUTHOR_DATE": fixture_date,
                                                     "GIT_COMMITTER_DATE": fixture_date})
    case = fixture.load(CASE)
    contract, packs = dispatch(tmp_path, case)
    plan = prereg.load(EXPERIMENT / "plan.yaml")
    plan["cases"] = [{"id": case.id, "family": case.manifest["family"], "sha256": fixture.case_sha256(case),
                      "hidden_sha256": case.manifest["hidden_sha256"], "control_of": None}]
    descriptions = {"A": "common ticket and role", "B": "current dispatch", "C": "common and reference sources"}
    plan["arms"] = [{"id": name.lower(), "kind": "scripted", "description": descriptions[name],
                     "config": {"variant": name, "steps": [], "pack_sha256": digest(pack),
                                "prompt_sha256": digest(preamble(contract) + "\n\n" + pack)}}
                    for name, pack in packs.items()]
    frozen = prereg.freeze(plan, by="offline rehearsal")
    prereg.dump(frozen, tmp_path / "frozen.yaml")
    monkeypatch.setitem(arms.ARMS, "scripted",
                        DeliveryArm(contract, packs, fixture.starting_files(fixture.snapshot(case), seeded=False)))
    records = []
    for cell in frozen["assignment"]["order"]:
        record = runner.run_cell(frozen, ledger_dir=tmp_path / "ledger", cell=cell["cell"], cases={case.id: CASE},
                                 work=tmp_path / "cells", run_name=cell["arm"], defer_scoring=True, deadline_s=30)
        assert record["validity"]["status"] == "valid", record["outcome"]
        assert not record["outcome"]["changed_paths"] and record["outcome"]["score"] is None
        assert record["profile"]["observed"] == []
        records.append(record)
    manifest = [{"run_id": r["run_id"], "preregistration_sha256": r["preregistration_sha256"], **r["arm"],
                 **r["harness"], "source_revision": r["outcome"]["base_commit"],
                 "export_sha256": r["outcome"]["scoring"]["export_sha256"]} for r in records]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return frozen, records


def test_registered_deliveries(rehearsal, tmp_path):
    frozen, records = rehearsal
    assert len({r["harness"]["session"] for r in records}) == 3
    dispatch_manifest = json.loads((tmp_path / "dispatch.json").read_text(encoding="utf-8"))
    snapshot = next(source for source in dispatch_manifest["sources"] if source["name"] == "snapshot")
    assert {r["outcome"]["base_commit"] for r in records} == {snapshot["base"]}
    assert len({r["harness"]["received_sha256"] for r in records}) == 3
    assert len({r["outcome"]["scoring"]["export_sha256"] for r in records}) == 1
    config = [arm["config"] for arm in frozen["arms"]]
    assert config[1]["pack_sha256"] == dispatch_manifest["sha256"]
    assert all(r["outcome"]["safety"]["checkout_untouched"] for r in records)
    assert all(record["preregistration_sha256"] == frozen["canonical_sha256"] for record in records)


def test_deferred_product_scores(rehearsal, tmp_path):
    frozen, records = rehearsal
    secret = tmp_path / "evaluator"
    shutil.copytree(EXPERIMENT / "evaluator/cases", secret / "cases")
    for record in records:
        entry = runner.score_run(frozen, ledger_dir=tmp_path / "ledger", run_id=record["run_id"], hidden_root=secret)
        score = entry["score"]
        assert score["failure"] is None and score["passed"] is False, score
        assert {row["name"]: row["ok"] for row in score["checks"]} == {
            "json-field": False, "current-spelling": False, "legacy-default": False, "csv-exact": True}
    assert len(runner.scores(tmp_path / "ledger")) == 3

def test_oracle_distinguishes_every_planted_fault(tmp_path, monkeypatch):
    """Requalify independent known answers through the ordinary hidden scorer on the public synthetic case."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    controls = runpy.run_path(str(EXPERIMENT / "evaluator/calibrate.py"))
    expected = json.loads((EXPERIMENT / "evaluator/qualification.json").read_text(encoding="utf-8"))
    secret = tmp_path / "evaluator"
    shutil.copytree(EXPERIMENT / "evaluator/cases", secret / "cases")
    oracle = hidden.Oracle.locate(secret, "REPORT-1")
    assert oracle.sha256 == expected["oracle_sha256"] == fixture.load(CASE).manifest["hidden_sha256"]
    for name, control in expected["controls"].items():
        tree = tmp_path / name
        tree.mkdir()
        arms.ScriptedArm().run(tree, {"steps": controls["steps"](name)}, deadline_s=30)
        assert hashlib.sha256((tree / "exporter.py").read_bytes()).hexdigest() == control["exporter_sha256"]
        score = hidden.score(oracle, tree)
        assert score["failure"] is None, score
        assert {row["name"]: row["ok"] for row in score["checks"]} == control["checks"]
        assert score["passed"] == (name == "good")
