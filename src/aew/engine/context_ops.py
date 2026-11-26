"""Context-pack assembly for invocations (WC §15.4; KC §15). Packs are rebuildable local data."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from aew import process_kind, roles
from aew.engine import scope_ops as SC
from aew.engine.archive_ops import evidence_reference, held_evidence, reference_summary
from aew.engine.base import TxnContext
from aew.errors import IntegrityError, NotFound
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.knowledge.records import read_record
from aew.maps import slices
from aew.skills import pins as skill_pins
from aew.snapshot import fingerprint
from aew.util import atomic_write, parse_frontmatter, sha256_bytes, sha256_text
from aew.workspace import git

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ArchivePort, WorkUnitsPort

AEW_EXCLUDE = ":(exclude).aew"


class _PackBase(NamedTuple):
    """What every pack reads first: the role card, the unit's record and accepted plan, and the adopted guardrails and
    checks. Each policy file is read once, so the checks a pack lists are the bytes whose hash it records."""

    card: dict[str, Any] | None
    record: Any
    plan: dict[str, Any] | None
    plan_text: str
    guard_raw: bytes
    checks_raw: bytes
    checks: dict[str, Any]


class ContextPacks:
    """Context packs for invocations (WC §15.4; KC §15). Packs are rebuildable local data."""

    def __init__(self, k: Kernel, *, units: WorkUnitsPort, archive: ArchivePort) -> None:
        self.k = k
        self.units = units
        self.archive = archive

    def _hierarchy_context(self, state: dict[str, Any], wid: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        from aew.engine import gates as G
        from aew.engine import hierarchy as H

        chain = []
        for anc in reversed(H.ancestors(state, wid)):
            a = state["work"][anc]
            record = read_record(self.k.aew_root / a["record"], "work-unit")
            meta = record.meta
            # The body and the whole acceptance: a plan assessor's preserved request (E160); no other pack shows them.
            chain.append({"id": anc, "kind": a["kind"], "title": a["title"], "risk_class": a["risk_class"],
                          "plan": (a.get("plan") or {}).get("accepted"),
                          "goal_backwards": (meta.get("acceptance") or {}).get("goal_backwards", []),
                          "body": record.body, "acceptance": meta.get("acceptance") or {}})
        obligations = G.effective_obligations(state, wid, {"risk_paths": {str(c): [] for c in range(5)}})
        inherited: dict[str, Any] = {"non_waivable": obligations["non_waivable"], "floor": obligations["floor"]}
        # A gate replaced on the record is shown with its correction, so the replaced name never reads as current
        # (ITEMS 55, addendum 2). Absent when there is none, so every other pack is unchanged.
        corrections = [{"unit": anc, **{k: c[k] for k in ("id", "replaced", "with")}}
                       for anc in reversed(H.ancestors(state, wid))
                       for c in (state["work"][anc].get("policy") or {}).get("corrections") or []]
        if corrections:
            inherited["corrections"] = corrections
        return chain, inherited

    def _input_summaries(self, inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each consumed input with what its record holds: the summary lines, and under ``open`` what its author
        recorded as unresolved, uncertain or a constraint (``ctxmod.open_items``; register E198), absent when it
        recorded none, so such a pack is what it was."""
        out = []
        for i in inputs:
            ev = next((e for e in E.scan(self.k.aew_root, i["from"])[0] if e["id"] == i["id"]), None)
            summary: list[str] = []
            left_open = ctxmod.open_items(ev) if ev else []
            if ev:
                d, r, pr = ev.get("discovery") or {}, ev.get("research") or {}, ev.get("proposal") or {}
                summary += [f"fact: {f['statement']}" for f in d.get("facts", [])]
                summary += [f"hypothesis: {h['statement']}" for h in d.get("hypotheses", [])]
                summary += [f"conclusion: {c}" for c in r.get("conclusions", [])]
                summary += [f"subject: {s.get('name')} {s.get('version') or ''} ({s.get('source')})"
                            for s in r.get("subjects", [])]
                if pr:
                    summary += [f"objective: {pr.get('objective')}", f"approach: {pr.get('approach')}"]
            out.append({**i, "summary": summary, **({"open": left_open} if left_open else {})})
        return out

    def _m2_pack_extras(self, state: dict[str, Any], inv: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
        """Hierarchy, inputs, record under review and child outputs (ADR-0007/0008). Deterministic."""
        from aew.engine import hierarchy as H

        wid = inv["work_unit"]
        extras: dict[str, Any] = {}
        chain, inherited = self._hierarchy_context(state, wid)
        extras["hierarchy"] = chain
        extras["inherited"] = inherited if (inherited["non_waivable"] or inherited["floor"] is not None) else None
        extras["inputs"] = self._input_summaries(inv.get("inputs") or [])
        execution = unit.get("execution") or {}
        if inv["role"] in {"investigator", "researcher", "planner"}:
            extras["expected_kind"] = execution.get("expected_kind")
            extras["attempt"] = inv.get("attempt")
        if inv.get("subject"):
            s = inv["subject"]
            ev = next((e for e in E.scan(self.k.aew_root, wid)[0] if e["id"] == s["id"]), None)
            if ev:
                content = {k: ev[k] for k in ("claim", "result", "discovery", "research", "proposal") if k in ev}
                _, body = parse_frontmatter((self.k.aew_root / ev["_path"]).read_text(encoding="utf-8"))
                from aew.util import dump_yaml
                extras["subject"] = {"id": s["id"], "sha256": s["sha256"], "kind": ev["kind"],
                                     "content": dump_yaml(content),
                                     "body": body, "observed_commit": ev["evaluated_snapshot"]["base_revision"]}
        if inv.get("scope") == E.ASSESSMENT_SCOPE:  # the preserved request beyond the unit's own record (E160)
            extras["request"] = [{k: a[k] for k in ("id", "kind", "title", "body", "acceptance")} for a in chain]
        if inv.get("scope") == "parent":
            baseline = unit.get("baseline_commit")
            commit = (inv.get("observation") or {}).get("commit")
            children = []
            kids = sorted([(cid, state["work"][cid]) for cid in H.children(state, wid)]
                          + self.archive.archived_children(state, wid))  # archived children, for this review only
            for cid, c in kids:
                entry = {"id": cid, "kind": c["kind"], "title": c["title"], "state": c["state"],
                         "completion_record": c.get("completion_record"),
                         "completion_sha256": self.units.completion_sha(state, cid) if cid in state["work"]
                         else c.get("completion_sha256")}
                rec = (c.get("execution") or {}).get("record")
                if rec and c["state"] == "DONE":
                    entry["record"] = rec["id"]
                integrated = (c.get("integration") or {}).get("commit") if c["state"] == "DONE" else None
                if integrated:
                    entry["integrated_commit"] = integrated
                    args = ("diff", "--no-color", "--no-renames") if inv["role"] == "reviewer" \
                        else ("diff", "--stat", "--no-renames")
                    entry["diff"] = git.git(*args, f"{integrated}^1", integrated, "--", ".", AEW_EXCLUDE,
                                            cwd=self.k.repo_root).stdout.decode("utf-8", "replace")
                    if baseline and git.is_ancestor(integrated, baseline, cwd=self.k.repo_root):
                        entry["before_baseline"] = True  # already in the baseline: absent from baseline..A
                children.append(entry)
            extras["children"] = children
            if baseline and commit:  # rendered even when empty: that is when it would hide a child's change
                extras["aggregate_diffstat"] = git.out("diff", "--stat", "--no-renames", baseline, commit, "--", ".",
                                                       AEW_EXCLUDE, cwd=self.k.repo_root)
        return extras

    def _history_refs(self, state: dict[str, Any], inv: dict[str, Any]) -> list[dict[str, Any]]:
        """The historical records the Lead loaded for this invocation's unit before it was dispatched (pinned on the
        invocation), each read and verified against its pinned hash (ADR-0011 invariant 14)."""
        out = []
        for ref in inv.get("history_refs") or []:
            if ref.get("held_by"):  # an evidence record inside an archived unit's bundle, pinned by its own hash
                entries = [e for e in self.archive.index(state).by_id(ref["held_by"]) if e["seq"] == ref["entry_seq"]]
                if not entries:
                    raise IntegrityError(f"loaded historical record {ref['id']}: its holder {ref['held_by']} is not "
                                         "in the history")
                ev_ref, meta, body = held_evidence(self.k.aew_root, self.archive.record(entries[-1]), ref["id"])
                if ev_ref["sha256"] != ref["sha256"]:
                    raise IntegrityError(f"loaded historical record {ref['id']}@{ref['sha256'][:12]} is not the one "
                                         f"{ref['held_by']} holds")
                out.append({**ref, "content": evidence_reference(meta, body)})
                continue
            entries = [e for e in self.archive.index(state).by_id(ref["id"]) if e["sha256"] == ref["sha256"]]
            if not entries:
                raise IntegrityError(f"loaded historical record {ref['id']}@{ref['sha256'][:12]} is not in the history")
            out.append({**ref, "content": reference_summary(entries[-1], self.archive.record(entries[-1]))})
        return out

    @staticmethod
    def _history_sources(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{"name": f"history:{r['id']}", "path": None, "sha256": r["sha256"], "trust": r["source"],
                 "reference": True} for r in refs]

    def _map_slice(self, inv: dict[str, Any], role_def: dict[str, Any], base: str | None,
                   record_meta: dict[str, Any], fresh: bool,
                   lead: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, list[str] | None]:
        """The structural map this pack carries (register F22.1 plan §5.4), as ``(the sources entry, the section's
        lines)``: when the pack is built (``fresh``), the selected map now, if the switch is on and the role's context
        names codebase_map; when it is regenerated, the entry the built pack pinned in its sources, whatever the switch
        or ``local/maps/`` say now, so a regenerated pack (and the ``launch.pack`` guard) never differs because of a
        map (PR #143 review, M1). ``lead``: the Lead whose transaction builds the pack, the only builder that
        refreshes a STALE or absent map for the work's base (``slices.pin``; ADR-0015, amended 2026-11-11). Never
        raises."""
        scope_paths = list((record_meta.get("scope") or {}).get("paths") or [])
        built = slices.pinned((inv.get("pack") or {}).get("sources"))
        if not fresh or built is not None:
            # An invocation has one map: a regenerated pack, or a second build in the transaction that dispatched it
            # (an observation pins its pack again once its attempt exists), takes the map the first build pinned,
            # so a refresh at dispatch runs at most once per invocation and its line stays in the pack.
            if built is None:
                return None, None
            return built, slices.lines(self.k.aew_root, self.k.repo_root, built, scope_paths)
        try:
            policy, _ = self.k.execution_policy()
        except Exception:  # an unreadable policy turns nothing on: a map never changes a pack by default
            return None, None
        if not slices.wanted(role_def, policy):
            return None, None
        if lead is None:
            return slices.pin(self.k.aew_root, self.k.repo_root, base, scope_paths)
        try:
            head = self.k.authoritative_commit()
        except Exception:  # no head to compare with: the refresh stores and pins, and selects nothing
            head = None
        return slices.pin(self.k.aew_root, self.k.repo_root, base, scope_paths, lead=lead, head=head)

    # ---- register F36: the recovery section of an invocation that replaces one (operator, 2026-11-26)

    @staticmethod
    def predecessor(state: dict[str, Any], inv_id: str) -> str | None:
        """The invocation ``inv_id`` replaces: the unit's latest earlier invocation of the same role and scope, when it
        ended without completing (cancelled, interrupted, superseded: any status but active or completed). Only for a
        role that produces the work (``RECOVERY_ROLES``), each of which is completed when its report is taken: an
        evaluator replaces nobody (a finished plan assessor is ended by `invoke cancel`, and a reviewer's verdict may
        be recorded before it is ingested, so their status says nothing of completing; review of #614, M1 and M2).
        None for a first invocation, and for one that follows completed work, such as a rework after a review."""
        inv = state["invocations"][inv_id]
        if inv.get("role") not in ctxmod.RECOVERY_ROLES:
            return None
        slot = (inv["role"], inv.get("scope") or "ticket")
        latest = None
        for other in (state["work"].get(inv["work_unit"]) or {}).get("invocations", []):
            if other == inv_id:
                break
            earlier = state["invocations"].get(other) or {}
            if (earlier.get("role"), earlier.get("scope") or "ticket") == slot:
                latest = other
        if latest is None or state["invocations"][latest]["status"] in {"active", "completed"}:
            return None
        return latest

    def recovery(self, state: dict[str, Any], inv_id: str) -> dict[str, Any] | None:
        """What a replacement invocation is told of the one it replaces, each fact read from its owner as it stands at
        dispatch and cut to the section's bounds (``aew.knowledge.context``): the predecessor's status (its
        invocation), why its credential ended (its token record), the evidence it produced (the evidence store, less
        any verdict), and for an implementer the workspace's paths against its base
        (``fingerprint.workspace_paths``). A role that works in a read-only observation inherits no workspace."""
        previous = self.predecessor(state, inv_id)
        if previous is None:
            return None
        inv, old = state["invocations"][inv_id], state["invocations"][previous]
        produced = sorted((e for e in E.scan(self.k.aew_root, inv["work_unit"])[0]
                           if e["producer"].get("invocation") == previous), key=lambda e: e.get("seq", 0))
        reason = (state["tokens"].get(old.get("token_id") or "") or {}).get("revoke_reason")
        out: dict[str, Any] = {
            "predecessor": previous, "role": old["role"], "scope": old.get("scope") or "ticket",
            "status": old["status"], "workspace_id": old.get("workspace_id"),
            "reason": ctxmod.bounded_text(reason) if reason else None,
            "evidence": ctxmod.recovery_evidence(produced)}
        ws = state["work"][inv["work_unit"]].get("workspace") or {}
        if inv["role"] != "implementer" or ws.get("id") != inv.get("workspace_id") or not ws.get("base_commit"):
            return out
        # Read straight after the dispatch's own snapshot of the same workspace: a workspace that cannot be read
        # has already refused the dispatch there.
        found = fingerprint.workspace_paths(Path(ws["path"]), ws["base_commit"], **self.k.check_cache_inputs())
        marked = {mark: set(found[mark]) for mark in ctxmod.RECOVERY_MARKS}
        paths = [{"path": ctxmod.bounded_text(path), **{mark: True for mark in ctxmod.RECOVERY_MARKS
                                                        if path in marked[mark]}}
                 for path in sorted({*found["changed"], *marked["staged"]})]
        out["workspace"] = {"id": ws["id"], "base": ws["base_commit"],
                            **{mark: len(marked[mark]) for mark in ctxmod.RECOVERY_MARKS},
                            "paths": ctxmod.bounded(paths, ctxmod.RECOVERY_MAX_PATHS)}
        return out

    @staticmethod
    def _recovery_sources(recovery: dict[str, Any] | None) -> list[dict[str, Any]]:
        """The pinned observation among the pack's sources, by its hash; nothing for a pack without the section."""
        if not recovery:
            return []
        return [{"name": f"recovery:{recovery['predecessor']}", "path": None,
                 "sha256": sha256_text(json.dumps(recovery, sort_keys=True, separators=(",", ":"))), "reference": True}]

    def _pack_base(self, inv: dict[str, Any], unit: dict[str, Any]) -> _PackBase:
        """The inputs both pack builders read first, with the policy files as adopted."""
        card = inv.get("card") or None
        record = read_record(self.k.aew_root / unit["record"], "work-unit")
        record = dataclasses.replace(record, meta=SC.effective_meta(record.meta, unit))  # the effective scope (E126)
        plan = unit.get("plan")
        plan_text = ""
        if plan:
            _, plan_text = parse_frontmatter((self.k.aew_root / plan["path"]).read_text(encoding="utf-8"))
        guard_raw = self.k.policy_bytes("guardrails")
        checks, checks_raw = self.k.policy_with_bytes("checks")
        return _PackBase(card, record, plan, plan_text, guard_raw, checks_raw, checks["checks"])

    def _base_sources(self, pb: _PackBase, role: str, unit: dict[str, Any], record_name: str) -> list[dict[str, Any]]:
        """The sources every pack records first, in this order. ``record_name`` names the unit's record:
        ``current_ticket`` for a Ticket's own work, ``current_work`` for a read-only invocation."""
        card, plan = pb.card or {}, pb.plan
        return [
            {"name": f"archetype:{role}", "path": f"aew/roles/archetypes/{role}.yaml", "sha256": None},
            {"name": f"role_card:{card.get('id')}", "path": card.get("path"), "sha256": card.get("sha256"),
             "version": card.get("version")},
            # the card's `skills:` as shipped at dispatch, by name, version and hash (the 2026-11-03 ruling, §3);
            # never its optional ones, so a listed skill adds nothing here (the 2026-11-04 ruling, §5)
            *skill_pins((card.get("content") or {}).get("skills") or []),
            {"name": record_name, "path": unit["record"], "sha256": unit["record_sha256"]},
            {"name": "accepted_plan", "path": plan["path"] if plan else None,
             "sha256": plan["sha256"] if plan else None},
            {"name": "guardrails", "path": self.k.manifest["policy"]["guardrails"],
             "sha256": sha256_bytes(pb.guard_raw)},
            {"name": "checks", "path": self.k.manifest["policy"]["checks"], "sha256": sha256_bytes(pb.checks_raw)},
        ]

    def pack_inputs(self, state: dict[str, Any], inv_id: str) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        """The pack's inputs and its sources, as regenerated: a structural map comes from what the built pack pinned."""
        return self._pack_inputs(state, inv_id, fresh_map=False)

    def _pack_inputs(self, state: dict[str, Any], inv_id: str, *,
                     fresh_map: bool, lead: dict[str, Any] | None = None
                     ) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        """``fresh_map``: the pack is being built now, so its map (if any) is the selected one (``build_pack``)."""
        inv = state["invocations"][inv_id]
        if inv.get("scope") in E.OBSERVER_SCOPES:
            return self._m2_pack_inputs(state, inv_id, fresh_map=fresh_map, lead=lead)
        role, wid = inv["role"], inv["work_unit"]
        unit = state["work"][wid]
        role_def = roles.archetype(role)
        pb = self._pack_base(inv, unit)
        card, record, plan = pb.card, pb.record, pb.plan
        snapshot = inv["snapshot"]
        cutoff = inv.get("evidence_seq_cutoff", 0)
        evidence = [e for e in E.scan(self.k.aew_root, wid)[0] if e.get("seq", 0) <= cutoff]
        history = self._history_refs(state, inv)
        fp = snapshot["relevant_inputs_fingerprint"]
        tree = fp.split(":", 1)[1]
        base = (unit.get("integration") or {}).get("base") if inv.get("scope") == "integration" \
            else (unit.get("workspace") or {}).get("base_commit")
        on_snapshot = [e for e in evidence if e["evaluated_snapshot"]["relevant_inputs_fingerprint"] == fp]
        impl = [e for e in on_snapshot if e["kind"] == "implementation_report"]
        summary = None
        if impl:
            i = impl[-1].get("implementation") or {}
            summary = {k: i.get(k, []) for k in ("files_changed", "checks_run", "deviations", "unexpected_findings")}
        failure = None
        if role == "implementer" and unit.get("failure_evidence"):
            fe = next((e for e in evidence if e["id"] == unit["failure_evidence"]), None)
            if fe:
                failure = {"id": fe["id"], "result": fe["result"],
                           "claims": fe["verification"]["claims"],
                           "suspected_cause": fe["verification"].get("suspected_cause")}
        map_source, map_lines = self._map_slice(inv, role_def, base, record.meta, fresh_map, lead)
        diff = diffstat = ""
        if base and role == "reviewer":
            diff = git.git("diff", "--no-color", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE,
                           cwd=self.k.repo_root).stdout.decode("utf-8", "replace")
        if base and role == "verifier":
            diffstat = git.out("diff", "--stat", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE,
                               cwd=self.k.repo_root)
        lines_changed = None
        if base and role == "reviewer" and SC.added_paths(unit):  # the add's proportion, for the review (m-c)
            numstat = git.out("diff", "--numstat", "-z", "--no-renames", base, tree, "--", ".", AEW_EXCLUDE,
                              cwd=self.k.repo_root)
            lines_changed = SC.lines_changed(numstat, SC.declared_scope(record.meta, unit), SC.added_paths(unit))
        inputs = ctxmod.PackInputs(
            invocation_id=inv_id, role=role, role_def=role_def, work_id=wid, title=unit["title"],
            scope=inv.get("scope", "ticket"), specialty=inv.get("specialty"), workspace=inv["workspace"],
            snapshot=snapshot, record_meta=record.meta, record_body=record.body, plan=plan, plan_text=pb.plan_text,
            guardrails_text=pb.guard_raw.decode("utf-8"), checks=pb.checks,
            authority=self.k.manifest["authority"]["accepted"], diff=diff, diffstat=diffstat,
            check_results=[{"id": e["id"], "check_id": e["check"]["check_id"], "result": e["result"],
                            "exit_code": e["check"]["exit_code"], "log": (e.get("evidence") or [{}])[0].get("path")}
                           for e in on_snapshot if e["kind"] == "check_result"],
            implementation_summary=summary,
            open_findings=[f for f in unit.get("findings", []) if f["status"] == "open"],
            failure_evidence=failure,
            card=(card or {}).get("content"),
            history=history, codebase_map=map_lines, scope_added=SC.pack_entries(self.k.aew_root, unit),
            scope_lines_changed=lines_changed,
            recovery=inv.get("recovery"),
            **{k: v for k, v in self._m2_pack_extras(state, inv, unit).items() if k in {"hierarchy", "inherited",
                                                                                        "inputs"}},
        )
        sources = [
            *self._base_sources(pb, role, unit, "current_ticket"),
            {"name": "snapshot", "path": None, "sha256": None, "base": base, "tree": fp},
            *[{"name": f"evidence:{e['id']}", "path": e["_path"], "sha256": e["_sha256"]} for e in on_snapshot],
            *self._history_sources(history),
            *([dict(map_source)] if map_source is not None else []),
            *SC.pack_sources(unit),  # register E126: each correction the pack lists
            *self._recovery_sources(inv.get("recovery")),
        ]
        return inputs, sources

    def _m2_pack_inputs(self, state: dict[str, Any], inv_id: str, *,
                        fresh_map: bool = False, lead: dict[str, Any] | None = None
                        ) -> tuple[ctxmod.PackInputs, list[dict[str, Any]]]:
        """Packs for read-only invocations: executors of non-mutating Tickets, reviewers/verifiers of their
        records, and parent (Story/Epic) acceptance reviewers/verifiers."""
        inv = state["invocations"][inv_id]
        role, wid = inv["role"], inv["work_unit"]
        unit = state["work"][wid]
        pb = self._pack_base(inv, unit)
        card, record, plan = pb.card, pb.record, pb.plan
        extras = self._m2_pack_extras(state, inv, unit)
        history = self._history_refs(state, inv)
        role_def = roles.archetype(role)
        map_source, map_lines = self._map_slice(inv, role_def, (inv.get("observation") or {}).get("commit"),
                                                record.meta, fresh_map, lead)
        inputs = ctxmod.PackInputs(
            invocation_id=inv_id, role=role, role_def=role_def, work_id=wid, title=unit["title"],
            scope=inv.get("scope"), specialty=inv.get("specialty"), workspace=inv["workspace"],
            snapshot=inv["snapshot"], record_meta=record.meta, record_body=record.body, plan=plan,
            plan_text=pb.plan_text, guardrails_text=pb.guard_raw.decode("utf-8"), checks=pb.checks,
            authority=self.k.manifest["authority"]["accepted"],
            open_findings=[f for f in unit.get("findings", []) if f["status"] == "open"],
            card=(card or {}).get("content"), history=history,
            codebase_map=map_lines, recovery=inv.get("recovery"), **extras)
        sources = [
            *self._base_sources(pb, role, unit, "current_work"),
            {"name": "observation", "path": None, "sha256": None,
             "commit": (inv.get("observation") or {}).get("commit"),
             "tree": inv["snapshot"]["relevant_inputs_fingerprint"]},
            *[{"name": f"ancestor:{a['id']}", "path": state["work"][a["id"]]["record"],
               "sha256": state["work"][a["id"]]["record_sha256"]} for a in extras["hierarchy"]],
            *[{"name": f"input:{i['id']}", "path": None, "sha256": i["sha256"], "freshness": i["freshness"]}
              for i in extras["inputs"]],
            *([{"name": f"subject:{inv['subject']['id']}", "path": None, "sha256": inv["subject"]["sha256"]}]
              if inv.get("subject") else []),
            *[{"name": f"child:{c['id']}", "path": c.get("completion_record"), "sha256": c.get("completion_sha256")}
              for c in extras.get("children", [])],
            *self._history_sources(history),
            *([dict(map_source)] if map_source is not None else []),
            *self._recovery_sources(inv.get("recovery")),
        ]
        return inputs, sources

    def pack_rel(self, inv_id: str) -> str:
        return f"local/packs/{inv_id}/pack.md"

    def build_pack(self, ctx: TxnContext, inv_id: str) -> None:
        inv = ctx.state["invocations"][inv_id]
        inv["evidence_seq_cutoff"] = E.next_seq(self.k.aew_root, inv["work_unit"]) - 1
        refs = (ctx.state["work"].get(inv["work_unit"]) or {}).get("history_refs")
        if refs:  # pinned per invocation: a later load changes later packs only, and a regenerated pack matches
            inv["history_refs"] = [dict(r) for r in refs]
        # Pinned once, as the map is: a second build in the dispatching transaction, and every regenerated pack, reads
        # the observation the first build made, so the pack never differs because the workspace moved (register F36).
        if "recovery" not in inv and (recovery := self.recovery(ctx.state, inv_id)) is not None:
            inv["recovery"] = recovery
        # only a Lead's transaction refreshes the map: a custodian's dispatch, or anything a run starts, uses it as is
        lead = ctx.actor if (ctx.actor or {}).get("kind") == "lead" else None
        inputs, sources = self._pack_inputs(ctx.state, inv_id, fresh_map=True, lead=lead)
        text = ctxmod.render(inputs)
        rel = self.pack_rel(inv_id)
        atomic_write(self.k.aew_root / rel, text)  # rebuildable local data, not control state
        inv["pack"] = {"path": rel, "sha256": sha256_text(text), "sources": sources}

    def _rendered(self, inv_id: str) -> tuple[str, dict[str, Any]]:
        """An invocation's pack text, rendered from durable state, and the invocation."""
        state = self.k.store.current()
        if inv_id not in state["invocations"]:  # a completed invocation of archived work: its pack, regenerated (R7)
            state = self.archive.rehydrate_invocation(state, inv_id) or state
        inv = state["invocations"].get(inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        inputs, _ = self.pack_inputs(state, inv_id)
        return ctxmod.render(inputs), inv

    def context_pack(self, inv_id: str) -> dict[str, Any]:
        """Regenerate an invocation's pack from durable state (e.g. after local/ was deleted). A writer's operation: its
        purpose is a write under ``.aew/local``, which a non-writer never makes (``context show`` renders in memory
        there; review of #231, m7)."""
        process_kind.require_writer("context pack", writes="the invocation's pack under .aew/local/packs")
        text, inv = self._rendered(inv_id)
        rel = self.pack_rel(inv_id)
        atomic_write(self.k.aew_root / rel, text)
        recorded = (inv.get("pack") or {}).get("sha256")
        return {"ok": True, "invocation": inv_id, "path": str(self.k.aew_root / rel), "sha256": sha256_text(text),
                "matches_recorded": recorded == sha256_text(text)}

    def context_show(self, inv_id: str) -> str:
        """The pack's text. A missing pack is regenerated, and kept, by a store writer; a non-writer (a worker's
        sandbox, where `.aew/local` is a read-only mask) renders it without writing (STG-05 CB-09, CBF-1)."""
        path = self.k.aew_root / self.pack_rel(inv_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        if process_kind.kind() == process_kind.NON_WRITER:
            return self._rendered(inv_id)[0]
        self.context_pack(inv_id)
        return path.read_text(encoding="utf-8")
