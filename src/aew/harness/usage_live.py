"""Live run usage, ``aew/usage-live/v1``: one bounded sample shape and one meter for every OpenCode server (F25 for
M4-H, slice L1; the cost and usage ledger design v0.2; Q7 v0.3.1 §16 and §9.2).

Everything here is non-authoritative local telemetry. The meter measures; it never terminates, charges a cap or
computes a guard (that is the M4-H evaluator's, F19). A sample carries R1's fields from :func:`usage.normalize`, so the
same tokens price the same whether they come from a run's live file or an evaluator-owned session.

**One poll** reads the server's own REST API, through the pinned 2.0.18 operations only (``session.list``,
``session.active``, ``session.message.list`` with ``type=assistant`` and ``type=compaction``, ``server.info``), and
relies on no event payload:

1. Every session on the server, with no filter, paged to the end in ascending order. The server is private to the run
   or the evaluator. At most ``SESSION_PAGES`` pages and ``MAX_SESSIONS`` tracked sessions; past either the source is
   ``truncated`` (unknown).
2. New messages of each session whose totals moved, that is active, or whose reading is held or behind, from a saved
   ascending cursor. A message counts once, when it becomes terminal; counting stops at the first message that is not.
3. The figure, per session and per category, recomputed every poll and never accumulated:
   ``max(high-water Session.Info totals, sum of counted messages)``. Any part of the totals on no counted message (a
   title call, a compaction whose message has not completed yet) is priced on the pinned model only when the caller
   proved the server pinned to it; otherwise it is a partition with no model, which never prices.

The facts this rests on are probe P1's, pinned with citations in ``tests/fixtures/opencode/live-usage-2.0.18.json``.
In short: a call's tokens appear only when it ends (its message gets ``time.completed`` and its tokens in the same
transaction as the session's totals); title and compaction usage reach the totals through ``session.usage.recorded``
(title usage is on no message; compaction usage is on its message too, recorded a moment later); a session's totals
cover that session only, never its children; nothing lowers them, but a fork copies its source's finished messages
into a new session whose totals start at zero, so a fork's copies (created before the fork) are never counted.

The meter's own state (cursors, high-water marks, per-model sums) is persisted at ``state_path`` and is not part of the
contract. A restarted meter carries it forward under a new ``epoch``. A decrease of a session's totals is recorded as
``integrity_pending`` once and as ``integrity`` when the next poll still sees it; it never lowers the figure.
"""

from __future__ import annotations

import copy
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aew.harness import runlog
from aew.harness import usage as U
from aew.harness.opencode.client import OpenCodeError, OpenCodeUnavailable
from aew.util import atomic_write

SCHEMA = "aew/usage-live/v1"
STATE_SCHEMA = "aew/usage-live-state/v1"  # the meter's own file; not part of the contract
HARNESS = "opencode"

MAX_SAMPLE_BYTES = 4096        # §3.1: one source's sample, at its worst case (tests/unit/test_usage_live.py)
MAX_STATE_BYTES = 512 << 10    # §2.1 (R3-n2): past this the state is not kept and the source is `truncated`
MAX_SESSIONS = 256             # tracked sessions per server; a 257th makes the source `truncated`
SESSION_PAGE = 50              # the pinned session.list default page
SESSION_PAGES = 6              # at most 300 sessions listed per poll (R2 nit 1); a seventh page is `truncated`
MESSAGE_PAGE = 200             # the pinned session.message.list maximum
MESSAGE_PAGES = 1              # pages per message type per session per poll: the rest is read on the next poll
MAX_ID = 64                    # a session id, message id or source id the meter keeps; longer ones are not kept
MAX_CURSOR = 512               # an opaque cursor the meter keeps; a longer one is not kept (`truncated`)
MAX_VERSION = 32
MAX_EPOCH = 64
MAX_COUNT = U.MAX_COUNT

