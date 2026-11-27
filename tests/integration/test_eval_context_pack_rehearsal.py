"""F19 offline rehearsal at the implementer dispatch, adapter delivery and deferred scoring boundaries."""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import fake_opencode as fake
import pytest
from conftest import Project, acquire_test_lead
from fake_harness import POLICY
from host_env import GUARDED, clean_launching_env

from aew.engine.api import Engine
from aew.harness.contract import preamble
from aew.harness.opencode import projection
from aew.harness.opencode.adapter import OpenCodeAdapter
from aew.harness.procs import ProcessTree
from aew.knowledge import context
from aew.util import dump_yaml, load_yaml

EVAL = Path(__file__).resolve().parents[2] / "eval"
sys.path.insert(0, str(EVAL))
from aew_eval import arms, fixture, hidden, prereg, runner  # noqa: E402

pytestmark = GUARDED

EXPERIMENT = EVAL / "experiments/context-pack-rehearsal"
CASE = EXPERIMENT / "case.yaml"
COMMON = {"contract", "role-card", "requirement", "guardrails", "authority", "checks", "open-findings"}
LIMIT = 32_000


@pytest.fixture(autouse=True)
def synthetic_home(tmp_path_factory, monkeypatch):
    clean_launching_env(monkeypatch, tmp_path_factory.mktemp("home"))


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dispatch(root, case):
    """Freeze one normal Lead assignment for every treatment; keep its source records and exact pack."""
    repo = root / "lead"
    fixture.build(fixture.snapshot(case), repo)
    project = Project(repo)
    project.ok("init", "--project-id", "report")
    policy_file = repo / ".aew/policy/execution.yaml"
    policy = {**load_yaml(policy_file.read_text(encoding="utf-8")), **POLICY, "harness": "opencode"}
    policy_file.write_text(dump_yaml(policy), encoding="utf-8", newline="\n")
    project.pin_policy()
    acquire_test_lead(project)
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


@contextmanager
def assigned_workspace(repo, contract):
    """Each fresh F19 tree occupies the identical path named by dispatch for its turn."""
    assigned = Path(contract.workspace)
    original = assigned.with_name(assigned.name + "-dispatch")
    assigned.rename(original)
    try:
        repo.rename(assigned)
        try:
            yield assigned
        finally:
            assigned.rename(repo)
    finally:
        original.rename(assigned)


def install_fake(root, run, isolated):
    """Copy only public fake-server dependencies, so Linux can mask the checkout and its Git object stores."""
    runtime = root / "fake-runtime"
    helpers = runtime / "tests/helpers"
    helpers.mkdir(parents=True)
    for name in ("fake_opencode", "fake_agent", "childdiag", "flight_recorder", "bounds", "proctree"):
        shutil.copyfile(fake.HERE / f"{name}.py", helpers / f"{name}.py")
    for source in (fake.SPEC, EVAL.parent / "src/aew/harness/opencode/capabilities.py"):
        target = runtime / source.relative_to(EVAL.parent)
        target.parent.mkdir(parents=True)
        shutil.copyfile(source, target)
    launcher = runtime / ("fake-opencode" if isolated else "fake-opencode.py")
    script = fake.LAUNCHER.format(helpers=str(helpers), scripts=str(run / "script"))
    if isolated:
        # The checkout's venv is also masked. The staged fake uses only the base interpreter's standard library.
        script = f"#!{sys._base_executable}\n" + script
    launcher.write_text(script, encoding="utf-8", newline="\n")
    if isolated:
        launcher.chmod(0o700)
    return launcher


