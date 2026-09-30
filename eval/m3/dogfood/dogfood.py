"""The M3 step-9 dogfood: AEW with a headless model Lead, against raw OpenCode, on the ``ledger`` fixture tasks.

Evaluation tooling, not product code. The tasks, the rubric and this driver are fixed before any paid run
(``rubric.md``); every run's record is appended to ``results.jsonl``, whatever its outcome.

**AEW mode.** A scratch project (a git repository outside the AEW checkout) is set up the way an operator would:
``aew init``, the ``unit`` check, guardrails and the execution policy (harness ``opencode``, the model under test).
The Lead is a real model: ``aew lead session --acquire -- <this file> lead-child`` holds the Lead credential in the
broker; the child runs a headless OpenCode session of the production ``aew-lead`` agent (``headless.py``) whose
shell reaches AEW only through the broker. The Lead gets the brief below and the objective, and does everything
else itself: Tickets, plans, dispatches with ``--launch`` (real role runs through the production adapter),
waits, ingests, transitions, integration. If its turn ends before the work is DONE it is nudged (at most twice;
each nudge is an intervention). T5 starts from a scripted first implementation (the seeded defect); T6 loses the
Lead's OpenCode mid-run (its state is wiped) and a fresh session resumes from AEW alone.

**Raw mode.** The same scratch repository with no AEW: OpenCode's own ``build`` agent, the same model, the objective
as the prompt, the same isolation. No nudges.

**Judging** is the hidden test (``hidden.py``), never visible to a model: on the integrated commit (AEW) or the
working tree (raw). Also recorded: cost (as OpenCode reports it, and from tokens at catalog prices), tokens, wall
time, steps, invocations and runs, reviews, state history, scope, interventions, and the safety checks (no AEW
credential and no provider key in any file the run left; the AEW checkout untouched).

Usage, from the AEW checkout with the provider key in the environment::

    python eval/m3/dogfood/dogfood.py selfcheck
    python eval/m3/dogfood/dogfood.py run T1 --mode aew --model openai/gpt-5.6-luna#medium
    python eval/m3/dogfood/dogfood.py run T1 --mode raw --model openai/gpt-5.6-luna#medium
    python eval/m3/dogfood/dogfood.py setup T2 --dir <scratch> --model ...   # a project for the operator's TUI session
"""

from __future__ import annotations

import argparse
import calendar
import fnmatch
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]  # the AEW checkout
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

from aew.util import dump_yaml  # noqa: E402

FIXTURE = HERE / "fixture"
RESULTS = HERE / "results.jsonl"
NO_WINDOW: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
SCHEMA = "aew/dogfood-run/v1"
SCOPE = ("ledger/*", "tests/*", "README.md")
ROLE_STEPS, ROLE_DEADLINE_S = 60, 900
LEAD_STEPS, RAW_STEPS = 150, 80
MAX_NUDGES = 2
# T6: the Lead's OpenCode is lost as soon as its first role run has been launched (amendment A2: a time trigger,
# "a run running for 60 s", never fired because GPT-5.6 Luna's runs finish sooner).
# USD per million tokens, from OpenCode 2.0.18's model catalog on 2026-09-28 (the tier below 200k context).
PRICES = {
    "openai/gpt-5.6-luna": {"input": 0.20, "output": 1.20, "cache_read": 0.02, "cache_write": 0.25},
    "openai/gpt-6-sol": {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50},
}
PROVIDER_ENV = {"openai": "OPENAI_API_KEY"}

# ---------------------------------------------------------------------------------------------- the tasks

T5_SPEC = ("Add `split_amount(total, parts)` to ledger/money.py: it splits a non-negative Decimal amount into `parts` "
           "amounts, each in whole cents, that add up exactly to `total`; leftover cents go one each to the first "
           "parts (10.00 into 3 gives 3.34, 3.33, 3.33). A `parts` below 1 raises ValueError.")
T2_OBJECTIVE = ("Add a `--category NAME` option to `python -m ledger summary`. It limits the summary to that "
                "category's entries, matching the name case-insensitively, and it can be combined with `--month`. "
                "For an unknown category the command exits with status 2 and prints an error to stderr that names "
                "the known categories. Document the option in README.md.")


REFERENCE_OF = {"T6": "T2", "T1C0": "T1"}  # tasks that share another task's starting point and hidden test


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    objective: str               # the operator's words: the Lead's objective and the raw prompt
    overlay: str | None = None   # files over the base project (the task's starting point)
    seeded: bool = False         # T5: a first implementation exists (AEW: submitted by a scripted implementer)
    lead_loss: bool = False      # T6: the Lead's OpenCode is lost mid-run
    lead_deadline_s: int = 2700
    raw_deadline_s: int = 900


T1_OBJECTIVE = ("In reports, negative amounts come out as `$-15.00`; they should read `-$15.00`, with the minus sign "
                "before the dollar sign (a refund row in a ledger CSV shows it). Fix it.")

