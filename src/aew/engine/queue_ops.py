"""The integration queue and its lease (M4-D slice D3; M4 report §2.6, the M4-D plan §1.2; ADR-0004 amendment).

Every COMMIT_READY mutating Ticket has one live queue entry in control state (``queue.entries``), served FIFO by its
``seq``. At most one entry holds the lease (``queue.lease``), and only the lease holder prepares, is post-integration
verified, and publishes. Queue state is scheduling, never eligibility: the integration's legality is the
``integrate.prepare`` dispatch decision, computed at every grant, and every existing check of ``prepare`` and
``publish`` still applies under the lease.

**The custodian.** A lease is held by a dedicated engine custody invocation, ``kind: integration_attempt`` (operator,
2026-10-04): executed by the engine, with no harness, no model, no role and no credential. It is created in the
transaction that grants the lease and ends in the one that releases it; the post-integration verifier is its child
(``custodian``). It is not a role invocation and is never modelled as one (ADR-0003 amendment).

**Death means reconciliation.** When the custodian stops being active while its lease is held (a takeover, a handoff
that did not carry it, an explicit cancel), the lease is marked ``reconcile`` in the same transaction and its
children are cancelled. No timeout releases a lease: ``aew integrate reconcile <T>`` does, after proving what was
published (an interrupted publish finishes through ADR-0004's reconcile first).

**Retirement.** An entry whose Ticket is no longer COMMIT_READY (DONE, CANCELLED, back to RUNNING, VERIFICATION_FAILED,
INTERRUPTED, ...) is retired in the same transaction: it leaves the hot queue for its unit's ``queue_history``, so
archival (ADR-0011) moves it with the unit. A lease it held is released; nothing can have been published unless the
Ticket is DONE, because a publish in progress refuses every other state change (``Integration.before_state_change``).

The queue is kept consistent by ``sync``, a transaction finalizer run before archival, so every route that changes a
Ticket's state (the Lead's own commits included, which call it directly) enqueues and retires in the same commit.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine.dispatch import GuardRegistration as DispatchGuard
from aew.engine.dispatch import blocker_from, checked
from aew.errors import IllegalTransition, IntegrityError, LeaseHeld, LeaseNotHeld, LeaseReconcileRequired, QueueOrder
from aew.knowledge.records import format_id
from aew.util import dump_yaml, load_yaml, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext
    from aew.engine.ports import InvocationsPort

LIVE = ("QUEUED", "LEASED", "DEFERRED", "AWAITING_DISPOSITION")
CHECKOUT_SYNC_LOCK = "local/checkout-sync.lock"  # AEW-INV-ISO-004
CUSTODIAN = "integration_attempt"


def empty() -> dict[str, Any]:
    return {"next_seq": 1, "lease": None, "entries": {}}


def is_custodian(inv: dict[str, Any] | None) -> bool:
    return (inv or {}).get("kind") == CUSTODIAN


def entry_of(state: dict[str, Any], work_id: str) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    """The live queue entry of ``work_id``, if any."""
    for qid, entry in ((state.get("queue") or {}).get("entries") or {}).items():
        if entry["work"] == work_id:
            return qid, entry
    return None, None


def lease_of(state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    """The lease, when ``work_id``'s entry holds it."""
    lease = (state.get("queue") or {}).get("lease")
    qid, _ = entry_of(state, work_id)
    return lease if lease and qid and lease["entry"] == qid else None


def _queued_ticket(unit: dict[str, Any]) -> bool:
    return unit.get("kind") == "ticket" and bool(unit.get("mutating")) and unit.get("state") == "COMMIT_READY"