TYPES = ("assistant", "compaction")
STATES = ("live", "final", "server_gone")
PROMPT_STATES = ("unsent", "posting", "posted")
SOURCE_KINDS = ("run", "session")
CATEGORIES = U.CATEGORIES
NAMED = U.NAMED
NO_MODEL: tuple[str | None, str | None, str | None] = (None, None, None)


class MeterError(Exception):
    """A request the meter needed failed: no sample was taken."""


def _iso_ms(ts: float | None = None) -> str:
    moment = datetime.fromtimestamp(time.time() if ts is None else ts, UTC)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _obj(value: Any) -> Mapping[str, Any]:
    """A response object, or an empty one: a malformed reply is read as carrying nothing, never as a crash."""
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _zeros() -> dict[str, int]:
    return dict.fromkeys(CATEGORIES, 0)


def _add(into: dict[str, int], tokens: Mapping[str, int]) -> None:
    for cat in CATEGORIES:
        into[cat] = min(into.get(cat, 0) + int(tokens.get(cat, 0)), U.MAX_TOKENS)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value != value or value < 0:
        return None
    return float(value)


def _model_key(ref: Any) -> tuple[str | None, str | None, str | None]:
    """A message's ``Model.Ref`` as ``(provider, model, effort)``; OpenCode's ``default`` variant is no effort (as the
    adapter's ``_effective`` reads it). A missing or over-long id is no model: its tokens are left to the totals."""
    if not isinstance(ref, Mapping):
        return NO_MODEL
    provider = U.identifier(ref.get("providerID"), U.MAX_PROVIDER)
    model = U.identifier(ref.get("id"), U.MAX_MODEL)
    if provider is None or model is None:
        return NO_MODEL
    variant = ref.get("variant")
    effort = None if variant in (None, "", "default") else U.identifier(variant, U.MAX_EFFORT)
    return provider, model, effort


def _time(message: Mapping[str, Any], field: str) -> float | None:
    t = message.get("time")
    return _number(t.get(field)) if isinstance(t, Mapping) else None


def _empty_type() -> dict[str, Any]:
    # cursor: the opaque cursor of the page that holds the next message to count (None: the first ascending page);
    # last/last_created: the last counted message, skipped when its page is read again (in_page: it is on the page
    # at `cursor`, rather than the anchor of `cursor` itself); n: messages counted;
    # held: counting stopped at a message still in progress; more: a full page was read, so more may follow;
    # by_model: [[provider, model, effort, {category: tokens}], ...], at most U.MAX_EFFECTIVE; cost: their cost.
    return {"cursor": None, "last": None, "last_created": None, "in_page": False, "n": 0, "held": False,
            "more": False, "by_model": [], "cost": 0.0}


def _empty_session() -> dict[str, Any]:
    return {"hw": _zeros(), "hw_cost": 0.0, "full": True, "model": None, "fork_after": None, "pending": False,
            "breached": False, "types": {t: _empty_type() for t in TYPES}}


def _empty_state() -> dict[str, Any]:
    return {"schema": STATE_SCHEMA, "truncated": False, "integrity": 0, "steps": 0, "compactions": 0, "retries": 0,
            "d_min_ms": None, "max_step": dict.fromkeys(NAMED, 0), "sessions": {}}


