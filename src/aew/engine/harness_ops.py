"""Harness runs of invocations (ADR-0009): launch, credential rotation, custody handoff, status.

A run ``R-<INV>-<n>`` is one harness execution of an invocation, recorded in control state as
``inv.runs[] = {run, harness, token_id, launched_at, kind, generation}``. The engine records runs and
rotates credentials; it never infers anything from a harness: a run that ends, crashes or is lost changes
no AEW state (success is never inferred, WC §8.2). What happened in a run is local telemetry
(``.aew/local/harness/runs/<run>/``), never read by a gate.

Credential custody: the credential of a launched run exists only in the launching process's memory,
then in the supervisor's memory (handed over through the supervisor's stdin pipe). It is never printed,
written, placed in an environment, or given to a model-controlled process.

* ``--launch`` on a dispatch records run 1, which adopts the credential the dispatch issued in-process.
* Every ``aew harness launch`` rotates the credential in the same commit that records the new run: the old
  credential is revoked (``rotated: R-…``), so at most one run can act for an invocation. A credential
  that was ever printed (a dispatch without ``--launch``) dies at the first launch.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from aew.engine import faults
from aew.engine.authority import ROLE_OPERATIONS, require_invocation, require_lead, rotate_invocation_token
from aew.engine.base import TxnContext
from aew.engine.resume_ops import ResumeOps
from aew.errors import HarnessLaunchFailed, IllegalTransition, NotFound, RunLive, UsageError
from aew.harness import contract as K
from aew.harness import procs, registry, runlog
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.snapshot.fingerprint import changed_paths
from aew.util import sha256_text, utc_now

# Never handed to a supervisor (and therefore never to a harness or an agent).
SCRUBBED_ENV = ("AEW_LEAD_TOKEN", "AEW_INVOCATION_TOKEN", "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY", "AEW_INVOCATION",
                "AEW_RUN", "AEW_WORK_UNIT", "AEW_LEAD_BROKER", "AEW_LEAD_BROKER_KEY")
ACK_WAIT_S = float(os.environ.get("AEW_LAUNCH_ACK_S", "90"))


def supervisor_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """The launching process's environment minus every credential-bearing variable."""
    env = dict(os.environ if base is None else base)
    for key in list(env):
        if key.upper() in SCRUBBED_ENV or K.CREDENTIAL_RE.search(env[key] or ""):
            del env[key]
    return env


