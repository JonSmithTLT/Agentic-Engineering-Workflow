"""The OpenCode V2 adapter (ADR-0009; docs/archive/milestones/m3-opencode-v2-rebaseline.md).

One adapter serves one run, inside the run's supervisor:

1. **Private server.** ``opencode-cli serve --stdio`` inside the run's process tree, with private XDG
   state under ``<run>/harness/`` (sessions, database, shell output: all disposable), the run's
   projection as ``OPENCODE_CONFIG_CONTENT``, project configuration off, and a server environment built
   from an allowlist plus the provider variables the execution policy names.
2. **Health**, against that server: version, the capability probe of its own ``/openapi.json``
   (:mod:`.capabilities`), and the pinned ``provider/model#effort`` in its model catalog. The catalog
   loads asynchronously, so it is polled; a model or variant that never appears fails closed.
3. **Session** with the pinned model, the workspace (as a long path) and the complete permission set;
   its shell environment is then **replaced** by the curated agent environment (no AEW credential, no
   provider secret, no server password). The launch contract is the first prompt.
4. **Watching.** The turn is over only when the REST API says so: the session is not active, the last
   prompt AEW sent has been delivered, the newest message is an ``idle`` after it, AEW's prompts are no
   longer queued, and all of that holds on two consecutive polls. The event stream only wakes the poll
   and feeds telemetry; losing it changes nothing. A permission request or form is never expected (every
   rule is allow or deny): it is rejected or cancelled and recorded.

Nothing the adapter reports is evidence. Effective model and usage come from the session's assistant
messages (non-authoritative telemetry that the supervisor compares with the pin).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from aew.errors import HarnessError, HarnessIncompatible
from aew.harness import agentenv
from aew.harness import usage as U
from aew.harness.base import HarnessAdapter
from aew.harness.contract import CREDENTIAL_RE, LaunchContract
from aew.harness.opencode import capabilities, projection
from aew.harness.opencode.client import Client, EventStream, OpenCodeError, OpenCodeUnavailable, Server, location

BIN_ENV = "AEW_OPENCODE_BIN"
POLL_S = 1.0
PAGES = 100  # at most this many pages of 200 messages are read for a run's snapshot (more: `truncated`)
CATALOG_WAIT_S = float(os.environ.get("AEW_OPENCODE_CATALOG_S", "90"))
CATALOG_SETTLE_S = float(os.environ.get("AEW_OPENCODE_CATALOG_SETTLE_S", "20"))
EXIT_CODES = {"succeeded": 0, "failed": 1, "interrupted": 2}
CREDENTIALS = "/api/credential"  # 2.0.22+: stored integration credentials, values included
LOGGED_EVENTS = frozenset({
    "session.created", "session.execution.started", "session.execution.succeeded", "session.execution.failed",
    "session.execution.interrupted", "session.step.started", "session.step.ended", "session.step.failed",
    "session.tool.called", "session.tool.failed", "session.inbox.enqueued", "session.inbox.delivered",
    "permission.asked", "permission.replied",
})


def default_binary() -> Path | None:
    """The pinned CLI: OpenCode Desktop's version-specific copy on Windows, else ``opencode-cli`` on PATH."""
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        pinned = Path(os.environ["APPDATA"], "ai.opencode.desktop", "cli", capabilities.TESTED_VERSIONS[0],
                      "opencode-cli.exe")
        if pinned.exists():
            return pinned
    found = shutil.which("opencode-cli") or shutil.which("opencode")
    return Path(found) if found else None


def binary_command() -> list[str]:
    configured = os.environ.get(BIN_ENV)
    path = Path(configured) if configured else default_binary()
    if path is None or not path.exists():
        raise HarnessIncompatible(f"no OpenCode binary: set {BIN_ENV} to the OpenCode CLI "
                                  f"(tested: {', '.join(capabilities.TESTED_VERSIONS)})",
                                  looked_for=str(path) if path else None)
    return [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]


