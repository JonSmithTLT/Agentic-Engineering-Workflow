"""The vertical UAT (spec v2): a fresh project and a normal operator session, from setup to a published one-line fix.

docs/implementation/vertical-uat.md states what it proves, its actors, its scenarios (V1 to V4), the burden ledger and
the hard limits. **It is expected to fail on today's main**: its first job is to measure by how much. Every scenario
goes to the end and writes its ledger (``vertical-ledger.json`` and a one-screen summary) whatever it finds, then
asserts. Nothing here is xfailed, skipped or softened; the job is in shadow (``VERTICAL_MODE``), outside the merge
gate, until the operator flips it. Windows is outside the enforced gate (the operator, Q1(e)): its job keeps running
and reporting, and every verdict it prints leads with its unqualified state and the conditions still open.

The path is V-01's acceptance oracle (``vertical/oracle.py``): row V01-01's 13 steps, each with its state derived from
the code's own registries and recorded in the ledger, and each scenario's PIN budget derived from its path (STG-13).
Each step the operator takes (every G3 step among them, `test_vertical_oracle.py` checks) goes through the oracle: while
it has not landed it is taken today's way and counted as a fallback with its derived state, and once it has landed
without a driver it is `no_driver`. The Lead's own steps (ask, work, result) are measured by the Lead's counters.

The actors are all scripted and offline: the operator (``vertical/scripted_operator.py``: only what a human types),
the Lead (``vertical/lead.py``: no AEW knowledge, inside the fake OpenCode TUI that the real ``aew opencode`` starts,
talking to the real broker over MCP), and the workers (``vertical/workers.py``: the fake harness making a real fix
checked by a real ``python -m pytest``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import git, run_aew
from notifier import recorder
from vertical import oracle, workers
from vertical.chat import Mailbox
from vertical.ledger import (
    HELD,
    NOT_EXERCISED,
    NOT_REFUSED,
    REBUILT,
    UNNAMED,
    V1_DECISIONS,
    Ledger,
    diagnoses,
    ledger_dir_name,
)
from vertical.scripted_operator import (
    Operator,
    containment,
    execution_policy,
    lead_events,
    lead_spec,
    new_world,
    stage_intents,
    staled_by,
)

from aew.harness import runlog

# G3 H1/H4: a failed scenario keeps an autopsy: the stacks, the processes, the Lead's TUI's own diagnostics (childdiag),
# and the parts of its world the helpers register (the chat, the Lead's events and state, the sessions' output), not
# its whole tmp_path (a project with its workspaces).
pytestmark = [pytest.mark.acceptance("VUAT"), pytest.mark.autopsy(tmp_path=False)]

OUT_ENV = "AEW_VERTICAL_OUT"  # where the ledgers go (CI uploads them); default: the test's own tmp_path


# ---------------------------------------------------------------------------------------------- the operator's steps


def configure(op: Operator, *, steering: bool = False, cause: str | None = None) -> None:
    """Setup's step 2 (configure), today's way while it has not landed: the check command and the harness in the
    policy files, then an acquire and an adopt (quickstart). ``cause`` puts a V3 cause into the operator's first
    configuration; ``steering`` adds what Run needs (a starting mode, a notifier, hard deadlines)."""
    op.workaround("configure", "edit .aew/policy/checks.yaml and execution.yaml, aew lead acquire, aew manifest adopt "
                               "(quickstart)")
    command = (["{python}", "-c", "open('check-output.txt', 'w').write('x')"] if cause == "check-changes-snapshot"
               else ["{python}", "-c", STAMP_CHECK] if cause == "stamp" else workers.UNIT)

    def checks(doc: dict[str, Any]) -> None:
        doc.update({"schema": "aew/checks/v1", "baseline_failures": [],
                    "checks": {"unit": {"configured": True, "command": command, "cwd": ".", "timeout_s": 300,
                                        "description": "the project's tests"}}})

    def execution(doc: dict[str, Any]) -> None:
        doc.clear()
        doc.update(execution_policy(op.lab, steering="crawl" if steering else None))
        if steering:
            doc["profiles"]["standard"]["deadline_s"] = 1800
            doc["notify"] = {"command": recorder(op.tmp)[0]}
        if cause == "provider-env-unset":
            doc["provider_env"] = ["VUAT_PROVIDER_KEY"]
        if cause in ("model-not-listed", "model-id-provider-prefix"):
            doc["harness"] = "opencode"
            doc["profiles"] = {"standard": {"provider": "vuatprov", "model": "vuat-missing-model"
                                            if cause == "model-not-listed" else "vuatprov/vuat-model"}}

    op.edit_policy("configure", "checks.yaml", checks)
    op.edit_policy("configure", "execution.yaml", execution)
    acquired = op.type("configure:acquire", ["lead", "acquire", "--expect-rev", "0", "--session-label", "operator"])
    assert acquired.returncode == 0, acquired.stderr
    op.credential = acquired.json["token"]
    op.lab.project.token = op.credential
    op.adopt("configure:adopt", "configured the test command and the harness")


def open_session(op: Operator, step: str, *, steering: bool = False):
    """Step 3 (open), or step 10 (reopen) from the same shell, today's way while it has not landed: the credential in
    AEW_LEAD_TOKEN, then ``aew opencode`` (quickstart). The operator's terminal is one shell: a variable exported
    earlier is still set."""
    op.workaround("reopen" if step == "reopen" else "open", "export AEW_LEAD_TOKEN=<credential>; aew opencode",
                  step=step)
    if op.shell_env.get("AEW_LEAD_TOKEN") != op.credential:
        op.export(step, "AEW_LEAD_TOKEN", op.credential)
    session = op.open_session(step, ["opencode"], lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    console_opened(op, step)
    assert first is not None, f"the Lead session did not start: {session.output()[-2000:]}"
    return session, first


def console_opened(op: Operator, step: str) -> None:
    """Whether opening AEW opened the operator console (spec v2): an endpoint is live for the project that the test
    did not start in-process. Recorded, never counted: the auto-opened console is not a step. A PIN it asks for is
    recorded by ``Ledger.pin_entered`` with the action it confirms (the PIN rule), once a confirmer exists to observe;
    nothing opens one today."""
    from aew.harness import operator_client

    found = operator_client.status(op.lab.aew_root)
    opened = bool(found.get("running")) and found.get("pid") != os.getpid()
    op.ledger.observe("open.console", step=step, auto_opened=opened,
                      endpoint={k: found.get(k) for k in ("pid", "started_at")} if opened else None)


def setup_operator(tmp_path: Path, scenario: str, *, steering: bool = False, also: tuple[str, ...] = (),
                   **world: Any) -> Operator:
    """A fresh world, and the ledger of ``scenario``'s path (its id's V1..V4; V1's for any other): each step's derived
    state, and the PIN budget the path gives (``also``: V3's open, when its path gets that far)."""
    lab = new_world(tmp_path, **world)
    steps = oracle.path(scenario[:2] if scenario[:2] in oracle.INHERITS else "V1", steering=steering, also=also)
    ledger = Ledger(scenario, steering=steering, pin_budget=oracle.pin_budget(steps))
    ledger.steps = oracle.derive(steps)
    chat = Mailbox(tmp_path / "sync" / "chat", "operator",
                   on_error=lambda path, exc: ledger.observe("chat_read_error", file=path.name,
                                                             error=f"{type(exc).__name__}: {exc}"[:300]))
    op = Operator(lab, ledger, tmp_path, chat)
    op.allowed_heads.add(git("rev-parse", "main", cwd=lab.root))
    res = op.type("init", ["init"])  # step 1, served by `aew init`
    assert res.returncode == 0, res.stderr
    return op


def merge_lead(op: Operator) -> None:
    for e in lead_events(op.lab):
        op.ledger.lead_event(e)


def write_out(op: Operator, request: pytest.FixtureRequest) -> Path:
    """Write the scenario's ledger. Called from the ``finally`` around its body: an exception escaping the body (the
    Lead did not start, setup raised) is in flight here, and makes the scenario not measured (STG-13, addendum 1)."""
    op.ledger.ended_by(sys.exc_info()[1])
    base = Path(os.environ.get(OUT_ENV) or op.tmp / "vertical-out")
    out = base / ledger_dir_name(request.node.name)
    op.ledger.observe("transcript", operator=op.transcript)
    op.ledger.write(out)
    print("\n" + op.ledger.summary())
    return out


def result_problems(op: Operator) -> list[str]:
    """The operator gets the result: the diff, an evidence summary, and the commit."""
    ended = [o for o in op.ledger.observations if o["kind"] in ("lead_silent", "lead.lead_error")]
    if not op.reports and ended:  # named with whose fault it is, as far as the evidence goes (review of #213, G2, H1)
        o = ended[0]
        what = (f"went silent waiting for {o.get('waiting_for')}" if o["kind"] == "lead_silent"
                else f"ended with an error: {o.get('error')}")
        side = ("a harness fault, not a product result" if o.get("fault") == "harness" else
                "the product's (the aew-lead MCP server ended)" if o.get("fault") == "product" else
                "fault not established: read as a possible product hang")
        return [f"the scripted Lead {what} ({side}; {o.get('why') or ''})"]
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


def path_problems(op: Operator) -> list[str]:
    """Every fallback the operator took (a step that has not landed, or a refused workaround), and every landed step
    the operator still has no driver for."""
    problems = []
    fallbacks = [o.get("step") for o in op.ledger.operator_fallbacks()]
    if fallbacks:  # any operator fallback fails the gate, whatever counter (if any) it touched
        problems.append(f"the operator fell back to today's workaround at: {', '.join(map(str, fallbacks))}")
    problems += [f"step {o['oracle_step']} ({o['step']}) is {o['state']}, and the operator has no driver for it yet"
                 for o in op.ledger.observations if o["kind"] == "no_driver"]
    return problems


def verdict(op: Operator, *, decisions: tuple[str, ...] | None = V1_DECISIONS,
            limits: tuple[str, ...] = ("publish_needs_decision", "containment")) -> list[str]:
    problems = [f"{k} = {n} (must be 0)" for k, n in op.ledger.over().items()] + path_problems(op)
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


def assert_verdict(op: Operator, problems: list[str]) -> None:
    """Every problem fails the test, on every platform: nothing is softened. On Windows the verdict leads with its
    unqualified state and the conditions still open (``Ledger.verdict_text``; the operator, Q1(e))."""
    assert not problems, op.ledger.verdict_text(problems)


def finish(op: Operator, session) -> None:
    op.end_session(session, "exit")
    merge_lead(op)
    stale_attribution(op)
    containment(op.lab, op.ledger)
    if op.ledger.steering:
        steering_facts(op)
    if "publish_needs_decision" not in op.ledger.hard_limits:
        op.check_heads("at the end")
        op.ledger.hard_limits.setdefault("publish_needs_decision", {"outcome": HELD})


def stale_attribution(op: Operator) -> None:
    """For each STALE_REVISION the Lead met, the commit that staled it: the first transition after the revision the
    call expected, read from the transition log, attributed through the stage intent it belongs to (the steering
    loop's when that intent is auto-run; ``staled_by``). It makes the steering-on variance attributable; it is
    recorded, never counted (counting stays with `stale_retries` and `refusals`)."""
    from aew.engine.outbox import LogView

    def expect_rev(e: dict[str, Any]) -> Any:
        args = e.get("arguments")
        return (args.get("expect_rev") if isinstance(args, dict) else
                args[args.index("--expect-rev") + 1] if isinstance(args, list) and "--expect-rev" in args else None)

    view = LogView(op.lab.aew_root, None)
    events = lead_events(op.lab)
    intents = stage_intents(op.lab.aew_root)
    for e in events:
        error = ((e.get("stopped") or {}).get("error") or {}) if e.get("kind") == "call" else {}
        if error.get("code") != "STALE_REVISION":
            continue
        expected = expect_rev(e)
        record: dict[str, Any] = {}
        try:
            record = view.resolve(int(expected) + 1) or {} if expected is not None else {}
        except Exception as exc:  # recorded, never hidden: attribution is evidence, not a verdict  # noqa: BLE001
            record = {"actor": f"unreadable: {exc}"[:200]}
        op.ledger.observe("stale_revision", tool=e.get("tool"), expect_rev=expected, step=e.get("step"),
                          **staled_by(record, intents), actor=record.get("actor"), op=record.get("op"),
                          summary=record.get("summary"), revision=record.get("revision"))


def steering_facts(op: Operator) -> None:
    """What the steering loop did (the stages it ran, attributed on their intents) and where it stopped: the
    steering-on variant's measurement, recorded whatever it is (spec: check first whether it completes a Ticket)."""
    import yaml

    auto, by_lead = [], []
    for path in sorted(op.lab.aew_root.glob("work/*/stage-intents/*.yaml")):
        intent = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        row = {"intent": path.stem, "tool": intent.get("tool"), "status": intent.get("status")}
        (auto if intent.get("auto_run") else by_lead).append(row)
    loop = op.lab.aew_root / "local" / "steering" / "loop.json"
    state = json.loads(loop.read_text(encoding="utf-8")) if loop.exists() else None
    op.ledger.observe("steering_loop", auto_run_stages=auto, lead_stages=by_lead, loop=state,
                      loop_completed_the_ticket=bool(auto) and not [r for r in by_lead
                                                                    if r["tool"] != "ticket_draft"])
    op.ledger.observe("steering_stop", stop=(state or {}).get("stop"), mode=(state or {}).get("mode"))


@pytest.fixture
def world(tmp_path):
    made: list[Operator] = []
    yield made
    for op in made:
        op.lab.cleanup()
        for close in op.closers:
            close()


def run_aew_json(op: Operator, *args: str) -> Any:
    res = run_aew("-C", str(op.root), *args, env=op.lab.env)
    return res.json if res.returncode == 0 else None


# ---------------------------------------------------------------------------------------------- V1


def run_v1_path(op: Operator, *, steering: bool = False) -> None:
    """Setup, open the Lead session, ask for the fix, answer the Lead until the result, close the session."""
    configure(op, steering=steering)
    op.in_setup = False
    session, _ = open_session(op, "open", steering=steering)
    if steering:  # a raise names the Lead generation its open established, so it follows the open
        raise_steering(op)
    op.say("ask", workers.REQUEST)
    op.converse(session)
    finish(op, session)


def v1_decisions(op: Operator, *, reopened: bool = False) -> tuple[str, ...]:
    """V1's decisions, in the order they are taken. A steering-on run also has the operator's raise after the open,
    and, when the run reopened, again after the reopen (between the plan and the publish), each a decision that is not
    V1's to count."""
    raised = ("steering_mode",) if op.ledger.steering else ()
    if not reopened:
        return raised + V1_DECISIONS
    plan, publish = V1_DECISIONS
    return (*raised, plan, *raised, publish)


@pytest.mark.parametrize("steering", [False, True], ids=["steering-off", "steering-on"])
def test_v1_fresh_path_reaches_a_published_fix_with_no_machinery(tmp_path, world, request, steering):
    op = setup_operator(tmp_path, "V1", steering=steering)
    world.append(op)
    try:
        run_v1_path(op, steering=steering)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=v1_decisions(op)) + result_problems(op)
    assert_verdict(op, problems)


