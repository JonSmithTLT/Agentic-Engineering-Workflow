"""The integration custodian's custody worker (M4-E E6a; plan v3 §2.3: N2, S1 to S3, T1, T3, V1, V2, W1).

Mechanical integration lifecycle work is the lease's custodian's, never the Lead's (designer, 2026-10-07): the
``integration_attempt`` custody invocation M4-D created, with no harness, model, role or Lead credential. E6a gives it
a process to run in, the **custody worker** (``aew integrate custody <IA-n>``):

- **Spawned** by whichever process committed the lease grant, right after that commit (``spawn_worker``): detached and
  windowless, with an allow-list environment (the run bridge's keep-list; no ``AEW_*`` variable, so nothing of a Lead
  session), and its custody credential written to its stdin pipe, never argv, the environment, a file or a log. The
  pipe is the only handle it inherits (``close_fds``). It reads the credential and closes the pipe before it starts
  anything; it passes the credential to no child.
- **Principal.** Every commit goes through ``Kernel.custody_txn`` with that credential: it is admitted only while the
  custodian is active, holds the lease and belongs to the current Lead generation, and only for the closed family of
  integration-custody operations. It adds no authority and makes no judgment.
- **Registers** ``{host_pid, started_at}`` on its custodian in its own first commit (S2): liveness, never authorization.
  ``Queue.sync`` ends a custodian whose registered worker is gone, or that has none ``custody_register_s`` after its
  grant, and that marks the lease ``reconcile``.
- **What it does, by validation mode** (its lease's candidate ``prepared``, not yet validated):
  - ``checks``: runs ``integrate.validate`` under its lease (``Validation.custody_validate``) and routes the result in
    the commit: a pass releases the lease to VALIDATED with the candidate kept; a fail or inconclusive result takes
    M4-D5's paths. Under the Lead's PUBLISH_IF_CLEAN request and the operator's usable envelope, §17 routes a pass
    instead (M4-E E6b; ``aew.engine.publication_ops``): published under the same lease (the worker then runs the
    publish's finish), rebuilt once on a moved head, or sent to AWAITING_DISPOSITION;
  - ``verifier``: waits for the integration verifier's run (the Lead's ``ticket_prepare`` launched it, as the
    custodian's child) to end, then routes its report **without accepting it**: a clean report to VALIDATED, anything
    else (a failed, unclean or missing report) to AWAITING_DISPOSITION. The Lead accepts and publishes later through
    ``integration_publish(verification_evidence)``.
- **Never races the Lead's publish** (T3): a lease granted to publish a VALIDATED candidate holds a ``validated``
  candidate, or one the Lead's own stage is publishing, so the worker only waits; after a rebuild in the Lead's stage
  the candidate is ``prepared`` again and the worker revalidates it (checks), or routes the verifier the stage
  launched.
- **Ends** when its custodian is no longer active, its lease is gone or marked for reconciliation, or its credential is
  refused: then it exits, committing nothing (S1 admits nothing more).

``aew integrate custody`` is never the Lead's (S3, T1): the broker never relays it, and it refuses to start where a
Lead session's environment is present. The real guard is the admission check: a Lead's shell cannot present the
custody credential, so it commits nothing.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import disposition_ops as DO
from aew.engine import queue_ops as Q
from aew.errors import AEWError, IllegalTransition, PermissionDenied, StaleAuthority
from aew.harness import contract as K
from aew.harness import procs, runlog
from aew.harness.agentenv import POSIX_KEEP, WINDOWS_KEEP
from aew.knowledge import evidence as E
from aew.policy import validation as V
from aew.util import utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import GatesPort, QueuePort, WorkUnitsPort

# The granting process starts no worker when this is `off` (tests, diagnosis). It withholds the worker only: S2 then
# ends the custodian, which marks its lease for reconciliation. It grants nothing.
WORKER_SWITCH = "AEW_CUSTODY_WORKER"
LOG_DIR = "local/custody"
# Variables a Lead session sets (the broker's, and the Lead credential): the worker refuses to run with any of them
# present (S3), and its spawn never passes one (its environment is an allow-list).
LEAD_SESSION_VARS = ("AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY", "AEW_LEAD_TOKEN")
POLL_S = 5.0  # the worker re-reads state at least this often; a commit's wake file wakes it sooner
ENDED, ACTED, WAITING = "ended", "acted", "waiting"
RUN_LOST = "run lost"  # the integration verifier's run that no supervisor holds any more (routed, §2.3)


# ---------------------------------------------------------------------------------------------- the spawn


def worker_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The worker's environment: the run bridge's keep-list (operating-system basics), ``PATH``, and the location of
    the engine that spawned it, so it runs the same code. Never an ``AEW_*`` variable or any other credential (T1)."""
    base = dict(os.environ if base is None else base)
    keep = WINDOWS_KEEP if sys.platform == "win32" else POSIX_KEEP
    env = {k: v for k, v in base.items()
           if k.upper() in keep or (sys.platform != "win32" and k.startswith("LC_"))}
    env["PATH"] = base.get("PATH") or base.get("Path") or ""
    env["PYTHONUTF8"] = "1"
    return procs.engine_imports(env)  # the engine's own import path only, whatever its argv or its launcher's


