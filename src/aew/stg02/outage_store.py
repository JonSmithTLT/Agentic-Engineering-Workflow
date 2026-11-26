"""Read O-02's allowed facts from a single committed snapshot, without a writer or service."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew.dashboard.projections import Projector
from aew.dashboard.reader import Snapshot
from aew.engine import gates, outbox
from aew.engine.api import Engine
from aew.engine.archive_ops import ARCHIVE_SCHEMAS, CLOSURE, evidence_pins, is_v2, pinned_records, unit_pins
from aew.engine.base import POLICY_PINS
from aew.engine.store import ControlStore, read_lock_free
from aew.errors import AEWError
from aew.harness import broker_liveness, contract, event_spool, notify, runlog
from aew.knowledge.manifest import MANIFEST
from aew.stg02 import wire
from aew.stg02.outage import ISSUER, POLICY, RECIPIENT, Request, refuse
from aew.stg02.outage_host import g3_present
from aew.stg02.reads import (
    axis_reported,
    axis_unavailable,
    committed_waiting,
    continuation_item,
    run_data,
    work_revision,
)
from aew.stg02.world import AXES, WAITING_STATES
from aew.util import load_yaml, parse_frontmatter, sha256_bytes

HISTORICAL = "historical"
UNAVAILABLE = "unavailable"
STALE = "stale"


def _member(refs: list[dict[str, Any]]) -> dict[str, Any]:
    return {"visibility": "partial_visible" if refs else "unknown", "refs": refs[:50]}


def _field(path: str, source: dict[str, Any]) -> dict[str, Any]:
    return {"field_path": f"data.{path}", "source": source}


def _clock(epoch: Any) -> str | None:
    try:
        return wire.utc(datetime.fromtimestamp(float(epoch), UTC))
    except (ValueError, TypeError, OverflowError, OSError):
        return None


class OutageStore:
    """An O-02 request reads the store directly; it never consults a derived history index or repairs a pin."""

    @classmethod
    def open(cls, root: Path, now: str) -> OutageStore:
        return cls(root, ControlStore(root).read_committed(), now)

    def __init__(self, root: Path, state: dict[str, Any], now: str) -> None:
        self.root = root.resolve()
        self.state = state
        self.now = now
        self.scope = f"aew:project:{state['project_id']}"
        self.version = f"aew:rev:{state['revision']}"
        self.disclosure = {"form": "full", "policy_ref": POLICY, "scope_ref": self.scope,
                           "effective_recipient_ref": RECIPIENT, "qualified_release": False}
        self.limitations: set[str] = set()
        self.notes: list[str] = []
        self._pins: dict[tuple[str, str | None], tuple[str, bytes | None]] = {}
        self._archived: dict[str, dict[str, Any]] | None = None
        self._entries: dict[str, dict[str, Any]] = {}
        self._closure: dict[str, list[tuple[str, str]]] = {}
        self.engine = Engine(self.root.parent, self.root)

    def project(self, request: Request) -> list[dict[str, Any]]:
        self._check_transitions()
        self._pin(MANIFEST, self.state.get("manifest_sha256"))
        for rel, digest in (self.state.get(POLICY_PINS) or {}).items():
            self._pin(rel, digest)
        projection = request.route.projection
        if request.route.mode == "list":
            lead_attached = self.state["lead"]["status"] != "vacant"
            active = any(inv["status"] == "active" for inv in self.state["invocations"].values())
            if lead_attached or active:
                self._partial("The committed state names a Lead or invocation that may still be writing.")
        if projection == "attention":
            return self.attention()
        handlers = {"waiting": self.waiting, "attachments": self.attachments, "work": self.work,
                    "runs": self.runs, "continuation": self.continuation, "packages": self.packages,
                    "assurance": self.assurance, "resolve": self.resolve}
        assert projection in handlers
        return handlers[projection](request)

    def _partial(self, note: str, *, unavailable: bool = False) -> None:
        self.limitations.add("partial_source")
        if unavailable:
            self.limitations.add("source_unavailable")
        if note not in self.notes:
            self.notes.append(note)

    def _check_transitions(self) -> None:
        last = None
        try:
            records = outbox.read_transitions(self.root, -1, self.state["revision"], outbox=self.state.get("outbox"))
            for record in records:
                last = record
            expected = (self.state.get("last_transition") or {}).get("h")
            if expected and (last or {}).get("h") != expected:
                self._partial("The transition log does not reach the committed control state's hash.")
        except (AEWError, OSError, ValueError, KeyError):
            self._partial("The transition log is incomplete or failed its hash chain check.")

    def _pin(self, rel: str, expected: str | None) -> tuple[str, bytes | None]:
        key = (rel, expected)
        if key in self._pins:
            return self._pins[key]
        try:
            candidate = (self.root / rel).resolve()
            inside = candidate.is_relative_to(self.root)
            keepout = any(candidate.is_relative_to(self.root / name) for name in ("local", "state"))
            raw = read_lock_free(candidate) if inside and not keepout and candidate == self.root / rel else None
        except (OSError, RuntimeError, ValueError):
            raw = None
        if raw is None:
            value = (UNAVAILABLE, None) if expected else (HISTORICAL, None)
            if expected:
                self._partial(f"Pinned record missing or unreadable: {rel}")
        elif expected != sha256_bytes(raw):
            value = (STALE, None)
            self._partial(f"Pinned record hash mismatch: {rel}")
        else:
            value = (HISTORICAL, raw)
        self._pins[key] = value
        return value

    def _stamp(self, owner: str, kind: str, ident: str, state: str = HISTORICAL,
               at: str | None = None) -> dict[str, Any]:
        return wire.stamp(owner, f"aew:{kind}:{ident}", self.scope, self.version, at or self.now,
                          coverage_ref=self.scope, issuer_ref=ISSUER, observation_state=state)

    def _item(self, resource: str, ref: dict[str, Any], source: dict[str, Any], data: dict[str, Any],
              fields: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {"resource_type": resource, "ref": ref, "source": source, "disclosure": self.disclosure, "data": data,
                "links": [], "field_sources": fields or []}

    def _text(self, text: str, source: dict[str, Any]) -> dict[str, Any]:
        return {"text": text, "render": "inert_text",
                "provenance": {"kind": "service_observation", "owner_or_author": ISSUER,
                               "source_ref": source["fact_ref"]}}

    def _history(self) -> dict[str, dict[str, Any]]:
        if self._archived is not None:
            return self._archived
        self._archived = {}
        if not is_v2(self.state):
            return self._archived
        try:
            for entry in self.engine.archive.cold.walk(self.state["cold"]["root"]):
                ident = entry["id"]
                if entry["kind"] == "unit":
                    self._entries[ident] = entry
                elif entry["kind"] == "annotation" and entry.get("rel") == "moved_to":
                    parent = (entry.get("links", {}).get("moved_to") or [None])[0]
                    status, _ = self._pin(entry["path"], entry["sha256"])
                    if status == HISTORICAL:
                        self._archived[entry["subject"]] = {"parent": parent}
                elif entry["kind"] == "annotation" and entry.get("rel") == CLOSURE:
                    _, raw = self._pin(entry["path"], entry["sha256"])
                    if raw is not None:
                        self._closure[entry["subject"]] = pinned_records(entry, raw)
        except (AEWError, OSError, ValueError, KeyError):
            self._partial("The archived record chain is incomplete or failed its hash check.")
        return self._archived

    def _archived_unit(self, wid: str) -> dict[str, Any] | None:
        moves = self._history()
        entry = self._entries.get(wid)
        if entry is None:
            return None
        _, raw = self._pin(entry["path"], entry["sha256"])
        if raw is None:
            return {"kind": entry["unit_kind"], "title": entry["title"], "state": entry["state"],
                    "parent": entry.get("parent"), "_archive_pin_failed": True, **moves.get(wid, {})}
        try:
            bundle = load_yaml(raw.decode("utf-8"), source=entry["path"])
            if bundle["id"] != wid or bundle["schema"] not in ARCHIVE_SCHEMAS:
                raise ValueError("archive record identity or format mismatch")
            unit = {**bundle["unit"], **moves.get(wid, {})}
            unit["_cited_evidence_pins"] = ([(e["path"], e["sha256"]) for e in bundle.get("cited_evidence") or []]
                                             + self._closure.get(wid, []))
            return unit
        except (AEWError, TypeError, ValueError, KeyError):
            self._partial(f"Archived record could not be read: {wid}")
            return None

    def _unit(self, wid: str) -> dict[str, Any] | None:
        return self.state["work"].get(wid) or self._archived_unit(wid)

    def _unit_pins(self, unit: dict[str, Any]) -> tuple[str, dict[str, str]]:
        states = {}
        pending = unit_pins(unit) + list(unit.get("_cited_evidence_pins") or [])
        for rel, digest in pending:
            if rel in states:
                continue
            states[rel], raw = self._pin(rel, digest)
            if raw is not None:
                try:
                    pending.extend(evidence_pins(rel, raw))
                except (AEWError, ValueError):
                    states[rel] = STALE
                    self._partial(f"Pinned record could not be read in its recorded format: {rel}")
        return (STALE if unit.get("_archive_pin_failed") or any(v != HISTORICAL for v in states.values())
                else HISTORICAL), states

    @staticmethod
    def _work_ref(wid: str, unit: dict[str, Any]) -> dict[str, Any]:
        return wire.subject(unit["kind"], wid, revision=work_revision(unit))

    def _accepted(self, wid: str, unit: dict[str, Any]) -> dict[str, Any] | None:
        revision = work_revision(unit)
        return wire.subject("accepted_revision", wid, revision=revision) if revision else None

    def work(self, request: Request) -> list[dict[str, Any]]:
        if request.route.mode == "list":
            items = self.state["work"]
            kind = request.query.get("kind")
            return [self._work_item(wid, unit) for wid, unit in sorted(items.items())
                    if kind is None or unit["kind"] == kind]
        wid, unit = self._target_unit(request)
        return [self._work_item(wid, unit)]

    def _target_unit(self, request: Request) -> tuple[str, dict[str, Any]]:
        wid = request.path_values["work_id"]
        unit = self._unit(wid)
        if unit is None or unit["kind"] != request.path_values["work_kind"]:
            raise refuse("not_found_or_not_disclosable")
        return wid, unit

    def _work_item(self, wid: str, unit: dict[str, Any]) -> dict[str, Any]:
        state, pins = self._unit_pins(unit)
        parent_id = unit.get("parent")
        parent = self._unit(parent_id) if parent_id else None
        source = self._stamp("CNI", "work", wid, state)
        accepted = self._accepted(wid, unit)
        record = unit.get("record")
        record_state = pins.get(record or "", UNAVAILABLE if unit.get("_archive_pin_failed") else HISTORICAL)
        plan_path = (unit.get("plan") or {}).get("path")
        plan_state = pins.get(plan_path or "", state)
        narrative = f"{unit['title']} [{unit['state']}]"
        if unit.get("state_reason"):
            narrative += "\n" + unit["state_reason"]
        if record and record_state == HISTORICAL:
            _, raw = self._pin(record, unit.get("record_sha256"))
            if raw is not None:
                try:
                    _, body = parse_frontmatter(raw.decode("utf-8"), source=record)
                    if body.strip():
                        narrative += "\n" + body.strip()
                except (AEWError, ValueError):
                    record_state = STALE
                    self._partial(f"Pinned work record could not be read: {wid}")
                    source = self._stamp("CNI", "work", wid, STALE)
        completion = unit.get("completion_record")
        if completion and unit.get("completion_sha256"):
            completion_state, completion_raw = self._pin(completion, unit["completion_sha256"])
            if completion_raw is not None:
                try:
                    _, body = parse_frontmatter(completion_raw.decode("utf-8"), source=completion)
                    if body.strip():
                        narrative += "\n" + body.strip()
                except (AEWError, ValueError):
                    completion_state = STALE
                    self._partial(f"Pinned completion record could not be read: {wid}")
            if completion_state != HISTORICAL:
                record_state = completion_state
                source = self._stamp("CNI", "work", wid, STALE)
        kids = [self._work_ref(cid, child) for cid, child in sorted(self.state["work"].items())
                if child.get("parent") == wid]
        data = {"work_kind": unit["kind"], "accepted_revision": accepted,
                "parent": self._work_ref(parent_id, parent) if parent_id and parent else None,
                "child_refs": _member(kids),
                "accepted_interface_refs": _member([]),
                "composition": "not_applicable" if unit["kind"] == "ticket" else "not_established",
                "completion": ("blocked" if unit["state"] in WAITING_STATES else "not_established"
                               if unit["state"] in {"DONE", "CANCELLED"} else "in_progress"),
                "narrative": self._text(narrative, source)}
        return self._item("work", self._work_ref(wid, unit), source, data,
                          [_field("accepted_revision", self._stamp("WIS", "work", wid, plan_state)),
                           _field("narrative", self._stamp("WIS", "work", wid, record_state))])

    def waiting(self, request: Request) -> list[dict[str, Any]]:
        if g3_present():
            self._partial("Sources not read: G3's pending approvals and the G3 client's per-host approval records.",
                          unavailable=True)
        results = []
        for wid, unit in sorted(self.state["work"].items()):
            if unit["state"] not in WAITING_STATES:
                continue
            state, _ = self._unit_pins(unit)
            results.append(committed_waiting(wid, unit, self._stamp("CNI", "waiting", wid, state),
                                             self._stamp("WIS", "work", wid, state), self.disclosure))
        return results

    def attention(self) -> list[dict[str, Any]]:
        if event_spool.spool_dir(self.root).exists() or (notify.notify_dir(self.root) / notify.STATE).exists():
            self._partial("Sources not read: the notify spool and the notifier's summary.", unavailable=True)
        manifest: dict[str, Any] = {"project": {"id": self.state["project_id"], "name": self.state["project_id"]}}
        for unit in self.state["work"].values():
            self._unit_pins(unit)
        pin_failures = [f"Pinned record {rel} is {status}" for (rel, _), (status, _) in self._pins.items()
                        if status != HISTORICAL]
        contradictions = self.engine.contradictions(self.state, pinned_failures=pin_failures)
        snap = Snapshot(self.engine, self.state, manifest, {}, self.now)
        results = []
        for item in Projector(snap).attention_items(include_notifier=False, contradictions=contradictions):
            subject = item["subject"]
            wid = subject["id"]
            unit = self.state["work"].get(wid)
            state, _ = self._unit_pins(unit) if unit else (HISTORICAL, {})
            ident = item["id"]
            source = self._stamp("CNI", "attention", ident, state)
            fields = []
            if subject["kind"] == "invocation":
                run = ident.removeprefix("AT-")
                run_stamp, _, _ = self._run_observation(run)
                fields.append(_field("narrative", run_stamp))
                source = self._stamp("CNI", "attention", ident, run_stamp["observation_state"],
                                     run_stamp["observed_at"])
            category = {"decision_required": "decision_need", "blocker": "blocker",
                        "required_finding": "decision_need", "anomaly": "blocker"}[item["kind"]]
            summary = item.get("summary")
            text = (summary.get("text") if isinstance(summary, dict) else None) or item["title"]
            data = {"work": self._work_ref(wid, unit) if unit else None, "lane": "owner_issued", "category": category,
                    "root_lineage_ref": wid, "priority": "owner_normal", "summary_of_excess": False,
                    "narrative": self._text(text, fields[0]["source"] if fields else source)}
            results.append(self._item("attention", wire.subject("attention", ident), source, data, fields))
        return results

    def attachments(self, request: Request) -> list[dict[str, Any]]:
        lead = self.state["lead"]
        if lead["status"] == "vacant":
            if request.route.mode == "detail":
                raise refuse("not_found_or_not_disclosable")
            return []
        generation = str(lead["generation"])
        ident = f"aew:attachment:{generation}"
        if request.route.mode == "detail" and request.path_values["attachment_id"] != ident:
            raise refuse("not_found_or_not_disclosable")
        beat = broker_liveness.read(self.root, retry_missing=False)
        if not isinstance(beat, dict) or str(beat["generation"]) != generation:
            beat = {}
        observed = _clock(beat.get("beat_at"))
        harness = ("observed_stopped" if beat.get("closed_at") else "observed_running") if observed else "unknown"
        ref = wire.subject("attachment_generation", ident, generation=generation)
        data = {"generation": generation, "attachment_state": "attached", "aew_lead_authority": "active",
                "custody": "unknown", "harness_state": harness, "held_result_refs": [], "current_generation_ref": ref}
        field = self._stamp("HEB", "broker-beat", generation, STALE if observed else UNAVAILABLE, observed)
        return [self._item("attachment", ref, self._stamp("HEB", "attachment", generation), data,
                           [_field("harness_state", field)])]

    def _run_observation(self, run: str) -> tuple[dict[str, Any], str, str | None]:
        directory = runlog.run_dir(self.root, run)
        status, record = runlog.observed_status(directory)
        at = _clock(runlog.heartbeat_time(directory))
        if at is None and record and isinstance(record.get("updated_at"), str):
            try:
                at = wire.utc(wire.parse_time(record["updated_at"]))
            except (ValueError, OverflowError):
                pass
        return self._stamp("R01", "run", run, STALE if at else UNAVAILABLE, at), status, at

    def runs(self, request: Request) -> list[dict[str, Any]]:
        invocations = self.state["invocations"]
        if request.route.mode == "detail":
            ident = request.path_values["execution_id"]
            inv = invocations.get(ident)
            if inv is None or inv.get("kind") == "integration_attempt":
                raise refuse("not_found_or_not_disclosable")
            return [self._run_item(ident, inv)]
        return [self._run_item(ident, inv) for ident, inv in sorted(invocations.items())
                if inv.get("kind") != "integration_attempt"]

    def _run_item(self, ident: str, inv: dict[str, Any]) -> dict[str, Any]:
        wid = inv["work_unit"]
        unit = self._unit(wid)
        state, _ = self._unit_pins(unit) if unit else (HISTORICAL, {})
        work = self._work_ref(wid, unit) if unit else None
        runs = inv.get("runs") or []
        observation = self._stamp("R01", "invocation", ident, UNAVAILABLE)
        data: dict[str, Any] = {"source_epoch": self.scope,
                                "limitations": ["source_unqualified", "partial_observation"]}
        if runs:
            run = runs[-1]["run"]
            observation, status, at = self._run_observation(run)
            phase = ("REPORTED_ACTIVE" if status in (contract.STARTING, contract.RUNNING) else "REPORTED_FINISHED"
                     if status in contract.TERMINAL else "UNKNOWN")
            basis = observation["fact_ref"] if at else None
            data.update(phase=phase, phase_observation_class="AGENT_REPORTED" if at else "UNKNOWN",
                        phase_basis_ref=basis, started_at=runs[0].get("launched_at"))
            if status == contract.LOST:
                data.update(stall_assessment="POSSIBLE_STALL", stall_basis_ref=observation["fact_ref"])
                data["limitations"].append("progress_suspected")
        fields = [_field("phase", observation), _field("work_ref", self._stamp("WIS", "work", wid, state))]
        return self._item("run", wire.subject("execution_activity", ident),
                          self._stamp("R01", "invocation", ident, state), run_data(ident, work, **data), fields)

    def continuation(self, request: Request) -> list[dict[str, Any]]:
        wid = request.path_values["work_id"]
        unit = self._unit(wid)
        if not unit:
            raise refuse("not_found_or_not_disclosable")
        state, pins = self._unit_pins(unit)
        axes = {owner: axis_unavailable() for owner in AXES}
        stamps = {f"axis:{owner}": self._stamp(owner, "continuation", wid, UNAVAILABLE) for owner in AXES}
        source = self._stamp("WIS", "work", wid, pins.get(unit.get("record") or "", state))
        if source["observation_state"] != UNAVAILABLE:
            axes["WIS"] = axis_reported(self.scope, self.version, source["fact_ref"], self.now)
            if state == STALE:
                axes["WIS"]["reason_code"] = "PIN_MISMATCH"
        stamps["WIS"] = stamps["axis:WIS"] = source
        stamps["HEB"] = stamps["axis:HEB"]
        self._partial("One or more continuation owners have no committed source.", unavailable=True)
        return [continuation_item(self.disclosure, f"aew:continuation:{wid}", wid, work_revision(unit) or "none",
                                  "unavailable:HEB", "unavailable:HEB", axes, stamps, stamps["HEB"])]

    def packages(self, request: Request) -> list[dict[str, Any]]:
        wid, unit = self._target_unit(request)
        return self._unit_packages(wid, unit)

    def _unit_packages(self, wid: str, unit: dict[str, Any]) -> list[dict[str, Any]]:
        state, pins = self._unit_pins(unit)
        accepted = self._accepted(wid, unit)
        if accepted is None:
            if unit.get("evidence"):
                self._partial("Some evidence has no accepted work revision in the committed state.")
            return []
        results = []
        for record in unit.get("evidence") or []:
            evidence_id = record["id"]
            digest = f"sha256:{record['sha256']}"
            ref = wire.subject("package", evidence_id, revision=accepted["revision"])
            ref["package_digest"] = digest
            source = self._stamp("WIS", "evidence", evidence_id, STALE if state != HISTORICAL else HISTORICAL)
            data = {"work": self._work_ref(wid, unit), "digest": digest, "designation": "unknown",
                    "accepted_revision": accepted, "g1": "NOT_ESTABLISHED",
                    "baseline_limitations": ["source_unqualified"], "source_closure_ref": None}
            fields = [_field("g1", self._stamp("AEV", "evidence", evidence_id, UNAVAILABLE)),
                      _field("digest", self._stamp("WIS", "evidence", evidence_id, pins[record["path"]]))]
            results.append(self._item("package", ref, source, data, fields))
        return results

    def assurance(self, request: Request) -> list[dict[str, Any]]:
        kind, ident = request.path_values["subject_kind"], request.path_values["subject_id"]
        package = self._find_package(ident) if kind == "package" else None
        wid = package["data"]["work"]["id"] if package else ident
        unit = self._unit(wid)
        if unit is None or (package is None and unit["kind"] != kind):
            raise refuse("not_found_or_not_disclosable")
        return [self._assurance_item(wid, unit, package["ref"] if package else self._work_ref(wid, unit))]

    def _assurance_item(self, wid: str, unit: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        state, pins = self._unit_pins(unit)
        accepted = self._accepted(wid, unit) or wire.subject("accepted_revision", wid)
        determinations = [wire.subject("assurance_determination", ref["id"]) for ref in unit.get("evidence") or []
                          if ref["kind"] in {"verification", "review"} and pins[ref["path"]] == HISTORICAL]
        obligations = self._obligations(wid, unit)
        closure = {"owner": "AEV", "epoch": self.scope, "version": self.version,
                   "coverage_ref": self.scope, "completeness": "unknown"}
        data = {"target": target, "accepted_revision": accepted, "obligation_state": "unknown", "hold_state": "unknown",
                "readiness": "blocked" if unit["state"] in WAITING_STATES else "historical",
                "mandatory_obligations": _member(obligations), "determination_refs": _member(determinations),
                "applicable_hold_refs": _member([]), "g1_conformance": "NOT_ESTABLISHED",
                "roster_closure": {**closure, "domain": "mandatory_obligation_roster"},
                "hold_closure": {**closure, "domain": "applicable_hold_collection"}}
        item = self._item("assurance", wire.subject("assurance_basis", f"aew:assurance:{target['id']}",
                                                   revision=target["revision"]),
                          self._stamp("AEV", "assurance", target["id"], state), data)
        item["links"] = [{"relation": "determination", "target": ref, "availability": "navigable"}
                         for ref in determinations]
        return item

    def _obligations(self, wid: str, unit: dict[str, Any]) -> list[dict[str, Any]]:
        manifest_pin = self._pin(MANIFEST, self.state.get("manifest_sha256"))[1]
        if manifest_pin is None:
            return []
        manifest = load_yaml(manifest_pin.decode("utf-8"), source=MANIFEST)
        rel = (manifest.get("policy") or {}).get("gates")
        digest = (self.state.get(POLICY_PINS) or {}).get(rel)
        if not rel or not digest:
            return []
        _, raw = self._pin(rel, digest)
        if raw is None:
            return []
        policy = load_yaml(raw.decode("utf-8"), source=rel)
        try:
            work = {**self.state["work"], wid: unit}
            parent = unit.get("parent")
            while parent and parent not in work:
                ancestor = self._archived_unit(parent)
                if not ancestor:
                    return []
                work[parent] = ancestor
                parent = ancestor.get("parent")
            roster = gates.effective_obligations({**self.state, "work": work}, wid, policy)
        except (AEWError, KeyError, TypeError, ValueError):
            self._partial("The committed gate roster could not be read.")
            return []
        return [wire.subject("assurance_basis", f"aew:obligation:{wid}:{gate}") for gate in roster["gates"]]

    def _find_evidence(self, ident: str) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
        for wid, unit in self.state["work"].items():
            for ref in unit.get("evidence") or []:
                if ref["id"] == ident:
                    return wid, unit, ref
        self._history()  # the store's chain locates older evidence without creating a derived index
        for wid in self._entries:
            unit = self._archived_unit(wid)
            if unit:
                for ref in unit.get("evidence") or []:
                    if ref["id"] == ident:
                        return wid, unit, ref
        return None

    def _find_package(self, ident: str) -> dict[str, Any] | None:
        found = self._find_evidence(ident)
        if not found:
            return None
        wid, unit, _ = found
        return next((item for item in self._unit_packages(wid, unit) if item["ref"]["id"] == ident), None)

    def resolve(self, request: Request) -> list[dict[str, Any]]:
        kind, ident = request.query["kind"], request.query["id"]
        if kind in {"assurance_evidence", "assurance_determination"}:
            found = self._find_evidence(ident)
            if found:
                _, _, record = found
                if kind == "assurance_evidence" or record["kind"] in {"verification", "review"}:
                    status, _ = self._pin(record["path"], record["sha256"])
                    stamp = self._stamp("AEV", "evidence", ident, status if status != UNAVAILABLE else STALE)
                    return [self._resolved(request, wire.subject(kind, ident), stamp,
                                           "evidence" if kind == "assurance_evidence" else "determination")]
            raise refuse("not_found_or_not_disclosable")
        item = None
        if kind == "package":
            item = self._find_package(ident)
        elif kind == "assurance_basis" and ident.startswith("aew:assurance:"):
            target = ident.removeprefix("aew:assurance:")
            unit = self._unit(target)
            if unit and unit["kind"] in {"story", "ticket"}:
                item = self._assurance_item(target, unit, self._work_ref(target, unit))
            else:
                package = self._find_package(target)
                if package:
                    wid = package["data"]["work"]["id"]
                    unit = self._unit(wid)
                    if unit:
                        item = self._assurance_item(wid, unit, package["ref"])
        elif kind == "assurance_basis" and ident.startswith("aew:obligation:"):
            wid = ident.removeprefix("aew:obligation:").split(":", 1)[0]
            unit = self._unit(wid)
            if unit:
                ref = next((ref for ref in self._obligations(wid, unit) if ref["id"] == ident), None)
                if ref:
                    return [self._resolved(request, ref, self._stamp("AEV", "obligation", ident), "obligation")]
        if not item:
            raise refuse("not_found_or_not_disclosable")
        return [self._resolved(request, item["ref"], item["source"], "package" if kind == "package" else "obligation")]

    def _resolved(self, request: Request, ref: dict[str, Any], source: dict[str, Any], kind: str) -> dict[str, Any]:
        if any(ref[key] != request.query.get(key) for key in ("revision", "generation", "package_digest")):
            raise refuse("not_found_or_not_disclosable")
        data = {"target": ref, "record_kind": kind,
                "summary": None, "basis_refs": _member([]),
                "status": "historical" if source["observation_state"] == HISTORICAL else "limited",
                "source_basis_ref": source["fact_ref"]}
        return self._item("subject_detail", ref, source, data)