TASKS = {t.id: t for t in (
    Task("T1", "tiny fix (Class 0)", T1_OBJECTIVE, overlay="T1"),
    # Amendment A3 (rubric.md): T1 with the operator directing Class 0, to exercise the Class 0 path end to end.
    Task("T1C0", "tiny fix, operator-directed Class 0", T1_OBJECTIVE + " It is a trivial, low-risk fix: handle it as "
         "a Class 0 Ticket.", overlay="T1"),
    Task("T2", "multi-file feature", T2_OBJECTIVE),
    Task("T3", "bug that needs investigation", "The monthly summaries don't add up. For data/sample.csv, the "
         "summaries for 2025-12, 2026-01 and 2026-02 together come to $4,713.70, but all the rows in the file add "
         "up to $4,754.94. Find out why and fix it.", overlay="T3"),
    Task("T4", "wrong initial hypothesis", "In the monthly report some category totals are off by cents to dimes. "
         "Example: `python -m ledger summary data/sample.csv --month 2026-01` shows `Groceries: $54.14`, but the two "
         "January grocery rows in data/sample.csv add up to $54.50. We believe this is float rounding (report.py adds "
         "the amounts up as floats): please move the report's arithmetic to Decimal so the totals are exact.",
         overlay="T4"),
    Task("T5", "review with a seeded defect", T5_SPEC, seeded=True),
    Task("T6", "resume after losing the Lead's harness", T2_OBJECTIVE, lead_loss=True),
)}

T5_TICKET = {
    "title": "Add split_amount()", "class": "1", "scope": ["ledger/**", "tests/**"],
    "contract": "changes stay within ledger/ and tests/",
    "goals": ["ledger.money.split_amount(Decimal('10.00'), 3) == [Decimal('3.34'), Decimal('3.33'), Decimal('3.33')]",
              "split_amount's shares are whole cents and always add up exactly to the total",
              "split_amount(total, parts) raises ValueError when parts < 1"],
    "plan": "1. Add split_amount(total, parts) to ledger/money.py as the goals describe.\n"
            "2. Add focused tests in tests/test_split.py.\n",
}
T5_REPORT = {"claim": "split_amount(total, parts) added with focused tests", "result": "pass",
             "producer": {"model": "seeded-first-attempt", "harness": "scripted"},
             "implementation": {"files_changed": ["ledger/money.py", "tests/test_split.py"], "checks_run": ["unit"],
                                "deviations": [], "self_review": {"completed": True, "notes": "matches the plan"}}}

# ---------------------------------------------------------------------------------------------- the Lead's brief

HEADLESS = ("You are the AEW Lead for the repository in this session, working headless: the operator is not present "
            "and nobody will answer questions. Make the decisions a Lead makes, record them in AEW, and keep going "
            "until the work is DONE. Stop early only if a decision truly belongs to the operator: then record it in a "
            "checkpoint (`aew checkpoint --note-file - --next \"...\" --expect-rev N <<'EOF'` ... `EOF`) and end your "
            "turn.")
WORKING = """## Working with AEW

- `aew status` shows the revision, the work and the next actions; `aew resume` rebuilds your context; `aew <command> --help` explains any command. Every change takes `--expect-rev N` with the current revision (each command returns the new one).
- Work goes through Tickets. Create one with its free text as data, never typed into the command line (the shell rewrites `$`, backticks, globs and quotes): `aew work create ticket --class <0-4> --expect-rev N --fields - <<'EOF'`, then YAML with `title:`, `goal:` (a list of observable outcomes), `contract:` (a list of rules) and `scope:` (a list of globs, one per item), then `EOF`. Then a plan: `aew plan propose <T> --file - --expect-rev N <<'EOF'` ... `EOF`, and `aew plan accept <T> --revision 1 --expect-rev N`. Reasons and notes take `--fields -` the same way (`reason:`, `next:`). Class 0 is for trivial, low-risk changes: it needs no review or verification before integration.
- Delegate: implementation, investigation, review and verification are bounded invocations, each dispatched with `--launch` so that AEW starts its run: `aew work assign <T> --launch --expect-rev N` (the implementer), `aew invoke create <T> --role reviewer --launch --expect-rev N`, `--role verifier`, and after `aew integrate prepare` the post-integration verifier `aew invoke create <T> --scope integration --launch --expect-rev N`. To find something out before changing code, create a non-mutating Ticket (`--non-mutating --card investigator`) and `aew work dispatch <T> --launch --expect-rev N`.
- Follow a run with `aew harness wait <run> --timeout 110`, repeated until it has ended; `aew harness status` lists runs. A run ending is not progress: ingest its evidence (`aew review ingest`, `aew verify ingest` or `aew evidence ingest`, with `--evidence <id>`) and move the Ticket on (`aew work transition <T> --to <STATE>`).
- A mutating Ticket goes READY → (assign) → RUNNING → REVIEW_PENDING → (review) → VERIFY_PENDING → (verification) → VERIFIED → COMMIT_READY → `aew integrate prepare` → (post-integration verification) → `aew integrate publish` → DONE. A failed review or verification sends it back to RUNNING for a fresh implementer.
- Your shell runs only `aew` and read-only `git` commands, and you cannot edit files: pass text with a heredoc (`--file - <<'EOF'`).

When the work is DONE, reply with a short summary: what changed, the evidence for it, and anything the operator should decide."""
NUDGE = ("The objective is not DONE yet: `aew status` shows open work. Continue as the Lead until it is DONE, or record "
         "in a checkpoint why it cannot be finished without the operator, and end your turn.")
# Rubric A5: asked once the measured work is over. Its answer is a lead for the analysis, checked against the
# transcript, never a score; its cost and steps are recorded so that comparisons leave them out.
DEBRIEF = ("The work is over. One last question, from the people who build AEW: your answer changes nothing in this "
           "project, so do not run any commands. In a few short bullets: (1) what in AEW's commands, messages or "
           "instructions confused you or cost you steps; (2) what you expected to exist or to be told that was not "
           "there; (3) how you chose each Ticket's risk class; (4) where you looked to learn how AEW works. Be "
           "specific, and say 'nothing' where nothing applies.")
