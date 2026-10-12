"""The scripted Lead of the vertical UAT: a model-free Lead with no AEW knowledge, inside the fake OpenCode TUI.

``aew opencode`` starts the fake TUI (``fake_opencode.tui``) in the Lead session's curated environment; a
``lead-tui.json`` that names this driver runs :func:`main` there. Like OpenCode, it starts the typed surface's MCP
server from the ``mcp`` entry of ``OPENCODE_CONFIG_CONTENT`` (``aew lead mcp``, which forwards to the session's real
Lead broker), and its shell commands run in the TUI's own environment.

**Its whole policy** (docs/implementation/vertical-uat.md, "The Lead"):

1. Read the projection (``status``; ``resume`` once at the start of a session, as its tool description says).
2. If ``decisions_required`` holds a decision the projection gives to the operator, or one whose ``owner`` is not
   stated (every one today), ask the operator and wait for the reply. One whose owner is exactly ``lead`` or
   ``mechanical``, the Lead takes itself and never asks (spec v2: ``decisions_required`` counts operator-owned
   decisions only). Any other stated owner is asked too, and recorded as ``unknown_owner``.
3. Otherwise call the single AVAILABLE action with exactly the arguments the projection supplied. The projection marks
   no action as next today, so a single AVAILABLE action is taken as the next one; when several are AVAILABLE,
   ``ambiguous_next_action`` is recorded and the first in order is taken.
4. When the subject is terminal, report the result to the operator.

**Judgment inputs** (spec v2): where an action, or a decision the projection gives to the Lead or the mechanism,
names ``judgment_inputs``, the Lead supplies them, its own judgment, with nothing asked (never on the operator's
decisions, whose choice is the operator's): a value the projection offers (or the first of its ``options``) goes
into the call's arguments, and the names it carries are recorded. Today's projection names none; projection v2 (A1)
does.

**Where the policy cannot make progress it falls back, and every fallback is counted** (the ledger classifies each
call this driver reports; nothing it does goes unreported). The fallbacks are scripted per known gap, so the run
finishes; they are the only place AEW knowledge appears here:

- ``no_ticket``: an empty project offers no action for the operator's request, so the Lead calls ``ticket_draft``,
  a tool the projection did not offer (``guessed_commands``), with its own proposition and plan (its judgement);
- ``plan_not_accepted``: no decision asks for the proposed plan's approval, so the Lead asks the operator anyway,
  then accepts it from its shell (``shell_aew_calls``), the way the quickstart's ``plan accept`` does;
- ``decision_without_tool``: a decision with no typed tool runs its ``cli_fallback`` from the shell; for
  ``RECONCILE`` (an INTERRUPTED Ticket) the Lead fills in the phase it was interrupted from and a reason;
- ``no_available_action``: nothing AVAILABLE and no decision gets one ``explain`` (``help_calls``), then:
  - ``hint_command``: the command a projection hint names, run from the shell with the subject and the revision filled
    in, and ``--launch`` added once a refusal asks for it (each a counted shell call);
  - ``publish_not_offered``: a prepared candidate whose post-integration verification reported, with no decision
    offered: the Lead asks the operator, then calls ``integration_publish`` (not offered) with the candidate and the
    report it read in its own wait's result;
- ``redispatch``: after a takeover and a reconcile the interrupted implementer is gone, nothing is offered and the
  hint's ``work transition --to RUNNING`` is refused ("no active implementer invocation"): the Lead dispatches a new
  attempt (``invoke create --role implementer --launch``, or ``work redispatch`` for a non-mutating Ticket). A hint
  whose command is refused is also recorded as ``stale_hint`` (evidence about the projection's guidance);
- ``recheck``: the gate still lacks the local check after the operator's own workaround (U14): the Lead relaunches
  the implementer's invocation from its shell, so its check runs again;
- ``decision_refused``: a decision still required after its answer was acted on is never re-asked: one
  ``explain``, its concrete ``cli_fallback`` if it has one (for ``RESOLVE_STAGE``, ``stage continue`` with the Lead's
  own rationale; when that is refused and the refusal names ``abandon``, ``stage abandon`` with the Lead's rationale),
  then stuck;
- ``stuck``: anything else: the Lead tells the operator it is stuck and waits; whatever the operator says next (for
  example after a workaround of their own), it goes on.

**With steering on**, an action the projection marks ``auto_runnable`` is the loop's: the Lead waits for an event
(the revision moves, or the loop records a stop) and pushes it itself, counted, only when the loop declined.

Events go to ``events`` (JSON lines), the Lead's own accounting: with a scripted Lead it is the ground truth for its
calls (spec §4, ``shell_aew_calls``).
"""

