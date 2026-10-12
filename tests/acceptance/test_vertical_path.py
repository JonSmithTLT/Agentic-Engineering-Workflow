"""The vertical UAT (spec v2): a fresh project and a normal operator session, from setup to a published one-line fix.

docs/implementation/vertical-uat.md states what it proves, its actors, its scenarios (V1 to V4), the burden ledger and
the hard limits. **It is expected to fail on today's main**: its first job is to measure by how much. Every scenario
goes to the end and writes its ledger (``vertical-ledger.json`` and a one-screen summary) whatever it finds, then
asserts. Nothing here is xfailed, skipped or softened; the job is in shadow (``VERTICAL_MODE``), outside the merge
gate, until the operator flips it. Windows is outside the enforced gate (the operator, Q1(e)): its job keeps running
and reporting, and every verdict it prints leads with its unqualified state and the conditions still open.

The actors are all scripted and offline: the operator (``vertical/scripted_operator.py``: only what a human types),
the Lead (``vertical/lead.py``: no AEW knowledge, inside the fake OpenCode TUI that the real ``aew opencode`` starts,
talking to the real broker over MCP), and the workers (``vertical/workers.py``: the fake harness making a real fix
checked by a real ``python -m pytest``).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import git, run_aew
from notifier import recorder
from vertical import workers
from vertical.chat import Mailbox
from vertical.ledger import HELD, NOT_EXERCISED, NOT_REFUSED, REBUILT, UNNAMED, V1_DECISIONS, Ledger, diagnoses
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
    # Spec v2: opening AEW opens the operator console, which asks for the PIN at most once per endpoint lifetime
    # (per project, per login session). The auto-opened console is not a counted step. Until B1, the ideal attempt
    # fails and today's fallback (the credential in AEW_LEAD_TOKEN) is counted as before.
    "open": {"input": "aew opencode", "status": EXISTS,
             "ideal": "opens the operator console, which asks for the PIN (at most once per endpoint lifetime), then "
                      "the Lead session, and runs preflight (PROPOSED behaviour): no credential, no variable, no "
                      "seat to manage"},
    "ask": {"input": workers.REQUEST, "status": EXISTS, "ideal": "a chat line to the Lead"},
    "decide": {"input": "yes", "status": EXISTS,
               "ideal": "answers only real judgements: the plan, and the publish (unless a grant covers it)"},
    "exit": {"input": "/exit", "status": EXISTS, "ideal": "ends the Lead session; work in flight is untouched"},
    "reopen": {"input": "aew opencode", "status": EXISTS,
               "ideal": "resumes without a takeover or a credential, and says where things stand in words; the "
                        "console's PIN is asked again only by a new endpoint (PROPOSED behaviour)"},
    "preflight": {"input": "aew preflight", "status": PROPOSED,
                  "ideal": "readiness: fails before any Ticket exists, naming the cause and the fix"},
    "change_model": {"input": "aew settings set execution.roles.implementer.model other/cheaper-model",
                     "status": PROPOSED,
                     "ideal": "one operator action that validates and saves; no raw YAML, no adopt, no restart"},
    "raise": {"input": "aew lead mode raise run", "status": EXISTS,
              "ideal": "the operator raises the Lead's steering mode at the operator endpoint: a decision, confirmed "
                       "on the endpoint's console on every platform (never a console challenge)"},
}


# ---------------------------------------------------------------------------------------------- the operator's steps


def ideal_argv(step: str) -> list[str]:
    return shlex.split(IDEAL_PATH[step]["input"])[1:]


def configure(op: Operator, *, steering: bool = False, cause: str | None = None) -> None:
    """Setup: the check command and the harness, the ideal way first. ``cause`` puts a V3 cause into the operator's
    first configuration; ``steering`` adds what Run needs (a starting mode, a notifier, hard deadlines)."""
    res = op.type("configure", ideal_argv("configure"))
    if res.returncode == 0:
        return
    instead = "edit .aew/policy/checks.yaml and execution.yaml, aew lead acquire, aew manifest adopt (quickstart)"
    op.fallback("configure", IDEAL_PATH["configure"]["input"], res.stderr or res.stdout, instead)
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
    """``aew opencode`` (the ``open`` or ``reopen`` row), the ideal way first; today's fallback is the credential in
    AEW_LEAD_TOKEN (quickstart). The operator's terminal is one shell: a variable exported earlier is still set."""
    row = "reopen" if step == "reopen" else "open"
    spec = lead_spec(op.lab, steering=steering)
    session = op.open_session(step, ideal_argv(row), spec)
    first = op.first_words(session)
    console_opened(op, step)
    if first is not None:
        return session, first
    op.fallback(step, IDEAL_PATH[row]["input"], session.output(), "export AEW_LEAD_TOKEN=<credential>; aew opencode")
    if op.shell_env.get("AEW_LEAD_TOKEN") != op.credential:
        op.export(step, "AEW_LEAD_TOKEN", op.credential)
    session = op.open_session(step, ideal_argv(row), lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    assert first is not None, f"the Lead session did not start: {session.output()[-2000:]}"
    return session, first


def console_opened(op: Operator, step: str) -> None:
    """Whether opening AEW opened the operator console (spec v2, the ``open`` row): an endpoint is live for the
    project that the test did not start in-process. Recorded, never counted: the auto-opened console is not a step.
    The PIN it asks for is counted by ``Ledger.pin_entered`` (at most once per endpoint lifetime), wired with the
    console by B1; nothing opens one before B1."""
    from aew.harness import operator_client

    found = operator_client.status(op.lab.aew_root)
    opened = bool(found.get("running")) and found.get("pid") != os.getpid()
    op.ledger.observe("open.console", step=step, auto_opened=opened,
                      endpoint={k: found.get(k) for k in ("pid", "started_at")} if opened else None)


def setup_operator(tmp_path: Path, scenario: str, *, steering: bool = False, **world: Any) -> Operator:
    lab = new_world(tmp_path, **world)
    ledger = Ledger(scenario, steering=steering)
    chat = Mailbox(tmp_path / "sync" / "chat", "operator",
                   on_error=lambda path, exc: ledger.observe("chat_read_error", file=path.name,
                                                             error=f"{type(exc).__name__}: {exc}"[:300]))
    op = Operator(lab, ledger, tmp_path, chat)
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
    silent = [o for o in op.ledger.observations if o["kind"] == "lead_silent"]
    if not op.reports and silent:  # a harness fault, never reported as AEW's (review of #213, G2)
        return [f"the scripted Lead went silent waiting for {silent[0].get('waiting_for')} (a harness fault, not a "
                f"product result; chat errors: {silent[0].get('chat_errors')})"]
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
    fallbacks = [o.get("step") for o in op.ledger.operator_fallbacks()]
    if fallbacks:  # any operator fallback fails the gate, whatever counter (if any) it touched
        problems.append(f"the operator fell back to today's workaround at: {', '.join(map(str, fallbacks))}")
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
    if steering:
        raise_steering(op)
    session, _ = open_session(op, "open", steering=steering)
    op.say("ask", workers.REQUEST)
    op.converse(session)
    finish(op, session)


def v1_decisions(op: Operator) -> tuple[str, ...]:
    """V1's decisions; a steering-on run also has the operator's raise, a decision that is not V1's to count."""
    return (("steering_mode",) if op.ledger.steering else ()) + V1_DECISIONS


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
    if steering:
        raise_steering(op)
    session, _ = open_session(op, "open", steering=steering)
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
    op.say("reopen:ask", "Where do things stand?")
    gate.write_text("go", encoding="utf-8")  # the implementer finishes only now, after the reopen
    op.converse(session)
    finish(op, session)
    facts.update(v2_facts(op))
    op.ledger.observe("v2", **facts)
    return facts


def reopen(op: Operator, *, steering: bool):
    """Open AEW again from a fresh terminal, nothing carried over. The ideal step first (`aew opencode`); then the
    way opencode.md documents starting the Lead (`aew opencode --acquire`); then the takeover a refusal asks for, at
    the operator's own terminal, with its new credential handed to the session (quickstart, "Losing the session")."""
    op.shell_env.clear()
    op.typed("reopen:terminal", "(a new terminal)")
    session = op.open_session("reopen", ideal_argv("reopen"), lead_spec(op.lab, steering=steering))
    first = op.first_words(session)
    if first is not None:
        return session, first
    op.fallback("reopen", IDEAL_PATH["reopen"]["input"], session.output(), "aew opencode --acquire (opencode.md)")
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
    problems = verdict(op, decisions=v1_decisions(op)) + result_problems(op) + v2_problems(facts)
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
    problems = verdict(op, decisions=v1_decisions(op)) + result_problems(op)
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
    problems = verdict(op, decisions=v1_decisions(op)) + result_problems(op) + v2_problems(facts)
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
# session, and the specific instruction (review of PR #211, F6: a loose word must not pass).
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
    op = setup_operator(tmp_path, f"V3-{case}")
    world.append(op)
    want = V3_CASES[case]
    problems: list[str] = []
    try:
        v3_setup(op, case)
        op.in_setup = False
        res = op.type("preflight", ideal_argv("preflight"))
        said = res.stdout + res.stderr
        if res.returncode != 0 and "invalid choice: 'preflight'" in said:
            op.fallback("preflight", IDEAL_PATH["preflight"]["input"], said, "aew doctor (structural health only)")
        doctor = op.type("preflight:doctor", ["doctor"])
        accepted = bool(want.get("accept_as_typed")) and res.returncode == 0
        op.ledger.observe("v3", case=case, preflight_exit=res.returncode, preflight=said[-1500:],
                          doctor_exit=doctor.returncode,
                          doctor_names_cause=diagnoses(doctor.stdout + doctor.stderr, want["cause"]),
                          operator_input_was_the_harness_id=bool(want.get("accept_as_typed")),
                          accepted_as_typed=accepted)
        if not accepted:
            if res.returncode == 0:
                problems.append(f"readiness passed with the cause in place: {said[-300:]}")
            elif not diagnoses(said, want["cause"]):
                problems.append(f"readiness did not name the cause {want['cause']}: {said[-300:]}")
            elif not diagnoses(said, want["fix"]):
                problems.append(f"readiness did not name the fix {want['fix']}: {said[-300:]}")
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
        res = op.type("change_model", ideal_argv("change_model"))
        if res.returncode != 0:
            op.fallback("change_model", IDEAL_PATH["change_model"]["input"], res.stderr or res.stdout,
                        "edit .aew/policy/execution.yaml; aew manifest adopt")

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
    """The operator raises the steering mode to Run at the operator endpoint: a decision, not a lifecycle step. The
    endpoint runs in its own terminal and `aew lead mode raise run` in another, with the code typed back; both
    terminals are this process (the in-process channel AT-1 uses on Windows), the endpoint and its code are real."""
    from notifier import Console

    from aew.engine.api import Engine
    from aew.harness import operator_client, operator_endpoint

    console = Console()
    endpoint = operator_endpoint.OperatorEndpoint(Engine.discover(op.root), console=console, dev=True, timeout=30)
    endpoint.start()
    op.closers.append(endpoint.close)
    op.typed("steering:serve", "aew operator serve --dev")
    op.typed("steering:raise", "aew lead mode raise run")
    try:
        out = operator_client.request_raise(op.lab.aew_root, "run", ask=lambda prompt: console.code())
        answer = f"yes (typed the code): {json.dumps(out)[:200]}"
    except Exception as exc:  # recorded, never hidden: the run goes on in the mode it has  # noqa: BLE001
        answer = f"refused: {exc}"
    op.ledger.decision("raise the Lead's steering mode to run?", answer, label="steering_mode", asked_by="operator")