DEBRIEF_S = 180
GUIDE_MODES = ("embedded", "pointer", "none")
RAW_TAIL = "\n\nNobody will answer questions during this session: make reasonable decisions and finish the task."


def lead_prompt(task: Task, ticket: str | None = None) -> str:
    objective = task.objective
    if task.seeded:
        objective = (f"Ticket {ticket} ({T5_TICKET['title']}) has been implemented and its implementer's report is "
                     f"in; the Ticket is waiting for review (REVIEW_PENDING). Take it to DONE: review, verification "
                     f"and integration.")
    return f"{HEADLESS}\n\n## Objective from the operator\n\n{objective}\n\n{WORKING}"


def resume_prompt() -> str:
    return (f"{HEADLESS}\n\nYour previous Lead session was lost: its harness crashed and the conversation is gone. "
            f"AEW's state is intact. Rebuild your context with `aew resume` and continue the work in progress until "
            f"it is DONE.\n\n{WORKING}")


def raw_prompt(task: Task) -> str:
    if task.seeded:
        return (f"A teammate added `split_amount` to ledger/money.py, with tests in tests/test_split.py, for this "
                f"requirement: {T5_SPEC}\n\nReview the change and make sure it is correct and ready to merge; fix "
                f"anything that is not.{RAW_TAIL}")
    return task.objective + RAW_TAIL


# ---------------------------------------------------------------------------------------------- helpers


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def epoch(stamp: str) -> int:
    return calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True,
                          stdin=subprocess.DEVNULL, **NO_WINDOW).stdout


def profile_of(ref: str) -> dict[str, Any]:
    target, _, effort = ref.partition("#")
    provider, _, model = target.partition("/")
    if not provider or not model:
        raise SystemExit(f"--model {ref!r}: expected provider/model[#effort]")
    return {"provider": provider, "model": model, **({"effort": effort} if effort else {})}


def model_key(profile: dict[str, Any]) -> str:
    return f"{profile['provider']}/{profile['model']}"


def provider_env(profile: dict[str, Any]) -> list[str]:
    name = PROVIDER_ENV.get(profile["provider"])
    return [name] if name else []


def priced(key: str, tokens: dict[str, Any] | None) -> float | None:
    """Cost from tokens at catalog prices (reasoning billed as output; cache writes at the catalog's cache-write
    price, as OpenCode charges them), as a cross-check of OpenCode's own figure."""
    price = PRICES.get(key)
    if not price or not isinstance(tokens, dict):
        return None
    cache = tokens.get("cache") or {}
    out = (tokens.get("output") or 0) + (tokens.get("reasoning") or 0)
    return round(((tokens.get("input") or 0) * price["input"] + (cache.get("read") or 0) * price["cache_read"]
                  + (cache.get("write") or 0) * price["cache_write"] + out * price["output"]) / 1e6, 6)


def add_tokens(*many: dict[str, Any] | None) -> dict[str, Any]:
    total = {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}
    for t in many:
        if not isinstance(t, dict):
            continue
        for k in ("input", "output", "reasoning"):
            total[k] += t.get(k) or 0
        for k in ("read", "write"):
            total["cache"][k] += (t.get("cache") or {}).get(k) or 0
    return total


def build_repo(task: Task, repo: Path, *, with_seed: bool) -> str:
    """The task's starting point as a fresh git repository; returns its first commit."""
    shutil.copytree(FIXTURE / "base", repo)
    if task.overlay:
        shutil.copytree(FIXTURE / "overlays" / task.overlay, repo, dirs_exist_ok=True)
    if with_seed:
        shutil.copytree(FIXTURE / "seeded" / task.id, repo, dirs_exist_ok=True)
    for path in repo.rglob("*"):  # LF only, whatever the checkout did
        if path.is_file():
            path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Ledger Developer")
    git(repo, "config", "user.email", "dev@ledger.invalid")
    git(repo, "config", "core.autocrlf", "false")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "ledger: initial" if not with_seed else "ledger: add split_amount")
    return git(repo, "rev-parse", "HEAD").strip()


def aew_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_PROFILE")}
    env["PYTHONUTF8"] = "1"
    env.update(extra or {})
    return env


def aew(repo: Path, *args: str, env: dict[str, str] | None = None, stdin: str | None = None,
        timeout: float = 300) -> Any:
    res = subprocess.run([sys.executable, "-m", "aew", "-C", str(repo), *args], capture_output=True, text=True,
                         encoding="utf-8", env=aew_env(env), input=stdin, timeout=timeout,
                         stdin=None if stdin is not None else subprocess.DEVNULL, **NO_WINDOW)
    if res.returncode != 0:
        raise RuntimeError(f"aew {' '.join(args[:3])} failed ({res.returncode}): {(res.stderr or res.stdout)[-800:]}")
    return json.loads(res.stdout) if res.stdout.strip().startswith(("{", "[")) else res.stdout