def launch_and_observe(contract, deadline_s, layout):
    """Run the normal adapter launch and read back the agent, permissions, model and message from the server."""
    run = Path(contract.run_dir)
    tree = ProcessTree(layout=layout, require_layout=layout is not None)
    adapter = OpenCodeAdapter(tree, run, lambda event: None)
    try:
        launch = adapter.launch(contract, hidden.program_env(Path(contract.scratch)))
        client, session = adapter.client, launch["session"]
        end = time.monotonic() + deadline_s
        while client.get("/api/session/active")["data"] and time.monotonic() < end:
            time.sleep(0.01)
        assert not client.get("/api/session/active")["data"]
        info, = client.get("/api/session")["data"]
        assert info["id"] == session and info["agent"] == projection.AGENT
        assert Path(info["location"]["directory"]).samefile(contract.workspace)
        messages = client.get(f"/api/session/{session}/message")["data"]
        received, = (m["text"] for m in messages if m["type"] == "user")
        config = json.loads((run / "harness/opencode-config.json").read_text(encoding="utf-8"))
        projected = config["agents"][projection.AGENT]
        served = next(agent for agent in client.get("/api/agent")["data"] if agent["id"] == info["agent"])
        assert served["system"] == projected["system"]
        assert info["permissions"] == projected["permissions"] == config["permissions"]
        assert info["model"] == projection.model_ref(contract.execution_profile)
        observed = {"session": session, "version": launch["version"], "agent": info["agent"],
                    "system_sha256": digest(served["system"]), "projection_sha256": launch["projection_sha256"],
                    "session_permissions_sha256": digest(json.dumps(info["permissions"], sort_keys=True)),
                    "skills_sha256": digest(json.dumps(launch["skills"], sort_keys=True))}
        assert launch["skills"] == projection.skills(contract)
        skills_folder = projection.skills_at(str(run / "harness"), os.sep).folder
        assert config.get("skills", []) == ([skills_folder] if launch["skills"]["exposed"] else [])
        return received, observed
    finally:
        try:
            adapter.terminate()
        finally:
            tree.kill()


class DeliveryArm(arms.ScriptedArm):
    """Receive the normal adapter's first client POST inside each registered, fresh scripted cell."""

    def __init__(self, contract, packs, expected_files, root):
        self.contract = contract
        self.packs = packs
        self.expected_files = expected_files
        self.root = root

    def run(self, repo, config, *, deadline_s, task=None):
        assert fixture.files_of(repo) == fixture.WorkTree(self.expected_files, {})
        assert task == "Add status to JSON reports"
        variant = config["variant"]
        pack = self.packs[variant]
        contract = replace(self.contract, pack_text=pack, pack_sha256=digest(pack))
        with assigned_workspace(repo, contract) as workspace:
            assert fixture.files_of(workspace) == fixture.WorkTree(self.expected_files, {})
            run = Path(contract.run_dir)
            Path(contract.scratch).mkdir(parents=True)
            script = run / "script"
            script.mkdir()
            target = workspace / "exporter.py"
            marked = self.expected_files["exporter.py"].decode() + config["receipt_suffix"]
            steps = [{"do": "write", "files": {str(target): marked}}]
            layout = None
            if config["isolated"]:
                protected = [*hidden.private_repository(EXPERIMENT / "evaluator"), self.root / "cells",
                             self.root / "ledger"]
                layout = hidden.scoring_layout(workspace, run, protected)
                runtime = str(self.root / "fake-runtime")
                # Hide the coordinator tree first. Bind back only this workspace, run and public fake runtime.
                layout = replace(layout, readonly=(*layout.readonly, runtime),
                                 hide_runs=(*layout.hide_runs, str(self.root)))
                prior = sorted((self.root / "cells").glob("*/received.md"))
                probes = [EXPERIMENT / "evaluator/cases/REPORT-1/oracle/checks.py",
                          self.root / "ledger/attempts.jsonl", self.root / "frozen.yaml",
                          self.root / "current.md", *prior]
                assert len(prior) >= 1 and all(path.is_file() for path in probes)
                steps.extend({"do": "read", "path": str(path)} for path in probes)
            (script / "default.json").write_text(json.dumps(steps), encoding="utf-8")
            received, observed = launch_and_observe(contract, deadline_s, layout)
            transcript = (run / "harness/transcript.jsonl").read_text(encoding="utf-8").splitlines()
            actions = [json.loads(line)["result"] for line in transcript]
            assert len(actions) == len(steps) and actions[0]["wrote"] == [str(target)]
            assert all(result["readable"] is False for result in actions[1:])
            assert observed["projection_sha256"] == config["projection_sha256"]
            assert target.read_bytes() == marked.encode()
            observed.update({"isolated_worker": layout is not None, "denied_reads": len(actions) - 1})
        # Archive the complete run, including scratch, before the next arm starts at the same logical paths.
        Path(contract.run_dir).rename(repo.parent / "run")
        assert received == preamble(self.contract) + "\n\n" + pack
        assert digest(received) == config["prompt_sha256"] and digest(pack) == config["pack_sha256"]
        (repo.parent / "received.md").write_bytes(received.encode())
        result = super().run(repo, config, deadline_s=deadline_s, task=task)
        result.harness.update({**observed, "received_sha256": digest(received),
                               "pack_sha256": digest(pack), "received_bytes": len(received.encode()),
                               "pack_chars": len(pack)})
        return result


