"""ADR-0011 archival: finished work leaves the hot state at the commit that finishes it (implementation plan R3–R7).

``Archive.finalize`` is a transaction finalizer (R6). Inside every Lead transaction, just before the commit, it
moves each unit that is DONE or CANCELLED (deepest first) out of what is serialized:
- its bundle (``work/<id>/archive.yaml``: the unit, its invocations and their credentials) is written immutably and
  appended to the history manifest (``aew.history``), whose new root replaces ``cold.root``;
- each ancestor's summary is updated: archived child counts and the pinned additive digest accumulator (R3), the
  transitive count of DONE Tickets below it, and its integration frontier (R5);
- a hot dependency edge to an archived unit keeps the facts it needs in ``archived_refs`` (R4);
- a workspace retained after integration stays visible in ``retained_workspaces`` until its directory is gone (R7);
- ``recent`` keeps the last few archived units for views.

The working state the operation's own code holds is never changed (R6): the finalizer hands the store a projection
(``ctx.commit_state``). A v1 project is never archived; ``aew migrate`` (P2d) moves it to v2.

The cold side is also read here: an archived unit's bundle by id, and the bundle that holds an archived invocation
or credential, through the derived index (``aew.history.index``).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import hierarchy as H
from aew.errors import IntegrityError
from aew.history import manifest as M
from aew.history.index import HistoryIndex
from aew.history.store import History, annotation_rel, bundle_rel
from aew.knowledge.records import format_id
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_file, utc_now
from aew.workspace import git, worktrees

if TYPE_CHECKING:
    from aew.engine.base import Kernel, TxnContext

V2 = "aew/control/v2"
ARCHIVE_SCHEMA = "aew/archive/v1"
ANNOTATION_SCHEMA = "aew/annotation/v1"
LEAD_SCHEMA = "aew/lead-archive/v1"
LEAD_KINDS = frozenset({"lead", "handoff_offer"})
RECENT = 20
ACC_MOD = 2 ** 256


def is_v2(state: dict[str, Any]) -> bool:
    return state.get("schema") == V2


def child_leaf(work_id: str, state: str, completion_sha256: str | None) -> int:
    """An archived child's term in its parent's accumulator (R3); golden vectors pin it."""
    body = M.canonical_json({"id": work_id, "state": state, "completion_sha256": completion_sha256})
    return int.from_bytes(hashlib.sha256(b"aew-child-v2\0" + body).digest(), "big")


def add_leaf(acc_hex: str, leaf: int, sign: int = 1) -> str:
    return f"{(int(acc_hex, 16) + sign * leaf) % ACC_MOD:064x}"


SUBTREE = ("done_tickets_subtree", "cancelled_tickets_subtree")


def tickets_in(unit: dict[str, Any]) -> dict[str, int]:
    """The finished Tickets a unit accounts for, DONE and CANCELLED: itself, or (a parent) every one counted below
    it."""
    if unit["kind"] == "ticket":
        return {"done_tickets_subtree": int(unit["state"] == "DONE"),
                "cancelled_tickets_subtree": int(unit["state"] == "CANCELLED")}
    s = H.archived_summary(unit)
    return {k: s[k] for k in SUBTREE}


def _add_counts(unit: dict[str, Any], counts: dict[str, int], sign: int) -> None:
    s = H.archived_summary(unit)
    for k, n in counts.items():
        s[k] += sign * n
    unit["archived_children"] = s


def integrated_commits(unit: dict[str, Any]) -> dict[str, str]:
    """The integrated commits a unit adds to its ancestors' frontiers (R5): its own, or (a parent) its frontier."""
    if unit["kind"] == "ticket":
        commit = (unit.get("integration") or {}).get("commit")
        return {commit: unit["id"]} if commit and unit.get("mutating") and unit["state"] == "DONE" else {}
    return dict(unit.get("integration_frontier") or {})


