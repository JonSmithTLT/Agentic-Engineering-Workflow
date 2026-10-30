"""The scripted operator of the vertical UAT: only what a human types at a fresh terminal, every input and output kept.

The operator knows what the product's documentation tells a user (``docs/guides/quickstart.md``, ``opencode.md``) and
nothing of AEW's internals. Each step of the path is V-01's oracle's (``vertical.oracle``), its state derived from the
code. A step that has not landed is taken today's way, and the fallback is recorded with its evidence (the step's
citation, its derived state and what holds it, and what was typed instead); a step that has landed and that the
operator has no driver for yet is recorded as ``no_driver``, which fails the verdict. So the ledger stops counting
ceremony as soon as the product no longer needs it.

**The setup boundary** (docs/implementation/vertical-uat.md): setup is ``aew init`` and the project's first
configuration (its check command and its harness), before the first Lead session opens. Hand-edited policy files in
setup are recorded as observations, not ``raw_yaml``; an edit after setup counts. Everything else in setup, such as an
acquire, a credential or a separate adopt, is counted like any other step.

**Channels the test substitutes:** a decision AEW confirms at the operator's own terminal (a policy adoption, a
takeover, a steering raise) runs in this process with the terminal channel substituted, the in-process channel AT-1
uses on Windows, on every platform here. What the operator typed is recorded exactly as they would type it.

The offline world (the fake harness, the fake OpenCode binary and its scripts) is the test's, like an installed tool:
its variables are not the operator's (``AEW_HARNESS_ADAPTERS``, ``AEW_FAKE_SCRIPTS``, ``AEW_OPENCODE_BIN``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import autopsy
import bounds
from conftest import IS_WINDOWS, CLIResult, Project, clean_env, git, make_git_repo, run_aew
from fake_harness import SCRIPTS_ENV, HarnessLab
from fake_opencode import TUI_SCRIPT, write_launcher

from aew.harness import runlog
from aew.util import dump_yaml
from vertical import lead as _lead  # noqa: F401  (the Lead runs in its TUI; this declares its bounds here too)
from vertical import oracle, workers
from vertical.chat import Gone, Mailbox
from vertical.ledger import (
    CONTAINMENT_MINIMUM,
    HELD,
    LABEL_ORDER,
    LEAD,
    NOT_EXERCISED,
    NOT_REFUSED,
    WORKERS,
    Ledger,
    _json_objects,
    at_least,
)

# Declared and nested under the vertical lane's --test-timeout (G3 H5): the operator's waits fail first, by name, and
# record why the Lead was silent (`lead_silent`).
SESSION_START_S = bounds.declare("vertical.session_start", 300, within="vertical.conversation", lanes={"vertical"},
                                 why="the operator's wait for a new Lead session's first words")
CONVERSATION_S = bounds.declare(
    "vertical.conversation", 1200, lanes={"vertical"},
    why="the operator's wait for the Lead's next message. In #213 it was 1800 s, equal to the lane's --test-timeout")
EXIT_S = bounds.declare("vertical.exit", 120, within="vertical.conversation", lanes={"vertical"},
                        why="the operator's wait for a session to end after /exit or a kill")


@dataclass
class Session:
    """One ``aew opencode`` the operator started: its process, and where its terminal output went."""

    proc: subprocess.Popen[bytes]
    out: Path
    err: Path
    pidfile: Path

    def ended(self) -> bool:
        return self.proc.poll() is not None

    def output(self) -> str:
        return (self.out.read_text(encoding="utf-8", errors="replace") if self.out.exists() else "") + \
            (self.err.read_text(encoding="utf-8", errors="replace") if self.err.exists() else "")


@dataclass
class Operator:
    lab: HarnessLab
    ledger: Ledger
    tmp: Path
    chat: Mailbox
    shell_env: dict[str, str] = field(default_factory=dict)  # what the operator exported in their own shell
    credential: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)
    allowed_heads: set[str] = field(default_factory=set)  # main's heads not published by AEW
    excluded_caches: bool = False  # the U14 workaround, applied once after the gate was observed to refuse
    publish_approved: bool = False
    reports: list[dict[str, Any]] = field(default_factory=list)
    said: list[dict[str, Any]] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    on_ask: dict[str, Callable[[dict[str, Any]], None]] = field(default_factory=dict)
    in_setup: bool = True
    closers: list[Callable[[], None]] = field(default_factory=list)  # in-process terminals the test opened
    session_id: str = ""  # the current Lead session's per-open id (its records carry it; review of #213, I1)
    chat_errors_at_open: int = 0  # the operator's chat read errors before the current session opened

    @property
    def root(self) -> Path:
        return self.lab.root

    # ------------------------------------------------------------------ what the operator types

    def type(self, step: str, argv: list[str], *, shown_text: bool = True) -> CLIResult:
        """An `aew` command line at the operator's terminal (with what their shell exports)."""
        res = run_aew("-C", str(self.root), *argv, env={**self.lab.env, **self.shell_env})
        text = "aew " + " ".join(argv)
        self.ledger.operator_input(text, step=step, argv=argv, shown=res.stdout + res.stderr if shown_text else "")
        self.transcript.append({"step": step, "input": text, "exit": res.returncode,
                                "output": (res.stdout + res.stderr)[-2000:]})
        return res

    def typed(self, step: str, text: str, argv: list[str] | None = None, *, shown: str = "") -> None:
        """Something the operator typed that the test carries out itself (an in-process terminal channel)."""
        self.ledger.operator_input(text, step=step, argv=argv, shown=shown)
        self.transcript.append({"step": step, "input": text})

    def fallback(self, step: str, ideal: str, observed: str, instead: str) -> None:
        self.ledger.observe("fallback", step=step, ideal=ideal, observed=observed[-600:], fallback=instead)

    def workaround(self, key: str, instead: str, *, step: str = "") -> None:
        """Step ``key`` of the oracle's path is about to be taken today's way (``instead``). While the step has not
        landed that is a fallback, its evidence the step's citation and derived state; once it has landed it is
        ``no_driver``: the operator still lacks the step's driver, which the verdict names."""
        found = oracle.state_of(key)
        cited = "; ".join(f"{p['catalog']} {p.get('action') or p.get('route') or p.get('act')}" for p in found["parts"])
        if oracle.landed(found["state"]):
            self.ledger.observe("no_driver", step=step or key, oracle_step=found["step"], state=found["state"],
                                instead=instead)
            return
        held = f", held by {', '.join(found['held_by'])}" if found.get("held_by") else ""
        self.fallback(step or key, f"step {found['step']} ({cited or 'no serving surface'})",
                      f"{found['state']}{held}", instead)

    def export(self, step: str, name: str, value: str) -> None:
        self.shell_env[name] = value
        text = f"export {name}={value}"
        self.ledger.count("env_vars", {"input": text}, actor="operator", step=step)
        self.typed(step, text)

    def edit_policy(self, step: str, name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        import yaml

        path = self.root / ".aew" / "policy" / name
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        mutate(doc)
        path.write_text(dump_yaml(doc), encoding="utf-8", newline="\n")
        evidence = {"input": f"$EDITOR .aew/policy/{name}"}
        if self.in_setup:
            self.ledger.observe("setup_edit", step=step, file=f".aew/policy/{name}")
            self.transcript.append({"step": step, "input": evidence["input"], "setup": True})
        else:
            self.ledger.count("raw_yaml", evidence, actor="operator", step=step)
            self.transcript.append({"step": step, **evidence})

    def rev(self) -> int:
        return int(run_aew("-C", str(self.root), "lead", "show", env=self.lab.env).json["revision"])

    def adopt(self, step: str, reason: str) -> None:
        """``aew manifest adopt``, as the quickstart documents it, confirmed at the operator's terminal (in-process)."""
        from aew.engine.api import Engine

        rev = self.rev()  # read from `aew status`, as the quickstart says
        self.typed(f"{step}:status", "aew status")
        self.typed(step, f'aew manifest adopt --reason "{reason}" --token {self.credential} --expect-rev {rev}',
                   ["manifest", "adopt", "--reason", reason, "--token", "<credential>", "--expect-rev", str(rev)])
        Engine.discover(self.root).manifest_adopt(token=self.credential, expect_rev=rev, reason=reason,
                                                  authorization={"authorized_by": "operator-tty"})

    def takeover(self, step: str, reason: str) -> None:
        """``aew lead takeover`` at the operator's terminal (the challenge channel substituted in-process, as AT-1)."""
        import aew.operator
        from aew.engine.api import Engine

        rev = self.rev()
        self.typed(f"{step}:status", "aew status")
        original = aew.operator.authorize
        aew.operator.authorize = lambda challenge, **_: {"authorized_by": "operator-tty (vertical UAT)"}
        try:
            token = Engine.discover(self.root).lead_takeover(expect_rev=rev, reason=reason,
                                                             session_label="operator")["token"]
        finally:
            aew.operator.authorize = original
        self.typed(step, f'aew lead takeover --reason "{reason}" --expect-rev {rev}',
                   ["lead", "takeover", "--reason", reason, "--expect-rev", str(rev)], shown=token)
        self.credential = token
        self.lab.project.token = token

    # ------------------------------------------------------------------ the Lead session

    def new_session(self, lead_spec: dict[str, Any]) -> dict[str, Any]:
        """Each open is its own session (review of #213, I1): a fresh id its records carry (a reused pid cannot match
        it), no state file left from the previous session, and the operator's chat errors counted from here, so a
        silence is judged only on this session's evidence. The spec the TUI reads is written with the id."""
        lead_spec = {**lead_spec, "session": uuid.uuid4().hex}
        self.session_id = lead_spec["session"]
        self.chat_errors_at_open = len(self.chat.errors)
        Path(lead_spec["state"]).unlink(missing_ok=True)
        (Path(self.lab.env[SCRIPTS_ENV]) / TUI_SCRIPT).write_text(json.dumps(lead_spec), encoding="utf-8")
        return lead_spec

    def open_session(self, step: str, argv: list[str], lead_spec: dict[str, Any]) -> Session:
        lead_spec = self.new_session(lead_spec)
        n = len(self.lab.sessions)
        out, err = self.tmp / f"session-{n}.out", self.tmp / f"session-{n}.err"
        kwargs: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS
                                  else {"start_new_session": True})
        env = clean_env({**self.lab.env, **self.shell_env})
        autopsy.register_workdir(out)  # the session's terminal output is kept if the test fails (G3 H4)
        autopsy.register_workdir(err)
        with out.open("wb") as o, err.open("wb") as e:
            proc = subprocess.Popen([sys.executable, "-m", "aew", "-C", str(self.root), *argv], env=env,
                                    stdin=subprocess.DEVNULL, stdout=o, stderr=e, **kwargs)
        self.lab.sessions.append(proc)  # type: ignore[arg-type]  (the lab kills it at teardown if still running)
        session = Session(proc, out, err, Path(lead_spec["pidfile"]))
        self.typed(step, "aew " + " ".join(argv), argv)
        return session

    def first_words(self, session: Session) -> dict[str, Any] | None:
        """The session's first message (the Lead's status line), or None when the session ended without one."""
        try:
            msg = self.chat.receive(SESSION_START_S, gone=session.ended)
        except Gone:
            if not session.ended():
                self.lead_silent("first words", SESSION_START_S)
            return None
        self.said.append(msg)
        return msg

    def lead_silent(self, waiting_for: str, bound: float) -> None:
        """The Lead's session is alive and said nothing within the bound. Recorded with whose fault it is, only as far
        as the evidence goes (review of #213, G2 and H1): see :func:`silence_fault`."""
        state = lead_state(self.lab)
        events = lead_events(self.lab)
        errors = self.chat.errors[self.chat_errors_at_open:]
        fault, why = silence_fault(chat_errors=errors, events=events, state=state, sent=self.chat.sent,
                                   session=self.session_id)
        mine = [e for e in events if e.get("session") == self.session_id]
        self.ledger.observe("lead_silent", waiting_for=waiting_for, bound_s=bound, fault=fault, why=why,
                            session=self.session_id, chat_errors=errors[-6:], lead_state=state,
                            last_lead_event=mine[-1] if mine else None)

    def say(self, step: str, text: str) -> None:
        self.chat.send({"text": text})
        self.typed(step, text)

    def converse(self, session: Session, *, stop: Callable[[], bool] | None = None) -> dict[str, Any] | None:
        """Answer the Lead until it reports a result or says it is stuck (that message is returned), or the session
        ends, or ``stop`` (an event the test waits for) holds (None)."""
        while True:
            self.check_heads("while the Lead works")
            try:
                msg = self.chat.receive(CONVERSATION_S,
                                        gone=lambda: session.ended() or (stop is not None and stop()))
            except Gone:
                if not session.ended() and not (stop is not None and stop()):
                    self.lead_silent("the conversation", CONVERSATION_S)
                return None
            self.said.append(msg)
            kind = msg.get("type")
            if kind == "ask":
                label = str(msg.get("label"))
                hook = self.on_ask.get(label)
                if hook is not None:
                    hook(msg)
                self.check_heads(f"before answering {label}")
                answer = self.answers.get(label, "yes")
                self.ledger.decision(str(msg.get("text")), answer, label=label, asked_by="lead",
                                     detail=msg.get("detail"))
                if label == "publish" and answer.startswith("y"):
                    self.publish_approved = True
                self.say(f"answer:{label}", answer)
            elif kind == "stuck" and self.cache_workaround(msg):
                continue
            elif kind in ("report", "stuck"):
                if kind == "report":
                    self.reports.append(msg)
                self.check_heads(f"at the Lead's {kind}")
                return msg

    def end_session(self, session: Session, how: str = "exit") -> int | None:
        """``/exit`` in the TUI (the primary way), or the session killed from outside."""
        if how == "exit":
            if not session.ended():
                self.say("exit", "/exit")
        else:
            # The session dies from outside, as when its terminal is closed: Windows, the session's process (its job
            # object then ends the TUI); POSIX, its whole process group (the hangup a closed terminal sends).
            if IS_WINDOWS:
                session.proc.kill()
            else:
                import signal

                os.killpg(session.proc.pid, signal.SIGKILL)
            self.typed("kill", "(the Lead session is killed)")
        try:
            return session.proc.wait(EXIT_S)
        except subprocess.TimeoutExpired:
            return None

    def cache_workaround(self, msg: dict[str, Any]) -> bool:
        """U14's workaround, only after the gate was observed to refuse (the Lead stuck on GATE_UNSATISFIED while the
        check's caches sat untracked in the Ticket's workspace): the operator excludes the caches for every worktree
        (`.git/info/exclude`) and tells the Lead to carry on. Counted as a fallback with its evidence, once."""
        text = str(msg.get("text", ""))
        if self.excluded_caches or "GATE_UNSATISFIED" not in text:
            return False
        caches = sorted({p.name for p in self.root.parent.glob(".aew-workspaces/*/*/**/__pycache__")} |
                        {p.name for p in self.root.parent.glob(".aew-workspaces/*/*/.pytest_cache")})
        if not caches:
            return False
        self.excluded_caches = True
        exclude = self.root / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write("\n" + workers.GITIGNORE)
        self.fallback("caches", "(nothing: the check's own caches should not change its snapshot)", text,
                      "add __pycache__/ and .pytest_cache/ to .git/info/exclude, then tell the Lead to carry on")
        self.typed("caches", "$EDITOR .git/info/exclude  (adds __pycache__/, .pytest_cache/, *.pyc)")
        self.say("caches:ask", "I excluded the test caches from git. Carry on.")
        return True

    # ------------------------------------------------------------------ hard limit: publish needs a decision

    def check_heads(self, when: str) -> None:
        head = git("rev-parse", "main", cwd=self.root)
        if head in self.allowed_heads or self.publish_approved:
            return
        self.ledger.hard_limit("publish_needs_decision", NOT_REFUSED, when=when, head=head,
                               note="main moved before the operator approved a publish")

    def own_commit(self, files: dict[str, str], message: str) -> str:
        """A commit on main that is not AEW's (someone else's change moving the branch)."""
        for rel, text in files.items():
            (self.root / rel).write_text(text, encoding="utf-8", newline="\n")
        git("add", "-A", cwd=self.root)
        git("commit", "-q", "-m", message, cwd=self.root)
        head = git("rev-parse", "main", cwd=self.root)
        self.allowed_heads.add(head)
        return head


