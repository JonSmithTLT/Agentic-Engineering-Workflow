"""Dispositions and anomalies (M4-E E5b; plan v3 §2.4).

**`requires_disposition`** is a generic, legality-affecting gates policy property (the designer, 2026-10-01):
``gates.requires_disposition: {review_severities: [...], unrequired_verification_results: [...]}``, empty by default so
that nothing changes until a project lists something. It marks a non-required review finding whose severity is listed,
and a verification claim whose result is listed while that result is not already a gate failure (under the current
outcome rules every listed result already is, so this half marks nothing until the designer defines decision D4).
Required findings are unchanged: they are resolved by a later review, never disposed of.

- **The guard.** ``review.ingest`` and ``verify.ingest`` refuse to advance a Ticket past a marked item the Lead has not
  disposed of (``DISPOSITION_REQUIRED``, a gate input in the ingest's own query: :func:`require_disposed`). The
  primitive and the stage share it, so stage/primitive equivalence holds. An ingest that does not advance (a failed
  review, or one with other reviews outstanding) records the report and is not refused.
- **The disposition** is the Lead's judgment (``work.dispose``: ``resolve`` or ``aew work dispose``): ``accept_risk``,
  ``follow_up`` (with the Ticket that follows it up) or ``not_applicable``, with a rationale, by the Lead generation, at
  a revision. Its record is written immutably beside the Ticket (``work/<T>/dispositions/<DP>.yaml``), and a pointer
  to it is the Ticket's hot index while the Ticket is live; archival carries the pointers into the Ticket's bundle,
  which pins each record, exactly as an ended stage intent's (§2.7).

**Anomalies** are recorded existing signals, nothing newly detected (§0). The hot ``anomalies`` key holds only open
ones (ADR-0011: bounded by what is open); disposing of one moves it, with its disposition, to the same cold record,
beside its subject Ticket (or under ``records/dispositions/`` when it concerns the project). The E5b sources:

- ``WORKSPACE_MUTATED`` and ``OBSERVATION_MUTATED`` (high): every such refusal. A refusal inside a Lead transaction is
  recorded by a follow-up commit under the same Lead credential (:meth:`Dispositions.record_refusal`); one met by a
  worker (a reviewer's submission or check) is a signal file under ``.aew/local/anomalies/`` (a worker commits no
  control state), recorded by the next Lead commit (:meth:`Dispositions.finalize`). The Lead takes from a signal file
  only its source and the invocation that was refused, and only for an invocation in flight: the subject, the key and
  the text are the engine's own, derived from that invocation (``_signalled_entry``), and a commit reads a bounded
  number of bounded files. A signal only reduces authority, never grants any.
- a control-state contradiction (``contradictions()``, high) that is live both when a Lead commit starts and as it
  leaves the state (a contradiction the commit itself resolves, such as the policy drift an adoption accepts, is never
  recorded), leaving out the engine's own retried housekeeping, which heals itself. While it is still live it cannot
  be disposed of (``still_live``, which the projection's decision answers too): the Lead removes its cause first.

Anomaly ids are ``ANM-n``: the archive's annotations already use ``AN-n``.

E7 and E8 add their sources. A high anomaly adds no primitive guard and changes no refusal (n6): it stops the steering
loop (E7), fails PIC's clause 7 (E6b), and makes its subject's projected actions ``auto_runnable: false``
(``aew.surface.projection``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from aew.engine.authority import require_lead
from aew.engine.base import V2, TxnContext
from aew.engine.store import Transition
from aew.errors import (
    AEWError,
    DispositionRequired,
    IllegalTransition,
    NotFound,
    ObservationMutated,
    UsageError,
    WorkspaceMutated,
)
from aew.knowledge.records import format_id
from aew.schemas import validate
from aew.util import sha256_bytes, utc_now

if TYPE_CHECKING:
    from aew.engine.base import Kernel

SCHEMA = "aew/disposition/v1"
CHOICES = ("accept_risk", "follow_up", "not_applicable")
POLICY_KEY = "requires_disposition"
HIGH, LOW = "high", "low"
CONTRADICTION = "CONTRADICTION"
# M4-E E7b's sources (plan v3 §2.4): an auto-run step whose committed changes exceed what its primitives declare (the
# steering loop's runtime check, SAE-07), and a harness run its supervisor ended at its hard deadline (A1 §3.2).
SIDE_EFFECT_UNDECLARED = "SIDE_EFFECT_UNDECLARED"
HARD_DEADLINE = "HARD_DEADLINE"
# The sources and their severity (plan v3 §2.4): E5b's, then E7b's; E8 adds its own.
SOURCES = {"WORKSPACE_MUTATED": HIGH, "OBSERVATION_MUTATED": HIGH, CONTRADICTION: HIGH, SIDE_EFFECT_UNDECLARED: HIGH,
           HARD_DEADLINE: LOW}
SIGNALLED = (WorkspaceMutated, ObservationMutated)  # the refusals that are recorded as anomalies
ANOMALY_PREFIX = "ANM"  # not "AN": the archive's annotations use it (PR 182 review, m5)
ANOMALY_ID = re.compile(r"^ANM-[0-9]{4,}$")
SPOOL_REL = "local/anomalies"  # worker-side signals, under .aew (never control state)
MAX_SIGNAL_FILES = 16  # signal files one commit reads; the rest wait for the next (PR 182 review, m3)
MAX_SIGNAL_BYTES = 4096  # a larger file is no signal the engine wrote: dropped unread
MAX_CHANGED = 20  # changed paths kept on an anomaly, each cut to MAX_PATH characters
MAX_PATH = 300
# The engine's own words for a signalled refusal (the Lead's projection never shows a worker's text).
SIGNAL_TEXT = {"WORKSPACE_MUTATED": "{inv} ({role}) changed the workspace it evaluates; its report was refused",
               "OBSERVATION_MUTATED": "{inv} ({role}) changed its read-only observation; its report was refused",
               # The supervisor's deadline stop (M4-E E7b; A1 §3.2): the run was terminated and its credential dropped;
               # no lease was released, nothing advanced and nothing relaunched. Reconcile it as any ended run.
               HARD_DEADLINE: "{inv} ({role}): a run was terminated at its hard deadline; nothing was advanced or "
                              "released, and nothing relaunched"}
RECORDS_DIR = "records/dispositions"
UNIT_KEY = "dispositions"  # the hot index on a live Ticket
MAX_TEXT = 2000


def cold_rel(disposition: str, work_id: str | None) -> str:
    return f"work/{work_id}/dispositions/{disposition}.yaml" if work_id else f"{RECORDS_DIR}/{disposition}.yaml"


# ---------------------------------------------------------------------------------------------- what policy marks


def marks(gates_policy: dict[str, Any] | None) -> tuple[frozenset[str], frozenset[str]]:
    """The review severities and the verification claim results policy marks (both empty by default)."""
    block = (gates_policy or {}).get(POLICY_KEY) or {}
    return (frozenset(block.get("review_severities") or ()), frozenset(block.get("unrequired_verification_results")
                                                                       or ()))


def finding_marked(marked: tuple[frozenset[str], frozenset[str]], finding: dict[str, Any]) -> bool:
    """A non-required finding whose severity policy lists. A required one is resolved, never disposed of."""
    return not finding.get("required") and finding.get("severity") in marked[0]


def report_items(marked: tuple[frozenset[str], frozenset[str]], ev: dict[str, Any], *,
                 advances: bool = True) -> list[dict[str, Any]]:
    """The items of report ``ev`` policy marks, each with the id a disposition names: ``<evidence>#<finding>`` (the id
    the ingest gives the finding on the Ticket) or ``<evidence>#claim-<n>``. A claim result that is already a gate
    failure is not marked (``advances``: the report's outcome advances the Ticket; under the current outcome rules a
    report with a claim that did not pass never does, so a listed result marks nothing until that changes)."""
    out: list[dict[str, Any]] = []
    if ev.get("kind") == "review":
        for f in (ev.get("review") or {}).get("findings") or []:
            if finding_marked(marked, f):
                out.append({"id": f"{ev['id']}#{f['id']}", "kind": "finding", "evidence": ev["id"],
                            "severity": f.get("severity"), "summary": f.get("summary")})
    elif ev.get("kind") == "verification" and advances:
        for n, c in enumerate((ev.get("verification") or {}).get("claims") or [], start=1):
            if c.get("result") in marked[1]:
                out.append({"id": f"{ev['id']}#claim-{n}", "kind": "claim", "evidence": ev["id"],
                            "result": c.get("result"), "summary": c.get("claim")})
    return out


def report_advances(ev: dict[str, Any]) -> bool:
    """Whether a report's own result lets its ingest advance the Ticket (a verification that passed); a review's
    findings are marked whatever its outcome, and the ingest refuses only when it advances."""
    return ev.get("kind") != "verification" or ev.get("result") == "pass"


def unit_items(marked: tuple[frozenset[str], frozenset[str]], unit: dict[str, Any]) -> list[dict[str, Any]]:
    """The marked findings recorded on ``unit``: noted (neither resolved nor open-required) and not waived."""
    waived = {w.get("finding") for w in unit.get("waivers") or []}
    return [{"id": f["id"], "kind": "finding", "evidence": f.get("source"), "severity": f.get("severity"),
             "summary": f.get("summary")}
            for f in unit.get("findings") or []
            if f.get("status") == "noted" and f["id"] not in waived and finding_marked(marked, f)]


# The states in which an ingest could still be refused on a marked item (PR 182 review, n6): a finding before the
# review that advances the Ticket past it (a later cycle back to RUNNING gates it again), a claim while its
# verification is pending (Ticket scope) or its candidate is prepared (integration scope).
FINDING_GATED = frozenset({"ASSIGNED", "RUNNING", "REVIEW_PENDING", "REVIEW_FAILED"})
CLAIM_GATED = frozenset({"VERIFY_PENDING", "COMMIT_READY"})


def still_gated(unit: dict[str, Any] | None, item: dict[str, Any]) -> bool:
    """Whether ``item`` can still hold an ingest of ``unit`` (a hot unit, in a state before the advance it gates)."""
    if not unit:
        return False
    return unit.get("state") in (FINDING_GATED if item["kind"] == "finding" else CLAIM_GATED)


def disposed(unit: dict[str, Any] | None) -> set[str]:
    return {p["subject"] for p in (unit or {}).get(UNIT_KEY) or []}


def undisposed(items: list[dict[str, Any]], unit: dict[str, Any] | None) -> list[dict[str, Any]]:
    done = disposed(unit)
    return [i for i in items if i["id"] not in done]


def require_disposed(items: list[dict[str, Any]], unit: dict[str, Any], work_id: str, to: str) -> None:
    """The ingest's gate input (§2.4): refuse to advance ``work_id`` to ``to`` past an undisposed marked item."""
    left = undisposed(items, unit)
    if left:
        raise DispositionRequired(
            f"{work_id} cannot advance to {to}: policy marks {', '.join(i['id'] for i in left)} requires_disposition, "
            "and the Lead has not disposed of it. Dispose of each (`resolve` with accept_risk, follow_up or "
            "not_applicable, or `aew work dispose`), then ingest again", work_id=work_id, to=to,
            items=[{k: i.get(k) for k in ("id", "kind", "evidence", "severity", "result")} for i in left])