def worker_argv(repo_root: Path, custodian: str) -> list[str]:
    """The worker's command: the running interpreter with no unsafe import path or user site, the project named."""
    return [sys.executable, *procs.ENGINE_PYTHON_FLAGS, "-m", "aew", "-C", str(repo_root), "integrate", "custody",
            custodian]


def spawn_worker(repo_root: Path, aew_root: Path, custodian: str, credential: str) -> int | None:
    """Start ``custodian``'s custody worker and write its credential to the worker's stdin pipe; the pid, or None when
    none was started (the switch is off, or the spawn failed: S2 then ends the custodian). Called once, right after the
    granting commit; the caller drops the credential after it."""
    if os.environ.get(WORKER_SWITCH) == "off":
        return None
    directory = aew_root / LOG_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            directory.chmod(0o700)
        with (directory / f"{custodian}.log").open("ab") as log:
            # It starts in the engine's own directory and imports only the engine and the standard library: never from
            # the project's tree (`-P`, `PYTHONSAFEPATH`), which it names with `-C` instead.
            proc = procs.spawn_detached(worker_argv(repo_root, custodian), env=worker_env(), cwd=str(directory),
                                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
    except OSError:
        return None
    try:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps({"credential": credential}) + "\n").encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass
    return proc.pid


def read_credential(stream: Any) -> str:
    """The worker's credential, read from its stdin pipe, which is then closed before anything else starts (V2)."""
    try:
        line = stream.readline()
    finally:
        stream.close()
    try:
        credential = json.loads(line)["credential"]
    except (ValueError, KeyError, TypeError):
        raise PermissionDenied("the custody worker received no credential on its pipe") from None
    if not isinstance(credential, str):
        raise PermissionDenied("the custody worker received no credential on its pipe")
    return credential


def refuse_lead_session(environ: dict[str, str] | None = None) -> None:
    """S3/T1: ``aew integrate custody`` is never a Lead's command; it refuses to run where a Lead session's environment
    is present. Keyed on the environment only: the worker is legitimately spawned by the broker's process, with that
    environment stripped."""
    present = [v for v in LEAD_SESSION_VARS if (environ if environ is not None else os.environ).get(v)]
    if present:
        raise PermissionDenied("`aew integrate custody` is the integration custodian's own process, started by the "
                               "engine when it grants a lease; it never runs in a Lead session "
                               f"({', '.join(present)} present)", variables=present)


# ---------------------------------------------------------------------------------------------- the worker


