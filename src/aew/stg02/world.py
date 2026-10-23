"""The slice's two fact providers: AEW's own engine state (real) and the labelled fixture world (STG-02).

**Real.** A project's committed control state, read lock-free through the dashboard's :class:`StateReader` (the same
read the provisional dashboard API uses; nothing of that API's envelope or routes is reused). It owns the work units
(their state, accepted plan revision and blockers: the WIS facts) and the invocations with their harness runs (the
R-01 progress facts). Every fact read from it is a real record, stamped with its real identity, and unqualified
(:mod:`aew.stg02.wire`).

**Fixture.** ``worlds/slice-world.json``: the owners AEW does not have yet (HEB's attachment, eligibility and
continuation effect, ADC, AEV, IF10, the delegation issuer ``delegation:fixture`` and the slice's recipient). Every
identifier in it starts with ``fixture:``. Its times are offsets from the server's start.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aew.stg02 import wire as W

WORLD_PATH = Path(__file__).resolve().parent / "worlds" / "slice-world.json"
AXES = ("HEB", "ADC", "WIS", "AEV", "R01", "IF10")
# The slice's one delegation issuer, under the name the STG-02 handoff gives it. It is a fixture: AEW has no qualified
# delegation issuer (the registry's preview rule ONLY_WHEN_EXISTING_CURRENT_DELEGATION_ACTUALLY_QUALIFIES).
DELEGATION_ISSUER = "delegation:fixture"
# The work states a Ticket waits in, and the D-01 waiting cause each is (WaitingData.cause). The Lead or the operator
# acts on ESCALATED and REPLAN_REQUIRED; REVIEW_FAILED and the verification failures wait on a required result.
WAITING_STATES = {"BLOCKED": "dependency", "ESCALATED": "operator_need", "REPLAN_REQUIRED": "operator_need",
                  "INTERRUPTED": "unknown", "REVIEW_FAILED": "mandatory_result",
                  "VERIFICATION_FAILED": "mandatory_result", "VERIFICATION_INCONCLUSIVE": "mandatory_result"}


class SourceUnavailable(Exception):
    """The real source could not be read now (a lock timeout, an unreadable or corrupt state file)."""


@dataclass
class Fixture:
    """The fixture world, resolved against the server's start time."""

    doc: dict[str, Any]
    started: datetime
    intents: dict[str, dict[str, Any]] = field(default_factory=dict)  # name -> the exact O-01 intent
    delegations: dict[str, dict[str, Any]] = field(default_factory=dict)  # proof_ref -> the issuer's record

    @classmethod
    def load(cls, started: datetime, path: Path = WORLD_PATH) -> Fixture:
        doc = json.loads(path.read_text(encoding="utf-8"))
        fx = cls(doc, started)
        fx._check_labels()
        for name, spec in doc["intents"].items():
            fx.intents[name] = fx.intent(spec)
        for d in doc["delegations"]:
            i = fx.intents[d["intent"]]
            fx.delegations[d["proof_ref"]] = {
                "issuer_ref": doc["delegation_issuer"], "status": d["status"], "intent_ref": i["intent_ref"],
                "actor_ref": i["actor_ref"], "installation_ref": doc["installation_ref"],
                "recipient_ref": doc["recipient_ref"], "intent_digest": W.intent_digest(i),
                "valid_until": W.utc(W.later(started, d["valid_for_s"]))}
        return fx

    def _check_labels(self) -> None:
        """Every identifier the world serves is labelled: a fixture fact can never pass for a real one."""
        def walk(o: Any, path: str) -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(o, list):
                for n, v in enumerate(o):
                    walk(v, f"{path}[{n}]")
            elif isinstance(o, str) and (path.endswith("_ref") or path.endswith("_id") or ".issuers." in path
                                         or path.endswith(("epoch", "version", "issuer"))):
                if not o.startswith(W.FIXTURE) and o != DELEGATION_ISSUER:
                    raise ValueError(f"fixture world {path} = {o!r} is not labelled {W.FIXTURE!r}")
        walk({k: v for k, v in self.doc.items() if k not in ("schema", "_label")}, "world")

    # ------------------------------------------------------------------ the world's facts

    @property
    def installation(self) -> str:
        return self.doc["installation_ref"]

    @property
    def recipient(self) -> str:
        return self.doc["recipient_ref"]

    @property
    def heb(self) -> dict[str, Any]:
        return self.doc["heb"]

    def at(self, offset_s: float) -> str:
        return W.utc(W.later(self.started, offset_s))

    def work(self, work_ref: str) -> dict[str, Any] | None:
        return next((w for w in self.doc["work"] if w["work_ref"] == work_ref), None)

    def visible_work(self, recipient: str) -> list[dict[str, Any]]:
        return [w for w in self.doc["work"] if recipient in w["recipients"]]

    def run(self, execution_id: str) -> dict[str, Any] | None:
        return next((r for r in self.doc["runs"] if r["execution_id"] == execution_id), None)

    def intent(self, spec: dict[str, Any]) -> dict[str, Any]:
        """The exact CONTINUE_ELIGIBLE_WORK intent a delegation in this world names (A-24 SW-04 binds the digest)."""
        h, w = self.heb, self.work(spec["work_ref"])
        basis = (w or {}).get("heb_eligibility", {}).get("basis_ref") or "fixture:basis-unknown"
        return {"intent_ref": spec["intent_ref"], "action": "CONTINUE_ELIGIBLE_WORK", "actor_ref": h["lead_ref"],
                "authority_class": "CURRENT_DELEGATED_GRANT", "owner_hint": "HEB",
                "subject": {"project_ref": self.doc["project_ref"], "installation_ref": self.installation,
                            "attachment_ref": h["attachment_ref"], "generation_ref": h["generation_ref"]},
                "predecessor": {"basis_ref": basis, "basis_version": spec["work_revision"], "source_epoch": h["epoch"]},
                "target": {"work_ref": spec["work_ref"], "work_revision": spec["work_revision"],
                           "grant_ref": "fixture:grant-" + spec["work_ref"].removeprefix(W.FIXTURE),
                           "eligible_basis_ref": basis, "selection_mode": "DELIBERATE_SELECTED_WORK"},
                "origin_proof_ref": None, "delegated_grant_proof_ref": spec["proof_ref"]}


class EngineSource:
    """AEW's committed control state for one project, read without the control lock."""

    def __init__(self, repo_root: Path) -> None:
        from aew.dashboard.reader import StateReader
        from aew.engine.api import Engine

        self.repo_root = repo_root
        self.engine = Engine(repo_root, repo_root / ".aew")
        self.reader = StateReader(self.engine)
        self.outage = False  # the test-only outage switch (server --test-routes); never set otherwise
        self._lock = threading.Lock()

    def snapshot(self) -> Any:
        from aew.errors import AEWError

        if self.outage:
            raise SourceUnavailable("engine source outage (test-only switch)")
        try:
            with self._lock:
                return self.reader.snapshot()
        except (AEWError, OSError, ValueError, KeyError) as exc:
            raise SourceUnavailable(type(exc).__name__) from exc

    def observed(self, run: str) -> str:
        from aew.harness import runlog

        status, _ = runlog.observed_status(runlog.run_dir(self.engine.aew_root, run))
        return status
