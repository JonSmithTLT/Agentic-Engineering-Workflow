#!/usr/bin/env python3
"""Control-plane performance: synthetic projects and per-command measurements (M3 plan §2.10; m3-performance.md).

    python tools/perf/control_plane.py run --sizes 50,500,3000 --work DIR [--reps 3] [--json results.json]
    python tools/perf/control_plane.py sweep --points 20:250,20:3000,200:250 --work DIR [--json results.json]
    python tools/perf/control_plane.py sweep --hierarchy --points 3:250,3:1000,3:3000 --work DIR [--json ...]
    python tools/perf/control_plane.py coldwrite --records 1000,3000,10000,30000 --work DIR [--json ...]
    python tools/perf/control_plane.py build --units 500 --out DIR           # a project only (read-only use)
    python tools/perf/control_plane.py footprint PROJECT                     # any project, read-only

**Projects.** A template is made by the real engine, in-process:
- T-0001 is taken through its whole lifecycle to DONE: four invocations, their evidence, a completion record;
- T-0002 is planned (READY);
- T-0003 awaits review ingest, its reviewer still active (the `review ingest`, `gate show` and `context pack`
  target);
- T-0004 is a READY investigation (the dispatch target: T-0003 holds the one mutating slot, and a read-only
  dispatch also creates a worktree).

The rest is cloned from T-0001 and T-0002: for ``run``, two DONE for each planned, until the project has the
requested number of units; for ``sweep``, until it has the requested numbers of open and completed units. Every
id (unit, invocation, credential id, decision), path, evidence seal and content hash is rewritten, so the engine
accepts the result as its own. The build checks this: the control state parses and validates, `doctor`
passes, `status` finds every record intact, `resume` finds no contradiction, and cloned evidence verifies. Clones
are top-level Tickets.

**Footprint.** How the bytes of ``control.yaml`` divide between the work that is open and the project's history
(ADR-0011, designer note 2026-09-27: hot state and latency should track active complexity, not lifetime history).
Each record is sized as it is serialized in the file:
- *open*: each open unit's record, its invocations (live, and ended ones it still carries) and their credentials
  (active, and revoked ones);
- *history*: each DONE or CANCELLED unit's record, with its invocations and credentials;
- *other*: the Lead, its credentials and handoff offers, counters, and the file's own structure.

*Terminal records* are everything ADR-0011 would move out of the hot state: the history, plus the ended invocations
and revoked credentials of open units. The rest is the *live* part.

A **sweep** measures the same commands at several ``open:completed`` points, so the dependence of cost on each can be
read separately: points with the same open count and growing history show what history alone costs.

**Measurements.** Each command runs as the real CLI in its own process, with ``AEW_PROFILE`` recording its phases
and counts; wall time is measured around the process. Mutations are measured on the project and undone after
each repetition (the `.aew` directory and any worktree or branch the command created are restored).

The Lead credential of a synthetic project exists only in this process's memory and in the environment of the
commands it runs; it is never written anywhere.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from aew.engine.api import Engine
from aew.engine.base import as_v1
from aew.engine.store import serialize_control
from aew.knowledge import evidence as E
from aew.util import dump_yaml, parse_frontmatter, sha256_text

NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
FILES = {
    ".gitignore": "__pycache__/\n*.pyc\n",
    "README.md": "# calc\n",
    "calc/__init__.py": "from calc.core import add\n",
    "calc/core.py": "def add(a, b):\n    return a + b\n",
    "tests/test_core.py": "from calc.core import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
}
PATCH = {"calc/core.py": FILES["calc/core.py"] + "\n\ndef subtract(a, b):\n    return a - b\n",
         "tests/test_subtract.py": "from calc.core import subtract\n\n\ndef test_subtract():\n"
                                   "    assert subtract(5, 3) == 2\n"}
PLAN = "1. Add subtract(a, b) to calc/core.py.\n2. Add a focused test.\n"
REPORT = {"claim": "subtract implemented", "result": "pass", "producer": {"model": "perf"},
          "implementation": {"files_changed": sorted(PATCH), "checks_run": ["unit"], "deviations": [],
                             "self_review": {"completed": True, "notes": "matches the plan"}}}
REVIEW = {"claim": "independent review", "producer": {"model": "perf"},
          "review": {"independence": "R1", "disposition": "pass", "findings": [], "resolved_findings": []}}


# ---------------------------------------------------------------------------------------------- template

def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, **NO_WINDOW).stdout


def submission(meta: dict[str, Any], body: str = "Report.\n") -> str:
    return f"---\n{dump_yaml(meta)}---\n{body}"


class Template:
    """The engine-made part of a project, and the Lead credential that made it (in memory only)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        git("init", "-q", "-b", "main", cwd=root)
        git("config", "user.name", "AEW perf", cwd=root)
        git("config", "user.email", "aew-perf@invalid", cwd=root)
        git("config", "core.autocrlf", "false", cwd=root)
        for rel, text in FILES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8", newline="\n")
        git("add", "-A", cwd=root)
        git("commit", "-q", "-m", "initial", cwd=root)
        Engine.initialize(root, project_id="perf")
        # The M3 layout these measurements were defined on: control state v1, where finished work stays hot. ADR-0011's
        # `aew migrate` (P2d) turns such a project into v2, which is how the series measure archival.
        control = root / ".aew/state/control.yaml"
        from aew.engine.store import deserialize_control
        state = deserialize_control(control.read_bytes(), source="control.yaml")
        control.write_bytes(serialize_control(as_v1(state)))
        policy = root / ".aew/policy"
        (policy / "checks.yaml").write_text(dump_yaml({
            "schema": "aew/checks/v1", "baseline_failures": [],
            "checks": {"unit": {"configured": True, "command": ["{python}", "-c", "import calc.core"], "cwd": ".",
                                "timeout_s": 120, "description": "import check (fast: this measures AEW)"}}}),
            encoding="utf-8", newline="\n")
        (policy / "guardrails.yaml").write_text(dump_yaml({
            "schema": "aew/guardrails/v1", "protected_paths": [], "generated_paths": [],
            "ticket_scope_enforcement": True, "review_triggers": [], "dependency_rules": []}),
            encoding="utf-8", newline="\n")
        self.eng = Engine.discover(root)
        # ADR-0011 refuses the Lead's mutations on v1 until `aew migrate`; this in-process engine builds the M3 layout
        # anyway (every measurement then runs on the migrated project, through the CLI).
        self.eng._k.legacy_v1_writes = True
        self.token = self.eng.lead_acquire(expect_rev=0, session_label="perf")["token"]

    def rev(self) -> int:
        return self.eng.store.read()["revision"]

    def lead(self, method: str, **kw: Any) -> dict[str, Any]:
        return getattr(self.eng, method)(token=self.token, expect_rev=self.rev(), **kw)

    def parent_unit(self, kind: str, title: str, parent: str | None) -> str:
        """An Epic or Story with an accepted plan, so that Tickets below it can be dispatched (ADR-0007)."""
        wid = self.lead("work_create", kind=kind, title=title, risk_class=1, parent=parent)["id"]
        self.lead("plan_propose", no_assurance=True, work_id=wid, body=f"{title}: deliver its Tickets.\n")
        self.lead("plan_accept", work_id=wid, revision=1)
        return wid

    def planned(self, title: str, *, mutating: bool = True, parent: str | None = None) -> str:
        wid = self.lead("work_create", kind="ticket", title=title, risk_class=1, mutating=mutating, parent=parent,
                        scope_paths=["calc/**", "tests/**"], goal_backwards=["calc.core.subtract(5, 3) == 2"],
                        contract=["changes stay in calc/ and tests/"])["id"]
        self.lead("plan_propose", no_assurance=True, work_id=wid, body=PLAN, affected_paths=["calc/core.py"])
        self.lead("plan_accept", work_id=wid, revision=1)
        return wid

    def implemented(self, wid: str) -> None:
        out = self.lead("work_assign", work_id=wid)
        self.lead("work_transition", work_id=wid, to="RUNNING")
        workspace = Path(out["workspace"]["path"])
        for rel, text in PATCH.items():
            (workspace / rel).parent.mkdir(parents=True, exist_ok=True)
            (workspace / rel).write_text(text, encoding="utf-8", newline="\n")
        self.eng.check_run(invocation_token=out["invocation_token"], check_id="unit")
        self.eng.submit(invocation_token=out["invocation_token"], kind="implementation_report", text=submission(REPORT))
        self.lead("work_transition", work_id=wid, to="REVIEW_PENDING")

    def role(self, wid: str, role: str, scope: str = "ticket") -> str:
        return self.lead("invoke_create", work_id=wid, role=role, scope=scope)["invocation_token"]

    def verification(self, token: str, scope: str) -> str:
        checks = [self.eng.check_run(invocation_token=token, check_id="unit")["evidence"]]
        claims = [{"type": "goal_backwards", "claim": "subtract works", "result": "pass", "checks": checks[:1]}]
        if scope == "ticket":
            checks.append(self.eng.check_run(invocation_token=token, check_id="guardrails")["evidence"])
            claims.append({"type": "contract", "claim": "scope respected", "result": "pass", "checks": checks[1:]})
        return self.eng.submit(invocation_token=token, kind="verification", text=submission({
            "claim": "behavior verified", "producer": {"model": "perf"},
            "verification": {"scope": scope, "claims": claims}}))["evidence"]

    def done(self, wid: str) -> None:
        self.implemented(wid)
        review = self.eng.submit(invocation_token=self.role(wid, "reviewer"), kind="review",
                                 text=submission(REVIEW))["evidence"]
        self.lead("review_ingest", work_id=wid, evidence_id=review)
        self.lead("work_transition", work_id=wid, to="VERIFY_PENDING")
        self.lead("verify_ingest", work_id=wid, evidence_id=self.verification(self.role(wid, "verifier"), "ticket"))
        self.lead("work_transition", work_id=wid, to="COMMIT_READY")
        self.lead("integrate_prepare", work_id=wid)
        token = self.role(wid, "verifier", "integration")
        self.lead("verify_ingest", work_id=wid, evidence_id=self.verification(token, "integration"))
        self.lead("integrate_publish", work_id=wid)