# ---------------------------------------------------------------------------------------------- the world


def new_world(tmp: Path, *, gate: Path | None = None, extra: dict[str, str] | None = None) -> HarnessLab:
    """A fresh repository with the sample, and the offline world around it (the fake harness and OpenCode). The
    sample has no `.gitignore` for the check's caches: a fresh project does not, and nothing may hide U14."""
    files = {**workers.SAMPLE, **(extra or {})}
    repo = make_git_repo(tmp / "repo", files)
    scripts = tmp / "fake-scripts"
    (tmp / "sync").mkdir(parents=True, exist_ok=True)
    workers.write_scripts(scripts, gate=gate)
    launcher = write_launcher(scripts / "fake-opencode", scripts)
    # G3 H1: the fake OpenCode and the Lead's TUI it becomes install childdiag from here (periodic stacks, a dying
    # thread's exception, their output teed); the chat, the Lead's events and state are kept if the test fails.
    autopsy.mark_helper_dir(scripts)
    autopsy.register_workdir(tmp / "sync")
    autopsy.register_workdir(scripts)
    env = {"AEW_HARNESS_ADAPTERS": workers.ADAPTER, SCRIPTS_ENV: str(scripts), "AEW_LAUNCH_ACK_S": "120",
           "AEW_OPENCODE_BIN": str(launcher),
           # The product as shipped: a lease's grant starts its custody worker (the suite turns it off by default).
           "AEW_CUSTODY_WORKER": "on"}
    return HarnessLab(Project(repo), tmp, env)