def configure(repo: Path, profile: dict[str, Any], routing: dict[str, str]) -> None:
    """What the operator sets up before a Lead starts: the project, its check, guardrails, the execution policy."""
    aew(repo, "init", "--project-id", "ledger")
    policy = repo / ".aew" / "policy"
    (policy / "checks.yaml").write_text(dump_yaml({
        "schema": "aew/checks/v1",
        "checks": {"unit": {"configured": True, "command": ["{python}", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                                            "tests"],
                            "cwd": ".", "timeout_s": 300, "description": "the project's pytest suite"}},
        "baseline_failures": []}), encoding="utf-8", newline="\n")
    (policy / "guardrails.yaml").write_text(dump_yaml({
        "schema": "aew/guardrails/v1", "protected_paths": [], "generated_paths": [], "ticket_scope_enforcement": True,
        "review_triggers": [], "dependency_rules": []}), encoding="utf-8", newline="\n")
    limits = {"max_steps": ROLE_STEPS, "deadline_s": ROLE_DEADLINE_S}
    profiles = {"standard": {**profile, **limits}}
    archetypes = {}
    for role, ref in sorted(routing.items()):
        profiles[f"{role}-route"] = {**profile_of(ref), **limits}
        archetypes[role] = f"{role}-route"
    envs = sorted({n for p in profiles.values() for n in provider_env(p)})
    (policy / "execution.yaml").write_text(dump_yaml({
        "schema": "aew/execution/v1", "configured": True, "harness": "opencode", "provider_env": envs,
        "profiles": profiles, "routing": {"default": "standard", "archetypes": archetypes, "classes": {},
                                          "cards": {}}}), encoding="utf-8", newline="\n")


def seed_t5(repo: Path, work: Path) -> tuple[str, str]:
    """T5's starting point in AEW: the Ticket, its accepted plan, and a scripted first implementation (the seeded
    defect) submitted with its own invocation credential. Returns the Lead credential (memory only) and the Ticket."""
    token = aew(repo, "lead", "acquire", "--expect-rev", "0", "--session-label", "dogfood-setup")["token"]

    def lead(*args: str, stdin: str | None = None) -> Any:
        rev = aew(repo, "status", "--json")["revision"]
        return aew(repo, *args, "--expect-rev", str(rev), env={"AEW_LEAD_TOKEN": token}, stdin=stdin)

    args = ["work", "create", "ticket", "--title", T5_TICKET["title"], "--class", T5_TICKET["class"],
            "--contract", T5_TICKET["contract"]]
    for s in T5_TICKET["scope"]:
        args += ["--scope", s]
    for g in T5_TICKET["goals"]:
        args += ["--goal", g]
    wid = lead(*args)["id"]
    lead("plan", "propose", wid, "--file", "-", "--affected", "ledger/money.py", stdin=T5_TICKET["plan"])
    lead("plan", "accept", wid, "--revision", "1")
    out = lead("work", "assign", wid)
    lead("work", "transition", wid, "--to", "RUNNING")
    workspace, inv_token = Path(out["workspace"]["path"]), out["invocation_token"]
    shutil.copytree(FIXTURE / "seeded" / "T5", workspace, dirs_exist_ok=True)
    role = {"AEW_INVOCATION_TOKEN": inv_token}
    aew(workspace, "check", "run", "unit", env=role)
    aew(workspace, "submit", "--kind", "implementation_report", "--file", "-", env=role,
        stdin=f"---\n{dump_yaml(T5_REPORT)}---\nImplemented per plan v1.\n")
    lead("work", "transition", wid, "--to", "REVIEW_PENDING")
    del inv_token
    return token, wid


# ---------------------------------------------------------------------------------------------- the Lead (child)


