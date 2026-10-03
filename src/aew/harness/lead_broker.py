"""The Lead bridge: Lead custody for a Lead harness session (ADR-0009; ADR-0005 amendment).

Invariant (operator requirement): the Lead's model can request Lead operations **without receiving the
raw Lead credential**. ``aew lead session -- <harness command>`` holds the Lead credential in its own
memory, serves a Lead bridge, and runs the Lead's harness (an OpenCode TUI in ``aew opencode``) with
only the bridge's coordinates in its environment. The ``aew`` CLI routes every Lead-authenticated
command to the bridge when no credential is supplied, and the broker runs the same command handler with
the held credential, so the engine's checks (current Lead, expected revision) stay authoritative.

It is the invocation bridge (``bridge.BridgeServer``: JSON only, key challenge, exact arguments,
redaction, drain) with one operation, ``lead.cli {argv, cwd, stdin}``. The broker additionally refuses:

* commands that would print a credential: ``lead acquire|takeover|release``, ``lead handoff offer|accept``
  (handoff, takeover and release stay operator actions at the operator's own terminal);
* dispatches without ``--launch`` (they print an invocation credential into the Lead's transcript);
* an explicit ``--token`` (the session never needs one) and any project other than its own.

When the held credential stops being the current Lead's (takeover, handoff, release elsewhere), the
broker refuses and closes its bridge. The Lead's harness keeps running as a read-only session.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
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
                                 "lead.whoami": {}}  # does this session hold Lead authority? (M3-D10)

CREDENTIAL_EMITTING = (frozenset({"lead", "acquire"}), frozenset({"lead", "takeover"}), frozenset({"lead", "release"}),
                       frozenset({"lead", "handoff", "offer"}), frozenset({"lead", "handoff", "accept"}))
DISPATCHES = (frozenset({"work", "assign"}), frozenset({"work", "dispatch"}), frozenset({"work", "redispatch"}),
              frozenset({"invoke", "create"}))
POLL_S = 1.0


def command_path(ns: argparse.Namespace) -> frozenset[str]:
    """The sub-command names of a parsed command (``aew lead handoff offer`` -> {lead, handoff, offer})."""
    names = {ns.command} if getattr(ns, "command", None) else set()
    names |= {v for k, v in vars(ns).items() if k.endswith("_cmd") and isinstance(v, str)}
    return frozenset(names)


def refuses_locally(ns: argparse.Namespace) -> str | None:
    """Inside a Lead session, commands that would print a credential are refused before they run."""
    path = command_path(ns)
    if any(p <= path for p in CREDENTIAL_EMITTING):
        return (f"`aew {' '.join(sorted(path))}` would put a Lead credential or offer secret into this session; "
                "Lead acquisition, handoff, takeover and release are operator actions at the operator's own terminal")
    return None


class LeadBroker:
    """Holds one Lead credential in memory and serves the Lead bridge for one project."""

    def __init__(self, engine: Any, token: str) -> None:
        self.engine = engine
        self._token = token
        self._require_lead(engine.store.read(), token)  # only the current Lead's credential is ever brokered
        self.server = bridge.BridgeServer(self.handle, OPERATIONS)
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

    def _authority_problem(self) -> str | None:
        token = self._token  # taken before the (possibly slow) read: close() may clear it meanwhile (M3-D11)
        try:
            self._require_lead(self.engine.store.read(), token)
        except errors.AEWError as exc:
            return exc.message
        return None

    def _watchdog(self) -> None:
        while not self._stop.wait(POLL_S):
            problem = self._authority_problem()
            if problem and not self._stop.is_set():
                self.superseded = problem
                self.server.close()
                return

    # ------------------------------------------------------------------ the one operation

    def handle(self, op: str, args: dict[str, Any]) -> Any:
        problem = self._authority_problem()
        if problem:
            self.superseded = problem
            self.server.close()
            raise errors.StaleAuthority(f"this Lead session no longer holds Lead authority: {problem}")
        if op == "lead.whoami":
            lead = self.engine.store.read()["lead"]
            return {"generation": lead["generation"], "session_label": lead.get("session_label")}
        return self._run_cli(list(args["argv"]), args["cwd"], args["stdin"])

    def _run_cli(self, argv: list[str], cwd: str, stdin: str) -> dict[str, Any]:
        from aew.cli.main import build_parser
        from aew.engine.api import Engine

        parser = build_parser()
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
        if ns.token:
            raise errors.UsageError("do not pass --token in a Lead session: the session holds the Lead credential")
        path = command_path(ns)
        if any(p <= path for p in DISPATCHES) and not getattr(ns, "launch", False):
            raise errors.PermissionDenied(
                "in a Lead session, dispatch with --launch: without it the dispatch prints an invocation credential "
                "into this session (the run's supervisor takes custody instead)")
        target = Path(cwd).resolve()
        if Engine.discover(target).aew_root != self.engine.aew_root:
            raise errors.PermissionDenied("this Lead session brokers a different AEW project",
                                          project=str(self.engine.aew_root))
        ns.token = self._token
        ns.cwd = str(target)
        previous = os.getcwd()
        stdin_before = sys.stdin
        try:  # requests are serialized by the bridge, so the process-wide cwd/stdin swap is safe here
            os.chdir(target)
            sys.stdin = io.StringIO(stdin)
            with dispatch.channel("lead_broker"):  # its dispatches record that the broker relayed them (M4-A)
                result = ns.handler(ns)
        finally:
            sys.stdin = stdin_before
            os.chdir(previous)
        return {"result": result, "json": bool(getattr(ns, "json", False))}


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
    """A Lead-authenticated command with no credential of its own, inside a Lead session."""
    return (hasattr(args, "token") and not args.token and not os.environ.get("AEW_LEAD_TOKEN")
            and bool(os.environ.get(ENV_ENDPOINT)))


def run_session(engine: Any, command: list[str], *, acquire: bool, session_label: str | None,
                keep_seat: bool, env: dict[str, str] | None = None) -> dict[str, Any]:
    """``aew lead session``: broker the Lead credential for one Lead harness session.

    ``env`` is the harness's environment (default: the caller's, minus every credential variable). A harness
    adapter passes a curated one (``aew opencode``); the broker's coordinates are added either way.
    """
    from aew.engine.harness_ops import supervisor_env
    from aew.harness.procs import harden_current_process

    if not command:
        raise errors.UsageError("name the Lead's harness command after `--`, e.g. `aew lead session -- opencode-cli`")
    harden_current_process()  # this process holds the Lead credential (Linux: not inspectable by its child)
    if acquire:
        token = engine.lead_acquire(expect_rev=engine.store.read()["revision"], session_label=session_label)["token"]
    else:
        token = os.environ.get("AEW_LEAD_TOKEN") or ""
        if not token:
            raise errors.UsageError("a Lead session needs the Lead credential: set AEW_LEAD_TOKEN in your own shell "
                                    "(it is removed from the session's environment), or take a vacant seat with "
                                    "--acquire (the credential then exists only inside this session)")
    broker = LeadBroker(engine, token)
    broker.start()
    child_env = {**(supervisor_env() if env is None else supervisor_env(env)), **broker.env}
    try:
        code = subprocess.call(command, env=child_env, cwd=str(engine.repo_root))
    finally:
        broker.close()
    out: dict[str, Any] = {"ok": True, "exit": code, "superseded": broker.superseded}
    state = engine.store.read()
    if acquire and not broker.superseded:
        active = sorted(i for i, inv in state["invocations"].items() if inv["status"] == "active")
        if keep_seat or active:
            out["seat"] = ("held; the Lead credential existed only inside this session, so continuing needs "
                           "`aew lead takeover` at your own terminal" + (f" (active: {', '.join(active)})"
                                                                         if active else ""))
        else:
            engine.lead_release(token=token, expect_rev=state["revision"])
            out["seat"] = "released"
    else:
        out["seat"] = "held by your AEW_LEAD_TOKEN" if not broker.superseded else "superseded"
    del token
    return out
