"""Bounded recovery: one automatic relaunch of a stage's failed launch (M4-E E8b; plan v3 E8, N2c; BRP R5-3 and §9;
A2 §8; A3 §5; amendment 1, R2-m2 and R3-n1).

Every launch here is real: the fake harness's configured execution policy, a real supervisor and a real failed start
(no fake script for the run, so nothing is ever spawned). No real failure maps to an allow-listed code yet, so where a
case needs one the seed goes where the code really comes from: the supervisor's acknowledgement, rewritten on the
launcher's side of the pipe in this process (``harness_ops._read_acks``). Nothing is seeded in the run directory, except
where a test proves that a code found there is never read."""

from __future__ import annotations

import ast
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from aewflow import create_planned_ticket, sample_project
from fake_harness import POLICY, HarnessLab, contains_credential
from invariants import assert_control_invariants, load_control
from test_stage_runner import call

from aew import errors
from aew.engine import harness_ops, recovery
from aew.engine import stage_intents as SI
from aew.engine.api import Engine
from aew.engine.store import Transition
from aew.harness import contract as K
from aew.harness import runlog
from aew.harness.procs import ProcessTree
from aew.knowledge.records import format_id
from aew.util import dump_yaml, load_yaml

SRC = Path(__file__).resolve().parents[2] / "src" / "aew"
HANG = [{"do": "hang"}]
NEVER = (K.CREDENTIAL_DENIED, K.CONFIG_ERROR, K.QUOTA_EXHAUSTED, K.CONTAINMENT_REFUSED, K.AUTH_FAILED,
         K.PROVIDER_OUTAGE, K.INCOMPATIBLE_CONFIG)


class Ticket:
    """A READY Ticket in a project launching the fake harness, with its implementer invocation's id known before the
    stage creates it (so a run's script, or its seed, can be named in advance). ``concurrency``: the project's mutating
    cap, for a test that starts several Tickets."""

    def __init__(self, tmp_path: Path, monkeypatch, *, recovery_policy: dict[str, Any] | None,
                 project: Any = None, lab: HarnessLab | None = None, concurrency: int | None = None) -> None:
        if project is None:
            project = sample_project(tmp_path)
            if concurrency is not None:  # fixture setup: the lab pins the policy as the project's starting one
                gates = project.root / ".aew" / "policy" / "gates.yaml"
                current = load_yaml(gates.read_text(encoding="utf-8"))
                current["mutating_concurrency"] = concurrency
                gates.write_text(dump_yaml(current), encoding="utf-8", newline="\n")
            policy = {**POLICY, **({"recovery": recovery_policy} if recovery_policy is not None else {})}
            lab = HarnessLab.create(project, tmp_path, policy=policy)
            for k, v in lab.env.items():
                monkeypatch.setenv(k, v)
        assert lab is not None
        self.p, self.lab = project, lab
        self.wid = create_planned_ticket(project, tmp_path, title=f"Add subtract() {id(self)}")
        self.inv = format_id("INV", int(load_control(project.root)["counters"]["invocation"]) + 1)

    def run(self, n: int) -> str:
        return K.run_id(self.inv, n)

    def start(self) -> dict[str, Any]:
        return call(self.p, "ticket_start", work_id=self.wid)

    def control(self) -> dict[str, Any]:
        return load_control(self.p.root)

    def invocation(self) -> dict[str, Any]:
        return self.control()["invocations"][self.inv]


@pytest.fixture
def make(tmp_path, monkeypatch):
    made: list[Ticket] = []

    def build(recovery_policy: dict[str, Any] | None = None, *, also: Ticket | None = None,
              concurrency: int | None = None) -> Ticket:
        if also is not None:  # another Ticket in the same project
            t = Ticket(tmp_path, monkeypatch, recovery_policy=None, project=also.p, lab=also.lab)
        else:
            t = Ticket(tmp_path, monkeypatch, recovery_policy=recovery_policy, concurrency=concurrency)
        made.append(t)
        return t

    yield build
    for t in made:
        t.lab.cleanup()


ON = {"relaunch_launch_failed": 1}