def execution_policy(lab: HarnessLab, *, steering: str | None = None) -> dict[str, Any]:
    """The execution policy a user writes for the offline world (opencode.md's shape, the fake harness's names)."""
    policy: dict[str, Any] = {
        "schema": "aew/execution/v1", "configured": True, "harness": "fake",
        "profiles": {"standard": {"provider": "fakeprov", "model": "fake-model", "effort": "high"}},
        "routing": {"default": "standard", "archetypes": {}, "classes": {}, "cards": {}},
        "provider_env": [],
        # Contained runs (Linux) read their scripts from the offline world's directory: declared writable roots.
        "containment": {"writable": [lab.env[SCRIPTS_ENV], str(lab.tmp / "sync")]},
    }
    if steering:
        policy["steering"] = {"mode": steering}
    return policy


def lead_spec(lab: HarnessLab, *, steering: bool = False) -> dict[str, Any]:
    sync = lab.tmp / "sync"
    return {"driver": "vertical", "chat": str(sync / "chat"), "events": str(sync / "lead-events.jsonl"),
            "state": str(sync / "lead-state.json"),
            "pidfile": str(sync / f"lead-{len(lab.sessions)}.pid"), "draft": workers.DRAFT, "steering": steering}


def lead_events(lab: HarnessLab) -> list[dict[str, Any]]:
    path = lab.tmp / "sync" / "lead-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# Whether `lead_label` reads the Lead's label from the product; `enforce` is refused until it does
