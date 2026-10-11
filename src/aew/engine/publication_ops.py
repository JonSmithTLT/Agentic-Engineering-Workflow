"""``PUBLISH_IF_CLEAN``: the operator's publication envelope, the Lead's request, and its exercise by the custodian
(M4-E E6b; plan v3 §2.2, §2.3; A1 §1, §5; the idea note's §17; HSD-22, HSD-23).

**The envelope is the operator's** (operator Q1, 2026-10-07). ``aew operator grant-publication`` grants it through the
operator endpoint, by a value only the endpoint constructs (``OperatorPrincipal``), after the challenge at its console.
It is a standing, bounded authorization: the sealed M4-H run manifest (its SHA-256, re-verified at every exercise),
the task input's hash (checked at grant against ``--task``), the Lead generation it was granted to, the authoritative
ref publication may move, an expiry (at most 72 h, and never past the manifest's ``envelope_duration_s``), a maximum
number of successful publications (never more than the manifest's ``max_publications``), the legality digest and the
policy pins. The record is cold and immutable (``records/authorizations/<PA-n>.yaml``); control state keeps the active
envelope's id, the record's digest, its counters and its status (``authorization``). One envelope at a time: a new
grant supersedes it, and so does ``revoke-publication``. A generation change, expiry, a manifest mismatch or
exhaustion ends it (:meth:`Publication.finalize`, every transaction); every exercise re-checks everything regardless.

**The Ticket belongs to the sealed run:** ``work.create`` stamps ``authorization_envelope: <PA-n>`` on each Ticket the
envelope's own Lead generation creates while it is active (:func:`stamp`). Tickets made before the grant, or by
another generation, carry no stamp and can never use it.

**The Lead's request grants nothing** (A1 §1.2). ``ticket_prepare(publish_if_clean: true)`` records a conditional
publication request on the integration attempt (the queue entry's attempt, so it lives exactly as long as the lease
and survives the one rebuild under it): the Ticket's record digest and state, ``commit_ready_seq`` and the entry, the
accepted plan and its acceptance binding, the obligation binding and the legality digest, the Lead generation, and the
conditions (``pic/v1``, §17's predicate). H and M are the candidate's base and commit.

**The exercise is the custodian's, never the steering loop's** (§2.3; A1 §5). In checks mode, a clean validation
under a lease whose attempt carries a request is routed by :meth:`Publication.on_clean` inside the custodian's own
validation commit: the envelope's usability first (the Ticket belongs to the sealed run and the request falls inside
the envelope), then §17's eight clauses in order. Unusable: VALIDATE_ONLY, as with no request (VALIDATED), the
condition recorded. A clause fails: not exercised, the first failure recorded, the lease released to
AWAITING_DISPOSITION; a moved head (clause 3) is first answered by the one automatic rebuild under the same lease
(PIC survives exactly that one), and a second move goes to disposition. All pass: the integration moves to
``publishing`` in that same commit, one publication is reserved, and the custodian's finish (``_finish_publish``
under its custody credential) re-checks all of it before the CAS. In verifier mode a request is recorded and never
exercised (designer, 2026-10-07: the engine never accepts a verifier report on the Lead's behalf).

**The count is crash-safe** (n4): reserved at the begin, converted to ``published`` in the commit that records
``integrated`` (the custodian's finish, or ``integrate reconcile`` confirming a CAS that landed before a crash), and
released by any path that proves nothing was published. A reconcile of a PIC publish whose CAS never landed never
completes it: the candidate returns VALIDATED, for the current generation to publish under fresh authority (HSD-22,
HSD-23).

Every operator record is ``guarantee: dev`` (plan v3 §2.1): the operator principal cannot yet be shown distinct from
the Lead host's (F18.6).
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aew.engine import disposition_ops as DO
from aew.engine import gates as G
from aew.engine import queue_ops as Q
from aew.engine.base import POLICY_PINS, V2
from aew.engine.steering import GUARANTEE, OperatorPrincipal
from aew.engine.store import Transition
from aew.errors import (
    IllegalTransition,
    MigrationRequired,
    PermissionDenied,
    StaleAuthority,
    UsageError,
)
from aew.knowledge.records import format_id
from aew.policy import validation as V
from aew.util import dump_yaml, load_yaml, sha256_bytes, sha256_file, sha256_text, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel

KEY = "authorization"  # control state's hot key (plan v3 §2.7): the latest envelope, active or ended
RECORDS_DIR = "records/authorizations"
RECORD_SCHEMA = "aew/publication-envelope/v1"
PIC_SCHEMA = "aew/pic-record/v1"
CONDITIONS = "pic/v1"  # §17's predicate, by version id (plan v3 §2.2)
MANIFEST_SCHEMA = "aew/m4h-run-manifest/v1"  # ADR-0018 D4, interface I2
MAX_DURATION_S = 72 * 3600  # plan v3 §9: an envelope lasts at most 72 h
MAX_MANIFEST_BYTES = 64 * 1024
ACTIVE, ENDED = "active", "ended"
# Why an envelope cannot be used now, in plan v3 §2.2's order: each is a case of `test_envelope_unusable`.
USABILITY = ("revoked", "expiry", "exhausted", "generation", "manifest", "stamp", "ref", "legality")
# §17's clauses, in order (plan v3 §2.3): each is a function below, and the first that fails is the reason recorded.
CLAUSES = {1: "the integrate.prepare decision is still allowed",
           2: "the obligation binding and the legality digest are unchanged since the request",
           3: "the authoritative head is still H",
           4: "every required integration check passes",
           5: "no required finding remains",
           6: "nothing policy marks requires_disposition is open",
           7: "no open high anomaly concerns the Ticket or the integration",
           8: "no override, waiver, conflict or unexpected policy branch was required"}
# Reservation states on a PIC record: held from the begin until a commit settles it.
HELD, PUBLISHED, RELEASED = "held", "published", "released"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(when: datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def envelope(state: dict[str, Any]) -> dict[str, Any] | None:
    """The latest envelope as control state keeps it (active or ended), or None."""
    return state.get(KEY)


def active(state: dict[str, Any]) -> dict[str, Any] | None:
    """The envelope, while it is active and of the current Lead generation and not yet expired; else None."""
    env = envelope(state)
    if env is None or env["status"] != ACTIVE or env["generation"] != int(state["lead"]["generation"]):
        return None
    return env if _now() < _parse(env["expires_at"]) else None


def stamp(state: dict[str, Any], unit: dict[str, Any]) -> None:
    """``work.create``'s stamp (plan v3 §2.2): a Ticket the envelope's own Lead generation creates while it is active
    belongs to the sealed run. Any other unit carries none."""
    env = active(state)
    if env is not None and unit.get("kind") == "ticket" and state["lead"]["status"] == "active":
        unit["authorization_envelope"] = env["id"]


def request_of(state: dict[str, Any], work_id: str) -> dict[str, Any] | None:
    """The PIC request on ``work_id``'s current lease attempt, or None (no lease, or no request)."""
    lease = Q.lease_of(state, work_id)
    if lease is None:
        return None
    attempts = state["queue"]["entries"][lease["entry"]]["attempts"]
    return attempts[-1].get("pic_request") if attempts else None


