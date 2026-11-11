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
runs one call of the typed Lead surface (``aew.surface``; F15.1) with the held credential, and appends one line for it
to the per-call typed-tool log (``aew.harness.tool_calls``; M4-E E5a). The broker additionally refuses:

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
import math
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aew import errors, lead_credential
from aew.engine import dispatch, faults
from aew.engine.authority import require_held_lead, require_lead
from aew.harness import agentenv, bridge, broker_liveness, steering_loop, tool_calls
from aew.util import read_text_input, stdin_only

ENV_ENDPOINT = "AEW_LEAD_BROKER"
ENV_KEY = "AEW_LEAD_BROKER_KEY"
ENV_NAMES = (ENV_ENDPOINT, ENV_KEY)
OPERATIONS: bridge.Operations = {"lead.cli": {"argv": list, "cwd": str, "stdin": str},
                                 "lead.whoami": {},  # does this session hold Lead authority? (M3-D10)
                                 # one typed Lead surface call (F15.1): arguments are JSON text
                                 "lead.tool": {"name": str, "arguments": str, "ingress": str, "profile": str},
                                 # one read relayed for the contained Lead (RELAYED_READS)
                                 "lead.read": {"argv": list, "cwd": str}}
COOPERATIVE = frozenset({"lead.tool", "lead.read"})
# Provenance. Its values also pick the refusal text of a command kept out of a Lead session (:func:`run_cli`).
INGRESS_CHANNEL = {"mcp": "lead_mcp", "cli": "lead_broker"}

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
# The operator endpoint and its client commands (M4-E plan v3 §2.1; A1 §1.1): an autonomy increase is the operator's,
# through the endpoint, so a Lead session can neither run the endpoint nor ask it for anything. `lead mode lower` is a
# separate command, so this path-based refusal refuses the raise only (plan v3 E2, M1). M4-E E6b, E7c and E8b add the
# grants, `confirm` and the relaunch breaker reset's client command here (plan v3 amendment 1, §4). `notify desktop`
# is the endpoint's notifier: what it shows on the operator's desktop is never an agent's text (A-44).
OPERATOR_ENDPOINT = (frozenset({"lead", "mode", "raise"}), frozenset({"operator", "serve"}),
                     frozenset({"operator", "ping"}), frozenset({"notify", "desktop"}))
# The capability register's operator changes (STG-15, CAP-1; the designer's ruling 1): they change what every
# contained context gets, so they are approved at the operator endpoint, and on no agent's surface (CAPR-05).
OPERATOR_REGISTER = (frozenset({"capability", "import"}), frozenset({"capability", "add"}),
                     frozenset({"capability", "remove"}), frozenset({"capability", "host-copies"}))
# Commands only the operator runs, at their own terminal: never relayed, never a typed tool (A1 §1).
OPERATOR_ONLY = CREDENTIAL_EMITTING + OPERATOR_CONFIRMED + OPERATOR_DECIDED + OPERATOR_ENDPOINT + OPERATOR_REGISTER
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
    "lead mode lower",  # a restriction the Lead makes for its own generation (A1 §1.2)
    "map generate", "map select-architecture",  # derived map state under .aew/local/maps/ only (ADR-0015)
    "message unseen",  # a read; with the Lead's credential it records what it showed (F9-A plan D-38, R1)
    "plan accept", "plan adopt",
    "plan propose", "plan reconfirm", "review ingest",
    "stage abandon", "stage continue",  # the typed `resolve` tool's CLI form: the current Lead's own choice (E3c)
    "verify classify", "verify ingest", "work accept",
    "work acknowledge-input", "work assign", "work cancel", "work close", "work create", "work depend",
    "work dispose",  # the typed `resolve` tool's disposition, as its CLI form (M4-E E5b)
    "work dispatch", "work move", "work promote", "work reclassify", "work reconcile", "work redispatch",
    "work staff", "work transition",
))
DISPATCHES = (frozenset({"work", "assign"}), frozenset({"work", "dispatch"}), frozenset({"work", "redispatch"}),
              frozenset({"invoke", "create"}))
POLL_S = 1.0

