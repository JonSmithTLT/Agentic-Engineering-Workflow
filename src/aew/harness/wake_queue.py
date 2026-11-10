"""The Lead's wake queue (steering design r4 §1, §2, §5; steering PR 2): how a run's news reaches an idle Lead.

The Lead ends its turn after a dispatch, and the Lead broker posts a **wake** into its session on a real event. This
module owns everything about that except the post itself, which is a harness's (:class:`Poster`).

- **Durable.** ``local/lead-wakes.json`` holds the one outstanding wake and each watched run's mark. It is written
  before a post, so a broker that starts again neither loses a wake nor posts one twice: a wake recorded as ``posting``
  is first looked for in the session (:meth:`Poster.landed`), and posted only if it is not there.
- **At most one undelivered wake.** A trigger that arrives while a wake is ``pending`` is merged into it, so a burst of
  events costs one turn. While a wake is ``posted`` and not yet delivered, nothing new is gathered: the triggers stay in
  the runs' digests until it lands.
- **No stale wakes.** A wake is checked when it is gathered and again immediately before the post, because input the
  harness has admitted can't be withdrawn. ``progress.holds`` is the rule for what a digest detects; this module adds
  the rest: a ``quiet`` wake gives way to any other wake for that run, and a ``run_ended`` wake to a later attempt of
  the same Ticket and role. What fails is dropped, and named in the next wake's ``since_last_wake``.
- **An ended run is told once.** Its invocation stays active until the Lead accepts or cancels it, so its mark stays
  too, recording that the end was told (``ended_told``), and goes once the run is no longer its invocation's live one.
  An end the Lead already has is no wake: a store writer's wait returned it (``runlog.end_returned``; a relayed read,
  a non-writer, records nothing), or the Lead itself closed the invocation.
  A run that reads as ended and then goes on, as a stalled heartbeat does, is watched again.
- **The broker's own mark.** Each run's mark is the newest trigger the Lead has been shown by a wake or by a wait
  (``runlog.read_returned``: a post moves that mark too, so neither repeats the other), with the absolute counts
  ``since_last_wake`` is computed from. ``told_outside`` settles what the digest alone cannot: a path reverted and then
  written outside the scope again wakes the Lead again (steering PR 1's stated limit).
- **`quiet` is the backstop.** A live run with no wake for ``quiet_s`` wakes the Lead, and the digest shows whether it
  still moves. A wake of any kind for that run restarts its clock.

**Text in a wake grants nothing.** The header says it is not the operator, and vouches only for AEW's own text. What a
wake quotes (a command, a file name, the worker's last message) sits in the JSON, where the digest frames it as data,
and the per-run lines hold only AEW's own values.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, Protocol

from aew.harness import contract as K
from aew.harness import progress as P
from aew.harness import runlog
from aew.util import atomic_write

WAKES_REL = "local/lead-wakes.json"
SERVING_REL = "local/lead-wakes.serving"  # the generation whose broker posts wakes (the Lead's fallback reads it)
SCHEMA = "aew/lead-wakes/v1"
HEADER = "AEW wake (not the operator)"
PENDING, POSTING, POSTED = "pending", "posting", "posted"
# What a harness says of a wake it was given.
WAITING, DELIVERED, UNKNOWN = "waiting", "delivered", "unknown"
COUNT_KEYS = ("steps", "files", "commands", "tests")
OFF_SWITCH = '`lead.push_wake: "off"` in the execution policy'


class Poster(Protocol):
    """A harness's way into the session the operator talks to (the `push_wake` feature's capabilities)."""

    def busy(self) -> bool:
        """Whether a turn is running in the session: a wake is held until it is not."""
        ...

    def post(self, wake_id: str, text: str) -> str:
        """Admit the wake as input that starts the session's next turn, and say which session it went to."""
        ...

    def landed(self, wake_id: str) -> str:
        """``waiting`` (admitted, its turn has not started), ``delivered``, or ``unknown`` (this session does not know
        it: it was never admitted, or the Lead has resumed in a new session)."""
        ...

    def new_id(self) -> str:
        """A wake's id, in the form the harness's input takes."""
        ...


class Watched(NamedTuple):
    """A run the queue watches: the live run of an active invocation."""

    run: str
    work_unit: Any
    role: Any
    launched_at: Any


