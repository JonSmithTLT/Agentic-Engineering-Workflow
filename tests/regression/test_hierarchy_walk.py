"""Seeded adversarial walk over the M2 hierarchy and the non-mutating path (ADR-0007, ADR-0008).

It mixes Epics/Stories with mutating and non-mutating Tickets and interleaves the operations whose
compositions M2 must survive: dispatch/redispatch attempts, record submission and ingestion, stale
inputs and acknowledgements (integrations change what investigations observed), ancestor plan
changes and reconfirmation, moves, promotions, dependency edits, parent review/verification,
closeout and cascading cancellation, Lead handoff and operator takeover, crash-injected commits,
and adversarial ones: late submissions with any credential ever issued, replayed ingestion of any
earlier record, and a read-only executor mutating its observation.

As in the M1 walk (``test_composition_walk.py``, untouched), rejections (``AEWError``) are expected,
any other exception is a bug, injected crashes are followed by a fresh engine, and the cross-operation
invariant oracle (M1 rules plus the M2 rules) must hold after every step. Knobs: ``AEW_HWALK_SEEDS``,
``AEW_HWALK_STEPS``, ``AEW_HWALK_FAULT_RATE``.
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import pytest

from aew import operator
from aew.engine import hierarchy as H
from aew.engine import transitions
from aew.engine.api import Engine
from aew.engine.faults import InjectedFault
from aew.errors import AEWError
from aew.util import dump_yaml
from aewflow import DISCOVERY, PROPOSAL, RESEARCH, SUBTRACT_PATCH, sample_project
from invariants import control_violations

SEEDS = [int(s) for s in os.environ.get("AEW_HWALK_SEEDS", "7,19,31,43,59").split(",")]
STEPS = int(os.environ.get("AEW_HWALK_STEPS", "80"))
FAULT_RATE = float(os.environ.get("AEW_HWALK_FAULT_RATE", "0.06"))

FAST_CHECKS = {
    "schema": "aew/checks/v1",
    "checks": {"unit": {"configured": True, "command": ["{python}", "-c", "import calc.core"], "cwd": ".",
                        "timeout_s": 120, "description": "import smoke (fast walk check)"}},
    "baseline_failures": [],
}
TXN_FAULTS = ["txn.after_stage", "txn.after_replace", "txn.mid_apply", "txn.after_log"]
PUBLISH_FAULTS = ["integrate.after_publishing_record", "integrate.after_cas", "integrate.before_done", *TXN_FAULTS]
RECORD_META = {"discovery_record": DISCOVERY, "research_record": RESEARCH, "plan_proposal": PROPOSAL}
MAX_TICKETS = 9


class HierarchyWalk:
    def __init__(self, tmp_path: Path, seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
        self.p = sample_project(tmp_path, checks=FAST_CHECKS)
        self.root = self.p.root
        self.rng = random.Random(seed)
        self.mp = monkeypatch
        self.token, self.gen = self.p.token, 1
        self.engine = Engine.discover(self.root)
        self.held: dict[str, str] = {}  # invocation id -> credential the walk holds (executors, implementers)
        self.issued: list[tuple[str, str, str, str | None]] = []  # (work id, credential, role, kind) ever issued
        self.records: list[tuple[str, str]] = []  # (work id, record id) ever submitted by an executor
        self.variant = 0
        self.log: list[str] = []
        self.accepted = 0
        self.units: list[str] = []
        epic = self.create("epic", "walk epic")
        self.plan(epic)
        for n in (1, 2):
            story = self.create("story", f"walk story {n}", parent=epic, cls=self.rng.choice([0, 1]))
            self.plan(story)
            self.new_ticket(story, mutating=False)
        self.new_ticket(self.units[1], mutating=True)

    # ------------------------------------------------------------------ plumbing

    def state(self) -> dict[str, Any]:
        """Committed control state, re-read only when control.yaml changed (every commit atomically replaces
        it). The walk consults state dozens of times per step; the engine itself always reads fresh."""
        st = os.stat(self.engine.store.control_path)
        key = (st.st_mtime_ns, st.st_size, st.st_ino)
        if getattr(self, "_state_key", None) != key:
            self._state, self._state_key = self.engine.store.read(), key
        return self._state

    def unit(self, wid: str) -> dict[str, Any]:
        return self.state()["work"][wid]

    def lead(self, method: str, **kw: Any) -> Any:
        return getattr(self.engine, method)(token=self.token, expect_rev=self.state()["revision"], **kw)

    def submit(self, tok: str, kind: str, meta: dict[str, Any]) -> str:
        return self.engine.submit(invocation_token=tok, kind=kind, text=f"---\n{dump_yaml(meta)}---\nwalk\n")["evidence"]

    def create(self, kind: str, title: str, *, parent: str | None = None, cls: int = 1, **kw: Any) -> str:
        wid = self.lead("work_create", kind=kind, title=title, risk_class=cls, parent=parent, **kw)["id"]
        self.units.append(wid)
        return wid

    def plan(self, wid: str, reason: str | None = None) -> None:
        self.variant += 1
        rev = self.lead("plan_propose", work_id=wid, body=f"Walk plan {self.variant}.\n", reason=reason)["revision_number"]
        self.lead("plan_accept", work_id=wid, revision=rev)

    def new_ticket(self, parent: str | None, *, mutating: bool) -> str:
        kw: dict[str, Any] = {"mutating": mutating, "scope_paths": ["calc/**", "tests/**"],
                              "goal_backwards": ["calc.core imports"], "contract": ["changes stay in calc/, tests/"]}
        if not mutating:
            kw["card"] = self.rng.choice([None, None, "researcher", "planner"])
        done_nm = [w for w in self.tickets() if self.nm(w) and self.unit(w)["state"] == "DONE"]
        if done_nm and self.rng.random() < 0.5:
            kw["depends_on"] = [f"{self.rng.choice(done_nm)}:evidence"]  # consume an accepted record
        wid = self.create("ticket", f"walk ticket {len(self.tickets()) + 1}", parent=parent, cls=1, **kw)
        self.plan(wid)
        return wid

    def tickets(self) -> list[str]:
        return [w for w in self.units if self.unit(w)["kind"] == "ticket"]

    def parents(self) -> list[str]:
        return [w for w in self.units if self.unit(w)["kind"] != "ticket"]

    def nm(self, wid: str) -> bool:
        u = self.unit(wid)
        return u["kind"] == "ticket" and not u.get("mutating")

    def live(self, wid: str) -> bool:
        return self.unit(wid)["state"] not in H.TERMINAL

    def hold(self, wid: str, out: dict[str, Any], role: str, kind: str | None = None) -> str:
        self.held[out["invocation"]] = out["invocation_token"]
        self.issued.append((wid, out["invocation_token"], role, kind))
        return out["invocation_token"]

    def executor(self, wid: str) -> tuple[str | None, bool, bool]:
        """(current executor invocation, active, held by the walk) for a non-mutating Ticket."""
        state = self.state()
        inv_id = (state["work"][wid].get("execution") or {}).get("invocation")
        active = state["invocations"].get(inv_id or "", {}).get("status") == "active"
        return inv_id, active, inv_id in self.held

    def implementer(self, wid: str) -> tuple[str | None, bool, bool]:
        state = self.state()
        inv_id = state["work"][wid].get("implementer_invocation")
        active = state["invocations"].get(inv_id or "", {}).get("status") == "active"
        return inv_id, active, inv_id in self.held

    # ------------------------------------------------------------------ non-mutating Tickets

    def dispatch(self, wid: str) -> None:
        out = self.lead("work_dispatch", work_id=wid, card=self.rng.choice([None, None, None, "researcher", "planner"]))
        self.hold(wid, out, out["execution"]["archetype"], out["execution"]["expected_kind"])

    def redispatch(self, wid: str) -> None:
        out = self.lead("work_redispatch", work_id=wid, reason="walk: supersede the attempt")
        self.hold(wid, out, out["execution"]["archetype"], out["execution"]["expected_kind"])

    def submit_record(self, wid: str) -> None:
        inv_id, _, _ = self.executor(wid)
        kind = self.unit(wid)["execution"]["expected_kind"]
        self.records.append((wid, self.submit(self.held[inv_id], kind, RECORD_META[kind])))

    def ingest(self, wid: str) -> None:
        mine = [ev for w, ev in self.records if w == wid]
        ev = mine[-1] if self.rng.random() < 0.8 else self.rng.choice(mine)
        self.lead("evidence_ingest", work_id=wid, evidence_id=ev)

    def accept(self, wid: str) -> None:
        self.lead("work_accept", work_id=wid)

    def mutate_observation(self, wid: str) -> None:
        """A read-only executor edits its observation, then tries to submit (OBSERVATION_MUTATED)."""
        inv_id, _, _ = self.executor(wid)
        obs = Path(self.state()["invocations"][inv_id]["observation"]["path"])
        if obs.exists():
            (obs / "calc/core.py").write_text("# a read-only role wrote here\n", encoding="utf-8", newline="\n")
        self.submit_record(wid)

    def acknowledge(self, wid: str) -> None:
        for i in self.engine.input_status(self.state(), wid):
            if i["blocks_dispatch"]:
                self.lead("work_acknowledge_input", work_id=wid, evidence_id=i["id"], source=i["from"],
                          reason="walk: rechecked against the current source")

    # ------------------------------------------------------------------ mutating Tickets (M1 path)

    def assign(self, wid: str) -> None:
        self.hold(wid, self.lead("work_assign", work_id=wid), "implementer")

    def new_implementer(self, wid: str) -> None:
        inv_id, active, _ = self.implementer(wid)
        if active:  # its credential died with a crashed process: revoke it first
            self.lead("invoke_cancel", invocation=inv_id, reason="walk: implementer credential lost")
        self.hold(wid, self.lead("invoke_create", work_id=wid, role="implementer"), "implementer")

    def implement(self, wid: str) -> None:
        inv_id, _, _ = self.implementer(wid)
        ws = Path(self.unit(wid)["workspace"]["path"])
        self.variant += 1
        files = dict(SUBTRACT_PATCH)
        files["calc/core.py"] += f"\n# walk variant {self.variant}\n"
        for rel, content in files.items():
            (ws / rel).parent.mkdir(parents=True, exist_ok=True)
            (ws / rel).write_text(content, encoding="utf-8", newline="\n")
        tok = self.held[inv_id]
        self.engine.check_run(invocation_token=tok, check_id="unit")
        self.submit(tok, "implementation_report", {
            "claim": "walk implementation", "result": "pass",
            "implementation": {"files_changed": sorted(files), "checks_run": ["unit"], "deviations": [],
                               "self_review": {"completed": True, "notes": "walk"}}})

    def review(self, wid: str) -> None:
        out = self.lead("invoke_create", work_id=wid, role="reviewer")
        tok = self.hold(wid, out, "reviewer")
        open_required = [f["id"] for f in self.unit(wid).get("findings", []) if f["required"] and f["status"] == "open"]
        passing = self.rng.random() < 0.8
        review = {"independence": "R1", "disposition": "pass" if passing else "changes_required",
                  "findings": [] if passing else [{"id": f"F{self.variant}", "severity": "major", "summary": "walk"}],
                  "resolved_findings": open_required if passing else []}
        ev = self.submit(tok, "review", {"claim": "walk review", "review": review})
        self.lead("review_ingest", work_id=wid, evidence_id=ev)

    def verify(self, wid: str, scope: str = "ticket") -> None:
        u = self.unit(wid)
        out = self.lead("invoke_create", work_id=wid, role="verifier", scope="integration" if scope == "integration" else "ticket")
        tok = self.hold(wid, out, "verifier")
        unit_ev = self.engine.check_run(invocation_token=tok, check_id="unit")["evidence"]
        goal = "pass" if scope == "integration" or self.rng.random() < 0.85 else "fail"
        claims = [{"type": "goal_backwards", "claim": "behaviour present", "result": goal, "checks": [unit_ev]}]
        vscope = "parent" if u["kind"] != "ticket" else scope
        if vscope in {"ticket", "parent"}:
            claims.append({"type": "contract", "claim": "contracts hold", "result": "pass", "checks": [unit_ev]})
        ev = self.submit(tok, "verification", {"claim": "walk verification",
                                               "verification": {"scope": vscope, "claims": claims}})
        self.lead("verify_ingest", work_id=wid, evidence_id=ev)

    def integration_verify(self, wid: str) -> None:
        self.verify(wid, "integration")

    def classify(self, wid: str) -> None:
        cls = self.rng.choice(sorted(transitions.VERIFICATION_CLASSIFICATIONS))
        self.lead("verify_classify", work_id=wid, classification=cls, reason="walk classification")

    def prepare(self, wid: str) -> None:
        self.lead("integrate_prepare", work_id=wid)

    def publish(self, wid: str) -> None:
        self.lead("integrate_publish", work_id=wid)

    def reconcile_publish(self, wid: str) -> None:
        self.lead("integrate_reconcile", work_id=wid)

    # ------------------------------------------------------------------ shared Ticket operations

    def to(self, wid: str, state: str, reason: str | None = None) -> None:
        self.lead("work_transition", work_id=wid, to=state, reason=reason)

    def replan(self, wid: str) -> None:
        if self.unit(wid)["state"] != "REPLAN_REQUIRED":
            self.to(wid, "REPLAN_REQUIRED", "walk replan")
        self.plan(wid, reason="walk replan")

    def reconcile_interrupted(self, wid: str) -> None:
        origin = self.unit(wid).get("interrupted_from") or "RUNNING"
        choices = [s for s in ("ASSIGNED", "RUNNING", "REVIEW_PENDING", "VERIFY_PENDING", "COMMIT_READY")
                   if transitions.PHASE_ORDER[s] <= transitions.PHASE_ORDER.get(origin, 2)]
        self.lead("work_reconcile", work_id=wid, to=self.rng.choice(choices), reason="walk inspection")

    def reconfirm(self, wid: str) -> None:
        self.lead("plan_reconfirm", work_id=wid, reason="walk: still valid under the ancestors' plans")

    def late_submit(self, wid: str) -> None:
        """Use ANY credential ever issued, whatever happened since (revocations and attempts must hold)."""
        w, tok, role, kind = self.rng.choice(self.issued)
        if kind:
            self.submit(tok, kind, RECORD_META[kind])
        elif role == "reviewer":
            self.submit(tok, "review", {"claim": "late", "review": {"independence": "R1", "disposition": "pass",
                                                                   "findings": [], "resolved_findings": []}})
        else:
            self.engine.check_run(invocation_token=tok, check_id="unit")

    def replay(self, wid: str) -> None:
        self.lead("evidence_ingest", work_id=wid, evidence_id=self.rng.choice([ev for w, ev in self.records if w == wid]))

    # ------------------------------------------------------------------ structure

    def close(self, wid: str) -> None:
        self.lead("work_close", work_id=wid, reason="walk closeout")

    def replan_parent(self, wid: str) -> None:
        self.plan(wid, reason="walk: the parent's intent changed")

    def cancel_parent(self, wid: str) -> None:
        self.lead("work_cancel", work_id=wid, reason="walk: objective dropped")

    def new_child(self, wid: str) -> None:
        if len(self.tickets()) < MAX_TICKETS:
            self.new_ticket(wid, mutating=self.rng.random() < 0.35)

    def new_story(self, wid: str) -> None:
        epics = [w for w in self.parents() if self.unit(w)["kind"] == "epic" and self.live(w)]
        story = self.create("story", f"walk story {len(self.parents()) + 1}",
                            parent=self.rng.choice(epics) if epics else None, cls=self.rng.choice([0, 1]))
        self.plan(story)

    def move(self, wid: str) -> None:
        targets = [w for w in self.parents() if self.live(w) and w != self.unit(wid).get("parent")]
        self.lead("work_move", work_id=wid, parent=self.rng.choice(targets + [None]), reason="walk move")

    def promote(self, wid: str) -> None:
        self.lead("work_promote", work_id=wid, to="story", title=f"walk promoted {wid}", reason="walk: bigger than it looked")
        self.units.append(self.state()["work"][wid]["parent"])

    def depend(self, wid: str) -> None:
        done_nm = [w for w in self.tickets() if self.nm(w) and self.unit(w)["state"] == "DONE" and w != wid]
        edges = [e["id"] for e in self.unit(wid).get("depends_on", [])]
        if edges and (not done_nm or self.rng.random() < 0.4):
            self.lead("work_depend", work_id=wid, remove=[self.rng.choice(edges)], reason="walk: not needed")
        elif done_nm:
            self.lead("work_depend", work_id=wid, add=[f"{self.rng.choice(done_nm)}:evidence"], reason="walk: needs it")

    def handoff(self, wid: str) -> None:
        offer = self.lead("lead_handoff_offer")["offer"]
        out = self.engine.lead_handoff_accept(offer=offer, expect_rev=self.state()["revision"])
        self.token, self.gen = out["token"], out["generation"]

    def handoff_cancel(self, wid: str) -> None:
        self.lead("lead_handoff_cancel")

    def takeover(self, wid: str) -> None:
        self.mp.setattr(operator, "authorize", lambda *a, **k: {"authorized_by": "walk-operator-stub"})
        out = self.engine.lead_takeover(expect_rev=self.state()["revision"], reason="walk: previous Lead lost")
        self.token, self.gen = out["token"], out["generation"]

    # ------------------------------------------------------------------ choice

    def nm_options(self, wid: str, st: str) -> list[tuple[str, float]]:
        _, active, held = self.executor(wid)
        mine = any(w == wid for w, _ in self.records)
        ingested = bool((self.unit(wid).get("execution") or {}).get("record"))
        # An executor that is gone (interrupted, cancelled) or orphaned by a crash: only a new attempt helps.
        stuck = [("redispatch", 8)] if not (active and held) and not ingested else []
        running = [("submit_record", 6), ("mutate_observation", 0.4)] if active and held else []
        return {
            "READY": [("dispatch", 8), ("acknowledge", 1)],
            "ASSIGNED": stuck or [("to:RUNNING", 8), ("redispatch", 0.5)],
            "RUNNING": stuck + running + ([("ingest", 5)] if mine else []) + [
                ("accept", 4 if ingested else 0.5), ("to:REVIEW_PENDING", 1.5 if ingested else 0.3),
                ("redispatch", 0.5), ("acknowledge", 0.3)],
            "REVIEW_PENDING": [("review", 8), ("regress", 1)],
            "REVIEW_FAILED": [("regress", 8)],
            "REVIEW_PASSED": [("accept", 8), ("regress", 1)],
            "INTERRUPTED": [("reconcile_interrupted", 8)],
            "REPLAN_REQUIRED": [("replan", 8)],
        }.get(st, []) + ([("replay", 1)] if mine and st == "RUNNING" else [])

    def mutating_options(self, wid: str, st: str) -> list[tuple[str, float]]:
        u = self.unit(wid)
        _, active, held = self.implementer(wid)
        integ = (u.get("integration") or {}).get("status")
        return {
            "READY": [("assign", 8), ("acknowledge", 1)],
            "ASSIGNED": [("to:RUNNING", 8)] if active else [("new_implementer", 8)],
            "RUNNING": ([("implement", 6), ("to:REVIEW_PENDING", 4)] if held and active else [("new_implementer", 8)]),
            "REVIEW_PENDING": [("review", 8), ("regress", 1)],
            "REVIEW_FAILED": [("regress", 8)],
            "REVIEW_PASSED": [("to:VERIFY_PENDING", 8)],
            "VERIFY_PENDING": [("verify", 8), ("regress", 1)],
            "VERIFICATION_FAILED": [("classify", 8)],
            "VERIFICATION_INCONCLUSIVE": [("regress", 4)],
            "VERIFIED": [("to:COMMIT_READY", 8)],
            "COMMIT_READY": {None: [("prepare", 8)], "prepared": [("integration_verify", 8)],
                             "validated": [("publish", 5), ("publish!", 3)],
                             "publishing": [("reconcile_publish", 8)]}.get(integ, [("prepare", 4), ("regress", 4)]),
            "INTERRUPTED": [("reconcile_interrupted", 8)],
            "REPLAN_REQUIRED": [("replan", 8)],
        }.get(st, [])

    def parent_options(self, wid: str, st: str) -> list[tuple[str, float]]:
        u = self.unit(wid)
        if st in H.TERMINAL:
            return []
        opts: list[tuple[str, float]] = [("new_child", 1.0), ("replan_parent", 0.25)]
        if u["kind"] == "story":
            opts.append(("cancel_parent", 0.2))
        if st == "ACCEPTANCE_PENDING":
            if (u.get("parent_verification") or {}).get("awaiting_classification"):
                opts.append(("classify", 8))
            opts += [("review", 5), ("verify", 5), ("close", 5)]
        return opts

    def options(self, wid: str) -> list[tuple[str, float]]:
        u = self.unit(wid)
        st = u["state"]
        if u["kind"] != "ticket":
            opts = self.parent_options(wid, st)
        else:
            opts = self.nm_options(wid, st) if self.nm(wid) else self.mutating_options(wid, st)
            if st not in H.TERMINAL:
                opts += [("move", 0.3), ("promote", 0.1)]
                if st in {"READY", "BLOCKED", "REPLAN_REQUIRED"}:
                    opts.append(("depend", 0.5))
                if st not in {"BLOCKED", "REPLAN_REQUIRED"}:
                    opts.append(("replan", 0.2))
            elif st == "DONE":
                opts.append(("move", 0.2))  # a DONE child moved into a live parent (its review goes stale)
        if u.get("plan") and self.engine.plan_binding_problem(self.state(), wid):
            opts.append(("reconfirm", 8))
        opts += [("handoff", 0.3), ("takeover", 0.3), ("new_story", 0.1)]
        if self.issued:
            opts.append(("late_submit", 0.6))
        return opts

    def lead_recovery(self) -> str | None:
        lead = self.state()["lead"]
        if lead["generation"] != self.gen:
            return "takeover"
        if lead["status"] == "handoff_pending":
            return "handoff_cancel"
        return None

    def pick_unit(self) -> str:
        live = [w for w in self.units if self.live(w)]
        if not [w for w in live if self.unit(w)["kind"] == "ticket"]:
            self.new_story("")
            self.new_ticket(self.units[-1], mutating=self.rng.random() < 0.3)
            live = [w for w in self.units if self.live(w)]
        def weight(w: str) -> float:
            u = self.unit(w)
            if u["kind"] != "ticket":
                return 3 if u["state"] == "ACCEPTANCE_PENDING" else 0.6
            return 1.5 if u["state"] in {"READY", "BLOCKED"} else 4
        return self.rng.choices(live, weights=[weight(w) for w in live])[0]

    def step(self, i: int) -> None:
        recovery = self.lead_recovery()
        wid = self.pick_unit()
        if recovery and self.rng.random() < 0.8:
            name = recovery
        else:
            opts = self.options(wid) or [("handoff", 1)]
            name = self.rng.choices([o for o, _ in opts], weights=[w for _, w in opts])[0]
        fault = self.rng.choice(PUBLISH_FAULTS) if name == "publish!" else (
            self.rng.choice(TXN_FAULTS) if self.rng.random() < FAULT_RATE else None)
        before = self.unit(wid)["state"]
        entry = f"{i:02d} {wid} {before}: {name}" + (f" [fault {fault}]" if fault else "")
        try:
            if fault:
                self.mp.setenv("AEW_FAULT", fault)
                self.mp.setenv("AEW_FAULT_MODE", "raise")
            if name.startswith("to:"):
                self.to(wid, name[3:])
            elif name == "regress":
                self.to(wid, "RUNNING", "walk regression")
            else:
                getattr(self, name.rstrip("!"))(wid)
            self.accepted += 1
            entry += " -> ok"
        except InjectedFault as exc:
            entry += f" -> CRASH at {exc}"
        except AEWError as exc:
            entry += f" -> rejected {exc.code}"
        finally:
            self.mp.delenv("AEW_FAULT", raising=False)
            self.mp.delenv("AEW_FAULT_MODE", raising=False)
            self.engine = Engine.discover(self.root)  # a fresh process: nothing survives in memory
        self.log.append(entry + f" (now {self.unit(wid)['state']})")
        problems = control_violations(self.root)
        assert not problems, "invariants violated after:\n  " + "\n  ".join(self.log[-15:] + problems)


@pytest.mark.exploratory
@pytest.mark.parametrize("seed", SEEDS)
def test_seeded_hierarchy_walk_keeps_control_invariants(tmp_path, monkeypatch, seed):
    walk = HierarchyWalk(tmp_path, seed, monkeypatch)
    for i in range(STEPS):
        walk.step(i)
    print("\n".join(walk.log))  # shown with -s
    assert walk.accepted >= STEPS // 3, "\n".join(walk.log)
    kinds = {w: walk.unit(w)["kind"] for w in walk.units}
    assert set(kinds.values()) >= {"epic", "story", "ticket"}