class Meter:
    """One source's live usage: a run's private server (``source.kind == "run"``) or an evaluator-owned server
    (``"session"``, its id the root session). ``poll()`` takes one sample; ``final()`` the last one."""

    def __init__(self, client: Any, *, source: Mapping[str, str], version: str,
                 semantics_table: Mapping[str, Mapping[str, str]], s_pot: int, k_assumed: int = 2,
                 state_path: Path, live_path: Path | None = None, request_timeout_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic, main_session: str | None = None,
                 pinned_model: Mapping[str, Any] | None = None) -> None:
        kind, sid = source.get("kind"), source.get("id")
        if kind not in SOURCE_KINDS or U.identifier(sid, MAX_ID) is None:
            raise ValueError(f"a live usage source is {{kind: run|session, id}} with an id of at most {MAX_ID} "
                             f"bytes, not {dict(source)!r}")
        if isinstance(s_pot, bool) or not isinstance(s_pot, int) or s_pot < 1 \
                or isinstance(k_assumed, bool) or not isinstance(k_assumed, int) or k_assumed < 1:
            raise ValueError("s_pot and k_assumed are positive integers (the plan's A2 and A3)")
        self.client = client  # may be bound later: a run's meter exists before its server does (L2)
        self.source = {"kind": str(kind), "id": str(sid)}
        self.version = str(version)
        self.semantics_table = semantics_table
        self.s_pot, self.k_assumed = s_pot, k_assumed
        self.state_path, self.live_path = Path(state_path), Path(live_path) if live_path is not None else None
        self.request_timeout_s = request_timeout_s
        self.clock = clock
        self.main_session = main_session
        # The model a remainder of the totals is priced on, only when preflight proved every model the server can
        # call pinned to it (M2). None: such a remainder is a partition with no model, which never prices.
        self.pinned = _model_key(pinned_model) if pinned_model is not None else None
        self.server_version: str | None = None
        self.prompt_state: str | None = "unsent" if kind == "run" else None
        self.errors = 0
        self.last_error: str | None = None
        self.last_success: float | None = None  # self.clock() at the last successful poll
        self._lock = threading.RLock()
        self._ended = False
        self.state = self._load_state()
        started = time.time()
        self.epoch = f"m-{secrets.token_hex(6)}:{_iso_ms(started)}"
        self.seq = -1
        self.observed_at = _iso_ms(started)
        self.sample: dict[str, Any] | None = None
        self._active: set[str] = set()

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict[str, Any]:
        """The persisted high-water state, read with the run directory's guards (no link followed, a regular file,
        at most 16 MiB). A missing file is a fresh meter; a file that is not this meter's state is not trusted: the
        source starts `truncated`, so it is unknown rather than counted from zero (m2)."""
        try:
            text = runlog._read_text(self.state_path)  # noqa: SLF001 - the run directory's guarded read
        except OSError:
            text = ""
        if text is None:
            return _empty_state()
        try:
            loaded = json.loads(text)
        except (ValueError, RecursionError):
            loaded = None
        if not isinstance(loaded, dict) or loaded.get("schema") != STATE_SCHEMA \
                or not isinstance(loaded.get("sessions"), dict):
            return {**_empty_state(), "truncated": True}
        return loaded

    def _persist(self, state: dict[str, Any]) -> None:
        text = json.dumps(state, sort_keys=True, separators=(",", ":"))
        if len(text.encode("utf-8")) > MAX_STATE_BYTES:
            state["truncated"] = True
            text = json.dumps({**_empty_state(), "truncated": True}, sort_keys=True, separators=(",", ":"))
        atomic_write(self.state_path, text)

    # ------------------------------------------------------------------ requests

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        try:
            return self.client.get(path, params, timeout=self.request_timeout_s)
        except (OpenCodeError, OpenCodeUnavailable) as exc:
            raise MeterError(f"{path}: {exc}") from None

    def _list_sessions(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Every session, oldest first (2.0.18 orders and anchors the list on ``time.updated``: a session updated while
        the list is paged moves later, so it is met again, never skipped; duplicates are dropped by id)."""
        out: dict[str, dict[str, Any]] = {}
        params: dict[str, str] = {"order": "asc", "limit": str(SESSION_PAGE)}
        for page_no in range(SESSION_PAGES):
            page = _obj(self._get("/api/session", params))
            data = [s for s in _list(page.get("data")) if isinstance(s, dict)]
            for s in data:
                sid = U.identifier(s.get("id"), MAX_ID)
                if sid is None:
                    state["truncated"] = True  # a session the meter cannot name cannot be tracked
                    continue
                out[sid] = s
            nxt = _obj(page.get("cursor")).get("next")
            if len(data) < SESSION_PAGE or not isinstance(nxt, str) or not nxt:
                break
            if page_no == SESSION_PAGES - 1:  # a full last page: the end was not reached (R2 nit 1)
                state["truncated"] = True
                break
            params = {"cursor": nxt, "limit": str(SESSION_PAGE)}
        return list(out.values())

    # ------------------------------------------------------------------ the poll

    def poll(self) -> dict[str, Any]:
        """One sample. A failed request takes no sample: the last one is returned and its ``observed_at`` ages."""
        with self._lock:
            if self._ended:
                return self._current()
            if self.client is None:
                return self._current()
            try:
                state = self._read_server()
            except MeterError as exc:
                self.errors += 1
                self.last_error = str(exc)[:300]
                return self._current()
            self.state = state
            self.last_success = self.clock()
            self.observed_at = _iso_ms()
            try:
                return self._publish("live")
            except OSError as exc:  # a meter that cannot write never ends the run (L2); the error is counted
                self.errors += 1
                self.last_error = f"write: {exc}"[:300]
                return self._current()

    def final(self) -> dict[str, Any]:
        """The final sample: ``final`` after a successful last poll, else ``server_gone`` with the last figures."""
        with self._lock:
            if self._ended and self.sample is not None:
                return self.sample
            ok = False
            if self.client is not None:
                try:
                    self.state = self._read_server()
                    self.last_success = self.clock()
                    self.observed_at = _iso_ms()
                    ok = True
                except MeterError as exc:
                    self.errors += 1
                    self.last_error = str(exc)[:300]
            elif self.prompt_state == "unsent":
                ok = True  # no server was started: nothing could have been spent (never launched)
            self._ended = True
            return self._publish("final" if ok else "server_gone")

    def set_prompt_state(self, prompt_state: str) -> None:
        """A run's prompt state, written at once with the next ``seq`` (M6, R2-m3). A failed write raises: the
        launch refuses before its server starts (R3-m3)."""
        if self.source["kind"] != "run":
            raise ValueError("only a run source has a prompt state")
        if prompt_state not in PROMPT_STATES:
            raise ValueError(f"a prompt state is one of {PROMPT_STATES}, not {prompt_state!r}")
        with self._lock:
            self.prompt_state = prompt_state
            self._publish(self.sample["state"] if self.sample is not None else "live")

    def _current(self) -> dict[str, Any]:
        if self.sample is None:
            return self._build(self.state, "live", self.seq + 1)
        return self.sample

    def _read_server(self) -> dict[str, Any]:
        state = copy.deepcopy(self.state)
        if self.server_version is None:
            version = _obj(self._get("/api/info")).get("version")
            self.server_version = U.identifier(version, MAX_VERSION) or "unknown"
        listed = self._list_sessions(state)
        active_raw = _obj(self._get("/api/session/active")).get("data")
        self._active = {str(k) for k in active_raw} if isinstance(active_raw, dict) else set()
        sessions: dict[str, Any] = state["sessions"]
        for info in listed:
            sid = str(info["id"])
            s = sessions.get(sid)
            if s is None:
                if len(sessions) >= MAX_SESSIONS:
                    state["truncated"] = True  # the 257th session
                    continue
                s = sessions[sid] = _empty_session()
                new = True
            else:
                new = False
            moved = self._observe_totals(state, s, info)
            if new or moved or sid in self._active or any(s["types"][t]["held"] or s["types"][t]["more"]
                                                          for t in TYPES):
                for kind in TYPES:
                    if not self._read_messages(state, s, sid, kind):
                        break  # the session vanished between the list and its messages: it keeps its figure
        return state

    def _observe_totals(self, state: dict[str, Any], s: dict[str, Any], info: Mapping[str, Any]) -> bool:
        """Raise the session's high-water marks; record a decrease (§2.4). Returns whether the totals moved up."""
        tokens, trust = U.normalize_tokens(info.get("tokens"))
        s["full"] = trust == "harness_reported"
        hw = s["hw"]
        down = any(tokens[c] < hw[c] for c in CATEGORIES)
        up = any(tokens[c] > hw[c] for c in CATEGORIES)
        if down:
            if s["pending"]:
                if not s["breached"]:  # one breach per persisting decrease, seen on two consecutive polls
                    state["integrity"] = min(state["integrity"] + 1, MAX_COUNT)
                    s["breached"] = True
            else:
                s["pending"] = True
        else:
            s["pending"] = s["breached"] = False
        for c in CATEGORIES:
            hw[c] = max(hw[c], tokens[c])
        cost = _number(info.get("cost"))
        if cost is not None:
            s["hw_cost"] = max(float(s["hw_cost"]), cost)
        model = _model_key(info.get("model"))
        s["model"] = list(model[:2]) if model != NO_MODEL else None
        # A fork starts with zero totals and copies of its source's finished messages, which keep their creation
        # time: only messages created at or after the fork's own creation are its usage (P1(d); OpenCode's own stats
        # query excludes the copies the same way).
        if isinstance(info.get("fork"), Mapping):
            s["fork_after"] = _time(info, "created") or 0.0
        return up

    def _read_messages(self, state: dict[str, Any], s: dict[str, Any], sid: str, kind: str) -> bool:
        st = s["types"][kind]
        for _ in range(MESSAGE_PAGES):
            params = {"type": kind, "limit": str(MESSAGE_PAGE)}
            if st["cursor"]:
                params["cursor"] = st["cursor"]  # the pinned operation: a cursor is never combined with order
            else:
                params["order"] = "asc"
            try:
                page = _obj(self.client.get(f"/api/session/{sid}/message", params, timeout=self.request_timeout_s))
            except OpenCodeError as exc:
                if exc.status == 404:
                    return False
                raise MeterError(f"messages of {sid}: {exc}") from None
            except OpenCodeUnavailable as exc:
                raise MeterError(f"messages of {sid}: {exc}") from None
            items = [m for m in _list(page.get("data")) if isinstance(m, dict)]
            if not self._count_page(state, s, sid, kind, st, items):
                st["held"], st["more"] = True, False
                return True
            st["held"] = False
            nxt = _obj(page.get("cursor")).get("next")
            if items and isinstance(nxt, str) and nxt:
                if len(nxt) > MAX_CURSOR:
                    state["truncated"] = True
                    return True
                st["cursor"] = nxt  # every message of the page is counted: the next read starts after it
                st["in_page"] = False
            st["more"] = len(items) >= MESSAGE_PAGE
            if not st["more"]:
                return True
        return True

    def _count_page(self, state: dict[str, Any], s: dict[str, Any], sid: str, kind: str, st: dict[str, Any],
                    items: list[dict[str, Any]]) -> bool:
        """Count the page's terminal messages in order after the last counted one. False when counting stopped at
        a message still in progress (the cursor and the last counted id stay before it)."""
        last, last_created = st["last"], st["last_created"]
        start = 0
        ids = [m.get("id") for m in items]
        if last is not None and last in ids:
            start = ids.index(last) + 1
        elif last_created is not None and st.get("in_page"):
            # The last counted message was on this page and is gone (a revert deletes messages from its boundary on,
            # P1(d)): what was created before it was counted already.
            while start < len(items) and (_time(items[start], "created") or 0.0) < last_created:
                start += 1
        for m in items[start:]:
            if not self._terminal(kind, m, sid):
                return False
            mid = U.identifier(m.get("id"), MAX_ID)
            if mid is None:
                state["truncated"] = True
                return False
            created = _time(m, "created")
            copied = s["fork_after"] is not None and (created or 0.0) < float(s["fork_after"])
            if not copied:
                self._count(state, st, kind, m)
            st["last"], st["last_created"], st["in_page"] = mid, created, True
        return True

    def _terminal(self, kind: str, m: Mapping[str, Any], sid: str) -> bool:
        if kind == "compaction":  # Session.Message.Compaction: running | completed | failed (P1(f))
            return m.get("status") in ("completed", "failed")
        # R3-m1: completed, or failed, or finished while its session is idle. On 2.0.18 `finish` and `error` are only
        # ever set together with `time.completed` (P1(a)), so `time.completed` alone decides there.
        return (_time(m, "completed") is not None or isinstance(m.get("error"), Mapping)
                or (m.get("finish") is not None and sid not in self._active))

    def _count(self, state: dict[str, Any], st: dict[str, Any], kind: str, m: Mapping[str, Any]) -> None:
        tokens, trust = U.normalize_tokens(m.get("tokens"))
        st["n"] = min(st["n"] + 1, MAX_COUNT)
        if kind == "assistant":
            state["steps"] = min(state["steps"] + 1, MAX_COUNT)
            retry = m.get("retry")
            attempts = retry.get("attempt") if isinstance(retry, Mapping) else None
            if isinstance(attempts, int) and not isinstance(attempts, bool) and attempts > 0:
                state["retries"] = min(state["retries"] + attempts, MAX_COUNT)
            if trust != "absent":  # a call that billed: its duration and its size (an aborted call carries none)
                created, completed = _time(m, "created"), _time(m, "completed")
                if created is not None and completed is not None and completed >= created:
                    d = completed - created
                    state["d_min_ms"] = d if state["d_min_ms"] is None else min(float(state["d_min_ms"]), d)
                for c in NAMED:
                    state["max_step"][c] = max(int(state["max_step"][c]), tokens[c])
        elif m.get("status") == "completed":
            state["compactions"] = min(state["compactions"] + 1, MAX_COUNT)
        key = _model_key(m.get("model"))
        if key == NO_MODEL or trust == "absent":
            return  # no model (a failed compaction) or no usage: whatever it billed is in the totals (P1(b))
        cost = _number(m.get("cost"))
        if cost is not None:
            st["cost"] = float(st["cost"]) + cost
        for entry in st["by_model"]:
            if tuple(entry[:3]) == key:
                _add(entry[3], tokens)
                return
        if len(st["by_model"]) < U.MAX_EFFECTIVE:
            st["by_model"].append([*key, dict(tokens)])
        else:  # a ninth model in one session: its tokens price nothing (a partition with no model)
            for entry in st["by_model"]:
                if tuple(entry[:3]) == NO_MODEL:
                    _add(entry[3], tokens)
                    return
            st["by_model"][-1] = [*NO_MODEL, _merge(st["by_model"][-1][3], tokens)]

    # ------------------------------------------------------------------ the sample

    def _publish(self, run_state: str) -> dict[str, Any]:
        self._persist(self.state)  # first: a state past its cap marks the source truncated in this very sample
        sample = self._build(self.state, run_state, self.seq + 1)
        if self.live_path is not None:
            atomic_write(self.live_path, json.dumps(sample, sort_keys=True, separators=(",", ":")))
        self.seq += 1
        self.sample = sample
        return sample

    def _build(self, state: dict[str, Any], run_state: str, seq: int) -> dict[str, Any]:
        effective: list[dict[str, Any]] = []
        partitions: dict[tuple[str | None, str | None], dict[str, int]] = {}
        total, foreign = _zeros(), _zeros()
        cost = 0.0
        full = True

        def to(key: tuple[str | None, str | None, str | None], tokens: Mapping[str, int]) -> None:
            if not any(tokens.values()):
                return
            _add(partitions.setdefault((key[0], key[1]), _zeros()), tokens)
            if key != NO_MODEL:
                entry = {"provider": key[0], "model": key[1], "effort": key[2]}
                if entry not in effective:
                    effective.append(entry)

        for sid, s in sorted(state["sessions"].items()):
            full = full and bool(s.get("full", True))
            counted = _zeros()
            counted_cost = 0.0
            for kind in TYPES:
                st = s["types"][kind]
                counted_cost += float(st["cost"])
                for entry in st["by_model"]:
                    _add(counted, entry[3])
            figure = {c: max(int(s["hw"][c]), counted[c]) for c in CATEGORIES}
            for kind in TYPES:
                for entry in s["types"][kind]["by_model"]:
                    to(tuple(entry[:3]), entry[3])  # type: ignore[arg-type]
            remainder = {c: figure[c] - counted[c] for c in CATEGORIES}
            if any(remainder.values()):
                to(self._remainder_model(s), remainder)
            _add(total, figure)
            if self.main_session is not None and sid != self.main_session:
                _add(foreign, figure)
            cost += max(float(s["hw_cost"]), counted_cost)
        providers = [p for (p, _m) in partitions if p is not None]
        version = self.server_version if self.server_version == self.version else None
        semantics = U.resolve_semantics(self.semantics_table, version, providers)
        record = U.normalize({"tokens": total, "cost": round(cost, 9)}, None, effective, semantics,
                             source=f"harness:{HARNESS}", truncated=bool(state.get("truncated")),
                             tokens_by_model=[{"provider": p, "model": m, "tokens": t}
                                              for (p, m), t in partitions.items()] or None)
        d_min = state.get("d_min_ms")
        sample: dict[str, Any] = {
            "schema": SCHEMA, "source": dict(self.source),
            "harness": {"name": HARNESS, "version": self.server_version or U.identifier(self.version, MAX_VERSION)
                        or "unknown"},
            "epoch": self.epoch, "seq": seq, "observed_at": self.observed_at, "state": run_state,
            "s_pot": self.s_pot, "k_assumed": self.k_assumed,
            "sessions": len(state["sessions"]), "truncated": bool(state.get("truncated")),
            "in_flight": len(self._active), "steps": int(state["steps"]), "compactions": int(state["compactions"]),
            "retries": int(state["retries"]),
            "d_min_s": None if d_min is None else round(float(d_min) / 1000.0, 3),
            "max_step_tokens": {c: int(state["max_step"][c]) for c in NAMED},
            "integrity_pending": sum(1 for s in state["sessions"].values() if s.get("pending")),
            "integrity": int(state["integrity"]),
            "foreign_tokens": foreign if self.main_session is not None else None,
        }
        if self.source["kind"] == "run":
            sample["prompt_state"] = self.prompt_state
        for field in ("effective", "effective_truncated", "tokens_by_model", "token_semantics", "tokens",
                      "tokens_trust", "provider_cost_usd", "provider_cost_trust"):
            sample[field] = record[field]
        if not full and sample["tokens_trust"] == "harness_reported":
            sample["tokens_trust"] = "partial"  # some session's totals lacked a category: their zeros are not counts
        if U.serialized_size(sample) > MAX_SAMPLE_BYTES:  # the partition is optional, the bound is not (as R1's)
            sample["tokens_by_model"] = None
        return sample

    def _remainder_model(self, s: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
        """Where a session's totals exceed its counted messages, the excess is priced on the pinned model, and only
        when the session's own model is that model (or unreported); otherwise it prices nothing (M2)."""
        if self.pinned is None or self.pinned == NO_MODEL:
            return NO_MODEL
        own = s.get("model")
        if own is not None and tuple(own) != self.pinned[:2]:
            return NO_MODEL
        return self.pinned


def _merge(a: Mapping[str, int], b: Mapping[str, int]) -> dict[str, int]:
    out = _zeros()
    _add(out, a)
    _add(out, b)
    return out


def OpenCodeMeter(client: Any, *, root_session: str, version: str, s_pot: int, state_path: Path,  # noqa: N802
                  k_assumed: int = 2, pinned_model: Mapping[str, Any] | None = None,
                  request_timeout_s: float = 2.0) -> Meter:
    """The meter of an evaluator-owned OpenCode server (R, R+, the A arm's headless Lead): its source is the root
    session, and its token semantics are the OpenCode adapter's pinned table (m6). F19 owns ``client`` and places
    ``state_path`` in the arm host's run root."""
    from aew.harness.opencode.adapter import OpenCodeAdapter  # the adapter will import this module (L2)

    return Meter(client, source={"kind": "session", "id": root_session}, version=version,
                 semantics_table=OpenCodeAdapter.token_semantics, s_pot=s_pot, k_assumed=k_assumed,
                 state_path=state_path, request_timeout_s=request_timeout_s, main_session=root_session,
                 pinned_model=pinned_model)
