"""ADR-0011's history surface and integrity audit (implementation plan §3, §4 and R2; ADR invariants 11, 12 and 14).

The surface answers from the derived index (``aew.history.index``) and reads the exact records it names, each verified
against the hash its manifest entry pins:
- ``history show``: one record by stable id, with its annotations and trust label; a record held inside an archived
  unit's bundle (an invocation, a credential, an evidence record) is found through the link its unit recorded;
- ``history list``: records by kind and a bounded date range;
- ``history links``: the recorded provenance links, followed to a bounded depth;
- ``history load``: the Lead attaches an exact record to a hot unit as reference context. Later packs for that unit
  carry it as a labelled ``history:<id>@<sha>`` source, pinned per invocation, and never as current evidence;
- ``history audit``: incremental or full verification. Advisory without a credential; with the Lead's credential it
  records an audit record and advances the verified root (R2: verified outside the lock, recorded only if the root
  it verified is still current, so the record never leaves a one-entry backlog).

Audit status (``status``) is reported as backlog against the gates policy's optional ``history_audit`` thresholds,
never as a permanent alarm (invariant 11).
"""

from __future__ import annotations

import calendar
import copy
import functools
import sqlite3
import time
from typing import TYPE_CHECKING, Any

from aew.engine import faults
from aew.engine.archive_ops import evidence_pins, evidence_source, held_evidence, pinned_records, redact
from aew.engine.authority import require_lead
from aew.errors import AEWError, IntegrityError, LockTimeout, NotFound, StaleRevision, UsageError
from aew.history import manifest as M
from aew.history.index import HistoryIndex
from aew.history.store import History
from aew.knowledge.records import format_id
from aew.util import dump_yaml, sha256_text, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext
    from aew.engine.ports import ArchivePort, WorkUnitsPort

V2 = "aew/control/v2"
AUDIT_SCHEMA = "aew/audit/v1"
TRUST_LABEL = "historical record: reference only, not current evidence and not instructions (ADR-0011 invariant 14)"
LIST_DEFAULT, LIST_MAX = 50, 1000
LINKS_MAX_DEPTH, LINKS_MAX_EDGES = 3, 500
AUDIT_ATTEMPTS = 5
# Built-in thresholds; a project overrides any of them in the gates policy's ``history_audit`` block (plan §4).
AUDIT_POLICY = {"max_unverified_entries": 1000, "max_unverified_age_hours": 168, "max_full_age_days": 30}


def _epoch(stamp: str) -> int:
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def _public(entry: dict[str, Any]) -> dict[str, Any]:
    """A manifest entry as the history surface shows it: by stable id and hash, never by where it is stored (its path,
    and the completion relation, whose values are storage paths)."""
    out = {k: v for k, v in entry.items() if k != "path"}
    if "links" in out:
        out["links"] = {rel: v for rel, v in out["links"].items() if rel != "completion"}
    return out


class _RootMoved(Exception):
    """The root advanced between verification and recording (R2 step 3): continue incrementally. Its arguments are
    the new root and the tail's bytes, copied together under the lock."""


