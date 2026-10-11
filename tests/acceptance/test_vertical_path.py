"""The vertical UAT (v1): a fresh project and a normal operator session, from setup to a published one-line fix.

docs/implementation/vertical-uat.md states what it proves, its actors, its scenarios (V1 to V4), the burden ledger and
the hard limits. **It is expected to fail on today's main**: its first job is to measure by how much. Every scenario
goes to the end and writes its ledger (``vertical-ledger.json`` and a one-screen summary) whatever it finds, then
asserts. Nothing here is xfailed, skipped or softened; the job is in shadow (``VERTICAL_MODE``), outside the merge
gate, until the operator flips it.

The actors are all scripted and offline: the operator (``vertical/scripted_operator.py``: only what a human types),
the Lead (``vertical/lead.py``: no AEW knowledge, inside the fake OpenCode TUI that the real ``aew opencode`` starts,
talking to the real broker over MCP), and the workers (``vertical/workers.py``: the fake harness making a real fix
checked by a real ``python -m pytest``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from conftest import git
from vertical import workers
from vertical.ledger import HELD, NOT_REFUSED, UNNAMED, V1_DECISIONS, Ledger
from vertical.scripted_operator import (
    Operator,
    containment,
    execution_policy,
    lead_events,
    lead_spec,
    new_world,
)
from vertical.chat import Mailbox

pytestmark = pytest.mark.acceptance("VUAT")

OUT_ENV = "AEW_VERTICAL_OUT"  # where the ledgers go (CI uploads them); default: the test's own tmp_path
EXISTS, PROPOSED = "exists", "PROPOSED"

# The ideal path: what a user would ideally type at each step. Names that do not exist yet are PROPOSED; the plan for
# the vertical-path shifts amends this table, nobody else. Each step is attempted as written first; a fallback to
# today's workaround fires only after that attempt is observed to fail, and is recorded with its evidence.
IDEAL_PATH: dict[str, dict[str, str]] = {
    "init": {"input": "aew init", "status": EXISTS,
             "ideal": "initializes the project; confers no authority"},
    "configure": {"input": 'aew settings set checks.unit.command "python -m pytest -q tests"', "status": PROPOSED,
                  "ideal": "one command that validates and saves a setting; saving is the adoption"},
    "open": {"input": "aew opencode", "status": EXISTS,
             "ideal": "opens the Lead session, runs preflight and authenticates the operator once (PROPOSED "
                      "behaviour): no credential, no variable, no seat to manage"},
    "ask": {"input": workers.REQUEST, "status": EXISTS, "ideal": "a chat line to the Lead"},
    "decide": {"input": "yes", "status": EXISTS,
               "ideal": "answers only real judgements: the plan, and the publish (unless a grant covers it)"},
    "exit": {"input": "/exit", "status": EXISTS, "ideal": "ends the Lead session; work in flight is untouched"},
    "reopen": {"input": "aew opencode", "status": EXISTS,
               "ideal": "resumes without a takeover or a credential, and says where things stand in words "
                        "(PROPOSED behaviour)"},
    "preflight": {"input": "aew preflight", "status": PROPOSED,
                  "ideal": "readiness: fails before any Ticket exists, naming the cause and the fix"},
    "change_model": {"input": "aew settings set execution.profiles.standard.model cheaper-model", "status": PROPOSED,
                     "ideal": "one operator action that validates and saves; no raw YAML, no adopt, no restart"},
}


# ---------------------------------------------------------------------------------------------- the operator's steps


def ideal_argv(step: str) -> list[str]:
    import shlex

    return shlex.split(IDEAL_PATH[step]["input"])[1:]


def configure(op: Operator, *, steering: str | None = None) -> None:
    """Setup: the check command and the harness, the ideal way first."""
    res = op.type("configure", ideal_argv("configure"))
    if res.returncode == 0:
        return
    instead = "edit .aew/policy/checks.yaml and execution.yaml, aew lead acquire, aew manifest adopt (quickstart)"
    op.fallback("configure", IDEAL_PATH["configure"]["input"], res.stderr or res.stdout, instead)

    def checks(doc: dict[str, Any]) -> None:
        doc.update({"schema": "aew/checks/v1", "baseline_failures": [],
                    "checks": {"unit": {"configured": True, "command": workers.UNIT, "cwd": ".", "timeout_s": 300,
                                        "description": "the project's tests"}}})

    op.edit_policy("configure", "checks.yaml", checks)
    op.edit_policy("configure", "execution.yaml",
                   lambda doc: (doc.clear(), doc.update(execution_policy(op.lab, steering=steering))))
    acquired = op.type("configure:acquire", ["lead", "acquire", "--expect-rev", "0", "--session-label", "operator"])
    assert acquired.returncode == 0, acquired.stderr
    op.credential = acquired.json["token"]
    op.lab.project.token = op.credential
    op.adopt("configure:adopt", "configured the test command and the harness")


def open_session(op: Operator, step: str, *, steering: bool = False):
    """``aew opencode``, the ideal way first; today's fallback is the credential in AEW_LEAD_TOKEN (quickstart)."""
    spec = lead_spec(op.lab, steering=steering)
    session = op.open_session(step, ideal_argv("open"), spec)
    first = op.first_words(session)
    if first is not None:
        return session, first
    op.fallback(step, IDEAL_PATH["open"]["input"], session.output(), "export AEW_LEAD_TOKEN=<credential>; aew opencode")
    if op.shell_env.get("AEW_LEAD_TOKEN") != op.credential:
        op.export(step, "AEW_LEAD_TOKEN", op.credential)
    session = op.open_session(step, ideal_argv("open"), lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    assert first is not None, f"the Lead session did not start: {session.output()[-2000:]}"
    return session, first


def setup_operator(tmp_path: Path, scenario: str, *, steering: bool = False, **world: Any) -> Operator:
    lab = new_world(tmp_path, **world)
    ledger = Ledger(scenario, steering=steering)
    op = Operator(lab, ledger, tmp_path, Mailbox(tmp_path / "sync" / "chat", "operator"))
    op.allowed_heads.add(git("rev-parse", "main", cwd=lab.root))
    res = op.type("init", ideal_argv("init"))
    assert res.returncode == 0, res.stderr
    return op


def merge_lead(op: Operator) -> None:
    for e in lead_events(op.lab):
        op.ledger.lead_event(e)


def write_out(op: Operator, request: pytest.FixtureRequest) -> Path:
    base = Path(os.environ.get(OUT_ENV) or op.tmp / "vertical-out")
    name = request.node.name.replace("[", "-").replace("]", "").replace("/", "-")
    out = base / name
    op.ledger.observe("transcript", operator=op.transcript)
    op.ledger.write(out)
    print("\n" + op.ledger.summary())
    return out


def result_problems(op: Operator) -> list[str]:
    """The operator gets the result: the diff, an evidence summary, and the commit."""
    if not op.reports:
        stuck = [m for m in op.said if m.get("type") == "stuck"]
        return [f"no result reached the operator{': ' + stuck[-1]['text'] if stuck else ''}"]
    r = op.reports[-1]
    problems = []
    if r.get("state") != "DONE":
        problems.append(f"the result's state is {r.get('state')}")
    if not r.get("commit") or git("rev-parse", "main", cwd=op.root) != r.get("commit"):
        problems.append("the result names no published commit on main")
    if "ledger/money.py" not in str(r.get("diff")):
        problems.append("the result carries no diff of the fix")
    if not r.get("evidence"):
        problems.append("the result carries no evidence summary")
    return problems


def verdict(op: Operator, *, decisions: tuple[str, ...] | None = V1_DECISIONS,
            limits: tuple[str, ...] = ("publish_needs_decision", "containment")) -> list[str]:
    problems = [f"{k} = {n} (must be 0)" for k, n in op.ledger.over().items()]
    labels = tuple(d["label"] for d in op.ledger.decisions)
    if decisions is not None and labels != decisions:
        problems.append(f"operator decisions {list(labels)} (must be exactly {list(decisions)})")
    for name in limits:
        found = op.ledger.hard_limits.get(name)
        if found is None:
            problems.append(f"hard limit {name}: not observed")
        elif found["outcome"] != HELD:
            problems.append(f"hard limit {name}: {found['outcome']}")
    return problems


def finish(op: Operator, session) -> None:
    op.end_session(session, "exit")
    merge_lead(op)
    containment(op.lab, op.ledger)
    if "publish_needs_decision" not in op.ledger.hard_limits:
        op.check_heads("at the end")
        op.ledger.hard_limits.setdefault("publish_needs_decision", {"outcome": HELD})


@pytest.fixture
def world(tmp_path):
    made: list[Operator] = []
    yield made
    for op in made:
        op.lab.cleanup()


# ---------------------------------------------------------------------------------------------- V1


def test_v1_fresh_path_reaches_a_published_fix_with_no_machinery(tmp_path, world, request):
    op = setup_operator(tmp_path, "V1")
    world.append(op)
    try:
        configure(op)
        op.in_setup = False
        session, _ = open_session(op, "open")
        op.say("ask", workers.REQUEST)
        op.converse(session)
        finish(op, session)
    finally:
        write_out(op, request)
    problems = verdict(op) + result_problems(op)
    assert not problems, "\n".join(problems) + "\n\n" + op.ledger.summary()


__all__ = ["NOT_REFUSED", "UNNAMED"]