# ---------------------------------------------------------------------------------------------- V1: the hard limits


# Someone else's change lands on main while the publish is prepared. A conflicting one rewrites the very line the
# Ticket fixes (thousands separators), so the Ticket's edit no longer applies; a compatible one touches another file.
CONFLICTING = {"ledger/money.py": "def format_amount(cents):\n    return f\"${abs(cents) / 100:,.2f}\"\n"}
COMPATIBLE = {"README.md": workers.SAMPLE["README.md"] + "\nAmounts are in cents.\n"}


def move_main_at_publish(op: Operator, files: dict[str, str], subject: str) -> dict[str, str]:
    """When the operator is asked to publish, the change lands on main first (once)."""
    moved: dict[str, str] = {}

    def move(msg: dict[str, Any]) -> None:
        if moved:
            return
        moved["subject"] = subject
        moved["path"] = next(iter(files))
        moved["sha"] = op.own_commit(files, subject)
        op.typed("moved", f"(someone else's change lands on main: {moved['path']})")

    op.on_ask["publish"] = move
    return moved


def is_ancestor(op: Operator, sha: str, head: str) -> bool:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, head], cwd=op.root, capture_output=True,
                          stdin=subprocess.DEVNULL, creationflags=flags).returncode == 0


def test_v1_a_semantic_conflict_stops_and_names_the_change(tmp_path, world, request):
    """Main moves under the prepared publish with a change to the line the Ticket fixes: the step must refuse, with a
    message that names the change. Publishing over it ("last writer wins") fails, and so does carrying on with a
    rebuild as if the change were compatible."""
    op = setup_operator(tmp_path, "V1-semantic-conflict")
    world.append(op)
    moved = move_main_at_publish(op, CONFLICTING, "Show thousands separators")
    try:
        run_v1_path(op)
        semantic_conflict(op, moved)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=None, limits=("semantic_conflict", "publish_needs_decision", "containment"))
    assert_verdict(op, problems)


