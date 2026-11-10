"""The run supervisor: one process per harness run, holding the invocation credential (ADR-0009).

Started detached by ``aew harness launch`` / ``--launch``. It:

1. reads the credential from its stdin pipe (never argv, environment or disk) and acknowledges custody,
   after checking against control state that the credential belongs to exactly this run;
2. serves the run's custody bridge, executing ``whoami`` / ``check.run`` / ``submit`` through the engine
   with the held credential, after re-checking that this run still holds the invocation's authority;
3. starts the harness through the adapter, inside a process tree it owns, with the curated agent
   environment;
4. watches: the harness exiting, the run's authority ending (invocation ended, credential rotated or
   revoked, Lead generation changed), Lead stop requests and the profile deadline. On any of these it
   closes the bridge, kills the harness tree, records the outcome locally and exits.

It never commits AEW state: a run ending, with or without evidence, moves nothing (WC §8.2). If the
supervisor itself dies, the OS kills the harness tree (job object / sentinel) and the run is ``lost``.

It appends to its run's own event-spool file (``aew.harness.event_spool``; M4-E plan v3 §2.8, amendment 1 E7a), before
the record that makes the run terminal, so the operator endpoint notifies: ``hard_deadline`` at its deadline stop, and
``launch_failed`` at each of its three launch-failure records (custody refused, the start failed, and ``main``'s two
records made before any supervisor exists; R2-m5). A launch whose custody is never acknowledged has no supervisor and
no event: its launcher gets ``HarnessLaunchFailed`` and the run reads ``unconfirmed``.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from aew import errors, skills
from aew.engine import faults
from aew.engine.authority import require_invocation, token_id_of
from aew.harness import agentenv, bridge, containment, event_spool, procs, registry, runlog, usage, weaker_register
from aew.harness import contract as K
from aew.harness.base import HarnessAdapter, refusal_of, relay_family_of
from aew.harness.delivery import NEXT_STEP, WHEN_DELIVERY
from aew.knowledge import evidence as E
from aew.util import sha256_text, utc_now

TICK_S = 0.25
STATE_POLL_S = 2.0
HANDOFF_LIMIT = 64 * 1024
TERMINATE_S = 20.0
ENDING_EXTRA_S = 60.0  # beyond the adapter's stop: collection and the evidence and credential scans
START_ENV = "AEW_RUN_START_S"
STARTING_MARGIN_S = 60.0  # beyond the self-test and the adapter's launch: the contract, the bridge, the layout
# The error type of a provider refusal on content, as the adapter's detail spells it ("failed (provider.content-filter,
# 200: ...)"); matched at the type, never in the provider's message text (PR #310 review, F3).
CONTENT_FILTER = re.compile(r"\(provider\.content[-_.]filter\b", re.IGNORECASE)


def starting_limit_s(harness: str | None) -> float:
    """A start's deadline, from custody to running (ADR-0009 amendment 2026-10-09). ``AEW_RUN_START_S`` when the
    operator set it; otherwise the sandbox self-test's and the adapter's own launch bounds, and the two short waits
    for the capability register's lock after the self-test (its checks' results, and the mark of the operator's flag:
    ``store.RECORD_WAIT_S`` each), in series, plus a margin, so the deadline caps the whole start without ever cutting
    off a step still inside its own timeout. A start still unfinished then is abandoned: its heartbeat stops, so the
    run reads `lost` within the deadline + STALE_AFTER_S of custody, and it never becomes `running`."""
    from aew.capability import store
    from aew.harness.containment import probe

    if os.environ.get(START_ENV):
        return float(os.environ[START_ENV])
    try:
        bound = registry.load(harness).launch_bound_s() if harness else HarnessAdapter.LAUNCH_BOUND_S
    except errors.AEWError:  # the launch loads it again and fails, well inside this deadline
        bound = HarnessAdapter.LAUNCH_BOUND_S
    return 2 * store.RECORD_WAIT_S + probe.BOUND_S + bound + STARTING_MARGIN_S


def contain_launch(policy: dict[str, Any] | None, adapter_cls: type[HarnessAdapter], *, provider: str | None,
                   provider_env: list[str], role: str, scope: str, workspace: str, run_dir: Path, scratch: str,
                   bridge_dir: str | None, bridge: str | None, project: Path, aew_root: Path, kind: str,
                   marker: Path | None = None, skills_dir: str | None = None) -> tuple[Any, dict[str, Any], Any, Any]:
    """A harness launch's containment: the provider key's check, the sandbox, self-tested, its label, the entry in the
    register of weaker contexts when the label is weaker, and the network of its own (the provider relay when the
    harness calls a provider, and the egress proxy when its allowlist names something). Returns ``(layout, label,
    network, weaker entry)``; ``marker`` is the file the register entry names (default: the run's record). The caller
    owns the network (closed with its process tree) and the entry. One owner for a run's supervisor and ``aew
    doctor``'s read of the harness's model list (register E153), so that read meets exactly what a launch meets.
    Raises ``ContainmentUnavailable`` (after removing what it made) where the policy refuses a launch, and
    ``HarnessIncompatible`` for a provider key a launch would not get."""
    from aew.harness.containment import client_cert, netns

    # The engine refused this before anything was committed (``require_launchable``); checked again here, on the names
    # this launch carries, before any sandbox or network exists (the operator's decision of 2026-11-06: AEW does not
    # rely on OpenCode's free models).
    on_route = netns.relay_route(policy, adapter_cls.PROVIDER_RELAY)
    missing = netns.provider_key_missing(provider, provider_env, os.environ, on_relay_route=on_route)
    if missing is not None:
        raise errors.HarnessIncompatible(netns.provider_key_message(str(provider), missing),
                                         reason=netns.PROVIDER_KEY_MISSING, variable=missing)
    no_relay = client_cert.no_relay(provider, policy, on_relay_route=on_route)
    if no_relay is not None:  # only the relay presents a client certificate (register E123)
        raise errors.ContainmentUnavailable(no_relay, provider=provider, reason=client_cert.NO_RELAY)
    layout = None
    try:
        try:  # built once: the self-test checks the same allowlist the run's egress proxy gets (register E143)
            allow = netns.egress_policy(policy, adapter_cls.EGRESS)
        except errors.AEWError as exc:
            raise errors.ContainmentUnavailable(f"containment.network.egress_allow: {exc.message}",
                                                reason="bad_egress_allow") from None
        layout, label = containment.establish(
            role=role, scope=scope, workspace=workspace, run_dir=run_dir, scratch=scratch, bridge_dir=bridge_dir,
            policy=policy, project=str(project), bridge=bridge, egress_policy=allow, skills_dir=skills_dir)
        # A weaker launch (allowed by the policy, or a sandbox on the host's network) enters the register of weaker
        # contexts before its harness starts; on Linux one that cannot be entered is refused (G3 addendum 7).
        weaker = weaker_register.enter_if_weaker(label, kind=kind, ownership=weaker_register.ownership_of(label),
                                                 project=project, aew_root=aew_root, directory=run_dir,
                                                 marker=marker if marker is not None else run_dir / runlog.RECORD)
        network = None
        if layout is not None and layout.private_network:
            network = netns.RunNetwork.start(layout, provider=provider, provider_env=provider_env, policy=policy,
                                             env=os.environ, relay_needed=adapter_cls.PROVIDER_RELAY, allow=allow)
            label["network"].update(network.describe())
    except errors.ContainmentUnavailable:
        if layout is not None and layout.net_dir:
            shutil.rmtree(layout.net_dir, ignore_errors=True)
            containment.retire_private_git(run_dir)
        raise
    return layout, label, network, weaker


def record_refused(record: dict[str, Any], network: Any) -> None:
    """The run's refused egress targets (``netns.RunNetwork.refused``), when there are any, as ``egress_refused``:
    beside the run's ``containment`` label and never in it, since `harness status` and `harness wait` give the Lead
    the label (the designer's ruling of 2026-11-06, point 1)."""
    refused = network.refused()
    if refused and (refused["targets"] or refused["more"]):
        record["egress_refused"] = refused


def log(msg: str) -> None:
    sys.stderr.write(K.redact(f"{utc_now()} {msg}\n"))
    sys.stderr.flush()


def spool(run_dir: Path, event: str, reason: str) -> None:
    """Append ``event`` to this run's event-spool file, for the operator endpoint to notify (M4-E E7a). The project is
    the run directory's (``<aew root>/local/harness/runs/<run>``); a directory anywhere else has none, and nothing is
    appended. Never raises (``event_spool.append``)."""
    depth = len(Path(runlog.RUNS_REL).parts)
    if len(run_dir.parents) <= depth:
        return
    aew_root = run_dir.parents[depth]
    if run_dir.parent != aew_root / runlog.RUNS_REL:
        return
    event_spool.append(aew_root, event_spool.run_writer(run_dir.name), event, subject=run_dir.name,
                       reason=K.redact(reason), ref=f"{runlog.RUNS_REL}/{run_dir.name}")


class Supervisor:
    def __init__(self, run_dir: Path, handoff: dict[str, Any], ack: Any) -> None:
        from aew.engine.api import Engine  # the supervisor is an engine client like any other process

        self.run_dir = run_dir
        self.run = handoff["run"]
        self.inv_id = handoff["invocation"]
        self._credential = handoff["credential"]
        self.token_id = token_id_of(self._credential)
        self.engine = Engine(Path(handoff["repo_root"]), Path(handoff["aew_root"]))
        self.ack = ack
        self.events = runlog.EventLog(run_dir / "events.jsonl")
        self._handled: set[str] = set()  # request files acted on (a replayed one is refused)
        self.record: dict[str, Any] = {"schema": K.RUN_SCHEMA, "run": self.run, "invocation": self.inv_id,
                                       "containment": containment.label(contained=False),
                                       "status": K.STARTING, "supervisor_pid": os.getpid(),
                                       "supervisor_start_id": procs.start_id(os.getpid()), "custody_at": utc_now(),
                                       "timeline": [{"at": utc_now(), "event": "custody"}]}
        self.bridge: bridge.BridgeServer | None = None
        self.adapter: Any = None
        # Fail closed until the run's containment is decided: on POSIX, nothing starts without a layout (M4-B).
        self.tree = procs.ProcessTree(require_layout=not procs.IS_WINDOWS)
        self.layout: containment.Layout | None = None
        self.weaker: weaker_register.Entry | None = None  # its entry, when its label is weaker (G3 addendum 7)
        self._checks = procs.CheckTrees()              # the trees of checks running for the agent now
        self._ending = threading.Event()               # set when the run ends: running checks are killed
        self.agent_env: dict[str, str] = {}
        self._started_mono: float | None = None  # when the harness started: the usage record's wall time (F25 R1)
        self._start_s = 0.0  # the start's deadline in seconds from custody, and as a monotonic time
        self._start_until: float | None = None
        self.stop_reason: tuple[str, str] | None = None  # (status, reason) requested by a bridge refusal
        self._control_seen: Any = None
        self._state_unreadable = False  # the last lock-free state read failed (logged once until one succeeds)
        self._deferred: dict[str, str] = {}  # request files taken while the state was unreadable: name -> text
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ record

    def _event(self, event: str, **extra: Any) -> None:
        self.record["timeline"].append({"at": utc_now(), "event": event, **extra})
        self.events({"event": event, **extra})

    def _save(self) -> None:
        runlog.write_record(self.run_dir, self.record)

    def _send_ack(self, payload: dict[str, Any]) -> None:
        try:
            self.ack.write((json.dumps(payload) + "\n").encode("utf-8"))
            self.ack.flush()
        except (OSError, ValueError):
            pass  # the launching process is gone: the run continues without it

    # ------------------------------------------------------------------ authority

    def authority_problem(self) -> str | None:
        """Why this run no longer holds its authority, or None while it holds it or while the state cannot be read
        (``_authority``)."""
        return self._authority()[1]

    def _authority(self) -> tuple[bool, str | None]:
        """(read, problem): whether the committed state was read, and why this run no longer holds its authority.

        The state is read lock-free (``ControlStore.read_committed``). The watch loop that beats the heartbeat calls
        this: under the control lock, another process's long hold (up to the lock's timeout, 60 s) stalled the beat past
        ``runlog.STALE_AFTER_S``, and a live run read as ``lost`` (two CI sightings on Windows, 2026-11-07).

        A stale read is safe because every condition ``run_authority_problem`` checks only moves forward: an invocation
        leaves ``active`` and never returns, ``runs[-1]`` only advances, ``revoked_at`` is only ever set, and the
        generation only grows. So a committed state read late can only be more permissive than the truth, never less,
        and every engine operation re-checks the credential under the lock before it writes, refusing what a stale read
        let through. A change to ``run_authority_problem`` must keep its conditions monotonic, or this read is unsafe.

        For the same reason a state that cannot be read this time (``_committed_state``) is unknown, not a problem: the
        caller reads again on its next tick, and the engine stays the gate (#366 review, M2)."""
        state = self._committed_state()
        if state is None:
            return False, None
        return True, self.engine.run_authority_problem(state, self.inv_id, self.run, self.token_id)

    def _committed_state(self) -> dict[str, Any] | None:
        """The committed control state read lock-free, or None when it cannot be read this time.

        Unlike the locked read, a lock-free read can meet a writer's replace: on Windows the mid-replace miss reaches it
        as ``ProjectNotFound`` and a sharing violation outlasting its retries as ``PermissionError``. Neither may end a
        live run (#366 review, M2). A failure is logged once until a read succeeds again, in the event log only, so a
        state unreadable for long never grows the run record."""
        try:
            state = self.engine.store.read_committed()
        except (errors.AEWError, OSError) as exc:
            if not self._state_unreadable:
                self._state_unreadable = True
                self.events({"event": "state_unreadable", "error": getattr(exc, "message", None) or repr(exc)})
            return None
        self._state_unreadable = False
        return state

    def _control_changed(self) -> bool:
        path = self.engine.aew_root / "state" / "control.yaml"
        try:
            st = path.stat()
            seen = (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            seen = None
        changed, self._control_seen = seen != self._control_seen, seen
        return changed

    # ------------------------------------------------------------------ bridge

    def handle(self, op: str, args: dict[str, Any]) -> Any:
        if self._start_overdue():  # the run reads (or is about to read) `lost`: nothing it does counts any more
            raise errors.HarnessLaunchFailed(f"run {self.run} did not start within {self._start_s:g}s ({START_ENV}) "
                                             "and is abandoned", run=self.run)
        problem = self.authority_problem()
        if problem:
            self.stop_reason = (K.TERMINATED, f"authority ended: {problem}")
            raise errors.StaleAuthority(f"run {self.run} no longer holds {self.inv_id}'s authority: {problem}",
                                        run=self.run)
        # The window a rotation or revocation can race: the engine re-checks the credential under its lock.
        faults.pause("harness.bridge.before_engine")
        try:
            if op == "whoami":
                return self.engine.invocation_whoami(invocation_token=self._credential)
            if op == "check.run":
                return self.engine.check_run(invocation_token=self._credential, check_id=args["check_id"],
                                             env=dict(self.agent_env), layout=self.layout, trees=self._checks,
                                             ending=self._ending, label=self.record["containment"])
            if op == "submit":
                return self.engine.submit(invocation_token=self._credential, kind=args["kind"], text=args["text"])
        except errors.StaleAuthority as exc:
            self.stop_reason = (K.TERMINATED, f"authority ended: {exc.message}")
            raise
        raise errors.UsageError(f"unknown bridge operation {op}")

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        faults.pause("harness.supervisor.before_custody")  # tests: a supervisor slow to take custody
        state = self.engine.store.current()
        try:
            inv_id, inv, _ = require_invocation(state, self._credential, None,
                                                archived=self.engine.archived_credential)
        except errors.AEWError as exc:
            return self._refuse(f"credential rejected: {exc.message}", exc.code)
        problem = self.engine.run_authority_problem(state, self.inv_id, self.run, self.token_id)
        if inv_id != self.inv_id or problem:
            return self._refuse(problem or f"credential is for {inv_id}, not {self.inv_id}")
        profile = inv["execution_profile"] or {}
        self.record.update(work_unit=inv["work_unit"], role=inv["role"], harness=profile.get("harness"),
                           execution_profile=profile)
        # Beat before the first record: a non-terminal record with no heartbeat reads as `lost`, and writing the record
        # wakes every `harness wait` into exactly that gap (CI, Windows, 2026-10-09; register E3).
        self._starting_beats(profile.get("harness"))
        self._save()  # status: starting — from here the run is visibly held, not merely unconfirmed
        faults.pause("harness.supervisor.after_custody_record")  # tests: a supervisor slow right after its first record
        self._send_ack({"custody": True, "run": self.run, "pid": os.getpid()})
        try:
            contract = self._deliver_skills(self.engine.harness_contract(state, self.inv_id, self.run))
            self.record["contract"] = contract.to_record()
            (self.run_dir / "prompt.md").write_text(K.redact(contract.prompt), encoding="utf-8")
            self.bridge = bridge.BridgeServer(self.handle)
            self.bridge.start()
            self.record["bridge"] = {"endpoint": self.bridge.address}
            Path(contract.scratch).mkdir(parents=True, exist_ok=True)
            adapter_cls = registry.load(profile["harness"])
            self._contain(contract, adapter_cls)
            contract = self._label_skills(contract)
            self.record["contract"] = contract.to_record()
            self._tools(contract)
            self.agent_env = agentenv.build(os.environ, endpoint=self.bridge.address, key_hex=self.bridge.key_hex,
                                            invocation=self.inv_id, run=self.run, work_unit=inv["work_unit"],
                                            scratch=contract.scratch,
                                            contained=self.layout.env if self.layout is not None else None)
            # The run's marker, whatever its label: the register of weaker contexts' scan finds its processes by it
            self.agent_env[weaker_register.MARKER] = str(self.run_dir / runlog.RECORD)
            self.adapter = adapter_cls(self.tree, self.run_dir, self.events)
            if self.weaker is not None:
                self.weaker.started()
            info = self.adapter.launch(contract, dict(self.agent_env))
            self.record["launch"] = info
            relay_family = relay_family_of(info)
            if relay_family is not None:  # the label says what the launch could check of its model (register E143)
                self.record["containment"]["network"]["relay_family"] = relay_family
            faults.pause("harness.supervisor.launched")  # tests: a start that wedges after the custody ack
        except errors.AEWError as exc:
            cause = exc.details.get(K.LAUNCH_CAUSE)
            return self._launch_failed(f"{exc.code}: {exc.message}", exc.code,
                                       cause=str(cause) if cause is not None else None, refusal=refusal_of(exc.details))
        except Exception as exc:
            log(traceback.format_exc())
            return self._launch_failed(f"{type(exc).__name__}: {exc}")
        if self._start_overdue():  # its heartbeat has stopped, and it may already have been read as `lost`
            return self._launch_failed(f"the start took longer than {self._start_s:g}s ({START_ENV}); the run was "
                                       "abandoned")
        self.record["status"] = K.RUNNING
        self.record["started_at"] = utc_now()
        self._started_mono = time.monotonic()
        self.record["harness_pids"] = list(self.tree.pids)
        self.record["harness_start_ids"] = [procs.start_id(pid) for pid in self.tree.pids]
        self._event("started", pids=list(self.tree.pids))
        self._save()
        runlog.beat(self.run_dir)
        launch = self.record.get("launch") or {}
        relay_family = relay_family_of(launch)
        self._send_ack({"started": True, "status": K.RUNNING, "harness": profile.get("harness"),
                        "session": launch.get("session"), **({"relay_family": relay_family} if relay_family else {})})
        faults.hit("harness.supervisor.after_start")
        return True

    def _skills_dir(self) -> Path:
        return self.run_dir / "harness" / "skills"

    def _deliver_skills(self, contract: K.LaunchContract) -> K.LaunchContract:
        """Copy the run's exposed skills into its own folder before its sandbox exists (the 2026-11-03 ruling, §3),
        and return the contract with the plan as delivered: a skill whose copy fails reports ``copy_failed`` and the
        run goes on. Every harness gets the same copy; a harness without a ``skill`` tool just never lists it."""
        planned = contract.extra.get("skills")
        if not isinstance(planned, dict):
            return contract
        try:
            delivered = skills.deliver(planned, self._skills_dir())
        except Exception as exc:  # noqa: BLE001 - a missing skill never fails a run (the 2026-11-03 ruling, §3)
            self._event("skills_not_delivered", error=f"{type(exc).__name__}: {exc}"[:300])
            shutil.rmtree(self._skills_dir(), ignore_errors=True)
            failed = {str(n): skills.COPY_FAILED for n in planned.get("exposed") or []}
            delivered = {**planned, "exposed": [], "unavailable": list(planned.get("requested") or []),
                         "reasons": dict(sorted({**(planned.get("reasons") or {}), **failed}.items())),
                         "delivered": []}
        return dataclasses.replace(contract, extra={**contract.extra, "skills": delivered})

    def _label_skills(self, contract: K.LaunchContract) -> K.LaunchContract:
        """What protects the copy, on the plan: ``read_only_bind`` when the run's sandbox binds it read-only (Linux),
        else ``rules_only``: the harness's ``edit`` deny is all there is, and a shell write was never tried (Windows, or
        a run the policy lets go uncontained). The copy is technique, never authority, so this is a label, not a
        refusal."""
        planned = contract.extra.get("skills")
        if not isinstance(planned, dict) or not planned.get("exposed"):
            return contract
        bound = self.layout is not None and os.path.realpath(self._skills_dir()) in self.layout.skills_binds
        planned = {**planned, "copy": "read_only_bind" if bound else "rules_only"}
        return dataclasses.replace(contract, extra={**contract.extra, "skills": planned})

    def _tools(self, contract: K.LaunchContract) -> None:
        """What the run's system text says of AEW's tools, from its containment label (``_contain``'s): what it goes
        without, from its own record, as a missing tool is logged, not voided (the operator, 2026-11-05); and what it
        has, by the names it calls them (the Lead's ruling on card-capability resolution), none where it is not
        contained."""
        from aew.capability import ops as capability

        contract.extra[K.UNAVAILABLE_TOOLS] = capability.unavailable(self.record["containment"].get("missing_tools"))
        contract.extra[K.AVAILABLE_TOOLS] = capability.placed(self.record["containment"],
                                                             contained=self.layout is not None)

    def _contain(self, contract: K.LaunchContract, adapter_cls: type[HarnessAdapter]) -> None:
        """Build and self-test this run's sandbox before any harness process exists (F2, M4-B), and start its network
        outside it (F28, STG-05 CS-3b): :func:`contain_launch`, which ``aew doctor``'s read of the harness's model list
        shares. Under the default policy a sandbox or a network that cannot be established refuses the launch; the
        label records what the run has."""
        policy, _ = self.engine.execution_policy()
        assert self.bridge is not None
        try:
            contained = contain_launch(
                policy, adapter_cls, provider=(self.record.get("execution_profile") or {}).get("provider"),
                provider_env=[str(n) for n in contract.extra.get("provider_env") or []], role=contract.role,
                scope=contract.scope, workspace=contract.workspace, run_dir=self.run_dir, scratch=contract.scratch,
                bridge_dir=self.bridge.private_dir, bridge=self.bridge.address, project=self.engine.repo_root,
                aew_root=self.engine.aew_root, kind="worker_run",
                skills_dir=str(self._skills_dir()) if (contract.extra.get("skills") or {}).get("exposed") else None)
        except errors.ContainmentUnavailable as exc:  # the self-test's rows, when it ran, stay on the refusal's label
            self.layout = None
            self.record["containment"] = containment.label(contained=False, reason=exc.message,
                                                           self_test=exc.details.get("self_test"))
            self._event("containment_refused", reason=exc.message)
            raise
        self.layout, self.record["containment"], network, self.weaker = contained
        line = containment.tree_masks_line(self.layout) if self.layout is not None else None
        self._event("containment", filesystem=self.record["containment"]["filesystem"],
                    process_ownership=self.record["containment"]["process_ownership"],
                    network=self.record["containment"]["network"]["mode"], **({"tree_masks": line} if line else {}))
        if not procs.IS_WINDOWS:
            self.tree = procs.ProcessTree(layout=self.layout, network=network)

    def _starting_beats(self, harness: str | None) -> None:
        """Beat while the harness starts (a server start plus health checks can take a while); the watchdog loop
        takes over once it runs, so a stalled watchdog shows as a stale heartbeat. Bounded by the start's deadline,
        so a supervisor stuck while starting goes stale too (register E3)."""
        self._start_s = starting_limit_s(harness)
        self._start_until = time.monotonic() + self._start_s
        self._watching = self._background_beats("aew-starting-heartbeat", until=self._start_until)

    def _start_overdue(self) -> bool:
        """The start ran past its deadline: the starting heartbeat has stopped."""
        return (self._start_until is not None and self.record["status"] == K.STARTING
                and time.monotonic() >= self._start_until)

    def _background_beats(self, name: str, *, until: float) -> threading.Event:
        """Beat from a thread until the returned event is set or the monotonic clock reaches ``until``, while the
        supervisor works outside its watch loop."""
        done = threading.Event()

        def beat() -> None:
            while not done.wait(runlog.HEARTBEAT_S) and time.monotonic() < until:
                runlog.beat(self.run_dir)

        if time.monotonic() < until:
            runlog.beat(self.run_dir)
        threading.Thread(target=beat, name=name, daemon=True).start()
        return done

    # A launch failure's record and acknowledgement carry its closed code beside the free-text reason (M4-E E8a; plan v3
    # n8). The acknowledgement's is the one the launcher passes on: the record sits in the model-writable run directory.
    def _refuse(self, reason: str, error_code: str | None = None) -> bool:
        code = K.launch_failure_code(K.CUSTODY, error_code)
        self.record.update(status=K.LAUNCH_FAILED, reason=f"custody refused: {reason}", reason_code=code,
                           ended_at=utc_now())
        self._event("custody_refused", reason=reason, reason_code=code)
        spool(self.run_dir, "launch_failed", self.record["reason"])  # site 1 (R2-m5), before the terminal record
        self._save()
        self._send_ack({"custody": False, "reason": reason, "reason_code": code})
        self._drop_credential()
        return False

    def _launch_failed(self, reason: str, error_code: str | None = None, *, cause: str | None = None,
                       refusal: str | None = None) -> bool:
        """``refusal``: the reason the launch was refused, one of ``base.LAUNCH_REFUSALS`` (an adapter's own, or this
        supervisor's missing-key refusal, E189), beside the closed code (register E143)."""
        code = K.launch_failure_code(K.START, error_code, cause)
        spool(self.run_dir, "launch_failed", reason)  # site 2 (R2-m5), before the terminal record
        if refusal is not None:
            self.record["refusal"] = refusal
        if cause is not None:  # the failure's own cause, which its code (`unknown`) does not tell apart
            self.record[K.LAUNCH_CAUSE] = cause
        self._finish(K.LAUNCH_FAILED, reason, reason_code=code)
        self._send_ack({"started": False, "status": K.LAUNCH_FAILED, "reason": reason, "reason_code": code,
                        **({"refusal": refusal} if refusal is not None else {})})
        return False

    def watch(self) -> None:
        self._watching.set()
        deadline_s = (self.record.get("execution_profile") or {}).get("deadline_s")
        deadline = time.monotonic() + deadline_s if deadline_s else None
        last_beat = last_poll = 0.0
        unread = False  # the last authority read failed: read again at the next tick (#366 review, M2)
        while True:
            faults.pause("harness.watchdog.tick")  # tests: a supervisor that is slow to notice anything
            now = time.monotonic()
            if now - last_beat >= runlog.HEARTBEAT_S:
                runlog.beat(self.run_dir)
                last_beat = now
            if self.stop_reason:
                return self._finish(*self.stop_reason)
            for req in self._authorized_requests():
                kind = req.get("kind")
                self._event("request", kind=kind)
                if kind == "stop":
                    return self._finish(K.TERMINATED, f"stopped: {req.get('reason')}")
                try:
                    if kind == "send":  # only `next-step` is ever a request file (F9-A amendment 2 §3.3; E55)
                        self.adapter.send(str(req.get("text") or ""), WHEN_DELIVERY[NEXT_STEP])
                    elif kind == "interrupt":
                        self.adapter.interrupt()
                except errors.AEWError as exc:
                    self._event("request_failed", kind=kind, error=exc.message)
            if unread or self._control_changed() or now - last_poll >= STATE_POLL_S:
                read, problem = self._authority()
                if problem:
                    return self._finish(K.TERMINATED, f"authority ended: {problem}")
                unread = not read
                if read:
                    last_poll = now
            status = self.adapter.inspect()
            if not status.get("alive"):
                return self._finish_exited(status)
            if deadline is not None and now >= deadline:
                spool(self.run_dir, "hard_deadline", f"deadline of {deadline_s}s exceeded")
                # A low anomaly the next Lead commit records (M4-E E7b; plan v3 §2.4, A1 §3.2): this process commits
                # nothing, so it leaves a worker-side signal, as a refused report does.
                from aew.engine.disposition_ops import HARD_DEADLINE, signal_source

                signal_source(self.engine.aew_root, HARD_DEADLINE, self.inv_id)
                return self._finish(K.TERMINATED, f"deadline of {deadline_s}s exceeded")
            time.sleep(TICK_S)

    def _authorized_requests(self) -> list[dict[str, Any]]:
        """Queued request files that a Lead operation recorded for this run, each acted on once.

        The run directory is model-writable (same user), so a file alone is no request: its name and digest must be
        on this run's entry in control state, which the Lead operation commits before it writes the file. Anything
        else is recorded and discarded (independent review R1)."""
        # Files taken while the state was unreadable are kept as they were taken: a later file of the same name (the
        # run directory is model-writable) never replaces a kept Lead request (#366 review, N3). That is all the
        # `setdefault` merge is for: the sort below decides the order. They are bounded by the queue's distinct names.
        pending = dict(self._deferred)
        for name, text in runlog.take_requests(self.run_dir):
            pending.setdefault(name, text)
        self._deferred = {}
        if not pending:
            return []
        # lock-free, as ``_authority``: the watch loop that beats the heartbeat calls this
        state = self._committed_state()
        if state is None:  # the files are taken already: keep them for the next tick, never refuse them (M2)
            self._deferred = pending
            return []
        inv = state["invocations"].get(self.inv_id) or {}
        entry = next((r for r in inv.get("runs") or [] if r["run"] == self.run), {})
        recorded = {r["file"]: r for r in entry.get("requests") or []}
        out = []
        # In issue order, kept files with new ones: a request file's name starts with its issue time
        # (runlog._next_request_ns), so the sort alone decides the order, whichever tick took a file and however late it
        # was delivered; the merge order above decides nothing (#366 review, N4)
        for name, text in sorted(pending.items()):
            want = recorded.get(name)
            why = ("not recorded by a Lead operation" if want is None else
                   "already handled" if name in self._handled else
                   "content differs from the recorded request" if sha256_text(text) != want["sha256"] else None)
            req: Any = None
            if why is None:
                assert want is not None  # `why` is None only for a recorded request
                try:
                    req = json.loads(text)
                except ValueError:
                    req = None
                if not isinstance(req, dict) or req.get("kind") != want["kind"]:
                    why = "content differs from the recorded request"
            if why is not None:  # the event log only: a flood of files never grows the run record
                self.events({"event": "request_refused", "file": name[:200], "why": why})
                continue
            self._handled.add(name)
            out.append(req)
        return out

    def _finish_exited(self, status: dict[str, Any]) -> None:
        """The harness exited. Its exit status is never success: only a recorded expected output is progress,
        and even that moves no state until the Lead ingests it (WC §8.2)."""
        expected = set((self.record.get("contract") or {}).get("expected_kinds") or [])
        outputs = [e for e, kind in self._evidence(kinds=True) if kind in expected]
        code = status.get("exit_code")
        self.record["exit_code"] = code
        if status.get("detail"):
            self.record["harness_outcome"] = status["detail"]
        reason_code = status.get("reason_code")
        if isinstance(reason_code, str) and reason_code:
            self.record["reason_code"] = reason_code
        if outputs:
            return self._finish(K.ENDED_WITH_EVIDENCE, f"harness exited ({code}) after recording {', '.join(outputs)}")
        if code == 0:
            return self._finish(K.ENDED_WITHOUT_EVIDENCE, "harness exited successfully without recording its expected "
                                f"output ({', '.join(sorted(expected))}); no AEW state changed")
        if reason_code == K.PROVIDER_AUTH_FAILED:  # its own reason, in the existing status (register V1)
            names = ", ".join(((self.record.get("contract") or {}).get("extra") or {}).get("provider_env") or [])
            return self._finish(K.CRASHED, f"{K.PROVIDER_AUTH_FAILED}: the model provider rejected the credential, so "
                                "the harness exited without recording its expected output; check the key in "
                                f"{names or 'the variables'} (the execution policy's provider_env), then relaunch. A "
                                "relaunch reads the key from the process that launches it: from inside a Lead session "
                                "(`aew opencode`, `aew lead session`) that is the session's own, so restart it from a "
                                "terminal with the new key first")
        reason = f"harness exited with {code} without recording its expected output"
        # the provider's text is bounded and cleaned before it reaches a reason that is shown (PR #310 review, F2);
        # the record's `harness_outcome` keeps the raw value
        detail = event_spool.clean(status.get("detail"))
        if detail:
            reason += f"; harness outcome: {detail}"
            if CONTENT_FILTER.search(detail):
                reason += self._content_filter_next_step()
        return self._finish(K.CRASHED, reason)

    def _content_filter_next_step(self) -> str:
        """What the Lead does when the provider refuses on content, as commands that parse as printed (PR #310
        review, F1). A relaunch keeps the invocation's pinned model (ADR-0010) and no governed command changes its
        pack, so a repeat means a new invocation on another model: cancel this one, then dispatch."""
        inv = self.inv_id
        wid = self.record.get("work_unit") or "<work unit>"
        rev = "--expect-rev <revision from aew status>"
        return (f". Relaunch it with `aew harness launch {inv} {rev}`. A relaunch keeps the invocation's pinned "
                "model (ADR-0010), so if the refusal repeats, cancel it:\n\n"
                f"```sh\naew invoke cancel {inv} {rev} --fields - <<'EOF'\n"
                "reason: 'why this invocation must end'\nEOF\n```\n\n"
                "and dispatch a new invocation on another model:\n\n"
                f"```sh\naew invoke create {wid} --launch --model PROVIDER/MODEL {rev}\n```\n\n"
                "For a non-mutating Ticket, redispatch it instead of cancelling and dispatching:\n\n"
                f"```sh\naew work redispatch {wid} --launch --model PROVIDER/MODEL {rev} --fields - <<'EOF'\n"
                "reason: 'why this Ticket is redispatched'\nEOF\n```")

    def _evidence(self, *, kinds: bool = False) -> list[Any]:
        wid = self.record.get("work_unit")
        if not wid:
            return []
        records, _ = E.scan(self.engine.aew_root, wid)
        mine = [e for e in records if e["producer"].get("run") == self.run]
        return [(e["id"], e["kind"]) for e in mine] if kinds else [e["id"] for e in mine]

    def _finish(self, status: str, reason: str, *, reason_code: str | None = None) -> None:
        with self._lock:
            if self.record.get("ended_at"):
                return
            if getattr(self, "_watching", None) is not None:
                self._watching.set()
            # Ending takes time outside the watch loop (the adapter alone may take TERMINATE_S): keep beating, or
            # `harness wait` reports a healthy run `lost` (found by CI). Bounded, so a supervisor stuck here still
            # goes stale. An abandoned start does not beat again: once it may have been read as `lost`, it stays so
            # until its final record.
            until = time.monotonic() + (0.0 if self._start_overdue() else TERMINATE_S + ENDING_EXTRA_S)
            ending = self._background_beats("aew-ending-heartbeat", until=until)
            try:
                faults.pause("harness.supervisor.finishing")  # tests: a run slow to end (a harness slow to stop)
                self._end(status, reason, reason_code)
            finally:
                ending.set()

    def _end(self, status: str, reason: str, reason_code: str | None = None) -> None:
        self._ending.set()
        # A check outlives neither its run nor the private git state it may use: running checks are killed, one whose
        # request is still in flight starts nothing, and the private state is retired only once they have returned.
        self._checks.end()
        if self.bridge is not None:
            self.bridge.close()
        try:
            if self.adapter is not None:
                self._terminate_adapter()
        finally:  # the tree is killed whatever the adapter managed
            self.tree.kill()
            if self.weaker is not None:  # ended only once its processes are proven ended (G3 addendum 7, ruling 2)
                self.weaker.end(self.tree.survivors() + list(self._checks.left))
            containment.retire_private_git(self.run_dir)  # private staging is scratch: nothing real refers to it
        # After the kill, so a slow stop never delays it; before the final record, so the supervisor never exits with
        # the stop still running and its private directory left (E128). Bounded by the stop's own bound.
        if self.bridge is not None and not self.bridge.wait_stopped():
            self._event("bridge_stop_timeout", bound_s=bridge.STOP_BOUND_S)
        try:
            self.record["result"] = self.adapter.collect() if self.adapter is not None else {}
        except Exception as exc:
            self.record["result"] = {"error": f"{type(exc).__name__}: {exc}"}
        self._record_usage()
        self._compare_effective()
        self.record["evidence"] = self._evidence()
        self.record.update(status=status, reason=reason, ended_at=utc_now())
        # The vocabulary follows the status (amendment 1, R2-m2): a launch-failure code is written with `launch_failed`
        # and never survives onto another ending, such as a `crashed` re-end after this one failed (PR #185, F2).
        if status == K.LAUNCH_FAILED:
            self.record["reason_code"] = reason_code or K.UNKNOWN_LAUNCH_FAILURE
        elif self.record.get("reason_code") in K.LAUNCH_FAILURE_CODES:
            del self.record["reason_code"]
        if self.bridge is not None:
            self.record["bridge"].update(requests=self.bridge.requests, refused=self.bridge.refused,
                                         outcomes=self.bridge.outcomes)
        if self.tree.network is not None:  # closed with the tree; its counts stay
            self.record["containment"]["network"]["decisions"] = self.tree.network.decisions()
            record_refused(self.record, self.tree.network)
        self._event("ended", status=status, reason=reason)
        self._drop_credential()
        try:
            self.record["credential_scan"] = runlog.credential_scan(self.run_dir)
        except Exception as exc:  # the final record is saved whatever the scan met; a failed scan is never clean
            self.record["credential_scan"] = {"clean": False, "files": [], "error": f"{type(exc).__name__}: {exc}"}
        self._save()

    def _terminate_adapter(self) -> None:
        """The adapter's own shutdown, bounded: a stuck adapter must not stop the supervisor from ending the run."""
        failure: list[str] = []

        def stop() -> None:
            try:
                self.adapter.terminate()
            except Exception as exc:
                failure.append(f"{type(exc).__name__}: {exc}")

        worker = threading.Thread(target=stop, name="aew-adapter-terminate", daemon=True)
        worker.start()
        worker.join(TERMINATE_S)
        if worker.is_alive():
            self._event("terminate_timeout", after_s=TERMINATE_S)
        elif failure:
            self._event("terminate_failed", error=failure[0])

    def _record_usage(self) -> None:
        """``result.usage_record`` as the adapter normalized it, plus the run's wall time, which only the supervisor
        observes (F25, cost and usage ledger v0.2 R2). The raw ``usage`` stays beside it for diagnosis. A record that
        is not an ``aew/run-usage/v1`` object is dropped: the engine's copy then counts the run's usage as absent."""
        result = self.record.get("result")
        if not isinstance(result, dict) or "usage_record" not in result:
            return
        if not isinstance(result["usage_record"], dict) or result["usage_record"].get("schema") != usage.SCHEMA:
            del result["usage_record"]
            return
        wall = time.monotonic() - self._started_mono if self._started_mono is not None else None
        usage.with_wall_time(result["usage_record"], wall)

    def _compare_effective(self) -> None:
        """Requested (pinned) versus effective execution: a mismatch is flagged, never silently accepted."""
        pin = self.record.get("execution_profile") or {}
        effective = (self.record.get("result") or {}).get("effective")
        if effective is None:
            self.record["model_check"] = {"status": "unreported"}
            return
        if not effective:  # the harness reports its models, and no model step ran in this run
            self.record["model_check"] = {"status": "no_model_step", "requested": {
                "provider": pin.get("provider"), "model": pin.get("model"), "effort": pin.get("effort")}}
            return
        wanted = {"provider": pin.get("provider"), "model": pin.get("model"), "effort": pin.get("effort")}
        # Effort is always compared, unless the adapter says the harness did not report it (`effort_unreported`):
        # `effort: None` means "no effort variant ran", which differs from a requested effort (independent audit I4).
        mismatches = [e for e in effective
                      if e.get("provider") != wanted["provider"] or e.get("model") != wanted["model"]
                      or (not e.get("effort_unreported") and e.get("effort") != wanted["effort"])]
        unverified = [e for e in effective
                      if e not in mismatches and e.get("effort_unreported") and wanted["effort"] is not None]
        status = "mismatch" if mismatches else "effort_unreported" if unverified else "match"
        self.record["model_check"] = {"status": status, "requested": wanted,
                                      "effective": effective, "mismatches": mismatches}
        if unverified:
            self.record["model_check"]["effort_unreported"] = unverified
        if mismatches:
            self._event("model_mismatch", requested=wanted, effective=mismatches)

    def _drop_credential(self) -> None:
        self._credential = ""


def main(argv: list[str] | None = None) -> int:
    from aew import process_kind

    process_kind.declare("aew.harness.supervisor")
    parser = argparse.ArgumentParser(prog="aew-harness-supervisor")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    for key in list(os.environ):  # defense in depth: the launcher already removed these
        if key.upper() in {"AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_KEY", "AEW_AGENT_ENDPOINT"}:
            del os.environ[key]
    procs.harden_current_process()
    ack = sys.stdout.buffer
    raw = sys.stdin.buffer.readline(HANDOFF_LIMIT)
    sys.stdin.close()
    if not raw.strip():  # site 3 (R2-m5): main's two records, made before any supervisor exists
        spool(run_dir, "launch_failed", "no credential handoff: the launching process ended before handing over "
                                        "custody")
        runlog.write_record(run_dir, {"schema": K.RUN_SCHEMA, "run": run_dir.name, "status": K.LAUNCH_FAILED,
                                      "reason": "no credential handoff: the launching process ended before handing "
                                                "over custody; no process holds this run's credential",
                                      "reason_code": K.launch_failure_code(K.HANDOFF),
                                      "supervisor_pid": os.getpid(), "ended_at": utc_now()})
        return 3
    try:
        handoff = json.loads(raw.decode("utf-8"))
    except ValueError:
        spool(run_dir, "launch_failed", "malformed credential handoff")
        runlog.write_record(run_dir, {"schema": K.RUN_SCHEMA, "run": run_dir.name, "status": K.LAUNCH_FAILED,
                                      "reason": "malformed credential handoff",
                                      "reason_code": K.launch_failure_code(K.HANDOFF), "ended_at": utc_now()})
        return 3
    del raw
    sup = Supervisor(run_dir, handoff, ack)
    handoff.clear()
    try:
        if sup.start():
            sys.stdout = open(os.devnull, "w")  # nothing more for the launcher, which may be gone
            try:
                ack.close()
            except OSError:
                pass
            sup.watch()
            if sup.bridge is not None:  # never exit under a request the engine is still deciding
                sup.bridge.drain(60)
    except BaseException as exc:
        log(traceback.format_exc())
        sup._finish(K.CRASHED, f"supervisor error: {type(exc).__name__}: {exc}")
        return 1
    finally:
        sup.tree.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