class Queue:
    """The integration queue: entries, the lease and its custodian, and the finalizer that keeps them consistent."""

    def __init__(self, k: Kernel, *, invocations: InvocationsPort) -> None:
        self.k = k
        self.invocations = invocations
        # Whether a Ticket's integration is legal now (raises when not): ``Integration.require_legal``, set by the
        # composition root. The order guard asks it of every earlier entry.
        self.legal: Callable[[dict[str, Any], str], None] | None = None

    # ------------------------------------------------------------------ consistency (a transaction finalizer)

    def finalize(self, ctx: TxnContext) -> None:
        self.sync(ctx.state)

    def sync(self, state: dict[str, Any]) -> None:
        """Enqueue every COMMIT_READY mutating Ticket without a live entry, retire every entry whose Ticket left
        COMMIT_READY, and mark a lease whose custodian is no longer active for reconciliation. Idempotent."""
        if state.get("schema") != "aew/control/v2":
            return
        if "queue" not in state:
            if not any(_queued_ticket(u) for u in state["work"].values()):
                return  # a project that never queued anything keeps its control state unchanged
            state["queue"] = empty()
        queue = state["queue"]
        live = {e["work"] for e in queue["entries"].values()}
        for wid in sorted(w for w, u in state["work"].items() if _queued_ticket(u) and w not in live):
            self._enqueue(state, wid)
        for qid in sorted(queue["entries"]):
            entry = queue["entries"][qid]
            unit = state["work"].get(entry["work"])
            if unit is None or not _queued_ticket(unit):
                self._retire(state, qid, unit)
        lease = queue["lease"]
        if lease and lease["reconcile"] is None:
            custodian = state["invocations"].get(lease["custodian"]) or {}
            if custodian.get("status") != "active":
                lease["reconcile"] = {"reason": f"custodian {lease['custodian']} is {custodian.get('status')}",
                                      "at": utc_now()}
                self._end_children(state, lease["custodian"], "cancelled")

    def _enqueue(self, state: dict[str, Any], wid: str) -> None:
        queue = state["queue"]
        state["counters"]["queue_entry"] = state["counters"].get("queue_entry", 0) + 1
        qid = format_id("Q", state["counters"]["queue_entry"])
        queue["entries"][qid] = {
            "work": wid, "seq": queue["next_seq"], "state": "QUEUED",
            "commit_ready_seq": state["work"][wid].get("commit_ready_seq", 0), "enqueued_at": utc_now(),
            "attempts": [], "rebuilds_used": 0, "disposition": None}
        queue["next_seq"] += 1

    def _retire(self, state: dict[str, Any], qid: str, unit: dict[str, Any] | None) -> None:
        queue = state["queue"]
        entry = queue["entries"].pop(qid)
        to = (unit or {}).get("state")
        lease = queue["lease"]
        if lease and lease["entry"] == qid:
            done = to == "DONE"
            self._end_lease(state, entry, result="integrated" if done else f"retired ({to})",
                            custodian_status="completed" if done else "cancelled")
        if unit is not None:
            unit.setdefault("queue_history", []).append(
                {"id": qid, **entry, "state": "RETIRED", "retired": {"at": utc_now(), "reason": f"Ticket is {to}"}})

    # ------------------------------------------------------------------ the dispatch guards of integrate.prepare

    def dispatch_guards(self) -> list[DispatchGuard]:
        return [DispatchGuard("queue.order", self._g_order), DispatchGuard("queue.lease", self._g_lease)]

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        """The queue as ``sync`` would leave it, without changing ``state`` (guards and reads)."""
        import copy

        probe = {k: state[k] for k in ("schema", "work", "invocations")} | {
            "counters": dict(state["counters"]), "queue": copy.deepcopy(state.get("queue") or empty())}
        probe["work"] = copy.deepcopy(state["work"])
        probe["invocations"] = copy.deepcopy(state["invocations"])
        self.sync(probe)
        return probe["queue"]

    def _g_order(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        """FIFO among runnable entries: no earlier QUEUED entry whose integration is legal now. DEFERRED and
        AWAITING_DISPOSITION entries never hold up an independent one (no head-of-line blocking)."""
        queue = self.view(state)
        qid, entry = next(((q, e) for q, e in queue["entries"].items() if e["work"] == work_id), (None, None))
        if entry is None:
            return blocker_from(IllegalTransition(f"{work_id} has no integration queue entry"))
        facts["queue_entry"] = qid
        if entry["state"] in ("DEFERRED", "AWAITING_DISPOSITION"):
            why = (entry.get("disposition") or {}).get("reason")
            return blocker_from(IllegalTransition(
                f"{work_id}'s queue entry {qid} is {entry['state']}" + (f" ({why})" if why else "")
                + ": the Lead disposes of it first (return the Ticket to RUNNING for a new implementation attempt, "
                "or REPLAN_REQUIRED)", entry=qid, state=entry["state"]))
        if entry["state"] == "LEASED":
            return None
        for other_id, other in sorted(queue["entries"].items(), key=lambda kv: kv[1]["seq"]):
            if other["seq"] >= entry["seq"]:
                break
            if other["state"] == "QUEUED" and self._runnable(state, other["work"]):
                return blocker_from(QueueOrder(
                    f"{other['work']} is ahead of {work_id} in the integration queue ({other_id}, seq {other['seq']}) "
                    f"and can integrate now: prepare it first", ahead=other["work"], entry=other_id))
        return None

    def _runnable(self, state: dict[str, Any], work_id: str) -> bool:
        def check() -> None:
            assert self.legal is not None
            self.legal(state, work_id)
        return checked(check) is None

    def _g_lease(self, state: dict[str, Any], work_id: str, facts: dict[str, Any]) -> Any:
        lease = (state.get("queue") or {}).get("lease")
        if lease is None:
            return None
        holder = ((state.get("queue") or {}).get("entries") or {}).get(lease["entry"]) or {}
        if lease["reconcile"] is not None:
            return blocker_from(LeaseReconcileRequired(
                f"the integration lease of {holder.get('work')} lost its custodian ({lease['reconcile']['reason']}): "
                f"run `aew integrate reconcile {holder.get('work')}` first", holder=holder.get("work"),
                entry=lease["entry"]))
        if lease["entry"] != facts.get("queue_entry"):
            return blocker_from(LeaseHeld(
                f"{holder.get('work')} holds the integration lease ({lease['entry']}): it publishes, or leaves "
                "COMMIT_READY, first", holder=holder.get("work"), entry=lease["entry"]))
        return None

    # ------------------------------------------------------------------ grant and release

    def grant(self, ctx: TxnContext, work_id: str) -> str:
        """The lease for ``work_id``'s entry (after an allowed ``integrate.prepare`` decision): its custodian. A
        second prepare under a lease the entry already holds keeps the lease and the custodian."""
        state = ctx.state
        self.sync(state)
        qid, entry = entry_of(state, work_id)
        assert qid is not None and entry is not None  # the decision's queue.order guard found it
        lease = state["queue"]["lease"]
        if lease is not None:
            if lease["entry"] != qid:
                raise LeaseHeld("the integration lease is held by another entry", entry=lease["entry"])
            return lease["custodian"]
        state["counters"]["invocation"] = state["counters"].get("invocation", 0) + 1
        custodian = format_id("INV", state["counters"]["invocation"])
        now = utc_now()
        state["invocations"][custodian] = {
            "kind": CUSTODIAN, "execution": "engine", "work_unit": work_id, "status": "active", "created_at": now,
            "generation": state["lead"]["generation"], "queue_entry": qid}
        state["work"][work_id]["invocations"].append(custodian)
        state["queue"]["lease"] = {"entry": qid, "custodian": custodian, "generation": state["lead"]["generation"],
                                   "granted_at": now, "reconcile": None}
        entry["state"] = "LEASED"
        entry["attempts"].append({"custodian": custodian, "granted_at": now, "integration_attempt": None,
                                  "base": None, "candidate": None, "result": None, "ended_at": None})
        ctx.refs.append(f"invocation:{custodian}")
        return custodian

    def record_attempt(self, state: dict[str, Any], work_id: str, integration: dict[str, Any]) -> None:
        """What the lease's current attempt built (``prepare``)."""
        lease = lease_of(state, work_id)
        if lease is None:
            return
        attempt = state["queue"]["entries"][lease["entry"]]["attempts"][-1]
        attempt.update(integration_attempt=integration.get("attempt"), base=integration.get("base"),
                       candidate=integration.get("candidate"), result=integration.get("status"))

    def release(self, state: dict[str, Any], work_id: str, *, to: str, result: str,
                detail: dict[str, Any] | None = None, custodian_status: str = "completed") -> None:
        """End the lease of ``work_id``'s entry: back to QUEUED (same ``seq``) or to AWAITING_DISPOSITION."""
        qid, entry = entry_of(state, work_id)
        if entry is None or (state["queue"]["lease"] or {}).get("entry") != qid:
            return
        self._end_lease(state, entry, result=result, custodian_status=custodian_status)
        entry["state"] = to
        entry["disposition"] = {"reason": result, "at": utc_now(), **({"detail": detail} if detail else {})} \
            if to == "AWAITING_DISPOSITION" else None

    def _end_lease(self, state: dict[str, Any], entry: dict[str, Any], *, result: str, custodian_status: str) -> None:
        lease = state["queue"]["lease"]
        custodian = lease["custodian"]
        attempt = entry["attempts"][-1] if entry["attempts"] else None
        if attempt is not None and attempt["ended_at"] is None:
            attempt.update(result=result, ended_at=utc_now())
        inv = state["invocations"].get(custodian)
        if inv and inv["status"] == "active":
            inv["status"] = custodian_status
        self._end_children(state, custodian, "cancelled")
        state["queue"]["lease"] = None

    def _end_children(self, state: dict[str, Any], custodian: str, status: str) -> None:
        """A dead custodian's children lose their authority with it."""
        for inv_id, inv in state["invocations"].items():
            if inv.get("custodian") == custodian and inv["status"] == "active":
                self.invocations.complete_invocation(state, inv_id, status)

    # ------------------------------------------------------------------ AEW-INV-ISO-004: the checkout-sync lock

    def checkout_sync_lock_path(self) -> Path:
        return self.k.aew_root / CHECKOUT_SYNC_LOCK

    def checkout_sync_lock(self, state: dict[str, Any], *, lease: dict[str, Any] | None,
                           work_id: str) -> AbstractContextManager[None]:
        return self._checkout_sync_lock(state, lease=lease, work_id=work_id)

    @contextmanager
    def _checkout_sync_lock(self, state: dict[str, Any], *, lease: dict[str, Any] | None,
                            work_id: str) -> Iterator[None]:
        """Serialize syncing a published commit into the authoritative checkout (``AEW-INV-ISO-004``).

        The lock shares the lease custodian's identity, not its lifetime: it is taken for the bounded sync only and
        released right after. It is serialization only, never eligibility or authority (M4-B6): taking it is the
        last step of a publish that every other check already allowed, and holding it lets nothing else happen. A
        holder left by a crash is a stale owner, reconciled here before the lock is taken again: its custodian is
        no longer active (or is this one, retrying), and the sync it was doing is idempotent and re-verified."""
        path = self.checkout_sync_lock_path()
        holder = {"custodian": (lease or {}).get("custodian"), "entry": (lease or {}).get("entry"), "work": work_id,
                  "pid": os.getpid(), "at": utc_now()}
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            found = self._lock_holder(path)
            owner = state["invocations"].get(found.get("custodian") or "") or {}
            if owner.get("status") == "active" and found.get("custodian") != holder["custodian"]:
                raise IntegrityError("the authoritative checkout's sync lock is held by another active integration "
                                     "custodian; nothing was synced", holder=found) from None
            path.unlink(missing_ok=True)  # the stale owner is reconciled: its sync is redone below
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(dump_yaml(holder))
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    @staticmethod
    def _lock_holder(path: Path) -> dict[str, Any]:
        try:
            found = load_yaml(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    # ------------------------------------------------------------------ the lease's checks for publish and verify

    def require_live_lease(self, state: dict[str, Any], work_id: str, what: str) -> dict[str, Any]:
        lease = lease_of(state, work_id)
        if lease is None:
            held = (state.get("queue") or {}).get("lease")
            holder = ((state.get("queue") or {}).get("entries") or {}).get((held or {}).get("entry") or "") or {}
            raise LeaseNotHeld(f"{what} needs {work_id}'s integration lease"
                               + (f"; {holder.get('work')} holds it" if held else "; run `aew integrate prepare` "
                                  f"{work_id}"), holder=holder.get("work"))
        if lease["reconcile"] is not None:
            raise LeaseReconcileRequired(
                f"{work_id}'s integration lease lost its custodian ({lease['reconcile']['reason']}): run `aew "
                f"integrate reconcile {work_id}`", entry=lease["entry"])
        return lease
