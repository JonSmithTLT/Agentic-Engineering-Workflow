"""Seeded adversarial walk over Lead and role operations (review 2026-09-26: "expand adversarial
sequences, not only the number of random store writes").

Each step picks an operation that is plausible for a Ticket's current state, plus cross-cutting
ones (Lead handoff, operator-authorized takeover, a relevant edit after evidence, a second mutating
Ticket, crash-injected commits and publishes) and adversarial ones from the remediation re-review:
straggler invocations, reports submitted but never ingested, late submissions with any credential
ever issued, and replayed ingestion of any earlier report. Each runs in-process through the Engine API — the same
authority the CLI uses — and then checks the cross-operation invariants.

* Rejections (``AEWError``) are expected: the walk deliberately tries things the state forbids.
* Any other exception is a bug.
* Injected crashes (``AEW_FAULT_MODE=raise``) are followed by a fresh engine, as a restarted
  process would be; recovery must leave state on which the invariants still hold.

The operator-terminal channel is stubbed *only here*: the walk exercises what a takeover does to
control state, not how it is authorized (that is AT-4b's job, through a real terminal).
"""

from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Any

import pytest

from aew import operator
from aew.engine import transitions
from aew.engine.api import Engine
from aew.engine.faults import InjectedFault
from aew.errors import AEWError
from aew.util import dump_yaml
from aewflow import SUBTRACT_PATCH, sample_project
from invariants import control_violations

SEEDS = [int(s) for s in os.environ.get("AEW_WALK_SEEDS", "11,23,37,41,53").split(",")]
STEPS = int(os.environ.get("AEW_WALK_STEPS", "60"))
FAULT_RATE = float(os.environ.get("AEW_WALK_FAULT_RATE", "0.08"))  # chance of a crash-injected commit per step

FAST_CHECKS = {
    "schema": "aew/checks/v1",
    "checks": {"unit": {"configured": True, "command": ["{python}", "-c", "import calc.core"], "cwd": ".",
                        "timeout_s": 120, "description": "import smoke (fast walk check)"}},
    "baseline_failures": [],
}
TXN_FAULTS = ["txn.after_stage", "txn.after_replace", "txn.mid_apply", "txn.after_log"]
PUBLISH_FAULTS = ["integrate.after_publishing_record", "integrate.after_cas", "integrate.mid_sync",
                  "integrate.before_done", *TXN_FAULTS]
RECONCILABLE = ("ASSIGNED", "RUNNING", "REVIEW_PENDING", "VERIFY_PENDING", "COMMIT_READY")