class HarnessOps(ResumeOps):
    # ------------------------------------------------------------------ launch preconditions

    def _require_launchable(self, state: dict[str, Any], inv_id: str, *, relaunch: bool = True) -> dict[str, Any]:
        inv = state["invocations"].get(inv_id)
        if inv is None:
            raise NotFound(f"no invocation {inv_id}")
        if inv["status"] != "active":
            raise IllegalTransition(f"{inv_id} is {inv['status']}; only an active invocation is launched")
        profile = inv.get("execution_profile")
        if not profile:
            raise IllegalTransition(
                f"{inv_id} has no execution profile, so no harness, provider or model is pinned for it: configure "
                "policy/execution.yaml, or dispatch a new invocation with --profile or --model (ADR-0010)")
        registry.check(profile["harness"])
        if relaunch:  # at dispatch the workspace or observation is being allocated in this same transaction
            self._invocation_workspace(state, inv)  # its workspace, candidate or observation is still live
        return inv

    def _record_launch_run(self, ctx: TxnContext, inv_id: str) -> None:
        """``--launch`` on a dispatch: run 1 adopts the credential this transaction issued."""
        inv = self._require_launchable(ctx.state, inv_id, relaunch=False)
        run = K.run_id(inv_id, 1)
        inv["runs"] = [{"run": run, "harness": inv["execution_profile"]["harness"], "token_id": inv["token_id"],
                        "launched_at": utc_now(), "kind": "dispatch", "generation": ctx.state["lead"]["generation"]}]
        ctx.refs.append(f"run:{run}")

    # ------------------------------------------------------------------ launch

    def harness_launch(self, *, token: str, expect_rev: int, invocation: str, replace: bool = False) -> dict[str, Any]:
        """Launch (or relaunch) a harness run: rotate the credential, record the run, hand custody over."""
        with self.lead_txn(token, expect_rev, "harness.launch") as ctx:
            state = ctx.state
            inv = self._require_launchable(state, invocation)
            pack = self._regenerated_pack(state, invocation)
            if pack["sha256"] != (inv.get("pack") or {}).get("sha256"):
                raise IllegalTransition(
                    f"{invocation}'s context pack no longer matches the pack pinned at dispatch (its inputs changed); "
                    "dispatch a new invocation rather than relaunching this one", pinned=(inv.get("pack") or {}).get(
                        "sha256"), now=pack["sha256"])
            runs = inv.setdefault("runs", [])
            previous = runs[-1] if runs else None
            if previous and not replace and runlog.may_be_live(runlog.run_dir(self.aew_root, previous["run"]),
                                                               previous["launched_at"]):
                raise RunLive(f"{previous['run']} may still be running; stop it (`aew harness stop {previous['run']}`) "
                              "or relaunch with --replace (its credential is revoked either way)",
                              run=previous["run"])
            run = K.run_id(invocation, len(runs) + 1)
            credential = rotate_invocation_token(state, invocation, f"rotated: {run}")
            runs.append({"run": run, "harness": inv["execution_profile"]["harness"], "token_id": inv["token_id"],
                         "launched_at": utc_now(), "kind": "relaunch" if previous else "launch",
                         "generation": state["lead"]["generation"]})
            ctx.refs.append(f"run:{run}")
            ctx.summary = f"{run} launched for {invocation}; credential rotated" + (
                f" (supersedes {previous['run']})" if previous else "")
        revision = ctx.session.committed_revision
        old_dir = runlog.run_dir(self.aew_root, previous["run"]) if previous else None
        if old_dir is not None and old_dir.exists():  # best effort: its credential is already dead, and its
            runlog.request(old_dir, "stop", {"reason": f"superseded by {run}"})  # supervisor notices on its own
        launched = self._spawn_run(invocation, run, credential)
        del credential
        return {"ok": True, "invocation": invocation, **launched,
                "superseded": previous["run"] if previous else None, "revision": revision}

    def launch_dispatched(self, result: dict[str, Any]) -> dict[str, Any]:
        """Finish ``--launch`` on a dispatch: the dispatch-issued credential goes to the run's supervisor and
        is removed from the command's output."""
        credential = result.pop("invocation_token")
        inv_id = result["invocation"]
        run = self.store.read()["invocations"][inv_id]["runs"][-1]["run"]
        result["launch"] = self._spawn_run(inv_id, run, credential)
        del credential
        return result

    def _spawn_run(self, inv_id: str, run: str, credential: str) -> dict[str, Any]:
        """Start the run's supervisor and hand it the credential over its stdin pipe. Never raises after the
        launch commit without saying which run was recorded."""
        faults.hit("harness.launch.after_commit")
        directory = runlog.run_dir(self.aew_root, run)
        directory.mkdir(parents=True, exist_ok=True)
        # The launch (and, with --launch, the dispatch) is committed: every failure below names what was recorded.
        base = {"run": run, "invocation": inv_id, "committed": True, "run_dir": str(directory)}
        with (directory / "supervisor.log").open("ab") as log:
            try:
                proc = procs.spawn_detached([sys.executable, "-m", "aew.harness.supervisor", "--run-dir",
                                             str(directory)], env=supervisor_env(), cwd=str(directory),
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log)
            except OSError as exc:
                raise HarnessLaunchFailed(f"{run} was recorded but its supervisor could not start: {exc}; relaunch "
                                          "with `aew harness launch` (the credential rotates)", **base) from None
        faults.hit("harness.launch.after_spawn")
        handoff = {"credential": credential, "run": run, "invocation": inv_id,
                   "repo_root": str(self.repo_root), "aew_root": str(self.aew_root)}
        try:
            assert proc.stdin is not None
            proc.stdin.write((json.dumps(handoff) + "\n").encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass
        finally:
            handoff.clear()
        faults.hit("harness.launch.after_handoff")
        acks = _read_acks(proc, ACK_WAIT_S)
        custody = next((a for a in acks if "custody" in a), None)
        started = next((a for a in acks if "started" in a), None)
        out = {**base, "supervisor_pid": proc.pid}
        if custody is None:  # no acknowledgement at all: make sure no process holds the credential
            proc.kill()
            raise HarnessLaunchFailed(f"{run}'s supervisor never acknowledged custody; it was stopped. Relaunch "
                                      "with `aew harness launch` (the credential rotates)", **out)
        if not custody["custody"]:
            raise HarnessLaunchFailed(f"{run}'s supervisor refused custody: {custody.get('reason')}", **out,
                                      reason=custody.get("reason"))
        if started is None:  # still starting, or the supervisor ended without a final word: its record says which
            status, record = runlog.observed_status(runlog.run_dir(self.aew_root, run))
            if status in K.TERMINAL:
                raise HarnessLaunchFailed(f"{run} failed to start: {(record or {}).get('reason')}", **out,
                                          status=status, reason=(record or {}).get("reason"))
            return {**out, "status": K.STARTING}
        if not started["started"]:
            raise HarnessLaunchFailed(f"{run} failed to start: {started.get('reason')}", **out,
                                      status=started.get("status"), reason=started.get("reason"))
        return {**out, "status": K.RUNNING, **{k: v for k, v in started.items() if k in {"harness", "session"}}}

    # ------------------------------------------------------------------ contract (read by the supervisor)

    def _regenerated_pack(self, state: dict[str, Any], inv_id: str) -> dict[str, Any]:
        inputs, _ = self._pack_inputs(state, inv_id)
        text = ctxmod.render(inputs)
        return {"text": text, "sha256": sha256_text(text), "path": self._pack_rel(inv_id)}

    def expected_kinds(self, state: dict[str, Any], inv: dict[str, Any]) -> list[str]:
        unit = state["work"][inv["work_unit"]]
        pinned = (unit.get("execution") or {}).get("expected_kind")
        if inv["role"] in E.EXECUTE_KIND and pinned:
            return [pinned]
        return sorted(E.ROLE_KINDS.get(inv["role"], set()))

    def operations_of(self, inv: dict[str, Any]) -> list[str]:
        ops = set(ROLE_OPERATIONS.get(inv["role"], frozenset()))
        if inv.get("allowed_operations") is not None:
            ops &= set(inv["allowed_operations"])
        return sorted(ops)

    def harness_contract(self, state: dict[str, Any], inv_id: str, run: str) -> K.LaunchContract:
        inv = state["invocations"][inv_id]
        pack = self._regenerated_pack(state, inv_id)
        if pack["sha256"] != (inv.get("pack") or {}).get("sha256"):
            raise IllegalTransition(f"{inv_id}'s context pack no longer matches the pack pinned at dispatch")
        workspace, _, base = self._invocation_workspace(state, inv)
        runs = inv.get("runs") or []
        continuation = None
        if len(runs) > 1:
            mine = [e for e in E.scan(self.aew_root, inv["work_unit"])[0] if e["producer"]["invocation"] == inv_id]
            changed = None
            if inv["role"] == "implementer" and base:
                try:
                    changed = changed_paths(workspace, base)
                except Exception:
                    changed = None
            continuation = {"previous_runs": [r["run"] for r in runs[:-1]],
                            "evidence": [{"id": e["id"], "kind": e["kind"], "result": e["result"]} for e in mine],
                            "changed_paths": changed}
        card = inv.get("card")
        return K.LaunchContract(
            run=run, invocation=inv_id, work_unit=inv["work_unit"], role=inv["role"],
            scope=inv.get("scope") or "ticket",
            card={k: card[k] for k in ("id", "version", "sha256")} if card else None,
            execution_profile=inv["execution_profile"], workspace=str(workspace),
            expected_kinds=self.expected_kinds(state, inv), operations=self.operations_of(inv),
            pack_path=str(self.aew_root / pack["path"]), pack_sha256=pack["sha256"], pack_text=pack["text"],
            continuation=continuation, run_dir=str(runlog.run_dir(self.aew_root, run)))

    def run_authority_problem(self, state: dict[str, Any], inv_id: str, run: str, token_id: str) -> str | None:
        """Why a run may no longer act (None while it may). The engine's credential checks remain authoritative;
        this lets a supervisor stop its harness and close its bridge as soon as authority ends."""
        inv = state["invocations"].get(inv_id)
        if inv is None:
            return "invocation unknown"
        if inv["status"] != "active":
            return f"invocation {inv['status']}"
        runs = inv.get("runs") or []
        if not runs or runs[-1]["run"] != run:
            return f"superseded by {runs[-1]['run'] if runs else 'nothing'}"
        tok = state["tokens"].get(token_id) or {}
        if tok.get("revoked_at") or inv["token_id"] != token_id:
            return f"credential revoked: {tok.get('revoke_reason')}"
        if (tok.get("scope") or {}).get("generation") != state["lead"]["generation"]:
            return "issued under a superseded Lead generation"
        return None

    # ------------------------------------------------------------------ identity (bridge + explicit credential)

    def invocation_whoami(self, *, invocation_token: str) -> dict[str, Any]:
        state = self.store.read()
        inv_id, inv, _ = require_invocation(state, invocation_token, "context.read")
        run = next((r["run"] for r in reversed(inv.get("runs") or []) if r["token_id"] == inv["token_id"]), None)
        return {"invocation": inv_id, "run": run, "role": inv["role"], "role_card": self._card_ref(inv),
                "work_unit": inv["work_unit"], "scope": inv.get("scope"), "workspace": inv.get("workspace"),
                "expected_kinds": self.expected_kinds(state, inv), "operations": self.operations_of(inv),
                "execution_profile": inv.get("execution_profile")}

    # ------------------------------------------------------------------ observation (read-only)

    def harness_status(self, invocation: str | None = None) -> dict[str, Any]:
        state = self.store.read()
        out = []
        for inv_id, inv in sorted(state["invocations"].items()):
            if (invocation and inv_id != invocation) or not inv.get("runs"):
                continue
            for i, r in enumerate(inv["runs"]):
                directory = runlog.run_dir(self.aew_root, r["run"])
                observed, record = runlog.observed_status(directory)
                current = i == len(inv["runs"]) - 1 and inv["status"] == "active" and r["token_id"] == inv["token_id"]
                tok = state["tokens"].get(r["token_id"]) or {}
                out.append({"run": r["run"], "invocation": inv_id, "work_unit": inv["work_unit"], "role": inv["role"],
                            "harness": r["harness"], "launched_at": r["launched_at"], "kind": r["kind"],
                            "status": observed, "reason": (record or {}).get("reason"),
                            "authority": "current" if current
                            else f"none ({tok.get('revoke_reason') or inv['status']})",
                            "supervisor_pid": (record or {}).get("supervisor_pid"),
                            "heartbeat_age_s": runlog.heartbeat_age(directory),
                            "evidence": (record or {}).get("evidence") or [], "run_dir": str(directory)})
        if invocation and not out and invocation not in state["invocations"]:
            raise NotFound(f"no invocation {invocation}")
        return {"runs": out}

    def _find_run(self, state: dict[str, Any], run: str) -> tuple[str, dict[str, Any]]:
        for inv_id, inv in state["invocations"].items():
            if any(r["run"] == run for r in inv.get("runs") or []):
                return inv_id, inv
        raise NotFound(f"no run {run}")

    def harness_wait(self, run: str, *, timeout: float = 600.0) -> dict[str, Any]:
        """Wait until a run is no longer running (it ended, failed, was never confirmed, or was lost)."""
        self._find_run(self.store.read(), run)
        directory = runlog.run_dir(self.aew_root, run)
        deadline = time.monotonic() + timeout
        while True:
            status, record = runlog.observed_status(directory)
            if status not in (K.STARTING, K.RUNNING):
                return {"run": run, "status": status, "reason": (record or {}).get("reason"),
                        "evidence": (record or {}).get("evidence") or [], "timed_out": False}
            if time.monotonic() >= deadline:
                return {"run": run, "status": status, "timed_out": True}
            time.sleep(0.2)

    def harness_stop(self, *, token: str, run: str, reason: str) -> dict[str, Any]:
        """Ask a run's supervisor to stop its harness. No AEW state changes; the invocation stays as it is."""
        if not (reason and reason.strip()):
            raise UsageError("stopping a run needs a reason")
        with self.store.session() as s:
            require_lead(s.state, token)
            self._find_run(s.state, run)
        path = runlog.request(runlog.run_dir(self.aew_root, run), "stop", {"reason": reason})
        return {"ok": True, "run": run, "requested": path.name}


def _read_acks(proc: subprocess.Popen[bytes], wait_s: float) -> list[dict[str, Any]]:
    """The supervisor's acknowledgement lines: ``{"custody": ...}`` then ``{"started": ...}``."""
    lines: queue.Queue[bytes | None] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        for raw in iter(proc.stdout.readline, b""):
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    acks: list[dict[str, Any]] = []
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            raw = lines.get(timeout=max(0.05, deadline - time.monotonic()))
        except queue.Empty:
            break
        if raw is None:
            break
        try:
            acks.append(json.loads(raw.decode("utf-8")))
        except ValueError:
            continue
        if "started" in acks[-1]:
            break
    return acks
