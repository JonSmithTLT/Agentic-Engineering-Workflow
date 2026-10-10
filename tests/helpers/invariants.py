"""Cross-operation control-state invariants (review 2026-09-26, "expand adversarial sequences").

A test oracle, not engine code: it reads the durable, human-readable control
state the same way an operator or another tool would, and checks properties
that must hold after *any* sequence of operations — the compositions the
independent review found unguarded.

ADR-0011 (control state v2): finished work is archived. The oracle learns the cold side additively
(invariant 8): it rebuilds the full state from the hot state and every archived bundle (moves applied), runs
every rule on that, exactly as before archival, and adds the rules archival itself must keep (19-23). It may
read the whole history; the engine's commit-time checks may not (invariant 13).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import yaml
from store_model import segment_violations  # a sibling helper: rule 27 over sealed segments

from aew.engine import hierarchy as H
from aew.engine import outbox
from aew.engine import ticket_fields as TF
from aew.engine.archive_ops import add_leaf, child_leaf
from aew.engine.store import deserialize_control
from aew.history.store import History
from aew.knowledge import evidence as E
from aew.util import load_yaml, parse_frontmatter, sha256_file


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def load_control(root: Path) -> dict[str, Any]:
    path = root / ".aew/state/control.yaml"
    return deserialize_control(path.read_bytes(), source=str(path))


def with_cold(root: Path, hot: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The full state: hot units, invocations and credentials plus every archived one, with each archived unit's
    later moves applied; and the problems found reading the history (rule 19)."""
    if hot.get("schema") != "aew/control/v2":
        return hot, []
    problems: list[str] = []
    root_ = hot["cold"]["root"]
    history = History(root / ".aew")
    report = history.verify(root_)
    if not report.ok:
        return hot, [f"history does not verify: {report.problems[:3]}"]
    work, invocations, tokens = {}, {}, {}
    moves: dict[str, str | None] = {}
    for entry in history.walk(root_):
        if entry["kind"] == "unit":
            doc = load_yaml((root / ".aew" / entry["path"]).read_text(encoding="utf-8"))
            work[entry["id"]] = dict(doc["unit"])
            invocations.update(doc.get("invocations", {}))
            tokens.update(doc.get("tokens", {}))
        elif entry["kind"] == "annotation" and entry.get("rel") == "moved_to":
            moves[entry["subject"]] = (entry.get("links", {}).get("moved_to") or [None])[0]
    for wid, parent in moves.items():
        work[wid]["parent"] = parent
    both = sorted(set(work) & set(hot["work"]))
    if both:
        problems.append(f"units both hot and archived: {both}")
    full = dict(hot, work={**work, **hot["work"]}, invocations={**invocations, **hot["invocations"]},
                tokens={**tokens, **hot["tokens"]})
    full["_archived"] = sorted(work)
    return full, problems


def cold_violations(root: Path, hot: dict[str, Any], full: dict[str, Any]) -> list[str]:
    """19-23: what archival must keep (ADR-0011; implementation plan R3-R5)."""
    if hot.get("schema") != "aew/control/v2":
        return []
    problems: list[str] = []
    archived = set(full["_archived"])
    work = full["work"]
    # 20. Only finished work is archived; a hot unit never has an archived ancestor.
    for wid in sorted(archived):
        if work[wid]["state"] not in {"DONE", "CANCELLED"}:
            problems.append(f"{wid} is archived but {work[wid]['state']}")
    for wid, u in sorted(hot["work"].items()):
        anc = u.get("parent")
        while anc:
            if anc in archived:
                problems.append(f"hot {wid} has the archived ancestor {anc}")
            anc = work.get(anc, {}).get("parent")
    # 21. Each hot parent's summary is the recount of its archived children and of the archived Tickets below it.
    for wid, u in sorted(hot["work"].items()):
        if u["kind"] == "ticket":
            continue
        kids = [c for c in archived if work[c].get("parent") == wid]
        below = [d for d in H.descendants(full, wid) if d in archived and work[d]["kind"] == "ticket"]
        acc = "0" * 64
        for c in kids:
            acc = add_leaf(acc, child_leaf(c, work[c]["state"], work[c].get("completion_sha256")))
        expected = {"done": sum(work[c]["state"] == "DONE" for c in kids),
                    "cancelled": sum(work[c]["state"] == "CANCELLED" for c in kids),
                    "done_tickets_subtree": sum(work[d]["state"] == "DONE" for d in below),
                    "cancelled_tickets_subtree": sum(work[d]["state"] == "CANCELLED" for d in below), "acc": acc}
        if H.archived_summary(u) != expected:
            problems.append(f"{wid}'s archived summary {H.archived_summary(u)} is not the recount {expected}")
        # 22. Derivation from hot state and summaries equals derivation from the full state (R3).
        flat = dict(full, schema="aew/control/v1",
                    work={k: {kk: vv for kk, vv in x.items() if kk != "archived_children"} for k, x in work.items()})
        if H.derive_parent(hot, wid) != H.derive_parent(flat, wid):
            problems.append(f"{wid}: derived from hot state {H.derive_parent(hot, wid)}, from the full state "
                            f"{H.derive_parent(flat, wid)}")
        # 23. The integration frontier covers every archived integrated Ticket below it (R5).
        frontier = u.get("integration_frontier") or {}
        for d in below:
            commit = (work[d].get("integration") or {}).get("commit")
            if work[d].get("mutating") and work[d]["state"] == "DONE" and commit and not any(
                    m == commit or _git("merge-base", "--is-ancestor", commit, m, cwd=root).returncode == 0
                    for m in frontier):
                problems.append(f"{wid}'s integration frontier does not cover {d}'s {commit[:12]}")
    # 23b. Every hot edge to an archived unit has its facts kept, matching the archive (R4).
    refs = hot.get("archived_refs") or {}
    for wid, u in sorted(hot["work"].items()):
        for e in u.get("depends_on", []):
            if e["id"] in hot["work"]:
                continue
            ref = refs.get(e["id"])
            if ref is None or e["id"] not in archived or ref["state"] != work[e["id"]]["state"]:
                problems.append(f"{wid}'s edge to archived {e['id']} has no matching archived_refs entry ({ref})")
    return problems


