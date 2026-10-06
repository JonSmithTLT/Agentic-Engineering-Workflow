"""Deterministic post-integration validation: ``aew integrate validate`` (M4-D5; the M4-D5 plan, revision 3).

With ``gates.post_integration.validation`` resolving to ``checks`` for a Ticket (``aew.policy.validation``), the
integration candidate is validated with no model: AEW's check machinery runs the policy's post-integration checks on
the candidate, under the entry's lease, contained, and records ``check_result`` evidence produced by the engine
(``producer.kind: engine``) under the lease's custodian invocation.

**Two transactions around the checks.** Transaction 1 pins the run: the lease and its custodian, the candidate and its
snapshot, the exact check set, the obligation binding (the legality inputs the mode was resolved from) and the hard
deadline. The checks then run outside the control lock. Transaction 2 re-resolves and re-verifies everything pinned;
any difference abandons the run and writes nothing satisfying.

**The run is durable and its identity exact.** A run is identified by (candidate, snapshot, check-set digest,
obligation binding). Only one runs per candidate. A crash between the transactions is resumable: staged results with
``finished.json`` are ingested without re-running; incomplete ones abandon the run. A committed run is reused only for
the exact identity. Every terminal run is kept as an immutable record (``work/<T>/validation-runs/<IV>.yaml``); hot
state keeps the current run and the ids.

**Fail closed without immutable source.** Checks mode produces satisfying evidence only where containment makes the
integration worktree read-only for the whole run (Linux, ``os_readonly_roots``, self-tested). Elsewhere it is refused
before anything is pinned; ``--diagnostic`` runs the checks for information only, and never produces evidence.

**Three kinds of result.** A FAIL is VERIFICATION_FAILED (the existing COMMIT_READY edge, taken by this command from
its own evidence: no verifier evidence is ever manufactured). Inconclusive (a timeout, or a changed candidate) takes the
existing integration-scope path: the Ticket stays COMMIT_READY and the entry waits for disposition. Infrastructure
failure records no evidence; an allow-listed transient reason is retried once after a backoff, a project circuit
breaker stops retries when failures cluster, and the bound reached releases the lease to AWAITING_DISPOSITION.

**The deadline reduces authority only.** Expiry kills the executor and refuses its late commit; the lease is released
only through AWAITING_DISPOSITION, never by the timer itself.
"""

from __future__ import annotations

import copy
import json
import os
import socket
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import faults, transitions
from aew.engine import queue_ops as Q
from aew.errors import (
    AEWError,
    ContainmentUnavailable,
    GateUnsatisfied,
    IllegalTransition,
    StaleRevision,
)
from aew.harness import containment, procs
from aew.harness.agentenv import POSIX_KEEP, WINDOWS_KEEP
from aew.knowledge import evidence as E
from aew.policy import checks as C
from aew.policy import guardrails as GR
from aew.policy import validation as V
from aew.util import atomic_write, create_exclusive, dump_yaml, sha256_file, sha256_text, utc_now
from aew.workspace import integration as I

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import GatesPort, InvocationsPort, QueuePort, WorkUnitsPort

STAGING = "local/validation"
RUNS_DIR = "validation-runs"
TERMINAL = ("committed", "abandoned", "unavailable", "advisory")
# Abandon reasons that are not infrastructure: the identity or the authority moved, so a fresh run is in order.
NOT_INFRA = frozenset({"STALE_OBLIGATION", "CHECK_SET_CHANGED", "CANDIDATE_CHANGED", "LEASE_LOST", "SUPERSEDED"})


class ValidationContainmentUnavailable(IllegalTransition):
    """Checks mode on a host whose containment cannot make the candidate immutable while the checks run."""

    code = "VALIDATION_CONTAINMENT_UNAVAILABLE"


class ValidationRunning(IllegalTransition):
    """Another validation run of this candidate is executing."""

    code = "VALIDATION_RUNNING"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _past(stamp: str | None) -> bool:
    return bool(stamp) and _now() >= _parse(str(stamp))


CURRENT, DIAGNOSTIC = "current_validation_run", "diagnostic_run"
SLOTS = (CURRENT, DIAGNOSTIC)


def slot_of(run: dict[str, Any]) -> str:
    """Where a run lives on its integration record: an authoritative run is the current one; an advisory diagnostic
    run has its own slot, so it never displaces the run publication relies on (PR #91 review, finding 4)."""
    return DIAGNOSTIC if run.get("diagnostic") else CURRENT


def executor_alive(run: dict[str, Any]) -> bool:
    """Whether the run's executor process still exists (its pid together with its start time). A run executing on
    another host is unobservable from here, so it counts as alive until its deadline."""
    ex = run.get("executor") or {}
    if ex.get("host") != socket.gethostname():
        return not _past(run.get("deadline_at"))
    return procs.same_process(ex.get("host_pid"), float(ex.get("start_time") or 0))


def stuck_run(run: dict[str, Any] | None) -> str | None:
    """The next action for a validation run left ``running`` whose executor is gone or past its deadline, or None."""
    if not run or run.get("state") != "running":
        return None
    if _past(run.get("deadline_at")):
        why = "is past its hard deadline"
    elif not executor_alive(run):
        why = "lost its executor"
    else:
        return None
    return (f"validation run {run['id']} {why}: `aew integrate validate` settles it (ingests finished results without "
            "re-running, or abandons it)")