def server_env(base: dict[str, str], state_dir: Path, *, provider_env: list[str], config: dict[str, Any],
               password: str) -> dict[str, str]:
    """The server's environment: operating-system basics, the provider variables the execution policy names,
    and private OpenCode state. Nothing else from the Lead's environment reaches OpenCode."""
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    # SHELL: OpenCode picks the agent's shell from it (else PowerShell on Windows), as for the operator's own use.
    env = {k: v for k, v in base.items() if k.upper() in keep or k.upper() in ("PATH", "SHELL")
           or (sys.platform != "win32" and k.startswith("LC_"))}
    for name in provider_env:
        value = base.get(name)
        if value and not name.upper().startswith("AEW_") and not CREDENTIAL_RE.search(value):
            env[name] = value
    for kind in ("config", "data", "state", "cache"):
        directory = state_dir / f"xdg-{kind}"
        directory.mkdir(parents=True, exist_ok=True)
        env[f"XDG_{kind.upper()}_HOME"] = str(directory)
    tmp = state_dir / "tmp"
    tmp.mkdir(exist_ok=True)
    env.update({"TEMP": str(tmp), "TMP": str(tmp), "TMPDIR": str(tmp),
                "OPENCODE_CONFIG_CONTENT": json.dumps(config, sort_keys=True),
                "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_AUTOUPDATE": "1",
                "OPENCODE_PASSWORD": password})
    return env


def new_message_id() -> str:
    return "msg_" + secrets.token_hex(12)