def control_violations(root: Path) -> list[str]:
    root = Path(root)
    hot = load_control(root)
    state, cold_problems = with_cold(root, hot)
    manifest = yaml.safe_load((root / ".aew/project.yaml").read_text(encoding="utf-8"))
    ref = f"refs/heads/{manifest['repository']['authoritative_branch']}"
    tokens = state["tokens"]
    problems: list[str] = []
    evidence: dict[str, dict[str, dict[str, Any]]] = {}

    # 1. Live mutating workspaces never share a path. The policy cap (`mutating_concurrency`) is an admission rule,
    #    enforced by the `cap.mutating` dispatch guard, not an invariant of the state: lowering the cap never makes
    #    work already admitted illegal; it drains, and nothing new is admitted until occupancy is below the new cap
    #    (operator, 2026-10-04). The admission side is tested in test_workspaces.py.
    live = sorted(wid for wid, u in state["work"].items()
                  if u["kind"] == "ticket" and u.get("mutating")
                  and (u.get("workspace") or {}).get("status") == "active")
    paths = [state["work"][w]["workspace"]["path"] for w in live]
    if len(set(paths)) != len(paths):
        problems.append(f"live mutating workspaces share a path: {sorted(paths)}")

    # 2. Every active invocation is bound to its Ticket's *current* live workspace, with a live credential;
    #    every inactive invocation's credential is revoked.
    for inv_id, inv in sorted(state["invocations"].items()):
        tok = tokens.get(inv.get("token_id") or "", {})
        if inv["status"] != "active":
            if tok and not tok.get("revoked_at"):
                problems.append(f"{inv_id} is {inv['status']} but its credential is not revoked")
            continue
        if inv.get("kind") == "integration_attempt":
            continue  # an engine custody invocation: no credential, no workspace (rules 34-39)
        if tok.get("revoked_at"):
            problems.append(f"{inv_id} is active but its credential is revoked")
        unit = state["work"].get(inv["work_unit"]) or {}
        if unit.get("state") in {"DONE", "CANCELLED"}:
            problems.append(f"{inv_id} is active on terminal {inv['work_unit']}")
            continue
        if inv.get("scope") in {"observation", "parent"}:
            continue  # bound to their own read-only observation (rules 9 and 12)
        if inv.get("scope") == "integration":
            integ = unit.get("integration") or {}
            if integ.get("workspace") != inv.get("workspace"):
                problems.append(f"{inv_id} (integration) is not bound to the current integration candidate")
        else:
            ws = unit.get("workspace") or {}
            if ws.get("status") != "active" or ws.get("path") != inv.get("workspace"):
                problems.append(f"{inv_id} is bound to {inv.get('workspace')}, which is not "
                                f"{inv['work_unit']}'s live workspace ({ws.get('id')}, {ws.get('status')})")

    for wid, u in sorted(state["work"].items()):
        if u["kind"] != "ticket":
            continue
        # 3. DONE mutating work: the integrated commit is in the authoritative lineage and is the
        #    output that was gated at COMMIT_READY.
        if u["state"] == "DONE" and u.get("mutating"):
            integ = u.get("integration") or {}
            commit = integ.get("commit")
            if not commit or _git("merge-base", "--is-ancestor", commit, ref, cwd=root).returncode != 0:
                problems.append(f"{wid} is DONE but {commit} is not in {ref}")
            gated = (u.get("commit_ready_snapshot") or {}).get("relevant_inputs_fingerprint")
            binding = integ.get("binding") or {}
            if binding and binding.get("gated_fingerprint") != gated:
                problems.append(f"{wid} integrated a candidate bound to {binding.get('gated_fingerprint')}, "
                                f"not the COMMIT_READY snapshot {gated}")
            rec = root / ".aew" / (u.get("completion_record") or "missing")
            if rec.exists():
                meta, _ = parse_frontmatter(rec.read_text(encoding="utf-8"))
                if meta.get("gated_snapshot") != gated:
                    problems.append(f"{wid} completion record gated_snapshot differs from COMMIT_READY snapshot")
            else:
                problems.append(f"{wid} is DONE without a completion record")
            # 3b. ...and it was validated by a report produced FOR this candidate, under its plan
            #     (re-review R1: identical content from another attempt/plan is not evidence for it).
            post = integ.get("post_integration_evidence")
            if post:
                ev = evidence.setdefault(wid, _evidence(root, wid)).get(post)
                inv = state["invocations"].get((ev or {}).get("producer", {}).get("invocation") or "", {})
                if ev is None or inv.get("workspace") != integ.get("workspace") \
                        or inv.get("integration_attempt") != integ.get("attempt"):
                    problems.append(f"{wid} integrated with {post}, which was not produced for candidate "
                                    f"attempt {integ.get('attempt')}")
                elif binding and ev.get("plan_revision") != binding.get("plan"):
                    problems.append(f"{wid} integrated with {post}, produced under plan {ev.get('plan_revision')}")
        # 4. VERIFICATION_FAILED is left only by a Lead classification (or cancellation).
        exits = [h for h in u.get("history", []) if h.get("from") == "VERIFICATION_FAILED"
                 and h.get("to") not in {"CANCELLED", "VERIFICATION_FAILED"}]
        if len(exits) > len(u.get("classifications", [])):
            problems.append(f"{wid} left VERIFICATION_FAILED {len(exits)}x with "
                            f"{len(u.get('classifications', []))} classification(s)")
        if u["state"] == "INTERRUPTED" and u.get("interrupted_from") == "VERIFICATION_FAILED":
            problems.append(f"{wid} was interrupted out of VERIFICATION_FAILED (classification pending)")
        # 5. No evidence is produced after its invocation's credential was revoked (re-review M2):
        #    retiring an assignment ends its write authority; its earlier reports stay as history.
        for ev in evidence.setdefault(wid, _evidence(root, wid)).values():
            inv = state["invocations"].get(ev["producer"]["invocation"], {})
            revoked = tokens.get(inv.get("token_id") or "", {}).get("revoked_at")
            if revoked and ev["created_at"] > revoked:
                problems.append(f"{ev['id']} was written at {ev['created_at']}, after its credential was revoked "
                                f"at {revoked}")
    # 6-14. M2 hierarchy and non-mutating invariants (ADR-0007/0008).
    problems += m2_violations(root, state)
    # 17-18. M3 harness runs and credential rotation (ADR-0009).
    problems += m3_violations(root, state, evidence)
    # 19-23. ADR-0011 archival.
    problems += cold_problems + cold_violations(root, hot, state)
    # 24 and 26. ADR-0012: the transition log (rule 25, event fidelity, needs the earlier states: store_model.py).
    problems += outbox_violations(root, hot)
    # 27. ADR-0012: sealed segments (rule 28, reader race safety, is modelled over interleavings: store_model.py).
    problems += segment_violations(Path(root) / ".aew", hot) if hot.get("outbox") else []
    # 34-39. M4-D: the integration queue and its lease (29-33 are ADR-0013's).
    problems += queue_violations(root, hot)
    # 40-42. M4-D5: checks-mode validation runs and engine-produced evidence.
    problems += validation_violations(root, state, evidence)
    # 43-45. M4-E E2: steering.
    problems += steering_violations(root, hot)
    # 46. Run usage (F25 R1, R5), over the hot state and every rehydrated bundle.
    problems += usage_violations(state)
    # 47-49 and 51. M4-E E3: the StageIntent journal, hot and cold, and its resolutions (E3c; 50 is F4 S1's, below).
    problems += stage_intent_violations(root, hot, state)
    # 50. F4 S1: every unit key and record field is classified by the Ticket field registry.
    problems += ticket_field_violations(root, state)
    # 52-58. F9-A: coordination threads, their seals and the coordination keys (plan v4 §7, C1 to C7).
    problems += coordination_violations(root, hot, state)
    return problems


def ticket_field_violations(root: Path, state: dict[str, Any]) -> list[str]:
    """50. Every control-state key of every unit, hot or archived, and every frontmatter field of every hot unit's
    record is classified by the Ticket field registry (F4 plan §3.3 and §9.2, the S1 meta-test over the walks).

    An unclassified input still fails closed into the acceptance group at run time; this rule makes the slice that
    adds a key classify it (one line in ``src/aew/schemas/ticket-field-registry.v1.json``)."""
    problems: list[str] = []
    archived = set(state.get("_archived") or [])
    for wid, unit in sorted(state["work"].items()):
        keys = TF.unclassified_control_keys(unit)
        if keys:
            problems.append(f"{wid}: unit keys the Ticket field registry does not classify: {keys}")
        rec = Path(root) / ".aew" / str(unit.get("record") or "missing")
        if wid not in archived and rec.is_file():
            meta, _ = parse_frontmatter(rec.read_text(encoding="utf-8"), source=str(rec))
            paths = TF.unclassified_record_paths(meta)
            if paths:
                problems.append(f"{wid}: record fields the Ticket field registry does not classify: {paths}")
    return problems