# ---------------------------------------------------------------------------------------------- worker-side signals


def signal(aew_root: Path, exc: AEWError, work_id: str | None) -> None:
    """Record a refusal met outside a Lead transaction as a signal file the next Lead commit records (a worker commits
    no control state): its source and the refused invocation, nothing else the Lead would take on trust. Best effort:
    it never changes the refusal."""
    signal_source(aew_root, exc.code, str(exc.details.get("invocation") or ""))


def signal_source(aew_root: Path, source: str, invocation: str) -> None:
    """A worker-side signal of ``source`` about ``invocation`` (:func:`signal`; the supervisor's hard deadline, M4-E
    E7b). Best effort: a signal only reduces authority, so one that cannot be written is lost, never an error."""
    try:
        if not invocation:
            return
        spool = aew_root / SPOOL_REL
        spool.mkdir(parents=True, exist_ok=True)
        name = sha256_bytes(f"{source}:{invocation}".encode())[:32]
        path = spool / f"{name}.json"
        if not path.exists():
            path.write_text(json.dumps({"source": source, "invocation": invocation}), encoding="utf-8")
    except (OSError, ValueError, TypeError):
        pass


@contextmanager
def signalled(aew_root: Path, work_id: str | None) -> Iterator[None]:
    """Around a worker's check that can refuse with a recorded signal: the refusal is signalled, then propagates."""
    try:
        yield
    except SIGNALLED as exc:
        signal(aew_root, exc, work_id)
        raise