@pytest.fixture
def rehearsal(tmp_path, monkeypatch, request):
    # Git includes its clock in commit IDs. Pin only the synthetic fixture clock after the runner sanitizes git.
    git_env = fixture.git_env
    fixture_date = "2026-01-01T00:00:00Z"
    monkeypatch.setattr(fixture, "git_env", lambda: {**git_env(), "GIT_AUTHOR_DATE": fixture_date,
                                                     "GIT_COMMITTER_DATE": fixture_date})
    isolated = getattr(request, "param", False)
    case = fixture.load(CASE)
    contract, packs = dispatch(tmp_path, case)
    launcher = install_fake(tmp_path, Path(contract.run_dir), isolated)
    monkeypatch.setenv("AEW_OPENCODE_BIN", str(launcher))
    prior = tmp_path / "cells/prior/received.md"
    prior.parent.mkdir(parents=True)
    prior.write_text("Synthetic prior-attempt receipt.\n", encoding="utf-8")
    plan = prereg.load(EXPERIMENT / "plan.yaml")
    if isolated:
        plan["experiment"] += "-isolated"
    projected = OpenCodeAdapter.projected_config(contract)
    projection_hash = digest(json.dumps(projected, sort_keys=True))
    plan["cases"] = [{"id": case.id, "family": case.manifest["family"], "sha256": fixture.case_sha256(case),
                      "hidden_sha256": case.manifest["hidden_sha256"], "control_of": None}]
    descriptions = {"A": "common ticket and role", "B": "current dispatch", "C": "common and reference sources"}
    plan["arms"] = [{"id": name.lower(), "kind": "scripted", "description": descriptions[name],
                     "config": {"variant": name, "steps": [], "pack_sha256": digest(pack), "isolated": isolated,
                                "projection_sha256": projection_hash, "receipt_suffix": "# F19 delivery receipt.\n",
                                "prompt_sha256": digest(preamble(contract) + "\n\n" + pack)}}
                    for name, pack in packs.items()]
    frozen = prereg.freeze(plan, by="offline rehearsal")
    prereg.dump(frozen, tmp_path / "frozen.yaml")
    starting = fixture.starting_files(fixture.snapshot(case), seeded=False)
    monkeypatch.setitem(arms.ARMS, "scripted", DeliveryArm(contract, packs, starting, tmp_path))
    records = []
    for cell in frozen["assignment"]["order"]:
        record = runner.run_cell(frozen, ledger_dir=tmp_path / "ledger", cell=cell["cell"], cases={case.id: CASE},
                                 work=tmp_path / "cells", run_name=cell["arm"], defer_scoring=True, deadline_s=30)
        assert record["validity"]["status"] == "valid", record["outcome"]
        assert record["outcome"]["changed_paths"] == ["exporter.py"] and record["outcome"]["score"] is None
        export = Path(record["outcome"]["scoring"]["export"]) / "exporter.py"
        assert export.read_bytes().endswith(b"# F19 delivery receipt.\n")
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
    for key in ("system_sha256", "projection_sha256", "session_permissions_sha256", "skills_sha256"):
        assert len({r["harness"][key] for r in records}) == 1
    assert len({r["outcome"]["scoring"]["export_sha256"] for r in records}) == 1
    config = [arm["config"] for arm in frozen["arms"]]
    assert config[1]["pack_sha256"] == dispatch_manifest["sha256"]
    assert all(r["outcome"]["safety"]["checkout_untouched"] for r in records)
    assert all(record["preregistration_sha256"] == frozen["canonical_sha256"] for record in records)


@pytest.mark.parametrize("rehearsal", [sys.platform.startswith("linux")], indirect=True)
def test_deferred_product_scores(rehearsal, tmp_path):
    frozen, records = rehearsal
    secret = tmp_path / "evaluator"
    shutil.copytree(EXPERIMENT / "evaluator/cases", secret / "cases")
    if sys.platform.startswith("linux"):
        assert [r["harness"]["denied_reads"] for r in records] == [5, 6, 7]
    for record in records:
        entry = runner.score_run(frozen, ledger_dir=tmp_path / "ledger", run_id=record["run_id"], hidden_root=secret)
        score = entry["score"]
        assert score["contained"] == sys.platform.startswith("linux")
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
        assert score["contained"] == sys.platform.startswith("linux")
        assert score["failure"] is None, score
        assert {row["name"]: row["ok"] for row in score["checks"]} == control["checks"]
        assert score["passed"] == (name == "good")