def acknowledge(monkeypatch, edits: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]],
                after: Callable[[str], None] | None = None) -> None:
    """Rewrite what a run's supervisor acknowledged about its failed start, as the launcher reads it (the seed's one
    place): ``edits[run]`` maps the real ``started`` acknowledgement to the seeded one (None drops it). ``after(run)``
    runs once the acknowledgements are read, before the launcher acts on them."""
    real = harness_ops._read_acks

    def read(proc, wait_s):
        acks = real(proc, wait_s)
        run = next((a.get("run") for a in acks if "custody" in a), None)
        out = []
        for ack in acks:
            if "started" in ack and run in edits:
                assert ack["started"] is False, ack  # a real failed start
                ack = edits[run](dict(ack))
                if ack is None:
                    continue
            out.append(ack)
        if after is not None and run is not None:
            after(run)
        return out

    monkeypatch.setattr(harness_ops, "_read_acks", read)


def acknowledged(code: str, **observed: Any) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def edit(ack: dict[str, Any]) -> dict[str, Any]:
        ack["reason_code"] = code
        ack["observations"] = {**ack["observations"], **observed}
        return ack
    return edit


def recovery_of(out: dict[str, Any]) -> dict[str, Any]:
    assert not out["ok"] and out["stopped"]["boundary"] == "launch_failed", out.get("stopped")
    return out["stopped"]["error"]["details"]["recovery"]


def relaunched(t: Ticket, out: dict[str, Any]) -> dict[str, Any]:
    """The stage went on over the relaunched run: completed, the Ticket RUNNING, both runs in history, and the record
    binding what A2 §7 names."""
    assert out["ok"], out.get("stopped")
    si = Engine.discover(t.p.root).stage_intent(out["stage_intent_id"])
    assert si["status"] == SI.COMPLETED and t.control()["work"][t.wid]["state"] == "RUNNING"
    inv = t.invocation()
    assert [(r["run"], r["kind"]) for r in inv["runs"]] == [(t.run(1), "dispatch"), (t.run(2), "relaunch")]
    record = inv["relaunch"]
    assert (record["failed_run"], record["new_run"], record["intent"]) == (t.run(1), t.run(2), si["id"])
    assert record["termination_proof"]["observed"] and all(v is True for v in
                                                           record["termination_proof"]["observed"].values())
    assert record["no_side_effect_proof"]["network"] == {"prompt_delivered": False}
    assert record["revocation"]["confirmed"].startswith("credential revoked")
    assert record["policy"]["relaunch_launch_failed"] == 1 and record["breaker"]["open"] is None
    return record


# ---------------------------------------------------------------------------------------------- BRP §9


def test_relaunch_off_by_default(make, monkeypatch):
    """BRP §9: with no `recovery` block (policy 0), an allow-listed, fully proven failure still stops the stage at
    launch_failed for the Lead, as before E8b."""
    t = make()
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    found = recovery_of(t.start())
    assert found["relaunched"] is False and found["reasons"] == [recovery.RELAUNCH_OFF]
    assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)] and "relaunch" not in t.invocation()
    assert t.control()["work"][t.wid]["state"] == "ASSIGNED"
    assert_control_invariants(t.p)


@pytest.mark.parametrize("change", ["legality", "base"])
def test_changed_binding_is_ineligible(make, monkeypatch, tmp_path, change):
    """BRP §9: a dispatch or base binding that changed between the failure and the relaunch's commit makes the run
    ineligible; the change lands while the recovery is pending (a pause the test releases)."""
    t = make(ON)
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    out = paused_for(monkeypatch, tmp_path, t, lambda: change_binding(t, change))
    found = recovery_of(out)
    assert recovery.BINDING_CHANGED in found["reasons"] and found["relaunched"] is False, found
    assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)]
    assert_control_invariants(t.p)


