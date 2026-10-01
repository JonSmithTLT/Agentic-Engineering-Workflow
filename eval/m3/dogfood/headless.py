"""A headless OpenCode V2 session for the dogfood (M3 step 9): evaluation tooling, not product code.

It drives an agent that AEW itself does not launch, the dogfood's **Lead** (``aew-lead``) or the **raw baseline**
(OpenCode's own ``build`` agent), exactly the way the production adapter drives a role run
(:class:`aew.harness.opencode.adapter.OpenCodeAdapter`, which it reuses):

* a private ``serve --stdio`` in its own process tree (a job object on Windows), with private XDG state;
* the provider key only in that server's environment, never in a shell a model can reach;
* the session's shell environment replaced by a curated one (operating-system basics, ``PATH`` with ``aew``, and
  for the Lead the Lead broker's coordinates: never the Lead credential);
* a turn is over only when the REST API says so; a permission request or a form is rejected (nobody is there to
  answer) and recorded;
* usage (tokens, cost, steps, tools, effective model) from the session's own messages.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from aew.harness import agentenv, procs
from aew.harness.opencode import adapter as oc
from aew.harness.opencode import projection
from aew.harness.opencode.client import EventStream, OpenCodeError, OpenCodeUnavailable, Server

TICK_S = 2.0


def shell_env(base: Mapping[str, str], extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of every model-controlled process: the same allowlist as a role's (no provider key)."""
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    env = {k: v for k, v in base.items() if k.upper() in keep or (sys.platform != "win32" and k.startswith("LC_"))}
    aew_bin = os.path.dirname(sys.executable)
    path = [p for p in (base.get("PATH") or base.get("Path") or "").split(os.pathsep) if p]
    env["PATH"] = os.pathsep.join([aew_bin, *[p for p in path if os.path.normcase(p) != os.path.normcase(aew_bin)]])
    env["PYTHONUTF8"] = "1"
    env.update(extra or {})
    return env


AEW_ERROR = re.compile(r'"code":\s*"([A-Z][A-Z_]+)"')
AEW_MESSAGE = re.compile(r'"message":\s*"((?:[^"\\]|\\.)*)"')
FRICTION_CHARS = 300


def _messages(state_dir: Path) -> list[dict[str, Any]]:
    """The session's messages, in order, from its private database (read-only)."""
    import sqlite3

    db = state_dir / "xdg-data" / "opencode" / "opencode.db"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = con.execute("select type, data from session_message order by seq").fetchall()
    finally:
        con.close()
    return [{"type": typ, **json.loads(data)} for typ, data in rows]


def command_log(state_dir: Path) -> list[dict[str, Any]]:
    """What an OpenCode session did, tool by tool, from its private database: the tool, the leading words of a shell
    command (``aew harness wait``, ``git log``), the outcome and the time. For a shell command, also its exit code,
    and for a refused ``aew`` command the AEW error code from its output: the harness's own ``status`` says only that
    the tool ran (M3 audit T3).

    Friction (rubric A5) also keeps the command itself and, for a refused ``aew`` command, the error's message, each
    clipped to 300 characters: for a refused or permission-denied command and for a ``--help`` lookup, never for
    any other call. Nothing else of the input or output is kept."""
    out: list[dict[str, Any]] = []
    for message in _messages(state_dir):
        for part in message.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            state = part.get("state") or {}
            entry: dict[str, Any] = {"tool": part.get("name"), "status": state.get("status")}
            if part.get("name") == "shell":
                command = str((state.get("input") or {}).get("command") or "")
                words = command.split()
                entry["cmd"] = " ".join(words[:3] if words[:1] == ["aew"] else words[:2])
                exit_code = (state.get("metadata") or {}).get("exit")
                if exit_code is not None:
                    entry["exit"] = exit_code
                if exit_code not in (None, 0) and words[:1] == ["aew"]:
                    text = " ".join(str(c.get("text") or "") for c in state.get("content") or [] if isinstance(c, dict))
                    found = AEW_ERROR.search(text)
                    if found:
                        entry["aew_error"] = found.group(1)
                    said = AEW_MESSAGE.search(text)
                    if said:
                        entry["message"] = said.group(1)[:FRICTION_CHARS]
                if exit_code not in (None, 0) or "--help" in words or isinstance(state.get("error"), dict):
                    entry["full"] = command[:FRICTION_CHARS]
            if isinstance(state.get("error"), dict):
                entry["error"] = state["error"].get("type")
            times = part.get("time") or {}
            if times.get("completed") and times.get("ran"):
                entry["s"] = round((times["completed"] - times["ran"]) / 1000, 1)
            out.append(entry)
    return out