def lead_child(spec_path: Path) -> int:
    """Runs inside ``aew lead session``: the broker holds the Lead credential; this process never has it."""
    import headless
    from aew.engine.api import Engine
    from aew.harness import contract as K
    from aew.harness import runlog
    from aew.harness.opencode import projection

    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    repo, state_root = Path(spec["repo"]), Path(spec["state"])
    profile, cap = spec["profile"], float(spec["cap_usd"])
    engine = Engine.discover(repo)
    runs_root = runlog.run_dir(engine.aew_root, "x").parent
    broker = {k: os.environ[k] for k in ("AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY")}
    env = headless.shell_env(os.environ, broker)
    guide = spec.get("guide", "embedded")
    guide = {True: "embedded", False: "pointer"}.get(guide, guide) if isinstance(guide, bool) else guide  # A4's specs
    config, rules = headless.lead_config(profile, LEAD_STEPS,
                                         guide=engine.lead_guide() if guide == "embedded" else "",
                                         pointer=guide != "none")
    deadline = time.monotonic() + float(spec["deadline_s"])
    out: dict[str, Any] = {"sessions": [], "nudges": 0, "stop": None, "lost": False}
    spent_closed = 0.0

    def role_cost() -> float:
        total = 0.0
        for d in runs_root.glob("*") if runs_root.is_dir() else []:
            usage = ((runlog.read_record(d) or {}).get("result") or {}).get("usage") or {}
            total += float(usage.get("cost") or 0)
        return total

    def stop_runs(reason: str) -> None:
        for d in runs_root.glob("*") if runs_root.is_dir() else []:
            if runlog.observed_status(d)[0] in (K.STARTING, K.RUNNING):
                runlog.request(d, "stop", {"reason": reason})

    def done() -> bool:
        work = engine.store.read()["work"]
        tickets = [u for u in work.values() if u["kind"] == "ticket"]
        return (bool(tickets) and all(u["state"] in ("DONE", "CANCELLED") for u in work.values())
                and any(u["state"] == "DONE" for u in tickets))

    def open_session(n: int) -> Any:
        session = headless.HeadlessSession(state_root / f"lead-{n}")
        session.open(directory=repo, profile=profile, agent=projection.LEAD_AGENT, config=config, env=env,
                     provider_env=spec["provider_env"], rules=rules, title=f"AEW Lead (dogfood {spec['task']})")
        return session

    def tick(session: Any) -> str | None:
        spent = spent_closed + float(session.live_usage().get("cost") or 0) + role_cost()
        if spent > cap:
            return "cost_cap"
        if spec["lead_loss"] and not out["lost"] and runs_root.is_dir() and any(runs_root.glob("*")):
            return "lose"  # the Lead has launched its first role run: its harness is lost mid-Ticket (amendment A2)
        return None

    def debrief(session: Any, stop: Any) -> dict[str, Any]:
        """Rubric A5: one question about AEW, after the measured work. Its own cost, steps and commands are recorded
        so that comparisons leave them out, and so is whether it changed AEW state (it should not)."""
        before = {"cost": float(session.live_usage().get("cost") or 0),
                  "steps": headless.assistant_steps(session.state_dir),
                  "commands": len(headless.command_log(session.state_dir)), "revision": engine.store.read()["revision"]}
        session.say(DEBRIEF)
        outcome = session.wait_turn(time.monotonic() + DEBRIEF_S, stop)
        return {"outcome": outcome, "text": headless.last_text(session.state_dir)[:4000],
                "cost_usd": round(float(session.live_usage().get("cost") or 0) - before["cost"], 6),
                "steps": headless.assistant_steps(session.state_dir) - before["steps"],
                "commands": len(headless.command_log(session.state_dir)) - before["commands"],
                "revision_changed": engine.store.read()["revision"] != before["revision"]}

    session = open_session(1)
    session.say(spec["prompt"])
    try:
        while True:
            outcome = session.wait_turn(deadline, lambda: tick(session))
            if outcome == "lose":  # T6: the Lead's harness is lost; its OpenCode state is wiped
                record = session.close()
                spent_closed += float((record.get("usage") or {}).get("cost") or 0)
                out["sessions"].append({**record, "lost_at_s": record.get("wall_s")})
                shutil.rmtree(session.run_dir / "harness", ignore_errors=True)
                out["lost"] = True
                session = open_session(2)
                session.say(spec["resume_prompt"])
                continue
            if outcome in ("cost_cap", "deadline"):
                out["stop"] = outcome
                stop_runs(f"dogfood {outcome}")
                break
            if done():
                break
            if "failed (provider." in str(session.detail):  # quota, authentication: a nudge cannot help
                out["stop"] = f"provider_error: {session.detail}"
                stop_runs("dogfood provider error")
                break
            if out["nudges"] >= MAX_NUDGES:
                out["stop"] = "not_done_after_nudges"
                break
            out["nudges"] += 1
            session.say(NUDGE)
        if out["stop"] in (None, "not_done_after_nudges"):
            out["debrief"] = debrief(session, lambda: "cost_cap" if tick(session) == "cost_cap" else None)
    finally:
        out["sessions"].append(session.close())
        (state_root / "lead.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------------------------- collecting


def hidden(task: str, tree: Path) -> dict[str, Any]:
    res = subprocess.run([sys.executable, str(HERE / "hidden.py"), task, str(tree)], capture_output=True, text=True,
                         encoding="utf-8", timeout=600, stdin=subprocess.DEVNULL, **NO_WINDOW)
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"task": task, "passed": False, "error": (res.stderr or res.stdout)[-600:]}


def export_commit(repo: Path, commit: str, dest: Path) -> Path:
    data = subprocess.run(["git", "archive", "--format=tar", commit], cwd=repo, capture_output=True, check=True,
                          stdin=subprocess.DEVNULL, **NO_WINDOW).stdout
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")
    return dest


def in_scope(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in SCOPE)


def changed_paths(repo: Path, base: str, head: str | None) -> list[str]:
    if head:
        return sorted(p for p in git(repo, "diff", "--name-only", base, head).split() if p)
    paths = set(git(repo, "diff", "--name-only", base).split())
    paths |= set(git(repo, "ls-files", "--others", "--exclude-standard").split())
    return sorted(paths)


def refused(commands: list[dict[str, Any]]) -> list[str]:
    """Tool calls the session's permission rules refused (V2 denies without asking: a failed tool call)."""
    return [c.get("cmd") or c.get("tool") for c in commands if str(c.get("error") or "").startswith("permission")]


def session_summary(s: dict[str, Any], key: str) -> dict[str, Any]:
    usage = s.get("usage") or {}
    commands = s.get("commands") or []
    return {"wall_s": s.get("wall_s"), "steps": s.get("steps"), "turns": len(s.get("turns") or []),
            "commands": commands, "refused": refused(commands),
            "tokens": usage.get("tokens"), "cost": usage.get("cost"), "cost_from_tokens": priced(key, usage.get("tokens")),
            "tools_called": s.get("tools_called"), "effective": s.get("effective"),
            "first_step_input_tokens": s.get("first_step_input_tokens"),
            "permission_rejected": [r.get("action") for r in s.get("permission_rejected") or []],
            "forms_cancelled": len(s.get("forms_cancelled") or []), "last_detail": s.get("last_detail"),
            "version": s.get("version")}


