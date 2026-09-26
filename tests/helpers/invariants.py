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
        # 4. VERIFICATION_FAILED is left only by a Lead classification (or cancellation).
        exits = [h for h in u.get("history", []) if h.get("from") == "VERIFICATION_FAILED"
                 and h.get("to") not in {"CANCELLED", "VERIFICATION_FAILED"}]
        if len(exits) > len(u.get("classifications", [])):
            problems.append(f"{wid} left VERIFICATION_FAILED {len(exits)}x with "
                            f"{len(u.get('classifications', []))} classification(s)")
        if u["state"] == "INTERRUPTED" and u.get("interrupted_from") == "VERIFICATION_FAILED":
            problems.append(f"{wid} was interrupted out of VERIFICATION_FAILED (classification pending)")
    return problems


def assert_control_invariants(project_or_root: Any) -> None:
    root = Path(getattr(project_or_root, "root", project_or_root))
    problems = control_violations(root)
    assert not problems, "control-state invariants violated:\n  " + "\n  ".join(problems)