def stage_intent_violations(root: Path, hot: dict[str, Any], full: dict[str, Any]) -> list[str]:
    """M4-E E3 (plan v3 E3, §2.7; typed surface §3.4).

    47: every hot intent is ACTIVE and schema-valid, owned by a generation that has existed, and its steps are a
        prefix of its plan under the keys ``<SI>:<n>``, at strictly increasing revisions after it opened and none past
        the current revision; a unit has at most one, and so does the project (a stage with no unit).
    48: every step carries the legality digest the intent bound (nothing commits under drift); a step is retried after
        a stale revision only when it and the stage are non-judgment, and the intent says so iff some step was; a stop
        names the next step, or the last when every step committed (rule 7).
    49: every intent ever opened (``counters.stage_intent``) lives in exactly one place: hot, or one immutable cold
        record that is terminal, valid and its own id, at the path its subject gives it. A unit's record is pinned by
        the unit's pointer (hot or in its bundle) or, when the unit was archived first, by a history annotation whose
        note carries the record's hash; a record with no unit (``records/``) is pinned by no hash.
    51: its resolutions (E3c), hot and cold: see ``resolutions`` below."""
    from aew.engine import stage_intents as S
    from aew.schemas import validate

    problems: list[str] = []
    aew = Path(root) / ".aew"
    intents = hot.get("stage_intents") or {}
    subjects: dict[str, str] = {}

    def journal(si: dict[str, Any], where: str) -> None:
        for n, (planned, done) in enumerate(zip(si["plan"], si["steps"], strict=False), start=1):
            if done["n"] != n or done["key"] != f"{si['id']}:{n}" or done["primitive"] != planned["primitive"]:
                problems.append(f"{where}: step {n} is not its plan's step {n}")
            if done["legality_digest"] != si["binding"]["legality_digest"]:
                problems.append(f"{where}: step {n} committed under another legality digest")
            if done.get("retried_after_stale_revision") and (
                    "JUDGMENT_BEARING" in (done["operation_class"], si["effective_class"])):
                problems.append(f"{where}: judgment-bearing step {n} was retried")
        if len(si["steps"]) > len(si["plan"]):
            problems.append(f"{where}: more steps than planned")
        revs = [si["opened"]["rev"], *(s["revision"] for s in si["steps"])]
        if revs != sorted(set(revs)):
            problems.append(f"{where}: step revisions do not increase from its opening: {revs}")
        if si["retried_after_stale_revision"] != any(s.get("retried_after_stale_revision") for s in si["steps"]):
            problems.append(f"{where}: the intent's retry flag disagrees with its steps")
        stop, done = si.get("stopped"), len(si["steps"])
        if stop and stop["n"] != done + 1 and not stop["n"] == done == len(si["plan"]):
            problems.append(f"{where}: stopped at step {stop['n']} after {done} committed")
        resolutions(si, where)

    def resolutions(si: dict[str, Any], where: str) -> None:
        """51 (E3c): every continue is an explicit rebind, chained generation to generation, each to one that held
        the seat; the owner is the last one rebound to; the latest resolution is the last continue, or the abandon
        that ended the intent; and nothing is resolved before it opened or after it closed."""
        rebound, resolution = si["rebound"], si["resolution"]
        owner = rebound[0]["from_generation"] if rebound else si["generation"]
        for r in rebound:
            if r["from_generation"] != owner or not owner <= r["to_generation"] <= hot["lead"]["generation"]:
                problems.append(f"{where}: a continue rebinds generation {r['from_generation']} to "
                                f"{r['to_generation']}, but generation {owner} owned it")
            owner = r["to_generation"]
        if owner != si["generation"]:
            problems.append(f"{where}: owned by generation {si['generation']}, last rebound to {owner}")
        revs = [si["opened"]["rev"], *(r["rev"] for r in rebound)]
        if revs != sorted(set(revs)) or (si["closed"] and revs[-1] > si["closed"]["rev"]):
            problems.append(f"{where}: its continues are not ordered between its opening and its end: {revs}")
        if (si["status"] == S.ABANDONED) != bool(resolution and resolution["choice"] == "abandon"):
            problems.append(f"{where}: {si['status']} with resolution {resolution and resolution['choice']}")
        if resolution and resolution["choice"] == "continue" and not (
                rebound and (resolution["rev"], resolution["generation"]) == (rebound[-1]["rev"], owner)):
            problems.append(f"{where}: its latest continue is not its last rebind")
        if resolution is None and rebound:
            problems.append(f"{where}: continued with no resolution recorded")

    for sid, si in sorted(intents.items()):
        where = f"stage intent {sid}"
        try:
            validate("stage-intent", si, source=where)
        except Exception as exc:
            problems.append(f"{where} is not a stage-intent record: {exc}")
            continue
        if si["id"] != sid or si["status"] != S.ACTIVE:
            problems.append(f"{where}: hot but {si['status']} (or filed under another id)")
        if not 1 <= si["generation"] <= hot["lead"]["generation"]:
            problems.append(f"{where}: owned by generation {si['generation']}, which never held the seat")
        if si["steps"] and si["steps"][-1]["revision"] > hot["revision"]:
            problems.append(f"{where}: a step past the current revision")
        key = si["subject"]["id"] or "the project"  # one per unit, and one with no unit
        if key in subjects:
            problems.append(f"{key} has two unfinished stages: {subjects[key]} and {sid}")
        subjects[key] = sid
        journal(si, where)

    pointers = {p["id"]: (wid, p) for wid, u in full["work"].items() for p in u.get("stage_intents") or []}
    for n in range(1, (hot["counters"].get("stage_intent") or 0) + 1):
        sid = f"SI-{n:04d}"
        homes = sorted(p.relative_to(aew).as_posix() for p in [*aew.glob(f"work/*/stage-intents/{sid}.yaml"),
                                                                *aew.glob(f"{S.RECORDS_DIR}/{sid}.yaml")])
        if sid in intents:
            if homes:
                problems.append(f"{sid} is both hot and cold: {homes}")
            continue
        if len(homes) != 1:
            problems.append(f"{sid} was opened and lives in {len(homes)} cold places, not one: {homes}")
            continue
        raw = (aew / homes[0]).read_bytes()
        doc = yaml.safe_load(raw)
        try:
            validate("stage-intent", doc, source=homes[0])
        except Exception as exc:
            problems.append(f"{homes[0]} is not a stage-intent record: {exc}")
            continue
        if doc["id"] != sid or doc["status"] not in S.TERMINAL or doc["closed"]["status"] != doc["status"]:
            problems.append(f"{homes[0]}: a cold intent must be its own id and terminal")
        if homes[0] != S.cold_rel(sid, doc["subject"]["id"]) and homes[0] != S.cold_rel(sid, None):
            problems.append(f"{homes[0]}: not where its subject {doc['subject']['id']} puts it")
        journal(doc, homes[0])
        sha = hashlib.sha256(raw).hexdigest()
        if sid in pointers:
            wid, pointer = pointers[sid]
            if pointer["path"] != homes[0] or pointer["sha256"] != sha:
                problems.append(f"{wid}'s pointer to {sid} does not name its record and hash")
        elif homes[0].startswith("work/"):
            # A unit's record is pinned by the unit's pointer, or by an annotation on a unit archived first.
            wid = homes[0].split("/")[1]
            notes = [yaml.safe_load(a.read_bytes()) for a in (aew / "work" / wid / "annotations").glob("*.yaml")]
            if not any(n.get("rel") == "stage_intent" and n.get("object") == sid
                       and n.get("note") == f"{homes[0]} sha256:{sha}" for n in notes):
                problems.append(f"{homes[0]} is pinned by no pointer or annotation on {wid}")
    return problems