def collect_aew(repo: Path, base: str, work: Path) -> dict[str, Any]:
    import headless
    from aew.engine.api import Engine
    from aew.harness import runlog
    from aew.knowledge import evidence as E
    from aew.util import parse_frontmatter

    engine = Engine.discover(repo)
    state = engine.store.read()
    units, reviews, verifications = {}, [], []
    for wid, u in sorted(state["work"].items()):
        units[wid] = {k: u.get(k) for k in ("kind", "state", "title", "risk_class", "class", "non_mutating")
                      if u.get(k) is not None}
        units[wid]["history"] = [[h.get("from"), h.get("to"), h.get("reason")] for h in u.get("history") or []]
        units[wid]["integrated"] = (u.get("integration") or {}).get("commit") if u["state"] == "DONE" else None
        for e in E.scan(engine.aew_root, wid)[0]:
            if e["kind"] not in ("review", "verification"):
                continue
            meta = parse_frontmatter((engine.aew_root / "evidence" / wid / f"{e['id']}.md").read_text(encoding="utf-8"),
                                     source=e["id"])[0]
            if e["kind"] == "review":
                r = meta.get("review") or {}
                reviews.append({"unit": wid, "evidence": e["id"], "run": e["producer"].get("run"),
                                "disposition": r.get("disposition"), "resolved": r.get("resolved_findings"),
                                "findings": [{k: f.get(k) for k in ("id", "severity", "required", "summary")}
                                             for f in r.get("findings") or []]})
            else:
                v = meta.get("verification") or {}
                verifications.append({"unit": wid, "evidence": e["id"], "run": e["producer"].get("run"),
                                      "result": e.get("result"), "scope": v.get("scope"),
                                      "claims": [{k: c.get(k) for k in ("type", "claim", "result")}
                                                 for c in v.get("claims") or []]})
    invocations, runs = {}, []
    for inv_id, inv in sorted(state["invocations"].items()):
        pin = inv.get("execution_profile") or {}
        invocations[inv_id] = {"unit": inv.get("work_unit"), "role": inv.get("role"), "card": inv.get("card"),
                               "status": inv.get("status"), "model": f"{pin.get('provider')}/{pin.get('model')}"
                               + (f"#{pin['effort']}" if pin.get("effort") else ""),
                               "runs": [r["run"] for r in inv.get("runs") or []]}
        for r in inv.get("runs") or []:
            rec = runlog.read_record(runlog.run_dir(engine.aew_root, r["run"])) or {}
            result, key = rec.get("result") or {}, f"{pin.get('provider')}/{pin.get('model')}"
            usage = result.get("usage") or {}
            wall = (epoch(rec["ended_at"]) - epoch(rec["started_at"])) if rec.get("ended_at") and rec.get(
                "started_at") else None
            commands = headless.command_log(runlog.run_dir(engine.aew_root, r["run"]) / "harness")
            runs.append({"run": r["run"], "invocation": inv_id, "role": inv.get("role"), "status": rec.get("status"),
                         "reason": rec.get("reason"), "wall_s": wall, "steps": result.get("steps"),
                         "tokens": usage.get("tokens"), "cost": usage.get("cost"),
                         "cost_from_tokens": priced(key, usage.get("tokens")),
                         "model_check": (rec.get("model_check") or {}).get("status"),
                         "tools_called": result.get("tools_called"), "commands": commands,
                         "refused": refused(commands),
                         "first_step_input_tokens": result.get("first_step_input_tokens"),
                         "context": (rec.get("launch") or {}).get("context"),
                         "permission_rejected": [p.get("action") for p in result.get("permission_rejected") or []],
                         "bridge_outcomes": (rec.get("bridge") or {}).get("outcomes"),
                         "credential_scan_clean": (rec.get("credential_scan") or {}).get("clean"),
                         "evidence": [e["id"] for e in E.scan(engine.aew_root, inv.get("work_unit"))[0]
                                      if e["producer"].get("run") == r["run"]]})
    head = git(repo, "rev-parse", "main").strip()
    tree = export_commit(repo, head, work / "tree-integrated") if head != base else None
    judged = hidden_result = hidden(state_task(work), tree) if tree else {"passed": False, "note": "nothing integrated"}
    workspaces = [u.get("workspace") for u in state["work"].values() if u.get("workspace")]
    out = {"units": units, "invocations": invocations, "runs": runs, "reviews": reviews,
           "verifications": verifications, "integrated_commit": head if head != base else None,
           "hidden": judged, "changed_paths": changed_paths(repo, base, head) if head != base else [],
           "revision": state["revision"]}
    if not hidden_result.get("passed") and workspaces:  # correct but not integrated?
        ws = Path(workspaces[-1]["path"])
        if ws.exists():
            out["hidden_workspace"] = hidden(state_task(work), ws)
    return out


def state_task(work: Path) -> str:
    return json.loads((work / "run.json").read_text(encoding="utf-8"))["task"]


def scan_secrets(root: Path, secret: str | None) -> dict[str, Any]:
    from aew.harness import runlog

    leaked = []
    if secret:
        needle = secret.encode()
        for p in root.rglob("*"):
            try:
                if p.is_file() and p.stat().st_size < 64 * 2**20 and needle in p.read_bytes():
                    leaked.append(str(p.relative_to(root)))
            except OSError:
                continue
    return {"aew_credentials": runlog.scan_for_credentials(root), "provider_key_files": leaked,
            "provider_key_checked": bool(secret)}


def stop_leftovers(repo: Path) -> list[str]:
    """End any run still going (a Lead that stopped early leaves its runs): asked, then waited for."""
    from aew.harness import contract as K
    from aew.harness import runlog

    aew_root = repo / ".aew"
    runs_root = runlog.run_dir(aew_root, "x").parent
    stopped = []
    for d in sorted(runs_root.glob("*")) if runs_root.is_dir() else []:
        if runlog.observed_status(d)[0] in (K.STARTING, K.RUNNING):
            runlog.request(d, "stop", {"reason": "dogfood teardown"})
            stopped.append(d.name)
    limit = time.monotonic() + 90
    for d in sorted(runs_root.glob("*")) if runs_root.is_dir() else []:
        while runlog.observed_status(d)[0] in (K.STARTING, K.RUNNING) and time.monotonic() < limit:
            time.sleep(1)
    return stopped


# ---------------------------------------------------------------------------------------------- one run