def parse_duration(text: str) -> int:
    """``--for``: seconds, or a number with ``s``, ``m``, ``h`` or ``d``."""
    raw = str(text).strip().lower()
    unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(raw[-1:], None)
    number = raw[:-1] if unit else raw
    try:
        value = int(number) * (unit or 1)
    except ValueError:
        raise UsageError(f"a duration is seconds, or a number with s, m, h or d (e.g. 24h), not {text!r}") from None
    if value <= 0:
        raise UsageError("a duration is positive")
    return value


class Publication:
    """The envelope's grant and revocation (the operator endpoint's commits), its finalizer, the Lead's request, and
    the custodian's exercise of §17 with its crash-safe count."""

    def __init__(self, k: Kernel, *, units: Any, gates: Any, queue: Any, dispatch: Any, integration: Any) -> None:
        self.k = k
        self.units = units
        self.gates = gates
        self.queue = queue
        self.dispatch = dispatch
        self.integration = integration

    # ------------------------------------------------------------------ the operator's grant (plan v3 §2.2)

    def _manifest(self, path: str) -> tuple[Path, str, dict[str, Any]]:
        """The sealed run manifest at ``path``: its absolute path, the SHA-256 of its bytes, and the fields the grant
        reads, each checked (ADR-0018 D4). Never more than it reads: the evaluator validates the rest."""
        where = Path(path).expanduser().resolve()
        try:
            raw = where.read_bytes()
        except OSError as exc:
            raise UsageError(f"the run manifest {where} cannot be read ({exc})") from None
        if len(raw) > MAX_MANIFEST_BYTES:
            raise UsageError(f"the run manifest {where} is larger than {MAX_MANIFEST_BYTES} bytes")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise UsageError(f"the run manifest {where} is not JSON") from None
        hexes = ("task_input_sha256", "seal_sha256", "treatment_sha256")
        if (not isinstance(data, dict) or data.get("schema") != MANIFEST_SCHEMA
                or not all(isinstance(data.get(h), str) and len(data[h]) == 64
                           and all(c in "0123456789abcdef" for c in data[h]) for h in hexes)
                or not isinstance(data.get("run_id"), str)
                or not all(isinstance(data.get(n), int) and not isinstance(data.get(n), bool) and data[n] >= 1
                           for n in ("max_publications", "envelope_duration_s"))):
            raise UsageError(f"{where} is not an {MANIFEST_SCHEMA} run manifest (its schema, run_id, the three "
                             "hashes, max_publications and envelope_duration_s are read)")
        return where, sha256_bytes(raw), data

    def grant_preview(self, *, manifest: str, task: str, duration_s: int | None = None,
                      max_publications: int | None = None) -> dict[str, Any]:
        """What a grant would bind, or the refusal it would get, before the operator is asked: the endpoint shows these
        bindings with its challenge, and the commit refuses if any of them moved."""
        state = self.k.store.read()
        self._grant_problem(state)
        where, digest, data = self._manifest(manifest)
        task_path = Path(task).expanduser().resolve()
        task_sha = sha256_file(task_path) if task_path.is_file() else None  # hashed in chunks: any size
        if task_sha is None:
            raise UsageError(f"the task file {task_path} cannot be read")
        if task_sha != data["task_input_sha256"]:
            raise PermissionDenied(
                f"the task file's SHA-256 ({task_sha}) is not the sealed manifest's task_input_sha256 "
                f"({data['task_input_sha256']}): the envelope is granted only for the sealed run's own task (n3)",
                reason="task_mismatch", task_sha256=task_sha, manifest_task_sha256=data["task_input_sha256"])
        ceiling = min(MAX_DURATION_S, data["envelope_duration_s"])
        duration = ceiling if duration_s is None else int(duration_s)
        if not 0 < duration <= ceiling:
            raise UsageError(f"an envelope lasts at most {ceiling} s (72 h, and the sealed manifest's "
                             f"envelope_duration_s {data['envelope_duration_s']})", requested=duration)
        most = data["max_publications"] if max_publications is None else int(max_publications)
        if not 0 < most <= data["max_publications"]:
            raise UsageError(f"an envelope allows at most the sealed manifest's max_publications "
                             f"({data['max_publications']})", requested=most)
        digests = self.k.policy_digests()
        return {"project": self.k.project_id, "generation": int(state["lead"]["generation"]),
                "revision": state["revision"], "run_manifest": {"path": str(where), "sha256": digest},
                "run_id": data["run_id"], "task_input_sha256": data["task_input_sha256"], "duration_s": duration,
                "max_publications": most, "target_ref": self._target_ref(),
                "legality_digest": digests["legality_digest"], "supersedes": (active(state) or {}).get("id")}

    def _grant_problem(self, state: dict[str, Any]) -> None:
        if state.get("schema") != V2:
            raise MigrationRequired("this project's control state is v1: migrate it first")
        if state["lead"]["status"] != "active":
            raise IllegalTransition("no active Lead holds the seat: an envelope binds the current Lead generation")

    def _target_ref(self) -> str:
        return f"refs/heads/{self.k.authoritative_branch}"

    def grant(self, principal: OperatorPrincipal, *, bound: dict[str, Any]) -> dict[str, Any]:
        """Grant the envelope the operator was shown (``bound``, from :meth:`grant_preview`): the operator endpoint's
        commit, after its peer check and the challenge at its console. Refused if the generation, the legality digest
        or the manifest's bytes moved since."""
        if not isinstance(principal, OperatorPrincipal):
            raise PermissionDenied("a publication envelope is the operator's, granted through the operator endpoint "
                                   "(`aew operator serve`); nothing else can grant it (A1 §1)")
        with self.k.store.session() as s:
            state = s.state
            self._grant_problem(state)
            self.k.check_manifest_pin(state)
            if int(state["lead"]["generation"]) != bound["generation"]:
                raise StaleAuthority(f"the operator approved an envelope for Lead generation {bound['generation']}, "
                                     f"but the current generation is {state['lead']['generation']}: grant it again",
                                     generation=bound["generation"], current=state["lead"]["generation"])
            digests = self.k.policy_digests()
            if digests["legality_digest"] != bound["legality_digest"]:
                raise StaleAuthority("the legality-affecting policy changed while the operator was asked: grant it "
                                     "again", reason="stale_policy")
            _where, digest, _data = self._manifest(bound["run_manifest"]["path"])
            if digest != bound["run_manifest"]["sha256"]:
                raise StaleAuthority("the run manifest changed while the operator was asked: grant it again",
                                     reason="manifest_changed")
            actor = {"kind": "operator", "principal": principal.record()}
            superseded = self._end(state, "superseded", s.revision + 1)
            state["counters"]["authorization"] = state["counters"].get("authorization", 0) + 1
            pa = format_id("PA", state["counters"]["authorization"])
            granted = _now()
            record = {"schema": RECORD_SCHEMA, "id": pa, "project_id": self.k.project_id,
                      "run_manifest": dict(bound["run_manifest"]), "run_id": bound["run_id"],
                      "task_input_sha256": bound["task_input_sha256"], "lead_generation": bound["generation"],
                      "target_ref": bound["target_ref"],
                      "expires_at": _iso(granted + timedelta(seconds=bound["duration_s"])),
                      "max_publications": bound["max_publications"], "legality_digest": digests["legality_digest"],
                      "policy_pins": dict(state.get(POLICY_PINS) or {}), "principal": principal.record(),
                      "granted_at": _iso(granted), "granted_rev": s.revision + 1, "conditions": CONDITIONS}
            rel = f"{RECORDS_DIR}/{pa}.yaml"
            text = dump_yaml(record)
            s.write(rel, text)
            state[KEY] = {"id": pa, "record": {"path": rel, "sha256": sha256_text(text)},
                          "generation": bound["generation"], "expires_at": record["expires_at"],
                          "max_publications": bound["max_publications"], "published": 0, "reserved": 0,
                          "status": ACTIVE, "ended": None}
            rev = s.commit(Transition(
                op="authorization.grant", actor=actor, refs=[rel],
                summary=f"publication envelope {pa} granted at the operator endpoint for Lead generation "
                        f"{bound['generation']}: at most {bound['max_publications']} publication(s) until "
                        f"{record['expires_at']}" + (f" (supersedes {superseded})" if superseded else "")))
        return {"ok": True, "envelope": pa, "record": rel, "expires_at": record["expires_at"],
                "max_publications": bound["max_publications"], "generation": bound["generation"],
                "supersedes": superseded, "revision": rev, "guarantee": GUARANTEE}

    def revoke_preview(self) -> dict[str, Any]:
        state = self.k.store.read()
        env = envelope(state)
        if env is None or env["status"] != ACTIVE:
            raise IllegalTransition("no publication envelope is active: there is nothing to revoke")
        return {"project": self.k.project_id, "envelope": env["id"], "published": env["published"],
                "reserved": env["reserved"], "expires_at": env["expires_at"]}

    def revoke(self, principal: OperatorPrincipal, *, envelope_id: str) -> dict[str, Any]:
        """End the active envelope (the operator endpoint's commit). A publication already begun under it settles as
        any other: revoking stops every later exercise, never a CAS in flight."""
        if not isinstance(principal, OperatorPrincipal):
            raise PermissionDenied("revoking a publication envelope is the operator's, through the operator endpoint")
        with self.k.store.session() as s:
            state = s.state
            env = envelope(state)
            if env is None or env["status"] != ACTIVE or env["id"] != envelope_id:
                raise StaleAuthority(f"{envelope_id} is no longer the active envelope", envelope=envelope_id)
            self._end(state, "revoked", s.revision + 1)
            rev = s.commit(Transition(op="authorization.revoke",
                                      actor={"kind": "operator", "principal": principal.record()},
                                      summary=f"publication envelope {envelope_id} revoked at the operator endpoint"))
        return {"ok": True, "envelope": envelope_id, "revoked": True, "revision": rev, "guarantee": GUARANTEE}

    @staticmethod
    def _end(state: dict[str, Any], reason: str, rev: int) -> str | None:
        env = envelope(state)
        if env is None or env["status"] != ACTIVE:
            return None
        env["status"] = ENDED
        env["ended"] = {"reason": reason, "at": utc_now(), "rev": rev}
        return str(env["id"])

    # ------------------------------------------------------------------ the envelope's end (a finalizer)

    def finalize(self, ctx: Any) -> None:
        """Every transaction: an active envelope whose generation ended, that expired, whose manifest no longer hashes
        to its record, or that is exhausted, ends here, with its reason (plan v3 §2.2). Its usability is re-checked at
        every exercise regardless; this keeps control state truthful for ``status`` and the notifier (M4-E E7d)."""
        state = ctx.state
        env = envelope(state)
        if env is None or env["status"] != ACTIVE:
            return
        why = None
        if env["generation"] != int(state["lead"]["generation"]):
            why = "generation"
        elif _now() >= _parse(env["expires_at"]):
            why = "expiry"
        elif env["published"] >= env["max_publications"]:
            why = "exhausted"
        else:
            record = self._record(env)
            if record is None or self._manifest_problem(record) is not None:
                why = "manifest"
        if why is not None:
            self._end(state, why, ctx.session.revision + 1)

    def _record(self, env: dict[str, Any]) -> dict[str, Any] | None:
        """The envelope's cold record, read and checked against the digest control state keeps; None if it is gone
        or differs."""
        path = self.k.aew_root / env["record"]["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if sha256_text(text) != env["record"]["sha256"]:
            return None
        data = load_yaml(text, source=str(path))
        return data if isinstance(data, dict) else None

    @staticmethod
    def _manifest_problem(record: dict[str, Any]) -> str | None:
        where = Path(record["run_manifest"]["path"])
        try:
            raw = where.read_bytes()
        except OSError:
            return f"the run manifest {where} cannot be read"
        if sha256_bytes(raw) != record["run_manifest"]["sha256"]:
            return f"the run manifest {where} no longer hashes to {record['run_manifest']['sha256']}"
        return None

    # ------------------------------------------------------------------ usability (plan v3 §2.2)

    def usable(self, state: dict[str, Any], work_id: str, *, holding: bool = False) -> tuple[str | None, str]:
        """``envelope_usable`` for ``work_id`` now: ``(None, envelope id)``, or the first condition that fails (one of
        :data:`USABILITY`) with why. ``holding``: the exercise already holds one reservation (the finish)."""
        env = envelope(state)
        if env is None:
            return "revoked", "no publication envelope has been granted"
        if env["status"] != ACTIVE:
            reason = (env.get("ended") or {}).get("reason")
            return (reason if reason in USABILITY else "revoked"), f"envelope {env['id']} ended ({reason})"
        if _now() >= _parse(env["expires_at"]):
            return "expiry", f"envelope {env['id']} expired at {env['expires_at']}"
        if env["published"] + env["reserved"] - (1 if holding else 0) >= env["max_publications"]:
            return "exhausted", (f"envelope {env['id']} allows {env['max_publications']} publication(s): "
                                 f"{env['published']} made, {env['reserved']} reserved")
        if env["generation"] != int(state["lead"]["generation"]):
            return "generation", (f"envelope {env['id']} is Lead generation {env['generation']}'s; the current one is "
                                  f"{state['lead']['generation']} (HSD-23)")
        record = self._record(env)
        if record is None:
            return "manifest", f"envelope {env['id']}'s record is missing or differs from its digest"
        problem = self._manifest_problem(record)
        if problem is not None:
            return "manifest", problem
        unit = state["work"].get(work_id) or {}
        if unit.get("authorization_envelope") != env["id"]:
            return "stamp", (f"{work_id} does not belong to the sealed run: it carries "
                             f"{unit.get('authorization_envelope') or 'no'} envelope stamp, not {env['id']}")
        if record["target_ref"] != self._target_ref():
            return "ref", f"the integration ref is {self._target_ref()}, not the envelope's {record['target_ref']}"
        if (self.k.policy_digests()["legality_digest"] != record["legality_digest"]
                or dict(state.get(POLICY_PINS) or {}) != record["policy_pins"]):
            return "legality", "the legality digest or the policy pins changed since the envelope was granted"
        return None, str(env["id"])

    # ------------------------------------------------------------------ the Lead's request (plan v3 §2.2)

    def record_request(self, ctx: Any, work_id: str) -> dict[str, Any]:
        """``ticket_prepare(publish_if_clean: true)``, in the prepare's own commit: the request on the lease's attempt,
        binding §17's inputs. It grants nothing: what can be exercised is decided at the custodian's commit."""
        from aew.engine.stage_intents import armed_intent

        state = ctx.state
        unit = self.units.unit(state, work_id)
        integ = unit.get("integration") or {}
        lease = Q.lease_of(state, work_id)
        if lease is None or integ.get("status") != "prepared":
            return {"requested": False, "why": "no candidate was prepared under a lease (a conflict or a refusal)"}
        entry = state["queue"]["entries"][lease["entry"]]
        ob = V.obligation(state, work_id, self.k.policy("gates"))
        intent = armed_intent()
        arguments = ((state.get("stage_intents") or {}).get(intent or "") or {}).get("arguments") or {}
        plan = unit.get("plan") or {}
        request = {"conditions": CONDITIONS, "at": utc_now(), "rev": ctx.session.revision + 1,
                   "generation": int(state["lead"]["generation"]), "requested_by": intent,
                   "ticket": {"record_sha256": unit.get("record_sha256"), "state": unit["state"]},
                   "entry": lease["entry"], "commit_ready_seq": entry["commit_ready_seq"],
                   "plan": {"accepted": plan.get("accepted"), "sha256": plan.get("sha256")},
                   "binding": self.gates.integration_binding(unit), "obligation_binding": ob["binding"],
                   "mode": ob["mode"], "legality_digest": self.k.policy_digests()["legality_digest"],
                   "h": integ.get("base"), "m": integ.get("candidate"),
                   "waivers": len(unit.get("waivers") or []), "execution_override": "execution" in arguments}
        entry["attempts"][-1]["pic_request"] = request
        problem, which = self.usable(state, work_id)
        out: dict[str, Any] = {"requested": True, "conditions": CONDITIONS, "mode": ob["mode"],
                               "envelope": which if problem is None else None}
        if problem is not None:
            out["unusable_now"] = {"condition": problem, "why": which}
        if ob["mode"] != V.CHECKS:
            out["note"] = ("verifier mode: PUBLISH_IF_CLEAN is never exercised (the engine never accepts a verifier "
                           "report for you); a clean report goes to VALIDATED for your integration_publish")
        return out

    # ------------------------------------------------------------------ §17's predicate (plan v3 §2.3)

    def predicate(self, state: dict[str, Any], work_id: str, request: dict[str, Any],
                  run: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Each clause in order, as ``{clause, ok, detail}``, stopping at the first that fails."""
        out: list[dict[str, Any]] = []
        clauses = (self._clause_1, self._clause_2, self._clause_3, self._clause_4, self._clause_5, self._clause_6,
                   self._clause_7, self._clause_8)
        for n, clause in zip(CLAUSES, clauses, strict=True):
            detail = clause(state, work_id, request, run)
            out.append({"clause": n, "ok": detail is None, "detail": detail or CLAUSES[n]})
            if detail is not None:
                break
        return out

    def _clause_1(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        # The decision as the one rebuild recomputes it (`Integration._moved_head`): on a copy whose open candidate is
        # set aside, since a prepared or validated candidate is itself what the prepare's guard refuses to replace.
        scratch = copy.deepcopy(state)
        scratch["work"][work_id]["integration"]["status"] = "stale_candidate"
        decision = self.dispatch.decide(scratch, "integrate.prepare", work_id)
        if decision.allowed:
            return None
        return "integrate.prepare is refused now: " + "; ".join(b.message for b in decision.blocking)

    def _clause_2(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        ob = V.obligation(state, work_id, self.k.policy("gates"))
        if ob["binding"] != request["obligation_binding"]:
            return "the obligation binding changed since the request"
        if self.k.policy_digests()["legality_digest"] != request["legality_digest"]:
            return "the legality digest changed since the request"
        return None

    def _clause_3(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        head = self.k.authoritative_commit()
        base = state["work"][work_id]["integration"]["base"]
        return None if head == base else f"the authoritative head is {head}, not H {base}"

    def _clause_4(self, state: dict[str, Any], work_id: str, request: dict[str, Any],
                  run: dict[str, Any] | None) -> str | None:
        # Checks mode only (PIC is never exercised in verifier mode): the committed run's overall result.
        if run is None or run.get("result") != "pass" or run.get("state") != "committed":
            return "the checks-mode validation did not commit a pass"
        return None

    def _clause_5(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        found = G.open_required_findings(state["work"][work_id])
        return None if not found else f"required findings are open: {', '.join(f['id'] for f in found)}"

    def _clause_6(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        unit = state["work"][work_id]
        left = DO.undisposed(DO.unit_items(DO.marks(self.k.policy("gates")), unit), unit)
        return None if not left else f"undisposed requires_disposition items: {', '.join(i['id'] for i in left)}"

    def _clause_7(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        lease = Q.lease_of(state, work_id) or {}
        subjects = {work_id, lease.get("custodian"), lease.get("entry")} - {None}
        high = sorted(a["id"] for a in (state.get("anomalies") or {}).values()
                      if a.get("severity") == DO.HIGH and a.get("subject") in subjects)
        return None if not high else f"open high anomalies: {', '.join(high)}"

    def _clause_8(self, state: dict[str, Any], work_id: str, request: dict[str, Any], run: Any) -> str | None:
        unit = state["work"][work_id]
        integ = unit["integration"]
        if request.get("execution_override"):
            return "the request's stage carried an execution override"
        if len(unit.get("waivers") or []) > int(request.get("waivers") or 0):
            return "a waiver was recorded since the request"
        if integ.get("conflict_paths"):
            return "the candidate needed a conflict resolution"
        ob = V.obligation(state, work_id, self.k.policy("gates"))
        if ob["mode"] != V.CHECKS or ob["mode"] != request.get("mode"):
            return f"the validation resolves to {ob['mode']}, not the checks mode the request was made under"
        return None

    # ------------------------------------------------------------------ the exercise (plan v3 §2.3)

    def on_clean(self, ctx: Any, work_id: str, run: dict[str, Any]) -> str | None:
        """The custodian's clean checks-mode result, in its validation commit: None when no request is on the lease's
        attempt or its envelope is unusable (VALIDATE_ONLY follows, the condition recorded); otherwise ``publishing``
        (begun, one publication reserved), ``rebuilt`` (the head moved: the one rebuild under the same lease, so the
        predicate is evaluated again on the rebuilt candidate) or ``not_exercised`` (the lease released to
        AWAITING_DISPOSITION, the first failed clause recorded)."""
        state = ctx.state
        request = request_of(state, work_id)
        if request is None:
            return None
        unit = self.units.unit(state, work_id)
        integ = unit["integration"]
        lease = Q.lease_of(state, work_id)
        assert lease is not None  # request_of found the attempt through it
        record: dict[str, Any] = {"schema": PIC_SCHEMA, "conditions": CONDITIONS, "request": request,
                                  "custodian": lease["custodian"], "run": run["id"], "h": integ["base"],
                                  "m": integ["candidate"], "at": utc_now(), "rev": ctx.session.revision + 1}
        problem, which = self.usable(state, work_id)
        if problem is not None:
            integ["pic"] = {**record, "exercised": False, "envelope_unusable": {"condition": problem, "why": which}}
            return None
        env = envelope(state)
        assert env is not None
        evidence = self._record(env) or {}
        record.update(envelope=env["id"], task_input_sha256=evidence.get("task_input_sha256"))
        clauses = self.predicate(state, work_id, request, run)
        failed = next((c for c in clauses if not c["ok"]), None)
        if failed is not None and failed["clause"] == 3:
            # The rebuild rule (m5): PIC survives exactly the one rebuild; a second move goes to disposition.
            integ["pic"] = {**record, "exercised": False, "clauses": clauses}
            moved = self.integration._moved_head(ctx, work_id, self.k.authoritative_commit())
            return "rebuilt" if moved["outcome"] == "rebuilt" else "not_exercised"
        if failed is not None:
            integ["pic"] = {**record, "exercised": False, "clauses": clauses}
            self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="pic_not_exercised",
                               detail={"clause": failed["clause"], "why": failed["detail"]})
            ctx.summary = (f"{work_id}: validated clean, but PUBLISH_IF_CLEAN was not exercised (§17 clause "
                           f"{failed['clause']}: {failed['detail']}); the entry waits for the Lead")
            return "not_exercised"
        integ["pic"] = {**record, "exercised": True, "clauses": clauses, "reservation": HELD}
        env["reserved"] += 1
        integ["status"] = "publishing"
        integ["publishing_at"] = utc_now()
        ctx.op = "integrate.publishing"
        ctx.pic_checked = True
        ctx.summary = (f"{work_id} validated clean and publishing {integ['candidate'][:12]} over "
                       f"{integ['base'][:12]} under PUBLISH_IF_CLEAN ({env['id']}, one publication reserved)")
        return "publishing"

    def recheck(self, ctx: Any, work_id: str) -> tuple[str, str] | None:
        """The finish's admission (§2.3, S1: the request, ``envelope_usable`` and the predicate in the same
        transaction): None when they all still hold; else ``("envelope", condition)`` or ``("clause", n)``."""
        state = ctx.state
        request = request_of(state, work_id)
        integ = state["work"][work_id]["integration"]
        if request is None or not (integ.get("pic") or {}).get("exercised"):
            return "envelope", "no_request"
        problem, _which = self.usable(state, work_id, holding=True)
        if problem is not None:
            return "envelope", problem
        failed = next((c for c in self.predicate(state, work_id, request, integ.get("current_validation_run"))
                       if not c["ok"]), None)
        if failed is not None:
            return "clause", str(failed["clause"])
        ctx.pic_checked = True
        return None

    def withdraw(self, ctx: Any, work_id: str, why: tuple[str, str]) -> None:
        """The finish's admission failed before any CAS: nothing was published. The reservation is released, and the
        custodian ends its lease: VALIDATED for an envelope that is no longer usable (as with no request), or
        AWAITING_DISPOSITION for a clause that no longer holds."""
        state = ctx.state
        integ = state["work"][work_id]["integration"]
        self.settle(state, integ, published=False)
        integ["status"] = "validated"
        integ.pop("publishing_at", None)
        integ["pic"]["withdrawn"] = {"kind": why[0], "which": why[1], "at": utc_now()}
        if why[0] == "envelope":
            self._validated(state, work_id, integ)
        else:
            self.queue.release(state, work_id, to="AWAITING_DISPOSITION", result="pic_not_exercised",
                               detail={"clause": int(why[1]), "why": CLAUSES[int(why[1])]})
        ctx.op = "integrate.withdrawn"
        ctx.summary = f"{work_id}: the PUBLISH_IF_CLEAN publish was withdrawn before its CAS ({why[0]} {why[1]})"

    def _validated(self, state: dict[str, Any], work_id: str, integ: dict[str, Any]) -> None:
        validation = integ.get("validation") or {}
        identity = validation.get("identity") or {}
        lease = Q.lease_of(state, work_id) or {}
        self.queue.release(state, work_id, to="VALIDATED", result="validated", validated=Q.validated_record(
            integ, mode=V.CHECKS, custodian=lease.get("custodian") or integ["pic"]["custodian"],
            run=validation.get("run"), check_set=identity.get("check_set"),
            obligation_binding=(identity.get("obligation") or {}).get("binding")))

    def reconcile_unlanded(self, ctx: Any, work_id: str) -> bool:
        """``integrate reconcile`` of a publish begun under PIC whose CAS never landed (the ref is still H): it is never
        completed by the reconcile, because PIC's authority was its custodian's exercise, which has ended. The
        reservation is released and the candidate returns VALIDATED, for the current generation to publish under
        fresh authority (HSD-22, HSD-23). False when the publish was not begun under PIC."""
        state = ctx.state
        integ = state["work"][work_id]["integration"]
        if (integ.get("pic") or {}).get("reservation") != HELD:
            return False
        self.settle(state, integ, published=False)
        integ["status"] = "validated"
        integ.pop("publishing_at", None)
        integ["pic"]["withdrawn"] = {"kind": "reconcile", "which": "cas_not_landed", "at": utc_now()}
        if Q.lease_of(state, work_id) is not None:
            self._validated(state, work_id, integ)
        ctx.op = "integrate.reconcile"
        ctx.summary = (f"{work_id}: the PUBLISH_IF_CLEAN publish never reached its CAS; nothing was published, and the "
                       "candidate is VALIDATED for the Lead's integration_publish")
        return True

    @staticmethod
    def settle(state: dict[str, Any], integ: dict[str, Any], *, published: bool) -> None:
        """Convert a held reservation (n4): ``published`` in the commit that records ``integrated``, released by any
        commit that proves nothing was published. A reservation is settled once; an envelope since superseded keeps
        its own record's count (the PIC record says how it settled)."""
        pic = integ.get("pic") or {}
        if pic.get("reservation") != HELD:
            return
        pic["reservation"] = PUBLISHED if published else RELEASED
        pic["settled_at"] = utc_now()
        env = envelope(state)
        if env is None or env["id"] != pic.get("envelope"):
            return
        env["reserved"] = max(0, env["reserved"] - 1)
        if published:
            env["published"] += 1

    def view(self, state: dict[str, Any]) -> dict[str, Any] | None:
        """The envelope as ``status`` shows it."""
        env = envelope(state)
        if env is None:
            return None
        out = {k: env[k] for k in ("id", "status", "generation", "expires_at", "max_publications", "published",
                                   "reserved")}
        if env.get("ended"):
            out["ended"] = dict(env["ended"])
        problem = None if env["status"] != ACTIVE else (
            "generation" if env["generation"] != int(state["lead"]["generation"])
            else "expiry" if _now() >= _parse(env["expires_at"]) else None)
        if problem:
            out["unusable"] = problem
        return out