def assistant_steps(state_dir: Path) -> int:
    """The session's steps so far, counted as the adapter counts them (one per assistant message)."""
    return sum(1 for m in _messages(state_dir) if m["type"] == "assistant")


def last_text(state_dir: Path, skip: int = 0) -> str:
    """The text of the session's last assistant message that has any (for the debrief, rubric A5 and A6), among
    those after its first ``skip`` steps: a debrief that says nothing must not be credited with an earlier answer."""
    for message in reversed([m for m in _messages(state_dir) if m["type"] == "assistant"][skip:]):
        text = "\n".join(str(p.get("text") or "") for p in message.get("content") or []
                         if isinstance(p, dict) and p.get("type") == "text").strip()
        if text:
            return text
    return ""


def pinned(profile: dict[str, Any]) -> dict[str, Any]:
    return projection.config_model(profile)


GUIDE_POINTER = "- `aew guide` explains how AEW works in this project"


def lead_config(profile: dict[str, Any], steps: int, guide: str = "",
                pointer: bool = True) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """The production Lead projection, made headless: nobody answers, so every ``ask`` is a ``deny`` (the Lead's
    shell runs only ``aew`` and read-only ``git``), and ``question`` is denied.

    ``pointer=False`` also removes the system text's pointer to ``aew guide`` (rubric A5: the Lead with no guide at
    all; A4's before arm kept it, and every one of its Leads ran ``aew guide``)."""
    rules = []
    for r in projection.LEAD_RULES:
        effect = "deny" if r["effect"] == "ask" or r["action"] == "question" else r["effect"]
        rules.append({**r, "effect": effect})
    config = projection.lead_config(guide)  # with the project's Lead guide, as `aew opencode` gives it (F16)
    agent = config["agents"][projection.LEAD_AGENT]
    if not pointer:
        lines = agent["system"].split("\n")
        kept = [line for line in lines if not line.startswith(GUIDE_POINTER)]
        if len(kept) != len(lines) - 1:
            raise RuntimeError("the Lead's system text no longer has exactly one line pointing to `aew guide`")
        agent["system"] = "\n".join(kept)
    agent.update(permissions=rules, model=pinned(profile), steps=steps)
    for name in projection.AUXILIARY_AGENTS:
        config["agents"][name] = {"model": pinned(profile)}
    config.update(snapshots=False, update="disable", plugins=[projection.COMPATIBILITY_PLUGIN], lsp=False,
                  formatter=False, permissions=rules)
    return config, rules


def raw_config(profile: dict[str, Any], steps: int) -> dict[str, Any]:
    """OpenCode's own ``build`` agent with its own system prompt and permissions. The model is pinned and the
    steps bounded; the isolation is the same as AEW's runs (no user configuration or plugins, no LSP or
    formatter downloads)."""
    agents: dict[str, Any] = {"build": {"model": pinned(profile), "steps": steps}}
    for name in projection.AUXILIARY_AGENTS:
        agents[name] = {"model": pinned(profile)}
    return {"share": "disabled", "update": "disable", "plugins": [projection.COMPATIBILITY_PLUGIN], "lsp": False,
            "formatter": False, "agents": agents}


