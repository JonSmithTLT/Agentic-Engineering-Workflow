"""The dashboard contract's projections, built from one :class:`~aew.dashboard.reader.Snapshot` (design note §4.10,
§4.11).

Every projection is built **field by field from an allowlist**: an engine record is never passed through, so no
storage path, run directory, workspace, environment, verifier or credential can reach a response (Q06). The engine
decides every conclusion the frontend shows (counts, blockers, capability states, health); the frontend only displays.

Capabilities (R18, as the designer decided on 2026-10-05): ``overview``, ``work``, ``runs``, ``evidence``,
``knowledge`` and ``activity`` are AVAILABLE; ``history`` and ``integrity`` are AVAILABLE on a v2 project whose index
syncs; ``queue`` is UNSUPPORTED (no route in 0.1.2); ``action_projection`` is UNSUPPORTED until the typed Lead
surface's ``ActionProjection`` (F15.1) is its source, so ``/attention`` answers 403 meanwhile, while ``/overview``'s
bounded ``attention`` list and ``Work.has_attention`` carry the engine facts the backend already provides.

Each route's envelope carries the version of the contract that defined its response (:data:`ENVELOPE_VERSION`;
register F20.8): a minor version only adds routes, so every 0.1.2 route keeps emitting ``0.1.2`` and a client built
against 0.1.2 keeps parsing it.

Wherever a projection needs the snapshot's time it writes :data:`~aew.dashboard.etag.SNAPSHOT_TIME`; the server
computes the validator over that and then stamps the real time in (F20.4), so the time of a read never changes an
``ETag``.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from aew.dashboard import cursors
from aew.dashboard import mapview as MV
from aew.dashboard.etag import SNAPSHOT_TIME
from aew.dashboard.reader import INVALID, NONE, MapsReader, Registry, Snapshot
from aew.dashboard.reasons import reason
from aew.engine import outbox
from aew.engine import transitions as T
from aew.engine.archive_ops import held_evidence, is_v2, redact
from aew.engine.freshness import record_freshness
from aew.engine.history_ops import _public as public_entry
from aew.errors import (
    AEWError,
    GitError,
    HistoryMoved,
    IntegrityError,
    LockTimeout,
    MapArtifactCorrupt,
    MapCurrentnessUnproven,
    NotFound,
    ValidationFailed,
)
from aew.harness import contract as K
from aew.harness import runlog
from aew.history import manifest as M
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.maps import freshness as MF
from aew.maps import gitobjects, structural
from aew.maps import rules as MR
from aew.maps import service as MSV
from aew.maps import store as MS

# Route -> the ``schema_version`` its envelope carries: the const of the route's response schema in the accepted
# contract (tests/unit/test_dashboard_contract.py holds every served route to it). A route a later minor version
# adds carries that version; the 0.1.2 routes never change theirs (the change note's compatibility rule).
ENVELOPE_VERSION: dict[str, str] = {
    route: "0.1.2" for route in (
        "/project", "/capabilities", "/overview", "/history/integrity", "/work", "/work/{id}", "/runs", "/runs/{id}",
        "/evidence", "/evidence/{id}", "/knowledge", "/knowledge/{id}", "/history", "/history/{id}", "/attention",
        "/activity")
}
# The maps routes (register F20.8, S1): added by contract 0.1.3, so their envelopes carry it.
MAPS_ROUTES = ("/maps", "/maps/structural", "/maps/structural/{root}", "/maps/structural/{root}/inputs", "/maps/diff")
ENVELOPE_VERSION.update(dict.fromkeys(MAPS_ROUTES, "0.1.3"))
BASE_ENVELOPE = "0.1.2"  # a projector built without a route (a test's) speaks the base version
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LIMIT_DEFAULT, LIMIT_MAX = 100, 250
OVERVIEW_WORK, OVERVIEW_RUNS, OVERVIEW_ATTENTION, OVERVIEW_ACTIVITY, OVERVIEW_RECENT = 6, 6, 6, 10, 20
CHILDREN_MAX = 250
LOG = logging.getLogger("aew.dashboard")
AVAILABLE, UNAVAILABLE, UNSUPPORTED = "AVAILABLE", "UNAVAILABLE", "UNSUPPORTED"
DECISION_ID = re.compile(r"^D-[0-9]+$")
EVIDENCE_PRODUCER = re.compile(r"^(INV-[0-9]+)-")
RICH_PLAIN, RICH_MARKDOWN = "plain", "markdown"

# The maps routes (register F20.8, S1; the change note §4). Ids are checked before any file or git access, so no
# ref, revision expression, option, short id or path reaches either.
MAP_ROOT = re.compile(r"[0-9a-f]{64}")  # fullmatch: `$` would admit a trailing newline
FULL_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
MAP_LIST_DEFAULT, MAP_LIST_MAX = 20, 50
MAP_INPUTS_DEFAULT, MAP_INPUTS_MAX = 100, 250
SCAN_MAPS, SCAN_BYTES = 256, 64 << 20  # one request examines at most this many stored maps and reads at most this
MAPS_GIT_TIMEOUT_S = 10.0  # each git process of a maps read: projections are serialized, so never the CLI's 300 s
EVIDENCE_ID_MAX = 64  # the registry's own bound on an architecture evidence id
ARCHIVE_WAIT_S = 2.0  # how long /maps waits on a busy history index for archived architecture evidence


def _custody(inv: dict[str, Any]) -> bool:
    """An engine custody invocation (M4-D3's ``integration_attempt``: the integration lease's custodian). It has no
    role, harness or run, and contract 0.1.2 leaves the integration queue UNSUPPORTED, so the run projections leave
    it out; projecting the queue is a later contract version with a renewed C0 review."""
    return inv.get("kind") == "integration_attempt"


class CapabilityUnavailable(AEWError):
    """A route whose capability is not AVAILABLE on this project (403)."""

    code = "CAPABILITY_UNAVAILABLE"
    exit_code = 1

    def __init__(self, capability: str, reasons: list[dict[str, Any]]) -> None:
        super().__init__(f"capability {capability} is not available", capability=capability)
        self.reasons = reasons


class InvalidRequest(AEWError):
    """A request outside the contract's bounds or vocabulary (400)."""

    code = "INVALID_REQUEST"
    exit_code = 2


# ------------------------------------------------------------------------------------------------- small shapes

def rich(text: str | None, fmt: str = RICH_PLAIN) -> dict[str, Any]:
    return {"format": fmt, "text": text or ""}


def entity(ident: str, kind: str, title: str | None = None) -> dict[str, Any]:
    return {"id": ident, "kind": kind, "title": title}


def _ids(values: Any) -> list[str]:
    return [v for v in (values or []) if isinstance(v, str) and OPAQUE_ID.match(v)]


def _bounded(items: list[Any], n: int = 250) -> list[Any]:
    return items[:n]


def parse_limit(raw: str | None, default: int = LIMIT_DEFAULT, maximum: int = LIMIT_MAX) -> int:
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise InvalidRequest("limit must be an integer") from None
    if not 1 <= value <= maximum:
        raise InvalidRequest(f"limit must be between 1 and {maximum}")
    return value


def check_id(value: str) -> str:
    if not OPAQUE_ID.match(value or "") or len(value) > 256:
        raise InvalidRequest("the id is not a valid opaque identity")
    return value


TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d{1,9})?Z$")