class Walk:
    def __init__(self, tmp_path: Path, seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
        self.p = sample_project(tmp_path, checks=FAST_CHECKS)
        self.root = self.p.root
        self.rng = random.Random(seed)
        self.mp = monkeypatch
        self.token = self.p.token
        self.gen = 1  # generation of self.token (sample_project acquired the seat)
        self.engine = Engine.discover(self.root)
        self.impl_token: dict[str, str] = {}
        self.impl_inv: dict[str, str] = {}  # the implementer invocation whose credential the walk actually holds
        self.issued: list[tuple[str, str, str, str]] = []  # (work id, credential, role, scope) — ever issued
        self.submitted: list[tuple[str, str, str]] = []  # (work id, evidence id, kind) — ever submitted
        self.variant = 0
        self.log: list[str] = []
        self.accepted = 0
        self.tickets = [self.new_ticket()]

    # ------------------------------------------------------------------ plumbing

    def state(self) -> dict[str, Any]:
        return self.engine.store.read()

    def unit(self, wid: str) -> dict[str, Any]:
        return self.state()["work"][wid]

    def lead(self, method: str, **kw: Any) -> Any:
        return getattr(self.engine, method)(token=self.token, expect_rev=self.state()["revision"], **kw)

    def submit(self, inv_token: str, kind: str, meta: dict[str, Any]) -> str:
        text = f"---\n{dump_yaml(meta)}---\nwalk step\n"
        return self.engine.submit(invocation_token=inv_token, kind=kind, text=text)["evidence"]

    def new_ticket(self) -> str:
        wid = self.lead("work_create", kind="ticket", title=f"walk ticket {len(getattr(self, 'tickets', []))+1}",
                        risk_class=1, scope_paths=["calc/**", "tests/**"],
                        goal_backwards=["calc.core imports and subtract works"],
                        contract=["changes stay within calc/ and tests/"])["id"]
        rev = self.lead("plan_propose", no_assurance=True, work_id=wid, body="Change calc/core.py; keep tests green.\n")["revision_number"]
        self.lead("plan_accept", work_id=wid, revision=rev)
        return wid

    def workspace(self, wid: str) -> Path:
        return Path(self.unit(wid)["workspace"]["path"])

    # ------------------------------------------------------------------ actions

    def dispatch(self, wid: str, role: str, scope: str = "ticket") -> str:
        kw: dict[str, Any] = {"role": role} | ({"scope": "integration"} if scope == "integration" else {})
        out = self.lead("invoke_create", work_id=wid, **kw)
        tok, self.dispatched = out["invocation_token"], out["invocation"]
        self.issued.append((wid, tok, role, scope))
        return tok

    def submit_review(self, wid: str, tok: str, passing: bool) -> str:
        open_required = [f["id"] for f in self.unit(wid).get("findings", [])
                         if f["required"] and f["status"] == "open"]
        review = {"independence": "R1", "disposition": "pass" if passing else "changes_required",
                  "findings": [] if passing else [{"id": f"F{self.variant}", "severity": "major",
                                                   "summary": "walk finding"}],
                  "resolved_findings": open_required if passing else []}
        ev = self.submit(tok, "review", {"claim": "walk review", "review": review})
        self.submitted.append((wid, ev, "review"))
        return ev

    def submit_verification(self, wid: str, tok: str, scope: str, goal: str = "pass") -> str:
        unit_ev = self.engine.check_run(invocation_token=tok, check_id="unit")["evidence"]
        claims = [{"type": "goal_backwards", "claim": "behaviour present", "result": goal, "checks": [unit_ev]}]
        if scope == "ticket":
            guard_ev = self.engine.check_run(invocation_token=tok, check_id="guardrails")["evidence"]
            claims.append({"type": "contract", "claim": "guardrails respected", "result": "pass",
                           "checks": [guard_ev]})
        ev = self.submit(tok, "verification", {"claim": "walk verification",
                                               "verification": {"scope": scope, "claims": claims}})
        self.submitted.append((wid, ev, "verification"))
        return ev

    def assign(self, wid: str) -> None:
        out = self.lead("work_assign", work_id=wid)
        tok = out["invocation_token"]
        self.impl_token[wid], self.impl_inv[wid] = tok, out["invocation"]
        self.issued.append((wid, tok, "implementer", "ticket"))

    def start(self, wid: str) -> None:
        self.lead("work_transition", work_id=wid, to="RUNNING")

    def redispatch(self, wid: str) -> None:
        self.impl_token[wid] = self.dispatch(wid, "implementer")
        self.impl_inv[wid] = self.dispatched

    def recover_implementer(self, wid: str) -> None:
        """A crash after an assignment's or dispatch's commit point left a live implementer invocation whose
        credential died with the process: the Lead cancels it (revoking it) and dispatches a fresh one.
        (Nightly walk finding, seeds 1014/1034; see test_compositions.py.)"""
        orphan = self.unit(wid)["implementer_invocation"]
        self.lead("invoke_cancel", invocation=orphan, reason="walk: implementer credential lost in a crash")
        self.redispatch(wid)

    def implement(self, wid: str) -> None:
        ws = self.workspace(wid)
        self.variant += 1
        files = dict(SUBTRACT_PATCH)
        files["calc/core.py"] += f"\n# walk variant {self.variant}\n"
        for rel, content in files.items():
            (ws / rel).parent.mkdir(parents=True, exist_ok=True)
            (ws / rel).write_text(content, encoding="utf-8", newline="\n")
        tok = self.impl_token[wid]
        self.engine.check_run(invocation_token=tok, check_id="unit")
        self.submit(tok, "implementation_report", {
            "claim": "walk implementation", "result": "pass",
            "implementation": {"files_changed": sorted(files), "checks_run": ["unit"], "deviations": [],
                               "self_review": {"completed": True, "notes": "walk"}}})

    def edit(self, wid: str) -> None:
        core = self.workspace(wid) / "calc/core.py"
        core.write_text(core.read_text(encoding="utf-8") + "# edited after evidence\n", encoding="utf-8",
                        newline="\n")

    def to(self, wid: str, state: str, reason: str | None = None) -> None:
        self.lead("work_transition", work_id=wid, to=state, reason=reason)

    def review(self, wid: str) -> None:
        ev = self.submit_review(wid, self.dispatch(wid, "reviewer"), passing=self.rng.random() < 0.7)
        self.lead("review_ingest", work_id=wid, evidence_id=ev)

    def review_submit_only(self, wid: str) -> None:
        self.submit_review(wid, self.dispatch(wid, "reviewer"), passing=self.rng.random() < 0.7)

    def verify(self, wid: str) -> None:
        goal = self.rng.choice(["pass", "pass", "pass", "fail", "blocked"])
        ev = self.submit_verification(wid, self.dispatch(wid, "verifier"), "ticket", goal)
        self.lead("verify_ingest", work_id=wid, evidence_id=ev)

    def verify_submit_only(self, wid: str) -> None:
        self.submit_verification(wid, self.dispatch(wid, "verifier"), "ticket")

    def straggler(self, wid: str) -> None:
        """Dispatch a role for the current phase and never use it (a lost or slow subagent)."""
        st = self.unit(wid)["state"]
        role, scope = {"REVIEW_PENDING": ("reviewer", "ticket"), "VERIFY_PENDING": ("verifier", "ticket"),
                       "COMMIT_READY": ("verifier", "integration")}.get(st, ("implementer", "ticket"))
        self.dispatch(wid, role, scope)

    def late_submit(self, wid: str) -> None:
        """Use ANY credential ever issued, whatever has happened since (revocations must hold)."""
        w, tok, role, scope = self.rng.choice(self.issued)
        if role == "reviewer":
            self.submit_review(w, tok, passing=True)
        elif role == "verifier":
            self.submit_verification(w, tok, scope)
        else:
            self.engine.check_run(invocation_token=tok, check_id="unit")

    def replay(self, wid: str) -> None:
        """Ingest ANY earlier report of this Ticket — the engine must accept it only for its own assignment."""
        mine = [(ev, kind) for w, ev, kind in self.submitted if w == wid]
        ev, kind = self.rng.choice(mine)
        self.lead("review_ingest" if kind == "review" else "verify_ingest", work_id=wid, evidence_id=ev)

    def classify(self, wid: str) -> None:
        cls = self.rng.choice(sorted(transitions.VERIFICATION_CLASSIFICATIONS))
        self.lead("verify_classify", work_id=wid, classification=cls, reason="walk classification")

    def replan(self, wid: str) -> None:
        if self.unit(wid)["state"] != "REPLAN_REQUIRED":
            self.to(wid, "REPLAN_REQUIRED", "walk replan")
        rev = self.lead("plan_propose", no_assurance=True, work_id=wid, body=f"Revised plan {self.variant}.\n",
                        reason="walk replan")["revision_number"]
        self.lead("plan_accept", work_id=wid, revision=rev)

    def prepare(self, wid: str) -> None:
        self.lead("integrate_prepare", work_id=wid)

    def integration_verify(self, wid: str) -> None:
        ev = self.submit_verification(wid, self.dispatch(wid, "verifier", "integration"), "integration")
        self.lead("verify_ingest", work_id=wid, evidence_id=ev)

    def integration_submit_only(self, wid: str) -> None:
        self.submit_verification(wid, self.dispatch(wid, "verifier", "integration"), "integration")

    def publish(self, wid: str) -> None:
        self.lead("integrate_publish", work_id=wid)

    def reconcile_publish(self, wid: str) -> None:
        self.lead("integrate_reconcile", work_id=wid)

    def reconcile_interrupted(self, wid: str) -> None:
        origin = self.unit(wid).get("interrupted_from") or "RUNNING"
        choices = [s for s in RECONCILABLE if transitions.PHASE_ORDER[s] <= transitions.PHASE_ORDER.get(origin, 2)]
        self.lead("work_reconcile", work_id=wid, to=self.rng.choice(choices), reason="walk inspection")

    def handoff(self, wid: str) -> None:
        offer = self.lead("lead_handoff_offer")["offer"]
        out = self.engine.lead_handoff_accept(offer=offer, expect_rev=self.state()["revision"])
        self.token, self.gen = out["token"], out["generation"]

    def handoff_cancel(self, wid: str) -> None:
        """A crash lost the offer secret: the offering Lead withdraws the offer."""
        self.lead("lead_handoff_cancel")

    def takeover(self, wid: str) -> None:
        self.mp.setattr(operator, "authorize", lambda *a, **k: {"authorized_by": "walk-operator-stub"})
        out = self.engine.lead_takeover(expect_rev=self.state()["revision"], reason="walk: previous Lead lost")
        self.token, self.gen = out["token"], out["generation"]

    def second_ticket(self, wid: str) -> None:
        if len(self.tickets) < 3:
            self.tickets.append(self.new_ticket())

    # ------------------------------------------------------------------ choice

    def options(self, wid: str) -> list[tuple[str, float]]:
        state = self.state()
        u = state["work"][wid]
        st = u["state"]
        integ = (u.get("integration") or {}).get("status")
        impl_active = state["invocations"].get(u.get("implementer_invocation") or "", {}).get("status") == "active"
        impl_held = impl_active and self.impl_inv.get(wid) == u.get("implementer_invocation")
        # A live implementer whose credential the walk does not hold was orphaned by a crash: recover it.
        orphaned = [("recover_implementer", 8)] if impl_active and not impl_held else []
        by_state: dict[str, list[tuple[str, float]]] = {
            "READY": [("assign", 8)],
            "ASSIGNED": ([("start", 8)] + orphaned) if impl_active else [("redispatch", 8)],
            "RUNNING": ([("implement", 6), ("to:REVIEW_PENDING", 5)] if impl_held else
                        orphaned + [("to:REVIEW_PENDING", 2)] if impl_active else [("redispatch", 8)]),
            "REVIEW_PENDING": [("review", 8), ("review_submit_only", 1), ("straggler", 0.5), ("regress", 1)],
            "REVIEW_FAILED": [("regress", 8)],
            "REVIEW_PASSED": [("to:VERIFY_PENDING", 8), ("edit", 1), ("regress", 2)],
            "VERIFY_PENDING": [("verify", 8), ("verify_submit_only", 1), ("straggler", 0.5), ("regress", 1)],
            "VERIFICATION_FAILED": [("classify", 8), ("regress", 1)],
            "VERIFICATION_INCONCLUSIVE": [("to:VERIFY_PENDING", 6), ("regress", 2)],
            "VERIFIED": [("to:COMMIT_READY", 8), ("edit", 2), ("regress", 1)],
            "COMMIT_READY": {
                None: [("prepare", 8), ("edit", 1), ("regress", 1)],
                "prepared": [("integration_verify", 8), ("integration_submit_only", 1.5), ("straggler", 0.5),
                             ("regress", 1)],
                "validated": [("publish", 5), ("publish!", 7), ("regress", 1)],
                "publishing": [("reconcile_publish", 8), ("regress", 1)],
            }.get(integ, [("prepare", 4), ("regress", 4)]),
            "INTERRUPTED": [("reconcile_interrupted", 8)],
            "REPLAN_REQUIRED": [("replan", 8)],
        }.get(st, [])
        common: list[tuple[str, float]] = [("handoff", 0.4), ("takeover", 0.4), ("second_ticket", 0.3)]
        if st not in {"DONE", "CANCELLED", "BLOCKED"}:
            common.append(("replan", 0.3))
        if self.issued:
            common.append(("late_submit", 0.6))
        if any(w == wid for w, _, _ in self.submitted) and st in {"REVIEW_PENDING", "VERIFY_PENDING", "COMMIT_READY"}:
            common.append(("replay", 1.5))
        return by_state + common

    def lead_recovery(self) -> str | None:
        """What an operator does after a crash lost a Lead secret (never inferred by the engine)."""
        lead = self.state()["lead"]
        if lead["generation"] != self.gen:
            return "takeover"  # the new holder's credential died with the crashed process
        if lead["status"] == "handoff_pending":
            return "handoff_cancel"  # the offer secret died with the crashed process
        return None

    def pick_ticket(self) -> str:
        live = [w for w in self.tickets if self.unit(w)["state"] not in {"DONE", "CANCELLED"}]
        if not live:
            self.tickets.append(self.new_ticket())
            live = self.tickets[-1:]
        holding = [(self.unit(w).get("workspace") or {}).get("status") == "active" for w in live]
        return self.rng.choices(live, weights=[6 if h else 1 for h in holding])[0]

    def step(self, i: int) -> None:
        recovery = self.lead_recovery()
        wid = self.pick_ticket()
        if recovery and self.rng.random() < 0.8:
            name = recovery
        else:
            opts = self.options(wid)
            name = self.rng.choices([o for o, _ in opts], weights=[w for _, w in opts])[0]
        fault = None
        if name == "publish!":
            fault = self.rng.choice(PUBLISH_FAULTS)
        elif self.rng.random() < FAULT_RATE:
            fault = self.rng.choice(TXN_FAULTS)
        before = self.unit(wid)["state"]
        entry = f"{i:02d} {wid} {before}: {name}" + (f" [fault {fault}]" if fault else "")
        try:
            if fault:
                self.mp.setenv("AEW_FAULT", fault)
                self.mp.setenv("AEW_FAULT_MODE", "raise")
            if name.startswith("to:"):
                self.to(wid, name[3:], "walk" if name[3:] == "VERIFY_PENDING" and before != "REVIEW_PASSED" else None)
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
        assert not problems, "invariants violated after:\n  " + "\n  ".join(self.log[-12:] + problems)


@pytest.mark.exploratory
@pytest.mark.parametrize("seed", SEEDS)
def test_seeded_adversarial_walk_keeps_control_invariants(tmp_path, monkeypatch, seed):
    walk = Walk(tmp_path, seed, monkeypatch)
    for i in range(STEPS):
        walk.step(i)
    print("\n".join(walk.log))  # shown with -s
    # The walk must actually exercise the engine, not only collect rejections.
    assert walk.accepted >= STEPS // 3, "\n".join(walk.log)