class Custody:
    """The custody worker's engine operations: registration, one pass of its work, and the report routing."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, gates: GatesPort, queue: QueuePort, validation: Any,
                 mode: Any, finish: Any = None) -> None:
        self.k = k
        self.units = units
        self.gates = gates
        self.queue = queue
        self.validation = validation
        self.mode = mode  # (state, work_id) -> "checks" | "verifier"
        self.finish = finish  # (credential, work_id) -> the PIC publish's finish (M4-E E6b)

    def register(self, credential: str) -> dict[str, Any]:
        """The worker's first commit (S2): its process identity on its custodian, under its custody credential."""
        pid = os.getpid()
        with self.k.custody_txn(credential, "custody.register") as ctx:
            custodian = ctx.actor["invocation"]
            inv = ctx.state["invocations"][custodian]
            inv["worker"] = {"host_pid": pid, "started_at": procs.started_at(pid) or time.time(),
                             "host": socket.gethostname(), "registered_at": utc_now()}
            ctx.refs.append(f"invocation:{custodian}")
            ctx.summary = f"custodian {custodian}'s custody worker registered (pid {pid})"
        return {"ok": True, "custodian": custodian, "pid": pid, "revision": ctx.session.committed_revision}

    def step(self, custodian: str, credential: str) -> tuple[str, dict[str, Any] | None]:
        """One pass of the worker's work: ``ended`` (its custody is over: exit, committing nothing), ``acted`` (it
        validated or routed, with the result) or ``waiting`` (nothing to do yet)."""
        state = self.k.store.read()
        inv = state["invocations"].get(custodian) or {}
        lease = (state.get("queue") or {}).get("lease") or {}
        if inv.get("status") != "active" or lease.get("custodian") != custodian or lease.get("reconcile") is not None:
            return ENDED, None
        wid = inv["work_unit"]
        integ = (state["work"].get(wid) or {}).get("integration") or {}
        try:
            if integ.get("status") == "publishing" and (integ.get("pic") or {}).get("custodian") == custodian:
                return ACTED, self._finish(credential, wid)  # a publish this custodian began under PIC (M4-E E6b)
            if integ.get("status") != "prepared":  # validated (a lease to publish: the Lead's), publishing, or retired
                return WAITING, None
            if self.mode(state, wid) == V.CHECKS:
                out = self.validation.custody_validate(credential=credential, work_id=wid)
                if out.get("integration") == "publishing":  # PIC began the publish in the validation's commit
                    out["publish"] = self._finish(credential, wid)
                return ACTED, out
            child = self._verifier(state, custodian)
            ended = self._ended(state, child) if child is not None else None
            if child is None or ended is None:
                return WAITING, None
            return ACTED, self.route(credential, wid, child, lost=ended == RUN_LOST)
        except (StaleAuthority, PermissionDenied):
            return ENDED, None  # its custody ended meanwhile: S1 admitted nothing

    def run(self, custodian: str, credential: str, *, poll_s: float = POLL_S,
            timeout_s: float | None = None) -> dict[str, Any]:
        """Register, then work until the custody ends (or ``timeout_s``, for tests). Every refusal of the custody
        credential ends it: the worker never retries a commit its custody no longer admits."""
        from aew.engine.outbox import wake_mark

        try:
            registered = self.register(credential)
        except (StaleAuthority, PermissionDenied) as exc:
            return {"ok": False, "custodian": custodian, "ended": "refused", "code": exc.code}
        acted: list[dict[str, Any]] = []
        deadline = None if timeout_s is None else time.monotonic() + timeout_s
        while True:
            mark = wake_mark(self.k.aew_root)
            try:
                found, out = self.step(custodian, credential)
            except AEWError as exc:  # not a custody refusal: recorded where it happened; look again after a wait
                found, out = WAITING, {"error": {"code": exc.code, "message": exc.message}}
            if found == ENDED:
                return {"ok": True, "custodian": custodian, "pid": registered["pid"], "ended": "custody_ended",
                        "acted": acted}
            if found == ACTED and out is not None:
                acted.append(out)
                continue
            if deadline is not None and time.monotonic() >= deadline:
                return {"ok": True, "custodian": custodian, "pid": registered["pid"], "ended": "timeout",
                        "acted": acted}
            until = time.monotonic() + poll_s
            while time.monotonic() < min(until, deadline or until) and wake_mark(self.k.aew_root) == mark:
                time.sleep(0.05)

    def _finish(self, credential: str, work_id: str) -> dict[str, Any]:
        """The finish of a publish begun under PUBLISH_IF_CLEAN (M4-E E6b): its result, or the refusal it ended with
        once committed (a withdrawal, a moved head's disposition). A refusal of the custody itself propagates."""
        try:
            return self.finish(credential, work_id)
        except (StaleAuthority, PermissionDenied):
            raise
        except AEWError as exc:
            return {"ok": False, "work_id": work_id, "published": False,
                    "error": {"code": exc.code, "message": exc.message, **exc.details}}

    # ------------------------------------------------------------------ verifier mode

    @staticmethod
    def _verifier(state: dict[str, Any], custodian: str) -> tuple[str, dict[str, Any]] | None:
        """The custodian's latest integration verifier (its child, launched by the Lead's stage), if any."""
        children = sorted((i, inv) for i, inv in state["invocations"].items()
                          if inv.get("custodian") == custodian and inv.get("scope") == "integration")
        return children[-1] if children else None

    def _ended(self, state: dict[str, Any], child: tuple[str, dict[str, Any]]) -> str | None:
        """How the verifier's run ended, or None while it may still be live (or has no run yet: being launched).
        ``ended``: its supervisor recorded a terminal status. ``RUN_LOST``: no supervisor holds it any more, so it never
        will: its supervisor stopped reporting (``lost``), or none ever took custody past the launch's grace
        (``unconfirmed``). A lost run is routed like a failed one, never waited on with the lease held (§2.3)."""
        _inv_id, inv = child
        runs = inv.get("runs") or []
        if not runs:
            return None
        observed, _ = runlog.observed_status(runlog.run_dir(self.k.aew_root, runs[-1]["run"]))
        if observed in K.TERMINAL:
            return "ended"
        if observed == K.LOST or not runlog.possibly_live(observed, runs[-1].get("launched_at")):
            return RUN_LOST
        return None

    def route(self, credential: str, work_id: str, child: tuple[str, dict[str, Any]], *,
              lost: bool = False) -> dict[str, Any]:
        """Route the verifier's report, never accepting it (§2.3, verifier mode): a clean report releases the lease to
        VALIDATED, the candidate kept and the report named for the Lead's acceptance; anything else releases it to
        AWAITING_DISPOSITION. One custody transaction, which re-reads everything it decides on."""
        inv_id = child[0]
        with self.k.custody_txn(credential, "integrate.route") as ctx:
            state = ctx.state
            custodian = ctx.actor["invocation"]
            unit = self.units.unit(state, work_id)
            integ = unit.get("integration") or {}
            if integ.get("status") != "prepared" or (state["invocations"].get(inv_id) or {}).get(
                    "custodian") != custodian:
                raise IllegalTransition(f"{work_id}'s candidate changed while its verifier's report was routed",
                                        integration=integ.get("status"))
            report, why = (None, RUN_LOST) if lost else self._report(state, work_id, unit, inv_id)
            if report is not None and why is None:
                self.queue.release(state, work_id, to="VALIDATED", result="validated", validated=Q.validated_record(
                    integ, mode=V.VERIFIER, custodian=custodian, report=report["id"]))
                outcome = {"to": "VALIDATED", "report": report["id"]}
                ctx.summary = (f"{work_id}: verifier {inv_id}'s report {report['id']} is clean: the candidate is kept, "
                               "VALIDATED, for the Lead to accept and publish (routed, not accepted)")
            else:
                detail = {"verifier": inv_id, "report": (report or {}).get("id"), "why": why}
                self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="verification_not_clean",
                                   detail=detail)
                outcome = {"to": "AWAITING_DISPOSITION", **detail}
                ctx.summary = f"{work_id}: verifier {inv_id}'s run ended without a clean report ({why}): the entry " \
                              "waits for the Lead"
            ctx.refs.append(f"invocation:{custodian}")
            self.units.before_commit(ctx)
        return {"ok": True, "work_id": work_id, "routed": outcome, "revision": ctx.session.committed_revision}

    def _report(self, state: dict[str, Any], work_id: str, unit: dict[str, Any],
                inv_id: str) -> tuple[dict[str, Any] | None, str | None]:
        """The verifier's latest report and why it is not clean (None: clean). Clean is decided mechanically from the
        report (§2.3): a verification of the current candidate's snapshot, bound to it, every claim ``pass``, nothing
        policy marks ``requires_disposition`` (clause 6) and no open high anomaly on the Ticket (clause 7)."""
        reports = [e for e in E.scan(self.k.aew_root, work_id)[0]
                   if e["kind"] == "verification" and e["producer"].get("invocation") == inv_id]
        if not reports:
            return None, "no report"
        ev = max(reports, key=lambda e: e.get("seq") or 0)
        integ = unit["integration"]
        if (ev.get("verification") or {}).get("scope") != "integration":
            return ev, "not an integration-scope verification"
        if ev["evaluated_snapshot"]["relevant_inputs_fingerprint"] != \
                integ["candidate_snapshot"]["relevant_inputs_fingerprint"]:
            return ev, "it evaluated another snapshot than the candidate's"
        try:
            self.gates.require_bound_report(state, unit, ev, scope="integration")
        except AEWError as exc:
            return ev, f"not bound to the candidate ({exc.code})"
        claims = (ev.get("verification") or {}).get("claims") or []
        if ev.get("result") != "pass" or not claims or any(c.get("result") != "pass" for c in claims):
            return ev, f"its result is {ev.get('result')}"
        if DO.report_items(DO.marks(self.k.policy("gates")), ev):
            return ev, "it has items policy marks requires_disposition"
        if any(a.get("severity") == DO.HIGH and a.get("subject") == work_id
               for a in (state.get("anomalies") or {}).values()):
            return ev, "a high anomaly is open on the Ticket"
        return ev, None
