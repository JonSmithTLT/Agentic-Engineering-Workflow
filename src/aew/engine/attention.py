"""The one attention module (A-44 BOY-02, BOY-03; register E101): every item that waits on the operator, or that the
operator should see, with its tier, lane, order and occurrence key from one table.

Its consumers read items from here and classify nothing again: the dashboard's ``/overview`` (contract 0.1.3,
unchanged, its ``attention`` list), ``aew status`` (with the dashboard stopped too, BOY-02.a), and the outage reader's
engine items. Each item's tier comes from its source record's class through :data:`TABLE`, never from any text.

The sources of slice S1:

* **G3 approvals** (BOY-05): the per-host records the G3 client writes (:mod:`aew.g3records`), read only. Nothing
  here connects to G3: only ``request.sock``'s path is checked, to tell "G3 is not on this host" (BOY-05, BOY-Q01).
* **The existing alert events**: units in a state the Lead must act on, contradictions, lost or crashed runs, and a
  notifier whose latest delivery failed.

Nothing here decides, answers or approves (BOY-00): an item names where to answer, from :data:`WHERE`'s closed set of
existing homes, and never links to, launches or pre-selects one (BOY-06). Unknown is never "nothing pending": a source
that cannot be read says so with its read time, and an unreadable record is an item of its own (BOY-04).
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

BLOCKED_ON_YOU, ATTENTION, FYI = "blocked_on_you", "attention", "fyi"
TIERS = (BLOCKED_ON_YOU, ATTENTION, FYI)  # the order: waiting items first, so the overview's six cannot hide them
OWNER, AGENT = "owner", "agent"
LANES = (OWNER, AGENT)  # within a tier, owner items before agent items (BOY-03.b)


@dataclass(frozen=True)
class Row:
    """A source class's place: its tier and lane, and the contract 0.1.3 ``kind`` and ``severity`` it shows as."""

    tier: str
    lane: str
    kind: str
    severity: str


# The one tier table (BOY-03.a). Each source class sits in one row, and each approval state of BOY-05.b in one too.
TABLE: dict[str, Row] = {
    # G3 approvals, by BOY-05.b's state: only a pending one, before expiry, whose live client still reads it, waits
    "g3_approval.waiting": Row(BLOCKED_ON_YOU, OWNER, "decision_required", "high"),
    "g3_approval.unknown": Row(ATTENTION, OWNER, "anomaly", "medium"),
    "g3_approval.client_gone": Row(FYI, OWNER, "anomaly", "info"),
    "g3_approval.decided": Row(FYI, OWNER, "anomaly", "info"),
    "g3_approval.not_found": Row(FYI, OWNER, "anomaly", "info"),
    "g3_approval.expired_unknown": Row(FYI, OWNER, "anomaly", "info"),
    # the existing alert events
    "work.decision_required": Row(ATTENTION, OWNER, "decision_required", "high"),
    "work.required_finding": Row(ATTENTION, OWNER, "required_finding", "medium"),
    "work.blocker": Row(ATTENTION, OWNER, "blocker", "low"),
    "work.interrupted": Row(ATTENTION, OWNER, "anomaly", "medium"),
    "contradiction": Row(ATTENTION, OWNER, "anomaly", "high"),
    "run.observed": Row(ATTENTION, OWNER, "anomaly", "medium"),
    "notifier.failed": Row(ATTENTION, OWNER, "anomaly", "medium"),
}
# A unit's state -> its source class (the states the Lead must act on)
WORK_STATES = {"ESCALATED": "work.decision_required", "REPLAN_REQUIRED": "work.decision_required",
               "REVIEW_FAILED": "work.required_finding", "VERIFICATION_FAILED": "work.required_finding",
               "VERIFICATION_INCONCLUSIVE": "work.required_finding", "BLOCKED": "work.blocker",
               "INTERRUPTED": "work.interrupted"}

# Where to answer: fixed words from BOY-06's closed set of existing homes. ``operator_endpoint`` waits for its command
# name from the surface map, with the steering requests it serves (register E102).
WHERE = {
    "aew_approvals": "Decide in AEW approvals: the desktop notification, or AEW approvals in the applications menu",
    "lead_terminal": "Answer in the Lead's terminal",
    "g3_request": "If you agree, start it with aew g3 request at your terminal",
}

