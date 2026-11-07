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
5. **Live usage** (F25 for M4-H, slice L2). The run's meter (:mod:`aew.harness.usage_live`) is created first and is
   the only writer of ``usage.live.json``: ``prompt_state: unsent`` is written before the server starts (a failed
   write refuses the launch), the meter polls the server every second with its own client and 2 s timeouts in every
   turn state, ``posting`` and ``posted`` bracket the first prompt, the end of a turn asks for a sample at once, and
   ``terminate`` takes a fresh final sample in at most 4 s all told. No adapter-thread call ever waits on the meter's
   network requests (a poll reads outside the meter's lock). At ``terminate`` polls are cancelled: one in flight
   stops at its next request, one that has not committed by then never commits, and the final sample never lowers
   the figure of one that did; no sample is written after ``terminate`` returns.
   A meter failure is counted and never ends or delays the run.

Nothing the adapter reports is evidence. Effective model and usage come from the session's assistant
messages (non-authoritative telemetry that the supervisor compares with the pin).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from aew.errors import HarnessError, HarnessIncompatible, HarnessLaunchFailed, ValidationFailed
from aew.harness import agentenv, progress, runlog, weaker_register
from aew.harness import usage as U
from aew.harness.base import (
    KEY_IN_SANDBOX,
    PROVIDER_ENV_UNUSABLE,
    RELAY_FAMILY_MATCHES,
    RELAY_FAMILY_MISMATCH,
    RELAY_FAMILY_REFUSED,
    RELAY_FAMILY_UNVERIFIED,
    HarnessAdapter,
)
from aew.harness.containment import netns
from aew.harness.contract import (
    AGENT_LOAD_TIMEOUT,
    AVAILABLE_TOOLS,
    CATALOG_TIMEOUT,
    CREDENTIAL_PATTERNS,
    EXPECT_REV,
    LONG_TOKEN,
    PROVIDER_AUTH_FAILED,
    REDACTION_FORMS,
    UNAVAILABLE_TOOLS,
    LaunchContract,
)
from aew.harness.harness_capabilities import PARTIAL as CAP_PARTIAL
from aew.harness.harness_capabilities import YES as CAP_YES
from aew.harness.harness_capabilities import Support
from aew.harness.opencode import capabilities, projection
from aew.harness.opencode.client import (
    EVENT_CONNECT_S,
    REQUEST_TIMEOUT_S,
    START_TIMEOUT_S,
    Client,
    EventStream,
    OpenCodeError,
    OpenCodeUnavailable,
    Server,
    location,
)
from aew.harness.usage_live import Meter

BIN_ENV = "AEW_OPENCODE_BIN"
POLL_S = 1.0
PAGES = 100  # at most this many pages of 200 messages are read for a run's snapshot (more: `truncated`)
CATALOG_WAIT_S = float(os.environ.get("AEW_OPENCODE_CATALOG_S", "90"))
CATALOG_SETTLE_S = float(os.environ.get("AEW_OPENCODE_CATALOG_SETTLE_S", "20"))
OPENAPI_TIMEOUT_S = 60.0  # the served schema is large
EXIT_CODES = {"succeeded": 0, "failed": 1, "interrupted": 2}
CREDENTIALS = "/api/credential"  # 2.0.22+: stored integration credentials, values included
# The live usage meter (F25 for M4-H, slice L2; plan v4 §2.1): one poll a second, 2 s per request, and at most 4 s
# of the adapter's share of TERMINATE_S for the final sample, the thread's join included (§4.2). The final read gets
# the share less a margin for its two file writes; the join gets whatever is left of the share.
METER_POLL_S = 1.0
METER_REQUEST_S = 2.0
METER_FINAL_S = 4.0
METER_WRITE_MARGIN_S = 0.5
# A run's potential sessions (A3): its own session; OpenCode's title and compaction calls run inside it (A2's k).
RUN_S_POT = 1
LOGGED_EVENTS = frozenset({
    "session.created", "session.execution.started", "session.execution.succeeded", "session.execution.failed",
    "session.execution.interrupted", "session.step.started", "session.step.ended", "session.step.failed",
    "session.tool.called", "session.tool.failed", "session.inbox.enqueued", "session.inbox.delivered",
    "permission.asked", "permission.replied",
})
# A failed turn's error type (the pinned 2.0.18 ``Session.StructuredError``: ``type``, ``message``, ``status``) -> the
# run's ``reason_code``. Observed on 2.0.18 (2026-10-09, a local provider answering HTTP 401): a provider that rejects
# the credential fails the turn at once, with no retry, and ``{type: "provider.auth", status: 401}`` (with the
# provider's message) is on the failed step's assistant message (``finish: "error"``), on ``session.step.failed`` and
# on ``session.execution.failed``; the turn's idle message has ``outcome: "failed"``.
AUTH_ERROR = "provider.auth"
REASON_CODES = {AUTH_ERROR: PROVIDER_AUTH_FAILED}
# Statuses whose message may concern a credential (unauthorized, forbidden, proxy authentication required): their
# message is dropped whatever the type says, so a renamed or different classification fails closed (register V1).
CREDENTIAL_STATUSES = frozenset({401, 403, 407})
# Key-shaped text redacted from every provider message that is kept: an `sk-` key (masked or not), a bearer token, a
# masked run of asterisks with whatever surrounds it, any strict provider-key shape, and a long token that mixes upper
# case, lower case and digits, as a random key does. Model ids, git shas, UUIDs, request ids and paths are one case or
# carry no digit, and stay: they are what an operator diagnoses a non-credential error from (PR #165 re-review, finding
# 1). Every form comes from the one home of credential shapes, `aew.harness.contract` (F46.1 proposal §7 rule 8). The
# prior pipeline runs unchanged (the broader forms, each with its own scoped flag, then the long-token form); the strict
# patterns are applied after it, to its output. A later pass only replaces more text, so the redaction never narrows.
KEY_SHAPED = re.compile("|".join(f.pattern for f in REDACTION_FORMS.values() if f.applies is None))
STRICT_SHAPED = re.compile("|".join(CREDENTIAL_PATTERNS))
_LONG_TOKEN_APPLIES = REDACTION_FORMS["long_token"].applies or (lambda _token: True)


def redact_key_shaped(text: str) -> str:
    def mixed(m: re.Match[str]) -> str:
        return "<redacted>" if _LONG_TOKEN_APPLIES(m.group(0)) else m.group(0)

    return STRICT_SHAPED.sub("<redacted>", LONG_TOKEN.sub(mixed, KEY_SHAPED.sub("<redacted>", text)))


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
        raise HarnessIncompatible(f"no OpenCode binary: {BIN_ENV} names the OpenCode CLI "
                                  f"(tested: {', '.join(capabilities.TESTED_VERSIONS)}); "
                                  f"{agentenv.env_fix(BIN_ENV, secret=False)}",
                                  looked_for=str(path) if path else None)
    return [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]


def server_env(base: dict[str, str], state_dir: Path, *, provider_env: list[str], config: dict[str, Any],
               password: str) -> dict[str, str]:
    """The server's environment: operating-system basics, the provider variables the execution policy names,
    and private OpenCode state. Nothing else from the Lead's environment reaches OpenCode.

    A provider variable that cannot be passed (unset, an AEW variable, or one holding an AEW credential) refuses the
    start, naming it: it is never dropped silently, which started a run with no key and blamed the provider
    (``agentenv.provider_env_problems``; the launch refuses the same before anything is committed)."""
    keep = agentenv.WINDOWS_KEEP if sys.platform == "win32" else agentenv.POSIX_KEEP
    # SHELL: OpenCode picks the agent's shell from it (else PowerShell on Windows), as for the operator's own use.
    env = {k: v for k, v in base.items() if k.upper() in keep or k.upper() in ("PATH", "SHELL")
           or (sys.platform != "win32" and k.startswith("LC_"))}
    problems = agentenv.provider_env_problems(provider_env, base)
    if problems:
        raise HarnessIncompatible("the execution policy's provider_env cannot be passed to the harness server: "
                                  + "; ".join(why for _, why in problems), reason=PROVIDER_ENV_UNUSABLE,
                                  variables=[name for name, _ in problems])
    for name in provider_env:
        env[name] = str(agentenv.lookup(base, name))  # the same lookup the checks use (Windows: any case)
    agentenv.bypass_proxy_for_loopback(env)
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


def declared_only(model: dict[str, Any]) -> bool:
    """Whether a catalog entry is one the server made from AEW's own configuration rather than one it offers: 2.0.18
    lists any model its configuration names, made up from the provider's defaults (measured on the Rocky VM,
    2026-10-24). Such an entry has no family and no release time, and its name is its id; an offered one has its
    catalog's. So the pinned model, which ``projection.relayed`` names to point it at the relay, is still refused at
    launch when the catalog does not offer it, as it was before the relay."""
    return not model.get("family") and not (model.get("time") or {}).get("released") and model.get("name") == model.get(
        "id")


# The relay-route check of the pinned model's family (``relay_family``): its results and the reason it refuses with are
# the harness's closed launch report (``aew.harness.base``), which the supervisor puts on the run's label and passes on
# in its acknowledgement (register E143).


def _served_at(address: Any) -> tuple[str, str, int, str] | None:
    """A catalog address as the relay's upstream is compared: scheme, host, port and base path; None if not one."""
    if not isinstance(address, str):
        return None
    try:
        up = netns.relay.Upstream(address)  # the relay's own reading of an upstream URL
    except ValidationFailed:
        return None
    return up.scheme, up.host, up.port, up.path  # urlsplit's hostname is lower case already


def relay_family(pinned: dict[str, Any], catalog: list[dict[str, Any]], upstream: str) -> dict[str, Any]:
    """Whether the run's provider relay's one upstream serves the pinned model's family (F28 §3.5; the designer's
    terms of 2026-11-06). A model of another family (an Anthropic model behind an OpenAI-style upstream) would have
    its requests sent to an endpoint that does not serve them, failing only at its first model call.

    The model's family is its catalog ``package`` (the SDK its requests are made with), which OpenCode 2.0.18 keeps on
    the relay route (measured 2026-11-06). Its address is not kept, since AEW's projection (``projection.relayed``)
    replaces it with the relay's. The families the upstream serves are read from the same catalog: the packages of the
    provider's other models whose own address is the upstream (each ``opencode/*`` model carries one, and AEW
    overrides only the pinned model's).

    - ``matches``: the model's package is among them;
    - ``mismatch``: it is not, and other models of the provider carry the package, none of them served from the
      upstream: the launch is refused;
    - ``unverified``: there is nothing to decide by, and the launch goes ahead with that recorded: the model states no
      package; no model of the catalog is served from the upstream (a catalog that spells the upstream another way,
      as 2.0.18's embedded snapshot gives Zen as ``opencode.ai/zen/v1`` where the live catalog and
      ``netns.UPSTREAMS`` have ``/inference/openai/v1``, is never refused on a spelling); or no other model carries
      the package, so the pinned model, whose own address is hidden, may be the one that serves it there (the live
      catalog's one ``mistral`` model at the upstream, 2026-11-06). Other carriers only decide between ``mismatch``
      and ``unverified``: they never pass a model. A carrier counts only when it states a readable address of its own
      (not the relay's, which the projection gave the pinned model): one with none says nothing of where it is served.

    Limits:

    - The package stands in for the endpoint. A model whose package other models carry at the upstream but which is
      itself served elsewhere (``openai-compatible`` serves many endpoints) reads ``matches``, and fails at its first
      call as before this check.
    - A package served from two addresses, the pinned model at the upstream and every other carrier elsewhere, is
      refused although the model is served where the relay sends. So is a carrier spelt otherwise in a catalog that
      mixes spellings (a ``zen/v1`` carrier among live addresses); each catalog measured has one spelling.
    - A package of one model really served elsewhere reads ``unverified`` and fails at its first call.
    - Only a provider whose catalog models carry their own address (``netns.CATALOG_ADDRESSED``) can be refused: for
      any other, every model shows the relay's address after the projection, and the check reads ``unverified``."""
    provider, package, pin = pinned.get("providerID"), pinned.get("package"), pinned.get("id")
    want = _served_at(upstream)
    others = [m for m in catalog if m.get("providerID") == provider and m.get("id") != pin and not declared_only(m)]
    served = sorted({str(m.get("package")) for m in others
                     if m.get("package") and want is not None
                     and _served_at((m.get("settings") or {}).get("baseURL")) == want})
    out: dict[str, Any] = {"package": package, "upstream_packages": served}
    if not package or not served:
        return {"check": RELAY_FAMILY_UNVERIFIED, **out}
    if package in served:
        return {"check": RELAY_FAMILY_MATCHES, **out}
    hidden = _served_at((pinned.get("settings") or {}).get("baseURL"))  # the relay's, as the projection set it
    addressed = [m for m in others if _served_at((m.get("settings") or {}).get("baseURL")) not in (None, hidden)]
    carried = any(m.get("package") == package for m in addressed)
    return {"check": RELAY_FAMILY_MISMATCH if carried else RELAY_FAMILY_UNVERIFIED, **out}


class OpenCodeAdapter(HarnessAdapter):
    name = "opencode"
    # F28 §3.4-3.5: it calls its provider itself, through the relay in a network of its own, and in connected mode it
    # fetches its model catalog, which a pinned model newer than its embedded one needs (F28 §1, E).
    PROVIDER_RELAY = True
    EGRESS = ("models.opencode.ai:443",)
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

    # The harness capabilities this adapter provides (steering design §7; aew.harness.harness_capabilities).
    harness_capabilities: dict[str, Support] = {
        "wake_idle_session": Support(CAP_YES, "`session.prompt`"),
        "queue_until_turn_end": Support(CAP_YES, "`session.prompt` with `delivery: queue`"),
        "steer_running_turn": Support(CAP_YES, "`session.prompt` with `delivery: steer`"),
        "interrupt_turn": Support(CAP_YES, "`session.interrupt`"),
        "read_progress": Support(CAP_YES, "polled: tool parts of `session.message.list` (the meter's poll)"),
        "read_usage": Support(CAP_YES, "polled: the meter (`session.list`, `session.message.list`)"),
        "attach_to_operator_session": Support(CAP_YES, "the Lead runs on AEW's OpenCode server, which the broker "
                                                       "serves"),
        "mark_non_operator_input": Support(CAP_PARTIAL, "text only: the wake's fixed header, which the model reads "
                                                        "as text; `session.prompt` metadata is not shown to it, and "
                                                        "there is no role of its own"),
    }

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
        self.reason_code: str | None = None
        self._failed: dict[str, Any] | None = None  # the error of the last `session.execution.failed`, as recorded
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
        self.meter: Meter | None = None
        self.meter_errors = 0
        self._relayed = False  # the pinned model is named in the server's configuration, for the provider relay
        self._relay: str | None = None  # the provider relay's upstream, on the relay route
        self._meter_wake = threading.Event()
        self._meter_stop = threading.Event()
        self._meter_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ launch

    def extra_requirements(self) -> tuple[capabilities.Op, ...]:
        """Further operations a subclass needs (tests: an impossible one proves the probe fails closed)."""
        return ()

    def _relaunch_command(self) -> str:
        """The complete command for recovering this invocation's run."""
        contract = getattr(self, "contract", None)
        invocation = contract.invocation if contract is not None else "<invocation from aew harness status>"
        return f"`aew harness launch {invocation} {EXPECT_REV}`"

    def launch(self, contract: LaunchContract, agent_env: dict[str, str]) -> dict[str, Any]:
        self.contract = contract
        self.state_dir = self.run_dir / "harness"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.directory = os.path.realpath(contract.workspace)  # 8.3 short paths break OpenCode's project detection
        network = self.tree.network  # a network of the run's own (F28; STG-05 CS-3b), or None
        state = os.path.realpath(self.state_dir)
        self.skills = projection.skills(contract)  # as the supervisor copied them (aew.skills.deliver)
        config = projection.invocation_config(
            contract, private_dirs=projection.private_output_dirs(
                state, os.sep, scratch=os.path.realpath(contract.scratch) if contract.scratch else ""),
            skills_dir=projection.skills_at(state, os.sep),
            network=network.describe() if network is not None else None,  # the agent is told what it reaches
            unavailable_tools=list(contract.extra.get(UNAVAILABLE_TOOLS) or []),  # and what it goes without
            available_tools=contract.extra.get(AVAILABLE_TOOLS))  # and what it has, by name
        rules = config["permissions"]
        base = network.provider_base() if network is not None else None
        self._relayed = base is not None
        if base is not None:
            assert network is not None and network.relay is not None  # a provider base is only a relay's
            self._relay = network.relay.upstream.url
            config = projection.relayed(config, contract.execution_profile, base)
        (self.state_dir / "opencode-config.json").write_text(json.dumps(config, indent=1, sort_keys=True),
                                                             encoding="utf-8")
        command = binary_command()
        self._start_meter(contract)  # before any server exists: no server, and so no prompt, without a live file
        env = server_env(dict(os.environ), self.state_dir, provider_env=list(contract.extra.get("provider_env") or []),
                         config=config, password=secrets.token_urlsafe(32))
        if agent_env.get(weaker_register.MARKER):  # a weaker run's server, and all it starts, carry its marker too
            env[weaker_register.MARKER] = agent_env[weaker_register.MARKER]
        if network is not None:  # the provider's variables are sentinels inside; the relay holds the values
            env = network.harness_env(env)
            leaked = network.leaks(*env.values(), json.dumps(config))
            if leaked:  # F28 §3.6, row 6: never started with a provider secret in its reach
                raise HarnessIncompatible(f"the value of {', '.join(leaked)} would reach the run's sandbox in the "
                                          "harness's environment or configuration, so the harness was not started; "
                                          "keep the provider's key out of every other variable and setting",
                                          reason=KEY_IN_SANDBOX, variables=leaked)
        spawn = self.tree.spawn if network is None else functools.partial(self.tree.spawn, network_shim=True)
        self.server = Server.start(spawn, command, env=env, cwd=self.directory, log_path=self.state_dir / "server.log",
                                   **({"port": netns.SERVER_PORT, "unix": network.server_socket}
                                      if network is not None else {}))
        del env
        self.client = self.server.client
        self._bind_meter()
        self.emit({"event": "opencode.server", "pid": self.server.proc.pid, "start_s": round(self.server.started_s, 3)})
        self.health = self._health(contract, config)
        if self.meter is not None and self.health.get("version"):
            self.meter.version = str(self.health["version"])  # semantics follow the version that runs, as collect()'s
        body = projection.session_body(contract, self.directory, rules)
        self.session = str(self.client.post("/api/session", body)["data"]["id"])
        if self.meter is not None:
            self.meter.main_session = self.session
        self.client.put(f"/api/session/{self.session}/environment", {"variables": dict(agent_env)})
        self.events = EventStream(self.client, self._on_event, self.server.alive)
        self.events.start()
        self._monitor = threading.Thread(target=self._watch, name="aew-opencode-monitor", daemon=True)
        self._monitor.start()
        self._set_prompt_state("posting", required=True)  # immediately before the prompt's POST (M6, R2-m3)
        self.deliver_contract(contract)
        self._set_prompt_state("posted")
        return {"harness": self.name, "version": self.health.get("version"), "session": self.session,
                "state_dir": str(self.state_dir), "server_pid": self.server.proc.pid, "health": self.health,
                "model": projection.model_ref(contract.execution_profile), "skills": self.skills,
                "projection_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                "context": {"prompt_bytes": len(contract.prompt.encode("utf-8")),
                            "system_bytes": len(config["agents"][projection.AGENT]["system"].encode("utf-8"))}}

    @classmethod
    def launch_bound_s(cls) -> float:
        """``launch``'s steps in series, each at its own timeout: the server's address; ``/api/info``; the schema; the
        catalog and the agent projection, each waited for up to ``CATALOG_WAIT_S`` with a request in flight at the end;
        the stored-credential check, the session, its environment and the first prompt; the event stream's connect."""
        request = REQUEST_TIMEOUT_S
        return (START_TIMEOUT_S + request + OPENAPI_TIMEOUT_S + 2 * (CATALOG_WAIT_S + request) + 4 * request
                + EVENT_CONNECT_S)

    # ------------------------------------------------------------------ live usage (F25 L2)

    def _start_meter(self, contract: LaunchContract) -> None:
        """The run's meter, and its ``seq 0, unsent`` sample, before the server starts. A failed write refuses the
        launch: a server, and so a prompt, never exists without a live file (plan v4 R3-m3)."""
        self.meter = Meter(None, source={"kind": "run", "id": self.run_dir.name},
                           version=capabilities.TESTED_VERSIONS[0], semantics_table=self.token_semantics,
                           s_pot=RUN_S_POT, state_path=self.run_dir / runlog.LIVE_STATE_FILE,
                           live_path=self.run_dir / runlog.LIVE_FILE, request_timeout_s=METER_REQUEST_S,
                           pinned_model=projection.model_ref(contract.execution_profile),
                           progress=progress.Tracker(run=self.run_dir.name, workspace=contract.workspace,
                                                     scope_paths=contract.extra.get(progress.SCOPE_PATHS),
                                                     clock=time.time),
                           progress_path=self.run_dir / runlog.PROGRESS_FILE)
        try:
            self.meter.set_prompt_state("unsent")
        except OSError as exc:
            raise HarnessLaunchFailed(f"the run's live usage file could not be written ({type(exc).__name__}: "
                                      f"{exc}); no server was started") from None

    def meter_client(self) -> Client:
        """The meter's own client: never the adapter's, so a slow 30 s request of ``_poll`` cannot delay a sample."""
        assert self.server is not None
        return Client(self.server.url, self.server.password, unix=self.server.unix)

    def _bind_meter(self) -> None:
        """Once the server answers, the meter polls it every second in every turn state, until ``terminate``."""
        if self.meter is None or self.server is None:
            return
        self.meter.client = self.meter_client()
        self._meter_thread = threading.Thread(target=self._meter_loop, name="aew-opencode-meter", daemon=True)
        self._meter_thread.start()

    def _meter_loop(self) -> None:
        while not self._meter_stop.is_set():
            self._meter_tick()
            self._meter_wake.wait(METER_POLL_S)
            self._meter_wake.clear()

    def _meter_tick(self) -> None:
        """One meter poll. Its failures are the meter's own (``meter.errors``), never the run's."""
        if self.meter is None or self._meter_stop.is_set():
            return
        try:
            self.meter.poll()
        except Exception as exc:  # noqa: BLE001 - a meter failure never ends or delays the run
            self.meter_errors += 1
            self.emit({"event": "opencode.meter_error", "error": f"{type(exc).__name__}: {str(exc)[:200]}"})

    def _set_prompt_state(self, prompt_state: str, *, required: bool = False) -> None:
        """``posting`` must be on file before the prompt is posted, or a delivered prompt could read as never launched:
        a failed write refuses the launch. ``posted`` only narrows ``posting``, so its failure is counted."""
        if self.meter is None:
            return
        try:
            self.meter.set_prompt_state(prompt_state)
        except OSError as exc:
            if required:
                raise HarnessLaunchFailed(f"the run's live usage file could not record the prompt as {prompt_state} "
                                          f"({type(exc).__name__}: {exc}); the prompt was not sent") from None
            self.meter_errors += 1

    def _final_sample(self) -> None:
        """Take a fresh final sample and stop the meter's thread, in at most ``METER_FINAL_S`` all told. A poll in
        flight is cancelled at its next request and never waited for (PR #197 review, M1): the final read runs beside
        it, and a poll that has not committed when polls are cancelled never commits, so nothing is written after this
        returns; one that committed first is carried into the final sample, never lowered (PR #197 review, N1)."""
        t0 = time.monotonic()
        self._meter_stop.set()
        self._meter_wake.set()
        if self.meter is not None:
            self.meter.cancel_polls()
            try:
                self.meter.final(budget_s=METER_FINAL_S - METER_WRITE_MARGIN_S)
            except Exception as exc:  # noqa: BLE001 - the server is closed and the run ends whatever the meter met
                self.meter_errors += 1
                self.emit({"event": "opencode.meter_error", "error": f"final: {type(exc).__name__}: {str(exc)[:200]}"})
        if self._meter_thread is not None:  # a daemon thread: one still in a request ends on its own, never committing
            self._meter_thread.join(max(0.0, METER_FINAL_S - (time.monotonic() - t0)))

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
        spec = self.client.get("/openapi.json", timeout=OPENAPI_TIMEOUT_S)
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
        declared = False
        while True:
            catalog = (self.client.get("/api/model", location(self.directory)) or {}).get("data") or []
            match = next((m for m in catalog if m.get("providerID") == ref["providerID"] and m.get("id") == ref["id"]),
                         None)
            now = time.monotonic()
            # Listed only because the relay projection names it: not offered, so wait for the catalog as if absent.
            declared = match is not None and self._relayed and declared_only(match)
            if declared:
                match = None
            if match is not None:
                variants = [v.get("id") for v in match.get("variants") or []]
                # Each refusal of the pin, here and the catalog's below, names the way on: a new invocation where the
                # pin must change, a relaunch where the cause is outside it (ADR-0010; CS-4 addendum 11; #304 m1).
                if "variant" in ref and ref["variant"] not in variants:
                    raise HarnessIncompatible(
                        f"model {ref['providerID']}/{ref['id']} has no variant {ref['variant']!r} (the pinned effort); "
                        f"it offers {variants or 'none'}; dispatch a new invocation with --profile or --model, or with "
                        "another --effort (a relaunch reuses this one's pin, ADR-0010); once OpenCode offers the "
                        f"variant, relaunch with {self._relaunch_command()}", model=ref)
                if match.get("enabled") is False:
                    raise HarnessIncompatible(f"model {ref['providerID']}/{ref['id']} is disabled in this OpenCode; "
                                              f"enable it in OpenCode and relaunch with {self._relaunch_command()}, "
                                              "or dispatch a new invocation with --profile or --model", model=ref)
                found = {"catalog_wait_s": round(now - t0, 3), "catalog_size": len(catalog), "variants": variants}
                if self._relay is not None:
                    found["relay_family"] = self._require_relay_family(match, catalog, ref)
                return found
            if catalog and first_seen is None:
                first_seen = now
            if now - t0 > CATALOG_WAIT_S or (first_seen is not None and now - first_seen > CATALOG_SETTLE_S):
                providers = sorted({str(m.get("providerID")) for m in catalog})
                raise HarnessIncompatible(
                    f"model {ref['providerID']}/{ref['id']} is not offered by this OpenCode "
                    f"({len(catalog)} models from {providers or 'no provider'} after {now - t0:.0f}s"
                    + ("; it is listed only because AEW names it in the server's configuration, to send it through "
                       "the run's provider relay (F28 §3.5)" if declared else "")
                    + "); check the execution policy and the provider variables it names; if the pinned model is what "
                      "is wrong, dispatch a new invocation with --profile or --model (a relaunch reuses this one's "
                      f"pin, ADR-0010); otherwise fix the variable and relaunch with {self._relaunch_command()}",
                    model=ref,
                    # Timing-dependent (the catalog fills in asynchronously): never read as a lasting incompatibility
                    # (M4-E E8a; PR #185 review, F1).
                    launch_cause=CATALOG_TIMEOUT)
            time.sleep(0.25)

    def _require_relay_family(self, match: dict[str, Any], catalog: list[dict[str, Any]],
                              ref: dict[str, Any]) -> dict[str, Any]:
        """The relay-route check of the pinned model's family (``relay_family``): a mismatch is refused now, naming
        both families and both ways on, rather than at the model's first call; otherwise its result is kept in the
        launch record."""
        assert self._relay is not None
        upstream = self._relay
        found = relay_family(match, catalog, upstream)
        if found["check"] == RELAY_FAMILY_MISMATCH:
            raise HarnessIncompatible(
                f"model {ref['providerID']}/{ref['id']} is a {found['package']} model, but the run's provider relay "
                f"sends only to {upstream}, which this OpenCode's catalog serves "
                f"{', '.join(found['upstream_packages'])} models from, so its requests would go to an endpoint that "
                "does not serve them; dispatch a new invocation with --profile or --model naming a model of a family "
                f"it serves ({', '.join(found['upstream_packages'])}), or the operator sets "
                f"containment.network.upstreams.{ref['providerID']} to an address that serves {found['package']} "
                f"models and relaunches with {self._relaunch_command()}", model=ref, package=found["package"],
                upstream=upstream, upstream_packages=found["upstream_packages"], reason=RELAY_FAMILY_REFUSED)
        return found

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
                                          agents=sorted(str(a.get("id")) for a in agents),
                                          # A wait that ran out, like the catalog's: a slow server and one that ignored
                                          # the configuration look the same here (M4-E E8a; PR #185 review, F3).
                                          launch_cause=AGENT_LOAD_TIMEOUT)
            time.sleep(0.25)

    # ------------------------------------------------------------------ prompts

    def _prompt(self, text: str, delivery: str | None = None) -> str:
        assert self.client is not None and self.session is not None
        mid = new_message_id()
        with self._lock:  # recorded first, so a poll never mistakes the previous turn's idle for this one's
            if self.turn == "ended":  # nothing watches an ended run: reviving it would leave it hanging (audit I3)
                raise HarnessError("this run's harness turn has ended, so the message was not delivered; "
                                   f"relaunch the run to continue it ({self._relaunch_command()})")
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

    def send(self, text: str, delivery: str) -> None:
        # `steer`: at the next step boundary, inside the same turn; `queue`: only when the turn would end, after its
        # last step (the F9-A MS0 probe, P1 and P2). Either way never lost.
        if delivery not in ("steer", "queue"):
            raise HarnessError(f"unknown delivery {delivery!r}: steer or queue")
        self._prompt(text, delivery=delivery)

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
                summary["error"] = error_view(data["error"])
            self.emit(summary)
        if kind == "session.execution.started":
            self._failed = None  # a new execution: an earlier one's failure is not this turn's
        elif kind == "session.execution.failed" and isinstance(data.get("error"), dict):
            self._failed = error_view(data["error"])
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
        self._turn_over(str(idle.get("outcome")), last, _created(delivered))

    def _turn_over(self, outcome: str, last: str, since: float = 0.0) -> None:
        """Close the turn whose last prompt was ``last`` (delivered at ``since``), unless a newer prompt arrived since
        the poll decided."""
        self._meter_wake.set()  # F25 L2: a turn's end is sampled at once, by the meter's own thread
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
            # The messages of this turn (created since its last prompt was delivered) say why it failed; the event
            # stream is the fallback, never the only source. An earlier turn's error is never this one's, and only a
            # failed turn has a reason code (PR #165 review, finding 4).
            mine = [m for m in (self.snapshot or {}).get("assistant", []) if float(m.get("created") or 0) >= since]
            error = (next((m["error"] for m in reversed(mine) if m.get("error")), None)
                     or (self._failed if outcome == "failed" else None))
            reason_code = (REASON_CODES.get(str(error.get("type"))) if isinstance(error, dict) and outcome == "failed"
                           else None)
            detail = f"the agent's turn ended: {outcome}" + (f" ({describe_error(error)})"
                                                              if isinstance(error, dict) else "")
            self._end(EXIT_CODES.get(outcome, 1), detail, reason_code)

    def _end(self, code: int, detail: str, reason_code: str | None = None) -> None:
        with self._lock:
            if self.turn == "ended":
                return
            self.turn, self.exit_code, self.detail, self.reason_code = "ended", code, detail, reason_code
        self.emit({"event": "opencode.ended", "exit_code": code, "detail": detail,
                   **({"reason_code": reason_code} if reason_code else {})})

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
                    "turn": self.turn, "detail": self.detail, "reason_code": self.reason_code}

    def _take_snapshot(self) -> None:
        """Assistant messages' model, usage and errors (never their text), while the server is still up."""
        if self.client is None or self.session is None:
            return
        assistant: list[dict[str, Any]] = []
        params: dict[str, str] = {"order": "asc", "limit": "200"}
        truncated = True  # unless the last page is reached: the bounded loop may stop with a next cursor left (F25 R1)
        loads: dict[str, Any] | None = {"loaded": {}, "other": 0}
        for _ in range(PAGES):
            page = self.client.get(f"/api/session/{self.session}/message", params) or {}
            for m in page.get("data") or []:
                if m.get("type") == "assistant":
                    assistant.append({"model": m.get("model"), "agent": m.get("agent"), "tokens": m.get("tokens"),
                                      "cost": m.get("cost"), "finish": m.get("finish"), "created": _created(m),
                                      "tools": [str(c.get("name")) for c in m.get("content") or []
                                                if isinstance(c, dict) and c.get("type") == "tool"],
                                      "error": error_view(m["error"]) if isinstance(m.get("error"), dict)
                                      else None})
                    loads = self._count_loads(loads, m)
            nxt = (page.get("cursor") or {}).get("next")
            if not nxt:
                truncated = False
                break
            params = {"cursor": str(nxt), "limit": "200"}
        info = (self.client.get(f"/api/session/{self.session}") or {}).get("data") or {}
        self.snapshot = {"assistant": assistant, "session": {k: info.get(k) for k in ("outcome", "tokens", "cost")},
                         "truncated": truncated, "skill_loads": loads}
        # Every other session in the run's private state (a subagent's, or anyone's): recorded even if the event
        # stream missed its creation. Listed unfiltered: the server is the run's alone (F25 plan v4, m1).
        for other in (self.client.get("/api/session") or {}).get("data") or []:
            sid = other.get("id")
            if sid and sid != self.session and sid not in self.foreign_sessions:
                self.foreign_sessions.append(str(sid))

    def _count_loads(self, loads: dict[str, Any] | None, message: dict[str, Any]) -> dict[str, Any] | None:
        """``loads`` with one assistant message's ``skill`` calls added (:func:`skill_loads`), or None, for good, once
        any reading fails. It runs on the poll path and at teardown, where an error would end the run or lose its
        snapshot, so nothing here can raise: telemetry never hurts a run (the 2026-11-04 ruling, §5)."""
        if loads is None:
            return None
        try:
            exposed = frozenset((getattr(self, "skills", None) or {}).get("exposed") or ())
            ids, other = skill_loads(message.get("content"), exposed)
            for sid in ids:
                loads["loaded"][sid] = loads["loaded"].get(sid, 0) + 1
            loads["other"] += other
            return loads
        except Exception:  # noqa: BLE001 - unknown, never a failed run (ruling of 2026-11-04, §5)
            return None

    def terminate(self) -> None:
        self._stop.set()
        self._wake.set()
        self._final_sample()  # fresh, whatever self.snapshot holds (m7), before the lease ends
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
                               "poll_errors": self.poll_errors, "skills": getattr(self, "skills", None),
                               "meter_errors": self.meter_errors + (self.meter.errors if self.meter else 0)}
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
            # The one exception to that (the 2026-11-04 ruling, §5): which exposed skills it loaded, and how many other
            # `skill` calls it made, never their ids. Telemetry only: nothing reads it as a gate, evidence or state.
            # Unknown stays unknown: absent with no snapshot, a truncated one, or any failure reading it.
            loads = snap.get("skill_loads")
            if isinstance(loads, dict) and not snap.get("truncated"):
                try:
                    found = (dict(sorted(loads["loaded"].items())), int(loads["other"]))
                except Exception:  # noqa: BLE001 - a lost result would lose the run's record (supervisor `_end`)
                    found = None
                if found is not None:
                    out["loaded"], out["skill_other"] = found
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