def run(task_id: str, mode: str, model: str, routing: dict[str, str], cap: float, results: Path,
        guide: str = "embedded") -> dict[str, Any]:
    import headless

    task, profile = TASKS[task_id], profile_of(model)
    names = provider_env(profile) + [n for ref in routing.values() for n in provider_env(profile_of(ref))]
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise SystemExit(f"{', '.join(missing)} is not set: the provider key must be in the environment")
    secret = os.environ.get(names[0]) if names else None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    work = Path(tempfile.gettempdir()) / "aew-dogfood" / f"{task_id}-{mode}-{stamp}"
    work.mkdir(parents=True)
    repo = work / "repo"
    base = build_repo(task, repo, with_seed=task.seeded and mode == "raw")
    (work / "run.json").write_text(json.dumps({"task": task_id, "mode": mode}), encoding="utf-8")
    checkout_before = git(ROOT, "status", "--porcelain", "--untracked-files=all")
    record: dict[str, Any] = {"schema": SCHEMA, "task": task_id, "title": task.title, "mode": mode, "model": model,
                              "routing": routing, "cap_usd": cap, "started_at": now(), "workdir": str(work),
                              "lead_guide": guide if mode == "aew" else None,  # rubric A4 (true/false), A5 (mode)
                              "aew_commit": git(ROOT, "rev-parse", "--short", "HEAD").strip(),
                              "agent_shell": "bash" if os.environ.get("SHELL") else "powershell",
                              "limits": {"role_steps": ROLE_STEPS, "role_deadline_s": ROLE_DEADLINE_S,
                                         "lead_steps": LEAD_STEPS, "raw_steps": RAW_STEPS,
                                         "lead_deadline_s": task.lead_deadline_s, "raw_deadline_s": task.raw_deadline_s}}
    t0 = time.monotonic()
    try:
        if mode == "aew":
            configure(repo, profile, routing)
            env: dict[str, str] = {}
            ticket = None
            session_args = ["lead", "session", "--acquire", "--session-label", "dogfood-lead"]
            if task.seeded:
                token, ticket = seed_t5(repo, work)
                env = {"AEW_LEAD_TOKEN": token}  # the broker takes it; its child never sees it
                session_args = ["lead", "session", "--session-label", "dogfood-lead"]
                record["setup"] = {"scripted": ["Ticket and accepted plan", "a seeded first implementation, submitted",
                                                "REVIEW_PENDING"], "ticket": ticket}
            spec = {"task": task_id, "repo": str(repo), "state": str(work / "lead"), "profile": profile,
                    "provider_env": provider_env(profile), "cap_usd": cap, "deadline_s": task.lead_deadline_s,
                    "lead_loss": task.lead_loss, "prompt": lead_prompt(task, ticket), "resume_prompt": resume_prompt(),
                    "guide": guide}
            (work / "lead").mkdir()
            spec_path = work / "lead-spec.json"
            spec_path.write_text(json.dumps(spec, indent=1), encoding="utf-8")
            res = subprocess.run([sys.executable, "-m", "aew", "-C", str(repo), *session_args, "--", sys.executable,
                                  str(HERE / "dogfood.py"), "lead-child", "--spec", str(spec_path)],
                                 capture_output=True, text=True, encoding="utf-8", env=aew_env(env),
                                 timeout=task.lead_deadline_s + 1200, stdin=subprocess.DEVNULL, **NO_WINDOW)
            env.clear()
            (work / "lead-session.log").write_text(f"exit {res.returncode}\n{res.stdout}\n{res.stderr}",
                                                   encoding="utf-8")
            try:
                record["lead_session"] = json.loads(res.stdout)
            except ValueError:
                record["lead_session"] = {"exit": res.returncode, "error": (res.stderr or res.stdout)[-800:]}
            lead = json.loads((work / "lead" / "lead.json").read_text(encoding="utf-8")) \
                if (work / "lead" / "lead.json").exists() else {}
            record["stopped_runs"] = stop_leftovers(repo)
            record["lead"] = {"sessions": [session_summary(s, model_key(profile)) for s in lead.get("sessions") or []],
                              "nudges": lead.get("nudges"), "stop": lead.get("stop"), "lost": lead.get("lost"),
                              "debrief": lead.get("debrief")}
            record.update(collect_aew(repo, base, work))
            record["interventions"] = lead.get("nudges") or 0
        else:
            session = headless.HeadlessSession(work / "raw")
            session.open(directory=repo, profile=profile, agent="build", config=headless.raw_config(profile, RAW_STEPS),
                         env=headless.shell_env(os.environ), provider_env=provider_env(profile),
                         title=f"raw OpenCode (dogfood {task_id})")
            session.say(raw_prompt(task))

            def over_cap() -> str | None:
                return "cost_cap" if float(session.live_usage().get("cost") or 0) > cap else None

            outcome = session.wait_turn(time.monotonic() + task.raw_deadline_s, over_cap)
            record["raw"] = {**session_summary(session.close(), model_key(profile)), "outcome": outcome}
            record["hidden"] = hidden(task_id, repo)
            record["changed_paths"] = changed_paths(repo, base, None)
            record["interventions"] = 0
    finally:
        record["wall_s"] = round(time.monotonic() - t0, 1)
        record["ended_at"] = now()
        record["out_of_scope"] = [p for p in record.get("changed_paths") or [] if not in_scope(p)]
        record["safety"] = scan_secrets(work, secret)
        record["safety"]["checkout_untouched"] = git(ROOT, "status", "--porcelain",
                                                     "--untracked-files=all") == checkout_before
        record["totals"] = totals(record, model_key(profile))
        with results.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return record