# The approvals source's fixed words (BOY-05.b, BOY-05.d)
NOT_ON_HOST = "G3 is not on this host"
NOTHING_WAITING = ("No approval that AEW started on this host is waiting. AEW approvals lists every approval, from any "
                   "client.")
COVERAGE = ("Approvals that AEW started on this host, from any project. AEW approvals lists every approval, from any "
            "client.")
HELD = "The action stays held until you decide."
NOT_ESTABLISHED = "G3 is not established here: approving admits nothing yet."
CLAIM = "started by the {role} (the client's own claim)"
UNREADABLE = "An approval record on this host cannot be read, so its state is unknown (?)"
DECIDED = {"approved_submitted": "Approved and submitted.", "approved_not_submitted": "Approved, not submitted.",
           "declined": "Declined.", "expired": "Expired."}
DECIDED_READ = {"APPROVED": "Approved; its client is submitting it.", "DECLINED": "Declined.", "EXPIRED": "Expired."}
GONE = "Nothing will submit this. Decline it in AEW approvals, or let it expire at {at}."
LOST = "No longer known to G3. Request it again if still wanted."
EXPIRED_UNKNOWN = "Unknown whether decided. Nothing waits on it."
UNKNOWN = "Its state is unknown (?): G3 last answered at {at}."

_OPAQUE = re.compile(r"[^A-Za-z0-9._-]")


def opaque(prefix: str, value: str) -> str:
    """An item id the dashboard contract's ``OpaqueId`` admits."""
    return prefix + _OPAQUE.sub(".", value)


def item(source: str, ident: str, *, key: str, subject: dict[str, Any], title: str, summary: str | None = None,
         reasons: list[dict[str, Any]] | None = None, since: str | None = None, who: str = "AEW",
         where: str | None = None, record: str, state: str | None = None,
         expires_at: str | None = None) -> dict[str, Any]:
    """One item: its tier, lane, kind and severity from :data:`TABLE`, and nothing classified anywhere else.
    ``since`` is the source's own time, or None when the source has none, never the time of the read (BOY-01)."""
    row = TABLE[source]
    return {"id": ident, "key": key, "source": source, "tier": row.tier, "lane": row.lane, "kind": row.kind,
            "severity": row.severity, "subject": subject, "title": title, "summary": summary,
            "reasons": list(reasons or []), "since": since, "who": who, "where": where, "record": record,
            "state": state, "expires_at": expires_at}


def ordered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tier first, then lane, each source's own order kept within them (BOY-03.b)."""
    return sorted(items, key=lambda i: (TIERS.index(i["tier"]), LANES.index(i["lane"])))