def change_binding(t: Ticket, change: str) -> None:
    if change == "legality":  # a legality-affecting policy edit (one more protected path), adopted by the operator
        path = t.p.root / ".aew" / "policy" / "guardrails.yaml"
        before = Engine.discover(t.p.root).policy_digests()["legality_digest"]
        guardrails = load_yaml(path.read_text(encoding="utf-8"))
        guardrails["protected_paths"] = [*guardrails["protected_paths"], "docs/e8b/**"]
        path.write_text(dump_yaml(guardrails), encoding="utf-8", newline="\n")
        t.p.adopt_policy()
        assert Engine.discover(t.p.root).policy_digests()["legality_digest"] != before
        return
    engine = Engine.discover(t.p.root)  # the invocation's base binding moved (only a defect could do this)
    with engine.store.session() as s:
        s.state["invocations"][t.inv]["snapshot"]["relevant_inputs_fingerprint"] = "0" * 64
        s.commit(Transition(op="test.seed", actor={"kind": "test"}, summary="a moved base binding"))


def paused_for(monkeypatch, tmp_path: Path, t: Ticket, during: Callable[[], None]) -> dict[str, Any]:
    """Start the stage, hold its recovery between the decision and the relaunch's commit, run ``during``, release it.
    Ordered by the pause file (the runner says it reached the point), never by time."""
    pause = tmp_path / "recovery.pause"
    pause.touch()
    monkeypatch.setenv("AEW_PAUSE", f"recovery.before_relaunch_commit={pause}")
    result: list[Any] = []
    runner = threading.Thread(target=lambda: result.append(t.start()), name="stage-under-test", daemon=True)
    runner.start()
    try:
        t.lab.until(lambda: Path(f"{pause}.reached").exists(), 120, "the recovery to be pending")
        during()
    finally:
        pause.unlink()
    runner.join(240)
    assert not runner.is_alive() and result, "the stage never returned"
    return result[0]


def test_second_failure_raises_attention_only(make, monkeypatch):
    """BRP §9: the relaunched run fails too; the stage stops at launch_failed with attention, and nothing more is
    relaunched: the invocation has had its one relaunch."""
    t = make(ON)
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE), t.run(2): acknowledged(K.SPAWN_RACE)})
    out = t.start()
    found = recovery_of(out)
    assert found["second_failure"] is True and found["failed_run"] == t.run(1)
    assert out["stopped"]["error"]["details"]["run"] == t.run(2)
    inv = t.invocation()
    assert [r["run"] for r in inv["runs"]] == [t.run(1), t.run(2)] and inv["relaunch"]["new_run"] == t.run(2)
    assert t.control()["work"][t.wid]["state"] == "ASSIGNED"
    assert_control_invariants(t.p)


# ---------------------------------------------------------------------------------------------- A2 §8


def _workspace_mutated(t: Ticket) -> Callable[[str], None]:
    def touch(run: str) -> None:
        if run == t.run(1):
            ws = Path(t.invocation()["workspace"])
            (ws / "calc" / "e8b_touched.py").write_text("X = 1\n", encoding="utf-8")
    return touch


A2: dict[str, tuple[Callable[[Ticket], dict[str, Any]], Callable[[Ticket], Callable[[str], None]] | None, str]] = {
    # A still-live old process: the supervisor's tree is not empty and a process it started is still running.
    "live_old_process_ineligible": (lambda t: {t.run(1): acknowledged(K.SPAWN_RACE, tree_empty=False,
                                                                      pids_gone=False)}, None,
                                    recovery.TERMINATION_UNPROVEN),
    # A stale heartbeat alone: no failed-start acknowledgement, only the run directory's record and its stopped beat.
    "stale_heartbeat_alone_ineligible": (lambda t: {t.run(1): lambda ack: None}, None, recovery.TERMINATION_UNPROVEN),
    "project_tool_event_ineligible": (lambda t: {t.run(1): acknowledged(K.SPAWN_RACE, bridge_requests=1)}, None,
                                      recovery.SIDE_EFFECT_POSSIBLE),
    "prompt_maybe_delivered_ineligible": (lambda t: {t.run(1): acknowledged(K.SPAWN_RACE, prompt_delivered=None)},
                                          None, recovery.SIDE_EFFECT_POSSIBLE),
    "workspace_mutation_ineligible": (lambda t: {t.run(1): acknowledged(K.SPAWN_RACE)}, _workspace_mutated,
                                      recovery.SIDE_EFFECT_POSSIBLE),
    # n8's "never relaunch": the real failure here maps to nothing, so it is `unknown`.
    "unknown_reason_ineligible": (lambda t: {}, None, recovery.REASON_NOT_ALLOWED),
    **{f"{code}_never": ((lambda c: lambda t: {t.run(1): acknowledged(c)})(code), None, recovery.REASON_NOT_ALLOWED)
       for code in NEVER},
}