def _bounded_details(details: dict[str, Any]) -> dict[str, Any]:
    """The details an anomaly keeps: the refused invocation or unit, and a bounded list of changed paths."""
    out: dict[str, Any] = {}
    for k in ("invocation", "work_id"):
        if isinstance(details.get(k), str):
            out[k] = details[k][:64]
    changed = details.get("changed")
    if isinstance(changed, list):
        out["changed"] = [str(c)[:MAX_PATH] for c in changed[:MAX_CHANGED]]
    return out


def anomaly_key(source: str, subject: str | None, details: dict[str, Any]) -> str:
    """The key an open anomaly is deduplicated by, derived by the engine from what it records: its source, its subject
    and the invocation or unit refused (never a key a signal file states: PR 182 review, m2)."""
    return sha256_bytes(json.dumps([source, subject, details.get("invocation"), details.get("work_id")],
                                   sort_keys=True).encode("utf-8"))[:32]


def _from_refusal(exc: AEWError, work_id: str | None) -> dict[str, Any]:
    details = _bounded_details(exc.details)
    detail = f"{exc.code}: {exc.message}"[:MAX_TEXT]
    return {"source": exc.code, "subject": work_id, "detail": detail, "details": details,
            "key": anomaly_key(exc.code, work_id, details)}


# ---------------------------------------------------------------------------------------------- the collaborator