def check_timestamp(name: str, value: str | None, *, lower_bound: bool = False) -> str | None:
    """A UTC timestamp as the frontend sends it (``2026-10-04T00:00:00Z`` or with a fraction,
    ``2026-10-04T00:00:00.000Z``), parsed and validated as a date, returned in the engine's whole-second form.

    The engine's history entries carry whole seconds and its filters compare bounds inclusively, so a fractional bound
    is moved to the nearest second that keeps the same entries: a lower bound (``since``) up to the next second when its
    fraction is not zero, an upper bound (``until``) down to its own second."""
    if value is None:
        return None
    match = TIMESTAMP_RE.fullmatch(value)
    if not match:
        raise InvalidRequest(f"{name} must be a UTC timestamp like 2026-10-02T00:00:00Z")
    try:
        moment = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        raise InvalidRequest(f"{name} is not a real date and time: {value}") from None
    if lower_bound and match.group(2) and int(match.group(2)[1:]) > 0:
        moment += timedelta(seconds=1)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def check_maps_request(route: str, query: dict[str, str], matched: dict[str, str]) -> None:
    """The maps routes' parameters, checked before the snapshot is read and before any file or git access (the
    change note §4.1): ``400 INVALID_REQUEST`` for a malformed root, commit, section or limit, or a missing
    operand. A cursor is checked by its projection, against its scope."""
    if "root" in matched and not MAP_ROOT.fullmatch(matched["root"]):
        raise InvalidRequest("the root must be 64 lower-case hex digits")
    for name in ("against", "source_revision"):
        if name in query and not FULL_OBJECT_ID.fullmatch(query[name]):
            raise InvalidRequest(f"{name} must be a full object id: 40 or 64 lower-case hex digits")
    if route == "/maps/diff":
        for name in ("a", "b"):
            if name not in query:
                raise InvalidRequest(f"the parameter {name} is required")
            if not MAP_ROOT.fullmatch(query[name]):
                raise InvalidRequest(f"{name} must be a root: 64 lower-case hex digits")
    if "section" in query and query["section"] not in structural.SECTIONS:
        raise InvalidRequest(f"section must be one of {', '.join(structural.SECTIONS)}")
    if route == "/maps/structural":
        parse_limit(query.get("limit"), MAP_LIST_DEFAULT, MAP_LIST_MAX)
    elif route == "/maps/structural/{root}/inputs":
        parse_limit(query.get("limit"), MAP_INPUTS_DEFAULT, MAP_INPUTS_MAX)


# ------------------------------------------------------------------------------------------------- the projector