def counted(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The items a count includes: FYI items are in none (BOY-03.b)."""
    return [i for i in items if i["tier"] != FYI]


def _iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clock(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%H:%M:%S UTC")


# ------------------------------------------------------------------------------------------- the existing alert events

def updated_at(unit: dict[str, Any]) -> str | None:
    """A unit's own last change: its last history entry's time, else its creation, else None."""
    history = unit.get("history") or []
    if history and isinstance(history[-1], dict) and history[-1].get("at"):
        return str(history[-1]["at"])
    return str(unit["created_at"]) if unit.get("created_at") else None


def blockers(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """A unit's recorded blockers, each as a ``BLOCKED_BY`` reason."""
    out = []
    for b in unit.get("blocked_by") or []:
        if not isinstance(b, dict):
            continue
        parts = [str(b.get("kind", "blocked"))]
        parts += [f"{k}={v}" for k, v in sorted(b.items()) if k != "kind" and isinstance(v, (str, int))]
        out.append({"code": "BLOCKED_BY", "message": " ".join(parts)})
    return out[:250]


def engine_items(state: dict[str, Any], *, project: dict[str, Any], contradictions: list[str],
                 observe: Callable[[str], str]) -> list[dict[str, Any]]:
    """The existing alert events from committed control state, the contradictions and each run's observed status
    (``observe``: a run id to its status). ``project`` is the subject of a project-wide item."""
    from aew.harness import contract as K

    out = []
    for wid, unit in sorted(state["work"].items()):
        st = unit["state"]
        source = WORK_STATES.get(st)
        if source is None or (st == "BLOCKED" and not unit.get("blocked_by")):
            continue
        reasons = [{"code": "STATE_REASON", "message": str(unit["state_reason"])}] if unit.get("state_reason") else []
        since = updated_at(unit)
        out.append(item(source, f"AT-{wid}", key=f"AT-{wid}|{TABLE[source].kind}|{since}",
                        subject={"id": wid, "kind": "work", "title": str(unit.get("title") or wid)},
                        title=f"{wid} is {st}", summary=unit.get("state_reason"),
                        reasons=(reasons + blockers(unit))[:250], since=since, record=f"control state: {wid}"))
    for n, text in enumerate(contradictions, 1):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        out.append(item("contradiction", f"AT-contradiction-{n}", key=f"AT-contradiction-{n}|anomaly|{digest}",
                        subject=project, title="Contradiction", summary=text,
                        reasons=[{"code": "CONTRADICTION", "message": text}], record="control state"))
    codes = {K.LOST: "RUN_LOST", K.CRASHED: "RUN_CRASHED", K.UNREADABLE: "RUN_UNREADABLE"}
    for inv_id, inv in sorted(state["invocations"].items()):
        for run in inv.get("runs") or []:
            observed = observe(run["run"])
            if observed not in codes:
                continue
            since = str(run["launched_at"]) if run.get("launched_at") else None
            out.append(item("run.observed", f"AT-{run['run']}", key=f"AT-{run['run']}|anomaly|{observed}|{since}",
                            subject={"id": inv_id, "kind": "invocation", "title": None},
                            title=f"run {run['run']} {observed}",
                            summary=f"{inv['role']} run for {inv['work_unit']} is {observed}",
                            reasons=[{"code": codes[observed], "message": f"run {run['run']} of {inv_id}"}],
                            since=since, record=f"run status: {run['run']}"))
    return out


def notifier_items(summary: dict[str, Any] | None, *, project: dict[str, Any]) -> list[dict[str, Any]]:
    """The operator notifier's latest delivery failed (M4-E E7a; operator decision 1): attention on the project, with
    no workflow effect. ``summary`` is the endpoint watcher's (``notify.summary``), a host record shown as data."""
    if not summary or not summary["attention"]:
        return []
    last = summary.get("last_failure") or {}
    parts = []
    if summary["consecutive_failures"]:
        parts.append(f"{summary['consecutive_failures']} delivery failure(s) in a row; the latest: "
                     f"{last.get('event')} ({last.get('reason')}"
                     f"{': ' + last['detail'] if last.get('detail') else ''})")
    if summary.get("pass_error"):
        parts.append(f"the watcher cannot read {', '.join(summary['pass_error']['sources'])}: "
                     f"{summary['pass_error']['error']}")
    text = "; ".join(parts)
    since = str(last["at"]) if last.get("at") else None
    return [item("notifier.failed", "AT-notifier", key=f"AT-notifier|anomaly|{since}", subject=project,
                 title="Operator notification failed", summary=text,
                 reasons=[{"code": "NOTIFY_DELIVERY_FAILED", "message": text}], since=since,
                 record="host record: the notifier's summary")]


# ------------------------------------------------------------------------------------------- G3 approvals (BOY-05)

def stale_read_s() -> float:
    """BOY-14's stale-read bound, the client's own (``g3client.STALE_READ_S``): its request timeout plus two polls."""
    from aew import g3client

    return float(g3client.STALE_READ_S)


def client_alive(client: Any) -> bool:
    """Whether the record's client is still the live process it names: its pid with its start identity, read without
    writing anything (``procs.same_process``)."""
    from aew.harness import procs

    if not isinstance(client, dict) or not isinstance(client.get("pid"), int):
        return False
    start = client.get("start_id")
    return procs.same_process(client["pid"], start) if isinstance(start, str) else procs.pid_alive(client["pid"])


def approval_state(record: dict[str, Any], now: datetime, *, alive: bool) -> tuple[str, str]:
    """BOY-05.b: one record's one truthful state, as ``(source class, its fixed words)``. The rows are tried in order,
    and the first that matches decides: past its expiry with no outcome, nothing waits on it whatever the client's
    liveness (G3 approves nothing after expiry); an outcome is final; then a client gone; then a 404; then no answer, a
    503 or a stale read is unknown; only a pending record read in time by its live client is blocked-on-you."""
    from aew import g3records as R

    expiry = R.parse_time(record["expires_at"])
    outcome, read = record["outcome"], record["state"]
    if outcome is None and expiry is not None and now > expiry:
        return "g3_approval.expired_unknown", EXPIRED_UNKNOWN
    if outcome in DECIDED:
        return "g3_approval.decided", DECIDED[outcome]
    if outcome == "not_found":
        return "g3_approval.not_found", LOST
    if outcome == "unanswered":
        return "g3_approval.expired_unknown", EXPIRED_UNKNOWN
    if not alive or record["exited_at"] is not None:
        return "g3_approval.client_gone", GONE.format(at=_clock(expiry) if expiry else "its expiry")
    if read == R.NOT_FOUND:
        return "g3_approval.not_found", LOST
    read_at = R.parse_time(record["read_at"])
    if read == R.NO_ANSWER or read_at is None or (now - read_at).total_seconds() > stale_read_s():
        answered = R.parse_time(record["g3_answered_at"])
        return "g3_approval.unknown", UNKNOWN.format(at=_iso(answered) if answered else "no time recorded")
    if read == R.PENDING:
        return "g3_approval.waiting", HELD
    return "g3_approval.decided", DECIDED_READ.get(read, EXPIRED_UNKNOWN)


@dataclass(frozen=True)
class Source:
    """A source's own outcome and read time (BOY-04): ``available``, or ``unsupported`` with why; and its line, which
    states what it covers. A source is never a count."""

    name: str
    outcome: str
    read_at: str
    line: str

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "outcome": self.outcome, "read_at": self.read_at, "line": self.line}