def live_runs(state: Mapping[str, Any]) -> list[Watched]:
    """The run each active invocation is on, from the control state."""
    out: list[Watched] = []
    for inv in (state.get("invocations") or {}).values():
        runs = inv.get("runs") or []
        if inv.get("status") == "active" and runs:
            last = runs[-1]
            out.append(Watched(last["run"], inv.get("work_unit"), inv.get("role"), last.get("launched_at")))
    return out


def mark_serving(aew_root: Path, generation: int) -> None:
    """This generation's broker posts wakes. Liveness is the broker's record: a crash leaves this file, and the record
    says the broker is gone."""
    path = Path(aew_root) / SERVING_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, str(int(generation)))


def clear_serving(aew_root: Path, generation: int) -> None:
    """This generation's broker no longer posts. A later generation's mark is that broker's, and stays."""
    if serving(aew_root) == generation:
        (Path(aew_root) / SERVING_REL).unlink(missing_ok=True)


def serving(aew_root: Path) -> int | None:
    """The generation whose broker posts wakes, or None."""
    try:
        return int((Path(aew_root) / SERVING_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def broker_posts(aew_root: Path, generation: int) -> bool:
    """Whether this generation's broker is live and posts wakes: its mark, and its liveness record's verdict."""
    from aew.harness import broker_liveness
    from aew.harness.lead_broker import POLL_S

    record = broker_liveness.read(aew_root)
    return (serving(aew_root) == generation and record is not None and record.get("generation") == generation
            and broker_liveness.judge(record, generation=generation, poll_s=POLL_S) is None)


def some_broker_posts(aew_root: Path) -> bool:
    """Whether the generation that marked itself is live and posts wakes, from files alone: a wait's own results read no
    state, since the broker's wait calls that code on every observation."""
    generation = serving(aew_root)
    return generation is not None and broker_posts(aew_root, generation)


def _empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "wake": None, "marks": {}, "folded": {}, "last_posted": None, "last_delivered": None,
            "last_failure": None, "dropped": 0}


def read(aew_root: Path) -> dict[str, Any] | None:
    """The queue's file, or None: missing, unreadable, or not this module's. The queue then starts empty: the runs'
    returned marks stop it repeating what the Lead has seen, and the worst case is one more wake."""
    try:
        doc = json.loads((Path(aew_root) / WAKES_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return None
    return {**_empty(), **doc}


def status(aew_root: Path, *, generation: int | None = None, off: bool = False) -> dict[str, Any] | None:
    """What the operator's status line shows (steering design §1), or None when no wake was ever recorded: the
    outstanding wake, the last posted and the last delivered, the runs being watched, and whether the broker posts
    wakes now (for ``generation``, the current Lead's). With wakes ``off`` nothing runs this queue, so what it last held
    is stale: only that they are off."""
    doc = read(aew_root)
    if doc is None:
        return None
    if off:
        return {"off": True}
    wake = doc["wake"]
    return {"outstanding": None if wake is None else {k: wake.get(k) for k in ("id", "phase", "why")},
            "last_posted": doc["last_posted"], "last_delivered": doc["last_delivered"],
            "last_failure": doc["last_failure"], "dropped": doc["dropped"],
            "watching": sorted(run for run, mark in doc["marks"].items() if not mark.get("ended_told")),
            "broker_posting": generation is not None and broker_posts(aew_root, generation)}


def render(status_: Mapping[str, Any]) -> list[str]:
    """The status line, as text: one for the session, and one more for a wake still outstanding, so a wake that never
    lands is visible."""
    if status_.get("off"):
        return [f"Lead wakes: off, by {OFF_SWITCH}"]
    last = status_.get("last_delivered") or status_.get("last_posted")
    said = "none posted yet"
    if last:
        said = (f"last {'delivered' if status_.get('last_delivered') else 'posted'} {last['id']} at {_when(last['at'])}"
                + (f" to session {last['session']}" if last.get("session") else ""))
    watching = status_.get("watching") or []
    posting = f"the broker posts them ({OFF_SWITCH} stops them)" if status_.get("broker_posting") else (
        f"{K.NO_BROKER} them")
    lines = [f"Lead wakes: watching {', '.join(watching) or 'no run'}; {said}; {posting}"]
    wake = status_.get("outstanding")
    if wake:
        lines.append(f"  ! outstanding wake {wake['id']}: {wake['phase']} ({', '.join(wake.get('why') or [])})")
    failure = status_.get("last_failure")
    if failure:
        lines.append(f"  ! the last pass failed: {failure['why']}")
    return lines


def _when(at: Any) -> str:
    """A record's time as `aew status` shows times."""
    return datetime.fromtimestamp(float(at), UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def wake_text(wake_id: str, shape: Mapping[str, Any]) -> str:
    """The wake as the Lead's session receives it: the fixed header, the JSON, and one line per run of AEW's own
    values (steering design §2). What it quotes is scrubbed as a wait's result is, here, the one way out of this
    module."""
    clean = K.scrub({"id": wake_id, **shape})
    lines = [HEADER, json.dumps(clean, sort_keys=True, ensure_ascii=False)]
    for run, digest in sorted((clean.get("runs") or {}).items()):
        digest = digest or {}
        lines.append(f"- {run}: {digest.get('state', P.UNKNOWN)}, {digest.get('steps', P.UNKNOWN)} steps")
    return "\n".join(lines)


class WakeQueue:
    """One Lead broker's wake queue. :meth:`tick` is one pass, and the broker calls it from one thread."""

    def __init__(self, aew_root: Path, *, poster: Poster, state: Callable[[], Mapping[str, Any]],
                 quiet_s: Callable[[], int], clock: Callable[[], float],
                 new_id: Callable[[], str] = lambda: f"wake_{uuid.uuid4().hex}") -> None:
        self.aew_root = Path(aew_root)
        self.poster, self.state, self.quiet_s, self.clock, self.new_id = poster, state, quiet_s, clock, new_id
        self.doc = read(self.aew_root) or _empty()

    # ---- one pass

    def tick(self) -> None:
        """Settle what was posted, gather what is new, and post when the Lead is idle."""
        before = json.dumps(self.doc, sort_keys=True)  # ahead of the clear: a failure's going is a change to save
        self.doc["last_failure"] = None
        settled = self._settle()  # not settled: a posted wake is still waiting to land, at most one undelivered wake
        live = live_runs(self.state()) if settled else []
        if settled:
            self._watch(live)
            self._gather({w.run for w in live})
        if json.dumps(self.doc, sort_keys=True) != before:
            self._save()
        if settled and self.doc["wake"] is not None and not self.poster.busy():
            self._post(live)

    def failed(self, why: str) -> None:
        """A pass that failed: shown in the status line, and the next pass tries again. Without a post, ``posting``
        stays as it is: the next pass looks for it first."""
        self.doc["last_failure"] = {"at": self.clock(), "why": why}
        self._save()

    def _settle(self) -> bool:
        """Whether nothing is waiting to land. A wake recorded as ``posting`` may have been admitted by a broker that
        died in the post: it is looked for first, so it is never posted twice."""
        wake = self.doc["wake"]
        if wake is None or wake["phase"] == PENDING:
            return True
        landed = self.poster.landed(wake["id"])
        if landed == WAITING:
            if wake["phase"] == POSTING:
                self._posted(wake)
            return False
        if landed == DELIVERED:
            if wake["phase"] == POSTING:
                self._posted(wake)
            self.doc["last_delivered"] = {"id": wake["id"], "at": self.clock(), "why": wake["why"],
                                          "session": wake.get("session")}
            self.doc["wake"] = None
        else:  # never admitted, or a new session: it is still news, and the post's check decides that
            wake["phase"] = PENDING
        self._save()
        return True

    # ---- gathering

    def _watch(self, live: list[Watched]) -> None:
        marks = self.doc["marks"]
        current = {w.run for w in live}
        for run in [r for r, mark in marks.items() if mark.get("ended_told") and r not in current]:
            del marks[run]
        for w in live:
            marks.setdefault(w.run, {"work_unit": w.work_unit, "role": w.role, "launched_at": w.launched_at,
                                     "last_wake_at": self.clock(), "seq": 0, "told_outside": [],
                                     "counts": dict.fromkeys(COUNT_KEYS, 0)})

    def _dir(self, run: str) -> Path:
        return runlog.run_dir(self.aew_root, run)

    def _shown(self, run: str, mark: Mapping[str, Any]) -> int:
        """The newest trigger the Lead has been shown for ``run``, by a wake or by a wait."""
        return max(int(mark["seq"]), runlog.read_returned(self._dir(run)))

    def _ended(self, run: str, mark: Mapping[str, Any]) -> bool:
        status_, _record = runlog.observed_status(self._dir(run))
        return not runlog.possibly_live(status_, mark.get("launched_at"))

    def _gather(self, live: set[str]) -> None:
        for run, mark in list(self.doc["marks"].items()):
            ended = self._ended(run, mark)
            if ended and run not in live:  # the Lead accepted, cancelled or replaced it: its end is no news to it
                del self.doc["marks"][run]
                continue
            if ended and runlog.end_returned(self._dir(run)):  # a wait already told the Lead
                mark["ended_told"] = True
            if mark.get("ended_told"):
                if ended:
                    continue
                del mark["ended_told"]  # its heartbeat came back: it never ended, so it is watched again
                runlog.forget_end_returned(self._dir(run))
            found: list[dict[str, Any]] = []
            newest = self._shown(run, mark)
            digest = runlog.read_progress(self._dir(run))
            if ended:
                found.append({"why": K.RUN_ENDED})
            else:
                fresh, newest = P.pending(digest, newest)
                found += fresh
                found += self._outside(digest, mark, fresh)
                if not found and self.clock() - float(mark["last_wake_at"]) >= self.quiet_s():
                    found.append({"why": K.QUIET})
            if found:
                self._merge(run, found, newest)

    @staticmethod
    def _outside(digest: Mapping[str, Any] | None, mark: dict[str, Any],
                 fresh: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Paths outside the scope now that the Lead was not told of. A path that left the list is forgotten, so writing
        it outside again is news, which the digest's once-per-path trigger cannot say."""
        outside = (digest or {}).get("out_of_scope")
        if not isinstance(outside, list):
            return []
        mark["told_outside"] = [p for p in mark["told_outside"] if p in outside]
        named = {t.get("path") for t in fresh if t.get("why") == K.OUT_OF_SCOPE}
        return [{"why": K.OUT_OF_SCOPE, "path": p} for p in outside if p not in mark["told_outside"] and p not in named]

    def _merge(self, run: str, found: list[dict[str, Any]], newest: int) -> None:
        wake = self.doc["wake"]
        if wake is None:
            wake = self.doc["wake"] = {"id": self.new_id(), "phase": PENDING, "at": self.clock(), "why": [], "runs": {}}
        entry = wake["runs"].setdefault(run, {"triggers": [], "newest": 0})
        for trigger in found:
            same = next((t for t in entry["triggers"] if self._same(t, trigger)), None)
            if same is None:
                entry["triggers"].append(trigger)
        entry["newest"] = max(int(entry["newest"]), newest)
        wake["why"] = _ordered(wake)

    @staticmethod
    def _same(one: Mapping[str, Any], other: Mapping[str, Any]) -> bool:
        return (one.get("why"), one.get("path"), one.get("command")) == (
            other.get("why"), other.get("path"), other.get("command"))

    # ---- the post

    def _post(self, live: list[Watched]) -> None:
        wake = self.doc["wake"]
        self._check(wake, live)
        if not wake["why"]:  # every reason in it went stale: nothing to say
            self.doc["wake"] = None
            self._save()
            return
        shape = self._shape(wake)
        wake["phase"] = POSTING
        self._save()  # before the post: a broker that dies inside it finds this
        wake["session"] = self.poster.post(wake["id"], wake_text(wake["id"], shape))
        self._posted(wake)
        self._save()

    def _check(self, wake: dict[str, Any], live: list[Watched]) -> None:
        """No stale wakes: each reason is checked against the run as it is now, immediately before the post."""
        for run, entry in list(wake["runs"].items()):
            digest = runlog.read_progress(self._dir(run))
            mark = self.doc["marks"].get(run) or {}
            kept: list[dict[str, Any]] = []
            for trigger in entry["triggers"]:
                if self._current(trigger, entry, digest, run, mark, live):
                    kept.append(trigger)
                else:
                    self.doc["dropped"] = int(self.doc["dropped"]) + 1
                    self.doc["folded"].setdefault(run, []).append(trigger["why"])
                    if trigger.get("why") == K.RUN_ENDED:
                        # The Lead has it, or a later attempt superseded it, so it is never said: later, it would be
                        # a stale wake.
                        if run in self.doc["marks"]:
                            self.doc["marks"][run]["ended_told"] = True
                        self.doc["folded"].pop(run, None)
            entry["triggers"] = kept
            if not kept:
                del wake["runs"][run]
        wake["why"] = _ordered(wake)

    def _current(self, trigger: Mapping[str, Any], entry: Mapping[str, Any], digest: Mapping[str, Any] | None,
                 run: str, mark: Mapping[str, Any], live: list[Watched]) -> bool:
        why = trigger.get("why")
        if why == K.RUN_ENDED:  # current, unless the Lead has it (a wait, its own close) or a later attempt replaced it
            return (any(w.run == run for w in live) and not runlog.end_returned(self._dir(run)) and not any(
                w.run != run and (w.work_unit, w.role) == (mark.get("work_unit"), mark.get("role")) for w in live))
        if why == K.QUIET:  # still no other wake for this run
            return len(entry["triggers"]) == 1 and not self._ended(run, mark)
        return digest is not None and P.holds(digest, trigger)

    def _shape(self, wake: Mapping[str, Any]) -> dict[str, Any]:
        """The wake's one shape (``progress.wake``), with ``since_last_wake`` computed from the broker's own mark."""
        runs: dict[str, Any] = {}
        for run in wake["runs"]:
            digest = runlog.read_progress(self._dir(run))
            mark = self.doc["marks"].get(run) or {}
            runs[run] = None if digest is None else {**digest, "since_last_wake": self._since(run, digest, mark)}
        return P.wake(list(wake["why"]), runs)

    def _since(self, run: str, digest: Mapping[str, Any], mark: Mapping[str, Any]) -> dict[str, Any]:
        counts = digest.get("counts") or {}
        told = mark.get("counts") or {}
        since: dict[str, Any] = {k: max(0, int(counts.get(k) or 0) - int(told.get(k) or 0)) for k in COUNT_KEYS}
        meter = digest.get("since_last_wake") or {}
        since["suppressed"] = meter.get("suppressed") or {}
        folded = self.doc["folded"].get(run)
        if folded:  # what cleared before it could be said
            since["cleared"] = sorted(set(folded))
        return since

    def _posted(self, wake: dict[str, Any]) -> None:
        """The Lead has been shown it: every run's mark moves, and the wait's with it."""
        now = self.clock()
        wake["phase"] = POSTED
        self.doc["last_posted"] = {"id": wake["id"], "at": now, "why": wake["why"], "session": wake.get("session")}
        for run, entry in wake["runs"].items():
            mark = self.doc["marks"].get(run)
            if mark is None:
                continue
            mark["seq"] = max(int(mark["seq"]), int(entry["newest"]))
            runlog.write_returned(self._dir(run), int(mark["seq"]))
            mark["last_wake_at"] = now
            digest = runlog.read_progress(self._dir(run)) or {}
            counts = digest.get("counts") or {}
            mark["counts"] = {k: int(counts.get(k) or mark["counts"].get(k) or 0) for k in COUNT_KEYS}
            outside = {t.get("path") for t in entry["triggers"] if t.get("why") == K.OUT_OF_SCOPE}
            mark["told_outside"] = sorted(set(mark["told_outside"]) | {p for p in outside if p})
            self.doc["folded"].pop(run, None)
        for run, entry in wake["runs"].items():  # an ended run has said all it will: it is watched no more
            if run in self.doc["marks"] and any(t.get("why") == K.RUN_ENDED for t in entry["triggers"]):
                self.doc["marks"][run]["ended_told"] = True

    def _save(self) -> None:
        path = self.aew_root / WAKES_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, json.dumps(self.doc, sort_keys=True, separators=(",", ":")))


def _ordered(wake: Mapping[str, Any]) -> list[str]:
    """The ``why`` values a wake holds, in the wake guide's order (the guide owns the enum and its order)."""
    held = {t["why"] for entry in wake["runs"].values() for t in entry["triggers"]}
    return [w for w in K.WHY if w in held]