def steering_violations(root: Path, state: dict[str, Any]) -> list[str]:
    """M4-E E2 (plan v3 §2.1, §2.7). 43: an override belongs to a Lead generation that has existed, and every mode
    and request names a record that exists in records/steering/. 44: only the operator's records raise, and each says
    `guarantee: dev`. 45: requests are bounded and each is a raise to walk or run, or a confirmation of an action."""
    steering = state.get("steering")
    if steering is None:
        return []
    problems: list[str] = []
    records: dict[str, dict[str, Any]] = {}
    for f in sorted((Path(root) / ".aew" / "records" / "steering").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            if entry.get("id"):
                records[entry["id"]] = entry
    override, standing = steering.get("override"), steering["standing"]
    if override and override["generation"] > state["lead"]["generation"]:
        problems.append(f"steering override for generation {override['generation']} is ahead of the Lead")
    for which, held in (("standing", standing), ("override", override)):
        if held and held.get("record") and held["record"] not in records:
            problems.append(f"steering {which} names record {held['record']}, which is not in records/steering/")
        elif held and held.get("record") and records[held["record"]]["new"] != held["mode"]:
            problems.append(f"steering {which} mode {held['mode']} disagrees with its record {held['record']}")
    for rid, record in records.items():
        if record.get("kind") != "mode_change":
            continue
        rank = {None: 0, "crawl": 0, "walk": 1, "run": 2}
        if rank[record["new"]] > rank[record["previous"]] and record["source"] not in ("raise", "default"):
            problems.append(f"{rid} raised the mode by {record['source']}: only the operator raises")
        by = record["by"]
        guarantee = by.get("guarantee", (by.get("principal") or {}).get("guarantee"))
        if by["kind"] == "operator" and guarantee != "dev":
            problems.append(f"{rid} is labelled guarantee {guarantee!r}; nothing before F18.6 is other than dev")
    requests = steering["requests"]
    if len(requests) > 8 or any((r["kind"] == "raise") != bool(r.get("mode")) for r in requests):
        problems.append(f"steering requests are unbounded or malformed: {requests}")
    return problems


def usage_violations(state: dict[str, Any]) -> list[str]:
    """F25 (the cost and usage ledger design v0.2 R1, R5). 46: every ``inv.runs[].usage``, when present, is a
    well-formed ``aew/run-usage/v1`` whose ``run`` names its own entry, at most 2 KiB serialized, with at most 8
    distinct effective entries; a run is copied once, so a usage never names another run."""
    from aew.harness import usage as U
    from aew.schemas import validate

    problems: list[str] = []
    for inv_id, inv in sorted(state["invocations"].items()):
        for entry in inv.get("runs") or []:
            usage = entry.get("usage")
            if usage is None:
                continue
            try:
                validate("run-usage", usage, source=f"{inv_id} {entry.get('run')}")
            except Exception as exc:  # the invariant reports; it never stops at the first bad record
                problems.append(f"{inv_id} run {entry.get('run')}: usage is not a run-usage record: {exc}")
                continue
            if usage["run"] != entry["run"]:
                problems.append(f"{inv_id} run {entry['run']} holds the usage of {usage['run']}")
            if U.serialized_size(usage) > U.MAX_BYTES:
                problems.append(f"{inv_id} run {entry['run']}: usage is {U.serialized_size(usage)} bytes, over 2 KiB")
            distinct = {(e.get("provider"), e.get("model"), e.get("effort")) for e in usage.get("effective") or []}
            if len(distinct) > U.MAX_EFFECTIVE:
                problems.append(f"{inv_id} run {entry['run']}: {len(distinct)} distinct effective entries, over 8")
    return problems


def validation_violations(root: Path, state: dict[str, Any],
                          evidence: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    """M4-D5 (the M4-D5 plan rev 3): validation runs are durable and exact, and engine evidence stays in its lane."""
    problems: list[str] = []
    lease = (state.get("queue") or {}).get("lease")
    entries = (state.get("queue") or {}).get("entries") or {}
    gates = yaml.safe_load((root / ".aew/policy/gates.yaml").read_text(encoding="utf-8")) or {}
    post = gates.get("post_integration") or {}
    for wid, u in sorted(state["work"].items()):
        integ = u.get("integration") or {}
        run = integ.get("current_validation_run")
        # 40. At most one running run per candidate (authoritative or diagnostic), and only under its entry's lease;
        #     every terminal run, on the open candidate or a retired one, is kept as an immutable record whose bytes
        #     match what the state says; run ids are never reused.
        ids = (integ.get("validation_runs") or {}).get("ids") or []
        if len(set(ids)) != len(ids):
            problems.append(f"{wid} reuses validation run ids {ids}")
        slots = ("current_validation_run", "diagnostic_run")
        live = [r for r in (integ.get(s) for s in slots) if r and r["state"] == "running"]
        if len(live) > 1:
            problems.append(f"{wid} has {len(live)} validation runs running at once")
        for r in live:
            holder = (entries.get((lease or {}).get("entry") or "") or {}).get("work")
            if holder != wid or (lease or {}).get("custodian") != r["custodian"]:
                problems.append(f"{wid}'s validation run {r['id']} is running without its entry's lease")
        for holder_record in [integ, *(u.get("integration_history") or [])]:
            for s in slots:
                r = holder_record.get(s)
                if not r or r["state"] == "running":
                    continue
                rec = root / ".aew" / ((r.get("record") or {}).get("path") or "missing")
                if not r.get("record") or not rec.exists() or sha256_file(rec) != r["record"]["sha256"]:
                    problems.append(f"{wid}'s terminal validation run {r['id']} has no intact record")
        # 41. Engine evidence (producer.kind engine) is only a check_result, names its validation run, and was produced
        #     under one of the Ticket's custody invocations.
        for ev in evidence.setdefault(wid, _evidence(root, wid)).values():
            prod = ev["producer"]
            if prod.get("kind") != "engine":
                continue
            inv = state["invocations"].get(prod["invocation"]) or {}
            if ev["kind"] != "check_result" or not prod.get("validation_run") or "role" in prod \
                    or inv.get("kind") != "integration_attempt" or inv.get("work_unit") != wid:
                problems.append(f"{ev['id']} is engine evidence outside its lane (kind {ev['kind']}, "
                                f"producer {prod})")
        # 42. A checks-mode `validated` candidate has a passing engine result of its committed run, for every policy
        #     check, on its snapshot, each produced under immutable-source containment (os_readonly_roots): a result
        #     from a weaker sandbox never counts (the plan rev 3, correction 3; PR #91 re-review, finding 5).
        validation = integ.get("validation") or {}
        if integ.get("status") == "validated" and validation.get("mode") == "checks":
            fp = integ["candidate_snapshot"]["relevant_inputs_fingerprint"]
            ev_all = evidence.setdefault(wid, _evidence(root, wid))
            passed = {ev_all[e]["check"]["check_id"] for e in validation.get("evidence") or [] if e in ev_all
                      and ev_all[e]["result"] == "pass"
                      and ev_all[e]["producer"].get("validation_run") == validation["run"]
                      and ev_all[e]["evaluated_snapshot"]["relevant_inputs_fingerprint"] == fp
                      and ev_all[e]["method"].get("containment") == "os_readonly_roots"}
            missing = [c for c in post.get("checks") or [] if c not in passed]
            if missing or (run or {}).get("id") != validation["run"] or (run or {}).get("state") != "committed":
                problems.append(f"{wid} is validated in checks mode without a committed, contained pass "
                                f"for {missing or 'its run'}")
        # 43. A run that passed its deadline never releases the lease by itself: while the candidate it validated is
        #     still open, its entry is still LEASED (a further attempt within the bound) or went the disposition
        #     way (AWAITING_DISPOSITION, or DEFERRED by the Lead). QUEUED only after that disposition: the release
        #     alone marks the candidate `validation_unavailable`, and the Lead may then requeue it (re-review R2).
        if run and run.get("reason") == "VALIDATION_DEADLINE_EXPIRED" and integ.get("workspace"):
            mine = [e for e in entries.values() if e.get("work") == wid]
            state_now = mine[0]["state"] if mine else None
            disposed = state_now == "QUEUED" and integ.get("status") == "validation_unavailable"
            if mine and state_now not in ("LEASED", "AWAITING_DISPOSITION", "DEFERRED") and not disposed:
                problems.append(f"{wid}'s validation run {run['id']} passed its deadline and its entry is "
                                f"{state_now}: the lease left other than through AWAITING_DISPOSITION")
        # 44. A run is running only on an open candidate: a published or retired one never keeps a running run
        #     (it would never be recorded, and the archive would hold it running forever; re-review R1).
        open_candidate = u["state"] == "COMMIT_READY" and integ.get("status") in ("prepared", "validated")
        for holder_record in [integ, *(u.get("integration_history") or [])]:
            for s in slots:
                r = holder_record.get(s)
                if r and r["state"] == "running" and (holder_record is not integ or not open_candidate):
                    problems.append(f"{wid}'s validation run {r['id']} is running on a candidate that is not open")
    return problems


def queue_violations(root: Path, state: dict[str, Any]) -> list[str]:
    """M4-D (the M4 report §2.6 and §6; the M4-D plan §1.2). A project whose control state has no ``queue`` yet has
    never queued anything since the queue existed; its first Lead transaction creates it."""
    problems: list[str] = []
    queue = state.get("queue")
    work, invocations = state["work"], state["invocations"]
    custodians = {i: inv for i, inv in invocations.items() if inv.get("kind") == "integration_attempt"}
    if queue is None:
        if custodians:
            problems.append(f"custody invocations {sorted(custodians)} exist without an integration queue")
        return problems
    entries, lease = queue["entries"], queue["lease"]
    # 34. One live entry per COMMIT_READY mutating Ticket, and only for one; FIFO positions are unique and issued.
    queued = sorted(w for w, u in work.items()
                    if u["kind"] == "ticket" and u.get("mutating") and u["state"] == "COMMIT_READY")
    by_work: dict[str, list[str]] = {}
    for qid, e in entries.items():
        by_work.setdefault(e["work"], []).append(qid)
    for wid in queued:
        if len(by_work.get(wid, [])) != 1:
            problems.append(f"{wid} is COMMIT_READY with queue entries {by_work.get(wid, [])}, not exactly one")
    for wid, qids in sorted(by_work.items()):
        if wid not in queued:
            problems.append(f"queue entries {qids} are live for {wid}, which is not a COMMIT_READY mutating Ticket")
    seqs = [e["seq"] for e in entries.values()]
    if len(set(seqs)) != len(seqs) or any(s >= queue["next_seq"] for s in seqs):
        problems.append(f"queue positions are not unique issued numbers: {sorted(seqs)} (next {queue['next_seq']})")
    # 35. At most one lease, held by the one LEASED entry; its custodian is that entry's custody invocation, active
    #     or marked for reconciliation (never released by a timeout).
    leased = sorted(q for q, e in entries.items() if e["state"] == "LEASED")
    if (lease is None and leased) or (lease is not None and leased != [lease["entry"]]):
        problems.append(f"LEASED entries {leased} disagree with the lease {lease}")
    if lease is not None:
        holder = entries.get(lease["entry"]) or {}
        cust = invocations.get(lease["custodian"]) or {}
        if (cust.get("kind") != "integration_attempt" or cust.get("queue_entry") != lease["entry"]
                or cust.get("work_unit") != holder.get("work")):
            problems.append(f"the lease's custodian {lease['custodian']} is not {lease['entry']}'s custody invocation")
        if cust.get("status") != "active" and lease["reconcile"] is None:
            problems.append(f"the lease's custodian {lease['custodian']} is {cust.get('status')} and the lease is not "
                            "marked for reconciliation")
    # 36. A custody invocation is the engine's: no role, credential, harness or run; an active one is the lease's
    #     custodian, of the current Lead generation; it is on its Ticket's invocation list.
    for inv_id, inv in sorted(custodians.items()):
        if any(k in inv for k in ("role", "token_id", "execution_profile", "runs")) or inv.get("execution") != "engine":
            problems.append(f"{inv_id} is a custody invocation with a role, credential, harness or run")
        if inv["status"] == "active":
            if lease is None or lease["custodian"] != inv_id:
                problems.append(f"{inv_id} is an active custody invocation that holds no lease")
            if inv.get("generation") != state["lead"]["generation"]:
                problems.append(f"{inv_id} is an active custody invocation of an earlier Lead generation")
        unit = work.get(inv["work_unit"])
        if unit is not None and inv_id not in unit.get("invocations", []):
            problems.append(f"{inv_id} is not on {inv['work_unit']}'s invocation list")
    # 37. No publication without the lease: a publish in progress belongs to the lease holder (its custodian may
    #     have died since: the lease then awaits reconciliation, which finishes the publish first).
    for wid, u in sorted(work.items()):
        if (u.get("integration") or {}).get("status") == "publishing":
            if lease is None or (entries.get(lease["entry"]) or {}).get("work") != wid:
                problems.append(f"{wid} is publishing without the integration lease")
    # 38. Post-integration verification runs under the lease: every active integration-scope invocation is a child of
    #     the live lease's custodian.
    for inv_id, inv in sorted(invocations.items()):
        if inv.get("scope") == "integration" and inv["status"] == "active":
            if lease is None or inv.get("custodian") != lease["custodian"] or lease["reconcile"] is not None:
                problems.append(f"{inv_id} (integration verifier) is active outside a live lease")
    # 39. M4-D4: a lease rebuilds its candidate automatically at most once, and only an entry set aside for the Lead
    #     (DEFERRED or AWAITING_DISPOSITION) carries a disposition record.
    for qid, e in sorted(entries.items()):
        if e["rebuilds_used"] not in (0, 1):
            problems.append(f"{qid} used {e['rebuilds_used']} automatic rebuilds; one is allowed")
        if (e["disposition"] is not None) != (e["state"] in ("DEFERRED", "AWAITING_DISPOSITION")):
            problems.append(f"{qid} is {e['state']} with disposition {e['disposition']}")
    return problems


_LOG_CHECKED: dict[str, tuple[int, str | None]] = {}  # per project: (revision verified through, its h)


def outbox_violations(root: Path, state: dict[str, Any]) -> list[str]:
    """24. From the revision the outbox began, every revision has exactly one logical transition, chained to the one
    before, the newest equal to ``last_transition``. 26. A record holds at most 64 hot events, and an overflow's
    sidecar holds exactly the set its descriptor names. Each revision resolves from either physical representation
    (D3: unsealed, else its sealed segment, equivalent where both exist). Incremental: a walk checks each record
    once."""
    marker = state.get("outbox")
    if marker is None:
        return ["24: the control state has no outbox marker"]
    aew_root = Path(root) / ".aew"
    key = str(aew_root.resolve())
    through, prev_h = _LOG_CHECKED.get(key, (marker["since"] - 1 if marker["since"] else -1, None))
    if through > state["revision"]:  # a fresh project at the same path
        through, prev_h = (marker["since"] - 1 if marker["since"] else -1, None)
    problems: list[str] = []
    view = outbox.LogView(aew_root, marker["since"], retries=0)
    try:
        for record in outbox.read_transitions(aew_root, through, state["revision"], outbox=marker, prev_h=prev_h):
            raw = view.resolve(record["revision"]) or {}
            if len(raw.get("events") or []) > outbox.MAX_HOT_EVENTS:
                problems.append(f"26: revision {record['revision']} holds {len(raw['events'])} hot events")
            if (raw.get("event_overflow") is None) != (len(record["events"] or []) <= outbox.MAX_HOT_EVENTS):
                problems.append(f"26: revision {record['revision']}: overflow present iff more than 64 events")
            through, prev_h = record["revision"], record.get("h")
    except Exception as exc:  # noqa: BLE001 (the oracle reports, it does not crash)
        problems.append(f"24: {exc}")
    if through != state["revision"]:
        problems.append(f"24: the log stops at revision {through}, the state is at {state['revision']}")
    elif (view.resolve(through) or {}) != state["last_transition"]:
        problems.append("24: the newest log record is not the committed last_transition")
    if not problems:
        _LOG_CHECKED[key] = (through, prev_h)
    return problems


def m3_violations(root: Path, state: dict[str, Any], evidence: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    problems: list[str] = []
    tokens = state["tokens"]
    for wid in state["work"]:
        for ev in evidence.setdefault(wid, _evidence(root, wid)).values():
            # 17. No evidence postdates the revocation of the credential that produced it (rotation included:
            #     rule 5 sees only an invocation's current credential).
            cred = ev["producer"].get("credential")
            if cred is None:
                continue
            revoked = (tokens.get(cred) or {}).get("revoked_at")
            if revoked and ev["created_at"] > revoked:
                problems.append(f"{ev['id']} was written at {ev['created_at']} by credential {cred}, revoked at "
                                f"{revoked} ({tokens[cred].get('revoke_reason')})")
            # ... and the run it names is the one that held that credential.
            inv = state["invocations"].get(ev["producer"]["invocation"], {})
            holder = next((r["run"] for r in inv.get("runs") or [] if r["token_id"] == cred), None)
            if ev["producer"].get("run") != holder:
                problems.append(f"{ev['id']} names run {ev['producer'].get('run')}, but credential {cred} was held by "
                                f"{holder}")
    for inv_id, inv in sorted(state["invocations"].items()):
        runs = inv.get("runs") or []
        # 18. Runs are numbered in order; at most one run holds live authority, and only the latest: every
        #     earlier run's credential is revoked, and the latest holds the invocation's credential.
        if [r["run"] for r in runs] != [f"R-{inv_id}-{n}" for n in range(1, len(runs) + 1)]:
            problems.append(f"{inv_id} runs are not numbered R-{inv_id}-1..n: {[r['run'] for r in runs]}")
        live = [r["run"] for r in runs if not (tokens.get(r["token_id"]) or {}).get("revoked_at")]
        if len(live) > 1:
            problems.append(f"{inv_id} has {len(live)} runs with live credentials: {live}")
        if live and live != [runs[-1]["run"]]:
            problems.append(f"{inv_id}: {live} holds a live credential but is not the latest run {runs[-1]['run']}")
        if runs and inv["status"] == "active" and runs[-1]["token_id"] != inv["token_id"]:
            problems.append(f"{inv_id} is active but its latest run {runs[-1]['run']} does not hold its credential")
        if len({r["token_id"] for r in runs}) != len(runs):
            problems.append(f"{inv_id}: two runs share a credential")
    return problems


def _evidence(root: Path, wid: str) -> dict[str, dict[str, Any]]:
    records, _ = E.scan(root / ".aew", wid)
    return {e["id"]: e for e in records}


def assert_control_invariants(project_or_root: Any) -> None:
    root = Path(getattr(project_or_root, "root", project_or_root))
    problems = control_violations(root)
    assert not problems, "control-state invariants violated:\n  " + "\n  ".join(problems)


# ------------------------------------------------------------------ M2: hierarchy and non-mutating work (ADR-0007/0008)

EXECUTORS = {"investigator", "researcher", "planner"}
EXECUTE_KIND = {"investigator": "discovery_record", "researcher": "research_record", "planner": "plan_proposal"}
PARENT_KINDS = {"ticket": {"story", "epic"}, "story": {"epic"}, "epic": set()}


UNSTARTED_OR_TERMINAL = {"BLOCKED", "READY", "REPLAN_REQUIRED", "DONE", "CANCELLED"}


def _dispatch_binding_violations(root: Path, state: dict[str, Any]) -> list[str]:
    work = state["work"]
    problems: list[str] = []

    def in_source(commit: str | None, base: str | None) -> bool:
        return bool(commit and base) and _git("merge-base", "--is-ancestor", commit, base, cwd=root).returncode == 0

    def satisfied(dep: dict[str, str], base: str | None) -> bool:
        up = work.get(dep["id"])
        if up is None or up["state"] != "DONE":
            return False
        if dep["kind"] != "mutating":
            return True
        if up["kind"] == "ticket":
            return in_source((up.get("integration") or {}).get("commit"), base)
        below, stack = [], [c for c, x in work.items() if x.get("parent") == dep["id"]]
        while stack:
            c = stack.pop()
            below.append(c)
            stack.extend(k for k, x in work.items() if x.get("parent") == c)
        return all(in_source((work[d].get("integration") or {}).get("commit"), base) for d in below
                   if work[d]["kind"] == "ticket" and work[d].get("mutating") and work[d]["state"] == "DONE")

    for wid, u in sorted(work.items()):
        if u["kind"] != "ticket" or u["state"] in UNSTARTED_OR_TERMINAL:
            continue
        if u.get("mutating"):
            attempt = u.get("workspace") or {}
            if attempt.get("status") != "active":
                continue
            base = attempt.get("base_commit")
        else:
            attempt = u.get("execution") or {}
            if not attempt:
                continue
            base = attempt.get("observed_commit")
        edges, anc = list(u.get("depends_on", [])), u.get("parent")
        while anc:
            edges += work[anc].get("depends_on", [])
            anc = work[anc].get("parent")
        current = {(e["id"], e["kind"]) for e in edges}
        recorded = attempt.get("dependencies")
        if recorded is not None and current != {(e["id"], e["kind"]) for e in recorded}:
            problems.append(f"{wid} ({u['state']}) was dispatched with dependencies {sorted(recorded, key=str)} but "
                            f"now has {sorted(current)}")
        for dep in sorted(current):
            if not satisfied({"id": dep[0], "kind": dep[1]}, base):
                problems.append(f"{wid} ({u['state']}) depends on {dep[0]}:{dep[1]}, which is not satisfied in the "
                                f"source its attempt works from ({str(base)[:12]})")
    return problems


def cap_violations(root: Path, state: dict[str, Any] | None = None) -> list[str]:
    """The concurrency caps, checked against the current policy file. Both caps are admission rules (operator,
    2026-10-04): lowering one never makes admitted work illegal, it drains. So this holds only while the policy is
    unchanged, which is how the seeded walks use it: there it still catches any path that admits past a cap (the M2
    re-review's redispatch bypass). It is not part of the general oracle."""
    root = Path(root)
    if state is None:
        state, _ = with_cold(root, load_control(root))
    gates_file = root / ".aew" / "policy" / "gates.yaml"
    gates = (yaml.safe_load(gates_file.read_text(encoding="utf-8")) or {}) if gates_file.exists() else {}
    problems: list[str] = []
    live = sorted(wid for wid, u in state["work"].items()
                  if u["kind"] == "ticket" and u.get("mutating")
                  and (u.get("workspace") or {}).get("status") == "active")
    mutating_cap = max(1, int(gates.get("mutating_concurrency") or 1))
    if len(live) > mutating_cap:
        problems.append(f"mutating cap {mutating_cap} exceeded: live mutating workspaces {live}")
    cap = gates.get("non_mutating_concurrency")
    if cap:
        # An engine custody invocation (M4-D's `integration_attempt` custodian) has a `kind` and no `role`.
        busy = sorted({inv["work_unit"] for inv in state["invocations"].values() if inv["status"] == "active"
                       and inv.get("role") in EXECUTORS and inv.get("scope") == "observation"})
        if len(busy) > cap:
            problems.append(f"{len(busy)} non-mutating Tickets have active executors {busy}; the policy cap is {cap}")
    return problems


def m2_violations(root: Path, state: dict[str, Any]) -> list[str]:
    if state.get("schema") == "aew/control/v2" and "_archived" not in state:  # a caller passed the hot state
        state, _ = with_cold(Path(root), state)
    problems: list[str] = []
    work, invocations = state["work"], state["invocations"]
    tokens = state["tokens"]

    def children(wid: str) -> list[str]:
        return [c for c, u in work.items() if u.get("parent") == wid]

    def descendants(wid: str) -> list[str]:
        out, stack = [], children(wid)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(children(c))
        return out

    for wid, u in sorted(work.items()):
        parent = u.get("parent")
        # 6. Hierarchy shape: parent kinds, no cycles.
        if parent is not None:
            if parent not in work or work[parent]["kind"] not in PARENT_KINDS[u["kind"]]:
                problems.append(f"{wid} ({u['kind']}) has an invalid parent {parent}")
            seen, anc = {wid}, parent
            while anc:
                if anc in seen:
                    problems.append(f"{wid} is in a parent cycle")
                    break
                seen.add(anc)
                anc = work.get(anc, {}).get("parent")
        if u["kind"] != "ticket":
            kids = children(wid)
            # 7. Parent state is the derivation: terminal only by recorded decision, with every descendant terminal.
            if u["state"] in {"DONE", "CANCELLED"}:
                open_desc = [d for d in descendants(wid) if work[d]["state"] not in {"DONE", "CANCELLED"}]
                if open_desc:
                    problems.append(f"{wid} is {u['state']} with open descendants {open_desc}")
                decided = u.get("closeout") if u["state"] == "DONE" else u.get("cancellation")
                if not decided:
                    problems.append(f"{wid} is {u['state']} without a recorded Lead decision")
                active = [i for i in [*u.get("invocations", []), *[x for d in descendants(wid)
                                                                  for x in work[d].get("invocations", [])]]
                          if invocations[i]["status"] == "active"]
                if active:
                    problems.append(f"{wid} is {u['state']} but invocations below it are active: {active}")
            if u["state"] == "DONE" and not any(work[k]["state"] == "DONE" for k in kids):
                problems.append(f"{wid} was closed without a DONE child")
            if u["state"] == "ACCEPTANCE_PENDING" and (not kids or any(work[k]["state"] not in {"DONE", "CANCELLED"}
                                                                        for k in kids)):
                problems.append(f"{wid} is ACCEPTANCE_PENDING with open or no children")
            continue
        if u.get("mutating"):
            continue
        # 8. A non-mutating Ticket never mutates, never integrates, never has an implementer.
        if u.get("workspace") or u.get("integration") or u.get("implementer_invocation"):
            problems.append(f"{wid} is non-mutating but holds a workspace/integration/implementer")
        if u["state"] in {"COMMIT_READY"}:
            problems.append(f"{wid} is non-mutating but reached COMMIT_READY")
        execution = u.get("execution") or {}
        # 9. At most one active execute invocation, and only the current attempt's.
        active_exec = [i for i in u.get("invocations", []) if invocations[i]["status"] == "active"
                       and invocations[i].get("role") in EXECUTORS]
        if len(active_exec) > 1:
            problems.append(f"{wid} has {len(active_exec)} active executors {active_exec}")
        for i in active_exec:
            if invocations[i].get("attempt") != execution.get("attempt") or execution.get("invocation") != i:
                problems.append(f"{wid}: executor {i} (attempt {invocations[i].get('attempt')}) is active but the "
                                f"current attempt is {execution.get('attempt')}")
        # 10. The accepted record is the pinned kind from the current attempt; DONE needs it and a completion record.
        rec = execution.get("record")
        if rec:
            ev = _evidence(root, wid).get(rec["id"])
            if (ev is None or ev["kind"] != execution.get("expected_kind")
                    or ev.get("attempt") != execution.get("attempt")):
                problems.append(f"{wid}: accepted record {rec['id']} is not the pinned output of attempt "
                                f"{execution.get('attempt')}")
            elif execution.get("expected_kind") != EXECUTE_KIND.get(execution.get("archetype")):
                problems.append(f"{wid}: expected_kind does not match the executor archetype")
        if u["state"] == "DONE":
            if not rec:
                problems.append(f"{wid} is DONE without an accepted record")
            if not (root / ".aew" / (u.get("completion_record") or "missing")).exists():
                problems.append(f"{wid} is DONE without a completion record")
    # 11. Execute records come only from the matching archetype, on an observation snapshot.
    for wid in work:
        for ev in _evidence(root, wid).values():
            if ev["kind"] in EXECUTE_KIND.values():
                inv = invocations.get(ev["producer"]["invocation"], {})
                if EXECUTE_KIND.get(inv.get("role")) != ev["kind"] or inv.get("scope") != "observation":
                    problems.append(f"{ev['id']} ({ev['kind']}) was produced by {inv.get('role')}/{inv.get('scope')}")
    # 12. Retired observations belong to ended invocations; revoked credentials never wrote later evidence
    #     (rule 5 covers all invocations, including observation ones).
    for inv_id, inv in invocations.items():
        obs = inv.get("observation") or {}
        if obs.get("status") == "active" and inv["status"] != "active":
            problems.append(f"{inv_id} ended ({inv['status']}) but its observation is still marked active")
        if inv["status"] == "active" and obs and tokens.get(inv["token_id"], {}).get("revoked_at"):
            problems.append(f"{inv_id} observation invocation is active with a revoked credential")
        # 13. Consumed inputs were CURRENT, external, or acknowledged by a recorded decision for exactly the
        #     commit this invocation was dispatched against (dependency satisfied != input acceptable).
        dispatched_at = obs.get("commit") or (inv.get("snapshot") or {}).get("base_revision")
        acks = work.get(inv["work_unit"], {}).get("input_acknowledgements", [])
        for i in inv.get("inputs") or []:
            if i.get("freshness") == "CURRENT" or i.get("basis") == "external":
                continue
            ack = next((a for a in acks if a["decision"] == i.get("acknowledgement")), None)
            if not ack or (ack["evidence"], ack["sha256"], ack["commit"]) != (i["id"], i["sha256"], dispatched_at):
                problems.append(f"{inv_id} consumed {i['id']} ({i.get('freshness')}) without an acknowledgement "
                                f"for its dispatch commit {str(dispatched_at)[:12]}")
    # 14. A started Ticket's attempt holds under its current effective dependencies (M2 review B2): the edges
    #     recorded at its dispatch are its edges now, and each is satisfied in the source it works from (M1 rule).
    problems += _dispatch_binding_violations(root, state)
    # 15. Moved to cap_violations: the non-mutating cap, like the mutating one, is an admission rule (operator,
    #     2026-10-04), so it is not an invariant of the state against whatever the policy says now.
    # 16. A parent's acceptance is a downstream assignment (M2 re-review decision): every report its closeout relied
    #     on was dispatched under exactly the dependencies the closeout records, and each of those was DONE.
    for wid, u in sorted(work.items()):
        record = (u.get("closeout") or {}).get("record")
        if u["kind"] == "ticket" or u["state"] != "DONE" or not record or not (root / ".aew" / record).exists():
            continue
        meta, _ = parse_frontmatter((root / ".aew" / record).read_text(encoding="utf-8"))
        deps = [{"id": d["id"], "kind": d["kind"]} for d in meta.get("dependencies", [])]
        unmet = [d["id"] for d in meta.get("dependencies", []) if d.get("state") != "DONE"]
        if unmet:
            problems.append(f"{wid} closed with unsatisfied dependencies {unmet}")
        reports = _evidence(root, wid)
        for gate, ev_id in (meta.get("basis") or {}).items():
            ev = reports.get(ev_id)
            if ev is None or ev["kind"] not in {"review", "verification"}:
                continue
            dispatched_with = invocations.get(ev["producer"]["invocation"], {}).get("dependencies")
            if dispatched_with != deps:
                problems.append(f"{wid} closed on {gate} report {ev_id}, dispatched under dependencies "
                                f"{dispatched_with} rather than {deps}")
    return problems


# ------------------------------------------------------------------ F9-A: coordination messages (rules 52-58, C1-C7)

THREAD_GENESIS = "aew/coordination-thread/v1"


def _thread_lines(raw: bytes, invocation: str) -> tuple[list[dict[str, Any]], int, str | None]:
    """An independent reading of a thread: each complete line's entry while the chain holds, the verified length, and
    the first problem (None when every complete line verifies). An incomplete final line is not read (C1)."""
    head = hashlib.sha256(f"{THREAD_GENESIS}:{invocation}".encode()).hexdigest()
    entries, verified = [], 0
    end = raw.rfind(b"\n") + 1
    for n, line in enumerate(raw[:end].split(b"\n")[:-1], 1):
        try:
            entry = json.loads(line)
            h = entry.pop("h")
            body = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        except (ValueError, KeyError, AttributeError, TypeError):
            return entries, verified, f"line {n} is not a chained JSON line"
        if hashlib.sha256(bytes.fromhex(head) + body).hexdigest() != h:
            return entries, verified, f"line {n} breaks the chain"
        head = h
        entries.append(entry)
        verified += len(line) + 1
    return entries, verified, None


def coordination_violations(root: Path, hot: dict[str, Any], full: dict[str, Any], *,
                            fallback_allowed: bool = False) -> list[str]:
    """52-58 (F9-A plan v4 §7, C1 to C7), over every thread on disk and the full state (hot and archived units):

    52 (C1) chains and identity; 53 (C2) authority at the time; 54 (C3) replies; 55 (C4) idempotency keys; 56 (C5)
    facts and the seen log; 57 (C6) seals, the marker and the registration key, and no seal by the commit check's
    fallback (a path that missed its call; ``fallback_allowed`` only for the test that provokes one); 58 (C7) no state
    moved, and only the coordination keys the plan names, within their bounds."""
    aew = Path(root) / ".aew"
    threads = sorted(aew.glob("work/*/coordination/INV-*.jsonl"))
    problems: list[str] = []
    store, unseen = hot.get("coordination_store"), hot.get("coordination_unseen")
    if not threads:
        if unseen is not None:
            problems.append("58: coordination_unseen without any thread")
        if any(u.get("coordination") for u in full["work"].values()):
            problems.append("58: a unit names a seal but no thread exists")
        return problems
    if not (aew / "coordination/marker.yaml").is_file():
        problems.append("57: a thread exists but the project marker does not")
    if store is None:
        problems.append("57: a thread exists but control state has no coordination_store")
    # The Lead generations and the revision each began at, the ops, and the declared events, from the transition log.
    began: dict[int, int] = {}
    fallbacks: list[str] = []
    ops: dict[int, Any] = {}
    marker = hot.get("outbox") or {}
    start = marker["since"] - 1 if marker.get("since") else -1
    try:
        for record in outbox.read_transitions(aew, start, hot["revision"], outbox=marker or None):
            ops[record["revision"]] = record.get("op")
            for e in record.get("events") or []:
                if e["kind"] == "lead.generation" and e.get("to") is not None:
                    began.setdefault(e["to"], record["revision"])
                if e["kind"] == "coordination.seal_fallback":
                    fallbacks.append(f"{e['invocation']} ({e['op']}, revision {record['revision']})")
    except Exception as exc:  # noqa: BLE001 (the oracle reports, it does not crash)
        problems.append(f"53: the transition log cannot be read: {exc}")
    if fallbacks and not fallback_allowed:
        problems.append(f"57: sealed by the commit check's fallback (a path missed its seal call): {fallbacks}")
    if any(str(op).startswith("message.") for op in ops.values()):
        problems.append("58: a transition records a message operation")
    if store is not None:
        wrote = "migrate" if store.get("via") == "migrate" else "manifest.adopt"  # a v1 adoption registers at migrate
        if ops.get(store["since_rev"], wrote) != wrote:
            problems.append(f"58: coordination_store was written by {ops[store['since_rev']]}, not {wrote}")
    seen_lines: list[dict[str, Any]] = []
    seen_path = aew / "coordination/lead-seen.jsonl"
    if seen_path.is_file():
        raw = seen_path.read_bytes()
        seen_lines = [json.loads(x) for x in raw[:raw.rfind(b"\n") + 1].split(b"\n")[:-1]]
    seals: dict[str, dict[str, Any]] = {}
    for path in threads:
        work_id, inv_id = path.parent.parent.name, path.stem
        where = f"{inv_id}'s thread"
        raw = path.read_bytes()
        inv = full["invocations"].get(inv_id) or {}
        unit = full["work"].get(work_id) or {}
        pointer = next((p for p in unit.get("coordination") or [] if p["invocation"] == inv_id), None)
        seal = None
        if pointer is not None:
            seal_path = aew / pointer["seal"]
            if sha256_file(seal_path) != pointer["sha256"]:
                problems.append(f"57: {inv_id}'s seal {pointer['seal']} does not hold its pointer's hash")
            else:
                seal = load_yaml(seal_path.read_text(encoding="utf-8"))
                seals[inv_id] = seal
                if hashlib.sha256(raw).hexdigest() != seal["thread"]["sha256"] or len(raw) != seal["thread"]["size"]:
                    problems.append(f"57: {where} is not the bytes its seal pins (a line follows the sealed head?)")
                if pointer["closed_rev"] != seal["closed_rev"] or pointer["messages"] != seal["messages"]:
                    problems.append(f"57: {inv_id}'s pointer disagrees with its seal")
        if inv.get("status") != "active" and pointer is None:
            problems.append(f"57: {inv_id} is {inv.get('status')} but its thread has no seal")
        if inv.get("status") == "active" and pointer is not None:
            problems.append(f"57: {inv_id} is active but its thread is sealed")
        entries, verified, problem = _thread_lines(raw, inv_id)
        if problem and not (seal and seal["damaged"] and verified >= seal.get("verified_bytes", 0)):
            problems.append(f"52: {where}: {problem}")
        if seal is not None and not seal["damaged"] and verified != len(raw):
            problems.append(f"52: {where} is sealed whole but does not verify to its end")
        messages = [e["message"] for e in entries if e.get("type") == "message"]
        by_id = {m["id"]: m for m in messages}
        if len(messages) > 200:
            problems.append(f"58: {where} holds {len(messages)} messages, beyond its bound")
        for n, m in enumerate(messages, 1):
            if (m["seq"], m["id"], m["thread"], m["work_unit"]) != (n, f"MSG-{inv_id}-{n}", inv_id, work_id):
                problems.append(f"52: {where}: message {n} is misnumbered or names another thread or unit")
            lead = m["sender"].startswith("lead:")
            if lead:
                g = int(m["sender"].split(":")[1])
                if not began.get(g, 10 ** 9) <= m["checked_rev"] < began.get(g + 1, 10 ** 9):
                    problems.append(f"53: {m['id']}'s generation {g} was not current at revision {m['checked_rev']}")
                if inv.get("scope") == "revision":
                    problems.append(f"58: {m['id']} is Lead text to a confirmer")
            elif m["sender"] != f"invocation:{inv_id}":
                problems.append(f"53: {m['id']} was sent by {m['sender']}, not the thread's invocation")
            target = by_id.get(m["in_reply_to"] or "")
            if m["in_reply_to"] is not None and (target is None or target["seq"] >= m["seq"]):
                problems.append(f"54: {m['id']} replies to {m['in_reply_to']}, not an earlier message of its thread")
            if not lead and (target is None or not target["sender"].startswith("lead:")):
                problems.append(f"54: worker message {m['id']} does not reply to a Lead message")
        keys = [(m["sender"], m["idempotency_id"]) for m in messages]
        if len(keys) != len(set(keys)):
            problems.append(f"55: {where} holds two messages with one (sender, idempotency id)")
        recorded: set[str] = set()
        for e in entries:
            if e.get("type") == "message":
                recorded.add(e["message"]["id"])
            elif e["fact"]["message"] not in recorded:
                problems.append(f"56: {where}: a {e['fact']['kind']} fact precedes the message it names")
        posted = {e["fact"]["message"] for e in entries if e.get("type") == "fact" and e["fact"]["kind"] == "POSTED"}
        for u in (seal or {}).get("undeliverable") or []:
            if u["message"] in posted or not by_id.get(u["message"], {}).get("sender", "").startswith("lead:"):
                problems.append(f"56: {u['message']} is undeliverable but was posted, or is not a Lead message")
    listed = {m: inv for inv, seal in seals.items() for m in seal["unseen_by_lead"]}
    for line in seen_lines:
        if "message" in line and line["message"] not in listed:
            problems.append(f"56: the seen log names {line['message']}, which no seal lists as unseen")
        if line.get("generation") not in began:
            problems.append(f"56: the seen log names generation {line.get('generation')}, which never existed")
    if unseen is not None:
        if len(unseen["entries"]) > 20:
            problems.append(f"58: coordination_unseen holds {len(unseen['entries'])} entries, beyond its cap")
        if not unseen["entries"] and not unseen["omitted"]:
            problems.append("58: an empty coordination_unseen stays in control state")
        for e in unseen["entries"]:
            if listed.get(e["message"]) != e["invocation"]:
                problems.append(f"58: coordination_unseen lists {e['message']}, which its seal does not")
    return problems