# (ledger.enforce_blockers; review of #213, F1). It does since CS-4 (#283) records the Lead session's label.
LEAD_LABEL_WIRED = True


def lead_label(lab: HarnessLab) -> str | None:
    """The Lead sessions' containment label, as the product records it (CS-4, #283): each session's ``label.json``
    beside its ``lead-*`` run directory, and the ``containment`` its ``aew opencode`` answered with when it ended (on
    every platform). The weakest of them; ``None`` when no session recorded one (none started, or each was killed
    before it answered)."""
    labels: list[Any] = []
    runs = runlog.run_dir(lab.aew_root, "x").parent
    for f in sorted(runs.glob("lead-*/label.json")) if runs.is_dir() else []:
        labels.append((json.loads(f.read_text(encoding="utf-8")) or {}).get("filesystem"))
    for out in sorted(Path(lab.tmp).glob("session-*.out")):
        for answer in _json_objects(out.read_text(encoding="utf-8", errors="replace"))[0]:
            if isinstance(answer.get("containment"), dict):
                labels.append(answer["containment"].get("filesystem"))
    if not labels:
        return None
    return min(labels, key=lambda label: LABEL_ORDER.index(label) if label in LABEL_ORDER else -1)


def containment(lab: HarnessLab, ledger: Ledger) -> list[str]:
    """Every harness run's containment label and the Lead's, each at or above this platform's minimum (spec v2)."""
    runs = runlog.run_dir(lab.aew_root, "x").parent
    want = CONTAINMENT_MINIMUM[ledger.platform]
    labels = {}
    for d in sorted(runs.glob("R-*")) if runs.is_dir() else []:
        record = runlog.read_record(d) or {}
        labels[d.name] = (record.get("containment") or {}).get("filesystem")
    lead = lead_label(lab)
    weaker = sorted(r for r, label in labels.items() if not at_least(label, want[WORKERS]))
    if not at_least(lead, want[LEAD]):
        weaker.append(LEAD)
    if not labels:
        ledger.hard_limit("containment", NOT_EXERCISED, minimum=want, lead=lead, note="no harness run was launched")
        return []
    ledger.hard_limit("containment", NOT_REFUSED if weaker else HELD, labels=labels, lead=lead, minimum=want,
                      **({"weaker": weaker} if weaker else {}),
                      **({} if lead else {"lead_note": "no session recorded the Lead's label (none started, or each "
                                                       "was killed before it answered)"}))
    return weaker