def approval_items(now: datetime, *, platform: str | None = None, sock: str | None = None,
                   directory: Path | None = None, alive: Callable[[Any], bool] = client_alive,
                   established: Callable[[], bool] | None = None) -> tuple[list[dict[str, Any]], Source]:
    """The G3 approvals this host's client recorded, and the source's outcome. On Windows, or with no
    ``request.sock`` (``g3client.REQUEST_SOCK``, whose path is only checked, never connected to), the source is
    ``unsupported`` and no record is read. A record stays until its expiry plus G3-06's window (BOY-05.c).
    ``established`` says whether G3 is established for this reader (``g3standing``); while it is not, each item says
    approving admits nothing yet (BOY-05.d)."""
    from aew import g3client
    from aew import g3records as R

    read_at = _iso(now)
    if (platform or sys.platform) == "win32" or not Path(sock or g3client.REQUEST_SOCK).exists():
        return [], Source("g3_approvals", "unsupported", read_at, NOT_ON_HOST)
    out = []
    window = timedelta(seconds=R.window_s())
    for found in R.read_all(directory):
        rec = found.record
        if rec is None:
            out.append(item("g3_approval.unknown", opaque("AT-g3-record-", found.name), key=f"g3-record:{found.name}",
                            subject={"id": opaque("g3-record-", found.name), "kind": "approval", "title": None},
                            title="Approval record unreadable (?)", summary=UNREADABLE,
                            reasons=[{"code": "G3_APPROVAL_UNKNOWN", "message": UNREADABLE}],
                            where="aew_approvals", record=f"host record: g3/requests/{found.name}", state="?"))
            continue
        expiry = R.parse_time(rec["expires_at"])
        if expiry is not None and now > expiry + window:
            continue  # out of view; its client's next write prunes it
        source, words = approval_state(rec, now, alive=alive(rec["client"]))
        out.append(_approval(rec, found.name, source, words))
    if out and established is not None and not established():
        for i in out:
            i["summary"] = f"{i['summary']} {NOT_ESTABLISHED}"
    waiting = any(i["tier"] == BLOCKED_ON_YOU for i in out)
    out.sort(key=lambda i: i["since"] or "")
    return out, Source("g3_approvals", "available", read_at, COVERAGE if waiting else NOTHING_WAITING)


_CODES = {"g3_approval.waiting": "G3_APPROVAL_WAITING", "g3_approval.unknown": "G3_APPROVAL_UNKNOWN",
          "g3_approval.client_gone": "G3_APPROVAL_CLIENT_GONE", "g3_approval.decided": "G3_APPROVAL_DECIDED",
          "g3_approval.not_found": "G3_APPROVAL_NOT_FOUND",
          "g3_approval.expired_unknown": "G3_APPROVAL_EXPIRED_UNKNOWN"}
_WHERE = {"g3_approval.waiting": "aew_approvals", "g3_approval.unknown": "aew_approvals",
          "g3_approval.client_gone": "aew_approvals", "g3_approval.not_found": "g3_request"}


