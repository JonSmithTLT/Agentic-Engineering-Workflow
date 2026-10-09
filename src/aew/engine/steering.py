"""Crawl/Walk/Run steering: the mode, who may change it, and its records (M4-E E2; A1 §1; CWR §5, §6, §8).

**The mode.** The project default is execution policy's ``steering.mode`` (absent: legacy/manual behaviour, not a
fourth mode). The effective mode is always the mode of the latest A1 §1.3 record, held in control state's
``steering`` key:

- ``standing``: the latest record no Lead generation bounds. Only an adopted default that is not a raise makes one.
- ``override``: an operator raise at the endpoint, or a Lead lowering. It is in force only while its Lead generation
  is current; when that generation ends, the mode falls back to ``standing`` (plan v3 §2.1, P2), so a new generation
  runs above the standing mode only after a fresh raise at the endpoint.

**Who may change it** (A1 §1.1, §1.2). Moving left (``crawl < walk < run``) is a restriction the Lead may make
(:meth:`Steering.lower`). Moving right is an authority increase, made only through the operator endpoint, by a value
only the endpoint constructs (:class:`OperatorPrincipal`, below). An adopted default that is a raise changes nothing
(plan v3 §2.1, N1): ``status`` shows it as pending a raise at the endpoint. The Lead's requests (a raise, a
confirmation) are recorded with their rationale and grant nothing.

**Records.** Every mode change and every closed request is a line in ``records/steering/<date>.jsonl``, append-only,
naming who changed it (with the operator principal's guarantee label), the previous and new mode, the Lead
generation, both policy digests and the revision at which it took effect (A1 §1.3). Nothing reads the mode to act on
it until the steering loop (M4-E E7).

**The guarantee label.** Every operator record is ``guarantee: dev``: the operator principal cannot yet be shown
distinct from the Lead host's (F18.6 has not built the protected-set ownership check), so none of this is A1/F18
production authority (plan v3 §2.1). Nothing in this module can produce another label.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aew.engine.base import V2
from aew.engine.store import Transition
from aew.errors import (
    IllegalTransition,
    MigrationRequired,
    PermissionDenied,
    StaleAuthority,
    SteeringNotConfigured,
    UsageError,
)
from aew.knowledge.records import format_id
from aew.util import utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel

MODES = ("crawl", "walk", "run")
# Absent and crawl rank together: neither auto-executes anything without a confirmation, so absent to crawl is not a
# raise (plan v3 §2.1, N1).
RANK = {None: 0, "crawl": 0, "walk": 1, "run": 2}
GUARANTEE = "dev"  # until F18.6: the only label any operator record carries in M4-E (plan v3 §2.1, §7)
MAX_REQUESTS = 8
RECORDS_DIR = "records/steering"
RECORD_SCHEMA = "aew/steering-record/v1"


@dataclass(frozen=True)
class OperatorPrincipal:
    """Who authorized an operator operation, as the operator endpoint established it: the endpoint's peer check and
    the challenge answered at its console. Constructed only by ``aew.harness.operator_endpoint`` (a static test pins
    it); no CLI parser, broker relay, typed tool or recovery escape can build one. ``guarantee`` is not a field: it
    is ``dev`` for every principal until F18.6."""

    uid: int | None
    method: str  # "peer_credentials" (POSIX) or "named_pipe" (Windows)
    endpoint_pid: int
    endpoint_started_at: str

    @property
    def guarantee(self) -> str:
        return GUARANTEE

    def record(self) -> dict[str, Any]:
        return {"uid": self.uid, "method": self.method, "guarantee": self.guarantee,
                "endpoint": {"pid": self.endpoint_pid, "started_at": self.endpoint_started_at}}


def is_raise(new: str | None, standing: str | None) -> bool:
    """Whether moving to ``new`` from ``standing`` increases autonomy (A1 §1.2)."""
    return RANK[new] > RANK[standing]


def empty() -> dict[str, Any]:
    return {"default": None, "standing": {"mode": None, "record": None, "rev": 0}, "override": None, "requests": []}


def effective(state: dict[str, Any]) -> dict[str, Any]:
    """The effective mode and where it comes from: the override while its generation is current, else the standing
    mode. ``ended`` names an override whose generation has ended (it no longer counts)."""
    s = state.get("steering") or empty()
    generation = int(state["lead"]["generation"])
    override = s.get("override")
    if override and override["generation"] == generation and state["lead"]["status"] != "vacant":
        return {"mode": override["mode"], "source": "raise" if override["by"] == "operator" else "lower",
                "record": override["record"], "rev": override["rev"], "generation": override["generation"]}
    out = {"mode": s["standing"]["mode"], "source": "default" if s["standing"]["record"] else "none",
           "record": s["standing"]["record"], "rev": s["standing"]["rev"], "generation": None}
    if override:
        out["ended"] = {"mode": override["mode"], "generation": override["generation"], "record": override["record"]}
    return out


def notifier_problem(policy: dict[str, Any] | None) -> str | None:
    """Why the adopted notifier cannot deliver, or ``None``: unattended Run needs a configured notifier whose
    ``command[0]`` resolves to an executable file (operator decision 1; plan v3 E2). E7 delivers through it."""
    command = ((policy or {}).get("notify") or {}).get("command") or []
    if not command:
        return "no notifier is configured (execution policy `notify.command`)"
    program = command[0]
    found = shutil.which(program) if os.sep not in program and "/" not in program else program
    if not found or not os.path.isfile(found) or not os.access(found, os.X_OK):
        return f"the notifier `{program}` does not resolve to an executable file"
    return None


class Steering:
    """The steering state's commands and projection."""

    def __init__(self, k: Kernel) -> None:
        self.k = k

    # ------------------------------------------------------------------ reads

    def policy_default(self) -> str | None:
        policy, _ = self.k.execution_policy()
        return ((policy or {}).get("steering") or {}).get("mode")

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        """The steering block of ``status``: the adopted default, the effective mode, a pending raise, open requests.
        ``configured`` is false while the adopted policy names no mode (legacy/manual behaviour)."""
        s = state.get("steering") or empty()
        try:
            default = self.policy_default()
        except Exception:  # noqa: BLE001 (an unreadable or drifted policy is reported by status and doctor)
            default = s.get("default")
        now = effective(state)
        out: dict[str, Any] = {"configured": default is not None, "default": default, "effective": now["mode"],
                               "source": now["source"], "record": now["record"]}
        if now.get("ended"):
            out["ended_override"] = now["ended"]
        if default is not None and is_raise(default, now["mode"]):
            out["pending_raise"] = (f"policy default `{default}`; effective `{now['mode'] or 'none'}`; raise pending "
                                    f"at the operator endpoint (`aew lead mode raise {default}`)")
        generation = int(state["lead"]["generation"])
        open_now = [dict(r) for r in s["requests"] if r["generation"] == generation]  # an ended generation's lapse
        if open_now:
            out["requests"] = open_now
        return out

    # ------------------------------------------------------------------ adoption (plan v3 §2.1, N1)

    def on_adopt(self, ctx: Any, policy: dict[str, Any] | None) -> None:
        """Inside ``manifest adopt``: when the adopted default changed, record it if it is not a raise over the standing
        mode (it then becomes the standing mode, and the effective one: the latest record wins). A raise changes
        nothing; ``status`` shows it pending at the endpoint."""
        state = ctx.state
        default = ((policy or {}).get("steering") or {}).get("mode")
        s = state.get("steering")
        if s is None:
            if default is None:
                return  # a project that never configured steering keeps no steering state
            s = state["steering"] = empty()
        if default == s["default"]:
            return
        previous_default, s["default"] = s["default"], default
        if is_raise(default, s["standing"]["mode"]):
            ctx.summary = (ctx.summary or "") + f"; steering default `{default}` adopted, pending a raise at the " \
                                                "operator endpoint"
            return
        before = effective(state)["mode"]
        record = self._record(ctx, {"kind": "mode_change", "source": "default",
                                    "by": {"kind": "operator", "via": "manifest.adopt", "guarantee": GUARANTEE},
                                    "previous": before, "new": default, "generation": None,
                                    "previous_default": previous_default})
        s["standing"] = {"mode": default, "record": record, "rev": ctx.session.revision + 1}
        s["override"] = None

    # ------------------------------------------------------------------ the operator's raise (A1 §1.1)

    def raise_preview(self, mode: str) -> dict[str, Any]:
        """What a raise to ``mode`` would bind, or the refusal it would get, before the operator is asked: the
        endpoint shows these bindings with its challenge and the commit refuses if any of them moved."""
        state = self.k.store.read()
        self._raise_problem(state, mode)
        digests = self.k.policy_digests()
        return {"project": self.k.project_id, "mode": mode, "previous": effective(state)["mode"],
                "generation": int(state["lead"]["generation"]), "revision": state["revision"],
                "legality_digest": digests["legality_digest"]}

    def raise_mode(self, principal: OperatorPrincipal, *, mode: str, generation: int,
                   legality_digest: str) -> dict[str, Any]:
        """Raise the effective mode to ``mode`` for Lead generation ``generation``: the operator endpoint's commit,
        after its peer check and the challenge at its console. Refused if the generation or the legality digest the
        operator was shown has moved since."""
        if not isinstance(principal, OperatorPrincipal):
            raise PermissionDenied("a steering raise is the operator's, through the operator endpoint "
                                   "(`aew operator serve`); nothing else can authorize it")
        with self.k.store.session() as s:
            state = s.state
            if state.get("schema") != V2:
                raise MigrationRequired("this project's control state is v1: migrate it first")
            self.k.check_manifest_pin(state)
            self._raise_problem(state, mode)
            if int(state["lead"]["generation"]) != generation:
                raise StaleAuthority(
                    f"the operator approved a raise for Lead generation {generation}, but the current generation is "
                    f"{state['lead']['generation']}: run `aew lead mode raise {mode}` again", generation=generation,
                    current=state["lead"]["generation"])
            digests = self.k.policy_digests()  # held to the committed pins, which this session holds the lock over
            if digests["legality_digest"] != legality_digest:
                raise StaleAuthority("the legality-affecting policy changed while the operator was asked: run "
                                     f"`aew lead mode raise {mode}` again", reason="stale_policy")
            actor = {"kind": "operator", "principal": principal.record()}
            ctx = _OperatorTxn(s, actor)
            before = effective(state)["mode"]
            steering = state.setdefault("steering", empty())
            record = self._record(ctx, {"kind": "mode_change", "source": "raise",
                                        "by": {"kind": "operator", "principal": principal.record()},
                                        "previous": before, "new": mode, "generation": generation}, digests=digests)
            steering["override"] = {"mode": mode, "generation": generation, "record": record,
                                    "rev": s.revision + 1, "by": "operator"}
            self._close_requests(ctx, lambda r: r["generation"] != generation, "the Lead generation ended")
            self._close_requests(ctx, lambda r: r["kind"] == "raise" and RANK[r.get("mode")] <= RANK[mode],
                                 f"raised to {mode} by the operator ({record})")
            rev = s.commit(Transition(op="steering.raise", actor=actor,
                                      summary=f"steering mode raised {before or 'none'} -> {mode} for Lead "
                                              f"generation {generation} at the operator endpoint ({record})",
                                      refs=ctx.refs))
        return {"ok": True, "record": record, "previous": before, "mode": mode, "generation": generation,
                "revision": rev, "guarantee": GUARANTEE}

    def _raise_problem(self, state: dict[str, Any], mode: str) -> None:
        if mode not in ("walk", "run"):
            raise UsageError("a raise is to walk or run (lowering is `aew lead mode lower`)")
        policy, _ = self.k.execution_policy()
        if ((policy or {}).get("steering") or {}).get("mode") is None:
            raise SteeringNotConfigured(
                "steering is not configured: the adopted execution policy names no `steering.mode`, so the project "
                "keeps legacy/manual behaviour (decision 3); set it and have the operator adopt it first")
        if state["lead"]["status"] == "vacant":
            raise IllegalTransition("no Lead holds the seat: a raise binds the current Lead generation")
        now = effective(state)["mode"]
        if not is_raise(mode, now):
            raise IllegalTransition(f"the effective mode is already `{now}`: `{mode}` is not a raise",
                                    effective=now)
        if mode == "run":
            problem = notifier_problem(policy)
            if problem:
                raise IllegalTransition(f"unattended Run needs an executable notifier: {problem} (operator decision 1)",
                                        reason="notifier_unavailable")

    # ------------------------------------------------------------------ the Lead's own (A1 §1.2)

    def lower(self, *, token: str, expect_rev: int, mode: str, rationale: str = "") -> dict[str, Any]:
        """The Lead lowers its effective mode for its own generation (a restriction, never authority)."""
        if mode not in ("crawl", "walk"):
            raise UsageError("a Lead lowers to crawl or walk")
        with self.k.lead_txn(token, expect_rev, "steering.lower") as ctx:
            state = ctx.state
            self._require_configured()
            now = effective(state)["mode"]
            if not is_raise(now, mode):
                raise IllegalTransition(f"the effective mode is `{now or 'none'}`: `{mode}` is not lower",
                                        effective=now)
            generation = int(state["lead"]["generation"])
            steering = state.setdefault("steering", empty())
            record = self._record(ctx, {"kind": "mode_change", "source": "lower",
                                        "by": {"kind": "lead", "generation": generation}, "previous": now,
                                        "new": mode, "generation": generation, "rationale": rationale or None})
            steering["override"] = {"mode": mode, "generation": generation, "record": record,
                                    "rev": ctx.session.revision + 1, "by": "lead"}
            self._close_requests(ctx, lambda r: r["generation"] != generation, "the Lead generation ended")
            ctx.summary = f"steering mode lowered {now} -> {mode} by the Lead ({record})"
        return {"ok": True, "record": record, "previous": now, "mode": mode,
                "revision": ctx.session.committed_revision}

    def request(self, *, token: str, expect_rev: int, kind: str, rationale: str, mode: str | None = None,
                action_ref: str | None = None) -> dict[str, Any]:
        """Record the Lead's request for a raise or a confirmation. It grants nothing: only the operator, at the
        endpoint, can raise or confirm (A1 §1.3). One raise request is open at a time (a new one replaces it), and a
        confirmation request replaces one for the same action."""
        if kind not in ("raise", "confirmation"):
            raise UsageError("a request is for a raise or a confirmation")
        if not rationale.strip():
            raise UsageError("a request carries its rationale")
        with self.k.lead_txn(token, expect_rev, "steering.request") as ctx:
            state = ctx.state
            self._require_configured()
            generation = int(state["lead"]["generation"])
            if kind == "raise":
                now = effective(state)["mode"]
                if mode not in ("walk", "run") or not is_raise(mode, now):
                    raise IllegalTransition(f"the effective mode is `{now or 'none'}`: request a raise to a higher "
                                            "mode (walk or run)", effective=now)
            steering = state.setdefault("steering", empty())
            self._close_requests(ctx, lambda r: r["generation"] != generation, "the Lead generation ended")
            if kind == "raise":
                self._close_requests(ctx, lambda r: r["kind"] == "raise", "replaced by a newer raise request")
            else:
                self._close_requests(ctx, lambda r: r["kind"] == "confirmation" and r.get("action_ref") == action_ref,
                                     "replaced by a newer confirmation request")
            if len(steering["requests"]) >= MAX_REQUESTS:
                raise IllegalTransition(f"{MAX_REQUESTS} requests are already open: they wait for the operator")
            state["counters"]["steering_request"] = state["counters"].get("steering_request", 0) + 1
            rid = format_id("SQ", state["counters"]["steering_request"])
            entry: dict[str, Any] = {"id": rid, "kind": kind, "rationale": rationale, "generation": generation,
                                     "at": utc_now(), "rev": ctx.session.revision + 1}
            if kind == "raise":
                entry["mode"] = mode
            else:
                entry["action_ref"] = action_ref
            steering["requests"].append(entry)
            what = f"a raise to {mode}" if kind == "raise" else f"confirmation of {action_ref}"
            ctx.summary = f"the Lead requested {what} ({rid}); it grants nothing until the operator acts"
        return {"ok": True, "request": rid, "revision": ctx.session.committed_revision,
                "next": "the operator decides at the operator endpoint; nothing is granted until then"}

    # ------------------------------------------------------------------ helpers

    def _require_configured(self) -> None:
        if self.policy_default() is None:
            raise SteeringNotConfigured(
                "steering is not configured: the adopted execution policy names no `steering.mode`, so the project "
                "keeps legacy/manual behaviour (decision 3)")

    def _close_requests(self, ctx: Any, which: Any, why: str) -> None:
        steering = ctx.state.get("steering") or {}
        keep, closed = [], []
        for r in steering.get("requests") or []:
            (closed if which(r) else keep).append(r)
        if closed:
            steering["requests"] = keep
            for r in closed:
                self._append(ctx, {"schema": RECORD_SCHEMA, "kind": "request_closed", "request": r, "closed": why,
                                   "at": utc_now(), "revision": ctx.session.revision + 1})

    def _record(self, ctx: Any, body: dict[str, Any], *, digests: dict[str, str] | None = None) -> str:
        """Write one A1 §1.3 record and return its id."""
        state = ctx.state
        state["counters"]["steering_record"] = state["counters"].get("steering_record", 0) + 1
        rid = format_id("SM", state["counters"]["steering_record"])
        d = digests if digests is not None else self.k.policy_digests()
        self._append(ctx, {"schema": RECORD_SCHEMA, "id": rid, **body,
                           "legality_digest": d["legality_digest"], "operational_digest": d["operational_digest"],
                           "revision": ctx.session.revision + 1, "at": utc_now()})
        return rid

    def _append(self, ctx: Any, line: dict[str, Any]) -> None:
        """Append ``line`` to today's steering record file, in the transaction (the file is rewritten whole with the
        new line last; earlier lines are never changed)."""
        rel = f"{RECORDS_DIR}/{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
        pending = getattr(ctx, "_steering_files", None)
        if pending is None:
            pending = {}
            ctx._steering_files = pending
        if rel not in pending:
            path = self.k.aew_root / rel
            pending[rel] = path.read_text(encoding="utf-8") if path.is_file() else ""
        pending[rel] += json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n"
        ctx.session.write(rel, pending[rel], immutable=False)  # replaces this transaction's earlier write of it
        if rel not in ctx.refs:
            ctx.refs.append(rel)


class _OperatorTxn:
    """The parts of a transaction context the record helpers use, for the endpoint's own commit (not a Lead
    transaction: the operator holds no Lead credential)."""

    def __init__(self, session: Any, actor: dict[str, Any]) -> None:
        self.session, self.actor = session, actor
        self.refs: list[str] = []
        self.summary: str | None = None

    @property
    def state(self) -> dict[str, Any]:
        return self.session.state