# ---------------------------------------------------------------------------------------------- stale attribution


def stage_intents(aew_root: Path) -> dict[str, dict[str, Any]]:
    """Every stage intent the project holds: the archived records (``**/stage-intents/*.yaml``) and the live ones in
    the control state, the live copy winning."""
    import yaml

    found: dict[str, dict[str, Any]] = {}
    for path in sorted(aew_root.glob("**/stage-intents/*.yaml")):
        intent = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if intent.get("id"):
            found[str(intent["id"])] = intent
    control = aew_root / "state" / "control.yaml"
    if control.exists():
        state = yaml.safe_load(control.read_text(encoding="utf-8")) or {}
        found.update({str(k): v for k, v in (state.get("stage_intents") or {}).items() if isinstance(v, dict)})
    return found


def staled_by(record: dict[str, Any], intents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Whose commit ``record`` (a transition) was, through the stage intent it belongs to (review of #213, F5): the
    intent its ``refs`` name (``stage.open`` and the other journal commits name theirs), else the intent that recorded
    a step at its revision. An intent the steering loop ran carries ``auto_run``; any other is the Lead's stage. Only
    when no intent is found does the actor's kind stand in, and a Lead credential then cannot tell the Lead from the
    loop (the loop runs under it), which the attribution says."""
    revision = record.get("revision")
    intent = next((intents[r] for r in record.get("refs") or [] if isinstance(r, str) and r in intents), None)
    if intent is None:
        intent = next((si for si in intents.values() if (si.get("opened") or {}).get("rev") == revision
                       or any(s.get("revision") == revision for s in si.get("steps") or [])), None)
    if intent is not None:
        loop = bool(intent.get("auto_run"))
        return {"by": "the steering loop" if loop else "the Lead", "intent": intent.get("id"), "via": "stage intent",
                "intent_tool": intent.get("tool")}
    actor = record.get("actor")
    kind = actor.get("kind") if isinstance(actor, dict) else actor
    by = ("the Lead's credential, no stage intent (the Lead, or the loop under it)" if kind == "lead"
          else str(kind))
    return {"by": by, "intent": None, "via": "actor"}


# ---------------------------------------------------------------------------------------------- a silent Lead


def lead_state(lab: HarnessLab) -> dict[str, Any] | None:
    """What the scripted Lead last said it was doing (``lead-state.json``), or None when no Lead ever started."""
    path = lab.tmp / "sync" / "lead-state.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def silence_fault(*, chat_errors: list[str], events: list[dict[str, Any]], state: dict[str, Any] | None,
                  sent: int, session: str) -> tuple[str, str]:
    """Whose fault a silent Lead is, from the evidence (review of #213, H1). ``harness`` only with harness evidence:
    a chat read error on either side, or the Lead waiting to hear while an operator message it has not read exists
    (both sides waiting on the chat). Otherwise ``not established``, with what the Lead was doing, so a product hang
    (a call that never returned, no TUI started) reads as one and never as the harness's.

    Only ``session``'s evidence counts (review of #213, I1): its events and its state carry its per-open id, and an
    earlier session's state or ``listener_error`` is ignored. ``chat_errors`` are the operator's since this session
    opened."""
    listener = [e for e in events if e.get("kind") == "listener_error" and e.get("session") == session]
    if state is not None and state.get("session") != session:
        state = None  # an earlier session's: not this one's evidence
    if chat_errors or listener:
        return "harness", f"chat read errors: operator {len(chat_errors)}, Lead {len(listener)}"
    if state is not None and state.get("doing") == "waiting_to_hear" and sent > int(state.get("chat_read") or 0):
        return "harness", (f"the Lead waits to hear, and {sent - int(state.get('chat_read') or 0)} operator "
                           "message(s) it has not read exist")
    if state is None:
        return "not established", "no Lead activity was recorded (no TUI started, or it never reached its policy)"
    if state.get("doing") == "calling":
        call = state.get("tool") or state.get("method")
        return "not established", f"the Lead is in a call that has not returned: {call}"
    return "not established", f"the Lead's last activity: {state.get('doing')}"