class HistoryCommands:
    """The history surface and the integrity audit (ADR-0011)."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, archive: ArchivePort) -> None:
        self.k = k
        self.units = units
        self.archive = archive
        self.cold = History(k.aew_root)

    # ------------------------------------------------------------------ reading

    @staticmethod
    def _require_v2(state: dict[str, Any]) -> None:
        if state.get("schema") != V2:
            raise UsageError("this project's control state is v1: its finished work stays hot and it has no cold "
                             "history to read or audit")

    def _found(self, state: dict[str, Any], record_id: str) -> tuple[dict[str, Any], str | None]:
        """The manifest entry that holds ``record_id``, and the relation through which it holds it (None: the entry
        is the record itself; ``invocations``/``tokens``/``evidence``: the record is inside that unit's bundle)."""
        index = self.archive.index(state)
        entries = index.by_id(record_id)
        if entries:
            return entries[-1], None
        for rel in ("invocations", "tokens", "evidence"):  # a unit's bundle; a Lead record holds tokens too, and a
            #                                                 closure annotation the cited checks of an older bundle
            holders = [e for e in index.linked(rel, record_id) if e["kind"] in ("unit", "lead", "annotation")]
            if holders:
                return holders[-1], rel
        hot = record_id in state["work"] or record_id in state["invocations"] or record_id in state["tokens"]
        raise NotFound(f"no historical record {record_id}"
                       + ("; it is current work, read it with `aew work show` or `aew status`" if hot else ""))

    @staticmethod
    def _trust(source: str) -> dict[str, str]:
        return {"source": source, "label": TRUST_LABEL}

    def _evidence(self, bundle: dict[str, Any], evidence_id: str) -> dict[str, Any]:
        """An archived unit's evidence record, verified against the hash its unit recorded at ingest."""
        _, meta, body = held_evidence(self.k.aew_root, bundle, evidence_id)
        return {"meta": meta, "body": body}

    def history_show(self, record_id: str) -> dict[str, Any]:
        """An exact historical record by stable id, with its annotations and trust label (invariant 12)."""
        state = self.k.store.read()
        self._require_v2(state)
        entry, held_as = self._found(state, record_id)
        doc = self.archive.record(entry)
        if held_as is None:
            out: dict[str, Any] = {"id": record_id, "kind": entry["kind"], "trust": self._trust(entry["source"]),
                                   "entry": _public(entry), "record": redact(doc)}
            if entry["kind"] == "unit":
                unit = self.archive.archived_unit(state, record_id) or {}
                out["current_parent"] = unit.get("parent")
            index = self.archive.index(state)
            out["annotations"] = [{"entry": _public(a), "record": self.archive.record(a)}
                                  for a in index.annotations(record_id)]
            return out
        if held_as == "evidence":
            record = self._evidence(doc, record_id)
            source = evidence_source(record["meta"])
        else:
            record = doc.get(held_as, {}).get(record_id)
            if record is None:
                raise IntegrityError(f"{entry['id']}'s bundle does not hold {record_id}")
            source = "engine"
        return {"id": record_id, "kind": {"invocations": "invocation", "tokens": "credential",
                                          "evidence": "evidence"}[held_as],
                "held_by": entry.get("subject") or entry["id"], "trust": self._trust(source),
                "record": redact(record)}

    def history_list(self, *, kind: str | None = None, since: str | None = None, until: str | None = None,
                     limit: int = LIST_DEFAULT) -> dict[str, Any]:
        """Historical records by kind and a bounded date range, newest first (invariant 12)."""
        if kind is not None and kind not in M.ENTRY_KINDS:
            raise UsageError(f"--kind must be one of {', '.join(M.ENTRY_KINDS)}")
        if not 1 <= limit <= LIST_MAX:
            raise UsageError(f"--limit must be between 1 and {LIST_MAX}")
        for name, stamp in (("--since", since), ("--until", until)):
            if stamp is not None:
                try:
                    _epoch(stamp)
                except ValueError:
                    raise UsageError(f"{name} must be a UTC timestamp like 2026-10-02T00:00:00Z") from None
        state = self.k.store.read()
        self._require_v2(state)
        index = self.archive.index(state)
        moves = index.moves()
        items = []
        for e in index.list(kind=kind, since=since, until=until, limit=limit):
            item = {k: e[k] for k in ("seq", "kind", "id", "at", "source") if k in e}
            item.update({k: e[k] for k in ("state", "unit_kind", "title", "subject", "rel") if e.get(k) is not None})
            if e["kind"] == "unit":
                item["parent"] = moves[e["id"]] if e["id"] in moves else e.get("parent")  # moves applied
            items.append(item)
        return {"items": items, "limit": limit, "truncated": len(items) == limit}

    def history_links(self, record_id: str, *, depth: int = 1) -> dict[str, Any]:
        """The provenance and reference links recorded from and to a record, followed ``depth`` steps (bounded)."""
        if not 1 <= depth <= LINKS_MAX_DEPTH:
            raise UsageError(f"--depth must be between 1 and {LINKS_MAX_DEPTH}")
        state = self.k.store.read()
        self._require_v2(state)
        self._found(state, record_id)  # NotFound for an unknown id
        index = self.archive.index(state)
        seen, frontier, edges, truncated = {record_id}, [record_id], [], False
        for _ in range(depth):
            following = []
            for node in frontier:
                for link in index.links(node):
                    if link.get("rel") == "completion":  # a storage path, not a record id
                        continue
                    if len(edges) >= LINKS_MAX_EDGES:
                        truncated = True
                        break
                    if link not in edges:
                        edges.append(link)
                    other = link["to"] if link["from"] == node else link["from"]
                    if other not in seen:
                        seen.add(other)
                        following.append(other)
            frontier = following
        hot = set(state["work"]) | set(state["invocations"]) | set(state["tokens"])
        nodes = {n: "history" if index.by_id(n) else "hot" if n in hot else "other" for n in sorted(seen)}
        return {"id": record_id, "depth": depth, "edges": edges, "nodes": nodes, "truncated": truncated}

    def history_reindex(self) -> dict[str, Any]:
        """Rebuild the derived index from the manifest (it is never authority; losing it loses nothing)."""
        state = self.k.store.read()
        self._require_v2(state)
        index = HistoryIndex(self.k.aew_root)
        try:
            index.path.unlink(missing_ok=True)
            out = index.sync(state["cold"]["root"])
        except (OSError, sqlite3.Error) as exc:  # another process has the index open (Windows refuses the unlink)
            raise LockTimeout("the history index is in use by another AEW process; run `aew history reindex` again "
                              f"once it is free ({exc})") from None
        return {"ok": True, "mode": out["mode"], "entries": out["added"]}

    # ------------------------------------------------------------------ loading as reference (invariant 14)

    def history_load(self, *, token: str, expect_rev: int, record_id: str, into: str, reason: str) -> dict[str, Any]:
        """Attach an exact historical record to a hot unit as reference context: later packs for the unit carry it
        as a labelled ``history:<id>@<sha>`` source with its trust classification, never as current evidence."""
        if not (reason and reason.strip()):
            raise UsageError("loading a historical record needs a reason")
        with self.k.lead_txn(token, expect_rev, "history.load", reason=reason) as ctx:
            state = ctx.state
            self._require_v2(state)
            unit = self.units.unit(state, into)  # hot only: finished work does not change
            entry, held_as = self._found(state, record_id)
            doc = self.archive.record(entry)  # verified now, and again whenever a pack reads it
            refs = unit.setdefault("history_refs", [])
            if any(r["id"] == record_id for r in refs):
                raise UsageError(f"{record_id} is already loaded into {into}")
            if held_as is None:
                ref = {"id": record_id, "kind": entry["kind"], "entry_seq": entry["seq"], "sha256": entry["sha256"],
                       "source": entry["source"]}
            elif held_as == "evidence":  # an exact evidence record, pinned by the hash its unit recorded at ingest
                ev_ref, meta, _ = held_evidence(self.k.aew_root, doc, record_id)
                ref = {"id": record_id, "kind": "evidence", "entry_seq": entry["seq"], "held_by": entry["id"],
                       "sha256": ev_ref["sha256"], "source": evidence_source(meta)}
            else:
                held = "invocation" if held_as == "invocations" else "credential"
                raise UsageError(f"{record_id} is an archived {held}; load the unit that holds it ({entry['id']}) or "
                                 "one of its evidence records")
            ref.update(reason=reason, loaded_at=utc_now(), generation=state["lead"]["generation"])
            refs.append(ref)
            ctx.refs.append(f"history:{record_id}@{ref['sha256']}")
            ctx.summary = f"history:{record_id} loaded into {into} as reference context"
        return {"ok": True, "work_id": into, "loaded": ref, "revision": ctx.session.committed_revision}

    # ------------------------------------------------------------------ the integrity audit (R2)

    @staticmethod
    def _verified_point(cold: dict[str, Any]) -> dict[str, Any] | None:
        v = cold.get("verified")
        return {"count": v["count"], "h": v["h"]} if v else None

    def history_audit(self, *, full: bool = False, token: str | None = None,
                      expect_rev: int | None = None) -> dict[str, Any]:
        """Verify the history: from the last verified root (incremental) or from the beginning (``full``) through the
        current root. Without ``token`` it only reports (advisory: CI runs it this way). With the Lead's credential
        it records the audit and, if the history verified, advances the verified root to the one it commits."""
        # 1. The root and the tail's bytes, copied together under the control lock.
        with self.k.store.session() as s:
            state = copy.deepcopy(s.state)
            tail = self.cold.tail_bytes()
            if token is not None:
                require_lead(s.state, token, archived=self.k.archived_credential)
                if expect_rev is None:
                    raise StaleRevision("control mutations must state the expected revision (--expect-rev)",
                                        current=s.revision)
                if expect_rev != s.revision:
                    raise StaleRevision(f"expected control revision {expect_rev}, current is {s.revision}",
                                        expected=expect_rev, current=s.revision)
        self._require_v2(state)
        start = None if full else self._verified_point(state["cold"])
        target = dict(state["cold"]["root"])
        # 2. Verification outside the lock: sealed segments and records are immutable, and the tail is the copy.
        closure: dict[str, dict[str, int]] = {"legacy": {}, "closed": {}}
        report = self.cold.verify(target, start, tail_raw=tail, pinned=functools.partial(pinned_records,
                                                                                       closure=closure),
                                  nested=evidence_pins)
        checked = {"entries": report.entries, "records": report.records}
        problems, damaged = list(report.problems) + self._unclosed(closure), list(report.damaged)
        result = {"mode": "full" if full else "incremental", "from": start or {"count": 0, "h": M.GENESIS_H},
                  "through": {"count": target["count"], "h": target["head_h"]}, **checked,
                  "ok": not problems, "problems": problems}
        if full and not problems:
            result["index"] = self._check_index(target)
        faults.pause("history.audit_after_verify")  # tests hold here to land a commit in the R2 window
        if token is None:
            if problems:
                raise IntegrityError(f"history audit found {len(problems)} problem(s)", audit=result)
            return {"recorded": False, **result}
        for _ in range(AUDIT_ATTEMPTS):
            revision = self.k.store.read()["revision"]
            try:
                with self.k.lead_txn(token, revision, "history.audit") as ctx:
                    root = ctx.state["cold"]["root"]
                    if root != target and not problems:
                        raise _RootMoved(dict(root), self.cold.tail_bytes())  # 3. it moved: continue
                    audit_id = self._record_audit(ctx, full=full, start=result["from"], target=target,
                                                  checked=checked, problems=problems, damaged=damaged)
            except StaleRevision:
                continue  # a commit landed between reading the revision and taking the lock
            except _RootMoved as moved:
                moved_root, moved_tail = moved.args
                more = self.cold.verify(moved_root, {"count": target["count"], "h": target["head_h"]},
                                        tail_raw=moved_tail, pinned=pinned_records, nested=evidence_pins)
                checked = {"entries": checked["entries"] + more.entries,
                           "records": checked["records"] + more.records}
                problems, damaged, target = list(more.problems), list(more.damaged), moved_root
                result.update(through={"count": target["count"], "h": target["head_h"]}, **checked,
                              ok=not problems, problems=problems)
                continue
            result.update(recorded=True, audit=audit_id, revision=ctx.session.committed_revision)
            if problems:
                raise IntegrityError(f"history audit {audit_id} found {len(problems)} problem(s)", audit=result)
            return result
        raise LockTimeout(f"the history kept advancing during {AUDIT_ATTEMPTS} attempts to record the audit; "
                          "run it again")

    @staticmethod
    def _unclosed(closure: dict[str, dict[str, int]]) -> list[str]:
        """Units the audit walked whose bundle predates ``cited_evidence`` and whose closure annotation it did not
        see: the checks their verification cites are not covered, so the audit cannot pass (P3-R2). Not damage: the
        unit gets no finding, and ``aew migrate`` records the closure."""
        return [f"entry {seq} ({wid}): archived before bundles recorded the checks its verification cites, which no "
                "annotation pins yet; `aew migrate` records them" for wid, seq in sorted(closure["legacy"].items(),
                                                                                        key=lambda kv: kv[1])
                if wid not in closure["closed"]]

    def _check_index(self, root: dict[str, Any]) -> str:
        """A full audit also compares the derived index with the history, row by row (queries authenticate what they
        return, but cannot see a row altered so that it no longer matches): ``consistent``, or ``rebuilt`` when it
        differed. The index is derived, so a busy index, or a root that moved meanwhile, only defers the check."""
        try:
            index = HistoryIndex(self.k.aew_root)
            index.sync(root)
            return "consistent" if index.check() else "rebuilt"
        except (IntegrityError, LockTimeout, OSError, sqlite3.Error):
            return "not checked"

    def _record_audit(self, ctx: TxnContext, *, full: bool, start: dict[str, Any], target: dict[str, Any],
                      checked: dict[str, int], problems: list[str], damaged: list[dict[str, Any]]) -> str:
        """Stage the audit record and its manifest entry (appended first, by the finalizer). A passing audit sets the
        verified root to the one this commit makes current: the audited root plus the audit's own entry, which was
        checked here, locally (R2 steps 4-6). It never claims to have audited itself: its target is the root it
        verified."""
        state = ctx.state
        faults.hit("history.audit_before_record")
        n = state["counters"].get("audit", 0) + 1
        state["counters"]["audit"] = n
        audit_id, rel, at = format_id("AU", n), f"history/audits/{n:06d}.yaml", utc_now()
        text = dump_yaml({"schema": AUDIT_SCHEMA, "id": audit_id, "mode": "full" if full else "incremental",
                          "at": at, "from": start, "target": {"count": target["count"], "h": target["head_h"]},
                          **checked, "result": "fail" if problems else "pass", "problems": problems,
                          "actor": {"generation": state["lead"]["generation"]}})
        sha = History.write_record(ctx.session, rel, text)
        fields = {"kind": "audit", "id": audit_id, "path": rel, "sha256": sha, "at": at, "source": "engine",
                  "links": {}}
        ctx.entries.append(fields)
        ctx.refs.append(rel)
        if problems:
            for d in damaged:  # a damaged archived unit gets a finding about it; its bundle is never rewritten
                if d["kind"] == "unit":
                    self.archive.annotate(ctx, d["id"], "audit_finding", audit_id,
                                          note=f"{audit_id}: its record, or a record it pins, is missing or changed")
            ctx.summary = f"history audit {audit_id}: {len(problems)} problem(s); the verified root is unchanged"
            return audit_id
        entry = M.new_entry(target["count"] + 1, target["head_h"], fields)
        if sha256_text(text) != sha or M.fold({"count": target["count"], "h": target["head_h"]}, [entry],
                                              source=rel) != {"count": entry["seq"], "h": entry["h"]}:
            raise IntegrityError("the audit record does not link to the root it audited")  # 5. checked locally
        verified = {"count": entry["seq"], "h": entry["h"], "at": at, "audit": audit_id}
        state["cold"] = dict(state["cold"], verified=verified, **({"last_full": dict(verified)} if full else {}))
        ctx.summary = (f"history audit {audit_id} ({'full' if full else 'incremental'}): {checked['entries']} "
                       f"entries verified through {target['count']}")
        return audit_id

    # ------------------------------------------------------------------ audit status (§4; invariant 11)

    def audit_backlog(self, state: dict[str, Any]) -> int | None:
        """How many entries are not covered by the verified root (None: a v1 project, which has no cold history)."""
        if state.get("schema") != V2:
            return None
        root, verified = state["cold"]["root"], state["cold"].get("verified")
        if verified and verified["count"] == root["count"] and verified["h"] == root["head_h"]:
            return 0
        return root["count"] - (verified["count"] if verified and verified["count"] <= root["count"] else 0)

    def _policy(self) -> dict[str, Any]:
        try:
            block = self.k.policy("gates").get("history_audit") or {}
        except (AEWError, OSError):
            block = {}
        return {**AUDIT_POLICY, **block}

    def audit_status(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """The current root, the verified root, unverified additions (count and age) and the age of the last full
        verification, judged against the policy thresholds: backlog, not an alarm (plan §4)."""
        if state.get("schema") != V2:
            return None
        cold = state["cold"]
        root, verified, last_full = cold["root"], cold.get("verified"), cold.get("last_full")
        backlog = self.audit_backlog(state) or 0
        now, policy, over = time.time(), self._policy(), []
        oldest_at = cold.get("unverified_since") if backlog else None
        if backlog and oldest_at is None:  # a v2 state from before these dates were kept: once, from the index
            first = self.archive.index(state).by_seq(root["count"] - backlog + 1)
            oldest_at = first["at"] if first else None
        age_h = round((now - _epoch(oldest_at)) / 3600, 1) if oldest_at else 0.0
        if backlog > policy["max_unverified_entries"]:
            over.append(f"{backlog} unverified history entries (policy: at most {policy['max_unverified_entries']})")
        if age_h > policy["max_unverified_age_hours"]:
            over.append(f"the oldest unverified entry is {age_h} h old "
                        f"(policy: {policy['max_unverified_age_hours']} h)")
        full_age_d = round((now - _epoch(last_full["at"])) / 86400, 1) if last_full else None
        if root["count"]:
            # Never fully verified: due once the history itself is older than the threshold, not at its first entry.
            since_d = full_age_d
            if since_d is None:
                first_at = cold.get("first_at")
                if first_at is None:  # as above
                    first = self.archive.index(state).by_seq(1)
                    first_at = first["at"] if first else None
                since_d = round((now - _epoch(first_at)) / 86400, 1) if first_at else 0.0
            if since_d > policy["max_full_age_days"]:
                over.append(f"no full verification for {since_d} days (policy: {policy['max_full_age_days']} days)")
        return {"current": {"count": root["count"], "h": root["head_h"]}, "verified": verified,
                "unverified": {"entries": backlog, "oldest_at": oldest_at, "age_hours": age_h},
                "last_full": dict(last_full, age_days=full_age_d) if last_full else None,
                "policy": policy, "over_policy": over}