class Validation:
    """``aew integrate validate``, the validation run, and the infrastructure circuit breaker."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, invocations: InvocationsPort, gates: GatesPort,
                 queue: QueuePort) -> None:
        self.k = k
        self.units = units
        self.invocations = invocations
        self.gates = gates
        self.queue = queue
        self.backoff_s = V.BACKOFF_S  # tests shorten it

    # ------------------------------------------------------------------ resolution (read-only)

    def _post(self) -> dict[str, Any]:
        return self.k.policy("gates").get("post_integration") or {}

    def obligation(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        return V.obligation(state, work_id, self.k.policy("gates"))

    def _check_set(self) -> dict[str, Any]:
        return V.check_set(self._post(), self.k.policy("checks"), self.k.policy("guardrails"))

    def _identity(self, unit: dict[str, Any], ob: dict[str, Any], check_set: dict[str, Any]) -> dict[str, Any]:
        integ = unit["integration"]
        return {"candidate": integ["candidate"],
                "snapshot": integ["candidate_snapshot"]["relevant_inputs_fingerprint"],
                "check_set": check_set["digest"],
                "obligation": {"mode": ob["mode"], "verifier_required": ob["verifier_required"],
                               "sources": ob["sources"], "binding": ob["binding"]}}

    def containment_available(self) -> bool:
        """Whether this host can make the integration worktree immutable while checks run: Linux, with policy
        requiring containment (``allow_weaker`` would let a run proceed labelled weaker, which proves nothing)."""
        return containment.supported() and containment.mode(self.k.policy("execution")) == containment.REQUIRED

    def establish(self, *, workspace: str, run_dir: Path) -> tuple[Any, dict[str, Any]]:
        """The run's sandbox (the verifier layout: the worktree read-only), self-tested. A seam tests replace."""
        return containment.establish(role="verifier", scope="integration", workspace=workspace, run_dir=run_dir,
                                     scratch=str(run_dir / "scratch"), bridge_dir=None,
                                     policy=self.k.policy("execution"), project=str(self.k.repo_root))

    def _require_validatable(self, state: dict[str, Any], work_id: str) -> dict[str, Any]:
        unit = self.units.unit(state, work_id)
        if not Q.queued(state):
            raise IllegalTransition("checks-mode validation runs under the integration queue's lease: migrate this "
                                    "project's control state to v2 first (`aew migrate`)")
        integ = unit.get("integration") or {}
        if unit["state"] != "COMMIT_READY" or integ.get("status") not in {"prepared", "validated"}:
            raise IllegalTransition(f"{work_id} has no prepared integration candidate to validate",
                                    state=unit["state"], integration=integ.get("status"))
        self.gates.require_current_binding(unit)
        self.queue.require_live_lease(state, work_id, "validating the integration candidate")
        return unit

    def _require_checks_mode(self, ob: dict[str, Any], work_id: str) -> None:
        if ob["mode"] == V.CHECKS:
            if not self._post().get("checks"):
                raise GateUnsatisfied(
                    f"{work_id}'s post-integration validation resolves to `checks`, but gates.post_integration.checks "
                    "lists none: an empty check set proves nothing, so it never validates a candidate. List the "
                    "checks, or validate with the verifier", code_reason="VALIDATION_CHECKS_EMPTY")
            return
        if ob["verifier_required"]:
            raise GateUnsatisfied(
                f"{work_id} must be validated by an integration verifier: {'; '.join(ob['sources'])}. Policy cannot "
                "weaken that obligation, so checks mode is refused; dispatch the post-integration verifier",
                code_reason="VERIFIER_OBLIGATION", sources=ob["sources"])
        raise GateUnsatisfied(
            f"{work_id}'s post-integration validation resolves to `verifier` (gates.post_integration.validation for "
            f"class {ob['local_class']}): dispatch the post-integration verifier",
            code_reason="VALIDATION_MODE_VERIFIER")

    # ------------------------------------------------------------------ the command

    def integrate_validate(self, *, token: str, expect_rev: int, work_id: str, wait: bool = False,
                           diagnostic: bool = False) -> dict[str, Any]:
        state = self.k.store.read()
        self._require_validatable(state, work_id)
        ob = self.obligation(state, work_id)
        self._require_checks_mode(ob, work_id)
        if not diagnostic and not self.containment_available():
            label = containment.label(contained=False)
            raise ValidationContainmentUnavailable(
                f"checks-mode validation needs containment that keeps the candidate immutable while the checks run, "
                f"and this host has {label['filesystem']}: a check could change the source, run against the change and "
                "restore it, unseen. Validate this Ticket with the post-integration verifier, or run `aew integrate "
                "validate --diagnostic` for advisory results that never satisfy validation",
                filesystem=label["filesystem"], next="dispatch the post-integration verifier")
        rev = expect_rev
        while True:
            state = self.k.store.read()
            unit = self._require_validatable(state, work_id)
            current = (unit["integration"] or {}).get(CURRENT)
            identity = self._identity(unit, self.obligation(state, work_id), self._check_set())
            # One run at a time on a candidate, authoritative or diagnostic: both execute in its worktree.
            running = next((r for r in ((unit["integration"] or {}).get(s) for s in SLOTS)
                            if r and r["state"] == "running"), None)
            if running is not None:
                settled = self._settle_running(token, rev, work_id, running, identity, wait=wait)
                if settled is not None:
                    return settled
                rev = self._rev()  # the run we waited for ended: look again, under the revision it left
                continue
            if current and current["state"] == "committed" and current["identity"] == identity and not diagnostic:
                return {"ok": True, "work_id": work_id, "noop": True, "run": current["id"],
                        "evidence": list(current.get("evidence") or []), "result": current.get("result"),
                        "integration": unit["integration"]["status"], "revision": self._rev()}
            # A diagnostic run is advisory: the authoritative runs' attempt bound never applies to it, so it can never
            # release the lease or change the candidate's status (PR #91 re-review, finding 2).
            attempts = 0 if diagnostic else self._infra_attempts(current, identity)
            if attempts >= V.MAX_INFRA_ATTEMPTS:
                return self._release_unavailable(token, rev, work_id, current, why="the infrastructure attempt "
                                                 "bound for this candidate is used up")
            return self._run(token, rev, work_id, attempt=attempts + 1, diagnostic=diagnostic)

    def _rev(self) -> int:
        return int(self.k.store.read()["revision"])

    @staticmethod
    def _infra_attempts(current: dict[str, Any] | None, identity: dict[str, Any]) -> int:
        if not current or current["identity"] != identity or current.get("diagnostic"):
            return 0
        if current["state"] in ("unavailable", "abandoned") and current.get("reason") not in NOT_INFRA:
            return int(current.get("infra_attempt") or 1)
        return 0

    def _settle_running(self, token: str, rev: int, work_id: str, run: dict[str, Any], identity: dict[str, Any], *,
                        wait: bool) -> dict[str, Any] | None:
        """A run recorded ``running`` when this command starts: wait for it, end it at its deadline, ingest what it
        finished, or abandon it. Returns the command's result, or None to look again."""
        alive = executor_alive(run)
        if alive and not _past(run["deadline_at"]):
            if not wait:
                raise ValidationRunning(
                    f"{run['id']} is validating {work_id}'s candidate (pid {run['executor'].get('host_pid')}): wait "
                    f"for it (`aew integrate validate {work_id} --wait`)", run=run["id"],
                    pid=run["executor"].get("host_pid"), deadline_at=run["deadline_at"])
            from aew.engine.outbox import wait_for

            def ended() -> bool:
                unit = self.k.store.read()["work"].get(work_id) or {}
                now = (unit.get("integration") or {}).get(slot_of(run)) or {}
                return now.get("id") != run["id"] or now.get("state") != "running" or not executor_alive(now)

            remaining = max(0.0, (_parse(run["deadline_at"]) - _now()).total_seconds())
            wait_for(ended, self.k.aew_root, timeout=remaining + 1.0)
            return None
        if alive:  # past its deadline: an authority-reducing action, never a lease release
            procs.kill_pid(run["executor"].get("host_pid"))
            return self._abandon(token, rev, work_id, run["id"], "VALIDATION_DEADLINE_EXPIRED",
                                 "the run passed its hard deadline; its executor was terminated")
        staged = self._staged(run)
        if staged is not None and (run["identity"] == identity or run.get("diagnostic")):
            return self._commit_txn(token, rev, work_id, run, staged)  # finished, never committed: no re-run
        if staged is not None:
            return self._abandon(token, rev, work_id, run["id"], self._moved_reason(run["identity"], identity),
                                 "the run finished, but its identity is no longer current")
        reason = "VALIDATION_DEADLINE_EXPIRED" if _past(run["deadline_at"]) else "VALIDATION_INTERRUPTED"
        return self._abandon(token, rev, work_id, run["id"], reason, "the executor died before the run finished")

    @staticmethod
    def _moved_reason(pinned: dict[str, Any], now: dict[str, Any]) -> str:
        if pinned["obligation"] != now["obligation"]:
            return "STALE_OBLIGATION"
        if pinned["check_set"] != now["check_set"]:
            return "CHECK_SET_CHANGED"
        return "CANDIDATE_CHANGED"

    # ------------------------------------------------------------------ transaction 1, the checks, transaction 2

    def _run(self, token: str, expect_rev: int, work_id: str, *, attempt: int, diagnostic: bool) -> dict[str, Any]:
        while True:
            run = self._pin(token, expect_rev, work_id, attempt=attempt, diagnostic=diagnostic)
            faults.hit("validate.after_pin")
            outcome = self._execute(work_id, run)
            if outcome.get("infra") is None:
                return self._commit(token, work_id, run, outcome)
            code = outcome["infra"]
            breaker_open = self._end_infra(token, work_id, run["id"], code, outcome.get("detail") or "")
            if code in V.TRANSIENT and attempt < V.MAX_INFRA_ATTEMPTS and not breaker_open and not diagnostic:
                time.sleep(self.backoff_s)  # never immediately: a second expensive run under the same pressure
                attempt += 1
                expect_rev = self._rev()
                continue
            if diagnostic:
                return {"ok": False, "work_id": work_id, "run": run["id"], "diagnostic": True, "unavailable": code,
                        "revision": self._rev()}
            current = (self.k.store.read()["work"][work_id].get("integration") or {}).get(CURRENT)
            return self._release_unavailable(token, None, work_id, current, why=f"{code}: "
                                             + ("the circuit breaker is open" if breaker_open
                                                else "not an allow-listed transient reason" if code not in V.TRANSIENT
                                                else "the retry is used up"))

    def _pin(self, token: str, expect_rev: int, work_id: str, *, attempt: int, diagnostic: bool) -> dict[str, Any]:
        """Transaction 1: the run, recorded ``running`` under the custodian, with everything it will re-verify."""
        with self.k.lead_txn(token, expect_rev, "integrate.validate") as ctx:
            state = ctx.state
            unit = self._require_validatable(state, work_id)
            ob = self.obligation(state, work_id)
            self._require_checks_mode(ob, work_id)
            integ = unit["integration"]
            for other in (integ.get(s) for s in SLOTS):
                if other and other["state"] == "running":
                    raise ValidationRunning(f"{other['id']} is already running on {work_id}'s candidate",
                                            run=other["id"])
            lease = Q.lease_of(state, work_id)
            assert lease is not None  # _require_validatable
            custodian = state["invocations"][lease["custodian"]]
            n = int(custodian.get("validation_runs", 0)) + 1
            custodian["validation_runs"] = n
            run_id = f"IV-{lease['custodian'].split('-', 1)[1]}-{n}"
            check_set = self._check_set()
            definitions = self._resolve_definitions(check_set)
            now = _now()
            run = {"id": run_id, "custodian": lease["custodian"], "entry": lease["entry"],
                   "identity": self._identity(unit, ob, check_set), "checks": check_set["checks"],
                   "executor": {"host_pid": os.getpid(), "start_time": procs.started_at(os.getpid()) or time.time(),
                                "host": socket.gethostname()},
                   "started_at": _iso(now),
                   "deadline_at": _iso(now + timedelta(seconds=V.deadline_s(self._post(), self.k.policy("checks")))),
                   "state": "running", "infra_attempt": attempt}
            if diagnostic:
                run["diagnostic"] = True
            integ[slot_of(run)] = run
            runs = integ.setdefault("validation_runs", {"count": 0, "ids": []})
            runs["count"] += 1
            runs["ids"].append(run_id)
            ctx.refs.append(f"invocation:{lease['custodian']}")
            ctx.summary = (f"{work_id} validation run {run_id} pinned ({'diagnostic, ' if diagnostic else ''}"
                           f"{len(check_set['checks'])} checks, deadline {run['deadline_at']})")
        # The resolved definitions travel with the executor, never through state: the checks run exactly what this
        # transaction pinned, whatever policy says while they run (PR #91 review, finding 1).
        return {**run, "_definitions": definitions}

    def _resolve_definitions(self, check_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Each pinned check's definition as resolved now: a configured check's command, cwd and timeout, or the
        guardrails policy for the builtin; with the digest it hashes to, which must be the pinned one."""
        checks_policy, guardrails = self.k.policy("checks"), copy.deepcopy(self.k.policy("guardrails"))
        out: dict[str, dict[str, Any]] = {}
        for entry in check_set["checks"]:
            if entry["definition_sha256"] is None:
                continue  # not configured: the run reports CHECK_NOT_CONFIGURED
            cfg = copy.deepcopy(C.resolve(checks_policy, entry["check_id"]))
            digest = C.definition_digest(cfg, guardrails=guardrails if cfg.get("builtin") else None)
            if digest != entry["definition_sha256"]:
                raise IllegalTransition(f"check {entry['check_id']}'s definition changed while the run was pinned; "
                                        "run `aew integrate validate` again")
            out[entry["check_id"]] = {"cfg": cfg, "guardrails": guardrails if cfg.get("builtin") else None}
        return out

    def _staging(self, run_id: str) -> Path:
        return self.k.aew_root / STAGING / run_id

    def _execute(self, work_id: str, run: dict[str, Any]) -> dict[str, Any]:
        """Run the pinned checks, outside the control lock, contained, under the deadline. Stages each result
        atomically and writes ``finished.json`` last. Returns the staged outcome, or ``{"infra": code}``."""
        unit = self.k.store.read()["work"][work_id]
        integ = unit["integration"]
        meta = self.gates.record_meta(unit)
        scope = (list((meta.get("scope") or {}).get("paths") or []), (meta.get("acceptance") or {}).get("inputs"))
        workspace = integ["workspace"]
        directory = self._staging(run["id"])
        directory.mkdir(parents=True, exist_ok=True)
        layout, label = None, containment.label(contained=False)
        try:
            layout, label = self.establish(workspace=workspace, run_dir=directory)
        except ContainmentUnavailable as exc:
            if not run.get("diagnostic"):
                return {"infra": V.classify_containment_failure(exc), "detail": exc.message}
        if not run.get("diagnostic") and label.get("filesystem") != containment.CONTAINED:
            return {"infra": "CONTAINMENT_UNAVAILABLE", "detail": "the run's sandbox was not established"}
        env = self._check_env(layout)
        trees = procs.CheckTrees()
        remaining = (_parse(run["deadline_at"]) - _now()).total_seconds()
        timer = threading.Timer(max(0.0, remaining), trees.end)  # the deadline ends the checks, mid-check included
        timer.daemon = True
        timer.start()
        results = []
        before = self.invocations.snapshot_of(workspace, integ["workspace_id"])
        try:
            for entry in run["checks"]:
                if _past(run["deadline_at"]):
                    return {"infra": "VALIDATION_DEADLINE_EXPIRED", "detail": "the deadline passed between checks"}
                check_id = entry["check_id"]
                if entry["definition_sha256"] is None:
                    return {"infra": "CHECK_NOT_CONFIGURED",
                            "detail": f"check {check_id} is not configured in policy/checks.yaml"}
                faults.hit("validate.before_check")
                staged = self._one_check(run, check_id, entry, Path(workspace), integ, scope, env, layout, trees)
                if _past(run["deadline_at"]):
                    return {"infra": "VALIDATION_DEADLINE_EXPIRED", "detail": f"the deadline passed during {check_id}"}
                if staged.get("infra"):
                    return staged
                results.append(staged)
        finally:
            timer.cancel()
        after = self.invocations.snapshot_of(workspace, integ["workspace_id"])
        finished = {"run": run["id"], "identity": run["identity"], "containment": label,
                    "before": before, "after": after,
                    "mutated": before["relevant_inputs_fingerprint"] != after["relevant_inputs_fingerprint"],
                    "results": [{"check_id": r["check_id"], "file": r["file"],
                                 "sha256": sha256_file(directory / r["file"])} for r in results]}
        faults.hit("validate.before_finished")
        atomic_write(directory / "finished.json", json.dumps(finished, indent=2, sort_keys=True))
        faults.hit("validate.after_finished")
        return self._staged(run) or {"infra": "VALIDATION_STAGING_INCONSISTENT", "detail": "finished.json unreadable"}

    @staticmethod
    def _check_env(layout: Any) -> dict[str, str]:
        """An allowlist environment: operating-system basics and the sandbox's own settings. Never the Lead's
        credential or anything else the Lead's shell held (the candidate's code runs here)."""
        keep = WINDOWS_KEEP if sys.platform == "win32" else POSIX_KEEP
        env = {k: v for k, v in os.environ.items()
               if k.upper() in keep or (sys.platform != "win32" and k.startswith("LC_"))}
        env["PATH"] = os.environ.get("PATH") or os.environ.get("Path") or ""
        env["PYTHONUTF8"] = "1"
        env.update(getattr(layout, "env", None) or {})
        return env

    def _one_check(self, run: dict[str, Any], check_id: str, entry: dict[str, Any], workspace: Path,
                   integ: dict[str, Any], scope: tuple[list[str], Any], env: dict[str, str], layout: Any,
                   trees: Any) -> dict[str, Any]:
        directory = self._staging(run["id"])
        pinned = run["_definitions"][check_id]  # the definition transaction 1 resolved, never live policy
        cfg = pinned["cfg"]
        if cfg.get("builtin"):  # the guardrails, over what the candidate changes against its base
            verdict = GR.evaluate(I.changed_between(self.k.repo_root, integ["base"], integ["candidate"]),
                                  pinned["guardrails"], scope[0], scope[1])
            out = {"exit_code": 1 if verdict["violations"] else 0, "duration_s": 0.0, "outcome": "ran",
                   "log": json.dumps(verdict, indent=2), "command": ["aew-builtin", "guardrails"], "spawn_errno": None}
        else:
            out = C.run(cfg, workspace, env=env, layout=layout, trees=trees)
        if out["outcome"] == "spawn_failed":
            return {"infra": V.classify_spawn_failure(out.get("spawn_errno")),
                    "detail": f"check {check_id} could not start: {out['log'].splitlines()[-1]}"}
        if out["outcome"] == "timeout" or out["exit_code"] is None:
            result, reason = "inconclusive", "CHECK_TIMEOUT"
        else:
            result, reason = ("pass" if out["exit_code"] == 0 else "fail"), None
        record = {"check_id": check_id, "definition_sha256": entry["definition_sha256"], "result": result,
                  "reason": reason, "exit_code": out["exit_code"], "duration_s": out["duration_s"],
                  "command": out["command"], "log": out["log"]}
        name = f"{check_id}.json"
        atomic_write(directory / name, json.dumps(record, indent=2, sort_keys=True))
        return {**record, "file": name}

    def _staged(self, run: dict[str, Any]) -> dict[str, Any] | None:
        """The run's staged results, if ``finished.json`` is present and every staged file still matches it."""
        directory = self._staging(run["id"])
        try:
            finished = json.loads((directory / "finished.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if finished.get("run") != run["id"] or finished.get("identity") != run["identity"]:
            return None
        results = []
        for item in finished.get("results") or []:
            path = directory / item["file"]
            if sha256_file(path) != item["sha256"]:
                return None
            results.append(json.loads(path.read_text(encoding="utf-8")))
        if [r["check_id"] for r in results] != [c["check_id"] for c in run["checks"]]:
            return None
        return {"results": results, "mutated": finished["mutated"], "before": finished["before"],
                "containment": finished.get("containment")}

    def _commit(self, token: str, work_id: str, run: dict[str, Any], staged: dict[str, Any]) -> dict[str, Any]:
        """Transaction 2, in the same command as transaction 1: it re-verifies everything pinned rather than relying
        on the revision, because the Lead may commit other work while the checks run."""
        try:
            return self._commit_txn(token, self._rev(), work_id, run, staged)
        except StaleRevision:  # another writer committed between the read and the lock: re-verify on the new state
            return self._commit_txn(token, self._rev(), work_id, run, staged)

    def _commit_txn(self, token: str, rev: int, work_id: str, run: dict[str, Any],
                    staged: dict[str, Any]) -> dict[str, Any]:
        abandoned: tuple[str, str] | None = None
        change = None
        evidence_ids: list[str] = []
        with self.k.lead_txn(token, rev, "integrate.validated") as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            integ = unit.get("integration") or {}
            current = integ.get(slot_of(run)) or {}
            problem = self._pin_problem(state, work_id, unit, run)
            if current.get("id") != run["id"] or current.get("state") != "running":
                # The candidate was retired, or the run settled, while the checks ran: nothing is recorded for it.
                abandoned = ("SUPERSEDED", f"{run['id']} is no longer {work_id}'s running validation run")
                ctx.summary = f"{work_id} validation run {run['id']} superseded while its checks ran; nothing recorded"
            elif problem is not None:
                abandoned = problem
                if problem[0] not in NOT_INFRA and not run.get("diagnostic"):  # an expiry counts, as in _abandon
                    current["breaker_open"] = self._breaker_record(state, work_id, run["id"], problem[0])
                self._terminate(ctx, work_id, current, "abandoned", reason=problem[0], detail=problem[1])
                ctx.summary = f"{work_id} validation run {run['id']} abandoned: {problem[0]}"
            elif run.get("diagnostic"):
                current["advisory"] = [{k: r[k] for k in ("check_id", "result", "reason", "exit_code")}
                                       for r in staged["results"]]
                current["advisory_mutated"] = staged["mutated"]
                self._terminate(ctx, work_id, current, "advisory")
                ctx.summary = f"{work_id} diagnostic run {run['id']}: advisory only, no evidence"
            else:
                results = self._bind_evidence(state, work_id, unit, run, staged)
                evidence_ids = [r["id"] for r in results]
                overall = self._overall(results, staged["mutated"])
                current["evidence"] = evidence_ids
                current["result"] = overall
                self._terminate(ctx, work_id, current, "committed")
                for eid in evidence_ids:
                    ctx.refs.append(f"evidence/{work_id}/{eid}.md")
                ctx.events.append({"kind": "evidence.ingested", "work": work_id, "evidence_kind": "check_result",
                                   "ids": evidence_ids})
                change = self._apply_result(state, work_id, unit, run, overall, results)
                ctx.summary = f"{work_id} validation run {run['id']} committed: {overall}"
            self.units.before_commit(ctx)
        out: dict[str, Any] = {"ok": abandoned is None, "work_id": work_id, "run": run["id"],
                               "revision": ctx.session.committed_revision}
        if abandoned:
            out.update(abandoned=abandoned[0], detail=abandoned[1],
                       next=f"`aew integrate validate {work_id}` starts a run under the current identity")
            return out
        if run.get("diagnostic"):
            out.update(diagnostic=True, advisory=current["advisory"], mutated=staged["mutated"])
            return out
        integ = self.units.unit(ctx.state, work_id).get("integration") or {}
        out.update(result=current["result"], evidence=evidence_ids, transition=change,
                   integration=integ.get("status"), queue=Q.entry_of(ctx.state, work_id)[1])
        out["ok"] = current["result"] == "pass"
        out["next"] = {"pass": f"`aew integrate publish {work_id}`",
                       "fail": f"classify the failure (`aew verify classify {work_id}`)",
                       "inconclusive": "the entry waits for your disposition (`aew integrate requeue` once settled)"
                       }[current["result"]]
        return out

    def _pin_problem(self, state: dict[str, Any], work_id: str, unit: dict[str, Any],
                     run: dict[str, Any]) -> tuple[str, str] | None:
        """Why the pinned run no longer stands (reason code, detail), or None."""
        lease = Q.lease_of(state, work_id)
        if lease is None or lease["reconcile"] is not None or lease["custodian"] != run["custodian"]:
            return "LEASE_LOST", "the entry's lease, or its custodian, changed while the checks ran"
        if _past(run["deadline_at"]):
            return "VALIDATION_DEADLINE_EXPIRED", "the run passed its hard deadline before it could commit"
        integ = unit.get("integration") or {}
        if unit["state"] != "COMMIT_READY" or integ.get("status") not in {"prepared", "validated"}:
            return "SUPERSEDED", f"the Ticket is {unit['state']} with integration {integ.get('status')}"
        if self.gates.binding_problem(unit) is not None:
            return "SUPERSEDED", "the candidate is bound to an earlier COMMIT_READY or plan"
        now = self._identity(unit, self.obligation(state, work_id), self._check_set())
        if now != run["identity"]:
            return self._moved_reason(run["identity"], now), "the pinned identity no longer matches current policy " \
                                                             "and state"
        live = self.invocations.snapshot_of(integ["workspace"], integ["workspace_id"])["relevant_inputs_fingerprint"]
        if live != run["identity"]["snapshot"]:
            return "CANDIDATE_CHANGED", "the integration worktree no longer matches the pinned snapshot"
        return None

    @staticmethod
    def _overall(results: list[dict[str, Any]], mutated: bool) -> str:
        if mutated:
            return "inconclusive"  # every result is suspect when the candidate changed (a containment defect on Linux)
        kinds = {r["result"] for r in results}
        if "fail" in kinds:
            return "fail"
        return "inconclusive" if "inconclusive" in kinds else "pass"

    def _bind_evidence(self, state: dict[str, Any], work_id: str, unit: dict[str, Any], run: dict[str, Any],
                       staged: dict[str, Any]) -> list[dict[str, Any]]:
        """One sealed engine ``check_result`` per check, bound to the candidate, the snapshot, the check's definition,
        the check set, the obligation binding and the run."""
        plan = unit.get("plan") or {}
        label = staged.get("containment") or {}
        out = []
        for r in staged["results"]:
            result = "inconclusive" if staged["mutated"] else r["result"]
            reason = "WORKSPACE_MUTATED" if staged["mutated"] else r.get("reason")
            seq = E.next_seq(self.k.aew_root, work_id)
            eid = f"{run['id']}-check-{r['check_id']}-{seq}"
            log_rel = f"evidence/{work_id}/logs/{eid}.log"
            create_exclusive(self.k.aew_root / log_rel, r["log"])
            meta = {
                "schema": "aew/evidence/v1", "id": eid, "kind": "check_result", "work_unit": work_id,
                "producer": {"kind": "engine", "invocation": run["custodian"], "validation_run": run["id"]},
                "created_at": utc_now(), "seq": seq,
                "plan_revision": {"revision": plan["accepted"], "sha256": plan["sha256"]} if plan else None,
                "evaluated_snapshot": staged["before"],
                "method": {"capability": "targeted_test_execution" if r["command"][0] != "aew-builtin"
                           else "guardrail_check", "provider": "aew-check-runner", "command": r["command"],
                           "containment": label.get("filesystem", containment.WORKDIR_ONLY)},
                "claim": f"check {r['check_id']} passes on the integration candidate {run['identity']['candidate']}",
                "result": result,
                "evidence": [{"path": log_rel, "sha256": sha256_file(self.k.aew_root / log_rel)}],
                "check": {"check_id": r["check_id"], "exit_code": r["exit_code"], "duration_s": r["duration_s"],
                          "mutated_inputs": staged["mutated"], "definition_sha256": r["definition_sha256"]},
                "integration_validation": {"candidate": run["identity"]["candidate"],
                                           "check_set": run["identity"]["check_set"],
                                           "obligation_binding": run["identity"]["obligation"]["binding"],
                                           **({"reason": reason} if reason else {})},
            }
            create_exclusive(self.k.aew_root / f"evidence/{work_id}/{eid}.md", E.seal(meta, ""))
            out.append({"id": eid, "result": result})
        return out

    def _apply_result(self, state: dict[str, Any], work_id: str, unit: dict[str, Any], run: dict[str, Any],
                      overall: str, results: list[dict[str, Any]]) -> dict[str, str] | None:
        evidence_ids = [r["id"] for r in results]
        integ = unit["integration"]
        integ["validation"] = {"mode": V.CHECKS, "run": run["id"], "evidence": evidence_ids,
                               "identity": run["identity"]}
        unit["last_verification"] = {"evidence": evidence_ids[0] if evidence_ids else None, "result": overall,
                                     "scope": "integration", "run": run["id"]}
        if overall == "pass":
            integ["status"] = "validated"
            return None
        if overall == "fail":
            # The existing COMMIT_READY -> VERIFICATION_FAILED edge, taken from the engine's own check evidence. No
            # verifier or verification evidence is written, and verify.ingest is not called (rev 3 tightening 6).
            integ["status"] = "validation_failed"
            failing = next(r["id"] for r in results if r["result"] == "fail")  # the classification's evidence
            transitions.check(unit["state"], "VERIFICATION_FAILED", "integrate.validate")
            unit["last_verification"]["evidence"] = failing
            return self.units.set_state(unit, "VERIFICATION_FAILED",
                                        f"post-integration checks failed ({run['id']})", state=state)
        integ["status"] = "validation_inconclusive"
        # The existing integration-scope inconclusive path (M4-D4): the Ticket stays COMMIT_READY and the entry waits
        # for the Lead, so it never holds the one lease while the Lead decides.
        self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="validation_inconclusive",
                           detail={"run": run["id"], "evidence": evidence_ids})
        return None

    # ------------------------------------------------------------------ terminal runs and infrastructure

    @staticmethod
    def _terminate(ctx: Any, work_id: str, run: dict[str, Any], to: str, *, reason: str | None = None,
                   detail: str | None = None) -> None:
        """Make the current run terminal and keep it as an immutable record (created once, never rewritten). Hot
        state keeps the run as it ended, with the record's path and digest."""
        run["state"] = to
        run["ended_at"] = utc_now()
        if reason:
            run["reason"] = reason
        if detail:
            run["detail"] = detail
        Validation._write_record(ctx, work_id, run)

    @staticmethod
    def _write_record(ctx: Any, work_id: str, run: dict[str, Any]) -> None:
        path = f"work/{work_id}/{RUNS_DIR}/{run['id']}.yaml"
        text = dump_yaml({"schema": "aew/validation-run/v1", **{k: v for k, v in run.items() if k != "record"}})
        ctx.session.write(path, text)
        ctx.refs.append(path)
        run["record"] = {"path": path, "sha256": sha256_text(text)}

    def finalize(self, ctx: Any) -> None:
        """A transaction finalizer: every terminal run without its immutable record gets one in the same commit. A run
        ended by retiring its candidate (a state hook, which has no transaction to write through) is recorded here,
        so no terminal run is ever only a line in integration history (PR #91 review, finding 6).

        First, a run still marked running on a candidate that is no longer open (the Ticket left COMMIT_READY, or
        the candidate is publishing, integrated, retired, inconclusive or unavailable, by whatever path: a verifier's
        verdict, a disposition, a publication) can never commit: it ends here, abandoned as SUPERSEDED (never a
        breaker event), and is recorded with the rest (PR #91 re-review R1, R3). Its executor, if alive, finds it no
        longer running at its transaction 2 and records nothing."""
        for wid, unit in ctx.state["work"].items():
            integ = unit.get("integration") or {}
            is_open = unit["state"] == "COMMIT_READY" and integ.get("status") in ("prepared", "validated")
            records = [integ, *(unit.get("integration_history") or [])]
            for holder in records:
                for s in SLOTS:
                    run = holder.get(s)
                    if run and run.get("state") == "running" and (holder is not integ or not is_open):
                        holder[s] = run = {**run, "state": "abandoned", "reason": "SUPERSEDED",
                                           "ended_at": _iso(_now()),
                                           "detail": f"{wid}'s candidate is no longer open "
                                                     f"({unit['state']}, {integ.get('status')})"}
                    if run and run.get("state") in TERMINAL and not run.get("record"):
                        self._write_record(ctx, wid, run)

    @staticmethod
    def _find(unit: dict[str, Any], run_id: str) -> dict[str, Any]:
        """The run ``run_id`` in whichever slot holds it, or an empty dict."""
        integ = unit.get("integration") or {}
        return next((r for r in (integ.get(s) for s in SLOTS) if r and r.get("id") == run_id), {})

    def _abandon(self, token: str, rev: int, work_id: str, run_id: str, reason: str, detail: str) -> dict[str, Any]:
        with self.k.lead_txn(token, rev, "integrate.validation_abandoned") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            current = self._find(unit, run_id)
            if current.get("state") != "running":
                raise IllegalTransition(f"{run_id} is no longer {work_id}'s running validation run")
            if reason not in NOT_INFRA and not current.get("diagnostic"):
                current["breaker_open"] = self._breaker_record(ctx.state, work_id, run_id, reason)
            self._terminate(ctx, work_id, current, "abandoned", reason=reason, detail=detail)
            ctx.summary = f"{work_id} validation run {run_id} abandoned: {reason}"
        return {"ok": False, "work_id": work_id, "run": run_id, "abandoned": reason, "detail": detail,
                "revision": ctx.session.committed_revision,
                "next": f"`aew integrate validate {work_id}` starts a new run within the attempt bound"}

    def _end_infra(self, token: str, work_id: str, run_id: str, code: str, detail: str) -> bool:
        """Record an infrastructure failure: the run ``unavailable``, the breaker updated. Returns whether the breaker
        is open."""
        with self.k.lead_txn(token, self._rev(), "integrate.validation_unavailable") as ctx:
            unit = self.units.unit(ctx.state, work_id)
            current = self._find(unit, run_id)
            is_open = (self._breaker_record(ctx.state, work_id, run_id, code) if not current.get("diagnostic")
                       else self._breaker(ctx.state)["open"] is not None)
            if current.get("state") == "running":
                current["breaker_open"] = is_open
                self._terminate(ctx, work_id, current, "abandoned" if code == "VALIDATION_DEADLINE_EXPIRED"
                                else "unavailable", reason=code, detail=detail)
            ctx.summary = f"{work_id} validation run {run_id} unavailable: {code}"
        return is_open

    def _release_unavailable(self, token: str, rev: int | None, work_id: str, run: dict[str, Any] | None, *,
                             why: str) -> dict[str, Any]:
        """The bound reached: prove nothing was published, park the candidate, release the lease to disposition."""
        with self.k.lead_txn(token, self._rev() if rev is None else rev, "integrate.validation_released") as ctx:
            state = ctx.state
            unit = self.units.unit(state, work_id)
            integ = unit["integration"]
            snapshot = self.invocations.snapshot_of(integ["workspace"], integ["workspace_id"])
            proofs = {"ref_unchanged": self.k.authoritative_commit() == integ["base"],
                      "candidate_unchanged": snapshot["relevant_inputs_fingerprint"]
                      == integ["candidate_snapshot"]["relevant_inputs_fingerprint"]}
            integ["status"] = "validation_unavailable"
            breaker = self._breaker(state)
            detail = {"run": (run or {}).get("id"), "code": (run or {}).get("reason"),
                      "attempts": (run or {}).get("infra_attempt"), "breaker_open": breaker.get("open") is not None,
                      "proofs": proofs, "why": why}
            self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="validation_unavailable",
                               detail=detail)
            ctx.summary = f"{work_id} validation unavailable ({why}): the entry waits for the Lead"
            self.units.before_commit(ctx)
        return {"ok": False, "work_id": work_id, "unavailable": True, **detail,
                "queue": Q.entry_of(ctx.state, work_id)[1], "revision": ctx.session.committed_revision,
                "next": f"fix the environment, then `aew integrate requeue {work_id}`; or defer it. Independent "
                        "entries behind it integrate meanwhile"}

    # ------------------------------------------------------------------ the circuit breaker

    @staticmethod
    def _breaker(state: dict[str, Any]) -> dict[str, Any]:
        queue = state.setdefault("queue", Q.empty())
        return queue.setdefault("validation_breaker", {"failures": [], "open": None})

    def _breaker_record(self, state: dict[str, Any], work_id: str, run_id: str, code: str) -> bool:
        breaker = self._breaker(state)
        cutoff = _now() - timedelta(seconds=V.BREAKER_WINDOW_S)
        breaker["failures"] = [f for f in breaker["failures"] if _parse(f["at"]) >= cutoff][-V.BREAKER_THRESHOLD:]
        breaker["failures"].append({"at": _iso(_now()), "code": code, "run": run_id, "work": work_id})
        if breaker["open"] is None and len(breaker["failures"]) >= V.BREAKER_THRESHOLD:
            breaker["open"] = {"at": _iso(_now()), "codes": sorted({f["code"] for f in breaker["failures"]}),
                               "runs": [f["run"] for f in breaker["failures"]]}
        breaker["failures"] = breaker["failures"][-V.BREAKER_THRESHOLD:]
        return breaker["open"] is not None

    def breaker_status(self) -> dict[str, Any]:
        state = self.k.store.read()
        breaker = ((state.get("queue") or {}).get("validation_breaker")) or {"failures": [], "open": None}
        return {"open": breaker["open"] is not None, **breaker, "threshold": V.BREAKER_THRESHOLD,
                "window_s": V.BREAKER_WINDOW_S}

    def breaker_reset(self, *, token: str, expect_rev: int, reason: str, authorization: dict[str, str]
                      ) -> dict[str, Any]:
        """Close the breaker: the operator's explicit reset (``authorization`` comes from the operator's terminal)."""
        if not (reason and reason.strip()):
            raise AEWError("resetting the validation breaker needs a reason")
        with self.k.lead_txn(token, expect_rev, "integrate.breaker_reset", reason=reason) as ctx:
            breaker = self._breaker(ctx.state)
            was = breaker["open"]
            breaker.update(open=None, failures=[], reset={"at": utc_now(), **authorization})
            ctx.summary = "validation circuit breaker reset by the operator" + ("" if was else " (it was closed)")
        return {"ok": True, "was_open": was is not None, "revision": ctx.session.committed_revision}