class Dispositions:
    """The Lead's dispositions, and the anomaly record (module docstring)."""

    def __init__(self, k: Kernel, *, gates: Any, archive: Any, views: Any) -> None:
        self.k = k
        self.gates = gates
        self.archive = archive
        self.views = views

    # ------------------------------------------------------------------ recording anomalies

    def open(self, state: dict[str, Any], *, source: str, subject: str | None, detail: str, key: str,
             details: dict[str, Any] | None = None, rev: int) -> str | None:
        """Open an anomaly on ``state`` unless one with the same key is open already; its id, or None."""
        if state.get("schema") != V2:  # a v2-only key: a v1 project records none
            return None
        open_ = state.get("anomalies") or {}
        if any(a["key"] == key for a in open_.values()):
            return None
        state["counters"]["anomaly"] = state["counters"].get("anomaly", 0) + 1
        an = format_id(ANOMALY_PREFIX, state["counters"]["anomaly"])
        state.setdefault("anomalies", {})[an] = {
            "id": an, "source": source, "severity": SOURCES.get(source, HIGH), "subject": subject,
            "detail": detail[:MAX_TEXT], "details": details or {}, "key": key, "opened_at": utc_now(), "rev": rev,
            "disposition": None}
        return an

    def _subject_of(self, state: dict[str, Any], details: dict[str, Any], fallback: str | None) -> str | None:
        inv = state["invocations"].get(str(details.get("invocation") or "")) or {}
        wid = details.get("work_id") or inv.get("work_unit") or fallback
        return wid if wid in state["work"] else None

    def record_refusal(self, token: str, exc: AEWError) -> None:
        """A Lead transaction was refused with a recorded signal (``SIGNALLED``): record it as an anomaly in a commit
        of its own, under the same credential and without an expected revision (it records what was refused, like a
        run request), then let the refusal propagate unchanged (its code, message and details are the guard's, as the
        query answered them). The refusal carries what was recorded beside them (``recorded``: the anomaly and the
        revision it moved to), which the CLI reports so its caller re-reads first (PR 182 review, n5). A credential that
        no longer holds the seat records nothing; nothing here ever masks the refusal."""
        if not isinstance(exc, SIGNALLED):
            return
        try:
            with self.k.store.session() as s:
                actor = require_lead(s.state, token, archived=self.archive.archived_credential)
                state = s.state
                entry = _from_refusal(exc, self._subject_of(state, exc.details, None))
                an = self.open(state, source=entry["source"], subject=entry["subject"], detail=entry["detail"],
                               key=entry["key"], details=entry["details"], rev=s.revision + 1)
                if an is not None:
                    rev = s.commit(Transition(op="anomaly.record", actor=actor,
                                              summary=f"anomaly {an} ({entry['source']}) recorded from a refused call",
                                              refs=[an]))
                    exc.recorded = {"anomaly": an, "revision": rev,
                                    "message": f"the refusal was recorded as anomaly {an}: the control revision is "
                                               f"now {rev}; read it again before your next call"}
        except (AEWError, OSError):
            pass

    def record_violation(self, *, token: str, subject: str | None, detail: str,
                         details: dict[str, Any] | None = None) -> dict[str, Any]:
        """The steering loop's runtime declaration check (M4-E E7b; SAE-07; plan v3 §2.4): an auto-run step committed
        a change its primitives do not declare. Recorded as a high anomaly in a commit of its own under the Lead
        credential the loop acts for, without an expected revision (it records what happened, like a refused call's
        anomaly). It only reduces authority: a high anomaly stops the loop in every mode and holds its subject's
        actions back from auto-running. One already open for the subject is not opened again."""
        bounded = _bounded_details(details or {})
        with self.k.store.session() as s:
            actor = require_lead(s.state, token, archived=self.archive.archived_credential)
            wid = subject if subject in s.state["work"] else None
            key = anomaly_key(SIDE_EFFECT_UNDECLARED, wid, bounded)
            an = self.open(s.state, source=SIDE_EFFECT_UNDECLARED, subject=wid,
                           detail=f"{SIDE_EFFECT_UNDECLARED}: {detail}", key=key, details=bounded, rev=s.revision + 1)
            if an is None:
                return {"anomaly": None, "revision": s.revision}
            rev = s.commit(Transition(op="anomaly.record", actor=actor,
                                      summary=f"anomaly {an} ({SIDE_EFFECT_UNDECLARED}) recorded by the steering loop",
                                      refs=[an]))
        return {"anomaly": an, "revision": rev}

    def finalize(self, ctx: TxnContext) -> None:
        """Every Lead commit records what is signalled and not recorded yet: at most ``MAX_SIGNAL_FILES`` worker-side
        signal files (each validated, ``_signalled_entry``; the rest wait for the next commit), and the contradictions
        live both in the committed state it starts from and in the state it leaves (``live_contradictions``). The
        signal files it read go after the commit."""
        state = ctx.state
        if state.get("schema") != V2:
            return
        rev = ctx.session.revision + 1
        spool = self.k.aew_root / SPOOL_REL
        folded: list[Path] = []
        for path in sorted(spool.glob("*.json"))[:MAX_SIGNAL_FILES] if spool.is_dir() else []:
            folded.append(path)
            entry = self._signalled_entry(state, path)
            if entry is not None:
                self.open(state, **entry, rev=rev)
        for text in self.live_contradictions(ctx.session.committed_view(), state):
            self.open(state, source=CONTRADICTION, subject=_contradiction_subject(state, text), detail=text,
                      key=anomaly_key(CONTRADICTION, None, {"work_id": text}), rev=rev)
        if folded:
            ctx.after_commit.append(lambda: _unlink(folded))

    def _signalled_entry(self, state: dict[str, Any], path: Path) -> dict[str, Any] | None:
        """What the Lead records of one signal file, or None: the file is small and well formed, names a signalled
        source and an invocation in flight; the subject, key and text are derived from that invocation by the engine,
        never taken from the file."""
        try:
            if path.stat().st_size > MAX_SIGNAL_BYTES:
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
            source, invocation = entry["source"], entry["invocation"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        inv = state["invocations"].get(invocation) if isinstance(invocation, str) else None
        if source not in SIGNAL_TEXT or inv is None or inv.get("work_unit") not in state["work"]:
            return None
        subject = inv["work_unit"]
        details = {"invocation": invocation}
        return {"source": source, "subject": subject, "details": details,
                "detail": f"{source}: " + SIGNAL_TEXT[source].format(inv=invocation, role=inv.get("role")),
                "key": anomaly_key(source, subject, details)}

    def live_contradictions(self, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        """The contradictions to record: live in the committed state a transaction starts from and still live in the
        state it leaves (one it resolves, such as the drift an adoption accepts, is not: PR 182 review, M1), without the
        engine's own retried housekeeping (m1). Read from ``before`` first, so a record the transaction rewrites, whose
        new bytes are not on disk yet, is never taken for one modified outside AEW."""
        first = self.views.contradictions(before, housekeeping=False)
        if not first:
            return []
        still = set(self.views.contradictions(after, housekeeping=False))
        return [text for text in first if text in still]

    def disposal_refusal(self, state: dict[str, Any], an: str) -> IllegalTransition | None:
        """Why open anomaly ``an`` cannot be disposed of now, or None: one query for the projection's decision and the
        disposal's own refusal (PR 182 review, m4). A contradiction cannot be while it is still live."""
        anomaly = (state.get("anomalies") or {}).get(an) or {}
        if anomaly.get("source") == CONTRADICTION and anomaly.get("detail") in self.views.contradictions(state):
            return IllegalTransition(f"{an} is a contradiction that is still live ({anomaly['detail']}): remove its "
                                     "cause first, then dispose of it", reason="still_live", anomaly=an)
        return None

    # ------------------------------------------------------------------ the Lead's disposition

    def dispose(self, *, token: str, expect_rev: int, subject: str, choice: str, rationale: str,
                follow_up: str | None = None) -> dict[str, Any]:
        """Dispose of a marked finding or claim, or an open anomaly: one Lead judgment, one commit."""
        if choice not in CHOICES:
            raise UsageError(f"a disposition is one of {', '.join(CHOICES)}", allowed=list(CHOICES))
        if not (rationale and rationale.strip()):
            raise UsageError("a disposition needs a rationale")
        if (choice == "follow_up") != bool(follow_up):
            raise UsageError("follow_up names the Ticket that follows it up; only that choice takes one")
        with self.k.lead_txn(token, expect_rev, "work.dispose") as ctx:
            state = ctx.state
            anomaly: dict[str, Any] | None = None
            evidence: str | None = None
            if ANOMALY_ID.match(subject):
                anomaly = self._anomaly(state, subject)
                kind, wid = "anomaly", anomaly["subject"]
            else:
                kind, wid, evidence = self._item(state, subject)
            if follow_up is not None:
                self._follow_up(state, follow_up, wid)
            rev = ctx.session.revision + 1
            state["counters"]["disposition"] = state["counters"].get("disposition", 0) + 1
            dp = format_id("DP", state["counters"]["disposition"])
            at = utc_now()
            decided = {"choice": choice, "follow_up": follow_up, "rationale": rationale.strip()[:MAX_TEXT],
                       "generation": state["lead"]["generation"], "rev": rev, "at": at}
            record = {"schema": SCHEMA, "id": dp, "subject": {"id": subject, "kind": kind, "evidence": evidence},
                      "work_unit": wid, **decided, "by": dict(ctx.actor),
                      "anomaly": {**anomaly, "disposition": {"id": dp, **decided}} if anomaly else None}
            validate("disposition", record, source=f"disposition {dp}")
            if anomaly is not None:
                del state["anomalies"][subject]
                if not state["anomalies"]:
                    del state["anomalies"]
            self._write(ctx, record, wid)
            ctx.summary = f"{subject} disposed of: {choice} ({dp})" + (f", followed up by {follow_up}"
                                                                        if follow_up else "")
            ctx.refs.append(dp)
        return {"ok": True, "disposition": dp, "subject": subject, "kind": kind, "work_id": wid, "choice": choice,
                "revision": rev}

    def _anomaly(self, state: dict[str, Any], an: str) -> dict[str, Any]:
        anomaly = (state.get("anomalies") or {}).get(an)
        if anomaly is None:
            raise NotFound(f"no open anomaly {an}: the projection's anomalies list the open ones", anomaly=an)
        refused = self.disposal_refusal(state, an)
        if refused is not None:
            raise refused
        return dict(anomaly)

    def _item(self, state: dict[str, Any], subject: str) -> tuple[str, str, str]:
        """The marked finding or claim ``subject`` names: its kind, its Ticket and its report."""
        evidence, sep, local = subject.partition("#")
        if not sep or not local:
            raise UsageError(f"{subject!r} names no finding, claim or anomaly: a finding is <evidence>#<finding>, a "
                             "claim <evidence>#claim-<n>, an anomaly ANM-<n>")
        owners = [i for i in state["invocations"] if evidence.startswith(f"{i}-")]
        if not owners:
            raise NotFound(f"no report {evidence} of work in flight", evidence=evidence)
        wid = state["invocations"][max(owners, key=len)]["work_unit"]
        unit = state["work"].get(wid)
        if unit is None:
            raise IllegalTransition(f"{wid} is no longer in flight: its findings are history", work_id=wid)
        ev = self.gates.find_evidence(wid, evidence)
        found = next((i for i in report_items(marks(self.k.policy("gates")), ev, advances=report_advances(ev))
                      if i["id"] == subject), None)
        if found is None:
            known = subject in {f"{ev['id']}#{f['id']}" for f in (ev.get("review") or {}).get("findings") or []} or (
                local.startswith("claim-") and local[6:].isdigit()
                and 0 < int(local[6:]) <= len((ev.get("verification") or {}).get("claims") or []))
            if not known:
                raise NotFound(f"{evidence} has no finding or claim {local}", subject=subject)
            raise IllegalTransition(f"policy does not mark {subject} requires_disposition: only a marked item is "
                                    "disposed of (a required finding is resolved by a later review)",
                                    reason="not_marked", subject=subject)
        if subject in disposed(unit):
            raise IllegalTransition(f"{subject} is disposed of already", reason="already_disposed", subject=subject)
        return found["kind"], wid, evidence

    def _follow_up(self, state: dict[str, Any], follow_up: str, wid: str | None) -> None:
        """A follow-up is another Ticket that is still to be done: in flight, and not finished or cancelled (PR 182
        review, n3)."""
        from aew.engine import transitions

        if follow_up == wid:
            raise IllegalTransition(f"{follow_up} is the subject's own Ticket: a follow-up is another Ticket",
                                    reason="follow_up_is_subject")
        unit = state["work"].get(follow_up)
        if unit is None:
            raise NotFound(f"no Ticket {follow_up} in flight to follow it up (a finished one cannot)",
                           work_id=follow_up)
        if unit["kind"] != "ticket" or unit["state"] in transitions.TERMINAL:
            raise IllegalTransition(f"{follow_up} is a {unit['kind']} in state {unit['state']}: a follow-up is a "
                                    "Ticket still to be done", reason="follow_up_not_open", work_id=follow_up)

    def _write(self, ctx: TxnContext, record: dict[str, Any], wid: str | None) -> None:
        """The record, immutable, beside its live Ticket with a pointer on it; beside an archived one with an
        annotation; or under ``records/`` for the project (§2.7, as an ended stage intent)."""
        state = ctx.state
        unit = state["work"].get(wid) if wid else None
        archived = wid is not None and unit is None and self.archive.bundle(state, wid) is not None
        rel = cold_rel(record["id"], wid if (unit is not None or archived) else None)
        text = yaml.safe_dump(record, sort_keys=False, allow_unicode=True)
        ctx.session.write(rel, text, immutable=True)
        sha = sha256_bytes(text.encode("utf-8"))
        subject = record["subject"]["id"]
        if unit is not None:
            unit.setdefault(UNIT_KEY, []).append({"id": record["id"], "subject": subject,
                                                  "kind": record["subject"]["kind"], "choice": record["choice"],
                                                  "path": rel, "sha256": sha, "rev": record["rev"]})
        elif archived:  # linked by its id and, for an anomaly, by the anomaly's (m5)
            for obj in dict.fromkeys((record["id"], subject if record["anomaly"] else record["id"])):
                self.archive.annotate(ctx, wid, "disposition", obj, note=f"{rel} sha256:{sha}")
        elif record["anomaly"] is not None:  # the project's: the same record under the anomaly's own id too (m5)
            ctx.session.write(cold_rel(subject, None), text, immutable=True)
        ctx.refs.append(rel)

    # ------------------------------------------------------------------ reads

    def read(self, state: dict[str, Any], ref: str) -> dict[str, Any]:
        """A disposition record by its id or its subject (an anomaly's id once disposed of), found without scanning
        (TIS-35): a live Ticket's pointer, an archived Ticket's bundle or annotation, or the project's records."""
        for unit in state["work"].values():  # bounded by live work
            for p in unit.get(UNIT_KEY) or []:
                if ref in (p["id"], p["subject"]):
                    return self._load(p["path"], p["sha256"])
        bundle = self.archive.bundle_holding(state, UNIT_KEY, ref)
        if bundle is not None:
            [p] = [p for p in bundle["unit"].get(UNIT_KEY) or [] if ref in (p["id"], p["subject"])]
            return self._load(p["path"], p["sha256"])
        notes = self.archive.index(state).linked("disposition", ref) if "cold" in state else []
        if notes:
            rel, _, sha = str(self.archive.record(notes[-1])["note"]).partition(" sha256:")
            return self._load(rel, sha)
        if (self.k.aew_root / RECORDS_DIR / f"{ref}.yaml").is_file():
            return self._load(f"{RECORDS_DIR}/{ref}.yaml", None)
        raise NotFound(f"no disposition {ref}", disposition=ref)

    def _load(self, rel: str, sha: str | None) -> dict[str, Any]:
        from aew.errors import IntegrityError
        from aew.util import load_yaml

        raw = (self.k.aew_root / rel).read_bytes()
        if sha is not None and sha256_bytes(raw) != sha:
            raise IntegrityError(f"the disposition record {rel} does not match its recorded hash", path=rel)
        doc = load_yaml(raw.decode("utf-8"), source=str(self.k.aew_root / rel))
        validate("disposition", doc, source=rel)
        return doc


def _unlink(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _contradiction_subject(state: dict[str, Any], text: str) -> str | None:
    """The unit a contradiction names first (``T-0001: ...``, or an invocation's unit), else the project (None)."""
    head = text.split(":", 1)[0].strip()
    if head in state["work"]:
        return head
    inv = state["invocations"].get(head) or {}
    return inv.get("work_unit") if inv.get("work_unit") in state["work"] else None
