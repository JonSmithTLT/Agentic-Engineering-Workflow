"""The scripted operator of the vertical UAT: only what a human types at a fresh terminal, every input and output kept.

The operator knows what the product's documentation tells a user (``docs/guides/quickstart.md``, ``opencode.md``) and
nothing of AEW's internals. Each step is first attempted the ideal way (the test module's ``IDEAL_PATH``); only when
that attempt is observed to fail does the operator fall back to today's workaround, and every fallback is recorded
with its evidence (the ideal input, what it answered, and what was typed instead). So the ledger stops counting
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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conftest import IS_WINDOWS, CLIResult, Project, clean_env, git, make_git_repo, run_aew
from fake_harness import SCRIPTS_ENV, HarnessLab
from fake_opencode import TUI_SCRIPT, write_launcher

from aew.harness import runlog
from aew.util import dump_yaml
from vertical import workers
from vertical.chat import Gone, Mailbox
from vertical.ledger import CONTAINMENT_MINIMUM, HELD, NOT_REFUSED, Ledger

SESSION_START_S = 300.0
CONVERSATION_S = 1800.0
EXIT_S = 120.0


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
    publish_approved: bool = False
    reports: list[dict[str, Any]] = field(default_factory=list)
    said: list[dict[str, Any]] = field(default_factory=list)
    answers: dict[str, str] = field(default_factory=dict)
    on_ask: dict[str, Callable[[dict[str, Any]], None]] = field(default_factory=dict)
    in_setup: bool = True
    closers: list[Callable[[], None]] = field(default_factory=list)  # in-process terminals the test opened

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

    def open_session(self, step: str, argv: list[str], lead_spec: dict[str, Any]) -> Session:
        scripts = Path(self.lab.env[SCRIPTS_ENV])
        (scripts / TUI_SCRIPT).write_text(json.dumps(lead_spec), encoding="utf-8")
        n = len(self.lab.sessions)
        out, err = self.tmp / f"session-{n}.out", self.tmp / f"session-{n}.err"
        kwargs: dict[str, Any] = ({"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WINDOWS
                                  else {"start_new_session": True})
        env = clean_env({**self.lab.env, **self.shell_env})
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
            return None
        self.said.append(msg)
        return msg

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


def new_world(tmp: Path, *, gitignore: bool = True, gate: Path | None = None) -> HarnessLab:
    """A fresh repository with the sample, and the offline world around it (the fake harness and OpenCode)."""
    files = dict(workers.SAMPLE)
    if gitignore:
        files[".gitignore"] = workers.GITIGNORE
    repo = make_git_repo(tmp / "repo", files)
    scripts = tmp / "fake-scripts"
    (tmp / "sync").mkdir(parents=True, exist_ok=True)
    workers.write_scripts(scripts, gate=gate)
    launcher = write_launcher(scripts / "fake-opencode", scripts)
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
            "pidfile": str(sync / f"lead-{len(lab.sessions)}.pid"), "draft": workers.DRAFT, "steering": steering}


def lead_events(lab: HarnessLab) -> list[dict[str, Any]]:
    path = lab.tmp / "sync" / "lead-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def containment(lab: HarnessLab, ledger: Ledger) -> list[str]:
    """Every harness run's containment label, against today's minimum for this platform."""
    runs = runlog.run_dir(lab.aew_root, "x").parent
    want = CONTAINMENT_MINIMUM[ledger.platform]
    labels = {}
    for d in sorted(runs.glob("R-*")) if runs.is_dir() else []:
        record = runlog.read_record(d) or {}
        labels[d.name] = (record.get("containment") or {}).get("filesystem")
    weaker = sorted(r for r, label in labels.items() if label != want)
    ledger.hard_limit("containment", HELD if labels and not weaker else NOT_REFUSED, labels=labels, minimum=want,
                      note="" if labels else "no harness run recorded a label")
    return weaker