def make_template(root: Path, *, hierarchy: bool = False) -> Template:
    """With ``hierarchy``, every Ticket (and so every clone) is a child of one open Story inside one open Epic: the
    ADR-0011 hierarchy-history series, where completed descendants accumulate below ancestors that stay open."""
    t = Template(root)
    parent = None
    if hierarchy:
        parent = t.parent_unit("story", "Representative story", t.parent_unit("epic", "Representative epic", None))
    t.done(t.planned("Add subtract()", parent=parent))     # T-0001: the DONE bundle
    t.planned("Planned work", parent=parent)               # T-0002: the planned bundle
    target = t.planned("Awaiting review ingest", parent=parent)  # T-0003
    t.implemented(target)
    t.review_target = t.eng.submit(invocation_token=t.role(target, "reviewer"), kind="review",
                                   text=submission(REVIEW))["evidence"]
    t.planned("Survey calc", mutating=False, parent=parent)  # T-0004: T-0003 holds the one mutating slot
    return t


# ---------------------------------------------------------------------------------------------- cloning

def ids_of(state: dict[str, Any], aew_root: Path, wid: str) -> dict[str, str]:
    """The template ids a clone of ``wid`` renames: the unit, its invocations, their credential ids, its decisions."""
    invs = list(state["work"][wid].get("invocations") or [])
    tokens = [state["invocations"][i]["token_id"] for i in invs]
    decisions = sorted(p.stem for p in (aew_root / "decisions").glob("D-*.md")
                       if f"\nwork_unit: {wid}\n" in p.read_text(encoding="utf-8"))
    return {"unit": [wid], "invocation": invs, "token": tokens, "decision": decisions}  # type: ignore[dict-item]