class Projector:
    """Every projection of one snapshot. Nothing here writes."""

    def __init__(self, snapshot: Snapshot, *, route: str | None = None, maps: MapsReader | None = None) -> None:
        self.s = snapshot
        self.route = route  # the contract route being answered: it decides the envelope's version
        self.maps = maps  # the server's maps reader and its caches (the maps routes; register F20.8)
        self.state = snapshot.state
        self.engine = snapshot.engine
        self.archive = snapshot.engine.archive
        self.units = snapshot.engine.units
        self._capabilities: dict[str, Any] | None = None
        self._attention: list[dict[str, Any]] | None = None
        self._observed: dict[str, tuple[str, dict[str, Any] | None]] = {}

    # ---------------------------------------------------------------- the envelope

    def envelope(self, data: Any) -> dict[str, Any]:
        version = ENVELOPE_VERSION[self.route] if self.route is not None else BASE_ENVELOPE
        return {"schema_version": version, "project_id": self.s.project_id,
                "control_revision": str(self.s.revision), "generated_at": SNAPSHOT_TIME, "data": data}

    def listing(self, items: list[dict[str, Any]], next_cursor: str | None) -> dict[str, Any]:
        return self.envelope({"items": items, "next_cursor": next_cursor})

    # ---------------------------------------------------------------- project, capabilities, health

    def project(self) -> dict[str, Any]:
        from aew import __version__

        return self.envelope({"id": self.s.project_id, "name": self.s.project_name, "aew_version": __version__})

    def _history_state(self) -> tuple[str, list[dict[str, Any]]]:
        if not is_v2(self.state):
            return UNAVAILABLE, [reason("MIGRATION_REQUIRED")]
        try:
            self.archive.index(self.state)
        except (LockTimeout, IntegrityError, OSError) as exc:
            # The exception's text can name the index's storage path (a permission failure does): it goes to the
            # server log, and the browser gets the registered reason only.
            LOG.warning("history index unavailable: %s: %s", type(exc).__name__, exc)
            return UNAVAILABLE, [reason("HISTORY_INDEX_UNAVAILABLE")]
        return AVAILABLE, []

    def capabilities_data(self) -> dict[str, Any]:
        if self._capabilities is None:
            ok = {"state": AVAILABLE, "reasons": []}
            history_state, history_reasons = self._history_state()
            self._capabilities = {
                "overview": dict(ok), "work": dict(ok), "runs": dict(ok), "evidence": dict(ok),
                "knowledge": dict(ok), "activity": dict(ok),
                "history": {"state": history_state, "reasons": list(history_reasons)},
                "integrity": {"state": history_state, "reasons": list(history_reasons)},
                "queue": {"state": UNSUPPORTED, "reasons": [reason("NOT_IN_CONTRACT_0_1_2")]},
                "action_projection": {"state": UNSUPPORTED, "reasons": [reason("AWAITS_ACTION_PROJECTION")]},
                # 0.1.3: every project has the maps pages; having no map is a state of the data (``/maps``)
                "maps": dict(ok),
            }
        return self._capabilities

    def capabilities(self) -> dict[str, Any]:
        return self.envelope(self.capabilities_data())

    def require(self, capability: str) -> None:
        cap = self.capabilities_data()[capability]
        if cap["state"] != AVAILABLE:
            raise CapabilityUnavailable(capability, cap["reasons"])

    def health(self) -> dict[str, Any]:
        reasons: list[dict[str, Any]] = []
        if not self.engine.manifest_pin_ok(self.state):
            reasons.append(reason("MANIFEST_PIN_MISMATCH"))
        if self.engine.policy_pin_drift(self.state, self.s.manifest):
            reasons.append(reason("POLICY_PIN_MISMATCH"))
        reasons += [reason("CONTRADICTION", text) for text in self._contradictions()]
        status = "UNHEALTHY" if reasons else "HEALTHY"
        audit = self.engine.audit_status(self.state, policy=self._audit_policy())
        for finding in (audit or {}).get("over_policy_detail") or []:
            reasons.append(reason(finding["code"], finding["message"]))
            status = status if status == "UNHEALTHY" else "DEGRADED"
        for inv_id, inv in sorted(self.state["invocations"].items()):
            for run in inv.get("runs") or []:
                observed, _ = self._observe(run["run"])
                if observed == K.LOST:
                    reasons.append(reason("RUN_LOST", f"run {run['run']} of {inv_id}"))
                    status = status if status == "UNHEALTHY" else "DEGRADED"
        return {"status": status, "reasons": _bounded(reasons), "observed_at": SNAPSHOT_TIME}

    def _audit_policy(self) -> dict[str, Any]:
        block = self.s.gates.get("history_audit") or {}
        return dict(block) if isinstance(block, dict) else {}

    def _contradictions(self) -> list[str]:
        try:
            return self.engine.contradictions(self.state, self.s.manifest)
        except AEWError as exc:
            return [f"the contradiction check itself failed: {exc.message}"]

    # ---------------------------------------------------------------- work

    def _hot_children(self) -> dict[str, list[str]]:
        kids: dict[str, list[str]] = {}
        for wid, unit in self.state["work"].items():
            if unit.get("parent"):
                kids.setdefault(unit["parent"], []).append(wid)
        return kids

    def _updated_at(self, unit: dict[str, Any]) -> str:
        history = unit.get("history") or []
        if history and isinstance(history[-1], dict) and history[-1].get("at"):
            return str(history[-1]["at"])
        return str(unit.get("created_at") or SNAPSHOT_TIME)

    def _blockers(self, unit: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for b in unit.get("blocked_by") or []:
            if not isinstance(b, dict):
                continue
            parts = [str(b.get("kind", "blocked"))]
            parts += [f"{k}={v}" for k, v in sorted(b.items()) if k != "kind" and isinstance(v, (str, int))]
            out.append(reason("BLOCKED_BY", " ".join(parts)))
        return _bounded(out)

    def _rollup(self, wid: str, unit: dict[str, Any]) -> dict[str, Any] | None:
        if unit["kind"] == "ticket" or wid not in self.state["work"]:
            return None
        counts = self.units.rollup(self.state, wid)["children_by_state"]
        done, cancelled = counts.get("DONE", 0), counts.get("CANCELLED", 0)
        return {"open": sum(counts.values()) - done - cancelled, "done": done, "cancelled": cancelled}

    def _integration(self, unit: dict[str, Any]) -> dict[str, Any] | None:
        integ = unit.get("integration")
        if not isinstance(integ, dict):
            return None
        seq = (integ.get("binding") or {}).get("commit_ready_seq")
        return {"status": integ.get("status"), "commit": integ.get("commit"),
                "commit_ready_seq": seq if isinstance(seq, int) else None}

    def _children(self, wid: str, kids: dict[str, list[str]]) -> tuple[list[str], bool]:
        ids = set(kids.get(wid, []))
        if is_v2(self.state):
            ids |= set(self.archive.archived_child_ids(self.state, wid))
        ordered = sorted(ids)
        return ordered[:CHILDREN_MAX], len(ordered) > CHILDREN_MAX

    def work_item(self, wid: str, unit: dict[str, Any], *, kids: dict[str, list[str]] | None = None,
                  with_children: bool = True) -> dict[str, Any]:
        kids = self._hot_children() if kids is None else kids
        archived = bool(unit.get("archived")) or wid not in self.state["work"]
        children, truncated = self._children(wid, kids) if with_children else ([], False)
        plan = (unit.get("plan") or {}).get("accepted")
        return {
            "id": wid, "kind": unit["kind"], "title": str(unit.get("title") or wid), "state": unit["state"],
            "parent_id": unit.get("parent"), "has_attention": wid in self._attention_ids(),
            "summary": rich(unit.get("state_reason")), "reasons": [],
            "related": _bounded([entity(e["id"], "work") for e in unit.get("depends_on") or []
                                 if isinstance(e, dict) and OPAQUE_ID.match(str(e.get("id", "")))]),
            "updated_at": self._updated_at(unit), "risk_class": unit.get("risk_class"),
            "plan_revision": plan if isinstance(plan, int) else None,
            "mutating": unit.get("mutating") if isinstance(unit.get("mutating"), bool) else None,
            "archived": archived, "blocked_by": self._blockers(unit), "children": children,
            "children_truncated": truncated, "rollup": self._rollup(wid, unit), "integration": self._integration(unit),
        }

    def _archived_view(self, wid: str) -> dict[str, Any]:
        unit = self.archive.archived_unit(self.state, wid)
        if unit is None:
            raise NotFound(f"no work unit {wid}")
        return unit

    def work(self, wid: str) -> dict[str, Any]:
        self.require("work")
        unit = self.units.view(self.state, check_id(wid))  # hot, or archived as it stands now (R7)
        return self.envelope(self.work_item(wid, unit))

    def work_list(self, *, state: str | None, kind: str | None, parent: str | None, limit: int,
                  cursor: str | None) -> dict[str, Any]:
        self.require("work")
        filters = {"state": state, "kind": kind, "parent": parent}
        if parent is not None:
            check_id(parent)
        # The selected scope, as ids with the facts the filters need (R15): hot work and the recent ring by default,
        # every archived unit in a finished state when asked for, never the whole archive through paging.
        scope: dict[str, dict[str, Any]] = {}
        for wid, unit in self.state["work"].items():
            scope[wid] = {"kind": unit["kind"], "state": unit["state"], "parent": unit.get("parent"), "hot": True}
        if state in T.TERMINAL:
            for e in self.archive.archived_units(self.state, state):
                scope.setdefault(e["id"], {"kind": e.get("unit_kind"), "state": e.get("state"),
                                           "parent": e.get("parent"), "hot": False})
        elif state is None:
            for r in self.state.get("recent") or []:
                scope.setdefault(r["id"], {"kind": r["kind"], "state": r["state"], "parent": r.get("parent"),
                                           "hot": False})
        selected = sorted(wid for wid, f in scope.items()
                          if (state is None or f["state"] == state) and (kind is None or f["kind"] == kind)
                          and (parent is None or f["parent"] == parent))
        after = None
        if cursor is not None:
            after = cursors.Hot.parse(cursor, route="work", project=self.s.project_id, filters=filters, limit=limit,
                                      revision=self.s.revision).after
        page_ids, next_after = cursors.page_by_id([{"id": i} for i in selected], after=after, limit=limit)
        kids = self._hot_children()
        items = []
        for row in page_ids:
            wid = row["id"]
            unit = self.state["work"].get(wid) or self._archived_view(wid)
            items.append(self.work_item(wid, unit, kids=kids))
        next_cursor = (cursors.Hot("work", self.s.project_id, self.s.revision, filters, limit, next_after).encode()
                       if next_after else None)
        return self.listing(items, next_cursor)

    # ---------------------------------------------------------------- attention (engine facts; not the projection)

    def _attention_ids(self) -> set[str]:
        return {item["subject"]["id"] for item in self.attention_items() if item["subject"]["kind"] == "work"}

    def attention_items(self) -> list[dict[str, Any]]:
        """Attention from engine facts: units in a state the Lead must act on, blockers, contradictions, lost or
        crashed runs. Shown through ``/overview`` (bounded) and ``Work.has_attention``; the ``/attention`` route
        waits for the canonical action projection (F15.1)."""
        if self._attention is not None:
            return self._attention
        items: list[dict[str, Any]] = []
        for wid, unit in sorted(self.state["work"].items()):
            st = unit["state"]
            if st in ("ESCALATED", "REPLAN_REQUIRED"):
                kind, severity = "decision_required", "high"
            elif st in ("REVIEW_FAILED", "VERIFICATION_FAILED", "VERIFICATION_INCONCLUSIVE"):
                kind, severity = "required_finding", "medium"
            elif st == "BLOCKED" and unit.get("blocked_by"):
                kind, severity = "blocker", "low"
            elif st == "INTERRUPTED":
                kind, severity = "anomaly", "medium"
            else:
                continue
            reasons = ([reason("STATE_REASON", str(unit["state_reason"]))] if unit.get("state_reason") else [])
            items.append({"id": f"AT-{wid}", "kind": kind, "severity": severity,
                          "subject": entity(wid, "work", str(unit.get("title") or wid)),
                          "title": f"{wid} is {st}", "summary": rich(unit.get("state_reason")),
                          "reasons": _bounded(reasons + self._blockers(unit)), "first_seen_at": self._updated_at(unit)})
        for n, text in enumerate(self._contradictions(), 1):
            items.append({"id": f"AT-contradiction-{n}", "kind": "anomaly", "severity": "high",
                          "subject": entity(self.s.project_id, "project", self.s.project_name),
                          "title": "Contradiction", "summary": rich(text), "reasons": [reason("CONTRADICTION", text)],
                          "first_seen_at": SNAPSHOT_TIME})
        for inv_id, inv in sorted(self.state["invocations"].items()):
            for run in inv.get("runs") or []:
                observed, _ = self._observe(run["run"])
                if observed in (K.LOST, K.CRASHED):
                    code = "RUN_LOST" if observed == K.LOST else "RUN_CRASHED"
                    items.append({"id": f"AT-{run['run']}", "kind": "anomaly", "severity": "medium",
                                  "subject": entity(inv_id, "invocation"), "title": f"run {run['run']} {observed}",
                                  "summary": rich(f"{inv['role']} run for {inv['work_unit']} is {observed}"),
                                  "reasons": [reason(code, f"run {run['run']} of {inv_id}")],
                                  "first_seen_at": str(run.get("launched_at") or SNAPSHOT_TIME)})
        self._attention = items
        return items

    def attention_list(self, *, limit: int, cursor: str | None) -> dict[str, Any]:
        self.require("action_projection")  # UNSUPPORTED until F15.1: never reached today
        raise AssertionError("unreachable")

    # ---------------------------------------------------------------- runs

    def _observe(self, run: str) -> tuple[str, dict[str, Any] | None]:
        if run not in self._observed:
            self._observed[run] = runlog.observed_status(runlog.run_dir(self.s.aew_root, run))
        return self._observed[run]

    def _run(self, inv: dict[str, Any], run: dict[str, Any], *, current: bool, tokens: dict[str, Any],
             ) -> dict[str, Any]:
        observed, _ = self._observe(run["run"])
        tok = tokens.get(str(run.get("token_id") or "")) or {}
        authority = "current" if current else f"none ({tok.get('revoke_reason') or inv['status']})"
        return {"id": run["run"], "harness": str(run.get("harness") or "unknown"),
                "launched_at": str(run.get("launched_at") or SNAPSHOT_TIME),
                "kind": str(run.get("kind") or "launch"), "status": observed, "authority": authority}

    def invocation_item(self, inv_id: str, inv: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
        work = view["work"].get(inv["work_unit"]) or {}
        runs = inv.get("runs") or []
        items = [self._run(inv, r, current=(i == len(runs) - 1 and inv["status"] == "active"
                                              and r.get("token_id") == inv.get("token_id")), tokens=view["tokens"])
                 for i, r in enumerate(runs)]
        evidence = [entity(e["id"], "evidence") for e in work.get("evidence") or []
                    if isinstance(e, dict) and str(e.get("id", "")).startswith(inv_id + "-")]
        return {"id": inv_id, "role": inv["role"], "status": inv["status"],
                "work": entity(inv["work_unit"], "work", work.get("title")), "created_at": str(inv["created_at"]),
                "runs": _bounded(items), "summary": rich(f"{inv['role']} for {inv['work_unit']}: {inv['status']}"),
                "evidence": _bounded(evidence), "reasons": []}

    def _runs_view(self) -> dict[str, Any]:
        """Hot state plus the invocations of the most recently finished work (the bounded ``recent`` ring), as
        ``aew harness status`` shows them."""
        view = self.state
        if is_v2(self.state):
            for r in self.state.get("recent") or []:
                if r["id"] not in self.state["work"]:
                    view = self.archive.rehydrate(view, r["id"]) or view
        return view

    def runs_list(self, *, limit: int, cursor: str | None) -> dict[str, Any]:
        self.require("runs")
        view = self._runs_view()
        rows = sorted(({"id": i} for i, inv in view["invocations"].items() if not _custody(inv)),
                      key=lambda r: r["id"])
        after = None
        if cursor is not None:
            after = cursors.Hot.parse(cursor, route="runs", project=self.s.project_id, filters={}, limit=limit,
                                      revision=self.s.revision).after
        page, next_after = cursors.page_by_id(rows, after=after, limit=limit)
        items = [self.invocation_item(r["id"], view["invocations"][r["id"]], view) for r in page]
        next_cursor = (cursors.Hot("runs", self.s.project_id, self.s.revision, {}, limit, next_after).encode()
                       if next_after else None)
        return self.listing(items, next_cursor)

    def run(self, inv_id: str) -> dict[str, Any]:
        self.require("runs")
        check_id(inv_id)
        view = self.state
        if inv_id not in view["invocations"] and is_v2(view):
            view = self.archive.rehydrate_invocation(view, inv_id) or view
        if inv_id not in view["invocations"] or _custody(view["invocations"][inv_id]):
            raise NotFound(f"no invocation {inv_id}")
        return self.envelope(self.invocation_item(inv_id, view["invocations"][inv_id], view))

    # ---------------------------------------------------------------- evidence

    def _currentness(self, meta: dict[str, Any], unit: dict[str, Any] | None) -> str:
        """The backend's rule: an evidence record is CURRENT while its fingerprint is the one its unit's most recent
        evidence was produced on, STALE once a later record was produced on another, UNKNOWN without a fingerprint."""
        mine = (meta.get("evaluated_snapshot") or {}).get("relevant_inputs_fingerprint")
        latest = next((e.get("fingerprint") for e in reversed((unit or {}).get("evidence") or [])
                       if isinstance(e, dict) and e.get("fingerprint")), None)
        if not mine or not latest:
            return "UNKNOWN"
        return "CURRENT" if mine == latest else "STALE"

    def evidence_item(self, meta: dict[str, Any], body: str, unit: dict[str, Any] | None) -> dict[str, Any]:
        producer = meta.get("producer") or {}
        snapshot = meta.get("evaluated_snapshot") or None
        plan = meta.get("plan_revision") or None
        review, impl = meta.get("review") or {}, meta.get("implementation") or {}
        findings = [reason("FINDING", f if isinstance(f, str) else str(f.get("text") or f.get("summary") or f))
                    for f in (review.get("findings") or []) if f]
        deviations = [reason("DEVIATION", d if isinstance(d, str) else str(d))
                      for d in (impl.get("deviations") or []) if d]
        provenance = []
        if OPAQUE_ID.match(str(producer.get("invocation") or "")):
            provenance.append(entity(producer["invocation"], "invocation"))
        if OPAQUE_ID.match(str(producer.get("run") or "")):
            provenance.append(entity(producer["run"], "run"))
        fingerprint = str((snapshot or {}).get("relevant_inputs_fingerprint") or "")
        digests = _bounded([str(d) for d in (snapshot or {}).get("artifact_digests") or []])

        def declared(key: str) -> str | None:
            value = producer.get(key)
            return value if isinstance(value, str) and value else None

        return {
            "id": meta["id"], "kind": meta["kind"],
            "result": meta.get("result") if isinstance(meta.get("result"), str) else review.get("disposition"),
            "subject": entity(meta["work_unit"], "work", (unit or {}).get("title")),
            "currentness": self._currentness(meta, unit), "requires_disposition": False,
            "claim": rich(str(meta.get("claim") or "")), "body": rich(body, RICH_MARKDOWN),
            "findings": _bounded(findings), "deviations": _bounded(deviations),
            "bindings": {
                "evaluated_snapshot": ({"base_revision": snapshot.get("base_revision"),
                                        "relevant_inputs_fingerprint": fingerprint, "artifact_digests": digests}
                                       if snapshot else None),
                "plan_revision": ({"revision": plan["revision"], "sha256": plan["sha256"]}
                                  if plan and isinstance(plan.get("revision"), int) and plan.get("sha256") else None),
                "producer": {"role": str(producer.get("role") or "unknown"),
                             "invocation": str(producer.get("invocation") or "unknown"),
                             "run": declared("run") if OPAQUE_ID.match(declared("run") or "") else None,
                             "model": declared("model"), "provider": declared("provider"),
                             "harness": declared("harness") if OPAQUE_ID.match(declared("harness") or "") else None},
            },
            "provenance": _bounded(provenance),
        }

    def _hot_evidence(self, wid: str) -> list[tuple[dict[str, Any], str]]:
        out = []
        for meta in E.scan(self.s.aew_root, wid)[0]:
            _, body = E.read(self.s.aew_root / meta["_path"])
            out.append((meta, body))
        return out

    def _archived_evidence(self, wid: str) -> tuple[dict[str, Any], list[tuple[dict[str, Any], str]]]:
        bundle = self.archive.bundle(self.state, wid) if is_v2(self.state) else None
        if bundle is None:
            raise NotFound(f"no work unit {wid}")
        unit = dict(bundle["unit"], archived=True)
        out = []
        for ref in unit.get("evidence") or []:
            _, meta, body = held_evidence(self.s.aew_root, bundle, ref["id"])
            out.append((meta, body))
        return unit, out

    def evidence_list(self, *, work: str | None, limit: int, cursor: str | None) -> dict[str, Any]:
        self.require("evidence")
        filters = {"work": work}
        records: list[tuple[dict[str, Any], str, dict[str, Any] | None]] = []
        if work is None:
            for wid, unit in sorted(self.state["work"].items()):
                records += [(m, b, unit) for m, b in self._hot_evidence(wid)]
        else:
            check_id(work)
            unit = self.state["work"].get(work)
            if unit is not None:
                records += [(m, b, unit) for m, b in self._hot_evidence(work)]
            else:
                unit, found = self._archived_evidence(work)
                records += [(m, b, unit) for m, b in found]
        records.sort(key=lambda r: r[0]["id"])
        after = None
        if cursor is not None:
            after = cursors.Hot.parse(cursor, route="evidence", project=self.s.project_id, filters=filters,
                                      limit=limit, revision=self.s.revision).after
        page, next_after = cursors.page_by_id([{"id": m["id"], "rec": (m, b, u)} for m, b, u in records],
                                              after=after, limit=limit)
        items = [self.evidence_item(*row["rec"]) for row in page]
        next_cursor = (cursors.Hot("evidence", self.s.project_id, self.s.revision, filters, limit, next_after).encode()
                       if next_after else None)
        return self.listing(items, next_cursor)

    def evidence(self, evidence_id: str) -> dict[str, Any]:
        self.require("evidence")
        check_id(evidence_id)
        meta, body, unit = self.locate_evidence(evidence_id)
        return self.envelope(self.evidence_item(meta, body, unit))

    def locate_evidence(self, evidence_id: str) -> tuple[dict[str, Any], str, dict[str, Any] | None]:
        """An evidence record by id: ``(meta, body, its unit)``, or ``NotFound``. The producing invocation names the
        unit (hot, or archived through the snapshot's history); a record of another shape is looked for in the hot
        units' directories. ``evidence_id`` must already be a checked opaque id. An archived lookup syncs the derived
        history index, and on a race re-reads state under the control lock as any reader does, unless the caller
        wraps it in ``archive.lockfree_reads`` (``/maps`` does; ``/evidence/{id}`` keeps the reader's path)."""
        match = EVIDENCE_PRODUCER.match(evidence_id)
        inv_id = match.group(1) if match else None
        inv = self.state["invocations"].get(inv_id) if inv_id else None
        wid = inv["work_unit"] if inv else None
        if wid is None and inv_id and is_v2(self.state):
            archived = self.archive.archived_invocation(self.state, inv_id)
            wid = archived["work_unit"] if archived else None
        if wid is None:  # a check result a Lead ingested by hand, or an id of another shape: the hot units' dirs
            for candidate in sorted(self.state["work"]):
                if (E.evidence_dir(self.s.aew_root, candidate) / f"{evidence_id}.md").is_file():
                    wid = candidate
                    break
        if wid is None:
            raise NotFound(f"no evidence {evidence_id}")
        unit = self.state["work"].get(wid)
        if unit is not None:
            path = E.evidence_dir(self.s.aew_root, wid) / f"{evidence_id}.md"
            if not path.is_file():
                raise NotFound(f"no evidence {evidence_id}")
            meta, body = E.read(path)
            return meta, body, unit
        unit, found = self._archived_evidence(wid)
        for meta, body in found:
            if meta["id"] == evidence_id:
                return meta, body, unit
        raise NotFound(f"no evidence {evidence_id}")

    # ---------------------------------------------------------------- knowledge (decision records)

    def _decisions_dir(self) -> Path:
        return self.s.aew_root / "decisions"

    def knowledge_item(self, path: Path) -> dict[str, Any]:
        record = read_record(path, "decision")
        meta, body = record.meta, record.body.strip()
        work_unit = str(meta.get("work_unit") or "")
        unit = self.state["work"].get(work_unit) or {}
        provenance = [entity(work_unit, "work", unit.get("title"))] if OPAQUE_ID.match(work_unit) else []
        summary = str(meta.get("summary") or "")
        return {"id": meta["id"], "kind": "decision", "title": summary or meta["id"],
                "state": "recorded", "body": rich(body, RICH_MARKDOWN) if body else rich(summary),
                "reasons": [reason("TRANSITION_REASON", str(meta["reason"]))] if meta.get("reason") else [],
                "provenance": provenance, "decision_type": str(meta.get("type") or "") or None}

    def knowledge_list(self, *, limit: int, cursor: str | None) -> dict[str, Any]:
        self.require("knowledge")
        directory = self._decisions_dir()
        rows = sorted(({"id": p.stem, "path": p} for p in directory.glob("D-*.md")), key=lambda r: r["id"]) \
            if directory.is_dir() else []
        after = None
        if cursor is not None:
            after = cursors.Hot.parse(cursor, route="knowledge", project=self.s.project_id, filters={}, limit=limit,
                                      revision=self.s.revision).after
        page, next_after = cursors.page_by_id(rows, after=after, limit=limit)
        items = [self.knowledge_item(r["path"]) for r in page]
        next_cursor = (cursors.Hot("knowledge", self.s.project_id, self.s.revision, {}, limit, next_after).encode()
                       if next_after else None)
        return self.listing(items, next_cursor)

    def knowledge(self, decision_id: str) -> dict[str, Any]:
        self.require("knowledge")
        check_id(decision_id)
        path = self._decisions_dir() / f"{decision_id}.md"
        if not DECISION_ID.match(decision_id) or not path.is_file():
            raise NotFound(f"no decision {decision_id}")
        return self.envelope(self.knowledge_item(path))

    # ---------------------------------------------------------------- history (ADR-0011)

    def _index(self) -> Any:
        self.require("history")
        return self.archive.index(self.state)

    def history_item(self, e: dict[str, Any], moves: dict[str, str | None]) -> dict[str, Any]:
        pub = public_entry(e)
        links = {str(rel): _bounded(_ids(v)) for rel, v in (pub.get("links") or {}).items() if isinstance(v, list)}
        parent = moves[e["id"]] if e["kind"] == "unit" and e["id"] in moves else pub.get("parent")
        return {"seq": e["seq"], "kind": e["kind"], "id": e["id"], "at": str(e["at"]),
                "state": pub.get("state"), "unit_kind": pub.get("unit_kind"), "title": pub.get("title"),
                "parent": parent, "subject": pub.get("subject"), "rel": pub.get("rel"), "links": links,
                "sha256": e["sha256"], "source": str(e.get("source") or "engine")}

    def history_list(self, *, kind: str | None, since: str | None, until: str | None, limit: int,
                     cursor: str | None) -> dict[str, Any]:
        index = self._index()
        if kind is not None and kind not in M.ENTRY_KINDS:
            raise InvalidRequest(f"kind must be one of {', '.join(M.ENTRY_KINDS)}")
        since = check_timestamp("since", since, lower_bound=True)
        until = check_timestamp("until", until)
        filters = {"kind": kind, "since": since, "until": until}
        count = int(self.state["cold"]["root"]["count"])
        if cursor is None:
            pinned = cursors.Pinned.start(route="history", project=self.s.project_id, filters=filters, limit=limit,
                                          current=count)
        else:
            pinned = cursors.Pinned.parse(cursor, route="history", project=self.s.project_id, filters=filters,
                                          limit=limit, current=count)
        entries = index.list(kind=kind, since=since, until=until, limit=limit + 1, max_seq=pinned.pin,
                             before_seq=pinned.before)
        more = len(entries) > limit
        page = entries[:limit]
        moves = index.moves()
        items = [self.history_item(e, moves) for e in page]
        nxt = pinned.advanced(page[-1]["seq"]) if more and page else None
        return self.listing(items, nxt.encode() if nxt else None)

    def _annotation(self, a: dict[str, Any]) -> dict[str, Any]:
        record = self.archive.record(a)
        obj = record.get("object")
        decision = record.get("decision")
        return {"id": a["id"], "rel": str(a.get("rel") or record.get("rel") or "unknown"),
                "object": obj if isinstance(obj, str) and OPAQUE_ID.match(obj) else None, "at": str(a["at"]),
                "decision": decision if isinstance(decision, str) and OPAQUE_ID.match(decision) else None,
                "source": str(a.get("source") or "engine"),
                "note": record.get("note") if isinstance(record.get("note"), str) else None}

    def history(self, record_id: str, *, annotations_cursor: str | None = None,
                annotations_limit: int = LIMIT_DEFAULT) -> dict[str, Any]:
        index = self._index()
        check_id(record_id)
        entries = index.by_id(record_id)
        if not entries:
            raise NotFound(f"no historical record {record_id}")
        entry = entries[-1]
        annotations = sorted(index.annotations(record_id), key=lambda a: a["seq"], reverse=True)
        count = int(self.state["cold"]["root"]["count"])
        filters = {"subject": record_id}
        if annotations_cursor is None:
            pinned = cursors.Pinned.start(route="history-annotations", project=self.s.project_id, filters=filters,
                                          limit=annotations_limit, current=count)
        else:
            pinned = cursors.Pinned.parse(annotations_cursor, route="history-annotations",
                                          project=self.s.project_id, filters=filters, limit=annotations_limit,
                                          current=count)
        window = [a for a in annotations if a["seq"] < pinned.before and a["seq"] <= pinned.pin]
        page = window[:annotations_limit]
        nxt = pinned.advanced(page[-1]["seq"]) if len(window) > annotations_limit and page else None
        item = self.history_item(entry, index.moves())
        item["annotations"] = [self._annotation(a) for a in page]
        item["annotations_next_cursor"] = nxt.encode() if nxt else None
        return self.envelope(item)

    def integrity(self) -> dict[str, Any]:
        self.require("integrity")
        audit = self.engine.audit_status(self.state, policy=self._audit_policy())
        if audit is None:
            raise CapabilityUnavailable("integrity", [reason("MIGRATION_REQUIRED")])
        cold = self.state["cold"]
        root = cold["root"]
        verified = cold.get("verified")
        last_full = cold.get("last_full")
        backlog = int(audit["unverified"]["entries"])
        reasons = [reason(f["code"], f["message"]) for f in audit.get("over_policy_detail") or []]
        status = "OVER_POLICY" if reasons else ("VERIFIED" if backlog == 0 else "BACKLOG")

        def verified_root(v: dict[str, Any] | None) -> dict[str, Any] | None:
            if not v:
                return None
            return {"count": int(v["count"]), "h": v["h"], "at": str(v["at"]), "audit": str(v["audit"])}

        sealed = root.get("sealed_head")
        sealed_head = {"seq": int(sealed["seq"]), "sha256": sealed["sha256"]} if sealed else None
        return self.envelope({
            "status": status,
            "current_root": {"count": int(root["count"]), "head_h": root["head_h"], "sealed_head": sealed_head},
            "verified": verified_root(verified), "backlog": backlog,
            "last_audit": entity(str(verified["audit"]), "audit") if verified else None,
            "reasons": _bounded(reasons), "last_full": verified_root(last_full),
            "oldest_unverified_at": audit["unverified"].get("oldest_at"),
        })

    # ---------------------------------------------------------------- activity (the transition log, ADR-0012)

    def _activity(self, record: dict[str, Any]) -> dict[str, Any]:
        rev = int(record["revision"])
        subject = entity(f"R{rev}", "transition")
        for ev in record.get("events") or []:
            if isinstance(ev, dict) and OPAQUE_ID.match(str(ev.get("id") or "")):
                subject = entity(str(ev["id"]), str(ev.get("unit") or ev["kind"].split(".")[0]))
                break
            if isinstance(ev, dict) and ev.get("kind") == "lead.generation":
                subject = entity("lead", "lead")
                break
        op, summary = str(record.get("op") or "transition"), record.get("summary")
        title = f"{op}: {summary}" if isinstance(summary, str) and summary else op
        return {"id": f"R{rev}", "subject": subject, "occurred_at": str(record["at"]), "title": title[:1000],
                "reason": reason("TRANSITION_REASON", str(record["reason"])) if record.get("reason") else None}

    def activity_list(self, *, limit: int, cursor: str | None) -> dict[str, Any]:
        self.require("activity")
        current = self.s.revision
        if cursor is None:
            pinned = cursors.Pinned.start(route="activity", project=self.s.project_id, filters={}, limit=limit,
                                          current=current)
        else:
            pinned = cursors.Pinned.parse(cursor, route="activity", project=self.s.project_id, filters={},
                                          limit=limit, current=current)
        through = pinned.before - 1
        since = max(0, through - limit)
        records = list(outbox.read_transitions(self.s.aew_root, since, through, outbox=self.state.get("outbox"))) \
            if through >= 1 else []
        items = [self._activity(r) for r in reversed(records)]
        nxt = pinned.advanced(since + 1) if since >= 1 else None
        return self.listing(items, nxt.encode() if nxt else None)

    # ---------------------------------------------------------------- overview

    def overview(self) -> dict[str, Any]:
        self.require("overview")
        kids = self._hot_children()
        attention = self.attention_items()
        hot = sorted(self.state["work"].items(), key=lambda kv: self._updated_at(kv[1]), reverse=True)
        hot.sort(key=lambda kv: kv[0] not in self._attention_ids())  # stable: attention first, then most recent
        work = [self.work_item(wid, unit, kids=kids, with_children=False) for wid, unit in hot[:OVERVIEW_WORK]]
        active = sorted((i, inv) for i, inv in self.state["invocations"].items()
                        if inv["status"] == "active" and not _custody(inv))
        runs = [self.invocation_item(i, inv, self.state) for i, inv in active[:OVERVIEW_RUNS]]
        activity = self.activity_list(limit=OVERVIEW_ACTIVITY, cursor=None)["data"]["items"]
        recent = []
        if is_v2(self.state):
            for r in list(self.state.get("recent") or [])[::-1][:OVERVIEW_RECENT]:
                if r["id"] in self.state["work"]:
                    continue
                unit = self.archive.archived_unit(self.state, r["id"])
                if unit is not None:
                    recent.append(self.work_item(r["id"], unit, kids=kids, with_children=False))
        archived = (self.state.get("cold") or {}).get("archived") or {}
        open_units = sum(1 for u in self.state["work"].values() if u["state"] not in T.TERMINAL)
        summary = (f"{open_units} open unit{'s' if open_units != 1 else ''}, {len(active)} active "
                   f"invocation{'s' if len(active) != 1 else ''}, {len(attention)} needing attention")
        return self.envelope({
            "project": self.project()["data"], "health": self.health(), "summary": rich(summary),
            "work": work, "runs": runs, "attention": attention[:OVERVIEW_ATTENTION], "activity": activity,
            "counts": {"work": {"open": open_units, "done": int(archived.get("done", 0)),
                                "cancelled": int(archived.get("cancelled", 0))},
                       "runs": len(active), "attention": len(attention)},
            "capabilities": self.capabilities_data(), "recent": recent,
        })

    # ---------------------------------------------------------------- maps (register F20.8, S1)
    #
    # Derived navigation context, never authority (T5-INV-01): read lock-free through the server's MapsReader,
    # bounded and checked, never generated from a request (the change note §4.1), and labelled on every response.
    # A missing, corrupt or unreadable selected map is data on /maps, never a refusal (T5-INV-04); a named one that
    # the strict reader refuses is 422 MAP_ARTIFACT_CORRUPT.

    def _maps(self) -> MapsReader:
        if self.maps is None:
            raise AssertionError("the maps routes need the server's MapsReader")
        return self.maps

    def _vocab(self) -> dict[str, frozenset[str]]:
        return MV.vocabulary(MR.load())

    def _head_ref(self) -> str:
        """The authoritative branch's ref, from this request's manifest: resolved by freshness's own ``rev-parse``
        (one git process), never through the engine's locked or unbounded paths."""
        return f"refs/heads/{self.s.manifest['repository']['authoritative_branch']}"

    def _registry(self) -> Registry:
        return self._maps().registry()

    def _selected_root(self, registry: Registry) -> str | None:
        entry = registry.selected("structural") if registry.state not in (NONE, INVALID) else None
        return str(entry["sha256"]) if entry else None

    def _stored(self, root: str, *, detail: bool = False,
                budget: int | None = None) -> tuple[dict[str, Any], dict[str, Any], MV.Detail | None, int]:
        """A stored map's summary (without ``selected``), what its freshness reads, its projected detail when asked
        for, and the bytes read for it (0 on a cache hit). ``NOT_FOUND`` and ``MAP_ARTIFACT_CORRUPT`` as the strict
        reader decides; with ``budget``, a read that would exceed it raises ``_OverBudget`` instead."""
        reader = self._maps()
        st = reader.stat(root)
        key = (root, MS.file_identity(st))
        known = reader.summaries.get(key)  # only AVAILABLE summaries are kept: a corrupt map is read again
        cached = reader.details.get(key)
        if known is not None and cached is not None and (cached[1] is not None or not detail):
            return known["summary"], cached[0], cached[1], 0
        if budget is not None and st.st_size > budget:
            raise _OverBudget
        vocab = self._vocab()
        record, identity = reader.load(root, st)  # a corrupt verdict is never cached (review of #178, finding A)
        key = (root, identity)
        summary = MV.summary(root, selected=False, record=record, vocab=vocab)
        inputs = record["inputs"]
        slim = {"artifact_sha256": record["artifact_sha256"], "source_tree": record["source_tree"],
                "generator": record["generator"],
                "inputs": {"path_listing_sha256": inputs["path_listing_sha256"],
                           "metadata": [{"path": i["path"], "git_oid": i["git_oid"]} for i in inputs["metadata"]]}}
        projected = MV.project_record(record, vocab) if detail else None
        size = 256 + sum(len(i["path"]) + 128 for i in inputs["metadata"]) + (projected.size if projected else 0)
        reader.summaries.put(key, {"status": "AVAILABLE", "summary": summary})
        reader.details.put(key, (slim, projected), size)
        return summary, slim, projected, st.st_size

    def _map_freshness(self, slim: dict[str, Any], against: str | None, tally: MV.Tally) -> dict[str, Any]:
        fresh = MF.freshness(self.s.engine.repo_root, slim, against or self._head_ref(), MSV.identity(),
                             timeout=MAPS_GIT_TIMEOUT_S)
        return MV.map_freshness(fresh, tally)

    def _head_commit(self) -> str | None:
        """The authoritative head, resolved on its own: only when no structural freshness resolved it already."""
        try:
            commit, _, _ = gitobjects.resolve(self.s.engine.repo_root, self._head_ref(), timeout=MAPS_GIT_TIMEOUT_S)
        except (MapCurrentnessUnproven, GitError):
            return None
        return commit

    def _architecture_evidence(self, evidence_id: str) -> dict[str, Any]:
        """The architecture reference's evidence metadata, lock-free (``locate_evidence``). The registry allows any
        1 to 64 characters, so the id is checked before any path is built (the change note §4.1)."""
        if not (isinstance(evidence_id, str) and _architecture_id(evidence_id)):
            raise ValidationFailed("the selected architecture evidence id is not a valid opaque id",
                                   reason="malformed_id")
        # Archived evidence goes through the derived history index: never the control lock, never a long wait
        # (review of #178, finding 1). A busy index or a commit that moved history meanwhile is "read again later".
        # Only the race and a busy index are "read again later" (review of #178, findings B and C): a query of an
        # index already synced meets a lock as SQLite's own error; a missing or altered record is damage, which
        # maps.service.architecture reports UNAVAILABLE.
        try:
            with self.archive.lockfree_reads(ARCHIVE_WAIT_S):
                meta, _, _ = self.locate_evidence(evidence_id)
        except (HistoryMoved, LockTimeout, sqlite3.DatabaseError) as exc:
            raise _HistoryBusy from exc
        return meta

    def _architecture_freshness(self, record: dict[str, Any], head: str | None) -> dict[str, Any]:
        """``record_freshness`` against ``head``, bounded and cached by ``(evidence, observed commit, head)``: a git
        that does not answer in time, or a partial clone that could fetch lazily, is UNKNOWN (never cached)."""
        observed = (record.get("evaluated_snapshot") or {}).get("base_revision")
        key = (str(record.get("id")), observed if isinstance(observed, str) else None, head)
        cache = self._maps().architecture
        known = cache.get(key) if head is not None else None
        if known is not None:
            return known
        repo = self.s.engine.repo_root
        try:
            gitobjects.refuse_lazy_fetch(repo, timeout=MAPS_GIT_TIMEOUT_S)
            fresh = record_freshness(repo, record, head, timeout=MAPS_GIT_TIMEOUT_S)
        except MapCurrentnessUnproven:
            return {"status": "UNKNOWN", "detail": "a partial clone on a git that cannot be told not to fetch "
                                                   "missing objects lazily"}
        except GitError as exc:
            LOG.warning("architecture freshness: %s", exc.message)
            return {"status": "UNKNOWN", "detail": "git did not answer within the dashboard's bound; read again later"
                    if (exc.details or {}).get("reason") == "timeout" else "git could not compare the commits"}
        if head is not None:  # an unresolved head is never cached: the next read resolves it again
            cache.put(key, fresh)
        return fresh

    def maps_overview(self, *, against: str | None) -> dict[str, Any]:
        reader = self._maps()
        registry = self._registry()
        tally = MV.Tally()
        if registry.state == INVALID:
            registry_reasons = [reason("MAP_REGISTRY_INVALID", f"{reason('MAP_REGISTRY_INVALID')['message']} "
                                                               f"({registry.problem})")]
        elif registry.state == NONE:
            registry_reasons = [reason("MAP_NONE")]
        else:
            registry_reasons = []
        structural_view: dict[str, Any] = {"state": "UNAVAILABLE", "reasons": [], "summary": None, "freshness": None}
        head: str | None = None
        root = self._selected_root(registry)
        if registry.state == INVALID:
            structural_view["reasons"] = list(registry_reasons)
        elif root is None:
            structural_view["reasons"] = [reason("MAP_NONE")]
        else:
            try:
                summary, slim, _, _ = self._stored(root)
            except NotFound:
                structural_view["reasons"] = [reason("MAP_MISSING")]
            except MapArtifactCorrupt as exc:
                why = str(exc.details.get("reason") or "unreadable")
                structural_view["reasons"] = [reason("MAP_CORRUPT", f"{reason('MAP_CORRUPT')['message']} ({why})")]
                structural_view["summary"] = MV.summary(root, selected=True, record=None, vocab=self._vocab(),
                                                        corrupt=why)
            except OSError as exc:  # the selected map is data on /maps, even when it cannot be read
                LOG.warning("selected map unreadable: %s", type(exc).__name__)
                structural_view["reasons"] = [reason("MAP_UNREADABLE")]
            else:
                freshness = self._map_freshness(slim, against, tally)
                structural_view = {"state": "AVAILABLE", "reasons": [], "summary": {**summary, "selected": True},
                                   "freshness": freshness}
                if against is None:
                    head = freshness["against_commit"]
        architecture = None
        if registry.selected("architecture") is not None and registry.state not in (NONE, INVALID):
            if head is None:
                head = self._head_commit()
            resolved = head
            try:
                ref = MSV.architecture(self.s.engine, registry.data, evidence=self._architecture_evidence,
                                       head=lambda: resolved, freshness=self._architecture_freshness)
            except _HistoryBusy:
                selected = registry.selected("architecture") or {}
                ref = {"evidence_id": selected.get("evidence_id"),
                       "freshness": {"status": "UNKNOWN", "detail": "the history index is busy or history moved "
                                                                   "during the read; read again later"}}
            architecture = MV.architecture(ref, valid_id=_architecture_id, tally=tally)
        return self.envelope({
            "map_revision": registry.revision, "registry": {"state": registry.state, "reasons": registry_reasons},
            "structural": structural_view, "architecture": architecture, "stored": {"count": len(reader.roots())},
            "label": MV.LABEL})

    def maps_list(self, *, limit: int, cursor: str | None, source_revision: str | None) -> dict[str, Any]:
        """The stored maps, keyset-paged by root, with a bounded scan (the change note §4.2): at most
        :data:`SCAN_MAPS` maps examined and :data:`SCAN_BYTES` read per request; past either the page says so and
        the cursor continues."""
        reader = self._maps()
        filters = {"source_revision": source_revision}
        after = None
        if cursor is not None:
            after = cursors.Keyset.parse(cursor, route="maps-structural", project=self.s.project_id, filters=filters,
                                         limit=limit).after
        selected = self._selected_root(self._registry())
        roots = reader.roots()
        rest = [r for r in roots if after is None or r > str(after)]
        vocab = self._vocab()
        items: list[dict[str, Any]] = []
        examined, spent, last, more, incomplete = 0, 0, None, False, False
        for root in rest:
            if len(items) >= limit:
                more = True
                break
            if examined >= SCAN_MAPS:
                more = incomplete = True
                break
            try:
                # the first map is always read, so a page makes progress whatever the bound
                summary, _, _, n = self._stored(root, budget=None if examined == 0 else SCAN_BYTES - spent)
            except _OverBudget:
                more = incomplete = True
                break
            except NotFound:  # removed since the listing: it is simply not there
                examined, last = examined + 1, root
                continue
            except MapArtifactCorrupt as exc:
                summary = MV.summary(root, selected=False, record=None, vocab=vocab,
                                     corrupt=str(exc.details.get("reason") or "unreadable"))
                n = 0
            examined, spent, last = examined + 1, spent + n, root
            if source_revision is not None and summary["source_revision"] != source_revision:
                continue
            items.append({**summary, "selected": root == selected})
        next_cursor = (cursors.Keyset("maps-structural", self.s.project_id, filters, limit, last).encode()
                       if more and last is not None else None)
        scan = ({"examined": examined, "stored": len(roots), "reasons": [reason("MAP_SCAN_LIMIT")]}
                if incomplete else None)
        return self.envelope({"items": items, "next_cursor": next_cursor, "scan_incomplete": scan,
                              "label": MV.LABEL})

    def map_detail(self, root: str, *, against: str | None, section: str | None) -> dict[str, Any]:
        selected = self._selected_root(self._registry())
        summary, slim, detail, _ = self._stored(root, detail=True)
        assert detail is not None
        tally = MV.Tally()
        freshness = self._map_freshness(slim, against, tally)
        names = [section] if section is not None else list(MV.SECTIONS)
        return self.envelope({
            "summary": {**summary, "selected": root == selected}, "freshness": freshness, "limits": detail.limits,
            "inputs": detail.inputs, "sections": {n: detail.sections[n] for n in names},
            "cut_strings": MV.clamp(tally.cut + sum(detail.section_cuts[n] for n in names)),
            "dropped_fields": MV.clamp(detail.dropped_fields), "label": MV.LABEL})

    def map_inputs(self, root: str, *, limit: int, cursor: str | None) -> dict[str, Any]:
        """A map's ``inputs.metadata``, paged by position in the record's sorted list, which is immutable because the
        artifact is content-addressed; the cursor names the root, never a path."""
        reader = self._maps()
        record, _ = reader.load(root, reader.stat(root))
        metadata = record["inputs"]["metadata"]
        filters = {"root": root}
        start = 0
        if cursor is not None:
            start = int(cursors.Keyset.parse(cursor, route="maps-inputs", project=self.s.project_id, filters=filters,
                                             limit=limit, position=True).after)
            if not 0 < start < len(metadata):
                raise cursors.CursorError("CURSOR_INVALID", "the cursor's position is outside this map's inputs")
        tally = MV.Tally()
        items = [MV.project_input(i, tally) for i in metadata[start:start + limit]]
        end = start + limit
        next_cursor = (cursors.Keyset("maps-inputs", self.s.project_id, filters, limit, end).encode()
                       if end < len(metadata) else None)
        return self.envelope({"root": root, "items": items, "next_cursor": next_cursor,
                              "cut_strings": MV.clamp(tally.cut), "dropped_fields": MV.clamp(tally.dropped_fields),
                              "label": MV.LABEL})

    def map_diff(self, a: str, b: str) -> dict[str, Any]:
        """Two stored maps compared, typed (never a map generated from a request: the change note §4.1)."""
        reader = self._maps()
        stats = (reader.stat(a), reader.stat(b))  # both exist before either is read: 404 before 422
        first, _ = reader.load(a, stats[0])
        second = first if b == a else reader.load(b, stats[1])[0]
        return self.envelope(MV.diff(first, second, self._vocab()))


class _OverBudget(Exception):
    """A stored map the scan's byte budget cannot read in this request."""


class _HistoryBusy(Exception):
    """The architecture evidence's archived lookup met a busy index or a moved history: ``UNKNOWN``, not gone.
    Not an ``AEWError``, so ``maps.service.architecture`` does not report it ``UNAVAILABLE``."""


def _architecture_id(value: str) -> bool:
    return len(value) <= EVIDENCE_ID_MAX and bool(OPAQUE_ID.fullmatch(value))  # no trailing newline


def scrub(value: Any) -> Any:
    """The second layer behind the allowlist: the engine's redaction of credential strings and verifiers."""
    return redact(value)
