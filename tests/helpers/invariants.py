"""Cross-operation control-state invariants (review 2026-09-26, "expand adversarial sequences").

A test oracle, not engine code: it reads the durable, human-readable control
state the same way an operator or another tool would, and checks properties
that must hold after *any* sequence of operations — the compositions the
independent review found unguarded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

from aew.engine.store import deserialize_control
from aew.knowledge import evidence as E
from aew.util import parse_frontmatter


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def load_control(root: Path) -> dict[str, Any]:
    path = root / ".aew/state/control.yaml"
    return deserialize_control(path.read_bytes(), source=str(path))


def control_violations(root: Path) -> list[str]:
    root = Path(root)
    state = load_control(root)
    manifest = yaml.safe_load((root / ".aew/project.yaml").read_text(encoding="utf-8"))
    ref = f"refs/heads/{manifest['repository']['authoritative_branch']}"
    tokens = state["tokens"]
    problems: list[str] = []
    evidence: dict[str, dict[str, dict[str, Any]]] = {}

    # 1. Serial mutation: at most one mutating Ticket holds a live workspace (ADR-0003 B6).
    live = sorted(wid for wid, u in state["work"].items()
                  if u["kind"] == "ticket" and u.get("mutating")
                  and (u.get("workspace") or {}).get("status") == "active")
    if len(live) > 1:
        problems.append(f"serial cap exceeded: live mutating workspaces {live}")

    # 2. Every active invocation is bound to its Ticket's *current* live workspace, with a live credential;
    #    every inactive invocation's credential is revoked.
    for inv_id, inv in sorted(state["invocations"].items()):
        tok = tokens.get(inv.get("token_id") or "", {})
        if inv["status"] != "active":
            if tok and not tok.get("revoked_at"):
                problems.append(f"{inv_id} is {inv['status']} but its credential is not revoked")
            continue
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


def m2_violations(root: Path, state: dict[str, Any]) -> list[str]:
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
                       and invocations[i]["role"] in EXECUTORS]
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
            if ev is None or ev["kind"] != execution.get("expected_kind") or ev.get("attempt") != execution.get("attempt"):
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
    # 15. Active non-mutating executors never exceed the policy cap (M2 re-review: redispatch bypassed it).
    #     Checked against the current policy file; tests never lower the cap while executors are active.
    gates_file = root / ".aew" / "policy" / "gates.yaml"
    cap = (yaml.safe_load(gates_file.read_text(encoding="utf-8")) or {}).get("non_mutating_concurrency") \
        if gates_file.exists() else None
    if cap:
        busy = sorted({inv["work_unit"] for inv in invocations.values() if inv["status"] == "active"
                       and inv["role"] in EXECUTORS and inv.get("scope") == "observation"})
        if len(busy) > cap:
            problems.append(f"{len(busy)} non-mutating Tickets have active executors {busy}; the policy cap is {cap}")
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