class Cloner:
    def __init__(self, root: Path) -> None:
        self.aew = root / ".aew"
        raw = (self.aew / "state/control.yaml").read_text(encoding="utf-8")
        from aew.engine.store import deserialize_control
        self.state = deserialize_control(raw.encode("utf-8"), source="control.yaml")
        self.counters = self.state["counters"]

    def next(self, kind: str, prefix: str) -> str:
        self.counters[kind] += 1
        return f"{prefix}-{self.counters[kind]:04d}"

    def clone(self, wid: str, groups: dict[str, list[str]]) -> str:
        mapping = {wid: self.next("ticket", "T")}
        mapping.update({i: self.next("invocation", "INV") for i in groups["invocation"]})
        mapping.update({t: f"tk_{secrets.token_hex(8)}" for t in groups["token"]})
        mapping.update({d: self.next("decision", "D") for d in groups["decision"]})
        pattern = re.compile(r"(?<![\w])(" + "|".join(sorted(map(re.escape, mapping), key=len, reverse=True))
                             + r")(?![\w])")

        def remap(value: Any) -> Any:
            if isinstance(value, str):
                return pattern.sub(lambda m: mapping[m.group(1)], value)
            if isinstance(value, list):
                return [remap(v) for v in value]
            if isinstance(value, dict):
                return {remap(k): remap(v) for k, v in value.items()}
            return value

        def rehash(node: Any) -> None:
            if isinstance(node, dict):
                if isinstance(node.get("path"), str) and node["path"] in written and "sha256" in node:
                    node["sha256"] = sha256_text(written[node["path"]])
                if node.get("record") in written and "record_sha256" in node:
                    node["record_sha256"] = sha256_text(written[node["record"]])
                for v in node.values():
                    rehash(v)
            elif isinstance(node, list):
                for v in node:
                    rehash(v)

        written: dict[str, str] = {}  # new relative path -> new text

        def evidence_record(path: Path) -> bool:
            rel = path.relative_to(self.aew).as_posix()
            return rel.startswith("evidence/") and rel.endswith(".md")

        sources = [p for d in (f"work/{wid}", f"evidence/{wid}") for p in (self.aew / d).rglob("*") if p.is_file()]
        sources += [self.aew / "decisions" / f"{d}.md" for d in groups["decision"]]
        # Evidence records last: each pins files (a check's log) whose renamed text changes their hash.
        for src in sorted(sources, key=evidence_record):
            rel = remap(src.relative_to(self.aew).as_posix())
            text = remap(src.read_text(encoding="utf-8"))
            if evidence_record(src):  # its pins rehashed, and a new seal over the renamed content
                meta, body = parse_frontmatter(text, source=rel)
                rehash(meta)
                text = E.seal(meta, body)
            target = self.aew / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
            written[rel] = text

        unit = remap(copy.deepcopy(self.state["work"][wid]))
        rehash(unit)
        self.state["work"][mapping[wid]] = unit
        for inv in groups["invocation"]:
            entry = remap(copy.deepcopy(self.state["invocations"][inv]))
            rehash(entry)
            self.state["invocations"][mapping[inv]] = entry
        for tok in groups["token"]:
            self.state["tokens"][mapping[tok]] = remap(copy.deepcopy(self.state["tokens"][tok]))
        return mapping[wid]

    def save(self) -> None:
        (self.aew / "state/control.yaml").write_bytes(serialize_control(self.state))


def grow(root: Path, units: int) -> None:
    """Clone the template's DONE and planned Tickets (two DONE for each planned) until the project has ``units``."""
    cloner = Cloner(root)
    state = cloner.state
    done, planned = ids_of(state, root / ".aew", "T-0001"), ids_of(state, root / ".aew", "T-0002")
    for i in range(max(units - len(state["work"]), 0)):
        cloner.clone(*(("T-0001", done) if i % 3 != 2 else ("T-0002", planned)))
    cloner.save()


def add_units(root: Path, *, done: int, planned: int) -> None:
    """Clone ``done`` more DONE Tickets and ``planned`` more planned ones."""
    cloner = Cloner(root)
    bundles = {"T-0001": ids_of(cloner.state, root / ".aew", "T-0001"),
               "T-0002": ids_of(cloner.state, root / ".aew", "T-0002")}
    for wid, n in (("T-0001", done), ("T-0002", planned)):
        for _ in range(n):
            cloner.clone(wid, bundles[wid])
    cloner.save()


def build(root: Path, units: int) -> Template:
    """The M3 (v1) layout at ``units``: the template grown by clones. ``migrate`` turns it into v2."""
    t = make_template(root)
    grow(root, units)
    validate(root)
    return t


def migrate(t: Template) -> dict[str, Any]:
    """``aew migrate`` (ADR-0011) on a built project, timed: the series measure the migrated project."""
    t0 = time.perf_counter()
    out = Engine.discover(t.root).migrate(token=t.token, expect_rev=t.rev())
    return {"migrate_s": round(time.perf_counter() - t0, 2), "archived": out["archived"], "hot": out["hot"],
            "history_entries": out["history"]["entries"]}