def _approval(rec: dict[str, Any], name: str, source: str, words: str) -> dict[str, Any]:
    """An approval's item: only what the confirmer lists (BOY-05.d) — G3's raw action names, the ref and its
    expiry, the state, the starter's role labelled as the client's claim, and where to decide. No client or agent
    string is shown as prose (G3-03, BOY-07): the names are G3's TEMPLATE ids, the ref is G3's."""
    from aew import g3records as R

    ref = rec["approval_ref"]
    names = ", ".join(rec["actions"]) or "(no action named)"
    expiry = R.parse_time(rec["expires_at"])
    project = rec["project"] or "outside a project"
    marker = " (?)" if source == "g3_approval.unknown" else ""
    summary = (f"{words} Approval {ref}, expires {_clock(expiry) if expiry else '?'}; "
               f"{CLAIM.format(role=rec['starter_role'])}, in {project}.")
    return item(source, opaque("AT-g3-", ref), key=ref,
                subject={"id": opaque("g3-", ref), "kind": "approval", "title": project},
                title=f"G3 approval{marker}: {names}", summary=summary,
                reasons=[{"code": _CODES[source], "message": words}], since=rec["started_at"],
                who=CLAIM.format(role=rec["starter_role"]), where=_WHERE.get(source),
                record=f"host record: g3/requests/{name}", state="?" if marker else words,
                expires_at=rec["expires_at"])


# ------------------------------------------------------------------------------------------- the whole view

def view(state: dict[str, Any], *, project: dict[str, Any], contradictions: list[str],
         observe: Callable[[str], str], notifier: dict[str, Any] | None, now: datetime | None = None,
         host: bool = True, established: Callable[[], bool] | None = None,
         approvals: Callable[..., tuple[list[dict[str, Any]], Source]] | None = None) -> dict[str, Any]:
    """Every item, ordered, and each host source's outcome. ``host=False`` reads committed records only: no notifier
    summary and no approval record (the outage reader's, BOY-05.e)."""
    now = now or datetime.now(UTC)
    items = engine_items(state, project=project, contradictions=contradictions, observe=observe)
    sources: list[Source] = []
    if host:
        found, source = (approvals or approval_items)(now, established=established)
        items = found + items + notifier_items(notifier, project=project)
        sources.append(source)
    return {"items": ordered(items), "sources": [s.as_dict() for s in sources]}


def for_engine(engine: Any, *, contradictions: list[str], now: datetime | None = None) -> dict[str, Any]:
    """:func:`view` for ``aew status``, from the engine with the dashboard stopped (BOY-02.a): the same items the
    overview shows, from the same table."""
    from aew import g3standing
    from aew.errors import AEWError
    from aew.harness import notify, runlog

    state = engine.store.current()

    def established() -> bool:
        try:
            policy = engine.execution_policy()[0]
        except AEWError:
            policy = None
        return g3standing.standing(policy, sweep=False).counts

    meta = engine.manifest["project"]
    return view(state, project={"id": str(meta["id"]), "kind": "project", "title": str(meta["name"])},
                contradictions=contradictions,
                observe=lambda run: runlog.observed_status(runlog.run_dir(engine.aew_root, run))[0],
                notifier=notify.summary(engine.aew_root), now=now, established=established)


def render(view: dict[str, Any], now: datetime | None = None) -> list[str]:
    """``aew status``'s block: each item with its tier and its source's own time, an approval's time left, and where
    to answer; then each host source's outcome, read time and coverage."""
    from aew import g3records as R

    now = now or datetime.now(UTC)
    lines = [f"Waiting on you ({len(counted(view['items']))} counted; FYI items are not)"]
    for i in view["items"]:
        when = f", since {i['since']}" if i["since"] else ""
        expiry = R.parse_time(i.get("expires_at"))
        left = ""
        if expiry is not None and i["tier"] != FYI:
            seconds = max(0, int((expiry - now).total_seconds()))
            left = f", {seconds // 60}m{seconds % 60:02d}s left"
        lines.append(f"  [{i['tier'].replace('_', '-')}] {i['title']}{when}{left}")
        if i["source"].startswith("g3_approval") and i["summary"]:
            lines.append(f"    {i['summary']}")
        if i["where"]:
            lines.append(f"    {WHERE[i['where']]}")
    lines += [f"  {s['name']}: {s['outcome']}, read {s['read_at']}: {s['line']}" for s in view["sources"]]
    return lines
