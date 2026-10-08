"""The Lead bridge: Lead custody for a Lead harness session (ADR-0009; ADR-0005 amendment).

Invariant (operator requirement): the Lead's model can request Lead operations **without receiving the
raw Lead credential**. ``aew lead session -- <harness command>`` holds the Lead credential in its own
memory, serves a Lead bridge, and runs the Lead's harness (an OpenCode TUI in ``aew opencode``) with
only the bridge's coordinates in its environment. The ``aew`` CLI routes every Lead-authenticated
command to the bridge when no credential is supplied, and the broker runs the same command handler with
the held credential, so the engine's checks (current Lead, expected revision) stay authoritative.

It is the invocation bridge (``bridge.BridgeServer``: JSON only, key challenge, exact arguments,
redaction, drain) with these operations: ``lead.cli {argv, cwd, stdin}`` relays one Lead-authenticated command,
``lead.whoami`` says whether the session still holds authority, and ``lead.tool {name, arguments, ingress, profile}``
runs one call of the typed Lead surface (``aew.surface``; F15.1) with the held credential. The broker additionally
refuses:

* every Lead-authenticated command that is not classified **Lead-reachable** (``LEAD_REACHABLE``): the
  operator-only ones (``OPERATOR_ONLY``: commands that would print a credential, offer secret or session URL, so Lead
  acquisition, handoff, takeover and release stay operator actions at the operator's own terminal; commands the
  operator confirms there; and the operator's own decisions, which the Lead must not make for them), the typed
  surface's own transports (``NOT_RELAYED``), and any command nobody has classified yet (fail closed). The same
  check runs in the ``aew`` client and in the broker, for a shell command and for the typed ``cli`` escape alike;
* dispatches without ``--launch`` (they print an invocation credential into the Lead's transcript);
* an explicit ``--token`` (the session never needs one) and any project other than its own.

``lead.tool`` is a cooperative bridge operation: it serializes its own engine calls, so a typed ``harness_wait``
blocks on the wake file without holding up any other request. Its dispatches are recorded with the channel of the
transport that carried them: ``lead_mcp`` for the MCP server, ``lead_broker`` for ``aew lead tool``.

When the held credential stops being the current Lead's (takeover, an accepted handoff, release elsewhere), the
broker refuses and closes its bridge; the Lead's harness keeps running as a read-only session. A pending handoff
does not end authority: requests reach the engine, which refuses everything but `lead handoff cancel`.

The Lead's harness runs in an owned process tree (:func:`aew.harness.procs.run_session_tree`): nothing it starts
outlives it, and an acquired seat is released only once that is proven, so no leftover process can take the seat.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from aew import errors
from aew.engine import dispatch
from aew.engine.authority import require_lead
from aew.harness import bridge
from aew.util import read_text_input

ENV_ENDPOINT = "AEW_LEAD_BROKER"
ENV_KEY = "AEW_LEAD_BROKER_KEY"
ENV_NAMES = (ENV_ENDPOINT, ENV_KEY)
OPERATIONS: bridge.Operations = {"lead.cli": {"argv": list, "cwd": str, "stdin": str},
                                 "lead.whoami": {},  # does this session hold Lead authority? (M3-D10)
                                 # one typed Lead surface call (F15.1): arguments are JSON text
                                 "lead.tool": {"name": str, "arguments": str, "ingress": str, "profile": str}}
COOPERATIVE = frozenset({"lead.tool"})
INGRESS_CHANNEL = {"mcp": "lead_mcp", "cli": "lead_broker"}  # provenance only, never legality

CREDENTIAL_EMITTING = (frozenset({"lead", "acquire"}), frozenset({"lead", "takeover"}), frozenset({"lead", "release"}),
                       frozenset({"lead", "handoff", "offer"}), frozenset({"lead", "handoff", "accept"}),
                       # the dashboard's one-time session URL (ADR-0005, 2026-10-05; F20.3)
                       frozenset({"dashboard", "serve"}), frozenset({"dashboard", "open"}))
# Commands the operator confirms with a typed-back code at their own terminal, which a Lead session has none of:
# resetting the validation circuit breaker (M4-D5; the breaker stops automatic retries until the operator says so).
OPERATOR_CONFIRMED = (frozenset({"integrate", "breaker", "reset"}),)
# The operator's decisions (operator, 2026-10-06): what governs the project and its state, which a Lead session must
# not be able to make, or record as the operator's, on its own. Authority sources become the files every pack treats
# as governing, and `authority accept --decided-by operator` would otherwise let the Lead record the operator's
# sign-off; `manifest adopt` is the approval of an edit to project.yaml, which the actor that can edit the file must not
# also hold; `migrate` restructures the control state and is not easily reverted. Waivers, history loads and audits
# stay the Lead's: policy bounds a waiver, and the others only add reference context or verify.
OPERATOR_DECIDED = (frozenset({"authority", "accept"}), frozenset({"authority", "reject"}),
                    frozenset({"manifest", "adopt"}), frozenset({"migrate"}))
# Arguments that record a decision as the operator's (operator, 2026-10-06: "if my name is attached to it I should have
# actually approved"): the command asks the operator at their own terminal (`operator.require_operator_attribution`),
# so a Lead session may run the command but never with this argument.
OPERATOR_ATTRIBUTED = {frozenset({"work", "staff"}): ("by", "operator"),
                       frozenset({"authority", "accept"}): ("decided_by", "operator")}
# Commands only the operator runs, at their own terminal: never relayed, never a typed tool (A1 §1 adds the
# operator's confirmation, autonomy increases and PUBLISH_IF_CLEAN grants here when F15.5 builds them).
OPERATOR_ONLY = CREDENTIAL_EMITTING + OPERATOR_CONFIRMED + OPERATOR_DECIDED
# The typed surface's own transports: they reach the broker through `lead.tool`, never through `lead.cli`.
NOT_RELAYED = (frozenset({"lead", "tool"}), frozenset({"lead", "mcp"}))
# Every Lead-authenticated command a Lead session may relay. Fail closed: a Lead-authenticated command missing from
# here and from OPERATOR_ONLY is refused until someone classifies it (a test walks the parser).
LEAD_REACHABLE = frozenset(frozenset(path.split()) for path in (
    "checkpoint", "evidence ingest", "gate waive", "harness interrupt",
    "harness launch", "harness send", "harness stop", "history audit", "history load", "integrate defer",
    "integrate prepare", "integrate publish", "integrate reconcile", "integrate reorder", "integrate requeue",
    "integrate validate",
    "invoke cancel", "invoke create", "lead handoff cancel",
    "map generate", "map select-architecture",  # derived map state under .aew/local/maps/ only (ADR-0015)
    "plan accept", "plan adopt",
    "plan propose", "plan reconfirm", "review ingest", "verify classify", "verify ingest", "work accept",
    "work acknowledge-input", "work assign", "work cancel", "work close", "work create", "work depend",
    "work dispatch", "work move", "work promote", "work reclassify", "work reconcile", "work redispatch",
    "work staff", "work transition",
))
DISPATCHES = (frozenset({"work", "assign"}), frozenset({"work", "dispatch"}), frozenset({"work", "redispatch"}),
              frozenset({"invoke", "create"}))
POLL_S = 1.0


def command_path(ns: argparse.Namespace) -> frozenset[str]:
    """The sub-command names of a parsed command (``aew lead handoff offer`` -> {lead, handoff, offer})."""
    names = {ns.command} if getattr(ns, "command", None) else set()
    names |= {v for k, v in vars(ns).items() if k.endswith("_cmd") and isinstance(v, str)}
    return frozenset(names)


def command_name(ns: argparse.Namespace) -> str:
    """The command as typed (``lead handoff offer``), for a refusal to name: argparse sets the command, then each
    sub-command, in order (the path above is a set; sorted, it named commands that do not exist; PR #91 re-review)."""
    names = [ns.command] if getattr(ns, "command", None) else []
    names += [v for k, v in vars(ns).items() if k.endswith("_cmd") and isinstance(v, str)]
    return " ".join(names)


def refuses_locally(ns: argparse.Namespace) -> str | None:
    """Inside a Lead session, why this command may not run here, or ``None``: an operator-only command, or a
    Lead-authenticated command nobody has classified Lead-reachable (fail closed). The one reachability check: the
    ``aew`` client applies it before relaying, and the broker again before it runs anything."""
    path = command_path(ns)
    if any(p <= path for p in OPERATOR_CONFIRMED):
        return (f"`aew {command_name(ns)}` is confirmed by the operator with a code typed at their own terminal; "
                "a Lead session cannot run it: ask the operator")
    if any(p <= path for p in OPERATOR_DECIDED):
        return (f"`aew {command_name(ns)}` is the operator's decision, made at their own terminal; a Lead session "
                "cannot run it or record it as theirs: ask the operator")
    dest, value = OPERATOR_ATTRIBUTED.get(path, ("", None))
    if value is not None and getattr(ns, dest, None) == value:
        return (f"`aew {command_name(ns)}` with `--{dest.replace('_', '-')} {value}` records the decision as the "
                "operator's, which only the operator confirms, at their own terminal: run it without that flag "
                "(as the Lead's), or ask the operator")
    if any(p <= path for p in OPERATOR_ONLY):
        return (f"`aew {command_name(ns)}` would put a Lead credential, offer secret or dashboard session URL "
                "into this session; Lead acquisition, handoff, takeover and release, and the dashboard's session, are "
                "operator actions at the operator's own terminal")
    if hasattr(ns, "token") and path not in LEAD_REACHABLE and path not in NOT_RELAYED:
        return (f"`aew {command_name(ns)}` is not classified as reachable from a Lead session; it is refused "
                "until it is (lead_broker.LEAD_REACHABLE or OPERATOR_ONLY)")
    return None


class LeadBroker:
    """Holds one Lead credential in memory and serves the Lead bridge for one project."""

    def __init__(self, engine: Any, token: str) -> None:
        self.engine = engine
        self._token = token
        state = engine.store.read()
        self._require_lead(state, token)  # only the current Lead's credential is ever brokered
        self.generation = int(state["lead"]["generation"])  # the generation this session acts for
        self.session_label = state["lead"].get("session_label")
        self.server = bridge.BridgeServer(self.handle, OPERATIONS, COOPERATIVE)
        self.superseded: str | None = None
        self._stop = threading.Event()
        self._watch = threading.Thread(target=self._watchdog, name="aew-lead-broker-watch", daemon=True)

    @property
    def env(self) -> dict[str, str]:
        return {ENV_ENDPOINT: self.server.address, ENV_KEY: self.server.key_hex}

    def start(self) -> None:
        self.server.start()
        self._watch.start()

    def close(self) -> None:
        self._stop.set()
        self.server.close()
        self.server.drain(60)
        if self._watch.is_alive():
            self._watch.join(60)  # a check in progress finishes before the credential goes (M3-D11)
        self._token = ""

    def _require_lead(self, state: dict[str, Any], token: str) -> None:
        """The current Lead's credential, or refused; an archived one is stale authority (ADR-0011 R7) when the engine
        keeps an archive."""
        archived = getattr(self.engine, "archived_credential", None)
        require_lead(state, token, **({"archived": archived} if archived else {}))

    def _authority_lost(self) -> str | None:
        """Why the held credential is no longer the current Lead's, or ``None`` while it is. Only lost authority
        counts: a pending handoff (or any other refusal) is the engine's to report per request, and the Lead may still
        cancel the handoff."""
        token = self._token  # taken before the (possibly slow) read: close() may clear it meanwhile (M3-D11)
        try:
            self._require_lead(self.engine.store.read(), token)
        except errors.StaleAuthority as exc:
            return exc.message
        except errors.AEWError:
            return None
        return None

    def _watchdog(self) -> None:
        while not self._stop.wait(POLL_S):
            problem = self._authority_lost()
            if problem and not self._stop.is_set():
                self.superseded = problem
                self.server.close()
                return

    # ------------------------------------------------------------------ the one operation

    def handle(self, op: str, args: dict[str, Any]) -> Any:
        if op == "lead.tool":  # cooperative: it takes the serialization itself
            return self._tool(args)
        problem = self._authority_lost()
        if problem:
            self.superseded = problem
            self.server.close()
            raise errors.StaleAuthority(f"this Lead session no longer holds Lead authority: {problem}")
        if op == "lead.whoami":
            lead = self.engine.store.read()["lead"]
            return {"generation": lead["generation"], "session_label": lead.get("session_label")}
        return self._run_cli(list(args["argv"]), args["cwd"], args["stdin"])

    def _run_cli(self, argv: list[str], cwd: str, stdin: str) -> dict[str, Any]:
        return run_cli(self.engine, self._token, argv, cwd, stdin, channel="lead_broker")

    # ------------------------------------------------------------------ the typed surface (F15.1)

    def _session(self, problem: str | None) -> dict[str, Any]:
        out: dict[str, Any] = {"holds": problem is None, "generation": self.generation,
                               "session_label": self.session_label}
        if problem:
            out["detail"] = problem
        return out

    def _cancelled(self) -> str | None:
        """For a cooperative wait, checked under the serialization: why this session can no longer act."""
        return self._authority_lost() or ("this Lead session's bridge closed" if self.server.closed else None)

    def _tool(self, args: dict[str, Any]) -> dict[str, Any]:
        """One typed surface call. The answer is ``{"stage_result": ...}`` for every well-formed call (an engine
        refusal and lost authority included), or ``{"adapter_input_error": ...}`` when the call never reached the
        runner. When authority is lost the session still answers once from committed state, then closes."""
        from aew.surface import run as surface_run
        from aew.surface.context import PROFILES, SurfaceContext
        from aew.surface.validate import AdapterInputError, check_call

        ingress, profile, name = args["ingress"], args["profile"], args["name"]
        if ingress not in INGRESS_CHANNEL or profile not in PROFILES:
            raise errors.UsageError("lead.tool: unknown ingress or surface profile", ingress=ingress, profile=profile)
        try:
            arguments = json.loads(args["arguments"])
            check_call(name, arguments, profile)  # before any engine call: an ill-formed call commits nothing
        except ValueError:
            return {"adapter_input_error": AdapterInputError(
                "INVALID_ARGUMENTS", f"{name}: the arguments are not JSON").to_dict()}
        except AdapterInputError as exc:
            return {"adapter_input_error": exc.to_dict()}
        channel = INGRESS_CHANNEL[ingress]

        def cli(argv: list[str], stdin: str) -> dict[str, Any]:
            return run_cli(self.engine, self._token, argv, str(self.engine.repo_root), stdin, channel=channel)

        with dispatch.channel(channel):
            if name == "harness_wait":
                with self.server.serialized():
                    problem = self._authority_lost()
                ctx = SurfaceContext(lead_session=self._session(problem), generation=self.generation,
                                     profile=profile, ingress=ingress)
                result = surface_run.run_tool(self.engine, ctx, name, arguments, token=self._token,
                                              serial=self.server.serialized, cancelled=self._cancelled)
            else:
                with self.server.serialized():
                    problem = self._authority_lost()
                    ctx = SurfaceContext(lead_session=self._session(problem), generation=self.generation,
                                         profile=profile, ingress=ingress)
                    result = surface_run.run_tool(self.engine, ctx, name, arguments, token=self._token,
                                                  run_cli=cli)
        if result["stopped"] and result["stopped"]["boundary"] == "stale_authority":
            with self.server.serialized():
                lost = self._authority_lost()
            if lost:  # answered once from committed state; from now on the bridge is closed
                self.superseded = lost
                self.server.close()
        return {"stage_result": result}


def run_cli(engine: Any, token: str, argv: list[str], cwd: str, stdin: str, *, channel: str) -> dict[str, Any]:
    """Run one Lead-authenticated ``aew`` command with ``token``, with every refusal a Lead session has: the relay of
    a shell command (``lead.cli``) and the typed surface's ``cli`` escape both come here. The caller serializes:
    the process-wide cwd and stdin swap below needs it."""
    from aew.cli.main import build_parser
    from aew.engine.api import Engine

    parser = build_parser()
    stdin_stream = io.StringIO(stdin)  # one input, read once: by --fields - or by the command, as in the direct CLI
    argv = _expand_fields(argv, parser, stdin_stream, cwd)
    noise = io.StringIO()
    try:
        with contextlib.redirect_stderr(noise), contextlib.redirect_stdout(noise):
            ns = parser.parse_args(argv)
    except SystemExit:
        raise errors.UsageError(f"invalid command: {noise.getvalue().strip()[-400:]}") from None
    if not hasattr(ns, "token") or getattr(ns, "handler", None) is None:
        raise errors.PermissionDenied("the Lead bridge runs only Lead-authenticated commands; run this one "
                                      "directly", command=sorted(command_path(ns)))
    refusal = refuses_locally(ns)
    if refusal:
        raise errors.PermissionDenied(refusal)
    path = command_path(ns)
    if path in NOT_RELAYED:
        raise errors.PermissionDenied(f"`aew {command_name(ns)}` is a transport of the typed Lead surface; it "
                                      "is never relayed and never nested in its own cli escape")
    if getattr(ns, "print_credential", False):
        raise errors.PermissionDenied("--print-credential is refused in a Lead session: a credential never goes "
                                      "into the Lead's transcript")
    if ns.token:
        raise errors.UsageError("do not pass --token in a Lead session: the session holds the Lead credential")
    if any(p <= path for p in DISPATCHES) and not getattr(ns, "launch", False):
        raise errors.PermissionDenied(
            "in a Lead session, dispatch with --launch: without it the dispatch prints an invocation credential "
            "into this session (the run's supervisor takes custody instead)")
    target = Path(cwd).resolve()
    if Engine.discover(target).aew_root != engine.aew_root:
        raise errors.PermissionDenied("this Lead session brokers a different AEW project",
                                      project=str(engine.aew_root))
    ns.token = token
    ns.cwd = str(target)
    previous = os.getcwd()
    stdin_before = sys.stdin
    try:  # requests are serialized, so the process-wide cwd/stdin swap is safe here
        os.chdir(target)
        sys.stdin = stdin_stream
        with dispatch.channel(channel):  # its dispatches record which transport carried them (M4-A)
            result = ns.handler(ns)
    finally:
        sys.stdin = stdin_before
        os.chdir(previous)
    return {"result": result, "json": bool(getattr(ns, "json", False))}


def _expand_fields(argv: list[str], parser: argparse.ArgumentParser, stdin: io.StringIO, cwd: str) -> list[str]:
    """``--fields FILE|-`` expanded as the ``aew`` client does, with this call's stdin and a FILE read from its
    directory, before anything is parsed or checked. A shell command relayed through ``lead.cli`` arrives already
    expanded (its client did it), so for it this changes nothing; the typed ``cli`` escape submits its argv as given
    (PR #93 review). Expanded values are checked like any other argument afterwards."""
    from aew.cli import fields

    if not any(a == fields.OPTION or a.startswith(fields.OPTION + "=") for a in argv):
        return argv
    previous, stdin_before = os.getcwd(), sys.stdin
    try:  # requests are serialized, so the process-wide swap is safe here
        try:
            os.chdir(Path(cwd).resolve())
        except OSError as exc:
            raise errors.UsageError(f"cannot use {cwd} as the command's directory: {exc.strerror or exc}") from None
        sys.stdin = stdin
        return fields.expand(argv, parser)
    finally:
        sys.stdin = stdin_before
        os.chdir(previous)


def forward(argv: list[str], args: argparse.Namespace) -> dict[str, Any]:
    """Client side: send a Lead-authenticated command to this Lead session's broker."""
    stdin = read_text_input("-") if "-" in argv else ""  # decoded here like any text input; parsed by the broker
    cwd = str(Path(args.cwd or os.getcwd()).resolve())
    return bridge.call("lead.cli", {"argv": list(argv), "cwd": cwd, "stdin": stdin}, env_names=ENV_NAMES)


def session_authority() -> dict[str, Any] | None:
    """Inside a Lead session, whether this session's broker holds the current Lead's authority (M3-D10): a read-only
    command such as `aew resume` runs without the broker and would otherwise assume that its reader holds none.
    ``None`` outside a Lead session."""
    if not os.environ.get(ENV_ENDPOINT):
        return None
    try:
        who = bridge.call("lead.whoami", {}, env_names=ENV_NAMES)
    except errors.AEWError as exc:
        return {"holds": False, "detail": exc.message}
    return {"holds": True, **(who or {})}


def routes(args: argparse.Namespace) -> bool:
    """A Lead-authenticated command with no credential of its own, inside a Lead session. The typed surface's own
    transports never go through ``lead.cli``: they reach the broker through ``lead.tool`` themselves."""
    return (hasattr(args, "token") and not args.token and not os.environ.get("AEW_LEAD_TOKEN")
            and bool(os.environ.get(ENV_ENDPOINT)) and command_path(args) not in NOT_RELAYED)


def run_session(engine: Any, command: list[str], *, acquire: bool, session_label: str | None,
                keep_seat: bool, env: dict[str, str] | None = None) -> dict[str, Any]:
    """``aew lead session``: broker the Lead credential for one Lead harness session.

    ``env`` is the harness's environment (default: the caller's, minus every credential variable). A harness
    adapter passes a curated one (``aew opencode``); the broker's coordinates are added either way.
    """
    from aew.engine.harness_ops import supervisor_env
    from aew.harness.procs import harden_current_process, run_session_tree

    if not command:
        raise errors.UsageError("name the Lead's harness command after `--`, e.g. `aew lead session -- opencode-cli`")
    harden_current_process()  # this process holds the Lead credential (Linux: not inspectable by its child)
    held = os.environ.pop("AEW_LEAD_TOKEN", "")  # in memory only: never inherited by git, hooks or any child
    if acquire:
        token = engine.lead_acquire(expect_rev=engine.store.read()["revision"], session_label=session_label)["token"]
    else:
        token = held
        if not token:
            raise errors.UsageError("a Lead session needs the Lead credential: set AEW_LEAD_TOKEN in your own shell "
                                    "(it is removed from the session's environment), or take a vacant seat with "
                                    "--acquire (the credential then exists only inside this session)")
    broker = LeadBroker(engine, token)
    broker.start()
    child_env = {**(supervisor_env() if env is None else supervisor_env(env)), **broker.env}
    try:
        code, ownership = run_session_tree(command, env=child_env, cwd=str(engine.repo_root))
    finally:
        broker.close()
    out: dict[str, Any] = {"ok": True, "exit": code, "superseded": broker.superseded, "processes": ownership}
    state = engine.store.read()
    if acquire and not broker.superseded:
        active = sorted(i for i, inv in state["invocations"].items() if inv["status"] == "active")
        if ownership != "clean":
            out["seat"] = ("held; "
                           + ("processes started by the Lead's harness could not all be ended"
                              if ownership == "survivors" else "this platform cannot prove that no process started by "
                              "the Lead's harness is still running")
                           + ", so the seat stays held and none of them can take it; continue with `aew lead "
                           "takeover` at your own terminal")
        elif keep_seat or active:
            out["seat"] = ("held; the Lead credential existed only inside this session, so continuing needs "
                           "`aew lead takeover` at your own terminal" + (f" (active: {', '.join(active)})"
                                                                         if active else ""))
        else:
            engine.lead_release(token=token, expect_rev=state["revision"])
            out["seat"] = "released"
    else:
        out["seat"] = "held by your AEW_LEAD_TOKEN" if not broker.superseded else "superseded"
    del token, held
    return out
