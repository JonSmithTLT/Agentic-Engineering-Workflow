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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from aew import errors
from aew.engine import faults
from aew.engine.authority import require_invocation, token_id_of
from aew.harness import agentenv, bridge, procs, registry, runlog
from aew.harness import contract as K
from aew.knowledge import evidence as E
from aew.util import sha256_text, utc_now

TICK_S = 0.25
STATE_POLL_S = 2.0
HANDOFF_LIMIT = 64 * 1024
TERMINATE_S = 20.0


def log(msg: str) -> None:
    sys.stderr.write(K.redact(f"{utc_now()} {msg}\n"))
    sys.stderr.flush()


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
                                       "containment": K.CONTAINMENT,
                                       "status": K.STARTING, "supervisor_pid": os.getpid(), "custody_at": utc_now(),
                                       "timeline": [{"at": utc_now(), "event": "custody"}]}
        self.bridge: bridge.BridgeServer | None = None
        self.adapter: Any = None
        self.tree = procs.ProcessTree()
        self.agent_env: dict[str, str] = {}
        self.stop_reason: tuple[str, str] | None = None  # (status, reason) requested by a bridge refusal
        self._control_seen: Any = None
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
        state = self.engine.store.read()
        return self.engine.run_authority_problem(state, self.inv_id, self.run, self.token_id)

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
                                             env=dict(self.agent_env))
            if op == "submit":
                return self.engine.submit(invocation_token=self._credential, kind=args["kind"], text=args["text"])
        except errors.StaleAuthority as exc:
            self.stop_reason = (K.TERMINATED, f"authority ended: {exc.message}")
            raise
        raise errors.UsageError(f"unknown bridge operation {op}")

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        faults.pause("harness.supervisor.before_custody")  # tests: a supervisor slow to take custody
        state = self.engine.store.read()
        try:
            inv_id, inv, _ = require_invocation(state, self._credential, "context.read")
        except errors.AEWError as exc:
            return self._refuse(f"credential rejected: {exc.message}")
        problem = self.engine.run_authority_problem(state, self.inv_id, self.run, self.token_id)
        if inv_id != self.inv_id or problem:
            return self._refuse(problem or f"credential is for {inv_id}, not {self.inv_id}")
        profile = inv["execution_profile"] or {}
        self.record.update(work_unit=inv["work_unit"], role=inv["role"], harness=profile.get("harness"),
                           execution_profile=profile)
        self._save()  # status: starting — from here the run is visibly held, not merely unconfirmed
        self._starting_beats()
        self._send_ack({"custody": True, "run": self.run, "pid": os.getpid()})
        try:
            contract = self.engine.harness_contract(state, self.inv_id, self.run)
            self.record["contract"] = contract.to_record()
            (self.run_dir / "prompt.md").write_text(K.redact(contract.prompt), encoding="utf-8")
            self.bridge = bridge.BridgeServer(self.handle)
            self.bridge.start()
            self.record["bridge"] = {"endpoint": self.bridge.address}
            Path(contract.scratch).mkdir(parents=True, exist_ok=True)
            self.agent_env = agentenv.build(os.environ, endpoint=self.bridge.address, key_hex=self.bridge.key_hex,
                                            invocation=self.inv_id, run=self.run, work_unit=inv["work_unit"],
                                            scratch=contract.scratch)
            self.adapter = registry.load(profile["harness"])(self.tree, self.run_dir, self.events)
            info = self.adapter.launch(contract, dict(self.agent_env))
            self.record["launch"] = info
        except errors.AEWError as exc:
            return self._launch_failed(f"{exc.code}: {exc.message}")
        except Exception as exc:
            log(traceback.format_exc())
            return self._launch_failed(f"{type(exc).__name__}: {exc}")
        self.record["status"] = K.RUNNING
        self.record["started_at"] = utc_now()
        self.record["harness_pids"] = list(self.tree.pids)
        self._event("started", pids=list(self.tree.pids))
        self._save()
        runlog.beat(self.run_dir)
        self._send_ack({"started": True, "status": K.RUNNING, "harness": profile.get("harness"),
                        "session": (self.record.get("launch") or {}).get("session")})
        faults.hit("harness.supervisor.after_start")
        return True

    def _starting_beats(self) -> None:
        """Beat while the harness starts (a server start plus health checks can take a while); the watchdog loop
        takes over once it runs, so a stalled watchdog shows as a stale heartbeat."""
        self._watching = threading.Event()

        def beat() -> None:
            while not self._watching.wait(runlog.HEARTBEAT_S):
                runlog.beat(self.run_dir)

        runlog.beat(self.run_dir)
        threading.Thread(target=beat, name="aew-starting-heartbeat", daemon=True).start()

    def _refuse(self, reason: str) -> bool:
        self.record.update(status=K.LAUNCH_FAILED, reason=f"custody refused: {reason}", ended_at=utc_now())
        self._event("custody_refused", reason=reason)
        self._save()
        self._send_ack({"custody": False, "reason": reason})
        self._drop_credential()
        return False

    def _launch_failed(self, reason: str) -> bool:
        self._finish(K.LAUNCH_FAILED, reason)
        self._send_ack({"started": False, "status": K.LAUNCH_FAILED, "reason": reason})
        return False

    def watch(self) -> None:
        self._watching.set()
        deadline_s = (self.record.get("execution_profile") or {}).get("deadline_s")
        deadline = time.monotonic() + deadline_s if deadline_s else None
        last_beat = last_poll = 0.0
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
                    if kind == "send":
                        self.adapter.send(str(req.get("text") or ""))
                    elif kind == "interrupt":
                        self.adapter.interrupt()
                except errors.AEWError as exc:
                    self._event("request_failed", kind=kind, error=exc.message)
            if self._control_changed() or now - last_poll >= STATE_POLL_S:
                last_poll = now
                problem = self.authority_problem()
                if problem:
                    return self._finish(K.TERMINATED, f"authority ended: {problem}")
            status = self.adapter.inspect()
            if not status.get("alive"):
                return self._finish_exited(status)
            if deadline is not None and now >= deadline:
                return self._finish(K.TERMINATED, f"deadline of {deadline_s}s exceeded")
            time.sleep(TICK_S)

    def _authorized_requests(self) -> list[dict[str, Any]]:
        """Queued request files that a Lead operation recorded for this run, each acted on once.

        The run directory is model-writable (same user), so a file alone is no request: its name and digest must be
        on this run's entry in control state, which the Lead operation commits before it writes the file. Anything
        else is recorded and discarded (independent review R1)."""
        pending = runlog.take_requests(self.run_dir)
        if not pending:
            return []
        try:
            inv = self.engine.store.read()["invocations"].get(self.inv_id) or {}
            entry = next((r for r in inv.get("runs") or [] if r["run"] == self.run), {})
            recorded = {r["file"]: r for r in entry.get("requests") or []}
        except errors.AEWError as exc:
            recorded = {}
            self._event("request_state_unreadable", error=exc.message)
        out = []
        for name, text in pending:
            want = recorded.get(name)
            why = ("not recorded by a Lead operation" if want is None else
                   "already handled" if name in self._handled else
                   "content differs from the recorded request" if sha256_text(text) != want["sha256"] else None)
            req: Any = None
            if why is None:
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
        if outputs:
            return self._finish(K.ENDED_WITH_EVIDENCE, f"harness exited ({code}) after recording {', '.join(outputs)}")
        if code == 0:
            return self._finish(K.ENDED_WITHOUT_EVIDENCE, "harness exited successfully without recording its expected "
                                f"output ({', '.join(sorted(expected))}); no AEW state changed")
        return self._finish(K.CRASHED, f"harness exited with {code} without recording its expected output")

    def _evidence(self, *, kinds: bool = False) -> list[Any]:
        wid = self.record.get("work_unit")
        if not wid:
            return []
        records, _ = E.scan(self.engine.aew_root, wid)
        mine = [e for e in records if e["producer"].get("run") == self.run]
        return [(e["id"], e["kind"]) for e in mine] if kinds else [e["id"] for e in mine]

    def _finish(self, status: str, reason: str) -> None:
        with self._lock:
            if self.record.get("ended_at"):
                return
            if getattr(self, "_watching", None) is not None:
                self._watching.set()
            if self.bridge is not None:
                self.bridge.close()
            try:
                if self.adapter is not None:
                    self._terminate_adapter()
            finally:  # the tree is killed whatever the adapter managed
                self.tree.kill()
            try:
                self.record["result"] = self.adapter.collect() if self.adapter is not None else {}
            except Exception as exc:
                self.record["result"] = {"error": f"{type(exc).__name__}: {exc}"}
            self._compare_effective()
            self.record["evidence"] = self._evidence()
            self.record.update(status=status, reason=reason, ended_at=utc_now())
            if self.bridge is not None:
                self.record["bridge"].update(requests=self.bridge.requests, refused=self.bridge.refused,
                                             outcomes=self.bridge.outcomes)
            self._event("ended", status=status, reason=reason)
            self._drop_credential()
            leaks = runlog.scan_for_credentials(self.run_dir)
            self.record["credential_scan"] = {"clean": not leaks, "files": leaks}
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
    if not raw.strip():
        runlog.write_record(run_dir, {"schema": K.RUN_SCHEMA, "run": run_dir.name, "status": K.LAUNCH_FAILED,
                                      "reason": "no credential handoff: the launching process ended before handing "
                                                "over custody; no process holds this run's credential",
                                      "supervisor_pid": os.getpid(), "ended_at": utc_now()})
        return 3
    try:
        handoff = json.loads(raw.decode("utf-8"))
    except ValueError:
        runlog.write_record(run_dir, {"schema": K.RUN_SCHEMA, "run": run_dir.name, "status": K.LAUNCH_FAILED,
                                      "reason": "malformed credential handoff", "ended_at": utc_now()})
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