# The reads a contained Lead relays to its broker, which runs them on the host (STG-05 CS-4 addendum 4, ruling 1). What
# they read is under `.aew/local`, which the Lead's sandbox masks whole: the runs' records, the notifier's and the
# steering loop's state, the map store. Each maps to the options it may carry; any other option, `-C` outside the
# Lead's project and `--print-credential` are refused. Map's `--root` names a stored map by its sha256, never a
# directory. A closed list beside LEAD_REACHABLE: a test walks the parser so that every command is classified.
RELAYED_READS: dict[frozenset[str], frozenset[str]] = {frozenset(path.split()): frozenset(dests) for path, dests in (
    ("status", ("work_id", "json")),
    ("resume", ("json",)),
    ("harness status", ("invocation",)),
    ("harness wait", ("run", "any_", "timeout")),
    ("map show", ("commit", "root", "section", "json")),
    ("map diff", ("operands", "json")),
    # F25 R6: a provisional run's usage is read from its run directory under `.aew/local`, which the sandbox masks
    ("usage show", ("target", "all", "since", "until", "json")),
)}
RELAYED_TIMEOUT_S = 300.0  # a relayed read other than `harness wait`, whose own --timeout bounds it
# The longest relayed `harness wait --timeout` the host can wait out: `communicate` waits in poll(2), whose timeout is
# a C int of milliseconds (POSIX), or in threading's waits, which stop at TIMEOUT_MAX (Windows), and the relay adds
# RELAYED_TIMEOUT_S to the command's own bound (the review of #283 at b2dc3035, m1). Rounded down to whole seconds,
# so the bound a refusal states is one a request may pass (quick check of #283 at c307481a, m3).
RELAYED_WAIT_MAX_S = math.floor(min((2**31 - 1) / 1000, threading.TIMEOUT_MAX) - RELAYED_TIMEOUT_S)
# What a relayed read's values may be (condition 3: none names another project, a directory or an output path): a
# stored map is named by its sha256; a commit is any revision that is not an option; anything else is a name.
_NAME = (re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*"), "an id or name, with no path separator, that is not an option")
RELAYED_VALUES: dict[str, tuple[re.Pattern[str], str]] = {
    "root": (re.compile(r"[0-9a-f]{64}"), "a stored map is named by its sha256"),
    "commit": (re.compile(r"[^-\x00][^\x00]*"), "a revision that is not an option"),
}
_LOCAL = "a read of committed state, which the sandbox shows read-only: it runs there, lock-free"
_HERE = "it reports on the environment it runs in: in the sandbox, the sandbox's"
_WRITER = "it writes under `.aew`, which a non-writer is refused: the operator runs it"
# Every command without a Lead credential that is not relayed, with why (the classification RELAYED_READS's test walks;
# OPERATOR_ONLY and NOT_RELAYED hold the rest, and custody_ops.LEAD_KEPT_OUT, their one owner, the commands a Lead
# session keeps out: #286 review F1).
CONTAINED_LOCAL: dict[frozenset[str], str] = {frozenset(path.split()): why for path, why in (
    ("authority list", _LOCAL), ("context show", _LOCAL + " (it renders the pack, as in a worker's sandbox)"),
    ("dispatch explain", _LOCAL), ("gate show", _LOCAL), ("guide", _LOCAL), ("invoke show", _LOCAL),
    ("history links", _LOCAL), ("history list", _LOCAL), ("history log", _LOCAL), ("history show", _LOCAL),
    ("history search", _LOCAL + " (its derived index is rebuilt privately)"),
    ("integrate breaker status", _LOCAL), ("lead show", _LOCAL), ("message list", _LOCAL), ("message thread", _LOCAL),
    ("plan lint", _LOCAL), ("role list", _LOCAL), ("role show", _LOCAL), ("role validate", _LOCAL),
    ("settings show", _LOCAL), ("work list", _LOCAL), ("work ready", _LOCAL), ("work roles", _LOCAL),
    ("work show", _LOCAL), ("work tree", _LOCAL),
    ("capability list", "a read of the operator's capability register, which the sandbox shows read-only"),
    ("doctor", _HERE), ("harness config", _HERE),
    ("dashboard status", "the operator's dashboard, found from its endpoint under `.aew/local`, which the sandbox "
                         "masks: there it reports none running, and the operator sees it at their own terminal"),
    ("context pack", _WRITER), ("history compact", _WRITER), ("history reindex", _WRITER),
    ("init", "the operator's own"), ("lead session", "the operator's own: it starts a Lead session"),
    ("opencode", "the operator's own: it starts a Lead session"),
    ("check run", "a worker run's, through its run's bridge"), ("submit", "a worker run's, through its run's bridge"),
    ("whoami", "a worker run's, through its run's bridge"),
    ("integrate custody", "AEW's own custody worker, started by the engine"),
)}


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
    if any(p <= path for p in OPERATOR_REGISTER):
        return (f"`aew {command_name(ns)}` changes the capability register, which every contained run reads, so it is "
                "the operator's, approved at the operator endpoint in their own terminal; a Lead session cannot run "
                "it: `aew capability list` shows the register, and the operator makes the change")
    if any(p <= path for p in OPERATOR_ENDPOINT):
        return (f"`aew {command_name(ns)}` is the operator's, through the operator endpoint in their own terminal; a "
                "Lead session can neither raise its own steering mode nor reach the endpoint: request a raise with "
                "the `steering` tool (action request_raise), or lower the mode with `aew lead mode lower`")
    if path == frozenset({"init"}):  # `aew init` stays the operator's own; its first configuration is at the console
        from aew.engine.first_configuration import FLAGS

        given = [flag for dest, flag in FLAGS.items() if getattr(ns, dest, None) is not None]
        if given:
            return (f"`aew init` with {', '.join(given)} sets what is pinned at setup, which the operator does at "
                    "their own console (register E119); a Lead session cannot: ask the operator")
    if path == frozenset({"init"}) and getattr(ns, "fetch_tool", None):  # downloading a tool is the operator's choice
        return ("`aew init` with --fetch-tool downloads a tool, which only the operator chooses, at their own "
                "terminal (the operator, 2026-11-05); a Lead session cannot: ask the operator")
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

    def __init__(self, engine: Any, token: str, *, clock: Callable[[], float] = time.time,
                 idle: Callable[[], threading.Event] = threading.Event) -> None:
        """``clock`` and ``idle`` are test seams, the real ones by default, and no production caller passes either (the
        flake audit's seam #3): ``clock`` stamps the liveness record, and ``idle`` makes the events the watchdog and the
        beat thread wait on between iterations, each set to stop its loop. A test passes an event whose ``wait`` returns
        when the test steps it, so each iteration runs when the test says, never after POLL_S of real time. Never an
        option, setting or variable an agent can reach: a slowed or faked watchdog would change what the operator is
        told."""
        self.engine = engine
        self._token = token
        state = engine.store.current()
        self._require_lead(state, token)  # only the current Lead's credential is ever brokered
        self.generation = int(state["lead"]["generation"])  # the generation this session acts for
        self.session_label = state["lead"].get("session_label")
        self.server = bridge.BridgeServer(self.handle, OPERATIONS, COOPERATIVE)
        self.superseded: str | None = None
        self._stop = idle()
        self._wakes: threading.Thread | None = None  # the wake queue's thread (:meth:`start_wakes`)
        self._reads: set[subprocess.Popen[str]] = set()  # the relayed reads in flight (RELAYED_READS)
        self._reads_lock = threading.Lock()
        self._watch = threading.Thread(target=self._watchdog, name="aew-lead-broker-watch", daemon=True)
        # The liveness record the operator endpoint watches (M4-E E7a; amendment 1, M2, R2-m3): its own thread, never
        # reading the store, with the wedge threshold of this broker's own store (R4-m1).
        root = getattr(engine, "aew_root", None)
        self._beat = None if root is None else broker_liveness.Beat(
            root, generation=self.generation, poll_s=POLL_S, wedge_after_s=broker_liveness.wedge_threshold_s(
                getattr(engine.store, "lock_timeout", 60.0), POLL_S), clock=clock, idle=idle)
        # The steering loop (M4-E E7b; plan v3 E7, M8.1): it runs here, beside the Lead's tools, on its own thread and
        # engine, acting for this session's credential and generation.
        self.loop = None if root is None else steering_loop.SteeringLoop(
            _own_engine(engine), generation=self.generation, session_label=self.session_label,
            token=lambda: self._token, poll_s=POLL_S)

    @property
    def env(self) -> dict[str, str]:
        return {ENV_ENDPOINT: self.server.address, ENV_KEY: self.server.key_hex}

    def start(self) -> None:
        self.server.start()
        if self._beat is not None:
            self._beat.start()
        self._watch.start()
        if self.loop is not None:
            self.loop.start()

    def start_wakes(self, poster: Any) -> None:
        """Post the Lead's wakes through ``poster`` (steering design r4 §1), on a thread of its own and its own engine:
        a tick reads the control state and files, and takes no credential. A failed tick is the next tick's: a wake is
        held, never lost, and the Lead's fallback is `harness_wait`."""
        from aew.harness.wake_queue import WakeQueue, clear_serving, mark_serving, serving
        from aew.policy.execution import PUSH_WAKE_ON, push_wake, quiet_wake_s

        own = _own_engine(self.engine)

        def quiet() -> int:
            policy, _ = own.execution_policy()
            return quiet_wake_s(policy)

        queue = WakeQueue(own.aew_root, poster=poster, state=own.store.current, quiet_s=quiet, clock=time.time,
                          new_id=poster.new_id)

        def run() -> None:
            while not self._stop.wait(POLL_S):
                try:
                    if self.superseded or self._authority_lost():  # no more wakes into a session that lost the seat
                        return
                    try:
                        off = push_wake(own.execution_policy()[0]) != PUSH_WAKE_ON
                    except Exception:  # an edit not yet adopted: no pass can run, so nothing says wakes reach the Lead
                        clear_serving(own.aew_root, self.generation)
                        raise
                    if off:  # turned off mid-session: posts stop now
                        clear_serving(own.aew_root, self.generation)
                        continue
                    if serving(own.aew_root) != self.generation:  # turned on again; a later generation's stops this one
                        mark_serving(own.aew_root, self.generation)
                    queue.tick()
                except Exception as exc:  # noqa: BLE001 - a wake must never take the session down
                    queue.failed(f"{type(exc).__name__}: {str(exc)[:200]}")  # the status line, not the TUI's terminal

        mark_serving(own.aew_root, self.generation)
        self._wakes_root = own.aew_root
        self._wakes = threading.Thread(target=run, name="aew-lead-broker-wakes", daemon=True)
        self._wakes.start()

    def close(self) -> None:
        if self.loop is not None:  # no new auto-run action once the session starts closing (review of PR #199, F4)
            self.loop.request_stop()
        self._stop.set()
        if self._wakes is not None:
            from aew.harness.wake_queue import clear_serving

            self._wakes.join(10)
            clear_serving(self._wakes_root, self.generation)
        self.server.close()
        self._end_reads()  # a relayed read in flight (a long `harness wait`) ends with the session, never holds it
        self.server.drain(60)
        if self._watch.is_alive():
            self._watch.join(60)  # a check in progress finishes before the credential goes (M3-D11)
        if self.loop is not None:
            self.loop.close()  # an auto-run stage in flight finishes before the credential goes
        if self._beat is not None:
            self._beat.close()  # closed_at: a clean end, never a crash
        if not self.server.wait_stopped():  # bounded: no stop left running as the process exits (E128)
            sys.stderr.write(f"aew: the Lead broker's bridge did not stop within {bridge.STOP_BOUND_S:g}s; its private "
                             f"directory {self.server.private_dir} may be left behind\n")
        self._token = ""

    def _require_lead(self, state: dict[str, Any], token: str) -> None:
        """The current Lead's credential, or refused; an archived one is stale authority (ADR-0011 R7) when the engine
        keeps an archive."""
        archived = getattr(self.engine, "archived_credential", None)
        require_lead(state, token, **({"archived": archived} if archived else {}))

    def _authority_lost(self) -> str | None:
        """Why the held credential is no longer the current Lead's, or ``None`` while it is. Only lost authority
        counts: a pending handoff (or any other refusal) is the engine's to report per request, and the Lead may still
        cancel the handoff. Judged from the hot state alone (``require_held_lead``), never the archive: every
        watchdog iteration runs this, and its bound (``broker_liveness.wedge_threshold_s``) counts the control lock's
        wait and no other."""
        token = self._token  # taken before the (possibly slow) read: close() may clear it meanwhile (M3-D11)
        try:
            require_held_lead(self.engine.store.current(), token)
        except errors.StaleAuthority as exc:
            return exc.message
        except errors.AEWError:
            return None
        return None

    def _watchdog(self) -> None:
        while not self._stop.wait(POLL_S):
            faults.pause("harness.lead_broker.watchdog")  # tests: a wedged watchdog (amendment 1, R3-n2)
            problem = self._authority_lost()
            if problem and not self._stop.is_set():
                self.superseded = problem
                self.server.close()
                if self._beat is not None:
                    self._beat.close()  # superseded: a clean end of this broker, never a crash
                return
            if self._beat is not None:
                self._beat.tick()

    # ------------------------------------------------------------------ the one operation

    def handle(self, op: str, args: dict[str, Any]) -> Any:
        if op == "lead.tool":  # cooperative: it takes the serialization itself
            return self._tool(args)
        if op == "lead.read":  # cooperative: a read in a process of its own, needing no Lead authority
            return run_read(self.engine, list(args["argv"]), args["cwd"], track=self._track)
        problem = self._authority_lost()
        if problem:
            self.superseded = problem
            self.server.close()
            raise errors.StaleAuthority(f"this Lead session no longer holds Lead authority: {problem}")
        if op == "lead.whoami":
            lead = self.engine.store.current()["lead"]
            return {"generation": lead["generation"], "session_label": lead.get("session_label")}
        return self._run_cli(list(args["argv"]), args["cwd"], args["stdin"])

    def _run_cli(self, argv: list[str], cwd: str, stdin: str) -> dict[str, Any]:
        return run_cli(self.engine, self._token, argv, cwd, stdin, channel="lead_broker")

    def _track(self, proc: subprocess.Popen[str], running: bool) -> None:
        with self._reads_lock:
            if not running:
                self._reads.discard(proc)
            elif self._stop.is_set():  # the session is closing: no new read starts
                proc.kill()
            else:
                self._reads.add(proc)

    def _end_reads(self) -> None:
        with self._reads_lock:
            for proc in self._reads:
                proc.kill()

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
        """One typed surface call (:meth:`_serve_tool`), and its line in the per-call typed-tool log (M4-E E5a, n7):
        every call, an input error or a refusal included. The log is telemetry and never fails the call
        (``tool_calls.record``). Its revision before is read inside the serialized section the call runs in, so another
        caller's commit while this one waited for the section is not counted as this call's (PR #177 review, 5)."""
        started = time.monotonic()
        meta: dict[str, Any] = {}
        answer: dict[str, Any] | None = None
        refused: dict[str, Any] | None = None
        try:
            answer = self._serve_tool(args, meta)
            return answer
        except errors.AEWError as exc:
            refused = {"code": exc.code}
            raise
        finally:
            after = ((answer or {}).get("stage_result") or {}).get("revision")
            if self.loop is not None and after is not None and after != meta.get("revision_before"):
                self.loop.wake()  # the commit of a Lead tool call wakes the steering loop (plan v3 E7, M8.1)
            tool_calls.record(
                self.engine.aew_root, tool=args.get("name"), arguments=args.get("arguments"),
                ingress=args.get("ingress"), profile=args.get("profile"), result=(answer or {}).get("stage_result"),
                input_error=(answer or {}).get("adapter_input_error"),
                error=refused or (None if answer is not None else {"code": "DEFECT"}),
                revision_before=meta.get("revision_before"), duration_ms=int((time.monotonic() - started) * 1000))

    def _mark(self, meta: dict[str, Any]) -> None:
        """Record the revision a call starts from, for the log. The caller holds the serialization."""
        try:
            meta["revision_before"] = int(self.engine.store.current()["revision"])
        except Exception:  # noqa: BLE001  telemetry: the call reports its own refusal, the log what it could read
            meta["revision_before"] = None

    def _serve_tool(self, args: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
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
            with self.server.serialized():
                self._mark(meta)
            return {"adapter_input_error": AdapterInputError(
                "INVALID_ARGUMENTS", f"{name}: the arguments are not JSON").to_dict()}
        except AdapterInputError as exc:
            with self.server.serialized():
                self._mark(meta)
            return {"adapter_input_error": exc.to_dict()}
        channel = INGRESS_CHANNEL[ingress]

        def cli(argv: list[str], stdin: str) -> dict[str, Any]:
            return run_cli(self.engine, self._token, argv, str(self.engine.repo_root), stdin, channel=channel)

        with dispatch.channel(channel):
            if name == "harness_wait":
                with self.server.serialized():
                    self._mark(meta)
                    problem = self._authority_lost()
                ctx = SurfaceContext(lead_session=self._session(problem), generation=self.generation,
                                     profile=profile, ingress=ingress)
                result = surface_run.run_tool(self.engine, ctx, name, arguments, token=self._token,
                                              serial=self.server.serialized, cancelled=self._cancelled)
            else:
                with self.server.serialized():
                    self._mark(meta)
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


def _own_engine(engine: Any) -> Any:
    """An engine of the loop's own for the same project, so its calls share no object with the Lead's (an engine is
    process-safe through the store's lock, as two processes are)."""
    from aew.engine.api import Engine

    return Engine(Path(engine.repo_root), Path(engine.aew_root)) if isinstance(engine, Engine) else engine


def run_cli(engine: Any, token: str, argv: list[str], cwd: str, stdin: str, *, channel: str) -> dict[str, Any]:
    """Run one Lead-authenticated ``aew`` command with ``token``, with every refusal a Lead session has: the relay of
    a shell command (``lead.cli``) and the typed surface's ``cli`` escape both come here. The caller serializes:
    the process-wide cwd and stdin swap below needs it."""
    from aew.cli.main import build_parser, coordination_reads_for, recall_search_for
    from aew.engine.api import Engine

    # Built as the `aew` client builds it, with the same switch read for this broker's project (register F21, Arm B).
    project = getattr(engine, "aew_root", None) or Path(cwd)
    parser = build_parser(recall_search=recall_search_for(argv, aew_root=project),
                          coordination_reads=coordination_reads_for(argv, aew_root=project))
    stdin_stream = io.StringIO(stdin)  # one input, read once: by --fields - or by the command, as in the direct CLI
    argv = _expand_fields(argv, parser, stdin_stream)
    noise = io.StringIO()
    try:
        with contextlib.redirect_stderr(noise), contextlib.redirect_stdout(noise):
            ns = parser.parse_args(argv)
    except SystemExit:
        raise errors.UsageError(f"invalid command: {noise.getvalue().strip()[-400:]}") from None
    # The operator-only refusal first: it says why and what to do, which "run this one directly" does not (CAP-1
    # review F8: the capability register's changes take no token)
    refusal = refuses_locally(ns)
    if refusal:
        raise errors.PermissionDenied(refusal)
    from aew.engine.custody_ops import LEAD_SESSION, kept_out_refusal

    # On the broker's own channels (a Lead session), a command kept out of one says so in its own text, not "run this
    # one directly" (QC3; #286 review F1); the operator's out-of-session `cli` escape keeps that text, which is true
    # there (#281 review, F2). For `capability check`, which takes no token, both are refusals, so the channel chooses
    # only its wording: a kept-out command that takes a token passes this line on the `cli` escape (#281's quick
    # check, R2).
    kept_out = kept_out_refusal(command_path(ns))
    if channel in INGRESS_CHANNEL.values() and kept_out:
        raise errors.PermissionDenied(kept_out, reason=LEAD_SESSION)
    if not hasattr(ns, "token") or getattr(ns, "handler", None) is None:
        raise errors.PermissionDenied("the Lead bridge runs only Lead-authenticated commands; run this one "
                                      "directly", command=sorted(command_path(ns)))
    path = command_path(ns)
    if path in NOT_RELAYED:
        raise errors.PermissionDenied(f"`aew {command_name(ns)}` is a transport of the typed Lead surface; it "
                                      "is never relayed and never nested in its own cli escape")
    if getattr(ns, "print_credential", False):
        raise errors.PermissionDenied("--print-credential is refused in a Lead session: a credential never goes "
                                      "into the Lead's transcript")
    if ns.token is not None:  # the client refuses it first; the typed `cli` tool's argv reaches only this check
        raise lead_credential.token_value_refusal(lead_session=True)
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
        with dispatch.channel(channel), stdin_only():  # its dispatches record which transport carried them (M4-A)
            result = ns.handler(ns)
    finally:
        sys.stdin = stdin_before
        os.chdir(previous)
    return {"result": result, "json": bool(getattr(ns, "json", False))}


def run_read(engine: Any, argv: list[str], cwd: str,
             track: Callable[[subprocess.Popen[str], bool], None] | None = None) -> dict[str, Any]:
    """Run one read relayed for the contained Lead (``RELAYED_READS``; STG-05 CS-4 addendum 4, ruling 1) on the host,
    and return what it printed, as it printed it, with its exit status. The request is parsed against the command's
    own parser, and runs as an argument list, never a shell string, on the Lead's project only, in a process of its
    own: a non-writer, reading lock-free as in the sandbox, with no credential and no broker in its environment, so a
    long read holds nothing of the session's. ``track`` is told when that process starts and ends, so the session
    ends it when it closes.

    That process writes nothing. A ``harness wait`` it ran told the Lead what it printed, so the broker, a store
    writer, records that (:func:`record_delivery`), as the Lead's typed wait records it: the triggers it returned are
    returned once, and an end it returned is no wake."""
    from aew import process_kind
    from aew.cli.main import build_parser, coordination_reads_for, recall_search_for
    from aew.engine.api import Engine
    from aew.engine.harness_ops import scrubbed_env
    from aew.harness import procs

    project = getattr(engine, "aew_root", None) or Path(cwd)  # as run_cli builds it
    parser = build_parser(recall_search=recall_search_for(argv, aew_root=project),
                          coordination_reads=coordination_reads_for(argv, aew_root=project))
    noise = io.StringIO()
    try:
        with contextlib.redirect_stderr(noise), contextlib.redirect_stdout(noise):
            ns = parser.parse_args(argv)
    except SystemExit:
        raise errors.UsageError(f"invalid command: {noise.getvalue().strip()[-400:]}") from None
    path, name = command_path(ns), command_name(ns)
    if path not in RELAYED_READS:
        raise errors.PermissionDenied(f"`aew {name}` is not relayed to a contained Lead: the operator runs it in their "
                                      "own shell", command=name, reason="not_relayed")
    parsers = [parser]  # every parser on the command's path, `aew`'s own options included (`--print-credential`)
    for word in name.split():
        parsers.append(next(a for a in parsers[-1]._actions if isinstance(a, argparse._SubParsersAction)).choices[word])
    allowed = RELAYED_READS[path] | {"help", "version", "cwd"}  # `-C` is checked below: the Lead's project only
    extra = [a.option_strings[0] if a.option_strings else a.dest for p in parsers for a in p._actions
             if not isinstance(a, argparse._SubParsersAction) and a.dest not in allowed
             and getattr(ns, a.dest, a.default) != a.default]
    if extra:
        raise errors.PermissionDenied(f"`aew {name}` is relayed to a contained Lead without {', '.join(extra)}",
                                      command=name, refused=extra, reason="relayed_option")
    for dest in sorted(RELAYED_READS[path]):
        value = getattr(ns, dest, None)
        values: list[Any] = value if isinstance(value, list) else [] if value is None else [value]
        for kind, text in (values if dest == "operands" else [(dest, v) for v in values]):  # map diff's are pairs
            if isinstance(text, str) and not _relayed_value_ok(kind, text):
                why = RELAYED_VALUES.get(kind, _NAME)[1]
                raise errors.PermissionDenied(f"`aew {name}`, relayed to a contained Lead, refuses {text!r}: {why}",
                                              command=name, reason="relayed_value")
    wait = path == frozenset({"harness", "wait"})
    if wait and not (math.isfinite(ns.timeout) and ns.timeout <= RELAYED_WAIT_MAX_S):
        raise errors.PermissionDenied(f"`aew {name}`, relayed to a contained Lead, refuses --timeout {ns.timeout}: "
                                      f"pass a finite number of seconds, at most {RELAYED_WAIT_MAX_S}",
                                      command=name, reason="relayed_value")
    target = Path(cwd).resolve()
    for place in (target, *([(target / ns.cwd).resolve()] if ns.cwd else [])):
        if Engine.discover(place).aew_root != project:
            raise errors.PermissionDenied("a read relayed for this Lead session runs on its own project only",
                                          project=str(project), reason="relayed_project")
    env = procs.engine_imports(scrubbed_env())  # the broker's own `aew`, and no credential
    for variable in ENV_NAMES:
        env.pop(variable, None)
    env[process_kind.LEAD_CONTAINED_ENV] = "1"  # a non-writer (process_kind): lock-free reads, it writes nothing
    timeout = (float(ns.timeout) if wait else 0.0) + RELAYED_TIMEOUT_S
    detached: dict[str, Any] = ({"creationflags": procs.CREATE_NO_WINDOW} if procs.IS_WINDOWS
                                else {"start_new_session": True})
    with subprocess.Popen([sys.executable, "-m", "aew", *argv], cwd=str(target), env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                          **detached) as proc:  # leaving it closes the pipes and reaps the process
        if track is not None:
            track(proc, True)
        try:
            out, err = proc.communicate(timeout=timeout)
        except BaseException as exc:
            proc.kill()  # whatever ended the wait, the read's process ends with it: never left running untracked
            if isinstance(exc, subprocess.TimeoutExpired):
                raise errors.UsageError(f"`aew {name}`, relayed for this Lead session, did not finish in "
                                        f"{timeout:.0f} s", command=name) from None
            raise
        finally:
            if track is not None:
                track(proc, False)
    if wait:
        record_delivery(project, list(ns.run), out)
    return {"stdout": out, "stderr": err, "exit": proc.returncode}


def record_delivery(project: Path, runs: list[str], stdout: str) -> None:
    """The broker's delivery records for a relayed ``harness wait`` (STG-05 CS-4 addendum 15): what the read printed
    told the Lead, so the broker records it (``harness_ops.record_told``), never the read's process. Only from the
    parsed result: the one value in it the Lead chose is the run, and only a run the wait named, which the broker
    checked, is recorded. Output that isn't a result records nothing."""
    from aew.engine.harness_ops import record_told

    try:
        told = json.loads(stdout)
    except ValueError:
        return
    if isinstance(told, dict) and isinstance(told.get("run"), str) and told["run"] in runs:
        record_told(project, told, lead=True)


def _relayed_value_ok(kind: str, text: str) -> bool:
    return RELAYED_VALUES.get(kind, _NAME)[0].fullmatch(text) is not None


def relays(args: argparse.Namespace) -> bool:
    """Inside the contained Lead (``AEW_LEAD_CONTAINED``, with its broker's coordinates), a read its broker runs on the
    host (``RELAYED_READS``)."""
    from aew import process_kind

    return (bool(os.environ.get(process_kind.LEAD_CONTAINED_ENV)) and bool(os.environ.get(ENV_ENDPOINT))
            and command_path(args) in RELAYED_READS)


def relay_read(argv: list[str]) -> dict[str, Any]:
    """Client side: send one relayed read to this Lead session's broker, from the shell's working directory."""
    return bridge.call("lead.read", {"argv": list(argv), "cwd": str(Path.cwd().resolve())}, env_names=ENV_NAMES)


def _expand_fields(argv: list[str], parser: argparse.ArgumentParser, stdin: io.StringIO) -> list[str]:
    """``--fields -`` expanded as the ``aew`` client does, with this call's stdin, before anything is parsed or checked.
    A shell command relayed through ``lead.cli`` arrives already expanded (its client did it), so for it this changes
    nothing; the typed ``cli`` escape submits its argv as given (PR #93 review). A relayed command takes bytes, so
    ``--fields FILE`` is refused here. Expanded values are checked like any other argument afterwards."""
    from aew.cli import fields

    if not any(a == fields.OPTION or a.startswith(fields.OPTION + "=") for a in argv):
        return argv
    stdin_before = sys.stdin
    try:  # requests are serialized, so the process-wide swap is safe here
        sys.stdin = stdin
        with stdin_only():
            return fields.expand(argv, parser)
    finally:
        sys.stdin = stdin_before


def _as_bytes(argv: list[str], args: argparse.Namespace, cwd: Path) -> tuple[list[str], str]:
    """The arguments to send, and the text that goes with them. A file argument is read here, in the client, relative
    to the command's directory, and sent as ``-``: the last value of an option is the one it takes, whatever form the
    command line spelled it in. The one stdin carries one input, so a command given two is refused."""
    from aew.cli import fields

    given = {option: value for option, dest in getattr(args, fields.GIVEN, {}).items()
             if (value := getattr(args, dest))}
    paths = {option: value for option, value in given.items() if value != "-"}
    piped = "-" in argv or "-" in given.values()
    if len(paths) + piped > 1:
        raise errors.UsageError(f"only one file argument or - can go with a relayed command; this one gives "
                                f"{', '.join(sorted(paths))}{' and -' if piped else ''}")
    if not paths:
        return list(argv), read_text_input("-") if piped else ""  # decoded here; parsed by the broker
    (option, path), = paths.items()
    at = argv.index("--") if "--" in argv else len(argv)
    return [*argv[:at], f"{option}=-", *argv[at:]], read_text_input(str(cwd / path))


def forward(argv: list[str], args: argparse.Namespace) -> dict[str, Any]:
    """Client side: send a Lead-authenticated command to this Lead session's broker, with its file arguments as text."""
    cwd = Path(args.cwd or os.getcwd()).resolve()
    sent, stdin = _as_bytes(argv, args, cwd)
    request = {"argv": sent, "cwd": str(cwd), "stdin": stdin}
    size = len(json.dumps({"op": "lead.cli", "args": request}).encode("utf-8"))  # as bridge.call sends it, escapes too
    if size > bridge.MAX_REQUEST:
        raise errors.UsageError(f"this command and its text make a {size}-byte request, and a Lead session's broker "
                                f"takes at most {bridge.MAX_REQUEST}: nothing was sent, so split the text or shorten "
                                "it",
                                size=size, limit=bridge.MAX_REQUEST, reason="relayed_too_large")
    return bridge.call("lead.cli", request, env_names=ENV_NAMES)


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


@dataclass
class Harness:
    """What a contained Lead session runs (STG-05 CS-4): ``argv`` with ``env``, on the terminal relay when ``relay``
    (``procs.run_session_tree``); ``label`` is the session's containment label, and ``close`` ends what the session
    holds outside its sandbox (its network)."""

    argv: list[str]
    env: dict[str, str]
    relay: bool
    label: dict[str, Any]
    close: Callable[[], None]
    entry: Any = None  # its entry in the register of weaker contexts, when its label is weaker (G3 addendum 7)
    poster: Any = None  # the way into its session for a push wake (``wake_queue.Poster``), where it has one


# `aew lead session` under `required` (G3 addendum 7, ruling 1): what it closes, and the ways on.
UNCONTAINED_LEAD = ("`aew lead session` runs its harness as it is, on your own terminal and network, from where it "
                    "could reach the display and G3, so under containment.mode: required (the default on Linux) it is "
                    "refused. `aew opencode` is the contained Lead. Setting containment.mode: allow_weaker in the "
                    "execution policy runs this harness labelled not contained; G3 is then held for this project "
                    "while its policy says so, and on this host until 15 minutes after the session ends")


def session_ownership() -> str:
    """How :func:`procs.run_session_tree` holds a session's processes on this platform, in the register of weaker
    contexts' terms: the session reaper is a subreaper on Linux, Windows' a job object, and elsewhere nothing."""
    if sys.platform.startswith("linux"):
        return "subreaper"
    return "job_object" if sys.platform == "win32" else "unowned"


def record_label(run_dir: Path, label: dict[str, Any]) -> None:
    """The session's label, beside its run directory's state, for what reads it (G3, #269; ``harness status``): the
    one writer of a Lead session's ``label.json``, both Lead routes'. It names the session's own process by pid and
    start id, so a reader judges the session live with ``same_process`` (G3 addendum 7, ruling 2)."""
    from aew.harness.procs import start_id

    label = {**label, "session_pid": os.getpid(), "session_start_id": start_id(os.getpid())}
    (run_dir / "label.json").write_text(json.dumps(label, indent=2, sort_keys=True, default=str) + "\n",
                                        encoding="utf-8")


def lead_run_dir(engine: Any) -> Path:
    """A Lead session's run directory: ``lead-<UTC>-<hex>``, beside the runs' (both Lead routes')."""
    import secrets

    from aew.harness import runlog

    run_dir = runlog.run_dir(engine.aew_root, f"lead-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-"
                                              f"{secrets.token_hex(3)}")
    run_dir.mkdir(parents=True)
    return run_dir


class WeakerLead:
    """The Lead's harness run as it is, labelled not contained (G3 addendum 7, ruling 1): ``aew lead session`` where
    its policy allows it or off Linux, and ``aew opencode`` off Linux. It writes the session's ``label.json``, prints
    the "runs NOT contained" line, and enters the session in the register of weaker contexts. Under ``required`` it
    refuses (:meth:`precheck`), before any credential is read or any seat moves."""

    def __init__(self, engine: Any, argv: list[str], *, kind: str, who: str) -> None:
        self.engine, self.argv, self.kind, self.who = engine, list(argv), kind, who

    def precheck(self) -> None:
        from aew.harness import containment

        policy, _ = self.engine.execution_policy()
        if containment.mode(policy) == containment.REQUIRED:
            raise errors.ContainmentUnavailable(UNCONTAINED_LEAD if self.kind == "lead_session" else
                                                containment.unsupported_message(), reason="lead_uncontained",
                                                instead="aew opencode")

    def __call__(self, bridge_dir: str | None, child_env: dict[str, str]) -> Harness:
        from aew.harness import containment, weaker_register

        self.precheck()
        run_dir = lead_run_dir(self.engine)
        label = containment.label(contained=False, reason=containment.uncontained_reason())
        label["session"] = run_dir.name
        record_label(run_dir, label)
        sys.stderr.write(f"{self.who}: the Lead runs NOT contained ({label['filesystem']}): "
                         f"{label['weaker_because']}\n")
        entry = weaker_register.enter(kind=self.kind, label=label, ownership=session_ownership(),
                                      project=self.engine.repo_root, aew_root=self.engine.aew_root,
                                      directory=run_dir, marker=run_dir / "label.json")
        return Harness(argv=self.argv, env=entry.mark(child_env), relay=False, label=label, close=lambda: None,
                       entry=entry)


def require_credential(acquire: bool) -> None:
    """A Lead session needs the Lead credential, from the operator (``lead_credential.required``: the variable, removed
    from the session's environment, or the hidden prompt) or a vacant seat (``--acquire``): refused before anything
    starts. ``aew opencode`` asks this before its contained Lead's own checks (U29)."""
    if not acquire:
        lead_credential.required(instead="take a vacant seat with --acquire (the credential then exists only inside "
                                         "this session)")


def run_session(engine: Any, command: list[str], *, acquire: bool, session_label: str | None,
                keep_seat: bool, contained: Callable[[str | None, dict[str, str]], Harness],
                env: dict[str, str] | None = None,
                with_token: Callable[[str], None] | None = None) -> dict[str, Any]:
    """``aew lead session``: broker the Lead credential for one Lead harness session.

    ``env`` is the harness's environment (default: the caller's, minus every credential variable). A harness
    adapter passes a curated one (``aew opencode``); the broker's coordinates are added either way.

    ``contained`` says how the harness runs, and every caller passes it (G3 addendum 7, ruling 1: no route stays
    uncontained by omission). It is called once the broker serves, with the broker's private directory (which the
    sandbox binds in) and that environment, and returns what to run instead of ``command``: in its sandbox (the
    contained Lead, STG-05 CS-4), or, where the policy allows a weaker run, as it is, labelled so (:class:`WeakerLead`).
    When it refuses (containment required and not established), nothing runs, and a seat this session acquired is
    released again. Its ``precheck``, where it has one, runs first: a refusal there comes before any credential is read.

    ``with_token`` is called once with the Lead credential, before the broker starts: what `aew opencode`'s switch offer
    needs, since on ``acquire`` the credential doesn't exist any earlier. It must not raise. `aew lead session` passes
    none, so it never applies an offer.
    """
    from aew.engine.harness_ops import scrubbed_env
    from aew.harness.procs import harden_current_process, run_session_tree

    if not command:
        raise errors.UsageError("name the Lead's harness command after `--`; the Lead's own OpenCode is `aew opencode`")
    if contained is None:  # the backstop: the handlers' own refusals come first (DV-5)
        raise errors.ContainmentUnavailable(UNCONTAINED_LEAD, reason="lead_uncontained", instead="aew opencode")
    precheck = getattr(contained, "precheck", None)
    if precheck is not None:
        precheck()
    harden_current_process()  # this process holds the Lead credential (Linux: not inspectable by its child)
    require_credential(acquire)
    # in memory only: never inherited by git, hooks or any child
    held = os.environ.pop(lead_credential.ENV, "") or lead_credential.take_prompted()
    if acquire:
        token = engine.lead_acquire(expect_rev=engine.store.current()["revision"], session_label=session_label)["token"]
    else:
        token = held
    if with_token is not None:
        with_token(token)
    broker = LeadBroker(engine, token)
    # Every launch this session's broker relays or its steering loop makes runs in this process and reads its
    # environment: a refusal for a missing provider variable says so (review of PR #214, F2).
    with agentenv.session_host("this Lead session (`aew opencode` or `aew lead session`)"):
        broker.start()
        child_env = {**(scrubbed_env() if env is None else scrubbed_env(env)), **broker.env}
        try:
            harness = contained(broker.server.private_dir, child_env)
        except BaseException:
            broker.close()
            if acquire and not broker.superseded:  # nothing ran: the seat this session took is free again
                with contextlib.suppress(errors.AEWError):
                    engine.lead_release(token=token, expect_rev=engine.store.current()["revision"])
            raise
        survivors: list[tuple[int, str | None]] = []
        ownership = None
        if harness.poster is not None:
            broker.start_wakes(harness.poster)
        try:
            if harness.entry is not None:
                harness.entry.started()
            code, ownership = run_session_tree(harness.argv, env=harness.env, cwd=str(engine.repo_root),
                                               relay=harness.relay, survivors=survivors)
        finally:
            if harness.entry is not None:  # an outcome the reaper never gave is an unknown one: unowned
                harness.entry.end(survivors if ownership in ("clean", "survivors") else None,
                                  ownership=None if ownership in ("clean", "survivors") else "unowned")
            harness.close()
            broker.close()
    out: dict[str, Any] = {"ok": True, "exit": code, "superseded": broker.superseded, "processes": ownership,
                           "containment": harness.label}
    state = engine.store.current()
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
