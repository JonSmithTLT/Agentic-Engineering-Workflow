"""Scripted, deterministic role drivers for acceptance tests.

Each role acts only through the CLI with its own invocation credential and from
inside the Ticket workspace, the same way an LLM subagent launched from a
generated launch contract would. Nothing here reaches into engine internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conftest import Project, make_git_repo, run_aew

from aew.util import dump_yaml, glob_any

SAMPLE_FILES = {
    ".gitignore": "__pycache__/\n.pytest_cache/\n*.pyc\n",
    "README.md": "# calc\n\nA tiny calculator used as the AEW acceptance fixture.\n",
    "calc/__init__.py": "from calc.core import add\n",
    "calc/core.py": "def add(a, b):\n    return a + b\n",
    "tests/test_core.py": "from calc.core import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    "vendor/lib.py": "VENDORED = True\n",
}

SUBTRACT_PATCH = {
    "calc/core.py": "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
    "tests/test_subtract.py": ("from calc.core import subtract\n\n\n"
                               "def test_subtract():\n    assert subtract(5, 3) == 2\n"),
}


APPLY_PATCH = {
    "calc/core.py": SUBTRACT_PATCH["calc/core.py"] + "\n\ndef apply(op, a, b):\n    return op(a, b)\n",
    "tests/test_apply.py": "from calc.core import apply, subtract\n\n\ndef test_apply():\n"
                           "    assert apply(subtract, 5, 3) == 2\n",
}

def unit_check_command() -> list[str]:
    return ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"]


def sample_project(tmp_path: Path, *, guardrails: dict[str, Any] | None = None,
                   checks: dict[str, Any] | None = None, gates: dict[str, Any] | None = None) -> Project:
    repo = make_git_repo(tmp_path / "repo", SAMPLE_FILES)
    p = Project(repo)
    p.ok("init", "--project-id", "calc")
    policy = repo / ".aew/policy"
    (policy / "checks.yaml").write_text(dump_yaml(checks or {
        "schema": "aew/checks/v1",
        "checks": {"unit": {"configured": True, "command": unit_check_command(), "cwd": ".", "timeout_s": 300,
                            "description": "focused pytest run"}},
        "baseline_failures": [],
    }), encoding="utf-8", newline="\n")
    (policy / "guardrails.yaml").write_text(dump_yaml(guardrails or {
        "schema": "aew/guardrails/v1", "protected_paths": ["vendor/**"], "generated_paths": [],
        "ticket_scope_enforcement": True, "review_triggers": [], "dependency_rules": [],
    }), encoding="utf-8", newline="\n")
    if gates:
        (policy / "gates.yaml").write_text(dump_yaml(gates), encoding="utf-8", newline="\n")
    p.token = p.ok("lead", "acquire", "--expect-rev", "0", "--session-label", "lead-a")["token"]
    return p


@dataclass
class Role:
    project: Project
    token: str
    workspace: Path

    def aew(self, *args: str):
        return run_aew("-C", str(self.workspace), *args, env={"AEW_INVOCATION_TOKEN": self.token})

    def ok(self, *args: str) -> Any:
        res = self.aew(*args)
        assert res.returncode == 0, f"role aew {' '.join(args)} failed: {res.stderr or res.stdout}"
        return res.json

    def check(self, check_id: str) -> dict[str, Any]:
        return self.ok("check", "run", check_id)

    def submit(self, kind: str, meta: dict[str, Any], body: str = "", *, expect_ok: bool = True):
        path = self.workspace.parent / f"submission-{kind}-{abs(hash(dump_yaml(meta))) % 10**8}.md"
        path.write_text(f"---\n{dump_yaml(meta)}---\n{body}", encoding="utf-8", newline="\n")
        res = self.aew("submit", "--kind", kind, "--file", str(path))
        if expect_ok:
            assert res.returncode == 0, f"submit {kind} failed: {res.stderr}"
            return res.json
        return res

    def write(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            target = self.workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")


# A Class 0 Ticket is created eligible (the Class 0 Workflow Contract amendment, enforced at dispatch since M4-A): a
# deterministic acceptance check and the Lead's three recorded assertions (the goal and the bounded scope are below).
CLASS0_ELIGIBLE = ("--acceptance-check", "unit", "--class0-assert", "transformation_clear",
                   "--class0-assert", "inputs_complete", "--class0-assert", "no_consequential_boundary")


def create_planned_ticket(p: Project, tmp_path: Path, *, title: str = "Add subtract()", cls: int = 1,
                          scope: tuple[str, ...] = ("calc/**", "tests/**"), extra: tuple[str, ...] = ()) -> str:
    args = ["work", "create", "ticket", "--title", title, "--class", str(cls),
            "--goal", "calc.core.subtract(5, 3) == 2 through the public module",
            "--contract", "changes stay within calc/ and tests/; vendored code untouched",
            *(CLASS0_ELIGIBLE if cls == 0 else ()), *extra]
    for s in scope:
        args += ["--scope", s]
    wid = p.lead(*args)["id"]
    plan = tmp_path / f"{wid}-plan.md"
    plan.write_text("1. Add subtract(a, b) to calc/core.py.\n2. Add a focused test.\n", encoding="utf-8")
    # The plan names a path inside the Ticket's scope (plan lint, M4-A).
    affected = "calc/core.py" if not scope or glob_any("calc/core.py", list(scope)) else scope[0]
    p.lead("plan", "propose", "--assurance", "none", wid, "--file", str(plan), "--affected", affected)
    p.lead("plan", "accept", wid, "--revision", "1")
    return wid


def assign(p: Project, wid: str) -> Role:
    out = p.lead("work", "assign", wid)
    p.lead("work", "transition", wid, "--to", "RUNNING")
    return Role(p, out["invocation_token"], Path(out["workspace"]["path"]))


def redispatch_implementer(p: Project, wid: str) -> Role:
    """Work returned to RUNNING: the Lead dispatches a fresh bounded implementer (WC §5)."""
    out = p.lead("invoke", "create", wid, "--role", "implementer")
    return Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))


def implement(impl: Role, files: dict[str, str] | None = None) -> None:
    impl.write(files if files is not None else SUBTRACT_PATCH)
    assert impl.check("unit")["result"] == "pass"
    impl.submit("implementation_report", {
        "claim": "subtract implemented with a focused test",
        "result": "pass",
        "producer": {"model": "scripted", "harness": "pytest"},
        "implementation": {"files_changed": sorted((files or SUBTRACT_PATCH).keys()), "checks_run": ["unit"],
                           "deviations": [], "self_review": {"completed": True, "notes": "diff matches plan"}},
    }, "Implemented per plan v1.\n")


def review(p: Project, wid: str, *, disposition: str = "pass", findings: list[dict] | None = None,
           resolved: list[str] | None = None, specialty: str | None = None, card: str | None = None) -> str:
    if specialty and not card:
        card = {"security": "security_reviewer"}[specialty]
    args = ["invoke", "create", wid] + (["--card", card] if card else ["--role", "reviewer"])
    out = p.lead(*args)
    rev = Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))
    meta = {"claim": "independent review of the change against plan and contracts",
            "producer": {"model": "scripted-reviewer"},
            "review": {"independence": "R1", "disposition": disposition, "findings": findings or [],
                       "resolved_findings": resolved or []}}
    return rev.submit("review", meta, "Reviewed the diff and check output.\n")["evidence"]


def verify(p: Project, wid: str, *, scope: str = "ticket", goal_result: str = "pass",
           contract_result: str = "pass", card: str | None = None) -> str:
    args = ["invoke", "create", wid] + (["--card", card] if card else ["--role", "verifier"])
    if scope == "integration":
        args += ["--scope", "integration"]
    out = p.lead(*args)
    control = p.ok("work", "show", wid)["control"]
    ws = control["integration"]["workspace"] if scope == "integration" else control["workspace"]["path"]
    ver = Role(p, out["invocation_token"], Path(ws))
    unit_ev = ver.check("unit")["evidence"]
    claims = [{"type": "goal_backwards", "claim": "subtract(5, 3) == 2 observed via tests", "result": goal_result,
               "checks": [unit_ev]}]
    if scope == "ticket":
        guard_ev = ver.check("guardrails")["evidence"]
        claims.append({"type": "contract", "claim": "guardrails and scope respected", "result": contract_result,
                       "checks": [guard_ev]})
    return ver.submit("verification", {
        "claim": "requested behavior exists in the evaluated snapshot",
        "producer": {"model": "scripted-verifier"},
        "verification": {"scope": scope, "claims": claims},
    }, "Goal-backwards: ran the focused tests. Contract: guardrail check.\n")["evidence"]


def prepare_and_validate(p: Project, wid: str) -> dict[str, Any]:
    """COMMIT_READY -> integration candidate -> post-integration verification (not yet published)."""
    out = p.lead("integrate", "prepare", wid)
    assert out["ok"], out
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid, scope="integration"))
    integ = p.ok("work", "show", wid)["control"]["integration"]
    assert integ["status"] == "validated", integ
    return integ


def integrate(p: Project, wid: str) -> dict[str, Any]:
    integ = prepare_and_validate(p, wid)
    out = p.lead("integrate", "publish", wid)
    assert out["state"] == "DONE" and out["integrated_commit"] == integ["candidate"]
    return out


def to_commit_ready(p: Project, tmp_path: Path, **kw: Any) -> tuple[str, Role]:
    wid, impl = to_verified(p, tmp_path, **kw)
    p.lead("work", "transition", wid, "--to", "COMMIT_READY")
    return wid, impl


def to_verified(p: Project, tmp_path: Path, *, files: dict[str, str] | None = None,
                wid: str | None = None, **kw: Any) -> tuple[str, Role]:
    wid = wid or create_planned_ticket(p, tmp_path, **kw)
    impl = assign(p, wid)
    implement(impl, files)
    p.lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    p.lead("review", "ingest", wid, "--evidence", review(p, wid))
    p.lead("work", "transition", wid, "--to", "VERIFY_PENDING")
    p.lead("verify", "ingest", wid, "--evidence", verify(p, wid))
    assert p.ok("work", "show", wid)["control"]["state"] == "VERIFIED"
    return wid, impl



# ------------------------------------------------------------------ M2: hierarchy and non-mutating roles


def plan_unit(p: Project, tmp_path: Path, wid: str, text: str = "Plan.\n", reason: str | None = None) -> int:
    """Propose and accept the next plan revision of any unit (Ticket, Story or Epic)."""
    f = tmp_path / f"{wid}-plan-{len(p.ok('work', 'show', wid)['control']['plans']) + 1}.md"
    f.write_text(text, encoding="utf-8")
    args = ["plan", "propose", "--assurance", "none", wid, "--file", str(f)] + (["--reason", reason] if reason else [])
    rev = p.lead(*args)["revision_number"]
    p.lead("plan", "accept", wid, "--revision", str(rev))
    return rev


def create_unit(p: Project, kind: str, title: str, *, cls: int = 1, parent: str | None = None,
                extra: tuple[str, ...] = ()) -> str:
    args = ["work", "create", kind, "--title", title, "--class", str(cls), *extra]
    if parent:
        args += ["--parent", parent]
    return p.lead(*args)["id"]


def create_investigation(p: Project, tmp_path: Path, *, title: str = "Investigate calc.core",
                         parent: str | None = None, cls: int = 1, card: str | None = None,
                         extra: tuple[str, ...] = ()) -> str:
    more = ("--non-mutating", "--goal", "current behavior of calc.core is documented", "--scope", "calc/**", *extra)
    if card:
        more += ("--card", card)
    wid = create_unit(p, "ticket", title, cls=cls, parent=parent, extra=more)
    plan_unit(p, tmp_path, wid, "Read calc/core.py and its tests; record facts and open questions.\n")
    return wid


def dispatch(p: Project, wid: str, card: str | None = None) -> tuple[Role, dict[str, Any]]:
    """work dispatch -> RUNNING; returns the executor Role (it works in its read-only observation)."""
    out = p.lead("work", "dispatch", wid, *(["--card", card] if card else []))
    p.lead("work", "transition", wid, "--to", "RUNNING")
    return Role(p, out["invocation_token"], Path(out["observation"]["path"])), out


DISCOVERY = {"claim": "calc.core defines add(a, b)", "result": "pass",
             "producer": {"model": "scripted-investigator"},
             "discovery": {"question": "what does calc.core provide?",
                           "facts": [{"statement": "calc/core.py defines add(a, b)", "evidence": ["calc/core.py:1"]}],
                           "hypotheses": [{"statement": "no subtraction exists yet", "confirm_by": "grep subtract"}],
                           "unresolved_questions": [], "observed_paths": ["calc/**"]}}
RESEARCH = {"claim": "pytest supports plain assert", "result": "pass", "producer": {"model": "scripted-researcher"},
            "research": {"question": "can tests use plain assert?", "conclusions": ["pytest rewrites plain asserts"],
                         "subjects": [{"name": "pytest", "version": "8", "source": "docs.pytest.org"}],
                         "constraints": [], "uncertainties": []}}
PROPOSAL = {"claim": "add subtract() with a focused test", "result": "pass", "producer": {"model": "scripted-planner"},
            "proposal": {"objective": "subtract(5, 3) == 2", "approach": "add subtract to calc/core.py",
                         "ordered_tasks": ["add subtract", "add test"], "required_tests": ["tests/test_subtract.py"],
                         "affected_paths": ["calc/**", "tests/**"]}}


def submit_record(role: Role, kind: str, meta: dict[str, Any] | None = None, body: str = "Findings.\n",
                  *, expect_ok: bool = True):
    meta = meta if meta is not None else {"discovery_record": DISCOVERY, "research_record": RESEARCH,
                                          "plan_proposal": PROPOSAL}[kind]
    return role.submit(kind, meta, body, expect_ok=expect_ok)


def complete_investigation(p: Project, wid: str, *, kind: str = "discovery_record", card: str | None = None) -> str:
    """dispatch -> submit -> ingest -> accept; returns the accepted record id."""
    role, _ = dispatch(p, wid, card)
    rec = submit_record(role, kind)["evidence"]
    p.lead("evidence", "ingest", wid, "--evidence", rec)
    p.lead("work", "accept", wid)
    return rec


def parent_review(p: Project, wid: str, *, disposition: str = "pass", findings: list[dict] | None = None) -> str:
    out = p.lead("invoke", "create", wid, "--role", "reviewer")
    rev = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    return rev.submit("review", {"claim": f"{wid} acceptance review", "producer": {"model": "scripted-reviewer"},
                                 "review": {"independence": "R1", "disposition": disposition,
                                            "findings": findings or [], "resolved_findings": []}},
                      "Reviewed the children's integrated changes together.\n")["evidence"]


def parent_verify(p: Project, wid: str, *, result: str = "pass") -> str:
    out = p.lead("invoke", "create", wid, "--role", "verifier")
    ver = Role(p, out["invocation_token"], Path(out["observation"]["path"]))
    unit_ev = ver.check("unit")["evidence"]
    claims = [{"type": "goal_backwards", "claim": "the parent objective is met on the authoritative source",
               "result": result, "checks": [unit_ev]},
              {"type": "contract", "claim": "contracts hold", "result": "pass", "checks": [unit_ev]}]
    return ver.submit("verification", {"claim": f"{wid} acceptance", "producer": {"model": "scripted-verifier"},
                                       "verification": {"scope": "parent", "claims": claims}},
                      "Ran the suite on the authoritative source.\n")["evidence"]


def close_parent(p: Project, wid: str) -> str:
    """Parent review + verification (class >= 1 path), then closeout; returns the closeout decision. An Epic closes
    only once the history is audited through the current root (ADR-0011), so its closeout records that audit first."""
    p.lead("review", "ingest", wid, "--evidence", parent_review(p, wid))
    p.lead("verify", "ingest", wid, "--evidence", parent_verify(p, wid))
    if p.ok("work", "show", wid)["control"]["kind"] == "epic":
        p.ok("history", "audit", "--token", p.token, "--expect-rev", str(p.rev()))
    return p.lead("work", "close", wid, "--reason", "acceptance gates passed")["decision"]