from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from vertical.chat import Gone, Mailbox
from vertical.ledger import OPERATOR_OWNER, SELF_OWNERS

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
LOOP_WAIT_S = 120.0  # the bound on waiting for the steering loop's event
POLL_S = 0.25
TERMINAL = frozenset({"DONE", "CANCELLED"})
AVAILABLE = "AVAILABLE"
EXIT = "/exit"
CHAT_TIMEOUT_S = 1800.0
WRITE_TRIES = 20  # a record write retried this many times on an OSError (a sharing violation on Windows), then raised
MCP_ENDED = "the aew-lead MCP server ended"
PROGRESS = ("REVIEW", "VERIFY", "COMMIT_READY", "RUNNING", "READY", "DONE")


class Lead:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        self.steering = bool(spec.get("steering"))
        self.events_path = Path(spec["events"])
        self.lock = threading.Lock()
        self.chat = Mailbox(Path(spec["chat"]), "lead", on_error=self._read_error)
        self.chat.skip_to_end()  # a reopened session answers only what is said to it from now on
        self.inbox: queue.Queue[dict[str, Any]] = queue.Queue()
        self.rid = 0
        self.subject: str | None = None
        self.stale_pending = False
        self.step = "start"
        self.seen: dict[tuple[Any, ...], int] = {}
        self.server: subprocess.Popen[bytes] | None = None
        self.reports: dict[str, str] = {}
        self.last_state: str | None = None
        self.last_projection: dict[str, Any] | None = None
        self.last_out: dict[str, Any] | None = None
        self.operator_acted = False  # the operator spoke after the Lead said it was stuck (a workaround of theirs)
        self.last_refusal = ""  # the last refusal a hint's command met

    # ------------------------------------------------------------------ accounting

    def event(self, kind: str, **facts: Any) -> None:
        if kind in ("gap", "stuck") and self.last_projection is not None:  # what the Lead was shown when it fell back
            facts.setdefault("blockers", [{k: b.get(k) for k in ("code", "message", "details")}
                                          for b in self.last_projection.get("blockers") or []][:8])
            facts.setdefault("hints", list(self.last_projection.get("hints") or [])[:8])
        line = json.dumps({"kind": kind, "step": self.step, "subject": self.subject, **facts}) + "\n"
        with self.lock:
            _retrying(lambda: _append(self.events_path, line))

    def best_effort_event(self, kind: str, **facts: Any) -> None:
        """An event from a path that must not die of recording it (the listener, an exit): ``event`` with its bounded
        retry, and, if the write still fails, the event goes to stderr instead of ending the thread (review of #213,
        H2). It records only the harness's own faults and the exit: no counted call ever goes through here."""
        try:
            self.event(kind, **facts)
        except OSError as exc:
            print(f"vertical lead: could not record {kind}: {exc}: {facts}", file=sys.stderr, flush=True)

    def doing(self, what: str, **facts: Any) -> None:
        """What the Lead is doing now (``lead-state.json``, overwritten): read by the operator when the Lead is silent
        past a bound, to tell a harness fault (both sides waiting on the chat) from a product hang (a call that never
        returned). Best-effort: it is evidence, never a count."""
        path = self.spec.get("state")
        if not path:
            return
        body = json.dumps({"doing": what, "chat_read": self.chat.read, "step": self.step, **facts})
        try:
            _retrying(lambda: _replace(Path(path), body))
        except OSError:
            pass

    # ------------------------------------------------------------------ the operator

    def _read_error(self, path: Path, exc: BaseException) -> None:
        """A chat read failed: recorded (the ledger keeps it as ``lead.listener_error``), then retried by the mailbox
        within its bound. A harness fault is never left to read as AEW's behaviour (review of #213, G2)."""
        self.best_effort_event("listener_error", file=path.name, error=f"{type(exc).__name__}: {exc}"[:300])

    def _listen(self) -> None:
        """Every operator line arrives here; ``/exit`` ends the TUI at once, whatever the Lead is doing (as
        OpenCode's own ``/exit`` does). Nothing ends this thread silently: an unexpected error is recorded as
        ``listener_error`` and the listener goes on, within the chat's bound (review of #213, G2)."""
        deadline = time.monotonic() + CHAT_TIMEOUT_S
        while True:
            try:
                msg = self.chat.receive(max(deadline - time.monotonic(), 0.0))
            except Gone:
                msg = {"text": EXIT, "timeout": True}
            except Exception as exc:  # recorded, never silent; retried within the same bound  # noqa: BLE001
                self.best_effort_event("listener_error", error=f"{type(exc).__name__}: {exc}"[:300])
                time.sleep(POLL_S)
                continue
            deadline = time.monotonic() + CHAT_TIMEOUT_S
            if str(msg.get("text", "")).strip() == EXIT:
                self.best_effort_event("exit", by="operator" if not msg.get("timeout") else "chat timeout")
                with self.lock:
                    if self.server is not None and self.server.stdin is not None:
                        self.server.stdin.close()
                    os._exit(0)
            self.inbox.put(msg)

    def say(self, kind: str, **body: Any) -> None:
        self.chat.send({"type": kind, **body})

    def hear(self) -> dict[str, Any]:
        self.doing("waiting_to_hear")
        msg = self.inbox.get(timeout=CHAT_TIMEOUT_S)
        self.doing("working")
        return msg

    def ask(self, question: str, *, label: str, detail: Any = None) -> str:
        self.say("ask", text=question, label=label, detail=detail)
        answer = str(self.hear().get("text", ""))
        self.event("asked", label=label, question=question, answer=answer)
        return answer

    # ------------------------------------------------------------------ the typed surface (MCP)

    def start_mcp(self) -> list[str]:
        config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
        server = next(iter(config["mcp"]["servers"].values()))
        argv = list(server["command"])
        argv[0] = shutil.which(argv[0], path=os.environ.get("PATH")) or argv[0]  # as OpenCode resolves it
        self.server = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       creationflags=NO_WINDOW)
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "vertical-lead", "version": "1"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return [t["name"] for t in self._rpc("tools/list", {})["result"]["tools"]]

    def _send(self, message: dict[str, Any]) -> None:
        assert self.server is not None and self.server.stdin is not None
        self.server.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.server.stdin.flush()

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert self.server is not None and self.server.stdout is not None
        self.rid += 1
        rid = self.rid
        self.doing("calling", method=method, tool=params.get("name"))
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = self.server.stdout.readline()
            if not line:
                raise RuntimeError(MCP_ENDED)
            reply = json.loads(line)
            if reply.get("id") == rid:
                return reply

    def call(self, tool: str, arguments: dict[str, Any], *, offered: bool = False, mechanical: bool = False,
             why: str = "") -> dict[str, Any]:
        if self.stale_pending:
            self.event("stale_retry", evidence={"tool": tool})
            self.stale_pending = False
        reply = self._rpc("tools/call", {"name": tool, "arguments": arguments})
        if "error" in reply:  # an input error: never reached the engine
            err = reply["error"]
            self.event("call", via="mcp", tool=tool, arguments=arguments, offered=offered, mechanical=mechanical,
                       why=why, ok=False, stopped={"error": (err.get("data") or {}).get("adapter_input_error")
                                                   or {"code": err.get("code"), "message": err.get("message")}})
            return {"ok": False, "projection": None, "result": None, "stopped": {"error": err}}
        out = reply["result"]["structuredContent"]
        stopped = out.get("stopped")
        if out.get("projection"):
            self.last_projection = out["projection"]
        self.event("call", via="mcp", tool=tool, arguments=arguments, offered=offered, mechanical=mechanical, why=why,
                   ok=out.get("ok"), stopped=stopped,
                   completed=[s.get("primitive") for s in out.get("completed_steps") or []],
                   said=_said(out) if tool not in ("status", "resume") else None)
        if stopped and (stopped.get("error") or {}).get("code") == "STALE_REVISION":
            self.stale_pending = True
        if tool == "harness_wait":  # what the Lead read in its own wait's result: the reports a run recorded
            for found in re.findall(r"INV-\d+-verify-\d+", json.dumps(out.get("result"))):
                scope = "integration" if (self.last_state or "") == "COMMIT_READY" else "ticket"
                self.reports[f"verification:{scope}"] = found
        return out

    def shell(self, argv: list[str], *, why: str, stdin: str | None = None) -> dict[str, Any]:
        """``aew`` from the Lead's own shell, in the TUI's environment (it reaches the session's broker)."""
        if self.stale_pending:
            self.event("stale_retry", evidence={"shell": argv})
            self.stale_pending = False
        exe = shutil.which("aew", path=os.environ.get("PATH"))
        cmd = [exe] if exe else [sys.executable, "-m", "aew"]
        proc = subprocess.run([*cmd, *argv], input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=NO_WINDOW,
                              **({} if stdin is not None else {"stdin": subprocess.DEVNULL}))
        error = None
        if proc.returncode:
            try:
                error = json.loads(proc.stderr)["error"]
            except (ValueError, KeyError, TypeError):
                error = None
            if not error:  # an `ok: false` answer carries its stop in the stdout JSON, with nothing on stderr
                try:
                    body = json.loads(proc.stdout)
                    error = ((body.get("stopped") or {}).get("error") or body.get("error")) if isinstance(
                        body, dict) else None
                except ValueError:
                    error = None
            if not error:
                error = {"code": None, "message": (proc.stderr.strip() or proc.stdout.strip())[-400:]}
        self.event("call", via="shell", tool="aew", arguments=argv, why=why, ok=proc.returncode == 0,
                   stopped={"error": error} if error else None)
        if error and error.get("code") == "STALE_REVISION":
            self.stale_pending = True
        try:
            return {"ok": proc.returncode == 0, "json": json.loads(proc.stdout), "error": error}
        except ValueError:
            return {"ok": proc.returncode == 0, "json": None, "error": error, "stdout": proc.stdout[-400:]}

    # ------------------------------------------------------------------ the policy

    def run(self) -> None:
        """The session: it ends only when the operator types ``/exit`` (the listener ends the process) or the chat
        goes silent past its bound."""
        Path(self.spec["pidfile"]).write_text(str(os.getpid()), encoding="utf-8")
        self.tools = self.start_mcp()
        threading.Thread(target=self._listen, daemon=True, name="vertical-chat").start()
        resumed = self.call("resume", {})
        self.say("status", words=_words(resumed.get("result")), session="started")
        self.subject = _open_ticket(resumed.get("result"))
        self.request = str(self.hear().get("text", ""))  # the operator's first line
        self.event("heard", text=self.request)
        budget = int(self.spec.get("max_steps") or 150)
        while True:  # the session stays open until the operator ends it
            for _ in range(budget):
                if not self.tick():
                    break
            else:
                self.stuck("the step budget ran out")
            heard = self.hear()  # after a result or a stop: whatever the operator says next; then the Lead goes on
            self.event("heard", text=str(heard.get("text", "")))
            self.seen.clear()
            self.operator_acted = True
            budget = 40

    def read(self) -> dict[str, Any]:
        out = self.call("status", {"work_id": self.subject} if self.subject else {})
        return out

    def tick(self) -> bool:
        out = self.read()
        self.last_out = out
        proj = out.get("projection") or {}
        if self.subject is None:
            ticket = _open_ticket(self.call("resume", {}).get("result"))
            if ticket is None:
                return self.gap_no_ticket(proj)
            self.subject = ticket
            return True
        state = proj.get("state")
        self.last_state = state
        self.step = f"{self.subject}:{state}"
        if state in TERMINAL:
            self.report(out)
            return False
        decisions = proj.get("decisions_required") or []
        for d in decisions:  # a decision the projection gives to the Lead or the mechanism is never asked (spec v2)
            if d.get("owner") in SELF_OWNERS:
                return self.own_decision(d)
        if decisions:
            return self.decide(decisions[0], proj)
        offered = [a for a in proj.get("actions") or [] if a.get("availability") == AVAILABLE and a.get("callable")]
        if len(offered) > 1:
            self.event("ambiguous", available=[a["action"] for a in offered])
        if offered:
            a = offered[0]
            if self.steering and a.get("auto_runnable") and self.loop_acts(proj):
                return True  # the loop did it: nothing for the Lead to push
            mechanical = a.get("kind") == "wait" or bool(a.get("auto_runnable"))
            self.call(a["action"], self.judged(a, a["arguments"]), offered=True, mechanical=mechanical)
            return True
        return self.gap(out, proj)

    def loop_acts(self, proj: dict[str, Any]) -> bool:
        """Steering on: an action the projection marks ``auto_runnable`` is the loop's to run. The Lead waits for an
        event: the revision moves (the loop acted: True), or the loop has recorded a stop at this projection's revision
        or later (it will not act: False, and the Lead pushes it, counted; the stop's code is recorded). A stop recorded
        before the Lead looked counts too, so the bound only covers a loop that is genuinely silent."""
        rev = int(proj.get("revision") or 0)
        deadline = time.monotonic() + LOOP_WAIT_S
        while time.monotonic() < deadline:
            out = self.call("status", {})
            loop = _loop(out.get("result"))
            if (out.get("projection") or {}).get("revision") != rev:
                return True
            stop = loop.get("stop") or {}
            if loop.get("status") != "running" and int(stop.get("revision") or -1) >= rev:
                self.event("loop_declined", stop=stop)
                return False
            time.sleep(POLL_S)
        self.event("loop_declined", stop=None, why=f"no loop event within {LOOP_WAIT_S:.0f}s")
        return False

    def decide(self, d: dict[str, Any], proj: dict[str, Any]) -> bool:
        asked = ("decision", d["decision"], tuple(d.get("evidence") or []))
        if self.seen.get(asked):  # answered already and still required: never re-asked, the fallback ladder instead
            return self.decision_refused(d, proj)
        self.seen[asked] = 1
        label = "publish" if d["decision"] == "PUBLISH" else d["decision"].lower()
        if d.get("owner") not in (None, OPERATOR_OWNER):  # neither the operator's nor one the Lead takes: asked
            self.event("unknown_owner", decision=d["decision"], owner=d.get("owner"))  # and recorded as a finding
        question = (f"{d['decision'].replace('_', ' ').lower()} for {d.get('subject')}"
                    + (f" (evidence {', '.join(d.get('evidence') or [])})" if d.get("evidence") else "") + "?")
        answer = self.ask(question, label=label, detail={"decision": d["decision"], "tool": d.get("tool"),
                                                          "owner": d.get("owner")})
        if not answer.lower().startswith(("y", "approve", "ok", "go")):
            self.say("holding", text=f"holding: {question}")
            self.hear()
            return True
        if d.get("tool") and d.get("arguments") is not None and d["tool"] in self.tools:
            # The operator's decision: its arguments as the projection supplied them, never a choice the Lead filled
            # (judgment inputs are the Lead's, for actions and its own decisions only; review of #213, F3).
            self.call(d["tool"], d["arguments"], offered=True)
            return True
        cli = list(d.get("cli_fallback") or [])
        if d["decision"] == "RECONCILE" and "<phase>" in cli:
            # The known gap: an INTERRUPTED Ticket is reconciled to the phase it was interrupted from, with a reason,
            # as the quickstart's "Losing the session" says (the Lead's AEW knowledge, counted with the shell call).
            phase = _unit((self.last_out or {}).get("result")).get("interrupted_from")
            self.event("gap", gap="reconcile", why="an INTERRUPTED Ticket: its decision has no typed tool")
            cli = [str(phase) if x == "<phase>" else x for x in cli]
            cli += ["--reason", "workspace inspected after the session was taken over"]
        if not cli or any(x.startswith("<") or "{" in x for x in cli):
            return self.stuck(f"decision {d['decision']} has no typed tool and its fallback needs a choice: {cli}")
        self.event("gap", gap="decision_without_tool", decision=d["decision"])
        self.shell(cli, why=f"decision {d['decision']} has no typed tool")
        return True

    def judged(self, item: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
        """The call's arguments with the Lead's own judgments supplied where the projection names ``judgment_inputs``
        (spec v2). A mapping offers a value per argument (or ``options`` to choose from: the Lead takes the first);
        it fills only what the projection's arguments leave out. A list names the judgments the complete arguments
        carry. Either way the names are recorded as the Lead's, never asked of the operator."""
        inputs = item.get("judgment_inputs")
        if not inputs:
            return arguments
        out = dict(arguments)
        if isinstance(inputs, dict):
            for name, offer in inputs.items():
                if isinstance(offer, dict) and offer.get("options"):
                    offer = offer["options"][0]
                elif isinstance(offer, dict) and "value" in offer:
                    offer = offer["value"]
                out.setdefault(str(name), offer)
        self.event("judgment", tool=item.get("action") or item.get("tool"),
                   inputs=sorted(map(str, inputs)) if isinstance(inputs, (dict, list)) else inputs)
        return out

    def own_decision(self, d: dict[str, Any]) -> bool:
        """A decision the projection gives to the Lead (or the mechanism): the Lead takes it itself, with its
        judgment inputs supplied, and never asks the operator. Recorded apart from the operator's decisions."""
        asked = ("own", d.get("decision"), tuple(d.get("evidence") or []))
        if self.seen.get(asked):
            return self.decision_refused(d, self.last_projection or {})
        self.seen[asked] = 1
        self.event("own_decision", decision=d.get("decision"), owner=d.get("owner"), tool=d.get("tool"))
        if d.get("tool") and d.get("arguments") is not None and d["tool"] in self.tools:
            self.call(d["tool"], self.judged(d, d["arguments"]), offered=True)
            return True
        return self.stuck(f"decision {d.get('decision')} is the {d.get('owner')}'s and offers no typed call")

    def decision_refused(self, d: dict[str, Any], proj: dict[str, Any]) -> bool:
        """A decision still required after its answer was acted on (its call refused): one ``explain``, then its
        ``cli_fallback`` when it is concrete, then stuck. Each step counted, none repeated."""
        rung = ("refused", d["decision"], tuple(d.get("evidence") or []))
        step = self.seen.get(rung, 0)
        self.seen[rung] = step + 1
        if step == 0:
            self.event("gap", gap="decision_refused", decision=d["decision"])
            self.call("explain", {"work_id": self.subject}, why=f"decision {d['decision']} still required")
            return True
        cli = list(d.get("cli_fallback") or [])
        if step == 1 and d["decision"] == "RESOLVE_STAGE":
            # The known gap: an unfinished stage (often the steering loop's, or one a lost session left) whose typed
            # call lacks the choice and rationale. The Lead continues it with its own rationale, from the shell, as
            # the decision's command names (`aew stage continue <intent> --rationale ... --expect-rev N`).
            self.event("gap", gap="resolve_stage", why="the stage's typed resolution was refused; its command needs a "
                                                        "choice and a rationale")
            cli = [("continue" if x == "<continue|abandon>" else
                    "the stage's work is still wanted; continue it" if x == "<why>" else x) for x in cli]
        if step == 1 and cli and not any(x.startswith("<") or "{" in x for x in cli):
            out = self.shell(cli, why=f"decision {d['decision']} still required: its cli_fallback")
            if not out["ok"]:
                self.follow_refusal(cli, out.get("error") or {})
            return True
        return self.stuck(f"decision {d['decision']} is still required after it was answered and acted on")

    def follow_refusal(self, argv: list[str], error: dict[str, Any]) -> None:
        """A shell fallback was refused and the refusal names the step to take instead: the Lead takes it, counted.
        Today's known case: continuing a stage whose subject moved (after a takeover) is refused with "Abandon it
        (committed steps stand) and decide anew from the projection", so the Lead abandons the stage with its own
        rationale and goes on from the projection (which then offers what the moved subject needs, e.g. RECONCILE)."""
        message = str(error.get("message") or "")
        if argv[:2] == ["stage", "continue"] and "abandon" in message.lower():
            self.event("gap", gap="refusal_names_a_step", why=message[:300], code=error.get("code"))
            rev = self.call("status", {"work_id": self.subject}).get("revision")
            self.shell(["stage", "abandon", argv[2], "--rationale",
                        "the refusal says the stage's subject moved: abandon it and decide anew from the projection",
                        "--expect-rev", str(rev)], why="the refusal names abandon as the step to take")

    # ------------------------------------------------------------------ the counted fallbacks

    def gap_no_ticket(self, proj: dict[str, Any]) -> bool:
        if self.seen.get(("no_ticket",)):
            return self.stuck("ticket_draft did not create a Ticket")
        self.seen[("no_ticket",)] = 1
        self.event("gap", gap="no_ticket", why="the project's projection offers no action for the operator's request")
        draft = dict(self.spec["draft"])
        args = {"expect_rev": proj.get("revision"), **draft}
        out = self.call("ticket_draft", args, why="no_ticket")
        found = (out.get("projection") or {}).get("subject")
        if out.get("ok") and found and found != "project":
            self.subject = found
        return True

    def gap(self, out: dict[str, Any], proj: dict[str, Any]) -> bool:
        key = (proj.get("revision"), proj.get("state"),
               tuple((a.get("action"), a.get("availability")) for a in proj.get("actions") or []))
        self.seen[key] = self.seen.get(key, 0) + 1
        unit = _unit(out.get("result"))
        plans = unit.get("plans") or []
        accepted = unit.get("accepted_plan")
        proposed = [p for p in plans if str(p.get("status")) == "proposed"]
        if proposed and not accepted and self.seen[key] == 1:
            return self.gap_plan(proposed[-1], proj)
        unmet = [b for b in proj.get("blockers") or [] if b.get("code") == "GATE_UNSATISFIED"
                 and "local_checks" in ((b.get("details") or {}).get("unmet") or {})]
        if unmet and self.operator_acted:
            return self.gap_recheck(proj)
        if self.seen[key] == 1:
            self.event("gap", gap="no_available_action", why="no decision and no AVAILABLE action")
            self.call("explain", {"work_id": self.subject}, why="no AVAILABLE action")
            return True
        hinted = self.hinted_command(proj)
        if hinted is not None and self.seen[key] == 2:
            return self.gap_hint(hinted, proj)
        if "no active implementer invocation" in self.last_refusal and not self.seen.get(("redispatch",)):
            return self.gap_redispatch(unit, proj)
        candidate = (unit.get("integration") or {}).get("candidate")
        if proj.get("state") == "COMMIT_READY" and candidate and self.seen[key] <= 3 and not self.seen.get(("pub",)):
            return self.gap_publish(str(candidate), proj)
        return self.stuck(f"no decision and no AVAILABLE action at {proj.get('state')}: "
                          + "; ".join(f"{a.get('action')} {a.get('availability')} {a.get('reason_codes')}"
                                      for a in proj.get("actions") or []))

    def hinted_command(self, proj: dict[str, Any]) -> list[str] | None:
        """The first `aew ...` command a hint of the projection names (hints are for a reader: the Lead reads them)."""
        for hint in proj.get("hints") or []:
            for quoted in re.findall(r"`aew ([^`]+)`", str(hint)):
                return shlex.split(quoted)
        return None

    def gap_hint(self, argv: list[str], proj: dict[str, Any]) -> bool:
        """Run the command a hint names from the shell, completed the way the Lead learns to: the subject after the
        command's words, the revision, and ``--launch`` once a refusal asks for it (each a counted call)."""
        self.event("gap", gap="hint_command", why="the projection offers nothing; a hint names a command",
                   hint=argv)
        words = [a for a in argv if not a.startswith("-")]
        if str(self.subject) not in argv:
            at = argv.index(words[1]) + 1 if len(words) > 1 else len(argv)
            argv = [*argv[:at], str(self.subject), *argv[at:]]
        if "--expect-rev" in argv:  # a placeholder (`N`) in the hint: the Lead fills in the revision it read
            at = argv.index("--expect-rev")
            argv = [*argv[:at], *argv[at + 2:]]
        argv = [*argv, "--expect-rev", str(proj.get("revision"))]
        out = self.shell(argv, why="hint_command")
        message = str((out.get("error") or {}).get("message") or "")
        if not out["ok"] and "unrecognized arguments" not in message and "--launch" not in message:
            # The product's own hint led to a refusal: evidence for the projection's guidance, kept in the ledger.
            self.event("stale_hint", hint=argv, refusal=out.get("error"))
            self.last_refusal = message
        if not out["ok"] and "unrecognized arguments: --expect-rev" in message:  # a read command takes none
            self.shell(argv[:-2], why="hint_command: the usage error refused --expect-rev")
        elif not out["ok"] and "--launch" in message:
            rev = self.call("status", {"work_id": self.subject}).get("revision")
            argv = [*argv[:-2], "--launch", "--expect-rev", str(rev)]
            self.shell(argv, why="hint_command: the refusal asked for --launch")
        return True

    def gap_redispatch(self, unit: dict[str, Any], proj: dict[str, Any]) -> bool:
        """After a takeover and a reconcile, the interrupted implementer is gone and nothing is offered: the Lead
        dispatches a new attempt the way the quickstart's "Losing the session" documents it (`invoke create --role
        implementer --launch` for a mutating Ticket, `work redispatch --launch` for a non-mutating one). Counted."""
        self.seen[("redispatch",)] = 1
        self.last_refusal = ""
        self.event("gap", gap="redispatch", why="no active implementer invocation, and nothing offered")
        rev = str(proj.get("revision"))
        if unit.get("mutating", True):
            argv = ["invoke", "create", str(self.subject), "--role", "implementer", "--launch", "--expect-rev", rev]
        else:
            argv = ["work", "redispatch", str(self.subject), "--reason", "the interrupted attempt is gone",
                    "--launch", "--expect-rev", rev]
        self.shell(argv, why="redispatch: a new attempt after the interrupted one")
        return True

    def gap_publish(self, candidate: str, proj: dict[str, Any]) -> bool:
        """A prepared candidate whose post-integration verification has reported, with no decision offered: the Lead
        asks the operator to publish, then calls ``integration_publish`` (not offered) with the candidate and the
        integration verifier's report it saw in its own wait's result."""
        self.seen[("pub",)] = 1
        self.event("gap", gap="publish_not_offered", why="a prepared candidate, its verification reported, and no "
                   "decision offered")
        report = self.reports.get("verification:integration")
        answer = self.ask(f"publish the prepared change of {self.subject}?", label="publish",
                          detail={"decision": None, "gap": "publish_not_offered", "tool": "integration_publish"})
        if not answer.lower().startswith(("y", "approve", "ok", "go")):
            return self.stuck("the operator did not approve the publish")
        args = {"expect_rev": proj.get("revision"), "work_id": self.subject, "prepared_candidate": candidate,
                **({"verification_evidence": report} if report else {})}
        self.call("integration_publish", args, why="publish_not_offered")
        return True

    def gap_recheck(self, proj: dict[str, Any]) -> bool:
        """The gate still lacks the local check after the operator's own workaround: the Lead relaunches the
        implementer's invocation so its check runs again (`aew harness launch`, the quickstart's relaunch; counted)."""
        self.operator_acted = False
        runs = [r for r in proj.get("runs") or [] if r.get("role") == "implementer"]
        if not runs:
            return self.stuck("the local check is missing and no implementer run is known to relaunch")
        self.event("gap", gap="recheck", why="local_checks unmet after the operator's workaround")
        self.shell(["harness", "launch", runs[-1]["invocation"], "--expect-rev", str(proj.get("revision"))],
                   why="recheck: relaunch the implementer so its check runs again")
        return True

    def gap_plan(self, plan: dict[str, Any], proj: dict[str, Any]) -> bool:
        self.event("gap", gap="plan_not_accepted", why="no decision asks for the proposed plan's approval")
        number = plan.get("revision") or plan.get("revision_number") or 1
        body = plan.get("body") or self.spec["draft"]["plan"]["body"]
        answer = self.ask(f"approve the plan for {self.subject}?\n\n{body}", label="plan",
                          detail={"decision": None, "gap": "plan_not_accepted", "tool": "aew plan accept (shell)"})
        if not answer.lower().startswith(("y", "approve", "ok")):
            return self.stuck("the operator did not approve the plan")
        self.shell(["plan", "accept", str(self.subject), "--revision", str(number), "--expect-rev",
                    str(proj.get("revision"))], why="plan_not_accepted")
        return True

    def stuck(self, why: str) -> bool:
        self.event("stuck", why=why)
        self.say("stuck", text=f"I cannot make progress: {why}")
        return False

    def report(self, out: dict[str, Any]) -> None:
        unit = _unit(out.get("result"))
        commit = (unit.get("integration") or {}).get("commit") or _find(out.get("result"), "integrated_commit")
        diff = ""
        if commit:
            # The published commit against main's previous tip (its first parent): the change the operator gets.
            proc = subprocess.run(["git", "diff", "--stat", "-p", f"{commit}^1", str(commit)], capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW,
                                  stdin=subprocess.DEVNULL)
            diff = proc.stdout
        evidence = [{"kind": e.get("kind"), "id": e.get("id")} for e in unit.get("evidence") or []]
        self.say("report", state=(out.get("projection") or {}).get("state"), commit=commit, diff=diff,
                 evidence=evidence)


# ---------------------------------------------------------------------------------------------- reading results

def _said(out: dict[str, Any]) -> str:
    """What a result told the Lead in words: its refusal, the text in its result, and its projection's hints and
    blockers (bounded)."""
    parts = [str(((out.get("stopped") or {}).get("error") or {}).get("message") or "")]

    def texts(value: Any) -> None:
        if isinstance(value, str) and " " in value:
            parts.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                texts(v)
        elif isinstance(value, list):
            for v in value:
                texts(v)

    texts(out.get("result"))
    proj = out.get("projection") or {}
    parts += [str(h) for h in proj.get("hints") or []]
    parts += [str(b.get("message")) for b in proj.get("blockers") or []]
    return "\n".join(p for p in parts if p)[:4000]


def _loop(result: Any) -> dict[str, Any]:
    """The steering loop's state as the project's status reports it."""
    return dict((((result or {}).get("steering") or {}).get("loop")) or {})


def _unit(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    for key in ("control", "work_unit"):
        if isinstance(result.get(key), dict):
            return result[key]
    return result


def _find(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if value.get(key):
            return value[key]
        for v in value.values():
            found = _find(v, key)
            if found:
                return found
    if isinstance(value, list):
        for v in value:
            found = _find(v, key)
            if found:
                return found
    return None


def _open_ticket(result: Any) -> str | None:
    for w in (result or {}).get("work") or []:
        if w.get("kind") == "ticket" and w.get("state") not in TERMINAL:
            return str(w["id"])
    return None


def _words(result: Any) -> str | None:
    """What the resume says in words, if it says anything that is not a data field (a headline or a summary)."""
    for key in ("headline", "summary", "message", "where_things_stand"):
        if isinstance((result or {}).get(key), str):
            return result[key]
    return None


def _append(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _replace(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _retrying(write: Any) -> None:
    """A record write, retried on an OSError within a bound (WRITE_TRIES polls), then raised."""
    for attempt in range(WRITE_TRIES):
        try:
            write()
            return
        except OSError:
            if attempt == WRITE_TRIES - 1:
                raise
            time.sleep(POLL_S)


def classify(exc: BaseException) -> str:
    """Whose fault ended the Lead: the aew-lead MCP server ending is the product's (AEW's broker or its MCP server);
    anything else is not established here (a bug in this script, or AEW answering what it did not expect)."""
    return "product" if isinstance(exc, RuntimeError) and str(exc) == MCP_ENDED else "not established"


def main(spec_path: Path) -> int:
    """The scripted Lead's session. Nothing ends it without a record (review of #213, H2): an exception in its main
    thread is recorded as ``lead_error`` with the step it was on and whose fault it is, then the session ends."""
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    lead = Lead(spec)
    try:
        lead.run()
    except Exception as exc:  # recorded, never silent  # noqa: BLE001
        lead.best_effort_event("lead_error", error=f"{type(exc).__name__}: {exc}"[:400], fault=classify(exc))
        return 1
    return 0