def semantic_conflict(op: Operator, moved: dict[str, str]) -> None:
    """``not_exercised``: main never moved, or no publish followed. ``did_not_refuse``: a publish succeeded over the
    change (main lost it, or a candidate was published after it). ``rebuilt_not_published``: the step carried on with
    a rebuild instead of refusing. Otherwise it refused: held if what the Lead was told names the change."""
    publishes = [e for e in lead_events(op.lab) if e.get("kind") == "call" and e.get("tool") == "integration_publish"]
    if not moved or not publishes:
        op.ledger.hard_limit("semantic_conflict", NOT_EXERCISED, moved=moved,
                             note="main never moved under a publish" if not moved else "no publish was attempted")
        return
    first = publishes[0]
    head = git("rev-parse", "main", cwd=op.root)
    if not is_ancestor(op, moved["sha"], head) or head != moved["sha"]:
        op.ledger.hard_limit("semantic_conflict", NOT_REFUSED, call=first, moved=moved, head=head,
                             note="a publish went ahead over the conflicting change")
        return
    if first.get("ok"):
        op.ledger.hard_limit("semantic_conflict", REBUILT, call=first, moved=moved, head=head,
                             note="the step carried on (rebuilt, re-verifying) instead of refusing the conflict")
        return
    said = str(((first.get("stopped") or {}).get("error") or {}).get("message") or "") + str(first.get("said") or "")
    named = moved["sha"][:7] in said or moved["subject"] in said or moved["path"] in said
    op.ledger.hard_limit("semantic_conflict", HELD if named else UNNAMED, call=first, moved=moved, head=head,
                         note="" if named else "refused, but nothing it told the Lead names the change (its commit, "
                                               "subject or path)")