class HeadlessSession(oc.OpenCodeAdapter):
    """One headless session. ``open`` starts it; ``say`` starts a turn; ``wait_turn`` waits for it to end."""

    def __init__(self, state_root: Path) -> None:
        state_root.mkdir(parents=True, exist_ok=True)
        self.events_path = state_root / "events.jsonl"
        super().__init__(procs.ProcessTree(), state_root, self._log)
        self.opened_at: float | None = None
        self.version: str | None = None
        self.model_info: dict[str, Any] = {}
        self.turns: list[dict[str, Any]] = []

    def _log(self, event: dict[str, Any]) -> None:
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": round(time.time(), 3), **event}, default=str) + "\n")

    def _start(self, *, directory: Path, profile: dict[str, Any], config: dict[str, Any],
               provider_env: list[str]) -> None:
        """A private server on this session's state, with the pinned model in its catalog."""
        self.opened_at = time.monotonic()
        self.state_dir = self.run_dir / "harness"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.directory = os.path.realpath(directory)
        server_env = oc.server_env(dict(os.environ), self.state_dir, provider_env=provider_env, config=config,
                                   password=secrets.token_urlsafe(32))
        self.server = Server.start(self.tree.spawn, oc.binary_command(), env=server_env, cwd=self.directory,
                                   log_path=self.state_dir / "server.log")
        del server_env
        self.client = self.server.client
        self.version = (self.client.get("/api/info") or {}).get("version")
        self.model_info = self._await_model(profile)

    def _attach(self, env: dict[str, str]) -> None:
        """The session's shell environment (held only in the server's memory), then its events."""
        assert self.client is not None and self.session is not None
        self.client.put(f"/api/session/{self.session}/environment", {"variables": dict(env)})
        self.events = EventStream(self.client, self._on_event, self.server.alive)
        self.events.start()

    def open(self, *, directory: Path, profile: dict[str, Any], agent: str, config: dict[str, Any],
             env: dict[str, str], provider_env: list[str], rules: list[dict[str, str]] | None = None,
             title: str = "AEW dogfood") -> None:
        self._start(directory=directory, profile=profile, config=config, provider_env=provider_env)
        assert self.client is not None
        body: dict[str, Any] = {"title": title, "agent": agent, "model": projection.model_ref(profile),
                                "location": {"directory": self.directory}}
        if rules is not None:
            body["permissions"] = rules  # applied last: the session's rules win
        self.session = str(self.client.post("/api/session", body)["data"]["id"])
        self._attach(env)
        self._log({"event": "dogfood.opened", "version": self.version, "agent": agent,
                   "model": projection.model_ref(profile), "env_names": sorted(env)})

    def resume(self, *, session: str, directory: Path, profile: dict[str, Any], config: dict[str, Any],
               env: dict[str, str], provider_env: list[str]) -> None:
        """Reopen a session this class ran before, from its saved state (rubric A6: a finished Lead's debrief).
        The session exists already, so nothing is created. Its shell environment lived only in the old server's
        memory, so it is curated again here: without it, the shell would get this server's own environment."""
        self._start(directory=directory, profile=profile, config=config, provider_env=provider_env)
        assert self.client is not None
        self.client.get(f"/api/session/{session}")  # it exists, or this raises
        self.session = session
        self._attach(env)
        self._log({"event": "dogfood.resumed", "version": self.version, "session": session,
                   "model": projection.model_ref(profile), "env_names": sorted(env)})

    def say(self, text: str) -> None:
        """A new turn. The adapter's monitor ends with each turn, so it is restarted for this one.

        A role run's adapter refuses a message to an ended turn, because nothing would watch it (audit I3). This
        session watches every turn it starts, so an ended turn is where its next one begins (a nudge, the debrief)."""
        with self._lock:
            if self.turn == "ended":
                self.turn = "starting"
            self.exit_code, self.detail = None, None
        self.turns.append({"at_s": self.elapsed(), "bytes": len(text.encode("utf-8"))})
        self._prompt(text)
        if self._monitor is None or not self._monitor.is_alive():
            self._stop.clear()
            self._monitor = threading.Thread(target=self._watch, name="dogfood-monitor", daemon=True)
            self._monitor.start()

    def wait_turn(self, deadline: float, tick: Callable[[], str | None] | None = None) -> str:
        """``ended`` (the turn is over), ``deadline``, or whatever ``tick`` returned to stop early."""
        last_tick = 0.0
        while True:
            with self._lock:
                if self.turn == "ended":
                    self.turns[-1].update(ended_s=self.elapsed(), outcome=self.detail)
                    return "ended"
            if time.monotonic() > deadline:
                return "deadline"
            if tick is not None and time.monotonic() - last_tick >= 15:
                last_tick = time.monotonic()
                stop = tick()
                if stop:
                    return stop
            time.sleep(TICK_S)

    def elapsed(self) -> float:
        return round(time.monotonic() - (self.opened_at or time.monotonic()), 1)

    def live_usage(self) -> dict[str, Any]:
        try:
            info = (self.client.get(f"/api/session/{self.session}") or {}).get("data") or {} if self.client else {}
        except (OpenCodeError, OpenCodeUnavailable):
            return {}
        return {"cost": info.get("cost"), "tokens": info.get("tokens")}

    def close(self) -> dict[str, Any]:
        """Stop everything this session started and return what happened (never message text)."""
        if self.client is not None and self.session is not None and self.turn != "ended":
            try:
                self.client.post(f"/api/session/{self.session}/interrupt", params={"resume": "false"})
            except (OpenCodeError, OpenCodeUnavailable):
                pass
        self.snapshot = None  # usage as of now, not as of the last turn's end
        self.terminate()
        self.tree.kill()
        out = self.collect()
        out.update(version=self.version, catalog=self.model_info, wall_s=self.elapsed(), turns=self.turns,
                   last_detail=self.detail, commands=command_log(self.state_dir) if hasattr(self, "state_dir") else [])
        return out
