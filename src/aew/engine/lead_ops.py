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

from typing import Any

from aew import operator
from aew.engine.authority import issue_token, revoke, verify_offer
from aew.engine.base import EngineBase, TxnContext
from aew.engine.store import Transition
from aew.errors import IllegalTransition, PermissionDenied, StaleRevision
from aew.knowledge.records import format_id
from aew.util import render_frontmatter, utc_now

ACTIVE_INVOCATION_STATES = {"active"}


class LeadOps(EngineBase):
    # ------------------------------------------------------------------ helpers

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

    def _interrupt_invocations(self, state: dict[str, Any], reason: str, keep: set[str] = frozenset()) -> list[str]:
        """Revoke in-flight invocations (except ``keep``) and mark their Tickets INTERRUPTED."""
        interrupted = []
        for inv_id, inv in state["invocations"].items():
            if inv["status"] not in ACTIVE_INVOCATION_STATES or inv_id in keep:
                continue
            inv["status"] = "interrupted"
            revoke(state, inv["token_id"], reason)
            interrupted.append(inv_id)
            unit = state["work"].get(inv["work_unit"])
            if unit and unit["state"] not in {"DONE", "CANCELLED", "INTERRUPTED"}:
                unit["interrupted_from"] = unit["state"]
                unit["state"] = "INTERRUPTED"
                unit["state_reason"] = f"invocation {inv_id} interrupted: {reason}"
        return interrupted

    def _revoke_all_lead_credentials(self, state: dict[str, Any], reason: str) -> None:
        for token_id, record in state["tokens"].items():
            if record["kind"] in {"lead", "handoff_offer"}:
                revoke(state, token_id, reason)

    # ------------------------------------------------------------------ operations

    def lead_show(self) -> dict[str, Any]:
        state = self.store.read()
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
        with self.store.session() as s:
            if s.state["lead"]["status"] != "vacant":
                raise PermissionDenied(
                    "the Lead seat is held; a successor must use `aew lead handoff accept` (cooperative) "
                    "or an operator-authorized `aew lead takeover`",
                    generation=s.state["lead"]["generation"],
                )
            if expect_rev != s.revision:
                raise StaleRevision(f"expected revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            token = self._new_lead(s.state, session_label)
            actor = {"kind": "session", "session_label": session_label,
                     "generation": s.state["lead"]["generation"]}
            rev = s.commit(Transition(op="lead.acquire", actor=actor,
                                      summary=f"Lead authority acquired (generation {s.state['lead']['generation']})"),
                           expect_rev=expect_rev)
        return {"ok": True, "token": token, "generation": s.state["lead"]["generation"], "revision": rev}

    def lead_handoff_offer(
        self, *, token: str, expect_rev: int, note: str = "", carry_invocations: list[str] | None = None
    ) -> dict[str, Any]:
        carry = list(carry_invocations or [])
        with self.lead_txn(token, expect_rev, "lead.handoff.offer") as ctx:
            state = ctx.state
            for inv in carry:
                if state["invocations"].get(inv, {}).get("status") != "active":
                    raise IllegalTransition(f"cannot carry {inv}: not an active invocation")
            path = self._write_handoff(ctx, note, carry)
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
        with self.lead_txn(token, expect_rev, "lead.handoff.cancel", allow_pending=True) as ctx:
            lead = ctx.state["lead"]
            if lead["status"] != "handoff_pending":
                raise IllegalTransition("no handoff is pending")
            revoke(ctx.state, lead["handoff"]["offer_token_id"], "handoff cancelled")
            lead["status"] = "active"
            lead["handoff"] = None
            ctx.summary = "Lead handoff cancelled"
        return {"ok": True, "revision": ctx.session.committed_revision}

    def lead_handoff_accept(self, *, offer: str, expect_rev: int, session_label: str | None = None) -> dict[str, Any]:
        with self.store.session() as s:
            state = s.state
            offer_id = verify_offer(state, offer)
            if expect_rev != s.revision:
                raise StaleRevision(f"expected revision {expect_rev}, current is {s.revision}",
                                    expected=expect_rev, current=s.revision)
            self.check_manifest_pin(state)
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
                    state["tokens"][inv["token_id"]]["scope"]["generation"] = new_gen
            interrupted = self._interrupt_invocations(state, "not carried across Lead handoff", keep=carry)
            actor = {"kind": "session", "session_label": session_label, "generation": new_gen}
            ctx = TxnContext(session=s, actor=actor)
            decision = self.new_decision(
                ctx, "authority_transfer",
                f"Cooperative Lead handoff: generation {previous['generation']} -> {new_gen}",
                decided_by={"kind": "lead", "session_label": previous["session_label"],
                            "generation": previous["generation"], "accepted_by": session_label},
                reason=f"handoff record {handoff['record']}",
                evidence_refs=[handoff["record"]],
            )
            rev = s.commit(Transition(op="lead.handoff.accept", actor=actor,
                                      summary=f"Lead authority transferred by handoff ({decision})",
                                      refs=ctx.refs), expect_rev=expect_rev)
        return {"ok": True, "token": token, "generation": new_gen, "revision": rev,
                "carried_invocations": sorted(carry), "interrupted_invocations": interrupted,
                "decision": decision}

    def lead_takeover(self, *, expect_rev: int, reason: str, session_label: str | None = None) -> dict[str, Any]:
        if not reason or not reason.strip():
            raise PermissionDenied("a takeover reason is required for provenance")
        snapshot = self.store.read()
        lead = snapshot["lead"]
        if lead["status"] == "vacant":
            raise IllegalTransition("the Lead seat is vacant; use `aew lead acquire`")
        if expect_rev != snapshot["revision"]:
            raise StaleRevision(f"expected revision {expect_rev}, current is {snapshot['revision']}",
                                expected=expect_rev, current=snapshot["revision"])
        # Authorization is obtained by the engine from the controlling terminal. There is
        # deliberately no parameter, flag or environment variable that can supply it.
        auth = operator.authorize(
            f"Project '{self.project_id}': TAKE OVER Lead authority\n"
            f"  current holder : generation {lead['generation']} ({lead.get('session_label') or 'unlabelled'})\n"
            f"  new holder     : generation {lead['generation'] + 1} ({session_label or 'unlabelled'})\n"
            f"  reason         : {reason}\n"
            "All current Lead and in-flight invocation credentials will be revoked."
        )
        with self.store.session() as s:
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
            decision = self.new_decision(
                ctx, "authority_transfer",
                f"Operator-authorized Lead takeover: generation {previous['generation']} -> {new_gen}",
                decided_by={"kind": "operator", "authorized_by": auth["authorized_by"],
                            "new_session_label": session_label},
                reason=reason,
                body=f"Superseded holder: {previous}\nInterrupted invocations: {interrupted or 'none'}\n",
            )
            rev = s.commit(Transition(op="lead.takeover", actor=actor, reason=reason,
                                      summary=f"Operator-authorized takeover ({decision})", refs=ctx.refs),
                           expect_rev=snapshot["revision"])
        return {"ok": True, "token": token, "generation": new_gen, "revision": rev,
                "interrupted_invocations": interrupted, "decision": decision}

    def lead_release(self, *, token: str, expect_rev: int) -> dict[str, Any]:
        with self.lead_txn(token, expect_rev, "lead.release") as ctx:
            state = ctx.state
            active = [i for i, inv in state["invocations"].items() if inv["status"] == "active"]
            if active:
                raise IllegalTransition("cannot release Lead authority with active invocations", active=active)
            revoke(state, state["lead"]["token_id"], "released")
            state["lead"].update(status="vacant", token_id=None, session_label=None, handoff=None)
            ctx.summary = "Lead authority released"
        return {"ok": True, "revision": ctx.session.committed_revision}

    # ------------------------------------------------------------------ handoff record

    def _write_handoff(self, ctx: TxnContext, note: str, carry: list[str]) -> str:
        from aew.knowledge.render import work_graph_lines

        state = ctx.state
        state["counters"]["handoff"] = state["counters"].get("handoff", 0) + 1
        hid = format_id("H", state["counters"]["handoff"])
        in_flight = [f"{i} ({inv['role']} for {inv['work_unit']})"
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
