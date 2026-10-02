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
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from aew.engine import faults
from aew.engine.authority import ROLE_OPERATIONS, require_invocation, require_lead, rotate_invocation_token
from aew.engine.nonmutating_ops import is_nm_ticket
from aew.engine.store import Transition
from aew.errors import AEWError, HarnessLaunchFailed, IllegalTransition, NotFound, RunLive, UsageError
from aew.harness import contract as K
from aew.harness import procs, runlog
from aew.knowledge import context as ctxmod
from aew.knowledge import evidence as E
from aew.roles import archetype
from aew.snapshot.fingerprint import changed_paths
from aew.util import sha256_text, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel
    from aew.engine.ports import ArchivePort, ContextPacksPort, GatesPort, InvocationsPort

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


class Harness:
    """Harness runs of invocations (ADR-0009) and the next action each run implies."""

    def __init__(self, k: Kernel, *, invocations: InvocationsPort, packs: ContextPacksPort, gates: GatesPort,
                 archive: ArchivePort) -> None:
        self.k = k
        self.invocations = invocations
        self.packs = packs
        self.gates = gates
        self.archive = archive

    def harness_launch(self, *, token: str, expect_rev: int, invocation: str, replace: bool = False) -> dict[str, Any]:
        """Launch (or relaunch) a harness run: rotate the credential, record the run, hand custody over."""
        with self.k.lead_txn(token, expect_rev, "harness.launch") as ctx:
            state = ctx.state
            inv = self.invocations.require_launchable(state, invocation)
            pack = self._regenerated_pack(state, invocation)
            if pack["sha256"] != (inv.get("pack") or {}).get("sha256"):
                raise IllegalTransition(
                    f"{invocation}'s context pack no longer matches the pack pinned at dispatch (its inputs changed); "
                    "dispatch a new invocation rather than relaunching this one", pinned=(inv.get("pack") or {}).get(
                        "sha256"), now=pack["sha256"])
            runs = inv.setdefault("runs", [])
            previous = runs[-1] if runs else None
            if previous and not replace and runlog.may_be_live(runlog.run_dir(self.k.aew_root, previous["run"]),
                                                               previous["launched_at"]):
                raise RunLive(f"{previous['run']} may still be running; stop it (`aew harness stop {previous['run']}`) "
                              "or relaunch with --replace (its credential is revoked either way)",
                              run=previous["run"])
            run = K.run_id(invocation, len(runs) + 1)
            stop_old = self._record_request(previous, "stop", {"reason": f"superseded by {run}"}) if previous else None
            credential = rotate_invocation_token(state, invocation, f"rotated: {run}")
            runs.append({"run": run, "harness": inv["execution_profile"]["harness"], "token_id": inv["token_id"],
                         "launched_at": utc_now(), "kind": "relaunch" if previous else "launch",
                         "generation": state["lead"]["generation"]})
            ctx.refs.append(f"run:{run}")
            ctx.summary = f"{run} launched for {invocation}; credential rotated" + (
                f" (supersedes {previous['run']})" if previous else "")
        revision = ctx.session.committed_revision
        old_dir = runlog.run_dir(self.k.aew_root, previous["run"]) if previous else None
        if old_dir is not None and old_dir.exists() and stop_old:  # best effort: its credential is already dead,
            runlog.deliver_request(old_dir, *stop_old)  # and its supervisor notices on its own
        launched = self._spawn_run(invocation, run, credential)
        del credential
        return {"ok": True, "invocation": invocation, **launched,
                "superseded": previous["run"] if previous else None, "revision": revision}

    def launch_dispatched(self, result: dict[str, Any]) -> dict[str, Any]:
        """Finish ``--launch`` on a dispatch: the dispatch-issued credential goes to the run's supervisor and
        is removed from the command's output."""
        credential = result.pop("invocation_token")
        inv_id = result["invocation"]
        run = self.k.store.read()["invocations"][inv_id]["runs"][-1]["run"]
        result["launch"] = self._spawn_run(inv_id, run, credential)
        del credential
        return result

    def _spawn_run(self, inv_id: str, run: str, credential: str) -> dict[str, Any]:
        """Start the run's supervisor and hand it the credential over its stdin pipe. Never raises after the
        launch commit without saying which run was recorded."""
        faults.hit("harness.launch.after_commit")
        directory = runlog.run_dir(self.k.aew_root, run)
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
                   "repo_root": str(self.k.repo_root), "aew_root": str(self.k.aew_root)}
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
            status, record = runlog.observed_status(runlog.run_dir(self.k.aew_root, run))
            if status in K.TERMINAL:
                raise HarnessLaunchFailed(f"{run} failed to start: {(record or {}).get('reason')}", **out,
                                          status=status, reason=(record or {}).get("reason"))
            return {**out, "status": K.STARTING}
        if not started["started"]:
            raise HarnessLaunchFailed(f"{run} failed to start: {started.get('reason')}", **out,
                                      status=started.get("status"), reason=started.get("reason"))
        return {**out, "status": K.RUNNING, **{k: v for k, v in started.items() if k in {"harness", "session"}}}

    def _regenerated_pack(self, state: dict[str, Any], inv_id: str) -> dict[str, Any]:
        inputs, _ = self.packs.pack_inputs(state, inv_id)
        text = ctxmod.render(inputs)
        return {"text": text, "sha256": sha256_text(text), "path": self.packs.pack_rel(inv_id)}

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
        workspace, _, base = self.invocations.invocation_workspace(state, inv)
        runs = inv.get("runs") or []
        continuation = None
        if len(runs) > 1:
            mine = [e for e in E.scan(self.k.aew_root, inv["work_unit"])[0] if e["producer"]["invocation"] == inv_id]
            changed = None
            if inv["role"] == "implementer" and base:
                try:
                    changed = changed_paths(workspace, base)
                except Exception:
                    changed = None
            # Evidence evaluated on a workspace state that is no longer the current one satisfies no gate: say so,
            # or a relaunched agent reads "pass" and stops (found live in M3 step 8).
            now = (self.invocations.current_snapshot(state["work"][inv["work_unit"]]) or {}).get("relevant_inputs_fingerprint")

            def entry(e: dict[str, Any]) -> dict[str, Any]:
                out = {"id": e["id"], "kind": e["kind"], "result": e["result"]}
                seen = (e.get("evaluated_snapshot") or {}).get("relevant_inputs_fingerprint")
                if now and seen and seen != now:
                    out["stale"] = True
                return out

            continuation = {"previous_runs": [r["run"] for r in runs[:-1]],
                            "evidence": [entry(e) for e in mine], "changed_paths": changed}
        card = inv.get("card")
        content = (card or {}).get("content") or {}
        capabilities = set(archetype(inv["role"]).get("capabilities") or [])
        capabilities |= set(content.get("required_capabilities") or []) | set(content.get("optional_capabilities") or [])
        policy, _ = self.k.execution_policy()
        return K.LaunchContract(
            run=run, invocation=inv_id, work_unit=inv["work_unit"], role=inv["role"],
            scope=inv.get("scope") or "ticket",
            card={k: card[k] for k in ("id", "version", "sha256")} if card else None,
            execution_profile=inv["execution_profile"], workspace=str(workspace),
            expected_kinds=self.expected_kinds(state, inv), operations=self.operations_of(inv),
            pack_path=str(self.k.aew_root / pack["path"]), pack_sha256=pack["sha256"], pack_text=pack["text"],
            continuation=continuation, run_dir=str(runlog.run_dir(self.k.aew_root, run)),
            scratch=str(runlog.run_dir(self.k.aew_root, run) / "scratch"),
            # For the harness projection: the pinned card's skills and capabilities, and the NAMES of the provider
            # variables the harness server needs (never their values; the policy's current list, not a pin).
            extra={"card_skills": sorted(content.get("skills") or []), "card_capabilities": sorted(capabilities),
                   "provider_env": list((policy or {}).get("provider_env") or [])})

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

    def invocation_whoami(self, *, invocation_token: str) -> dict[str, Any]:
        state = self.k.store.read()
        inv_id, inv, _ = require_invocation(state, invocation_token, "context.read",
                                            archived=self.archive.archived_credential)
        run = next((r["run"] for r in reversed(inv.get("runs") or []) if r["token_id"] == inv["token_id"]), None)
        return {"invocation": inv_id, "run": run, "role": inv["role"], "role_card": self.invocations.card_ref(inv),
                "work_unit": inv["work_unit"], "scope": inv.get("scope"), "workspace": inv.get("workspace"),
                "expected_kinds": self.expected_kinds(state, inv), "operations": self.operations_of(inv),
                "execution_profile": inv.get("execution_profile")}

    def run_evidence(self, work_unit: str, run: str,
                     _cache: dict[str, list[dict[str, Any]]] | None = None) -> list[str]:
        """A run's evidence, read from the evidence store (sealed, engine-stamped ``producer.run``). A run record is
        telemetry in a directory model-controlled processes can write, so its own evidence list is never shown."""
        cache = {} if _cache is None else _cache
        if work_unit not in cache:
            cache[work_unit] = E.scan(self.k.aew_root, work_unit)[0]
        return sorted(e["id"] for e in cache[work_unit] if e["producer"].get("run") == run)

    def run_results(self, work_unit: str, run: str, _cache: dict[str, list[dict[str, Any]]] | None = None
                    ) -> dict[str, str]:
        """Each of a run's evidence items with its result (pass, fail, blocked), from the same store: a Lead must see
        a `blocked` report before it acts on the run (M3 dogfood report §6.6, E8)."""
        cache = {} if _cache is None else _cache
        if work_unit not in cache:
            cache[work_unit] = E.scan(self.k.aew_root, work_unit)[0]
        return {e["id"]: e.get("result") for e in cache[work_unit] if e["producer"].get("run") == run}

    def harness_status(self, invocation: str | None = None) -> dict[str, Any]:
        state = self.k.store.read()
        if invocation and invocation not in state["invocations"]:  # the runs of an archived invocation (R7)
            state = self.archive.rehydrate_invocation(state, invocation) or state
        elif not invocation:  # and the runs of the most recently finished work (bounded: ``recent``)
            for r in state.get("recent", []):
                if r["id"] not in state["work"]:
                    state = self.archive.rehydrate(state, r["id"]) or state
        cache: dict[str, list[dict[str, Any]]] = {}
        out = []
        for inv_id, inv in sorted(state["invocations"].items()):
            if (invocation and inv_id != invocation) or not inv.get("runs"):
                continue
            for i, r in enumerate(inv["runs"]):
                directory = runlog.run_dir(self.k.aew_root, r["run"])
                observed, record = runlog.observed_status(directory)
                current = i == len(inv["runs"]) - 1 and inv["status"] == "active" and r["token_id"] == inv["token_id"]
                tok = state["tokens"].get(r["token_id"]) or {}
                out.append({"run": r["run"], "invocation": inv_id, "work_unit": inv["work_unit"], "role": inv["role"],
                            "harness": r["harness"], "launched_at": r["launched_at"], "kind": r["kind"],
                            "status": observed, "reason": (record or {}).get("reason"),
                            "containment": (record or {}).get("containment") or K.CONTAINMENT,
                            "authority": "current" if current
                            else f"none ({tok.get('revoke_reason') or inv['status']})",
                            "supervisor_pid": (record or {}).get("supervisor_pid"),
                            "heartbeat_age_s": runlog.heartbeat_age(directory),
                            "evidence": self.run_evidence(inv["work_unit"], r["run"], cache),
                            "results": self.run_results(inv["work_unit"], r["run"], cache),
                            "model_check": ((record or {}).get("model_check") or {}).get("status"),
                            "foreign_sessions": ((record or {}).get("result") or {}).get("foreign_sessions") or [],
                            "run_dir": str(directory)})
        if invocation and not out and invocation not in state["invocations"]:
            raise NotFound(f"no invocation {invocation}")
        return {"runs": out}

    def _find_run(self, state: dict[str, Any], run: str) -> tuple[str, dict[str, Any]]:
        for inv_id, inv in state["invocations"].items():
            if any(r["run"] == run for r in inv.get("runs") or []):
                return inv_id, inv
        inv_id = K.invocation_of_run(run)  # a run of archived work (R7): its invocation names it
        inv = self.archive.archived_invocation(state, inv_id) if inv_id else None
        if inv is not None and any(r["run"] == run for r in inv.get("runs") or []):
            return inv_id, inv
        raise NotFound(f"no run {run}")

    def harness_wait(self, run: str, *, timeout: float = 600.0) -> dict[str, Any]:
        """Wait until a run is no longer running (it ended, failed, was never confirmed, or was lost).

        A run launched moments ago whose supervisor has not written its first record yet is possibly live, as
        the launch preconditions treat it: it is waited on, not reported unconfirmed at once (found by CI)."""
        _, inv = self._find_run(self.k.store.read(), run)
        launched_at = next((r.get("launched_at") for r in inv["runs"] if r["run"] == run), None)
        directory = runlog.run_dir(self.k.aew_root, run)
        deadline = time.monotonic() + timeout
        while True:
            status, record = runlog.observed_status(directory)
            if not runlog.possibly_live(status, launched_at):
                out = {"run": run, "status": status, "reason": (record or {}).get("reason"),
                       "evidence": self.run_evidence(inv["work_unit"], run),
                       "results": self.run_results(inv["work_unit"], run), "timed_out": False}
                # the run's next action, as `aew status` gives it
                action = next((h["action"] for h in self.harness_resume(self.k.store.read()) if h["run"] == run), None)
                if action:
                    out["next_action"] = action
                return out
            if time.monotonic() >= deadline:
                return {"run": run, "status": status, "timed_out": True}
            time.sleep(0.2)

    @staticmethod
    def _record_request(entry: dict[str, Any], kind: str, payload: dict[str, Any]) -> tuple[str, str]:
        """Record a Lead request on its run, in the transaction that authorizes it: the supervisor acts only on a
        request file whose name and digest are recorded here (independent review R1). The file carries the payload,
        so a message's text never enters control state."""
        name, text = runlog.new_request(kind, payload)
        entry.setdefault("requests", []).append({"file": name, "kind": kind, "sha256": sha256_text(text),
                                                 "at": utc_now()})
        return name, text

    def _lead_request(self, token: str, run: str, kind: str, payload: dict[str, Any], *, current: bool,
                      reason: str | None = None) -> dict[str, Any]:
        """Record and deliver a Lead request for a run. Work and invocation state do not change. Like the Lead seat
        operations, it needs no expected revision: it names one run and is checked against the state it commits on."""
        directory = runlog.run_dir(self.k.aew_root, run)
        with self.k.store.session() as s:
            actor = require_lead(s.state, token, archived=self.archive.archived_credential)
            inv_id, inv = self._find_run(s.state, run)
            if current:
                if inv["status"] != "active" or inv["runs"][-1]["run"] != run:
                    raise IllegalTransition(f"{run} is not {inv_id}'s current run (invocation {inv['status']}, "
                                            f"latest run {inv['runs'][-1]['run']})")
                status, _ = runlog.observed_status(directory)
                if status not in (K.STARTING, K.RUNNING):
                    raise IllegalTransition(f"{run} is {status}; relaunch with `aew harness launch` to continue its "
                                            "invocation")
            entry = next(r for r in inv["runs"] if r["run"] == run)
            name, text = self._record_request(entry, kind, payload)
            revision = s.commit(Transition(op=f"harness.{kind}", actor=actor, summary=f"{kind} requested for {run}",
                                           reason=reason, refs=[f"run:{run}"]))
        runlog.deliver_request(directory, name, text)
        return {"ok": True, "run": run, "requested": kind, "file": name, "revision": revision}

    def harness_stop(self, *, token: str, run: str, reason: str) -> dict[str, Any]:
        """Ask a run's supervisor to stop its harness. The invocation stays as it is."""
        if not (reason and reason.strip()):
            raise UsageError("stopping a run needs a reason")
        return self._lead_request(token, run, "stop", {"reason": reason}, current=False, reason=reason)

    def harness_send(self, *, token: str, run: str, text: str) -> dict[str, Any]:
        """Deliver a Lead message to a running agent after its current step. Work and invocation state do not change."""
        if not (text and text.strip()):
            raise UsageError("nothing to send")
        if K.CREDENTIAL_RE.search(text):
            raise UsageError("refusing to send an AEW credential to an agent (its harness would persist it)")
        return self._lead_request(token, run, "send", {"text": text}, current=True)

    def harness_interrupt(self, *, token: str, run: str) -> dict[str, Any]:
        """Stop a run's current turn, keeping its session: `harness send` continues it. Work and invocation state do
        not change."""
        return self._lead_request(token, run, "interrupt", {}, current=True)

    def harness_config(self, harness: str, *, invocation: str | None = None, lead: bool = False,
                       lead_projection: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """The exact projection a harness receives, for inspection (read-only; prints no secret). The Lead's projection
        describes the whole Engine (``aew opencode``), so the facade supplies it as ``lead_projection``."""
        if harness != "opencode":
            raise UsageError(f"no projection for harness {harness!r}; known: opencode")
        from aew.harness.opencode import projection

        if lead == bool(invocation):
            raise UsageError("name an invocation, or pass --lead")
        if lead:
            return {"harness": harness, "target": "lead", **lead_projection()}
        state = self.k.store.read()
        inv = state["invocations"].get(invocation or "")
        if inv is None:
            raise NotFound(f"no invocation {invocation}")
        if not inv.get("execution_profile"):
            raise IllegalTransition(f"{invocation} has no execution profile, so it has no harness projection")
        runs = inv.get("runs") or []
        contract = self.harness_contract(state, invocation or "", K.run_id(invocation or "", len(runs) + 1))
        state_dir = os.path.realpath(runlog.run_dir(self.k.aew_root, contract.run) / "harness")
        config = projection.invocation_config(contract, private_dirs=projection.private_output_dirs(
            state_dir, os.sep, scratch=os.path.realpath(contract.scratch)))
        directory = os.path.realpath(contract.workspace)
        return {"harness": harness, "target": invocation, "for_run": contract.run, "config": config,
                "session": projection.session_body(contract, directory, config["permissions"]),
                "skills": projection.skills(contract),
                "prompt": {"bytes": len(contract.prompt.encode("utf-8")), "pack_sha256": contract.pack_sha256},
                "server_env": {"provider_variables": contract.extra.get("provider_env") or [],
                               "private": ["XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                                           "OPENCODE_CONFIG_CONTENT", "OPENCODE_DISABLE_PROJECT_CONFIG",
                                           "OPENCODE_DISABLE_AUTOUPDATE", "OPENCODE_PASSWORD (random, per run)"]},
                "agent_env": ["operating-system basics", "PATH (aew first)", "PYTHONUTF8", "AEW_INVOCATION", "AEW_RUN",
                              "AEW_WORK_UNIT", "AEW_AGENT_ENDPOINT", "AEW_AGENT_KEY"]}

    def harness_resume(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """The latest harness run of every active invocation that has runs (ADR-0009; empty without runs).

        Local telemetry, never read by a gate. A harness that ended, crashed or was lost changes no AEW state and
        is not an interruption (M3-B1): the invocation keeps its authority and is relaunched or cancelled."""
        from aew.harness import contract as K
        from aew.harness import runlog

        out = []
        for inv_id, inv in sorted(state["invocations"].items()):
            if inv["status"] != "active" or not inv.get("runs"):
                continue
            run = inv["runs"][-1]["run"]
            status, record = runlog.observed_status(runlog.run_dir(self.k.aew_root, run))
            produced = [e for e in E.scan(self.k.aew_root, inv["work_unit"])[0]  # the store, not the record
                        if e["producer"].get("run") == run]
            evidence = sorted(e["id"] for e in produced)
            if status in (K.STARTING, K.RUNNING):
                action = f"{run} is running for {inv_id}: follow it with `aew harness wait {run}`"
            elif status == K.ENDED_WITH_EVIDENCE:
                action = (f"{run} ended with evidence {', '.join(evidence)}: "
                          f"{self._after_run(state, inv, produced)} (the run itself decides nothing)")
            else:
                action = (f"{inv_id} has no live run ({run}: {status}): relaunch it with `aew harness launch {inv_id} "
                          f"--expect-rev N` (its credential rotates) or cancel it with `aew invoke cancel {inv_id}`")
            out.append({"invocation": inv_id, "work_unit": inv["work_unit"], "role": inv["role"], "run": run,
                        "status": status, "reason": (record or {}).get("reason"), "evidence": evidence,
                        "action": action})
        return out

    def _after_run(self, state: dict[str, Any], inv: dict[str, Any], produced: list[dict[str, Any]]) -> str:
        """What the Lead does with a finished run's evidence, as the command that applies (M3-D8)."""
        wid = inv["work_unit"]
        unit = state["work"].get(wid) or {}
        if inv["role"] == "implementer":
            blocked = self.implementation_blocker(state, wid)
            if blocked:
                return f"its implementation report is in, but {blocked}"
            return f"its implementation report moves {wid} on by transition: {self.after_implementation(state, wid)}"
        command = {"reviewer": "aew review ingest", "verifier": "aew verify ingest"}.get(inv["role"])
        if command is None and is_nm_ticket(unit):
            command = "aew evidence ingest"
        records = sorted(e["id"] for e in produced if e["kind"] != "check_result") or ["<id>"]
        if command is None:
            return "ingest it"
        return "ingest it: " + ", ".join(f"`{command} {wid} --evidence {e}`" for e in records)

    def after_implementation(self, state: dict[str, Any], wid: str) -> str:
        """The transition(s) that take a mutating Ticket on once its implementer's report and checks are in."""
        unit = state["work"][wid]
        try:
            gc = self.gates.gate_context(state, wid)
            to = ("REVIEW_PENDING" if self.gates.review_gates(gc) else "VERIFY_PENDING" if self.gates.verification_gates(gc)
                  else "COMMIT_READY")
            step = f"`aew work transition {wid} --to {to}`"
        except AEWError:
            step = f"`aew work transition {wid} --to REVIEW_PENDING|VERIFY_PENDING|COMMIT_READY` (as its gates require)"
        if unit["state"] == "ASSIGNED":
            return f"`aew work transition {wid} --to RUNNING`, then {step}"
        return step

    def implementation_blocker(self, state: dict[str, Any], wid: str) -> str | None:
        """Why a mutating Ticket cannot move on although its implementer has reported, or None: a report that is not
        a pass, or a gate the next transition would refuse. A next action never proposes a transition its gates will
        refuse (M3 dogfood report §6.6, E8: `aew status` proposed one, twice)."""
        unit = state["work"][wid]
        try:
            gc = self.gates.gate_context(state, wid)
        except AEWError:
            return None
        reasons = []
        reports = [e for e in gc["evidence"] if e["kind"] == "implementation_report"
                   and e["producer"].get("invocation") == unit.get("implementer_invocation")]
        if reports:
            report = max(reports, key=lambda e: e.get("seq") or 0)
            if report.get("result") != "pass":
                deviations = (report.get("implementation") or {}).get("deviations") or []
                first = str(deviations[0]) if deviations else ""
                reasons.append(f"its implementer's report is {report.get('result')}"
                               + (f" ({first[:160]}{'...' if len(first) > 160 else ''})" if first else ""))
        try:
            self.gates.require_gates(gc, self.gates.PRE_REVIEW, what="the next transition")
        except AEWError as exc:
            reasons.append(exc.message)
        if not reasons:
            return None
        return f"{wid} cannot move on yet: {'; '.join(reasons)}. `aew gate show {wid}` shows what blocks it"



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