def validate(root: Path) -> dict[str, Any]:
    """The engine accepts the project as its own."""
    eng = Engine.discover(root)
    state = eng.store.read()
    failed = [c for c in eng.doctor_checks() if c.get("status") == "FAIL"]
    assert not failed, failed
    resume = eng.resume()  # contradictions include every record and plan whose hash does not match
    assert resume["contradictions"] == [], resume["contradictions"][:5]
    for wid in list(state["work"])[-3:]:
        records, problems = E.scan(eng.aew_root, wid)
        assert not problems, (wid, problems)
    return {"units": len(state["work"]), "invocations": len(state["invocations"]), "tokens": len(state["tokens"]),
            "control_bytes": (root / ".aew/state/control.yaml").stat().st_size}


# ---------------------------------------------------------------------------------------------- footprint

TERMINAL_UNITS = frozenset({"DONE", "CANCELLED"})
# ADR-0011 (control state v2): what the hot state keeps about archived work. Constant-size aggregates and bounded
# lists, never a record per finished unit (H1).
HOT_HISTORY_KEYS = ("cold", "recent", "archived_refs", "retained_workspaces", "retired_observations")


def _bytes(section: str, key: str, value: Any) -> int:
    """A record's size as it sits in ``control.yaml`` (under its section, at the file's indentation)."""
    return len(dump_yaml({section: {key: value}}).encode("utf-8")) - len(f"{section}:\n")


def footprint(state: dict[str, Any], control_bytes: int) -> dict[str, Any]:
    work, invocations, tokens = state["work"], state["invocations"], state["tokens"]
    open_units = {w for w, u in work.items() if u["state"] not in TERMINAL_UNITS}
    owner: dict[str, str] = {}  # credential id -> invocation
    for iid, inv in invocations.items():
        for tid in [inv.get("token_id"), *(r.get("token_id") for r in inv.get("runs") or [])]:
            if tid:
                owner[tid] = iid
    for tid, tok in tokens.items():
        iid = (tok.get("scope") or {}).get("invocation_id")
        if tok.get("kind") == "invocation" and iid:
            owner.setdefault(tid, iid)
    live = {"units": 0, "live_invocations": 0, "ended_invocations": 0, "active_credentials": 0,
            "revoked_credentials": 0}
    history = {"units": 0, "invocations": 0, "credentials": 0}
    for wid, unit in work.items():
        if wid in open_units:
            live["units"] += _bytes("work", wid, unit)
        else:
            history["units"] += _bytes("work", wid, unit)
    for iid, inv in invocations.items():
        size = _bytes("invocations", iid, inv)
        if inv.get("work_unit") not in open_units:
            history["invocations"] += size
        else:
            live["live_invocations" if inv.get("status") == "active" else "ended_invocations"] += size
    for tid, tok in tokens.items():
        iid = owner.get(tid)
        if iid is None:
            continue  # the Lead's credentials and handoff offers: "other"
        size = _bytes("tokens", tid, tok)
        if invocations.get(iid, {}).get("work_unit") not in open_units:
            history["credentials"] += size
        else:
            live["revoked_credentials" if tok.get("revoked_at") else "active_credentials"] += size
    open_total, history_total = sum(live.values()), sum(history.values())
    # v2: what stays hot about archived work is counted with the history (it is history, kept as aggregates).
    aggregates = sum(len(dump_yaml({k: state[k]}).encode("utf-8")) for k in HOT_HISTORY_KEYS if k in state)
    history["archived_aggregates"] = aggregates
    history_total += aggregates
    terminal = history_total + live["ended_invocations"] + live["revoked_credentials"]
    n_open, n_done = len(open_units), len(work) - len(open_units)
    return {"units": {"open": n_open, "completed": n_done},
            "control_bytes": control_bytes,
            "open_bytes": {**live, "total": open_total},
            "history_bytes": {**history, "total": history_total},
            "other_bytes": control_bytes - open_total - history_total,
            "per_open_unit_bytes": round(open_total / n_open) if n_open else None,
            "per_completed_unit_bytes": round(history_total / n_done) if n_done else None,
            "terminal_record_bytes": terminal,
            "live_bytes": control_bytes - terminal}


def project_footprint(root: Path) -> dict[str, Any]:
    """The hot footprint, plus (v2) the cold store on disk: the history records and the manifest."""
    path = root / ".aew/state/control.yaml"
    raw = path.read_bytes()
    from aew.engine.store import deserialize_control
    from aew.history.store import RECORD_GLOBS
    aew_root = root / ".aew"
    cold = [p for pattern in (*RECORD_GLOBS, "history/seg-*.yaml", "history/tail.yaml") for p in aew_root.glob(pattern)]
    return {**footprint(deserialize_control(raw, source="control.yaml"), len(raw)),
            "cold_bytes": sum(p.stat().st_size for p in cold if p.is_file())}


# ---------------------------------------------------------------------------------------------- measuring

READS = [("CLI floor (aew --version)", ["--version"]),
         ("lead show", ["lead", "show"]),
         ("status", ["status", "--json"]),
         ("work tree", ["work", "tree"]),
         ("resume", ["resume", "--json"]),
         ("gate show", ["gate", "show", "T-0003"]),
         ("context pack", ["context", "pack", "{reviewer}"]),
         ("harness status", ["harness", "status"])]
MUTATIONS = [("checkpoint (commit path)", ["checkpoint", "--next", "measure"]),
             ("dispatch (work dispatch)", ["work", "dispatch", "T-0004"]),
             ("review ingest", ["review", "ingest", "T-0003", "--evidence", "{review}"])]