def test_v1_a_compatible_move_rebuilds_and_publishes_without_ceremony(tmp_path, world, request):
    """The positive counterpart: a compatible change lands on main under the prepared publish. AEW should rebuild,
    re-verify and publish both, with no further question to the operator after the publish approval. (V1 holds the
    zeros; this check is about the move.)"""
    op = setup_operator(tmp_path, "V1-compatible-move")
    world.append(op)
    moved = move_main_at_publish(op, COMPATIBLE, "Say what unit amounts are in")
    try:
        run_v1_path(op)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=None, limits=("publish_needs_decision", "containment"))
    # This check is about the move: V1 holds the zeros and the fallbacks.
    problems = [p for p in problems if " = " not in p and not p.startswith("the operator fell back")]
    problems += result_problems(op)
    if not moved or not is_ancestor(op, moved["sha"], git("rev-parse", "main", cwd=op.root)):
        problems.append("the compatible change is not in what was published")
    labels = [d["label"] for d in op.ledger.decisions]
    after = labels[labels.index("publish") + 1:] if "publish" in labels else []
    if after:
        problems.append(f"the operator was asked again after approving the publish: {after}")
    assert_verdict(op, problems)


# The evidence mismatch, independent of U14: the project's check also changes a TRACKED file (each run appends a line),
# which no scrubbing of caches can make legitimate. The gate must refuse, and the refusal must name that path.
STAMP = "ledger/build-stamp.txt"
STAMP_CHECK = ("import pathlib, subprocess, sys; r = subprocess.call([sys.executable, '-m', 'pytest', '-q', "
               f"'tests']); p = pathlib.Path('{STAMP}'); p.write_text(p.read_text() + 'built\\n'); sys.exit(r)")


def test_v1_an_evidence_mismatch_blocks_and_names_the_paths(tmp_path, world, request):
    """The check changes a tracked file of the snapshot it checks: the gate must refuse, naming that path (an
    auto-waived mismatch fails)."""
    op = setup_operator(tmp_path, "V1-evidence-mismatch", extra={STAMP: "0\n"})
    world.append(op)
    try:
        configure(op, cause="stamp")
        op.in_setup = False
        session, _ = open_session(op, "open")
        op.say("ask", workers.REQUEST)
        op.converse(session)
        finish(op, session)
        evidence_mismatch(op)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=None, limits=("evidence_mismatch", "publish_needs_decision", "containment"))
    assert_verdict(op, problems)


# The refusals that are about evidence and its snapshot (a git or usage error is not the gate speaking).
EVIDENCE_CODES = frozenset({"GATE_UNSATISFIED", "INPUT_STALE", "STALE_CANDIDATE", "WORKSPACE_MUTATED",
                            "OBSERVATION_MUTATED", "EVIDENCE_STALE", "SNAPSHOT_MISMATCH"})