def _a2_new_run_id_and_credential(make, monkeypatch):
    """A2 §8 (and BRP §9's seeded relaunch): an eligible failure relaunches exactly once, under a new run id and a new
    credential; the failed run stays in history, its credential revoked, and the stage goes on over the new run."""
    t = make(ON)
    t.lab.script(t.run(2), HANG)
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    out = t.start()
    record = relaunched(t, out)
    inv, state = t.invocation(), t.control()
    first, second = inv["runs"]
    assert first["token_id"] != second["token_id"] == inv["token_id"]
    assert state["tokens"][first["token_id"]]["revoked_at"] and not state["tokens"][second["token_id"]]["revoked_at"]
    assert record["revocation"]["token_id"] == first["token_id"] and record["reason_code"] == K.SPAWN_RACE
    assert record["reason_code_source"] == "acknowledgement"
    assert second["dispatch"]["entrypoint"] == "harness.launch"
    assert runlog.observed_status(runlog.run_dir(t.p.root / ".aew", t.run(2)))[0] in ("starting", "running")
    assert not contains_credential(str(out)) and not contains_credential(str(inv))
    assert_control_invariants(t.p)


def _a2_revoke_before_mint(make, monkeypatch):
    """A2 §3: the failed run's credential is revoked, and the revocation confirmed, before the new one is minted."""
    t = make(ON)
    t.lab.script(t.run(2), HANG)
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    order: list[str] = []
    real_revoke, real_issue = recovery.revoke, recovery.issue_token

    def revoke(state, token_id, reason):
        order.append("revoke")
        return real_revoke(state, token_id, reason)

    def issue(state, kind, scope):
        assert all(tok["revoked_at"] for tid, tok in state["tokens"].items()
                   if tid == state["invocations"][t.inv]["token_id"]), "minted while the old credential was live"
        order.append("mint")
        return real_issue(state, kind, scope)

    monkeypatch.setattr(recovery, "revoke", revoke)
    monkeypatch.setattr(recovery, "issue_token", issue)
    relaunched(t, t.start())
    assert order == ["revoke", "mint"]


def _a2_breaker(make, monkeypatch):
    """A2 §6: eligible failures are counted per scope; the one that reaches the threshold opens the breaker, is not
    relaunched, and every later one in that scope stops for the Lead until the operator resets the breaker."""
    seeds: dict[str, Callable[[dict[str, Any]], dict[str, Any] | None]] = {}
    acknowledge(monkeypatch, seeds)

    def ticket(also: Ticket | None = None) -> Ticket:  # each made just before its start: its invocation id is next
        t = (make({**ON, "breaker": {"threshold": 2, "window_s": 300}}, concurrency=3) if also is None
             else make(also=also))
        t.lab.script(t.run(2), HANG)
        seeds[t.run(1)] = acknowledged(K.SPAWN_RACE)
        return t

    first = ticket()
    relaunched(first, first.start())
    second = ticket(first)
    found = recovery_of(second.start())
    assert found["reasons"] == [recovery.BREAKER_TRIPPED] and found["scope"] == recovery.PROJECT_SCOPE
    breaker = first.control()["recovery"]["breakers"][recovery.PROJECT_SCOPE]
    assert breaker["open"]["runs"] == [first.run(1), second.run(1)]
    assert "relaunch" not in second.invocation()
    third = ticket(first)
    assert recovery_of(third.start())["reasons"] == [recovery.BREAKER_OPEN]
    assert Engine.discover(first.p.root).recovery_breaker_status()["open"] == [recovery.PROJECT_SCOPE]
    assert_control_invariants(first.p)


