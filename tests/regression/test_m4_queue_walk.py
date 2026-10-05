"""Seeded adversarial walk over the integration queue (M4-D slice D3; M4 report §6: "no publication without the lease,
a current ALLOW and validation bound to the current head").

The composition walk (``test_composition_walk.py``), with mutating concurrency 3 and up to four Tickets, so entries
queue behind each other. Each Ticket changes a module of its own, and now and then ``calc/core.py`` too, so some
candidates conflict. Added moves: preparing any COMMIT_READY Ticket out of turn, cancelling the lease's custodian,
a commit to ``main`` from outside AEW (the one automatic rebuild, then AWAITING_DISPOSITION on a second move), and
reconciling a lease; and since D4 the Lead's defer, requeue and reorder. Every step is followed by the whole oracle,
queue rules 34-39 included, and injected crashes are followed by a fresh engine.

The default is a short run; the slice's acceptance run is ``AEW_QUEUE_WALK_STEPS=500`` over the three seeds.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_composition_walk import Walk

from aew.engine import transitions
from aew.util import dump_yaml, load_yaml

SEEDS = [int(s) for s in os.environ.get("AEW_QUEUE_WALK_SEEDS", "7,19,31").split(",")]
STEPS = int(os.environ.get("AEW_QUEUE_WALK_STEPS", "60"))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class QueueWalk(Walk):
    def __init__(self, tmp_path: Path, seed: int, monkeypatch: pytest.MonkeyPatch) -> None:
        super().__init__(tmp_path, seed, monkeypatch)
        gates = self.root / ".aew/policy/gates.yaml"
        gates.write_text(dump_yaml({**load_yaml(gates.read_text(encoding="utf-8")), "mutating_concurrency": 3}),
                         encoding="utf-8", newline="\n")
        self.outside = 0
        self.edited: set[str] = set()
        while len(self.tickets) < 3:
            self.tickets.append(self.new_ticket())
        for wid in self.tickets:  # three entries queue behind each other from the first step
            self.fast_forward(wid)

    def fast_forward(self, wid: str) -> None:
        """READY -> COMMIT_READY with passing review and verification, without crashes."""
        self.assign(wid)
        self.start(wid)
        self.implement(wid)
        self.to(wid, "REVIEW_PENDING")
        ev = self.submit_review(wid, self.dispatch(wid, "reviewer"), passing=True)
        self.lead("review_ingest", work_id=wid, evidence_id=ev)
        self.to(wid, "VERIFY_PENDING")
        ev = self.submit_verification(wid, self.dispatch(wid, "verifier"), "ticket")
        self.lead("verify_ingest", work_id=wid, evidence_id=ev)
        self.to(wid, "COMMIT_READY")

    def queue(self) -> dict[str, Any]:
        return self.state().get("queue") or {"entries": {}, "lease": None}

    # ------------------------------------------------------------------ actions

    def implement(self, wid: str) -> None:
        ws = self.workspace(wid)
        self.variant += 1
        files = {f"calc/m_{wid.replace('-', '_').lower()}.py": f"def f():\n    return {self.variant}\n"}
        if self.rng.random() < 0.25:  # some Tickets also touch the shared module: candidates may conflict
            core = (ws / "calc/core.py").read_text(encoding="utf-8")
            files["calc/core.py"] = core + f"\n# {wid} variant {self.variant}\n"
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
        super().edit(wid)
        self.edited.add(wid)  # its gated snapshot is gone: integration is refused until it goes back to RUNNING

    def second_ticket(self, wid: str) -> None:
        if len(self.tickets) < 4:
            self.tickets.append(self.new_ticket())

    def prepare_any(self, wid: str) -> None:
        """Prepare a COMMIT_READY Ticket whatever its place in the queue (FIFO and the lease must refuse)."""
        ready = [w for w in self.tickets if (self.state()["work"].get(w) or {}).get("state") == "COMMIT_READY"]
        if ready:
            self.lead("integrate_prepare", work_id=self.rng.choice(ready))

    def cancel_custodian(self, wid: str) -> None:
        lease = self.queue()["lease"]
        if lease:
            self.lead("invoke_cancel", invocation=lease["custodian"], reason="walk: custodian lost")

    def reconcile_lease(self, wid: str) -> None:
        lease = self.queue()["lease"]
        if lease:
            work = self.queue()["entries"][lease["entry"]]["work"]
            self.lead("integrate_reconcile", work_id=work)

    def outside_commit(self, wid: str) -> None:
        """Someone commits to the authoritative branch outside AEW: a prepared candidate goes stale."""
        self.outside += 1
        note = self.root / "OUTSIDE.md"
        note.write_text(f"outside commit {self.outside}\n", encoding="utf-8", newline="\n")
        for args in (("add", "OUTSIDE.md"), ("commit", "-q", "-m", f"outside {self.outside}")):
            subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True, creationflags=NO_WINDOW)

    def defer_entry(self, wid: str) -> None:
        live = [e["work"] for e in self.queue()["entries"].values()
                if e["state"] in ("QUEUED", "LEASED", "AWAITING_DISPOSITION")]
        if live:
            self.lead("integrate_defer", work_id=self.rng.choice(live), reason="walk: set aside")

    def requeue_entry(self, wid: str) -> None:
        waiting = [e["work"] for e in self.queue()["entries"].values()
                   if e["state"] in ("DEFERRED", "AWAITING_DISPOSITION")]
        if waiting:
            self.lead("integrate_requeue", work_id=self.rng.choice(waiting), reason="walk: try again")

    def reorder_entry(self, wid: str) -> None:
        live = [e["work"] for e in self.queue()["entries"].values()]
        if len(live) >= 2:
            moved, ahead_of = self.rng.sample(live, 2)
            self.lead("integrate_reorder", work_id=moved, before=None if self.rng.random() < 0.3 else ahead_of,
                      reason="walk: reorder")

    # ------------------------------------------------------------------ choice

    def options(self, wid: str) -> list[tuple[str, float]]:
        # The base walk's Lead churn (handoff, takeover) interrupts every Ticket at once here; keep it, but rarer.
        calmer = {"handoff": 0.1, "takeover": 0.1, "replan": 0.1}
        opts = [(name, calmer.get(name, weight)) for name, weight in super().options(wid)]
        if wid in self.edited:
            if self.unit(wid)["state"] in {"RUNNING", "ASSIGNED", "READY"}:
                self.edited.discard(wid)
            else:
                opts.append(("regress", 12))
        q = self.queue()
        lease = q["lease"]
        ready = [w for w in self.tickets if (self.state()["work"].get(w) or {}).get("state") == "COMMIT_READY"]
        opts += [("second_ticket", 0.5)] + ([("prepare_any", 3)] if ready else [])
        states = [e["state"] for e in q["entries"].values()]
        if states:  # D4: the Lead's queue commands
            opts += [("defer_entry", 0.4), ("reorder_entry", 0.5)]
            if any(s in ("DEFERRED", "AWAITING_DISPOSITION") for s in states):
                opts.append(("requeue_entry", 4))
        if lease is not None:
            opts += [("cancel_custodian", 0.4), ("outside_commit", 0.3)]
            if lease["reconcile"] is not None:
                opts.append(("reconcile_lease", 8))
        return opts

    def pick_ticket(self) -> str:
        """Favour the Tickets furthest along, so several reach COMMIT_READY and queue behind each other."""
        lease = self.queue()["lease"]
        if lease is not None and lease["reconcile"] is not None and self.rng.random() < 0.7:
            work = self.queue()["entries"][lease["entry"]]["work"]
            if work in self.tickets:
                return work
        live = [w for w in self.tickets if self.unit(w)["state"] not in {"DONE", "CANCELLED"}]
        if not live:
            return super().pick_ticket()
        weights = [(1 + transitions.PHASE_ORDER.get(self.unit(w)["state"], 0)) ** 2 for w in live]
        return self.rng.choices(live, weights=weights)[0]


@pytest.mark.exploratory
@pytest.mark.parametrize("seed", SEEDS)
def test_seeded_queue_walk_keeps_the_queue_and_lease_invariants(tmp_path, monkeypatch, seed):
    walk = QueueWalk(tmp_path, seed, monkeypatch)
    for i in range(STEPS):
        walk.step(i)
    print("\n".join(walk.log))  # shown with -s
    assert walk.accepted >= STEPS // 3, "\n".join(walk.log)