class Snapshot:
    """Undo a mutation: restore `.aew` and remove worktrees and branches the command created."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.saved = Path(tempfile.mkdtemp(prefix="aew-perf-snap-", dir=root.parent)) / "aew"
        shutil.copytree(root / ".aew", self.saved)
        self.branches = set(git("branch", "--format=%(refname:short)", cwd=root).split())
        self.worktrees = self._worktrees()

    def _worktrees(self) -> set[str]:
        return {line.split(" ", 1)[1] for line in git("worktree", "list", "--porcelain", cwd=self.root).splitlines()
                if line.startswith("worktree ")}

    def _remove_worktree(self, wt: str) -> None:
        """Windows: a worktree created moments ago can still be held (an antivirus or indexer scanning its new
        files), and `git worktree remove` then fails. Retry; as a last resort delete it and prune git's record."""
        for _ in range(50):
            proc = subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=self.root, capture_output=True,
                                  text=True, **NO_WINDOW)
            if proc.returncode == 0:
                return
            time.sleep(0.2)
        for _ in range(50):
            try:
                shutil.rmtree(wt)
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(0.2)
        git("worktree", "prune", cwd=self.root)
        if wt in self._worktrees():
            raise RuntimeError(f"could not remove worktree {wt}: {proc.stderr.strip()}")

    def restore(self) -> None:
        for wt in self._worktrees() - self.worktrees:
            self._remove_worktree(wt)
        for branch in set(git("branch", "--format=%(refname:short)", cwd=self.root).split()) - self.branches:
            git("branch", "-D", branch, cwd=self.root)
        for _ in range(50):  # Windows: a file closed a moment ago can still be held briefly
            try:
                shutil.rmtree(self.root / ".aew")
                break
            except PermissionError:
                time.sleep(0.2)
        shutil.copytree(self.saved, self.root / ".aew")


def cli(root: Path, args: list[str], env: dict[str, str]) -> tuple[float, dict[str, Any]]:
    profile = Path(tempfile.mkdtemp(prefix="aew-perf-prof-", dir=root.parent)) / "profile.jsonl"
    t0 = time.perf_counter()
    res = subprocess.run([sys.executable, "-m", "aew", "-C", str(root), *args], capture_output=True, text=True,
                         env={**env, "AEW_PROFILE": str(profile)}, stdin=subprocess.DEVNULL, **NO_WINDOW)
    wall = time.perf_counter() - t0
    if res.returncode != 0:
        raise RuntimeError(f"aew {' '.join(args[:2])} failed: {res.stderr[-800:]}")
    lines = profile.read_text(encoding="utf-8").splitlines() if profile.exists() else []
    shutil.rmtree(profile.parent, ignore_errors=True)
    return wall, (json.loads(lines[-1]) if lines else {})


class Runner:
    """Runs each measured command against a built project; a mutation is undone after every run."""

    def __init__(self, t: Template) -> None:
        self.t = t
        inv = next(i for i, v in t.eng.store.read()["invocations"].items()
                   if v["work_unit"] == "T-0003" and v["status"] == "active")
        self.fill = {"{reviewer}": inv, "{review}": getattr(t, "review_target", "")}
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("AEW_")}
        self.snap: Snapshot | None = None

    def run(self, args: list[str], *, mutation: bool) -> tuple[float, dict[str, Any]]:
        args = [self.fill.get(a, a) for a in args]
        if not mutation:
            return cli(self.t.root, args, self.env)
        if self.snap is None:
            self.snap = Snapshot(self.t.root)
        # The Lead credential goes in the command's environment, never on its command line.
        try:
            return cli(self.t.root, [*args, "--expect-rev", str(self.t.rev())],
                       {**self.env, "AEW_LEAD_TOKEN": self.t.token})
        finally:
            self.snap.restore()

    def resnapshot(self) -> None:
        """The project was changed on purpose (grown): mutations are undone to this state from now on."""
        self.snap = None


def measure(t: Template, reps: int) -> list[dict[str, Any]]:
    runner = Runner(t)
    out = []
    for name, args in READS + MUTATIONS:
        mutation = (name, args) in MUTATIONS
        runs = [runner.run(args, mutation=mutation) for _ in range(reps)]
        walls = [w for w, _ in runs]
        profiles = [p for _, p in runs if p]
        phases = {k: statistics.median(p["phases_s"][k] for p in profiles) for k in profiles[0]["phases_s"]} \
            if profiles else {}
        out.append({"op": name, "wall_s": statistics.median(walls), "wall_min_s": min(walls),
                    "in_process_s": statistics.median(p["total_s"] for p in profiles) if profiles else None,
                    "phases_s": phases, "counts": profiles[-1]["counts"] if profiles else {}})
    return out


def micro(root: Path) -> dict[str, float]:
    """Where a parse and a commit go: YAML (pure Python and libyaml), schema validation, deep copy; and
    ``control_reparse_s``, the whole re-parse a run's supervisor does after a Lead commit changed the file (checksum,
    YAML and schema: ADR-0011 H3 and its absolute heartbeat bound)."""
    import yaml

    from aew.engine.store import deserialize_control
    from aew.schemas import validate as schema_validate

    raw = (root / ".aew/state/control.yaml").read_text(encoding="utf-8")
    raw_bytes = raw.encode("utf-8")
    body = raw.rsplit("\n# aew-checksum", 1)[0] + "\n"

    def timed(fn: Any) -> float:
        t0 = time.perf_counter()
        fn()
        return round(time.perf_counter() - t0, 4)

    from aew import util

    class PythonDumper(yaml.SafeDumper):
        pass

    class LibyamlDumper(yaml.CSafeDumper):
        pass

    for cls in (PythonDumper, LibyamlDumper):
        cls.add_representer(str, util._str_representer)
    options = {"sort_keys": False, "allow_unicode": True, "default_flow_style": False, "width": 100}
    state = yaml.load(body, Loader=yaml.CSafeLoader)
    return {"yaml_load_python_s": timed(lambda: yaml.load(body, Loader=yaml.SafeLoader)),
            "yaml_load_libyaml_s": timed(lambda: yaml.load(body, Loader=yaml.CSafeLoader)),
            "yaml_dump_python_s": timed(lambda: yaml.dump(state, Dumper=PythonDumper, **options)),
            "yaml_dump_libyaml_s": timed(lambda: yaml.dump(state, Dumper=LibyamlDumper, **options)),
            "schema_validate_s": timed(lambda: schema_validate("control", state, source="perf")),
            "deepcopy_s": timed(lambda: copy.deepcopy(state)),
            "control_reparse_s": timed(lambda: deserialize_control(raw_bytes, source="control.yaml"))}