CUSTOM: dict[str, Callable[[Any, Any], None]] = {
    "new_run_id_and_credential": _a2_new_run_id_and_credential,
    "revoke_before_mint": _a2_revoke_before_mint,
    "breaker": _a2_breaker,
}


@pytest.mark.parametrize("case", [*A2, *CUSTOM])
def test_a2(make, monkeypatch, case):
    """A2 §8: each condition that must keep a failed launch from relaunching does, with every other proof holding,
    and the stage stops at launch_failed for the Lead with the verdict on its error. The last three cases are the
    positive ones: a new run id and credential, revocation before minting, and the breaker."""
    if case in CUSTOM:
        return CUSTOM[case](make, monkeypatch)
    t = make(ON)
    seeds, after, why = A2[case]
    acknowledge(monkeypatch, seeds(t), after=after(t) if after else None)
    found = recovery_of(t.start())
    assert found["relaunched"] is False and why in found["reasons"], found
    assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)] and "relaunch" not in t.invocation()
    if case == "unknown_reason_ineligible":
        assert found["reason_code"] == K.UNKNOWN_LAUNCH_FAILURE
    assert_control_invariants(t.p)


# ---------------------------------------------------------------------------------------------- N2c, A3 §5, R2-m2


def test_relaunch_only_at_the_stage_launch_failed_stop(make, monkeypatch):
    """N2c: the relaunch is the stage runner's, at a stage's launch_failed stop. Statically, only the stage executor
    asks for one. A launch outside a stage (`aew harness launch`, the route the recovery `cli` escape takes) with
    relaunch on and an eligible, fully proven failure raises the failure to its caller and relaunches nothing."""
    callers = []
    for path in sorted(SRC.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in ("recovery_relaunch", "_recovery"):
                callers.append(f"{path.relative_to(SRC).as_posix()}:{node.attr}")
    assert sorted(set(callers)) == ["engine/api.py:_recovery", "surface/stage.py:recovery_relaunch"], callers
    t = make(ON)
    t.p.lead("work", "assign", t.wid)  # dispatched without a launch: `harness launch` records run 1
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    with pytest.raises(errors.HarnessLaunchFailed) as failed:
        Engine.discover(t.p.root).harness_launch(token=t.p.token, expect_rev=t.p.rev(), invocation=t.inv)
    assert failed.value.details["reason_code"] == K.SPAWN_RACE and "recovery" not in failed.value.details
    assert failed.value.details["observations"]["supervisor_exited"] is True
    assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)] and "relaunch" not in t.invocation()


@pytest.mark.parametrize("change", ["switched_off", "breaker_bounds_changed"])
def test_relaunch_setting_change_reevaluates_pending_recovery_only(make, monkeypatch, tmp_path, change):
    """A3 §5: the recovery setting is snapshotted at the decision; an adopted change before the relaunch commits
    re-evaluates that pending recovery under the new setting, and stales nothing: no STALE_POLICY, and the stage's own
    binding is untouched (the recovery fields are operational)."""
    t = make(ON)
    t.lab.script(t.run(2), HANG)
    acknowledge(monkeypatch, {t.run(1): acknowledged(K.SPAWN_RACE)})
    before = Engine.discover(t.p.root).policy_digests()

    def edit() -> None:
        path = t.p.root / ".aew" / "policy" / "execution.yaml"
        text = path.read_text(encoding="utf-8")
        new = ("relaunch_launch_failed: 0" if change == "switched_off"
               else "relaunch_launch_failed: 1\n  breaker:\n    threshold: 5")
        path.write_text(text.replace("relaunch_launch_failed: 1", new), encoding="utf-8")
        t.p.adopt_policy()

    out = paused_for(monkeypatch, tmp_path, t, edit)
    after = Engine.discover(t.p.root).policy_digests()
    assert after["legality_digest"] == before["legality_digest"] != None  # noqa: E711
    assert after["operational_digest"] != before["operational_digest"]
    si = Engine.discover(t.p.root).stage_intent(out["stage_intent_id"])
    assert si["binding"]["legality_digest"] == before["legality_digest"]
    if change == "switched_off":
        found = recovery_of(out)
        assert found["reasons"] == [recovery.RELAUNCH_OFF] and found["reevaluated"] is True
        assert out["stopped"]["error"]["code"] == "HARNESS_LAUNCH_FAILED"  # never STALE_POLICY
        assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)]
    else:
        record = relaunched(t, out)
        assert record["policy"]["breaker"]["threshold"] == 5
    assert_control_invariants(t.p)


