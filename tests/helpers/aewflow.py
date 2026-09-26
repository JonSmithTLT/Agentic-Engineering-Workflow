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

from aew.util import dump_yaml

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
    "tests/test_subtract.py": "from calc.core import subtract\n\n\ndef test_subtract():\n    assert subtract(5, 3) == 2\n",
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


def create_planned_ticket(p: Project, tmp_path: Path, *, title: str = "Add subtract()", cls: int = 1,
                          scope: tuple[str, ...] = ("calc/**", "tests/**"), extra: tuple[str, ...] = ()) -> str:
    args = ["work", "create", "ticket", "--title", title, "--class", str(cls),
            "--goal", "calc.core.subtract(5, 3) == 2 through the public module",
            "--contract", "changes stay within calc/ and tests/; vendored code untouched", *extra]
    for s in scope:
        args += ["--scope", s]
    wid = p.lead(*args)["id"]
    plan = tmp_path / f"{wid}-plan.md"
    plan.write_text("1. Add subtract(a, b) to calc/core.py.\n2. Add a focused test.\n", encoding="utf-8")
    p.lead("plan", "propose", wid, "--file", str(plan), "--affected", "calc/core.py")
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
           resolved: list[str] | None = None, specialty: str | None = None) -> str:
    args = ["invoke", "create", wid, "--role", "specialist" if specialty else "reviewer"]
    if specialty:
        args += ["--specialty", specialty]
    out = p.lead(*args)
    rev = Role(p, out["invocation_token"], Path(p.ok("work", "show", wid)["control"]["workspace"]["path"]))
    meta = {"claim": "independent review of the change against plan and contracts",
            "producer": {"model": "scripted-reviewer"},
            "review": {"independence": "R1", "disposition": disposition, "findings": findings or [],
                       "resolved_findings": resolved or []}}
    if specialty:
        meta["review"]["specialty"] = specialty
    return rev.submit("review", meta, "Reviewed the diff and check output.\n")["evidence"]


def verify(p: Project, wid: str, *, scope: str = "ticket", goal_result: str = "pass",
           contract_result: str = "pass") -> str:
    args = ["invoke", "create", wid, "--role", "verifier"]
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