# ---------------------------------------------------------------------------------------------- cold-write series

COLD_ROOT_REL = "state/history-root.yaml"  # P2b keeps the root in control.yaml (schema v2); until then, a file
COLD_AT = "2026-10-02T00:00:00Z"           # written in the same transaction (exactly as atomic, via the redo record)
COLD_BUNDLE_BYTES = 20_000                 # a DONE Ticket with its invocations and credentials (M3: about 20.3 KB)


class ColdStore:
    """A synthetic ADR-0011 cold store: ``n`` archived units behind a real control store, built quickly from small
    pre-written bundles; the measured archivals write realistic ones through the normal transaction path."""

    def __init__(self, aew_root: Path) -> None:
        from aew import SPEC_SET
        from aew.engine.store import ControlStore
        from aew.history.index import HistoryIndex
        from aew.history.store import History

        self.root = aew_root
        self.store = ControlStore(aew_root, lock_timeout=120)
        self.store.create({
            "schema": "aew/control/v1", "project_id": "cold", "spec_set": SPEC_SET, "revision": 0,
            "manifest_sha256": "0" * 64,
            "lead": {"schema": "aew/lead/v1", "status": "vacant", "generation": 0, "session_label": None,
                     "token_id": None, "acquired_at": None, "handoff": None},
            "tokens": {}, "counters": {"n": 0}, "work": {}, "invocations": {},
            "last_transition": {"revision": 0, "at": COLD_AT, "actor": {"kind": "init"}, "op": "init",
                                "summary": None, "reason": None, "refs": [], "txn": None}}, {})
        self.history = History(aew_root)
        self.index = HistoryIndex(aew_root)

    def current(self) -> dict[str, Any]:
        from aew.history import manifest as M
        from aew.util import load_yaml

        path = self.root / COLD_ROOT_REL
        return load_yaml(path.read_text(encoding="utf-8")) if path.exists() else M.empty_root()

    @staticmethod
    def fields(k: int, sha: str) -> dict[str, Any]:
        """An entry as an archived Ticket's would be: its links are what history traversal follows."""
        return {"kind": "unit", "id": f"T-{k:05d}", "path": f"work/T-{k:05d}/archive.yaml", "sha256": sha,
                "at": COLD_AT, "state": "DONE", "parent": "S-0001", "source": "engine",
                "links": {"depends_on": [f"T-{k - 1:05d}"], "decisions": [f"D-{2 * k:05d}", f"D-{2 * k + 1:05d}"],
                          "evidence": [f"E-{5 * k + i:06d}" for i in range(5)],
                          "integration_commit": [secrets.token_hex(20)],
                          "completion": [f"work/T-{k:05d}/completion.md"]}}

    def archive(self, count: int, *, realistic: bool) -> None:
        """Archive ``count`` more units in one transaction: pre-written small bundles (building), or realistic
        bundles staged through the redo record (what an archival in a Lead commit does)."""
        from aew.engine.store import Transition
        from aew.history.store import bundle_rel, prewrite
        from aew.util import dump_yaml

        k0 = self.store.read()["counters"]["n"]
        body = "x" * (COLD_BUNDLE_BYTES if realistic else 200)
        texts = {k: f"id: T-{k:05d}\npayload: {body}\n" for k in range(k0 + 1, k0 + count + 1)}
        shas = {} if realistic else {k: prewrite(self.root, bundle_rel(f"T-{k:05d}"), text)
                                     for k, text in texts.items()}
        with self.store.session() as s:
            items = []
            for k, text in texts.items():
                rel = bundle_rel(f"T-{k:05d}")
                if realistic:
                    sha = self.history.write_record(s, rel, text)
                else:
                    s.prewritten(rel, shas[k])
                    sha = shas[k]
                items.append(self.fields(k, sha))
            root = self.history.append(s, self.current(), items)
            s.write(COLD_ROOT_REL, dump_yaml(root), immutable=False)
            s.state["counters"]["n"] = k0 + count
            s.commit(Transition(op="history.archive", actor={"kind": "perf"}))

    def fill_tail(self, occupancy: int) -> None:
        """Archive (small bundles, in batches) until the tail holds ``occupancy`` entries."""
        from aew.history import manifest as M

        need = (occupancy - self.current()["count"]) % M.SEGMENT_SIZE
        while need:
            batch = min(need, 2000)
            self.archive(batch, realistic=False)
            need -= batch


def timed(fn: Any) -> tuple[float, Any]:
    t0 = time.perf_counter()
    out = fn()
    return time.perf_counter() - t0, out