def test_relaunch_eligibility_never_reads_the_run_directory_code(make, monkeypatch):
    """R2-m2 and R3-n1: the run directory is model-writable. With no failed-start acknowledgement the launcher reads
    the run's record, and even a record that says `spawn_race` (written there after the supervisor's own) is
    `unknown` to eligibility, which has no observations either: the run is never relaunched."""
    t = make(ON)

    def forge(run: str) -> None:
        directory = runlog.run_dir(t.p.root / ".aew", run)
        record = runlog.read_record(directory) or {}
        runlog.write_record(directory, {**record, "reason_code": K.SPAWN_RACE})

    acknowledge(monkeypatch, {t.run(1): lambda ack: None}, after=forge)
    out = t.start()
    found = recovery_of(out)
    details = out["stopped"]["error"]["details"]
    assert details["reason_code"] == K.UNKNOWN_LAUNCH_FAILURE and details["reason_code_source"] == "run_record"
    assert runlog.read_record(runlog.run_dir(t.p.root / ".aew", t.run(1)))["reason_code"] == K.SPAWN_RACE
    assert found["reason_code"] == K.UNKNOWN_LAUNCH_FAILURE and recovery.REASON_NOT_ALLOWED in found["reasons"]
    failure = recovery.failure_of({"run": t.run(1), "invocation": t.inv, "reason_code": K.SPAWN_RACE,
                                   "reason_code_source": "run_record", "observations": {"platform": "linux"}},
                                  intent=None)
    assert failure["reason_code"] == K.UNKNOWN_LAUNCH_FAILURE and failure["observations"] is None
    assert [r["run"] for r in t.invocation()["runs"]] == [t.run(1)]


def test_the_typed_run_shows_its_reason_code_for_display_only(make, monkeypatch):
    """The typed `run` object carries the run record's `reason_code` (display only; M4-E E8b)."""
    t = make()
    recovery_of(t.start())
    from aew.surface import projection

    runs = projection._runs(Engine.discover(t.p.root), t.wid)
    assert [(r["run"], r["reason_code"]) for r in runs] == [(t.run(1), K.UNKNOWN_LAUNCH_FAILURE)]


# ---------------------------------------------------------------------------------------------- the proofs' sources


def test_a_failed_start_acknowledges_this_platforms_termination_proof(make, monkeypatch):
    """A2 §2 on this platform, from a real supervisor (nothing seeded): every observation the platform's rule names
    is on the failed-start acknowledgement and is true, and the launcher adds that the supervisor exited."""
    t = make()
    seen: list[dict[str, Any]] = []
    acknowledge(monkeypatch, {t.run(1): lambda ack: seen.append(dict(ack)) or ack})
    t.start()
    [ack] = seen
    proof, gaps = recovery.termination_proof({**ack["observations"], "supervisor_exited": True})
    assert not gaps, (proof, gaps)
    assert ack["observations"]["prompt_delivered"] is False and ack["observations"]["bridge_requests"] == 0
    assert ack["observations"]["spawned"] == 0


def test_a_live_process_fails_the_tree_termination_observation():
    """A2 §2: a process still running in the run's tree is observed as such, on this platform's own mechanism (the
    job object, or the process group and sentinel), and is gone once the tree is killed."""
    import subprocess
    import sys

    tree = ProcessTree()
    proc = tree.spawn([sys.executable, "-c", "import time; time.sleep(600)"], stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        live = tree.termination(wait_s=0)
        assert live["tree_empty"] is False and live["pids_gone"] is False
        tree.kill()
        proc.wait(30)
        ended = tree.termination(wait_s=30)
        assert ended["tree_empty"] is True and ended["pids_gone"] is True
        if sys.platform != "win32":
            assert ended["sentinel_released"] is True
    finally:
        tree.kill()
