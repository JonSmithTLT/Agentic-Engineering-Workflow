"""The four D-01 0.3.4 reads of the STG-02 journey, built from the two providers of :mod:`aew.stg02.world`.

Every read is for the authenticated recipient only: a member it may not see changes no count, page, cursor or error.
Every consequential fact carries a stamp naming its owner (``FieldSource`` where a resource mixes owners, pinned as
``00-DESIGN/owner-pins.json`` says), and none is qualified (:mod:`aew.stg02.wire`). So no read here is ever
``provided`` with ``source_qualified`` continuity, no list claims ``qualified_scoped`` membership, and no continuation
axis shows ``ok`` or ``blocked``: the wire allows those only on a qualified owner fact (``SourceStamp``,
``ReadResult`` and ``FR_OwnerAxis``). That is the honest product state of the slice today, not an error.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Any

from aew.stg02 import wire as W
from aew.stg02.ledger import Ledger
from aew.stg02.world import AXES, WAITING_STATES, EngineSource, Fixture, SourceUnavailable

LIMIT_DEFAULT, LIMIT_MAX = 25, 100
OWNER_OPS_PAGE = 25
O01_OWNERS = ("HEB", "ADC", "IF13", "RESOURCE_POLICY_ISSUER")
ENGINE_ISSUER = "aew:engine-state"
RUNNING = ("starting", "running")


class ReadProblem(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Reads:
    def __init__(self, fx: Fixture, engine: EngineSource | None, ledger: Ledger) -> None:
        self.fx = fx
        self.engine = engine
        self.ledger = ledger
        self._cursor_key = secrets.token_bytes(32)  # cursors are this process's; a restart makes them stale (409)

    # ------------------------------------------------------------------ shared

    def _entitled(self, recipient: str) -> None:
        with self.ledger.reading() as t:
            if not t.entitled(recipient):
                raise ReadProblem("not_found_or_not_disclosable")

    def _snapshot(self) -> Any | None:
        """The engine snapshot, ``None`` when no project is configured; raises :class:`SourceUnavailable`."""
        return self.engine.snapshot() if self.engine is not None else None

    def _result(self, mode: str, items: list[dict[str, Any]], page: dict[str, Any] | None, limitations: list[str],
                recipient: str, now: datetime, correlation: str, basis: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"wire_version": W.D01_VERSION, "mode": mode, "outcome": "partial", "projection_as_of": W.utc(now),
                "continuity": "unknown", "items": items, "page": page, "limitations": sorted(set(limitations)),
                "correlation_id": correlation, "collection_basis": basis, "effective_recipient_ref": recipient}

    def _disclosure(self, recipient: str) -> dict[str, Any]:
        return {"form": "full", "policy_ref": self.fx.doc["policy_ref"], "scope_ref": self.fx.doc["scope_ref"],
                "effective_recipient_ref": recipient, "qualified_release": False}

    def _fx_stamp(self, owner: str, fact: str, observed_at: str | None = None) -> dict[str, Any]:
        o = owner.lower()
        return W.stamp(owner, fact, f"fixture:{o}-epoch-1", f"fixture:{o}-v1", observed_at or self.fx.at(0),
                       coverage_ref=self.fx.doc["scope_ref"],
                       issuer_ref=self.fx.doc["issuers"].get(owner, "fixture:issuer"))

    @staticmethod
    def _aew_stamp(owner: str, fact: str, snap: Any) -> dict[str, Any]:
        return W.stamp(owner, fact, f"aew:project:{snap.project_id}", f"aew:rev:{snap.revision}", snap.generated_at,
                       coverage_ref=f"aew:project:{snap.project_id}", issuer_ref=ENGINE_ISSUER)

    def _unavailable(self, owner: str, now: datetime) -> dict[str, Any]:
        return W.unavailable(owner, W.utc(now), coverage_ref=self.fx.doc["scope_ref"])

    # cursors: bound to the route, the recipient, the filters, the page size and the visible set (a changed set is a
    # 409); short, so they fit PageInfo's 192-character pattern
    def _cursor(self, route: str, recipient: str, filters: Any, limit: int, digest: str, pos: int) -> str:
        mac = hmac.new(self._cursor_key, json.dumps([route, recipient, filters, limit, digest, pos]).encode(),
                       hashlib.sha256).hexdigest()[:32]
        return f"c1.{pos}.{mac}"

    def _position(self, cursor: str | None, route: str, recipient: str, filters: Any, limit: int, digest: str) -> int:
        if cursor is None:
            return 0
        parts = cursor.split(".")
        if len(parts) != 3 or parts[0] != "c1" or not parts[1].isdigit():
            raise ReadProblem("cursor_stale_or_unauthorized")
        pos = int(parts[1])
        if not hmac.compare_digest(cursor, self._cursor(route, recipient, filters, limit, digest, pos)):
            raise ReadProblem("cursor_stale_or_unauthorized")
        return pos

    def _page(self, items: list[dict[str, Any]], route: str, recipient: str, filters: Any, limit: int,
              cursor: str | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        digest = hashlib.sha256(W.canonical([[i["ref"]["id"], i["source"]["fact_ref"], i["source"]["source_version"]]
                                             for i in items])).hexdigest()
        pos = self._position(cursor, route, recipient, filters, limit, digest)
        if pos > len(items):
            raise ReadProblem("cursor_stale_or_unauthorized")
        page, more = items[pos:pos + limit], pos + limit < len(items)
        nxt = self._cursor(route, recipient, filters, limit, digest, pos + limit) if more else None
        return page, {"page_size": limit, "next_cursor": nxt, "has_more": more, "scope": "effective_recipient_view",
                      "membership": "unknown"}

    # ------------------------------------------------------------------ 1. GET /v1/read/waiting

    def waiting(self, recipient: str, limit: int, cursor: str | None, now: datetime,
                correlation: str) -> dict[str, Any]:
        self._entitled(recipient)
        items = [self._fx_waiting(w, recipient) for w in self.fx.visible_work(recipient) if w.get("waiting")]
        limitations = ["source_unqualified"]
        try:
            snap = self._snapshot()
        except SourceUnavailable:
            snap, limitations = None, limitations + ["source_unavailable", "partial_source"]
        if snap is not None:
            items += [self._aew_waiting(wid, u, snap, recipient) for wid, u in sorted(snap.state["work"].items())
                      if u.get("state") in WAITING_STATES]
        items.sort(key=lambda i: i["ref"]["id"])
        page, info = self._page(items, "waiting", recipient, None, limit, cursor)
        basis = self._fx_stamp("CNI", "fixture:cni-waiting-collection")
        return self._result("list", page, info, limitations, recipient, now, correlation, basis)

    def _fx_waiting(self, w: dict[str, Any], recipient: str) -> dict[str, Any]:
        wt, ref = w["waiting"], w["work_ref"].removeprefix(W.FIXTURE)
        owner = wt["responsible_owner"]
        narrative = ({"text": wt["narrative"], "render": "inert_text",
                      "provenance": {"kind": "service_observation", "owner_or_author": self.fx.doc["issuers"]["CNI"],
                                     "source_ref": f"fixture:cni-waiting-{ref}"}} if wt.get("narrative") else None)
        return {"resource_type": "waiting", "ref": W.subject("waiting_condition", f"fixture:waiting-{ref}"),
                "source": self._fx_stamp("CNI", f"fixture:cni-waiting-{ref}"),
                "disclosure": self._disclosure(recipient),
                "data": {"work": W.subject(w["kind"], w["work_ref"], revision=w["work_revision"]), "cause": wt["cause"],
                         "basis_refs": {"visibility": "unknown", "refs": []},
                         "responsible_owner": wt["responsible_owner"],
                         "progress": wt["progress"], "action_status": "read_only", "narrative": narrative},
                "links": [],
                "field_sources": [{"field_path": "data.work",
                                   "source": self._fx_stamp("WIS", f"fixture:wis-work-{ref}")},
                                  {"field_path": "data.cause",
                                   "source": self._fx_stamp(owner, f"fixture:{owner.lower()}-cause-{ref}")},
                                  {"field_path": "data.progress",
                                   "source": self._fx_stamp("HEB", f"fixture:heb-progress-{ref}")}]}

    def _aew_waiting(self, wid: str, u: dict[str, Any], snap: Any, recipient: str) -> dict[str, Any]:
        """A real AEW work unit in a waiting state: the engine's own record, reported (WIS facts, CNI listing)."""
        blockers = [b for b in u.get("blocked_by") or [] if isinstance(b, dict) and b.get("id")]
        refs = [W.subject("ticket", str(b["id"])) for b in blockers][:50]
        reason = u.get("state_reason")
        work = self._aew_stamp("WIS", f"aew:work:{wid}", snap)
        return {"resource_type": "waiting", "ref": W.subject("waiting_condition", f"aew:waiting:{wid}"),
                "source": self._aew_stamp("CNI", f"aew:waiting:{wid}", snap), "disclosure": self._disclosure(recipient),
                "data": {"work": W.subject(_kind(u), wid, revision=_revision(u)), "cause": WAITING_STATES[u["state"]],
                         "basis_refs": {"visibility": "partial_visible" if refs else "unknown", "refs": refs},
                         "responsible_owner": "WIS", "progress": "blocked", "action_status": "read_only",
                         "narrative": ({"text": f"{u['state']}: {reason}", "render": "inert_text",
                                        "provenance": {"kind": "service_observation", "owner_or_author": ENGINE_ISSUER,
                                                       "source_ref": f"aew:work:{wid}"}} if reason else None)},
                "links": [],
                "field_sources": [{"field_path": p, "source": work} for p in
                                  ("data.work", "data.cause", "data.basis_refs", "data.progress")]}

    # ------------------------------------------------------------------ 2. GET /v1/read/runs/{execution_id}

    def run(self, recipient: str, execution_id: str, now: datetime, correlation: str) -> dict[str, Any]:
        self._entitled(recipient)
        if execution_id.startswith(W.FIXTURE):
            r = self.fx.run(execution_id)
            if r is None or recipient not in r["recipients"]:
                raise ReadProblem("not_found_or_not_disclosable")
            item, lim = self._fx_run(r, recipient, now)
        else:
            if self.engine is None:
                raise ReadProblem("not_found_or_not_disclosable")
            try:
                snap: Any = self._snapshot()
            except SourceUnavailable as exc:  # we cannot even say whether it exists: no honest limited answer
                raise ReadProblem("owner_unavailable") from exc
            inv = snap.state["invocations"].get(execution_id)
            if inv is None or inv.get("kind") == "integration_attempt":  # custody, not a run (as the dashboard)
                raise ReadProblem("not_found_or_not_disclosable")
            item, lim = self._aew_run(execution_id, inv, snap, recipient, now)
        return self._result("detail", [item], None, lim, recipient, now, correlation)

    def _run_data(self, inv_ref: str, work: dict[str, Any] | None, **kw: Any) -> dict[str, Any]:
        data = {"invocation_ref": W.subject("execution_activity", inv_ref), "work_ref": work, "attachment_ref": None,
                "phase": "UNKNOWN", "progress_basis_ref": None, "started_at": None, "last_progress_at": None,
                "elapsed_observed_seconds": None, "elapsed_basis_ref": None, "custody_state": "UNKNOWN",
                "custody_basis_ref": None,
                "resource_state": {"accounting_class": "UNKNOWN", "monetary_amount": None, "currency": None,
                                   "usage_units": None, "observation_class": "UNKNOWN",
                                   "outstanding_exposure": "UNKNOWN",
                                   "original_operation_ref": None, "accounting_domain": "IF10_MODEL_DELIVERY_ONLY"},
                "resource_basis_ref": None, "source_epoch": None, "limitations": ["source_unqualified"],
                "authority_effect": "READ_ONLY_NO_LIFECYCLE_EFFECT", "phase_observation_class": "UNKNOWN",
                "phase_basis_ref": None, "stall_assessment": "NOT_ESTABLISHED", "stall_basis_ref": None,
                "wake_assessment": "NOT_ESTABLISHED", "wake_basis_ref": None, "remote_effect_state": "NOT_ESTABLISHED",
                "remote_effect_basis_ref": None, "remote_effect_domain": "IF12_MODEL_DELIVERY_ONLY",
                "non_model_effect_state": "NOT_ESTABLISHED", "non_model_effect_basis_ref": None,
                "non_model_resource_exposure": "UNKNOWN", "non_model_resource_basis_ref": None,
                "whole_invocation_effect_clearance": "NOT_ESTABLISHED",
                "whole_invocation_resource_clearance": "NOT_ESTABLISHED"}
        data.update(kw)
        return data

    def _fx_run(self, r: dict[str, Any], recipient: str, now: datetime) -> tuple[dict[str, Any], list[str]]:
        w = self.fx.work(r["work_ref"])
        work = W.subject(w["kind"], w["work_ref"], revision=w["work_revision"]) if w else None
        ident = r["execution_id"].removeprefix(W.FIXTURE)
        phase = r["phase"]
        kw: dict[str, Any] = {"phase": phase, "phase_observation_class": _phase_class(phase),
                              "phase_basis_ref": r["phase_basis_ref"], "progress_basis_ref": r["phase_basis_ref"],
                              "started_at": self.fx.at(r["started_offset_s"]),
                              "last_progress_at": self.fx.at(r["last_progress_offset_s"]),
                              "source_epoch": "fixture:r01-epoch-1"}
        lim = ["source_unqualified"]
        fs = [{"field_path": "data.phase", "source": self._fx_stamp("R01", r["phase_basis_ref"])},
              {"field_path": "data.work_ref", "source": self._fx_stamp("WIS", f"fixture:wis-work-{ident}")},
              {"field_path": "data.custody_state", "source": self._unavailable("HEB", now)},
              {"field_path": "data.resource_state", "source": self._unavailable("IF10", now)}]
        eff = r.get("remote_effect")
        if eff:
            kw.update(remote_effect_state=eff["state"], remote_effect_basis_ref=eff["basis_ref"])
            lim.append("unknown_remote_effect")
            # the effect's own source, basis and last-known time (field map step 2)
            fs.append({"field_path": "data.remote_effect_state",
                       "source": self._fx_stamp("IF12", eff["basis_ref"], self.fx.at(eff["observed_offset_s"]))})
        else:
            fs.append({"field_path": "data.remote_effect_state", "source": self._unavailable("IF12", now)})
        if r.get("stall"):
            kw.update(stall_assessment=r["stall"]["assessment"], stall_basis_ref=r["stall"]["basis_ref"])
            lim.append("progress_suspected")
        kw["limitations"] = lim
        item = {"resource_type": "run", "ref": W.subject("execution_activity", r["execution_id"]),
                "source": self._fx_stamp("R01", f"fixture:r01-run-{ident}"), "disclosure": self._disclosure(recipient),
                "data": self._run_data(r["execution_id"], work, **kw),
                "links": [], "field_sources": fs}
        return item, ["source_unqualified"]

    def _aew_run(self, inv_id: str, inv: dict[str, Any], snap: Any, recipient: str,
                 now: datetime) -> tuple[dict[str, Any], list[str]]:
        """A real AEW invocation: the engine's record and its supervisor's run record, reported, never qualified."""
        runs = [r for r in inv.get("runs") or [] if isinstance(r, dict) and r.get("run")]
        unit = snap.state["work"].get(inv.get("work_unit")) or {}
        kw: dict[str, Any] = {"source_epoch": f"aew:rev:{snap.revision}", "limitations": ["source_unqualified",
                                                                                       "partial_observation"]}
        if runs:
            last = runs[-1]
            status = self.engine.observed(str(last["run"])) if self.engine is not None else "unknown"
            phase = ("REPORTED_ACTIVE" if status in RUNNING else "REPORTED_FINISHED" if status in _terminal()
                     else "UNKNOWN")
            kw.update(phase=phase, phase_observation_class=_phase_class(phase),
                      phase_basis_ref=f"aew:run:{last['run']}" if phase != "UNKNOWN" else None,
                      started_at=str(runs[0].get("launched_at")) if runs[0].get("launched_at") else None)
        work = self._aew_stamp("WIS", f"aew:work:{inv.get('work_unit')}", snap)
        item = {"resource_type": "run", "ref": W.subject("execution_activity", inv_id),
                "source": self._aew_stamp("R01", f"aew:invocation:{inv_id}", snap),
                "disclosure": self._disclosure(recipient),
                "data": self._run_data(inv_id, W.subject(_kind(unit), str(inv.get("work_unit")),
                                                         revision=_revision(unit)), **kw),
                "links": [],
                "field_sources": [{"field_path": "data.phase",
                                   "source": self._aew_stamp("R01", f"aew:invocation:{inv_id}", snap)},
                                  {"field_path": "data.work_ref", "source": work},
                                  {"field_path": "data.custody_state", "source": self._unavailable("HEB", now)},
                                  {"field_path": "data.resource_state", "source": self._unavailable("IF10", now)},
                                  {"field_path": "data.remote_effect_state", "source": self._unavailable("IF12", now)}]}
        return item, ["source_unqualified"]

    # ------------------------------------------------------------------ 3. GET /v1/read/continuation-state/{work_id}

    def continuation(self, recipient: str, work_ref: str, now: datetime, correlation: str) -> dict[str, Any]:
        self._entitled(recipient)
        if work_ref.startswith(W.FIXTURE):
            w = self.fx.work(work_ref)
            if w is None or recipient not in w["recipients"]:
                raise ReadProblem("not_found_or_not_disclosable")
            item = self._fx_continuation(w, recipient, now)
        else:
            if self.engine is None:
                raise ReadProblem("not_found_or_not_disclosable")
            try:
                snap: Any = self._snapshot()
            except SourceUnavailable as exc:
                raise ReadProblem("owner_unavailable") from exc
            u = snap.state["work"].get(work_ref)
            if u is None:
                raise ReadProblem("not_found_or_not_disclosable")
            item = self._aew_continuation(work_ref, u, snap, recipient, now)
        unknown = any(a["qualification"] == "not_established" for a in item["data"]["axes"].values())
        lim = ["source_unqualified", "G3_unqualified"] + (["source_unavailable"] if unknown else [])
        return self._result("detail", [item], None, lim, recipient, now, correlation)

    @staticmethod
    def _axis_unavailable() -> dict[str, Any]:
        return {"state": "unknown", "owner_epoch": None, "source_version": None, "basis_ref": None, "observed_at": None,
                "valid_until": None, "qualification": "not_established", "reason_code": "SOURCE_UNAVAILABLE"}

    @staticmethod
    def _axis_reported(epoch: str, version: str, basis: str, observed_at: str) -> dict[str, Any]:
        """An owner fact we can name but not qualify: its state stays unknown (FR_OwnerAxis: ok and blocked need a
        qualified fact), with the slice's interim reason SOURCE_UNQUALIFIED (gap STG02-BE-05)."""
        return {"state": "unknown", "owner_epoch": epoch, "source_version": version, "basis_ref": basis,
                "observed_at": observed_at, "valid_until": None, "qualification": "unqualified",
                "reason_code": "SOURCE_UNQUALIFIED"}

    def _vector(self, recipient: str, ref_id: str, work_ref: str, revision: str, generation: str, binding: str,
                axes: dict[str, dict[str, Any]], stamps: dict[str, dict[str, Any]], item_source: dict[str, Any],
                ) -> dict[str, Any]:
        pins = {"data.work_ref": "WIS", "data.work_revision": "WIS", "data.generation_ref": "HEB",
                "data.binding_ref": "HEB", "data.operation": "HEB", "data.informational_only": "HEB"}
        fs = [{"field_path": f"data.axes.{x}", "source": stamps[f"axis:{x}"]} for x in sorted(AXES)]
        fs += [{"field_path": p, "source": stamps[o]} for p, o in sorted(pins.items())]
        return {"resource_type": "continuation_vector",
                "ref": W.subject("continuation_state", ref_id, revision=revision, generation=generation),
                "source": item_source, "disclosure": self._disclosure(recipient),
                "data": {"binding_ref": binding, "work_ref": work_ref, "work_revision": revision,
                         "generation_ref": generation, "operation": "CONTINUE_ELIGIBLE_WORK", "axes": axes,
                         "informational_only": True},
                "links": [], "field_sources": fs}

    def _fx_continuation(self, w: dict[str, Any], recipient: str, now: datetime) -> dict[str, Any]:
        ref, heb = w["work_ref"].removeprefix(W.FIXTURE), self.fx.heb
        axes, stamps = {}, {}
        for x in AXES:
            spec = w["axes"].get(x)
            if spec is None:
                axes[x], stamps[f"axis:{x}"] = self._axis_unavailable(), self._unavailable(x, now)
            else:
                o = x.lower()
                axes[x] = self._axis_reported(f"fixture:{o}-epoch-1", f"fixture:{o}-v1", spec["basis_ref"],
                                              self.fx.at(0))
                stamps[f"axis:{x}"] = self._fx_stamp(x, spec["basis_ref"])
        stamps["WIS"] = self._fx_stamp("WIS", f"fixture:wis-work-{ref}")
        stamps["HEB"] = self._fx_stamp("HEB", f"fixture:heb-continuation-{ref}")
        return self._vector(recipient, f"fixture:continuation-{ref}", w["work_ref"], w["work_revision"],
                            heb["generation_ref"], heb["binding_ref"], axes, stamps, stamps["HEB"])

    def _aew_continuation(self, wid: str, u: dict[str, Any], snap: Any, recipient: str,
                          now: datetime) -> dict[str, Any]:
        """A real AEW work unit: WIS's axis is the engine's record; HEB, ADC, AEV, R-01 and IF-10 have no source."""
        axes = {x: self._axis_unavailable() for x in AXES}
        stamps = {f"axis:{x}": self._unavailable(x, now) for x in AXES}
        axes["WIS"] = self._axis_reported(f"aew:project:{snap.project_id}", f"aew:rev:{snap.revision}",
                                          f"aew:work:{wid}", snap.generated_at)
        stamps["axis:WIS"] = stamps["WIS"] = self._aew_stamp("WIS", f"aew:work:{wid}", snap)
        stamps["HEB"] = self._unavailable("HEB", now)
        return self._vector(recipient, f"aew:continuation:{wid}", wid, _revision(u) or "none", "unavailable:HEB",
                            "unavailable:HEB", axes, stamps, stamps["HEB"])

    # ------------------------------------------------------------------ 5. GET /v1/read/owner-operations

    def owner_operations(self, recipient: str, owner: str | None, scope_ref: str | None, attachment_ref: str | None,
                         cursor: str | None, now: datetime, correlation: str) -> dict[str, Any]:
        if owner is not None and owner not in O01_OWNERS:
            raise ReadProblem("invalid_request")
        self._entitled(recipient)
        if scope_ref is not None and scope_ref != self.fx.doc["scope_ref"]:
            raise ReadProblem("not_found_or_not_disclosable")  # a scope not disclosed to this recipient
        with self.ledger.reading() as t:
            ops = t.owner_ops(self.fx.installation, recipient)
        ops = [o for o in ops if (owner is None or o["owner"] == owner)
               and (attachment_ref is None or o["attachment_ref"] == attachment_ref)]
        items = [self._index_item(o, recipient) for o in ops]  # already in (owner, operation_ref) order
        filters = [owner, scope_ref, attachment_ref]
        page, info = self._page(items, "owner-operations", recipient, filters, OWNER_OPS_PAGE, cursor)
        basis = self._fx_stamp("CNI", "fixture:cni-owner-operation-roster")
        return self._result("list", page, info, ["source_unqualified", "G3_unqualified"], recipient, now, correlation,
                            basis)

    def _index_item(self, o: dict[str, Any], recipient: str) -> dict[str, Any]:
        heb = self.fx.heb
        s = W.stamp(o["owner"], "op-record:" + o["operation_ref"], heb["epoch"], heb["version"], o["issued_at"],
                    coverage_ref=self.fx.doc["scope_ref"], issuer_ref=self.fx.doc["issuers"]["HEB"])
        return {"resource_type": "owner_operation_index",
                "ref": W.subject("owner_operation_index", f"ownerop:{o['owner']}:{o['operation_ref']}"),
                "source": s, "disclosure": self._disclosure(recipient),
                "data": {"owner": o["owner"], "operation_ref": o["operation_ref"], "action": o["action"],
                         "subject_ref": o["subject_ref"], "attachment_generation": o["attachment_generation"],
                         "issued_at": o["issued_at"], "owner_epoch": heb["epoch"], "source_version": heb["version"],
                         "detail_path": f"/o01/v0/owner-operations/{o['owner']}/{o['operation_ref']}"},
                "links": [], "field_sources": []}


def _kind(u: dict[str, Any]) -> str:
    return str(u["kind"]) if u.get("kind") in ("epic", "story", "ticket") else "ticket"


def _revision(u: dict[str, Any]) -> str | None:
    accepted = (u.get("plan") or {}).get("accepted")
    return f"plan-{accepted}" if accepted else None


def _phase_class(phase: str) -> str:
    for prefix, cls in (("OBSERVED_", "HEB_OBSERVED"), ("REPORTED_", "AGENT_REPORTED"),
                        ("INFERRED_", "MODEL_INFERRED")):
        if phase.startswith(prefix):
            return cls
    return phase  # UNKNOWN, WITHHELD


def _terminal() -> frozenset[str]:
    from aew.harness import contract as K

    return K.TERMINAL