def skill_loads(content: Any, exposed: frozenset[str]) -> tuple[list[str], int]:
    """One assistant message's ``skill`` calls: ``(ids loaded, other calls)``. A load is a content part with ``type``
    ``tool``, ``name`` ``skill``, ``state.status`` ``completed`` and ``state.input`` a mapping whose ``id`` is a string
    the run exposed. Anything else named ``skill`` (a denied or unknown id, a failed or pending call, a streaming part
    whose input is still a string) is only counted: its id is the model's text and is never kept. Every ``skill`` part
    is one or the other, so their sum is ``tools_called["skill"]``."""
    loaded: list[str] = []
    other = 0
    for part in content or []:
        if not isinstance(part, dict) or part.get("type") != "tool" or str(part.get("name")) != "skill":
            continue
        state = part.get("state")
        status = state.get("status") if isinstance(state, dict) else None
        given = state.get("input") if isinstance(state, dict) else None
        sid = given.get("id") if isinstance(given, dict) else None
        if status == "completed" and isinstance(sid, str) and sid in exposed:
            loaded.append(sid)
        else:
            other += 1
    return loaded, other


def error_view(error: dict[str, Any]) -> dict[str, Any]:
    """What AEW keeps of a provider error in its own records (the event log, the run record, the snapshot): its type
    and status, and its message unless it may concern a credential. A provider's authentication message can quote part
    of the key (OpenAI's names it, masked), and AEW records no key or part of one (register V1): only the variable's
    name appears, in the next action. This fails closed: the message goes for an auth-like type or a credential status,
    and key-shaped text is redacted from every message kept. (The harness's own private state, under the run's
    ``harness/`` directory, keeps whatever the harness itself stores.)"""
    out: dict[str, Any] = {"type": error.get("type")}
    if error.get("status") is not None:
        out["status"] = error.get("status")
    if not credential_related(error) and error.get("message") is not None:
        out["message"] = redact_key_shaped(str(error.get("message")))
    return out


def credential_related(error: dict[str, Any]) -> bool:
    status = error.get("status")
    return "auth" in str(error.get("type") or "").lower() or (isinstance(status, int) and status in CREDENTIAL_STATUSES)


def describe_error(error: dict[str, Any]) -> str:
    status = f", {error['status']}" if error.get("status") is not None else ""
    message = f": {error['message']}" if error.get("message") else ""
    return f"{error.get('type')}{status}{message}"


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