def evidence_mismatch(op: Operator) -> None:
    """The gate's answer to a check that changed a tracked file of its own snapshot. Candidates: a refusal the Lead
    met with an evidence code, a worker's submission refused with one, and a check result AEW marked as having mutated
    its inputs. Named: one of them names the changed path. ``not_exercised`` when no check ever ran. Anything else the
    run met is kept as an observation."""
    found: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for e in lead_events(op.lab):
        for b in e.get("blockers") or [] if e.get("kind") in ("gap", "stuck") else []:
            if b.get("code") in EVIDENCE_CODES:  # the gate, as the projection showed it to the Lead
                found.append({"by": "lead (projection blocker)", "error": b})
        if e.get("kind") == "call" and e.get("ok") is False:
            error = (e.get("stopped") or {}).get("error") or {}
            (found if error.get("code") in EVIDENCE_CODES else other).append(
                {"by": "lead", "tool": e.get("tool"), "error": error})
    checks_ran = False
    for path in sorted(op.lab.aew_root.rglob("transcript.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            step = json.loads(line)
            checks_ran = checks_ran or step.get("do") == "check"
            result = step.get("result") or {}
            out = result.get("stdout_json") if isinstance(result.get("stdout_json"), dict) else {}
            stderr = result.get("stderr_json") if isinstance(result.get("stderr_json"), dict) else {}
            error = stderr.get("error") or {}
            run = path.parent.parent.name
            if out.get("mutated_inputs"):
                found.append({"by": run, "do": step.get("do"), "flag": {k: out.get(k) for k in (
                    "result", "mutated_inputs", "message", "changed_paths") if k in out}})
            elif error:
                (found if error.get("code") in EVIDENCE_CODES else other).append(
                    {"by": run, "do": step.get("do"), "error": error})
    op.ledger.observe("evidence_mismatch.other_refusals", refusals=other[:6])
    if not checks_ran:
        op.ledger.hard_limit("evidence_mismatch", NOT_EXERCISED, note="no check ever ran")
        return
    if not found:
        op.ledger.hard_limit("evidence_mismatch", NOT_REFUSED,
                             note="the check rewrote a tracked file and nothing refused or flagged it")
        return
    named = [f for f in found if STAMP in json.dumps(f)]
    op.ledger.hard_limit("evidence_mismatch", HELD if named else UNNAMED, refusals=found[:6],
                         note="" if named else "refused or flagged without naming the changed paths")


# ---------------------------------------------------------------------------------------------- V2


def run_v2(op: Operator, gate: Path, *, how: str, steering: bool, fresh: bool) -> dict[str, Any]:
    ready = Path(f"{gate}.ready")
    facts: dict[str, Any] = {"how": how, "terminal": "fresh" if fresh else "same shell"}
    configure(op, steering=steering)
    op.in_setup = False
    session, _ = open_session(op, "open", steering=steering)
    if steering:
        raise_steering(op)
    op.say("ask", workers.REQUEST)
    op.converse(session, stop=ready.exists)  # until the implementer announces that it is running
    facts["implementer_running"] = ready.exists()
    op.end_session(session, how)
    facts["lead_gone"] = lead_gone(session)
    session, first = reopen(op, steering=steering) if fresh else open_session(op, "reopen", steering=steering)
    facts["first_words"] = first.get("words")
    facts["run_after_reopen"] = run_status(op, "R-INV-0001-1")
    facts["state_after_reopen"] = ((run_aew_json(op, "work", "show", "T-0001") or {}).get("control") or {}).get(
        "state")
    if steering:  # the reopen started a new Lead generation and the raised mode lapsed with the old one (I6-R01)
        raise_steering(op)
    op.say("reopen:ask", "Where do things stand?")
    gate.write_text("go", encoding="utf-8")  # the implementer finishes only now, after the reopen
    op.converse(session)
    finish(op, session)
    facts.update(v2_facts(op))
    op.ledger.observe("v2", **facts)
    return facts


def reopen(op: Operator, *, steering: bool):
    """Step 10 (reopen) from a fresh terminal, nothing carried over, today's way while it has not landed: the way
    opencode.md documents starting the Lead (`aew opencode --acquire`); when that is refused, the takeover the refusal
    asks for, at the operator's own terminal, with its new credential handed to the session (quickstart, "Losing the
    session")."""
    op.shell_env.clear()
    op.typed("reopen:terminal", "(a new terminal)")
    op.workaround("reopen", "aew opencode --acquire (opencode.md)")
    session = op.open_session("reopen:acquire", ["opencode", "--acquire"], lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    if first is not None:
        return session, first
    op.fallback("reopen:acquire", "aew opencode --acquire", session.output(),
                "aew lead takeover; export AEW_LEAD_TOKEN=<credential>; aew opencode")
    op.takeover("reopen:takeover", "the Lead session ended with work in flight")
    op.export("reopen:takeover", "AEW_LEAD_TOKEN", op.credential)
    session = op.open_session("reopen:open", ["opencode"], lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    assert first is not None, f"the Lead session did not start after the takeover: {session.output()[-2000:]}"
    return session, first


@pytest.mark.parametrize("steering", [False, True], ids=["steering-off", "steering-on"])
@pytest.mark.parametrize("how", ["exit", "kill"])
def test_v2_closing_and_reopening_with_work_active_costs_the_operator_nothing(tmp_path, world, request, how,
                                                                              steering):
    """V2's verdict: the operator opens AEW again from a fresh terminal, as anyone does the next morning."""
    gate = tmp_path / "sync" / "implementer-gate"
    op = setup_operator(tmp_path, f"V2-{how}", steering=steering, gate=gate)
    world.append(op)
    facts: dict[str, Any] = {}
    try:
        facts = run_v2(op, gate, how=how, steering=steering, fresh=True)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=v1_decisions(op, reopened=True)) + result_problems(op) + v2_problems(facts)
    assert_verdict(op, problems)


def test_v2_forced_kill_mid_stage_finishes_through_abandon_reconcile_redispatch(tmp_path, world, request):
    """V2 with the session killed while a stage is half done, every run on every platform: the implementer's launch
    (the second step of `ticket_start`, after `work.assign` committed) is held by the fake harness's hook until the
    test has killed the session; nothing depends on timing. Reopening then needs the takeover, which moves the
    stage's subject: continuing it is refused, the Lead abandons it, reconciles the Ticket and dispatches a new
    implementer attempt, and the run still goes to the end (spec §2). The chain is asserted as well as V2's zeros."""
    op = setup_operator(tmp_path, "V2-forced-mid-stage")
    world.append(op)
    scripts = Path(op.lab.env["AEW_FAKE_SCRIPTS"])
    facts: dict[str, Any] = {"how": "kill, mid-stage", "terminal": "fresh"}
    try:
        configure(op)
        op.in_setup = False
        session, _ = open_session(op, "open")
        (scripts / "pause-launch-implementer").write_text("hold", encoding="utf-8")
        op.say("ask", workers.REQUEST)
        op.converse(session, stop=lambda: any(scripts.glob("paused-R-*")))  # the stage is between its steps
        facts["held_mid_stage"] = any(scripts.glob("paused-R-*"))
        op.end_session(session, "kill")
        facts["lead_gone"] = lead_gone(session)
        (scripts / "resume-launch").write_text("go", encoding="utf-8")
        session, first = reopen(op, steering=False)
        facts["first_words"] = first.get("words")
        op.say("reopen:ask", "Where do things stand?")
        op.converse(session)
        finish(op, session)
        facts.update(v2_facts(op))
        gaps = [e.get("gap") for e in lead_events(op.lab) if e.get("kind") == "gap"]
        facts["chain"] = [g for g in gaps if g in ("decision_refused", "resolve_stage", "refusal_names_a_step",
                                                   "reconcile", "redispatch")]
        op.ledger.observe("v2", **facts)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=v1_decisions(op, reopened=True)) + result_problems(op)
    if not facts.get("held_mid_stage"):
        problems.append("the session was not killed mid-stage (the launch hook never held)")
    for step in ("refusal_names_a_step", "reconcile", "redispatch"):
        if step not in facts.get("chain", []):
            problems.append(f"the forced path did not run its {step} step: {facts.get('chain')}")
    if facts.get("interrupted"):
        problems.append("the Ticket was INTERRUPTED")
    assert_verdict(op, problems)


def test_v2_extra_same_shell_reopen_is_not_v2s_verdict(tmp_path, world, request):
    """An extra measurement, never V2's verdict: the reopen from the same shell, where the credential exported for
    the first open is still set. It shows what that variable alone buys; the fresh terminal above decides V2."""
    gate = tmp_path / "sync" / "implementer-gate"
    op = setup_operator(tmp_path, "V2-extra-same-shell", gate=gate)
    world.append(op)
    facts: dict[str, Any] = {}
    try:
        facts = run_v2(op, gate, how="exit", steering=False, fresh=False)
    finally:
        write_out(op, request)
    problems = verdict(op, decisions=v1_decisions(op, reopened=True)) + result_problems(op) + v2_problems(facts)
    assert_verdict(op, problems)


def lead_gone(session: Any) -> bool:
    """The closed session's TUI process has ended (its pid, recorded by the scripted Lead), within a bound."""
    from notifier import until

    from aew.harness import procs

    if not session.pidfile.exists():
        return True
    pid = int(session.pidfile.read_text(encoding="utf-8"))
    try:
        until(lambda: not procs.pid_alive(pid), 60, "the Lead's TUI to end")
    except AssertionError:
        return False
    return True


def run_status(op: Operator, run: str) -> str | None:
    return runlog.observed_status(runlog.run_dir(op.lab.aew_root, run))[0]


def v2_facts(op: Operator) -> dict[str, Any]:
    shown = run_aew_json(op, "work", "show", "T-0001")
    history = ((shown or {}).get("control") or {}).get("history") or []
    runs = sorted(d.name for d in runlog.run_dir(op.lab.aew_root, "x").parent.glob("R-INV-0001-*"))
    reconciled = [e for e in lead_events(op.lab) if e.get("kind") == "call"
                  and "reconcile" in json.dumps(e.get("arguments"))]
    record = runlog.read_record(runlog.run_dir(op.lab.aew_root, "R-INV-0001-1")) or {}
    return {"interrupted": any(h.get("to") == "INTERRUPTED" for h in history), "implementer_runs": runs,
            "implementer_record": record.get("status"), "reconciles": len(reconciled)}


def v2_problems(facts: dict[str, Any]) -> list[str]:
    problems = []
    if not facts.get("implementer_running"):
        problems.append("the implementer was not running when the session ended")
    if not facts.get("lead_gone"):
        problems.append("the closed Lead session's TUI was still running")
    if facts.get("run_after_reopen") not in ("running", "starting"):
        problems.append(f"the implementer's run was {facts.get('run_after_reopen')} after the reopen (want running)")
    if facts.get("interrupted") or facts.get("state_after_reopen") == "INTERRUPTED":
        problems.append("the Ticket was INTERRUPTED")
    if facts.get("reconciles"):
        problems.append("a reconcile was needed")
    if facts.get("implementer_runs") != ["R-INV-0001-1"] or facts.get("implementer_record") != "ended_with_evidence":
        problems.append(f"the implementer's run was not left alone: {facts.get('implementer_runs')} "
                        f"{facts.get('implementer_record')}")
    words = facts.get("first_words")
    if not words or "T-0001" not in str(words):
        problems.append(f"the operator was not told where things stand in words on reopening: {words!r}")
    return problems


# ---------------------------------------------------------------------------------------------- V3


# Each case's cause and fix are regular expressions over what readiness says: the specific variable, model id, path or
# session, and the specific instruction (review of PR #211, F6: a loose word must not pass). Readiness is step 11
# (P03, `/v1/read/capabilities`); until it lands they are measured on doctor's report, which is not V3's verdict, and
# its driver judges readiness by them (a cause and a fix named, or `accept_as_typed`).
V3_CASES: dict[str, dict[str, Any]] = {
    # A provider variable the policy names is not set where AEW launches.
    "provider-env-unset": {"cause": r"VUAT_PROVIDER_KEY",
                           "fix": r"(?<!un)set\b[^\n]{0,40}VUAT_PROVIDER_KEY|export VUAT_PROVIDER_KEY|"
                                  r"\$env:VUAT_PROVIDER_KEY"},
    # A configured model the harness does not list.
    "model-not-listed": {"cause": r"vuat-missing-model", "fix": r"vuatprov/vuat-model\b"},
    # The check changes the snapshot it runs on (it writes into the tree).
    "check-changes-snapshot": {"cause": r"check-output\.txt", "fix": r"\.gitignore|git/info/exclude"},
    # Stale state the engine could recover: a Lead session that died holding the seat (label `operator`).
    "stale-lead-session": {"cause": r"Lead session[^\n]{0,80}(dead|ended|gone|no longer running|stale)|"
                                    r"(dead|ended|gone|stale)[^\n]{0,40}Lead session",
                           "fix": r"reattach|recover"},
    # The model id carries the provider prefix: the operator pasted the harness's own printed `provider/model` id,
    # and AEW passes provider and id apart, so the joined reference is doubled. Ideal: accepted as typed (no error);
    # otherwise readiness names the doubled reference and suggests the listed id.
    "model-id-provider-prefix": {"cause": r"vuatprov/vuatprov/vuat-model",
                                 "fix": r"(did you mean|use)[^\n]{0,20}vuatprov/vuat-model\b",
                                 "accept_as_typed": True},
}
V3_MODELS = [{"id": "vuat-model", "modelID": "vuat-model", "providerID": "vuatprov", "name": "VUAT", "enabled": True,
              "variants": []}]


def v3_setup(op: Operator, case: str) -> None:
    """Setup with the cause in it: the operator's own first configuration, before any Ticket."""
    if case in ("model-not-listed", "model-id-provider-prefix"):
        scripts = Path(op.lab.env["AEW_FAKE_SCRIPTS"])
        (scripts / "default.json").write_text(json.dumps({"steps": [], "server": {"models": V3_MODELS}}),
                                              encoding="utf-8")
    configure(op, cause=case)
    if case == "stale-lead-session":
        op.in_setup = False
        session, _ = open_session(op, "stale:open")
        op.end_session(session, "kill")
        lead_gone(session)


@pytest.mark.parametrize("case", sorted(V3_CASES))
def test_v3_preflight_names_the_cause_and_the_fix_before_any_ticket(tmp_path, world, request, case):
    op = setup_operator(tmp_path, f"V3-{case}", also=("open",) if case == "stale-lead-session" else ())
    world.append(op)
    want = V3_CASES[case]
    problems: list[str] = []
    try:
        v3_setup(op, case)
        op.in_setup = False
        op.workaround("preflight", "aew doctor (structural health only)")
        doctor = op.type("preflight:doctor", ["doctor"])
        said = doctor.stdout + doctor.stderr
        op.ledger.observe("v3", case=case, readiness=oracle.state_of("preflight")["state"],
                          doctor_exit=doctor.returncode, doctor_names_cause=diagnoses(said, want["cause"]),
                          doctor_names_fix=diagnoses(said, want["fix"]),
                          operator_input_was_the_harness_id=bool(want.get("accept_as_typed")))
        problems += path_problems(op)
        launched = launched_anything(op)
        if launched:
            problems.append(f"something was launched before any Ticket: {launched}")
    finally:
        write_out(op, request)
    assert_verdict(op, problems)


def launched_anything(op: Operator) -> list[str]:
    runs = runlog.run_dir(op.lab.aew_root, "x").parent
    found = [d.name for d in runs.glob("R-*")] if runs.is_dir() else []
    state = run_aew_json(op, "resume", "--json") or {}
    return found + [w["id"] for w in state.get("work") or []]


# ---------------------------------------------------------------------------------------------- V4


CHEAPER = {"provider": "other", "model": "cheaper-model"}


def test_v4_changing_a_setting_is_one_action_that_validates_and_saves(tmp_path, world, request):
    op = setup_operator(tmp_path, "V4")
    world.append(op)
    try:
        configure(op)
        op.in_setup = False
        session, _ = open_session(op, "open")
        op.workaround("setting", "edit .aew/policy/execution.yaml; aew manifest adopt", step="change_model")

        def route(doc: dict[str, Any]) -> None:
            doc["profiles"]["cheaper"] = dict(CHEAPER)
            doc["routing"].setdefault("archetypes", {})["implementer"] = "cheaper"

        op.edit_policy("change_model", "execution.yaml", route)
        op.adopt("change_model:adopt", "the implementer runs on the cheaper model")
        op.say("ask", workers.REQUEST)
        op.converse(session)
        finish(op, session)
    finally:
        write_out(op, request)
    record = runlog.read_record(runlog.run_dir(op.lab.aew_root, "R-INV-0001-1")) or {}
    pin = (record.get("contract") or {}).get("execution_profile") or {}
    problems = verdict(op) + result_problems(op)
    if pin.get("model") != CHEAPER["model"]:
        problems.append(f"the implementer ran on {pin.get('provider')}/{pin.get('model')}, not the new setting")
    assert_verdict(op, problems)


# ---------------------------------------------------------------------------------------------- steering


def raise_steering(op: Operator) -> None:
    """Step 13 (raise) today's way while it has not landed on an adopted wire (F5: today's command serves it with no
    adopted action): the operator raises the steering mode to Run at the operator endpoint, a decision, not a
    lifecycle step. The endpoint runs in its own terminal and `aew lead mode raise run` in another, with the code typed
    back; both terminals are this process (the in-process channel AT-1 uses on Windows), the endpoint and its code are
    real. The endpoint starts with the first raise, and a later raise (after a reopen) uses it again."""
    from notifier import Console

    from aew.engine.api import Engine
    from aew.harness import operator_client, operator_endpoint

    op.workaround("raise", "aew operator serve; aew lead mode raise run, the code typed back")
    if op.steering_console is None:
        op.steering_console = Console()
        endpoint = operator_endpoint.OperatorEndpoint(Engine.discover(op.root), console=op.steering_console, dev=True,
                                                      timeout=30)
        endpoint.start()
        op.closers.append(endpoint.close)
        op.typed("steering:serve", "aew operator serve --dev")
    console = op.steering_console
    op.typed("steering:raise", "aew lead mode raise run")
    try:
        out = operator_client.request_raise(op.lab.aew_root, "run", ask=lambda prompt: console.code())
        answer = f"yes (typed the code): {json.dumps(out)[:200]}"
    except Exception as exc:  # recorded, never hidden: the run goes on in the mode it has  # noqa: BLE001
        answer = f"refused: {exc}"
    op.ledger.decision("raise the Lead's steering mode to run?", answer, label="steering_mode", asked_by="operator")


# ---------------------------------------------------------------------------------------------- G3: #213, rebuilt


def test_g3_the_213_listener_death_is_diagnosed_from_the_kept_files_alone(tmp_path, world, request, monkeypatch):
    """The hang-and-flake diagnosis plan's own test (G3, "the real case"). In #213 the vertical lane hung for 30
    minutes once: the Lead's chat listener, in the fake TUI **subprocess**, died with no trace, under a chat bound
    (1800 s) equal to the lane's --test-timeout, and the evidence was deleted with tmp_path.

    Rebuilt here: the listener dies of an exception no ``except Exception`` catches, on the operator's first request.
    From the autopsy's kept files alone: the listener died and why (the TUI's childdiag events, and ``thread_died`` in
    the Lead's events), where the test was waiting (the operator's chat wait ran out, in the flight recorder) and where
    the Lead was (its periodic stacks: waiting to hear), and that the old bounds broke the nesting rule, which the pin
    (``test_ci_tools``) now fails first."""
    import sys

    import autopsy
    import bounds
    from fake_harness import SCRIPTS_ENV
    from vertical import scripted_operator

    op = setup_operator(tmp_path, "G3-213")
    world.append(op)
    configure(op)
    op.in_setup = False
    autopsy.mark_helper_dir(Path(op.lab.env[SCRIPTS_ENV]), interval=2)  # a dump every 2 s, for this test only
    module = sys.modules[__name__]
    injected = module.lead_spec
    monkeypatch.setattr(module, "lead_spec", lambda lab, steering=False: {**injected(lab, steering=steering),
                                                                         "inject": "listener_dies"})
    monkeypatch.setattr(scripted_operator, "CONVERSATION_S", 20.0)  # the operator's wait, short for this test
    session, _ = open_session(op, "open")
    op.say("ask", workers.REQUEST)
    assert op.converse(session) is None  # the operator's wait ran out: the Lead is silent
    plugin = autopsy.current()
    assert plugin is not None
    kept = plugin.collect(request.node.nodeid, "G3: the #213 reconstruction", item=request.node)
    op.end_session(session, "kill")

    def read(pattern: str) -> str:
        return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(kept.rglob(pattern))
                         if p.is_file())

    events = read("events-*")  # the TUI's own record of the death (childdiag)
    assert "thread_exception" in events and "vertical-chat" in events and "InjectedDeath" in events, events
    assert "the listener died on its first operator message" in events and "_listen" in events, events
    assert "thread_died" in read("lead-events.jsonl*")  # and in the Lead's events, which the ledger reads
    lead_stacks = read("stacks-*")
    assert "in hear" in lead_stacks, lead_stacks[-3000:]  # the Lead waits to hear what its dead listener never passes
    recorder = read("recorder.*")
    assert '"name": "chat.operator.receive"' in recorder and '"ended": "timeout"' in recorder, recorder[-3000:]
    in_force = read("bounds*")
    assert "vertical.chat: 1500s" in in_force and "vertical.conversation: 1200s" in in_force, in_force

    # The bounds #213 ran under break the nesting rule: the pin fails on them before any run could hang.
    lane = next(x for x in bounds.workflow_lanes(Path(__file__).resolve().parents[2] / ".github" / "workflows")
                if x.lane == "vertical")
    old = [bounds.Bound("vertical.chat", 1800, None, frozenset({"vertical"})),
           bounds.Bound("vertical.conversation", 1800, None, frozenset({"vertical"}))]
    found = bounds.nesting_problems(lane, old)
    assert any("bound vertical.chat (1800s) is not below --test-timeout 1800s" in p for p in found), found
    assert bounds.nesting_problems(lane, [b for b in bounds.BOUNDS.values() if b.name.startswith("vertical.")]) == []