class Archive:
    """Archival at commit time, and the reading of archived records."""

    def __init__(self, k: Kernel) -> None:
        self.k = k
        self.history = History(k.aew_root)

    # ------------------------------------------------------------------ the finalizer (R6)

    def finalize(self, ctx: TxnContext) -> None:
        state = ctx.state
        if not is_v2(state):
            return
        work = state["work"]
        order = sorted((w for w, u in work.items() if u["state"] in H.TERMINAL),
                       key=lambda w: (-H.depth(state, w), w))
        retained = self._retained(state, order)
        archived = set(order)
        lead_ended = self._ended_lead_credentials(state)
        retired = self._retired_observations(state, order)
        # Removing a retired observation is an obligation that outlives its invocation: it stays listed until the
        # directory is gone, and every commit retries it, so a crash or a failed removal never loses it.
        ctx.after_commit.extend(lambda p=o["path"]: self._prune_observation(p) for o in retired)
        if not order and not ctx.annotations and not lead_ended \
                and retained == state.get("retained_workspaces", []) \
                and retired == state.get("retired_observations", []) and self._refs_unchanged(state, archived):
            return
        entries, facts, recent, gone_invocations, gone_tokens = [], {}, [], set(), set()
        for wid in order:
            unit = work[wid]
            invocations = [i for i in unit.get("invocations", []) if i in state["invocations"]]
            tokens = self._tokens_of(state, invocations)
            if unit.get("completion_record") and not unit.get("completion_sha256"):
                unit["completion_sha256"] = sha256_file(self.k.aew_root / unit["completion_record"])
            bundle = dump_yaml({
                "schema": ARCHIVE_SCHEMA, "id": wid, "unit": unit,
                "invocations": {i: state["invocations"][i] for i in invocations},
                "tokens": {t: state["tokens"][t] for t in tokens}})
            sha = self.history.write_record(ctx.session, bundle_rel(wid), bundle)
            at = ((unit.get("history") or [{}])[-1].get("at")) or utc_now()
            entries.append(self._entry(wid, unit, sha, at, invocations, tokens))
            facts[wid] = self._facts(unit, sha)
            recent.append({"id": wid, "kind": unit["kind"], "state": unit["state"], "title": unit["title"], "at": at,
                           "parent": unit.get("parent")})
            self._join(state, unit.get("parent"), dict(unit, id=wid), subtree=False)
            gone_invocations.update(invocations)
            gone_tokens.update(tokens)
        entries += self._annotation_entries(ctx)
        if lead_ended:
            entries.append(self._lead_entry(ctx.session, state, lead_ended))
            gone_tokens.update(lead_ended)
        root = state["cold"]["root"]
        if entries:
            root = self.history.append(ctx.session, root, entries)
        hot = {w: u for w, u in work.items() if w not in archived}
        projected = dict(state)
        projected["work"] = hot
        projected["invocations"] = {i: v for i, v in state["invocations"].items() if i not in gone_invocations}
        projected["tokens"] = {t: v for t, v in state["tokens"].items() if t not in gone_tokens}
        counts = Counter({"done": 0, "cancelled": 0, **(state["cold"].get("archived") or {})})
        counts.update(work[w]["state"].lower() for w in order)
        projected["cold"] = dict(state["cold"], root=root, archived=dict(sorted(counts.items())))
        projected["recent"] = (list(state.get("recent", [])) + recent)[-RECENT:]
        projected["archived_refs"] = self._archived_refs(state, hot, facts)
        projected["retained_workspaces"] = retained
        projected["retired_observations"] = retired
        ctx.commit_state = projected

    # ------------------------------------------------------------------ ended Lead credentials

    @staticmethod
    def _ended_lead_credentials(state: dict[str, Any]) -> list[str]:
        current = state["lead"].get("token_id")
        return sorted(t for t, rec in state["tokens"].items()
                      if rec["kind"] in LEAD_KINDS and rec.get("revoked_at") and t != current)

    def _lead_entry(self, session: Any, state: dict[str, Any], ended: list[str]) -> dict[str, Any]:
        """Ended Lead and handoff-offer credentials leave the hot state, one record per change of the seat: a superseded
        Lead presenting one again is told so (R7), and the hot state does not grow with the number of generations."""
        state["counters"]["lead_archive"] = state["counters"].get("lead_archive", 0) + 1
        n = state["counters"]["lead_archive"]
        rid, rel = f"LEAD-{n:04d}", f"history/lead/{n:06d}.yaml"
        sha = self.history.write_record(session, rel, dump_yaml({
            "schema": LEAD_SCHEMA, "id": rid, "generation": state["lead"]["generation"],
            "tokens": {t: state["tokens"][t] for t in ended}}))
        return {"kind": "lead", "id": rid, "path": rel, "sha256": sha, "at": utc_now(), "source": "engine",
                "links": {"tokens": ended}}

    def end_lead_credentials(self, session: Any) -> None:
        """For the Lead's own commits outside ``lead_txn`` (acquire, handoff accept, takeover): archive the credentials
        the change of seat just ended, in the same commit."""
        state = session.state
        if not is_v2(state):
            return
        ended = self._ended_lead_credentials(state)
        if not ended:
            return
        entry = self._lead_entry(session, state, ended)
        for t in ended:
            del state["tokens"][t]
        state["cold"] = dict(state["cold"], root=self.history.append(session, state["cold"]["root"], [entry]))

    # ------------------------------------------------------------------ annotations (moves of archived units, R3)

    def annotate(self, ctx: TxnContext, subject: str, rel: str, obj: str | None, *, decision: str | None = None,
                 note: str | None = None) -> str:
        """Record a later fact about an archived unit: an immutable annotation and its manifest entry, written by this
        transition's finalizer. The unit's bundle is never rewritten (ADR-0011)."""
        state = ctx.state
        state["counters"]["annotation"] = state["counters"].get("annotation", 0) + 1
        an_id = format_id("AN", state["counters"]["annotation"])
        ctx.annotations.append({"id": an_id, "subject": subject, "rel": rel, "object": obj, "decision": decision,
                                "note": note, "at": utc_now(), "generation": state["lead"]["generation"]})
        return an_id

    def _annotation_entries(self, ctx: TxnContext) -> list[dict[str, Any]]:
        if not ctx.annotations:
            return []
        index = self._index(ctx.state)
        written: Counter[str] = Counter()
        out = []
        for a in ctx.annotations:
            subject = [e for e in index.by_id(a["subject"]) if e["kind"] == "unit"][-1]
            written[a["subject"]] += 1
            rel = annotation_rel(a["subject"], len(index.annotations(a["subject"])) + written[a["subject"]])
            record = dump_yaml({"schema": ANNOTATION_SCHEMA, "id": a["id"],
                                "subject": {"id": a["subject"], "entry_seq": subject["seq"],
                                            "bundle_sha256": subject["sha256"]},
                                "rel": a["rel"], "object": a["object"], "at": a["at"],
                                "actor": {"generation": a["generation"]}, "decision": a["decision"],
                                "source": "engine", "note": a["note"]})
            sha = self.history.write_record(ctx.session, rel, record)
            out.append({"kind": "annotation", "id": a["id"], "path": rel, "sha256": sha, "at": a["at"],
                        "subject": a["subject"], "rel": a["rel"], "source": "engine",
                        "links": {a["rel"]: [a["object"]] if a["object"] else []}})
        return out

    @staticmethod
    def _retired_observations(state: dict[str, Any], order: list[str]) -> list[dict[str, str]]:
        """Observation worktrees whose invocation is archived (by this commit or an earlier one) and that are still on
        disk: ``retired_observations``, until each directory is gone."""
        out = {o["path"]: o for o in state.get("retired_observations", []) if Path(o["path"]).exists()}
        for wid in order:
            for inv_id in state["work"][wid].get("invocations", []):
                path = ((state["invocations"].get(inv_id) or {}).get("observation") or {}).get("path")
                if path and Path(path).exists():
                    out[path] = {"invocation": inv_id, "path": path}
        return [out[p] for p in sorted(out)]

    def _prune_observation(self, path: str) -> None:
        """Remove a retired observation worktree of an archived invocation, after the commit. A failure leaves it
        listed in ``retired_observations``; the next commit retries it."""
        if Path(path).exists():
            worktrees.remove(self.k.repo_root, path)

    @staticmethod
    def _tokens_of(state: dict[str, Any], invocations: list[str]) -> list[str]:
        """Every credential an invocation ever held: current, rotated (runs) and any other issued to it."""
        ids = set(invocations)
        out = {state["invocations"][i]["token_id"] for i in invocations}
        out.update(r["token_id"] for i in invocations for r in state["invocations"][i].get("runs") or []
                   if r.get("token_id"))
        out.update(t for t, rec in state["tokens"].items() if rec["scope"].get("invocation_id") in ids)
        return sorted(t for t in out if t in state["tokens"])

    @staticmethod
    def _entry(wid: str, unit: dict[str, Any], sha: str, at: str, invocations: list[str],
               tokens: list[str]) -> dict[str, Any]:
        links = {"depends_on": sorted({e["id"] for e in unit.get("depends_on", [])}),
                 "invocations": invocations, "tokens": tokens,
                 "evidence": sorted({e["id"] for e in unit.get("evidence", [])}),
                 "integration_commit": [c] if (c := (unit.get("integration") or {}).get("commit")) else [],
                 "completion": [unit["completion_record"]] if unit.get("completion_record") else []}
        return {"kind": "unit", "id": wid, "path": bundle_rel(wid), "sha256": sha, "at": at, "state": unit["state"],
                "unit_kind": unit["kind"], "title": unit["title"], "parent": unit.get("parent"), "source": "engine",
                "links": {k: v for k, v in links.items() if v}}

    @staticmethod
    def _facts(unit: dict[str, Any], sha: str) -> dict[str, Any]:
        """What a hot dependency edge needs to know about an archived unit (R4)."""
        out: dict[str, Any] = {"kind": unit["kind"], "mutating": unit.get("mutating"), "state": unit["state"],
                               "bundle_sha256": sha}
        if (unit.get("integration") or {}).get("commit"):
            out["integration_commit"] = unit["integration"]["commit"]
        record = (unit.get("execution") or {}).get("record")
        if record:
            out["record"] = record
        if unit.get("integration_frontier"):
            out["integration_frontier"] = unit["integration_frontier"]
        if unit.get("completion_sha256"):
            out["completion_sha256"] = unit["completion_sha256"]
        return out

    def _join(self, state: dict[str, Any], parent: str | None, unit: dict[str, Any], *, subtree: bool) -> None:
        """An archived child joins ``parent``'s summary (R3): its count and leaf, and for every ancestor from
        ``parent`` up, the DONE Tickets it accounts for and its integrated commits (R5). At archival only the unit
        itself is new to its ancestors (its descendants were counted when they were archived); a move brings its whole
        subtree (``subtree``)."""
        if not parent:
            return
        p = state["work"][parent]
        s = H.archived_summary(p)
        s["done" if unit["state"] == "DONE" else "cancelled"] += 1
        s["acc"] = add_leaf(s["acc"], child_leaf(unit["id"], unit["state"], unit.get("completion_sha256")))
        p["archived_children"] = s
        counts = tickets_in(unit) if subtree or unit["kind"] == "ticket" else {}
        commits = integrated_commits(unit) if subtree or unit["kind"] == "ticket" else {}
        for anc in [parent, *H.ancestors(state, parent)]:
            a = state["work"][anc]
            _add_counts(a, counts, +1)
            for commit, via in sorted(commits.items()):
                a["integration_frontier"] = self._advance_frontier(a.get("integration_frontier") or {}, commit, via)

    def _leave(self, state: dict[str, Any], parent: str | None, unit: dict[str, Any]) -> None:
        """An archived child leaves ``parent``'s summary (a move): its count and leaf, and the DONE Tickets it
        accounts for on every ancestor. The frontiers keep its commits: that over-approximates what those ancestors
        need integrated, so it fails closed (R5)."""
        if not parent:
            return
        p = state["work"][parent]
        s = H.archived_summary(p)
        s["done" if unit["state"] == "DONE" else "cancelled"] -= 1
        s["acc"] = add_leaf(s["acc"], child_leaf(unit["id"], unit["state"], unit.get("completion_sha256")), -1)
        p["archived_children"] = s
        counts = tickets_in(unit)
        for anc in [parent, *H.ancestors(state, parent)]:
            _add_counts(state["work"][anc], counts, -1)

    def move_hot_subtree(self, state: dict[str, Any], unit: dict[str, Any], old: str | None,
                         new: str | None) -> None:
        """A hot Story or Epic moves: the archived Tickets below it (its subtree counts) and their integrated commits
        (its frontier) leave its old ancestors and join its new ones. Its own children summary moves with it."""
        if unit["kind"] == "ticket":
            return
        counts = tickets_in(unit)
        if old:
            for anc in [old, *H.ancestors(state, old)]:
                _add_counts(state["work"][anc], counts, -1)
        if new:
            commits = integrated_commits(unit)
            for anc in [new, *H.ancestors(state, new)]:
                a = state["work"][anc]
                _add_counts(a, counts, +1)
                for commit, via in sorted(commits.items()):
                    a["integration_frontier"] = self._advance_frontier(a.get("integration_frontier") or {}, commit, via)

    def archived_tickets_below(self, state: dict[str, Any], parent: str, finished: str) -> list[str]:
        """The archived Tickets in ``finished`` anywhere below ``parent``, by id (read on request: a refusal names
        them)."""
        out: list[str] = []
        stack = [parent, *H.descendants(state, parent)]
        while stack:
            for wid, u in self.archived_children(state, stack.pop()):
                if u["kind"] != "ticket":
                    stack.append(wid)
                elif u["state"] == finished:
                    out.append(wid)
        return sorted(out)

    def move(self, ctx: TxnContext, work_id: str, unit: dict[str, Any], new_parent: str | None, *,
             decision: str | None, note: str) -> str:
        """Move an archived unit (R3): it leaves its parent's summary, joins the new one with its whole subtree, and the
        move is recorded as a ``moved_to`` annotation; the bundle is never rewritten."""
        subject = dict(unit, id=work_id)
        self._leave(ctx.state, unit.get("parent"), subject)
        self._join(ctx.state, new_parent, subject, subtree=True)
        # The bounded ``recent`` projection is hot state that views read: it follows the move (the bundle and its
        # manifest entry never change; the annotation records the move).
        ctx.state["recent"] = [dict(r, parent=new_parent) if r["id"] == work_id else r
                               for r in ctx.state.get("recent", [])]
        return self.annotate(ctx, work_id, "moved_to", new_parent, decision=decision, note=note)

    def _advance_frontier(self, frontier: dict[str, str], commit: str, via: str) -> dict[str, str]:
        """The antichain of integrated commits under git ancestry (R5): every member being in a base is exactly every
        integrated descendant being in it."""
        repo = self.k.repo_root
        if any(m == commit or git.is_ancestor(commit, m, cwd=repo) for m in frontier):
            return frontier
        kept = {m: v for m, v in frontier.items() if not git.is_ancestor(m, commit, cwd=repo)}
        kept[commit] = via
        return dict(sorted(kept.items()))

    @staticmethod
    def _retained(state: dict[str, Any], order: list[str]) -> list[dict[str, Any]]:
        """Retained workspaces of archived Tickets, until their directory is gone (R7)."""
        out = [r for r in state.get("retained_workspaces", []) if Path(r["path"]).exists()]
        for wid in order:
            ws = state["work"][wid].get("workspace") or {}
            if str(ws.get("status", "")).startswith("retained") and Path(ws["path"]).exists():
                out.append({"work_id": wid, "id": ws["id"], "path": ws["path"], "status": ws["status"]})
        return out

    @staticmethod
    def _edge_targets(hot: dict[str, Any]) -> Counter[str]:
        return Counter(e["id"] for u in hot.values() for e in u.get("depends_on", []) if e["id"] not in hot)

    def _refs_unchanged(self, state: dict[str, Any], archived: set[str]) -> bool:
        current = state.get("archived_refs", {})
        targets = self._edge_targets(state["work"])
        return {k: v["refs"] for k, v in current.items()} == dict(targets)

    def _archived_refs(self, state: dict[str, Any], hot: dict[str, Any],
                       new_facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """``archived_refs`` for the hot edges after this commit: each archived target an edge still names, with how
        many edges name it (R4). Facts come from this commit's archival, the previous map, or (an edge created to a
        unit archived earlier) the cold index."""
        previous = state.get("archived_refs", {})
        out = {}
        for target, refs in sorted(self._edge_targets(hot).items()):
            facts = new_facts.get(target) or previous.get(target) or self.facts_from_cold(state, target)
            if facts is None:
                raise IntegrityError(f"a dependency edge names {target}, which is neither hot nor archived")
            out[target] = {**{k: v for k, v in facts.items() if k != "refs"}, "refs": refs}
        return out

    # ------------------------------------------------------------------ reading archived records

    def _index(self, state: dict[str, Any]) -> HistoryIndex:
        """The index synced to the cold root of ``state``. Inside a transaction that root is the committed one; a
        reader outside the lock re-reads the state if a later commit replaced the tail meanwhile."""
        for attempt in range(3):
            index = HistoryIndex(self.k.aew_root)
            try:
                index.sync(state["cold"]["root"])
                return index
            except IntegrityError:
                if self.k.store.held or attempt == 2:
                    raise
                state = self.k.store.read()
        raise AssertionError("unreachable")

    def bundle(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """An archived unit's bundle (verified against its manifest entry), or None if it was never archived."""
        if not is_v2(state):
            return None
        entries = [e for e in self._index(state).by_id(work_id) if e["kind"] == "unit"]
        return self._load(entries[-1]) if entries else None

    def bundle_holding(self, state: dict[str, Any], rel: str, target: str) -> dict[str, Any] | None:
        """The bundle of the archived unit whose entry links ``rel`` to ``target`` (an invocation or a credential)."""
        if not is_v2(state):
            return None
        entries = self._index(state).linked(rel, target)
        return self._load(entries[-1]) if entries else None

    def _load(self, entry: dict[str, Any]) -> dict[str, Any]:
        raw = (self.k.aew_root / entry["path"]).read_bytes()
        if sha256_bytes(raw) != entry["sha256"]:
            raise IntegrityError(f"archived record {entry['path']} does not hold the content its entry pins",
                                 path=entry["path"])
        doc = load_yaml(raw.decode("utf-8"), source=entry["path"])
        if doc.get("schema") not in {ARCHIVE_SCHEMA, LEAD_SCHEMA} or doc.get("id") != entry["id"]:
            raise IntegrityError(f"{entry['path']} is not the archive record of {entry['id']}")
        return doc

    def facts_from_cold(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        doc = self.bundle(state, work_id)
        if doc is None:
            return None
        return self._facts(doc["unit"], sha256_bytes((self.k.aew_root / bundle_rel(work_id)).read_bytes()))

    def archived_credential(self, state: dict[str, Any], token_id: str) -> dict[str, Any] | None:
        """The credential record of an archived invocation (R7: a presented archived credential is stale authority,
        never an unknown one)."""
        doc = self.bundle_holding(state, "tokens", token_id)
        return (doc or {}).get("tokens", {}).get(token_id)

    def archived_invocation(self, state: dict[str, Any], inv_id: str) -> dict[str, Any] | None:
        doc = self.bundle_holding(state, "invocations", inv_id)
        return (doc or {}).get("invocations", {}).get(inv_id)

    def archived_unit(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """An archived unit as it stands now: its bundled record with later moves applied (``moved_to``
        annotations), marked ``archived``. None if it was never archived."""
        doc = self.bundle(state, work_id)
        if doc is None:
            return None
        unit = dict(doc["unit"], archived=True)
        moves = [a for a in self._index(state).annotations(work_id) if a["rel"] == "moved_to"]
        if moves:
            history = list(unit.get("parent_history") or [])
            for a in moves:
                to = (a.get("links", {}).get("moved_to") or [None])[0]
                history.append({"from": unit.get("parent"), "to": to, "at": a["at"], "annotation": a["id"]})
                unit["parent"] = to
            unit["parent_history"] = history
        return unit

    def rehydrate(self, state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
        """A copy of ``state`` with one archived unit, its invocations and credentials back in it, and its archived
        ancestors (a read walks the unit's ancestry; at most a Story and an Epic): a read about that unit (its gates,
        an invocation's pack, a run) then answers exactly as it did before archival (R7). None if the unit was never
        archived."""
        doc = self.bundle(state, work_id)
        if doc is None:
            return None
        unit = self.archived_unit(state, work_id)
        work = {**state["work"], work_id: unit}
        parent = unit.get("parent")
        while parent and parent not in work:  # a hot unit never has an archived ancestor, so this stops at hot work
            ancestor = self.archived_unit(state, parent)
            if ancestor is None:
                raise IntegrityError(f"{work_id}'s ancestor {parent} is neither hot nor archived")
            work[parent] = ancestor
            parent = ancestor.get("parent")
        return dict(state, work=work, invocations={**state["invocations"], **doc.get("invocations", {})},
                    tokens={**state["tokens"], **doc.get("tokens", {})})

    def rehydrate_invocation(self, state: dict[str, Any], inv_id: str) -> dict[str, Any] | None:
        """``rehydrate`` for the unit that archived invocation ``inv_id``."""
        doc = self.bundle_holding(state, "invocations", inv_id)
        return self.rehydrate(state, doc["id"]) if doc else None

    def archived_units(self, state: dict[str, Any], finished: str) -> list[dict[str, Any]]:
        """The manifest entries of every archived unit in ``finished`` (DONE or CANCELLED), each with its current
        parent (later moves applied): an explicit history query."""
        if not is_v2(state):
            return []
        index = self._index(state)
        moves = index.moves()
        return [dict(e, parent=moves[e["id"]]) if e["id"] in moves else e for e in index.units(finished)]

    def archived_child_ids(self, state: dict[str, Any], parent: str) -> list[str]:
        """The ids of the archived units whose current parent is ``parent``, from the index alone (no bundle is read):
        archived under it and not moved since, or moved to it last."""
        if not is_v2(state):
            return []
        index = self._index(state)
        out = []
        candidates = {e["id"]: e.get("parent") for e in index.children(parent)}
        candidates.update({a["subject"]: None for a in index.linked("moved_to", parent)})
        for wid, archived_parent in sorted(candidates.items()):
            if wid in state["work"]:
                continue
            moves = [a for a in index.annotations(wid) if a["rel"] == "moved_to"]
            current = (moves[-1].get("links", {}).get("moved_to") or [None])[0] if moves else archived_parent
            if current == parent:
                out.append(wid)
        return out

    def archived_children(self, state: dict[str, Any], parent: str) -> list[tuple[str, dict[str, Any]]]:
        """The archived units whose current parent is ``parent`` (archived under it, or moved to it since), with their
        records: what a closeout or a tree reads about one parent, never the whole history (R3)."""
        if not is_v2(state):
            return []
        index = self._index(state)
        candidates = {e["id"] for e in index.children(parent)}
        candidates |= {a["subject"] for a in index.linked("moved_to", parent)}
        out = []
        for wid in sorted(candidates - set(state["work"])):
            unit = self.archived_unit(state, wid)
            if unit is not None and unit.get("parent") == parent:
                out.append((wid, unit))
        return out