def coldwrite(records: list[int], work: Path, reps: int) -> list[dict[str, Any]]:
    """ADR-0011's cold-write series. At each size, with the tail at a fixed occupancy so that sizes compare:
    three archivals (tail 254 -> 255, the append that seals, and the first into an empty tail), incremental
    verification and index catch-up over exactly those, and exact lookups. Full verification and an index rebuild
    are recorded too: they are linear in history by design and never on a command's path."""
    import random

    from aew.history import manifest as M

    results = []
    for n in records:
        cs = ColdStore(work / f"cold-{n}" / ".aew")
        t0 = time.perf_counter()
        while cs.current()["count"] < n:
            cs.archive(min(2000, n - cs.current()["count"]), realistic=False)
        build_s = time.perf_counter() - t0
        rebuild_s, _ = timed(lambda: cs.index.sync(cs.current()))
        samples: dict[str, list[float]] = {k: [] for k in ("append_tail_254", "append_seal", "append_tail_0",
                                                            "verify_incremental", "index_catch_up")}
        tail_bytes = 0
        for _ in range(reps):
            cs.fill_tail(M.SEGMENT_SIZE - 2)
            tail_bytes = (cs.root / M.TAIL_REL).stat().st_size  # the tail the measured appends rewrite
            before = cs.current()
            cs.index.sync(before)  # the setup records are not part of the timed catch-up
            for key in ("append_tail_254", "append_seal", "append_tail_0"):
                samples[key].append(timed(lambda: cs.archive(1, realistic=True))[0])
            after = cs.current()
            report = cs.history.verify(after, {"count": before["count"], "h": before["head_h"]})
            samples["verify_incremental"].append(timed(
                lambda: cs.history.verify(after, {"count": before["count"], "h": before["head_h"]}))[0])
            assert report.ok and report.entries == 3, report.problems
            catch_up_s, caught = timed(lambda: cs.index.sync(after))
            assert caught == {"mode": "caught_up", "added": 3}, caught  # exactly the three measured archivals
            samples["index_catch_up"].append(catch_up_s)
        root = cs.current()
        rng = random.Random(n)
        ids = [f"T-{rng.randint(1, root['count']):05d}" for _ in range(50)]
        seqs = [rng.randint(1, root["count"]) for _ in range(50)]
        lookup = [timed(lambda i=i: cs.index.by_id(i))[0] for i in ids]
        entry = [timed(lambda s=s: cs.history.entry(root, s))[0] for s in seqs]
        full_s, full = timed(lambda: cs.history.verify(root))
        assert full.ok, full.problems[:3]
        out = {"records": root["count"], "segments": root["sealed_head"]["seq"] if root["sealed_head"] else 0,
               "build_s": round(build_s, 1), "tail_bytes_at_254": tail_bytes,
               **{f"{k}_s": round(statistics.median(v), 4) for k, v in samples.items()},
               "lookup_by_id_s": round(statistics.median(lookup), 5),
               "entry_by_seq_s": round(statistics.median(entry), 5),
               "verify_full_s": round(full_s, 2), "index_rebuild_s": round(rebuild_s, 2)}
        print(json.dumps(out), flush=True)
        results.append(out)
    return results