def totals(record: dict[str, Any], key: str) -> dict[str, Any]:
    parts = [s for s in (record.get("lead") or {}).get("sessions") or []] + list(record.get("runs") or [])
    if record.get("raw"):
        parts.append(record["raw"])
    cost = sum(float(p.get("cost") or 0) for p in parts)
    from_tokens = [p.get("cost_from_tokens") for p in parts]
    lead_cost = sum(float(s.get("cost") or 0) for s in (record.get("lead") or {}).get("sessions") or [])
    debrief = (record.get("lead") or {}).get("debrief") or {}
    return {"cost_usd": round(cost, 6),
            "debrief_cost_usd": debrief.get("cost_usd"),  # rubric A5: included in cost_usd, left out of comparisons
            "cost_from_tokens_usd": round(sum(float(c) for c in from_tokens if c is not None), 6)
            if any(c is not None for c in from_tokens) else None,
            "lead_cost_share": round(lead_cost / cost, 3) if cost else None,
            "tokens": add_tokens(*[p.get("tokens") for p in parts]),
            "runs": len(record.get("runs") or []), "invocations": len(record.get("invocations") or {}),
            "passed": bool((record.get("hidden") or {}).get("passed")),
            "done": any(u.get("state") == "DONE" for u in (record.get("units") or {}).values())}


# ---------------------------------------------------------------------------------------------- self-check, setup


def selfcheck() -> int:
    """Every task's starting point passes the project's own tests and fails its hidden test; the reference
    solution passes both. No model, no AEW, no cost."""
    references = {"T1": {"ledger/money.py": FIXTURE / "base/ledger/money.py"},
                  "T2": {"ledger/cli.py": FIXTURE / "reference/T2/ledger/cli.py",
                         "README.md": FIXTURE / "reference/T2/README.md"},
                  "T3": {"ledger/dates.py": FIXTURE / "base/ledger/dates.py"},
                  "T4": {"ledger/money.py": FIXTURE / "base/ledger/money.py"},
                  "T5": {"ledger/money.py": FIXTURE / "reference/T5/ledger/money.py"}}
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        for tid, task in TASKS.items():
            repo = Path(tmp) / tid
            build_repo(task, repo, with_seed=task.seeded)
            start = hidden(tid, repo)
            for rel, src in references[REFERENCE_OF.get(tid, tid)].items():
                shutil.copyfile(src, repo / rel)
            solved = hidden(tid, repo)
            good = start.get("project_tests") and not start.get("passed") and solved.get("passed") and solved.get(
                "project_tests")
            ok &= bool(good)
            failing = [c["name"] for c in start.get("checks") or [] if not c["ok"]]
            print(f"{tid}: start project_tests={start.get('project_tests')} hidden={start.get('passed')} "
                  f"(failing: {failing}) | reference hidden={solved.get('passed')} "
                  f"project_tests={solved.get('project_tests')} -> {'OK' if good else 'BAD'}")
            if not solved.get("passed"):
                print("   ", [c for c in solved.get("checks") or [] if not c["ok"]])
    return 0 if ok else 1


def setup(task_id: str, directory: Path, model: str) -> int:
    task = TASKS[task_id]
    build_repo(task, directory / "repo", with_seed=False)
    configure(directory / "repo", profile_of(model), {})
    print(json.dumps({"repo": str(directory / "repo"), "objective": task.objective}, indent=1))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="dogfood")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("task", choices=sorted(TASKS))
    r.add_argument("--mode", choices=("aew", "raw"), required=True)
    r.add_argument("--model", required=True, help="provider/model[#effort]")
    r.add_argument("--routing", default="", help="role=provider/model[#effort],... (AEW mode)")
    r.add_argument("--guide", choices=GUIDE_MODES, default="embedded",
                   help="AEW mode: the project's guide in the Lead's system text (embedded), only the system text's "
                        "pointer to `aew guide` (pointer: rubric A4's before arm), or neither (none: rubric A5)")
    r.add_argument("--no-guide", dest="guide", action="store_const", const="pointer", default=argparse.SUPPRESS,
                   help="the same as --guide pointer (rubric A4's before arm)")
    r.add_argument("--cap-usd", type=float, default=1.50, help="stop the run when its cost passes this")
    r.add_argument("--results", type=Path, default=RESULTS)
    c = sub.add_parser("lead-child")
    c.add_argument("--spec", type=Path, required=True)
    sub.add_parser("selfcheck")
    s = sub.add_parser("setup")
    s.add_argument("task", choices=sorted(TASKS))
    s.add_argument("--dir", type=Path, required=True)
    s.add_argument("--model", required=True)
    args = parser.parse_args()
    if args.cmd == "lead-child":
        return lead_child(args.spec)
    if args.cmd == "selfcheck":
        return selfcheck()
    if args.cmd == "setup":
        return setup(args.task, args.dir, args.model)
    routing = dict(item.split("=", 1) for item in args.routing.split(",") if item.strip())
    record = run(args.task, args.mode, args.model, routing, args.cap_usd, args.results, guide=args.guide)
    t = record["totals"]
    print(json.dumps({"task": record["task"], "mode": record["mode"], "model": record["model"],
                      "passed": t["passed"], "done": t["done"], "cost_usd": t["cost_usd"],
                      "cost_from_tokens_usd": t["cost_from_tokens_usd"], "wall_s": record["wall_s"],
                      "runs": t["runs"], "interventions": record.get("interventions"),
                      "safety": record["safety"], "workdir": record["workdir"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