class OpenCodeAdapter(HarnessAdapter):
    name = "opencode"
    # How each provider's reported counters overlap, per qualified OpenCode version (F25, cost and usage ledger v0.2
    # R4 rule 1), pinned by tests/unit/test_usage_conformance.py against the fixture
    # tests/fixtures/opencode/usage-2.0.18-openai.json.
    # A provider not named here is `unknown` and is never priced: no other provider is inferred (register F25).
    #
    # 2.0.18 / openai -> disjoint, qualified from source (sst/opencode tag v2.0.18, commit
    # cd9a14a6b688d4021bee381dfd39d2cef9c0f862):
    # - packages/core/src/session/usage.ts:11-19 stores input = nonCachedInputTokens, output = visibleOutputTokens,
    #   reasoning = reasoningTokens, cache.read = cacheReadInputTokens, cache.write = cacheWriteInputTokens;
    # - packages/ai/src/schema/events.ts:20-85: the Usage breakdown fields are non-overlapping, and
    #   visibleOutputTokens = max(0, outputTokens - reasoningTokens);
    # - packages/ai/src/protocols/open-responses.ts:843-859 (openai's default Responses route): nonCached =
    #   input_tokens - (cached_tokens + cache_write_tokens); outputTokens = output_tokens; reasoningTokens =
    #   output_tokens_details.reasoning_tokens.
    # So the stored input excludes cache read and write, and the stored output excludes reasoning.
    token_semantics = {"2.0.18": {"openai": U.DISJOINT}}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.server: Server | None = None
        self.client: Client | None = None
        self.events: EventStream | None = None
        self.session: str | None = None
        self.sent: list[str] = []
        self.turn = "starting"          # running | held (after a Lead interrupt) | ended
        self.exit_code: int | None = None
        self.detail: str | None = None
        self.health: dict[str, Any] = {}
        self.snapshot: dict[str, Any] | None = None
        self.step_models: list[dict[str, Any]] = []
        self.permission_rejected: list[dict[str, Any]] = []
        self.forms_cancelled: list[str] = []
        self.foreign_sessions: list[str] = []
        self.tool_names: dict[str, str] = {}  # tool call id -> tool name (V2 names a tool only when its input starts)
        self.poll_errors = 0
        self._idle_seen: str | None = None
        self._lead_interrupted = False
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None

    # ------------------------------------------------------------------ launch

    def extra_requirements(self) -> tuple[capabilities.Op, ...]:
        """Further operations a subclass needs (tests: an impossible one proves the probe fails closed)."""
        return ()

    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        self.contract = contract
        self.state_dir = self.run_dir / "harness"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.directory = os.path.realpath(contract.workspace)  # 8.3 short paths break OpenCode's project detection
        config = projection.invocation_config(
            contract, private_dirs=projection.private_output_dirs(
                os.path.realpath(self.state_dir), os.sep,
                scratch=os.path.realpath(contract.scratch) if contract.scratch else ""))
        self.skills = projection.skills(contract)
        rules = config["permissions"]
        (self.state_dir / "opencode-config.json").write_text(json.dumps(config, indent=1, sort_keys=True),
                                                             encoding="utf-8")
        command = binary_command()
        env = server_env(dict(os.environ), self.state_dir, provider_env=list(contract.extra.get("provider_env") or []),
                         config=config, password=secrets.token_urlsafe(32))
        self.server = Server.start(self.tree.spawn, command, env=env, cwd=self.directory,
                                   log_path=self.state_dir / "server.log")
        del env
        self.client = self.server.client
        self.emit({"event": "opencode.server", "pid": self.server.proc.pid, "start_s": round(self.server.started_s, 3)})
        self.health = self._health(contract, config)
        body = projection.session_body(contract, self.directory, rules)
        self.session = str(self.client.post("/api/session", body)["data"]["id"])
        self.client.put(f"/api/session/{self.session}/environment", {"variables": dict(agent_env)})
        self.events = EventStream(self.client, self._on_event, self.server.alive)
        self.events.start()
        self._monitor = threading.Thread(target=self._watch, name="aew-opencode-monitor", daemon=True)
        self._monitor.start()
        self.deliver_contract(contract)
        return {"harness": self.name, "version": self.health.get("version"), "session": self.session,
                "state_dir": str(self.state_dir), "server_pid": self.server.proc.pid, "health": self.health,
                "model": projection.model_ref(contract.execution_profile), "skills": self.skills,
                "projection_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                "context": {"prompt_bytes": len(contract.prompt.encode("utf-8")),
                            "system_bytes": len(config["agents"][projection.AGENT]["system"].encode("utf-8"))}}

    def deliver_contract(self, contract: LaunchContract) -> None:
        """The first prompt: the launch contract (subclasses in tests act without a model instead)."""
        try:
            self._prompt(contract.prompt)
        except OpenCodeUnavailable:
            assert self.server is not None
            try:  # a server that was healthy and then died while taking the contract crashed: it did not fail to start
                self.server.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                raise
            self._server_gone()

    def _health(self, contract: LaunchContract, config: dict[str, Any]) -> dict[str, Any]:
        assert self.client is not None
        t0 = time.monotonic()
        version = (self.client.get("/api/info") or {}).get("version")
        spec = self.client.get("/openapi.json", timeout=60)
        gaps = capabilities.version_problems(version) + capabilities.problems(spec, self.extra_requirements())
        if gaps:
            raise HarnessIncompatible(f"OpenCode {version} lacks what AEW needs: " + "; ".join(gaps),
                                      version=version, problems=gaps)
        probe_s = time.monotonic() - t0
        model = self._await_model(contract.execution_profile)
        loaded = self._await_projection(config)
        stored = self._stored_credentials(spec)
        return {"version": version, "tested": version in capabilities.TESTED_VERSIONS, "stored_credentials": stored,
                "openapi_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
                "probe_s": round(probe_s, 3), **model, **loaded}

    def _stored_credentials(self, spec: Any) -> int:
        """A run's server must hold no stored integration credential. OpenCode 2.0.22 serves them, values included,
        at ``GET /api/credential``, and the server password is readable from the agent's shell (ADR-0009 residual),
        so one stored there would be the agent's. A run's state is private and starts empty; this proves it at each
        launch and refuses otherwise (register E17). A server without the endpoint holds none it could serve."""
        assert self.client is not None
        paths = spec.get("paths") if isinstance(spec, dict) else None
        if not isinstance(paths, dict) or "get" not in (paths.get(CREDENTIALS) or {}):
            return 0
        found = self.client.get(CREDENTIALS)
        items = found.get("data") if isinstance(found, dict) else found
        count = len(items) if isinstance(items, (list, dict)) else int(bool(items))
        if count:
            raise HarnessIncompatible(f"the run's OpenCode server holds {count} stored credential(s), which its agent "
                                      "could read; a run's server state must start empty", stored_credentials=count)
        return 0

    def _await_model(self, profile: dict[str, Any]) -> dict[str, Any]:
        """The pinned model and variant, from a catalog that fills in asynchronously. Never a fallback."""
        assert self.client is not None
        ref = projection.model_ref(profile)
        t0 = time.monotonic()
        first_seen: float | None = None
        catalog: list[dict[str, Any]] = []
        while True:
            catalog = (self.client.get("/api/model", location(self.directory)) or {}).get("data") or []
            match = next((m for m in catalog if m.get("providerID") == ref["providerID"] and m.get("id") == ref["id"]),
                         None)
            now = time.monotonic()
            if match is not None:
                variants = [v.get("id") for v in match.get("variants") or []]
                if "variant" in ref and ref["variant"] not in variants:
                    raise HarnessIncompatible(
                        f"model {ref['providerID']}/{ref['id']} has no variant {ref['variant']!r} (the pinned effort); "
                        f"it offers {variants or 'none'}", model=ref)
                if match.get("enabled") is False:
                    raise HarnessIncompatible(f"model {ref['providerID']}/{ref['id']} is disabled in this OpenCode",
                                              model=ref)
                return {"catalog_wait_s": round(now - t0, 3), "catalog_size": len(catalog), "variants": variants}
            if catalog and first_seen is None:
                first_seen = now
            if now - t0 > CATALOG_WAIT_S or (first_seen is not None and now - first_seen > CATALOG_SETTLE_S):
                providers = sorted({str(m.get("providerID")) for m in catalog})
                raise HarnessIncompatible(
                    f"model {ref['providerID']}/{ref['id']} is not offered by this OpenCode "
                    f"({len(catalog)} models from {providers or 'no provider'} after {now - t0:.0f}s); check the "
                    "execution policy and the provider variables it names", model=ref)
            time.sleep(0.25)

    def _await_projection(self, config: dict[str, Any]) -> dict[str, Any]:
        """The server must have loaded AEW's agent exactly as projected: its system text, the pinned model and
        effort, the step limit, and AEW's rules as the last (winning) part of its permissions, followed by nothing
        but denials (``projection.rules_hold``). Agents load asynchronously, like the catalog."""
        assert self.client is not None
        want = config["agents"][projection.AGENT]
        pinned = (want["model"]["providerID"], want["model"]["model"], want["model"].get("variant") or "default")
        t0 = time.monotonic()
        first_seen: float | None = None
        while True:
            agents = (self.client.get("/api/agent", location(self.directory)) or {}).get("data") or []
            mine = next((a for a in agents if a.get("id") == projection.AGENT), None)
            now = time.monotonic()
            if mine is not None:
                model = mine.get("model") or {}
                rules = list(mine.get("permissions") or [])
                checks = (("system text", mine.get("system") == want["system"]),
                          ("model", (model.get("providerID"), model.get("id"), model.get("variant") or "default")
                           == pinned),
                          ("step limit", mine.get("steps") == want.get("steps")),
                          ("permissions", (why := projection.rules_hold(rules, want["permissions"])) is None))
                differs = [name for name, same in checks if not same]
                if differs:
                    raise HarnessIncompatible(f"OpenCode loaded AEW's agent with a different {', '.join(differs)}: the "
                                              "projection was not applied as written", differs=differs,
                                              **({"permissions": why} if why else {}))
                return {"projection_loaded_s": round(now - t0, 3), "agent_rules": len(rules)}
            if agents and first_seen is None:
                first_seen = now
            if now - t0 > CATALOG_WAIT_S or (first_seen is not None and now - first_seen > CATALOG_SETTLE_S):
                raise HarnessIncompatible("OpenCode did not load AEW's agent: its configuration "
                                          "(OPENCODE_CONFIG_CONTENT) was not applied",
                                          agents=sorted(str(a.get("id")) for a in agents))
            time.sleep(0.25)

    # ------------------------------------------------------------------ prompts

    def _prompt(self, text: str, delivery: str | None = None) -> str:
        assert self.client is not None and self.session is not None
        mid = new_message_id()
        with self._lock:  # recorded first, so a poll never mistakes the previous turn's idle for this one's
            if self.turn == "ended":  # nothing watches an ended run: reviving it would leave it hanging (audit I3)
                raise HarnessError("this run's harness turn has ended, so the message was not delivered; "
                                   "relaunch the run to continue it (`aew harness launch`)")
            self.sent.append(mid)
            self.turn = "running"
            self._idle_seen = None
        body: dict[str, Any] = {"id": mid, "text": text}
        if delivery:
            body["delivery"] = delivery
        try:
            self.client.post(f"/api/session/{self.session}/prompt", body)
        except (OpenCodeError, OpenCodeUnavailable):
            with self._lock:
                self.sent.remove(mid)
            raise
        self.emit({"event": "opencode.prompt", "message": mid, "delivery": delivery or "steer",
                   "bytes": len(text.encode("utf-8"))})
        self._wake.set()
        return mid

    def send(self, text: str) -> None:
        self._prompt(text, delivery="queue")  # after the current step, inside the same turn; never lost

    def interrupt(self) -> None:
        assert self.client is not None
        with self._lock:
            self._lead_interrupted = True
        self.client.post(f"/api/session/{self.session}/interrupt", params={"resume": "false"})
        self._wake.set()

    # ------------------------------------------------------------------ watching

    def _on_event(self, frame: dict[str, Any]) -> None:
        kind = str(frame.get("type") or "")
        raw = frame.get("data")
        data: dict[str, Any] = raw if isinstance(raw, dict) else {}
        sid = data.get("sessionID")
        if kind == "session.created" and sid and sid != self.session and self.session is not None:
            self.foreign_sessions.append(str(sid))  # no subagents exist: any other session is recorded
            self.emit({"event": "opencode.foreign_session", "session": sid})
        if sid not in (None, self.session):
            return
        if kind == "session.step.started" and isinstance(data.get("model"), dict):
            self.step_models.append(data["model"])
        if kind == "session.tool.input.started" and data.get("id"):
            self.tool_names[str(data["id"])] = str(data.get("name"))
        if kind in LOGGED_EVENTS:
            summary: dict[str, Any] = {"event": f"opencode.{kind}"}
            for key in ("finish", "reason", "action", "inboxID", "assistantMessageID"):
                if key in data:
                    summary[key] = data[key]
            if isinstance(data.get("model"), dict):
                summary["model"] = data["model"]
            if kind in ("session.tool.called", "session.tool.failed"):  # the name only: never the tool's input
                summary["tool"] = self.tool_names.get(str(data.get("id")))
            if isinstance(data.get("tokens"), dict):
                summary["tokens"] = data["tokens"]
            if isinstance(data.get("error"), dict):
                summary["error"] = {k: data["error"].get(k) for k in ("type", "message")}
            self.emit(summary)
        if kind.startswith("session.execution.") or kind.startswith("permission.") or kind.startswith("form."):
            self._wake.set()

    def _watch(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(POLL_S)
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                self._poll()
            except OpenCodeUnavailable:
                self.poll_errors += 1
                if self.server is not None and not self.server.alive():
                    self._server_gone()
            except OpenCodeError as exc:
                self.poll_errors += 1
                if exc.status == 404 and not self._session_exists():
                    self._end(1, f"the OpenCode session {self.session} disappeared")
            except Exception as exc:  # noqa: BLE001 - never leave a run unwatched
                self._end(70, f"adapter error: {type(exc).__name__}: {exc}")
            if self.turn == "ended":
                return

    def _session_exists(self) -> bool:
        assert self.client is not None
        try:
            self.client.get(f"/api/session/{self.session}")
        except OpenCodeError as exc:
            return exc.status != 404
        except OpenCodeUnavailable:
            return True  # unknown: the server check decides
        return True

    def _server_gone(self) -> None:
        assert self.server is not None
        code = self.server.proc.returncode
        self._end(code if code not in (None, 0) else 70, f"the OpenCode server exited ({code}) during the run")

    def _poll(self) -> None:
        assert self.client is not None and self.server is not None
        if not self.server.alive():
            return self._server_gone()
        self._reject_requests()
        with self._lock:
            if self.turn != "running" or not self.sent:
                return
            last = self.sent[-1]
        active = (self.client.get("/api/session/active") or {}).get("data") or {}
        if self.session in active:
            self._idle_seen = None
            return
        try:
            delivered = self.client.get(f"/api/session/{self.session}/message/{last}")["data"]
        except OpenCodeError as exc:
            if exc.status == 404:  # still queued: not delivered yet
                self._idle_seen = None
                return
            raise
        newest = (self.client.get(f"/api/session/{self.session}/message", {"order": "desc", "limit": "1"})
                  or {}).get("data") or []
        idle = newest[0] if newest else {}
        if idle.get("type") != "idle" or _created(idle) < _created(delivered):
            self._idle_seen = None
            return
        inbox = (self.client.get(f"/api/session/{self.session}/inbox") or {}).get("data") or []
        with self._lock:
            if any(item.get("id") in self.sent for item in inbox) or self.sent[-1] != last:
                self._idle_seen = None
                return
            if self._idle_seen != idle.get("id"):
                self._idle_seen = idle.get("id")  # confirm on the next poll: a queue boundary can reopen the turn
                self._wake.set()
                return
        self._turn_over(str(idle.get("outcome")), last)

    def _turn_over(self, outcome: str, last: str) -> None:
        """Close the turn whose last prompt was ``last``, unless a newer prompt arrived since the poll decided."""
        self._take_snapshot()
        with self._lock:  # the decision and the state change are one step for `_prompt` (independent audit I3)
            if self.turn != "running" or self.sent[-1] != last:
                self._idle_seen = None  # a Lead message arrived meanwhile: the run goes on
                return
            if outcome == "interrupted" and self._lead_interrupted:
                self._lead_interrupted = False
                self.turn = "held"  # the Lead interrupted: the session waits for `send`, a stop or the deadline
                self.emit({"event": "opencode.held", "outcome": outcome})
                return
            error = next((m.get("error") for m in reversed((self.snapshot or {}).get("assistant", []))
                          if m.get("error")), None)
            detail = f"the agent's turn ended: {outcome}" + (f" ({error.get('type')}: {error.get('message')})"
                                                              if isinstance(error, dict) else "")
            self._end(EXIT_CODES.get(outcome, 1), detail)

    def _end(self, code: int, detail: str) -> None:
        with self._lock:
            if self.turn == "ended":
                return
            self.turn, self.exit_code, self.detail = "ended", code, detail
        self.emit({"event": "opencode.ended", "exit_code": code, "detail": detail})

    def _reject_requests(self) -> None:
        """AEW's rules are allow or deny only, so a permission request or a form means something unexpected:
        it is rejected (the turn ends) and recorded, never left to block the session forever."""
        assert self.client is not None
        for request in (self.client.get(f"/api/session/{self.session}/permission") or {}).get("data") or []:
            self.permission_rejected.append({"action": request.get("action"),
                                             "resources": list(request.get("resources") or [])[:5]})
            self.emit({"event": "opencode.permission_rejected", "action": request.get("action")})
            try:
                self.client.post(f"/api/session/{self.session}/permission/{request['id']}/reply",
                                 {"decision": "reject", "message": "AEW runs allow or deny only; nothing asks."})
            except OpenCodeError:
                pass
        for form in (self.client.get(f"/api/session/{self.session}/form") or {}).get("data") or []:
            fid = str(form.get("id"))
            if fid in self.forms_cancelled:
                continue
            self.forms_cancelled.append(fid)
            self.emit({"event": "opencode.form_cancelled", "form": fid})
            try:
                self.client.delete(f"/api/session/{self.session}/form/{fid}")
            except OpenCodeError:
                pass

    # ------------------------------------------------------------------ observation

    def inspect(self) -> dict[str, Any]:
        with self._lock:
            return {"alive": self.turn != "ended", "exit_code": self.exit_code, "session": self.session,
                    "turn": self.turn, "detail": self.detail}

    def _take_snapshot(self) -> None:
        """Assistant messages' model, usage and errors (never their text), while the server is still up."""
        if self.client is None or self.session is None:
            return
        assistant: list[dict[str, Any]] = []
        params: dict[str, str] = {"order": "asc", "limit": "200"}
        truncated = True  # unless the last page is reached: the bounded loop may stop with a next cursor left (F25 R1)
        for _ in range(PAGES):
            page = self.client.get(f"/api/session/{self.session}/message", params) or {}
            for m in page.get("data") or []:
                if m.get("type") == "assistant":
                    assistant.append({"model": m.get("model"), "agent": m.get("agent"), "tokens": m.get("tokens"),
                                      "cost": m.get("cost"), "finish": m.get("finish"),
                                      "tools": [str(c.get("name")) for c in m.get("content") or []
                                                if isinstance(c, dict) and c.get("type") == "tool"],
                                      "error": {k: (m.get("error") or {}).get(k) for k in ("type", "message")}
                                      if m.get("error") else None})
            nxt = (page.get("cursor") or {}).get("next")
            if not nxt:
                truncated = False
                break
            params = {"cursor": str(nxt), "limit": "200"}
        info = (self.client.get(f"/api/session/{self.session}") or {}).get("data") or {}
        self.snapshot = {"assistant": assistant, "session": {k: info.get(k) for k in ("outcome", "tokens", "cost")},
                         "truncated": truncated}
        # Every other session in the run's private state (a subagent's, or anyone's): recorded even if the event
        # stream missed its creation.
        for other in (self.client.get("/api/session", location(self.directory)) or {}).get("data") or []:
            sid = other.get("id")
            if sid and sid != self.session and sid not in self.foreign_sessions:
                self.foreign_sessions.append(str(sid))

    def terminate(self) -> None:
        self._stop.set()
        self._wake.set()
        if self.server is not None and self.server.alive() and self.snapshot is None:
            try:
                self._take_snapshot()
            except (OpenCodeError, OpenCodeUnavailable):
                pass
        if self.events is not None:
            self.events.close()
        if self.server is not None:
            self.server.close(wait_s=3.0)  # the lease; the supervisor's process tree ends whatever remains

    def collect(self) -> dict[str, Any]:
        out: dict[str, Any] = {"sessions": [self.session] if self.session else [], "turn": self.turn,
                               "prompts": len(self.sent), "permission_rejected": self.permission_rejected,
                               "forms_cancelled": self.forms_cancelled, "foreign_sessions": self.foreign_sessions,
                               "events_dropped": self.events.drops if self.events else None,
                               "poll_errors": self.poll_errors, "skills": getattr(self, "skills", None)}
        snap = self.snapshot
        if snap is not None:
            out["effective"] = _effective([m["model"] for m in snap["assistant"]])
            out["usage"] = snap["session"]
            out["steps"] = len(snap["assistant"])
            tools: dict[str, int] = {}
            for m in snap["assistant"]:
                for name in m.get("tools") or []:
                    tools[name] = tools.get(name, 0) + 1
            out["tools_called"] = tools  # what the agent actually used (never its inputs or outputs)
            first = next((m["tokens"] for m in snap["assistant"] if isinstance(m.get("tokens"), dict)), None)
            if first:  # what the model received on its first step: contract + OpenCode's own overhead
                cached = (first.get("cache") or {}).get("read") or 0
                out["first_step_input_tokens"] = (first.get("input") or 0) + cached
        elif self.step_models:
            out["effective"] = _effective(self.step_models)
        out["usage_record"] = self._usage_record(out.get("effective") or [])
        return out

    def _usage_record(self, effective: list[dict[str, Any]]) -> dict[str, Any]:
        """The normalized ``aew/run-usage/v1`` record (F25 R2): the session's totals, its model calls, and the token
        semantics declared for the providers that ran, under the OpenCode version that ran them."""
        snap = self.snapshot
        source = f"harness:{self.name}"
        if snap is None:  # no snapshot (the server was gone): the usage is unknown, never zero
            return U.normalize(None, None, effective, U.UNKNOWN, source=source,
                               foreign_sessions=len(self.foreign_sessions))
        contract = getattr(self, "contract", None)
        pinned = (contract.execution_profile or {}).get("provider") if contract is not None else None
        providers = [e.get("provider") for e in effective] or [pinned]
        semantics = U.resolve_semantics(self.token_semantics, self.health.get("version"), providers)
        return U.normalize(snap["session"], snap["assistant"], effective, semantics, source=source,
                           truncated=bool(snap.get("truncated")), foreign_sessions=len(self.foreign_sessions))


def _created(message: dict[str, Any]) -> float:
    return float((message.get("time") or {}).get("created") or 0)


def _effective(models: list[Any]) -> list[dict[str, Any]]:
    """Distinct ``{provider, model, effort}`` in first-use order.

    OpenCode's ``default`` variant is an observation: no effort variant ran (``effort: None``). A missing or empty
    variant is not an observation, so the entry is marked ``effort_unreported`` and never counts as a match for a
    requested effort (independent audit I4)."""
    out: list[dict[str, Any]] = []
    for m in models:
        if not isinstance(m, dict):
            continue
        variant = m.get("variant")
        entry: dict[str, Any] = {"provider": m.get("providerID"), "model": m.get("id"),
                                 "effort": None if variant in (None, "", "default") else variant}
        if variant in (None, ""):
            entry["effort_unreported"] = True
        if entry not in out:
            out.append(entry)
    return out