def cold_table(results: list[dict[str, Any]]) -> str:
    rows = [("one archival, tail 254", "append_tail_254_s"), ("one archival that seals", "append_seal_s"),
            ("one archival, empty tail", "append_tail_0_s"), ("incremental verify (3)", "verify_incremental_s"),
            ("index catch-up (3)", "index_catch_up_s"), ("lookup by id (index)", "lookup_by_id_s"),
            ("entry by seq (files)", "entry_by_seq_s"), ("full verify (linear)", "verify_full_s"),
            ("index rebuild (linear)", "index_rebuild_s")]
    head = "| | " + " | ".join(f"{r['records']:,} records" for r in results) + " |"
    lines = [head, "|---" * (len(results) + 1) + "|"]
    for label, key in rows:
        lines.append(f"| {label} | " + " | ".join(f"{r[key] * 1000:.1f} ms" for r in results) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- output

def table(results: list[dict[str, Any]]) -> str:
    sizes = [r["project"] for r in results]
    head = "| Command | " + " | ".join(f"{s['units']} units ({s['control_bytes'] / 1e6:.1f} MB)" for s in sizes) + " |"
    lines = [head, "|---" * (len(sizes) + 1) + "|"]
    for i, row in enumerate(results[0]["ops"]):
        cells = []
        for r in results:
            op = r["ops"][i]
            top = sorted(((k, v) for k, v in op["phases_s"].items()), key=lambda kv: -kv[1])[:2]
            cells.append(f"{op['wall_s']:.2f} s ({', '.join(f'{k} {v:.2f}' for k, v in top)})")
        lines.append(f"| {row['op']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def sweep_points(spec: str) -> list[tuple[int, int]]:
    """``open:completed,...``, measured in order, each on a project of its own (built, then migrated)."""
    return [(int(a), int(b)) for a, b in (p.split(":") for p in spec.split(","))]


def sweep(points: list[tuple[int, int]], work: Path, reps: int, *, hierarchy: bool = False) -> list[dict[str, Any]]:
    """With ``hierarchy``, ``open`` counts the open Tickets below the Story; the Story and Epic are open as well."""
    results: list[dict[str, Any]] = []
    for n, (want_open, want_done) in enumerate(points):
        # Each point is built in the M3 (v1) layout and migrated (ADR-0011), so it is a project of its own: 3 open
        # Tickets (T-0002..T-0004) and 1 completed (T-0001) to start; in a hierarchy, all below one Story and Epic.
        t = make_template(work / f"sweep-{n}" / "repo", hierarchy=hierarchy)
        t0 = time.perf_counter()
        add_units(t.root, done=max(want_done - 1, 0), planned=max(want_open - 3, 0))
        info = {**validate(t.root), "build_s": round(time.perf_counter() - t0, 1)}
        fp_v1 = project_footprint(t.root)
        migration = migrate(t)
        print(f"point open={fp_v1['units']['open']} completed={fp_v1['units']['completed']} {info} {migration}",
              flush=True)
        results.append({"point": {"open": fp_v1["units"]["open"], "completed": fp_v1["units"]["completed"]},
                        "shape": "hierarchy" if hierarchy else "flat",
                        "project": info, "footprint_v1": fp_v1, "migration": migration,
                        "footprint": project_footprint(t.root), "micro": micro(t.root),
                        "ops": measure(t, reps)})
    return results


def ab(points: list[tuple[int, int]], work: Path, rounds: int) -> dict[str, Any]:
    """H2 paired: build and migrate one project per point, then measure them in turns, one sample each per round, so
    that a change in the machine's speed during the run reaches every point alike (P3). Each op's median per point,
    and its median paired difference from the first point."""
    projects = []
    for n, (want_open, want_done) in enumerate(points):
        t = make_template(work / f"ab-{n}" / "repo")
        add_units(t.root, done=max(want_done - 1, 0), planned=max(want_open - 3, 0))
        migrate(t)
        projects.append(t)
        print(f"built {want_open}:{want_done}", flush=True)
    walls: list[list[dict[str, float]]] = [[] for _ in points]
    for r in range(rounds):
        for i, t in enumerate(projects if r % 2 == 0 else list(reversed(projects))):
            k = i if r % 2 == 0 else len(projects) - 1 - i
            walls[k].append({o["op"]: o["wall_s"] for o in measure(t, 1)})
    ops = list(walls[0][0])
    out: dict[str, Any] = {"points": [{"open": o, "completed": d} for o, d in points], "rounds": rounds, "ops": {}}
    for op in ops:
        per = [[w[op] for w in walls[i]] for i in range(len(points))]
        out["ops"][op] = {"median_s": [round(statistics.median(x), 4) for x in per],
                          "paired_delta_s": [round(statistics.median(b - a for a, b in zip(per[0], x, strict=True)), 4)
                                             for x in per[1:]],
                          "samples_s": [[round(v, 4) for v in x] for x in per]}
    return out


def sweep_table(results: list[dict[str, Any]]) -> str:
    head = "| Command | " + " | ".join(f"{r['point']['open']} open, {r['point']['completed']} completed"
                                       for r in results) + " |"
    lines = [head, "|---" * (len(results) + 1) + "|",
             "| control.yaml | " + " | ".join(f"{r['footprint']['control_bytes'] / 1e6:.2f} MB" for r in results)
             + " |",
             "| live part (ADR-0011) | " + " | ".join(f"{r['footprint']['live_bytes'] / 1e3:.0f} KB" for r in results)
             + " |",
             "| aew migrate | " + " | ".join(f"{r['migration']['migrate_s']:.2f} s" for r in results) + " |"]
    for i, row in enumerate(results[0]["ops"]):
        lines.append(f"| {row['op']} | " + " | ".join(f"{r['ops'][i]['wall_s']:.2f} s" for r in results) + " |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--units", type=int, required=True)
    b.add_argument("--out", type=Path, required=True)
    r = sub.add_parser("run")
    r.add_argument("--sizes", default="50,500,3000")
    r.add_argument("--work", type=Path, required=True)
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--json", type=Path)
    s = sub.add_parser("sweep")
    s.add_argument("--points", default="20:250,20:1000,20:3000,200:250")
    s.add_argument("--hierarchy", action="store_true",
                   help="ADR-0011 hierarchy-history series: every Ticket below one open Story and Epic")
    s.add_argument("--work", type=Path, required=True)
    s.add_argument("--reps", type=int, default=3)
    s.add_argument("--json", type=Path)
    f = sub.add_parser("footprint")
    f.add_argument("project", type=Path)
    a = sub.add_parser("ab", help="H2 paired: measure sweep points in turns, so machine drift reaches all alike")
    a.add_argument("--points", default="20:250,20:3000")
    a.add_argument("--rounds", type=int, default=6)
    a.add_argument("--work", type=Path, required=True)
    a.add_argument("--json", type=Path)
    c = sub.add_parser("coldwrite", help="ADR-0011 cold-write series: synthetic cold stores of these sizes")
    c.add_argument("--records", default="1000,3000,10000,30000")
    c.add_argument("--work", type=Path, required=True)
    c.add_argument("--reps", type=int, default=3)
    c.add_argument("--json", type=Path)
    args = ap.parse_args()
    if args.cmd == "coldwrite":
        cold = coldwrite([int(x) for x in args.records.split(",")], args.work, args.reps)
        print(cold_table(cold))
        if args.json:
            args.json.write_text(json.dumps(cold, indent=1), encoding="utf-8")
        return 0
    if args.cmd == "ab":
        paired = ab(sweep_points(args.points), args.work, args.rounds)
        for op, v in paired["ops"].items():
            print(f"{op}: medians {v['median_s']}, paired delta {v['paired_delta_s']}")
        if args.json:
            args.json.write_text(json.dumps(paired, indent=1), encoding="utf-8")
        return 0
    if args.cmd == "build":
        build(args.out, args.units)
        print(json.dumps(validate(args.out), indent=1))
        return 0
    if args.cmd == "footprint":
        print(json.dumps(project_footprint(args.project), indent=1))
        return 0
    if args.cmd == "sweep":
        swept = sweep(sweep_points(args.points), args.work, args.reps, hierarchy=args.hierarchy)
        print(sweep_table(swept))
        if args.json:
            args.json.write_text(json.dumps(swept, indent=1), encoding="utf-8")
        return 0
    results = []
    for n in (int(x) for x in args.sizes.split(",")):
        root = args.work / f"units-{n}" / "repo"
        t0 = time.perf_counter()
        t = build(root, n)
        info = {**validate(root), "build_s": round(time.perf_counter() - t0, 1)}
        fp_v1 = project_footprint(root)
        migration = migrate(t)
        print(f"built {info} {migration}", flush=True)
        results.append({"project": info, "footprint_v1": fp_v1, "migration": migration,
                        "footprint": project_footprint(root), "micro": micro(root),
                        "ops": measure(t, args.reps if n < 3000 else 1)})
        print(json.dumps(results[-1]["micro"]), flush=True)
    print(table(results))
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
