"""Lead authority lifecycle (WC §5 single-authoritative-Lead + crash-safe authority rules).

* acquire   — only when the seat is vacant; starts a new authority generation.
* handoff   — cooperative: the current Lead offers (one-time secret), a successor
              that has reconstructed state accepts; generation advances.
* takeover  — non-cooperative (prior Lead lost): requires out-of-band operator
              authorization at the controlling terminal (D-op-3). A reason is
              recorded for provenance but never authorizes anything.
* release   — the current Lead vacates the seat cleanly.

Every authority change atomically advances the generation and revokes all
superseded credentials, so a superseded Lead can never overwrite newer state.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from typing import TYPE_CHECKING, Any

from aew import operator
from aew.engine.authority import issue_token, revoke, verify_offer
from aew.engine.base import TxnContext
from aew.engine.store import Transition
from aew.errors import IllegalTransition, PermissionDenied, StaleRevision
from aew.knowledge.records import format_id
from aew.roles import NON_MUTATING_EXECUTORS
from aew.util import render_frontmatter, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ArchivePort, QueuePort

ACTIVE_INVOCATION_STATES = {"active"}
# The invocation each phase is waiting on (role, scope). Only when *that* invocation is lost is the
# Ticket's state in doubt; every other state is already determined by ingested evidence or a Lead
# decision, and interruption must not erase the obligation it carries — e.g. VERIFICATION_FAILED
# still requires the Lead's classification (review 2026-09-26 M5; ADR-0003 amendment).
PHASE_DRIVERS = {
    "ASSIGNED": ("implementer", "ticket"),
    "RUNNING": ("implementer", "ticket"),
    "REVIEW_PENDING": ("reviewer", "ticket"),
    "VERIFY_PENDING": ("verifier", "ticket"),
    "COMMIT_READY": ("verifier", "integration"),  # only while the candidate awaits validation (prepared)
}


class Lead:
    """Lead authority lifecycle: acquire, handoff, takeover, release, handoff records."""

    def __init__(self, k: Kernel, *, archive: ArchivePort, queue: QueuePort) -> None:
        self.k = k
        self.archive = archive
        self.queue = queue

    @staticmethod
    def _seat_held(state: dict[str, Any]) -> PermissionDenied:
        """Why ``lead acquire`` is refused, and the way on (register V2). The common case is a Lead wrapper that exited
        while the seat was held: its credential went with it, so the seat cannot be re-acquired or handed off, and an
        operator-authorized takeover is the path. Saying which invocations a takeover interrupts lets the operator
        decide it with the cost in view."""
        lead = state["lead"]
        generation = lead["generation"]
        active = sorted(i for i, inv in state["invocations"].items()
                        if inv["status"] == "active" and inv.get("kind") != "integration_attempt")
        holder = f"generation {generation}" + (f", session {lead['session_label']!r}" if lead.get("session_label")
                                               else "") + (f", acquired {lead['acquired_at']}"
                                                           if lead.get("acquired_at") else "")
        interrupts = (f"it interrupts the active invocation(s) {', '.join(active)}" if active
                      else "no invocation is active, so it interrupts nothing")
        lease = (state.get("queue") or {}).get("lease")
        if lease:
            work = ((state["queue"]["entries"].get(lease["entry"])) or {}).get("work")
            interrupts += f"; the integration lease of {work} is then reconciled with `aew integrate reconcile {work}`"
        return PermissionDenied(
            f"the Lead seat is held ({holder}). A successor takes it over cooperatively with `aew lead handoff "
            f"accept`. If the holding session is gone (its wrapper exited or crashed and its credential went with "
            f"it), the seat cannot be re-acquired: run `aew lead takeover` at an operator terminal. It starts "
            f"generation {generation + 1}, revokes the old credential, and {interrupts}",
            generation=generation, session_label=lead.get("session_label"), acquired_at=lead.get("acquired_at"),
            active_invocations=active, next="aew lead takeover")

    def _new_lead(self, state: dict[str, Any], session_label: str | None) -> str:
        lead = state["lead"]
        lead["generation"] += 1
        token = issue_token(state, "lead", {"generation": lead["generation"], "session_label": session_label})
        lead.update(
            status="active",
            session_label=session_label,
            token_id=token.split(".")[1],
            acquired_at=utc_now(),
            handoff=None,
        )
        return token

    @staticmethod
    def _phase_waits_on(unit: dict[str, Any], inv: dict[str, Any]) -> bool:
        if unit["kind"] != "ticket":
            return False  # a parent's phase is derived; losing a parent reviewer/verifier leaves a gate missing
        if not unit.get("mutating"):
            # Non-mutating Tickets (ADR-0008): the phase waits on the current attempt's executor, or on the
            # reviewer/verifier of its accepted record; all of them work in observation scope.
            waits = {"ASSIGNED": NON_MUTATING_EXECUTORS, "RUNNING": NON_MUTATING_EXECUTORS,
                     "REVIEW_PENDING": {"reviewer"}, "VERIFY_PENDING": {"verifier"}}.get(unit["state"], set())
            if inv.get("role") not in waits or inv.get("scope") != "observation":
                return False
            return inv.get("role") not in NON_MUTATING_EXECUTORS or \
                inv.get("attempt") == (unit.get("execution") or {}).get("attempt")
        driver = PHASE_DRIVERS.get(unit["state"])
        if driver != (inv.get("role"), inv.get("scope") or "ticket"):
            return False
        return unit["state"] != "COMMIT_READY" or (unit.get("integration") or {}).get("status") == "prepared"

    def _interrupt_invocations(self, state: dict[str, Any], reason: str,
                               keep: AbstractSet[str] = frozenset()) -> list[str]:
        """Revoke in-flight invocations (except ``keep``).

        A Ticket becomes INTERRUPTED only if its current phase is waiting on the lost invocation;
        otherwise its state is retained and the revocation is recorded in its history.
        """
        interrupted = []
        for inv_id, inv in state["invocations"].items():
            if inv["status"] not in ACTIVE_INVOCATION_STATES or inv_id in keep:
                continue
            inv["status"] = "interrupted"
            if inv.get("token_id"):  # an engine custody invocation holds no credential (M4-D)
                revoke(state, inv["token_id"], reason)
            if (inv.get("observation") or {}).get("status") == "active":
                inv["observation"]["status"] = "retired"  # the attempt ends; its worktree is pruned later
            interrupted.append(inv_id)
            unit = state["work"].get(inv["work_unit"])
            if not unit:
                continue
            note = f"invocation {inv_id} ({inv.get('role') or inv.get('kind')}) interrupted: {reason}"
            if self._phase_waits_on(unit, inv):
                unit.setdefault("history", []).append(
                    {"from": unit["state"], "to": "INTERRUPTED", "at": utc_now(), "reason": note})
                unit["interrupted_from"] = unit["state"]
                unit["state"] = "INTERRUPTED"
                unit["state_reason"] = note
            else:
                unit.setdefault("history", []).append(
                    {"from": unit["state"], "to": unit["state"], "at": utc_now(), "event": "invocation_interrupted",
                     "reason": f"{note}; state retained (determined by accepted evidence or a Lead decision)"})
        return interrupted

    def _revoke_all_lead_credentials(self, state: dict[str, Any], reason: str) -> None:
        for token_id, record in state["tokens"].items():
            if record["kind"] in {"lead", "handoff_offer"}:
                revoke(state, token_id, reason)

    def lead_show(self) -> dict[str, Any]:
        state = self.k.store.read()
        lead = state["lead"]
        return {
            "revision": state["revision"],
            "status": lead["status"],
            "generation": lead["generation"],
            "session_label": lead.get("session_label"),
            "acquired_at": lead.get("acquired_at"),
            "handoff_pending": lead["status"] == "handoff_pending",
        }

    def lead_acquire(self, *, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        with self.k.store.session() as s:
            if s.state["lead"]["status"] != "vacant":
                raise self._seat_held(s.state)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            token = self._new_lead(s.state, session_label)
            actor = {"kind": "session", "session_label": session_label,
                     "generation": s.state["lead"]["generation"]}
            self.queue.sync(s.state)
            projected = self.archive.end_lead_credentials(s)
            rev = s.commit(Transition(op="lead.acquire", actor=actor,
                                      summary=f"Lead authority acquired (generation {s.state['lead']['generation']})"),
                           expect_rev=expect_rev, state=projected)
        return {"ok": True, "token": token, "generation": s.state["lead"]["generation"], "revision": rev}

    def lead_handoff_offer(
        self, *, token: str, expect_rev: int, note: str = "", carry_invocations: list[str] | None = None
    ) -> dict[str, Any]:
        carry = list(carry_invocations or [])
        with self.k.lead_txn(token, expect_rev, "lead.handoff.offer") as ctx:
            state = ctx.state
            for inv in carry:
                if state["invocations"].get(inv, {}).get("status") != "active":
                    raise IllegalTransition(f"cannot carry {inv}: not an active invocation")
            path = self.write_handoff(ctx, note, carry)
            offer = issue_token(state, "handoff_offer", {"from_generation": state["lead"]["generation"]})
            state["lead"]["status"] = "handoff_pending"
            state["lead"]["handoff"] = {
                "offer_token_id": offer.split(".")[1],
                "offered_at": utc_now(),
                "record": path,
                "carry_invocations": carry,
            }
            ctx.summary = "Lead handoff offered"
        return {"ok": True, "offer": offer, "handoff_record": path, "revision": ctx.session.committed_revision}

    def lead_handoff_cancel(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "lead.handoff.cancel", allow_pending=True) as ctx:
            lead = ctx.state["lead"]
            if lead["status"] != "handoff_pending":
                raise IllegalTransition("no handoff is pending")
            revoke(ctx.state, lead["handoff"]["offer_token_id"], "handoff cancelled")
            lead["status"] = "active"
            lead["handoff"] = None
            ctx.summary = "Lead handoff cancelled"
        return {"ok": True, "revision": ctx.session.committed_revision}

    def lead_handoff_accept(self, *, offer: str, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        with self.k.store.session() as s:
            state = s.state
            offer_id = verify_offer(state, offer)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            self.k.check_manifest_pin(state)
            previous = {"generation": state["lead"]["generation"], "session_label": state["lead"]["session_label"]}
            handoff = state["lead"]["handoff"]
            carry = set(handoff["carry_invocations"])
            self._revoke_all_lead_credentials(state, "superseded by cooperative handoff")
            revoke(state, offer_id, "handoff accepted")
            token = self._new_lead(state, session_label)
            new_gen = state["lead"]["generation"]
            for inv_id in carry:
                inv = state["invocations"][inv_id]
                if inv["status"] == "active":
                    inv["generation"] = new_gen
                    if inv.get("token_id"):  # an engine custody invocation holds no credential (M4-D)
                        state["tokens"][inv["token_id"]]["scope"]["generation"] = new_gen
            interrupted = self._interrupt_invocations(state, "not carried across Lead handoff", keep=carry)
            actor = {"kind": "session", "session_label": session_label, "generation": new_gen}
            ctx = TxnContext(session=s, actor=actor)
            decision = self.k.new_decision(
                ctx, "authority_transfer",
                f"Cooperative Lead handoff: generation {previous['generation']} -> {new_gen}",
                decided_by={"kind": "lead", "session_label": previous["session_label"],
                            "generation": previous["generation"], "accepted_by": session_label},
                reason=f"handoff record {handoff['record']}",
                evidence_refs=[handoff["record"]],
            )
            self.queue.sync(s.state)  # a custodian the handoff did not carry is dead: its lease awaits reconcile
            projected = self.archive.end_lead_credentials(s)
            rev = s.commit(Transition(op="lead.handoff.accept", actor=actor,
                                      summary=f"Lead authority transferred by handoff ({decision})",
                                      refs=ctx.refs, events=ctx.events), expect_rev=expect_rev, state=projected)
        return {"ok": True, "token": token, "generation": new_gen, "revision": rev,
                "carried_invocations": sorted(carry), "interrupted_invocations": interrupted,
                "decision": decision}

    def lead_takeover(self, *, expect_rev: int, reason: str, session_label: str | None = None) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise PermissionDenied("a takeover reason is required for provenance")
        snapshot = self.k.store.read()
        lead = snapshot["lead"]
        if lead["status"] == "vacant":
            raise IllegalTransition("the Lead seat is vacant; use `aew lead acquire`")
        if expect_rev != snapshot["revision"]:
            raise StaleRevision(f"expected revision {expect_rev}, current is {snapshot['revision']}",
                                expected=expect_rev, current=snapshot["revision"])
        # Authorization is obtained by the engine from the controlling terminal. There is
        # deliberately no parameter, flag or environment variable that can supply it.
        auth = operator.authorize(
            f"Project '{self.k.project_id}': TAKE OVER Lead authority\n"
            f"  current holder : generation {lead['generation']} ({lead.get('session_label') or 'unlabelled'})\n"
            f"  new holder     : generation {lead['generation'] + 1} ({session_label or 'unlabelled'})\n"
            f"  reason         : {reason}\n"
            "All current Lead and in-flight invocation credentials will be revoked."
        )
        with self.k.store.session() as s:
            state = s.state
            if s.revision != snapshot["revision"] or state["lead"]["generation"] != lead["generation"]:
                raise StaleRevision("control state changed during operator authorization; re-run takeover",
                                    expected=snapshot["revision"], current=s.revision)
            previous = {"generation": state["lead"]["generation"], "session_label": state["lead"]["session_label"]}
            self._revoke_all_lead_credentials(state, "superseded by operator-authorized takeover")
            token = self._new_lead(state, session_label)
            new_gen = state["lead"]["generation"]
            interrupted = self._interrupt_invocations(state, "Lead takeover")
            actor = {"kind": "operator", "authorized_by": auth["authorized_by"], "session_label": session_label,
                     "generation": new_gen}
            ctx = TxnContext(session=s, actor=actor)
            decision = self.k.new_decision(
                ctx, "authority_transfer",
                f"Operator-authorized Lead takeover: generation {previous['generation']} -> {new_gen}",
                decided_by={"kind": "operator", "authorized_by": auth["authorized_by"],
                            "new_session_label": session_label},
                reason=reason,
                body=f"Superseded holder: {previous}\nInterrupted invocations: {interrupted or 'none'}\n",
            )
            self.queue.sync(s.state)  # the takeover ended every custodian: their leases await reconcile
            projected = self.archive.end_lead_credentials(s)
            rev = s.commit(Transition(op="lead.takeover", actor=actor, reason=reason,
                                      summary=f"Operator-authorized takeover ({decision})", refs=ctx.refs,
                                      events=ctx.events),
                           expect_rev=snapshot["revision"], state=projected)
        return {"ok": True, "token": token, "generation": new_gen, "revision": rev,
                "interrupted_invocations": interrupted, "decision": decision}

    def lead_release(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        with self.k.lead_txn(token, expect_rev, "lead.release") as ctx:
            state = ctx.state
            active = [i for i, inv in state["invocations"].items() if inv["status"] == "active"]
            if active:
                raise IllegalTransition("cannot release Lead authority with active invocations", active=active)
            revoke(state, state["lead"]["token_id"], "released")
            state["lead"].update(status="vacant", token_id=None, session_label=None, handoff=None)
            ctx.summary = "Lead authority released"
        return {"ok": True, "revision": ctx.session.committed_revision}

    def write_handoff(self, ctx: TxnContext, note: str, carry: list[str]) -> str:
        from aew.knowledge.render import work_graph_lines

        state = ctx.state
        state["counters"]["handoff"] = state["counters"].get("handoff", 0) + 1
        hid = format_id("H", state["counters"]["handoff"])
        ctx.events.append({"kind": "handoff.recorded", "id": hid})
        in_flight = [f"{i} ({inv.get('role') or inv.get('kind')} for {inv['work_unit']})"
                     for i, inv in sorted(state["invocations"].items()) if inv["status"] == "active"]
        meta = {
            "schema": "aew/handoff/v1",
            "id": hid,
            "at": utc_now(),
            "from": {"generation": state["lead"]["generation"], "session_label": state["lead"]["session_label"]},
            "base_revision": ctx.session.revision,
            "carry_invocations": carry,
        }
        body = "\n".join([
            f"# Handoff {hid}",
            "",
            "## Work graph at handoff",
            "",
            "```text",
            *work_graph_lines(state),
            "```",
            "",
            "## In-flight invocations",
            "",
            *(f"- {x}" for x in in_flight or ["none"]),
            "",
            "## Next action / notes from the outgoing Lead",
            "",
            note.strip() or "(none recorded)",
            "",
            "This summary does not replace the artifacts it references; reconstruct with `aew resume`.",
            "",
        ])
        path = f"state/handoffs/{hid}.md"
        ctx.session.write(path, render_frontmatter(meta, body))
        ctx.refs.append(path)
        state["latest_handoff"] = path
        return path
